"""hip_05 — RiskCappedWithStop: mesmo orcamento de risco do hip_04, mas com
stop ATR EXPLICITO — o risco de 2% por posicao passa a ser real, nao teorico.

Mecanismo
---------
Identico a hip_04 (peso ~ 2% / (3*ATR%), teto 40%, sobra fica em caixa), com
UMA diferenca: a entrada leva `initial_stop = close[D] * (1 - 3*ATR%)`, um
stop de fato registrado no engine. Em hip_04 o "orcamento de risco" e so
aritmetica de tamanho — nada impede o papel de cair 10 ATRs se o robo nao
rotacionar a tempo. Aqui o stop FECHA a posicao se o preco cair `k_atr` ATRs,
tornando o "2% de risco por trade" uma promessa que o engine cumpre, nao uma
suposicao do dimensionamento.

Razao a priori
---------------
Dimensionar pelo risco sem um stop que materialize esse risco e so metade do
mecanismo — o tamanho da posicao promete uma perda maxima que nada garante.
Somar o stop ATR ao dimensionamento ATR fecha o ciclo: agora o "teto de risco
por posicao" do foco da familia e literal (perda maxima aproximada = orcamento
de risco), nao apenas uma esperanca de que a rotacao mensal saia a tempo. O
contraste com hip_04 isola exatamente esse efeito: mesmo tamanho, com e sem
enforcement — se o stop nao mudar nada, o mecanismo de rotacao mensal ja
estava suficientemente rapido; se mudar (para melhor ou pior), o enforcement
importa.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[3])
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from strategy.lab.risk_targeting._common import RiskTargetingDip

RISK_BUDGET_PCT = 0.02
K_ATR = 3.0
MAX_WEIGHT_PER_SLOT = 0.40


class RiskCappedWithStop(RiskTargetingDip):
    name = "risk_targeting_05"
    version = "1.0"
    candidate = False

    def _weights_for(self, entering, date, open_positions):
        raw = {}
        for t in entering:
            a = self._safe(self._atr_pct, t, date)
            if a is None or a <= 1e-6:
                continue
            stop_dist_pct = K_ATR * a
            w = RISK_BUDGET_PCT / stop_dist_pct
            raw[t] = min(w, MAX_WEIGHT_PER_SLOT)
        missing = [t for t in entering if t not in raw]
        if missing and raw:
            avg = sum(raw.values()) / len(raw)
            for t in missing:
                raw[t] = min(avg, MAX_WEIGHT_PER_SLOT)
        elif missing and not raw:
            for t in missing:
                raw[t] = MAX_WEIGHT_PER_SLOT
        total = sum(raw.values())
        if total > 1.0:
            raw = {t: w / total for t, w in raw.items()}
        return raw

    def _stop_price_for(self, ticker, date):
        a = self._safe(self._atr_pct, ticker, date)
        if a is None:
            return None
        # Preco de referencia: close[D] (aproximacao da execucao em open[D+1],
        # que o robo ainda nao ve nesta chamada — mesma aproximacao usada em
        # todo o resto do sinal desta familia, ex. `_dist_from_high`).
        close_val = self._safe(self._close, ticker, date)
        if close_val is None:
            return None
        return close_val * (1.0 - K_ATR * a)

    def initialize(self, panels, ibov):
        super().initialize(panels, ibov)
        self._close = {t: df["close"] for t, df in panels.items()}


if __name__ == "__main__":
    import sys as _s
    _s.path.insert(0, "src")
    _s.path.insert(0, "scripts")
    from swing_lab.measure import screen

    r = screen(
        lambda: RiskCappedWithStop(),
        name="risk_targeting_05",
        family="risk_targeting",
        note="hip_04 + stop explicito a 3*ATR% do close[D] (risco enforced)",
    )
    print(r)
