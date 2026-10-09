"""Passo 3: usos do estado causal de rotacao, medidos sobre o robo_v4 nos 90 dias (motor ciclo4/cfg4.py + filtros).

DECLARADO ANTES DE VER QUALQUER EFEITO NO ROBO (os limiares vem so de p2_resultado.json = medianas das features no calendario IS, por hora):
  Estado causal "rotacao" na decisao t (hora cheia H = max(10,11,12,13 <= t.hour); antes das 10:00 => estado = nao-rotacao):
    E1 = ef_parcial(t) <= mediana_H           (1 feature)
    E2 = voto>=3 de 4: ef_parcial<=med, amp/ATRd<=med, cruzamentos VWAP>=med, sobreposicao>=med
    OR = oraculo (ef do dia inteiro < 0,15) -- NAO CAUSAL, so teto de referencia
  (a) vetar FAZER no estado:  a1 = fontes {n_rot>=2, R$rot<0, R$fora>0 na tabela do passo 1}; a2 = {R$rot<0 e R$fora>=0, n_rot>=1}; a3 = vetar TODA entrada
  (b) b1 = 1 contrato no estado; b2 = alvo x0,5 (distancia ao alvo) no estado
  (c) c1 = no estado, para o dia apos 1o trade perdedor; c2 = no estado, para apos 2 ops; c3 = (sem estado) para apos 1o perdedor; c4 = no estado, para se P&L do dia <= -R$100
  (d) d1 = fade do extremo da faixa do dia (pos>=0,85/<=0,15, faixa>=4 ATR15, 10:30-15:30), alvo = meio da faixa, stop = extremo +-0,5 ATR15, 1 contrato, exige recompensa>=risco
      d2 = falha de rompimento: a vela fechada anterior rompeu max/min do dia ate entao e a atual fechou de volta dentro; alvo = meio da faixa, stop = extremo da falha +-0,5 ATR15
      (d so dispara no estado; entra na lista FAZER do v4 como regra extra, sujeita aos vetos/conflito do motor)
  Parametros acima nao foram ajustados em nenhum resultado."""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
from concurrent.futures import ProcessPoolExecutor, as_completed

P2 = json.load(open(ER / "p2_resultado.json"))
MED = {int(k): v for k, v in P2["medianas"].items()}
P1 = json.load(open(ER / "p1_fontes.json"))
A1 = {f["fonte"] for f in P1 if f["n_rot"] >= 2 and f["brl_rot"] < 0 and f["brl_fora"] > 0}
A2 = {f["fonte"] for f in P1 if f["n_rot"] >= 1 and f["brl_rot"] < 0 and f["brl_fora"] >= 0}
FONTES_FAZER = None  # preenchido por conj. de nomes (a3 veta tudo)


def estado(ctx, modo, dia=None):
    if modo == "OR": return EF[str(ctx.t.date())] < 0.15
    H = max([h for h in (10, 11, 12, 13) if h <= ctx.t.hour], default=None)
    if H is None: return False
    f = feats(ctx); m = MED[H]
    if modo == "E1": return f["ef_parc"] <= m["ef_parc"]
    v = (f["ef_parc"] <= m["ef_parc"]) + (f["amp_atrd"] <= m["amp_atrd"]) + (f["cruz_vwap"] >= m["cruz_vwap"]) + (f["sobrep"] >= m["sobrep"])
    return v >= 3


def filtro_post(uso, modo):
    def filtro(n, s, ctx):
        rot = estado(ctx, modo)
        if uso == "a1": return None if (rot and n in A1) else s
        if uso == "a2": return None if (rot and n in A2) else s
        if uso == "a3": return None if rot else s
        if uso == "b1":
            if rot: s = dict(s); s["contratos"] = 1
            return s
        if uso == "b2":
            if rot and s.get("alvo") is not None:
                p = float(s.get("preco", ctx.hoje.close.iloc[-1])); s = dict(s); s["alvo"] = p + 0.5 * (float(s["alvo"]) - p)
            return s
        ops = ctx.ops_hoje
        if uso == "c1": return None if (rot and any(x.brl < 0 for x in ops)) else s
        if uso == "c2": return None if (rot and len(ops) >= 2) else s
        if uso == "c3": return None if any(x.brl < 0 for x in ops) else s
        if uso == "c4": return None if (rot and sum(x.brl for x in ops) <= -100) else s
        return s
    return filtro


def _rd(modo):
    def regra(ctx, tipo):
        h = ctx.hoje
        hm = ctx.t.hour * 60 + ctx.t.minute
        if len(h) < 4 or hm < 10 * 60 + 30 or hm > 15 * 60 + 30: return None
        if not estado(ctx, modo): return None
        a = ctx.atr15
        if tipo == "d1":
            hi, lo = float(h.high.max()), float(h.low.min()); c = float(h.close.iloc[-1])
            if hi - lo < 4 * a: return None
            pos = (c - lo) / (hi - lo); mid = (hi + lo) / 2
            if pos >= 0.85: lado, stop, alvo = "venda", hi + 0.5 * a, mid
            elif pos <= 0.15: lado, stop, alvo = "compra", lo - 0.5 * a, mid
            else: return None
        else:
            hp = h.iloc[:-2]; ult, pen = h.iloc[-1], h.iloc[-2]
            hi, lo = float(hp.high.max()), float(hp.low.min()); mid = (hi + lo) / 2
            if hi - lo < 4 * a: return None
            if pen.high > hi and ult.close < hi: lado, stop, alvo = "venda", float(max(pen.high, ult.high)) + 0.5 * a, mid
            elif pen.low < lo and ult.close > lo: lado, stop, alvo = "compra", float(min(pen.low, ult.low)) - 0.5 * a, mid
            else: return None
        c = float(h.close.iloc[-1]); sg = 1 if lado == "compra" else -1
        risco, rec = sg * (c - stop), sg * (alvo - c)
        if risco <= 0 or rec < risco or risco > 600: return None
        return dict(lado=lado, stop=stop, alvo=alvo, contratos=1)
    return regra


def monta_uso(spec):
    uso, modo = spec
    cfg = cfg4.monta(robo_v4.IDS)
    if uso in ("d1", "d2"):
        r = _rd(modo)
        cfg.fz = cfg.fz + [(f"X:{uso}", (lambda ctx, u=uso, rr=r: rr(ctx, u)), None)]
        return cfg
    if uso == "base": return cfg
    flt = filtro_post(uso, modo)
    def envolve(n, r):
        def r2(ctx):
            s = r(ctx)
            if s and "erro" not in s: return flt(n, s, ctx)
            return s
        return r2
    cfg.prio = [(n, envolve(n, r), g) for n, r, g in cfg.prio]
    cfg.post = cfg.post + [lambda n, s, g, ctx, f=flt: (f(n, s, ctx), g)]
    return cfg


def _um(a):
    spec, dia = a
    return spec, dia, cfg4.resultado_dia(dia, monta_uso(spec))


SPECS = [("base", "-")] + [(u, m) for u in ("a1", "a2", "a3", "b1", "b2", "c1", "c2", "c4", "d1", "d2") for m in ("E1", "E2", "OR")] + [("c3", "-")]

if __name__ == "__main__":
    args = [(s, d) for s in SPECS for d in DIAS]
    res = {}; pend = {s: len(DIAS) for s in SPECS}
    with ProcessPoolExecutor(5) as ex:
        for f in as_completed([ex.submit(_um, a) for a in args]):
            s, d, r = f.result(); res.setdefault(s, {})[d] = r; pend[s] -= 1
            if pend[s] == 0: print("  pronto", s, flush=True)
    json.dump({f"{s[0]}|{s[1]}": v for s, v in res.items()}, open(ER / "p3_res.json", "w"))
    V = {s: np.array([res[s][d]["brl"] for d in DIAS]) for s in SPECS}
    vb = V[("base", "-")]
    print(f"\nA1 = {sorted(A1)}\nA2 = {sorted(A2)}\n", flush=True)
    print("uso|estado | total | rep | d_rep | d_nd/dia | d_rot/dia | d_40 R$ | d_40/dia | piores/melhores | pior dia | LOO min | neg dias | trades")
    rows = []
    for s in SPECS:
        v = V[s]; l = linha(v, vb); d = v - vb
        nt = sum(len(res[s][x]["trades"]) for x in DIAS)
        l.update(uso=s[0], estado=s[1], d_rot=float(d[EST3 == "rot"].mean()), trades=nt); rows.append(l)
        print(f"{s[0]}|{s[1]} | {l['total']:.0f} | {l['rep']:.2f} | {l['d_rep']:+.2f} | {l['d_nd']:+.2f} | {l['d_rot']:+.2f} | {l['d_40']:+.0f} | {l['d_40_dia']:+.2f} | {l['pior']}/{l['melhor']} | {l['pior_dia']:.0f} | {l['lodo_min']:+.2f} | {l['neg']} | {nt}", flush=True)
    json.dump(rows, open(ER / "p3_resumo.json", "w"), indent=1)
