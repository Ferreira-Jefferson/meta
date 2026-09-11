# -*- coding: utf-8 -*-
"""Piso de capital REAL da config de producao do `copa_win` (WIN@).

Refaz, pelo metodo certo, a conta que gerou os R$600 de
`CopaWin.capital_minimo_recomendado_brl` em 2026-09-11.

POR QUE REFAZER. O R$600 saiu de "margem crua (R$100) + pior queda medida
(R$226,90)". Os R$226,90 vieram de rodar o robo com capital de R$250 e ler
`capital - equity_minima` -- e uma conta de R$250 NAO CONSEGUE SOFRER a queda
da estrategia: ela quebra antes, o portao de capital passa a recusar
entradas, e o que se mede e' a queda de uma conta que morreu cedo. Janela
censurada dimensionando capital, que e' o pior lugar possivel para ela.

A segunda tentativa tambem nao serve, e por outro motivo: medir a queda com
1 CONTRATO FIXO (deu R$2.892,70 de maxima em 191 pregoes) descreve uma
estrategia que a producao nao roda -- a producao ESCALA contratos com o caixa
(`margin_per_contract_brl` + `risco_pct_por_trade`). Uma conta maior nao
enfrenta a mesma queda em reais: ela abre mais contratos e a queda cresce
junto. Piso nao se deriva de uma queda medida num tamanho, porque o tamanho e'
funcao do proprio capital.

O QUE DECIDE E' SOBREVIVENCIA, nao aritmetica: rodar a config de PRODUCAO,
com o dimensionamento dela, em passada CRONOLOGICA continua (o caixa de um
pregao e' o que sobrou do anterior), em varios niveis de capital, e ver quais
atravessam o historico inteiro sem quebrar e sem travar. E' a metodologia de
`copawin_piso_sobrevivencia_2026_08_29.py`, aplicada a config nova.

CRITERIO (declarado antes de rodar):
  1. nunca zerar (`wiped_out_at is None`);
  2. 0 pregoes sem trade -- pregao pulado por capital e' o robo calado, e a
     partir do primeiro ele costuma nunca mais voltar (item 1.14/3.10/3.11);
  3. caixa minimo acima da MARGEM CRUA (R$100), que e' o piso de
     SOBREVIVENCIA do WIN@;
  4. e, para o piso RECOMENDADO (nao o minimo absoluto), folga: o menor
     nivel que passa 1-3 com sobra confortavel, nao o que passa raspando --
     191 pregoes nao esgotam o que o mercado faz.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_piso_capital_producao_2026_09_11.py`
"""
from __future__ import annotations

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
MARGEM_CRUA = 100.0
NIVEIS = [600.0, 1_000.0, 1_500.0, 2_000.0, 2_500.0, 3_000.0, 4_000.0,
          5_000.0, 7_500.0, 10_000.0]

_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _bars():
    if "b" not in _CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        _CACHE["b"] = df[[d in completos for d in df.index.date]]
    return _CACHE["b"]


def _roda(capital: float):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars()
    strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(res.trades)
    pregoes = len(set(pd.DatetimeIndex(bars.index).date))
    com = len({t.entry_ts.date() for t in trades})
    eq = res.equity_curve
    cmin = float(eq.min()) if eq is not None and not eq.empty else capital
    queda = float((eq.cummax() - eq).max()) if eq is not None and not eq.empty else 0.0
    zerou = getattr(res, "wiped_out_at", None)
    qtds = sorted({t.quantity for t in trades})
    passa = (zerou is None and (pregoes - com) == 0 and cmin > MARGEM_CRUA)
    return dict(
        capital=capital, trades=len(trades), liquido=sum(t.pnl_brl for t in trades),
        sem_trade=pregoes - com, pregoes=pregoes, caixa_min=cmin, queda=queda,
        zerou=zerou, qtd_min=(qtds[0] if qtds else 0), qtd_max=(qtds[-1] if qtds else 0),
        passa=passa, dt=dt,
    )


def _unidade(cap):
    buf = StringIO()
    with redirect_stdout(buf):
        return _roda(cap)


def main() -> None:
    print("config de PRODUCAO (alvo_vol=9,5, alvo por ordem-limite real, "
          "dimensionamento por margem + risco)", flush=True)
    print("passada CRONOLOGICA continua, historico completo\n", flush=True)

    resultados = []
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, c): c for c in NIVEIS}
        for fut in as_completed(futs):
            r = fut.result()
            resultados.append(r)
            print("  " + br(r["capital"], 0).rjust(9) + " concluido ("
                  + str(round(r["dt"])) + "s)", flush=True)

    resultados.sort(key=lambda r: r["capital"])
    print()
    hdr = ("capital".rjust(9) + "trades".rjust(8) + "s/trade".rjust(9)
           + "liquido".rjust(13) + "caixa min".rjust(11) + "queda max".rjust(11)
           + "contratos".rjust(11) + "zerou".rjust(8) + "  criterio")
    print(hdr); print("-" * len(hdr))
    for r in resultados:
        print(br(r["capital"], 0).rjust(9) + str(r["trades"]).rjust(8)
              + (str(r["sem_trade"]) + "/" + str(r["pregoes"])).rjust(9)
              + br(r["liquido"]).rjust(13) + br(r["caixa_min"]).rjust(11)
              + br(r["queda"]).rjust(11)
              + (str(r["qtd_min"]) + "-" + str(r["qtd_max"])).rjust(11)
              + ("SIM" if r["zerou"] else "nao").rjust(8)
              + "  " + ("PASSA" if r["passa"] else "falha"))

    passam = [r for r in resultados if r["passa"]]
    print()
    if not passam:
        print("NENHUM nivel testado passa o criterio.")
        return
    menor = passam[0]
    print("menor nivel que PASSA: R$ " + br(menor["capital"], 0)
          + " (caixa minimo R$ " + br(menor["caixa_min"])
          + ", queda maxima R$ " + br(menor["queda"]) + ")")
    print()
    print("FOLGA de cada nivel que passa -- quanto do caixa inicial a pior")
    print("queda ja' consumiu. Quanto MAIOR a folga, mais longe da parede:")
    print("  capital".rjust(11) + "queda/capital".rjust(16) + "sobra no vale".rjust(16))
    for r in passam:
        print(br(r["capital"], 0).rjust(11)
              + (br(100 * r["queda"] / r["capital"], 1) + "%").rjust(16)
              + br(r["caixa_min"]).rjust(16))


if __name__ == "__main__":
    main()
