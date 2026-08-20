from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "raw"
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


@dataclass(frozen=True)
class CostModel:
    brokerage_pct: float = 0.0003
    exchange_fees_pct: float = 0.0003
    slippage_pct: float = 0.0015

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
