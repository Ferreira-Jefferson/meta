"""f2 — FIGURAS GRAFICAS / ESTRUTURA como filtro de entrada ou saida do WinCincoMedias v2.02 (M30). Features + candidatas.

Tudo usa so' velas FECHADAS ate' a barra do sinal t (inclusive). Pivos (fractal de k velas de cada lado) so' contam a partir
da vela de CONFIRMACAO p+k (nunca a do pivo). Pivos diarios (agregando o M30 do segmento/contrato por dia) so' contam do
pregao SEGUINTE a confirmacao. Sem informacao suficiente (NaN) => o filtro nao corta (neutro).
Funcionam com qualquer ano (so' 2026 foi rodado). Saida por figura exige `simula_x` (copia exata de W.simula + 1 gancho)."""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as W

# ---------------------------------------------------------------- simula com gancho de saida extra
_src = inspect.getsource(W.simula)
_src = _src.replace("aperta=(STOP_APERTA_N, STOP_APERTA_K)):", "aperta=(STOP_APERTA_N, STOP_APERTA_K), saida_x=None):", 1)
_src = _src.replace("    sel = d.index >= ini\n",
                    "    if saida_x is not None:\n        xl_all, xs_all, pl_all, ps_all = saida_x(d)\n    sel = d.index >= ini\n", 1)
_src = _src.replace("                sai = bool(vsl[j]) if pos == 1 else bool(vss[j])\n",
                    "                sai = bool(vsl[j]) if pos == 1 else bool(vss[j])\n"
                    "            if not sai and saida_x is not None:\n"
                    "                gj = pos0 + j\n"
                    "                sai = bool(xl_all[gj] and pl_all[gj] >= ent_g) if pos == 1 else bool(xs_all[gj] and ps_all[gj] >= ent_g)\n", 1)
_src = _src.replace("nb = 0; stop_x = -np.inf; t_ent_i = t\n", "nb = 0; stop_x = -np.inf; t_ent_i = t; ent_g = pos0 + t\n", 1)
assert _src.count("saida_x") >= 4 and "gj = pos0 + j" in _src and "ent_g = pos0 + t" in _src
exec(compile(_src, "simula_x", "exec"), W.__dict__)
simula_x = W.__dict__["simula"]


def instala_simula_x():
    """rodar_janelas chama W.simula; troca pela versao com gancho (sem saida_x = identica a original)."""
    W.simula = simula_x


# ---------------------------------------------------------------- pivos
def _atr(d):
    pc = d["c"].shift()
    tr = pd.concat([d["h"] - d["l"], (d["h"] - pc).abs(), (d["l"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().values


def pivos(x, k, alto):
    """lista (p, nivel) de pivos de x (alto=True topo) com k velas de cada lado; confirmado em p+k."""
    out = []
    n = len(x)
    for p in range(k, n - k):
        esq, dir_ = x[p - k:p], x[p + 1:p + k + 1]
        if alto and x[p] > esq.max() and x[p] >= dir_.max():
            out.append((p, x[p]))
        elif (not alto) and x[p] < esq.min() and x[p] <= dir_.min():
            out.append((p, x[p]))
    return out


def ultimos2(x, k, alto):
    """por barra t: (nivel do ultimo pivo confirmado, nivel do anterior, indice do ultimo) usando so' conf <= t."""
    n = len(x)
    pv = pivos(x, k, alto)
    a1 = np.full(n, np.nan); a2 = np.full(n, np.nan); pi = np.full(n, -1)
    j = 0; l1 = l2 = np.nan; lp = -1
    for t in range(n):
        while j < len(pv) and pv[j][0] + k <= t:
            l2, l1, lp = l1, pv[j][1], pv[j][0]
            j += 1
        a1[t], a2[t], pi[t] = l1, l2, lp
    return a1, a2, pi


def _dia_para_barra(d, arr_dia, desloca=1):
    """arr_dia indexado por pregao (ordem cronologica no segmento); barra do pregao di usa arr_dia[di-desloca]."""
    dias = d.index.normalize()
    cod = pd.factorize(dias)[0]
    out = np.full((len(d),) + arr_dia.shape[1:], np.nan)
    ok = cod - desloca >= 0
    out[ok] = arr_dia[cod[ok] - desloca]
    return out


def _diario(d):
    g = d.groupby(d.index.normalize())
    return g["h"].max().values, g["l"].min().values


# ---------------------------------------------------------------- estrutura (HH/HL)
def _struct_flags(H1, H2, L1, L2, modo):
    with np.errstate(invalid="ignore"):
        up_full = (H1 > H2) & (L1 > L2); dn_full = (H1 < H2) & (L1 < L2)
        if modo == "full":
            return up_full, dn_full, np.isnan(H1 + H2 + L1 + L2)
        if modo == "hl":      # so' fundos (compra) / topos (venda)
            return (L1 > L2), (H1 < H2), np.isnan(H1 + H2 + L1 + L2)
        if modo == "hh":      # so' topos (compra) / fundos (venda)
            return (H1 > H2), (L1 < L2), np.isnan(H1 + H2 + L1 + L2)
        if modo == "ncontra":  # nao entra contra estrutura oposta
            return ~dn_full, ~up_full, np.isnan(H1 + H2 + L1 + L2)
    raise ValueError(modo)


def feat_estrutura(d, tf, k, modo):
    """tf 'm30' ou 'dia'. Retorna (ok_compra, ok_venda)."""
    if tf == "m30":
        H1, H2, _ = ultimos2(d["h"].values, k, True)
        L1, L2, _ = ultimos2(d["l"].values, k, False)
    else:
        dh, dl = _diario(d)
        a = [ultimos2(dh, k, True), ultimos2(dl, k, False)]
        H1 = _dia_para_barra(d, a[0][0]); H2 = _dia_para_barra(d, a[0][1])
        L1 = _dia_para_barra(d, a[1][0]); L2 = _dia_para_barra(d, a[1][1])
    c, v, nan = _struct_flags(H1, H2, L1, L2, modo)
    return np.asarray(c | nan, bool), np.asarray(v | nan, bool)


# ---------------------------------------------------------------- rompimento
def _quebra_ref(d, ref):
    """(quebra_alta[t], quebra_baixa[t]) na barra t: fechamento acima da max / abaixo da min da referencia."""
    c = d["c"].values
    if isinstance(ref, int):
        mx = d["h"].rolling(ref).max().shift(1).values
        mn = d["l"].rolling(ref).min().shift(1).values
    else:
        dias = d.index.normalize()
        if ref == "dia":
            key = dias
        else:  # semana
            key = d.index.to_period("W")
        gmax = d.groupby(key)["h"].max(); gmin = d.groupby(key)["l"].min()
        ant_max = gmax.shift(1); ant_min = gmin.shift(1)
        mx = pd.Series(key, index=d.index).map(ant_max).values.astype(float)
        mn = pd.Series(key, index=d.index).map(ant_min).values.astype(float)
    with np.errstate(invalid="ignore"):
        return c > mx, c < mn


def feat_rompimento(d, ref, m, modo):
    """so_rompe: houve quebra (a favor do sinal) em alguma das ultimas m velas ate' t. nao_rompe: o complemento."""
    qa, qb = _quebra_ref(d, ref)
    ra = pd.Series(qa.astype(float)).rolling(m, min_periods=1).max().values > 0
    rb = pd.Series(qb.astype(float)).rolling(m, min_periods=1).max().values > 0
    if modo == "so_rompe":
        return ra, rb
    return ~ra, ~rb


# ---------------------------------------------------------------- distancia a barreira
def feat_barreira(d, fonte, X, olhar=40):
    """compra: nivel de pivo-topo confirmado ACIMA do fechamento mais proximo; exige (nivel-c)/ATR >= X (sem barreira = ok).
    venda: espelho com pivos-fundo abaixo. fonte ('m30',k) ou ('dia',k)."""
    c = d["c"].values; atr = _atr(d); n = len(d)
    tipo, k = fonte
    okc = np.ones(n, bool); oks = np.ones(n, bool)
    if tipo == "m30":
        ph = pivos(d["h"].values, k, True); pl = pivos(d["l"].values, k, False)
        jh = jl = 0; lh, ll = [], []
        for t in range(n):
            while jh < len(ph) and ph[jh][0] + k <= t:
                lh.append(ph[jh][1]); jh += 1
            while jl < len(pl) and pl[jl][0] + k <= t:
                ll.append(pl[jl][1]); jl += 1
            if np.isnan(atr[t]):
                continue
            acima = [x for x in lh[-olhar:] if x > c[t]]
            abaixo = [x for x in ll[-olhar:] if x < c[t]]
            if acima:
                okc[t] = (min(acima) - c[t]) / atr[t] >= X
            if abaixo:
                oks[t] = (c[t] - max(abaixo)) / atr[t] >= X
    else:
        dh, dl = _diario(d)
        ph = pivos(dh, k, True); pl = pivos(dl, k, False)
        dias = pd.factorize(d.index.normalize())[0]
        for t in range(n):
            di = dias[t]
            if np.isnan(atr[t]):
                continue
            lh = [lv for p, lv in ph if p + k <= di - 1][-olhar:]
            ll = [lv for p, lv in pl if p + k <= di - 1][-olhar:]
            acima = [x for x in lh if x > c[t]]; abaixo = [x for x in ll if x < c[t]]
            if acima:
                okc[t] = (min(acima) - c[t]) / atr[t] >= X
            if abaixo:
                oks[t] = (c[t] - max(abaixo)) / atr[t] >= X
    return okc, oks


# ---------------------------------------------------------------- congestao
def feat_compressao(d, N, q, modo):
    """razao = (max h - min l das ultimas N velas ate' t)/ATR[t]. modo 'baixo': razao <= quantil expansivo q do passado
    (shift 1, min 100 velas) ; 'alto': razao >= quantil (1-q)... (complemento aproximado: razao > q-quantil)."""
    atr = pd.Series(_atr(d), index=d.index)
    r = (d["h"].rolling(N).max() - d["l"].rolling(N).min()) / atr
    thr = r.expanding(min_periods=100).quantile(q).shift(1)
    with np.errstate(invalid="ignore"):
        ok = (r <= thr).values if modo == "baixo" else (r > thr).values
    nan = np.isnan(thr.values) | np.isnan(r.values)
    ok = np.asarray(ok | nan, bool)
    return ok, ok


def feat_contrai(d, N, f):
    """range das ultimas N velas <= f * range das N velas anteriores (triangulo/contracao)."""
    r1 = d["h"].rolling(N).max() - d["l"].rolling(N).min()
    r0 = r1.shift(N)
    with np.errstate(invalid="ignore"):
        ok = (r1 <= f * r0).values
    ok = np.asarray(ok | np.isnan(r0.values), bool)
    return ok, ok


# ---------------------------------------------------------------- saida: topo/fundo duplo contra
def saida_duplo(d, k, tol):
    """compra sai quando se confirma topo duplo: ultimo pivo-topo ~ anterior (|dif| <= tol*ATR) E aparece apos a entrada
    (pivo >= barra de entrada); venda: fundo duplo. Devolve (xl, xs, pivo_l, pivo_s) por barra de CONFIRMACAO."""
    atr = _atr(d); n = len(d)
    out = []
    for alto in (True, False):
        a1, a2, pi = ultimos2(d["h"].values if alto else d["l"].values, k, alto)
        # evento so' na barra em que o pivo e' confirmado (pi muda)
        novo = np.zeros(n, bool); novo[1:] = pi[1:] != pi[:-1]
        with np.errstate(invalid="ignore"):
            perto = np.abs(a1 - a2) <= tol * atr
        out.append((novo & perto & ~np.isnan(a2), pi))
    return out[0][0], out[1][0], out[0][1], out[1][1]


# ---------------------------------------------------------------- despacho de especificacoes
def construir(spec):
    """spec -> (extra_fn | None, saida_x_fn | None). spec = None (baseline) | (tipo, ...) | ('and', s1, s2, ...)."""
    if spec is None:
        return None, None
    t = spec[0]
    if t == "and":
        fs = [construir(s)[0] for s in spec[1:]]
        def f(d):
            ok = [g(d) for g in fs]
            return (np.logical_and.reduce([o[0] for o in ok]), np.logical_and.reduce([o[1] for o in ok]))
        return f, None
    if t == "st":
        return (lambda d: feat_estrutura(d, spec[1], spec[2], spec[3])), None
    if t == "rb":
        return (lambda d: feat_rompimento(d, spec[1], spec[2], spec[3])), None
    if t == "bar":
        return (lambda d: feat_barreira(d, spec[1], spec[2])), None
    if t == "cp":
        return (lambda d: feat_compressao(d, spec[1], spec[2], spec[3])), None
    if t == "ct":
        return (lambda d: feat_contrai(d, spec[1], spec[2])), None
    if t == "dup":
        return None, (lambda d: saida_duplo(d, spec[1], spec[2]))
    raise ValueError(spec)


def rodar(ano, d, spec):
    """roda a estrategia v2.02 + a figura `spec` sobre o M30 `d` do ano. Devolve resumo (dict)."""
    instala_simula_x()
    ex, sx = construir(spec)
    kw = {}
    if ex is not None:
        kw["extra"] = ex
    if sx is not None:
        kw["saida_x"] = sx
    tab, res = W.rodar_janelas(ano, dados=d, **kw)
    return res


# ---- candidatas congeladas: NENHUMA. Das 112 variantes (104 isoladas + 8 combinacoes), nenhuma melhorou o CONJUNTO vs v2.02
# com platô e percentil >= 90 do aleatorio (ver f2_relatorio.md). Dict vazio de proposito.
# Reproduzir qualquer linha: rodar(ano, dados_m30, spec); spec = ('st',tf,k,modo) | ('rb',ref,m,modo) | ('bar',(tipo,k),X)
#   | ('cp',N,q,modo) | ('ct',N,f) | ('dup',k,tol) | ('and',spec1,spec2).
CANDIDATAS = {}
