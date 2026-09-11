# -*- coding: utf-8 -*-
"""O alvo do `copa_win` vira ordem-limite REAL -- e quanta FILA ele aguenta.

Ordem do dono, 2026-09-11, depois da varredura de alvo
(`copawin_alvo_menor_sweep_2026_09_11.py`): converter o alvo para ordem-limite
fatiada e varrer a sensibilidade a fila.

POR QUE ESTA MEDICAO EXISTE. A varredura de alvo achou que baixar o alvo para
50% do pedido tira a dependencia do fechamento do pregao -- a contribuicao do
achatamento para o lucro cai de 114,1% para 5,0% no IS -- mas transfere o
resultado inteiro para a saida por ALVO (de 79,9% para 211,4%). E a saida por
alvo era justamente a perna que o motor NAO sabia questionar: sem fatia,
`exit_queue_ahead_qty` nem e' consultado (o caminho da fila mora em
`machine._resolve_target_partial_fill`, que so' roda com `exit_split_unit`),
entao "tocou" virava "preencheu", sempre. O ganho morava exatamente onde o
simulador e' mais otimista -- a assinatura que este projeto ja pagou duas
vezes (deslize do TP nativo; fila da familia maker, onde o motor chegou a
errar o SINAL: +R$3,82/op previsto contra -R$3,00 realizado).

`fatiar_saida_alvo=True` (novo em `CopaWin`, opt-in) poe o alvo como
ordem-limite parada no livro, e com isso a fila passa a alcanca-lo.

O QUE ESTE SCRIPT E' E O QUE ELE NAO E'.
  * E' um teste de SENSIBILIDADE: "a que nivel de fila o ganho morre?".
  * NAO e' uma previsao. O WIN@ continua SEM fidelidade calibrada
    (`backtest.intraday.fidelidade.FIDELIDADE` so' tem WDO@, medido contra
    extrato real), entao nenhum dos niveis abaixo e' "a fila do WIN@" -- sao
    degraus declarados, expressos em FRACAO DO VOLUME DA BARRA MEDIANA para
    terem escala interpretavel em vez de serem numeros soltos. Escolher um
    deles como se fosse medida seria exatamente o que o CLAUDE.md proibe.

ESCOPO DELIBERADO: varre so' a fila da SAIDA. A fila da ENTRADA fica em 0,0
nos dois lados da comparacao -- a pergunta aqui e' o que DIFERENCIA o alvo
50% do alvo 100%, e o que os diferencia e' a saida (3x mais fills por alvo).
Consequencia que viaja com o resultado: a perna de ENTRADA continua otimista
em TODAS as linhas.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_alvo_fatiado_fila_sensibilidade_2026_09_11.py`
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

FRACOES_ALVO = [1.00, 0.50]
CAPITAIS = [250.0, 3_000.0]
#: fila na frente da nossa ordem-limite de ALVO, em FRACAO do volume da barra
#: M1 mediana do WIN@ (o script imprime o numero absoluto que cada uma vira).
#: `None` = alvo NATIVO (o mecanismo de ate 2026-09-11, sem fatia nenhuma) --
#: e' a linha de base contra a qual a fatia tem de se justificar.
FILAS_EM_BARRAS = [None, 0.0, 0.10, 0.25, 0.50, 1.00, 2.00]
EXTRAS = ("alvo%", "mecanismo", "acerto alvo", "flat%", "BE emp", "IC95 win",
          "s/trade", "caixa min")

_BARS_CACHE: dict = {}
_VOL_MEDIANO: dict = {}


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95_proporcao(k: int, n: int):
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def _volume_mediano() -> float:
    """Volume da barra M1 MEDIANA do WIN@, pela MESMA regra que o motor usa
    (`backtest.intraday.engine._bar_volume`: `real_volume` quando reportado,
    `tick_volume` senao) -- redigitar a regra aqui produziria uma escala que
    nao e' a do motor."""
    if "v" not in _VOL_MEDIANO:
        sys.path.insert(0, str(ROOT / "src"))
        from backtest.intraday.engine import _bar_volume

        df = _todas_as_barras()
        _VOL_MEDIANO["v"] = float(df.apply(_bar_volume, axis=1).median())
    return _VOL_MEDIANO["v"]


def _todas_as_barras():
    if "tudo" not in _BARS_CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        _BARS_CACHE["tudo"] = df[[d in completos for d in df.index.date]]
    return _BARS_CACHE["tudo"]


def _bars(janela: str):
    if janela not in _BARS_CACHE:
        df = _todas_as_barras()
        if janela == "IS":
            df = df[[d < OOS_INICIO for d in df.index.date]]
        else:
            df = df[[d >= OOS_INICIO for d in df.index.date]]
        _BARS_CACHE[janela] = df
    return _BARS_CACHE[janela]


def _roda(janela: str, capital: float, fracao: float, fila_barras):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars(janela)
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    strat.alvo_vol = ALVO_VOL_PRODUCAO * fracao
    fatiado = fila_barras is not None
    strat.fatiar_saida_alvo = fatiado
    fila_qtd = (fila_barras * _volume_mediano()) if fatiado else 0.0

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        # a perna de ENTRADA fica de fora da varredura de proposito (ver o
        # modulo) -- declarado explicito, nunca herdado em silencio
        queue_ahead_qty=0.0,
        exit_queue_ahead_qty=fila_qtd,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    n = len(trades)
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    lo, hi = ic95_proporcao(len(ganhos), n)
    g = sum(ganhos) / len(ganhos) if ganhos else 0.0
    pm = abs(sum(perdas) / len(perdas)) if perdas else 0.0
    be = pm / (g + pm) if (g + pm) > 0 else float("nan")
    alvo = sum(1 for t in trades if t.exit_reason.value == "target")
    flat = sum(1 for t in trades if t.exit_reason.value == "forced_flatten")

    pregoes = len(set(pd.DatetimeIndex(bars.index).date))
    com = len({t.entry_ts.date() for t in trades})
    eq = res.equity_curve
    caixa_min = float(eq.min()) if eq is not None and not eq.empty else capital

    mec = "tp NATIVO" if not fatiado else ("limite fila " + br(fila_barras, 2) + "x")
    nome = "alvo " + br(100 * fracao, 0) + "% - " + mec
    linha = linha_de_resultado(
        janela + " " + br(capital, 0) + " " + nome, res, capital,
        extras={
            "alvo%": br(100 * fracao, 0) + "%",
            "mecanismo": mec,
            "acerto alvo": br(100 * alvo / n, 1) + "%" if n else "--",
            "flat%": br(100 * flat / n, 1) + "%" if n else "--",
            "BE emp": br(100 * be, 2) + "%" if be == be else "--",
            "IC95 win": "[" + br(100 * lo, 1) + ";" + br(100 * hi, 1) + "]",
            "s/trade": str(pregoes - com) + "/" + str(pregoes),
            "caixa min": br(caixa_min),
        },
    )
    return dict(
        janela=janela, capital=capital, fracao=fracao, fila_barras=fila_barras,
        fila_qtd=fila_qtd, mec=mec, nome=nome, linha=linha, dt=dt, n=n,
        win=(len(ganhos) / n if n else 0.0), be=be, lo=lo, hi=hi,
        acerto_alvo=(alvo / n if n else 0.0), flat=(flat / n if n else 0.0),
        liquido=sum(t.pnl_brl for t in trades),
        sem_trade=pregoes - com, pregoes=pregoes, caixa_min=caixa_min,
        veredito=("POSITIVO" if (n and lo > be) else
                  "NEGATIVO" if (n and hi < be) else "indefinido"),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import tabela

    vmed = _volume_mediano()
    print("volume da barra M1 MEDIANA do WIN@: " + br(vmed, 0) + " contratos", flush=True)
    print("degraus de fila varridos (na frente da nossa ordem de ALVO):", flush=True)
    for f in FILAS_EM_BARRAS:
        if f is None:
            print("   tp NATIVO  -- sem fatia; a fila nem e' consultada", flush=True)
        else:
            print("   " + (br(f, 2) + "x barra").rjust(12) + " = "
                  + br(f * vmed, 0).rjust(9) + " contratos", flush=True)
    print(flush=True)

    tarefas = [(j, c, fr, fi) for j in ("IS", "OOS") for c in CAPITAIS
               for fr in FRACOES_ALVO for fi in FILAS_EM_BARRAS]
    print(str(len(tarefas)) + " celulas\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            be = br(100 * r["be"], 1) if r["be"] == r["be"] else "--"
            print("[" + str(len(resultados)).rjust(2) + "/" + str(len(tarefas)) + "] "
                  + r["janela"].rjust(3) + " cap " + br(r["capital"], 0).rjust(8) + " "
                  + r["nome"].ljust(30)
                  + " liq " + br(r["liquido"]).rjust(12)
                  + "  n=" + str(r["n"]).ljust(4)
                  + " alvo " + (br(100 * r["acerto_alvo"], 1) + "%").rjust(6)
                  + " win " + (br(100 * r["win"], 1) + "%").rjust(6)
                  + " BE " + (be + "%").rjust(6)
                  + "  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"])
                  + "  " + r["veredito"] + "  (" + str(round(r["dt"])) + "s)", flush=True)

    ordem = {None: -1}
    for janela in ("IS", "OOS"):
        for capital in CAPITAIS:
            sel = [r for r in resultados if r["janela"] == janela and r["capital"] == capital]
            sel.sort(key=lambda r: (-r["fracao"], ordem.get(r["fila_barras"], r["fila_barras"] or 0)))
            print("\n\n===== " + janela + " - capital R$ " + br(capital, 0) + " =====", flush=True)
            print(tabela([r["linha"] for r in sel], extras=EXTRAS), flush=True)

    print("\n\n===== ATE QUE FILA O GANHO SOBREVIVE (capital R$ 3.000) =====")
    print("A pergunta e' onde cada alvo PARA de ter veredito. Fila em fracao da")
    print("barra M1 mediana; a perna de ENTRADA esta em 0 nas duas colunas.\n")
    print("fila".rjust(14) + "alvo 100% IS".rjust(16) + "alvo 100% OOS".rjust(16)
          + "alvo 50% IS".rjust(16) + "alvo 50% OOS".rjust(16))
    for f in FILAS_EM_BARRAS:
        rot = "tp NATIVO" if f is None else br(f, 2) + "x barra"
        cels = []
        for fr in (1.00, 0.50):
            for j in ("IS", "OOS"):
                m = [r for r in resultados if r["capital"] == 3_000.0
                     and r["fracao"] == fr and r["fila_barras"] == f and r["janela"] == j]
                cels.append(br(m[0]["liquido"], 0) + " " + m[0]["veredito"][:3] if m else "--")
        print(rot.rjust(14) + cels[0].rjust(16) + cels[1].rjust(16)
              + cels[2].rjust(16) + cels[3].rjust(16))


if __name__ == "__main__":
    main()
