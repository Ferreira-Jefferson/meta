"""quality_factor/hip_01 -- ranquear por MENOR volatilidade realizada (em
vez de momentum 12-1) encontra uma vantagem que NAO dependa de pegar
poucos trades grandes?

Contexto (medido 2026-08-21, ANTES deste arquivo)
----------------------------------------------------
Medido com amostra grande (174 trades, `liquid_sleeves5`, R$1.000, sem
taxa fixa -- o regime sem distorcao de capital pequeno): o trade MEDIANO
do sinal momentum 12-1 + dip 2% ja e' perdedor (-0,9%) mesmo contando TODOS
os trades, taxa de acerto 48,3%. O resultado positivo da familia inteira
vem de uma cauda direita gorda (RADL3 +158%, BPAC11 +156%, WEGE3 +105%,
CSNA3 +90%...) -- assinatura classica de trend-following (poucos trades
grandes financiam muitos pequenos, as vezes perdedores). Pedido explicito
do usuario: testar um sinal de filosofia OPOSTA -- baixa volatilidade
("qualidade"/estabilidade) em vez de momentum -- pra ver se existe alguma
vantagem que NAO dependa de pegar os poucos trades extremos.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
A "anomalia de baixa volatilidade" e' um fator bem documentado na
literatura academica (Ang et al. 2006, "Low Volatility Anomaly"): acoes
menos volateis tendem a ter retorno ajustado a risco melhor (as vezes
retorno absoluto melhor tambem) que acoes mais volateis, ao contrario do
que a teoria classica (mais risco = mais retorno) preveria. Ranquear os
candidatos elegiveis (mesmo universo top-20 por liquidez, mesmo gate de
dip 2%/40 pregoes) pela MENOR volatilidade realizada de 60 pregoes, em vez
do maior momentum 12-1, deveria produzir uma distribuicao de trades mais
"normal" -- menos cauda extrema, talvez taxa de acerto mais alta -- porque
a aposta nao e mais "este papel vai continuar subindo forte", e' "este
papel e estavel e caiu um pouco, deve voltar ao normal sem susto".

O que este arquivo NAO faz: nao muda o gate de dip, a histerese (15% de
vantagem pra trocar, agora medido em unidades de "menos volatilidade"),
o stop, o gate de Selic, nem o universo -- so troca a REGUA de ranking de
momentum para baixa-volatilidade.

Risco declarado da aposta: baixa volatilidade pode simplesmente significar
baixa LIQUIDEZ/interesse do mercado (papel parado, nao "estavel por
qualidade"), ou pode nunca ter um motivo pra subir (sem catalisador, sem
tendencia) -- se a hipotese estiver errada, isso deve aparecer como CAGR
mediano pior que o momentum no holdout completo, nao ser gratis.

`candidate = False`: mesma razao de toda a familia lab -- so disputa o
ranking automatico depois de julgado no holdout de 48 janelas + FULL.

RESULTADO (medido apos este arquivo) -- NAO RESOLVE A DEPENDENCIA DE OUTLIERS, E PIOR NO CAPITAL REAL
------------------------------------------------------------------------------------------------------------
Escala grande (R$1.000, 5 sleeves, sem taxa, 108 trades): mediana POSITIVA
contando todos os trades (+1,6% vs -0,9% do momentum), mas some (-2,8%,
pior que momentum) assim que se exclui os 10 melhores -- baixa-vol NAO
evita a dependencia de outliers, e o top-5 inclui RADL3 e WEGE3, OS MESMOS
outliers do momentum (uma alta de tendencia pode ter vol baixa no caminho
-- os dois sinais nao sao independentes). CAGR pior (9,1% vs 10,1%).

Capital real (R$100 + taxa fixa, 1 posicao): DECISIVAMENTE pior, nao so
"menos bom" -- holdout mediana -2,6% (era +18,6%), 38/48 janelas negativas
(eram 2), so bate IBOV em 17/48 (eram 48/48). FULL: R$100 -> R$57,21
(CAGR -3,3%, PREJUIZO liquido). Nao promovido.
"""
from __future__ import annotations

from core.indicators import historical_volatility
from strategy.liquid_sleeve import LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5


class LiquidSleeveLowVol(LiquidSleeve):
    """`LiquidSleeve` com o RANKING trocado de momentum 12-1 para MENOR
    volatilidade realizada. Ver docstring do modulo para a hipotese; o
    gate de dip e tudo mais fica igual."""

    name = "liquid_sleeve_low_vol"
    version = "1.0"
    candidate = False  # peca de composicao, mesma razao de LiquidSleeve

    def __init__(self, vol_window: int = 60, **kwargs):
        super().__init__(**kwargs)
        self.vol_window = vol_window

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        for t, df in panels.items():
            if t not in self._eligible.columns:
                continue
            vol = historical_volatility(df["close"], self.vol_window)
            # score = -vol: quanto MENOR a volatilidade, MAIOR o score
            # (rank-1 = candidato mais estavel entre os elegiveis).
            score = -vol
            self._raw_scores[t] = score
            mask = self._eligible[t].reindex(score.index).fillna(False)
            self._scores[t] = score.where(mask)


class LiquidFocusLowVol(LiquidSleeves5):
    """`LiquidSleeves5` (default 1 posicao) ranqueando por baixa
    volatilidade em vez de momentum. Ver docstring do modulo."""

    name = "liquid_focus_low_vol"
    version = "1.0"
    candidate = False

    def __init__(self, sleeve_count: int = 1, vol_window: int = 60, **kwargs):
        self._lv_kwargs = dict(vol_window=vol_window)
        super().__init__(sleeve_count=sleeve_count, **kwargs)

    def _make_sleeve(self, **kwargs) -> LiquidSleeve:
        return LiquidSleeveLowVol(**kwargs, **self._lv_kwargs)
