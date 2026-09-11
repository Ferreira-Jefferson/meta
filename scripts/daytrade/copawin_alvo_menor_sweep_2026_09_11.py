# -*- coding: utf-8 -*-
"""Varredura do ALVO do `copa_win` (WIN@) -- a hipotese do dono, 2026-09-11.

"A estrategia diz que o alvo deve ser 100, mas em varios trades ele alcanca
60%, entao podemos testar se colocar o alvo a 60% do sugerido nao aumenta a
taxa de acerto do alvo e talvez mantenha o resultado positivo mesmo sem
depender tanto do tempo."

O DIAGNOSTICO QUE MOTIVOU (`copawin_excursao_alvo_stop_2026_09_11.py`, 321
trades): a excursao favoravel MEDIANA e' 31,6% do alvo pedido, e o alvo
cheio e' encostado por 6,9% dos trades. A taxa de acerto POTENCIAL por
fracao do alvo:

    100%  6,9%  |  60%  28,3%  |  30%  53,9%
     90% 13,1%  |  50%  34,3%  |  20%  67,3%
     80% 17,1%  |  40%  42,7%  |  10%  78,5%

Aquela tabela e' TETO, nao previsao: baixar o alvo fecha o trade mais cedo e
muda tudo o que vem depois no mesmo pregao (`max_entradas_dia=10`). Esta
varredura e' quem mede o dinheiro.

O QUE ELA TEM DE DECIDIR -- sao TRES perguntas, nao uma, e elas podem ter
respostas diferentes:
  1. a taxa de acerto do alvo sobe? (deve subir por construcao -- serve de
     conferencia de que a varredura esta medindo o que se pensa)
  2. a DEPENDENCIA DO RELOGIO cai? -- e' a coluna `flat%` (fracao das saidas
     por achatamento de fim de pregao). E' o objetivo declarado do dono;
  3. o resultado sobrevive? -- liquido, e sobretudo o VEREDITO (IC95% do
     win% contra o breakeven EMPIRICO). Um alvo menor melhora a razao
     risco:retorno no papel e piora o payoff realizado ao mesmo tempo; so'
     o breakeven empirico concilia os dois (itens 6.22/6.23).

ARITMETICA QUE MANDA DUVIDAR ANTES DE MEDIR (a hipotese nula desta rodada):
os 22 trades que hoje batem o alvo cheio valem muito, e um alvo menor corta
o ganho DELES para financiar a conversao dos outros. Pela tabela 4 do
diagnostico, a 60% a conversao rende ~+R$46/contrato em 69 trades (~+R$3.170)
enquanto o corte nos 22 vencedores custa ~-R$4.655. Se essa conta grosseira
estiver certa, o alvo menor compra menos dependencia do relogio PAGANDO em
resultado -- que continua podendo ser um bom negocio para o dono, mas e'
uma TROCA, nao uma melhora de graca.

RESSALVAS que viajam com qualquer numero daqui:
  * WIN@ NAO tem fidelidade de execucao calibrada (so' WDO@ esta em
    `backtest.intraday.fidelidade.FIDELIDADE`) -- entrada E saida enchem no
    primeiro toque, e a linha sai carimbada `fila NAO CALIBRADA`. Este vies
    PIORA aqui: um alvo menor e' tocado mais vezes, entao a suposicao de
    "tocou = preencheu" e' exercida mais vezes;
  * a janela OOS do WIN@ (>=2026-06-13) ja' foi gasta duas vezes;
  * `alvo_vol` foi varrido em 2026-08-28 (400 celulas) e 19,0 venceu -- mas
    aquela varredura otimizou LIQUIDO, nao dependencia do relogio, e rodou
    antes do modelo de custo atual.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_alvo_menor_sweep_2026_09_11.py`
"""
from __future__ import annotations

import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
OOS_INICIO = pd.Timestamp("2026-06-13").date()
ALVO_VOL_PRODUCAO = 19.0
#: fracao do alvo que a estrategia pede hoje. 1,00 = producao (linha de base).
FRACOES = [1.00, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10]
#: R$250 e' o capital REAL do slot (CLAUDE.md manda medir nele). R$3.000 e' o
#: unico nivel onde a populacao de trades existe -- a R$250 o robo trava e a
#: janela vira censurada, entao ela mede o portao de capital, nao o alvo.
CAPITAIS = [250.0, 3_000.0]
EXTRAS = ("alvo%", "acerto alvo", "flat%", "BE emp", "IC95 win", "s/trade", "caixa min")

_BARS_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95_proporcao(k: int, n: int):
    """IC95% de Wilson -- serve em n pequeno, ao contrario do normal ingenuo."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def _bars(janela: str):
    if janela not in _BARS_CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        df = df[[d in completos for d in df.index.date]]
        if janela == "IS":
            df = df[[d < OOS_INICIO for d in df.index.date]]
        else:
            df = df[[d >= OOS_INICIO for d in df.index.date]]
        _BARS_CACHE[janela] = df
    return _BARS_CACHE[janela]


def _roda(janela: str, capital: float, fracao: float):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars(janela)
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    strat.alvo_vol = ALVO_VOL_PRODUCAO * fracao

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    n = len(trades)
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    lo, hi = ic95_proporcao(len(ganhos), n)
    g_med = sum(ganhos) / len(ganhos) if ganhos else 0.0
    p_med = abs(sum(perdas) / len(perdas)) if perdas else 0.0
    be = p_med / (g_med + p_med) if (g_med + p_med) > 0 else float("nan")
    alvo = sum(1 for t in trades if t.exit_reason.value == "target")
    flat = sum(1 for t in trades if t.exit_reason.value == "forced_flatten")

    pregoes_total = len(set(pd.DatetimeIndex(bars.index).date))
    com_trade = len({t.entry_ts.date() for t in trades})
    eq = res.equity_curve
    caixa_min = float(eq.min()) if eq is not None and not eq.empty else capital

    nome = "alvo " + br(100 * fracao, 0) + "% (vol " + br(ALVO_VOL_PRODUCAO * fracao, 1) + ")"
    linha = linha_de_resultado(
        janela + " " + br(capital, 0) + " " + nome, res, capital,
        extras={
            "alvo%": br(100 * fracao, 0) + "%",
            "acerto alvo": br(100 * alvo / n, 1) + "%" if n else "--",
            "flat%": br(100 * flat / n, 1) + "%" if n else "--",
            "BE emp": br(100 * be, 2) + "%" if be == be else "--",
            "IC95 win": "[" + br(100 * lo, 1) + ";" + br(100 * hi, 1) + "]",
            "s/trade": str(pregoes_total - com_trade) + "/" + str(pregoes_total),
            "caixa min": br(caixa_min),
        },
    )
    return dict(
        janela=janela, capital=capital, fracao=fracao, nome=nome, linha=linha, dt=dt,
        n=n, win=(len(ganhos) / n if n else 0.0), be=be, lo=lo, hi=hi,
        acerto_alvo=(alvo / n if n else 0.0), flat=(flat / n if n else 0.0),
        liquido=sum(t.pnl_brl for t in trades),
        sem_trade=pregoes_total - com_trade, pregoes=pregoes_total, caixa_min=caixa_min,
        veredito=("POSITIVO" if (n and lo > be) else
                  "NEGATIVO" if (n and hi < be) else "indefinido"),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        r = _roda(*args)
    return r


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import tabela

    tarefas = [(j, c, f) for j in ("IS", "OOS") for c in CAPITAIS for f in FRACOES]
    print(str(len(tarefas)) + " celulas: " + str(len(FRACOES)) + " fracoes de alvo x "
          + str(len(CAPITAIS)) + " capitais x 2 janelas", flush=True)
    print("cada uma imprime assim que termina\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            be = br(100 * r["be"], 1) if r["be"] == r["be"] else "--"
            print("[" + str(len(resultados)).rjust(2) + "/" + str(len(tarefas)) + "] "
                  + r["janela"].rjust(3) + " cap " + br(r["capital"], 0).rjust(8) + " "
                  + r["nome"].ljust(22)
                  + " liq " + br(r["liquido"]).rjust(12)
                  + "  n=" + str(r["n"]).ljust(4)
                  + " alvo " + (br(100 * r["acerto_alvo"], 1) + "%").rjust(6)
                  + " flat " + (br(100 * r["flat"], 1) + "%").rjust(6)
                  + " win " + (br(100 * r["win"], 1) + "%").rjust(6)
                  + " BE " + (be + "%").rjust(6)
                  + "  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"])
                  + "  " + r["veredito"]
                  + "  (" + str(round(r["dt"])) + "s)", flush=True)

    for janela in ("IS", "OOS"):
        for capital in CAPITAIS:
            sel = [r for r in resultados if r["janela"] == janela and r["capital"] == capital]
            sel.sort(key=lambda r: -r["fracao"])
            print("\n\n===== " + janela + " - capital R$ " + br(capital, 0) + " =====", flush=True)
            print(tabela([r["linha"] for r in sel], extras=EXTRAS), flush=True)

    print("\n\n===== RESUMO: as tres perguntas, lado a lado (capital R$ 3.000) =====")
    print("alvo".rjust(6) + "janela".rjust(8) + "n".rjust(6) + "acerto alvo".rjust(13)
          + "flat%".rjust(8) + "liquido".rjust(13) + "win%".rjust(8) + "BE%".rjust(8)
          + "veredito".rjust(13))
    for r in sorted([x for x in resultados if x["capital"] == 3_000.0],
                    key=lambda r: (-r["fracao"], r["janela"])):
        be = br(100 * r["be"], 2) if r["be"] == r["be"] else "--"
        print((br(100 * r["fracao"], 0) + "%").rjust(6) + r["janela"].rjust(8)
              + str(r["n"]).rjust(6) + (br(100 * r["acerto_alvo"], 1) + "%").rjust(13)
              + (br(100 * r["flat"], 1) + "%").rjust(8) + br(r["liquido"]).rjust(13)
              + br(100 * r["win"], 2).rjust(8) + be.rjust(8) + r["veredito"].rjust(13))


if __name__ == "__main__":
    main()
