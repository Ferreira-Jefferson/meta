"""Toda calibracao de `gremah` que promete rodar sozinha (sem
`profit_pct=`/`stop_multiplier=` explicitos) precisa de um `SymbolProfile`
em `backtest.intraday.profiles.PROFILES` -- senao `scripts/run_live.py::
build_intraday` recusa o simbolo (`ValueError`, "sem perfil economico
declarado") e o robo fica com calibracao medida mas inoperavel ao vivo.
Este teste existe para pegar essa lacuna cedo (aconteceu com CSAN3/KLBN4
em 2026-08-22 -- calibrados em `gremah.py`, esquecidos aqui)."""
from __future__ import annotations

from backtest.intraday.profiles import PROFILES, config_for
from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL
from strategy.daytrade.lab.gremah_tick import _CALIBRATION_BY_SYMBOL_TICK


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


def test_todo_simbolo_calibrado_da_gremah_tick_tem_perfil_para_operar_ao_vivo():
    """Mesma lacuna do teste acima, so' que para `_CALIBRATION_BY_SYMBOL_TICK`
    -- existia sem cobertura ate' 2026-08-23 (achado ao implementar o alvo
    por volatilidade, que toca os dois robos igual)."""
    faltando = set(_CALIBRATION_BY_SYMBOL_TICK) - set(PROFILES)
    assert not faltando, (
        f"simbolo(s) calibrado(s) em gremah_tick._CALIBRATION_BY_SYMBOL_TICK sem "
        f"perfil em profiles.PROFILES (nao operam ao vivo): {sorted(faltando)}"
    )


# ---------- enforce_capital_minimo (2026-08-23) -----------------------------
# `config_for` e' o caminho que TODO backtest/sombra real usa -- fecha a
# divergencia com `live.intraday_runtime.IntradayLiveRuntime._check_capital`,
# que ja recusava operar sem caixa suficiente. O campo em si comeca `False`
# em `IntradayBacktestConfig` (preserva testes com capital sintetico
# pequeno de proposito); e' `config_for` quem liga o padrao seguro.

def test_config_for_liga_enforce_capital_minimo_por_padrao():
    profile = PROFILES["PMAM3"]
    config = config_for(profile, trade_tick_value=0.01, trade_tick_size=0.01, preco_atual=1.0)
    assert config.enforce_capital_minimo is True


def test_config_for_pode_desligar_enforce_capital_minimo_explicitamente():
    profile = PROFILES["PMAM3"]
    config = config_for(profile, trade_tick_value=0.01, trade_tick_size=0.01, preco_atual=1.0,
                        enforce_capital_minimo=False)
    assert config.enforce_capital_minimo is False
