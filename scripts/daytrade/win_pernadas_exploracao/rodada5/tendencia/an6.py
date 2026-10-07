import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
R = pd.read_csv("grade_resultado.csv"); R["X"] = R.X.astype(str)
d = R[(R.conv == "cons") & (R.filt == "todos") & (R.stop == 100) & (R.alvo == 750) & (R.X == "150")]
rows = []
for sc in ["-"] + ["i_leg", "i_open", "i_vwap", "i_m15", "i_h1", "d_ma20", "d_wkprev", "d_seq", "conc3", "conc5"]:
    for mode in (["none"] if sc == "-" else ["favor", "contra"]):
        r = {"escala": sc, "modo": mode}
        for per in ("desc", "conf", "set"):
            x = d[(d.scale == sc) & (d["mode"] == mode) & (d.per == per)].iloc[0]
            r[f"n_{per}"] = int(x.n); r[f"ac_{per}"] = round(x.acerto * 100, 1); r[f"esp_{per}"] = round(x.esp, 1)
            r[f"ic_{per}"] = f"[{x.lo:.0f};{x.hi:.0f}]"
        rows.append(r)
print(pd.DataFrame(rows).to_string())
print(d[(d.scale == "i_leg") & (d["mode"] == "favor")][["per", "fill", "be_emp", "nulo", "mpos", "seqperd", "ops_dia", "unres"]])
print(d[(d.scale == "-")][["per", "fill", "be_emp", "nulo", "mpos", "seqperd", "ops_dia", "unres"]])
# quantas celulas favor com lo>0 por periodo
for per in ("desc", "conf", "set"):
    x = R[(R.per == per) & (R.conv == "cons") & (R["mode"] == "favor") & (R.n >= 100)]
    print(per, "favor cons n>=100:", len(x), "esp>0:", (x.esp > 0).sum(), "lo>0:", (x.lo > 0).sum())
    y = R[(R.per == per) & (R.conv == "cons") & (R["mode"] == "contra") & (R.n >= 100)]
    print(per, "contra:", len(y), "esp>0:", (y.esp > 0).sum(), "lo>0:", (y.lo > 0).sum())
    z = R[(R.per == per) & (R.conv == "cons") & (R["mode"] == "none") & (R.n >= 100)]
    print(per, "none:", len(z), "esp>0:", (z.esp > 0).sum(), "lo>0:", (z.lo > 0).sum())
