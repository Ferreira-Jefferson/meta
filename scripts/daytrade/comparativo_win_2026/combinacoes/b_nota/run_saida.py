"""Frente B, partes 2 e 4: tamanho de alvo/stop pela nota (re-simulacao nos ticks com saida.py, MESMA entrada) e pela volatilidade
esperada do horario (ideia 6). Saida: saida_res.pkl.

RetEma34 tem stop e alvo proprios fixos (stop 0,45L, alvo 0,90L; o EA ainda aproxima o alvo com o tempo, o que a re-simulacao NAO
reproduz -> a base de comparacao e' a propria re-simulacao com multiplicadores (1,1), nao o CSV original).
Win/Win_c1/Cinco/Desloc tem saidas dinamicas (canal, esticada, stop que persegue a media): nao da' para ALARGAR; so' se testa um
stop-teto extra (overlay) de sc x ATR M5 nas entradas de nota baixa: sai no overlay se ele disparar ANTES da saida original.
"""
import pickle, time
import numpy as np
import pandas as pd
from comum import *
import saida as S
import dados as DD
from functools import lru_cache
S._ticks = lru_cache(maxsize=None)(S._ticks.__wrapped__)   # cache de todos os pregoes (o original guarda so 16)

rng = np.random.default_rng(11)
F = pickle.load(open(AQ / "filtro_res.pkl", "rb"))
e = F["e"]; P = F["P"]
mes = e.mes.to_numpy(); est = e.estrategia.to_numpy(); rs = e.rs.to_numpy()
N = len(e)
TICK = 5.0
def arred(x): return np.maximum(np.round(np.asarray(x, float) / TICK) * TICK, TICK)

# ------------------------------------------------------------------ RetEma34: re-simulacao
niv = pd.read_csv(AQ / "retema34_niveis.csv")
r_idx = np.flatnonzero(est == "WinRetanguloEma34")
er = e.iloc[r_idx].reset_index(drop=True)
m_ = er.merge(niv[["t_ent", "stop_pts", "alvo0_pts"]], left_on="t_entrada_ms", right_on="t_ent", how="left")
assert m_.stop_pts.notna().all() and len(m_) == len(er), "join dos niveis falhou"
STOP0 = m_.stop_pts.to_numpy(); ALVO0 = m_.alvo0_pts.to_numpy()
LADO = er.lado.to_numpy(); PE = er.preco_entrada.to_numpy(); TE = er.t_entrada_ms.to_numpy()

def resim(sm, am):
    """-> rs bruto (R$) por trade do RetEma34, com stop*sm e alvo*am (escalares ou vetores)."""
    o = S.simula_saida_lote(TE, LADO, PE, arred(STOP0 * sm), arred(ALVO0 * am), hora_zera="17:00", alvo_limite=True)
    return o.pontos.to_numpy() * RS_PT

t0 = time.time()
base_r = resim(1.0, 1.0)
print(f"re-sim (1,1) levou {time.time()-t0:.1f}s | original RetEma34 R$ {er.rs.sum():.0f} | re-sim {base_r.sum():.0f} | iguais em {(np.abs(base_r-er.rs.to_numpy())<0.5).mean()*100:.0f}% dos trades", flush=True)

MA = [1.0, 1.25, 1.5]; MS = [1.0, 0.75, 0.5]
sims = {(1.0, 1.0): base_r}
for ma in MA[1:]: sims[(1.0, ma)] = resim(1.0, ma)
for ms in MS[1:]: sims[(ms, 1.0)] = resim(ms, 1.0)
print("sims por nota prontas", flush=True)
CELULAS = [(ma, ms) for ma in MA for ms in MS]                 # 9 celulas (alvo se alta, stop se baixa)

def wf_celulas(score, idx_all, sim_get, celulas, sel_mask, min_mes=MES_MIN_FILTRO):
    """Escolha walk-forward da celula por mes. score: previsao OOS (por evento do subconjunto, NaN no 1o mes); sim_get(cel, high)->rs R$ liquido
    de cada evento do subconjunto. Devolve (rs_liq_final por evento, celula por mes)."""
    mm = mes[idx_all]
    final = np.array(sim_get((1.0, 1.0), np.ones(len(idx_all), bool)), float).copy()
    esc = {}
    for m in range(min_mes, 11):
        past = (mm >= 2) & (mm < m) & ~np.isnan(score) & sel_mask
        if past.sum() < 20:
            continue
        thr = np.median(score[past]); high = np.where(np.isnan(score), True, score >= thr)
        best, bv = (1.0, 1.0), sim_get((1.0, 1.0), high)[past].sum()
        for c in celulas:
            v = sim_get(c, high)[past].sum()
            if v > bv + 1e-9: best, bv = c, v
        esc[m] = (best, thr)
        cur = mm == m
        final[cur] = sim_get(best, high)[cur]
    return final, esc

def sim_get_ret(cel, high):
    ma, ms = cel
    out = np.where(high, sims[(1.0, ma)], sims[(ms, 1.0)]) - CUSTO
    return out

res = {}
for k in ("logit", "nota", "tabela"):
    sc = P[k][r_idx]
    fin, esc = wf_celulas(sc, r_idx, sim_get_ret, CELULAS, np.ones(len(r_idx), bool))
    base = base_r - CUSTO
    # controle: score aleatorio, mesma regra
    ctrl = []
    for _ in range(200):
        s2 = rng.uniform(size=len(r_idx)); s2[mes[r_idx] == 1] = np.nan
        f2, _ = wf_celulas(s2, r_idx, sim_get_ret, CELULAS, np.ones(len(r_idx), bool))
        ctrl.append(f2.sum())
    ctrl = np.array(ctrl)
    res[k] = dict(final=fin, esc=esc, ctrl=ctrl, pct=(ctrl < fin.sum()).mean() * 100)
    print(f"[RetEma34 nota={k}] base re-sim R$2 {base.sum():.0f} | WF {fin.sum():.0f} | celulas por mes {[(m, v[0]) for m, v in esc.items()]} | sorteio p50 {np.median(ctrl):.0f} p95 {np.percentile(ctrl,95):.0f} percentil {res[k]['pct']:.0f}", flush=True)
    # todas as 9 celulas fixas (informativo; escolhidas olhando o futuro -> so' orientacao)
    sc_ = sc.copy(); thr = np.nanmedian(sc[mes[r_idx] >= 2]); hi = np.where(np.isnan(sc), True, sc >= thr)
    print("   celulas fixas (ma,ms) -> R$2 total (olha 2026 inteiro, so' orientacao): " + " ".join(f"{c}:{sim_get_ret(c,hi).sum():.0f}" for c in CELULAS), flush=True)

# ------------------------------------------------------------------ ideia 6: volatilidade esperada do horario (RetEma34)
m1 = DD.m1()
dias_ = sorted(set(m1.index.date)); di = {d: i for i, d in enumerate(dias_)}
slot = m1.index.hour * 2 + (m1.index.minute >= 30)
g = pd.DataFrame(dict(d=[di[x] for x in m1.index.date], s=slot, h=m1.high.to_numpy(), l=m1.low.to_numpy())).groupby(["d", "s"]).agg(h=("h", "max"), l=("l", "min"))
amp = np.full((len(dias_), 48), np.nan)
amp[g.index.get_level_values(0), g.index.get_level_values(1)] = (g.h - g.l).to_numpy()
ratio = np.ones(len(er))
for i, r in enumerate(er.itertuples(index=False)):
    d = di[r.entrada.date()]; s = r.entrada.hour * 2 + (r.entrada.minute >= 30)
    hist = amp[:d, s]; hist = hist[~np.isnan(hist)]
    if len(hist) >= 10:
        ref = np.nanmedian(amp[:d, 18:35])
        ratio[i] = np.clip(np.median(hist) / ref, 0.5, 2.0)
print(f"ideia 6: razao vol_horario/vol_ref: mediana {np.median(ratio):.2f} p10 {np.percentile(ratio,10):.2f} p90 {np.percentile(ratio,90):.2f}; correl(razao, |pontos| original) {np.corrcoef(ratio, er.pontos.abs())[0,1]:.2f}", flush=True)
G = [0.0, 0.5, 1.0]
VCEL = [(gs, ga) for gs in G for ga in G]
vsims = {}
t0 = time.time()
for gs, ga in VCEL:
    vsims[(gs, ga)] = resim(ratio ** gs, ratio ** ga) - CUSTO
print(f"sims ideia 6 prontas ({time.time()-t0:.0f}s) | R$2 por celula (gs,ga), todo o ano: " + " ".join(f"{c}:{v.sum():.0f}" for c, v in vsims.items()), flush=True)

def wf_vol(vs, rr, min_mes=MES_MIN_FILTRO):
    mm = mes[r_idx]; final = vs[(0.0, 0.0)].copy(); esc = {}
    for m in range(min_mes, 11):
        past = mm < m
        best, bv = (0.0, 0.0), vs[(0.0, 0.0)][past].sum()
        for c in VCEL:
            v = vs[c][past].sum()
            if v > bv + 1e-9: best, bv = c, v
        esc[m] = best; final[mm == m] = vs[best][mm == m]
    return final, esc
fv, escv = wf_vol(vsims, ratio)
# controle: embaralha a razao entre os trades DO MESMO MES (so' 20 sorteios: cada um refaz 9 re-simulacoes)
ctrlv = []
for j in range(30):
    rr = ratio.copy()
    for m in range(1, 11):
        ix = np.flatnonzero(mes[r_idx] == m); rr[ix] = ratio[rng.permutation(ix)]
    vs2 = {c: resim(rr ** c[0], rr ** c[1]) - CUSTO for c in VCEL}
    ctrlv.append(wf_vol(vs2, rr)[0].sum())
ctrlv = np.array(ctrlv)
print(f"[ideia 6 RetEma34] base R$2 {vsims[(0.0,0.0)].sum():.0f} | WF {fv.sum():.0f} | celulas {escv} | razao embaralhada (30 sorteios) p50 {np.median(ctrlv):.0f} p95 {np.percentile(ctrlv,95):.0f} percentil {(ctrlv < fv.sum()).mean()*100:.0f}", flush=True)

# ------------------------------------------------------------------ overlay de stop nas de tendencia (nota baixa)
tmask = np.isin(est, ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal"])
t_idx = np.flatnonzero(tmask)
et = e.iloc[t_idx].reset_index(drop=True)
atr = et.atr_m5.to_numpy()
SC = [None, 0.5, 0.75, 1.0, 1.5]
osims = {None: et.rs.to_numpy() - CUSTO}
for sc_ in SC[1:]:
    o = S.simula_saida_lote(et.t_entrada_ms.to_numpy(), et.lado.to_numpy(), et.preco_entrada.to_numpy(), arred(atr * sc_), None, hora_zera="23:59", alvo_limite=True)
    antes = (o.motivo.to_numpy() == "stop") & (o.t_saida_ms.to_numpy() < et.t_saida_ms.to_numpy())
    osims[sc_] = np.where(antes, o.pontos.to_numpy() * RS_PT, et.rs.to_numpy()) - CUSTO
    print(f"overlay stop {sc_} x ATR: dispara antes da saida original em {antes.mean()*100:.0f}% das entradas", flush=True)

def sim_get_t(cel, high):
    return np.where(high, osims[None], osims[cel])
OC = SC[1:]
sel_t = (et.estrategia != "Win_c1").to_numpy()
ores = {}
for k in ("logit", "nota", "tabela"):
    sc = P[k][t_idx]
    fin, esc = wf_celulas(sc, t_idx, lambda c, h: sim_get_t(c if c is not None else None, h) if c != (1.0, 1.0) else osims[None], [c for c in OC], sel_t)
    ctrl = []
    for _ in range(200):
        s2 = rng.uniform(size=len(t_idx)); s2[mes[t_idx] == 1] = np.nan
        f2, _ = wf_celulas(s2, t_idx, lambda c, h: sim_get_t(c, h) if c != (1.0, 1.0) else osims[None], [c for c in OC], sel_t)
        ctrl.append(f2[sel_t].sum())
    ctrl = np.array(ctrl)
    ores[k] = dict(final=fin, esc=esc, pct=(ctrl < fin[sel_t].sum()).mean() * 100, ctrl=ctrl)
    print(f"[overlay stop tendencia nota={k}] base R$2 {osims[None][sel_t].sum():.0f} | WF {fin[sel_t].sum():.0f} | celulas {[(m, v[0]) for m, v in esc.items()]} | sorteio p50 {np.median(ctrl):.0f} p95 {np.percentile(ctrl,95):.0f} percentil {ores[k]['pct']:.0f}", flush=True)

pickle.dump(dict(r_idx=r_idx, t_idx=t_idx, base_r=base_r, res=res, ratio=ratio, vsims=vsims, fv=fv, escv=escv, ctrlv=ctrlv, osims=osims, ores=ores), open(AQ / "saida_res.pkl", "wb"))
print("pronto", flush=True)
