from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class QualityReport:
    ticker: str
    rows: int
    start: pd.Timestamp
    end: pd.Timestamp
    nan_count: int
    max_gap_days: int
    duplicated_index: int
    missing_sessions: list[pd.Timestamp] = field(default_factory=list)

    def ok(self) -> bool:
        return (
            self.nan_count == 0
            and self.duplicated_index == 0
            and self.max_gap_days < 15
            and not self.missing_sessions
        )


def check(
    ticker: str, df: pd.DataFrame, calendar: pd.DatetimeIndex | None = None
) -> QualityReport:
    idx = df.index
    if len(idx) == 0:
        return QualityReport(ticker, 0, pd.NaT, pd.NaT, 0, 0, 0)

    gaps = idx.to_series().diff().dt.days.fillna(0).astype(int)
    missing: list[pd.Timestamp] = []
    if calendar is not None:
        window = calendar[(calendar >= idx.min()) & (calendar <= idx.max())]
        missing = list(window.difference(idx))

    return QualityReport(
        ticker=ticker,
        rows=len(df),
        start=idx.min(),
        end=idx.max(),
        nan_count=int(df[["open", "high", "low", "close"]].isna().sum().sum()),
        max_gap_days=int(gaps.max()),
        duplicated_index=int(idx.duplicated().sum()),
        missing_sessions=missing,
    )


def consensus_calendar(
    frames: dict[str, pd.DataFrame], min_ratio: float = 0.5, min_tickers: int = 5
) -> pd.DatetimeIndex | None:
    """Calendário de pregão B3 construído por consenso, sem depender de lib externa.

    Um dia entra no calendário se pelo menos `min_ratio` dos tickers de histórico
    longo o possuem. Isso separa feriado/fim de semana real (nenhum ticker tem,
    presença=0) de buraco pontual do yfinance num único ticker (quase todos têm,
    só um não — presença=n-1). O default de maioria simples (0.5) é deliberado:
    com universos pequenos (a watchlist oficial tem só 7 tickers + benchmark),
    um limiar alto como 0.9 exigiria unanimidade e trataria até 1 dissidente
    como "feriado", que é exatamente o oposto do que se quer detectar aqui.
    Exige um universo mínimo (`min_tickers`) com histórico longo o bastante para
    o voto fazer sentido; caso contrário devolve None (chamador pula a checagem
    em vez de arriscar falso positivo com poucos votantes).
    """
    long_hist = {t: df for t, df in frames.items() if len(df) > 0}
    if not long_hist:
        return None
    oldest_start = min(df.index.min() for df in long_hist.values())
    eligible = {
        t: df for t, df in long_hist.items() if df.index.min() <= oldest_start + pd.Timedelta(days=30)
    }
    if len(eligible) < min_tickers:
        return None

    union = sorted(set().union(*[set(df.index) for df in eligible.values()]))
    n = len(eligible)
    presence = {d: sum(1 for df in eligible.values() if d in df.index) for d in union}
    return pd.DatetimeIndex([d for d in union if presence[d] >= n * min_ratio])


def fill_gaps(df: pd.DataFrame, calendar: pd.DatetimeIndex) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Preenche sessões do `calendar` ausentes em `df` carregando o close anterior.

    Barra sintética: open=high=low=close=adj_close(se houver)=fechamento anterior,
    volume=0. Marcada em `synthetic=True` para não confundir com pregão real caso
    algo a jusante precise diferenciar (ex.: um hiato de VÁRIOS dias seguidos
    sinalizaria suspensão de negociação, não gap de provedor). Só preenche
    sessões DENTRO do intervalo já coberto por `df` — não estende a série.
    """
    if df.empty:
        return df, []
    window = calendar[(calendar >= df.index.min()) & (calendar <= df.index.max())]
    missing = list(window.difference(df.index))
    if not missing:
        out = df.copy()
        out["synthetic"] = False
        return out, []

    full_idx = window.union(df.index).sort_values()
    out = df.reindex(full_idx)
    price_cols = [c for c in ("open", "high", "low", "close", "adj_close") if c in out.columns]
    out["synthetic"] = out[price_cols[0]].isna() if price_cols else False
    out[price_cols] = out[price_cols].ffill()
    if "volume" in out.columns:
        out.loc[out["synthetic"], "volume"] = 0.0
    return out, sorted(missing)
