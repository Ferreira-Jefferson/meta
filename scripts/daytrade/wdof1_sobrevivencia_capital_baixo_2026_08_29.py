"""Varredura pedida pelo dono em 2026-08-29, reagindo direto ao numero de
sobrevivencia da reversao de `stop_ticks` (16, ver a nota no topo de
`strategy/daytrade/lab/wdo_grid_reload_maker.py`): "se so tenho o capital
minimo inicial (R$375), do que me adianta saber que nao trava a partir de
R$5.000? Eu quero que a partir do capital minimo ele ja tenha lucros e
lucros consistentes."

Pergunta literal respondida aqui: dentre TODAS as configuracoes de
`stop_ticks` ja mapeadas pela grade completa 1..20 (`profit_ticks=1` fixo --
"T1" e' vencedor isolado em toda varredura anterior do robo, nunca disputado),
existe ALGUMA que sobrevive (nunca trava por capital) E fecha positiva
rodando o historico M1 SALVO INTEIRO (177 pregoes, 2025-12-09 -> 2026-08-28,
capital REAL nao nocional) a partir de perto do piso de tabela (R$375), em vez
de precisar dos R$5.000 medidos para o default atual (S16)?

## Por que isto e' uma pergunta DIFERENTE da que gerou o default atual

A escolha original de S4 (depois revertida) e a comparacao final S4 x S16
otimizaram "maior lucro" (nocional, sem checar capital real) ou "sobrevive a
QUALQUER capital dado" -- nenhuma das duas rodadas anteriores teve como
CRITERIO DE BUSCA "menor capital de sobrevivencia". Este script inverte o
alvo: fixa uma faixa de capital BAIXA (perto do piso real que o dono tem hoje)
e pergunta, pra cada stop_ticks, se sobrevive E lucra ali -- nao em algum
nivel de capital maior.

## Metodologia -- identica a `wdof1_stress_capital_real_historico_completo.py`

MESMO caminho de producao: `config_for(profile_for("WDO@"), ...)` SEM
`max_open_contracts`/`enforce_capital_cap` explicitos (o motor decide sozinho,
como em `scripts/run_live.py::build_intraday`), rodando o historico INTEIRO
numa unica passada continua (nunca reiniciando caixa por pregao -- e' isso que
deixa uma sequencia de perdas ATRAVESSAR dias e revela a trava por capital de
verdade, ver a docstring do script irmao). A UNICA diferenca e' variar
`stop_ticks` no construtor de `WdoGridReloadMaker` em vez de usar o default
da classe via `get_daytrade_robot()` -- os dois caminhos convergem quando
`stop_ticks=16` (o default atual), ja conferido.

`profit_ticks=1` e `level_spacing_ticks=1` fixos (nunca disputados por
nenhuma varredura anterior -- variar so' stop_ticks mantem o espaco de busca
no que ja foi validado como relevante).

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`) --
`feedback_parallelize_sweeps` / `feedback_stream_results_as_ready`: cada
combinacao (stop_ticks, capital) roda como uma unidade independente e imprime
o resultado assim que termina, sem esperar a rodada inteira.

Uso: `python -u scripts/daytrade/wdof1_sobrevivencia_capital_baixo_2026_08_29.py`
"""
from __future__ import annotations

import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SYMBOL = "WDO@"
STOP_TICKS_VALUES = [1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20]
NIVEIS_CAPITAL = [375.0, 500.0, 750.0, 1_000.0, 1_500.0, 2_000.0, 3_000.0, 5_000.0]
MIN_BARRAS_POR_PREGAO = 400

OUT_CSV = ROOT / "scripts" / "daytrade" / "wdof1_sobrevivencia_capital_baixo_2026_08_29.csv"

_BARS_CACHE = None  # por processo -- o pool reusa processos entre tarefas


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _bars_do_processo() -> pd.DataFrame:
    global _BARS_CACHE
    if _BARS_CACHE is None:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        _BARS_CACHE = df[[d in completos for d in df.index.date]]
    return _BARS_CACHE


def _roda(args):
    stop_ticks, capital = args
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker

    bars = _bars_do_processo()
    profile = profile_for(SYMBOL)
    strat = WdoGridReloadMaker(stop_ticks=stop_ticks)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=capital,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    liquido = sum(t.pnl_brl for t in resultado.trades)
    equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else capital
    dias_cobertos = len(set(pd.DatetimeIndex(resultado.equity_curve.index).date)) if not resultado.equity_curve.empty else 0

    return dict(
        stop_ticks=stop_ticks, capital=capital, dt=dt,
        trades=len(resultado.trades), liquido=liquido, equity_final=equity_final,
        dias_cobertos=dias_cobertos,
        recusadas_por_teto=resultado.ordens_recusadas_por_teto,
        zerou=resultado.wiped_out_at is not None,
    )


def main() -> None:
    combos = [(st, cap) for st in STOP_TICKS_VALUES for cap in NIVEIS_CAPITAL]
    n_workers = min(12, os.cpu_count() or 4)
    print(f"[wdof1_sobrevivencia] {len(combos)} combinacoes (stop_ticks x capital), "
          f"{n_workers} processos em paralelo, T1/x1 fixos\n", flush=True)

    t0 = time.perf_counter()
    linhas: list[dict] = []
    total_dias = None
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, combo): combo for combo in combos}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            linhas.append(r)
            feitos += 1
            if total_dias is None:
                total_dias = None  # preenchido abaixo via dias_cobertos maximo observado
            trava = "TRAVOU" if r["dias_cobertos"] < 170 and not r["zerou"] else ("ZEROU" if r["zerou"] else "ok")
            print(f"  [{feitos:3d}/{len(combos)} {r['dt']:5.1f}s] S{r['stop_ticks']:<2d} "
                  f"R${br(r['capital'],0):>8s} -> trades={r['trades']:5d} "
                  f"liquido=R${br(r['liquido']):>12s} final=R${br(r['equity_final']):>10s} "
                  f"dias_cobertos={r['dias_cobertos']:3d} recusadas={r['recusadas_por_teto']:5d} [{trava}]",
                  flush=True)

    print(f"\ntotal: {time.perf_counter()-t0:.1f}s\n", flush=True)

    dias_totais = max(l["dias_cobertos"] for l in linhas)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["stop_ticks", "capital", "trades", "liquido",
                                           "equity_final", "dias_cobertos", "recusadas_por_teto", "zerou"])
        w.writeheader()
        for l in linhas:
            w.writerow({k: l[k] for k in w.fieldnames})
    print(f"[wdof1_sobrevivencia] CSV salvo em {OUT_CSV}\n")

    print("=== para cada stop_ticks: MENOR capital (da lista testada) que cobre o historico INTEIRO "
          f"({dias_totais} pregoes) sem travar ===")
    print(f"{'stop_ticks':>10}{'capital minimo testado':>26}{'trades':>10}{'liquido':>16}{'final':>14}")
    print("-" * 80)
    algum_lucra_no_piso = []
    for st in STOP_TICKS_VALUES:
        candidatos = [l for l in linhas if l["stop_ticks"] == st and l["dias_cobertos"] >= dias_totais and not l["zerou"]]
        if not candidatos:
            print(f"{st:>10}{'nenhum nivel testado sobrevive':>26}")
            continue
        melhor = min(candidatos, key=lambda l: l["capital"])
        print(f"{st:>10}{('R$'+br(melhor['capital'],0)):>26}{melhor['trades']:>10}"
              f"{('R$'+br(melhor['liquido'])):>16}{('R$'+br(melhor['equity_final'])):>14}")
        if melhor["capital"] <= 1_000.0 and melhor["liquido"] > 0:
            algum_lucra_no_piso.append((st, melhor))

    print("\n=== resultado direto no PISO DE TABELA (R$375) para cada stop_ticks ===")
    print(f"{'stop_ticks':>10}{'trades':>10}{'liquido':>16}{'final':>14}{'dias_cobertos':>16}{'':>10}")
    print("-" * 80)
    for st in STOP_TICKS_VALUES:
        l = next(l for l in linhas if l["stop_ticks"] == st and l["capital"] == 375.0)
        trava = "TRAVOU" if l["dias_cobertos"] < dias_totais and not l["zerou"] else ("ZEROU" if l["zerou"] else "sobrevive")
        print(f"{st:>10}{l['trades']:>10}{('R$'+br(l['liquido'])):>16}{('R$'+br(l['equity_final'])):>14}"
              f"{l['dias_cobertos']:>16}{trava:>10}")

    print()
    if algum_lucra_no_piso:
        print(f"*** existe(m) {len(algum_lucra_no_piso)} configuracao(oes) que sobrevivem e "
              f"lucram com <= R$1.000: {[(st, m['capital']) for st, m in algum_lucra_no_piso]} ***")
    else:
        print("*** NENHUMA configuracao de stop_ticks (1..20, T1/x1) sobrevive E lucra com "
              "capital <= R$1.000 no historico inteiro -- a restricao e' estrutural ao "
              "desenho (posicao minima de 1 contrato + piso de margem), nao ao stop escolhido. ***")


if __name__ == "__main__":
    main()
