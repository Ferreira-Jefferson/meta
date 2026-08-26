"""Congela o comportamento ATUAL da familia `gremah` em disco, para provar
depois que uma mudanca de codigo foi byte-a-byte inofensiva.

Motivo (2026-08-26): a rodada de GEOMETRIA EM TICKS acrescenta parametros as
duas estrategias, e uma delas (`GremahTick` em PMAM3) esta na rua com dinheiro
real. O teste unitario prova que `_session_ticks` continua devolvendo o mesmo
numero; ele NAO prova que o `on_bar` inteiro -- fase fixa -> rolante,
`_build_entry`, divisao de entrada, TTL de saida, realocacao por caixa --
continua produzindo os MESMOS trades. Este script prova, comparando trade a
trade.

Grava um arquivo por par (simbolo x motor) com: cabecalho da run, a linha da
TABELA PADRAO e o digest de cada trade fechado. `diff -r antes/ depois/` tem
que sair VAZIO.

Uso:
    python scripts/daytrade/snapshot_baseline.py --out /caminho/antes --jobs 8
    python scripts/daytrade/snapshot_baseline.py --out /caminho/depois --jobs 8
    diff -r /caminho/antes /caminho/depois && echo COMPATIVEL

As duas rodadas TEM de usar o mesmo cache de `symbol_economics` (default:
`economics.json` na pasta acima de `--out`) -- o terminal MT5 pode devolver
valor diferente em outro dia, e isso apareceria como diferenca que a mudanca
de codigo nao causou. Ver `_geometria_comum.carregar_economics`.
"""
from __future__ import annotations

import argparse
import hashlib
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


def _digest_trades(trades) -> list[str]:
    """Uma linha por trade, com casas decimais FIXAS -- `repr` de float varia
    entre plataformas e transformaria o diff em ruido."""
    fora = []
    for t in trades:
        fora.append(
            f"{t.entry_ts.isoformat()}|{t.exit_ts.isoformat()}|{t.side}|"
            f"{t.entry_price:.10f}|{t.exit_price:.10f}|{t.quantity}|"
            f"{t.exit_reason}|{t.fees_total:.10f}|{t.slippage_total:.10f}|"
            f"{t.pnl_brl:.10f}"
        )
    return fora


def _snapshot_par(symbol: str, motor: str, econ: Economics, out_dir: str,
                  tail: int | None) -> str:
    run_bars, profile, preco_ref = carregar_is(symbol, motor, tail)
    destino = Path(out_dir) / f"{symbol}_{motor}.txt"
    if run_bars.empty:
        destino.write_text(f"{symbol} {motor}: SEM DADO LOCAL\n", encoding="utf-8")
        return f"{symbol}/{motor}: sem dado local"

    strat = classe_do_motor(motor)(symbol=symbol)
    capital_inicial = capital_minimo_brl(preco_ref)
    config = config_for(
        profile,
        trade_tick_value=econ.trade_tick_value,
        trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker,
        preco_atual=preco_ref,
    )
    result = run_intraday_backtest(run_bars, strat, config)
    calib = calibracao_do_motor(motor)[symbol]
    item = linha_de_resultado(f"atual {symbol}/{motor}", result, capital_inicial)

    digest = _digest_trades(result.trades)
    sha = hashlib.sha256("\n".join(digest).encode("utf-8")).hexdigest()
    texto = "\n".join([
        f"# {symbol} / motor={motor}",
        f"# registros IS: {len(run_bars)}  janela: {run_bars.index.min()} -> {run_bars.index.max()}",
        f"# preco_ref: {preco_ref:.10f}  capital_inicial: {capital_inicial:.10f}",
        f"# calibracao: profit_pct={calib.profit_pct!r} stop_multiplier={calib.stop_multiplier!r}",
        f"# economics: tick_value={econ.trade_tick_value!r} tick_size={econ.trade_tick_size!r}",
        f"# trades: {len(digest)}  sha256: {sha}",
        cabecalho(),
        linha(item),
        "# --- trades ---",
        *digest,
        "",
    ])
    destino.write_text(texto, encoding="utf-8")
    return (f"{symbol}/{motor}: {len(digest)} trades, liquido R$ {item.liquido_brl:.2f}, "
            f"sha {sha[:12]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="pasta destino (criada se nao existir)")
    parser.add_argument("--symbol", action="append", choices=list(SIMBOLOS), default=None)
    parser.add_argument("--motor", action="append", choices=list(MOTORES), default=None)
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--econ-cache", default=None,
                        help="default: economics.json na pasta ACIMA de --out, para "
                             "'antes' e 'depois' compartilharem o mesmo valor")
    parser.add_argument("--tail-ticks", type=int, default=None,
                        help="usa so' os ultimos N registros do IS (corte de tempo, "
                             "nunca toca o OOS) -- precisa ser o MESMO nas duas rodadas")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = Path(args.econ_cache) if args.econ_cache else out_dir.parent / "economics.json"

    symbols = args.symbol or list(SIMBOLOS)
    motores = args.motor or list(MOTORES)
    pares = [(s, m) for s in symbols for m in motores]

    economics = carregar_economics(symbols, cache)
    print(f"[snapshot] economics de {len(economics)} simbolo(s) em {cache}", flush=True)

    max_workers = args.jobs or min(len(pares), os.cpu_count() or 4)
    print(f"[snapshot] {len(pares)} par(es) em ate {max_workers} processo(s)...", flush=True)

    # `as_completed`, nunca `pool.map`: os pares sao MUITO desiguais (um tick de
    # CSAN3 tem ordens de grandeza mais registros que um M1 de LPSB3) e `map` so'
    # entrega na ordem de submissao -- um par rapido ficaria preso atras de um
    # lento ja tendo terminado. `flush=True` porque stdout redirecionado a
    # arquivo e' bufferizado em bloco.
    concluidos = 0
    falhas = 0
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_snapshot_par, s, m, economics[s], str(out_dir), args.tail_ticks): (s, m)
            for s, m in pares
        }
        for future in as_completed(futures):
            concluidos += 1
            symbol, motor = futures[future]
            try:
                resumo = future.result()
            except Exception as exc:  # noqa: BLE001 -- um par que quebra nao derruba a rodada
                falhas += 1
                resumo = f"{symbol}/{motor}: FALHOU -- {type(exc).__name__}: {exc}"
            print(f"[snapshot] {concluidos}/{len(pares)}  {resumo}", flush=True)

    print(f"[snapshot] pronto em {out_dir}"
          + (f"  ({falhas} par(es) falharam)" if falhas else ""), flush=True)
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
