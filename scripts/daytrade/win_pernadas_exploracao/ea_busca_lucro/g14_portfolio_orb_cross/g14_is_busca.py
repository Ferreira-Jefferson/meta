# -*- coding: utf-8 -*-
"""Geracao 14 (`WinBuscaLucroG14PortfolioOrbCross`) -- IS (jan-jun/2026).

Mandato do COORDENADOR: alavanca (4), a ULTIMA das 4 pedidas -- portfolio/
ALTERNANCIA entre a familia ORB momentum (G8/G13) e a familia de confirmacao
cruzada WIN x WDO (G4), compartilhando o MESMO caixa SEQUENCIALMENTE (OU
logico, nunca 2 posicoes/ordens simultaneas -- ver docstring da classe).
Geometrias herdadas (vencedoras de cada familia), NAO retunadas aqui -- esta
geracao testa o MECANISMO de alternancia, nao parametro novo.

Protocolo em 3 passos:
  1. Roda o PORTFOLIO combinado + as DUAS familias SOLO no MESMO periodo
     (IS), para a comparacao ser sobre o MESMO conjunto de pregoes.
  2. Mede a CORRELACAO diaria entre as duas series SOLO (pergunta central:
     as duas tendem a perder nos MESMOS dias?).
  3. Calcula p_ruina (MC, `motor.ruina_mc`, caixa R$250, barreira R$100)
     para as TRES series (combinado, G8 solo, G4 solo) -- a resposta direta
     a pergunta desta geracao: p_ruina(combinado) < p_ruina(pior individual)?

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g14_portfolio_orb_cross/g14_is_busca.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g14_base as b  # noqa: E402

HORIZONTE_PREGOES = 44  # tamanho do OOS-1


def _trades_por_origem(res, strat) -> dict[str, list]:
    """Separa `res.trades` pela origem gravada em
    `strat.origem_por_entry_ts` (ver docstring da classe -- o motor nao
    carrega `reason` em `IntradayTrade`, entao a estrategia grava a origem
    no momento do FILL e o harness casa por `entry_ts`)."""
    por_origem: dict[str, list] = {"orb": [], "cross": [], "desconhecida": []}
    for t in res.trades:
        origem = strat.origem_por_entry_ts.get(t.entry_ts, "desconhecida")
        por_origem.setdefault(origem, []).append(t)
    return por_origem


def _resumo(rotulo: str, trades: list, dias: list, capital: float = b.CAPITAL) -> dict:
    c = b.consistencia(trades, dias)
    top5 = b.concentracao_topn(c["serie"], 5)
    ruina = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), horizonte_pregoes=HORIZONTE_PREGOES)
    const = b.constancia_motor(trades)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    return dict(rotulo=rotulo, c=c, top5=top5, ruina=ruina, const=const,
                pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, trades=trades)


def _censurado(c: dict, equity_min: float) -> bool:
    return c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or equity_min < b.MARGEM_WIN_BRL


def _imprime_resumo(r: dict, equity_min: float) -> None:
    c = r["c"]
    ru = r["ruina"]
    print(f"  {r['rotulo']:<26} liquido={b.br(c['liquido']):>11}  trades={c['n']:>4}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>6}%  "
          f"veredito={c['veredito']:<10}  "
          f"p_ruina={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>5}%  "
          f"top3/liq={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--':>5}%  "
          f"pior_seq={r['pior_seq_n']:>2} (R${b.br(r['pior_seq_brl'])})  "
          f"censurado={_censurado(c, equity_min)}", flush=True)


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print("=" * 170)
    print("WinBuscaLucroG14PortfolioOrbCross -- IS (jan-jun/2026), capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 170)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.")
    print("Geometrias herdadas (nao retunadas): ORB(G8/G13) stop_max=140/alvo=3x/buffer=20; "
          "cruzado(G4) continuacao j=20/q=0.75/stop=150/alvo=3x/buffer=30")
    print("Prioridade de empate na MESMA barra: ORB vence (ver docstring da classe).\n", flush=True)

    # -- (1) roda o PORTFOLIO combinado ------------------------------------
    print("--- Passo 1a: PORTFOLIO combinado (G14) ---", flush=True)
    res_pf, strat_pf = b.roda_portfolio(dias, **b.KWARGS_G14_VENCEDOR)
    trades_pf = list(res_pf.trades)
    equity_min_pf = float(res_pf.equity_curve.min()) if len(res_pf.equity_curve) else float("nan")
    por_origem = _trades_por_origem(res_pf, strat_pf)
    resumo_pf = _resumo("PORTFOLIO (combinado)", trades_pf, dias)
    resumo_pf_orb = _resumo("  -- origem ORB", por_origem["orb"], dias)
    resumo_pf_cross = _resumo("  -- origem cruzado", por_origem["cross"], dias)
    _imprime_resumo(resumo_pf, equity_min_pf)
    _imprime_resumo(resumo_pf_orb, equity_min_pf)
    _imprime_resumo(resumo_pf_cross, equity_min_pf)
    if por_origem["desconhecida"]:
        print(f"  AVISO: {len(por_origem['desconhecida'])} trades sem origem identificada "
              f"(bug de rastreio) -- investigar antes de aceitar qualquer numero.", flush=True)
    print(f"  stats estrategia: bruto_orb={strat_pf.stats_bruto_orb} "
          f"bruto_cross={strat_pf.stats_bruto_cross} "
          f"orb_ja_operou_hoje={strat_pf.stats_orb_ja_operou_hoje} "
          f"cross_contra_tendencia={strat_pf.stats_cross_contra_tendencia} "
          f"cross_perdeu_empate_pra_orb={strat_pf.stats_cross_perdeu_empate_pra_orb} "
          f"emitidas_orb={strat_pf.stats_ordens_emitidas_orb} "
          f"emitidas_cross={strat_pf.stats_ordens_emitidas_cross}", flush=True)

    # -- (1b) roda CADA familia SOLO no MESMO periodo -----------------------
    print("\n--- Passo 1b: familias SOLO (mesmo periodo, mesmo metodo) ---", flush=True)
    res_g08, strat_g08 = b.roda_g08_solo(dias, **b.KWARGS_G08_SOLO)
    equity_min_g08 = float(res_g08.equity_curve.min()) if len(res_g08.equity_curve) else float("nan")
    resumo_g08 = _resumo("G8 SOLO (ORB)", list(res_g08.trades), dias)
    _imprime_resumo(resumo_g08, equity_min_g08)

    res_g04, strat_g04 = b.roda_g04_solo(dias, **b.KWARGS_G04_SOLO)
    equity_min_g04 = float(res_g04.equity_curve.min()) if len(res_g04.equity_curve) else float("nan")
    resumo_g04 = _resumo("G4 SOLO (cruzado)", list(res_g04.trades), dias)
    _imprime_resumo(resumo_g04, equity_min_g04)

    # -- (2) correlacao diaria entre as DUAS series SOLO ---------------------
    print("\n--- Passo 2: correlacao diaria entre as duas familias (series SOLO) ---", flush=True)
    serie_g08 = b.serie_diaria(list(res_g08.trades), dias)
    serie_g04 = b.serie_diaria(list(res_g04.trades), dias)
    ambos_zero = int(((serie_g08 == 0) & (serie_g04 == 0)).sum())
    so_g08 = int(((serie_g08 != 0) & (serie_g04 == 0)).sum())
    so_g04 = int(((serie_g08 == 0) & (serie_g04 != 0)).sum())
    ambos_nao_zero = int(((serie_g08 != 0) & (serie_g04 != 0)).sum())
    corr = float(np.corrcoef(serie_g08.values, serie_g04.values)[0, 1])
    g08_perde = serie_g08 < 0
    g04_perde = serie_g04 < 0
    ambos_perdem = int((g08_perde & g04_perde).sum())
    so_g08_perde = int((g08_perde & ~g04_perde).sum())
    so_g04_perde = int((~g08_perde & g04_perde).sum())
    n_g08_perde = int(g08_perde.sum())
    n_g04_perde = int(g04_perde.sum())
    print(f"  n={len(dias)} pregoes. Pearson(P&L_diario_G8, P&L_diario_G4) = {corr:.4f}")
    print(f"  dias com os 2 zerados={ambos_zero}  so' G8 operou={so_g08}  so' G4 operou={so_g04}  "
          f"os 2 operaram={ambos_nao_zero}")
    print(f"  dias em que G8 perde={n_g08_perde} (dos quais G4 TAMBEM perde no mesmo dia={ambos_perdem}, "
          f"{b.br(100*ambos_perdem/n_g08_perde,1) if n_g08_perde else float('nan')}%)")
    print(f"  dias em que G4 perde={n_g04_perde} (dos quais G8 TAMBEM perde no mesmo dia={ambos_perdem}, "
          f"{b.br(100*ambos_perdem/n_g04_perde,1) if n_g04_perde else float('nan')}%)")
    print(f"  so' G8 perde (G4 nao perde nesse dia)={so_g08_perde}  so' G4 perde={so_g04_perde}", flush=True)

    # -- (3) p_ruina: combinado x G8 solo x G4 solo --------------------------
    print("\n--- Passo 3: p_ruina (MC, R$250->R$100, horizonte=%d ops projetadas) ---" % HORIZONTE_PREGOES, flush=True)
    for r, eqmin in ((resumo_pf, equity_min_pf), (resumo_g08, equity_min_g08), (resumo_g04, equity_min_g04)):
        ru = r["ruina"]
        print(f"  {r['rotulo']:<22} p_ruina(MC)={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--':>6}%  "
              f"ruina_formula(Lundberg)={b.br(100*ru['ruina_formula'],1) if ru['ruina_formula']==ru['ruina_formula'] else '--':>6}%  "
              f"n_ops_projetadas={ru['n_ops']}")

    pior_individual = max(resumo_g08["ruina"]["p_ruina"], resumo_g04["ruina"]["p_ruina"])
    p_combinado = resumo_pf["ruina"]["p_ruina"]
    print(f"\n  RESPOSTA DA GERACAO: p_ruina(combinado)={b.br(100*p_combinado,1)}%  "
          f"x  p_ruina(pior individual)={b.br(100*pior_individual,1)}%  "
          f"reducao={b.br(100*(pior_individual-p_combinado),1)}pp  "
          f"combinado < pior individual? {p_combinado < pior_individual}")

    # -- tabela padrao (12 colunas + extras) ---------------------------------
    print("\n" + "=" * 170)
    print("TABELA PADRAO")
    print("=" * 170)
    linhas = []
    for (rotulo, res_obj, r, eqmin) in (
        ("PORTFOLIO combinado (G14)", res_pf, resumo_pf, equity_min_pf),
        ("  origem ORB (dentro do G14)", None, resumo_pf_orb, equity_min_pf),
        ("  origem cruzado (dentro do G14)", None, resumo_pf_cross, equity_min_pf),
        ("G8 SOLO (ORB)", res_g08, resumo_g08, equity_min_g08),
        ("G4 SOLO (cruzado)", res_g04, resumo_g04, equity_min_g04),
    ):
        c = r["c"]
        ru = r["ruina"]
        extras = {
            "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
            "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
            "veredito": c["veredito"],
            "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
            "top5/liq": (b.br(100 * r["top5"], 0) + "%") if r["top5"] == r["top5"] else "--",
            "pregoes c/trade": f"{c['com_trade']}/{c['pregoes']}",
            "p_ruina(MC)": (b.br(100 * ru["p_ruina"], 1) + "%") if ru["p_ruina"] == ru["p_ruina"] else "--",
            "pior_seq_perdas": f"{r['pior_seq_n']} (R${b.br(r['pior_seq_brl'])})",
            "censurado": str(_censurado(c, eqmin)),
        }
        if res_obj is not None:
            linhas.append(linha_de_resultado(rotulo, res_obj, b.CAPITAL, extras=extras))
        else:
            # subconjunto por origem -- nao tem `res`/equity curve PROPRIA (a
            # equity curve e' a do portfolio combinado, as duas origens
            # compartilham o mesmo caixa sequencial). Linha INFORMATIVA, nao
            # uma run independente: MaxDD/retorno/capital saem em branco de
            # proposito (ver `aviso`), so' liquido/trades/win%/R$-dia valem.
            from backtest.intraday.report import LinhaResultado
            liquido = c["liquido"]
            n_trades = c["n"]
            pregoes_com_dado = c["pregoes"]
            linhas.append(LinhaResultado(
                variante=rotulo, retorno_pct=None, liquido_brl=liquido, maxdd_pct=None,
                maxdd_brl=0.0, win_rate_pct=(100 * c["win"] if c["n"] else 0.0),
                trades=n_trades, capital_final=None, pregoes=pregoes_com_dado,
                extras=extras, aviso="subset informativo, nao e' run independente",
            ))

    print(tabela(linhas, extras=("BEemp%", "IC95 win", "veredito", "top3/liq", "top5/liq",
                                  "pregoes c/trade", "p_ruina(MC)", "pior_seq_perdas", "censurado"),
                 largura_extra=13))

    print("\nFIM.")


if __name__ == "__main__":
    main()
