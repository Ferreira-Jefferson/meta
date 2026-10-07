# -*- coding: utf-8 -*-
"""Rodada 3: as duas celulas congeladas da rodada 2 num holdout (2025-12-19 a 2026-02-19), em barras M1.

Regras e criterios: CRITERIOS.md (escrito antes). Mesmo codigo de sinal/niveis da rodada 2 (`regras.py`),
sizing de producao (`sizing.py`), mesmo nulo de direcao aleatoria. Execucao M1 CONSERVADORA (sem ticks):
stop dentro da faixa da barra do fill => stop acionado.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
R2 = AQUI.parent / "rodada2_2026_10_06"
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(R2))
import dados  # noqa: E402  (rodada 1; poe src/ no path)
import regras as R  # noqa: E402
import sizing as Z  # noqa: E402
import ctx as C2  # noqa: E402  (IS: mesmos dias/contexto da rodada 2)
import analise as AN  # noqa: E402  (linhas da tabela padrao)

ROOT = Path(__file__).resolve().parents[4]
D1 = ROOT / "data" / "win_sem_leiloes"
HOLD_INI, HOLD_FIM = pd.Timestamp("2025-12-19"), pd.Timestamp("2026-02-19")
TICK, SLIP, PV, FEE = 5.0, 5.0, 0.2, 0.5
TTL_MS = 6 * 300_000
CELULAS = ["V2 r0 | S700", "V2 r0 | S.6atr"]
FILLS = ("toque", "atrav+1t")
N_NULO, SEED = 20000, 20261006


def r5(x):
    return float(np.round(x / TICK) * TICK)


# ------------------------------------------------------------------------------------------- dados
def carrega_m1():
    m1 = pd.read_parquet(D1 / "m1_WIN$N.parquet")
    return m1


_C1 = {}


def dia_m1(m1, dia):
    if dia in _C1:
        return _C1[dia]
    g = m1[m1.index.normalize() == pd.Timestamp(dia)]
    st = (g.index.hour * 3_600_000 + g.index.minute * 60_000).to_numpy().astype("int64")
    _C1[dia] = dict(st=st, o=g.open.to_numpy(float), h=g.high.to_numpy(float), l=g.low.to_numpy(float), c=g.close.to_numpy(float))
    return _C1[dia]


def ctx_holdout():
    """(ctx por dia da janela, tabela de dias com flags, dias usados no aquecimento do ATR)."""
    b5, d = dados.carrega("2026")
    pre = d[d.index < HOLD_INI]
    pre_ok = pre[~pre.excluir].index[-ATR_N:]
    janela = d[(d.index >= HOLD_INI) & (d.index <= HOLD_FIM)]
    ok = janela[~janela.excluir]
    dia5 = b5.index.normalize()
    amp = {}
    for dia in list(pre_ok) + list(ok.index):
        g = b5[dia5 == dia]
        amp[dia] = float(g.high.max() - g.low.min())
    ctx, hist = {}, [amp[x] for x in pre_ok]
    cp = d["call_preco"].shift(1)
    for dia, r in ok.iterrows():
        g = b5[dia5 == dia]
        b1 = g.iloc[0]
        ctx[dia.date()] = dict(gap=float(r.gap), vol_alto=False, prev_call=float(cp.loc[dia]),
                               atr_prev=float(np.mean(hist[-ATR_N:])) if len(hist) >= 3 else float("nan"),
                               o1=float(b1.open), h1=float(b1.high), l1=float(b1.low), c1=float(b1.close))
        hist.append(amp[dia])
    return ctx, janela, list(pre_ok)


ATR_N = 10


# ------------------------------------------------------------------------------------------- simulador M1
def sim_m1(m, side, lim, stop, qty, fill_mode, t_sinal, pior=False):
    """None = sem fill. Dict com pnl, motivo, pior excursao etc. Stop 'a mercado' com 1 tick de deslize."""
    st, o, h, l, c = m["st"], m["o"], m["h"], m["l"], m["c"]
    n = len(st)
    k0 = int(np.searchsorted(st, t_sinal, side="left"))
    k1 = int(np.searchsorted(st, t_sinal + TTL_MS, side="left"))
    nivel = lim - (TICK if fill_mode == "atrav+1t" else 0.0) * side
    fk = -1
    for k in range(k0, min(k1, n)):
        if (l[k] <= nivel) if side > 0 else (h[k] >= nivel):
            fk = k
            break
    if fk < 0:
        return None
    mae = 0.0

    def fim(reason, px, k):
        pts = (px - lim) * side
        return dict(pnl=(pts * PV - FEE) * qty, reason=reason, exit_price=px, worst=pts, fill_t=int(st[fk]), exit_k=k,
                    fill_k=fk, mae=min(mae, pts), nominal=abs(lim - stop), qty=qty, side=side)

    # barra do fill: regra conservadora
    ext = (l[fk] - lim) * side if side > 0 else (lim - h[fk]) * 1.0
    mae = min(0.0, (l[fk] - lim) if side > 0 else (lim - h[fk]))
    if (l[fk] <= stop) if side > 0 else (h[fk] >= stop):
        px = (l[fk] - SLIP) if (pior and side > 0) else ((h[fk] + SLIP) if pior else stop - SLIP * side)
        return fim("stop", px, fk)
    for k in range(fk + 1, n):
        mae = min(mae, (l[k] - lim) if side > 0 else (lim - h[k]))
        if (l[k] <= stop) if side > 0 else (h[k] >= stop):
            ref = min(o[k], stop) if side > 0 else max(o[k], stop)
            return fim("stop", ref - SLIP * side, k)
        if k == n - 1:
            return fim("flatten", c[k] - SLIP * side, k)
    return fim("flatten", c[fk] - SLIP * side, fk)


def roda_janela(m1, ctx, cid, fill, pior=False):
    """Modo B (R$1.000/pregao, q=2): real e oposta; modo A (conta continua)."""
    cel = {g["id"]: g for g in R.grade()}[cid]
    dias = sorted(ctx)
    q2 = Z.n_contratos(Z.CAPITAL)
    D = len(dias)
    real = np.zeros(D); alt = np.zeros(D); trig = np.zeros(D, bool); fil = np.zeros(D, bool)
    trades = []; atraso = []
    A = dict(cash=Z.CAPITAL, pnls=[], qts=[], recus=0, legs={k: 0 for k in AN.LEG}, min_eq=Z.CAPITAL, cash_dia=[], dias_trade=0, pregoes=D)
    cash = Z.CAPITAL
    eq_pts = [cash]
    for i, dia in enumerate(dias):
        c = ctx[dia]
        s = R.gatilho(c, cel["ent"])
        if s != 0:
            lim = R.limite(c, s, cel["ent"]["recuo"])
            sa = R.saida_de(c, s, lim, cel["ex"], s, lim)
        if s != 0 and sa is not None:
            m = dia_m1(m1, dia)
            t_sinal = 32_400_000 + 300_000
            trig[i] = True
            tr = sim_m1(m, s, lim, sa.stop, q2, fill, t_sinal, pior)
            if tr is not None:
                real[i] = tr["pnl"]; fil[i] = True; trades.append(tr)
                atraso.append((tr["fill_t"] - t_sinal) / 60000.0)
            # oposta (mesmas distancias, mesmo gatilho)
            lim_a = R.limite(c, -s, cel["ent"]["recuo"])
            sa_a = R.saida_de(c, -s, lim_a, cel["ex"], s, lim)
            ta = sim_m1(m, -s, lim_a, sa_a.stop, q2, fill, t_sinal, pior)
            if ta is not None:
                alt[i] = ta["pnl"]
            # modo A
            n = Z.n_contratos(cash)
            if n < 1:
                A["recus"] += 1
            else:
                tA = sim_m1(m, s, lim, sa.stop, min(n, 5), fill, t_sinal, pior)
                if tA is not None:
                    trough = cash + tA["mae"] * tA["qty"] * PV
                    A["min_eq"] = min(A["min_eq"], trough)
                    cash += tA["pnl"]
                    A["pnls"].append(tA["pnl"]); A["qts"].append(tA["qty"]); A["dias_trade"] += 1
                    A["legs"][tA["reason"]] += 1
                    A["atraso"] = A.get("atraso", []) + [(tA["fill_t"] - t_sinal) / 60000.0]
        A["cash_dia"].append(cash)
    A["cash"] = cash; A["liquido"] = cash - Z.CAPITAL
    A["min_eq"] = min(A["min_eq"], min(A["cash_dia"] + [Z.CAPITAL]))
    A["trig"] = int(trig.sum()); A["fills"] = len(A["pnls"])
    legs = {k: 0 for k in AN.LEG}
    for t in trades:
        legs[t["reason"]] += 1
    B = dict(real=real, alt=alt, trig=trig, fil=fil, legs=legs, q=q2, atraso=atraso, trades=trades)
    return B, A, dias


def nulo(B):
    rng = np.random.default_rng(SEED)
    S = rng.integers(0, 2, size=(N_NULO, len(B["real"]))).astype(np.float32)
    tot = S @ B["real"].astype(np.float32) + (1 - S) @ B["alt"].astype(np.float32)
    obs = float(B["real"].sum())
    return dict(p=float(((tot >= obs).sum() + 1) / (N_NULO + 1)), mu=float(tot.mean()), sd=float(tot.std()),
                p5=float(np.percentile(tot, 5)), p95=float(np.percentile(tot, 95)), obs=obs)


def resumo(B, A, dias, nl, janela):
    pnl = B["real"][B["fil"]]
    g = pnl[pnl > 0]; p = -pnl[pnl < 0]
    be = 100 * p.mean() / (g.mean() + p.mean()) if len(g) and len(p) else float("nan")
    n = int(B["fil"].sum())
    nom = np.array([t["nominal"] for t in B["trades"]]) if n else np.array([1.0])
    worst = np.array([t["worst"] for t in B["trades"]]) if n else np.array([0.0])
    mult = (-worst) / nom
    ap = np.array(A["pnls"])
    return dict(janela=janela, pregoes=len(dias), sinais=int(B["trig"].sum()), fills=n, sem_fill=100 * (B["trig"].sum() - n) / max(B["trig"].sum(), 1),
                liquido=float(pnl.sum()), win=100 * len(g) / n if n else float("nan"), be=be, r_trade=float(pnl.mean()) if n else float("nan"),
                r_pregao=float(pnl.sum() / len(dias)), sd_trade=float(pnl.std(ddof=1)) if n > 1 else float("nan"),
                pior_pts=float(worst.min()) if n else 0.0, pior_mult=float(mult.max()) if n else 0.0, pior_brl=float(pnl.min()) if n else 0.0,
                stop_na_barra_fill=int(sum(1 for t in B["trades"] if t["exit_k"] == t["fill_k"] and t["reason"] == "stop")),
                seq_perd=AN.seq_perdas(pnl), nulo=nl,
                A_liq=A["liquido"], A_recus=A["recus"], A_min_eq=A["min_eq"], A_trades=len(ap), A_ctr=(float(np.mean(A["qts"])) if A["qts"] else 0.0),
                A_cens=bool(A["recus"] or A["min_eq"] < Z.MARGEM))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    m1 = carrega_m1()
    ctx_h, jan, warm = ctx_holdout()
    _, _, ctx_is = C2.constroi()
    print(f"holdout: {len(ctx_h)} pregoes elegiveis ({HOLD_INI.date()} a {HOLD_FIM.date()}); aquecimento do ATR: {[str(x.date()) for x in warm]}")
    print(f"excluidos na janela: { {str(k.date()): v for k, v in jan[jan.excluir].motivo_excl.items()} }")
    out = {}
    linhas_h, linhas_a = [], []
    for nome, ctx in (("HOLDOUT", ctx_h), ("IS (M1 conservador)", ctx_is)):
        for cid in CELULAS:
            for fill in FILLS:
                B, A, dias = roda_janela(m1, ctx, cid, fill)
                nl = nulo(B)
                Bp, Ap, _ = roda_janela(m1, ctx, cid, fill, pior=True)
                r = resumo(B, A, dias, nl, nome)
                r["pior_variante_liq"] = float(Bp["real"].sum())
                out[(nome, cid, fill)] = dict(r=r, B=B, A=A, dias=dias)
                st = dict(be=r["be"], sem_fill=r["sem_fill"], atraso_med=float(np.median(B["atraso"])) if B["atraso"] else float("nan"), p=nl["p"], p_adj=min(1.0, 2 * nl["p"]),
                          be_a=AN.stats_be(np.array(A["pnls"])) if A["pnls"] else float("nan"),
                          sem_fill_a=100 * (A["trig"] - A["recus"] - A["fills"]) / max(A["trig"], 1),
                          atraso_med_a=float(np.median(A.get("atraso", [np.nan]))) if A.get("atraso") else float("nan"))
                (linhas_h if nome == "HOLDOUT" else linhas_a).append(AN.linha_b(f"{cid}", fill, B, dias, st))
                (linhas_h if nome == "HOLDOUT" else linhas_a).append(AN.linha_a(f"{cid}", fill, A, dias, st))
    pickle.dump({k: dict(r=v["r"]) for k, v in out.items()}, open(AQUI / "out" / "holdout_resumo.pkl", "wb"))
    ext = AN.EXTRAS
    print("\n=== HOLDOUT 2025-12-19..2026-02-19 (M1 conservador; `p adj` = 2 x p, Bonferroni de 2 celulas) ===")
    print(AN.tabela(linhas_h, ext, 12))
    print("\n=== IS 2026-04-06..2026-10-05, MESMA regra M1 conservadora ===")
    print(AN.tabela(linhas_a, ext, 12))
    print("\n=== lado a lado (modo B, 2 contratos; R$) ===")
    cab = f"{'janela':<22}{'celula':<17}{'fill':<10}{'pregoes':>8}{'sinais':>7}{'fills':>6}{'sem fill%':>10}{'liquido':>10}{'R$/trade':>10}{'R$/pregao':>10}{'win%':>7}{'BE emp%':>8}{'pior pts':>9}{'pior/stop':>10}{'p nulo':>8}{'nulo medio [p5;p95]':>26}"
    print(cab)
    for (nome, cid, fill), v in out.items():
        r = v["r"]; nl = r["nulo"]
        print(f"{nome:<22}{cid:<17}{fill:<10}{r['pregoes']:>8}{r['sinais']:>7}{r['fills']:>6}{r['sem_fill']:>10.1f}{r['liquido']:>10,.0f}{r['r_trade']:>10.1f}{r['r_pregao']:>10.1f}"
              f"{r['win']:>7.1f}{r['be']:>8.1f}{r['pior_pts']:>9.0f}{r['pior_mult']:>10.2f}{nl['p']:>8.3f}{nl['mu']:>12.0f} [{nl['p5']:.0f};{nl['p95']:.0f}]")
    # tick IS (rodada 2) para referencia
    an = pickle.load(open(R2 / "out" / "analise.pkl", "rb"))
    print("\nreferencia IS rodada 2 (ticks, modo B toque): ", {c: round(float(an['out']['toque']['obs'][an['ids'].index(c)])) for c in CELULAS})
    print("\n=== sensibilidade: stop na barra do fill ao LOW/HIGH da barra (modo B, liquido) e saidas por stop na barra do fill ===")
    for (nome, cid, fill), v in out.items():
        r = v["r"]
        print(f"{nome:<22}{cid:<17}{fill:<10} liquido base {r['liquido']:>9,.0f} | pior-caso {r['pior_variante_liq']:>9,.0f} | stops na barra do fill {r['stop_na_barra_fill']}/{r['fills']}")
    print("\n=== modo A (conta continua R$1.000) ===")
    for (nome, cid, fill), v in out.items():
        r = v["r"]
        print(f"{nome:<22}{cid:<17}{fill:<10} liquido {r['A_liq']:>9,.0f} trades {r['A_trades']:>3} contratos medios {r['A_ctr']:.1f} recusadas {r['A_recus']} caixa min {r['A_min_eq']:.0f} censurada={r['A_cens']} seq perdas B={r['seq_perd']}")
    # poder estatistico
    print("\n=== poder estatistico (alfa 0,05 unilateral, poder 0,80; z = 1,645 + 0,842) ===")
    for cid in CELULAS:
        h = out[("HOLDOUT", cid, "toque")]["r"]; i = out[("IS (M1 conservador)", cid, "toque")]["r"]
        sd = h["sd_trade"]; n = h["fills"]
        mde_trade = 2.486 * sd / np.sqrt(n)
        mde_tot = 2.486 * h["nulo"]["sd"]
        efeito_is = (i["liquido"] - i["nulo"]["mu"]) / max(i["fills"], 1)
        print(f"{cid}: holdout n={n} trades, sd por trade R${sd:.0f}; efeito minimo detectavel = R${mde_trade:.0f}/trade (media) ou R${mde_tot:,.0f} de excesso total sobre o nulo (sd do nulo R${h['nulo']['sd']:,.0f}); "
              f"efeito da IS (excesso sobre o nulo por trade) = R${efeito_is:.0f}/trade; trades necessarios para detectar o efeito da IS = {(2.486*sd/efeito_is)**2 if efeito_is>0 else float('inf'):.0f}")
    pickle.dump(out, open(AQUI / "out" / "holdout_full.pkl", "wb"))


if __name__ == "__main__":
    main()
