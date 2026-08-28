"""REFINO (rodada de ate' 3, ESTA E' A RODADA 1): testa as 3 variantes de
`src/strategy/daytrade/lab/win_daily_continuidade_refino.py` contra o
BASELINE `ContinuidadeDiaria(direction="reversal")` em WIN@ (+R$8.832,30
IS, 127 trades, 55,9% acerto; metade1 lucro/DD=2,26, metade2=0,34) -- ver a
docstring do modulo de estrategias para o DIAGNOSTICO completo que motiva
cada variante (reproduzido rodando `win_daily_continuidade_refino_
diagnostico.py`).

Reusa (IMPORTA, nunca copia/cola) `carregar_is_bars` de
`continuidade_stats.py` e `_metade`, `_series_bruto_custo`,
`nulo_sign_flip`, `_config`, `CAPITAL_NOCIONAL`, `DIRECTION_BY_SYMBOL` de
`continuidade_daily_rule.py` -- NAO edita nenhum dos dois.

Para CADA variante (baseline incluso, como referencia) roda o MESMO trio
exigido pela disciplina desta investigacao:
  (a) regra completa no IS inteiro, tabela padrao;
  (b) teste de METADE cronologica (MESMA divisao que a regra original);
  (c) nulo por sign-flip (formula correta, `bruto_d`/`custo_d` separados,
      5 sementes x 2.000 tiragens).

So' WIN@ -- e' o unico simbolo com liquido positivo no IS inteiro entre os
dois candidatos da rodada anterior (WDO@ reversal fecha negativo, fora do
escopo "forte candidato" desta rodada de refino)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from continuidade_daily_rule import (  # noqa: E402
    CAPITAL_NOCIONAL,
    _config,
    _metade,
    nulo_sign_flip,
)
from continuidade_stats import carregar_is_bars  # noqa: E402
from strategy.daytrade.lab.continuidade_daily import ContinuidadeDiaria  # noqa: E402
from strategy.daytrade.lab.win_daily_continuidade_refino import (  # noqa: E402
    ContinuidadeDiariaDirecaoRolante,
    ContinuidadeDiariaMagnitudeCap,
    ContinuidadeDiariaVolCap,
)

SYMBOL = "WIN@"
DIRECTION = "reversal"


def _rodar(strat, bars: pd.DataFrame):
    cfg = _config(SYMBOL)
    return run_intraday_backtest(bars, strat, cfg)


def _linha(rotulo: str, result):
    return linha_de_resultado(rotulo, result, CAPITAL_NOCIONAL, capital_nocional=True)


def testar_variante(rotulo: str, strat_factory, bars_full: pd.DataFrame,
                     bars_h1: pd.DataFrame, bars_h2: pd.DataFrame) -> dict:
    """Roda o trio completo para UMA variante (`strat_factory()` -> nova
    instancia da estrategia, chamada 3x -- uma por subconjunto, cada
    backtest precisa de estado zerado). Devolve um dict com os numeros
    centrais, para o resumo final honesto no fim do script."""
    print(f"\n{'='*100}\n{rotulo}\n{'='*100}")

    print("\n--- (a) regra completa (IS inteiro) ---")
    resultado_full = _rodar(strat_factory(), bars_full)
    linha_full = _linha(rotulo, resultado_full)
    print(tabela([linha_full]))

    print("\n--- (b) teste de metade ---")
    res_h1 = _rodar(strat_factory(), bars_h1)
    res_h2 = _rodar(strat_factory(), bars_h2)
    linha_h1 = _linha("metade 1", res_h1)
    linha_h2 = _linha("metade 2", res_h2)
    print(tabela([linha_h1, linha_h2]))

    print("\n--- (c) nulo sign-flip (regra completa, IS inteiro) ---")
    liquido_real, percentis = nulo_sign_flip(resultado_full)
    n_trades = len(resultado_full.trades)
    if percentis:
        media_pct = float(np.mean(percentis))
        print(f"liquido real: R$ {num_br(liquido_real)} ({n_trades} trades)")
        print(f"  percentis: " + ", ".join(f"{num_br(p,2)}%" for p in percentis)
              + f"   media={num_br(media_pct,2)}%")
    else:
        media_pct = float("nan")
        print("  sem trades -- nulo nao se aplica")

    return {
        "rotulo": rotulo,
        "full_liquido": linha_full.liquido_brl,
        "full_lucro_dd": linha_full.lucro_por_dd,
        "full_trades": linha_full.trades,
        "full_win_pct": linha_full.win_rate_pct,
        "h1_liquido": linha_h1.liquido_brl,
        "h1_lucro_dd": linha_h1.lucro_por_dd,
        "h1_trades": linha_h1.trades,
        "h2_liquido": linha_h2.liquido_brl,
        "h2_lucro_dd": linha_h2.lucro_por_dd,
        "h2_trades": linha_h2.trades,
        "nulo_percentil_medio": media_pct,
        "sobrevive_h1_e_h2_positivas": bool(linha_h1.liquido_brl > 0 and linha_h2.liquido_brl > 0),
    }


def main() -> None:
    bars = carregar_is_bars(SYMBOL)
    bars_h1, bars_h2 = _metade(bars, 1), _metade(bars, 2)
    print(f"[win_daily_continuidade_refino_variantes] {SYMBOL} -- {len(set(bars.index.date))} pregoes "
          f"({bars.index.min()} -> {bars.index.max()})")
    print(f"metade1: {len(set(bars_h1.index.date))} pregoes   metade2: {len(set(bars_h2.index.date))} pregoes")

    resumos: list[dict] = []

    resumos.append(testar_variante(
        "0) BASELINE continuidade_diaria_reversal",
        lambda: ContinuidadeDiaria(symbol=SYMBOL, direction=DIRECTION),
        bars, bars_h1, bars_h2,
    ))

    resumos.append(testar_variante(
        "1) MAGNITUDE CAP (exclui tercio 'forte' de |ret D-1|, corte da metade1)",
        lambda: ContinuidadeDiariaMagnitudeCap(symbol=SYMBOL, direction=DIRECTION),
        bars, bars_h1, bars_h2,
    ))

    resumos.append(testar_variante(
        "2) VOL CAP (exclui regime de vol trailing 'alta', corte da metade1)",
        lambda: ContinuidadeDiariaVolCap(symbol=SYMBOL, direction=DIRECTION),
        bars, bars_h1, bars_h2,
    ))

    resumos.append(testar_variante(
        "3) DIRECAO ROLANTE (corr lag-1 rolante, janela=20 pregoes concluidos)",
        lambda: ContinuidadeDiariaDirecaoRolante(symbol=SYMBOL, janela_dias=20),
        bars, bars_h1, bars_h2,
    ))

    print(f"\n{'='*100}")
    print("RESUMO HONESTO -- TODAS as variantes tentadas nesta rodada (nenhuma omitida)")
    print(f"{'='*100}")
    print(f"{'variante':<55} {'full R$':>12} {'full l/DD':>10} {'h1 R$':>11} {'h1 l/DD':>9} "
          f"{'h2 R$':>11} {'h2 l/DD':>9} {'h1&h2>0?':>9} {'nulo pct':>9} {'trades':>7}")
    for r in resumos:
        print(f"{r['rotulo']:<55} {num_br(r['full_liquido']):>12} "
              f"{num_br(r['full_lucro_dd']) if r['full_lucro_dd'] is not None else '—':>10} "
              f"{num_br(r['h1_liquido']):>11} "
              f"{num_br(r['h1_lucro_dd']) if r['h1_lucro_dd'] is not None else '—':>9} "
              f"{num_br(r['h2_liquido']):>11} "
              f"{num_br(r['h2_lucro_dd']) if r['h2_lucro_dd'] is not None else '—':>9} "
              f"{'SIM' if r['sobrevive_h1_e_h2_positivas'] else 'nao':>9} "
              f"{num_br(r['nulo_percentil_medio'],1)}%{'':>3} "
              f"{r['full_trades']:>7}")

    print(f"\n{len(resumos)-1} variantes de refino testadas (+ 1 baseline de referencia) -- "
          f"nenhuma omitida deste resumo, inclusive as que nao ajudarem/piorarem.")


if __name__ == "__main__":
    main()
