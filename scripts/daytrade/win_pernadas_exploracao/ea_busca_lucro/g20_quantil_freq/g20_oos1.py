# -*- coding: utf-8 -*-
"""Geracao 20 (`WinBuscaLucroG20CrossWdoFreq`) -- OOS-1 (jul-ago/2026), RODA UMA VEZ.

Vencedor do IS (congelado em
`win_busca_lucro_g20_cross_wdo_freq_congelado_v20.py` ANTES desta rodada):
direcao_aposta=continuacao, janela_min=20, **quantil=0,60** (baixado de 0,75
da G17 -- ideia central desta geracao: mais frequencia dilui concentracao),
stop_pontos=150, alvo_multiplo=3,0x, buffer_entrada_pontos=30, capital de
teste R$1.000. IS: liquido=+R$2.166,00, 324 trades, win=32,7% (BEnom 25,0%,
BEemp 27,1%, IC95[27,8;38,0] POSITIVO por 0,7pp), 95/122 pregoes com trade,
top3/liquido=38,5%, top5/liquido=58,4% (referencia G17: 56,3%/77,0%),
p_ruina(MC)=1,6%. Escolhido por bater o criterio composto desta geracao
(POSITIVO + p_ruina<=20% + concentracao < referencia G17) e ser o UNICO entre
15 celulas do cruzamento quantil x alvo_multiplo (`g20_alvo_cruzamento.py`).

O quantil causal do estado anomalo usa o historico REAL acumulado (IS +
OOS-1, ate' o dia anterior a cada barra) -- mesmo precedente de G4/G12/G14/
G15/G17.

Protocolo (ORQUESTRACAO.md / mandato do dono): roda UMA VEZ, sem reajustar
nada depois de ver o numero -- se falhar, esta' MORTA.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g20_quantil_freq/g20_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g20_base as b  # noqa: E402

KW_VENCEDOR = dict(
    direcao_aposta="continuacao",
    stop_pontos=150.0,
    alvo_multiplo=3.0,
    buffer_entrada_pontos=30.0,
)
JANELA_MIN = 20
QUANTIL = 0.60

#: Referencia G17 (mesmo criterio de comparacao do mandato, item 4/5).
REF_G17_IS_TOP3 = 0.563
REF_G17_IS_TOP5 = 0.770
REF_G17_OOS1_TOP3 = 3.83
REF_G17_OOS1_TOP5 = 6.39


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    win = b.carrega_win()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    dias_historico = sorted(set(dias_is) | set(dias_oos1))

    print("=" * 130)
    print("WinBuscaLucroG20CrossWdoFreq -- OOS-1 (jul-ago/2026), CONGELADO, roda UMA VEZ")
    print("=" * 130)
    print(f"OOS-1: {len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print(f"kwargs congelados = {KW_VENCEDOR}, janela_min={JANELA_MIN}, quantil={QUANTIL}, "
          f"capital=R${b.br(b.CAPITAL,0)}")
    print("Quantil causal usa o historico acumulado IS+OOS-1 (nao reinicia burn-in em jul/2026).\n", flush=True)

    ep = b.episodios_stats(dias_oos1, dias_historico, JANELA_MIN, QUANTIL)
    res, strat = b.roda_congelado_v20(
        dias_oos1, dias_historico=dias_historico, janela_min=JANELA_MIN, quantil=QUANTIL,
        capital=b.CAPITAL, **KW_VENCEDOR)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos1), caixa=b.CAPITAL)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    be_nom = 1.0 / (1.0 + KW_VENCEDOR["alvo_multiplo"])
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
    }
    linha = linha_de_resultado("OOS-1 q=0,60/alvo=3x/stop=150 (congelado G20)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=10))

    censurado = b.censurado(c, equity_min)
    print(f"\nepisodios_brutos(onset)={ep['episodios_brutos']}  "
          f"pregoes_distintos_com_episodio={ep['pregoes_distintos']}/{ep['pregoes_totais']}")
    print(f"liquido={b.br(c['liquido'])}  trades={c['n']}  pregoes_com_trade={c['com_trade']}/{c['pregoes']}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  equity_min={b.br(equity_min)}  "
          f"ordens_recusadas_por_capital={res.ordens_recusadas_por_capital}  censurado={censurado}")
    print(f"top3/liquido={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liquido={b.br(100*top5,0) if top5==top5 else '--'}%  "
          f"(referencia G17 OOS-1: {b.br(100*REF_G17_OOS1_TOP3,0)}%/{b.br(100*REF_G17_OOS1_TOP5,0)}%)")
    print(f"p_ruina(MC, caixa=R${b.br(b.CAPITAL,0)}, n_ops={ru['n_ops']})="
          f"{b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%  "
          f"pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)})")
    stop_med = sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2] if c["stop_dist_pts"] else float("nan")
    print(f"stop_mediana_pts={b.br(stop_med,0)}  (>=100 -> item 6.47 nao exige checagem com ticks; <100 -> EXIGE)")

    retorno_pct = 100.0 * c["liquido"] / b.CAPITAL
    print(f"\nRetorno sobre R$1.000 (regua do dono): {b.br(retorno_pct,1)}% em {len(dias_oos1)} pregoes "
          f"({b.br(retorno_pct / 2.0, 1)}%/mes medio, 2 meses)")

    print("\nVEREDITO FINAL:")
    concentracao_menor_que_g17 = (
        c["concentracao_top3"] == c["concentracao_top3"] and c["concentracao_top3"] < REF_G17_OOS1_TOP3
        and top5 == top5 and top5 < REF_G17_OOS1_TOP5)
    com_folga = (not censurado and c["liquido"] > 0 and c["veredito"] != "NEGATIVO"
                 and ru["p_ruina"] == ru["p_ruina"] and ru["p_ruina"] <= 0.20
                 and c["concentracao_top3"] == c["concentracao_top3"] and c["concentracao_top3"] <= 1.20)
    if censurado:
        print("  -> MORTA (censurado: 0 trades, ou >=50% pregoes sem trade, ou caixa minimo abaixo da margem crua).")
    elif c["liquido"] <= 0:
        print("  -> MORTA (liquido <= 0 no OOS-1).")
    elif c["veredito"] == "NEGATIVO":
        print("  -> MORTA (win% estatisticamente ABAIXO do breakeven empirico no OOS-1).")
    elif com_folga:
        print("  -> PASSA COM FOLGA (liquido>0, nao censurado, veredito!=NEGATIVO, "
              "p_ruina<=20%, concentracao top3 nao explodiu) -- avanca para OOS-2.")
    else:
        print("  -> PASSA O GATE LITERAL MAS NAO COM FOLGA (ver os numeros acima -- "
              "nao avanca para OOS-2 sem reler o padrao de fragilidade).")
    print(f"  Concentracao MENOR que a referencia G17 no OOS-1 ({b.br(100*REF_G17_OOS1_TOP3,0)}%/"
          f"{b.br(100*REF_G17_OOS1_TOP5,0)}%)? {concentracao_menor_que_g17}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
