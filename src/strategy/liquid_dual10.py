"""LiquidDual10 -- dez sleeves, duas faixas de liquidez, uma conta so.

De onde vem o desenho
----------------------
`strategy/liquid_champion.py` (top-20 por giro financeiro, 5 sleeves) e uma
peca de medicao equivalente na faixa 21-40 (mesmo sinal, `rank_offset=20`)
foram rodados lado a lado nas 48 janelas de `run_holdout_frozen.py`.
A correlacao diaria mediana entre as duas curvas foi 0,46 e a combinacao
estatica 50/50 teve MaxDD melhor que a media dos dois isolados em 48 das 48
janelas. Isso e o resultado de H2: duas faixas de liquidez disjuntas, com o
MESMO sinal, se complementam mais do que diversificam por acaso.

Esta classe testa se essa combinacao pode ser UM robo em vez de duas contas
separadas na corretora: 10 sleeves na mesma conta, 5 sobre o top-20 (rank_offset
0, o universo do campeao) e 5 sobre a faixa 21-40 (rank_offset 20), cada
sleeve dimensionando a entrada em 1/10 do caixa livre.

A peca de medicao isolada da faixa 21-40 (`liquid_mid5`) foi APAGADA em
2026-08-20 a pedido do dono: ela era redundante como robo (esta faixa vive
dentro deste arquivo, nos sleeves 5-9) e nao era candidata a podio. O custo
declarado da remocao: a correlacao de 0,46 citada acima deixou de ter codigo
que a reproduza — ela e agora uma afirmacao historica, nao um numero
re-executavel.

ATENCAO -- 10 SLEEVES, MAS NO MAXIMO 5 POSICOES
------------------------------------------------
Esta e a caracteristica mais importante do robo e ela NAO estava documentada
ate 2026-08-20. `BacktestConfig.max_concurrent_positions` vale 5 por default e
e um teto do ENGINE, checado em `backtest/sizing.py::has_free_slot` -- o mesmo
que o runtime ao vivo aplica em `live/runtime.py`. O campeao tem 5 sleeves e
nunca encosta nesse teto. Este robo tem 10 sleeves disputando 5 vagas, entao o
teto APERTA, e duas consequencias caem sobre todo numero medido deste arquivo:

  1. **O robo fica ~50% em caixa por construcao.** Cada sleeve dimensiona a
     entrada em 1/10 do caixa livre, mas so 5 entradas cabem: 5 x 10% = 50% do
     patrimonio a mercado, no maximo. A exposicao media medida nas 48 janelas
     do holdout foi 43,9%, contra 76,3% do campeao. Parte relevante da vantagem
     de drawdown (-17,0% contra -34,4%) vem DISSO, e nao da segunda faixa.
     `scripts/run_dual10_holdout.py` roda o controle que separa as duas coisas
     (mistura estatica campeao+Selic na mesma exposicao): o dual10 ganhou nas
     quatro colunas, entao o caixa explica parte da vantagem, nao toda.
  2. **A faixa 21-40 so pega vaga que sobra.** `LiquidSleeves5.on_bar` percorre
     os sleeves em ordem, entao os sleeves 0-4 (top-20) reivindicam as vagas
     primeiro e a faixa 21-40 fica com o que sobrar. Medido no holdout: 33,0%
     de exposicao na faixa top-20 contra 10,9% na faixa 21-40, apesar de as
     duas terem 5 sleeves cada. Nao e 50/50, e aproximadamente 75/25.

Rodar este robo com o teto solto (`max_concurrent_positions=10`, que seria "o
desenho literal" de 10 sleeves) da um robo DIFERENTE e pior no que importa:
janela FULL, capital final R$ 6.067 contra R$ 5.412, mas MaxDD -28,1% contra
-16,9% e 363 trades contra 200. Ou seja, o teto de 5 nao e um defeito a ser
corrigido -- e parte do desenho que produziu os numeros aprovados. Ele so
estava implicito, herdado do default do repo, e agora esta declarado.

`tests/test_liquid_dual10.py` trava esse acoplamento: se alguem mudar o default
de `max_concurrent_positions`, o teste quebra em vez de o robo mudar de
comportamento em silencio.

**Zero parametro novo.** Nenhum numero aqui foi ajustado para melhorar nada: e
o campeao (`liquid_champion`) mais a faixa 21-40 do MESMO ranking de liquidez,
com o MESMO sinal congelado (momentum 12-1, dip 2%, high_window 40, histerese
15%, gate de Selic). A unica coisa que este arquivo decide e como fatiar cada
faixa em 5 -- por rodizio `[i::5]` DENTRO da faixa, exatamente como
`liquid_sleeve.py` fatia o top-20. Nao e `[i::10]` sobre 40 nomes: isso mudaria
o perfil de risco de cada sleeve (misturaria blue chip com papel de faixa 21-40
na mesma fatia) e deixaria de ser o desenho que H2 mediu.

Promovido a candidato em 2026-08-20
------------------------------------
`candidate = True`. Decisao do dono do capital, tomada depois de tres rodadas
de medicao nas 48 janelas do holdout congelado, todas com o robo pareado
contra `liquid_champion` e o IBOV:

  1. `scripts/run_dual10_holdout.py` (R$ 1.000, sem aporte): CAGR mediano
     11,0% contra 5,0% do campeao; pior MaxDD -17,0% contra -34,4%; bate o
     IBOV em 48/48 janelas contra 47/48. Controle de exposicao (criterio 3)
     passou em 4 das 4 colunas contra a mistura estatica campeao+Selic na
     mesma exposicao media.
  2. `scripts/run_dual10_control_k10.py`: a vantagem NAO e o k=10 disfarcado.
     Rodando `LiquidChampion(sleeve_count=10)` -- dez sleeves no MESMO top-20,
     sem a segunda faixa -- com exposicao media quase identica (42,0% contra
     43,9%, diferenca limpa), o dual10 ainda vence por +6,0 p.p. de CAGR
     mediano e +2,8 p.p. de MaxDD. A faixa 21-40 faz trabalho real, nao e
     diluicao de tamanho de posicao.
  3. `scripts/run_capital_real_100.py` (R$ 100 + R$ 100/mes, o capital real do
     operador, nao a convencao de R$ 1.000 do diario): TIR mediana 15,46%
     contra 11,84% do campeao, DD de cota -11,63% contra -32,03%, e ZERO das
     48 janelas terminou com TIR negativa (o campeao teve 5/48).

Ressalva que continua de pe e nao foi resolvida por nenhuma das tres rodadas:
o vies de sobrevivencia assimetrico da faixa 21-40 (ver abaixo) nao e
mensuravel com os dados que existem em `data/raw/` -- precisaria de tickers
deslistados entre 2010 e 2026. A decisao de promover foi tomada sabendo disso,
nao apesar de ignora-lo.

Vies de sobrevivencia ASSIMETRICO entre as duas faixas
-------------------------------------------------------
O `POOL` de `strategy/liquid_sleeve.py` so tem empresas vivas em 2026 -- quem
saiu da bolsa entre 2010 e hoje simplesmente nao esta no arquivo. Isso ja
inflava o numero do campeao (top-20); aqui infla MAIS a metade nova (rank_offset
20), porque a mortalidade da B3 mora tipicamente fora das blue chips do top-20,
que sobreviveriam de qualquer jeito. As duas metades deste robo carregam o
mesmo tipo de vies em proporcoes diferentes -- o numero da faixa 21-40 deve ser
lido com desconto maior que o do top-20.

Capacidade
----------
A faixa 21-40 gira financeiramente menos que o top-20 por definicao do
proprio ranking. A capacidade em reais deste robo -- limitada pelo lado mais
fraco -- e menor que os ~R$ 14 milhoes do campeao sozinho. Qualquer capital
final medido aqui tem de ser lido junto com essa capacidade, nao isolado.

A armadilha do k=10
--------------------
`strategy/liquid_champion.py` registra que k=10 (dez sleeves sobre o MESMO
top-20) ja pareceu reduzir MaxDD antes e nao era diversificacao: a exposicao
media caia de 72,7% (k=5) para 40,3% (k=10) porque cada sleeve passa a
escolher entre poucos papeis e fica mais tempo em caixa. `run_champion_k_control.py`
mostrou que uma mistura estatica de k=5 com Selic, calibrada para a MESMA
exposicao media, bate o k=10 puro em CAGR, pior janela e pior 12 meses -- o
ganho era caixa parado, nao risco menor.

Este arquivo tambem tem 10 sleeves, entao carrega o mesmo risco: se a
exposicao media do dual10 vier menor que a do campeao (5 sleeves, mesmo
universo), o motivo pode ser so isso, nao a faixa 21-40 sendo genuinamente
descorrelacionada. `scripts/run_dual10_holdout.py` (arquivo 2 desta mudanca)
mede a exposicao media dos dois braços e, se a do dual10 for menor, roda o
mesmo controle de mistura estatica com Selic antes de aceitar qualquer melhora
de drawdown como real. Este arquivo so se sustenta como composicao de conta se
esse controle passar -- ele mesmo nao decide nada sozinho.
"""
from __future__ import annotations

from strategy.liquid_sleeves5 import LiquidSleeves5

_FIXED = ("sleeve_count", "rank_offset")


class LiquidDual10(LiquidSleeves5):
    """Dez sleeves: 5 no top-20 de liquidez (offset 0), 5 na faixa 21-40 (offset universe_n)."""

    name = "liquid_dual10"
    version = "1.0"
    candidate = True

    def __init__(
        self,
        universe_n: int = 20,
        liquidity_window: int = 252,
        refresh_months: int = 12,
        min_history_days: int = 504,
        evict_on_refresh: bool = False,
        **kwargs,
    ):
        presos = [k for k in _FIXED if k in kwargs]
        if presos:
            raise TypeError(
                f"liquid_dual10: {', '.join(presos)} fixo(s) neste desenho -- "
                "10 sleeves (5+5), rank_offset 0/universe_n. Nao aceita override."
            )
        # Constroi via super() para herdar sleeve_count/_owner/etc como o
        # sleeves5 espera; a lista de 10 sleeves criada aqui (todos com
        # rank_offset=0) e descartada e substituida logo abaixo pelas duas
        # faixas disjuntas -- minimo toque, zero mudanca na classe base.
        super().__init__(
            sleeve_count=10,
            universe_n=universe_n,
            liquidity_window=liquidity_window,
            refresh_months=refresh_months,
            min_history_days=min_history_days,
            evict_on_refresh=evict_on_refresh,
            **kwargs,
        )
        self._sleeves = [
            self._make_sleeve(
                sleeve_index=i,
                sleeve_count=5,
                universe_n=universe_n,
                rank_offset=offset,
                liquidity_window=liquidity_window,
                refresh_months=refresh_months,
                min_history_days=min_history_days,
                evict_on_refresh=evict_on_refresh,
                **kwargs,
            )
            for offset in (0, universe_n)
            for i in range(5)
        ]
