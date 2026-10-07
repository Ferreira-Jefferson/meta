import json, importlib.util as u, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import hip_a_ancora_mensal as H
R = json.load(open(H.AQUI / "hip_a_resultados.json"))
base = R["baseline"]; bl = base["liq"]
def f(x): return f"{x:,.0f}".replace(",", ".")
L = ["# Hipótese A — média/VWAP/abertura ancorada no 1º pregão do mês\n",
     f"Variantes testadas: **{len(R)}** (1 baseline + 60 variantes + 1 oráculo). Motor, capital (R$1.000/janela) e execução (entrada limite) idênticos ao baseline.\n",
     "Âncora = primeiro pregão do mês DENTRO do contrato (max(início do mês, início do contrato)); só usa dados até o fechamento da barra do sinal. Primeiros D pregões: `0` opera os dois lados; `mesant` usa o regime da última barra do mês anterior (se estiver no mesmo contrato; senão os dois lados).\n",
     "| variante | líquido R$ | jan + | pior jan | PF | pts/op | trades | maior DD R$ | DD % | fator recup. | LOWO (sem a melhor jan) vs base |",
     "|---|---|---|---|---|---|---|---|---|---|---|"]
def row(n):
    r = R[n]["r"]; liq = R[n]["liq"]
    i = max(range(len(liq)), key=lambda k: liq[k] - bl[k])  # janela de maior ganho vs baseline
    j = max(range(len(liq)), key=lambda k: liq[k])
    lo = sum(liq) - liq[j]; bo = sum(bl) - bl[j]
    return (f"| {n} | {f(r['liquido_total'])} | {r['janelas_pos']} | {f(r['pior_janela'])} | {r['PF']} | {r['pts/op']} | {r['trades']} | "
            f"{f(r['maior_DD_R$'])} | {r['maior_DD%']} | {r['fator_recup']} | {f(lo)} vs {f(bo)} |")
ordem = ["baseline"] + sorted([n for n in R if n not in ("baseline", "ORACULO")], key=lambda n: -R[n]["r"]["liquido_total"]) + ["ORACULO"]
for n in ordem: L.append(row(n))
L.append("\nLOWO: remove de cada série (variante e baseline separadamente) a sua janela de maior ganho e compara o líquido restante.\n")
# resumo por âncora
import statistics as st
for anc in ("media", "vwap", "abertura"):
    xs = [R[n]["r"]["liquido_total"] for n in R if n.startswith(anc + "|")]
    L.append(f"- Âncora `{anc}`: {len(xs)} variantes, líquido min/mediana/max = {f(min(xs))} / {f(st.median(xs))} / {f(max(xs))} (baseline {f(sum(bl))}); superam o baseline: {sum(x>sum(bl) for x in xs)}/{len(xs)}.")
# mes a mes
cands = ["abertura|pos|k0|D0", "abertura|pos|k0.5|D2"]
L.append("\n## Mês a mês — baseline vs candidatas (líquido R$ por janela)\n")
L.append("| janela | baseline | " + " | ".join(cands) + " |"); L.append("|---|---|" + "---|" * len(cands))
for i, j in enumerate(base["jan"]):
    L.append(f"| {j} | {f(bl[i])} | " + " | ".join(f(R[c]['liq'][i]) for c in cands) + " |")
L.append("| **total** | " + f"**{f(sum(bl))}** | " + " | ".join(f"**{f(sum(R[c]['liq']))}**" for c in cands) + " |")
o = R["ORACULO"]["liq"]
L.append(f"\n## Oráculo (teto, nunca candidata)\nLíquido {f(sum(o))}, janelas+ {R['ORACULO']['r']['janelas_pos']}, PF {R['ORACULO']['r']['PF']}, pior janela {f(R['ORACULO']['r']['pior_janela'])}, maior DD {f(R['ORACULO']['r']['maior_DD_R$'])}.")
Path(H.AQUI / "hip_a_ancora_mensal.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
