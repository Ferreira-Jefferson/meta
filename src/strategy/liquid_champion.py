"""LiquidChampion — o robo que substitui `portfolio_dip2_hw40` como TOP-1.

Por que o campeao antigo foi aposentado
----------------------------------------
`portfolio_dip2_hw40` liderava o ranking por capital final, mas o capital dele
nao e reproduzivel: a watchlist de sete tickers em `core/config.py` foi escolhida
em 2026 maximizando o periodo 2010-2026. `scripts/run_walk_forward.py` refez a
mesma selecao usando so dado passado e o CAGR caiu de ~36% para 17,1% / -4,2% /
18,3%. `scripts/run_holdout_frozen.py` fechou o diagnostico: nas 48 janelas com
inicio em 2010-2013 — a parte MAIS contaminada da amostra, porque e onde a
selecao de 2026 mais sabia o que ia subir — ele marcou 57,4% de CAGR mediano com
6 trades. Isso mede o vies, nao o talento. Ele ficou com `candidate = False`.

Ele tambem opera papel ilikido: EMAE4 gira R$ 141 mil/dia e o robo satura o
proprio papel a partir de ~R$ 70 mil. O backtest nunca soube porque nao modela
impacto. Este robo tem capacidade de ~R$ 14 milhoes pelo mesmo criterio.

De onde vem cada peca
---------------------
| peca                              | como foi decidida                                    |
|-----------------------------------|------------------------------------------------------|
| universo por liquidez na data     | walk-forward — e a unica regra montavel no proprio dia |
| 5 sleeves disjuntos, 20% cada     | holdout 48 janelas: negativas 21/48 (IBOV) -> 3/48    |
| grandfathering (sem despejo)      | despejo forca venda por calendario, custa IR e corretagem |
| top-20 refeito a cada 12 meses    | holdout: 3/48 janelas negativas contra 8/48 da banda de rank |
| parametros de sinal CONGELADOS    | tunar no in-sample perdeu em 4 de 6 trilhas           |

Duas coisas foram testadas para este arquivo e REPROVADAS — estao registradas
porque saber o que nao entrou vale tanto quanto saber o que entrou:

  - **Reserva de lucro realizado** (`scripts/run_champion_calibration.py`).
    Guardar 2/5/10% de cada lucro num bolso que nao volta melhorou o MaxDD de
    forma monotona, mas custou ~2,5 p.p. de CAGR mediano: o Calmar caiu de 0,42
    para 0,36. Ela funcionou no campeao antigo, que tinha UMA posicao
    concentrada; aqui os cinco sleeves ja fazem esse trabalho, e os dois
    mecanismos sao substitutos, nao somam.
  - **Mais sleeves** (`scripts/run_champion_k.py` + `run_champion_k_control.py`).
    k=10 mostrou MaxDD -19,9% contra -36,7% de k=5 e parecia uma melhoria
    enorme. Nao era: a exposicao media cai de 72,7% para 40,3%, e uma mistura
    estatica de k=5 com Selic na MESMA exposicao bate o k=10 em CAGR, pior
    janela e pior 12m. O ganho era caixa parado, nao diversificacao. Entre k=3 e
    k=5 — que tem exposicao praticamente igual, 70,9% e 72,7% — a comparacao e
    limpa, e k=5 vence claramente no pior 12m (-17,9% contra -26,0%).

Consequencia pratica que vale mais que qualquer uma delas: **quem quiser menos
drawdown deve deixar parte do dinheiro fora do robo, nao pedir ao robo que fique
com medo.** Uma mistura de 55% neste robo e 45% em Selic entregou, nas cinco
janelas de ajuste, CAGR mediano 9,3% com MaxDD -24,5% e pior 12m -8,8%. Isso e
uma decisao de alocacao do operador, e por isso NAO esta embutida aqui.

O que se pode e o que nao se pode prometer
-------------------------------------------
O portao "nenhuma janela de cinco anos negativa" CAIU no holdout — era artefato
das cinco janelas de ajuste. A afirmacao honesta e menor: **IBOV mais ~4,7 p.p.
ao ano, com MaxDD cerca de 10 p.p. melhor que o indice, e ainda assim com chance
real de uma janela de cinco anos levemente negativa** (3 de 48 no holdout, contra
21 de 48 do indice). Ver `memory/holdout_frozen_2026_08_20.md`.

Vies que continua de pe: `POOL` sai de `data/raw/`, que so tem empresas vivas em
2026. Quem saiu da bolsa entre 2010 e hoje nao esta ali, e isso empurra todo
numero deste arquivo para cima.

Custo operacional que o backtest nao cobra: cinco sleeves querem cinco posicoes
simultaneas, e o lote minimo na Clear e de 100 acoes (~R$ 4.900 num papel de
R$ 49). Abaixo de ~R$ 25 mil de capital os sleeves nao cabem em lotes e o robo
opera distorcido. Ver `memory/mt5_terminal_clear_config.md`.

Por que a epoca de 12 meses e nao a banda de rank continua
-----------------------------------------------------------
Esta escolha foi feita DUAS vezes, e mudou de lado. O primeiro argumento foi de
parcimonia: a regra por epoca carrega dois parametros arbitrarios (a cadencia de
12 meses e a fase — as epocas comecam em janeiro porque o calendario e assim), e
a banda de rank nao carrega nenhum. Entre desenhos que a evidencia nao distingue,
fica o mais simples.

A evidencia passou a distinguir. Nas 48 janelas do holdout, que sao a unica
medicao cujos inicios nunca participaram de escolha nenhuma, a epoca de 12 meses
ganha em tres das cinco colunas: 3 janelas negativas contra 8, pior janela -0,7%
contra -2,1%, MaxDD -34,4% contra -36,7%. A banda ganha so no pior 12m (-25,8%
contra -29,7%) e a mediana empata. Depois, com o caixa remunerado na run oficial
de ranking, a janela FULL confirmou pelo mesmo lado: 10,05% de CAGR e MaxDD
-34,22% contra 9,19% e -36,51%.

Trocar por causa disso nao e o mesmo erro de ajustar cem configuracoes em cinco
janelas: sao dois desenhos que ja estavam congelados antes do holdout, julgados
uma vez, no criterio que foi declarado antes (pior janela primeiro). Um grau de
liberdade, nao cem.

O preco da troca esta medido e e real: `scripts/run_rebalance_day_sensitivity.py`
mostra que esta regra e MAIS sensivel ao dia do rebalanceamento (coeficiente de
variacao 20,1% contra 13,4%), que e exatamente o que a fase arbitraria de janeiro
faz prever. `liquid_flow5` continua como candidato no ranking justamente por
isso: se a banda abrir vantagem consistente em dado novo, esta decisao deve ser
revista, e ela precisa estar sendo medida para que isso seja notado.
"""
from __future__ import annotations

from strategy.liquid_sleeves5 import LiquidSleeves5


class LiquidChampion(LiquidSleeves5):
    """Cinco sleeves de universo liquido (top-20, epoca de 12 meses), numa conta so."""

    name = "liquid_champion"
    version = "1.0"
    candidate = True
