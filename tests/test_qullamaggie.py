"""Qullamaggie: núcleo puro (scripts/qullamaggie/qm_core.py), espelho do EA mt5/QullamaggieLib.mqh.

Cada teste constrói a série à mão e checa UMA regra da fonte primária.
"""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "qullamaggie"))
import qm_core as q                                    # noqa: E402
from qm_portfolio import run_portfolio                 # noqa: E402

P = q.QmParams()


def series(closes, spread=0.025, vol=1e6, opens=None):
    c = np.asarray(closes, float)
    o = c.copy() if opens is None else np.asarray(opens, float)
    n = len(c)
    return {"date": np.datetime64("2020-01-01") + np.arange(n).astype("timedelta64[D]"),
            "o": o, "h": np.maximum(o, c) * (1 + spread), "l": np.minimum(o, c) * (1 - spread),
            "c": c, "v": np.full(n, vol)}


def flag_closes(n_flat=60, run_to=1.6, run_bars=15, consol=12):
    """lateral -> alta de 60% -> bandeira apertada com mínimas ascendentes."""
    base = [100 + 0.05 * (k % 3) for k in range(n_flat)]
    run = list(np.linspace(100, 100 * run_to, run_bars + 1)[1:])
    top = run[-1]
    flag = [top * (0.985 + 0.0015 * k) for k in range(consol)]
    return base + run + flag


# ------------------------------------------------------------------ indicadores
def test_sma_adr_dvol_contra_calculo_ingenuo():
    rng = np.random.default_rng(1)
    c = 50 + rng.random(80)
    h, l = c * 1.03, c * 0.98
    v = rng.integers(1000, 5000, 80).astype(float)
    assert q.sma(c, 10)[40] == pytest.approx(c[31:41].mean())
    assert q.adr(h, l, 20)[50] == pytest.approx((h[31:51] / l[31:51]).mean() - 1)
    assert q.dollar_volume(c, v, 20)[50] == pytest.approx((c[31:51] * v[31:51]).mean())
    assert math.isnan(q.sma(c, 10)[8])


def test_prior_move_up_exige_minima_ANTES_da_maxima():
    # sobe 100 -> 150: alta de 50%; o inverso (cai 150 -> 100) não conta como alta
    up = np.linspace(100, 150, 30)
    down = up[::-1]
    mv_up = q.prior_move_up(up, up, 30)[-1]
    mv_dn = q.prior_move_up(down, down, 30)[-1]
    assert mv_up == pytest.approx(0.5)
    assert mv_dn == pytest.approx(0.0)


# --------------------------------------------------------------------- breakout
def test_breakout_detecta_bandeira_e_gatilho_e_maxima_da_consolidacao():
    a = series(flag_closes())
    ok, trig, stop = q.breakout_setup(a, P)
    i = len(a["c"]) - 1
    assert ok[i]
    assert trig[i] == pytest.approx(a["h"][i - P.consol_bars + 1: i + 1].max())
    assert stop[i] == pytest.approx(a["l"][i - P.stop_bars + 1: i + 1].min())
    assert 0 < (trig[i] - stop[i]) / trig[i] <= P.stop_adr_max * q.adr(a["h"], a["l"])[i]


def test_breakout_rejeita_sem_alta_previa():
    closes = [100 + 0.05 * (k % 3) for k in range(100)]       # só lateral
    ok, _, _ = q.breakout_setup(series(closes), P)
    assert not ok.any()


def test_breakout_rejeita_consolidacao_funda():
    c = flag_closes()
    c[-6] *= 0.6                                               # derrubão no meio da bandeira
    ok, _, _ = q.breakout_setup(series(c), P)
    assert not ok[-1]


def test_breakout_rejeita_abaixo_da_media_de_10_dias():
    c = flag_closes()
    c[-1] = c[-1] * 0.93                                       # fecha furando a 10/20
    ok, _, _ = q.breakout_setup(series(c), P)
    assert not ok[-1]


def test_breakout_rejeita_adr_baixo():
    ok, _, _ = q.breakout_setup(series(flag_closes(), spread=0.004), P)
    assert not ok[-1]


def test_stop_mais_largo_que_o_adr_nao_opera():
    ok, _, _ = q.breakout_setup(series(flag_closes()), P.with_(stop_bars=12, stop_adr_max=0.2))
    assert not ok[-1]


def test_sem_look_ahead_sinal_nao_muda_com_barras_futuras():
    c = flag_closes()
    a1 = series(c)
    a2 = series(c + [c[-1] * 1.5, c[-1] * 0.5, c[-1] * 2])
    i = len(c) - 1
    o1, t1, s1 = q.breakout_setup(a1, P)
    o2, t2, s2 = q.breakout_setup(a2, P)
    assert o1[i] == o2[i] and t1[i] == t2[i] and s1[i] == s2[i]


# -------------------------------------------------------------- trade: long
def long_path(levels, spread=0.0, n_pre=40):
    """barras de teste: [pre-roll de 100 .. ] + closes dados. Abre = fecha anterior (sem gap)."""
    c = [100.0] * n_pre + list(levels)
    o = [100.0] + c[:-1]
    return series(c, spread=spread, opens=o)


def test_entrada_nao_preenche_se_maxima_nao_alcanca_o_gatilho():
    a = long_path([100, 100])
    assert q.run_long(a, 41, level=105.0, stop=95.0, p=P) is None


def test_gap_acima_do_gatilho_enche_na_abertura_nao_no_gatilho():
    a = long_path([100, 112, 112], spread=0.0)
    a["o"][41] = 110.0
    t = q.run_long(a, 41, level=105.0, stop=95.0, p=P)
    assert t["entry"] == 110.0


def test_stop_na_barra_da_entrada_pessimista_vs_otimista():
    a = long_path([100, 104], spread=0.0)
    a["h"][41], a["l"][41], a["o"][41], a["c"][41] = 106.0, 94.0, 100.0, 105.0
    pess = q.run_long(a, 41, 105.0, 95.0, P.with_(same_bar="pess"))
    opt = q.run_long(a, 41, 105.0, 95.0, P.with_(same_bar="opt"))
    assert pess["reason"] == "stop" and pess["x"] == 41
    assert opt["reason"] != "stop" or opt["x"] > 41


def test_gap_abaixo_do_stop_sai_na_abertura_pior_que_o_stop():
    a = long_path([106, 106, 90, 90])
    a["o"][42] = 90.0
    t = q.run_long(a, 40, 105.0, 98.0, P.with_(leg_cost=0.0))
    assert t["reason"] == "gap" and t["x"] == 42
    assert t["ret"] == pytest.approx(90 / 105 - 1, rel=1e-6)


def test_parcial_no_3o_pregao_leva_stop_ao_zero_a_zero_e_resto_no_trailing():
    # sobe forte (parcial lucrativa), depois cai abaixo da SMA10 -> trail
    up = [106 + 3 * k for k in range(8)]                       # 106..127
    a = long_path(up + [118, 117, 116], spread=0.0)
    p = P.with_(leg_cost=0.0, partial_days=3, partial_frac=0.5, trail_ma=10)
    t = q.run_long(a, 40, 105.0, 98.0, p)
    assert t is not None
    assert t["reason"] in ("trail", "stop", "open")
    # parcial de 50% no 3º pregão após a entrada: retorno > retorno de simplesmente sair no stop
    assert t["ret"] > 0


def test_stop_zero_a_zero_apos_parcial_nao_perde_dinheiro_na_metade_restante():
    # sobe, realiza parcial, depois despenca para baixo da entrada: resto sai em ~f (0%)
    path = [106, 108, 110, 112, 100, 90]
    a = long_path(path, spread=0.0)
    p = P.with_(leg_cost=0.0, partial_days=3, partial_frac=0.5, trail_ma=200)
    t = q.run_long(a, 40, 105.0, 98.0, p)
    assert t["reason"] in ("gap", "stop")
    # metade em +x% (aberto no 3º pregão) e metade no zero a zero ou no gap
    assert t["ret"] > -0.5 * (105 - 90) / 105


def test_trailing_so_vale_apos_o_prazo_da_parcial():
    # fecha abaixo da SMA10 no 1º dia seguinte: NÃO sai (held < partial_days)
    path = [106, 104, 104, 104, 104]
    a = long_path(path, spread=0.0)
    p = P.with_(leg_cost=0.0, partial_days=3, trail_ma=3)
    t = q.run_long(a, 40, 105.0, 90.0, p)
    assert t["x"] >= 40 + 3 or t["reason"] == "open"


# ---------------------------------------------------------------- ep / parabolic
def test_ep_exige_gap_e_acao_dormente():
    n = 120
    c = np.full(n, 50.0) + np.sin(np.arange(n)) * 0.1
    o = np.concatenate(([50.0], c[:-1]))
    o[100] = c[99] * 1.15                                      # gap de 15%
    a = series(c, spread=0.05, opens=o)
    ok, lvl, stp = q.ep_setup(a, P.with_(adr_min=0.03))
    assert ok[100] and not ok[99]
    assert lvl[100] == pytest.approx(o[100]) and stp[100] < o[100]
    # mesma barra, mas a ação já tinha subido 60% antes: não é EP "dormente"
    c2 = c.copy()
    c2[:99] = np.linspace(31, 50, 99)
    a2 = series(c2, spread=0.05, opens=np.concatenate(([31.0], c2[:-1])))
    a2["o"][100] = c2[99] * 1.15
    ok2, _, _ = q.ep_setup(a2, P.with_(adr_min=0.03))
    assert not ok2[100]


def test_parabolic_short_exige_altas_seguidas_e_movimento():
    base = [20.0] * 60
    para = [20 * 1.12 ** k for k in range(1, 6)]               # 5 altas seguidas, +76%
    a = series(base + para, spread=0.04)
    p = P.with_(adr_min=0.03, para_move=0.30)
    d = len(a["c"])
    a = series(base + para + [para[-1]], spread=0.04)
    ok, lvl, stp = q.para_setup(a, p)
    assert ok[d]
    assert stp[d] > lvl[d]


def test_parabolic_short_alvo_na_media_cobre_com_lucro():
    c = [20.0] * 60 + [20 * 1.12 ** k for k in range(1, 6)] + [30, 27, 24, 22, 21, 20]
    a = series(c, spread=0.01)
    e = 66
    t = q.run_short(a, e, level=a["o"][e], stop=a["o"][e] * 1.2, p=P.with_(leg_cost=0.0, para_target_ma=10))
    assert t is not None and t["side"] == -1 and t["ret"] > 0


# ------------------------------------------------------------------- carteira
def fake_trade(ie, ix, ret, stop_pct=0.05, entry=20.0, path=None):
    path = np.full(ix - ie + 1, ret) if path is None else path
    return {"sym": "X", "ie": ie, "ix": ix, "date_e": np.datetime64("2020-01-01") + np.timedelta64(ie, "D"),
            "date_x": np.datetime64("2020-01-01") + np.timedelta64(ix, "D"), "entry": entry, "stop_pct": stop_pct,
            "ret": ret, "path": path, "rank": 0.0}


def test_carteira_perde_no_stop_exatamente_o_risco_configurado():
    p = P.with_(capital=100_000, risk_pct=0.005, max_pos_pct=0.9, lot=1)
    cal = np.datetime64("2020-01-01") + np.arange(30).astype("timedelta64[D]")
    res = run_portfolio([fake_trade(2, 5, -0.05)], cal, p,
                        np.datetime64("2019-01-01"), np.datetime64("2030-01-01"))
    assert res.net == pytest.approx(-500.0, rel=1e-6)          # 0,5% de 100k
    assert res.trades == 1


def test_carteira_respeita_teto_de_posicoes_e_lote():
    p = P.with_(capital=100_000, max_positions=2, lot=100)
    cal = np.datetime64("2020-01-01") + np.arange(30).astype("timedelta64[D]")
    trades = [fake_trade(2, 10, 0.1) for _ in range(5)]
    res = run_portfolio(trades, cal, p, np.datetime64("2019-01-01"), np.datetime64("2030-01-01"))
    assert res.trades == 2 and res.skipped == 3


def test_maxdd_e_marcado_a_mercado_nao_so_no_realizado():
    p = P.with_(capital=100_000, risk_pct=0.005, max_pos_pct=0.5, lot=1)
    cal = np.datetime64("2020-01-01") + np.arange(30).astype("timedelta64[D]")
    path = np.array([0.0, -0.20, -0.20, 0.10, 0.10])           # afunda 20% no meio, termina +10%
    res = run_portfolio([fake_trade(2, 6, 0.10, stop_pct=0.05, path=path)], cal, p,
                        np.datetime64("2019-01-01"), np.datetime64("2030-01-01"))
    assert res.maxdd_brl > 0 and res.net > 0
