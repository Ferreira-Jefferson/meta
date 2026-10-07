"""Z1: numero esperado no Testador para Win v2.05 e Win_c1 v2.06 (H1, filtro H3).
WINV26, 13/08/2026 -> 30/09/2026, sem custo, R$1.000, 1 contrato.

Duas leituras do mesmo port padrao (port_win_padrao -> port_win_tf, tf 60 / sup 180):
  A) dados do comparativo: M1 e ticks do WIN$N (igual ao WINV26 desde 13/08, mas o historico de aquecimento antes de
     13/08 e' o do contrato anterior);
  B) WINV26 puro: M1 do WINV26 tirado do MT5 (o historico que o Testador carrega para aquecer as medias H1/H3) e os
     ticks reais do WINV26 em data/cache_win_ticks/WINV26 (so' ticks com last > 0; execucao no last, como no port).
Uso: python z1_testador_esperado.py
"""
import sys, types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np, pandas as pd

AQUI = Path(__file__).resolve().parent
BASE = AQUI.parents[1]                      # comparativo_win_2026/
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / "combinacoes" / "y_tempos" / "win"))
import dados as D

INI, FIM = date(2026, 8, 13), date(2026, 9, 30)
CACHE = ROOT / "data" / "cache_win_ticks" / "WINV26"


def m1_winv26() -> pd.DataFrame:
    arq = AQUI / "m1_WINV26.parquet"
    if arq.exists():
        return pd.read_parquet(arq)
    import MetaTrader5 as mt5
    assert mt5.initialize(), "abra o terminal do MT5"
    mt5.symbol_select("WINV26", True)
    out, d0 = [], date(2026, 1, 1)
    while d0 <= date(2026, 10, 2):
        d1 = d0 + timedelta(days=5)
        r = mt5.copy_rates_range("WINV26", mt5.TIMEFRAME_M1, datetime(d0.year, d0.month, d0.day, tzinfo=timezone.utc),
                                 datetime(d1.year, d1.month, d1.day, tzinfo=timezone.utc))
        if r is not None and len(r):
            out.append(pd.DataFrame(r))
        d0 = d1
    m = pd.concat(out).drop_duplicates("time")
    m.index = pd.to_datetime(m["time"], unit="s")
    m = m.sort_index()[["open", "high", "low", "close", "tick_volume", "real_volume"]]
    m.to_parquet(arq)
    return m


def shim_winv26():
    m = m1_winv26()
    S = types.ModuleType("dados")
    for k in ("TICK", "RS_PONTO", "COLUNAS", "trade", "salvar", "ts", "ms"):
        setattr(S, k, getattr(D, k))
    S.m1 = lambda: m
    S.dias = lambda: sorted(set(m.index.date))

    def ticks(dia):
        x = pd.read_pickle(CACHE / f"{dia}.pkl")
        x = x[x["last"] > 0]
        return x.time_msc.to_numpy(np.int64), x["last"].to_numpy(float), x.volume.to_numpy(np.int64), True
    S.ticks = ticks
    return S


def roda(rotulo):
    import port_win_padrao as PP
    res = {}
    for nome, p in PP.ROBOS:
        out = PP.P.rodar(nome, p, INI, FIM, salvar=False, verbose=False)
        df = pd.DataFrame(out, columns=D.COLUNAS)
        df.to_csv(AQUI / f"z1_{nome}_{rotulo}.csv", index=False)
        res[nome] = df
        print(f"\n== {rotulo} {nome}: {len(df)} ops, liquido R$ {df.rs.sum():.2f}", flush=True)
        print(df[["entrada", "lado", "saida", "preco_entrada", "preco_saida", "motivo", "rs"]].to_string(index=False), flush=True)
    return res


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "A"
    if modo == "B":
        sys.modules["dados"] = shim_winv26()
        D = sys.modules["dados"]
    roda("WIN$N" if modo == "A" else "WINV26")
