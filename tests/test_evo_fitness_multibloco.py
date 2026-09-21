"""O fitness pontua pelo PIOR de varios blocos disjuntos -- e o DD morde.

Por que existe: na rodada de 2026-09-18 cada geracao media os individuos num
UNICO bloco contiguo de 18 pregoes sorteado do treino. Ao cruzar o fitness de
treino das 10 ilhas com o R$/op delas na janela cega, a correlacao deu
**-0,555**: as duas ilhas de maior fitness foram as duas piores fora da
amostra. Selecionar pelo maximo de um sorteio e' selecionar ruido, e foi isso
que a rodada fez por 65 geracoes.

O segundo conserto e' de peso: a penalidade de drawdown RELATIVO -- ordem
explicita do dono -- pesava de 3% a 11% do fitness dos campeoes. Era
decorativa. Agora e' quadratica.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "daytrade"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from evo import avaliacao, ga                                # noqa: E402

DIAS = [f"2026-03-{d:02d}" for d in range(1, 31)] + \
       [f"2026-04-{d:02d}" for d in range(1, 23)]            # 52 pregoes


def test_blocos_sao_disjuntos_contiguos_e_na_ordem():
    for g in range(1, 40):
        blocos = ga.blocos_da_geracao(DIAS, 17, semente=42, g=g)
        assert len(blocos) == ga.N_BLOCOS_FITNESS
        vistos = [d for b in blocos for d in b]
        assert len(vistos) == len(set(vistos)), "blocos se sobrepoem"
        assert vistos == sorted(vistos), "a ordem cronologica quebrou"
        for b in blocos:                       # cada bloco e' um trecho REAL
            i = DIAS.index(b[0])
            assert DIAS[i:i + len(b)] == b


def test_a_particao_se_move_entre_geracoes():
    vistos = {tuple(ga.blocos_da_geracao(DIAS, 17, 42, g)[0])
              for g in range(1, 40)}
    assert len(vistos) > 1, "fronteira congelada: volta a ser janela fixa"


def test_amostra_grande_demais_nao_gera_bloco_vazio():
    blocos = ga.blocos_da_geracao(DIAS, 25, semente=1, g=1)   # 3x25 > 52
    assert all(len(b) >= 2 for b in blocos)
    vistos = [d for b in blocos for d in b]
    assert len(vistos) == len(set(vistos))


def test_pontua_pelo_pior_bloco_e_reporta_as_metricas_dele(monkeypatch):
    """O numero que aparece tem de ser o do bloco que pontuou."""
    bom, ruim = [6.0] * 17, [-9.0] * 17
    out = _roda(monkeypatch, [_Bloco(trades=20, por_pregao=bom),
                              _Bloco(trades=11, por_pregao=ruim),
                              _Bloco(trades=20, por_pregao=bom)])
    assert out["fitness"] < 0, "media ou maximo em vez do minimo"
    assert out["n_trades"] == 11, "metricas nao sao as do bloco que pontuou"
    assert out["n_blocos"] == 3 and out["n_trades_total"] == 51


def test_um_bloco_otimo_nao_salva_quem_quebra_no_outro(monkeypatch):
    """A ordem do dono e' sobreviver SEMPRE. A media perdoaria; o minimo nao."""
    otimo = [99.0] * 17
    out = _roda(monkeypatch, [_Bloco(trades=40, por_pregao=otimo),
                              _Bloco(trades=4, pregoes=4, morreu=True),
                              _Bloco(trades=40, por_pregao=otimo)])
    assert out["morreu"] and out["fitness"] < avaliacao.FITNESS_SEM_AMOSTRA


@pytest.mark.parametrize("dd,minimo", [(0.15, 3.0), (0.35, 20.0),
                                       (0.80, 100.0), (0.96, 150.0)])
def test_penalidade_de_dd_e_progressiva_e_fatal_no_alto(dd, minimo):
    pena = avaliacao.PENALIDADE_DD_RELATIVO * dd ** 2
    assert pena >= minimo


def test_dd_pequeno_custa_menos_que_dd_grande_por_muito():
    p15 = avaliacao.PENALIDADE_DD_RELATIVO * 0.15 ** 2
    p80 = avaliacao.PENALIDADE_DD_RELATIVO * 0.80 ** 2
    # linear daria 5,3x; a forma quadratica tem de separar MUITO mais
    assert p80 / p15 > 25


# --------------------------------------------------------------------------
# As PORTAS valem em niveis diferentes: morte por bloco, amostra no agregado.
# Ver `ga._avalia_worker`. O bug que isto fecha: o campeao da ilha `vwap`
# pontuava -54,4 ou -995,0 conforme a particao comecasse no dia 0 ou no dia 1,
# porque um bloco caia de 7 para 5 operacoes e cruzava o piso de amostra.
# --------------------------------------------------------------------------

class _Bloco:
    """Um `Resultado` de bloco, so' com o que o worker le."""
    def __init__(self, *, trades, pregoes=17, morreu=False, dd=0.0,
                 por_pregao=None):
        self.n_trades = trades
        self.pregoes_vividos = pregoes
        self.pregoes_oferecidos = 17
        self.morreu = morreu
        self.dd_relativo = self.dd_absoluto = dd
        self.folga = 1.0
        self.caixa_por_pregao = por_pregao or [1.0] * pregoes
        self.caixa_final = self.caixa_minimo = 500.0
        self.liquido = self.r_por_op = self.win_pct = 0.0
        self.breakeven_emp = self.r_por_pregao = self.desvio_op = 0.0
        self.pregoes_com_op = pregoes


def _roda(monkeypatch, blocos):
    it = iter(blocos)
    monkeypatch.setattr(ga, "avalia", lambda g, d, feed: next(it))
    monkeypatch.setattr(ga, "resumo_pontos", lambda r: {})
    return ga._avalia_worker(((0.5,) * 33, [["a"], ["b"], ["c"]], "m1"))


def test_um_bloco_magro_nao_derruba_quem_tem_amostra_no_agregado(monkeypatch):
    """5 + 20 + 20 = 45 operacoes em 51 pregoes. O piso agregado e' 20."""
    out = _roda(monkeypatch, [_Bloco(trades=5), _Bloco(trades=20),
                              _Bloco(trades=20)])
    assert ga._banda(out) == "medido", "voltou o penhasco por bloco"
    assert out["fitness"] > avaliacao.FITNESS_SEM_AMOSTRA + 1000


def test_quem_quase_nao_opera_em_nenhum_bloco_continua_sentinela(monkeypatch):
    """A porta nao pode sumir: o robo que nao opera e' o sobrevivente
    perfeito, e sem degrau a busca converge para ele."""
    out = _roda(monkeypatch, [_Bloco(trades=2), _Bloco(trades=3),
                              _Bloco(trades=2)])
    assert ga._banda(out) == "sem_amostra"


def test_morte_em_um_unico_bloco_mata_o_individuo(monkeypatch):
    """Morte continua valendo POR BLOCO -- quem quebra num trecho quebrou."""
    out = _roda(monkeypatch, [_Bloco(trades=30), _Bloco(trades=30),
                              _Bloco(trades=9, pregoes=9, morreu=True)])
    assert ga._banda(out) == "morto" and out["morreu"]
    assert out["fitness"] < avaliacao.FITNESS_SEM_AMOSTRA


def test_entre_blocos_medidos_vale_o_PIOR(monkeypatch):
    bom = [5.0] * 17
    ruim = [-5.0] * 17
    out = _roda(monkeypatch, [_Bloco(trades=20, por_pregao=bom),
                              _Bloco(trades=20, por_pregao=ruim),
                              _Bloco(trades=20, por_pregao=bom)])
    assert out["fitness"] < 0, "a media venceu o minimo"
