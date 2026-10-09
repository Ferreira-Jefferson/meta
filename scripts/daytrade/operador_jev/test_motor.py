"""Testes do motor SEM LLM (operador falso deterministico). Rodar: python -m pytest scripts/daytrade/operador_jev/test_motor.py"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mercado import Mercado  # noqa: E402
from motor import run_dia, Sessao  # noqa: E402

N_M1 = 565          # 09:00..18:24
FLAT = 559          # M1 das 18:19 (fim 18:24 -> zera 5 min antes)


def m1_dia(data, base=100000.0, over=None, seed=None):
    t = pd.date_range(pd.Timestamp(data) + pd.Timedelta(hours=9), periods=N_M1, freq="min")
    o = np.full(N_M1, base)
    if seed is not None:
        o = base + np.cumsum(np.random.default_rng(seed).normal(0, 20, N_M1)).round(-1)
    df = pd.DataFrame(dict(open=o, high=o + 5, low=o - 5, close=o), index=t)
    for i, (a, b, c, d) in (over or {}).items():
        df.iloc[i, :4] = [a, b, c, d]
    df["ultima_continua"] = False
    df.iloc[-1, df.columns.get_loc("ultima_continua")] = True
    df["real_volume"] = 10.0
    return df


def monta(dias):
    m1 = pd.concat(dias).sort_index()
    m15 = m1.resample("15min").agg(dict(open="first", high="max", low="min", close="last", real_volume="sum")).dropna()
    m15["dia"] = m15.index.normalize()
    m15["contrato"] = 1
    return Mercado(m15, m1[["open", "high", "low", "close", "ultima_continua"]], vencimentos=[])


def roda(over, ordem, k_dec=1, extra_cb=None):
    """Dia de teste = 2026-03-10 (com um dia anterior plano). ordem = decisao dada em k_dec; depois 'manter'."""
    mk = monta([m1_dia("2026-03-09"), m1_dia("2026-03-10", over=over)])
    dia = mk.dia("2026-03-10")

    def decidir(pf, k, s):
        if k == k_dec:
            return ordem, {}
        if extra_cb:
            r = extra_cb(k, s)
            if r:
                return r, {}
        return dict(acao="manter"), {}
    return run_dia(mk, dia, decidir)[0]


def compra(**kw):
    d = dict(acao="comprar_limite", preco=99995, stop=99900, alvo=None, contratos=1, validade_velas=2)
    d.update(kw)
    return d


def test_limite_nao_enche_sem_passar_10_pts():
    # decisao na vela 09:15-09:30 (k=1); fill so em velas seguintes (a partir de 09:30). M1 idx 32: low = preco-5 -> nao enche
    s = roda({32: (100000, 100005, 99990, 100000)}, compra())
    assert not s.trades and s.ordens[0]["estado"] == "expirada"


def test_limite_enche_quando_passa_10_pts():
    s = roda({32: (100000, 100005, 99985, 100000)}, compra())
    assert s.ordens[0]["fill"]["preco"] == 99995 and s.ordens[0]["fill"]["t"] == "09:32"
    assert len(s.trades) == 1 and s.trades[0]["motivo"].startswith("fim do pregao")


def test_nao_enche_na_propria_vela_da_decisao():
    # M1 29 (09:29) pertence a vela k=1 (09:15-09:30): fill ali seria look-ahead
    s = roda({29: (100000, 100005, 99900, 100000)}, compra())
    assert s.ordens[0]["fill"] is None or s.ordens[0]["fill"]["t"] != "09:29"


def test_expira_apos_validade():
    s = roda({50: (100000, 100005, 99900, 100000)}, compra(validade_velas=1, stop=99800))
    assert s.ordens[0]["estado"] == "expirada" and not s.trades


def test_stop_no_nivel_e_custo():
    # enche no M1 32, depois M1 40 minima 99895 < stop 99900 -> sai no stop 99900: bruto -95, liq -105, R$ = -105*0,2
    s = roda({32: (100000, 100005, 99985, 99990), 40: (99990, 99995, 99895, 99950)}, compra())
    t = s.trades[0]
    assert t["preco_sai"] == 99900 and t["motivo"] == "stop"
    assert t["pts_bruto"] == -95 and t["pts_liq"] == -105 and abs(t["brl"] - (-105 * 0.2)) < 1e-9


def test_stop_com_gap_sai_na_abertura():
    s = roda({32: (100000, 100005, 99985, 99990), 40: (99800, 99810, 99790, 99800)}, compra())
    t = s.trades[0]
    assert t["preco_sai"] == 99800 and "gap" in t["motivo"]


def test_alvo_enche_so_passando_10_pts():
    ov = {32: (100000, 100005, 99985, 100000), 40: (100000, 100055, 99995, 100000)}  # alvo 100050: precisa high >= 100060
    s = roda(ov, compra(alvo=100050))
    assert s.trades[0]["motivo"].startswith("fim do pregao")
    ov[40] = (100000, 100060, 99995, 100000)
    s = roda(ov, compra(alvo=100050, contratos=2))
    t = s.trades[0]
    assert t["motivo"] == "alvo" and t["preco_sai"] == 100050
    assert t["pts_liq"] == 55 - 10 + 0 - 0 + 0 or t["pts_liq"] == 45  # 100050-99995-10
    assert abs(t["brl"] - 45 * 2 * 0.2) < 1e-9


def test_stop_e_alvo_na_mesma_vela_assume_stop():
    s = roda({32: (100000, 100005, 99985, 100000), 40: (100000, 100100, 99890, 100000)}, compra(alvo=100050))
    assert s.trades[0]["motivo"] == "stop"


def test_stop_no_minuto_do_preenchimento():
    s = roda({32: (100000, 100005, 99890, 100000)}, compra())
    assert s.trades[0]["motivo"] == "stop" and s.trades[0]["t_ent"] == s.trades[0]["t_sai"]


def test_zerar_fim_do_pregao_no_close_do_flat():
    base = {32: (100000, 100005, 99985, 100000), FLAT: (100000, 100010, 99995, 100020)}
    s = roda(base, compra())
    t = s.trades[0]
    assert t["t_sai"] == "18:19" and t["preco_sai"] == 100020 and "fim do pregao" in t["motivo"]
    assert s.encerrada


def test_zerar_acao_sai_na_abertura_da_proxima_vela_m1():
    ov = {32: (100000, 100005, 99985, 100000), 61: (100100, 100110, 100095, 100105)}  # k=4 fecha 10:00 -> M1 60 (10:00)
    s = roda(ov, compra(), extra_cb=lambda k, s: dict(acao="zerar") if (k == 3 and s.pos) else None)
    t = s.trades[0]
    assert "zerar" in t["motivo"] and t["t_sai"] == "10:00" and t["preco_sai"] == 100000


def test_rejeita_compra_acima_do_mercado_e_stop_errado():
    s = roda({}, compra(preco=100100))
    assert s.pend is None and any("mercado" in e["texto"] for e in s.eventos)
    s = roda({}, compra(stop=99999.0 + 100))
    assert s.pend is None and any(e["tipo"] == "rejeitada" for e in s.eventos)


def test_mover_stop_so_a_favor():
    ov = {32: (100000, 100005, 99985, 100000)}
    s = roda(ov, compra(), extra_cb=lambda k, s: dict(acao="mover_stop", novo_stop=99800) if (k == 3 and s.pos) else None)
    assert any(e["tipo"] == "rejeitada" for e in s.eventos)
    s = roda(ov, compra(), extra_cb=lambda k, s: dict(acao="mover_stop", novo_stop=99950) if (k == 3 and s.pos) else None)
    assert s.ordens[0]["stops"][-1]["valor"] == 99950


def test_sem_look_ahead_no_pacote():
    """O pacote da vela k nao muda se TODO o futuro (velas > k hoje e dias seguintes) for trocado por lixo."""
    d1, d2, d3 = m1_dia("2026-03-09", seed=1), m1_dia("2026-03-10", seed=2), m1_dia("2026-03-11", seed=3)
    mk = monta([d1, d2, d3])
    K = 10
    corte = pd.Timestamp("2026-03-10 09:00") + pd.Timedelta(minutes=15 * (K + 1))
    d2b, d3b = d2.copy(), d3.copy()
    fut = d2b.index >= corte
    d2b.loc[fut, ["open", "high", "low", "close"]] = 55555.0
    d3b.loc[:, ["open", "high", "low", "close"]] = 77777.0
    mk2 = monta([d1, d2b, d3b])
    est = dict(pos=None, pend=None, pts=0, brl=0, ntrades=0)
    p1 = __import__("mercado").montar_pacote(mk, mk.dia("2026-03-10"), K, est, [], [])
    p2 = __import__("mercado").montar_pacote(mk2, mk2.dia("2026-03-10"), K, est, [], [])
    assert p1 == p2
    assert "55555" not in p1 and "77777" not in p1
    assert "2026" not in p1 and "03-10" not in p1  # data real nunca aparece
    p3 = __import__("mercado").montar_pacote(mk, mk.dia("2026-03-10"), K + 1, est, [], [])
    assert p3 != p1  # a vela seguinte so aparece no pacote seguinte


def test_motor_nao_usa_pacote_do_futuro_nem_enche_antes_da_decisao():
    # ordem decidida em k=1 nunca preenche em M1 de vela <= 1
    for m in range(0, 30):
        s = roda({m: (100000, 100005, 99000, 100000)}, compra(stop=98000))
        if s.ordens and s.ordens[0]["fill"]:
            assert int(s.ordens[0]["fill"]["t"][3:]) + 60 * (int(s.ordens[0]["fill"]["t"][:2]) - 9) >= 30
