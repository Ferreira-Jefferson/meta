"""LiquidFlow5 — cinco sleeves de universo continuo, uma conta. Sem cadencia.

Mesma composicao de `strategy/liquid_sleeves5.py` (cinco sleeves disjuntos, 20%
do capital em cada, caixa compartilhado, posse rastreada por `_owner`), trocando
apenas de onde cada sleeve pode escolher: em vez do top-20 refeito a cada N
meses, o top-20 reavaliado todo fim de mes com banda de rank 20/30 — ver
`strategy/liquid_flow.py` para o porque.

O ganho nao e de capital, e de honestidade: `refresh_months` era um parametro
que as cinco janelas de teste nao conseguiam escolher (so uma das quatro
metricas era monotona nele), e todo parametro que a evidencia nao escolhe e um
grau de liberdade esperando para ser sobreajustado. Aqui ele nao existe.

`exit_rank=30` sobre `universe_n=20` e uma banda de 50%, no mesmo espirito da
histerese de 15% que a familia usa para rotacao — nao foi varrida em grid de
proposito, justamente para nao reintroduzir pela porta dos fundos o parametro
que este arquivo elimina.
"""
from __future__ import annotations

from strategy.liquid_flow import LiquidFlowSleeve
from strategy.liquid_sleeve import LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5


class LiquidFlow5(LiquidSleeves5):
    """Cinco sleeves com universo liquido continuo (banda 20/30), numa conta."""

    name = "liquid_flow5"
    version = "1.0"
    # Fora do podio desde 2026-08-20, por decisao explicita do usuario: o pódio
    # passou a ter um robo so, o `liquid_champion`.
    #
    # O custo desta escolha esta declarado aqui para nao virar surpresa depois:
    # este desenho perdeu a regra de universo por margem ESTREITA (ganha o
    # pior-12m no holdout, -25,8% contra -29,7%, e e menos sensivel ao dia do
    # rebalanceamento, CV 13,4% contra 20,1%). Enquanto estava candidato, uma
    # virada dele apareceria sozinha no ranking a cada refresh. Fora do pódio,
    # nao aparece: se a banda de rank voltar a ser melhor, ninguem vai notar sem
    # alguem rodar de proposito. Para voltar a medir, basta `candidate = True`.
    candidate = False

    def __init__(self, exit_rank: int = 30, **kwargs):
        self._exit_rank = exit_rank
        super().__init__(**kwargs)

    def _make_sleeve(self, **kwargs) -> LiquidSleeve:
        # `refresh_months` chega da assinatura do pai e nao tem uso aqui: o
        # universo continuo nao tem cadencia. Descartar explicitamente e melhor
        # que aceitar em silencio — um parametro que parece configuravel e nao
        # faz nada e pior que um parametro ausente.
        kwargs.pop("refresh_months", None)
        return LiquidFlowSleeve(exit_rank=self._exit_rank, **kwargs)
