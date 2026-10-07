"""COFRE (2025-04-01 em diante, rodado UMA vez) dos 3 finalistas de sinais LENTOS definidos so' com 2021-10..2025-03.

F1 M15 LWMA144+SMMA144 vela inteira fora; F2 M15 fechamento > LWMA34 +/- 3*ATR14; F3 igual ao F2 em M10.
Stop 300 / alvo 600 fixos, sem trailing, entrada na abertura da barra seguinte. Executa em M1 com o walk validado
de win_duas_pontas_2026_10_01.py. Compara com a base (M5/34) no mesmo periodo e com horarios aleatorios.
Os finalistas vem de scratchpad/agtMedias7/m_finalistas.py (parametros fixos; copiados para ca' sem alteracao).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta\fae6711e-a3c0-4a4e-b240-2198230a12db\scratchpad\agtMedias7")
import win_duas_pontas_2026_10_01 as dp  # noqa: E402
import win_ema8_wma8_sim_m1 as sim  # noqa: E402
from m_finalistas import eventos as ev_final  # noqa: E402

COFRE = pd.Timestamp("2025-04-01")
rng = np.random.default_rng(1)


def main() -> None:
    m1 = sim.ler("WIN@D_M1_*.csv")
    M = dp.indexar(m1)
    pos = {ts: k for k, ts in enumerate(M["idx"])}
    sets = {}
    for nome in ("F1", "F2", "F3"):
        e = ev_final(m1, nome)
        e = e[e.t_entrada >= COFRE]
        sets[nome] = [(pos[t], int(s)) for t, s in zip(e.t_entrada, e.lado)]
    # base M5/34 no mesmo periodo
    m1b, sig5, nova = dp.carregar()
    base = [(i, s) for i, s in dp.eventos(M, m1b, sig5, nova) if M["idx"][i] >= COFRE]
    sets["BASE M5/34"] = base

    # pool de horarios para o controle: aberturas de qualquer M5 nos dias do cofre, por minuto do dia
    por_t: dict[int, list[int]] = {}
    for i, t in enumerate(M["t"]):
        if M["idx"][i] >= COFRE and t % 5 == 0 and 9 * 60 <= t < sim.SEM_ENTRADA:
            por_t.setdefault(int(t), []).append(i)

    pd.set_option("display.width", 250, "display.max_columns", 30)
    linhas, anos = [], []
    for nome, ev in sets.items():
        P = dp.grade_fixa(M, ev, [300], [600])[(300, 600)]
        dr = np.array([s for _, s in ev])
        col = np.where(dr == 1, 0, 1)
        sig = P[np.arange(len(P)), col]
        opp = P[np.arange(len(P)), 1 - col]
        dias = np.array([M["dia"][i] for i, _ in ev], dtype="datetime64[D]").astype(str)
        ic = dp.boot_dia(sig, dias)
        ganhos, perdas = sig[sig > 0], -sig[sig < 0]
        be = perdas.mean() / (ganhos.mean() + perdas.mean()) * 100 if len(ganhos) and len(perdas) else np.nan
        # controle: mesmo numero de eventos, mesmo horario e mesmo lado, em dias aleatorios do cofre
        medias = []
        for _ in range(200):
            cev = [(int(rng.choice(por_t.get(int(M["t"][i]), [i]))), s) for i, s in ev]
            Pc = dp.grade_fixa(M, cev, [300], [600])[(300, 600)]
            medias.append(Pc[np.arange(len(Pc)), np.where(np.array([s for _, s in cev]) == 1, 0, 1)].mean())
        perc = (np.array(medias) < sig.mean()).mean() * 100
        linhas.append({"cfg": nome, "n": len(ev), "R$/op": sig.mean(), "ic_lo": ic[0], "ic_hi": ic[1],
                       "win%": (sig > 0).mean() * 100, "BE%": be, "oposto": opp.mean(), "perc_aleat": perc,
                       "ctrl_media": float(np.mean(medias))})
        ano = pd.Series(sig).groupby(pd.Series(dias).str[:7].map(lambda s: s[:4] + ("S1" if int(s[5:]) <= 6 else "S2"))).agg(["count", "mean"])
        ano.insert(0, "cfg", nome)
        anos.append(ano)
    print("\n== COFRE 2025-04-01..fim, stop 300 / alvo 600 fixo (R$ por operacao, custos incluidos)")
    print(pd.DataFrame(linhas).set_index("cfg").round(2), flush=True)
    print("\n== POR SEMESTRE (n, R$/op do lado do sinal)")
    print(pd.concat(anos).round(2).to_string(), flush=True)


if __name__ == "__main__":
    main()
