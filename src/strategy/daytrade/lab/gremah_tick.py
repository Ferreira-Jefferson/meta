"""GREMAH_TICK -- porte da `Gremah` (`strategy/daytrade/lab/gremah.py`) para
rodar tick a tick (trade ticks reais, ver `market_data_intraday/
mt5_ticks_source.py`) em vez de barra M1. EXPLORATORIO (2026-08-22), pedido
do dono para ver o comportamento do desenho na menor granularidade que o MT5
oferece -- nao substitui a `Gremah` original, e' um robo PROPRIO (AGENTS.md:
uma estrategia por arquivo).

O DESENHO e' o mesmo: grade de niveis ao redor do preco, ancora FIXA (preco
de abertura) ate `fixed_anchor_until`, ROLANTE (preco do momento) depois;
ordem-limite parada esperando o preco vir ate ela (maker); alterna os lados;
teto de perda diaria; tamanho de posicao crescendo com o caixa acumulado. O
motor (`backtest.intraday.machine`) nao muda uma linha -- ele so' conhece
`Bar` (ts/open/high/low/close/volume) e decide toque via
`bar.low <= nivel <= bar.high`. Um tick vira `Bar` com
`open=high=low=close=preco_negociado` (ver `ticks_to_bars` em
`scripts/daytrade/run_backtest_ticks.py`): um negocio e' um evento atomico, a
um preco so', entao o "range" da barra degenera para um ponto -- e isso e'
estritamente MAIS PRECISO que M1, nao uma aproximacao: no M1 duas coisas
(stop e alvo) podem ter tocado na mesma barra sem saber qual foi primeiro
(`IntradayBacktestConfig.ambiguous_bar_resolution` existe so' por causa
disso); com tick, so' um preco acontece por vez, entao essa ambiguidade
desaparece por construcao.

DOIS parametros da `Gremah` original sao contados em BARRAS, o que so' faz
sentido quando toda barra dura o MESMO tempo (1 minuto). Tick nao tem
cadencia fixa -- pode vir 1 negocio em 3 segundos ou nenhum em 3 horas (medido
2026-08-22 na PMAM3, papel ilíquido). Os dois foram RECONTADOS em tempo de
parede:

  1. `rolling_reanchor_after_bars` (30 barras M1 = 30 min) virou
     `rolling_reanchor_after_seconds` -- compara `ts` do tick atual contra o
     `ts` de quando a ordem foi armada, em vez de contar quantas vezes
     `on_bar` rodou.
  2. O teto de posicao (`RollingVolumeWindow`, `strategy/daytrade/base.py`)
     e' resolution-agnostic por construcao: soma volume por EVENTO (tick ou
     barra) dentro de uma janela de TEMPO (30 minutos por default), nao de
     contagem de eventos -- um tick e' so' um evento menor que uma barra
     M1, a formula nao muda. E' a MESMA classe que a `Gremah` M1 usa desde
     2026-08-22 (ver a docstring dela para o motivo da media movel
     substituir o antigo teto congelado no primeiro minuto).

O QUE NAO MUDOU, porque a formula ja e' resolution-independent: `profit_pct`/
`stop_multiplier` continuam sendo PERCENTUAL do preco de ancora, convertido
para ticks (`_ticks_from_pct`); `max_trades_per_side` continua sendo
CONTAGEM DE TRADES (nao de barras); o teto de perda diaria continua sendo
fracao de `capital_minimo_brl`, verificado a cada evento (agora por tick, o
que so' torna o stop MAIS responsivo, nunca menos).

CALIBRACAO: `_CALIBRATION_BY_SYMBOL_TICK` abaixo comeca com os MESMOS numeros
de `gremah._CALIBRATION_BY_SYMBOL` -- ponto de partida, NAO validacao. Esses
pares foram medidos bar a bar de 1 minuto; tick muda quantos fills acontecem
por dia e QUANDO (um nivel que uma barra M1 "tocaria" sem preencher de
verdade dentro do minuto agora so' preenche se um negocio real bateu nele).
Antes de tratar um resultado tick como decisao, repetir os MESMOS 4 passos
de medicao da `gremah.py` (regime de preco, varredura fina IS, confirmacao
OOS) com dado de tick -- herdar o numero do M1 sem medir de novo e' o
EXATO erro que aquele arquivo documenta ter sido cometido e corrigido antes.

PMAM3, BMGB4, KLBN3, LPSB3, DASA3, KLBN4, PCAR3, CSAN3 e GRND3 ja
passaram pelos 4 passos EM TICK -- ver `TICK_CONFIRMED_SYMBOLS`. CLSC4
tambem esta' na lista, mas por um caminho diferente: confirmada em OOS,
NAO pelos 4 passos completos (amostra pequena demais no IS pra
diferenciar qualquer parametro) -- ver o paragrafo dela mais abaixo.

PMAM3 foi medida 2x, a unica com historico de duas rodadas:

  1a medicao (2026-08-22, capital de teste R$100 fixo): a varredura IS
  sugeriu pares "melhores" que 0,32%/10x (ex.: 0,25%/15x), mas a confirmacao
  OOS mostrou 0,25%/15x e 0,32%/10x produzindo o MESMO resultado exato (337
  trades, R$1.074,63) -- ao preco de PMAM3 (~R$0,13-0,15), varios
  percentuais diferentes arredondam pro MESMO numero de ticks
  (`_ticks_from_pct`), entao a "melhora" da varredura era em boa parte
  ilusao de arredondamento. Conclusao daquela rodada: manter 0,32%/10x.

  2a medicao (2026-08-23, caixa REAL -- pedido do dono, "sempre rode com o
  caixa minimo para cada ativo"): com `capital_minimo_brl` em vez de R$100
  fixo, o IS mostrou 0,32%/20x (MESMO alvo, stop MAIOR) batendo o par
  antigo de forma nao-trivial (R$739,93 vs R$671,03 no IS), e a confirmacao
  OOS (2026-06-15..2026-08-21) CONFIRMOU: R$325,76 vs R$310,41 (+4,9%),
  MaxDD tambem menor (-11,7% vs -12,0%). Substitui o par de 2026-08-22 --
  o caixa de teste fixo mascarava esta melhora, mesmo motivo documentado em
  `gremah._VOLATILITY_OVERRIDE_BY_SYMBOL` para a KLBN4 em M1.

BMGB4 e KLBN3 (2026-08-23, mesma rodada -- IS+OOS, percentual E
volatilidade, caixa real): o mesmo par percentual 0,15%/10x bateu o
herdado do M1 nos dois, IS e OOS (BMGB4 +0,4% no OOS; KLBN3 +8,9% no OOS,
custando um pouco mais de MaxDD: -1,3%->-1,9%) -- ver a tabela abaixo.

LPSB3 (mesma rodada): candidato de volatilidade (k=0,05/s=30) venceu no IS
mas PIOROU no OOS (-0,4%); o par herdado do M1 fica, agora CONFIRMADO em
vez de so' herdado (a medicao testou e o par antigo se manteve).

DASA3, KLBN4 e PCAR3 (2026-08-23, mesma rodada de caixa real -- a
varredura completa de 10 simbolos tinha sido cancelada por tempo antes
disso, ver o paragrafo seguinte; estes 3 foram medidos numa rodada
separada, so' com eles): DASA3 0,15%/20x bateu o herdado 0,21%/10x no IS
(R$1.138,38 vs R$923,52) e CONFIRMOU no OOS (R$884,86 vs R$851,73, +3,9%,
MaxDD tambem menor). KLBN4 0,15%/5x bateu 0,21%/5x no IS (R$3.056,52 vs
R$1.548,23, quase o dobro) e CONFIRMOU no OOS (R$1.296,51 vs R$1.178,42,
+10,0%) -- o maior ganho OOS de toda a rodada de recalibracao tick.
PCAR3 0,20%/8x bateu 0,21%/10x no IS (R$986,27 vs R$943,30) mas EMPATOU
byte-a-byte no OOS (R$334,65 nos dois, 19 trades, 49 dias pulados nos
dois) -- ao preco da PCAR3 no periodo OOS (~R$1,60) os dois pares
arredondam para o mesmo numero de ticks, mesma ilusao de arredondamento
que a 1a medicao da PMAM3 documentou. Par herdado fica, agora CONFIRMADO
em vez de so' herdado.

  Investigacao extra da PCAR3 (2026-08-23, pedido do dono desconfiando do
  MaxDD): numa janela BEM mais longa (2025-12-16..2026-06-12, ainda dentro
  do IS, so' um corte de data comum pra comparar com outros simbolos), o
  par herdado (0,21%/10x) mostrou MaxDD de -17,6% -- pior que TODOS os
  candidatos testados naquela janela, inclusive em capital final. O
  melhor da janela longa (0,15%/8x, R$1.343,82 vs R$1.129,40, MaxDD
  -10,3% vs -17,6%) foi retestado no OOS CONGELADO de verdade e PIOROU
  (-7,8%, MaxDD -5,9%) -- nao generalizou. Confirma que o OOS curto da
  PCAR3 (so' 19 trades) nao tem poder estatistico pra distinguir
  candidatos, mas tambem confirma que otimizar numa janela maior sem
  reconfirmar no OOS de verdade teria trocado um problema por outro.
  Dono decidiu manter o par herdado (0,21%/10x) -- nao adotar 0,15%/8x.

CSAN3 (2026-08-23, varredura rodou so' nos ultimos 500 mil negocios do
IS -- 2,86 milhoes no total e' pesado demais pra grade inteira em tempo
razoavel, ver `scripts/daytrade/sweep_gremah_tick.py --tail-ticks`):
0,15%/5x bateu o herdado 0,21%/20x no IS (R$1.222,17 vs R$1.164,58) E no
OOS (R$1.245,29 vs R$969,17, +28,5%, MaxDD tambem menor: -1,2% vs
-2,2%), com o dobro de trades -- sem ilusao de arredondamento, a maior
melhora confirmada da rodada.

GRND3 (2026-08-23, varredura completa -- so' 755 mil negocios, nao
precisou de corte): candidato de volatilidade B k=0,05/s=8 bateu o
percentual herdado do M1 (0,21%/5x) no IS (R$2.623,63 vs R$1.437,30,
quase o dobro) E no OOS (+30,9%, MaxDD tambem menor: -0,8% vs -2,0%) --
ver `_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`. Primeiro simbolo confirmado
em tick com par de volatilidade, nao percentual; o par quase coincide
com o que a `Gremah` M1 ja usa para este simbolo (k=0,05/s=10), boa
confirmacao cruzada entre os dois motores.

CLSC4 (2026-08-23, testada com o parametro dos outros 9 confirmados, nao
com varredura propria): no IS (8.028 negocios, 2025-05-12..2026-06-12) TODOS
os candidatos deram so' 2-4 trades -- amostra pequena demais pra
diferenciar qualquer parametro, o herdado (0,42%/10x) empata com o da
LPSB3 e vence o resto por acaso, nao por medicao. No OOS (2026-06-15..
2026-08-21, preco subiu de R$83,58 pra R$137,19) o quadro muda: o par da
PCAR3 (0,21%/10x) da 27 trades contra so' 1 do herdado, e capital final
maior (R$28.238,79 vs R$27.369,35). Dono decidiu adotar 0,21%/10x vendo
essa diferenca -- e' uma escolha a partir do OOS SEM confirmacao previa
no IS (o inverso do protocolo normal: aqui foi o holdout que
diferenciou, nao o treino). Dono pediu para marcar como CONFIRMADA EM
OOS mesmo assim (2026-08-23) -- esta' em `TICK_CONFIRMED_SYMBOLS`, mas
por um caminho diferente dos outros 9: decisao explicita do dono a
partir do OOS, nao medicao pelos 4 passos completos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from statistics import median

import math

import pandas as pd

from strategy.daytrade.base import (
    LOTE_PADRAO_B3,
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    JanelaVolatilidadeDiaria,
    RollingVolumeWindow,
    capital_minimo_brl,
)

#: Mesmo default de `gremah.VOL_JANELA_DIAS_PADRAO` -- ver a docstring la para
#: o motivo (nao repetida aqui).
VOL_JANELA_DIAS_PADRAO = 10

#: Mesmos defaults de `gremah.py` -- ver as constantes homonimas la para a
#: justificativa completa de cada numero (nao repetida aqui).
SESSION_STOP_FRACAO_PADRAO = 0.20
REALOCACAO_LIMIAR_CAIXA_PADRAO = 4.0
REALOCACAO_TETO_PCT_VOLUME_MINUTO_PADRAO = 0.10
#: Janela (minutos) da media movel de volume que alimenta o teto acima --
#: MESMO mecanismo da `Gremah` M1 (`strategy.daytrade.base.
#: RollingVolumeWindow`), reavaliado a CADA sinal de entrada. Ate 2026-08-22
#: este robo usava uma janela de acumulo unica (60s) desde a abertura,
#: congelada assim que fechasse -- substituido no mesmo dia (pedido do dono,
#: mesma mudanca aplicada na `Gremah`) por uma media MOVEL, que tambem
#: completa com a cauda do pregao ANTERIOR enquanto a sessao de hoje ainda
#: nao acumulou a janela inteira sozinha. Ver a constante homonima em
#: `gremah.py` para a medicao (so' feita em M1) que decidiu 1min em vez de
#: 30min -- o pedido original (2026-08-22) cobria os DOIS robos, entao o
#: mesmo valor foi aplicado aqui sem remedir em tick.
REALOCACAO_JANELA_MINUTOS_PADRAO = 1.0
#: Equivalente em tempo dos "30 barras M1" que `Gremah.rolling_reanchor_
#: after_bars` usa por default (30 minutos).
ROLLING_REANCHOR_SEGUNDOS_PADRAO = 30.0 * 60.0

#: Teto de pedacos que `dividir_entrada=True` cria para UMA entrada --
#: generico o bastante pra nao fragmentar demais um papel iliquido (PMAM3
#: chega a ter horas sem negocio nenhum: um numero de pedacos gigante so'
#: aumentaria o tempo ate' o ultimo casar, sem ganho real). So' tem efeito
#: com `IntradayBacktestConfig.limit_fill_capped_by_volume=True` -- sem o
#: cap, o motor preenche tudo de uma vez de qualquer jeito (ver
#: `IntradaySessionMachine._resolve_limit_fills`), entao dividir a ordem nao
#: muda nada. `dividir_entrada` virou padrao `True` 2026-08-23 (pedido do
#: dono, depois de medir IS/OOS -- ver a memoria `dividir_entrada_is_oos_
#: 2026_08_23` do projeto: inverte de sinal entre IS e OOS na GremahTick,
#: mas o dono decidiu ligar mesmo assim -- "no teste e tudo lindo, por isso
#: temos o OOS, pra chegar mais proximo da verdade").
DIVIDIR_MAX_PECAS_PADRAO = 8

#: Barras (1 negocio real cada, aqui -- NAO 1 minuto, ver `Gremah.
#: EXIT_TTL_BARS_PADRAO`) que uma fatia de SAIDA espera antes de virar ordem
#: a mercado pelo restante (`EnterLimit.exit_ttl_bars`) -- so' tem efeito com
#: `dividir_entrada=True`. Decidido 2026-08-23 apos varrer 1..10 em PMAM3
#: (IS+OOS, Gremah E GremahTick -- ver a memoria `exit_ttl_bars_decisao_
#: 2026_08_23` do projeto): ttl curto (1-3) e' estruturalmente pior em quase
#: toda metrica, 8 e' o melhor ou quase melhor ponto nas duas janelas (MaxDD
#: -6,68%/-12,00%, os mais baixos ou quase da faixa toda), e ir alem de 8 nao
#: e' monotonico. MESMA constante e mesmo motivo de `DIVIDIR_MAX_PECAS_PADRAO`
#: acima.
EXIT_TTL_BARS_PADRAO = 8


@dataclass(frozen=True)
class _SymbolCalibrationTick:
    profit_pct: float
    stop_multiplier: float


# PONTO DE PARTIDA copiado de `gremah._CALIBRATION_BY_SYMBOL` (medido em M1,
# 2026-08-21/22) -- ver o AVISO no topo do modulo. Nao adicionar simbolo aqui
# sem repetir a medicao propria em tick.
_CALIBRATION_BY_SYMBOL_TICK: dict[str, _SymbolCalibrationTick] = {
    # CONFIRMADO em tick, unico da tabela -- medido 2x (2026-08-22 e
    # 2026-08-23, ver o aviso no topo do modulo). stop_multiplier=20.0
    # (nao 10.0) desde 2026-08-23: caixa de teste real revelou uma melhora
    # que o caixa fixo de R$100 mascarava (+4,9% no OOS).
    "PMAM3": _SymbolCalibrationTick(profit_pct=0.0032, stop_multiplier=20.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/5x bateu o par herdado do M1
    # (0,21%/5x) no IS (R$3.056,52 vs R$1.548,23, quase o dobro) E no OOS
    # (+10,0%) -- o maior ganho OOS da rodada.
    "KLBN4": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=5.0),
    # CONFIRMADO em tick 2026-08-23 -- varredura fina rodou so' nos ultimos
    # 500 mil negocios do IS (tick da CSAN3 tem 2,86 milhoes, pesado demais
    # pra grade inteira em tempo razoavel -- ver `sweep_gremah_tick.py
    # --tail-ticks`). % 0,15/5x bateu o par herdado do M1 (0,21%/20x) no IS
    # (R$1.222,17 vs R$1.164,58) E no OOS (R$1.245,29 vs R$969,17, +28,5%,
    # MaxDD tambem menor: -1,2% vs -2,2%) -- a maior melhora confirmada da
    # rodada, sem ilusao de arredondamento (o dobro de trades, 1266 vs 618).
    "CSAN3": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=5.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/20x bateu o par herdado do M1
    # (0,21%/10x) no IS (R$1.138,38 vs R$923,52) E no OOS (+3,9%).
    "DASA3": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=20.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,20/8x bateu 0,21%/10x no IS, mas
    # EMPATOU byte-a-byte no OOS (arredondamento de tick no preco da PCAR3
    # no periodo). Par herdado fica, agora com medicao propria.
    "PCAR3": _SymbolCalibrationTick(profit_pct=0.0021, stop_multiplier=10.0),
    # CONFIRMADA EM OOS (2026-08-23) -- mas NAO pelos 4 passos completos: o
    # IS tem so' 2-4 trades em qualquer parametro (amostra pequena demais
    # pra diferenciar nada ali). O dono adotou 0,21%/10x (par da PCAR3) ao
    # ver 27 trades no OOS contra so' 1 do herdado (0,42%/10x) e capital
    # final maior (R$28.238,79 vs R$27.369,35) -- decisao explicita a
    # partir do OOS, sem confirmacao IS previa (o inverso do protocolo
    # normal). Decisao do dono, registrada como tal.
    "CLSC4": _SymbolCalibrationTick(profit_pct=0.0021, stop_multiplier=10.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/10x bateu o par herdado do M1
    # (0,21%/5x) no IS (R$3.098,47 vs R$1.825,77) E no OOS (+8,9%).
    "KLBN3": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=10.0),
    # Par percentual FALLBACK, so' usado se `_VOLATILITY_OVERRIDE_BY_SYMBOL_
    # TICK` nao tiver dado (primeiro pregao do historico, ou feed falhou) --
    # o par CONFIRMADO de verdade da GRND3 e' o de volatilidade, abaixo.
    "GRND3": _SymbolCalibrationTick(profit_pct=0.0021, stop_multiplier=5.0),
    # CONFIRMADO em tick 2026-08-23 -- candidato de volatilidade (k=0,05/
    # s=30) venceu no IS mas PIOROU no OOS (-0,4%); o par herdado do M1
    # (0,42%/20x) e' quem fica, agora com medicao propria em vez de so'
    # herdado.
    "LPSB3": _SymbolCalibrationTick(profit_pct=0.0042, stop_multiplier=20.0),
    # CONFIRMADO em tick 2026-08-23 -- % 0,15/10x bateu o par herdado do M1
    # (0,21%/20x) no IS (R$2.075,40 vs R$1.352,59) E no OOS (+0,4%).
    "BMGB4": _SymbolCalibrationTick(profit_pct=0.0015, stop_multiplier=10.0),
}

#: Mesmo mecanismo/motivo de `gremah._VOLATILITY_OVERRIDE_BY_SYMBOL` (mesma
#: classe): simbolo aqui liga `alvo_por_volatilidade` AUTOMATICAMENTE em
#: `GremahTick.__init__`, so' se o chamador nao decidiu nada por conta
#: propria. `_CALIBRATION_BY_SYMBOL_TICK` acima vira FALLBACK pra estes.
#:
#: GRND3 (2026-08-23) -- unico da tabela ate' agora: B k=0,05/s=8 bateu o
#: percentual herdado do M1 (0,21%/5x) no IS (R$2.623,63 vs R$1.437,30) E
#: no OOS (R$1.198,59 vs R$915,94, +30,9%, MaxDD tambem menor: -0,8% vs
#: -2,0%) -- quase o MESMO par (k=0,05/s=10) que a `Gremah` M1 ja usa pra
#: este simbolo (`gremah._VOLATILITY_OVERRIDE_BY_SYMBOL["GRND3"]`), boa
#: confirmacao cruzada entre os dois motores.
_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK: dict[str, tuple[float, float]] = {
    "GRND3": (0.05, 8.0),
}

#: Dos 10 acima, quais passaram pelos 4 passos EM TICK (regime de preco ->
#: varredura fina IS -> confirmacao OOS). A tabela inteira continua servindo
#: de PONTO DE PARTIDA para varrer um simbolo novo (`scripts/daytrade/
#: sweep_gremah_tick.py` precisa instanciar o robo para medi-lo); esta tupla
#: e' o que o PAINEL oferece para operar. A distincao e' o ponto todo:
#: herdar um numero medido em M1 e liga-lo em dinheiro real e' o erro que
#: `gremah.py` documenta ter cometido e corrigido antes.
#:
#: CLSC4 e' um caso a parte -- confirmada em OOS mas NAO pelos 4 passos
#: completos, ja' que o IS nao teve amostra suficiente pra diferenciar
#: nenhum parametro (ver o paragrafo dela no topo do modulo). Incluida
#: aqui por decisao explicita do dono (2026-08-23), nao por medicao igual
#: aos outros 9.
TICK_CONFIRMED_SYMBOLS: tuple[str, ...] = (
    "PMAM3", "BMGB4", "KLBN3", "LPSB3", "DASA3", "KLBN4", "PCAR3", "CSAN3",
    "GRND3", "CLSC4",
)


@dataclass(frozen=True)
class SymbolSetup:
    """Um ativo calibrado EM TICK, como a ficha do robo o mostra. Espelha
    `gremah.SymbolSetup` (mesma forma, lida pelo mesmo `dashboard/
    robot_view.py`) -- separado porque os numeros sao de outra medicao.

    `alvo_por_volatilidade`/`alvo_vol_mult`/`stop_vol_mult` (2026-08-23):
    mesmo motivo de `gremah.SymbolSetup` -- quando ligado (GRND3, ver
    `_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`), `profit_pct`/`stop_multiplier`
    acima viram FALLBACK, nao o que decide o alvo no dia a dia."""

    symbol: str
    profit_pct: float
    stop_multiplier: float
    alvo_por_volatilidade: bool = False
    alvo_vol_mult: float | None = None
    stop_vol_mult: float | None = None


def calibrated_setups() -> tuple[SymbolSetup, ...]:
    """Os ativos que este robo pode OPERAR hoje -- so' os confirmados em tick.

    Hoje bate com `_CALIBRATION_BY_SYMBOL_TICK` (os 10 simbolos estao em
    `TICK_CONFIRMED_SYMBOLS`), mas a distincao continua existindo por
    desenho: um simbolo novo, sem medicao propria em tick, NAO deveria
    aparecer aqui -- ver o aviso no topo do modulo sobre herdar numero de
    outra granularidade sem medir de novo. Quem le esta funcao e' o
    painel (`strategy.daytrade.registry.symbols_for_robot` -> formulario
    de robo novo).

    Constroi uma instancia REAL de `GremahTick` por simbolo e le os
    atributos JA' RESOLVIDOS dela -- mesmo motivo de `gremah.
    calibrated_setups()`: ler `_CALIBRATION_BY_SYMBOL_TICK` direto mostraria
    o percentual da GRND3 como se ainda fosse ele quem decide, quando quem
    decide e' `_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`.
    """
    setups = []
    for symbol in TICK_CONFIRMED_SYMBOLS:
        robo = GremahTick(symbol=symbol)
        setups.append(SymbolSetup(
            symbol=symbol, profit_pct=robo.profit_pct, stop_multiplier=robo.stop_multiplier,
            alvo_por_volatilidade=robo.alvo_por_volatilidade,
            alvo_vol_mult=robo.alvo_vol_mult, stop_vol_mult=robo.stop_vol_mult,
        ))
    return tuple(setups)


@dataclass
class _SessionState:
    open_price: float | None = None
    session_halted: bool = False
    pending_side: str | None = None
    pending_mode: str | None = None  # "fixed" ou "rolling"
    pending_since_ts: pd.Timestamp | None = None
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None
    spacing_ticks_today: int = 1
    profit_ticks_today: int = 1
    stop_ticks_today: int | None = None
    session_stop_armed: bool = False
    session_stop_brl_hoje: float = 0.0
    session_start_ts: pd.Timestamp | None = None


class GremahTick(IntradayStrategy):
    """Porte tick a tick da `Gremah` -- ver docstring do modulo para o que
    mudou (2 parametros recontados em tempo de parede) e o que ficou
    identico (formula de niveis, teto de perda, dimensionamento por caixa)."""

    name = "gremah_tick"
    version = "0.1"
    target_fills_as_maker = True
    #: Negocio a negocio, nunca M1 -- e' a granularidade em que ele foi medido
    #: e a unica em que os dois parametros de TEMPO dele fazem sentido. Quem
    #: monta o feed ao vivo le isto (`live/intraday_feed.py::feed_for`).
    feed_kind = "tick"

    # FICHA TECNICA -- documentacao, nunca decisao (mesma convencao da
    # `gremah`, ver o bloco equivalente la). Escrita conferindo cada numero
    # contra a INSTANCIA default, nao contra a docstring.
    tagline = (
        "A mesma Grid REload MAker Hybrid da gremah, mas enxergando negocio a "
        "negocio em vez de resumo de minuto. O desenho nao mudou; o que mudou e' "
        "que ela ve cada preco que de fato aconteceu, na ordem em que aconteceu — "
        "e por isso o stop dela sai no negocio, nao no fim do minuto."
    )
    plain_summary = (
        "Ela faz exatamente o que a gremah faz: deixa uma ordem de compra parada um "
        "pouco abaixo do preco, e quando o mercado desce ate' la, compra e ja' pendura "
        "a venda um pouco acima. O lucro de cada ida e volta e' de centavos, e o ganho "
        "vem da repeticao.",
        "A diferenca e' o que ela recebe do mercado. A gremah ve um resumo por minuto: "
        "abriu tanto, maximo tanto, minimo tanto, fechou tanto. Esta ve cada negocio "
        "fechado, um por um, com o preco e o horario de cada um.",
        "Isso resolve uma ambiguidade que o resumo de minuto tem por construcao: se "
        "dentro do mesmo minuto o preco encostou no stop E no alvo, o resumo nao diz "
        "qual veio primeiro, e o backtest tem de chutar (ele chuta o pior caso). "
        "Negocio a negocio nao ha o que chutar — cada negocio tem um preco so'.",
        "Ao vivo isso vale um minuto de reacao. A gremah so' pode conferir stop e alvo "
        "quando o minuto acaba; esta confere a cada negocio que chega.",
        "O preco disso e' quanto ela foi medida. So' a PMAM3 passou pela medicao "
        "completa em negocio a negocio; os outros nove ativos da gremah continuam "
        "medidos so' em minuto, e por isso nao aparecem na lista dela. Pedir um ativo "
        "fora da lista faz o robo se recusar a ligar.",
    )
    plain_example = (
        "PMAM3 abre a R$ 0,14. O alvo de 0,32% do preco nao chega a um centavo, entao "
        "vira o minimo negociavel: 1 centavo. Ate' aqui, identico a' gremah.",
        "Ela deixa a compra parada a R$ 0,13. Enquanto ninguem negociar nesse preco, "
        "nada acontece.",
        "A diferenca aparece agora: a ordem so' e' considerada tocada quando um negocio "
        "de verdade sai a R$ 0,13. No resumo de minuto bastaria a MINIMA do minuto ter "
        "encostado ali — o que pode ter sido um unico negocio de outra pessoa, na "
        "frente da fila.",
        "Comprada, ela pendura a venda a R$ 0,14 e o stop mais abaixo. Se o preco cair "
        "ate' o stop, a saida e' decidida no negocio que furou o nivel, nao no "
        "fechamento do minuto em que ele furou.",
        "Uma ordem parada que espera 30 minutos sem ser tocada e' cancelada e refeita "
        "no preco do momento — na gremah essa espera e' contada em 30 barras, aqui em "
        "30 minutos de relogio, porque negocio nao chega em cadencia fixa.",
    )
    watched_signals = (
        "O preco de cada negocio fechado no ativo, na ordem em que sai.",
        "O preco de abertura do dia, que ancora os niveis das primeiras horas.",
        "O relogio do pregao — e' ele que decide se a ancora e' a abertura ou o preco "
        "do momento.",
        "O tempo de relogio desde que a ordem parada foi armada (30 minutos), e nao "
        "quantos negocios passaram desde entao.",
        "O volume do ultimo minuto FECHADO, somado negocio a negocio, para o teto de "
        "tamanho da PROXIMA entrada.",
        "O resultado acumulado do dia contra o limite de prejuizo do ativo (20% do "
        "caixa minimo dele).",
    )
    entry_rules = (
        "Uma ordem parada por vez, um pouco abaixo do preco de referencia para comprar "
        "(ou acima, para vender a descoberto) — nunca persegue o preco.",
        "So' conta como tocada quando um negocio SAI naquele preco. E' a regra mais "
        "estrita que a de minuto, onde bastava a faixa do minuto conter o nivel.",
        "Entrada, alvo e stop saem de um percentual do preco de referencia arredondado "
        "para centavos inteiros. Em acao de centavos esse arredondamento manda: varios "
        "percentuais diferentes viram o mesmo 1 centavo.",
        "Ate' as 11h de Brasilia a referencia e' a abertura do dia; depois, o preco do "
        "momento. Mesmo corte da gremah, e pelo mesmo motivo — nao foi reotimizado.",
        "Alterna os lados: depois de fechar uma compra, tenta uma venda, e so' insiste "
        "no mesmo lado quando o outro bateu o teto de 15 operacoes.",
        "Ordem parada ha' 30 minutos sem ser tocada e' cancelada e refeita no preco "
        "atual. Tempo de relogio, nao contagem de negocios: num papel iliquido podem "
        "passar horas sem negocio nenhum, e contar eventos deixaria a ordem velha "
        "parada indefinidamente.",
    )
    exit_rules = (
        "Vende com ordem parada no alvo, tambem sem perseguir o preco.",
        "Se o preco vai contra, o stop fecha a posicao — avaliado a cada negocio, nao "
        "no fim do minuto.",
        "Se o prejuizo acumulado do dia chega a 20% do caixa minimo do ativo, fecha o "
        "que estiver aberto e nao opera mais ate' o proximo pregao.",
        "Nunca carrega posicao para o dia seguinte. O corte segue o calendario real da "
        "B3, que anda 1h com o horario de verao americano.",
    )
    sizing_rules = (
        "Sempre em lotes inteiros de 100 acoes — nunca fracionario, onde cada ordem "
        "custaria R$ 1,90 fixos de corretagem num robo de giro alto.",
        "A cada 4x o custo de 1 lote que o caixa acumulado tiver, a proxima entrada "
        "usa mais um lote — e encolhe de volta se o caixa cair.",
        "O teto e' 10% do volume do ULTIMO minuto FECHADO, reavaliado a cada entrada "
        "nova -- nao mais um numero congelado no primeiro minuto do dia. Na abertura, "
        "quando ainda nao ha 1 minuto do proprio pregao, completa com o final do "
        "pregao anterior.",
        "O caixa minimo para operar o ativo e' o dobro do custo de um lote de 100 "
        "acoes, no preco de hoje.",
        "Esse minimo nao fica congelado no valor do primeiro dia: se o ativo sobe "
        "de preco depois que o robo ja esta' rodando, o minimo sobe junto, e se o "
        "caixa acumulado nao tiver alcancado o novo valor, o robo PULA o pregao "
        "inteiro ate' o lucro guardado cobrir o minimo atual — mesma regra da "
        "gremah, medida na DASA3 (48 pregoes fora quando o preco subiu de R$ 2,60 "
        "para R$ 4,19).",
    )
    param_pct = ("profit_pct", "session_stop_pct_capital",
                 "realocacao_teto_pct_volume_minuto")
    # Mesmo motivo da `gremah`: alvo e stop sao POR ATIVO, e a tabela plana
    # mostra so' a instancia default. Quem carrega todos e' a tabela de ativos.
    param_hidden = ("symbol", "profit_pct", "stop_multiplier")
    param_utc_time = ("fixed_anchor_until",)
    param_docs = {
        "symbol": "Ativo que ele negocia.",
        "tick_size": "Variacao minima de preco do ativo.",
        "profit_pct": "Alvo de lucro por trade, em % do preco da ancora. Vazio = lookup por "
                      "simbolo em `_CALIBRATION_BY_SYMBOL_TICK`.",
        "spacing_multiplier": "Distancia da entrada, em multiplos do alvo.",
        "stop_multiplier": "Distancia do stop, em multiplos do alvo. Vazio = mesmo lookup de "
                           "`profit_pct`.",
        "max_trades_per_side": "Teto de preenchimentos por lado, por sessao.",
        "session_stop_pct_capital": "Percentual do caixa minimo do dia que define a "
                                    "perda-limite diaria.",
        "fixed_anchor_until": "Hora em que a ancora fixa vira rolante.",
        "rolling_reanchor_after_seconds": "Segundos que uma ordem rolante espera antes de "
                                          "rearmar. Na gremah isto e' contado em barras; aqui "
                                          "e' relogio, porque negocio nao chega em cadencia fixa.",
        "realocacao_limiar_caixa": "Quantas vezes o custo de 1 lote o caixa acumulado precisa "
                                   "ter para a proxima entrada usar mais um lote.",
        "realocacao_teto_pct_volume_minuto": "Teto de posicao: % da media de volume por minuto "
                                             "na janela rolante (`realocacao_janela_minutos`).",
        "realocacao_janela_minutos": "Tamanho da janela (minutos) da media movel de volume que "
                                     "alimenta o teto acima. Reavaliada a cada entrada nova; na "
                                     "abertura, completa com a cauda do pregao anterior.",
        "dividir_entrada": "Divide ENTRADA (em pedacos do tamanho do negocio tipico recente) E "
                          "SAIDA (em fatias de 1 lote, `LOTE_PADRAO_B3`) em vez de exigir tudo "
                          "de uma vez. So' tem efeito com o motor rodando "
                          "`limit_fill_capped_by_volume=True` (padrao desde 2026-08-23). Padrao "
                          "`True` desde 2026-08-23 -- medido IS/OOS antes (inverte de sinal), "
                          "ligado mesmo assim por decisao do dono.",
        "dividir_max_pecas": "Teto de pedacos que `dividir_entrada` cria para uma entrada.",
        "exit_ttl_bars": "Barras (negocios reais, aqui, nao minutos) que uma fatia de saida "
                         "espera antes de virar ordem a mercado pelo restante. Padrao 8 desde "
                         "2026-08-23 (varredura 1..10 em PMAM3, IS+OOS). Vazio = execucao real "
                         "recusa operar com `dividir_entrada` ligado; backtest/sombra esperam "
                         "sem prazo.",
        "alvo_por_volatilidade": "Alvo/espacamento/stop por fracao da volatilidade medida "
                                 "(mediana do range diario) em vez de percentual do preco. "
                                 "Desligado por padrao -- opt-in, pendente de medicao/decisao.",
        "alvo_vol_mult": "O 'k' da regra alvo = k x range diario mediano. So' usado com "
                        "`alvo_por_volatilidade` ligado -- sem default.",
        "vol_janela_dias": "Sessoes anteriores usadas para medir a mediana do range diario.",
        "stop_vol_mult": "Multiplicador GLOBAL do stop sobre o alvo por volatilidade. Vazio = "
                         "usa o `stop_multiplier` do simbolo.",
        "stop_frac_range": "Fracao do range diario mediano que substitui o stop, mantendo "
                           "alvo/espacamento no caminho de sempre. Independente de "
                           "`alvo_por_volatilidade`. Vazio = stop pelo `stop_multiplier`.",
    }

    @staticmethod
    def calibrated_setups() -> tuple[SymbolSetup, ...]:
        """Os ativos calibrados EM TICK, alcancaveis a partir da CLASSE —
        espelho fino do `calibrated_setups()` do modulo, pelo mesmo motivo do
        espelho equivalente na `gremah`: quem monta a ficha recebe a classe e
        procura este nome com `getattr`."""
        return calibrated_setups()

    def __init__(
        self,
        symbol: str = "PMAM3",
        tick_size: float = 0.01,
        profit_pct: float | None = None,
        spacing_multiplier: float = 2.0,
        stop_multiplier: float | None = None,
        max_trades_per_side: int = 15,
        session_stop_pct_capital: float = SESSION_STOP_FRACAO_PADRAO,
        fixed_anchor_until: time = time(14, 0),
        rolling_reanchor_after_seconds: float = ROLLING_REANCHOR_SEGUNDOS_PADRAO,
        realocacao_limiar_caixa: float = REALOCACAO_LIMIAR_CAIXA_PADRAO,
        realocacao_teto_pct_volume_minuto: float = REALOCACAO_TETO_PCT_VOLUME_MINUTO_PADRAO,
        realocacao_janela_minutos: float = REALOCACAO_JANELA_MINUTOS_PADRAO,
        dividir_entrada: bool = True,
        dividir_max_pecas: int = DIVIDIR_MAX_PECAS_PADRAO,
        exit_ttl_bars: int | None = EXIT_TTL_BARS_PADRAO,
        alvo_por_volatilidade: bool = False,
        alvo_vol_mult: float | None = None,
        vol_janela_dias: int = VOL_JANELA_DIAS_PADRAO,
        stop_vol_mult: float | None = None,
        stop_frac_range: float | None = None,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        if profit_pct is None or stop_multiplier is None:
            calib = _CALIBRATION_BY_SYMBOL_TICK.get(symbol)
            if calib is None:
                raise ValueError(
                    f"gremah_tick: sem calibracao para o simbolo {symbol!r} em "
                    "_CALIBRATION_BY_SYMBOL_TICK (strategy/daytrade/lab/gremah_tick.py). "
                    "Passe profit_pct= e stop_multiplier= explicitamente, ou meca "
                    "este simbolo em tick (IS + OOS, mesmos 4 passos de gremah.py) "
                    "e adicione-o a tabela antes de usar o default."
                )
            if profit_pct is None:
                profit_pct = calib.profit_pct
            if stop_multiplier is None:
                stop_multiplier = calib.stop_multiplier
        self.profit_pct = profit_pct
        self.spacing_multiplier = spacing_multiplier
        self.stop_multiplier = stop_multiplier
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_pct_capital = abs(session_stop_pct_capital)
        self.fixed_anchor_until = fixed_anchor_until
        self.rolling_reanchor_after_seconds = abs(rolling_reanchor_after_seconds)
        self.realocacao_limiar_caixa = abs(realocacao_limiar_caixa)
        self.realocacao_teto_pct_volume_minuto = abs(realocacao_teto_pct_volume_minuto)
        self.realocacao_janela_minutos = abs(realocacao_janela_minutos)
        self.dividir_entrada = dividir_entrada
        self.dividir_max_pecas = max(1, int(dividir_max_pecas))
        self.exit_ttl_bars = exit_ttl_bars
        # Mesmo mecanismo/motivo de `Gremah.__init__` (mesma classe) -- ver
        # a docstring la para a justificativa completa: simbolo com par
        # (k,s) CONFIRMADO no OOS (`_VOLATILITY_OVERRIDE_BY_SYMBOL_TICK`)
        # liga isto AUTOMATICAMENTE, so' se o chamador nao decidiu nada por
        # conta propria.
        if not alvo_por_volatilidade and alvo_vol_mult is None:
            override = _VOLATILITY_OVERRIDE_BY_SYMBOL_TICK.get(symbol)
            if override is not None:
                alvo_por_volatilidade = True
                alvo_vol_mult, override_stop_vol_mult = override
                if stop_vol_mult is None:
                    stop_vol_mult = override_stop_vol_mult
        if alvo_por_volatilidade and alvo_vol_mult is None:
            raise ValueError(
                "gremah_tick: alvo_por_volatilidade=True exige alvo_vol_mult "
                "explicito (o 'k' da regra alvo = k x range_mediano) -- sem "
                "default, precisa ser medido (ver scripts/daytrade/"
                "sweep_gremah_vol.py)."
            )
        self.alvo_por_volatilidade = alvo_por_volatilidade
        self.alvo_vol_mult = alvo_vol_mult
        self.vol_janela_dias = max(1, int(vol_janela_dias))
        self.stop_vol_mult = stop_vol_mult
        # Mesmo mecanismo/motivo de `Gremah.__init__` (mesma classe) -- ver
        # a docstring la para a justificativa completa.
        self.stop_frac_range = stop_frac_range

        self.quantity: int | None = None
        self._state = _SessionState()
        self._cash_atual_brl = 0.0
        # Sobrevive a `on_session_start` de proposito -- ver o comentario
        # equivalente em `Gremah.__init__` (mesma classe, mesmo motivo).
        self._janela_volume = RollingVolumeWindow(self.realocacao_janela_minutos)
        self._janela_vol = JanelaVolatilidadeDiaria(self.vol_janela_dias)

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()
        self._janela_volume.iniciar_sessao()

    def on_capital_update(self, cash_brl: float) -> None:
        self._cash_atual_brl = cash_brl

    def seed_volume_window(self, previous_session_tail: list[Bar]) -> None:
        self._janela_volume.definir_cauda_anterior(previous_session_tail)

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        # Mesmo padrao de `Gremah.seed_daily_volatility` -- SUBSTITUI, nunca
        # acumula (ver a docstring la).
        self._janela_vol = JanelaVolatilidadeDiaria(self.vol_janela_dias)
        for dia in previous_daily_bars[-self.vol_janela_dias:]:
            self._janela_vol.registrar_dia(dia)

    def _ticks_from_pct(self, price: float, pct: float) -> int:
        return max(1, round(price * pct / self.tick_size))

    def _ticks_from_vol(self, mult: float) -> int | None:
        range_mediano = self._janela_vol.range_mediano()
        if range_mediano is None:
            return None
        return max(1, round(range_mediano * mult / self.tick_size))

    def _session_ticks(self, price_ref: float) -> tuple[int, int, int]:
        """Mesmo mecanismo de `Gremah._session_ticks` (mesma classe) -- ver
        a docstring la para a justificativa completa, inclusive
        `stop_frac_range` (aplicado por ultimo, independente do resto)."""
        profit_ticks = spacing_ticks = stop_ticks = None
        if self.alvo_por_volatilidade:
            profit_ticks = self._ticks_from_vol(self.alvo_vol_mult)
            if profit_ticks is not None:
                stop_mult = self.stop_vol_mult if self.stop_vol_mult is not None else self.stop_multiplier
                spacing_ticks = self._ticks_from_vol(self.alvo_vol_mult * self.spacing_multiplier)
                stop_ticks = self._ticks_from_vol(self.alvo_vol_mult * stop_mult)
        if profit_ticks is None:
            profit_ticks = self._ticks_from_pct(price_ref, self.profit_pct)
            spacing_ticks = self._ticks_from_pct(price_ref, self.profit_pct * self.spacing_multiplier)
            stop_ticks = self._ticks_from_pct(price_ref, self.profit_pct * self.stop_multiplier)
        if self.stop_frac_range is not None:
            stop_vol = self._ticks_from_vol(self.stop_frac_range)
            if stop_vol is not None:
                stop_ticks = stop_vol
        return profit_ticks, spacing_ticks, stop_ticks

    def _arm_fixed_session_params(self) -> None:
        price = self._state.open_price
        profit_ticks, spacing_ticks, stop_ticks = self._session_ticks(price)
        self._state.profit_ticks_today = profit_ticks
        self._state.spacing_ticks_today = spacing_ticks
        self._state.stop_ticks_today = stop_ticks

    def _fills_of(self, side: str) -> int:
        return self._state.long_fills if side == "long" else self._state.short_fills

    def _next_side_to_arm(self) -> str | None:
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def _lotes_por_realocacao(self, anchor: float, ts: pd.Timestamp) -> int:
        """Mesmo mecanismo de `Gremah._lotes_por_realocacao` (mesma classe)
        -- ver a docstring la, inclusive o motivo de SEMPRE haver ao menos
        1 lote (quem barra caixa genuinamente insuficiente e' o freio em
        `backtest.intraday.engine.run_intraday_backtest`, nao aqui)."""
        custo_do_lote = anchor * LOTE_PADRAO_B3
        lotes = 1 + math.floor(self._cash_atual_brl / (self.realocacao_limiar_caixa * custo_do_lote))
        media_volume_min = self._janela_volume.media_por_minuto(ts)
        teto_acoes = media_volume_min * self.realocacao_teto_pct_volume_minuto
        max_lotes_dia = max(1, int(teto_acoes) // LOTE_PADRAO_B3)
        return min(max_lotes_dia, max(1, lotes))

    def _dividir_pecas(self, quantidade_total: int, ts: pd.Timestamp) -> tuple[int, ...] | None:
        """Fatia `quantidade_total` (acoes, multiplo de `LOTE_PADRAO_B3`) em
        pedacos do tamanho do NEGOCIO TIPICO observado na janela rolante
        (mediana de `RollingVolumeWindow.volumes_por_evento`) -- um pedaco
        do tamanho de um negocio REAL tem mais chance de casar sozinho
        (FOK, ver `IntradayBacktestConfig.limit_fill_capped_by_volume`) do
        que a ordem inteira de uma vez. `None` = nao divide (janela sem
        evento ainda, ou o negocio tipico ja cobre o total sozinho -- nao
        ha' o que ganhar fatiando)."""
        eventos = self._janela_volume.volumes_por_evento(ts)
        if not eventos:
            return None
        tipico_lotes = max(1, int(median(eventos)) // LOTE_PADRAO_B3)
        total_lotes = quantidade_total // LOTE_PADRAO_B3
        if tipico_lotes >= total_lotes:
            return None
        n_pecas = min(self.dividir_max_pecas, math.ceil(total_lotes / tipico_lotes))
        base, resto = divmod(total_lotes, n_pecas)
        # distribui o resto (em LOTES) pelas primeiras pecas, 1 lote a mais
        # cada, em vez de empilhar tudo na ultima -- pecas parecidas entre
        # si, nenhuma desproporcionalmente maior que o negocio tipico.
        lotes_por_peca = [base + (1 if i < resto else 0) for i in range(n_pecas)]
        return tuple(l * LOTE_PADRAO_B3 for l in lotes_por_peca if l > 0)

    def _build_entry(self, side: str, anchor: float, spacing_ticks: int, profit_ticks: int, stop_ticks: int | None, ts: pd.Timestamp) -> EnterLimit:
        self.quantity = self._lotes_por_realocacao(anchor, ts) * LOTE_PADRAO_B3
        split = self._dividir_pecas(self.quantity, ts) if self.dividir_entrada else None
        spacing_off = spacing_ticks * self.tick_size
        level_price = round(anchor - spacing_off, 2) if side == "long" else round(anchor + spacing_off, 2)
        profit_off = profit_ticks * self.tick_size
        target_price = level_price + profit_off if side == "long" else level_price - profit_off
        stop_price = None
        if stop_ticks is not None:
            stop_off = stop_ticks * self.tick_size
            stop_price = level_price - stop_off if side == "long" else level_price + stop_off
        return EnterLimit(
            side=side,
            limit_price=level_price,
            initial_target=target_price,
            initial_stop=stop_price,
            quantity=self.quantity,
            reason="gremah_tick_" + side,
            split_quantities=split,
            # Mesmo `dividir_entrada` tambem fatia a SAIDA (2026-08-22,
            # pedido do dono): o alvo tinha o MESMO problema tudo-ou-nada
            # que a entrada -- ver `EnterLimit.exit_split_unit`.
            exit_split_unit=LOTE_PADRAO_B3 if self.dividir_entrada else None,
            exit_ttl_bars=self.exit_ttl_bars if self.dividir_entrada else None,
        )

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        position: IntradayOpenPosition | None,
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []
        is_fixed_phase = ts.time() < self.fixed_anchor_until

        # Armado no PRIMEIRO tick da sessao -- equivalente ao bloco
        # `session_stop_armed` da `Gremah` M1, so' que a perda-limite usa o
        # preco desse primeiro tick (aproximadamente a abertura).
        if state.session_start_ts is None:
            state.session_start_ts = ts
            state.session_stop_armed = True
            state.session_stop_brl_hoje = capital_minimo_brl(bar.open) * self.session_stop_pct_capital

        # Alimenta a janela de volume rolante com TODO tick visto, mesmo
        # fora de sinal de entrada -- ver o comentario equivalente em
        # `Gremah.on_bar` (mesma classe `RollingVolumeWindow`).
        self._janela_volume.registrar(ts, bar.volume)

        if is_fixed_phase and state.open_price is None:
            state.open_price = bar.open
            self._arm_fixed_session_params()

        if not state.session_halted and session_pnl_brl <= -state.session_stop_brl_hoje:
            state.session_halted = True
            if position is not None:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if position is not None:
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
                state.pending_since_ts = None
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        stale_fixed_order = state.pending_side is not None and state.pending_mode == "fixed" and not is_fixed_phase
        stale_rolling_order = (
            state.pending_side is not None and state.pending_mode == "rolling"
            and state.pending_since_ts is not None
            and (ts - state.pending_since_ts).total_seconds() >= self.rolling_reanchor_after_seconds
        )
        stale_order = stale_fixed_order or stale_rolling_order
        if state.pending_side is not None and not stale_order:
            return actions

        next_side = state.pending_side if stale_order else self._next_side_to_arm()
        if next_side is None:
            return actions

        state.pending_side = next_side
        state.pending_since_ts = ts
        state.pending_mode = "fixed" if is_fixed_phase else "rolling"
        if is_fixed_phase:
            entry = self._build_entry(
                next_side, state.open_price,
                state.spacing_ticks_today, state.profit_ticks_today, state.stop_ticks_today,
                ts,
            )
        else:
            anchor = bar.close
            profit_ticks, spacing_ticks, stop_ticks = self._session_ticks(anchor)
            entry = self._build_entry(next_side, anchor, spacing_ticks, profit_ticks, stop_ticks, ts)
        return [entry]
