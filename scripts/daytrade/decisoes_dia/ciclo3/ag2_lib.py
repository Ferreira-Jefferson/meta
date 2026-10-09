"""Ferramentas do ciclo 3->4 (agente dos dias 2025-06-20 e 2025-07-11). Nao edita nada existente; cache proprio (ag2_cache.pkl).
Base = robo_v3. Metrica = R$/dia REPONDERADO (2 estratos: direcional ef>=0,25 = 3,8%; nao-direcional 96,2%) nos 70 dias de dias_usados.json."""
import sys, json, pickle, importlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np, pandas as pd

C3 = Path(__file__).resolve().parent
RAIZ = C3.parent
sys.path.insert(0, str(C3)); sys.path.insert(0, str(RAIZ))
import base, robo, cfg3, robo_v3

CACHE = C3 / "ag2_cache.pkl"
FR_DIR = 0.038  # fracao real de dias direcionais (PREREGISTRO, emenda 1): 3,8% / 96,2%
EF = json.load(open(C3 / "ef_todos.json"))
FR = (sum(e >= 0.25 for e in EF.values()) / len(EF))


def dias70():
    du = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in du["ciclo0"]["dias"]]
    for c in ("ciclo1", "ciclo2", "ciclo3"):
        out += [(x["dia"], c[-1:].join(["c", ""])) for x in du[c]["dias"]]
    return out

D70 = dias70()
DIAS = [d for d, _ in D70]
CIC = np.array([c for _, c in D70])
EST = np.array(["dir" if EF[d] >= 0.25 else "nd" for d in DIAS])
M3 = CIC == "c3"


def repond(v, mask=None):
    m = np.ones(len(v), bool) if mask is None else mask
    out = 0.0
    for e, f in (("dir", FR), ("nd", 1 - FR)):
        sel = m & (EST == e)
        out += f * (v[sel].mean() if sel.any() else 0.0)
    return out


class Cfg2(cfg3.Cfg):
    def __init__(self, c):
        super().__init__(c.fz, c.nf, c.prio, c.post)
        self.conflito = "nao_entra"   # ou 'dia' ou 'continuacao'


def base_v3():
    return Cfg2(robo_v3.monta_v3())


def _lado_dia(ctx, lim=0.2):
    h = ctx.hoje
    d = float(h.close.iloc[-1] - h.open.iloc[0]) / ctx.atrd
    return "compra" if d >= lim else ("venda" if d <= -lim else None)


def roda2(dia, cfg):
    """= cfg3.roda, mais a politica de conflito (FAZER nos dois lados)."""
    fz, nf, prio, post = cfg.fz, cfg.nf, cfg.prio, cfg.post

    def decide(ctx):
        for n, r, g in prio:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and not robo._agressiva(s, ctx):
                return s, dict(fazer=[(n, s["lado"])], vetos={}, entrou=n, nota="prioritaria"), g
        sins = []
        for n, r, g in fz:
            s = robo._chama(r, ctx)
            if s and "erro" not in s: sins.append((n, s, g))
        if not sins: return None, None, None
        vetos = {"compra": [], "venda": []}
        for n, r, g in nf:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
        info = dict(fazer=[(n, s["lado"]) for n, s, g in sins], vetos={k: v for k, v in vetos.items() if v}, entrou=None, nota="")
        lados = {s["lado"] for _, s, _ in sins}
        if len(lados) > 1:
            if cfg.conflito == "nao_entra":
                info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
            if cfg.conflito == "dia":
                ld = _lado_dia(ctx)
                if ld is None: info["nota"] = "dois lados, dia neutro: nao entra"; return None, info, None
                sins = [x for x in sins if x[1]["lado"] == ld]
            elif cfg.conflito == "continuacao":
                cont = [x for x in sins if cfg3.natureza(x[0]) in ("continuacao", "rompimento")]
                if len({x[1]["lado"] for x in cont}) != 1: info["nota"] = "dois lados sem desempate: nao entra"; return None, info, None
                sins = cont
        for n, s, g in sins:
            if robo._agressiva(s, ctx):
                info["nota"] += f"[{n} limitada agressiva] "; continue
            if vetos[s["lado"]]:
                info["nota"] += f"[{n} VETADA por {len(vetos[s['lado']])}] "
                return None, info, None
            info["entrou"] = n
            for f in post: s, g = f(n, s, g, ctx)
            return s, info, g
        return None, info, None
    return robo._roda(dia, decide)


def res_dia(dia, cfg):
    tr, log = roda2(dia, cfg)
    ok = [x for x in tr if x.t_ent is not None]
    return dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok),
                trades=[dict(fonte=x.fonte, lado=x.lado, sinal=str(x.t_sinal.time()), ent=str(x.t_ent.time()), sai=str(x.t_sai.time()),
                             preco=x.preco, stop=x.stop_ini, alvo=x.alvo, preco_sai=x.preco_sai, motivo=x.motivo,
                             pts=round(x.pts, 1), brl=round(x.brl, 2)) for x in ok])


# ---- candidatas: registro {id: ap(cfg)} montado a partir de modulos regras.c3_*
def monta(ids, mods=("c3_2025_06_20", "c3_2025_07_11", "c3_grupo_2025_06_20")):
    cfg = base_v3()
    reg = {}
    for m in mods:
        reg.update(importlib.import_module(f"regras.{m}").APLICA)
    for i in ids:
        if i not in reg and i.startswith("G1_"):
            from regras import c3_2025_06_20 as g
            _, d, e, m = i.split("_"); reg[i] = g._ap_post(g._g1(float(d), float(e), float(m)))
        reg[i](cfg)
    return cfg


def _um(a):
    ids, dia = a
    return ids, dia, res_dia(dia, monta(list(ids)))


def avalia(configs, dias=DIAS, workers=4):
    cache = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}
    ks = [tuple(c) for c in configs]
    falta = [(k, d) for k in dict.fromkeys(ks) for d in dias if (k, d) not in cache]
    if falta:
        with ProcessPoolExecutor(workers) as ex:
            fut = [ex.submit(_um, a) for a in falta]
            for f in as_completed(fut):
                k, d, r = f.result(); cache[(k, d)] = r
        pickle.dump(cache, open(CACHE, "wb"))
    return {k: {d: cache[(k, d)] for d in dias} for k in dict.fromkeys(ks)}


def base70():
    c = pickle.load(open(C3 / "cache.pkl", "rb"))
    return {d: c[(("C4", "C6", "C7", "C8"), d)] for d in DIAS}


def vec(res): return np.array([res[d]["brl"] for d in DIAS])


def linha(v, vb):
    d = v - vb
    lo = []
    for i in range(len(v)):
        m = np.ones(len(v), bool); m[i] = False
        lo.append(repond(v, m) - repond(vb, m))
    return dict(total=float(v.sum()), d_total=float(d.sum()), rep=repond(v), d_rep=repond(v) - repond(vb),
                d_dir=float(d[EST == "dir"].mean()), d_nd=float(d[EST == "nd"].mean()), nd=float(v[EST == "nd"].mean()),
                d_c3=float(d[M3].sum()), d_n3=float(d[M3].sum() / M3.sum()), pior=int((d < -0.5).sum()), melhor=int((d > 0.5).sum()),
                pior_dia=float(v.min()), lodo_min=float(min(lo)), lodo_dia=DIAS[int(np.argmin(lo))],
                d_0620=float(d[DIAS.index("2025-06-20")]), d_0711=float(d[DIAS.index("2025-07-11")]))


def tabela(nomes, res, vb, extra=""):
    print("id | d_rep | d_nd/dia | d_dir/dia | d_c3 | d_total | pior/melhor | pior_dia | lodo_min | 06-20 | 07-11")
    for n in nomes:
        l = linha(vec(res[n]), vb)
        print(n, round(l["d_rep"], 2), round(l["d_nd"], 2), round(l["d_dir"], 2), round(l["d_c3"], 1), round(l["d_total"], 1),
              f"{l['pior']}/{l['melhor']}", round(l["pior_dia"], 1), round(l["lodo_min"], 2), round(l["d_0620"], 1), round(l["d_0711"], 1), flush=True)
