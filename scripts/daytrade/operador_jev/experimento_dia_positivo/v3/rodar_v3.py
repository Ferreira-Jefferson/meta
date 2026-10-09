"""Roda a v3 (modo A simplificado: etapa 1 com as perguntas v3, etapa 2 decide vendo as respostas; ou F = fusao numa chamada) em dias dados.
Cada dia gera DUAS sessoes sobre as MESMAS chamadas de mercado: M (`zerar` a mercado, como na v2) e L (`zerar` por limite no ultimo fechamento, 2 velas).
Uso: python rodar_v3.py --dias rodada_v3_dias.json --saida sessoes_v3/R50 [--modo A|F] [--grupo treino]
Dias: arquivo JSON {dias:[{data,periodo}]} (rodada) ou --grupo treino (os 20 de referencia.json)."""
from __future__ import annotations
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import estado_v, EXP, PAI  # noqa: E402
from mercado import Mercado, _hm  # noqa: E402
from motor import Sessao  # noqa: E402
from decisoes import Ctx, decisao_entrada, decisao_gestao, ks_decisao  # noqa: E402
from operador_decisoes import metricas_basicas  # noqa: E402
import jev_api  # noqa: E402
import perguntas_v3 as p3  # noqa: E402
from sessao_l import SessaoL  # noqa: E402

HORA_INI, HORA_FIM = "09:15", "17:30"
ESTADO = dict(n_velas=p3.ESTADO_N_VELAS, diario_n=p3.ESTADO_DIARIO_N, h1_dias=p3.ESTADO_H1_DIAS)


def soma(a, b):
    o = dict(a)
    for x in ("custo", "tempo", "tokens_in", "tokens_out"):
        o[x] = o.get(x, 0) + b.get(x, 0)
    if b.get("falha"):
        o["falha"] = (o.get("falha") or "") + " | " + b["falha"]
    return o


def run_cls(mk, dia, decidir, classe):
    s = classe(dia)
    pontos = []
    n = len(dia.m15_t)
    for k in range(n):
        s.simular_barra(k)
        if s.encerrada:
            break
        t_fech = _hm(dia.m15_t[k] + np.timedelta64(15, "m"))
        if not (HORA_INI <= t_fech <= HORA_FIM):
            continue
        if int(dia.m1_fim[k]) > dia.flat_i + 1 or k == n - 1:
            continue
        dec, meta = decidir(k, s)
        msgs = s.aplicar(dec, k)
        pontos.append(dict(k=k, t=t_fech, decisao=dec, meta=meta, msgs=msgs))
    return s, pontos


def roda_dia(mk, ctx, cli, data, dia_n, modo, limiar, pvelas, saida: Path, modelo):
    dia = mk.dia(data, dia_n)
    t0 = time.time()
    ks = ks_decisao(dia, HORA_INI, HORA_FIM)
    estados = {k: estado_v(mk, dia, k, **ESTADO) for k in ks}
    cache, r1_k = {}, {}

    def mercado(k):
        est = estados[k]
        try:
            if modo == "F":
                r, m = cli.decidir(est, p3.QUESTOES_FUSAO)
                r1_k[k] = r
                return r, m
            r1, m1 = cli.decidir(est, p3.QUESTOES_MERCADO_V3)
            if not r1:
                return None, dict(m1, etapa1_falhou=True)
            r1_k[k] = r1
            r2, m2 = cli.decidir(est + "\n\n" + p3.texto_respostas(r1), p3.QUESTOES_FINAIS_A3)
            m = soma(m1, m2)
            m["etapa2_falhou"] = r2 is None
            return {**r1, **(r2 or {})}, m
        except jev_api.CustoExcedido as e:
            return None, dict(falha=str(e), abortado=True, custo=0.0, tempo=0.0, tokens_in=0, tokens_out=0, modelo=None)

    with ThreadPoolExecutor(max_workers=pvelas) as ex:
        futs = {k: ex.submit(mercado, k) for k in ks}
        for k, f in futs.items():
            cache[k] = f.result()
    custo_mercado = sum(m.get("custo", 0) for _, m in cache.values())
    memo_g: dict = {}
    custo_g = [0.0]

    def gestao(k, s):
        p = s.pos
        chave = (k, p["k_ent"], p["dir"], p["preco"], p["stop"], p["n"])
        if chave in memo_g:
            return memo_g[chave]
        est = estado_v(mk, dia, k, pos=dict(p, lado=p["lado"]), **ESTADO)
        r, mg = cli.decidir(est + "\n\n" + p3.texto_respostas(r1_k.get(k) or {}), p3.QUESTOES_GESTAO_V3)
        rg = dict(r, g_acao=r["v2_g_acao"]) if r and "v2_g_acao" in r else None
        custo_g[0] += mg.get("custo", 0)
        memo_g[chave] = (rg, mg)
        return rg, mg

    def mk_decidir():
        def decidir(k, s):
            rm, mm = cache[k] if k in cache else (None, dict(falha="vela fora das decisoes"))
            meta = dict(mm)
            rg = None
            if s.pos:
                if not getattr(s, "exit_pend", None):
                    rg, mg = gestao(k, s)
                    meta = soma(meta, mg)
                dec, info = decisao_gestao(rg, ctx, dia, k, s.pos)
                info["fase"] = "gestao"
            elif s.pend:
                dec, info = dict(acao="manter", confianca=0, respostas=[], raciocinio="ordem pendente: aguarda"), dict(fase="pendente")
            elif not rm:
                dec, info = dict(acao="ficar_fora", confianca=0, respostas=[], raciocinio="(sem resposta do Jev)"), dict(fase="falha")
                meta["falha_decisao"] = True
            else:
                dec, info = decisao_entrada(rm, ctx, dia, k, limiar, "argmax")
                info["fase"] = "entrada"
            meta["jev"] = dict(m=rm, g=rg, info=info)
            return dec, meta
        return decidir

    bars = [dict(t=_hm(dia.m15_t[i]), o=float(r[0]), h=float(r[1]), l=float(r[2]), c=float(r[3]), v=float(r[4])) for i, r in enumerate(dia.m15)]
    out = {}
    for var, classe in (("M", Sessao), ("L", SessaoL)):
        s, pontos = run_cls(mk, dia, mk_decidir(), classe)
        sess = dict(motor="v3", modo=modo, variante=var, data=str(pd.Timestamp(data).date()), dia_n=dia_n, modelo_pedido=modelo, limiar=limiar,
                    flat=_hm(dia.m1_t[dia.flat_i] + np.timedelta64(1, "m")), bars=bars,
                    pontos=[dict(k=p["k"], t=p["t"], decisao=p["decisao"], msgs=p["msgs"], jev=p["meta"].get("jev", {}),
                                 **{x: p["meta"].get(x) for x in ("custo", "tokens_in", "tokens_out", "falha")}) for p in pontos],
                    eventos=s.eventos, ordens=s.ordens, trades=s.trades, resumo=dict(metricas_basicas(s.trades), pts=s.pts),
                    custo_usd=custo_mercado + custo_g[0], custo_mercado=custo_mercado, custo_gestao=custo_g[0], tempo_s=time.time() - t0,
                    n_falhas=sum(1 for p in pontos if p["meta"].get("falha_decisao")),
                    estado_exemplo=(estados[ks[len(ks) // 2]] + "\n\n" + p3.texto_respostas(r1_k.get(ks[len(ks) // 2]) or {})) if ks else None)
        d = saida / var
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{sess['data']}.json").write_text(json.dumps(sess, ensure_ascii=False, default=float, separators=(",", ":")), encoding="utf-8")
        out[var] = sess
    return out


def dia_n_v1(periodo, data):
    return json.loads((PAI / "sessoes_dec" / periodo / f"{data}.json").read_text(encoding="utf-8")).get("dia_n", 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias")
    ap.add_argument("--grupo", choices=["treino"])
    ap.add_argument("--saida", required=True)
    ap.add_argument("--modo", default="A", choices=["A", "F"])
    ap.add_argument("--limiar", type=float, default=0.3)
    ap.add_argument("--modelo", default=jev_api.MODELO_FIXO)
    ap.add_argument("--paralelo-dias", type=int, default=4)
    ap.add_argument("--paralelo-velas", type=int, default=6)
    ap.add_argument("--max-custo-usd", type=float, default=4.0)
    ap.add_argument("--refazer", action="store_true")
    a = ap.parse_args()
    if a.grupo == "treino":
        ref = json.load(open(EXP / "referencia.json", encoding="utf-8"))
        dias = [dict(data=x["data"], periodo=x["periodo"]) for k in ("bons", "ruins") for x in ref["treino"][k]]
    else:
        dias = json.load(open(a.dias, encoding="utf-8"))["dias"]
    saida = Path(a.saida)
    pend = [d for d in dias if a.refazer or not (saida / "L" / f"{d['data']}.json").exists()]
    print(f"[v3 modo {a.modo}] {len(dias)} dias, {len(pend)} a rodar | estado {ESTADO} | saida {saida}", flush=True)
    mk = Mercado.carregar()
    ctx = Ctx(mk)
    cli = jev_api.Cliente(a.modelo, a.max_custo_usd, max_simultaneas=16)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.paralelo_dias) as ex:
        futs = {ex.submit(roda_dia, mk, ctx, cli, d["data"], dia_n_v1(d["periodo"], d["data"]), a.modo, a.limiar, a.paralelo_velas, saida, a.modelo): d for d in pend}
        for f in as_completed(futs):
            d = futs[f]
            try:
                o = f.result()
            except Exception as e:
                import traceback
                print(f"{d['data']} ERRO {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                continue
            m, l = o["M"], o["L"]
            print(f"{d['data']} M R$ {m['resumo']['total']:+.0f} ({m['resumo']['ops']} ops) | L R$ {l['resumo']['total']:+.0f} ({l['resumo']['ops']} ops)"
                  f"{' FALHAS ' + str(m['n_falhas']) if m['n_falhas'] else ''} | US$ {cli.custo:.3f} acum | {time.time() - t0:.0f}s", flush=True)
    print(f"Jev: {cli.chamadas} chamadas | US$ {cli.custo:.4f} | tokens in {cli.tokens_in} out {cli.tokens_out} | falhas {cli.falhas} | 429 {cli.rate_limit}", flush=True)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / f"_custo_{int(time.time())}.json").write_text(json.dumps(dict(modo=a.modo, estado=ESTADO, chamadas=cli.chamadas, custo=cli.custo, tokens_in=cli.tokens_in,
                                                                          tokens_out=cli.tokens_out, falhas=cli.falhas, rate_limit=cli.rate_limit, modelos=cli.modelos,
                                                                          tempo_s=time.time() - t0)), encoding="utf-8")


if __name__ == "__main__":
    main()
