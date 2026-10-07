# -*- coding: utf-8 -*-
"""Geracao 3 (`WinBuscaLucroG03RecuoRaso`) -- BUSCA no IS (jan-jun/2026).

R57 (recuo raso, 1o fundo em 23-38% do avanco) + filtros R59 (fundos
ascendentes/descendentes entre pernas) e R58 (janela de horario como
parametro). Cinco estagios, cada um fixando o vencedor do anterior:

  Estagio A -- 4 combinacoes de filtro (R57 so' / R57+R59 / R57+horario /
               R57+R59+horario), geometria fixa (T=750, m=10, alvo=5x).
  Estagio B -- T da perna de referencia (500 / 750) na combinacao vencedora
               do estagio A.
  Estagio C -- m (0 / 10 / 20 pontos) no T vencedor do estagio B.
  Estagio D -- alvo_multiplo (3x / 5x / 7x) no T+m vencedores de B+C.
  Estagio E -- janela de horario (sem filtro / 11:00-13:00 / 09:00-11:00),
               mantendo o `usar_filtro_r59` vencedor do estagio A e a
               geometria vencedora de B+C+D -- isola o efeito do horario
               mesmo quando o estagio A nao o escolheu, para nao deixar a
               pergunta sem resposta.

Tudo dentro do IS -- nenhum numero de jul/2026 em diante e' olhado aqui.
Capital R$250,00 (piso de PARTIDA real do WIN@). Fila zero nos dois lados
(WIN@ sem fidelidade calibrada), premissa otimista declarada.

Conta TAMBEM as ocorrencias BRUTAS do gatilho R57 (antes de qualquer filtro
de execucao/capital/pode_armar) ao lado das ordens de fato emitidas -- e' o
teste que teria pego mais cedo o bug de ordem-de-operacoes da Geracao 2 (ver
docstring de `WinBuscaLucroG03RecuoRaso`).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g03_recuo_raso/g03_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g03_base as b  # noqa: E402

MAX_WORKERS = 4

GEOMETRIA_BASE = dict(pernada_pontos=750.0, m_pontos=10.0, alvo_multiplo=5.0)

ESTAGIO_A = [
    ("A1 R57 so'", dict(**GEOMETRIA_BASE, usar_filtro_r59=False,
                         janela_inicio="00:00", janela_fim="23:59")),
    ("A2 R57+R59", dict(**GEOMETRIA_BASE, usar_filtro_r59=True,
                         janela_inicio="00:00", janela_fim="23:59")),
    ("A3 R57+horario(11-13)", dict(**GEOMETRIA_BASE, usar_filtro_r59=False,
                                    janela_inicio="11:00", janela_fim="13:00")),
    ("A4 R57+R59+horario(11-13)", dict(**GEOMETRIA_BASE, usar_filtro_r59=True,
                                        janela_inicio="11:00", janela_fim="13:00")),
]


def _monta_estagio_b(vencedor_a: dict) -> list:
    base = dict(vencedor_a)
    base.pop("pernada_pontos", None)
    return [
        ("B1 T=500", dict(**base, pernada_pontos=500.0)),
        ("B2 T=750", dict(**base, pernada_pontos=750.0)),
    ]


def _monta_estagio_c(vencedor_b: dict) -> list:
    base = dict(vencedor_b)
    base.pop("m_pontos", None)
    return [
        ("C1 m=0", dict(**base, m_pontos=0.0)),
        ("C2 m=10", dict(**base, m_pontos=10.0)),
        ("C3 m=20", dict(**base, m_pontos=20.0)),
    ]


def _monta_estagio_d(vencedor_c: dict) -> list:
    base = dict(vencedor_c)
    base.pop("alvo_multiplo", None)
    return [
        ("D1 alvo=3x", dict(**base, alvo_multiplo=3.0)),
        ("D2 alvo=5x", dict(**base, alvo_multiplo=5.0)),
        ("D3 alvo=7x", dict(**base, alvo_multiplo=7.0)),
    ]


def _monta_estagio_e(vencedor_d: dict) -> list:
    base = dict(vencedor_d)
    base.pop("janela_inicio", None)
    base.pop("janela_fim", None)
    return [
        ("E1 sem_filtro (00-23:59)", dict(**base, janela_inicio="00:00", janela_fim="23:59")),
        ("E2 11:00-13:00", dict(**base, janela_inicio="11:00", janela_fim="13:00")),
        ("E3 09:00-11:00", dict(**base, janela_inicio="09:00", janela_fim="11:00")),
    ]


def _worker(rotulo: str, kw: dict, dias: list):
    """Roda 1 variante num processo filho -- devolve so' dados picklable."""
    res, strat = b.roda(dias, **kw)
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
        "bruto": str(strat.stats_bruto_r57),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto_r57}",
        "pts/op": b.br(c["pontos_por_op"], 2),
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    return dict(
        rotulo=rotulo, kw=kw, c=c, linha=linha_res,
        equity_min=equity_min,
        ordens_recusadas=res.ordens_recusadas_por_capital,
        bruto=strat.stats_bruto_r57, emitidas=strat.stats_ordens_emitidas,
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
            print(f"  {rot:<28} liquido={b.br(c['liquido']):>10}  bruto={r['bruto']:>4}  "
                  f"emitidas={r['emitidas']:>4}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
                  f"equity_min={b.br(r['equity_min']):>9}  "
                  f"stop_med_pts={b.br(r['stop_dist_mediana'],0)}",
                  flush=True)
    return [resultados[rot] for rot, _ in variantes]


def _censurado(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or r["equity_min"] < b.MARGEM_WIN_BRL


def _melhor(resultados: list[dict]) -> dict:
    """Mesmo criterio de `g02_is_busca._melhor`: prefere NAO censurado com
    liquido>0; senao, maior liquido entre os nao censurados; senao, maior
    liquido mesmo censurado (so' para seguir para o proximo estagio)."""
    nao_censurados = [r for r in resultados if not _censurado(r)]
    pool = nao_censurados if nao_censurados else resultados
    return max(pool, key=lambda r: r["c"]["liquido"])


def main() -> None:
    from backtest.intraday.report import tabela

    df = b.carrega_df()
    dias = b.dias_da_janela(df, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 125)
    print("WinBuscaLucroG03RecuoRaso -- BUSCA no IS (jan-jun/2026), capital R$ %s (piso de partida real do WIN@)"
          % b.br(b.CAPITAL, 0))
    print("=" * 125)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE "
          "(queue_ahead_qty=0, exit_queue_ahead_qty=0).")
    print("Censura (para escolher o vencedor de cada estagio): 0 trades, OU >=50% dos pregoes sem "
          "trade, OU caixa minimo < margem crua (R$100).\n", flush=True)

    todas_as_linhas = []

    res_a = _roda_estagio("ESTAGIO A -- combinacao de filtros", ESTAGIO_A, dias)
    todas_as_linhas += res_a
    vencedor_a = _melhor(res_a)
    print(f"\n  >> vencedor do estagio A: {vencedor_a['rotulo']} "
          f"(censurado={_censurado(vencedor_a)})", flush=True)

    estagio_b = _monta_estagio_b(vencedor_a["kw"])
    res_b = _roda_estagio("ESTAGIO B -- T da perna de referencia", estagio_b, dias)
    todas_as_linhas += res_b
    vencedor_b = _melhor(res_b)
    print(f"\n  >> vencedor do estagio B: {vencedor_b['rotulo']} "
          f"(censurado={_censurado(vencedor_b)})", flush=True)

    estagio_c = _monta_estagio_c(vencedor_b["kw"])
    res_c = _roda_estagio("ESTAGIO C -- m (pontos acima do fundo)", estagio_c, dias)
    todas_as_linhas += res_c
    vencedor_c = _melhor(res_c)
    print(f"\n  >> vencedor do estagio C: {vencedor_c['rotulo']} "
          f"(censurado={_censurado(vencedor_c)})", flush=True)

    estagio_d = _monta_estagio_d(vencedor_c["kw"])
    res_d = _roda_estagio("ESTAGIO D -- multiplo do alvo", estagio_d, dias)
    todas_as_linhas += res_d
    vencedor_d = _melhor(res_d)
    print(f"\n  >> vencedor do estagio D: {vencedor_d['rotulo']} "
          f"(censurado={_censurado(vencedor_d)})", flush=True)

    estagio_e = _monta_estagio_e(vencedor_d["kw"])
    res_e = _roda_estagio("ESTAGIO E -- janela de horario (isolando o efeito)", estagio_e, dias)
    todas_as_linhas += res_e
    vencedor_e = _melhor(res_e)
    print(f"\n  >> vencedor do estagio E: {vencedor_e['rotulo']} "
          f"(censurado={_censurado(vencedor_e)})", flush=True)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "seq-", "bruto", "emit/brt", "pts/op", "sem_tr")
    print("\n" + "=" * 125)
    print("TABELA CONSOLIDADA -- todas as variantes testadas no IS")
    print("=" * 125)
    print(tabela([r["linha"] for r in todas_as_linhas], extras=EXTRAS, largura_extra=10))

    vencedor_final = vencedor_e
    print(f"\nVENCEDOR FINAL (congelar para OOS-1): {vencedor_final['rotulo']}")
    print(f"  kwargs = {vencedor_final['kw']}")
    cc = vencedor_final["c"]
    print(f"  liquido={b.br(cc['liquido'])}  bruto={vencedor_final['bruto']}  emitidas={vencedor_final['emitidas']}  "
          f"trades={cc['n']}  win={b.br(100*cc['win'],1) if cc['n'] else '--'}%  "
          f"sem_trade={cc['sem_trade']}/{cc['pregoes']}  censurado={_censurado(vencedor_final)}  "
          f"stop_mediana_pts={b.br(vencedor_final['stop_dist_mediana'],0)}")

    print("\nGATE para OOS-1 (regra do protocolo): liquido > 0 E nao censurado.")
    passa = cc["liquido"] > 0 and not _censurado(vencedor_final)
    print(f"  -> {'PASSA (roda OOS-1)' if passa else 'NAO PASSA (morta no IS)'}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
