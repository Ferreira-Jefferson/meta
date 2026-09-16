# -*- coding: utf-8 -*-
"""ROMPIMENTO de retângulo: o fenômeno existe? -- medição, ainda não estratégia.

Pedido do dono (2026-09-16): "da mesma maneira que criamos toda uma sequência de
questionamento e conclusões que levaram a entender a lateralização e chegar em
uma estratégia com ótimos resultados, vamos criar uma estratégia de rompimento
de lateralização".

Primeira rodada da linha, e ela é de REFUTAÇÃO: mede o fenômeno cru, no IS
apenas, sem desenhar geometria. Base inteira só para o que sobreviver.

## A restrição que define a forma da estratégia, e vem ANTES de qualquer número

Desenho de execução FECHADO: entrada só por `EnterLimit` com prazo. Uma limite
de COMPRA só descansa ABAIXO do preço, uma de VENDA só ACIMA. Romper é o preço
indo EMBORA do nível -- perseguir com ordem-limite é contradição de mecanismo,
não escolha de parâmetro.

Logo a única forma executável é **romper e VOLTAR** (reteste), com a limite
esperando no nível rompido. Sem reteste não existe operação, por melhor que
seja o rompimento. Por isso a taxa de reteste é pergunta de primeira ordem.

## Os dois precedentes CONTRA, declarados

1. `copawin_rompimento_wdo_refutado_2026_08_31`: rompimento já refutado nesta
   linha -- o melhor combo do IS cai no OOS.
2. `wdo_orb_cortar_fade_refutado_2026_09_14`: no robô de rompimento em
   produção, a perna FORTE é o fade; o rompimento é a perna quebrada.

O que diferencia: aqui o rompimento é CONDICIONADO a um retângulo validado
pelo detector. Se o condicionamento não mudar nada, a linha morre aqui.

## DOIS VÍCIOS DE MÉTODO CORRIGIDOS NESTA VERSÃO -- leia antes dos números

**1. Ponto de referência (Q2).** O rompimento só é DETECTADO 3 barras depois de
o fechamento passar da borda + 25% da largura. No instante da detecção o preço
já está tipicamente ~109 pontos além da borda (25% de uma largura mediana de
435). Medir MFE/MAE a partir da BORDA dá ao rompimento uma vantagem de largada
que o nulo -- medido a partir do fechamento -- não tem, e infla a razão
MFE/MAE. A primeira passada desta rodada devolvia 4,11 contra 1,09 por causa
disso. Q2 agora mede a partir do **preço no instante da detecção**, que é o
único ponto comparável com o nulo.

**2. Ordem de chegada (Q4).** "Anda X a favor antes de X contra" estava escrito
como `MFE >= X e MAE < X`, que não é ordem nenhuma -- é exigir excursão adversa
minúscula, e com MAE mediana de 465 quase nada passa. Q4 agora percorre a
série e compara o ÍNDICE do primeiro toque favorável com o do primeiro toque
adverso, que é a pergunta de verdade.

## As quatro perguntas, em ordem de custo de refutação

Q1. Quantos retângulos ROMPEM, para que lado, depois de quanto tempo?
Q2. Depois de romper, o preço CONTINUA? MFE/MAE a partir do preço de detecção,
    contra o NULO (mesma medição em instantes sorteados do mesmo pregão).
Q3. O preço VOLTA à borda rompida? Sem reteste não há entrada possível.
Q4. Depois do reteste, quem chega primeiro: o alvo ou o stop? É o que a
    estratégia capturaria, e tem de pagar os 7,5 pontos de ida-e-volta.

## Definições, herdadas do robô de produção

Retângulo: `detecta_retangulo` do `win_retangulo` (função pura), W=20,
tolerância 0,20, largura mínima 328. Rompimento: a MESMA regra de morte que o
robô já usa -- fechamento além da borda + `MARGEM_MORTE` (25%) por
`BARRAS_MORTE` (3) barras. Não é critério novo: é o evento que o robô de fade
já calcula e descarta.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/rompimento_retangulo_fenomeno_2026_09_16.py`
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_retangulo import (  # noqa: E402
    BARRAS_MORTE, MARGEM_MORTE, detecta_retangulo)

SIMBOLO = "WIN@"
JANELA = 20
TOLERANCIA = 0.20
LARGURA_MINIMA = 328.0
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
PEDAGIO_PONTOS = 7.5
HORIZONTE = 60
LIMIARES = (20, 40, 60, 100, 150)
SEMENTE = 20260916


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x):
    return "—" if x != x else br(100 * x, 1) + "%"


def rompimentos_do_pregao(g: pd.DataFrame) -> list[dict]:
    """Todo rompimento de retângulo validado NAQUELE pregão."""
    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)
    c = g["close"].to_numpy(float)
    n = len(g)
    achados: list[dict] = []
    ret = None
    fora = 0
    nascimento = 0
    i = 3 * JANELA
    while i < n:
        if ret is None:
            anterior = float(h[i - 3 * JANELA:i - JANELA].max()
                             - l[i - 3 * JANELA:i - JANELA].min())
            r = detecta_retangulo(h[i - JANELA:i], l[i - JANELA:i], c[i - JANELA:i],
                                  anterior, tolerancia=TOLERANCIA)
            if r is not None and r["largura"] >= LARGURA_MINIMA:
                ret, fora, nascimento = r, 0, i
            i += 1
            continue
        margem = MARGEM_MORTE * ret["largura"]
        acima = c[i] > ret["topo"] + margem
        abaixo = c[i] < ret["piso"] - margem
        if acima or abaixo:
            fora += 1
            if fora >= BARRAS_MORTE:
                achados.append(dict(
                    idx=i, lado="alta" if acima else "baixa",
                    borda=float(ret["topo"] if acima else ret["piso"]),
                    largura=float(ret["largura"]),
                    barras_vivo=i - nascimento,
                    preco_deteccao=float(c[i]),
                ))
                ret, fora = None, 0
        else:
            fora = 0
        i += 1
    return achados


def excursao(g, idx: int, lado: str, referencia: float, horizonte: int = HORIZONTE) -> dict:
    """MFE/MAE a partir de `referencia`, na direção do rompimento."""
    fim = min(idx + 1 + horizonte, len(g))
    if fim <= idx + 1:
        return dict(mfe=np.nan, mae=np.nan, voltou=np.nan, barras_ate_voltar=np.nan)
    h = g["high"].to_numpy(float)[idx + 1:fim]
    l = g["low"].to_numpy(float)[idx + 1:fim]
    if lado == "alta":
        mfe, mae = float(h.max() - referencia), float(referencia - l.min())
        tocou = np.where(l <= referencia)[0]
    else:
        mfe, mae = float(referencia - l.min()), float(h.max() - referencia)
        tocou = np.where(h >= referencia)[0]
    voltou = len(tocou) > 0
    return dict(mfe=mfe, mae=mae, voltou=voltou,
                barras_ate_voltar=float(tocou[0] + 1) if voltou else np.nan)


def quem_chega_primeiro(g, idx: int, lado: str, referencia: float,
                        limiar: float, horizonte: int = HORIZONTE):
    """`True` se `+limiar` é tocado ANTES de `-limiar`; `False` se o contrário;
    `None` se nenhum dos dois acontece no horizonte.

    É a pergunta que `MFE >= X and MAE < X` NÃO responde: aquilo exige excursão
    adversa pequena, esta compara ORDEM DE CHEGADA."""
    fim = min(idx + 1 + horizonte, len(g))
    if fim <= idx + 1:
        return None
    h = g["high"].to_numpy(float)[idx + 1:fim]
    l = g["low"].to_numpy(float)[idx + 1:fim]
    if lado == "alta":
        favor = np.where(h >= referencia + limiar)[0]
        contra = np.where(l <= referencia - limiar)[0]
    else:
        favor = np.where(l <= referencia - limiar)[0]
        contra = np.where(h >= referencia + limiar)[0]
    if not len(favor) and not len(contra):
        return None
    if not len(contra):
        return True
    if not len(favor):
        return False
    return bool(favor[0] < contra[0])


def main():
    df = load_m1(SIMBOLO).sort_index()
    cont = df.groupby(df.index.date).size()
    dias = sorted(d for d, n in cont.items()
                  if n >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    print("=" * 140)
    print("ROMPIMENTO DE RETÂNGULO — o fenômeno existe? (IS apenas, ainda não é estratégia)")
    print("=" * 140)
    print(f"  {SIMBOLO} M1 | {len(dias)} pregões | {dias[0]} a {dias[-1]}")
    print(f"  retângulo W={JANELA}, tolerância {TOLERANCIA}, largura mínima "
          f"{br(LARGURA_MINIMA,0)} | rompimento = a regra de MORTE do robô de fade")
    print(f"  horizonte {HORIZONTE} barras | pedágio ida-e-volta {br(PEDAGIO_PONTOS,1)} pontos")
    print("  *** dois vícios de método da 1a passada corrigidos aqui — ver a docstring ***\n",
          flush=True)

    eventos: list[dict] = []
    nulos: list[dict] = []
    rng = random.Random(SEMENTE)
    por_dia: dict = {}
    for d in dias:
        g = df[df.index.date == d]
        if len(g) < 3 * JANELA + 5:
            continue
        rs = rompimentos_do_pregao(g)
        por_dia[d] = (g, rs)
        for r in rs:
            # Q2 mede do PREÇO DE DETECÇÃO (comparável com o nulo);
            # o reteste (Q3) mede a volta à BORDA, que é onde a limite ficaria.
            e_det = excursao(g, r["idx"], r["lado"], r["preco_deteccao"])
            e_borda = excursao(g, r["idx"], r["lado"], r["borda"])
            eventos.append({**r, "dia": d,
                            "mfe": e_det["mfe"], "mae": e_det["mae"],
                            "voltou": e_borda["voltou"],
                            "barras_ate_voltar": e_borda["barras_ate_voltar"]})
            j = rng.randrange(3 * JANELA, len(g) - 1)
            ref = float(g["close"].to_numpy(float)[j])
            nulos.append({**excursao(g, j, r["lado"], ref), "idx": j,
                          "lado": r["lado"], "ref": ref, "dia": d})

    n = len(eventos)
    print("=" * 140)
    print("Q1 — QUANTOS ROMPEM, PARA QUE LADO, DEPOIS DE QUANTO TEMPO")
    print("=" * 140)
    alta = sum(1 for e in eventos if e["lado"] == "alta")
    vivos = [e["barras_vivo"] for e in eventos]
    larg = [e["largura"] for e in eventos]
    print(f"  rompimentos: {n}   ({br(n/len(dias),1)} por pregão)")
    print(f"  ALTA {alta} ({_pct(alta/n)})  |  BAIXA {n-alta} ({_pct((n-alta)/n)})")
    print(f"  barras vivo antes de romper: mediana {br(float(np.median(vivos)),0)} "
          f"(p25 {br(float(np.percentile(vivos,25)),0)}, p75 {br(float(np.percentile(vivos,75)),0)})")
    print(f"  largura rompida: mediana {br(float(np.median(larg)),0)} pontos "
          f"(p25 {br(float(np.percentile(larg,25)),0)}, p75 {br(float(np.percentile(larg,75)),0)})")
    afast = [e["preco_deteccao"] - e["borda"] if e["lado"] == "alta"
             else e["borda"] - e["preco_deteccao"] for e in eventos]
    print(f"  JÁ ANDOU da borda até a detecção: mediana {br(float(np.median(afast)),0)} pontos "
          f"— é o degrau que viciava a 1a passada")

    print("\n" + "=" * 140)
    print("Q2 — DEPOIS DE ROMPER, CONTINUA? (do PREÇO DE DETECÇÃO, contra o nulo)")
    print("=" * 140)

    def resumo(lst, rot):
        mfe = np.array([x["mfe"] for x in lst], float)
        mae = np.array([x["mae"] for x in lst], float)
        ok = ~np.isnan(mfe)
        mfe, mae = mfe[ok], mae[ok]
        print(f"  {rot:<24} n={len(mfe):>4}  MFE med {br(float(np.median(mfe)),1):>7}  "
              f"MAE med {br(float(np.median(mae)),1):>7}  "
              f"MFE>MAE {_pct(float((mfe > mae).mean())):>7}  "
              f"razão {br(float(np.median(mfe))/max(float(np.median(mae)),1e-9),2)}")
        return mfe, mae

    resumo(eventos, "rompimento")
    resumo(nulos, "NULO (instante sorteado)")

    print("\n  quem chega primeiro, do preço de detecção:")
    print(f"    {'limiar':<10}{'rompimento':>14}{'NULO':>14}{'diferença':>13}")
    for t in LIMIARES:
        r_ev = [quem_chega_primeiro(por_dia[e['dia']][0], e["idx"], e["lado"],
                                    e["preco_deteccao"], t) for e in eventos]
        r_nu = [quem_chega_primeiro(por_dia[x['dia']][0], x["idx"], x["lado"],
                                    x["ref"], t) for x in nulos]
        a = [z for z in r_ev if z is not None]
        b = [z for z in r_nu if z is not None]
        pa = float(np.mean(a)) if a else float("nan")
        pb = float(np.mean(b)) if b else float("nan")
        print(f"    {str(t)+' pts':<10}{_pct(pa):>14}{_pct(pb):>14}"
              f"{br(100*(pa-pb),1)+' pp':>13}")

    print("\n" + "=" * 140)
    print("Q3 — O PREÇO VOLTA À BORDA? (sem reteste NÃO EXISTE entrada por ordem-limite)")
    print("=" * 140)
    voltou = np.array([1.0 if x["voltou"] is True else 0.0
                       for x in eventos if x["voltou"] == x["voltou"]])
    barras = np.array([x["barras_ate_voltar"] for x in eventos
                       if x["barras_ate_voltar"] == x["barras_ate_voltar"]])
    print(f"  retesta a borda em até {HORIZONTE} barras: {_pct(float(voltou.mean()))} "
          f"({int(voltou.sum())} de {len(voltou)})")
    if len(barras):
        print(f"  barras até o reteste: mediana {br(float(np.median(barras)),0)} "
              f"(p25 {br(float(np.percentile(barras,25)),0)}, "
              f"p75 {br(float(np.percentile(barras,75)),0)})")
    for prazo in (5, 10, 20, 30):
        frac = float(np.mean(barras <= prazo)) * float(voltou.mean()) if len(barras) else 0.0
        print(f"    retesta em até {prazo:>2} barras: {_pct(frac)} de TODOS os rompimentos")

    print("\n" + "=" * 140)
    print("Q4 — DEPOIS DO RETESTE, QUEM CHEGA PRIMEIRO? (ordem de chegada, da BORDA)")
    print("=" * 140)
    entradas = []
    for e in eventos:
        if e["barras_ate_voltar"] != e["barras_ate_voltar"]:
            continue
        g = por_dia[e["dia"]][0]
        j = int(e["idx"] + e["barras_ate_voltar"])
        if j >= len(g) - 2:
            continue
        entradas.append((g, j, e))
    print(f"  n={len(entradas)} retestes com continuação observável "
          f"(de {n} rompimentos)")
    print(f"\n    {'limiar':<12}{'a favor 1o':>13}{'contra 1o':>12}{'nenhum':>10}"
          f"{'% decididos a favor':>22}")
    for t in LIMIARES:
        res = [quem_chega_primeiro(g, j, e["lado"], e["borda"], t)
               for g, j, e in entradas]
        fav = sum(1 for z in res if z is True)
        con = sum(1 for z in res if z is False)
        nen = sum(1 for z in res if z is None)
        dec = fav + con
        print(f"    {str(t)+' pts':<12}{fav:>13}{con:>12}{nen:>10}"
              f"{(_pct(fav/dec) if dec else '—'):>22}")
    print("\n  O nulo desta tabela é 50%: alvo e stop simétricos, sem custo. Abaixo de 50%")
    print("  o reteste é pior que cara-ou-coroa; em 50% ele empata e o pedágio decide.")

    print("\n" + "=" * 140)
    print("COMO LER")
    print("=" * 140)
    print("  * NÃO é estratégia: não há entrada, alvo, stop nem custo. É a pergunta anterior.")
    print("  * Q3 é eliminatória por MECANISMO: sem reteste, o desenho de execução fechado")
    print("    (entrada só por ordem-limite) não tem como entrar.")
    print("  * Q4 é eliminatória por ECONOMIA: com alvo e stop simétricos o nulo é 50%, e")
    print("    ainda é preciso pagar 7,5 pontos de ida-e-volta.")
    print("  * Só o IS. A janela cega fica intacta para o que sobreviver.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
