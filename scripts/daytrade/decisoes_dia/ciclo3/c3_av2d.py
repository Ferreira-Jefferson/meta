"""Avaliacao do ciclo 3 -> 4 (agentes dos dias 2024-04-26 e 2024-07-30): candidatas sobre o v3, nos 70 dias de dias_usados.json.
Metrica: R$/dia REPONDERADO ao calendario real (direcional ef>=0,25 = 3,8%; nao-direcional 96,2%), efeito no estrato nao-direcional e
nos 20 dias do ciclo 3 (unicos sorteados ao calendario real). Nao edita nada existente; reaproveita cfg3/robo."""
import sys, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

C3 = Path(__file__).resolve().parent
RAIZ = C3.parent
sys.path.insert(0, str(C3)); sys.path.insert(0, str(RAIZ))
import cfg3, robo, base

V3 = ["C8", "C7", "C6", "C4"]
FR2 = {"dir": 0.038, "nd": 0.962}   # frações reais medidas (PREREGISTRO emenda 1): 3,8% direcional / 96,2% nao-direcional


def dias70():
    du = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in du["ciclo0"]["dias"]]
    for c in ("ciclo1", "ciclo2", "ciclo3"):
        out += [(x["dia"], c[-1:] and "c" + c[-1]) for x in du[c]["dias"]]
    return out


def registro():
    from regras import c3_grupo_2024_04_26 as g, c3_2024_04_26 as a, c3_2024_07_30 as b
    reg = {}
    for m in (g, a, b): reg.update(m.AJUSTES)
    return reg


def monta(chaves, reg):
    cfg = cfg3.monta(V3)
    motor = dict(dois_lados=None, max_ops=robo.MAX_OPS)
    for k in chaves:
        aj = reg[k]
        cfg.fz = cfg.fz + list(aj.get("add_fazer", []))
        cfg.nf = cfg.nf + list(aj.get("add_veto", []))
        cfg.prio = cfg.prio + list(aj.get("add_prio", []))
        for nome, fab in aj.get("sub_fazer", {}).items():
            assert any(n == nome for n, _, _ in cfg.fz), nome
            cfg.fz = [(n, fab(r), g) if n == nome else (n, r, g) for n, r, g in cfg.fz]
        for nome, fab in aj.get("sub_veto", {}).items():
            assert any(n == nome for n, _, _ in cfg.nf), nome
            cfg.nf = [(n, fab(r), g) if n == nome else (n, r, g) for n, r, g in cfg.nf]
        motor.update(aj.get("motor", {}))
    return cfg, motor


def roda(dia, cfg, motor):
    """Igual a cfg3.roda, com opcoes de motor: max_ops e dois_lados='desloc'."""
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
        if len({s["lado"] for _, s, _ in sins}) > 1:
            if motor.get("dois_lados") == "desloc":
                h = ctx.hoje
                d = float(h.close.iloc[-1] - h.open.iloc[0])
                if abs(d) >= ctx.atr15:
                    lado = "compra" if d > 0 else "venda"
                    sins = [x for x in sins if x[1]["lado"] == lado]
                    info["nota"] = f"dois lados -> {lado} (desloc) "
                else:
                    info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
            else:
                info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
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

    return robo._roda(dia, decide, max_ops=motor.get("max_ops", robo.MAX_OPS))


def _um(args):
    chaves, dia = args
    reg = registro()
    cfg, motor = monta(chaves, reg)
    tr, log = roda(dia, cfg, motor)
    ok = [x for x in tr if x.t_ent is not None]
    return chaves, dia, dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok),
                             trades=[dict(fonte=x.fonte, lado=x.lado, sinal=str(x.t_sinal.time()), sai=str(x.t_sai.time()), motivo=x.motivo,
                                          brl=round(x.brl, 2), pts=round(x.pts, 1)) for x in ok])


def avalia(listas, dias, workers=11):
    res = {tuple(c): {} for c in listas}
    with ProcessPoolExecutor(workers) as ex:
        fut = [ex.submit(_um, (tuple(c), d)) for c in listas for d in dias]
        for f in as_completed(fut):
            c, d, r = f.result(); res[c][d] = r
    return res


class Medida:
    def __init__(self):
        ef = json.load(open(C3 / "ef_todos.json"))
        dd = dias70()
        self.dias = [d for d, _ in dd]
        self.ciclo = np.array([c for _, c in dd])
        self.est = np.array(["dir" if ef[d] >= 0.25 else "nd" for d in self.dias])
        self.m3 = self.ciclo == "c3"

    def vec(self, r): return np.array([r[d]["brl"] for d in self.dias])

    def rep(self, v):
        return sum(f * v[self.est == e].mean() for e, f in FR2.items())

    def linha(self, v, vb):
        d = v - vb
        return dict(total=float(v.sum()), rep=float(self.rep(v)), d_rep=float(self.rep(v) - self.rep(vb)),
                    d_dir=float(d[self.est == "dir"].mean()), d_nd=float(d[self.est == "nd"].mean()),
                    d_c3=float(d[self.m3].sum()), d_tot=float(d.sum()),
                    pior=int((d < -0.5).sum()), melhor=int((d > 0.5).sum()), pior_dia=float(v.min()),
                    soma_pior=float(d[d < -0.5].sum()), soma_melhor=float(d[d > 0.5].sum()))


if __name__ == "__main__":
    reg = registro()
    cands = sys.argv[1:] or list(reg)
    M = Medida()
    listas = [()] + [tuple(c.split("+")) for c in cands]
    res = avalia(listas, M.dias)
    vb = M.vec(res[()])
    print(f"BASE v3 nos 70: total {vb.sum():.2f}  rep {M.rep(vb):.2f}  dir {vb[M.est=='dir'].mean():.2f}  nd {vb[M.est=='nd'].mean():.2f}  c3 {vb[M.m3].sum():.2f}", flush=True)
    out = {}
    for c in listas[1:]:
        v = M.vec(res[c]); l = M.linha(v, vb); out["+".join(c)] = l
        dias_p = [M.dias[i] for i in np.where((v - vb) < -0.5)[0]]
        print(f"{'+'.join(c):14s} d_rep {l['d_rep']:+7.2f}  d_nd {l['d_nd']:+6.2f}  d_dir {l['d_dir']:+7.2f}  d_c3 {l['d_c3']:+8.1f}  d_tot {l['d_tot']:+8.1f}  "
              f"pior {l['pior']} ({l['soma_pior']:+.1f}) melhor {l['melhor']} ({l['soma_melhor']:+.1f})  pior_dia {l['pior_dia']:.1f}  piorou {dias_p}", flush=True)
    json.dump(dict(base=dict(total=float(vb.sum()), rep=float(M.rep(vb))), cand=out), open(C3 / ("c3_av2d_resultado.json" if len(sys.argv) == 1 else "c3_av2d_combos.json"), "w"), indent=1)
