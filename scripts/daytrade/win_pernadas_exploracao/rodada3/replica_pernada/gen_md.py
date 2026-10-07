import pickle, numpy as np
A = pickle.load(open("agg.pkl", "rb")); R17 = pickle.load(open("r17.pkl", "rb")); AUC = pickle.load(open("auc.pkl", "rb"))
R19 = pickle.load(open("r19.pkl", "rb")); R2 = pickle.load(open("r25_r26.pkl", "rb"))
MES = ["01", "02", "03", "04", "05", "06", "07", "08"]; NM = dict(zip(MES, "jan fev mar abr mai jun jul ago".split()))
def f(x, d=1, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)): return "-"
    if pct: x = x * 100
    return ("%." + str(d) + "f") % x if False else (("%." + str(d) + "f") % x).replace(".", ",")
HDR = "| " + " | ".join(["métrica"] + [NM[m] + "/26" for m in MES] + ["jan–ago [IC95 dias]", "set/26"]) + " |\n|" + "---|" * 11 + "\n"
def linha(nome, fn):
    return "| " + nome + " | " + " | ".join(fn(m) for m in MES + ["jan-ago", "09"]) + " |\n"
def rate(k, d=1):
    def fn(m):
        x = A[m][k]
        s = f(x["real"], d, True)
        if m == "jan-ago": s += " [%s;%s]" % (f(x["ic"][0], d, True), f(x["ic"][1], d, True))
        return s
    return fn
def nulo(k, d=1, pct=True):
    def fn(m):
        x = A[m][k]; return f(x["nulo"], d, pct) + (" [%s;%s]" % (f(x["p5"], d, pct), f(x["p95"], d, pct)) if m == "jan-ago" else "")
    return fn
def z(k):
    return lambda m: f((A[m][k]["real"] - A[m][k]["nulo"]) / A[m][k]["sd"], 1) if A[m][k]["sd"] else "-"
out = []
out.append("### R13 — a pernada seguinte passa do início da anterior\n\n" + HDR +
    linha("real %", rate("R13")) + linha("nulo (blocos 30 min) %", nulo("R13")) + linha("z real−nulo", z("R13")) +
    linha("n pares", lambda m: str(int(A[m]["n"]["n_R13"]))))
out.append("\n### R14 — P(recuo de X chegar a 750 antes de novo extremo | alta ≥ 750), eventos de topo e fundo\n\n" + HDR)
for X in (150, 250, 375, 500):
    k = f"R14_{X}"
    out.append(linha(f"X={X} real %", rate(k)) + linha(f"X={X} nulo %", nulo(k)) + linha(f"X={X} z", z(k)))
out.append(linha("n eventos X=250", lambda m: str(int(A[m]["n"]["n_R14_250"]))))
out.append("\n### R16 — correlação do log do tamanho da pernada n com a n+1\n\n" + HDR + linha("real", rate("R16", 2).__call__ if False else (lambda m: f(A[m]["R16"]["real"], 2) + (" [%s;%s]" % (f(A[m]["R16"]["ic"][0], 2), f(A[m]["R16"]["ic"][1], 2)) if m == "jan-ago" else ""))) +
    linha("nulo", lambda m: f(A[m]["R16"]["nulo"], 2) + (" [%s;%s]" % (f(A[m]["R16"]["p5"], 2), f(A[m]["R16"]["p95"], 2)) if m == "jan-ago" else "")))
out.append("\n### R17 — alta × baixa (pernadas fechadas sem a 1ª do dia; razão alta/baixa das medianas; virada X=250 topo menos fundo em pp)\n\n" + HDR)
def r17f(key, ratio=True, d=2):
    def fn(m):
        r = R17[m]; a, b = r[key]
        s = f(a / b, d) if ratio else f((a - b) * 100, 1)
        if m == "jan-ago": s += " [%s;%s]" % ((f(r["ic"][key][0], d), f(r["ic"][key][1], d)) if ratio else (f(r["ic"][key][0] * 100, 1), f(r["ic"][key][1] * 100, 1)))
        return s
    return fn
out.append(linha("tamanho (alta/baixa)", r17f("tam")) + linha("velocidade pts/min", r17f("vel")) + linha("correção máx.", r17f("corr")) +
           linha("P(vira) topo−fundo, pp", r17f("vira", False)) + linha("n pernadas alta/baixa", lambda m: "%d/%d" % R17[m]["n"]))
FEATN = {"ema_cruz": "cruzamento EMA9/21 (contra a perna)", "ema_dist": "distância à EMA21", "rsi": "RSI14", "rsi_div": "divergência de RSI", "vwap_dist": "distância do extremo ao VWAP (ATR M5)",
         "vol_ult": "volume do último minuto vs perna", "vol_pre": "volume do minuto pré-extremo", "corpo": "corpo da vela do extremo", "pavio": "pavio do extremo", "vel": "velocidade da perna", "fluxo": "fluxo agressor da perna (regra do tick)", "fluxo_real": "fluxo agressor da perna (flags reais WINV26, 12–31/ago + set)"}
def auc_tab(X, feats):
    s = HDR.replace("métrica", "AUC (X=%d)" % X)
    for nm in feats:
        def fn(m, nm=nm):
            t = AUC[(X, m, nm)]; a = t[0]
            if m == "jan-ago": return f(a, 3) + " [%s;%s] p=%s" % (f(t[3], 3), f(t[4], 3), f(t[1], 2))
            if m == "09": return f(a, 3) + " p=%s" % f(t[1], 2)
            return f(a, 3)
        s += linha(FEATN[nm], fn)
    s += linha("n eventos", lambda m: str(AUC[(X, m, feats[0])][2]))
    return s
F15 = ["ema_cruz", "ema_dist", "rsi", "rsi_div", "vwap_dist", "vol_ult", "vol_pre", "corpo", "pavio", "vel"]
out.append("\n### R15 — indicadores no momento do recuo vs virada (AUC estratificado hora × tamanho; 0,50 = nada)\n\n" + auc_tab(250, F15) + "\n" + auc_tab(500, F15))
out.append("\n### R18 — fluxo agressor a favor da pernada vs virada\n\n" + auc_tab(250, ["fluxo", "fluxo_real"]) + "\n" + auc_tab(500, ["fluxo", "fluxo_real"]))
out.append("\n### R19 — extremo esticado do VWAP vira mais?\n\n" + auc_tab(250, ["vwap_dist"]))
out.append("\n" + HDR.replace("métrica", "P(vira), X=250") + linha("dist > 1,5 ATR M5 %", lambda m: f(R19[(250, m)]["p_hi"], 1, True) + " (n=%d)" % R19[(250, m)]["n_hi"]) + linha("dist ≤ 1,5 ATR %", lambda m: f(R19[(250, m)]["p_lo"], 1, True) + " (n=%d)" % R19[(250, m)]["n_lo"]) +
           linha("mediana dist, vira", lambda m: f(R19[(250, m)]["med_vira"], 2)) + linha("mediana dist, segue", lambda m: f(R19[(250, m)]["med_segue"], 2)))
out.append("\n### R25 — Spearman(volume relativo da vela anterior ao início, tamanho da pernada)\n\n" + HDR)
for tf in ("M5", "M15"):
    out.append(linha("rho " + tf, lambda m, tf=tf: f(R2["R25"][(tf, m)]["rho"], 2) + (" [%s;%s]" % (f(R2["R25"][(tf, m)]["ic"][0], 2), f(R2["R25"][(tf, m)]["ic"][1], 2)) if m == "jan-ago" else "")))
    out.append(linha("n / sd do nulo " + tf, lambda m, tf=tf: "%d / %s" % (R2["R25"][(tf, m)]["n"], f(R2["R25"][(tf, m)]["nulo_sd"], 2))))
out.append("\n### R26 — dólar (WDO) × WIN\n\n" + HDR + linha("pernadas do WIN com WDO em sentido oposto, real %", rate("R26_opp")) + linha("idem, nulo (mesma permutação nos dois) %", nulo("R26_opp")) +
           linha("n pernadas", lambda m: str(int(A[m]["n"]["n_R26"]))))
out.append("\n" + HDR.replace("métrica", "corr. de retornos M1") )
for k, nm in ((0, "lag 0 (mesmo minuto)"), (1, "WDO lidera 1 min"), (2, "WDO lidera 2 min"), (-1, "WIN lidera 1 min"), (-2, "WIN lidera 2 min")):
    out.append(linha(nm, lambda m, k=k: f(R2["R26"][m]["corr"][k], 3) + (" [%s;%s]" % (f(R2["R26"][m]["ic"][k][0], 3), f(R2["R26"][m]["ic"][k][1], 3)) if m == "jan-ago" else "")))
out.append("\n### Base — dentro da pernada = acaso\n\n" + HDR + linha("pernadas/dia real", lambda m: f(A[m]["legs_dia"]["real"], 1) + (" [%s;%s]" % (f(A[m]["legs_dia"]["ic"][0], 1), f(A[m]["legs_dia"]["ic"][1], 1)) if m == "jan-ago" else "")) +
    linha("pernadas/dia nulo", lambda m: f(A[m]["legs_dia"]["nulo"], 1) + (" [%s;%s]" % (f(A[m]["legs_dia"]["p5"], 1), f(A[m]["legs_dia"]["p95"], 1)) if m == "jan-ago" else "")) +
    linha("correções/perna real", lambda m: f(A[m]["corr_perna"]["real"], 2) + (" [%s;%s]" % (f(A[m]["corr_perna"]["ic"][0], 2), f(A[m]["corr_perna"]["ic"][1], 2)) if m == "jan-ago" else "")) +
    linha("correções/perna nulo", lambda m: f(A[m]["corr_perna"]["nulo"], 2) + (" [%s;%s]" % (f(A[m]["corr_perna"]["p5"], 2), f(A[m]["corr_perna"]["p95"], 2)) if m == "jan-ago" else "")) +
    linha("dias", lambda m: str(A[m]["dias"])))
open("tabelas.md", "w", encoding="utf-8").write("".join(out))
print("ok")
