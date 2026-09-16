# -*- coding: utf-8 -*-
"""ANATOMIA do que acontece DEPOIS do rompimento de retângulo -- taxonomia
exaustiva, tempo e magnitude de cada ramo. Só o IS (janela cega intacta).

Pergunta do dono, textual (2026-09-16): "após romper o preço volta? após
voltar ele entra no retângulo ou retorna ao sentido do rompimento?"

Este script é a continuação de `rompimento_retangulo_fenomeno_2026_09_16.py`
(mesmo dia, outro território): aquele mediu SE o preço retesta a borda
(69,3%, mediana 7 barras) e quem chega primeiro depois do reteste. Este mede
o que o reteste **significa**: tocar a borda não é a mesma coisa que fechar
dentro do retângulo, e as duas coisas têm consequência diferente. Reusa a
mesma base (WIN@ M1, IS < 2026-06-13, 129 pregões) e o MESMO detector de
produção (`detecta_retangulo`) e a MESMA regra de morte
(`MARGEM_MORTE`/`BARRAS_MORTE`) -- não redefine nada nesses dois pontos.

## A distinção que o dono pediu, e como ela vira número

`rompimento_retangulo_fenomeno` define "reteste" como TOQUE: `low <= borda`
(lado alta) -- é o critério mais fraco possível, um pavio já conta. Isso
resolve "a limite de reteste teria preenchido?" (Q3 daquele script), mas não
resolve "voltar" no sentido que o dono perguntou: um pavio que toca a borda e
sai de novo, sem nunca fechar dentro, não é o preço "voltando para o
retângulo" -- é o preço testando a borda e retomando o rompimento.

Este script separa os dois com uma segunda régua, mais forte: ENTRAR exige
FECHAMENTO do lado de dentro da borda (`close < borda`, alta). Toda barra que
fecha dentro também tocou (o toque é necessário, nunca o contrário), então a
taxonomia abaixo é uma SUBDIVISÃO do "retesta" já medido, não uma medição
concorrente -- e a soma dos ramos (b)+(c) deste script tem de bater com os
69,3% do script anterior. É a primeira conferência do relatório.

## A árvore (exaustiva, mutuamente exclusiva)

    (a) NUNCA RETESTA           -- nunca toca a borda de novo
    (b) RETESTA MAS NÃO ENTRA   -- toca (pavio), fecha sempre do lado de fora
        (b1) RETOMA             -- confirma o rompimento de novo (mesma regra
                                    de morte do robô: 3 fechamentos além da
                                    borda + 25% da largura)
        (b2) INDEFINIDO         -- nem retoma nem entra até o fim do pregão
    (c) ENTRA NO RETÂNGULO      -- fecha do lado de dentro da borda
        (c1) SAI PELO MESMO LADO       -- reconfirma a MESMA regra de morte,
                                           agora depois de ter entrado (é o
                                           "falso reteste" / round-trip)
        (c2) ATRAVESSA ATÉ A OPOSTA    -- confirma a regra de morte na BORDA
                                           OPOSTA (segundo rompimento, lado
                                           contrário)
        (c3) ATRAVESSA O MEIO, SEM CHEGAR NA OPOSTA -- fechou além do meio,
                                           pregão acaba antes de decidir
        (c4) FICA RASO                  -- entra mas nunca fecha além do meio

O critério de (b1)/(c1)/(c2) é literalmente o mesmo `_morreu` do robô em
produção (`MARGEM_MORTE=0,25` da largura, `BARRAS_MORTE=3` fechamentos
consecutivos) aplicado à mesma geometria -- por isso "romper de novo" tem a
MESMA definição do primeiro rompimento, nos dois lados do retângulo.

## O NULO -- mesma pergunta, instante sorteado

Para cada rompimento real sorteia-se um instante do MESMO pregão, herda-se a
LARGURA do evento pareado (não dá para sortear "largura do retângulo" de um
ponto que não tem retângulo), e projeta-se meio/oposta na direção interior a
partir do preço do instante sorteado -- exatamente a mesma forma que
`rompimento_retangulo_fenomeno` já usa (referência = preço do instante, não
um nível 263 pontos atrás). A MESMA função de classificação corre nos dois.

## Duas armadilhas de método já conhecidas desta linha, evitadas aqui

1. Medir excursão a partir da BORDA em vez do ponto de decisão -- aqui cada
   medida (barras, profundidade) conta a partir do índice em que a decisão
   estaria disponível (o próprio instante de reteste/entrada), nunca da
   borda "de graça".
2. "Anda X a favor antes de X contra" não é MFE/MAE -- aqui não se usa essa
   forma; o que decide qual ramo um evento pertence é ORDEM DE CHEGADA das
   regras de saída (mesma regra de morte, aplicada aos dois lados), andando
   barra a barra, nunca um par de limiares estáticos comparados fora de ordem.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/rompimento_anatomia_pos_retorno_2026_09_16.py`
"""
from __future__ import annotations

import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.stdout.reconfigure(encoding="utf-8")

SIMBOLO = "WIN@"
JANELA = 20
TOLERANCIA = 0.20
LARGURA_MINIMA = 328.0
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
PONTO_VALOR_BRL = 0.20
PEDAGIO_PONTOS = 7.5
SEMENTE = 20260916


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x):
    return "—" if x is None or x != x else br(100 * x, 1) + "%"


# ---------------------------------------------------------------------------
# Detecção de rompimentos (glue em cima do detector de PRODUÇÃO -- não
# reimplementa `detecta_retangulo`; só adiciona meio/oposta ao achado, que o
# script-irmão não guardava porque não precisava).
# ---------------------------------------------------------------------------
def _rompimentos_com_geometria(g: pd.DataFrame, detecta_retangulo, MARGEM_MORTE, BARRAS_MORTE) -> list[dict]:
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
                lado = "alta" if acima else "baixa"
                borda = float(ret["topo"] if acima else ret["piso"])
                oposta = float(ret["piso"] if acima else ret["topo"])
                achados.append(dict(
                    idx=i, lado=lado, borda=borda, oposta=oposta,
                    meio=float(ret["meio"]), largura=float(ret["largura"]),
                    barras_vivo=i - nascimento,
                    preco_deteccao=float(c[i]),
                    afastamento=float(abs(c[i] - borda)),
                ))
                ret, fora = None, 0
        else:
            fora = 0
        i += 1
    return achados


# ---------------------------------------------------------------------------
# Classificação -- a mesma função para EVENTO REAL e para NULO.
# ---------------------------------------------------------------------------
def classifica(high, low, close, idx_ref, lado, borda, meio, oposta, largura,
                margem_morte, barras_morte):
    """Anda barra a barra depois de `idx_ref` e classifica o desfecho.

    ARMADILHA DE MÉTODO evitada aqui, e que a 1a versão deste script não
    evitou: os contadores de "reconfirmação de rompimento" (`fora_mesmo` /
    `fora_oposto`) SÓ COMEÇAM A CONTAR depois do primeiro reteste
    (`tocou_idx`). Sem essa trava, o contador herda de graça os fechamentos
    que já estavam além da margem NO INSTANTE DA DETECÇÃO (é assim que o
    rompimento foi confirmado) e a inércia normal de 1-3 barras pós-detecção
    reconfirma a MESMA regra quase sempre — o evento vira "retoma" ou "nunca
    retesta" por um artefato de contagem, não porque o preço de fato voltou e
    resumiu. A 1a passada media 76,5% em "nunca retesta" (deveria bater com
    os 69,3% de RETESTE, não com o oposto) exatamente por causa disto.
    """
    n = len(close)
    tocou_idx = None
    entrou_idx = None
    meio_idx = None
    terminal_lado = None
    terminal_idx = None
    fora_mesmo = 0
    fora_oposto = 0
    margem = margem_morte * largura
    prof_max = 0.0
    overshoot_oposta = 0.0

    for t in range(idx_ref + 1, n):
        c, h, l = close[t], high[t], low[t]
        if lado == "alta":
            if tocou_idx is None and l <= borda:
                tocou_idx = t
            if entrou_idx is None and c < borda:
                entrou_idx = t
            if meio_idx is None and c <= meio:
                meio_idx = t
            pen = borda - l
            if pen > prof_max:
                prof_max = pen
        else:
            if tocou_idx is None and h >= borda:
                tocou_idx = t
            if entrou_idx is None and c > borda:
                entrou_idx = t
            if meio_idx is None and c >= meio:
                meio_idx = t
            pen = h - borda
            if pen > prof_max:
                prof_max = pen

        # Reconfirmação (mesma regra de morte, nos dois lados) só é avaliada
        # DEPOIS do primeiro reteste -- antes disso é só a inércia do
        # rompimento original, não um evento novo.
        if tocou_idx is None:
            continue

        if lado == "alta":
            if c > borda + margem:
                fora_mesmo += 1
            else:
                fora_mesmo = 0
            if c < oposta - margem:
                fora_oposto += 1
                over = oposta - c
                if over > overshoot_oposta:
                    overshoot_oposta = over
            else:
                fora_oposto = 0
        else:
            if c < borda - margem:
                fora_mesmo += 1
            else:
                fora_mesmo = 0
            if c > oposta + margem:
                fora_oposto += 1
                over = c - oposta
                if over > overshoot_oposta:
                    overshoot_oposta = over
            else:
                fora_oposto = 0

        if fora_mesmo >= barras_morte:
            terminal_lado, terminal_idx = "mesmo", t - barras_morte + 1
            break
        if fora_oposto >= barras_morte:
            terminal_lado, terminal_idx = "oposto", t - barras_morte + 1
            break

    if tocou_idx is None:
        ramo = "a_nunca_retesta"
    elif entrou_idx is None:
        ramo = "b1_retoma" if terminal_lado == "mesmo" else "b2_indefinido_sem_entrar"
    else:
        if terminal_lado == "mesmo":
            ramo = "c1_sai_mesmo_lado"
        elif terminal_lado == "oposto":
            ramo = "c2_atravessa_ate_oposta"
        elif meio_idx is not None:
            ramo = "c3_atravessa_meio_sem_oposta"
        else:
            ramo = "c4_fica_raso"

    return dict(
        ramo=ramo,
        barras_ate_tocar=(tocou_idx - idx_ref) if tocou_idx is not None else np.nan,
        barras_ate_entrar=(entrou_idx - idx_ref) if entrou_idx is not None else np.nan,
        barras_ate_meio=(meio_idx - idx_ref) if meio_idx is not None else np.nan,
        barras_ate_terminal=(terminal_idx - idx_ref) if terminal_idx is not None else np.nan,
        profundidade_max_pts=prof_max,
        profundidade_max_frac=(prof_max / largura) if largura > 0 else np.nan,
        overshoot_oposta_pts=overshoot_oposta,
        barras_restantes_sessao=n - 1 - idx_ref,
    )


def processa_dia(dia_iso: str, symbol: str) -> dict:
    """Unidade paralela: um pregão inteiro. Import local -- cada processo do
    `ProcessPoolExecutor` monta seu próprio `sys.path` (Windows usa spawn)."""
    import sys as _sys
    if str(SRC) not in _sys.path:
        _sys.path.insert(0, str(SRC))
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.lab.win_retangulo import (
        BARRAS_MORTE, MARGEM_MORTE, detecta_retangulo)

    dia = pd.Timestamp(dia_iso).date()
    df = load_m1(symbol).sort_index()
    g = df[df.index.date == dia]
    if len(g) < 3 * JANELA + 5:
        return dict(dia=dia_iso, eventos=[], nulos=[])

    achados = _rompimentos_com_geometria(g, detecta_retangulo, MARGEM_MORTE, BARRAS_MORTE)
    high = g["high"].to_numpy(float)
    low = g["low"].to_numpy(float)
    close = g["close"].to_numpy(float)
    # `hash(str)` é RANDOMIZADO por processo (PYTHONHASHSEED) -- usar aqui
    # tornaria o nulo irreprodutível entre execuções (medido: mudou de
    # rodada para rodada). O ordinal da data é estável.
    rng = random.Random(SEMENTE ^ dia.toordinal())

    eventos = []
    nulos = []
    for r in achados:
        cl = classifica(high, low, close, r["idx"], r["lado"], r["borda"],
                         r["meio"], r["oposta"], r["largura"],
                         MARGEM_MORTE, BARRAS_MORTE)
        eventos.append({**r, **cl, "dia": dia_iso})

        # nulo pareado: mesmo pregão, mesmo lado, largura HERDADA do evento
        # real, referência = preço do instante sorteado (nunca a borda real).
        if len(g) - 5 <= 3 * JANELA:
            continue
        j = rng.randrange(3 * JANELA, len(g) - 2)
        ref = float(close[j])
        largura = r["largura"]
        if r["lado"] == "alta":
            meio_n = ref - largura / 2.0
            oposta_n = ref - largura
        else:
            meio_n = ref + largura / 2.0
            oposta_n = ref + largura
        cln = classifica(high, low, close, j, r["lado"], ref, meio_n, oposta_n,
                          largura, MARGEM_MORTE, BARRAS_MORTE)
        nulos.append({**cln, "dia": dia_iso, "lado": r["lado"], "largura": largura,
                      "afastamento": r["afastamento"]})

    print(f"  [{dia_iso}] {len(achados):>2} rompimentos, {len(g):>4} barras", flush=True)
    return dict(dia=dia_iso, eventos=eventos, nulos=nulos)


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------
RAMOS_ORDEM = [
    "a_nunca_retesta",
    "b1_retoma",
    "b2_indefinido_sem_entrar",
    "c1_sai_mesmo_lado",
    "c2_atravessa_ate_oposta",
    "c3_atravessa_meio_sem_oposta",
    "c4_fica_raso",
]
RAMOS_ROTULO = {
    "a_nunca_retesta": "(a) nunca retesta a borda",
    "b1_retoma": "(b1) retesta, NÃO entra, RETOMA o rompimento",
    "b2_indefinido_sem_entrar": "(b2) retesta, NÃO entra, indefinido no pregão",
    "c1_sai_mesmo_lado": "(c1) ENTRA, sai de novo pelo MESMO lado",
    "c2_atravessa_ate_oposta": "(c2) ENTRA, atravessa até a borda OPOSTA",
    "c3_atravessa_meio_sem_oposta": "(c3) ENTRA, passa o meio, indefinido",
    "c4_fica_raso": "(c4) ENTRA, fica RASO (não chega no meio)",
}


def tabela_taxonomia(eventos: list[dict], titulo: str) -> None:
    n = len(eventos)
    print(f"\n  {titulo}  (n={n})")
    if n == 0:
        print("    -- amostra vazia --")
        return
    print(f"    {'ramo':<46}{'n':>6}{'%':>8}{'barras (mediana)':>18}"
          f"{'prof. máx pts (mediana)':>26}{'R$/contrato (mediana)':>24}")
    for ramo in RAMOS_ORDEM:
        sub = [e for e in eventos if e["ramo"] == ramo]
        if not sub:
            print(f"    {RAMOS_ROTULO[ramo]:<46}{0:>6}{pct(0.0):>8}")
            continue
        frac = len(sub) / n
        # tempo até o EVENTO QUE DEFINE o ramo
        if ramo == "a_nunca_retesta":
            barras = [e["barras_restantes_sessao"] for e in sub]
            rot_tempo = "(pregão restante)"
        elif ramo in ("b1_retoma", "c1_sai_mesmo_lado", "c2_atravessa_ate_oposta"):
            barras = [e["barras_ate_terminal"] for e in sub if e["barras_ate_terminal"] == e["barras_ate_terminal"]]
            rot_tempo = ""
        elif ramo == "b2_indefinido_sem_entrar":
            barras = [e["barras_ate_tocar"] for e in sub]
            rot_tempo = "(até tocar)"
        else:  # c3, c4
            barras = [e["barras_ate_entrar"] for e in sub]
            rot_tempo = "(até entrar)"
        med_barras = float(np.median(barras)) if barras else float("nan")
        prof = np.array([e["profundidade_max_pts"] for e in sub], float)
        med_prof = float(np.median(prof))
        med_rs = med_prof * PONTO_VALOR_BRL
        print(f"    {RAMOS_ROTULO[ramo]:<46}{len(sub):>6}{pct(frac):>8}"
              f"{(br(med_barras,0)+' '+rot_tempo if med_barras==med_barras else '—'):>18}"
              f"{br(med_prof,0):>26}{br(med_rs,2):>24}")
    print(f"    checagem: (b)+(c) = {sum(1 for e in eventos if e['ramo'] not in ('a_nunca_retesta',))} "
          f"de {n} = {pct(sum(1 for e in eventos if e['ramo'] != 'a_nunca_retesta')/n)} "
          f"-- tem de ser >= 69,3% (reteste do script-irmão, horizonte 60 barras); "
          f"aqui o horizonte é o PREGÃO INTEIRO, então mais eventos têm tempo de retestar")


def dispersao(vals, rotulo):
    v = np.array([x for x in vals if x == x], float)
    if len(v) == 0:
        print(f"    {rotulo}: n=0")
        return
    print(f"    {rotulo}: n={len(v)}  média {br(float(np.mean(v)),1)}  "
          f"mediana {br(float(np.median(v)),1)}  desvio {br(float(np.std(v)),1)}  "
          f"p25 {br(float(np.percentile(v,25)),1)}  p75 {br(float(np.percentile(v,75)),1)}")


def main():
    import sys as _sys
    if str(SRC) not in _sys.path:
        _sys.path.insert(0, str(SRC))
    from market_data_intraday.storage import load_m1

    df = load_m1(SIMBOLO).sort_index()
    cont = df.groupby(df.index.date).size()
    dias = sorted(d for d, k in cont.items() if k >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    print("=" * 140)
    print("ANATOMIA DO ROMPIMENTO -- o preço volta? entra ou retoma? até onde? (IS apenas)")
    print("=" * 140)
    print(f"  {SIMBOLO} M1 | {len(dias)} pregões | {dias[0]} a {dias[-1]}")
    print(f"  retângulo W={JANELA}, tolerância {TOLERANCIA}, largura mínima {br(LARGURA_MINIMA,0)}")
    print("  ramo definido pela MESMA regra de morte do robô (25% da largura, 3 fechamentos),")
    print("  aplicada aos DOIS lados do retângulo depois do reteste.\n", flush=True)

    eventos: list[dict] = []
    nulos: list[dict] = []
    with ProcessPoolExecutor() as ex:
        futs = {ex.submit(processa_dia, str(d), SIMBOLO): d for d in dias}
        for fut in as_completed(futs):
            res = fut.result()
            eventos.extend(res["eventos"])
            nulos.extend(res["nulos"])

    eventos.sort(key=lambda e: (e["dia"], e["idx"]))
    n = len(eventos)
    print(f"\n{'=' * 140}\ntotal: {n} rompimentos, {len(nulos)} nulos pareados\n{'=' * 140}")

    print("\n" + "=" * 140)
    print("(a)-(c) A ÁRVORE DE DESFECHOS -- REAL vs NULO")
    print("=" * 140)
    tabela_taxonomia(eventos, "REAL (todos os rompimentos)")
    tabela_taxonomia(nulos, "NULO (instante sorteado, largura herdada do evento pareado)")

    print("\n" + "=" * 140)
    print("RESPOSTA DIRETA: volta e RETOMA vs volta e ENTRA")
    print("=" * 140)
    retesta = [e for e in eventos if e["ramo"] != "a_nunca_retesta"]
    retoma = [e for e in retesta if e["ramo"] in ("b1_retoma", "b2_indefinido_sem_entrar")]
    entra = [e for e in retesta if e["ramo"].startswith("c")]
    nr = len(retesta)
    print(f"  de {nr} que retestam a borda ({pct(nr/n)} de {n}):")
    print(f"    NÃO entra (retoma o rompimento ou fica indefinido no toque): "
          f"{len(retoma)} ({pct(len(retoma)/nr) if nr else '—'})")
    print(f"    ENTRA no retângulo (fecha do lado de dentro):                "
          f"{len(entra)} ({pct(len(entra)/nr) if nr else '—'})")
    ret_confirmado = [e for e in retesta if e["ramo"] == "b1_retoma"]
    print(f"  entre os que NÃO entram, quantos CONFIRMAM retomada (3 fechamentos "
          f"além da borda de novo): {len(ret_confirmado)} ({pct(len(ret_confirmado)/len(retoma)) if retoma else '—'})")

    print("\n" + "=" * 140)
    print("(c) ATÉ ONDE VAI O RETORNO AO RETÂNGULO, DADO QUE ENTROU")
    print("=" * 140)
    for ramo in ("c1_sai_mesmo_lado", "c2_atravessa_ate_oposta", "c3_atravessa_meio_sem_oposta", "c4_fica_raso"):
        sub = [e for e in entra if e["ramo"] == ramo]
        print(f"\n  {RAMOS_ROTULO[ramo]}  n={len(sub)} ({pct(len(sub)/len(entra)) if entra else '—'} dos que entram)")
        if not sub:
            continue
        dispersao([e["barras_ate_terminal"] if e["barras_ate_terminal"] == e["barras_ate_terminal"]
                   else e["barras_ate_entrar"] for e in sub], "barras até o desfecho")
        dispersao([e["profundidade_max_pts"] for e in sub], "profundidade máxima (pts)")
        dispersao([e["profundidade_max_frac"] for e in sub], "profundidade máxima (fração da largura)")
        if ramo == "c2_atravessa_ate_oposta":
            dispersao([e["overshoot_oposta_pts"] for e in sub], "quanto passa da borda oposta (pts)")
            r_por_op = np.array([e["profundidade_max_pts"] * PONTO_VALOR_BRL - PEDAGIO_PONTOS * PONTO_VALOR_BRL for e in sub])
            print(f"    R$/contrato mediano líquido de pedágio (alvo=profundidade máxima): "
                  f"{br(float(np.median(r_por_op)),2)}")

    print("\n" + "=" * 140)
    print("(d) O DESFECHO DEPENDE DE QUANTO O PREÇO JÁ ANDOU NA DETECÇÃO?")
    print("=" * 140)
    afast = np.array([e["afastamento"] for e in eventos])
    corte = float(np.median(afast))
    print(f"  mediana do afastamento na detecção: {br(corte,0)} pontos (corte usado abaixo)")
    curto = [e for e in eventos if e["afastamento"] < corte]
    esticado = [e for e in eventos if e["afastamento"] >= corte]
    tabela_taxonomia(curto, f"CURTO (afastamento < {br(corte,0)} pts)")
    tabela_taxonomia(esticado, f"ESTICADO (afastamento >= {br(corte,0)} pts)")

    print("\n" + "=" * 140)
    print("(f) SEGUNDO ROMPIMENTO -- depois de ENTRAR, o preço rompe de novo?")
    print("=" * 140)
    c1 = [e for e in eventos if e["ramo"] == "c1_sai_mesmo_lado"]
    c2 = [e for e in eventos if e["ramo"] == "c2_atravessa_ate_oposta"]
    print(f"  entrou e reconfirmou rompimento MESMO lado (c1): {len(c1)} ({pct(len(c1)/n)} de todos)")
    print(f"  entrou e rompeu o lado OPOSTO (c2, segundo rompimento de verdade): "
          f"{len(c2)} ({pct(len(c2)/n)} de todos)")
    print(f"  razão c2/(c1+c2) -- dado que houve 2o rompimento, fração que foi "
          f"para o lado OPOSTO: {pct(len(c2)/(len(c1)+len(c2))) if (c1 or c2) else '—'}")
    print("  nulo desta razão é 50% (nenhuma razão estrutural para preferir um lado)")
    c1n = [e for e in nulos if e["ramo"] == "c1_sai_mesmo_lado"]
    c2n = [e for e in nulos if e["ramo"] == "c2_atravessa_ate_oposta"]
    print(f"  NULO: c1={len(c1n)}  c2={len(c2n)}  razão oposto={pct(len(c2n)/(len(c1n)+len(c2n))) if (c1n or c2n) else '—'}")

    print("\n" + "=" * 140)
    print("COMO LER")
    print("=" * 140)
    print("  * (b)+(c) tem de ser >= os 69,3% de reteste medidos em horizonte 60 barras por")
    print("    rompimento_retangulo_fenomeno_2026_09_16.py (aqui o horizonte é o pregão")
    print("    inteiro) -- é a conferência cruzada; menor que 69,3% seria bug.")
    print("  * Toda medida de tempo/magnitude conta a partir do PONTO DE DECISÃO")
    print("    (o próprio instante do evento), nunca da borda de graça.")
    print("  * O NULO usa a MESMA largura do evento pareado, herdada -- não existe")
    print("    'largura do retângulo' num ponto que não tem retângulo.")
    print("  * Só o IS. A janela cega (>= 2026-06-13) fica intacta.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
