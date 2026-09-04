"""Mede os DOIS mecanismos de saida antecipada novos em `GremahTick`
(`strategy/daytrade/lab/gremah_tick.py`, motor TICK) -- `defesa_ativa`
(distancia de preco, portado de `WdoGridReloadMaker`) e `corte_persistencia_
ativo` (persistencia no tempo/negocios, portado de `CopaWin`) -- nos DOIS
simbolos pedidos para esta rodada: **PMAM3** e **KLBN3**.

## Diagnostico ANTES de rodar uma unica barra: a hipotese de degenerescencia
## ja se confirma so' olhando a geometria

`GremahTick._session_ticks(preco)` no preco de referencia do INICIO da janela
IS e' `(profit_ticks, spacing_ticks, stop_ticks)`:

  PMAM3 @ R$0,59 (inicio IS): (1, 1, 4)  -- preco varia 0,22..0,83 no IS
      inteiro; profit_ticks = 1 em TODA a faixa de preco vista.
  KLBN3 @ R$4,15 (inicio IS): (1, 1, 6)  -- preco varia 3,23..4,24 no IS
      inteiro; profit_ticks = 1 em TODA a faixa tambem.

Ou seja: para os DOIS simbolos, o alvo fica travado em 1 tick durante TODA a
janela medida -- exatamente a condicao que zerou os disparos de `defesa_
recuo` na `WdoGridReloadMaker` (sem estado intermediario entre "0% do alvo"
e "100% do alvo"). Isto e' fato geometrico, verificavel sem rodar o motor;
o script ainda assim RODA a grade completa (a hipotese pede confirmacao
empirica, nao so' aritmetica -- pode haver disparo residual em casos em que
o stop foi apertado por outro motivo, embora esta classe nao tenha trailing).

## Por que PMAM3/KLBN3 e nao os 9 -- e o que isto NAO decide

Pedido explicito desta rodada: medir os dois simbolos em producao real
(PMAM3 e KLBN3 sao os dois candidatos citados). Os outros 7 simbolos
confirmados tem a MESMA familia de geometria (`_CALIBRATION_BY_SYMBOL_TICK`,
percentual arredondado para ticks inteiros) e portanto a MESMA suspeita de
degenerescencia se o preco deles tambem satura em 1 tick -- nao verificado
aqui, fora do escopo desta rodada.

## Disciplina IS/OOS

Isto mexe em regra de SAIDA de uma estrategia em producao real (PMAM3/KLBN3
ao vivo, `GremahTick`) -- `backtest.intraday.frozen_split.LockedBars`, corte
declarado no PERFIL do simbolo (`profile_for(symbol).frozen_cutoff`,
`OOS_CUTOFF = "2026-06-13"`). IS e OOS SEMPRE reportados separados.

## Capital -- CLAUDE.md, "capital inicial nunca arbitrario"

`capital_minimo_brl(preco_de_referencia_do_INICIO_de_CADA_janela)` -- preco
de IS e de OOS sao DIFERENTES (o papel se move), entao os dois usam o PROPRIO
preco de referencia, nunca um numero fixo nem o preco da outra janela.

## Contagem de disparos -- por que nao usar `IntradayExitReason`

Todo `Exit(reason=...)` que a estrategia emite (`corte_persistencia`,
`defesa_recuo`, `filtro_volume_toque`, `stop_agregado_sessao`) vira o MESMO
`IntradayExitReason.SIGNAL` no trade fechado -- o motor nao preserva a string
do motivo (ver `backtest/intraday/machine.py::_close_position`). Contar
"quantos SIGNAL" misturaria os quatro mecanismos. Em vez disso, este script
substitui (monkeypatch, so' na instancia, dentro do processo filho)
`strat._corte_persistencia_deve_fechar`/`strat._defesa_deve_fechar` por um
wrapper que conta toda vez que o metodo devolve `True` -- a contagem sai
exata, sem depender do motor guardar o motivo.

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`),
`redirect_stdout` por tarefa, `flush=True`, streaming (cada tarefa imprime a
linha dela assim que termina) -- mesmo padrao de `copawin_corte_persistencia_
sweep_2026_09_03.py`/`sweep_gremah_tick.py`.

## Tabela BASELINE dos 9 simbolos confirmados (`--baseline`)

Modo separado: reproduz o numero ja' validado de `GremahTick(symbol=)` (SEM
os dois mecanismos novos, que sao opt-in/default desligado -- e' byte-a-byte
o comportamento de producao) nos 9 simbolos de `TICK_CONFIRMED_SYMBOLS`, com
o HISTORICO COMPLETO disponivel localmente (IS+OOS combinados -- nao e'
calibracao nova, e' reproducao de numero ja decidido, entao nao precisa do
split congelado: mesma regra da memoria `frozen_split_scope_2026_08_21`,
"medir numero ja decidido pode usar a base toda"). Capital = `capital_
minimo_brl` no preco do INICIO do historico disponivel de cada simbolo.

Uso:
    python scripts/daytrade/gremahtick_defesa_corte_sweep_2026_09_03.py
    python scripts/daytrade/gremahtick_defesa_corte_sweep_2026_09_03.py --baseline
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


SYMBOLS = ("PMAM3", "KLBN3")

#: Grade de `defesa_ativa` -- 3 x 3 = 9 combos + 1 baseline (desligado,
#: compartilhado com o corte_persistencia abaixo).
DEFESA_GATILHO_GRID = [0.3, 0.5, 0.8]
DEFESA_PROXIMIDADE_GRID = [0.1, 0.3, 0.5]

#: Grade de `corte_persistencia_ativo` -- 4 x 3 = 12 combos. `min_barras` em
#: NEGOCIOS/atualizacoes (ver a ressalva de unidade na docstring do modulo
#: `gremah_tick.py`), nao minutos.
CORTE_MIN_BARRAS_GRID = [5, 10, 30, 60]
CORTE_FRAC_ADVERSO_GRID = [0.6, 0.8, 1.0]

#: Colunas EXTRA -- entram DEPOIS das 12 da base (backtest/intraday/report.py).
EXTRAS = ("defesa_g%", "defesa_p%", "corte_min", "corte_frac%", "defesa_n", "corte_n", "recusa_capital")

UNLOCK_REASON = (
    "defesa_recuo/corte_persistencia (2026-09-03) mexem em regra de SAIDA de "
    "GremahTick em producao real (PMAM3/KLBN3) -- disciplina IS/OOS exigida "
    "por AGENTS.md/CLAUDE.md para 'melhorar estrategia'."
)

_BARS_PROC: dict[str, object] = {}


def _locked_bars(symbol: str):
    """Carrega ticks -> barras degeneradas -> `LockedBars` desbloqueado, UMA
    vez por processo filho (nao por tarefa) -- mesmo padrao de
    `copawin_corte_persistencia_sweep_2026_09_03.py::_bars_do_processo`."""
    if symbol not in _BARS_PROC:
        from _geometria_comum import REGIME_START
        from backtest.intraday.frozen_split import LockedBars, declare_frozen_split
        from backtest.intraday.profiles import profile_for
        from market_data_intraday.tick_bars import ticks_to_degenerate_bars
        from market_data_intraday.tick_storage import load_ticks

        ticks = load_ticks(symbol)
        bars = ticks_to_degenerate_bars(ticks) if not ticks.empty else pd.DataFrame()
        regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
        bars = bars.loc[bars.index >= regime_start]

        profile = profile_for(symbol)
        split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
        locked = LockedBars(bars, split)
        locked.unlock(UNLOCK_REASON)
        _BARS_PROC[symbol] = locked
    return _BARS_PROC[symbol]


def _monta_specs() -> list[dict]:
    specs: list[dict] = []
    for symbol in SYMBOLS:
        for janela in ("IS", "OOS"):
            specs.append(dict(
                rotulo=f"{symbol} {janela} baseline (off)", symbol=symbol, janela=janela,
                mecanismo="baseline", defesa_g=None, defesa_p=None, corte_min=None, corte_frac=None,
            ))
            for g in DEFESA_GATILHO_GRID:
                for p in DEFESA_PROXIMIDADE_GRID:
                    specs.append(dict(
                        rotulo=f"{symbol} {janela} defesa g{g*100:.0f}% p{p*100:.0f}%",
                        symbol=symbol, janela=janela, mecanismo="defesa",
                        defesa_g=g, defesa_p=p, corte_min=None, corte_frac=None,
                    ))
            for m in CORTE_MIN_BARRAS_GRID:
                for f in CORTE_FRAC_ADVERSO_GRID:
                    specs.append(dict(
                        rotulo=f"{symbol} {janela} corte m{m} f{f*100:.0f}%",
                        symbol=symbol, janela=janela, mecanismo="corte",
                        defesa_g=None, defesa_p=None, corte_min=m, corte_frac=f,
                    ))
    return specs


def _roda_uma(spec: dict) -> tuple[str, dict]:
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.lab.gremah_tick import GremahTick

    symbol = spec["symbol"]
    locked = _locked_bars(symbol)
    bars = locked.in_sample() if spec["janela"] == "IS" else locked.out_of_sample()
    profile = profile_for(symbol)
    preco_ref = float(bars.iloc[0]["close"])
    capital_inicial = capital_minimo_brl(preco_ref)

    kwargs = dict(symbol=symbol)
    if spec["mecanismo"] == "defesa":
        kwargs.update(defesa_ativa=True, defesa_gatilho_stop_pct=spec["defesa_g"],
                      defesa_alvo_proximidade_pct=spec["defesa_p"])
    elif spec["mecanismo"] == "corte":
        kwargs.update(corte_persistencia_ativo=True, corte_persistencia_min_barras=spec["corte_min"],
                      corte_persistencia_frac_adverso=spec["corte_frac"])
    strat = GremahTick(**kwargs)

    # Contagem EXATA de disparos -- ver a docstring do modulo ("Contagem de
    # disparos"): o motor colapsa todo `Exit(reason=...)` no mesmo
    # `IntradayExitReason.SIGNAL`, entao a unica forma de distinguir
    # `defesa_recuo` de `corte_persistencia` (ou de outros Exit da mesma
    # classe) e' contar na PROPRIA funcao que decide, via monkeypatch de
    # instancia (nao de classe -- nao vaza para outra instancia no mesmo
    # processo).
    contagem = {"defesa_n": 0, "corte_n": 0}
    if spec["mecanismo"] == "defesa":
        _orig = strat._defesa_deve_fechar

        def _wrap_defesa(pos, bar, _orig=_orig):
            r = _orig(pos, bar)
            if r:
                contagem["defesa_n"] += 1
            return r
        strat._defesa_deve_fechar = _wrap_defesa
    elif spec["mecanismo"] == "corte":
        _orig = strat._corte_persistencia_deve_fechar

        def _wrap_corte(pos, bar, _orig=_orig):
            r = _orig(pos, bar)
            if r:
                contagem["corte_n"] += 1
            return r
        strat._corte_persistencia_deve_fechar = _wrap_corte

    econ_tick_value = econ_tick_size = 0.01  # B3 acao: ver data/_economics_cache.json
    cfg = config_for(
        profile, trade_tick_value=econ_tick_value, trade_tick_size=econ_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)

    extras = {
        "defesa_g%": "—" if spec["defesa_g"] is None else num_br(spec["defesa_g"] * 100, 0),
        "defesa_p%": "—" if spec["defesa_p"] is None else num_br(spec["defesa_p"] * 100, 0),
        "corte_min": "—" if spec["corte_min"] is None else str(spec["corte_min"]),
        "corte_frac%": "—" if spec["corte_frac"] is None else num_br(spec["corte_frac"] * 100, 0),
        "defesa_n": str(contagem["defesa_n"]),
        "corte_n": str(contagem["corte_n"]),
        "recusa_capital": str(resultado.ordens_recusadas_por_capital),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, capital_inicial, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item, EXTRAS), flush=True)

    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        retorno_pct=item.retorno_pct, maxdd_pct=item.maxdd_pct, capital_final=item.capital_final,
        extras=item.extras, aviso=item.aviso,
        symbol=symbol, janela=spec["janela"], mecanismo=spec["mecanismo"],
        defesa_g=spec["defesa_g"], defesa_p=spec["defesa_p"],
        corte_min=spec["corte_min"], corte_frac=spec["corte_frac"],
        defesa_n=contagem["defesa_n"], corte_n=contagem["corte_n"],
        preco_ref=preco_ref, capital_inicial=capital_inicial,
    )
    return buf.getvalue(), campos


def _n_workers(n_tarefas: int) -> int:
    return max(1, min(n_tarefas, 6, os.cpu_count() or 4))


def main() -> None:
    from backtest.intraday.report import LinhaResultado, cabecalho, tabela

    t0 = time.perf_counter()
    specs = _monta_specs()
    n_workers = _n_workers(len(specs))
    print(f"[gremahtick_defesa_corte_sweep] {len(specs)} tarefas "
          f"({len(SYMBOLS)} simbolos x 2 janelas x (1 baseline + 9 defesa + 12 corte)), "
          f"{n_workers} processos", flush=True)
    print(cabecalho(EXTRAS), flush=True)

    resultados: dict[str, dict] = {}
    concluidos = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            concluidos += 1
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados[futures[future]] = campos
            print(f"[gremahtick_defesa_corte_sweep] {concluidos}/{len(specs)} concluido(s) "
                  f"({futures[future]})", flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[gremahtick_defesa_corte_sweep] motor: {dt:.1f}s em {n_workers} processos\n")

    for symbol in SYMBOLS:
        print(f"\n{'#'*90}\n{symbol}\n{'#'*90}")
        for janela in ("IS", "OOS"):
            campos = [c for spec, c in ((s, resultados[s["rotulo"]]) for s in specs)
                      if c["symbol"] == symbol and c["janela"] == janela]
            linhas = [
                LinhaResultado(
                    variante=c["variante"], liquido_brl=c["liquido_brl"], maxdd_brl=c["maxdd_brl"],
                    win_rate_pct=c["win_rate_pct"], trades=c["trades"], pregoes=c["pregoes"],
                    retorno_pct=c["retorno_pct"], maxdd_pct=c["maxdd_pct"],
                    capital_final=c["capital_final"], extras=c["extras"], aviso=c["aviso"],
                )
                for c in campos
            ]
            preco_ref = campos[0]["preco_ref"] if campos else float("nan")
            capital_ini = campos[0]["capital_inicial"] if campos else float("nan")
            print(f"\n=== {symbol} -- janela {janela} (preco_ref=R${br(preco_ref, 4)}, "
                  f"capital_inicial=R${br(capital_ini)}) ===")
            print(tabela(linhas, EXTRAS))

            baseline = next(c for c in campos if c["mecanismo"] == "baseline")
            melhor_defesa = max((c for c in campos if c["mecanismo"] == "defesa"),
                                key=lambda c: c["liquido_brl"], default=None)
            melhor_corte = max((c for c in campos if c["mecanismo"] == "corte"),
                               key=lambda c: c["liquido_brl"], default=None)
            total_defesa_n = sum(c["defesa_n"] for c in campos if c["mecanismo"] == "defesa")
            total_corte_n = sum(c["corte_n"] for c in campos if c["mecanismo"] == "corte")
            print(f"[diagnostico {symbol}/{janela}] baseline: liquido=R${br(baseline['liquido_brl'])} "
                  f"({baseline['trades']} trades)")
            print(f"[diagnostico {symbol}/{janela}] defesa_recuo: {total_defesa_n} disparo(s) "
                  f"somados nas 9 combinacoes da grade (0 = mecanismo NUNCA disparou nesta janela)")
            if melhor_defesa is not None:
                print(f"[diagnostico {symbol}/{janela}] melhor combo defesa: g{melhor_defesa['defesa_g']*100:.0f}% "
                      f"p{melhor_defesa['defesa_p']*100:.0f}% -> liquido=R${br(melhor_defesa['liquido_brl'])} "
                      f"({melhor_defesa['defesa_n']} disparos) vs baseline R${br(baseline['liquido_brl'])}")
            print(f"[diagnostico {symbol}/{janela}] corte_persistencia: {total_corte_n} disparo(s) "
                  f"somados nas 12 combinacoes da grade")
            if melhor_corte is not None:
                print(f"[diagnostico {symbol}/{janela}] melhor combo corte: m{melhor_corte['corte_min']} "
                      f"f{melhor_corte['corte_frac']*100:.0f}% -> liquido=R${br(melhor_corte['liquido_brl'])} "
                      f"({melhor_corte['corte_n']} disparos) vs baseline R${br(baseline['liquido_brl'])}")

    print(f"\n[gremahtick_defesa_corte_sweep] total: {time.perf_counter() - t0:.1f}s")


# ============================================================================
# BASELINE dos 9 simbolos confirmados -- `--baseline`. Mecanismos DESLIGADOS
# (config de producao atual, sem nenhum parametro novo), historico COMPLETO
# disponivel localmente (IS+OOS combinados -- reproducao de numero ja
# decidido, ver a docstring do modulo).
# ============================================================================

def _full_bars(symbol: str) -> pd.DataFrame:
    from _geometria_comum import REGIME_START
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars
    from market_data_intraday.tick_storage import load_ticks

    ticks = load_ticks(symbol)
    if ticks.empty:
        return pd.DataFrame()
    bars = ticks_to_degenerate_bars(ticks)
    regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
    return bars.loc[bars.index >= regime_start]


def _roda_baseline(symbol: str, tail_ticks: int | None) -> tuple[str, dict]:
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.lab.gremah_tick import GremahTick

    bars = _full_bars(symbol)
    aviso_corte = ""
    if bars.empty:
        buf = io.StringIO()
        return buf.getvalue(), dict(symbol=symbol, sem_dado=True)
    if tail_ticks is not None and len(bars) > tail_ticks:
        aviso_corte = f" [cortado p/ ultimos {tail_ticks} de {len(bars)} negocios]"
        bars = bars.tail(tail_ticks)

    profile = profile_for(symbol)
    preco_ref = float(bars.iloc[0]["close"])
    capital_inicial = capital_minimo_brl(preco_ref)
    strat = GremahTick(symbol=symbol)  # producao pura -- defesa/corte OFF (default)
    cfg = config_for(
        profile, trade_tick_value=0.01, trade_tick_size=0.01,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    item = linha_de_resultado(f"{symbol}{aviso_corte}", resultado, capital_inicial)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item), flush=True)

    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        retorno_pct=item.retorno_pct, maxdd_pct=item.maxdd_pct, capital_final=item.capital_final,
        extras=item.extras, aviso=item.aviso, symbol=symbol, sem_dado=False,
        preco_ref=preco_ref, capital_inicial=capital_inicial, n_negocios=len(bars),
        janela=f"{bars.index.min()} -> {bars.index.max()}",
    )
    return buf.getvalue(), campos


def main_baseline(tail_ticks: int | None) -> None:
    from _geometria_comum import SIMBOLOS  # noqa: F401 -- so' para checar import ok
    from backtest.intraday.report import LinhaResultado, cabecalho, tabela
    from strategy.daytrade.lab.gremah_tick import TICK_CONFIRMED_SYMBOLS

    t0 = time.perf_counter()
    symbols = list(TICK_CONFIRMED_SYMBOLS)
    n_workers = _n_workers(len(symbols))
    print(f"[gremahtick_baseline] {len(symbols)} simbolos confirmados, {n_workers} processos",
          flush=True)
    print(cabecalho(), flush=True)

    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_baseline, s, tail_ticks): s for s in symbols}
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            symbol = futures[future]
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados[symbol] = campos
            print(f"[gremahtick_baseline] {concluidos}/{len(symbols)} concluido(s) ({symbol})",
                  flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[gremahtick_baseline] motor: {dt:.1f}s em {n_workers} processos\n")

    print(f"\n{'='*90}\nBASELINE GremahTick -- 9 simbolos confirmados, mecanismos novos DESLIGADOS "
          "(config de producao), historico COMPLETO local por simbolo\n" + "=" * 90)
    linhas = []
    for symbol in symbols:  # ordem de TICK_CONFIRMED_SYMBOLS
        c = resultados[symbol]
        if c.get("sem_dado"):
            print(f"{symbol}: SEM DADO LOCAL")
            continue
        linhas.append(LinhaResultado(
            variante=c["variante"], liquido_brl=c["liquido_brl"], maxdd_brl=c["maxdd_brl"],
            win_rate_pct=c["win_rate_pct"], trades=c["trades"], pregoes=c["pregoes"],
            retorno_pct=c["retorno_pct"], maxdd_pct=c["maxdd_pct"],
            capital_final=c["capital_final"], extras=c["extras"], aviso=c["aviso"],
        ))
    print(tabela(linhas))
    print("\n--- referencia (preco/capital/janela por simbolo) ---")
    for symbol in symbols:
        c = resultados[symbol]
        if c.get("sem_dado"):
            continue
        print(f"{symbol:<8} preco_ref=R${br(c['preco_ref'], 4):>10}  "
              f"capital_inicial=R${br(c['capital_inicial']):>10}  "
              f"negocios={c['n_negocios']:>9}  janela={c['janela']}")

    print(f"\n[gremahtick_baseline] total: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true",
                        help="imprime a tabela baseline dos 9 simbolos confirmados, "
                             "em vez da varredura defesa/corte de PMAM3/KLBN3")
    parser.add_argument("--tail-ticks", type=int, default=None,
                        help="so' no modo --baseline: usa os ultimos N negocios de cada "
                             "simbolo (ex.: CSAN3, pesado demais pra rodar inteiro)")
    args = parser.parse_args()
    if args.baseline:
        main_baseline(args.tail_ticks)
    else:
        main()
