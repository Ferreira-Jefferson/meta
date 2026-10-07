"""Ranking pelo critério do dono (2026-10-06): uma estratégia nova é CANDIDATA se, com custo, rende mais que a
PIOR das 6 originais no mesmo período (2026-01-02 → 2026-10-05). Depois todas são tabeladas com os mesmos indicadores.

Fontes:
  - originais: ../resultados/*.csv
  - variantes das frentes: <frente>/trades/*.csv, separadas pela coluna `estrategia` (cada robô vira uma linha)
  - estratégias novas autônomas: A2 (gatilho de consenso) e RDT (n_nova/r1_RDT_2026.csv, se já existir)
Ficam de fora: c_portfolio (são somas de vários robôs, não uma estratégia) e os arquivos *_vetadas.

Indicadores (capital R$1.000 corrido, 1 contrato, custo R$2 por operação):
  líquido c/ e s/ custo, operações, acerto, payoff (ganho médio / perda média), fator de lucro, maior queda do saldo,
  fator de recuperação (líquido c/ custo / maior queda), meses positivos, pior mês, quebra (data).

Candidata: estrategia NOVA com liquido c/ custo > piso; VARIANTE com liquido > piso E acima do proprio original.

Uso: python ranking.py  ->  ranking.csv + ranking.json (lido por ../comparativo.py)
"""
import json
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
CAPITAL, CUSTO = 1000.0, 2.0
MESES = [f"2026-{m:02d}" for m in range(1, 11)]
FRENTES = {"a_consenso": "A consenso", "b_nota": "B nota", "d_regime_1030": "D regime 10:30",
           "e_saida_virada": "E saída na virada", "f_veto": "F veto"}
NOVAS = {"ConsensoGatilho", "RDT"}
EXCLUIDAS = {"WdoRetangulo"}   # removido pelo dono em 2026-10-06 (do comparativo e do MT5)


def metricas(t: pd.DataFrame) -> dict:
    t = t.assign(qtd=t["qtd"] if "qtd" in t else 1.0).sort_values("saida", kind="stable")
    saldo, pico, dd, quebra, rs_l, sai = CAPITAL, CAPITAL, 0.0, None, [], []
    for r in t.itertuples():
        v = r.rs - CUSTO * r.qtd
        saldo += v; rs_l.append(v); sai.append(r.saida)
        pico = max(pico, saldo); dd = max(dd, pico - saldo)
        if saldo <= 0:
            quebra = r.saida[:10]; break
    u = pd.Series(rs_l, dtype=float)
    meses = pd.Series(rs_l, index=[s[:7] for s in sai]).groupby(level=0).sum() if rs_l else pd.Series(dtype=float)
    g, p = u[u > 0], -u[u < 0]
    liq = float(u.sum())
    return dict(ops=int(len(u)), liq=round(liq, 2), liq_sem=round(float(t.rs.iloc[:len(u)].sum()), 2),
                acerto=round(100 * float((u > 0).mean()), 1) if len(u) else None,
                payoff=round(float(g.mean() / p.mean()), 2) if len(g) and len(p) else None,
                pf=round(float(g.sum() / p.sum()), 2) if len(p) else None, dd=round(dd, 2),
                fr=round(liq / dd, 2) if dd else None,
                meses_pos=int((meses > 0).sum()), meses_op=int(len(meses)),
                pior_mes=round(float(meses.min()), 2) if len(meses) else None, quebra=quebra,
                mensal={m: round(float(meses.get(m, 0.0)), 2) for m in MESES})


def main():
    linhas = []
    for arq in sorted((RAIZ / "resultados").glob("*.csv")):
        t = pd.read_csv(arq)
        linhas.append(dict(nome=arq.stem, tipo="original", robo=arq.stem, origem="resultados", **metricas(t)))
    for pasta, rot in FRENTES.items():
        for arq in sorted((AQUI / pasta / "trades").glob("*.csv")):
            if arq.stem.endswith("_vetadas"):
                continue
            t = pd.read_csv(arq)
            for est, g in t.groupby("estrategia"):
                if est in EXCLUIDAS:
                    continue
                tipo = "nova" if est in NOVAS else "variante"
                nome = est if tipo == "nova" else f"{est} · {rot} ({arq.stem})"
                linhas.append(dict(nome=nome, tipo=tipo, robo=est, origem=f"{pasta}/trades/{arq.name}", **metricas(g)))
    rdt = AQUI / "n_nova" / "r1_RDT_2026.csv"
    if rdt.exists():
        linhas.append(dict(nome="RDT (estratégia nova)", tipo="nova", robo="RDT", origem="n_nova/r1_RDT_2026.csv", **metricas(pd.read_csv(rdt))))
    df = pd.DataFrame(linhas)
    orig = df[df.tipo == "original"].set_index("robo")
    piso = float(orig.liq.min())
    df["vs_original"] = [round(r.liq - orig.liq[r.robo], 2) if r.tipo == "variante" and r.robo in orig.index else None
                         for r in df.itertuples()]
    # nova: rende mais que a pior original. variante de um robô: além disso, tem de render mais que o próprio original
    # (senão ela só herda o lucro do robô forte em que foi aplicada).
    df["candidata"] = (df.tipo != "original") & (df.liq > piso) & ((df.tipo == "nova") | (df.vs_original.fillna(0) > 0))
    df = df.sort_values("liq", ascending=False)
    df.drop(columns="mensal").to_csv(AQUI / "ranking.csv", index=False)
    (AQUI / "ranking.json").write_text(json.dumps(dict(piso=piso, piso_nome=orig.liq.idxmin(), custo=CUSTO,
                                                       linhas=df.astype(object).where(pd.notna(df), None).to_dict("records")), ensure_ascii=False), encoding="utf-8")
    cols = ["nome", "tipo", "ops", "liq", "acerto", "payoff", "pf", "dd", "fr", "meses_pos", "quebra", "candidata", "vs_original"]
    with pd.option_context("display.width", 250, "display.max_colwidth", 70, "display.max_rows", 200):
        print(f"piso = {piso} ({orig.liq.idxmin()})")
        print(df[cols].to_string(index=False))


if __name__ == "__main__":
    main()
