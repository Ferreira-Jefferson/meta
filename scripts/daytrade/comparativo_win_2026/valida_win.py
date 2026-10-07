"""Validacao do port_win contra scripts/daytrade/win_replay_ticks.py (WINV26, 2026-08-13..09-30, latencia 0).
Modos do replay antigo: mt5 (M1 do MT5, como ele roda) e dados (M1 do WIN$N, isola so' a execucao)."""
import sys, json
from datetime import date
from pathlib import Path
import numpy as np, pandas as pd
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent))
import dados as D, port_win as P, win_replay_ticks as R

INI, FIM = date(2026, 8, 13), date(2026, 9, 30)
modo = sys.argv[1] if len(sys.argv) > 1 else "dados"
if modo == "dados":
    m = D.m1()
    R.carregar_m1 = lambda ativo, i, f: m[["open", "high", "low", "close"]].astype(float)

def comp(nome, params, port_p):
    r = R.replay(INI, FIM, 0.0, "fixa", params)
    old = pd.DataFrame(r["trades"])
    new = pd.DataFrame(P.rodar(nome, port_p, INI, FIM, salvar=False, verbose=False))
    old["te"], old["tx"] = pd.to_datetime(old.te), pd.to_datetime(old.tx)
    new["entrada"], new["saida"] = pd.to_datetime(new.entrada, format='mixed'), pd.to_datetime(new.saida, format='mixed')
    print(f"\n##### {nome} modo={modo}: antigo {len(old)} trades R$ {old.rs.sum():.2f} | port {len(new)} trades R$ {new.rs.sum():.2f}")
    # chave: entrada (segundo) + lado
    old["k"] = old.te.dt.floor("s").astype(str) + "|" + old.d.astype(str)
    new["k"] = new.entrada.dt.floor("s").astype(str) + "|" + new.lado.astype(str)
    j = old.merge(new, on="k", how="outer", suffixes=("_o", "_n"), indicator=True)
    both = j[j._merge == "both"]
    ig = (both.tx.dt.floor("s") == both.saida.dt.floor("s"))
    print(f"entradas em comum {len(both)} | so' antigo {(j._merge=='left_only').sum()} | so' port {(j._merge=='right_only').sum()}")
    print(f"das comuns: saida no mesmo segundo {int(ig.sum())}; preco entrada igual {int((both.pe == both.preco_entrada).sum())}; preco saida igual {int((both.px == both.preco_saida).sum())}; motivo igual {int((both.mot == both.motivo).sum())}")
    cols = ["k", "tx", "saida", "mot", "motivo", "px", "preco_saida", "rs_o", "rs_n"]
    dif = both[~ig | (both.px != both.preco_saida)]
    print("--- comuns com saida diferente:"); print(dif[cols].to_string() if len(dif) else "nenhuma")
    print("--- so' antigo:"); print(j[j._merge == "left_only"][["k", "tx", "mot", "pe", "px", "rs_o"]].to_string())
    print("--- so' port:"); print(j[j._merge == "right_only"][["k", "saida", "motivo", "preco_entrada", "preco_saida", "rs_n"]].to_string())

comp("Win", dict(be_minutos=0), P.PARAMS)
comp("Win_c1", dict(be_minutos=15, be_colchao_pts=7.0), P.PARAMS_C1)
