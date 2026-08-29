"""Teste FORCADO (nao e' sinal natural da estrategia -- ja confirmado que o
grid nao armou nada entre 14:49-15:08 UTC nesse pregao): injeta uma posicao
SHORT ja aberta (via `IntradaySessionMachine.restore`, o mesmo caminho que um
restart ao vivo usa) em dois instantes candidatos, com o alvo/stop de
producao (T1/S4) ja calculados do jeito que `WdoGridReloadMaker` calcularia,
e deixa o motor genereico (nao a estrategia -- ver `on_bar`, linha 465:
"alvo e stop ja sao geridos pelo motor") resolver a saida contra as barras
M1 REAIS de 2026-08-28.

Pergunta do dono: "se no bt pegaria a posicao" -- ou seja, SE essa posicao
tivesse existido, o stop de 4 ticks do motor teria fechado antes de virar o
prejuizo real (R$295,00, conta que zerou por o stop nunca ter sido
registrado NA CORRETORA -- ver `LICOES_DE_PRODUCAO.md` Parte 0)?

Dois pontos testados:
  A. mesmo horario da 1a compra real: 11:58:53 BRT / 14:58:53 UTC, preco
     5204,00 (preco exato do 1o negocio do extrato).
  B. 10 minutos antes do 3o negocio real (11:59:04 BRT / 14:59:04 UTC) ->
     11:49:04 BRT / 14:49:04 UTC, preco = abertura da barra 14:49 UTC.

Lado SHORT nos dois (replica a posicao que de fato ficou presa e zerou a
conta -- a 1a compra em si foi fechada em 6s com -R$5,00 e nao e' o
evento que interessa aqui). Quantidade = 1 (dimensionamento de PRODUCAO;
o real abriu 2 por bug de teto agregado, que e' exatamente o que este
teste NAO reproduz de proposito -- aqui testamos SO' o stop/alvo).

Uso: `python scripts/daytrade/wdof1_forcado_incidente_2026_08_28.py`
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import bar_from_row  # noqa: E402
from backtest.intraday.machine import IntradaySessionMachine, PositionClosed  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

SYMBOL = "WDO@"
DIA = date(2026, 8, 28)
_ECONOMIA_WDO = (0.01, 0.001)
CAPITAL_NOCIONAL = 1_000_000.0


def montar_cfg():
    profile = profile_for(SYMBOL)
    trade_tick_value, trade_tick_size = _ECONOMIA_WDO
    return config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=CAPITAL_NOCIONAL,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
        max_open_contracts=1,
    )


def rodar_teste(rotulo: str, entry_ts: pd.Timestamp, entry_price: float,
                 bars_dia: pd.DataFrame, strat, cfg, tick_size: float):
    side = "short"
    offset_alvo = strat.profit_ticks * tick_size
    offset_stop = strat.stop_ticks * tick_size
    target = entry_price - offset_alvo
    stop = entry_price + offset_stop

    machine = IntradaySessionMachine(strat, cfg)
    machine.begin_session(DIA)
    machine.restore({
        "session_date": DIA.isoformat(),
        "session_pnl": 0.0,
        "realized_pnl": 0.0,
        "flattened": False,
        "positions": [{
            "side": side, "entry_ts": entry_ts.isoformat(), "entry_price": entry_price,
            "quantity": 1, "current_stop": stop, "current_target": target,
            "bars_held": 0, "metadata": {}, "exit_split_unit": None,
            "exit_ttl_bars": None, "exit_resting_qty": 0, "exit_resting_bars_waited": 0,
        }],
    })

    futuras = bars_dia[bars_dia.index > entry_ts]
    print(f"\n=== {rotulo} ===")
    print(f"entrada forcada: {side} 1x @ {entry_price:.2f} em {entry_ts} "
          f"| alvo={target:.2f} (T{strat.profit_ticks}) stop={stop:.2f} (S{strat.stop_ticks})")

    for i, (ts, row) in enumerate(futuras.iterrows()):
        bar = bar_from_row(ts, row)
        is_last = i == len(futuras) - 1
        eventos = machine.on_closed_bar(bar, is_last_bar=is_last)
        for ev in eventos:
            if isinstance(ev, PositionClosed):
                t = ev.trade
                print(f"FECHOU em {t.exit_ts} @ {t.exit_price:.2f} | motivo={t.exit_reason} "
                      f"| barras ate fechar={i + 1} | pnl_brl={t.pnl_brl:.2f}")
                return t
    print("nao fechou ate o fim do pregao (flatten forcado deveria ter pego -- checar).")
    return None


def main() -> None:
    df = load_m1(SYMBOL).sort_index()
    bars_dia = df[df.index.date == DIA]
    if bars_dia.empty:
        raise SystemExit(f"sem barras M1 para {SYMBOL} em {DIA}.")

    strat = get_daytrade_robot("wdo_grid_reload_maker")
    cfg = montar_cfg()
    tick_size = profile_for(SYMBOL).price_tick_size
    print(f"candidato: T{strat.profit_ticks} S{strat.stop_ticks} x{strat.level_spacing_ticks} "
          f"(defaults de producao) | tick_size={tick_size}")

    testes = [
        ("A) mesmo horario da 1a compra real (11:58:53 BRT / 14:58:53 UTC)",
         pd.Timestamp("2026-08-28 14:58:53+00:00"), 5204.00),
        ("B) 10min antes do 3o negocio (11:49:04 BRT / 14:49:04 UTC)",
         pd.Timestamp("2026-08-28 14:49:04+00:00"), float(bars_dia.loc["2026-08-28 14:49:00+00:00", "open"])),
    ]

    resultados = []
    for rotulo, ts, preco in testes:
        strat_teste = get_daytrade_robot("wdo_grid_reload_maker")
        strat_teste.initialize(bars_dia)
        t = rodar_teste(rotulo, ts, preco, bars_dia, strat_teste, cfg, tick_size)
        resultados.append((rotulo, t))

    print("\n=== resumo ===")
    for rotulo, t in resultados:
        if t is None:
            print(f"{rotulo}: nao fechou")
        else:
            print(f"{rotulo}: pnl=R${t.pnl_brl:.2f} | fechou em {t.exit_ts} "
                  f"({(t.exit_ts - pd.Timestamp(t.entry_ts)).total_seconds() / 60:.0f} min depois)")


if __name__ == "__main__":
    main()
