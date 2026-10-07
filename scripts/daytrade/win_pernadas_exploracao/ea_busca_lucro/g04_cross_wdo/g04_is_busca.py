# -*- coding: utf-8 -*-
"""Geracao 4 (`WinBuscaLucroG04CrossWdo`) -- BUSCA no IS (jan-jun/2026).

Confirmacao cruzada WIN x WDO, estado anomalo (os dois andam na MESMA
direcao por uma janela curta, quando normalmente andam opostos). Quatro
estagios, cada um fixando o vencedor do anterior:

  Estagio A -- janela (10/15/20 min) x quantil (0,60/0,75/0,90) x direcao da
               aposta (continuacao/reversao), geometria fixa (stop=150pts,
               alvo=5x, buffer=20pts). 18 celulas -- descobre ONDE procurar
               antes de refinar geometria.
  Estagio B -- stop_pontos (100/150/200) na celula vencedora do estagio A,
               alvo_multiplo=5x fixo.
  Estagio C -- alvo_multiplo (3x/5x/7x) no stop vencedor do estagio B.
  Estagio D -- buffer_entrada_pontos (0/10/20/30) na geometria vencedora de B+C.

Sempre a favor da pernada maior do WIN (R43, principio inegociavel -- nao e'
parametro). Execucao fechada identica a` linha (EnterLimit ttl=10, saida
fatiada sem prazo, anchor_exits_at_fill, so' stop a mercado), capital real
R$250, fila WIN@ zero (nao calibrada, premissa otimista declarada), 1
contrato fixo.

Conta TAMBEM `stats_bruto` (borda de anomalia com direcao definida, antes de
qualquer filtro) ao lado de `stats_contra_tendencia` e `stats_ordens_
emitidas` -- e' o teste que teria pego mais cedo o bug de ordem-de-operacoes
da Geracao 2 (item 6.48 de LICOES_DE_PRODUCAO.md).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g04_cross_wdo/g04_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g04_base as b  # noqa: E402

MAX_WORKERS = 4

GEOMETRIA_BASE = dict(stop_pontos=150.0, alvo_multiplo=5.0, buffer_entrada_pontos=20.0)

ESTAGIO_A = [
    (f"A j{janela} q{int(quantil*100)} {direcao[:4]}",
     dict(janela_min=janela, quantil=quantil, direcao_aposta=direcao, **GEOMETRIA_BASE))
    for janela in (10, 15, 20)
    for quantil in (0.60, 0.75, 0.90)
    for direcao in ("continuacao", "reversao")
]


def _monta_estagio_b(vencedor_a: dict) -> list:
    base = dict(vencedor_a)
    base.pop("stop_pontos", None)
    return [(f"B stop={s:.0f}", dict(**base, stop_pontos=s)) for s in (100.0, 150.0, 200.0)]


def _monta_estagio_c(vencedor_b: dict) -> list:
    base = dict(vencedor_b)
    base.pop("alvo_multiplo", None)
    return [(f"C alvo={m:.0f}x", dict(**base, alvo_multiplo=m)) for m in (3.0, 5.0, 7.0)]


def _monta_estagio_d(vencedor_c: dict) -> list:
    base = dict(vencedor_c)
    base.pop("buffer_entrada_pontos", None)
    return [(f"D buffer={bp:.0f}", dict(**base, buffer_entrada_pontos=bp)) for bp in (0.0, 10.0, 20.0, 30.0)]


def _worker(rotulo: str, kw: dict, dias: list):
    """Roda 1 variante num processo filho -- devolve so' dados picklable."""
    janela_min = kw.pop("janela_min")
    quantil = kw.pop("quantil")
    res, strat = b.roda(dias, dias_historico=dias, janela_min=janela_min, quantil=quantil, **kw)
    kw["janela_min"] = janela_min
    kw["quantil"] = quantil
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    from backtest.intraday.report import linha_de_resultado
    be_nom = 1.0 / (1.0 + kw.get("alvo_multiplo", 5.0))
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "bruto": str(strat.stats_bruto),
        "contra_tend": str(strat.stats_contra_tendencia),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "pts/op": b.br(c["pontos_por_op"], 2),
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    return dict(
        rotulo=rotulo, kw=kw, c=c, linha=linha_res,
        equity_min=equity_min,
        ordens_recusadas=res.ordens_recusadas_por_capital,
        bruto=strat.stats_bruto, contra_tend=strat.stats_contra_tendencia,
        emitidas=strat.stats_ordens_emitidas,
        stop_dist_mediana=(sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2]
                            if c["stop_dist_pts"] else float("nan")),
    )


def _roda_estagio(nome_estagio: str, variantes: list, dias: list) -> list[dict]:
    print(f"\n--- {nome_estagio} ({len(variantes)} variantes, {MAX_WORKERS} workers) ---", flush=True)
    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, dict(kw), dias): rot for rot, kw in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            c = r["c"]
            print(f"  {rot:<22} liquido={b.br(c['liquido']):>10}  bruto={r['bruto']:>4}  "
                  f"contra_tend={r['contra_tend']:>4}  emitidas={r['emitidas']:>4}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
                  f"equity_min={b.br(r['equity_min']):>9}  "
                  f"stop_med_pts={b.br(r['stop_dist_mediana'],0)}  "
                  f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%",
                  flush=True)
    return [resultados[rot] for rot, _ in variantes]


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _melhor(resultados: list[dict]) -> dict:
    nao_censurados = [r for r in resultados if not _censurado(r)]
    pool = nao_censurados if nao_censurados else resultados
    return max(pool, key=lambda r: r["c"]["liquido"])


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 135)
    print("WinBuscaLucroG04CrossWdo -- BUSCA no IS (jan-jun/2026), capital R$ %s (piso de partida real do WIN@)"
          % b.br(b.CAPITAL, 0))
    print("=" * 135)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    corr = b.correlacao_incrementos_minuto(win, b.carrega_wdo(), dias)
    print(f"Correlacao incrementos de 1 min (IS, remedida do zero): r={corr['r']:.4f}  n={corr['n']}")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE "
          "(queue_ahead_qty=0, exit_queue_ahead_qty=0).")
    print("Censura (para escolher o vencedor de cada estagio): 0 trades, OU >=50% dos pregoes sem "
          "trade, OU caixa minimo < margem crua (R$100).\n", flush=True)

    todas_as_linhas = []

    res_a = _roda_estagio("ESTAGIO A -- janela x quantil x direcao da aposta", ESTAGIO_A, dias)
    todas_as_linhas += res_a
    vencedor_a = _melhor(res_a)
    print(f"\n  >> vencedor do estagio A: {vencedor_a['rotulo']} "
          f"(censurado={_censurado(vencedor_a)})", flush=True)

    estagio_b = _monta_estagio_b(vencedor_a["kw"])
    res_b = _roda_estagio("ESTAGIO B -- stop_pontos", estagio_b, dias)
    todas_as_linhas += res_b
    vencedor_b = _melhor(res_b)
    print(f"\n  >> vencedor do estagio B: {vencedor_b['rotulo']} "
          f"(censurado={_censurado(vencedor_b)})", flush=True)

    estagio_c = _monta_estagio_c(vencedor_b["kw"])
    res_c = _roda_estagio("ESTAGIO C -- alvo_multiplo", estagio_c, dias)
    todas_as_linhas += res_c
    vencedor_c = _melhor(res_c)
    print(f"\n  >> vencedor do estagio C: {vencedor_c['rotulo']} "
          f"(censurado={_censurado(vencedor_c)})", flush=True)

    estagio_d = _monta_estagio_d(vencedor_c["kw"])
    res_d = _roda_estagio("ESTAGIO D -- buffer_entrada_pontos", estagio_d, dias)
    todas_as_linhas += res_d
    vencedor_d = _melhor(res_d)
    print(f"\n  >> vencedor do estagio D: {vencedor_d['rotulo']} "
          f"(censurado={_censurado(vencedor_d)})", flush=True)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "bruto", "contra_tend",
              "emit/brt", "top3/liq", "pts/op", "sem_tr")
    print("\n" + "=" * 135)
    print("TABELA CONSOLIDADA -- todas as variantes testadas no IS")
    print("=" * 135)
    print(tabela([r["linha"] for r in todas_as_linhas], extras=EXTRAS, largura_extra=10))

    vencedor_final = vencedor_d
    print(f"\nVENCEDOR FINAL (congelar para OOS-1): {vencedor_final['rotulo']}")
    print(f"  kwargs = {vencedor_final['kw']}")
    cc = vencedor_final["c"]
    print(f"  liquido={b.br(cc['liquido'])}  bruto={vencedor_final['bruto']}  "
          f"contra_tend={vencedor_final['contra_tend']}  emitidas={vencedor_final['emitidas']}  "
          f"trades={cc['n']}  win={b.br(100*cc['win'],1) if cc['n'] else '--'}%  "
          f"sem_trade={cc['sem_trade']}/{cc['pregoes']}  censurado={_censurado(vencedor_final)}  "
          f"stop_mediana_pts={b.br(vencedor_final['stop_dist_mediana'],0)}  "
          f"top3/liq={b.br(100*cc['concentracao_top3'],0) if cc['concentracao_top3']==cc['concentracao_top3'] else '--'}%")

    print("\nGATE para OOS-1 (regra do protocolo): liquido > 0 E nao censurado.")
    passa = cc["liquido"] > 0 and not _censurado(vencedor_final)
    print(f"  -> {'PASSA (roda OOS-1)' if passa else 'NAO PASSA (morta no IS)'}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
