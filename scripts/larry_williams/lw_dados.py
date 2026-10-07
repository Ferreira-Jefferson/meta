"""Carga dos dados do motor Larry Williams (acoes B3 diarias, WIN/WDO M1, ETFs de bitcoin).

Este modulo e' I/O (nao e' parte das funcoes puras de `lw_setups`). Resultados de carga
pesados ficam em cache npz em `data/cache_lw/` (data/ nao e' versionado).
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import lw_sim as M  # noqa: E402

CACHE = RAIZ / "data" / "cache_lw"
CSV_FUTUROS = {
    "WIN": RAIZ / "data" / "wdo-mt5" / "WIN@D_M1_202110010900_202610011717.csv",
    "WDO": RAIZ / "data" / "wdo-mt5" / "WDO@D_M1_202109290900_202609291020.csv",
}
#: Pregao REGULAR: M1 das 09:00 ate 17:54 (inclusive). O CSV tem barras ate 18:24-18:29 em parte
#: dos pregoes (call de fechamento / horario estendido muda com o horario de verao) -- cortar
#: em 17:54 da' o MESMO pregao em todo o historico (decisao registrada em DECISOES.md).
MINUTO_INICIO, MINUTO_FIM = 9 * 60, 17 * 60 + 54
MIN_BARRAS_PREGAO = 300

# ---- janelas IS/OOS por TEMPO -------------------------------------------------
IS_FIM_ACOES = np.datetime64("2020-12-31")      # IS 2010-2020 / OOS 2021-hoje
IS_FIM_FUTUROS = np.datetime64("2024-06-30")    # IS 2021-10..2024-06 / OOS 2024-07-hoje
FRACAO_IS_BTC = 0.6                             # ETFs BTC: so' ~1 ano de M1 -> 60% / 40%

# ---- criterio de liquidez do universo de acoes ---------------------------------
GIRO_MIN_BRL = 20e6          # mediana do giro financeiro diario (close*volume), historico E ultimos 250 pregoes
MIN_BARRAS_IS = 750
MIN_BARRAS_OOS = 500
MAX_FRACAO_VOLUME_ZERO = 0.05
SALTO_MAX = 0.5              # |close/close_anterior - 1| acima disto = suspeita de desdobramento nao ajustado


def janelas(at: M.Ativo) -> dict[str, tuple[int, int]]:
    """{'IS': (i0,i1), 'OOS': (i0,i1)} em indices de pregao (i1 exclusivo)."""
    if at.classe in ("WIN", "WDO"):
        corte = np.searchsorted(at.datas, IS_FIM_FUTUROS, side="right")
    elif at.classe == "ETF_BTC":
        corte = int(at.n * FRACAO_IS_BTC)
    else:
        corte = np.searchsorted(at.datas, IS_FIM_ACOES, side="right")
    return {"IS": (0, int(corte)), "OOS": (int(corte), at.n)}


def semestres_is(at: M.Ativo) -> list[tuple[int, int]]:
    """Blocos semestrais dentro da janela IS (usados como 'blocos' de robustez em futuros)."""
    i0, i1 = janelas(at)["IS"]
    d = at.datas[i0:i1].astype("datetime64[M]").astype(int)
    sem = (d // 6)
    blocos = []
    for s in np.unique(sem):
        idx = np.flatnonzero(sem == s) + i0
        blocos.append((int(idx[0]), int(idx[-1]) + 1))
    return blocos


# ----------------------------------------------------------------------------
def _limpa_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    df = df.copy()
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


def carregar_acao(simbolo: str) -> M.Ativo | None:
    f = RAIZ / "data" / "raw" / f"{simbolo}_SA.parquet"
    if not f.exists():
        return None
    df = pd.read_parquet(f)
    df = _limpa_ohlc(df)
    df = df[df["volume"] > 0]                       # dias sem negocio nao sao pregoes operaveis
    df = df[~df.index.duplicated(keep="first")].sort_index()
    lote = 1 if simbolo == "BOVA11" else 100
    return M.criar_ativo(simbolo, "ACAO", df.index.values.astype("datetime64[D]"), df["open"].values,
                         df["high"].values, df["low"].values, df["close"].values, lote=lote)


def universo_acoes() -> tuple[list[str], list[dict]]:
    """Filtra as 157 acoes/ETFs de data/raw por liquidez e integridade.

    Retorna (simbolos_incluidos, tabela_de_decisao) -- a tabela diz POR QUE cada um entrou/saiu."""
    linhas = []
    incluidos = []
    for f in sorted(glob.glob(str(RAIZ / "data" / "raw" / "*_SA.parquet"))):
        s = os.path.basename(f)[:-11]
        df = pd.read_parquet(f)
        df = _limpa_ohlc(df)
        df = df[~df.index.duplicated(keep="first")].sort_index()
        giro = (df["close"] * df["volume"])
        zero = float((df["volume"] == 0).mean())
        d = df.index.values.astype("datetime64[D]")
        n_is = int((d <= IS_FIM_ACOES).sum())
        n_oos = int((d > IS_FIM_ACOES).sum())
        giro_hist = float(giro[df["volume"] > 0].median()) if len(df) else 0.0
        giro_250 = float(giro.tail(250).median()) if len(df) else 0.0
        salto = float((df["close"] / df["close"].shift(1) - 1).abs().max()) if len(df) > 1 else 0.0
        motivo = []
        if giro_hist < GIRO_MIN_BRL:
            motivo.append(f"giro historico {giro_hist/1e6:.1f}M < {GIRO_MIN_BRL/1e6:.0f}M")
        if giro_250 < GIRO_MIN_BRL:
            motivo.append(f"giro 250d {giro_250/1e6:.1f}M < {GIRO_MIN_BRL/1e6:.0f}M")
        if n_is < MIN_BARRAS_IS:
            motivo.append(f"{n_is} barras no IS < {MIN_BARRAS_IS}")
        if n_oos < MIN_BARRAS_OOS:
            motivo.append(f"{n_oos} barras no OOS < {MIN_BARRAS_OOS}")
        if zero > MAX_FRACAO_VOLUME_ZERO:
            motivo.append(f"{100*zero:.0f}% dos dias sem volume")
        if salto > SALTO_MAX:
            motivo.append(f"salto diario de {100*salto:.0f}% (desdobramento nao ajustado?)")
        if s == "BOVA11" and motivo and all("salto" not in m for m in motivo):
            motivo = []   # BOVA11 e' pedido explicito do dono
        linhas.append({"simbolo": s, "giro_hist_mi": giro_hist / 1e6, "giro_250_mi": giro_250 / 1e6,
                       "barras_is": n_is, "barras_oos": n_oos, "salto_max": salto,
                       "incluido": not motivo, "motivo": "; ".join(motivo)})
        if not motivo:
            incluidos.append(s)
    return incluidos, linhas


# ----------------------------------------------------------------------------
def _m1_csv(simbolo: str) -> pd.DataFrame:
    df = pd.read_csv(CSV_FUTUROS[simbolo], sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    t = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    df = df.assign(t=t)
    return df[["t", "open", "high", "low", "close", "tickvol"]]


def carregar_futuro(simbolo: str) -> M.Ativo:
    """WIN/WDO: M1 `@D` (ajuste por diferenca), so' pregao regular, pregoes com >= 300 barras."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"{simbolo}_M1_regular.npz"
    if cache.exists() and cache.stat().st_mtime > CSV_FUTUROS[simbolo].stat().st_mtime:
        z = np.load(cache)
        return _ativo_de_m1(simbolo, z["data_dia"], z["O"], z["H"], z["L"], z["C"], z["minuto"], z["dia_id"])
    df = _m1_csv(simbolo)
    minuto = (df["t"].dt.hour * 60 + df["t"].dt.minute).values
    df = df[(minuto >= MINUTO_INICIO) & (minuto <= MINUTO_FIM)]
    df = df[~df["t"].duplicated(keep="first")].sort_values("t")
    dia = df["t"].dt.normalize()
    cont = dia.groupby(dia).transform("size")
    df = df[cont >= MIN_BARRAS_PREGAO]
    dia = df["t"].dt.normalize()
    dias_unicos, dia_id = np.unique(dia.values, return_inverse=True)
    minuto = (df["t"].dt.hour * 60 + df["t"].dt.minute).values.astype(np.int32)
    np.savez_compressed(cache, data_dia=dias_unicos.astype("datetime64[D]"), O=df["open"].values,
                        H=df["high"].values, L=df["low"].values, C=df["close"].values,
                        minuto=minuto, dia_id=dia_id)
    return _ativo_de_m1(simbolo, dias_unicos.astype("datetime64[D]"), df["open"].values, df["high"].values,
                        df["low"].values, df["close"].values, minuto, dia_id)


def _ativo_de_m1(nome, datas, O, H, L, C, minuto, dia_id, classe: str | None = None, lote=None) -> M.Ativo:
    n = len(datas)
    O, H, L, C = (np.asarray(x, dtype=float) for x in (O, H, L, C))
    ini = np.searchsorted(dia_id, np.arange(n), side="left")
    fim = np.searchsorted(dia_id, np.arange(n), side="right")
    do = O[ini]
    dh = np.maximum.reduceat(H, ini)
    dl = np.minimum.reduceat(L, ini)
    dc = C[fim - 1]
    barras = {"O": O, "H": H, "L": L, "C": C, "minuto": np.asarray(minuto), "ini": ini, "fim": fim}
    return M.criar_ativo(nome, classe or nome, datas, do, dh, dl, dc, barras=barras, lote=lote)


# ----------------------------------------------------------------------------
#: Veiculos de bitcoin listados na B3 que o dono opera (CLAUDE.md / cripto_comum.py).
VEICULOS_BTC = ("BITH11", "BTCI11", "QBTC11")
MIN_BARRAS_M1_PREGAO = 96          # mesmo criterio de scripts/daytrade/cripto_comum.py
GIRO_MIN_BTC_BRL = 1e6


def carregar_btc(simbolo: str) -> tuple[M.Ativo | None, dict]:
    """ETF de bitcoin: M1 (UTC) -> pregao diario em horario de Brasilia. Aplica o criterio de
    cripto_comum.py: >= 96 barras M1 por pregao (mediana) e giro mediano > R$1 milhao/dia."""
    f = RAIZ / "data" / "raw_intraday" / f"{simbolo}.parquet"
    df = pd.read_parquet(f)
    idx = df.index.tz_convert("America/Sao_Paulo")
    df = df.assign(dia=idx.normalize().tz_localize(None), minuto=(idx.hour * 60 + idx.minute))
    df = df[(df["minuto"] >= 10 * 60) & (df["minuto"] <= 17 * 60 + 54)]
    df = df[df["real_volume"] > 0] if "real_volume" in df else df
    g = df.groupby("dia")
    barras_mediana = float(g.size().median())
    giro = float((df["close"] * df["real_volume"]).groupby(df["dia"]).sum().median())
    info = {"simbolo": simbolo, "pregoes": int(g.ngroups), "barras_m1_mediana": barras_mediana,
            "giro_mediano_brl": giro,
            "inicio": str(df["dia"].min())[:10], "fim": str(df["dia"].max())[:10]}
    motivo = []
    if barras_mediana < MIN_BARRAS_M1_PREGAO:
        motivo.append(f"{barras_mediana:.0f} barras/pregao < {MIN_BARRAS_M1_PREGAO}")
    if giro < GIRO_MIN_BTC_BRL:
        motivo.append(f"giro {giro/1e6:.2f}M < 1M")
    info["incluido"] = not motivo
    info["motivo"] = "; ".join(motivo)
    if motivo:
        return None, info
    d = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              n=("close", "size"))
    d = d[d["n"] >= MIN_BARRAS_M1_PREGAO]
    info["pregoes"] = int(len(d))
    at = M.criar_ativo(simbolo, "ETF_BTC", d.index.values.astype("datetime64[D]"), d["open"].values,
                       d["high"].values, d["low"].values, d["close"].values, lote=1)
    return at, info


def carregar(nome: str) -> M.Ativo:
    """Carrega qualquer ativo do experimento por nome ('WIN', 'WDO', 'BITH11', ... ou acao)."""
    if nome in ("WIN", "WDO"):
        return carregar_futuro(nome)
    if nome in VEICULOS_BTC:
        at, _ = carregar_btc(nome)
        return at
    return carregar_acao(nome)
