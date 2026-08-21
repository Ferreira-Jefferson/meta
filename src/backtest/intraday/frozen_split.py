"""Arcabouco de teste cego — trava o trecho out-of-sample ATE alguem
desbloquear explicitamente.

O lado swing usa 48 janelas de holdout com 5 anos cada (`scripts/
run_holdout_frozen.py`) porque tem 16 anos de historico diario. Day trade
via MT5 hoje tem so ~9 meses de M1 (achado do plano de escopo) — nao ha
como replicar esse desenho. O que sobrevive e a DISCIPLINA: declarar o
corte ANTES de olhar qualquer hipotese, e so trocar de banco de dado
depois de decidir. `LockedBars` torna isso estrutural (o codigo recusa
`out_of_sample()`) em vez de so documentado — documentado e opcional,
estrutural nao e.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class FrozenSplit:
    cutoff: pd.Timestamp
    frozen_at: datetime
    note: str = ""


def declare_frozen_split(
    cutoff: str,
    note: str = "",
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> FrozenSplit:
    """Registra a decisao de corte AGORA, antes de qualquer hipotese ser
    testada. `now_fn` injetavel (mesma convencao de `ParquetCloseFeed`/
    `MT5Feed`) para `frozen_at` ser deterministico em teste."""
    return FrozenSplit(cutoff=pd.Timestamp(cutoff), frozen_at=now_fn(), note=note)


class LockedBars:
    """Envolve um DataFrame de barras M1 completo + um `FrozenSplit`.
    `.in_sample()` sempre disponivel; `.out_of_sample()` levanta
    `RuntimeError` ate `.unlock(reason)` ser chamado explicitamente — trava
    ESTRUTURAL contra "so espiar uma vez", nao so uma convencao de nome de
    variavel."""

    def __init__(self, bars: pd.DataFrame, split: FrozenSplit) -> None:
        self._bars = bars
        self._split = split
        self._unlocked_reason: str | None = None
        # `declare_frozen_split` nao sabe se as barras que vao chegar tem
        # tz (dado real do MT5 sempre tem, ver `mt5_source._bars_to_df`) ou
        # nao (dado sintetico de teste pode nao ter) — casa o `cutoff` com a
        # tz-awareness do INDEX recebido aqui, uma vez, em vez de deixar a
        # comparacao em `in_sample`/`out_of_sample` explodir com
        # `TypeError: Invalid comparison` toda vez que os dois lados
        # divergirem.
        cutoff = split.cutoff
        index_has_tz = getattr(bars.index, "tz", None) is not None
        if index_has_tz and cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(bars.index.tz)
        elif not index_has_tz and cutoff.tzinfo is not None:
            cutoff = cutoff.tz_localize(None)
        self._cutoff = cutoff

    @property
    def split(self) -> FrozenSplit:
        return self._split

    def in_sample(self) -> pd.DataFrame:
        return self._bars.loc[self._bars.index < self._cutoff]

    def out_of_sample(self) -> pd.DataFrame:
        if self._unlocked_reason is None:
            raise RuntimeError(
                "out_of_sample() travado — chame unlock(reason) explicitamente "
                f"antes de olhar o trecho a partir de {self._cutoff} "
                f"(congelado em {self._split.frozen_at}, nota: {self._split.note!r})"
            )
        return self._bars.loc[self._bars.index >= self._cutoff]

    def unlock(self, reason: str) -> None:
        if not reason:
            raise ValueError("unlock() exige um motivo explicito, nao vazio")
        self._unlocked_reason = reason
        print(f"[frozen_split] OOS desbloqueado — motivo: {reason}")
