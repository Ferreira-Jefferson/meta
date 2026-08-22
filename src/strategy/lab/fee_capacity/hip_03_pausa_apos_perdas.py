"""fee_capacity/hip_03 -- pausar novas entradas depois de 2 saidas negativas
seguidas evita operar durante o regime ruim que causa o pior DD de liquid_focus?

Diagnostico (medido 2026-08-21, ANTES deste arquivo)
------------------------------------------------------
As 5 piores janelas por DD do holdout de `liquid_focus` NAO sao 5 eventos
independentes -- convergem na MESMA sequencia real de trades, fev/2013 a
nov/2014 (RADL3 -5,9% -> SBSP3 STOP -19% -> UGPA3 -7,7% -> USIM5 STOP -20% ->
USIM5 +14,6% -> UGPA3 -0,5% -> TIMS3 +11,4% -> DASA3 STOP -20,1% -> ITUB4
+0,9%). Nao e 2008 (fora do holdout de proposito) -- e o Taper Tantrum
(meados de 2013, fuga de EM com o fim do QE americano) emendando com o
prelúdio da recessao/crise Petrobras (final de 2014). Ha uma sequencia REAL
de 4 perdas seguidas (RADL3, SBSP3, UGPA3, USIM5) antes da recuperacao.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
Depois de 2 saidas seguidas com resultado negativo, o robo entra em modo
"caixa" -- para de abrir posicao nova por `pause_bars` pregoes (~21, um mes,
mesma cadencia de rebalanceamento da familia) -- em vez de rotacionar
imediatamente pro proximo candidato do ranking. O caixa parado RENDE Selic
(ver `cash_yield_bug_2026_08_20` em memoria, ja corrigido no engine), entao
pausar nao e o mesmo que perder o dinheiro parado debaixo do colchao.

SIMPLIFICACAO DECLARADA: a formulacao original ("so volta a operar quando
apresentar sequencia no sentido em que eu opero") pediria checar se o
momentum do PROXIMO candidato (ainda nao escolhido) virou positivo antes de
liberar a pausa -- isso exigiria acoplar este wrapper ao ranking interno do
sleeve (`LiquidSleeve._scores`), o que o tornaria fragil a qualquer mudanca
de como o sleeve pontua candidatos. A versao aqui usa uma pausa de
CALENDARIO fixa como proxy honesto e simples: mede a direcao do efeito
(sair do caixa cedo ou tarde demais) sem acoplar aos internals do sleeve.
Se isto passar, uma versao com gate por momentum pode ser tentada depois.

Risco declarado da aposta: ficar em caixa por `pause_bars` pregoes pode
atrasar a entrada bem no INICIO de uma recuperacao -- se a hipotese estiver
errada, isso deve aparecer como CAGR mediano MENOR no holdout completo, nao
gratis (mesmo padrao de risco declarado de hip_02, que se confirmou l·).

O que este arquivo NAO faz: nao muda o momentum, o dip, a histerese, nem o
universo -- so suprime `Enter` por `pause_bars` pregoes apos o gatilho.
`Exit` (STOP ou qualquer outro motivo) nunca e bloqueado -- controle de risco
real nunca espera pausa nenhuma. Assume sleeve_count=1 (LiquidFocus).

PROMOVIDO ao ranking automatico e UNICO CANDIDATO do podio (2026-08-21)
--------------------------------------------------------------------------
`candidate = True`. Holdout de 48 janelas (R$100+taxa real) melhorou em
TODAS as metricas sobre `liquid_focus` (pior janela CAGR -1,6%->+0,6%, DD
pior -52,8%->-47,0%, pior 12m -43,9%->-38,3%, capital final da pior janela
R$92,28->R$103,30) e no FULL (R$1.368,01->R$2.957,93). Decisao explicita do
dono do capital, depois de:
  - confirmar que o edge INTEIRO (deste robo e de `liquid_focus`) depende
    de 3-5 eventos raros/semi-raros (WEGE3/Covid, RADL3/fusao, BRAP4/
    commodity, CSNA3/commodity, SBSP3/privatizacao) -- sem eles, prejuizo;
  - testar e refutar 4 sinais alternativos que tentavam nao depender disso
    (medo+volume, medo+volume+saida rapida, baixa-volatilidade, valor-
    relativo/pairs -- ver `strategy/lab/market_nature/` e
    `strategy/lab/relative_value/`, `strategy/lab/quality_factor/`);
  - testar e refutar diversificacao (sleeve_count 2/3, espiral de morte da
    taxa fixa ainda pior) e stop movel (decapita o WEGE3, troca retorno por
    protecao parcial);
  - medir o capital ideal de operacao: R$500 e o piso que passa todos os
    portoes de risco, R$2.000-3.000 e onde a taxa fixa deixa de distorcer
    o resultado por completo.
`liquid_dual10` e `sintese_02_iliquidez_grupo_risco_orcado` foram
APOSENTADOS no mesmo dia (ver os proprios arquivos) -- o dono do capital
escolheu reduzir o podio a este UM robo so, em vez de manter os quatro que
disputavam antes.
"""
from __future__ import annotations

from strategy.base import Enter, Exit
from strategy.lab.fee_capacity.hip_01_concentracao import LiquidFocus


class LiquidFocusLossStreakPause(LiquidFocus):
    """`LiquidFocus` + pausa de entradas após `loss_streak_threshold` saídas
    negativas seguidas.

    Ver o docstring do módulo para a hipótese a priori e a simplificação
    declarada — a pausa é de calendário, não um gate por momentum.
    """
    # (docstring COM acento de propósito: a primeira frase dele é o resumo
    # que aparece no cartão do catálogo e no topo da ficha do robô, ver
    # `strategy/registry.py::docstring_parts`. O docstring do módulo segue em
    # ASCII, como o resto do histórico escrito antes disto.)

    # "liqflop" = LIQ(uid) + F(ocus) + LO(ss) + P(ause) -- as quatro pecas do
    # desenho, na ordem em que foram decididas: LiquidSleeves5 (universo por
    # LIQuidez) -> LiquidFOcus (concentrado em 1 posicao) -> pausa apos
    # perdas seguidas (LOss streak) -> Pausa de calendario. Renomeado de
    # `liquid_focus_loss_pause` em 2026-08-21, so o nome externo (`name`),
    # nada de comportamento muda.
    name = "liqflop"
    version = "1.0"
    candidate = True  # UNICO candidato do podio desde 2026-08-21 -- ver docstring do modulo

    # ---------------------------------------------------------------- ficha
    # TEXTO PARA O DONO DO CAPITAL (nao para quem le codigo) -- ver a
    # convencao em `strategy/base.py`. Os numeros abaixo foram CONFERIDOS
    # contra a instancia real (2026-08-22), nao contra a assinatura das
    # classes-base: 1 posicao (`top_n`/`sleeve_count`), universo top-20 por
    # liquidez (`universe_n=20`) tirado de um pool FIXO de 63 tickers
    # (`liquid_sleeve.POOL`) e reranqueado a cada 12 meses
    # (`refresh_months=12`, mediana de giro de `liquidity_window=252`
    # pregoes), momentum 12-1 (`lookback=252`/`skip_recent=21`), dip 2%,
    # janela de 40 pregoes (~8 semanas), histerese 15% (`_hysteresis`,
    # privado -- por isso nao aparece na tabela de parametros), Selic
    # (`selic_threshold=0,5%` em `selic_window=63`), pausa de 21 pregoes
    # depois de 2 perdas seguidas.
    #
    # Tres coisas que a versao anterior desta ficha errava, todas corrigidas
    # aqui (2026-08-22) -- registradas para nao voltarem:
    #   1. dizia "as 20 acoes mais negociadas da BOLSA", sugerindo re-selecao
    #      mensal em todo o mercado. E' top-20 de um pool fixo de 63, revisto
    #      1x por ano.
    #   2. afirmava que papel que sai do top-20 e VENDIDO. E' o oposto:
    #      `evict_on_refresh=False` neste robo (grandfathering) -- o refresh
    #      proibe COMPRAR fora da lista, nao segurar o que ja se tem.
    #   3. anunciava o stop de 15% como regra do robo. Ele e' do ENGINE
    #      (`BacktestConfig.stop_loss_pct`), nao um parametro desta classe --
    #      por isso nao esta (e nao pode estar) na tabela de parametros.
    tagline = (
        "Compra uma ação por mês — a de melhor desempenho no ano que estiver em "
        "queda recente — e para de comprar por um mês depois de duas vendas no "
        "prejuízo seguidas."
    )
    plain_summary = (
        "Ele carrega uma ação por vez e decide uma vez por mês. No último dia útil, "
        "olha a sua lista de 20 ações, escolhe a que subiu mais nos últimos 12 "
        "meses — ignorando o mês mais recente, para não comprar o que acabou de "
        "disparar — e compra. Mas só compra se essa ação estiver pelo menos 2% "
        "abaixo da máxima das últimas 8 semanas: ele não paga o topo. Se nenhuma "
        "candidata estiver em queda, o mês passa sem compra nenhuma, e isso é "
        "regra, não falha.",
        "Essa lista de 20 não é escolhida a dedo nem refeita todo mês. Uma vez por "
        "ano ele pega um conjunto fixo de 63 ações da bolsa e fica com as 20 mais "
        "negociadas do último ano — só volume, nenhum olhar sobre retorno. É o que "
        "impede o robô de operar papel que não gira, onde o próprio dinheiro dele "
        "moveria o preço.",
        "No mês seguinte ele refaz a conta. Só troca de ação se a nova candidata "
        "estiver pelo menos 15% melhor que a que ele já tem — trocar por pouco só "
        "paga corretagem. Fora dessa data mensal ele não faz nada, com uma exceção: "
        "se a ação cair 15% abaixo do preço que ele pagou, ela é vendida no mesmo "
        "dia, sem esperar o fim do mês. Esse limite de 15% é do backtest, não um "
        "botão do robô: quem o aplica é o motor que executa as ordens.",
        "A parte que dá nome ao robô: depois de duas vendas no prejuízo seguidas, "
        "ele para de comprar por um mês inteiro e fica no caixa, rendendo Selic. "
        "Passado esse mês, volta a operar normalmente — a pausa é de calendário, "
        "não uma opinião sobre o mercado. Ela existe porque as piores quedas do "
        "histórico dele não foram um tombo isolado, foram uma sequência de perdas "
        "encadeadas.",
    )
    plain_example = (
        "Último dia útil de março. Entre as 20 ações da lista, WEGE3 é a que mais "
        "subiu em 12 meses e está 3% abaixo da máxima das últimas 8 semanas — ele "
        "compra WEGE3 com todo o caixa, na abertura do dia seguinte.",
        "Abril e maio: WEGE3 continua sendo a melhor da lista. Ele não faz nada. "
        "Nenhuma ordem, nenhuma taxa.",
        "Junho: RADL3 aparece 8% melhor que WEGE3. Oito é menos que os 15% exigidos "
        "para justificar a troca, então ele fica onde está.",
        "Julho: RADL3 está 20% melhor. Aí sim ele vende WEGE3 e compra RADL3.",
        "Agosto: RADL3 é vendida com prejuízo. Setembro: a próxima também. Duas "
        "perdas seguidas — ele fica em caixa em outubro inteiro, sem comprar nada, "
        "e volta a decidir no fim de outubro.",
    )

    # Regras em linguagem de DONO, escritas de novo (nao herdadas da familia,
    # que as escreve com nome de parametro): a folha e o unico lugar que sabe
    # os numeros de verdade. O detalhe tecnico continua no docstring do
    # modulo e nas classes-base.
    watched_signals = (
        "O quanto cada ação subiu nos últimos 12 meses, sem contar o mês mais "
        "recente. É o que define a “melhor da lista”.",
        "A que distância cada ação está da máxima das últimas 8 semanas — é a queda "
        "recente que ele exige para comprar.",
        "Quanto dinheiro cada ação negocia por dia, medido pela mediana do último "
        "ano. É o que define a lista de 20, revista uma vez por ano. Papel que não "
        "gira não entra, por mais atraente que pareça.",
        "A Selic: uma alta forte em três meses faz ele zerar a carteira.",
        "O calendário: o último dia útil do mês (a única data em que ele decide) e a "
        "semana de divulgação de balanços.",
        "As duas últimas vendas: se as duas deram prejuízo, a pausa dispara.",
    )
    entry_rules = (
        "Decide uma vez por mês, no último dia útil. Em qualquer outro dia ele não "
        "olha preço nem manda ordem.",
        "Compra a ação de melhor desempenho em 12 meses entre as 20 da sua lista — "
        "uma ação só, com todo o caixa disponível.",
        "A lista de 20 é refeita uma vez por ano, pelas mais negociadas do último "
        "ano dentro de um conjunto fixo de 63 ações. Ele nunca compra fora dela.",
        "Só compra se a ação estiver pelo menos 2% abaixo da máxima das últimas 8 "
        "semanas. Se nenhuma estiver, o mês passa sem compra.",
        "Só troca a ação que já tem se a nova candidata estiver 15% melhor. Troca "
        "por pouco só paga corretagem.",
        "Depois de duas vendas no prejuízo seguidas, para de comprar por um mês e "
        "fica no caixa, rendendo Selic. É pausa de calendário: passado o mês, ele "
        "volta a comprar mesmo que o mercado ainda pareça ruim.",
        "Na semana de balanços ele adia a decisão em vez de forçá-la, e refaz a "
        "conta do zero no primeiro dia livre.",
        "O que ele decide no fechamento de um dia é executado na abertura do dia "
        "seguinte — nunca no mesmo dia.",
    )
    exit_rules = (
        "Vende quando a ação deixa de ser a melhor da lista por uma margem de 15% — "
        "na virada do mês.",
        "Vende no mesmo dia, sem esperar o fim do mês, se a ação cair 15% abaixo do "
        "preço que ele pagou. Esse limite é fixo no preço de compra: ele não sobe "
        "junto com o lucro.",
        "Zera a carteira inteira se a Selic subir forte em três meses. É a única "
        "defesa macro que ele tem.",
        "Ação que ele já tem e que sai da lista das 20 NÃO é vendida por isso. Ela "
        "continua sendo julgada pelo desempenho, como qualquer outra — o que a "
        "revisão anual da lista proíbe é COMPRAR fora dela, não segurar o que já "
        "está na carteira. Vender por causa do calendário custaria corretagem e "
        "imposto num dia que não foi escolhido pelo sinal.",
        "A pausa depois das duas perdas nunca bloqueia uma venda: ela só impede "
        "compra nova. Controle de risco não espera pausa.",
    )
    sizing_rules = (
        "Uma posição por vez, com todo o caixa livre. Concentrar não é agressividade: "
        "no mercado fracionário a corretagem é de R$ 1,90 fixos POR ORDEM, então "
        "dividir o mesmo dinheiro em cinco ações multiplica a taxa por cinco sem "
        "multiplicar nada mais. Numa posição de R$ 20, R$ 1,90 é quase 10% só de "
        "corretagem; numa de R$ 100, é 1,9%.",
        "O preço disso está declarado: uma ação ruim pesa o capital inteiro. Isso "
        "aparece na queda máxima medida, não é de graça.",
        "Capital de operação medido: R$ 500 é o piso em que ele passa todos os "
        "portões de risco; de R$ 2.000 a R$ 3.000 a corretagem deixa de distorcer o "
        "resultado. Abaixo disso o desenho ainda funciona, mas a taxa é que manda.",
        "Toda compra e venda já vem com custo descontado — corretagem, taxas da bolsa "
        "e o deslize de preço da execução.",
        "Enquanto está fora do mercado, o caixa rende Selic. Ficar parado é uma "
        "posição, não uma pausa.",
    )
    param_docs = {
        "loss_streak_threshold": "Vendas no prejuízo seguidas que disparam a pausa.",
        "pause_bars": "Dias de bolsa sem comprar depois do gatilho (21 ≈ 1 mês).",
    }
    # Encanamento, fora da ficha (ver `Strategy.param_hidden`): `selic_path` é
    # caminho de arquivo, `redist_mode` só existe para os satélites (que este
    # robô não usa) e `sleeve_count` é o nome interno da mesma coisa que
    # `top_n` já diz -- uma posição por vez.
    param_hidden = ("selic_path", "redist_mode", "sleeve_count")

    def __init__(self, loss_streak_threshold: int = 2, pause_bars: int = 21, **kwargs):
        super().__init__(**kwargs)
        self.loss_streak_threshold = loss_streak_threshold
        self.pause_bars = pause_bars
        self._loss_streak = 0
        self._pause_bars_left = 0
        self._prev_open: dict = {}

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        self._close_panels = {t: df["close"] for t, df in panels.items()}

    def on_bar(self, date, open_positions, cash_available):
        actions = super().on_bar(date, open_positions, cash_available)

        # `Exit(STOP)` e decidido pelo ENGINE intra-bar (ver docstring de
        # `strategy/base.py`) e NUNCA aparece nas acoes que `on_bar` devolve
        # -- por isso a saida e detectada comparando o snapshot de posicoes
        # entre pregoes (`_prev_open` vs `open_positions` de hoje), nao a
        # lista de acoes. O resultado realizado usa o fechamento de hoje
        # (mesma base sem look-ahead dos scores de momentum da familia)
        # contra o preco de entrada guardado na posicao anterior.
        saidas_hoje = set(self._prev_open) - set(open_positions)
        for t in saidas_hoje:
            entry_price = self._prev_open[t].entry_price
            closes = self._close_panels.get(t)
            atual = closes.loc[date] if closes is not None and date in closes.index else None
            if atual is None:
                continue
            if atual < entry_price:
                self._loss_streak += 1
            else:
                self._loss_streak = 0

        if self._loss_streak >= self.loss_streak_threshold and self._pause_bars_left == 0:
            self._pause_bars_left = self.pause_bars
            self._loss_streak = 0

        if self._pause_bars_left > 0:
            self._pause_bars_left -= 1
            actions = [a for a in actions if not isinstance(a, Enter)]

        self._prev_open = dict(open_positions)
        return actions
