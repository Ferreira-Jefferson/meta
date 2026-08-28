"""Re-medicao das 5 celulas nomeadas da familia "M5 pre-registrada" (WIN@ M5),
julgadas pelo critério de BLOCO de 4 pregoes (`copa_score.PREGOES_POR_FASE`)
alem do P&L/pregao -- pedido do dono 2026-08-27.

RESSALVA: o `m5_preregistro.md` original (grade fechada de 22 celulas, gravada
ANTES de rodar) NAO esta no repo. Isto e' re-medicao das 5 celulas cujos
parametros ficaram nomeados na memoria -- a propriedade de pre-registro se
perdeu com o arquivo.

BUG ACHADO E CORRIGIDO nesta rodada (1a versao deste script): rompimento com
fill NO NIVEL preenche num preco que nao existe mais quando o nivel foi
atravessado ANTES da barra em que o scan comeca (o nivel do ATR fica a ~388 pts
do open e o dia anda ~1.009 pts, entao na mediana o preco ja passou -- barra de
entrada mediana era exatamente a 1a barra escaneada). Inflava +238 pts/pregao no
IS e +373 no OOS. O fill agora e' o PIOR entre nivel e abertura da barra que
dispara, mesma convencao de `machine.py::_exit_fill_price`. Mesmo padrao de
look-ahead de saida/entrada que ja contaminou a corrida k3 e o F3 do WDO.

Custo: convencao do repo em pontos por round-trip por contrato (2,5 = so'
tarifa / 7,5 = +1 tick / 12,5 = +2 ticks), point_value R$0,20, teto 12.
Nulo: espelhamento de barra (sign-flip) POR PREGAO, construcao de
copa_calibracao_nula, 20 replicas, com as duas verificacoes obrigatorias
(high-low identico barra a barra; distribuicao de gap preservada).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PARQUET = "data/raw_intraday/WIN_A_M5.parquet"
IS_INI, IS_FIM = "2023-11-06", "2026-06-13"
CONTRATOS, POINT_VALUE, BLOCO = 12, 0.20, 4
CUSTOS_PTS = (2.5, 7.5, 12.5)
N_REPLICAS = 20

Sessao = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]  # o,h,l,c


def sessoes() -> dict:
    d = pd.read_parquet(PARQUET)[["open", "high", "low", "close"]].copy()
    d["dia"] = d.index.date
    out = {}
    for k, g in d.groupby("dia"):
        if len(g) >= 20:
            out[k] = tuple(g[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    return out


def espelha(s: Sessao, rng: np.random.Generator) -> Sessao:
    o, h, l, c = s
    gap = np.empty_like(o); gap[0] = 0.0; gap[1:] = o[1:] - c[:-1]
    body = c - o
    up = h - np.maximum(o, c)
    dn = np.minimum(o, c) - l
    sg = rng.choice([1.0, -1.0], size=len(o))
    # novo_close acumula: no[i] = nc[i-1] + s*gap; nc[i] = no[i] + s*body
    # => nc[i] = o[0] + cumsum(s*(gap+body)) com gap[0]=0
    nc = o[0] + np.cumsum(sg * (gap + body))
    no = np.empty_like(nc); no[0] = o[0]; no[1:] = nc[:-1] + sg[1:] * gap[1:]
    hi, lo = np.maximum(no, nc), np.minimum(no, nc)
    nh = np.where(sg > 0, hi + up, hi + dn)
    nl = np.where(sg > 0, lo - dn, lo - up)
    return no, nh, nl, nc


# ---------------- as 5 celulas (pts por trade, lista) ----------------
def _fill_stop(s: Sessao, n: int, alto: float, baixo: float):
    o, h, l, c = s
    for i in range(n, len(o)):
        if h[i] >= alto:
            return c[-1] - max(o[i], alto)
        if l[i] <= baixo:
            return min(o[i], baixo) - c[-1]
    return None


def comprado(s):
    return [s[3][-1] - s[0][0]]


def vendido(s):
    return [s[0][0] - s[3][-1]]


def romp_atr(s, n=14, mult=1.5):
    o, h, l, c = s
    if len(o) <= n:
        return []
    atr = float((h - l)[:n].mean())
    v = _fill_stop(s, n, o[0] + mult * atr, o[0] - mult * atr)
    return [] if v is None else [v]


def romp_abertura(s, n=18):
    o, h, l, c = s
    if len(o) <= n:
        return []
    v = _fill_stop(s, n, float(h[:n].max()), float(l[:n].min()))
    return [] if v is None else [v]


def continuacao(s, k=12):
    o, h, l, c = s
    out, n = [], len(o)
    for ini in range(k, n - k + 1, k):
        r = c[ini - 1] - c[ini - k]
        if r == 0:
            continue
        out.append((1.0 if r > 0 else -1.0) * (c[min(ini + k - 1, n - 1)] - o[ini]))
    return out


CELULAS = {
    "comprado o dia inteiro (EXATA)": comprado,
    "vendido o dia inteiro (EXATA)": vendido,
    "rompimento ATR m1,5 (recon.)": romp_atr,
    "rompimento abertura N18 (recon.)": romp_abertura,
    "continuacao k=12 (recon.)": continuacao,
}


def bruto_e_n(fn, dias, ses) -> tuple[np.ndarray, np.ndarray]:
    """Separa BRUTO de contagem de round-trips: permite variar custo sem
    reprocessar o dado (o custo e' linear em n_trades)."""
    br = np.empty(len(dias)); nt = np.empty(len(dias))
    for j, d in enumerate(dias):
        t = fn(ses[d]); br[j] = sum(t); nt[j] = len(t)
    return br, nt


def em_reais(br, nt, custo):
    return (br - custo * nt) * POINT_VALUE * CONTRATOS


def blocos(v, tam=BLOCO):
    n = len(v) - len(v) % tam
    bl = [v[i:i + tam].sum() for i in range(0, n, tam)]
    return sum(1 for b in bl if b > 0), len(bl)


def main() -> None:
    ses = sessoes()
    todos = sorted(ses)
    a, b = pd.Timestamp(IS_INI).date(), pd.Timestamp(IS_FIM).date()
    IS = [d for d in todos if a <= d < b]
    OOS = [d for d in todos if d >= b]

    g0 = ses[IS[0]]
    e0 = espelha(g0, np.random.default_rng(0))
    hl_ok = np.allclose(g0[1] - g0[2], e0[1] - e0[2])
    gr = g0[0][1:] - g0[3][:-1]; gs = e0[0][1:] - e0[3][:-1]
    print(f"[nulo] high-low identico barra a barra: {hl_ok} | "
          f"|gap| medio real {np.abs(gr).mean():.2f} vs sintetico {np.abs(gs).mean():.2f}")
    print(f"IS {len(IS)} pregoes {IS[0]}..{IS[-1]} | OOS {len(OOS)} pregoes {OOS[0]}..{OOS[-1]}")
    print(f"teto {CONTRATOS} contratos, bloco {BLOCO} pregoes, {N_REPLICAS} replicas\n")

    # espelhamento HOISTADO: 20 conjuntos sinteticos, reusados por celula e custo
    sint = []
    for r in range(N_REPLICAS):
        rng = np.random.default_rng(1000 + r)
        sint.append({d: espelha(ses[d], rng) for d in todos})

    cache = {}
    for nome, fn in CELULAS.items():
        for tag, dias in (("IS", IS), ("OOS", OOS)):
            cache[(nome, tag, "real")] = bruto_e_n(fn, dias, ses)
            cache[(nome, tag, "nulo")] = [bruto_e_n(fn, dias, sint[r]) for r in range(N_REPLICAS)]

    for custo in CUSTOS_PTS:
        print(f"===== custo {custo} pts/round-trip/contrato =====")
        print(f"{'celula':34s} {'jan':4s} {'R$/pregao':>10s} {'mediana':>9s} {'liquido':>12s} "
              f"{'blocos+':>9s} {'top3':>7s} {'nulo medio':>11s} {'p':>6s}")
        for nome in CELULAS:
            for tag in ("IS", "OOS"):
                br, nt = cache[(nome, tag, "real")]
                v = em_reais(br, nt, custo)
                pos, tot = blocos(v)
                top3 = 100 * np.sort(v)[-3:].sum() / v.sum() if v.sum() else float("nan")
                nul = np.array([em_reais(b2, n2, custo).mean()
                                for b2, n2 in cache[(nome, tag, "nulo")]])
                p = float((nul >= v.mean()).mean())
                print(f"{nome:34s} {tag:4s} {v.mean():10,.2f} {np.median(v):9,.2f} {v.sum():12,.2f} "
                      f"{pos:4d}/{tot:<4d} {top3:6.0f}% {nul.mean():11,.2f} {p:6.3f}")
        print()


if __name__ == "__main__":
    main()
