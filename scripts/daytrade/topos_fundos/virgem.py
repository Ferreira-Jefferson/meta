"""Confirmacao em periodo NUNCA usado: WIN$N 08/10/2021 a 31/12/2021 (o MT5 da corretora so tem dados a partir de 08/10/2021).
Mesmo pipeline das outras janelas: base sem leiloes -> escada M15 -> filtros v1..v3 -> sinais bons (v4) -> stop v4.1
(aperto na MME38 do M15 com colchao 0,2 ATR). Regras congeladas antes de abrir este periodo (2026-10-08).
"""
import os
import sys
import datetime as dt
import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from market_data_intraday.win_sem_leiloes import carrega_win_m1_sem_leiloes  # noqa: E402

import confirma, motor, hipoteses, mtf  # noqa: E402

BASE = "scripts/daytrade/topos_fundos/"
OUT = BASE + "res_virgem/"
SRC = "data/win_sem_leiloes/m1_WIN$N_2021_virgem.parquet"


def baixar():
    import MetaTrader5 as mt5
    mt5.initialize()
    r = mt5.copy_rates_range("WIN$N", mt5.TIMEFRAME_M1, dt.datetime(2021, 10, 1), dt.datetime(2021, 12, 1))
    mt5.shutdown()
    d = pd.DataFrame(r); d.index = pd.to_datetime(d.time, unit="s"); d.index.name = "time"
    d = d[["open", "high", "low", "close", "tick_volume", "real_volume"]].astype(float)
    dez = pd.read_parquet("data/comparativo_win_2026/m1_WIN$N_2022_2025.parquet")
    dez = dez[(dez.index >= "2021-12-01") & (dez.index < "2022-01-01")][["open", "high", "low", "close", "tick_volume", "real_volume"]]
    print("MT5 out-nov/21:", d.index.min(), d.index.max(), len(d), "| dez/21 da base:", len(dez), flush=True)
    r = carrega_win_m1_sem_leiloes([d, dez.astype(float)], inicio="2021-10-08", fim="2021-12-31")
    r.barras.to_parquet(SRC)
    print("base sem leilões:", r.barras.index.min(), r.barras.index.max(), len(r.barras), "pregões", r.barras.index.normalize().nunique(), flush=True)


def pipeline():
    os.makedirs(OUT, exist_ok=True)
    confirma.PER["virgem"] = dict(src=SRC, ini="2021-10-01", fim="2022-01-01", out=OUT)
    motor.SRC, motor.INI, motor.FIM, motor.OUT = SRC, "2021-10-01", "2022-01-01", OUT
    hipoteses.R = OUT
    motor.unidade("M15", "dia", 1.5)
    f = hipoteses.features("M15", "dia", 1.5, min_est=0)
    ev = pd.read_pickle(OUT + "ev_M15_dia_K1.5.pkl")
    for c in ("res", "est", "R", "r2", "r3", "mfe"): f[c] = ev.loc[f.idx, c].values
    f.to_pickle(OUT + "feat0_M15_dia_K1.5.pkl")
    # mtf.montar le barras_M5_dia (nao usado na v4, mas exigido): gera M5 tambem
    motor.unidade("M5", "dia", 1.5)
    t = mtf.montar("virgem")
    t.to_pickle(BASE + "res_conf/mtf_virgem.pkl")  # prob.montar procura em res_conf/ fora da pesquisa
    print("sinais da escada com estado multi-TF:", len(t), flush=True)


def avaliar():
    import prob as pb, stops as st, stops2 as s2
    confirma.PER["virgem"] = dict(src=SRC, ini="2021-10-01", fim="2022-01-01", out=OUT)
    linhas = []
    for per in ("pesquisa", "reserva", "virgem"):
        b, f, c = pb.montar(per)
        base = pb.sim(f, c)
        bom = f.bom.to_numpy()[base.row]
        fb, dias = st.preparar(per)
        b15 = pd.read_pickle(confirma.PER[per]["out"] + "barras_M15_dia.pkl")
        N = b15.close.ewm(span=38, adjust=False).mean().to_numpy()[fb.pos.to_numpy()]
        g = fb.copy(); arr = s2.stop_ini(fb, dias, N, "aperto", 0.2); g["stop"] = [arr[i] for i in g.index]
        V = {"v3 (todas, 1 contrato)": base.pts.to_numpy(),
             "v4 (só bons, 2 contratos)": st.simular(fb, dias, {}).pts.to_numpy(),
             "v4.1 (v4 + aperto MME38 +0,2)": st.simular(g, dias, {}).pts.to_numpy()}
        for k, x in V.items():
            eq = np.cumsum(x); dd = (np.maximum.accumulate(eq) - eq).max() if len(x) else 0
            linhas.append(dict(periodo=per, versao=k, ops=len(x), total=x.sum(), pts_op=x.mean() if len(x) else np.nan,
                               acerto=(x > 0).mean() if len(x) else np.nan, dd=dd, total_R=x.sum() * 0.2))
        print(per, "bons:", int(bom.sum()), "de", len(bom), flush=True)
    t = pd.DataFrame(linhas); t.to_pickle(OUT + "avaliacao.pkl")
    pd.set_option("display.width", 200); print(t.round(1).to_string(index=False))


if __name__ == "__main__":
    etapa = sys.argv[1]
    {"baixar": baixar, "pipeline": pipeline, "avaliar": avaliar}[etapa]()
