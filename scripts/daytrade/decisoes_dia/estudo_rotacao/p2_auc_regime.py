"""Passo 2: quao bem estimativas CAUSAIS (so ctx ate a hora H) separam o dia que terminara em rotacao (ef do dia inteiro < 0,15).
Orientacao de cada feature = common.SINAL (declarada antes). Sem limiar ajustado: limiar = MEDIANA da feature no calendario IS (937 pregoes), por hora.
Populacoes: (A) calendario IS completo (937 pregoes, so mercado; sem rodar robo) e (B) os 90 dias do estudo (amostra estratificada, nao e o calendario)."""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
from concurrent.futures import ProcessPoolExecutor, as_completed
HORAS = [10, 11, 12, 13]

def um(dia):
    out = {}
    for t, ctx in base.contextos(dia):
        if t.hour in HORAS and t.minute == 0:
            out[t.hour] = feats(ctx)
    return dia, out

def auc(score, y):  # P(score_rot > score_nao_rot), score ja orientado (maior => rotacao)
    s = pd.Series(score); r = s.rank(); n1 = y.sum(); n0 = len(y) - n1
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

if __name__ == "__main__":
    dias_is = sorted(EF.keys())
    res = {}
    with ProcessPoolExecutor(5) as ex:
        fut = [ex.submit(um, d) for d in dias_is]
        for i, f in enumerate(as_completed(fut)):
            d, o = f.result(); res[d] = o
            if i % 100 == 0: print(f"  {i}/{len(dias_is)}", flush=True)
    json.dump(res, open(ER / "p2_feats.json", "w"))
    y_all = {d: EF[d] < 0.15 for d in dias_is}
    med = {}; linhas = []
    feats_nome = list(SINAL)
    for H in HORAS:
        med[H] = {}
        dd = [d for d in dias_is if H in res[d]]
        df = pd.DataFrame({d: res[d][H] for d in dd}).T
        y = np.array([y_all[d] for d in dd])
        for k in feats_nome: med[H][k] = float(df[k].median())
        # votos: 4 features principais, orientadas (declarado antes: ef_parc, amp_atrd, cruz_vwap, sobrep)
        def votos(df):
            v = 0
            for k in ("ef_parc", "amp_atrd", "cruz_vwap", "sobrep"):
                v = v + ((df[k] >= med[H][k]) if SINAL[k] > 0 else (df[k] <= med[H][k])).astype(int)
            return v
        for pop, sel in (("IS937", np.ones(len(dd), bool)), ("90d", np.array([d in set(DIAS) for d in dd]))):
            d2 = df[sel]; y2 = y[sel]
            for k in feats_nome:
                sc = d2[k].astype(float) * SINAL[k]
                m = sc.notna().values
                a = auc(sc.values[m], y2[m])
                lim = med[H][k]; pred = (d2[k] >= lim) if SINAL[k] > 0 else (d2[k] <= lim)
                ac = float((pred.values == y2).mean())
                linhas.append(dict(pop=pop, H=H, feat=k, auc=a, acerto_mediana=ac, n=int(m.sum()), base_rot=float(y2.mean())))
            v = votos(d2); a = auc(v.values.astype(float), y2)
            pred = v >= 3
            linhas.append(dict(pop=pop, H=H, feat="voto>=3de4", auc=a, acerto_mediana=float((pred.values == y2).mean()), n=len(y2), base_rot=float(y2.mean())))
    json.dump(dict(medianas=med, linhas=linhas), open(ER / "p2_resultado.json", "w"), indent=1)
    for pop in ("IS937", "90d"):
        print(f"\n== {pop}: AUC (acerto no limiar=mediana) por hora; base_rot = fracao de dias rotacao", flush=True)
        L = [l for l in linhas if l["pop"] == pop]
        print("feature".ljust(14) + "".join(f"| {H}:00 AUC  acerto " for H in HORAS))
        for k in feats_nome + ["voto>=3de4"]:
            print(k.ljust(14) + "".join(f"| {[l for l in L if l['H']==H and l['feat']==k][0]['auc']:.3f}   {[l for l in L if l['H']==H and l['feat']==k][0]['acerto_mediana']*100:4.0f}%   " for H in HORAS), flush=True)
        print("base rot".ljust(14) + "".join(f"| {[l for l in L if l['H']==H][0]['base_rot']*100:.0f}%  n={[l for l in L if l['H']==H][0]['n']}   " for H in HORAS))
