"""F1 — PADROES DE CANDLE como FILTRO de entrada e como SAIDA da WinCincoMedias v2.02 (WIN M30, so' 2026).
Controle de acaso: cada variante roda tambem com filtro/saida ALEATORIO de mesma intensidade (10 sementes).
Uso: python f1_candle.py            (roda tudo, paralelo, grava f1_resultados.csv)
Sem look-ahead: todos os padroes usam so' velas fechadas ate' a barra do sinal t (lags positivos).
"""
from __future__ import annotations
import sys as _sy; _sy.path[:0] = [r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade', r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_fases_correlacao_2026_10_06\refazer\a3\copias']

import inspect
import itertools
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[0]))
import win_cinco_medias_semleilao as w; w.usar_v202()  # noqa: E402

# ---- copia de `simula` com gancho de saida extra (reproduz o baseline exato quando saida_extra=None) --------
_src = inspect.getsource(w.simula)
_src = _src.replace("aperta=(STOP_APERTA_N, STOP_APERTA_K), saida_st=(ST_H1_N, ST_H1_M) if SAIDA_ST_H1 else None):", "aperta=(STOP_APERTA_N, STOP_APERTA_K), saida_st=(ST_H1_N, ST_H1_M) if SAIDA_ST_H1 else None, saida_extra=None):", 1)
_src = _src.replace("    dias, hora, n = idx.normalize(), idx.time, len(idx)\n",
                    "    dias, hora, n = idx.normalize(), idx.time, len(idx)\n"
                    "    if saida_extra is not None:\n"
                    "        _xl, _xs = saida_extra(d)\n"
                    "        xl, xs = np.asarray(_xl, bool)[sel], np.asarray(_xs, bool)[sel]\n", 1)
_src = _src.replace("            if sai:\n                fecha(o[t] - pos * TICK, t)",
                    "            if not sai and saida_extra is not None:\n"
                    "                sai = bool(xl[j]) if pos == 1 else bool(xs[j])\n"
                    "            if sai:\n                fecha(o[t] - pos * TICK, t)", 1)
assert "saida_extra(d)" in _src and "xl[j]" in _src
exec(_src, w.__dict__)   # w.simula agora e' a copia; rodar_janelas (no mesmo modulo) a usa

BASE = None


# ---- padroes por barra (so' passado/presente) -------------------------------------------------------------
def barras(d: pd.DataFrame) -> dict:
    o, h, l, c = (d[k].astype(float) for k in "ohlc")
    rng = (h - l).replace(0, np.nan)
    body = (c - o).abs()
    top, bot = np.maximum(o, c), np.minimum(o, c)
    uw, lw = (h - top), (bot - l)
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return dict(o=o, h=h, l=l, c=c, rng=rng, body=body, uw=uw, lw=lw, atr=atr, bfrac=body / rng,
                up=(c > o), dn=(c < o))


def pat_bull(B, nome, x=None):
    """padrao na versao ALTISTA (a favor de compra). A versao baixista e' o espelho (pat_bear)."""
    o, h, l, c = B["o"], B["h"], B["l"], B["c"]
    if nome == "col":
        return B["up"]
    if nome == "maru":
        return B["up"] & (B["bfrac"] >= x)
    if nome == "wick_rej":          # pavio de rejeicao INFERIOR >= x do range (rejeicao de baixa => a favor de compra)
        return (B["lw"] / B["rng"]) >= x
    if nome == "engolfo":
        po, pc_ = o.shift(), c.shift()
        return B["up"] & (po > pc_) & (c >= po) & (o <= pc_)
    if nome == "martelo":
        return (B["lw"] >= 2 * B["body"]) & (B["uw"] <= 0.3 * B["rng"]) & (B["body"] > 0)
    if nome == "seq":               # N velas seguidas de alta (ate' t)
        n = int(x)
        return B["up"].astype(int).rolling(n).sum() == n
    raise KeyError(nome)


def pat_bear(B, nome, x=None):
    o, h, l, c = B["o"], B["h"], B["l"], B["c"]
    if nome == "col":
        return B["dn"]
    if nome == "maru":
        return B["dn"] & (B["bfrac"] >= x)
    if nome == "wick_rej":
        return (B["uw"] / B["rng"]) >= x
    if nome == "engolfo":
        po, pc_ = o.shift(), c.shift()
        return B["dn"] & (po < pc_) & (c <= po) & (o >= pc_)
    if nome == "martelo":           # estrela cadente
        return (B["uw"] >= 2 * B["body"]) & (B["lw"] <= 0.3 * B["rng"]) & (B["body"] > 0)
    if nome == "seq":
        n = int(x)
        return B["dn"].astype(int).rolling(n).sum() == n
    raise KeyError(nome)


def pat_sim(B, nome, x=None):
    """padroes simetricos (sem lado)."""
    h, l = B["h"], B["l"]
    if nome == "doji":
        return B["bfrac"] <= x
    if nome == "inside":
        return (h <= h.shift()) & (l >= l.shift())
    if nome == "outside":
        return (h > h.shift()) & (l < l.shift())
    if nome == "grande":            # range >= x ATR (esticada); ATR da vela ANTERIOR (sem a propria vela)
        return B["rng"] >= x * B["atr"].shift()
    if nome == "pequena":           # range <= x ATR
        return B["rng"] <= x * B["atr"].shift()
    raise KeyError(nome)


def anyL(s: pd.Series, L: int) -> np.ndarray:
    s = s.fillna(False).astype(bool)
    return (s.astype(int).rolling(L, min_periods=1).max() > 0).values


# ---- especificacao das variantes ---------------------------------------------------------------------------
def variantes():
    """lista de (nome, tipo, args). tipo 'F' = filtro de entrada; 'S' = saida."""
    v = []
    # lado: req = exige padrao a favor; veto = proibe padrao contra (versao contra do padrao). L = janela 1..3 velas
    for nome, xs in [("maru", (0.5, 0.6, 0.7, 0.8)), ("wick_rej", (0.3, 0.4, 0.5)), ("engolfo", (None,)),
                     ("martelo", (None,)), ("col", (None,))]:
        for x in xs:
            for L in ((1, 2, 3) if nome != "col" else (1,)):
                for modo in ("req", "veto"):
                    if nome == "col" and modo == "veto":
                        continue
                    v.append((f"F:{modo}_{nome}{'' if x is None else x}_L{L}", "F", ("lado", modo, nome, x, L)))
    for x in (2, 3, 4, 5):
        for modo in ("req", "veto"):
            v.append((f"F:{modo}_seq{x}", "F", ("lado", modo, "seq", x, 1)))
    # veto de contra-padrao 'sequencia contra' = exaustao nao se aplica; padroes simetricos
    for nome, xs in [("doji", (0.1, 0.2, 0.3)), ("inside", (None,)), ("outside", (None,)),
                     ("grande", (1.2, 1.5, 2.0, 2.5)), ("pequena", (0.5, 0.75, 1.0))]:
        for x in xs:
            for modo in ("req", "veto"):
                v.append((f"F:{modo}_{nome}{'' if x is None else x}", "F", ("sim", modo, nome, x, 1)))
    # saidas: padrao CONTRA a posicao em vela fechada -> sai na abertura seguinte
    for x in (None,):
        v.append(("S:engolfo_contra", "S", ("engolfo", None, 0.0)))
    v.append(("S:martelo_contra", "S", ("martelo", None, 0.0)))
    for x in (0.5, 0.6, 0.7):
        for mg in (0.0, 1.0):
            v.append((f"S:wick{x}_rng{mg}", "S", ("wick_rej", x, mg)))
    for x in (0.7, 0.8, 0.9):
        for mg in (0.0, 1.0):
            v.append((f"S:maru{x}_rng{mg}", "S", ("maru", x, mg)))
    for n in (2, 3):
        v.append((f"S:seq{n}_contra", "S", ("seq", n, 0.0)))
    return v


def filtro_func(args):
    kind, modo, nome, x, L = args

    def f(d):
        B = barras(d)
        if kind == "lado":
            pb, pe = pat_bull(B, nome, x), pat_bear(B, nome, x)
            if modo == "req":
                return anyL(pb, L), anyL(pe, L)
            return ~anyL(pe, L), ~anyL(pb, L)           # compra veta padrao baixista
        p = pat_sim(B, nome, x)
        a = anyL(p, L)
        return (a, a) if modo == "req" else (~a, ~a)
    return f


def saida_func(args):
    nome, x, mg = args

    def f(d):
        B = barras(d)
        pb, pe = pat_bull(B, nome, x), pat_bear(B, nome, x)
        if mg > 0:
            big = B["rng"] >= mg * B["atr"].shift()
            pb, pe = pb & big, pe & big
        return pe.fillna(False).values, pb.fillna(False).values     # (sai da compra, sai da venda)
    return f


# ---- execucao ------------------------------------------------------------------------------------------------
_D = None


def dados():
    global _D
    if _D is None:
        _D = w.carregar(2026)
    return _D


def resumir(tab, res):
    return dict(liquido=float(res["liquido"]), jan=res["janelas_pos"], pior=float(res["pior"]), trades=int(res["trades"]),
                PF=res["PF"], DD=float(res["maior_DD"]), sem_set=float(res["liquido_sem_set"]), acerto=res["acerto"])


def rodar(extra=None, saida_extra=None):
    kw = {}
    if extra is not None:
        kw["extra"] = extra
    if saida_extra is not None:
        kw["saida_extra"] = saida_extra
    tab, res = w.rodar_janelas(2026, dados=dados(), **kw)
    return tab, resumir(tab, res)


def baseline():
    global BASE
    if BASE is None:
        tab, r = rodar()
        BASE = (tab.set_index("janela").liquido, r)
    return BASE


def meses(tab, base_liq):
    x = tab.set_index("janela").liquido
    dif = (x - base_liq).round(2)
    return int((dif > 0).sum()), int((dif < 0).sum())


def aleatorio_entrada(frac_corte, seed):
    def f(d):
        est = w.alinhamento(d)
        ok = np.ones(len(d), bool)
        idx = np.flatnonzero(est != 0)
        k = int(round(frac_corte * len(idx)))
        rs = np.random.RandomState(seed * 100003 + len(d))
        if k:
            ok[rs.choice(idx, k, replace=False)] = False
        return ok, ok
    return f


def aleatorio_saida(p, seed):
    def f(d):
        rs = np.random.RandomState(seed * 100003 + len(d))
        a = rs.rand(len(d)) < p
        return a, a
    return f


def unidade(item, nseeds=10):
    nome, tipo, args = item
    base_liq, _ = baseline()
    if tipo == "F":
        fx = filtro_func(args)
        tab, r = rodar(extra=fx)
        d = dados()
        est = w.alinhamento(d)
        ok_c, ok_v = fx(d)
        sinais = est != 0
        corte = 1 - ((np.where(est == 1, ok_c, ok_v) & sinais).sum() / max(sinais.sum(), 1))
        rnd = [rodar(extra=aleatorio_entrada(corte, s))[1]["liquido"] for s in range(nseeds)]
        intens = corte
    else:
        sx = saida_func(args)
        tab, r = rodar(saida_extra=sx)
        d = dados()
        sl, ss = sx(d)
        p = float((np.asarray(sl).mean() + np.asarray(ss).mean()) / 2)
        rnd = [rodar(saida_extra=aleatorio_saida(p, s))[1]["liquido"] for s in range(nseeds)]
        intens = p
    mb, mp = meses(tab, base_liq)
    pct = 100.0 * float(np.mean([r["liquido"] > x for x in rnd]))
    return dict(variante=nome, tipo=tipo, **r, meses_melhor=mb, meses_pior=mp, intens=round(float(intens), 3),
                pct_aleat=pct, rnd_med=round(float(np.mean(rnd)), 2), rnd_max=round(float(np.max(rnd)), 2))


def variantes_refino():
    """malha fina em torno da melhor saida (pavio contra x range minimo em ATR) — 30 sementes de aleatorio."""
    return [(f"R:wick{x}_rng{mg}", "S", ("wick_rej", x, mg)) for x in (0.4, 0.5, 0.6, 0.7) for mg in (0.5, 0.75, 1.0, 1.25, 1.5)]


def passa(r, b):
    return (r["liquido"] > b["liquido"] and int(r["jan"].split("/")[0]) >= int(b["jan"].split("/")[0])
            and r["pior"] >= b["pior"] and r["DD"] <= b["DD"] and r["sem_set"] > b["sem_set"]
            and r["meses_melhor"] > r["meses_pior"] and r["trades"] >= 150 and r["pct_aleat"] >= 90)


def main():
    _, b = baseline()
    print("BASELINE", b, flush=True)
    refino = len(sys.argv) > 1 and sys.argv[1] == "refino"
    vs = variantes_refino() if refino else variantes()
    ns = 30 if refino else 10
    print(f"{len(vs)} variantes (cada uma com 10 aleatorios = {len(vs) * 11} rodadas)", flush=True)
    out = []
    with ProcessPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(unidade, it, ns): it[0] for it in vs}
        for f in as_completed(futs):
            r = f.result()
            r["passa"] = passa(r, b)
            out.append(r)
            print(f"{r['variante']:28s} liq {r['liquido']:9.2f} jan {r['jan']:>5s} pior {r['pior']:8.2f} tr {r['trades']:3d} "
                  f"PF {r['PF']} DD {r['DD']:7.2f} semset {r['sem_set']:8.2f} m+/- {r['meses_melhor']}/{r['meses_pior']} "
                  f"int {r['intens']:.3f} pct {r['pct_aleat']:5.1f} {'<== PASSA' if r['passa'] else ''}", flush=True)
    df = pd.DataFrame(out).sort_values("variante")
    df.to_csv(AQUI / ("f1_refino.csv" if refino else "f1_resultados.csv"), index=False)
    print(f"\nTOTAL variantes: {len(df)} | passam todos os criterios: {int(df.passa.sum())}", flush=True)


if __name__ == "__main__":
    main()
