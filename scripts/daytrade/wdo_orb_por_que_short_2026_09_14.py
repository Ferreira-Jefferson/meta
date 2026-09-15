"""INVESTIGACAO (2026-09-14) -- por que o VENDIDO vence mesmo com o dolar subindo?

## O fato que nao fecha

O `wdo_orb` opera comprado e vendido pelo mesmo criterio simetrico (rompe pra
cima, compra; rompe pra baixo, vende). Mesmo assim o vendido bate o comprado
em 9 de 9 recortes (3 janelas x 3 pernas), +33,33/op no agregado. A explicacao
obvia -- "o dolar caiu no periodo" -- foi checada e NAO se sustenta: no
OOS_LIMPO o dolar SUBIU 3,53% e o vendido venceu do mesmo jeito.

Um criterio simetrico dando resultado assimetrico e' um sintoma. Alguma coisa
no mercado ou no MECANISMO do robo quebra a simetria, e essa coisa ainda nao
foi nomeada. Este script faz as tres perguntas que ninguem tinha feito.

## Pergunta 1 -- o dolar sobe DE NOITE e cai DE DIA?

O robo nunca carrega posicao overnight: ele so' captura o movimento de dentro
do pregao. Fechamento-a-fechamento (que foi como o "+3,53%" foi medido) mistura
duas coisas que ele vive de forma completamente diferente:

    gap        = abertura[d] - fechamento[d-1]   <- o robo NUNCA pega isto
    intradiario = fechamento[d] - abertura[d]    <- o robo so' vive disto

Se a alta do periodo veio dos GAPS enquanto o intradiario foi de baixa, o
"vendido vence em mercado de alta" deixa de ser misterio e vira aritmetica --
o mercado em que o robo vive e' outro mercado.

## Pergunta 2 -- a ordem-limite de entrada seleciona rompimento FRACO?

A entrada e' `EnterLimit` 2 ticks ATRAS do rompimento, esperando o recuo. Um
rompimento que sai e NAO volta nunca preenche -- o robo so' entra nos que
recuaram. Ou seja: por construcao, o robo opera a subamostra dos rompimentos
que hesitaram.

Se essa hesitacao for mais comum (ou mais informativa) de um lado que do
outro, o mecanismo de entrada -- e nao o mercado -- e' quem cria a assimetria.
Mede-se pela taxa de PREENCHIMENTO por lado: quantas ordens de compra foram
armadas e quantas encheram, contra o mesmo para venda.

## Pergunta 3 -- o mercado continua mais para baixo do que para cima?

Esta pergunta ignora o robo inteiro. Para cada pregao: achado o primeiro
rompimento de cada lado da faixa de abertura, o que o PRECO faz nos 60 minutos
seguintes (o horizonte do robo)? Quanto continua a favor do rompimento, quanto
volta contra, onde termina.

E' o teste mais limpo dos tres, porque nao ha' estrategia no meio: se a
continuacao apos rompimento de BAIXA for sistematicamente maior que apos
rompimento de ALTA, a assimetria e' do mercado, e vale para qualquer robo de
rompimento -- nao so' para este.

## Como ler o conjunto

As tres perguntas sao mutuamente exclusivas quanto a CULPA, e e' isso que as
torna uteis juntas:

    P1 positiva -> a assimetria e' do mercado, e e' de REGIME (dia x noite)
    P2 positiva -> a assimetria e' do MECANISMO de entrada do robo
    P3 positiva -> a assimetria e' do mercado, e e' de MICROESTRUTURA

Se nenhuma responder, a assimetria continua sem nome e o "vendido melhor"
volta a ser o que era antes deste script: uma coincidencia de 9 recortes que
nao passa em teste nenhum (menor p = 0,107).

Uso: `python -u scripts/daytrade/wdo_orb_por_que_short_2026_09_14.py`
"""
from __future__ import annotations

import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import JANELAS, pregoes_da_janela  # noqa: E402

SAIDA = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
MAX_WORKERS = min(10, (os.cpu_count() or 4))
RANGE_MIN = 15.0      # a faixa de abertura do robo
HORIZONTE_MIN = 60.0  # o horizonte do robo (saida_limite_minutos)


def mann_whitney(a: list[float], b: list[float]) -> tuple[float, float]:
    n1, n2 = len(a), len(b)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    j = [(v, 0) for v in a] + [(v, 1) for v in b]
    j.sort(key=lambda x: x[0])
    r = [0.0] * len(j); i = 0; emp = []
    while i < len(j):
        k = i
        while k + 1 < len(j) and j[k + 1][0] == j[i][0]:
            k += 1
        rm = (i + k + 2) / 2.0
        for t in range(i, k + 1):
            r[t] = rm
        if k > i:
            emp.append(k - i + 1)
        i = k + 1
    r1 = sum(x for x, (_, g) in zip(r, j) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    n = n1 + n2; mu = n1 * n2 / 2.0
    corr = sum(t ** 3 - t for t in emp)
    var = (n1 * n2 / 12.0) * ((n + 1) - corr / float(n * (n - 1)))
    if var <= 0:
        return float("nan"), float("nan")
    z = (u1 - mu) / math.sqrt(var)
    return z, 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def um_pregao(dia: str) -> dict:
    bars = carregar_bars(dia, dia)
    if bars.empty or len(bars) < 50:
        return {}
    preco = bars["close"]
    abertura_ts = bars.index.min()
    saida: dict = {
        "data": dia,
        "abertura": float(preco.iloc[0]),
        "fechamento": float(preco.iloc[-1]),
    }

    # ---- P3: o que o PRECO faz depois de romper (sem estrategia no meio) ----
    fim_faixa = abertura_ts + pd.Timedelta(minutes=RANGE_MIN)
    faixa = bars.loc[:fim_faixa, "close"]
    if faixa.empty:
        return saida
    hi, lo = float(faixa.max()), float(faixa.min())
    saida["faixa_ticks"] = (hi - lo) / TICK_SIZE
    depois = bars.loc[fim_faixa:, "close"]

    for lado, cond in (("alta", depois > hi), ("baixa", depois < lo)):
        rompeu = depois[cond]
        if rompeu.empty:
            continue
        ts0 = rompeu.index[0]
        p0 = float(rompeu.iloc[0])
        jan = depois.loc[ts0:ts0 + pd.Timedelta(minutes=HORIZONTE_MIN)]
        if jan.empty:
            continue
        sinal = 1.0 if lado == "alta" else -1.0
        saida[f"{lado}_hora"] = (ts0 - abertura_ts).total_seconds() / 60.0
        # continuacao = o quanto andou NO SENTIDO do rompimento
        saida[f"{lado}_continuacao"] = sinal * (jan.max() - p0) / TICK_SIZE if sinal > 0 \
            else sinal * (jan.min() - p0) / TICK_SIZE
        saida[f"{lado}_reversao"] = sinal * (jan.min() - p0) / TICK_SIZE if sinal > 0 \
            else sinal * (jan.max() - p0) / TICK_SIZE
        saida[f"{lado}_fim"] = sinal * (float(jan.iloc[-1]) - p0) / TICK_SIZE

    # ---- P2: taxa de preenchimento da ordem-limite, por lado ---------------
    strat = WdoOrbInstrumentado()
    cfg = monta_config(strat, CAPITAL_PARTIDA_BRL)
    res = run_intraday_backtest(bars, strat, cfg)
    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
    ts_fills = sorted(pd.Timestamp(t.entry_ts) for t in res.trades)
    lados_fill = {pd.Timestamp(t.entry_ts): t.side for t in res.trades}
    for k, lado in (("ordens_long", "long"), ("ordens_short", "short")):
        saida[k] = sum(1 for o in ordens if o["side"] == lado)
    saida["fills_long"] = sum(1 for ts in ts_fills if lados_fill[ts] == "long")
    saida["fills_short"] = sum(1 for ts in ts_fills if lados_fill[ts] == "short")
    return saida


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
    print(f"[investiga] {len(todos)} pregoes, {MAX_WORKERS} processos\n", flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(um_pregao, d): d for d in todos}
        for fut in as_completed(futuros):
            feitos += 1
            try:
                r = fut.result()
                if r:
                    linhas.append(r)
            except Exception as exc:
                print(f"[{futuros[fut]}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(todos)}", flush=True)

    df = pd.DataFrame(linhas).sort_values("data").reset_index(drop=True)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    # gap = abertura de hoje contra o fechamento de ontem (dentro da serie toda)
    df["gap_ticks"] = (df["abertura"] - df["fechamento"].shift(1)) / TICK_SIZE
    df["intradiario_ticks"] = (df["fechamento"] - df["abertura"]) / TICK_SIZE
    df.to_csv(SAIDA / "80_por_que_short.csv", index=False, encoding="utf-8")

    # =====================================================================
    print("=" * 104)
    print("P1 -- O DOLAR SOBE DE NOITE E CAI DE DIA?  (em ticks; 1 tick = R$5,00 no WDO@)")
    print("=" * 104)
    p1 = df.groupby("janela").agg(
        pregoes=("data", "count"),
        gap_total=("gap_ticks", "sum"),
        gap_medio=("gap_ticks", "mean"),
        intra_total=("intradiario_ticks", "sum"),
        intra_medio=("intradiario_ticks", "mean"),
        intra_neg_pct=("intradiario_ticks", lambda s: 100.0 * (s < 0).mean()),
    ).round(2).reindex(["IS", "OOS_LIMPO", "DESCOBERTA"])
    p1["total"] = (p1.gap_total + p1.intra_total).round(2)
    print(p1.to_string())
    print("\n  [leitura] `gap_total` e' o movimento que o robo NUNCA pega; "
          "`intra_total` e' o unico que ele vive.")
    print("  Se gap > 0 e intra < 0, o mercado do robo e' BAIXISTA mesmo num "
          "periodo de alta.")

    # =====================================================================
    print("\n" + "=" * 104)
    print("P2 -- A ORDEM-LIMITE SELECIONA ROMPIMENTO FRACO, E DE UM LADO SO'?")
    print("=" * 104)
    p2 = df.groupby("janela").agg(
        ordens_long=("ordens_long", "sum"), fills_long=("fills_long", "sum"),
        ordens_short=("ordens_short", "sum"), fills_short=("fills_short", "sum"),
    ).reindex(["IS", "OOS_LIMPO", "DESCOBERTA"])
    p2["fill_long_pct"] = (100.0 * p2.fills_long / p2.ordens_long).round(1)
    p2["fill_short_pct"] = (100.0 * p2.fills_short / p2.ordens_short).round(1)
    p2["dif_pp"] = (p2.fill_short_pct - p2.fill_long_pct).round(1)
    print(p2.to_string())
    print("\n  [leitura] taxa de fill MENOR de um lado = daquele lado o robo so' "
          "entra quando o rompimento hesita.")

    # =====================================================================
    print("\n" + "=" * 104)
    print("P3 -- O MERCADO CONTINUA MAIS PARA BAIXO DO QUE PARA CIMA?  "
          "(60 min apos o rompimento, sem estrategia)")
    print("=" * 104)
    linhas_p3 = []
    for janela in ["IS", "OOS_LIMPO", "DESCOBERTA", "TODAS"]:
        sub = df if janela == "TODAS" else df[df.janela == janela]
        for metrica in ["continuacao", "reversao", "fim"]:
            a = sub[f"alta_{metrica}"].dropna()
            b = sub[f"baixa_{metrica}"].dropna()
            z, p = mann_whitney(b.tolist(), a.tolist())
            linhas_p3.append({
                "janela": janela, "metrica": metrica,
                "n_alta": len(a), "alta_mediana": round(a.median(), 1),
                "n_baixa": len(b), "baixa_mediana": round(b.median(), 1),
                "dif": round(b.median() - a.median(), 1),
                "p": round(p, 4),
            })
    p3 = pd.DataFrame(linhas_p3)
    print(p3.to_string(index=False))
    p3.to_csv(SAIDA / "81_p3_rompimento.csv", index=False, encoding="utf-8")
    print("\n  [leitura] `continuacao` = quanto anda a favor do rompimento nos 60 min;")
    print("  `reversao` = quanto volta contra; `fim` = onde termina. Tudo em ticks,")
    print("  com sinal ja' ajustado ao lado (positivo = a favor de quem entrou no")
    print("  rompimento). Diferenca positiva = o lado da BAIXA anda mais.")

    print(f"\n[investiga] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
