import json, sys
import pandas as pd
sys.path.insert(0, ".")
import motor, coleta
T = pd.read_json("teto_dias.json").sort_values("falta3", ascending=False).head(10)
R = {r["dia"]: r for r in json.load(open("coleta.json"))}
import base
out = []
for _, row in T.iterrows():
    d = row.dia; r = R[d]
    m1 = base.carrega(d, 0); m1d = m1[m1.index.normalize() == pd.Timestamp(d)]
    fim = m1d.index[m1d["ultima_continua"]].max()
    tempos = list(pd.date_range(m1d.index[0].normalize() + pd.Timedelta(hours=9, minutes=15), fim, freq="15min"))
    ops = sorted(coleta.teto_dia(m1d, fim, tempos), key=lambda x: -x[3])
    b = ops[0]
    t0, ent, sai, pts, lado = b
    # candidatas no lado e janela do melhor trade (sinal em [t0-45min, ent])
    cs = [c for c in r["cands"] if c["lado"] == lado and pd.Timestamp(c["t"]) >= t0 - pd.Timedelta(minutes=45) and pd.Timestamp(c["t"]) <= ent]
    trs = r["trades"]
    sobre = [t for t in trs if t["lado"] == lado and pd.Timestamp(t["ent"]) <= sai and pd.Timestamp(t["t_sai"]) >= ent]
    causas = sorted({c["causa"] for c in cs})
    sim = [round(c["brl"]) for c in cs]
    motivo = ("robo estava no lado certo: " + ", ".join(f'{t["fonte"][:30]} {t["brl"]}R$ ({t["motivo"]})' for t in sobre)) if sobre else \
             (("bloqueado: " + "/".join(causas) + f" (sim isolada {sim})") if cs else "nenhuma regra FAZER sinalizou naquele lado")
    n_fazer = len(r["cands"]) + r["ops"]
    out.append(dict(dia=d, tipo=row.tipo, robo=row.robo, teto3=row.teto3, falta=row.falta3, melhor=f"{lado} sinal {t0.time()} sai {sai.time()} +R${pts*0.2:.0f}", motivo=motivo,
                    trades="; ".join(f'{t["lado"][0]} {t["ent"][11:16]}-{t["t_sai"][11:16]} {t["brl"]}' for t in trs)))
for o in out: print(o)
json.dump(out, open("top10.json", "w"), indent=1, default=str)
