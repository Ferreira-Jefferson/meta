"""GREMAH em veiculos de BTC/ETH da B3 (2026-08-27): a familia nao tem
calibracao para nenhum simbolo de cripto (nao esta em `_CALIBRATION_BY_SYMBOL`)
-- este e' o passo 3/4 do protocolo padrao ("Um simbolo novo exige os MESMOS 4
passos antes de entrar aqui", ver `strategy.daytrade.lab.gremah`): varredura
fina de geometria em TICKS (alvo=espacamento x stop), IN-SAMPLE apenas, para
cada simbolo candidato de `cripto_comum.CRIPTO`.

Por que geometria em TICKS e nao percentual: o proprio preco dos veiculos
(R$9 a R$93) faz 1 tick (R$0,01) valer de 0,01% a 0,11% do preco -- 3 a 30x
mais fino que o mesmo tick nas acoes calibradas da familia (R$0,14 a R$4,53,
onde 1 tick ja' vale 0,2%-7%). Testar com o `profit_pct` percentual herdado
faria o mesmo bug que motivou a tabela em ticks originalmente
(`_ticks_from_pct` satura no piso de 1 tick) -- so' que ao contrario: aqui o
alvo percentual old (0,21%-0,42%) vira MUITOS ticks, nao 1, e o comportamento
seria outra coisa nao testada. Ticks inteiros deixam a busca comparavel entre
simbolos de preco muito diferente.

Filtros de qualidade de entrada (`filtro_minutos_desde_abertura_min`/
`filtro_volume_toque_max`, default global 216min/3200) e a capacidade de
caixa (`capacidade_negocio_mult`/`capacidade_fracao`) foram calibrados nas 10
ACOES da familia -- transplantar um numero calibrado para outro instrumento
sem medir e' o erro ja documentado em `gremah_universo_138_ativos_refutado`
(24% zeram a conta). Por isso os DOIS filtros de entrada saem DESLIGADOS
(`None`) nesta rodada -- e' o comportamento mais NEUTRO disponivel -- e a
capacidade usa o PADRAO global da classe (`CAPACIDADE_NEGOCIO_MULT_PADRAO`/
`CAPACIDADE_FRACAO_PADRAO` = 1,0/10%), nunca um numero calibrado emprestado de
uma acao especifica.

Uso:
    python scripts/daytrade/cripto_grid_2026_08_27.py --symbol QBTC11
    python scripts/daytrade/cripto_grid_2026_08_27.py --all --jobs 8
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cripto_comum import CRIPTO, SHARES_PER_LOT, carregar_is, carregar_oos  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import (  # noqa: E402
    CAPACIDADE_FRACAO_PADRAO,
    CAPACIDADE_NEGOCIO_MULT_PADRAO,
    Gremah,
)

#: Grade em ticks inteiros -- Fibonacci, nao uniforme: cobre 1 tick (o piso
#: que ganha em quase toda a familia) ate' 89 ticks (R$0,89) sem gastar 484
#: celulas como a grade densa das acoes (essas ja tem preco parecido entre
#: si; aqui o range de preco e' 10x maior e uma grade uniforme fina
#: desperdicaria celulas nas pontas). Estendida ate' 89/377 (2a rodada, apos
#: uma sondagem manual em ETHY11 mostrar que o resultado so' piora menos --
#: nunca vira positivo -- e platoo entre T34 e T89, sem achar um pico novo
#: mais adiante).
ALVO_TICKS = (1, 2, 3, 5, 8, 13, 21, 34)
STOP_TICKS = (2, 3, 5, 8, 13, 21, 34, 55, 89, 144)

OOS_MOTIVO = (
    "confirmacao UNICA do melhor candidato IS por simbolo cripto, mesmo "
    "protocolo de `alvo_stop_grid_2026_08_27.py`/`confirm_oos_ticks.py` -- "
    "a varredura fina so' olhou o trecho IS."
)

# Preenchidos pelo `_init_worker` -- 1x por PROCESSO, nunca por celula.
_SYMBOL = None
_JANELA = None
_ECON = None


def _init_worker(symbol: str) -> None:
    global _SYMBOL, _JANELA, _ECON
    import MetaTrader5 as mt5

    _SYMBOL = symbol
    _JANELA = carregar_is(symbol)
    mt5.initialize()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info(None) para {symbol!r} -- terminal MT5 aberto?")
    _ECON = (float(info.trade_tick_value), float(info.trade_tick_size))


def _strat(alvo: int, stop: int) -> Gremah:
    return Gremah(
        symbol=_SYMBOL,
        # placeholders sem efeito: `profit_ticks`/`stop_ticks` explicitos
        # sobrescrevem por ultimo em `_session_ticks` -- so' precisam ser
        # nao-None para pular o lookup em `_CALIBRATION_BY_SYMBOL` (que nao
        # tem, e nao deveria ter, nenhum simbolo de cripto).
        profit_pct=1.0, stop_multiplier=1.0,
        profit_ticks=alvo, spacing_ticks=alvo, stop_ticks=stop,
        shares_per_lot=SHARES_PER_LOT,
        capacidade_negocio_mult=CAPACIDADE_NEGOCIO_MULT_PADRAO,
        capacidade_fracao=CAPACIDADE_FRACAO_PADRAO,
        filtro_minutos_desde_abertura_min=None,
        filtro_volume_toque_max=None,
    )


def _rodar(strat: Gremah, bars, label: str, preco_ref: float):
    config = config_for(
        _JANELA.profile, trade_tick_value=_ECON[0], trade_tick_size=_ECON[1],
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_ref,
    )
    result = run_intraday_backtest(bars, strat, config)
    return linha_de_resultado(label, result, capital_minimo_brl(preco_ref, SHARES_PER_LOT))


def _celula(alvo: int, stop: int):
    strat = _strat(alvo, stop)
    label = f"T{alvo} E{alvo} S{stop}"
    return (alvo, stop, _rodar(strat, _JANELA.bars, label, _JANELA.preco_ref))


def _rodar_symbol(symbol: str, jobs: int, out_dir: Path) -> dict:
    print(f"\n=== {symbol} ({CRIPTO[symbol]}) — IN-SAMPLE, {jobs} processo(s) ===", flush=True)
    pares = [(a, s) for a in ALVO_TICKS for s in STOP_TICKS]
    t0 = time.time()
    linhas = []
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker,
                              initargs=(symbol,)) as pool:
        futures = {pool.submit(_celula, a, s): (a, s) for a, s in pares}
        print(cabecalho(), flush=True)
        feitos = 0
        for fut in as_completed(futures):
            try:
                alvo, stop, item = fut.result()
            except Exception as exc:
                a, s = futures[fut]
                print(f"[erro] {symbol} T{a}E{a}S{s}: {exc}", flush=True)
                continue
            feitos += 1
            print(linha(item), flush=True)
            linhas.append((alvo, stop, item))
    dt = time.time() - t0
    if not linhas:
        print(f"[{symbol}] nenhuma celula rodou (sem dado local?) -- {dt:.0f}s", flush=True)
        return {"symbol": symbol, "erro": "sem dado"}

    linhas.sort(key=lambda t: t[2].capital_final, reverse=True)
    melhor_alvo, melhor_stop, melhor = linhas[0]
    print(f"[{symbol}] {len(linhas)} celulas em {dt:.0f}s. Melhor IS: "
          f"T{melhor_alvo}E{melhor_alvo}S{melhor_stop} -> capital final R$ "
          f"{num_br(melhor.capital_final,2)} (liquido R$ {num_br(melhor.liquido_brl,2)}, "
          f"lucro/DD {num_br(melhor.lucro_por_dd,2)})", flush=True)

    out = {
        "symbol": symbol,
        "is_top5": [
            {"alvo": a, "stop": s, "capital_final": item.capital_final,
             "liquido_brl": item.liquido_brl, "lucro_por_dd": item.lucro_por_dd,
             "trades": item.trades, "win_rate_pct": item.win_rate_pct}
            for a, s, item in linhas[:5]
        ],
        "melhor_is": {"alvo": melhor_alvo, "stop": melhor_stop,
                      "liquido_brl": melhor.liquido_brl, "capital_final": melhor.capital_final},
    }

    if melhor.liquido_brl <= 0:
        print(f"[{symbol}] melhor celula IS ja' e' NEGATIVA (R$ {num_br(melhor.liquido_brl,2)}) "
              "-- sem candidato para confirmar no OOS, pulando (mesma regra de "
              "'positivo no IS e negativo no OOS = descartado': nem chega a IS positivo).",
              flush=True)
        out["oos"] = None
        return out

    # Confirmacao UNICA no OOS, so' da celula vencedora.
    janela_oos = carregar_oos(symbol, OOS_MOTIVO)
    if janela_oos.bars.empty:
        print(f"[{symbol}] sem barras no trecho OOS -- confirmacao pulada.", flush=True)
        out["oos"] = None
        return out
    import MetaTrader5 as mt5
    mt5.initialize()
    info = mt5.symbol_info(symbol)
    global _JANELA, _ECON, _SYMBOL
    _SYMBOL, _JANELA, _ECON = symbol, janela_oos, (float(info.trade_tick_value), float(info.trade_tick_size))
    strat = _strat(melhor_alvo, melhor_stop)
    item_oos = _rodar(strat, janela_oos.bars, f"OOS T{melhor_alvo}E{melhor_alvo}S{melhor_stop}",
                       janela_oos.preco_ref)
    print(f"[{symbol}] OOS: {linha(item_oos)}", flush=True)
    veredito = "POSITIVO" if item_oos.liquido_brl > 0 else "NEGATIVO (descartado)"
    print(f"[{symbol}] veredito OOS: {veredito}", flush=True)
    out["oos"] = {
        "liquido_brl": item_oos.liquido_brl, "capital_final": item_oos.capital_final,
        "lucro_por_dd": item_oos.lucro_por_dd, "trades": item_oos.trades,
        "win_rate_pct": item_oos.win_rate_pct, "veredito": veredito,
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol", choices=sorted(CRIPTO))
    group.add_argument("--all", action="store_true")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--out", default=str(ROOT / "scripts" / "daytrade" /
                                              "cripto_grid_2026_08_27_result.json"))
    args = parser.parse_args()

    symbols = sorted(CRIPTO) if args.all else [args.symbol]
    out_path = Path(args.out)
    resultados = []
    if out_path.exists():
        try:
            resultados = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            resultados = []
    ja_feitos = {r["symbol"] for r in resultados}

    for symbol in symbols:
        if symbol in ja_feitos:
            print(f"[skip] {symbol} ja' tem resultado salvo em {out_path.name}", flush=True)
            continue
        r = _rodar_symbol(symbol, args.jobs, out_path.parent)
        resultados.append(r)
        out_path.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[salvo] {out_path}", flush=True)

    print("\n=== RESUMO ===", flush=True)
    for r in resultados:
        if "erro" in r:
            print(f"{r['symbol']:<8} {r['erro']}")
            continue
        m = r["melhor_is"]
        oos = r.get("oos")
        oos_txt = (f"OOS R$ {num_br(oos['liquido_brl'],2)} ({oos['veredito']})"
                   if oos else "sem OOS")
        print(f"{r['symbol']:<8} IS T{m['alvo']}E{m['alvo']}S{m['stop']} -> "
              f"R$ {num_br(m['liquido_brl'],2)}  |  {oos_txt}")


if __name__ == "__main__":
    main()
