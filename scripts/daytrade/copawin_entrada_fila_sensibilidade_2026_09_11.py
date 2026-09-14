# -*- coding: utf-8 -*-
"""Sensibilidade mecanica da fila de ENTRADA do `copa_win` (WIN@) -- a metade
que o item 6.30 de LICOES_DE_PRODUCAO.md deixou explicitamente em aberto
("a fila da SAIDA nao morde; a fila da ENTRADA ainda nao foi medida").

## Por que isto e SENSIBILIDADE, e nao CALIBRACAO

`scripts/daytrade/copawin_calibra_fila_entrada_real_2026_09_11.py` tentou
reconstruir a fila real de ENTRADA a partir do terminal MT5 (mesmo metodo
Kaplan-Meier do WDO@) e devolveu n=0: o `copa_win` nunca rodou
`execution_mode=live` no WIN@ (so' sombra, que por desenho nao manda ordem
para o book -- ver aquele script para o detalhe). Sem ordem real, nao ha'
Q_frente para medir, e `backtest.intraday.fidelidade.FIDELIDADE` continua
sem entrada para "WIN@" -- corretamente, porque inventar um numero
(emprestar do WDO@, chutar) seria o erro que aquele modulo foi desenhado
para impedir.

O que ESTE script faz e' a pergunta que MEDE, mesmo sem a calibracao real:
"dado o tamanho da ordem de entrada, o tempo que ela espera, e o GIRO real
do WIN@, existe algum nivel PLAUSIVEL de fila que mudaria o resultado?" --
a mesma pergunta e o mesmo metodo do item 6.30 (fracao do volume da barra M1
mediana + teste de sanidade em valor absurdo), aplicados ao lado da ENTRADA
em vez do lado da SAIDA.

## A diferenca mecanica que faz a pergunta valer a pena perguntar de novo

O item 6.30 mediu a SAIDA (posicao aberta por HORAS -- mediana 184 barras
M1 medida ao vivo) e achou que a fila so' morde a partir de 250.000
contratos, muito acima do giro plausivel. A ENTRADA e' estruturalmente
DIFERENTE: `entrada_ttl_barras=5` (item 6.33 da producao) -- a ordem espera
no MAXIMO 5 barras M1, nao horas. Em 5 minutos a 24.962 contratos/minuto
(volume mediano da barra do WIN@, mesma regra do motor,
`engine._bar_volume`) o orcamento de volume disponivel para consumir a fila
e' ~124.810 contratos -- MENOR que o giro que uma posicao de horas ve, e por
isso a conclusao do 6.30 ("giro gigante, fila irrelevante") NAO pode ser
copiada sem medir: e' exatamente o erro que o proprio 6.30 nomeia ("nao
generaliza entre instrumentos" -- aqui o eixo que muda e' o TEMPO de espera,
dentro do MESMO instrumento).

## Teste pequeno primeiro

Roda primeiro numa janela de ~20 pregoes recentes (rapido, poucos segundos
por celula). So' expande para o historico IS/OOS completo (191 pregoes,
corte em 2026-06-13) se a janela pequena mostrar QUALQUER sensibilidade --
convencao do projeto ("o minimo que refuta primeiro").

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_entrada_fila_sensibilidade_2026_09_11.py`
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
PREGOES_JANELA_PEQUENA = 20

CAPITAIS = [250.0, 3_000.0]
#: fila na frente da nossa ordem-limite de ENTRADA, em FRACAO do volume da
#: barra M1 mediana do WIN@ (mesma escala do item 6.30). `SANIDADE` e' o
#: teste de wiring do 6.30 (a 25 milhoes o acerto tem de zerar, senao o
#: modelo nao esta ligado).
FILAS_EM_BARRAS = [0.0, 0.10, 0.25, 0.50, 1.00, 2.00, 5.00]
SANIDADE_BARRAS = 1000.0  # ~25 milhoes de contratos, mesma ordem do 6.30
EXTRAS = ("entrada c/ fill", "s/trade", "caixa min")

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
        if janela == "PEQUENA":
            dias = sorted(set(df.index.date))[-PREGOES_JANELA_PEQUENA:]
            df = df[[d in set(dias) for d in df.index.date]]
        elif janela == "IS":
            df = df[[d < OOS_INICIO for d in df.index.date]]
        else:
            df = df[[d >= OOS_INICIO for d in df.index.date]]
        _BARS_CACHE[janela] = df
    return _BARS_CACHE[janela]


def _roda(janela: str, capital: float, fila_barras: float):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars(janela)
    # PRODUCAO, sem sobrescrever nenhum parametro de estrategia -- so' a
    # fila muda nesta varredura. `get_daytrade_robot` resolve os kwargs
    # oficiais do catalogo (`_KWARGS_PADRAO`, registry.py).
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    fila_qtd = fila_barras * _volume_mediano()

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=fila_qtd,
        # SAIDA fica de fora de proposito -- o item 6.30 ja' mediu que ela
        # nao morde ate 2x a barra mediana, e o objetivo aqui e' isolar
        # SO' o efeito da ENTRADA. Declarado explicito, nunca herdado.
        exit_queue_ahead_qty=0.0,
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
    stops = sum(1 for t in trades if t.exit_reason.value == "stop")

    pregoes = len(set(pd.DatetimeIndex(bars.index).date))
    com = len({t.entry_ts.date() for t in trades})
    eq = res.equity_curve
    caixa_min = float(eq.min()) if eq is not None and not eq.empty else capital
    maxdd_pct = (float((eq.cummax() - eq).max() / eq.cummax().max()) * 100.0
                 if eq is not None and not eq.empty and eq.cummax().max() > 0 else 0.0)

    rot = "sanidade(1000x)" if fila_barras == SANIDADE_BARRAS else br(fila_barras, 2) + "x barra"
    nome = "fila entrada " + rot
    linha = linha_de_resultado(
        janela + " " + br(capital, 0) + " " + nome, res, capital,
        extras={
            "entrada c/ fill": br(100 * n / max(1, com), 1) + "%" if com else "--",
            "s/trade": str(pregoes - com) + "/" + str(pregoes),
            "caixa min": br(caixa_min),
        },
    )
    return dict(
        janela=janela, capital=capital, fila_barras=fila_barras, fila_qtd=fila_qtd,
        nome=nome, linha=linha, dt=dt, n=n, stops=stops,
        win=(len(ganhos) / n if n else 0.0), be=be, lo=lo, hi=hi,
        liquido=sum(t.pnl_brl for t in trades),
        sem_trade=pregoes - com, pregoes=pregoes, caixa_min=caixa_min,
        maxdd_pct=maxdd_pct,
        veredito=("POSITIVO" if (n and lo > be) else
                  "NEGATIVO" if (n and hi < be) else "indefinido"),
    )


def _unidade(args):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(*args)


def _imprime_bloco(resultados, tarefas, titulo):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import tabela

    print("\n\n===== " + titulo + " =====", flush=True)
    for janela in sorted({t[0] for t in tarefas}):
        for capital in CAPITAIS:
            sel = [r for r in resultados if r["janela"] == janela and r["capital"] == capital]
            sel.sort(key=lambda r: r["fila_barras"])
            if not sel:
                continue
            print("\n--- " + janela + " - capital R$ " + br(capital, 0) + " ---", flush=True)
            print(tabela([r["linha"] for r in sel], extras=EXTRAS), flush=True)


def _roda_bloco(tarefas, titulo):
    resultados = []
    print(f"\n{len(tarefas)} celulas -- {titulo}", flush=True)
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            be = br(100 * r["be"], 1) if r["be"] == r["be"] else "--"
            print("[" + str(len(resultados)).rjust(2) + "/" + str(len(tarefas)) + "] "
                  + r["janela"].rjust(7) + " cap " + br(r["capital"], 0).rjust(8) + " "
                  + r["nome"].ljust(24)
                  + " liq " + br(r["liquido"]).rjust(12)
                  + "  n=" + str(r["n"]).ljust(5)
                  + " win " + (br(100 * r["win"], 1) + "%").rjust(6)
                  + " BE " + (be + "%").rjust(6)
                  + " stops " + str(r["stops"]).rjust(3)
                  + " maxdd " + (br(r["maxdd_pct"], 1) + "%").rjust(7)
                  + "  s/trade " + str(r["sem_trade"]) + "/" + str(r["pregoes"])
                  + "  " + r["veredito"] + "  (" + str(round(r["dt"])) + "s)", flush=True)
    _imprime_bloco(resultados, tarefas, titulo)
    return resultados


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))

    vmed = _volume_mediano()
    print("volume da barra M1 MEDIANA do WIN@: " + br(vmed, 0) + " contratos", flush=True)
    print("entrada_ttl_barras (producao) = 5 -- orcamento max de volume "
          "disponivel para a fila ~= 5x a barra mediana = "
          + br(5 * vmed, 0) + " contratos", flush=True)
    print("degraus varridos (fila na frente da ENTRADA):", flush=True)
    for f in FILAS_EM_BARRAS + [SANIDADE_BARRAS]:
        rot = "SANIDADE" if f == SANIDADE_BARRAS else (br(f, 2) + "x barra")
        print("   " + rot.rjust(12) + " = " + br(f * vmed, 0).rjust(12) + " contratos", flush=True)
    print(flush=True)

    # ---- FASE 1: janela pequena, teste que refuta primeiro -----------
    tarefas_pequena = [("PEQUENA", c, f) for c in CAPITAIS
                       for f in FILAS_EM_BARRAS + [SANIDADE_BARRAS]]
    res_pequena = _roda_bloco(tarefas_pequena,
                              f"FASE 1 -- janela PEQUENA ({PREGOES_JANELA_PEQUENA} pregoes recentes)")

    # A pergunta de decisao: o veredito ou o liquido MUDAM entre fila=0 e a
    # maior fila plausivel (5x)? Se NAO, ainda roda o sanidade (que TEM que
    # mudar, senao o wiring esta quebrado) e para -- expandir para IS/OOS
    # completo sem sinal nenhum na janela pequena seria gastar CPU numa
    # pergunta ja respondida (convencao "teste pequeno primeiro").
    muda_plausivel = False
    for capital in CAPITAIS:
        base = next((r for r in res_pequena if r["capital"] == capital and r["fila_barras"] == 0.0), None)
        topo = next((r for r in res_pequena if r["capital"] == capital and r["fila_barras"] == 5.00), None)
        if base and topo:
            dif_liq = abs(topo["liquido"] - base["liquido"])
            dif_n = abs(topo["n"] - base["n"])
            print(f"\ncapital R$ {br(capital, 0)}: liquido fila=0 -> {br(base['liquido'])}  "
                  f"fila=5x -> {br(topo['liquido'])}  (dif R$ {br(dif_liq)}, dif n trades {dif_n})",
                  flush=True)
            if dif_n > 0 or dif_liq > 0.01:
                muda_plausivel = True

    sanidade_ok = any(r["fila_barras"] == SANIDADE_BARRAS and r["n"] == 0 for r in res_pequena) or \
        any(r["fila_barras"] == SANIDADE_BARRAS and r["n"] < min(
            (x["n"] for x in res_pequena if x["fila_barras"] == 0.0 and x["capital"] == r["capital"]),
            default=0)
            for r in res_pequena if r["fila_barras"] == SANIDADE_BARRAS)
    print(f"\nteste de sanidade (fila absurda reduz/zera trades, prova que o "
          f"modelo esta LIGADO): {'PASSOU' if sanidade_ok else 'FALHOU -- investigar wiring'}",
          flush=True)

    if not muda_plausivel:
        print("\n" + "=" * 74)
        print("NENHUM nivel PLAUSIVEL de fila (ate 5x a barra mediana, "
              f"{br(5 * vmed, 0)} contratos) mudou trade nenhum na janela pequena.")
        print("Nao expandindo para IS/OOS completo -- a pergunta ja esta' respondida")
        print("aqui: o orcamento de volume em 5 barras (ttl da entrada) e' grande")
        print("demais para o WIN@ para qualquer fila plausivel morder.")
        print("=" * 74)
        return

    # ---- FASE 2: so' roda se a fase 1 mostrou QUALQUER sensibilidade --
    tarefas_full = [(j, c, f) for j in ("IS", "OOS") for c in CAPITAIS
                    for f in FILAS_EM_BARRAS + [SANIDADE_BARRAS]]
    _roda_bloco(tarefas_full, "FASE 2 -- historico completo (IS+OOS, 191 pregoes)")


if __name__ == "__main__":
    main()
