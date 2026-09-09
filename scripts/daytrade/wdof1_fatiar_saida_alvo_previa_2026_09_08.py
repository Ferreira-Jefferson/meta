"""PREVIA: saida por alvo FATIADA (`EnterLimit.exit_split_unit`) em vez do
TP nativo (WDO F1, T2 e T3, 10 primeiros pregoes do IS, capital R$375).

## A ideia (proposta minha, aprovada pelo dono 2026-09-08)

O deslize de TP nativo (item 4.8/6.18 de LICOES_DE_PRODUCAO.md, secao do
CLAUDE.md "O motor COBRA o deslize do TP") existe porque o `tp` que viaja
amarrado no request da entrada e' executado pela corretora como GATILHO
varrido a mercado, nunca como ordem-limite na fila -- por isso desliza
SEMPRE contra (10 de 11 medidos, 0 a favor).

O motor ja' tem outro caminho de saida por alvo, usado hoje por
`gremah`/`gremah_tick` (`dividir_entrada=True`): a saida FATIADA
(`EnterLimit.exit_split_unit`), que posiciona ordem-limite REAL no livro por
fatia. `machine._close_position` ja' documenta que esse caminho "nao e' de
graca, mas nao cobra o deslize do TP nativo" -- ver o bloco `is_maker_target`.
Testado aqui pela primeira vez no WDO F1: `WdoGridReloadMaker` ganhou o
parametro `fatiar_saida_alvo` (default `False`, comportamento IDENTICO a
antes) que declara `exit_split_unit=quantity` no `EnterLimit` do alvo.

## O preco desta troca

Nao e' de graca: o alvo fatiado so' "toca" de verdade se o volume da barra
cobrir a fatia inteira (`limit_fill_capped_by_volume`, ja' ligado por
default nos testes) -- o mesmo risco de fila que a ENTRADA ja' tem hoje,
agora do lado da SAIDA. Com 1 contrato (capital minimo) a fatia e' pequena
(a propria posicao inteira), entao a barreira de volume deve quase sempre
passar num instrumento liquido como o WDO@ -- mas isso e' medido aqui, nao
suposto.

## As celulas

  1. `T2 nivel (motor de hoje)`   -- TP nativo, paga deslize (baseline).
  2. `T2 fatiado (hipotese)`      -- `exit_split_unit` ligado, sem deslize.
  3. `T3 nivel (motor de hoje)`   -- idem, T3 (compensacao do dono).
  4. `T3 fatiado (hipotese)`      -- idem, T3 fatiado.

`profit_ticks=1` (T1) nao entra -- ordem do dono, ver CLAUDE.md.

## Como LER

10 pregoes com capital R$375 (piso EXATO de 1 contrato) e' o regime
CENSURADO de sempre -- olhe `trades`/`pregoes_sem_trade` ANTES do liquido
(item 6.15 de LICOES_DE_PRODUCAO.md). PREVIA/smoke test, nao veredito: o
que decide se vale medir janela cheia e' o CONTRASTE nivel-vs-fatiado
dentro do mesmo profit_ticks, e a taxa de fill do alvo fatiado (se a
barreira de volume recusar demais, a ideia morre aqui).

Uso: `python -u scripts/daytrade/wdof1_fatiar_saida_alvo_previa_2026_09_08.py`
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"

#: Capital REAL do slot ao vivo (WDO@) -- margem R$150 x buffer 2,0 x reserva
#: 1,25. Ordem expressa do dono (2026-09-08): nada de bateria com capital de
#: folga, ele nao tem esse capital.
CAPITAL_REAL_BRL = 375.0

#: Ultimo pregao da PREVIA -- o 10o do IS (a janela IS comeca em 2026-02-27).
ATE_DIA = date(2026, 3, 12)

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
)

EXTRAS = ("trades", "saida_alvo", "saida_stop", "alvo_fatias_recusadas",
          "pregoes_sem_trade", "caixa_min")

#: `(rotulo, profit_ticks, fatiar_saida_alvo)`. `profit_ticks=None` = default
#: de producao (2).
VARIANTES = (
    ("T2 nivel (motor de hoje)", None, False),
    ("T2 fatiado (hipotese)",    None, True),
    ("T3 nivel (motor de hoje)", 3,    False),
    ("T3 fatiado (hipotese)",    3,    True),
)

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars() -> pd.DataFrame:
    """Fatia OHLCV dos 10 primeiros pregoes do IS, cacheada por PROCESSO."""
    if "bars" not in _DF_CACHE:
        df = pd.read_parquet(
            CACHE,
            columns=["open", "high", "low", "close", "volume"],
            filters=[("janela", "==", "IS"), ("dia", "<=", ATE_DIA)],
        )
        _DF_CACHE["bars"] = df.sort_index()
        del df
    return _DF_CACHE["bars"]


def _roda_uma(spec: dict):
    """Executado no processo FILHO. Devolve `(rotulo, LinhaResultado,
    texto_pronto, dt_segundos)`."""
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars()

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
        # so' e' cobrado na celula NAO fatiada (ver `is_maker_target` em
        # `machine._close_position`); a celula fatiada nao paga isto por
        # construcao, e' o proprio ponto do teste.
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    dias_janela = set(bars.index.date)
    dias_com_trade = {t.entry_ts.date() for t in trades}
    caixa_min = min((float(c) for c in resultado.equity_curve), default=capital)

    extras = {
        "trades": str(len(trades)),
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        # placeholder -- o motor nao expoe recusa de fatia por volume como
        # contador direto; fica registrado no README do resultado, nao aqui.
        "alvo_fatias_recusadas": "-",
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "caixa_min": num_br(caixa_min, 2),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, capital,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{dt:6.1f}s] {linha(item, EXTRAS)}", flush=True)
    return spec["rotulo"], item, buf.getvalue(), dt


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_fatiar_saida] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt

    print(f"[wdof1_fatiar_saida] PREVIA -- IS ate' {ATE_DIA} (10 pregoes), "
          f"capital R${CAPITAL_REAL_BRL:.2f}, {len(VARIANTES)} celulas em "
          f"{MAX_WORKERS} processos\n", flush=True)

    specs = [dict(capital=CAPITAL_REAL_BRL, rotulo=rotulo, profit_ticks=pt,
                  fatiar=fatiar)
             for rotulo, pt, fatiar in VARIANTES]

    resultados: dict = {}
    t0 = time.perf_counter()
    concluidos = 0
    n_workers = max(1, min(len(specs), MAX_WORKERS))
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            rotulo, item, texto, _dt = future.result()
            resultados[rotulo] = item
            concluidos += 1
            print(f"[{concluidos}/{len(specs)}] {texto}", end="", flush=True)

    print(f"\n[wdof1_fatiar_saida] motor: {time.perf_counter() - t0:.1f}s\n")

    print("=== PREVIA -- 10 primeiros pregoes do IS, capital R$375 ===")
    print(cabecalho(EXTRAS))
    for rotulo, _pt, _fatiar in VARIANTES:
        item = resultados.get(rotulo)
        if item is not None:
            print(linha_fmt(item, EXTRAS))


if __name__ == "__main__":
    main()
