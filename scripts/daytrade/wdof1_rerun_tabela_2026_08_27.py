"""Re-rodada limpa do candidato WDO F1 maker (`WdoGridReloadMaker`, WDO@,
T1 S16 x1, leitura tick) nas tres janelas, so' para produzir a tabela pedida
pelo dono: Trades / Liquido / R$ por pregao / Lucro por trade / MaxDD / Calmar.

Nao redescobre nada: reusa `carregar_tick_bars` (IS), `carregar_oos_bars`
(OOS ja destravado em 2026-08-27) e `montar_config`/`rodar` dos labs
existentes, entao os numeros sao comparaveis com o que ja esta registrado.

`Calmar` aqui e' `liquido R$ / MaxDD R$` -- a convencao deste motor
(`backtest/intraday/report.py`): anualizar uma janela de semanas AMPLIFICA o
numero em vez de estima-lo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wdo_grid_reload_f1_lab import CANDIDATO_PARAMS, montar_config, rodar  # noqa: E402
from wdo_grid_reload_f1_tick_lab import carregar_tick_bars  # noqa: E402
from wdo_grid_reload_f1_tick_lab_oos_2026_08_27 import carregar_oos_bars  # noqa: E402


def maxdd_e_pico(trades) -> tuple[float, float]:
    """MaxDD da curva de P&L realizado, trade a trade (mesma leitura usada em
    toda a escada de capital desta frente)."""
    eq = 0.0
    pico = 0.0
    dd = 0.0
    for t in trades:
        eq += t.pnl_brl
        pico = max(pico, eq)
        dd = max(dd, pico - eq)
    return dd, eq


def pregoes(trades) -> int:
    return len({t.exit_ts.date() for t in trades})


def linha(rotulo: str, res) -> dict:
    tr = res.trades
    liq = sum(t.pnl_brl for t in tr)
    dd, _ = maxdd_e_pico(tr)
    n_preg = pregoes(tr)
    return {
        "janela": rotulo,
        "pregoes": n_preg,
        "trades": len(tr),
        "liquido": liq,
        "por_pregao": liq / n_preg if n_preg else float("nan"),
        "por_trade": liq / len(tr) if tr else float("nan"),
        "maxdd": dd,
        "calmar": liq / dd if dd > 0 else float("inf"),
    }


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def main() -> None:
    cfg = montar_config()
    print(f"candidato: T{CANDIDATO_PARAMS['profit_ticks']} S{CANDIDATO_PARAMS['stop_ticks']} "
          f"x{CANDIDATO_PARAMS['level_spacing_ticks']} | WDO@ | leitura tick | "
          f"1 contrato | pedagio de fila 0")
    print(f"custo: tarifa real + slippage do perfil, "
          f"limit_fill_capped_by_volume={cfg.limit_fill_capped_by_volume}\n")

    print("[1/3] carregando tick do IS ...", flush=True)
    dias_is, bars_is = carregar_tick_bars()
    print(f"      {len(bars_is):,} barras tick, {len(dias_is)} pregoes", flush=True)

    print("[2/3] carregando OOS (tick + fallback M1) ...", flush=True)
    oos = carregar_oos_bars()
    bars_oos = oos["bars_mixed"]
    print(f"      {len(bars_oos):,} barras, {len(oos['dias_oos'])} pregoes "
          f"({len(oos['dias_tick'])} tick + {len(oos['dias_m1_fallback'])} M1)", flush=True)

    print("[3/3] rodando o motor nas tres janelas ...\n", flush=True)
    bars_comb = pd.concat([bars_is, bars_oos]).sort_index()

    linhas = []
    for rotulo, bars in (("IS", bars_is), ("OOS", bars_oos), ("IS+OOS", bars_comb)):
        res = rodar(bars, cfg)
        l = linha(rotulo, res)
        linhas.append(l)
        print(f"  {rotulo:7s} pronto: {l['trades']} trades, R$ {br(l['liquido'])}", flush=True)

    print()
    cab = (f"| {'Candidato':17s} | {'Janela':7s} | {'Trades':>7s} | {'Liquido':>12s} | "
           f"{'R$/pregao':>10s} | {'Lucro/trade':>11s} | {'MaxDD':>9s} | {'Calmar':>7s} |")
    print(cab)
    print("|" + "|".join("-" * (len(c) + 2) for c in
                         ["Candidato".ljust(17), "Janela!".ljust(7), "Trades!".rjust(7),
                          "Liquido!".rjust(12), "R$/pregao!".rjust(10),
                          "Lucro/trade".rjust(11), "MaxDD!".rjust(9), "Calmar!".rjust(7)]) + "|")
    for l in linhas:
        print(f"| {'WDO F1 maker':17s} | {l['janela']:7s} | {l['trades']:>7,} | "
              f"{br(l['liquido']):>12s} | {br(l['por_pregao']):>10s} | "
              f"{br(l['por_trade'], 3):>11s} | {br(l['maxdd']):>9s} | "
              f"{br(l['calmar'], 1):>7s} |")
    print(f"\npregoes: " + " · ".join(f"{l['janela']}={l['pregoes']}" for l in linhas))


if __name__ == "__main__":
    main()
