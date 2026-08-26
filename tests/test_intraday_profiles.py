"""Toda calibracao de `gremah` que promete rodar sozinha (sem
`profit_pct=`/`stop_multiplier=` explicitos) precisa de um `SymbolProfile`
em `backtest.intraday.profiles.PROFILES` -- senao `scripts/run_live.py::
build_intraday` recusa o simbolo (`ValueError`, "sem perfil economico
declarado") e o robo fica com calibracao medida mas inoperavel ao vivo.
Este teste existe para pegar essa lacuna cedo (aconteceu com CSAN3/KLBN4
em 2026-08-22 -- calibrados em `gremah.py`, esquecidos aqui)."""
from __future__ import annotations

import pytest

from backtest.intraday.profiles import FUTURES_PROFILES, PROFILES, config_for, profile_for
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
# `config_for` e' o caminho que TODO backtest/sombra real usa -- historicamente
# a mesma regra que `live.intraday_runtime.IntradayLiveRuntime._check_capital`
# aplicava ao vivo (2x o lote); desde 2026-08-24 o gate diario ao vivo caiu
# para 1x (o 2x agora so' vale na ENTRADA, ver `live_control.start`), mas o
# flag de backtest continua em 2x -- dimensiona a calibracao, nao decide se um
# robo ja rodando pode continuar. O campo em si comeca `False` em
# `IntradayBacktestConfig` (preserva testes com capital sintetico pequeno de
# proposito); e' `config_for` quem liga o padrao seguro.

def test_config_for_liga_enforce_capital_minimo_por_padrao():
    profile = PROFILES["PMAM3"]
    config = config_for(profile, trade_tick_value=0.01, trade_tick_size=0.01, preco_atual=1.0)
    assert config.enforce_capital_minimo is True


def test_config_for_pode_desligar_enforce_capital_minimo_explicitamente():
    profile = PROFILES["PMAM3"]
    config = config_for(profile, trade_tick_value=0.01, trade_tick_size=0.01, preco_atual=1.0,
                        enforce_capital_minimo=False)
    assert config.enforce_capital_minimo is False


# ---------- mini-futuros (familia `copa`, 2026-08-25) ----------------------
# Tabela SEPARADA de `PROFILES` de proposito (ver o comentario de
# `FUTURES_PROFILES`): os dois testes de cobertura acima leem cada entrada de
# `PROFILES` assumindo acao em lote de 100 com calibracao `gremah` -- um
# futuro nao tem nenhuma das tres coisas.

def test_futuro_nao_entra_na_tabela_de_acoes():
    assert not (set(FUTURES_PROFILES) & set(PROFILES))


def test_profile_for_resolve_as_duas_tabelas():
    assert profile_for("PMAM3") is PROFILES["PMAM3"]
    assert profile_for("WIN@") is FUTURES_PROFILES["WIN@"]


def test_profile_for_levanta_para_simbolo_sem_perfil():
    """Nunca um default silencioso: operar com custo/horario de outro
    instrumento e' pior que nao operar."""
    with pytest.raises(KeyError):
        profile_for("NAO_EXISTE")


def test_futuro_opera_em_contrato_nao_em_lote_de_100():
    for symbol, profile in FUTURES_PROFILES.items():
        assert profile.default_quantity == 1, symbol
        assert profile.session_end_policy == "fixed", symbol
        assert profile.exchange_fee_pct_per_leg == 0.0, symbol
        assert profile.fee_round_trip_brl > 0.0, symbol


def test_override_de_tick_corrige_a_grade_de_preco_sem_mexer_no_valor_do_ponto():
    """A serie continua `WIN@` reporta `trade_tick_size=1.0`, mas o contrato
    cheio (`WINV26`) negocia de 5 em 5 pontos -- medido no terminal em
    2026-08-25. Sem o override, o robo colocaria ordem-limite num preco que
    nao existe no book. O `point_value_brl` NAO pode mudar junto: e' ele que
    converte ponto em real, e mexer nele reescreveria o P&L inteiro."""
    win = config_for(profile_for("WIN@"), trade_tick_value=0.2, trade_tick_size=1.0,
                     initial_capital=1_000_000.0)
    assert win.costs.tick_size == 5.0
    assert win.costs.point_value_brl == pytest.approx(0.20)

    wdo = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                     initial_capital=1_000_000.0)
    assert wdo.costs.tick_size == 0.5
    assert wdo.costs.point_value_brl == pytest.approx(10.0)


def test_teto_de_contratos_vem_do_perfil_mas_e_sobrescrivivel():
    """Os numeros de 2025 (WIN 15 / WDO 5) podem mudar antes da competicao de
    2026 -- por isso o teto e' ENTRADA de configuracao, e o teste com folga
    (12/4) usa o mesmo caminho, sem tocar em codigo de estrategia."""
    oficial = config_for(profile_for("WIN@"), trade_tick_value=0.2, trade_tick_size=1.0,
                         initial_capital=1_000_000.0)
    assert oficial.max_open_contracts == 15

    com_folga = config_for(profile_for("WIN@"), trade_tick_value=0.2, trade_tick_size=1.0,
                           initial_capital=1_000_000.0, max_open_contracts=12)
    assert com_folga.max_open_contracts == 12


def test_futuro_nao_liga_o_gate_de_capital_minimo():
    """`capital_minimo_brl` e' o custo de 2 lotes de 100 ACOES -- nao
    significa nada num ambiente de margem infinita, onde o limitador e' o
    teto de contratos. Acao continua ligando por padrao."""
    futuro = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                        initial_capital=1_000_000.0)
    assert futuro.enforce_capital_minimo is False

    acao = config_for(PROFILES["PMAM3"], trade_tick_value=0.01, trade_tick_size=0.01,
                      preco_atual=1.0)
    assert acao.enforce_capital_minimo is True

    # explicito sempre vence os dois defaults
    forcado = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                         initial_capital=1_000_000.0, enforce_capital_minimo=True)
    assert forcado.enforce_capital_minimo is True
