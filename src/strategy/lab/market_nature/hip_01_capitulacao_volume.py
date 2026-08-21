"""market_nature/hip_01 -- ranquear candidatos por MEDO+AGRESSAO (IFR baixo
confirmado por volume alto) em vez de momentum 12-1, pega reversoes mais
confiaveis que "so caiu X% da maxima"?

Contexto (por que esta hipotese, medido 2026-08-21, ANTES deste arquivo)
--------------------------------------------------------------------------
Toda a familia `buy_the_dip`/`portfolio_dip2_hw40`/`liquid_sleeves5` ranqueia
candidatos por um numero PURAMENTE de preco: momentum 12-1 (retorno dos
ultimos 12 meses, pulando o ultimo mes). O gate de entrada e' "caiu >= 2% da
maxima de 40 pregoes" -- tambem so preco. Nenhum dos dois olha PARTICIPACAO
(volume) nem distingue uma queda com convicção vendedora de um papel que so
foi perdendo interesse aos poucos. Pedido explicito: uma estrategia guiada
pela natureza do mercado -- sinais de agressividade e medo, volume -- nao so
pelos numeros de retorno.

`core/market_features.py` e `core/indicators.py` JA calculam `ifr14` (RSI,
medo/sobrevenda) e `volume_vs_avg20` (participacao/agressao) para TODO
ticker, mas hoje isso so alimenta o `MarketSnapshot` do diario (anotacao,
nunca decisao -- ver a regra 6 do modulo). Esta e a primeira vez que esses
dois numeros entram numa decisao de ENTRADA.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
Um candidato com IFR14 em zona de sobrevenda (medo real, exaustao
vendedora) *confirmado* por volume acima da media (agressao real -- alguem
esta vendendo com convicção, nao e' so falta de interesse) e' um sinal de
capitulacao mais confiavel de reversao de curto prazo do que apenas
"caiu X% da maxima" (que nao distingue queda com convicção de queda vazia).
`capitulacao = max(0, limiar_ifr - ifr14) * max(0, volume/media20 - limiar_vol)`
-- ZERO se faltar QUALQUER uma das duas condicoes (nao e' medo sem volume,
nem volume sem medo). Ranking: em vez do momentum 12-1, usa este score.

O QUE NAO MUDA (mesma maquina testada e validada do resto da familia):
universo por liquidez (top-20, POOL), sleeve, sizing, histerese de 15% pra
trocar de posicao, o STOP, o gate de Selic, o blackout de resultados, e o
GATE de dip (`dist_from_high <= -dip_pct`, 2% de 40 pregoes) -- o candidato
ainda precisa estar em queda pra entrar, so quem GANHA o rank-1 entre os
elegiveis muda de "melhor momentum" pra "capitulacao mais extrema
confirmada por volume".

Risco declarado da aposta: um papel em capitulacao pode ser uma "faca
caindo" -- continuar despencando em vez de reverter. Se a hipotese estiver
errada, isso deve aparecer como STOP mais frequente e/ou CAGR pior no
holdout completo, nao ser gratis.

`candidate = False`: mesma razao de toda a familia lab -- so disputa o
ranking automatico depois de julgado no holdout de 48 janelas (mesmo
protocolo de `fee_capacity/hip_01/02/03`), nunca antes.

RESULTADO (holdout completo, 48 janelas + FULL, medido apos este arquivo) -- REFUTADA
---------------------------------------------------------------------------------------
O risco declarado se confirmou em cheio: capitulacao (IFR baixo + volume
alto) dentro desta familia de rotacao/histerese pega a faca caindo, nao a
reversao. Holdout: mediana de CAGR 18,6%->-16,7%, 41/48 janelas negativas
(eram 2), pior DD -52,8%->-95,4%, pior 12m -43,9%->-88,9%, so bate o IBOV em
10/48 janelas (eram 48/48). FULL (2010-2026): R$100 -> R$1.368,01
(liquid_focus) vira R$100 -> R$10,11 (CAGR -12,9%, MaxDD -95,7%) -- quase
zerado. Nao promovido.
"""
from __future__ import annotations

from core.indicators import ifr, sma
from strategy.liquid_sleeve import LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5


class LiquidSleeveFearVolume(LiquidSleeve):
    """`LiquidSleeve` com o RANKING trocado de momentum 12-1 para
    medo (IFR baixo) confirmado por agressao (volume alto). Ver docstring
    do modulo para a hipotese; o gate de dip e tudo mais fica igual."""

    name = "liquid_sleeve_fear_volume"
    version = "1.0"
    candidate = False  # peca de composicao, mesma razao de LiquidSleeve

    def __init__(
        self,
        ifr_window: int = 14,
        ifr_oversold: float = 40.0,
        volume_window: int = 20,
        volume_min_ratio: float = 1.3,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.ifr_window = ifr_window
        self.ifr_oversold = ifr_oversold
        self.volume_window = volume_window
        self.volume_min_ratio = volume_min_ratio

    def initialize(self, panels, ibov) -> None:
        # `super().initialize` monta momentum/dip/elegibilidade normalmente
        # -- so SUBSTITUIMOS `_scores` (a regua de ranking) pelo composto de
        # medo+agressao, reaplicando a MESMA mascara de elegibilidade
        # (universo/sleeve) que `LiquidSleeve` ja calculou em `_eligible`.
        super().initialize(panels, ibov)
        for t, df in panels.items():
            if t not in self._eligible.columns or "volume" not in df.columns:
                continue
            medo = (self.ifr_oversold - ifr(df["close"], self.ifr_window)).clip(lower=0.0)
            volume_ratio = df["volume"] / sma(df["volume"], self.volume_window)
            agressao = (volume_ratio - self.volume_min_ratio).clip(lower=0.0)
            # Zero (nao NaN) quando falta uma das duas condicoes -- vira NaN
            # so no passo seguinte, pra nao rankear um candidato sem
            # capitulacao real so porque nenhum outro teve capitulacao hoje.
            capitulacao = (medo * agressao).replace(0.0, float("nan"))
            self._raw_scores[t] = capitulacao
            mask = self._eligible[t].reindex(capitulacao.index).fillna(False)
            self._scores[t] = capitulacao.where(mask)


class LiquidFocusFearVolume(LiquidSleeves5):
    """`LiquidSleeves5` (default 1 posicao, como `LiquidFocus`) ranqueando
    por medo+volume em vez de momentum. Ver docstring do modulo."""

    name = "liquid_focus_fear_volume"
    version = "1.0"
    candidate = False

    def __init__(
        self,
        sleeve_count: int = 1,
        ifr_window: int = 14,
        ifr_oversold: float = 40.0,
        volume_window: int = 20,
        volume_min_ratio: float = 1.3,
        **kwargs,
    ):
        # Guardado ANTES do super().__init__ porque `LiquidSleeves5.__init__`
        # chama `_make_sleeve` internamente -- precisa existir a tempo.
        self._fv_kwargs = dict(
            ifr_window=ifr_window, ifr_oversold=ifr_oversold,
            volume_window=volume_window, volume_min_ratio=volume_min_ratio,
        )
        super().__init__(sleeve_count=sleeve_count, **kwargs)

    def _make_sleeve(self, **kwargs) -> LiquidSleeve:
        return LiquidSleeveFearVolume(**kwargs, **self._fv_kwargs)
