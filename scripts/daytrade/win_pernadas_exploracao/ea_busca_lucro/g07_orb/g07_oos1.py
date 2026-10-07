# -*- coding: utf-8 -*-
"""Geracao 7 (`WinBuscaLucroG07Orb`) -- OOS-1 (jul-ago/2026), RODA UMA VEZ.

Vencedor do IS (congelado em
`win_busca_lucro_g07_orb_congelado_v07.py` ANTES desta rodada):
range_minutos=5min, stop_min_pontos=100, stop_max_pontos=250,
alvo_multiplo=5x, buffer_entrada_pontos=20, ttl_barras_entrada=10.
IS: liquido=+R$2.685,50, 121 trades, win=24,8% (BEnom 16,7%, BEemp 17,4%,
IC95[18,0;33,2] -- POSITIVO por margem apertada, 0,6pp), 121/122 pregoes com
trade, top3/liquido=28%, top5/liquido=46%, equity_min=R$132,00 (nao
censurado), stop mediano 255 pontos (>=100 -- item 6.47 nao exige checagem
com ticks).

O ORB nao depende de historico de dias ANTERIORES (a faixa de abertura e'
calculada dentro do proprio pregao, sem quantil/burn-in causal entre dias) --
diferente de G4/G5/G6, nao ha' "historico acumulado" a declarar aqui.

Protocolo (ORQUESTRACAO.md / mandato do dono): roda UMA VEZ, sem reajustar
nada depois de ver o numero -- se falhar, esta' MORTA.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g07_orb/g07_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g07_base as b  # noqa: E402

KW_VENCEDOR = dict(
    range_minutos=5.0,
    stop_min_pontos=100.0,
    stop_max_pontos=250.0,
    alvo_multiplo=5.0,
    buffer_entrada_pontos=20.0,
    ttl_barras_entrada=10,
)


def roda_congelado(dias_operar: list, capital: float = b.CAPITAL, **kwargs_estrategia):
    """Mesmo papel de `g04_base.roda_congelado` -- importa a classe do
    modulo CONGELADO (`..._congelado_v07`), nunca do modulo vivo, para o
    OOS-1 nao poder ser afetado por uma edicao posterior de `win_busca_lucro_
    g07_orb.py`."""
    sys.path.insert(0, str(b.ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g07_orb_congelado_v07 import (
        WinBuscaLucroG07Orb as WinBuscaLucroG07OrbCongelado,
    )

    win = b.carrega_win()
    bars = b.bars_dos_dias(win, dias_operar)
    strat = WinBuscaLucroG07OrbCongelado(**kwargs_estrategia)
    cfg = b.monta_config(capital)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    win = b.carrega_win()
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)

    print("=" * 130)
    print("WinBuscaLucroG07Orb -- OOS-1 (jul-ago/2026), CONGELADO, roda UMA VEZ")
    print("=" * 130)
    print(f"OOS-1: {len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print(f"kwargs congelados = {KW_VENCEDOR}\n", flush=True)

    res, strat = roda_congelado(dias_oos1, **KW_VENCEDOR)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    top5 = b.concentracao_topn(c["serie"], 5)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    be_nom = 1.0 / (1.0 + KW_VENCEDOR["alvo_multiplo"])
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": (b.br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
        "IC95 win": (f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--"),
        "veredito": c["veredito"],
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
        "top3/liq": (b.br(100 * c["concentracao_top3"], 0) + "%") if c["concentracao_top3"] == c["concentracao_top3"] else "--",
        "top5/liq": (b.br(100 * top5, 0) + "%") if top5 == top5 else "--",
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
    }
    linha = linha_de_resultado("OOS-1 (congelado)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=10))

    equity_min_ok = equity_min >= b.MARGEM_WIN_BRL
    censurado = c["n"] == 0 or c["sem_trade"] >= 0.5 * c["pregoes"] or not equity_min_ok
    stop_dist = sorted(c["stop_dist_pts"])
    stop_med = stop_dist[len(stop_dist) // 2] if stop_dist else float("nan")

    print(f"\nliquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  pregoes_c_trade={c['com_trade']}/{c['pregoes']}  "
          f"equity_min={b.br(equity_min)}  "
          f"ordens_recusadas_por_capital={res.ordens_recusadas_por_capital}  censurado={censurado}")
    print(f"bruto={strat.stats_bruto}  ja_operou_hoje={strat.stats_ja_operou_hoje}  "
          f"emitidas={strat.stats_ordens_emitidas}")
    print(f"top3/liquido={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liquido={b.br(100*top5,0) if top5==top5 else '--'}%")
    print(f"stop_mediana_pts={b.br(stop_med,0)}  (>=100 -> item 6.47 nao exige checagem com ticks; <100 -> EXIGE)")

    print("\nVEREDITO FINAL:")
    if censurado:
        print("  -> MORTA (censurado: 0 trades, ou >=50% pregoes sem trade, ou caixa minimo abaixo da margem crua).")
    elif c["liquido"] <= 0:
        print("  -> MORTA (liquido <= 0 no OOS-1).")
    elif c["veredito"] == "NEGATIVO":
        print("  -> MORTA (win% estatisticamente ABAIXO do breakeven empirico no OOS-1).")
    elif c["veredito"] == "indefinido":
        print("  -> NAO VALIDADA COM FOLGA (liquido>0 mas IC95 do win% cruza o breakeven empirico).")
    else:
        print("  -> PASSA (liquido>0, nao censurado, win% estatisticamente acima do breakeven empirico) -- "
              "ver tambem a concentracao top3/top5 antes de declarar 'com folga'.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
