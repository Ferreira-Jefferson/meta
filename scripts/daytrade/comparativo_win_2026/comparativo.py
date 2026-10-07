"""Junta os resultados dos ports (resultados/*.csv) num comparativo WIN 2026 com capital inicial de R$1.000.

Capital: cada estrategia comeca 2026 com R$1.000 e nao recebe aporte. O saldo anda operacao a operacao (na ordem
de saida). Se o saldo chega a zero ou menos, a estrategia QUEBROU naquela operacao: ela fica registrada como
perdedora, com a data, e nao opera mais pelo resto do ano.

Dois cenarios: "testador" (sem custo, como o Testador do MT5 sem comissao) e "custo" (R$2 por operacao).

Uso: python comparativo.py  ->  comparativo_win_2026.html (+ comparativo_win_2026.json)
"""
import json
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
CAPITAL = 1000.0
CUSTO_OP = 2.0
MESES = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def resumo(t: pd.DataFrame, custo: float) -> dict:
    saldo, pico, dd, quebra, usados = CAPITAL, CAPITAL, 0.0, None, []
    curva = [(f"{MESES[0]}-01", CAPITAL)]
    for r in t.itertuples():
        rs = r.rs - custo * r.qtd
        saldo += rs
        usados.append((r.saida, rs))
        pico = max(pico, saldo)
        dd = max(dd, pico - saldo)
        curva.append((r.saida[:10], round(saldo, 2)))
        if saldo <= 0:
            quebra = dict(data=r.saida[:16], saldo=round(saldo, 2))
            break
    u = pd.DataFrame(usados, columns=["saida", "rs"])
    meses = {}
    for m in MESES:
        g = u[u.saida.str[:7] == m] if len(u) else u
        meses[m] = None if (quebra and m > quebra["data"][:7]) else dict(rs=round(float(g.rs.sum()), 2), n=int(len(g)))
    ganhos, perdas = u.rs[u.rs > 0].sum(), -u.rs[u.rs < 0].sum()
    # curva diaria (ultimo saldo de cada dia) para o grafico
    cd = pd.DataFrame(curva, columns=["d", "s"]).groupby("d").s.last()
    return dict(total=round(float(u.rs.sum()), 2), final=round(saldo, 2), n=int(len(u)),
                acerto=round(100 * float((u.rs > 0).mean()), 1) if len(u) else None,
                pf=round(float(ganhos / perdas), 2) if perdas else None, dd=round(dd, 2),
                meses_pos=sum(1 for v in meses.values() if v and v["n"] and v["rs"] > 0),
                meses_op=sum(1 for v in meses.values() if v and v["n"]),
                quebra=quebra, meses=meses, curva=[[d, s] for d, s in cd.items()])


def main():
    notas = json.loads((AQUI / "notas.json").read_text(encoding="utf-8")) if (AQUI / "notas.json").exists() else {}
    out = dict(capital=CAPITAL, custo_op=CUSTO_OP, meses=MESES, estrategias=[])
    for arq in sorted((AQUI / "resultados").glob("*.csv")):
        t = pd.read_csv(arq).sort_values("saida", kind="stable")
        nome = arq.stem
        out["estrategias"].append(dict(nome=nome, nota=notas.get(nome, {}),
                                       testador=resumo(t, 0.0), custo=resumo(t, CUSTO_OP)))
        r = out["estrategias"][-1]["testador"]
        print(f"{nome:28s} n={r['n']:4d} total={r['total']:10.2f} final={r['final']:10.2f} quebra={r['quebra']}", flush=True)
    rk = AQUI / "combinacoes" / "ranking.json"
    out["ranking"] = json.loads(rk.read_text(encoding="utf-8")) if rk.exists() else None
    (AQUI / "comparativo_win_2026.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    html = (AQUI / "modelo.html").read_text(encoding="utf-8").replace("/*__DADOS__*/null", json.dumps(out, ensure_ascii=False))
    (AQUI / "comparativo_win_2026.html").write_text(html, encoding="utf-8")
    print("ok ->", AQUI / "comparativo_win_2026.html")


if __name__ == "__main__":
    main()
