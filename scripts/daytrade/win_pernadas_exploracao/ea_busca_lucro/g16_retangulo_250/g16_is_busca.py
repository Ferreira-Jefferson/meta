# -*- coding: utf-8 -*-
"""Busca no IS (jan-jun/2026) da Geracao 16 -- `WinBuscaLucroG16Retangulo250`.

Grade 2D: `stop_fracao_largura` (stop TECNICO, aquem da borda oposta, em vez
do stop original de `WinRetangulo` que vai ate' ela) x `alvo_multiplo`
(alvo = alvo_multiplo x stop -- SEMPRE >=3, imposto no construtor da classe).
`janela_barras=20`, `tolerancia_borda=0,20`, `largura_minima_pontos=328`
herdados do `WinRetangulo` CONGELADO, nao retunados (esta geracao testa
geometria de entrada/saida, nao deteccao de forma).

Capital real R$250,00, 1 contrato fixo. Fila WIN@ zero (nao calibrada,
premissa otimista declarada). Criterio composto (declarado ANTES de rodar
qualquer celula, mesmo molde de G8/G13/G15): liquido>0 E NAO censurado POR
CAPITAL (item 6.51 -- `censura_capital`, nao so' `sem_trade`) E veredito do
win% != NEGATIVO E p_ruina(MC, R$250->R$100, horizonte=44 operacoes
projetadas) <= 25% (mesmo limiar revisado de G8/G13).

ProcessPoolExecutor, max 4 workers, submit/as_completed (nunca pool.map),
cada celula imprime a propria linha assim que termina.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g16_retangulo_250/g16_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

STOP_FRACOES = [0.15, 0.20, 0.25, 0.30, 0.375, 0.50]
ALVO_MULTIPLOS = [3.0, 4.0, 5.0]


def _roda_celula(stop_fracao: float, alvo_multiplo: float) -> dict:
    import g16_base as b

    dias_is = b.dias_da_janela(b.carrega_win(), b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    alvo_fracao = stop_fracao * alvo_multiplo
    res, strat = b.roda(dias_is, stop_fracao_largura=stop_fracao,
                         alvo_fracao_largura=alvo_fracao)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_is)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_is))
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    # Distancia REAL do stop -- so' das saidas que de fato bateram o stop
    # (mesma convencao de `g05_base.consistencia`, campo `stop_dist_pts`).
    stop_pts = sorted(c["stop_dist_pts"])
    stop_mediano = stop_pts[len(stop_pts) // 2] if stop_pts else float("nan")
    bate = (
        c["n"] > 0 and c["liquido"] > 0 and not cs["censura_capital"]
        and c["veredito"] != "NEGATIVO"
        and ru["p_ruina"] == ru["p_ruina"] and ru["p_ruina"] <= 0.25
    )
    return dict(
        stop_fracao=stop_fracao, alvo_multiplo=alvo_multiplo, alvo_fracao=alvo_fracao,
        liquido=c["liquido"], n=c["n"], win=c["win"], be=c["be"], veredito=c["veredito"],
        lo=c["lo"], hi=c["hi"], sem_trade=c["sem_trade"], pregoes=c["pregoes"],
        top3=c["concentracao_top3"], top5=top5,
        pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl,
        p_ruina=ru["p_ruina"], equity_min=cs["equity_min"],
        recusadas_capital=cs["ordens_recusadas_por_capital"],
        censura_capital=cs["censura_capital"], seletividade_amostra=cs["seletividade_amostra"],
        stop_mediano=stop_mediano, bate_criterio=bate,
    )


def _formata(r: dict) -> str:
    import g16_base as b
    win_pct = f"{100*r['win']:.1f}" if r['win'] == r['win'] else "--"
    be_pct = f"{100*r['be']:.1f}" if r['be'] == r['be'] else "--"
    p_ruina_pct = f"{100*r['p_ruina']:.1f}" if r['p_ruina'] == r['p_ruina'] else "--"
    top3_pct = f"{100*r['top3']:.0f}" if r['top3'] == r['top3'] else "--"
    return (
        f"  stop={r['stop_fracao']:.3f}xL mult={r['alvo_multiplo']:.0f}x "
        f"alvo={r['alvo_fracao']:.3f}xL  liquido={b.br(r['liquido']):>11}  "
        f"n={r['n']:>4}  win={win_pct:>5}%  BEemp={be_pct:>5}%  "
        f"veredito={r['veredito']:<10}  p_ruina={p_ruina_pct:>5}%  "
        f"top3={top3_pct:>4}%  pior_seq={r['pior_seq_n']:>2}(R${b.br(r['pior_seq_brl'])})  "
        f"stop_med={r['stop_mediano']:.0f}pts  sem_trade={r['sem_trade']}/{r['pregoes']}  "
        f"cens_capital={r['censura_capital']}  BATE={r['bate_criterio']}"
    )


def main() -> None:
    celulas = [(s, m) for s in STOP_FRACOES for m in ALVO_MULTIPLOS]
    print(f"Geracao 16 -- busca IS (jan-jun/2026, 122 pregoes, capital R$250, "
          f"1 contrato fixo). {len(celulas)} celulas.\n", flush=True)

    resultados = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_roda_celula, s, m): (s, m) for s, m in celulas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print(_formata(r), flush=True)

    vencedores = [r for r in resultados if r["bate_criterio"]]
    print(f"\n{len(vencedores)} de {len(resultados)} celulas batem o criterio composto.")
    if vencedores:
        vencedores.sort(key=lambda r: r["p_ruina"])
        print("\nMelhores por p_ruina (ascendente):")
        for r in vencedores[:5]:
            print(_formata(r))


if __name__ == "__main__":
    main()
