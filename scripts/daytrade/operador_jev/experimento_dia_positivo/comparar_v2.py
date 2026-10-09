"""Compara referencia (Jev atual) x A (duas etapas) x B (veto) dia a dia, por grupo (bons/ruins) e total; diagnostico de direcao.
Uso: python comparar_v2.py [--grupo validacao|treino]   (le sessoes_v2/A_<grupo>, B_<grupo>, REF_val5)
Imprime tabelas em texto (R$ BR) e grava comparacao_<grupo>.json."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np

AQUI = Path(__file__).resolve().parent
PAI = AQUI.parent
SV = AQUI / "sessoes_v2"


def br(x, nd=0):
    if x is None or (isinstance(x, float) and (np.isnan(x))):
        return "-"
    if isinstance(x, float) and np.isinf(x):
        return "inf"
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carrega(pasta):
    return {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(Path(pasta).glob("2*.json"))}


def stats(trades_por_dia, totais_dia):
    tr = [t for ts in trades_por_dia for t in ts]
    brl = np.array([t["brl"] for t in tr]) if tr else np.array([])
    g, p = brl[brl > 0].sum(), -brl[brl < 0].sum()
    return dict(total=float(sum(totais_dia)), ops=len(tr), acerto=float(100 * (brl > 0).mean()) if len(brl) else float("nan"),
                pf=float(g / p) if p > 0 else (float("inf") if g > 0 else float("nan")), pior_dia=float(min(totais_dia)) if totais_dia else 0.0,
                melhor_dia=float(max(totais_dia)) if totais_dia else 0.0, dias_sem_op=int(sum(1 for ts in trades_por_dia if not ts)))


def alinhado(s, t):
    """Trade a favor da tendencia do dia no momento da decisao? Medida OBJETIVA: sinal de (fechamento da vela de decisao - abertura do dia).
    Devolve (+1 a favor, -1 contra, 0 nulo) usando a ultima decisao de entrada do mesmo lado antes do fill."""
    dirn = 1 if t["lado"] == "compra" else -1
    cand = [p for p in s["pontos"] if p["decisao"].get("acao") in ("comprar_limite", "vender_limite")
            and (1 if p["decisao"]["acao"] == "comprar_limite" else -1) == dirn and p["k"] < t["k_ent"]]
    if not cand:
        return None, None
    p = cand[-1]
    bars = s["bars"]
    ab = bars[0]["o"]
    c = bars[p["k"]]["c"]
    atr_aprox = np.mean([b["h"] - b["l"] for b in bars[: p["k"] + 1]]) or 1
    desl = c - ab
    return (int(np.sign(desl) * dirn) if abs(desl) > 0 else 0), p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grupo", default="validacao")
    a = ap.parse_args()
    ref = json.load(open(AQUI / "referencia.json", encoding="utf-8"))
    dias = [dict(x, bom=(k == "bons")) for k in ("bons", "ruins") for x in ref[a.grupo][k]]
    SA, SB = carrega(SV / f"A_{a.grupo}"), carrega(SV / f"B_{a.grupo}")
    SR = {d["data"]: json.loads((PAI / "sessoes_dec" / d["periodo"] / f"{d['data']}.json").read_text(encoding="utf-8")) for d in dias}
    sess = dict(ref=SR, A=SA, B=SB)
    print(f"\n=== {a.grupo.upper()} ===")
    print(f"{'data':<11} {'grupo':<5} {'atual R$':>9} {'A R$':>9} {'B R$':>9} | {'ops atual':>9} {'ops A':>6} {'ops B':>6}")
    linhas = []
    for d in dias:
        k = d["data"]
        ra = SA.get(k, {}).get("resumo", {}).get("total")
        rb = SB.get(k, {}).get("resumo", {}).get("total")
        oa = SA.get(k, {}).get("resumo", {}).get("ops")
        ob = SB.get(k, {}).get("resumo", {}).get("ops")
        linhas.append(dict(data=k, bom=d["bom"], atual=d["brl"], A=ra, B=rb, ops=(d["ops"], oa, ob)))
        print(f"{k:<11} {'bom' if d['bom'] else 'ruim':<5} {br(d['brl']):>9} {br(ra):>9} {br(rb):>9} | {d['ops']:>9} {oa if oa is not None else '-':>6} {ob if ob is not None else '-':>6}")
    print()
    cab = f"{'':<22} {'total R$':>10} {'ops':>5} {'acerto%':>8} {'F.lucro':>8} {'pior dia':>9} {'melhor':>8} {'dias s/op':>9}"
    out = {}
    for nome, filtro in (("BONS", lambda l: l["bom"]), ("RUINS", lambda l: not l["bom"]), ("TOTAL", lambda l: True)):
        print(f"-- {nome} --")
        print(cab)
        sel = [l for l in linhas if filtro(l)]
        for v, key in (("atual", "ref"), ("A (duas etapas)", "A"), ("B (veto)", "B")):
            ds = [l["data"] for l in sel]
            S = sess[key]
            ds = [x for x in ds if x in S]
            trs = [S[x]["trades"] for x in ds]
            tot = [S[x]["resumo"]["total"] for x in ds]
            st = stats(trs, tot)
            out[f"{nome}_{key}"] = st
            print(f"{v:<22} {br(st['total']):>10} {st['ops']:>5} {br(st['acerto'], 1):>8} {br(st['pf'], 2):>8} {br(st['pior_dia']):>9} {br(st['melhor_dia']):>8} {st['dias_sem_op']:>9}")
        print()
    for key, nome in (("A", "A"), ("B", "B")):
        rr = [l for l in linhas if not l["bom"] and l[key] is not None]
        bb = [l for l in linhas if l["bom"] and l[key] is not None]
        melh = sum(1 for l in rr if l[key] > l["atual"])
        pior = sum(1 for l in bb if l[key] < l["atual"])
        pos = sum(1 for l in linhas if l[key] is not None and l[key] > 0)
        print(f"{nome}: ruins melhores que o atual: {melh}/{len(rr)} | bons piores que o atual: {pior}/{len(bb)} | dias positivos: {pos}/{len(linhas)} | dias sem operar: {sum(1 for l in linhas if l[key] == 0)}")
    json.dump(dict(linhas=linhas, stats=out), open(AQUI / f"comparacao_{a.grupo}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)

    # ---------------- ruido: referencia rodada de novo
    rp = SV / "REF_val5"
    if a.grupo == "validacao" and rp.exists():
        SRr = carrega(rp)
        print("\n=== RUIDO: referencia ATUAL rodada de novo (mesmo limiar/versao/54 perguntas) ===")
        s0 = s1 = 0
        for k, s in SRr.items():
            o = SR[k]["resumo"]["total"]
            n = s["resumo"]["total"]
            s0 += o
            s1 += n
            print(f"{k} atual(original) R$ {br(o)} ({SR[k]['resumo']['ops']} ops) -> nova rodada R$ {br(n)} ({s['resumo']['ops']} ops)")
        print(f"soma dos 5: original {br(s0)} -> rodada nova {br(s1)} (diferenca {br(s1 - s0)}; |dif| media por dia {br(np.mean([abs(SRr[k]['resumo']['total'] - SR[k]['resumo']['total']) for k in SRr]))})")

    # ---------------- diagnostico de direcao
    print(f"\n=== DIAGNOSTICO DE DIRECAO ({a.grupo}) ===")
    print("trade a favor = lado igual ao sinal de (fechamento da vela de decisao - abertura do dia)")
    print(f"{'versao':<10} {'trades':>6} {'a favor':>8} {'contra':>7} {'R$ a favor':>11} {'R$ contra':>10} {'R$/trade a favor':>17} {'R$/trade contra':>16}")
    diag = {}
    for key, nome in (("ref", "atual"), ("A", "A"), ("B", "B")):
        r = {+1: [], -1: [], 0: []}
        for d in dias:
            s = sess[key].get(d["data"])
            if not s:
                continue
            for t in s["trades"]:
                al, _ = alinhado(s, t)
                if al is not None:
                    r[al].append(t["brl"])
        diag[nome] = {k: (len(v), float(sum(v))) for k, v in r.items()}
        nf, nc = len(r[1]), len(r[-1])
        tot = max(1, nf + nc + len(r[0]))
        print(f"{nome:<10} {tot:>6} {100 * nf / tot:>7.0f}% {100 * nc / tot:>6.0f}% {br(sum(r[1])):>11} {br(sum(r[-1])):>10} {br(np.mean(r[1]) if r[1] else float('nan'), 1):>17} {br(np.mean(r[-1]) if r[-1] else float('nan'), 1):>16}")
    json.dump(diag, open(AQUI / f"diagnostico_direcao_{a.grupo}.json", "w"), indent=1)

    # perguntas: voto de cada pergunta de direcao no momento da decisao x resultado do trade (A) e vetos (B)
    import sys
    sys.path.insert(0, str(AQUI))
    import perguntas_v2 as pv
    print(f"\n=== PERGUNTAS DE DIRECAO x RESULTADO DOS TRADES DE A ({a.grupo}): R$ medio por trade quando a pergunta votava A FAVOR / CONTRA / sem voto ===")
    print(f"{'pergunta':<20} {'a favor n':>9} {'R$/tr':>7} {'contra n':>9} {'R$/tr':>7} {'sem voto n':>11} {'R$/tr':>7}")
    for qid, cats in pv.VOTOS.items():
        buck = {"f": [], "c": [], "n": []}
        for d in dias:
            s = SA.get(d["data"])
            if not s:
                continue
            for t in s["trades"]:
                dirn = 1 if t["lado"] == "compra" else -1
                _, p = alinhado(s, t)
                if p is None:
                    continue
                r = (p["jev"].get("m") or {}).get(qid)
                voto = 0
                if isinstance(r, dict):
                    for cat, sg in cats.items():
                        if r["p"].get(cat, 0) >= pv.P_VETO:
                            voto = sg * dirn
                buck["f" if voto > 0 else "c" if voto < 0 else "n"].append(t["brl"])
        f = lambda L: (len(L), np.mean(L) if L else float("nan"))
        (nf, mf), (nc, mc), (nn, mn) = f(buck["f"]), f(buck["c"]), f(buck["n"])
        print(f"{qid:<20} {nf:>9} {br(mf, 1):>7} {nc:>9} {br(mc, 1):>7} {nn:>11} {br(mn, 1):>7}")
    # vetos em B
    cont = {}
    n_ent = n_vet = 0
    for d in dias:
        s = SB.get(d["data"])
        if not s:
            continue
        for p in s["pontos"]:
            inf = p["jev"].get("info") or {}
            if inf.get("fase") == "entrada" and inf.get("esc") in ("comprar", "vender") and (p["decisao"].get("acao") != "ficar_fora" or inf.get("vetado")):
                n_ent += 1
                if inf.get("vetado"):
                    n_vet += 1
                    for m in inf["vetado"]:
                        q = m.split("=")[0].split(" ")[0]
                        cont[q] = cont.get(q, 0) + 1
    print(f"\nB ({a.grupo}): {n_ent} decisoes de entrada do Jev (P>=limiar), {n_vet} vetadas ({100 * n_vet / max(1, n_ent):.0f}%). Vetos por pergunta (uma decisao pode ter varios): {dict(sorted(cont.items(), key=lambda x: -x[1]))}")
    # onde ainda erram: 6 piores trades de A e B
    for key, nome, S in (("A", "A", SA), ("B", "B", SB)):
        piores = []
        for k, s in S.items():
            for t in s["trades"]:
                al, p = alinhado(s, t)
                m = (p["jev"].get("m") or {}) if p else {}
                dt = m.get("v2_dia_tipo", {}).get("c") if isinstance(m.get("v2_dia_tipo"), dict) else None
                piores.append((t["brl"], k, t["t_ent"], t["lado"], t["motivo"], al, dt))
        piores.sort()
        print(f"\nPiores 6 trades de {nome} ({a.grupo}): (R$, dia, hora, lado, motivo, a favor da tendencia?, v2_dia_tipo na decisao)")
        for x in piores[:6]:
            print("  ", x)
    # horario dos trades
    for key, nome, S in (("A", "A", SA), ("B", "B", SB)):
        tarde = [t["brl"] for s in S.values() for t in s["trades"] if t["t_ent"] >= "15:00"]
        print(f"{nome}: trades entrados >= 15:00: n={len(tarde)} R$ {br(sum(tarde))}")


if __name__ == "__main__":
    main()
