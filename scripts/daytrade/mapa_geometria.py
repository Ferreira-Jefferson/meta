"""Mapa da GEOMETRIA que a familia `gremah` realmente armou, pregao a pregao.

A pergunta que este script responde (2026-08-26): o `profit_pct` calibrado por
simbolo nao decide o alvo -- o PISO de 1 tick de `_ticks_from_pct`
(`max(1, round(price * pct / tick_size))`) decide, em 9 dos 10 simbolos. Isso
o repo ja sabia (ver a docstring de `sweep_gremah_vol.py`). O que ainda nao
estava medido e' a consequencia SEGUINTE: alvo, espacamento e stop saem todos
do MESMO `profit_pct` --

    profit_ticks  = _ticks_from_pct(preco, profit_pct)
    spacing_ticks = _ticks_from_pct(preco, profit_pct * spacing_multiplier)
    stop_ticks    = _ticks_from_pct(preco, profit_pct * stop_multiplier)

-- entao, quando o preco do ativo cai o bastante, os TRES afundam no piso e
COLAPSAM na mesma distancia. Um robo que arrisca 1 tick para ganhar 1 tick nao
tem calibracao nenhuma: nenhum dos tres parametros tem efeito. Foi o que
aconteceu com a PMAM3, cujo preco caiu de R$4,53 para R$0,13 DENTRO da janela
de backtest -- o stop dela encolheu de 29 ticks para 1.

O script NAO reimplementa a formula: ele embrulha o `_session_ticks` da
propria instancia de producao e roda o backtest, registrando o que a
estrategia de fato armou -- inclusive no caminho por VOLATILIDADE, que tem a
mesma estrutura de acoplamento (`alvo_vol_mult * stop_mult`) e portanto o
mesmo colapso.

Saida em tabela propria, nao na TABELA PADRAO de `backtest/intraday/report.py`:
aqui nao ha resultado de backtest nenhum para reportar (lucro, MaxDD, win
rate). E' diagnostico de configuracao, outra grandeza.

Uso:
    python scripts/daytrade/mapa_geometria.py --jobs 8
    python scripts/daytrade/mapa_geometria.py --symbol PMAM3
"""
from __future__ import annotations

import argparse
import os
import statistics
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
from backtest.intraday.report import num_br  # noqa: E402

COLUNAS = (
    ("simbolo", 9, "<"), ("motor", 7, "<"), ("armacoes", 10, ">"),
    ("alvo p50", 10, ">"), ("espac p50", 11, ">"), ("stop p50", 10, ">"),
    ("stop min-max", 14, ">"), ("alvo no piso", 14, ">"),
    ("DEGENERADO", 12, ">"), ("preco colapso", 15, ">"),
)


def _celula(texto, largura, alinha):
    return f"{texto:{alinha}{largura}}"


def cabecalho() -> str:
    cab = "".join(_celula(n, l, a) for n, l, a in COLUNAS)
    return cab + "\n" + "-" * len(cab)


def _preco_de_colapso(profit_pct, stop_multiplier, tick_size) -> float | None:
    """Preco abaixo do qual o STOP cai para 1 tick e encosta no alvo.

    `round` do Python usa arredondamento bancario (`.5` vai para o PAR mais
    proximo, e 2 e' par), entao o stop deixa de ser 1 tick exatamente quando
    `preco * profit_pct * stop_multiplier / tick_size >= 1.5`."""
    denom = profit_pct * stop_multiplier
    if denom <= 0:
        return None
    return 1.5 * tick_size / denom


def _mapear_par(symbol: str, motor: str, econ: Economics, tail: int | None) -> dict:
    run_bars, profile, preco_ref = carregar_is(symbol, motor, tail)
    if run_bars.empty:
        return {"symbol": symbol, "motor": motor, "erro": "sem dado local"}

    strat = classe_do_motor(motor)(symbol=symbol)
    registros: list[tuple[float, int, int, int]] = []

    # Embrulha `_session_ticks` NA INSTANCIA (nao na classe): registra o que a
    # producao armou, sem tocar em `src/` e sem reimplementar a formula. Pega
    # os DOIS sitios de chamada -- a fase fixa (armada na abertura do pregao) e
    # a fase rolante (rearmada a cada reancoragem).
    original = strat._session_ticks

    def _espiao(price_ref: float):
        saida = original(price_ref)
        registros.append((price_ref, *saida))
        return saida

    strat._session_ticks = _espiao

    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
    )
    run_intraday_backtest(run_bars, strat, config)

    if not registros:
        return {"symbol": symbol, "motor": motor, "erro": "nenhuma armacao"}

    alvos = [r[1] for r in registros]
    espacos = [r[2] for r in registros]
    stops = [r[3] for r in registros]
    n = len(registros)
    calib = calibracao_do_motor(motor)[symbol]

    return {
        "symbol": symbol, "motor": motor, "n": n,
        "alvo_p50": statistics.median(alvos),
        "espac_p50": statistics.median(espacos),
        "stop_p50": statistics.median(stops),
        "stop_min": min(stops), "stop_max": max(stops),
        "alvo_no_piso_pct": 100.0 * sum(1 for a in alvos if a <= 1) / n,
        "degenerado_pct": 100.0 * sum(1 for a, s in zip(alvos, stops) if s <= a) / n,
        "preco_colapso": _preco_de_colapso(calib.profit_pct, calib.stop_multiplier,
                                           strat.tick_size),
        "preco_min": min(r[0] for r in registros),
        "preco_max": max(r[0] for r in registros),
        "vol": strat.alvo_por_volatilidade,
    }


def _linha(d: dict) -> str:
    if "erro" in d:
        return f"{d['symbol']:<9}{d['motor']:<7}{d['erro']}"
    colapso = ("-" if d["vol"] or d["preco_colapso"] is None
               else "R$ " + num_br(d["preco_colapso"], 3))
    valores = [
        d["symbol"], d["motor"] + ("*" if d["vol"] else ""), str(d["n"]),
        num_br(d["alvo_p50"], 1), num_br(d["espac_p50"], 1), num_br(d["stop_p50"], 1),
        f"{d['stop_min']}-{d['stop_max']}",
        num_br(d["alvo_no_piso_pct"], 1) + "%",
        num_br(d["degenerado_pct"], 1) + "%",
        colapso,
    ]
    return "".join(_celula(v, l, a) for v, (_, l, a) in zip(valores, COLUNAS))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", action="append", choices=list(SIMBOLOS), default=None)
    parser.add_argument("--motor", action="append", choices=list(MOTORES), default=None)
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--econ-cache", default=None)
    parser.add_argument("--tail-ticks", type=int, default=None)
    args = parser.parse_args()

    symbols = args.symbol or list(SIMBOLOS)
    motores = args.motor or list(MOTORES)
    pares = [(s, m) for s in symbols for m in motores]

    cache = Path(args.econ_cache) if args.econ_cache else ROOT / "data" / "_economics_cache.json"
    economics = carregar_economics(symbols, cache)

    max_workers = args.jobs or min(len(pares), os.cpu_count() or 4)
    print(f"[mapa] {len(pares)} par(es) em ate {max_workers} processo(s)...", flush=True)
    print(cabecalho(), flush=True)

    resultados = []
    # `as_completed` + `flush=True`: cada par sai na tela assim que fica pronto,
    # em vez de tudo so' no fim (os pares sao muito desiguais -- tick de CSAN3
    # contra M1 de LPSB3).
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_mapear_par, s, m, economics[s], args.tail_ticks): (s, m)
                   for s, m in pares}
        for future in as_completed(futures):
            symbol, motor = futures[future]
            try:
                d = future.result()
            except Exception as exc:  # noqa: BLE001
                d = {"symbol": symbol, "motor": motor,
                     "erro": f"FALHOU {type(exc).__name__}: {exc}"}
            resultados.append(d)
            print(_linha(d), flush=True)

    print("")
    print("(*) simbolo no caminho por VOLATILIDADE: o preco de colapso nao se aplica,")
    print("    porque o alvo vem da mediana do range diario, nao do preco.")
    print("DEGENERADO = % das armacoes com stop <= alvo: nenhum parametro tem efeito.")

    bons = [d for d in resultados if "erro" not in d]
    if bons:
        pior = max(bons, key=lambda d: d["degenerado_pct"])
        print("")
        print(f"Pior par: {pior['symbol']}/{pior['motor']} — "
              f"{num_br(pior['degenerado_pct'], 1)}% das armacoes degeneradas.")


if __name__ == "__main__":
    main()
