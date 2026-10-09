"""Roda o Jev com as perguntas v2 em duas formas de decidir (ambas guiadas so pelas perguntas, sem estrategia fixa):

  A (duas etapas): 1a chamada = 17 perguntas v2 de mercado; 2a chamada recebe o pacote + as respostas da 1a (texto) e responde
                   acao/stop/alvo/mao (ou, com posicao, estrutura preservada + g_acao).
  B (veto):        1 chamada (17 perguntas v2 + acao/stop/alvo/mao); o motor so aceita a acao se nenhuma pergunta de direcao votar contra
                   (regra em perguntas_v2.vetos); gestao: P(estrutura preservada) < 0,5 -> aperta o stop ao pivo.
  REF:             a referencia ATUAL (54 perguntas, operador_decisoes.roda_dia_decisoes) para medir o ruido da API.

Uso: python rodar_v2.py --modo A --grupo validacao --saida sessoes_v2/A_val [--datas 2026-01-21,...] [--refazer]
O limiar (0,3) e a versao (jev-1.13-20260917) sao os mesmos da referencia. dia_n = o da sessao de referencia (o pacote traz 'SIMULACAO dia N').
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
PAI = AQUI.parent
sys.path.insert(0, str(PAI))
sys.path.insert(0, str(AQUI))
from mercado import Mercado, montar_estado, _hm  # noqa: E402
from motor import run_dia  # noqa: E402
from decisoes import Ctx, decisao_entrada, decisao_gestao, ks_decisao  # noqa: E402
from operador_decisoes import metricas_basicas, roda_dia_decisoes  # noqa: E402
import jev_api  # noqa: E402
import perguntas_v2 as pv  # noqa: E402

HORA_INI, HORA_FIM = "09:15", "17:30"


def soma_meta(a: dict, b: dict) -> dict:
    out = dict(a)
    for x in ("custo", "tempo", "tokens_in", "tokens_out"):
        out[x] = out.get(x, 0) + b.get(x, 0)
    if b.get("falha"):
        out["falha"] = (out.get("falha") or "") + " | " + b["falha"]
    return out


def decide_v2(ctx, dia, k, s, rm, rg, limiar, modo):
    """Decisao na vela k. Sem posicao e sem ordem: decisao_entrada do v1 (P da escolha >= limiar); na versao B, passa antes pelo veto."""
    if s.pos:
        dec, info = decisao_gestao(rg, ctx, dia, k, s.pos)
        info["fase"] = "gestao"
        return dec, info
    if s.pend:
        return dict(acao="manter", confianca=0, respostas=[], raciocinio="ordem pendente: aguarda"), dict(fase="pendente")
    if not rm:
        return dict(acao="ficar_fora", confianca=0, respostas=[], raciocinio="(sem resposta do Jev)"), dict(fase="falha")
    dec, info = decisao_entrada(rm, ctx, dia, k, limiar, "argmax")
    info["fase"] = "entrada"
    v = pv.vetos(rm)
    info["vetos"] = v
    if modo == "B" and dec["acao"] != "ficar_fora":
        lado = "comprar" if dec["acao"] == "comprar_limite" else "vender"
        mot = v["fora"] + v[lado]
        if mot:
            info["vetado"] = mot
            dec = dict(acao="ficar_fora", confianca=dec.get("confianca", 0), respostas=[],
                       raciocinio=f"veto ({lado}): " + "; ".join(mot))
    return dec, info


def roda_dia_v2(mk, ctx, cli, data, dia_n, modo, limiar, paralelo_velas, saida: Path, modelo):
    dia = mk.dia(data, dia_n)
    t0 = time.time()
    ks = ks_decisao(dia, HORA_INI, HORA_FIM)
    estados = {k: montar_estado(mk, dia, k, derivados=True) for k in ks}
    cache: dict[int, tuple] = {}     # k -> (rm, meta)
    r1_por_k: dict[int, dict] = {}   # A: respostas da etapa 1 (usadas tambem na gestao)

    def chama_mercado(k):
        est = estados[k]
        if modo == "B":
            return cli.decidir(est, pv.QUESTOES_B)
        r1, m1 = cli.decidir(est, pv.QUESTOES_MERCADO_V2)
        if not r1:
            return None, dict(m1, etapa1_falhou=True)
        r1_por_k[k] = r1
        r2, m2 = cli.decidir(est + "\n\n" + pv.texto_respostas(r1), pv.QUESTOES_FINAIS_A)
        meta = soma_meta(m1, m2)
        meta["etapa2_falhou"] = r2 is None
        return {**r1, **(r2 or {})}, meta

    def seguro(k):
        try:
            return chama_mercado(k)
        except jev_api.CustoExcedido as e:
            return None, dict(falha=str(e), abortado=True, custo=0.0, tempo=0.0, tokens_in=0, tokens_out=0, modelo=None)

    with ThreadPoolExecutor(max_workers=paralelo_velas) as ex:
        futs = {k: ex.submit(seguro, k) for k in ks}
        for k, f in futs.items():
            cache[k] = f.result()
    custo = dict(v=sum(m.get("custo", 0) for _, m in cache.values()))

    def decidir(pacote_fn, k, s):
        rm, mm = cache[k] if k in cache else (None, dict(falha="vela fora das decisoes"))
        meta = dict(mm)
        rg = None
        if s.pos:
            try:
                est = montar_estado(mk, dia, k, pos=dict(s.pos, lado=s.pos["lado"]), derivados=True)
                if modo == "B":
                    r, mg = cli.decidir(est, pv.QUESTOES_GESTAO_B)
                    if r and "v2_estrutura_preservada" in r:
                        p = float(r["v2_estrutura_preservada"])
                        c = "manter" if p >= pv.P_ESTRUTURA_PRESERVADA else "stop_pivo"
                        rg = dict(r, g_acao=dict(c=c, p={"manter": p, "stop_pivo": 1 - p}, k=0.0))
                else:
                    r1 = r1_por_k.get(k) or {}
                    r, mg = cli.decidir(est + "\n\n" + pv.texto_respostas(r1), pv.QUESTOES_GESTAO_A)
                    if r and "v2_g_acao" in r:
                        rg = dict(r, g_acao=r["v2_g_acao"])
                meta = soma_meta(meta, mg)
                custo["v"] += mg.get("custo", 0)
            except jev_api.CustoExcedido as e:
                meta["falha"] = str(e)
        dec, info = decide_v2(ctx, dia, k, s, rm, rg, limiar, modo)
        meta["jev"] = dict(m=rm, g=rg, info=info)
        if not rm and not s.pos and not s.pend:
            meta["falha_decisao"] = True
        return dec, meta

    s, pontos = run_dia(mk, dia, decidir, HORA_INI, HORA_FIM, None)
    bars = [dict(t=_hm(dia.m15_t[i]), o=float(r[0]), h=float(r[1]), l=float(r[2]), c=float(r[3]), v=float(r[4])) for i, r in enumerate(dia.m15)]
    n_falhas = sum(1 for p in pontos if p["meta"].get("falha_decisao") or (p["meta"].get("falha") and not p["meta"].get("jev", {}).get("m")))
    sess = dict(
        motor="decisoes_v2", modo_v2=modo, data=str(pd.Timestamp(data).date()), dia_n=dia_n, semana_venc=dia.venc_semana, dia_venc=dia.venc_dia,
        modelo_pedido=modelo, limiar=limiar, modo_entrada="argmax", flat=_hm(dia.m1_t[dia.flat_i] + np.timedelta64(1, "m")), bars=bars,
        pontos=[dict(k=p["k"], t=p["t"], decisao=p["decisao"], msgs=p["msgs"], jev=p["meta"].get("jev", {}),
                     **{x: p["meta"].get(x) for x in ("modelo", "custo", "tempo", "tokens_in", "tokens_out", "falha")})
                for p in pontos],
        estado_exemplo=(estados[ks[len(ks) // 2]] + ("\n\n" + pv.texto_respostas(r1_por_k.get(ks[len(ks) // 2]) or {}) if modo == "A" else "")) if ks else None,
        eventos=s.eventos, ordens=s.ordens, trades=s.trades,
        resumo=dict(metricas_basicas(s.trades), pts=s.pts), custo_usd=custo["v"], tempo_s=time.time() - t0, n_falhas=n_falhas,
        abortado=any(m.get("abortado") for _, m in cache.values()),
    )
    saida.mkdir(parents=True, exist_ok=True)
    (saida / f"{sess['data']}.json").write_text(json.dumps(sess, ensure_ascii=False, default=float, separators=(",", ":")), encoding="utf-8")
    return sess


def dias_ref(grupo):
    ref = json.load(open(AQUI / "referencia.json", encoding="utf-8"))
    g = ref[grupo]
    return [dict(data=x["data"], periodo=x["periodo"], brl=x["brl"], ops=x["ops"], bom=(k == "bons"))
            for k in ("bons", "ruins") for x in g[k]]


def dia_n_ref(periodo, data):
    f = PAI / "sessoes_dec" / periodo / f"{data}.json"
    return json.loads(f.read_text(encoding="utf-8")).get("dia_n", 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", required=True, choices=["A", "B", "REF"])
    ap.add_argument("--grupo", default="validacao", choices=["validacao", "treino"])
    ap.add_argument("--datas", help="subconjunto (AAAA-MM-DD separados por virgula)")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--limiar", type=float, default=0.3)
    ap.add_argument("--modelo", default=jev_api.MODELO_FIXO)
    ap.add_argument("--paralelo-dias", type=int, default=5)
    ap.add_argument("--paralelo-velas", type=int, default=8)
    ap.add_argument("--max-custo-usd", type=float, default=3.0)
    ap.add_argument("--refazer", action="store_true")
    a = ap.parse_args()
    dias = dias_ref(a.grupo)
    if a.datas:
        sel = set(x.strip() for x in a.datas.split(","))
        dias = [d for d in dias if d["data"] in sel]
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    print("carregando dados...", flush=True)
    mk = Mercado.carregar()
    ctx = Ctx(mk)
    cli = jev_api.Cliente(a.modelo, a.max_custo_usd, max_simultaneas=16)
    pend = [d for d in dias if a.refazer or not (saida / f"{d['data']}.json").exists()]
    print(f"[{a.modo}/{a.grupo}] {len(dias)} dias, {len(pend)} a rodar | limiar {a.limiar} | modelo {a.modelo} | saida {saida}", flush=True)
    args_ref = SimpleNamespace(modelo=a.modelo, limiar=a.limiar, modo_entrada="argmax", paralelo_velas=a.paralelo_velas, hora_ini=HORA_INI, hora_fim=HORA_FIM)

    def um(d):
        n = dia_n_ref(d["periodo"], d["data"])
        if a.modo == "REF":
            return roda_dia_decisoes(mk, ctx, cli, d["data"], n, args_ref, saida)
        return roda_dia_v2(mk, ctx, cli, d["data"], n, a.modo, a.limiar, a.paralelo_velas, saida, a.modelo)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.paralelo_dias) as ex:
        futs = {ex.submit(um, d): d for d in pend}
        for f in as_completed(futs):
            d = futs[f]
            try:
                s = f.result()
            except Exception as e:
                print(f"{d['data']} ERRO {type(e).__name__}: {e}", flush=True)
                continue
            print(f"{s['data']} ({'bom' if d['bom'] else 'ruim'}) atual R$ {d['brl']:+.0f} -> {a.modo} R$ {s['resumo']['total']:+.0f} em {s['resumo']['ops']} ops"
                  f"{' FALHAS ' + str(s['n_falhas']) if s['n_falhas'] else ''} | US$ {cli.custo:.3f} acum | {time.time() - t0:.0f}s", flush=True)
    print(f"Jev: {cli.chamadas} chamadas | US$ {cli.custo:.4f} | tokens in {cli.tokens_in} out {cli.tokens_out} | falhas {cli.falhas} | 429 {cli.rate_limit} | modelos {cli.modelos}", flush=True)
    (saida / f"_custo_{int(time.time())}.json").write_text(json.dumps(dict(chamadas=cli.chamadas, custo=cli.custo, tokens_in=cli.tokens_in, tokens_out=cli.tokens_out,
                                                                          falhas=cli.falhas, rate_limit=cli.rate_limit, modelos=cli.modelos, tempo_s=time.time() - t0)), encoding="utf-8")


if __name__ == "__main__":
    main()
