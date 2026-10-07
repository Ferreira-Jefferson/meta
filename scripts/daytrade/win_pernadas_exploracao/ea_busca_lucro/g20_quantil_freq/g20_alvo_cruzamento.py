# -*- coding: utf-8 -*-
"""Geracao 20, PASSO 2 -- cruzamento quantil x alvo_multiplo, no IS
(jan-jun/2026).

Mandato: cruzar com `alvo_multiplo in {2, 2.5, 3, 4, 5}` nos quantis mais
promissores do PASSO 1 (`g20_quantil_curva.py`). Resultado do passo 1: dos 4
quantis que batem o portao basico (0,60/0,65/0,70/0,75), so' **q=0,60** tem
concentracao (top3/liq=47,9%) MENOR que a referencia G17 (q=0,75,
top3/liq=56,3%) -- os outros (0,65/0,70) na verdade PIORAM a concentracao
(58,9%/61,2%) alem de tambem nao serem POSITIVO. q=0,80 colapsa (poucos
episodios concentram ainda mais, 163%/221%). Por isso o cruzamento roda em
**3 quantis**: 0,60 (melhor concentracao), 0,70 (ponto medio da curva) e
0,75 (referencia/unico POSITIVO do passo 1) -- cobre as duas pontas e o
meio da curva sem repetir celulas redundantes (0,65 fica muito perto de
0,70 no padrao observado).

Stop fixo em 150pts (vencedor da G17/G4), buffer=30, janela=20min,
direcao=continuacao -- so' alvo_multiplo e quantil variam.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g20_quantil_freq/g20_alvo_cruzamento.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g20_base as b  # noqa: E402

MAX_WORKERS = 4

QUANTIS_CRUZAMENTO = (0.60, 0.70, 0.75)
ALVOS = (2.0, 2.5, 3.0, 4.0, 5.0)
STOP = b.STOP_G17  # 150pts, fixo (vencedor herdado)

GRADE = [
    (q, alvo, dict(direcao_aposta=b.DIRECAO_APOSTA, stop_pontos=STOP, alvo_multiplo=alvo,
                   buffer_entrada_pontos=b.BUFFER_ENTRADA))
    for q in QUANTIS_CRUZAMENTO
    for alvo in ALVOS
]


def _worker(quantil: float, alvo: float, kw: dict, dias: list):
    res, strat = b.roda(dias, dias_historico=dias, janela_min=b.JANELA_MIN,
                         quantil=quantil, capital=b.CAPITAL, **kw)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), caixa=b.CAPITAL)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    be_nom = 1.0 / (1.0 + alvo)
    return dict(
        quantil=quantil, alvo=alvo, kw=kw, c=c, equity_min=equity_min,
        ordens_recusadas=res.ordens_recusadas_por_capital, ruina=ru, top5=top5,
        pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, be_nom=be_nom,
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
    print("Geracao 20 PASSO 2 -- cruzamento quantil x alvo_multiplo, IS (jan-jun/2026)")
    print("=" * 150)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print(f"quantis testados: {QUANTIS_CRUZAMENTO}  alvos: {ALVOS}  "
          f"stop={STOP:.0f}pts (fixo)  buffer={b.BUFFER_ENTRADA:.0f}pts  "
          f"janela={b.JANELA_MIN}min  direcao={b.DIRECAO_APOSTA}\n", flush=True)

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, q, alvo, dict(kw), dias): (q, alvo) for q, alvo, kw in GRADE}
        resultados: dict[tuple, dict] = {}
        for fut in as_completed(futs):
            key = futs[fut]
            r = fut.result()
            resultados[key] = r
            c = r["c"]
            print(f"  q={key[0]:.2f} alvo={key[1]:.1f}x  liquido={b.br(c['liquido']):>11}  "
                  f"trades={c['n']:>4}  win={_fmt_pct(c['win']):>6}  BEemp={_fmt_pct(c['be']):>6}  "
                  f"veredito={c['veredito']:<10}  top3/liq={_fmt_pct(c['concentracao_top3']):>6}  "
                  f"top5/liq={_fmt_pct(r['top5']):>6}  p_ruina={_fmt_pct(r['ruina']['p_ruina']):>6}",
                  flush=True)

    print("\n" + "=" * 150)
    print("TABELA CONSOLIDADA -- quantil x alvo_multiplo (stop=150pts fixo)")
    print("=" * 150)
    header = (f"{'q x alvo':>14} {'liquido':>12} {'trades':>7} {'win%':>7} {'BEemp%':>7} "
              f"{'IC95 win':>16} {'veredito':>10} {'top3/liq':>9} {'top5/liq':>9} {'p_ruina':>8} {'sem_tr':>8}")
    print(header)
    print("-" * len(header))
    for q, alvo, kw in GRADE:
        r = resultados[(q, alvo)]
        c = r["c"]
        ic = f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"
        rotulo = f"q={q:.2f}/{alvo:.1f}x"
        print(f"{rotulo:>14} {b.br(c['liquido']):>12} {c['n']:>7} {_fmt_pct(c['win']):>7} "
              f"{_fmt_pct(c['be']):>7} {ic:>16} {c['veredito']:>10} "
              f"{_fmt_pct(c['concentracao_top3']):>9} {_fmt_pct(r['top5']):>9} "
              f"{_fmt_pct(r['ruina']['p_ruina']):>8} {c['sem_trade']:>3}/{c['pregoes']:<4}")

    # Criterio composto desta geracao (mandato, item 4): liquido>0, nao
    # censurado, win%/IC95 POSITIVO, p_ruina baixa, E concentracao MENOR que
    # a referencia G17 (top3/liq<56,3%, top5/liq<77,0% no IS).
    candidatos = []
    for q, alvo, kw in GRADE:
        r = resultados[(q, alvo)]
        c = r["c"]
        if (c["liquido"] > 0 and not _censurado_capital(r) and not _censurado_amostra(r)
                and c["veredito"] == "POSITIVO"
                and r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] and r["ruina"]["p_ruina"] <= 0.20
                and c["concentracao_top3"] < 0.563 and r["top5"] < 0.770):
            candidatos.append((q, alvo, r))

    print(f"\nCelulas que batem o CRITERIO COMPOSTO desta geracao (POSITIVO + p_ruina<=20% + "
          f"concentracao < referencia G17 56,3%/77,0%): {len(candidatos)}/{len(GRADE)}")
    for q, alvo, r in sorted(candidatos, key=lambda x: x[2]["c"]["concentracao_top3"]):
        c = r["c"]
        print(f"  q={q:.2f} alvo={alvo:.1f}x  liquido={b.br(c['liquido'])}  win={_fmt_pct(c['win'])}  "
              f"top3/liq={_fmt_pct(c['concentracao_top3'])}  top5/liq={_fmt_pct(r['top5'])}  "
              f"p_ruina={_fmt_pct(r['ruina']['p_ruina'])}")

    if candidatos:
        q, alvo, r = sorted(candidatos, key=lambda x: x[2]["c"]["concentracao_top3"])[0]
        print(f"\nVENCEDOR candidato a promocao: q={q:.2f} alvo={alvo:.1f}x stop={STOP:.0f}pts")
    else:
        print("\nNENHUMA celula bate o criterio composto -- ver tabelas acima para o padrao de falha.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
