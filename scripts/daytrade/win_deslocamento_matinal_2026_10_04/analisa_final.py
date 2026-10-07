"""Estatisticas finais (OOS WIN, IS/OOS WDO): IC, win% vs breakeven empirico, por ano, censura de caixa, saidas."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comum as c  # noqa: E402


def main() -> None:
    rs = json.loads((HERE / "saidas" / "final.json").read_text(encoding="utf-8"))
    linhas = []
    for r in sorted(rs, key=lambda x: (x["simbolo"], x["janela_ini"], x["premissa"])):
        tr = [SimpleNamespace(entry_ts=pd.Timestamp(t["entry_ts"]), pnl_brl=t["pnl"], reason=t["reason"], exit_ts=pd.Timestamp(t["exit_ts"]),
                              entry_price=t["entry_price"], exit_price=t["exit_price"]) for t in r["trades"]]
        s = r["simbolo"]
        st = c.estatisticas(tr)
        piso = c.economics_for(s).margin_per_contract_brl
        cam = c.caminhada_caixa(tr, c.CAPITAL[s], piso)
        anos = c.por_ano(tr)
        ct = Counter(t.reason for t in tr)
        linhas.append(dict(
            simbolo=s, janela="IS" if r["janela_ini"].startswith("2021") else "OOS", prem=r["premissa"],
            sinais=r["n_sinais"], n=st["n"], liquido=st["liquido"], media=st["media"], ic_lo=st["ic_lo"], ic_hi=st["ic_hi"],
            win=st["win"], be=st["be"],
            por_ano="; ".join(f"{a}: {n}tr {v:+.0f}" for a, (n, v) in anos.items()),
            exec_cap=cam["exec"], perdidos=cam["perdidos"], caixa_min=cam["caixa_min"],
            trava=c.prob_trava(tr, c.CAPITAL[s], piso, n=3000), cap_exigido=c.capital_para_sobreviver(tr, piso),
            stops=ct["STOP"], flat=ct["FORCED_FLATTEN"], alvo=ct["TARGET"],
            ult_saida=str(max(t.exit_ts.time() for t in tr)) if tr else ""))
    df = pd.DataFrame(linhas)
    df.to_csv(HERE / "analise_final.csv", index=False, sep=";", decimal=",")
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 90)
    print(df[["simbolo", "janela", "prem", "sinais", "n", "liquido", "media", "ic_lo", "ic_hi", "win", "be"]].round(1).to_string(index=False))
    print()
    print(df[["simbolo", "janela", "prem", "por_ano"]].to_string(index=False))
    print()
    print(df[["simbolo", "janela", "prem", "exec_cap", "perdidos", "caixa_min", "trava", "cap_exigido", "stops", "flat", "alvo", "ult_saida"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
