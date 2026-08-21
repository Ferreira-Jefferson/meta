"""fee_capacity/hip_02 -- cooldown de rotacao reduz o DD de `liquid_focus`
sem re-tunar o sinal congelado?

Diagnostico (medido 2026-08-21, ANTES deste arquivo)
------------------------------------------------------
`liquid_focus` (hip_01, 1 posicao) passou o holdout de 48 janelas MUITO
melhor que a versao diluida, mas falhou G1/G2/G5 (DD pior -52,8%, 12m pior
-43,9%). Inspecionando os trades da pior janela (inicio 2011-05-01) NENHUMA
perna perdeu mais que exatamente os -15,1% do stop -- ou seja, nao e risco de
gap (o mesmo padrao de HAPV3/DASA3 em `disaster_forced_entry_2026_08_20`, ja
descartado aqui). O que aparece e turnover: 7 das 11 pernas da janela sao
`ExitReason.ROTATION_OUT` (troca de ticker por ranking de momentum, nao
stop), cada uma pagando ~R$3,90 de corretagem fixa (round-trip) sobre uma
base que, apos uma sequencia de trocas ruins, ja encolheu -- o MESMO
mecanismo de arrasto fixo que destruiu as versoes diluidas, so que em escala
menor porque aqui e 1 posicao de ~R$70-100, nao 5-10 fatias de R$10-20.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
Um COOLDOWN minimo antes de aceitar uma troca por ROTATION_OUT (nao por
STOP -- risco real continua saindo na hora) deveria reduzir o NUMERO de
round-trips e portanto o arrasto de corretagem fixa acumulado, sem tocar o
LIMIAR de decisao do sinal (momentum/histerese congelados permanecem
intocados) -- so atrasa a EXECUCAO de uma troca já sinalizada. Custo
declarado: segurar um papel que ja perdeu o rank-1 por mais tempo pode
custar retorno se o papel continuar caindo antes do stop disparar -- se a
hipotese estiver certa, isso deve aparecer como CAGR mediano menor, nao
gratis.

O que este arquivo NAO faz: nao muda o momentum, o dip, a histerese, nem o
universo -- literalmente so atrasa quando uma saida por ROTATION_OUT (nunca
por STOP) e executada, e so quando ha exatamente 1 posicao (`sleeve_count`
do pai). Assume sleeve_count=1 -- nao generaliza para N sleeves (ver
docstring de `on_bar`).

`candidate = False`: mesma razao de `liquid_focus` -- experimental, nao
disputa o ranking automatico.

RESULTADO (holdout completo, 48 janelas, medido apos este arquivo) -- REFUTADA
-------------------------------------------------------------------------------
Na UNICA janela usada para diagnosticar (inicio 2011-05-01, a pior de
`liquid_focus`), o cooldown ajudou bastante: DD -52,8%->-34,5%, 12m
-42,5%->-32,6%, capital final R$136->R$188. Nas 48 janelas do holdout
completo, o efeito INVERTE: pior CAGR -1,6%->-8,3%, DD pior -52,8%->-56,7%,
12m pior -43,9%->-50,9%, pior capital R$92,28->R$64,92, e passa a perder do
IBOV em 1 das 48 janelas (antes batia em todas). Mediana de CAGR tambem cai
(18,6%->15,8%).

Le-se assim: segurar uma posicao que ja perdeu o rank-1 por mais tempo
ajuda quando o papel se recupera antes do stop, mas piora quando ele so
continua caindo -- e no conjunto das 48 janelas o segundo caso pesa mais que
o primeiro. Diagnosticar em UMA janela e medir so nela teria produzido uma
conclusao errada na direcao contraria -- exatamente o motivo de medir no
holdout completo antes de declarar qualquer coisa "resolvida".
"""
from __future__ import annotations

from core.models import ExitReason
from strategy.base import Exit
from strategy.lab.fee_capacity.hip_01_concentracao import LiquidFocus


class LiquidFocusCooldown(LiquidFocus):
    """`LiquidFocus` (1 posicao) + cooldown minimo antes de aceitar uma
    saida por ROTATION_OUT -- ver docstring do módulo para a hipótese."""

    name = "liquid_focus_cooldown"
    version = "1.0"
    candidate = False

    def __init__(self, min_hold_bars: int = 63, **kwargs):
        # 63 pregoes ~ 3 meses -- mesma ORDEM DE GRANDEZA da "confirmacao de
        # 2 meses" já existente na família (ver docstring de `liquid_sleeves5.
        # LiquidSleeves5`), não um número escolhido olhando este backtest.
        super().__init__(**kwargs)
        self.min_hold_bars = min_hold_bars

    def on_bar(self, date, open_positions, cash_available):
        """Filtra `Exit(ROTATION_OUT)` de posições ainda "novas" (menos de
        `min_hold_bars` pregões) -- e, junto, qualquer `Enter` do mesmo
        pregão, porque com `sleeve_count=1` há no máximo UM par saída/entrada
        por vez: se a saída foi vetada, a entrada que dependia da vaga
        liberada também não deve acontecer (o caixa continua preso na
        posição que ficou). `Exit(STOP)`/outros motivos nunca são filtrados
        -- controle de risco real não espera cooldown nenhum."""
        actions = super().on_bar(date, open_positions, cash_available)

        vetadas = {
            a.ticker for a in actions
            if isinstance(a, Exit) and a.reason == ExitReason.ROTATION_OUT
            and a.ticker in open_positions
            and open_positions[a.ticker].bars_held < self.min_hold_bars
        }
        if not vetadas:
            return actions
        # Descarta a(s) saida(s) vetada(s) e QUALQUER entrada deste pregao --
        # com sleeve_count=1 so existe um par saida/entrada por vez, e a
        # entrada so existe porque a saida (vetada) liberaria a vaga.
        return [a for a in actions if isinstance(a, Exit) and a.ticker not in vetadas]
