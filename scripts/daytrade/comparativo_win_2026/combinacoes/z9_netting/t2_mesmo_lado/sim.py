"""Z9-T2: mesmo lado mantem, lado oposto encerra a mercado e inverte. Variantes: T2 (dono mantem), T2b (saida = mais tardia),
T2c (saida = mais cedo). Aproximacao: robo interrompido/bloqueado nao muda as operacoes seguintes dele."""
import sys
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from base import operacoes, preco, resumo, ROBOS  # noqa: E402

PT = 0.20


def simular(ops: pd.DataFrame, var: str):
    trades, cnt = [], {r: dict(sinais=0, assumiram=0, ignorados=0, inverteram=0, invertidos=0) for r in ROBOS}
    pos = None

    def fechar(ts, px, motivo):
        nonlocal pos
        rs = (px - pos["pe"]) * PT * pos["lado"]
        trades.append(dict(ano=pos["ent"].year, dono=pos["dono"], lado=pos["lado"], entrada=pos["ent"], saida=ts,
                           preco_entrada=pos["pe"], preco_saida=px, rs=round(rs, 4), motivo=motivo,
                           def_saida=pos["defs"]))
        pos = None

    for s in ops.itertuples():
        t = s.entrada
        if pos is not None and pos["sai"] <= t:
            fechar(pos["sai"], pos["ps"], "natural" if pos["defs"] == pos["dono"] else "natural_" + pos["defs"])
        cnt[s.estrategia]["sinais"] += 1
        novo = dict(dono=s.estrategia, lado=int(s.lado), ent=t, pe=float(s.preco_entrada), sai=s.saida,
                    ps=float(s.preco_saida), defs=s.estrategia)
        if pos is None:
            pos = novo; cnt[s.estrategia]["assumiram"] += 1
        elif pos["lado"] == novo["lado"]:
            cnt[s.estrategia]["ignorados"] += 1
            if var == "T2b" and novo["sai"] > pos["sai"]:
                pos.update(sai=novo["sai"], ps=novo["ps"], defs=novo["dono"])
            elif var == "T2c" and novo["sai"] < pos["sai"]:
                pos.update(sai=novo["sai"], ps=novo["ps"], defs=novo["dono"])
        else:
            cnt[pos["dono"]]["invertidos"] += 1
            fechar(t, preco(t), "inversao_por_" + s.estrategia)
            pos = novo; cnt[s.estrategia]["assumiram"] += 1; cnt[s.estrategia]["inverteram"] += 1
    if pos is not None:
        fechar(pos["sai"], pos["ps"], "natural" if pos["defs"] == pos["dono"] else "natural_" + pos["defs"])
    return pd.DataFrame(trades), cnt


def main():
    anos = range(2022, 2027)
    res = {v: {} for v in ("T2", "T2b", "T2c")}
    iso, trs, cnts = {}, {v: [] for v in res}, {v: {} for v in res}
    for ano in anos:
        ops = operacoes(ano)
        iso[ano] = resumo(ops)[ano]
        for v in res:
            tr, cnt = simular(ops, v)
            trs[v].append(tr); cnts[v][ano] = cnt
            res[v][ano] = resumo(tr)[ano]
            print(ano, v, res[v][ano], "| isolada", iso[ano]["liq"], flush=True)
    todos = {}
    for v in res:
        todos[v] = pd.concat(trs[v], ignore_index=True)
        todos[v].to_csv(AQUI / f"trades_{v}.csv", index=False)
    # sanidade: 3 inversoes
    print("SANIDADE (inversoes T2: preco_saida deve = preco(entrada do robo causador))", flush=True)
    inv = todos["T2"][todos["T2"].motivo.str.startswith("inversao")]
    for _, r in inv.sample(3, random_state=1).iterrows():
        print(f"  {r.dono} lado {r.lado} saiu {r.saida} a {r.preco_saida} | preco(t)={preco(r.saida)} "
              f"{'OK' if abs(r.preco_saida - preco(r.saida)) < 1e-9 else 'DIFERE'} | {r.motivo}", flush=True)
    # resultado.md
    L = ["# Z9-T2 -- mesmo lado mantem, lado oposto inverte (WIN, conta NETTING, 1 contrato, R$1.000/ano, custo R$2/op)", "",
         "Regras: T2 = sinal do mesmo lado ignorado (dono segue ate' a saida dele); T2b = saida passa a ser a mais tardia entre os que concordam; "
         "T2c = saida passa a ser a mais cedo. Sinal contrario: encerra a mercado a preco(t) (t = entrada do causador) e o novo robo assume a preco_entrada. "
         "Saida natural a preco_saida. Empate de segundo: ordem de ROBOS; saida natural em t <= entrada do sinal e' processada antes.",
         "Aproximacao: robo interrompido/bloqueado/ignorado nao muda as operacoes seguintes dele; sinal so existe no instante da entrada.", "",
         "## Por ano (liquido R$ c/ custo | ops | acerto % | maior queda R$ | quebra)", "",
         "| ano | soma isolada | T2 liq | ops | acerto | queda | quebra | T2b liq | ops | acerto | queda | quebra | T2c liq | ops | acerto | queda | quebra |", "|" + "---|" * 17]
    f = lambda d: f"{d['liq']:+,.0f} | {d['ops']} | {d['acerto']} | {d['dd']:.0f} | {d['quebra'] or '-'}".replace(",", ".")
    for a in anos:
        L.append(f"| {a} | {iso[a]['liq']:+,.0f} ({iso[a]['ops']} ops) | " .replace(",", ".") +
                 " | ".join(f(res[v][a]) for v in res) + " |")
    L += ["", "", "## Por robo"]
    for v in res:
        L += ["", f"### {v}", "", "| ano | robo | sinais | assumiram | ignorados (concordancia) | inverteram | foram invertidos | liquido R$ (atribuido ao dono) |",
              "|---|---|---|---|---|---|---|---|"]
        for a in anos:
            tr = trs[v][a - 2022]
            for r in ROBOS:
                c = cnts[v][a][r]
                liq = float((tr[tr.dono == r].rs - 2.0).sum())
                L.append(f"| {a} | {r} | {c['sinais']} | {c['assumiram']} | {c['ignorados']} | {c['inverteram']} | {c['invertidos']} | {liq:+,.0f} |".replace(",", "."))
    L += ["", "## Inversoes por ano (T2)", "", "| ano | inversoes |", "|---|---|"]
    for a in anos:
        L.append(f"| {a} | {sum(c['inverteram'] for c in cnts['T2'][a].values())} |")
    (AQUI / "resultado.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("ok", flush=True)


if __name__ == "__main__":
    main()
