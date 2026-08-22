"""Toda calibracao de `gremah` que promete rodar sozinha (sem
`profit_pct=`/`stop_multiplier=` explicitos) precisa de um `SymbolProfile`
em `backtest.intraday.profiles.PROFILES` -- senao `scripts/run_live.py::
build_intraday` recusa o simbolo (`ValueError`, "sem perfil economico
declarado") e o robo fica com calibracao medida mas inoperavel ao vivo.
Este teste existe para pegar essa lacuna cedo (aconteceu com CSAN3/KLBN4
em 2026-08-22 -- calibrados em `gremah.py`, esquecidos aqui)."""
from __future__ import annotations

from backtest.intraday.profiles import PROFILES
from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL


def test_todo_simbolo_calibrado_da_gremah_tem_perfil_para_operar_ao_vivo():
    faltando = set(_CALIBRATION_BY_SYMBOL) - set(PROFILES)
    assert not faltando, (
        f"simbolo(s) calibrado(s) em gremah._CALIBRATION_BY_SYMBOL sem perfil "
        f"em profiles.PROFILES (nao operam ao vivo): {sorted(faltando)}"
    )


def test_perfis_da_gremah_usam_lote_padrao_de_100_acoes():
    for symbol in _CALIBRATION_BY_SYMBOL:
        assert PROFILES[symbol].default_quantity == 100, (
            f"{symbol}: gremah so opera lote padrao (sem fracionar) -- "
            "default_quantity tem que ser 100."
        )
