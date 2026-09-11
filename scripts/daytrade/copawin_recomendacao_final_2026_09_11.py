# -*- coding: utf-8 -*-
"""A recomendacao final para "ganhar pouco, mas sempre" -- `copa_win`, WIN@.

Pedido do dono, 2026-09-11: "descubra como fazer essa estrategia se tornar
ganhadora mesmo que pouco, mas constante".

Este script NAO descobre nada: ele fecha a conta. Imprime na TABELA PADRAO do
projeto (`backtest.intraday.report`, 12 colunas + extras) as tres unicas
configuracoes que sobreviveram a seis rodadas de medicao, nas quatro janelas
que importam, e roda o teste por data de inicio para as tres.

O QUE FOI REFUTADO NO CAMINHO (para ninguem re-propor amanha):

  * `trail_vol` ligado -- 40 de 40 celulas com win% em 33-38% colado no
    breakeven empirico. O stop arrastado corta o vencedor antes de ele pagar
    o perdedor, e este robo vive de poucos trades grandes.
  * `stop_vol` mais curto (4, 6, 8, 10) -- degrada monotonicamente. E 12 e'
    OMBRO, nao borda: 14, 16 e 20 tambem pioram.
  * `corte_persistencia` mais agressivo (0,6 a 0,9) -- o robo QUEBRA: 123 a
    150 dos 191 pregoes sem trade, caixa abaixo do portao. Desistir cedo,
    aqui, e' desistir do lucro junto.
  * `risco_pct_por_trade` (1% / 2% / 5%) -- INERTE. A R$3.000 a quantidade
    esta presa em 1 contrato pelo piso de `quantidade_por_entrada`, entao NAO
    EXISTE hoje um botao de "ganhar menos e oscilar menos". O unico tamanho
    disponivel e' 1. Quem quiser escala menor precisa de outro instrumento,
    nao de outro parametro.
  * `max_entradas_dia` (1, 2, 3, 5) -- corta lucro sem comprar constancia.
  * mexer na `defesa_ativa` -- as variantes mais lucrativas (0,2/0,3 e
    0,6/0,2) compram lucro com CAUDA: pior pregao de -R$1.469 para -R$2.166,
    MaxDD quase dobrado. Direcao errada para este pedido.
  * `janela_rompimento` 5/20/30 e `aquecimento_barras` 30/60/90 -- todos
    piores que o default em ambas as janelas.

O QUE SOBROU -- dois parametros, e os dois sao do MESMO tipo: nao mexem em
quanto o robo arrisca, mexem em QUAIS operacoes ele aceita fazer.

  1. `alvo_vol` 9,5 -> 7,6. Aproxima o alvo do que a excursao favoravel de
     fato alcanca. Acerto do alvo sobe de 20,3% para ~32%. PLATO confirmado:
     7,6 e 8,55 dao os dois 100% de datas de inicio positivas.
  2. `entrada_ttl_barras` 15 -> 5. A ordem-limite de reteste espera 5 minutos
     pelo recuo, nao 15. NAO e' numero de grade justificado depois: o
     CLAUDE.md ja documenta o mecanismo, medido no `wdo_orb` -- ordem de
     entrada com prazo longo preenche horas depois do sinal (269,7 min no
     caso medido) e "os fills atrasados foram justamente os piores
     resultados".

     Os dois andam JUNTOS. O prazo curto SOZINHO (a9,5+ttl5) e' PIOR que a
     producao no que interessa: 96,1% de datas positivas contra 89,5%, mas
     com uma MORTE e pior inicio de -R$2.992,50 (a producao: -R$888,40).

A ESCOLHA ENTRE ttl5 E ttl8, dita em voz alta porque e' o unico ponto em que
duas leituras honestas discordam. `ttl8` rende MAIS (+R$23.812 contra
+R$18.322 no historico) e leva veredito POSITIVO tambem no OOS. `ttl5` ganha
no criterio que o dono pediu: MaxDD de R$2.735 contra R$5.224, pior pregao de
-R$947 contra -R$2.913, blocos de 20 pregoes positivos 97% contra 95%, meses
positivos 100% contra 80%. E o eixo do prazo NAO tem plato de lucro (ttl3
7.295 / ttl5 18.322 / ttl8 23.812 / ttl15 14.271 -- vizinhos discordando em
60%), entao escolher o 8 e' escolher o maior numero de um eixo ruidoso, que
e' exatamente o que este repo ja pagou caro para nao fazer. `ttl5` e' a
escolha por criterio declarado; `ttl8` e' a escolha por liquido. As duas
estao na tabela.

O FREIO DIARIO como bonus, e por que ele funciona onde a escada de risco por
trade falhou. `perda_max_dia_pontos=300` = R$900 por pregao (`pontos x
point_value x teto_contratos`), FIXO em reais. Fixo parece defeito e aqui e'
a virtude: a R$3.000 ele e' 30% da carteira, a R$18.000 e' 5%. E' a escada
que o dono pediu em 2026-09-11 ("ate' 50% da carteira e ir diminuindo ... para
representar no maximo 5%") -- e ela funciona AQUI porque age sobre o DIA, onde
varias operacoes se acumulam, e nao sobre a operacao unica, onde o piso de 1
contrato tornava a escada aritmeticamente inerte.

LIMITACAO QUE NAO PODE SER APAGADA: o OOS do WIN@ (>=2026-06-13) ja foi gasto
varias vezes, inclusive hoje. Nao existe teste cego para este robo. O que
sustenta a recomendacao e' (i) o PLATO no eixo do alvo, (ii) 100% das datas
de inicio, que e' robustez e nao cegueira, (iii) o mecanismo ser legivel nos
dois casos, e (iv) sobreviver a fila ate 4x o volume mediano da barra. Nao e'
validacao fora da amostra e nao deve ser vendida como tal.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_recomendacao_final_2026_09_11.py`
"""
from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 3_000.0
OOS_INICIO = pd.Timestamp("2026-06-13").date()
DUAS_SEMANAS = pd.Timestamp("2026-09-01").date()
BLOCO = 20
HORIZONTE = 40
PASSO = 2

EXTRAS = ("preg+", "bl20+", "mes+", "top5", "pior dia", "alvo%", "BE emp",
          "IC95 win", "veredito")

CONFIGS: list[tuple[str, dict]] = [
    ("PRODUCAO a9,5 ttl15", {}),
    ("RECOMENDADA a7,6 ttl5", dict(alvo_vol=7.6, entrada_ttl_barras=5)),
    ("+ freio R$900/dia", dict(alvo_vol=7.6, entrada_ttl_barras=5,
                               perda_max_dia_pontos=300.0)),
    ("alternativa a7,6 ttl8", dict(alvo_vol=7.6, entrada_ttl_barras=8)),
]

_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    if v != v:
        return "--"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int):
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


def _base():
    if "df" not in _CACHE:
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        cont = df.groupby(df.index.date).size()
        dias = sorted(d for d, n in cont.items() if n >= MIN_BARRAS_POR_PREGAO)
        _CACHE["df"] = df[[d in set(dias) for d in df.index.date]]
        _CACHE["dias"] = dias
    return _CACHE["df"], _CACHE["dias"]


def _dias_da(janela: str):
    _, dias = _base()
    if janela == "IS":
        return [d for d in dias if d < OOS_INICIO]
    if janela == "OOS":
        return [d for d in dias if d >= OOS_INICIO]
    if janela == "2SEM":
        return [d for d in dias if d >= DUAS_SEMANAS]
    return list(dias)


def _rodar(kwargs: dict, ds):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, _ = _base()
    bars = df[[d in set(ds) for d in df.index.date]]
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    for k, v in kwargs.items():
        setattr(strat, k, v)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    return run_intraday_backtest(bars, strat, cfg)


def _extras(res, ds) -> dict:
    trades = list(res.trades)
    por_dia = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    serie = pd.Series([por_dia.get(d, 0.0) for d in ds], index=pd.to_datetime(ds))
    com = list(por_dia.values())
    blocos = [float(serie.iloc[i:i + BLOCO].sum())
              for i in range(0, max(1, len(serie) - BLOCO + 1))]
    mes = serie.groupby([serie.index.year, serie.index.month]).sum()
    ganhos = sorted((v for v in com if v > 0), reverse=True)
    bruto = sum(ganhos)
    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    alvos = sum(1 for t in trades if t.exit_reason.value == "target")
    return {
        "preg+": (br(100 * sum(1 for v in com if v > 0) / len(com), 0) + "%") if com else "--",
        "bl20+": (br(100 * sum(1 for b in blocos if b > 0) / len(blocos), 0) + "%") if blocos else "--",
        "mes+": (br(100 * int((mes > 0).sum()) / len(mes), 0) + "%") if len(mes) else "--",
        "top5": (br(100 * sum(ganhos[:5]) / bruto, 0) + "%") if bruto > 0 else "--",
        "pior dia": br(float(serie.min())) if len(serie) else "--",
        "alvo%": (br(100 * alvos / n, 1) + "%") if n else "--",
        "BE emp": (br(100 * be, 2) + "%") if be == be else "--",
        "IC95 win": "[" + br(100 * lo, 1) + ";" + br(100 * hi, 1) + "]",
        "veredito": (("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido")
                     if be == be and n else "--"),
    }


def _unidade_data(args):
    rotulo, kwargs, i = args
    buf = StringIO()
    with redirect_stdout(buf):
        _, dias = _base()
        janela = dias[i:i + HORIZONTE]
        res = _rodar(kwargs, janela)
        trades = list(res.trades)
        com = {t.entry_ts.date() for t in trades}
        eq = res.equity_curve
        por_dia = {}
        for t in trades:
            por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
        return dict(
            rotulo=rotulo, liquido=sum(t.pnl_brl for t in trades),
            maxdd=(float((eq.cummax() - eq).max())
                   if eq is not None and not eq.empty else 0.0),
            morreu=((getattr(res, "wiped_out_at", None) is not None)
                    or (len(janela) - len(com)) > 0),
            pior_dia=min(por_dia.values()) if por_dia else 0.0,
        )


def main() -> None:
    from backtest.intraday.report import linha_de_resultado, tabela

    _, dias = _base()
    print("copa_win / WIN@ -- capital R$ " + br(CAPITAL, 0)
          + " (piso declarado do robo), stop_vol 12,0 e trail DESLIGADO em todas")
    print(str(len(dias)) + " pregoes completos, " + str(dias[0]) + " a "
          + str(dias[-1]) + "\n", flush=True)

    rotulos = {
        "TUDO": "HISTORICO INTEIRO (191 pregoes)",
        "IS": "IS (< 2026-06-13)",
        "OOS": "OOS (>= 2026-06-13) -- JA GASTO: pode reprovar, nao pode promover",
        "2SEM": "AS DUAS ULTIMAS SEMANAS (01/09 a 10/09)",
    }
    for janela in ("TUDO", "IS", "OOS", "2SEM"):
        ds = _dias_da(janela)
        linhas = []
        for rot, kw in CONFIGS:
            res = _rodar(kw, ds)
            linhas.append(linha_de_resultado(rot, res, CAPITAL,
                                             extras=_extras(res, ds)))
        print("\n\n===== " + rotulos[janela] + " =====")
        print(tabela(linhas, extras=EXTRAS), flush=True)

    # ---- o teste que decide: toda data de inicio -------------------------
    inicios = list(range(0, len(dias) - HORIZONTE + 1, PASSO))
    tarefas = [(rot, kw, i) for rot, kw in CONFIGS for i in inicios]
    print("\n\nrodando " + str(len(tarefas)) + " simulacoes por data de inicio"
          " (horizonte fixo de " + str(HORIZONTE) + " pregoes)...", flush=True)
    res = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade_data, t): t for t in tarefas}
        for fut in as_completed(futs):
            res.append(fut.result())

    print("\n===== O TESTE QUE DECIDE: comecando em QUALQUER dia, "
          + str(HORIZONTE) + " pregoes a frente =====")
    hdr = ("configuracao".ljust(26) + "POSITIVAS".rjust(11) + "morreram".rjust(10)
           + "liq mediano".rjust(13) + "PIOR inicio".rjust(13)
           + "p25".rjust(12) + "MaxDD med".rjust(12) + "pior dia med".rjust(14))
    print(hdr)
    print("-" * len(hdr))
    for rot, _ in CONFIGS:
        sub = [r for r in res if r["rotulo"] == rot]
        liq = pd.Series([r["liquido"] for r in sub])
        print(rot.ljust(26)
              + (br(100 * float((liq > 0).mean()), 1) + "%").rjust(11)
              + str(sum(1 for r in sub if r["morreu"])).rjust(10)
              + br(float(liq.median())).rjust(13)
              + br(float(liq.min())).rjust(13)
              + br(float(liq.quantile(0.25))).rjust(12)
              + br(float(pd.Series([r["maxdd"] for r in sub]).median()), 0).rjust(12)
              + br(float(pd.Series([r["pior_dia"] for r in sub]).median()), 0).rjust(14))


if __name__ == "__main__":
    main()
