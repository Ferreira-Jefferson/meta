"""Mede mudancas no robo v2 nos 50 dias. Saida: varre.json = {config: {dia: [brl, ops, pior_trade]}}."""
import json, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, ".")
import motor, motor2, robo_v2
from motor2 import Cfg


def mk(nome, **kw):
    c = Cfg(); c.nome = nome
    for k, v in kw.items(): setattr(c, k, v)
    return c


def saldo(feitos):
    return sum(x.brl for x in feitos if x.t_sai is not None)


def teto_din(lim, exige_ultimo=False, min_saldo=0.0):
    def f(feitos, ctx):
        if len(feitos) < 3: return 3
        ok = saldo(feitos) > min_saldo
        fech = [x for x in feitos if x.t_sai is not None]
        if exige_ultimo: ok = ok and bool(fech) and fech[-1].brl > 0
        return lim if ok else 3
    return f


def dois(x):
    def f(sins, ctx):
        c = {}
        for n, s, g in sins:
            if s["lado"] not in c: c[s["lado"]] = motor.estado(ctx, s["lado"])["desloc"]
        a = [l for l, v in c.items() if v >= x]
        b = [l for l, v in c.items() if v < x]
        return a[0] if len(a) == 1 and len(c) == 2 else None
    return f


def pira(thr_atr, desloc_min=None):
    def f(abertas, s, est, ctx):
        sg = 1 if s["lado"] == "compra" else -1
        px = float(ctx.hoje.close.iloc[-1])
        if not all((px - a.preco) * sg >= thr_atr * ctx.atr15 for a in abertas): return False
        if desloc_min is not None and est["desloc"] < desloc_min: return False
        return True
    return f


def veto_lt(feat, x): return lambda vv, s, est, ctx: est[feat] < x


CONFIGS = {}
def add(c): CONFIGS[c.nome] = c
add(mk("base"))
add(mk("veto_off", veto_fn=lambda *a: False))
for x in (0, 0.5, 1, 1.5, 2, 2.5): add(mk(f"V_desloc<{x}", veto_fn=veto_lt("desloc", x)))
for x in (0.1, 0.15, 0.2, 0.25): add(mk(f"V_efdia<{x}", veto_fn=veto_lt("ef_dia", x)))
for x in (0.5, 1, 1.5): add(mk(f"V_perna<{x}", veto_fn=veto_lt("perna", x)))
add(mk("V_so_venda", veto_fn=lambda vv, s, est, ctx: s["lado"] == "venda"))
add(mk("V_so_compra", veto_fn=lambda vv, s, est, ctx: s["lado"] == "compra"))
add(mk("T4_saldo>0", teto_fn=teto_din(4)))
add(mk("T5_saldo>0", teto_fn=teto_din(5)))
add(mk("T5_saldo>0_ult_ganhou", teto_fn=teto_din(5, True)))
add(mk("T6_saldo>R$100", teto_fn=teto_din(6, False, 100.0)))
add(mk("C_cascata", cascata=True))
add(mk("D_dois_desloc>=0.5", dois_fn=dois(0.5)))
add(mk("D_dois_desloc>=1", dois_fn=dois(1.0)))
add(mk("P_pira_a_favor>=0", maxc=2, pira_fn=pira(0.0)))
add(mk("P_pira_a_favor>=0.5atr", maxc=2, pira_fn=pira(0.5)))
add(mk("P_pira_a_favor>=0.5atr_desloc>=1", maxc=2, pira_fn=pira(0.5, 1.0)))


def um(args):
    nome, dia = args
    fz, nf = robo_v2.monta_v2()
    tr = motor2.roda(dia, fz, nf, CONFIGS[nome])
    ok = [x for x in tr if x.t_ent is not None]
    return nome, dia, [motor.brl(tr), len(ok), min([x.brl for x in ok], default=0.0)]


def main(extra=None):
    cfgs = CONFIGS if extra is None else extra
    dias = [d for d, _, _ in motor.dias50()]
    res = {n: {} for n in cfgs}
    with ProcessPoolExecutor(11) as ex:
        fut = [ex.submit(um, (n, d)) for n in cfgs for d in dias]
        k = 0
        for f in as_completed(fut):
            n, d, r = f.result(); res[n][d] = r; k += 1
            if k % 100 == 0: print(k, len(fut), flush=True)
    json.dump(res, open("varre.json" if extra is None else ("varre4.json" if sys.argv[1] == "extra4" else "varre3.json" if sys.argv[1] == "extra3" else "varre2.json"), "w"), indent=0)
    for n in cfgs: print(n, round(sum(v[0] for v in res[n].values()), 1), flush=True)


def alvo_k(k, dmin):
    def f(s, est, ctx):
        if s.get("alvo") is not None and est["desloc"] >= dmin:
            p = float(s.get("preco", ctx.hoje.close.iloc[-1])); s["alvo"] = p + k * (float(s["alvo"]) - p)
        return s
    return f


VD0 = veto_lt("desloc", 0)
def vlado(lado, x): return lambda vv, s, est, ctx: s["lado"] == lado and est["desloc"] < x
EXTRA = {}
def addx(c): EXTRA[c.nome] = c
for x in (0, 0.5, 1): addx(mk(f"V2_venda&desloc<{x}", veto_fn=vlado("venda", x)))
for k, dm in ((1.5, 1.0), (2.0, 1.0), (2.0, 1.5), (1.5, 0.0)): addx(mk(f"A_alvo{k}x_desloc>={dm}", ajusta_fn=alvo_k(k, dm)))
for k, dm in ((1.5, 1.0), (2.0, 1.0)): addx(mk(f"X_Vd0+alvo{k}x_desloc>={dm}", veto_fn=VD0, ajusta_fn=alvo_k(k, dm)))
addx(mk("X_Vd0+pira0.5atr_d>=1", veto_fn=VD0, maxc=2, pira_fn=pira(0.5, 1.0)))
addx(mk("X_Vd0+T5ult", veto_fn=VD0, teto_fn=teto_din(5, True)))
addx(mk("X_Vd0+T5ult+pira0.5atr_d>=1", veto_fn=VD0, teto_fn=teto_din(5, True), maxc=2, pira_fn=pira(0.5, 1.0)))
addx(mk("X_Vd0+dois_d>=0.5", veto_fn=VD0, dois_fn=dois(0.5)))
addx(mk("X_Vd0+cascata", veto_fn=VD0, cascata=True))
addx(mk("X_Vd0+tudo(T5ult,pira,dois)", veto_fn=VD0, teto_fn=teto_din(5, True), maxc=2, pira_fn=pira(0.5, 1.0), dois_fn=dois(0.5)))

EXTRA3 = {}
def addy(c): EXTRA3[c.nome] = c
addy(mk("Y_Vd0+pira0", veto_fn=VD0, maxc=2, pira_fn=pira(0.0)))
addy(mk("Y_Vd0+T5ult+pira0", veto_fn=VD0, teto_fn=teto_din(5, True), maxc=2, pira_fn=pira(0.0)))
addy(mk("Y_Vd0+T5ult+pira0+dois", veto_fn=VD0, teto_fn=teto_din(5, True), maxc=2, pira_fn=pira(0.0), dois_fn=dois(0.5)))
addy(mk("Y_Vd0+T5ult+pira0.5atr+dois", veto_fn=VD0, teto_fn=teto_din(5, True), maxc=2, pira_fn=pira(0.5), dois_fn=dois(0.5)))
addy(mk("Y_Vd0+T5ult+pira_d>=1+dois+alvo2x", veto_fn=VD0, teto_fn=teto_din(5, True), maxc=2, pira_fn=pira(0.5, 1.0), dois_fn=dois(0.5), ajusta_fn=alvo_k(2.0, 1.0)))

EXTRA4 = {}
def dirv(a, b): return lambda vv, s, est, ctx: not (est["desloc"] >= a and est["ef_dia"] >= b)
for a in (0, 1, 2):
    for b in (0.15, 0.25, 0.35):
        c = mk(f"Z_veto_solto_se_desloc>={a}&ef>={b}", veto_fn=dirv(a, b)); EXTRA4[c.nome] = c
def pirad(a, b):
    def f(abertas, s, est, ctx):
        sg = 1 if s["lado"] == "compra" else -1
        px = float(ctx.hoje.close.iloc[-1])
        return all((px - x.preco) * sg >= 0 for x in abertas) and est["desloc"] >= a and est["ef_dia"] >= b
    return f
def tetod(a, b):
    def f(feitos, ctx):
        if len(feitos) < 3: return 3
        fech = [x for x in feitos if x.t_sai is not None]
        return 5 if saldo(feitos) > 0 and fech and fech[-1].brl > 0 else 3
    return f
for a, b in ((0, 0.25), (1, 0.25), (1, 0.35)):
    c = mk(f"Z_pilha_dir(desloc>={a}&ef>={b})", veto_fn=dirv(a, b), teto_fn=tetod(a, b), maxc=2, pira_fn=pirad(a, b)); EXTRA4[c.nome] = c
CONFIGS.update(EXTRA); CONFIGS.update(EXTRA3); CONFIGS.update(EXTRA4)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "extra":
        main(EXTRA)
    elif len(sys.argv) > 1 and sys.argv[1] == "extra4":
        main(EXTRA4)
    elif len(sys.argv) > 1 and sys.argv[1] == "extra3":
        main(EXTRA3)
    else:
        main()
