"""Testes de `live/notify.py` — canal de alerta fora do dashboard, sem rede real.

Foco: nenhuma implementacao de `Notifier` pode deixar excecao escapar de
`notify()` (rede/SMTP podem falhar a qualquer momento no servidor 24/7), o
`on_error` opcional recebe a excecao quando fornecido, `CompositeNotifier`
chama todos os canais mesmo se um deles falhar, `MinLevelNotifier` filtra por
severidade na ordem debug < info < warn < error, e `NullNotifier` e um no-op
puro.
"""
from __future__ import annotations

import smtplib
import urllib.error
import urllib.request

import pytest

from live.notify import (
    CompositeNotifier,
    EmailNotifier,
    MinLevelNotifier,
    Notifier,
    NullNotifier,
    TelegramNotifier,
)
from tests.doubles import _RecordingNotifier


# ---------------------------------------------------------------------------
# duplos de teste
# ---------------------------------------------------------------------------

class _BoomNotifier(Notifier):
    """Notifier fake que viola o contrato e lanca — usado so para testar a
    defesa em profundidade de `CompositeNotifier` (nao deveria ser possivel
    dado o contrato de `Notifier`, mas o composite se protege mesmo assim)."""

    def notify(self, level, source, message, payload=None) -> None:
        raise RuntimeError("notifier mal implementado explodiu")


class _FakeSMTPResponse:
    """Contexto retornado por `_FakeSMTP()` — implementa o protocolo de
    context manager usado pelo `with smtp_cls(...) as smtp:` de `EmailNotifier`."""

    def __init__(self, fake: "_FakeSMTP") -> None:
        self._fake = fake

    def __enter__(self) -> "_FakeSMTP":
        return self._fake

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._fake.quit()
        return False


class _FakeSMTP:
    """Dublê de `smtplib.SMTP`/`SMTP_SSL`: registra `starttls`/`login`/
    `send_message`/`quit`, e pode ser configurado para falhar em qualquer um
    desses passos (simulando problema de rede/credencial)."""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, login_exc=None, send_exc=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_args = None
        self.sent_message = None
        self.quit_called = False
        self._login_exc = login_exc
        self._send_exc = send_exc
        _FakeSMTP.instances.append(self)

    def starttls(self):
        self.starttls_called = True

    def login(self, username, password):
        if self._login_exc is not None:
            raise self._login_exc
        self.login_args = (username, password)

    def send_message(self, msg):
        if self._send_exc is not None:
            raise self._send_exc
        self.sent_message = msg

    def quit(self):
        self.quit_called = True


def _fake_smtp_factory(login_exc=None, send_exc=None):
    """Fabrica uma classe substituta de `smtplib.SMTP`/`SMTP_SSL` que se
    comporta como `_FakeSMTP`, mas expõe o protocolo de context manager
    (`with smtp_cls(...) as smtp:`) que `EmailNotifier` usa."""

    def _constructor(host, port, timeout=None):
        fake = _FakeSMTP(host, port, timeout=timeout, login_exc=login_exc, send_exc=send_exc)
        return _FakeSMTPResponse(fake)

    return _constructor


# ---------------------------------------------------------------------------
# TelegramNotifier
# ---------------------------------------------------------------------------

def test_telegram_notifier_monta_request_com_token_chat_id_e_texto(monkeypatch):
    captured = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    notifier = TelegramNotifier(bot_token="TOKEN123", chat_id="CHAT456")
    notifier.notify("error", "runtime", "circuit breaker disparado", payload={"ticker": "WEGE3.SA"})

    assert "TOKEN123" in captured["url"]
    assert "CHAT456" in captured["body"]
    assert "circuit+breaker" in captured["body"] or "circuit%20breaker" in captured["body"]
    assert "WEGE3.SA" in captured["body"]
    assert captured["timeout"] == pytest.approx(10.0)


def test_telegram_notifier_falha_de_rede_nao_propaga_e_chama_on_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    erros = []
    notifier = TelegramNotifier(bot_token="TOKEN", chat_id="CHAT", on_error=erros.append)

    # nao deve lancar
    notifier.notify("warn", "feed", "yfinance fora do ar")

    assert len(erros) == 1
    assert isinstance(erros[0], urllib.error.URLError)


def test_telegram_notifier_sem_on_error_nao_propaga(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise TimeoutError("demorou demais")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    notifier = TelegramNotifier(bot_token="TOKEN", chat_id="CHAT")
    # sem on_error configurado, so nao pode lancar
    notifier.notify("info", "runtime", "tick")


# ---------------------------------------------------------------------------
# EmailNotifier
# ---------------------------------------------------------------------------

def test_email_notifier_envia_com_assunto_e_corpo_esperados(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", _fake_smtp_factory())

    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="bot@example.com",
        password="segredo",
        to_addr="alguem@example.com",
    )
    notifier.notify("error", "runtime", "ordem rejeitada", payload={"ticker": "RADL3.SA", "motivo": "saldo"})

    assert len(_FakeSMTP.instances) == 1
    fake = _FakeSMTP.instances[0]
    assert fake.starttls_called is True
    assert fake.login_args == ("bot@example.com", "segredo")
    assert fake.quit_called is True

    msg = fake.sent_message
    assert msg["Subject"] == "[META] ERROR · runtime"
    assert msg["From"] == "bot@example.com"
    assert msg["To"] == "alguem@example.com"
    body = msg.get_content()
    assert "ordem rejeitada" in body
    assert "RADL3.SA" in body
    assert "saldo" in body


def test_email_notifier_from_addr_explicito_sobrescreve_username(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", _fake_smtp_factory())

    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="bot@example.com",
        password="segredo",
        to_addr="alguem@example.com",
        from_addr="alertas@example.com",
    )
    notifier.notify("info", "runtime", "tick diario")

    assert _FakeSMTP.instances[0].sent_message["From"] == "alertas@example.com"


def test_email_notifier_use_tls_false_usa_smtp_ssl_sem_starttls(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", _fake_smtp_factory())

    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=465,
        username="bot@example.com",
        password="segredo",
        to_addr="alguem@example.com",
        use_tls=False,
    )
    notifier.notify("info", "runtime", "tick diario")

    fake = _FakeSMTP.instances[0]
    assert fake.starttls_called is False
    assert fake.login_args == ("bot@example.com", "segredo")


def test_email_notifier_falha_de_login_nao_propaga_e_chama_on_error(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _fake_smtp_factory(login_exc=smtplib.SMTPAuthenticationError(535, b"bad creds")))

    erros = []
    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="bot@example.com",
        password="errada",
        to_addr="alguem@example.com",
        on_error=erros.append,
    )

    notifier.notify("error", "runtime", "circuit breaker")

    assert len(erros) == 1
    assert isinstance(erros[0], smtplib.SMTPAuthenticationError)


def test_email_notifier_falha_de_envio_nao_propaga_e_chama_on_error(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _fake_smtp_factory(send_exc=smtplib.SMTPServerDisconnected("caiu")))

    erros = []
    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        username="bot@example.com",
        password="segredo",
        to_addr="alguem@example.com",
        on_error=erros.append,
    )

    notifier.notify("warn", "runtime", "reconexao")

    assert len(erros) == 1
    assert isinstance(erros[0], smtplib.SMTPServerDisconnected)


# ---------------------------------------------------------------------------
# CompositeNotifier
# ---------------------------------------------------------------------------

def test_composite_notifier_chama_todos():
    a = _RecordingNotifier()
    b = _RecordingNotifier()

    composite = CompositeNotifier([a, b])
    composite.notify("info", "runtime", "tick", payload={"x": 1})

    assert a.calls == [("info", "runtime", "tick", {"x": 1})]
    assert b.calls == [("info", "runtime", "tick", {"x": 1})]


def test_composite_notifier_um_notifier_quebrado_nao_impede_os_outros():
    antes = _RecordingNotifier()
    depois = _RecordingNotifier()

    composite = CompositeNotifier([antes, _BoomNotifier(), depois])
    # nao deve lancar, mesmo com um notifier no meio explodindo
    composite.notify("error", "runtime", "circuit breaker")

    assert len(antes.calls) == 1
    assert len(depois.calls) == 1


def test_composite_notifier_lista_vazia_nao_faz_nada():
    CompositeNotifier([]).notify("info", "runtime", "tick")


# ---------------------------------------------------------------------------
# NullNotifier
# ---------------------------------------------------------------------------

def test_null_notifier_e_no_op():
    notifier = NullNotifier()
    # nenhuma das chamadas abaixo pode lancar nem ter efeito observavel
    notifier.notify("error", "runtime", "qualquer coisa", payload={"a": 1})
    notifier.notify("debug", "runtime", "outra coisa")


# ---------------------------------------------------------------------------
# MinLevelNotifier
# ---------------------------------------------------------------------------

def test_min_level_notifier_bloqueia_abaixo_do_minimo():
    inner = _RecordingNotifier()
    notifier = MinLevelNotifier(inner, min_level="warn")

    notifier.notify("debug", "runtime", "tick")
    notifier.notify("info", "runtime", "tick")

    assert inner.calls == []


def test_min_level_notifier_repassa_no_minimo_e_acima():
    inner = _RecordingNotifier()
    notifier = MinLevelNotifier(inner, min_level="warn")

    notifier.notify("warn", "runtime", "atencao")
    notifier.notify("error", "runtime", "circuit breaker")

    assert [c[0] for c in inner.calls] == ["warn", "error"]


@pytest.mark.parametrize(
    "min_level,allowed,blocked",
    [
        ("debug", ["debug", "info", "warn", "error"], []),
        ("info", ["info", "warn", "error"], ["debug"]),
        ("warn", ["warn", "error"], ["debug", "info"]),
        ("error", ["error"], ["debug", "info", "warn"]),
    ],
)
def test_min_level_notifier_ordem_debug_info_warn_error(min_level, allowed, blocked):
    inner = _RecordingNotifier()
    notifier = MinLevelNotifier(inner, min_level=min_level)

    for level in allowed + blocked:
        notifier.notify(level, "runtime", "msg")

    niveis_recebidos = [c[0] for c in inner.calls]
    assert niveis_recebidos == allowed


def test_min_level_notifier_default_e_info():
    inner = _RecordingNotifier()
    notifier = MinLevelNotifier(inner)

    notifier.notify("debug", "runtime", "tick")
    notifier.notify("info", "runtime", "tick")

    assert [c[0] for c in inner.calls] == ["info"]


# ---------------------------------------------------------------------------
# contrato ABC
# ---------------------------------------------------------------------------

def test_notifier_e_abstrata():
    with pytest.raises(TypeError):
        Notifier()
