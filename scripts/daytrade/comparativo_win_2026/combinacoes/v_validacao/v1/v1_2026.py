"""V1 etapa 1: reproducao COM WdoRetangulo (x/y contra o CSV da frente) e refeito em 2026 SEM WdoRetangulo + filtro do pre-registro.
Uso: python v1_2026.py [C1 C2 ...]   -> trades_2026_sem_wdo/Ck.csv, reproducao_2026.csv, filtro_2026.csv"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd
AQ = Path(__file__).resolve().parent
sys.path.insert(0, str(AQ))
import v1_regras as R
R.init("2026")
votos, eventos, res, dados = R.carrega_ctx("2026")
ids = sys.argv[1:] or list(R.CAND)
(AQ / "trades_2026_sem_wdo").mkdir(exist_ok=True); (AQ / "trades_2026_com_wdo").mkdir(exist_ok=True)
PISO = 841.0


def liq(t): return float((t.rs - R.CUSTO * (t.qtd if "qtd" in t else 1.0)).sum())


def compara(mine, ref):
    ref = ref.copy(); ref["entrada"] = pd.to_datetime(ref.entrada, format="mixed"); ref["saida"] = pd.to_datetime(ref.saida, format="mixed")
    m = mine.merge(ref[["entrada", "saida", "lado", "rs"]], on=["entrada", "saida", "lado"], how="inner", suffixes=("", "_ref"))
    ok = int((np.abs(m.rs - m.rs_ref) < 0.011).sum())
    return ok, len(ref), len(mine)


lin_rep, lin_f = [], []
for cid in ids:
    robo, desc, tipo, arq = R.CAND[cid]
    t0 = time.time()
    tw, _ = R.roda(cid, votos, eventos, res, dados, com_wdo=True)
    ref = pd.read_csv(R.COMB / arq)
    if robo != "ConsensoGatilho" or True:
        ref = ref[ref.estrategia == robo]
    ok, y, nmine = compara(tw, ref)
    tw.to_csv(AQ / "trades_2026_com_wdo" / f"{cid}.csv", index=False)
    print(f"[{cid}] {robo} {desc}: reproducao COM Wdo {ok}/{y} (minhas {nmine}) liq R$2 mine {liq(tw):.1f} ref {liq(ref.assign(qtd=1.0)):.1f}  ({time.time()-t0:.0f}s)", flush=True)
    lin_rep.append(dict(id=cid, robo=robo, regra=desc, iguais=ok, csv=y, minhas=nmine, liq2_minha=round(liq(tw), 2), liq2_csv=round(liq(ref.assign(qtd=1.0)), 2)))
    ts, _ = R.roda(cid, votos, eventos, res, dados, com_wdo=False)
    ts.to_csv(AQ / "trades_2026_sem_wdo" / f"{cid}.csv", index=False)
    l_new = liq(ts)
    if tipo == "nova":
        passa = l_new > PISO; l_o = np.nan; d = np.nan
    else:
        l_o = liq(R.original_janela(res, robo)); d = l_new - l_o; passa = d > 0
    print(f"    SEM Wdo: ops {len(ts)} liq R$2 {l_new:.1f} | original {l_o:.1f} | delta {d:.1f} | {'SEGUE' if passa else 'CAI'}", flush=True)
    lin_f.append(dict(id=cid, robo=robo, regra=desc, tipo=tipo, ops=len(ts), liq2_sem_wdo=round(l_new, 2), liq2_com_wdo=round(liq(tw), 2),
                      liq2_original=round(l_o, 2) if l_o == l_o else None, delta_sem_wdo=round(d, 2) if d == d else None,
                      criterio="liq > 841" if tipo == "nova" else "delta > 0", segue=bool(passa)))
suf = "" if len(sys.argv) == 1 else "_" + "_".join(ids)
pd.DataFrame(lin_rep).to_csv(AQ / f"reproducao_2026{suf}.csv", index=False)
pd.DataFrame(lin_f).to_csv(AQ / f"filtro_2026{suf}.csv", index=False)
