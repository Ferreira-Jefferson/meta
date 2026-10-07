"""Passo 4: interacao com filtros (cedo / vela) e Kelly/ruina da melhor celula congelada."""
import sys, json
import numpy as np, pandas as pd
import run
from base import *
sys.path.insert(0, "C:/Users/Jeffe/Documents/study/meta/scripts/daytrade/win_pernadas_exploracao/rodada4/decisao")
import motor
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 400)

R = pd.read_csv("grade_resultado.csv"); R["X"] = R.X.astype(str)
ref = R[(R.conv == "cons") & (R.stop.isin([100, 150])) & (R.alvo.isin([750, 1000]))]
rows = []
for per in ("desc", "conf", "set"):
    for filt in ("todos", "cedo", "vela"):
        d = ref[(ref.per == per) & (ref.filt == filt)]
        none = d[d["mode"] == "none"]
        for sc in ["i_leg", "i_open", "i_vwap", "i_m15", "i_h1", "d_ma20", "d_wkprev", "conc3", "conc5"]:
            f = d[(d.scale == sc) & (d["mode"] == "favor")]; c = d[(d.scale == sc) & (d["mode"] == "contra")]
            w = lambda x: (x.acerto * x.n).sum() / x.n.sum() * 100
            e = lambda x: (x.esp * x.n).sum() / x.n.sum()
            rows.append(dict(per=per, filt=filt, escala=sc, ac_favor=w(f), ac_contra=w(c), ac_nenhum=w(none), dif_pp=w(f) - w(c),
                             esp_favor=e(f), esp_contra=e(c), esp_nenhum=e(none), n_favor=f.n.sum(), n_contra=c.n.sum(), n_nenhum=none.n.sum(),
                             pct_pos_favor=(f.esp > 0).mean() * 100))
T = pd.DataFrame(rows); T.to_csv("filtros_interacao.csv", index=False)
for per in ("desc", "conf", "set"):
    print("\n==", per); print(T[T.per == per].drop(columns="per").round(1).to_string())

# ---- Kelly e ruina da melhor celula congelada (1a do arquivo = maior esperanca na descoberta) e da unica que segurou
fro = json.load(open("congelado_ANTES_da_confirmacao.json"))["celulas"]
run.init()
for f in (fro[0], fro[-1]):
    X = f["X"] if f["X"] == "mm" else int(f["X"])
    dia, pnl, tip, ordens = run.trades(f["scale"], f["mode"], f["filt"], X, f["stop"], f["alvo"], True)
    days = run._G["days"]
    m = (days[dia] >= "2026.01.01") & (days[dia] <= "2026.08.31")
    p = pnl[m]; k = tip[m]
    n = len(p); res = k != 2; w = int((k == 1).sum()); nr = int(res.sum())
    gan = f["alvo"] - 2; per = f["stop"] + 5 + 2
    pb = f["stop"] / (f["alvo"] + f["stop"])
    ph = w / nr
    pe = motor.p_encolhido(w, nr, pb, 100)
    print("\nCELULA", f, "jan-ago n", n, "acerto %.3f nulo %.3f BE %.3f esp %.1f pts" % (ph, pb, motor.breakeven_p(gan, per), p.mean()))
    print(" p_encolhido(n0=100) %.3f; edge encolhido %.1f pts; tamanho(R$250) = %d contratos; tamanho(R$1000)= %d" % (
        pe, motor.esperanca(pe, gan, per), motor.tamanho(pe, gan, per, 250.0), motor.tamanho(pe, gan, per, 1000.0)))
    brl = p * 0.2
    print(" perda de 1 contrato R$ %.2f (%.1f%% de R$250); ganho R$ %.2f" % (per * .2, per * .2 / 250 * 100, gan * .2))
    for dias_ops in (len(p),):
        mc = motor.ruina_mc(brl, None, 250.0, n_ops=len(p), n_caminhos=4000)
        print(" ruina MC 1 contrato, R$250, %d ops (jan-ago, 8 meses): P(ruina)=%.1f%%, caixa final mediana R$%.0f, t mediano %.0f ops" % (
            len(p), mc["p_ruina"] * 100, mc["caixa_final_mediana"], mc["t_mediano"]))
    # sequencia de perdas esperada: P(perda)=1-ph (resolvidas); sequencia esperada em n ops ~ log(n)/-log(1-ph)
    q = 1 - ph
    print(" sequencia esperada de perdas em %d ops ~ %.0f (observada %d)" % (n, np.log(n) / -np.log(q), run_seq if (run_seq := max([len(s) for s in ''.join('L' if x < 0 else 'W' for x in p).split('W')])) else 0))
    # com p verdadeiro = BE exato (sem edge)
    print(" Lundberg ruina (esp>0?):", motor.ruina_formula(brl, None, 250.0))
