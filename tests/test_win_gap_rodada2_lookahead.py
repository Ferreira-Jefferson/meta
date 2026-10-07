"""Anti look-ahead da rodada 2 do estudo WIN gap (scripts/daytrade/win_gap_estrategia_2026_10_06/rodada2_2026_10_06).

Cada teste muda SO' o futuro (dias/barras/ticks depois do instante de decisao) e exige que a decisao e os
normalizadores nao se mexam. Paralelo-seguro: so' `tmp_path`, sem ordem entre testes, sem arquivo fixo.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "scripts" / "daytrade" / "win_gap_estrategia_2026_10_06"
for p in (BASE, BASE / "rodada2_2026_10_06"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import ctx as C  # noqa: E402
import dados  # noqa: E402
import regras as R  # noqa: E402
import sim as S  # noqa: E402


def test_atr_prev_so_usa_dias_anteriores():
    dias = [pd.Timestamp("2026-04-06") + pd.Timedelta(days=i) for i in range(30)]
    amp = pd.Series(np.arange(30, dtype=float) * 10 + 1000, index=dias)
    base = C.calcula_atr_prev(amp, [d.date() for d in dias])
    k = dias[15]
    amp2 = amp.copy()
    amp2[amp2.index >= k] = 99999.0           # muda o dia D e todo o futuro
    alt = C.calcula_atr_prev(amp2, [d.date() for d in dias])
    assert alt[k.date()] == base[k.date()]    # ATR de D nao enxerga o proprio D
    assert all(np.isclose(alt[d.date()], base[d.date()], equal_nan=True) for d in dias[:16])
    assert np.isnan(base[dias[0].date()]) and np.isnan(base[dias[2].date()])   # precisa de >= 3 dias anteriores
    assert base[dias[3].date()] == pytest.approx(np.mean(amp.iloc[:3]))


def _base_sintetica(tmp_path, call_vol, proxy=False):
    n = len(call_vol)
    dias = pd.bdate_range("2026-04-06", periods=n)
    idx = [d + pd.Timedelta(hours=9 + k * 0.0833) for d in dias for k in range(3)]
    bars = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "tick_volume": 1.0, "real_volume": 1.0,
                         "proxy": False, "flag_leilao": False, "ultima_continua": False, "hl_aprox": False}, index=pd.DatetimeIndex(idx))
    pq = tmp_path / "m5.parquet"
    bars.to_parquet(pq)
    d = pd.DataFrame({"data": dias, "call_preco": 100.0, "call_volume": call_vol, "call_volume_estimado": False,
                      "call_barra": True, "leilao_preco": 100.0, "leilao_hora": "", "leilao_volume": 1.0,
                      "leilao_volume_estimado": False, "flag_leilao": False, "proxy": proxy, "tem_fases": not proxy,
                      "fim_continuo": dias + pd.Timedelta(hours=18, minutes=25),
                      "ultima_barra_continua": dias + pd.Timedelta(hours=18, minutes=24)})
    csv = tmp_path / "dias.csv"
    d.to_csv(csv, sep=";", index=False, encoding="utf-8-sig")
    return pq, csv


def test_vol_alto_so_usa_passado(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    vol = rng.uniform(1000, 9000, 80)
    pq, csv = _base_sintetica(tmp_path, vol)
    monkeypatch.setitem(dados.BASES, "sint", (pq, csv))
    _, d0 = dados.carrega("sint")
    k = 50
    vol2 = vol.copy()
    vol2[k:] = 1e9                                    # futuro (de k em diante) absurdo
    (tmp_path / "b").mkdir()
    pq2, csv2 = _base_sintetica(tmp_path / "b", vol2)
    monkeypatch.setitem(dados.BASES, "sint2", (pq2, csv2))
    _, d1 = dados.carrega("sint2")
    # vol_alto[D] depende de call_volume[D-1] e da mediana de dias <= D-1: D = k usa vol2[k-1] (inalterado)
    a, b = d0["vol_alto"].to_numpy(), d1["vol_alto"].to_numpy()
    assert np.array_equal(a[: k + 1], b[: k + 1], equal_nan=True)
    assert not np.array_equal(a[k + 2:], b[k + 2:], equal_nan=True)   # o teste enxerga uma mudanca de verdade depois


def test_decisao_so_depende_da_1a_barra_e_do_contexto():
    c = dict(gap=-500.0, vol_alto=False, prev_call=100000.0, atr_prev=1500.0, o1=100000.0, h1=100400.0, l1=99900.0, c1=100300.0)
    ent = dict(fam="V2", recuo=150.0)
    s = R.gatilho(c, ent)
    lim = R.limite(c, s, 150.0)
    ex = R.SAIDAS[3]
    sa = R.saida_de(c, s, lim, ex, s, lim)
    # o contexto nao carrega nada alem da 1a barra, do gap e de D-1 para tras
    assert set(c) <= {"gap", "vol_alto", "prev_call", "atr_prev", "o1", "h1", "l1", "c1", "t1"}
    assert s == 1 and lim == 100150.0 and sa.stop == 99450.0 and sa.target == 100850.0


def _dia(p_ticks, t_ticks):
    st = np.arange(32_400_000, 32_400_000 + 3 * S.M5, S.M5)
    return S.DiaTicks(t=np.asarray(t_ticks, "int32"), p=np.asarray(p_ticks, "int32"), bst=st,
                      bo=np.full(3, 100.0), bh=np.full(3, 101.0), bl=np.full(3, 99.0), bc=np.full(3, 100.0))


def test_ordem_nao_enche_antes_do_fecho_da_1a_barra():
    t_sinal = 32_400_000 + S.M5
    # o preco toca o limite (long a 99.800) ANTES do sinal e nao volta a toca-lo depois: sem fill
    t = [32_400_000 + 1000, 32_400_000 + 2000, t_sinal + 1000, t_sinal + 2000]
    p = [99_700, 99_800, 100_000, 100_100]
    d = _dia(p, t)
    sa = S.Saida(stop=99_000.0, target=None)
    assert S.simula_tick(d, +1, 99_800.0, sa, 1, "toque", t_sinal) is None
    # tocando depois do sinal enche
    d2 = _dia(p + [99_800], t + [t_sinal + 3000])
    tr = S.simula_tick(d2, +1, 99_800.0, sa, 1, "toque", t_sinal)
    assert tr is not None and tr.fill_t == t_sinal + 3000


def test_saida_ignora_ticks_anteriores_ao_fill_e_futuro_nao_muda_o_passado():
    t_sinal = 32_400_000 + S.M5
    t = [t_sinal + 100, t_sinal + 200, t_sinal + 300, t_sinal + 400]
    p = [99_700, 99_900, 99_800, 100_300]          # 99_700 (antes do fill) violaria um stop em 99_750
    d = _dia(p, t)
    sa = S.Saida(stop=99_650.0, target=100_200.0)
    tr = S.simula_tick(d, +1, 99_800.0, sa, 1, "toque", t_sinal)
    assert tr.legs[-1].reason == "alvo" and tr.fill_t == t_sinal + 100
    # mudar ticks DEPOIS da saida nao altera o resultado
    d2 = _dia(p + [90_000], t + [t_sinal + 500])
    tr2 = S.simula_tick(d2, +1, 99_800.0, sa, 1, "toque", t_sinal)
    assert (tr2.legs[0].reason, tr2.legs[0].exit_price) == (tr.legs[0].reason, tr.legs[0].exit_price)
