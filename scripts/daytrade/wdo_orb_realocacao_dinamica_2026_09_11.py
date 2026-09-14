"""EXPERIMENTO (2026-09-11) -- realocacao dinamica de contratos na WdoOrb.

NAO TOCA EM PRODUCAO: `WdoOrbDinamico`, definida so' neste arquivo, e' uma
SUBCLASSE de `strategy.daytrade.lab.wdo_orb.WdoOrb` que acrescenta o MESMO
padrao `on_capital_update` + `contracts_from_capital_com_reserva` ja usado
(opt-in) em `CopaWin`/`WdoGridReloadMaker` (ver a memoria do projeto
`capital_dinamico_realocacao_2026_08_27`). `strategy/daytrade/lab/wdo_orb.py`
e `strategy/daytrade/registry.py` NAO sao editados nesta rodada.

## A pergunta (ordem do dono, 2026-09-11)

Prioridade #1 e' SEGURANCA. A ORB e' a unica candidata viva do projeto, mas
seu win% so' foi confirmado (IC95% acima do breakeven) DEPOIS do fade do
rompimento oposto, medido `2026-09-11` mesmo -- ver a docstring de
`WdoOrb`. Antes de cogitar MAIS capital em producao, a pergunta e' se
ESCALAR contratos conforme o caixa cresce (em vez de ficar travado em 1,
como hoje) AMPLIFICA a incerteza estatistica do proprio win%, em vez de so'
multiplicar um edge ja' solido (que era o caso do WDO F1 maker quando essa
mesma infra foi testada nele).

## O mecanismo que se espera medir (nao e' so' "mais risco de ruina")

`WdoOrb._ordem` pede sempre `quantity=1`. Com `limit_fill_capped_by_volume=
True` (padrao de teste do repo desde 2026-08-23), uma ordem-limite de N
contratos so' preenche se sobrar, na MESMA barra/tick, volume real >= N
DEPOIS da fila calibrada (`queue_ahead_qty`, 438 contratos no WDO@) ja ter
consumido o que vem antes -- `machine.py::_resolve_limit_fills`, FOK por
filho, sem preenchimento parcial. Ou seja: pedir 3 contratos em vez de 1 NAO
e' so' "3x o risco por trade" -- e' uma ordem estruturalmente MAIS DIFICIL
de encher, na MESMA fila real medida. Se a taxa de preenchimento cai
conforme o caixa cresce e a estrategia pede mais contrato, a amostra de
trades REALIZADOS fica MENOR (mais pregoes em branco), e o IC de Wilson do
win% fica MAIS LARGO -- a incerteza aumenta por CENSURA, nao por acaso.

## Diferenca do refutado (nao e' "tentar de nvo")

`capital_dinamico_realocacao_2026_08_27`: mesma infra testada em duas
estrategias, os DOIS com win% JA' solido antes de escalar (CopaWin ~ nulo
sign-flip favoravel; WdoGridReloadMaker F1 win% ~99%, depois anulado pela
fila real medida em 2026-09-09 -- ver `wdof1_familia_maker_encerrada_fila_
2026_09_10`). A ORB tem perfil estatistico DIFERENTE: win% ~57-68% por
perna, ainda perto do breakeven, IC apertado. Nenhum dos dois vereditos
anteriores (CopaWin quebra por falta de amortecimento; WDO F1 e' seguro mas
morre de fila depois) diz nada sobre o que acontece quando quem escala e' um
robo cujo proprio win% ainda depende de amostra.

## Metodo

1. Teste PEQUENO primeiro: ~15 pregoes (2026-02-27..2026-03-20, a fatia mais
   antiga do tick cache).
2. Se nao morrer trivialmente (0 trades, erro de sizing, etc.), expande para
   TODO o tick history disponivel em `data/raw_ticks/WDO_A_.parquet`
   (2026-02-27..2026-09-04, 130 pregoes -- mais que os 123 de IS+OOS ja'
   documentados na classe, porque o cache foi regerado depois).
3. Cada janela roda DUAS variantes, MESMOS dados/geometria/capital:
     a. ESTATICO -- `WdoOrb()` puro, `quantity=1` fixo (producao hoje).
     b. DINAMICO -- `WdoOrbDinamico(margin_per_contract_brl=150,
        hard_cap_contratos=5)` (5 = teto oficial do perfil WDO@).
   Capital REAL de partida: R$375,00 (margem R$150 x buffer 2,0 x reserva
   1,25 -- `strategy.daytrade.base`), nunca nocional (ordem do dono,
   `feedback_capital_inicial_nunca_arbitrario`).
4. `config_for` (`backtest.intraday.profiles`) monta a config exatamente
   como `scripts/run_live.py::build_intraday` -- fidelidade calibrada
   (438/489), deslize do alvo nativo (nao se aplica aqui, alvo e' maker
   fatiado), `anchor_exits_at_fill` herdado da estrategia. `enforce_capital_
   cap` fica default-on (perfil de futuro com margem conhecida) -- e' o
   MOTOR quem recusa entrada que a `contracts_from_capital_operacional`
   (2026-09-08) nao sustenta, exatamente como ao vivo.
5. Rejeicao i.i.d. p=50%, 30 sementes, MESMO metodo/formato de
   `capital_dinamico_rerun_2026_08_27.py` (sorteio POR TRADE sobre a
   sequencia de trades JA' realizados na rodada base p=100% -- nao rereoda o
   motor por semente).
6. Metricas reportadas para CADA variante/janela: liquido R$, win% com IC95%
   de Wilson contra o breakeven EMPIRICO (perda_media/(ganho_medio+
   perda_media)), trades, STOPS, MaxDD %, fracao de PREGOES positivos,
   capital real usado, pregoes SEM trade (censura), contratos min/max
   pedidos (evidencia de que a realocacao aconteceu), ordens recusadas por
   teto de capital.

Uso: `python -u scripts/daytrade/wdo_orb_realocacao_dinamica_2026_09_11.py`
     (roda so' a janela pequena; `WDO_ORB_JANELA=grande` roda a janela
     inteira em vez de/alem da pequena)
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402
from core.models import IntradayExitReason  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from strategy.daytrade.base import (  # noqa: E402
    EnterLimit,
    MARGIN_BUFFER_FUTUROS,
    RESERVA_CAIXA_SEGURANCA,
    contracts_from_capital_com_reserva,
)
from strategy.daytrade.lab.wdo_orb import EXIT_TTL_BARS_SEM_PRAZO, WdoOrb  # noqa: E402

SYMBOL = "WDO@"
MARGEM_WDO_BRL = 150.0
#: piso de PARTIDA oficial do WDO@ (CLAUDE.md): margem x buffer x reserva.
CAPITAL_REAL_BRL = MARGEM_WDO_BRL * MARGIN_BUFFER_FUTUROS * RESERVA_CAIXA_SEGURANCA  # 375,00
#: `(trade_tick_value, trade_tick_size)` do WDO@ -- mesmo par usado em todo
#: script deste repo que monta config para o simbolo (ver wdo_grid_reload_f1_lab.py).
_ECONOMIA_WDO = (0.01, 0.001)
TICK_PARQUET = ROOT / "data" / "raw_ticks" / "WDO_A_.parquet"

N_SEMENTES = 30
P_ALVO = 0.5


# ---------------------------------------------------------------------------
# 1. a estrategia EXPERIMENTAL -- nao mora em strategy/, nao e' producao.
# ---------------------------------------------------------------------------

@dataclass
class WdoOrbDinamico(WdoOrb):
    """`WdoOrb` + `on_capital_update`/`contracts_from_capital_com_reserva`,
    MESMO padrao opt-in de `CopaWin`/`WdoGridReloadMaker`
    (`margin_per_contract_brl=None` = comportamento IDENTICO ao pai, 1
    contrato fixo). So' existe neste script -- EXPERIMENTO, nao candidato a
    substituir `WdoOrb` em `strategy/daytrade/lab/`."""

    margin_per_contract_brl: float | None = None
    margin_buffer: float = MARGIN_BUFFER_FUTUROS
    #: teto OFICIAL do perfil (5 no WDO@) -- a realocacao nunca escala alem
    #: dele, mesmo com caixa de sobra.
    hard_cap_contratos: int | None = None
    #: Atualizado por `on_capital_update`, chamado pelo motor logo antes de
    #: cada `on_bar` -- mesmo padrao de `CopaWin._cash_atual_brl`.
    _cash_atual_brl: float = field(default=0.0, init=False, repr=False)

    def on_capital_update(self, cash_brl: float) -> None:
        self._cash_atual_brl = cash_brl

    @property
    def quantidade_dinamica(self) -> int:
        """`quantity` fixo quando `margin_per_contract_brl` e' `None`
        (default = comportamento do pai); senao
        `max(1, contracts_from_capital_com_reserva(caixa, margem, buffer,
        hard_cap))` -- piso de 1 contrato pelo MESMO motivo de
        `CopaWin.quantidade_por_entrada` (zero contratos nao e' "menor", e'
        nenhuma entrada)."""
        if self.margin_per_contract_brl is None:
            return self.quantity
        teto = contracts_from_capital_com_reserva(
            self._cash_atual_brl, self.margin_per_contract_brl,
            buffer=self.margin_buffer, hard_cap=self.hard_cap_contratos,
        )
        return max(1, teto)

    def _ordem(self, side, limite: float, stop_ticks: int, alvo_ticks: int,
               reason: str) -> EnterLimit:
        """IDENTICA a `WdoOrb._ordem`, so' trocando `self.quantity` fixo por
        `self.quantidade_dinamica` -- e' o UNICO ponto onde `quantity` e'
        lido em todo `WdoOrb.on_bar` (conferido por leitura direta do
        arquivo em 2026-09-11), entao sobrescrever so' este metodo basta
        para os dois caminhos de entrada (rompimento normal E fade)."""
        sinal = 1.0 if side == "long" else -1.0
        return EnterLimit(
            side=side,
            limit_price=limite,
            initial_stop=limite - sinal * stop_ticks * self.tick_size,
            initial_target=limite + sinal * alvo_ticks * self.tick_size,
            quantity=self.quantidade_dinamica,
            ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# 2. dado -- tick real do cache, sem MT5 ao vivo.
# ---------------------------------------------------------------------------

def carregar_bars(inicio: str, fim: str) -> pd.DataFrame:
    """Barras DEGENERADAS (1 tick = 1 barra, ver `ticks_to_degenerate_bars`)
    do WDO@ entre `[inicio, fim)`, filtradas NA LEITURA do parquet (a coluna
    `time` e' o indice original, mas continua sendo coluna fisica no
    arquivo -- filtro empurrado pro leitor evita materializar os 21,5
    milhoes de linhas do cache inteiro so' para descartar a maior parte)."""
    ticks = pd.read_parquet(
        TICK_PARQUET,
        columns=["last", "volume", "volume_real"],
        filters=[
            ("time", ">=", pd.Timestamp(inicio, tz="UTC")),
            ("time", "<", pd.Timestamp(fim, tz="UTC")),
        ],
    )
    # `kind="stable"` -- varios ticks podem cair no MESMO milissegundo (visto
    # no cache real); mergesort preserva a ordem de chegada original entre
    # eles em vez de embaralhar (quicksort, o default, nao garante isso).
    ticks = ticks.sort_index(kind="mergesort")
    return ticks_to_degenerate_bars(ticks)


# ---------------------------------------------------------------------------
# 3. rodar UMA variante.
# ---------------------------------------------------------------------------

def monta_config(strategy: WdoOrb, cash: float):
    profile = profile_for(SYMBOL)
    trade_tick_value, trade_tick_size = _ECONOMIA_WDO
    return config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        target_fills_as_maker=strategy.target_fills_as_maker,
        anchor_exits_at_fill=strategy.anchor_exits_at_fill,
        initial_capital=cash,
    )


@dataclass
class Rodada:
    rotulo: str
    bars: pd.DataFrame = field(repr=False)
    resultado: object
    dias_janela: int
    qtd_min: int
    qtd_max: int


def roda_estatico(bars: pd.DataFrame, cash: float) -> Rodada:
    strat = WdoOrb()
    cfg = monta_config(strat, cash)
    resultado = run_intraday_backtest(bars, strat, cfg)
    qtds = [t.quantity for t in resultado.trades]
    return Rodada("ESTATICO (qty=1 fixo)", bars, resultado,
                   len(set(bars.index.date)),
                   min(qtds, default=0), max(qtds, default=0))


def roda_dinamico(bars: pd.DataFrame, cash: float, hard_cap: int) -> Rodada:
    strat = WdoOrbDinamico(margin_per_contract_brl=MARGEM_WDO_BRL,
                            margin_buffer=MARGIN_BUFFER_FUTUROS,
                            hard_cap_contratos=hard_cap)
    cfg = monta_config(strat, cash)
    resultado = run_intraday_backtest(bars, strat, cfg)
    qtds = [t.quantity for t in resultado.trades]
    return Rodada("DINAMICO (on_capital_update)", bars, resultado,
                   len(set(bars.index.date)),
                   min(qtds, default=0), max(qtds, default=0))


# ---------------------------------------------------------------------------
# 4. estatistica -- Wilson (mesma formula de wdof1_regime_medio_prazo_2026_09_11.py)
#    + breakeven empirico + rejeicao i.i.d p=50%.
# ---------------------------------------------------------------------------

def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


def breakeven_empirico_pct(pnls: list[float]) -> float:
    """`perda_media / (ganho_medio + perda_media)`, em % -- o nulo CERTO
    quando o payoff realizado foge do nominal (item 6.22/6.23,
    LICOES_DE_PRODUCAO.md). `nan` sem vencedor ou sem perdedor (nao
    computavel)."""
    ganhos = [p for p in pnls if p > 0]
    perdas = [-p for p in pnls if p <= 0]
    if not ganhos or not perdas:
        return float("nan")
    ganho_medio = sum(ganhos) / len(ganhos)
    perda_media = sum(perdas) / len(perdas)
    return 100.0 * perda_media / (ganho_medio + perda_media)


def _pnl_por_pregao(trades) -> dict:
    por_dia: dict = {}
    for t in trades:
        dia = pd.Timestamp(t.exit_ts).date()
        por_dia[dia] = por_dia.get(dia, 0.0) + t.pnl_brl
    return por_dia


def rejeicao_p_alvo(rodada: Rodada, cash: float, p: float = P_ALVO,
                     n_sementes: int = N_SEMENTES, seed_base: int = 0) -> dict:
    """MESMO metodo de `capital_dinamico_rerun_2026_08_27.py::rejeicao_p_
    alvo`: sorteio i.i.d POR TRADE sobre a sequencia JA REALIZADA na rodada
    base (p=100%) -- nao rereoda o motor por semente."""
    trades = list(rodada.resultado.trades)
    n = len(trades)

    capital_final = np.empty(n_sementes)
    lucro = np.empty(n_sementes)
    n_trades = np.empty(n_sementes)
    n_stops = np.empty(n_sementes)
    maxdd = np.empty(n_sementes)
    win_pct = np.empty(n_sementes)
    zerou = np.zeros(n_sementes, dtype=bool)

    for s in range(n_sementes):
        rng = np.random.default_rng(seed_base + s)
        aceita = rng.random(n) < p if n else np.array([], dtype=bool)
        aceitos = [t for t, a in zip(trades, aceita) if a]
        pnls = [t.pnl_brl for t in aceitos]
        liquido_s = float(sum(pnls))

        lucro[s] = liquido_s
        capital_final[s] = cash + liquido_s
        n_trades[s] = len(aceitos)
        n_stops[s] = sum(1 for t in aceitos if t.exit_reason == IntradayExitReason.STOP)
        vencedores = sum(1 for pnl in pnls if pnl > 0)
        win_pct[s] = (100.0 * vencedores / len(pnls)) if pnls else float("nan")

        curva = [cash]
        acc = cash
        for pnl in pnls:
            acc += pnl
            curva.append(acc)
        maxdd[s] = maxdd_brl(pd.Series(curva))
        zerou[s] = any(v <= 0 for v in curva)

    return dict(capital_final=capital_final, lucro=lucro, trades=n_trades,
                stops=n_stops, maxdd=maxdd, win_pct=win_pct, zerou=zerou)


def _media_desvio(arr: np.ndarray) -> str:
    validos = arr[~np.isnan(arr)] if np.issubdtype(arr.dtype, np.floating) else arr
    if len(validos) == 0:
        return "—"
    media = float(np.mean(validos))
    desvio = float(np.std(validos, ddof=1)) if len(validos) > 1 else 0.0
    return f"{num_br(media)} +/- {num_br(desvio)}"


# ---------------------------------------------------------------------------
# 5. relatorio de UMA janela -- as DUAS variantes lado a lado.
# ---------------------------------------------------------------------------

def relatorio_janela(nome_janela: str, bars: pd.DataFrame, cash: float) -> None:
    perfil = profile_for(SYMBOL)
    hard_cap = perfil.max_open_contracts  # 5, teto oficial WDO@

    print(f"\n{'=' * 100}\nJANELA {nome_janela}: {len(set(bars.index.date))} pregoes "
          f"({bars.index.min()} -> {bars.index.max()}), {len(bars)} ticks, "
          f"capital real R${num_br(cash, 2)}\n{'=' * 100}", flush=True)

    print("  rodando ESTATICO...", flush=True)
    r_estatico = roda_estatico(bars, cash)
    print("  rodando DINAMICO...", flush=True)
    r_dinamico = roda_dinamico(bars, cash, hard_cap)

    print(f"\n--- BASE (p=100%), janela {nome_janela} ---")
    cab = (f"{'variante':<30}{'trades':>8}{'stops':>8}{'win%':>9}"
           f"{'BE emp%':>10}{'IC95 win%':>22}{'liquido R$':>16}{'MaxDD R$':>12}"
           f"{'MaxDD %':>10}{'qty min/max':>14}{'s/trade':>10}{'recus.teto':>12}")
    print(cab)
    print("-" * len(cab))
    linhas_base = []
    for r in (r_estatico, r_dinamico):
        trades = list(r.resultado.trades)
        pnls = [t.pnl_brl for t in trades]
        liquido = sum(pnls)
        vencedores = sum(1 for p in pnls if p > 0)
        n_trades = len(trades)
        n_stops = sum(1 for t in trades if t.exit_reason == IntradayExitReason.STOP)
        win = (100.0 * vencedores / n_trades) if n_trades else float("nan")
        be = breakeven_empirico_pct(pnls)
        ic_lo, ic_hi = ic_wilson(vencedores, n_trades) if n_trades else (float("nan"),) * 2
        dd_brl = maxdd_brl(r.resultado.equity_curve)
        dd_pct = 100.0 * dd_brl / cash if cash else float("nan")
        dias_com_trade = {pd.Timestamp(t.exit_ts).date() for t in trades}
        sem_trade = r.dias_janela - len(dias_com_trade)
        total_ordens = r.resultado.ordens_aceitas + r.resultado.ordens_recusadas_por_teto
        recus_pct = (100.0 * r.resultado.ordens_recusadas_por_teto / total_ordens
                     if total_ordens else 0.0)
        zerado = " ZERADO" if r.resultado.wiped_out_at is not None else ""
        print(f"{r.rotulo:<30}{n_trades:>8}{n_stops:>8}{num_br(win,1)+'%':>9}"
              f"{num_br(be,1)+'%':>10}{('['+num_br(ic_lo,1)+';'+num_br(ic_hi,1)+']'):>22}"
              f"{num_br(liquido):>16}{num_br(dd_brl):>12}{num_br(dd_pct,1)+'%':>10}"
              f"{(str(r.qtd_min)+'/'+str(r.qtd_max)):>14}{sem_trade:>10}"
              f"{num_br(recus_pct,1)+'%':>12}{zerado}")
        linhas_base.append(dict(rotulo=r.rotulo, win=win, ic=(ic_lo, ic_hi), be=be,
                                 n_trades=n_trades, liquido=liquido, dd_pct=dd_pct,
                                 sem_trade=sem_trade))

        # fracao de PREGOES positivos (so' entre os que tiveram trade -- um
        # pregao sem trade nao e' "positivo" nem "negativo", e' censura).
        por_dia = _pnl_por_pregao(trades)
        if por_dia:
            positivos = sum(1 for v in por_dia.values() if v > 0)
            frac_pos = 100.0 * positivos / len(por_dia)
        else:
            frac_pos = float("nan")
        print(f"    [diag] pregoes com trade positivos: {num_br(frac_pos,1)}% "
              f"({sum(1 for v in por_dia.values() if v > 0)}/{len(por_dia)}) | "
              f"ordens aceitas={r.resultado.ordens_aceitas} "
              f"recusadas_por_teto={r.resultado.ordens_recusadas_por_teto}", flush=True)

    largura_ic_estatico = linhas_base[0]["ic"][1] - linhas_base[0]["ic"][0]
    largura_ic_dinamico = linhas_base[1]["ic"][1] - linhas_base[1]["ic"][0]
    print(f"\n  [leitura] largura do IC95% do win%: estatico={num_br(largura_ic_estatico,1)}pp "
          f"vs dinamico={num_br(largura_ic_dinamico,1)}pp "
          f"({'AMPLIFICOU' if largura_ic_dinamico > largura_ic_estatico + 0.5 else 'nao amplificou de forma clara'})")

    print(f"\n--- REJEICAO i.i.d. p={num_br(P_ALVO*100,0)}% ({N_SEMENTES} sementes), "
          f"janela {nome_janela} ---")
    cab2 = (f"{'variante':<30}{'capital final':>26}{'lucro':>22}{'trades':>16}"
            f"{'stops':>14}{'win%':>16}{'maxdd':>20}{'zerou':>10}")
    print(cab2)
    print("-" * len(cab2))
    for r in (r_estatico, r_dinamico):
        stats = rejeicao_p_alvo(r, cash)
        n_zerou = int(stats["zerou"].sum())
        print(f"{r.rotulo:<30}{_media_desvio(stats['capital_final']):>26}"
              f"{_media_desvio(stats['lucro']):>22}{_media_desvio(stats['trades']):>16}"
              f"{_media_desvio(stats['stops']):>14}{_media_desvio(stats['win_pct']):>16}"
              f"{_media_desvio(stats['maxdd']):>20}{n_zerou:>6}/{N_SEMENTES}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"[wdo_orb_realocacao_dinamica] CAPITAL_REAL_BRL=R${num_br(CAPITAL_REAL_BRL,2)} "
          f"(margem R${num_br(MARGEM_WDO_BRL,0)} x buffer {MARGIN_BUFFER_FUTUROS} x "
          f"reserva {RESERVA_CAIXA_SEGURANCA})")

    print("\n[wdo_orb_realocacao_dinamica] carregando janela PEQUENA "
          "(2026-02-27..2026-03-20)...", flush=True)
    bars_pequena = carregar_bars("2026-02-27", "2026-03-21")
    relatorio_janela("PEQUENA (~15 pregoes)", bars_pequena, CAPITAL_REAL_BRL)

    if os.environ.get("WDO_ORB_JANELA", "").strip().lower() == "grande":
        print("\n[wdo_orb_realocacao_dinamica] carregando janela GRANDE "
              "(2026-02-27..2026-09-04, todo o tick history disponivel)...", flush=True)
        bars_grande = carregar_bars("2026-02-27", "2026-09-05")
        relatorio_janela("GRANDE (todo o tick history, ~130 pregoes)", bars_grande,
                          CAPITAL_REAL_BRL)


if __name__ == "__main__":
    main()
