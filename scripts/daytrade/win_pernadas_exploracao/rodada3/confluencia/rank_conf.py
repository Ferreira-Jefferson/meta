import pickle, json, numpy as np, an
fz=json.load(open("frozen.json"))
cfg,res=pickle.load(open("conf.pkl","rb"))
rows={r["key"]:r for r in an.summarize(res["obs"],res["shift"],res["shuf"])}
for c in fz["configs"]:
    r=rows[tuple(c)]
    print(c, "n",r["n"],"B250 obs %.3f nulo %.3f nulo_shuf %.3f z %+.1f zshuf %+.1f jul/ago %+.3f %+.3f | B150 %.3f/%.3f B400 %.3f/%.3f S250 %.3f/%.3f PL %.3f/%.3f"%(r["ro"][1],r["mu"][1],r["mus"][1],r["z"][1],r["zs"][1],r["halves"][0],r["halves"][1],r["ro"][0],r["mu"][0],r["ro"][2],r["mu"][2],r["ro"][4],r["mu"][4],r["ro"][6],r["mu"][6]))
