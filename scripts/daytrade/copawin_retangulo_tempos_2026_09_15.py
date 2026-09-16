# -*- coding: utf-8 -*-
"""WIN@ retangulo: os TRES TEMPOS que decidem se da' para operar nele.

Pedido do dono (2026-09-15), depois de o detector de retangulo ficar pronto:

  1. Com quantas barras/minutos conseguimos IDENTIFICAR a lateralizacao?
  2. Quantas barras/minutos ela DURA?
  3. Em quantas barras conseguimos descobrir onde fica o MEIO dela?

As tres sao a mesma conta vista de tres angulos, e e' a conta que decide tudo:
se a identificacao consome quase toda a duracao, nao sobra retangulo para
operar; e se o MEIO so' fica conhecido perto do fim, um fade que mira o meio
nao tem alvo confiavel no momento em que precisaria dele.

## De onde vem a amostra

`scripts/daytrade/copawin_retangulo_lateral_2026_09_15.py` ja detectou os
retangulos e gravou `scratch/copawin_retangulos.csv`. Este script NAO
redetecta: ele pega cada retangulo confirmado e mede os tres tempos em cima
das barras do proprio pregao.

## 1) INICIO REAL e LATENCIA DE IDENTIFICACAO

O detector confirma na barra `t` olhando as W barras anteriores -- entao dizer
"a latencia e' W" seria circular. O inicio REAL e' achado andando para TRAS a
partir da confirmacao, com a banda ja conhecida: recua enquanto o preco nao
tiver 3 fechamentos SEGUIDOS fora de [piso - 25%L, topo + 25%L]. E' o espelho
exato do criterio de MORTE usado na deteccao, para os dois lados da vida do
retangulo terem a mesma regua.

    latencia = confirmacao - inicio_real

Isto e' retrospectivo de proposito: mede ha' quanto tempo a estrutura existia
quando finalmente deu para nomea-la. E' a pergunta do dono, e a resposta e'
uma PERDA -- o pedaco do retangulo que nao da' para usar.

## 2) DURACAO TOTAL

    duracao_total = latencia + vida_depois_da_confirmacao

A `vida_depois` vem do CSV, ja medida pelo criterio TOLERANTE (3 fechamentos
alem de 25% da largura), que e' o que corresponde ao "fura a linha e volta"
das imagens do dono. A fracao APROVEITAVEL do retangulo e'
`vida_depois / duracao_total`.

## 3) QUANDO O MEIO FICA CONHECIDO

A cada barra k a partir do inicio real, estima-se o meio com o que se sabe ate
ali: `meio_k = (q90 dos high + q10 dos low)` / 2 sobre as barras [inicio, k].
Compara-se com `meio_ref`, o meio calculado sobre o retangulo INTEIRO (inicio
ate a morte). O tempo de convergencia e' o menor k tal que
`|meio_k - meio_ref| <= tol * largura` E o desvio nunca mais volta a passar
disso. Duas tolerancias: 10% e 20% da largura.

RESSALVA QUE NAO PODE SUMIR: `meio_ref` e' retrospectivo. Esta medicao diz em
quantas barras a estimativa CONVERGE para a verdade -- nao diz que ao vivo se
saberia que ja convergiu. E' um LIMITE SUPERIOR do que e' descobrivel: ao
vivo, a confirmacao de que o meio parou de andar so' vem depois. Se nem esse
limite superior for confortavel, o caso ao vivo e' pior.

## O que NAO esta aqui

Nenhum resultado financeiro. Isto e' medicao de geometria temporal; o teste de
fade mirando o meio (a unica perna ainda viva desta linha) so' faz sentido
depois destes numeros.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_tempos_2026_09_15.py`
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
    "_base_tmp", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

SCRATCH = ROOT / "scratch"
CSV = SCRATCH / "copawin_retangulos.csv"
CORTE_OOS = pd.Timestamp("2026-06-13").date()

#: espelho do criterio de morte: 3 fechamentos seguidos alem de 25% da largura
MARGEM_VIDA = 0.25
BARRAS_FORA = 3
#: tolerancias para dizer que o meio "ja e' conhecido", em fracao da largura
TOLS_MEIO = (0.10, 0.20)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _inicio_real(close, i_conf, topo, piso, L):
    """Anda para TRAS a partir da confirmacao enquanto a estrutura se sustenta."""
    fora_cima, fora_baixo = topo + MARGEM_VIDA * L, piso - MARGEM_VIDA * L
    seguidas = 0
    i = i_conf
    while i > 0:
        j = i - 1
        if close[j] > fora_cima or close[j] < fora_baixo:
            seguidas += 1
            if seguidas >= BARRAS_FORA:
                return i - 1 + BARRAS_FORA   # a 1a das 3 barras fora ja nao conta
        else:
            seguidas = 0
        i = j
    return 0


def _convergencia_meio(high, low, ini, fim, L):
    """Menor k (barras desde o inicio) a partir do qual a estimativa do meio
    fica -- e permanece -- dentro da tolerancia em torno do meio verdadeiro."""
    h, lo = high[ini:fim + 1], low[ini:fim + 1]
    n = len(h)
    if n < 6 or L <= 0:
        return {t: float("nan") for t in TOLS_MEIO}
    meio_ref = (float(np.quantile(h, 0.90)) + float(np.quantile(lo, 0.10))) / 2.0
    desvios = np.full(n, np.nan)
    for k in range(5, n):
        m = (float(np.quantile(h[:k + 1], 0.90)) + float(np.quantile(lo[:k + 1], 0.10))) / 2.0
        desvios[k] = abs(m - meio_ref) / L
    out = {}
    for tol in TOLS_MEIO:
        ok = np.where(~np.isnan(desvios), desvios <= tol, False)
        # menor k a partir do qual NUNCA mais sai da tolerancia
        k_conv = float("nan")
        for k in range(5, n):
            if ok[k] and bool(np.all(ok[k:n])):
                k_conv = k
                break
        out[tol] = k_conv
    return out


def roda_dia(args):
    dia, linhas = args
    df, _ = _base._df()
    b = df[df.index.date == pd.Timestamp(dia).date()]
    if b.empty:
        return []
    idx = b.index
    high = b["high"].to_numpy(float)
    low = b["low"].to_numpy(float)
    close = b["close"].to_numpy(float)
    mapa = {ts: i for i, ts in enumerate(idx)}
    out = []
    for r in linhas:
        i_conf = mapa.get(pd.Timestamp(r["confirmou_utc"]))
        if i_conf is None:
            continue
        topo, piso = r["topo"], r["piso"]
        L = r["largura_pontos"]
        ini = _inicio_real(close, i_conf, topo, piso, L)
        fim = min(len(close) - 1, i_conf + int(r["tol_barras_depois"]))
        conv = _convergencia_meio(high, low, ini, fim, L)
        lat_barras = i_conf - ini
        out.append(dict(
            data=dia, janela_barras=r["janela_barras"],
            latencia_barras=lat_barras,
            latencia_min=(idx[i_conf] - idx[ini]).total_seconds() / 60.0,
            vida_depois_min=r["tol_vida_min"],
            duracao_total_min=(idx[fim] - idx[ini]).total_seconds() / 60.0,
            duracao_total_barras=fim - ini,
            **{f"conv_{int(t*100)}_barras": conv[t] for t in TOLS_MEIO},
        ))
    return out


def main():
    if not CSV.exists():
        sys.exit(f"faltando {CSV} -- rode antes copawin_retangulo_lateral_2026_09_15.py")
    r = pd.read_csv(CSV, parse_dates=["confirmou_utc", "inicio_utc"])
    print("=" * 112)
    print("WIN@ retangulo -- OS TRES TEMPOS: identificar, durar, e achar o meio")
    print("=" * 112)
    print(f"{len(r)} retangulos de scratch/copawin_retangulos.csv")
    print("inicio REAL achado andando para tras com a banda ja conhecida (espelho do")
    print(f"criterio de morte: {BARRAS_FORA} fechamentos seguidos alem de {int(MARGEM_VIDA*100)}% da largura).\n",
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

    t = pd.DataFrame(linhas)
    t["janela"] = np.where(pd.to_datetime(t["data"]).dt.date < CORTE_OOS, "IS", "OOS")
    t["frac_aproveitavel"] = t["vida_depois_min"] / t["duracao_total_min"].replace(0, np.nan)
    t.to_csv(SCRATCH / "copawin_retangulo_tempos.csv", index=False, encoding="utf-8")
    print(f"\n{len(t)} retangulos medidos -> scratch/copawin_retangulo_tempos.csv\n")

    print("=" * 112)
    print("1) QUANTO TEMPO ATE IDENTIFICAR  (do inicio real ate a confirmacao)")
    print("=" * 112)
    hdr = (f"  {'W':<6}{'jan':<5}{'n':>6}{'lat. mediana (min)':>20}{'p25':>7}{'p75':>7}"
           f"{'media':>9}{'em barras (med)':>17}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in sorted(t.janela_barras.unique()):
        for jan in ("IS", "OOS"):
            s = t[(t.janela_barras == W) & (t.janela == jan)]
            if s.empty:
                continue
            print(f"  {W:<6}{jan:<5}{len(s):>6}{br(s.latencia_min.median(), 1):>20}"
                  f"{br(s.latencia_min.quantile(.25), 0):>7}{br(s.latencia_min.quantile(.75), 0):>7}"
                  f"{br(s.latencia_min.mean(), 1):>9}{br(s.latencia_barras.median(), 0):>17}")

    print("\n" + "=" * 112)
    print("2) QUANTO DURA, E QUANTO SOBRA DEPOIS DE IDENTIFICADO")
    print("=" * 112)
    hdr = (f"  {'W':<6}{'jan':<5}{'n':>6}{'duracao total (med)':>21}{'p75':>7}"
           f"{'vida depois (med)':>19}{'% aproveitavel (med)':>22}{'% casos com >=50%':>19}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in sorted(t.janela_barras.unique()):
        for jan in ("IS", "OOS"):
            s = t[(t.janela_barras == W) & (t.janela == jan)]
            if s.empty:
                continue
            print(f"  {W:<6}{jan:<5}{len(s):>6}{br(s.duracao_total_min.median(), 1):>21}"
                  f"{br(s.duracao_total_min.quantile(.75), 0):>7}"
                  f"{br(s.vida_depois_min.median(), 1):>19}"
                  f"{br(100 * s.frac_aproveitavel.median(), 0) + '%':>22}"
                  f"{br(100 * (s.frac_aproveitavel >= 0.5).mean(), 0) + '%':>19}")

    print("\n" + "=" * 112)
    print("3) EM QUANTAS BARRAS O MEIO FICA CONHECIDO")
    print("   (menor k desde o inicio a partir do qual a estimativa do meio fica -- e")
    print("    permanece -- dentro da tolerancia em torno do meio verdadeiro)")
    print("=" * 112)
    hdr = (f"  {'W':<6}{'jan':<5}{'n':>6}"
           + "".join(f"{f'conv {int(x*100)}% (med)':>18}{'p75':>7}" for x in TOLS_MEIO)
           + f"{'conv10 / duracao':>19}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in sorted(t.janela_barras.unique()):
        for jan in ("IS", "OOS"):
            s = t[(t.janela_barras == W) & (t.janela == jan)]
            if s.empty:
                continue
            linha = f"  {W:<6}{jan:<5}{len(s):>6}"
            for x in TOLS_MEIO:
                c = s[f"conv_{int(x*100)}_barras"].dropna()
                linha += f"{br(c.median(), 1):>18}{br(c.quantile(.75), 0):>7}"
            c10 = s["conv_10_barras"]
            razao = (c10 / s["duracao_total_barras"].replace(0, np.nan)).dropna()
            linha += f"{br(100 * razao.median(), 0) + '%':>19}"
            print(linha)

    print("\n" + "=" * 112)
    print("4) A CONTA QUE INTERESSA -- o meio ja e' conhecido quando o retangulo e' confirmado?")
    print("=" * 112)
    hdr = (f"  {'W':<6}{'jan':<5}{'n':>6}{'meio conv. ANTES da confirmacao':>34}"
           f"{'barras uteis depois (med)':>27}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for W in sorted(t.janela_barras.unique()):
        for jan in ("IS", "OOS"):
            s = t[(t.janela_barras == W) & (t.janela == jan)].dropna(subset=["conv_10_barras"])
            if s.empty:
                continue
            antes = (s["conv_10_barras"] <= s["latencia_barras"])
            uteis = (s["duracao_total_barras"] - np.maximum(s["conv_10_barras"],
                                                            s["latencia_barras"]))
            print(f"  {W:<6}{jan:<5}{len(s):>6}{br(100 * antes.mean(), 0) + '%':>34}"
                  f"{br(uteis.median(), 0):>27}")

    print("\n  'barras uteis depois' = o que sobra do retangulo DEPOIS de ele estar confirmado")
    print("  E o meio ja conhecido -- e' a janela real em que um fade mirando o meio poderia")
    print("  existir. Se for pequena, a ideia morre por geometria temporal, nao por edge.")
    print("\nRESSALVA: o meio de referencia e' retrospectivo, entao a convergencia medida e' um")
    print("LIMITE SUPERIOR do que se sabe ao vivo -- na pratica so' se descobre que o meio parou")
    print("de andar algum tempo depois de ele ter parado.\n\nFIM.")


if __name__ == "__main__":
    main()
