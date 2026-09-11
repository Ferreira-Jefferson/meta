# -*- coding: utf-8 -*-
"""Validacao do candidato `alvo_vol=7,6` do `copa_win` -- as quatro perguntas.

Pedido do dono, 2026-09-11: "ganhadora mesmo que pouco, mas constante".

DE ONDE VEIO O CANDIDATO. Tres rodadas de hoje, nesta ordem:

  1. `copawin_consistencia_diagnostico_2026_09_11.py` -- a producao JA ganha
     (+R$13.533,30 em 191 pregoes, 59% dos pregoes com operacao positivos,
     84% dos blocos rolantes de 20 pregoes positivos) e ja NAO depende mais do
     fechamento (o achatamento carrega 2% do liquido, contra 114,1% da config
     anterior). O desequilibrio que sobrou e' o TAMANHO do stop: -R$437,77 por
     stop contra +R$267,74 por alvo.
  2. `copawin_grade_constancia_2026_09_11.py` (120 + 32 celulas) -- os dois
     ajustes obvios para a cauda esquerda foram REFUTADOS: `trail_vol` ligado
     derruba o win% para 33-38% e cola no breakeven em 40 de 40 celulas;
     apertar `stop_vol` degrada monotonicamente, e s12 e' OMBRO (s14/s16/s20
     tambem pioram). Sobrou UM eixo vivo: `alvo_vol`.
  3. `copawin_robustez_por_data_de_inicio_2026_09_11.py` (912 simulacoes) --
     a pergunta do dono na forma medivel: "comecando em QUALQUER dia, em que
     fracao das datas eu termino positivo?". Horizonte fixo de 40 pregoes, 76
     datas de inicio:

         alvo   datas positivas   liq mediano   PIOR data de inicio
         6,65        71,1%          1.506,60        -2.862,00
         7,60       100,0%          2.941,70          +883,80
         8,55       100,0%          2.846,30          +302,90
         9,50 (prod) 89,5%          2.812,45          -888,40

     `7,60` e `8,55` sao PLATO, nao pico -- as duas celulas vizinhas dao 100%.
     E o ganho nao e' comprado com risco: o MaxDD mediano fica igual
     (R$1.664 contra R$1.702 da producao).

A MESMA RODADA REFUTOU O DIAL DE ESCALA: `risco_pct_por_trade` a 1%, 2% e 5%
devolve resultado praticamente IDENTICO (2.942 / 2.942 / 2.923 de liquido
mediano em `alvo=7,6`). No capital de R$3.000 a quantidade fica presa em 1
contrato pelo piso de `quantidade_por_entrada`, entao NAO EXISTE, hoje, um
botao de "ganhar menos e oscilar menos" -- o unico tamanho disponivel e' 1.

ESTE SCRIPT FAZ AS QUATRO PERGUNTAS QUE FALTAM antes de propor troca:

  A. O candidato ganha nas janelas congeladas, com as metricas de constancia
     lado a lado com a producao?
  B. Ele sobrevive a FILA? Esta e' a pergunta que mais importa e a que quase
     passou batido hoje de manha: alvo MENOR = mais saidas por ALVO = a
     premissa de preenchimento e' exercida MAIS. O WIN@ nao tem fidelidade
     calibrada (`backtest.intraday.fidelidade` so' tem WDO@), entao o unico
     uso honesto e' SENSIBILIDADE -- "a que nivel de fila o ganho morre?" --
     nunca previsao pontual. A escala e' o volume MEDIANO da barra M1, lido
     do proprio motor (`engine._bar_volume`), nunca digitado.
  C. Os freios que sobreviveram (`max_entradas_dia`, `perda_max_dia_pontos`)
     SOMAM com o alvo novo, ou o ganho de um e' o ganho do outro contado
     duas vezes?
  D. O que ele teria feito nas duas ultimas semanas -- a janela que o dono
     acabou de ver, e em que a producao perdeu R$1.081,50.

LIMITACAO QUE VIAJA JUNTO E NAO PODE SER APAGADA: o OOS do WIN@
(>=2026-06-13) ja foi gasto varias vezes, inclusive hoje. Nao existe teste
cego para este robo. O que sustenta o candidato e' (i) o plato na grade,
(ii) 100% das datas de inicio, que e' um teste de ROBUSTEZ e nao de cegueira,
e (iii) o mecanismo ser legivel (alvo mais perto do que a excursao mediana de
fato alcanca). Nao e' validacao fora da amostra, e nao deve ser vendida como
tal.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_candidato_a76_validacao_2026_09_11.py`
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
SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 3_000.0
OOS_INICIO = pd.Timestamp("2026-06-13").date()
DUAS_SEMANAS = pd.Timestamp("2026-09-01").date()
BLOCO = 20

#: Fila assumida na frente da ordem-limite do ALVO, em FRACAO do volume
#: MEDIANO da barra M1 do proprio WIN@ (lido do motor, nunca digitado). O
#: WIN@ NAO tem fidelidade calibrada -- isto e' sensibilidade, nao previsao.
FILAS_EM_BARRAS = [0.0, 0.25, 0.50, 1.00, 2.00, 4.00]

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


def _volume_mediano() -> float:
    """Volume MEDIANO da barra M1, pela MESMA regra do motor
    (`engine._bar_volume`: `real_volume` quando reportado, `tick_volume`
    senao). Redigitar a regra aqui produziria uma escala que nao e' a que o
    motor consome."""
    if "vol" not in _CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from backtest.intraday.engine import _bar_volume

        df, _ = _base()
        _CACHE["vol"] = float(df.apply(_bar_volume, axis=1).median())
    return _CACHE["vol"]


def _roda(janela: str, rotulo: str, kwargs: dict, fila_barras: float = 0.0):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    df, dias = _base()
    if janela == "IS":
        ds = [d for d in dias if d < OOS_INICIO]
    elif janela == "OOS":
        ds = [d for d in dias if d >= OOS_INICIO]
    elif janela == "2SEM":
        ds = [d for d in dias if d >= DUAS_SEMANAS]
    else:
        ds = list(dias)
    bars = df[[d in set(ds) for d in df.index.date]]

    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    for k, v in kwargs.items():
        setattr(strat, k, v)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0,
        exit_queue_ahead_qty=fila_barras * _volume_mediano(),
    )
    res = run_intraday_backtest(bars, strat, cfg)
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
    seq = pior_seq = 0
    for v in serie.values:
        if v < 0:
            seq += 1
            pior_seq = max(pior_seq, seq)
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
    liquido = sum(t.pnl_brl for t in trades)
    alvos = [t for t in trades if t.exit_reason.value == "target"]
    stops = [t for t in trades if t.exit_reason.value == "stop"]
    flat = sum(t.pnl_brl for t in trades if t.exit_reason.value == "forced_flatten")

    return dict(
        janela=janela, rotulo=rotulo, fila=fila_barras, liquido=liquido, n=n,
        pregoes=len(ds), sem_trade=len(ds) - len(com),
        frac_preg=(sum(1 for v in com if v > 0) / len(com)) if com else float("nan"),
        frac_bl=(sum(1 for b in blocos if b > 0) / len(blocos)) if blocos else float("nan"),
        frac_mes=(int((mes > 0).sum()) / len(mes)) if len(mes) else float("nan"),
        top5=(sum(ganhos_dia[:5]) / bruto) if bruto > 0 else float("nan"),
        seq_neg=pior_seq, pior_dia=float(serie.min()) if len(serie) else float("nan"),
        maxdd=dd, flat_share=(flat / liquido) if liquido else float("nan"),
        win=(len(g) / n) if n else float("nan"), be=be,
        veredito=(("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido")
                  if be == be and n else "--"),
        alvo_pct=(len(alvos) / n) if n else float("nan"),
        stop_rs=(sum(t.pnl_brl for t in stops) / len(stops)) if stops else float("nan"),
        alvo_rs=(sum(t.pnl_brl for t in alvos) / len(alvos)) if alvos else float("nan"),
        rs_op=(liquido / n) if n else float("nan"),
        zerou=(getattr(res, "wiped_out_at", None) is not None),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


_HDR = ("variante".ljust(26) + "liquido".rjust(12) + "ops".rjust(6)
        + "preg+".rjust(7) + "bl20+".rjust(7) + "mes+".rjust(7)
        + "top5".rjust(7) + "seq-".rjust(5) + "pior dia".rjust(11)
        + "MaxDD".rjust(9) + "flat$".rjust(7) + "alvo%".rjust(7)
        + "win%".rjust(7) + "BE%".rjust(7) + "veredito".rjust(12))


def _linha(r) -> str:
    return (r["rotulo"].ljust(26) + br(r["liquido"]).rjust(12) + str(r["n"]).rjust(6)
            + (br(100 * r["frac_preg"], 0) + "%").rjust(7)
            + (br(100 * r["frac_bl"], 0) + "%").rjust(7)
            + (br(100 * r["frac_mes"], 0) + "%").rjust(7)
            + (br(100 * r["top5"], 0) + "%").rjust(7)
            + str(r["seq_neg"]).rjust(5) + br(r["pior_dia"]).rjust(11)
            + br(r["maxdd"], 0).rjust(9)
            + (br(100 * r["flat_share"], 0) + "%").rjust(7)
            + (br(100 * r["alvo_pct"], 0) + "%").rjust(7)
            + (br(100 * r["win"], 1) + "%").rjust(7)
            + (br(100 * r["be"], 1) + "%").rjust(7)
            + r["veredito"].rjust(12)
            + (("  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"]))
               if r["sem_trade"] else "")
            + ("  ZEROU" if r["zerou"] else ""))


#: (rotulo, kwargs). Producao primeiro, sempre. `alvo_vol=7,6` veio da grade
#: de geometria; `entrada_ttl_barras` da varredura do filtro de entrada, e os
#: dois precisam ser lidos JUNTOS -- o teste por data de inicio
#: (`copawin_finalistas_robustez_2026_09_11.py`) mostrou que o prazo curto
#: SOZINHO, com o alvo antigo, chega a MATAR uma data de inicio (a9,5+ttl5:
#: 96,1% de datas positivas, pior inicio -R$2.992,50), enquanto o par
#: a7,6+ttl5/ttl8 fica em 100% com o pior inicio POSITIVO.
VARIANTES = [
    ("PRODUCAO (a9,5 ttl15)", {}),
    ("a7,6 ttl15", dict(alvo_vol=7.6)),
    ("a7,6 ttl5", dict(alvo_vol=7.6, entrada_ttl_barras=5)),
    ("a7,6 ttl8  <- CANDIDATO", dict(alvo_vol=7.6, entrada_ttl_barras=8)),
    ("a8,55 ttl8 (plato alvo)", dict(alvo_vol=8.55, entrada_ttl_barras=8)),
    ("a9,5 ttl8 (so o prazo)", dict(entrada_ttl_barras=8)),
    ("a7,6 ttl8 + perda R$900", dict(alvo_vol=7.6, entrada_ttl_barras=8,
                                     perda_max_dia_pontos=300.0)),
]


def main() -> None:
    vmed = _volume_mediano()
    print("validacao do candidato alvo_vol=7,6 -- capital R$ " + br(CAPITAL, 0)
          + ", stop_vol 12,0, trail DESLIGADO")
    print("volume MEDIANO da barra M1 do WIN@: " + br(vmed, 0)
          + " contratos (escala da sensibilidade de fila)\n", flush=True)

    tarefas = [(j, rot, kw, 0.0) for j in ("TUDO", "IS", "OOS", "2SEM")
               for rot, kw in VARIANTES]
    tarefas += [("TUDO", rot, kw, f)
                for rot, kw in (VARIANTES[0], VARIANTES[3])
                for f in FILAS_EM_BARRAS if f]

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print("[" + str(len(resultados)).rjust(2) + "/" + str(len(tarefas))
                  + "] " + r["janela"].ljust(5) + r["rotulo"].ljust(26)
                  + " fila " + br(r["fila"], 2).rjust(5)
                  + "  liq " + br(r["liquido"]).rjust(11)
                  + "  " + r["veredito"], flush=True)

    ordem = [rot for rot, _ in VARIANTES]
    rotulos = {"TUDO": "A. HISTORICO INTEIRO (191 pregoes)",
               "IS": "A. IS (< 2026-06-13)",
               "OOS": "A. OOS (>= 2026-06-13) -- JA GASTO, so' pode reprovar",
               "2SEM": "D. AS DUAS ULTIMAS SEMANAS (01/09 a 10/09)"}
    for janela in ("TUDO", "IS", "OOS", "2SEM"):
        sub = {r["rotulo"]: r for r in resultados
               if r["janela"] == janela and not r["fila"]}
        print("\n\n===== " + rotulos[janela] + " =====")
        print(_HDR)
        print("-" * len(_HDR))
        for rot in ordem:
            if rot in sub:
                print(_linha(sub[rot])
                      + ("   <== PRODUCAO" if rot.startswith("PRODUCAO") else ""))

    # ---- B. a fila: a que nivel o ganho morre ----------------------------
    print("\n\n===== B. SENSIBILIDADE A FILA NA SAIDA POR ALVO "
          "(historico inteiro) =====")
    print("o WIN@ NAO tem fila calibrada -- isto responde 'a que nivel o ganho"
          " morre?', nunca 'quanto vai render'")
    print("fila em FRACAO do volume mediano da barra M1 (" + br(vmed, 0)
          + " contratos)\n")
    hdr = ("fila (x barra)".ljust(16) + "contratos".rjust(11)
           + "PRODUCAO a9,5".rjust(16) + "alvo%".rjust(8)
           + "CANDIDATO a7,6 ttl8".rjust(21) + "alvo%".rjust(8)
           + "diferenca".rjust(13))
    print(hdr)
    print("-" * len(hdr))
    for f in FILAS_EM_BARRAS:
        a = next((r for r in resultados if r["janela"] == "TUDO"
                  and r["rotulo"].startswith("PRODUCAO") and r["fila"] == f), None)
        b = next((r for r in resultados if r["janela"] == "TUDO"
                  and r["rotulo"].startswith("a7,6 ttl8 ") and r["fila"] == f), None)
        if a is None or b is None:
            continue
        print((br(f, 2) + "x").ljust(16) + br(f * vmed, 0).rjust(11)
              + br(a["liquido"]).rjust(16)
              + (br(100 * a["alvo_pct"], 0) + "%").rjust(8)
              + br(b["liquido"]).rjust(21)
              + (br(100 * b["alvo_pct"], 0) + "%").rjust(8)
              + br(b["liquido"] - a["liquido"]).rjust(13))


if __name__ == "__main__":
    main()
