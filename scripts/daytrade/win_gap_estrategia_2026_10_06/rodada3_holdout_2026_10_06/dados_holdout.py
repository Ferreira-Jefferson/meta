# -*- coding: utf-8 -*-
"""Checagem de dados do holdout (2025-12-19 a 2026-02-19) -> DADOS_HOLDOUT.md. Sem ticks: tudo em barras."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import dados  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
INI, FIM = pd.Timestamp("2025-12-19"), pd.Timestamp("2026-02-19")


def md(df):
    if df.empty:
        return "_(nenhum)_\n"
    return "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n" + \
        "\n".join("| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False)) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    b5, d = dados.carrega("2026")
    m1 = pd.read_parquet(ROOT / "data" / "win_sem_leiloes" / "m1_WIN$N.parquet")
    jan = d[(d.index >= INI) & (d.index <= FIM)]
    # WIN@D (serie ajustada por diferenca): gap em pontos preservado, inclusive nas rolagens
    z = pd.read_csv(ROOT / "data" / "wdo-mt5" / "WIN@D_M1_202110010900_202610011717.csv", sep="\t")
    z.columns = [c.strip("<>").lower() for c in z.columns]
    z.index = pd.to_datetime(z["date"] + " " + z["time"], format="%Y.%m.%d %H:%M:%S")
    z = z[(z.index >= "2025-12-01") & (z.index < "2026-02-21")]
    zd = z.groupby(z.index.normalize())
    zg = pd.DataFrame({"abre": zd["open"].first(), "fecha": zd["close"].last()})
    zg["gap_D"] = zg["abre"] - zg["fecha"].shift(1)
    L = ["# DADOS DO HOLDOUT (2025-12-19 a 2026-02-19)\n",
         "## 0. Ticks\n",
         "- MT5 (`copy_ticks_range`, dia inteiro 00:00-24:00) devolveu 0 ticks para WIN$N, WIN$, WIN@, WIN@D, WIN@N e WIN$D em 2025-12-22, 2026-01-15 e 2026-02-19, e 2.074.311 ticks em 2026-02-20 (primeiro dia com tick). Os contratos WINZ25 e WING26 nao existem no terminal (`Terminal: Not found`). Nao ha tick local anterior a 2026-02-20 (`data/raw_ticks`, `data/cache_win_ticks`, `data/comparativo_win_2026/ticks`).",
         "- Portanto: execucao em barras M1 com a regra conservadora da barra do fill (CRITERIOS.md). Leilao e call sao **PROXY** (`proxy=True` em todos os dias): preco do leilao = open da barra M1 do leilao (nao corrigido); preco do call = close da ultima barra continua; volume do call estimado.\n",
         "## 1. Gap: WIN$N (proxy) x serie ajustada WIN@D (independente)\n"]
    x = jan[["gap", "call_preco", "leilao_preco"]].join(zg[["gap_D"]])
    x["dif"] = x.gap - x.gap_D
    comp = x[x.gap.notna() & x.gap_D.notna()]
    L.append(f"- Dias comparaveis: {len(comp)}. |gap$N − gapD|: mediana {comp['dif'].abs().median():.0f} pts, maxima {comp['dif'].abs().max():.0f} pts; iguais em {(comp['dif'].abs() < 1).sum()}/{len(comp)}.")
    big = comp[comp["dif"].abs() >= 1]
    L.append("- Dias em que difere:\n" + md(big.reset_index()[["data", "gap", "gap_D", "dif"]].assign(data=lambda t: t.data.dt.date)))
    L.append("## 2. Rolagens (WINZ25→WING26 em 2025-12-17; WING26→WINJ26 em 2026-02-18), detectadas pelo tamanho do gap\n")
    pre = d[(d.index >= "2025-12-12") & (d.index <= "2026-02-20")]
    xx = pre[["gap"]].join(zg[["gap_D"]])
    xx["|gap$N|−|gapD|"] = xx.gap.abs() - xx.gap_D.abs()
    grandes = xx[(xx["|gap$N|−|gapD|"].abs() > 1500) | xx.gap.isna()]
    L.append(f"- |gap| mediano dos dias da janela: {comp.gap.abs().median():.0f} pts; maior |gap| nao-rolagem: {comp.gap.abs().max():.0f} pts.")
    L.append("- Dias com degrau entre as duas series (|gap$N| − |gapD| > 1.500) ou sem gap:\n" + md(grandes.reset_index().assign(data=lambda t: t.data.dt.date)))
    L.append("- 2025-12-17 fica fora da janela (so' aquecimento do ATR, e excluido da media por ser rolagem); 2026-02-18 (rolagem + sessao parcial 13:00) esta na janela e e' EXCLUIDO; 2026-02-19, o dia seguinte, usa o call de 02-18 (ja' no contrato novo) e entra.\n")
    L.append("## 3. Sessoes: feriados, meio-pregao e fim do continuo\n")
    ex = jan[jan.excluir]
    L.append("- Dias da janela excluidos:\n" + md(ex.reset_index()[["data", "n_barras", "primeira", "motivo_excl"]].assign(data=lambda t: t.data.dt.date)))
    cal = pd.bdate_range(INI, FIM)
    falta = [x.date() for x in cal if x not in jan.index]
    L.append(f"- Dias uteis sem pregao na base (feriados: 24/12 e 31/12 sem dados, 01/01, 16-17/02 carnaval): {falta}")
    L.append(f"- Pregoes elegiveis: {int((~jan.excluir).sum())}; todos com 113 barras M5 (09:00 a 18:20) e 1a barra as 09:00: {bool((jan[~jan.excluir].n_barras == 113).all() and (jan[~jan.excluir].primeira == pd.Timestamp('09:00').time()).all())}.")
    fc = jan["fim_continuo"].dt.strftime("%H:%M").value_counts().to_dict()
    L.append(f"- `fim_continuo` (data/b3_grade_horaria_win.csv) por dia: {fc}; maior hora de barra M5 na base: {b5.index.time.max()}; barras com hora >= 18:25: {int((b5.index.time >= pd.Timestamp('18:25').time()).sum())}.\n")
    L.append("## 4. Sem leilao nem call nas barras\n")
    w1 = m1[(m1.index >= INI) & (m1.index < FIM + pd.Timedelta(days=1))]
    ult = w1.groupby(w1.index.normalize()).tail(1)
    L.append(f"- Ultima barra M1 de cada dia: hora {sorted(set(ult.index.strftime('%H:%M')))} (18:24 = ultima do continuo; o call esta fora); flag `ultima_continua` em {int(w1.ultima_continua.sum())} barras (1 por dia). Barras com `hl_aprox`: {int(w1.hl_aprox.sum())} (maxima/minima do dia aproximadas so' quando o preco removido era o extremo); `flag_leilao`: {int(w1.flag_leilao.sum())} barras (a barra do leilao, com volume removido; open nao corrigido).")
    # consistencia intradia $N x @D
    dif_std = []
    for dia in jan.index:
        a = w1[w1.index.normalize() == dia].close
        bz = z[z.index.normalize() == dia].close
        j = pd.concat([a, bz], axis=1, join="inner")
        if len(j) > 100:
            dif_std.append(float((j.iloc[:, 0] - j.iloc[:, 1]).std()))
    L.append(f"- Consistencia intradia WIN$N x WIN@D (close M1, desvio padrao da diferenca dentro do dia; 0 = mesma serie a menos de constante): mediana {np.median(dif_std):.1f} pts, maxima {np.max(dif_std):.1f} pts em {len(dif_std)} dias.\n")
    L.append("## 5. ATR (aquecimento)\n")
    L.append("- ATR dos pregoes anteriores a D: media da amplitude (max-min das barras M5) dos <= 10 pregoes validos anteriores. Para os primeiros dias da janela le so' precos de 2025-12-04 a 2025-12-18 (rolagem de 12-17 excluida da media); nenhum dia da IS.\n")
    (AQUI / "DADOS_HOLDOUT.md").write_text("\n".join(L), encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
