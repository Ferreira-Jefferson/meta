"""Grava em data/win_sem_leiloes/ as bases M1 e M5 do WIN$N SEM os leiloes (carrega_win_m1_sem_leiloes).

Rode DEPOIS de scripts/daytrade/win_fases_pregao_6m_2026_10_06.py (o carregador le a tabela de fases).
Saidas por base: parquet e TSV no layout do MT5 (<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>)
+ PROXY, FLAG_LEILAO, ULTIMA_CONTINUA, HL_APROX; e dias_<base>.csv. Nao grava WIN@/WIN@D (preco ajustado).
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from market_data_intraday.win_sem_leiloes import carrega_win_m1_sem_leiloes  # noqa: E402

SAIDA = ROOT / "data" / "win_sem_leiloes"
BASES = {"WIN$N": "m1_WIN$N.parquet", "WIN$N_2022_2025": "m1_WIN$N_2022_2025.parquet"}


def tsv(b: pd.DataFrame, caminho: Path) -> None:
    out = pd.DataFrame({
        "<DATE>": b.index.strftime("%Y.%m.%d"), "<TIME>": b.index.strftime("%H:%M:%S"),
        "<OPEN>": b.open.to_numpy(), "<HIGH>": b.high.to_numpy(), "<LOW>": b.low.to_numpy(),
        "<CLOSE>": b.close.to_numpy(), "<TICKVOL>": b.tick_volume.round().astype("int64").to_numpy(),
        "<VOL>": b.real_volume.round().astype("int64").to_numpy(), "<SPREAD>": 0,
        "PROXY": b.proxy.astype(int).to_numpy(), "FLAG_LEILAO": b.flag_leilao.astype(int).to_numpy(),
        "ULTIMA_CONTINUA": b.ultima_continua.astype(int).to_numpy(), "HL_APROX": b.hl_aprox.astype(int).to_numpy(),
    })
    out.to_csv(caminho, sep="\t", index=False)


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    for nome, arq in BASES.items():
        for tf in ("M1", "M5"):
            r = carrega_win_m1_sem_leiloes(arq, tf=tf)
            pref = tf.lower()
            r.barras.to_parquet(SAIDA / f"{pref}_{nome}.parquet")
            tsv(r.barras, SAIDA / f"{pref}_{nome}.csv")
            print(nome, tf, len(r.barras), r.barras.index[0], r.barras.index[-1], flush=True)
            if tf == "M1":
                d = r.dias.copy()
                d.to_csv(SAIDA / f"dias_{nome}.csv", sep=";", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
