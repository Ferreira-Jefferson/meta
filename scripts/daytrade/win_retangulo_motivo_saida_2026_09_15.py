# -*- coding: utf-8 -*-
"""`win_retangulo` -- DECOMPOSICAO por MOTIVO DE SAIDA, nas duas janelas.

Pergunta do dono: a margem de 0,2pp do OOS pode crescer por ECONOMIA da
operacao (ganho medio maior / perda media menor), nao por mais amostra. O
breakeven empirico (perda_media / (ganho_medio + perda_media)) e' um
AGREGADO -- antes de propor qualquer mudanca de geometria e' preciso saber
QUAL caminho de saida domina cada lado dele. Sem este mapa toda proposta
seria chute.

## O que este script faz e o que NAO faz

Roda o robo de PRODUCAO (`strategy.daytrade.registry.get_daytrade_robot`,
defaults congelados) nas duas janelas oficiais (IS < 2026-06-13, OOS >=
2026-06-13, capital R$1.100, MIN_BARRAS_POR_PREGAO=400 -- a mesma regua de
`win_retangulo_regua_padrao_2026_09_15.py`) e classifica CADA operacao pelo
`IntradayExitReason` do motor (`core.models.IntradayExitReason`) mais o
sub-motivo `exit_detail` ("target_timeout": a fatia do alvo estourou o prazo
e fechou a MERCADO -- mora dentro de TARGET no enum mas paga custo diferente).

Para cada motivo: n, % da amostra, PnL medio, soma, e quanto ele CONTRIBUI
para o ganho medio agregado (soma dos ganhos daquele motivo / total de
trades) e para a perda media agregada (soma das perdas daquele motivo, em
modulo / total de trades) -- e' essa decomposicao que explica de onde vem
gm e pm, e portanto de onde vem o breakeven.

Isto NAO propoe regra de saida nenhuma (24 regras de gestao ja foram
medidas e refutadas no copa_win -- ver LICOES_DE_PRODUCAO.md). E' mapa, nao
receita.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_motivo_saida_2026_09_15.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from core.models import IntradayExitReason  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
#: mesmo corte de `win_retangulo_regua_padrao_2026_09_15.py`: HOJE e' pregao
#: PARCIAL (dado so' ate 17:23 BRT, achatamento das 18:20 ainda nao aconteceu)
#: e fica de fora do OOS -- inclui-lo mudaria n=179->182 e pregoes 64->65 sem
#: aviso, deixando de bater com o numero OFICIAL do dono.
HOJE = pd.Timestamp("2026-09-15").date()
CAPITAL = float(get_daytrade_robot("win_retangulo").capital_minimo_recomendado_brl)
MIN_BARRAS_POR_PREGAO = 400


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _categoria(t) -> str:
    if t.exit_reason == IntradayExitReason.TARGET and t.exit_detail == "target_timeout":
        return "alvo (estouro prazo, a mercado)"
    if t.exit_reason == IntradayExitReason.TARGET:
        return "alvo (limite, preenchido)"
    if t.exit_reason == IntradayExitReason.STOP:
        return "stop (a mercado)"
    if t.exit_reason == IntradayExitReason.FORCED_FLATTEN:
        return "achatamento de fim de pregao"
    if t.exit_reason == IntradayExitReason.SIGNAL:
        return "sinal (reversao)"
    return f"outro ({t.exit_reason})"


def _unidade(args):
    rotulo, dias = args
    strat = get_daytrade_robot("win_retangulo")
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
    return dict(rotulo=rotulo, trades=trades)


def main():
    df = load_m1(get_daytrade_robot("win_retangulo").symbol).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    print("=" * 118)
    print("win_retangulo -- DECOMPOSICAO por MOTIVO DE SAIDA (IS e OOS, regua padrao)")
    print("=" * 118)
    print(f"  capital R$ {br(CAPITAL,0)} | IS {len(IS)} pregoes | OOS {len(OOS)} pregoes\n",
          flush=True)

    tarefas = [("IS  (< 2026-06-13)", IS), ("OOS (>= 2026-06-13)", OOS)]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[r["rotulo"]] = r
            print(f"  ok {r['rotulo']}: {len(r['trades'])} trades", flush=True)

    ordem_cat = [
        "alvo (limite, preenchido)",
        "alvo (estouro prazo, a mercado)",
        "stop (a mercado)",
        "achatamento de fim de pregao",
        "sinal (reversao)",
    ]

    for rot, _d in tarefas:
        trades = out[rot]["trades"]
        n_total = len(trades)
        if n_total == 0:
            print(f"\n  {rot}: nenhuma operacao")
            continue
        cats = {}
        for t in trades:
            c = _categoria(t)
            cats.setdefault(c, []).append(t.pnl_brl)
        # garante que categorias conhecidas apareçam mesmo com n=0, na ordem certa
        for c in ordem_cat:
            cats.setdefault(c, [])
        outras = [c for c in cats if c not in ordem_cat]

        soma_ganhos = sum(p for p in (t.pnl_brl for t in trades) if p > 0)
        soma_perdas = sum(p for p in (t.pnl_brl for t in trades) if p <= 0)
        n_ganhos = sum(1 for t in trades if t.pnl_brl > 0)
        n_perdas = sum(1 for t in trades if t.pnl_brl <= 0)
        gm = soma_ganhos / n_ganhos if n_ganhos else 0.0
        pm = abs(soma_perdas / n_perdas) if n_perdas else 0.0
        be = pm / (gm + pm) if (n_ganhos and n_perdas) else float("nan")

        print("\n" + "=" * 118)
        print(f"{rot} -- {n_total} operacoes | ganho medio R${br(gm)} | "
              f"perda media R${br(pm)} | breakeven empirico "
              f"{br(100*be,1) if be==be else '--'}%")
        print("=" * 118)
        print(f"  {'motivo':<34}{'n':>6}{'% amostra':>11}{'R$/op':>10}{'soma R$':>12}"
              f"{'contrib. ganho medio':>23}{'contrib. perda media':>23}")
        for c in ordem_cat + outras:
            vals = cats[c]
            n = len(vals)
            if n == 0:
                print(f"  {c:<34}{0:>6}{'0,0%':>11}{'—':>10}{'—':>12}"
                      f"{'0,00':>23}{'0,00':>23}")
                continue
            soma = sum(vals)
            media = soma / n
            ganhos_c = sum(v for v in vals if v > 0)
            perdas_c = sum(v for v in vals if v <= 0)
            contrib_gm = ganhos_c / n_total if n_total else 0.0
            contrib_pm = abs(perdas_c) / n_total if n_total else 0.0
            pct = 100.0 * n / n_total
            print(f"  {c:<34}{n:>6}{br(pct,1)+'%':>11}{br(media):>10}{br(soma):>12}"
                  f"{br(contrib_gm):>23}{br(contrib_pm):>23}")
        print(f"  {'TOTAL':<34}{n_total:>6}{'100,0%':>11}{br(sum(t.pnl_brl for t in trades)/n_total):>10}"
              f"{br(sum(t.pnl_brl for t in trades)):>12}{br(gm*n_ganhos/n_total):>23}"
              f"{br(pm*n_perdas/n_total):>23}")
        print("  (a soma das colunas 'contrib.' bate com ganho_medio*n_ganhos/n_total e")
        print("   perda_media*n_perdas/n_total -- e' a mesma decomposicao, so' dividida por motivo)")

    print("\n" + "=" * 118)
    print("LEITURA")
    print("=" * 118)
    print("  O breakeven empirico e' pm/(gm+pm). Qualquer motivo que pesa MUITO do lado da")
    print("  perda (tipicamente o stop, a mercado, geometria fixa em 0,50xL) e' dificil de")
    print("  atacar sem mudar a geometria estrutural (ja varrida: platô 39/42). Um motivo do")
    print("  lado do GANHO que contribuir pouco (ex.: alvo raramente completa antes do")
    print("  achatamento, ou completa mas com valor medio baixo) e' onde uma mudanca de")
    print("  ECONOMIA (nao de regra de gestao) teria alavanca.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
