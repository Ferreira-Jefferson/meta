# -*- coding: utf-8 -*-
"""WIN@ retangulo: a CONCORDANCIA entre prazos muda a direcao da quebra?

Pergunta do dono (2026-09-15), depois de a regua unica dar ~50%: "se a
tendencia estiver em concordancia com tempos diferentes, isso muda o quadro?
Por exemplo, nos timestamps de 1 min e 5 min esta tudo em queda -- isso aumenta
as chances de romper para baixo?"

E' uma pergunta DIFERENTE da anterior. Antes eu variei o TAMANHO da regua
(15/30/60 barras, desde a abertura) e cada uma votou sozinha. Aqui a pergunta e'
sobre ACORDO ENTRE PRAZOS: um mercado em que M1, M5 e M15 apontam todos para
baixo e' um estado diferente de um em que so' o M1 aponta -- mesmo que a
variacao acumulada seja parecida.

## Como os prazos sao montados

M5 e M15 sao reamostrados da propria base M1 do pregao (`resample`), usando
SO' as barras ANTERIORES ao inicio real do retangulo -- nenhuma barra do
retangulo, nenhuma barra do futuro. Em cada prazo a tendencia e' a variacao do
fechamento nas ultimas N barras DAQUELE prazo:

    M1  : 10 barras =  10 minutos
    M5  : 10 barras =  50 minutos
    M15 : 10 barras = 150 minutos

E' o que um operador quer dizer com "olhei os tres graficos": mesmo numero de
candles em cada tela, portanto horizontes diferentes.

## O corte que evita contar ruido como tendencia

Um prazo cuja variacao e' menor que `MINIMO_FRAC` da largura da banda vota
NEUTRO, nao "para baixo". Sem isso, um M15 que andou 3 pontos entraria como
voto de queda e a "concordancia" viraria sorteio de sinal.

## As celulas

    3 de 3 alinhados  -- os tres prazos no mesmo sentido (a pergunta do dono)
    2 de 3            -- dois concordam, um neutro ou contrario
    sem alinhamento   -- o resto

Para cada uma: P(a quebra sai A FAVOR do sentido alinhado), com IC95 de
Wilson. Nulo = 50%. Veredito exige a MESMA direcao no IS e no OOS.

RESSALVAS: (1) o mesmo retangulo fisico aparece em mais de um W, entao as
tabelas agregadas tem dependencia entre linhas -- a tabela por W esta' junto
para isso ficar visivel. (2) condicionar a 3 de 3 afina a amostra; onde n < 25
a celula sai marcada.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_multitf_2026_09_15.py`
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


_base = _carrega("copawin_encerrar_mais_cedo_2026_09_14.py", "_base_mtf")
_tempos = _carrega("copawin_retangulo_tempos_2026_09_15.py", "_tempos_mtf")

SCRATCH = ROOT / "scratch"
CSV = SCRATCH / "copawin_retangulos.csv"
CORTE_OOS = pd.Timestamp("2026-06-13").date()

#: prazos e quantas barras DAQUELE prazo entram na conta
PRAZOS = (("M1", "1min", 10), ("M5", "5min", 10), ("M15", "15min", 10))
#: variacao menor que isto (fracao da largura da banda) vota NEUTRO
MINIMO_FRAC = 0.25


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
        if ini < 30 or L <= 0:
            continue
        # SO' barras anteriores ao inicio do retangulo
        antes = b.iloc[:ini]
        reg = dict(data=dia, janela_barras=int(r["janela_barras"]),
                   largura=L, direcao=r["tol_direcao"])
        votos = []
        ok = True
        for nome, regra, n_barras in PRAZOS:
            serie = antes["close"].resample(regra).last().dropna()
            if len(serie) < n_barras + 1:
                ok = False
                break
            var = float(serie.iloc[-1] - serie.iloc[-(n_barras + 1)])
            reg[f"var_{nome}"] = var
            voto = 0 if abs(var) < MINIMO_FRAC * L else (1 if var > 0 else -1)
            reg[f"voto_{nome}"] = voto
            votos.append(voto)
        if not ok:
            continue
        soma = sum(votos)
        n_baixo = sum(1 for v in votos if v < 0)
        n_cima = sum(1 for v in votos if v > 0)
        if n_cima == 3:
            reg["estado"], reg["sentido"] = "3 de 3 alinhados", 1
        elif n_baixo == 3:
            reg["estado"], reg["sentido"] = "3 de 3 alinhados", -1
        elif n_cima == 2 and n_baixo == 0:
            reg["estado"], reg["sentido"] = "2 de 3", 1
        elif n_baixo == 2 and n_cima == 0:
            reg["estado"], reg["sentido"] = "2 de 3", -1
        else:
            reg["estado"], reg["sentido"] = "sem alinhamento", (1 if soma > 0 else
                                                                -1 if soma < 0 else 0)
        out.append(reg)
    return out


def _linha(nome, s):
    s = s[(s.direcao != "fim do pregao") & (s.sentido != 0)]
    if len(s) == 0:
        return None
    favor = int((((s.sentido > 0) & (s.direcao == "cima"))
                 | ((s.sentido < 0) & (s.direcao == "baixo"))).sum())
    lo, hi = wilson(favor, len(s))
    marca = "  (n<25)" if len(s) < 25 else ""
    return (f"  {nome:<22}{len(s):>7}{br(100 * favor / len(s), 1) + '%':>16}"
            f"{'[' + br(lo, 1) + ' ; ' + br(hi, 1) + ']':>18}{marca}")


def main():
    if not CSV.exists():
        sys.exit(f"faltando {CSV} -- rode antes copawin_retangulo_lateral_2026_09_15.py")
    r = pd.read_csv(CSV, parse_dates=["confirmou_utc"])
    print("=" * 108)
    print("WIN@ retangulo -- A CONCORDANCIA ENTRE PRAZOS (M1/M5/M15) PREVE A DIRECAO DA QUEBRA?")
    print("=" * 108)
    print(f"{len(r)} retangulos | prazos: " + ", ".join(
        f"{n} ({k} barras = {k * int(g[:-3]) if g[:-3].isdigit() else '?'} min)"
        for n, g, k in PRAZOS))
    print(f"voto NEUTRO quando |variacao| < {int(MINIMO_FRAC*100)}% da largura da banda")
    print("nulo = 50% | IC95 de Wilson | veredito exige mesma direcao no IS e no OOS\n", flush=True)

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
    d.to_csv(SCRATCH / "copawin_retangulo_multitf.csv", index=False, encoding="utf-8")
    print(f"\n{len(d)} retangulos medidos -> scratch/copawin_retangulo_multitf.csv")

    print("\n" + "=" * 108)
    print("1) P(a quebra sai A FAVOR do sentido alinhado), por estado de concordancia")
    print("=" * 108)
    hdr = f"  {'estado':<22}{'n':>7}{'quebra a favor':>16}{'IC95':>18}"
    for jan in ("IS", "OOS"):
        print(f"\n  --- {jan} ---")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for est in ("3 de 3 alinhados", "2 de 3", "sem alinhamento"):
            out = _linha(est, d[(d.janela == jan) & (d.estado == est)])
            if out:
                print(out)

    print("\n" + "=" * 108)
    print("2) A MESMA CONTA, separada por LADO -- alinhado para BAIXO x para CIMA")
    print("   (a pergunta do dono e' sobre queda; um efeito que so' existe de um lado")
    print("    e' viés direcional, nao concordancia de prazos)")
    print("=" * 108)
    for jan in ("IS", "OOS"):
        print(f"\n  --- {jan} ---")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for est in ("3 de 3 alinhados", "2 de 3"):
            for sent, rot in ((-1, "para BAIXO"), (1, "para CIMA")):
                out = _linha(f"{est} {rot}",
                             d[(d.janela == jan) & (d.estado == est) & (d.sentido == sent)])
                if out:
                    print(out)

    print("\n" + "=" * 108)
    print("3) 3 DE 3 ALINHADOS, por janela W (para ver a dependencia entre linhas)")
    print("=" * 108)
    for jan in ("IS", "OOS"):
        print(f"\n  --- {jan} ---")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for W in sorted(d.janela_barras.unique()):
            out = _linha(f"W={W}", d[(d.janela == jan) & (d.estado == "3 de 3 alinhados")
                                     & (d.janela_barras == W)])
            if out:
                print(out)

    print("\n" + "=" * 108)
    print("4) QUANTOS RETANGULOS CAEM EM CADA ESTADO")
    print("=" * 108)
    print(d.groupby(["janela", "estado"]).size().unstack(fill_value=0).to_string())
    print("\nFIM.")


if __name__ == "__main__":
    main()
