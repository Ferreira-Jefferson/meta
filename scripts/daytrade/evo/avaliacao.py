"""AVALIACAO de um individuo -- o caixa ANDA, e quem fica sem caixa MORRE.

## A regra que define esta busca

Ordem do dono, 2026-09-18: *"todas as especies devem ser assim -- se elas
ficarem sem capital para operar, elas morrem"*, e o objetivo e' *"aumentar o
capital sem que em nenhum momento ela fique sem capital para operar"*.

Entao a avaliacao nao e' uma soma de pregoes independentes. E' uma
CAMINHADA: comeca em R$500, cada pregao parte de onde o anterior terminou, e
se o caixa cai abaixo da margem crua (R$150) o individuo esta' morto --
nenhum pregao seguinte acontece, e nenhum fitness de sobrevivente pode ser
alcancado por ele.

E' o desenho do Flappy Bird aplicado a serio: nao existe "quase bateu no
cano". O passaro que bateu perdeu, por melhor que fosse o voo ate' ali.

### Por que isso e' MELHOR que medir com capital reposto, e nao pior

Havia uma objecao de metodo real contra medir assim, e ela esta' escrita em
CLAUDE.md: uma janela em que o robo parou por falta de caixa esta'
CENSURADA -- ela mede a restricao, nao a estrategia. Pior, dentro de uma
busca evolutiva a censura cria um gradiente perverso: um genoma que perde
cedo fica PROTEGIDO de perder mais, e aparece na tabela como "quase neutro"
enquanto um genoma que opera o tempo todo acumula perdas visiveis.

A objecao cai -- e' importante entender por que, porque e' o que torna este
desenho legitimo. Ela so' vale quando o liquido e' o criterio. **Aqui morrer
e' pontuado como o pior desfecho que existe**, abaixo de qualquer
sobrevivente, e a ordenacao dentro da faixa dos mortos e' por quanto tempo
aguentaram. Parar de perder cedo deixa de ser protecao e vira eliminacao.
Nao ha' como um genoma lucrar com a propria censura.

O que a censura ainda faz e' outra coisa, e essa e' real e fica registrada:
**a janela em que um individuo morre nao mede a geometria dele**, so' mede
que ele morreu. Por isso o relatorio final de um sobrevivente sempre mostra
as duas leituras -- a caminhada (sobreviveu?) e as metricas por operacao
(tem edge?) --, e elas respondem perguntas diferentes.

## Blocos CONTIGUOS, nunca sorteio disperso

Como o resultado depende do CAMINHO, a amostra de uma geracao tem de ser um
pedaco cronologico de verdade. Sortear 20 pregoes espalhados e encadear o
caixa entre eles produziria uma trajetoria que nunca existiu -- com os
pregoes ruins diluidos por vizinhos que na realidade estavam a semanas de
distancia. A amostra e' um bloco CONTIGUO sorteado de dentro do treino: a
janela muda a cada geracao (e' o que impede decorar uma janela fixa), mas
cada janela e' um trecho real da historia, na ordem em que aconteceu.

## O que o fitness premia, em ordem

    1. SOBREVIVER a janela inteira -- condicao, nao termo;
    2. ter AMOSTRA (>= MIN_TRADES operacoes) -- um individuo com 3 operacoes
       pode ter qualquer R$/op, e o caso degenerado que uma busca encontra
       sozinha e' o robo que nao opera: ele nunca morre;
    3. crescer o caixa de forma REGULAR -- media menos desvio do resultado
       por pregao entre blocos, nao o liquido. Um individuo que ganha R$3.000
       num bloco e perde R$500 nos outros tres perde para um que ganha R$300
       em todos;
    4. devolver pouco, em TERMOS RELATIVOS -- o drawdown maximo medido
       contra o PICO de caixa daquele instante, nao em reais. Perder R$50
       com R$100 em caixa e perder R$50 com R$1.000 sao o mesmo numero e
       riscos de quebrar a banca completamente diferentes (exemplo do dono,
       2026-09-18). Isto e' o que o item 5 sozinho nao pega: uma conta que
       foi de R$500 a R$1.500 e voltou a R$600 nunca chegou perto da margem;
    5. ter FOLGA -- quanto o caixa chegou perto da margem. "Sem que em nenhum
       momento ela fique sem capital" nao e' so' nao morrer: e' nao passar
       raspando. Mede distancia da MORTE, enquanto o item 4 mede
       INSTABILIDADE -- as duas coisas se movem separado.

## Tamanho de posicao: 1 contrato, fixo

Nao escala com o caixa, e isso e' deliberado. O motor sabe escalar
(`contracts_from_capital_operacional`, e a escada de risco do sistema), mas
foi exposicao AGREGADA -- dois contratos simultaneos num caixa de R$300 --
que zerou a conta de verdade em 2026-08-28. Escalar e' uma alavanca
SEPARADA, que se mede depois de existir um genoma que sobrevive com um
contrato. Medir as duas juntas confunde "a politica e' boa" com "a escada
compensou uma politica ruim".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

from backtest.intraday.engine import run_intraday_backtest
from backtest.intraday.fidelidade import fidelidade_for
from backtest.intraday.profiles import config_for, profile_for
from strategy.daytrade.evo.genoma import Genoma
from strategy.daytrade.lab.wdo_evo import WdoEvo

from evo.dados import (
    BARRAS_POR_MINUTO, CAPITAL_PARTIDA_BRL, ECONOMIA_WDO,
    FILA_MULTIPLICADOR_M1, MARGEM_WDO_BRL, SYMBOL, bars_m1, bars_tick,
)

#: Piso de atividade, como TAXA (operacoes por pregao) e nao como numero
#: absoluto. Abaixo disto o individuo nao tem amostra para ser julgado -- ver
#: o item 2 da lista na docstring do modulo.
#:
#: Tem de ser taxa: com um numero fixo, uma janela curta joga a populacao
#: INTEIRA na faixa "sem amostra" e o gradiente desaparece (medido -- com
#: piso de 10 numa janela de 6 pregoes, os 16 individuos ficaram todos na
#: mesma faixa e a selecao virou sorteio). 0,4 e' aproximadamente uma
#: operacao a cada dois pregoes e meio: ralo o bastante para nao exigir giro
#: alto, apertado o bastante para excluir o robo que quase nao opera.
MIN_TRADES_POR_PREGAO = 0.4
#: Piso absoluto, para janelas muito curtas nao aceitarem 1 operacao.
MIN_TRADES_ABSOLUTO = 5


def min_trades(n_pregoes: int) -> int:
    return max(MIN_TRADES_ABSOLUTO,
               int(round(MIN_TRADES_POR_PREGAO * n_pregoes)))

#: Peso do desvio ENTRE BLOCOS na agregacao pessimista. 0,5 e' uma escolha,
#: nao uma medicao: penaliza concentracao o bastante para mudar a ordem entre
#: individuos parecidos, sem virar "minimize a variancia" (que elegeria o
#: robo que nao opera, se nao fosse o piso de operacoes).
LAMBDA_DESVIO = 0.5

#: Penalidade, em R$ por pregao, de ter chegado a ENCOSTAR na margem. Um
#: individuo que nunca desceu de R$500 nao paga nada; um que raspou os R$150
#: paga isto inteiro. Mede distancia da MORTE.
PENALIDADE_SEM_FOLGA = 3.0

#: Penalidade, em R$ por pregao, do DRAWDOWN RELATIVO maximo. Um individuo
#: que nunca devolveu nada nao paga; um que devolveu 50% do pico paga metade
#: disto; um que zerou paga tudo.
#:
#: ORDEM DO DONO, 2026-09-18, com o exemplo dele: *"se estou com R$100 em
#: caixa e perco R$50, e outra tinha R$1.000 e perde R$50, o valor e' o
#: mesmo, mas R$50 pra quem tem R$1.000 nao e' nada -- o risco de quebrar a
#: banca e' baixo. Eu seria eliminado por ter perdido 50 enquanto tinha
#: somente 100."*
#:
#: E' por isso que o drawdown tem de ser RELATIVO ao caixa do momento, e nao
#: em reais. A metrica de folga sozinha nao pega isso: uma conta que foi de
#: R$500 a R$1.500 e voltou a R$600 nunca chegou perto da margem (folga
#: quase cheia) e mesmo assim devolveu 60% do pico, que e' um robo que
#: quebraria se aquele mesmo trecho acontecesse mais cedo.
#:
#: MEDIDO em 2026-09-19: com peso 20,0 e LINEAR, a penalidade pesou de 3% a
#: 11% do fitness dos 10 campeoes (media -5,0 contra fitness de +45 a +92).
#: A regra do dono era decorativa na pratica -- nenhum campeao foi rebaixado
#: por devolver 30% do pico, e os campeoes chegaram a validacao com DD
#: relativo de 60% a 96%.
#:
#: Agora e' QUADRATICA, e a forma importa mais que o peso: risco de quebrar a
#: banca nao cresce em linha reta com a devolucao. Devolver 15% e' custo de
#: operacao; devolver 80% e' um robo que so' nao quebrou porque o trecho ruim
#: calhou de vir depois do bom. Com 200,0 * dd^2:
#:
#:     dd  15% ->   4,5      dd  50% ->  50,0
#:     dd  30% ->  18,0      dd  80% -> 128,0
#:     dd  35% ->  24,5      dd  96% -> 184,3
#:
#: Barato onde e' barato, fatal onde e' fatal. Nos 10 campeoes desta base
#: isso reordena a fila sem zerar ninguem (rompimento +56,9 -> +44,4;
#: microestrutura +69,6 -> +47,7), e apaga qualquer coisa acima de 60%.
PENALIDADE_DD_RELATIVO = 200.0

#: Em quantos blocos cronologicos a janela e' cortada para a agregacao.
N_BLOCOS = 4

#: Faixas de fitness, separadas de forma que nenhum individuo de uma faixa
#: alcance a de cima. Nao sao numeros magicos soltos: sao a codificacao da
#: ordem de prioridade da docstring num unico escalar, que e' o que o torneio
#: de selecao consegue comparar.
FITNESS_MORTO = -10_000.0     # + ate 1000 pela fracao da janela sobrevivida
FITNESS_SEM_AMOSTRA = -1_000.0  # + a contagem de operacoes

_FID = fidelidade_for(SYMBOL)


@dataclass
class Resultado:
    """O que uma avaliacao devolve.

    Guarda o BRUTO (`pnls`, `pontos`, `caixa_por_pregao`) junto das metricas
    porque o relatorio final precisa de breakeven empirico e IC, e
    recalcular isso a partir de medias arredondadas ja' produziu divergencia
    antes."""

    fitness: float = FITNESS_MORTO
    morreu: bool = False
    pregoes_vividos: int = 0
    pregoes_oferecidos: int = 0
    caixa_final: float = 0.0
    caixa_minimo: float = 0.0
    #: Maior devolucao RELATIVA ao pico de caixa ate' aquele instante,
    #: medida operacao a operacao. 0,40 = em algum momento a conta devolveu
    #: 40% do que ja' tinha acumulado. Ver `PENALIDADE_DD_RELATIVO`.
    dd_relativo: float = 0.0
    #: O mesmo drawdown em reais -- guardado ao lado so' para o relatorio
    #: poder mostrar os dois e deixar visivel que sao coisas diferentes.
    dd_absoluto: float = 0.0
    n_trades: int = 0
    liquido: float = 0.0
    r_por_op: float = 0.0
    win_pct: float = 0.0
    breakeven_emp: float = 0.0
    r_por_pregao: float = 0.0
    pregoes_com_op: int = 0
    desvio_op: float = 0.0
    pnls: list[float] = field(default_factory=list)
    pontos: list[float] = field(default_factory=list)
    caixa_por_pregao: list[float] = field(default_factory=list)

    @property
    def folga(self) -> float:
        """1,0 = nunca desceu do capital de partida; 0,0 = encostou na
        margem. E' o colchao que sobrou, normalizado."""
        vao = CAPITAL_PARTIDA_BRL - MARGEM_WDO_BRL
        if vao <= 0:
            return 0.0
        return max(0.0, min(1.0, (self.caixa_minimo - MARGEM_WDO_BRL) / vao))

    @property
    def frac_sem_op(self) -> float:
        if not self.pregoes_vividos:
            return 1.0
        return 1.0 - self.pregoes_com_op / self.pregoes_vividos


def monta_config(feed: str, capital: float):
    """A config do motor -- pelo MESMO montador que `scripts/run_live.py` usa
    para subir o robo sombra.

    E' isso que faz a janela de pregao (12:00-21:30 UTC, achatamento 21:25),
    a corretagem (R$0,50 round-trip), o piso de margem e o portao de caixa
    aqui serem literalmente os da operacao real, em vez de uma reconstrucao
    parecida. Reimplementar qualquer um deles criaria a divergencia classica
    entre robo validado e robo que opera.

    A fila e' o UNICO ponto em que o backtest diverge da producao de
    proposito, e a divergencia e' para o lado DURO: em M1 a calibracao de
    `fidelidade.py` e' multiplicada por `FILA_MULTIPLICADOR_M1`, porque o
    motor credita o volume inteiro do minuto contra a fila. Ver `evo.dados`."""
    mult = FILA_MULTIPLICADOR_M1 if feed == "m1" else 1.0
    valor_tick, tam_tick = ECONOMIA_WDO
    return config_for(
        profile_for(SYMBOL),
        trade_tick_value=valor_tick, trade_tick_size=tam_tick,
        target_fills_as_maker=True,
        anchor_exits_at_fill=True,
        initial_capital=capital,
        queue_ahead_qty=_FID.queue_ahead_qty * mult,
        exit_queue_ahead_qty=_FID.exit_queue_ahead_qty * mult,
    )


def monta_robo(genoma: Genoma, feed: str) -> WdoEvo:
    return WdoEvo(genoma=genoma, feed_kind=feed,
                  barras_por_minuto=BARRAS_POR_MINUTO[feed])


def fitness_medido(r: Resultado) -> float:
    """So' o TERMO MEDIDO do fitness -- sem as portas de morte e de amostra.

    Existe porque as portas nao podem ser aplicadas bloco a bloco quando o
    escore do individuo e' o MINIMO entre varios blocos. Ver
    `ga._avalia_worker`: morte continua valendo por bloco (quem quebra num
    trecho quebrou), mas o piso de AMOSTRA passa a valer sobre o agregado.

    MEDIDO em 2026-09-19, e foi o que obrigou a separacao: o campeao da ilha
    `vwap` pontuava **-54,4** com a particao comecando no dia 0 e **-995,0**
    com ela comecando no dia 1. Um deslocamento de UM dia. A causa nao era a
    estrategia mudar -- era um dos tres blocos cair de 7 para 5 operacoes e
    atravessar o piso de amostra, o que jogava o individuo inteiro na faixa
    sentinela, indistinguivel de um genoma que nunca opera.

    Piso de amostra por bloco e' um penhasco onde deveria haver medida: 6
    operacoes em 17 pregoes nao e' "sem evidencia", e' menos evidencia. No
    agregado (51 pregoes, piso de 20 operacoes) o degrau volta a proteger do
    que foi feito para proteger -- o robo que nao opera -- sem destruir a
    leitura de quem opera pouco num trecho."""
    por_pregao = r.caixa_por_pregao
    if not por_pregao:
        return FITNESS_SEM_AMOSTRA
    tam = max(1, len(por_pregao) // N_BLOCOS)
    blocos = [por_pregao[i:i + tam] for i in range(0, len(por_pregao), tam)]
    blocos = [b for b in blocos if b]
    medias = [sum(b) / len(b) for b in blocos]
    media = sum(medias) / len(medias)
    desvio = (math.sqrt(sum((m - media) ** 2 for m in medias)
                        / (len(medias) - 1)) if len(medias) > 1 else 0.0)
    return (media
            - LAMBDA_DESVIO * desvio
            - PENALIDADE_DD_RELATIVO * r.dd_relativo ** 2
            - PENALIDADE_SEM_FOLGA * (1 - r.folga))


def fitness_morte(r: Resultado) -> float:
    """A faixa dos mortos, ordenada por quanto da janela aguentaram."""
    vivido = (r.pregoes_vividos / r.pregoes_oferecidos
              if r.pregoes_oferecidos else 0.0)
    return FITNESS_MORTO + 1000.0 * vivido


def _fitness(r: Resultado) -> float:
    """As quatro prioridades da docstring codificadas num escalar.

    Vale para UM bloco isolado (a validacao, a confirmacao em tick, a
    bancada). Na busca, onde o individuo enfrenta varios blocos, quem compoe
    o escore e' `ga._avalia_worker` a partir de `fitness_medido`."""
    if r.morreu:
        # Ordenado por quanto da janela aguentou: morrer no pregao 40 de 50
        # e' melhor que morrer no 3o, e a busca consegue subir por esse
        # gradiente ate' a faixa dos sobreviventes.
        return fitness_morte(r)
    if r.n_trades < min_trades(r.pregoes_vividos):
        # Sobreviveu sem operar. Nao e' morte, mas tambem nao e' evidencia de
        # nada -- e sem este degrau a busca convergiria para o robo que nunca
        # opera, que e' o sobrevivente perfeito.
        return FITNESS_SEM_AMOSTRA + r.n_trades
    return fitness_medido(r)


def avalia(genoma: Genoma, dias: list[str], feed: str = "m1",
           capital: float = CAPITAL_PARTIDA_BRL) -> Resultado:
    """UM individuo contra um bloco CONTIGUO de pregoes, com o caixa ANDANDO.

    `dias` tem de vir em ordem cronologica e ser contiguo -- ver a secao
    "Blocos CONTIGUOS" da docstring do modulo. A funcao nao verifica isso
    (seria custo por chamada num caminho que roda dezenas de milhares de
    vezes); quem monta a amostra e' `ga.py`, e o teste que garante o contrato
    mora em `tests/`.

    O criterio de morte e' a MARGEM CRUA (R$150), nao o piso de partida de
    R$375. O piso cheio e' indicacao de PARTIDA e governa ESCALAR, nao
    sobreviver: abaixo da margem quem recusa e' a corretora, e nao faz
    sentido o motor recusar antes (CLAUDE.md, "O piso de capital e' indicacao
    de PARTIDA, nunca condicao de continuidade")."""
    carregar = bars_m1 if feed == "m1" else bars_tick
    caixa = capital
    minimo = capital
    # Pico corrente do caixa e a maior devolucao a partir dele. Medidos
    # OPERACAO A OPERACAO, nao por pregao: um dia que abre bem, sobe R$300 e
    # devolve tudo antes de fechar tem drawdown real, e a foto do fechamento
    # nao mostra nada.
    pico = capital
    dd_rel = 0.0
    dd_abs = 0.0
    pnls: list[float] = []
    pontos: list[float] = []
    caixa_por_pregao: list[float] = []
    com_op = 0
    vividos = 0
    morreu = False

    for dia in dias:
        if caixa < MARGEM_WDO_BRL:
            morreu = True
            break
        bars = carregar(dia)
        if bars.empty:
            continue
        res = run_intraday_backtest(bars, monta_robo(genoma, feed),
                                    monta_config(feed, caixa))
        vividos += 1
        do_dia = []
        for t in res.trades:
            caixa += t.pnl_brl
            minimo = min(minimo, caixa)
            if caixa > pico:
                pico = caixa
            elif pico > 0:
                # RELATIVO ao pico, que e' o ponto do dono: perder R$50 com
                # R$100 em caixa e perder R$50 com R$1.000 sao riscos de
                # quebrar a banca completamente diferentes.
                dd_abs = max(dd_abs, pico - caixa)
                dd_rel = max(dd_rel, (pico - caixa) / pico)
            do_dia.append(t.pnl_brl)
            pontos.append((t.exit_price - t.entry_price) if t.side == "long"
                          else (t.entry_price - t.exit_price))
        pnls.extend(do_dia)
        caixa_por_pregao.append(sum(do_dia))
        com_op += 1 if do_dia else 0
    else:
        morreu = caixa < MARGEM_WDO_BRL

    r = _metricas(pnls, pontos, caixa_por_pregao)
    r.morreu = morreu
    r.pregoes_vividos = vividos
    r.pregoes_oferecidos = len(dias)
    r.caixa_final = caixa
    r.caixa_minimo = minimo
    r.dd_relativo = dd_rel
    r.dd_absoluto = dd_abs
    r.pregoes_com_op = com_op
    r.fitness = _fitness(r)
    return r


def _metricas(pnls: list[float], pontos: list[float],
              caixa_por_pregao: list[float]) -> Resultado:
    n = len(pnls)
    liquido = sum(pnls)
    ganhos = [p for p in pnls if p > 0]
    perdas = [-p for p in pnls if p < 0]
    ganho_medio = sum(ganhos) / len(ganhos) if ganhos else 0.0
    perda_media = sum(perdas) / len(perdas) if perdas else 0.0
    # Breakeven EMPIRICO, nao o nominal `stop/(alvo+stop)`: quando o payoff
    # realizado foge do nominal (e num robo com corte de relogio ele SEMPRE
    # foge), este e' o nulo certo. Itens 6.22/6.23 de LICOES_DE_PRODUCAO.
    denom = ganho_medio + perda_media
    breakeven = (perda_media / denom) if denom > 0 else 0.0
    if n > 1:
        media = liquido / n
        desvio = math.sqrt(sum((p - media) ** 2 for p in pnls) / (n - 1))
    else:
        desvio = 0.0
    return Resultado(
        n_trades=n, liquido=liquido,
        r_por_op=liquido / n if n else 0.0,
        win_pct=100.0 * len(ganhos) / n if n else 0.0,
        breakeven_emp=100.0 * breakeven,
        r_por_pregao=(liquido / len(caixa_por_pregao)
                      if caixa_por_pregao else 0.0),
        desvio_op=desvio, pnls=pnls, pontos=pontos,
        caixa_por_pregao=caixa_por_pregao,
    )


def resumo_pontos(r: Resultado) -> dict:
    """Distribuicao do resultado em PONTOS -- a checagem da ordem dos 3
    pontos (dono, 2026-09-18).

    Existe porque a regra dos 3 pontos e' facil de respeitar na GEOMETRIA
    pedida e ainda assim ser violada no resultado REALIZADO: o corte do
    relogio, o achatamento de fim de pregao e um stop parcial fecham onde o
    mercado esta', nao onde a geometria mandou. Se a mediana do |resultado|
    de um individuo ficar abaixo de 3 pontos, ele esta' vivendo de movimentos
    do tamanho do proprio escorregao de preco -- que e' precisamente o que a
    regra proibe, independente de o alvo PEDIDO ter sido 8 ticks."""
    if not r.pontos:
        return {"mediana_abs_pts": 0.0, "frac_abaixo_3pt": 1.0}
    absolutos = [abs(p) for p in r.pontos]
    return {
        "mediana_abs_pts": median(absolutos),
        "frac_abaixo_3pt": sum(1 for a in absolutos if a < 3.0) / len(absolutos),
    }
