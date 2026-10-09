import sys, numpy as np, pandas as pd
from bq_core import bancoC, dados
import catalogo as K, soma, estrategia, escada, operacao, stop, indicadores as ind
from medir import sides
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
W = pd.read_pickle("pesos_sets.pkl")["W"]
SETS = {"A": list(W)[0], "B": list(W)[1], "C": list(W)[2], "L": list(W)[4]}
PER = ("IS", "OOS", "virgem")
Sc = {k: {p: soma.score(p, *W[n]) for p in PER} for k, n in SETS.items()}   # (n,2) por periodo
BARS = {p: dados.m15(p) for p in PER}

def painel(tr, b):
    d = bancoC.painel(tr, b)
    return dict(ops=d["ops"], total_R=d["total"] * .2, pior_queda_R=d["dd"] * .2, recup=d["recup"], fl=d["fl"], acerto=d["acerto"],
                pior_mes_R=d["pior_mes"] * .2, meses_pos=d["meses_pos"], sharpe=d["sharpe"])

def prep(per):
    b = BARS[per].copy(); b["mme38"] = ind.mme(b.close, stop.MME_APERTO); dias = escada.pregoes(b)
    raw = escada.sinais(dias); ok = pd.Series(True, index=raw.index)
    for f in estrategia.FILTROS: ok &= f(b, raw)
    return b, dias, raw, raw[ok].sort_values(["seg", "t0"]).reset_index(drop=True)
PR = {p: prep(p) for p in PER}
def esc(s_, p, k): return Sc[k][p][s_.pos.to_numpy(), np.where(s_.lado.to_numpy() == 1, 0, 1)]

# ---------------- (a) escada
print("\n##### (a) ESCADA v4.1 com pesos")
rows = {}
for k in ("A", "B", "L"):
    med = np.median(esc(PR["IS"][3], "IS", k)); print(f"[{k}] mediana IS dos pesos nos sinais v4.1 = {med:.3f}")
    for p in PER:
        b, dias, raw, s = PR[p]
        sc = esc(s, p, k)
        base = operacao.operar(s, dias, stop.inicial_v41, stop.estrutura)
        filt = operacao.operar(s[sc >= med].reset_index(drop=True), dias, stop.inicial_v41, stop.estrutura)
        mao = base.copy()
        scb = Sc[k][p][mao.pos.to_numpy(), np.where(mao.lado.to_numpy() == 1, 0, 1)]
        mao["pts"] = np.where(scb >= med, mao.pts, mao.pts * 0.5)
        if k == "A": rows[(p, "base")] = painel(base, b)
        rows[(p, f"{k} filtro >=mediana")] = painel(filt, b); rows[(p, f"{k} mão 2/1")] = painel(mao, b)
T4a = pd.DataFrame(rows).T.round(2); print(T4a.to_string()); T4a.to_pickle("t4a.pkl")

# ---------------- (b) estrategia pura de pesos
print("\n##### (b) ESTRATEGIA PURA DE PESOS (limitada no fechamento, stop 1 ATR M15, alvo +1 ATR limitada, fim do dia)")
def sim_pura(b, S, thr, sel=None):
    O, H, L, C, A = (b[c].to_numpy() for c in ("open", "high", "low", "close", "atr")); d = b.dia.to_numpy()
    mins = (b.index.hour * 60 + b.index.minute).to_numpy(); n = len(b)
    seg = np.r_[0, np.where(d[1:] != d[:-1])[0] + 1, n]; out = []
    for s0, e0 in zip(seg[:-1], seg[1:]):
        i = s0
        while i < e0 - 1:
            ok = 570 <= mins[i] <= 1005 and np.isfinite(A[i]) and A[i] > 0
            sb, ss = S[i]
            if not ok or max(sb, ss) < thr or sb == ss: i += 1; continue
            lado = 1 if sb > ss else -1; lim = C[i]; stp = lim - lado * A[i]; tgt = lim + lado * A[i]
            ent = None
            for t in range(i + 1, min(i + 1 + operacao.VALIDADE, e0)):
                tocou = (L[t] <= stp) if lado == 1 else (H[t] >= stp)
                if tocou or ((L[t] <= lim - operacao.FURA) if lado == 1 else (H[t] >= lim + operacao.FURA)):
                    ent = (t, min(O[t], lim) if lado == 1 else max(O[t], lim)); break
            if ent is None: i += 1; continue
            te, px = ent
            if (px - stp) * lado <= 0: i += 1; continue
            saida, ts = C[e0 - 1], e0 - 1
            for t in range(te, e0):
                ot = px if t == te else O[t]
                if (L[t] <= stp) if lado == 1 else (H[t] >= stp): saida, ts = (min(ot, stp) if lado == 1 else max(ot, stp)), t; break
                if (H[t] >= tgt + operacao.FURA) if lado == 1 else (L[t] <= tgt - operacao.FURA): saida, ts = tgt, t; break
            out.append(dict(dia=pd.Timestamp(d[s0]), lado=lado, pts=(saida - px) * lado - operacao.CUSTO))
            i = ts + 1
    return pd.DataFrame(out)
rows = {}; rng = np.random.default_rng(7)
for k in ("A", "B", "L", "C"):
    thr = np.percentile(Sc[k]["IS"][soma.Z["IS"]["elig"]].reshape(-1), 90)
    for p in ("OOS", "virgem", "IS"):
        tr = sim_pura(BARS[p], Sc[k][p], thr); rows[(p, f"{k} pura topo-decil")] = painel(tr, BARS[p])
for p in ("OOS", "virgem"):
    tots = []; ops = []
    for r in range(60):
        tr = sim_pura(BARS[p], rng.random((len(BARS[p]), 2)), 0.9); tots.append(tr.pts.sum() * .2); ops.append(len(tr))
    rows[(p, "nulo: velas aleatórias 10% (média de 60)")] = dict(ops=np.mean(ops), total_R=np.mean(tots), pior_queda_R=np.std(tots))
T4b = pd.DataFrame(rows).T.round(2); print(T4b.to_string()); T4b.to_pickle("t4b.pkl")
print("(linha nulo: pior_queda_R = desvio-padrão do total entre as 60 sorteios)")
