"""DipTop1Portfolio — histerese com dip_pct=2% e high_window=40, sem satelites.

Vencedor da busca de 2026-08-15 (W3):
  FULL: R$170.821 / CAGR 36,29% / Sharpe 0,87 / MaxDD -35,12% / NegYrs 1.
  vs portfolio_hysteresis (antigo TOP-1): +R$36.418 (+27,1%) com apenas +2,1 p.p. de MaxDD.

Diferencas vs portfolio_hysteresis:
  dip_pct:       1% -> 2%   (mais seletivo — exige queda maior antes de entrar)
  high_window:   20 -> 40   (janela do rolling max mais longa)
  satellite_pct:  5% -> 0%  (sem satelites — 100% do capital na posicao principal)
"""
from __future__ import annotations
from strategy.portfolio_satellite import PortfolioHysteresis


class DipTop1Portfolio(PortfolioHysteresis):
    """Hysteresis com dip 2%, janela 40 pregoes, sem satelites."""
    name = "portfolio_dip2_hw40"
    version = "1.0"
    candidate = True  # reafirma participacao no ranking (classes-base ancestrais optaram por candidate=False)

    satellite_pct: float = 0.00

    def __init__(self, **kwargs):
        kwargs.setdefault("confirm_months", 2)
        kwargs.setdefault("redist_mode", "pool")
        kwargs.setdefault("dip_pct", 0.02)
        kwargs.setdefault("high_window", 40)
        super().__init__(**kwargs)
        self.satellite_pct = 0.00
