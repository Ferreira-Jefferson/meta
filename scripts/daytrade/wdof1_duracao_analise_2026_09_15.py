"""Le o CSV produzido por `wdof1_duracao_operacao_2026_09_15.py` e imprime a
distribuicao conjunta DURACAO x RESULTADO das operacoes do WDO F1.

Tres leituras, nesta ordem:
  1. duracao por DESFECHO (alvo vs stop) -- mostra o quanto do padrao e'
     mecanica da geometria;
  2. faixa de duracao x R$/op, win% e composicao -- e' a tabela que o dono
     montou no olho, com n grande;
  3. o corte NAIVE (somar o que aconteceu acima/abaixo de N min) -- que e'
     exatamente a leitura que NAO vale como decisao, impressa aqui so' para
     poder ser comparada com a Parte B (corte de verdade, no motor).

Uso: `python -u scripts/daytrade/wdof1_duracao_analise_2026_09_15.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CSV = RAIZ / "scratch" / "wdof1_duracao_operacoes_2026_09_15.csv"

FAIXAS = [(0, 0.5), (0.5, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6),
          (6, 8), (8, 10), (10, 15), (15, 20), (20, 30), (30, 10 ** 9)]


def rotulo(a: float, b: float) -> str:
    return f">{a:g}" if b > 10 ** 8 else f"{a:g}-{b:g}"


def bloco(df: pd.DataFrame, titulo: str) -> None:
    print("=" * 118)
    print(titulo + f"   (n={len(df)}, {df['dia'].nunique()} pregoes)")
    print("=" * 118)
    if df.empty:
        print("  sem operacoes\n")
        return
    dur = df["dur_s"] / 60.0
    print(f"  liquido R${df['pnl'].sum():+,.2f}   R$/op {df['pnl'].mean():+.3f}   "
          f"win% {100 * (df['pnl'] > 0).mean():.2f}   "
          f"duracao: mediana {dur.median():.2f} min, media {dur.mean():.2f}, "
          f"p90 {dur.quantile(.9):.2f}, max {dur.max():.1f}")
    print()
    print("  -- duracao por DESFECHO --")
    print(f"  {'motivo':<10}{'n':>7}{'%':>7}{'mediana':>10}{'media':>9}{'p10':>8}"
          f"{'p25':>8}{'p75':>9}{'p90':>9}{'R$/op':>9}")
    for mot, sub in df.groupby("reason"):
        d = sub["dur_s"] / 60.0
        print(f"  {mot:<10}{len(sub):>7}{100 * len(sub) / len(df):>6.1f}%{d.median():>10.2f}"
              f"{d.mean():>9.2f}{d.quantile(.1):>8.2f}{d.quantile(.25):>8.2f}"
              f"{d.quantile(.75):>9.2f}{d.quantile(.9):>9.2f}{sub['pnl'].mean():>9.2f}")
    print()
    print("  -- faixa de duracao (minutos) --")
    print(f"  {'faixa':>10}{'n':>8}{'% do n':>8}{'win%':>8}{'liquido':>13}{'R$/op':>9}"
          f"{'stops':>8}{'% stops':>9}")
    for a, b in FAIXAS:
        sel = df[(dur >= a) & (dur < b)]
        if sel.empty:
            continue
        st = int((sel["reason"] == "stop").sum())
        print(f"  {rotulo(a, b):>10}{len(sel):>8}{100 * len(sel) / len(df):>7.1f}%"
              f"{100 * (sel['pnl'] > 0).mean():>7.1f}%{sel['pnl'].sum():>13,.2f}"
              f"{sel['pnl'].mean():>9.2f}{st:>8}{100 * st / len(sel):>8.1f}%")
    print()
    print("  -- corte NAIVE (soma do que ja aconteceu; NAO e' simulacao de corte) --")
    print(f"  {'corte':>8}{'n abaixo':>10}{'R$/op <':>9}{'liq <':>13}"
          f"{'n acima':>10}{'R$/op >':>9}{'liq >':>13}{'win% >':>8}")
    for k in (1, 2, 3, 4, 5, 6, 8, 10, 15):
        ab, ac = df[dur < k], df[dur >= k]
        if ac.empty or ab.empty:
            continue
        print(f"  {k:>6} min{len(ab):>10}{ab['pnl'].mean():>9.2f}{ab['pnl'].sum():>13,.2f}"
              f"{len(ac):>10}{ac['pnl'].mean():>9.2f}{ac['pnl'].sum():>13,.2f}"
              f"{100 * (ac['pnl'] > 0).mean():>7.1f}%")
    print()


def main() -> None:
    if not CSV.exists():
        raise SystemExit(f"[erro] rode antes o wdof1_duracao_operacao_2026_09_15.py ({CSV})")
    df = pd.read_csv(CSV)
    dias = sorted(df["dia"].unique())
    corte = round(len(dias) * 2 / 3)
    is_dias, oos_dias = set(dias[:corte]), set(dias[corte:])

    for cap, nome in [(15000.0, "DIAGNOSTICA R$15.000 (1 contrato, SEM censura de caixa) -- "
                                "e' a leitura valida da DISTRIBUICAO, nao de retorno"),
                      (375.0, "PRODUCAO R$375 (censurada pelo portao de capital)")]:
        d = df[df["capital"] == cap]
        bloco(d, f"[{nome}] BASE INTEIRA")
        bloco(d[d["dia"].isin(is_dias)], f"[{nome}] IS")
        bloco(d[d["dia"].isin(oos_dias)], f"[{nome}] OOS")


if __name__ == "__main__":
    main()
