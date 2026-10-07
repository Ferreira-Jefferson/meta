"""D1 - familia STOP sobre WinCincoMedias v2.01 (so 2026). Copia estendida de `simula`.
stop=None -> identica ao baseline. stop = dict(init=k, be=m, trail=k, trailn=N, aperta=(N,k), widen=(N,ka,kb)).
Stop a mercado: gatilho no toque; preco = nivel -/+ 1 tick; gap -> abertura. Niveis so com barras FECHADAS
(nivel calculado no fechamento de t vale a partir de t+1); na barra da entrada vale o stop inicial.
Barra do stop: conta o stop antes de qualquer saida favoravel (fecho do pregao)."""
from __future__ import annotations
import sys as _sy; _sy.path[:0] = [r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade', r'C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_fases_correlacao_2026_10_06\refazer\a3\copias']
import sys, itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias_semleilao as wcm
from win_cinco_medias_semleilao import (alinhamento, zona_ok, regime_mes, colunas_volume, CAPITAL, MARGEM, PONTO_BRL, TICK,
                              CUSTO_RT, TTL_BARRAS, ULTIMA_ENTRADA, EMAS, EMA_SAIDA, SAIDA_VOL, SAIDA_VOL_Q)

COLETA: list = []   # trades coletados (diagnostico, processo unico)


def atr14(d):
    c1 = d["c"].shift(1)
    tr = pd.concat([d["h"] - d["l"], (d["h"] - c1).abs(), (d["l"] - c1).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().values


def simula(d, ini, fim=None, rolagem=None, periodos=EMAS, inclina=None, zona=None,
           ema_saida=EMA_SAIDA, filtro_mes=True, extra=None, saida_vol=SAIDA_VOL, stop=None):
    st = stop or {}
    est_all = alinhamento(d, periodos, inclina)
    zl_all, zs_all = zona_ok(d, periodos, zona)
    if extra is not None:
        el, es_ = extra(d)
        zl_all = zl_all & np.asarray(el, bool); zs_all = zs_all & np.asarray(es_, bool)
    reg_all = regime_mes(d, rolagem) if filtro_mes else np.zeros(len(d), dtype=int)
    e_saida_all = d["c"].ewm(span=ema_saida, adjust=False).mean().values
    atr_all = atr14(d)
    if saida_vol:
        if "vrel" not in d.columns:
            d = colunas_volume(d)
        vthr = d["vrel"].expanding(min_periods=wcm.VOL_MIN_HIST).quantile(SAIDA_VOL_Q).shift(1)
        grande = (d["vrel"] >= vthr).fillna(False).values & vthr.notna().values
        corpo = np.sign(d["c"] - d["o"]).values
        vsl_all, vss_all = grande & (corpo < 0), grande & (corpo > 0)
    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    pos0 = int(np.flatnonzero(sel)[0]) if sel.any() else 0
    L, H = d["l"].values, d["h"].values            # arrays completos (indice absoluto g = pos0 + t)
    o, h, l, c = (d[k].values[sel] for k in "ohlc")
    est, reg, e_saida = est_all[sel], reg_all[sel], e_saida_all[sel]
    zl, zs = zl_all[sel], zs_all[sel]
    if saida_vol:
        vsl, vss = vsl_all[sel], vss_all[sel]
    dias, hora, n = idx.normalize(), idx.time, len(idx)
    ult = d["ultima_continua"].to_numpy(bool)[sel] if "ultima_continua" in d.columns else None

    caixa = CAPITAL
    trades, curva = [], np.empty(n)
    pos = 0; preco = 0.0; a_favor = False; t_ent = None
    pend = 0; limite = 0.0; ttl = 0; pend_favor = False
    atr_e = np.nan; ex = 0.0; nb = 0; best_x = 0.0; be_on = False
    s_tr = -np.inf; s_trn = -np.inf; s_ap = -np.inf
    mae = mfe = 0.0; t_ent_i = 0

    def fecha(saida, t, mot):
        nonlocal caixa, pos
        pts = pos * (saida - preco)
        pnl = pts * PONTO_BRL - CUSTO_RT
        caixa += pnl
        trades.append(dict(entrada=t_ent, saida=idx[t], lado=pos, a_favor=a_favor, pts=pts, pnl=pnl,
                           atr=atr_e, mae=mae, mfe=mfe, motivo=mot, barras=nb))
        pos = 0

    def nivel():
        """stop (x-space) valido para a proxima barra, so com info de barras fechadas."""
        s = -np.inf
        if np.isnan(atr_e):
            return s
        if "init" in st:
            s = max(s, ex - st["init"] * atr_e)
        if "widen" in st:
            wn, ka, kb = st["widen"]
            s = max(s, ex - (ka if nb < wn else kb) * atr_e)
        if be_on:
            s = max(s, ex)
        return max(s, s_tr, s_trn, s_ap)

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
            if not sai and saida_vol:
                sai = bool(vsl[j]) if pos == 1 else bool(vss[j])
            if sai:
                sx = nivel() if st else -np.inf
                fecha(o[t] - pos * TICK, t, "stop" if pos * o[t] <= sx else "regra")
        if pend and not pos:
            if (pend == 1 and l[t] <= limite) or (pend == -1 and h[t] >= limite):
                if caixa >= MARGEM:
                    pos, a_favor, t_ent = pend, pend_favor, idx[t]
                    preco = min(limite, o[t]) if pend == 1 else max(limite, o[t])
                    g = pos0 + t
                    atr_e = atr_all[g - 1] if g >= 1 else np.nan
                    ex = pos * preco; nb = 0; best_x = ex; be_on = False
                    s_tr = s_trn = s_ap = -np.inf; mae = mfe = 0.0; t_ent_i = t
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        # stop dentro da barra t (posicao mantida durante a barra)
        if pos and st:
            sx = nivel()
            if sx > -np.inf:
                ox = pos * o[t]
                lox = l[t] if pos == 1 else -h[t]
                if t == t_ent_i:               # barra da entrada: sem gap
                    if lox <= sx:
                        fecha(pos * (sx - TICK), t, "stop")
                elif ox <= sx:
                    fecha(o[t], t, "stop")
                elif lox <= sx:
                    fecha(pos * (sx - TICK), t, "stop")
        if (not pos and not pend and est[t] != 0 and hora[t] < ULTIMA_ENTRADA and reg[t] in (est[t], 0)
                and (zl[t] if est[t] == 1 else zs[t])):
            pend, limite, ttl = est[t], c[t], TTL_BARRAS
            pend_favor = reg[t] == est[t]
        if pos:
            adv = (preco - l[t]) if pos == 1 else (h[t] - preco)
            fav = (h[t] - preco) if pos == 1 else (preco - l[t])
            mae = max(mae, adv); mfe = max(mfe, fav)
        if pos and (t == n - 1 or dias[t + 1] != dias[t] or (ult is not None and ult[t])):
            fecha(c[t] - pos * TICK, t, "regra")
        if pos and st:
            nb += 1
            cx = pos * c[t]
            best_x = max(best_x, cx)
            if not np.isnan(atr_e):
                if "be" in st and best_x - ex >= st["be"] * atr_e:
                    be_on = True
                if "trail" in st:
                    s_tr = max(s_tr, best_x - st["trail"] * atr_e)
                if "trailn" in st:
                    N = st["trailn"]; a = pos0 + t - N + 1
                    if a >= 0:
                        lowx = (L[a:pos0 + t + 1] if pos == 1 else -H[a:pos0 + t + 1]).min()
                        s_trn = max(s_trn, lowx)
                if "aperta" in st:
                    an, ak = st["aperta"]
                    if nb >= an and cx - ex < 0:
                        s_ap = max(s_ap, ex - ak * atr_e)
        curva[t] = caixa
    tr = pd.DataFrame(trades)
    COLETA.append(tr)
    return tr, pd.Series(curva, index=idx)


def rodar(dados, ano=2026, **kw):
    old = wcm.simula
    wcm.simula = simula
    try:
        return wcm.rodar_janelas(ano, dados=dados, **kw)
    finally:
        wcm.simula = old


# ---- execucao paralela das variantes -------------------------------------------------
_D = None


def _init():
    global _D
    _D = colunas_volume(wcm.carregar(2026))


def _run(nome, st):
    df, r = rodar(_D, 2026, stop=st)
    return nome, st, df, r


def montar():
    V = {}
    for k in (0.5, 1, 1.5, 2, 3): V[f"init k={k}"] = dict(init=k)
    for m in (0.5, 1, 1.5, 2): V[f"BE m={m}"] = dict(be=m)
    for k in (1, 1.5, 2, 3): V[f"trail k={k}"] = dict(trail=k)
    for N in (2, 3, 5): V[f"trailN N={N}"] = dict(trailn=N)
    for N, k in itertools.product((2, 4, 8), (0.5, 1, 1.5)): V[f"aperta N={N} k={k}"] = dict(aperta=(N, k))
    for N, ka, kb in itertools.product((2, 4), (0.5, 1), (2, 3)): V[f"afasta N={N} ka={ka} kb={kb}"] = dict(widen=(N, ka, kb))
    return V


def montar2():
    """estagio 2: plateau de 'aperta' (N x k) e combinacoes pequenas."""
    V = {}
    for N, k in itertools.product((1, 2, 3), (0.75, 1.0, 1.25, 2.0)):
        V[f"aperta N={N} k={k}"] = dict(aperta=(N, k))
    V["aperta N=1 k=0.5"] = dict(aperta=(1, 0.5)); V["aperta N=1 k=1"] = dict(aperta=(1, 1)); V["aperta N=1 k=1.5"] = dict(aperta=(1, 1.5))
    V["aperta N=3 k=0.5"] = dict(aperta=(3, 0.5)); V["aperta N=3 k=1"] = dict(aperta=(3, 1)); V["aperta N=3 k=1.5"] = dict(aperta=(3, 1.5))
    A = (2, 1)
    for k in (1.5, 2): V[f"aperta(2,1)+init {k}"] = dict(aperta=A, init=k)
    for m in (1, 1.5): V[f"aperta(2,1)+BE {m}"] = dict(aperta=A, be=m)
    for k in (1.5, 3): V[f"aperta(2,1)+trail {k}"] = dict(aperta=A, trail=k)
    V["aperta(2,1)+init1.5+trail3"] = dict(aperta=A, init=1.5, trail=3)
    V["aperta(2,1)+init1.5+BE1"] = dict(aperta=A, init=1.5, be=1)
    V["aperta(2,1.5)+init1.5"] = dict(aperta=(2, 1.5), init=1.5)
    V["init1.5+BE1"] = dict(init=1.5, be=1)
    V["init1.5+trail1.5"] = dict(init=1.5, trail=1.5)
    return V


def varrer(V):
    res = {}
    with ProcessPoolExecutor(max_workers=6, initializer=_init) as ex:
        fs = [ex.submit(_run, k, v) for k, v in V.items()]
        for f in as_completed(fs):
            nome, st, df, r = f.result()
            res[nome] = (st, df, r)
            print(f"{nome:34s} liq {r['liquido']:9.2f} jan {r['janelas_pos']:>5s} pior {r['pior']:8.2f} PF {r['PF']} "
                  f"trd {r['trades']} DD {r['maior_DD']:.2f} semSet {r['liquido_sem_set']:.2f}", flush=True)
    return res


if __name__ == "__main__":
    import pickle
    d = colunas_volume(wcm.carregar(2026))
    COLETA.clear()
    df0, r0 = rodar(d, 2026, stop=None)
    print("COPIA DESLIGADA:", r0, flush=True)
    assert abs(r0["liquido"] - 7805.20) < 0.005 and r0["trades"] == 248, "NAO reproduz o baseline"
    T = pd.concat([x for x in COLETA if len(x)], ignore_index=True)
    T.to_pickle(Path(__file__).with_name("d1_trades_base.pkl"))
    df0.to_pickle(Path(__file__).with_name("d1_df_base.pkl"))
    print("trades diag:", len(T), flush=True)
    est = sys.argv[1] if len(sys.argv) > 1 else "1"
    V = montar() if est == "1" else montar2()
    if est == "2":
        V = {k: v for k, v in V.items() if k not in montar()}
    res = varrer(V)
    pickle.dump(res, open(Path(__file__).with_name(f"d1_res_stage{est}.pkl"), "wb"))
    print(f"N VARIANTES estagio {est}:", len(V), flush=True)
