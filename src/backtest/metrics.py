from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0 or total_return <= 0:
        return 0.0
    return total_return ** (1.0 / years) - 1.0


def period_return(equity: pd.Series, min_years_to_annualize: float = 1.0) -> float:
    """`cagr(equity)` se o periodo cobrir pelo menos `min_years_to_annualize`
    anos, senao o retorno TOTAL do periodo (sem anualizar).

    Anualizar (elevar o retorno a `1/anos`) so' faz sentido com uma
    quantidade de dado da ORDEM DE UM ANO -- com menos, o expoente e' > 1 e
    AMPLIFICA o retorno do periodo em vez de estima-lo (67 dias = 0,18 anos
    -> expoente 5,46; um retorno de 3x no periodo vira "39.805% ao ano", que
    ninguem vai realmente repetir 5,46 vezes seguidas). Medido no day trade
    (`GremahTick`, PMAM3, 2026-08-22): um OOS de 67 dias com capital real de
    R$100 dava CAGR de dezenas de milhares de %, sem erro nenhum na conta --
    so' a pergunta errada pro dado que se tem. Existe como funcao SEPARADA
    de `cagr()` (nao um parametro nela) porque o ranking diario/portfolio
    (`backtest/engine.py`, `engine_portfolio.py`, `engine_satellite.py`) roda
    em janelas de anos de verdade (FULL/5Y/3Y/1Y) onde anualizar e' exatamente
    a conta certa -- so' o motor intradiario (janelas de semanas/meses por
    natureza do split IS/OOS) precisa deste fallback."""
    if len(equity) < 2:
        return 0.0
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0 or total_return <= 0:
        return 0.0
    if years < min_years_to_annualize:
        return total_return - 1.0
    return total_return ** (1.0 / years) - 1.0


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def sharpe(equity: pd.Series, rf_annual: float = 0.10) -> float:
    ret = equity.pct_change().dropna()
    if ret.std() == 0 or len(ret) == 0:
        return 0.0
    daily_rf = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    excess = ret - daily_rf
    return float(excess.mean() / excess.std() * math.sqrt(TRADING_DAYS))


def sortino(equity: pd.Series, rf_annual: float = 0.10) -> float:
    ret = equity.pct_change().dropna()
    if len(ret) == 0:
        return 0.0
    daily_rf = (1.0 + rf_annual) ** (1.0 / TRADING_DAYS) - 1.0
    excess = ret - daily_rf
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return float(excess.mean() / downside.std() * math.sqrt(TRADING_DAYS))


def calmar(equity: pd.Series, min_years_to_annualize: float | None = None) -> float:
    """`min_years_to_annualize=None` (default, todo chamador existente):
    usa `cagr()` sem ressalva -- comportamento antigo intacto. Um valor
    numerico troca para `period_return()` (ver a docstring la para o
    motivo) -- so' o motor intradiario passa isso."""
    c = cagr(equity) if min_years_to_annualize is None else period_return(equity, min_years_to_annualize)
    dd = abs(max_drawdown(equity))
    return c / dd if dd > 0 else 0.0


def negative_years(equity: pd.Series) -> int:
    """Conta anos-calendário com retorno negativo (primeiro vs último valor do ano).

    Critério usado nos experimentos de ranking (NegYrs) — ver scripts/run_confirm_final_winners.py.
    """
    if len(equity) < 2:
        return 0
    yearly = equity.resample("YE").agg(["first", "last"])
    ret = yearly["last"] / yearly["first"] - 1.0
    return int((ret < 0).sum())


def trade_stats(pnls: Iterable[float]) -> dict[str, float]:
    arr = np.array(list(pnls), dtype=float)
    if len(arr) == 0:
        return {"win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0}
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    win_rate = len(wins) / len(arr)
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    expectancy = float(arr.mean())
    return {"win_rate": win_rate, "profit_factor": profit_factor, "expectancy": expectancy}

def irr_annual(flows: list[tuple[object, float]], tol: float = 1e-7) -> float:
    """Taxa interna de retorno ANUAL de uma serie de fluxos datados.

    `flows` = [(data, valor)], valor NEGATIVO para dinheiro que entra na conta
    (aporte, capital inicial) e POSITIVO para o resgate final. E a unica medida
    de retorno honesta quando ha aporte: `cagr` sobre a curva de patrimonio
    contaria dinheiro novo como se fosse rendimento, e a curva de COTA responde
    outra pergunta (quanto o gestor rendeu, nao quanto o dono ganhou).

    Bisseccao em vez de Newton: o intervalo [-0,99, +10] cobre qualquer
    resultado plausivel de uma conta de acoes e nao depende de derivada nem de
    palpite inicial, que e onde Newton falha em fluxo com muitos sinais.
    Devolve `nan` quando nao ha troca de sinal (fluxo sem solucao).
    """
    if len(flows) < 2:
        return float("nan")
    t0 = min(d for d, _ in flows)
    anos = [((d - t0).days / 365.25) for d, _ in flows]
    vals = [v for _, v in flows]

    def vpl(r: float) -> float:
        return sum(v / ((1.0 + r) ** a) for v, a in zip(vals, anos))

    lo, hi = -0.9899, 10.0
    f_lo, f_hi = vpl(lo), vpl(hi)
    if f_lo * f_hi > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = vpl(mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0
