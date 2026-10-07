"""Analise da grade IS: estatisticas por celula/premissa, por ano, censura pelo caixa real (caminhada R$250),
probabilidade de travar, capital exigido; e a aplicacao da regra de escolha do PRE_REGISTRO (secao 7 + adendo)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import comum as c  # noqa: E402

PISO = 100.0


def trades_de(r):
    out = []
    for t in r["trades"]:
        out.append(SimpleNamespace(entry_ts=pd.Timestamp(t["entry_ts"]), pnl_brl=t["pnl"], reason=t["reason"],
                                   side=t["side"], entry_price=t["entry_price"], exit_price=t["exit_price"]))
    return out


def chave(p):
    return (p["desloc_min_atr"], p["stop_atr"], p["alvo_atr"])


def main(arq: str = "is_grade.json") -> None:
    rs = json.loads((HERE / "saidas" / arq).read_text(encoding="utf-8"))
    linhas = []
    for r in rs:
        tr = trades_de(r)
        st = c.estatisticas(tr)
        cam = c.caminhada_caixa(tr, c.CAPITAL["WIN@"], PISO)
        anos = c.por_ano(tr)
        linhas.append(dict(
            cel=c.nome_celula(r["params"]), key=c.nome_celula(r["params"]), prem=r["premissa"], n=st["n"],
            sinais=r["n_sinais"], liquido=st["liquido"], media=st["media"], ic_lo=st["ic_lo"], ic_hi=st["ic_hi"],
            win=st["win"], be=st["be"], maxdd=None,
            a2022=anos.get(2022, (0, 0.0))[1], a2023=anos.get(2023, (0, 0.0))[1], a2024=anos.get(2024, (0, 0.0))[1],
            a2021=anos.get(2021, (0, 0.0))[1],
            exec250=cam["exec"], perdidos250=cam["perdidos"], caixa_min250=cam["caixa_min"], caixa_fin250=cam["caixa_final"],
            trava=c.prob_trava(tr, c.CAPITAL["WIN@"], PISO, n=3000), cap_exigido=c.capital_para_sobreviver(tr, PISO),
            stop_medio=np.mean([abs(t.entry_price - t.exit_price) * 0.2 for t in tr if t.reason == "STOP"]) if any(t.reason == "STOP" for t in tr) else np.nan,
            n_stop=sum(t.reason == "STOP" for t in tr), n_alvo=sum(t.reason == "TARGET" for t in tr),
            n_flat=sum(t.reason == "FORCED_FLATTEN" for t in tr)))
    df = pd.DataFrame(linhas)
    df.to_csv(HERE / f"analise_{arq.replace('.json', '')}.csv", index=False, sep=";", decimal=",")
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    cols = ["cel", "prem", "n", "sinais", "liquido", "media", "ic_lo", "ic_hi", "win", "be", "a2022", "a2023", "a2024"]
    print(df[df.prem == "P2"][cols].round(1).to_string(index=False))
    print("\nCENSURA caixa real R$250 (caminhada), P2")
    print(df[df.prem == "P2"][["cel", "n", "exec250", "perdidos250", "caixa_min250", "caixa_fin250", "trava", "cap_exigido", "stop_medio", "n_stop", "n_alvo", "n_flat"]].round(2).to_string(index=False))
    print("\nTodas as premissas: liquido")
    print(df.pivot(index="cel", columns="prem", values="liquido").round(1).to_string())
    print(df.pivot(index="cel", columns="prem", values="n").to_string())

    # --- regra de escolha ---
    KP = {c.nome_celula(p): p for p in c.celulas()}
    p2 = df[df.prem == "P2"].set_index("key"); p0 = df[df.prem == "P0"].set_index("key")
    elig = {}
    for k in p2.index:
        a = p0.loc[k, "liquido"] > 0 and p2.loc[k, "liquido"] > 0
        b = p2.loc[k, "n"] >= 60
        viz = [c.nome_celula(v) for v in c.vizinhos(KP[k])]
        pos = sum(p2.loc[v, "liquido"] > 0 for v in viz)
        d = pos / len(viz) >= 2 / 3
        cens_ok = (p2.loc[k, "perdidos250"] <= 0.05 * p2.loc[k, "sinais"]) and p2.loc[k, "caixa_min250"] >= PISO
        elig[k] = dict(a=a, b=b, d=d, viz_pos=pos, viz_tot=len(viz), edge=a and b and d, completa=a and b and d and cens_ok)
    e = pd.DataFrame(elig).T
    e["cel"] = list(e.index)
    print("\nELEGIBILIDADE\n", e[["cel", "a", "b", "d", "viz_pos", "viz_tot", "edge", "completa"]].to_string(index=False))


if __name__ == "__main__":
    main(*(sys.argv[1:]))
