"""Grade INDEPENDENTE alvo x stop (motor M1) para UM simbolo da familia
`gremah`, com o CAPITAL MINIMO REAL do ativo -- nao um numero de teste
digitado a mao.

CORRECAO (2026-08-27): a 1a versao deste script (so' para BMGB4) usava
`initial_capital=50_000` fixo e uma tabela impressa a mao, com `enforce_
capital_minimo=False`. O dono apontou os dois erros ao mesmo tempo: (1)
capital arbitrario em vez do minimo REAL de cada ativo
(`strategy.daytrade.base.capital_minimo_brl`, o mesmo numero que TODO outro
script do repo usa via `config_for(..., preco_atual=preco_ref)`), e (2) a
regra ja escrita no AGENTS.md ("Saida de backtest: uma tabela so") que exige
`backtest/intraday/report.py` -- que ja' TEM `capital final` como coluna
fixa -- em vez de tabela improvisada.

Efeito colateral honesto de ligar o capital real + o portao (`enforce_
capital_minimo`, default True pra acao): celulas da grade podem pular
sessoes diferentes entre si (a mesma distorcao ja documentada na confirmacao
OOS -- ver `pulou Nd` no aviso de `linha_de_resultado`), entao "capital
final" de duas celulas so' e' comparavel olhando tambem quantos pregoes cada
uma realmente operou. A tabela imprime os `pregoes` (total da janela) e o
aviso de pulo quando existe -- leia os dois juntos, nao so' o capital final.

IN-SAMPLE apenas -- rodar a grade inteira no OOS gastaria o holdout numa
busca (ver `copa_oos_gasto_2026_08_26`/`holdout_frozen_2026_08_20`). Padrao
do projeto: escolher o candidato no IS, confirmar UMA vez no OOS
(`confirm_oos_ticks.py` / `bmgb4_confirm_oos_t1s6_2026_08_27.py`).

Uso:
    python scripts/daytrade/alvo_stop_grid_2026_08_27.py --symbol BMGB4
    python scripts/daytrade/alvo_stop_grid_2026_08_27.py --symbol PMAM3 --jobs 6
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _geometria_comum import Economics, SIMBOLOS, carregar_economics, carregar_is  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402

TICKS_MIN, TICKS_MAX = 1, 22  # R$0,01 a R$0,22 (tick_size=0,01)

# Preenchidos pelo `_init_worker` -- 1x por PROCESSO, nunca por celula.
_SYMBOL = None
_BARS = None
_PROFILE = None
_ECON: Economics | None = None
_PRECO_REF = None


def _init_worker(symbol: str, econ: Economics) -> None:
    global _SYMBOL, _BARS, _PROFILE, _ECON, _PRECO_REF
    _SYMBOL = symbol
    _BARS, _PROFILE, _PRECO_REF = carregar_is(symbol, "m1")
    _ECON = econ


def _rodar(strat: Gremah, label: str):
    config = config_for(
        _PROFILE, trade_tick_value=_ECON.trade_tick_value, trade_tick_size=_ECON.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=_PRECO_REF,
    )
    result = run_intraday_backtest(_BARS, strat, config)
    return linha_de_resultado(label, result, capital_minimo_brl(_PRECO_REF))


def _celula(profit_ticks: int, stop_ticks: int):
    strat = Gremah(symbol=_SYMBOL, profit_ticks=profit_ticks, spacing_ticks=profit_ticks,
                    stop_ticks=stop_ticks)
    return (profit_ticks, stop_ticks, _rodar(strat, f"T{profit_ticks} E{profit_ticks} S{stop_ticks}"))


def _baseline():
    strat = Gremah(symbol=_SYMBOL)  # sem override = producao real
    rotulo = ("producao (vol-adapt)" if strat.alvo_por_volatilidade
              else f"producao (ticks {strat.profit_ticks}/{strat.spacing_ticks}/{strat.stop_ticks})"
              if strat.profit_ticks is not None
              else f"producao ({strat.profit_pct*100:.2f}%/{strat.stop_multiplier:.0f}x)")
    return _rodar(strat, rotulo)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, choices=sorted(SIMBOLOS))
    parser.add_argument("--jobs", type=int, default=6,
                        help="processos em paralelo (default 6 -- deixa nucleo pros robos ao vivo)")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    cache = ROOT / "data" / "_economics_cache.json"
    econ = carregar_economics([args.symbol], cache)[args.symbol]

    pares = [(a, s) for a in range(TICKS_MIN, TICKS_MAX + 1) for s in range(TICKS_MIN, TICKS_MAX + 1)]
    print(f"[grid] {args.symbol}: {len(pares)} celulas + baseline, {args.jobs} processo(s), "
          f"capital = minimo real do ativo, IN-SAMPLE only", flush=True)

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs, initializer=_init_worker,
                              initargs=(args.symbol, econ)) as pool:
        fut_baseline = pool.submit(_baseline)
        futures = {pool.submit(_celula, a, s): (a, s) for a, s in pares}

        base = fut_baseline.result()
        capital_inicial = base.capital_final - base.liquido_brl
        print(f"[baseline] capital inicial R$ {num_br(capital_inicial, 2)}")
        print(cabecalho())
        print(linha(base), flush=True)
        linhas = [base]

        feitos = 0
        for future in as_completed(futures):
            _a, _s, item = future.result()
            linhas.append(item)
            feitos += 1
            if feitos % 40 == 0 or feitos == len(pares):
                print(f"[grid] {feitos}/{len(pares)} celulas ({time.time()-t0:.0f}s decorridos)",
                      flush=True)

    print("")
    top = sorted(linhas[1:], key=lambda item: item.capital_final, reverse=True)[:args.top]
    print(f"=== {args.symbol} -- top {args.top} celulas (de {len(pares)}), "
          f"capital inicial R$ {num_br(capital_inicial, 2)} ===")
    print(cabecalho())
    print(linha(base), flush=True)
    for item in top:
        print(linha(item), flush=True)


if __name__ == "__main__":
    main()
