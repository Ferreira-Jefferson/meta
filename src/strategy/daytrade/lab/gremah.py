"""GREMAH = abreviacao de "Grid REload MAker Hybrid" (2026-08-21).

Combina os dois desenhos anteriores num robo so'. Ancora FIXA na abertura
(como a geracao anterior, ticks%) enquanto o pregao ainda esta "fresco"
(antes de `fixed_anchor_until`, por padrao 14:00 UTC / ~11h Brasilia); a
partir dai, muda para ancora ROLANTE (recalculada a cada recarga a partir
do preco ATUAL) para o resto da sessao -- nao precisa mais saber onde foi
a abertura a partir desse ponto.

Motivado por um achado empirico direto (2026-08-21, in-sample real,
PMAM3): mesmo com a abertura corretamente calibrada
(`warm_start_calibration`), o grid ancorado na abertura degrada de
+R$747,10 (comecando as 13:00 UTC, a abertura real) para -R$1.000,50
(comecando as 18:00 UTC) no MESMO periodo de dados -- o preco deriva da
abertura conforme o dia avanca e os niveis fixos ficam cada vez mais
"fora do dinheiro" (raramente tocados, e quando tocados o contexto de
preco ja' e' outro). Um grid de ancora rolante pura NAO degrada dessa
forma (fica estavel entre R$305 e R$615 em qualquer horario testado), mas
comecando EXATAMENTE na abertura perde para o fixo (R$514 vs R$747) --
abre mao do edge especifico de reversao-ao-redor-da-abertura que parece
so' existir nas primeiras horas do pregao.

Este hibrido tenta capturar os dois: o edge forte e especifico do inicio
do pregao (fixo) sem herdar a degradacao do fim do pregao (rolante).
`fixed_anchor_until` (14:00 UTC por padrao) NAO foi re-otimizado -- e' so'
o ponto medio observavel entre "13:00 ainda positivo" e "15:00 ja'
negativo" na tabela que motivou este desenho; validar/varrer esse corte e'
trabalho futuro, nao presumir que 14:00 e' o otimo.

Uso correto (decidido pelo CALLER, nao pela classe): so' fazer
`warm_start_calibration` (buscar a abertura real via historico) se a hora
de inicio for ANTES de `fixed_anchor_until` -- se nao sobra janela fixa
real, pular o warm-start e deixar o robo rodar cru desde agora (ele ja se
comporta como puro modo rolante nesse caso). Ver
`strategy/daytrade/base.py::warm_start_calibration` e a memoria do
campeao de day trade PMAM3 para o historico completo da investigacao."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

import math

from strategy.daytrade.base import (
    LOTE_PADRAO_B3,
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    RollingVolumeWindow,
    capital_minimo_brl,
)

#: Perda-limite diaria padrao, como fracao do caixa minimo do dia
#: (`capital_minimo_brl`). Substituiu o R$30 fixo em 2026-08-22: medido nos
#: 10 ativos calibrados, 20% reproduz o MESMO resultado (IS e OOS) do R$30
#: antigo, mas escala com o preco de cada ativo em vez de travar num numero
#: so'.
SESSION_STOP_FRACAO_PADRAO = 0.20

#: Quantas vezes o custo de 1 lote (no preco da ANCORA da entrada) o caixa
#: ACUMULADO (capital inicial + PnL realizado ate agora, ver
#: `IntradayStrategy.on_capital_update`) precisa ter para a proxima entrada
#: usar mais um lote. Formula: `lotes = 1 + floor(caixa / (limiar x custo_do_
#: lote))` -- cresce com o caixa, encolhe de volta se ele cair (perdas, ou o
#: preco subiu e o lote ficou mais caro). Medido 2026-08-22 em PMAM3 (R$50 ->
#: R$10.380,17 em ~11 meses, contra R$971,21 de 1 lote fixo sempre, MESMO
#: MaxDD) -- pedido do dono para virar comportamento padrao do robo, nao so'
#: experimento.
REALOCACAO_LIMIAR_CAIXA_PADRAO = 4.0

#: Teto de tamanho de posicao, como fracao do volume MEDIO por minuto na
#: janela rolante (`REALOCACAO_JANELA_MINUTOS_PADRAO`, ver
#: `strategy.daytrade.base.RollingVolumeWindow`). Pedido do dono 2026-08-22:
#: nunca pedir uma fatia do mercado maior que isto, porque o backtest simula
#: preenchimento instantaneo e o book real nao absorve uma ordem grande
#: demais frente ao proprio giro do momento.
#:
#: Ate 2026-08-22 isto usava so' o volume do PRIMEIRO minuto do pregao,
#: CONGELADO pelo resto do dia. Substituido no mesmo dia (pedido do dono) por
#: uma media MOVEL dos ultimos `REALOCACAO_JANELA_MINUTOS_PADRAO` minutos,
#: reavaliada a CADA sinal de entrada: um minuto so' e' amostra ruidosa
#: demais (um pico ou um vazio isolado travava o teto do DIA inteiro), e
#: congelar ignorava o giro real do resto da sessao.
REALOCACAO_TETO_PCT_VOLUME_MINUTO_PADRAO = 0.10

#: Janela (minutos) da media movel de volume que alimenta o teto acima. Na
#: ABERTURA, quando a sessao de hoje ainda nao acumulou a janela inteira
#: sozinha, `RollingVolumeWindow` completa o que falta com a CAUDA do
#: pregao ANTERIOR (mesmo pedido do dono) -- nunca assume volume zero nos
#: minutos que a sessao de hoje ainda nao viveu.
#:
#: Medido 2026-08-22 (PMAM3, IS 2023-2026 + OOS jun-ago/2026) contra 5min e
#: 30min: 30min tinha o menor MaxDD e o melhor Calmar das tres nas DUAS
#: janelas de teste (o unico que nao inverteu de sinal entre IS e OOS), mas
#: o dono decidiu manter 1min por ora ("por hora" -- decisao PROVISORIA,
#: revisitar). 1min = "o volume do ultimo minuto FECHADO", reavaliado a cada
#: entrada -- ja e' uma melhora sobre o desenho anterior (congelado no
#: PRIMEIRO minuto do dia), mesmo sem a suavizacao da media de 30min.
REALOCACAO_JANELA_MINUTOS_PADRAO = 1.0


@dataclass(frozen=True)
class _SymbolCalibration:
    profit_pct: float
    stop_multiplier: float


# Calibracao por SIMBOLO, medida 2026-08-21 (backtest M1, janela comum
# 2025-09-16..2026-06-13, capital dimensionado ao custo real de 1 lote
# padrao -- day trade nao usa fracionario porque cada ordem fracionaria
# custa R$1,90 fixos na corretora, proibitivo dado o giro alto da gremah).
#
# CONFIRMADO pelo dono do capital em 2026-08-22: "frac tem sim a taxa". O
# fracionario COBRA R$1,90 fixos por ordem. Houve uma contradicao no repo por
# um dia -- `backtest/intraday/profiles.py` afirmava que a Rico zerava tambem
# o fracionario e que o R$1,90 era "leitura superada"; essa frase estava
# ERRADA e foi corrigida na fonte. A justificativa acima (day trade em lote
# inteiro para nao pagar taxa fixa num robo de giro alto) segue VALIDA.
#
# Buraco que continua aberto, e este e' de MEDICAO, nao de leitura:
# `core/config.py::CostModel.fractional_fixed_fee` e' 0.0 no default, ou seja
# o ranking oficial de swing roda SEM cobrar a taxa que existe de verdade --
# nenhum robo do podio foi re-simulado com ela. Ver a memoria
# `rico_fractional_fee_2026_08_21`.
#
# ---------------------------------------------------------------------------
# A TABELA (10 simbolos, medidos 2026-08-21/22)
# ---------------------------------------------------------------------------
# Como cada linha foi obtida, sem excecao:
#   1. Varredura ampla do universo inteiro (140 papeis com M1 salvo) no default
#      global antigo (0,42%/20x), so' para achar candidatos.
#   2. REGIME DE PRECO: para cada candidato, a data mais antiga a partir da
#      qual o fechamento diario nunca mais saiu de [0,5x, 2x] do preco de hoje.
#      So' esse trecho conta. Sem isso a medicao mente: `profit_pct` vira TICKS
#      (`_ticks_from_pct`), entao o mesmo percentual e' outro alvo em outro
#      preco -- calibrar a CSAN3 com dado de quando ela valia R$7,62 produziria
#      o par certo para um papel que nao existe mais.
#   3. Varredura fina de alvo x stop DENTRO do regime, so' ate o corte
#      `backtest.intraday.profiles.OOS_CUTOFF` (2026-06-13).
#   4. UMA passada no trecho reservado, ja com o par escolhido. Positivo no IS
#      e negativo no OOS = descartado, sem segunda tentativa (foi o que
#      aconteceu com CMIN3, BBDC3, EQTL3 e EUCA4 -- os quatro tinham IS bom).
#
#   simbolo  alvo/stop     trades OOS  wr OOS     lucro OOS     pf OOS  MaxDD OOS
#   PMAM3    0,32% / 10x          319   83,1%      +R$177,79      2,75    -21,59%
#   KLBN4    0,21% /  5x          671   98,7%      +R$425,02     12,15     -0,81%
#   CSAN3    0,21% / 20x          627   98,2%      +R$347,48      4,22     -2,16%
#   DASA3    0,21% / 10x          857   93,5%      +R$278,94      1,77     -4,24%
#   PCAR3    0,21% / 10x          894   92,4%      +R$249,89      1,59     -4,55%
#   CLSC4    0,42% / 10x           14   64,3%      +R$215,21      1,56     -0,99%
#   KLBN3    0,21% /  5x          395   95,9%      +R$198,43      3,63     -1,48%
#   GRND3    0,21% /  5x          334   97,3%      +R$189,70      5,59     -1,54%
#   LPSB3    0,42% / 20x          171   94,2%      +R$139,51      4,83     -2,42%
#   BMGB4    0,21% / 20x          316   97,5%      +R$137,72      2,86     -2,11%
#
# O que NAO esta provado, e precisa ser dito junto com os numeros acima:
#   - CLSC4 tem 14 trades no OOS (131 no IS). Passou nos dois trechos, mas 14
#     trades nao demonstram edge -- e ela exige R$30.390 em caixa (lote de
#     R$15.195), fora da realidade do dono hoje.
#   - PMAM3 e' a unica cujo par foi escolhido com dado que o corte anterior
#     dela (2025-12-01) mantinha reservado -- ver `OOS_CUTOFF` em
#     `backtest/intraday/profiles.py` para o porque da troca e o custo dela.
#   - MaxDD aqui e' medido sobre `capital_minimo_brl` (o piso), o capital mais
#     agressivo possivel. Quem operar com folga maior ve MaxDD percentual menor.
#
# Um simbolo novo exige os MESMOS 4 passos antes de entrar aqui -- ver
# `Gremah.__init__`, que FALHA ALTO (`ValueError`) para qualquer simbolo
# ausente desta tabela em vez de herdar a calibracao de outro papel. Duas
# evidencias de que herdar seria errado: o par 0,21%/5x da KLBN4 rende
# +R$425 nela e o mesmo par foi REPROVADO na CMIN3; e nao ha um so par que
# apareca em todas as 10 linhas.
_CALIBRATION_BY_SYMBOL: dict[str, _SymbolCalibration] = {
    "PMAM3": _SymbolCalibration(profit_pct=0.0032, stop_multiplier=10.0),
    "KLBN4": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=5.0),
    "CSAN3": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=20.0),
    "DASA3": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=10.0),
    "PCAR3": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=10.0),
    "CLSC4": _SymbolCalibration(profit_pct=0.0042, stop_multiplier=10.0),
    "KLBN3": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=5.0),
    "GRND3": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=5.0),
    "LPSB3": _SymbolCalibration(profit_pct=0.0042, stop_multiplier=20.0),
    "BMGB4": _SymbolCalibration(profit_pct=0.0021, stop_multiplier=20.0),
}


@dataclass(frozen=True)
class SymbolSetup:
    """Um ativo calibrado, como a FICHA do robô o mostra.

    Existe porque `_CALIBRATION_BY_SYMBOL` é o encanamento (dict privado de
    `_SymbolCalibration`, lido pelo `__init__`) e a página do robô precisa dos
    MESMOS números numa forma estável de ler: uma instância de `Gremah` opera
    UM símbolo, então a tabela de parâmetros dela mostra o alvo/stop de um
    ativo só — e mostrar esse número solto anunciava "o robô usa 0,32%" quando
    0,32% é a calibração da PMAM3 e não vale para nenhum outro papel.

    O capital mínimo fica de fora de propósito: ele depende do preço de HOJE,
    e buscar preço não é assunto de `strategy/` (AGENTS.md #1) — quem exibe
    busca o preço e chama `strategy.daytrade.base.capital_minimo_brl`.
    """

    symbol: str
    profit_pct: float
    stop_multiplier: float


def calibrated_setups() -> tuple[SymbolSetup, ...]:
    """Os ativos que este robô pode operar hoje, na ordem em que foram medidos.

    Cada um com alvo e stop PRÓPRIOS: `profit_pct`/`stop_multiplier` não
    transferem entre símbolos (medido 2026-08-21, reconfirmado em 10 papéis
    2026-08-22), e é por isso que `Gremah.__init__` falha alto num símbolo
    ausente em vez de herdar a calibração de outro papel.
    """
    return tuple(
        SymbolSetup(symbol=s, profit_pct=c.profit_pct, stop_multiplier=c.stop_multiplier)
        for s, c in _CALIBRATION_BY_SYMBOL.items()
    )


@dataclass
class _SessionState:
    open_price: float | None = None
    session_halted: bool = False
    pending_side: str | None = None
    pending_mode: str | None = None  # "fixed" ou "rolling" -- modo em que a ordem pendente foi armada
    pending_bars_waited: int = 0
    open_side: str | None = None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None
    spacing_ticks_today: int = 1
    profit_ticks_today: int = 1
    stop_ticks_today: int | None = None
    session_stop_armed: bool = False
    session_stop_brl_hoje: float = 0.0


class Gremah(IntradayStrategy):
    """Ancora fixa na abertura ate' `fixed_anchor_until`; ancora rolante
    (preco atual, recalculada a cada recarga) depois disso.

    ESCOPO: acoes da B3 com calibracao PROPRIA medida, em qualquer faixa de
    preco. A lista vive em `_CALIBRATION_BY_SYMBOL` (acima, com a evidencia de
    cada linha); `Gremah.__init__` levanta `ValueError` para qualquer simbolo
    fora dela em vez de herdar a calibracao de outro papel.

    Ate 2026-08-21 esta docstring dizia "desenhada para operar acoes ABAIXO de
    R$4". Era uma conclusao APRESSADA e foi DERRUBADA em 2026-08-22 por
    medicao: varrendo os 140 papeis com dado M1 e calibrando cada candidato no
    seu proprio regime de preco, apareceram positivos confirmados em IS e OOS
    a R$5,08 (BMGB4) e a R$151,95 (CLSC4). O preco baixo nunca foi a causa --
    era coincidencia de que os tres primeiros papeis testados eram baratos.

    O que a medicao MOSTROU ser a causa real: `profit_pct` vira TICKS
    (`_ticks_from_pct`, com piso de 1 tick), entao o mesmo percentual e um
    alvo diferente em cada preco. O default global antigo (0,42%) calhava de
    saturar no piso de 1 tick em papel barato -- funcionava por acidente
    aritmetico, nao por desenho. Papel caro precisa de percentual proprio, e
    com ele funciona igual. Ou seja: a exigencia nunca foi "preco baixo", e
    sim "alvo calibrado para ESTE preco", que e' o que a tabela guarda.

    O que o preco alto realmente muda e' o CAPITAL, nao o edge: o lote de 100
    acoes custa 100x o preco, e o piso para operar e o dobro disso
    (`strategy.daytrade.base.capital_minimo_brl`). CLSC4 exige R$30.390 em
    caixa; PMAM3, R$28. Essa e a restricao que separa os papeis para o dono do
    capital hoje -- nao a mecanica do robo."""

    name = "gremah"
    version = "0.1"

    # FICHA TECNICA -- documentacao, nunca decisao: nada disto e' lido por
    # `on_bar`. Mesma convencao (e mesmos nomes de atributo) da familia de
    # swing, declarada em `strategy/base.py::Strategy` -- `IntradayStrategy`
    # nao herda de `Strategy` de proposito, entao os atributos moram aqui e
    # quem le (`dashboard/robot_view.py`) usa `getattr` com default vazio.
    # Existe para a pagina `/strategies/gremah` poder explicar o robo em prosa
    # em vez de mostrar so' a tabela de parametros.
    # A frase de abertura explica o NOME, porque o nome é a descrição do
    # desenho: cada uma das quatro partes de "Grid REload MAker Hybrid" é uma
    # decisão do robô, e explicar a sigla explica a estratégia de uma vez.
    tagline = (
        "Grid REload MAker Hybrid — o nome é o desenho: uma GRADE de "
        "níveis em volta do preço (Grid), que se RECARREGA a cada ida e volta "
        "(REload), com a ordem sempre PARADA esperando o mercado em vez de "
        "persegui-lo (MAker), e com duas âncoras no mesmo pregão — a abertura nas "
        "primeiras horas, o preço do momento depois (Hybrid). Dezenas de operações "
        "por dia, um ativo por conta, nunca dormindo com posição aberta."
    )
    plain_summary = (
        "Ele não tenta adivinhar se a ação vai subir ou cair. Deixa uma ordem de "
        "compra parada um pouco abaixo do preço do momento; se o mercado cair até "
        "ali, ele compra e imediatamente coloca a ordem de venda um pouco acima. O "
        "lucro de cada ida e volta é de centavos — o ganho vem da repetição, não do "
        "tamanho.",
        "O detalhe que sustenta o desenho: as duas ordens ficam PARADAS esperando o "
        "preço chegar, nunca perseguem o mercado. Quem espera recebe o spread em vez "
        "de pagá-lo, e é essa diferença que separa o robô de dar lucro ou prejuízo "
        "com o mesmo número de operações.",
        "Ele opera UM ativo por conta, escolhido entre os que já têm calibração "
        "medida — a tabela de ativos abaixo é a lista completa, e o número dela é o "
        "número de verdade. Cada ativo tem alvo de lucro e stop próprios, medidos "
        "separadamente: o que funciona numa ação de centavos não funciona numa de "
        "cento e cinquenta reais, e isso não é preferência, é medição. Pedir um "
        "ativo fora da lista faz o robô se recusar a ligar em vez de reaproveitar a "
        "calibração de outro papel.",
        "Cada ativo também exige um caixa mínimo diferente, e é aí que a escolha "
        "aperta: day trade compra em lote inteiro de 100 ações, e o piso é o DOBRO "
        "do custo de um lote. Uma ação de R$ 0,14 pede R$ 28; uma de R$ 151,95 pede "
        "R$ 30.390. O mesmo robô, o mesmo desenho, mais de mil vezes o capital — é o "
        "caixa, não a mecânica, que decide quais ativos estão ao alcance de quem "
        "opera.",
        "Nas primeiras horas do pregão, os níveis são calculados a partir do preço de "
        "abertura do dia. Depois das 11h de Brasília, passam a ser calculados a partir "
        "do preço do momento, refeitos a cada ordem nova — medimos que os níveis "
        "presos na abertura vão ficando longe demais conforme o dia avança, e param de "
        "ser tocados.",
        "Ele alterna os lados: depois de fechar uma compra, a próxima tentativa é uma "
        "venda. Nunca dorme com posição aberta, e se o prejuízo acumulado do dia "
        "chegar a 20% do caixa mínimo do ativo ele fecha o que estiver aberto e não "
        "opera mais até o próximo pregão — numa ação de R$ 0,14 isso são uns R$ 5,60; "
        "numa de R$ 151,95, uns R$ 6.078.",
    )
    plain_example = (
        "O exemplo abaixo usa PMAM3, um dos ativos calibrados. Em qualquer outro da "
        "tabela a mecânica é idêntica, mas os números mudam — alvo, stop e caixa "
        "mínimo são próprios de cada ativo.",
        "PMAM3 abre o dia a R$ 0,14. O alvo de lucro dela é 0,32% do preço — menos "
        "de um centavo. Como a bolsa não negocia fração de centavo, o alvo vira o "
        "mínimo possível: 1 centavo.",
        "Ele deixa uma ordem de compra parada a R$ 0,13, um centavo abaixo. Enquanto "
        "o preço não tocar ali, nada acontece — nenhuma ordem enviada, nenhum custo.",
        "O preço cai a R$ 0,13 e a ordem é executada: 100 ações, R$ 13,00 investidos. "
        "Na mesma hora ele deixa a venda parada a R$ 0,14.",
        "Se o preço volta a R$ 0,14, a venda sai: R$ 1,00 de lucro bruto na ida e "
        "volta, menos a taxa da bolsa. Ele então tenta o lado oposto, uma venda a "
        "descoberto, pelo mesmo mecanismo.",
        "Se em vez de subir o preço cair a R$ 0,12, o stop sai com R$ 1,00 de "
        "prejuízo. É por isso que um papel de centavos exige calibração medida: num "
        "preço tão baixo, um único centavo já é 7% do valor da ação — e é por isso "
        "que a CSAN3, a R$ 3,64, usa um alvo menor (0,21%) e um stop bem mais largo.",
    )
    watched_signals = (
        "O preço de abertura do dia, que ancora todos os níveis das primeiras horas.",
        "O preço do momento, que passa a ancorar os níveis depois das 11h de Brasília.",
        "O relógio do pregão — é ele que decide qual das duas âncoras vale agora.",
        "O resultado acumulado do dia, em reais, contra o limite de prejuízo do ativo "
        "(20% do caixa mínimo dele).",
        "Quantas operações já fez de cada lado, contra o teto de 15 por lado.",
        "Há quanto tempo a ordem parada está esperando sem ser tocada.",
    )
    entry_rules = (
        "Uma ordem parada por vez, um pouco abaixo do preço de referência para "
        "comprar (ou acima, para vender a descoberto). Ele espera o preço vir até "
        "ele — nunca paga o spread para entrar.",
        "Os três níveis (entrada, alvo e stop) saem de um percentual do preço de "
        "referência, arredondado para centavos inteiros. Em ações de centavos, esse "
        "arredondamento é o que manda: tudo tende a virar 1 centavo.",
        "Esse percentual é do ATIVO, não do robô: cada ativo liberado tem alvo e "
        "stop próprios, medidos separadamente. Trocar de ativo troca os dois "
        "números junto — ver a tabela de ativos.",
        "Até as 11h de Brasília a referência é a abertura do dia; depois, é o preço "
        "do momento. Esse corte não foi otimizado — é o meio entre o horário em que a "
        "medição ainda dava lucro e o em que já dava prejuízo.",
        "Alterna os lados: depois de fechar uma compra, tenta uma venda, e só insiste "
        "no mesmo lado quando o outro já bateu o teto de 15 operações.",
        "Ordem parada que ficou velha é cancelada e refeita no preço atual — tanto a "
        "que sobrou da fase da abertura quanto a que esperou tempo demais sem ser "
        "tocada.",
    )
    exit_rules = (
        "Vende com uma ordem parada no alvo, também sem perseguir o preço: sair como "
        "quem espera, e não como quem paga o spread, é o centro do desenho.",
        "Se o preço vai contra, o stop fecha a posição na direção oposta ao alvo.",
        "Se o prejuízo acumulado do dia chega a 20% do caixa mínimo do ativo, fecha "
        "o que estiver aberto e encerra: nada mais é enviado até o próximo pregão.",
        "Nunca carrega posição para o dia seguinte. O fechamento segue o calendário "
        "real da B3, não um horário fixo — o pregão muda de hora com o horário de "
        "verão americano.",
    )
    sizing_rules = (
        "Sempre em lotes inteiros de 100 ações — nunca no mercado fracionário, onde "
        "cada ordem custaria R$ 1,90 fixos de corretagem. O NÚMERO de lotes por "
        "ordem, porém, não é fixo: cresce com o caixa acumulado e encolhe de volta "
        "se ele cair.",
        "A cada entrada nova ele recalcula: a cada 4x o custo de 1 lote que o caixa "
        "acumulado tiver, usa mais um lote. O teto é 10% do volume do ÚLTIMO minuto "
        "FECHADO — nunca pedir do mercado uma fatia maior que essa. Na abertura, "
        "quando ainda não há 1 minuto do próprio pregão, completa com o final do "
        "pregão anterior.",
        "Cada ativo tem um caixa mínimo próprio para começar a operar: o piso é o "
        "DOBRO do custo de um lote de 100 ações, sem arredondamento. É a diferença "
        "entre poder operar um ativo e não poder — ver a tabela de ativos.",
        "Em lote inteiro a corretagem é zero na Rico. O que sobra é a taxa da bolsa, "
        "e o backtest assume o DOBRO da taxa real, de propósito, como margem de "
        "segurança.",
        "O giro alto é o risco econômico do desenho: cada ida e volta paga a taxa duas "
        "vezes. O teto de 15 operações por lado é o que limita isso por dia.",
    )
    # Fração mostrada como percentual na ficha (ver `Strategy.param_pct` --
    # `IntradayStrategy` não herda de `Strategy`, mas quem lê usa `getattr`).
    param_pct = ("profit_pct", "session_stop_pct_capital", "realocacao_teto_pct_volume_minuto")
    # Fora da tabela PLANA de parâmetros porque o valor deles é POR ATIVO, e a
    # tabela mostra uma instância só (a default, PMAM3). Ela anunciava
    # "symbol=PMAM3, profit_pct=0,32%, stop_multiplier=10" como se fossem os
    # números DO ROBÔ -- são os da PMAM3, e não valem para nenhum outro papel.
    # Quem carrega todos é a tabela de ativos da ficha, alimentada por
    # `calibrated_setups()`.
    # `quantity` some' da tabela pelo MESMO motivo que profit_pct/stop_multiplier:
    # nao e' mais um parametro de verdade. Passar um valor explicito no
    # construtor NAO tem efeito -- `_build_entry` sempre recalcula
    # `self.quantity` via `_lotes_por_realocacao` antes de cada entrada.
    # Mostrar "1 lote (100 acoes)" (o "—" formatado) seria uma MENTIRA
    # especifica: o tamanho de verdade varia a cada entrada, conforme o caixa
    # acumulado E o volume medio recente, explicado em prosa em `sizing_rules`.
    param_hidden = ("symbol", "profit_pct", "stop_multiplier", "quantity")
    # O valor cru é o relógio do terminal MT5 (UTC), e é ele que `on_bar`
    # compara. A ficha mostra "14:00 UTC" como valor e "11:00 Brasília" ao
    # lado, em corpo menor -- ver `Strategy.param_utc_time`.
    param_utc_time = ("fixed_anchor_until",)
    param_docs = {
        "symbol": "Ativo que ele negocia.",
        "tick_size": "Variação mínima de preço do ativo.",
        "profit_pct": "Alvo de lucro por trade, em % do preço da âncora. Vazio = lookup por "
                      "símbolo em `_CALIBRATION_BY_SYMBOL` (falha se o símbolo não estiver lá).",
        "spacing_multiplier": "Distância da entrada, em múltiplos do alvo.",
        "stop_multiplier": "Distância do stop, em múltiplos do alvo. Vazio = mesmo lookup de "
                           "`profit_pct`.",
        "max_trades_per_side": "Teto de preenchimentos por lado, por sessão.",
        "session_stop_pct_capital": "Percentual do caixa mínimo do dia que define a "
                                    "perda-limite diária.",
        "realocacao_limiar_caixa": "Quantas vezes o custo de 1 lote o caixa acumulado precisa "
                                   "ter para a próxima entrada usar mais um lote (encolhe de volta "
                                   "se o caixa cair).",
        "realocacao_teto_pct_volume_minuto": "Teto de posição: % da média de volume por minuto "
                                             "na janela rolante (`realocacao_janela_minutos`).",
        "realocacao_janela_minutos": "Tamanho da janela (minutos) da média móvel de volume que "
                                     "alimenta o teto acima. Reavaliada a cada entrada nova; na "
                                     "abertura, completa com a cauda do pregão anterior.",
        # Exibido em hora de Brasília com o UTC ao lado (`param_utc_time`), então
        # a descrição não precisa mais carregar a conversão.
        "fixed_anchor_until": "Hora em que a âncora fixa vira rolante.",
        "rolling_reanchor_after_bars": "Barras que uma ordem rolante espera antes de rearmar.",
    }
    @staticmethod
    def calibrated_setups() -> tuple[SymbolSetup, ...]:
        """Os ativos calibrados, alcançáveis a partir da CLASSE.

        Espelho fino de `calibrated_setups()` (módulo) de propósito: quem
        monta a ficha (`dashboard/robot_view.py`) recebe a classe do robô e
        procura este nome com `getattr`, sem saber de que módulo ela veio. Um
        robô de day trade de um símbolo só simplesmente não define o método, e
        a ficha dele cai no caminho de ativo único.
        """
        return calibrated_setups()

    # A saida por alvo deste robo e uma ordem-limite parada no nivel: e o
    # centro do desenho (capturar o spread em vez de paga-lo), nao um
    # detalhe de modelagem. Ver `IntradayStrategy.target_fills_as_maker`.
    target_fills_as_maker = True

    def __init__(
        self,
        symbol: str = "PMAM3",
        tick_size: float = 0.01,
        profit_pct: float | None = None,
        spacing_multiplier: float = 2.0,
        stop_multiplier: float | None = None,
        max_trades_per_side: int = 15,
        session_stop_pct_capital: float = SESSION_STOP_FRACAO_PADRAO,
        quantity: int | None = None,
        fixed_anchor_until: time = time(14, 0),
        rolling_reanchor_after_bars: int = 30,
        realocacao_limiar_caixa: float = REALOCACAO_LIMIAR_CAIXA_PADRAO,
        realocacao_teto_pct_volume_minuto: float = REALOCACAO_TETO_PCT_VOLUME_MINUTO_PADRAO,
        realocacao_janela_minutos: float = REALOCACAO_JANELA_MINUTOS_PADRAO,
    ):
        self.symbol = symbol
        self.tick_size = tick_size
        # `None` (o default) = busca a calibracao do SIMBOLO na tabela
        # (mesmo padrao de `default_quantity` em
        # `backtest/intraday/profiles.py::config_for`: sentinela `None`
        # resolvido aqui dentro, nunca herdado de outro papel). Quem passa
        # `profit_pct=`/`stop_multiplier=` explicito sempre vence o lookup.
        if profit_pct is None or stop_multiplier is None:
            calib = _CALIBRATION_BY_SYMBOL.get(symbol)
            if calib is None:
                raise ValueError(
                    f"gremah: sem calibracao para o simbolo {symbol!r} em "
                    "_CALIBRATION_BY_SYMBOL (strategy/daytrade/lab/gremah.py). "
                    "profit_pct/stop_multiplier NAO transferem entre simbolos "
                    "(medido 2026-08-21) -- passe profit_pct= e "
                    "stop_multiplier= explicitamente, ou meca este simbolo "
                    "(backtest IS + OOS) e adicione-o a tabela antes de "
                    "operar com o default."
                )
            if profit_pct is None:
                profit_pct = calib.profit_pct
            if stop_multiplier is None:
                stop_multiplier = calib.stop_multiplier
        self.profit_pct = profit_pct
        self.spacing_multiplier = spacing_multiplier
        self.stop_multiplier = stop_multiplier
        self.max_trades_per_side = max_trades_per_side
        # Perda-limite do dia = session_stop_pct_capital x capital_minimo_brl,
        # recalculada na abertura da sessao (ver on_bar).
        self.session_stop_pct_capital = abs(session_stop_pct_capital)
        self.quantity = quantity
        self.fixed_anchor_until = fixed_anchor_until
        # uma ordem ROLANTE parada esperando por muitas barras acumula o
        # MESMO problema que motivou abandonar a ordem fixa na troca de
        # fase: seu preco de ancora (o preco de QUANDO foi armada) vai
        # ficando cada vez mais desatualizado frente ao preco ATUAL.
        # Achado empirico (2026-08-21): sem isso, uma ordem herdada do
        # warm-start (armada perto do fim da fase fixa, nunca tocada) fica
        # parada com ancora velha por horas ate' o robo comecar a operar
        # de verdade num horario atrasado -- o hibrido ficava pior que a
        # rolling pura em todo horario de entrada atrasada.
        self.rolling_reanchor_after_bars = rolling_reanchor_after_bars
        self.realocacao_limiar_caixa = abs(realocacao_limiar_caixa)
        self.realocacao_teto_pct_volume_minuto = abs(realocacao_teto_pct_volume_minuto)
        self.realocacao_janela_minutos = abs(realocacao_janela_minutos)

        self._state = _SessionState()
        # Atualizado por `on_capital_update`, chamado pelo motor logo antes de
        # `on_bar` -- 0.0 so' antes da primeira barra real (warm start nunca
        # chama `on_capital_update`, entao a primeira ordem calibrada por
        # replay usa 1 lote, o minimo; a primeira barra AO VIVO ja chega com o
        # caixa real).
        self._cash_atual_brl = 0.0
        # Sobrevive a `on_session_start` de proposito (so' a parte de HOJE
        # zera, ver `RollingVolumeWindow.iniciar_sessao`) -- a cauda do
        # pregao anterior e' definida por `seed_volume_window`, que pode ser
        # chamada antes OU depois de `on_session_start`.
        self._janela_volume = RollingVolumeWindow(self.realocacao_janela_minutos)

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()
        self._janela_volume.iniciar_sessao()

    def on_capital_update(self, cash_brl: float) -> None:
        self._cash_atual_brl = cash_brl

    def seed_volume_window(self, previous_session_tail: list[Bar]) -> None:
        self._janela_volume.definir_cauda_anterior(previous_session_tail)

    def _ticks_from_pct(self, price: float, pct: float) -> int:
        return max(1, round(price * pct / self.tick_size))

    def _arm_fixed_session_params(self) -> None:
        price = self._state.open_price
        self._state.profit_ticks_today = self._ticks_from_pct(price, self.profit_pct)
        self._state.spacing_ticks_today = self._ticks_from_pct(price, self.profit_pct * self.spacing_multiplier)
        self._state.stop_ticks_today = self._ticks_from_pct(price, self.profit_pct * self.stop_multiplier)

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
        """Quantos lotes a proxima entrada usa, dado o caixa acumulado
        (`on_capital_update`) e o teto de volume rolante (`_janela_volume`).
        Os DOIS sao recalculados a CADA entrada nova, nao 1x por dia --
        tambem ENCOLHEM se o caixa cair ou o giro recente esfriar. `anchor`
        e' a mesma ancora que spacing/alvo/stop ja usam (fixa na abertura ou
        rolante), nao um preco fixo: o custo de 1 lote muda com ela."""
        custo_do_lote = anchor * LOTE_PADRAO_B3
        lotes = 1 + math.floor(self._cash_atual_brl / (self.realocacao_limiar_caixa * custo_do_lote))
        media_volume_min = self._janela_volume.media_por_minuto(ts)
        teto_acoes = media_volume_min * self.realocacao_teto_pct_volume_minuto
        max_lotes_dia = max(1, int(teto_acoes) // LOTE_PADRAO_B3)
        return min(max_lotes_dia, max(1, lotes))

    def _build_entry(self, side: str, anchor: float, spacing_ticks: int, profit_ticks: int, stop_ticks: int | None, ts: pd.Timestamp) -> EnterLimit:
        self.quantity = self._lotes_por_realocacao(anchor, ts) * LOTE_PADRAO_B3
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
            reason="gremah_" + side,
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

        # Armada UMA vez por sessao, na primeira barra vista -- independente
        # de comecar em fase fixa ou ja' direto em rolante (robo ligado
        # atrasado): `_arm_fixed_session_params`, abaixo, so' roda em fase
        # fixa, e um inicio 100% rolante nunca a chamaria, deixando o limite
        # de perda diaria travado no default `0.0` do dataclass (halt na
        # primeira barra) se isto morasse la' dentro.
        # Alimenta a janela de volume rolante com TODA barra vista, mesmo
        # fora de sinal de entrada -- e' o dado bruto que `_lotes_por_
        # realocacao` consulta na hora de armar uma ordem nova (ver
        # `strategy.daytrade.base.RollingVolumeWindow`).
        self._janela_volume.registrar(ts, bar.volume)

        if not state.session_stop_armed:
            state.session_stop_armed = True
            state.session_stop_brl_hoje = capital_minimo_brl(bar.open) * self.session_stop_pct_capital

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
                state.pending_bars_waited = 0
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        # ordem pendente parada ficou obsoleta de 1 de 2 jeitos: (a) foi
        # armada na fase FIXA e o relogio ja passou pra fase ROLANTE --
        # nivel so' fazia sentido perto da abertura; (b) foi armada em
        # modo ROLANTE mas ja' esperou tempo demais sem tocar -- seu
        # preco de ancora (de QUANDO foi armada) ja' ficou velho frente
        # ao preco atual. Nos dois casos: abandona (o motor substitui a
        # resting_limit pela nova `EnterLimit` devolvida abaixo) e
        # re-arma no modo/preco atual, mesmo lado.
        stale_fixed_order = state.pending_side is not None and state.pending_mode == "fixed" and not is_fixed_phase
        stale_rolling_order = (
            state.pending_side is not None and state.pending_mode == "rolling"
            and state.pending_bars_waited >= self.rolling_reanchor_after_bars
        )
        stale_order = stale_fixed_order or stale_rolling_order
        if state.pending_side is not None and not stale_order:
            state.pending_bars_waited += 1
            return actions

        next_side = state.pending_side if stale_order else self._next_side_to_arm()
        if next_side is None:
            return actions

        state.pending_side = next_side
        state.pending_bars_waited = 0
        state.pending_mode = "fixed" if is_fixed_phase else "rolling"
        if is_fixed_phase:
            entry = self._build_entry(
                next_side, state.open_price,
                state.spacing_ticks_today, state.profit_ticks_today, state.stop_ticks_today,
                ts,
            )
        else:
            anchor = bar.close
            profit_ticks = self._ticks_from_pct(anchor, self.profit_pct)
            spacing_ticks = self._ticks_from_pct(anchor, self.profit_pct * self.spacing_multiplier)
            stop_ticks = self._ticks_from_pct(anchor, self.profit_pct * self.stop_multiplier)
            entry = self._build_entry(next_side, anchor, spacing_ticks, profit_ticks, stop_ticks, ts)
        return [entry]
