"""Rerun com CAPITAL REAL (2026-08-27) -- WDO grid-maker F1, CopaWin, CopaWdo.

Correcao do dono sobre uma rodada anterior: a tabela de capital das MESMAS 3
estrategias tinha usado "capital inicial = 2x o valor NOCIONAL do contrato"
(preco x valor do ponto), o que estava ERRADO. A margem de garantia REAL de
day trade em mini-contrato (valores promocionais, corretoras BR) e' muito
menor: ~R$100/contrato WIN@, ~R$150/contrato WDO@. Capital inicial = 2x essa
margem (`strategy.daytrade.base.MARGIN_BUFFER_FUTUROS`, mesma convencao de
`contracts_from_capital`): R$200 (WIN@), R$300 (WDO@).

As 3 rodadas anteriores desta linha de pesquisa (WDO grid-maker F1 tick,
CopaWin, CopaWdo) foram medidas sob capital "praticamente ilimitado"
(`CAPITAL_NOCIONAL=R$1.000.000` em `copa_lab.py`/`wdo_grid_reload_f1_lab.py`),
deixando a estrategia dimensionar pelo TETO DE TESTE dela (12 WIN / 4 WDO em
`copa_lab.TETO_DE_TESTE`; 1 contrato fixo no grid-maker, ja' o teto NATURAL
da mecanica de reload). Este script reroda as 3 do ZERO -- lista de trades
NOVA, nao reescalada -- com o teto de contratos REALMENTE sustentado por
R$200/R$300 de capital.

## Por que `enforce_capital_minimo` NAO e' ligado aqui

`enforce_capital_minimo=True` aplicaria `strategy.daytrade.base.
capital_minimo_brl(preco_abertura, config.default_quantity)` no INICIO de
cada pregao (`backtest/intraday/engine.py::run_intraday_backtest`, o gate
"pula o pregao inteiro"). Essa formula foi desenhada para ACAO
(`preco_abertura` em R$/acao x `shares_per_lot`). Aplicada a um FUTURO ela
le' `preco_abertura` em PONTOS (WIN@ ~140.000, WDO@ ~5.400) como se fosse
R$/contrato -- confundindo ponto com real. Com WIN@ a ~140.000 pontos isso
computaria um "minimo" de ~R$280.000/pregao (2x `CAPITAL_MINIMO_EM_LOTES`)
contra R$200 de caixa: TODO pregao seria recusado, 0 trades -- artefato de
descasamento de unidade, nao restricao economica real. A propria docstring
de `config_for` confirma: "False para um instrumento com teto de CONTRATOS
declarado, onde `capital_minimo_brl` nao significa nada".

O portao de capital REAL para futuro e' outro, e ja' existe, em duas partes:

1. `max_open_contracts` computado por `strategy.daytrade.base.
   contracts_from_capital(cash_brl, margin_per_contract_brl, buffer=2.0,
   hard_cap=<teto oficial do perfil>)` -- quantos contratos R$200/R$300
   sustentam. Ordem que excede o teto e' RECUSADA por inteiro
   (`IntradaySessionMachine.ordens_recusadas_por_teto`, portao G5).
2. O freio INCONDICIONAL de patrimonio do motor (`engine.py`: `if
   equity_atual <= 0: wiped_out_at = ts; break` -- para o backtest INTEIRO,
   nao so' o trade) -- nao depende de `enforce_capital_minimo`, vale para
   qualquer instrumento, e e' o unico jeito de um R$200/R$300 realmente
   "quebrar" no meio da janela.

As duas juntas SAO o portao de capital real: quantos contratos cabem, e se
uma perda unica ou acumulada zera a conta.

Uso: `python -u scripts/daytrade/capital_real_rerun_2026_08_27.py`
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig  # noqa: E402
from backtest.intraday.profiles import profile_for  # noqa: E402
from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402
from core.models import IntradayExitReason  # noqa: E402
from strategy.daytrade.base import MARGIN_BUFFER_FUTUROS, contracts_from_capital  # noqa: E402

import copa_lab as L  # noqa: E402
from run_copa_score import CALIBRACAO_IS  # noqa: E402
import wdo_grid_reload_f1_lab as G  # noqa: E402
import wdo_grid_reload_f1_tick_lab as GT  # noqa: E402

# ---------------------------------------------------------------------------
# capital real (confirmado pelo dono 2026-08-27)
# ---------------------------------------------------------------------------
MARGEM_WIN_BRL = 100.0
MARGEM_WDO_BRL = 150.0
CAPITAL_WIN_BRL = MARGEM_WIN_BRL * MARGIN_BUFFER_FUTUROS   # R$200
CAPITAL_WDO_BRL = MARGEM_WDO_BRL * MARGIN_BUFFER_FUTUROS   # R$300

N_SEMENTES = 30
P_ALVO = 0.5


@dataclasses.dataclass
class RodadaReal:
    rotulo: str
    symbol: str
    initial_capital: float
    teto_efetivo: int
    resultado: object
    pregoes_janela: int  # pregoes no INPUT (bars) antes de qualquer wipeout


# ---------------------------------------------------------------------------
# rodadas BASE (p=100%, capital real)
# ---------------------------------------------------------------------------

def roda_copa_real(symbol: str, cash: float, margin: float) -> RodadaReal:
    perfil = profile_for(symbol)
    teto = contracts_from_capital(cash, margin, hard_cap=perfil.max_open_contracts)
    params = dict(CALIBRACAO_IS[symbol])
    bars = L.barras(symbol).in_sample()
    pregoes_janela = len(set(bars.index.date))
    if teto < 1:
        raise SystemExit(
            f"[capital_real] {symbol}: contracts_from_capital devolveu {teto} -- "
            f"R${num_br(cash)} de capital nao sustenta nem 1 contrato a R${num_br(margin)} "
            f"de margem x {MARGIN_BUFFER_FUTUROS} de buffer."
        )
    instancia = L.robo(symbol, teto, **params)
    cfg_nocional = L.config(symbol, teto, pernas_maker=int(getattr(instancia, "pernas_maker", 1)))
    cfg = dataclasses.replace(cfg_nocional, initial_capital=cash)
    resultado = run_intraday_backtest(bars, instancia, cfg)
    return RodadaReal(rotulo=f"Copa{symbol.rstrip('@').capitalize()}", symbol=symbol,
                       initial_capital=cash, teto_efetivo=teto, resultado=resultado,
                       pregoes_janela=pregoes_janela)


def roda_wdo_grid_real(cash: float, margin: float) -> RodadaReal:
    symbol = "WDO@"
    perfil = profile_for(symbol)
    teto = contracts_from_capital(cash, margin, hard_cap=perfil.max_open_contracts)
    dias, tick_bars = GT.carregar_tick_bars()
    pregoes_janela = len(dias)
    if teto < 1:
        raise SystemExit(
            f"[capital_real] wdo_grid: contracts_from_capital devolveu {teto} -- "
            f"R${num_br(cash)} de capital nao sustenta nem 1 contrato."
        )
    cfg_nocional: IntradayBacktestConfig = G.montar_config()
    # `G.MAX_OPEN_CONTRATOS=1` ja' e' o teto NATURAL da mecanica de reload
    # (a propria estrategia nunca pede mais de 1 posicao por vez) -- checa
    # que bate com o teto por CAPITAL antes de so' confiar no numero antigo.
    if teto != cfg_nocional.max_open_contracts:
        cfg_nocional = dataclasses.replace(cfg_nocional, max_open_contracts=teto)
    cfg = dataclasses.replace(cfg_nocional, initial_capital=cash)
    resultado = G.rodar(tick_bars, cfg)
    return RodadaReal(rotulo="WdoGridReloadMaker (F1, tick)", symbol=symbol,
                       initial_capital=cash, teto_efetivo=teto, resultado=resultado,
                       pregoes_janela=pregoes_janela)


# ---------------------------------------------------------------------------
# rejeicao i.i.d. p=50%, com MaxDD reconstruido cronologicamente por semente
# ---------------------------------------------------------------------------

def rejeicao_p_alvo(rodada: RodadaReal, p: float = P_ALVO, n_sementes: int = N_SEMENTES,
                     seed_base: int = 0) -> dict:
    trades = list(rodada.resultado.trades)
    n = len(trades)
    pregoes_base = len(set(pd.DatetimeIndex(rodada.resultado.equity_curve.index).date)) \
        if rodada.resultado.equity_curve is not None and not rodada.resultado.equity_curve.empty else 0

    capital_final = np.empty(n_sementes)
    lucro = np.empty(n_sementes)
    lucro_dia = np.empty(n_sementes)
    n_trades = np.empty(n_sementes)
    n_stops = np.empty(n_sementes)
    maxdd = np.empty(n_sementes)

    for s in range(n_sementes):
        rng = np.random.default_rng(seed_base + s)
        aceita = rng.random(n) < p if n else np.array([], dtype=bool)  # sorteio POR TRADE, sem olhar pnl
        aceitos = [t for t, a in zip(trades, aceita) if a]
        pnls = [t.pnl_brl for t in aceitos]
        liquido_s = float(sum(pnls))

        lucro[s] = liquido_s
        capital_final[s] = rodada.initial_capital + liquido_s
        lucro_dia[s] = (liquido_s / pregoes_base) if pregoes_base else 0.0
        n_trades[s] = len(aceitos)
        n_stops[s] = sum(1 for t in aceitos if t.exit_reason == IntradayExitReason.STOP)

        # MaxDD reconstruido CRONOLOGICAMENTE (trades ja' vem em ordem de
        # fechamento -- `run_intraday_backtest` acumula `trades` bar a bar)
        # a partir do NOVO `initial_capital`: capital acumulado degrau a
        # degrau, pico-a-vale via `report.maxdd_brl` (mesma funcao canonica
        # de todo o resto do repo).
        curva = [rodada.initial_capital]
        acc = rodada.initial_capital
        for pnl in pnls:
            acc += pnl
            curva.append(acc)
        maxdd[s] = maxdd_brl(pd.Series(curva))

    return dict(
        pregoes_base=pregoes_base,
        capital_final=capital_final, lucro=lucro, lucro_dia=lucro_dia,
        trades=n_trades, stops=n_stops, maxdd=maxdd,
    )


def _media_desvio(arr: np.ndarray) -> str:
    return f"{num_br(float(arr.mean()))} +/- {num_br(float(arr.std(ddof=1)) if len(arr) > 1 else 0.0)}"


# ---------------------------------------------------------------------------
# relatorio
# ---------------------------------------------------------------------------

def linha_base(r: RodadaReal) -> None:
    res = r.resultado
    trades = list(res.trades)
    liquido = sum(t.pnl_brl for t in trades)
    dd = maxdd_brl(res.equity_curve)
    total_ordens = res.ordens_aceitas + res.ordens_recusadas_por_teto
    recusas_pct = (100.0 * res.ordens_recusadas_por_teto / total_ordens) if total_ordens else 0.0
    pregoes_rodados = len(set(pd.DatetimeIndex(res.equity_curve.index).date)) \
        if res.equity_curve is not None and not res.equity_curve.empty else 0
    zerou = " ZERADO" if getattr(res, "wiped_out_at", None) is not None else ""
    print(f"{r.rotulo:<28}{r.symbol:<8}{('R$'+num_br(r.initial_capital,0)):>12}"
          f"{r.teto_efetivo:>10}{res.ordens_recusadas_por_teto:>26}{len(trades):>10}"
          f"{('R$'+num_br(liquido)):>16}{('R$'+num_br(dd)):>14}{zerou}")
    print(f"    [diag] ordens aceitas={res.ordens_aceitas} recusadas={res.ordens_recusadas_por_teto} "
          f"({num_br(recusas_pct,1)}%) | pregoes na janela={r.pregoes_janela} | "
          f"pregoes realmente simulados={pregoes_rodados}"
          + (f" | wiped_out_at={res.wiped_out_at}" if getattr(res, 'wiped_out_at', None) is not None else ""))


def linha_p50(r: RodadaReal, stats: dict) -> None:
    print(f"{r.rotulo:<28}{r.symbol:<8}{('R$'+num_br(r.initial_capital,0)):>12}"
          f"{_media_desvio(stats['capital_final']):>26}{_media_desvio(stats['lucro']):>22}"
          f"{_media_desvio(stats['lucro_dia']):>18}{_media_desvio(stats['trades']):>16}"
          f"{_media_desvio(stats['stops']):>14}{_media_desvio(stats['maxdd']):>20}")


def main() -> None:
    print(f"[capital_real] MARGIN_BUFFER_FUTUROS={MARGIN_BUFFER_FUTUROS} | "
          f"WIN@ margem=R${num_br(MARGEM_WIN_BRL,0)} -> capital=R${num_br(CAPITAL_WIN_BRL,0)} | "
          f"WDO@ margem=R${num_br(MARGEM_WDO_BRL,0)} -> capital=R${num_br(CAPITAL_WDO_BRL,0)}")

    rodadas: list[RodadaReal] = []
    print("\n=== rodando WdoGridReloadMaker (F1, tick, capital real) ===", flush=True)
    rodadas.append(roda_wdo_grid_real(CAPITAL_WDO_BRL, MARGEM_WDO_BRL))
    print("=== rodando CopaWin (capital real) ===", flush=True)
    rodadas.append(roda_copa_real("WIN@", CAPITAL_WIN_BRL, MARGEM_WIN_BRL))
    print("=== rodando CopaWdo (capital real) ===", flush=True)
    rodadas.append(roda_copa_real("WDO@", CAPITAL_WDO_BRL, MARGEM_WDO_BRL))

    print("\n\n=== TABELA BASE (p=100%, capital real) ===")
    print(f"{'estrategia':<28}{'simbolo':<8}{'capital ini':>12}{'teto efetivo':>10}"
          f"{'entradas recusadas (capital)':>26}{'trades':>10}{'liquido':>16}{'maxdd':>14}")
    print("-" * 130)
    for r in rodadas:
        linha_base(r)

    print(f"\n=== REJEICAO i.i.d. p={num_br(P_ALVO*100,0)}% ({N_SEMENTES} sementes, sorteio por trade, "
          f"sem olhar o P&L) ===")
    print(f"{'estrategia':<28}{'simbolo':<8}{'capital ini':>12}{'capital final':>26}"
          f"{'lucro':>22}{'lucro/dia':>18}{'trades':>16}{'stops':>14}{'maxdd':>20}")
    print("-" * 156)
    for r in rodadas:
        stats = rejeicao_p_alvo(r)
        linha_p50(r, stats)
        print(f"    [diag] pregoes usados no denominador de lucro/dia = {stats['pregoes_base']}")


if __name__ == "__main__":
    main()
