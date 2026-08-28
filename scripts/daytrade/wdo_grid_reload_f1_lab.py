"""Frente F1-wdo-consolidacao -- laboratorio de consolidacao do candidato
"T1 S16 x1" (`strategy.daytrade.lab.wdo_grid_reload_maker.WdoGridReloadMaker`)
em WDO@. Roda:

  1. checagem de sanidade -- reproduz (ou nao) o numero IS ja conhecido
     (+R$37.606,53, atrito zero de fila, 123 pregoes).
  2. teste de metade dentro do IS.
  3. nulo por sign-flip (formula correta: `bruto_d`/`custo_d` separados,
     nunca inverte o liquido inteiro), 5+ sementes, percentil.
  4. curva de sensibilidade a pedagio de fila (0..0,5 tick/perna maker).
  5. tabela padrao (`backtest.intraday.report`).

NAO destrava o trecho OOS (`LockedBars.out_of_sample()` nunca e chamado) --
ver a disciplina de teste da missao desta rodada. So' o trecho IN-SAMPLE
(< `profile_for("WDO@").frozen_cutoff` = 2026-06-13) e' usado em QUALQUER
lugar deste arquivo.

Mora em `scripts/` (nao em `backtest/`) pela MESMA regra de fronteira que
justifica `copa_lab.py` estar aqui: precisa importar `backtest` E
`strategy` ao mesmo tempo (AGENTS.md #1, `strategy/` so' importa `core`).
NAO importa `copa_lab.py` de proposito -- aquele modulo e' especifico da
familia `copa` (score por bloco de fase/bateria, que nao existe mais para
este objetivo); a montagem de dado/config aqui e' equivalente mas PROPRIA,
para as duas frentes nao colidirem rodando em paralelo.

Uso: `python scripts/daytrade/wdo_grid_reload_f1_lab.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.costs import IntradayCostModel  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig, IntradayTrade  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import (  # noqa: E402
    LinhaResultado,
    cabecalho,
    linha,
    linha_de_resultado,
    num_br,
)
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker  # noqa: E402

SYMBOL = "WDO@"

#: Linha de base NOCIONAL da curva de patrimonio -- futuro nao tem saldo
#: real neste teste (o limitador e' `max_open_contracts`, nao caixa: ver
#: `config_for(..., enforce_capital_minimo=False)`, que e' o default para
#: todo perfil com `max_open_contracts` declarado). Grande o bastante para
#: a conta nunca "quebrar" (equity <= 0) mesmo empilhando perdas -- so'
#: existe para a curva ter uma base.
CAPITAL_NOCIONAL = 1_000_000.0

#: 1 CONTRATO -- a restricao real do dono nesta rodada (ver o cabecalho da
#: missao). A propria estrategia nunca pede mais de 1 posicao por vez
#: (mecanica de reload: so' rearma depois do fechamento anterior), entao
#: este teto so' formaliza o que ja seria verdade sem ele.
MAX_OPEN_CONTRATOS = 1

#: Minimo de barras M1 para uma sessao contar (mesmo numero de
#: `scripts/daytrade/copa_lab.py`, mesmo motivo: o perfil documenta ~570
#: barras/pregao tipicas para o WDO@; um pregao pela metade (feriado
#: parcial, feed cortado) nao e' um pregao e distorce qualquer media por
#: dia).
MIN_BARRAS_POR_PREGAO = 400

#: Economia conhecida (trade_tick_value, trade_tick_size) da serie
#: CONTINUA, mesmo fallback documentado em `copa_lab.py` -- point_value_brl
#: = 0,01/0,001 = R$10,00/ponto, preservado por `config_for` ao trocar a
#: grade de preco pelo `price_tick_size` real do perfil (0,5).
_ECONOMIA_WDO = (0.01, 0.001)

#: Candidato consolidado desta frente: alvo 1 tick, stop 16 ticks, nivel a
#: 1 tick (x1) da abertura -- ver `WdoGridReloadMaker` para a mecanica.
CANDIDATO_PARAMS = dict(level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)

#: Numero-alvo da checagem de sanidade (medicao anterior, fora deste
#: repo -- ver o cabecalho da missao desta rodada).
BALLPARK_IS_LIQUIDO_BRL = 37_606.53


def carregar_barras() -> LockedBars:
    """Barras M1 do WDO@ dentro do split CONGELADO do perfil -- so'
    `.in_sample()` e chamado neste arquivo inteiro."""
    df = load_m1(SYMBOL)
    if df.empty:
        raise SystemExit(
            f"[wdo_grid_reload_f1] sem dado M1 salvo para {SYMBOL!r} -- rode "
            f"`scripts/daytrade/backfill_m1.py --symbol {SYMBOL}` primeiro."
        )
    profile = profile_for(SYMBOL)
    df = df.sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    df = df[[d in completos for d in df.index.date]]
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    return LockedBars(df, split)


def montar_config(pedagio_ticks: float = 0.0, com_custo: bool = True,
                   limit_fill_capped_by_volume: bool = True,
                   slippage_ticks: float | None = None,
                   pernas_maker: int = 2) -> IntradayBacktestConfig:
    """Config do motor para o WDO@, com o TETO desta frente (1 contrato).

    `com_custo=False` zera tarifa E slippage -- so' para comparacao bruta,
    nunca o numero reportado como resultado (disciplina de teste #2).

    `limit_fill_capped_by_volume`: `True` (default, PADRAO DE TESTE do
    repo desde 2026-08-23, ver `config_for`) exige volume real >= a
    quantidade pedida para uma ordem parada preencher -- sem isto o
    percentual de acerto medido superestima a realidade. A checagem de
    sanidade (item 1) roda os DOIS valores lado a lado, porque a medicao
    anterior ("atrito zero de fila") pode ter usado qualquer um dos dois.

    `slippage_ticks`: `None` (default) preserva o slippage PADRAO do perfil
    (1 tick, so' cobrado nas saidas a MERCADO -- stop e flatten forcado,
    nunca entrada/alvo maker). A checagem de sanidade (item 1) tambem testa
    `0.0` explicito: "atrito zero de fila (so' tarifa R$0,50/contrato/
    round-trip)" (texto da missao) pode ter significado ZERO slippage em
    TODA saida, nao so' zero pedagio de fila -- as duas leituras sao
    testadas lado a lado em vez de escolhida uma.

    `pedagio_ticks` (item 4, sensibilidade a fila): pedagio artificial de N
    ticks por perna MAKER, somado a tarifa -- mesmo padrao de
    `copa_lab.py::config()`. `pernas_maker=2` (entrada + alvo, as DUAS
    maker neste robo) e' aplicado a TODO round-trip, inclusive o que fecha
    por STOP (so' 1 perna maker de verdade, a entrada) -- overcounting
    deliberado e CONSERVADOR: superestimar custo nunca infla lucro."""
    profile = profile_for(SYMBOL)
    trade_tick_value, trade_tick_size = _ECONOMIA_WDO
    cfg = config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=CAPITAL_NOCIONAL,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=limit_fill_capped_by_volume,
        max_open_contracts=MAX_OPEN_CONTRATOS,
    )
    custos = cfg.costs
    if not com_custo:
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=0.0, slippage_ticks=0.0, exchange_fee_pct_per_leg=0.0,
        )
    elif slippage_ticks is not None:
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=custos.fee_round_trip_brl, slippage_ticks=slippage_ticks,
            exchange_fee_pct_per_leg=custos.exchange_fee_pct_per_leg,
        )
    if pedagio_ticks:
        extra = pedagio_ticks * custos.tick_size * custos.point_value_brl * pernas_maker
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=custos.fee_round_trip_brl + extra,
            slippage_ticks=custos.slippage_ticks,
            exchange_fee_pct_per_leg=custos.exchange_fee_pct_per_leg,
        )
    return IntradayBacktestConfig(
        costs=custos,
        initial_capital=cfg.initial_capital,
        default_quantity=cfg.default_quantity,
        session_end_time=cfg.session_end_time,
        session_end_policy=cfg.session_end_policy,
        target_fills_as_maker=cfg.target_fills_as_maker,
        limit_fill_capped_by_volume=cfg.limit_fill_capped_by_volume,
        enforce_capital_minimo=cfg.enforce_capital_minimo,
        max_open_contracts=cfg.max_open_contracts,
    )


def rodar(bars: pd.DataFrame, cfg: IntradayBacktestConfig, **strategy_kwargs):
    params = {**CANDIDATO_PARAMS, **strategy_kwargs}
    strat = WdoGridReloadMaker(**params)
    return run_intraday_backtest(bars, strat, cfg)


def descreve_janela(bars: pd.DataFrame) -> str:
    pregoes = len(set(bars.index.date))
    return (f"{len(bars)} barras M1, {pregoes} pregoes, "
            f"{bars.index.min():%Y-%m-%d} -> {bars.index.max():%Y-%m-%d}")


# ---------------------------------------------------------------------------
# 1. checagem de sanidade
# ---------------------------------------------------------------------------

def checagem_de_sanidade(bars: pd.DataFrame) -> None:
    """Testa TRES leituras plausiveis da mecanica/custo por tras do numero
    conhecido -- nenhuma escolhida a priori, todas reportadas juntas (ver a
    docstring de `WdoGridReloadMaker.ReanchorMode` para o motivo da ancora
    ser a variavel mais suspeita: `fixed_session_open`, igual ao
    `GridReloadMaker` de acao, deu liquido NEGATIVO com win rate ~84%, bem
    abaixo do breakeven de ~94,1% que a razao 1:16 exige)."""
    print("\n=== 1. checagem de sanidade (ballpark conhecido: "
          f"+R${num_br(BALLPARK_IS_LIQUIDO_BRL)}) ===")
    print(f"janela IS: {descreve_janela(bars)}")
    variantes = [
        ("rolling, fill capped por volume (config PADRAO)",
         dict(reanchor_mode="rolling_last_price"), dict(limit_fill_capped_by_volume=True)),
        ("rolling, slippage=0 (leitura literal 'atrito zero')",
         dict(reanchor_mode="rolling_last_price"), dict(limit_fill_capped_by_volume=True, slippage_ticks=0.0)),
        ("fixed_session_open (mecanica literal do GridReloadMaker)",
         dict(reanchor_mode="fixed_session_open"), dict(limit_fill_capped_by_volume=True)),
    ]
    linhas: list[LinhaResultado] = []
    for rotulo, strat_kwargs, cfg_kwargs in variantes:
        cfg = montar_config(pedagio_ticks=0.0, com_custo=True, **cfg_kwargs)
        resultado = rodar(bars, cfg, **strat_kwargs)
        recusas_total = resultado.ordens_aceitas + resultado.ordens_recusadas_por_teto
        recusas_pct = (100.0 * resultado.ordens_recusadas_por_teto / recusas_total) if recusas_total else 0.0
        linhas.append(linha_de_resultado(
            rotulo, resultado, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={"recusas_teto%": num_br(recusas_pct, 1)},
        ))
    print(cabecalho(("recusas_teto%",)))
    for item in linhas:
        print(linha(item, ("recusas_teto%",)))
    diffs = [(item.liquido_brl - BALLPARK_IS_LIQUIDO_BRL) / BALLPARK_IS_LIQUIDO_BRL * 100.0
             for item in linhas]
    print("desvio vs ballpark, na mesma ordem: " + ", ".join(f"{num_br(d, 1)}%" for d in diffs))


# ---------------------------------------------------------------------------
# 2. teste de metade
# ---------------------------------------------------------------------------

def teste_de_metade(bars: pd.DataFrame) -> None:
    print("\n=== 2. teste de metade (dentro do IS) ===")
    dias = sorted(set(bars.index.date))
    corte = dias[len(dias) // 2]
    primeira = bars[[d < corte for d in bars.index.date]]
    segunda = bars[[d >= corte for d in bars.index.date]]
    print(f"1a metade: {descreve_janela(primeira)}")
    print(f"2a metade: {descreve_janela(segunda)}")
    cfg = montar_config()
    linhas = [
        linha_de_resultado("1a metade (IS)", rodar(primeira, cfg), CAPITAL_NOCIONAL, capital_nocional=True),
        linha_de_resultado("2a metade (IS)", rodar(segunda, cfg), CAPITAL_NOCIONAL, capital_nocional=True),
    ]
    print(cabecalho())
    for item in linhas:
        print(linha(item))
    ambas_positivas = all(item.liquido_brl > 0 for item in linhas)
    print(f"as duas metades positivas com o MESMO candidato (T1 S16 x1)? {ambas_positivas}")
    print("nota de escopo: esta rodada NAO reotimiza parametros por metade -- "
          "so' confere se o candidato ja fixado (medido fora deste repo) se "
          "sustenta nas duas metades cronologicas do IS, nao se ele seria "
          "'o escolhido' por uma varredura rodada so' na 1a metade.")


# ---------------------------------------------------------------------------
# 3. nulo por sign-flip
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DiaPnL:
    bruto: float  # P&L SEM custo (soma dos trades do dia)
    custo: float  # SEMPRE <= 0 (tarifa + taxa de bolsa do dia, negativo)


def _pnl_diario(trades: list[IntradayTrade]) -> list[_DiaPnL]:
    por_dia: dict = {}
    for t in trades:
        dia = pd.Timestamp(t.exit_ts).date()
        bruto_trade = t.pnl_brl + t.fees_total  # desfaz o desconto de custo
        custo_trade = -t.fees_total
        b, c = por_dia.get(dia, (0.0, 0.0))
        por_dia[dia] = (b + bruto_trade, c + custo_trade)
    return [_DiaPnL(bruto=b, custo=c) for b, c in por_dia.values()]


def nulo_sign_flip(bars: pd.DataFrame, n_sementes: int = 5, draws_por_semente: int = 5000,
                    rotulo: str = "config padrao", cfg_kwargs: dict | None = None) -> None:
    print(f"\n=== 3. nulo por sign-flip ({rotulo}, formula correta) ===")
    cfg = montar_config(**(cfg_kwargs or {}))
    resultado = rodar(bars, cfg)
    dias = _pnl_diario(resultado.trades)
    if not dias:
        print("sem trades no IS -- nulo nao computavel.")
        return
    brutos = np.array([d.bruto for d in dias])
    custos = np.array([d.custo for d in dias])  # <= 0
    liquido_real = float(brutos.sum() + custos.sum())
    custo_total = float(custos.sum())
    print(f"{len(dias)} pregoes com trade. liquido real = R${num_br(liquido_real)}; "
          f"custo total pago = R${num_br(custo_total)}")

    percentis: list[float] = []
    medias_sinteticas: list[float] = []
    for semente in range(n_sementes):
        rng = np.random.default_rng(semente)
        sinais = rng.choice([-1.0, 1.0], size=(draws_por_semente, len(dias)))
        # cada linha = 1 sorteio: soma_dias(s_d * bruto_d) + custo_d (custo
        # SEMPRE pago, nunca invertido pelo sinal -- disciplina de teste #5).
        sintetico = sinais @ brutos + custo_total
        percentil = float((sintetico <= liquido_real).mean() * 100.0)
        percentis.append(percentil)
        medias_sinteticas.append(float(sintetico.mean()))

    percentis_arr = np.array(percentis)
    print(f"percentil do liquido real na distribuicao nula, por semente: "
          + ", ".join(num_br(p, 1) + "%" for p in percentis_arr))
    print(f"media entre {n_sementes} sementes = {num_br(percentis_arr.mean(), 1)}% "
          f"(min {num_br(percentis_arr.min(), 1)}%, max {num_br(percentis_arr.max(), 1)}%, "
          f"desvio {num_br(percentis_arr.std(), 1)}pp, n_draws/semente={draws_por_semente})")
    print(f"media do nulo (deveria ~ = -custo pago, R${num_br(-custo_total)}): "
          f"R${num_br(float(np.mean(medias_sinteticas)))}")


# ---------------------------------------------------------------------------
# 4. sensibilidade a pedagio de fila
# ---------------------------------------------------------------------------

def sensibilidade_pedagio(bars: pd.DataFrame, rotulo: str = "config padrao",
                           cfg_kwargs: dict | None = None,
                           grade: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)) -> None:
    print(f"\n=== 4. sensibilidade a pedagio de fila ({rotulo}, ticks/perna maker) ===")
    cfg_kwargs = dict(cfg_kwargs or {})
    linhas: list[LinhaResultado] = []
    pontos: list[tuple[float, float]] = []
    for pedagio in grade:
        cfg = montar_config(pedagio_ticks=pedagio, **cfg_kwargs)
        resultado = rodar(bars, cfg)
        liquido = sum(t.pnl_brl for t in resultado.trades)
        pontos.append((pedagio, liquido))
        linhas.append(linha_de_resultado(
            f"pedagio {num_br(pedagio, 1)} tick", resultado, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={"pedagio_ticks": num_br(pedagio, 1)},
        ))
    print(cabecalho(("pedagio_ticks",)))
    for item in linhas:
        print(linha(item, ("pedagio_ticks",)))

    ponto_morte = None
    for (p0, l0), (p1, l1) in zip(pontos, pontos[1:]):
        if l0 > 0 >= l1:
            frac = l0 / (l0 - l1) if (l0 - l1) != 0 else 0.0
            ponto_morte = p0 + frac * (p1 - p0)
            break
    if ponto_morte is None:
        if pontos[0][1] <= 0:
            print("ja nasce negativo mesmo com pedagio 0 -- sem ponto de morte a reportar aqui "
                  "(ver a checagem de sanidade acima).")
        else:
            print(f"nao morreu dentro da grade testada (positivo ate {pontos[-1][0]} tick/perna).")
        return
    preenchimento_minimo = 1.0 - ponto_morte
    print(f"ponto de morte (interpolado): ~{num_br(ponto_morte, 2)} tick/perna maker")
    print(f"traduzido em preenchimento passivo minimo necessario (1 - pedagio_ticks): "
          f"~{num_br(preenchimento_minimo * 100.0, 1)}%")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    locked = carregar_barras()
    bars = locked.in_sample()
    print(f"[wdo_grid_reload_f1] {SYMBOL} -- {descreve_janela(bars)} "
          f"(corte congelado: {locked.split.cutoff.date()})")
    print(f"candidato: T{CANDIDATO_PARAMS['profit_ticks']} "
          f"S{CANDIDATO_PARAMS['stop_ticks']} x{CANDIDATO_PARAMS['level_spacing_ticks']}, "
          f"quantity=1 contrato fixo, max_open_contracts={MAX_OPEN_CONTRATOS}")

    checagem_de_sanidade(bars)
    teste_de_metade(bars)
    nulo_sign_flip(bars, rotulo="config padrao (fee + slippage 1 tick)")
    sensibilidade_pedagio(bars, rotulo="config padrao (fee + slippage 1 tick)")

    # Segunda passada nas secoes 3/4, na MELHOR variante achada na checagem
    # de sanidade (rolling + slippage=0) -- ainda assim NAO reproduz o
    # ballpark, mas e' a unica com liquido positivo no IS, entao vale medir
    # se ela sobrevive ao nulo e ate onde ela aguenta pedagio de fila. Grade
    # de pedagio bem mais fina (o baseline e' so' +R$1.224 em 5.049 trades --
    # qualquer atrito ja deve derrubar isso perto de zero).
    print("\n--- mesma bateria (3/4) na variante 'rolling, slippage=0' (a unica positiva no IS) ---")
    nulo_sign_flip(bars, rotulo="rolling, slippage=0", cfg_kwargs=dict(slippage_ticks=0.0))
    sensibilidade_pedagio(bars, rotulo="rolling, slippage=0", cfg_kwargs=dict(slippage_ticks=0.0),
                          grade=(0.0, 0.02, 0.04, 0.06, 0.08, 0.1))

    print("\n=== 5. tabela padrao (linha unica, candidato completo, config padrao) ===")
    cfg = montar_config()
    resultado = rodar(bars, cfg)
    item = linha_de_resultado("wdo_grid_reload T1 S16 x1 (IS)", resultado,
                               CAPITAL_NOCIONAL, capital_nocional=True)
    print(cabecalho())
    print(linha(item))


if __name__ == "__main__":
    main()
