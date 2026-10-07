# -*- coding: utf-8 -*-
"""Geracao 15 (`WinBuscaLucroG15PortfolioOrcamento`) -- IS (jan-jun/2026).

Corrige o MECANISMO que a G14 diagnosticou: o portfolio OU-logico nao dilui
risco porque SOMA frequencia sobre o MESMO caixa nao-reposto (244 trades
contra 121-127 solo), mesmo com correlacao diaria ~0 entre as duas familias.
Esta geracao testa um ORCAMENTO DE EXPOSICAO fixo, do tamanho de UMA familia
sozinha (~121, o n do G8 solo no mesmo periodo) -- o portfolio ganha o
DIREITO as mesmas ~121 tentativas que uma familia sozinha teria.

Protocolo (ver `ORQUESTRACAO.md`, Geracao 15):
  0. Diagnostico de concentracao temporal (`g15_diagnostico.py`, ja' rodado
     separadamente -- resultado: NAO ha separacao limpa, as duas familias
     concentram nas mesmas 2 primeiras horas do pregao, score de corte
     1,036 de um maximo de 2,0). Reportado aqui de novo, resumido.
  1. Referencias: G8 solo, G4 solo, e o portfolio com orcamento ILIMITADO
     (reproduz G14 byte-a-byte, checado) -- todos no MESMO periodo.
  2. Politica (a) FIFO, orcamento UNICO para o semestre (121 = n do G8 solo;
     127 = n do G4 solo, sensibilidade).
  3. Politica (a) FIFO, orcamento MENSAL (reabastece todo mes, 20/mes ~=
     121 no semestre inteiro).
  4. Politica (b) por REGIME (corte de horario, EXPLORATORIO -- o
     diagnostico do passo 0 ja mostra que a premissa "ORB de manha, cruzado
     de tarde" nao se sustenta com limpeza; testado mesmo assim com o MELHOR
     corte achado por varredura, 10h, rotulado como fraco/exploratorio, nao
     como candidato pre-registrado).
  5. p_ruina (MC, `motor.ruina_mc`, caixa R$250, barreira R$100, horizonte=44
     operacoes projetadas) para TODAS as linhas -- a resposta direta a
     pergunta desta geracao.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g15_portfolio_orcamento/g15_is_busca.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g15_base as b  # noqa: E402

HORIZONTE_PREGOES = 44  # tamanho do OOS-1


def _trades_por_origem(res, strat) -> dict[str, list]:
    por_origem: dict[str, list] = {"orb": [], "cross": [], "desconhecida": []}
    for t in res.trades:
        origem = strat.origem_por_entry_ts.get(t.entry_ts, "desconhecida")
        por_origem.setdefault(origem, []).append(t)
    return por_origem


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela, LinhaResultado

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 175)
    print("WinBuscaLucroG15PortfolioOrcamento -- IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 175)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("Geometrias herdadas (nao retunadas): ORB(G8/G13) stop_max=140/alvo=3x/buffer=20; "
          "cruzado(G4) continuacao j=20/q=0.75/stop=150/alvo=3x/buffer=30\n", flush=True)

    print("--- Passo 0: diagnostico de concentracao temporal (resumo; ver g15_diagnostico.py) ---")
    print("  NAO ha separacao temporal limpa entre as familias: ambas concentram nas 2")
    print("  primeiras horas do pregao (orb 9-11h=63,7%, cross 9-11h=78,0%); melhor corte de")
    print("  hora encontrado por varredura (10h) tem score 1,036 de um maximo de 2,0 -- perto")
    print("  do que um corte aleatorio daria. A politica (b) abaixo e' testada mesmo assim,")
    print("  rotulada EXPLORATORIA/fraca, nao como candidato pre-registrado.\n", flush=True)

    # -- referencias: G8 solo, G4 solo, portfolio ILIMITADO (== G14) --------
    print("--- Passo 1: referencias (G8 solo, G4 solo, portfolio ILIMITADO = G14) ---", flush=True)
    res_g08, strat_g08 = b.roda_g08_solo(dias, **b.KWARGS_G08_SOLO)
    equity_min_g08 = float(res_g08.equity_curve.min()) if len(res_g08.equity_curve) else float("nan")
    resumo_g08 = b.resumo("G8 SOLO (ORB, referencia)", list(res_g08.trades), dias,
                           horizonte_pregoes=HORIZONTE_PREGOES)
    b.imprime_resumo(resumo_g08, equity_min_g08)

    res_g04, strat_g04 = b.roda_g04_solo(dias, **b.KWARGS_G04_SOLO)
    equity_min_g04 = float(res_g04.equity_curve.min()) if len(res_g04.equity_curve) else float("nan")
    resumo_g04 = b.resumo("G4 SOLO (cruzado, referencia)", list(res_g04.trades), dias,
                           horizonte_pregoes=HORIZONTE_PREGOES)
    b.imprime_resumo(resumo_g04, equity_min_g04)

    res_ilim, strat_ilim = b.roda_portfolio(
        dias, orcamento_modo="ilimitado", orcamento_valor=None, politica_prioridade="fifo",
        **b.KWARGS_GEOMETRIA)
    equity_min_ilim = float(res_ilim.equity_curve.min()) if len(res_ilim.equity_curve) else float("nan")
    resumo_ilim = b.resumo("PORTFOLIO ilimitado (= G14, controle)", list(res_ilim.trades), dias,
                            horizonte_pregoes=HORIZONTE_PREGOES)
    b.imprime_resumo(resumo_ilim, equity_min_ilim)
    print(f"  [checagem de reproducao] G14 registrado: liquido=+2.367,00 trades=244 -- "
          f"aqui: liquido={b.br(resumo_ilim['c']['liquido'])} trades={resumo_ilim['c']['n']} "
          f"{'(bate)' if resumo_ilim['c']['n'] == 244 else '(DIVERGE -- investigar)'}\n", flush=True)

    # -- politica (a): orcamento UNICO (semestre inteiro) --------------------
    print("--- Passo 2: politica (a) FIFO, orcamento UNICO (semestre) ---", flush=True)
    variantes_unico = []
    for valor, rotulo_sufixo in ((121, "=n(G8 solo)"), (127, "=n(G4 solo), sensibilidade")):
        res_u, strat_u = b.roda_portfolio(
            dias, orcamento_modo="unico", orcamento_valor=valor, politica_prioridade="fifo",
            **b.KWARGS_GEOMETRIA)
        equity_min_u = float(res_u.equity_curve.min()) if len(res_u.equity_curve) else float("nan")
        por_origem = _trades_por_origem(res_u, strat_u)
        rot = f"UNICO orc={valor} {rotulo_sufixo}"
        r = b.resumo(rot, list(res_u.trades), dias, horizonte_pregoes=HORIZONTE_PREGOES)
        b.imprime_resumo(r, equity_min_u)
        ultimo_trade = max((t.exit_ts for t in res_u.trades), default=None)
        print(f"      split origem: orb={len(por_origem['orb'])} cross={len(por_origem['cross'])}  "
              f"recusado_por_orcamento: orb={strat_u.stats_recusado_por_orcamento_orb} "
              f"cross={strat_u.stats_recusado_por_orcamento_cross}  "
              f"ultimo_trade={ultimo_trade}  fim_janela={dias[-1]}", flush=True)
        variantes_unico.append((rot, res_u, r, equity_min_u, strat_u, por_origem))

    # -- politica (a): orcamento MENSAL (reabastece) --------------------------
    print("\n--- Passo 3: politica (a) FIFO, orcamento MENSAL (reabastece todo mes) ---", flush=True)
    res_m, strat_m = b.roda_portfolio(
        dias, orcamento_modo="mensal", orcamento_valor=20, politica_prioridade="fifo",
        **b.KWARGS_GEOMETRIA)
    equity_min_m = float(res_m.equity_curve.min()) if len(res_m.equity_curve) else float("nan")
    por_origem_m = _trades_por_origem(res_m, strat_m)
    resumo_m = b.resumo("MENSAL orc=20/mes (~120/semestre)", list(res_m.trades), dias,
                         horizonte_pregoes=HORIZONTE_PREGOES)
    b.imprime_resumo(resumo_m, equity_min_m)
    ultimo_trade_m = max((t.exit_ts for t in res_m.trades), default=None)
    print(f"      split origem: orb={len(por_origem_m['orb'])} cross={len(por_origem_m['cross'])}  "
          f"recusado_por_orcamento: orb={strat_m.stats_recusado_por_orcamento_orb} "
          f"cross={strat_m.stats_recusado_por_orcamento_cross}  "
          f"ultimo_trade={ultimo_trade_m}  fim_janela={dias[-1]}", flush=True)

    # -- politica (b): por REGIME (exploratoria, corte=10h) --------------------
    print("\n--- Passo 4: politica (b) por REGIME (corte=10h, EXPLORATORIA) ---", flush=True)
    res_r, strat_r = b.roda_portfolio(
        dias, orcamento_modo="unico", orcamento_valor=121, politica_prioridade="regime",
        regime_corte_hora=10, **b.KWARGS_GEOMETRIA)
    equity_min_r = float(res_r.equity_curve.min()) if len(res_r.equity_curve) else float("nan")
    por_origem_r = _trades_por_origem(res_r, strat_r)
    resumo_r = b.resumo("REGIME corte=10h + orc.unico=121 (exploratoria)", list(res_r.trades), dias,
                         horizonte_pregoes=HORIZONTE_PREGOES)
    b.imprime_resumo(resumo_r, equity_min_r)
    ultimo_trade_r = max((t.exit_ts for t in res_r.trades), default=None)
    print(f"      split origem: orb={len(por_origem_r['orb'])} cross={len(por_origem_r['cross'])}  "
          f"recusado_por_regime: orb={strat_r.stats_recusado_por_regime_orb} "
          f"cross={strat_r.stats_recusado_por_regime_cross}  "
          f"recusado_por_orcamento: orb={strat_r.stats_recusado_por_orcamento_orb} "
          f"cross={strat_r.stats_recusado_por_orcamento_cross}  "
          f"ultimo_trade={ultimo_trade_r}  fim_janela={dias[-1]}", flush=True)

    # -- correlacao diaria (contexto, ja conhecida da G14, recomputada aqui) -
    print("\n--- Passo 5 (contexto): correlacao diaria G8 solo x G4 solo (mesmo metodo da G14) ---", flush=True)
    serie_g08 = b.serie_diaria(list(res_g08.trades), dias)
    serie_g04 = b.serie_diaria(list(res_g04.trades), dias)
    corr = float(np.corrcoef(serie_g08.values, serie_g04.values)[0, 1])
    print(f"  Pearson(P&L_diario_G8, P&L_diario_G4) = {corr:.4f}  (G14 registrou 0,0117)", flush=True)

    # -- p_ruina: TODAS as linhas, a resposta direta da geracao ----------------
    print(f"\n--- Passo 6: p_ruina (MC, R$250->R$100, horizonte={HORIZONTE_PREGOES} ops projetadas) "
          f"-- RESPOSTA DECISIVA ---", flush=True)
    todas = [resumo_g08, resumo_g04, resumo_ilim] + [v[2] for v in variantes_unico] + [resumo_m, resumo_r]
    for r in todas:
        ru = r["ruina"]
        print(f"  {r['rotulo']:<42} p_ruina(MC)={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>6}%  "
              f"n_ops_proj={ru['n_ops']}  trades_IS={r['c']['n']}")

    pior_individual = max(resumo_g08["ruina"]["p_ruina"], resumo_g04["ruina"]["p_ruina"])
    melhor_individual = min(resumo_g08["ruina"]["p_ruina"], resumo_g04["ruina"]["p_ruina"])
    print(f"\n  referencia: pior familia solo (G4)={b.br(100*pior_individual,1)}%  "
          f"melhor familia solo (G8)={b.br(100*melhor_individual,1)}%  "
          f"portfolio ILIMITADO (G14)={b.br(100*resumo_ilim['ruina']['p_ruina'],1)}%")
    for rot, _, r, _, _, _ in variantes_unico:
        p = r["ruina"]["p_ruina"]
        print(f"  {rot:<42} p_ruina={b.br(100*p,1)}%  "
              f"< pior_individual? {p < pior_individual}   <= melhor_individual? {p <= melhor_individual}")
    p_m = resumo_m["ruina"]["p_ruina"]
    print(f"  {'MENSAL orc=20/mes':<42} p_ruina={b.br(100*p_m,1)}%  "
          f"< pior_individual? {p_m < pior_individual}   <= melhor_individual? {p_m <= melhor_individual}")
    p_r = resumo_r["ruina"]["p_ruina"]
    print(f"  {'REGIME corte=10h (exploratoria)':<42} p_ruina={b.br(100*p_r,1)}%  "
          f"< pior_individual? {p_r < pior_individual}   <= melhor_individual? {p_r <= melhor_individual}")

    # -- tabela padrao (12 colunas + extras) -----------------------------------
    print("\n" + "=" * 175)
    print("TABELA PADRAO")
    print("=" * 175)
    linhas = []
    for (rotulo, res_obj, r, eqmin) in (
        ("G8 SOLO (ORB, referencia)", res_g08, resumo_g08, equity_min_g08),
        ("G4 SOLO (cruzado, referencia)", res_g04, resumo_g04, equity_min_g04),
        ("PORTFOLIO ilimitado (=G14)", res_ilim, resumo_ilim, equity_min_ilim),
        *((rot, res_u, r, eqmin) for (rot, res_u, r, eqmin, _, _) in variantes_unico),
        ("MENSAL orc=20/mes", res_m, resumo_m, equity_min_m),
        ("REGIME corte=10h (exploratoria)", res_r, resumo_r, equity_min_r),
    ):
        c = r["c"]
        ru = r["ruina"]
        extras = {
            "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
            "veredito": c["veredito"],
            "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
            "p_ruina(MC)": (b.br(100 * ru["p_ruina"], 1) + "%") if ru["p_ruina"] == ru["p_ruina"] else "--",
            "pior_seq_perdas": f"{r['pior_seq_n']} (R${b.br(r['pior_seq_brl'])})",
            "censurado": str(b.censurado(c, eqmin)),
        }
        linhas.append(linha_de_resultado(rotulo, res_obj, b.CAPITAL, extras=extras))

    print(tabela(linhas, extras=("BEemp%", "veredito", "top3/liq", "p_ruina(MC)",
                                  "pior_seq_perdas", "censurado"), largura_extra=13))

    print("\nFIM.")


if __name__ == "__main__":
    main()
