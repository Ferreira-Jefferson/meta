"""Supertrend (pedido do dono, 2026-10-09): filtro de entrada, trailing stop e robô sozinho, sobre o WIN M15.

Supertrend: meio = (máx + mín)/2; bandas = meio ± mult x ATR(n) (Wilder). A banda final só anda a favor; a tendência
vira quando o close fecha além da banda oposta. Linha = banda inferior em alta, superior em baixa. Só barras fechadas.

Usos testados (grade ATR 7/10/14 x mult 2/3/4; central ATR 10 x 3):
  F  filtro na v4.1: Supertrend do M15 (ou do H1 fechado) a favor na barra de confirmação
  T  trailing na v4.1: stop = melhor(estrutura, linha do Supertrend M15) enquanto ela estiver a favor
  R  robô sozinho: entra na virada (limitada no close da barra da virada, 3 barras), stop na linha, segue a linha,
     zera no fim do pregão; mesma execução e custo da v4.1
Critério (melhoria da v4.1): pregões de TESTE do IS, total E total/DD melhores + pareado P >= 0,90 + platô; depois OOS.
Robô sozinho: só é lido como referência (IS e OOS lado a lado).
Uso: python supertrend.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "novas_2026_10_09"))
import estrategia  # noqa: E402
import escada  # noqa: E402
import operacao  # noqa: E402
import stop  # noqa: E402
from novas import pareado, N_DESC, SEM_DESC  # noqa: E402

GRADE = [(10, 3.0), (7, 3.0), (14, 3.0), (10, 2.0), (10, 4.0), (7, 2.0), (14, 4.0)]


def supertrend(df, n=10, mult=3.0):
    h, l, c = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - l, np.abs(h - pc), np.abs(l - pc)], axis=1)
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    meio = (h + l) / 2
    up_b, dn_b = meio + mult * atr, meio - mult * atr
    fu, fl = up_b.copy(), dn_b.copy()
    dirc = np.zeros(len(c)); linha = np.full(len(c), np.nan)
    for t in range(1, len(c)):
        if np.isnan(atr[t]): continue
        fu[t] = up_b[t] if (np.isnan(fu[t - 1]) or up_b[t] < fu[t - 1] or c[t - 1] > fu[t - 1]) else fu[t - 1]
        fl[t] = dn_b[t] if (np.isnan(fl[t - 1]) or dn_b[t] > fl[t - 1] or c[t - 1] < fl[t - 1]) else fl[t - 1]
        d = dirc[t - 1] or 1
        if not np.isnan(fu[t - 1]) and c[t] > fu[t - 1]: d = 1
        elif not np.isnan(fl[t - 1]) and c[t] < fl[t - 1]: d = -1
        dirc[t] = d; linha[t] = fl[t] if d == 1 else fu[t]
    return pd.DataFrame(dict(dir=dirc, linha=linha), index=df.index)


def colunas(b):
    for n, m in GRADE:
        st = supertrend(b, n, m); b[f"st_dir_{n}_{m}"], b[f"st_lin_{n}_{m}"] = st.dir, st.linha
        h1 = b.resample("60min").agg(dict(high="max", low="min", close="last")).dropna()
        s1 = supertrend(h1, n, m).dir; s1.index = s1.index + pd.Timedelta("60min")
        b[f"st_h1_{n}_{m}"] = s1.reindex(b.index, method="ffill").fillna(0)  # H1 fechado até o início da barra


def filtro(col):
    return lambda b, s: b[col].to_numpy()[s.pos.to_numpy()] * s.lado.to_numpy() == 1


def trailing(n, m):
    def mover(st, t, p, D):
        st = stop.estrutura(st, t, p, D)
        if D[f"st_dir_{n}_{m}"][t] == p.lado: st = stop.melhor(st, D[f"st_lin_{n}_{m}"][t], p.lado)
        return st
    return mover


def sinais_sozinho(dias, n, m):
    rows = []
    for seg, D in enumerate(dias):
        d, lin = D[f"st_dir_{n}_{m}"], D[f"st_lin_{n}_{m}"]
        for t in range(1, len(d) - 1):
            if d[t] != 0 and d[t] != d[t - 1] and d[t - 1] != 0 and lin[t] == lin[t]:
                rows.append(dict(seg=seg, t0=t + 1, pos=D["ini"] + t, lado=int(d[t]), stop=lin[t]))
    return pd.DataFrame(rows)


def main():
    pd.set_option("display.width", 220)
    per = {}
    for p in ("IS", "OOS"):
        b, dias, s = estrategia.preparar(p, colunas)
        per[p] = (b, dias, s, operacao.operar(s, dias, stop.inicial_v41, stop.estrutura))
    b, dias, s, base = per["IS"]
    datas = np.array(sorted(base.dia.unique()))
    desc = set(np.random.default_rng(SEM_DESC).choice(datas, N_DESC, replace=False))
    dt = pd.DatetimeIndex([D["dia"] for D in dias if D["dia"] not in desc])
    teste = lambda tr: tr[tr.dia.isin(dt)]
    rb = operacao.resumo(teste(base)); rng = np.random.default_rng(11)
    print(f"BASE v4.1 TESTE: {rb['ops']} ops, total {rb['total']:+.0f}, DD {rb['dd']:.0f}, t/DD {rb['total_dd']:.2f}", flush=True)
    V = {}
    for n, m in GRADE:
        V[f"F filtro Supertrend M15 {n}x{m}"] = ("F15", dict(filtro=filtro(f"st_dir_{n}_{m}")))
        V[f"F filtro Supertrend H1 {n}x{m}"] = ("FH1", dict(filtro=filtro(f"st_h1_{n}_{m}")))
        V[f"T trailing na linha M15 {n}x{m}"] = ("T", dict(mover=trailing(n, m)))

    def roda(p, v):
        b_, d_, s_, _ = per[p]
        if "filtro" in v: s_ = s_[v["filtro"](b_, s_)]
        return operacao.operar(s_, d_, stop.inicial_v41, v.get("mover", stop.estrutura))

    rows = []
    for nome, (g, v) in V.items():
        tr = roda("IS", v); r = operacao.resumo(teste(tr)); pr = pareado(tr, base, dt, rng)
        ok = r["total"] > rb["total"] and r["total_dd"] > rb["total_dd"] and pr >= 0.90
        rows.append(dict(grupo=g, var=nome, ok=ok, d=r["total"] - rb["total"]))
        print(f"{nome:42s} ops {r['ops']:3d} total {r['total']:+8.0f} ({100 * (r['total'] / rb['total'] - 1):+6.1f}%) DD {r['dd']:6.0f} "
              f"t/DD {r['total_dd']:5.2f} P {pr:.2f}{'  MELHORA' if ok else ''}", flush=True)
    t = pd.DataFrame(rows)
    passa = []
    for g, x in t.groupby("grupo", sort=False):
        c = x.iloc[0]; plat = (x.iloc[1:].d > 0).mean()
        print(f"{g}: central {'melhora' if c.ok else 'não melhora'}, vizinhos com total maior {plat:.0%}", flush=True)
        if c.ok and plat > 0.5: passa.append(c["var"])
    if passa:
        ro = operacao.resumo(per["OOS"][3]); print(f"OOS BASE total {ro['total']:+.0f} DD {ro['dd']:.0f} t/DD {ro['total_dd']:.2f}")
        for nome in passa:
            r = operacao.resumo(roda("OOS", V[nome][1]))
            print(f"OOS {nome}: total {r['total']:+.0f} DD {r['dd']:.0f} t/DD {r['total_dd']:.2f} -> "
                  f"{'PASSA' if r['total'] > ro['total'] and r['total_dd'] > ro['total_dd'] else 'falha'}")
    else:
        print("Nenhum uso do Supertrend melhora a v4.1 no TESTE: OOS não é aberto para filtro/trailing.")
    print("\nROBÔ SOZINHO (virada do Supertrend M15, mesma execução da v4.1, 2 contratos):", flush=True)
    for n, m in GRADE:
        lin = f"  {n}x{m}:"
        for p in ("IS", "OOS"):
            _, d_, _, _ = per[p]; sg = sinais_sozinho(d_, n, m)
            r = operacao.resumo(operacao.operar(sg, d_, lambda s_, D: s_.stop, trailing(n, m)))
            lin += f" {p} ops {r['ops']:4d} total {r['total']:+8.0f} DD {r['dd']:6.0f} acerto {r['acerto']:.0%} |"
        print(lin, flush=True)


if __name__ == "__main__":
    main()
