# -*- coding: utf-8 -*-
"""`win_retangulo` em DOIS MESES, partindo do caixa minimo e sem nenhum aporte.

Pedido do dono (2026-09-16): "rode um teste com dois meses iniciando com o
capital minimo e usando somente este capital, veja quanto fica ate' a data de
16/09, mostre quantos pregoes, quantos dias, lucro/prejuizo dia, max contratos,
etc".

## A janela

2026-07-16 a 2026-09-16. **O pregao de 16/09 ainda nao aconteceu** -- este
script rodou as 00:28 BRT de 16/09, antes da abertura --, entao a serie termina
no ultimo pregao real, 15/09. A base M1 canonica confirma: o ultimo dia com
barra e' 2026-09-15 (561 barras).

## "Usando somente este capital"

Capital inicial = `capital_minimo_recomendado_brl` do robo (R$1.100, que e' o
pior rebaixamento POR OPERACAO medido no IS + a margem crua do WIN@). Nenhum
aporte: o caixa e' o inicial + P&L realizado, e e' ele que dimensiona a proxima
entrada (`on_capital_update` a cada barra). Se cair abaixo da margem, o motor
recusa a entrada -- e isso aparece como pregao sem operar, nao como erro.

A escada de contratos (`WinRetangulo._dimensiona`): `C(n) = R$1.100 x n^1,415`,
ou seja 1 contrato em R$1.100, 2 em R$2.933, 3 em R$5.206, 4 em R$7.822.

## Ressalvas que andam com o numero

- A janela esta INTEIRA dentro do OOS (>= 2026-06-13), que ja foi medido. E'
  um ZOOM nas mesmas operacoes, nao evidencia nova.
- Dois meses nao produzem veredito: o intervalo do acerto e' largo demais.
- `fila NAO CALIBRADA`: o WIN@ nao tem entrada em `backtest/intraday/
  fidelidade.py`, entao toda ordem-limite preenche no TOQUE, dos dois lados.
  Premissa otimista na entrada E no alvo, honesta so' no stop (a mercado).
- Tudo passa por `config_for`, o mesmo construtor de configuracao do caminho ao
  vivo, com a mesma classe `WinRetangulo` que o `registry` entrega ao runtime.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_dois_meses_caixa_unico_2026_09_16.py`
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

INICIO = pd.Timestamp("2026-07-16").date()
FIM = pd.Timestamp("2026-09-16").date()
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


def main():
    robo = get_daytrade_robot("win_retangulo")
    capital = float(robo.capital_minimo_recomendado_brl)
    df = load_m1(robo.symbol).sort_index()
    contagem = df.groupby(df.index.date).size()
    pregoes = sorted(d for d, n in contagem.items()
                     if n >= MIN_BARRAS_POR_PREGAO and INICIO <= d <= FIM)

    profile = profile_for(robo.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=capital,
        target_fills_as_maker=robo.target_fills_as_maker,
        anchor_exits_at_fill=robo.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True)
    alvo = set(pregoes)
    bars = df[[d in alvo for d in df.index.date]]
    res = run_intraday_backtest(bars, robo, cfg)
    trades = list(res.trades)

    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    qt = [int(getattr(t, "quantity", 1) or 1) for t in trades]
    liquido = sum(t.pnl_brl for t in trades)
    pts = ((liquido / len(trades)) / 0.20) if trades else float("nan")
    com_trade = {t.exit_ts.date() for t in trades}

    corridos = (pregoes[-1] - pregoes[0]).days + 1
    print("=" * 172)
    print("win_retangulo — DOIS MESES, caixa mínimo e nenhum aporte")
    print("=" * 172)
    print(f"  janela pedida : {INICIO} a {FIM}")
    print(f"  janela medida : {pregoes[0]} a {pregoes[-1]}")
    print(f"  16/09 NÃO entrou: o pregão ainda não tinha aberto quando isto rodou "
          f"(00:28 BRT); último dia com barra na base é {max(contagem.index)}")
    print()
    print(f"  dias corridos            : {corridos}")
    print(f"  PREGÕES no período       : {len(pregoes)}")
    print(f"  pregões COM operação     : {len(com_trade)}")
    print(f"  pregões SEM operação     : {len(pregoes) - len(com_trade)}")
    print(f"  capital inicial          : R$ {br(capital)}  (piso medido, sem aporte)")
    print(f"  fila                     : NÃO CALIBRADA (preenche no toque, dos dois lados)")
    print(flush=True)

    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "ctr max": str(max(qt)) if qt else "—",
        "ctr méd": br(sum(qt) / len(qt), 2) if qt else "—",
        "sem trade": f"{len(pregoes)-len(com_trade)}/{len(pregoes)}",
        "pior op.": br(min(p)) if p else "—",
        "melhor op.": br(max(g)) if g else "—",
    }
    linha = linha_de_resultado(f"2 meses ({len(pregoes)} pregões)", res, capital,
                               extras=extras)
    print(tabela([linha], extras=EXTRAS))

    # ---- pregão a pregão -------------------------------------------------
    por_dia: dict = {}
    for t in trades:
        por_dia.setdefault(t.exit_ts.date(), []).append(t)

    print("\n" + "=" * 172)
    print("PREGÃO A PREGÃO — lucro/prejuízo do dia e o caixa correndo")
    print("=" * 172)
    print(f"  {'pregão':<9}{'dia':<11}{'ops':>5}{'acertos':>9}{'ctr máx':>9}"
          f"{'result. do dia':>16}{'caixa ao fim':>15}{'pico':>13}{'do pico':>10}")
    caixa = capital
    pico = capital
    acum_dd = 0.0
    melhor_dia = (None, float("-inf"))
    pior_dia = (None, float("inf"))
    positivos = negativos = zerados = 0
    for d in pregoes:
        ops = por_dia.get(d, [])
        r = sum(t.pnl_brl for t in ops)
        caixa += r
        pico = max(pico, caixa)
        acum_dd = max(acum_dd, pico - caixa)
        acertos = sum(1 for t in ops if t.pnl_brl > 0)
        ctr = max([int(getattr(t, "quantity", 1) or 1) for t in ops], default=0)
        if ops:
            if r > 0:
                positivos += 1
            elif r < 0:
                negativos += 1
            else:
                zerados += 1
            if r > melhor_dia[1]:
                melhor_dia = (d, r)
            if r < pior_dia[1]:
                pior_dia = (d, r)
        print(f"  {d.strftime('%d/%m'):<9}{pd.Timestamp(d).day_name()[:9]:<11}"
              f"{(len(ops) or '—'):>5}{(f'{acertos}/{len(ops)}' if ops else '—'):>9}"
              f"{(ctr or '—'):>9}{(br(r) if ops else '—'):>16}{br(caixa):>15}"
              f"{br(pico):>13}{br(caixa-pico):>10}")

    # ---- rebaixamento por OPERAÇÃO (o que o portão de capital vê) --------
    pico_op = acum_op = dd_op = 0.0
    caixa_min = capital
    for t in trades:
        acum_op += t.pnl_brl
        pico_op = max(pico_op, acum_op)
        dd_op = max(dd_op, pico_op - acum_op)
        caixa_min = min(caixa_min, capital + acum_op)

    ic = _ic95(len(g), len(trades))
    print("\n" + "=" * 172)
    print("FECHAMENTO")
    print("=" * 172)
    print(f"  capital inicial              R$ {br(capital):>12}")
    print(f"  resultado do período         R$ {br(liquido):>12}   "
          f"({br(100*liquido/capital,1)}%)")
    print(f"  CAIXA FINAL                  R$ {br(caixa):>12}")
    print()
    print(f"  operações                       {len(trades):>12}")
    print(f"  acerto                          {br(100*len(g)/len(trades),1)+'%':>12}   "
          f"IC95 [{br(100*ic[0],1)} ; {br(100*ic[1],1)}] contra breakeven {br(100*be,1)}%")
    print(f"  média por operação           R$ {br(liquido/len(trades)):>12}   "
          f"({br(pts,1)} pontos)")
    print(f"  média por pregão             R$ {br(liquido/len(pregoes)):>12}")
    print(f"  operações por pregão            {br(len(trades)/len(pregoes),1):>12}")
    print()
    print(f"  pregões positivos               {positivos:>12}")
    print(f"  pregões negativos               {negativos:>12}")
    print(f"  pregões sem operar              {len(pregoes)-len(com_trade):>12}")
    print(f"  melhor pregão                R$ {br(melhor_dia[1]):>12}   "
          f"({melhor_dia[0].strftime('%d/%m') if melhor_dia[0] else '—'})")
    print(f"  pior pregão                  R$ {br(pior_dia[1]):>12}   "
          f"({pior_dia[0].strftime('%d/%m') if pior_dia[0] else '—'})")
    print()
    print(f"  contratos máximos               {max(qt) if qt else 0:>12}")
    print(f"  contratos médios                {br(sum(qt)/len(qt),2) if qt else '—':>12}")
    print(f"  pior operação                R$ {br(min(p)) if p else '—':>12}")
    print(f"  melhor operação              R$ {br(max(g)) if g else '—':>12}")
    print()
    print(f"  pior queda (série DIÁRIA)    R$ {br(acum_dd):>12}")
    print(f"  pior queda (por OPERAÇÃO)    R$ {br(dd_op):>12}   "
          f"← é esta que o portão de capital vê")
    print(f"  menor caixa da série         R$ {br(caixa_min):>12}   "
          f"(margem crua do WIN@ é R$100)")

    print("\n" + "=" * 172)
    print("COMO LER")
    print("=" * 172)
    print("  * A janela está INTEIRA dentro do OOS já medido: é zoom nas mesmas operações,")
    print("    não evidência nova. Dois meses não produzem veredito.")
    print("  * `fila NÃO CALIBRADA` é a ressalva que mais pesa: toda ordem-limite preenche")
    print("    no TOQUE. Quando essa premissa foi conferida contra extrato real no WDO, o")
    print("    motor errou o SINAL do resultado (+R$3,82/op previsto contra −R$3,00 real).")
    print("  * Mesma classe `WinRetangulo` e mesmo `config_for` do caminho ao vivo.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
