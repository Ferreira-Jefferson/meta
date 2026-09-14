"""relval/hip_02 -- Rotacao long-only por valor relativo entre DUAS acoes do
mesmo setor (par cointegrado), SEM nunca vender a descoberto e SEM nunca
ficar em caixa: 100% do capital sempre em UMA das duas pontas, trocando de
perna quando o z-score do spread cruza um limiar.

Contexto (ANTES de medir este arquivo)
---------------------------------------
`strategy/lab/relative_value/hip_01_pairs_cross_sectional.py` ja testou uma
ideia adjacente -- comprar o maior "laggard" (z-score de RETORNO, nao de
SPREAD) contra um GRUPO inteiro de liquidez (top-20) -- e foi REFUTADA
(CATASTROFICA a capital real: holdout 0/48 janelas positivas, FULL R$100 ->
R$1,39). A hipotese aqui e mecanicamente diferente em tres pontos: (1) par
FIXO de 2 ativos, nao um grupo de 20 -- o "ruido do ranking" que inflou o giro
da hip_01 nao existe aqui por construcao; (2) sinal e' o SPREAD cointegrado
(preco relativo, beta OLS rolante), nao o retorno bruto -- e o racional
classico de pairs trading e' sobre o SPREAD, nao sobre quem "ficou pra tras"
em retorno; (3) o par e' escolhido por triagem de cointegracao explicita
(half-life de reversao do spread), nao herdado do universo de liquidez do
robo composto. Ainda assim, o precedente da hip_01 pesa contra: a familia
"comprar o que ficou mais barato relativo a uma referencia, sem operar o lado
vendido" ja perdeu uma vez feio a capital real -- este arquivo tem a barra
de prova alta.

Dado que NAO existe no repo (declarado, nao contornado com proxy)
-------------------------------------------------------------------
Nao ha teste formal de cointegracao (Engle-Granger/Johansen com p-valor) --
`statsmodels` nao esta instalado e o AGENTS.md proibe adicionar dependencia
sem justificativa forte para um script de laboratorio. Substituido por um
proxy honesto e mais fraco: beta OLS estatico (formula fechada,
cov/var, sem biblioteca) + regressao AR(1) do spread (tambem formula fechada)
para estimar velocidade de reversao (half-life) e o coeficiente b (b<0 e
sinal necessario de reversao, NAO suficiente -- sem p-valor de ADF nao da
para afirmar estacionariedade com confianca estatistica). Se a hipotese
sobreviver ao teste pequeno, a proxima medida objetiva seria rodar um ADF de
verdade (instalar `statsmodels` so nesse ponto, com justificativa).

Metodo
------
1. Triagem (cara, mas so aritmetica -- nao e' "gastar maquina"): AR(1) do
   spread log-log para todo par dentre {CMIG4, ITSA4, BRAP4, CPLE3, TAEE11,
   EQTL3} -- substitutos de TRPL4 (deslistada/renomeada, sem dado no
   yfinance sob esse ticker -- 0 barras baixadas em 2026-09-11) dentro do
   mesmo agrupamento "estatal/blue-chip de preco baixo" que o dono pediu.
2. TESTE PEQUENO PRIMEIRO: backtest de 2 anos (2023-2025) na melhor dupla,
   pequena grade de geometria (2 janelas de beta x 2 limiares de z) via
   ProcessPoolExecutor.
3. So expande pra FULL (2010-2026) se o teste pequeno nao refutar de cara.
4. Metrica padrao: liquido R$, win% + Wilson 95% contra breakeven empirico,
   trades, stops, MaxDD%, fracao de MESES positivos, capital usado, dias sem
   posicao (censura -- aqui e' o tempo em caixa parado no arranque, ja que a
   estrategia nunca vende sem comprar o outro lado).

Sem look-ahead: o sinal (`_z`) so usa `rolling(...)` fechado no proprio dia
`t`; a decisao de `on_bar(date=t)` vira `Enter`/`Exit` enfileirados pelo
engine e so executam no `open[t+1]` (contrato de `strategy/base.py`).
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from backtest.metrics import max_drawdown
from backtest.runner import run as run_bt
from core.config import BacktestConfig
from core.models import ExitReason
from market_data.loader import load_one
from strategy.base import Action, Enter, Exit, OpenPosition, Strategy

DIR_E = ROOT / "data" / "wide_e"
SELIC_E = str(DIR_E / "selic.parquet")
INITIAL = 1000.0
OUT = ROOT / "scripts" / "swing_lab" / "relval_pair_rotation_2026_09_11.json"

CANDIDATES = ("CMIG4.SA", "ITSA4.SA", "BRAP4.SA", "CPLE3.SA", "TAEE11.SA", "EQTL3.SA")
FULL_START, FULL_END = "2010-01-04", "2026-08-20"
SMALL_START, SMALL_END = "2023-01-02", "2025-01-02"  # teste pequeno: 2 anos recentes


def _panel(ticker: str) -> pd.DataFrame:
    return load_one(ticker, out_dir=DIR_E)


# ----------------------------------------------------------------- triagem
def _ols_beta(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """beta, alpha de x = alpha + beta*y (OLS fechado, sem statsmodels)."""
    vy = y.var()
    beta = float(x.cov(y) / vy) if vy > 0 else 0.0
    alpha = float(x.mean() - beta * y.mean())
    return beta, alpha


def _ar1_halflife(spread: pd.Series) -> tuple[float, float]:
    """AR(1) fechado: d(spread) = a + b*spread_{t-1} + e. Devolve (b, half_life_dias).

    b<0 = reversao (necessario, nao suficiente -- sem ADF nao prova
    estacionariedade). half_life = -ln(2)/b, em pregoes.
    """
    s = spread.dropna()
    lag = s.shift(1).dropna()
    d = s.diff().dropna()
    idx = lag.index.intersection(d.index)
    lag, d = lag.loc[idx], d.loc[idx]
    b, _a = _ols_beta(d, lag)
    hl = float(-np.log(2) / b) if b < 0 else float("inf")
    return b, hl


def screen_pairs() -> list[dict]:
    logs = {}
    for t in CANDIDATES:
        df = _panel(t)
        logs[t] = np.log(df["adj_close"])
    rows = []
    for a, b in combinations(CANDIDATES, 2):
        la, lb = logs[a].align(logs[b], join="inner")
        if len(la) < 500:
            continue
        beta, alpha = _ols_beta(la, lb)
        spread = la - alpha - beta * lb
        bcoef, hl = _ar1_halflife(spread)
        ret_corr = float(la.diff().corr(lb.diff()))
        rows.append({
            "par": f"{a}-{b}", "a": a, "b": b, "beta": beta,
            "ar1_b": bcoef, "half_life_dias": hl, "corr_retornos": ret_corr,
            "n": len(la),
        })
    rows.sort(key=lambda r: (r["half_life_dias"] if r["half_life_dias"] > 0 else 1e9))
    return rows


# ----------------------------------------------------------------- strategy
class PairRotationLab(Strategy):
    """Sempre 100% investido numa das duas pontas de um par cointegrado.

    z > z_entry  -> `ticker_a` ficou CARO relativo a `ticker_b` -> roda pra B.
    z < -z_entry -> `ticker_b` ficou CARO relativo a `ticker_a` -> roda pra A.
    |z| <= z_entry -> mantem a perna atual (histerese -- sem isso o robo
    trocaria de lado toda vez que o z tocasse zero, giro que ja matou a
    hip_01 cross-sectional).
    """

    name = "relval_pair_rotation_lab"
    version = "1.0"
    candidate = False  # experimento de scripts/, nao disputa podio

    def __init__(self, ticker_a: str, ticker_b: str, beta_window: int = 120,
                 z_window: int = 60, z_entry: float = 1.0, **kwargs):
        self.ticker_a = ticker_a
        self.ticker_b = ticker_b
        self.beta_window = beta_window
        self.z_window = z_window
        self.z_entry = z_entry
        self.universe_tickers = (ticker_a, ticker_b)
        self._z: pd.Series | None = None

    def initialize(self, panels, ibov) -> None:
        a = np.log(panels[self.ticker_a]["adj_close"])
        b = np.log(panels[self.ticker_b]["adj_close"])
        a, b = a.align(b, join="inner")
        # beta ROLANTE (formula fechada, fecha no proprio dia t -- sem
        # look-ahead: `rolling(w)` so usa [t-w+1, t]).
        cov = a.rolling(self.beta_window).cov(b)
        var = b.rolling(self.beta_window).var()
        beta = (cov / var).replace([np.inf, -np.inf], np.nan)
        spread = a - beta * b
        mu = spread.rolling(self.z_window).mean()
        sd = spread.rolling(self.z_window).std()
        self._z = ((spread - mu) / sd).dropna()

    def on_bar(self, date: pd.Timestamp, open_positions: dict[str, OpenPosition],
               cash_available: float) -> list[Action]:
        if self._z is None or date not in self._z.index:
            return []
        z = float(self._z.loc[date])
        if not np.isfinite(z):
            return []
        held = next(iter(open_positions), None)
        if z > self.z_entry:
            target = self.ticker_b
        elif z < -self.z_entry:
            target = self.ticker_a
        else:
            target = held
        if target is None or target == held:
            return []
        actions: list[Action] = []
        if held is not None:
            actions.append(Exit(ticker=held, reason=ExitReason.ROTATION_OUT))
        actions.append(Enter(ticker=target, size_hint=1.0, reason="relval_rotation"))
        return actions


# ------------------------------------------------------------------ medicao
def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    phat = k / n
    denom = 1.0 + z * z / n
    center = phat + z * z / (2 * n)
    adj = z * np.sqrt(phat * (1.0 - phat) / n + z * z / (4 * n * n))
    return float((center - adj) / denom), float((center + adj) / denom)


@dataclass
class Cell:
    ticker_a: str
    ticker_b: str
    beta_window: int
    z_window: int
    z_entry: float
    start: str
    end: str


def _cfg() -> BacktestConfig:
    return BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC_E)


def run_cell(cell: Cell) -> dict:
    panels = {t: _panel(t) for t in (cell.ticker_a, cell.ticker_b)}
    panels["^BVSP"] = _panel("^BVSP")
    strat = PairRotationLab(cell.ticker_a, cell.ticker_b, beta_window=cell.beta_window,
                             z_window=cell.z_window, z_entry=cell.z_entry)
    r = run_bt(panels, strat, _cfg(), start=cell.start, end=cell.end)
    eq = r.equity_curve
    if len(eq) < 30:
        return {"cell": vars(cell), "erro": "janela curta demais / sem dado"}

    closed = [t for t in r.trades if t.exit_price is not None]
    pnls = [float(t.pnl_brl) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    n = len(pnls)
    nwin = len(wins)
    win_pct = nwin / n if n else float("nan")
    lo, hi = _wilson_ci(nwin, n) if n else (float("nan"), float("nan"))
    ganho_medio = float(np.mean(wins)) if wins else 0.0
    perda_media = float(-np.mean(losses)) if losses else 0.0
    breakeven_emp = (perda_media / (ganho_medio + perda_media)
                      if (ganho_medio + perda_media) > 0 else float("nan"))
    n_stops = sum(1 for t in closed if t.exit_reason == ExitReason.STOP)

    liquido = float(eq.iloc[-1] - eq.iloc[0])
    dd = float(max_drawdown(eq))

    # meses positivos (retorno mes a mes da curva de patrimonio)
    monthly = eq.resample("ME").last().pct_change().dropna()
    pct_meses_pos = float((monthly > 0).mean()) if len(monthly) else float("nan")

    # dias sem posicao aberta (proxy de "censura": caixa parado, so pode
    # acontecer no arranque antes do primeiro sinal valido, ja que depois
    # disso a estrategia SEMPRE roda pra algum lado, nunca zera as duas).
    dias_com_posicao = 0
    intervalos = [(pd.Timestamp(t.entry_date), pd.Timestamp(t.exit_date) if t.exit_date
                   else eq.index[-1]) for t in r.trades]
    for d in eq.index:
        if any(ini <= d <= fim for ini, fim in intervalos):
            dias_com_posicao += 1
    dias_sem_posicao = len(eq.index) - dias_com_posicao

    return {
        "cell": vars(cell),
        "liquido_brl": liquido,
        "capital_final": float(eq.iloc[-1]),
        "trades": n,
        "n_stops": n_stops,
        "win_pct": win_pct,
        "wilson95": [lo, hi],
        "breakeven_empirico": breakeven_emp,
        "ganho_medio": ganho_medio,
        "perda_media": perda_media,
        "max_dd_pct": dd,
        "pct_meses_positivos": pct_meses_pos,
        "n_meses": len(monthly),
        "dias_sem_posicao": int(dias_sem_posicao),
        "dias_total": len(eq.index),
        "capital_usado": float(INITIAL),
    }


def _fmt(r: dict) -> str:
    if "erro" in r:
        return f"{r['cell']} -- ERRO: {r['erro']}"
    c = r["cell"]
    return (f"{c['ticker_a']:<10}{c['ticker_b']:<10}bw={c['beta_window']:<5}"
            f"zw={c['z_window']:<5}z={c['z_entry']:<5}"
            f"liq=R${r['liquido_brl']:>10,.2f}  trades={r['trades']:>4}  "
            f"stops={r['n_stops']:>3}  win%={r['win_pct']*100 if r['trades'] else float('nan'):>6.2f}  "
            f"IC95=[{r['wilson95'][0]*100:>5.2f};{r['wilson95'][1]*100:>5.2f}]  "
            f"be_emp={r['breakeven_empirico']*100 if np.isfinite(r['breakeven_empirico']) else float('nan'):>6.2f}  "
            f"MaxDD={r['max_dd_pct']*100:>6.2f}%  mesesPos={r['pct_meses_positivos']*100 if r['n_meses'] else float('nan'):>6.2f}%"
            f"  diasSemPos={r['dias_sem_posicao']}/{r['dias_total']}")


def main() -> None:
    print("=" * 100)
    print("TRIAGEM: half-life de reversao do spread log-log (AR(1) fechado, sem ADF formal)")
    print("=" * 100)
    tri = screen_pairs()
    for row in tri:
        print(f"{row['par']:<24} beta={row['beta']:>7.3f}  AR1_b={row['ar1_b']:>8.5f}  "
              f"half_life={row['half_life_dias']:>8.1f} pregoes  corr_ret={row['corr_retornos']:>6.3f}  n={row['n']}")

    melhor = tri[0]
    print(f"\nmelhor par por half-life: {melhor['par']} ({melhor['half_life_dias']:.1f} pregoes)")

    a, b = melhor["a"], melhor["b"]
    top3 = tri[:3]

    print("\n" + "=" * 100)
    print(f"TESTE PEQUENO ({SMALL_START} a {SMALL_END}) -- top-3 pares x pequena grade de geometria")
    print("=" * 100)
    cells = []
    for row in top3:
        for bw in (60, 120):
            for zw in (40, 60):
                for ze in (0.75, 1.0, 1.5):
                    cells.append(Cell(row["a"], row["b"], bw, zw, ze, SMALL_START, SMALL_END))

    results_small = []
    with ProcessPoolExecutor() as ex:
        futs = {ex.submit(run_cell, c): c for c in cells}
        for fut in as_completed(futs):
            res = fut.result()
            print(_fmt(res), flush=True)
            results_small.append(res)

    ok_small = [r for r in results_small if "erro" not in r and r["trades"] >= 3]
    ok_small.sort(key=lambda r: r["liquido_brl"], reverse=True)

    print("\ntop-5 do teste pequeno por liquido:")
    for r in ok_small[:5]:
        print(_fmt(r))

    survives_small = any(
        r["liquido_brl"] > 0 and np.isfinite(r["breakeven_empirico"])
        and r["wilson95"][0] > r["breakeven_empirico"]
        for r in ok_small
    )

    saida = {"triagem": tri, "teste_pequeno": results_small, "survives_small": survives_small}

    if not survives_small:
        print("\nNENHUMA celula do teste pequeno teve IC95(win%) inteiramente ACIMA do "
              "breakeven empirico com liquido positivo -- nao expande para a janela FULL.")
        OUT.write_text(json.dumps(saida, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return

    print("\n" + "=" * 100)
    print(f"JANELA FULL ({FULL_START} a {FULL_END}) -- so a melhor geometria do teste pequeno")
    print("=" * 100)
    melhor_cell_dict = max(ok_small, key=lambda r: r["liquido_brl"])["cell"]
    full_cells = [Cell(melhor_cell_dict["ticker_a"], melhor_cell_dict["ticker_b"],
                        melhor_cell_dict["beta_window"], melhor_cell_dict["z_window"],
                        melhor_cell_dict["z_entry"], FULL_START, FULL_END)]
    # tambem roda a mesma geometria nas OUTRAS 2 duplas do top-3, pra nao
    # promover so por causa do par -- e um controle de robustez do par, nao so da janela.
    for row in top3:
        if row["a"] == melhor_cell_dict["ticker_a"] and row["b"] == melhor_cell_dict["ticker_b"]:
            continue
        full_cells.append(Cell(row["a"], row["b"], melhor_cell_dict["beta_window"],
                                melhor_cell_dict["z_window"], melhor_cell_dict["z_entry"],
                                FULL_START, FULL_END))

    results_full = []
    with ProcessPoolExecutor() as ex:
        futs = {ex.submit(run_cell, c): c for c in full_cells}
        for fut in as_completed(futs):
            res = fut.result()
            print(_fmt(res), flush=True)
            results_full.append(res)

    saida["teste_full"] = results_full
    OUT.write_text(json.dumps(saida, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nresultado salvo em {OUT}")


if __name__ == "__main__":
    main()
