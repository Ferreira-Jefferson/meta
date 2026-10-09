"""Roda a v4: etapa 1 (8 perguntas de mercado) REUSADA dos logs da v3 nos mesmos dias (mesmo estado de entrada => mesma chamada; se faltar, chama);
etapa 2 sequencial (so sem posicao e sem ordem pendente) com o bloco CONTEXTO DO DIA E DE RISCO + `v4_direcao_comprovada`; gestao com `v4_g_acao`
(bloco TESE DA POSICAO). Regras deterministicas de regras_v4 aplicadas sobre as respostas. Execucao: entrada limitada, alvo limitado, stop a mercado,
`zerar` LIMITADO (SessaoL da v3).
Uso: python rodar_v4.py --dias ../rodada_v4_dias.json --v3 ../sessoes_v3/R50v4 --saida ../sessoes_v4/R50"""
from __future__ import annotations
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(EXP / "v3"))
import perguntas_v4 as p4  # noqa: E402
import regras_v4 as rg  # noqa: E402
from decisoes_v4 import CFG_V4, decisao_entrada_v4, decisao_gestao_v4  # noqa: E402
from comum import estado_v, PAI  # noqa: E402
from mercado import Mercado, _hm  # noqa: E402
from decisoes import Ctx, ks_decisao  # noqa: E402
from operador_decisoes import metricas_basicas  # noqa: E402
import jev_api  # noqa: E402
import perguntas_v3 as p3  # noqa: E402
from sessao_l import SessaoL  # noqa: E402
from rodar_v3 import soma, HORA_INI, HORA_FIM, ESTADO, dia_n_v1  # noqa: E402


def r1_de_v3(v3_pasta: Path, data):
    """{k: respostas da etapa 1} lidas do log da v3 (jev.m filtrado pelos ids de mercado da v3)."""
    f = v3_pasta / "M" / f"{data}.json"
    if not f.exists():
        return {}
    s = json.loads(f.read_text(encoding="utf-8"))
    out = {}
    for p in s["pontos"]:
        m = (p.get("jev") or {}).get("m")
        if m and all(q in m for q in p3.IDS_V3):
            out[p["k"]] = {q: m[q] for q in p3.IDS_V3}
    return out


def roda_dia(mk, ctx, cli, data, dia_n, v3_pasta, limiar, saida: Path, modelo):
    dia = mk.dia(data, dia_n)
    t0 = time.time()
    ks = ks_decisao(dia, HORA_INI, HORA_FIM)
    r1_log = r1_de_v3(v3_pasta, data)
    s = SessaoL(dia)
    pontos = []
    custo = [0.0]
    n_reuso, n_live1 = [0], [0]
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
        meta = dict(custo=0.0, tempo=0.0, tokens_in=0, tokens_out=0)
        rm = rgst = None
        if s.pos:
            if not getattr(s, "exit_pend", None):
                est = estado_v(mk, dia, k, pos=dict(s.pos, lado=s.pos["lado"]), **ESTADO)
                tese_txt, _, _ = p4.bloco_tese(ctx, dia, k, s.pos)
                r1 = r1_log.get(k)
                r, mg = cli.decidir(est + "\n\n" + p4.texto_respostas(r1 or {}) + "\n\n" + tese_txt, p4.QUESTOES_GESTAO_V4)
                meta = soma(meta, mg)
                rgst = dict(r, g_acao=r["v4_g_acao"]) if r and "v4_g_acao" in r else None
            dec, info = decisao_gestao_v4(rgst, ctx, dia, k, s.pos, CFG_V4)
            info["fase"] = "gestao"
        elif s.pend:
            dec, info = dict(acao="manter", confianca=0, respostas=[], raciocinio="ordem pendente: aguarda"), dict(fase="pendente")
        else:
            est = estado_v(mk, dia, k, **ESTADO)
            r1 = r1_log.get(k)
            if r1:
                n_reuso[0] += 1
            else:
                n_live1[0] += 1
                r1, m1 = cli.decidir(est, p3.QUESTOES_MERCADO_V3)
                meta = soma(meta, m1)
            if not r1:
                rm = None
                dec, info = dict(acao="ficar_fora", confianca=0, respostas=[], raciocinio="(sem resposta do Jev)"), dict(fase="falha")
                meta["falha_decisao"] = True
            else:
                bloco = p4.bloco_dia(ctx, dia, k, s.trades)
                r2, m2 = cli.decidir(est + "\n\n" + p4.texto_respostas(r1) + "\n\n" + bloco, p4.QUESTOES_FINAIS_A4)
                meta = soma(meta, m2)
                rm = {**r1, **(r2 or {})}
                if r2 is None:
                    dec, info = dict(acao="ficar_fora", confianca=0, respostas=[], raciocinio="(etapa 2 falhou)"), dict(fase="falha")
                    meta["falha_decisao"] = True
                else:
                    dec, info = decisao_entrada_v4(rm, ctx, dia, k, limiar, s.trades, CFG_V4)
                    info["fase"] = "entrada"
        custo[0] += meta.get("custo", 0.0)
        msgs = s.aplicar(dec, k)
        pontos.append(dict(k=k, t=t_fech, decisao=dec, msgs=msgs, jev=dict(m=rm, g=rgst, info=info),
                           **{x: meta.get(x) for x in ("custo", "tokens_in", "tokens_out", "falha")}))
    bars = [dict(t=_hm(dia.m15_t[i]), o=float(r[0]), h=float(r[1]), l=float(r[2]), c=float(r[3]), v=float(r[4])) for i, r in enumerate(dia.m15)]
    sess = dict(motor="v4", variante="L", data=str(pd.Timestamp(data).date()), dia_n=dia_n, modelo_pedido=modelo, limiar=limiar, cfg=CFG_V4,
                flat=_hm(dia.m1_t[dia.flat_i] + np.timedelta64(1, "m")), bars=bars, pontos=pontos, eventos=s.eventos, ordens=s.ordens, trades=s.trades,
                resumo=dict(metricas_basicas(s.trades), pts=s.pts), custo_usd=custo[0], tempo_s=time.time() - t0,
                n_falhas=sum(1 for p in pontos if p["jev"].get("info", {}).get("fase") == "falha"), etapa1_reusada=n_reuso[0], etapa1_ao_vivo=n_live1[0])
    d = saida / "L"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sess['data']}.json").write_text(json.dumps(sess, ensure_ascii=False, default=float, separators=(",", ":")), encoding="utf-8")
    return sess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", required=True)
    ap.add_argument("--v3", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--limiar", type=float, default=0.3)
    ap.add_argument("--modelo", default=jev_api.MODELO_FIXO)
    ap.add_argument("--paralelo-dias", type=int, default=8)
    ap.add_argument("--max-custo-usd", type=float, default=4.0)
    ap.add_argument("--refazer", action="store_true")
    ap.add_argument("--so", nargs="*")
    a = ap.parse_args()
    dias = json.load(open(a.dias, encoding="utf-8"))["dias"]
    if a.so:
        dias = [d for d in dias if d["data"] in a.so]
    saida, v3 = Path(a.saida), Path(a.v3)
    pend = [d for d in dias if a.refazer or not (saida / "L" / f"{d['data']}.json").exists()]
    print(f"[v4] {len(dias)} dias, {len(pend)} a rodar | estado {ESTADO} | cfg {CFG_V4} | saida {saida}", flush=True)
    mk = Mercado.carregar()
    ctx = Ctx(mk)
    cli = jev_api.Cliente(a.modelo, a.max_custo_usd, max_simultaneas=16)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.paralelo_dias) as ex:
        futs = {ex.submit(roda_dia, mk, ctx, cli, d["data"], dia_n_v1(d["periodo"], d["data"]), v3, a.limiar, saida, a.modelo): d for d in pend}
        for f in as_completed(futs):
            d = futs[f]
            try:
                s = f.result()
            except Exception as e:
                import traceback
                print(f"{d['data']} ERRO {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                continue
            print(f"{d['data']} v4 R$ {s['resumo']['total']:+.0f} ({s['resumo']['ops']} ops)"
                  f"{' FALHAS ' + str(s['n_falhas']) if s['n_falhas'] else ''} | etapa1 reuso {s['etapa1_reusada']} ao vivo {s['etapa1_ao_vivo']} | US$ {cli.custo:.3f} acum | {time.time() - t0:.0f}s", flush=True)
    print(f"Jev: {cli.chamadas} chamadas | US$ {cli.custo:.4f} | tokens in {cli.tokens_in} out {cli.tokens_out} | falhas {cli.falhas} | 429 {cli.rate_limit}", flush=True)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / f"_custo_{int(time.time())}.json").write_text(json.dumps(dict(chamadas=cli.chamadas, custo=cli.custo, tokens_in=cli.tokens_in, tokens_out=cli.tokens_out,
                                                                          falhas=cli.falhas, rate_limit=cli.rate_limit, modelos=cli.modelos, tempo_s=time.time() - t0)), encoding="utf-8")


if __name__ == "__main__":
    main()
