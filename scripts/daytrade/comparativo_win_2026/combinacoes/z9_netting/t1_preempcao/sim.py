"""Z9-T1 preempcao total (T1) e T1b (mesmo lado so' transfere a gestao). python sim.py"""
import sys
from pathlib import Path
import pandas as pd
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import base  # noqa: E402
from base import ROBOS, operacoes, preco, resumo  # noqa: E402

PT = 0.20


def simular(ops, transfere):
    """ops ja' ordenado por entrada, prio. Retorna (trades df, sinais por robo)."""
    tr, pos = [], None
    def fecha(motivo, t_saida, p_saida):
        nonlocal pos
        rs = (p_saida - pos["pe"]) * PT * pos["lado"]
        tr.append(dict(ano=pos["te"].year, dono=pos["dono"], dono_abertura=pos["dono0"], entrada=pos["te"], saida=t_saida,
                       lado=pos["lado"], preco_entrada=pos["pe"], preco_saida=p_saida, rs=rs, motivo_saida=motivo))
        pos = None
    sig = {r: dict(sinais=0, assumiu=0, interrompido=0) for r in ROBOS}
    for o in ops.itertuples():
        t, r = o.entrada, o.estrategia
        sig[r]["sinais"] += 1
        if pos is not None and pos["saida"] <= t:
            fecha("natural", pos["saida"], pos["ps"])
        if pos is not None and pos["dono"] == r:
            continue
        novo = dict(dono=r, dono0=r, lado=o.lado, pe=o.preco_entrada, te=t, saida=o.saida, ps=o.preco_saida)
        if pos is None:
            pos = novo; sig[r]["assumiu"] += 1; continue
        sig[pos["dono"]]["interrompido"] += 1
        sig[r]["assumiu"] += 1
        if transfere and pos["lado"] == o.lado:
            pos.update(dono=r, saida=o.saida, ps=o.preco_saida)
            continue
        fecha("preemptada", t, preco(t))
        pos = novo
    if pos is not None:
        fecha("natural", pos["saida"], pos["ps"])
    return pd.DataFrame(tr), sig


def main():
    res = {}
    for nome, tf in (("T1", False), ("T1b", True)):
        todos, sigs = [], {}
        for ano in range(2022, 2027):
            ops = operacoes(ano)
            t, sg = simular(ops, tf)
            todos.append(t); sigs[ano] = sg
            r = resumo(t)[ano]
            print(nome, ano, r, flush=True)
        t = pd.concat(todos, ignore_index=True)
        t.to_csv(AQUI / f"trades_{nome}.csv", index=False)
        res[nome] = (t, sigs)
    iso = {a: resumo(operacoes(a))[a] for a in range(2022, 2027)}
    # sanidade: 3 trocas manuais
    t1 = res["T1"][0]
    pre = t1[t1.motivo_saida == "preemptada"]
    for i in (0, len(pre) // 2, len(pre) - 1):
        x = pre.iloc[i]
        print("SANIDADE", x.dono_abertura, x.lado, "entrou", x.entrada, "@", x.preco_entrada, "saiu", x.saida, "@",
              x.preco_saida, "preco(t)=", preco(x.saida), flush=True)
    L = ["# Z9-T1 preempcao total\n",
         "Regra: o sinal de outro robo encerra a posicao a mercado (`preco(t)`, t = entrada do novo) e ele assume a `preco_entrada` dele. "
         "T1b: mesmo lado so' transfere a gestao (preco de entrada original, saida do novo robo, 1 operacao). Mesmo robo: ignora. "
         "Empate: ordem de ROBOS. Custo R$2/operacao, R$1.000 por ano, 1 contrato.\n",
         "Aproximacao: robo interrompido/bloqueado nao altera as operacoes seguintes dele; sinal so' existe no instante da entrada; "
         "sinal de robo que ja' tem a posicao e' ignorado (nao e' contado como assumido).\n",
         "## Por ano (liquido c/ custo, ops, acerto %, maior queda R$, quebra)\n",
         "| ano | soma isolada liq* | T1 liq | T1 ops | T1 acerto | T1 DD | T1 quebra | T1b liq | T1b ops | T1b acerto | T1b DD | T1b quebra |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in range(2022, 2027):
        r1, r2 = resumo(res["T1"][0])[a], resumo(res["T1b"][0])[a]
        L.append(f"| {a} | {iso[a]['liq']:.0f} | {r1['liq']:.0f} | {r1['ops']} | {r1['acerto']} | {r1['dd']:.0f} | {r1['quebra']} | "
                 f"{r2['liq']:.0f} | {r2['ops']} | {r2['acerto']} | {r2['dd']:.0f} | {r2['quebra']} |")
    L.append("\n*soma isolada = soma das operacoes isoladas dos 5 robos (sem NETTING): 2022 +5.026, 2023 +4.512, 2024 +4.720, 2025 +5.208, 2026 +14.079.\n")
    for nome in ("T1", "T1b"):
        t, sigs = res[nome]
        L.append(f"## Por robo -- {nome} (liquido c/ custo pelo dono ao fechar (em T1b a cadeia transferida fica toda com o ultimo dono, entao o liquido por robo nao e' atribuicao justa); anos somados 2022-2026)\n")
        L.append("| robo | sinais | assumiu | interrompido | ops (dono) | liquido R$ |")
        L.append("|---|---|---|---|---|---|")
        for r in ROBOS:
            s = {k: sum(sigs[a][r][k] for a in sigs) for k in ("sinais", "assumiu", "interrompido")}
            g = t[t.dono == r]
            L.append(f"| {r} | {s['sinais']} | {s['assumiu']} | {s['interrompido']} | {len(g)} | {g.rs.sum() - 2 * len(g):.0f} |")
        L.append("")
        L.append("Por ano e robo (liquido): " + "; ".join(
            f"{a}: " + ", ".join(f"{r[:8]} {t[(t.ano==a)&(t.dono==r)].rs.sum()-2*len(t[(t.ano==a)&(t.dono==r)]):.0f}" for r in ROBOS)
            for a in range(2022, 2027)) + "\n")
    (AQUI / "resultado.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L), flush=True)


if __name__ == "__main__":
    main()
