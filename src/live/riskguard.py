"""Disjuntor de risco (`CircuitBreaker`) — trava operacional, NAO trava de sinal.

Contexto: o robo vai operar sozinho, com dinheiro real, sem ninguem olhando a
tela o tempo todo. Regra 6 do AGENTS.md diz que `live/` nao decide NADA de
trade — quem decide o que comprar/vender e `strategy/`. Mas isto aqui e uma
categoria diferente de trava: nao e uma regra de sinal, e uma trava de RISCO
OPERACIONAL, do tipo "algo pode estar estruturalmente errado (estrategia,
dado, bug), pare de aumentar exposicao ate um humano olhar". Por isso o unico
poder desta classe e VETAR abertura de posicao NOVA — ela nunca escolhe o que
comprar, nunca forca uma venda, nunca mexe em stop ou em saque. Liquidar a
forca seria, ela mesma, mais uma forma de perder dinheiro (venda no pior
momento) — nao menos. `is_frozen` e um sinal binario que outro codigo, fora
desta classe, consulta antes de mandar uma ordem de ENTRADA; esta classe nao
sabe nem precisa saber quem a consulta.

Assimetria de proposito entre as duas travas (o cuidado central do design):

  - Trava DIARIA reseta SOZINHA no primeiro `observe()` de um dia-calendario
    novo. Um dia ruim isolado (gap, noticia, volatilidade de curto prazo) nao
    deveria travar o sistema para sempre — amanha e um dia novo, com uma base
    de comparacao nova, e o robo deve voltar a poder abrir posicao sem
    intervencao humana.
  - Trava MENSAL NAO reseta sozinha — nem quando o mes-calendario vira. Uma
    perda mensal grande e um sinal mais serio: pode ser a estrategia
    quebrada, um bug no calculo de posicao, dado incorreto vindo do feed, ou
    um evento estrutural do mercado. Ela so sai do ar com `unfreeze()`
    chamado EXPLICITAMENTE por um humano, via CLI, depois de revisar o que
    aconteceu. Deixar a trava mensal resetar sozinha no dia 1 do mes seguinte
    (um erro facil de cometer "simplificando" a logica para tratar as duas
    igual) devolveria o robo ao ar automaticamente logo depois do pior tipo
    de evento — exatamente o oposto do que a trava existe para fazer.

Cuidado de persistencia (mesmo padrao de `backtest.withdrawal.WithdrawalPolicy`,
ver `state()`/`restore()` la para o precedente): o processo ao vivo reinicia
(deploy, reboot, queda de energia) e perde toda memoria local. As referencias
diaria/mensal sao tuplas (`(ano, mes, dia)` e `(ano, mes)`); o caminho real de
persistencia passa por JSON (`json.loads(json.dumps(...))`), que nao tem tipo
tupla — uma tupla vira lista na volta. Sem normalizar de volta em `restore()`,
comparacoes como `dia != self._daily_ref_day` ficam sempre True (lista nunca
`==` tupla em Python), e a trava diaria nunca reconheceria "mesmo dia" —
recalcularia a base a cada `observe()` como se fosse sempre o primeiro do dia.
"""
from __future__ import annotations

from datetime import date


class CircuitBreaker:
    """Trava de perda diaria/mensal. NAO decide o que comprar/vender — so
    pode vetar a abertura de posicao NOVA. Saidas, stops e saques continuam
    liberados mesmo com o disjuntor acionado (reduzir risco nunca e bloqueado,
    so aumentar risco).

    Assimetria de proposito (ver docstring do modulo para o detalhe):
    a trava DIARIA reseta sozinha a cada dia-calendario novo; a trava MENSAL
    so sai do ar com `unfreeze()` chamado explicitamente por um humano — um
    mes ruim merece revisao, nao reset automatico.
    """

    def __init__(
        self,
        daily_loss_pct: float = 0.05,
        monthly_loss_pct: float = 0.15,
    ) -> None:
        self.daily_loss_pct = float(daily_loss_pct)
        self.monthly_loss_pct = float(monthly_loss_pct)

        # referencia (base de comparacao) do dia/mes corrente, e o
        # patrimonio observado nela. `None` = ainda nao houve nenhum
        # `observe()` (ou, no caso do mes, ainda nao houve nenhum no mes
        # corrente apos um eventual restore de estado antigo).
        self._daily_ref_date: tuple | None = None    # (ano, mes, dia)
        self._daily_ref_equity: float | None = None
        self._monthly_ref_month: tuple | None = None  # (ano, mes)
        self._monthly_ref_equity: float | None = None

        # travas: guardam o motivo (str) quando acionadas, None quando livres.
        self._daily_frozen_reason: str | None = None
        self._monthly_frozen_reason: str | None = None

    # ---------- observacao ------------------------------------------------

    def observe(self, date: date, patrimonio: float) -> None:
        """Registra o patrimonio do dia.

        No primeiro `observe()` de um dia-calendario novo, o patrimonio vira
        a base de comparacao do dia (e a trava diaria reseta sozinha — ver
        docstring da classe). No primeiro `observe()` de um mes-calendario
        novo, o patrimonio vira a base de comparacao do mes — mas a trava
        mensal, se ja estava acionada, PERMANECE acionada: so `unfreeze()`
        explicito a libera.
        """
        patrimonio = float(patrimonio)
        day_key = (date.year, date.month, date.day)
        month_key = (date.year, date.month)

        if day_key != self._daily_ref_date:
            self._daily_ref_date = day_key
            self._daily_ref_equity = patrimonio
            self._daily_frozen_reason = None  # dia novo: reset automatico

        if month_key != self._monthly_ref_month:
            self._monthly_ref_month = month_key
            self._monthly_ref_equity = patrimonio
            # trava mensal NAO reseta aqui, de proposito (ver docstring).

        # perda diaria: comparacao contra a base do dia (que pode ter acabado
        # de ser fixada nesta mesma chamada, caso em que a perda e sempre 0).
        assert self._daily_ref_equity is not None
        if self._daily_ref_equity > 0:
            daily_loss = patrimonio / self._daily_ref_equity - 1.0
            if daily_loss < -self.daily_loss_pct:
                self._daily_frozen_reason = (
                    f"perda diaria {daily_loss:.2%} > limite {-self.daily_loss_pct:.2%}"
                )

        # perda mensal: mesma logica, base do mes.
        assert self._monthly_ref_equity is not None
        if self._monthly_ref_equity > 0:
            monthly_loss = patrimonio / self._monthly_ref_equity - 1.0
            if monthly_loss < -self.monthly_loss_pct:
                self._monthly_frozen_reason = (
                    f"perda mensal {monthly_loss:.2%} > limite {-self.monthly_loss_pct:.2%}"
                )

    # ---------- consulta ----------------------------------------------------

    @property
    def is_frozen(self) -> bool:
        """True se uma das duas travas esta acionada agora."""
        return self._daily_frozen_reason is not None or self._monthly_frozen_reason is not None

    @property
    def reason(self) -> str | None:
        """Motivo legivel do congelamento atual, ou None se nao congelado.

        Se as duas travas estiverem ativas ao mesmo tempo, ambas aparecem
        (separadas por '; ') — nao esconde uma pela outra.
        """
        reasons = [r for r in (self._daily_frozen_reason, self._monthly_frozen_reason) if r]
        return "; ".join(reasons) if reasons else None

    # ---------- reset manual --------------------------------------------

    def unfreeze(self) -> None:
        """Reset manual — usado por um humano via CLI depois de revisar.

        Limpa as DUAS travas de uma vez (nao e seletivo): e o botao de "revisei
        a situacao, pode voltar a operar normalmente", nao um reset fino por
        trava.
        """
        self._daily_frozen_reason = None
        self._monthly_frozen_reason = None

    # ---------- persistencia (restart do processo ao vivo) -----------------

    def state(self) -> dict:
        """Estado interno para sobreviver a um restart do processo ao vivo.

        Mesmo padrao de `backtest.withdrawal.WithdrawalPolicy.state()`:
        serializa os atributos privados (prefixo `_`) que reconstroem o
        estado exato. Sem isso, um restart no meio do dia perderia a base de
        comparacao diaria/mensal e o motivo de um congelamento em curso.
        """
        return {k: v for k, v in vars(self).items() if k.startswith("_")}

    def restore(self, state: dict) -> None:
        """Reidrata o estado devolvido por `state()`.

        `_daily_ref_date` e `_monthly_ref_month` sao tuplas. O caminho real
        de persistencia passa por JSON (`json.loads(json.dumps(...))`), que
        nao tem tipo tupla — elas voltam como lista. Sem normalizar de volta
        aqui, a comparacao `day_key != self._daily_ref_date` fica SEMPRE True
        (lista nunca `==` tupla em Python, mesmo com os mesmos elementos):
        todo `observe()` pareceria o primeiro do dia, resetando a trava
        diaria (e recalculando a base) a cada chamada.
        """
        for k, v in state.items():
            setattr(self, k, tuple(v) if isinstance(v, list) else v)
