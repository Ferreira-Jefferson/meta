# -*- coding: utf-8 -*-
"""Geracao 17 (`WinBuscaLucroG17CrossWdoCapital1000`) -- BUSCA no IS (jan-jun/2026).

Mandato do dono, 2026-10-05 (ver `ORQUESTRACAO.md`, secao "Decisao do dono"):
reabre a busca com DUAS portas, so' nesta linha:
  1. Capital de teste = R$1.000 (nao R$250).
  2. `alvo_multiplo` vira grade {2x, 2,5x, 3x, 4x, 5x} (piso antigo era 3x
     fixo). Nunca <=1x (perder>=ganhar continua proibido).

Reaproveita a deteccao do estado anomalo cruzado da G4 (`estado_anomalo_
cruzado`, j=20min/q=0,75/continuacao -- ja identificados como o melhor ponto
no IS original, NAO retunados aqui) e so' RETUNA a geometria: grade 2D
completa `alvo_multiplo` x `stop_pontos`, buffer_entrada=30 (vencedor da G4,
fixo). 1 contrato FIXO (isola o efeito de alvo/stop primeiro -- escalar
contrato por caixa fica para a G19, mandato explicito).

Para cada celula: liquido, trades, win%, BE nominal/empirico, IC95,
concentracao top-3/top-5, pregoes distintos com trade, p_ruina (Monte Carlo,
caixa=R$1.000, piso=margem crua R$100), maior sequencia de perdas.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g17_capital1000/g17_is_busca.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g17_base as b  # noqa: E402

MAX_WORKERS = 4

#: Vencedor da G4 (nao retunado aqui -- mandato: reaproveitar a deteccao).
JANELA_MIN = 20
QUANTIL = 0.75
DIRECAO_APOSTA = "continuacao"
BUFFER_ENTRADA = 30.0

ALVOS = (2.0, 2.5, 3.0, 4.0, 5.0)
STOPS = (100.0, 150.0, 200.0)

GRADE = [
    (f"alvo={alvo:.1f}x stop={stop:.0f}",
     dict(direcao_aposta=DIRECAO_APOSTA, stop_pontos=stop, alvo_multiplo=alvo,
          buffer_entrada_pontos=BUFFER_ENTRADA))
    for stop in STOPS
    for alvo in ALVOS
]


def _worker(rotulo: str, kw: dict, dias: list):
    """Roda 1 celula num processo filho -- devolve so' dados picklable."""
    res, strat = b.roda(dias, dias_historico=dias, janela_min=JANELA_MIN,
                         quantil=QUANTIL, capital=b.CAPITAL, **kw)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), caixa=b.CAPITAL)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    from backtest.intraday.report import linha_de_resultado
    be_nom = 1.0 / (1.0 + kw["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "p_ruina": (b.br(100 * ru["p_ruina"], 1) + "%") if ru["p_ruina"] == ru["p_ruina"] else "--",
        "pior_seq": f"{pior_seq_n} (R${b.br(pior_seq_brl)})",
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
        "bruto": str(strat.stats_bruto),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
    }
    linha_res = linha_de_resultado(rotulo, res, b.CAPITAL, extras=extras)
    return dict(
        rotulo=rotulo, kw=kw, c=c, linha=linha_res, equity_min=equity_min,
        ordens_recusadas=res.ordens_recusadas_por_capital, ruina=ru, top5=top5,
        pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl,
        bruto=strat.stats_bruto, emitidas=strat.stats_ordens_emitidas,
        stop_dist_mediana=(sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2]
                            if c["stop_dist_pts"] else float("nan")),
    )


def _censurado_capital(r: dict) -> bool:
    return bool(r["ordens_recusadas"] > 0) or r["equity_min"] < b.MARGEM_WIN_BRL


def _censurado_amostra(r: dict) -> bool:
    c = r["c"]
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"]


def main() -> None:
    from backtest.intraday.report import tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 150)
    print("WinBuscaLucroG17CrossWdoCapital1000 -- BUSCA no IS (jan-jun/2026), "
          f"capital de TESTE R$ {b.br(b.CAPITAL, 0)} (mandato do dono, 2026-10-05)")
    print("=" * 150)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print(f"Deteccao herdada da G4 (NAO retunada): janela={JANELA_MIN}min  quantil={QUANTIL}  "
          f"direcao={DIRECAO_APOSTA}  buffer_entrada={BUFFER_ENTRADA}pts")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE "
          "(queue_ahead_qty=0, exit_queue_ahead_qty=0). 1 contrato FIXO (escalar fica para a G19).")
    print("Censura separada (item 6.51): capital (ordens recusadas OU equity_min<margem crua) "
          "x amostra (0 trades OU >=50% pregoes sem trade) -- reportadas em colunas distintas.\n", flush=True)

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_worker, rot, dict(kw), dias): rot for rot, kw in GRADE}
        resultados: dict[str, dict] = {}
        for fut in as_completed(futs):
            rot = futs[fut]
            r = fut.result()
            resultados[rot] = r
            c = r["c"]
            print(f"  {rot:<20} liquido={b.br(c['liquido']):>11}  trades={c['n']:>4}  "
                  f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
                  f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
                  f"veredito={c['veredito']:<10}  "
                  f"p_ruina={b.br(100*r['ruina']['p_ruina'],1) if r['ruina']['p_ruina']==r['ruina']['p_ruina'] else '--':>5}%  "
                  f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
                  f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
                  f"equity_min={b.br(r['equity_min']):>9}  "
                  f"cens_cap={_censurado_capital(r)}  cens_amostra={_censurado_amostra(r)}",
                  flush=True)

    linhas_ordenadas = [resultados[rot] for rot, _ in GRADE]
    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "top3/liq", "top5/liq",
              "p_ruina", "pior_seq", "sem_tr", "bruto", "emit/brt")
    print("\n" + "=" * 150)
    print("TABELA CONSOLIDADA -- grade completa alvo_multiplo x stop_pontos, IS, capital R$1.000")
    print("=" * 150)
    print(tabela([r["linha"] for r in linhas_ordenadas], extras=EXTRAS, largura_extra=10))

    # Criterio composto (item 5 do mandato): liquido>0, nao censurado (capital
    # E amostra), win%/IC95 favoravel (idealmente POSITIVO), p_ruina baixa.
    candidatos = [r for r in linhas_ordenadas
                  if r["c"]["liquido"] > 0
                  and not _censurado_capital(r) and not _censurado_amostra(r)
                  and r["c"]["veredito"] != "NEGATIVO"]
    print(f"\nCelulas que batem o portao basico (liquido>0, nao censurada, veredito != NEGATIVO): "
          f"{len(candidatos)}/{len(linhas_ordenadas)}")
    for r in sorted(candidatos, key=lambda r: r["ruina"]["p_ruina"] if r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] else 1.0):
        c = r["c"]
        print(f"  {r['rotulo']:<20} liquido={b.br(c['liquido']):>11}  win={b.br(100*c['win'],1):>6}%  "
              f"veredito={c['veredito']:<10}  p_ruina={b.br(100*r['ruina']['p_ruina'],1):>5}%  "
              f"top3/liq={b.br(100*c['concentracao_top3'],0):>5}%")

    if candidatos:
        vencedor = sorted(candidatos, key=lambda r: r["ruina"]["p_ruina"] if r["ruina"]["p_ruina"] == r["ruina"]["p_ruina"] else 1.0)[0]
        print(f"\nVENCEDOR DO IS (menor p_ruina entre os candidatos que batem o portao): {vencedor['rotulo']}")
        print(f"  kwargs = {vencedor['kw']}")
    else:
        print("\nNENHUMA celula bate o portao basico -- ver tabela acima para o padrao de falha.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
