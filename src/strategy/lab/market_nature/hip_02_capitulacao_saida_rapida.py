"""market_nature/hip_02 -- a mesma entrada por capitulacao (medo+volume) de
hip_01, mas com SAIDA RAPIDA por reversao, em vez da histerese lenta de
trend-following da familia -- resolve o motivo do fracasso?

Diagnostico (medido 2026-08-21, ANTES deste arquivo)
------------------------------------------------------
`liquid_focus_fear_volume` (hip_01 deste mesmo diretorio) foi refutado com
forca: 41/48 janelas negativas, FULL quase zera (R$100 -> R$10,11). O
mecanismo de saida da familia (`DipTop1Hysteresis`) so reavalia no FIM DO
MES e so sai por ROTATION_OUT (novo rank-1 15% melhor) ou STOP (-15%) -- os
DOIS desenhados para TREND-FOLLOWING (segurar o vencedor, deixar o sinal
decidir quando trocar). Uma entrada de CAPITULACAO e o oposto: a aposta e
que o papel reverte RAPIDO; segurar um mes inteiro (ou mais, se a
histerese nao achar substituto melhor) deixa a "faca caindo" continuar
caindo sem nenhum mecanismo de saida rapida alem do stop de -15%.

Hipotese a priori (declarada ANTES de medir este arquivo)
------------------------------------------------------------
A MESMA entrada (medo+volume de hip_01, sem mudar um numero) combinada com
uma saida que dispara TODO PREGAO (nao so no fim do mes) quando:
  (a) o IFR do papel NORMALIZA (volta a `ifr_recovery`, ex.: 50 -- a
      exaustao vendedora que justificou a entrada acabou, a razao de estar
      no trade nao existe mais, seja o resultado bom ou neutro); ou
  (b) `max_hold_bars` pregoes se passam sem (a) acontecer (a reversao
      esperada nao veio -- corta a perda de tempo/exposicao em vez de
      esperar o fim do mes ou um stop de -15% que pode nunca disparar numa
      queda lenta)
deve performar MUITO melhor que hip_01 combinado com a saida lenta -- nao
porque o SINAL de entrada mudou, mas porque a saida passa a bater com a
premissa da aposta (reversao rapida, nao segurar).

O que este arquivo NAO faz: nao muda a entrada (mesmo `_scores` de
medo+volume de `LiquidSleeveFearVolume`), nao muda o STOP de protecao
(continua -15%, automatico do engine), nao muda a cadencia de ENTRADA
(continua so em fim de mes, via `DipTop1Hysteresis.on_bar`) -- so acrescenta
uma saida antecipada, fora do calendario mensal, quando (a) ou (b) acontece.

Risco declarado da aposta: sair CEDO demais (IFR normaliza so um pouco, ou
o teto de dias e curto) pode cortar reversoes que ainda tinham mais corrida
-- se a hipotese estiver errada, isso deve aparecer como CAGR pior que
hip_01 (nao so "menos ruim"), ou pior que liquid_focus original, no
holdout completo -- nao ser gratis.

`candidate = False`: mesma razao de toda a familia lab -- so disputa o
ranking automatico depois de julgado no holdout de 48 janelas.

RESULTADO (holdout completo, 48 janelas + FULL, medido apos este arquivo) -- REFUTADA, e o DIAGNOSTICO ESTAVA ERRADO
-----------------------------------------------------------------------------------------------------------------------
Piorou em vez de melhorar: mediana de CAGR -16,7% (hip_01) -> -36,3%, 47/48
janelas negativas (eram 41/48), NUNCA MAIS bate o IBOV (0/48, eram 10/48),
pior DD -95,4% -> -99,6%. FULL praticamente igual (R$10,11 -> R$9,71) --
ainda quase zerado. O risco declarado ("sair cedo demais corta reversoes
que ainda tinham corrida") se confirmou, mas isso NAO era o problema
principal: cortar no teto de dias trava a perda no ponto errado, sem dar
tempo pro stop de -15% ou pra uma reversao organica funcionar.

Conclusao real: nao e a VELOCIDADE da saida que falha -- e a ENTRADA. Medo+
volume (comprar capitulacao) compra facas caindo que continuam caindo
neste mercado/periodo, independente de como/quando se sai. Os unicos
ganhos reais ja documentados nesta familia (WEGE3/Covid, CSNA3/commodity,
SBSP3/privatizacao -- ver `fee_capacity/hip_01_concentracao.py`) vieram de
MOMENTUM/tendencia, nao de reversao. Nao vale iterar mais em saidas para a
mesma entrada de capitulacao -- o problema esta na premissa da entrada.
"""
from __future__ import annotations

import pandas as pd

from core.models import ExitReason
from strategy.base import Exit
from strategy.lab.market_nature.hip_01_capitulacao_volume import LiquidSleeveFearVolume
from strategy.liquid_sleeve import LiquidSleeve
from strategy.liquid_sleeves5 import LiquidSleeves5


class LiquidSleeveFearVolumeFastExit(LiquidSleeveFearVolume):
    """`LiquidSleeveFearVolume` + saida antecipada por reversao de IFR ou
    teto de dias, checada TODO pregao (nao so no fim do mes). Ver docstring
    do modulo para a hipotese."""

    name = "liquid_sleeve_fear_volume_fast_exit"
    version = "1.0"
    candidate = False

    def __init__(self, ifr_recovery: float = 50.0, max_hold_bars: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.ifr_recovery = ifr_recovery
        self.max_hold_bars = max_hold_bars
        self._ifr_series: dict[str, pd.Series] = {}

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        from core.indicators import ifr
        for t, df in panels.items():
            self._ifr_series[t] = ifr(df["close"], self.ifr_window)

    def on_bar(self, date, open_positions, cash_available):
        for t, pos in open_positions.items():
            serie = self._ifr_series.get(t)
            atual = serie.loc[date] if serie is not None and date in serie.index else None
            reverteu = atual is not None and not pd.isna(atual) and float(atual) >= self.ifr_recovery
            venceu_prazo = pos.bars_held >= self.max_hold_bars
            if reverteu or venceu_prazo:
                razao = ExitReason.MEAN_REVERSION_DONE if reverteu else ExitReason.ROTATION_OUT
                return [Exit(ticker=t, reason=razao)]
        return super().on_bar(date, open_positions, cash_available)


class LiquidFocusFearVolumeFastExit(LiquidSleeves5):
    """`LiquidFocusFearVolume` (hip_01) + saida rapida por reversao/teto de
    dias (hip_02). Ver docstring do modulo."""

    name = "liquid_focus_fear_volume_fast_exit"
    version = "1.0"
    candidate = False

    def __init__(
        self,
        sleeve_count: int = 1,
        ifr_window: int = 14,
        ifr_oversold: float = 40.0,
        volume_window: int = 20,
        volume_min_ratio: float = 1.3,
        ifr_recovery: float = 50.0,
        max_hold_bars: int = 20,
        **kwargs,
    ):
        self._fv_kwargs = dict(
            ifr_window=ifr_window, ifr_oversold=ifr_oversold,
            volume_window=volume_window, volume_min_ratio=volume_min_ratio,
            ifr_recovery=ifr_recovery, max_hold_bars=max_hold_bars,
        )
        super().__init__(sleeve_count=sleeve_count, **kwargs)

    def _make_sleeve(self, **kwargs) -> LiquidSleeve:
        return LiquidSleeveFearVolumeFastExit(**kwargs, **self._fv_kwargs)
