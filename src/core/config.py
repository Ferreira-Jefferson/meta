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
