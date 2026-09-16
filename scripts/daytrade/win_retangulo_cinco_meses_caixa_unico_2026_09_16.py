# -*- coding: utf-8 -*-
"""`win_retangulo` em CINCO MESES, partindo do caixa minimo e sem nenhum aporte.

Pedido do dono (2026-09-16): "rode os ultimos 5 meses", na sequencia do teste
de dois meses (`win_retangulo_dois_meses_caixa_unico_2026_09_16.py`), com as
mesmas regras: capital inicial = piso do robo, nenhum aporte, caixa acumulando.

## A janela ATRAVESSA o corte IS/OOS -- e isso muda como ela se le

2026-04-16 a 2026-09-16. O corte congelado do projeto e' **2026-06-13**, entao
esta janela e' ~2 meses de IS (onde os parametros foram escolhidos) + ~3 meses
de OOS. Ler o agregado dos 5 meses como se fosse tudo evidencia cega seria
errado: a primeira parte e' justamente onde o desenho foi ajustado.

Por isso o script separa os tres blocos -- IS, OOS e o total -- em vez de
mostrar so' a linha cheia. O numero que mais informa e' o do OOS; o do IS e' o
que se espera que seja bom, porque foi ali que se olhou.

O pregao de 16/09 nao entra: este script rodou antes da abertura.

## O que "usando somente este capital" significa aqui

Capital inicial = `capital_minimo_recomendado_brl` (R$1.100). Nenhum aporte. O
caixa e' inicial + P&L realizado e e' ele que dimensiona a proxima entrada
(`on_capital_update` a cada barra). Escada de contratos: `C(n) = R$1.100 x
n^1,415` -- 1 contrato em R$1.100, 2 em R$2.933, 3 em R$5.206, 4 em R$7.822.

## Ressalvas

- `fila NAO CALIBRADA`: WIN@ nao esta em `backtest/intraday/fidelidade.py`,
  entao toda ordem-limite preenche no TOQUE, dos dois lados.
- Backtest com feed PERFEITO e sem restart. A sombra perde barra (medido:
  14/09, `copa_win` parou de receber barra as 10:31 com posicao aberta e o
  ledger terminou R$138,50 otimista).
- So' pregoes com >= 400 barras entram; a sombra nao escolhe o dia que vive.
- Mesma classe `WinRetangulo` e mesmo `config_for` do caminho ao vivo.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_cinco_meses_caixa_unico_2026_09_16.py`
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
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

INICIO = pd.Timestamp("2026-04-16").date()
FIM = pd.Timestamp("2026-09-16").date()
CORTE_OOS = pd.Timestamp("2026-06-13").date()
MIN_BARRAS_POR_PREGAO = 400
EXTRAS = ("pts/op", "BEemp%", "ctr max", "ctr méd", "sem trade", "pior op.", "melhor op.")


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ic95(k: int, n: int):
    if n == 0:
        return float("nan"), float("nan")
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - r) / d, (c + r) / d


def _mede(rotulo, robo, df, dias, capital):
    profile = profile_for(robo.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=capital,
        target_fills_as_maker=robo.target_fills_as_maker,
        anchor_exits_at_fill=robo.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True)
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    res = run_intraday_backtest(bars, robo, cfg)
    trades = list(res.trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    qt = [int(getattr(t, "quantity", 1) or 1) for t in trades]
    liq = sum(t.pnl_brl for t in trades)
    pts = ((liq / len(trades)) / 0.20) if trades else float("nan")
    com = {t.exit_ts.date() for t in trades}
    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "ctr max": str(max(qt)) if qt else "—",
        "ctr méd": br(sum(qt) / len(qt), 2) if qt else "—",
        "sem trade": f"{len(dias)-len(com)}/{len(dias)}",
        "pior op.": br(min(p)) if p else "—",
        "melhor op.": br(max(g)) if g else "—",
    }
    linha = linha_de_resultado(rotulo, res, capital, extras=extras)
    return linha, trades, be, _ic95(len(g), len(trades))


def main():
    robo = get_daytrade_robot("win_retangulo")
    capital = float(robo.capital_minimo_recomendado_brl)
    df = load_m1(robo.symbol).sort_index()
    contagem = df.groupby(df.index.date).size()
    pregoes = sorted(d for d, n in contagem.items()
                     if n >= MIN_BARRAS_POR_PREGAO and INICIO <= d <= FIM)
    is_dias = [d for d in pregoes if d < CORTE_OOS]
    oos_dias = [d for d in pregoes if d >= CORTE_OOS]

    print("=" * 172)
    print("win_retangulo — CINCO MESES, caixa mínimo e nenhum aporte")
    print("=" * 172)
    print(f"  janela pedida : {INICIO} a {FIM}")
    print(f"  janela medida : {pregoes[0]} a {pregoes[-1]}   "
          f"({(pregoes[-1]-pregoes[0]).days + 1} dias corridos, {len(pregoes)} pregões)")
    print(f"  16/09 não entrou: o pregão ainda não abriu quando isto rodou")
    print(f"  capital inicial R$ {br(capital)} — piso do robô, SEM aporte")
    print()
    print(f"  *** A janela ATRAVESSA o corte IS/OOS ({CORTE_OOS}) ***")
    print(f"      IS  (parâmetros foram escolhidos aqui): {len(is_dias)} pregões, "
          f"{is_dias[0]} a {is_dias[-1]}")
    print(f"      OOS (janela cega)                     : {len(oos_dias)} pregões, "
          f"{oos_dias[0]} a {oos_dias[-1]}")
    print(flush=True)

    linhas = []
    for rot, dias in (("5 meses (TOTAL)", pregoes),
                      ("  ├ parte IS", is_dias),
                      ("  └ parte OOS (cega)", oos_dias)):
        linha, trades, be, ic = _mede(rot, get_daytrade_robot("win_retangulo"),
                                      df, dias, capital)
        linhas.append((rot, linha, trades, be, ic, dias))
    print(tabela([x[1] for x in linhas], extras=EXTRAS))

    print("\n" + "=" * 172)
    print("MÊS A MÊS — a série inteira corrida de uma vez, partindo de R$1.100")
    print("=" * 172)
    _rot, _linha, trades, _be, _ic = linhas[0][:5]
    por_dia: dict = {}
    for t in trades:
        por_dia.setdefault(t.exit_ts.date(), []).append(t)
    print(f"  {'mês':<10}{'pregões':>9}{'c/ ops':>8}{'ops':>6}{'acertos':>9}"
          f"{'result. R$':>13}{'caixa ao fim':>15}{'ctr máx':>9}{'melhor dia':>13}{'pior dia':>12}")
    caixa = capital
    meses = sorted({(d.year, d.month) for d in pregoes})
    for ano, mes in meses:
        dd = [d for d in pregoes if (d.year, d.month) == (ano, mes)]
        ops = [t for d in dd for t in por_dia.get(d, [])]
        r = sum(t.pnl_brl for t in ops)
        caixa += r
        acertos = sum(1 for t in ops if t.pnl_brl > 0)
        qt = [int(getattr(t, "quantity", 1) or 1) for t in ops]
        dias_res = [sum(t.pnl_brl for t in por_dia.get(d, [])) for d in dd if por_dia.get(d)]
        print(f"  {pd.Timestamp(ano,mes,1).strftime('%b/%y'):<10}{len(dd):>9}"
              f"{len([d for d in dd if por_dia.get(d)]):>8}{len(ops):>6}"
              f"{f'{acertos}/{len(ops)}':>9}{br(r):>13}{br(caixa):>15}"
              f"{(max(qt) if qt else 0):>9}{br(max(dias_res)) if dias_res else '—':>13}"
              f"{br(min(dias_res)) if dias_res else '—':>12}")

    # ---- fechamento ------------------------------------------------------
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    qt = [int(getattr(t, "quantity", 1) or 1) for t in trades]
    liq = sum(t.pnl_brl for t in trades)
    pico_op = acum_op = dd_op = 0.0
    caixa_min = capital
    for t in trades:
        acum_op += t.pnl_brl
        pico_op = max(pico_op, acum_op)
        dd_op = max(dd_op, pico_op - acum_op)
        caixa_min = min(caixa_min, capital + acum_op)
    caixa_d = capital
    pico_d = capital
    dd_d = 0.0
    dias_pos = dias_neg = 0
    for d in pregoes:
        r = sum(t.pnl_brl for t in por_dia.get(d, []))
        caixa_d += r
        pico_d = max(pico_d, caixa_d)
        dd_d = max(dd_d, pico_d - caixa_d)
        if por_dia.get(d):
            if r > 0:
                dias_pos += 1
            elif r < 0:
                dias_neg += 1
    be = linhas[0][3]
    ic = linhas[0][4]

    print("\n" + "=" * 172)
    print("FECHAMENTO — os 5 meses corridos")
    print("=" * 172)
    print(f"  capital inicial              R$ {br(capital):>12}")
    print(f"  resultado do período         R$ {br(liq):>12}   ({br(100*liq/capital,1)}%)")
    print(f"  CAIXA FINAL                  R$ {br(capital+liq):>12}")
    print()
    print(f"  dias corridos                   {(pregoes[-1]-pregoes[0]).days+1:>12}")
    print(f"  pregões                         {len(pregoes):>12}")
    print(f"  pregões com operação            {len([d for d in pregoes if por_dia.get(d)]):>12}")
    print(f"  pregões sem operação            {len([d for d in pregoes if not por_dia.get(d)]):>12}")
    print(f"  pregões positivos / negativos   {f'{dias_pos} / {dias_neg}':>12}")
    print()
    print(f"  operações                       {len(trades):>12}")
    print(f"  acerto                          {br(100*len(g)/len(trades),1)+'%':>12}   "
          f"IC95 [{br(100*ic[0],1)} ; {br(100*ic[1],1)}] contra breakeven {br(100*be,1)}%")
    print(f"  média por operação           R$ {br(liq/len(trades)):>12}")
    print(f"  média por pregão             R$ {br(liq/len(pregoes)):>12}")
    print(f"  operações por pregão            {br(len(trades)/len(pregoes),1):>12}")
    print()
    print(f"  contratos máximos               {max(qt) if qt else 0:>12}")
    print(f"  contratos médios                {br(sum(qt)/len(qt),2) if qt else '—':>12}")
    print(f"  pior operação                R$ {br(min(p)) if p else '—':>12}")
    print(f"  melhor operação              R$ {br(max(g)) if g else '—':>12}")
    print()
    print(f"  pior queda (série DIÁRIA)    R$ {br(dd_d):>12}")
    print(f"  pior queda (por OPERAÇÃO)    R$ {br(dd_op):>12}   ← o que o portão de capital vê")
    print(f"  menor caixa da série         R$ {br(caixa_min):>12}   (margem crua do WIN@: R$100)")

    print("\n" + "=" * 172)
    print("COMO LER")
    print("=" * 172)
    print("  * A linha TOTAL mistura IS e OOS. Os parâmetros do robô foram escolhidos")
    print("    olhando o IS, então a parte cega (OOS) é a que informa — e ela está separada.")
    print("  * `fila NÃO CALIBRADA`: toda ordem-limite preenche no TOQUE. Quando essa")
    print("    premissa foi conferida contra extrato real no WDO, o motor errou o SINAL.")
    print("  * Backtest tem feed perfeito e nunca reinicia. A sombra perde barra: em 14/09")
    print("    o copa_win parou de receber barra às 10:31 com posição aberta e o ledger")
    print("    da sombra terminou R$138,50 otimista.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
