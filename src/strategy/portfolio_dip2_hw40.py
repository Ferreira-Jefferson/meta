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
    # APOSENTADO do ranking em 2026-08-20. Nao foi refutado por desempenho — foi
    # descoberto que o desempenho nao era dele. A `WATCHLIST` de sete tickers que
    # ele opera foi escolhida em 2026 maximizando o capital de 2010-2026, entao o
    # capital final que o punha em primeiro lugar e a resposta copiada do
    # gabarito. `scripts/run_walk_forward.py` refez a selecao so com dado passado
    # e o CAGR caiu de ~36% para 17,1% / -4,2% / 18,3%;
    # `scripts/run_holdout_frozen.py` mostrou 57,4% de CAGR mediano justamente
    # nas 48 janelas MAIS contaminadas, com 6 trades — assinatura de look-ahead.
    # Some-se a isso a capacidade: EMAE4 gira R$ 141 mil/dia e ele satura o papel
    # a partir de ~R$ 70 mil.
    #
    # A classe CONTINUA aqui e continua sendo a base de toda a familia
    # (`liquid_sleeve.py` herda dela): as regras de sinal — momentum 12-1, dip
    # 2%, histerese 15%, gate de Selic — nunca foram o problema. O problema era
    # de onde ele escolhia. O sucessor e `strategy/liquid_champion.py`.
    candidate = False

    satellite_pct: float = 0.00

    # Ficha: sem satelites, 100% na posicao principal (ver base.py).
    sizing_rules = (
        "Sem satélites: 100% do capital vai para a posição principal. A geração "
        "anterior deixava 5% para trás em cada rotação; aqui não sobra ponta.",
    ) + PortfolioHysteresis.sizing_rules[1:]

    def __init__(self, **kwargs):
        kwargs.setdefault("confirm_months", 2)
        kwargs.setdefault("redist_mode", "pool")
        kwargs.setdefault("dip_pct", 0.02)
        kwargs.setdefault("high_window", 40)
        super().__init__(**kwargs)
        self.satellite_pct = 0.00
