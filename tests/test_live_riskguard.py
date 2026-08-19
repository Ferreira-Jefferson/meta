"""Testes do disjuntor de risco (`live/riskguard.py`).

`CircuitBreaker` e uma trava OPERACIONAL, nao uma regra de sinal (ver
docstring do modulo para a distincao com a regra 6 do AGENTS.md): o unico
poder dela e `is_frozen` — um booleano que outro codigo, fora desta classe,
consulta para decidir se libera a abertura de uma posicao NOVA. Esta classe
nao tem, e nao deveria ter, nenhum metodo que bloqueie saida/stop/saque:
reduzir risco nunca pode ser vetado, so aumentar risco. Por isso os testes
abaixo verificam a MECANICA da trava (quando liga, quando desliga sozinha,
quando so um humano desliga) e nunca testam "bloqueou uma venda", porque essa
acao nao existe na classe.
"""
import json
from datetime import date

import pytest

from live.riskguard import CircuitBreaker


def _d(y: int, m: int, d: int) -> date:
    return date(y, m, d)


# ---------- trava diaria ----------------------------------------------------

def test_perda_diaria_abaixo_do_limite_nao_trava():
    cb = CircuitBreaker(daily_loss_pct=0.05)
    cb.observe(_d(2026, 8, 17), 100_000.0)   # base do dia
    cb.observe(_d(2026, 8, 17), 97_000.0)    # -3%, dentro do limite
    assert cb.is_frozen is False
    assert cb.reason is None


def test_perda_diaria_acima_do_limite_trava_e_reason_tem_o_numero_certo():
    cb = CircuitBreaker(daily_loss_pct=0.05)
    cb.observe(_d(2026, 8, 17), 100_000.0)   # base do dia
    cb.observe(_d(2026, 8, 17), 93_800.0)    # -6,20%
    assert cb.is_frozen is True
    assert "6.20%" in cb.reason
    assert "5.00%" in cb.reason


def test_novo_dia_calendario_reseta_trava_diaria_sozinha():
    """Um dia ruim nao trava o sistema para sempre: no dia seguinte a base
    recalcula a partir do novo patrimonio observado, sem precisar de
    `unfreeze()`."""
    cb = CircuitBreaker(daily_loss_pct=0.05)
    cb.observe(_d(2026, 8, 17), 100_000.0)
    cb.observe(_d(2026, 8, 17), 90_000.0)    # -10%: trava
    assert cb.is_frozen is True

    cb.observe(_d(2026, 8, 18), 90_000.0)    # dia novo: base = 90k, reset automatico
    assert cb.is_frozen is False
    assert cb.reason is None

    # a nova base e o patrimonio do primeiro observe do dia novo (90k), nao o antigo
    cb.observe(_d(2026, 8, 18), 86_000.0)    # -4,44% sobre a NOVA base: nao trava
    assert cb.is_frozen is False


# ---------- trava mensal -----------------------------------------------------

def test_perda_mensal_acima_do_limite_trava():
    cb = CircuitBreaker(monthly_loss_pct=0.15)
    cb.observe(_d(2026, 8, 3), 100_000.0)    # base do mes
    cb.observe(_d(2026, 8, 20), 80_000.0)    # -20%
    assert cb.is_frozen is True
    assert "perda mensal" in cb.reason
    assert "20.00%" in cb.reason
    assert "15.00%" in cb.reason


def test_mes_calendario_novo_NAO_reseta_trava_mensal_sozinha():
    """O teste mais importante: a assimetria do design. Perda mensal grande
    pode significar estrategia/dado/bug quebrado — so um humano, via
    `unfreeze()`, deveria religar. Trocar de mes-calendario sozinho NAO
    conta como revisao humana."""
    cb = CircuitBreaker(monthly_loss_pct=0.15)
    cb.observe(_d(2026, 8, 3), 100_000.0)    # base de agosto
    cb.observe(_d(2026, 8, 20), 80_000.0)    # -20%: trava mensal aciona
    assert cb.is_frozen is True

    # mes vira (setembro), nova base e fixada, mas a trava CONTINUA ativa
    cb.observe(_d(2026, 9, 1), 80_000.0)
    assert cb.is_frozen is True
    assert "perda mensal" in cb.reason

    # mesmo sem nenhuma perda adicional em setembro, continua travado
    cb.observe(_d(2026, 9, 2), 80_500.0)     # ligeira alta sobre a base de set/2026
    assert cb.is_frozen is True

    # so unfreeze() explicito libera
    cb.unfreeze()
    assert cb.is_frozen is False


def test_unfreeze_limpa_as_duas_travas_de_uma_vez():
    """Mesmo que so uma trava esteja ativa, `unfreeze()` limpa as duas —
    e reset manual completo, nao seletivo."""
    cb = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
    cb.observe(_d(2026, 8, 3), 100_000.0)
    cb.observe(_d(2026, 8, 3), 80_000.0)     # -20%: trava diaria E mensal juntas
    assert cb.is_frozen is True
    assert "perda diaria" in cb.reason
    assert "perda mensal" in cb.reason

    cb.unfreeze()
    assert cb.is_frozen is False
    assert cb.reason is None

    # unfreeze() nao apaga a BASE mensal (so o motivo do congelamento) — a
    # base de agosto continua 100k. Uma recuperacao para 87k fica em -13%,
    # dentro do limite de 15%, entao nao re-trava sozinho.
    cb.observe(_d(2026, 8, 4), 87_000.0)
    assert cb.is_frozen is False


def test_so_diaria_ativa_unfreeze_tambem_limpa_mensal_vazia_sem_erro():
    cb = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
    cb.observe(_d(2026, 8, 3), 100_000.0)
    cb.observe(_d(2026, 8, 3), 90_000.0)     # -10%: so a diaria trava (mensal limite e 15%)
    assert cb.is_frozen is True
    assert "perda diaria" in cb.reason
    assert "perda mensal" not in (cb.reason or "")

    cb.unfreeze()
    assert cb.is_frozen is False


# ---------- escopo da classe: so veta ENTRADA, nunca bloqueia saida ---------

def test_classe_nao_tem_nenhum_metodo_de_bloqueio_de_saida():
    """Documenta o limite de escopo: nao existe `block_exit`, `veto_stop`,
    `veto_withdrawal` ou qualquer coisa parecida. O unico produto desta
    classe e o booleano `is_frozen` (mais `reason` para diagnostico); quem
    decide o que fazer com isso — inclusive nunca usar `is_frozen` para
    impedir uma saida — e codigo de fora, que esta classe nem conhece."""
    cb = CircuitBreaker()
    public_api = {name for name in dir(cb) if not name.startswith("_")}
    assert public_api == {
        "daily_loss_pct",
        "monthly_loss_pct",
        "observe",
        "is_frozen",
        "reason",
        "unfreeze",
        "state",
        "restore",
    }


# ---------- persistencia de estado (restart ao vivo) ------------------------

def test_state_round_trip_via_json_preserva_comportamento():
    cb = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
    cb.observe(_d(2026, 8, 3), 100_000.0)
    cb.observe(_d(2026, 8, 4), 98_000.0)

    snapshot = json.loads(json.dumps(cb.state()))
    fresh = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
    fresh.restore(snapshot)

    assert fresh.is_frozen == cb.is_frozen
    assert fresh.reason == cb.reason

    # a partir daqui as duas instancias tem que andar juntas
    cb.observe(_d(2026, 8, 5), 90_000.0)
    fresh.observe(_d(2026, 8, 5), 90_000.0)
    assert fresh.is_frozen == cb.is_frozen
    assert fresh.reason == cb.reason


def test_restore_normaliza_lista_em_tupla_das_referencias():
    """Sem a normalizacao lista->tupla em `restore`, a trava diaria
    resetaria (e recalcularia a base) a cada `observe()`, porque
    `day_key != self._daily_ref_date` ficaria sempre True (lista nunca
    `==` tupla) mesmo representando o mesmo dia."""
    cb = CircuitBreaker(daily_loss_pct=0.05)
    cb.observe(_d(2026, 8, 17), 100_000.0)

    state = json.loads(json.dumps(cb.state()))
    assert isinstance(state["_daily_ref_date"], list)     # JSON perdeu o tipo tupla
    assert isinstance(state["_monthly_ref_month"], list)

    fresh = CircuitBreaker(daily_loss_pct=0.05)
    fresh.restore(state)
    assert isinstance(fresh._daily_ref_date, tuple)       # restore normalizou de volta
    assert isinstance(fresh._monthly_ref_month, tuple)
    assert fresh._daily_ref_date == (2026, 8, 17)
    assert fresh._monthly_ref_month == (2026, 8)

    # mesmo dia-calendario: se a normalizacao nao tivesse acontecido, este
    # segundo observe recalcularia a base (achando que e "dia novo") e a
    # perda de -6% nunca seria detectada contra a base original de 100k.
    fresh.observe(_d(2026, 8, 17), 94_000.0)   # -6% sobre a base de 100k
    assert fresh.is_frozen is True


def test_unfreeze_com_patrimonio_reancora_as_duas_bases():
    """Passo 6 (RED antes de GREEN, achado F2): sem re-ancorar, o tick
    seguinte ao destravamento recalcula a MESMA perda contra a MESMA base
    antiga e recongela em segundos -- o botao de panico documentado vira
    inoperante durante o pregao. `unfreeze(session, patrimonio)` tem de
    re-ancorar as duas bases (diaria e mensal) no patrimonio corrente."""
    cb = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
    cb.observe(_d(2026, 8, 17), 100_000.0)
    cb.observe(_d(2026, 8, 17), 80_000.0)     # -20%: trava diaria E mensal
    assert cb.is_frozen is True

    cb.unfreeze(_d(2026, 8, 17), 80_000.0)    # humano revisou, patrimonio atual = 80k
    assert cb.is_frozen is False

    # o proximo observe() com o MESMO patrimonio (80k) NAO pode recongelar:
    # a base do dia/mes agora E 80k, entao a perda contra ela e 0%.
    cb.observe(_d(2026, 8, 17), 80_000.0)
    assert cb.is_frozen is False
    assert cb._daily_ref_equity == pytest.approx(80_000.0)
    assert cb._monthly_ref_equity == pytest.approx(80_000.0)
    assert cb._daily_ref_date == (2026, 8, 17)
    assert cb._monthly_ref_month == (2026, 8)

    # chamada SEM argumentos preserva o comportamento antigo (nao re-ancora)
    cb2 = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
    cb2.observe(_d(2026, 8, 17), 100_000.0)
    cb2.observe(_d(2026, 8, 17), 80_000.0)
    cb2.unfreeze()
    assert cb2._daily_ref_equity == pytest.approx(100_000.0)   # base NAO mudou
    assert cb2._monthly_ref_equity == pytest.approx(100_000.0)


def test_restart_no_meio_do_mes_produz_o_mesmo_resultado_que_processo_continuo():
    """Uma instancia que reinicia no meio do caminho tem que terminar
    identica (is_frozen, reason) a uma que nunca reiniciou."""
    baseline = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
    restarted = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)

    schedule = [
        (_d(2026, 8, 3), 100_000.0),
        (_d(2026, 8, 4), 99_000.0),
        (_d(2026, 8, 5), 97_500.0),
        (_d(2026, 8, 6), 96_000.0),   # ainda dentro dos limites
        (_d(2026, 8, 7), 95_000.0),
        (_d(2026, 8, 10), 84_000.0),  # -16% sobre a base do mes: trava mensal aciona
        (_d(2026, 8, 11), 84_200.0),
        (_d(2026, 9, 1), 84_200.0),   # mes novo: trava mensal PERSISTE
        (_d(2026, 9, 2), 84_500.0),
    ]

    for i, (d, equity) in enumerate(schedule):
        baseline.observe(d, equity)
        if i == 4:
            # "restart": serializa, descarta a instancia, recria do zero e
            # reidrata antes de continuar observando.
            snap = json.loads(json.dumps(restarted.state()))
            restarted = CircuitBreaker(daily_loss_pct=0.05, monthly_loss_pct=0.15)
            restarted.restore(snap)
        restarted.observe(d, equity)

    assert restarted.is_frozen == baseline.is_frozen == True
    assert restarted.reason == baseline.reason
