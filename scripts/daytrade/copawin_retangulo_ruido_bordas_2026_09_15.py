# -*- coding: utf-8 -*-
"""WIN@ retangulo: quanto a BORDA varia em torno da linha?

Pergunta do dono (2026-09-15): "quantos pontos em media tem fora, tanto pra
cima quanto pra baixo do topo e do fundo? Descobrimos que a media do topo e'
123, mas ele varia entre 120 e 125 -- ou seja, varia 2 pontos acima da media."

E' a pergunta operacional da linha inteira. A borda de um retangulo nao e' um
preco, e' uma REGIAO: cada visita ao topo para num lugar um pouco diferente. O
tamanho dessa regiao decide duas coisas que nenhum backtest conserta depois:

  - onde a ordem-limite de entrada tem de ficar (dentro da regiao ela enche
    cedo demais e o preco ainda sobe; fora dela nao enche nunca)
  - onde o stop pode ficar (colado na linha, o proprio ruido da borda o
    executa antes de o retangulo ter quebrado de verdade)

## A medida

Para cada retangulo de `scratch/copawin_retangulos.csv`, com o topo e o piso
ja definidos pelo detector (quantil 90 dos `high` / quantil 10 dos `low` da
janela):

  VISITA ao topo = corrida de barras consecutivas com `high >= topo - 8%L`,
  colapsada em uma so'. O EXTREMO da visita e' o maior `high` dela.

      desvio_topo = extremo_da_visita - topo

  Positivo = a visita FUROU a linha (foi alem). Negativo = parou ANTES dela.
  Simetrico no piso: `desvio_piso = piso - menor low da visita`.

Reportado em pontos, em ticks (1 tick = 5 pontos no WIN) e em fracao da
largura da banda -- as tres leituras respondem perguntas diferentes, e a
terceira e' a unica comparavel entre retangulos de larguras diferentes.

## Os dois recortes

  1. DENTRO da janela de deteccao -- as visitas que DEFINIRAM a linha. Este
     numero e' otimista por construcao: o quantil 90 foi calculado sobre
     essas mesmas barras, entao os desvios sao pequenos porque a linha foi
     ajustada a eles.
  2. DEPOIS da confirmacao -- as visitas que aconteceram com a linha JA
     fixada. **E' o unico numero operacional**, e e' maior que o primeiro.
     Quem desenhar o stop com o numero (1) vai ser estopado pelo numero (2).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_ruido_bordas_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "_base_ruido", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

SCRATCH = ROOT / "scratch"
CSV = SCRATCH / "copawin_retangulos.csv"
CORTE_OOS = pd.Timestamp("2026-06-13").date()
TOL = 0.08          # a mesma zona de toque do detector
TICK = 5.0          # WIN: 1 tick = 5 pontos


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _visitas(high, low, topo, piso, L, corta_ultima=False):
    """Devolve (desvios_topo, desvios_piso) -- um valor por VISITA.

    `corta_ultima=True` descarta a corrida que termina na ULTIMA barra da
    fatia. Sem isso o recorte pos-confirmacao mede o ROMPIMENTO FINAL como se
    fosse uma visita: as barras que matam o retangulo tambem satisfazem a
    condicao de toque, e o extremo delas (centenas de pontos alem da linha)
    domina a media. O que se quer aqui e' o ruido das visitas que VOLTARAM."""
    zona = TOL * L
    saida = []
    for arr, linha, sinal in ((high, topo, 1.0), (low, piso, -1.0)):
        dentro = (arr >= topo - zona) if sinal > 0 else (arr <= piso + zona)
        vals, i, n = [], 0, len(dentro)
        while i < n:
            if dentro[i]:
                j = i
                while j + 1 < n and dentro[j + 1]:
                    j += 1
                if not (corta_ultima and j == n - 1):
                    extremo = float(arr[i:j + 1].max() if sinal > 0 else arr[i:j + 1].min())
                    vals.append((extremo - linha) * sinal)
                i = j + 1
            else:
                i += 1
        saida.append(vals)
    return saida[0], saida[1]


def roda_dia(args):
    dia, linhas = args
    df, _ = _base._df()
    b = df[df.index.date == pd.Timestamp(dia).date()]
    if b.empty:
        return []
    idx = b.index
    high = b["high"].to_numpy(float)
    low = b["low"].to_numpy(float)
    mapa = {ts: i for i, ts in enumerate(idx)}
    out = []
    for r in linhas:
        i_conf = mapa.get(pd.Timestamp(r["confirmou_utc"]))
        if i_conf is None:
            continue
        W = int(r["janela_barras"])
        topo, piso, L = r["topo"], r["piso"], r["largura_pontos"]
        i_ini = max(0, i_conf - W + 1)
        i_fim = min(len(high) - 1, i_conf + int(r["tol_barras_depois"]))

        for rot, a, z in (("janela (definiu a linha)", i_ini, i_conf),
                          ("depois da confirmacao", i_conf + 1, i_fim)):
            if z <= a:
                continue
            dt, dp = _visitas(high[a:z + 1], low[a:z + 1], topo, piso, L,
                              corta_ultima=(rot == "depois da confirmacao"))
            for lado, vals in (("topo", dt), ("piso", dp)):
                for v in vals:
                    out.append(dict(data=dia, janela_barras=W, recorte=rot,
                                    lado=lado, desvio_pontos=v,
                                    desvio_frac=v / L if L > 0 else float("nan"),
                                    largura=L))
    return out


def _bloco(d, titulo):
    print("\n" + "=" * 112)
    print(titulo)
    print("=" * 112)
    hdr = (f"  {'W':<6}{'lado':<7}{'jan':<5}{'visitas':>9}{'media':>9}{'dp':>8}"
           f"{'p10':>8}{'mediana':>9}{'p90':>8}{'|desvio| med':>14}{'em ticks':>10}"
           f"{'% da largura':>14}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in sorted(d.janela_barras.unique()):
        for lado in ("topo", "piso"):
            for jan in ("IS", "OOS"):
                s = d[(d.janela_barras == W) & (d.lado == lado) & (d.janela == jan)]
                if len(s) < 10:
                    continue
                v = s.desvio_pontos
                print(f"  {W:<6}{lado:<7}{jan:<5}{len(s):>9}{br(v.mean(), 1):>9}"
                      f"{br(v.std(ddof=1), 1):>8}{br(v.quantile(.10), 1):>8}"
                      f"{br(v.median(), 1):>9}{br(v.quantile(.90), 1):>8}"
                      f"{br(v.abs().mean(), 1):>14}{br(v.abs().mean() / TICK, 1):>10}"
                      f"{br(100 * s.desvio_frac.abs().mean(), 1) + '%':>14}")
    print("\n  desvio POSITIVO = a visita FUROU a linha (foi alem dela);")
    print("  NEGATIVO = parou ANTES de chegar nela.")


def main():
    if not CSV.exists():
        sys.exit(f"faltando {CSV} -- rode antes copawin_retangulo_lateral_2026_09_15.py")
    r = pd.read_csv(CSV, parse_dates=["confirmou_utc"])
    print("=" * 112)
    print("WIN@ retangulo -- RUIDO DA BORDA: quanto a visita se afasta da linha")
    print("=" * 112)
    print(f"{len(r)} retangulos | zona de toque {int(TOL*100)}% da largura | 1 tick = {br(TICK,0)} pontos")
    print("uma observacao por VISITA (barras consecutivas colapsadas), pelo EXTREMO da visita.\n",
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
    d.to_csv(SCRATCH / "copawin_retangulo_ruido_bordas.csv", index=False, encoding="utf-8")
    print(f"\n{len(d)} visitas medidas -> scratch/copawin_retangulo_ruido_bordas.csv")

    _bloco(d[d.recorte == "janela (definiu a linha)"],
           "A) DENTRO da janela de deteccao -- OTIMISTA (a linha foi ajustada a estas visitas)")
    _bloco(d[d.recorte == "depois da confirmacao"],
           "B) DEPOIS da confirmacao -- O NUMERO OPERACIONAL (linha ja fixada)")

    print("\n" + "=" * 112)
    print("C) A CONTA DO STOP: a que distancia da linha o stop deixa de ser ruido?")
    print("   (fracao das visitas POS-CONFIRMACAO que furam a linha em mais de X pontos)")
    print("=" * 112)
    pos = d[d.recorte == "depois da confirmacao"]
    dist = [5, 10, 15, 20, 25, 30, 40, 50, 75, 100]
    hdr = f"  {'W':<6}{'lado':<7}{'n':>7}" + "".join(f"{f'>{x}p':>8}" for x in dist)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in sorted(pos.janela_barras.unique()):
        for lado in ("topo", "piso"):
            s = pos[(pos.janela_barras == W) & (pos.lado == lado)]
            if len(s) < 10:
                continue
            linha = f"  {W:<6}{lado:<7}{len(s):>7}"
            for x in dist:
                linha += f"{br(100 * (s.desvio_pontos > x).mean(), 0) + '%':>8}"
            print(linha)
    print("\n  Leia assim: um stop a X pontos alem da linha e' atropelado por ruido de borda")
    print("  nessa fracao das visitas -- SEM que o retangulo tenha quebrado de verdade.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
