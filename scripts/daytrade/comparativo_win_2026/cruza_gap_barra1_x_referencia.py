"""Cruzamento do replay do WinGapBarra1 (port_win_gap_barra1.py) com EA_referencia_trades.csv (S1200, 1 contrato,
2026-04-06..2026-10-05). A referencia usa R$0,50/contrato de custo e 1 tick de deslize no stop e no zeramento (R$1,00)."""
import sys
from datetime import date
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import port_win_gap_barra1 as G  # noqa: E402

REF = AQUI.parents[0] / "win_gap_estrategia_2026_10_06" / "rodada4_estrategia_2026_10_06" / "EA_referencia_trades.csv"
m1 = G.m1_total(); gt = G.ticks_fn(m1)
dias = [d for d in sorted(set(m1.index.date)) if date(2026, 4, 6) <= d <= date(2026, 10, 5)]
R = pd.read_csv(REF, sep=";", decimal=",")
R = R[R.celula.str.startswith("S1200")].copy()
R["lado"] = R.lado.map({"compra": 1, "venda": -1})
print("referencia:", len(R), "trades, R$", round(R.pnl_1_contrato_brl.sum(), 2))
for var in ("ea", "ref"):
    tr, _, _, dg = G.rodar(dias, m1, gt, variante=var)
    T = pd.DataFrame(tr); T["dia"] = T.entrada.str[:10]; R["dia"] = R.dia.astype(str)
    j = R.merge(T, on="dia", how="outer", suffixes=("_ref", "_py"), indicator=True)
    both = j[j._merge == "both"]
    mesmo_lado = (both.lado_ref == both.lado_py)
    mesma_ent = mesmo_lado & ((both.entrada_ref if "entrada_ref" in both else both["entrada_ref"]) == both.preco_entrada) if False else mesmo_lado & (both["entrada_ref"] == both.preco_entrada)
    # preco de saida e motivo
    mesmo_mot = both.motivo_ref == both.motivo_py
    dif = (both.rs - 1.5 * 0 - both.pnl_1_contrato_brl)   # bruto do replay - liquido da referencia (R$0,50 + 1 tick de deslize = R$1,50 de custo)
    print(f"\n== variante {var}: replay {len(T)} trades, bruto R$ {T.rs.sum():.2f}, liq. ref-conv (-R$1,50/trade) R$ {T.rs.sum()-1.5*len(T):.2f} | diag {dg}")
    print(f"dias em ambos {len(both)}  so' ref {(j._merge=='left_only').sum()}  so' replay {(j._merge=='right_only').sum()}")
    print(f"mesmo lado {mesmo_lado.mean()*100:.1f}% | mesmo lado e preco de entrada {mesma_ent.mean()*100:.1f}% ({mesma_ent.sum()}/{len(both)}) | mesmo motivo {mesmo_mot.mean()*100:.1f}%")
    dd = dif[mesma_ent]
    print(f"nos {mesma_ent.sum()} com mesma entrada: dif replay bruto - ref liquido: mediana {dd.median():.2f}  media {dd.mean():.2f}  |dif|<=2: {(dd.abs()<=2).mean()*100:.1f}%  |dif|<=5: {(dd.abs()<=5).mean()*100:.1f}%")
    both = both.assign(dif=dif, ent_ok=mesma_ent)
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_rows", 200)
    print(both[~both.ent_ok][["dia", "lado_ref", "lado_py", "entrada_ref", "preco_entrada", "hora_fill", "motivo_ref", "motivo_py", "pnl_1_contrato_brl", "rs"]].to_string())
    print(j[j._merge != "both"][["dia", "lado_ref", "lado_py", "entrada_ref", "preco_entrada", "pnl_1_contrato_brl", "rs", "_merge"]].to_string())
    big = both[both.ent_ok & (both.dif.abs() > 5)]
    print("com mesma entrada e |dif|>5:\n", big[["dia", "entrada_ref", "motivo_ref", "motivo_py", "saida_ref", "preco_saida", "hora_saida", "pnl_1_contrato_brl", "rs"]].to_string())
