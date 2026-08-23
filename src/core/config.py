from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "raw"
# Dado intradiario (M1 de futuros via MT5) — diretorio PROPRIO, nao dentro de
# DATA_DIR: um parquet de minuto misturado com os parquets diarios de acao
# faria qualquer `glob("data/raw/*.parquet")` existente (ex.
# `scripts/run_walk_forward.py`) engolir um formato que nao e o dele por
# acidente. Ver `market_data_intraday/storage.py`.
INTRADAY_DATA_DIR = ROOT / "data" / "raw_intraday"
# Tick a tick (trade ticks via MT5, `market_data_intraday/mt5_ticks_source.py`)
# -- diretorio PROPRIO do M1 pelo MESMO motivo de `INTRADAY_DATA_DIR` acima:
# formato diferente (bid/ask/last/volume/flags, sem open/high/low) misturado
# no mesmo glob quebraria o primeiro leitor que assumir OHLCV.
TICK_DATA_DIR = ROOT / "data" / "raw_ticks"
DB_PATH = ROOT / "db" / "journal.sqlite"
SCHEMA_PATH = ROOT / "src" / "journal" / "schema.sql"

# Banco DEDICADO à operação real (tabelas `live_*`), separado fisicamente do
# diário de backtest (`DB_PATH` acima). Existe porque um backtest longo
# rodando em `threading.Thread` (ver `dashboard/app.py`) e a gravação de uma
# ordem real disputavam lock do MESMO arquivo `.sqlite` — dois domínios que
# não têm por que competir pelo mesmo I/O. Ver `journal.live_store` (usa este
# caminho como default) e `scripts/migrate_live_db.py` (copia o que já
# existia em `DB_PATH` para cá, sem apagar o original).
LIVE_DB_PATH = ROOT / "db" / "live.sqlite"


WATCHLIST: tuple[str, ...] = (
    # Top-7 selecionados por forward selection greedy (2026-08-15) maximizando
    # capital final FULL no dip_top1_hysteresis. CAGR 35,51% / Sharpe 0,85.
    "WEGE3.SA",   # industrial — motor principal, CAGR solo 20%
    "BRAP4.SA",   # holding Vale — captura ciclos de commodity com momentum distinto
    "RADL3.SA",   # farmácia — CAGR solo 17%, win rate alto
    "CSMG3.SA",   # saneamento (Copasa) — CAGR solo 15%, 3Y solo 35%
    "EMAE4.SA",   # energia — CAGR solo 16%, maior salto marginal (+R$39k)
    "KEPL3.SA",   # industrial (Kepler Weber) — CAGR solo 6%, contribui +R$20k
    "CXSE3.SA",   # seguros (Caixa Seg.) — MaxDD solo -19%, NegYrs 1; hist. curto ~4 anos
)

BENCHMARK: str = "^BVSP"

HISTORY_START: str = "2010-01-01"


# ---------------------------------------------------------------------------
# Slots de operação ao vivo
# ---------------------------------------------------------------------------
# Até 2026-08-21 o painel `/operacao` operava UM robô só: um PID, um log, uma
# conta chamada "principal" fixada em `scripts/run_live.py`. O dono do capital
# passou a querer dois robôs simultâneos — um de day trade (`gremah`, PMAM3,
# decide barra a barra) e um de swing (`liqflop`, carteira B3, decide 1x por
# pregão) — cada um com o SEU caixa, para que "quanto tenho disponível" seja
# uma pergunta com resposta por robô, não uma disputa pelo saldo da corretora.
#
# Um slot é DADO, não lógica: qual conta, que tipo de cadência, que `magic`.
# Quem age em cima disso é `dashboard/live_control.py` (sobe/derruba
# processo) e `scripts/run_live.py` (monta o runtime certo).
#
# O SÍMBOLO NÃO é campo do slot (removido 2026-08-21) — é propriedade do
# ROBÔ escolhido (`strategy.daytrade.registry`/`strategy.registry`), porque
# o slot só empresta caixa/conta/processo: dois robôs de day trade diferentes
# podem operar símbolos diferentes no MESMO slot, um por vez. `robot_key`
# abaixo é só o DEFAULT sugerido para uma conta nova — depois de criada, a
# conta fixa o robô dela (`live_accounts.investment_robot`) e o catálogo
# nunca mais escolhe por ela.
#
# `id` É o nome da conta em `live_accounts.name` — de propósito: um slot sem
# conta própria não teria caixa próprio, e caixa próprio é o pedido inteiro.
# A conta "principal" deixa de existir (ver `scripts/migrate_live_slots.py`).


@dataclass(frozen=True)
class Slot:
    """Uma vaga de operação ao vivo. Um processo, uma conta, um caixa."""

    id: str            # == `live_accounts.name`
    kind: str          # "daily" (decide no fecho) | "intraday" (barra a barra)
    robot_key: str     # robô DEFAULT sugerido para conta nova (não é o robô da conta)
    label: str
    dek: str           # uma linha explicando o slot no painel
    order: int         # posição no painel (0 = em cima)
    magic: int         # identificador das ordens deste slot no MT5
    min_cash_brl: float = 50.0
    # Ativo que este slot negocia. Vazio no swing (o robô diário escolhe dentro
    # do universo dele); preenchido no day trade, onde o slot É o par
    # robô+ativo — ver `daytrade_slot()`.
    symbol: str = ""

    @property
    def is_intraday(self) -> bool:
        return self.kind == "intraday"

    @property
    def is_dynamic(self) -> bool:
        """`True` se este slot foi criado pelo dono no painel (day trade), e
        não declarado em `SLOTS`. Slot dinâmico pode ser REMOVIDO; slot
        estático, não."""
        return self.id.startswith(DAYTRADE_SLOT_PREFIX + "-")


# SÓ O SWING É ESTÁTICO (2026-08-22). Até esta data havia também um slot
# `daytrade` fixo aqui, um robô num ativo só. O dono pediu para abrir QUANTOS
# robôs de day trade quiser, um por ativo, cada um com processo/conta/caixa
# próprios — o que um catálogo escrito no código não consegue expressar: o
# conjunto muda em tempo de execução, por clique. Day trade virou slot
# DINÂMICO, derivado das contas com `symbol` no banco (ver `daytrade_slot` e
# `dashboard.slots`). O swing continua aqui porque é genuinamente único: um
# robô diário que escolhe os papéis dentro do próprio universo, não um par
# robô+ativo.
#
# Ordem do painel decidida pelo dono (2026-08-21): day trade em CIMA, e não
# por ser melhor — é a primeira opção operável, porque o capital atual não
# alcança o swing (ver `capital_real_100_mes`/`liquid_focus_promoted` na
# memória do projeto). Por isso o swing declara `order=1` e todo slot de day
# trade nasce com `order=0`. `magic` distinto por slot é obrigatório, não estética:
# a conta da Rico é NETTING (`margin_mode=0`, verificado no terminal real em
# 2026-08-21), então dois robôs no MESMO símbolo virariam UMA posição só na
# corretora e os dois livros-caixa passariam a mentir.
# `live_control.start()` checa universo disjunto entre slots dinamicamente
# (pelo robô ESCOLHIDO, não por um símbolo fixo aqui — ver
# `_assert_slots_disjuntos`).
SLOTS: tuple[Slot, ...] = (
    Slot(
        id="swing",
        kind="daily",
        robot_key="liqflop",
        label="Swing — carteira B3",
        dek=("Uma posição por vez, rotação mensal por liquidez, decide no "
             "fechamento do pregão. Precisa de capital maior para a taxa fixa "
             "não comer o retorno."),
        order=1,
        magic=20260817,  # o mesmo de antes: a conta swing herda o histórico do CLI antigo
    ),
)


#: Prefixo do id de todo slot de day trade criado pelo dono no painel. O id
#: inteiro é `dt-<robô>-<ativo>` (ex.: `dt-gremah-pmam3`) e CARREGA a
#: identidade do slot: dá para reconstruir o `Slot` a partir do id, sem
#: consultar banco nenhum. Isso é o que permite `scripts/run_live.py --slot
#: dt-gremah-pmam3` funcionar como processo isolado, sem depender do
#: dashboard estar de pé nem de um catálogo compartilhado em memória.
DAYTRADE_SLOT_PREFIX = "dt"

#: Base do `magic` dos slots dinâmicos. `magic` distingue as ordens de cada
#: robô dentro do MESMO terminal MT5, e precisa ser estável entre reinícios
#: (senão o robô perde de vista as próprias ordens ao voltar) e distinto entre
#: slots (senão dois robôs leem as ordens um do outro como suas). Derivar de
#: `crc32(id)` dá as duas coisas de graça: mesmo id -> mesmo número, ids
#: diferentes -> números praticamente sempre diferentes. "Praticamente" não
#: basta para dinheiro real, então `live_control._assert_slots_disjuntos`
#: confere a unicidade de fato antes de qualquer robô subir.
_DAYTRADE_MAGIC_BASE = 862_000_000
_DAYTRADE_MAGIC_SPAN = 1_000_000


def daytrade_magic(slot_id: str) -> int:
    """`magic` determinístico deste slot — ver `_DAYTRADE_MAGIC_BASE`."""
    return _DAYTRADE_MAGIC_BASE + (zlib.crc32(slot_id.encode("utf-8")) % _DAYTRADE_MAGIC_SPAN)


def daytrade_slot_id(robot_key: str, symbol: str) -> str:
    """`dt-<robô>-<ativo>`, minúsculo. Recusa (`ValueError`) robô ou ativo com
    hífen: o hífen é o separador, e um valor que o contenha tornaria o id
    ambíguo para `slot_by_id` desmontar de volta."""
    robot_key = (robot_key or "").strip().lower()
    symbol = (symbol or "").strip().upper()
    if not robot_key or not symbol:
        raise ValueError(f"slot de day trade exige robô e ativo (recebi {robot_key!r}/{symbol!r})")
    if "-" in robot_key or "-" in symbol:
        raise ValueError(
            f"robô/ativo não podem conter '-' ({robot_key!r}/{symbol!r}) — "
            "é o separador do id do slot."
        )
    return f"{DAYTRADE_SLOT_PREFIX}-{robot_key}-{symbol.lower()}"


def daytrade_slot(robot_key: str, symbol: str, order: int = 0) -> Slot:
    """Monta o `Slot` de um robô de day trade rodando `symbol`.

    Função PURA (sem banco, sem I/O): é chamada tanto pelo painel, que sabe
    quais contas existem, quanto por `slot_by_id`, que só tem a string do id.
    Quem descobre que contas existem é a camada de orquestração
    (`dashboard.slots`), nunca `core/`.

    `min_cash_brl` fica no default genérico de propósito — o piso REAL do day
    trade é `capital_minimo_brl` do ativo no preço de HOJE, que depende de
    buscar preço e portanto não pode ser resolvido aqui (`core/` não faz I/O).
    Quem resolve é `dashboard.live_control.min_cash_for`.
    """
    robot_key = robot_key.strip().lower()
    symbol = symbol.strip().upper()
    slot_id = daytrade_slot_id(robot_key, symbol)
    return Slot(
        id=slot_id,
        kind="intraday",
        robot_key=robot_key,
        label=f"{robot_key} — {symbol}",
        dek=("Grade de ordens-limite recarregada dentro do pregão, sem posição "
             "overnight. Processo, conta e caixa próprios deste ativo."),
        order=order,
        magic=daytrade_magic(slot_id),
        symbol=symbol,
    )


def ordered_slots() -> tuple[Slot, ...]:
    """Os slots ESTÁTICOS (`SLOTS`) na ordem de exibição.

    Não inclui os slots de day trade: eles são criados pelo dono no painel e
    vivem no banco (`live_accounts` com `symbol` preenchido) — quem os lista é
    `dashboard.slots.all_slots()`, que é orquestração e pode tocar em
    `journal/`. `core/` não importa feature nenhuma (regra 1 do AGENTS.md).
    """
    return tuple(sorted(SLOTS, key=lambda s: s.order))


def slot_by_id(slot_id: str) -> Slot:
    """Slot pelo id — estático (`SLOTS`) ou dinâmico (`dt-<robô>-<ativo>`,
    reconstruído do próprio id). `KeyError` se não for nem um nem outro:
    nunca um default silencioso, porque um id desconhecido chegando de uma
    URL/argv significa form adulterado ou catálogo mudado, e escolher um slot
    por chute operaria dinheiro real na vaga errada."""
    for slot in SLOTS:
        if slot.id == slot_id:
            return slot
    partes = (slot_id or "").split("-")
    if len(partes) == 3 and partes[0] == DAYTRADE_SLOT_PREFIX:
        _, robot_key, symbol = partes
        if robot_key and symbol:
            return daytrade_slot(robot_key, symbol)
    raise KeyError(
        f"slot desconhecido: {slot_id!r} — estáticos: "
        f"{', '.join(s.id for s in SLOTS)}; dinâmicos seguem o formato "
        f"'{DAYTRADE_SLOT_PREFIX}-<robô>-<ativo>'."
    )


@dataclass(frozen=True)
class CostModel:
    brokerage_pct: float = 0.0003
    exchange_fees_pct: float = 0.0003
    slippage_pct: float = 0.0015
    # Corretagem FIXA por perna (compra OU venda) que não fecha lote padrão —
    # na Rico via MT5 (2026-08-21), lote padrão (>= `fractional_lot_shares`
    # ações) é GRATUITO e o mercado fracionário cobra R$1,90/ordem, fixo, não
    # percentual (ver `live/broker_mt5.py::MT5Broker._resolve_execution`, que
    # decide isso ao vivo com a MESMA regra — quantidade da perna vs
    # `fractional_lot_shares`). Default `0.0` = comportamento histórico de
    # TODO o diário (custo só em %) — mudar o default aqui reescreveria o
    # significado de 16 anos de runs gravadas, mesmo motivo do default de
    # `cash_yield_path=None` (ver `backtest/costs.py::cash_yield_series`).
    fractional_fixed_fee: float = 0.0
    # Quantidade mínima de ações (nessa perna) que fecha lote padrão — abaixo
    # disso, `fees_for_leg` cobra `fractional_fixed_fee` além do percentual.
    # Convenção real da B3 (100 ações), independente de `BacktestConfig.
    # lot_size` (que é granularidade de SIZING, não limiar de corretagem —
    # a run oficial de ranking usa `lot_size=1`, ver `dashboard/scheduler.py`).
    fractional_lot_shares: int = 100

    @property
    def per_side_pct(self) -> float:
        return self.brokerage_pct + self.exchange_fees_pct


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    max_concurrent_positions: int = 5
    stop_loss_pct: float = 0.15
    ibov_defensive_days: int = 3
    lot_size: int = 100
    costs: CostModel = field(default_factory=CostModel)
    # Caminho do parquet de Selic diária para remunerar o caixa parado.
    # `None` = caixa a 0%, que é como TODO o diário foi gravado — ver
    # `backtest.costs.cash_yield_series` para o porquê do default e para o
    # tamanho do viés que ele introduz nas variantes defensivas.
    cash_yield_path: str | None = None
    # Como o stop é PREENCHIDO — modelo de EXECUÇÃO, não regra de decisão (o
    # nível do stop continua vindo da estratégia). Existe para medir a única
    # divergência estrutural entre backtest e operação real: ao vivo o stop
    # dispara no preço OBSERVADO pelo feed, não na barra fechada.
    #
    #   "stop_or_open"  dispara se `low <= stop`, preenche em `min(open, stop)`.
    #                   Default e comportamento histórico de todo o diário.
    #                   É a hipótese OTIMISTA: assume que se conseguiu sair no
    #                   nível do stop (ou no open, se o gap foi pior).
    #   "close"         dispara se `close <= stop`, preenche no `close`. É o
    #                   que o `ParquetCloseFeed` faz de verdade em
    #                   `scripts/run_live_sim.py`: um feed que só vê o
    #                   fechamento não enxerga a perfuração intradiária, então
    #                   além de sair pior ele às vezes NÃO SAI.
    #   "low"           dispara se `low <= stop`, preenche no `low`. Limite
    #                   inferior de qualquer feed intradiário com atraso:
    #                   ninguém sai pior que a mínima do dia.
    #
    # Mudar isto NÃO melhora nem piora estratégia nenhuma — só troca a
    # hipótese de execução. Comparar arms é o ponto.
    stop_fill: str = "stop_or_open"
    # Gatilho de queda SUBITA, independente do stop — cobre o buraco que
    # `stop_loss_pct` nao cobre: um papel que subiu bastante desde a entrada
    # pode desabar 25% num unico pregao e ainda ficar ACIMA do stop (que fica
    # `stop_loss_pct` abaixo da ENTRADA original e nunca sobe). Nesse caso o
    # robo hoje nao faz nada ate o rebalance de fim de mes. Medido contra
    # desastres reais (`scripts/run_disaster_forced_entry.py`): HAPV3
    # 2025-11-13, DASA3 2021-04-07, IRBR3 2020-03-04, ENEV3 2015-02-13.
    #
    # `None` = desligado, e e o DEFAULT de proposito: o robo do podio
    # (`liquid_dual10`) foi medido e promovido SEM este gatilho, e liga-lo por
    # default mudaria em silencio um robo ja aprovado.
    #
    # Quando ligado: se o preco cair `gap_exit_pct` ou mais em relacao ao
    # FECHAMENTO ANTERIOR, sai a mercado imediatamente, independente do nivel
    # do stop. A referencia e o fechamento anterior (nao a entrada, nao a
    # maxima) porque o que se quer detectar e VELOCIDADE de queda, nao perda
    # acumulada — perda acumulada ja e trabalho do stop.
    #
    # Valor natural = o mesmo `stop_loss_pct` (0.15): a MESMA tolerancia que o
    # robo ja declara, so com outra referencia. Nao e um parametro novo de
    # ajuste.
    gap_exit_pct: float | None = None
    # Aporte mensal em reais, creditado no PRIMEIRO pregão de cada mês civil
    # (o mês do capital inicial não recebe aporte — ele JÁ é o primeiro
    # depósito). 0.0 = conta fechada, que é como todo o diário foi medido.
    #
    # Com aporte, `cagr` e `max_drawdown` da curva de patrimônio deixam de ser
    # comparáveis com uma conta fechada: dinheiro novo empurra o patrimônio
    # para cima sem que nada tenha rendido. Por isso o engine passa a devolver
    # também uma curva UNITIZADA (cota, no sentido de fundo): cada aporte
    # compra cotas ao valor do dia, então a cota mede só o desempenho. Ver
    # `BacktestResult.unit_curve` e as métricas `*_unit` / `irr`.
    monthly_contribution: float = 0.0
