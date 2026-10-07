"""Z9-T5 prioridade fixa. Ordens decididas SO com 2022-2025 e gravadas em ordens.json antes de simular qualquer ano."""
import sys, json
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from base import operacoes, preco, resumo, ROBOS, CUSTO  # noqa: E402

AQUI = Path(__file__).resolve().parent
ANOS = [2022, 2023, 2024, 2025, 2026]


def simular(ops, ordem, precofn=preco):
    """ordem: lista de robos, indice 0 = maior prioridade."""
    pr = {r: len(ordem) - i for i, r in enumerate(ordem)}
    ops = sorted(ops.to_dict("records"), key=lambda o: (o["entrada"], -pr[o["estrategia"]]))
    out, h = [], None  # h: dict posicao

    def fecha(h, saida, ps, motivo):
        out.append(dict(ano=h["entrada"].year, estrategia=h["dono"], entrada=h["entrada"], saida=saida, lado=h["lado"],
                        preco_entrada=h["pe"], preco_saida=ps, rs=(ps - h["pe"]) * 0.20 * h["lado"], motivo=motivo,
                        transferida=h["transf"]))

    for o in ops:
        t = o["entrada"]
        if h is not None and h["saida"] <= t:
            fecha(h, h["saida"], h["ps"], "natural"); h = None
        novo = dict(dono=o["estrategia"], entrada=t, saida=o["saida"], lado=o["lado"], pe=o["preco_entrada"],
                    ps=o["preco_saida"], transf=False)
        if h is None:
            h = novo
        elif pr[o["estrategia"]] > pr[h["dono"]]:
            if o["lado"] == h["lado"]:  # transfere gestao: mantem entrada, vale a saida do novo
                h.update(dono=o["estrategia"], saida=o["saida"], ps=o["preco_saida"], transf=True)
            else:
                fecha(h, t, precofn(t), "zerada_por_prioridade"); h = novo
        # senao: bloqueado
    if h is not None:
        fecha(h, h["saida"], h["ps"], "natural")
    return pd.DataFrame(out)


def sanidade():
    T = pd.Timestamp
    def mk(r, e, s, l, pe, ps):
        return dict(estrategia=r, entrada=T(e), saida=T(s), lado=l, preco_entrada=pe, preco_saida=ps)
    pf = lambda t: 100.0
    ordem = ["A", "B"]  # A maior
    # 1) menor ocupa, maior chega lado oposto: zera a 100 e assume. B compra 90 ; A vende 110 as 10:30
    d = simular(pd.DataFrame([mk("B", "2024-01-02 10:00", "2024-01-02 11:00", 1, 90, 120),
                              mk("A", "2024-01-02 10:30", "2024-01-02 11:30", -1, 110, 105)]), ordem, pf)
    assert len(d) == 2 and abs(d.rs[0] - 10 * .2) < 1e-9 and abs(d.rs[1] - 5 * .2) < 1e-9, d
    # 2) mesmo lado: transfere, 1 operacao, entrada 90, saida 130 do A
    d = simular(pd.DataFrame([mk("B", "2024-01-02 10:00", "2024-01-02 11:00", 1, 90, 120),
                              mk("A", "2024-01-02 10:30", "2024-01-02 11:30", 1, 95, 130)]), ordem, pf)
    assert len(d) == 1 and d.estrategia[0] == "A" and abs(d.rs[0] - 40 * .2) < 1e-9, d
    # 3) menor chega com maior posicionado: bloqueada; maior sai natural
    d = simular(pd.DataFrame([mk("A", "2024-01-02 10:00", "2024-01-02 11:00", 1, 90, 120),
                              mk("B", "2024-01-02 10:30", "2024-01-02 10:50", -1, 100, 80),
                              mk("B", "2024-01-02 11:00", "2024-01-02 11:20", -1, 100, 80)]), ordem, pf)
    assert len(d) == 2 and d.estrategia[0] == "A" and abs(d.rs[0] - 30 * .2) < 1e-9 and d.estrategia[1] == "B", d
    print("sanidade ok (3 casos)", flush=True)


def met(ops):
    v = ops.rs - CUSTO
    gp, gl = v[v > 0].sum(), -v[v <= 0].sum()
    return dict(liq=round(float(v.sum()), 2), pf=round(float(gp / gl), 3) if gl else float("inf"),
                win=round(100 * float((v > 0).mean()), 2), ops=len(v))


if __name__ == "__main__":
    sanidade()
    ins = pd.concat([operacoes(a).assign(ano=a) for a in range(2022, 2026)])
    iso = {r: met(ins[ins.estrategia == r]) for r in ROBOS}
    ordens = {"P1_liquido": sorted(ROBOS, key=lambda r: -iso[r]["liq"]),
              "P2_fator_lucro": sorted(ROBOS, key=lambda r: -iso[r]["pf"]),
              "P3_acerto": sorted(ROBOS, key=lambda r: -iso[r]["win"])}
    (AQUI / "ordens.json").write_text(json.dumps(dict(isolado_2022_2025=iso, ordens=ordens), indent=1), encoding="utf-8")
    print("METRICAS ISOLADAS 2022-2025:", json.dumps(iso), flush=True)
    for k, v in ordens.items():
        print("ORDEM", k, v, flush=True)
    res = {}
    base = pd.concat([operacoes(a) for a in ANOS])
    res["isolada"] = resumo(base)
    for k, o in ordens.items():
        ds = []
        for a in ANOS:
            d = simular(operacoes(a), o)
            ds.append(d)
            r = resumo(d)[a]
            print(k, a, r, flush=True)
        d = pd.concat(ds); d.to_csv(AQUI / f"trades_{k}.csv", index=False)
        res[k] = resumo(d)
        res[k + "_robo"] = {r: {a: v for a, v in resumo(d[d.estrategia == r].assign(ano=lambda x: x.ano)).items()} for r in ROBOS}
        res[k + "_transf"] = int(d.transferida.sum()); res[k + "_zeradas"] = int((d.motivo != "natural").sum())
    print("isolada", {a: v["liq"] for a, v in res["isolada"].items()}, flush=True)
    json.dump(res, open(AQUI / "res.json", "w"), default=str)
