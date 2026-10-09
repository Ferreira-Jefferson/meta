"""Fase 1b da v3: ablacao REAL na etapa 2 (so dias de TREINO; nunca validacao/teste).
Para cada vela amostrada: a etapa 2 recebe o estado + as respostas da etapa 1 LOGADAS (v2 A) com um subconjunto de perguntas; compara a decisao
(classe comprar/vender/fora a limiar 0,3 + P(lado)) com a decisao logada (17 respostas). O ruido da API = repeticao do baseline."""
from __future__ import annotations
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import estado_v, EXP, PAI  # noqa: E402
from mercado import Mercado  # noqa: E402
from decisoes import ks_decisao  # noqa: E402
import jev_api  # noqa: E402
import perguntas_v2 as pv  # noqa: E402

MQ = [d["id"] for d in pv.M]
LIM = 0.3


def classe(r):
    pa = r["acao"]["p"]
    esc = r["acao"]["c"]
    return esc if esc in ("comprar", "vender") and pa.get(esc, 0) >= LIM else "fora"


def lado(r):
    pa = r["acao"]["p"]
    return pa.get("comprar", 0) - pa.get("vender", 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passo", type=int, default=2)
    ap.add_argument("--max-custo", type=float, default=6.0)
    ap.add_argument("--saida", default=str(EXP / "v3" / "ablacao_api.json"))
    ap.add_argument("--so-candidatos", help="json com candidatos; roda apenas eles (sem baseline/leave-one-out)")
    a = ap.parse_args()
    ref = json.load(open(EXP / "referencia.json", encoding="utf-8"))
    dias = [(x["data"], x["periodo"]) for k in ("bons", "ruins") for x in ref["treino"][k]]
    mk = Mercado.carregar()
    cli = jev_api.Cliente(jev_api.MODELO_FIXO, a.max_custo, max_simultaneas=16)
    amostra = []   # (data, dia_n, k, r_logada, estado)
    for d, per in dias:
        s = json.load(open(EXP / "sessoes_v2" / "A_treino" / f"{d}.json", encoding="utf-8"))
        dia = mk.dia(d, s["dia_n"])
        ks = ks_decisao(dia)
        por_k = {p["k"]: p["jev"].get("m") for p in s["pontos"]}
        for i, k in enumerate(ks):
            m = por_k.get(k)
            if m and i % a.passo == 0 and all(q in m for q in MQ) and "acao" in m:
                amostra.append((d, s["dia_n"], k, m, estado_v(mk, dia, k)))
    print(f"{len(amostra)} velas de treino amostradas", flush=True)

    def etapa2(est, m, ids):
        txt = est + "\n\n" + pv.texto_respostas(m, ids=ids) if ids else est
        r, meta = cli.decidir(txt, pv.QUESTOES_FINAIS_A)
        return r, meta

    exps = {}
    if not a.so_candidatos:
        exps["baseline_repeticao"] = MQ
        for q in MQ:
            exps[f"sem_{q}"] = [x for x in MQ if x != q]
        exps["nenhuma_resposta"] = []
    for nome, ids in json.load(open(a.so_candidatos or EXP / "v3" / "candidatos.json", encoding="utf-8")).items():
        exps[f"cand_{nome}"] = ids
    res = {}
    t0 = time.time()
    for nome, ids in exps.items():
        with ThreadPoolExecutor(16) as ex:
            outs = list(ex.map(lambda x: etapa2(x[4], x[3], ids), amostra))
        cls_ref = [classe(x[3]) for x in amostra]
        ok = [o[0] is not None and "acao" in o[0] for o in outs]
        cl = [classe(o[0]) if k else None for o, k in zip(outs, ok)]
        agree = np.mean([c == r for c, r, k in zip(cl, cls_ref, ok) if k])
        dl = np.mean([abs(lado(o[0]) - lado(x[3])) for o, x, k in zip(outs, amostra, ok) if k])
        ent = np.mean([c != "fora" for c, k in zip(cl, ok) if k])
        ent_ref = np.mean([c != "fora" for c in cls_ref])
        tok = np.mean([o[1]["tokens_in"] for o in outs])
        res[nome] = dict(n_resp=len(ids), concorda=float(agree), dif_lado=float(dl), entra=float(ent), entra_ref=float(ent_ref), tokens_in=float(tok),
                         n=int(sum(ok)))
        print(f"{nome:<34} n_resp {len(ids):>2} | concorda c/ logada {100*agree:5.1f}% | |dif P(lado)| {dl:.3f} | entra {100*ent:4.1f}% (ref {100*ent_ref:.1f}%) | tok_in {tok:.0f} | US$ {cli.custo:.2f} | {time.time()-t0:.0f}s", flush=True)
    Path(a.saida).write_text(json.dumps(dict(n_velas=len(amostra), res=res, custo=cli.custo), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
