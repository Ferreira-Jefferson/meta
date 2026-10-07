"""fractal_core -- forma interna (fractal) de um recuo no WIN. Definicoes congeladas em definicoes_congeladas.json.

Tudo e estado observavel em tempo real: cada fase so e confirmada por preco ja ocorrido.
  A      avanco: pivo S (confirmado pelo zigzag T) ate o extremo corrente E (A >= T).
  F      fundo provisorio do recuo: minimo corrente desde E; CONFIRMADO em t1 quando o preco sobe s da minima.
  H      topo do repique: maximo corrente desde t1; confirmado em t2 quando o preco cai s do maximo.
  G      fundo do reteste: minimo corrente desde t2; confirmado em t3 quando o preco sobe s da minima.
  Forma (a,a2,b,c,d,e) so e atribuida em t3, com F,H,G ja confirmados. Resultado olha t3 em diante.
Direcao: baixa e tratada espelhando o sinal (q = dir*preco).
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada2/chave")
from kit_pernadas import _ZZ  # noqa: E402

CSV = "C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WIN@D_M1_202110010900_202610011717.csv"
TOL = 10.0          # fundo duplo: |G-F| <= 10 pts (2 ticks)
RHO_PEQ = 0.38      # repique pequeno
RHO_MED = 0.50
X_POUCO = 0.10      # "fura por pouco": <= 10% do recuo
KS = (20, 50, 100, 150, 200, 300)
CUSTO = 2.0
DESLIZE_STOP = 5.0
ESCALAS = [(250, 65), (250, 30), (500, 125), (500, 65), (750, 190), (750, 95)]

PERIODOS = {
    "descoberta": ("2026-01-01", "2026-07-01"),
    "confirmacao": ("2026-07-01", "2026-09-01"),
    "referencia": ("2026-09-01", "2026-10-01"),
}


def carregar_m1(ini: str, fim: str) -> pd.DataFrame:
    """So 2026 (>= 2026-01-01). Nunca abre antes disso."""
    assert ini >= "2026-01-01"
    df = pd.read_csv(CSV, sep="\t", usecols=[0, 1, 2, 3, 4, 5])
    df.columns = ["d", "t", "open", "high", "low", "close"]
    df = df[df.d >= "2026.01.01"]
    df["ts"] = pd.to_datetime(df["d"] + " " + df["t"], format="%Y.%m.%d %H:%M:%S")
    df = df[(df.ts >= ini) & (df.ts < fim)].set_index("ts")[["open", "high", "low", "close"]].astype(float)
    return df


def caminho_dia(g: pd.DataFrame):
    o, h, l, c = (g[k].values for k in ("open", "high", "low", "close"))
    up = c >= o
    a = np.where(up, l, h)
    b = np.where(up, h, l)
    pr = np.empty(2 * len(g))
    pr[0::2] = a
    pr[1::2] = b
    tm = np.repeat((g.index.hour * 60 + g.index.minute).values, 2)  # minuto do dia
    return tm, pr


def embaralha_dia(g: pd.DataFrame, rng) -> pd.DataFrame:
    """Embaralha velas dentro de blocos de 30 min e reencadeia (open novo = close anterior): sem saltos."""
    blk = (g.index.hour * 60 + g.index.minute) // 30
    idx = np.arange(len(g))
    perm = idx.copy()
    for b in np.unique(blk):
        m = np.where(blk == b)[0]
        perm[m] = rng.permutation(m)
    o, h, l, c = (g[k].values[perm] for k in ("open", "high", "low", "close"))
    sh = np.zeros(len(g))
    prev_c = o[0]
    for i in range(len(g)):
        sh[i] = prev_c - o[i]
        prev_c = c[i] + sh[i]
    return pd.DataFrame({"open": o + sh, "high": h + sh, "low": l + sh, "close": c + sh}, index=g.index)


def zz_estado(pr: np.ndarray, T: float):
    """Por ponto: dir, E, E_idx, S (perna_ini). Retorna arrays; pontos sem pivo: dir=0."""
    n = len(pr)
    dr = np.zeros(n, np.int8)
    E = np.full(n, np.nan)
    S = np.full(n, np.nan)
    zz = _ZZ(T)
    for i in range(n):
        zz.passo(i, pr[i])
        if zz.dir != 0:
            dr[i] = zz.dir
            E[i] = zz.E
            S[i] = zz.perna_ini
    return dr, E, S


def scan(q, i0, E, S, s, dmin, tol=TOL):
    """Evento a partir do extremo E (indice i0). q ja espelhado (E>S). Retorna dict ou None."""
    n = len(q)
    j = i0 + 1
    Fm = np.inf
    j1 = -1
    while j < n:
        p = q[j]
        if p >= E or p <= S:
            return None
        if p < Fm:
            Fm = p
        elif p >= Fm + s:
            j1 = j
            break
        j += 1
    if j1 < 0:
        return None
    F = Fm
    d1 = E - F
    if d1 < dmin:
        return None
    r = dict(i0=i0, j1=j1, F=F, d1=d1)
    # fase 2: repique
    Hm = q[j1]
    j = j1 + 1
    j2 = -1
    while j < n:
        p = q[j]
        if p >= E:
            r.update(forma="s", H=E, rho=1.0, G=np.nan, j2=-1, j3=-1, out="sup", jout=j)
            return r
        if p <= S:
            r.update(forma="s", H=Hm, rho=(Hm - F) / d1, G=np.nan, j2=-1, j3=-1, out="vira", jout=j)
            return r
        if p > Hm:
            Hm = p
        elif p <= Hm - s:
            j2 = j
            break
        j += 1
    if j2 < 0:
        return None
    H = Hm
    rho = (H - F) / d1
    r.update(H=H, rho=rho, j2=j2)
    # fase 3: reteste
    Gm = q[j2]
    j = j2 + 1
    j3 = -1
    while j < n:
        p = q[j]
        if p >= E:
            return None  # inalcancavel por construcao (d1>=2s); guarda
        if p <= S:
            r.update(forma="e", G=min(Gm, p), j3=-1, out="vira", jout=j)
            return r
        if p < Gm:
            Gm = p
        elif p >= Gm + s:
            j3 = j
            break
        j += 1
    if j3 < 0:
        return None
    G = Gm
    r.update(G=G, j3=j3)
    if G < F - tol:
        if rho < RHO_PEQ:
            f = "d"
        elif (F - G) <= X_POUCO * d1:
            f = "c"
        else:
            f = "e"
    elif abs(G - F) <= tol:
        f = "b"
    else:
        f = "a" if rho >= RHO_MED else "a2"
    r["forma"] = f
    # desfecho a partir de t3
    mn = min(Gm, F)
    j = j3 + 1
    out, jout = "nada", n - 1
    while j < n:
        p = q[j]
        if p >= E:
            out, jout = "sup", j
            break
        if p <= S:
            out, jout = "vira", j
            break
        if p < mn:
            mn = p
        j += 1
    r.update(out=out, jout=jout)
    return r


def geometria(q, r, E, S, KS=KS):
    """Limite de compra em F colocada em t2 (H confirmado). Preenche ao tocar F. Alvo E; stop F-k.
    Retorna dict com fill, e por k: res (+1 alvo, -1 stop, 0 fim do pregao)."""
    n = len(q)
    F = r["F"]
    j2 = r["j2"]
    out = dict(fill=0)
    if j2 < 0:
        return out
    jf = -1
    for j in range(j2 + 1, n):
        if q[j] >= E:
            return out  # alvo sem preencher: cancela
        if q[j] <= F:
            jf = j
            break
    if jf < 0:
        return out
    out["fill"] = 1
    out["jf"] = jf
    mn = F
    jE = -1
    for j in range(jf, n):
        if q[j] >= E:
            jE = j
            break
        if q[j] < mn:
            mn = q[j]
    out["mn_exc"] = F - mn  # excesso abaixo de F ate alvo/fim
    out["alvo"] = int(jE >= 0)
    out["ult"] = q[-1] - F
    return out


def eventos_dia(g: pd.DataFrame, dia, escalas=ESCALAS, pr_tm=None):
    """Todos os eventos do dia (tick ou M1). pr_tm: (tm, pr) para usar caminho alternativo."""
    tm, pr = pr_tm if pr_tm is not None else caminho_dia(g)
    linhas = []
    for T, s in escalas:
        dr, E, S = zz_estado(pr, T)
        # inicios de evento: pontos onde (dir,E) muda
        qs = {1: pr, -1: -pr}
        for i in range(len(pr)):
            d = dr[i]
            if d == 0:
                continue
            if i > 0 and dr[i - 1] == d and E[i] == E[i - 1]:
                continue
            sg = float(d)
            q = qs[int(sg)]
            Eq, Sq = sg * E[i], sg * S[i]
            A = Eq - Sq
            r = scan(q, i, Eq, Sq, s, 2 * s)
            if r is None:
                continue
            r.update(dia=dia, T=T, s=s, dir=int(d), A=A, S=Sq, E=Eq,
                     hora=tm[r["j1"]] / 60.0, r1=r["d1"] / A)
            if r["j2"] >= 0 and "G" in r and not np.isnan(r.get("G", np.nan)):
                pass
            gm = geometria(q, r, Eq, Sq)
            r.update({f"g_{k}": v for k, v in gm.items()})
            # excesso ate o alvo (so quando o desfecho a partir de t1 e sup): fundo minimo t1..jout
            jo = r["jout"]
            mn = q[r["j1"]:jo + 1].min() if jo >= r["j1"] else r["F"]
            r["exc_min"] = max(0.0, r["F"] - mn)
            # nulo analitico
            if r["j3"] >= 0:
                p3 = r["G"] + s
                D, dd = Eq - p3, p3 - Sq
                r["p_sup_ruina"] = dd / (D + dd)
                r["p_G_menor"] = np.exp(-(r["H"] - s - r["F"] + TOL) / s)
            linhas.append(r)
    return linhas


def processa(ini, fim, seed=None, caminho="m1"):
    """seed None = real; senao embaralhado. Retorna DataFrame de eventos."""
    m1 = carregar_m1(ini, fim)
    rng = np.random.default_rng(seed) if seed is not None else None
    linhas = []
    for dia, g in m1.groupby(m1.index.normalize()):
        if len(g) < 60:
            continue
        gg = embaralha_dia(g, rng) if rng is not None else g
        linhas += eventos_dia(gg, dia)
    return pd.DataFrame(linhas)
