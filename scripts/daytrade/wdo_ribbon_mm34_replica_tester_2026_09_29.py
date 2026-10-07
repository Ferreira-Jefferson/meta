"""Replica do Strategy Tester do MT5 para o EA mt5/WdoRibbonMm34.mq5 (v1.63),
rodando a propria WdoRibbonMm34 do Python sobre as velas M1 do terminal Rico.

Aferido em 2026-09-29 contra rodadas reais do Testador (WDOV26, M1, "cada
tick"): as operacoes batem uma a uma -- entrada, stop inicial, alvo, motivo e
preco de saida -- e o total de pontos bate. Convencoes de preenchimento que o
Testador usa (e que tiveram de ser copiadas para bater): compra entra no ask
(open + 0,5), venda no bid (open); stop e alvo saem no preco pedido; saida a
mercado de venda (zeragem 18:20 ou stop que abre com gap) compra no ask
(open + 0,5). Quando stop e alvo caem na mesma vela, os ticks reais do minuto
decidem qual veio antes.

Nao passa pelo motor de backtest do projeto (backtest/intraday) nem cobra custo:
o resultado e' em PONTOS brutos, igual ao que o Testador executa.

Uso:
  python scripts/daytrade/wdo_ribbon_mm34_replica_tester_2026_09_29.py
  python scripts/daytrade/wdo_ribbon_mm34_replica_tester_2026_09_29.py --ini 2026-08-01 --fim 2026-09-28
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from strategy.daytrade.base import Bar  # noqa: E402
from strategy.daytrade.lab.wdo_ribbon_mm34 import WdoRibbonMm34  # noqa: E402

TERMINAL = r"C:\Program Files\Rico - MetaTrader 5\terminal64.exe"
SIMBOLO = "WDOV26"
SPREAD = 0.5
ZERAR = (18, 20)
PASTA = ROOT / "scratch" / "wdo_ribbon_mm34"


def _conectar() -> None:
    if not mt5.initialize(path=TERMINAL):
        raise SystemExit(f"mt5: {mt5.last_error()}")


def carregar_m1(ini: datetime, fim: datetime) -> pd.DataFrame:
    cache = PASTA / f"m1_{ini:%Y%m%d}_{fim:%Y%m%d}.pkl"
    if cache.exists():
        df = pd.read_pickle(cache)
    else:
        _conectar()
        # 7 dias antes para as MMs de 34 ja' chegarem aquecidas no primeiro pregao
        r = mt5.copy_rates_range(SIMBOLO, mt5.TIMEFRAME_M1, ini - timedelta(days=7), fim)
        df = pd.DataFrame(r)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        PASTA.mkdir(parents=True, exist_ok=True)
        df.to_pickle(cache)
    return df


_ticks: dict = {}


def primeiro_toque(ts: pd.Timestamp, compra: bool, stop: float, alvo: float) -> str:
    d = ts.normalize()
    if d not in _ticks:
        _conectar()
        tk = pd.DataFrame(mt5.copy_ticks_range(
            SIMBOLO, d.to_pydatetime(), (d + pd.Timedelta(days=1)).to_pydatetime(), mt5.COPY_TICKS_ALL))
        tk["t"] = pd.to_datetime(tk["time_msc"], unit="ms")
        _ticks[d] = tk[tk["last"] > 0].set_index("t")["last"]
    for v in _ticks[d][ts:ts + pd.Timedelta(seconds=59.999)]:
        if (v <= stop) if compra else (v >= stop):
            return "stop"
        if (v >= alvo) if compra else (v <= alvo):
            return "alvo"
    return "stop"


class _Pos:
    pass


def simular(df: pd.DataFrame, ini: datetime, estrategia: WdoRibbonMm34 | None = None) -> pd.DataFrame:
    """Roda a WdoRibbonMm34 (config padrao se `estrategia` nao for passada)
    sobre `df` a partir de `ini`, replicando a mecanica de fill do Testador."""
    s = estrategia or WdoRibbonMm34()
    s.initialize(df)
    trades = []
    pos = pend = dia = None
    for ts, row in df[df.index >= ini].iterrows():
        if ts.date() != dia:
            dia = ts.date()
            s.on_session_start(dia)
            pend = None
        zerar = (ts.hour, ts.minute) >= ZERAR
        if pend and pos is None and not zerar:
            pos = _Pos()
            pos.side, pos.current_stop = pend.side, pend.initial_stop
            pos.ent = row.open + (SPREAD if pos.side == "long" else 0.0)
            pos.ts, pos.stop0 = ts, pend.initial_stop
            if (pos.ent - pos.stop0) * (1 if pos.side == "long" else -1) < SPREAD:
                pos = None  # stop do lado errado do preco real: a corretora recusaria
            else:
                # o EA calcula o alvo com o preco real da ordem (ask/bid)
                pos.alvo = s.alvo_para(pos.side, pos.ent, pos.stop0)
                if pos.alvo is None:
                    pos = None
        pend = None
        if pos and zerar:
            trades.append((pos, ts, row.open if pos.side == "long" else row.open + SPREAD, "18:20"))
            pos = None
        if zerar:
            continue
        if pos:
            compra = pos.side == "long"
            bate_stop = (row.low <= pos.current_stop) if compra else (row.high >= pos.current_stop)
            bate_alvo = (row.high >= pos.alvo) if compra else (row.low <= pos.alvo)
            if bate_stop and bate_alvo and primeiro_toque(ts, compra, pos.current_stop, pos.alvo) == "alvo":
                bate_stop = False
            if bate_stop:
                gap = (row.open <= pos.current_stop) if compra else (row.open >= pos.current_stop)
                px = (row.open if compra else row.open + SPREAD) if gap else pos.current_stop
                trades.append((pos, ts, px, "stop"))
                pos = None
            elif bate_alvo:
                trades.append((pos, ts, pos.alvo, "alvo"))
                pos = None
        bar = Bar(ts=ts, open=row.open, high=row.high, low=row.low, close=row.close, volume=1)
        for x in s.on_bar(ts, bar, [pos] if pos else [], 0.0):
            if hasattr(x, "new_stop"):
                pos.current_stop = x.new_stop
            elif pos is None:
                pend = x
    linhas = []
    for p, tsai, px, mot in trades:
        pts = (px - p.ent) if p.side == "long" else (p.ent - px)
        linhas.append(dict(
            entrada=p.ts, lado="C" if p.side == "long" else "V", preco=p.ent,
            stop_inicial=p.stop0, alvo=p.alvo, saida=tsai, preco_saida=px, motivo=mot, pontos=pts,
        ))
    return pd.DataFrame(linhas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ini", default="2026-09-01")
    ap.add_argument("--fim", default="2026-09-28")
    a = ap.parse_args()
    ini = datetime.strptime(a.ini, "%Y-%m-%d")
    fim = datetime.strptime(a.fim, "%Y-%m-%d")
    df = carregar_m1(ini, fim)
    res = simular(df, ini)
    m = res.motivo.value_counts()
    res.to_csv(PASTA / "ops_config_padrao.csv", sep=";", index=False, decimal=",", encoding="utf-8-sig")
    print(f"{a.ini} a {a.fim}: {len(res)} ops, {res.pontos.sum():+.1f} pts "
          f"(stop={m.get('stop', 0)} alvo={m.get('alvo', 0)} 18:20={m.get('18:20', 0)}, "
          f"ganhos={(res.pontos > 0).sum()} perdas={(res.pontos < 0).sum()})")
    print(f"operacoes em {PASTA / 'ops_config_padrao.csv'}")


if __name__ == "__main__":
    main()
