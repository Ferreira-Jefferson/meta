# -*- coding: utf-8 -*-
"""Frente D do pedido do dono: detectar `win_retangulo` em duas janelas W ao
mesmo tempo (W=20, producao, e W=30) e' amostra NOVA ou a MESMA operacao
contada duas vezes?

## Metodo

Roda os DOIS robos, cada um SOZINHO (motor nao piramida -- nao ha' como rodar
os dois DENTRO da mesma instancia disputando a mesma posicao), com a largura
minima PROPRIA de cada janela (328 pontos para W=20, ja' congelado; 401
pontos para W=30, o numero que a docstring do robo cita como "o terco
superior medido no W=30" -- mesmo metodo, janela diferente). Depois mede, por
TEMPO, quanto as operacoes de um se sobrepoem as do outro: dois trades
"colidem" se os intervalos `[entry_ts, exit_ts]` se cruzam.

Overlap ALTO => os dois detectores estao vendo o MESMO movimento de mercado
com janelas diferentes -- somar os `n` dos dois contaria a mesma oportunidade
duas vezes. Overlap BAIXO => sao oportunidades genuinamente distintas, e SE
o desenho permitisse rodar os dois ao mesmo tempo, isso seria amostra nova de
verdade (nao so' liquido novo).

## O obstaculo estrutural, independente do resultado do overlap

Mesmo com overlap baixo, "rodar os dois ao mesmo tempo" nao e' gratis: os
dois operam o MESMO simbolo (`WIN@`) numa conta MT5 NETTING, e a memoria do
projeto ja' registrou que dois robos no MESMO simbolo precisam de um GATE
para nao conflitar ordens (`netting_same_symbol_gate_confirmed_2026_08_25`).
"Multi-janela" aqui significaria DOIS slots de capital independentes com
esse gate ligado entre eles -- nao e' amplificacao gratuita de amostra, e'
uma decisao de alocar capital a um SEGUNDO robo. Este script mede se ha'
sinal genuino para justificar essa decisao; nao mede a operacao dos dois
gateados juntos (fora do escopo desta frente).

Capital: R$1.100 para as duas pernas nesta rodada -- serve so' para a tabela
padrao existir; a pergunta desta frente e' sobre SOBREPOSICAO DE TEMPO, nao
sobre P&L combinado (que exigiria escolher como dividir capital entre os
dois, decisao fora do escopo aqui).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_overlap_w20_w30_2026_09_15.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 1_100.0


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _roda(janela_barras, largura_minima, dias, rotulo):
    strat = WinRetangulo(
        janela_barras=janela_barras, largura_minima_pontos=largura_minima,
        alvo_fracao_largura=0.80, stop_fracao_largura=0.50,
        ttl_barras=10, quantidade=1, tolerancia_borda=0.20,
        risco_maximo_brl=80.0,
    )
    df = load_m1("WIN@").sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(strat.symbol)
    cfg = config_for(
        profile, trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01, initial_capital=CAPITAL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    linha = linha_de_resultado(rotulo, res, CAPITAL, extras={})
    return dict(rotulo=rotulo, trades=list(res.trades), linha=linha)


def _unidade(args):
    tag, dias = args
    r20 = _roda(20, 328.0, dias, f"W20 {tag}")
    r30 = _roda(30, 401.0, dias, f"W30 {tag}")
    return tag, r20, r30


def _sobrepoe(a, b) -> bool:
    return a.entry_ts <= b.exit_ts and b.entry_ts <= a.exit_ts


def _conta_overlap(trades_a, trades_b):
    if not trades_a or not trades_b:
        return 0, 0
    b_ordenado = sorted(trades_b, key=lambda t: t.entry_ts)
    n_a_com_overlap = 0
    for ta in trades_a:
        if any(_sobrepoe(ta, tb) for tb in b_ordenado):
            n_a_com_overlap += 1
    return n_a_com_overlap, len(trades_a)


def main():
    df = load_m1("WIN@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    print("=" * 130)
    print("win_retangulo -- SOBREPOSICAO de trades entre W=20 (producao) e W=30")
    print("=" * 130)
    print(f"  IS {len(IS)} pregoes | OOS {len(OOS)} pregoes | largura minima: W20=328pts, W30=401pts\n",
          flush=True)

    tarefas = [("IS", IS), ("OOS", OOS)]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t[0] for t in tarefas}
        for fut in as_completed(futs):
            tag, r20, r30 = fut.result()
            out[tag] = (r20, r30)
            print(f"  ok {tag}: W20 n={len(r20['trades'])} | W30 n={len(r30['trades'])}", flush=True)

    print("\n" + tabela([out[t][0]["linha"] for t, _d in tarefas] +
                         [out[t][1]["linha"] for t, _d in tarefas]))

    print("\n" + "=" * 130)
    print("SOBREPOSICAO DE TEMPO (intervalo [entry_ts, exit_ts] se cruza)")
    print("=" * 130)
    for tag, _d in tarefas:
        r20, r30 = out[tag]
        t20, t30 = r20["trades"], r30["trades"]
        n20_overlap, n20 = _conta_overlap(t20, t30)
        n30_overlap, n30 = _conta_overlap(t30, t20)
        # tempo em mercado de cada perna, e tempo em que as DUAS pernas
        # estavam simultaneamente com posicao aberta (uniao de intervalos
        # que se cruzam, aproximada por soma de intersecoes par-a-par --
        # ok para o proposito desta medicao, superposicoes triplas seriam
        # raras com um so' contrato por perna).
        print(f"  {tag}: W20 n={n20} ({n20_overlap} com overlap em algum trade W30, "
              f"{br(100*n20_overlap/n20,1) if n20 else '—'}%) | "
              f"W30 n={n30} ({n30_overlap} com overlap em algum trade W20, "
              f"{br(100*n30_overlap/n30,1) if n30 else '—'}%)")
        soma_ingenua = n20 + n30
        uniao_aprox = n20 + n30 - min(n20_overlap, n30_overlap)
        print(f"       soma ingenua (n20+n30) = {soma_ingenua} | "
              f"uniao aproximada (descontando overlap) ~= {uniao_aprox} | "
              f"ganho real de amostra ~= {br(100*(uniao_aprox-max(n20,n30))/max(n20,n30),1) if max(n20,n30) else '—'}% "
              f"sobre a MAIOR perna sozinha")

    print("\n" + "=" * 130)
    print("O QUE ISTO NAO RESPONDE")
    print("=" * 130)
    print("  * Overlap baixo NAO significa 'rode os dois e dobre o lucro': WIN@ e' um so'")
    print("    simbolo numa conta MT5 NETTING, e dois robos no MESMO simbolo precisam de gate")
    print("    para nao conflitar ordens (memoria do projeto, netting_same_symbol_gate). Rodar")
    print("    W20+W30 juntos exige DOIS slots de capital com esse gate ligado -- decisao de")
    print("    alocacao, nao amplificacao gratuita medida aqui.")
    print("  * W30 nao foi validado nas mesmas condicoes que W20 (tolerancia/alvo/stop vieram")
    print("    do W20 sem recalibrar) -- os `n` de W30 acima sao para medir SOBREPOSICAO, nao")
    print("    para promover W30 como geometria alternativa.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
