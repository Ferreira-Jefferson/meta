# -*- coding: utf-8 -*-
"""Fila propria do ORB portado para o WIN@ -- curva de preenchimento medida
no TAPE real (nao Kaplan-Meier sobre ordem real: nao ha' ordem real de limite
no WIN@ ainda, ver a ressalva no topo de `win_orb_port_2026_09_11.py`).

Mesmo metodo de `scripts/daytrade/win_fila_real_por_tape_2026_09_11.py`
(item 6.30 de LICOES_DE_PRODUCAO.md), aplicado aos NIVEIS E JANELAS que o
ORB (nao o `copa_win`) de fato escolhe -- os dois robos tem perfil de ordem
MUITO diferente (ORB: alvo curto, minutos de exposicao; copa_win: alvo longo,
horas), e o item 6.30 e' explicito que fila e' funcao de tamanho-da-ordem x
giro x TEMPO DE ESPERA -- nao transfere de um robo para o outro sem medir.

Le' `data/raw_ticks/win_por_pregao/` (60 pregoes, 100,2% de cobertura,
2026-06-17 a 2026-09-10) e cruza contra os niveis que o ORB arma rodando
sobre M1 (`market_data_intraday.storage.load_m1`), com o mesmo ajuste de
razao (serie M1 continua ajustada x tape cru) que o script irmao ja' precisou
resolver.

Uso: .venv/Scripts/python.exe -u scripts/daytrade/win_orb_fila_calibracao_2026_09_11.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
TAPE_DIR = ROOT / "data" / "raw_ticks" / "win_por_pregao"
TICK_REAL = 5.0
QS = [0, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000]


def br(v, dec=1):
    if v != v:
        return "--"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def carrega_tape():
    arquivos = sorted(TAPE_DIR.glob("*.parquet"))
    if not arquivos:
        raise SystemExit(f"sem tape em {TAPE_DIR}")
    partes, ultimos = [], []
    for k, f in enumerate(arquivos, 1):
        t = pd.read_parquet(f)
        t = t[t["last"] > 0]
        if t.empty:
            continue
        if t.index.tz is None:
            t.index = t.index.tz_localize("UTC")
        vol = t["volume_real"].fillna(t["volume"])
        minuto = t.index.floor("min")
        g = pd.DataFrame({"min": minuto, "px": t["last"].values, "v": vol.values})
        partes.append(g.groupby(["min", "px"], sort=False)["v"].sum())
        ultimos.append(t.groupby(minuto)["last"].last())
        print(f"  tape: {f.stem}  ({k}/{len(arquivos)})", flush=True)
    vol_mp = pd.concat(partes).groupby(level=[0, 1]).sum().sort_index()
    ultimo = pd.concat(ultimos).groupby(level=0).last()
    return vol_mp, ultimo


def razoes_por_pregao(ultimo_tick_por_min, m1):
    j = m1["close"].reindex(ultimo_tick_por_min.index).dropna()
    razao = j / ultimo_tick_por_min.reindex(j.index)
    return razao.groupby(razao.index.date).median()


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from win_orb_port_2026_09_11 import range_abertura_ticks, monta_estrategia
    from market_data_intraday.storage import load_m1

    m1 = load_m1(SYMBOL).sort_index()
    ranges = range_abertura_ticks(m1)
    p25, p75 = ranges.quantile([.25, .75])
    strat = monta_estrategia(int(round(p25)), int(round(p75)), entrada_ttl_bars=15)

    print("carregando tape do WIN@...", flush=True)
    vol_mp, ultimo = carrega_tape()
    razao = razoes_por_pregao(ultimo, m1)
    dias_tape = sorted(razao.index)
    print(f"\njanela cruzavel: {dias_tape[0]} a {dias_tape[-1]} "
          f"({len(dias_tape)} pregoes)\n", flush=True)

    bars = m1[[d in set(dias_tape) for d in m1.index.date]]

    # ---- espiona as ordens que o ORB armaria (sem rodar fila nenhuma) -----
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for

    armadas: list[dict] = []
    ts_atual = {"t": None}
    on_bar_orig = strat.on_bar

    def on_bar_espiao(ts, bar, positions, session_pnl_brl):
        ts_atual["t"] = ts
        acoes = on_bar_orig(ts, bar, positions, session_pnl_brl)
        for a in acoes:
            if hasattr(a, "limit_price"):
                armadas.append(dict(
                    ts=ts, side=a.side, limite=float(a.limit_price),
                    alvo=float(a.initial_target), stop=float(a.initial_stop),
                ))
        return acoes

    strat.on_bar = on_bar_espiao
    perfil = profile_for(SYMBOL)
    cfg = config_for(perfil, trade_tick_value=1.0, trade_tick_size=5.0,
                      initial_capital=250.0, target_fills_as_maker=True,
                      anchor_exits_at_fill=True, limit_fill_capped_by_volume=True,
                      queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    print(f"robo rodado: {len(armadas)} ordens de entrada armadas, "
          f"{len(trades)} operacoes fechadas\n", flush=True)

    ttl = strat.entrada_ttl_bars

    def volume_no_nivel(nivel, t0, t1, dia):
        r = razao.get(dia)
        if r is None or r != r:
            return None
        px = round((nivel / r) / TICK_REAL) * TICK_REAL
        try:
            fatia = vol_mp.loc[(slice(t0, t1), px)]
        except KeyError:
            return 0.0
        return float(fatia.sum())

    v_ent, encheu_ent = [], []
    entradas_por_preco = {(t.side, round(t.entry_price, 2)): t for t in trades}
    for a in armadas:
        t0 = a["ts"] + pd.Timedelta(minutes=1)
        t1 = t0 + pd.Timedelta(minutes=ttl)
        v = volume_no_nivel(a["limite"], t0, t1, a["ts"].date())
        if v is None:
            continue
        v_ent.append(v)
        chave = (a["side"], round(a["limite"], 2))
        t = entradas_por_preco.get(chave)
        encheu_ent.append(bool(t is not None and t0 <= t.entry_ts <= t1))

    v_sai, encheu_sai = [], []
    for t in trades:
        cand = [a for a in armadas
                if a["side"] == t.side and abs(a["limite"] - t.entry_price) < 1e-6
                and a["ts"] <= t.entry_ts]
        if not cand:
            continue
        alvo = cand[-1]["alvo"]
        v = volume_no_nivel(alvo, t.entry_ts, t.exit_ts, t.entry_ts.date())
        if v is None:
            continue
        v_sai.append(v)
        encheu_sai.append(t.exit_reason.value == "target")

    for rot, vs, fills in (
        (f"ENTRADA (limite 2t atras do rompimento, prazo {ttl} barras M1)", v_ent, encheu_ent),
        ("SAIDA POR ALVO (limite parada ate' pagar, sem prazo)", v_sai, encheu_sai),
    ):
        s = pd.Series(vs)
        print(f"\n===== {rot} =====")
        print(f"n = {len(s)} ordens   |   motor SEM fila encheu "
              f"{br(100*pd.Series(fills).mean(),1)}% delas")
        if len(s) == 0:
            continue
        print("volume no NOSSO preco durante a janela (contratos):")
        for q, val in (("minimo", s.min()), ("p10", s.quantile(.10)),
                       ("p25", s.quantile(.25)), ("MEDIANA", s.median()),
                       ("p75", s.quantile(.75)), ("p90", s.quantile(.90)),
                       ("maximo", s.max())):
            print(f"  {q:<10}{br(float(val),0):>14}")
        print(f"  ordens com volume ZERO no nosso preco: {br(100*float((s==0).mean()),1)}%")
        print("curva de preenchimento (V>=Q):")
        for q in QS:
            print(f"  {br(q,0):>10}{br(100*float((s>=q).mean()),1)+'%':>14}")


if __name__ == "__main__":
    main()
