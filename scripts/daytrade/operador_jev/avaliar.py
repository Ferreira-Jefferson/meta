"""Avaliacao do operador Jev (--motor decisoes): painel padrao, nulos, re-limiar offline, diagnostico e calibracao.

Uso: python avaliar.py --pasta sessoes_dec/OOS [--pasta sessoes_dec/IS] [--sorteios 300] [--sem-nulo] [--workers 4]
Tudo sai em R$ (WIN, R$ 0,20/ponto/contrato, custo 10 pts/contrato ja descontado nos trades).
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

LIMIARES = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
REF_ESCADA = "escada v4.1 (referencia): OOS +R$ 10.521, 109 ops, 2 contratos"


def br(x, nd=2):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "-" if x is None or np.isnan(x) else "inf"
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------------------------- carga
def carrega(pasta: Path):
    sess = []
    for f in sorted(pasta.glob("2*.json")):
        sess.append(json.loads(f.read_text(encoding="utf-8")))
    return sess


# --------------------------------------------------------------------------- painel
def painel(sess_dias: list[dict]) -> dict:
    """sess_dias: sessoes (todas as do recorte, inclusive dias sem operacao). Devolve o painel padrao."""
    dias = sorted(sess_dias, key=lambda s: s["data"])
    trades = []
    for s in dias:
        for t in s["trades"]:
            trades.append(dict(data=s["data"], t_sai=t["t_sai"], brl=float(t["brl"])))
    trades.sort(key=lambda t: (t["data"], t["t_sai"]))
    brl = np.array([t["brl"] for t in trades])
    n_dias = len(dias)
    out = dict(dias=n_dias, ops=len(trades), total=float(brl.sum()) if len(brl) else 0.0)
    eq = np.concatenate([[0.0], np.cumsum(brl)])
    out["dd"] = float((np.maximum.accumulate(eq) - eq).max())
    out["fator_rec"] = out["total"] / out["dd"] if out["dd"] > 0 else (float("inf") if out["total"] > 0 else float("nan"))
    g, p = brl[brl > 0].sum(), -brl[brl < 0].sum()
    out["fator_lucro"] = g / p if p > 0 else (float("inf") if g > 0 else float("nan"))
    out["acerto"] = 100 * (brl > 0).mean() if len(brl) else float("nan")
    por_dia = pd.Series({s["data"]: sum(t["brl"] for t in s["trades"]) for s in dias})
    mes = por_dia.groupby(pd.to_datetime(por_dia.index).to_period("M")).sum()
    out["pior_mes"] = float(mes.min()) if len(mes) else float("nan")
    out["meses_pos"] = 100 * float((mes > 0).mean()) if len(mes) else float("nan")
    out["sharpe"] = float(por_dia.mean() / por_dia.std(ddof=1) * np.sqrt(252)) if len(por_dia) > 2 and por_dia.std(ddof=1) > 0 else float("nan")
    out["ops_dia"] = len(trades) / n_dias if n_dias else float("nan")
    return out


COLS = [("ops", "ops", 0), ("total", "total R$", 2), ("dd", "pior queda R$", 2), ("fator_rec", "fat.recup.", 2), ("fator_lucro", "fat.lucro", 2),
        ("acerto", "acerto%", 1), ("pior_mes", "pior mês R$", 2), ("meses_pos", "% meses+", 0), ("sharpe", "Sharpe", 2), ("ops_dia", "ops/dia", 2)]


def tabela(linhas: list[tuple[str, dict]]):
    w0 = max(12, max(len(n) for n, _ in linhas))
    cab = f"{'':<{w0}} {'dias':>5} " + " ".join(f"{c[1]:>13}" for c in COLS)
    print(cab)
    for nome, m in linhas:
        print(f"{nome:<{w0}} {m['dias']:>5} " + " ".join(f"{br(m[c[0]], c[2]):>13}" for c in COLS), flush=True)


def trimestre(d):
    t = pd.Timestamp(d)
    return f"{t.year}T{(t.month - 1) // 3 + 1}"


def por_trimestre(sess):
    grupos = {}
    for s in sess:
        grupos.setdefault(trimestre(s["data"]), []).append(s)
    return [(q, painel(v)) for q, v in sorted(grupos.items())]


# --------------------------------------------------------------------------- nulos
_MK = None
_CTX = None
_DIAS: dict = {}


def _init_worker():
    global _MK, _CTX
    from mercado import Mercado
    from decisoes import Ctx
    _MK = Mercado.carregar()
    _CTX = Ctx(_MK)


def _geometrias(sess):
    """Uma geometria por ordem PREENCHIDA do Jev: distancia de stop inicial, de alvo, contratos, trail."""
    geos = []
    for s in sess:
        trail_por_k = {p["k"]: bool(p["decisao"].get("trail")) for p in s["pontos"]}
        for o in s["ordens"]:
            if o.get("fill"):
                geos.append(dict(ds=abs(o["preco"] - o["stop"]), da=(abs(o["alvo"] - o["preco"]) if o.get("alvo") else None),
                                 n=o["n"], trail=trail_por_k.get(o["k_dec"], False)))
    return geos


def _um_sorteio(args):
    """Um sorteio do nulo: cada geometria vira uma entrada em (dia, vela, lado) aleatorios, mesmo motor, validade 3."""
    seed, datas, geos, hora_ini, hora_fim = args
    from motor import run_dia
    from decisoes import ks_decisao, decisao_gestao, VALIDADE_VELAS
    rng = np.random.default_rng(seed)
    for d in datas:
        if d not in _DIAS:
            _DIAS[d] = _MK.dia(d, 1)
    dias = _DIAS
    ks = {d: ks_decisao(dias[d], hora_ini, hora_fim) for d in datas}
    tot = 0.0
    for geo in geos:
        for _ in range(40):
            d = datas[rng.integers(len(datas))]
            if not ks[d]:
                continue
            dia = dias[d]
            k = int(rng.choice(ks[d]))
            lado = 1 if rng.random() < 0.5 else -1
            px = float(dia.m15[k, 3])

            def decidir(pf, kk, s, k=k, lado=lado, px=px, geo=geo, dia=dia):
                if s.pos:
                    dec, _ = decisao_gestao(None, _CTX, dia, kk, s.pos)
                    return dec, {}
                if kk != k or s.pend:
                    return dict(acao="manter"), {}
                return dict(acao="comprar_limite" if lado > 0 else "vender_limite", preco=px, stop=px - lado * geo["ds"],
                            alvo=(px + lado * geo["da"]) if geo["da"] else None, contratos=geo["n"],
                            validade_velas=VALIDADE_VELAS, trail=geo["trail"]), {}
            ss, _ = run_dia(_MK, dia, decidir, hora_ini, hora_fim)
            if ss.trades:
                tot += ss.trades[0]["brl"]
                break
    return tot


def nulo_aleatorio(sess, sorteios, workers, hora_ini="09:15", hora_fim="17:30"):
    geos = _geometrias(sess)
    datas = [pd.Timestamp(s["data"]) for s in sess]
    if not geos:
        return np.zeros(sorteios)
    out = np.zeros(sorteios)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        futs = {ex.submit(_um_sorteio, (1000 + i, datas, geos, hora_ini, hora_fim)): i for i in range(sorteios)}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    return out


# --------------------------------------------------------------------------- re-limiar offline
def relimiar(mk, ctx, sess, limiares, modo="argmax", hora_ini="09:15", hora_fim="17:30"):
    from decisoes import resimula_dia
    res = {}
    for L in limiares:
        refeitas = []
        for s in sess:
            dia = mk.dia(s["data"], s["dia_n"])
            ss = resimula_dia(mk, ctx, dia, s, L, hora_ini, hora_fim, modo)
            refeitas.append(dict(data=s["data"], trades=ss.trades))
        res[L] = painel(refeitas)
    return res


# --------------------------------------------------------------------------- diagnostico
def planifica(sess):
    """DataFrame (dia, k) x features: noul -> p ; choice -> p de cada categoria ; score -> valor."""
    linhas = []
    for s in sess:
        for p in s["pontos"]:
            m = p["jev"].get("m")
            if not m:
                continue
            r = dict(data=s["data"], k=p["k"])
            for qid, v in m.items():
                if isinstance(v, dict) and "c" in v:
                    for cat, pr in v["p"].items():
                        r[f"{qid}:{cat}"] = pr
                elif isinstance(v, dict) and "s" in v:
                    r[f"{qid}"] = v["s"]
                else:
                    r[qid] = v
            linhas.append(r)
    return pd.DataFrame(linhas)


def diagnostico(df, topo=15):
    df = df.copy()
    df["lado"] = df["acao:comprar"] - df["acao:vender"]
    df["fora"] = df["acao:fora"]
    feats = [c for c in df.columns if c not in ("data", "k", "lado", "fora") and not c.startswith(("acao:", "stop:", "alvo:", "mao:"))]
    rk = df[feats + ["lado", "fora"]].rank()          # Spearman = Pearson dos postos (sem scipy)
    corr = pd.DataFrame({"corr_lado": rk[feats].corrwith(rk["lado"]), "corr_fora": rk[feats].corrwith(rk["fora"])}).dropna()
    return corr


def calibracao(mk, ctx, sess, alvo_atr=1.0):
    """Quando o Jev da P(comprar)=p (ou P(vender)=p), com que frequencia o preco toca +1 ATR antes de -1 ATR (compra),
    ou -1 ATR antes de +1 ATR (venda), a partir do fechamento da vela? Resolucao em M1; ambiguo no mesmo M1 = nao acerto."""
    linhas = []
    for s in sess:
        dia = mk.dia(s["data"], s["dia_n"])
        for p in s["pontos"]:
            m = p["jev"].get("m")
            if not m:
                continue
            k = p["k"]
            g = ctx.g(dia, k)
            px, atr = float(ctx.C[g]), float(ctx.ATR[g])
            i0, i1 = int(dia.m1_fim[k]), dia.flat_i + 1
            if i1 - i0 < 3 or not atr > 0:
                continue
            hi, lo = dia.m1[i0:i1, 1], dia.m1[i0:i1, 2]
            iu = np.argmax(hi >= px + alvo_atr * atr) if (hi >= px + alvo_atr * atr).any() else 10**9
            idn = np.argmax(lo <= px - alvo_atr * atr) if (lo <= px - alvo_atr * atr).any() else 10**9
            if iu == 10**9 and idn == 10**9:
                continue                      # nenhum dos dois ate o fim do pregao: sem resolucao
            pr = m["acao"]["p"]
            linhas.append(dict(p_c=pr.get("comprar", 0), p_v=pr.get("vender", 0), sobe=bool(iu < idn), desce=bool(idn < iu)))
    return pd.DataFrame(linhas)


def tab_calibracao(cal):
    bins = [0, 0.2, 0.3, 0.4, 0.5, 0.6, 1.01]
    nomes = ["<0,2", "0,2-0,3", "0,3-0,4", "0,4-0,5", "0,5-0,6", ">=0,6"]
    print(f"{'faixa de P':<10} | {'n(comprar)':>10} {'sobe 1ATR antes%':>17} | {'n(vender)':>10} {'desce 1ATR antes%':>18}")
    cal = cal.copy()
    cal["fc"] = pd.cut(cal.p_c, bins, labels=nomes, right=False)
    cal["fv"] = pd.cut(cal.p_v, bins, labels=nomes, right=False)
    for nm in nomes:
        a, b = cal[cal.fc == nm], cal[cal.fv == nm]
        print(f"{nm:<10} | {len(a):>10} {br(100 * a.sobe.mean() if len(a) else float('nan'), 1):>17} | {len(b):>10} {br(100 * b.desce.mean() if len(b) else float('nan'), 1):>18}")
    print(f"{'todas':<10} | {len(cal):>10} {br(100 * cal.sobe.mean(), 1):>17} | {len(cal):>10} {br(100 * cal.desce.mean(), 1):>18}   (base: sem informacao do Jev)", flush=True)


# --------------------------------------------------------------------------- main
def avalia_pasta(nome, pasta: Path, args, mk, ctx):
    sess = carrega(pasta)
    if not sess:
        print(f"{nome}: sem sessoes em {pasta}")
        return None
    custo = json.loads((pasta / "_custo.json").read_text()) if (pasta / "_custo.json").exists() else {}
    lim = sess[0].get("limiar")
    print("=" * 100)
    print(f"{nome}: {len(sess)} dias ({sess[0]['data']} a {sess[-1]['data']}) | modelo {sess[0].get('modelo_pedido')} | limiar da execucao {lim} "
          f"({sess[0].get('modo_entrada', 'argmax')}) | custo Jev US$ {br(sum(s['custo_usd'] for s in sess), 4)} "
          f"| dias com falha de API: {sum(1 for s in sess if s.get('n_falhas'))}")
    P = painel(sess)
    print("\nPAINEL (execucao real, " + REF_ESCADA + ")")
    tabela([(nome, P)])
    print("\nPor trimestre:")
    tabela(por_trimestre(sess))
    res = dict(painel=P, trimestres={q: m for q, m in por_trimestre(sess)})
    # nulos
    total = P["total"]
    if not args.sem_nulo:
        t0 = time.time()
        nulo = nulo_aleatorio(sess, args.sorteios, args.workers)
        res["nulo_aleatorio"] = dict(media=float(nulo.mean()), p5=float(np.percentile(nulo, 5)), p95=float(np.percentile(nulo, 95)),
                                     pct_jev_ge=float(100 * (total >= nulo).mean()), p_nulo=float((nulo >= total).mean()), sorteios=int(args.sorteios))
        print(f"\nNULOS ({time.time() - t0:.0f}s)\n  (a) ficar de fora: R$ 0,00 | Jev R$ {br(total)}")
        print(f"  (b) {args.sorteios} sorteios, {P['ops']} entradas em velas/lados aleatorios, mesma geometria (stop, alvo, mão, trailing): "
              f"média R$ {br(nulo.mean())} | p5 {br(np.percentile(nulo, 5))} p95 {br(np.percentile(nulo, 95))} | "
              f"p (nulo >= Jev) = {br((nulo >= total).mean(), 3)}", flush=True)
    # re-limiar
    rl = relimiar(mk, ctx, sess, LIMIARES)
    chk = [L for L in LIMIARES if lim is not None and abs(L - lim) < 1e-9]
    print("\nRE-LIMIAR OFFLINE (re-simulado com as respostas logadas; modo argmax: escolha = comprar/vender com P >= limiar)")
    print("  aproximação: entradas exatas; gestão (parar/zerar/stop no pivô) só existe nas velas em que a posição ORIGINAL estava aberta")
    tabela([(f"limiar {L}", rl[L]) for L in LIMIARES])
    if chk:
        d = abs(rl[chk[0]]["total"] - total)
        print(f"  conferência: re-simulação a {chk[0]} = R$ {br(rl[chk[0]]['total'])} vs execução real R$ {br(total)} (dif {br(d)})")
    res["relimiar"] = {str(L): m for L, m in rl.items()}
    rl2 = relimiar(mk, ctx, sess, (0.3, 0.4, 0.5, 0.6), modo="lado")
    print("\nRE-LIMIAR, modo 'lado' (compara só comprar x vender, ignora 'fora'; P do lado vencedor >= limiar)")
    tabela([(f"limiar {L}", rl2[L]) for L in rl2])
    res["relimiar_lado"] = {str(L): m for L, m in rl2.items()}
    # diagnostico
    df = planifica(sess)
    cor = diagnostico(df)
    print(f"\nDIAGNÓSTICO: o que o Jev 'olha' (correlação de Spearman, {len(df)} velas; alvo = P(comprar)-P(vender) e P(fora))")
    top = cor.reindex(cor.corr_lado.abs().sort_values(ascending=False).index).head(15)
    print(f"  {'pergunta':<22} {'corr c/ lado':>13} {'corr c/ fora':>13}")
    for q, r in top.iterrows():
        print(f"  {q:<22} {br(r.corr_lado, 2):>13} {br(r.corr_fora, 2):>13}")
    top2 = cor.reindex(cor.corr_fora.abs().sort_values(ascending=False).index).head(8)
    print("  mais ligadas a 'ficar de fora':", ", ".join(f"{q} ({br(r.corr_fora, 2)})" for q, r in top2.iterrows()))
    res["diag_top"] = {q: dict(lado=float(r.corr_lado), fora=float(r.corr_fora)) for q, r in top.iterrows()}
    # calibracao
    cal = calibracao(mk, ctx, sess)
    print(f"\nCALIBRAÇÃO ({len(cal)} velas resolvidas): quando o Jev dá P(lado)=p, o preço toca 1 ATR a favor antes de 1 ATR contra?")
    tab_calibracao(cal)
    res["calibracao_n"] = len(cal)
    (pasta / "_avaliacao.json").write_text(json.dumps(res, ensure_ascii=False, default=float), encoding="utf-8")
    # resumo p/ o viewer (compativel com o template antigo)
    resumo = dict(total=dict(ops=P["ops"], acerto=P["acerto"], total=P["total"]), custo_llm=sum(s["custo_usd"] for s in sess),
                  chamadas=int(custo.get("chamadas", 0)), modelos=custo.get("modelos", {}), nulo_ficar_fora=0.0,
                  nulo_aleatorio=res.get("nulo_aleatorio", dict(media=0, p5=0, p95=0, pct_jev_ge=0, sorteios=0)),
                  painel=P, relimiar=res["relimiar"], trimestres=res["trimestres"], dias=[s["data"] for s in sess])
    (pasta / "_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, default=float), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", action="append", required=True)
    ap.add_argument("--sorteios", type=int, default=300)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sem-nulo", action="store_true")
    args = ap.parse_args()
    from mercado import Mercado
    from decisoes import Ctx
    mk = Mercado.carregar()
    ctx = Ctx(mk)
    for p in args.pasta:
        avalia_pasta(Path(p).name, Path(p), args, mk, ctx)


if __name__ == "__main__":
    main()
