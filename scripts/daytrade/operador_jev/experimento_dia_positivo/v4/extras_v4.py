"""Descritivo extra da v4 (nao pre-registrado, so para entender o resultado): trades por hora de entrada, portao com minimo de velas, breakeven empirico."""
import json
import sys
from pathlib import Path
import numpy as np
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(EXP.parent))
import regras_v4 as rg  # noqa: E402

dias = json.load(open(EXP / "rodada_v4_dias.json", encoding="utf-8"))["dias"]
S4 = {d["data"]: json.loads((EXP / "sessoes_v4/R50/L" / f"{d['data']}.json").read_text(encoding="utf-8")) for d in dias}
S3 = {d["data"]: json.loads((EXP / "sessoes_v3/R50v4/L" / f"{d['data']}.json").read_text(encoding="utf-8")) for d in dias}


def bucket(h):
    return "09:00-09:59" if h < "10:00" else "10:00-11:59" if h < "12:00" else "12:00-14:59" if h < "15:00" else "15:00-17:30"


def tabela(S, nome):
    b = {}
    for s in S.values():
        for t in s["trades"]:
            x = b.setdefault(bucket(t["t_ent"]), [0, 0.0, 0])
            x[0] += 1
            x[1] += t["brl"]
            x[2] += t["brl"] > 0
    print(f"-- {nome}: trades por hora de entrada")
    for k in sorted(b):
        n, tot, w = b[k]
        print(f"   {k}: n {n:>3} | total R$ {tot:+8.0f} | R$/trade {tot / n:+6.1f} | acerto {100 * w / n:4.0f}%")
    tr = [t["brl"] for s in S.values() for t in s["trades"]]
    g = [x for x in tr if x > 0]
    p = [-x for x in tr if x < 0]
    be = np.mean(p) / (np.mean(g) + np.mean(p))
    print(f"   ganho medio R$ {np.mean(g):.1f} | perda media R$ {np.mean(p):.1f} | breakeven empirico {100 * be:.1f}% | acerto {100 * len(g) / len(tr):.1f}% | R$/trade {np.mean(tr):+.2f}")


tabela(S4, "v4")
tabela(S3, "v3 (zerar limitado)")
# intencoes de entrada do Jev (acao comprar/vender com p>=0,3) por n de velas do dia: o portao so tem o que cortar depois das primeiras velas
n_vel = {}
for s in S4.values():
    for p in s["pontos"]:
        inf = p["jev"].get("info", {})
        if inf.get("fase") == "entrada" and inf.get("esc") in ("comprar", "vender") and inf.get("p", 0) >= s["limiar"]:
            k = p["k"] + 1
            c = "1-5 velas (ate ~10:30)" if k <= 5 else "6+ velas"
            x = n_vel.setdefault(c, [0, 0, 0.0])
            x[0] += 1
            x[1] += bool(inf.get("portao_ok"))
            x[2] += inf.get("er", 0)
print("-- intencoes de entrada do Jev (p>=0,3), portao deterministico (er>=0,20 e a favor do lado do dia)")
for c, (n, ok, ers) in n_vel.items():
    print(f"   {c}: {n} intencoes | passam o portao {ok} ({100 * ok / n:.0f}%) | er medio {ers / n:.2f}")
# entradas executadas da v4 com er < 0,15 (portao frouxo), e o que fariam com minimo de 6 velas
print("-- trades v4: er do dia na vela da decisao")
rows = []
for s in S4.values():
    ords = {o["k_dec"]: o for o in s["ordens"] if o.get("fill")}
    tr_by_k = {}
    for t in s["trades"]:
        tr_by_k[t["k_ent"]] = t
    for p in s["pontos"]:
        inf = p["jev"].get("info", {})
        if p["k"] in ords and inf.get("er") is not None:
            o = ords[p["k"]]
            t = next((t for t in s["trades"] if t["k_ent"] >= o["k_dec"] and abs(t["preco_ent"] - o["preco"]) < 1e-9 and t["t_ent"] == o["fill"]["t"]), None)
            if t:
                rows.append((p["k"] + 1, inf["er"], t["brl"]))
rows = np.array(rows)
for lo, hi in ((0, 0.15), (0.15, 0.25), (0.25, 0.4), (0.4, 9)):
    m = (rows[:, 1] >= lo) & (rows[:, 1] < hi)
    print(f"   er [{lo:.2f}, {hi:.2f}): n {int(m.sum()):>3} | total R$ {rows[m, 2].sum():+7.0f}")
m6 = rows[:, 0] >= 6
print(f"   entradas com >= 6 velas no dia: n {int(m6.sum())} total R$ {rows[m6, 2].sum():+.0f} | com < 6 velas: n {int((~m6).sum())} total R$ {rows[~m6, 2].sum():+.0f}")
