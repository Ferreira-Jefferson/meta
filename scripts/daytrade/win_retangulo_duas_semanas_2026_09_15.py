# -*- coding: utf-8 -*-
"""`win_retangulo` nas ULTIMAS DUAS SEMANAS, pela regua padrao.

Pedido do dono (2026-09-15): "rode retangulo de acordo com a regua de teste nas
ultimas duas semanas".

Janela: **2026-09-01 a 2026-09-14, 9 pregoes** (07/09 e' feriado da
Independencia; 05-06 e 12-13 sao fins de semana). O pregao de **15/09 fica
FORA da janela** e sai numa linha propria: ele tem 501 barras contra 562 dos
completos, ou seja, o achatamento das 18:20 ainda nao aconteceu. Misturar
pregao incompleto no agregado estraga `R$/dia` e `pregoes` de um jeito que
ninguem enxerga depois.

## O que esta janela NAO e'

Ela esta inteira DENTRO do OOS (>= 2026-06-13), que ja foi medido. **Isto e'
um ZOOM, nao evidencia nova** -- as mesmas operacoes ja estao contadas na
linha de 64 pregoes. Nove pregoes servem para ver a FORMA (como o resultado
se distribui, se depende de um dia so'), nunca para veredito: com ~30
operacoes o intervalo do acerto e' largo demais para separar qualquer coisa.

Por isso sai tambem a decomposicao pregao a pregao e a conta de quanto o
melhor dia responde pelo total -- que e' a pergunta que um agregado de 9
linhas esconde.

Capital R$1.100 (piso medido do robo), corte de achatamento vindo do perfil,
saida por `backtest/intraday/report.py`.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_duas_semanas_2026_09_15.py`
"""
from __future__ import annotations

import sys
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

CAPITAL = float(daytrade_robot_class("win_retangulo").capital_minimo_recomendado_brl)
MIN_BARRAS_POR_PREGAO = 400
HOJE = pd.Timestamp("2026-09-15").date()
INICIO = pd.Timestamp("2026-09-01").date()
EXTRAS = ("pts/op", "BEemp%", "alvo/stop", "sem trade", "pior op.")


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ic95(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - r) / d, (c + r) / d


def _roda(rotulo: str, dias: list):
    robo = get_daytrade_robot("win_retangulo")
    df = load_m1(robo.symbol).sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(robo.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=CAPITAL,
        target_fills_as_maker=robo.target_fills_as_maker,
        anchor_exits_at_fill=robo.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True)
    res = run_intraday_backtest(bars, robo, cfg)
    trades = list(res.trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    pts = ((sum(t.pnl_brl for t in trades) / len(trades)) / 0.20) if trades else float("nan")
    alvos = sum(1 for t in trades if t.exit_reason.value == "target")
    stops = sum(1 for t in trades if t.exit_reason.value == "stop")
    com_trade = {t.exit_ts.date() for t in trades}
    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "alvo/stop": f"{alvos}/{stops}",
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}",
        "pior op.": br(min(p)) if p else "—",
    }
    return (linha_de_resultado(rotulo, res, CAPITAL, extras=extras), trades,
            be, _ic95(len(g), len(trades)))


def main():
    robo = get_daytrade_robot("win_retangulo")
    df = load_m1(robo.symbol).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items()
                       if n >= MIN_BARRAS_POR_PREGAO and INICIO <= d <= HOJE)
    janela = [d for d in completos if d < HOJE]

    print("=" * 152)
    print("win_retangulo -- ULTIMAS DUAS SEMANAS, pela regua padrao")
    print("=" * 152)
    print(f"  janela: {janela[0]} a {janela[-1]} | {len(janela)} pregoes "
          f"(07/09 feriado; fins de semana fora)")
    print(f"  capital R$ {br(CAPITAL,0)} (piso medido) | 1 contrato | corte de "
          f"achatamento vindo do PERFIL (18:20 BRT)")
    print(f"  15/09 fica FORA do agregado: {int(contagem.get(HOJE,0))} barras contra "
          f"~562 dos completos (pregao ainda aberto)\n", flush=True)
    print("  *** ATENCAO: esta janela esta INTEIRA dentro do OOS ja medido. E' um ZOOM")
    print("      nas mesmas operacoes, nao evidencia nova. ***\n", flush=True)

    linha, trades, be, ic = _roda(f"2 semanas ({len(janela)} pregoes)", janela)
    linha_hoje, tr_hoje, _be_h, _ic_h = _roda("15/09 (PARCIAL, fora do agregado)", [HOJE])

    print(tabela([linha, linha_hoje], extras=EXTRAS))

    print("\n" + "=" * 152)
    print("PREGAO A PREGAO -- de onde o numero agregado vem")
    print("=" * 152)
    por_dia = {}
    for t in trades:
        por_dia.setdefault(t.exit_ts.date(), []).append(t.pnl_brl)
    print(f"  {'pregao':<14}{'dia':<11}{'operacoes':>11}{'liquido R$':>13}"
          f"{'acertos':>10}{'acumulado':>13}")
    acum = 0.0
    for d in janela:
        vals = por_dia.get(d, [])
        acum += sum(vals)
        ganhos = sum(1 for v in vals if v > 0)
        print(f"  {d.strftime('%d/%m'):<14}{pd.Timestamp(d).day_name():<11}"
              f"{len(vals):>11}{br(sum(vals)):>13}"
              f"{(f'{ganhos}/{len(vals)}' if vals else '—'):>10}{br(acum):>13}")

    dias_pos = [d for d in janela if sum(por_dia.get(d, [])) > 0]
    dias_neg = [d for d in janela if sum(por_dia.get(d, [])) < 0]
    somas = sorted((sum(v) for v in por_dia.values()), reverse=True)
    total = sum(somas)
    print(f"\n  pregoes positivos: {len(dias_pos)}/{len(janela)} | negativos: "
          f"{len(dias_neg)} | sem operar: {len(janela) - len(por_dia)}")
    if somas and total != 0:
        print(f"  MELHOR pregao responde por {br(100*somas[0]/total,0)}% do liquido "
              f"da janela (R$ {br(somas[0])} de R$ {br(total)})")
    print(f"  acerto na janela: IC95 [{br(100*ic[0],1)} ; {br(100*ic[1],1)}] "
          f"contra breakeven empirico {br(100*be,1)}%")

    print("\n" + "=" * 152)
    print("COMO LER")
    print("=" * 152)
    print("  * 9 pregoes nao produzem veredito. Com ~30 operacoes o intervalo do acerto")
    print("    e' largo demais para separar estrategia de sorteio -- por isso a coluna de")
    print("    veredito nao aparece aqui.")
    print("  * A janela e' um recorte do OOS que ja foi medido: as operacoes dela ja")
    print("    estao contadas na linha de 64 pregoes. Serve para ver FORMA, nao tamanho.")
    print("  * `fila NAO CALIBRADA`: WIN@ nao tem entrada em `fidelidade.py`, entao toda")
    print("    ordem-limite preenche no TOQUE, dos dois lados. Premissa otimista.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
