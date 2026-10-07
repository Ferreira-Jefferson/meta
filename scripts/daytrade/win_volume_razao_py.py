"""Replica em Python do indicador mt5/WinVolumeRazao.mq5 + utilitarios para estuda-lo.

razao = volume da vela / MEDIANA do volume da MESMA HORA nas ultimas `dias` ocorrencias
anteriores do mesmo grupo (padrao: mesmo DIA DA SEMANA). Ocorrencia sem vela ou com volume 0 e'
pulada (equivale a "voltar semana a semana ate achar dias validos"). Estrito: se nao ha `dias`
ocorrencias antes da vela, a razao e' NaN (igual ao indicador). Nunca olha o futuro: so' usa
ocorrencias ANTERIORES (shift 1).

modo: "semana" (hora + dia da semana, o do indicador), "hora" (so' a hora, qualquer dia) -- serve
para medir quanto o dia da semana agrega. agg: "mediana" (indicador) ou "media".
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_ema8_wma8_sim_m1 as sim  # noqa: E402

ROOT = sim.ROOT
CACHE = ROOT / "data" / "cache_win_volume"


def ler_m5_volume(tf: str = "M5") -> pd.DataFrame:
    """Barras do WIN@D no tempo grafico tf (M1/M5) com colunas open, high, low, close, vol (volume real)."""
    arq = sorted((ROOT / "data" / "wdo-mt5").glob(f"WIN@D_{tf}_*.csv"))[-1]
    d = pd.read_csv(arq, sep="\t")
    d.index = pd.to_datetime(d["<DATE>"] + " " + d["<TIME>"], format="%Y.%m.%d %H:%M:%S")
    d = d.rename(columns={"<OPEN>": "open", "<HIGH>": "high", "<LOW>": "low", "<CLOSE>": "close", "<VOL>": "vol"})
    return d[["open", "high", "low", "close", "vol"]].astype(float)


def razao_volume(d: pd.DataFrame, dias: int = 2, modo: str = "semana", agg: str = "mediana") -> pd.Series:
    hora = d.index.hour * 60 + d.index.minute
    chave = (d.index.dayofweek * 10000 + hora) if modo == "semana" else hora
    v = d["vol"].where(d["vol"] > 0).dropna()  # volume 0 nao conta como ocorrencia
    k = pd.Series(np.asarray(chave)[d["vol"].notna().to_numpy() & (d["vol"] > 0).to_numpy()], index=v.index)
    roll = v.groupby(k).transform(
        lambda x: getattr(x.shift(1).rolling(dias, min_periods=dias), "median" if agg == "mediana" else "mean")())
    base = roll.reindex(d.index)
    return (d["vol"] / base).where(base > 0).rename("razao")


def trades_com_razao(mes: str, stop: float, alvo: float, dias: int = 2, modo: str = "semana",
                     agg: str = "mediana") -> pd.DataFrame:
    """Operacoes da estrategia WIN (vela limpa vs roxa + verde do lado oposto, execucao em M1) do mes,
    com a razao de volume da VELA DO SINAL (a M5 que fechou antes da entrada)."""
    m1 = sim.preparar(mes, limpa=True, so_roxa=True)
    tr = sim.simular(m1, stop, alvo)
    d = ler_m5_volume()
    r = razao_volume(d, dias, modo, agg)
    tr["t_sinal"] = tr["t_entrada"] - pd.Timedelta(minutes=5)
    tr["razao"] = r.reindex(tr["t_sinal"]).to_numpy()
    return tr


if __name__ == "__main__":
    # conferencia com o calculo manual: quartas 23/09 e 16/09 -> 1.01, 0.79, 0.96, 2.03
    d = ler_m5_volume()
    r = razao_volume(d, 2, "semana")
    for h in ["2026-09-30 09:00", "2026-09-30 11:50", "2026-09-30 13:00", "2026-09-30 17:00"]:
        print(h, round(float(r[pd.Timestamp(h)]), 2))
