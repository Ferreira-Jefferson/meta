# -*- coding: utf-8 -*-
"""IS (jan-jun/2026, 122 pregoes) da Geracao 26 -- filtro de tendencia sobre
a geometria vencedora da G21. Grade DECLARADA antes de rodar (nao escolhida
depois de ver o numero): 4 janelas de `drift_bars` (60/120/240/480 barras
M1 = 1h/2h/4h/8h) + `drift_dia` (desde a abertura da sessao), cada uma em
modo frouxo (`estrito=False`, neutro passa) e estrito (`estrito=True`,
neutro bloqueia tambem) -- 10 celulas. Compara contra a linha de base SEM
filtro (a propria G21, ja medida em `g21_is_busca_stdout.log`: liquido
R$2.790,00, n=562, win 37,9%, BEemp 33,8%, top3/liq=41%, top5/liq=64%).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g26_filtro_tendencia/g26_is_busca.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g26_base as b  # noqa: E402

JANELAS = [60, 120, 240, 480]


def avalia(dias_is, **kwargs) -> dict:
    res, _ = b.roda(dias_is, **kwargs)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_is)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_is))
    return dict(c=c, top5=top5, pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, ru=ru)


def imprime(nome: str, r: dict) -> None:
    c = r["c"]
    print(f"{nome:28s} liquido={b.br(c['liquido']):>10s}  n={c['n']:4d}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>5s}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>5s}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  "
          f"veredito={c['veredito']:10s}  "
          f"top3/liq={b.br(100*c['concentracao_top3'],1) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5s}%  "
          f"top5/liq={b.br(100*r['top5'],1) if r['top5']==r['top5'] else '--':>5s}%  "
          f"p_ruina={b.br(100*r['ru']['p_ruina'],1) if r['ru']['p_ruina']==r['ru']['p_ruina'] else '--'}%",
          flush=True)


def main() -> None:
    win = b.carrega_win()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"IS (jan-jun/2026, {len(dias_is)} pregoes) -- geometria herdada da G21 "
          f"(stop={b.STOP_FRACAO}, alvo={b.ALVO_FRACAO})\n", flush=True)

    base = avalia(dias_is, medida="drift_bars", janela_tendencia=240, estrito=False)
    # SEM FILTRO (referencia G21, recalculada aqui so' para bater digito a
    # digito com g21_is_busca_stdout.log antes de comparar filtros -- usa
    # a classe G26 com janela curta e estrito=False degenera para "deixa
    # tudo passar"? NAO: precisa de um modo explicito "sem filtro". Roda a
    # propria G21 direto para a referencia exata.
    sys.path.insert(0, str(Path(__file__).parent.parent / "g21_retangulo_1000"))
    import g21_base as g21b  # noqa: E402
    res_g21, _ = g21b.roda(dias_is, congelado=False,
                            stop_fracao_largura=b.STOP_FRACAO, alvo_fracao_largura=b.ALVO_FRACAO)
    c_g21 = b.consistencia(list(res_g21.trades), dias_is)
    top5_g21 = b.concentracao_topn(c_g21["serie"], 5)
    print(f"{'SEM FILTRO (G21, referencia)':28s} liquido={b.br(c_g21['liquido']):>10s}  "
          f"n={c_g21['n']:4d}  win={b.br(100*c_g21['win'],1):>5s}%  "
          f"BEemp={b.br(100*c_g21['be'],1):>5s}%  veredito={c_g21['veredito']:10s}  "
          f"top3/liq={b.br(100*c_g21['concentracao_top3'],1):>5s}%  "
          f"top5/liq={b.br(100*top5_g21,1):>5s}%\n", flush=True)

    resultados = {}
    for estrito in (False, True):
        for w in JANELAS:
            nome = f"drift_bars W={w} {'estrito' if estrito else 'frouxo'}"
            r = avalia(dias_is, medida="drift_bars", janela_tendencia=w, estrito=estrito)
            imprime(nome, r)
            resultados[nome] = r
        nome = f"drift_dia {'estrito' if estrito else 'frouxo'}"
        r = avalia(dias_is, medida="drift_dia", janela_tendencia=240, estrito=estrito)
        imprime(nome, r)
        resultados[nome] = r

    print("\n-- resumo: celulas com win% acima do BE empirico E top3/liq melhor que o G21 --")
    for nome, r in resultados.items():
        c = r["c"]
        if c["n"] >= 30 and c["win"] == c["win"] and c["be"] == c["be"] and c["win"] > c["be"] \
                and c["concentracao_top3"] == c["concentracao_top3"] \
                and c["concentracao_top3"] < c_g21["concentracao_top3"]:
            print(f"  {nome}: win {b.br(100*c['win'],1)}% > BE {b.br(100*c['be'],1)}%, "
                  f"top3/liq {b.br(100*c['concentracao_top3'],1)}% < {b.br(100*c_g21['concentracao_top3'],1)}% (G21), n={c['n']}")


if __name__ == "__main__":
    main()
