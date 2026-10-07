# -*- coding: utf-8 -*-
"""Geracao 7 (`WinBuscaLucroG07Orb`) -- BUSCA no IS (jan-jun/2026).

Pergunta (ORQUESTRACAO.md, raciocinio da G6): as Geracoes 4-6 esgotaram a
familia "continuacao da pernada maior sob gatilho de volatilidade/regime" --
concentracao top-3/liquido nao cede por nenhum angulo testado. Esta geracao
testa uma familia ESTRUTURALMENTE diferente: ORB (rompimento da faixa de
abertura), adaptado do `WdoOrb` (ja' em producao real no WDO@), SEM depender
de pernada de 750 pontos nem de regime/cross-market. Alvo sempre >= 3x o
stop (disciplina do mandato, mais estrito que o `WdoOrb` em producao, que usa
1,5x). NO MAXIMO 1 operacao real por pregao (sem fade) -- ver a docstring da
classe para a razao de nao somar o fade nesta primeira rodada.

Busca em 3 estagios gulosos, cada um fixando o vencedor do anterior:
  A -- range_minutos in {5, 15, 30} (stop_max=250, alvo=3x fixos)
  B -- stop_max_pontos in {150, 250, 400} (range_minutos do vencedor A, alvo=3x)
  C -- alvo_multiplo in {3, 5, 7} (range_minutos e stop_max dos vencedores A/B)

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g07_orb/g07_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g07_base as b  # noqa: E402

MAX_WORKERS = 4


def _worker(rotulo: str, kwargs_estrategia: dict, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda(dias, **kwargs_estrategia)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    be_nom = 1.0 / (1.0 + kwargs_estrategia["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "pregoes c/trade": f"{c['com_trade']}/{c['pregoes']}",
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    stop_dist = sorted(c["stop_dist_pts"])
    return dict(
        rotulo=rotulo, kwargs=kwargs_estrategia, c=c, top5=top5, linha=linha_res,
        equity_min=equity_min, bruto=strat.stats_bruto, ja_operou=strat.stats_ja_operou_hoje,
        emitidas=strat.stats_ordens_emitidas,
        stop_dist_mediana=(stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")),
    )


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _imprime_linha(rot: str, r: dict) -> None:
    c = r["c"]
    print(f"  {rot:<28} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"pregoes_c_trade={c['com_trade']:>3}/{c['pregoes']}  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"emit/bruto={r['emitidas']}/{r['bruto']}  "
          f"censurado={_censurado(r)}", flush=True)


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


def _vencedor(resultados: dict[str, dict]) -> dict:
    """Maior liquido entre os NAO censurados; se todos censurados, maior
    liquido mesmo assim (declarado na leitura, nunca escondido)."""
    nao_censurados = {k: v for k, v in resultados.items() if not _censurado(v)}
    pool = nao_censurados if nao_censurados else resultados
    return max(pool.values(), key=lambda r: r["c"]["liquido"])


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 150)
    print("WinBuscaLucroG07Orb -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 150)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("NO MAXIMO 1 operacao real por pregao (sem fade); alvo sempre >= 3x o stop.\n", flush=True)

    todas_linhas: list[dict] = []

    # -- ESTAGIO A: range_minutos --------------------------------------------
    base_kwargs = dict(stop_min_pontos=100.0, stop_max_pontos=250.0,
                        alvo_multiplo=3.0, buffer_entrada_pontos=20.0)
    variantes_a = [
        (f"A range={rm:g}min", dict(base_kwargs, range_minutos=rm))
        for rm in (5.0, 15.0, 30.0)
    ]
    res_a = _roda_estagio("A -- range_minutos", variantes_a, dias)
    todas_linhas += list(res_a.values())
    venc_a = _vencedor(res_a)
    range_venc = venc_a["kwargs"]["range_minutos"]
    print(f"  >> vencedor A: range_minutos={range_venc:g} (liquido={b.br(venc_a['c']['liquido'])})")

    # -- ESTAGIO B: stop_max_pontos -------------------------------------------
    variantes_b = [
        (f"B stop_max={sm:g}", dict(base_kwargs, range_minutos=range_venc, stop_max_pontos=sm))
        for sm in (150.0, 250.0, 400.0)
    ]
    res_b = _roda_estagio("B -- stop_max_pontos", variantes_b, dias)
    todas_linhas += list(res_b.values())
    venc_b = _vencedor(res_b)
    stop_max_venc = venc_b["kwargs"]["stop_max_pontos"]
    print(f"  >> vencedor B: stop_max_pontos={stop_max_venc:g} (liquido={b.br(venc_b['c']['liquido'])})")

    # -- ESTAGIO C: alvo_multiplo ---------------------------------------------
    variantes_c = [
        (f"C alvo={am:g}x", dict(base_kwargs, range_minutos=range_venc,
                                  stop_max_pontos=stop_max_venc, alvo_multiplo=am))
        for am in (3.0, 5.0, 7.0)
    ]
    res_c = _roda_estagio("C -- alvo_multiplo", variantes_c, dias)
    todas_linhas += list(res_c.values())
    venc_c = _vencedor(res_c)
    print(f"  >> vencedor C: alvo_multiplo={venc_c['kwargs']['alvo_multiplo']:g}x "
          f"(liquido={b.br(venc_c['c']['liquido'])})")

    # -- tabela consolidada ----------------------------------------------------
    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "emit/brt",
              "top3/liq", "top5/liq", "pregoes c/trade")
    print("\n" + "=" * 150)
    print("TABELA CONSOLIDADA -- 3 estagios, 9 variantes")
    print("=" * 150)
    print(tabela([r["linha"] for r in todas_linhas], extras=EXTRAS, largura_extra=10))

    print("\nSTOP MEDIANO (pts) por variante (item 6.47 -- flag se < 100):")
    for r in todas_linhas:
        flag = " <<< FLAG 6.47" if r["stop_dist_mediana"] == r["stop_dist_mediana"] and r["stop_dist_mediana"] < 100 else ""
        print(f"  {r['rotulo']:<28} stop_mediano={b.br(r['stop_dist_mediana'],0)}  "
              f"equity_min={b.br(r['equity_min'])}{flag}")

    vencedor_final = venc_c
    print("\n" + "=" * 150)
    print("VENCEDOR FINAL DA BUSCA:", vencedor_final["rotulo"], vencedor_final["kwargs"])
    print("=" * 150)
    c = vencedor_final["c"]
    print(f"liquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1)}%  "
          f"BEemp={b.br(100*c['be'],1)}%  veredito={c['veredito']}  "
          f"pregoes_c_trade={c['com_trade']}/{c['pregoes']}  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0)}%  top5/liq={b.br(100*vencedor_final['top5'],0)}%  "
          f"stop_mediano={b.br(vencedor_final['stop_dist_mediana'],0)}pts  "
          f"censurado={_censurado(vencedor_final)}")

    print("\nCRITERIO DE PROMOCAO AO OOS-1: liquido>0 E nao censurado E amostra razoavel.")
    amostra_ok = c["n"] >= 10 and c["com_trade"] >= 8
    liquido_ok = c["liquido"] > 0
    censura_ok = not _censurado(vencedor_final)
    bate = amostra_ok and liquido_ok and censura_ok
    print(f"  amostra_ok={amostra_ok}  liquido>0={liquido_ok}  nao_censurado={censura_ok} "
          f"-> {'PROMOVE ao OOS-1' if bate else 'NAO PROMOVE'}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
