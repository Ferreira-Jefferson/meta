"""ESTAGIO B da sub-hipotese 2 (CONTINUIDADE INTRADIARIA): converte a UNICA
dependencia bruta que sobreviveu a promocao em `continuidade_stats.py`
(WDO@, barras de 5 minutos, lag-1, p2s=0,0013 < 0,0167 bonferroni/3,
direcao REVERSAO) numa regra de trade real
(`strategy.daytrade.lab.continuidade_intraday.ContinuidadeIntraday`), com
CUSTO de verdade (`backtest.intraday.profiles.FUTURES_PROFILES`), IN-SAMPLE.

So' roda a celula PROMOVIDA -- WIN@/5min chegou perto (p2s=0,0387) mas NAO
bateu o corte de bonferroni/3 (0,0167) e por isso NAO e' promovido nem
testado aqui; incluir "quase-significativo" no estagio B seria o mesmo
vies de "escolher o melhor depois de olhar" que a rodada evita em todo
lugar (briefing: "TODOS os horizontes/lags testados sao reportados... a
promocao e' decidida ANTES de olhar o resultado").

Diferente do estagio B diario (`continuidade_daily_rule.py`, uma decisao
por pregao, sem timing nenhum), esta regra decide A CADA fronteira de 5
minutos -- e' precisamente a situacao que o achado de cautela da linha
Copa avisa (ML por barra acerta o lado mas o timing de entrada/saida
destroi o lucro). Rodar este estagio B com o MESMO rigor (custo real,
metade, nulo sign-flip) e' o jeito de descobrir se o mesmo problema
acontece aqui, em vez de assumir.

## O que este script roda

1. Regra completa no IS inteiro, tabela padrao (`backtest.intraday.report`).
2. Teste de METADE: a MESMA regra na metade 1 e na metade 2 cronologicas.
3. Nulo por SIGN-FLIP (regra 5 do briefing): separa bruto_d/custo_d por
   pregao, sorteia sinal em {-1,+1} por pregao, 5 sementes x 2.000
   tiragens, percentil do real na distribuicao.

Capital NOCIONAL + 1 contrato (`max_open_contracts=1`,
`default_quantity=1`) -- mesmo espirito de `continuidade_daily_rule.py`:
escalonamento por capital e' outra frente de pesquisa."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # continuidade_stats.py mora ao lado deste script

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from continuidade_stats import carregar_is_bars  # noqa: E402
from strategy.daytrade.lab.continuidade_intraday import ContinuidadeIntraday  # noqa: E402

CAPITAL_NOCIONAL = 1_000_000.0

#: Unica celula promovida em `continuidade_stats.py` (rodada de 2026-08-26,
#: seed=20260826, n_perm=3000): WDO@ 5min lag1 corr real=-0,0345
#: (p2s=0,0013 < 0,05/3 bonferroni). Direcao SEMPRE a medida (negativa ->
#: "reversal") -- nunca escolhida tentando os dois lados aqui.
PROMOVIDOS = [
    {"symbol": "WDO@", "bar_minutes": 5, "direction": "reversal",
     "nota": "corr lag-1 real=-0,0345, p2s=0,0013 (bonferroni/3=0,0167)"},
]

N_SEEDS_NULO_SIGNFLIP = 5
DRAWS_POR_SEMENTE = 2000


def _config(symbol: str):
    profile = profile_for(symbol)
    from copa_lab import _economia  # reaproveita fallback conhecido
    tick_value, tick_size = _economia(symbol)
    return config_for(
        profile, trade_tick_value=tick_value, trade_tick_size=tick_size,
        initial_capital=CAPITAL_NOCIONAL, default_quantity=1, max_open_contracts=1,
    )


def rodar(symbol: str, bars: pd.DataFrame, bar_minutes: int, direction: str):
    strat = ContinuidadeIntraday(symbol=symbol, bar_minutes=bar_minutes, direction=direction)
    cfg = _config(symbol)
    return run_intraday_backtest(bars, strat, cfg)


def _metade(bars: pd.DataFrame, metade: int) -> pd.DataFrame:
    datas = sorted(set(bars.index.date))
    meio = len(datas) // 2
    escolhidas = set(datas[:meio]) if metade == 1 else set(datas[meio:])
    return bars[[d in escolhidas for d in bars.index.date]]


def _series_bruto_custo(result) -> tuple[pd.Series, pd.Series]:
    """Mesma formula de `continuidade_daily_rule.py`/`win_orb_lab.py`
    (regra 5 do briefing): `bruto_d` (P&L bruto por pregao de SAIDA) e
    `custo_d` (>=0) tal que `liquido_d = bruto_d - custo_d` sempre."""
    trades = result.trades
    if not trades:
        vazio = pd.Series(dtype="float64")
        return vazio, vazio
    df = pd.DataFrame({
        "data": [pd.Timestamp(t.exit_ts).normalize() for t in trades],
        "bruto": [t.pnl_brl + t.fees_total for t in trades],
        "custo": [t.fees_total for t in trades],
    })
    g = df.groupby("data").sum(numeric_only=True).sort_index()
    return g["bruto"], g["custo"]


def nulo_sign_flip(result, seeds=range(1, N_SEEDS_NULO_SIGNFLIP + 1), draws: int = DRAWS_POR_SEMENTE):
    bruto_d, custo_d = _series_bruto_custo(result)
    liquido_real = sum(t.pnl_brl for t in result.trades)
    liquido_d = bruto_d - custo_d
    if len(liquido_d):
        assert abs(float(liquido_d.sum()) - liquido_real) < 1e-6, (
            "bruto_d - custo_d diverge do liquido real -- bug na separacao"
        )
    bruto = bruto_d.to_numpy()
    custo_total = float(custo_d.to_numpy().sum())
    n = len(bruto)
    percentis: list[float] = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        if n == 0:
            percentis.append(50.0)
            continue
        s = rng.choice(np.array([-1.0, 1.0]), size=(draws, n))
        sinteticos = s @ bruto - custo_total
        percentis.append(float((sinteticos < liquido_real).mean() * 100.0))
    return liquido_real, percentis


def main() -> None:
    for cfg in PROMOVIDOS:
        symbol, bar_minutes, direction = cfg["symbol"], cfg["bar_minutes"], cfg["direction"]
        print(f"\n{'='*100}\n{symbol}  bar_minutes={bar_minutes}  direction={direction}\n"
              f"achado bruto: {cfg['nota']}\n{'='*100}")
        bars = carregar_is_bars(symbol)

        print("\n=== 1) REGRA COMPLETA (IN-SAMPLE) ===")
        resultado_full = rodar(symbol, bars, bar_minutes, direction)
        linha_full = linha_de_resultado(f"continuidade_intraday_{bar_minutes}min_{direction}",
                                         resultado_full, CAPITAL_NOCIONAL, capital_nocional=True)
        print(tabela([linha_full]))

        print("\n=== 2) TESTE DE METADE ===")
        bars_h1, bars_h2 = _metade(bars, 1), _metade(bars, 2)
        res_h1 = rodar(symbol, bars_h1, bar_minutes, direction)
        res_h2 = rodar(symbol, bars_h2, bar_minutes, direction)
        linha_h1 = linha_de_resultado("metade 1", res_h1, CAPITAL_NOCIONAL, capital_nocional=True)
        linha_h2 = linha_de_resultado("metade 2", res_h2, CAPITAL_NOCIONAL, capital_nocional=True)
        print(tabela([linha_h1, linha_h2]))

        print("\n=== 3) NULO SIGN-FLIP (formula correta, regra 5) ===")
        liquido_real, percentis = nulo_sign_flip(resultado_full)
        media_pct = float(np.mean(percentis)) if percentis else float("nan")
        n_trades = len(resultado_full.trades)
        n_pregoes_trade = len(set(pd.Timestamp(t.exit_ts).normalize() for t in resultado_full.trades))
        print(f"liquido real: R$ {num_br(liquido_real)} ({n_trades} trades, {n_pregoes_trade} pregoes com trade)")
        if percentis:
            for seed, pct in zip(range(1, N_SEEDS_NULO_SIGNFLIP + 1), percentis):
                print(f"  semente {seed}: percentil {num_br(pct, 2)}%")
            print(f"  media={num_br(media_pct, 2)}%  min={num_br(min(percentis), 2)}%  "
                  f"max={num_br(max(percentis), 2)}%  desvio={num_br(float(np.std(percentis)), 2)}%  "
                  f"n={N_SEEDS_NULO_SIGNFLIP} sementes x {DRAWS_POR_SEMENTE} tiragens")
        else:
            print("  (sem trades -- nulo nao se aplica)")


if __name__ == "__main__":
    main()
