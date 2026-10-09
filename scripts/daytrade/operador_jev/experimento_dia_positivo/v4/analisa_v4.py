"""Analise da rodada v4: painel v1 x v3 x v4 nos MESMOS dias, pareados, nulo (livre e COM PORTAO), tipo de dia, saidas por motivo, caixa, ablacao offline, dias ruins.
Uso: python analisa_v4.py [--sorteios 300] [--workers 6] [--sem-nulo]   (grava ../analise_R50_v4.json e ../dias_ruins_v4.json)"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
for p in (str(AQUI), str(EXP / "v3"), str(EXP.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)
import analisa_rodada as ar  # noqa: E402  (v3)
import avaliar as av  # noqa: E402
import regras_v4 as rg  # noqa: E402
import nulo_portao as npt  # noqa: E402
from decisoes_v4 import CFG_V4, decisao_entrada_v4, decisao_gestao_v4  # noqa: E402
from decisoes import Ctx, decisao_entrada, decisao_gestao  # noqa: E402
from mercado import Mercado, _hm  # noqa: E402
from sessao_l import SessaoL  # noqa: E402
from rodar_v3 import run_cls  # noqa: E402
from comum import PAI  # noqa: E402

br = av.br
LIM_DIF_RUIM = -300.0


def carrega(dias):
    S = {k: {} for k in ("v1", "v3M", "v3L", "v4")}
    for d in dias:
        dt = d["data"]
        S["v1"][dt] = json.loads((PAI / "sessoes_dec" / d["periodo"] / f"{dt}.json").read_text(encoding="utf-8"))
        for nome, pasta in (("v3M", EXP / "sessoes_v3/R50v4/M"), ("v3L", EXP / "sessoes_v3/R50v4/L"), ("v4", EXP / "sessoes_v4/R50/L")):
            f = pasta / f"{dt}.json"
            if f.exists():
                S[nome][dt] = json.loads(f.read_text(encoding="utf-8"))
    return S


# ----------------------------------------------------------------------------- resimulacao offline (ablacao)
def resim(mk, ctx, dia, s4, s3, cfg, gestao="v4", portao_jev=False, limiar=0.3, entrada="v4"):
    """Re-roda um dia com as respostas JA LOGADAS (sem rede). Entrada: respostas da v4 na vela; se nao houver (a trajetoria original estava com posicao), usa as da v3
    na mesma vela. Gestao: 'v4' = respostas `v4_g_acao` logadas; 'v3' = respostas `v2_g_acao` da v3 logadas; sem resposta na vela -> manter. Devolve (sessao, n_fallback)."""
    M4 = {p["k"]: p["jev"].get("m") for p in s4["pontos"]}
    G4 = {p["k"]: p["jev"].get("g") for p in s4["pontos"]}
    M3 = {p["k"]: p["jev"].get("m") for p in s3["pontos"]}
    G3 = {p["k"]: p["jev"].get("g") for p in s3["pontos"]}
    fb = [0]

    def decidir(k, s):
        if s.pos:
            if getattr(s, "exit_pend", None):
                return dict(acao="manter"), {}
            rgst = (G4 if gestao == "v4" else G3).get(k)
            return decisao_gestao_v4(rgst, ctx, dia, k, s.pos, cfg)
        if s.pend:
            return dict(acao="manter"), {}
        rm = M4.get(k) if entrada == "v4" else None
        if not rm or "acao" not in rm:
            rm = M3.get(k)
            fb[0] += 1
        if not rm:
            return dict(acao="ficar_fora"), {}
        dec, info = decisao_entrada_v4(rm, ctx, dia, k, limiar, s.trades, cfg)
        if portao_jev and dec["acao"] in ("comprar_limite", "vender_limite"):
            if float(rm.get("v4_direcao_comprovada", 0.0)) < 0.5:
                return dict(acao="ficar_fora"), dict(info, bloq=["portao do Jev: P(sim) < 0,5"])
        return dec, info
    s, _ = run_cls(mk, dia, decidir, SessaoL)
    return s, fb[0]


def sess_de(s_trades, data):
    return dict(data=data, trades=s_trades)


def ablacao(mk, ctx, S, datas):
    cfgs = [
        ("v4 completa (checagem: deve igualar o vivo)", CFG_V4, "v4", False),
        ("v4 sem portao", dict(CFG_V4, portao=False), "v4", False),
        ("v4 sem gestao nova (gestao da v3)", dict(CFG_V4, guarda_gestao=False), "v3", False),
        ("v4 sem guarda determ. da gestao (so o Jev)", dict(CFG_V4, guarda_gestao=False), "v4", False),
        ("v4 sem regra de risco", dict(CFG_V4, risco=False), "v4", False),
        ("v4 sem regra de reentrada/max 3", dict(CFG_V4, reentrada=False), "v4", False),
        ("v4 sem NENHUMA das 4 (aprox. v3)", dict(CFG_V4, portao=False, risco=False, reentrada=False, guarda_gestao=False), "v3", False),
        ("v4 com portao do Jev (P>=0,5) em vez do determ.", dict(CFG_V4, portao=False), "v4", True),
        ("v4 portao 0,15 (sensib. descritiva)", dict(CFG_V4, limiar_er=0.15), "v4", False),
        ("v4 portao 0,25 (sensib. descritiva)", dict(CFG_V4, limiar_er=0.25), "v4", False),
        # entradas = respostas da etapa 2 da v3 (Jev SEM ver o bloco de contexto/regras): isola o efeito da regra deterministica do efeito de o Jev ler a regra
        ("[entr. v3] v3 puro resimulado (checagem ~ v3 L)", dict(CFG_V4, portao=False, risco=False, reentrada=False, guarda_gestao=False), "v3", False, "v3"),
        ("[entr. v3] + so o portao 0,20", dict(CFG_V4, risco=False, reentrada=False, guarda_gestao=False), "v3", False, "v3"),
        ("[entr. v3] + so a reentrada/max 3", dict(CFG_V4, portao=False, risco=False, guarda_gestao=False), "v3", False, "v3"),
        ("[entr. v3] + so a regra de risco 6%", dict(CFG_V4, portao=False, reentrada=False, guarda_gestao=False), "v3", False, "v3"),
        ("[entr. v3] + so a gestao v4 (guarda)", dict(CFG_V4, portao=False, risco=False, reentrada=False), "v4", False, "v3"),
        ("[entr. v3] + as 4 regras (v4 determ. sem o Jev ver)", dict(CFG_V4), "v4", False, "v3"),
        ("[entr. v3] + as 4 regras, sem portao", dict(CFG_V4, portao=False), "v4", False, "v3"),
    ]
    out = []
    for item in cfgs:
        nome, cfg, ges, pj = item[:4]
        ent = item[4] if len(item) > 4 else "v4"
        ss, fbs = [], 0
        for d in datas:
            dia = mk.dia(d, S["v4"][d].get("dia_n", 1))
            s, fb = resim(mk, ctx, dia, S["v4"][d], S["v3L"][d], cfg, ges, pj, entrada=ent)
            ss.append(dict(data=d, trades=s.trades))
            fbs += fb
        out.append((nome, ss, fbs))
    return out


# ----------------------------------------------------------------------------- dias ruins
def diag_v4(d, s4, s1, ef, sinal, s3):
    tr = s4["trades"]
    tot4, tot1, tot3 = ar.total_dia(s4), ar.total_dia(s1), ar.total_dia(s3)
    mo = {}
    for t in tr:
        m = t["motivo"].split(" (gap")[0]
        x = mo.setdefault(m, [0, 0.0])
        x[0] += 1
        x[1] += t["brl"]
    af = sum(1 for t in tr if (1 if t["lado"] == "compra" else -1) == sinal)
    pior = min(tr, key=lambda t: t["brl"]) if tr else None
    partes = [f"{d}: v4 R$ {tot4:+.0f} ({len(tr)} ops) | v3 {tot3:+.0f} | v1 {tot1:+.0f} | dia {'alta' if sinal > 0 else 'baixa'} ef {ef:.2f}"]
    if tr:
        partes.append("saidas " + ", ".join(f"{n}x {m} ({b:+.0f})" for m, (n, b) in mo.items()))
        partes.append(f"{af}/{len(tr)} entradas a favor do lado final do dia")
        partes.append(f"pior trade {pior['t_ent']}-{pior['t_sai']} {pior['motivo'].split(' (gap')[0]} R$ {pior['brl']:+.0f} (n={pior['n']})")
    else:
        partes.append("nenhuma operacao")
    # causa simples (regra declarada): maior perda por tipo de saida
    if tr:
        por = {m: b for m, (n, b) in mo.items()}
        causa = min(por, key=por.get)
        if tot4 < 0:
            partes.append("causa dominante: " + ("stop em dia que reverteu/rotacionou" if causa.startswith("stop") else f"saidas '{causa}'") +
                          (" (dia de rotacao, ef<0,15: o portao libera so no inicio/ruido)" if ef < 0.15 else ""))
        else:
            partes.append("v4 positivo mas bem abaixo do v1 (v1 captou o que o portao/regras cortaram)")
    return " | ".join(partes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", default=str(EXP / "rodada_v4_dias.json"))
    ap.add_argument("--sorteios", type=int, default=300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sem-nulo", action="store_true")
    ap.add_argument("--sem-ablacao", action="store_true")
    ap.add_argument("--saida", default=str(EXP / "analise_R50_v4.json"))
    a = ap.parse_args()
    dias = json.load(open(a.dias, encoding="utf-8"))["dias"]
    S = carrega(dias)
    datas = [d["data"] for d in sorted(dias, key=lambda x: x["data"]) if all(d["data"] in S[k] for k in S)]
    per = {d["data"]: d["periodo"] for d in dias}
    print(f"{len(datas)} dias completos de {len(dias)}")
    L = {k: [S[k][d] for d in datas] for k in S}
    out = dict(n_dias=len(datas))
    nome = {"v1": "v1 (54 perguntas)", "v3M": "v3 (zerar a mercado)", "v3L": "v3 (zerar limitado)", "v4": "v4 (portao+gestao+risco+reentrada)"}
    P = {k: ar.painel_x(L[k]) for k in L}
    print("\n== PAINEL (mesmos dias) ==")
    print(f"{'':<36} {'total R$':>9} {'ops':>5} {'acerto%':>8} {'F.lucro':>8} {'pior queda':>11} {'pior dia':>9} {'dias +':>7} {'R$/dia':>8} {'custo US$':>10}")
    out["painel"] = {}
    for k in ("v1", "v3M", "v3L", "v4"):
        p = P[k]
        custo = sum(s.get("custo_usd", 0) for s in L["v3M" if k == "v3L" else k]) if k != "v1" else sum(s.get("custo_usd", 0) for s in L["v1"])
        p["custo_usd"] = custo
        out["painel"][k] = p
        print(f"{nome[k]:<36} {br(p['total'], 0):>9} {p['ops']:>5} {br(p['acerto'], 1):>8} {br(p['fator_lucro'], 2):>8} {br(p['dd'], 0):>11} {br(p['pior_dia'], 0):>9} "
              f"{p['dias_pos']:>3}/{p['dias']:<3} {br(p['rs_dia'], 0):>8} {br(custo, 3):>10}")
    tot = {k: np.array([ar.total_dia(s) for s in L[k]]) for k in L}
    print("\n== PAREADO POR DIA (diferenca de R$/dia) ==")
    out["pareado"] = {}
    for nm, d in (("v4 - v3(L)", tot["v4"] - tot["v3L"]), ("v4 - v3(M)", tot["v4"] - tot["v3M"]), ("v4 - v1", tot["v4"] - tot["v1"]), ("v3(L) - v1", tot["v3L"] - tot["v1"])):
        r = ar.pareado(d)
        out["pareado"][nm] = r
        print(f"{nm:<12} media R$ {br(r['media'], 1):>8}/dia | IC95 bootstrap [{br(r['ic95'][0], 1)} ; {br(r['ic95'][1], 1)}] | t = {r['t']:.2f} (p = {r['p_t']:.3f}) | p sign-flip {r['p_signflip']:.3f} | melhor em {r['dias_melhor']} dias, pior em {r['dias_pior']}", flush=True)
    # --------------------------------------------------------------- nulo
    mk = Mercado.carregar()
    ctx = Ctx(mk)
    if not a.sem_nulo:
        print("\n== NULO (entradas aleatorias, mesma geometria das ordens preenchidas) ==")
        out["nulo"] = {}
        tt = P["v4"]["total"]
        nl = av.nulo_aleatorio(L["v4"], a.sorteios, a.workers)
        out["nulo"]["livre"] = dict(media=float(nl.mean()), p5=float(np.percentile(nl, 5)), p95=float(np.percentile(nl, 95)), p_nulo=float((nl >= tt).mean()), total=tt)
        print(f"nulo LIVRE (qualquer vela, 2 lados)      v4 R$ {br(tt, 0)} | nulo media {br(nl.mean(), 0)}, p5 {br(np.percentile(nl, 5), 0)}, p95 {br(np.percentile(nl, 95), 0)} | p(nulo >= v4) = {br((nl >= tt).mean(), 3)}", flush=True)
        cands = npt.candidatos(mk, datas)
        n_par = sum(len(v) for v in cands.values())
        ng, ngeo = npt.nulo(L["v4"], cands, a.sorteios, a.workers)
        out["nulo"]["com_portao"] = dict(media=float(ng.mean()), p5=float(np.percentile(ng, 5)), p95=float(np.percentile(ng, 95)), p_nulo=float((ng >= tt).mean()), total=tt,
                                         velas_que_passam=n_par, dias_com_vela_que_passa=len(cands), geometrias=ngeo)
        print(f"nulo COM PORTAO (so velas que passam, lado a favor; {n_par} pares em {len(cands)} dias, {ngeo} geometrias)  v4 R$ {br(tt, 0)} | nulo media {br(ng.mean(), 0)}, p5 {br(np.percentile(ng, 5), 0)}, "
              f"p95 {br(np.percentile(ng, 95), 0)} | p(nulo >= v4) = {br((ng >= tt).mean(), 3)}", flush=True)
        # referencia: o mesmo nulo com portao aplicado aos geometrias da v3 (L) e do v1
        for k in ("v3L", "v1"):
            n3, g3 = npt.nulo(L[k], cands, max(100, a.sorteios // 2), a.workers, seed0=9000)
            tk = P[k]["total"]
            out["nulo"][f"com_portao_geom_{k}"] = dict(media=float(n3.mean()), p5=float(np.percentile(n3, 5)), p95=float(np.percentile(n3, 95)), p_nulo=float((n3 >= tk).mean()), total=tk, geometrias=g3)
            print(f"  (ref) nulo COM PORTAO com a geometria de {nome[k]} ({g3} geom.): media {br(n3.mean(), 0)}, p5 {br(np.percentile(n3, 5), 0)}, p95 {br(np.percentile(n3, 95), 0)} | resultado real do {k} R$ {br(tk, 0)} p = {br((n3 >= tk).mean(), 3)}", flush=True)
    # --------------------------------------------------------------- quebras
    efs = {d: ar.eficiencia(S["v1"][d]) for d in datas}

    def quebra(titulo, chave, ordem=None):
        grupos = {}
        for d in datas:
            grupos.setdefault(chave(d), []).append(d)
        print(f"\n== {titulo} ==")
        print(f"{'grupo':<28} {'dias':>4} | {'v1 R$':>7} {'v3L R$':>7} {'v4 R$':>7} | {'ops v1':>6} {'v3':>4} {'v4':>4} | {'acerto v1':>9} {'v3':>5} {'v4':>5}")
        res = {}
        for g in (ordem or sorted(grupos)):
            if g not in grupos:
                continue
            ds = grupos[g]
            pp = {k: ar.painel_x([S[k][d] for d in ds]) for k in ("v1", "v3L", "v4")}
            res[g] = dict(dias=len(ds), **{k: pp[k]["total"] for k in pp}, ops={k: pp[k]["ops"] for k in pp}, acerto={k: pp[k]["acerto"] for k in pp})
            print(f"{g:<28} {len(ds):>4} | {br(pp['v1']['total'], 0):>7} {br(pp['v3L']['total'], 0):>7} {br(pp['v4']['total'], 0):>7} | {pp['v1']['ops']:>6} {pp['v3L']['ops']:>4} {pp['v4']['ops']:>4} | "
                  f"{br(pp['v1']['acerto'], 1):>9} {br(pp['v3L']['acerto'], 1):>5} {br(pp['v4']['acerto'], 1):>5}")
        out.setdefault("quebras", {})[titulo] = res
    quebra("POR TIPO DE DIA (eficiencia do dia, ex-post)", lambda d: ar.tipo_dia(efs[d][0]), ["rotacao (<0,15)", "intermediario (0,15-0,30)", "direcional (>=0,30)"])
    quebra("POR PERIODO (IS/OOS)", lambda d: per[d])
    # --------------------------------------------------------------- motivos
    print("\n== SAIDAS POR MOTIVO ==")
    out["motivos"] = {}
    for k in ("v1", "v3L", "v4"):
        mo = {}
        for s in L[k]:
            for t in s["trades"]:
                m = t["motivo"].split(" (gap")[0]
                x = mo.setdefault(m, [0, 0.0])
                x[0] += 1
                x[1] += t["brl"]
        n = sum(v[0] for v in mo.values())
        out["motivos"][k] = {m: dict(n=v[0], brl=v[1]) for m, v in mo.items()}
        print(f"-- {nome[k]} ({n} saidas)")
        for m, v in sorted(mo.items(), key=lambda x: -x[1][0]):
            print(f"   {m:<28} n {v[0]:>4} ({100 * v[0] / max(n, 1):4.0f}%) | total R$ {br(v[1], 0):>7} | medio R$ {br(v[1] / v[0], 1):>7}")
    # bloqueios e conversas do Jev com as regras
    bl, jev_ok, jev_n, cnt = {}, 0, 0, dict(entradas_jev=0, bloq_portao=0, bloq_reent=0, bloq_risco=0, mao_reduzida=0, gestao_zerar_jev=0, gestao_stop_pivo_jev=0, guarda_bloqueou=0, gestao_chamadas=0)
    for s in L["v4"]:
        for p in s["pontos"]:
            inf = p["jev"].get("info", {})
            if inf.get("fase") == "entrada" and inf.get("esc") in ("comprar", "vender") and inf.get("p", 0) >= s["limiar"]:
                cnt["entradas_jev"] += 1
                for b in inf.get("bloq") or []:
                    cnt["bloq_portao" if b.startswith("portao") else "bloq_reent" if b.startswith("reentrada") else "bloq_risco"] += 1
                if inf.get("mao_reduzida"):
                    cnt["mao_reduzida"] += 1
                m = p["jev"].get("m") or {}
                if "v4_direcao_comprovada" in m:
                    det = inf.get("portao_ok")
                    jev_n += 1
                    jev_ok += int((float(m["v4_direcao_comprovada"]) >= 0.5) == bool(det))
            if inf.get("fase") == "gestao" and not inf.get("fase") is None:
                if p["jev"].get("g"):
                    cnt["gestao_chamadas"] += 1
                if inf.get("esc_jev") == "zerar":
                    cnt["gestao_zerar_jev"] += 1
                if inf.get("esc_jev") == "stop_pivo":
                    cnt["gestao_stop_pivo_jev"] += 1
                if inf.get("guarda_bloqueou"):
                    cnt["guarda_bloqueou"] += 1
    cnt["portao_jev_concorda_com_determ"] = f"{jev_ok}/{jev_n}"
    out["contagens_regras"] = cnt
    print("\n== O QUE AS REGRAS FIZERAM (v4) ==")
    for k_, v_ in cnt.items():
        print(f"   {k_:<34} {v_}")
    # --------------------------------------------------------------- caixa
    print("\n== CAIXA (escada: R$ 1.000/contrato, max 2, inicio R$ 2.000; < R$ 2.000 -> 1 contrato; < R$ 1.000 -> para) ==")
    out["capital"] = {}
    for k in ("v1", "v3M", "v3L", "v4"):
        c = ar.capital([(d, S[k][d]["trades"]) for d in datas])
        out["capital"][k] = c
        print(f"{nome[k]:<36} final R$ {br(c['final'], 0)} | minimo R$ {br(c['minimo'], 0)} | maximo R$ {br(c['maximo'], 0)} | dias abaixo de R$ 2.000: {c['dias_abaixo_2000']} | abaixo de R$ 1.000: {c['dias_abaixo_1000']} | parou: {c['parou_em']} ({c['trades_pulados']} trades pulados)")
    print("curva v4: " + " | ".join(f"{d[5:]} {br(c, 0)}" for d, c in out["capital"]["v4"]["curva"]))
    # --------------------------------------------------------------- ablacao
    if not a.sem_ablacao:
        print("\n== ABLACAO OFFLINE (respostas logadas; sem nova chamada; entrada sem resposta v4 na vela usa a da v3 = coluna fallback) ==")
        ab = ablacao(mk, ctx, S, datas)
        out["ablacao"] = {}
        print(f"{'variante':<52} {'total R$':>9} {'ops':>5} {'acerto%':>8} {'F.lucro':>8} {'pior queda':>11} {'pior dia':>9} {'dias +':>7} {'fallback':>9}")
        for nm, ss, fbs in ab:
            p = ar.painel_x(ss)
            out["ablacao"][nm] = dict(p, fallback=fbs)
            print(f"{nm:<52} {br(p['total'], 0):>9} {p['ops']:>5} {br(p['acerto'], 1):>8} {br(p['fator_lucro'], 2):>8} {br(p['dd'], 0):>11} {br(p['pior_dia'], 0):>9} {p['dias_pos']:>3}/{p['dias']:<3} {fbs:>9}", flush=True)
        base = np.array([sum(t["brl"] for t in s["trades"]) for s in ab[0][1]])
        print("   (checagem) v4 completa resimulada = vivo?  resim " + br(base.sum(), 0) + " x vivo " + br(P["v4"]["total"], 0))
        for nm, ss, _ in ab[1:]:
            dd = np.array([sum(t["brl"] for t in s["trades"]) for s in ss]) - base
            r = ar.pareado(dd)
            out["ablacao"][nm]["pareado_vs_v4"] = r
            print(f"   {nm:<52} vs v4: media {br(r['media'], 1):>7}/dia | IC95 [{br(r['ic95'][0], 1)} ; {br(r['ic95'][1], 1)}] | p sign-flip {r['p_signflip']:.3f}")
    # --------------------------------------------------------------- dias ruins
    ruins = [d for d in datas if ar.total_dia(S["v4"][d]) < 0 or ar.total_dia(S["v4"][d]) - ar.total_dia(S["v1"][d]) <= LIM_DIF_RUIM]
    print(f"\n== DIAS RUINS DA v4: total < 0 ou v4 - v1 <= R$ {LIM_DIF_RUIM:.0f} ({len(ruins)} de {len(datas)}) ==")
    dr = []
    for d in ruins:
        ef, sg = efs[d]
        linha = diag_v4(d, S["v4"][d], S["v1"][d], ef, sg, S["v3L"][d])
        print(" - " + linha)
        dr.append(dict(data=d, periodo=per[d], v4_brl=ar.total_dia(S["v4"][d]), v3_brl=ar.total_dia(S["v3L"][d]), v1_brl=ar.total_dia(S["v1"][d]), eficiencia_dia=ef,
                       diagnostico=linha,
                       trades_v4=[dict(lado=t["lado"], n=t["n"], ent=t["t_ent"], sai=t["t_sai"], motivo=t["motivo"], brl=round(t["brl"], 1)) for t in S["v4"][d]["trades"]],
                       trades_v1=[dict(lado=t["lado"], n=t["n"], ent=t["t_ent"], sai=t["t_sai"], motivo=t["motivo"], brl=round(t["brl"], 1)) for t in S["v1"][d]["trades"]]))
    (EXP / "dias_ruins_v4.json").write_text(json.dumps(dict(criterio=f"v4 com total < 0, ou v4 - v1 <= R$ {LIM_DIF_RUIM:.0f} no dia (mesmo criterio da v3, declarado antes)", n=len(dr), dias=dr),
                                                       ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    out["dias_ruins"] = [x["data"] for x in dr]
    out["por_dia"] = [dict(data=d, periodo=per[d], v1=ar.total_dia(S["v1"][d]), v3M=ar.total_dia(S["v3M"][d]), v3L=ar.total_dia(S["v3L"][d]), v4=ar.total_dia(S["v4"][d]), ef=efs[d][0],
                           ops1=len(S["v1"][d]["trades"]), ops3=len(S["v3L"][d]["trades"]), ops4=len(S["v4"][d]["trades"])) for d in datas]
    out["custo_v4_usd"] = sum(s.get("custo_usd", 0) for s in L["v4"])
    out["custo_v3_usd"] = sum(s.get("custo_usd", 0) for s in L["v3M"])
    Path(a.saida).write_text(json.dumps(out, ensure_ascii=False, default=float, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
