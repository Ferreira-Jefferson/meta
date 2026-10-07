# -*- coding: utf-8 -*-
"""Geracao 2 (`WinBuscaLucroG02R65`) -- OOS-1 (jul-ago/2026), GATE UNICO.

So' roda depois que `g02_is_busca.py` apontou um vencedor com liquido > 0 E
nao censurado no IS. Os parametros do vencedor sao CONGELADOS aqui (copiados
a mao do print "VENCEDOR FINAL" do script de IS) -- este arquivo roda UMA
VEZ, sem reajustar depois de ver o resultado (regra do dono, ORQUESTRACAO.md).

A classe de estrategia usada e' `WinBuscaLucroG02R65` em
`src/strategy/daytrade/lab/win_busca_lucro_g02_r65_tarde.py`, versao
congelada antes desta rodada (ver `ORQUESTRACAO.md` para qual hash/estado o
arquivo tinha quando este script rodou).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g02_r65/g02_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g02_base as b  # noqa: E402

# -- Vencedor EXATO do IS (`g02_is_busca.py`, rodado 2026-10-05) -----------
# Estagio A: janela "sem_filtro" (09:00-18:29) empatou BIT-A-BIT com
# "so_tarde" (12:59-18:29) -- os 4 sinais do IS nasceram todos a' tarde, a
# janela nao mudou NADA do resultado. Estagio B: stop tecnico N=10 (empatou
# com N=15). Estagio C: alvo 5x. liquido IS = R$637,00, 4 trades (n MINUSCULO
# -- ver a ressalva de metodo no modulo e em ORQUESTRACAO.md antes de ler
# o resultado abaixo como validacao).
KWARGS_CONGELADOS = dict(
    janela_inicio="09:00",
    janela_fim="18:29",
    familia_stop="tecnico",
    barras_stop_tecnico=10,
    alvo_multiplo=5.0,
)
ROTULO = "vencedor IS (congelado v02): tecnico N=10, alvo 5x, janela 09:00-18:29"


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    df = b.carrega_df()
    dias_is = b.dias_da_janela(df, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    dias_oos1 = b.dias_da_janela(df, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    print("=" * 110)
    print("WinBuscaLucroG02R65 -- OOS-1 (jul-ago/2026), GATE UNICO -- capital R$ %s" % b.br(b.CAPITAL, 0))
    print("=" * 110)
    print(f"kwargs congelados: {KWARGS_CONGELADOS}")
    print(f"{len(dias_oos1)} pregoes completos ({dias_oos1[0]} a {dias_oos1[-1]})")
    print("RESSALVA: WIN@ sem fila calibrada -- toda ordem-limite enche no TOQUE.\n", flush=True)

    EXTRAS = ("BEnom%", "BEemp%", "IC95 win", "veredito", "seq-", "n_stop", "pts/op", "sem_tr")

    def _linha(rotulo: str, dias: list):
        res = b.roda_congelado(dias, **KWARGS_CONGELADOS)
        trades = list(res.trades)
        c = b.consistencia(trades, dias)
        be_nom = 1.0 / (1.0 + KWARGS_CONGELADOS["alvo_multiplo"])
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
        print(f"  {rotulo:<28} liquido={b.br(c['liquido']):>10}  trades={c['n']:>4}  "
              f"win={b.br(100*c['win'],1) if c['n'] else '--':>6}%  "
              f"sem_trade={c['sem_trade']:>3}/{c['pregoes']}  "
              f"ordens_recusadas_capital={res.ordens_recusadas_por_capital:>4}  "
              f"equity_min={b.br(float(res.equity_curve.min()) if len(res.equity_curve) else float('nan')):>9}",
              flush=True)
        return linha_res, c

    linha_is, c_is = _linha("IS (jan-jun, referencia)", dias_is)
    linha_oos1, c_oos1 = _linha("OOS-1 (jul-ago, GATE)", dias_oos1)

    print()
    print(tabela([linha_is, linha_oos1], extras=EXTRAS))

    print("\nVEREDITO OOS-1 (gate unico, sem retunar):")
    censurado = c_oos1["n"] == 0 or c_oos1["sem_trade"] >= 0.5 * c_oos1["pregoes"]
    ic_nao_toca_zero = c_oos1["n"] > 0 and (c_oos1["liquido"] > 0) and (c_oos1["lo"] > c_oos1["be"] if c_oos1["be"] == c_oos1["be"] else False)
    if censurado:
        print("  CENSURADO -- robo parou de operar na janela, nao e' veredito de estrategia.")
    elif c_oos1["liquido"] > 0 and ic_nao_toca_zero:
        print("  PASSA COM FOLGA -- liquido>0, nao censurado, IC95 do win% acima do breakeven empirico.")
    elif c_oos1["liquido"] > 0:
        print("  PASSA NO LIMITE -- liquido>0 mas IC95 do win% cruza o breakeven (n pequeno) -- "
              "tratar como indefinido, nao como vitoria.")
    else:
        print("  MORTA -- liquido<=0 no OOS-1. Nao reajustar parametro; registrar e encerrar esta linha.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
