"""Rerun com REALOCACAO DINAMICA por capital (2026-08-27) -- `CopaWin` (WIN@)
e `WdoGridReloadMaker` F1 tick (WDO@), os DOIS unicos candidatos vivos que
sobreviveram ao portao de capital real (ver `daytrade_capital_real_gate_2026_
08_27`).

Pergunta do dono: a realocacao dinamica por capital (`margin_per_contract_brl`,
implementada nesta rodada em `CopaWin`/`WdoGridReloadMaker`) produz evolucao de
PATRIMONIO SEGURA -- ganha mais SEM aumentar desproporcionalmente o risco de
zerar a conta --, nos mesmos moldes de `Gremah`? Nao e' so' pergunta de
retorno esperado, e' pergunta de RISCO DE RUINA.

MODELO de metodologia (funcoes `rejeicao_p_alvo`/`_media_desvio`, formato de
tabela): `scripts/daytrade/capital_real_rerun_2026_08_27.py`. Aquele script
esta QUEBRADO -- ainda importa/chama `CopaWdo`, removido do repo em
2026-08-27 (`roda_copa_real("WDO@", ...)` levanta `ValueError` no despachante
`Copa`, que so' tem `CopaWin` registrado) -- e NAO e' rodado aqui, so'
copiado/adaptado. Este script cobre so' os 2 candidatos vivos:

  - `CopaWin` em WIN@, capital inicial R$200, margem R$100.
  - `WdoGridReloadMaker` (F1, tick) em WDO@, capital inicial R$300, margem
    R$150.

Para CADA um, DUAS variantes na MESMA janela IN-SAMPLE (`copa_lab.barras
(symbol).in_sample()` / `wdo_grid_reload_f1_tick_lab.carregar_tick_bars()` --
o trecho OOS, >= 2026-06-13, ja' foi GASTO e continua CONGELADO por regra do
repo; nenhuma linha deste arquivo toca nele):

  1. ESTATICO (baseline) -- reproduz EXATAMENTE a logica de
     `capital_real_rerun_2026_08_27.py::roda_copa_real`/`roda_wdo_grid_real`:
     teto de contratos FIXO, calculado 1x por `contracts_from_capital`, sem
     os parametros novos (`margin_per_contract_brl=None`). Os numeros tem
     que BATER com os ja registrados na memoria do dono (2026-08-27) -- se
     nao bater, e' sinal de que algo mudou no dado/ambiente desde entao, ou
     que esta reproducao esta errada, e vale investigar antes de confiar no
     lado dinamico.
  2. DINAMICO (novo) -- MESMOS dados/janela/capital inicial/margem, mas com
     `margin_per_contract_brl` ativando a realocacao E `config.
     max_open_contracts` trocado para o teto OFICIAL do perfil (15 WIN@, 5
     WDO@) -- ARMADILHA DE ENGINE explicada na missao desta rodada: se a
     ESTRATEGIA pede mais contratos conforme o caixa cresce mas
     `max_open_contracts` do motor continua congelado no teto pequeno
     inicial, o motor recusa a ordem em SILENCIO
     (`ordens_recusadas_por_teto`) e a realocacao nunca aparece no
     resultado. A tabela base abaixo reporta essa coluna explicitamente
     para o dinamico nunca escapar sem checagem.

Rejeicao i.i.d. p=50%/30 sementes, MESMO codigo/parametros do script de
referencia, aplicada as DUAS variantes de cada estrategia -- mais, por
rodada: teto de contratos MINIMO e MAXIMO atingido ao longo do periodo
(evidencia de que a realocacao aconteceu de fato -- lido direto de
`IntradayTrade.quantity` de cada trade da rodada BASE, p=100%, que e' a
MESMA sequencia de trades da qual toda semente da rejeicao subamostra) e
quantas das 30 sementes ZERARAM a conta.

"Zerou" na rejeicao e' calculado POS-HOC (a i.i.d. so' subamostra o
P&L de uma UNICA rodada-base, nunca reroda o motor por semente -- mesma
tecnica do script de referencia): a curva sintetica de cada semente
(`capital_inicial`, depois um degrau por trade ACEITO, na ORDEM cronologica
original) e' inspecionada ponto a ponto; se ela toca <=0 em algum grau,
a semente conta como zerada. E' o mesmo criterio do freio incondicional do
motor (`backtest/intraday/engine.py`: `if equity_atual <= 0: wiped_out_at =
ts; break`), so' que aplicado sobre a subamostra em vez de re-rodar o motor
inteiro 30 vezes (caro, principalmente no lado tick do WDO). A linha BASE
(p=100%) reporta tambem o `wiped_out_at` DE VERDADE, calculado pelo motor.

Uso: `python -u scripts/daytrade/capital_dinamico_rerun_2026_08_27.py`
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
# capital real -- MESMOS numeros de `capital_real_rerun_2026_08_27.py`,
# confirmados pelo dono 2026-08-27 (margem real de day trade em
# mini-contrato, corretoras BR, valores promocionais).
# ---------------------------------------------------------------------------
MARGEM_WIN_BRL = 100.0
MARGEM_WDO_BRL = 150.0
CAPITAL_WIN_BRL = MARGEM_WIN_BRL * MARGIN_BUFFER_FUTUROS   # R$200
CAPITAL_WDO_BRL = MARGEM_WDO_BRL * MARGIN_BUFFER_FUTUROS   # R$300

N_SEMENTES = 30
P_ALVO = 0.5


@dataclasses.dataclass
class RodadaCapital:
    rotulo: str
    symbol: str
    initial_capital: float
    resultado: object
    pregoes_janela: int              # pregoes no INPUT (bars), antes de qualquer wipeout
    teto_contratos_min: int          # min(IntradayTrade.quantity) na rodada BASE (p=100%)
    teto_contratos_max: int          # max(IntradayTrade.quantity) na rodada BASE (p=100%)


def _teto_min_max(trades) -> tuple[int, int]:
    """`quantity` de cada trade JA FECHADO -- evidencia direta de quanto a
    estrategia realmente pediu em cada entrada (nao uma leitura indireta do
    teto configurado). Na variante ESTATICA os dois numeros sao IGUAIS (o
    teto e' constante do inicio ao fim); na DINAMICA, diferentes = a
    realocacao aconteceu de fato."""
    qtds = [t.quantity for t in trades]
    if not qtds:
        return (0, 0)
    return (min(qtds), max(qtds))


# ---------------------------------------------------------------------------
# ESTATICO -- reproduz `capital_real_rerun_2026_08_27.py::roda_copa_real` /
# `roda_wdo_grid_real`, byte-a-byte (sem os parametros novos).
# ---------------------------------------------------------------------------

def roda_copa_estatico(cash: float, margin: float) -> RodadaCapital:
    symbol = "WIN@"
    perfil = profile_for(symbol)
    teto = contracts_from_capital(cash, margin, hard_cap=perfil.max_open_contracts)
    params = dict(CALIBRACAO_IS[symbol])
    bars = L.barras(symbol).in_sample()
    pregoes_janela = len(set(bars.index.date))
    if teto < 1:
        raise SystemExit(
            f"[capital_dinamico] {symbol} estatico: contracts_from_capital devolveu {teto} -- "
            f"R${num_br(cash)} nao sustenta nem 1 contrato a R${num_br(margin)} de margem."
        )
    instancia = L.robo(symbol, teto, **params)
    cfg_nocional = L.config(symbol, teto, pernas_maker=int(getattr(instancia, "pernas_maker", 1)))
    cfg = dataclasses.replace(cfg_nocional, initial_capital=cash)
    resultado = run_intraday_backtest(bars, instancia, cfg)
    tmin, tmax = _teto_min_max(resultado.trades)
    return RodadaCapital(rotulo="CopaWin (estatico)", symbol=symbol, initial_capital=cash,
                          resultado=resultado, pregoes_janela=pregoes_janela,
                          teto_contratos_min=tmin, teto_contratos_max=tmax)


def roda_wdo_grid_estatico(cash: float, margin: float) -> RodadaCapital:
    symbol = "WDO@"
    perfil = profile_for(symbol)
    teto = contracts_from_capital(cash, margin, hard_cap=perfil.max_open_contracts)
    dias, tick_bars = GT.carregar_tick_bars()
    pregoes_janela = len(dias)
    if teto < 1:
        raise SystemExit(
            f"[capital_dinamico] wdo_grid estatico: contracts_from_capital devolveu {teto} -- "
            f"R${num_br(cash)} nao sustenta nem 1 contrato."
        )
    cfg_nocional: IntradayBacktestConfig = G.montar_config()
    # `G.MAX_OPEN_CONTRATOS=1` ja' e' o teto NATURAL da mecanica de reload --
    # checa que bate com o teto por CAPITAL antes de so' confiar no numero antigo
    # (mesma checagem do script de referencia).
    if teto != cfg_nocional.max_open_contracts:
        cfg_nocional = dataclasses.replace(cfg_nocional, max_open_contracts=teto)
    cfg = dataclasses.replace(cfg_nocional, initial_capital=cash)
    resultado = G.rodar(tick_bars, cfg)
    tmin, tmax = _teto_min_max(resultado.trades)
    return RodadaCapital(rotulo="WdoGridReloadMaker F1 tick (estatico)", symbol=symbol,
                          initial_capital=cash, resultado=resultado, pregoes_janela=pregoes_janela,
                          teto_contratos_min=tmin, teto_contratos_max=tmax)


# ---------------------------------------------------------------------------
# DINAMICO -- ativa `margin_per_contract_brl` E troca `max_open_contracts`
# do MOTOR para o teto OFICIAL do perfil (a estrategia e' quem se autolimita
# pelo capital real; o motor so' garante que ela nunca ultrapasse o
# regulamento -- ver a docstring do modulo, secao "armadilha de engine").
# ---------------------------------------------------------------------------

def roda_copa_dinamico(cash: float, margin: float) -> RodadaCapital:
    symbol = "WIN@"
    perfil = profile_for(symbol)
    teto_oficial = perfil.max_open_contracts  # 15
    params = dict(CALIBRACAO_IS[symbol])
    bars = L.barras(symbol).in_sample()
    pregoes_janela = len(set(bars.index.date))
    instancia = L.robo(symbol, teto_oficial, margin_per_contract_brl=margin,
                        margin_buffer=MARGIN_BUFFER_FUTUROS, **params)
    # `L.config(symbol, teto_oficial, ...)` ja' seta `max_open_contracts=
    # teto_oficial` -- e' exatamente a troca que a armadilha de engine pede,
    # so' que alcancada passando `teto_oficial` (em vez do teto de teste
    # pequeno) para a MESMA montagem compartilhada usada pelo estatico.
    cfg_nocional = L.config(symbol, teto_oficial, pernas_maker=int(getattr(instancia, "pernas_maker", 1)))
    cfg = dataclasses.replace(cfg_nocional, initial_capital=cash)
    resultado = run_intraday_backtest(bars, instancia, cfg)
    tmin, tmax = _teto_min_max(resultado.trades)
    return RodadaCapital(rotulo="CopaWin (dinamico)", symbol=symbol, initial_capital=cash,
                          resultado=resultado, pregoes_janela=pregoes_janela,
                          teto_contratos_min=tmin, teto_contratos_max=tmax)


def roda_wdo_grid_dinamico(cash: float, margin: float) -> RodadaCapital:
    symbol = "WDO@"
    perfil = profile_for(symbol)
    hard_cap = perfil.max_open_contracts  # 5
    dias, tick_bars = GT.carregar_tick_bars()
    pregoes_janela = len(dias)
    cfg_nocional: IntradayBacktestConfig = G.montar_config()
    cfg = dataclasses.replace(cfg_nocional, initial_capital=cash, max_open_contracts=hard_cap)
    resultado = G.rodar(tick_bars, cfg, margin_per_contract_brl=margin,
                         margin_buffer=MARGIN_BUFFER_FUTUROS, hard_cap_contratos=hard_cap)
    tmin, tmax = _teto_min_max(resultado.trades)
    return RodadaCapital(rotulo="WdoGridReloadMaker F1 tick (dinamico)", symbol=symbol,
                          initial_capital=cash, resultado=resultado, pregoes_janela=pregoes_janela,
                          teto_contratos_min=tmin, teto_contratos_max=tmax)


# ---------------------------------------------------------------------------
# rejeicao i.i.d. p=50%, com MaxDD reconstruido cronologicamente por semente
# (MESMA funcao de `capital_real_rerun_2026_08_27.py::rejeicao_p_alvo`,
# so' com o rastreio de "zerou" adicionado).
# ---------------------------------------------------------------------------

def rejeicao_p_alvo(rodada: RodadaCapital, p: float = P_ALVO, n_sementes: int = N_SEMENTES,
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
    zerou = np.zeros(n_sementes, dtype=bool)

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
        # fechamento) a partir do NOVO `initial_capital` -- mesma tecnica do
        # script de referencia. "Zerou" (novo aqui): a MESMA curva tocando
        # <=0 em algum degrau, o criterio POS-HOC equivalente ao freio
        # incondicional do motor (ver docstring do modulo).
        curva = [rodada.initial_capital]
        acc = rodada.initial_capital
        for pnl in pnls:
            acc += pnl
            curva.append(acc)
        maxdd[s] = maxdd_brl(pd.Series(curva))
        zerou[s] = any(v <= 0 for v in curva)

    return dict(
        pregoes_base=pregoes_base,
        capital_final=capital_final, lucro=lucro, lucro_dia=lucro_dia,
        trades=n_trades, stops=n_stops, maxdd=maxdd, zerou=zerou,
    )


def _media_desvio(arr: np.ndarray) -> str:
    return f"{num_br(float(arr.mean()))} +/- {num_br(float(arr.std(ddof=1)) if len(arr) > 1 else 0.0)}"


# ---------------------------------------------------------------------------
# relatorio -- tabela CRUA, sem veredito embutido (o dono julga os numeros).
# ---------------------------------------------------------------------------

def linha_base(r: RodadaCapital) -> None:
    res = r.resultado
    trades = list(res.trades)
    liquido = sum(t.pnl_brl for t in trades)
    dd = maxdd_brl(res.equity_curve)
    total_ordens = res.ordens_aceitas + res.ordens_recusadas_por_teto
    recusas_pct = (100.0 * res.ordens_recusadas_por_teto / total_ordens) if total_ordens else 0.0
    pregoes_rodados = len(set(pd.DatetimeIndex(res.equity_curve.index).date)) \
        if res.equity_curve is not None and not res.equity_curve.empty else 0
    zerou = " ZERADO" if getattr(res, "wiped_out_at", None) is not None else ""
    print(f"{r.rotulo:<34}{r.symbol:<8}{('R$'+num_br(r.initial_capital,0)):>12}"
          f"{r.teto_contratos_min:>10}{r.teto_contratos_max:>10}"
          f"{res.ordens_recusadas_por_teto:>18}{len(trades):>10}"
          f"{('R$'+num_br(liquido)):>16}{('R$'+num_br(dd)):>14}{zerou}")
    print(f"    [diag] ordens aceitas={res.ordens_aceitas} recusadas={res.ordens_recusadas_por_teto} "
          f"({num_br(recusas_pct,1)}%) | pregoes na janela={r.pregoes_janela} | "
          f"pregoes realmente simulados={pregoes_rodados}"
          + (f" | wiped_out_at={res.wiped_out_at}" if getattr(res, 'wiped_out_at', None) is not None else ""))


def linha_p50(r: RodadaCapital, stats: dict) -> None:
    n_zerou = int(stats["zerou"].sum())
    print(f"{r.rotulo:<34}{r.symbol:<8}{('R$'+num_br(r.initial_capital,0)):>12}"
          f"{_media_desvio(stats['capital_final']):>26}{_media_desvio(stats['lucro']):>22}"
          f"{_media_desvio(stats['lucro_dia']):>18}{_media_desvio(stats['trades']):>16}"
          f"{_media_desvio(stats['stops']):>14}{_media_desvio(stats['maxdd']):>20}"
          f"{n_zerou:>10}/{len(stats['zerou'])}")


def main() -> None:
    print(f"[capital_dinamico] MARGIN_BUFFER_FUTUROS={MARGIN_BUFFER_FUTUROS} | "
          f"WIN@ margem=R${num_br(MARGEM_WIN_BRL,0)} -> capital=R${num_br(CAPITAL_WIN_BRL,0)} | "
          f"WDO@ margem=R${num_br(MARGEM_WDO_BRL,0)} -> capital=R${num_br(CAPITAL_WDO_BRL,0)}")

    rodadas: list[RodadaCapital] = []

    print("\n=== ESTATICO: rodando CopaWin (WIN@) ===", flush=True)
    r = roda_copa_estatico(CAPITAL_WIN_BRL, MARGEM_WIN_BRL)
    rodadas.append(r)
    linha_base(r)

    print("\n=== ESTATICO: rodando WdoGridReloadMaker F1 tick (WDO@) ===", flush=True)
    r = roda_wdo_grid_estatico(CAPITAL_WDO_BRL, MARGEM_WDO_BRL)
    rodadas.append(r)
    linha_base(r)

    print("\n=== DINAMICO: rodando CopaWin (WIN@) ===", flush=True)
    r = roda_copa_dinamico(CAPITAL_WIN_BRL, MARGEM_WIN_BRL)
    rodadas.append(r)
    linha_base(r)

    print("\n=== DINAMICO: rodando WdoGridReloadMaker F1 tick (WDO@) ===", flush=True)
    r = roda_wdo_grid_dinamico(CAPITAL_WDO_BRL, MARGEM_WDO_BRL)
    rodadas.append(r)
    linha_base(r)

    print("\n\n=== TABELA BASE (p=100%) -- estatico vs dinamico ===")
    print(f"{'estrategia':<34}{'simbolo':<8}{'capital ini':>12}{'teto min':>10}{'teto max':>10}"
          f"{'recusadas (teto)':>18}{'trades':>10}{'liquido':>16}{'maxdd':>14}")
    print("-" * 140)
    for r in rodadas:
        linha_base(r)

    print(f"\n=== REJEICAO i.i.d. p={num_br(P_ALVO*100,0)}% ({N_SEMENTES} sementes, sorteio por trade, "
          f"sem olhar o P&L) -- estatico vs dinamico ===")
    print(f"{'estrategia':<34}{'simbolo':<8}{'capital ini':>12}{'capital final':>26}"
          f"{'lucro':>22}{'lucro/dia':>18}{'trades':>16}{'stops':>14}{'maxdd':>20}{'zerou':>10}")
    print("-" * 190)
    for r in rodadas:
        stats = rejeicao_p_alvo(r)
        linha_p50(r, stats)
        print(f"    [diag] pregoes usados no denominador de lucro/dia = {stats['pregoes_base']}", flush=True)


if __name__ == "__main__":
    main()
