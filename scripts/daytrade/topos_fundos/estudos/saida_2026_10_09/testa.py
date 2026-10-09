"""Estudo de saída/trailing da v4.1 (2026-10-09), etapa 2: testa as hipóteses de hipoteses.py.

Critério, fixado antes de rodar:
  1. TESTE = pregões do IS fora da descoberta (338). Passa se melhora o total E o total/DD contra a v4.1.
  2. Vizinhos: a hipótese só vale se a maioria dos vizinhos também melhorar o total no TESTE (platô, não pico).
  3. OOS: só quem passou 1 e 2, uma vez. Fica se melhorar o total E o total/DD também no OOS.
Uso: python testa.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import estrategia  # noqa: E402
import operacao  # noqa: E402
import stop  # noqa: E402
import dossie  # noqa: E402
import hipoteses as H  # noqa: E402

BASE = dict(inicial=stop.inicial_v41, mover=stop.estrutura)


def rodar(b, s, dias, v):
    v = {**BASE, **v}
    if "pular" in v: s = s[~v["pular"](b, s)]
    return operacao.operar(s, dias, v["inicial"], v["mover"], v.get("alvo"), v.get("contratos_alvo", operacao.CONTRATOS))


def descoberta(tr_base):
    datas = np.array(sorted(tr_base.dia.unique()))
    return set(np.random.default_rng(dossie.SEMENTE).choice(datas, dossie.N_DESCOBERTA, replace=False))


def linha(tr, prefixo):
    return {f"{prefixo}_{k}": v for k, v in operacao.resumo(tr).items() if k in ("ops", "total", "dd", "total_dd", "acerto")}


def main():
    b, dias, s = estrategia.preparar("IS", H.colunas)
    base = rodar(b, s, dias, {})
    desc = descoberta(base)
    teste = lambda tr: tr[~tr.dia.isin(desc)]
    rb = operacao.resumo(teste(base))
    print(f"BASE v4.1 TESTE: {rb['ops']} ops, total {rb['total']:+.0f}, DD {rb['dd']:.0f}, total/DD {rb['total_dd']:.2f}", flush=True)
    rows = []
    for hip, variantes in H.VARIANTES.items():
        for nome, v in variantes.items():
            tr = rodar(b, s, dias, v)
            r = dict(hip=hip, var=nome, **linha(teste(tr), "T"), **linha(tr[tr.dia.isin(desc)], "D"))
            r["dT_total"] = r["T_total"] - rb["total"]; r["dT_tdd"] = r["T_total_dd"] - rb["total_dd"]
            r["melhora"] = r["dT_total"] > 0 and r["dT_tdd"] > 0
            rows.append(r)
            print(f"{hip:4s} {nome:60s} TESTE {r['T_total']:+8.0f} ({r['dT_total']:+6.0f}) DD {r['T_dd']:6.0f} "
                  f"t/DD {r['T_total_dd']:5.2f} ({r['dT_tdd']:+5.2f}) | descob. {r['D_total']:+6.0f}{'  MELHORA' if r['melhora'] else ''}", flush=True)
    t = pd.DataFrame(rows)
    # platô: a variante central (1ª de cada hipótese) passa se ela melhora e a maioria dos vizinhos melhora o total
    passa = []
    for hip, g in t.groupby("hip", sort=False):
        c = g.iloc[0]; viz = g.iloc[1:]
        ok = bool(c.melhora) and (len(viz) == 0 or (viz.dT_total > 0).mean() > 0.5)
        print(f"{hip}: central {'melhora' if c.melhora else 'não melhora'}; vizinhos com total maior {int((viz.dT_total > 0).sum())}/{len(viz)} -> {'PASSA' if ok else 'não passa'}", flush=True)
        if ok: passa.append((hip, c["var"]))
    if not passa:
        print("Nenhuma hipótese passou no TESTE: OOS não é aberto."); t.to_csv(Path(__file__).with_name("resultado_is.csv"), index=False); return
    bo, diaso, so = estrategia.preparar("OOS", H.colunas)
    ro = operacao.resumo(rodar(bo, so, diaso, {}))
    print(f"\nOOS BASE: {ro['ops']} ops, total {ro['total']:+.0f}, DD {ro['dd']:.0f}, total/DD {ro['total_dd']:.2f}", flush=True)
    for hip, nome in passa:
        r = operacao.resumo(rodar(bo, so, diaso, H.VARIANTES[hip][nome]))
        ok = r["total"] > ro["total"] and r["total_dd"] > ro["total_dd"]
        print(f"OOS {hip} {nome}: total {r['total']:+.0f} ({r['total'] - ro['total']:+.0f}) DD {r['dd']:.0f} t/DD {r['total_dd']:.2f} "
              f"{'-> PASSA' if ok else '-> falha'}", flush=True)
    t.to_csv(Path(__file__).with_name("resultado_is.csv"), index=False)


if __name__ == "__main__":
    main()
