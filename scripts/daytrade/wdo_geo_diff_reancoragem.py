"""Frente F4-wdo-geometria-sessao, RODADA 2, bloco (B) -- resolve a
divergencia de 5x-25x entre `WdoGeoGridRolling` (este arquivo compara F4) e
`WdoGridReloadReancoragem` (F2) apontada pelo critico da rodada 1: as duas
implementacoes do "mesmo" desenho (T1/S16/espacamento~1 tick/reancoragem
rolante a cada 1 barra parada) divergem de +R$62.226,48 (F4) para
+R$2.575~3.069 no melhor achado de F2 (com `reanchor_after_bars=1`
especificamente, F2 deu -R$1.525,62).

METODO (pedido explicito do critico): pega 1 pregao concreto do IS, roda as
DUAS implementacoes com os MESMOS parametros (T=1, S=16, espacamento=1 tick,
reanchor/rolling_reanchor_after_bars=1, quantity=1, pedagio=0 -- isto e' um
diagnostico de MECANICA, nao de sobrevivencia a custo, que ja foi respondida
em rodada 1: 0/15 sobrevivem a pedagio de qualquer forma) e diffa
TRADE A TRADE (timestamp de armamento, preco do nivel, timestamp de
reancoragem).

ACHADO ANALITICO (derivado lendo o codigo-fonte das duas classes ANTES de
rodar nada, depois confirmado empiricamente abaixo): as duas leem o MESMO
parametro nominal `N=1` ("reancora depois de N barras paradas") com
semanticas DIFERENTES, por causa de ONDE o `if` de estagnacao fica em
relacao ao incremento do contador:

* `WdoGridReloadReancoragem._SessionState.pending_bars_waited` (F2):
  INCREMENTA primeiro, decide depois (`waited += 1; if waited < N: espera
  else: reancora`). Para N=1: no primeiro `on_bar` depois do armamento,
  `waited` vai de 0 para 1, e `1 < 1` e' Falso -- reancora IMEDIATAMENTE
  nessa mesma chamada. A ordem teve UMA UNICA barra de chance de tocar
  (a barra em que foi armada mais a barra seguinte, onde o motor confere o
  toque ANTES do robo decidir reancorar -- ver `IntradaySessionMachine.
  on_closed_bar`, secao "(3b)" roda antes da secao "(5)" na MESMA chamada).

* `WdoGeoGridRolling._SessionState.pending_bars_waited` (F4, esta frente):
  DECIDE primeiro, incrementa depois (`stale = waited >= N; if not stale:
  waited += 1; else: reancora`). Para N=1: na primeira chamada depois do
  armamento, `stale = 0 >= 1` e' Falso -- so' incrementa (`waited=1`), SEM
  reancorar. So' na SEGUNDA chamada `stale = 1 >= 1` e' Verdadeiro e
  reancora. Ou seja, a ordem tem DUAS chances de toque (barra do
  armamento + 2 barras seguintes) antes de ser substituida -- UMA BARRA
  CHEIA A MAIS que F2, para o MESMO `N=1` nominal.

Generalizando para qualquer N (nao so' N=1): F2 da' N oportunidades de
toque antes de reancorar; F4 da' N+1. E' um off-by-one sistemico entre as
duas implementacoes, nao um bug isolado de N=1 -- mas e' em N=1
especificamente que o efeito relativo e' maior (2 chances contra 1 e' o
dobro; N+1 contra N encolhe proporcionalmente conforme N cresce).

Isto e' NECESSARIO mas pode nao ser SUFICIENTE para explicar o fator
5x-25x inteiro -- com espacamento de 1 tick a ordem frequentemente
PREENCHE antes de qualquer reancoragem por estagnacao acontecer (a
media geral da grade e' ~1 trade a cada poucas barras), entao o efeito
acumulado de "mais paciencia por reancoragem individual" so' se manifesta
nos casos em que a ordem NAO preenche rapido. Por isso este script tambem
conta, no pregao concreto, QUANTOS armamentos de cada implementacao vieram
de PREENCHIMENTO (fill) vs de REANCORAGEM POR ESTAGNACAO -- se F2 reancora
por estagnacao com muito mais frequencia que F4 (o que a analise acima
prediz), isso por si so' muda o preco medio de entrada e a distribuicao de
trades ao longo do pregao inteiro, nao so' o timing de um unico evento.

Uso:
    python scripts/daytrade/wdo_geo_diff_reancoragem.py
    python scripts/daytrade/wdo_geo_diff_reancoragem.py --dia 2026-02-10
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import num_br  # noqa: E402
from strategy.daytrade.lab.wdo_geo_grid_rolling import WdoGeoGridRolling  # noqa: E402
from strategy.daytrade.lab.wdo_reancoragem_grid_reload import WdoGridReloadReancoragem  # noqa: E402
from wdo_geo_sweep import _bars_is, _config_com_pedagio  # noqa: E402  (reusa infra da F4, so' LE, nao edita)

T = 1
S = 16
SPACING = 1
REANCHOR_BARS = 1


class _ArmLogger:
    """Envolve QUALQUER `IntradayStrategy` por composicao (`__getattr__`
    repassa tudo -- `name`, `version`, `symbol`, `on_session_start`,
    `initialize`, `on_capital_update`...) e so' intercepta `on_bar` para
    registrar toda `EnterLimit` devolvida, sem mudar nenhuma decisao. Nao
    faz `isinstance(strategy, IntradayStrategy)` em lugar nenhum do motor
    (conferido em `machine.py`/`engine.py` antes de escrever isto) -- duck
    typing por composicao e' seguro aqui."""

    def __init__(self, strat):
        self._strat = strat
        self.armamentos: list[dict] = []

    def __getattr__(self, name):
        return getattr(self._strat, name)

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        actions = self._strat.on_bar(ts, bar, positions, session_pnl_brl)
        for a in actions:
            if type(a).__name__ == "EnterLimit":
                self.armamentos.append({
                    "ts": ts, "side": a.side, "limit_price": a.limit_price,
                    "target": a.initial_target, "stop": a.initial_stop,
                })
        return actions


def _bars_entre(idx: pd.DatetimeIndex, ts_a: pd.Timestamp, ts_b: pd.Timestamp) -> int:
    return int(idx.get_loc(ts_b) - idx.get_loc(ts_a))


def _roda(strat_cls, kwargs: dict, bars_dia: pd.DataFrame, cfg):
    base = strat_cls(**kwargs)
    wrapped = _ArmLogger(base)
    resultado = run_intraday_backtest(bars_dia, wrapped, cfg)
    return wrapped, resultado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dia", default=None, help="YYYY-MM-DD; default = meio do IS")
    args = parser.parse_args()

    bars = _bars_is()
    dias = sorted(set(bars.index.date))
    if args.dia:
        alvo = pd.Timestamp(args.dia).date()
    else:
        alvo = dias[len(dias) // 2]
    if alvo not in set(dias):
        raise SystemExit(f"dia {alvo} nao esta no IS ({dias[0]}..{dias[-1]})")

    bars_dia = bars[[d == alvo for d in bars.index.date]]
    print(f"[wdo_geo_diff_reancoragem] pregao escolhido: {alvo} ({len(bars_dia)} barras M1)")
    print(f"[wdo_geo_diff_reancoragem] parametros identicos nas duas implementacoes: "
          f"T={T} S={S} espacamento={SPACING} reancora={REANCHOR_BARS} qty=1, pedagio=0 "
          f"(diagnostico de MECANICA, nao de custo)")

    cfg = _config_com_pedagio(0.0)
    tick = cfg.costs.tick_size

    f4, res_f4 = _roda(
        WdoGeoGridRolling,
        dict(symbol="WDO@", tick_size=tick, level_spacing_ticks=SPACING, profit_ticks=T,
             stop_ticks=S, rolling_reanchor_after_bars=REANCHOR_BARS, quantity=1),
        bars_dia, cfg,
    )
    f2, res_f2 = _roda(
        WdoGridReloadReancoragem,
        dict(symbol="WDO@", tick_size=tick, level_spacing_ticks=SPACING, profit_ticks=T,
             stop_ticks=S, reanchor_after_bars=REANCHOR_BARS, quantity=1,
             session_stop_brl=1_000_000.0),
        bars_dia, cfg,
    )

    idx = bars_dia.index

    def _resume(nome: str, wrapper: "_ArmLogger", resultado) -> None:
        arms = wrapper.armamentos
        liquido = sum(t.pnl_brl for t in resultado.trades)
        print(f"\n=== {nome}: {len(arms)} armamento(s), {len(resultado.trades)} trade(s), "
              f"liquido do dia = {num_br(liquido, 2)} ===")
        if len(arms) >= 2:
            deltas = [
                _bars_entre(idx, arms[i]["ts"], arms[i + 1]["ts"])
                for i in range(len(arms) - 1)
                if arms[i]["ts"] in idx and arms[i + 1]["ts"] in idx
            ]
            if deltas:
                print(f"    barras entre armamentos sucessivos: "
                      f"media={statistics.mean(deltas):.2f}  mediana={statistics.median(deltas)}  "
                      f"min={min(deltas)}  max={max(deltas)}  n={len(deltas)}")
        print(f"    primeiros armamentos: "
              + "; ".join(f"{a['ts'].strftime('%H:%M')}/{a['side']}@{a['limit_price']:.1f}"
                           for a in arms[:8]))

    _resume("F4 WdoGeoGridRolling (esta frente)", f4, res_f4)
    _resume("F2 WdoGridReloadReancoragem", f2, res_f2)

    # Classifica cada armamento como FILL (o proximo armamento do MESMO lado
    # veio de uma posicao ter fechado -- ou seja, preencheu) vs REANCORAGEM
    # POR ESTAGNACAO (o nivel mudou de preco sem nenhum trade ter fechado
    # entre um armamento e o proximo). Aproximacao por contagem: nao ha
    # trade novo "entre" os dois timestamps de armamento cujo entry_ts caia
    # nesse intervalo.
    def _conta_fills_vs_reancoragem(wrapper: "_ArmLogger", resultado) -> tuple[int, int]:
        arms = wrapper.armamentos
        entry_tss = sorted(t.entry_ts for t in resultado.trades)
        fills = 0
        reancoragens = 0
        for i in range(len(arms) - 1):
            janela = [e for e in entry_tss if arms[i]["ts"] <= e < arms[i + 1]["ts"]]
            if janela:
                fills += 1
            else:
                reancoragens += 1
        return fills, reancoragens

    f4_fills, f4_reanc = _conta_fills_vs_reancoragem(f4, res_f4)
    f2_fills, f2_reanc = _conta_fills_vs_reancoragem(f2, res_f2)
    print(f"\n=== Composicao dos armamentos (fill vs reancoragem-por-estagnacao) ===")
    print(f"  F4: {f4_fills} seguidos de fill, {f4_reanc} reancoragens por estagnacao "
          f"({100.0*f4_reanc/max(1,f4_fills+f4_reanc):.1f}% estagnacao)")
    print(f"  F2: {f2_fills} seguidos de fill, {f2_reanc} reancoragens por estagnacao "
          f"({100.0*f2_reanc/max(1,f2_fills+f2_reanc):.1f}% estagnacao)")

    print(f"\n=== Trades lado a lado (ate 20 primeiros de cada) ===")
    print(f"{'F4 entry_ts':<20}{'F4 exit':<10}{'F4 R$':>10}   {'F2 entry_ts':<20}{'F2 exit':<10}{'F2 R$':>10}")
    n = max(len(res_f4.trades), len(res_f2.trades))
    for i in range(min(20, n)):
        if i < len(res_f4.trades):
            t4 = res_f4.trades[i]
            c4 = f"{t4.entry_ts.strftime('%H:%M:%S'):<20}{t4.exit_reason.value:<10}{num_br(t4.pnl_brl,2):>10}"
        else:
            c4 = " " * 40
        if i < len(res_f2.trades):
            t2 = res_f2.trades[i]
            c2 = f"{t2.entry_ts.strftime('%H:%M:%S'):<20}{t2.exit_reason.value:<10}{num_br(t2.pnl_brl,2):>10}"
        else:
            c2 = ""
        print(f"{c4}   {c2}")

    print(f"\n[wdo_geo_diff_reancoragem] conclusao: ver o texto impresso acima -- "
          f"a media de barras-entre-armamentos e a razao fill/reancoragem sao o "
          f"diagnostico direto de qual convencao 'segura' a ordem parada por mais tempo.")


if __name__ == "__main__":
    main()
