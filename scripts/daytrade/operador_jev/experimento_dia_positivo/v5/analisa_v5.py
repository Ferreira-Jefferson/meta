"""Analise da rodada v5: v3 viva (sem regras no pacote) + as 4 regras deterministicas por cima (resimulacao com respostas logadas). Criterio pre-fixado em RODADAS.md.
Uso: python analisa_v5.py [--sorteios 300] [--workers 6] [--sem-nulo]"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
for p in (str(AQUI), str(EXP / "v4"), str(EXP / "v3"), str(EXP.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)
import analisa_rodada as ar  # noqa: E402
import avaliar as av  # noqa: E402
import nulo_v5 as n5  # noqa: E402
from decisoes_v4 import CFG_V4, decisao_entrada_v4, decisao_gestao_v4  # noqa: E402
from decisoes import Ctx  # noqa: E402
from mercado import Mercado  # noqa: E402
from sessao_l import SessaoL  # noqa: E402
from rodar_v3 import run_cls  # noqa: E402
from comum import PAI  # noqa: E402

br = av.br
LIM_DIF_RUIM = -300.0
CFG_OFF = dict(CFG_V4, portao=False, risco=False, reentrada=False, guarda_gestao=False)


def resim5(mk, ctx, dia, s3, cfg, limiar=0.3):
    """Entradas = respostas da etapa 2 da v3 (logadas); gestao = `g_acao` logada da v3; sem resposta -> manter."""
    M3 = {p["k"]: p["jev"].get("m") for p in s3["pontos"]}
    G = {p["k"]: p["jev"].get("g") for p in s3["pontos"]}
    pts = []

    def decidir(k, s):
        if s.pos:
            if getattr(s, "exit_pend", None):
                return dict(acao="manter"), {}
            d, i = decisao_gestao_v4(G.get(k), ctx, dia, k, s.pos, cfg)
        elif s.pend:
            return dict(acao="manter"), {}
        else:
            rm = M3.get(k)
            if not rm:
                return dict(acao="ficar_fora"), {}
            d, i = decisao_entrada_v4(rm, ctx, dia, k, limiar, s.trades, cfg)
        pts.append(dict(k=k, decisao=d))
        return d, i
    s, _ = run_cls(mk, dia, decidir, SessaoL)
    return s, pts


def sim(mk, ctx, dias, S3, cfg, dia_n):
    out = []
    for d in dias:
        dia = mk.dia(d, dia_n[d])
        s, pts = resim5(mk, ctx, dia, S3[d], cfg)
        out.append(dict(data=d, trades=s.trades, ordens=s.ordens, pontos=pts, bars=S3[d]["bars"]))
    return out


def carrega(dias, pasta3):
    S = {"v1": {}, "v3M": {}, "v3L": {}}
    for d in dias:
        dt = d["data"]
        S["v1"][dt] = json.loads((PAI / "sessoes_dec" / d["periodo"] / f"{dt}.json").read_text(encoding="utf-8"))
        for nm, v in (("v3M", "M"), ("v3L", "L")):
            S[nm][dt] = json.loads((pasta3 / v / f"{dt}.json").read_text(encoding="utf-8"))
    return S


def painel_linha(nome, p):
    return (f"{nome:<30} {br(p['total'], 0):>9} {p['ops']:>5} {br(p['acerto'], 1):>8} {br(p['fator_lucro'], 2):>8} {br(p['dd'], 0):>11} {br(p['pior_dia'], 0):>9} "
            f"{p['dias_pos']:>3}/{p['dias']:<3} {br(p['rs_dia'], 0):>8}")


def motivos(sessoes):
    mo = {}
    for s in sessoes:
        for t in s["trades"]:
            m = t["motivo"].split(" (gap")[0]
            x = mo.setdefault(m, [0, 0.0])
            x[0] += 1
            x[1] += t["brl"]
    return mo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sorteios", type=int, default=300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sem-nulo", action="store_true")
    a = ap.parse_args()
    out = {}
    mk = Mercado.carregar()
    ctx = Ctx(mk)
    dias = json.load(open(EXP / "rodada_v5_dias.json", encoding="utf-8"))["dias"]
    per = {d["data"]: d["periodo"] for d in dias}
    S = carrega(dias, EXP / "sessoes_v3/R50v5")
    datas = sorted(per)
    dia_n = {d: S["v3L"][d].get("dia_n", 1) for d in datas}
    v5 = sim(mk, ctx, datas, S["v3L"], CFG_V4, dia_n)
    chk = sim(mk, ctx, datas, S["v3L"], CFG_OFF, dia_n)
    L = {"v1": [S["v1"][d] for d in datas], "v3M": [S["v3M"][d] for d in datas], "v3L": [S["v3L"][d] for d in datas], "v5": v5}
    P = {k: ar.painel_x(L[k]) for k in L}
    nome = {"v1": "v1 (54 perguntas)", "v3M": "v3 (zerar a mercado)", "v3L": "v3 (zerar limitado)", "v5": "v5 (v3 + 4 regras motor)"}
    chk_tot = sum(sum(t["brl"] for t in s["trades"]) for s in chk)
    print(f"{len(datas)} dias; checagem: v3 resimulada sem regras = R$ {br(chk_tot, 0)} x v3 L vivo R$ {br(P['v3L']['total'], 0)}")
    out["checagem_v3_resim"] = chk_tot
    print("\n== PAINEL (mesmos dias) ==")
    print(f"{'':<30} {'total R$':>9} {'ops':>5} {'acerto%':>8} {'F.lucro':>8} {'pior queda':>11} {'pior dia':>9} {'dias +':>7} {'R$/dia':>8}")
    for k in ("v1", "v3M", "v3L", "v5"):
        print(painel_linha(nome[k], P[k]))
    out["painel"] = P
    tot = {k: np.array([ar.total_dia(s) for s in L[k]]) for k in L}
    print("\n== PAREADO POR DIA ==")
    out["pareado"] = {}
    for nm, d in (("v5 - v1", tot["v5"] - tot["v1"]), ("v5 - v3(L)", tot["v5"] - tot["v3L"]), ("v3(L) - v1", tot["v3L"] - tot["v1"])):
        r = ar.pareado(d)
        out["pareado"][nm] = r
        print(f"{nm:<12} media R$ {br(r['media'], 1):>8}/dia | IC95 [{br(r['ic95'][0], 1)} ; {br(r['ic95'][1], 1)}] | t = {r['t']:.2f} | p sign-flip {r['p_signflip']:.3f} | melhor em {r['dias_melhor']}, pior em {r['dias_pior']}")
    out["nulo"] = {}
    tt = P["v5"]["total"]
    if not a.sem_nulo:
        print("\n== NULOS ==")
        nl = av.nulo_aleatorio(L["v5"], a.sorteios, a.workers)
        out["nulo"]["livre"] = dict(media=float(nl.mean()), p5=float(np.percentile(nl, 5)), p95=float(np.percentile(nl, 95)), p_nulo=float((nl >= tt).mean()))
        print(f"nulo LIVRE (qualquer vela, 2 lados, sem regras)  v5 R$ {br(tt, 0)} | media {br(nl.mean(), 0)}, p5 {br(np.percentile(nl, 5), 0)}, p95 {br(np.percentile(nl, 95), 0)} | p(nulo >= v5) = {br((nl >= tt).mean(), 3)}", flush=True)
        cands = n5.candidatos(mk, [pd.Timestamp(d) for d in datas])
        cands = {str(pd.Timestamp(k).date()): v for k, v in cands.items()}
        npar = sum(len(v) for v in cands.values())
        ng, ngeo = n5.nulo(v5, cands, a.sorteios, a.workers)
        out["nulo"]["com_portao_e_regras"] = dict(media=float(ng.mean()), p5=float(np.percentile(ng, 5)), p95=float(np.percentile(ng, 95)), p_nulo=float((ng >= tt).mean()),
                                                  velas_que_passam=npar, geometrias=ngeo)
        print(f"nulo COM PORTAO+REGRAS ({npar} pares dia-vela passam, {ngeo} geom.)  v5 R$ {br(tt, 0)} | media {br(ng.mean(), 0)}, p5 {br(np.percentile(ng, 5), 0)}, p95 {br(np.percentile(ng, 95), 0)} | p(nulo >= v5) = {br((ng >= tt).mean(), 3)}", flush=True)
    efs = {d: ar.eficiencia(S["v1"][d]) for d in datas}
    byd = dict(zip(datas, v5))

    def quebra(titulo, chave, ordem):
        print(f"\n== {titulo} ==")
        print(f"{'grupo':<28} {'dias':>4} | {'v1 R$':>7} {'v3L R$':>7} {'v5 R$':>7} | {'ops v1':>6} {'v3':>4} {'v5':>4} | {'acerto v1':>9} {'v3':>5} {'v5':>5}")
        res = {}
        for g in ordem:
            ds = [d for d in datas if chave(d) == g]
            if not ds:
                continue
            pp = {"v1": ar.painel_x([S["v1"][d] for d in ds]), "v3L": ar.painel_x([S["v3L"][d] for d in ds]), "v5": ar.painel_x([byd[d] for d in ds])}
            res[g] = dict(dias=len(ds), **{k: pp[k]["total"] for k in pp}, ops={k: pp[k]["ops"] for k in pp})
            print(f"{g:<28} {len(ds):>4} | {br(pp['v1']['total'], 0):>7} {br(pp['v3L']['total'], 0):>7} {br(pp['v5']['total'], 0):>7} | {pp['v1']['ops']:>6} {pp['v3L']['ops']:>4} {pp['v5']['ops']:>4} | "
                  f"{br(pp['v1']['acerto'], 1):>9} {br(pp['v3L']['acerto'], 1):>5} {br(pp['v5']['acerto'], 1):>5}")
        out.setdefault("quebras", {})[titulo] = res
    quebra("POR TIPO DE DIA (ex-post)", lambda d: ar.tipo_dia(efs[d][0]), ["rotacao (<0,15)", "intermediario (0,15-0,30)", "direcional (>=0,30)"])
    quebra("POR PERIODO", lambda d: per[d], ["OOS", "IS"])
    print("\n== SAIDAS POR MOTIVO ==")
    out["motivos"] = {}
    for k in ("v1", "v3L", "v5"):
        mo = motivos(L[k])
        n = sum(v[0] for v in mo.values())
        out["motivos"][k] = {m: dict(n=v[0], brl=v[1]) for m, v in mo.items()}
        print(f"-- {nome[k]} ({n} saidas)")
        for m, v in sorted(mo.items(), key=lambda x: -x[1][0]):
            print(f"   {m:<28} n {v[0]:>4} ({100 * v[0] / max(n, 1):4.0f}%) | total R$ {br(v[1], 0):>7} | medio R$ {br(v[1] / v[0], 1):>7}")
    gs = [t["brl"] for s in v5 for t in s["trades"] if t["brl"] > 0]
    ps = [-t["brl"] for s in v5 for t in s["trades"] if t["brl"] <= 0]
    ganho = float(np.mean(gs)) if gs else 0.0
    perda = float(np.mean(ps)) if ps else 0.0
    be = perda / (ganho + perda) if ganho + perda else float("nan")
    out["breakeven_empirico_v5"] = dict(ganho_medio=ganho, perda_media=perda, breakeven=be, acerto=P["v5"]["acerto"])
    print(f"\nv5: ganho medio R$ {br(ganho, 1)} | perda media R$ {br(perda, 1)} | breakeven empirico {br(100 * be, 1)}% | acerto {br(P['v5']['acerto'], 1)}%")
    print("\n== CAIXA (escada, R$ 2.000) ==")
    out["capital"] = {}
    for k in ("v1", "v3L", "v5"):
        c = ar.capital([(d, s["trades"]) for d, s in zip(datas, L[k])])
        out["capital"][k] = c
        print(f"{nome[k]:<30} final R$ {br(c['final'], 0)} | min R$ {br(c['minimo'], 0)} | max R$ {br(c['maximo'], 0)} | dias < 2.000: {c['dias_abaixo_2000']} | < 1.000: {c['dias_abaixo_1000']} | parou: {c['parou_em']} ({c['trades_pulados']} pulados)")
    pr = out["pareado"]["v5 - v1"]
    cr = dict(a_pareado_v5_v1_p=pr["p_signflip"], a_ok=bool(pr["p_signflip"] < 0.10), b_total=P["v5"]["total"], b_ok=bool(P["v5"]["total"] > 0),
              c_dd_v5=P["v5"]["dd"], c_dd_v1=P["v1"]["dd"], c_ok=bool(P["v5"]["dd"] <= P["v1"]["dd"]))
    if "com_portao_e_regras" in out["nulo"]:
        cr["d_p_nulo"] = out["nulo"]["com_portao_e_regras"]["p_nulo"]
        cr["d_ok"] = bool(cr["d_p_nulo"] < 0.10)
        cr["passou"] = bool(cr["a_ok"] and cr["b_ok"] and cr["c_ok"] and cr["d_ok"])
    out["criterio"] = cr
    print("\n== CRITERIO PRE-FIXADO ==")
    for k, v in cr.items():
        print(f"   {k}: {v}")
    ruins = [d for d in datas if ar.total_dia(byd[d]) < 0 or ar.total_dia(byd[d]) - ar.total_dia(S["v1"][d]) <= LIM_DIF_RUIM]
    print(f"\n== DIAS RUINS DA v5 ({len(ruins)} de {len(datas)}) ==")
    dr = []
    for d in ruins:
        ef, sg = efs[d]
        tr = byd[d]["trades"]
        mo = {}
        for t in tr:
            m = t["motivo"].split(" (gap")[0]
            x = mo.setdefault(m, [0, 0.0])
            x[0] += 1
            x[1] += t["brl"]
        af = sum(1 for t in tr if (1 if t["lado"] == "compra" else -1) == sg)
        linha = f"{d}: v5 R$ {ar.total_dia(byd[d]):+.0f} ({len(tr)} ops) | v3 {ar.total_dia(S['v3L'][d]):+.0f} | v1 {ar.total_dia(S['v1'][d]):+.0f} | dia {'alta' if sg > 0 else 'baixa'} ef {ef:.2f}"
        if tr:
            pior = min(tr, key=lambda t: t["brl"])
            causa = min(mo, key=lambda m: mo[m][1])
            linha += (" | saidas " + ", ".join(f"{n}x {m} ({b:+.0f})" for m, (n, b) in mo.items()) + f" | {af}/{len(tr)} a favor do lado final do dia | pior {pior['t_ent']}-{pior['t_sai']} "
                      f"{pior['motivo'].split(' (gap')[0]} R$ {pior['brl']:+.0f} (n={pior['n']}) | causa: "
                      + (("stop em dia de rotacao (ef<0,15)" if ef < 0.15 else "stop em dia que reverteu") if causa.startswith("stop") else f"saidas '{causa}'"))
        else:
            linha += " | nenhuma operacao (perda so vs v1)"
        print(" - " + linha)
        dr.append(dict(data=d, periodo=per[d], v5_brl=ar.total_dia(byd[d]), v3_brl=ar.total_dia(S["v3L"][d]), v1_brl=ar.total_dia(S["v1"][d]), eficiencia_dia=ef, diagnostico=linha,
                       trades_v5=[dict(lado=t["lado"], n=t["n"], ent=t["t_ent"], sai=t["t_sai"], motivo=t["motivo"], brl=round(t["brl"], 1)) for t in tr],
                       trades_v1=[dict(lado=t["lado"], n=t["n"], ent=t["t_ent"], sai=t["t_sai"], motivo=t["motivo"], brl=round(t["brl"], 1)) for t in S["v1"][d]["trades"]]))
    (EXP / "dias_ruins_v5.json").write_text(json.dumps(dict(criterio="v5 total < 0 ou v5 - v1 <= R$ -300 no dia", n=len(dr), dias=dr), ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    out["dias_ruins"] = [x["data"] for x in dr]
    out["custo_v3_usd"] = sum(s.get("custo_usd", 0) for s in L["v3M"])
    print("\n== ESTABILIDADE DESCRITIVA (dentro da amostra; sem chamadas novas) ==")
    out["estabilidade"] = {}
    for rot, f3, pasta in (("50 dias da v3 (R2)", "rodada_v3_dias.json", "sessoes_v3/R50"), ("50 dias da v4", "rodada_v4_dias.json", "sessoes_v3/R50v4")):
        dd_ = json.load(open(EXP / f3, encoding="utf-8"))["dias"]
        S2 = carrega(dd_, EXP / pasta)
        ds2 = sorted(d["data"] for d in dd_)
        dn2 = {d: S2["v3L"][d].get("dia_n", 1) for d in ds2}
        r5 = sim(mk, ctx, ds2, S2["v3L"], CFG_V4, dn2)
        L2 = {"v1": [S2["v1"][d] for d in ds2], "v3L": [S2["v3L"][d] for d in ds2], "v5": r5}
        P2 = {k: ar.painel_x(L2[k]) for k in L2}
        print(f"-- {rot}")
        for k in ("v1", "v3L", "v5"):
            print(painel_linha(nome[k], P2[k]))
        t2 = {k: np.array([ar.total_dia(s) for s in L2[k]]) for k in L2}
        pr1, pr3 = ar.pareado(t2["v5"] - t2["v1"]), ar.pareado(t2["v5"] - t2["v3L"])
        print(f"   v5 - v1 {br(pr1['media'], 1)}/dia IC95 [{br(pr1['ic95'][0], 1)} ; {br(pr1['ic95'][1], 1)}] p {pr1['p_signflip']:.3f} | v5 - v3 {br(pr3['media'], 1)}/dia p {pr3['p_signflip']:.3f}")
        out["estabilidade"][rot] = dict(painel=P2, v5_v1=pr1, v5_v3=pr3)
    Path(EXP / "analise_R50_v5.json").write_text(json.dumps(out, ensure_ascii=False, default=float, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
