"""ROBUSTEZ (2026-09-14) -- a vantagem do T1.5 sobre o T2.0 e' estavel?

## O problema que este script ataca

`wdo_orb_geometria_is_oos_2026_09_14.py` mediu 7 celulas de `alvo_multiplo`
em duas janelas independentes e o T1.5 (alvo = 1,5x stop) ganhou do T2.0 (a
producao) nas duas, em consistencia, dispersao e concentracao.

Isso NAO e' validacao. A celula foi escolhida OLHANDO as duas janelas -- elas
foram gastas na escolha, e nao sobrou janela cega. Com 7 celulas x 2 janelas
x 3 metricas, alguma celula ganha nos dois lados por sorte com probabilidade
que nao da' para ignorar. Validacao cega de verdade so' com pregao que ainda
nao aconteceu.

O que da' para medir HOJE e' outra coisa, e vale por si: **a vantagem depende
de quais operacoes aconteceram, ou ela reaparece quando a amostra e'
reembaralhada?** Uma vantagem que so' existe na ordem exata em que os
pregoes caiu e' ruido com aparencia de resultado.

## Os dois testes

1. **Walk-forward por mes.** Em quantos meses, dos ~6 que IS+OOS cobrem, o
   T1.5 bate o T2.0? Nao e' cego (os meses estao dentro do que foi olhado),
   mas responde se a vantagem e' persistente ou vem de um mes so'.

2. **Bootstrap por PREGAO, nao por operacao.** Reamostra os pregoes com
   reposicao 5.000 vezes e recalcula tudo. Por pregao, e nao por operacao,
   porque as duas operacoes de um mesmo dia compartilham a faixa de abertura,
   o regime e ate' o lado -- tratar as 195 como independentes inflaria a
   confianca. O que sai e': em que fracao das reamostragens o T1.5 ganha.

   O emparelhamento e' MANTIDO: cada reamostragem sorteia os mesmos pregoes
   para as duas celulas, entao a comparacao e' sempre sobre o mesmo mercado.
   Sortear independente mediria a diferenca entre dois mercados diferentes,
   que nao e' a pergunta.

## Leitura

Uma fracao perto de 50% significa "cara-ou-coroa" -- a vantagem observada e'
um sorteio. Acima de ~90% a vantagem sobrevive ao reembaralhamento. Isso
ainda nao e' validacao fora de amostra; e' o piso que ela precisa passar
antes de merecer uma.

Uso: `python -u scripts/daytrade/wdo_orb_t15_robustez_2026_09_14.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
DIR = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"

#: defaults = o teste original (alvo). Sobrescreviveis por linha de comando
#: para servir a qualquer par de celulas:
#:   python ... <arquivo.csv> <celula_atual> <celula_candidata>
ARQUIVO, ATUAL, CANDIDATA = "40_geometria_trades.csv", "T2.0", "T1.5"
if len(sys.argv) == 4:
    ARQUIVO, ATUAL, CANDIDATA = sys.argv[1], sys.argv[2], sys.argv[3]
N_BOOT = 5000
JANELAS_INDEP = ["IS", "OOS_LIMPO"]


def metricas(ops: pd.DataFrame) -> dict:
    if ops.empty:
        return {"rs_por_op": np.nan, "pregoes_pos": np.nan, "desvio": np.nan}
    por_dia = ops.groupby("data")["pnl_brl"].sum()
    return {
        "rs_por_op": ops["pnl_brl"].mean(),
        "pregoes_pos": 100.0 * (por_dia > 0).sum() / len(por_dia),
        "desvio": ops["pnl_brl"].std(ddof=1),
    }


def main() -> None:
    df = pd.read_csv(DIR / ARQUIVO)
    df = df[df.celula.isin([ATUAL, CANDIDATA])]
    base = df[df.janela.isin(JANELAS_INDEP)]

    print(f"populacao: {base.data.nunique()} pregoes, "
          f"{len(base[base.celula == ATUAL])} operacoes no {ATUAL}, "
          f"{len(base[base.celula == CANDIDATA])} no {CANDIDATA}\n")

    # ---- 1. walk-forward por mes -----------------------------------------
    print("=" * 96)
    print("1) WALK-FORWARD POR MES -- a vantagem persiste ou vem de um mes so'?")
    print("=" * 96)
    base = base.copy()
    base["mes"] = pd.to_datetime(base["data"]).dt.to_period("M").astype(str)
    linhas = []
    for mes, sub in base.groupby("mes"):
        a = metricas(sub[sub.celula == ATUAL])
        c = metricas(sub[sub.celula == CANDIDATA])
        linhas.append({
            "mes": mes,
            "pregoes": sub.data.nunique(),
            f"{ATUAL} R$/op": round(a["rs_por_op"], 2),
            f"{CANDIDATA} R$/op": round(c["rs_por_op"], 2),
            "venceu_rs": "SIM" if c["rs_por_op"] > a["rs_por_op"] else "nao",
            f"{ATUAL} preg+": round(a["pregoes_pos"], 1),
            f"{CANDIDATA} preg+": round(c["pregoes_pos"], 1),
            "venceu_preg": "SIM" if c["pregoes_pos"] > a["pregoes_pos"]
                           else ("empate" if c["pregoes_pos"] == a["pregoes_pos"] else "nao"),
        })
    tab = pd.DataFrame(linhas)
    print(tab.to_string(index=False))
    v_rs = (tab.venceu_rs == "SIM").sum()
    v_pr = (tab.venceu_preg == "SIM").sum()
    e_pr = (tab.venceu_preg == "empate").sum()
    print(f"\n  {CANDIDATA} bate {ATUAL} em R$/op em {v_rs}/{len(tab)} meses")
    print(f"  {CANDIDATA} bate {ATUAL} em pregoes positivos em {v_pr}/{len(tab)} "
          f"meses ({e_pr} empate)")
    tab.to_csv(DIR / "60_walkforward_mensal.csv", index=False, encoding="utf-8")

    # ---- 2. bootstrap por pregao, emparelhado -----------------------------
    print("\n" + "=" * 96)
    print(f"2) BOOTSTRAP POR PREGAO ({N_BOOT} reamostragens, emparelhado)")
    print("=" * 96)

    rng = np.random.default_rng(20260914)
    dias = base.data.unique()
    # pre-agrega por (celula, dia): soma e contagem, para o laco nao refazer
    # groupby 5.000 vezes
    agr = {}
    for cel in (ATUAL, CANDIDATA):
        g = base[base.celula == cel].groupby("data")["pnl_brl"]
        agr[cel] = pd.DataFrame({"soma": g.sum(), "n": g.count()}).reindex(dias).fillna(0.0)

    ganhou_rs = ganhou_preg = ganhou_ambos = 0
    difs_rs, difs_preg = [], []
    for _ in range(N_BOOT):
        idx = rng.integers(0, len(dias), len(dias))
        res = {}
        for cel in (ATUAL, CANDIDATA):
            somas = agr[cel]["soma"].values[idx]
            ns = agr[cel]["n"].values[idx]
            total_n = ns.sum()
            res[cel] = {
                "rs": somas.sum() / total_n if total_n else np.nan,
                # pregao sem operacao nao conta como positivo nem negativo
                "preg": 100.0 * (somas > 0).sum() / max((ns > 0).sum(), 1),
            }
        d_rs = res[CANDIDATA]["rs"] - res[ATUAL]["rs"]
        d_pr = res[CANDIDATA]["preg"] - res[ATUAL]["preg"]
        difs_rs.append(d_rs); difs_preg.append(d_pr)
        if d_rs > 0: ganhou_rs += 1
        if d_pr > 0: ganhou_preg += 1
        if d_rs > 0 and d_pr > 0: ganhou_ambos += 1

    difs_rs = np.array(difs_rs); difs_preg = np.array(difs_preg)
    print(f"  {CANDIDATA} tem R$/op maior em          "
          f"{100.0*ganhou_rs/N_BOOT:5.1f}% das reamostragens")
    print(f"  {CANDIDATA} tem mais pregoes positivos em {100.0*ganhou_preg/N_BOOT:5.1f}%")
    print(f"  {CANDIDATA} ganha nas DUAS ao mesmo tempo em {100.0*ganhou_ambos/N_BOOT:5.1f}%")
    print(f"\n  diferenca de R$/op:            mediana {np.median(difs_rs):+6.2f}  "
          f"IC95 [{np.percentile(difs_rs,2.5):+6.2f} ; {np.percentile(difs_rs,97.5):+6.2f}]")
    print(f"  diferenca de pregoes positivos: mediana {np.median(difs_preg):+6.2f}pp "
          f"IC95 [{np.percentile(difs_preg,2.5):+6.2f} ; {np.percentile(difs_preg,97.5):+6.2f}]")

    pd.DataFrame({"dif_rs_por_op": difs_rs, "dif_pregoes_pos_pp": difs_preg}).to_csv(
        DIR / "61_bootstrap_t15.csv", index=False, encoding="utf-8")

    print("\n  [leitura] perto de 50% = a vantagem e' sorteio. Acima de ~90% ela")
    print("  sobrevive ao reembaralhamento -- o que ainda NAO e' validacao fora")
    print("  de amostra, e' o piso para merecer uma.")
    print(f"\n[robustez] arquivos em {DIR}")


if __name__ == "__main__":
    main()
