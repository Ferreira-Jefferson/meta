"""Reteste OOS do filtro `volume_toque` -- WdoGridReloadMaker F1 (WDO@),
2026-08-27. Confirmacao de amostra UNICA hold-out (SEM gate split-half --
o split-half so' faz sentido calibrando dentro do IS; aqui o OOS inteiro
JA E' o "segundo pedaco" que confirma ou refuta o achado do IS).

## O que foi validado hoje no IS (memoria `capital_ladder_qualidade_sinal_
## reversao_2026_08_27`, reproduzido em `signal_quality_wdof1_resumo_
## 2026_08_27.csv`)

`volume_toque` (volume do tick/negocio que causou o fill) tem correlacao de
Pearson NEGATIVA com `pnl_brl` no IS: corr=-0,1459, p bicaudal (permutacao,
n_perm=5000) = 0,0008, reproduzivel split-half (mesmo sinal E p<0,05 pool E
p<0,10 cada metade) -- "mais volume no tick que toca o nivel = pior
resultado" (fluxo agressivo atropelando a ordem maker).

## Pergunta desta rodada

O MESMO sinal (mesma direcao, negativa) aparece nos trades do OOS (holdout
nunca antes olhado para esta estrategia)? Reporta so' correlacao + p-valor
no OOS puro -- SEM split-half aqui (n muito menor que o IS, dividir ao meio
so' perderia poder; a funcao de split-half inteira e' um instrumento de
CALIBRACAO, o OOS inteiro ja e' a confirmacao).

## Fonte dos dados -- reuso, nenhum rerun do motor

Le' o trade log N=1 OOS-only ja' salvo por `capital_ladder_wdof1_oos_
2026_08_27.py` (`capital_ladder_wdof1_n1_trades_oos_2026_08_27.csv`, 51
pregoes, tick+fallback M1) via `carregar_trade_log` REIMPORTADO de
`signal_quality_wdof1_2026_08_27.py` (mesma funcao, mesmo parser). As
features vem de `computa_features` (TAMBEM reimportado de la', generico em
`(trades, tick_bars)`).

## Por que so' o subconjunto TICK do OOS (49/51 pregoes) entra na feature

`volume_toque` so' faz sentido comparavel em resolucao TICK (volume do
NEGOCIO individual que tocou o nivel). Os 2 pregoes de fallback M1
(2026-08-03, 2026-08-04, ver `wdo_grid_reload_f1_tick_lab_oos_2026_08_27.py`)
nao tem tick cru pra procurar -- passando so' `tick_only_bars` (49 dias)
para `computa_features`, os trades desses 2 dias simplesmente NAO encontram
tick correspondente (`touch_idx is None`) e caem em `sem_match`, excluidos
automaticamente da correlacao (comportamento built-in da funcao, nenhum
filtro extra necessario aqui) -- ver a nota equivalente na docstring de
`wdo_grid_reload_f1_tick_lab_oos_2026_08_27.py`.

Uso: `python -u scripts/daytrade/signal_quality_wdof1_oos_2026_08_27.py`
(depende de `capital_ladder_wdof1_oos_2026_08_27.py` ja ter rodado e salvo
o trade log N=1 OOS-only).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br  # noqa: E402

from copa_rejection_lab import imprime_correlacao, testa_proxy  # noqa: E402
from signal_quality_wdof1_2026_08_27 import (  # noqa: E402
    carregar_trade_log,
    computa_features,
)
from wdo_grid_reload_f1_tick_lab_oos_2026_08_27 import carregar_oos_bars  # noqa: E402

OUT_DIR = ROOT / "scripts" / "daytrade"
TRADE_LOG_N1_OOS_CSV = OUT_DIR / "capital_ladder_wdof1_n1_trades_oos_2026_08_27.csv"
IS_RESUMO_CSV = OUT_DIR / "signal_quality_wdof1_resumo_2026_08_27.csv"
FEATURES_OOS_CSV = OUT_DIR / "signal_quality_wdof1_oos_features_2026_08_27.csv"

FEATURE = "volume_toque"


def _corr_is() -> tuple[float, float]:
    """Le' o achado IS ja' salvo (nenhum recalculo) -- corr + p bicaudal do
    pool, para a comparacao de direcao de sinal."""
    df = pd.read_csv(IS_RESUMO_CSV)
    row = df[df["feature"] == FEATURE].iloc[0]
    return float(row["corr_pearson"]), float(row["p_bicaudal_pool"])


def main() -> None:
    trades = carregar_trade_log(TRADE_LOG_N1_OOS_CSV)
    print(f"[signal_quality_oos] {len(trades)} trades N=1 OOS-only carregados de {TRADE_LOG_N1_OOS_CSV}")
    perdedores = [t for t in trades if t.pnl_brl <= 0]
    print(f"[signal_quality_oos] {len(trades) - len(perdedores)} vencedores / {len(perdedores)} perdedores "
          f"({num_br(100.0 * len(perdedores) / len(trades), 2)}% de perdas)")

    oos = carregar_oos_bars()
    tick_only_bars = oos["tick_only_bars"]
    print(f"[signal_quality_oos] tick_only_bars (OOS): {len(tick_only_bars)} ticks, "
          f"{len(oos['dias_tick'])} pregoes ({oos['dias_tick'][0]} -> {oos['dias_tick'][-1]}) -- "
          f"fallback M1 ({oos['dias_m1_fallback']}) NAO entra aqui (resolucao incompativel p/ volume_toque)")

    feats, sem_match = computa_features(trades, tick_only_bars)
    print(f"[signal_quality_oos] features computadas para {len(feats)}/{len(trades)} trades "
          f"({sem_match} sem tick correspondente -- esperado ~= trades nos {len(oos['dias_m1_fallback'])} "
          f"pregoes de fallback M1, ver docstring do modulo)")
    if not feats:
        raise SystemExit(
            "[signal_quality_oos] 0 trades com feature computavel -- isto e' o MESMO sintoma do bug de "
            "volume NaN achado em wdo_grid_reload_f1_tick_lab_oos_2026_08_27.py (concat naive tick+M1). "
            "Confira se capital_ladder_wdof1_oos_2026_08_27.py foi rodado APOS a correcao antes de "
            "reexecutar este script (o trade log N=1 OOS usado aqui precisa vir da versao corrigida)."
        )

    df_feats = pd.DataFrame([dict(pnl_brl=f.pnl_brl, volume_toque=f.volume_toque) for f in feats])
    df_feats.to_csv(FEATURES_OOS_CSV, index=False)
    print(f"[signal_quality_oos] tabela por-trade (OOS) salva em {FEATURES_OOS_CSV}")

    x = df_feats["volume_toque"].to_numpy(dtype=float)
    y = df_feats["pnl_brl"].to_numpy(dtype=float)

    print(f"\n=== reteste OOS puro -- feature '{FEATURE}' (correlacao + permutacao, n_perm=5000) ===")
    r = testa_proxy(FEATURE, x, y, seed=1)
    imprime_correlacao(r)

    corr_is, p_is = _corr_is()
    mesmo_sinal = (r.corr_real > 0) == (corr_is > 0)
    significativo_oos = r.p_two_sided < 0.05

    print("\n=== VEREDITO ===")
    print(f"IS   (2.773 trades): corr={num_br(corr_is, 4)}, p bicaudal={num_br(p_is, 4)} "
          f"(reproduzivel split-half no IS: True, ja' confirmado hoje)")
    print(f"OOS  ({r.n} trades): corr={num_br(r.corr_real, 4)}, p bicaudal={num_br(r.p_two_sided, 4)}")
    print(f"mesma direcao de sinal (IS negativo, mais volume no toque = pior) confirmada no OOS puro? "
          f"{mesmo_sinal} | significativo no OOS isoladamente (p<0,05)? {significativo_oos}")


if __name__ == "__main__":
    main()
