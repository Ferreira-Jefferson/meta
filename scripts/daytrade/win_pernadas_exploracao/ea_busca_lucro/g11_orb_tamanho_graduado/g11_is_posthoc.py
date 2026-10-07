# -*- coding: utf-8 -*-
"""Geracao 11 -- analise POS-HOC: estratifica os 121 trades REAIS da REF
(G8 sem filtro, rodada UMA vez) pela forca do rompimento que os originou,
em vez de rodar 3 simulacoes EXCLUSIVAS (como `g11_is_busca.py` fez no
Passo 2).

Por que esta segunda analise e' necessaria (achado de metodo desta
geracao): rodar 3 celulas EXCLUSIVAS com `forca_min`/`forca_max` muda qual
EDGE do dia e' escolhido -- quando o primeiro edge do dia nao bate o balde,
a estrategia so' re-arma no PROXIMO edge fresco (mecanismo de
`on_order_rejected`/`on_order_expired`), que pode cair num horario/contexto
diferente do dia. Isso confunde "forca do sinal" com "qual sinal do dia foi
escolhido" -- exatamente por isso REF (sem filtro, aceita o 1o edge
valido) superou TODOS os 3 baldes exclusivos no Passo 2, mesmo o balde
"forte".

Esta analise evita o confundimento: roda REF UMA VEZ (operacao identica a`
G8, 121 trades reais), e so' DEPOIS classifica cada trade pela forca da
PROPRIA ordem que o originou (`strat.stats_forca_das_entradas`, na mesma
ordem cronologica de `res.trades`). Pergunta: dentre os trades que
REALMENTE aconteceram, os de forca mais alta tem win%/payoff genuinamente
melhor que os de forca mais baixa?

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g11_orb_tamanho_graduado/g11_is_posthoc.py`
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g11_base as b  # noqa: E402


def _z_duas_proporcoes(k1, n1, k2, n2) -> float:
    if n1 == 0 or n2 == 0:
        return float("nan")
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    denom = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if denom == 0:
        return float("nan")
    return (p1 - p2) / denom


def main() -> None:
    win = b.carrega_win()
    dias = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)

    print("=" * 120)
    print("Geracao 11 -- analise POS-HOC (REF rodada 1x, trades estratificados pela forca de entrada)")
    print("=" * 120)

    res, strat = b.roda(dias, forca_min=0.0, forca_max=float("inf"), **b.GEOMETRIA_G8)
    trades = list(res.trades)
    forcas_entrada = list(strat.stats_forca_das_entradas)
    print(f"trades={len(trades)}  forcas_de_entrada_registradas={len(forcas_entrada)}")
    if len(trades) != len(forcas_entrada):
        print("AVISO: contagem nao bate -- instrumentacao de forca por trade pode estar "
              "dessincronizada; analise pos-hoc abortada.")
        return

    ordem = sorted(range(len(trades)), key=lambda i: trades[i].entry_ts)
    trades_ord = [trades[i] for i in ordem]
    forcas_ord = [forcas_entrada[i] for i in ordem]

    arr = np.asarray(forcas_ord, dtype=float)
    q_baixo, q_alto = np.quantile(arr, (1 / 3, 2 / 3))
    print(f"forca das {len(trades)} entradas reais: min={b.br(arr.min(),3)}  max={b.br(arr.max(),3)}  "
          f"mediana={b.br(np.median(arr),3)}")
    print(f"cortes de tercil (sobre os trades REAIS, pos-hoc): p33={b.br(q_baixo,3)}  p67={b.br(q_alto,3)}\n")

    baldes = {"fraco": [], "medio": [], "forte": []}
    for t, f in zip(trades_ord, forcas_ord):
        if f < q_baixo:
            baldes["fraco"].append((t, f))
        elif f < q_alto:
            baldes["medio"].append((t, f))
        else:
            baldes["forte"].append((t, f))

    resumo = {}
    for nome, pares in baldes.items():
        n = len(pares)
        vitorias = [t for t, _ in pares if t.pnl_brl > 0]
        k = len(vitorias)
        win = (k / n) if n else float("nan")
        ganhos = [t.pnl_brl for t, _ in pares if t.pnl_brl > 0]
        perdas = [t.pnl_brl for t, _ in pares if t.pnl_brl <= 0]
        gm = (sum(ganhos) / len(ganhos)) if ganhos else 0.0
        pm = (abs(sum(perdas) / len(perdas))) if perdas else 0.0
        be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
        payoff = (gm / pm) if pm > 0 else float("nan")
        liquido = sum(t.pnl_brl for t, _ in pares)
        lo, hi = b.ic95_wilson(k, n) if n else (float("nan"), float("nan"))
        veredito = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
            if be == be and n else "--"
        resumo[nome] = dict(n=n, k=k, win=win, gm=gm, pm=pm, be=be, payoff=payoff,
                             liquido=liquido, lo=lo, hi=hi, veredito=veredito)
        print(f"  {nome:<8} n={n:>4}  vitorias={k:>4}  win={b.br(100*win,1) if n else '--':>6}%  "
              f"BEemp={b.br(100*be,1) if be==be else '--':>6}%  IC95=[{b.br(100*lo,1) if n else '--'};"
              f"{b.br(100*hi,1) if n else '--'}]  veredito={veredito:<10}  "
              f"payoff={b.br(payoff,2) if payoff==payoff else '--':>5}  liquido={b.br(liquido):>10}")

    print("\n--- comparacao forte x fraco (teste de duas proporcoes, win%, pos-hoc) ---")
    z = _z_duas_proporcoes(resumo["forte"]["k"], resumo["forte"]["n"],
                            resumo["fraco"]["k"], resumo["fraco"]["n"])
    print(f"z = {b.br(z,2) if z==z else '--'}  (|z|>=1,96 => distinguivel de ruido a 95%)")
    print(f"diferenca forte-vs-fraco distinguivel de ruido? {z==z and abs(z)>=1.96}")

    print("\n--- correlacao forca x resultado (ponto-bisserial aproximado, todos os 121 trades) ---")
    pnl = np.asarray([t.pnl_brl for t in trades_ord], dtype=float)
    ganhou = (pnl > 0).astype(float)
    if np.std(arr) > 0 and np.std(ganhou) > 0:
        corr_forca_ganho = float(np.corrcoef(arr, ganhou)[0, 1])
    else:
        corr_forca_ganho = float("nan")
    if np.std(arr) > 0 and np.std(pnl) > 0:
        corr_forca_pnl = float(np.corrcoef(arr, pnl)[0, 1])
    else:
        corr_forca_pnl = float("nan")
    print(f"corr(forca, venceu?) = {b.br(corr_forca_ganho,3)}")
    print(f"corr(forca, pnl R$)  = {b.br(corr_forca_pnl,3)}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
