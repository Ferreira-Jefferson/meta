"""Camada de votos das 6 estrategias do comparativo WIN 2026 -> votos.parquet.

Uma linha por barra M1 do periodo (dados.dias(): 2026-01-02 -> 2026-10-05), indice = ABERTURA da barra.
Colunas `<Estrategia>.voto`, `.forca`, `.posicao`, `.sinal` (e `.ret` para as duas de retangulo).

REGRA SEM OLHAR O FUTURO: o valor da linha t usa SO' barras M1 FECHADAS ate' t inclusive (fecham em t+1min).
Quem consome usa a partir da abertura de t+1. Barras de periodo maior (M5, M15, M30, D1) so' entram depois de
fechadas: uma M5 aberta em b vale nas linhas com t+1min >= b+5min. `python votos.py teste` recalcula os votos
com o M1 truncado em instantes sorteados e confere que o passado nao muda (test_votos_sem_futuro.py faz o mesmo).

Definicao de cada voto (linha do .mq5 em mt5/):

| estrategia | voto (-1/0/+1) | forca [0,1] | de onde veio |
|---|---|---|---|
| Win / Win_c1 | Sinal() da ultima M5 FECHADA: +1 se minima > roxa(LWMA34) e verde(SMMA34) < roxa; -1 o espelho; mantido so' se passam os filtros que nao dependem do gatilho: gap |roxa-verde|/ATR < 3, toques na roxa (20 velas) <= 14 e M15 alinhado (ultima M15 fechada: close do lado do sinal da roxa M15 e verde M15 do outro lado) | fracao dos 4 filtros "de gatilho" aprovados: idade da onda <= 9, distancia a roxa >= 15 pts, extremo >= 1,4 ATR da roxa, close >= 1,2 ATR da verde. forca = 1 <=> a M5 seria entrada do EA (fora horas bloqueadas e checagem do stop) | Win.mq5 249-258 (Sinal), 295-313 (FiltrosAprovam), 340 (FiltrosNovosAprovam M15); Win_c1.mq5 270-278, 322-324 (mesma logica; Win_c1 so' muda o break-even -> votos IDENTICOS) |
| WinCincoMedias | Alinhamento(1) da ultima M30 FECHADA (EMAs 2/4/6/17/33 em ordem E todas subindo/descendo) se o RegimeMes(1) for 0 ou do mesmo lado; senao 0 | |close - EMA33| / (2 x ATR Wilder 14 M30), cortado em 1 | WinCincoMedias.mq5 185-208 (Alinhamento), 269 (RegimeMes), 635-640 (decisao de entrada) |
| WinDeslocamentoMatinal | 0 ate' a decisao (a linha t vale a partir de t >= 1a M1 do dia + 89 min, i.e. ja' fechadas as 90 primeiras M1); depois, em cada barra, a regra da decisao reavaliada: +1 se close - abertura >= 0,3 ATR D1 e nenhuma M1 do dia fechou abaixo de abertura - 0,05 ATR; -1 o espelho | |close - abertura| / ATR D1 (14 D1 fechadas, media simples do TR), cortado em 1 | WinDeslocamentoMatinal.mq5 206-240 (Decidir), 102-115 (AtrDiario) |
| WinRetanguloEma34 | sem retangulo ativo: lado do close em relacao a EMA34 (M1). Com retangulo ativo (detector do EA, mesmo historico diario, morte por 3 closes fora de 0,25 L, zera as 17:00): lado = close vs meio (acima -> compra, abaixo -> venda), mantido so' se a EMA34 concorda (compra exige close >= EMA), senao 0 | sem retangulo: 0,5 x min(1, |close-EMA34| / (2 x ATR14 M1)) (<= 0,5); com retangulo: 0,5 + 0,5 x min(1, |close-meio| / (L/2)) (> 0,5) | WinRetanguloEma34.mq5 446 (TentaDetectar), 489 (morte), 592/724 (ZerarPregao 17:00), 668-693 (lado pelo meio + filtro EMA) |
| WdoRetangulo | com retangulo ativo (detector do EA, inputs do Testador do dono: janela 25, tol 0,28; zera 18:20): lado = close vs meio; sem retangulo: 0 | min(1, |close-meio| / (L/2)) | WdoRetangulo.mq5 367 (TentaDetectar), 410 (morte), 480/584 (ZerarPregao), 540-556 (lado pelo meio) |

`.ret` = 1 se o retangulo do EA esta' ativo depois de processar a barra t.
`.posicao` = lado (+1/-1) se a estrategia esta' posicionada no FECHAMENTO da barra t (entrada < t+1min <= saida),
  tirado de resultados/<nome>.csv (posicao real do replay, nao depende do voto).
`.sinal` = lado (+1/-1) na barra que CONTEM o horario de entrada de uma operacao real (|sinal| = 1 marca a entrada).
Simplificacoes declaradas: (a) votos M1 usam dados.m1() (o port de retangulo monta as M1 dos ticks; iguais quase
sempre); (b) nos retangulos, a ultima barra do dia anterior que o EA processa no 1o tick do pregao nao e' processada
(ela so' afeta a 1a barra do dia, antes de o historico zerar); (c) as horas bloqueadas e a checagem de distancia
do stop do Win nao entram no voto (sao do envio da ordem, nao da leitura do mercado).

Uso: python votos.py          -> votos.parquet
     python votos.py teste    -> teste sem-futuro
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]
sys.path.insert(0, str(BASE))
import dados as D  # noqa: E402
import port_win as PW  # noqa: E402
import port_cinco_medias as PC  # noqa: E402
import port_deslocamento as PD  # noqa: E402
import port_retangulo_ema34 as PR  # noqa: E402
import port_wdo_retangulo as PWR  # noqa: E402

ESTRATEGIAS = ["Win", "Win_c1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34", "WdoRetangulo"]
ARQ = AQUI / "votos.parquet"
MIN = np.timedelta64(60, "s")


def _periodo(m1: pd.DataFrame) -> pd.DatetimeIndex:
    d = m1.index.date
    return m1.index[(d >= D.INICIO) & (d <= D.FIM)]


def _para_m1(idx_m1: pd.DatetimeIndex, fecha: np.ndarray, *cols):
    """Leva valores de barras maiores (que fecham em `fecha`) para as linhas M1: linha t pega a ultima barra com
    fecha <= t+1min. Sem barra fechada -> 0."""
    fim = (idx_m1 + pd.Timedelta(minutes=1)).values
    k = np.searchsorted(fecha, fim, side="right") - 1
    ok = k >= 0
    out = []
    for c in cols:
        v = np.zeros(len(idx_m1), dtype=float)
        v[ok] = c[k[ok]]
        out.append(v)
    return out


# --------------------------------------------------------------------------- Win / Win_c1 (M5)
def votos_win(m1: pd.DataFrame, idx: pd.DatetimeIndex):
    p = PW.PARAMS
    m5 = PW._ohlc(m1, "5min")
    c, h, l = (m5[k].to_numpy(float) for k in ("close", "high", "low"))
    n = p["periodo"]
    w, s = PW.lwma(c, n), PW.smma(c, n)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = np.nan
    atr = pd.Series(tr).rolling(p["periodo_atr"]).mean().to_numpy()
    raw = np.where((l > w) & (s < w), 1, np.where((h < w) & (s > w), -1, 0))
    raw[np.isnan(w) | np.isnan(s) | np.isnan(atr)] = 0
    with np.errstate(invalid="ignore", divide="ignore"):
        lado = np.sign(c - w); lado[np.isnan(w)] = 0
        run = np.ones(len(c), int)
        for i in range(1, len(c)):
            run[i] = run[i - 1] + 1 if lado[i] == lado[i - 1] else 1
        f_idade = (lado == raw) & (run <= p["idade_max"])
        f_dist = np.where(raw > 0, l - w, w - h) >= p["dist_min"]
        f_ext = np.where(raw > 0, h - w, w - l) / atr >= p["ext_roxa_min_atr"]
        f_verde = raw * (c - s) / atr >= p["dist_verde_min_atr"]
        f_gap = np.abs(w - s) / atr < p["gap_max_atr"]
        j = p["janela_toques"]
        tq_c = pd.Series((l <= w).astype(float)).rolling(j).sum().to_numpy()
        tq_v = pd.Series((h >= w).astype(float)).rolling(j).sum().to_numpy()
        f_toq = np.where(raw > 0, tq_c, tq_v) <= p["toques_max"]
    m15 = PW._ohlc(m1, "15min")
    c15 = m15.close.to_numpy(float)
    w15, s15 = PW.lwma(c15, n), PW.smma(c15, n)
    fim15 = (m15.index + pd.Timedelta(minutes=15)).values
    fim5 = (m5.index + pd.Timedelta(minutes=5)).values
    k = np.searchsorted(fim15, fim5, side="right") - 1
    kk = np.clip(k, 0, None)
    cc, ww, ss = c15[kk], w15[kk], s15[kk]
    f_m15 = (k >= 0) & np.where(raw > 0, (cc > ww) & (ss < ww), (cc < ww) & (ss > ww))
    voto = np.where(f_gap & f_toq & f_m15, raw, 0)
    forca = np.where(voto != 0, (f_idade.astype(int) + f_dist + f_ext + f_verde) / 4.0, 0.0)
    return _para_m1(idx, fim5, voto, forca)


# --------------------------------------------------------------------------- WinCincoMedias (M30)
def votos_cinco(m1: pd.DataFrame, idx: pd.DatetimeIndex):
    P = PC.prepara(M=m1)
    est, reg, c = P["est"], P["reg"], P["c"]
    voto = np.where((est != 0) & ((reg == 0) | (reg == est)), est, 0)
    e33 = pd.Series(c).ewm(span=PC.EMAS[-1], adjust=False).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        f = np.clip(np.abs(c - e33) / (2 * P["atr"]), 0, 1)
    forca = np.where(voto != 0, np.nan_to_num(f), 0.0)
    fim = (P["ts"] + pd.Timedelta(minutes=30)).values
    return _para_m1(idx, fim, voto, forca)


# --------------------------------------------------------------------------- WinDeslocamentoMatinal (M1 + D1)
def votos_desloc(m1: pd.DataFrame, idx: pd.DatetimeIndex):
    p = PD.P
    d1 = PD.d1_de(m1)
    voto = np.zeros(len(idx)); forca = np.zeros(len(idx))
    pos = pd.Series(np.arange(len(idx)), index=idx)
    for dia, b in m1.loc[idx.min():idx.max()].groupby(m1.loc[idx.min():idx.max()].index.date):
        atr = PD.atr_d1(d1, dia, p["per_atr"])
        if atr <= 0:
            continue
        ab = float(b.open.iloc[0]); cl = b.close.to_numpy(float)
        t0 = b.index[0]
        decid = (b.index >= t0 + pd.Timedelta(minutes=p["minutos_decisao"] - 1))
        desloc = cl - ab
        mn, mx = np.minimum.accumulate(cl), np.maximum.accumulate(cl)
        banda = p["banda"] * atr
        v = np.where((desloc >= p["desloc"] * atr) & (mn >= ab - banda), 1,
                     np.where((-desloc >= p["desloc"] * atr) & (mx <= ab + banda), -1, 0))
        v = np.where(decid, v, 0)
        ii = pos.reindex(b.index).to_numpy()
        ok = ~np.isnan(ii)
        ii = ii[ok].astype(int)
        voto[ii] = v[ok]
        forca[ii] = np.where(v[ok] != 0, np.clip(np.abs(desloc[ok]) / atr, 0, 1), 0.0)
    return voto, forca


# --------------------------------------------------------------------------- retangulos (M1, estado do detector)
def votos_ret_ema34(m1: pd.DataFrame, idx: pd.DatetimeIndex):
    ema = m1.close.ewm(span=PR.PER_EMA, adjust=False).mean()
    pc = m1.close.shift(1)
    tr = np.fmax(m1.high - m1.low, np.fmax((m1.high - pc).abs(), (m1.low - pc).abs()))
    atr = tr.rolling(14).mean()
    b = m1.loc[idx]
    E, A = ema.loc[idx].to_numpy(), atr.loc[idx].to_numpy()
    H, L, C = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    tms = idx.values.astype("datetime64[ms]").astype(np.int64)
    ea = PR.Ea()
    ea.pos = {}                                   # sentinela: processar_barra para antes de armar ordem
    voto = np.zeros(len(idx)); forca = np.zeros(len(idx)); ret = np.zeros(len(idx))
    for i in range(len(idx)):
        if ((tms[i] // 60000 + 1) % 1440) >= PR.ZERA_MIN:   # 1o tick da barra seguinte >= 17:00 -> ZerarPregao
            ea.tem_ret = False
        else:
            ea.processar_barra(None, None, (int(tms[i]), H[i], L[i], C[i], float(E[i])))
        ladoE = 1 if C[i] >= E[i] else -1
        if ea.tem_ret:
            ret[i] = 1
            lado = int(np.sign(C[i] - ea.meio))
            ok = (lado > 0 and C[i] >= E[i]) or (lado < 0 and C[i] <= E[i])
            voto[i] = lado if ok else 0
            forca[i] = 0.5 + 0.5 * min(1.0, abs(C[i] - ea.meio) / (ea.larg / 2)) if voto[i] else 0.0
        else:
            voto[i] = ladoE
            forca[i] = 0.5 * min(1.0, abs(C[i] - E[i]) / (2 * A[i])) if A[i] > 0 else 0.0
    return voto, forca, ret


def votos_wdo_ret(m1: pd.DataFrame, idx: pd.DatetimeIndex):
    cfg = PWR.Cfg()
    zer = cfg.hora_zerar * 60 + cfg.min_zerar
    b = m1.loc[idx]
    H, L, C = (b[k].to_numpy(float) for k in ("high", "low", "close"))
    tms = idx.values.astype("datetime64[ms]").astype(np.int64)
    ea = PWR.EA(cfg, "votos", None)
    ea.pos = {}
    voto = np.zeros(len(idx)); forca = np.zeros(len(idx)); ret = np.zeros(len(idx))
    for i in range(len(idx)):
        if ((tms[i] // 60000 + 1) % 1440) >= zer:
            ea.tem = False
        else:
            ea.prev_bar = (int(tms[i]), H[i], L[i], C[i])
            ea.processa()
        if ea.tem:
            ret[i] = 1
            voto[i] = np.sign(C[i] - ea.meio)
            forca[i] = min(1.0, abs(C[i] - ea.meio) / (ea.larg / 2)) if voto[i] else 0.0
    return voto, forca, ret


# --------------------------------------------------------------------------- posicao / sinal reais
def posicoes(idx: pd.DatetimeIndex, nome: str):
    t = pd.read_csv(BASE / "resultados" / f"{nome}.csv")
    te = pd.to_datetime(t.entrada, format="mixed").values
    tx = pd.to_datetime(t.saida, format="mixed").values
    fim = (idx + pd.Timedelta(minutes=1)).values
    posicao = np.zeros(len(idx)); sinal = np.zeros(len(idx))
    a = np.searchsorted(fim, te, side="right")        # 1a linha com fim > entrada
    z = np.searchsorted(fim, tx, side="right")        # linhas com fim <= saida
    ks = np.searchsorted(idx.values, te, side="right") - 1   # barra que contem a entrada
    for i in range(len(t)):
        posicao[a[i]:z[i]] = t.lado.iloc[i]
        if ks[i] >= 0:
            sinal[ks[i]] = t.lado.iloc[i]
    return posicao, sinal


def calcula_votos(m1: pd.DataFrame, log=print) -> pd.DataFrame:
    """So' voto/forca/ret (dependem do mercado). Indice = M1 do periodo presentes em m1."""
    idx = _periodo(m1)
    out = {}
    t0 = time.time()
    v, f = votos_win(m1, idx)
    for nm in ("Win", "Win_c1"):
        out[f"{nm}.voto"], out[f"{nm}.forca"] = v, f
    log(f"  Win ok ({time.time() - t0:.0f}s)", flush=True)
    out["WinCincoMedias.voto"], out["WinCincoMedias.forca"] = votos_cinco(m1, idx)
    log(f"  CincoMedias ok ({time.time() - t0:.0f}s)", flush=True)
    out["WinDeslocamentoMatinal.voto"], out["WinDeslocamentoMatinal.forca"] = votos_desloc(m1, idx)
    log(f"  Deslocamento ok ({time.time() - t0:.0f}s)", flush=True)
    out["WinRetanguloEma34.voto"], out["WinRetanguloEma34.forca"], out["WinRetanguloEma34.ret"] = votos_ret_ema34(m1, idx)
    log(f"  RetanguloEma34 ok ({time.time() - t0:.0f}s)", flush=True)
    out["WdoRetangulo.voto"], out["WdoRetangulo.forca"], out["WdoRetangulo.ret"] = votos_wdo_ret(m1, idx)
    log(f"  WdoRetangulo ok ({time.time() - t0:.0f}s)", flush=True)
    df = pd.DataFrame(out, index=idx)
    for c in df.columns:
        if c.endswith(".voto") or c.endswith(".ret"):
            df[c] = df[c].astype(np.int8)
    return df


def gerar():
    m1 = D.m1()
    print("calculando votos...", flush=True)
    df = calcula_votos(m1)
    for nm in ESTRATEGIAS:
        df[f"{nm}.posicao"], df[f"{nm}.sinal"] = posicoes(df.index, nm)
        df[f"{nm}.posicao"] = df[f"{nm}.posicao"].astype(np.int8)
        df[f"{nm}.sinal"] = df[f"{nm}.sinal"].astype(np.int8)
    cols = [f"{nm}.{k}" for nm in ESTRATEGIAS for k in ("voto", "forca", "posicao", "sinal", "ret") if f"{nm}.{k}" in df]
    df = df[cols]
    df.index.name = "t"
    df.to_parquet(ARQ)
    print(f"salvo {ARQ} {df.shape}", flush=True)
    for nm in ESTRATEGIAS:
        v = df[f"{nm}.voto"]
        print(f"  {nm:24s} +1 {100 * (v > 0).mean():5.1f}%  -1 {100 * (v < 0).mean():5.1f}%  0 {100 * (v == 0).mean():5.1f}%"
              f"  entradas {int((df[f'{nm}.sinal'] != 0).sum())}", flush=True)
    return df


def teste_sem_futuro(cortes=None, completo: pd.DataFrame | None = None, seed=7) -> list:
    """Recalcula com o M1 truncado em `cortes` e confere que as linhas <= corte nao mudam. Devolve falhas."""
    m1 = D.m1()
    if completo is None:
        completo = pd.read_parquet(ARQ) if ARQ.exists() else calcula_votos(m1)
    idx = _periodo(m1)
    if cortes is None:
        rng = np.random.default_rng(seed)
        cortes = sorted(idx[rng.integers(len(idx) // 10, len(idx), 3)])
    falhas = []
    cols = [c for c in completo.columns if c.split(".")[1] in ("voto", "forca", "ret")]
    for T in cortes:
        trunc = calcula_votos(m1[m1.index <= T], log=lambda *a, **k: None)
        a = completo.loc[completo.index <= T, cols]
        b = trunc.loc[a.index, cols]
        dif = ~np.isclose(a.to_numpy(float), b.to_numpy(float), equal_nan=True)
        n = int(dif.sum())
        print(f"corte {T}: {len(a)} linhas x {len(cols)} colunas comparadas, diferencas {n}", flush=True)
        if n:
            r, c = np.argwhere(dif)[0]
            falhas.append((str(T), str(a.index[r]), cols[c], a.iat[r, c], b.iat[r, c]))
            print("   1a diferenca:", falhas[-1], flush=True)
    return falhas


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "teste":
        f = teste_sem_futuro()
        print("TESTE SEM-FUTURO:", "OK" if not f else f"FALHOU {f}", flush=True)
    else:
        gerar()
