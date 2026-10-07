"""[Y1] COPIA PARAMETRIZADA de port_win.py: tempo gráfico base `tf_min` (nativo 5) e superior `sup_min`.
Mudancas vs original: so' o tempo grafico (resample, +5min -> +tf, 300000 -> tf em ms, M15 -> sup). Resto identico.
Tabela base -> superior (proximo tempo MT5 >= 3x a base; lista MT5: 1,2,3,4,5,6,10,12,15,20,30,60,120):
  M1->M3, M2->M6, M3->M10, M5->M15, M10->M30, M15->H1, M30->H2.

Port do Win.mq5 (v2.04) e Win_c1.mq5 (v2.05) para o replay tick a tick do comparativo WIN 2026.

Segue o .mq5 (que vence qualquer replay antigo) e as regras de execucao de `dados.py` (bid = ask = last):
  - entrada a mercado no `last` do 1o tick da M5 seguinte ao sinal;
  - SL nativo dispara no tick em que o last o toca/atravessa (ANTES do OnTick daquele tick) e sai no last do tick;
  - saidas a mercado do EA (canal, esticada, stop alcancado, break-even, zerar) saem no last do tick em que o EA age;
  - o EA so' reavalia entrada no 1o tick de uma M5 nova; se o SL fechou a posicao antes desse tick (ou NESSE tick),
    a entrada da barra e' avaliada normalmente.
Indicadores contínuos sobre o WIN$N (LWMA34 / SMMA34 estilo MT5 com semente SMA / ATR = media simples do TR).
Tudo por eventos: nada de loop por tick (searchsorted / argmax em fatias).

Uso: python port_win.py [--inicio 2026-01-02] [--fim 2026-10-05] [--so Win|Win_c1] [--sem-salvar]
"""
import argparse, sys, time
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd

import dados as D

TICK = D.TICK

# Inputs padrao dos .mq5 (Win_c1 difere so' em BreakEven*).
PARAMS = dict(periodo=34, periodo_atr=14, k_atr=0.6, idade_max=9, dist_min=15.0, gap_max_atr=3.0, ext_roxa_min_atr=1.4,
              dist_verde_min_atr=1.2, esticada_arma_atr=2.5, esticada_recuo_atr=0.75, alinhar_m15=1, janela_toques=20,
              toques_max=14, horas_sem_entrada="11,15,16,17", hora_fim=18, minuto_fim=0, min_sem_entrada=30,
              min_zerar=10, lote=1.0, be_minutos=0, be_colchao_pts=7.0, tf_min=5, sup_min=15)
SUP = {1: 3, 2: 6, 3: 10, 5: 15, 10: 30, 15: 60, 30: 120}
PARAMS_C1 = {**PARAMS, "be_minutos": 15, "be_colchao_pts": 7.0}


# --------------------------------------------------------------------------- indicadores (estilo MT5)
def lwma(c: np.ndarray, n: int) -> np.ndarray:
    w = np.arange(1, n + 1, dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1:] = np.correlate(c, w, "valid") / w.sum()
    return out


def smma(c: np.ndarray, n: int) -> np.ndarray:
    """iMA MODE_SMMA: 1o valor (indice n-1) = SMA das n primeiras; depois (ant*(n-1)+preco)/n."""
    out = np.full(len(c), np.nan)
    if len(c) < n:
        return out
    v = c[:n].mean()
    out[n - 1] = v
    for i in range(n, len(c)):
        v = (v * (n - 1) + c[i]) / n
        out[i] = v
    return out


def _ohlc(m1: pd.DataFrame, freq: str) -> pd.DataFrame:
    return m1.resample(freq, closed="left", label="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def preparar(p: dict) -> pd.DataFrame:
    """Barras M5 contínuas com wma/smma/atr e `sinal` (+1/-1/0) ja' filtrado, valido para a ordem enviada na
    abertura da M5 seguinte (= idx + 5min)."""
    m1 = D.m1()
    tf = int(p["tf_min"]); m5 = _ohlc(m1, f"{tf}min")
    c, h, l = (m5[k].to_numpy(float) for k in ("close", "high", "low"))
    n = p["periodo"]
    w, s = lwma(c, n), smma(c, n)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = np.nan                                   # sem fechamento anterior
    atr = pd.Series(tr).rolling(p["periodo_atr"]).mean().to_numpy()   # media simples dos ultimos N TR (a vela atual inclusa)
    m5["wma"], m5["smma"], m5["atr"] = w, s, atr

    comp = (l > w) & (s < w)
    vend = (h < w) & (s > w)
    sinal = np.where(comp, 1, np.where(vend, -1, 0))
    sinal[np.isnan(w) | np.isnan(s) | np.isnan(atr)] = 0
    ok = np.ones(len(m5), bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        if p["idade_max"] > 0:          # IdadeDaOnda: velas seguidas (a do sinal incluida) do mesmo lado da roxa
            lado = np.sign(c - w)
            lado[np.isnan(w)] = 0
            run = np.zeros(len(c), int)
            for i in range(len(c)):
                run[i] = (run[i - 1] + 1 if i and lado[i] == lado[i - 1] else 1)
            ok &= (lado == sinal) & (run <= p["idade_max"])
        dist = np.where(sinal > 0, l - w, w - h)
        ok &= dist >= p["dist_min"]
        if p["gap_max_atr"] > 0:
            ok &= np.abs(w - s) / atr < p["gap_max_atr"]
        if p["ext_roxa_min_atr"] > 0:
            ok &= np.where(sinal > 0, h - w, w - l) / atr >= p["ext_roxa_min_atr"]
        if p["dist_verde_min_atr"] > 0:
            ok &= sinal * (c - s) / atr >= p["dist_verde_min_atr"]
        if p["janela_toques"] > 0:
            j = int(p["janela_toques"])
            tq_c = pd.Series((l <= w).astype(float)).rolling(j).sum().to_numpy()
            tq_v = pd.Series((h >= w).astype(float)).rolling(j).sum().to_numpy()
            ok &= np.where(sinal > 0, tq_c, tq_v) <= p["toques_max"]
    if p["alinhar_m15"]:                # ultima M15 JA FECHADA na abertura da M5 de entrada
        sup = int(p["sup_min"]); m15 = _ohlc(m1, f"{sup}min")
        c15 = m15.close.to_numpy(float)
        w15, s15 = lwma(c15, n), smma(c15, n)
        fim15 = (m15.index + pd.Timedelta(minutes=sup)).to_numpy("datetime64[ns]")
        t_ent = (m5.index + pd.Timedelta(minutes=tf)).to_numpy("datetime64[ns]")
        k = np.searchsorted(fim15, t_ent, side="right") - 1          # fim <= abertura da M5 de entrada
        kk = np.clip(k, 0, None)
        cc, ww, ss = c15[kk], w15[kk], s15[kk]
        m15ok = (k >= 0) & np.where(sinal > 0, (cc > ww) & (ss < ww), (cc < ww) & (ss > ww))
        ok &= m15ok
    sinal = np.where(ok, sinal, 0)
    horas = [int(x) for x in str(p["horas_sem_entrada"]).split(",") if x.strip()]
    if horas:                           # hora da vela em que a ordem entra
        sinal[np.isin((m5.index + pd.Timedelta(minutes=tf)).hour, horas)] = 0
    m5["sinal"] = sinal.astype(int)
    return m5


# --------------------------------------------------------------------------- um pregao
def _arred(v):
    return round(v / TICK) * TICK


def replay_dia(dia: date, m5: pd.DataFrame, tk, p: dict, nome: str, out: list):
    tms, last, _vol, _real = tk
    n = len(tms)
    if n == 0:
        return
    ini = int(pd.Timestamp(dia).value // 10**6)
    fim_min = p["hora_fim"] * 60 + p["minuto_fim"]
    t_zera = ini + (fim_min - p["min_zerar"]) * 60000
    t_sem = ini + (fim_min - p["min_sem_entrada"]) * 60000
    mn = tms // 60000
    fm = np.empty(n, bool); fm[0] = True; fm[1:] = mn[1:] != mn[:-1]      # 1o tick de cada minuto M1
    be_on = p["be_minutos"] > 0
    col = p["be_colchao_pts"]
    k_atr = p["k_atr"]
    TFMS = int(p["tf_min"]) * 60000

    dm = m5[m5.index.date == dia]
    if dm.empty:
        return
    tb_all = (dm.index.values.astype("datetime64[ms]").astype(np.int64) + TFMS)
    W, S, C, A, G = (dm[c].to_numpy(float) for c in ("wma", "smma", "close", "atr", "sinal"))
    iz = int(np.searchsorted(tms, t_zera))      # 1o tick em/apos o horario de zerar
    pos = None

    def fechar(i, px, mot):
        nonlocal pos
        out.append(D.trade(nome, pos["te"], tms[i], pos["d"], p["lote"], pos["e"], px, mot))
        pos = None

    def avanca(a, i0):
        """Ticks [a, i0): SL pode disparar em [a, i0] (inclui o tick i0: o SL age antes do OnTick); BE so' nos
        primeiros ticks de minuto em [a, i0) (o do tick i0 e' checado depois da logica do evento). Fecha pos se houver."""
        if i0 < a:
            return
        j = None
        seg = last[a:i0 + 1]
        c = (seg <= pos["sl"]) if pos["d"] == 1 else (seg >= pos["sl"])
        if c.any():
            j = a + int(np.argmax(c))
        jb = None
        if be_on and i0 > a:
            cand = np.flatnonzero(fm[a:i0]) + a
            cand = cand[mn[cand] * 60000 >= pos["dl"]]
            if len(cand):
                hit = pos["d"] * (last[cand] - pos["e"]) <= col
                if hit.any():
                    jb = int(cand[int(np.argmax(hit))])
        if j is not None and (jb is None or j <= jb):
            fechar(j, last[j], "stop")
        elif jb is not None:
            fechar(jb, last[jb], "break_even")

    cur = 0                                       # proximo tick ainda nao varrido pelo SL
    for kk in range(len(tb_all)):
        tb = int(tb_all[kk])
        if tb >= t_zera:
            break
        i0 = int(np.searchsorted(tms, tb))
        if i0 >= n or tms[i0] >= tb + TFMS:     # barra nova sem tick: o EA nao ve o evento
            continue
        if tms[i0] >= t_zera:
            break
        if pos is not None:
            avanca(cur, i0)
        if pos is not None:
            d = pos["d"]
            # AtualizaPosicao (1o tick da M5 nova; usa a vela fechada kk)
            if not (np.isnan(W[kk]) or np.isnan(A[kk]) or A[kk] <= 0):
                px_now = last[i0]
                if min(W[kk], S[kk]) < C[kk] < max(W[kk], S[kk]):
                    fechar(i0, px_now, "canal")
                else:
                    ex = None
                    if p["esticada_arma_atr"] > 0:
                        est = d * (C[kk] - W[kk]) / A[kk]
                        if est >= p["esticada_arma_atr"]:
                            pos["arm"] = True
                        pos["pico"] = max(pos["pico"], est)
                        if pos["arm"] and est <= pos["pico"] - p["esticada_recuo_atr"]:
                            ex = "esticada"
                    if ex is None:
                        novo = _arred(W[kk] + d * k_atr * A[kk])
                        if (d == 1 and novo > px_now - TICK) or (d == -1 and novo < px_now + TICK):
                            ex = "stop_alcancado"
                    if ex:
                        fechar(i0, px_now, ex)
                    else:
                        pos["sl"] = novo
            if pos is not None and be_on and fm[i0]:       # VerificaBreakEven no mesmo tick, depois de AtualizaPosicao
                if mn[i0] * 60000 >= pos["dl"] and pos["d"] * (last[i0] - pos["e"]) <= col:
                    fechar(i0, last[i0], "break_even")
            if pos is not None:
                cur = i0 + 1
            continue
        # sem posicao: avalia entrada no 1o tick da M5 nova
        s = int(G[kk])
        if s == 0 or tms[i0] >= t_sem:
            continue
        pr = last[i0]
        sl = _arred(W[kk] + s * k_atr * A[kk])
        if (s == 1 and sl > pr - TICK) or (s == -1 and sl < pr + TICK):
            continue
        pos = dict(d=s, e=float(pr), sl=float(sl), te=int(tms[i0]), arm=False, pico=-1e9,
                   dl=int(tms[i0]) // TFMS * TFMS + p["be_minutos"] * 60000)
        cur = i0 + 1
    if pos is not None:                           # zerar: 1o tick >= 17:50 (ou o ultimo do dia)
        iz2 = min(iz, n - 1)
        avanca(cur, iz2)
        if pos is not None:
            fechar(iz2, last[iz2], "zera")


def rodar(nome: str, p: dict, inicio: date, fim: date, salvar=True, verbose=True):
    m5 = preparar(p)
    out = []
    dias = [d for d in D.dias() if inicio <= d <= fim]
    t0 = time.time()
    for i, dia in enumerate(dias):
        tk = D.ticks(dia)
        replay_dia(dia, m5, tk, p, nome, out)
        if verbose and (i % 10 == 0 or i == len(dias) - 1):
            print(f"[{nome}] {i + 1}/{len(dias)} {dia} real={tk[3]} trades={len(out)} ({time.time() - t0:.0f}s)", flush=True)
    if salvar:
        print("salvo:", D.salvar(nome, out), flush=True)
    return out


def resumo(nome, out):
    df = pd.DataFrame(out)
    if df.empty:
        print(nome, "sem trades"); return
    df["mes"] = df.saida.str[:7]
    g = df.groupby("mes").rs.agg(trades="count", liquido="sum").round(2)
    print(f"== {nome}: {len(df)} trades, liquido R$ {df.rs.sum():.2f}, win {100 * (df.rs > 0).mean():.1f}%")
    print(g.to_string(), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", default="2026-01-02"); ap.add_argument("--fim", default="2026-10-05")
    ap.add_argument("--so", default=None); ap.add_argument("--sem-salvar", action="store_true")
    a = ap.parse_args()
    ini, fim = date.fromisoformat(a.inicio), date.fromisoformat(a.fim)
    for nome, p in (("Win", PARAMS), ("Win_c1", PARAMS_C1)):
        if a.so and a.so != nome:
            continue
        resumo(nome, rodar(nome, p, ini, fim, salvar=not a.sem_salvar))
