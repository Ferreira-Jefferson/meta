# -*- coding: utf-8 -*-
"""Geracao 12 (`WinBuscaLucroG12AndOrbCross`) -- BUSCA no IS (jan-jun/2026).

Mandato do COORDENADOR: alavanca (2) -- combinacao E (AND) de dois sinais
INDEPENDENTES (ORB da G8 + estado anomalo WIN x WDO da G4, direcao=continuacao,
j=20min/q=0,75 FIXOS pelo mandato). Eixo causal varrido: `k_minutos in
{0, 5, 15, 30}` -- janela, terminando no proprio instante do rompimento, em
que o sinal B precisa ter estado ativo e na MESMA direcao.

Diagnostico previo (`g12_diagnostico.py`, `g12_diagnostico_stdout.log`): o AND
derruba o bruto de 1084 (ORB puro) para 15-82 bordas A∩B conforme k_minutos
(0/5/15/30), e as ordens emitidas (com a geometria-base da G8: stop_max=140,
alvo=3x) ficam entre 12 e 33 -- MUITO abaixo da amostra de 121 trades da REF.
Por isso esta busca roda os DOIS estagios da G08 (stop_max_pontos, depois
alvo_multiplo) para CADA k_minutos, exatamente como o mandato pede ("sinta-se
livre para retunar dentro do IS").

Criterio de PROMOCAO/vencedor: o MESMO composto da G08 (precedente direto,
mesma familia/capital/instrumento) -- liquido>0 E nao censurado E win% nao-
NEGATIVO E p_ruina(MC, R$250->R$100, horizonte=44 pregoes) <= 25% (G08 usou
20% no desenho e relaxou para 25% ANTES de ver o OOS-1 -- herdado aqui desde
o inicio, declarado, nao ajustado depois de ver numero).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g12_and_orb_cross/g12_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g12_base as b  # noqa: E402

MAX_WORKERS = 4
LIMIAR_RUINA = 0.25
HORIZONTE_PREGOES = 44  # tamanho do OOS-1
KS = (0.0, 5.0, 15.0, 30.0)


def _worker_ref(dias: list, kwargs_estrategia: dict):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda_orb_puro(dias, **kwargs_estrategia)
    trades = list(res.trades)
    return _monta_registro("REF ORB puro (G8)", kwargs_estrategia, res, trades, dias,
                            bruto_a=strat.stats_bruto, bruto_b=None, and_bruto=None,
                            emitidas=strat.stats_ordens_emitidas)


def _worker_and(rotulo: str, k: float, kwargs_estrategia: dict, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

    res, strat = b.roda(dias, k_minutos=k, **kwargs_estrategia)
    trades = list(res.trades)
    return _monta_registro(rotulo, dict(kwargs_estrategia, k_minutos=k), res, trades, dias,
                            bruto_a=strat.stats_bruto_a, bruto_b=strat.stats_bruto_b,
                            and_bruto=strat.stats_and_bruto, emitidas=strat.stats_ordens_emitidas)


def _monta_registro(rotulo, kwargs_estrategia, res, trades, dias, *, bruto_a, bruto_b, and_bruto, emitidas):
    from backtest.intraday.report import linha_de_resultado

    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), horizonte_pregoes=HORIZONTE_PREGOES)
    const = b.constancia_motor(trades)
    sizing = b.sizing_motor(trades)
    alvo_m = kwargs_estrategia.get("alvo_multiplo", 3.0)
    be_nom = 1.0 / (1.0 + alvo_m)
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "brtA/brtB/A∩B/emit": f"{bruto_a}/{bruto_b if bruto_b is not None else '--'}/"
                               f"{and_bruto if and_bruto is not None else '--'}/{emitidas}",
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
        equity_min=equity_min, bruto_a=bruto_a, bruto_b=bruto_b, and_bruto=and_bruto,
        emitidas=emitidas, ruina=ruina, const=const, sizing=sizing,
        stop_dist_mediana=(stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")),
    )


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


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
    print(f"  {rot:<28} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"stop_med={b.br(r['stop_dist_mediana'],0):>5}pt  "
          f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"composto={_bate_composto(r)}", flush=True)


def _roda_estagio(nome: str, variantes: list, k: float, dias: list) -> dict:
    print(f"\n--- k={k:g}min -- ESTAGIO {nome} ---", flush=True)
    resultados: dict = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker_and, rot, k, kw, dias): rot for rot, kw in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            _imprime_linha(rot, r)
    return resultados


def _vencedor_composto(resultados: dict) -> dict:
    def chave(r):
        pr = r["ruina"]["p_ruina"]
        pr = pr if pr == pr else 1.0
        return (pr, -r["c"]["liquido"])

    compostos = {k: v for k, v in resultados.items() if _bate_composto(v)}
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
    print("=" * 170)
    print("WinBuscaLucroG12AndOrbCross -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 170)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("Sinal B (estado anomalo WIN x WDO, G4): janela_min=%d quantil=%.2f direcao=continuacao (FIXOS pelo mandato)"
          % (b.JANELA_MIN_SINAL_B, b.QUANTIL_SINAL_B))
    print("NO MAXIMO 1 operacao real por pregao (sem fade); alvo sempre >= 3x o stop.")
    print(f"CRITERIO COMPOSTO: liquido>0 E nao censurado E win% != NEGATIVO E "
          f"p_ruina(MC, horizonte={HORIZONTE_PREGOES} pregoes) <= {LIMIAR_RUINA*100:.0f}%.\n", flush=True)

    # -- REF: ORB puro (G8, geometria vencedora original) ----------------------
    ref_kwargs = dict(range_minutos=5.0, stop_min_pontos=50.0, stop_max_pontos=140.0,
                       alvo_multiplo=3.0, buffer_entrada_pontos=20.0, ttl_barras_entrada=10)
    ref = _worker_ref(dias, ref_kwargs)
    _imprime_linha("REF ORB puro (G8)", ref)

    todas_linhas = [ref]
    vencedores_por_k: dict = {}

    for k in KS:
        base_kwargs = dict(range_minutos=5.0, stop_min_pontos=50.0,
                            alvo_multiplo=3.0, buffer_entrada_pontos=20.0, ttl_barras_entrada=10)
        variantes_a = [
            (f"k{k:g} A stop_max={sm:g}", dict(base_kwargs, stop_max_pontos=sm))
            for sm in (250.0, 200.0, 160.0, 150.0, 140.0, 130.0, 120.0, 110.0, 100.0, 90.0, 80.0, 60.0)
        ]
        res_a = _roda_estagio(f"A -- stop_max_pontos (range=5min, alvo=3x fixos)", variantes_a, k, dias)
        todas_linhas += list(res_a.values())
        venc_a = _vencedor_composto(res_a)
        stop_max_venc = venc_a["kwargs"]["stop_max_pontos"]
        print(f"  >> vencedor composto A (k={k:g}min): stop_max_pontos={stop_max_venc:g} "
              f"(liquido={b.br(venc_a['c']['liquido'])}, p_ruina={b.br(100*venc_a['ruina']['p_ruina'],1)}%, "
              f"bate_composto={_bate_composto(venc_a)})")

        variantes_b = [
            (f"k{k:g} B alvo={am:g}x", dict(range_minutos=5.0, stop_min_pontos=50.0,
                                             stop_max_pontos=stop_max_venc,
                                             buffer_entrada_pontos=20.0, ttl_barras_entrada=10, alvo_multiplo=am))
            for am in (3.0, 4.0, 5.0, 6.0)
        ]
        res_b = _roda_estagio(f"B -- alvo_multiplo (stop_max={stop_max_venc:g} fixo)", variantes_b, k, dias)
        todas_linhas += list(res_b.values())
        venc_b = _vencedor_composto(res_b)
        print(f"  >> vencedor composto B (k={k:g}min): alvo_multiplo={venc_b['kwargs']['alvo_multiplo']:g}x "
              f"(liquido={b.br(venc_b['c']['liquido'])}, p_ruina={b.br(100*venc_b['ruina']['p_ruina'],1)}%, "
              f"bate_composto={_bate_composto(venc_b)})")

        vencedores_por_k[k] = _vencedor_composto({**res_a, **res_b})

    # -- tabela consolidada ----------------------------------------------------
    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "brtA/brtB/A∩B/emit",
              "top3/liq", "top5/liq", "pregoes c/trade", "p_ruina(MC)", "pior_seq_perdas")
    print("\n" + "=" * 170)
    print(f"TABELA CONSOLIDADA -- REF + {len(KS)} valores de k_minutos x 2 estagios")
    print("=" * 170)
    print(tabela([r["linha"] for r in todas_linhas], extras=EXTRAS, largura_extra=11))

    print("\nVENCEDOR COMPOSTO POR k_minutos:")
    for k in KS:
        v = vencedores_por_k[k]
        c = v["c"]
        ru = v["ruina"]
        print(f"  k={k:>4g}min  {v['rotulo']:<22}  kwargs={v['kwargs']}  "
              f"liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
              f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%  "
              f"composto={_bate_composto(v)}")

    todos = {f"k{k:g}_{v['rotulo']}": v for k, v in vencedores_por_k.items()}
    vencedor_final = _vencedor_composto(todos) if todos else None
    print("\n" + "=" * 170)
    if vencedor_final is not None:
        print("VENCEDOR FINAL (composto, uniao de todos os k_minutos):", vencedor_final["rotulo"], vencedor_final["kwargs"])
        c = vencedor_final["c"]
        ru = vencedor_final["ruina"]
        const = vencedor_final["const"]
        print(f"liquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1)}%  "
              f"BEemp={b.br(100*c['be'],1)}%  veredito={c['veredito']}  IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  "
              f"pregoes_c_trade={c['com_trade']}/{c['pregoes']}")
        print(f"top3/liq={b.br(100*c['concentracao_top3'],0)}%  top5/liq={b.br(100*vencedor_final['top5'],0)}%  "
              f"stop_mediano={b.br(vencedor_final['stop_dist_mediana'],0)}pts  censurado={_censurado(vencedor_final)}")
        print(f"p_ruina(MC, {ru['n_ops']} ops, R$250->R$100)={b.br(100*ru['p_ruina'],1)}%  "
              f"ruina_formula(Lundberg)={b.br(100*ru['ruina_formula'],1)}%  "
              f"pior_seq_perdas={const.get('pior_seq_ops','--')} (R${b.br(const.get('pior_seq_brl',0.0))})")
        print(f"\nCRITERIO COMPOSTO bate? {_bate_composto(vencedor_final)}  "
              f"(liquido>0 E nao-censurado E veredito!=NEGATIVO E p_ruina<={LIMIAR_RUINA*100:.0f}%)")
    else:
        print("NENHUMA celula para comparar.")
    print("=" * 170)
    print("\nFIM.")


if __name__ == "__main__":
    main()
