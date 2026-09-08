"""Toda calibracao de `gremah` que promete rodar sozinha (sem
`profit_pct=`/`stop_multiplier=` explicitos) precisa de um `SymbolProfile`
em `backtest.intraday.profiles.PROFILES` -- senao `scripts/run_live.py::
build_intraday` recusa o simbolo (`ValueError`, "sem perfil economico
declarado") e o robo fica com calibracao medida mas inoperavel ao vivo.
Este teste existe para pegar essa lacuna cedo (aconteceu com CSAN3/KLBN4
em 2026-08-22 -- calibrados em `gremah.py`, esquecidos aqui)."""
from __future__ import annotations

import dataclasses

import pytest

from backtest.intraday.profiles import FUTURES_PROFILES, PROFILES, config_for, profile_for
from strategy.daytrade.base import (
    MARGIN_BUFFER_FUTUROS,
    RESERVA_CAIXA_SEGURANCA,
    contracts_from_capital,
    contracts_from_capital_com_reserva,
    contracts_from_capital_operacional,
)
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


# ---------- teto de contratos por CAPITAL (2026-08-26, Frente F0) ----------
# `cash_brl`/`margin_per_contract_brl` sao ADITIVOS -- todo uso EXISTENTE de
# `config_for` (sem esses dois parametros novos) tem que continuar produzindo
# o MESMO `max_open_contracts` de antes. Os testes de regressao ficam
# PRIMEIRO, deliberadamente, porque e' a garantia mais importante desta
# mudanca: nao quebrar nenhum chamador ja existente no repo.

def test_config_for_sem_cash_brl_se_comporta_exatamente_como_antes():
    """Regressao: nenhum parametro novo passado -- `max_open_contracts` sai
    do perfil, igual sempre saiu (`test_teto_de_contratos_vem_do_perfil_mas_
    e_sobrescrivivel`, acima, ja cobre isso; este teste so' torna explicito
    que adicionar `cash_brl`/`margin_per_contract_brl` na assinatura nao
    mudou o comportamento de quem nao os usa)."""
    win = config_for(profile_for("WIN@"), trade_tick_value=0.2, trade_tick_size=1.0,
                      initial_capital=1_000_000.0)
    assert win.max_open_contracts == 15  # teto oficial do perfil, sem mudanca

    wdo = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                      initial_capital=1_000_000.0)
    assert wdo.max_open_contracts == 5  # teto oficial do perfil, sem mudanca

    acao = config_for(PROFILES["PMAM3"], trade_tick_value=0.01, trade_tick_size=0.01,
                       preco_atual=1.0)
    assert acao.max_open_contracts is None  # acao continua sem teto


def test_config_for_max_open_contracts_explicito_ainda_vence_tudo():
    """Regressao: passar `max_open_contracts=` explicito continua vencendo
    o teto do perfil -- e agora tambem vence `cash_brl`/`margin_per_contract_
    brl`, mesmo que os dois estejam presentes na chamada."""
    com_folga = config_for(profile_for("WIN@"), trade_tick_value=0.2, trade_tick_size=1.0,
                            initial_capital=1_000_000.0, max_open_contracts=12)
    assert com_folga.max_open_contracts == 12

    explicito_vence_capital = config_for(
        profile_for("WIN@"), trade_tick_value=0.2, trade_tick_size=1.0,
        initial_capital=1_000_000.0, max_open_contracts=12,
        cash_brl=999_999_999.0, margin_per_contract_brl=1.0,
    )
    assert explicito_vence_capital.max_open_contracts == 12


def test_config_for_calcula_teto_por_capital_quando_cash_e_margem_passados():
    """Caminho NOVO: sem `max_open_contracts` explicito, com os dois
    parametros de capital, o teto sai de `contracts_from_capital` -- e bate
    com o mesmo numero que chamar a funcao pura direto produziria."""
    margem = 1_000.0
    caixa = margem * MARGIN_BUFFER_FUTUROS * 3  # sustenta exatamente 3 contratos
    config = config_for(
        profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=1_000_000.0, cash_brl=caixa, margin_per_contract_brl=margem,
    )
    assert config.max_open_contracts == 3
    assert config.max_open_contracts == contracts_from_capital(
        cash_brl=caixa, margin_per_contract_brl=margem, hard_cap=profile_for("WDO@").max_open_contracts,
    )


def test_config_for_teto_por_capital_nunca_passa_do_teto_oficial_do_perfil():
    """O teto OFICIAL do perfil (WDO=5) vira `hard_cap` -- caixa de sobra
    nao pode escalar o robo ALEM do que o instrumento permite."""
    config = config_for(
        profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=1_000_000.0, cash_brl=999_999_999.0, margin_per_contract_brl=1.0,
    )
    assert config.max_open_contracts == 5


def test_config_for_cash_brl_exige_margin_per_contract_brl_junto():
    with pytest.raises(ValueError):
        config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                   initial_capital=1_000_000.0, cash_brl=10_000.0)
    with pytest.raises(ValueError):
        config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                   initial_capital=1_000_000.0, margin_per_contract_brl=500.0)


def test_config_for_cash_brl_em_perfil_de_acao_e_erro_do_chamador():
    """Teto por capital nao significa nada numa acao (limitada por caixa via
    `enforce_capital_minimo`) -- misturar os dois e' erro, nunca um no-op
    silencioso."""
    with pytest.raises(ValueError):
        config_for(PROFILES["PMAM3"], trade_tick_value=0.01, trade_tick_size=0.01,
                   preco_atual=1.0, cash_brl=10_000.0, margin_per_contract_brl=500.0)


# ---------- teto DINAMICO por CAPITAL, ligado por PADRAO em futuro
# (2026-08-28, incidente REAL) -----------------------------------------------
# `wdo_grid_reload_maker` (WDO@, capital real R$300) zerou a conta ao vivo:
# a config real montada por `scripts/run_live.py::build_intraday` (que chama
# `config_for(profile, ..., initial_capital=args.capital)`, SEM nenhum dos
# parametros de capital acima) so' carregava `max_open_contracts=5` -- o
# numero REGULATORIO da Copa BTG, sem nenhuma relacao com o caixa real.
#
# `enforce_capital_cap` fecha esse buraco a partir da RAIZ: liga por padrao
# `IntradayBacktestConfig.margin_per_contract_brl` (a partir de `profile.
# margin_per_contract_brl`, ja conhecido no perfil, SEM precisar de nenhum
# parametro novo com o valor) para todo perfil de futuro -- entao QUALQUER
# chamador de `config_for` (incluindo `build_intraday`, sem precisar mudar
# uma linha de `live/`) passa a ter o teto por capital do motor
# (`IntradaySessionMachine._cap_capital_atual`) ligado, recalculado a cada
# barra contra o caixa DE VERDADE da run.

def test_enforce_capital_cap_liga_sozinho_em_futuro_com_margem_conhecida():
    """O caminho que `build_intraday` usa (sem nenhum parametro novo) -- o
    campo tem de vir preenchido, senao a operacao real continuaria exposta
    ao mesmo buraco do incidente."""
    wdo = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                      initial_capital=300.0)
    assert wdo.margin_per_contract_brl == 150.0
    assert wdo.margin_buffer == MARGIN_BUFFER_FUTUROS

    win = config_for(profile_for("WIN@"), trade_tick_value=0.2, trade_tick_size=1.0,
                      initial_capital=200.0)
    assert win.margin_per_contract_brl == 100.0


def test_enforce_capital_cap_nao_liga_em_acao():
    """Acao e' limitada por caixa via `enforce_capital_minimo`/`capital_
    minimo_brl` -- o campo tem que continuar `None`, nunca inventar um teto
    por margem que nao significa nada nesse instrumento."""
    acao = config_for(PROFILES["PMAM3"], trade_tick_value=0.01, trade_tick_size=0.01, preco_atual=1.0)
    assert acao.margin_per_contract_brl is None


def test_enforce_capital_cap_false_explicito_desliga():
    """Ambiente de margem simulada infinita (Copa BTG) ou sensibilidade
    deliberada sem o teto por caixa -- opt-out explicito continua
    disponivel."""
    config = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                        initial_capital=300.0, enforce_capital_cap=False)
    assert config.margin_per_contract_brl is None
    # o teto ESTATICO (regulatorio) continua intacto -- so' o DINAMICO desliga.
    assert config.max_open_contracts == 5


def test_enforce_capital_cap_true_sem_margem_conhecida_e_erro():
    """Pedir o teto por capital sem dado de margem no perfil e' erro do
    chamador -- nunca um 'sem teto' silencioso disfarcado de pedido
    atendido."""
    sem_margem = dataclasses.replace(profile_for("WDO@"), margin_per_contract_brl=None)
    with pytest.raises(ValueError):
        config_for(sem_margem, trade_tick_value=0.01, trade_tick_size=0.001,
                   initial_capital=300.0, enforce_capital_cap=True)


def test_enforce_capital_cap_nao_muda_o_max_open_contracts_estatico():
    """O teto ESTATICO (`max_open_contracts`, regulatorio) resolve
    exatamente como sempre resolveu -- o campo novo e' ADITIVO, nunca
    substitui o antigo (ver os testes de regressao no topo do arquivo)."""
    config = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                        initial_capital=1_000_000.0)
    assert config.max_open_contracts == 5          # inalterado
    assert config.margin_per_contract_brl == 150.0  # NOVO, aditivo


def test_enforce_capital_cap_com_capital_real_do_incidente_produz_teto_zero():
    """Leitura HONESTA do incidente sob a regra nova: R$300 no WDO@ e' o
    piso ingenuo de `MARGIN_BUFFER_FUTUROS` (sem NENHUMA folga) -- com a
    reserva de seguranca adicional (`strategy.daytrade.base.RESERVA_CAIXA_
    SEGURANCA`), o motor passa a nao autorizar nem 1 contrato nesse caixa
    exato. Nao e' um bug deste teste -- e' a mudanca de comportamento que o
    dono pediu ('caixa de seguranca sempre'), medida e reportada, nao
    escondida."""
    config = config_for(profile_for("WDO@"), trade_tick_value=0.01, trade_tick_size=0.001,
                        initial_capital=300.0)
    assert contracts_from_capital_com_reserva(
        config.initial_capital, config.margin_per_contract_brl, config.margin_buffer,
        hard_cap=config.max_open_contracts,
    ) == 0


def test_perfil_de_futuro_sem_margem_declarada_e_RECUSADO():
    """`margin_per_contract_brl` era opcional, com default `None` -- e
    `None` DESLIGA o teto de contratos por caixa
    (`IntradaySessionMachine._cap_capital_atual` devolve `None`), deixando
    valer so' `max_open_contracts`, que e' o limite REGULATORIO da Copa BTG
    e nao conhece o dinheiro do dono.

    Era exatamente esse o estado do WDO F1 no dia em que zerou a conta. Um
    perfil de futuro novo que esquecesse o argumento reproduziria o
    incidente ponto por ponto, sem erro nenhum no caminho -- entao agora
    esquecer nao e' possivel."""
    from datetime import time

    import pytest

    from backtest.intraday.profiles import _futures_profile

    with pytest.raises(ValueError, match="margin_per_contract_brl"):
        _futures_profile(
            session_end_time=time(21, 24), price_tick_size=0.5,
            max_open_contracts=5, medicao="teste",
            margin_per_contract_brl=None,
        )
    with pytest.raises(ValueError, match="margin_per_contract_brl"):
        _futures_profile(
            session_end_time=time(21, 24), price_tick_size=0.5,
            max_open_contracts=5, medicao="teste",
            margin_per_contract_brl=0.0,
        )


def test_todo_perfil_de_futuro_do_registry_declara_margem():
    """O invariante acima valendo para o que ja existe, nao so' para o que
    vier. Um perfil de futuro sem margem no registry seria um robo com teto
    de caixa desligado em producao."""
    from backtest.intraday.profiles import FUTURES_PROFILES

    futuros = {s: p for s, p in FUTURES_PROFILES.items() if p.is_futures}
    assert futuros, "premissa: ha perfil de futuro no registry"
    faltando = [s for s, p in futuros.items() if not p.margin_per_contract_brl]
    assert not faltando, f"perfil de futuro sem margem declarada: {faltando}"


# ---------- invariantes que valem para TODO robo (2026-09-08) ---------------
# Os tres testes abaixo varrem o REGISTRY em vez de citar WDO@/WIN@ na mao.
# O motivo e' o pedido do dono de 2026-09-08 -- "isso deve ser verdade para
# todos os robos, sejam os que ja existem ou os futuros": as tres correcoes
# daquele dia (piso de capital, saldo do MT5, relogio de futuro) nasceram
# olhando o WDO@, e um perfil/robo novo herdaria a versao quebrada em
# silencio se o teste fosse escrito sobre um simbolo especifico.


@pytest.mark.parametrize("symbol", sorted(FUTURES_PROFILES))
def test_todo_perfil_de_futuro_declara_a_propria_abertura(symbol):
    """Futuro NAO usa o relogio da acao. Sem `session_start_time` o robo cai
    no `clock.phase()` de acao (10:00) e perde a primeira hora do pregao --
    no WDO@ eram 149 minutos, 26,2% da sessao, onde mora o pico de atividade
    (ver `live.intraday_runtime.IntradayLiveRuntime._fase_do_instrumento`).

    Quem constroi por `_futures_profile` ganha isso de graca; o teste existe
    para o perfil montado na mao, que nao ganharia."""
    perfil = FUTURES_PROFILES[symbol]
    assert perfil.session_start_time is not None, (
        f"{symbol}: perfil de futuro sem `session_start_time` -- ao vivo ele "
        "seria gateado pelo pregao de ACAO e operaria uma janela menor que a "
        "que o backtest mede."
    )
    assert perfil.session_start_time < perfil.session_end_time


@pytest.mark.parametrize("symbol", sorted(FUTURES_PROFILES))
def test_todo_futuro_sobrevive_na_margem_crua_e_so_escala_com_a_pilha(symbol):
    """A regra do dono (2026-09-08): a pilha de seguranca governa ESCALAR,
    nunca SOBREVIVER.

    Com o caixa exatamente na margem crua o robo ainda abre 1 contrato pelo
    caminho que o motor usa (`contracts_from_capital_operacional`), e NAO
    abre pelo caminho com reserva -- e' essa diferenca que conserta o bug em
    que um unico stop derrubava o caixa abaixo do piso cheio e calava o robo
    em silencio, para sempre. Se as duas funcoes empatarem aqui, alguem
    reintroduziu a reserva no caminho de recusa."""
    margem = FUTURES_PROFILES[symbol].margin_per_contract_brl
    assert margem, "premissa: perfil de futuro declara margem"

    assert contracts_from_capital_operacional(margem, margem) == 1, (
        f"{symbol}: com a margem crua no caixa a corretora deixa segurar 1 "
        "contrato -- o motor nao pode recusar antes dela."
    )
    assert contracts_from_capital_com_reserva(margem, margem) == 0, (
        f"{symbol}: a pilha de seguranca precisa continuar recusando aqui -- "
        "e' ela que impede o 2o contrato que zerou a conta em 2026-08-28."
    )
    # Escalar continua exigindo a pilha inteira: 2 contratos so' com
    # margem x buffer x reserva x 2.
    piso_de_dois = margem * MARGIN_BUFFER_FUTUROS * RESERVA_CAIXA_SEGURANCA * 2
    assert contracts_from_capital_operacional(piso_de_dois, margem) == 2
    assert contracts_from_capital_operacional(piso_de_dois - 0.01, margem) == 1


@pytest.mark.parametrize("symbol", sorted(FUTURES_PROFILES))
def test_piso_do_dia_a_dia_fica_abaixo_do_piso_de_partida(symbol):
    """O piso cheio e' indicacao de PARTIDA, nao condicao de continuidade.

    `live.intraday_runtime.IntradayLiveRuntime._check_capital` cobra
    `margem x default_quantity` todo pregao; o painel cobra a pilha inteira
    UMA vez, no botao "Iniciar operacao" (`dashboard.robot_view.
    _capital_minimo_do_robo`). Este teste trava a ORDEM entre os dois: se o
    piso do dia-a-dia alcancar o de partida, o robo volta a se auto-barrar no
    primeiro stop -- exatamente o que o dono mandou consertar."""
    perfil = FUTURES_PROFILES[symbol]
    margem = perfil.margin_per_contract_brl
    minimo_do_dia = margem * perfil.default_quantity
    piso_de_partida = margem * MARGIN_BUFFER_FUTUROS * RESERVA_CAIXA_SEGURANCA

    assert minimo_do_dia < piso_de_partida, (
        f"{symbol}: o piso do dia-a-dia (R$ {minimo_do_dia:.2f}) alcancou o de "
        f"partida (R$ {piso_de_partida:.2f}) -- a partir dai um stop cala o robo."
    )
    assert minimo_do_dia == margem, (
        f"{symbol}: o gate diario tem que ser a margem CRUA de 1 contrato. "
        "Futuro nao opera lote de 100 -- `default_quantity` tem que ser 1."
    )
