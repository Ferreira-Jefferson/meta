# -*- coding: utf-8 -*-
"""Geracao 20 -- diagnostico completo do vencedor do IS (q=0,60, alvo=3,0x,
stop=150pts), achado no PASSO 2 (`g20_alvo_cruzamento.py`). Roda UMA vez a
mais (fora do sweep paralelo) so' para extrair equity_min, pior sequencia de
perdas, stop mediano (item 6.47) e episodios/pregoes distintos -- os mesmos
campos que as geracoes anteriores reportam na secao "Vencedora do IS" do
ORQUESTRACAO.md.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g20_quantil_freq/g20_vencedor_diagnostico.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g20_base as b  # noqa: E402

QUANTIL = 0.60
KW = dict(direcao_aposta=b.DIRECAO_APOSTA, stop_pontos=150.0, alvo_multiplo=3.0,
          buffer_entrada_pontos=b.BUFFER_ENTRADA)


def _fmt_pct(v) -> str:
    return (b.br(100 * v, 1) + "%") if v == v else "--"


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    ep = b.episodios_stats(dias, dias, b.JANELA_MIN, QUANTIL)

    res, strat = b.roda(dias, dias_historico=dias, janela_min=b.JANELA_MIN,
                         quantil=QUANTIL, capital=b.CAPITAL, **KW)
    trades = list(res.trades)
    c = b.consistencia(trades, dias)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias), caixa=b.CAPITAL)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    be_nom = 1.0 / (1.0 + KW["alvo_multiplo"])
    stop_med = sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2] if c["stop_dist_pts"] else float("nan")

    print("=" * 130)
    print(f"Geracao 20 -- diagnostico completo: q={QUANTIL:.2f}, alvo=3,0x, stop=150pts, "
          f"buffer=30pts, janela=20min, continuacao, capital R$1.000")
    print("=" * 130)
    extras = {
        "BEnom%": b.br(100 * be_nom, 1) + "%",
        "BEemp%": _fmt_pct(c["be"]),
        "IC95 win": f"[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]" if c["n"] else "--",
        "veredito": c["veredito"],
        "top3/liq": _fmt_pct(c["concentracao_top3"]),
        "top5/liq": _fmt_pct(top5),
        "p_ruina": _fmt_pct(ru["p_ruina"]),
        "pior_seq": f"{pior_seq_n} (R${b.br(pior_seq_brl)})",
        "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
        "bruto": str(strat.stats_bruto),
        "emit/brt": f"{strat.stats_ordens_emitidas}/{strat.stats_bruto}",
    }
    linha = linha_de_resultado("IS q=0,60/alvo=3,0x/stop=150 (vencedor G20)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=10))

    print(f"\nepisodios_brutos(onset)={ep['episodios_brutos']}  "
          f"pregoes_distintos_com_episodio={ep['pregoes_distintos']}/{ep['pregoes_totais']}")
    print(f"liquido={b.br(c['liquido'])}  trades={c['n']}  pregoes_com_trade={c['com_trade']}/{c['pregoes']}  "
          f"win={_fmt_pct(c['win'])}  BEnom={_fmt_pct(be_nom)}  BEemp={_fmt_pct(c['be'])}  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  margem(IC95_lo-BEemp)={b.br(100*c['lo']-100*c['be'],1)}pp  "
          f"veredito={c['veredito']}")
    print(f"equity_min={b.br(equity_min)}  ordens_recusadas_por_capital={res.ordens_recusadas_por_capital}  "
          f"censurado={b.censurado(c, equity_min)}")
    print(f"top3/liquido={_fmt_pct(c['concentracao_top3'])}  top5/liquido={_fmt_pct(top5)}  "
          f"(referencia G17 IS: 56,3%/77,0%)")
    print(f"p_ruina(MC, caixa=R${b.br(b.CAPITAL,0)}, n_ops={ru['n_ops']})={_fmt_pct(ru['p_ruina'])}  "
          f"ruina_formula(Lundberg)={_fmt_pct(ru['ruina_formula'])}  "
          f"pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)}, {b.br(100*abs(pior_seq_brl)/b.CAPITAL,1)}% do caixa de partida)")
    print(f"stop_dist_mediana_pts={b.br(stop_med,0)}  (>=100 -> item 6.47 nao exige checagem com ticks; <100 -> EXIGE)")
    print(f"lucro/DD={b.br(c['liquido']/c['maxdd'],2) if c['maxdd']>0 else '--'}  maxdd=R${b.br(c['maxdd'])}")

    retorno_pct = 100.0 * c["liquido"] / b.CAPITAL
    print(f"\nRetorno sobre R$1.000 (regua do dono), IS inteiro (122 pregoes, 6 meses): "
          f"{b.br(retorno_pct,1)}% ({b.br(retorno_pct/6.0,1)}%/mes medio)")
    print("\nFIM.")


if __name__ == "__main__":
    main()
