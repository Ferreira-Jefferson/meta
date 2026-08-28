"""`CopaWin` — rompimento de faixa no mini-indice.

Cenario sintetico (AGENTS.md, "toda regra de saida/entrada em `strategy/` ->
teste com cenario sintetico"): barras construidas a mao, sem parquet e sem
MT5, para cada regra ser verificavel com valor conhecido.
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.base import (
    AdjustStop,
    Bar,
    Enter,
    EnterLimit,
    IntradayOpenPosition,
)
from strategy.daytrade.lab.copa_win import CopaWin

TICK = 5.0


def _bar(minuto: int, o, h, low, c, volume=100_000.0) -> Bar:
    ts = pd.Timestamp("2026-03-02 12:00", tz="UTC") + pd.Timedelta(minutes=minuto)
    return Bar(ts=ts, open=float(o), high=float(h), low=float(low),
               close=float(c), volume=volume)


def _robo(**kw) -> CopaWin:
    base = dict(teto_contratos=12, tick_size=TICK, janela_rompimento=5,
                aquecimento_barras=0, vol_min_ticks=1.0, trail_vol=None)
    base.update(kw)
    r = CopaWin(**base)
    r.on_session_start(pd.Timestamp("2026-03-02").date())
    return r


def _alimentar(robo: CopaWin, barras: list[Bar], posicoes=()) -> list:
    """Empurra todas menos a ultima em branco e devolve a decisao da ultima --
    o formato de "encher a faixa e ver o que ele faz na barra seguinte"."""
    for i, b in enumerate(barras[:-1]):
        robo.on_bar(b.ts, b, [], 0.0)
    ultima = barras[-1]
    return robo.on_bar(ultima.ts, ultima, list(posicoes), 0.0)


def _faixa_plana(n: int, preco: float = 140_000.0, amplitude: float = 100.0) -> list[Bar]:
    """`n` barras oscilando dentro de [preco-amplitude, preco+amplitude] --
    faixa com volatilidade suficiente para o robo aceitar operar."""
    return [_bar(i, preco, preco + amplitude, preco - amplitude, preco) for i in range(n)]


# ---------- o teto e' ENTRADA, nunca constante ------------------------------

@pytest.mark.parametrize("teto,esperado", [(4, 2), (12, 6), (15, 8), (20, 10)])
def test_a_mesma_instancia_escala_com_o_teto_sem_alterar_codigo(teto, esperado):
    """As regras de 2025 (WIN 15) podem mudar antes de 14/09/2026 -- por isso
    todo tamanho e' FRACAO do teto e nenhum literal 12/15 existe no robo."""
    assert CopaWin(teto_contratos=teto, fracao_entrada=0.5).quantidade_por_entrada == esperado


def test_fracao_pequena_nunca_produz_entrada_de_zero_contrato():
    assert CopaWin(teto_contratos=4, fracao_entrada=0.01).quantidade_por_entrada == 1


def test_teto_invalido_levanta_em_vez_de_assumir_um_numero():
    with pytest.raises(ValueError):
        CopaWin(teto_contratos=0)


# ---------- o sinal ---------------------------------------------------------

def test_rompimento_para_cima_entra_comprado_com_stop_e_alvo_na_grade_do_tick():
    robo = _robo(alvo_vol=2.0, stop_vol=1.0, fracao_entrada=0.5)
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    acoes = _alimentar(robo, barras)

    assert len(acoes) == 1 and isinstance(acoes[0], Enter)
    ordem = acoes[0]
    assert ordem.side == "long"
    assert ordem.quantity == 6                       # 12 x 0,5
    # vol de referencia = media de (high-low) das 5 barras da faixa = 200
    assert ordem.initial_stop == pytest.approx(140_300 - 200)
    assert ordem.initial_target == pytest.approx(140_300 + 400)
    # niveis na grade de 5 pontos -- um stop em 140.137 nao existe no book
    assert ordem.initial_stop % TICK == 0
    assert ordem.initial_target % TICK == 0


def test_rompimento_para_baixo_entra_vendido():
    robo = _robo()
    barras = _faixa_plana(5) + [_bar(5, 139_900, 139_950, 139_600, 139_700)]
    acoes = _alimentar(robo, barras)
    assert acoes[0].side == "short"
    assert acoes[0].initial_stop > acoes[0].initial_target


def test_preco_dentro_da_faixa_nao_gera_entrada():
    robo = _robo()
    barras = _faixa_plana(5) + [_bar(5, 140_000, 140_050, 139_950, 140_000)]
    assert _alimentar(robo, barras) == []


def test_a_propria_barra_do_sinal_nao_entra_na_faixa_contra_a_qual_e_comparada():
    """Se a barra corrente ja fosse parte da faixa, ela nunca poderia romper o
    proprio maximo -- nenhum sinal existiria."""
    robo = _robo()
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    _alimentar(robo, barras)
    assert len(robo._faixa) == 5
    assert robo._faixa[-1].high == 140_400   # so' entrou DEPOIS da decisao


def test_faixa_ainda_incompleta_nao_opera():
    robo = _robo(janela_rompimento=20)
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    assert _alimentar(robo, barras) == []


def test_volatilidade_abaixo_do_minimo_nao_opera():
    """Um "rompimento" de faixa achatada e' quantizacao do tick, nao sinal."""
    robo = _robo(vol_min_ticks=10.0)   # exige 50 pontos de amplitude media
    barras = _faixa_plana(5, amplitude=5.0) + [_bar(5, 140_000, 140_050, 140_000, 140_040)]
    assert _alimentar(robo, barras) == []


def test_aquecimento_segura_as_primeiras_barras_do_pregao():
    robo = _robo(aquecimento_barras=10)
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    assert _alimentar(robo, barras) == []


def test_teto_de_entradas_do_dia_e_respeitado():
    robo = _robo(max_entradas_dia=1)
    rompe = [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    assert len(_alimentar(robo, _faixa_plana(5) + rompe)) == 1
    # segunda tentativa, faixa ja cheia e preco rompendo de novo
    outra = _bar(6, 140_300, 140_800, 140_250, 140_700)
    assert robo.on_bar(outra.ts, outra, [], 0.0) == []


# ---------- nenhum nivel de preco atravessa a virada do pregao --------------

def test_on_session_start_apaga_a_faixa_do_pregao_anterior():
    """A serie continua `WIN@` tem emenda de rolagem que se esconde dentro do
    ruido overnight normal -- so' zerar tudo protege de operar contra um nivel
    que pertence a outro contrato."""
    robo = _robo()
    for b in _faixa_plana(5):
        robo.on_bar(b.ts, b, [], 0.0)
    assert len(robo._faixa) == 5
    robo.on_session_start(pd.Timestamp("2026-03-03").date())
    assert len(robo._faixa) == 0
    assert robo._barras_hoje == 0 and robo._entradas_hoje == 0


# ---------- trailing --------------------------------------------------------

def _posicao(side, entry, stop) -> IntradayOpenPosition:
    return IntradayOpenPosition(
        side=side, entry_ts=pd.Timestamp("2026-03-02 12:05", tz="UTC"),
        entry_price=entry, quantity=6, current_stop=stop,
        current_target=None, bars_held=3,
    )


def test_trailing_aperta_o_stop_quando_o_trade_anda_a_favor():
    robo = _robo(trail_vol=1.0)
    barras = _faixa_plana(5) + [_bar(5, 141_000, 141_100, 140_900, 141_000)]
    pos = _posicao("long", entry=140_300, stop=140_100)
    acoes = _alimentar(robo, barras, posicoes=[pos])
    assert len(acoes) == 1 and isinstance(acoes[0], AdjustStop)
    assert acoes[0].new_stop == pytest.approx(141_000 - 200)   # vol de referencia = 200


def test_trailing_nunca_afrouxa_um_stop_ja_mais_protetor():
    """O motor recusaria de qualquer jeito (`AdjustStop` so' aperta); emitir
    a acao mesmo assim so' encheria o diario de ruido."""
    robo = _robo(trail_vol=1.0)
    barras = _faixa_plana(5) + [_bar(5, 140_400, 140_450, 140_350, 140_400)]
    pos = _posicao("long", entry=140_300, stop=140_390)
    assert _alimentar(robo, barras, posicoes=[pos]) == []


def test_trail_desligado_nao_emite_nada():
    robo = _robo(trail_vol=None)
    barras = _faixa_plana(5) + [_bar(5, 141_000, 141_100, 140_900, 141_000)]
    assert _alimentar(robo, barras, posicoes=[_posicao("long", 140_300, 140_100)]) == []


def test_com_posicao_aberta_o_robo_nao_tenta_entrar_de_novo():
    robo = _robo()
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    acoes = _alimentar(robo, barras, posicoes=[_posicao("long", 140_300, 140_100)])
    assert not [a for a in acoes if isinstance(a, Enter)]


# ---------- freio diario ----------------------------------------------------

def test_perda_max_dia_e_fracao_do_teto_e_para_de_abrir():
    robo = _robo(perda_max_dia_pontos=100.0, point_value_brl=0.20)
    assert robo.perda_max_dia_brl == pytest.approx(100.0 * 0.20 * 12)
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    for b in barras[:-1]:
        robo.on_bar(b.ts, b, [], 0.0)
    ultima = barras[-1]
    assert robo.on_bar(ultima.ts, ultima, [], -1_000.0) == []


def test_freio_diario_desligado_por_padrao():
    """Funcao objetivo e' lucro total; um freio diario e' hipotese a MEDIR na
    varredura, nao premissa embutida."""
    assert CopaWin(teto_contratos=12).perda_max_dia_brl is None


# ---------- entrada por RETESTE (maker) ------------------------------------
# Medido 2026-08-25: com entrada a mercado, o custo por round-trip no WIN e'
# ~10,4 pontos por contrato contra ~10,6 pontos de edge BRUTO -- o spread da
# entrada come praticamente todo o ganho. Uma ordem PARADA no nivel rompido
# nao paga esse tick; em troca, perde o rompimento que nunca retesta.

def test_entrada_maker_deixa_ordem_parada_no_nivel_rompido():
    robo = _robo(entrada_maker=True, alvo_vol=2.0, stop_vol=1.0, fracao_entrada=0.5)
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    acoes = _alimentar(robo, barras)

    assert len(acoes) == 1 and isinstance(acoes[0], EnterLimit)
    ordem = acoes[0]
    assert ordem.side == "long"
    assert ordem.quantity == 6
    # o nivel rompido e' o teto da faixa (140.100), nao o fechamento (140.300)
    assert ordem.limit_price == pytest.approx(140_100)
    # stop e alvo saem do preco em que ele REALMENTE entraria
    assert ordem.initial_stop == pytest.approx(140_100 - 200)
    assert ordem.initial_target == pytest.approx(140_100 + 400)
    assert ordem.ttl_bars == robo.entrada_ttl_barras


def test_entrada_a_mercado_continua_ancorando_stop_e_alvo_no_fechamento():
    robo = _robo(entrada_maker=False, alvo_vol=2.0, stop_vol=1.0)
    barras = _faixa_plana(5) + [_bar(5, 140_100, 140_400, 140_050, 140_300)]
    ordem = _alimentar(robo, barras)[0]
    assert isinstance(ordem, Enter)
    assert ordem.initial_stop == pytest.approx(140_300 - 200)


def _escada(minuto0: int, n: int, preco0: float = 140_400.0,
            passo: float = 300.0) -> list[Bar]:
    """`n` barras em alta continua: cada uma FECHA acima do maximo de todas as
    anteriores, entao toda barra e' um rompimento novo. E' o cenario que
    isola o prazo da ordem -- sem ele o teste passaria por falta de sinal em
    vez de por respeito ao prazo."""
    barras = []
    preco = preco0
    for k in range(n):
        barras.append(_bar(minuto0 + k, preco, preco + passo, preco, preco + passo))
        preco += passo
    return barras


def test_reteste_nao_re_arma_antes_do_prazo():
    """Re-armar a cada barra SUBSTITUI a ordem no motor -- o `ttl_bars` nunca
    se cumpriria e a ordem ficaria eternamente no nivel mais recente."""
    robo = _robo(entrada_maker=True, entrada_ttl_barras=4)
    assert len(_alimentar(robo, _faixa_plana(5) + _escada(5, 1))) == 1
    for i, b in enumerate(_escada(6, 3, preco0=140_700.0), start=6):
        assert robo.on_bar(b.ts, b, [], 0.0) == [], f"re-armou na barra {i}"
    ultima = _escada(9, 1, preco0=141_700.0)[0]
    assert len(robo.on_bar(ultima.ts, ultima, [], 0.0)) == 1


def test_pernas_maker_conta_a_entrada_parada():
    """Multiplicador do portao G7: cobrar 1 perna numa variante com 2 fills
    maker afrouxaria justamente o desenho mais exposto a fila."""
    assert CopaWin(teto_contratos=12, entrada_maker=False).pernas_maker == 1
    assert CopaWin(teto_contratos=12, entrada_maker=True).pernas_maker == 2


# ---------- realocacao dinamica por CAPITAL (2026-08-27, aditiva/opt-in) ----
# `margin_per_contract_brl=None` (default) tem que continuar byte-a-byte
# identico ao comportamento de antes desta rodada -- nenhum teste acima foi
# alterado, e os quatro abaixo cobrem especificamente o modo novo.

def test_sem_margin_per_contract_brl_comportamento_identico_ao_de_antes():
    """Regressao: nao passar os parametros novos (ou passa-los no default)
    tem que dar o MESMO resultado de antes -- `quantidade_por_entrada` nunca
    olha `_cash_atual_brl` neste modo, mesmo que o motor chame
    `on_capital_update` com um caixa que sozinho sustentaria menos contratos."""
    robo = CopaWin(teto_contratos=12, fracao_entrada=0.5)
    assert robo.quantidade_por_entrada == 6
    robo.on_capital_update(1.0)   # caixa minusculo -- nao pode afetar nada aqui
    assert robo.quantidade_por_entrada == 6


def test_capital_baixo_encolhe_o_teto_efetivo_ate_1_contrato():
    """Com `margin_per_contract_brl` setado, um caixa que so' sustenta uma
    fracao de contrato ainda produz PELO MENOS 1 (piso), nunca 0."""
    robo = CopaWin(teto_contratos=15, fracao_entrada=1.0, margin_per_contract_brl=100.0)
    robo.on_capital_update(200.0)   # R$200 / (R$100 x buffer 2.0) = 1 contrato
    assert robo.quantidade_por_entrada == 1


def test_capital_alto_nunca_ultrapassa_o_teto_oficial_da_competicao():
    """O caixa real pode sustentar MUITO mais do que `teto_contratos` --
    a formula e' `min(teto_contratos, contracts_from_capital(...))`, entao a
    entrada nunca pode violar o teto oficial da competicao."""
    robo = CopaWin(teto_contratos=15, fracao_entrada=1.0, margin_per_contract_brl=100.0)
    robo.on_capital_update(1_000_000.0)   # caixa sustentaria centenas de contratos
    assert robo.quantidade_por_entrada == 15

    # caixa intermediario: fica ABAIXO do teto oficial, nunca acima.
    # 1000 / (100 x 2.0) = 5 contratos SEM reserva, mas `quantidade_por_
    # entrada` usa `contracts_from_capital_com_reserva` desde 2026-08-28
    # (incidente real, ver `strategy.daytrade.base.RESERVA_CAIXA_SEGURANCA`)
    # -- buffer efetivo 2.0 x 1.25 = 2.5, entao 1000 / (100 x 2.5) = 4 contratos.
    robo.on_capital_update(1_000.0)
    assert robo.quantidade_por_entrada == 4


def test_on_capital_update_nunca_chamado_ainda_produz_pelo_menos_1_contrato():
    """`_cash_atual_brl` comeca em 0.0 (estado inicial, antes de qualquer
    `on_capital_update`) -- mesmo assim `quantidade_por_entrada` nunca
    devolve 0, mesmo espirito do piso de `Gremah._lotes_por_realocacao`."""
    robo = CopaWin(teto_contratos=15, fracao_entrada=1.0, margin_per_contract_brl=100.0)
    assert robo.quantidade_por_entrada == 1
