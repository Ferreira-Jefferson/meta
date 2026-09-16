# -*- coding: utf-8 -*-
"""`win_retangulo` -- ESCADA DE PISO DE LARGURA: subir o piso melhora a
ECONOMIA por operacao o bastante para compensar o corte de amostra?

## A pergunta exata

Ja esta' medido (`win_retangulo_largura_paga_2026_09_15.py`) que o retorno
por REAL ARRISCADO cresce com a largura do retangulo (correlacao de posto
+0,338 no IS / +0,306 no OOS) e que o PISO de 328 pontos e' o UNICO filtro
de forma que sobreviveu as duas janelas. A pergunta que fica, e que este
script responde: **subir o piso (em vez de por TETO, que ja foi refutado
tres vezes como alavanca de lucro) desloca o breakeven empirico o bastante
para abrir mais margem contra o IC95 do acerto -- ou o corte de amostra
alarga o intervalo mais rapido do que a economia melhora?**

Isto NAO e' a grade de geometria alvo/stop (ja e' platô, 39/42, resposta
fechada) nem o teto de risco (ja refutado 3x). E' o UNICO eixo de forma que
tinha ficado sem varredura em escada.

## Metodo

Robo de PRODUCAO (`strategy.daytrade.lab.win_retangulo.WinRetangulo`),
subclassado SO' para variar `largura_minima_pontos` -- todo o resto
(W=20, alvo 0,80xL, stop 0,50xL, tolerancia 0,20, teto risco R$80, ttl=10,
quantidade=1) fica no default CONGELADO. Cada piso e' um backtest
INDEPENDENTE (levantar o piso muda quais retangulos o detector aceita, e
portanto a POPULACAO de operacoes -- nao da' para ler isso comparando
tetos numa unica rodada, e' o mesmo motivo que ja vetou ler o teto de risco
por uma varredura so').

Capital R$1.100 (piso medido do robo, regua oficial), MIN_BARRAS_POR_
PREGAO=400, IS < 2026-06-13, OOS >= 2026-06-13 (excluindo HOJE, pregao
parcial) -- identico a `win_retangulo_regua_padrao_2026_09_15.py`.

Para cada (piso, janela): tabela padrao (`backtest/intraday/report.py`) +
extras -- ganho medio, perda media, breakeven empirico, IC95 Wilson do
acerto, MARGEM (limite inferior do IC menos o breakeven, em pp) e caixa
minimo realizado (rebaixamento por OPERACAO + margem crua R$100). A conta
de N e' obrigatoria: subir o piso corta amostra, e cortar amostra alarga o
IC -- se a margem so' cresce porque o IC ficou largo (nao porque o centro
subiu), isso e' fabricar melhora, nao medi-la.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_escada_piso_largura_2026_09_15.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
_PRODUCAO = get_daytrade_robot("win_retangulo")
CAPITAL = float(_PRODUCAO.capital_minimo_recomendado_brl)
SYMBOL = _PRODUCAO.symbol
MIN_BARRAS_POR_PREGAO = 400
PISOS = [328.0, 380.0, 430.0, 500.0, 600.0]
EXTRAS = ("ganho med.", "perda med.", "BEemp%", "IC95 acerto", "margem pp",
          "rebaix.op.", "sem trade")


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


def _caixa_realizado(trades, capital):
    """caixa minimo NESTA ordem historica + rebaixamento POR OPERACAO (pico a
    vale da curva de patrimonio, o mesmo conceito que fixou o piso de R$1.100
    do robo -- ver `WinRetangulo.capital_minimo_recomendado_brl`)."""
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    if not seq:
        return capital, 0.0
    acum = np.cumsum(seq)
    eq_path = capital + acum
    rebaix_op = float((np.maximum.accumulate(eq_path) - eq_path).max())
    return float(eq_path.min()), rebaix_op


def _unidade(args):
    piso, rotulo, dias = args
    strat = WinRetangulo(largura_minima_pontos=piso)
    df = load_m1(strat.symbol).sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(strat.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=CAPITAL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)

    trades = list(res.trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    lo, hi = _ic95(len(g), len(trades))
    margem_pp = 100 * (lo - be) if (be == be and lo == lo) else float("nan")
    com_trade = {t.exit_ts.date() for t in trades}
    caixa_min, rebaix_op = _caixa_realizado(trades, CAPITAL)

    extras = {
        "ganho med.": br(gm),
        "perda med.": br(pm),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "IC95 acerto": (f"[{br(100*lo,1)};{br(100*hi,1)}]" if trades else "--"),
        "margem pp": br(margem_pp, 1) if margem_pp == margem_pp else "--",
        "rebaix.op.": br(rebaix_op),
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}",
    }
    linha = linha_de_resultado(f"piso {piso:.0f}", res, CAPITAL, extras=extras)
    return dict(piso=piso, rotulo=rotulo, linha=linha, n=len(trades),
                n_g=len(g), n_p=len(p), gm=gm, pm=pm, be=be, ic=(lo, hi),
                margem_pp=margem_pp, caixa_min=caixa_min, rebaix_op=rebaix_op)


def main():
    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    print("=" * 170)
    print("win_retangulo -- ESCADA DE PISO DE LARGURA (largura_minima_pontos), IS e OOS")
    print("=" * 170)
    print(f"  capital R$ {br(CAPITAL,0)} | 1 contrato | IS {len(IS)} pregoes | "
          f"OOS {len(OOS)} pregoes | pisos testados: "
          + ", ".join(f'{p:.0f}' for p in PISOS) + "\n", flush=True)

    tarefas = [(piso, jn, dd) for jn, dd in (("IS", IS), ("OOS", OOS)) for piso in PISOS]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out.setdefault(r["rotulo"], {})[r["piso"]] = r
            print(f"  ok {r['rotulo']} piso={r['piso']:.0f}: n={r['n']}", flush=True)

    for jn in ("IS", "OOS"):
        linhas = [out[jn][piso]["linha"] for piso in PISOS]
        print("\n" + "=" * 170)
        print(f"{jn} -- tabela padrao por piso de largura")
        print("=" * 170)
        print(tabela(linhas, extras=EXTRAS))

    print("\n" + "=" * 170)
    print("A CONTA EXPLICITA: n, win%, breakeven, IC95 e MARGEM, piso 328 (baseline) -> cada piso maior")
    print("=" * 170)
    for jn in ("IS", "OOS"):
        base = out[jn][328.0]
        print(f"\n  janela {jn} (baseline piso 328: n={base['n']}, "
              f"win%={br(100*base['n_g']/base['n'],1) if base['n'] else 0}%, "
              f"BEemp={br(100*base['be'],1) if base['be']==base['be'] else '--'}%, "
              f"IC95=[{br(100*base['ic'][0],1)};{br(100*base['ic'][1],1)}], "
              f"margem={br(base['margem_pp'],1)}pp)")
        print(f"  {'piso':>6}{'n':>7}{'delta n':>9}{'win%':>8}{'ganho med.':>12}"
              f"{'perda med.':>12}{'BEemp%':>9}{'IC95 baixo':>12}{'margem pp':>11}{'delta margem':>14}")
        for piso in PISOS:
            r = out[jn][piso]
            win = 100 * r["n_g"] / r["n"] if r["n"] else float("nan")
            delta_n = r["n"] - base["n"]
            delta_margem = r["margem_pp"] - base["margem_pp"]
            print(f"  {piso:>6.0f}{r['n']:>7}{delta_n:>+9}"
                  f"{br(win,1):>7}%{br(r['gm']):>12}{br(r['pm']):>12}"
                  f"{(br(100*r['be'],1)+'%') if r['be']==r['be'] else '--':>9}"
                  f"{br(100*r['ic'][0],1):>12}{br(r['margem_pp'],1):>11}"
                  f"{delta_margem:>+14.1f}")

    print("\n" + "=" * 170)
    print("LEITURA")
    print("=" * 170)
    print("  'margem pp' = limite INFERIOR do IC95 do acerto menos o breakeven empirico, em")
    print("  pontos percentuais -- e' a mesma grandeza que decide o veredito POSITIVO/indefinido.")
    print("  Se ela cresce com o piso NAS DUAS janelas e o centro do acerto tambem sobe (nao so'")
    print("  o IC alargando), a mudanca replica. Se ela so' cresce numa janela, ou cresce so'")
    print("  porque o 'n' caiu e o IC alargou (o limite inferior desce, nao sobe -- ai a margem")
    print("  so' aumentaria por acaso), a leitura e' REFUTACAO, nao achado.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
