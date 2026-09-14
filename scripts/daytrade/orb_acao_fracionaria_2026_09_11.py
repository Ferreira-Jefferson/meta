"""VALIDACAO: ORB fracionario numa acao liquida (ITUB4/BBAS3), capital alvo
R$500, dentro do desenho de execucao FECHADO (entrada limite, alvo limite
fatiado, so' o stop a mercado) -- pedido do dono, rodada 2026-09-11.

## O que este script testa

Mesma logica de `strategy/daytrade/lab/wdo_orb.py` (rompimento da faixa de
abertura + fade do rompimento oposto), portada de TICKS para CENTAVOS e de
CONTRATOS para ACOES FRACIONARIAS -- a estrategia mora AQUI (nao em
`strategy/`, e' experimento de laboratorio, nao candidato a producao ainda)
porque a pergunta de fundo e' se o efeito ORB generaliza para o padrao de
abertura de uma acao, ou se e' especifico do cambio.

## ACHADO MAIS IMPORTANTE, ANTES DE QUALQUER NUMERO DE BACKTEST

O repo tem uma politica JA DECIDIDA e JA IMPLEMENTADA (pedido do dono,
2026-08-22) que este experimento contraria: **day trade nunca opera no
mercado fracionario**. Nao e' uma lacuna, e' bloqueio deliberado, em tres
lugares:

  * `strategy.daytrade.base.LOTE_PADRAO_B3` (docstring): "Day trade nao usa
    fracionario: cada ordem la custa R$1,90 fixos na corretora, proibitivo
    num robo de giro alto";
  * `dashboard/live_control.py::detect_fractional_symbol_map` (docstring):
    "Dia trade NUNCA usa o resultado desta funcao (...) uma quantidade que
    nao fecha o lote padrao tem de ser REJEITADA, nunca reencaminhada ao
    mercado fracionario";
  * `dashboard/app.py::operacao_iniciar`: `mt5_fractional_map` fica `None`
    SEMPRE para um slot intradiario, e `scripts/run_live.py::build_intraday`
    ignora `--mt5-fractional-map` de proposito mesmo se a flag vier setada.

A justificativa ESCRITA nos tres lugares fala de GIRO ALTO (a familia
Gremah, centenas de round-trips/mes) -- e' exatamente a distincao que a
hipotese desta rodada tenta fazer (ORB faz 1-2 round-trips/PREGAO, nao
centenas/mes). Mas o BLOQUEIO no codigo e' por SLOT INTRADIARIO INTEIRO, nao
por estrategia: nao ha' parametro nenhum, em nenhum dos tres lugares, que
deixe um robo de giro baixo passar. Reverter isso exigiria editar
`dashboard/app.py`, `dashboard/live_control.py` e `scripts/run_live.py` --
os TRES sao producao, e esta fase e' so' experimento (nao edito producao
aqui). Portanto: mesmo que o numero abaixo saia POSITIVO, HOJE nao ha'
caminho de execucao real para ele chegar ao vivo sem o dono decidir revogar
uma politica explicita e sem uma mudanca de codigo fora do escopo desta
rodada.

Isso e' medido e reportado mesmo assim, por dois motivos: (1) o dono pode
decidir que a excecao vale a pena para um robo de baixo giro, e a decisao
merece o numero ao lado; (2) "sem caminho de execucao" e' por si so' um
resultado de metodo digno de registro (mesma familia do "Enter a mercado nao
tem caminho real" que ja motivou o desenho fechado).

## O segundo problema, economico, independente do bloqueio de politica

R$1,90 e' por ORDEM, nao por acao/contrato (`IntradayCostModel.fee_round_
trip_brl` do motor e' por-UNIDADE -- nao serve para modelar uma tarifa FIXA
por ordem sem reescrever o motor). Contorno adotado aqui, sem tocar
`backtest/intraday/`: `profile.fee_round_trip_brl = (2 x R$1,90) / quantity`
-- como o motor multiplica `fee_round_trip_brl x quantity` a CADA registro de
trade fechado (inclusive fatias parciais do alvo fatiado), a soma ao longo
de um round-trip inteiro (entrada + saida, fatiada ou nao) da' exatamente
R$3,80 = 2 ordens x R$1,90, nao importa em quantas fatias o motor divida o
fechamento. Fica de fora, DECLARADO como limitacao: o reprice de
`AdjustTarget` (60min) pode gerar uma 3a ordem na corretora (cancela+repoe),
nao modelada; e cada FADE (2a operacao no dia) e' um round-trip GENUINO
novo, e por isso paga os R$3,80 de novo -- correto, nao e' bug.

Com Q acoes fracionarias e capital ~R$500, R$3,80 fixos por round-trip e'
uma fatia GRANDE do notional (Q~6-13 acoes x R$18-39 = R$450-500,
R$3,80/R$470 ~ 0,8%) -- ordem de grandeza MAIOR que a taxa de bolsa
percentual (0,05%/perna) que ja e' cobrada em cima disso.

## Fila NAO CALIBRADA

`backtest/intraday/fidelidade.py` so' tem WDO@ medido. ITUB4/BBAS3 em
fracionario nunca tiveram fila real medida -- a tabela de saida carimba
`fila NAO CALIBRADA` automaticamente (`IntradayCostModel.fidelidade_
calibrada=False`, ver `report.linha_de_resultado`), e o motor roda com
`queue_ahead_qty=exit_queue_ahead_qty=0,0` (o motor OTIMISTA, primeiro toque
preenche) -- o mesmo regime que, no WDO@, superestimava o resultado por
inverter o SINAL do trade medio. Sem essa medicao aqui, todo numero desta
tabela e' um TETO otimista, nao uma previsao.

## Desenho de execucao (dentro do fechado, ordem do dono 2026-09-10)

  * entrada por `EnterLimit` parada `offset_ticks` centavos ATRAS do
    rompimento, com prazo (`entrada_ttl_bars`, em MINUTOS -- feed M1, nao
    tick, entao aqui barra=minuto de verdade, sem a armadilha do WDO@);
  * alvo por ordem-limite REAL fatiada (`exit_split_unit=1` acao),
    `EXIT_TTL_BARS_SEM_PRAZO` (nunca `None` -- mesma regra do `wdo_orb`);
  * `anchor_exits_at_fill=True`;
  * stop a MERCADO -- unica excecao;
  * fade do rompimento oposto, `max_fades_por_dia=1` (mesmo default atual
    do `wdo_orb` em producao).

## Capital

`strategy.daytrade.base.capital_minimo_brl(preco_atual, shares_per_lot=Q)`
-- NAO o `capital_minimo_brl(preco_atual)` default (que assume lote de 100 e
daria R$7.000+): a convencao de "capital minimo real do INSTRUMENTO" so' faz
sentido aqui em cima do desenho FRACIONARIO que a hipotese propoe, com Q
calibrado para ficar perto de R$500. Q e' fixo por simbolo (nao redimensiona
com o caixa) -- mesma politica de `quantity: int = 1` do `wdo_orb`.

## Janelas

`OOS_CUTOFF="2026-06-13"` -- a mesma convencao de corte que toda a familia
Gremah usa (`backtest.intraday.profiles.OOS_CUTOFF`), reaproveitada aqui pela
MESMA razao (nunca escolhida em funcao deste experimento). Dado local vai de
~2025-09-16 (ITUB4) / ~2025-09-17 (BBAS3) ate' 2026-08-21 (M1,
`market_data_intraday.storage`). Antes de rodar a janela cheia, uma fatia
PEQUENA (20 primeiros pregoes do dado) roda sozinha, como gate -- "o minimo
que refuta primeiro".

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` -- 2 simbolos x 3 janelas
(pequena, IS, OOS) = 6 tarefas independentes, cada uma imprime a linha dela
assim que termina.

Uso: `python -u scripts/daytrade/orb_acao_fracionaria_2026_09_11.py`
"""
from __future__ import annotations

import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

#: Custo Rico do fracionario, por ORDEM (confirmado pelo dono, 2026-08-21/22).
FEE_POR_ORDEM_BRL = 1.90
ORDENS_POR_ROUND_TRIP = 2  # 1 entrada + 1 saida (fatiada ou nao, ver docstring)

OOS_CUTOFF = "2026-06-13"

SYMBOLS = ("ITUB4", "BBAS3")

#: (stop_min_ticks, stop_max_ticks) em CENTAVOS -- calibrado na distribuicao
#: real da faixa de abertura de 15min de cada papel (ver o print de
#: diagnostico no `main()`; ITUB4 p25/p50/p75 = 21/28/39 centavos, BBAS3 =
#: 15/20/25). Mesma logica de `WdoOrb.stop_min_ticks/stop_max_ticks`: o piso
#: evita stop ridiculo num pregao parado, o teto evita stop gigante num
#: pregao de faixa larga.
GEOMETRIA_POR_SYMBOL = {
    "ITUB4": (15, 35),
    "BBAS3": (12, 28),
}

CAPITAL_ALVO_BRL = 500.0


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


def _quantidade_fracionaria(preco: float, capital_alvo: float) -> int:
    """Quantas acoes fracionarias cabem no capital-alvo, via a MESMA formula
    de `capital_minimo_brl` (preco x qty x 2) -- nunca digitar Q na mao."""
    from strategy.daytrade.base import CAPITAL_MINIMO_EM_LOTES
    q = int(capital_alvo // (preco * CAPITAL_MINIMO_EM_LOTES))
    return max(1, q)


def _monta_profile(symbol: str, quantity: int):
    """`SymbolProfile` de laboratorio -- ITUB4/BBAS3 fracionario nao esta
    em `backtest.intraday.profiles.PROFILES` (aquela tabela e' a familia
    Gremah, lote padrao). Construido a mao, e nao com `_equity_profile`
    (privada do modulo), porque o tarifario aqui e' DIFERENTE (fracionario
    fixo por ordem, nao lote padrao gratuito) -- reusar a fabrica emprestaria
    um `fee_note`/custo que nao e' o daqui."""
    from backtest.intraday.costs import B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG
    from backtest.intraday.profiles import SymbolProfile

    # `fee_round_trip_brl=0.0` DE PROPOSITO -- o motor multiplica este campo
    # pela QUANTIDADE de CADA `IntradayTrade` fechado, e com `exit_split_unit
    # =1` uma posicao de Q acoes vira ate' Q registros PARCIAIS de 1 acao
    # cada. R$1,90 e' por ORDEM, nao por acao: tentar prorratear por acao
    # (testado, revertido) faz cada fatia de 1 acao pagar quase R$0,63 de
    # taxa sobre um bruto de ~R$0,50 (alvo pequeno x 1 acao), derrubando o
    # win% para 0% por um artefato de CONTABILIDADE, nao pela estrategia. O
    # custo real (R$3,80 = 2 ordens x R$1,90, FLAT por round-trip, qualquer
    # que seja Q) e' somado FORA do motor, uma vez por posicao (agrupada por
    # `entry_ts`) em `_roda_uma` -- ver o comentario la'.
    fee_round_trip_brl=0.0
    return SymbolProfile(
        frozen_cutoff=OOS_CUTOFF,
        frozen_note=(
            f"experimento novo (2026-09-11), sem historico de calibracao previo. "
            f"IS=inicio..{OOS_CUTOFF}, OOS={OOS_CUTOFF}..fim do dado local."
        ),
        fee_round_trip_brl=fee_round_trip_brl,
        fee_note=(
            f"MERCADO FRACIONARIO: R${FEE_POR_ORDEM_BRL:.2f} fixos/ordem na Rico x "
            f"{ORDENS_POR_ROUND_TRIP} ordens/round-trip = R$3,80 FLAT por posicao "
            f"fechada (nao escala com Q), deduzido FORA do motor -- ver `_roda_uma`."
        ),
        exchange_fee_pct_per_leg=B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG,
        session_end_time=dtime(19, 54),
        session_end_policy="b3_equities",
        default_quantity=quantity,
        point_value_brl=1.0,
    )


def main() -> None:
    sys.path.insert(0, str(SRC))
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.base import capital_minimo_brl

    print("[orb_acao_fracionaria] ACHADO DE POLITICA (ler antes da tabela):")
    print("  day trade fracionario esta' BLOQUEADO na producao por pedido")
    print("  explicito do dono (2026-08-22) -- dashboard/live_control.py,")
    print("  dashboard/app.py e scripts/run_live.py recusam o caminho para")
    print("  QUALQUER slot intradiario, nao so' robo de giro alto. Mesmo um")
    print("  resultado positivo abaixo NAO tem caminho de execucao ao vivo")
    print("  hoje sem o dono revogar essa politica + mudanca de codigo fora")
    print("  do escopo desta rodada (ver docstring do modulo).\n", flush=True)

    diagnostico = {}
    for symbol in SYMBOLS:
        df = load_m1(symbol).sort_index()
        preco_ref = float(df["close"].iloc[-1])
        q = _quantidade_fracionaria(preco_ref, CAPITAL_ALVO_BRL)
        capital = capital_minimo_brl(preco_ref, shares_per_lot=q)
        diagnostico[symbol] = (df, preco_ref, q, capital)
        print(f"[orb_acao_fracionaria] {symbol}: preco_ref=R${preco_ref:.2f} "
              f"Q={q} acoes fracionarias -> capital_minimo_brl=R${capital:.2f} "
              f"(alvo R${CAPITAL_ALVO_BRL:.2f})", flush=True)

    tarefas = []
    for symbol in SYMBOLS:
        df, preco_ref, q, capital = diagnostico[symbol]
        dias = sorted(set(df.index.date))
        dias_pequena = set(dias[:20])
        tarefas.append(dict(symbol=symbol, janela="pequena(20d)",
                             filtro_dias=dias_pequena, q=q, capital=capital))
        dias_is = {d for d in dias if str(d) < OOS_CUTOFF}
        dias_oos = {d for d in dias if str(d) >= OOS_CUTOFF}
        tarefas.append(dict(symbol=symbol, janela="IS", filtro_dias=dias_is,
                             q=q, capital=capital))
        tarefas.append(dict(symbol=symbol, janela="OOS", filtro_dias=dias_oos,
                             q=q, capital=capital))

    print(f"\n[orb_acao_fracionaria] {len(tarefas)} tarefas, "
          f"{min(6, len(tarefas))} processos\n", flush=True)

    resultados = {}
    with ProcessPoolExecutor(max_workers=min(6, len(tarefas))) as pool:
        futs = {pool.submit(_roda_uma, t): (t["symbol"], t["janela"]) for t in tarefas}
        for fut in as_completed(futs):
            chave, texto, payload = fut.result()
            resultados[chave] = payload
            print(texto, flush=True)

    print("\n=== TABELA FINAL ===")
    from backtest.intraday.report import cabecalho, linha
    extras = ("fee/ordem", "s/trd", "stops", "caixa_min", "BE_emp%",
              "IC95_win", "pregoes+%")
    print(cabecalho(extras))
    for symbol in SYMBOLS:
        for janela in ("pequena(20d)", "IS", "OOS"):
            chave = (symbol, janela)
            if chave in resultados:
                item = resultados[chave]["linha"]
                print(linha(item, extras))


def _roda_uma(spec: dict):
    sys.path.insert(0, str(SRC))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for
    from backtest.intraday.report import linha_de_resultado, num_br
    from core.models import IntradayExitReason
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.base import (
        AdjustTarget, Bar, EnterLimit, Exit, IntradayAction,
        IntradayOpenPosition, IntradayStrategy,
    )

    symbol = spec["symbol"]
    q = spec["q"]
    capital = spec["capital"]
    stop_min, stop_max = GEOMETRIA_POR_SYMBOL[symbol]

    EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

    @dataclass
    class AcaoOrbLab(IntradayStrategy):
        """Porte do `wdo_orb` para acao fracionaria -- ticks viram centavos,
        contratos viram acoes. Ver docstring do modulo para o desenho."""

        # Defaults GENERICOS de proposito -- classe definida DENTRO da funcao
        # do processo filho (closure sobre o simbolo desta tarefa), e o
        # corpo de uma classe Python NAO enxerga variaveis LOCAIS da funcao
        # que a envolve (so' enxerga global/builtin -- diferente de uma
        # `def` aninhada). Os valores REAIS (symbol/stop_min/stop_max/q)
        # entram via CONSTRUTOR, na instanciacao logo abaixo.
        name: str = "acao_orb_lab"
        version: str = "0.1.0"
        symbol: str = "?"
        target_fills_as_maker: bool = True
        anchor_exits_at_fill: bool = True
        feed_kind: str = "m1"
        is_futuro: bool = False

        tick_size: float = 0.01
        range_minutos: float = 15.0
        stop_min_ticks: int = 1
        stop_max_ticks: int = 1
        alvo_multiplo: float = 2.0
        quantity: int = 1

        exit_minutos: float | None = None
        saida_limite_minutos: float | None = 60.0
        offset_ticks: int = 2
        entrada_ttl_bars: int | None = 15  # MINUTOS de verdade (feed m1)
        fade_rompimento_oposto: bool = True
        max_fades_por_dia: int = 1

        _open_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
        _range_hi: float | None = field(default=None, init=False, repr=False)
        _range_lo: float | None = field(default=None, init=False, repr=False)
        _armou_hoje: bool = field(default=False, init=False, repr=False)
        _limite_posto: bool = field(default=False, init=False, repr=False)
        _preencheu_hoje: bool = field(default=False, init=False, repr=False)
        _lado_primeiro: str | None = field(default=None, init=False, repr=False)
        _fades_no_dia: int = field(default=0, init=False, repr=False)
        _tinha_posicao: bool = field(default=False, init=False, repr=False)

        def on_session_start(self, session_date) -> None:
            self._open_ts = None
            self._range_hi = None
            self._range_lo = None
            self._armou_hoje = False
            self._limite_posto = False
            self._preencheu_hoje = False
            self._lado_primeiro = None
            self._fades_no_dia = 0
            self._tinha_posicao = False

        def on_order_rejected(self, ts) -> None:
            self._armou_hoje = False

        def on_order_expired(self, ts) -> None:
            self._armou_hoje = False

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            if self._open_ts is None:
                self._open_ts = ts

            if self._tinha_posicao and not positions:
                self._tinha_posicao = False
                if self.fade_rompimento_oposto:
                    self._armou_hoje = False
                    self._limite_posto = False
            if positions:
                self._tinha_posicao = True

            if (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos):
                self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
                self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
                return []

            if positions:
                self._preencheu_hoje = True
                pos = positions[0]
                if self.saida_limite_minutos is not None and not self._limite_posto:
                    if (ts - pos.entry_ts) >= pd.Timedelta(minutes=self.saida_limite_minutos):
                        self._limite_posto = True
                        return [AdjustTarget(float(bar.close))]
                return []
            self._limite_posto = False

            if self._armou_hoje:
                return []
            if self._range_hi is None or self._range_lo is None:
                return []

            if not self._preencheu_hoje:
                stop_ticks, alvo_ticks = self._geometria()
                off = self.offset_ticks * self.tick_size
                if bar.close > self._range_hi:
                    limite = bar.close - off
                    self._armou_hoje = True
                    self._lado_primeiro = "long"
                    return [self._ordem("long", limite, stop_ticks, alvo_ticks, "orb_rompimento_alta")]
                if bar.close < self._range_lo:
                    limite = bar.close + off
                    self._armou_hoje = True
                    self._lado_primeiro = "short"
                    return [self._ordem("short", limite, stop_ticks, alvo_ticks, "orb_rompimento_baixa")]
                return []

            if (self.fade_rompimento_oposto and self._fades_no_dia < self.max_fades_por_dia
                    and self._lado_primeiro is not None):
                stop_ticks, alvo_ticks = self._geometria()
                off = self.offset_ticks * self.tick_size
                if self._lado_primeiro == "long" and bar.close < self._range_lo:
                    self._fades_no_dia += 1
                    self._armou_hoje = True
                    return [self._ordem("long", bar.close - off, stop_ticks, alvo_ticks, "orb_fade_volta_a_faixa")]
                if self._lado_primeiro == "short" and bar.close > self._range_hi:
                    self._fades_no_dia += 1
                    self._armou_hoje = True
                    return [self._ordem("short", bar.close + off, stop_ticks, alvo_ticks, "orb_fade_volta_a_faixa")]
            return []

        def _geometria(self):
            assert self._range_hi is not None and self._range_lo is not None
            range_ticks = (self._range_hi - self._range_lo) / self.tick_size
            stop_ticks = max(self.stop_min_ticks, min(self.stop_max_ticks, round(range_ticks)))
            alvo_ticks = round(stop_ticks * self.alvo_multiplo)
            return int(stop_ticks), int(alvo_ticks)

        def _ordem(self, side, limite, stop_ticks, alvo_ticks, reason):
            sinal = 1.0 if side == "long" else -1.0
            return EnterLimit(
                side=side, limit_price=limite,
                initial_stop=limite - sinal * stop_ticks * self.tick_size,
                initial_target=limite + sinal * alvo_ticks * self.tick_size,
                quantity=self.quantity, ttl_bars=self.entrada_ttl_bars,
                exit_split_unit=1, exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
                reason=reason,
            )

    df = load_m1(symbol).sort_index()
    filtro = spec["filtro_dias"]
    bars = df[[d in filtro for d in df.index.date]]

    strat = AcaoOrbLab(symbol=symbol, stop_min_ticks=stop_min,
                       stop_max_ticks=stop_max, quantity=q)
    profile = _monta_profile(symbol, q)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.01,
        initial_capital=capital,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
        anchor_exits_at_fill=True,
        enforce_capital_minimo=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)

    # `resultado.trades` esta' em FATIAS (exit_split_unit=1): uma posicao de
    # Q acoes que fecha em pedacos vira ate' Q registros PARCIAIS com o
    # MESMO `entry_ts`. Agrupar por `entry_ts` reconstroi a POSICAO (o
    # round-trip de verdade -- 1 entrada, 1 saida, mesmo que a saida tenha
    # sido preenchida aos poucos) e e' so' NELA que o custo fixo de R$3,80
    # (2 ordens x R$1,90, FLAT, nao escala com Q -- ver `_monta_profile`)
    # e' cobrado, uma vez por posicao. Sem este agrupamento, "trades" conta
    # fatia de 1 acao como se fosse operacao inteira, e o win%/breakeven
    # saem sobre a unidade errada.
    trades_brutos = list(resultado.trades)
    posicoes: dict[tuple, list] = {}
    for t in trades_brutos:
        posicoes.setdefault((t.entry_ts, t.side), []).append(t)

    registros = []
    for (entry_ts, _side), fatias in posicoes.items():
        pnl_bruto_motor = sum(t.pnl_brl for t in fatias)  # ja' inclui taxa de bolsa %
        pnl_liquido = pnl_bruto_motor - (ORDENS_POR_ROUND_TRIP * FEE_POR_ORDEM_BRL)
        is_stop = any(t.exit_reason == IntradayExitReason.STOP for t in fatias)
        registros.append({
            "pnl": pnl_liquido,
            "dia": pd.Timestamp(entry_ts).date(),
            "is_stop": is_stop,
        })

    n = len(registros)
    dias_janela = set(bars.index.date)
    dias_com_trade = {r["dia"] for r in registros}
    s_trd = len(dias_janela - dias_com_trade)
    ganhos = [r["pnl"] for r in registros if r["pnl"] > 0]
    perdas = [r["pnl"] for r in registros if r["pnl"] <= 0]
    vitorias = len(ganhos)
    stops = sum(1 for r in registros if r["is_stop"])
    ganho_medio = (sum(ganhos) / len(ganhos)) if ganhos else 0.0
    perda_media = (abs(sum(perdas)) / len(perdas)) if perdas else 0.0
    be_emp = (100.0 * perda_media / (ganho_medio + perda_media)
              if (ganho_medio + perda_media) > 0 else float("nan"))
    win_pct = (100.0 * vitorias / n) if n else 0.0
    ic_lo, ic_hi = ic_wilson(vitorias, n)

    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")
    # LIMITACAO declarada: `caixa_min`/`equity_curve`/`wiped_out_at` vem do
    # motor com o custo FLAT de R$3,80/posicao ainda NAO deduzido (o motor
    # so' conhece `fee_round_trip_brl=0.0`, ver `_monta_profile`) -- a curva
    # de caixa aqui e' ligeiramente OTIMISTA (nao inclui a corretagem por
    # ordem). Corrigir isso exigiria o custo entrando na config do motor
    # (`IntradayBacktestConfig`), fora do escopo de um script de laboratorio.
    # O `liquido`/`win%`/breakeven usados no VEREDITO (abaixo) SAO ajustados;
    # so' a curva intradiaria de caixa nao e'.

    liquido_ajustado = sum(r["pnl"] for r in registros)
    # Mutar o `fees_total` da fatia mais TARDIA de cada posicao (a que
    # realmente fecha o round-trip) para a tabela PADRAO (`linha_de_
    # resultado`, que soma `t.pnl_brl` sobre as fatias BRUTAS) bater com o
    # liquido ajustado -- sem isto a coluna `liquido R$` da tabela de 12
    # colunas ficaria otimista em R$3,80 x numero de posicoes.
    for (entry_ts, _side), fatias in posicoes.items():
        mais_tardia = max(fatias, key=lambda t: t.exit_ts)
        mais_tardia.fees_total += ORDENS_POR_ROUND_TRIP * FEE_POR_ORDEM_BRL

    # dias/pregoes POSITIVOS -- soma do pnl (ja' ajustado) por dia de
    # calendario, agrupado por POSICAO (nao por fatia).
    if n:
        pnl_by_day: dict = {}
        for r in registros:
            pnl_by_day[r["dia"]] = pnl_by_day.get(r["dia"], 0.0) + r["pnl"]
        dias_operados = len(pnl_by_day)
        dias_pos = sum(1 for v in pnl_by_day.values() if v > 0)
        pct_dias_pos = 100.0 * dias_pos / dias_operados if dias_operados else float("nan")
    else:
        pct_dias_pos = float("nan")

    extras = {
        "fee/ordem": num_br(FEE_POR_ORDEM_BRL, 2),
        "s/trd": f"{s_trd}/{len(dias_janela)}",
        "stops": str(stops),
        "caixa_min": num_br(caixa_min, 2),
        "BE_emp%": num_br(be_emp, 2),
        "IC95_win": f"[{num_br(ic_lo,1)};{num_br(ic_hi,1)}]",
        "pregoes+%": num_br(pct_dias_pos, 1),
    }
    item = linha_de_resultado(f"{symbol}/{spec['janela']}", resultado, capital,
                              capital_nocional=False, extras=extras)

    texto = (f"[{symbol}/{spec['janela']}] posicoes(round-trip)={n} win={win_pct:.1f}% "
             f"BE_emp={be_emp:.2f}% IC95=[{ic_lo:.1f};{ic_hi:.1f}] "
             f"liquido_ajustado=R${liquido_ajustado:.2f} "
             f"stops={stops} s/trd={s_trd}/{len(dias_janela)} "
             f"caixa_min(sem taxa/ordem)=R${caixa_min:.2f} zerou={resultado.wiped_out_at}")
    payload = {"linha": item, "n": n, "win_pct": win_pct, "be_emp": be_emp,
               "ic": (ic_lo, ic_hi), "stops": stops, "s_trd": s_trd,
               "dias": len(dias_janela), "caixa_min": caixa_min,
               "liquido": liquido_ajustado,
               "maxdd": item.maxdd_brl, "capital": capital, "q": q,
               "pct_dias_pos": pct_dias_pos, "zerou": resultado.wiped_out_at}
    return (symbol, spec["janela"]), texto, payload


if __name__ == "__main__":
    main()
