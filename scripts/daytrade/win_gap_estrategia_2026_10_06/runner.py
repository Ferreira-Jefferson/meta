# -*- coding: utf-8 -*-
"""Roda UMA celula (variante+geometria) numa janela e devolve resumo + linha da tabela padrao.

Motor de producao intocado. Para base em BRT, `session_end_time=18:20` e' passado aqui (o
`profiles.py` do WIN@ corta em UTC 21:20 e nunca chegaria). As barras vem do carregador sem
leiloes, entao a ultima barra do dia e' a ultima do CONTINUO, nao o call.

Premissas de preenchimento (declaradas em toda linha, coluna `fill`):
  toque     : limite de entrada e alvo enchem quando a barra TOCA o nivel (motor padrao),
              fila 0/0, `limit_fill_capped_by_volume=True`. WIN NAO tem fila calibrada
              (`fidelidade.py`) -- premissa otimista, nao medida.
  atrav+1t  : sensibilidade -- entrada e alvo so' enchem se a barra ATRAVESSA o nivel em >= 1 tick
              (5 pts); preco do fill = o nivel pedido. Stop continua a mercado, no toque.
"""
from __future__ import annotations

import contextlib
import dataclasses
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import dados  # noqa: E402  (poe src/ no sys.path)

CAPITAL = 250.0           # WIN: margem R$100 x 2 (buffer) x 1,25 (reserva) = R$250
MARGEM_WIN = 100.0
TICK = 5.0
SYMBOL = "WIN@"
_CACHE: dict = {}


def monta_config(capital: float = CAPITAL):
    from backtest.intraday.profiles import config_for, profile_for
    from core.instruments import economics_for
    eco = economics_for(SYMBOL)
    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=eco.point_value_brl * eco.price_tick_size,
        trade_tick_size=eco.price_tick_size,
        initial_capital=capital,
        target_fills_as_maker=True, anchor_exits_at_fill=True,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,   # WIN sem calibracao: declarado, nao inventado
        cash_brl=capital, margin_per_contract_brl=MARGEM_WIN)
    return dataclasses.replace(cfg, session_end_time=time(18, 20))


@contextlib.contextmanager
def fill_atravessa(ticks: float = 1.0):
    """Entrada e alvo so' enchem se a barra atravessa o nivel em >= `ticks` ticks."""
    from backtest.intraday import machine as m
    o_touch, o_st = m._limit_touched, m._stop_target_touch
    delta = ticks * TICK

    def touched(order, bar):
        return (bar.low <= order.limit_price - delta) if order.side == "long" else (bar.high >= order.limit_price + delta)

    def st(pos, bar):
        stop_hit = pos.current_stop is not None and (
            bar.low <= pos.current_stop if pos.side == "long" else bar.high >= pos.current_stop)
        tgt = pos.current_target is not None and (
            bar.high >= pos.current_target + delta if pos.side == "long" else bar.low <= pos.current_target - delta)
        return stop_hit, tgt

    m._limit_touched, m._stop_target_touch = touched, st
    try:
        yield
    finally:
        m._limit_touched, m._stop_target_touch = o_touch, o_st


def dados_da_janela(base: str, ini: str, fim: str):
    k = (base, ini, fim)
    if k not in _CACHE:
        if base not in _CACHE:
            _CACHE[base] = dados.carrega(base)
        b, d = _CACHE[base]
        _CACHE[k] = dados.janela(b, d, ini, fim)
    return _CACHE[k]


def roda(spec: dict, base: str, ini: str, fim: str, fill: str = "toque", null_seed: int | None = None,
         detalhe: bool = False) -> dict:
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.report import linha_de_resultado
    from win_gap import WinGapReversao

    bars, dj, ctx = dados_da_janela(base, ini, fim)
    est = WinGapReversao(contexto_por_dia=ctx, null_seed=null_seed, **spec)
    cfg = monta_config()
    cm = fill_atravessa(1.0) if fill == "atrav+1t" else contextlib.nullcontext()
    with cm:
        res = run_intraday_backtest(bars, est, cfg)
    tr = list(res.trades)
    pnl = np.array([t.pnl_brl for t in tr], float)
    n = len(tr)
    gan, per = pnl[pnl > 0], -pnl[pnl <= 0]
    be = (per.mean() / (gan.mean() + per.mean())) if (len(gan) and len(per)) else float("nan")
    win = 100.0 * len(gan) / n if n else 0.0
    eq = res.equity_curve
    pregoes = len(set(pd.DatetimeIndex(eq.index).date)) if len(eq) else 0
    dias_trade = len({t.entry_ts.date() for t in tr})
    atraso = [max(0.0, (t.entry_ts - est.sinal_ts[t.entry_ts.date()]).total_seconds() / 60.0 - 5.0) for t in tr]
    fim_cont = dj["fim_continuo"]
    BARS = bars
    ff = [t for t in tr if str(getattr(t.exit_reason, "value", t.exit_reason)) == "forced_flatten"]
    ult = set(pd.DatetimeIndex(BARS.index[BARS["ultima_continua"].to_numpy()]))
    n_ff_ult = sum(1 for t in ff if pd.Timestamp(t.exit_ts) in ult)
    n_call = sum(1 for t in tr if t.exit_ts >= fim_cont.get(pd.Timestamp(t.exit_ts.date()), pd.Timestamp.max))
    motivos: dict = {}
    for t in tr:
        r = str(getattr(t.exit_reason, "value", t.exit_reason))
        motivos[r] = motivos.get(r, 0) + 1
    recusadas = int(getattr(res, "ordens_recusadas_por_capital", 0) or 0)
    eqmin = float(eq.min()) if len(eq) else float("nan")
    out = dict(
        spec=spec, base=base, ini=ini, fim=fim, fill=fill, null_seed=null_seed,
        n=n, liquido=float(pnl.sum()), win=win, be=100.0 * be if be == be else float("nan"),
        pregoes=pregoes, dias_trade=dias_trade, sem_trade=pregoes - dias_trade,
        elegiveis=est.dias_elegiveis, gatilho=est.dias_gatilho, ordens=est.ordens,
        sem_fill=est.ordens - n - recusadas, recusadas=recusadas,
        atraso_med=float(np.median(atraso)) if atraso else float("nan"),
        atraso_p90=float(np.percentile(atraso, 90)) if atraso else float("nan"),
        eq_min=eqmin, zerado=res.wiped_out_at is not None, motivos=motivos,
        ff=len(ff), ff_ultima_continua=n_ff_ult, saidas_barra_call=n_call,
        excl=dict(dj[dj.excluir].motivo_excl.value_counts()),
    )
    out["_linha"] = linha_de_resultado("x", res, CAPITAL)
    if detalhe:
        out["trades"] = [(t.entry_ts, t.side, t.entry_price, t.exit_ts, t.exit_price,
                          str(getattr(t.exit_reason, "value", t.exit_reason)), t.pnl_brl) for t in tr]
    return out


# ---------------------------------------------------------------------------------------------
# Modo B -- "R$250 por pregao": cada pregao e' uma run NOVA com capital inicial R$250 (o minimo
# real), sem arrastar o caixa. Mede o resultado de cada operacao com o capital real sem que uma
# morte de caixa no meio da janela esconda o resto (o modo A, conta continua, mostra a morte).
# Como os pregoes sao independentes, o nulo de direcao aleatoria e' exato: roda-se cada dia de
# gatilho forcando +1 e forcando -1 e o nulo sorteia entre os dois resultados de cada dia.
# ---------------------------------------------------------------------------------------------
def roda_pregao(spec: dict, base: str, ini: str, fim: str, fill: str = "toque") -> dict:
    from backtest.intraday.engine import run_intraday_backtest
    from win_gap import WinGapReversao

    bars, dj, ctx = dados_da_janela(base, ini, fim)
    cfg = monta_config()
    dia_b = bars.index.normalize()
    cm = fill_atravessa(1.0) if fill == "atrav+1t" else contextlib.nullcontext()
    out: dict = {}
    reais: dict = {}
    with cm:
        for forca in (+1, -1):
            est = WinGapReversao(contexto_por_dia=ctx, dir_forcada=forca, **spec)
            for dia, bd in bars.groupby(dia_b):
                if dia.date() not in ctx:
                    continue
                n0 = est.ordens
                res = run_intraday_backtest(bd, est, cfg)
                if est.ordens == n0:
                    continue                      # sem gatilho nesse dia
                tr = list(res.trades)
                out[(dia.date(), forca)] = tr[0] if tr else None
                if tr and len(tr) > 1:
                    raise RuntimeError("mais de 1 trade no pregao")
            reais.update(est.dir_real)
            if forca == +1:
                sinal_ts = dict(est.sinal_ts)
    dias_sessao = sorted(set(d.date() for d in dia_b))
    return dict(out=out, dir_real=reais, dias_sessao=dias_sessao, sinal_ts=sinal_ts, pregoes=int(dia_b.nunique()), dj=dj,
                bars=bars, elegiveis=len(ctx))


def _pnl(t):
    return 0.0 if t is None else float(t.pnl_brl)


def resume_pregao(rp: dict, spec: dict, n_null: int = 10000, seed: int = 20261006) -> dict:
    """Estatisticas do modo B: resultado real (direcao da regra), BE empirico, nulo de direcao
    aleatoria, fill, atraso, saidas no ultimo bar."""
    out, dr, bars, dj = rp["out"], rp["dir_real"], rp["bars"], rp["dj"]
    dias = sorted(dr)
    n_trig = len(dias)
    pos = np.array([_pnl(out[(d, +1)]) for d in dias], float)
    neg = np.array([_pnl(out[(d, -1)]) for d in dias], float)
    fp = np.array([out[(d, +1)] is not None for d in dias])
    fn = np.array([out[(d, -1)] is not None for d in dias])
    real = np.array([dr[d] for d in dias])
    pnl = np.where(real > 0, pos, neg)
    fil = np.where(real > 0, fp, fn)
    trades = [out[(d, int(dr[d]))] for d in dias if out[(d, int(dr[d]))] is not None]
    n = len(trades)
    liquido = float(pnl.sum())
    gan, per = pnl[pnl > 0], -pnl[pnl < 0]
    be = per.mean() / (gan.mean() + per.mean()) if len(gan) and len(per) else float("nan")
    win = 100.0 * len(gan) / n if n else 0.0
    rng = np.random.default_rng(seed)
    sg = rng.integers(0, 2, size=(n_null, n_trig)).astype(bool) if n_trig else np.zeros((0, 0), bool)
    nulo = np.where(sg, pos[None, :], neg[None, :]).sum(axis=1) if n_trig else np.zeros(1)
    p = float((1 + (nulo >= liquido).sum()) / (1 + len(nulo)))
    # win% e BE sob o nulo: media/IC95 do liquido nulo
    atrasos = [max(0.0, (t.entry_ts - rp["sinal_ts"][t.entry_ts.date()]).total_seconds() / 60.0 - 5.0) for t in trades]
    fim_cont = dj["fim_continuo"]
    BARS = bars
    ult = set(pd.DatetimeIndex(BARS.index[BARS["ultima_continua"].to_numpy()]))
    ff = [t for t in trades if str(getattr(t.exit_reason, "value", t.exit_reason)) == "forced_flatten"]
    n_ff_ult = sum(1 for t in ff if pd.Timestamp(t.exit_ts) in ult)
    n_call = sum(1 for t in trades if t.exit_ts >= fim_cont.get(pd.Timestamp(t.exit_ts.date()), pd.Timestamp.max))
    motivos: dict = {}
    for t in trades:
        r = str(getattr(t.exit_reason, "value", t.exit_reason))
        motivos[r] = motivos.get(r, 0) + 1
    # stop tocado DENTRO da barra do fill (o motor so' avalia stop/alvo a partir da barra seguinte)
    tocou = 0
    for t in trades:
        row = bars.loc[t.entry_ts]
        sp = spec["stop_pts"]
        tocou += int(row["low"] <= t.entry_price - sp) if t.side == "long" else int(row["high"] >= t.entry_price + sp)
    return dict(
        n=n, liquido=liquido, win=win, be=100.0 * be if be == be else float("nan"),
        pregoes=rp["pregoes"], dias_gatilho=n_trig, sem_fill=n_trig - n,
        taxa_sem_fill=100.0 * (n_trig - n) / n_trig if n_trig else float("nan"),
        sem_trade=rp["pregoes"] - n, atraso_med=float(np.median(atrasos)) if atrasos else float("nan"),
        atraso_p90=float(np.percentile(atrasos, 90)) if atrasos else float("nan"),
        p_nulo=p, nulo_med=float(nulo.mean()), nulo_p95=float(np.percentile(nulo, 95)),
        nulo_p5=float(np.percentile(nulo, 5)),
        ff=len(ff), ff_ultima_continua=n_ff_ult, saidas_barra_call=n_call, motivos=motivos,
        elegiveis=rp["elegiveis"], trades=trades, pnl_dia=dict(zip(dias, pnl)),
        dir_real=real, pos=pos, neg=neg, dias_sessao=rp["dias_sessao"],
        pior=float(pnl.min()) if len(pnl) else 0.0, stop_na_barra_do_fill=tocou,
    )
