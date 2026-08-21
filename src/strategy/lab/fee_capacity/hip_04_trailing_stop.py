"""fee_capacity/hip_04 -- travar parte do lucro de um vencedor grande com
stop movel reduz a dependencia de "aguentar o trade de sorte até o fim"?

Contexto (por que esta hipotese, medido 2026-08-21, ANTES deste arquivo)
--------------------------------------------------------------------------
O edge inteiro de `liquid_focus` (16,6 anos, FULL) vem de 3 trades (WEGE3
+134,8%, CSNA3 +36,3%, SBSP3 +23,9%) -- sem eles o resto da carteira da
prejuizo. Hoje a familia so tem DOIS mecanismos de saida: o STOP fixo de
-15% ancorado no preco de ENTRADA (nunca sobe) e a ROTACAO mensal (só troca
se o novo rank-1 tiver score >=15% melhor). NADA protege o lucro JA FEITO
no caminho: um vencedor que sobe 100% pode devolver boa parte disso antes
de a rotacao mensal achar substituto melhor -- o trade so "trava" o ganho
no dia exato em que sai, que pode ser muito depois do pico.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
Um stop MOVEL que so ativa depois de um ganho minimo (`activation_gain`,
ex.: 20% -- nao trava ruido de posicoes normais, só protege vencedores
GRANDES) e a partir dali segue o preco maximo desde a entrada a uma
distancia fixa (`trail_pct`, ex.: 10% do pico) deveria reduzir o quanto um
trade de sorte "devolve" antes de sair, sem mudar QUANDO ou O QUE entra
(mesmo sinal, mesmo universo, mesma rotacao/histerese) -- so acrescenta um
piso que sobe conforme o preco sobe, nunca desce (`AdjustStop` do engine ja
garante isso: "so aceita se new_stop >= current_stop").

O que este arquivo NAO faz: nao muda a entrada, nao muda a rotacao mensal,
nao muda o stop original de -15% (continua valendo enquanto o trailing nao
ativar) -- so acrescenta um `AdjustStop` diario depois que o trade ja foi
bem o suficiente para "ativar" a protecao.

Risco declarado da aposta: travar cedo demais um vencedor GRANDE (como
WEGE3, que subiu 134% sem nunca corrigir 10% do pico ao longo do caminho --
precisa ser medido, nao assumido) cortaria a compra na cabeca justamente do
tipo de trade que sustenta o resultado inteiro. Se a hipotese estiver
errada, isso deve aparecer como CAGR/capital final PIOR no holdout completo
e no FULL, nao ser gratis -- e faria hip_04 REPETIR o erro de
`fee_capacity/hip_02` (cooldown que ajudou em 1 janela e piorou nas 48).

`candidate = False`: mesma razao de toda a familia lab -- so disputa o
ranking automatico depois de julgado no holdout de 48 janelas + FULL.

RESULTADO (holdout completo, 48 janelas + FULL, medido apos este arquivo) -- TROCA, NAO GANHO DE GRACA
-----------------------------------------------------------------------------------------------------------
O risco declarado se confirmou: o WEGE3 (o maior trade do FULL) que rendia
+133,8% (saida por ROTATION_OUT em 2021-03-01) passa a sair em 2020-04-24
por STOP a so +8,6% -- o trailing ativou no primeiro repique pos-fundo da
Covid e foi acionado no recuo seguinte, cortando os outros 11 meses de alta
que fizeram o trade valer. FULL: R$1.368,01 -> R$1.016,72 (CAGR 17,0%->
15,0%). Holdout: mediana 18,6%->11,8% (pior), mas pior-janela -1,6%->-0,5%
e DD -52,8%->-49,2% (melhor) -- reduz um pouco a cauda de risco ao custo de
reduzir a mediana. Nao promovido: e uma troca de risco por retorno, nao uma
melhoria sem custo.
"""
from __future__ import annotations

from strategy.base import AdjustStop
from strategy.lab.fee_capacity.hip_01_concentracao import LiquidFocus


class LiquidFocusTrailingStop(LiquidFocus):
    """`LiquidFocus` + stop movel que ativa apos `activation_gain` de ganho
    e segue o pico a `trail_pct` de distancia. Ver docstring do modulo."""

    name = "liquid_focus_trailing_stop"
    version = "1.0"
    candidate = False

    def __init__(self, activation_gain: float = 0.20, trail_pct: float = 0.10, **kwargs):
        super().__init__(**kwargs)
        self.activation_gain = activation_gain
        self.trail_pct = trail_pct
        self._peak_since_entry: dict[str, float] = {}
        self._prev_open: dict = {}

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        self._close_panels = {t: df["close"] for t, df in panels.items()}

    def on_bar(self, date, open_positions, cash_available):
        for t, pos in open_positions.items():
            if t not in self._prev_open:
                # entrada nova neste ticker -- reinicia o pico rastreado (nao
                # pode herdar o pico de um trade ANTERIOR no mesmo ticker).
                self._peak_since_entry[t] = pos.entry_price

        trailing_actions = []
        for t, pos in open_positions.items():
            closes = self._close_panels.get(t)
            atual = closes.loc[date] if closes is not None and date in closes.index else None
            if atual is None:
                continue
            peak = max(self._peak_since_entry.get(t, pos.entry_price), float(atual))
            self._peak_since_entry[t] = peak
            ganho_do_pico = peak / pos.entry_price - 1.0
            if ganho_do_pico < self.activation_gain:
                continue
            novo_stop = peak * (1.0 - self.trail_pct)
            if pos.current_stop is None or novo_stop > pos.current_stop:
                trailing_actions.append(AdjustStop(ticker=t, new_stop=novo_stop))

        self._prev_open = dict(open_positions)
        return trailing_actions + super().on_bar(date, open_positions, cash_available)
