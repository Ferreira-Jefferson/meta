"""copa_win: DENTRO da 1a operacao do dia, da' pra prever qual vai stopar?

Esta e' a unica versao ACIONAVEL da pergunta. A lente 3 (`copawin_preditor_
stop_2026_09_15.py`) achou AUC OOS 0,689 num modelo sobre os 564 trades, mas
o maior coeficiente dele e' `tentativa_no_dia` -- ou seja, boa parte do poder
preditivo e' o modelo redescobrindo o proprio fato sob investigacao
("operacao tardia stopa menos"). Isso nao e' acionavel: ninguem escolhe nao
ser a primeira operacao do dia.

Aqui a populacao e' fixada nas 191 PRIMEIRAS operacoes (36 stops, 18,8%), o
ordinal vira constante e some do modelo. O que sobrar de separacao e' sinal
de verdade.

## Escolha PRE-DECLARADA das variaveis (antes de olhar qualquer resultado)

Com 24 stops no IS, um modelo de 11 variaveis daria ~2,2 eventos por
variavel -- muito abaixo da regra pratica de ~10 e uma fabrica de
sobreajuste. O conjunto do modelo combinado e' fixado em QUATRO, escolhidas
por motivo declarado aqui e nao por desempenho:

  * `razao_range_tipico`  -- unico preditor CONFIRMADO pela lente 3 que nao
                             e' colinear com o relogio (Spearman ~0,67).
  * `minutos_desde_abertura` -- o relogio continua VARIANDO dentro da 1a
                             operacao (46 a 90 barras, lente 1), entao e'
                             preditor legitimo aqui, nao constante.
  * `razao_volume_tipico` -- o analogo do range no eixo de volume; ficou a
                             um passo do corte no IS da lente 3 (p=0,081).
  * `vol_ref_ticks`       -- a manchete da lente 1 (a 1a nasce em regime
                             estreito). Entra para ser testada com
                             honestidade DENTRO da 1a, onde a lente 3 so' a
                             mediu na populacao inteira (e la' ela INVERTEU
                             de sinal no OOS).

`stop_dist_ticks` e `barras_hoje` ficam FORA por colinearidade exata
(stop_dist = 12,0 x vol_ref; barras = minutos, base M1).

A tabela UNIVARIADA, essa sim, roda em TODAS as numericas -- descritiva,
com Benjamini-Hochberg, para nada ficar escondido.

## Fonte dos dados

`scratch/copawin_preditor_stop_trades.csv`, produzido pela lente 3 a partir
do backtest CONTINUO de 191 pregoes com a config de producao (564 trades,
58 stops, conferido byte a byte contra `copawin_onde_perde_2026_09_14.log`).
Nao rodo o backtest de novo: a populacao tem de ser exatamente a mesma, ou a
comparacao com a lente 3 nao vale.

Sem scipy/sklearn (convencao do repo): Mann-Whitney por soma de postos com
aproximacao normal, AUC pela estatistica U, logistica por Newton/IRLS.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "scratch" / "copawin_preditor_stop_trades.csv"

PRE_DECLARADAS = [
    "razao_range_tipico",
    "minutos_desde_abertura",
    "razao_volume_tipico",
    "vol_ref_ticks",
]
FORA_DO_MODELO = {"stop_dist_ticks", "barras_hoje", "tentativa_no_dia"}
NAO_PREDITORAS = {"data", "janela", "lado", "dia_semana", "hora_sinal",
                  "exit_reason", "stop_out", "pnl_brl"}


def br(x, casas=3):
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def mann_whitney(a, b):
    """z e p (bicaudal) por soma de postos, aproximacao normal com correcao
    de empates. Devolve tambem o tamanho de efeito r = z/sqrt(N)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    na, nb = len(a), len(b)
    if na < 3 or nb < 3:
        return np.nan, np.nan, np.nan, na, nb
    todos = np.concatenate([a, b])
    postos = pd.Series(todos).rank().to_numpy()
    ra = postos[:na].sum()
    u = ra - na * (na + 1) / 2.0
    mu = na * nb / 2.0
    _, cont = np.unique(todos, return_counts=True)
    corr = (cont ** 3 - cont).sum()
    n = na + nb
    var = na * nb / 12.0 * ((n + 1) - corr / (n * (n - 1)))
    if var <= 0:
        return np.nan, np.nan, np.nan, na, nb
    z = (u - mu) / np.sqrt(var)
    from math import erf, sqrt
    p = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    return z, p, z / np.sqrt(n), na, nb


def bh(ps, alpha=0.05):
    """Benjamini-Hochberg: devolve mascara de rejeicao."""
    ps = np.asarray(ps, float)
    ok = ~np.isnan(ps)
    idx = np.where(ok)[0]
    ordem = idx[np.argsort(ps[idx])]
    m = len(ordem)
    rej = np.zeros(len(ps), bool)
    maior = -1
    for i, j in enumerate(ordem, start=1):
        if ps[j] <= alpha * i / m:
            maior = i
    for i, j in enumerate(ordem, start=1):
        if i <= maior:
            rej[j] = True
    return rej


def auc(y, s):
    """AUC pela estatistica U (equivalente ao trapezio da ROC)."""
    y, s = np.asarray(y, bool), np.asarray(s, float)
    pos, neg = s[y], s[~y]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    postos = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    u = postos[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0
    return u / (len(pos) * len(neg))


def logistica(X, y, iters=60, ridge=1e-4):
    """Newton/IRLS com ridge minimo (so' para nao explodir em separacao)."""
    X = np.column_stack([np.ones(len(X)), X])
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = X @ beta
        p = 1.0 / (1.0 + np.exp(-np.clip(eta, -30, 30)))
        W = np.clip(p * (1 - p), 1e-9, None)
        H = X.T @ (X * W[:, None]) + ridge * np.eye(X.shape[1])
        g = X.T @ (y - p) - ridge * beta
        passo = np.linalg.solve(H, g)
        beta = beta + passo
        if np.max(np.abs(passo)) < 1e-9:
            break
    return beta


def prever(X, beta):
    X = np.column_stack([np.ones(len(X)), X])
    return 1.0 / (1.0 + np.exp(-np.clip(X @ beta, -30, 30)))


def main():
    if not CSV.exists():
        sys.exit(f"nao achei {CSV} -- rode a lente 3 antes")
    d = pd.read_csv(CSV)
    p1 = d[d["tentativa_no_dia"] == 1].copy()
    p1["stop"] = p1["stop_out"].astype(bool)
    p1["data"] = pd.to_datetime(p1["data"])
    corte = pd.Timestamp("2026-06-13")
    is_ = p1[p1["data"] < corte]
    oos = p1[p1["data"] >= corte]

    print("=" * 108)
    print("copa_win -- DENTRO da 1a operacao do dia: da' pra prever o STOP?")
    print("=" * 108)
    print(f"populacao: {len(p1)} primeiras operacoes | stops {int(p1['stop'].sum())} "
          f"({br(100 * p1['stop'].mean(), 1)}%)")
    print(f"  IS  : n={len(is_):>3}  stops={int(is_['stop'].sum()):>3} ({br(100 * is_['stop'].mean(), 1)}%)")
    print(f"  OOS : n={len(oos):>3}  stops={int(oos['stop'].sum()):>3} ({br(100 * oos['stop'].mean(), 1)}%)")
    print("\nAVISO DE POTENCIA, declarado ANTES do resultado: 24 stops no IS. Mesmo com as 4")
    print("variaveis pre-declaradas isso da' ~6 eventos por variavel, abaixo da regra de ~10.")
    print("Um resultado NULO aqui NAO distingue 'nao ha sinal' de 'nao ha amostra'.\n")

    numericas = [c for c in p1.columns
                 if c not in NAO_PREDITORAS | {"stop"} | FORA_DO_MODELO
                 and pd.api.types.is_numeric_dtype(p1[c])]

    print("=" * 108)
    print("UNIVARIADA -- todas as numericas (IS descobre com BH, OOS valida a direcao)")
    print("=" * 108)
    linhas = []
    for c in numericas:
        zi, pi, ri, nai, nbi = mann_whitney(is_.loc[is_["stop"], c], is_.loc[~is_["stop"], c])
        zo, po, ro, nao, nbo = mann_whitney(oos.loc[oos["stop"], c], oos.loc[~oos["stop"], c])
        mi = is_.loc[is_["stop"], c].median() - is_.loc[~is_["stop"], c].median()
        mo = oos.loc[oos["stop"], c].median() - oos.loc[~oos["stop"], c].median()
        linhas.append(dict(variavel=c, IS_dif_mediana=mi, IS_p=pi, IS_r=ri,
                           OOS_dif_mediana=mo, OOS_p=po,
                           mesma_direcao=("SIM" if (np.sign(mi) == np.sign(mo) and mi != 0) else "INVERTE")))
    tab = pd.DataFrame(linhas).sort_values("IS_p")
    tab["IS_BH"] = np.where(bh(tab["IS_p"].to_numpy()), "SIM", "nao")
    tab["veredito"] = np.where(
        (tab["IS_BH"] == "SIM") & (tab["mesma_direcao"] == "SIM") & (tab["OOS_p"] < 0.05),
        "CONFIRMADA",
        np.where(tab["IS_BH"] == "SIM", "so' no IS", "nao separa no IS"))
    hdr = (f"{'variavel':<36}{'IS dif med':>12}{'IS p':>9}{'IS r':>8}{'BH':>5}"
           f"{'OOS dif med':>13}{'OOS p':>9}{'direcao':>10}{'veredito':>20}")
    print(hdr)
    print("-" * len(hdr))
    for _, r in tab.iterrows():
        print(f"{r['variavel']:<36}{br(r['IS_dif_mediana']):>12}{br(r['IS_p'], 4):>9}"
              f"{br(r['IS_r'], 3):>8}{r['IS_BH']:>5}{br(r['OOS_dif_mediana']):>13}"
              f"{br(r['OOS_p'], 4):>9}{r['mesma_direcao']:>10}{r['veredito']:>20}")

    print("\n" + "=" * 108)
    print("MODELO COMBINADO -- 4 variaveis PRE-DECLARADAS, ajustado SO' no IS")
    print("=" * 108)
    cols = PRE_DECLARADAS
    tr = is_.dropna(subset=cols)
    te = oos.dropna(subset=cols)
    print(f"  linhas completas: IS {len(tr)}/{len(is_)}   OOS {len(te)}/{len(oos)}")
    print(f"  eventos por variavel no IS: {br(tr['stop'].sum() / len(cols), 1)}")
    mu, sd = tr[cols].mean(), tr[cols].std(ddof=0).replace(0, 1.0)
    Xtr = ((tr[cols] - mu) / sd).to_numpy()
    Xte = ((te[cols] - mu) / sd).to_numpy()
    beta = logistica(Xtr, tr["stop"].to_numpy(float))
    print("\n  coeficientes (padronizados pelo IS):")
    print(f"    {'intercepto':<26}{br(beta[0]):>10}")
    for c, b in zip(cols, beta[1:]):
        print(f"    {c:<26}{br(b):>10}")
    a_is = auc(tr["stop"].to_numpy(bool), prever(Xtr, beta))
    a_oos = auc(te["stop"].to_numpy(bool), prever(Xte, beta))
    print(f"\n  AUC IS  (ajuste)   : {br(a_is, 3)}")
    print(f"  AUC OOS (validacao): {br(a_oos, 3)}   <- o numero que decide")
    print("  referencia: 0,500 = moeda. A lente 3, na populacao INTEIRA e COM o ordinal,")
    print("  chegou a 0,689 -- mas la' o ordinal fazia o trabalho, e ele nao e' acionavel.")

    print("\n" + "-" * 108)
    print("SE fosse usado como filtro: taxa de stop por decil de risco previsto (OOS)")
    print("-" * 108)
    te = te.copy()
    te["risco"] = prever(Xte, beta)
    te["faixa"] = pd.qcut(te["risco"], 4, labels=["Q1 (menor)", "Q2", "Q3", "Q4 (maior)"],
                          duplicates="drop")
    g = te.groupby("faixa", observed=True).agg(n=("stop", "size"), stops=("stop", "sum"),
                                               pnl_medio=("pnl_brl", "mean"))
    g["P(stop)%"] = 100 * g["stops"] / g["n"]
    print(g.to_string())
    print("\n  base de comparacao: P(stop) da 1a operacao no OOS = "
          f"{br(100 * oos['stop'].mean(), 1)}%")
    print("\nFIM.")


if __name__ == "__main__":
    main()
