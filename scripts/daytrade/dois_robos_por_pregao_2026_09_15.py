# -*- coding: utf-8 -*-
"""Os dois robos, pregao a pregao, pela REGUA PADRAO -- 14/09 e 11/09.

Pedido do dono (2026-09-15): "rode as duas na data de ontem 14/09 e outra
separada na data de 13/09".

**13/09 e' DOMINGO e 12/09 e' SABADO -- nao houve pregao em nenhum dos dois.**
Confirmado na base: zero barras M1 em WIN@ e WDO@ nas duas datas. No lugar de
13/09 entra **11/09 (sexta)**, o pregao anterior real, rotulado como
substituto para ninguem confundir com o que foi pedido.

## Como rodam

Igual a producao, sem corte inventado: `config_for` direto, achatamento vindo
do perfil (18:20 BRT no WIN@, 18:25 no WDO@) e saida pela tabela padrao de
`backtest/intraday/report.py`. Capital = o piso de cada robo (R$1.100 no
`win_retangulo`, R$375 no `wdo_grid_reload_maker`), nunca valor redondo.

## Duas tabelas, nao uma

Instrumentos diferentes, granularidades diferentes (M1 x tick) e capitais
diferentes. Somar ou ordenar as duas na mesma tabela seria comparar coisas
incomparaveis -- cada robo tem a sua.

`wdo_grid_reload_maker` roda em TICK e a base canonica de tick para em
2026-09-04, entao os ticks destes pregoes vem do terminal em memoria, **sem
merge na base canonica**.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/dois_robos_por_pregao_2026_09_15.py`
"""
from __future__ import annotations

import sys
from datetime import datetime, time, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import daytrade_robot_class, get_daytrade_robot  # noqa: E402

PEDIDOS = [
    (pd.Timestamp("2026-09-14").date(), "14/09 seg"),
    (pd.Timestamp("2026-09-11").date(), "11/09 sex (no lugar de 13/09, domingo)"),
]
ROBOS = [("win_retangulo", 1_100.0), ("wdo_grid_reload_maker", 375.0)]
EXTRAS = ("pts/op", "BEemp%", "alvo/stop", "pior op.", "melhor op.")


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ticks_do_dia(symbol_real: str, dia):
    from core.b3_session import utc_to_server_wall_clock
    from market_data_intraday.mt5_ticks_source import fetch_ticks_range

    ini = datetime.combine(dia, time(11, 0), tzinfo=timezone.utc)
    fim = datetime.combine(dia, time(21, 40), tzinfo=timezone.utc)
    erros: list = []
    df = fetch_ticks_range(
        symbol_real,
        utc_to_server_wall_clock(ini).replace(tzinfo=timezone.utc),
        utc_to_server_wall_clock(fim).replace(tzinfo=timezone.utc),
        on_error=lambda k, e: erros.append((k, e)))
    if erros:
        print(f"    [ticks] erros: {erros}", flush=True)
    return df


def _barras(robo, dia):
    if robo.feed_kind == "tick":
        from market_data_intraday.tick_bars import ticks_to_degenerate_bars

        real = "WDOV26" if robo.symbol == "WDO@" else "WINV26"
        ticks = _ticks_do_dia(real, dia)
        if ticks.empty:
            return ticks
        b = ticks_to_degenerate_bars(ticks)
        return b[b.index.date == dia]
    df = load_m1(robo.symbol).sort_index()
    return df[df.index.date == dia]


def _roda(chave: str, capital: float, dia, rotulo: str):
    robo = get_daytrade_robot(chave)
    bars = _barras(robo, dia)
    if bars.empty:
        return None, robo, 0
    profile = profile_for(robo.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=capital,
        target_fills_as_maker=robo.target_fills_as_maker,
        anchor_exits_at_fill=robo.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True)
    res = run_intraday_backtest(bars, robo, cfg)
    trades = list(res.trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    # breakeven empirico exige os DOIS lados da amostra: sem acerto (ou sem
    # perda) a formula devolve 1,0 (ou 0,0) por construcao, e comparar o
    # win% com isso e' comparar um numero com ele mesmo.
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    pts = ((sum(t.pnl_brl for t in trades) / len(trades)) / 0.20) if trades else float("nan")
    alvos = sum(1 for t in trades if t.exit_reason.value == "target")
    stops = sum(1 for t in trades if t.exit_reason.value == "stop")
    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "alvo/stop": f"{alvos}/{stops}",
        "pior op.": br(min(p)) if p else "—",
        "melhor op.": br(max(g)) if g else "—",
    }
    return linha_de_resultado(rotulo, res, capital, extras=extras), robo, len(bars)


def main():
    print("=" * 158)
    print("OS DOIS ROBOS, PREGAO A PREGAO -- pela regua padrao")
    print("=" * 158)
    print("  13/09 e' DOMINGO e 12/09 e' SABADO: zero barras M1 em WIN@ e WDO@ nos dois.")
    print("  No lugar de 13/09 entra 11/09 (sexta), o pregao anterior real.")
    print("  Corte de achatamento vindo do PERFIL (18:20 BRT no WIN@, 18:25 no WDO@).\n",
          flush=True)

    for dia, rotulo_dia in PEDIDOS:
        print("=" * 158)
        print(f"PREGAO {rotulo_dia}   ({dia.strftime('%A')})")
        print("=" * 158)
        for chave, capital in ROBOS:
            print(f"  rodando {chave} (capital R$ {br(capital,0)})...", flush=True)
            linha, robo, n_barras = _roda(chave, capital, dia, chave)
            if linha is None:
                print(f"    SEM DADO para {robo.symbol} neste pregao "
                      f"(feed {robo.feed_kind}) -- nenhuma linha.\n")
                continue
            print(f"    {robo.symbol} {robo.feed_kind}: {n_barras} barras\n")
            print(tabela([linha], extras=EXTRAS))
            print()

    print("=" * 158)
    print("COMO LER")
    print("=" * 158)
    print("  * UM pregao por linha. Nenhum veredito sai daqui -- o acerto de um dia nao")
    print("    separa estrategia de sorteio, e por isso a coluna de veredito nem aparece.")
    print("  * As duas tabelas NAO se comparam: instrumentos, granularidades e capitais")
    print("    diferentes. Cada robo contra ele mesmo.")
    print("  * O aviso `fila NAO CALIBRADA` na linha do WIN@ e' a ressalva que mais pesa:")
    print("    toda ordem-limite preenche no TOQUE, dos dois lados. O WDO@ ja roda com a")
    print("    fila medida contra extrato real.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
