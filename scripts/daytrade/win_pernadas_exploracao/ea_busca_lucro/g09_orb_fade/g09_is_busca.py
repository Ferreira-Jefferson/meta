# -*- coding: utf-8 -*-
"""Geracao 9 (`WinBuscaLucroG09OrbFade`) -- BUSCA no IS (jan-jun/2026).

Mesmo METODO da Geracao 8 (mandato do dono, item 3 do prompt desta geracao):
a probabilidade de ruina (`motor.ruina_mc`, Monte Carlo reamostrando as
operacoes do IS, partindo do caixa real R$250, barreira R$100) entra como
RESTRICAO DE BUSCA desde o INICIO, nao so' como checagem depois de escolher o
vencedor por liquido.

Busca em 2 estagios (range_minutos=5min FIXO -- ja estabelecido por G7/G8
como o melhor eixo para o WIN@, nao revisitado aqui):
  AB -- grade CONJUNTA falha_n_barras in {3, 5, 10} x stop_max_pontos in
        {250(ref G7/G8), 200, 160, 140, 120, 100, 80, 60, 50} (27 celulas,
        alvo=3x fixo). Conjunta porque um probe preliminar mostrou que
        stop_max=250 sozinho censura as 3 celulas de falha_n_barras de forma
        quase identica (eixo morto, item 6.25) -- separar os dois estagios
        teria escondido o eixo que de fato importa (stop_max).
  C  -- alvo_multiplo in {3, 4, 5} (M e stop_max do vencedor composto de AB
        fixos) -- so' sobe se o win% permitir, nunca abaixo de 3x.

Criterio de PROMOCAO/vencedor final: COMPOSTO, IDENTICO ao da G8 -- liquido>0
E nao censurado E win% nao-NEGATIVO (POSITIVO ou indefinido, nunca abaixo do
BE empirico com significancia) E probabilidade de ruina (MC, R$250->R$100,
horizonte=44 pregoes projetado pela taxa do IS) <= 20% (revisavel para 25%
ANTES de ver o OOS-1, mesmo precedente da G8, se nenhuma celula bater 20%).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g09_orb_fade/g09_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g09_base as b  # noqa: E402

MAX_WORKERS = 4
LIMIAR_RUINA = 0.20
HORIZONTE_PREGOES = 44  # tamanho do OOS-1 -- a pergunta de ruina e' sobre ESSE horizonte


def _worker(rotulo: str, kwargs_estrategia: dict, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda(dias, **kwargs_estrategia)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias),
                                  horizonte_pregoes=HORIZONTE_PREGOES)
    const = b.constancia_motor(trades)
    sizing = b.sizing_motor(trades)
    be_nom = 1.0 / (1.0 + kwargs_estrategia["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "pregoes c/trade": f"{c['com_trade']}/{c['pregoes']}",
        "p_ruina(MC)": (b.br(100 * ruina["p_ruina"], 1) + "%") if ruina["p_ruina"] == ruina["p_ruina"] else "--",
        "pior_seq_perdas": str(const.get("pior_seq_ops", 0)),
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    stop_dist = sorted(c["stop_dist_pts"])
    return dict(
        rotulo=rotulo, kwargs=kwargs_estrategia, c=c, top5=top5, linha=linha_res,
        equity_min=equity_min, bruto_rompimento=strat.stats_bruto_rompimento,
        bruto_falha=strat.stats_bruto_falha, ja_operou=strat.stats_ja_operou_hoje,
        emitidas=strat.stats_ordens_emitidas, ruina=ruina, const=const, sizing=sizing,
        stop_dist_mediana=(stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")),
    )


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _bate_composto(r: dict, limiar: float = LIMIAR_RUINA) -> bool:
    c = r["c"]
    liquido_ok = c["liquido"] > 0
    censura_ok = not _censurado(r)
    win_ok = c["veredito"] != "NEGATIVO"
    ruina_ok = r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] and r["ruina"]["p_ruina"] <= limiar
    return liquido_ok and censura_ok and win_ok and ruina_ok


def _imprime_linha(rot: str, r: dict) -> None:
    c = r["c"]
    ru = r["ruina"]
    print(f"  {rot:<22} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"stop_med={b.br(r['stop_dist_mediana'],0):>5}pt  "
          f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"bruto(romp/falha)={r['bruto_rompimento']}/{r['bruto_falha']}  "
          f"composto={_bate_composto(r)}", flush=True)


def _roda_estagio(nome: str, variantes: list[tuple[str, dict]], dias: list) -> dict[str, dict]:
    print(f"\n--- ESTAGIO {nome} ---", flush=True)
    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, kw, dias): rot for rot, kw in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            _imprime_linha(rot, r)
    return resultados


def _vencedor_composto(resultados: dict[str, dict], limiar: float = LIMIAR_RUINA) -> dict:
    """Vencedor, em TRES niveis de fallback (declarados, mesma disciplina de
    `g08_is_busca._vencedor_composto`):

    1. Dentre quem BATE o criterio composto inteiro, o de MENOR probabilidade
       de ruina (desempate: maior liquido).
    2. Se ninguem bate mas existe celula NAO CENSURADA, o de menor ruina
       entre as nao censuradas.
    3. So' se TODAS as celulas forem censuradas, o de maior liquido mesmo
       assim (resultado degenerado, declarado como tal na leitura)."""
    def chave(r):
        pr = r["ruina"]["p_ruina"]
        pr = pr if pr == pr else 1.0
        return (pr, -r["c"]["liquido"])

    compostos = {k: v for k, v in resultados.items() if _bate_composto(v, limiar)}
    if compostos:
        return min(compostos.values(), key=chave)
    nao_censurados = {k: v for k, v in resultados.items() if not _censurado(v)}
    if nao_censurados:
        return min(nao_censurados.values(), key=chave)
    return max(resultados.values(), key=lambda r: r["c"]["liquido"])


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 160)
    print("WinBuscaLucroG09OrbFade -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 160)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("NO MAXIMO 1 operacao real por pregao; SEM perna de momentum -- so' fade da FALHA do rompimento.")
    print("alvo sempre >= 3x o stop (mandato do dono).")
    print(f"CRITERIO COMPOSTO: liquido>0 E nao censurado E win% != NEGATIVO E "
          f"p_ruina(MC, R$250->R$100, horizonte={HORIZONTE_PREGOES} pregoes) <= {LIMIAR_RUINA*100:.0f}%.\n",
          flush=True)

    todas_linhas: list[dict] = []
    todos_resultados: dict[str, dict] = {}

    # -- ESTAGIO AB: grade CONJUNTA falha_n_barras x stop_max_pontos ----------
    # Probes preliminares (nao incluidos na tabela oficial) mostraram que, com
    # stop_max largo (250, a referencia "sem restricao"), TODAS as 3 celulas
    # de falha_n_barras colapsam para ~6 trades/censura em poucos dias (equity
    # minima 85, abaixo da margem) -- ou seja, buscar falha_n_barras sozinho
    # com stop_max fixo em 250 teria sido um EIXO MORTO (item 6.25: nenhuma
    # das 3 celulas discrimina nada, todas censuram igual). Por isso esta
    # geracao busca os dois eixos JUNTOS, numa grade 3x9=27 celulas, em vez
    # do estagio sequencial A->B que G07/G08 usaram (ali o eixo fixo da vez
    # anterior nao tinha esse problema).
    variantes_ab = [
        (f"AB M={m} stop_max={sm:g}",
         dict(range_minutos=5.0, stop_min_pontos=50.0, stop_buffer_pontos=20.0,
              buffer_entrada_pontos=20.0, alvo_multiplo=3.0,
              falha_n_barras=m, stop_max_pontos=sm))
        for m in (3, 5, 10)
        for sm in (250.0, 200.0, 160.0, 140.0, 120.0, 100.0, 80.0, 60.0, 50.0)
    ]
    res_ab = _roda_estagio("AB -- falha_n_barras x stop_max_pontos (grade conjunta, range=5min, alvo=3x fixos)",
                           variantes_ab, dias)
    todas_linhas += list(res_ab.values())
    todos_resultados.update(res_ab)
    venc_ab = _vencedor_composto(res_ab)
    falha_n_venc = venc_ab["kwargs"]["falha_n_barras"]
    stop_max_venc = venc_ab["kwargs"]["stop_max_pontos"]
    print(f"  >> vencedor composto AB: falha_n_barras={falha_n_venc}  stop_max_pontos={stop_max_venc:g} "
          f"(liquido={b.br(venc_ab['c']['liquido'])}, p_ruina={b.br(100*venc_ab['ruina']['p_ruina'],1)}%, "
          f"bate_composto={_bate_composto(venc_ab)})")

    # -- ESTAGIO C: alvo_multiplo ----------------------------------------------
    variantes_c = [
        (f"C alvo={am:g}x", dict(range_minutos=5.0, stop_min_pontos=50.0,
                                  stop_buffer_pontos=20.0, buffer_entrada_pontos=20.0,
                                  falha_n_barras=falha_n_venc, stop_max_pontos=stop_max_venc,
                                  alvo_multiplo=am))
        for am in (3.0, 4.0, 5.0)
    ]
    res_c = _roda_estagio(f"C -- alvo_multiplo (falha_n={falha_n_venc}, stop_max={stop_max_venc:g} fixos)",
                          variantes_c, dias)
    todas_linhas += list(res_c.values())
    todos_resultados.update(res_c)
    venc_c = _vencedor_composto(res_c)
    print(f"  >> vencedor composto C: alvo_multiplo={venc_c['kwargs']['alvo_multiplo']:g}x "
          f"(liquido={b.br(venc_c['c']['liquido'])}, p_ruina={b.br(100*venc_c['ruina']['p_ruina'],1)}%, "
          f"bate_composto={_bate_composto(venc_c)})")

    # -- tabela consolidada ----------------------------------------------------
    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "top3/liq", "top5/liq",
              "pregoes c/trade", "p_ruina(MC)", "pior_seq_perdas")
    print("\n" + "=" * 160)
    print("TABELA CONSOLIDADA -- 2 estagios, 30 variantes")
    print("=" * 160)
    print(tabela([r["linha"] for r in todas_linhas], extras=EXTRAS, largura_extra=11))

    print("\nSTOP MEDIANO (pts) por variante (item 6.47 -- flag se < 100):")
    for r in todas_linhas:
        flag = " <<< FLAG 6.47 (precisa checagem com ticks)" if r["stop_dist_mediana"] == r["stop_dist_mediana"] and r["stop_dist_mediana"] < 100 else ""
        print(f"  {r['rotulo']:<22} stop_mediano={b.br(r['stop_dist_mediana'],0)}  "
              f"equity_min={b.br(r['equity_min'])}  "
              f"ruina_formula(Lundberg)={b.br(100*r['ruina']['ruina_formula'],1)}%  "
              f"n_ops_simulados={r['ruina']['n_ops']}  "
              f"bruto(romp/falha/ja_operou/emitidas)={r['bruto_rompimento']}/{r['bruto_falha']}/{r['ja_operou']}/{r['emitidas']}"
              f"{flag}")

    print("\nSIZING (motor.tamanho/p_encolhido) -- Kelly fracionario a R$250 sugere quantos contratos?")
    for r in todas_linhas:
        s = r["sizing"]
        print(f"  {r['rotulo']:<22} p_encolhido={b.br(100*s.get('p_encolhido',float('nan')),1)}%  "
              f"contratos_kelly={s.get('contratos_kelly','--')}")

    # -- vencedor final: composto sobre A UNIAO de todas as celulas testadas --
    vencedor_final = _vencedor_composto(todos_resultados)
    limiar_usado = LIMIAR_RUINA
    if not _bate_composto(vencedor_final, LIMIAR_RUINA):
        # mesma logica de revisao da G8: se NINGUEM bate 20%, revisa para 25%
        # ANTES de ver o OOS-1, so' se existir celula nao-censurada que bata 25%.
        cand_25 = _vencedor_composto(todos_resultados, 0.25)
        if _bate_composto(cand_25, 0.25):
            vencedor_final = cand_25
            limiar_usado = 0.25
            print("\nAVISO: nenhuma celula bateu o limiar de ruina de 20% -- "
                  "revisado para 25% ANTES de ver o OOS-1 (mesmo precedente da G8).")

    print("\n" + "=" * 160)
    print("VENCEDOR FINAL (criterio COMPOSTO, uniao de AB+C, limiar ruina=%.0f%%):" % (limiar_usado * 100),
          vencedor_final["rotulo"], vencedor_final["kwargs"])
    print("=" * 160)
    c = vencedor_final["c"]
    ru = vencedor_final["ruina"]
    const = vencedor_final["const"]
    print(f"liquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  veredito={c['veredito']}  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  "
          f"pregoes_c_trade={c['com_trade']}/{c['pregoes']}")
    print(f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liq={b.br(100*vencedor_final['top5'],0) if vencedor_final['top5']==vencedor_final['top5'] else '--'}%  "
          f"stop_mediano={b.br(vencedor_final['stop_dist_mediana'],0)}pts  censurado={_censurado(vencedor_final)}")
    print(f"p_ruina(MC, {ru['n_ops']} ops, R$250->R$100)={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%  "
          f"ruina_formula(Lundberg)={b.br(100*ru['ruina_formula'],1) if ru['ruina_formula']==ru['ruina_formula'] else '--'}%  "
          f"pior_seq_perdas={const.get('pior_seq_ops','--')} (R${b.br(const.get('pior_seq_brl',0.0))})")
    print(f"bruto(rompimento/falha/ja_operou/emitidas)="
          f"{vencedor_final['bruto_rompimento']}/{vencedor_final['bruto_falha']}/"
          f"{vencedor_final['ja_operou']}/{vencedor_final['emitidas']}")
    print(f"\nCRITERIO COMPOSTO bate (limiar {limiar_usado*100:.0f}%)? {_bate_composto(vencedor_final, limiar_usado)}  "
          f"(liquido>0 E nao-censurado E veredito!=NEGATIVO E p_ruina<={limiar_usado*100:.0f}%)")
    print("\nFIM.")


if __name__ == "__main__":
    main()
