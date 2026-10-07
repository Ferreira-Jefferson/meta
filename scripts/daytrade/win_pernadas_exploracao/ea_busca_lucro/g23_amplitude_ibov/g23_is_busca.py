# -*- coding: utf-8 -*-
"""Busca no IS (jan-jun/2026) da Geracao 23 -- `WinBuscaLucroG23AmplitudeIbov`.

Parametros FIXADOS pelo passo de validacao causal (`g23_validacao_causal.py`,
ver `g23_validacao_causal_stdout.log`): `janela_min=5` (folego de 5 minutos)
e `nascente_pontos=375` deram a separacao MAIS limpa entre tercis de
concordancia -- tercil baixo/diverge 31,3% IC95[28,4%;34,3%] contra
tercil alto/confirma 38,5% IC95[35,1%;42,0%] de taxa de "chegou a 750" --
as DUAS pontas do IC95 NAO se sobrepoem, o par mais significativo das 4
combinacoes testadas. A direcao que o dado sustenta e' CONFIRMACAO (folego
concordando com a pernada nascente prediz MAIS confirmacao, nao menos, em
TODAS as 4 combinacoes testadas -- nunca o padrao oposto), entao so' essa
leitura vira estrategia aqui (a "divergencia" nao tem nenhum sinal a favor
em nenhuma combinacao -- nao faz sentido gastar celula de grade nela).

`limiar_concordancia=0,5` -- arredondado a partir do corte do tercil alto
medido (~0,625 na mesma combinacao, mas o VALOR exato do quantil IS nao vira
parametro ajustado a` dedo: 0,5 e' uma fracao redonda, mais frouxa que o
tercil (deixa passar mais eventos), declarada aqui, nao re-otimizada depois
do IS. `stop_pontos = nascente_pontos = 375` (a mesma distancia que define o
nascimento da perna -- escolha DECLARADA: a aposta e' exatamente que a
pernada nascente CONTINUA, entao o stop natural e' "ela reverteu a mesma
distancia que a fez nascer").

Grade 1D do mandato: `alvo_multiplo` em {2x, 2,5x, 3x, 4x, 5x} (piso do
mandato 2026-10-05, nunca <=1x -- imposto no construtor da classe).

Capital de teste R$1.000,00, 1 contrato fixo. Fila WIN@ zero (nao calibrada,
premissa otimista declarada).

Criterio composto para "bate o criterio" (promove a OOS-1), mesmo molde de
G16/G20/G21: liquido>0 E NAO censurado POR CAPITAL (item 6.51) E veredito do
win% != NEGATIVO E p_ruina(MC, R$1.000->R$100, horizonte=44 operacoes
projetadas) <= 25%.

ProcessPoolExecutor, max 4 workers, submit/as_completed (nunca pool.map),
cada celula imprime a propria linha assim que termina.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g23_amplitude_ibov/g23_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

JANELA_MIN = 5
NASCENTE_PONTOS = 375.0
LIMIAR_CONCORDANCIA = 0.5
ALVO_MULTIPLOS = [2.0, 2.5, 3.0, 4.0, 5.0]


def _roda_celula(alvo_multiplo: float) -> dict:
    import g23_base as b

    dias_is = b.dias_da_janela(b.carrega_win(), b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    res, strat = b.roda(
        dias_is, janela_min=JANELA_MIN,
        direcao_aposta="confirmacao", nascente_pontos=NASCENTE_PONTOS,
        stop_pontos=NASCENTE_PONTOS, alvo_multiplo=alvo_multiplo,
        limiar_concordancia=LIMIAR_CONCORDANCIA,
    )
    trades = list(res.trades)
    c = b.consistencia(trades, dias_is)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_is))
    top3 = c["concentracao_top3"]
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    stop_pts = sorted(c["stop_dist_pts"])
    stop_mediano = stop_pts[len(stop_pts) // 2] if stop_pts else float("nan")
    bate = (
        c["n"] > 0 and c["liquido"] > 0 and not cs["censura_capital"]
        and c["veredito"] != "NEGATIVO"
        and ru["p_ruina"] == ru["p_ruina"] and ru["p_ruina"] <= 0.25
    )
    return dict(
        alvo_multiplo=alvo_multiplo,
        liquido=c["liquido"], n=c["n"], win=c["win"], be=c["be"], veredito=c["veredito"],
        lo=c["lo"], hi=c["hi"], sem_trade=c["sem_trade"], pregoes=c["pregoes"],
        top3=top3, top5=top5,
        pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl,
        p_ruina=ru["p_ruina"], equity_min=cs["equity_min"],
        recusadas_capital=cs["ordens_recusadas_por_capital"],
        censura_capital=cs["censura_capital"], seletividade_amostra=cs["seletividade_amostra"],
        stop_mediano=stop_mediano, bate_criterio=bate,
        stats_bruto=strat.stats_bruto,
        stats_sem_confirmacao_externa=strat.stats_sem_confirmacao_externa,
        stats_ordens_emitidas=strat.stats_ordens_emitidas,
    )


def _formata(r: dict) -> str:
    import g23_base as b
    win_pct = f"{100*r['win']:.1f}" if r['win'] == r['win'] else "--"
    be_pct = f"{100*r['be']:.1f}" if r['be'] == r['be'] else "--"
    p_ruina_pct = f"{100*r['p_ruina']:.1f}" if r['p_ruina'] == r['p_ruina'] else "--"
    top3_pct = f"{100*r['top3']:.0f}" if r['top3'] == r['top3'] else "--"
    top5_pct = f"{100*r['top5']:.0f}" if r['top5'] == r['top5'] else "--"
    return (
        f"  alvo_mult={r['alvo_multiplo']:.1f}x  liquido={b.br(r['liquido']):>11}  "
        f"n={r['n']:>4}  win={win_pct:>5}%  BEemp={be_pct:>5}%  "
        f"veredito={r['veredito']:<10}  p_ruina={p_ruina_pct:>5}%  "
        f"top3={top3_pct:>5}%  top5={top5_pct:>5}%  "
        f"pior_seq={r['pior_seq_n']:>2}(R${b.br(r['pior_seq_brl'])})  "
        f"stop_med={r['stop_mediano']:.0f}pts  sem_trade={r['sem_trade']}/{r['pregoes']}  "
        f"cens_capital={r['censura_capital']}  BATE={r['bate_criterio']}\n"
        f"      bruto={r['stats_bruto']}  sem_confirmacao_externa="
        f"{r['stats_sem_confirmacao_externa']}  ordens_emitidas={r['stats_ordens_emitidas']}"
    )


def main() -> None:
    print(f"Geracao 23 -- busca IS (jan-jun/2026, 122 pregoes, capital R$1.000, "
          f"1 contrato fixo). janela_min={JANELA_MIN} nascente_pontos={NASCENTE_PONTOS:.0f} "
          f"limiar_concordancia={LIMIAR_CONCORDANCIA}. {len(ALVO_MULTIPLOS)} celulas.\n",
          flush=True)

    resultados = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_roda_celula, m): m for m in ALVO_MULTIPLOS}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print(_formata(r), flush=True)

    vencedores = [r for r in resultados if r["bate_criterio"]]
    print(f"\n{len(vencedores)} de {len(resultados)} celulas batem o criterio composto.")
    if vencedores:
        vencedores.sort(key=lambda r: r["p_ruina"])
        print("\nMelhores por p_ruina (ascendente):")
        for r in vencedores:
            print(_formata(r))

    print("\n--- Tabela completa, ordenada por alvo_multiplo ---")
    resultados.sort(key=lambda r: r["alvo_multiplo"])
    for r in resultados:
        print(_formata(r))


if __name__ == "__main__":
    main()
