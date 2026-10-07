"""d2_alvo: familia ALVO sobre WinCincoMedias v2.01 (so 2026). Copia estendida de simula.
Alvo = ordem-limite: enche so se o preco NEGOCIAR 1 tick alem do nivel; preco = nivel (ou abertura se abre alem);
sem slippage de saida; saidas EMA4/quebra/volume/fim do pregao mantidas (tem prioridade, 'desfavoravel primeiro').
Niveis calculados no fechamento da barra t valem a partir de t+1; na barra da entrada o alvo so vale a partir da seguinte."""
from __future__ import annotations
import sys, math
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as wcm
from win_cinco_medias import (EMAS, EMA_SAIDA, SAIDA_VOL, SAIDA_VOL_Q, VOL_MIN_HIST, TTL_BARRAS, ULTIMA_ENTRADA,
                              PONTO_BRL, TICK, CUSTO_RT, CAPITAL, MARGEM, alinhamento, zona_ok, regime_mes,
                              colunas_volume, carregar, rolagens)


def atr14(d):
    pc = d["c"].shift(1)
    tr = pd.concat([d.h - d.l, (d.h - pc).abs(), (d.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()


def _tick_up(x): return math.ceil(x / TICK - 1e-9) * TICK
def _tick_dn(x): return math.floor(x / TICK + 1e-9) * TICK


def simula_alvo(d, ini, fim=None, rolagem=None, periodos=EMAS, inclina=None, zona=None,
                ema_saida=EMA_SAIDA, filtro_mes=True, extra=None, saida_vol=SAIDA_VOL, alvo=None):
    """alvo: None | ('fixo',k) | ('trail',k,j) | ('contra',N,kk) | ('estr','dia'|n)."""
    est_all = alinhamento(d, periodos, inclina)
    zl_all, zs_all = zona_ok(d, periodos, zona)
    reg_all = regime_mes(d, rolagem) if filtro_mes else np.zeros(len(d), dtype=int)
    e_saida_all = d["c"].ewm(span=ema_saida, adjust=False).mean().values
    if saida_vol:
        if "vrel" not in d.columns:
            d = colunas_volume(d)
        vthr = d["vrel"].expanding(min_periods=VOL_MIN_HIST).quantile(SAIDA_VOL_Q).shift(1)
        grande = (d["vrel"] >= vthr).fillna(False).values & vthr.notna().values
        corpo = np.sign(d["c"] - d["o"]).values
        vsl_all, vss_all = grande & (corpo < 0), grande & (corpo > 0)
    atr_all = atr14(d).values
    dia_all = d.index.normalize()
    dh = d["h"].groupby(dia_all).max(); dl = d["l"].groupby(dia_all).min()
    pdh = pd.Series(dia_all, index=d.index).map(dh.shift(1)).values
    pdl = pd.Series(dia_all, index=d.index).map(dl.shift(1)).values
    modo = alvo[0] if alvo else None
    if modo == "estr" and alvo[1] != "dia":
        nbar_h = d["h"].rolling(alvo[1]).max().values; nbar_l = d["l"].rolling(alvo[1]).min().values
    else:
        nbar_h = nbar_l = np.full(len(d), np.nan)
    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    o, h, l, c = (d[k].values[sel] for k in "ohlc")
    est, reg, e_saida = est_all[sel], reg_all[sel], e_saida_all[sel]
    zl, zs = zl_all[sel], zs_all[sel]
    atr = atr_all[sel]; PDH = pdh[sel]; PDL = pdl[sel]; NH = nbar_h[sel]; NL = nbar_l[sel]
    if saida_vol:
        vsl, vss = vsl_all[sel], vss_all[sel]
    dias, hora, n = idx.normalize(), idx.time, len(idx)
    caixa = CAPITAL
    trades, curva = [], np.empty(n)
    pos = 0; preco = 0.0; a_favor = False; t_ent = None
    pend = 0; limite = 0.0; ttl = 0; pend_favor = False; pend_atr = np.nan; pend_sig_t = 0
    tgt = None; ent_i = -1; atr_e = np.nan; ext = 0.0; neg = 0

    def fecha(saida, t, por_alvo=False):
        nonlocal caixa, pos, tgt
        pts = pos * (saida - preco)
        pnl = pts * PONTO_BRL - CUSTO_RT
        caixa += pnl
        trades.append(dict(entrada=t_ent, saida=idx[t], lado=pos, a_favor=a_favor, pts=pts, pnl=pnl, alvo=por_alvo))
        pos = 0; tgt = None

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
                fecha(o[t] - pos * TICK, t)
        if pos and tgt is not None and ent_i < t:
            if pos == 1 and h[t] >= tgt + TICK:
                fecha(max(tgt, o[t]), t, True)
            elif pos == -1 and l[t] <= tgt - TICK:
                fecha(min(tgt, o[t]), t, True)
        if pend and not pos:
            if (pend == 1 and l[t] <= limite) or (pend == -1 and h[t] >= limite):
                if caixa >= MARGEM:
                    pos, a_favor, t_ent = pend, pend_favor, idx[t]
                    preco = min(limite, o[t]) if pend == 1 else max(limite, o[t])
                    ent_i = t; atr_e = pend_atr; tgt = None; neg = 0
                    ext = h[t] if pos == 1 else l[t]
                    if alvo and not np.isnan(atr_e):
                        if modo in ("fixo", "trail"):
                            k = alvo[1]
                            tgt = _tick_up(preco + k * atr_e) if pos == 1 else _tick_dn(preco - k * atr_e)
                        elif modo == "estr":
                            if alvo[1] == "dia":
                                lv = PDH[pend_sig_t] if pos == 1 else PDL[pend_sig_t]
                            else:
                                lv = NH[pend_sig_t] if pos == 1 else NL[pend_sig_t]
                            if lv == lv and ((pos == 1 and lv > preco + 2 * TICK) or (pos == -1 and lv < preco - 2 * TICK)):
                                tgt = _tick_up(lv) if pos == 1 else _tick_dn(lv)
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        if (not pos and not pend and est[t] != 0 and hora[t] < ULTIMA_ENTRADA and reg[t] in (est[t], 0)
                and (zl[t] if est[t] == 1 else zs[t])):
            pend, limite, ttl = est[t], c[t], TTL_BARRAS
            pend_favor = reg[t] == est[t]; pend_atr = atr[t]; pend_sig_t = t
        # fim da barra t: atualiza niveis (valem de t+1)
        if pos and ent_i <= t and alvo and not np.isnan(atr_e):
            if modo == "trail":
                if pos == 1 and h[t] > ext:
                    ext = h[t]; tgt = max(tgt if tgt is not None else -1e18, _tick_up(ext + alvo[2] * atr_e))
                elif pos == -1 and l[t] < ext:
                    ext = l[t]; tgt = min(tgt if tgt is not None else 1e18, _tick_dn(ext - alvo[2] * atr_e))
            elif modo == "contra" and tgt is None:
                neg = neg + 1 if pos * (c[t] - preco) < 0 else 0
                if neg >= alvo[1]:
                    kk = alvo[2]
                    tgt = _tick_up(preco + kk * atr_e) if pos == 1 else _tick_dn(preco - kk * atr_e)
        if pos and (t == n - 1 or dias[t + 1] != dias[t]):
            fecha(c[t] - pos * TICK, t)
        curva[t] = caixa
    return pd.DataFrame(trades), pd.Series(curva, index=idx)


def rodar(d, ano=2026, **kw):
    rol = rolagens(ano)
    linhas, todos = [], []
    for k in range(len(rol) - 1):
        seg = d[rol[k]:rol[k + 1] - pd.Timedelta(minutes=1)]
        dias = sorted(set(seg.index.normalize()))
        if len(dias) < 4: continue
        ini_op, ult = dias[3], dias[-1]
        for mes in pd.period_range(ini_op, ult, freq="M"):
            a = max(ini_op, mes.start_time); z = min(mes.end_time, ult + pd.Timedelta(days=1))
            if not len(seg[a:z]): continue
            tr, cv = simula_alvo(seg, a, z, **kw)
            linhas.append(dict(janela=f"{mes} {a:%d}", liquido=round(cv.iloc[-1] - CAPITAL, 2),
                               maxDD=round(float((cv.cummax() - cv).max()), 2)))
            if len(tr): todos.append(tr)
    df = pd.DataFrame(linhas); t = pd.concat(todos)
    g, p = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl < 0].sum()
    w, ls = t.pnl[t.pnl > 0], t.pnl[t.pnl < 0]
    sem = df[~df.janela.str.startswith(f"{ano}-09")]
    res = dict(liquido=round(df.liquido.sum(), 2), jan=f"{(df.liquido > 0).sum()}/{len(df)}", pior=round(df.liquido.min(), 2),
               PF=round(g / p, 2), acerto=round(100 * (t.pnl > 0).mean(), 1), payoff=round(w.mean() / -ls.mean(), 2),
               trades=len(t), DD=round(df.maxDD.max(), 2), sem_set=round(sem.liquido.sum(), 2), n_alvo=int(t.alvo.sum()))
    return df, res


_D = None
def _dados():
    global _D
    if _D is None:
        _D = colunas_volume(carregar(2026))
    return _D


def unidade(nome, alvo):
    df, r = rodar(_dados(), alvo=alvo)
    return nome, r, df.liquido.tolist(), df.janela.tolist()


def variantes():
    v = [("base", None)]
    v += [(f"fixo k={k}", ("fixo", k)) for k in (1, 2, 3, 4, 6, 8)]
    v += [(f"trail k={k} j={j}", ("trail", k, j)) for k in (2, 4, 8) for j in (0.5, 1, 2)]
    v += [(f"contra N={N} kk={kk}", ("contra", N, kk)) for N in (2, 3, 4) for kk in (0, 0.25)]
    v += [("estr dia ant", ("estr", "dia"))] + [(f"estr {n}barras", ("estr", n)) for n in (10, 20, 40)]
    return v


if __name__ == "__main__":
    vs = variantes(); res = {}
    with ProcessPoolExecutor(max_workers=6) as ex:
        fs = [ex.submit(unidade, n, a) for n, a in vs]
        for f in as_completed(fs):
            n, r, m, jn = f.result(); res[n] = (r, m, jn)
            print(n, r, flush=True)
    base = res["base"][1]
    print("\n=== TABELA ===")
    print(f"{'variante':22}{'liq':>9}{'jan':>6}{'pior':>9}{'PF':>6}{'acerto':>7}{'payoff':>7}{'trades':>7}{'DD':>8}{'semSet':>9}{'alvo':>5}{'mesesMelh':>10}")
    for n, _ in vs:
        r, m, _j = res[n]
        melh = sum(1 for a, b in zip(m, base) if a > b + 1e-9)
        print(f"{n:22}{r['liquido']:9.2f}{r['jan']:>6}{r['pior']:9.2f}{r['PF']:6}{r['acerto']:7}{r['payoff']:7}{r['trades']:7}{r['DD']:8.2f}{r['sem_set']:9.2f}{r['n_alvo']:5}{melh:>7}/{len(m)}", flush=True)
    jn = res["base"][2]
    print("\n=== MES A MES (liquido) ===")
    print(f"{'variante':22}" + "".join(f"{j[:7]:>9}" for j in jn))
    for n, _ in vs:
        print(f"{n:22}" + "".join(f"{x:9.1f}" for x in res[n][1]))
