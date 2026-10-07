# -*- coding: utf-8 -*-
"""Geracao 20, PASSO 1 -- curva quantil x frequencia x concentracao x
qualidade, no IS (jan-jun/2026).

Mandato: redescobrir, dentro do IS, a curva variando
`quantil in {0,60; 0,65; 0,70; 0,75; 0,80}` -- mantendo janela_min=20,
direcao=continuacao, buffer=30 (ja estabelecidos nas geracoes anteriores) e
GEOMETRIA FIXA (alvo=4x/stop=150, a vencedora da G17) para isolar o efeito
do quantil sozinho antes de cruzar com alvo_multiplo (passo 2,
`g20_alvo_cruzamento.py`).

Para cada quantil: episodios BRUTOS (onsets do sinal, antes do filtro de
pernada/execucao), pregoes DISTINTOS com episodio, liquido, trades, win%, BE
empirico, IC95, concentracao top-3/top-5, p_ruina (Monte Carlo, caixa
R$1.000).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g20_quantil_freq/g20_quantil_curva.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g20_base as b  # noqa: E402

MAX_WORKERS = 4

KW_GEOMETRIA = dict(direcao_aposta=b.DIRECAO_APOSTA, stop_pontos=b.STOP_G17,
                     alvo_multiplo=b.ALVO_G17, buffer_entrada_pontos=b.BUFFER_ENTRADA)


def _worker(quantil: float, dias: list):
    ep = b.episodios_stats(dias, dias, b.JANELA_MIN, quantil)
    res, strat = b.roda(dias, dias_historico=dias, janela_min=b.JANELA_MIN,
                         quantil=quantil, capital=b.CAPITAL, **KW_GEOMETRIA)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), caixa=b.CAPITAL)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    be_nom = 1.0 / (1.0 + KW_GEOMETRIA["alvo_multiplo"])
    return dict(
        quantil=quantil, ep=ep, c=c, equity_min=equity_min,
        ordens_recusadas=res.ordens_recusadas_por_capital, ruina=ru, top5=top5,
        pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, be_nom=be_nom,
        bruto=strat.stats_bruto, emitidas=strat.stats_ordens_emitidas,
    )


def _censurado_capital(r: dict) -> bool:
    return bool(r["ordens_recusadas"] > 0) or r["equity_min"] < b.MARGEM_WIN_BRL


def _censurado_amostra(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"]


def _fmt_pct(v) -> str:
    return (b.br(100 * v, 1) + "%") if v == v else "--"


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 150)
    print("Geracao 20 PASSO 1 -- curva quantil x frequencia x concentracao, IS (jan-jun/2026)")
    print("=" * 150)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print(f"Geometria FIXA (vencedora da G17): alvo={b.ALVO_G17}x stop={b.STOP_G17:.0f}pts "
          f"buffer={b.BUFFER_ENTRADA:.0f}pts janela={b.JANELA_MIN}min direcao={b.DIRECAO_APOSTA}")
    print("Referencia G17 (q=0,75, mesma geometria): liquido=+R$1.698,50 trades=125 win=31,2% "
          "top3/liq=56% top5/liq=77% p_ruina=0,2%\n", flush=True)

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, q, dias): q for q in b.QUANTIS}
        resultados: dict[float, dict] = {}
        for fut in as_completed(futs):
            q = futs[fut]
            r = fut.result()
            resultados[q] = r
            c = r["c"]
            print(f"  q={q:.2f}  episodios_brutos={r['ep']['episodios_brutos']:>4}  "
                  f"pregoes_distintos={r['ep']['pregoes_distintos']:>3}/{r['ep']['pregoes_totais']}  "
                  f"liquido={b.br(c['liquido']):>11}  trades={c['n']:>4}  "
                  f"win={_fmt_pct(c['win']):>6}  BEemp={_fmt_pct(c['be']):>6}  "
                  f"veredito={c['veredito']:<10}  "
                  f"top3/liq={_fmt_pct(c['concentracao_top3']):>6}  top5/liq={_fmt_pct(r['top5']):>6}  "
                  f"p_ruina={_fmt_pct(r['ruina']['p_ruina']):>6}",
                  flush=True)

    print("\n" + "=" * 150)
    print("TABELA CONSOLIDADA -- curva quantil (geometria fixa alvo=4x/stop=150)")
    print("=" * 150)
    header = (f"{'quantil':>8} {'ep.brutos':>10} {'preg.dist':>10} {'liquido':>12} "
              f"{'trades':>7} {'win%':>7} {'BEemp%':>7} {'IC95 win':>16} {'veredito':>10} "
              f"{'top3/liq':>9} {'top5/liq':>9} {'p_ruina':>8} {'sem_tr':>8}")
    print(header)
    print("-" * len(header))
    for q in b.QUANTIS:
        r = resultados[q]
        c = r["c"]
        ic = f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"
        print(f"{q:>8.2f} {r['ep']['episodios_brutos']:>10} {r['ep']['pregoes_distintos']:>10} "
              f"{b.br(c['liquido']):>12} {c['n']:>7} {_fmt_pct(c['win']):>7} {_fmt_pct(c['be']):>7} "
              f"{ic:>16} {c['veredito']:>10} {_fmt_pct(c['concentracao_top3']):>9} "
              f"{_fmt_pct(r['top5']):>9} {_fmt_pct(r['ruina']['p_ruina']):>8} "
              f"{c['sem_trade']:>3}/{c['pregoes']:<4}")

    print("\nCensura (item 6.51): capital (ordens recusadas OU equity_min<margem crua) "
          "x amostra (0 trades OU >=50% pregoes sem trade).")
    for q in b.QUANTIS:
        r = resultados[q]
        print(f"  q={q:.2f}  cens_capital={_censurado_capital(r)}  cens_amostra={_censurado_amostra(r)}  "
              f"equity_min={b.br(r['equity_min'])}  emit/bruto_estrategia={r['emitidas']}/{r['bruto']}")

    # Ranking: melhor equilibrio = passa portao (liquido>0, nao censurado,
    # veredito!=NEGATIVO) E concentracao (top3) MENOR que a referencia G17
    # (56%), ordenado por menor top3/liq entre os que passam.
    candidatos = [q for q in b.QUANTIS
                  if resultados[q]["c"]["liquido"] > 0
                  and not _censurado_capital(resultados[q]) and not _censurado_amostra(resultados[q])
                  and resultados[q]["c"]["veredito"] != "NEGATIVO"]
    print(f"\nQuantis que batem o portao basico: {candidatos}")
    melhora_concentracao = [q for q in candidatos
                            if resultados[q]["c"]["concentracao_top3"] < 0.56]
    print(f"Destes, com top3/liq < 56% (referencia G17 q=0,75): {melhora_concentracao}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
