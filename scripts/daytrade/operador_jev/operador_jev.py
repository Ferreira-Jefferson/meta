"""Operador Jev (LLM) no WIN: a LLM decide vela a vela, o motor deterministico executa.

Uso:
  python operador_jev.py --inicio 2026-03-10 --dias 2 [--periodo OOS] [--modelo typesafe/jev-router] [--paralelo-dias 3]
  python operador_jev.py --datas 2026-03-10,2026-05-12
"""
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
sys.path.insert(0, str(AQUI))
from mercado import Mercado, _hm  # noqa: E402
from motor import run_dia, Abortar, VALOR_PT  # noqa: E402
import llm  # noqa: E402


def br(x, nd=2):
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def metricas(trades):
    brl = [t["brl"] for t in trades]
    ganhos = sum(x for x in brl if x > 0)
    perdas = -sum(x for x in brl if x < 0)
    eq = np.cumsum(brl) if brl else np.array([0.0])
    pico = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    dd = float((pico - eq).max()) if len(brl) else 0.0
    return dict(ops=len(brl), total=float(sum(brl)), dd=dd,
                pf=(ganhos / perdas if perdas > 0 else (float("inf") if ganhos > 0 else float("nan"))),
                acerto=(100 * sum(1 for x in brl if x > 0) / len(brl) if brl else float("nan")))


def linha(nome, m, custo=None, tempo=None):
    pf = "-" if np.isnan(m["pf"]) else ("inf" if np.isinf(m["pf"]) else br(m["pf"]))
    ac = "-" if np.isnan(m["acerto"]) else br(m["acerto"], 1)
    return (f"{nome:<12} {m['ops']:>4} {br(m['total']):>12} {br(m['dd']):>12} {pf:>7} {ac:>8} "
            f"{('' if custo is None else br(custo, 3)):>10} {('' if tempo is None else f'{tempo:.0f}s'):>7}")


CAB = f"{'dia':<12} {'ops':>4} {'total R$':>12} {'pior queda':>12} {'F.lucro':>7} {'acerto%':>8} {'LLM US$':>10} {'tempo':>7}"


def estima(mk, dias, cli, hora_ini, hora_fim, preco_in, preco_out):
    from mercado import montar_pacote
    d0 = mk.dia(dias[0], 1)
    k = min(20, len(d0.m15_t) - 2)
    pk = montar_pacote(mk, d0, k, dict(pos=None, pend=None, pts=0, brl=0, ntrades=0), [], ["10:00 ficar_fora (conf 50): " + "x" * 160] * 12)
    n_pontos = len([1 for t in d0.m15_t if hora_ini <= _hm(t + np.timedelta64(15, "m")) <= hora_fim])
    calls = n_pontos * len(dias)
    tin = len(cli.sistema) / 3.2 + len(pk) / 3.2
    tout = 900  # raciocinio + JSON (estimativa)
    custo = calls * (tin * preco_in + tout * preco_out) / 1e6
    print(f"[estimativa] {len(dias)} dia(s) x ~{n_pontos} pontos = ~{calls} chamadas | ~{tin:,.0f} tokens de entrada (sistema {len(cli.sistema) / 3.2:,.0f} + pacote {len(pk) / 3.2:,.0f}) "
          f"e ~{tout} de saida por chamada | custo indicativo ~US$ {custo:.2f} (premissa {preco_in}/{preco_out} US$/Mtok entrada/saida; o real vem de usage.cost)", flush=True)


def roda_dia(mk, cli, data, dia_n, args, saida: Path):
    dia = mk.dia(data, dia_n)
    t0 = time.time()
    custo0 = 0.0
    acum = dict(custo=0.0)

    def decidir(pacote_fn, k, s):
        pk = pacote_fn()
        try:
            dec, meta = cli.decidir(pk)
        except llm.CustoExcedido as e:
            raise Abortar(str(e))
        meta["pacote"] = pk
        acum["custo"] += meta["custo"]
        if dec is None:
            dec = dict(acao="ficar_fora", respostas=[], raciocinio="(falha do operador: " + str(meta.get("falha")) + ")", confianca=0)
            meta["falha_decisao"] = True
        return dec, meta

    def on_ponto(p):
        m = p["meta"]
        print(f"  [{pd.Timestamp(data).date()} {p['t']}] {p['decisao'].get('acao'):<15} conf {p['decisao'].get('confianca')} "
              f"modelo {m.get('modelo')} US$ {m.get('custo', 0):.4f} {m.get('tempo', 0):.0f}s{' FALHA' if m.get('falha_decisao') else ''}", flush=True)

    s, pontos = run_dia(mk, dia, decidir, args.hora_ini, args.hora_fim, on_ponto)
    bars = [dict(t=_hm(dia.m15_t[i]), o=float(r[0]), h=float(r[1]), l=float(r[2]), c=float(r[3]), v=float(r[4])) for i, r in enumerate(dia.m15)]
    sess = dict(
        data=str(pd.Timestamp(data).date()), dia_n=dia_n, semana_venc=dia.venc_semana, dia_venc=dia.venc_dia,
        modelo_pedido=args.modelo, flat=_hm(dia.m1_t[dia.flat_i] + np.timedelta64(1, "m")),
        bars=bars,
        pontos=[dict(k=p["k"], t=p["t"], decisao=p["decisao"], msgs=p["msgs"], **{x: p["meta"].get(x) for x in
                     ("modelo", "custo", "tempo", "tokens_in", "tokens_out", "falha", "tentativas", "abortado", "pacote")})
                for p in pontos],
        eventos=s.eventos, ordens=s.ordens, trades=s.trades,
        resumo=dict(metricas(s.trades), pts=s.pts), custo_usd=acum["custo"], tempo_s=time.time() - t0,
        abortado=any(p["meta"].get("abortado") for p in pontos),
    )
    saida.mkdir(parents=True, exist_ok=True)
    (saida / f"{sess['data']}.json").write_text(json.dumps(sess, ensure_ascii=False, default=float), encoding="utf-8")
    return sess


def nulo_aleatorio(mk, dias_mkt, trades, sorteios=100, seed=7, hora_ini="09:15", hora_fim="17:30"):
    """Entradas aleatorias: mesma quantidade de trades do Jev, lado aleatorio, limite no ultimo fechamento (validade 2),
    mesmas distancias de stop/alvo e contratos de cada trade do Jev. Mesmo motor de execucao."""
    rng = np.random.default_rng(seed)
    if not trades:
        return np.zeros(sorteios)
    ks = {d.data: [k for k in range(len(d.m15_t) - 1) if hora_ini <= _hm(d.m15_t[k] + np.timedelta64(15, "m")) <= hora_fim and d.m1_fim[k] <= d.flat_i] for d in dias_mkt}
    tot = np.zeros(sorteios)
    for s in range(sorteios):
        for tr in trades:
            ds = abs(tr["preco_ent"] - tr["stop_ini"])
            da = abs(tr["alvo"] - tr["preco_ent"]) if tr.get("alvo") else None
            for _ in range(40):
                d = dias_mkt[rng.integers(len(dias_mkt))]
                k = int(rng.choice(ks[d.data]))
                lado = 1 if rng.random() < 0.5 else -1
                px = float(d.m15[k, 3])

                def decidir(pf, kk, sess, k=k, lado=lado, px=px):
                    if kk != k:
                        return dict(acao="manter"), {}
                    return dict(acao="comprar_limite" if lado > 0 else "vender_limite", preco=px, stop=px - lado * ds,
                                alvo=(px + lado * da) if da else None, contratos=tr["n"], validade_velas=2), {}
                ss, _ = run_dia(mk, d, decidir, hora_ini, hora_fim)
                if ss.trades:
                    tot[s] += ss.trades[0]["brl"]
                    break
    return tot


def main_decisoes(mk, dias, args):
    from operador_decisoes import roda_dia_decisoes
    from decisoes import Ctx
    import jev_api
    cli = jev_api.Cliente(args.modelo, args.max_custo_usd, max_simultaneas=args.paralelo_chamadas)
    ctx = Ctx(mk)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    pend = []
    for i, d in enumerate(dias):
        f = saida / f"{pd.Timestamp(d).date()}.json"
        if f.exists() and not args.refazer:
            try:
                if json.loads(f.read_text(encoding="utf-8")).get("n_falhas", 0) == 0:
                    continue
            except Exception:
                pass
        pend.append((i, d))
    print(f"[decisoes] modelo {args.modelo} | {len(dias)} dias, {len(pend)} a rodar (resto ja gravado) | limiar {args.limiar} | saida {saida}", flush=True)
    print(CAB, flush=True)
    t0 = time.time()
    feitos = 0
    with ThreadPoolExecutor(max_workers=max(1, args.paralelo_dias)) as ex:
        futs = {ex.submit(roda_dia_decisoes, mk, ctx, cli, d, i + 1, args, saida): d for i, d in pend}
        for f in as_completed(futs):
            d = futs[f]
            try:
                s = f.result()
            except Exception as e:
                print(f"{pd.Timestamp(d).date()} ERRO: {type(e).__name__}: {e}", flush=True)
                continue
            feitos += 1
            print(linha(s["data"], s["resumo"], s["custo_usd"], s["tempo_s"]) + (f" falhas {s['n_falhas']}" if s["n_falhas"] else "")
                  + f"  [{feitos}/{len(pend)} | US$ {cli.custo:.3f} acumulado | {time.time() - t0:.0f}s | 429: {cli.rate_limit}]", flush=True)
    print(f"Jev: {cli.chamadas} chamadas | US$ {cli.custo:.4f} | tokens in {cli.tokens_in} out {cli.tokens_out} | falhas {cli.falhas} | 429 {cli.rate_limit} | modelos {cli.modelos}", flush=True)
    (saida / "_custo.json").write_text(json.dumps(dict(chamadas=cli.chamadas, custo=cli.custo, tokens_in=cli.tokens_in, tokens_out=cli.tokens_out,
                                                       falhas=cli.falhas, rate_limit=cli.rate_limit, modelos=cli.modelos, tempo_s=time.time() - t0)), encoding="utf-8")
    print(f"sessoes em {saida} ; avaliar: python avaliar.py --pasta {saida}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio")
    ap.add_argument("--dias", type=int, default=1)
    ap.add_argument("--datas", help="lista AAAA-MM-DD separada por virgula (substitui --inicio/--dias)")
    ap.add_argument("--periodo", default="OOS", choices=["IS", "OOS", "virgem"])
    ap.add_argument("--motor", default="decisoes", choices=["decisoes", "chat"],
                    help="decisoes = endpoint /api/alpha/decisions do Jev (padrao); chat = router /chat/completions (antigo)")
    ap.add_argument("--modelo", default=None, help="padrao: typesafe/jev-1.13-20260917 (decisoes) | typesafe/jev-router (chat)")
    ap.add_argument("--limiar", type=float, default=0.5, help="decisoes: P(acao escolhida) minima para entrar")
    ap.add_argument("--modo-entrada", default="argmax", choices=["argmax", "lado"],
                    help="argmax: entra se a escolha do Jev for comprar/vender com P>=limiar (padrao); lado: compara so comprar x vender (ignora 'fora')")
    ap.add_argument("--paralelo-velas", type=int, default=8, help="decisoes: chamadas de mercado simultaneas dentro de um dia")
    ap.add_argument("--paralelo-chamadas", type=int, default=16, help="decisoes: teto global de requisicoes simultaneas")
    ap.add_argument("--amostra", type=int, default=0, help="sorteia N dias do periodo (seed fixa) em vez de --inicio/--dias")
    ap.add_argument("--seed", type=int, default=20261009)
    ap.add_argument("--refazer", action="store_true", help="decisoes: nao pula dias ja gravados")
    ap.add_argument("--paralelo-dias", type=int, default=3)
    ap.add_argument("--max-custo-usd", type=float, default=None, help="teto de custo (padrao: 5 chat, 30 decisoes)")
    ap.add_argument("--hora-ini", default="09:15")
    ap.add_argument("--hora-fim", default="17:30")
    ap.add_argument("--saida", default=None)
    ap.add_argument("--sorteios", type=int, default=100)
    ap.add_argument("--preco-in", type=float, default=1.0, help="so p/ estimativa (US$/Mtok)")
    ap.add_argument("--preco-out", type=float, default=4.0, help="so p/ estimativa (US$/Mtok)")
    args = ap.parse_args()
    if args.max_custo_usd is None:
        args.max_custo_usd = 30.0 if args.motor == "decisoes" else 5.0
    if args.modelo is None:
        args.modelo = "typesafe/jev-1.13-20260917" if args.motor == "decisoes" else "typesafe/jev-router"
    if args.saida is None:
        args.saida = str(AQUI / ("sessoes_dec" / Path(args.periodo) if args.motor == "decisoes" else "sessoes"))

    print("carregando dados...", flush=True)
    mk = Mercado.carregar()
    if args.datas:
        dias = [pd.Timestamp(x.strip()) for x in args.datas.split(",")]
    elif args.amostra:
        todos = mk.dias_do_periodo(args.periodo)
        rng = np.random.default_rng(args.seed)
        idx = sorted(rng.choice(len(todos), size=min(args.amostra, len(todos)), replace=False))
        dias = [todos[i] for i in idx]
    elif args.inicio is None and args.motor == "decisoes":
        dias = mk.dias_do_periodo(args.periodo)
    else:
        lista = [d for d in mk.dias_do_periodo(args.periodo) if d >= pd.Timestamp(args.inicio)]
        dias = lista[: args.dias]
    if not dias:
        sys.exit("nenhum dia encontrado")
    if args.motor == "decisoes":
        return main_decisoes(mk, dias, args)
    cli = llm.Cliente(args.modelo, args.max_custo_usd)
    estima(mk, dias, cli, args.hora_ini, args.hora_fim, args.preco_in, args.preco_out)
    saida = Path(args.saida)
    print(CAB, flush=True)
    sessoes = {}
    with ThreadPoolExecutor(max_workers=max(1, args.paralelo_dias)) as ex:
        futs = {ex.submit(roda_dia, mk, cli, d, i + 1, args, saida): d for i, d in enumerate(dias)}
        for f in as_completed(futs):
            d = futs[f]
            try:
                s = f.result()
            except Exception as e:
                print(f"{d.date()} ERRO: {type(e).__name__}: {e}", flush=True)
                continue
            sessoes[s["data"]] = s
            print(linha(s["data"], s["resumo"], s["custo_usd"], s["tempo_s"]) + (" (ABORTADO por custo)" if s["abortado"] else ""), flush=True)
    ordem = sorted(sessoes)
    trades = [t for dd in ordem for t in sessoes[dd]["trades"]]
    m = metricas(trades)
    print("-" * len(CAB))
    print(linha("TOTAL", m, cli.custo, None), flush=True)
    print(f"LLM: {cli.chamadas} chamadas | US$ {cli.custo:.4f} | tokens in {cli.tokens_in} (cache {cli.tokens_cache}) out {cli.tokens_out} | modelos que responderam: {cli.modelos}", flush=True)
    # resumo acumulado de TODAS as sessoes na pasta (execucoes anteriores incluidas) + nulos
    todas = {}
    for f in sorted(saida.glob("2*.json")):
        x = json.loads(f.read_text(encoding="utf-8"))
        todas[x["data"]] = x
    ordem = sorted(todas)
    trades = [t for dd in ordem for t in todas[dd]["trades"]]
    m = metricas(trades)
    modelos = {}
    for dd in ordem:
        for p in todas[dd]["pontos"]:
            if p.get("modelo"):
                modelos[p["modelo"]] = modelos.get(p["modelo"], 0) + 1
    custo_tot = sum(todas[dd]["custo_usd"] for dd in ordem)
    dias_mkt = [mk.dia(d, todas[d]["dia_n"]) for d in ordem]
    nulo = nulo_aleatorio(mk, dias_mkt, trades, args.sorteios, hora_ini=args.hora_ini, hora_fim=args.hora_fim)
    print(f"ACUMULADO ({len(ordem)} dias na pasta): " + linha("TOTAL", m, custo_tot, None).strip())
    print(f"NULO 1 (ficar sempre de fora): R$ {br(0)} | Jev {br(m['total'])}")
    print(f"NULO 2 ({args.sorteios} sorteios, {len(trades)} entradas aleatorias, mesmas distancias de stop/alvo): media R$ {br(nulo.mean())} | "
          f"p5 {br(np.percentile(nulo, 5))} p95 {br(np.percentile(nulo, 95))} | Jev >= sorteio em {100 * (m['total'] >= nulo).mean():.0f}% dos sorteios", flush=True)
    resumo = dict(total=m, custo_llm=custo_tot, chamadas=sum(modelos.values()), modelos=modelos,
                  nulo_ficar_fora=0.0, nulo_aleatorio=dict(media=float(nulo.mean()), p5=float(np.percentile(nulo, 5)), p95=float(np.percentile(nulo, 95)),
                                                         pct_jev_ge=float(100 * (m["total"] >= nulo).mean()), sorteios=int(args.sorteios), amostra=[float(x) for x in nulo]),
                  dias=ordem)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, default=float), encoding="utf-8")
    print(f"sessoes em {saida} ; viewer: python gera_viewer.py", flush=True)


if __name__ == "__main__":
    main()
