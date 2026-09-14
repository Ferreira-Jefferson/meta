# -*- coding: utf-8 -*-
"""O acerto de ~88% do alvo fino sobrevive a uma FILA de verdade?

Complemento obrigatorio de `copawin_300_reais_acerto_90_2026_09_13.py`
(rodada `fino`), 2026-09-13.

O QUE A GRADE FINA ACHOU, e por que ela nao pode ser lida sozinha. Encolhendo
`alvo_vol` de 7,6 para 0,08 -- ate **2,6 ticks REAIS** do WINV26, encostando
no piso de executabilidade de 2 ticks -- a taxa de acerto sobe de 57,0% para
**88,2% (IS)** / **88,6% (OOS)**. Nunca chega a 90%, e ja' isso responde o
pedido. Mas o numero de 88% tem uma dependencia que precisa ser exposta:

    ELE E' INTEIRAMENTE UM NUMERO DE PREENCHIMENTO, NAO DE DIRECAO.

O que faz o acerto subir de 57% para 88% nao e' o robo prever melhor -- e' o
alvo ficar tao perto que quase toda operacao o alcanca. E "alcancar" aqui
significa que uma ordem-limite MINHA, parada a 2,6 ticks do preco de entrada,
foi preenchida. O WIN@ **nao tem fidelidade de execucao calibrada**
(`backtest.intraday.fidelidade` so' tem WDO@), entao o motor assume
`queue_ahead_qty=0` e `exit_queue_ahead_qty=0`: toda limite minha preenche no
PRIMEIRO TOQUE do nivel, dos dois lados.

Este e' literalmente o erro que o repo ja pagou. No WDO@, antes da calibracao
de 2026-09-09, o motor com fila zero previa **+R$3,82 por operacao num dia que
deu −R$3,00** e 97,8% de fill num dia que deu 33,3% -- errou o SINAL, nao a
margem. E quanto mais perto o alvo esta' do preco de entrada, mais o resultado
depende justamente da premissa nao calibrada: um nivel a 2,6 ticks e' dos mais
disputados do livro.

O QUE ESTE SCRIPT FAZ. Pega as geometrias de alvo fino que a grade premiou e
varre `queue_ahead_qty`/`exit_queue_ahead_qty` em MULTIPLOS do volume mediano
da barra M1 do WIN@ (24.955 contratos), medindo quanto do acerto e do liquido
sobra. Ver o comentario de `FILAS` para por que a escala e' essa e nao a do
WDO@ -- a primeira versao deste script varreu 0..2.000 contratos e devolveu
eixo MORTO, porque nessa escala a fila e' engolida pelo primeiro toque.

A producao (a7,6) entra como controle: se ela degrada MENOS que o alvo fino,
isso mostra que a fragilidade e' propriedade da geometria fina, e nao um
efeito generico de "fila derruba tudo".

Uso:
    .venv/Scripts/python.exe -u scripts/daytrade/copawin_300_alvo_fino_sensibilidade_fila_2026_09_13.py
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
CAPITAL = 300.0
OOS_INICIO = pd.Timestamp("2026-06-13").date()
TICK_REAL_PONTOS = 5.0

#: As duas geometrias de alvo fino com maior acerto medido, mais a producao
#: como CONTROLE (alvo 46x maior -- se a fila derruba as duas igual, o efeito
#: e' generico; se derruba so' a fina, e' a geometria).
GEOMETRIAS = [(0.08, 20.0), (0.15, 20.0), (7.6, 12.0)]

#: Contratos na FRENTE da minha ordem, no nivel dela.
#:
#: A ESCALA FOI CORRIGIDA DEPOIS DA PRIMEIRA RODADA, e o erro vale registrar
#: porque e' o eixo-morto do item 6.25 acontecendo ao vivo. A primeira versao
#: varreu 0..2.000 contratos -- por analogia com o WDO@, cuja calibracao real
#: deu 438/489 -- e devolveu numeros IDENTICOS em todas as celulas, ate 2.000.
#: Nao era robustez: e' que o motor consome a fila com o `bar.volume` da
#: barra, e a barra M1 do WIN@ tem volume MEDIANO de **24.955 contratos**
#: (p10 8.063, p90 63.511, coluna `real_volume`, que e' a que
#: `engine._volume_da_barra` usa). Uma fila de 2.000 e' engolida pelo primeiro
#: toque de qualquer barra. Fila do WIN@ nao se mede na escala do WDO@.
#:
#: Entao os niveis sao MULTIPLOS do volume mediano da barra -- 0x, 0,25x,
#: 0,5x, 1x, 2x, 4x -- que e' a mesma escala de
#: `copawin_candidato_a76_validacao_2026_09_11.py`.
#:
#: A LIMITACAO QUE SOBRA, e que nenhum destes numeros resolve: `bar.volume` e'
#: o volume do minuto inteiro em TODOS os precos, nao o volume NO MEU NIVEL. O
#: estudo de tape (`win_fila_real_por_tape_2026_09_11.py`) mede volume-ao-
#: preco, que e' a grandeza certa, e o motor M1 nao enxerga essa coluna. Ou
#: seja: mesmo a coluna `fila 4x` aqui continua sendo otimista.
VOL_BARRA_MEDIANO = 24_955.0
FILAS = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0]

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


def _roda(janela: str, alvo: float, stop: float, fila: float):
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

    vols: list[float] = []
    orig = strat._entrada

    def espiao(lado, preco, nivel, vol):
        vols.append(float(vol))
        return orig(lado, preco, nivel, vol)

    strat._entrada = espiao

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=fila * VOL_BARRA_MEDIANO,
        exit_queue_ahead_qty=fila * VOL_BARRA_MEDIANO,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    dias_com = {t.exit_ts.date() for t in trades}
    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    eq = res.equity_curve
    cmin = float(eq.min()) if eq is not None and not eq.empty else CAPITAL
    alvos = [t for t in trades if t.exit_reason.value == "target"]
    vol_med = float(pd.Series(vols).median()) if vols else float("nan")

    return dict(
        janela=janela, alvo=alvo, stop=stop, fila=fila, dt=dt,
        liquido=sum(t.pnl_brl for t in trades), n=n,
        pregoes=len(ds), sem_trade=len(ds) - len(dias_com),
        win=(len(g) / n) if n else float("nan"), be=be, lo=lo, hi=hi,
        veredito=(("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido")
                  if be == be and n else "--"),
        caixa_min=cmin,
        zerou=(getattr(res, "wiped_out_at", None) is not None),
        alvo_pct=(len(alvos) / n) if n else float("nan"),
        alvo_tk=(alvo * vol_med / TICK_REAL_PONTOS) if vol_med == vol_med else float("nan"),
        armadas=len(vols),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def _linha(r) -> str:
    return ((br(r["fila"], 2) + "x").rjust(8)
            + (br(100 * r["win"], 1) + "%").rjust(9)
            + (br(100 * r["be"], 1) + "%").rjust(9)
            + br(r["liquido"]).rjust(12)
            + str(r["n"]).rjust(7)
            + (br(100 * r["alvo_pct"], 1) + "%").rjust(9)
            + br(r["caixa_min"], 0).rjust(10)
            + r["veredito"].rjust(12)
            + (("  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"]))
               if r["sem_trade"] else "")
            + ("  ZEROU" if r["zerou"] else ""))


_HDR = ("fila".rjust(8) + "win%".rjust(9) + "BE emp".rjust(9)
        + "liquido".rjust(12) + "ops".rjust(7) + "saiu alvo".rjust(9)
        + "caixa min".rjust(10) + "veredito".rjust(12))


def main() -> None:
    tarefas = [(j, a, s, f) for j in ("IS", "OOS")
               for a, s in GEOMETRIAS for f in FILAS]
    print("o acerto do alvo fino sobrevive a fila? -- capital R$ "
          + br(CAPITAL, 0))
    print(str(len(GEOMETRIAS)) + " geometrias x " + str(len(FILAS))
          + " filas x 2 janelas = " + str(len(tarefas)) + " celulas")
    print("fila = contratos na FRENTE da minha limite, no nivel dela. "
          "O motor do WIN@ hoje assume 0.")
    print("referencia externa: tape do WIN@ empata com o teto em ~500; "
          "WDO@ calibrado da' 438/489.\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print("[" + str(len(resultados)).rjust(3) + "/" + str(len(tarefas))
                  + "] " + r["janela"].ljust(4)
                  + ("a" + br(r["alvo"], 2) + " fila " + br(r["fila"], 2) + "x").ljust(20)
                  + " win " + (br(100 * r["win"], 1) + "%").rjust(6)
                  + "  liq " + br(r["liquido"]).rjust(11)
                  + "  " + r["veredito"] + "  (" + str(round(r["dt"])) + "s)",
                  flush=True)

    for a, s in GEOMETRIAS:
        sub = [r for r in resultados if r["alvo"] == a and r["stop"] == s]
        tk = next((r["alvo_tk"] for r in sub if r["alvo_tk"] == r["alvo_tk"]),
                  float("nan"))
        rot = ("alvo " + br(a, 2) + " / stop " + br(s, 0)
               + "   (alvo mediano = " + br(tk, 1) + " ticks reais)")
        print("\n\n===== " + rot
              + ("   <== PRODUCAO" if (a, s) == (7.6, 12.0) else "") + " =====")
        for janela in ("IS", "OOS"):
            print("\n  " + janela + " (" + str(next(r["pregoes"] for r in sub
                                                    if r["janela"] == janela))
                  + " pregoes)")
            print("  " + _HDR)
            print("  " + "-" * len(_HDR))
            for r in sorted((x for x in sub if x["janela"] == janela),
                            key=lambda x: x["fila"]):
                print("  " + _linha(r))

    print("\n\n===== quanto do resultado sobrevive a fila de 500 =====")
    print("geometria".ljust(22) + "janela".rjust(7)
          + "liq fila 0".rjust(13) + "liq fila 500".rjust(14)
          + "retencao".rjust(10) + "win 0".rjust(8) + "win 500".rjust(9))
    print("-" * 83)
    for a, s in GEOMETRIAS:
        for janela in ("IS", "OOS"):
            z = next((r for r in resultados if r["alvo"] == a and r["stop"] == s
                      and r["janela"] == janela and r["fila"] == 0.0), None)
            q = next((r for r in resultados if r["alvo"] == a and r["stop"] == s
                      and r["janela"] == janela and r["fila"] == 1.0), None)
            if not z or not q:
                continue
            ret = (q["liquido"] / z["liquido"]) if z["liquido"] else float("nan")
            print(("a" + br(a, 2) + " s" + br(s, 0)).ljust(22) + janela.rjust(7)
                  + br(z["liquido"]).rjust(13) + br(q["liquido"]).rjust(14)
                  + ((br(100 * ret, 0) + "%") if ret == ret else "--").rjust(10)
                  + (br(100 * z["win"], 1) + "%").rjust(8)
                  + (br(100 * q["win"], 1) + "%").rjust(9))


if __name__ == "__main__":
    main()
