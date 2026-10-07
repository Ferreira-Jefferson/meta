"""Estatistica descritiva da base F0 -> descritiva.md (sem custo; nada de decisao, so' contagens).

Uso: python descritiva.py   (precisa de votos.parquet e eventos.parquet)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI)); sys.path.insert(0, str(AQUI.parents[1]))
import dados as D  # noqa: E402
from votos import ESTRATEGIAS, ARQ as ARQ_V  # noqa: E402
from eventos import ARQ as ARQ_E  # noqa: E402

CURTO = {"Win": "Win", "Win_c1": "Win_c1", "WinCincoMedias": "Cinco", "WinDeslocamentoMatinal": "Desloc",
         "WinRetanguloEma34": "RetEma34", "WdoRetangulo": "WdoRet"}


def br(x, nd=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabela_condicional(e: pd.DataFrame, sufixo="") -> str:
    linhas = ["| k | favor: n | acerto | R$/op | contra: n | acerto | R$/op | neutro: n | acerto | R$/op |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    kmax = int(max(e["favor" + sufixo].max(), e["contra" + sufixo].max(), e["neutro" + sufixo].max(), 0))
    for k in range(0, max(kmax, 4 if sufixo else 5) + 1):
        cel = []
        for col in ("favor", "contra", "neutro"):
            g = e[e[col + sufixo] == k]
            if len(g):
                cel += [str(len(g)), br(100 * (g.rs > 0).mean()) + "%", br(g.rs.mean(), 2)]
            else:
                cel += ["0", "—", "—"]
        linhas.append(f"| {k} | " + " | ".join(cel) + " |")
    return "\n".join(linhas)


def main():
    ev = pd.read_parquet(ARQ_E)
    V = pd.read_parquet(ARQ_V)
    out = ["# Base F0 — estatística descritiva (WIN$N, 02/01–05/10/2026, sem custo, 1 contrato)", ""]
    out += ["Leitura dos votos na última M1 fechada antes de cada entrada (`eventos.parquet`). "
            "`favor`/`contra`/`neutro` = quantas das OUTRAS 5 estratégias votam o lado da entrada / o lado oposto / 0. "
            "Acerto = fração de operações com R$ > 0. Cada célula traz o seu n.", ""]
    out += ["**Atenção à gêmea:** Win e Win_c1 têm a mesma lógica de entrada, portanto o mesmo voto. Para essas duas, "
            "uma das 5 \"outras\" é sempre a gêmea (que vota igual ao próprio voto). A segunda tabela de cada uma "
            "conta só as 4 independentes.", ""]
    out += ["**Atenção ao próprio voto nos retângulos:** a entrada é uma limite no meio do retângulo que enche quando o "
            "preço VOLTA ao meio; na última M1 antes do preenchimento o fechamento muitas vezes já cruzou o meio, e o "
            "próprio voto aparece contra (WinRetanguloEma34 vota o lado da entrada em "
            f"{br(100 * (ev[ev.estrategia == 'WinRetanguloEma34']['WinRetanguloEma34.voto'] == ev[ev.estrategia == 'WinRetanguloEma34'].lado).mean())}% "
            "das entradas; WdoRetangulo em "
            f"{br(100 * (ev[ev.estrategia == 'WdoRetangulo']['WdoRetangulo.voto'] == ev[ev.estrategia == 'WdoRetangulo'].lado).mean())}%; "
            "as outras 4 em 100%).", ""]

    out += ["## 1. Resultado condicionado ao voto das outras", ""]
    resumo = []
    for nm in ESTRATEGIAS:
        e = ev[ev.estrategia == nm]
        out += [f"### {nm} — {len(e)} entradas, acerto {br(100 * (e.rs > 0).mean())}%, R$/op {br(e.rs.mean(), 2)}", ""]
        out += [tabela_condicional(e), ""]
        if nm in ("Win", "Win_c1"):
            out += ["Sem a gêmea (4 outras):", "", tabela_condicional(e, "_sem_gemea"), ""]
        suf = "_sem_gemea" if nm in ("Win", "Win_c1") else ""
        a = e[e["favor" + suf] > e["contra" + suf]]; b = e[e["favor" + suf] < e["contra" + suf]]; c = e[e["favor" + suf] == e["contra" + suf]]
        resumo.append((nm, len(a), a.rs.mean() if len(a) else np.nan, 100 * (a.rs > 0).mean() if len(a) else np.nan,
                       len(c), c.rs.mean() if len(c) else np.nan, 100 * (c.rs > 0).mean() if len(c) else np.nan,
                       len(b), b.rs.mean() if len(b) else np.nan, 100 * (b.rs > 0).mean() if len(b) else np.nan))
    out += ["### Resumo: mais outras a favor do que contra / empate / mais contra (Win e Win_c1 sem a gêmea)", "",
            "| estratégia | favor>contra: n | R$/op | acerto | empate: n | R$/op | acerto | contra>favor: n | R$/op | acerto |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for r in resumo:
        out.append(f"| {r[0]} | {r[1]} | {br(r[2], 2)} | {br(r[3])}% | {r[4]} | {br(r[5], 2)} | {br(r[6])}% | {r[7]} | {br(r[8], 2)} | {br(r[9])}% |")
    out.append("")

    # 2. correlacao diaria
    dias = [str(d) for d in D.dias()]
    ev["dia_saida"] = ev.saida.dt.strftime("%Y-%m-%d")
    M = ev.pivot_table(index="dia_saida", columns="estrategia", values="rs", aggfunc="sum").reindex(dias).fillna(0.0)[ESTRATEGIAS]
    corr = M.corr()
    out += ["## 2. Correlação diária de resultado (R$ por dia de saída)", "",
            f"Pearson sobre os {len(dias)} pregões do período, dia sem operação = 0. Pregões com operação: "
            + ", ".join(f"{CURTO[n]} {int((ev[ev.estrategia == n].dia_saida.nunique()))}" for n in ESTRATEGIAS) + ".", "",
            "| | " + " | ".join(CURTO[n] for n in ESTRATEGIAS) + " |", "|---|" + "---|" * len(ESTRATEGIAS)]
    for a in ESTRATEGIAS:
        out.append(f"| {CURTO[a]} | " + " | ".join(br(corr.loc[a, b], 2) for b in ESTRATEGIAS) + " |")
    out += ["", "Só nos dias em que as DUAS operaram (n de dias entre parênteses):", "",
            "| | " + " | ".join(CURTO[n] for n in ESTRATEGIAS) + " |", "|---|" + "---|" * len(ESTRATEGIAS)]
    Mn = ev.pivot_table(index="dia_saida", columns="estrategia", values="rs", aggfunc="sum").reindex(dias)[ESTRATEGIAS]
    for a in ESTRATEGIAS:
        cel = []
        for b in ESTRATEGIAS:
            x = Mn[[a, b]].dropna() if a != b else Mn[[a]].dropna()
            if a == b:
                cel.append(f"({len(x)})")
            else:
                cel.append(f"{br(x[a].corr(x[b]), 2)} ({len(x)})" if len(x) > 2 else f"— ({len(x)})")
        out.append(f"| {CURTO[a]} | " + " | ".join(cel) + " |")
    out.append("")

    # 3. concordancia de votos por par (todas as M1 do periodo)
    out += ["## 3. Concordância de votos por par (todas as M1 do período)", "",
            f"{len(V):,} barras M1. ".replace(",", ".") + "Em cada célula: % de barras no mesmo lado, sobre as barras em que "
            "as duas votam ≠ 0; entre parênteses, % das barras em que as duas votam ≠ 0 e o n dessas barras. "
            "Na diagonal, % das barras com voto ≠ 0.", "",
            "| | " + " | ".join(CURTO[n] for n in ESTRATEGIAS) + " |", "|---|" + "---|" * len(ESTRATEGIAS)]
    for a in ESTRATEGIAS:
        cel = []
        va = V[f"{a}.voto"].to_numpy()
        for b in ESTRATEGIAS:
            vb = V[f"{b}.voto"].to_numpy()
            ambos = (va != 0) & (vb != 0)
            n = int(ambos.sum())
            if a == b:
                cel.append(f"ativo {br(100 * (va != 0).mean())}%")
            elif n:
                cel.append(f"{br(100 * (va[ambos] == vb[ambos]).mean())}% ({br(100 * ambos.mean())}%; {n})")
            else:
                cel.append("—")
        out.append(f"| {CURTO[a]} | " + " | ".join(cel) + " |")
    out += ["", "Fração de barras por voto:", "", "| estratégia | +1 | −1 | 0 | forca média (voto ≠ 0) |", "|---|---|---|---|---|"]
    for a in ESTRATEGIAS:
        v = V[f"{a}.voto"]; f = V[f"{a}.forca"][v != 0]
        out.append(f"| {a} | {br(100 * (v > 0).mean())}% | {br(100 * (v < 0).mean())}% | {br(100 * (v == 0).mean())}% | {br(f.mean(), 2)} |")
    out.append("")
    (AQUI / "descritiva.md").write_text("\n".join(out), encoding="utf-8")
    print("ok ->", AQUI / "descritiva.md", flush=True)


if __name__ == "__main__":
    main()
