"""Linha de base da estrategia semanal no IS e no OOS do MT5 (a VALIDACAO nao e tocada).

Estrategia medida: recuo a MME9 com as tres MMEs semanais subindo, compra no
rompimento da maxima, stop inicial na minima do candle-sinal, saida pela linha
ATR (14x2 e 21x3). Regras em `semanal_mmes_video_2026_10_08.py`; divisao dos
dados em `base_mt5.py`.

O que imprime, para IS e OOS separados:
  1. por operacao (com e sem stop inicial), com o equilibrio EMPIRICO ao lado;
  2. ano a ano (pela data de entrada) -- melhora que so aparece num ano e regime;
  3. recuo de verdade x reversao de baixo (o achado de 2026-10-08);
  4. carteira de R$1.000 com R$1,90/ordem contra BOVA11 e contra o
     igual-ponderado dos papeis do conjunto.

Operacao ainda aberta em 2025-09-30 entra marcada no ultimo fechamento
("cortadas na borda") -- jogar fora tiraria justamente as longas, que sao o lucro.

Uso: .venv/Scripts/python.exe scripts/swing_lab/semanal_linha_de_base_2026_10_08.py
"""
from __future__ import annotations

import io
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_mt5 as base  # noqa: E402
import semanal_mmes_video_2026_10_08 as setup  # noqa: E402

CAP0, TAXA, PCT = 1000.0, 1.90, setup.CUSTO_PERNA
VARIANTES = [("atr14x2", True, "14×2"), ("atr14x2", False, "14×2 só ATR"),
             ("atr21x3", True, "21×3"), ("atr21x3", False, "21×3 só ATR")]


def br(v: float, casas: int = 2, pct: bool = True, sinal: bool = True) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    s = f"{v * 100 if pct else v:{'+' if sinal else ''}.{casas}f}".replace(".", ",")
    return s + ("%" if pct else "")


def medir(tk: str, conjunto: str) -> tuple[str, list[dict], dict, pd.Series]:
    with redirect_stdout(io.StringIO()):
        d = base.carregar(tk, conjunto)
        if len(d) < 300:  # sem as 50 semanas de aquecimento da MME50: nenhum sinal possivel
            return tk, [], {}, d["close"]
        w = setup.semanal(d)
        if w.index[-1] > d.index[-1]:  # semana em formacao no corte nao gera sinal
            w = w.iloc[:-1]
        sig = setup.sinais(w)
        # recuo de verdade: medias alinhadas, semana anterior acima da MME50, MME50 subindo ha 4 semanas
        real = (sig.e9 > sig.e21) & (sig.e21 > sig.e50) & (w.close.shift() >= sig.e50.shift()) & (sig.e50 > sig.e50.shift(4))
        ini, fim = base.janela(conjunto)
        trades = []
        for v, si, rot in VARIANTES:
            for t in setup.simular(d, w, sig, "recuo_media", v, stop_inicial=si):
                if ini <= t.entrada_data <= fim:
                    trades.append(t.__dict__ | {"ticker": tk, "rot": rot,
                                                "recuo_real": bool(real.get(pd.Timestamp(t.semana_sinal), False))})
        r52 = (w["close"] / w["close"].shift(52) - 1).dropna()
    return tk, trades, {k.strftime("%Y-%m-%d"): float(x) for k, x in r52.items()}, d["close"]


def fechar(pos, ds, est):
    for p in [p for p in pos if p["t"]["saida_data"] == ds]:
        v = p["q"] * p["t"]["saida"] * (1 - PCT) - TAXA
        est["cash"] += v; est["taxas"] += TAXA; est["n"] += 1; est["ganhos"] += v > p["custo"]
        pos.remove(p)


def carteira(trades, closes, K, ini, fim, so_top):
    """Dia a dia; sinais do mesmo dia entram pelo ranking de 12m; tamanho = patrimonio/K."""
    ent: dict[str, list] = {}
    for t in trades:
        if not so_top or (t["pct12m"] or 0) >= .7:
            ent.setdefault(t["entrada_data"], []).append(t)
    for v in ent.values():
        v.sort(key=lambda t: (-(t["pct12m"] or 0), t["ticker"]))  # desempate fixo: sem ele a ordem dos processos paralelos decidia
    dias = closes.loc[ini:fim].index
    est = dict(cash=CAP0, taxas=0.0, n=0, ganhos=0)
    pos, eq = [], []
    for dia in dias:
        ds = dia.strftime("%Y-%m-%d")
        fechar(pos, ds, est)
        for t in ent.get(ds, []):
            if len(pos) >= K or any(p["t"]["ticker"] == t["ticker"] for p in pos):
                continue
            pat = est["cash"] + sum(p["q"] * closes.at[dia, p["t"]["ticker"]] for p in pos)
            q = int((min(est["cash"], pat / K) - TAXA) // (t["entrada"] * (1 + PCT)))
            if q < 1:
                continue
            custo = q * t["entrada"] * (1 + PCT) + TAXA
            est["cash"] -= custo; est["taxas"] += TAXA
            pos.append({"t": t, "q": q, "custo": custo})
        fechar(pos, ds, est)  # estopada no proprio dia da entrada
        eq.append(est["cash"] + sum(p["q"] * closes.at[dia, p["t"]["ticker"]] for p in pos))
    e = pd.Series(eq, index=dias)
    return dict(final=float(e.iloc[-1]), dd=float((e / e.cummax() - 1).min()), n=est["n"] + len(pos), taxas=est["taxas"])


def bh(serie, ini, fim):
    s = serie.loc[ini:fim].dropna()
    q = (CAP0 - TAXA) / (s.iloc[0] * (1 + PCT))
    e = s * q
    return dict(final=float(e.iloc[-1] * (1 - PCT) - TAXA), dd=float((e / e.cummax() - 1).min()))


def linha_op(nome, g):
    r = g["ret"].to_numpy()
    ganho, perda = r[r > 0].mean(), -r[r <= 0].mean()
    be = perda / (ganho + perda)
    return (f"  {nome:16s} n={len(r):5d}  cortadas={int((g.motivo == 'aberto').sum()):3d}  acerto={br((r > 0).mean(), 1, sinal=False):>6s}"
            f"  equilíbrio={br(be, 1, sinal=False):>6s}  por op.={br(r.mean()):>7s} ±{br(1.96 * r.std(ddof=1) / np.sqrt(len(r)), sinal=False)}"
            f"  ganho méd={br(ganho, 1):>7s}  perda méd={br(-perda, 1):>7s}  dias méd={g.dias.median():4.0f}")


def main() -> None:
    bova = pd.read_parquet(base.PASTA / "BOVA11.parquet")["close"]
    for conjunto in ("is", "oos"):
        tks = base.papeis(conjunto)
        ini, fim = base.janela(conjunto)
        print(f"\n{'=' * 30} {conjunto.upper()} — {len(tks)} papéis, entradas {ini} a {fim} {'=' * 30}", flush=True)
        trades, r52, closes, curtos = [], {}, {}, []
        with ProcessPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(medir, tk, conjunto) for tk in tks]
            for i, f in enumerate(as_completed(futs), 1):
                tk, tr, r, c = f.result()
                trades += tr; closes[tk] = c
                if r:
                    r52[tk] = pd.Series(r)
                else:
                    curtos.append(tk)
                if i % 25 == 0 or i == len(tks):
                    print(f"  medidos {i}/{len(tks)}", flush=True)
        if curtos:
            print(f"  sem histórico para sinal antes do corte ({len(curtos)}): {' '.join(sorted(curtos))}", flush=True)
        pct = pd.DataFrame(r52).rank(axis=1, pct=True)
        for t in trades:
            s = t["semana_sinal"]
            v = pct.at[s, t["ticker"]] if s in pct.index else np.nan
            t["pct12m"] = None if pd.isna(v) else float(v)
        T = pd.DataFrame(trades)
        T["ano"] = T.entrada_data.str[:4]
        cl = pd.DataFrame(closes).sort_index().ffill().loc[:fim]

        print("\n1. POR OPERAÇÃO", flush=True)
        for _, _, rot in VARIANTES:
            print(linha_op(rot, T[T.rot == rot]), flush=True)

        print("\n2. ANO A ANO (por operação, com stop inicial)", flush=True)
        for rot in ("14×2", "21×3"):
            g = T[T.rot == rot]
            partes = [f"{a}: {br(h.ret.mean())} (n={len(h)})" for a, h in g.groupby("ano")]
            print(f"  {rot:5s} " + "  |  ".join(partes), flush=True)

        print("\n3. RECUO DE VERDADE x REVERSÃO DE BAIXO (com stop inicial)", flush=True)
        for rot in ("14×2", "21×3"):
            g = T[T.rot == rot]
            for k, nome in ((True, "recuo de verdade"), (False, "reversão/resto")):
                h = g[g.recuo_real == k]
                print(f"  {rot:5s} {nome:17s} n={len(h):4d} ({len(h) / len(g):4.0%})  por op.={br(h.ret.mean()):>7s} "
                      f"±{br(1.96 * h.ret.std(ddof=1) / np.sqrt(len(h)), sinal=False)}  acerto={br((h.ret > 0).mean(), 1, sinal=False)}", flush=True)

        print("\n4. CARTEIRA R$1.000 (R$1,90/ordem + 0,21%/perna)", flush=True)
        b = bh(bova, ini, fim)
        ew = cl.loc[ini:fim]
        vivos = ew.columns[ew.iloc[0].notna()]
        ewr = (ew[vivos] / ew[vivos].iloc[0]).mean(axis=1) * CAP0 * (1 - PCT) ** 2
        print(f"  BOVA11 comprar e segurar                 R${br(b['final'], 0, pct=False, sinal=False):>7s}  MaxDD {br(b['dd'], 1)}", flush=True)
        print(f"  igual-ponderado dos {len(vivos):3d} papéis (sem taxa) R${br(float(ewr.iloc[-1]), 0, pct=False, sinal=False):>7s}"
              f"  MaxDD {br(float((ewr / ewr.cummax() - 1).min()), 1)}", flush=True)
        for _, _, rot in VARIANTES:
            tv = [t for t in trades if t["rot"] == rot]
            cel = []
            for K in (1, 3, 5):
                for top in (False, True):
                    r = carteira(tv, cl, K, ini, fim, top)
                    cel.append(f"K{K}{'top' if top else '   '} R${br(r['final'], 0, pct=False, sinal=False):>6s} dd{br(r['dd'], 0):>5s}")
            print(f"  {rot:12s} " + " | ".join(cel), flush=True)


if __name__ == "__main__":
    main()
