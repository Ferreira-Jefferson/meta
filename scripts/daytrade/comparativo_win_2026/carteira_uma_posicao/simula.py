"""Carteira: todos os robos da pagina ligados juntos numa conta de R$1.000, UMA posicao por vez.
O primeiro que entra trava os outros ate' sair; entrada de outro robo durante a posicao aberta e' descartada.
Aproximacao: as operacoes de cada robo vem do replay isolado (resultados/*.csv); um robo bloqueado
nao muda as operacoes seguintes dele. 1 contrato. Custo por operacao: R$2 (pagina) e R$5 (saida a mercado)."""
import sys
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
RES = AQUI.parent / "resultados"
INI, FIM = pd.Timestamp("2026-02-05"), pd.Timestamp("2026-10-05 23:59")
ORDEM = ["WinGapBarra1", "WinCincoMedias", "WinDeslocamentoMatinal", "WinRetanguloEma34", "Win_c1"]  # desempate se entram no mesmo segundo
MARGEM = 100.0

tr = pd.concat([pd.read_csv(RES / f"{r}.csv") for r in ORDEM], ignore_index=True)
tr["entrada"] = pd.to_datetime(tr.entrada.astype(object), format="ISO8601"); tr["saida"] = pd.to_datetime(tr.saida.astype(object), format="ISO8601")
tr = tr[(tr.entrada >= INI) & (tr.entrada <= FIM)].copy()
tr["prio"] = tr.estrategia.map({r: i for i, r in enumerate(ORDEM)})
tr = tr.sort_values(["entrada", "prio"]).reset_index(drop=True)

livre_em, aceitos, empates = pd.Timestamp.min, [], 0
for i, x in tr.iterrows():
    if x.entrada >= livre_em:
        if aceitos and tr.loc[aceitos[-1], "entrada"] == x.entrada:
            empates += 1
        aceitos.append(i); livre_em = x.saida
    elif x.entrada == tr.loc[aceitos[-1], "entrada"]:
        empates += 1
tr["executou"] = False; tr.loc[aceitos, "executou"] = True

def curva(df, custo):
    s = 1000.0 + (df.rs - custo).cumsum()
    pico = s.cummax().clip(lower=1000.0)
    return s, float((pico - s).max()), float(min(1000.0, s.min()))

linhas = []
for custo in (2.0, 5.0):
    ex = tr[tr.executou].sort_values("saida")
    s, dd, smin = curva(ex, custo)
    linhas.append((custo, len(ex), float(s.iloc[-1] - 1000), dd, smin))
    print(f"\n=== custo R${custo:.0f}/op: carteira 1 posicao por vez ===", flush=True)
    print(f"operacoes {len(ex)} | liquido R${s.iloc[-1]-1000:,.0f} | maior queda R${dd:,.0f} | saldo minimo R${smin:,.0f}")
    print(f"capital necessario (saldo nunca < margem R$100): R${1000 - smin + MARGEM:,.0f} | com folga 2,5x margem (R$250): R${1000 - smin + 250:,.0f}")
    # quanto precisaria se partisse do zero: pior queda desde o inicio + margem
    print(f"{'robo':24s} {'sinais':>6s} {'operou':>6s} {'bloq.':>6s} {'liq. operado':>12s} {'liq. sozinho':>12s}")
    for r in ORDEM:
        a = tr[tr.estrategia == r]; e = a[a.executou]
        print(f"{r:24s} {len(a):6d} {len(e):6d} {len(a)-len(e):6d} {(e.rs-custo).sum():12,.0f} {(a.rs-custo).sum():12,.0f}")
    tot = tr.groupby("estrategia").apply(lambda a: (a.rs - custo).sum())
    print(f"soma dos robos cada um sozinho (5 contas): R${tot.sum():,.0f}")
print(f"\nempates de horario de entrada: {empates}")
tr.to_csv(AQUI / "operacoes_carteira.csv", index=False)
