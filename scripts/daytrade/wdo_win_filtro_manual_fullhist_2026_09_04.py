"""Variante MANUAL pedida pelo dono, 2026-09-04, depois de ver
`wdo_win_filtro_dia_horario_impacto_2026_09_04.py`: "rode desta maneira" --
WDO SEM sexta + 9h, WIN SEM terca + 12h/15h/17h. Sao os numeros do relatorio
DESCRITIVO (`wdo_win_padrao_dia_horario_2026_09_04.py`, historico INTEIRO)
para o dia, misturados com as horas ruins do teste IS-only (`wdo_win_filtro_
dia_horario_impacto_2026_09_04.py`) para o WIN -- uma combinacao escolhida a
mao pelo dono, nao recalculada aqui.

## Ressalva que precisa ficar dita, nao escondida

Diferente do script IS->OOS anterior, a regra AQUI usa numero derivado do
historico INTEIRO (o dia "sexta"/"terca" veio do relatorio com IS+OOS
misturados). Isso significa que a leitura "SO OOS" abaixo NAO e' uma
confirmacao honesta como a do script anterior -- o OOS ja' influenciou a
escolha do dia (vazamento parcial). Ainda vale rodar (o dono pediu
explicitamente para comparar), mas o numero tem de ser lido como
REFERENCIA, no MESMO nivel de confianca do bloco "historico INTEIRO" do
script anterior -- nunca como prova independente.

Mesmo mecanismo de filtro (`FiltroDiaHora`, com o cuidado de chamar
`on_order_rejected` ao suprimir uma entrada -- ver a docstring longa em
`wdo_win_filtro_dia_horario_impacto_2026_09_04.py` para o porque disso ser
obrigatorio na `WdoGridReloadMaker`), mesmo capital com folga (R$5.000 WDO /
R$3.000 WIN), mesmo corte OOS (2026-06-13).

Uso: `python -u scripts/daytrade/wdo_win_filtro_manual_fullhist_2026_09_04.py`
"""
from __future__ import annotations

import datetime
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TZ = "America/Sao_Paulo"
MIN_BARRAS_POR_PREGAO = 400
DIAS_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta")
OOS_CUTOFF = "2026-06-13"

#: dia (indice em DIAS_SEMANA) + horas excluidas, por simbolo -- pedido
#: literal do dono, nao recalculado.
VARIANTES_MANUAIS = {
    "WDO@": dict(label="WDO F1 maker", key="wdo_grid_reload_maker",
                 economia=(0.01, 0.001), capital=5_000.0,
                 dia=DIAS_SEMANA.index("sexta"), horas=frozenset({9})),
    "WIN@": dict(label="CopaWin", key="copa_win",
                 economia=(0.2, 1.0), capital=3_000.0,
                 dia=DIAS_SEMANA.index("terca"), horas=frozenset({12, 15, 17})),
}


def br(v, casas: int = 2) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _to_local(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(TZ)


def _carregar_bars(symbol: str) -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "src"))
    from market_data_intraday.storage import load_m1

    df = load_m1(symbol).sort_index()
    if df.empty:
        raise SystemExit(f"sem dado M1 salvo para {symbol!r}.")
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return df[[d in completos for d in df.index.date]]


def _rodar_variante(symbol: str, key: str, economia: tuple[float, float], capital: float,
                     dias_excluidos: frozenset[int], horas_excluidas: frozenset[int]):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.base import Enter, EnterLimit, IntradayStrategy
    from strategy.daytrade.registry import get_daytrade_robot

    class FiltroDiaHora(IntradayStrategy):
        def __init__(self, inner: IntradayStrategy):
            self._inner = inner
            self.name = inner.name
            self.version = inner.version
            self.symbol = inner.symbol
            self.target_fills_as_maker = inner.target_fills_as_maker
            self.feed_kind = inner.feed_kind
            self.is_futuro = inner.is_futuro

        def initialize(self, bars):
            return self._inner.initialize(bars)

        def on_session_start(self, session_date):
            return self._inner.on_session_start(session_date)

        def on_capital_update(self, cash_brl):
            return self._inner.on_capital_update(cash_brl)

        def on_order_rejected(self, ts):
            return self._inner.on_order_rejected(ts)

        def seed_volume_window(self, previous_session_tail):
            return self._inner.seed_volume_window(previous_session_tail)

        def seed_daily_volatility(self, previous_daily_bars):
            return self._inner.seed_daily_volatility(previous_daily_bars)

        def seed_typical_trade_size(self, previous_daily_medians):
            return self._inner.seed_typical_trade_size(previous_daily_medians)

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            acoes = self._inner.on_bar(ts, bar, positions, session_pnl_brl)
            local = _to_local(pd.Timestamp(ts))
            bloqueado = local.weekday() in dias_excluidos or local.hour in horas_excluidas
            if not bloqueado:
                return acoes
            permitidas = []
            suprimiu_entrada = False
            for a in acoes:
                if isinstance(a, (Enter, EnterLimit)):
                    suprimiu_entrada = True
                else:
                    permitidas.append(a)
            if suprimiu_entrada:
                self._inner.on_order_rejected(ts)
            return permitidas

    bars = _carregar_bars(symbol)
    strat: IntradayStrategy = get_daytrade_robot(key, symbol=symbol)
    if dias_excluidos or horas_excluidas:
        strat = FiltroDiaHora(strat)
    profile = profile_for(symbol)
    trade_tick_value, trade_tick_size = economia
    cfg = config_for(
        profile, trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    return resultado


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import cabecalho, linha, linha_de_resultado

    cutoff = datetime.date.fromisoformat(OOS_CUTOFF)
    print("[wdo_win_filtro_manual_fullhist] regra MANUAL (dia/hora do relatorio "
          "descritivo, nao recalculada aqui) -- ver ressalva de vazamento na docstring\n",
          flush=True)

    tarefas = []
    for symbol, cfg in VARIANTES_MANUAIS.items():
        tarefas.append((symbol, "baseline", frozenset(), frozenset()))
        tarefas.append((symbol, "sem_dia_e_horas_fullhist", frozenset({cfg["dia"]}), cfg["horas"]))

    resultados = {}
    with ProcessPoolExecutor(max_workers=len(tarefas)) as ex:
        futuros = {}
        for symbol, nome, dias, horas in tarefas:
            cfg = VARIANTES_MANUAIS[symbol]
            fut = ex.submit(_rodar_variante, symbol, cfg["key"], cfg["economia"], cfg["capital"], dias, horas)
            futuros[fut] = (symbol, nome)
        for fut in futuros:
            symbol, nome = futuros[fut]
            resultados[(symbol, nome)] = fut.result()
            print(f"[pronto] {symbol} {nome}: {len(resultados[(symbol, nome)].trades)} trades", flush=True)

    print()
    for symbol, cfg in VARIANTES_MANUAIS.items():
        print("=" * 100)
        print(f"{cfg['label']} ({symbol}) -- exclui {DIAS_SEMANA[cfg['dia']]} + "
              f"horas {sorted(cfg['horas'])} -- capital R${br(cfg['capital'], 0)}")
        print("=" * 100)

        print("\n--- historico INTEIRO ---")
        print(cabecalho())
        for nome in ("baseline", "sem_dia_e_horas_fullhist"):
            resultado = resultados[(symbol, nome)]
            item = linha_de_resultado(nome, resultado, cfg["capital"])
            print(linha(item))

        print(f"\n--- SO OOS (>= {OOS_CUTOFF}) -- LEIA A RESSALVA: regra usou dado do historico "
              f"inteiro, entao isto NAO e uma confirmacao IS->OOS limpa ---")
        print(cabecalho())
        linhas_oos = {}
        for nome in ("baseline", "sem_dia_e_horas_fullhist"):
            resultado = resultados[(symbol, nome)]
            trades_oos = [t for t in resultado.trades
                          if _to_local(pd.Timestamp(t.entry_ts)).date() >= cutoff]
            eq = resultado.equity_curve
            if eq is not None and not eq.empty:
                local_idx = pd.DatetimeIndex([_to_local(pd.Timestamp(ts)) for ts in eq.index])
                eq_oos = eq[local_idx.date >= cutoff]
            else:
                eq_oos = eq
            fake = SimpleNamespace(trades=trades_oos, equity_curve=eq_oos)
            item = linha_de_resultado(f"{nome} [OOS]", fake, initial_capital=0, capital_nocional=True)
            linhas_oos[nome] = item
            print(linha(item))

        base, var = linhas_oos["baseline"], linhas_oos["sem_dia_e_horas_fullhist"]
        print(f"\nOOS baseline: R${br(base.liquido_brl)} liquido, {br(base.win_rate_pct,1)}% win, "
              f"{base.trades} trades")
        print(f"OOS com filtro manual: R${br(var.liquido_brl)} liquido "
              f"({'+' if var.liquido_brl >= base.liquido_brl else ''}"
              f"{br(var.liquido_brl - base.liquido_brl)}), "
              f"{br(var.win_rate_pct,1)}% win "
              f"({'+' if var.win_rate_pct >= base.win_rate_pct else ''}"
              f"{br(var.win_rate_pct - base.win_rate_pct,1)}pp), "
              f"{var.trades} trades ({var.trades - base.trades:+d})")
        print()


if __name__ == "__main__":
    main()
