"""fee_capacity/hip_01 -- concentrar posicoes sobrevive melhor a corretagem
FIXA do mercado fracionario com capital pequeno?

Contexto que motivou a hipotese (medido 2026-08-21, ANTES deste arquivo)
-------------------------------------------------------------------------
A Rico cobra R$1,90 FIXO por ordem no mercado fracionario (lote padrao e
gratuito, mas exige >= 100 acoes -- inatingivel com R$100 de capital em
qualquer papel real). `liquid_dual10` (10 sleeves, 5 vagas) e
`sintese_02_iliquidez_grupo_risco_orcado`, os dois primeiros do ranking
oficial, foram re-rodados com capital real (R$100) e o `CostModel` corrigido
(ver `core/config.py::CostModel.fractional_fixed_fee`) -- capital final:

    liquid_dual10:                         R$605,74 -> R$10,58   (-98%)
    sintese_02_iliquidez_grupo_risco_orcado: R$1.250,54 -> R$1,25 (-99,9%)

Nao foi degradacao, foi espiral de morte: com R$100 divididos em 5-10
posicoes, cada fatia vira ~R$10-20; um round-trip fracionario custa R$3,80
fixo (compra + venda), ~19-38% da fatia SO de corretagem, antes de qualquer
sinal. Com 37-47 trades ao longo do periodo, isso composto destroi o capital.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
Se a corretagem fixa e o problema, e ela e por ORDEM (nao por posicao em
capital), concentrar o MESMO capital em MENOS posicoes simultaneas deveria
sobreviver melhor: a mesma R$1,90 fixa vira uma fracao MENOR de uma posicao
de R$50-100 do que de uma posicao de R$10-20. Nao deveria (e a aposta) mudar
o SINAL (mesmo universo por liquidez, mesmo momentum 12-1, mesma histerese de
`LiquidSleeves5`/`liquid_champion`) -- so o numero de sleeves simultaneos.

Risco declarado da aposta: concentrar tambem reduz diversificacao -- um
sleeve perdedor pesa mais no capital total. Se a hipotese estiver certa, o
preco disso deve aparecer no MaxDD/pior-12m, nao ser gratis.

O que este arquivo NAO decide: se `sleeve_count=1` (o teste mais extremo,
usado aqui como default) e o numero certo para operar de verdade -- e so o
ponto mais claro da curva pra medir a direcao do efeito. Valores
intermediarios (2, 3) sao testados via instanciacao direta de
`LiquidSleeves5(sleeve_count=N)` no script de comparacao, sem precisar de
uma classe nova para cada N.

PROMOVIDO ao ranking automatico (2026-08-21) apos holdout de 48 janelas
(2010-01..2013-12) medido no regime R$100+taxa fixa real: liquid_focus bateu
IBOV em 48/48, 34/48 recuperaram o pico anterior de DD antes do fim da
janela, 0/48 pioraram depois do fundo, 10/10 das piores janelas por DD
terminaram com capital final > R$100 -- falhou os portoes G2 (DD>-45%) e G5
(12m>-35%) formalmente, mas esses portoes foram calibrados para perda
PERMANENTE de capital, nao para o padrao medido aqui (DD profundo e
transitorio). Decisao do dono do capital (nao minha) apos ver os dados.

RESSALVA DECLARADA -- o ranking automatico (`scheduler.py`) roda a
R$1.000/`CostModel` padrao (sem a taxa fixa fracionaria), regime EM QUE
liquid_focus nunca foi medido: a vantagem de concentrar (sobreviver a taxa
FIXA por ordem) nao existe nesse capital/custo. Decisao explicita do dono do
capital foi promover mesmo assim, aceitando que a posicao dele no pódio
geral (R$1.000/sem taxa) pode nao refletir o mesmo desempenho do regime em
que foi provado (R$100/com taxa) -- ver `strategy/discovery.py` para o
registro dessa decisao.

DESPROMOVIDO em 2026-08-21 -- substituido por `liqflop` (ex-`liquid_focus_loss_pause`)
--------------------------------------------------------------------------
`candidate = False` de volta. Nao foi refutado -- `hip_03_pausa_apos_perdas.py`
(mesma entrada, so acrescenta pausa apos 2 saidas negativas seguidas) mediu
MELHOR nas 48 janelas do holdout E no FULL, e o dono do capital escolheu
reduzir o podio a esse UM robo so, entre os quatro que disputavam antes
(`liquid_dual10`, `sintese_02_iliquidez_grupo_risco_orcado`, este e o
loss_pause). Continua resolvivel por chave, nao apagado.
"""
from __future__ import annotations

from strategy.liquid_sleeves5 import LiquidSleeves5


class LiquidFocus(LiquidSleeves5):
    """`LiquidSleeves5` com poucas posicoes simultaneas (default: 1) -- mesmo
    universo/sinal/histerese, só concentracao diferente. Ver docstring do
    módulo para a hipótese e o contexto que a motivou."""

    name = "liquid_focus"
    version = "1.0"
    candidate = False  # despromovido 2026-08-21 -- ver docstring do modulo

    # Ficha: o que muda e so a CONCENTRACAO (ver `Strategy` em base.py).
    sizing_rules = (
        "Uma posição por vez: os 100% do caixa livre vão para o único sleeve. "
        "Concentrar não é agressividade — é o que faz a corretagem FIXA de R$1,90 por "
        "ordem virar fração pequena da posição em vez de 19-38% dela.",
        "O preço disso está declarado: um papel perdedor pesa o capital inteiro. "
        "A conta aparece no MaxDD, não é de graça.",
    ) + LiquidSleeves5.sizing_rules[2:]

    def __init__(self, sleeve_count: int = 1, **kwargs):
        super().__init__(sleeve_count=sleeve_count, **kwargs)
