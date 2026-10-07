# -*- coding: utf-8 -*-
"""Geracao 2 (`WinBuscaLucroG02R65`) -- BUSCA no IS (jan-jun/2026).

R65 como hipotese PROPRIA (nao herda o portao de horario `<11h` da G1, que
zerou o sinal por engano -- ver `ORQUESTRACAO.md`, Geracao 1). Tres estagios,
cada um fixando o vencedor do anterior, para nao estourar a tabela:

  Estagio A -- janela de horario (sem filtro / so' manha / so' tarde / dia
               todo exceto ultimos 30min), geometria fixa (stop tecnico
               N=10, alvo 5x).
  Estagio B -- familia de stop (tecnico N=5/10/15, ATR M15 k=1,0/1,5) na
               janela vencedora do estagio A, alvo 5x.
  Estagio C -- multiplo do alvo (3x/5x/7x) na janela+stop vencedores de
               A+B.

Tudo dentro do IS -- nenhum numero de jul/2026 em diante e' olhado aqui.
Capital R$250,00 (piso de PARTIDA real do WIN@). Fila zero nos dois lados
(WIN@ sem fidelidade calibrada), premissa otimista declarada.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g02_r65/g02_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g02_base as b  # noqa: E402

MAX_WORKERS = 4

# -- Estagio A: janela de horario (geometria fixa) --------------------------
ESTAGIO_A = [
    ("A1 sem_filtro (09-18:29)", dict(janela_inicio="09:00", janela_fim="18:29",
                                       familia_stop="tecnico", barras_stop_tecnico=10, alvo_multiplo=5.0)),
    ("A2 so_manha (09-11:00)", dict(janela_inicio="09:00", janela_fim="11:00",
                                     familia_stop="tecnico", barras_stop_tecnico=10, alvo_multiplo=5.0)),
    ("A3 so_tarde (12:59-18:29)", dict(janela_inicio="12:59", janela_fim="18:29",
                                        familia_stop="tecnico", barras_stop_tecnico=10, alvo_multiplo=5.0)),
    ("A4 dia_todo_s/ult30min (09-18:00)", dict(janela_inicio="09:00", janela_fim="18:00",
                                                 familia_stop="tecnico", barras_stop_tecnico=10, alvo_multiplo=5.0)),
]


def _monta_estagio_b(janela: dict) -> list:
    base = dict(janela_inicio=janela["janela_inicio"], janela_fim=janela["janela_fim"], alvo_multiplo=5.0)
    return [
        ("B1 tecnico N=5", dict(**base, familia_stop="tecnico", barras_stop_tecnico=5)),
        ("B2 tecnico N=10", dict(**base, familia_stop="tecnico", barras_stop_tecnico=10)),
        ("B3 tecnico N=15", dict(**base, familia_stop="tecnico", barras_stop_tecnico=15)),
        ("B4 atr k=1,0 (M15,14)", dict(**base, familia_stop="atr", atr_periodo_m15=14, atr_multiplo=1.0)),
        ("B5 atr k=1,5 (M15,14)", dict(**base, familia_stop="atr", atr_periodo_m15=14, atr_multiplo=1.5)),
    ]


def _monta_estagio_c(janela: dict, stop: dict) -> list:
    base = dict(janela_inicio=janela["janela_inicio"], janela_fim=janela["janela_fim"])
    for k in ("familia_stop", "barras_stop_tecnico", "atr_periodo_m15", "atr_multiplo"):
        if k in stop:
            base[k] = stop[k]
    return [
        ("C1 alvo=3x", dict(**base, alvo_multiplo=3.0)),
        ("C2 alvo=5x", dict(**base, alvo_multiplo=5.0)),
        ("C3 alvo=7x", dict(**base, alvo_multiplo=7.0)),
    ]


def _worker(rotulo: str, kw: dict, dias: list):
    """Roda 1 variante num processo filho -- devolve so' dados picklable
    (nao o `IntradayBacktestResult` inteiro, que carrega objetos do motor)."""
    res = b.roda(dias, **kw)
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
        "seq-": str(c["seq_neg"]),
        "n_stop": str(c["n_stops"]),
        "pts/op": b.br(c["pontos_por_op"], 2),
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    return dict(
        rotulo=rotulo, kw=kw, c=c, linha=linha_res,
        equity_min=equity_min,
        ordens_recusadas=res.ordens_recusadas_por_capital,
        stop_dist_mediana=(sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2]
                            if c["stop_dist_pts"] else float("nan")),
    )


def _roda_estagio(nome_estagio: str, variantes: list, dias: list) -> list[dict]:
    print(f"\n--- {nome_estagio} ({len(variantes)} variantes, {MAX_WORKERS} workers) ---", flush=True)
    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, kw, dias): rot for rot, kw in variantes}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            c = r["c"]
            print(f"  {rot:<36} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
                  f"equity_min={b.br(r['equity_min']):>9}  "
                  f"stop_med_pts={b.br(r['stop_dist_mediana'],0)}",
                  flush=True)
    # devolve na ORDEM original da lista de variantes (nao na ordem de chegada)
    return [resultados[rot] for rot, _ in variantes]


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _melhor(resultados: list[dict]) -> dict:
    """Criterio: prefere NAO censurado com liquido>0; senao, maior liquido
    entre os nao censurados; senao, maior liquido mesmo censurado (so' para
    ter ALGUM vencedor a seguir para o proximo estagio -- a tabela final
    deixa claro se ele e' censurado)."""
    nao_censurados = [r for r in resultados if not _censurado(r)]
    pool = nao_censurados if nao_censurados else resultados
    return max(pool, key=lambda r: r["c"]["liquido"])


def main() -> None:
    from backtest.intraday.report import tabela

    df = b.carrega_df()
    dias = b.dias_da_janela(df, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 115)
    print("WinBuscaLucroG02R65 -- BUSCA no IS (jan-jun/2026), capital R$ %s (piso de partida real do WIN@)"
          % b.br(b.CAPITAL, 0))
    print("=" * 115)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE "
          "(queue_ahead_qty=0, exit_queue_ahead_qty=0).")
    print("Censura (para escolher o vencedor de cada estagio): 0 trades, OU >=50% dos pregoes sem "
          "trade, OU caixa minimo < margem crua (R$100).\n", flush=True)

    todas_as_linhas = []

    res_a = _roda_estagio("ESTAGIO A -- janela de horario", ESTAGIO_A, dias)
    todas_as_linhas += res_a
    vencedor_a = _melhor(res_a)
    print(f"\n  >> vencedor do estagio A: {vencedor_a['rotulo']} "
          f"(censurado={_censurado(vencedor_a)})", flush=True)

    estagio_b = _monta_estagio_b(vencedor_a["kw"])
    res_b = _roda_estagio("ESTAGIO B -- familia de stop", estagio_b, dias)
    todas_as_linhas += res_b
    vencedor_b = _melhor(res_b)
    print(f"\n  >> vencedor do estagio B: {vencedor_b['rotulo']} "
          f"(censurado={_censurado(vencedor_b)})", flush=True)

    estagio_c = _monta_estagio_c(vencedor_a["kw"], vencedor_b["kw"])
    res_c = _roda_estagio("ESTAGIO C -- multiplo do alvo", estagio_c, dias)
    todas_as_linhas += res_c
    vencedor_c = _melhor(res_c)
    print(f"\n  >> vencedor do estagio C: {vencedor_c['rotulo']} "
          f"(censurado={_censurado(vencedor_c)})", flush=True)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "seq-", "n_stop", "pts/op", "sem_tr")
    print("\n" + "=" * 115)
    print("TABELA CONSOLIDADA -- todas as variantes testadas no IS")
    print("=" * 115)
    print(tabela([r["linha"] for r in todas_as_linhas], extras=EXTRAS))

    print(f"\nVENCEDOR FINAL (congelar para OOS-1): {vencedor_c['rotulo']}")
    print(f"  kwargs = {vencedor_c['kw']}")
    cc = vencedor_c["c"]
    print(f"  liquido={b.br(cc['liquido'])}  trades={cc['n']}  win={b.br(100*cc['win'],1) if cc['n'] else '--'}%  "
          f"sem_trade={cc['sem_trade']}/{cc['pregoes']}  censurado={_censurado(vencedor_c)}  "
          f"stop_mediana_pts={b.br(vencedor_c['stop_dist_mediana'],0)}")

    print("\nGATE para OOS-1 (regra do protocolo): liquido > 0 E nao censurado.")
    passa = cc["liquido"] > 0 and not _censurado(vencedor_c)
    print(f"  -> {'PASSA (roda OOS-1)' if passa else 'NAO PASSA (morta no IS)'}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
