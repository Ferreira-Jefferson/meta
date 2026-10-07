"""`win_busca_lucro_g22_retangulo_filtro_amplitude` -- Geracao 22 da busca por
EA lucrativo de day trade do WIN
(`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`, ver
`ORQUESTRACAO.md`).

## Por que esta geracao existe

Tres familias de sinal independentes desta busca (ORB/G8/G18, confirmacao
cruzada WIN x WDO/G4/G17/G20, retangulo/lateralizacao/G21) chegaram a OOS-1
com liquido positivo mas CONCENTRACAO que sempre PIORA da janela de
desenvolvimento para a de validacao (G4: 59%->240%; G20: 38,5%/58,4%->
467%/696%; G21: 41%/64%->97,2%/133,4%). A pergunta desta geracao: existe
algum proxy observavel ANTES do pregao (ou nos primeiros minutos dele) que
preveja se aquele PREGAO INTEIRO vai ser de regime favoravel para o
retangulo da G21, em vez de continuar variando geometria sobre o MESMO
gatilho?

## O que foi testado e o que sobreviveu

`g22_is_estratificacao.py` rodou a G21 vencedora (stop=0,45xL/alvo=2,0x,
capital R$1.000) UMA UNICA VEZ sobre o IS (jan-jun/2026), sem filtro de dia
nenhum, e particionou POS-HOC (nunca simulacoes exclusivas -- item 6.50 de
LICOES_DE_PRODUCAO.md) os MESMOS 562 trades ja ocorridos por 4 proxies
diarios causais:

  (a) `amplitude_ontem` -- high-low do pregao ANTERIOR do WIN@ (3 tercis)
  (b) `gap_abertura` -- |abertura hoje - fechamento ontem| do WIN@ (3 tercis)
  (c) `dia_semana` -- segunda/sexta vs ter-qui (2 grupos)
  (d) `wdo_range_abertura` -- high-low dos 1os 30min do WDO@ no mesmo dia (3 tercis)

So' (a) separou de forma MONOTONICA, sem reversao, com significancia real
(teste de permutacao sobre a serie DIARIA de liquido, nao sobre trade --
item 6.49: p=0,0040): tercio baixo (amplitude_ontem<2558,3pts) deu
-R$14,93/pregao (win 30,2%, abaixo do BE empirico 34,4%); tercio medio
+R$17,37/pregao; tercio alto (amplitude_ontem>3680,0pts) +R$67,25/pregao
(win 42,7%, BEemp 33,8%, IC95 [36,7%;48,9%] -- margem de 2,9pp acima do
BEemp, MAIOR que qualquer margem ja medida em toda a busca G1-G21). Os
outros 3 proxies (b/c/d) nao separaram de forma distinguivel de ruido
(p=0,09/0,997/0,74) -- consistente com o historico do projeto (REGRAS.md ja
tinha refutado dia-da-semana e gap em outros contextos).

Dois filtros candidatos foram avaliados em `g22_candidato_filtro_
amplitude.py` com os limiares CONGELADOS (numeros absolutos em pontos, NUNCA
recalculados sobre o OOS): "so_tercio_alto" (amplitude_ontem>3680,0pts, opera
40/122 dias do IS) e "excluir_tercio_baixo" (amplitude_ontem>2558,3pts, opera
81/122 dias). **Esta classe implementa "excluir_tercio_baixo"**, escolhido
por ter a MELHOR concentracao dos dois (top3/liq=32%, top5/liq=50%, contra
41%/61% do outro candidato e 41%/64% da G21 sem filtro) e o maior liquido
total (R$3.402,00 contra R$2.690,00), mantendo IC95 do win% com folga real
acima do BE empirico (1,9pp) e p_ruina baixo (1,9%). O candidato mais
agressivo ("so_tercio_alto": margem estatistica ainda maior, 2,9pp, p_ruina
0,4%, mas so' 1/3 dos dias e concentracao pior que o escolhido) fica
registrado como alternativa para uma geracao futura, nao testado no OOS-1
por protocolo (um so' candidato promovido por vez).

## Arquitetura: filtro de PREGAO, nao de BARRA

O proxy e' uma funcao pura module-level (`dias_elegiveis_por_amplitude`,
OHLCV do WIN@ completo -> conjunto de dias elegiveis), calculada FORA do
motor e entregue PRONTA ao construtor como `frozenset[date]` -- mesmo padrao
arquitetural de `wdo_anomalo`/`wdo_direcao` da G4 (dado causal pre-computado
fora do loop; `on_bar` so' faz lookup, nenhum calculo cruzado roda dentro do
motor). `on_session_start` decide, uma vez por pregao, se a sessao esta
HABILITADA; se nao estiver, `on_bar` devolve `[]` o pregao inteiro sem
chamar a logica da G21 (nem a deteccao de retangulo roda -- o filtro e'
aplicado ANTES da deteccao, nao depois, porque o proxy usa dado do pregao
ANTERIOR, disponivel desde a abertura de hoje).

Nenhuma logica de deteccao/geometria foi reimplementada: esta classe
SUBCLASSEIA `WinBuscaLucroG21Retangulo1000` e sobrescreve so' `on_session_
start`/`on_bar` para aplicar o filtro -- a geometria vencedora (stop=
0,45xL/alvo=2,0x) e toda a deteccao de retangulo (`detecta_retangulo`,
import transitivo via a classe-mae) permanecem EXATAMENTE as mesmas, sem
retune.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)

#: Limiar CONGELADO no IS (jan-jun/2026, `g22_is_estratificacao.py` ->
#: `g22_candidato_filtro_amplitude.py`) -- tercio 1/3 x 2/3 de
#: `amplitude_ontem` sobre os 122 pregoes do IS. NUNCA recalculado sobre o
#: OOS-1/OOS-2: o mesmo numero absoluto (pontos) e' aplicado tal como esta'.
LIMIAR_AMPLITUDE_ONTEM_PONTOS = 2558.3


def dias_elegiveis_por_amplitude(dias: list[date], win_full: pd.DataFrame,
                                  limiar_pontos: float = LIMIAR_AMPLITUDE_ONTEM_PONTOS,
                                  ) -> frozenset[date]:
    """Funcao pura module-level (OHLCV -> decisao, sem I/O, sem banco --
    AGENTS.md regra 2): para cada dia de `dias`, calcula `amplitude_ontem`
    (high-low do PREGAO ANTERIOR do WIN@ na serie `win_full`, que deve cobrir
    pelo menos 1 pregao antes do primeiro dia de `dias`) e devolve o
    subconjunto de `dias` com `amplitude_ontem > limiar_pontos`. Causal por
    construcao: so' olha o pregao que ja terminou antes de `dias[i]` comecar.
    """
    todos_dias = sorted(set(win_full.index.date))
    pos = {d: i for i, d in enumerate(todos_dias)}
    elegiveis = []
    for d in dias:
        i = pos.get(d)
        if i is None or i == 0:
            continue
        dia_anterior = todos_dias[i - 1]
        fatia = win_full[win_full.index.date == dia_anterior]
        if not len(fatia):
            continue
        amplitude = float(fatia["high"].max() - fatia["low"].min())
        if amplitude > limiar_pontos:
            elegiveis.append(d)
    return frozenset(elegiveis)


class WinBuscaLucroG22RetanguloFiltroAmplitude(WinBuscaLucroG21Retangulo1000):
    """`WinBuscaLucroG21Retangulo1000` (retangulo, stop=0,45xL/alvo=2,0x,
    capital R$1.000) + filtro de PREGAO: so' opera em dias cujo
    `amplitude_ontem` (pre-computado, ver `dias_elegiveis_por_amplitude`)
    exceda `LIMIAR_AMPLITUDE_ONTEM_PONTOS`. Fora disso, comportamento
    IDENTICO a G21 -- mesma execucao fechada, mesma deteccao, mesma
    geometria, 1 contrato fixo."""

    name = "win_busca_lucro_g22_retangulo_filtro_amplitude"
    version = "1.0.0"

    def __init__(self, dias_habilitados: frozenset, **kwargs) -> None:
        super().__init__(**kwargs)
        if not dias_habilitados:
            raise ValueError(
                "dias_habilitados vazio -- esta classe exige o conjunto "
                "pre-computado por dias_elegiveis_por_amplitude(), nunca "
                "calcula o proxy sozinha (a logica de sinal precisa "
                "continuar pura, AGENTS.md regra 2)")
        self.dias_habilitados = frozenset(dias_habilitados)
        self._sessao_habilitada = False

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._sessao_habilitada = session_date in self.dias_habilitados

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if not self._sessao_habilitada:
            return []
        return super().on_bar(ts, bar, positions, session_pnl_brl)
