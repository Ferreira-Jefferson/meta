"""Z9-T3 -- so opera com concordancia. Variantes: a (saida segue o 1o votante), b (sai quando o 1o dos concordantes sai),
c (sai quando o ultimo sai), ad/bd/cd (+ conflito: voto contrario zera a mercado), e (3 robos, saida como a). Entrada: mkt=preco(t), lim=preco_entrada do 2o."""
import sys
from collections import Counter
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base

OUT = Path(__file__).resolve().parent
VAR = {"a": ("a", 2, False), "b": ("b", 2, False), "c": ("c", 2, False), "ad": ("a", 2, True),
       "bd": ("b", 2, True), "cd": ("c", 2, True), "e": ("a", 3, False)}


def formacoes(o, nmin):
    """eventos de concordancia: (t, B, ativos_mesmo_lado ordenados por entrada) sem voto contrario ativo."""
    ev = []
    for i, b in o.iterrows():
        t = b.entrada
        at = o[(o.entrada <= t) & (o.saida > t)]
        if (at.lado != b.lado).any():
            continue
        if len(at) >= nmin:
            ev.append((t, i, at.sort_values(["entrada", "prio"]).index.tolist()))
    return ev


def simula(o, modo, nmin, conflito, entr):
    sai_modo = modo
    pos = []
    livre = pd.Timestamp.min
    for t, ib, ids in formacoes(o, nmin):
        if t < livre:
            continue
        g = o.loc[ids]; b = o.loc[ib]; L = int(b.lado); lead = g.iloc[0]
        pe = base.preco(t) if entr == "mkt" else float(b.preco_entrada)
        if sai_modo == "a":
            ts, ps = lead.saida, float(lead.preco_saida); mot = "lider"
        elif sai_modo == "b":
            ts = g.saida.min(); ps = base.preco(ts); mot = "primeiro_sai"
        else:
            ts = g.saida.max(); ps = base.preco(ts); mot = "ultimo_sai"
        if conflito:
            c = o[(o.lado != L) & (o.entrada > t) & (o.entrada < ts)]
            if len(c):
                ts = c.entrada.min(); ps = base.preco(ts); mot = "conflito"
        pos.append(dict(ano=int(b.entrada.year), entrada=t, saida=ts, lado=L, preco_entrada=pe, preco_saida=ps,
                        rs=(ps - pe) * 0.2 * L, lider=lead.estrategia, segundo=b.estrategia, n=len(g), motivo=mot))
        livre = ts
    return pd.DataFrame(pos)


def main():
    anos = range(2022, 2027)
    res = {}; trades = {}; conc = {}; pares = Counter()
    iso = {}
    for ano in anos:
        o = base.operacoes(ano); o["prio"] = o.estrategia.map({r: i for i, r in enumerate(base.ROBOS)})
        iso[ano] = base.resumo(o)[ano]["liq"]
        f2 = formacoes(o, 2)
        conc[ano] = (len(f2), len({t.date() for t, _, _ in f2}), o.entrada.dt.date.nunique())
        for t, ib, ids in f2:
            pares[tuple(sorted([o.loc[ids[0]].estrategia, o.loc[ib].estrategia]))] += 1
        for entr in ("mkt", "lim"):
            for v, (m, n, c) in VAR.items():
                p = simula(o, m, n, c, entr)
                trades.setdefault((v, entr), []).append(p)
                r = base.resumo(p)[ano] if len(p) else dict(liq=0, ops=0, acerto=None, dd=0, quebra=None)
                res[(v, entr, ano)] = r
        print(ano, "soma isolada", iso[ano], "| concordancias", conc[ano],
              "| a/mkt", res[("a", "mkt", ano)], flush=True)
    for (v, e), l in trades.items():
        pd.concat(l).to_csv(OUT / f"trades_{v}_{e}.csv", index=False)
    # sanidade: 3 casos
    print("\nSANIDADE (T3a mkt)")
    d = pd.read_csv(OUT / "trades_a_mkt.csv")
    for _, r in d.sample(3, random_state=1).iterrows():
        print(f"{r.entrada} {r.lado:+d} {r.segundo} confirma {r.lider}; entra {r.preco_entrada} sai {r.saida} @ {r.preco_saida}"
              f" -> {(r.preco_saida-r.preco_entrada)*0.2*r.lado:.2f} (csv {r.rs:.2f})", flush=True)
    # resultado.md
    L = ["# Z9-T3 -- so opera com concordancia (>=2 robos, mesmo lado, nenhum contra)\n",
         "Votos = operacoes isoladas; abertura a preco(t) do 2o votante (mkt) ou preco_entrada dele (lim). Custo R$2/op, R$1.000 por ano.\n",
         "Variantes: a=saida segue o 1o votante (preco_saida dele); b=sai quando o 1o dos concordantes sai; c=quando o ultimo sai; "
         "ad/bd/cd=+voto contrario zera a mercado; e=exige 3 robos (saida como a).\n",
         "## Frequencia de concordancia (eventos / dias com concordancia / dias com alguma op)\n",
         "| ano | eventos | dias | dias c/ op |\n|---|---|---|---|"]
    for a in anos:
        L.append(f"| {a} | {conc[a][0]} | {conc[a][1]} | {conc[a][2]} |")
    for e in ("mkt", "lim"):
        L.append(f"\n## Entrada `{e}` -- liquido R$ (ops; acerto%; maior queda R$; quebra)\n")
        L.append("| variante | " + " | ".join(map(str, anos)) + " | soma 22-25 |\n|---|" + "---|" * (len(anos) + 1))
        L.append("| soma isolada (5 contas) | " + " | ".join(f"{iso[a]:.0f}" for a in anos) + f" | {sum(iso[a] for a in anos if a<2026):.0f} |")
        for v in VAR:
            c = []
            for a in anos:
                r = res[(v, e, a)]
                c.append(f"{r['liq']:.0f} ({r['ops']}; {r['acerto']}; {r['dd']:.0f}; {r['quebra'] or '-'})")
            s = sum(res[(v, e, a)]["liq"] for a in anos if a < 2026)
            L.append(f"| {v} | " + " | ".join(c) + f" | {s:.0f} |")
    L.append("\n## Pares que mais formam concordancia (lider, 2o)\n")
    for k, n in pares.most_common():
        L.append(f"- {k[0]} + {k[1]}: {n}")
    (OUT / "resultado.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L), flush=True)


if __name__ == "__main__":
    main()
