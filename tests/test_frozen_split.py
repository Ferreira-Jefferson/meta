from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from backtest.intraday.frozen_split import LockedBars, declare_frozen_split


def _bars():
    idx = pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC")
    return pd.DataFrame({"close": range(10)}, index=idx)


def test_out_of_sample_travado_antes_de_unlock():
    split = declare_frozen_split(cutoff="2026-01-06")
    locked = LockedBars(_bars(), split)

    with pytest.raises(RuntimeError):
        locked.out_of_sample()


def test_unlock_libera_out_of_sample_e_particoes_sao_disjuntas_e_exaustivas():
    split = declare_frozen_split(cutoff="2026-01-06")
    locked = LockedBars(_bars(), split)

    locked.unlock("teste explicito")
    is_ = locked.in_sample()
    oos = locked.out_of_sample()

    assert len(is_) + len(oos) == 10
    assert is_.index.intersection(oos.index).empty
    assert (is_.index < pd.Timestamp("2026-01-06", tz="UTC")).all()
    assert (oos.index >= pd.Timestamp("2026-01-06", tz="UTC")).all()


def test_unlock_exige_motivo_nao_vazio():
    locked = LockedBars(_bars(), declare_frozen_split(cutoff="2026-01-06"))
    with pytest.raises(ValueError):
        locked.unlock("")


def test_declare_frozen_split_now_fn_injetavel_e_deterministico():
    fixo = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    split = declare_frozen_split(cutoff="2026-01-06", note="teste", now_fn=lambda: fixo)
    assert split.frozen_at == fixo
    assert split.note == "teste"
