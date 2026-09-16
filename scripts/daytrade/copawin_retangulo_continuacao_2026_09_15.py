# -*- coding: utf-8 -*-
"""WIN@ retangulo: a quebra CONTINUA a tendencia anterior ou INVERTE?

Pergunta do dono (2026-09-15): "o rompimento tende a seguir a tendencia
imediatamente anterior a lateralizacao ou oposta? Ele vinha numa perna de
queda, comecou a lateralizar; quando acaba o retangulo, rompe para cima contra
a tendencia, ou a favor, continuando a queda? Percentualmente, qual e' mais
comum -- ou nao tem padrao claro?"

## Como cada peca e' definida

INICIO REAL do retangulo: andando para TRAS a partir da confirmacao com a
banda ja conhecida, ate 3 fechamentos seguidos alem de 25% da largura. E' a
mesma funcao usada em `copawin_retangulo_tempos_2026_09_15.py`, importada de
la' -- nao reimplementada, para os dois scripts nao divergirem.

TENDENCIA ANTERIOR: variacao do fechamento nas K barras que antecedem o inicio
real, para K in {15, 30, 60} e tambem "desde a abertura do pregao ate o
inicio". Quatro reguas de propOsito: "a tendencia imediatamente anterior" e'
uma ideia visual, e o resultado nao pode depender de uma unica escolha de
janela. Se as quatro discordarem, isso E' a resposta.

FORCA da tendencia: |variacao| / largura da banda. Uma perna que andou menos
que a propria largura do retangulo nao e' tendencia, e' ruido -- por isso o
resultado tambem sai separado por faixa de forca.

QUEBRA: a direcao registrada na deteccao (3 fechamentos seguidos alem de 25%
da largura, para cima ou para baixo). Retangulos que morreram no FIM DO
PREGAO nao tem quebra e ficam fora do percentual -- sao contados a parte.

    CONTINUACAO = tendencia para baixo e quebra para baixo, ou
                  tendencia para cima  e quebra para cima
    INVERSAO    = o contrario

## O nulo

Sem padrao, continuacao = 50%. O IC95 de Wilson sai ao lado de cada
percentual, e o veredito exige a MESMA direcao no IS e no OOS -- sinal trocado
entre as janelas ja matou meia duzia de achados neste projeto.

RESSALVA DE INDEPENDENCIA: o mesmo retangulo fisico pode aparecer em mais de
um W (a varredura roda 30/45/60/90/120 separadamente). Por isso cada W e'
reportado como amostra propria e os n NAO se somam.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_continuacao_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")


def _carrega(nome, apelido):
    spec = importlib.util.spec_from_file_location(apelido, Path(__file__).with_name(nome))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_base = _carrega("copawin_encerrar_mais_cedo_2026_09_14.py", "_base_cont")
_tempos = _carrega("copawin_retangulo_tempos_2026_09_15.py", "_tempos_cont")

SCRATCH = ROOT / "scratch"
CSV = SCRATCH / "copawin_retangulos.csv"
CORTE_OOS = pd.Timestamp("2026-06-13").date()
LOOKBACKS = (15, 30, 60)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def wilson(k, n):
    if n == 0:
        return (float("nan"), float("nan"))
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * max(0.0, c - m), 100 * min(1.0, c + m))


def roda_dia(args):
    dia, linhas = args
    df, _ = _base._df()
    b = df[df.index.date == pd.Timestamp(dia).date()]
    if b.empty:
        return []
    idx = b.index
    close = b["close"].to_numpy(float)
    mapa = {ts: i for i, ts in enumerate(idx)}
    out = []
    for r in linhas:
        i_conf = mapa.get(pd.Timestamp(r["confirmou_utc"]))
        if i_conf is None:
            continue
        topo, piso, L = r["topo"], r["piso"], r["largura_pontos"]
        ini = _tempos._inicio_real(close, i_conf, topo, piso, L)
        if ini <= 0:
            continue
        reg = dict(data=dia, janela_barras=int(r["janela_barras"]),
                   largura=L, direcao=r["tol_direcao"])
        for K in LOOKBACKS:
            a = ini - K
            if a < 0:
                reg[f"var_{K}"] = float("nan")
                reg[f"forca_{K}"] = float("nan")
                continue
            var = float(close[ini - 1] - close[a])
            reg[f"var_{K}"] = var
            reg[f"forca_{K}"] = abs(var) / L if L > 0 else float("nan")
        var_ab = float(close[ini - 1] - close[0])
        reg["var_abertura"] = var_ab
        reg["forca_abertura"] = abs(var_ab) / L if L > 0 else float("nan")
        out.append(reg)
    return out


def _tabela(d, col_var, col_forca, rotulo):
    print(f"\n  --- tendencia medida por {rotulo} ---")
    hdr = (f"  {'W':<6}{'jan':<5}{'n com quebra':>14}{'continuacao':>13}{'IC95':>18}"
           f"{'inversao':>11}{'sem quebra':>12}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in sorted(d.janela_barras.unique()):
        for jan in ("IS", "OOS"):
            s = d[(d.janela_barras == W) & (d.janela == jan)]
            sem = int((s.direcao == "fim do pregao").sum())
            s = s[(s.direcao != "fim do pregao") & s[col_var].notna() & (s[col_var] != 0)]
            if len(s) < 15:
                continue
            cont = int((((s[col_var] > 0) & (s.direcao == "cima"))
                        | ((s[col_var] < 0) & (s.direcao == "baixo"))).sum())
            lo, hi = wilson(cont, len(s))
            print(f"  {W:<6}{jan:<5}{len(s):>14}"
                  f"{br(100 * cont / len(s), 1) + '%':>13}"
                  f"{'[' + br(lo, 1) + ' ; ' + br(hi, 1) + ']':>18}"
                  f"{br(100 - 100 * cont / len(s), 1) + '%':>11}{sem:>12}")


def _por_forca(d, col_var, col_forca, rotulo):
    print(f"\n  --- por FORCA da tendencia ({rotulo}); forca = |variacao| / largura da banda ---")
    cortes = [(0, 0.5, "fraca (<0,5x)"), (0.5, 1.0, "media (0,5-1x)"),
              (1.0, 2.0, "forte (1-2x)"), (2.0, 99, "muito forte (>2x)")]
    hdr = f"  {'faixa':<20}{'jan':<5}{'n':>7}{'continuacao':>13}{'IC95':>18}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    base = d[(d.direcao != "fim do pregao") & d[col_var].notna() & (d[col_var] != 0)]
    for lo_f, hi_f, nome in cortes:
        for jan in ("IS", "OOS"):
            s = base[(base.janela == jan) & (base[col_forca] >= lo_f) & (base[col_forca] < hi_f)]
            if len(s) < 15:
                continue
            cont = int((((s[col_var] > 0) & (s.direcao == "cima"))
                        | ((s[col_var] < 0) & (s.direcao == "baixo"))).sum())
            lo, hi = wilson(cont, len(s))
            print(f"  {nome:<20}{jan:<5}{len(s):>7}{br(100 * cont / len(s), 1) + '%':>13}"
                  f"{'[' + br(lo, 1) + ' ; ' + br(hi, 1) + ']':>18}")
    print("  (todas as janelas W juntas nesta tabela -- ver a ressalva de independencia)")


def main():
    if not CSV.exists():
        sys.exit(f"faltando {CSV} -- rode antes copawin_retangulo_lateral_2026_09_15.py")
    r = pd.read_csv(CSV, parse_dates=["confirmou_utc"])
    print("=" * 112)
    print("WIN@ retangulo -- A QUEBRA CONTINUA A TENDENCIA ANTERIOR, OU INVERTE?")
    print("=" * 112)
    print(f"{len(r)} retangulos | nulo = 50% | IC95 de Wilson ao lado")
    print("tendencia = variacao do fechamento nas K barras antes do INICIO REAL do retangulo\n",
          flush=True)

    grupos = [(d, g.to_dict("records")) for d, g in r.groupby("data")]
    linhas = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(roda_dia, g): g[0] for g in grupos}
        feitos = 0
        for fut in as_completed(futs):
            linhas.extend(fut.result())
            feitos += 1
            if feitos % 40 == 0:
                print(f"  ... {feitos}/{len(grupos)} pregoes", flush=True)

    d = pd.DataFrame(linhas)
    d["janela"] = np.where(pd.to_datetime(d["data"]).dt.date < CORTE_OOS, "IS", "OOS")
    d.to_csv(SCRATCH / "copawin_retangulo_continuacao.csv", index=False, encoding="utf-8")
    print(f"\n{len(d)} retangulos medidos -> scratch/copawin_retangulo_continuacao.csv")

    print("\n" + "=" * 112)
    print("CONTINUACAO x INVERSAO, por regua de tendencia")
    print("=" * 112)
    for K in LOOKBACKS:
        _tabela(d, f"var_{K}", f"forca_{K}", f"{K} barras antes do inicio")
    _tabela(d, "var_abertura", "forca_abertura", "desde a abertura do pregao")

    print("\n" + "=" * 112)
    print("A FORCA DA PERNA ANTERIOR MUDA ALGUMA COISA?")
    print("=" * 112)
    _por_forca(d, "var_30", "forca_30", "30 barras antes")
    _por_forca(d, "var_abertura", "forca_abertura", "desde a abertura")

    print("\n" + "=" * 112)
    print("CONFERENCIA -- a quebra e' simetrica em termos absolutos?")
    print("=" * 112)
    for jan in ("IS", "OOS"):
        s = d[d.janela == jan]
        cima = int((s.direcao == "cima").sum())
        baixo = int((s.direcao == "baixo").sum())
        fim = int((s.direcao == "fim do pregao").sum())
        tot = cima + baixo
        lo, hi = wilson(cima, tot)
        print(f"  {jan}: quebra para CIMA {cima} / BAIXO {baixo} / sem quebra {fim}  -> "
              f"cima = {br(100*cima/tot, 1)}%  IC95 [{br(lo,1)} ; {br(hi,1)}]")
    print("\n  (se este numero ja e' 50/50, uma assimetria continuacao/inversao so' pode vir")
    print("   da correlacao com a tendencia anterior, nao de um vies direcional do WIN)")
    print("\nFIM.")


if __name__ == "__main__":
    main()
