# -*- coding: utf-8 -*-
"""Geracao 18 (`WinBuscaLucroG18OrbCapital1000`) -- BUSCA no IS (jan-jun/2026).

MUDANCA DE MANDATO (dono, 2026-10-05, mesma porta da G17): capital de TESTE
R$1.000 (nao R$250) + `alvo_multiplo` em GRADE {2,0x; 2,5x; 3,0x; 4,0x; 5,0x}
(piso nunca <=1x). `stop_max_pontos` varre 6 valores ao redor da regiao
interessante que G8/G13 ja mapearam a R$250 (100-250): {100,120,140,160,200,250}.
Grade 2D completa: 5 x 6 = 30 celulas, `range_minutos=5min` e
`buffer_entrada_pontos=20` FIXOS (mesmo precedente de G8 -- eixo ja
estabelecido, nao revisitado aqui).

Pergunta central desta geracao (ver docstring do modulo da estrategia): o
penhasco de ruina que G8/G13 mediram a R$250 (stop_max=140/alvo=3x isolado,
TODO vizinho colapsando em censura total de capital) sobrevive ao caixa 4x
maior? E a concentracao do ORB (gatilho no maximo 1x/pregao por construcao)
e' estruturalmente menor que a do sinal cruzado WIN x WDO que a G17 mediu
(383% no OOS-1)?

Criterio de PROMOCAO/vencedor: COMPOSTO, mesma disciplina de G8/G13/G17 --
liquido>0 E nao censurado POR CAPITAL (item 6.51 -- `seletividade_amostra`
sozinha NAO reprova) E win% != NEGATIVO E p_ruina (MC, R$1.000->R$100,
horizonte=44 pregoes) <= 20%.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g18_orb_capital1000/g18_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g18_base as b  # noqa: E402

MAX_WORKERS = 4
LIMIAR_RUINA = 0.20
HORIZONTE_PREGOES = 44  # tamanho do OOS-1

ALVO_GRID = (2.0, 2.5, 3.0, 4.0, 5.0)
STOP_MAX_GRID = (100.0, 120.0, 140.0, 160.0, 200.0, 250.0)


def _worker(rotulo: str, kwargs_estrategia: dict, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda(dias, **kwargs_estrategia)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    censura = b.censura_separada(res, c)
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias),
                                  horizonte_pregoes=HORIZONTE_PREGOES)
    const = b.constancia_motor(trades)
    sizing = b.sizing_motor(trades)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    be_nom = 1.0 / (1.0 + kwargs_estrategia["alvo_multiplo"])
    extras = {
        "alvo": f"{kwargs_estrategia['alvo_multiplo']:g}x",
        "stop_max": f"{kwargs_estrategia['stop_max_pontos']:g}",
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "pregoes c/trade": f"{c['com_trade']}/{c['pregoes']}",
        "p_ruina(MC)": (b.br(100 * ruina["p_ruina"], 1) + "%") if ruina["p_ruina"] == ruina["p_ruina"] else "--",
        "pior_seq_perdas": f"{pior_seq_n} (R${b.br(pior_seq_brl)})",
        "cens_capital": str(censura["censura_capital"]),
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    stop_dist = sorted(c["stop_dist_pts"])
    return dict(
        rotulo=rotulo, kwargs=kwargs_estrategia, c=c, top5=top5, linha=linha_res,
        censura=censura, bruto=strat.stats_bruto, ja_operou=strat.stats_ja_operou_hoje,
        emitidas=strat.stats_ordens_emitidas, ruina=ruina, const=const, sizing=sizing,
        pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl,
        stop_dist_mediana=(stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")),
    )


def _censurado(r: dict) -> bool:
    """Item 6.51 -- so' o ramo de CAPITAL reprova (mesma disciplina de G13).
    `seletividade_amostra` fica informativo na tabela, nunca reprova
    sozinha."""
    return r["c"]["n"] == 0 or r["censura"]["censura_capital"]


def _bate_composto(r: dict) -> bool:
    c = r["c"]
    liquido_ok = c["liquido"] > 0
    censura_ok = not _censurado(r)
    win_ok = c["veredito"] != "NEGATIVO"
    ruina_ok = r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] and r["ruina"]["p_ruina"] <= LIMIAR_RUINA
    return liquido_ok and censura_ok and win_ok and ruina_ok


def _imprime_linha(rot: str, r: dict) -> None:
    c = r["c"]
    ru = r["ruina"]
    print(f"  {rot:<26} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"stop_med={b.br(r['stop_dist_mediana'],0):>5}pt  "
          f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"cens_cap={r['censura']['censura_capital']}  "
          f"composto={_bate_composto(r)}", flush=True)


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 170)
    print("WinBuscaLucroG18OrbCapital1000 -- GRADE 2D no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 170)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("NO MAXIMO 1 operacao real por pregao (sem fade). 1 contrato FIXO (G19 escala).")
    print(f"GRADE: alvo_multiplo x {ALVO_GRID}  x  stop_max_pontos x {STOP_MAX_GRID}  = "
          f"{len(ALVO_GRID)*len(STOP_MAX_GRID)} celulas")
    print(f"CRITERIO COMPOSTO: liquido>0 E nao censurado POR CAPITAL (item 6.51) E win% != NEGATIVO E "
          f"p_ruina(MC, R${b.br(b.CAPITAL,0)}->R$100, horizonte={HORIZONTE_PREGOES} pregoes) <= {LIMIAR_RUINA*100:.0f}%.\n",
          flush=True)

    variantes = []
    for am in ALVO_GRID:
        for sm in STOP_MAX_GRID:
            rot = f"a={am:g}x/sm={sm:g}"
            kw = dict(range_minutos=5.0, stop_min_pontos=50.0, buffer_entrada_pontos=20.0,
                       alvo_multiplo=am, stop_max_pontos=sm)
            variantes.append((rot, kw))

    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, kw, dias): rot for rot, kw in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            _imprime_linha(rot, r)

    # -- tabela consolidada, ordenada por (alvo, stop_max) para leitura de curva --
    ordenado = [resultados[f"a={am:g}x/sm={sm:g}"] for am in ALVO_GRID for sm in STOP_MAX_GRID]
    EXTRAS = ("alvo", "stop_max", "BEnom%", "BEemp%", "IC95 win", "veredito",
              "top3/liq", "top5/liq", "pregoes c/trade", "p_ruina(MC)",
              "pior_seq_perdas", "cens_capital")
    print("\n" + "=" * 170)
    print(f"TABELA CONSOLIDADA -- grade completa, {len(variantes)} celulas (ordenada por alvo, depois stop_max)")
    print("=" * 170)
    print(tabela([r["linha"] for r in ordenado], extras=EXTRAS, largura_extra=11))

    print("\nSIZING (motor.tamanho/p_encolhido) -- Kelly fracionario a R$1.000 pede mais de 1 contrato em algum ponto?")
    for r in ordenado:
        s = r["sizing"]
        print(f"  {r['rotulo']:<22} p_encolhido={b.br(100*s.get('p_encolhido',float('nan')),1)}%  "
              f"contratos_kelly={s.get('contratos_kelly','--')}")

    # -- leitura por EIXO (curva, nao so' vencedor) -----------------------------
    print("\n" + "=" * 170)
    print("CORTES por eixo (leitura de platô x penhasco)")
    print("=" * 170)
    for am in ALVO_GRID:
        print(f"\n-- CORTE alvo={am:g}x, variando stop_max --")
        for sm in STOP_MAX_GRID:
            r = resultados[f"a={am:g}x/sm={sm:g}"]
            c = r["c"]
            ru = r["ruina"]
            print(f"    stop_max={sm:>5g}  liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
                  f"cens_cap={r['censura']['censura_capital']}  composto={_bate_composto(r)}")

    for sm in STOP_MAX_GRID:
        print(f"\n-- CORTE stop_max={sm:g}, variando alvo --")
        for am in ALVO_GRID:
            r = resultados[f"a={am:g}x/sm={sm:g}"]
            c = r["c"]
            ru = r["ruina"]
            print(f"    alvo={am:>5g}x  liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
                  f"cens_cap={r['censura']['censura_capital']}  composto={_bate_composto(r)}")

    # -- vencedor composto: menor ruina entre quem bate o criterio; fallback
    #    declarado em niveis, mesma disciplina de G8/G13 -----------------------
    def chave(r):
        pr = r["ruina"]["p_ruina"]
        pr = pr if pr == pr else 1.0
        return (pr, -r["c"]["liquido"])

    compostos = {k: v for k, v in resultados.items() if _bate_composto(v)}
    if compostos:
        nivel = "COMPOSTO (liquido>0 E nao censurado por capital E veredito!=NEGATIVO E p_ruina<=20%)"
        vencedor = min(compostos.values(), key=chave)
    else:
        nao_censurados = {k: v for k, v in resultados.items() if not _censurado(v)}
        if nao_censurados:
            nivel = "FALLBACK 1 (nenhuma bate composto -- menor ruina entre nao-censuradas por capital)"
            vencedor = min(nao_censurados.values(), key=chave)
        else:
            nivel = "FALLBACK 2 (TODAS censuradas por capital -- maior liquido mesmo assim, degenerado)"
            vencedor = max(resultados.values(), key=lambda r: r["c"]["liquido"])

    print("\n" + "=" * 170)
    print(f"VENCEDOR ({nivel}):", vencedor["rotulo"], vencedor["kwargs"])
    print("=" * 170)
    c = vencedor["c"]
    ru = vencedor["ruina"]
    const = vencedor["const"]
    print(f"liquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  veredito={c['veredito']}  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  pregoes_c_trade={c['com_trade']}/{c['pregoes']}")
    print(f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liq={b.br(100*vencedor['top5'],0) if vencedor['top5']==vencedor['top5'] else '--'}%  "
          f"stop_mediano={b.br(vencedor['stop_dist_mediana'],0)}pts  "
          f"censura_capital={vencedor['censura']['censura_capital']}  "
          f"seletividade_amostra={vencedor['censura']['seletividade_amostra']}")
    print(f"p_ruina(MC, {ru['n_ops']} ops, R${b.br(b.CAPITAL,0)}->R$100)={b.br(100*ru['p_ruina'],1)}%  "
          f"ruina_formula(Lundberg)={b.br(100*ru['ruina_formula'],1)}%  "
          f"pior_seq_perdas={vencedor['pior_seq_n']} (R${b.br(vencedor['pior_seq_brl'])})")
    print(f"\nCRITERIO COMPOSTO bate? {_bate_composto(vencedor)}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
