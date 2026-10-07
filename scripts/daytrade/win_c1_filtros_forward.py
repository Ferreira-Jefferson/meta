"""Acompanhamento FORWARD dos filtros de contexto em tempo maior do C1 (Win.mq5 v2.04) -- outubro/2026 em diante.

O que faz: puxa M1 do MT5 aberto (WIN@D por padrao, a serie continua usada na pesquisa), roda o C1 (porte fiel do EA em M5,
mesmos parametros e custos do simulador da pesquisa) a partir de `--desde` (padrao 2026-10-02) e marca, por operacao, se cada
um dos 7 filtros CONGELADOS retiraria a entrada. Grava um CSV acumulavel (uma linha por operacao; reexecutar substitui as
linhas do periodo, nao duplica) e um resumo base x filtrado.

Os 7 filtros e os limiares (quantis do IS 2021-10..2024-06 do WIN@D) estao congelados abaixo e NAO se reotimizam; qualquer
mudanca invalida o acompanhamento (o hash dos limiares e conferido na partida e gravado no CSV de resumo).
Sem resultado ainda por construcao: o periodo comeca depois da pesquisa (ultimo dado usado: 2026-10-01).

Uso:
    .\\.venv\\Scripts\\python.exe scripts/daytrade/win_c1_filtros_forward.py                 # 2026-10-02 ate hoje
    .\\.venv\\Scripts\\python.exe scripts/daytrade/win_c1_filtros_forward.py --desde 2026-06-02 --csv C:\\tmp\\x.csv
    .\\.venv\\Scripts\\python.exe scripts/daytrade/win_c1_filtros_forward.py --simbolo WIN$D

Dados: so a ultima barra M5 COMPLETA entra (a barra em formacao e descartada), entao a operacao so aparece depois que a
barra de entrada abriu. Operacao ainda aberta no fim dos dados aparece com `fechada=0` e fica fora do resumo.
Nao envia ordem, nao altera o EA, nao toca o banco do robo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CSV_PADRAO = ROOT / "data" / "win_c1_filtros_forward_operacoes.csv"
RESUMO_PADRAO = ROOT / "data" / "win_c1_filtros_forward_resumo.csv"
DESDE_PADRAO = "2026-10-02"
AQUECIMENTO_DIAS = 45  # historico antes de --desde: WMA34/ATR14 e caixas de 20 barras H1 (~54 barras H1 + folga)

# ---------------------------------------------------------------- parametros do C1 (Win.mq5 v2.04, defaults)
P = dict(periodo=34, periodo_atr=14, k=0.6, idade_max=9, gap_max=3.0, ext_min=1.4, dverde_min=1.2,
         arma=2.5, recuo=0.75, janela=20, toques_max=14, horas_sem=(11, 15, 16, 17))
TICK = 5.0
RS_PONTO = 0.20        # R$ por ponto (1 contrato WIN)
CUSTO_PTS = 5.0        # pontos por operacao (ida e volta)
SLIP_PTS = 2.0         # pontos adicionais nas saidas por stop
DIST_MIN = 15.0        # pontos
ZERAR = 17 * 60 + 50
SEM_ENTRADA = 17 * 60 + 30
NB, NX = 12, 20

# ---------------------------------------------------------------- filtros CONGELADOS (S_filtros_congelados.json, 2026-10-05)
FILTROS = {  # id: (coluna, operador, limiar)   keep = condicao verdadeira
    "H1.D": ("H1_posbox", "<=", 0.8711115745229416),
    "nofit60": ("fit60", "==", 0.0),
    "M1.b30lo": ("m1box30_atr", ">=", 2.538686120117338),
    "H1.B": ("H1_depth", ">=", 0.5615640449438203),
    "M30.D": ("M30_posbox", "<=", 0.8858495293973843),
    "M30.E": ("M30_room", ">=", 0.414841557815594),
    "H1.E": ("H1_room", ">=", 0.3866971964357788),
}
HASH_LIMIARES = "7312c389acb7f646eaf09336379e6b1f2cd0130ea95a5b37a96a01fbacb696aa"


def hash_limiares() -> str:
    th = {k: (v[2] if k != "nofit60" else None) for k, v in FILTROS.items()}
    return hashlib.sha256(json.dumps(th, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------- indicadores (identicos a M_core / W_core da pesquisa)
def lwma(s: pd.Series, w: int) -> pd.Series:
    wt = np.arange(1, w + 1, dtype=float)
    return s.rolling(w, min_periods=w).apply(lambda v: float(np.dot(v, wt) / wt.sum()), raw=True)


def smma(s: pd.Series, w: int) -> pd.Series:
    return s.ewm(alpha=1.0 / w, adjust=False, min_periods=w).mean()


def reamostra(m1: pd.DataFrame, minutos: int) -> pd.DataFrame:
    return m1[["open", "high", "low", "close"]].resample(f"{minutos}min", origin="start_day", offset="9h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def prepara(m5: pd.DataFrame) -> pd.DataFrame:
    b = m5[["open", "high", "low", "close"]].copy()
    b["wma"], b["smma"] = lwma(b.close, P["periodo"]), smma(b.close, P["periodo"])
    tr = pd.concat([b.high - b.low, (b.high - b.close.shift()).abs(), (b.low - b.close.shift()).abs()], axis=1).max(axis=1)
    b["atr"] = tr.rolling(P["periodo_atr"]).mean()
    comp = (b.low > b.wma) & (b.smma < b.wma)
    vend = (b.high < b.wma) & (b.smma > b.wma)
    s = pd.Series(np.where(comp, 1, np.where(vend, -1, 0)), index=b.index)
    s[b.wma.isna() | b.smma.isna() | b.atr.isna()] = 0
    b["sig0"] = s
    lado = np.sign(b.close - b.wma).fillna(0)
    b["idade"] = lado.groupby((lado != lado.shift()).cumsum()).cumcount() + 1
    b["dist"] = np.where(s == 1, b.low - b.wma, b.wma - b.high)
    b["gap"] = (b.wma - b.smma).abs() / b.atr
    b["ext"] = np.where(s == 1, b.high - b.wma, b.wma - b.low) / b.atr
    b["cver"] = s * (b.close - b.smma) / b.atr
    j = P["janela"]
    tc = (b.low <= b.wma).astype(float).rolling(j).sum()
    tv = (b.high >= b.wma).astype(float).rolling(j).sum()
    b["toq"] = np.where(s == 1, tc, tv)
    m15 = b[["open", "high", "low", "close"]].resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    m15["w"], m15["s"] = lwma(m15.close, P["periodo"]), smma(m15.close, P["periodo"])
    m15.index = m15.index + pd.Timedelta(minutes=15)
    k = m15.reindex(b.index + pd.Timedelta(minutes=5), method="ffill")
    d = s.to_numpy()
    b["m15ok"] = (np.sign(k.close.to_numpy() - k.w.to_numpy()) == d) & np.where(d == 1, k.s.to_numpy() < k.w.to_numpy(), k.s.to_numpy() > k.w.to_numpy())
    return b


def sinal_filtrado(b: pd.DataFrame) -> pd.Series:
    ok = (b.idade <= P["idade_max"]) & (b.dist >= DIST_MIN) & (b.gap < P["gap_max"]) & (b.ext >= P["ext_min"]) \
        & (b.cver >= P["dverde_min"]) & (b.toq <= P["toques_max"]) & b.m15ok
    sg = b.sig0.where(ok.fillna(False), 0).astype(int)
    sg[np.isin((b.index + pd.Timedelta(minutes=5)).hour, list(P["horas_sem"]))] = 0
    return sg


def simula(b: pd.DataFrame, sg: pd.Series, inicio: pd.Timestamp) -> tuple[pd.DataFrame, dict | None]:
    """Mesma maquina de estados de M_core.simula (modo win, zera 17:50, 1 contrato). Devolve (operacoes fechadas, posicao aberta)."""
    o, h, l, c = (b[x].to_numpy() for x in ("open", "high", "low", "close"))
    rx, vd, at = b.wma.to_numpy(), b.smma.to_numpy(), b.atr.to_numpy()
    sgn = sg.to_numpy(); idx = b.index; n = len(b)
    dia = np.array(idx.date); t = (idx.hour * 60 + idx.minute).to_numpy()
    K, ARMA, RECUO = P["k"], P["arma"], P["recuo"]
    ini = int(np.searchsorted(idx.values, np.datetime64(pd.Timestamp(inicio))))
    trades: list[dict] = []; pos = None

    def rnd(x):
        return round(round(x / TICK) * TICK, 6)

    def fechar(i, px, motivo, stop=False):
        nonlocal pos
        d = pos["d"]
        pnl = (d * (px - pos["e"]) - CUSTO_PTS - (SLIP_PTS if stop else 0)) * RS_PONTO
        trades.append(dict(entrada=pos["te"], saida=idx[i], d=d, e=pos["e"], x=px, pnl=pnl, pnl0=d * (px - pos["e"]) * RS_PONTO, motivo=motivo, sinal=pos["sinal"]))
        pos = None

    for i in range(1, n):
        if pos is not None:
            d = pos["d"]
            if t[i] >= ZERAR or dia[i] != pos["dia"]:
                fechar(i, o[i], "zera")
            else:
                if (d == 1 and o[i] <= pos["sl"]) or (d == -1 and o[i] >= pos["sl"]):
                    fechar(i, o[i], "stop_gap" if o[i] != pos["sl"] else "stop", True)
                else:
                    fc, r_, v_, a_ = c[i - 1], rx[i - 1], vd[i - 1], at[i - 1]
                    if min(v_, r_) < fc < max(v_, r_):
                        fechar(i, o[i], "canal")
                    else:
                        est = d * (fc - r_) / a_
                        if est >= ARMA:
                            pos["arm"] = True
                        pos["pico"] = max(pos["pico"], est)
                        if pos["arm"] and est <= pos["pico"] - RECUO:
                            fechar(i, o[i], "esticada")
                        else:
                            novo = rnd(r_ + d * K * a_)
                            if (d == 1 and novo > o[i] - TICK) or (d == -1 and novo < o[i] + TICK):
                                fechar(i, o[i], "stop_alcancado")
                            else:
                                pos["sl"] = novo
                if pos is not None:
                    sl = pos["sl"]
                    if d == 1 and l[i] <= sl:
                        fechar(i, min(sl, o[i]), "stop", True)
                    elif d == -1 and h[i] >= sl:
                        fechar(i, max(sl, o[i]), "stop", True)
        elif i >= ini and sgn[i - 1] != 0 and dia[i - 1] == dia[i]:
            d = int(sgn[i - 1])
            if not (t[i] >= SEM_ENTRADA) and not np.isnan(at[i - 1]):
                sl = rnd(rx[i - 1] + d * K * at[i - 1]); px = o[i]
                if d * (px - sl) > TICK - 1e-9:
                    pos = dict(d=d, e=px, sl=sl, dia=dia[i], te=idx[i], arm=False, pico=-1e9, sinal=idx[i - 1])
                    if d == 1 and l[i] <= pos["sl"]:
                        fechar(i, min(pos["sl"], o[i]), "stop", True)
                    elif d == -1 and h[i] >= pos["sl"]:
                        fechar(i, max(pos["sl"], o[i]), "stop", True)
    aberto = None
    if pos is not None:
        d = pos["d"]
        aberto = dict(entrada=pos["te"], saida=idx[-1], d=d, e=pos["e"], x=c[-1], pnl=d * (c[-1] - pos["e"]) * RS_PONTO - CUSTO_PTS * RS_PONTO,
                      pnl0=d * (c[-1] - pos["e"]) * RS_PONTO, motivo="aberta", sinal=pos["sinal"])
    return pd.DataFrame(trades), aberto


# ---------------------------------------------------------------- descritores de contexto (identicos a R_desc.py da pesquisa)
def barras_tf(m1: pd.DataFrame, minutos: int) -> pd.DataFrame:
    b = reamostra(m1, minutos)
    b["wma"] = lwma(b.close, 34); b["smma"] = smma(b.close, 34)
    tr = pd.concat([b.high - b.low, (b.high - b.close.shift()).abs(), (b.low - b.close.shift()).abs()], axis=1).max(axis=1)
    b["atr"] = tr.rolling(14).mean()
    b["end"] = b.index + pd.Timedelta(minutes=minutos)
    return b


def descritores(m1: pd.DataFrame, Te: np.ndarray, d: np.ndarray, px: np.ndarray, atr5: np.ndarray) -> pd.DataFrame:
    """So barras de tempo maior JA FECHADAS na abertura da M5 de entrada (fim da barra <= Te)."""
    D = pd.DataFrame({"Te": Te, "d": d, "atr5": atr5, "px": px})
    Te = np.asarray(Te, dtype="datetime64[ns]")
    for nome, mins in (("M15", 15), ("M30", 30), ("H1", 60)):
        t = barras_tf(m1, mins); ends = t["end"].values
        k = np.searchsorted(ends, Te, side="right") - 1
        ok = k >= NX + 4; kk = np.where(ok, k, 0)
        H = t.high.to_numpy(); L = t.low.to_numpy(); C = t.close.to_numpy(); O = t.open.to_numpy()
        W_ = t.wma.to_numpy(); AT = t.atr.to_numpy()
        res = {c: np.full(len(D), np.nan) for c in ("depth", "posbox", "room", "lastrange")}
        for j in range(len(D)):
            i = kk[j]
            if not ok[j] or np.isnan(AT[i]) or np.isnan(W_[i - 3]):
                continue
            dd = d[j]; a = AT[i]
            hh = H[i - NB + 1:i + 1].max(); ll = L[i - NB + 1:i + 1].min()
            res["depth"][j] = ((hh - C[i]) if dd == 1 else (C[i] - ll)) / a
            hx = H[i - NX + 1:i + 1].max(); lx = L[i - NX + 1:i + 1].min()
            pb = (C[i] - lx) / max(hx - lx, 1e-9)
            res["posbox"][j] = pb if dd == 1 else 1 - pb
            dist = ((hx - D.px.iat[j]) if dd == 1 else (D.px.iat[j] - lx)) / a
            res["room"][j] = dist if dist > 0 else 9.0
            res["lastrange"][j] = H[i] - L[i]
        for c, v in res.items():
            D[f"{nome}_{c}"] = v
    mi = m1.index.values; h1 = m1.high.to_numpy(); l1 = m1.low.to_numpy()
    pos = np.searchsorted(mi, Te, side="left")
    for w in (30, 60):
        bx = np.full(len(D), np.nan)
        for j, p in enumerate(pos):
            if p >= w:
                bx[j] = h1[p - w:p].max() - l1[p - w:p].min()
        D[f"m1box{w}"] = bx
    D["m1box30_atr"] = D.m1box30 / D.atr5
    D["fit60"] = (D.m1box60 <= D.H1_lastrange).astype(float).where(D.m1box60.notna() & D.H1_lastrange.notna())
    return D


def marca_filtros(D: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=D.index)
    for fid, (col, op, lim) in FILTROS.items():
        x = D[col].astype(float)
        m = {">=": x >= lim, "<=": x <= lim, "==": x == lim}[op]
        out[f"ret_{fid}"] = m.fillna(False).astype(int)   # 1 = o filtro MANTEM a entrada; 0 = retiraria
    out["descritores_ok"] = D["H1_posbox"].notna().astype(int)
    return out


# ---------------------------------------------------------------- dados MT5
def baixa_m1(simbolo: str, desde: datetime, ate: datetime) -> pd.DataFrame:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 nao inicializou: {mt5.last_error()}")
    try:
        mt5.symbol_select(simbolo, True)
        # janela LARGA (nunca estreita: copy_rates_range com poucas horas devolve horario errado em alguns simbolos)
        r = mt5.copy_rates_range(simbolo, mt5.TIMEFRAME_M1, desde, ate)
        if r is None or len(r) == 0:
            raise RuntimeError(f"sem barras M1 de {simbolo} em {desde}..{ate}: {mt5.last_error()}")
        d = pd.DataFrame(r)
        d.index = pd.to_datetime(d["time"], unit="s")
        return d[["open", "high", "low", "close"]].sort_index()
    finally:
        mt5.shutdown()


def prepara_m1(m1: pd.DataFrame) -> pd.DataFrame:
    m1 = m1[~m1.index.duplicated(keep="last")]
    m1 = m1[(m1.index.hour * 60 + m1.index.minute) < 18 * 60 + 30]
    # descarta a barra M5 em formacao: so buckets M5 completos
    corte = m1.index[-1].floor("5min")
    return m1[m1.index < corte]


# ---------------------------------------------------------------- metricas
def metricas(p: np.ndarray) -> dict:
    p = np.asarray(p, float); n = len(p)
    if n == 0:
        return dict(n=0, win=np.nan, pf=np.nan, liquido=0.0, dd=0.0, por_trade=np.nan)
    g = p[p > 0].sum(); l = -p[p < 0].sum(); eq = np.cumsum(p); pk = np.maximum.accumulate(np.r_[0, eq])[1:]
    return dict(n=n, win=100 * (p > 0).mean(), pf=(g / l if l > 0 else np.inf), liquido=p.sum(), dd=float((pk - eq).max()), por_trade=p.mean())


def resumo(T: pd.DataFrame) -> pd.DataFrame:
    F = T[T.fechada == 1].sort_values("entrada")
    linhas = []
    for nome, m in [("BASE C1", np.ones(len(F), bool))] + [(f, F[f"ret_{f}"].to_numpy() == 1) for f in FILTROS]:
        k = metricas(F.pnl.to_numpy()[m]); ret = 100 * m.mean() if len(F) else np.nan
        linhas.append(dict(filtro=nome, entradas=k["n"], retidas_pct=round(ret, 1) if ret == ret else np.nan, win_pct=round(k["win"], 1) if k["win"] == k["win"] else np.nan,
                           pf=round(k["pf"], 2) if np.isfinite(k["pf"]) else k["pf"], liquido_rs=round(k["liquido"], 2), dd_rs=round(k["dd"], 2),
                           rs_por_trade=round(k["por_trade"], 2) if k["por_trade"] == k["por_trade"] else np.nan, hash_limiares=HASH_LIMIARES[:12]))
    return pd.DataFrame(linhas)


def br(df: pd.DataFrame) -> str:
    return df.to_string(index=False, float_format=lambda v: f"{v:.2f}".replace(".", ","))


# ---------------------------------------------------------------- principal
def roda(simbolo: str, desde: str, ate: str | None, csv: Path, resumo_csv: Path, m1: pd.DataFrame | None = None) -> pd.DataFrame:
    if hash_limiares() != HASH_LIMIARES:
        raise SystemExit("limiares diferentes dos congelados (hash nao confere) -- acompanhamento invalidado")
    d0 = pd.Timestamp(desde)
    if m1 is None:
        fim = (pd.Timestamp(ate) if ate else pd.Timestamp.now().normalize()) + timedelta(days=1)
        m1 = baixa_m1(simbolo, (d0 - timedelta(days=AQUECIMENTO_DIAS)).to_pydatetime(), fim.to_pydatetime())
    m1 = prepara_m1(m1)
    b5 = prepara(reamostra(m1, 5))
    sg = sinal_filtrado(b5)
    fechadas, aberta = simula(b5, sg, d0)
    linhas = fechadas.assign(fechada=1)
    if aberta is not None:
        linhas = pd.concat([linhas, pd.DataFrame([aberta]).assign(fechada=0)], ignore_index=True)
    if len(linhas):
        linhas = linhas[linhas.entrada >= d0].reset_index(drop=True)
    if len(linhas):
        Te = linhas.entrada.values
        atr5 = b5.atr.reindex(linhas.sinal).values; px = b5.close.reindex(linhas.sinal).values
        D = descritores(m1, Te, linhas.d.to_numpy().astype(int), px, atr5)
        linhas = pd.concat([linhas.reset_index(drop=True), marca_filtros(D)], axis=1)
    else:
        for f in FILTROS: linhas[f"ret_{f}"] = pd.Series(dtype=int)
        linhas["descritores_ok"] = pd.Series(dtype=int)
    linhas["simbolo"] = simbolo
    linhas["dados_ate"] = str(m1.index[-1] + pd.Timedelta(minutes=1))
    # acumula: substitui as linhas do periodo [desde, hoje], preserva as anteriores a --desde
    if csv.exists():
        ant = pd.read_csv(csv, parse_dates=["entrada", "saida", "sinal"])
        ant = ant[ant.entrada < d0]
        linhas = pd.concat([ant, linhas], ignore_index=True)
    linhas = linhas.sort_values("entrada").reset_index(drop=True)
    csv.parent.mkdir(parents=True, exist_ok=True)
    linhas.to_csv(csv, index=False)
    R = resumo(linhas) if len(linhas) else pd.DataFrame()
    if len(R):
        R.to_csv(resumo_csv, index=False)
    print(f"[{simbolo}] dados M1 ate {m1.index[-1] + pd.Timedelta(minutes=1)} | operacoes: {len(linhas)} "
          f"(fechadas {int((linhas.fechada == 1).sum()) if len(linhas) else 0}) | CSV: {csv}", flush=True)
    if len(R):
        print(br(R), flush=True)
    else:
        print("sem operacoes no periodo ainda.", flush=True)
    return linhas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default=DESDE_PADRAO, help="primeiro dia do acompanhamento (YYYY-MM-DD)")
    ap.add_argument("--ate", default=None, help="ultimo dia (padrao: hoje)")
    ap.add_argument("--simbolo", default="WIN@D")
    ap.add_argument("--csv", default=str(CSV_PADRAO), help="CSV acumulavel de operacoes + flags")
    ap.add_argument("--resumo", default=str(RESUMO_PADRAO), help="CSV do resumo base x filtrado")
    a = ap.parse_args(argv)
    roda(a.simbolo, a.desde, a.ate, Path(a.csv), Path(a.resumo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
