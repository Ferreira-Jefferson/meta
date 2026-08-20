from __future__ import annotations

from pathlib import Path

import pandas as pd

from core.config import CostModel


def cash_yield_series(path: str | None, index: pd.DatetimeIndex) -> pd.Series | None:
    """Taxa DIARIA de remuneracao do caixa, alinhada ao calendario do backtest.

    Por que isto passou 16 anos faltando
    ------------------------------------
    O engine movimenta caixa em dezenas de pontos e nunca remunerou nenhum. No
    Brasil isso nao e arredondamento: o robo campeao fica 24% do tempo com o
    caixa parado e o `liquid_flow5` fica 32%, com a Selic media do periodo em
    9,48% a.a. Pior, o vies nao e neutro — ele cai TODO em cima das variantes
    defensivas, que por definicao seguram mais caixa, e o gate de Selic sai para
    o caixa exatamente quando a Selic esta subindo, ou seja, quando o caixa
    renderia mais. Toda conclusao do tipo "filtro defensivo nao compensa" foi
    tirada cobrando 0% de um dinheiro que renderia.

    `None` (default de `BacktestConfig.cash_yield_path`) mantem o comportamento
    antigo byte-a-byte — o diario tem 16 anos de runs gravadas com caixa a 0% e
    mudar o default aqui reescreveria o significado de todas elas de uma vez.

    O parquet do BCB traz `valor` em PERCENTUAL AO DIA (0,0376 = 0,0376%/dia,
    ~9,5% a.a.), nao ao ano — a mesma convencao que `strategy/buy_the_dip.py`
    usa no detector de aperto monetario e que `backtest/withdrawal.py` documenta.
    """
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    raw = pd.read_parquet(p)["valor"].astype(float) / 100.0
    return raw.reindex(index.union(raw.index)).ffill().reindex(index).fillna(0.0)


def apply_slippage(price: float, side: str, model: CostModel) -> float:
    """Ajusta o preço pela slippage estimada. Compra sobe, venda desce."""
    factor = 1.0 + model.slippage_pct if side == "buy" else 1.0 - model.slippage_pct
    return price * factor


def fees_for_leg(gross: float, model: CostModel) -> float:
    return gross * model.per_side_pct
