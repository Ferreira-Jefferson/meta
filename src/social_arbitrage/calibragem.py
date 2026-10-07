"""Calibracao do ledger contra a realidade -- fecha o loop entre o que foi
ESTIMADO na hora de aprovar uma tese (Kelly: `prob_acerto_estimada`,
`payoff_estimado`) e o que foi REALIZADO depois de `Fase.FECHADA`. Mesma
disciplina do resto do repo (`LICOES_DE_PRODUCAO.md`: "resultado de
backtest nunca aferido contra o extrato e' hipotese, nao previsao"), so' que
aqui quem esta sendo calibrado nao e' um motor de execucao -- e' o
JULGAMENTO do dono sobre probabilidade/payoff de uma tese discricionaria.

Nunca reporta so' um numero: toda linha carrega `n`, e proporcao vem sempre
com IC95 (mesma exigencia de `metodo_numero_sem_dispersao` da memoria do
projeto). Com `n` pequeno -- e' o regime normal aqui, teses discricionarias
nao acontecem aos milhares -- o IC e' largo e a linha deve ser lida como
"ainda nao decide nada", nunca como veredito. Ver `LinhaCalibragem.n_baixo`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from social_arbitrage.thesis import Fase, Lente, Thesis

#: Abaixo deste `n`, o IC de Wald (normal) fica pouco confiavel (regra de
#: bolso comum: `n*p` e `n*(1-p)` deveriam ser >= ~5) -- `LinhaCalibragem.
#: n_baixo` usa este piso para marcar a linha, nao para escondê-la.
_N_MINIMO_PARA_IC_CONFIAVEL = 20


def _ic95_proporcao(acertos: int, n: int) -> tuple[float, float] | None:
    """IC95 de Wald (aproximacao normal) para uma proporcao -- mesma familia
    de calculo que `CLAUDE.md` cita para o win% do WDO F1 (z-score contra o
    breakeven). Larga e conhecidamente ruim para `n` pequeno ou proporcao
    perto de 0/1 -- e' um AVISO, nao um motivo para omitir o IC."""
    if n == 0:
        return None
    p = acertos / n
    erro = 1.96 * math.sqrt(p * (1.0 - p) / n)
    return (max(0.0, p - erro), min(1.0, p + erro))


@dataclass(frozen=True)
class LinhaCalibragem:
    """Uma linha do relatorio -- uma lente, ou `"TOTAL"`."""

    grupo: str
    n: int
    vitorias: int
    win_pct: float | None
    ic95_win_pct: tuple[float, float] | None
    ganho_medio_brl: float | None
    perda_media_brl: float | None
    payoff_realizado: float | None
    breakeven_empirico: float | None
    resultado_total_brl: float
    prob_acerto_estimada_media: float | None
    payoff_estimado_medio: float | None
    n_com_estimativa: int

    @property
    def n_baixo(self) -> bool:
        return self.n < _N_MINIMO_PARA_IC_CONFIAVEL

    @property
    def edge_confirmada(self) -> bool:
        """`True` só quando o IC95 do win% fica INTEIRO acima do breakeven
        empírico -- a mesma leitura que `CLAUDE.md` faz do WDO F1 (IC que
        atravessa o breakeven não decide nada, para nenhum dos dois lados).
        `False` (não "sem edge") quando faltar dado -- ver `edge_indeterminada`."""
        if self.ic95_win_pct is None or self.breakeven_empirico is None:
            return False
        return self.ic95_win_pct[0] > self.breakeven_empirico

    @property
    def edge_indeterminada(self) -> bool:
        """`True` quando não há dado suficiente (sem derrota nenhuma para
        calcular breakeven, ou `n` zero) para julgar `edge_confirmada` --
        distingue "não decide ainda" de "decide que não tem edge"."""
        return self.ic95_win_pct is None or self.breakeven_empirico is None


def _linha_para_grupo(grupo: str, teses: list[Thesis]) -> LinhaCalibragem:
    n = len(teses)
    resultados = [t.resultado_brl for t in teses if t.resultado_brl is not None]
    vitorias_lista = [r for r in resultados if r > 0]
    derrotas_lista = [r for r in resultados if r <= 0]
    vitorias = len(vitorias_lista)
    win_pct = (vitorias / n) if n > 0 else None
    ic95 = _ic95_proporcao(vitorias, n) if n > 0 else None
    ganho_medio = (sum(vitorias_lista) / len(vitorias_lista)) if vitorias_lista else None
    perda_media = (sum(-r for r in derrotas_lista) / len(derrotas_lista)) if derrotas_lista else None
    payoff_realizado = (ganho_medio / perda_media) if (ganho_medio is not None and perda_media not in (None, 0.0)) else None
    breakeven = (perda_media / (ganho_medio + perda_media)) if (ganho_medio is not None and perda_media is not None and (ganho_medio + perda_media) > 0) else None
    com_estimativa = [t for t in teses if t.prob_acerto_estimada is not None]
    prob_media = (sum(t.prob_acerto_estimada for t in com_estimativa) / len(com_estimativa)) if com_estimativa else None
    payoff_medio_estimado = (
        sum(t.payoff_estimado for t in com_estimativa if t.payoff_estimado is not None) / len(com_estimativa)
        if com_estimativa else None
    )
    return LinhaCalibragem(
        grupo=grupo,
        n=n,
        vitorias=vitorias,
        win_pct=win_pct,
        ic95_win_pct=ic95,
        ganho_medio_brl=ganho_medio,
        perda_media_brl=perda_media,
        payoff_realizado=payoff_realizado,
        breakeven_empirico=breakeven,
        resultado_total_brl=sum(resultados),
        prob_acerto_estimada_media=prob_media,
        payoff_estimado_medio=payoff_medio_estimado,
        n_com_estimativa=len(com_estimativa),
    )


def calibrar(teses: list[Thesis]) -> list[LinhaCalibragem]:
    """Uma linha por `Lente` presente + uma linha `"TOTAL"`. Filtra para
    `Fase.FECHADA` internamente -- SEMPRE, mesmo que o chamador passe teses
    em outras fases -- porque uma tese ainda ABERTA nao tem `resultado_brl`
    definitivo, e misturar as duas inflaria/vazaria n sem que o resultado
    signifique nada (censura ao contrario da que `LICOES_DE_PRODUCAO.md`
    descreve para janela de backtest: aqui e' a tese individual que nao
    terminou, nao a janela)."""
    fechadas = [t for t in teses if t.fase == Fase.FECHADA]
    linhas = [
        _linha_para_grupo(lente.value, [t for t in fechadas if t.lente == lente])
        for lente in Lente
        if any(t.lente == lente for t in fechadas)
    ]
    linhas.append(_linha_para_grupo("TOTAL", fechadas))
    return linhas
