"""Carregador do WIN M1 sem leiloes (market_data_intraday.win_sem_leiloes).

Testes sinteticos usam so tmp_path/DataFrames (sem arquivo de data/). Os testes
de regressao em dados reais fazem skip se os arquivos grandes nao existem.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from market_data_intraday.win_sem_leiloes import (
    FASES_PADRAO,
    GRADE_PADRAO,
    RAIZ,
    carrega_fases,
    carrega_win_m1_sem_leiloes,
    filtra_ticks_continuo,
)

BASE_N = RAIZ / "data" / "comparativo_win_2026" / "m1_WIN$N.parquet"
BASE_N_HIST = RAIZ / "data" / "comparativo_win_2026" / "m1_WIN$N_2022_2025.parquet"
BASE_D = next(iter((RAIZ / "data" / "wdo-mt5").glob("WIN@D_M1_*.csv")), None) if (RAIZ / "data" / "wdo-mt5").exists() else None

precisa_fases = pytest.mark.skipif(not (FASES_PADRAO.exists() and BASE_N.exists() and GRADE_PADRAO.exists()),
                                   reason="fases/base/grade em data/ ausentes")

GRADE = pd.DataFrame({  # grade sintetica (nao depende de data/)
    "vigencia_inicio": ["2022-03-14", "2022-11-07"],
    "negociacao_fim": ["17:55", "18:25"],
})


def _dia_sintetico(dia: str, fim_h: int, fim_m: int, leilao_na_2a=False) -> pd.DataFrame:
    """Barras 09:00 .. fim-1min com volume 3000; leilao na 1a (ou 2a) e call na ultima."""
    ini = pd.Timestamp(dia) + pd.Timedelta(hours=9)
    fim = pd.Timestamp(dia) + pd.Timedelta(hours=fim_h, minutes=fim_m)
    idx = pd.date_range(ini, fim - pd.Timedelta(minutes=1), freq="min")
    n = len(idx)
    px = 100000.0 + np.arange(n)
    d = pd.DataFrame({"open": px, "high": px + 5, "low": px - 5, "close": px + 1,
                      "tick_volume": 300.0, "real_volume": 3000.0}, index=idx)
    d.iloc[1 if leilao_na_2a else 0, d.columns.get_loc("real_volume")] = 60000.0
    d.iloc[-1, d.columns.get_loc("real_volume")] = 22000.0
    d.iloc[-1, d.columns.get_loc("close")] = 100500.0  # preco do call, longe do continuo
    d.iloc[-1, d.columns.get_loc("high")] = 100500.0
    return d


def test_sintetico_sem_tick_marca_proxy_e_leilao_na_2a_barra() -> None:
    # dia de 17:55 (verao) + dia de 18:25; leilao na 2a barra no primeiro
    d = pd.concat([_dia_sintetico("2022-05-02", 17, 55, leilao_na_2a=True),
                   _dia_sintetico("2022-12-01", 18, 25)])
    r = carrega_win_m1_sem_leiloes(d, fases=pd.DataFrame(columns=["data"]), grade=GRADE)
    b, dias = r.barras, r.dias
    d1, d2 = dias.index
    assert dias.loc[d1, "ultima_barra_continua"] == pd.Timestamp("2022-05-02 17:54")
    assert dias.loc[d2, "ultima_barra_continua"] == pd.Timestamp("2022-12-01 18:24")
    assert dias["proxy"].all() and dias["call_barra"].all()
    # close da ultima barra = close da anterior (proxy); call em coluna propria
    ult = b[b.ultima_continua]
    ant = d.close.shift(1).loc[ult.index]
    assert (ult.close.values == ant.values).all()
    assert (dias.call_preco == 100500.0).all()
    assert (dias.call_volume == 19000.0).all()  # 22000 - mediana 3000
    assert (ult.real_volume == 3000.0).all()
    # leilao: 2a barra no dia 1 (NAO assume a 1a), 1a no dia 2
    assert dias.loc[d1, "leilao_hora"] == pd.Timestamp("2022-05-02 09:01")
    assert dias.loc[d2, "leilao_hora"] == pd.Timestamp("2022-12-01 09:00")
    assert b.loc["2022-05-02 09:01", "flag_leilao"] and not b.loc["2022-05-02 09:00", "flag_leilao"]
    assert (dias.leilao_volume == 57000.0).all() and dias.leilao_volume_estimado.all()
    assert b.real_volume.max() <= 3000.0  # sem volume extremo
    assert (b.index.time < pd.Timestamp("18:25").time()).all()


def test_sintetico_com_fases_usa_ultimo_negocio_e_primeiro_negocio() -> None:
    d = _dia_sintetico("2022-12-01", 18, 25)
    fases = pd.DataFrame([{
        "data": "2022-12-01", "pre_hora_leilao": "09:00:30.000", "pre_preco_inicio": 100000.0,
        "pre_preco_fechamento": 100000.0, "pre_volume": 50000, "pre_negocios": 80,
        "pregao_preco_inicio": 100004.0, "pregao_preco_fechamento": 100490.0,
        "pos_volume": 20000, "pos_negocios": 90, "pos_preco_fechamento": 100500.0,
    }])
    r = carrega_win_m1_sem_leiloes(d, fases=fases, grade=GRADE)
    b = r.barras
    assert b.iloc[0].open == 100004.0 and b.iloc[0].real_volume == 10000.0
    assert b.iloc[-1].close == 100490.0 and b.iloc[-1].real_volume == 2000.0
    assert not b.proxy.any()
    assert r.dias.iloc[0].call_preco == 100500.0 and r.dias.iloc[0].leilao_preco == 100000.0


def test_sintetico_reamostragem_sem_call_e_ancorada_em_0900() -> None:
    d = pd.concat([_dia_sintetico("2022-05-02", 17, 55), _dia_sintetico("2022-12-01", 18, 25)])
    for tf in ("M5", "M30", "H1"):
        r = carrega_win_m1_sem_leiloes(d, fases=pd.DataFrame(columns=["data"]), grade=GRADE, tf=tf)
        m = {"M5": 5, "M30": 30, "H1": 60}[tf]
        mins = (r.barras.index - r.barras.index.normalize() - pd.Timedelta(hours=9)) // pd.Timedelta(minutes=1)
        assert (mins % m == 0).all()
        assert r.barras.real_volume.max() <= 3000.0 * m  # nenhum volume de leilao/call
        assert (r.barras[r.barras.ultima_continua].index.values == r.dias.ultima_barra_continua.values).all()
        assert r.barras.groupby(r.barras.index.normalize()).ultima_continua.sum().eq(1).all()


def test_filtra_ticks_remove_leilao_e_call(tmp_path: Path) -> None:
    dia = pd.Timestamp("2022-12-01")
    base = int(dia.value // 10**6)  # t do npz = relogio BRT rotulado como UTC

    def ms(h: int, m: int, s: float) -> int:
        return base + int(((h * 60 + m) * 60 + s) * 1000)

    t = np.array([ms(9, 3, 14.728), ms(9, 3, 14.733), ms(12, 0, 0), ms(18, 24, 59.9),
                  ms(18, 25, 0), ms(18, 31, 14.5)])
    p = np.arange(6) + 100
    v = np.ones(6, dtype=int)
    t2, p2, v2 = filtra_ticks_continuo(t, p, v, grade=GRADE)
    assert list(p2) == [101, 102, 103]
    # dia de 17:55
    dia = pd.Timestamp("2022-05-02")
    base = int(dia.value // 10**6)
    t = np.array([ms(9, 0, 1), ms(9, 0, 2), ms(17, 54, 59), ms(17, 55, 0), ms(18, 24, 59)])
    t3, p3, _ = filtra_ticks_continuo(t, np.arange(5), np.ones(5, dtype=int), grade=GRADE)
    assert list(p3) == [1, 2]


# ----------------------------------------------------------------- dados reais (skip se ausentes)
@precisa_fases
def test_127_dias_close_da_ultima_barra_igual_ao_ultimo_negocio_continuo() -> None:
    f = carrega_fases()
    r = carrega_win_m1_sem_leiloes(BASE_N, f.index.min(), f.index.max())
    ult = r.barras[r.barras.ultima_continua]
    assert len(ult) == len(f) == 127
    assert (ult.index.normalize() == f.index).all()
    assert (ult.close.values == f.pregao_preco_fechamento.values).all()
    assert not r.dias.proxy.any()
    assert (r.dias.ultima_barra_continua.dt.strftime("%H:%M") == "18:24").all()
    # open da 1a barra do leilao = 1o negocio do continuo
    ab = r.barras[r.barras.flag_leilao]
    assert (ab.open.values == f.loc[ab.index.normalize(), "pregao_preco_inicio"].values).all()


@precisa_fases
def test_volumes_extremos_sem_leilao() -> None:
    f = carrega_fases()
    r = carrega_win_m1_sem_leiloes(BASE_N, f.index.min(), f.index.max())
    b, v = r.barras, r.barras.real_volume
    pos = np.flatnonzero(b.ultima_continua.values)
    razao = np.array([v.iloc[p] / v.iloc[p - 5:p].median() for p in pos])
    assert np.median(razao) < 1.5            # antes do ajuste: ~7x
    pa = np.flatnonzero(b.flag_leilao.values)
    razao_a = np.array([v.iloc[p] / v.iloc[p + 1:p + 6].median() for p in pa])
    assert np.median(razao_a) < 1.5          # antes do ajuste: ~2,5x ou mais
    assert (r.dias.call_volume.dropna() > 4000).all() and (r.dias.leilao_volume.dropna() > 0).all()


@pytest.mark.parametrize("base,ini,fim", [(BASE_N, "2026-01-01", "2026-06-30"),
                                           (BASE_N_HIST, "2023-01-01", "2023-12-31"),
                                           (BASE_D, "2023-01-01", "2023-12-31")])
def test_nenhuma_barra_comeca_no_fim_do_continuo_ou_depois(base, ini, fim) -> None:
    if base is None or not Path(base).exists() or not GRADE_PADRAO.exists():
        pytest.skip("base/grade ausente")
    r = carrega_win_m1_sem_leiloes(base, ini, fim)
    fim = r.dias["fim_continuo"].reindex(r.barras.index.normalize()).values
    assert (r.barras.index.values < fim).all()
    assert (r.barras.index.time >= pd.Timestamp("09:00").time()).all()
    # 18:24 em dias de 18:25; 17:54 em dias de 17:55
    assert (r.dias.ultima_barra_continua + pd.Timedelta(minutes=1) == r.dias.fim_continuo).mean() > 0.95


@precisa_fases
@pytest.mark.parametrize("tf", ["M5", "M30"])
def test_m5_m30_sem_call(tf: str) -> None:
    f = carrega_fases()
    m1 = carrega_win_m1_sem_leiloes(BASE_N, f.index.min(), f.index.max())
    r = carrega_win_m1_sem_leiloes(BASE_N, f.index.min(), f.index.max(), tf=tf)
    ult = r.barras[r.barras.ultima_continua]
    assert (ult.close.values == f.pregao_preco_fechamento.values).all()
    # volume agregado == soma do M1 ja sem call
    assert r.barras.real_volume.sum() == m1.barras.real_volume.sum()
    fim = r.dias["fim_continuo"].reindex(r.barras.index.normalize()).values
    assert (r.barras.index.values < fim).all()


@precisa_fases
def test_filtra_ticks_reproduz_o_pregao_da_tabela_de_fases() -> None:
    """Os ticks filtrados de cada dia devem comecar no 1o negocio continuo, terminar no
    ultimo antes do fim da grade e somar o volume do pregao da tabela de fases."""
    f = carrega_fases()
    pasta = RAIZ / "data" / "comparativo_win_2026" / "ticks"
    if not pasta.exists():
        pytest.skip("ticks ausentes")
    dias = [d for d in f.index if (pasta / f"{d:%Y-%m-%d}.npz").exists()
            and pd.notna(f.loc[d, "pre_preco_inicio"])
            and f.loc[d, "fonte"] == "ticks"]  # dias "ticks+M1" tem volume completado pelo M1: nao bate com os ticks
    assert len(dias) >= 120
    for d in dias:
        z = np.load(pasta / f"{d:%Y-%m-%d}.npz")
        _, p, v = filtra_ticks_continuo(z["t"], z["p"], z["v"])
        # o .npz funde ticks consecutivos de mesmo preco no mesmo minuto, entao o 1o negocio
        # continuo pode ter sido absorvido pela linha do leilao: tolera 1 tick (5 pts)
        assert abs(p[0] - f.loc[d, "pregao_preco_inicio"]) <= 5, d
        assert p[-1] == f.loc[d, "pregao_preco_fechamento"], d
        assert abs(v.sum() - f.loc[d, "pregao_volume"]) <= 0.001 * f.loc[d, "pregao_volume"], d
