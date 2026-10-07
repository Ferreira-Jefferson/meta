# -*- coding: utf-8 -*-
"""Geracao 18 (`WinBuscaLucroG18OrbCapital1000`) -- OOS-1 (jul-ago/2026), RODA UMA VEZ.

Vencedor do IS (congelado em
`win_busca_lucro_g18_orb_capital1000_congelado_v18.py` ANTES desta rodada):
`stop_max_pontos=140`, `alvo_multiplo=3.0`, `range_minutos=5.0`,
`buffer_entrada_pontos=20.0`, `stop_min_pontos=50.0`, capital de teste
R$1.000, 1 contrato fixo. Escolhido entre as 9 celulas POSITIVAS da grade de
30 (alvo x stop_max) por: maior `lucro/DD` (6,28, a maior da grade inteira),
menor `p_ruina` (0,0%, empatada com varias outras), menor concentracao
(top3/liquido=18%, top5=31%, entre as duas menores da grade) e maior margem
estatistica sobre o breakeven empirico (IC95 inferior 29,1% contra BEemp
27,4% -- 1,7pp de folga, a maior margem relativa entre as 9 POSITIVAS). E' a
MESMA geometria que ja era o vencedor isolado de G8/G13 a R$250 (penhasco
cercado de colapso) -- a R$1.000 ela continua sendo o melhor ponto, agora no
MEIO de um platô largo (30/30 celulas passam o criterio composto, contra
1/75 a R$250).

IS (jan-jun/2026, 122 pregoes): liquido=R$1.365,50, 121 trades, win=37,2%
(BEnom 25,0%, BEemp 27,4%, IC95[29,1%;46,1%], POSITIVO), 121/122 pregoes com
trade, top3/liquido=18%, top5/liquido=31%, p_ruina(MC, R$1.000->R$100)=0,0%,
pior_seq=6 (R$-179,00).

Comparacao isolada (`g18_comparacao_capital.py`, MESMOS 121 trades, MESMO
liquido): a R$250 esta MESMA geometria tinha p_ruina=24,8% (acima do limiar
de 20% que G8/G13 usavam) -- so' o capital 4x maior derruba para 0,0%, sem
mudar NENHUM trade.

Protocolo (ORQUESTRACAO.md / mandato do dono): roda UMA VEZ, sem reajustar
nada depois de ver o numero -- se falhar, esta' MORTA.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g18_orb_capital1000/g18_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g18_base as b  # noqa: E402

KW_VENCEDOR = dict(
    range_minutos=5.0,
    stop_min_pontos=50.0,
    stop_max_pontos=140.0,
    alvo_multiplo=3.0,
    buffer_entrada_pontos=20.0,
)


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    win = b.carrega_win()
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)

    print("=" * 130)
    print("WinBuscaLucroG18OrbCapital1000 -- OOS-1 (jul-ago/2026), CONGELADO, roda UMA VEZ")
    print("=" * 130)
    print(f"OOS-1: {len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print(f"kwargs congelados = {KW_VENCEDOR}, capital=R${b.br(b.CAPITAL,0)}")
    print("Sem pool causal externo -- o ORB nao depende de historico de dias anteriores.\n", flush=True)

    res, strat = b.roda_congelado(dias_oos1, capital=b.CAPITAL, **KW_VENCEDOR)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    censura = b.censura_separada(res, c)
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
    linha = linha_de_resultado("OOS-1 alvo=3x/stop_max=140 (congelado v18)", res, b.CAPITAL, extras=extras)
    print(tabela([linha], extras=tuple(extras.keys()), largura_extra=10))

    print(f"\nliquido={b.br(c['liquido'])}  trades={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  equity_min={b.br(censura['equity_min'])}  "
          f"ordens_recusadas_por_capital={censura['ordens_recusadas_por_capital']}  "
          f"censura_capital={censura['censura_capital']}  seletividade_amostra={censura['seletividade_amostra']}")
    print(f"top3/liquido={b.br(100*c['concentracao_top3'],0) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liquido={b.br(100*top5,0) if top5==top5 else '--'}%  "
          f"(comparar com a G17: top3=56%, top5=77% no OOS-1 do sinal cruzado)")
    print(f"p_ruina(MC, caixa=R${b.br(b.CAPITAL,0)}, n_ops={ru['n_ops']})="
          f"{b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%  "
          f"pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)})")
    stop_med = sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2] if c["stop_dist_pts"] else float("nan")
    print(f"stop_mediana_pts={b.br(stop_med,0)}  (>=100 -> item 6.47 nao exige checagem com ticks; <100 -> EXIGE)")

    retorno_pct = 100.0 * c["liquido"] / b.CAPITAL
    print(f"\nRetorno sobre R$1.000 (regua do dono): {b.br(retorno_pct,1)}% em {len(dias_oos1)} pregoes "
          f"({b.br(retorno_pct / 2.0, 1)}%/mes medio, 2 meses)")

    print("\nVEREDITO FINAL:")
    censurado = censura["censura_capital"] or c["n"] == 0
    com_folga = (not censurado and c["liquido"] > 0 and c["veredito"] != "NEGATIVO"
                 and ru["p_ruina"] == ru["p_ruina"] and ru["p_ruina"] <= 0.20
                 and c["concentracao_top3"] == c["concentracao_top3"] and c["concentracao_top3"] <= 0.60
                 and top5 == top5 and top5 <= 0.80)
    if censurado:
        print("  -> MORTA (censurado por capital: equity cruzou a margem crua ou ordem recusada).")
    elif c["liquido"] <= 0:
        print("  -> MORTA (liquido <= 0 no OOS-1).")
    elif c["veredito"] == "NEGATIVO":
        print("  -> MORTA (win% estatisticamente ABAIXO do breakeven empirico no OOS-1).")
    elif com_folga:
        print("  -> PASSA COM FOLGA (liquido>0, nao censurado por capital, veredito!=NEGATIVO, "
              "p_ruina<=20%, concentracao top3<=60%/top5<=80%) -- avanca para OOS-2.")
    else:
        print("  -> PASSA O GATE LITERAL MAS NAO COM FOLGA (ver os numeros acima -- "
              "nao avanca para OOS-2 sem reler o padrao de fragilidade).")
    print("\nFIM.")


if __name__ == "__main__":
    main()
