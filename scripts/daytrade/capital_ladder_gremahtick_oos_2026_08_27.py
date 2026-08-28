"""CONFIRMACAO OOS -- escada de capital da `GremahTick` (PMAM3, motor tick),
2026-08-27. Continuacao de `capital_ladder_gremahtick_2026_08_27.py` (que
mediu SO' o IN-SAMPLE, `LockedBars.unlock()` nunca chamado la').

## O que ja' foi olhado antes (NAO e' novidade, contexto so')

O OOS da GEOMETRIA DEFAULT da `GremahTick` (T1 E1 S4) ja foi confirmado em
`confirm_oos_ticks.py` 2026-08-26 (PMAM3/tick: IS +11,5%, OOS +26,9%,
APROVADO -- adotada em producao). Este script NAO repete aquilo. O que e'
NOVO aqui, e' o que a missao pede: (1) a ESCADA DE CAPITAL por N=1..10 lotes
fixos (capital_ladder_gremahtick_2026_08_27.py so' mediu o IS) e (2) os DOIS
filtros de qualidade de sinal validados HOJE so' no IS
(signal_quality_gremahtick_2026_08_27.py: `volume_toque<=400` e
`distancia_sma20_ticks>=0,70`) -- nenhum dos dois tinha sido testado fora do
IS ate' agora.

## Autorizacao explicita do dono para destravar o OOS AGORA

O dono autorizou expressamente (2026-08-27) destravar `LockedBars` desta
janela para esta validacao final, antes de atualizar producao -- ver
`unlock()` abaixo, com o motivo gravado no proprio codigo (nao um parametro
de linha de comando digitado na hora, mesmo espirito de `confirm_oos_ticks.
py`: lista/motivo FIXOS no arquivo, nao "tentar mais um").

## Reuso -- NADA da logica de bissecção/rejeicao e' reescrita

Este script IMPORTA (nao reescreve) de `capital_ladder_gremahtick_2026_08_
27.py` (mesmo diretorio, ja' no `sys.path`):
  - `GremahTickLoteFixo` (subclasse de lote fixo -- unica forma de rodar N
    lotes constantes sem editar `gremah_tick.py`, ja' documentada la');
  - `roda_base` (generica em `run_bars` -- funciona identica para
    IS, OOS-only ou IS+OOS combinado, SEM nenhuma mudanca);
  - `rejeicao_stats` / `zerou_count` / `busca_capital_minimo_seguro`
    (rejeicao i.i.d. p=50%, 30 sementes, bisseccao -- MESMO metodo);
  - `capital_que_producao_libera` (achado operacional -- caixa em que a
    formula REAL de producao libera N lotes).
  - Constantes: `SYMBOL="PMAM3"`, `MOTOR="tick"`, `N_MIN=1`, `N_MAX=10`,
    `N_SEMENTES=30`, `P_ALVO=0.5`, `SEED_BASE=0`,
    `CAPITAL_NOMINAL_PROBE_BRL`, `MAX_OPEN_CONTRACTS_TESTE`.

So' o CARREGAMENTO de barras e' novo aqui (precisa destravar o OOS, o que
`_geometria_comum.carregar_is` deliberadamente NUNCA faz) -- replica o MESMO
corte (`REGIME_START`, `profile.frozen_cutoff`, `declare_frozen_split`) que
`_geometria_comum.carregar_is` e `confirm_oos_ticks.py` ja usam, so' que
tambem le' `locked.out_of_sample()` apos `unlock()`.

## Dois casos, lado a lado (pedido explicito da missao)

  (a) OOS-ONLY: so' `locked.out_of_sample()` -- confirmacao ISOLADA, mesmo
      tamanho de amostra que o OOS permitir (~2,5 meses de tick, bem menor
      que o IS).
  (b) IS+OOS COMBINADO: `pd.concat([locked.in_sample(), locked.
      out_of_sample()])` -- exatamente as MESMAS barras que estariam em
      `bars_all` sem split nenhum (verificado abaixo por assert) -- numero
      FINAL consolidado, valido porque o dono ja' autorizou o destrave para
      esta medicao (nao e' mais "espiar", e' medicao final).

## Correcao de margem/notional (MESMA formula ja aplicada e documentada
hoje em `capital_ladder_qualidade_sinal_reversao_2026_08_27`, memoria do
dono): `capital_minimo_real(N) = capital_minimo_seguro_medido(N) +
pior_caso_exigencia_capital_brl(N)`. Valido porque a curva de equity e' um
deslocamento aditivo puro: exigir equity(t) >= M para todo t (M = maior
notional de entrada observado, o "piso de margem" de uma ACAO sem margem de
verdade) equivale a exigir equity(t)-M >= 0, ou seja capital_inicial >=
capital_minimo_seguro + M. `pior_caso_exigencia_capital_brl(N) = N x
LOTE_PADRAO_B3 x max(entry_price)` -- MESMA formula (e MESMO motivo,
`dividir_entrada=True` faz `quantity` do trade individual ficar sempre 100)
ja documentada em `capital_ladder_gremahtick_2026_08_27.py`.

## Regra do repo

So' arquivo NOVO (sufixo `_oos_2026_08_27`). Nenhum arquivo existente
editado -- nem `gremah_tick.py`, nem `_geometria_comum.py`, nem `capital_
ladder_gremahtick_2026_08_27.py` (so' importado). `git add/commit/push`
nunca chamado por este script.

Uso:
    python -u scripts/daytrade/capital_ladder_gremahtick_oos_2026_08_27.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES  # noqa: E402
from backtest.intraday.report import num_br  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402

from _geometria_comum import REGIME_START, carregar_economics  # noqa: E402

# reuso literal (import, nao reescrita) do script de HOJE que ja mediu o IS
import capital_ladder_gremahtick_2026_08_27 as CL27  # noqa: E402

# ---------------------------------------------------------------------------
# motivo do destrave -- explicito, gravado no codigo (nao um argv digitado
# na hora), autorizado pelo dono para esta validacao final (2026-08-27).
# ---------------------------------------------------------------------------
MOTIVO_UNLOCK = (
    "Validacao final autorizada pelo dono em 2026-08-27 para consolidar "
    "capital/sinal antes de atualizar producao (GremahTick, PMAM3, motor "
    "tick -- TOP-1 do podio, rodando ao vivo)."
)

SYMBOL = CL27.SYMBOL          # "PMAM3"
MOTOR = CL27.MOTOR            # "tick"
N_MIN, N_MAX = CL27.N_MIN, CL27.N_MAX

SCRATCH_DIR = ROOT / "scratch" / "scripts"
CSV_TRADE_LOG_OOS_N1 = SCRATCH_DIR / "capital_ladder_gremahtick_pmam3_oos_n1_trades_2026_08_27.csv"
JSON_RESULTADO = SCRATCH_DIR / "capital_ladder_gremahtick_pmam3_oos_2026_08_27.json"


# ---------------------------------------------------------------------------
# carregamento -- MESMO corte de `_geometria_comum.carregar_is`
# (REGIME_START + profile.frozen_cutoff + declare_frozen_split), so' que
# tambem le' `out_of_sample()` apos `unlock()` explicito.
# ---------------------------------------------------------------------------

def carregar_is_oos_combinado(symbol: str, motor: str, unlock_reason: str):
    profile = PROFILES[symbol]
    if motor == "m1":
        raise NotImplementedError("este script so' cobre o motor tick da GremahTick")
    ticks = load_ticks(symbol)
    bars_all = ticks_to_degenerate_bars(ticks) if not ticks.empty else pd.DataFrame()
    if bars_all.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), profile

    regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
    bars_all = bars_all.loc[bars_all.index >= regime_start]

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(bars_all, split)
    is_bars = locked.in_sample()
    locked.unlock(unlock_reason)
    oos_bars = locked.out_of_sample()

    combinado = pd.concat([is_bars, oos_bars])
    assert combinado.index.is_monotonic_increasing, (
        "IS+OOS combinado nao ficou em ordem cronologica -- corte quebrado"
    )
    assert len(combinado) == len(bars_all), (
        f"IS({len(is_bars)}) + OOS({len(oos_bars)}) = {len(combinado)} != "
        f"bars_all({len(bars_all)}) -- corte perdeu ou duplicou registros"
    )
    return is_bars, oos_bars, combinado, profile


# ---------------------------------------------------------------------------
# uma escada de capital completa (N=1..10) sobre UMA janela de barras --
# reusa `CL27.roda_base` / `CL27.busca_capital_minimo_seguro` /
# `CL27.rejeicao_stats` / `CL27.capital_que_producao_libera` (NENHUMA
# logica de bissecção/rejeicao reescrita); so' o loop por N e os guard
# clauses de sanidade (mesmos da rodada original) e a correcao de
# margem/notional sao novos aqui.
# ---------------------------------------------------------------------------

def escada_de_capital(rotulo: str, run_bars: pd.DataFrame, profile, economics) -> tuple[list[dict], list]:
    pregoes = len(set(run_bars.index.date))
    print(f"\n[capital_ladder_oos] janela={rotulo} -- {len(run_bars)} negocios, "
          f"{pregoes} pregoes, {run_bars.index.min()} -> {run_bars.index.max()}", flush=True)

    linhas: list[dict] = []
    trade_log_n1 = None

    for n in range(N_MIN, N_MAX + 1):
        strat, resultado = CL27.roda_base(n, run_bars, profile, economics)
        trades = list(resultado.trades)
        if getattr(resultado, "wiped_out_at", None) is not None:
            raise SystemExit(
                f"[capital_ladder_oos] janela={rotulo} N={n}: a rodada-base ZEROU em "
                f"{resultado.wiped_out_at} mesmo com capital nominal de "
                f"R${num_br(CL27.CAPITAL_NOMINAL_PROBE_BRL, 0)} -- capital de sondagem "
                "insuficiente para esta janela."
            )
        puladas = len(getattr(resultado, "sessoes_puladas_por_capital", []) or [])
        if puladas:
            raise SystemExit(
                f"[capital_ladder_oos] janela={rotulo} N={n}: {puladas} sessao(oes) pulada(s) "
                "por enforce_capital_minimo mesmo com capital nominal folgado."
            )
        if resultado.ordens_recusadas_por_teto:
            raise SystemExit(
                f"[capital_ladder_oos] janela={rotulo} N={n}: "
                f"{resultado.ordens_recusadas_por_teto} ordem(ns) recusada(s) pelo teto do motor."
            )
        if n == N_MIN:
            trade_log_n1 = trades

        pior_caso = (n * CL27.LOTE_PADRAO_B3 * max(t.entry_price for t in trades)) if trades else 0.0

        chute = max(pior_caso, 1.0)
        capital_seguro = CL27.busca_capital_minimo_seguro(trades, chute)
        stats_no_seguro = CL27.rejeicao_stats(trades, capital_seguro)
        assert int(stats_no_seguro["zerou"].sum()) == 0, (
            f"[capital_ladder_oos] janela={rotulo} N={n}: bisseccao nao bateu 0/30 na confirmacao."
        )

        # -- CORRECAO de margem/notional (mesma formula documentada hoje) --
        capital_minimo_real = capital_seguro + pior_caso

        libera_n = CL27.capital_que_producao_libera(strat.snapshots, n)
        if libera_n is None:
            libera_antes = "n/d (producao nunca alcanca N nesta janela)"
        else:
            libera_antes = "sim" if libera_n < capital_seguro else "nao"

        maxdd_medio = float(stats_no_seguro["maxdd"].mean())
        maxdd_desvio = float(stats_no_seguro["maxdd"].std(ddof=1)) if CL27.N_SEMENTES > 1 else 0.0

        linha = dict(
            n_lotes=n,
            trades=len(trades),
            pior_caso_exigencia_capital_brl=pior_caso,
            capital_minimo_seguro_brl=capital_seguro,
            capital_minimo_real_brl=capital_minimo_real,
            capital_que_producao_libera_n_brl=libera_n,
            producao_libera_antes_do_seguro=libera_antes,
            maxdd_medio_no_capital_seguro_brl=maxdd_medio,
            maxdd_desvio_no_capital_seguro_brl=maxdd_desvio,
        )
        linhas.append(linha)
        print(f"    [{rotulo}] N={n:>2} trades={len(trades):>5} | pior_caso=R${num_br(pior_caso)} | "
              f"cap_min_seguro=R${num_br(capital_seguro)} | "
              f"CAP_MINIMO_REAL=R${num_br(capital_minimo_real)} | "
              f"libera_antes_do_seguro={libera_antes}", flush=True)

    return linhas, (trade_log_n1 or [])


def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    is_bars, oos_bars, combinado_bars, profile = carregar_is_oos_combinado(SYMBOL, MOTOR, MOTIVO_UNLOCK)
    if oos_bars.empty:
        raise SystemExit(f"[capital_ladder_oos] sem dado OOS local para {SYMBOL!r} (motor={MOTOR!r})")

    print(f"[capital_ladder_oos] {SYMBOL} motor={MOTOR}")
    print(f"    IS       : {len(is_bars):>7} negocios, {is_bars.index.min()} -> {is_bars.index.max()}")
    print(f"    OOS      : {len(oos_bars):>7} negocios, {oos_bars.index.min()} -> {oos_bars.index.max()}")
    print(f"    IS+OOS   : {len(combinado_bars):>7} negocios, "
          f"{combinado_bars.index.min()} -> {combinado_bars.index.max()}")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    print(f"[capital_ladder_oos] economics (cache) {SYMBOL}: trade_tick_value="
          f"{economics.trade_tick_value} trade_tick_size={economics.trade_tick_size}")

    linhas_oos, trades_oos_n1 = escada_de_capital("OOS-only", oos_bars, profile, economics)
    linhas_combo, _trades_combo_n1 = escada_de_capital("IS+OOS combinado", combinado_bars, profile, economics)

    # -- trade log OOS-only N=1 -> CSV (reusado por signal_quality_gremahtick_oos_2026_08_27.py) --
    df_log = pd.DataFrame([dict(
        symbol=t.symbol, strategy_name=t.strategy_name, strategy_version=t.strategy_version,
        side=t.side, entry_ts=t.entry_ts, entry_price=t.entry_price,
        exit_ts=t.exit_ts, exit_price=t.exit_price, quantity=t.quantity,
        exit_reason=(t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)),
        point_value_brl=t.point_value_brl, capital_base=t.capital_base,
        fees_total=t.fees_total, slippage_total=t.slippage_total,
        pnl_brl=t.pnl_brl, pnl_pct=t.pnl_pct,
    ) for t in trades_oos_n1])
    df_log.to_csv(CSV_TRADE_LOG_OOS_N1, index=False)
    print(f"\n[capital_ladder_oos] trade log OOS-only N=1 ({len(df_log)} trades) salvo em {CSV_TRADE_LOG_OOS_N1}")

    with open(JSON_RESULTADO, "w", encoding="utf-8") as fh:
        json.dump(dict(
            symbol=SYMBOL, motor=MOTOR, motivo_unlock=MOTIVO_UNLOCK,
            is_inicio=str(is_bars.index.min()), is_fim=str(is_bars.index.max()), is_pregoes=len(set(is_bars.index.date)),
            oos_inicio=str(oos_bars.index.min()), oos_fim=str(oos_bars.index.max()), oos_pregoes=len(set(oos_bars.index.date)),
            combinado_inicio=str(combinado_bars.index.min()), combinado_fim=str(combinado_bars.index.max()),
            combinado_pregoes=len(set(combinado_bars.index.date)),
            capital_nominal_probe_brl=CL27.CAPITAL_NOMINAL_PROBE_BRL,
            n_sementes=CL27.N_SEMENTES, p_alvo=CL27.P_ALVO, seed_base=CL27.SEED_BASE,
            linhas_oos_only=linhas_oos,
            linhas_is_oos_combinado=linhas_combo,
        ), fh, indent=2, ensure_ascii=False, default=str)
    print(f"[capital_ladder_oos] resultado completo salvo em {JSON_RESULTADO}")

    # ---------------------------------------------------------------
    # tabela final -- CRUA, os dois casos lado a lado, capital MINIMO REAL
    # (ja com a correcao de margem/notional somada)
    # ---------------------------------------------------------------
    print(f"\n\n=== ESCADA DE CAPITAL (CAPITAL MINIMO REAL, corrigido) -- {SYMBOL} motor={MOTOR} ===")
    por_n_combo = {ln["n_lotes"]: ln for ln in linhas_combo}
    cab = f"{'N':>3}{'trades_OOS':>12}{'CAP_REAL_OOS_R$':>18}{'trades_IS+OOS':>15}{'CAP_REAL_IS+OOS_R$':>20}"
    print(cab)
    print("-" * len(cab))
    for ln in linhas_oos:
        n = ln["n_lotes"]
        combo = por_n_combo[n]
        print(f"{n:>3}{ln['trades']:>12}{num_br(ln['capital_minimo_real_brl']):>18}"
              f"{combo['trades']:>15}{num_br(combo['capital_minimo_real_brl']):>20}")


if __name__ == "__main__":
    main()
