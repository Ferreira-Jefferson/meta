"""Passo 4 do redesenho de alvo por VOLATILIDADE (ver a docstring de
`strategy.daytrade.lab.gremah`/`JanelaVolatilidadeDiaria` e o plano do dono,
2026-08-23): varre `k` (Variante A -- so' o alvo vira `k x range_mediano`,
`stop_multiplier` continua POR SIMBOLO) e `k` x `s` (Variante B -- `k` e `s`
GLOBAIS, a tabela por simbolo deixa de valer inclusive para o stop) nos 10
simbolos calibrados, contra a calibracao ATUAL de producao (`Gremah(symbol=)`
sem parametro nenhum -- ja inclui o override de volatilidade dos 4 simbolos
confirmados) -- mesmo periodo, mesma config, por simbolo.

RECALIBRACAO 2026-08-23 (2a rodada, pedido do dono): a 1a medicao deste
sweep rodou com capital de teste FIXO em R$100 para todo simbolo -- inclusive
os caros, onde R$100 nao cobre nem 1 lote e o piso `max(1, lotes)` de
`_lotes_por_realocacao` mascarava esse fato (foi assim que a CLSC4 apareceu
com MaxDD de -244,7%, ver `engine.py::wiped_out_at`). Este sweep agora usa o
CAIXA MINIMO REAL de cada simbolo (`capital_minimo_brl` no preco do inicio da
janela) e `enforce_capital_minimo=True` (padrao de `config_for` desde
2026-08-23) -- o mesmo caixa que o robo teria de verdade, o que muda quantos
lotes cabem e portanto pode mudar qual (k,s) e melhor.

Motivado por `profit_pct` saturar no piso de 1 tick (`_ticks_from_pct`) em
9 dos 10 simbolos calibrados: o alvo bruto nunca passa de 1,07 tick fora da
CLSC4, entao o percentual configurado nao tem efeito pratico nenhum sobre
9 papeis -- so' sobrevive via os derivados (espacamento/stop, que escapam
do piso por multiplicarem antes de arredondar).

Roda em M1 (`load_m1`), nao em tick: so' a PMAM3 tem tick baixado, e a
medicao aqui precisa dos 10 simbolos calibrados.

So' IN-SAMPLE aqui -- a confirmacao OOS e' UMA passada so', depois, com o
par (`k` ou `k`+`s`) escolhido (ver `run_backtest.py --unlock-oos`).
CRITERIO DE ADOCAO do dono (2026-08-23, "nenhum papel pode piorar"): so' vale
adotar se TODOS os 10 simbolos ficarem iguais ou melhores que a linha
"atual" na confirmacao OOS -- este script so' informa o IS, nao decide.

Ressalva registrada de antemao no plano: por causa do piso de 1 tick, um `k`
pequeno o bastante pode produzir resultado BYTE-IDENTICO ao de hoje na
maioria dos papeis -- nao e' bug, e' o piso agindo igual nos dois caminhos
(percentual e volatilidade).

Uso:
    python scripts/daytrade/sweep_gremah_vol.py
    python scripts/daytrade/sweep_gremah_vol.py --symbol PMAM3
    python scripts/daytrade/sweep_gremah_vol.py --symbol PMAM3 --top 15
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES, config_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import capital_minimo_brl  # noqa: E402
from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL, Gremah  # noqa: E402

# Mesmo regime de preco de `sweep_gremah_tick.py`/`run_backtest_ticks.py` --
# e' propriedade do ATIVO (a partir de quando o preco de hoje deixou de ser
# outro patamar), nao da fonte de dado (M1 vs tick), entao a mesma data vale
# aqui.
REGIME_START = {
    "PMAM3": "2025-12-16", "KLBN4": "2025-09-02", "CSAN3": "2025-09-22",
    "DASA3": "2025-09-11", "PCAR3": "2025-08-21", "CLSC4": "2025-05-12",
    "KLBN3": "2025-03-10", "GRND3": "2025-09-05", "LPSB3": "2022-12-20",
    "BMGB4": "2025-06-04",
}

K_GRID = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
S_GRID = [5.0, 8.0, 10.0, 15.0, 20.0, 30.0]  # so' Variante B
VOL_JANELA_DIAS_PADRAO = 10
MIN_TRADES_CONFIAVEL = 30


#: Coluna EXTRA desta varredura -- entra DEPOIS das 12 da base
#: (`backtest/intraday/report.py`), nunca no lugar de nenhuma delas.
EXTRAS = ("confiavel",)


def _rodar(profile, run_bars: pd.DataFrame, econ, strat: Gremah, preco_atual: float,
           label: str = ""):
    """Devolve a linha da TABELA PADRAO -- ate 2026-08-25 este script montava
    a propria tabela, e comparar duas varreduras virava trabalho de leitura."""
    capital_inicial = capital_minimo_brl(preco_atual)
    config = config_for(
        profile, trade_tick_value=econ.trade_tick_value, trade_tick_size=econ.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker, preco_atual=preco_atual,
    )
    result = run_intraday_backtest(run_bars, strat, config)
    n = len(result.trades)
    return linha_de_resultado(
        label, result, capital_inicial,
        extras={"confiavel": "sim" if n >= MIN_TRADES_CONFIAVEL
                else f"NAO<{MIN_TRADES_CONFIAVEL}"},
    )


def _sweep_symbol(symbol: str, top: int) -> None:
    profile = PROFILES[symbol]
    bars = load_m1(symbol)
    if bars.empty:
        print(f"[sweep_vol] sem dado local para {symbol!r} — rode backfill_m1.py primeiro")
        return
    regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
    bars = bars.loc[bars.index >= regime_start]

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    run_bars = LockedBars(bars, split).in_sample()

    econ = symbol_economics(symbol)
    if econ is None:
        print("[sweep_vol] nao consegui ler symbol_economics — terminal MT5 aberto?")
        return

    # Mesmo preco de referencia (inicio da janela IS) para TODA variante --
    # e' o que faz o caixa minimo real ser o MESMO para o "atual" e para
    # cada candidato, condicao para a comparacao ser honesta.
    preco_atual = float(run_bars.iloc[0]["close"])

    calib = _CALIBRATION_BY_SYMBOL[symbol]
    print(f"\n=== {symbol} — IN-SAMPLE: {len(run_bars)} barras, "
          f"{run_bars.index.min()} -> {run_bars.index.max()}, "
          f"caixa minimo R${capital_minimo_brl(preco_atual):.2f} ===")

    linhas = []
    baseline = Gremah(symbol=symbol)
    rotulo_atual = (
        f"atual (k={baseline.alvo_vol_mult:.2f}/s={baseline.stop_vol_mult:.0f})"
        if baseline.alvo_por_volatilidade
        else f"atual ({calib.profit_pct*100:.2f}%/{calib.stop_multiplier:.0f}x)"
    )
    linhas.append(_rodar(profile, run_bars, econ, baseline, preco_atual, rotulo_atual))

    for k in K_GRID:
        strat_a = Gremah(symbol=symbol, alvo_por_volatilidade=True,
                          alvo_vol_mult=k, vol_janela_dias=VOL_JANELA_DIAS_PADRAO)
        linhas.append(_rodar(profile, run_bars, econ, strat_a, preco_atual, f"A k={k:.2f}"))

    for k in K_GRID:
        for s in S_GRID:
            strat_b = Gremah(symbol=symbol, alvo_por_volatilidade=True,
                              alvo_vol_mult=k, vol_janela_dias=VOL_JANELA_DIAS_PADRAO,
                              stop_vol_mult=s)
            linhas.append(_rodar(profile, run_bars, econ, strat_b, preco_atual,
                                 f"B k={k:.2f} s={s:.0f}"))

    # A linha "atual" fica SEMPRE visivel, mesmo fora do top-N, para servir
    # de referencia direta a cada variante ordenada por capital final.
    atual = linhas[0]
    resto = sorted(linhas[1:], key=lambda item: item.liquido_brl, reverse=True)

    print(cabecalho(EXTRAS))
    print(linha(atual, EXTRAS), flush=True)
    for item in resto[:top]:
        print(linha(item, EXTRAS), flush=True)
    if len(resto) > top:
        print(f"  ... {len(resto) - top} combinacao(oes) a mais, fora do top-{top}")


def _sweep_symbol_capturado(symbol: str, top: int) -> str:
    """Mesmo `_sweep_symbol`, so' que devolve o texto em vez de imprimir --
    cada SIMBOLO roda num PROCESSO separado (`ProcessPoolExecutor` em
    `main`, abaixo): os 43 backtests de um simbolo sao independentes dos de
    outro (cada um le seu proprio trecho de `bars`, nenhum estado
    compartilhado), entao paralelizar por simbolo usa os nucleos disponiveis
    sem qualquer coordenacao entre processos. Capturar o `print` e devolver
    como string (em vez de deixar cada processo escrever direto no stdout
    compartilhado) evita que a saida de dois simbolos se intercale no
    terminal."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _sweep_symbol(symbol, top)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=sorted(_CALIBRATION_BY_SYMBOL), default=None,
                        help="default: todos os 10 simbolos calibrados")
    parser.add_argument("--top", type=int, default=10,
                        help="quantas combinacoes mostrar por simbolo, alem da linha 'atual' (default 10)")
    parser.add_argument("--jobs", type=int, default=None,
                        help="processos em paralelo (default: min(simbolos, nucleos disponiveis))")
    args = parser.parse_args()
    symbols = [args.symbol] if args.symbol else sorted(_CALIBRATION_BY_SYMBOL)

    if len(symbols) == 1:
        # 1 simbolo so' -- nada pra paralelizar entre simbolos, e' o proprio
        # processo atual que roda os 43 backtests em sequencia.
        _sweep_symbol(symbols[0], args.top)
        return

    max_workers = args.jobs or min(len(symbols), os.cpu_count() or 4)
    print(f"[sweep_vol] {len(symbols)} simbolo(s) em ate {max_workers} processo(s) paralelo(s)...",
          flush=True)
    # `pool.submit`+`as_completed` (NAO `pool.map`) -- `map` so' entrega na
    # ORDEM DE SUBMISSAO, entao um simbolo rapido preso atras de um lento
    # nao aparece ate' o lento terminar; combinado com `flush=True` em todo
    # print, o arquivo de saida cresce de verdade a cada simbolo pronto, em
    # vez de tudo aparecer de uma vez no fim (ou nao aparecer, se o processo
    # for morto antes -- ver a memoria `feedback_parallelize_sweeps`, achado
    # medindo `sweep_gremah_tick.py` com simbolos de custo muito desigual).
    concluidos = 0
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_sweep_symbol_capturado, s, args.top): s for s in symbols}
        for future in as_completed(futures):
            concluidos += 1
            symbol = futures[future]
            print(future.result(), end="", flush=True)
            print(f"[sweep_vol] {concluidos}/{len(symbols)} concluido(s) ({symbol})", flush=True)


if __name__ == "__main__":
    main()
