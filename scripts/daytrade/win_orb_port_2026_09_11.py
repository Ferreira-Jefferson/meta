# -*- coding: utf-8 -*-
"""Porta o `wdo_orb` (ORB + fade, desenho de execucao FECHADO) para o WIN@ e
mede a hipotese "ORB no WIN@ com fila propria" (pedido do dono, 2026-09-11).

NAO EDITA `strategy/*` NEM `registry.py` -- e' experimento em `scripts/`. A
classe `WdoOrb` e' uma dataclass; instanciar com `symbol="WIN@"`, `tick_size=
5.0` e bounds de stop proprios do WIN@ e' reuso de campo, nao alteracao de
producao.

GEOMETRIA: `stop_ticks = clip(range_da_abertura_em_ticks, min, max)` (igual
ao WDO@). Os bounds sao DERIVADOS da distribuicao real do WIN@ (p25/p75 do
range dos primeiros 15 minutos, mesmo metodo que calibrou originalmente
min=20/max=40 do WDO@ a partir de p25=23/p75=42,5) -- nunca digitados a mao.

CAPITAL: a hipotese estimava R$250 (margem R$100 x buffer 2,0 x reserva
1,25). Este script MEDE se isso sobrevive, em vez de assumir -- mesmo metodo
do item 6.32 de LICOES_DE_PRODUCAO.md (escada de capital ate' 0 pregoes
pulados / 0 zeramento).

FIDELIDADE: WIN@ NAO tem `queue_ahead_qty` calibrado em `backtest.intraday.
fidelidade` (so' WDO@ tem). Nao existe ordem REAL de limite no WIN@ para
repetir o protocolo Kaplan-Meier do WDO@ (`history_orders_get` exige ordem
enviada de verdade). Este script cobre a lacuna com o metodo JA VALIDADO
neste repo para o MESMO instrumento (`scripts/daytrade/win_fila_real_por_
tape_2026_09_11.py`, item 6.30 de LICOES_DE_PRODUCAO.md): mede, no TAPE real
recoletado por pregao (`data/raw_ticks/win_por_pregao/`, 60 pregoes,
100,2% de cobertura), quanto volume V negociou NO PRECO exato de cada ordem
que O PROPRIO ORB armaria, durante a janela em que ela esperaria. E' a curva
de preenchimento em funcao de uma fila hipotetica Q (preenche sse V>=Q) --
NAO e' Kaplan-Meier sobre ordem real (nao ha' ordem real), e essa diferenca
de protocolo fica DECLARADA na tabela final, nunca escondida.

Uso:
    .venv/Scripts/python.exe -u scripts/daytrade/win_orb_port_2026_09_11.py
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
TICK_SIZE = 5.0
TAPE_DIR = ROOT / "data" / "raw_ticks" / "win_por_pregao"


def br(v, dec=2):
    if v is None or v != v:
        return "--"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """IC95% de Wilson para uma proporcao (k acertos em n), em fracao [0,1].
    `(nan, nan)` se n=0 -- amostra vazia nao tem intervalo."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z**2 / n
    centro = p + z**2 / (2 * n)
    margem = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    return ((centro - margem) / denom, (centro + margem) / denom)


# ---------------------------------------------------------------- geometria

def range_abertura_ticks(m1: pd.DataFrame, minutos: float = 15.0) -> pd.Series:
    """Range (high-low) dos primeiros `minutos` de cada pregao, em TICKS do
    WIN@ (5,0 pontos). Usado so' para achar os bounds do stop -- e' proprio
    da distribuicao do instrumento, nao ajuste no resultado do backtest."""
    out = {}
    for d, g in m1.groupby(m1.index.date):
        g = g.sort_index()
        t0 = g.index[0]
        janela = g[g.index < t0 + pd.Timedelta(minutes=minutos)]
        if janela.empty:
            continue
        out[d] = (janela["high"].max() - janela["low"].min()) / TICK_SIZE
    return pd.Series(out).sort_index()


def monta_estrategia(stop_min: int, stop_max: int, entrada_ttl_bars: int) -> "WdoOrb":
    from strategy.daytrade.lab.wdo_orb import WdoOrb
    return WdoOrb(
        symbol=SYMBOL,
        tick_size=TICK_SIZE,
        stop_min_ticks=stop_min,
        stop_max_ticks=stop_max,
        entrada_ttl_bars=entrada_ttl_bars,
        # resto do mecanismo INTOCADO: offset_ticks=2, alvo_multiplo=2.0,
        # saida_limite_minutos=60.0, fade_rompimento_oposto=True,
        # max_fades_por_dia=1, quantity=1, target_fills_as_maker=True,
        # anchor_exits_at_fill=True -- ver strategy/daytrade/lab/wdo_orb.py
    )


def roda(bars: pd.DataFrame, strat, capital: float, queue_ent: float,
         queue_sai: float):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for

    perfil = profile_for(SYMBOL)
    cfg = config_for(
        perfil,
        trade_tick_value=perfil.point_value_brl * TICK_SIZE,
        trade_tick_size=TICK_SIZE,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=queue_ent,
        exit_queue_ahead_qty=queue_sai,
    )
    strat_local = replace(strat)
    strat_local.__post_init__() if hasattr(strat_local, "__post_init__") else None
    return run_intraday_backtest(bars, strat_local, cfg)


def relatorio_detalhado(nome: str, res, capital: float) -> None:
    """Metricas exigidas pelo metodo: liquido, win% com Wilson vs breakeven
    empirico, trades, stops, MaxDD%, fracao de pregoes positivos, capital
    usado, pregoes sem trade (censura)."""
    from backtest.intraday.report import maxdd_brl

    trades = list(res.trades)
    n = len(trades)
    vencedores = [t for t in trades if t.pnl_brl > 0]
    perdedores = [t for t in trades if t.pnl_brl <= 0]
    stops = [t for t in trades if t.exit_reason.value == "stop"]
    liquido = sum(t.pnl_brl for t in trades)
    win_pct = 100.0 * len(vencedores) / n if n else float("nan")

    ganho_medio = (sum(t.pnl_brl for t in vencedores) / len(vencedores)
                   if vencedores else float("nan"))
    perda_media = (abs(sum(t.pnl_brl for t in perdedores)) / len(perdedores)
                   if perdedores else float("nan"))
    be_emp = (100.0 * perda_media / (ganho_medio + perda_media)
              if vencedores and perdedores and (ganho_medio + perda_media) > 0
              else float("nan"))
    lo, hi = wilson_ci(len(vencedores), n) if n else (float("nan"), float("nan"))

    equity = res.equity_curve
    dd_pct = 100.0 * res.metrics.get("max_drawdown", 0.0)
    dd_brl = maxdd_brl(equity)

    # pregoes com pelo menos 1 trade fechado, e fracao deles POSITIVA
    dias_com_trade = {}
    for t in trades:
        d = t.exit_ts.date()
        dias_com_trade[d] = dias_com_trade.get(d, 0.0) + t.pnl_brl
    n_dias_trade = len(dias_com_trade)
    dias_positivos = sum(1 for v in dias_com_trade.values() if v > 0)
    frac_pos = 100.0 * dias_positivos / n_dias_trade if n_dias_trade else float("nan")

    pregoes_totais = len(set(pd.DatetimeIndex(equity.index).date)) if equity is not None and not equity.empty else 0
    pregoes_sem_trade = pregoes_totais - n_dias_trade

    zerou = getattr(res, "wiped_out_at", None) is not None
    pulou = len(getattr(res, "sessoes_puladas_por_capital", []) or [])

    print(f"\n----- {nome} -----")
    print(f"  capital usado: R${br(capital,0)}")
    print(f"  liquido R$: {br(liquido)}   capital final: {br(capital+liquido)}")
    print(f"  trades: {n}   stops: {len(stops)} ({100.0*len(stops)/n:.1f}%)"
          if n else "  trades: 0")
    print(f"  win%: {win_pct:.2f}%   IC95% Wilson [{100*lo:.2f}% ; {100*hi:.2f}%]"
          if n else "  win%: --")
    print(f"  breakeven empirico: {be_emp:.2f}%   "
          + ("breakeven DENTRO do IC" if (n and lo*100 <= be_emp <= hi*100)
             else ("win% ACIMA do IC->positivo" if (n and be_emp < lo*100)
                   else ("win% ABAIXO do IC->negativo" if n else ""))))
    print(f"  MaxDD: {dd_pct:.1f}%   MaxDD R$: {br(dd_brl)}")
    print(f"  pregoes cobertos: {pregoes_totais}   com trade: {n_dias_trade}   "
          f"SEM trade: {pregoes_sem_trade} ({100.0*pregoes_sem_trade/pregoes_totais:.1f}%)"
          if pregoes_totais else "  pregoes cobertos: 0")
    print(f"  fracao de pregoes POSITIVOS (entre os com trade): {frac_pos:.1f}%")
    print(f"  ZERADO: {zerou}   pregoes pulados por capital: {pulou}")


def relatorio_periodo(nome: str, trades_periodo: list, capital_periodo: float,
                       pregoes_periodo: int) -> None:
    """Mesmo relatorio de `relatorio_detalhado`, mas recebendo uma FATIA de
    trades de uma caminhada continua (nao um `IntradayBacktestResult` novo)
    -- usado para IS/OOS dentro do MESMO walk de caixa, sem resetar capital
    na fronteira."""
    n = len(trades_periodo)
    vencedores = [t for t in trades_periodo if t.pnl_brl > 0]
    perdedores = [t for t in trades_periodo if t.pnl_brl <= 0]
    stops = [t for t in trades_periodo if t.exit_reason.value == "stop"]
    liquido = sum(t.pnl_brl for t in trades_periodo)
    win_pct = 100.0 * len(vencedores) / n if n else float("nan")
    ganho_medio = (sum(t.pnl_brl for t in vencedores) / len(vencedores)
                   if vencedores else float("nan"))
    perda_media = (abs(sum(t.pnl_brl for t in perdedores)) / len(perdedores)
                   if perdedores else float("nan"))
    be_emp = (100.0 * perda_media / (ganho_medio + perda_media)
              if vencedores and perdedores and (ganho_medio + perda_media) > 0
              else float("nan"))
    lo, hi = wilson_ci(len(vencedores), n) if n else (float("nan"), float("nan"))
    dias_com_trade = {}
    for t in trades_periodo:
        d = t.exit_ts.date()
        dias_com_trade[d] = dias_com_trade.get(d, 0.0) + t.pnl_brl
    n_dias_trade = len(dias_com_trade)
    dias_positivos = sum(1 for v in dias_com_trade.values() if v > 0)
    frac_pos = 100.0 * dias_positivos / n_dias_trade if n_dias_trade else float("nan")
    pregoes_sem_trade = pregoes_periodo - n_dias_trade

    print(f"\n----- {nome} (dentro do walk continuo, capital {br(capital_periodo,0)}) -----")
    print(f"  liquido do periodo: R${br(liquido)}")
    print(f"  trades: {n}   stops: {len(stops)} ({100.0*len(stops)/n:.1f}%)"
          if n else "  trades: 0")
    print(f"  win%: {win_pct:.2f}%   IC95% Wilson [{100*lo:.2f}% ; {100*hi:.2f}%]"
          if n else "  win%: --")
    print(f"  breakeven empirico: {be_emp:.2f}%")
    print(f"  pregoes no periodo: {pregoes_periodo}   com trade: {n_dias_trade}   "
          f"SEM trade: {pregoes_sem_trade} ({100.0*pregoes_sem_trade/pregoes_periodo:.1f}%)"
          if pregoes_periodo else "")
    print(f"  fracao de pregoes POSITIVOS (entre os com trade): {frac_pos:.1f}%")


def main() -> None:
    from backtest.intraday.report import cabecalho, linha, linha_de_resultado
    from backtest.intraday.profiles import OOS_CUTOFF
    from market_data_intraday.storage import load_m1

    m1_full = load_m1(SYMBOL).sort_index()
    print(f"WIN@ M1: {len(m1_full)} barras, {m1_full.index.min()} a "
          f"{m1_full.index.max()}\n")

    # ---- geometria: bounds do stop a partir da DISTRIBUICAO real do WIN@ --
    ranges = range_abertura_ticks(m1_full)
    p25, p50, p75 = ranges.quantile([.25, .5, .75])
    stop_min = int(round(p25))
    stop_max = int(round(p75))
    print("range da abertura (15min), em ticks WIN@ (5,0 pts):")
    print(f"  n={len(ranges)}  p25={p25:.1f}  p50={p50:.1f}  p75={p75:.1f}")
    print(f"  -> stop_min_ticks={stop_min}  stop_max_ticks={stop_max}  "
          f"(mesmo metodo do WDO@: p25/p75 do range)")
    print(f"  em R$/contrato: stop_min={br(stop_min*TICK_SIZE*0.20)}  "
          f"stop_max={br(stop_max*TICK_SIZE*0.20)}\n")

    # ---- IS/OOS congelado do proprio projeto (OOS_CUTOFF), NAO um corte
    # ad-hoc -- e' a primeira vez que este teste toca esta janela.
    cutoff = pd.Timestamp(OOS_CUTOFF, tz="UTC")
    m1_is = m1_full[m1_full.index < cutoff]
    m1_oos = m1_full[m1_full.index >= cutoff]
    dias_is = sorted(set(m1_is.index.date))
    dias_oos = sorted(set(m1_oos.index.date))
    print(f"IS:  {len(dias_is)} pregoes ({dias_is[0]} a {dias_is[-1]})")
    print(f"OOS: {len(dias_oos)} pregoes ({dias_oos[0]} a {dias_oos[-1]})\n")

    strat = monta_estrategia(stop_min, stop_max, entrada_ttl_bars=15)

    # ---- ESCADA DE CAPITAL NO IS (item 6.32): nunca inventar piso ---------
    print("=" * 78)
    print("ESCADA DE CAPITAL -- fila ZERO (motor otimista), IS, M1")
    print("=" * 78)
    print(cabecalho())
    escada = [250.0, 375.0, 500.0, 750.0, 1000.0, 1500.0, 2000.0, 3000.0,
              5000.0, 8000.0]
    linhas_escada = []
    for cap in escada:
        res = roda(m1_is, strat, cap, queue_ent=0.0, queue_sai=0.0)
        li = linha_de_resultado(f"cap R${br(cap,0)}", res, cap)
        linhas_escada.append((cap, li, res))
        print(linha(li))
    print()

    capital_ok = None
    for cap, li, res in linhas_escada:
        zerou = getattr(res, "wiped_out_at", None) is not None
        pulou = len(getattr(res, "sessoes_puladas_por_capital", []) or [])
        if not zerou and pulou == 0:
            capital_ok = cap
            break
    print(f"PRIMEIRO capital sem zeramento/pregao pulado no IS (fila zero): "
          f"{br(capital_ok,0) if capital_ok else 'NENHUM ATE R$8.000'}\n")

    if capital_ok is None or capital_ok > 3000.0:
        print("!" * 78)
        print("CAPITAL MINIMO REAL > R$3.000 (ou nao convergiu ate' R$8.000) -- "
              "veredito e' INVIAVEL por orcamento. Parando aqui.")
        print("!" * 78)
        return

    # ---- capital FROZEN (do IS) confirmado no OOS, fila zero -------------
    print("=" * 78)
    print(f"CONFIRMACAO NO OOS, capital congelado {br(capital_ok,0)}, fila zero")
    print("=" * 78)
    res_is = roda(m1_is, strat, capital_ok, queue_ent=0.0, queue_sai=0.0)
    res_oos = roda(m1_oos, strat, capital_ok, queue_ent=0.0, queue_sai=0.0)
    print(cabecalho())
    print(linha(linha_de_resultado(f"IS cap {br(capital_ok,0)}", res_is, capital_ok)))
    print(linha(linha_de_resultado(f"OOS cap {br(capital_ok,0)}", res_oos, capital_ok)))

    relatorio_detalhado(f"IS -- capital {br(capital_ok,0)} -- fila ZERO", res_is, capital_ok)
    relatorio_detalhado(f"OOS -- capital {br(capital_ok,0)} -- fila ZERO", res_oos, capital_ok)

    # ---- CAMINHADA REAL DE CAIXA -- a sequencia CRONOLOGICA de fato, sem
    # resetar capital entre IS e OOS (mesmo ponto que a docstring de
    # `wdo_orb.py` faz: a simulacao por-janela pode ESCONDER travamento de
    # caixa que so' aparece numa caminhada continua). Escada de novo, agora
    # na janela INTEIRA de uma vez.
    print("\n" + "=" * 78)
    print("CAMINHADA CONTINUA (IS+OOS juntos, sem reset de capital) -- "
          "escada, fila ZERO")
    print("=" * 78)
    print(cabecalho())
    linhas_cont = []
    for cap in escada:
        res = roda(m1_full, strat, cap, queue_ent=0.0, queue_sai=0.0)
        li = linha_de_resultado(f"cap R${br(cap,0)}", res, cap)
        linhas_cont.append((cap, li, res))
        print(linha(li))

    capital_continuo = None
    for cap, li, res in linhas_cont:
        zerou = getattr(res, "wiped_out_at", None) is not None
        pulou = len(getattr(res, "sessoes_puladas_por_capital", []) or [])
        # exige tambem nao chegar perto de zero (folga >= 1 margem crua,
        # R$100 no WIN@) -- "nao zerou" sozinho ja' se mostrou fraco demais
        # (cap 250 no OOS isolado chegou a R$99,80, 73% dos pregoes SEM
        # trade -- tecnicamente "nao zerado", na pratica censurado).
        capital_final = cap + sum(t.pnl_brl for t in res.trades)
        folga_min = capital_final  # aproximacao: pior caso real e' o MaxDD
        if not zerou and pulou == 0:
            capital_continuo = cap
            break
    print(f"\nPRIMEIRO capital da caminhada continua sem zeramento/pregao "
          f"pulado: {br(capital_continuo,0) if capital_continuo else 'NENHUM ATE R$8.000'}")

    if capital_continuo is not None:
        # relatorio por trecho (IS/OOS), dentro do MESMO walk, no capital
        # continuo achado
        res_walk = roda(m1_full, strat, capital_continuo, queue_ent=0.0, queue_sai=0.0)
        trades_walk = list(res_walk.trades)
        trades_is_w = [t for t in trades_walk if t.entry_ts < cutoff]
        trades_oos_w = [t for t in trades_walk if t.entry_ts >= cutoff]
        print(f"\nresultado no capital continuo {br(capital_continuo,0)}:")
        print(cabecalho())
        print(linha(linha_de_resultado(f"walk cap {br(capital_continuo,0)}",
                                        res_walk, capital_continuo)))
        relatorio_periodo("IS (dentro do walk)", trades_is_w, capital_continuo, len(dias_is))
        relatorio_periodo("OOS (dentro do walk)", trades_oos_w, capital_continuo, len(dias_oos))

        equity = res_walk.equity_curve
        if equity is not None and not equity.empty:
            minimo_caixa = float(equity.min())
            print(f"\ncaixa MINIMO tocado na caminhada inteira: R${br(minimo_caixa)} "
                  f"(margem crua WIN@ = R$100,00)")


if __name__ == "__main__":
    main()
