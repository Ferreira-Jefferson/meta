"""C2 - volume na SAIDA e como CONTEXTO (dia / mes) sobre WinCincoMedias v2 (M30). Somente 2026.
Volume so de velas FECHADAS: toda decisao na barra j usa dados[<= j]; a execucao e' na abertura de j+1.
Normalizacoes so com passado: razao vs mediana do MESMO horario nos N pregoes ANTERIORES (shift(1));
limiares por quantil EXPANDIDO do passado (shift(1)).
Controle de preco: mesma regra trocando volume por range (h-l) ou |c-o|, mesmo quantil/limiar.
"""
from __future__ import annotations
import sys as _sy; _sy.path[:0] = [r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade', r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_fases_correlacao_2026_10_06\refazer\a3\copias']
import sys, itertools, io, contextlib
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))
import win_cinco_medias_semleilao as wcm
from win_cinco_medias_semleilao import (EMAS, EMA_SAIDA, ULTIMA_ENTRADA, TTL_BARRAS, PONTO_BRL, TICK, CUSTO_RT,
                              CAPITAL, MARGEM, alinhamento, zona_ok, regime_mes)

NPREG = 20  # pregoes anteriores para a mediana do mesmo horario


# ------------------------------------------------------------------ features (so passado / barras fechadas)
def _rel_horario(s: pd.Series, n=NPREG) -> pd.Series:
    """s / mediana de s no MESMO horario dos n pregoes anteriores (a barra atual fica fora da mediana)."""
    hh = pd.Series(s.index.time, index=s.index)
    med = s.groupby(hh).transform(lambda x: x.rolling(n, min_periods=5).median().shift(1))
    return s / med


def _qexp(s: pd.Series, q: float) -> pd.Series:
    """Quantil expandido do passado (shift 1)."""
    return s.expanding(min_periods=100).quantile(q).shift(1)


def features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["rng"] = d.h - d.l
    d["body"] = (d.c - d.o).abs()
    d["dirb"] = np.sign(d.c - d.o)
    for k, col in (("v", "v"), ("r", "rng"), ("b", "body")):
        d[f"{k}_rel"] = _rel_horario(d[col])
        d[f"{k}_cru"] = d[col].astype(float)
    # acumulado do pregao ate a barra (inclui a barra fechada) vs mesmo horario dos pregoes anteriores
    dia = d.index.normalize()
    for k, col in (("v", "v"), ("r", "rng"), ("b", "body")):
        cum = d[col].groupby(dia).cumsum()
        d[f"{k}_dia"] = _rel_horario(cum)
    # contexto do mes: media diaria do mes ate ONTEM / media diaria de todos os pregoes anteriores ao mes
    for k, col in (("v", "v"), ("r", "rng")):
        diario = d[col].groupby(dia).sum()
        mes = diario.index.to_period("M")
        out = pd.Series(np.nan, index=diario.index)
        for p in mes.unique():
            ant = diario[mes < p]
            idx = diario.index[mes == p]
            if len(ant) < 15:           # comeco do ano: sem referencia -> NaN (sem restricao)
                continue
            ref = ant.mean()
            for i, dd in enumerate(idx):
                if i < 3:                # menos de 3 pregoes do mes ate ontem -> NaN
                    continue
                out[dd] = diario[idx[:i]].mean() / ref
        d[f"{k}_mes"] = out.reindex(dia).values
    return d


def thr_q(d, col, q):
    return _qexp(d[col].astype(float), q).values


# ------------------------------------------------------------------ simula (copia de win_cinco_medias.simula + saida_fn/reg_fn)
def simula(d, ini, fim=None, rolagem=None, periodos=EMAS, inclina=None, zona=None, ema_saida=EMA_SAIDA,
           filtro_mes=True, extra=None, saida_fn=None, saida_escopo="todos", reg_fn=None):
    """saida_fn(d) -> (sai_long, sai_short): bool por barra FECHADA j (usa so d[<=j]); se a posicao
    esta aberta e a flag do lado dela e' True em j, sai na abertura de j+1 (a mercado, 1 tick de deslize).
    saida_escopo: 'todos' | 'favor' (so operacoes a favor do regime) | 'neutro'."""
    est_all = alinhamento(d, periodos, inclina)
    zl_all, zs_all = zona_ok(d, periodos, zona)
    if extra is not None:
        el, es_ = extra(d)
        zl_all = zl_all & np.asarray(el, bool); zs_all = zs_all & np.asarray(es_, bool)
    reg_all = regime_mes(d, rolagem) if filtro_mes else np.zeros(len(d), dtype=int)
    if reg_fn is not None:
        reg_all = reg_fn(d, reg_all)
    e_saida_all = d["c"].ewm(span=ema_saida, adjust=False).mean().values
    if saida_fn is not None:
        sl_all, ss_all = saida_fn(d)
        sl_all = np.asarray(sl_all, bool); ss_all = np.asarray(ss_all, bool)
    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    o, h, l, c = (d[k].values[sel] for k in "ohlc")
    est, reg, e_saida = est_all[sel], reg_all[sel], e_saida_all[sel]
    zl, zs = zl_all[sel], zs_all[sel]
    if saida_fn is not None:
        sl, ss = sl_all[sel], ss_all[sel]
    dias, hora, n = idx.normalize(), idx.time, len(idx)
    ult = d["ultima_continua"].to_numpy(bool)[sel] if "ultima_continua" in d.columns else None

    caixa = CAPITAL
    trades, curva = [], np.empty(n)
    pos = 0; preco = 0.0; a_favor = False; t_ent = None
    pend = 0; limite = 0.0; ttl = 0; pend_favor = False

    def fecha(saida, t):
        nonlocal caixa, pos
        pts = pos * (saida - preco)
        pnl = pts * PONTO_BRL - CUSTO_RT
        caixa += pnl
        trades.append(dict(entrada=t_ent, saida=idx[t], lado=pos, a_favor=a_favor, pts=pts, pnl=pnl))
        pos = 0

    for t in range(n):
        novo_dia = t == 0 or dias[t] != dias[t - 1]
        if novo_dia:
            pend = 0
        if pos and t > 0 and not novo_dia:
            j = t - 1
            if hora[j] >= ULTIMA_ENTRADA:
                sai = True
            elif a_favor:
                sai = pos * (c[j] - e_saida[j]) <= 0
            else:
                sai = est[j] != pos
            if (not sai) and saida_fn is not None and (
                    saida_escopo == "todos" or (saida_escopo == "favor" and a_favor)
                    or (saida_escopo == "neutro" and not a_favor)):
                sai = bool(sl[j]) if pos == 1 else bool(ss[j])
            if sai:
                fecha(o[t] - pos * TICK, t)
        if pend and not pos:
            if (pend == 1 and l[t] <= limite) or (pend == -1 and h[t] >= limite):
                if caixa >= MARGEM:
                    pos, a_favor, t_ent = pend, pend_favor, idx[t]
                    preco = min(limite, o[t]) if pend == 1 else max(limite, o[t])
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        if (not pos and not pend and est[t] != 0 and hora[t] < ULTIMA_ENTRADA and reg[t] in (est[t], 0)
                and (zl[t] if est[t] == 1 else zs[t])):
            pend, limite, ttl = est[t], c[t], TTL_BARRAS
            pend_favor = reg[t] == est[t]
        if pos and (t == n - 1 or dias[t + 1] != dias[t] or (ult is not None and ult[t])):
            fecha(c[t] - pos * TICK, t)
        curva[t] = caixa
    return pd.DataFrame(trades), pd.Series(curva, index=idx)


wcm.simula = simula   # rodar_janelas passa a usar a copia estendida


# ------------------------------------------------------------------ construcao das variantes
METRICAS_SAIDA = ["v_rel", "v_cru", "r_rel", "r_cru", "b_rel"]
CTRL = {"v_rel": "r_rel", "v_cru": "r_cru"}   # controle de preco correspondente


def fn_climax(metrica, q, sentido):
    """sentido 'contra': vela fechada com metrica >= quantil q e corpo CONTRA a posicao.
    'favor': idem com corpo A FAVOR (exaustao)."""
    def f(d):
        m = d[metrica].values; th = thr_q(d, metrica, q)
        big = (m >= th) & ~np.isnan(th) & ~np.isnan(m)
        up, dn = d.dirb.values > 0, d.dirb.values < 0
        if sentido == "contra":
            return big & dn, big & up         # long sai se vela de baixa; short sai se vela de alta
        return big & up, big & dn
    return f


def fn_secagem(metrica, modo, k, lim=None):
    def f(d):
        m = d[metrica]
        if modo == "queda":
            flag = pd.Series(True, index=d.index)
            for i in range(k):
                flag &= m.shift(i) < m.shift(i + 1)
        else:
            flag = (m < lim).rolling(k).sum() == k
        a = flag.fillna(False).values
        return a, a
    return f


def extra_dia(metrica, thr, sentido):
    def f(d):
        m = d[metrica].values
        ok = (m >= thr) if sentido == "alto" else (m <= thr)
        ok = np.where(np.isnan(m), False, ok)
        return ok, ok
    return f


def _mes_alto(d, metrica, thr, alto):
    m = d[metrica].values
    cond = (m >= thr) if alto else (m < thr)
    return np.where(np.isnan(m), True, cond)    # sem referencia (comeco do ano) = sem restricao


def extra_mes_so(metrica, thr, alto):
    def f(d):
        ok = _mes_alto(d, metrica, thr, alto)
        return ok, ok
    return f


def reg_mes_em(metrica, thr, alto):
    """filtro de lado so vale nos meses 'alto' (ou 'baixo'); nos demais regime=0 (os dois lados)."""
    def f(d, reg):
        ok = _mes_alto(d, metrica, thr, alto)
        return np.where(ok, reg, 0)
    return f


def variantes():
    V = {}
    for m, q, esc in itertools.product(METRICAS_SAIDA, (0.80, 0.90, 0.95), ("favor", "todos")):
        V[f"climaxCONTRA|{m}|q{int(q*100)}|{esc}"] = dict(saida_fn=fn_climax(m, q, "contra"), saida_escopo=esc)
        V[f"climaxFAVOR|{m}|q{int(q*100)}|{esc}"] = dict(saida_fn=fn_climax(m, q, "favor"), saida_escopo=esc)
    for m, esc in itertools.product(("v_rel", "r_rel", "b_rel"), ("favor", "todos")):
        for k in (2, 3, 4):
            V[f"secagemQUEDA|{m}|k{k}|{esc}"] = dict(saida_fn=fn_secagem(m, "queda", k), saida_escopo=esc)
        for k, lim in itertools.product((2, 3), (0.6, 0.8)):
            V[f"secagemABAIXO|{m}|k{k}|<{lim}|{esc}"] = dict(saida_fn=fn_secagem(m, "abaixo", k, lim), saida_escopo=esc)
    for m, thr, s in itertools.product(("v_dia", "r_dia", "b_dia"), (0.8, 0.9, 1.0, 1.1, 1.2, 1.3), ("alto", "baixo")):
        V[f"dia|{m}|{s}|{thr}"] = dict(extra=extra_dia(m, thr, s))
    for m, thr, modo in itertools.product(("v_mes", "r_mes"), (0.9, 1.0, 1.1),
                                          ("so_alto", "so_baixo", "filtro_so_alto", "filtro_so_baixo")):
        alto = modo.endswith("alto")
        if modo.startswith("so_"):
            V[f"mes|{m}|{modo}|{thr}"] = dict(extra=extra_mes_so(m, thr, alto))
        else:
            V[f"mes|{m}|{modo}|{thr}"] = dict(reg_fn=reg_mes_em(m, thr, alto))
    return V


def controle_de(nome):
    p = nome.split("|")
    if p[1] in CTRL:
        return "|".join([p[0], CTRL[p[1]]] + p[2:])
    if p[1] == "v_dia": return "|".join([p[0], "r_dia"] + p[2:])
    if p[1] == "v_mes": return "|".join([p[0], "r_mes"] + p[2:])
    return None


# ------------------------------------------------------------------ execucao
_D = None
def _init():
    global _D
    _D = features(wcm.carregar(2026))


def _run(nome):
    kw = variantes()[nome] if nome != "BASE" else {}
    with contextlib.redirect_stdout(io.StringIO()):
        df, r = wcm.rodar_janelas(2026, dados=_D, **kw)
    return nome, df, r


def main():
    from concurrent.futures import ProcessPoolExecutor, as_completed
    _init()
    nomes = ["BASE"] + list(variantes())
    print(f"variantes (sem BASE): {len(nomes)-1}", flush=True)
    res = {}
    with ProcessPoolExecutor(max_workers=6, initializer=_init) as ex:
        fut = [ex.submit(_run, n) for n in nomes]
        for f in as_completed(fut):
            n, df, r = f.result(); res[n] = (df, r)
            print(f"{n:48s} liq {r['liquido']:9.2f} jan+ {r['janelas_pos']:>5s} pior {r['pior']:8.2f} "
                  f"tr {r['trades']:4d} PF {r['PF']} DD {r['maior_DD']:7.2f} semset {r['liquido_sem_set']:8.2f}", flush=True)
    bdf, br = res["BASE"]
    print("\nBASE", br, flush=True)
    assert abs(br["liquido"] - 7349.90) < 0.01 and br["trades"] == 241, "copia nao reproduz o baseline"
    rows = []
    for n, (df, r) in res.items():
        melhora = int((df.liquido.values > bdf.liquido.values).sum()) if len(df) == len(bdf) else -1
        rows.append(dict(nome=n, liquido=r["liquido"], jan=r["janelas_pos"], pior=r["pior"], trades=r["trades"],
                         PF=r["PF"], DD=r["maior_DD"], semset=r["liquido_sem_set"], meses_melhor=melhora))
    T = pd.DataFrame(rows).set_index("nome")
    T.to_csv(Path(__file__).with_name("c2_resultados.csv"), sep=";", decimal=",")
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    print("\n=== TODAS (ordenadas por liquido) ===")
    print(T.sort_values("liquido", ascending=False).to_string())
    print("\n=== Pre-filtro (liq>base, pior>=base, DD<=base, trades>=150) com controle ===")
    for n, row in T.iterrows():
        if n == "BASE": continue
        if row.liquido > br["liquido"] and row.pior >= br["pior"] and row.DD <= br["maior_DD"] and row.trades >= 150:
            c = controle_de(n); cr = T.loc[c] if c in T.index else None
            print(n, dict(row), "| CONTROLE", c, None if cr is None else (cr.liquido, cr.jan, cr.pior, cr.DD, cr.meses_melhor))
    import pickle
    pickle.dump({n: (df, r) for n, (df, r) in res.items()}, open(Path(__file__).with_name("c2_res.pkl"), "wb"))


if __name__ == "__main__":
    main()
