"""Carregador unico do WIN M1 SEM os leiloes de abertura e de fechamento.

Por que existe (auditoria 2026-10-06, scripts/daytrade/win_fases_correlacao_2026_10_06/
auditoria_leiloes/AUDITORIA.md): nas bases M1 do WIN a 1a barra do dia carrega o
leilao de abertura (open = preco do leilao, ~56 mil contratos) e a ultima barra
(18:24, ou 17:54 quando o pregao acabava 17:55) carrega o call de fechamento
(close = preco do call, ~22 mil contra ~3 mil nas vizinhas). Zerar "no fim do
dia" cai no call; o erro medio e ~86 pts (~R$17/contrato).

Camada: feature (`market_data_intraday`), importa so pandas/numpy. Le arquivo
porque os caminhos sao passados pelo chamador; nao importa outra feature.

Como corrige cada dia
---------------------
Com fases (`data/win_fases_pregao_6m.csv`, 127 dias abr-out/2026, medidas por tick):
  * ultima barra continua: close = `pregao_preco_fechamento` (ultimo negocio do
    continuo); volume e tick_volume menos `pos_volume`/`pos_negocios`; proxy=False.
  * 1a barra: open = `pregao_preco_inicio`; volume menos `pre_volume`/`pre_negocios`.
  * Bases ajustadas (WIN@, WIN@D) tem o preco deslocado por uma constante diaria;
    os precos das fases sao deslocados pelo mesmo delta (close da barra do call
    menos `pos_preco_fechamento`; se nao houver barra do call, open do leilao
    menos `pre_preco_inicio`). Em `WIN$N` o delta e 0.
Sem fases (2022-25 e inicio de 2026) -- APROXIMACAO, nao ha tick:
  * close da ultima barra continua = close da barra anterior ao call, `proxy=True`.
  * volume do call = excesso da barra sobre a MEDIANA das 5 barras anteriores
    (`call_volume_estimado=True`).
  * barra do leilao = a de MAIOR volume entre 09:00 e 09:04 (em 2022-25 a 2a
    barra costuma ter mais volume que a 1a; nao se assume a 1a). Volume do leilao
    = excesso sobre a mediana das 5 barras seguintes (`leilao_volume_estimado=True`).
    O OPEN dessa barra NAO e corrigido (nao ha o 1o negocio do continuo).
  * High/low: so quando o preco removido (leilao/call) era a propria maxima/minima
    da barra ela e encolhida para max/min(open, close) -- limite inferior do
    intervalo verdadeiro (a barra fica marcada em `hl_aprox`).

Fim do continuo por data: `data/b3_grade_horaria_win.csv` (`negociacao_fim`).
Barras que comecam em `fim` ou depois (call, pos-call) sao descartadas.
Reamostragem (M5/M30/H1...) so DEPOIS dos ajustes, ancorada em 09:00 por dia.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
FASES_PADRAO = RAIZ / "data" / "win_fases_pregao_6m.csv"
GRADE_PADRAO = RAIZ / "data" / "b3_grade_horaria_win.csv"
_DIRS_BASE = (RAIZ / "data" / "comparativo_win_2026", RAIZ / "data" / "wdo-mt5", RAIZ / "data")
_ABERTURA = pd.Timedelta(hours=9)
_JANELA_LEILAO = pd.Timedelta(minutes=5)
_UM_MIN = pd.Timedelta(minutes=1)
_OFFSET_TICKS_MS = 0  # t do .npz ja e o relogio do servidor MT5 (BRT) rotulado como UTC; nao ha 3h a desfazer
_JANELA_LEILAO_MS = 5  # o cruzamento do leilao sai em 0-2 ms num preco so; o continuo comeca ~4 ms depois
_COLS_BASE = ["open", "high", "low", "close", "tick_volume", "real_volume"]


class WinSemLeiloes(NamedTuple):
    """`barras`: OHLCV no timeframe pedido + proxy, flag_leilao, ultima_continua, hl_aprox.
    `dias`: uma linha por pregao (indice = data) com call_*/leilao_*/ultima_barra_continua."""
    barras: pd.DataFrame
    dias: pd.DataFrame


# --------------------------------------------------------------------------- leitura
def carrega_grade(grade: str | Path | pd.DataFrame | None = None) -> pd.DataFrame:
    g = grade.copy() if isinstance(grade, pd.DataFrame) else pd.read_csv(grade or GRADE_PADRAO)
    g = g.dropna(subset=["negociacao_fim"]).copy()
    g["vigencia_inicio"] = pd.to_datetime(g["vigencia_inicio"])
    return g.sort_values("vigencia_inicio").reset_index(drop=True)


def fim_continuo(dia, grade: pd.DataFrame) -> pd.Timestamp:
    """Instante em que o continuo acaba (dai em diante: call). Grade vigente na data."""
    dia = pd.Timestamp(dia).normalize()
    vig = grade[grade["vigencia_inicio"] <= dia]
    if vig.empty:
        raise ValueError(f"data {dia.date()} anterior a primeira vigencia da grade")
    hh, mm = str(vig.iloc[-1]["negociacao_fim"]).split(":")
    return dia + pd.Timedelta(hours=int(hh), minutes=int(mm))


def carrega_fases(fases: str | Path | pd.DataFrame | None = None) -> pd.DataFrame | None:
    """Fases por tick indexadas por data; None se o arquivo nao existe."""
    if isinstance(fases, pd.DataFrame):
        f = fases.copy()
    else:
        p = Path(fases) if fases else FASES_PADRAO
        if not p.exists():
            return None
        f = pd.read_csv(p, sep=";", encoding="utf-8-sig")
    f["data"] = pd.to_datetime(f["data"])
    return f.set_index("data")


def _le_base(base) -> pd.DataFrame:
    if isinstance(base, pd.DataFrame):
        d = base[_COLS_BASE].copy()
    else:
        p = Path(base)
        if not p.exists():
            achados = [x / p.name for x in _DIRS_BASE if (x / p.name).exists()]
            if not achados:
                raise FileNotFoundError(f"base nao encontrada: {base}")
            p = achados[0]
        if p.suffix == ".parquet":
            d = pd.read_parquet(p)[_COLS_BASE]
        else:  # TSV exportado do MT5
            raw = pd.read_csv(p, sep="\t")
            d = pd.DataFrame({
                "open": raw["<OPEN>"], "high": raw["<HIGH>"], "low": raw["<LOW>"],
                "close": raw["<CLOSE>"], "tick_volume": raw["<TICKVOL>"],
                "real_volume": raw["<VOL>"],
            })
            d.index = pd.to_datetime(raw["<DATE>"] + " " + raw["<TIME>"], format="%Y.%m.%d %H:%M:%S")
    d.index = pd.DatetimeIndex(d.index).as_unit("ns")
    d.index.name = "time"
    return d.astype("float64")


def _carrega_bruta(base) -> pd.DataFrame:
    bases = base if isinstance(base, (list, tuple)) else [base]
    partes = [_le_base(b) for b in bases]
    d = pd.concat(partes) if len(partes) > 1 else partes[0]
    return d[~d.index.duplicated(keep="last")].sort_index()


# --------------------------------------------------------------------------- ajuste por dia
def _encolhe_hl(h, l, o, c, i, preco_removido, h0, l0, aprox) -> None:
    """Se o preco removido era a maxima/minima da barra, encolhe ate max/min(open, close)."""
    if h0 == preco_removido:
        h[i] = max(o[i], c[i]); aprox[i] = True
    if l0 == preco_removido:
        l[i] = min(o[i], c[i]); aprox[i] = True
    h[i] = max(h[i], o[i], c[i])
    l[i] = min(l[i], o[i], c[i])


def _ajusta_dia(dia, tm, o, h, l, c, tv, rv, fim, f, proxy, flag_l, ult, aprox) -> dict:
    """Ajusta in-place as fatias do dia; devolve as colunas por dia."""
    n = len(tm)
    r = dict(call_preco=np.nan, call_volume=np.nan, call_volume_estimado=False, call_barra=False,
             leilao_preco=np.nan, leilao_hora=pd.NaT, leilao_volume=np.nan,
             leilao_volume_estimado=False, flag_leilao=False, proxy=False, tem_fases=f is not None)
    ult[-1] = True
    il = n - 1 if tm[-1] == fim - _UM_MIN else None
    # ---- barra do leilao
    ia = None
    if f is not None:
        hora = (dia + pd.Timedelta(f["pre_hora_leilao"])).floor("min")
        w = np.nonzero(tm == hora)[0]
        ia = int(w[0]) if len(w) else None
    else:
        w = np.nonzero((tm >= dia + _ABERTURA) & (tm < dia + _ABERTURA + _JANELA_LEILAO))[0]
        if len(w):
            ia = int(w[np.argmax(rv[w])])
    # ---- delta de escala (so com fases)
    delta = 0.0
    if f is not None:
        if il is not None:
            delta = c[il] - f["pos_preco_fechamento"]
        elif ia is not None:
            delta = o[ia] - f["pre_preco_inicio"]
    # ---- call
    if il is not None:
        r["call_barra"] = True
        r["call_preco"] = float(c[il])
        h0, l0, preco = h[il], l[il], c[il]
        if f is not None:
            cv, cn = float(f["pos_volume"]), float(f["pos_negocios"])
            r["call_volume"] = min(cv, rv[il])
            c[il] = f["pregao_preco_fechamento"] + delta
        else:
            ant = slice(max(0, il - 5), il)
            cv = max(0.0, rv[il] - (float(np.median(rv[ant])) if il else 0.0))
            cn = max(0.0, tv[il] - (float(np.median(tv[ant])) if il else 0.0))
            r["call_volume"] = cv
            r["call_volume_estimado"] = True
            if il >= 1:
                c[il] = c[il - 1]
            proxy[il] = True
            r["proxy"] = True
        rv[il] = max(0.0, rv[il] - cv)
        tv[il] = max(0.0, tv[il] - cn)
        _encolhe_hl(h, l, o, c, il, preco, h0, l0, aprox)
    # ---- leilao de abertura
    if ia is not None:
        r["flag_leilao"] = True
        flag_l[ia] = True
        r["leilao_preco"] = float(o[ia])
        r["leilao_hora"] = dia + pd.Timedelta(f["pre_hora_leilao"]) if f is not None else tm[ia]
        h0, l0, preco = h[ia], l[ia], o[ia]
        if f is not None:
            av, an = float(f["pre_volume"]), float(f["pre_negocios"])
            r["leilao_volume"] = min(av, rv[ia])
            o[ia] = f["pregao_preco_inicio"] + delta
            _encolhe_hl(h, l, o, c, ia, preco, h0, l0, aprox)
        else:
            viz = slice(ia + 1, ia + 6) if ia + 1 < n else slice(max(0, ia - 5), ia)
            av = max(0.0, rv[ia] - float(np.median(rv[viz])))
            an = max(0.0, tv[ia] - float(np.median(tv[viz])))
            r["leilao_volume"] = av
            r["leilao_volume_estimado"] = True
        rv[ia] = max(0.0, rv[ia] - av)
        tv[ia] = max(0.0, tv[ia] - an)
    return r


def _reamostra(d: pd.DataFrame, minutos: int) -> pd.DataFrame:
    dia = d.index.normalize()
    desde = (d.index - dia - _ABERTURA) // _UM_MIN
    chave = dia + _ABERTURA + pd.to_timedelta((desde // minutos) * minutos, unit="min")
    g = d.groupby(chave, sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "tick_volume": g["tick_volume"].sum(),
        "real_volume": g["real_volume"].sum(), "proxy": g["proxy"].any(),
        "flag_leilao": g["flag_leilao"].any(), "ultima_continua": g["ultima_continua"].any(),
        "hl_aprox": g["hl_aprox"].any(),
    })
    out.index.name = "time"
    return out


_TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}


def carrega_win_m1_sem_leiloes(base, inicio=None, fim=None, tf: str = "M1", *,
                               fases: str | Path | pd.DataFrame | None = None,
                               grade: str | Path | pd.DataFrame | None = None) -> WinSemLeiloes:
    """Carrega WIN M1 sem os leiloes de abertura e fechamento.

    base: nome/caminho de `m1_WIN$N.parquet`, `m1_WIN$N_2022_2025.parquet` ou
          `data/wdo-mt5/WIN@*_M1_*.csv`; lista de bases (concatena; a ultima vence
          em horario duplicado); ou DataFrame OHLCV (colunas do parquet).
    inicio, fim: datas inclusivas (str/Timestamp) ou None.
    tf: "M1", "M5", "M15", "M30", "H1", "H4" (ou numero de minutos como int).
    fases: CSV/DataFrame das fases por tick (padrao `data/win_fases_pregao_6m.csv`;
           se o arquivo nao existir, tudo cai na aproximacao sem tick).
    grade: `data/b3_grade_horaria_win.csv`.
    Devolve `WinSemLeiloes(barras, dias)`; ver docstring do modulo.
    """
    minutos = tf if isinstance(tf, int) else _TF_MIN[str(tf).upper()]
    g = carrega_grade(grade)
    fs = carrega_fases(fases)
    d = _carrega_bruta(base)
    if inicio is not None:
        d = d[d.index >= pd.Timestamp(inicio).normalize()]
    if fim is not None:
        d = d[d.index < pd.Timestamp(fim).normalize() + pd.Timedelta(days=1)]
    dias_idx = d.index.normalize()
    fim_por_dia = {x: fim_continuo(x, g) for x in dias_idx.unique()}
    fim_bar = dias_idx.map(fim_por_dia)
    d = d[(d.index >= dias_idx + _ABERTURA) & (d.index < fim_bar)]  # descarta call e pos-call
    if d.empty:
        raise ValueError("nenhuma barra no periodo pedido")
    dias_idx = d.index.normalize()
    o, h, l, c, tv, rv = (d[k].to_numpy(copy=True) for k in _COLS_BASE)
    proxy = np.zeros(len(d), bool)
    flag_l, ult, aprox = proxy.copy(), proxy.copy(), proxy.copy()
    linhas = {}
    cortes = np.flatnonzero(np.r_[True, dias_idx[1:] != dias_idx[:-1], True])
    for a, b in zip(cortes[:-1], cortes[1:]):
        dia = dias_idx[a]
        f = fs.loc[dia] if (fs is not None and dia in fs.index) else None
        sl = slice(a, b)
        linhas[dia] = _ajusta_dia(dia, d.index[sl], o[sl], h[sl], l[sl], c[sl], tv[sl], rv[sl],
                                  fim_por_dia[dia], f, proxy[sl], flag_l[sl], ult[sl], aprox[sl])
    m1 = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "tick_volume": tv,
                       "real_volume": rv, "proxy": proxy, "flag_leilao": flag_l,
                       "ultima_continua": ult, "hl_aprox": aprox}, index=d.index)
    barras = m1 if minutos == 1 else _reamostra(m1, minutos)
    dias = pd.DataFrame.from_dict(linhas, orient="index")
    dias.index.name = "data"
    dias["fim_continuo"] = pd.Series(fim_por_dia)
    ub = barras.index[barras["ultima_continua"].to_numpy()]
    dias["ultima_barra_continua"] = pd.Series(ub, index=ub.normalize())
    return WinSemLeiloes(barras, dias)


# --------------------------------------------------------------------------- ticks
def filtra_ticks_continuo(t, p, v, *, grade: str | Path | pd.DataFrame | None = None,
                          deslocamento_ms: int = _OFFSET_TICKS_MS):
    """Remove dos ticks `.npz` (t ms, p, v) os negocios fora do continuo.

    Fora = (a) leilao de abertura: a sequencia inicial do dia no MESMO preco do 1o tick
    e a ate `_JANELA_LEILAO_MS` dele (mesma regra que gerou data/win_fases_pregao_6m.csv);
    (b) a partir do fim do pregao da grade (>= 18:25 ou 17:55, inclui o call);
    (c) antes das 09:00. `t` do npz ja e BRT; `deslocamento_ms` so existe para fonte
    que venha em outro relogio.
    Aceita varios dias no mesmo array (t crescente). Devolve (t, p, v) filtrados.
    """
    t = np.asarray(t); p = np.asarray(p); v = np.asarray(v)
    if t.size == 0:
        return t, p, v
    g = carrega_grade(grade)
    brt = t.astype("int64") + deslocamento_ms
    dia_ms = brt // 86_400_000 * 86_400_000
    manter = np.ones(len(t), bool)
    for dm in np.unique(dia_ms):
        idx = np.flatnonzero(dia_ms == dm)
        fim_ms = int((fim_continuo(pd.Timestamp(int(dm), unit="ms"), g)
                      - pd.Timestamp(int(dm), unit="ms")).total_seconds() * 1000)
        ms = brt[idx] - dm
        ok = (ms >= int(_ABERTURA.total_seconds() * 1000)) & (ms < fim_ms)
        t0, p0 = brt[idx][0], p[idx][0]
        leilao = np.minimum.accumulate((p[idx] == p0) & (brt[idx] <= t0 + _JANELA_LEILAO_MS))
        ok &= ~leilao.astype(bool)
        manter[idx] = ok
    return t[manter], p[manter], v[manter]
