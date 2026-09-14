"""Combina os caches de P&L diario ja' computados (`_gremah_daily_pnl_cache.
json`, janela completa 170 pregoes, e `_wdo_daily_pnl_cache.json`, amostra de
20 pregoes -- 10 IS + 10 OOS, ver a ressalva no relatorio final sobre por que
nao e' a janela cheia de 123) e calcula correlacao + varredura de peso, no
MESMO metodo do `portfolio_wdoorb_gremah_2026_09_11.py::main`. Script de
apoio, NAO reroda nenhum backtest -- so' le' os dois JSON e faz a conta."""
import json
import math

import numpy as np
import pandas as pd

with open("scripts/daytrade/_gremah_daily_pnl_cache.json") as f:
    g = json.load(f)
with open("scripts/daytrade/_wdo_daily_pnl_cache.json") as f:
    w = json.load(f)

gre_daily = pd.Series({pd.Timestamp(k): v for k, v in g["daily_pnl"].items()}).sort_index()
wdo_daily = pd.Series({pd.Timestamp(k): v for k, v in w["daily_pnl"].items()}).sort_index()
cap_gre = float(g["capital"])
cap_wdo = float(w["capital"])

print(f"gremah: {len(gre_daily)} dias, capital R${cap_gre:.2f}")
print(f"wdo_orb: {len(wdo_daily)} dias (amostra), capital R${cap_wdo:.2f}")

overlap = wdo_daily.index.intersection(gre_daily.index)
print(f"\n[overlap] {len(overlap)} pregoes em comum")
print("dias:", [d.date().isoformat() for d in overlap])

if len(overlap) == 0:
    raise SystemExit("sem overlap -- nada a correlacionar")

r_wdo = (wdo_daily.reindex(overlap) / cap_wdo).astype(float)
r_gre = (gre_daily.reindex(overlap) / cap_gre).astype(float)

corr = float(np.corrcoef(r_wdo.values, r_gre.values)[0, 1]) if len(overlap) > 1 else float("nan")
print(f"\n[correlacao] Pearson (retornos diarios normalizados): {corr:.4f}")

print("\ndia          wdo_pnl   wdo_ret%   gre_pnl   gre_ret%")
for d in overlap:
    print(f"{d.date()}  {wdo_daily[d]:8.2f}  {100*r_wdo[d]:7.2f}%  {gre_daily[d]:8.2f}  {100*r_gre[d]:7.2f}%")


def maxdd_pct(equity_rel: pd.Series) -> float:
    pico = equity_rel.cummax()
    dd = (equity_rel - pico) / pico
    return float(dd.min()) * 100.0


melhores = []
for wt in np.linspace(0.0, 1.0, 21):
    combinado = wt * r_wdo + (1 - wt) * r_gre
    equity_rel = 1.0 + combinado.cumsum()
    dd = maxdd_pct(equity_rel)
    melhores.append((round(float(wt), 2), dd, float(combinado.sum())))

melhores_ord = sorted(melhores, key=lambda t: t[1], reverse=True)
print("\n=== varredura de peso w (fracao alocada ao wdo_orb) ===")
print(f"{'w':>6}  {'MaxDD%':>10}  {'retorno_norm_acum':>18}")
for wt, dd, liq in melhores:
    marca = "  <- MENOR |MaxDD|" if (wt, dd, liq) == melhores_ord[0] else ""
    print(f"{wt:6.2f}  {dd:10.2f}  {liq:18.4f}{marca}")

w1 = next(t for t in melhores if t[0] == 1.0)
w0 = next(t for t in melhores if t[0] == 0.0)
w5 = next(t for t in melhores if t[0] == 0.5)
wstar = melhores_ord[0]
print(f"\nwdo_orb sozinho (w=1,0): MaxDD {w1[1]:.2f}%")
print(f"gremah sozinho  (w=0,0): MaxDD {w0[1]:.2f}%")
print(f"50/50 ingenuo   (w=0,5): MaxDD {w5[1]:.2f}%")
print(f"otimo (min |MaxDD|) w={wstar[0]:.2f}: MaxDD {wstar[1]:.2f}%")

# ---- combinado NATURAL (caixa separado, capitais reais) -------------------
capital_total = cap_wdo + cap_gre
pnl_wdo = wdo_daily.reindex(overlap).fillna(0.0)
pnl_gre = gre_daily.reindex(overlap).fillna(0.0)
pnl_comb = pnl_wdo + pnl_gre
equity_comb = capital_total + pnl_comb.cumsum()
maxdd_brl = float(equity_comb.cummax().sub(equity_comb).max())
print(f"\n=== combinado NATURAL (R${cap_wdo:.2f} + R${cap_gre:.2f} = R${capital_total:.2f}) ===")
print(f"liquido combinado R$ {float(pnl_comb.sum()):.2f}")
print(f"MaxDD combinado   R${maxdd_brl:.2f} ({100*maxdd_brl/capital_total:.2f}% do capital total)")
print(f"dias positivos    {int((pnl_comb>0).sum())}/{len(overlap)}")
print(f"peso natural (capital) w_wdo={cap_wdo/capital_total:.3f} w_gremah={cap_gre/capital_total:.3f}")
