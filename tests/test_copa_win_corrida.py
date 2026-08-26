"""`CopaWinCorrida` — segue a corrida de barras M1 no mesmo sentido.

Cenario sintetico (AGENTS.md, "toda regra de saida/entrada em `strategy/` ->
teste com cenario sintetico"): barras construidas a mao, sem parquet e sem
MT5, para cada regra ser verificavel com valor conhecido. Mesmo estilo de
`tests/test_copa_win.py`.
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.daytrade.base import Bar, Enter, Exit, IntradayOpenPosition
from strategy.daytrade.lab.copa_win_corrida import CopaWinCorrida


def _bar(minuto: int, close: float, dia: str = "2026-03-02") -> Bar:
    """Barra degenerada (open=high=low=close) — este robo so olha `close`
    (a definicao de corrida e' sobre `close_t - close_{t-1}`), entao OHLC
    identico nao esconde nenhum comportamento sob teste."""
    ts = pd.Timestamp(f"{dia} 12:00", tz="UTC") + pd.Timedelta(minutes=minuto)
    return Bar(ts=ts, open=close, high=close, low=close, close=close, volume=1_000.0)


def _robo(**kw) -> CopaWinCorrida:
    base = dict(teto_contratos=12, confirmacao_barras=3, fracao_entrada=1.0)
    base.update(kw)
    r = CopaWinCorrida(**base)
    r.on_session_start(pd.Timestamp("2026-03-02").date())
    return r


def _posicao(side: str, entry: float) -> IntradayOpenPosition:
    return IntradayOpenPosition(
        side=side, entry_ts=pd.Timestamp("2026-03-02 12:05", tz="UTC"),
        entry_price=entry, quantity=6, current_stop=None, current_target=None,
        bars_held=1,
    )


# ---------- o teto e' ENTRADA, nunca constante ------------------------------

@pytest.mark.parametrize("teto,esperado", [(4, 2), (12, 6), (15, 8), (20, 10)])
def test_a_mesma_instancia_escala_com_o_teto_sem_alterar_codigo(teto, esperado):
    """As regras de 2025 (WIN 15) podem mudar antes de 14/09/2026 -- por isso
    todo tamanho e' FRACAO do teto e nenhum literal 12/15 existe no robo."""
    assert CopaWinCorrida(teto_contratos=teto, fracao_entrada=0.5).quantidade_por_entrada == esperado


def test_fracao_pequena_nunca_produz_entrada_de_zero_contrato():
    assert CopaWinCorrida(teto_contratos=4, fracao_entrada=0.01).quantidade_por_entrada == 1


def test_teto_invalido_levanta_em_vez_de_assumir_um_numero():
    with pytest.raises(ValueError):
        CopaWinCorrida(teto_contratos=0)


def test_confirmacao_barras_invalida_levanta():
    with pytest.raises(ValueError):
        CopaWinCorrida(teto_contratos=12, confirmacao_barras=0)


# ---------- definicao de corrida --------------------------------------------

def test_primeira_barra_do_pregao_nao_gera_diff_nem_decisao():
    """Sem `close_{t-1}` dentro do pregao, nao ha o que comparar -- a
    primeira barra so serve para estabelecer a referencia."""
    robo = _robo()
    b0 = _bar(0, 100_000.0)
    assert robo.on_bar(b0.ts, b0, [], 0.0) == []
    assert robo._run_len == 0 and robo._run_dir == 0


def test_barra_de_retorno_zero_nao_quebra_nem_estende_a_corrida():
    """Mesma convencao da medicao: barra com `close_t == close_{t-1}` fica
    fora da analise direcional -- nem soma, nem reseta."""
    robo = _robo(confirmacao_barras=3)
    # seed, +1 (len1), +1 (len2), 0 (fica em len2, sem decisao), +1 (len3 -> entra)
    precos = [100_000.0, 100_100.0, 100_200.0, 100_200.0, 100_300.0]
    decisoes = [robo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(precos)]
    assert all(d == [] for d in decisoes[:-1]), "entrou antes da corrida confirmar 3 barras"
    assert len(decisoes[-1]) == 1 and isinstance(decisoes[-1][0], Enter)
    assert decisoes[-1][0].side == "long"
    assert robo._run_len == 3


def test_corrida_de_baixa_reconhecida_simetricamente():
    robo = _robo(confirmacao_barras=2)
    precos = [100_000.0, 99_900.0, 99_800.0]  # seed, -1 (len1), -1 (len2 -> entra)
    decisoes = [robo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(precos)]
    assert decisoes[-1][0].side == "short"


# ---------- corrida NAO atravessa a virada do pregao ------------------------

def test_on_session_start_apaga_a_corrida_do_pregao_anterior():
    robo = _robo(confirmacao_barras=3)
    precos = [100_000.0, 100_100.0, 100_200.0]  # seed, +1 (len1), +1 (len2) -- incompleta
    for i, p in enumerate(precos):
        b = _bar(i, p)
        robo.on_bar(b.ts, b, [], 0.0)
    assert robo._run_len == 2 and robo._run_dir == 1

    robo.on_session_start(pd.Timestamp("2026-03-03").date())
    assert robo._run_len == 0 and robo._run_dir == 0 and robo._last_close is None
    assert robo._entradas_hoje == 0


def test_primeira_barra_do_novo_pregao_nao_completa_a_corrida_antiga():
    """Mesmo se a corrida do dia anterior estivesse em `len == confirmacao -
    1`, a primeira barra de um pregao NOVO nunca entra so por si -- ela so
    estabelece a referencia (nenhum nivel de preco atravessa a virada)."""
    robo = _robo(confirmacao_barras=2)
    seed = _bar(0, 100_000.0)
    subida = _bar(1, 100_100.0)  # len1
    robo.on_bar(seed.ts, seed, [], 0.0)
    robo.on_bar(subida.ts, subida, [], 0.0)
    assert robo._run_len == 1

    robo.on_session_start(pd.Timestamp("2026-03-03").date())
    b_novo = _bar(0, 200_000.0, dia="2026-03-03")
    assert robo.on_bar(b_novo.ts, b_novo, [], 0.0) == []
    assert robo._run_len == 0


# ---------- confirmacao_barras respeitada -----------------------------------

def test_nao_entra_antes_de_confirmar_k_barras():
    robo = _robo(confirmacao_barras=4)
    precos = [100_000.0, 100_100.0, 100_200.0, 100_300.0]  # seed, len1, len2, len3
    decisoes = [robo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(precos)]
    assert all(d == [] for d in decisoes)
    assert robo._run_len == 3


def test_entra_exatamente_quando_confirma_k_barras():
    robo = _robo(confirmacao_barras=4)
    precos = [100_000.0, 100_100.0, 100_200.0, 100_300.0, 100_400.0]  # seed..len4
    decisoes = [robo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(precos)]
    assert decisoes[-1] and isinstance(decisoes[-1][0], Enter)
    assert all(d == [] for d in decisoes[:-1])


def test_com_posicao_aberta_o_robo_nao_tenta_entrar_de_novo():
    """O motor ja descarta um `Enter` com posicao aberta (nao piramida
    hoje) -- mas o robo tambem nao deve TENTAR: uma corrida que continua
    crescendo alem de `confirmacao_barras` enquanto ha posicao aberta nao
    gera novo `Enter`."""
    robo = _robo(confirmacao_barras=2)
    seed = _bar(0, 100_000.0)
    gatilho = _bar(1, 100_100.0)  # len1
    robo.on_bar(seed.ts, seed, [], 0.0)
    robo.on_bar(gatilho.ts, gatilho, [], 0.0)
    continua = _bar(2, 100_200.0)  # len2 -- entraria se estivesse zerado
    acoes = robo.on_bar(continua.ts, continua, [_posicao("long", 100_100.0)], 0.0)
    assert not [a for a in acoes if isinstance(a, Enter)]


# ---------- saida na quebra --------------------------------------------------

def test_sai_quando_a_corrida_quebra():
    robo = _robo(confirmacao_barras=2)
    seed = _bar(0, 100_000.0)
    subida1 = _bar(1, 100_100.0)  # len1
    robo.on_bar(seed.ts, seed, [], 0.0)
    robo.on_bar(subida1.ts, subida1, [], 0.0)
    assert robo._run_dir == 1

    quebra = _bar(2, 99_950.0)  # fecha ABAIXO -- quebra a corrida de alta
    acoes = robo.on_bar(quebra.ts, quebra, [_posicao("long", 100_100.0)], 0.0)
    assert len(acoes) == 1 and isinstance(acoes[0], Exit)
    assert acoes[0].reason == "corrida_quebrou"


def test_barra_de_retorno_zero_com_posicao_aberta_nao_sai():
    robo = _robo(confirmacao_barras=1)
    seed = _bar(0, 100_000.0)
    robo.on_bar(seed.ts, seed, [], 0.0)
    subida = _bar(1, 100_100.0)  # len1 -> confirmaria e entraria se zerado
    robo.on_bar(subida.ts, subida, [], 0.0)

    plana = _bar(2, 100_100.0)  # retorno zero -- nao quebra
    acoes = robo.on_bar(plana.ts, plana, [_posicao("long", 100_100.0)], 0.0)
    assert acoes == []


# ---------- stop_pontos / max_entradas_dia / janela: defaults fieis a medicao

def test_stop_pontos_none_por_padrao_fiel_a_medicao():
    robo = _robo(confirmacao_barras=2)
    precos = [100_000.0, 100_100.0, 100_200.0]
    decisoes = [robo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(precos)]
    assert decisoes[-1][0].initial_stop is None


def test_stop_pontos_quando_declarado_fica_na_grade_do_tick():
    robo = _robo(confirmacao_barras=2, stop_pontos=150.0, tick_size=5.0)
    precos = [100_000.0, 100_100.0, 100_200.0]
    decisoes = [robo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(precos)]
    ordem = decisoes[-1][0]
    assert ordem.initial_stop == pytest.approx(100_200.0 - 150.0)
    assert ordem.initial_stop % 5.0 == 0


def test_max_entradas_dia_none_por_padrao_nao_limita():
    assert CopaWinCorrida(teto_contratos=12).max_entradas_dia is None


def test_max_entradas_dia_e_respeitado_quando_declarado():
    robo = _robo(confirmacao_barras=1, max_entradas_dia=1)
    seed = _bar(0, 100_000.0)
    robo.on_bar(seed.ts, seed, [], 0.0)
    primeira = robo.on_bar(_bar(1, 100_100.0).ts, _bar(1, 100_100.0), [], 0.0)
    assert len(primeira) == 1
    # segunda corrida do dia (posicao ja teria sido fechada por fora -- aqui
    # so testamos o teto de entradas, positions=[] simula ja ter zerado)
    quebra = _bar(2, 99_900.0)
    robo.on_bar(quebra.ts, quebra, [], 0.0)  # nova corrida de baixa, len1
    outra = robo.on_bar(_bar(3, 99_800.0).ts, _bar(3, 99_800.0), [], 0.0)
    assert outra == []


def test_janela_de_horario_bloqueia_entrada_fora_dela():
    from datetime import time
    robo = _robo(confirmacao_barras=2, hora_inicio=time(13, 0), hora_fim=time(17, 0))
    precos = [100_000.0, 100_100.0, 100_200.0]  # todas as 12:0x, fora da janela
    decisoes = [robo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(precos)]
    assert all(d == [] for d in decisoes)
    assert robo._run_len == 2  # a corrida continua sendo contada, so a ENTRADA e' que nao dispara


def test_janela_de_horario_nao_impede_saida_fora_dela():
    """A janela so filtra ENTRADA -- uma posicao ja aberta continua vigiada
    (a corrida pode quebrar e sair) mesmo fora da janela declarada."""
    from datetime import time
    robo = _robo(confirmacao_barras=2, hora_inicio=time(0, 0), hora_fim=time(0, 1))
    seed = _bar(0, 100_000.0)
    subida = _bar(1, 100_100.0)
    robo.on_bar(seed.ts, seed, [], 0.0)
    robo.on_bar(subida.ts, subida, [], 0.0)  # fora da janela, so estabelece direcao
    quebra = _bar(2, 99_950.0)
    acoes = robo.on_bar(quebra.ts, quebra, [_posicao("long", 100_100.0)], 0.0)
    assert len(acoes) == 1 and isinstance(acoes[0], Exit)


# ---------- ausencia de look-ahead ------------------------------------------

def test_decisao_da_barra_t_nao_muda_com_barras_futuras():
    """A decisao em `on_bar` so pode depender de dados ate o fechamento da
    propria barra -- alimentar o mesmo prefixo de barras a duas instancias
    (uma que para ali, outra que continua para um futuro MUITO diferente)
    tem que produzir a MESMA sequencia de decisoes no prefixo comum."""
    prefixo = [100_000.0, 100_100.0, 100_200.0, 100_300.0, 100_400.0]
    futuro_diferente = prefixo + [50_000.0, 40_000.0, 30_000.0]

    robo_curto = _robo(confirmacao_barras=3)
    decisoes_curto = [
        robo_curto.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(prefixo)
    ]

    robo_longo = _robo(confirmacao_barras=3)
    decisoes_longo_prefixo = [
        robo_longo.on_bar(_bar(i, p).ts, _bar(i, p), [], 0.0) for i, p in enumerate(futuro_diferente)
    ][: len(prefixo)]

    for curta, longa in zip(decisoes_curto, decisoes_longo_prefixo):
        assert len(curta) == len(longa)
        for a, b in zip(curta, longa):
            assert type(a) is type(b)
            if isinstance(a, Enter):
                assert a.side == b.side and a.quantity == b.quantity
