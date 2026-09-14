"""EXPERIMENTO (nao promovido a strategy/): reversao cross-sectional semanal.

Hipotese (lote 2, brainstorm 2026-09-11): toda sexta-feira, ranquear o
retorno_5d de um universo amplo (POOL de `strategy/liquid_sleeve.py` menos os
3 ETFs) em decis; comprar em partes iguais o decil INFERIOR (pior retorno
relativo dos ultimos 5 pregoes) SOMENTE SE a mediana do retorno_5d do universo
estiver em [-2%, +2%] (filtro "mercado de lado", isolando o efeito
cross-sectional do efeito de mercado direcional). Manter 1 semana, rebalancear
toda sexta. Sem stop individual — so stop de PORTFOLIO de -6% sobre a fatia
alocada na semana.

Isto e um EXPERIMENTO, nao uma strategy/*.py de producao: a classe abaixo vive
so neste script (nenhum arquivo em strategy/ ou registry.py foi tocado).

Metodo (convencoes do projeto, nao negociaveis):
  - motor: backtest/engine.py (swing), capital R$1.000, lot_size=1
    (fracionario — decil de ~6 papeis com R$1.000 nao fecha lote de 100 em
    nenhum papel liquido da B3; ver `mt5_fractional_execution_2026_08_21` e
    `rico_fractional_fee_2026_08_21` na memoria do projeto). Custo fracionario
    real (R$1,90/ordem fixo) incluido explicitamente.
  - teste pequeno primeiro: ~3 meses (12-13 rebalances) antes de gastar a
    janela cheia.
  - metricas: liquido R$, win% com Wilson 95% contra o breakeven empirico,
    trades, STOPS de portfolio, MaxDD%, fracao de MESES positivos (convencao
    swing), capital usado, semanas sem posicao (censura, equivalente semanal
    de "pregoes sem trade").
  - sem look-ahead: decisao no close de sexta executa no open do proximo
    pregao (engine ja garante isso para Enter/Exit).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from backtest.engine import run_backtest
from core.config import BacktestConfig, CostModel
from core.models import ExitReason
from market_data.loader import load_universe
from strategy.base import Action, Enter, Exit, OpenPosition, Strategy

# POOL menos os 3 ETFs (BOVA11=indice, IMAB11=renda fixa, GOLD11=ouro) — o
# fator cross-sectional e sobre ACOES, nao sobre veiculos passivos que
# replicam o proprio benchmark ou outra classe de ativo.
from strategy.liquid_sleeve import POOL as _POOL_BRUTO

_ETFS_EXCLUIDOS = {"BOVA11.SA", "IMAB11.SA", "GOLD11.SA"}
UNIVERSE: tuple[str, ...] = tuple(t for t in _POOL_BRUTO if t not in _ETFS_EXCLUIDOS)


class ReversaoCrossSectionalSemanal(Strategy):
    """EXPERIMENTO — nao e robo de producao. Ver docstring do modulo."""

    name = "exp_reversao_cross_sectional_semanal"
    version = "0.1-experimento"
    universe_tickers = UNIVERSE

    def __init__(
        self,
        lookback_dias: int = 5,
        banda_mediana: float = 0.02,
        stop_portfolio_pct: float = 0.06,
        n_decis: int = 10,
        min_universo_valido: int = 20,
    ):
        self.lookback_dias = lookback_dias
        self.banda_mediana = banda_mediana
        self.stop_portfolio_pct = stop_portfolio_pct
        self.n_decis = n_decis
        self.min_universo_valido = min_universo_valido

        self._ret5: pd.DataFrame | None = None
        self._closes: pd.DataFrame | None = None
        self._basket_entry_value: float | None = None

        # Contadores para o relatorio (censura / diagnostico de eixo morto).
        self.semanas_com_entrada = 0
        self.semanas_filtro_mediana = 0
        self.semanas_universo_insuficiente = 0
        self.semanas_com_rebalance = 0
        self.stops_portfolio = 0
        self.medianas_observadas: list[float] = []

    def initialize(self, panels: dict[str, pd.DataFrame], ibov: pd.DataFrame) -> None:
        closes = {t: df["close"] for t, df in panels.items() if "close" in df.columns}
        close_df = pd.DataFrame(closes).sort_index()
        self._closes = close_df
        self._ret5 = close_df.pct_change(self.lookback_dias)

    def _preco(self, ticker: str, date: pd.Timestamp) -> float | None:
        if self._closes is None or ticker not in self._closes.columns:
            return None
        try:
            px = self._closes.at[date, ticker]
        except KeyError:
            return None
        if px is None or (isinstance(px, float) and math.isnan(px)):
            return None
        return float(px)

    def on_bar(
        self,
        date: pd.Timestamp,
        open_positions: dict[str, OpenPosition],
        cash_available: float,
    ) -> list[Action]:
        actions: list[Action] = []

        # Captura o valor de entrada da cesta assim que ela aparece preenchida
        # (o Enter de sexta so executa no open da proxima segunda — ver
        # docstring do modulo). So roda enquanto ainda nao temos referencia.
        if self._basket_entry_value is None and open_positions:
            self._basket_entry_value = sum(
                p.entry_price * p.quantity for p in open_positions.values()
            )

        # (a) STOP DE PORTFOLIO — checado TODO dia, nao so sexta. Unico stop
        # que existe neste desenho (hipotese explicita: sem stop individual).
        if open_positions and self._basket_entry_value:
            valor_atual = 0.0
            precos_ok = True
            for ticker, pos in open_positions.items():
                px = self._preco(ticker, date)
                if px is None:
                    precos_ok = False
                    break
                valor_atual += px * pos.quantity
            if precos_ok:
                dd = (valor_atual - self._basket_entry_value) / self._basket_entry_value
                if dd <= -self.stop_portfolio_pct:
                    for ticker in open_positions:
                        actions.append(Exit(ticker=ticker, reason=ExitReason.STOP))
                    self._basket_entry_value = None
                    self.stops_portfolio += 1
                    return actions

        # (b) REBALANCE SEMANAL — toda sexta-feira (weekday() == 4).
        if date.weekday() != 4:
            return actions

        self.semanas_com_rebalance += 1

        # Fecha a cesta da semana que termina (se ainda aberta — o stop de
        # portfolio pode ja ter fechado tudo antes da proxima sexta).
        for ticker in list(open_positions.keys()):
            actions.append(Exit(ticker=ticker, reason=ExitReason.ROTATION_OUT))
        self._basket_entry_value = None

        if self._ret5 is None or date not in self._ret5.index:
            return actions
        row = self._ret5.loc[date].dropna()
        n = len(row)
        if n < self.min_universo_valido:
            self.semanas_universo_insuficiente += 1
            return actions

        mediana = float(row.median())
        self.medianas_observadas.append(mediana)
        if not (-self.banda_mediana <= mediana <= self.banda_mediana):
            self.semanas_filtro_mediana += 1
            return actions

        decile_size = max(1, n // self.n_decis)
        piores = row.sort_values(ascending=True).index[:decile_size]
        size_hint = 1.0 / len(piores)
        for ticker in piores:
            actions.append(
                Enter(
                    ticker=ticker,
                    initial_stop=None,
                    size_hint=size_hint,
                    reason="reversao_decil_inferior",
                )
            )
        self.semanas_com_entrada += 1
        return actions


# ---------------------------------------------------------------------------
# Wilson score interval (95%) — nao existe helper no repo (`grep wilson` vazio
# em 2026-09-11), implementado aqui inline.
# ---------------------------------------------------------------------------
def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    centro = p + z**2 / (2 * n)
    margem = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    lo = (centro - margem) / denom
    hi = (centro + margem) / denom
    return (max(0.0, lo), min(1.0, hi))


def breakeven_empirico(ganhos: list[float], perdas: list[float]) -> float | None:
    """perda_media / (ganho_medio + perda_media), em modulo. `None` se nao da
    para calcular (sem perdas ou sem ganhos)."""
    if not ganhos or not perdas:
        return None
    ganho_medio = sum(ganhos) / len(ganhos)
    perda_media = abs(sum(perdas) / len(perdas))
    if ganho_medio + perda_media == 0:
        return None
    return perda_media / (ganho_medio + perda_media)


def rodar_janela(start: str, end: str, capital: float, label: str) -> dict:
    print(f"\n{'=' * 78}\nJANELA {label}: {start} -> {end} | capital R$ {capital:,.2f}\n{'=' * 78}", flush=True)

    universe = load_universe(tickers=UNIVERSE, include_benchmark=True)

    decile_size_estimado = max(1, len(UNIVERSE) // 10)
    config = BacktestConfig(
        initial_capital=capital,
        max_concurrent_positions=decile_size_estimado + 4,  # folga sobre o decil
        stop_loss_pct=0.0,  # sem stop individual — so o de portfolio, na estrategia
        lot_size=1,  # fracionario: R$1.000/decil nao fecha lote de 100 em papel liquido
        costs=CostModel(fractional_fixed_fee=1.90, fractional_lot_shares=100),
    )

    strat = ReversaoCrossSectionalSemanal()
    result = run_backtest(universe, strat, config, start=start, end=end)

    trades = result.trades
    pnls_brl = [
        (t.exit_price - t.entry_price) * t.quantity - t.fees_total for t in trades if not t.is_open
    ]
    ganhos = [p for p in pnls_brl if p > 0]
    perdas = [p for p in pnls_brl if p <= 0]
    n_trades = len(pnls_brl)
    n_wins = len(ganhos)
    win_pct = 100.0 * n_wins / n_trades if n_trades else 0.0
    lo, hi = wilson_ci(n_wins, n_trades) if n_trades else (0.0, 0.0)
    be = breakeven_empirico(ganhos, perdas)
    stops = sum(1 for t in trades if not t.is_open and t.exit_reason == ExitReason.STOP)

    liquido = float(result.equity_curve.iloc[-1] - capital) if len(result.equity_curve) else 0.0

    # Fracao de MESES positivos (convencao swing) sobre a curva de equity.
    eq = result.equity_curve
    meses_pos = 0
    meses_total = 0
    if len(eq) > 1:
        eq_m = eq.resample("ME").last()
        eq_m_ret = eq_m.pct_change().dropna()
        meses_total = len(eq_m_ret)
        meses_pos = int((eq_m_ret > 0).sum())

    print(f"Universo (acoes, sem ETF): {len(UNIVERSE)} tickers | decil ~{decile_size_estimado}")
    print(f"Semanas com rebalance verificado (sextas na janela): {strat.semanas_com_rebalance}")
    print(f"  -> com entrada nova:                {strat.semanas_com_entrada}")
    print(f"  -> bloqueadas pelo filtro de mediana [-{2}%,+{2}%]: {strat.semanas_filtro_mediana}")
    print(f"  -> universo insuficiente (<{strat.min_universo_valido} papeis com ret5):{strat.semanas_universo_insuficiente}")
    print(f"Stops de PORTFOLIO disparados (-6% da fatia): {strat.stops_portfolio}")
    if strat.medianas_observadas:
        med = pd.Series(strat.medianas_observadas)
        print(f"Mediana do retorno_5d do universo, em todas as sextas: media {med.mean()*100:.2f}%, "
              f"desvio {med.std()*100:.2f}%, min {med.min()*100:.2f}%, max {med.max()*100:.2f}%")
    print(f"Trades fechados: {n_trades} | STOPS(perdas por reversal do portfolio): {stops}")
    print(f"Capital final: R$ {result.metrics.get('final_capital', capital):,.2f} | Liquido: R$ {liquido:,.2f}")
    print(f"MaxDD: {result.metrics.get('max_drawdown', 0.0) * 100:.2f}%")
    print(f"Win%: {win_pct:.2f}% (IC95% Wilson [{lo*100:.2f}% ; {hi*100:.2f}%]), n={n_trades}")
    if be is not None:
        dentro = lo <= be <= hi
        print(f"Breakeven empirico (perda_media/(ganho_medio+perda_media)): {be*100:.2f}% "
              f"{'-> DENTRO do IC (indefinido)' if dentro else ('-> ACIMA do IC (edge negativo)' if be > hi else '-> ABAIXO do IC (edge positivo)')}")
    else:
        print("Breakeven empirico: nao calculavel (sem ganhos ou sem perdas na amostra)")
    if meses_total:
        print(f"Meses positivos: {meses_pos}/{meses_total} ({100*meses_pos/meses_total:.1f}%)")
    else:
        print("Meses positivos: janela curta demais para agregar por mes")

    return {
        "label": label,
        "start": start,
        "end": end,
        "capital": capital,
        "n_trades": n_trades,
        "n_wins": n_wins,
        "win_pct": win_pct,
        "ic95_lo": lo,
        "ic95_hi": hi,
        "breakeven_empirico": be,
        "stops": stops,
        "liquido": liquido,
        "final_capital": result.metrics.get("final_capital", capital),
        "max_drawdown_pct": result.metrics.get("max_drawdown", 0.0) * 100,
        "semanas_com_rebalance": strat.semanas_com_rebalance,
        "semanas_com_entrada": strat.semanas_com_entrada,
        "semanas_filtro_mediana": strat.semanas_filtro_mediana,
        "semanas_universo_insuficiente": strat.semanas_universo_insuficiente,
        "meses_pos": meses_pos,
        "meses_total": meses_total,
    }


if __name__ == "__main__":
    CAPITAL = 1000.0

    # FASE 1 — teste pequeno (~6 meses -> ~26 sextas) antes de gastar a janela
    # cheia. Janela mais recente disponivel (dado vai ate 2026-09-11).
    r1 = rodar_janela("2026-03-01", "2026-09-11", CAPITAL, "PEQUENA (~6 meses)")

    # FASE 2 — so roda se a Fase 1 nao mostrou problema estrutural (universo
    # sempre insuficiente, engine quebrando, todas as semanas filtradas etc.)
    prosseguir = (
        r1["semanas_com_entrada"] >= 3
        and r1["n_trades"] >= 10
    )
    if prosseguir:
        r2 = rodar_janela("2010-01-01", "2026-09-11", CAPITAL, "CHEIA (FULL, 2010-2026)")
    else:
        print("\nFASE 1 nao produziu amostra minima (>=3 semanas com entrada e >=10 trades) "
              "-- FASE 2 (janela cheia) nao rodada. Ver diagnostico acima.")
