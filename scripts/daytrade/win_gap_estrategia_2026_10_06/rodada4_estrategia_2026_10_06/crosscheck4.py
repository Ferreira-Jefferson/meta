# -*- coding: utf-8 -*-
"""Cruzamento da CLASSE `WinGapBarra1` (motor real, M5, R$1.000, config_for) com o simulador, celula escolhida.

 (A) motor + classe em barras M5 BRUTAS (com leilao e call: gap calculado pela classe a partir das barras; flatten proprio
     as 18:15) x simulador a tick, modo A.
 (B) motor + classe em barras M5 SEM leilao (loader), gap externo `gap_por_dia` (= gap do CSV de fases), `zerar_no_fim=False`
     (flatten do motor no ultimo negocio continuo) x simulador em modo barra (mesma semantica do motor): deve ser IDENTICO.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
R2 = AQUI.parent / "rodada2_2026_10_06"
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(R2))
import ctx as C  # noqa: E402
import regras as R  # noqa: E402
import sim as S  # noqa: E402
import sizing as Z  # noqa: E402
import ticks_prep as TP  # noqa: E402
import run4 as G  # noqa: E402
import runner  # noqa: E402  (rodada 1: monta_config)
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from strategy.daytrade.lab.win_gap_barra1 import WinGapBarra1  # noqa: E402

ROOT = AQUI.parents[3]


def m5_bruto(ini="2026-04-02", fim="2026-10-05"):
    m = pd.read_parquet(ROOT / "data" / "comparativo_win_2026" / "m1_WIN$N.parquet")
    m = m[(m.index >= ini) & (m.index < pd.Timestamp(fim) + pd.Timedelta(days=1))]
    r = m.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum", "real_volume": "sum"}).dropna(subset=["open"])
    return r


def trades_df(res):
    rows = []
    for t in sorted(res.trades, key=lambda t: (t.entry_ts, t.exit_ts)):
        rows.append(dict(dia=t.entry_ts.date(), lado=t.side, qtd=t.quantity, entrada=t.entry_price, saida=t.exit_price,
                         motivo=str(getattr(t.exit_reason, "value", t.exit_reason)), exit_ts=t.exit_ts, pnl=round(t.pnl_brl, 2)))
    return pd.DataFrame(rows)


def sim_modoA(ctx, bj, stop, modo, fill="toque"):
    """Conta continua R$1.000 com o simulador (modo 'tick' ou 'barra')."""
    cash, rows = Z.CAPITAL, []
    for dia in sorted(ctx):
        c = ctx[dia]
        s = R.gatilho(c, G.ENT)
        if s == 0:
            continue
        lim = R.limite(c, s, 0.0)
        ex = G.ex_de(stop, "none")
        sa = R.saida_de(c, s, lim, ex, s, lim)
        n = Z.n_contratos(cash)
        if n < 1:
            continue
        b = C.barras_do_dia(bj, dia)
        t, p = TP.carrega(dia)
        d = S.DiaTicks(t=t, p=p, bst=b["st"], bo=b["o"], bh=b["h"], bl=b["l"], bc=b["c"])
        tsig = int(b["st"][0] + S.M5)
        tr = S.simula_tick(d, s, lim, sa, n, fill, tsig) if modo == "tick" else S.simula_barra(d, s, lim, sa.stop, None, n, fill, tsig)
        if tr is None:
            continue
        cash += tr.pnl
        rows.append(dict(dia=dia, lado="long" if s > 0 else "short", qtd=n, entrada=tr.entry_price, saida=tr.legs[-1].exit_price,
                         motivo=tr.legs[-1].reason, pnl=round(tr.pnl, 2), fill_bar_stop=tr.sai_na_barra_do_fill))
    return pd.DataFrame(rows), cash - Z.CAPITAL


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    stop = int(json.load(open(AQUI / "out" / "escolha.json"))["escolha"].split("|")[0].strip()[1:])
    bj, dj, ctx = C.constroi()
    excl = frozenset(pd.Timestamp(x).date() for x in dj[dj.excluir].index)
    cfg = runner.monta_config(Z.CAPITAL)
    print(f"celula: V2 r0, stop {stop}, sem alvo; config_for R$1.000: max_open_contracts={cfg.max_open_contracts}, session_end_time={cfg.session_end_time}")
    print(f"dias excluidos (sem operar na classe): {sorted(str(x) for x in excl)}")
    # simuladores
    st, liq_t = sim_modoA(ctx, bj, stop, "tick")
    sb, liq_b = sim_modoA(ctx, bj, stop, "barra")
    print(f"\nsimulador a tick, modo A: {len(st)} trades, liquido R${liq_t:,.2f}")
    print(f"simulador em modo barra (semantica do motor), modo A: {len(sb)} trades, liquido R${liq_b:,.2f}")

    # (A) motor + classe, barras brutas
    raw = m5_bruto()
    est = WinGapBarra1(stop_pts=stop, dias_sem_operar=excl)
    janela = raw[raw.index >= pd.Timestamp("2026-04-02")]
    res = run_intraday_backtest(janela, est, cfg)
    tA = trades_df(res)
    tA = tA[tA.dia >= pd.Timestamp("2026-04-06").date()]
    print(f"\n(A) motor + classe, M5 BRUTO (gap das barras, flatten 18:15): {len(tA)} trades, liquido R${tA.pnl.sum():,.2f}; sinais da classe {est.dias_com_sinal}")
    # (A1) gap das barras x gap do CSV
    gap_cls = {}
    last = None
    for dia, g in janela.groupby(janela.index.normalize()):
        if last is not None:
            gap_cls[dia.date()] = float(g.iloc[0].open - last)
        last = float(g.iloc[-1].close)
    dif = [(d, gap_cls[d], ctx[d]["gap"]) for d in ctx if d in gap_cls and abs(gap_cls[d] - ctx[d]["gap"]) > 0]
    print(f"gap calculado das barras brutas == gap do CSV de fases em {sum(1 for d in ctx if d in gap_cls)-len(dif)}/{len(ctx)} dias; diferentes: {dif[:5]}")
    sig_motor = set(tA.dia)
    sig_sim = set(st.dia)
    print(f"dias com trade: motor {len(sig_motor)}, simulador {len(sig_sim)}; so' no motor {sorted(str(x) for x in sig_motor - sig_sim)[:8]}; so' no simulador {sorted(str(x) for x in sig_sim - sig_motor)[:8]}")
    # comparacao dia a dia dos trades em comum com mesmo caixa nao e' possivel (caixa diverge); compara entrada/lado
    j = tA.merge(st, on="dia", suffixes=("_motor", "_sim"))
    print(f"trades em comum: {len(j)}; mesmo lado {int((j.lado_motor == j.lado_sim).sum())}; mesma entrada {int((j.entrada_motor == j.entrada_sim).sum())}; mesma quantidade {int((j.qtd_motor == j.qtd_sim).sum())}")
    j["dpnl_por_contrato"] = j.pnl_motor / j.qtd_motor - j.pnl_sim / j.qtd_sim
    print("P&L por contrato (motor - simulador a tick): mediana %.1f, media %.1f, min %.1f, max %.1f" % (j.dpnl_por_contrato.median(), j.dpnl_por_contrato.mean(), j.dpnl_por_contrato.min(), j.dpnl_por_contrato.max()))
    print("motivos de saida motor:", tA.motivo.value_counts().to_dict(), "| simulador:", st.motivo.value_counts().to_dict())
    print("trades com stop na barra do fill no simulador a tick (o motor nao ve):", int(st.fill_bar_stop.sum()))
    # (B) motor + classe, barras sem leilao e gap externo
    gap_csv = {d: ctx[d]["gap"] for d in ctx}
    est2 = WinGapBarra1(stop_pts=stop, gap_por_dia=gap_csv, zerar_no_fim=False, evitar_vencimento=False, dias_sem_operar=excl)
    res2 = run_intraday_backtest(bj, est2, cfg)
    tB = trades_df(res2)
    print(f"\n(B) motor + classe, M5 sem leilao + gap externo, flatten do motor: {len(tB)} trades, liquido R${tB.pnl.sum():,.2f}")
    a = tB[["dia", "lado", "qtd", "entrada", "saida", "motivo", "pnl"]].reset_index(drop=True)
    b = sb[["dia", "lado", "qtd", "entrada", "saida", "motivo", "pnl"]].copy()
    b["motivo"] = b.motivo.map({"stop": "stop", "flatten": "forced_flatten", "alvo": "target"})
    a["motivo"] = a.motivo.astype(str)
    b = b.reset_index(drop=True)
    igual = a.shape == b.shape and a.equals(b)
    print(f"(B) x simulador em modo barra: IGUAIS = {igual} ({len(a)} x {len(b)} trades)")
    if not igual:
        m = a.merge(b, on="dia", how="outer", suffixes=("_motor", "_sim"))
        print(m[(m.pnl_motor != m.pnl_sim)].head(8).to_string())
    json.dump(dict(stop=stop, liq_tick=liq_t, n_tick=len(st), liq_barra=liq_b, n_barra=len(sb), liq_motor_raw=float(tA.pnl.sum()), n_motor_raw=len(tA),
                   liq_motor_loader=float(tB.pnl.sum()), n_motor_loader=len(tB), identico_B=bool(igual)),
              open(AQUI / "out" / "crosscheck4.json", "w"), indent=1)


if __name__ == "__main__":
    main()
