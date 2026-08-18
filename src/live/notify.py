"""Notificacao FORA do dashboard (Telegram/e-mail) para a operacao ao vivo.

Por que isto existe (contexto de produto)
-----------------------------------------------------------------------------
O sistema roda autonomo, 24/7, num servidor, com dinheiro real, sem ninguem
olhando a tela o tempo todo. Toda decisao, execucao, erro e disparo de
circuit-breaker ja vira linha em `live_events` (via `journal.live_store.
log_event`) para quem ABRIR o dashboard depois. Mas quem esta longe do
computador precisa saber que algo aconteceu SEM precisar abrir a pagina — daí
este modulo: um canal push (Telegram e/ou e-mail) com a MESMA forma de
`log_event` (level/source/message/payload), de proposito, para ficar facil
disparar diario + notificacao juntos no mesmo ponto de chamada.

Regra de fronteira (AGENTS.md #6): `live/` nao decide NADA de trade. Este
modulo so entrega uma mensagem que ja foi decidida em outro lugar — nao filtra
por importancia de negocio (isso e decisao de quem chama), nao interpreta o
`payload`, nao decide o que e "grave". A UNICA logica que este modulo tem
(`MinLevelNotifier`) e sobre RUIDO DE CANAL (quantos alertas cabem num
Telegram sem virar spam), nunca sobre risco de mercado.

Por que uma falha de notificacao NUNCA pode propagar
-----------------------------------------------------------------------------
Mesmo padrao de `live.feed.YFinanceFeed`: rede (Telegram) e SMTP podem falhar
a qualquer momento — timeout, DNS, credencial expirada, provedor fora do ar.
O processo de operacao roda sozinho num servidor; se `notify()` pudesse
lançar, um problema de notificacao (que e, por definicao, um problema
SECUNDARIO) derrubaria o loop principal que esta executando ordens de
verdade. Por isso TODA implementacao aqui engole a excecao e, no maximo,
repassa para um callback `on_error` opcional — nunca propaga.

Por que a resolucao de credenciais fica FORA destas classes
-----------------------------------------------------------------------------
Token de bot, chat_id, host/porta/usuario/senha de SMTP sao configuracao de
ambiente (producao real vs. paper local). Ler `os.environ` aqui dentro
acoplaria esta camada a uma forma especifica de configurar (env var) e
tornaria os testes dependentes de variaveis globais do processo. Quem
CONSTROI o notifier (a linha de comando / composicao em `scripts/run_live.py`,
que nao e responsabilidade deste arquivo) resolve as credenciais e passa os
valores ja prontos como parametro — estas classes ficam puras e testaveis
sem monkeypatch de `os.environ`.

Zero dependencias novas: so stdlib (`urllib`, `smtplib`, `email`) — ver
AGENTS.md, "Nao adicionar dependencia sem justificativa".
"""
from __future__ import annotations

import smtplib
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Callable, Optional

# Ordem de severidade usada por `MinLevelNotifier` para decidir o que passa
# no filtro. Mesmos rotulos que `journal.live_store.log_event` grava em
# `level` — nao inventamos uma taxonomia paralela.
_LEVEL_ORDER: dict[str, int] = {"debug": 0, "info": 1, "warn": 2, "error": 3}


def _level_rank(level: str) -> int:
    """Traduz o nivel textual em rank numerico comparavel.

    Nivel desconhecido (erro de digitacao em algum `source` novo) cai em
    "info": nem some silenciosamente (como cairia em "debug", o rank mais
    baixo) nem trava o alerta (como cairia em "error"). E o meio-termo que
    nao esconde bug de digitacao sem inundar o canal.
    """
    return _LEVEL_ORDER.get(level.lower(), _LEVEL_ORDER["info"])


def _format_payload_inline(payload: Optional[dict]) -> str:
    """Formata o payload em uma linha curta ("chave=valor | chave=valor").

    Usado pelo Telegram, onde mensagem longa atrapalha leitura no celular.
    Chaves ordenadas para saida deterministica (facilita teste e leitura).
    """
    if not payload:
        return ""
    return " | ".join(f"{key}={value}" for key, value in sorted(payload.items()))


def _format_payload_block(payload: Optional[dict]) -> str:
    """Formata o payload como bloco multi-linha ("  chave: valor" por linha).

    Usado no corpo do e-mail, onde ha espaco de sobra e legibilidade importa
    mais que compacidade.
    """
    if not payload:
        return ""
    return "\n".join(f"  {key}: {value}" for key, value in sorted(payload.items()))


class Notifier(ABC):
    """Contrato de canal de alerta. Ver docstring do modulo para o porque de
    `notify()` nunca poder lancar excecao."""

    @abstractmethod
    def notify(self, level: str, source: str, message: str, payload: Optional[dict] = None) -> None:
        """NUNCA lanca excecao — falha de notificacao nao pode derrubar o
        processo de operacao. Erros de envio sao engolidos e (opcionalmente)
        reportados via um callback `on_error`, nunca propagados."""
        raise NotImplementedError


class TelegramNotifier(Notifier):
    """Envia a mensagem via Telegram Bot API (`sendMessage`), usando so a
    stdlib (`urllib`) — ver docstring do modulo sobre nao adicionar `requests`
    como dependencia nova."""

    _TIMEOUT_SECONDS = 10.0

    def __init__(self, bot_token: str, chat_id: str, on_error: Optional[Callable[[Exception], None]] = None) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._on_error = on_error

    def notify(self, level: str, source: str, message: str, payload: Optional[dict] = None) -> None:
        text = f"[{level}] {source}: {message}"
        extra = _format_payload_inline(payload)
        if extra:
            text = f"{text}\n{extra}"

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": self._chat_id, "text": text}).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        try:
            # Timeout curto de proposito: se a rede estiver ruim, o loop
            # principal (que roda sozinho no servidor) nao pode ficar preso
            # aqui esperando o Telegram responder.
            with urllib.request.urlopen(request, timeout=self._TIMEOUT_SECONDS) as response:
                response.read()
        except Exception as exc:  # qualquer falha (rede, timeout, resposta malformada) e engolida
            self._report_error(exc)

    def _report_error(self, exc: Exception) -> None:
        if self._on_error is not None:
            self._on_error(exc)


class EmailNotifier(Notifier):
    """Envia a mensagem por e-mail via SMTP, usando so a stdlib
    (`smtplib` + `email.message.EmailMessage`)."""

    _TIMEOUT_SECONDS = 10.0

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        to_addr: str,
        from_addr: Optional[str] = None,
        use_tls: bool = True,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._to_addr = to_addr
        # Sem `from_addr` explicito, usa o proprio login — e o que a maioria
        # dos provedores SMTP exige de qualquer forma (from == autenticado).
        self._from_addr = from_addr or username
        self._use_tls = use_tls
        self._on_error = on_error

    def notify(self, level: str, source: str, message: str, payload: Optional[dict] = None) -> None:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[META] {level.upper()} · {source}"
            msg["From"] = self._from_addr
            msg["To"] = self._to_addr

            body = message
            extra = _format_payload_block(payload)
            if extra:
                body = f"{body}\n\npayload:\n{extra}"
            msg.set_content(body)

            # `use_tls=True` (porta 587 tipica): conexao em claro + STARTTLS.
            # `use_tls=False` (porta 465 tipica): SSL implicito desde o
            # connect — smtplib.SMTP_SSL. Um unico flag cobre os dois modos
            # mais comuns de SMTP autenticado sem precisar de um terceiro
            # parametro.
            smtp_cls = smtplib.SMTP if self._use_tls else smtplib.SMTP_SSL
            with smtp_cls(self._smtp_host, self._smtp_port, timeout=self._TIMEOUT_SECONDS) as smtp:
                if self._use_tls:
                    smtp.starttls()
                smtp.login(self._username, self._password)
                smtp.send_message(msg)
        except Exception as exc:  # qualquer falha de SMTP (login, envio, conexao) e engolida
            self._report_error(exc)

    def _report_error(self, exc: Exception) -> None:
        if self._on_error is not None:
            self._on_error(exc)


class CompositeNotifier(Notifier):
    """Repassa a notificacao para varios canais (ex.: Telegram + e-mail).

    Se um canal falhar — mesmo que ja engula a propria excecao pelo contrato
    de `Notifier` — os demais ainda precisam ser chamados. O `try/except`
    aqui e defesa em profundidade: nao deveria ser necessario dado o
    contrato, mas um notifier mal implementado nao pode travar os outros.
    """

    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = list(notifiers)

    def notify(self, level: str, source: str, message: str, payload: Optional[dict] = None) -> None:
        for notifier in self._notifiers:
            try:
                notifier.notify(level, source, message, payload)
            except Exception:
                # Ver docstring da classe: contrato diz que isto nao deveria
                # acontecer, mas um canal quebrado nao pode impedir os outros.
                continue


class NullNotifier(Notifier):
    """No-op. Default sensato quando ninguem configurou alerta (ex.: rodando
    em paper local, sem Telegram/e-mail configurados) — chamar `notify()`
    aqui e um no-op DELIBERADO, nao um "esquecemos de implementar"."""

    def notify(self, level: str, source: str, message: str, payload: Optional[dict] = None) -> None:
        return None


class MinLevelNotifier(Notifier):
    """Filtro de ruido de canal: so repassa para `inner` se `level` for >= `min_level`.

    Util para nao lotar o Telegram com todo evento `info` do dia a dia — por
    exemplo, mandar so `warn`/`error` para o celular enquanto o diario
    (`live_events`, via `log_event`) continua guardando TUDO sem filtro. Essa
    e a UNICA logica de "importancia" que este modulo tem, e e sobre volume
    de mensagem no canal, nunca sobre risco de mercado (ver docstring do
    modulo, regra 6 do AGENTS.md).
    """

    def __init__(self, inner: Notifier, min_level: str = "info") -> None:
        self._inner = inner
        self._min_rank = _level_rank(min_level)

    def notify(self, level: str, source: str, message: str, payload: Optional[dict] = None) -> None:
        if _level_rank(level) >= self._min_rank:
            self._inner.notify(level, source, message, payload)
