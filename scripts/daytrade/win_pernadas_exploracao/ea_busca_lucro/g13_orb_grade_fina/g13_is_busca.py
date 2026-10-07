# -*- coding: utf-8 -*-
"""Geracao 13 (`WinBuscaLucroG13OrbGradeFina`) -- BUSCA no IS (jan-jun/2026).

Mandato do coordenador: grade MULTIDIMENSIONAL (nao mais 1 eixo como a G8) --
multiplo do alvo x definicao do stop x limiar de confirmacao do rompimento --
para checar se existe um PLATO robusto (varias celulas vizinhas concordando),
nao so' um pico isolado cercado de piora abrupta (padrao ja' visto em G8/G9).

Estagios:
  A (principal, 3D) -- stop_family="tecnico" FIXO (familia vencedora da G8),
      stop_max_pontos in {100,120,140,160,180} (ao redor da regiao
      interessante da G8: 140 sobrevive, 150/160 colapsam) x
      alvo_multiplo in {3,4,5} x confirma_pontos in {0,10,20,30,50}.
      5 x 3 x 5 = 75 celulas.
  B (ATR-M15, vizinhanca do vencedor de A) -- atr_multiplo in {1.0,1.5,2.0},
      alvo_multiplo/confirma_pontos fixados no vencedor composto de A.
      3 celulas.
  C (fixo em pontos, vizinhanca do vencedor de A) -- stop_fixo_pontos in
      {100,120,140,160} (faixa que G7/G8 ja' mostraram segura, >=100 por
      construcao -- item 6.47), alvo_multiplo/confirma_pontos fixados no
      vencedor composto de A. 4 celulas.

Criterio de PROMOCAO/vencedor: COMPOSTO -- liquido>0 E NAO censurado por
CAPITAL (item 6.51 -- equity_min>=margem crua E ordens_recusadas_por_capital
=0; fracao alta de pregoes sem trade por SELETIVIDADE de confirma_pontos alto
NAO reprova sozinha) E win% != NEGATIVO E p_ruina(MC, 44 operacoes projetadas,
R$250->R$100) <= 25% (mesmo limiar revisado da G8, declarado ANTES de rodar
qualquer celula desta geracao, pela mesma razao: nenhuma geometria desta
familia bateu 20% na G8, e a vizinhanca imediata do unico ponto que bate ~25%
e' degenerada).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g13_orb_grade_fina/g13_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g13_base as b  # noqa: E402

MAX_WORKERS = 4
LIMIAR_RUINA = 0.25
HORIZONTE_PREGOES = 44  # tamanho do OOS-1 -- a pergunta de ruina e' sobre ESSE horizonte

STOP_MAX_GRID = (100.0, 120.0, 140.0, 160.0, 180.0)
ALVO_GRID = (3.0, 4.0, 5.0)
CONFIRMA_GRID = (0.0, 10.0, 20.0, 30.0, 50.0)
ATR_K_GRID = (1.0, 1.5, 2.0)
STOP_FIXO_GRID = (100.0, 120.0, 140.0, 160.0)


def _worker(rotulo: str, kwargs_estrategia: dict, dias: list, atr_serie_completa: dict | None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda(dias, atr_serie_completa=atr_serie_completa, **kwargs_estrategia)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    censura = b.censura_separada(res, c)
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias),
                                  horizonte_pregoes=HORIZONTE_PREGOES)
    const = b.constancia_motor(trades)
    sizing = b.sizing_motor(trades)
    be_nom = 1.0 / (1.0 + kwargs_estrategia["alvo_multiplo"])
    extras = {
        "familia": kwargs_estrategia["stop_family"],
        "confirma_pt": f"{kwargs_estrategia.get('confirma_pontos', 0.0):g}",
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "pregoes c/trade": f"{c['com_trade']}/{c['pregoes']}",
        "p_ruina(MC)": (b.br(100 * ruina["p_ruina"], 1) + "%") if ruina["p_ruina"] == ruina["p_ruina"] else "--",
        "pior_seq_perdas": str(const.get("pior_seq_ops", 0)),
        "censura_capital": str(censura["censura_capital"]),
        "seletiv_amostra": str(censura["seletividade_amostra"]),
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    stop_dist = sorted(c["stop_dist_pts"])
    return dict(
        rotulo=rotulo, kwargs=kwargs_estrategia, c=c, top5=top5, linha=linha_res,
        censura=censura, bruto=strat.stats_bruto, ja_operou=strat.stats_ja_operou_hoje,
        emitidas=strat.stats_ordens_emitidas,
        sem_atr=getattr(strat, "stats_sem_atr_disponivel", 0),
        ruina=ruina, const=const, sizing=sizing,
        stop_dist_mediana=(stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")),
    )


def _bate_composto(r: dict) -> bool:
    """Criterio COMPOSTO desta geracao -- censura so' pelo ramo de CAPITAL
    (item 6.51), nao pela fracao de pregoes sem trade (que e' esperada e
    cresce por DESENHO quando `confirma_pontos` sobe)."""
    c = r["c"]
    liquido_ok = c["liquido"] > 0
    censura_ok = not r["censura"]["censura_capital"]
    win_ok = c["veredito"] != "NEGATIVO"
    ruina_ok = r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] and r["ruina"]["p_ruina"] <= LIMIAR_RUINA
    return liquido_ok and censura_ok and win_ok and ruina_ok


def _imprime_linha(rot: str, r: dict) -> None:
    c = r["c"]
    ru = r["ruina"]
    cz = r["censura"]
    print(f"  {rot:<32} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"stop_med={b.br(r['stop_dist_mediana'],0):>5}pt  "
          f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"cap_cens={cz['censura_capital']!s:<5}  "
          f"composto={_bate_composto(r)}", flush=True)


def _roda_estagio(nome: str, variantes: list[tuple[str, dict]], dias: list,
                   atr_serie_completa: dict | None = None) -> dict[str, dict]:
    print(f"\n--- ESTAGIO {nome} ({len(variantes)} celulas) ---", flush=True)
    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, kw, dias, atr_serie_completa): rot for rot, kw in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            _imprime_linha(rot, r)
    return resultados


def _vencedor_composto(resultados: dict[str, dict]) -> dict:
    """Vencedor desta geracao, TRES niveis de fallback (mesma disciplina de
    G7/G8 -- declarados, nunca escondidos):

    1. Dentre quem bate o criterio composto inteiro, o de MENOR p_ruina
       (desempate: maior liquido).
    2. Se ninguem bate mas existe celula sem censura de CAPITAL, o de menor
       ruina entre essas.
    3. So' se TODAS tiverem censura de capital, o de maior liquido mesmo
       assim (degenerado, declarado como tal)."""
    def chave(r):
        pr = r["ruina"]["p_ruina"]
        pr = pr if pr == pr else 1.0
        return (pr, -r["c"]["liquido"])

    compostos = {k: v for k, v in resultados.items() if _bate_composto(v)}
    if compostos:
        return min(compostos.values(), key=chave)
    sem_censura_capital = {k: v for k, v in resultados.items() if not v["censura"]["censura_capital"]}
    if sem_censura_capital:
        return min(sem_censura_capital.values(), key=chave)
    return max(resultados.values(), key=lambda r: r["c"]["liquido"])


def _imprime_curva_por_eixo(resultados: dict[str, dict]) -> None:
    """Leitura de PLATO -- para cada eixo, imprime a matriz liquido/p_ruina
    fixando os outros dois no valor do vencedor composto (ou no mais comum),
    para o eixo em si ficar visivel sem rolar a tabela inteira."""
    venc = _vencedor_composto(resultados)
    alvo_v = venc["kwargs"]["alvo_multiplo"]
    conf_v = venc["kwargs"].get("confirma_pontos", 0.0)
    sm_v = venc["kwargs"].get("stop_max_pontos")

    def fatia(fixar: dict, variar_chave: str, grid):
        linhas = []
        for rot, r in resultados.items():
            kw = r["kwargs"]
            if kw.get("stop_family") != "tecnico":
                continue
            if all(kw.get(k) == v for k, v in fixar.items()):
                linhas.append((kw.get(variar_chave), r))
        linhas.sort(key=lambda t: t[0])
        return linhas

    print(f"\n  CORTE 1 -- variando stop_max_pontos (alvo={alvo_v:g}x, confirma={conf_v:g}pt fixos):")
    for sm, r in fatia({"alvo_multiplo": alvo_v, "confirma_pontos": conf_v}, "stop_max_pontos", STOP_MAX_GRID):
        c = r["c"]
        print(f"    stop_max={sm:>5g}  liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
              f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  p_ruina={b.br(100*r['ruina']['p_ruina'],1) if r['ruina']['p_ruina']==r['ruina']['p_ruina'] else '--':>5}%  "
              f"cap_cens={r['censura']['censura_capital']}")

    print(f"\n  CORTE 2 -- variando alvo_multiplo (stop_max={sm_v:g}, confirma={conf_v:g}pt fixos):")
    for am, r in fatia({"stop_max_pontos": sm_v, "confirma_pontos": conf_v}, "alvo_multiplo", ALVO_GRID):
        c = r["c"]
        print(f"    alvo={am:>3g}x  liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
              f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  p_ruina={b.br(100*r['ruina']['p_ruina'],1) if r['ruina']['p_ruina']==r['ruina']['p_ruina'] else '--':>5}%  "
              f"cap_cens={r['censura']['censura_capital']}")

    print(f"\n  CORTE 3 -- variando confirma_pontos (stop_max={sm_v:g}, alvo={alvo_v:g}x fixos):")
    for cp, r in fatia({"stop_max_pontos": sm_v, "alvo_multiplo": alvo_v}, "confirma_pontos", CONFIRMA_GRID):
        c = r["c"]
        print(f"    confirma={cp:>4g}pt  liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
              f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  p_ruina={b.br(100*r['ruina']['p_ruina'],1) if r['ruina']['p_ruina']==r['ruina']['p_ruina'] else '--':>5}%  "
              f"cap_cens={r['censura']['censura_capital']}  seletiv={r['censura']['seletividade_amostra']}")


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 170)
    print("WinBuscaLucroG13OrbGradeFina -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 170)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("NO MAXIMO 1 operacao real por pregao (sem fade); alvo sempre >= 3x o stop.")
    print(f"CRITERIO COMPOSTO: liquido>0 E nao censurado POR CAPITAL (item 6.51) E "
          f"win% != NEGATIVO E p_ruina(MC, R$250->R$100, horizonte={HORIZONTE_PREGOES} pregoes) <= {LIMIAR_RUINA*100:.0f}%.\n",
          flush=True)

    todas_linhas: list[dict] = []
    todos_resultados: dict[str, dict] = {}

    # -- ESTAGIO A: grade 3D tecnico (stop_max x alvo x confirma) ------------
    variantes_a = []
    for sm in STOP_MAX_GRID:
        for am in ALVO_GRID:
            for cp in CONFIRMA_GRID:
                rot = f"A tec sm={sm:g} alvo={am:g}x conf={cp:g}"
                kw = dict(range_minutos=5.0, stop_family="tecnico", stop_min_pontos=50.0,
                          stop_max_pontos=sm, alvo_multiplo=am, confirma_pontos=cp,
                          buffer_entrada_pontos=20.0)
                variantes_a.append((rot, kw))
    res_a = _roda_estagio("A -- tecnico: stop_max x alvo_multiplo x confirma_pontos", variantes_a, dias)
    todas_linhas += list(res_a.values())
    todos_resultados.update(res_a)
    venc_a = _vencedor_composto(res_a)
    print(f"\n  >> vencedor composto A: {venc_a['kwargs']} "
          f"(liquido={b.br(venc_a['c']['liquido'])}, p_ruina={b.br(100*venc_a['ruina']['p_ruina'],1)}%, "
          f"bate_composto={_bate_composto(venc_a)})")

    print("\n" + "=" * 170)
    print("LEITURA DE PLATO -- cortes do Estagio A ao redor do vencedor composto")
    print("=" * 170)
    _imprime_curva_por_eixo(res_a)

    sm_venc = venc_a["kwargs"]["stop_max_pontos"]
    alvo_venc = venc_a["kwargs"]["alvo_multiplo"]
    conf_venc = venc_a["kwargs"]["confirma_pontos"]

    # -- ESTAGIO B: ATR-M15 na vizinhanca do vencedor de A -------------------
    print("\n--- precomputando ATR14-M15 causal sobre o IS (uma vez) ---", flush=True)
    atr_serie = b.computa_atr_serie(b.bars_dos_dias(win, dias))
    variantes_b = [
        (f"B atr k={k:g} (alvo={alvo_venc:g}x conf={conf_venc:g})",
         dict(range_minutos=5.0, stop_family="atr", stop_min_pontos=50.0,
              atr_multiplo=k, alvo_multiplo=alvo_venc, confirma_pontos=conf_venc,
              buffer_entrada_pontos=20.0))
        for k in ATR_K_GRID
    ]
    res_b = _roda_estagio(f"B -- ATR-M15 (vizinhanca do vencedor A: alvo={alvo_venc:g}x, confirma={conf_venc:g}pt)",
                           variantes_b, dias, atr_serie_completa=atr_serie)
    todas_linhas += list(res_b.values())
    todos_resultados.update(res_b)

    # -- ESTAGIO C: stop fixo na vizinhanca do vencedor de A -----------------
    variantes_c = [
        (f"C fixo sf={sf:g} (alvo={alvo_venc:g}x conf={conf_venc:g})",
         dict(range_minutos=5.0, stop_family="fixo", stop_min_pontos=50.0,
              stop_fixo_pontos=sf, alvo_multiplo=alvo_venc, confirma_pontos=conf_venc,
              buffer_entrada_pontos=20.0))
        for sf in STOP_FIXO_GRID
    ]
    res_c = _roda_estagio(f"C -- stop FIXO (vizinhanca do vencedor A: alvo={alvo_venc:g}x, confirma={conf_venc:g}pt)",
                           variantes_c, dias)
    todas_linhas += list(res_c.values())
    todos_resultados.update(res_c)

    # -- tabela consolidada ----------------------------------------------------
    EXTRAS = ("familia", "confirma_pt", "BEnom%", "BEemp%", "IC95 win", "veredito",
              "top3/liq", "top5/liq", "pregoes c/trade", "p_ruina(MC)", "pior_seq_perdas",
              "censura_capital", "seletiv_amostra")
    print("\n" + "=" * 170)
    print(f"TABELA CONSOLIDADA -- 3 estagios, {len(todas_linhas)} celulas")
    print("=" * 170)
    print(tabela([r["linha"] for r in todas_linhas], extras=EXTRAS, largura_extra=11))

    print("\nSTOP MEDIANO (pts) por variante (item 6.47 -- flag se < 100):")
    for r in todas_linhas:
        flag = " <<< FLAG 6.47 (precisa checagem com ticks)" if r["stop_dist_mediana"] == r["stop_dist_mediana"] and r["stop_dist_mediana"] < 100 else ""
        print(f"  {r['rotulo']:<42} stop_mediano={b.br(r['stop_dist_mediana'],0)}  "
              f"ruina_formula(Lundberg)={b.br(100*r['ruina']['ruina_formula'],1) if r['ruina']['ruina_formula']==r['ruina']['ruina_formula'] else '--'}%  "
              f"n_ops_simulados={r['ruina']['n_ops']}{flag}")

    print("\nSIZING (motor.tamanho/p_encolhido) -- Kelly fracionario a R$250 sugere quantos contratos?")
    for r in todas_linhas:
        s = r["sizing"]
        print(f"  {r['rotulo']:<42} p_encolhido={b.br(100*s.get('p_encolhido',float('nan')),1)}%  "
              f"contratos_kelly={s.get('contratos_kelly','--')}")

    # -- vencedor final: composto sobre A UNIAO de todas as celulas testadas --
    vencedor_final = _vencedor_composto(todos_resultados)
    print("\n" + "=" * 170)
    print("VENCEDOR FINAL (criterio COMPOSTO, uniao A+B+C):", vencedor_final["rotulo"], vencedor_final["kwargs"])
    print("=" * 170)
    c = vencedor_final["c"]
    ru = vencedor_final["ruina"]
    const = vencedor_final["const"]
    cz = vencedor_final["censura"]
    print(f"liquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1)}%  "
          f"BEemp={b.br(100*c['be'],1)}%  veredito={c['veredito']}  IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  "
          f"pregoes_c_trade={c['com_trade']}/{c['pregoes']}")
    print(f"top3/liq={b.br(100*c['concentracao_top3'],0)}%  top5/liq={b.br(100*vencedor_final['top5'],0)}%  "
          f"stop_mediano={b.br(vencedor_final['stop_dist_mediana'],0)}pts  "
          f"censura_capital={cz['censura_capital']}  seletividade_amostra={cz['seletividade_amostra']}  "
          f"equity_min={b.br(cz['equity_min'])}  ordens_recusadas_por_capital={cz['ordens_recusadas_por_capital']}")
    print(f"p_ruina(MC, {ru['n_ops']} ops, R$250->R$100)={b.br(100*ru['p_ruina'],1)}%  "
          f"ruina_formula(Lundberg)={b.br(100*ru['ruina_formula'],1)}%  "
          f"pior_seq_perdas={const.get('pior_seq_ops','--')} (R${b.br(const.get('pior_seq_brl',0.0))})")
    print(f"\nCRITERIO COMPOSTO bate? {_bate_composto(vencedor_final)}  "
          f"(liquido>0 E nao-censurado-por-capital E veredito!=NEGATIVO E p_ruina<={LIMIAR_RUINA*100:.0f}%)")
    print("\nFIM.")


if __name__ == "__main__":
    main()
