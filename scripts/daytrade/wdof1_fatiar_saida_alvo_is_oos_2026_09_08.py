"""WDO F1 (T2/T3, S16) -- saida por alvo FATIADA (`fatiar_saida_alvo=True`,
ligada em producao 2026-09-08) contra o TP nativo (motor de antes), IS e OOS
completos, capital real R$375.

## Por que esta medicao existe

A previa de 10 pregoes do IS (`wdof1_fatiar_saida_alvo_previa_2026_09_08.py`)
reverteu o quadro do deslize de TP (item 4.8/6.18 de LICOES_DE_PRODUCAO.md):
T2 foi de -R$242,50 (TP nativo) para +R$21.033,50 (fatiado); T3 de -R$229,00
para +R$12.928,50 -- e as duas saíram de CENSURADAS (8-9 de 10 pregoes sem
trade) para 0 de 10. O dono mandou aplicar direto no robo de producao
(`strategy.daytrade.registry`, `fatiar_saida_alvo=True`) antes desta medicao
de janela cheia rodar -- este script e' a validacao que faltava, nao o que
decidiu a aplicacao.

## As celulas

  1. `T2 nivel (motor antigo)`  -- TP nativo, paga deslize (o que rodava ATE'
     2026-09-08).
  2. `T2 fatiado (producao)`    -- o que roda em producao AGORA.
  3. `T3 nivel (motor antigo)`  -- idem, T3 (compensacao do dono).
  4. `T3 fatiado`               -- T3 com a saida fatiada tambem.

`profit_ticks=1` (T1) nao entra -- ordem do dono, ver CLAUDE.md. So' capital
REAL (R$375) -- ordem do dono 2026-09-08, nada de bateria com folga.

## Como LER

Confira `pregoes_sem_trade`/`trades` ANTES do liquido (item 6.15 de
LICOES_DE_PRODUCAO.md): uma janela onde o robo parou de operar mede o portao
de capital, nao a estrategia. A previa nao mostrou censura nas celulas
fatiadas -- aqui e' onde isso se confirma (ou nao) na janela inteira.

Uso: `python -u scripts/daytrade/wdof1_fatiar_saida_alvo_is_oos_2026_09_08.py`
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"

#: Capital REAL do slot ao vivo (WDO@) -- margem R$150 x buffer 2,0 x reserva
#: 1,25. Ordem do dono 2026-09-08: nunca capital com folga.
CAPITAL_REAL_BRL = 375.0

#: BAIXO de proposito -- cada processo carrega a fatia da janela em memoria
#: (IS ~700 MB); o gargalo e' RAM, nao CPU (ver a nota analoga em
#: wdof1_deslize_alvo_is_oos_2026_09_08.py).
MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "4"))

CAMPOS_KWARGS = (
    "symbol", "tick_size", "level_spacing_ticks", "profit_ticks", "stop_ticks",
    "reanchor_mode", "reancora_min_segundos", "reancora_min_ticks",
    "max_trades_per_side", "session_stop_brl", "quantity",
    "margin_per_contract_brl", "margin_buffer", "hard_cap_contratos",
    "risco_pct_por_trade", "point_value_brl",
    "defesa_ativa", "defesa_gatilho_stop_pct", "defesa_alvo_proximidade_pct",
    "trailing_ativo", "trailing_recuo_ticks",
    "gate_atividade_ativo", "gate_volume_min", "gate_janela_segundos",
    "exit_ttl_bars",
)

EXTRAS = ("trades", "saida_alvo", "saida_stop", "saida_flatten",
          "pregoes_sem_trade", "zerou", "caixa_min")

#: `(rotulo, profit_ticks, fatiar_saida_alvo)`. `profit_ticks=None` = default
#: de producao (2).
VARIANTES = (
    ("T2 nivel (motor antigo)",     None, False),
    ("T2 fatiado (producao)",       None, True),
    ("T3 nivel (motor antigo)",     3,    False),
    ("T3 fatiado",                  3,    True),
)

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars_do_processo(janela: str) -> pd.DataFrame:
    """Fatia OHLCV da janela pedida, cacheada por PROCESSO -- filtro no
    LEITOR do parquet (ver a nota identica em
    wdof1_deslize_alvo_is_oos_2026_09_08.py)."""
    if janela not in _DF_CACHE:
        _DF_CACHE.clear()
        df = pd.read_parquet(
            CACHE,
            columns=["open", "high", "low", "close", "volume"],
            filters=[("janela", "==", janela)],
        )
        _DF_CACHE[janela] = df.sort_index()
        del df
    return _DF_CACHE[janela]


def _roda_uma(spec: dict):
    """Executado no processo FILHO. Devolve `(janela, rotulo, LinhaResultado,
    texto_pronto, dt_segundos)`."""
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars_do_processo(spec["janela"])

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    if spec["profit_ticks"] is not None:
        kwargs["profit_ticks"] = spec["profit_ticks"]
    kwargs["fatiar_saida_alvo"] = spec["fatiar"]
    strat = WdoGridReloadMaker(**kwargs)

    capital = float(spec["capital"])
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        # `target_slippage_ticks` no default de `config_for` (1,0 tick) --
        # so' cobrado na celula NAO fatiada; a fatiada nao paga por
        # construcao (`machine._close_position`, `is_maker_target` com
        # `exit_split_unit is not None`).
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "trades": str(len(trades)),
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        "saida_flatten": str(contagem.get("forced_flatten", 0)),
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "zerou": ("NAO" if resultado.wiped_out_at is None
                  else str(resultado.wiped_out_at)),
        "caixa_min": num_br(caixa_min, 2),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, capital,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{spec['janela']}, {dt:6.1f}s] {linha(item, EXTRAS)}", flush=True)
    return spec["janela"], spec["rotulo"], item, buf.getvalue(), dt


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_fatiar_saida_is_oos] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt

    print(f"[wdof1_fatiar_saida_is_oos] IS+OOS completos, capital real "
          f"R${CAPITAL_REAL_BRL:.2f}, {len(VARIANTES)} variantes x 2 janelas, "
          f"{MAX_WORKERS} processos por batelada\n", flush=True)

    resultados: dict = {}
    t0 = time.perf_counter()
    total = len(VARIANTES) * 2
    concluidos = 0

    for janela in ("IS", "OOS"):
        specs = [dict(capital=CAPITAL_REAL_BRL, janela=janela, rotulo=rotulo,
                      profit_ticks=pt, fatiar=fatiar)
                 for rotulo, pt, fatiar in VARIANTES]
        n_workers = max(1, min(len(specs), MAX_WORKERS))
        print(f"--- batelada {janela} ({len(specs)} tarefas, {n_workers} "
              f"processos) ---", flush=True)
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
            for future in as_completed(futures):
                jan, rotulo, item, texto, _dt = future.result()
                resultados[(jan, rotulo)] = item
                concluidos += 1
                print(f"[{concluidos}/{total}] {texto}", end="", flush=True)

    print(f"\n[wdof1_fatiar_saida_is_oos] motor: {time.perf_counter() - t0:.1f}s\n")

    for janela in ("IS", "OOS"):
        print(f"\n=== tabela {janela} -- capital real R$375 ===")
        print(cabecalho(EXTRAS))
        for rotulo, _pt, _fatiar in VARIANTES:
            item = resultados.get((janela, rotulo))
            if item is not None:
                print(linha_fmt(item, EXTRAS))


if __name__ == "__main__":
    main()
