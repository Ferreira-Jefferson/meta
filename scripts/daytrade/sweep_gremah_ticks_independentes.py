"""Varredura da familia `gremah` com ALVO E STOP INDEPENDENTES, em ticks.

O experimento que a grade antiga era incapaz de fazer. Ate' 2026-08-26 alvo,
espacamento e stop saiam todos do MESMO `profit_pct`:

    profit_ticks  = _ticks_from_pct(preco, profit_pct)
    spacing_ticks = _ticks_from_pct(preco, profit_pct * spacing_multiplier)
    stop_ticks    = _ticks_from_pct(preco, profit_pct * stop_multiplier)

Subir `profit_pct` para tirar o alvo do piso de 1 tick subia o stop e o
espacamento na mesma proporcao. A grade percentual
(`sweep_gremah_tick.py::PROFIT_PCT_GRID`) portanto nunca testou "alvo de 2
ticks com o stop onde esta" -- ela so' testou "tudo maior junto", e perdeu.
Isso e' resultado sobre a ESCALA da geometria, nao sobre a FORMA dela.

Aqui os tres eixos sao independentes, em ticks inteiros. A pergunta e' se
alguma FORMA de geometria que a parametrizacao velha nao conseguia expressar
tem edge.

Unidade de paralelizacao: (simbolo, motor, alvo) = 10 x 2 x 3 = 60 unidades
para ~960 backtests. Mais fina que a do `sweep_gremah_tick.py` (que paraleliza
so' por simbolo, 10 unidades) de proposito: as unidades sao muito desiguais --
um tick de CSAN3 tem ordens de grandeza mais registros que um M1 de LPSB3 --
e com 60 unidades o resultado comeca a aparecer na tela ~6x mais cedo e ~6x
mais vezes.

A BASELINE e' recalculada nesta mesma rodada, nunca comparada contra numero
antigo: o commit `dffeeae` mudou o dimensionamento de posicao e os valores
absolutos anteriores nao reproduzem mais. Toda comparacao aqui e' interna.

So' IN-SAMPLE. Nenhuma chamada a `unlock()` -- a confirmacao OOS e' uma
passada so', depois, com a lista de candidatos ja fechada.

Uso:
    python scripts/daytrade/sweep_gremah_ticks_independentes.py --symbol PMAM3 --jobs 8
    python scripts/daytrade/sweep_gremah_ticks_independentes.py --jobs 8
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _geometria_comum import (  # noqa: E402
    MOTORES, SIMBOLOS, Economics, calibracao_do_motor, carregar_economics,
    carregar_is, classe_do_motor,
)
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402

#: Alvo em ticks. 1 e' o que a producao usa hoje em 9 dos 10 simbolos (por
#: acidente do piso, nao por escolha) -- fica na grade como piso de comparacao.
ALVO_TICKS_GRID = (1, 2, 3)

#: Espacamento como MULTIPLO do alvo. Nao e' um eixo livre nesta primeira
#: rodada: com 3 eixos livres a grade explode, e o espacamento e' o menos
#: suspeito dos tres (ele so' decide onde a ordem repousa, nao o risco).
#: A rodada fina, depois, solta este eixo.
ESPACO_MULT_GRID = (1, 2, 4)

#: Stop em ticks, ABSOLUTO. Este e' o eixo que a parametrizacao velha nao
#: conseguia mover sem arrastar o alvo junto.
STOP_TICKS_GRID = (2, 4, 8, 15, 25, 40)

MIN_TRADES_CONFIAVEL = 30

#: Colunas EXTRA -- entram DEPOIS das 12 da base (`backtest/intraday/report.py`).
EXTRAS = ("confiavel",)


def _celulas(alvo: int):
    """As combinacoes de um alvo. `stop <= alvo` fica DE FORA: e' exatamente o
    regime degenerado que ja sabemos perder (ver
    `strategy.daytrade.base.geometria_e_degenerada`), e gastar backtest nele
    seria re-medir o problema em vez de procurar a saida."""
    for mult in ESPACO_MULT_GRID:
        for stop in STOP_TICKS_GRID:
            if stop > alvo:
                yield alvo, alvo * mult, stop


def _rodar(profile, run_bars, econ: Economics, strat, preco_ref: float, label: str):
    capital_inicial = capital_minimo_brl(preco_ref)
    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
    )
    result = run_intraday_backtest(run_bars, strat, config)
    n = len(result.trades)
    return linha_de_resultado(
        label, result, capital_inicial,
        extras={"confiavel": "sim" if n >= MIN_TRADES_CONFIAVEL
                else f"NAO<{MIN_TRADES_CONFIAVEL}"},
    )


def _unidade(symbol: str, motor: str, alvo: int, econ: Economics,
             tail: int | None, com_baseline: bool) -> dict:
    """Uma unidade de trabalho: um alvo, num simbolo, num motor."""
    run_bars, profile, preco_ref = carregar_is(symbol, motor, tail)
    if run_bars.empty:
        return {"symbol": symbol, "motor": motor, "alvo": alvo,
                "erro": "sem dado local", "linhas": [], "baseline": None}

    Classe = classe_do_motor(motor)
    baseline = None
    if com_baseline:
        # Calculada UMA vez por (simbolo, motor), na unidade do menor alvo --
        # as outras duas unidades do mesmo par a herdam na consolidacao.
        calib = calibracao_do_motor(motor)[symbol]
        baseline = _rodar(
            profile, run_bars, econ, Classe(symbol=symbol), preco_ref,
            f"atual ({calib.profit_pct*100:.2f}%/{calib.stop_multiplier:.0f}x)",
        )

    linhas = []
    for a, espaco, stop in _celulas(alvo):
        strat = Classe(symbol=symbol, profit_ticks=a, spacing_ticks=espaco, stop_ticks=stop)
        linhas.append(_rodar(profile, run_bars, econ, strat, preco_ref,
                             f"T{a} E{espaco} S{stop}"))
    return {"symbol": symbol, "motor": motor, "alvo": alvo,
            "linhas": linhas, "baseline": baseline,
            "registros": len(run_bars)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", choices=list(SIMBOLOS), default=None)
    parser.add_argument("--motor", action="append", choices=list(MOTORES), default=None)
    parser.add_argument("--top", type=int, default=8,
                        help="combinacoes mostradas por (simbolo, motor) na consolidacao final")
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--econ-cache", default=None)
    parser.add_argument("--tail-ticks", type=int, default=None)
    args = parser.parse_args()

    symbols = args.symbol or list(SIMBOLOS)
    motores = args.motor or list(MOTORES)
    cache = Path(args.econ_cache) if args.econ_cache else ROOT / "data" / "_economics_cache.json"
    economics = carregar_economics(symbols, cache)

    unidades = [
        (s, m, alvo, alvo == ALVO_TICKS_GRID[0])
        for s in symbols for m in motores for alvo in ALVO_TICKS_GRID
    ]
    max_workers = args.jobs or min(len(unidades), os.cpu_count() or 4)
    print(f"[sweep] {len(unidades)} unidade(s) em ate {max_workers} processo(s); "
          f"grade de {sum(1 for _ in _celulas(1))}+{sum(1 for _ in _celulas(2))}"
          f"+{sum(1 for _ in _celulas(3))} celulas por par", flush=True)

    # `as_completed`, nunca `pool.map`: `map` so' entrega na ORDEM de submissao,
    # entao uma unidade rapida fica presa atras de uma lenta mesmo ja tendo
    # terminado. `flush=True` em todo print porque stdout redirecionado a
    # arquivo e' bufferizado em bloco -- sem isso a rodada parece travada.
    por_par: dict[tuple[str, str], list] = {}
    baselines: dict[tuple[str, str], object] = {}
    concluidas = 0
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_unidade, s, m, alvo, economics[s], args.tail_ticks, base): (s, m, alvo)
            for s, m, alvo, base in unidades
        }
        for future in as_completed(futures):
            concluidas += 1
            symbol, motor, alvo = futures[future]
            try:
                d = future.result()
            except Exception as exc:  # noqa: BLE001 -- uma unidade nao derruba a rodada
                print(f"[sweep] {concluidas}/{len(unidades)}  {symbol}/{motor} alvo={alvo}: "
                      f"FALHOU {type(exc).__name__}: {exc}", flush=True)
                continue
            if d.get("erro"):
                print(f"[sweep] {concluidas}/{len(unidades)}  {symbol}/{motor}: {d['erro']}",
                      flush=True)
                continue

            chave = (symbol, motor)
            por_par.setdefault(chave, []).extend(d["linhas"])
            if d["baseline"] is not None:
                baselines[chave] = d["baseline"]

            # Mini-tabela da unidade, na hora -- nada espera o fim da rodada.
            melhor = max(d["linhas"], key=lambda it: it.liquido_brl, default=None)
            resumo = (f"melhor {melhor.variante} R$ {melhor.liquido_brl:.2f}"
                      if melhor else "sem celula valida")
            print(f"[sweep] {concluidas}/{len(unidades)}  {symbol}/{motor} alvo={alvo}: "
                  f"{len(d['linhas'])} celulas, {resumo}", flush=True)

    print("\n" + "=" * 100, flush=True)
    for chave in sorted(por_par):
        symbol, motor = chave
        linhas = sorted(por_par[chave], key=lambda it: it.liquido_brl, reverse=True)
        print(f"\n=== {symbol} / motor={motor} — IN-SAMPLE, alvo e stop independentes ===",
              flush=True)
        print(cabecalho(EXTRAS), flush=True)
        if chave in baselines:
            print(linha(baselines[chave], EXTRAS), flush=True)
        for item in linhas[:args.top]:
            print(linha(item, EXTRAS), flush=True)
        if len(linhas) > args.top:
            print(f"  ... {len(linhas) - args.top} combinacao(oes) fora do top-{args.top}",
                  flush=True)


if __name__ == "__main__":
    main()
