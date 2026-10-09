"""Analise da rodada v3: painel v3 x v1 nos MESMOS dias, pareado, nulo, quebras, zerar mercado x limitado, capital, dias ruins.
Uso: python analisa_rodada.py --pasta ../sessoes_v3/R50 --dias ../rodada_v3_dias.json [--sorteios 300] [--workers 6] [--sem-nulo]
Grava ../analise_R50.json e ../dias_ruins_v3.json (com --gravar-dias-ruins)."""
from __future__ import annotations
import argparse
import json
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comum import EXP, PAI  # noqa: E402
import avaliar as av  # noqa: E402

CAIXA_POR_CONTRATO = 1000.0
CAIXA_INI = 2000.0
LIM_DIF_RUIM = -300.0     # "muito abaixo do v1": v3 - v1 <= -R$300 no dia (declarado antes de olhar)


def br(x, nd=0):
    return av.br(x, nd)


# ---------------------------------------------------------------- estatistica
def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c
        c = c if abs(c) > 1e-30 else 1e-30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c
        c = c if abs(c) > 1e-30 else 1e-30
        de = d * c
        h *= de
        if abs(de - 1) < 1e-12:
            break
    return h


def betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    return bt * _betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * _betacf(b, a, 1 - x) / b


def p_t(t, df):
    """p bicaudal da t de Student."""
    return betainc(df / 2, 0.5, df / (df + t * t))


def pareado(dif, seed=7, B=10000):
    dif = np.asarray(dif, float)
    n = len(dif)
    m = dif.mean()
    sd = dif.std(ddof=1)
    t = m / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    rng = np.random.default_rng(seed)
    bs = np.array([rng.choice(dif, n).mean() for _ in range(B)])
    flips = np.array([(dif * rng.choice([-1, 1], n)).mean() for _ in range(B)])
    return dict(n=n, media=float(m), ic95=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))], t=float(t), p_t=float(p_t(t, n - 1)),
                p_signflip=float((np.abs(flips) >= abs(m)).mean()), dias_melhor=int((dif > 0).sum()), dias_pior=int((dif < 0).sum()))


# ---------------------------------------------------------------- carga
def carrega_tudo(pasta: Path, dias):
    v = {"M": {}, "L": {}, "v1": {}}
    for d in dias:
        for var in ("M", "L"):
            f = pasta / var / f"{d['data']}.json"
            if f.exists():
                v[var][d["data"]] = json.loads(f.read_text(encoding="utf-8"))
        v["v1"][d["data"]] = json.loads((PAI / "sessoes_dec" / d["periodo"] / f"{d['data']}.json").read_text(encoding="utf-8"))
    return v


def total_dia(s):
    return float(sum(t["brl"] for t in s["trades"]))


def painel_x(sess):
    P = av.painel(sess)
    tot = [total_dia(s) for s in sess]
    P["pior_dia"] = min(tot) if tot else 0.0
    P["dias_pos"] = int(sum(1 for x in tot if x > 0))
    P["dias_neg"] = int(sum(1 for x in tot if x < 0))
    P["dias_zero"] = int(sum(1 for x in tot if x == 0))
    P["rs_dia"] = P["total"] / len(sess) if sess else float("nan")
    return P


def eficiencia(s):
    b = s["bars"]
    soma = sum(x["h"] - x["l"] for x in b)
    return abs(b[-1]["c"] - b[0]["o"]) / soma if soma > 0 else float("nan"), (1 if b[-1]["c"] >= b[0]["o"] else -1)


def tipo_dia(e):
    return "rotacao (<0,15)" if e < 0.15 else ("intermediario (0,15-0,30)" if e < 0.30 else "direcional (>=0,30)")


# ---------------------------------------------------------------- capital
def capital(trades_dias, caixa_ini=CAIXA_INI):
    """trades_dias: lista (data, [trades]) em ordem cronologica. Sizing da escada: caixa >= 2.000 -> ate 2 contratos; < 2.000 -> 1; < 1.000 -> para.
    Cada trade e reescalado: brl/n * n_efetivo (n = maos pedidas pelo Jev). Aproximacao: as decisoes do Jev nao mudam com o tamanho."""
    caixa = caixa_ini
    parou = None
    curva, pulados, abaixo_piso, abaixo_1000 = [], 0, 0, 0
    for data, trs in trades_dias:
        for t in sorted(trs, key=lambda x: x["t_sai"]):
            cap = 2 if caixa >= 2 * CAIXA_POR_CONTRATO else (1 if caixa >= CAIXA_POR_CONTRATO else 0)
            if cap == 0:
                parou = parou or data
                pulados += 1
                continue
            n = min(int(t["n"]), cap)
            caixa += t["brl"] / t["n"] * n
        curva.append((data, caixa))
        if caixa < 2 * CAIXA_POR_CONTRATO:
            abaixo_piso += 1
        if caixa < CAIXA_POR_CONTRATO:
            abaixo_1000 += 1
    cx = [c for _, c in curva]
    return dict(final=caixa, minimo=min(cx) if cx else caixa_ini, maximo=max(cx) if cx else caixa_ini, dias_abaixo_2000=abaixo_piso, dias_abaixo_1000=abaixo_1000,
                parou_em=parou, trades_pulados=pulados, curva=curva)


# ---------------------------------------------------------------- dias ruins
def entrada_info(s, t):
    """Respostas do Jev na vela da decisao que gerou o trade (ultima entrada do mesmo lado antes do fill)."""
    lado = "comprar_limite" if t["lado"] == "compra" else "vender_limite"
    cand = [p for p in s["pontos"] if p["decisao"].get("acao") == lado and p["k"] < t["k_ent"]]
    if not cand:
        return {}
    p = cand[-1]
    m = p["jev"].get("m") or {}
    r = dict(t=p["t"])
    for q in ("v2_dia_tipo", "v2_preco_vs_ref", "v2_rompe_dia", "v2_seguimento", "v2_swing_rompido"):
        if q in m:
            r[q.replace("v2_", "")] = f"{m[q]['c']} ({m[q]['p'][m[q]['c']]:.2f})"
    for q in ("v2_lateral_morta", "v2_perna_esgotada", "v2_tendencia_limpa"):
        if q in m:
            r[q.replace("v2_", "")] = round(float(m[q]), 2)
    if "acao" in m:
        r["acao_p"] = {k: round(v, 2) for k, v in m["acao"]["p"].items()}
    for q in ("stop", "alvo", "mao"):
        if q in m:
            r[q] = m[q]["c"]
    return r


def diag_dia(data, s3, s1, ef, sinal):
    tr = s3["trades"]
    partes = []
    for t in tr:
        info = entrada_info(s3, t)
        partes.append(dict(lado=t["lado"], n=t["n"], ent=t["t_ent"], sai=t["t_sai"], motivo=t["motivo"], brl=round(t["brl"], 1), respostas=info))
    tot3 = total_dia(s3)
    tot1 = total_dia(s1)
    linha = (f"{data}: v3 R$ {tot3:+.0f} ({len(tr)} ops) x v1 R$ {tot1:+.0f} ({len(s1['trades'])} ops) | dia {'alta' if sinal > 0 else 'baixa'}, eficiencia {ef:.2f} ({tipo_dia(ef).split(' ')[0]}) | ")
    if tr:
        mo = {}
        for t in tr:
            mo[t["motivo"]] = mo.get(t["motivo"], 0) + 1
        lados = {}
        for t in tr:
            a = (t["lado"], "a favor do dia" if (1 if t["lado"] == "compra" else -1) == sinal else "contra o dia")
            lados[a] = lados.get(a, 0) + 1
        linha += "entradas " + ", ".join(f"{n}x {l[0]} {l[1]}" for l, n in lados.items()) + "; saidas " + ", ".join(f"{n}x {k}" for k, n in mo.items())
        e = partes[0]["respostas"]
        if e:
            linha += f" | 1a entrada {partes[0]['ent']}: dia_tipo={e.get('dia_tipo')}, preco_vs_ref={e.get('preco_vs_ref')}, tendencia_limpa={e.get('tendencia_limpa')}, perna_esgotada={e.get('perna_esgotada')}"
    else:
        linha += "nenhuma operacao"
    return linha, partes


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default=str(EXP / "sessoes_v3" / "R50"))
    ap.add_argument("--dias", default=str(EXP / "rodada_v3_dias.json"))
    ap.add_argument("--sorteios", type=int, default=300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sem-nulo", action="store_true")
    ap.add_argument("--saida", default=str(EXP / "analise_R50.json"))
    ap.add_argument("--gravar-dias-ruins", action="store_true")
    a = ap.parse_args()
    dias = json.load(open(a.dias, encoding="utf-8"))["dias"]
    V = carrega_tudo(Path(a.pasta), dias)
    datas = [d["data"] for d in sorted(dias, key=lambda x: x["data"]) if d["data"] in V["M"] and d["data"] in V["L"]]
    print(f"{len(datas)} dias completos de {len(dias)}")
    S = {k: [V[k][d] for d in datas] for k in ("M", "L", "v1")}
    out = dict(n_dias=len(datas))
    P = {k: painel_x(S[k]) for k in S}
    nome = {"v1": "v1 (54 perguntas)", "M": "v3 (zerar a mercado)", "L": "v3 (zerar limitado)"}
    print("\n== PAINEL (mesmos dias) ==")
    print(f"{'':<24} {'total R$':>10} {'ops':>5} {'acerto%':>8} {'F.lucro':>8} {'pior queda':>11} {'pior dia':>9} {'dias +':>7} {'R$/dia':>8} {'custo US$':>10}")
    for k in ("v1", "M", "L"):
        p = P[k]
        custo = sum(s.get("custo_usd", 0) for s in S[k]) if k != "L" else sum(s.get("custo_usd", 0) for s in S["M"])
        print(f"{nome[k]:<24} {br(p['total']):>10} {p['ops']:>5} {br(p['acerto'], 1):>8} {br(p['fator_lucro'], 2):>8} {br(p['dd']):>11} {br(p['pior_dia']):>9} "
              f"{p['dias_pos']:>3}/{p['dias']:<3} {br(p['rs_dia']):>8} {br(custo, 3):>10}")
        out.setdefault("painel", {})[k] = p
    # pareado
    tot = {k: np.array([total_dia(s) for s in S[k]]) for k in S}
    print("\n== PAREADO POR DIA (diferenca de R$/dia) ==")
    out["pareado"] = {}
    for nm, d in (("v3(M) - v1", tot["M"] - tot["v1"]), ("v3(L) - v1", tot["L"] - tot["v1"]), ("v3(L) - v3(M)", tot["L"] - tot["M"])):
        r = pareado(d)
        out["pareado"][nm] = r
        print(f"{nm:<14} media R$ {br(r['media'], 1):>8}/dia | IC95 bootstrap [{br(r['ic95'][0], 1)} ; {br(r['ic95'][1], 1)}] | t = {r['t']:.2f} (p = {r['p_t']:.3f}) | p sign-flip {r['p_signflip']:.3f} | melhor em {r['dias_melhor']} dias, pior em {r['dias_pior']}")
    # nulo
    if not a.sem_nulo:
        print("\n== NULO: entradas aleatorias com a mesma geometria (avaliar.nulo_aleatorio) ==")
        out["nulo"] = {}
        for k in ("M", "v1"):
            nl = av.nulo_aleatorio(S[k], a.sorteios, a.workers)
            tt = P[k]["total"]
            out["nulo"][k] = dict(media=float(nl.mean()), p5=float(np.percentile(nl, 5)), p95=float(np.percentile(nl, 95)), p_nulo=float((nl >= tt).mean()), total=tt, sorteios=a.sorteios)
            print(f"{nome[k]:<24} total R$ {br(tt)} | nulo: media R$ {br(nl.mean())}, p5 {br(np.percentile(nl, 5))}, p95 {br(np.percentile(nl, 95))} | p(nulo >= real) = {br((nl >= tt).mean(), 3)}  ({a.sorteios} sorteios)", flush=True)
    # quebras
    efs = {d: eficiencia(V["v1"][d]) for d in datas}
    per = {d["data"]: d["periodo"] for d in dias}

    def quebra(titulo, chave, ordem=None):
        grupos = {}
        for d in datas:
            grupos.setdefault(chave(d), []).append(d)
        print(f"\n== {titulo} ==")
        print(f"{'grupo':<26} {'dias':>4} | {'v1 R$':>8} {'v3 R$':>8} {'dif R$/dia':>11} | {'ops v1':>6} {'ops v3':>6} | {'acerto v1':>9} {'acerto v3':>9}")
        res = {}
        for g in (ordem or sorted(grupos)):
            if g not in grupos:
                continue
            ds = grupos[g]
            s1, s3 = [V["v1"][d] for d in ds], [V["M"][d] for d in ds]
            p1, p3 = painel_x(s1), painel_x(s3)
            dif = np.mean([total_dia(V["M"][d]) - total_dia(V["v1"][d]) for d in ds])
            res[g] = dict(dias=len(ds), v1=p1["total"], v3=p3["total"], dif_dia=float(dif), ops1=p1["ops"], ops3=p3["ops"], ac1=p1["acerto"], ac3=p3["acerto"])
            print(f"{g:<26} {len(ds):>4} | {br(p1['total']):>8} {br(p3['total']):>8} {br(dif):>11} | {p1['ops']:>6} {p3['ops']:>6} | {br(p1['acerto'], 1):>9} {br(p3['acerto'], 1):>9}")
        out.setdefault("quebras", {})[titulo] = res

    quebra("POR TRIMESTRE", lambda d: av.trimestre(d))
    quebra("POR PERIODO (IS/OOS)", lambda d: per[d])
    quebra("POR TIPO DE DIA (eficiencia do dia, ex-post)", lambda d: tipo_dia(efs[d][0]),
           ["rotacao (<0,15)", "intermediario (0,15-0,30)", "direcional (>=0,30)"])
    quebra("POR DIRECAO DO DIA", lambda d: "alta" if efs[d][1] > 0 else "baixa")
    # zerar
    print("\n== SAIDAS POR MOTIVO (v3, zerar a mercado) x v1 ==")
    out["motivos"] = {}
    for k in ("v1", "M", "L"):
        mo = {}
        for s in S[k]:
            for t in s["trades"]:
                m = t["motivo"].split(" (gap")[0]
                x = mo.setdefault(m, [0, 0.0])
                x[0] += 1
                x[1] += t["brl"]
        n = sum(v[0] for v in mo.values())
        out["motivos"][k] = {m: dict(n=v[0], brl=v[1]) for m, v in mo.items()}
        print(f"-- {nome[k]} ({n} saidas)")
        for m, v in sorted(mo.items(), key=lambda x: -x[1][0]):
            print(f"   {m:<28} n {v[0]:>4} ({100 * v[0] / n:4.0f}%) | total R$ {br(v[1]):>8} | medio R$ {br(v[1] / v[0], 1):>7}")
    ped = sum(1 for s in S["L"] for e in s["eventos"] if e["tipo"] == "zerar_limite")
    exp = sum(1 for s in S["L"] for e in s["eventos"] if e["tipo"] == "expirada" and "saida limitada" in e["texto"])
    print(f"\nzerar limitado: {ped} pedidos, {ped - exp} encheram, {exp} expiraram sem encher (stop seguiu)")
    out["zerar_limitado"] = dict(pedidos=ped, expiraram=exp)
    # capital
    print("\n== CAPITAL (sizing da escada: R$ 1.000/contrato, max 2, inicio R$ 2.000; < R$ 2.000 -> 1 contrato; < R$ 1.000 -> para) ==")
    out["capital"] = {}
    for k in ("M", "L", "v1"):
        c = capital([(d, V[k][d]["trades"]) for d in datas])
        out["capital"][k] = c
        print(f"{nome[k]:<24} final R$ {br(c['final'])} | minimo R$ {br(c['minimo'])} | maximo R$ {br(c['maximo'])} | dias terminados abaixo de R$ 2.000: {c['dias_abaixo_2000']} | abaixo de R$ 1.000: {c['dias_abaixo_1000']} | parou: {c['parou_em']} ({c['trades_pulados']} trades pulados)")
    print("\ncurva de caixa v3 (zerar a mercado) fim de dia:")
    print("  " + " | ".join(f"{d} {br(c)}" for d, c in out["capital"]["M"]["curva"]))
    # dias ruins
    ruins = []
    for d in datas:
        t3, t1 = total_dia(V["M"][d]), total_dia(V["v1"][d])
        if t3 < 0 or t3 - t1 <= LIM_DIF_RUIM:
            ruins.append(d)
    print(f"\n== DIAS RUINS DA v3: total < 0 ou v3 - v1 <= R$ {LIM_DIF_RUIM:.0f} ({len(ruins)} de {len(datas)}) ==")
    dr = []
    for d in ruins:
        ef, sg = efs[d]
        linha, partes = diag_dia(d, V["M"][d], V["v1"][d], ef, sg)
        print(" - " + linha)
        dr.append(dict(data=d, periodo=per[d], v3_brl=total_dia(V["M"][d]), v1_brl=total_dia(V["v1"][d]), eficiencia_dia=ef, direcao_dia="alta" if sg > 0 else "baixa",
                       motivo_ruim=("v3 negativo" if total_dia(V["M"][d]) < 0 else "") + (" e " if total_dia(V["M"][d]) < 0 and total_dia(V["M"][d]) - total_dia(V["v1"][d]) <= LIM_DIF_RUIM else "")
                       + ("muito abaixo do v1" if total_dia(V["M"][d]) - total_dia(V["v1"][d]) <= LIM_DIF_RUIM else ""),
                       diagnostico=linha, trades_v3=partes,
                       trades_v1=[dict(lado=t["lado"], n=t["n"], ent=t["t_ent"], sai=t["t_sai"], motivo=t["motivo"], brl=round(t["brl"], 1)) for t in V["v1"][d]["trades"]]))
    out["dias_ruins"] = [x["data"] for x in dr]
    if a.gravar_dias_ruins:
        (EXP / "dias_ruins_v3.json").write_text(json.dumps(dict(criterio=f"v3 (zerar a mercado) com total < 0, ou v3 - v1 <= R$ {LIM_DIF_RUIM:.0f} no dia (declarado antes de olhar)", n=len(dr), dias=dr),
                                                           ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    out["por_dia"] = [dict(data=d, periodo=per[d], v1=total_dia(V["v1"][d]), v3M=total_dia(V["M"][d]), v3L=total_dia(V["L"][d]), ef=efs[d][0], ops1=len(V["v1"][d]["trades"]), ops3=len(V["M"][d]["trades"])) for d in datas]
    out["custo_v3_usd"] = sum(s.get("custo_usd", 0) for s in S["M"])
    out["custo_v1_usd_ref"] = sum(s.get("custo_usd", 0) for s in S["v1"])
    Path(a.saida).write_text(json.dumps(out, ensure_ascii=False, default=float, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
