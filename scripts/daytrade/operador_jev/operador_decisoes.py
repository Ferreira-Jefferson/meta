"""Modo `--motor decisoes`: o Jev (endpoint /api/alpha/decisions) responde perguntas vela a vela; o motor executa.

Por vela M15 fechada: 1 chamada de MERCADO (estado so de mercado, todas as perguntas, independe da trajetoria) e,
se ha posicao aberta, 1 chamada de GESTAO (estado + linha POSICAO). As chamadas de mercado do dia sao disparadas em paralelo
(nao dependem da simulacao); a simulacao e sequencial e deterministica.
"""
from __future__ import annotations
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd

from mercado import montar_estado, _hm
from motor import run_dia, Abortar
from decisoes import Ctx, decide_vela, ks_decisao
from perguntas_jev import QUESTOES_MERCADO, QUESTOES_GESTAO
import jev_api


def metricas_basicas(trades):
    brl = [t["brl"] for t in trades]
    ganhos = sum(x for x in brl if x > 0)
    perdas = -sum(x for x in brl if x < 0)
    eq = np.cumsum(brl) if brl else np.array([0.0])
    pico = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    return dict(ops=len(brl), total=float(sum(brl)), dd=float((pico - eq).max()) if brl else 0.0,
                pf=(ganhos / perdas if perdas > 0 else (float("inf") if ganhos > 0 else float("nan"))),
                acerto=(100 * sum(1 for x in brl if x > 0) / len(brl) if brl else float("nan")))


def roda_dia_decisoes(mk, ctx: Ctx, cli: jev_api.Cliente, data, dia_n, args, saida: Path):
    dia = mk.dia(data, dia_n)
    t0 = time.time()
    ks = ks_decisao(dia, args.hora_ini, args.hora_fim)
    cache_m: dict[int, tuple] = {}
    estado_txt: dict[int, str] = {}

    def busca_m(k):
        est = montar_estado(mk, dia, k)
        estado_txt[k] = est
        return cli.decidir(est, QUESTOES_MERCADO)

    # chamadas de mercado em paralelo (independem da posicao); falha de custo vira ficar fora
    with ThreadPoolExecutor(max_workers=args.paralelo_velas) as ex:
        futs = {k: ex.submit(busca_m, k) for k in ks}
        for k, f in futs.items():
            try:
                cache_m[k] = f.result()
            except jev_api.CustoExcedido as e:
                cache_m[k] = (None, dict(falha=str(e), abortado=True, custo=0.0, tempo=0.0, tokens_in=0, tokens_out=0, modelo=None))

    custo = dict(v=sum(m.get("custo", 0) for _, m in cache_m.values()))

    def decidir(pacote_fn, k, s):
        rm, mm = cache_m[k] if k in cache_m else busca_m(k)
        meta = dict(mm)
        rg = None
        if s.pos:
            try:
                est = montar_estado(mk, dia, k, pos=dict(s.pos, lado=s.pos["lado"]))
                rg, mg = cli.decidir(est, QUESTOES_GESTAO)
                meta["custo"] = meta.get("custo", 0) + mg.get("custo", 0)
                meta["tempo"] = meta.get("tempo", 0) + mg.get("tempo", 0)
                meta["tokens_in"] = meta.get("tokens_in", 0) + mg.get("tokens_in", 0)
                meta["tokens_out"] = meta.get("tokens_out", 0) + mg.get("tokens_out", 0)
                custo["v"] += mg.get("custo", 0)
                if mg.get("falha"):
                    meta["falha"] = (meta.get("falha") or "") + " | gestao: " + mg["falha"]
            except jev_api.CustoExcedido as e:
                meta["falha"] = str(e)
        dec, info = decide_vela(ctx, dia, k, s, rm, rg, args.limiar, args.modo_entrada)
        meta["jev"] = dict(m=rm, g=rg, info=info)
        if not rm and not s.pos and not s.pend:
            meta["falha_decisao"] = True
        return dec, meta

    s, pontos = run_dia(mk, dia, decidir, args.hora_ini, args.hora_fim, None)
    bars = [dict(t=_hm(dia.m15_t[i]), o=float(r[0]), h=float(r[1]), l=float(r[2]), c=float(r[3]), v=float(r[4]))
            for i, r in enumerate(dia.m15)]
    n_falhas = sum(1 for p in pontos if p["meta"].get("falha_decisao") or (p["meta"].get("falha") and not p["meta"].get("jev", {}).get("m")))
    sess = dict(
        motor="decisoes", data=str(pd.Timestamp(data).date()), dia_n=dia_n, semana_venc=dia.venc_semana, dia_venc=dia.venc_dia,
        modelo_pedido=args.modelo, limiar=args.limiar, modo_entrada=args.modo_entrada, flat=_hm(dia.m1_t[dia.flat_i] + np.timedelta64(1, "m")),
        bars=bars,
        pontos=[dict(k=p["k"], t=p["t"], decisao=p["decisao"], msgs=p["msgs"], jev=p["meta"].get("jev", {}),
                     **{x: p["meta"].get(x) for x in ("modelo", "custo", "tempo", "tokens_in", "tokens_out", "falha")})
                for p in pontos],
        estado_exemplo=estado_txt.get(ks[len(ks) // 2]) if ks else None,
        eventos=s.eventos, ordens=s.ordens, trades=s.trades,
        resumo=dict(metricas_basicas(s.trades), pts=s.pts), custo_usd=custo["v"], tempo_s=time.time() - t0, n_falhas=n_falhas,
        abortado=any((m.get("abortado")) for _, m in cache_m.values()),
    )
    saida.mkdir(parents=True, exist_ok=True)
    (saida / f"{sess['data']}.json").write_text(json.dumps(sess, ensure_ascii=False, default=float, separators=(",", ":")), encoding="utf-8")
    return sess
