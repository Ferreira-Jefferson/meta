"""Fase 1c da v3: reducao do STATE e fusao das etapas, medidas em velas de TREINO (as mesmas ~340 da ablacao).
Referencia = etapa 1 (perguntas FINAL) + etapa 2 com o estado COMPLETO da v2 (40 velas M15, 10 dias de DIARIO, 2 dias de H1), rodada de novo agora.
Variantes: estado reduzido (so muda o estado; mesmas perguntas) e fusao (1 chamada: perguntas + acao/stop/alvo/mao, sem as respostas na frente).
Metricas: concordancia da classe de decisao (comprar/vender/fora a limiar 0,3) com a referencia, |dif P(lado)|, taxa de entrada, tokens e custo por vela.
O ruido da API = a propria referencia repetida (variante 'ref_repeticao')."""
from __future__ import annotations
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import estado_v, EXP  # noqa: E402
from mercado import Mercado  # noqa: E402
from decisoes import ks_decisao  # noqa: E402
import jev_api  # noqa: E402
import perguntas_v2 as pv  # noqa: E402
import perguntas_v3 as p3  # noqa: E402

LIM = 0.3


def classe(r):
    pa = r["acao"]["p"]
    esc = r["acao"]["c"]
    return esc if esc in ("comprar", "vender") and pa.get(esc, 0) >= LIM else "fora"


def lado(r):
    pa = r["acao"]["p"]
    return pa.get("comprar", 0) - pa.get("vender", 0)


def main():
    ref = json.load(open(EXP / "referencia.json", encoding="utf-8"))
    dias = [(x["data"], x["periodo"]) for k in ("bons", "ruins") for x in ref["treino"][k]]
    mk = Mercado.carregar()
    cli = jev_api.Cliente(jev_api.MODELO_FIXO, 5.0, max_simultaneas=16)
    amostra = []
    for d, per in dias:
        s = json.load(open(EXP / "sessoes_v2" / "A_treino" / f"{d}.json", encoding="utf-8"))
        dia = mk.dia(d, s["dia_n"])
        ks = ks_decisao(dia)
        for i, k in enumerate(ks):
            if i % 2 == 0:
                amostra.append((d, dia, k))
    print(f"{len(amostra)} velas", flush=True)
    VAR = {
        "ref_repeticao": dict(n_velas=40, diario_n=10, h1_dias=2),
        "m15_16": dict(n_velas=16, diario_n=10, h1_dias=2),
        "m15_12": dict(n_velas=12, diario_n=10, h1_dias=2),
        "m15_16_diario5_h1ontem": dict(n_velas=16, diario_n=5, h1_dias=1),
        "m15_16_sem_diario_h1hoje": dict(n_velas=16, diario_n=0, h1_dias=0),
        "m15_12_sem_diario_h1hoje": dict(n_velas=12, diario_n=0, h1_dias=0),
    }

    def duas_etapas(est):
        r1, m1 = cli.decidir(est, p3.QUESTOES_MERCADO_V3)
        if not r1:
            return None, m1, None
        r2, m2 = cli.decidir(est + "\n\n" + p3.texto_respostas(r1), p3.QUESTOES_FINAIS_A3)
        return ({**r1, **(r2 or {})} if r2 else None), (m1, m2), r1

    def run(est_kw, fusao=False):
        def um(x):
            d, dia, k = x
            est = estado_v(mk, dia, k, **est_kw)
            if fusao:
                r, m = cli.decidir(est, p3.QUESTOES_FUSAO)
                return r, (m,), r
            return duas_etapas(est)
        with ThreadPoolExecutor(16) as ex:
            return list(ex.map(um, amostra))

    t0 = time.time()
    base = run(VAR["ref_repeticao"])
    # referencia = primeira passada; a repeticao mede o ruido
    ref_out = base
    res = {}

    def resumo(nome, outs, referencia):
        ok = [o[0] is not None and "acao" in o[0] and r[0] is not None and "acao" in r[0] for o, r in zip(outs, referencia)]
        ag = np.mean([classe(o[0]) == classe(r[0]) for o, r, k in zip(outs, referencia, ok) if k])
        dl = np.mean([abs(lado(o[0]) - lado(r[0])) for o, r, k in zip(outs, referencia, ok) if k])
        ent = np.mean([classe(o[0]) != "fora" for o, k in zip(outs, ok) if k])
        tok = np.mean([sum(m["tokens_in"] for m in o[1]) if isinstance(o[1], tuple) else o[1]["tokens_in"] for o in outs])
        cus = np.mean([sum(m["custo"] for m in o[1]) if isinstance(o[1], tuple) else o[1]["custo"] for o in outs])
        # concordancia das respostas da etapa 1 mais usadas na decisao (classe modal igual)
        c1 = []
        for o, r, k in zip(outs, referencia, ok):
            if k and o[2] and r[2]:
                for q in ("v2_dia_tipo", "v2_estrutura", "v2_seguimento"):
                    if q in o[2] and q in r[2]:
                        c1.append(o[2][q]["c"] == r[2][q]["c"])
        res[nome] = dict(concorda=float(ag), dif_lado=float(dl), entra=float(ent), tokens_in_vela=float(tok), custo_vela=float(cus),
                         concorda_etapa1=float(np.mean(c1)) if c1 else None, n=int(sum(ok)))
        print(f"{nome:<30} concorda {100*ag:5.1f}% | |dif P(lado)| {dl:.3f} | entra {100*ent:4.1f}% | tok_in/vela {tok:6.0f} | US$/vela {cus:.5f} | "
              f"etapa1 igual {100*np.mean(c1) if c1 else float('nan'):4.0f}% | acum US$ {cli.custo:.2f} | {time.time()-t0:.0f}s", flush=True)

    resumo("ref_cheio_(1a passada)", base, base)
    for nome, kw in VAR.items():
        o = run(kw) if nome != "ref_repeticao" else run(kw)
        resumo(nome, o, ref_out)
    o = run(VAR["ref_repeticao"], fusao=True)
    resumo("fusao_1_chamada_estado_cheio", o, ref_out)
    Path(EXP / "v3" / "estado_api.json").write_text(json.dumps(dict(n=len(amostra), res=res, custo=cli.custo), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
