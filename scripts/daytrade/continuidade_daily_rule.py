"""ESTAGIO B da sub-hipotese 1 (CONTINUIDADE DIARIA): converte a
dependencia BRUTA medida em `continuidade_stats.py` numa REGRA DE TRADE
real (`strategy.daytrade.lab.continuidade_daily.ContinuidadeDiaria`), com
CUSTO de verdade (`backtest.intraday.profiles.FUTURES_PROFILES`), IN-SAMPLE.

Roda para WIN@ e WDO@ mesmo quando o lag-1 diario NAO bateu o criterio de
promocao do estagio A (briefing: "isso e' um alerta, nao um veto... Mas
teste isso explicitamente -- nao assuma" sobre a hipotese de que decidir
UMA vez por pregao, sem timing intradiario, escapa do problema que matou o
sinal por BARRA da linha Copa) -- e' precisamente o tipo de situacao que o
nulo por sign-flip e o teste de metade servem para desmascarar: se a
direcao vier de RUIDO (nao promovida no estagio A), o P&L real vai cair
DENTRO da distribuicao do nulo, e a metade 2 nao vai confirmar a metade 1.

`direction`: SEMPRE o sinal medido da correlacao lag-1 REAL (`corr.real`)
do proprio simbolo no estagio A -- nunca escolhido tentando os dois lados e
ficando com o melhor (o vies que a rodada evita em todo lugar). Hardcoded
aqui, um por simbolo, com o numero medido escrito ao lado -- reproduzivel
rodando `continuidade_stats.py` de novo.

## O que este script roda (nesta ordem), por simbolo

1. Regra completa no IS inteiro, tabela padrao (`backtest.intraday.report`).
2. Teste de METADE: a MESMA regra (sem parametro nenhum pra re-escolher)
   rodada separadamente na metade 1 e na metade 2 cronologicas do IS.
3. Nulo por SIGN-FLIP (formula da regra 5 do briefing): separa bruto_d/
   custo_d por pregao, sorteia sinal em {-1,+1} por pregao, 5 sementes x
   2.000 tiragens, percentil do real na distribuicao.

Capital NOCIONAL + 1 contrato (`max_open_contracts=1`, `default_quantity=1`)
-- mesmo espirito de `scripts/daytrade/win_orb_lab.py`: a regra nunca abre
mais de 1 posicao por vez (1 entrada por sessao), entao testar com teto
maior so' escalaria o P&L por uma constante sem mudar se existe edge -- e
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
from strategy.daytrade.lab.continuidade_daily import ContinuidadeDiaria  # noqa: E402

CAPITAL_NOCIONAL = 1_000_000.0

#: Direcao de cada simbolo = sinal da correlacao lag-1 REAL medida em
#: `continuidade_stats.py` (rodada de 2026-08-26, seed=20260826,
#: n_perm=20000) -- NUNCA escolhida tentando os dois lados aqui. Corr
#: negativa -> "reversal" (aposta contra o sinal de ontem); positiva ->
#: "continuation". Nenhum dos dois bateu o criterio de promocao (p<0,05) --
#: rodando mesmo assim por pedido explicito do briefing de testar a
#: hipotese de escape do timing, nao assumir.
DIRECTION_BY_SYMBOL = {
    "WIN@": "reversal",      # corr lag-1 real = -0,1018 (p2s=0,29, NAO promovido)
    "WDO@": "reversal",      # corr lag-1 real = -0,0750 (NAO promovido -- mesmo sinal de WIN@)
}

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


def rodar(symbol: str, bars: pd.DataFrame, direction: str):
    strat = ContinuidadeDiaria(symbol=symbol, direction=direction)
    cfg = _config(symbol)
    return run_intraday_backtest(bars, strat, cfg)


def _metade(bars: pd.DataFrame, metade: int) -> pd.DataFrame:
    datas = sorted(set(bars.index.date))
    meio = len(datas) // 2
    escolhidas = set(datas[:meio]) if metade == 1 else set(datas[meio:])
    return bars[[d in escolhidas for d in bars.index.date]]


def _series_bruto_custo(result) -> tuple[pd.Series, pd.Series]:
    """Mesma formula de `scripts/daytrade/win_orb_lab.py::_series_bruto_custo`
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
    for symbol, direction in DIRECTION_BY_SYMBOL.items():
        print(f"\n{'='*100}\n{symbol}  (direction={direction})\n{'='*100}")
        bars = carregar_is_bars(symbol)

        print("\n=== 1) REGRA COMPLETA (IN-SAMPLE) ===")
        resultado_full = rodar(symbol, bars, direction)
        linha_full = linha_de_resultado(f"continuidade_diaria_{direction}", resultado_full,
                                         CAPITAL_NOCIONAL, capital_nocional=True)
        print(tabela([linha_full]))

        print("\n=== 2) TESTE DE METADE ===")
        bars_h1, bars_h2 = _metade(bars, 1), _metade(bars, 2)
        res_h1 = rodar(symbol, bars_h1, direction)
        res_h2 = rodar(symbol, bars_h2, direction)
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
