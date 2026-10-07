# -*- coding: utf-8 -*-
"""Geracao 6 (`WinBuscaLucroG06AmplitudeTeto`) -- BUSCA no IS (jan-jun/2026).

Pergunta (ORQUESTRACAO.md, raciocinio da G5): o proxy `regime_amplitude_
bloco` (j15/q90) com a geometria vencedora da G5 (stop=150/alvo=3x/
buffer=30) deu liquido POSITIVO com amostra grande (667 trades, win% POSITIVO
com folga), mas concentracao top-3-pregoes/liquido = 59% -- igual a` G4, nao
menor -- porque o proxy REENTRA dezenas de vezes no MESMO pregao favoravel
(maximo 24 operacoes/dia). Esta geracao testa se um teto `max_trades_por_
pregao` em N in {1,2,3,4} + SEM TETO (= G5, referencia) devolve a
concentracao para perto de 35-40% mantendo liquido>0 e win%/BE favoravel.

Decisao de qual trade manter quando ha' mais de 1 candidato no pregao: os
PRIMEIROS N sinais, na ORDEM EM QUE O GATILHO DISPARA (nao e' selecao
retroativa -- ver docstring da classe). Geometria/proxy FIXOS nesta geracao
(herdados do vencedor da G5): janela_min=15, quantil=0.90, stop_pontos=150,
alvo_multiplo=3.0, buffer_entrada_pontos=30 -- so' `max_trades_por_pregao`
varia.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g06_amplitude_teto/g06_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g06_base as b  # noqa: E402

MAX_WORKERS = 4
REGIME_KWARGS = dict(janela_min=15, quantil=0.90)
GEOMETRIA = dict(stop_pontos=150.0, alvo_multiplo=3.0, buffer_entrada_pontos=30.0)

VARIANTES = [
    ("N=1", 1), ("N=2", 2), ("N=3", 3), ("N=4", 4), ("sem teto (=G5)", None),
]


def _worker(rotulo: str, max_trades: int | None, dias: list):
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))
    from backtest.intraday.report import linha_de_resultado

    res, strat = b.roda(
        dias, dias, REGIME_KWARGS,
        max_trades_por_pregao=max_trades, **GEOMETRIA,
    )
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    be_nom = 1.0 / (1.0 + GEOMETRIA["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "bruto": str(strat.stats_bruto),
        "sem_tend": str(strat.stats_sem_tendencia),
        "teto_pregao": str(strat.stats_teto_pregao),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "pregoes c/trade": f"{c['com_trade']}/{c['pregoes']}",
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    return dict(
        rotulo=rotulo, max_trades=max_trades, c=c, top5=top5, linha=linha_res,
        equity_min=equity_min, bruto=strat.stats_bruto, sem_tend=strat.stats_sem_tendencia,
        teto_pregao=strat.stats_teto_pregao, emitidas=strat.stats_ordens_emitidas,
        stop_dist_mediana=(sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2]
                            if c["stop_dist_pts"] else float("nan")),
    )


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 150)
    print("WinBuscaLucroG06AmplitudeTeto -- BUSCA no IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 150)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print(f"proxy FIXO: regime_amplitude_bloco {REGIME_KWARGS}; geometria FIXA: {GEOMETRIA}")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("Decisao de desempate no mesmo pregao: PRIMEIROS N sinais, na ordem em que o gatilho dispara.\n",
          flush=True)

    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, mx, dias): rot for rot, mx in VARIANTES}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            c = r["c"]
            print(f"  {rot:<16} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
                  f"veredito={c['veredito']:<10}  "
                  f"pregoes_c_trade={c['com_trade']:>3}/{c['pregoes']}  "
                  f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
                  f"top5/liq={b.br(100*r['top5'],0) if r['top5']==r['top5'] else '--':>5}%  "
                  f"teto_pregao_descartou={r['teto_pregao']:>5}  "
                  f"censurado={_censurado(r)}", flush=True)

    ordem = [rot for rot, _ in VARIANTES]
    linhas = [resultados[rot] for rot in ordem]

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "bruto", "sem_tend",
              "teto_pregao", "emit/brt", "top3/liq", "top5/liq", "pregoes c/trade")
    print("\n" + "=" * 150)
    print("TABELA CONSOLIDADA -- N in {1,2,3,4,sem teto} no IS")
    print("=" * 150)
    print(tabela([r["linha"] for r in linhas], extras=EXTRAS, largura_extra=10))

    print("\nSTOP MEDIANO (pts) por N:")
    for r in linhas:
        print(f"  {r['rotulo']:<16} stop_mediano={b.br(r['stop_dist_mediana'],0)}  equity_min={b.br(r['equity_min'])}")

    print("\nCRITERIO DE PROMOCAO AO OOS-1 (item 5 do mandato): liquido>0 E nao censurado "
          "E win%/IC95 favoravel E top3/liq MATERIALMENTE < 59% (ex. <=40%) SEM destruir a amostra "
          "(ainda dezenas de trades em dezenas de pregoes distintos).")
    aprovados = []
    for r in linhas:
        c = r["c"]
        se_amostra_razoavel = c["n"] >= 20 and c["com_trade"] >= 15
        se_conc_ok = c["concentracao_top3"] == c["concentracao_top3"] and c["concentracao_top3"] <= 0.40
        se_win_ok = c["veredito"] == "POSITIVO"
        se_liquido_ok = c["liquido"] > 0
        se_censura_ok = not _censurado(r)
        bate = se_amostra_razoavel and se_conc_ok and se_win_ok and se_liquido_ok and se_censura_ok
        print(f"  {r['rotulo']:<16} amostra_ok={se_amostra_razoavel}  conc<=40%={se_conc_ok}  "
              f"win_POSITIVO={se_win_ok}  liquido>0={se_liquido_ok}  nao_censurado={se_censura_ok}  "
              f"-> {'PROMOVE' if bate else 'nao promove'}")
        if bate:
            aprovados.append(r)

    print("\nVEREDITO DO PORTAO IS:")
    if aprovados:
        for r in aprovados:
            print(f"  -> {r['rotulo']} BATE o criterio -- candidato a promover ao OOS-1 (rodar g06_oos1.py).")
    else:
        print("  -> NENHUM N bate o criterio completo no IS. Nao promove ninguem ao OOS-1.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
