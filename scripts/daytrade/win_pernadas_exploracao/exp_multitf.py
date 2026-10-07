"""Hipótese do dono: dentro de uma pernada >= 750 pts, quando o recuo passa da correção TÍPICA do M5 / M15 / H1
e o gráfico menor vira a favor, a correção acabou e o preço volta a fazer novo extremo.

Tudo em tempo real, sobre o caminho M1 (mínima/máxima na ordem da cor da vela):
- a pernada só existe depois de confirmada (preço andou 750 desde o pivô);
- recuo = distância do extremo corrente, em % do avanço já feito (extremo - início da pernada);
- resultado de cada entrada: o preço volta ao extremo anterior ANTES de a pernada virar (recuo de 750 do extremo)?
  ganho = extremo - entrada; perda = entrada - (extremo - 750). Nulo = breakeven empírico perda/(ganho+perda).
IS = até 2024-06-30, OOS = depois (frio)."""
import sys, json, math
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed

ARQ = r"C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
THR = 750.0
CUSTO = 10.0  # pts por operação ida+volta (corretagem/emolumentos + 1 tick de deslize no stop)
CORTE_IS = "2024-07-01"


def carrega():
    df = pd.read_csv(ARQ, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df["d"] = df["ts"].dt.strftime("%Y-%m-%d")
    df["mi"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    return df


# ---------- correção típica de cada gráfico (IS), em % do avanço já feito, só depois da pernada confirmada ----------
def tipica(df_is, minutos):
    vals = []
    for d, g in df_is.groupby("d"):
        b = g.groupby(g["mi"] // minutos).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"))
        p = []
        for o, h, l, c in b.itertuples(index=False):
            p += [l, h] if c >= o else [h, l]
        # zigzag + correções com avanço >= THR
        dir_ = 0; hi = lo = p[0] if p else 0; st = ext = None
        rh = None; pm = None
        for x in p:
            if dir_ == 0:
                hi = max(hi, x); lo = min(lo, x)
                if hi - lo >= THR:
                    # ordem: quem veio antes define a direção (aproximação suficiente para a mediana)
                    dir_ = 1 if p.index(lo) < p.index(hi) else -1
                    st = lo if dir_ == 1 else hi; ext = hi if dir_ == 1 else lo; rh = ext; pm = None
                continue
            s = dir_
            if s * (x - ext) > 0:
                if pm is not None:
                    dep = s * (rh - pm); av = s * (rh - st)
                    if dep >= 5 and av >= THR: vals.append(dep / av * 100)
                ext = x; rh = x; pm = None
            elif s * (ext - x) >= THR:
                st = ext; ext = x; dir_ = -s; rh = x; pm = None
            elif pm is None or s * (x - pm) < 0:
                pm = x
    return float(np.median(vals)), len(vals)


# ---------- simulação em tempo real sobre o M1 ----------
NIVEIS = [10, 15, 20, 25, 30, 40, 50]


def roda_dia(g, T):
    o, h, l, c, mi = (g[k].to_numpy() for k in ("open", "high", "low", "close", "mi"))
    n = len(o)
    fim5 = np.r_[(mi[1:] // 5) != (mi[:-1] // 5), True]
    fim15 = np.r_[(mi[1:] // 15) != (mi[:-1] // 15), True]
    ab5 = {}; ab15 = {}
    VARS = {"B: >M5 típ + vira M5": ("M5", T["M5"]), "C: >M15 típ + vira M5": ("M5", T["M15"]),
            "D: >M15 típ + vira M15": ("M15", T["M15"]), "E: >H1 típ + vira M5": ("M5", T["H1"]),
            "F: >H1 típ + vira M15": ("M15", T["H1"]), "Z: qualquer virada M5 no recuo": ("M5", 0.0)}
    dir_ = 0; hi = lo = None; hik = lok = 0; st = ext = None; leg = 0
    maxdep = 0.0; feitos = set()
    abertos = []; out = []

    def fecha_leg(final_ext, leg_id, s):
        for t in abertos:
            if t["leg"] == leg_id and not t.get("fim"):
                t["fim"] = True; t["final"] = final_ext
                if not t.get("win"):
                    t["pnl"] = -(s * (t["E"] - (t["rh"] - s * THR)))
                out.append(t)

    k = 0
    for i in range(n):
        if mi[i] // 5 not in ab5: ab5[mi[i] // 5] = o[i]
        if mi[i] // 15 not in ab15: ab15[mi[i] // 15] = o[i]
        for x in ((l[i], h[i]) if c[i] >= o[i] else (h[i], l[i])):
            k += 1
            if dir_ == 0:
                if hi is None: hi = lo = x
                if x > hi: hi = x; hik = k
                if x < lo: lo = x; lok = k
                if hi - lo >= THR:
                    dir_ = 1 if lok < hik else -1; st = lo if dir_ == 1 else hi; ext = hi if dir_ == 1 else lo
                    leg += 1; maxdep = 0.0; feitos = set()
                continue
            s = dir_
            # alvo das operações abertas desta pernada
            for t in abertos:
                if t["leg"] == leg and not t.get("win") and s * (x - t["rh"]) >= 0:
                    t["win"] = True; t["pnl"] = s * (t["rh"] - t["E"])
            if s * (x - ext) > 0:
                ext = x; maxdep = 0.0; feitos = set()
                continue
            dep = s * (ext - x)
            if dep >= THR:  # pernada virou
                fecha_leg(ext, leg, s)
                st = ext; ext = x; dir_ = -s; leg += 1; maxdep = 0.0; feitos = set()
                continue
            maxdep = max(maxdep, dep); av = s * (ext - st)
            for L in NIVEIS:  # A: ordem-limite no nível L% do avanço
                key = f"A: limite {L}%"
                if key not in feitos and dep >= L / 100 * av and L / 100 * av < THR:
                    feitos.add(key)
                    abertos.append(dict(v=key, leg=leg, s=s, rh=ext, E=ext - s * L / 100 * av, dep=L / 100 * av, av=av, d=None))
        # fechamento de vela M5 / M15 → confirmações
        if dir_ != 0 and maxdep > 0:
            s = dir_; av = s * (ext - st)
            for key, (tf, tp) in VARS.items():
                fim = fim5[i] if tf == "M5" else fim15[i]
                if not fim or key in feitos: continue
                aberto = ab5[mi[i] // 5] if tf == "M5" else ab15[mi[i] // 15]
                vira = s * (c[i] - aberto) > 0
                dep_c = s * (ext - c[i])
                if vira and maxdep / av * 100 >= tp and 0 < dep_c < THR:
                    feitos.add(key)
                    abertos.append(dict(v=key, leg=leg, s=s, rh=ext, E=c[i], dep=dep_c, av=av, d=None))
    # fim do dia: o que ficou aberto sai no último preço
    for t in abertos:
        if not t.get("fim"):
            if not t.get("win"):
                t["pnl"] = t["s"] * (c[-1] - t["E"]); t["fimdia"] = True
            t["final"] = ext if t["leg"] == leg else t["rh"]
            out.append(t)
    return out


def bloco(dias_df, T):
    res = []
    for d, g in dias_df:
        for t in roda_dia(g, T):
            res.append(dict(d=d, v=t["v"], win=bool(t.get("win")), pnl=t["pnl"], dep=t["dep"], av=t["av"],
                            mfe=t["s"] * (t["final"] - t["E"]), fimdia=bool(t.get("fimdia"))))
    return res


def resumo(x):
    n = len(x)
    if n == 0: return None
    w = x[x.win]; ls = x[~x.win]
    g = w.pnl.mean() if len(w) else 0.0; p = -ls.pnl.mean() if len(ls) else 0.0
    wr = len(w) / n; be = p / (g + p) if g + p > 0 else np.nan
    se = math.sqrt(wr * (1 - wr) / n)
    return dict(n=n, win=wr * 100, ic=1.96 * se * 100, be=be * 100, ganho=g, perda=p, liq=x.pnl.mean() - CUSTO,
                ic_liq=1.96 * x.pnl.std() / math.sqrt(n), mfe_med=x.mfe.median(), fimdia=x.fimdia.mean() * 100)


if __name__ == "__main__":
    df = carrega()
    is_ = df[df.d < CORTE_IS]
    T = {}
    for tf, m in (("M5", 5), ("M15", 15), ("H1", 60)):
        T[tf], nn = tipica(is_, m)
        print(f"correção típica {tf} (IS, mediana, % do avanço): {T[tf]:.1f}%  n={nn}", flush=True)
    grupos = list(df.groupby("d"))
    chunks = [grupos[i::8] for i in range(8)]
    res = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        for fu in as_completed([ex.submit(bloco, ch, T) for ch in chunks]):
            res += fu.result(); print("bloco pronto", len(res), flush=True)
    r = pd.DataFrame(res); r["per"] = np.where(r.d < CORTE_IS, "IS", "OOS")
    r.to_csv(sys.argv[1], index=False)
    linhas = []
    for (v, per), x in r.groupby(["v", "per"]):
        s = resumo(x); s.update(v=v, per=per); linhas.append(s)
    t = pd.DataFrame(linhas).set_index(["v", "per"]).round(1)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 20)
    print(t.to_string(), flush=True)
    json.dump(dict(T=T, tabela=t.reset_index().to_dict("records")), open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
