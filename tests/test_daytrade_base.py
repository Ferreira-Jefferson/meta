"""Contrato compartilhado da familia de day trade (`strategy/daytrade/base.py`).

Cobre `capital_minimo_brl`, que saiu de `lab/gremah.py` em 2026-08-22: a regra
"2x o custo de 1 lote" nao e' de UM robo, vale para qualquer robo intradiario
que opere lote padrao sem fracionario -- e `live/intraday_runtime.py` precisa
consultar a MESMA funcao que a ficha exibe e que dimensionou o capital de todo
backtest da tabela de calibracao (AGENTS.md #6: `live/` aplica regra
declarada, nunca inventa a propria).
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.base import (
    CAPITAL_MINIMO_EM_LOTES,
    LOTE_PADRAO_B3,
    MARGIN_BUFFER_FUTUROS,
    RESERVA_CAIXA_SEGURANCA,
    Bar,
    JanelaVolatilidadeDiaria,
    RollingVolumeWindow,
    barra_diaria,
    capital_minimo_brl,
    contracts_from_capital,
    contracts_from_capital_com_reserva,
    contracts_from_capital_operacional,
)


def test_capital_minimo_e_o_dobro_do_custo_de_um_lote():
    """Regra do dono, 2026-08-22, com o exemplo que ele deu: PMAM3 a R$0,14
    -> lote de R$14,00 -> minimo R$28,00."""
    assert capital_minimo_brl(0.14) == pytest.approx(28.0)
    assert capital_minimo_brl(3.64) == pytest.approx(728.0)   # CSAN3
    assert capital_minimo_brl(151.95) == pytest.approx(30_390.0)  # CLSC4


def test_capital_minimo_acompanha_o_preco_sem_arredondar():
    """Substituiu (2026-08-22) a regra de arredondar pra cima ao proximo
    multiplo de R$50, que dava folga absurdamente desigual conforme o preco
    (PMAM3 R$14 -> R$50 era 3,6x o lote; CSAN3 R$364 -> R$400, so 1,1x).
    Agora a proporcao e' a MESMA em qualquer preco, e por isso um centavo a
    mais no preco move o minimo -- e' o comportamento pretendido, ja que o
    piso e' reavaliado a cada pregao."""
    assert capital_minimo_brl(1.00) == pytest.approx(200.0)
    assert capital_minimo_brl(1.01) == pytest.approx(202.0)
    for preco in (0.09, 0.5, 3.66, 5.08, 75.09):
        assert capital_minimo_brl(preco) % 50 != 0 or preco in (0.5,)


def test_capital_minimo_usa_o_lote_que_o_robo_de_fato_negocia():
    """`shares_per_lot` nao e' decoracao: quem chama ao vivo passa
    `config.default_quantity` (a quantidade que o robo realmente manda por
    ordem), para o piso cobrir o que sera' comprado -- nao um lote de
    referencia que nao corresponde a ordem."""
    assert capital_minimo_brl(2.00, shares_per_lot=100) == pytest.approx(400.0)
    assert capital_minimo_brl(2.00, shares_per_lot=200) == pytest.approx(800.0)
    assert capital_minimo_brl(2.00) == capital_minimo_brl(2.00, shares_per_lot=LOTE_PADRAO_B3)


def test_constantes_declaradas_batem_com_a_formula():
    """Se alguem mudar `CAPITAL_MINIMO_EM_LOTES` sem querer, isto pega -- a
    formula e as constantes nao podem divergir em silencio."""
    assert CAPITAL_MINIMO_EM_LOTES == pytest.approx(2.0)
    assert LOTE_PADRAO_B3 == 100
    assert capital_minimo_brl(7.0) == pytest.approx(7.0 * LOTE_PADRAO_B3 * CAPITAL_MINIMO_EM_LOTES)


# ---------- RollingVolumeWindow (2026-08-22, pedido do dono: media movel --
# substitui o teto de posicao antigo, congelado no primeiro minuto/janela
# inicial do pregao) --------------------------------------------------------

def _bar(ts: pd.Timestamp, volume: float) -> Bar:
    return Bar(ts=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=volume)


def test_media_por_minuto_sem_cauda_e_conservadora_ate_a_janela_encher():
    """Sem cauda do pregao anterior, minutos ainda nao vividos hoje contam
    como volume ZERO -- divide SEMPRE pela janela NOMINAL (30min por
    default), nunca so' pelo tempo decorrido. E' o lado seguro: superestimar
    o teto de posicao e' o erro caro (o book real nao absorve uma ordem
    grande demais), subestimar so' custa lote a menos."""
    janela = RollingVolumeWindow(janela_minutos=30.0)
    janela.iniciar_sessao()
    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    janela.registrar(t0, 3000.0)  # 1 unico evento, 0min decorridos

    assert janela.media_por_minuto(t0) == pytest.approx(3000.0 / 30.0)


def test_media_por_minuto_com_janela_cheia_e_a_media_de_verdade():
    janela = RollingVolumeWindow(janela_minutos=30.0)
    janela.iniciar_sessao()
    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    for i in range(30):
        janela.registrar(t0 + pd.Timedelta(minutes=i), 100.0)

    ts_final = t0 + pd.Timedelta(minutes=29)
    assert janela.media_por_minuto(ts_final) == pytest.approx(100.0)


def test_evicta_eventos_mais_velhos_que_a_propria_janela():
    """Um pico isolado bem antigo nao pode continuar inflando a media
    depois de sair da janela -- so' os eventos DENTRO dela contam."""
    janela = RollingVolumeWindow(janela_minutos=10.0)
    janela.iniciar_sessao()
    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    janela.registrar(t0, 100_000.0)  # pico isolado
    for i in range(1, 11):
        janela.registrar(t0 + pd.Timedelta(minutes=i), 10.0)
    ts_final = t0 + pd.Timedelta(minutes=11)
    janela.registrar(ts_final, 10.0)  # 11min depois do pico -- ja saiu da janela de 10min

    assert janela.media_por_minuto(ts_final) == pytest.approx(10.0)


def test_cauda_do_pregao_anterior_completa_o_deficit_na_abertura():
    """Pedido literal do dono: 'na abertura ele considera tambem as ultimas
    barras do dia anterior' -- sem os 30min de hoje ainda vividos, a media
    usa o final REAL do pregao anterior em vez de assumir volume zero."""
    janela = RollingVolumeWindow(janela_minutos=30.0)
    ontem_fim = pd.Timestamp("2026-01-05 20:55:00", tz="UTC")
    cauda = [_bar(ontem_fim - pd.Timedelta(minutes=m), 100.0) for m in range(29, -1, -1)]
    janela.definir_cauda_anterior(cauda)  # 30 barras x 100 acoes = 3000 no total
    janela.iniciar_sessao()

    hoje_abertura = pd.Timestamp("2026-01-06 13:00:00", tz="UTC")
    janela.registrar(hoje_abertura, 500.0)

    # 0min decorridos hoje -- deficit inteiro (30min) vem da cauda.
    assert janela.media_por_minuto(hoje_abertura) == pytest.approx((3000.0 + 500.0) / 30.0)


def test_cauda_para_de_ser_usada_assim_que_hoje_acumula_a_janela_inteira():
    janela = RollingVolumeWindow(janela_minutos=5.0)
    ontem_fim = pd.Timestamp("2026-01-05 20:55:00", tz="UTC")
    janela.definir_cauda_anterior([_bar(ontem_fim, 999_999.0)])  # pico enorme
    janela.iniciar_sessao()

    hoje_abertura = pd.Timestamp("2026-01-06 13:00:00", tz="UTC")
    for i in range(6):
        janela.registrar(hoje_abertura + pd.Timedelta(minutes=i), 100.0)
    ts_final = hoje_abertura + pd.Timedelta(minutes=5)  # 5min decorridos == janela inteira

    # decorrido (5min) NAO e' menor que a janela (5min) -- cauda ignorada,
    # o pico de ontem nao pode mais aparecer na media.
    assert janela.media_por_minuto(ts_final) == pytest.approx(100.0)


def test_definir_cauda_pode_vir_antes_ou_depois_de_iniciar_sessao():
    """As duas ordens de chamada tem que produzir o MESMO resultado -- ao
    vivo a cauda e' buscada no INICIO de `_start_session`, antes do warm
    start decidir cold vs quente; no backtest e' antes de `begin_session`."""
    ontem_fim = pd.Timestamp("2026-01-05 20:55:00", tz="UTC")
    cauda = [_bar(ontem_fim, 1000.0)]
    hoje = pd.Timestamp("2026-01-06 13:00:00", tz="UTC")

    antes = RollingVolumeWindow(janela_minutos=30.0)
    antes.definir_cauda_anterior(cauda)
    antes.iniciar_sessao()

    depois = RollingVolumeWindow(janela_minutos=30.0)
    depois.iniciar_sessao()
    depois.definir_cauda_anterior(cauda)

    assert antes.media_por_minuto(hoje) == pytest.approx(depois.media_por_minuto(hoje))


def test_cauda_vazia_e_o_default_seguro():
    """`definir_cauda_anterior([])` (primeiro pregao do historico, ou feed
    sem dado do dia anterior) tem que se comportar EXATAMENTE como nunca
    ter sido chamado -- nunca um erro, nunca um valor inventado."""
    com_chamada_vazia = RollingVolumeWindow(janela_minutos=30.0)
    com_chamada_vazia.definir_cauda_anterior([])
    com_chamada_vazia.iniciar_sessao()

    sem_chamada = RollingVolumeWindow(janela_minutos=30.0)
    sem_chamada.iniciar_sessao()

    t0 = pd.Timestamp("2026-01-05 13:00:00", tz="UTC")
    com_chamada_vazia.registrar(t0, 900.0)
    sem_chamada.registrar(t0, 900.0)

    assert com_chamada_vazia.media_por_minuto(t0) == pytest.approx(sem_chamada.media_por_minuto(t0))


# ---------- barra_diaria / JanelaVolatilidadeDiaria (2026-08-23, alvo por
# volatilidade em vez de percentual do preco -- ver `strategy.daytrade.lab.
# gremah`/`gremah_tick`) -------------------------------------------------

def _bar_ohlc(hhmm: str, o, h, low, c) -> Bar:
    return Bar(ts=pd.Timestamp(f"2026-01-05 {hhmm}", tz="UTC"),
               open=float(o), high=float(h), low=float(low), close=float(c), volume=100.0)


def test_barra_diaria_agrega_ohlc_da_sessao_inteira():
    barras = [
        _bar_ohlc("13:00", 10.0, 10.5, 9.8, 10.2),
        _bar_ohlc("13:01", 10.2, 11.0, 10.1, 10.9),
        _bar_ohlc("13:02", 10.9, 10.9, 9.5, 9.6),
    ]
    diaria = barra_diaria(barras)
    assert diaria.open == pytest.approx(10.0)      # da PRIMEIRA barra
    assert diaria.high == pytest.approx(11.0)       # max de todas
    assert diaria.low == pytest.approx(9.5)         # min de todas
    assert diaria.close == pytest.approx(9.6)       # da ULTIMA barra
    assert diaria.volume == pytest.approx(300.0)    # soma
    assert diaria.ts == barras[-1].ts


def test_barra_diaria_vazia_e_none():
    assert barra_diaria([]) is None


def test_janela_volatilidade_vazia_devolve_none():
    janela = JanelaVolatilidadeDiaria(janela_dias=10)
    assert janela.range_mediano() is None


def test_janela_volatilidade_e_a_mediana_do_range_diario():
    janela = JanelaVolatilidadeDiaria(janela_dias=5)
    for rng in (3.0, 5.0, 100.0, 4.0, 6.0):  # mediana = 5.0, 100.0 e' outlier
        janela.registrar_dia(_bar_ohlc("18:00", 10.0, 10.0 + rng, 10.0, 10.0))
    assert janela.range_mediano() == pytest.approx(5.0)


def test_janela_volatilidade_descarta_alem_do_tamanho_declarado():
    """So' as ultimas `janela_dias` sessoes contam -- um pregao antigo demais
    nao pode continuar influenciando a mediana."""
    janela = JanelaVolatilidadeDiaria(janela_dias=3)
    janela.registrar_dia(_bar_ohlc("18:00", 10.0, 1_000.0, 10.0, 10.0))  # sai da janela
    for rng in (1.0, 2.0, 3.0):
        janela.registrar_dia(_bar_ohlc("18:00", 10.0, 10.0 + rng, 10.0, 10.0))
    assert janela.range_mediano() == pytest.approx(2.0)


# ---------- contracts_from_capital (2026-08-26, Frente F0 -- equivalente de
# `capital_minimo_brl` para FUTURO: o limitador de tamanho e' MARGEM por
# contrato, nao caixa por lote) ----------------------------------------------

def test_contracts_from_capital_zero_quando_nao_cobre_1_contrato():
    """Caixa abaixo de `margin * buffer` nao sustenta nem 1 contrato -- 0,
    nunca negativo, nunca um erro (o robo so' espera ter caixa, mesmo
    espirito de `enforce_capital_minimo` recusando o pregao)."""
    assert contracts_from_capital(cash_brl=100.0, margin_per_contract_brl=1_000.0) == 0
    assert contracts_from_capital(cash_brl=0.0, margin_per_contract_brl=1_000.0) == 0
    assert contracts_from_capital(cash_brl=-50.0, margin_per_contract_brl=1_000.0) == 0


def test_contracts_from_capital_exatamente_1_contrato():
    """Caixa exatamente igual a `margin * buffer` sustenta 1 contrato --
    testa a tolerancia de ponto flutuante do `floor` (1.0 exato nao pode
    truncar para 0 por erro de representacao binaria, o classico `1000.0 /
    500.0` que pode virar `1.9999999999998` num calculo intermediario)."""
    margem = 500.0
    caixa_exata = margem * MARGIN_BUFFER_FUTUROS
    assert contracts_from_capital(cash_brl=caixa_exata, margin_per_contract_brl=margem) == 1
    # um centavo A MENOS de verdade nao fecha o contrato -- fica em 0
    assert contracts_from_capital(cash_brl=caixa_exata - 0.01, margin_per_contract_brl=margem) == 0
    # um centavo A MAIS nao e' o suficiente para abrir um 2o (precisaria do dobro)
    assert contracts_from_capital(cash_brl=caixa_exata + 0.01, margin_per_contract_brl=margem) == 1
    # caso classico de erro de ponto flutuante: 3 x (margem*buffer) construido
    # por soma repetida pode ficar a 1 ULP abaixo do valor exato -- ainda tem
    # que fechar 3 contratos, nao 2.
    caixa_por_soma = sum([margem * MARGIN_BUFFER_FUTUROS] * 3)
    assert contracts_from_capital(cash_brl=caixa_por_soma, margin_per_contract_brl=margem) == 3


def test_contracts_from_capital_varios_contratos_escala_com_o_caixa():
    margem = 500.0
    assert contracts_from_capital(cash_brl=margem * MARGIN_BUFFER_FUTUROS * 3, margin_per_contract_brl=margem) == 3
    assert contracts_from_capital(cash_brl=margem * MARGIN_BUFFER_FUTUROS * 3.9, margin_per_contract_brl=margem) == 3
    assert contracts_from_capital(cash_brl=margem * MARGIN_BUFFER_FUTUROS * 10, margin_per_contract_brl=margem) == 10


def test_contracts_from_capital_hard_cap_realmente_limita():
    """Mesmo com caixa de sobra, `hard_cap` e' o teto -- e' o encaixe com o
    teto OFICIAL de um instrumento (`SymbolProfile.max_open_contracts`,
    ex.: 15 no WIN, 5 no WDO): o robo escala com o capital, mas nunca alem
    do que o instrumento/regulamento permite."""
    assert contracts_from_capital(
        cash_brl=1_000_000.0, margin_per_contract_brl=500.0, hard_cap=5,
    ) == 5
    # hard_cap so' LIMITA -- nunca aumenta alem do que o caixa sustentaria
    assert contracts_from_capital(
        cash_brl=500.0 * MARGIN_BUFFER_FUTUROS, margin_per_contract_brl=500.0, hard_cap=99,
    ) == 1
    assert contracts_from_capital(
        cash_brl=1_000_000.0, margin_per_contract_brl=500.0, hard_cap=None,
    ) > 5


def test_contracts_from_capital_buffer_customizado_sobrescreve_o_default():
    """Quem tiver dado real de margem/chamada de margem (ver docstring de
    `MARGIN_BUFFER_FUTUROS`) pode calibrar um `buffer` proprio -- o default
    e' so' o ponto de partida seguro, nao uma constante travada."""
    margem = 1_000.0
    com_buffer_1x = contracts_from_capital(cash_brl=margem, margin_per_contract_brl=margem, buffer=1.0)
    assert com_buffer_1x == 1
    com_buffer_default = contracts_from_capital(cash_brl=margem, margin_per_contract_brl=margem)
    assert com_buffer_default == 0  # o default (2x) exige o dobro para o mesmo caixa


def test_contracts_from_capital_rejeita_margem_ou_buffer_nao_positivos():
    with pytest.raises(ValueError):
        contracts_from_capital(cash_brl=10_000.0, margin_per_contract_brl=0.0)
    with pytest.raises(ValueError):
        contracts_from_capital(cash_brl=10_000.0, margin_per_contract_brl=-500.0)
    with pytest.raises(ValueError):
        contracts_from_capital(cash_brl=10_000.0, margin_per_contract_brl=500.0, buffer=0.0)


# ---------- contracts_from_capital_com_reserva (2026-08-28, incidente REAL --
# `wdo_grid_reload_maker` zerou a conta ao vivo com WDO@/R$300 abrindo 2
# contratos simultaneos; ver a docstring de `RESERVA_CAIXA_SEGURANCA`) -------

def test_reserva_reproduz_exatamente_o_incidente_wdo_r300():
    """O numero do incidente: WDO@ a R$300, margem R$150 -- SEM reserva
    (`contracts_from_capital` puro) da' exatamente 1 contrato, zero folga.
    COM a reserva, o mesmo caixa nao fecha nem 1 -- e' a leitura honesta de
    que R$300 opera exatamente na borda, sem nenhuma margem de erro."""
    assert contracts_from_capital(cash_brl=300.0, margin_per_contract_brl=150.0) == 1
    assert contracts_from_capital_com_reserva(cash_brl=300.0, margin_per_contract_brl=150.0) == 0


def test_reserva_e_buffer_compoem_por_multiplicacao():
    """`contracts_from_capital_com_reserva` e' `contracts_from_capital` com
    `buffer x reserva` no lugar de `buffer` -- mesma mecanica/tolerancia de
    ponto flutuante, testada aqui so' pela composicao dos dois fatores."""
    margem = 1_000.0
    buffer = 2.0
    reserva = 1.25
    caixa = margem * buffer * reserva * 4  # sustenta exatamente 4 contratos com os dois fatores
    assert contracts_from_capital_com_reserva(
        cash_brl=caixa, margin_per_contract_brl=margem, buffer=buffer, reserva=reserva,
    ) == 4
    assert contracts_from_capital_com_reserva(
        cash_brl=caixa, margin_per_contract_brl=margem, buffer=buffer, reserva=reserva,
    ) == contracts_from_capital(cash_brl=caixa, margin_per_contract_brl=margem, buffer=buffer * reserva)


def test_reserva_default_e_a_constante_do_modulo():
    """Nao passar `reserva` usa `RESERVA_CAIXA_SEGURANCA` -- garante que o
    default nao pode divergir silenciosamente da constante documentada."""
    assert contracts_from_capital_com_reserva(cash_brl=10_000.0, margin_per_contract_brl=1_000.0) == \
        contracts_from_capital_com_reserva(cash_brl=10_000.0, margin_per_contract_brl=1_000.0,
                                            reserva=RESERVA_CAIXA_SEGURANCA)


def test_reserva_hard_cap_continua_funcionando():
    """`hard_cap` viaja intacto para `contracts_from_capital` -- a reserva
    nao muda essa mecanica (o teto oficial do instrumento continua sendo o
    teto, independente de quanto caixa sobra)."""
    assert contracts_from_capital_com_reserva(
        cash_brl=1_000_000.0, margin_per_contract_brl=150.0, hard_cap=5,
    ) == 5


def test_reserva_nunca_devolve_mais_contratos_que_a_versao_pura():
    """Para QUALQUER caixa, a versao com reserva e' <= a versao pura -- a
    reserva so' pode ENCOLHER a capacidade calculada, nunca aumenta-la
    (verificado numa faixa de caixas, nao so' um ponto)."""
    margem = 150.0
    for caixa in (0.0, 100.0, 299.0, 300.0, 301.0, 900.0, 10_000.0, 1_000_000.0):
        crua = contracts_from_capital(cash_brl=caixa, margin_per_contract_brl=margem)
        com_reserva = contracts_from_capital_com_reserva(cash_brl=caixa, margin_per_contract_brl=margem)
        assert com_reserva <= crua


# ---------- contracts_from_capital_operacional (2026-09-08, decisao do dono:
# a pilha de seguranca governa ESCALAR, nao SOBREVIVER) ---------------------
# O piso cheio (`margem x buffer x reserva` = R$375 no WDO@) e' a INDICACAO de
# quanto e' preciso para COMECAR, checada 1x no painel. Estava sendo cobrado
# tambem para o 1o contrato, a cada entrada, para sempre -- um stop de R$80
# sobre R$375 derrubava o caixa para R$299 e calava o robo em silencio.

def test_operacional_mantem_1_contrato_na_faixa_entre_margem_crua_e_pilha_cheia():
    """O caso que motivou a funcao: R$299 no WDO@ (margem R$150). A pilha
    cheia nao autoriza nem 1 contrato (piso R$375), mas a corretora sustenta
    1 (margem crua R$150) -- e' esse contrato que mantem o robo VIVO."""
    assert contracts_from_capital_com_reserva(cash_brl=299.0, margin_per_contract_brl=150.0) == 0
    assert contracts_from_capital_operacional(cash_brl=299.0, margin_per_contract_brl=150.0) == 1


def test_operacional_nunca_autoriza_o_2o_contrato_pela_margem_crua():
    """A protecao do incidente de 2026-08-28 fica INTACTA: escalar exige a
    pilha inteira. R$740 sustentaria 4 contratos pela margem crua e 2 pelo
    buffer puro, mas so' 1 com buffer x reserva (375/contrato) -- e o
    operacional tem de concordar com a pilha, nao com a margem."""
    assert contracts_from_capital(cash_brl=740.0, margin_per_contract_brl=150.0, buffer=1.0) == 4
    assert contracts_from_capital(cash_brl=740.0, margin_per_contract_brl=150.0) == 2
    assert contracts_from_capital_operacional(cash_brl=740.0, margin_per_contract_brl=150.0) == 1
    # e a partir de 2 x 375 ele libera o segundo, igual a versao com reserva
    assert contracts_from_capital_operacional(cash_brl=750.0, margin_per_contract_brl=150.0) == 2


def test_operacional_abaixo_da_margem_crua_devolve_zero():
    """Abaixo da margem que a corretora cobra nao ha' sobrevivencia nenhuma
    -- quem recusaria ali e' a propria corretora."""
    assert contracts_from_capital_operacional(cash_brl=149.99, margin_per_contract_brl=150.0) == 0
    assert contracts_from_capital_operacional(cash_brl=0.0, margin_per_contract_brl=150.0) == 0
    assert contracts_from_capital_operacional(cash_brl=-50.0, margin_per_contract_brl=150.0) == 0
    # exatamente a margem crua ja' sustenta 1 (mesma tolerancia de ponto
    # flutuante que `contracts_from_capital` aplica)
    assert contracts_from_capital_operacional(cash_brl=150.0, margin_per_contract_brl=150.0) == 1


def test_operacional_respeita_hard_cap_zero():
    """`hard_cap` e' teto duro por cima de tudo -- nao existe 'sobrevivencia'
    acima de um teto que proibe qualquer contrato."""
    assert contracts_from_capital_operacional(
        cash_brl=1_000_000.0, margin_per_contract_brl=150.0, hard_cap=0,
    ) == 0
    assert contracts_from_capital_operacional(
        cash_brl=299.0, margin_per_contract_brl=150.0, hard_cap=0,
    ) == 0


def test_operacional_e_identico_a_versao_com_reserva_sempre_que_ela_autoriza_1():
    """A funcao so' pode DIFERIR no ponto em que a pilha cheia devolve 0.
    Acima disso as duas tem de dar exatamente o mesmo numero, senao existiriam
    duas regras de escala concorrentes."""
    margem = 150.0
    for caixa in (0.0, 100.0, 149.0, 150.0, 299.0, 375.0, 400.0, 750.0, 10_000.0):
        com_reserva = contracts_from_capital_com_reserva(
            cash_brl=caixa, margin_per_contract_brl=margem)
        operacional = contracts_from_capital_operacional(
            cash_brl=caixa, margin_per_contract_brl=margem)
        if com_reserva >= 1:
            assert operacional == com_reserva
        else:
            assert operacional in (0, 1)
            # e nunca mais que a margem crua permite
            assert operacional <= contracts_from_capital(
                cash_brl=caixa, margin_per_contract_brl=margem, buffer=1.0)
