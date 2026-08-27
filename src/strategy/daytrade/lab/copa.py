"""`Copa` — o despachante por ATIVO da familia da Copa BTG Trader.

Decisao do dono (2026-08-24): "o robo nao deve ter uma estrategia que funcione
pros dois ativos, ele tem que entender qual ativo foi selecionado e usar a
melhor estrategia para aquele ativo".

Isso nao e' preferencia: e' o que a economia MEDIDA dos dois instrumentos
obriga. A mesma tarifa de R$0,50 por round-trip vale meio tick no WIN e um
decimo de tick no WDO, e o range diario e' de ~594 ticks contra ~99. Um alvo
de 1 tick nasce negativo num e sobra 90% no outro. Nenhum conjunto de
parametros serve para os dois — o desenho tem de ser por ativo: `CopaWin`
(rompimento, poucos trades grandes) e' a resposta medida para WIN@. A
tentativa equivalente para WDO@ (`CopaWdo`, grade maker de muitos trades
pequenos) zerou a conta sob capital real de day trade (R$300, margem R$150
x2) no 4o pregao de 123 e foi removida em 2026-08-27 -- WDO@ hoje NAO tem
estrategia propria registrada nesta familia.

`Copa` e' so' a porta: recebe o simbolo e o teto de contratos e devolve a
instancia certa. Simbolo sem estrategia propria LEVANTA, do mesmo jeito que
`Gremah`/`GremahTick` recusam simbolo sem calibracao medida (ver
`strategy/daytrade/lab/gremah_tick.py`) -- herdar em silencio a estrategia de
outro ativo e' exatamente o erro que a decisao acima proibe.

## Por que `__new__`, e nao uma funcao `criar_copa(...)`

Para o chamador ficar identico ao de qualquer outro robo do repo
(`Copa(symbol=..., teto_contratos=...)`, como `Gremah(symbol=...)`). A
alternativa de uma classe que DELEGA cada hook (`on_bar`, `on_session_start`,
os tres `seed_*`, `on_capital_update`) seria uma camada a mais em que um hook
esquecido vira um robo que silenciosamente nao recebe o dado que precisa --
e' exatamente esse o tipo de divergencia que `AGENTS.md` regra 6 existe para
impedir. Aqui nao ha' o que esquecer: a instancia devolvida E' o robo.
"""
from __future__ import annotations

from strategy.daytrade.base import IntradayStrategy
from strategy.daytrade.lab.copa_win import CopaWin

#: Um arquivo por estrategia (`AGENTS.md`), um simbolo por estrategia. Crescer
#: esta tabela significa MEDIR o ativo novo do zero (IS + confirmacao OOS),
#: nunca apontar um simbolo novo para uma classe existente.
#:
#: `CopaWdo` (WDO@) foi removida em 2026-08-27: zerou a conta sob capital
#: real de day trade no 4o pregao de 123 (rerun com R$300 de capital,
#: margem R$150 x `MARGIN_BUFFER_FUTUROS`). WDO@ nao tem estrategia propria
#: registrada nesta familia ate' que uma nova seja medida do zero.
ESTRATEGIA_POR_SIMBOLO: dict[str, type[IntradayStrategy]] = {
    CopaWin.symbol: CopaWin,
}


class Copa:
    """Despachante. `Copa(symbol="WIN@", teto_contratos=12)` devolve um
    `CopaWin`. `Copa(symbol="WDO@", ...)` LEVANTA `ValueError` -- WDO@ nao
    tem estrategia propria registrada nesta familia (ver `CopaWdo`, removida
    em 2026-08-27 por zerar a conta sob capital real).

    `teto_contratos` e' obrigatorio e viaja para o robo escolhido: o teto e'
    ENTRADA de configuracao, porque os numeros de 2025 (WIN 15 / WDO 5) podem
    mudar antes de 14/09/2026. Qualquer outro parametro passa adiante para o
    construtor do robo -- e' assim que a varredura de parametros funciona sem
    a grade precisar saber qual classe esta do outro lado."""

    def __new__(cls, symbol: str, teto_contratos: int, **kwargs) -> IntradayStrategy:
        classe = ESTRATEGIA_POR_SIMBOLO.get(symbol)
        if classe is None:
            raise ValueError(
                f"copa: sem estrategia propria para o simbolo {symbol!r}. "
                f"Disponiveis: {', '.join(sorted(ESTRATEGIA_POR_SIMBOLO))}. "
                "A estrategia NAO transfere entre ativos (a economia de cada "
                "instrumento e' outra) -- meca o ativo novo (IS + confirmacao "
                "OOS) e escreva a classe dele antes de operar."
            )
        return classe(symbol=symbol, teto_contratos=teto_contratos, **kwargs)

    @staticmethod
    def simbolos() -> tuple[str, ...]:
        """Ativos com estrategia propria medida, na ordem declarada."""
        return tuple(ESTRATEGIA_POR_SIMBOLO)
