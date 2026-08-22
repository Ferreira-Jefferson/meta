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

    # Ficha: o que este arquivo acrescenta e a PAUSA, e so ela (ver `Strategy`
    # em `strategy/base.py`).
    watched_signals = LiquidFocus.watched_signals + (
        "Sequência de perdas: compara o snapshot de posições entre pregões para "
        "descobrir toda saída — inclusive a que o engine decidiu por stop, que nunca "
        "aparece nas ações devolvidas por `on_bar`. Saída abaixo do preço de entrada "
        "conta como perda; qualquer ganho zera a contagem.",
    )
    entry_rules = LiquidFocus.entry_rules + (
        "Depois de `loss_streak_threshold` saídas negativas SEGUIDAS, para de abrir "
        "posição nova por `pause_bars` pregões e fica em caixa (rendendo Selic, se "
        "ligado).",
        "A pausa é de CALENDÁRIO, não de sinal: ela não espera o momentum virar. É a "
        "simplificação declarada da hipótese — acoplar a liberação ao ranking interno "
        "do sleeve deixaria o robô frágil a qualquer mudança de como ele pontua.",
        "Risco declarado da aposta: ficar de fora `pause_bars` pregões pode atrasar a "
        "entrada bem no início de uma recuperação.",
    )
    exit_rules = LiquidFocus.exit_rules + (
        "A pausa NUNCA bloqueia uma saída. Só `Enter` é filtrado — controle de risco "
        "real não espera pausa nenhuma.",
    )
    param_docs = {
        "loss_streak_threshold": "Saídas negativas seguidas que disparam a pausa.",
        "pause_bars": "Pregões sem comprar depois do gatilho (21 ≈ 1 mês).",
    }

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
