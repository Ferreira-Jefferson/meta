"""kit_pernadas -- ferramenta de levantamento de pernadas do WIN (setembro/2026).

Uso rapido:
    import kit_pernadas as k
    m1 = k.carregar_m1()                 # agosto (aquecimento) + setembro
    f  = k.features_m1(m1)               # features causais, 1 linha por minuto
    ev = k.eventos(m1, "5min")           # eventos "recuou X do extremo" + features + rotulo
    st = k.estado_zigzag_m1(m1)          # estado do zigzag 750 minuto a minuto

Convencoes
- Caminho dentro da vela: alta (close>=open) minima->maxima; baixa maxima->minima. Dois pontos por vela.
- Pernada = zigzag de 750 pts, por pregao (estado zerado a cada dia).
- TUDO que e feature/estado e causal: a linha do minuto t so usa velas M1 com indice <= t
  e velas M5/M15 ja COMPLETAS em t. Rotulos ficam em funcoes separadas e olham o futuro.
- Indice da vela = abertura da vela. Linha t descreve o mundo ao FIM do minuto t.
- Evento (X, TF): o extremo corrente E da pernada em andamento (maximo se a perna e de alta)
  e o preco recua X de E pela primeira vez. Rotulo: do extremo, o movimento contrario chega a
  750 antes de o preco voltar a superar E?  (= E vira pivo confirmado de 750)
  Duas familias de evento (coluna `familia`):
    "extremo": o acima (E = extremo corrente do zigzag de 750).
    "balanco": o de `precursores_indicadores.md` da rodada 1. Pivos de um zigzag menor (100 pts, no caminho
       da vela TF); evento = o preco ja andou X do ultimo pivo confirmado (1x por pivo); rotulo = esse
       balanco chega a 750 do pivo antes de recuar 100 do seu extremo ("antes de virar").
  Features do evento: M1/M5/M15 ate o minuto anterior a abertura da vela TF onde o recuo
  ocorreu (conservador) + estado do zigzag no instante do evento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CSV = r"C:/Users/Jeffe/Documents/study/meta/data/wdo-mt5/WINV26_M1_202604151210_202610011824.csv"
PERNADA = 750.0
INICIO_AQUECIMENTO = "2026-08-01"   # so aquece indicadores
INICIO_ANALISE = "2026-09-01"
FIM_ANALISE = "2026-10-01"
XS = (150, 250, 375, 500)
TFS = {"M5": "5min", "M15": "15min", "H1": "60min"}


# ----------------------------------------------------------------- dados
def carregar_m1(path: str = CSV) -> pd.DataFrame:
    """M1 de agosto (aquecimento) e setembro/2026. Colunas: open high low close vol, dia, analise(bool)."""
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df = df[(df.ts >= INICIO_AQUECIMENTO) & (df.ts < FIM_ANALISE)].set_index("ts")
    df = df[["open", "high", "low", "close", "vol"]].astype(float)
    df["dia"] = df.index.normalize()
    df["analise"] = df.index >= INICIO_ANALISE
    return df


def reamostrar(m1: pd.DataFrame, tf: str, so_completas_ate: pd.Timestamp | None = None) -> pd.DataFrame:
    """OHLCV na janela tf (label=abertura). Se so_completas_ate=t, descarta velas cujo fim (calendario) > t+1min."""
    rule = TFS.get(tf, tf)
    r = m1.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum"}).dropna()
    r["dia"] = r.index.normalize()
    r["fim"] = r.index + pd.Timedelta(rule)          # instante em que a vela completa
    if so_completas_ate is not None:
        r = r[r["fim"] <= so_completas_ate + pd.Timedelta("1min")]
    return r


def caminho(m: pd.DataFrame) -> tuple[list, list, list]:
    """Caminho dentro da vela: (ts, preco, idx_vela) com 2 pontos por vela."""
    ts, pr, ix = [], [], []
    o, h, l, c = m["open"].values, m["high"].values, m["low"].values, m["close"].values
    idx = m.index
    for i in range(len(m)):
        a, b = (l[i], h[i]) if c[i] >= o[i] else (h[i], l[i])
        ts += [idx[i], idx[i]]
        pr += [a, b]
        ix += [i, i]
    return ts, pr, ix


# ----------------------------------------------------------------- zigzag causal
class _ZZ:
    """Zigzag de limiar T processado ponto a ponto (so passado)."""

    def __init__(self, T=PERNADA):
        self.T = T
        self.reset()

    def reset(self):
        self.dir = 0              # +1 perna de alta em curso, -1 baixa, 0 indefinido (inicio do dia)
        self.hi = self.lo = None
        self.hi_t = self.lo_t = None
        self.E = None             # extremo corrente
        self.E_t = None
        self.piv = None           # ultimo pivo confirmado (preco)
        self.piv_t = None
        self.perna_ini = None     # preco de onde a perna corrente partiu
        self.n_piv = 0
        self.perna_conf = np.nan  # tamanho da ultima perna COMPLETA (pivo a pivo)
        self.ult_perna_dir = 0

    def passo(self, t, p):
        """Retorna True se confirmou um pivo neste ponto."""
        T = self.T
        if self.dir == 0:
            if self.hi is None:
                self.hi = self.lo = p
                self.hi_t = self.lo_t = t
                self.E, self.E_t = p, t
                return False
            if p > self.hi:
                self.hi, self.hi_t = p, t
            if p < self.lo:
                self.lo, self.lo_t = p, t
            if p >= self.lo + T:                        # sobe 750 da minima: minima vira pivo
                self.piv, self.piv_t = self.lo, self.lo_t
                self.dir, self.E, self.E_t = 1, p, t
                self.perna_ini = self.lo
                self.n_piv = 1
                return True
            if p <= self.hi - T:                        # cai 750 da maxima: maxima vira pivo
                self.piv, self.piv_t = self.hi, self.hi_t
                self.dir, self.E, self.E_t = -1, p, t
                self.perna_ini = self.hi
                self.n_piv = 1
                return True
            # extremo corrente (para estado) = o mais afastado do inicio
            return False
        if self.dir == 1:
            if p > self.E:
                self.E, self.E_t = p, t
            elif p <= self.E - T:                       # E vira pivo; perna de baixa
                self.perna_conf = abs(self.E - self.piv)
                self.piv, self.piv_t = self.E, self.E_t
                self.perna_ini = self.E
                self.dir, self.E, self.E_t = -1, p, t
                self.n_piv += 1
                return True
        else:
            if p < self.E:
                self.E, self.E_t = p, t
            elif p >= self.E + T:
                self.perna_conf = abs(self.E - self.piv)
                self.piv, self.piv_t = self.E, self.E_t
                self.perna_ini = self.E
                self.dir, self.E, self.E_t = 1, p, t
                self.n_piv += 1
                return True
        return False

    def estado(self, p_atual):
        """Estado no instante (apos o ponto p_atual)."""
        if self.dir == 0:
            # sem pivo ainda: E = extremo mais recente entre maxima e minima do dia
            if self.hi is None:
                return dict(dir=0, edir=0, E=np.nan, E_t=None, recuo=np.nan, leg_ate_E=np.nan,
                            perna_conf=np.nan, n_piv=0)
            up = self.hi_t >= self.lo_t
            E = self.hi if up else self.lo
            return dict(dir=0, edir=1 if up else -1, E=E, E_t=self.hi_t if up else self.lo_t,
                        recuo=abs(E - p_atual), leg_ate_E=self.hi - self.lo, perna_conf=np.nan, n_piv=0)
        return dict(dir=self.dir, edir=self.dir, E=self.E, E_t=self.E_t, recuo=abs(self.E - p_atual),
                    leg_ate_E=abs(self.E - self.perna_ini), perna_conf=self.perna_conf, n_piv=self.n_piv)


def estado_zigzag_m1(m1: pd.DataFrame) -> pd.DataFrame:
    """Estado do zigzag 750 ao fim de cada minuto (so passado). Apenas pregoes de setembro.

    Colunas: dir (+1/-1/0), E (extremo corrente), E_min (minutos desde E), recuo (distancia do E ao close),
    recuo_max (maior recuo desde E), leg_ate_E (tamanho da perna ate E), perna_conf (ultima perna completa),
    n_piv, andou_dia (high-low do dia ate t), min_abertura.
    """
    d = m1[m1["analise"]]
    out = []
    for dia, g in d.groupby("dia"):
        zz = _ZZ()
        t0 = g.index[0]
        hi_dia, lo_dia = -np.inf, np.inf
        recuo_max, E_prev = 0.0, None
        for ts_, o, h, l, c in zip(g.index, g["open"], g["high"], g["low"], g["close"]):
            pts = (l, h) if c >= o else (h, l)
            rmax_min = 0.0
            for p in pts:
                zz.passo(ts_, p)
                sp = zz.estado(p)
                if sp["E"] != E_prev:
                    recuo_max, E_prev = 0.0, sp["E"]
                elif sp["E"] == sp["E"]:
                    recuo_max = max(recuo_max, sp["recuo"])
            hi_dia, lo_dia = max(hi_dia, h), min(lo_dia, l)
            s = zz.estado(c)
            s.update(ts=ts_, E_min=(ts_ - s["E_t"]).total_seconds() / 60 if s["E_t"] is not None else np.nan,
                     recuo_max=recuo_max, andou_dia=hi_dia - lo_dia,
                     min_abertura=(ts_ - t0).total_seconds() / 60)
            out.append(s)
    return pd.DataFrame(out).set_index("ts")


# ----------------------------------------------------------------- features causais
def _atr_completas(r: pd.DataFrame, n: int) -> pd.Series:
    """Media do range das ultimas n velas completas, indexada pelo fim da vela."""
    rng = (r["high"] - r["low"])
    m = rng.rolling(n, min_periods=n).mean()
    m.index = r["fim"]
    return m


def _alinha(serie_fim: pd.Series, idx_m1: pd.DatetimeIndex) -> pd.Series:
    """Valor da vela completa mais recente ao fim do minuto t (fim <= t+1min)."""
    s = serie_fim.dropna()
    return s.reindex(s.index.union(idx_m1 + pd.Timedelta("1min"))).ffill().reindex(idx_m1 + pd.Timedelta("1min")).set_axis(idx_m1)


def features_m1(m1: pd.DataFrame) -> pd.DataFrame:
    """Features no instante t (fim do minuto t), so passado. Linhas: minutos de setembro.

    hora (decimal, ex 9.5), min_abertura, atr5_m5, atr50_m5, r_m5=atr5/atr50, idem m15 (atr5_m15...),
    rh_m5/rh_m15 (ATR5 / media do ATR5 no mesmo minuto dos 5 pregoes anteriores = volatilidade sem o relogio),
    vol30_300 (media do range M1 30min / 300min), range_dia (high-low do dia ate t),
    + estado do zigzag (dir, E, recuo, recuo_max, leg_ate_E, perna_conf, n_piv).
    """
    idx = m1.index
    f = pd.DataFrame(index=idx)
    for tf in ("M5", "M15"):
        r = reamostrar(m1, tf)
        a5, a50 = _atr_completas(r, 5), _atr_completas(r, 50)
        f[f"atr5_{tf.lower()}"] = _alinha(a5, idx).values
        f[f"atr50_{tf.lower()}"] = _alinha(a50, idx).values
        f[f"r_{tf.lower()}"] = f[f"atr5_{tf.lower()}"] / f[f"atr50_{tf.lower()}"]
    rng1 = m1["high"] - m1["low"]
    f["vol30_300"] = rng1.rolling(30, min_periods=30).mean() / rng1.rolling(300, min_periods=300).mean()
    f["hora"] = idx.hour + idx.minute / 60.0
    # volatilidade curta "sem relogio": ATR5 de agora / media do ATR5 nas 5 ultimas ocorrencias do mesmo minuto do dia
    tod = idx.strftime("%H:%M")
    for tf in ("m5", "m15"):
        a = f[f"atr5_{tf}"]
        ref = a.groupby(tod).transform(lambda x: x.shift(1).rolling(5, min_periods=3).mean())
        f[f"rh_{tf}"] = a / ref
    f = f[m1["analise"]]
    st = estado_zigzag_m1(m1)
    f = f.join(st)
    f["range_dia"] = f["andou_dia"]
    return f


# ----------------------------------------------------------------- eventos (X, TF)
def _features_na_abertura(feat: pd.DataFrame, ts_open: pd.Timestamp) -> dict:
    """Features M1/M5/M15 conhecidas ao abrir a vela ts_open (ultimo minuto anterior)."""
    i = feat.index.searchsorted(ts_open) - 1      # ultimo minuto < ts_open
    if i < 0:
        return {}
    row = feat.iloc[i]
    d = dict(row[["atr5_m5", "atr50_m5", "r_m5", "atr5_m15", "atr50_m15", "r_m15", "rh_m5", "rh_m15", "vol30_300"]])
    mesmo_dia = feat.index[i].normalize() == ts_open.normalize()
    d["hora"] = ts_open.hour + ts_open.minute / 60.0
    d["range_dia"] = row["range_dia"] if mesmo_dia else 0.0
    return d


def eventos(m1: pd.DataFrame, tf: str, xs=XS, feat: pd.DataFrame | None = None) -> pd.DataFrame:
    """Eventos 'preco recuou X do extremo corrente (primeira vez para esse extremo)'. Sem rotulo.

    Colunas: tf, X, dia, ts_vela (abertura da vela TF), i_ponto (indice no caminho), dir (da perna que
    acabou: +1 = E e maximo), E, leg_ate_E, perna_conf, n_piv + features na abertura da vela.
    Rotulo vem de `rotular`.
    """
    if feat is None:
        feat = features_m1(m1)
    r = reamostrar(m1[m1["analise"]], tf)
    linhas = []
    for dia, g in r.groupby("dia"):
        ts, pr, ix = caminho(g)
        zz = _ZZ()
        E_prev = None
        feitos: set = set()
        for k, (t, p) in enumerate(zip(ts, pr)):
            zz.passo(t, p)
            if zz.dir == 0 and zz.hi is None:
                continue
            s = zz.estado(p)
            chave = (s["E"], s["E_t"])
            if chave != E_prev:
                feitos = set()
                E_prev = chave
            for X in xs:
                if X in feitos:
                    continue
                if s["recuo"] >= X:
                    feitos.add(X)
                    row = dict(familia="extremo", tf=tf, X=X, dia=dia, ts_vela=ts[k], i_ponto=k, dia_pontos=(ts, pr),
                               dir=s["edir"], E=s["E"], leg_ate_E=s["leg_ate_E"], perna_conf=s["perna_conf"],
                               n_piv=s["n_piv"])
                    row.update(_features_na_abertura(feat, ts[k]))
                    linhas.append(row)
    ev = pd.DataFrame(linhas)
    return ev


def eventos_balanco(m1: pd.DataFrame, tf: str, xs=XS, feat: pd.DataFrame | None = None,
                    Tmin: float = 100.0) -> pd.DataFrame:
    """Familia "balanco": ja andou X do ultimo pivo (zigzag Tmin). perna_conf = tamanho do balanco anterior
    (o que terminou no pivo); leg_ate_E = mesmo valor que perna_conf, para uso uniforme. Sem rotulo."""
    if feat is None:
        feat = features_m1(m1)
    r = reamostrar(m1[m1["analise"]], tf)
    linhas = []
    for dia, g in r.groupby("dia"):
        ts, pr, ix = caminho(g)
        zz = _ZZ(Tmin)
        feitos: set = set()
        piv_prev = None
        for k, (t, p) in enumerate(zip(ts, pr)):
            zz.passo(t, p)
            if zz.dir == 0:
                continue
            chave = (zz.piv, zz.piv_t, zz.n_piv)
            if chave != piv_prev:
                feitos = set()
                piv_prev = chave
            dist = abs(p - zz.piv)
            for X in xs:
                if X not in feitos and dist >= X:
                    feitos.add(X)
                    row = dict(familia="balanco", tf=tf, X=X, dia=dia, ts_vela=ts[k], i_ponto=k,
                               dia_pontos=(ts, pr), dir=zz.dir, E=zz.piv, leg_ate_E=zz.perna_conf,
                               perna_conf=zz.perna_conf, n_piv=zz.n_piv)
                    row.update(_features_na_abertura(feat, ts[k]))
                    linhas.append(row)
    return pd.DataFrame(linhas)


def rotular(ev: pd.DataFrame, T: float = PERNADA, Tmin: float = 100.0) -> pd.DataFrame:
    """OLHA O FUTURO (so para medir). y=1: do extremo E o preco recua T antes de superar E. y=NaN: dia acabou."""
    ys = []
    for _, e in ev.iterrows():
        ts, pr = e["dia_pontos"]
        y = np.nan
        if e["familia"] == "balanco":     # E = pivo; balanco chega a T do pivo antes de recuar Tmin do extremo?
            ext = pr[e["i_ponto"]]
            for p in pr[e["i_ponto"] + 1:]:
                ext = max(ext, p) if e["dir"] == 1 else min(ext, p)
                if abs(ext - e["E"]) >= T:
                    y = 1
                    break
                if abs(ext - p) >= Tmin:
                    y = 0
                    break
            ys.append(y)
            continue
        for p in pr[e["i_ponto"] + 1:]:
            if e["dir"] == 1:
                if p > e["E"]:
                    y = 0
                    break
                if p <= e["E"] - T:
                    y = 1
                    break
            else:
                if p < e["E"]:
                    y = 0
                    break
                if p >= e["E"] + T:
                    y = 1
                    break
        ys.append(y)
    out = ev.copy()
    out["y"] = ys
    return out.drop(columns="dia_pontos")


def todos_eventos(m1=None, tfs=("M5", "M15"), xs=XS) -> pd.DataFrame:
    """Eventos rotulados para os TFs pedidos."""
    m1 = carregar_m1() if m1 is None else m1
    feat = features_m1(m1)
    partes = []
    for tf in tfs:
        partes.append(rotular(eventos(m1, tf, xs, feat)))
        partes.append(rotular(eventos_balanco(m1, tf, xs, feat)))
    return pd.concat(partes, ignore_index=True)
