# -*- coding: utf-8 -*-
"""Geracao 3 (`WinBuscaLucroG03RecuoRaso`) -- OOS-1 (jul-ago/2026), GATE UNICO.

So' roda depois que `g03_is_busca.py` apontou um vencedor com liquido > 0 E
nao censurado no IS (rodado 2026-10-05, ver `g03_is_busca_stdout.log`). Os
parametros do vencedor sao CONGELADOS aqui -- este arquivo roda UMA VEZ, sem
reajustar depois de ver o resultado (regra do dono, ORQUESTRACAO.md).

A classe de estrategia usada e' `WinBuscaLucroG03RecuoRaso` em
`src/strategy/daytrade/lab/win_busca_lucro_g03_recuo_raso_congelado_v03.py`,
versao congelada ANTES desta rodada.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g03_recuo_raso/g03_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g03_base as b  # noqa: E402

# -- Vencedor EXATO do IS (`g03_is_busca.py`, rodado 2026-10-05) -----------
# Estagio A: R57+horario(11-13) venceu (so' porque TODAS as variantes do
# estagio A estavam censuradas -- o criterio de desempate caiu no maior
# liquido entre censuradas). Estagio B: T=750. Estagio C: m=20. Estagio D:
# alvo=7x (primeira celula a sair do vermelho, +R$53,50, ainda censurada por
# sem_trade). Estagio E isolou o efeito do horario com a geometria de B+C+D
# e achou que NENHUM filtro de horario bate o "sem filtro" em frequencia --
# 09:00-11:00 venceu em liquido (R$357,00) e R$/dia, mas "sem_filtro"
# (00:00-23:59) fica logo atras (R$294,50) com 2x mais trades (183 x 92) e
# tambem nao-censurado. R59 NUNCA venceu nenhum estagio (A2/A4 sempre piores
# que os pares sem R59) -- o filtro nao ajudou nesta busca.
KWARGS_CONGELADOS = dict(
    usar_filtro_r59=False,
    pernada_pontos=750.0,
    m_pontos=20.0,
    alvo_multiplo=7.0,
    janela_inicio="09:00",
    janela_fim="11:00",
)
ROTULO = "vencedor IS (congelado v03): T750, m=20, alvo=7x, R59=off, janela 09:00-11:00"


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    df = b.carrega_df()
    dias_is = b.dias_da_janela(df, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    dias_oos1 = b.dias_da_janela(df, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    print("=" * 115)
    print("WinBuscaLucroG03RecuoRaso -- OOS-1 (jul-ago/2026), GATE UNICO -- capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 115)
    print(f"kwargs congelados: {KWARGS_CONGELADOS}")
    print(f"{len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.\n", flush=True)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "seq-", "bruto", "emit/brt", "pts/op", "sem_tr")

    def _linha(rotulo: str, dias: list):
        res, strat = b.roda_congelado(dias, **KWARGS_CONGELADOS)
        trades = list(res.trades)
        c = b.consistencia(trades, dias)
        be_nom = 1.0 / (1.0 + KWARGS_CONGELADOS["alvo_multiplo"])
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
        equity_min = float(res.equity_curve.min()) if len(res.equity_curve) else float("nan")
        print(f"  {rotulo:<28} liquido={b.br(c['liquido']):>10}  bruto={strat.stats_bruto_r57:>4}  "
              f"emitidas={strat.stats_ordens_emitidas:>4}  trades={c['n']:>4}  "
              f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
              f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
              f"ordens_recusadas_capital={res.ordens_recusadas_por_capital:>4}  "
              f"equity_min={b.br(equity_min):>9}",
              flush=True)
        stop_med = (sorted(c["stop_dist_pts"])[len(c["stop_dist_pts"]) // 2]
                    if c["stop_dist_pts"] else float("nan"))
        return linha_res, c, equity_min, stop_med

    linha_is, c_is, eqmin_is, stopmed_is = _linha("IS (jan-jun, referencia)", dias_is)
    linha_oos1, c_oos1, eqmin_oos1, stopmed_oos1 = _linha("OOS-1 (jul-ago, GATE)", dias_oos1)

    print()
    print(tabela([linha_is, linha_oos1], extras=EXTRAS, largura_extra=10))
    print(f"\nstop mediano (pts): IS={b.br(stopmed_is,0)}  OOS-1={b.br(stopmed_oos1,0)}  "
          f"equity_min: IS={b.br(eqmin_is)}  OOS-1={b.br(eqmin_oos1)}")

    print("\nVEREDITO OOS-1 (gate unico, sem retunar):")
    censurado = (c_oos1["n"] == 0 or c_oos1["sem_trade"] >= 0.5 * c_oos1["pregoes"]
                 or eqmin_oos1 < b.MARGEM_WIN_BRL)
    ic_nao_toca_zero = c_oos1["n"] > 0 and (c_oos1["liquido"] > 0) and (
        c_oos1["lo"] > c_oos1["be"] if c_oos1["be"] == c_oos1["be"] else False)
    if censurado:
        print("  CENSURADO -- robo parou de operar/caixa exauriu na janela, nao e' veredito de estrategia.")
    elif c_oos1["liquido"] > 0 and ic_nao_toca_zero:
        print("  PASSA COM FOLGA -- liquido>0, nao censurado, IC95 do win% acima do breakeven empirico.")
    elif c_oos1["liquido"] > 0:
        print("  PASSA NO LIMITE -- liquido>0 mas IC95 do win% cruza o breakeven -- "
              "tratar como indefinido, nao como vitoria.")
    else:
        print("  MORTA -- liquido<=0 no OOS-1. Nao reajustar parametro; registrar e encerrar esta linha.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
