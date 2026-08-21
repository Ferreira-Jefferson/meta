"""relative_value/hip_01 -- pairs trading generalizado pra N ativos: comprar
o papel que mais DIVERGIU do seu grupo de pares (z-score de retorno
relativo, nao absoluto) e' uma vantagem que nao dependa de pegar tendencia?

Contexto (medido 2026-08-21, ANTES deste arquivo)
----------------------------------------------------
Testados ate aqui: momentum absoluto (edge so na cauda, mediano perdedor
mesmo com 174 trades -- ver `fee_capacity/hip_01`), capitulacao (medo+
volume, REFUTADA 2x -- `market_nature/hip_01/hip_02`), baixa volatilidade
(nao resolve, pega os MESMOS outliers do momentum -- `quality_factor/
hip_01`). Pedido explicito do usuario: tentar valor relativo/pairs -- a
premissa classica de pairs trading e' que DISPERSAO entre ativos
correlacionados (do mesmo grupo/setor) e' mais frequente e mais estrutural
que "pegar uma tendencia rara" -- reversao de spread acontece com
regularidade estatistica, nao depende de uma pandemia ou privatizacao.

O engine de swing deste repo e' LONG-ONLY (sem short -- `Enter` em
`strategy/base.py` nao tem lado, so ticker) -- pairs classico (comprar A,
vender B a descoberto) nao e' implementavel direto. Generalizacao usada
aqui: em vez de UM par fixo, calcula o retorno de `lookback` pregoes de
CADA ticker elegivel, tira o Z-SCORE TRANSVERSAL (cross-sectional) desse
retorno contra a MEDIA e DESVIO do grupo de pares elegivel NAQUELE DIA (o
universo top-20 por liquidez que ja' existe na familia) -- e compra o mais
NEGATIVO (o que mais ficou atras do grupo), apostando que a dispersao
fecha. Isso e' pairs trading contra o proprio grupo de liquidez, nao contra
um par fixo escolhido a dedo.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
Comprar o maior LAGGARD relativo ao grupo (nao o mais barato em termos
absolutos, nem o de maior momentum) deveria capturar reversao de dispersao
setorial/de grupo -- um fenomeno estatistico mais frequente que picos de
tendencia isolados -- sem precisar de um catalisador raro. Se a hipotese
estiver certa, isso deve aparecer como taxa de acerto/mediana de trade
MELHOR que momentum SEM depender de uma cauda extrema pra funcionar.

O que este arquivo NAO faz: nao muda o gate de dip, a histerese, o stop, o
gate de Selic, nem o universo -- so troca a REGUA de ranking de momentum
absoluto para z-score de retorno relativo ao grupo.

Risco declarado da aposta: um laggard pode estar atras do grupo por um
motivo real e permanente (empresa fundamentalmente mais fraca), nao por
ruido estatistico que reverte -- mesmo risco de "faca caindo" da
capitulacao, agora medido em termos RELATIVOS em vez de absolutos. Se a
hipotese estiver errada, isso deve aparecer como CAGR/taxa de acerto pior
que momentum no holdout completo, nao ser gratis.

`candidate = False`: mesma razao de toda a familia lab -- so disputa o
ranking automatico depois de julgado no holdout de 48 janelas + FULL.

RESULTADO (medido apos este arquivo) -- REFUTADA, PIOR RESULTADO ENTRE TODAS AS ALTERNATIVAS TESTADAS
------------------------------------------------------------------------------------------------------------
Escala grande (R$1.000, 5 sleeves, sem taxa): 405 trades (2,3x mais que
momentum -- o ranking por z-score e' mais ruidoso, troca de posicao com
muito mais frequencia), CAGR 3,8% (menos da metade do momentum, 10,1%),
mediana igualmente negativa (-0,9%) SEM a mesma cauda direita (media
+0,9% vs +4,0% do momentum) -- e ainda depende de outlier (BPAC11
+155,8%, mesma magnitude do que apareceu no momentum).

Capital real (R$100 + taxa fixa, 1 posicao): CATASTROFICO, o PIOR
resultado entre todas as 4 alternativas testadas nesta sessao (medo+
volume, medo+volume+saida rapida, baixa-vol, esta). Holdout: mediana
-48,5%, as 48 JANELAS negativas (nenhuma passa), NUNCA bate o IBOV (0/48).
FULL: R$100 -> R$1,39 (quase zerado, CAGR -22,7%). O giro mais alto
(mais trocas de posicao pelo ranking ruidoso) multiplicou o arrasto da
taxa fixa por ordem em vez de reduzir a dependencia de outliers. Nao
promovido.
"""
from __future__ import annotations

import pandas as pd

from strategy.liquid_sleeve import LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5


class LiquidSleeveRelativeValue(LiquidSleeve):
    """`LiquidSleeve` com o RANKING trocado de momentum absoluto para
    z-score de retorno RELATIVO ao grupo de pares elegivel (pairs trading
    generalizado). Ver docstring do modulo para a hipotese; o gate de dip
    e tudo mais fica igual."""

    name = "liquid_sleeve_relative_value"
    version = "1.0"
    candidate = False  # peca de composicao, mesma razao de LiquidSleeve

    def __init__(self, rv_lookback: int = 60, **kwargs):
        super().__init__(**kwargs)
        self.rv_lookback = rv_lookback

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)

        cols = list(self._eligible.columns)
        rets = {}
        for t in cols:
            if t not in panels or "close" not in panels[t].columns:
                continue
            rets[t] = panels[t]["close"].pct_change(self.rv_lookback)
        if not rets:
            return
        ret_df = pd.DataFrame(rets)

        elig = self._eligible.reindex(index=ret_df.index, columns=ret_df.columns).fillna(False)
        masked = ret_df.where(elig)
        media_grupo = masked.mean(axis=1)
        desvio_grupo = masked.std(axis=1)
        # z-score do retorno de CADA ticker contra a media/desvio do grupo
        # elegivel NAQUELE DIA -- negativo = ficou atras do grupo.
        z = ret_df.sub(media_grupo, axis=0).div(desvio_grupo, axis=0)
        score = -z  # score alto = ficou mais atras do grupo (candidato a reversao)

        for t in ret_df.columns:
            s = score[t]
            self._raw_scores[t] = s
            mask = self._eligible[t].reindex(s.index).fillna(False)
            self._scores[t] = s.where(mask)


class LiquidFocusRelativeValue(LiquidSleeves5):
    """`LiquidSleeves5` (default 1 posicao) ranqueando por reversao de
    dispersao relativa ao grupo em vez de momentum. Ver docstring do
    modulo."""

    name = "liquid_focus_relative_value"
    version = "1.0"
    candidate = False

    def __init__(self, sleeve_count: int = 1, rv_lookback: int = 60, **kwargs):
        self._rv_kwargs = dict(rv_lookback=rv_lookback)
        super().__init__(sleeve_count=sleeve_count, **kwargs)

    def _make_sleeve(self, **kwargs) -> LiquidSleeve:
        return LiquidSleeveRelativeValue(**kwargs, **self._rv_kwargs)
