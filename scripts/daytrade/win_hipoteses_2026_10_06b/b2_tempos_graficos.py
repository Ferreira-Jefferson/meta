"""b2 — tempos graficos (so 2026). TTL_BARRAS e' constante de modulo lida em tempo de chamada:
setamos wcm.TTL_BARRAS no processo (sem editar o arquivo base)."""
import sys, io, contextlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import win_cinco_medias as wcm

TFS = {"1min": 1, "2min": 2, "3min": 3, "5min": 5, "10min": 10, "15min": 15, "30min": 30}
BASE = (9, 21, 34, 100, 200)

def escala(m):
    f = 5 / m
    return tuple(max(1, int(round(p * f))) for p in BASE)

def variantes():
    v = []
    for tf, m in TFS.items():
        for modo in ("a_mesmos", "b_horizonte"):
            per = BASE if modo == "a_mesmos" else escala(m)
            es = 21 if modo == "a_mesmos" else per[1]
            for ttlmod in ("ttl5barras", "ttl25min"):
                ttl = 5 if ttlmod == "ttl5barras" else max(1, round(25 / m))
                v.append(dict(tf=tf, modo=modo, per=per, es=es, ttlmod=ttlmod, ttl=ttl))
    seen, out = set(), []
    for x in v:
        k = (x["tf"], x["per"], x["es"], x["ttl"])
        if k not in seen:
            seen.add(k); out.append(x)
    return out

def roda(x):
    wcm.TTL_BARRAS = x["ttl"]
    df, r = wcm.rodar_janelas(2026, x["tf"], periodos=x["per"], ema_saida=x["es"])
    return x, df, r

def main():
    vs = variantes()
    print(f"{len(vs)} variantes", flush=True)
    wcm.TTL_BARRAS = 5
    _, base = wcm.rodar_janelas(2026, "5min")[::-1][0:1][0], None
    bdf, br = wcm.rodar_janelas(2026, "5min")
    print("BASELINE", br, flush=True)
    bmap = dict(zip(bdf.janela, bdf.liquido))
    res = []
    with ProcessPoolExecutor(max_workers=5) as ex:
        fs = [ex.submit(roda, x) for x in vs]
        for f in as_completed(fs):
            x, df, r = f.result()
            melhora = sum(1 for j, l in zip(df.janela, df.liquido) if l > bmap.get(j, -1e9))
            r["melhora_meses"] = f"{melhora}/{len(df)}"
            res.append((x, r))
            print(f"{x['tf']:>5} {x['modo']:<11} ttl={x['ttl']:>2} per={x['per']} es={x['es']} | liq {r['liquido']:>9.2f} | "
                  f"+{r['janelas_pos']:>5} | pior {r['pior']:>8.2f} | PF {r['PF']} | tr {r['trades']:>5} | DD {r['maior_DD']:>8.2f} | "
                  f"sem_set {r['liquido_sem_set']:>9.2f} | melhora {r['melhora_meses']}", flush=True)
    print("\nORDENADO POR LIQUIDO")
    for x, r in sorted(res, key=lambda t: -t[1]["liquido"]):
        print(f"{x['tf']:>5} {x['modo']:<11} ttl={x['ttl']:>2} per={x['per']} es={x['es']} | liq {r['liquido']:>9.2f} | "
              f"+{r['janelas_pos']:>5} | pior {r['pior']:>8.2f} | PF {r['PF']} | tr {r['trades']:>5} | DD {r['maior_DD']:>8.2f} | "
              f"sem_set {r['liquido_sem_set']:>9.2f} | melhora {r['melhora_meses']}", flush=True)

if __name__ == "__main__":
    main()
