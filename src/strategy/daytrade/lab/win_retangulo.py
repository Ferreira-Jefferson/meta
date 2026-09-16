"""`win_retangulo` — opera a LATERALIZAÇÃO do mini-índice a partir da definição
visual do dono: o retângulo.

## O que é um retângulo, na definição que originou este robô

Palavras do dono (2026-09-15): *"o preço, por vários minutos ou barras, vai a
um ponto x e volta para próximo do ponto de origem, depois retorna para
próximo do ponto x e volta novamente para perto do ponto de origem, podendo
ficar um pouco abaixo e/ou um pouco acima. O que dá para notar é um desenho
retangular que se forma. Quando passa o meio deste desenho e depois volta
passando o meio novamente no sentido contrário, é uma lateralização."*

`detecta_retangulo` é a tradução literal dessa frase, e cada critério dela
existe porque uma versão mais frouxa foi medida e fracassou:

| critério | o que traduz | o que custou não ter |
|---|---|---|
| ≥2 VISITAS por borda | "vai ao x, VOLTA, RETORNA ao x" | contar BARRAS confundia "visitou 3 vezes" com "ficou 14 min encostado" |
| espalhamento ≥ W/3 | as visitas separadas no tempo | 3 toques em 3 barras seguidas passavam como retângulo |
| ≥3 cruzamentos do meio | "passa o meio e volta passando o meio" | é o único critério que o dono enunciou explicitamente |
| contenção ≥95% com banda q90/q10 | o desenho CONTÉM o preço | com q95/q05 a contenção dava ≥90% por construção — não era teste |
| CONTRAÇÃO ≤55% | o retângulo é ESTREITO perto do que veio antes | sem isto, "retângulo" é qualquer pedaço de mercado visto de perto |
| deriva ≤25% | as linhas são HORIZONTAIS | canal inclinado não é retângulo |

A primeira versão do detector, sem contração e com tolerância 0,15, achava
**8.830 retângulos (15 por pregão), com banda mediana de 598 pontos**. Não
era um detector, era uma janela deslizante. A versão que ficou acha ~5 por
pregão em W=30 e ~6,7 em W=20.

## A geometria, e por que ela é o oposto do que parecia óbvio

O desenho que o dono descreveu primeiro era *"posiciono a ordem no centro e
coloco o alvo a 90% da média do centro ao piso"*. Medido como especificado:
**14 de 15 células negativas**, com o acerto caindo EM CIMA do breakeven
empírico em toda a grade — jogo justo, não estratégia.

A matriz de trajetória (registrar o caminho uma vez, avaliar toda geometria
offline) mostrou por quê: **o alvo tinha de ser MAIOR, não menor**. Alvo de
0,80 × a largura contado do meio — ou seja, 0,30 × a largura ALÉM da borda
oposta — com o stop na borda de trás. O que paga não é a viagem até a borda:
é a viagem que ATRAVESSA a borda.

Risco 0,50 · retorno 0,80 ⇒ breakeven nominal de 38,5%. Acerto medido: 44,9%
no IS e 45,8% no OOS, contra breakeven empírico de 39,7% e 38,5%.

## O resultado medido, e o que ele NÃO é

Janelas congeladas (corte 2026-06-13), 1 contrato, custo de ida-e-volta de
7,5 pontos (1,5 tick) já descontado, com os defaults desta classe:

| | IS (129 pregões) | OOS (64 pregões) |
|---|---|---|
| líquido | R$ 3.720,70 | R$ 1.464,50 |
| operações | 615 | 179 |
| acerto | 44,9% | 45,8% |
| breakeven empírico | 39,7% | 38,5% |
| IC95 do acerto | [41,0 ; 48,8] | [38,7 ; 53,1] |
| pontos por operação | 30,2 | 40,9 |
| MaxDD | R$ 1.042,10 | R$ 384,50 |
| lucro/DD | 3,57 | 3,81 |
| pior operação | −R$ 80,50 | −R$ 74,30 |
| pregões sem operar | 10/129 | 11/64 |

Esta tabela é com `escala_por_caixa=False` (1 contrato fixo) — é a geometria
sobre a qual o veredito estatístico (acerto, IC95, breakeven) foi construído
e continua valendo como está. Com a escala LIGADA (default desde
2026-09-15), as mesmas 615/179 operações e o mesmo acerto se repetem — a
quantidade não muda qual retângulo é aceito —, mas os valores em R$ sobem
conforme o caixa cresce dentro da janela, e o pior rebaixamento por operação
sobe de R$989,50 para R$1.979,00 no IS. Ver `capital_minimo_recomendado_brl`
para o piso corrigido.

Para comparar: com `tolerancia_borda=0.08` (o primeiro congelado) e sem teto
de risco, os mesmos números eram R$2.980,10 / 403 operações / 33 pregões
parados no IS e R$737,70 / 101 / 23 no OOS.

É o primeiro desenho deste projeto a atravessar o OOS mantendo acerto E
magnitude. **Não é validação.** Quatro limites, declarados:

0. **O "POSITIVO" do OOS tem margem de 0,2 ponto percentual** (IC95 inferior
   38,7% contra breakeven 38,5%) e vem de uma configuração cujos DOIS
   parâmetros não-estruturais — `tolerancia_borda` e `risco_maximo_brl` —
   foram avaliados olhando essa mesma janela. Ele não é teste cego; é o
   melhor número disponível sobre o dado que existe.

1. **O retângulo não é o que gera o lucro bruto.** Um placebo com a banda
   q90/q10 CRUA (sem nenhum critério de forma) rendeu **+R$1.306,70 no OOS
   contra +R$737,70** deste desenho, operando 3,7× mais. Por OPERAÇÃO o
   detector paga nas duas janelas (35,16 contra −12,29 no IS; 36,52 contra
   17,52 no OOS) e tem 1/3 do rebaixamento — o que ele compra é QUALIDADE e
   ESTABILIDADE DE SINAL (o placebo inverte entre as janelas, este não),
   não volume de lucro.
2. **Estatisticamente é "indefinido".** Com 101 operações no OOS o IC95 do
   acerto (36,2% a 55,2%) engloba o breakeven. 62 pregões dão para checar
   inversão de sinal, não para cravar.
3. **NUNCA operou com dinheiro real.** Em sombra desde 2026-09-15 (slot
   `dt-win_retangulo-win@-shadow`), e a sombra não fecha o buraco da fila:
   ela não manda ordem, então enche no toque igual ao backtest.
4. **A tabela do topo vale para quem começa no piso de R$1.100**, que é
   onde a escada de `_dimensiona` roda 1 contrato. Com caixa maior o robô
   escala e os R$ mudam — as OPERAÇÕES não: em todas as janelas medidas o
   número de trades e o acerto ficam idênticos (615/44,9% no IS, 182/45,1%
   no OOS, 79/46,8% no último mês), porque a quantidade não interfere em
   qual retângulo é aceito.

## Fila: por que este desenho aguenta o que o WDO F1 maker não aguentou

WIN@ não tem fidelidade de execução calibrada (`backtest.intraday.fidelidade`
só tem WDO@), então o motor assume **fila ZERO nos dois lados**. Medida a
SENSIBILIDADE (não é calibração): o desenho aguenta até **50.000 contratos na
frente — 2 barras M1 medianas do WIN@** — e só morre em 100.000. Transplantar
a fração medida no WDO@ (15,0% / 16,7% de uma barra ⇒ ~3.733/~4.167 aqui) dá
degradação **ZERO**.

O motivo é estrutural e vale guardar: a entrada é uma limite na **linha do
meio**, nível que o preço cruza várias vezes e onde ele demora — o volume
acumulado naquele preço é enorme. O WDO F1 morria de fila porque o alvo de 2
ticks é o nível mais disputado do livro. **Nível que o preço visita muito é
nível barato de fila.**

## Execução — o desenho fechado, sem exceção

Entrada só por `EnterLimit` com prazo; alvo só como ordem-limite real
fatiada; **só o stop é a mercado**. Limite de venda só descansa ACIMA do
preço, de compra só ABAIXO — e há conferência mecânica disso antes de armar,
porque uma limite do lado errado é ordem a mercado disfarçada.

## Nada de nível de preço atravessa o pregão

`WIN@` é série contínua com emenda de rolagem, e o salto dela (+742, +786,
+630, +510 pontos nos 4 dias medidos) se esconde DENTRO do ruído overnight
normal — é indetectável por outlier. A única defesa estrutural é nunca deixar
um nível de preço cruzar a sessão, e `on_session_start` zera tudo.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    contracts_from_capital_operacional, no_tick,
)

#: Caixa exigido para o PRIMEIRO contrato: pior rebaixamento POR OPERAÇÃO
#: medido no IS com 1 contrato (R$989,50) + margem crua do WIN@ (R$100),
#: arredondado. É a base da escada de `_dimensiona` — o contrato `n` exige
#: `PISO_UM_CONTRATO_BRL × n^expoente`.
PISO_UM_CONTRATO_BRL = 1_100.0

#: Tolerância das bordas, em fração da largura — "podendo ficar um pouco
#: abaixo e/ou um pouco acima". É só o FALLBACK da função pura, para quem a
#: chama sem escolher; o robô passa o valor DELE
#: (`WinRetangulo.tolerancia_borda`, hoje 0,20). São dois números com dois
#: empregos: aqui fica o valor histórico da primeira medição (0,08), que
#: mantém reprodutível todo o material antigo desta linha; lá fica o valor
#: que o robô opera, medido depois. Igualá-los à força faria os números
#: antigos deixarem de bater sem que ninguém percebesse.
TOLERANCIA_BORDA = 0.08
#: Toques mínimos por borda, antes de colapsar em visitas.
TOQUES_MINIMOS = 2
#: VISITAS por borda — barras consecutivas encostadas colapsam em uma só.
#: É o critério fiel à definição ("vai ao x, VOLTA, RETORNA ao x") e é o
#: parâmetro que de fato governa a forma.
VISITAS_MINIMAS = 2
#: "Passa o meio e depois volta passando o meio no sentido contrário."
CRUZAMENTOS_MINIMOS = 3
#: Fração dos fechamentos que tem de estar DENTRO da banda.
CONTENCAO_MINIMA = 0.95
#: O retângulo tem de ser estreito perto do movimento que veio antes dele:
#: largura ≤ 55% da amplitude das 2W barras anteriores.
CONTRACAO_MAXIMA = 0.55
#: Primeiro e último toque de cada borda separados por ≥ W/3 barras.
ESPALHAMENTO_MINIMO = 1 / 3
#: Inclinação máxima: deriva do primeiro ao último terço, em fração da largura.
DERIVA_MAXIMA = 0.25
#: Um retângulo mais estreito que isto não paga o pedágio de 1,5 tick.
LARGURA_MINIMA_TICKS = 6.0
#: Morte do retângulo: N fechamentos CONSECUTIVOS além de M×largura da borda.
#: Matar no primeiro fechamento fora (o critério ingênuo) dava vida mediana de
#: 5 minutos — a "vida" virava artefato do critério, não medida do mercado.
MARGEM_MORTE = 0.25
BARRAS_MORTE = 3


def detecta_retangulo(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    amplitude_anterior: float | None = None,
    tolerancia: float = TOLERANCIA_BORDA,
) -> dict | None:
    """O retângulo desta janela, ou `None` se ela não qualifica.

    Pura: arrays de OHLC entram, dicionário sai. Nenhuma I/O, nenhum estado —
    é o que permite portar para MQL5 (regra 1 do `AGENTS.md`).

    `amplitude_anterior` é a amplitude das 2W barras ANTERIORES à janela e
    serve só ao teste de CONTRAÇÃO. `None` (começo do pregão, sem histórico
    suficiente) pula o teste — e isso fica marcado em `contracao` como NaN,
    nunca escondido atrás de um default que faria o critério passar calado.
    """
    topo = float(np.quantile(high, 0.90))
    piso = float(np.quantile(low, 0.10))
    largura = topo - piso
    if largura <= 0:
        return None
    meio = (topo + piso) / 2.0
    zona = tolerancia * largura

    lados: list[int] = []
    pos_topo: list[int] = []
    pos_piso: list[int] = []
    for i, (h, lo) in enumerate(zip(high, low)):
        if h >= topo - zona:
            lados.append(1)
            pos_topo.append(i)
        elif lo <= piso + zona:
            lados.append(-1)
            pos_piso.append(i)
    if len(pos_topo) < TOQUES_MINIMOS or len(pos_piso) < TOQUES_MINIMOS:
        return None

    def _visitas(pos: list[int]) -> int:
        return 1 + sum(1 for a, b in zip(pos, pos[1:]) if b - a > 1)

    visitas_topo, visitas_piso = _visitas(pos_topo), _visitas(pos_piso)
    if visitas_topo < VISITAS_MINIMAS or visitas_piso < VISITAS_MINIMAS:
        return None

    minimo = ESPALHAMENTO_MINIMO * len(close)
    if (pos_topo[-1] - pos_topo[0]) < minimo or (pos_piso[-1] - pos_piso[0]) < minimo:
        return None

    trocas = sum(1 for a, b in zip(lados, lados[1:]) if a != b)
    if trocas < 2:
        return None

    acima = close > meio
    cruzamentos = int(np.sum(acima[1:] != acima[:-1]))
    if cruzamentos < CRUZAMENTOS_MINIMOS:
        return None

    contencao = float(np.mean((close >= piso) & (close <= topo)))
    if contencao < CONTENCAO_MINIMA:
        return None

    n = len(close)
    primeiro = float(np.mean(close[: n // 3]))
    ultimo = float(np.mean(close[-(n // 3):]))
    if abs(ultimo - primeiro) > DERIVA_MAXIMA * largura:
        return None

    contracao = float("nan")
    if amplitude_anterior is not None and amplitude_anterior > 0:
        contracao = largura / amplitude_anterior
        if contracao > CONTRACAO_MAXIMA:
            return None

    return dict(
        topo=topo, piso=piso, largura=largura, meio=meio, contracao=contracao,
        visitas_topo=visitas_topo, visitas_piso=visitas_piso,
        toques_topo=len(pos_topo), toques_piso=len(pos_piso), trocas=trocas,
        cruzamentos=cruzamentos, contencao=contencao,
        deriva_frac=abs(ultimo - primeiro) / largura,
    )


class WinRetangulo(IntradayStrategy):
    """Entra por ordem-limite no MEIO de um retângulo largo, mirando ALÉM da
    borda oposta."""

    name = "win_retangulo"
    version = "1.0.0"
    symbol = "WIN@"
    is_futuro = True
    #: O alvo é ordem-limite REAL parada no livro (nunca `tp` nativo, que a
    #: corretora varre a mercado: R$55,00 de deslize contra R$95,00 de bruto
    #: teórico, n=11, 10 contra 0 a favor).
    target_fills_as_maker = True
    #: A entrada é limite, então a âncora de saída no preço realmente obtido
    #: vale de verdade aqui (em robô que entra a mercado ela é no-op silencioso
    #: — item 4.23 de `LICOES_DE_PRODUCAO.md`).
    anchor_exits_at_fill = True
    feed_kind = "m1"

    #: PISO DE PARTIDA, medido — não é o piso de tabela do WIN@ (R$250).
    #:
    #: A escada de capital (`scripts/daytrade/copawin_retangulo_escada_
    #: capital_2026_09_15.py`) achou um PENHASCO entre R$275 e R$290: a
    #: R$275 o robô toma duas perdas seguidas (R$104,50 + R$85,50), o caixa
    #: cai para R$85, fica abaixo da margem crua de R$100 e ele **cala para
    #: sempre** — 128 dos 129 pregões do IS em branco. A R$290 ele roda as
    #: 403 operações inteiras.
    #:
    #: R$290 é o piso EXATO daquela sequência de operações, e por isso nunca
    #: foi o número adotado: um piso medido em cima do penhasco é sorteio
    #: sobre quais operações vieram primeiro, não margem. O número que
    #: aguenta COMEÇAR EM QUALQUER PONTO da série é o pior rebaixamento mais
    #: a margem.
    #:
    #: **R$650 foi a primeira resposta e estava baixa por DOIS motivos, os
    #: dois corrigidos aqui (2026-09-15):**
    #:
    #: 1. Ela usou o rebaixamento da SÉRIE DIÁRIA (R$525,60), que soma o
    #:    pregão antes de acumular e portanto suaviza o que acontece dentro
    #:    do dia. O portão de capital não vê a série diária: o caixa é
    #:    creditado e debitado POR OPERAÇÃO, e por operação o mesmo desenho
    #:    rebaixava R$640,60 — piso real de R$740,60, não R$650.
    #: 2. `tolerancia_borda` subiu de 0,08 para 0,20, e mais operações
    #:    trazem mais rebaixamento junto: **R$989,50 por operação no IS**.
    #:
    #: Daí **R$1.100** (R$989,50 + R$100, arredondado). É o preço honesto da
    #: melhora — quem não tiver esse caixa não deve "baixar o piso": baixar o
    #: piso não torna a estratégia mais segura, só move a quebra para dentro
    #: da conta.
    #:
    #: A escada de capital mostra que **R$400 já roda 100% das operações nas
    #: duas janelas medidas** (e R$250 fica censurada, 125/129 pregões
    #: parados). Não adote R$400: esse é o número de quem começa no dia 1 da
    #: série medida, que é exatamente o sorteio que o parágrafo acima recusa.
    #:
    #: Contexto do risco: o stop é 0,50 × a largura do retângulo, então NÃO é
    #: fixo: pior operação medida −R$110,50 no IS e −R$85,50 no OOS, ou seja
    #: até 10% do caixa de partida numa operação só. `risco_maximo_brl`
    #: existe para cortar essa cauda — ver a docstring dele para as três
    #: medições que tiraram o teto do lugar de alavanca.
    #:
    #: **SUBIU de R$1.100 para R$2.100 em 2026-09-16 — o piso tinha ficado
    #: ÓRFÃO.** `PISO_UM_CONTRATO_BRL = R$1.100` continua correto como base
    #: da ESCADA (é o caixa que compra o 1º contrato; o 2º só aparece em
    #: R$2.933, o 3º em R$5.206) — o que estava errado era usar essa MESMA
    #: constante como piso de SEGURANÇA. As duas perguntas parecem a mesma e
    #: não são: uma é "quanto compra 1 contrato", a outra é "quanto aguenta
    #: o pior rebaixamento".
    #:
    #: R$1.100 respondia a segunda pergunta quando foi medido — mas a
    #: medição (R$989,50 de rebaixamento por operação) rodou com
    #: `quantidade=1` FIXA, ANTES de a escala pelo caixa virar default
    #: (commits `4806636`/`ca252a7`, 2026-09-15 21:40). Rodando hoje o robô
    #: de produção sem nenhuma modificação, na MESMA janela e MESMO capital
    #: de partida: o caixa cresce com o lucro acumulado dentro do próprio
    #: IS, ultrapassa R$2.933 no meio da série, e um rebaixamento chega a
    #: acontecer já com 2 contratos — **R$1.979,00 por operação**, quase o
    #: dobro do número que sustentava R$1.100. Ver item 6.43 de
    #: `LICOES_DE_PRODUCAO.md`.
    #:
    #: Daí **R$2.100** (R$1.979,00 + R$100 de margem crua, arredondado). No
    #: OOS a escada nunca escala além de 1 contrato, então lá o rebaixamento
    #: continua R$373,50 — é o IS, com mais pregões para o caixa crescer,
    #: quem decide o piso.
    #:
    #: A REGRA que fica, e que generaliza além deste robô: **todo piso de
    #: capital publicado descreve uma VERSÃO do robô com um mecanismo de
    #: dimensionamento específico.** Mudar o dimensionamento sem remedir o
    #: piso é a mesma classe de erro que rodar backtest com capital
    #: arbitrário — só que mais traiçoeira, porque o número antigo continua
    #: parecendo medido.
    #:
    #: Uma tentativa anterior de escala (2026-09-15, descartada no mesmo dia)
    #: amarrava a quantidade à LARGURA do retângulo em vez do caixa. Ela
    #: alavancava sem exigir caixa: o líquido quase dobrava nas três janelas
    #: (IS 3.720,70 → 7.266,20) com o acerto PARADO e as mesmas operações,
    #: ou seja, era a mesma estratégia em tamanho maior — e o piso saltava
    #: para R$3.400. Ficou registrada aqui porque o número bonito dela pode
    #: reaparecer numa medição futura e precisa ser reconhecido pelo que era.
    capital_minimo_recomendado_brl: float | None = 2_100.0

    def __init__(
        self,
        symbol: str | None = None,
        janela_barras: int = 20,
        largura_minima_pontos: float = 328.0,
        alvo_fracao_largura: float = 0.80,
        stop_fracao_largura: float = 0.50,
        ttl_barras: int = 10,
        quantidade: int = 1,
        tolerancia_borda: float = 0.20,
        risco_maximo_brl: float = 80.0,
        escala_por_caixa: bool = True,
        caixa_primeiro_contrato_brl: float | None = None,
        expoente_escala: float = 1.415,
    ) -> None:
        """Todos os defaults são os valores CONGELADOS na passada do OOS.

        `janela_barras=20` — escolha do dono. A medição de detecção precoce
        (só IS) comparou W10 a W25 contra o nulo de "o mercado lateraliza o
        tempo todo": W10 dá ganho de 1,04× (relógio parado), W20 dá **1,78×
        com 8 barras de antecedência**, W25 dá 2,25× mas só 4 barras. W20 é o
        ponto onde ainda sobra vida útil do retângulo para operar — a
        identificação custa ≈W barras, e no W30 ela come 2/3 da vida do
        padrão (35 min de 61).

        `largura_minima_pontos=328` — o terço SUPERIOR da largura dos
        retângulos W=20 medido NO IS. Não é o número do W=30 (401 pontos):
        janela menor produz retângulo naturalmente mais estreito, e
        reaproveitar o corte selecionaria outra fatia da distribuição. É o
        único filtro que manteve sinal E magnitude nas duas janelas.

        `alvo_fracao_largura=0.80` / `stop_fracao_largura=0.50` — a grade de
        7×6 células é um **PLATÔ, não um pico**: 39 de 42 positivas no IS, 40
        no OOS, 39 nas DUAS. O eixo do ALVO concorda entre janelas (maior é
        melhor até ~0,8-1,0 × largura); o eixo do STOP discorda (IS prefere
        0,375-0,50, OOS prefere 0,25) mas todo valor testado é positivo — o
        stop é ruído dentro do platô, não parâmetro a garimpar. Por isso o
        par default é o congelado, e não o ótimo de nenhuma das duas janelas.

        `quantidade=1` fixo: dimensionamento NUNCA foi medido nesta linha, e
        o risco por operação varia de R$32 a R$110. Ligar escala aqui sem
        medir repetiria o incidente de 2026-08-28.

        `tolerancia_borda=0.20` — a zona que conta como "toque" na borda, em
        fração da largura. NÃO é afrouxamento arbitrário: o ruído das bordas
        foi MEDIDO e vale 10-17% da largura (p90 em +131/+165 pontos), ou
        seja, uma tolerância de 8% era mais apertada que o que o mercado de
        fato faz numa borda de retângulo. Varrida de 8% a 35% no IS, a
        superfície é um PLATÔ: toda célula de 10% para cima bate o 8%, e o
        8% fica na BORDA da região útil. 20% é o meio do platô — o máximo do
        IS estava em 30% (R$4.910,90) e foi deliberadamente NÃO escolhido.
        Nenhum critério estrutural muda junto: visitas, cruzamentos,
        contenção, contração, deriva e espalhamento seguem nos valores
        originais. Afrouxar `deriva`/`contenção` JUNTO com tolerância ≥25%
        foi medido e colapsa (94-124 de 129 pregões sem operar) — é penhasco,
        não platô.

        `risco_maximo_brl=80.0` — teto de risco projetado por operação
        (`stop_fracao_largura × largura × R$0,20/ponto × quantidade`).

        **Está LIGADO para limitar a CAUDA, e explicitamente NÃO por
        resultado** (decisão do dono, 2026-09-15, tomada depois de ver as
        duas leituras lado a lado). O que ele entrega de forma consistente é
        uma coisa só, e essa replica nas três janelas medidas:

            janela              pior operação SEM → COM
            IS (129 pregões)      −110,50  →  −80,50
            OOS (64 pregões)       −85,50  →  −74,30
            2 semanas (9 preg.)    −85,50  →  −72,50

        Com caixa de partida de R$1.100, é a pior operação saindo de 10,0%
        para 7,3% da conta.

        **O ganho em R$ NÃO é o motivo, e três medições explicam por quê:**

        1. **O eixo não tem estrutura.** No IS, R$80 é o PIOR valor da
           vizinhança R$70-120 (R$3.720,70 contra R$4.460,70 em R$70 e
           R$4.482,20 em R$100); no OOS é um pico de uma célula só — os
           vizinhos R$90, R$100 e R$120 empatam exatamente em R$905,50.
           Mesma célula, direções opostas nas duas janelas.
        2. **O pico do OOS são DUAS operações.** O teto de R$80 rejeita 2 dos
           133 retângulos daquela janela, e essas 2 rejeições valem os R$367
           de diferença. R$90 rejeita ZERO; R$70 rejeita 13. Não é filtro bom
           nem embaralhamento — 97% a 100% das operações são idênticas com e
           sem teto; muda um punhado, e o punhado decidiu o número.
        3. **A largura prevê o resultado, e na direção CONTRÁRIA ao teto.**
           Medido numa rodada sem teto, casando cada operação com a largura
           do retângulo que a gerou, o retorno POR REAL ARRISCADO cresce com
           a largura nas duas janelas:

               faixa (pontos)   R$ por R$ de risco, IS   OOS
               328-400                    0,055          0,051
               400-470                    0,248          0,086
               470-550                   −0,024          0,212
               550-650                    0,206          0,348
               650-800                    0,429          (n=2)

           Correlação de posto largura × retorno/risco: **+0,338 no IS e
           +0,306 no OOS**. Um teto de largura corta exatamente as operações
           que melhor pagam pelo risco que tomam — e isso é coerente com o
           achado mais antigo desta linha, que o PISO de largura (328) é o
           único filtro que sobreviveu às duas janelas.

        Tetos RELATIVOS foram testados pelo mesmo motivo (a pergunta certa
        era "existe teto deduzível do dado prévio?"). `largura ≤ k × amplitude
        do pregão até agora` é a única regra cuja ordem de células replica
        (correlação de posto IS×OOS = 0,86) — e o que ela replica é que
        **apertar destrói**: o melhor `k` é o que quase não corta (0,40, que
        rejeita 6%). O quantil rolante das larguras já vistas é pior que
        nada (correlação de posto = −0,30).

        O efeito em R$ **inverte entre as janelas**: no IS o teto custa
        R$792,00 movendo 32 das 615 operações; no OOS ele ganha R$367,00
        movendo **4 das 179**. E atenção a uma armadilha de contagem: a
        janela de "duas semanas" que também o favorece está INTEIRA dentro
        do OOS — são as mesmas operações contadas duas vezes, não duas
        confirmações independentes. A única janela independente é o IS, e
        nela o teto perde.

        Ele também **não reduz o rebaixamento** (R$989,50 no IS com ou sem),
        então o piso de caixa de R$1.100 não muda por causa dele.

        `inf` desliga. Mexer neste número por líquido é garimpo: o eixo não
        tem estrutura, como a tabela acima mostra.
        """
        if janela_barras < 6:
            raise ValueError(
                f"janela_barras={janela_barras} é curto demais para um retângulo: "
                f"o espalhamento exige W/3 barras entre a primeira e a última "
                f"visita de cada borda"
            )
        if alvo_fracao_largura <= 0 or stop_fracao_largura <= 0:
            raise ValueError("alvo e stop têm de ser distâncias positivas")
        if ttl_barras is None or ttl_barras <= 0:
            # Ordem-limite de entrada SEM prazo espera até o fim do pregão e
            # preenche horas depois do sinal — medido um fill 269,7 minutos
            # depois do gatilho, e os fills atrasados foram os piores
            # resultados. Não é o trade que a estratégia pediu.
            raise ValueError("ttl_barras é obrigatório: limite de entrada sem prazo "
                             "vira ordem esquecida no livro")
        if symbol is not None:
            self.symbol = symbol
        self.janela_barras = int(janela_barras)
        self.largura_minima_pontos = float(largura_minima_pontos)
        self.alvo_fracao_largura = float(alvo_fracao_largura)
        self.stop_fracao_largura = float(stop_fracao_largura)
        self.ttl_barras = int(ttl_barras)
        if not 0 < tolerancia_borda < 0.5:
            raise ValueError(
                f"tolerancia_borda={tolerancia_borda} fora de (0; 0,5): acima de "
                f"0,5 as duas bordas se encontram no meio e todo preço 'toca' as duas"
            )
        if risco_maximo_brl <= 0:
            raise ValueError("risco_maximo_brl tem de ser positivo (use inf para desligar)")
        self.quantidade = int(quantidade)
        self.tolerancia_borda = float(tolerancia_borda)
        self.risco_maximo_brl = float(risco_maximo_brl)
        self.escala_por_caixa = bool(escala_por_caixa)
        if expoente_escala <= 1.0:
            raise ValueError(
                f"expoente_escala={expoente_escala} tem de ser > 1: em 1,0 o "
                "caixa por contrato fica CONSTANTE e o risco em % da conta "
                "para de cair quando a posicao cresce")
        self.expoente_escala = float(expoente_escala)
        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size
        self.valor_do_ponto_brl = economia.point_value_brl
        self.margem_por_contrato_brl = economia.margin_per_contract_brl
        #: Quantidade PEDIDA na entrada. Com `escala_por_caixa` ela é
        #: recalculada a cada retângulo; sem ela fica em `quantidade` para
        #: sempre. O motor aplica o teto dele por cima
        #: (`IntradaySessionMachine._cap_capital_atual`), então este número
        #: nunca passa do que a margem sustenta mesmo se a conta aqui errar.
        self.caixa_primeiro_contrato_brl = float(
            caixa_primeiro_contrato_brl
            if caixa_primeiro_contrato_brl is not None
            else PISO_UM_CONTRATO_BRL)
        self._teto_margem = int(self.quantidade)
        self._caixa_brl = 0.0
        self._reset_sessao()

    # -- dimensionamento ---------------------------------------------------
    def on_capital_update(self, cash_brl: float) -> None:
        """O caixa corrente decide quantos contratos cabem — para CIMA e para
        BAIXO. Chamado pelo motor a cada barra com `capital inicial + P&L
        realizado`, então a quantidade acompanha a conta de verdade em vez de
        ser uma foto tirada uma vez no início."""
        super().on_capital_update(cash_brl)
        self._caixa_brl = float(cash_brl)
        if self.escala_por_caixa:
            self._teto_margem = max(1, contracts_from_capital_operacional(
                self._caixa_brl, self.margem_por_contrato_brl))

    def _dimensiona(self) -> int:
        """Quantos contratos o CAIXA sustenta agora, com cada contrato novo
        exigindo mais caixa que o anterior (regra do dono, 2026-09-15).

        `C(n) = caixa_primeiro_contrato_brl × n^expoente`, com expoente > 1.
        O expoente é o que faz o risco CAIR conforme a posição cresce: com
        expoente 1 o caixa por contrato seria constante (dobrar a posição
        dobraria o risco em reais e manteria o risco em % do caixa); acima de
        1 o caixa exigido por contrato sobe, então cada contrato adicional
        carrega uma fatia MENOR da conta.

        Calibração do expoente (palavras do dono): "se preciso de 3k para
        rodar 1 contrato no mínimo precisaria de 6k para 2, mas como a ideia é
        reduzir o risco conforme aumento contrato, 8k seria um bom capital
        para operar dois". 8/3 em vez de 6/3 ⇒ `2^expoente = 8/3` ⇒
        expoente ≈ 1,415.

        A escada que sai disso, com o piso medido de 1 contrato:

        | contratos | caixa exigido | caixa por contrato |
        |---|---|---|
        | 1 | R$ 1.100 | R$ 1.100 |
        | 2 | R$ 2.933 | R$ 1.467 |
        | 3 | R$ 5.243 | R$ 1.748 |
        | 4 | R$ 7.822 | R$ 1.955 |

        **Não é a escada de MARGEM, e a diferença é o ponto todo.** A margem
        (`contracts_from_capital_operacional`) autoriza 4 contratos já com
        R$1.100 — ela protege a CORRETORA de chamada de margem, não o dono de
        ruína por sequência de stops (item 3.9 de `LICOES_DE_PRODUCAO.md`: no
        `CopaWin` o teto por margem escalou a entrada de 12 para 15 contratos
        e o mesmo stop levou a conta de R$3.000,00 a R$68,50). A margem
        continua valendo como teto de cima; quem manda é esta escada.
        """
        if not self.escala_por_caixa:
            return int(self.quantidade)
        n = 1
        while True:
            exigido = self.caixa_primeiro_contrato_brl * (n + 1) ** self.expoente_escala
            if self._caixa_brl < exigido or n + 1 > self._teto_margem:
                return n
            n += 1

    # -- estado ------------------------------------------------------------
    def _reset_sessao(self) -> None:
        # 3×W barras: W para a janela do detector, 2W para a amplitude
        # anterior que o teste de CONTRAÇÃO consome.
        self._hist: deque[Bar] = deque(maxlen=3 * self.janela_barras + 2)
        self._retangulo: dict | None = None
        self._contratos = int(self.quantidade)
        self._fora_seguidas = 0
        self._barras_esperando: int | None = None

    def on_session_start(self, session_date) -> None:
        """Zera TUDO. Nenhum nível de preço atravessa a virada — ver a
        docstring do módulo sobre a emenda de rolagem do `WIN@`."""
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """A ordem morreu por teto/capital sem abrir posição. Sem isto o robô
        acharia para sempre que ainda tem ordem viva e travaria pelo resto da
        sessão (20/20 amostras no `WdoGridReloadMaker` antes do hook existir)."""
        self._barras_esperando = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        """A limite de entrada estourou o prazo e o motor já a cancelou. É o
        irmão de `on_order_rejected` e existe pelo mesmo motivo — item 4.25 de
        `LICOES_DE_PRODUCAO.md`: uma limite de entrada morre por CINCO
        caminhos, e o robô que só trata um deles trava nos outros quatro."""
        self._barras_esperando = None

    # -- detecção ----------------------------------------------------------
    def _janelas(self):
        W = self.janela_barras
        h = list(self._hist)
        recente = h[-W:]
        anterior = h[-3 * W:-W]
        return (
            np.array([b.high for b in recente], dtype=float),
            np.array([b.low for b in recente], dtype=float),
            np.array([b.close for b in recente], dtype=float),
            float(max(b.high for b in anterior) - min(b.low for b in anterior)),
        )

    def _tenta_detectar(self) -> None:
        if len(self._hist) < 3 * self.janela_barras:
            return
        high, low, close, amplitude_anterior = self._janelas()
        ret = detecta_retangulo(high, low, close, amplitude_anterior,
                                tolerancia=self.tolerancia_borda)
        if ret is None:
            return
        if ret["largura"] < LARGURA_MINIMA_TICKS * self.tick_size:
            return
        if ret["largura"] < self.largura_minima_pontos:
            return
        # TETO DE RISCO: o stop é proporcional à largura, então retângulo
        # largo demais põe dinheiro demais numa operação só. Recusa aqui (na
        # detecção) e não na hora de armar, porque o retângulo inteiro é
        # inoperável — deixá-lo vivo faria o robô tentar de novo a cada barra.
        risco = (self.stop_fracao_largura * ret["largura"]
                 * self.valor_do_ponto_brl)
        if risco > self.risco_maximo_brl:
            return
        self._retangulo = ret
        # Quantos contratos este retângulo comporta AGORA. Avaliado aqui (e não
        # na hora de armar) pelo mesmo motivo do teto: é propriedade do
        # retângulo mais o caixa, e os dois já são conhecidos.
        self._contratos = self._dimensiona()
        self._fora_seguidas = 0

    def _morreu(self, bar: Bar) -> bool:
        r = self._retangulo
        margem = MARGEM_MORTE * r["largura"]
        if bar.close > r["topo"] + margem or bar.close < r["piso"] - margem:
            self._fora_seguidas += 1
            return self._fora_seguidas >= BARRAS_MORTE
        self._fora_seguidas = 0
        return False

    # -- loop --------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)

        if self._retangulo is not None and self._morreu(bar):
            self._retangulo = None
            self._barras_esperando = None
        if self._retangulo is None:
            self._tenta_detectar()
            if self._retangulo is None:
                return []

        # Posição aberta: o motor cuida de stop e alvo. Este robô não gere
        # posição — 24 regras de gestão (trailing, zero-a-zero, corte por
        # tempo) foram medidas no `copa_win` e TODAS saíram negativas.
        if positions:
            self._barras_esperando = None
            return []

        # Ordem já parada no livro, dentro do prazo: não rearma por cima.
        if self._barras_esperando is not None:
            self._barras_esperando += 1
            if self._barras_esperando < self.ttl_barras:
                return []
            self._barras_esperando = None

        r = self._retangulo
        meio, largura = r["meio"], r["largura"]
        if bar.close < meio:
            lado = "short"
            alvo = meio - self.alvo_fracao_largura * largura
            stop = meio + self.stop_fracao_largura * largura
        elif bar.close > meio:
            lado = "long"
            alvo = meio + self.alvo_fracao_largura * largura
            stop = meio - self.stop_fracao_largura * largura
        else:
            # Fechou exatamente no meio: não há lado em que a limite descanse.
            return []

        # Conferência MECÂNICA, e não é redundante com o teste acima: depois
        # do arredondamento ao tick a limite pode cair em cima do preço. Uma
        # limite do lado errado é ordem a mercado disfarçada, que é o que o
        # desenho de execução deste projeto proíbe.
        limite = no_tick(meio, self.tick_size)
        if lado == "short" and limite <= bar.close:
            return []
        if lado == "long" and limite >= bar.close:
            return []

        self._barras_esperando = 0
        return [EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self._contratos,
            ttl_bars=self.ttl_barras,
            reason=f"retangulo_W{self.janela_barras}_L{largura:.0f}",
        )]
