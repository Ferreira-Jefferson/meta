import json, numpy as np
from pathlib import Path
AQ = Path(__file__).resolve().parent
D = json.load(open(AQ / "coleta.json")); GRADE = [tuple(g) for g in D["grade"]]; T = D["trades"]
RS = 0.2
G = np.array([t["grade"] for t in T]) * RS          # R$ por trade x combo
ATUAL = np.array([t["atual"] for t in T]) * RS
dias = np.array([t["dia"] for t in T]); ciclo = np.array([t["ciclo"] for t in T])
fonte = [t["fonte"].encode("latin1", "ignore").decode("ascii", "ignore").lower() for t in T]
def nat(s):
    if any(k in s for k in ("rompe", "rompimento", "impulso", "nova m")): return "rompimento"
    if any(k in s for k in ("recuo", "pullback")): return "continuacao"
    return "reversao"
NAT = np.array([nat(s) for s in fonte])
E_ = lambda k: np.array([t["estado"][k] for t in T])
ef, vol4, fav = E_("ef"), E_("vol4"), E_("a_favor")
REG = {
 "ef>=0,20 (direcional) x rotacao": np.where(ef >= 0.20, "dir", "rot"),
 "vol4>=1,0 (alta) x baixa": np.where(vol4 >= 1.0, "alta", "baixa"),
 "a favor x contra o dia": np.where(fav == 1, "favor", "contra"),
 "natureza: continuacao x resto": np.where(NAT == "continuacao", "cont", "resto"),
 "ef x vol (4 regimes)": np.array([f"{a}/{b}" for a, b in zip(np.where(ef >= .2, "dir", "rot"), np.where(vol4 >= 1, "alta", "baixa"))]),
}
nome = lambda j: f"stop {GRADE[j][0]} / alvo {GRADE[j][1] or 'sem'} / {GRADE[j][2]}"
NMIN = 5

def fixa(idx): return int(np.argmax(G[idx].sum(0)))
def escolhe(idx, reg):
    f = fixa(idx); m = {}
    for r in set(reg[idx]):
        k = idx[reg[idx] == r]
        m[r] = int(np.argmax(G[k].sum(0))) if len(k) >= NMIN else f
    return m, f
def aplica(idx, reg, m, f): return sum(G[i, m.get(reg[i], f)] for i in idx)

def avalia(treino, teste, reg):
    m, f = escolhe(treino, reg)
    return dict(adapt=aplica(teste, reg, m, f), fixa=G[teste, f].sum(), atual=ATUAL[teste].sum())
def lodo(reg):
    a = fx = 0
    for d in set(dias):
        te = np.where(dias == d)[0]; tr = np.where(dias != d)[0]
        m, f = escolhe(tr, reg); a += aplica(te, reg, m, f); fx += G[te, f].sum()
    return a, fx
if __name__ == "__main__":
    n = len(T); allx = np.arange(n)
    out = []
    P = lambda *a: out.append(" ".join(str(x) for x in a))
    teto = G.max(1).sum()
    P(f"trades {n}; dias {len(set(dias))}; combos {len(GRADE)}")
    P(f"TETO (melhor gestao por trade, retrospectivo): R$ {teto:.0f} | atual R$ {ATUAL.sum():.0f} | melhor fixa (in-sample) R$ {G.sum(0).max():.0f} = {nome(fixa(allx))}")
    for c in (0, 1, 2): P(f" ciclo {c}: n={int((ciclo==c).sum())} atual {ATUAL[ciclo==c].sum():.0f} teto {G[ciclo==c].max(1).sum():.0f}")
    P("\nPOR NATUREZA (atual R$ / n):", {k: (round(ATUAL[NAT == k].sum()), int((NAT == k).sum())) for k in set(NAT)})
    tr = np.where(ciclo <= 1)[0]; te = np.where(ciclo == 2)[0]
    f = fixa(tr); P(f"\nMelhor fixa treino ciclos 0+1: {nome(f)} -> treino R$ {G[tr,f].sum():.0f} (atual {ATUAL[tr].sum():.0f}); ciclo 2: {G[te,f].sum():.0f} (atual {ATUAL[te].sum():.0f})")
    P("\n| regime | n parametros | dentro (todos 50) adapt | ciclo0+1->2 adapt | fixa | atual | LODO adapt | LODO fixa | atual 50 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for k, reg in REG.items():
        m, f0 = escolhe(allx, reg); dentro = aplica(allx, reg, m, f0)
        r = avalia(tr, te, reg); la, lf = lodo(reg)
        P(f"| {k} | {3*len(set(reg))} | {dentro:.0f} | {r['adapt']:.0f} | {r['fixa']:.0f} | {r['atual']:.0f} | {la:.0f} | {lf:.0f} | {ATUAL.sum():.0f} |")
        if k in ("ef>=0,20 (direcional) x rotacao",) or True:
            P("   mapa (50 dias):", {r_: nome(j) for r_, j in m.items()}, "| n:", {r_: int((reg == r_).sum()) for r_ in m})
            mt, ft = escolhe(tr, reg); P("   mapa (ciclos 0+1):", {r_: nome(j) for r_, j in mt.items()})
    # LODO da melhor fixa vs atual
    P(f"\nLODO melhor fixa: usado acima. Atual total {ATUAL.sum():.0f}")
    # por ciclo-out (leave-one-cycle-out)
    P("\nLeave-one-cycle-out (adapt / fixa / atual):")
    for k, reg in REG.items():
        row = []
        for c in (0, 1, 2):
            r = avalia(np.where(ciclo != c)[0], np.where(ciclo == c)[0], reg); row.append(f"c{c}: {r['adapt']:.0f}/{r['fixa']:.0f}/{r['atual']:.0f}")
        P(" ", k, "|", " ; ".join(row))
    # distribuicao de ganhos por tipo de gestao (marginal)
    P("\nTop 8 combos fixos (50 dias, in-sample):")
    for j in np.argsort(-G.sum(0))[:8]: P(f"  {nome(j)}: R$ {G[:,j].sum():.0f}")
    P("Marginais: por stop", {s: round(G[:, [i for i,g in enumerate(GRADE) if g[0]==s]].sum(1).mean()*0+G[:, [i for i,g in enumerate(GRADE) if g[0]==s]].mean()*n) for s in (0.75,1,1.5,2)})
    P("por alvo", {str(a): round(G[:, [i for i,g in enumerate(GRADE) if g[1]==a]].mean()*n) for a in (0.75,1,1.5,2,3,None)})
    P("por trailing", {t: round(G[:, [i for i,g in enumerate(GRADE) if g[2]==t]].mean()*n) for t in ("nenhum","be1","t2","t4","t8")})
    # melhor gestao por trade: o que ela e? e correlacao com estado
    best = G.argmax(1)
    P("\nMelhor gestao por trade -> fracao com alvo 'sem':", np.mean([GRADE[j][1] is None for j in best]).round(2), "| stop medio", np.mean([GRADE[j][0] for j in best]).round(2))
    txt = "\n".join(out); print(txt); (AQ / "analise_saida.txt").write_text(txt, encoding="utf-8")
