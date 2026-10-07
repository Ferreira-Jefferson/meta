"""Z9-T4 conflito = fora. Variantes: T4 (lado oposto zera a mercado, ninguem entra), T4b (T4 + fora pelo resto do
pregao), T4c (nao zera; bloqueia como T0, mas conta conflitos e compara natural vs zerar no conflito).
Aproximacao: robo bloqueado/interrompido nao muda as operacoes seguintes dele. Custo R$2/op, R$1.000 por ano."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base  # noqa: E402

AQUI = Path(__file__).resolve().parent
PT = 0.20
VARS = ("T4", "T4b", "T4c")


def simular(ops, variante, preco=base.preco):
    """ops ordenado por entrada (desempate = ROBOS). Retorna (trades, conflitos)."""
    trades, conflitos = [], []
    pos = None          # dict: dono, lado, pe, entrada, saida, ps
    fora = set()        # datas fora (T4b)

    def fecha(p, saida, ps, motivo):
        trades.append(dict(ano=p["entrada"].year, dono=p["dono"], entrada=p["entrada"], saida=saida, lado=p["lado"],
                           preco_entrada=p["pe"], preco_saida=ps, rs=(ps - p["pe"]) * PT * p["lado"], motivo=motivo))

    for s in ops.itertuples():
        t = s.entrada
        if pos is not None and pos["saida"] <= t:            # saida natural antes (ou no) do sinal
            fecha(pos, pos["saida"], pos["ps"], "natural"); pos = None
        if variante == "T4b" and t.date() in fora:
            continue
        if pos is None:
            pos = dict(dono=s.estrategia, lado=s.lado, pe=s.preco_entrada, entrada=t, saida=s.saida, ps=s.preco_saida,
                       conf=False)
        elif s.lado == pos["lado"]:
            continue                                         # concordancia: ignora
        else:                                                # discordancia
            px = preco(t)
            zer = (px - pos["pe"]) * PT * pos["lado"]
            if not pos["conf"]:
                nat = (pos["ps"] - pos["pe"]) * PT * pos["lado"]
                conflitos.append(dict(t=t, dono=pos["dono"], contra=s.estrategia, lado=pos["lado"],
                                      rs_zerando=zer, rs_natural=nat))
                pos["conf"] = True
            if variante in ("T4", "T4b"):
                fecha(pos, t, px, f"conflito com {s.estrategia}"); pos = None
                if variante == "T4b":
                    fora.add(t.date())
    if pos is not None:
        fecha(pos, pos["saida"], pos["ps"], "natural")
    return pd.DataFrame(trades), pd.DataFrame(conflitos)


def _casos():
    mk = lambda r: pd.DataFrame(r, columns=["estrategia", "entrada", "saida", "lado", "preco_entrada", "preco_saida"])
    T = pd.Timestamp
    px = lambda ts: 90.0
    # 1: oposto zera e ninguem entra; 3o sinal posterior no mesmo dia abre em T4, nao em T4b
    o = mk([("A", T("2024-01-02 10:00"), T("2024-01-02 12:00"), 1, 100.0, 120.0),
            ("B", T("2024-01-02 10:30"), T("2024-01-02 11:00"), -1, 95.0, 90.0),
            ("C", T("2024-01-02 11:30"), T("2024-01-02 11:45"), -1, 90.0, 80.0)])
    a, c = simular(o, "T4", px)
    assert list(a.dono) == ["A", "C"] and a.rs[0] == (90 - 100) * PT and a.rs[1] == 10 * PT and len(c) == 1, a
    b, _ = simular(o, "T4b", px)
    assert list(b.dono) == ["A"], b
    # 2: mesmo lado ignorado; saida natural libera sinal no mesmo instante
    o = mk([("A", T("2024-01-02 10:00"), T("2024-01-02 11:00"), 1, 100.0, 110.0),
            ("B", T("2024-01-02 10:30"), T("2024-01-02 10:50"), 1, 105.0, 99.0),
            ("C", T("2024-01-02 11:00"), T("2024-01-02 11:30"), -1, 110.0, 100.0)])
    a, c = simular(o, "T4", px)
    assert list(a.dono) == ["A", "C"] and len(c) == 0 and a.rs[0] == 10 * PT, a
    # 3: T4c nao zera: A segue ate saida natural, conflito registrado com ambos resultados
    o = mk([("A", T("2024-01-02 10:00"), T("2024-01-02 12:00"), 1, 100.0, 120.0),
            ("B", T("2024-01-02 10:30"), T("2024-01-02 11:00"), -1, 95.0, 90.0)])
    a, c = simular(o, "T4c", px)
    assert list(a.dono) == ["A"] and a.rs[0] == 20 * PT and c.rs_zerando[0] == -10 * PT and c.rs_natural[0] == 20 * PT
    print("sanidade: 3 casos manuais OK", flush=True)


def fmt(v):
    return f"{v:,.0f}".replace(",", ".")


if __name__ == "__main__":
    _casos()
    anos = list(range(2022, 2027))
    res = {v: {} for v in ("iso",) + VARS}
    trs = {v: [] for v in VARS}
    confs = {v: [] for v in VARS}
    for ano in anos:
        ops = base.operacoes(ano)
        res["iso"].update(base.resumo(ops))
        for v in VARS:
            tr, cf = simular(ops, v)
            res[v].update(base.resumo(tr))
            trs[v].append(tr)
            confs[v].append(cf.assign(ano=ano))
            print(ano, v, res[v][ano], "conflitos:", len(cf), flush=True)
        print(ano, "soma isolada", res["iso"][ano], flush=True)
    for v in VARS:
        pd.concat(trs[v]).to_csv(AQUI / f"trades_{v}.csv", index=False)
    conf = pd.concat(confs["T4"])
    conf.to_csv(AQUI / "conflitos.csv", index=False)

    f = lambda d: f"{fmt(d['liq'])} / {d['ops']} / {d['acerto']} / {fmt(d['dd'])} / {d['quebra'] or '-'}"
    L = ["# Z9-T4 conflito = fora", "",
         "Regra: quem abre primeiro fica; mesmo lado ignorado; lado contrario zera a mercado (preco(t), t = entrada do causador) e ninguem entra; "
         "depois a conta fica livre. T4b: fora pelo resto do pregao apos conflito. T4c: nao zera, bloqueia como T0 (so registra conflitos). "
         "Liquido com custo R$2/op, 1 contrato, R$1.000 por ano. "
         "Aproximacao: robo bloqueado/interrompido nao muda as operacoes seguintes dele.", "",
         "## Por ano (liquido R$ / ops / acerto % / maior queda R$ / quebra)", "",
         "| ano | soma isolada | T4 | T4b | T4c (=T0) |", "|---|---|---|---|---|"]
    for a in anos:
        L.append(f"| {a} | {f(res['iso'][a])} | {f(res['T4'][a])} | {f(res['T4b'][a])} | {f(res['T4c'][a])} |")
    L += ["", "## Por robo dono (liquido R$ c/ custo (ops))", "",
          "| robo | variante | " + " | ".join(map(str, anos)) + " |", "|---|---|" + "---|" * len(anos)]
    for v in VARS:
        al = pd.concat(trs[v])
        for r in base.ROBOS:
            cel = []
            for a in anos:
                g = al[(al.dono == r) & (al.ano == a)]
                cel.append(f"{fmt(g.rs.sum() - 2 * len(g))} ({len(g)})")
            L.append(f"| {r} | {v} | " + " | ".join(cel) + " |")
    L += ["", "## O conflito e' informativo? Posicao aberta no 1o conflito: R$ bruto (1 contrato, sem custo) ate' a saida natural vs zerando no conflito", "",
          "| ano | conflitos | natural R$ | zerando R$ | zerar - natural | % perda se natural | % perda se zerar | R$ medio por op (nao-conflito) |",
          "|---|---|---|---|---|---|---|---|"]
    for a in anos + ["2022-25"]:
        c = conf[conf.ano.between(2022, 2025)] if a == "2022-25" else conf[conf.ano == a]
        base_ops = pd.concat(trs["T4c"])
        base_ops = base_ops[base_ops.ano.between(2022, 2025)] if a == "2022-25" else base_ops[base_ops.ano == a]
        if len(c):
            L.append(f"| {a} | {len(c)} | {fmt(c.rs_natural.sum())} | {fmt(c.rs_zerando.sum())} | "
                     f"{fmt(c.rs_zerando.sum() - c.rs_natural.sum())} | {100*(c.rs_natural<0).mean():.0f} | "
                     f"{100*(c.rs_zerando<0).mean():.0f} | media geral T4c {base_ops.rs.mean():.1f}; media nas posicoes com conflito {c.rs_natural.mean():.1f} |")
    (AQUI / "resultado.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L), flush=True)
