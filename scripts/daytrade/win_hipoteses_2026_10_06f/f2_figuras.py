"""f2: figuras graficas / estrutura como FILTRO de entrada ou SAIDA do WinCincoMedias v2.02. So' 2026.
Cada variante: 1 rodada real + 10 rodadas com filtro ALEATORIO que corta a mesma fracao de sinais (por segmento/contrato).
Estagio 1 = variantes isoladas; estagio 2 = combinacoes dos melhores. Saidas: f2_resumo.csv, f2_res.pkl, stdout."""
import itertools
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parent))
import win_cinco_medias as W
import f2_candidatas as C

SEEDS = range(10)
_D = None


def specs_estagio1():
    S = []
    for tf, ks in (("m30", (2, 3, 5)), ("dia", (1, 2, 3))):
        for k in ks:
            for modo in ("full", "hl", "hh", "ncontra"):
                S.append(("st", tf, k, modo))
    for N in (12, 24, 48):
        for m in (1, 3, 6):
            for modo in ("so_rompe", "nao_rompe"):
                S.append(("rb", N, m, modo))
    for ref in ("dia", "sem"):
        for m in (1, 3, 6):
            for modo in ("so_rompe", "nao_rompe"):
                S.append(("rb", ref, m, modo))
    for fonte in (("m30", 3), ("m30", 5), ("dia", 2)):
        for X in (0.5, 1.0, 1.5, 2.0, 3.0):
            S.append(("bar", fonte, X))
    for N in (6, 12, 24):
        for q in (0.3, 0.5, 0.7):
            for modo in ("baixo", "alto"):
                S.append(("cp", N, q, modo))
    for N in (6, 12, 24):
        for f in (0.6, 0.8, 1.0):
            S.append(("ct", N, f))
    for k in (2, 3):
        for tol in (0.2, 0.4, 0.6, 1.0):
            S.append(("dup", k, tol))
    return S


def nome(s):
    if s is None:
        return "BASE"
    if s[0] == "and":
        return "AND[" + " + ".join(nome(x) for x in s[1:]) + "]"
    return s[0] + ":" + "_".join(str(x) for x in s[1:])


def _rodar_kw(d, extra=None, saida_x=None):
    C.instala_simula_x()
    kw = {}
    if extra is not None:
        kw["extra"] = extra
    if saida_x is not None:
        kw["saida_x"] = saida_x
    return W.rodar_janelas(2026, dados=d, **kw)


def _rand_fns(spec, seed):
    ex, sx = C.construir(spec)
    if ex is not None:
        def f(dd):
            ok_c, ok_s = ex(dd)
            est = W.alinhamento(dd)
            pc = ok_c[est == 1].mean() if (est == 1).any() else 1.0
            ps = ok_s[est == -1].mean() if (est == -1).any() else 1.0
            rng = np.random.default_rng([seed, len(dd)])
            n = len(dd)
            return rng.random(n) < pc, rng.random(n) < ps
        return f, None
    def g(dd):
        xl, xs, _, _ = sx(dd)
        n = len(dd); rng = np.random.default_rng([seed, len(dd), 7])
        idx = np.arange(n)
        return rng.random(n) < xl.mean(), rng.random(n) < xs.mean(), idx, idx
    return None, g


def unidade(spec):
    global _D
    if _D is None:
        _D = W.carregar(2026)
    d = _D
    ex, sx = C.construir(spec)
    tab, res = _rodar_kw(d, ex, sx)
    rand = []
    if spec is not None:
        for sd in SEEDS:
            e2, s2 = _rand_fns(spec, sd)
            rand.append(_rodar_kw(d, e2, s2)[1])
    return spec, tab, res, rand


def linha(spec, tab, r, rand, base_tab, rb):
    m = dict(zip(tab.janela, tab.liquido)); bm = dict(zip(base_tab.janela, base_tab.liquido))
    melh = sum(m.get(j, 0) > bm[j] for j in bm); pior = sum(m.get(j, 0) < bm[j] for j in bm)
    rl = np.array([x["liquido"] for x in rand]) if rand else np.array([])
    pct = float((rl < r["liquido"]).mean() * 100) if len(rl) else np.nan
    jp = int(r["janelas_pos"].split("/")[0]); jb = int(rb["janelas_pos"].split("/")[0])
    crit = dict(liq=r["liquido"] > rb["liquido"], jan=jp >= jb, pior=r["pior"] >= rb["pior"], DD=r["maior_DD"] <= rb["maior_DD"],
                sset=r["liquido_sem_set"] > rb["liquido_sem_set"], mes=melh > pior)
    return dict(nome=nome(spec), liq=r["liquido"], jan=r["janelas_pos"], pior=r["pior"], PF=r["PF"], trades=r["trades"],
                DD=r["maior_DD"], sem_set=r["liquido_sem_set"], melhores=melh, piores=pior,
                rand_med=round(float(np.median(rl)), 0) if len(rl) else np.nan,
                rand_max=round(float(rl.max()), 0) if len(rl) else np.nan, pct=pct,
                n_crit=sum(crit.values()), tudo=all(crit.values()) and r["trades"] >= 150 and pct >= 90)


def rodar_lote(lote, R, rows, rotulo, base):
    tb, rb = base
    with ProcessPoolExecutor(max_workers=6) as ex:
        fut = [ex.submit(unidade, s) for s in lote]
        for i, f in enumerate(as_completed(fut)):
            s, tab, r, rand = f.result()
            R[s] = (tab, r, rand)
            ln = linha(s, tab, r, rand, tb, rb); rows.append(ln)
            print(f"[{rotulo} {i + 1}/{len(lote)}] {ln['nome']}: liq {ln['liq']} jan {ln['jan']} pior {ln['pior']} DD {ln['DD']} "
                  f"trades {ln['trades']} crit {ln['n_crit']}/6 pct {ln['pct']:.0f} rand_med {ln['rand_med']} max {ln['rand_max']}", flush=True)


if __name__ == "__main__":
    R = {}; rows = []
    s0, tb, rb, _ = unidade(None)
    print("BASELINE", rb, flush=True)
    base = (tb, rb)
    S1 = specs_estagio1()
    print("estagio 1:", len(S1), "variantes", flush=True)
    rodar_lote(S1, R, rows, "E1", base)
    df1 = pd.DataFrame(rows)
    # estagio 2: combinacoes (AND) dos melhores isolados (liq >= 0.97*base, trades>=150), familias diferentes
    fam = lambda n: n.split(":")[0]
    cand = df1[(df1.liq >= 0.97 * rb["liquido"]) & (df1.trades >= 150) & (~df1.nome.str.startswith("dup"))].sort_values("liq", ascending=False)
    topo = []
    vistos = {}
    for _, r_ in cand.iterrows():
        if vistos.get(fam(r_["nome"]), 0) < 2:
            topo.append(r_["nome"]); vistos[fam(r_["nome"])] = vistos.get(fam(r_["nome"]), 0) + 1
    nome2spec = {nome(s): s for s in S1}
    S2 = [("and", nome2spec[a], nome2spec[b]) for a, b in itertools.combinations(topo, 2) if fam(a) != fam(b)]
    dups = df1[df1.nome.str.startswith("dup")].sort_values("liq", ascending=False)
    if len(dups) and len(topo):
        S2 += [("and", nome2spec[topo[0]], nome2spec[dups.iloc[0]["nome"]])] if False else []
    print("estagio 2:", len(S2), "combinacoes de", topo, flush=True)
    if S2:
        rodar_lote(S2, R, rows, "E2", base)
    df = pd.DataFrame(rows)
    df.to_csv(AQUI / "f2_resumo.csv", index=False)
    pickle.dump((R, base), open(AQUI / "f2_res.pkl", "wb"))
    pd.set_option("display.width", 300); pd.set_option("display.max_rows", 600); pd.set_option("display.max_colwidth", 80)
    print("\nTOTAL DE VARIANTES:", len(df), "(estagio 1:", len(S1), "| estagio 2:", len(S2), ") + baseline")
    print(df.sort_values("liq", ascending=False).to_string(index=False))
    print("\nPASSAM TODOS OS CRITERIOS:\n", df[df.tudo].to_string(index=False))
