"""Confere no MOTOR COMPLETO (sequencia de entradas, max 3 ops, 1 posicao) as gestoes fixas, sobrepondo stop/alvo/gerir de cada FAZER."""
import json, sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
AQ = Path(__file__).resolve().parent; PAI = AQ.parent; sys.path.insert(0, str(PAI))
import robo_v2

def envolve(r, sk, ak):
    def f(ctx):
        s = r(ctx)
        if not s or "erro" in s: return s
        s = dict(s); p = float(s.get("preco", ctx.hoje.close.iloc[-1])); sg = 1 if s["lado"] == "compra" else -1
        s["stop"] = p - sg * min(sk * ctx.atr15, 600)
        s["alvo"] = None if ak is None else p + sg * ak * ctx.atr15
        return s
    return f

def um(args):
    dia, sk, ak = args
    fz, nf = robo_v2.monta_v2()
    if sk is not None: fz = [(n, envolve(r, sk, ak), None) for n, r, g in fz]
    tr, _, _ = robo_v2.roda_v2(dia, fz, nf)
    ok = [x for x in tr if x.t_ent]
    return args, sum(x.brl for x in ok), len(ok)

if __name__ == "__main__":
    du = json.load(open(PAI / "dias_usados.json"))
    dias = list(du["ciclo0"]["dias"]) + [x["dia"] for x in du["ciclo1"]["dias"]] + [x["dia"] for x in du["ciclo2"]["dias"]]
    cfgs = [(None, None), (2, None), (1.5, None), (1, None), (1.5, 3), (1.5, 2)]
    tot = {c: [0, 0] for c in cfgs}
    with ProcessPoolExecutor(6) as ex:
        for f in as_completed([ex.submit(um, (d, *c)) for d in dias for c in cfgs]):
            (d, sk, ak), b, n = f.result(); tot[(sk, ak)][0] += b; tot[(sk, ak)][1] += n
    for c, (b, n) in tot.items(): print("stop", c[0], "alvo", c[1], "-> R$", round(b), "ops", n, flush=True)
