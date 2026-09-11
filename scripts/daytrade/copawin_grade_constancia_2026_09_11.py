# -*- coding: utf-8 -*-
"""Grade de GEOMETRIA do `copa_win` pontuada por CONSTANCIA, nao por lucro.

Pedido do dono, 2026-09-11: "descubra como fazer essa estrategia se tornar
ganhadora mesmo que pouco, mas constante".

O QUE O DIAGNOSTICO (`copawin_consistencia_diagnostico_2026_09_11.py`) ACHOU
e que define esta grade -- decomposicao por motivo de saida, 191 pregoes,
capital R$3.000, config de PRODUCAO:

    motivo            ops     liquido     R$/op    win%
    stop               69  -30.206,00   -437,77     0,0%
    target             99  +26.506,10   +267,74   100,0%
    signal            135  +16.997,60   +125,91    53,3%   (defesa + corte)
    forced_flatten    185      +235,60     +1,27    51,9%

A perna que desequilibra e' o STOP: ele custa 1,64x o que o alvo paga. Nao e'
frequencia (14,1% das operacoes) -- e' TAMANHO. Um robo "constante" nao
precisa acertar mais; precisa que o dia ruim seja do tamanho do dia bom.

POR QUE A GRADE E' ESTA, e nao uma varredura de `alvo_vol` de novo. O alvo ja
foi varrido hoje (`copawin_alvo_menor_sweep_2026_09_11.py`, 10 fracoes) e
escolheu 50%. O que NUNCA foi varrido neste robo:

  * `stop_vol` -- 12,0 desde a calibracao de 2026-08-28, nunca mexido, e a
    perna cara segundo a tabela acima;
  * `trail_vol` -- **DESLIGADO em producao** (`None`). O mecanismo classico de
    "converter lucro aberto em lucro realizado" simplesmente nunca foi medido
    aqui. E' o candidato mais obvio de todos e estava invisivel.

CUIDADO QUE MUDA A LEITURA DA GRADE. `risco_pct_por_trade=0,05` dimensiona a
entrada PELA DISTANCIA DO STOP (`contracts_from_risk`): stop mais curto =>
MAIS contratos, com o mesmo orcamento de risco em reais. Entao encurtar o
stop NAO reduz o risco por operacao -- ele ja e' normalizado. O que muda e' a
GEOMETRIA (quantas operacoes morrem no stop contra quantas chegam ao alvo) e
a quantizacao (o piso de 1 contrato). Quem quiser reduzir o TAMANHO do
resultado -- ganhar menos e oscilar menos -- mexe em `risco_pct_por_trade`,
que e' outra rodada; esta grade mede a FORMA, nao a escala.

METODO, e a limitacao que vem junto. O OOS do WIN@ (>=2026-06-13) JA FOI
GASTO -- pelo menos tres vezes so' hoje. Nao existe teste cego disponivel
para este robo, e fingir que existe seria pior que nao ter. O que sobra, e
que e' honesto:

  1. ESCOLHER olhando o IS. O OOS entra so' como confirmacao, e uma
     confirmacao ja' contaminada -- ela pode REPROVAR (sign-flip mata o
     candidato) mas nao pode PROMOVER sozinha.
  2. Exigir PLATO, nao pico: a celula vizinha em cada eixo tem de continuar
     boa. Um maximo isolado numa grade e' ruido com endereco (item 6.25 e a
     grade de eixo morto da ORB).
  3. O veredito continua sendo IC95% do win% contra o breakeven EMPIRICO
     (itens 6.22/6.23). As metricas de constancia ORDENAM; elas nao promovem.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_grade_constancia_2026_09_11.py`
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
CAPITAL = 3_000.0
OOS_INICIO = pd.Timestamp("2026-06-13").date()
BLOCO = 20

#: Producao: alvo 9,5 / stop 12,0 / trail None. A grade contem a producao
#: como celula para a comparacao ser direta, nunca contra um numero lembrado.
#:
#: DUAS RODADAS, e a segunda existe por causa do resultado da primeira.
#:
#: `base` -- a varredura ampla: 4 alvos x 5 stops x 3 trails. Achou duas
#: coisas e as duas sao REFUTACOES limpas, nao ajustes:
#:   * TRAILING mata o robo. Em 40 celulas com `trail_vol` ligado o win% cai
#:     para 33-38% e cola no breakeven empirico (veredito `indefinido` em
#:     TODAS); o liquido do IS vai de +R$9.185 para perto de zero. O stop
#:     arrastado corta o vencedor antes de ele pagar o perdedor -- e este robo
#:     vive de poucos trades grandes (ver a docstring do modulo `copa_win`).
#:   * APERTAR O STOP tambem mata. Com trail desligado, `s12` e' a MELHOR
#:     coluna para TODO alvo; s10/s8/s6/s4 degradam monotonicamente. Mesmo
#:     mecanismo que `wdo_orb.alvo_multiplo` ja documentou em sentido
#:     contrario: com stop largo o perdedor sai pelo relogio com perda
#:     PEQUENA, com stop apertado o MESMO trade sai no stop CHEIO.
#:
#: `extensao` -- so' existe porque `s12` ficou na BORDA da grade base, e
#: maximo na borda nao e' ombro, e' parede que ninguem tentou atravessar. Aqui
#: o eixo do stop segue ate 20 e o do alvo ganha resolucao em volta de 7,6
#: (a celula que liderou a rodada base). Trail fica FORA: ja foi refutado.
RODADAS = {
    "base": dict(alvos=[5.7, 7.6, 9.5, 11.4],
                 stops=[4.0, 6.0, 8.0, 10.0, 12.0],
                 trails=[None, 2.0, 4.0]),
    "extensao": dict(alvos=[6.65, 7.6, 8.55, 9.5],
                     stops=[12.0, 14.0, 16.0, 20.0],
                     trails=[None]),
}
RODADA = sys.argv[1] if len(sys.argv) > 1 else "base"
ALVOS = RODADAS[RODADA]["alvos"]
STOPS = RODADAS[RODADA]["stops"]
TRAILS = RODADAS[RODADA]["trails"]

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
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        cont = df.groupby(df.index.date).size()
        dias = sorted(d for d, n in cont.items() if n >= MIN_BARRAS_POR_PREGAO)
        _CACHE["df"] = df[[d in set(dias) for d in df.index.date]]
        _CACHE["dias"] = dias
    return _CACHE["df"], _CACHE["dias"]


def _roda(janela: str, alvo: float, stop: float, trail):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _base()
    ds = [d for d in dias if (d < OOS_INICIO if janela == "IS" else d >= OOS_INICIO)]
    bars = df[[d in set(ds) for d in df.index.date]]

    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    strat.alvo_vol = alvo
    strat.stop_vol = stop
    strat.trail_vol = trail
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    por_dia = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    serie = pd.Series([por_dia.get(d, 0.0) for d in ds], index=pd.to_datetime(ds))
    com = list(por_dia.values())
    blocos = [float(serie.iloc[i:i + BLOCO].sum())
              for i in range(0, max(1, len(serie) - BLOCO + 1))]
    mes = serie.groupby([serie.index.year, serie.index.month]).sum()
    ganhos_dia = sorted((v for v in com if v > 0), reverse=True)
    bruto = sum(ganhos_dia)
    seq = pior = 0
    for v in serie.values:
        if v < 0:
            seq += 1
            pior = max(pior, seq)
        elif v > 0:
            seq = 0

    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    eq = res.equity_curve
    dd = float((eq.cummax() - eq).max()) if eq is not None and not eq.empty else 0.0
    cmin = float(eq.min()) if eq is not None and not eq.empty else CAPITAL
    stops = [t for t in trades if t.exit_reason.value == "stop"]
    alvos = [t for t in trades if t.exit_reason.value == "target"]
    flat = sum(t.pnl_brl for t in trades if t.exit_reason.value == "forced_flatten")
    liquido = sum(t.pnl_brl for t in trades)

    return dict(
        janela=janela, alvo=alvo, stop=stop, trail=trail, dt=dt,
        liquido=liquido, n=n, pregoes=len(ds), sem_trade=len(ds) - len(com),
        frac_preg=(sum(1 for v in com if v > 0) / len(com)) if com else float("nan"),
        frac_bl=(sum(1 for b in blocos if b > 0) / len(blocos)) if blocos else float("nan"),
        frac_mes=(int((mes > 0).sum()) / len(mes)) if len(mes) else float("nan"),
        top5=(sum(ganhos_dia[:5]) / bruto) if bruto > 0 else float("nan"),
        seq_neg=pior,
        flat_share=(flat / liquido) if liquido else float("nan"),
        win=(len(g) / n) if n else float("nan"), be=be, lo=lo, hi=hi,
        veredito=(("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido")
                  if be == be and n else "--"),
        maxdd=dd, caixa_min=cmin, zerou=(getattr(res, "wiped_out_at", None) is not None),
        stop_rs=(sum(t.pnl_brl for t in stops) / len(stops)) if stops else float("nan"),
        alvo_rs=(sum(t.pnl_brl for t in alvos) / len(alvos)) if alvos else float("nan"),
        stop_pct=(len(stops) / n) if n else float("nan"),
        alvo_pct=(len(alvos) / n) if n else float("nan"),
        rs_dia=(liquido / len(ds)) if ds else float("nan"),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def _rotulo(r) -> str:
    tr = "off" if r["trail"] is None else br(r["trail"], 0)
    return ("a" + br(r["alvo"], 1) + " s" + br(r["stop"], 0) + " t" + tr)


def _linha(r) -> str:
    return (_rotulo(r).ljust(16)
            + br(r["liquido"]).rjust(12) + str(r["n"]).rjust(6)
            + br(r["rs_dia"]).rjust(9)
            + (br(100 * r["frac_preg"], 0) + "%").rjust(7)
            + (br(100 * r["frac_bl"], 0) + "%").rjust(7)
            + (br(100 * r["frac_mes"], 0) + "%").rjust(7)
            + (br(100 * r["top5"], 0) + "%").rjust(7)
            + str(r["seq_neg"]).rjust(5)
            + br(r["maxdd"], 0).rjust(9)
            + br(r["stop_rs"], 0).rjust(9)
            + br(r["alvo_rs"], 0).rjust(9)
            + (br(100 * r["alvo_pct"], 0) + "%").rjust(7)
            + (br(100 * r["win"], 1) + "%").rjust(7)
            + (br(100 * r["be"], 1) + "%").rjust(7)
            + r["veredito"].rjust(12)
            + (("  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"]))
               if r["sem_trade"] else "")
            + ("  ZEROU" if r["zerou"] else ""))


_HDR = ("alvo/stop/trail".ljust(16) + "liquido".rjust(12) + "ops".rjust(6)
        + "R$/dia".rjust(9) + "preg+".rjust(7) + "bl20+".rjust(7) + "mes+".rjust(7)
        + "top5".rjust(7) + "seq-".rjust(5) + "MaxDD".rjust(9)
        + "R$/stop".rjust(9) + "R$/alvo".rjust(9) + "alvo%".rjust(7)
        + "win%".rjust(7) + "BE%".rjust(7) + "veredito".rjust(12))


def main() -> None:
    tarefas = [(j, a, s, t) for j in ("IS", "OOS")
               for a in ALVOS for s in STOPS for t in TRAILS]
    print("grade de GEOMETRIA pontuada por CONSTANCIA -- rodada " + RODADA.upper()
          + ", capital R$ " + br(CAPITAL, 0))
    print(str(len(ALVOS)) + " alvos x " + str(len(STOPS)) + " stops x "
          + str(len(TRAILS)) + " trails x 2 janelas = " + str(len(tarefas))
          + " celulas")
    print("producao = a9,5 s12 toff\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print("[" + str(len(resultados)).rjust(3) + "/" + str(len(tarefas))
                  + "] " + r["janela"].ljust(4) + _rotulo(r).ljust(16)
                  + " liq " + br(r["liquido"]).rjust(11)
                  + "  bl20+ " + (br(100 * r["frac_bl"], 0) + "%").rjust(5)
                  + "  " + r["veredito"] + "  (" + str(round(r["dt"])) + "s)",
                  flush=True)

    for janela in ("IS", "OOS"):
        sub = [r for r in resultados if r["janela"] == janela]
        prod = [r for r in sub if r["alvo"] == 9.5 and r["stop"] == 12.0
                and r["trail"] is None]
        resto = sorted((r for r in sub if r not in prod),
                       key=lambda r: (-(r["frac_bl"] if r["frac_bl"] == r["frac_bl"] else -1),
                                      -r["liquido"]))
        print("\n\n===== " + janela + " -- ordenado por bl20+ (blocos rolantes "
              "de 20 pregoes positivos), depois liquido =====")
        print(_HDR)
        print("-" * len(_HDR))
        for r in prod:
            print(_linha(r) + "   <== PRODUCAO")
        for r in resto[:30]:
            print(_linha(r))

    # ---- o cruzamento IS x OOS: so' sobrevive quem passa nas DUAS ---------
    print("\n\n===== CRUZAMENTO IS x OOS (quem e' bom nas duas janelas) =====")
    chave = lambda r: (r["alvo"], r["stop"], r["trail"])
    is_ = {chave(r): r for r in resultados if r["janela"] == "IS"}
    oos = {chave(r): r for r in resultados if r["janela"] == "OOS"}
    linhas = []
    for k, a in is_.items():
        b = oos.get(k)
        if b is None:
            continue
        linhas.append((k, a, b))
    linhas.sort(key=lambda x: -(min(x[1]["frac_bl"], x[2]["frac_bl"])))
    hdr = ("alvo/stop/trail".ljust(16)
           + "IS liq".rjust(12) + "IS bl20+".rjust(10) + "IS win".rjust(8)
           + "IS BE".rjust(8) + "IS ver".rjust(12)
           + "OOS liq".rjust(12) + "OOS bl20+".rjust(11) + "OOS win".rjust(9)
           + "OOS BE".rjust(8) + "OOS ver".rjust(12) + "  pior bl20+".rjust(13))
    print(hdr)
    print("-" * len(hdr))
    for k, a, b in linhas[:35]:
        marca = "   <== PRODUCAO" if k == (9.5, 12.0, None) else ""
        print(_rotulo(a).ljust(16)
              + br(a["liquido"]).rjust(12)
              + (br(100 * a["frac_bl"], 0) + "%").rjust(10)
              + (br(100 * a["win"], 1) + "%").rjust(8)
              + (br(100 * a["be"], 1) + "%").rjust(8)
              + a["veredito"].rjust(12)
              + br(b["liquido"]).rjust(12)
              + (br(100 * b["frac_bl"], 0) + "%").rjust(11)
              + (br(100 * b["win"], 1) + "%").rjust(9)
              + (br(100 * b["be"], 1) + "%").rjust(8)
              + b["veredito"].rjust(12)
              + (br(100 * min(a["frac_bl"], b["frac_bl"]), 0) + "%").rjust(13)
              + marca)

    # ---- mapa do PLATO: bl20+ do IS em grade alvo x stop, por trail -------
    for tr in TRAILS:
        print("\n\n===== MAPA DO PLATO -- bl20+ no IS, trail="
              + ("off" if tr is None else br(tr, 0)) + " =====")
        print("alvo \\ stop".ljust(14) + "".join(
            ("s" + br(s, 0)).rjust(9) for s in STOPS))
        for a in ALVOS:
            fila = ("a" + br(a, 1)).ljust(14)
            for s in STOPS:
                r = is_.get((a, s, tr))
                fila += ((br(100 * r["frac_bl"], 0) + "%") if r else "--").rjust(9)
            print(fila)


if __name__ == "__main__":
    main()
