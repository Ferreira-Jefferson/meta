"""Infra comum dos scripts de win_deslocamento_matinal (IS, OOS, WDO).

Carrega o CSV M1 (@D, BRT), poe o indice em UTC ingenuo (como as barras
salvas do repo: 09:00 BRT = 12:00 UTC, rotulo = ABERTURA da barra), monta a
config pelo caminho oficial (`config_for`) e roda o motor.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado  # noqa: E402
from core.instruments import economics_for  # noqa: E402
from strategy.daytrade.base import MARGIN_BUFFER_FUTUROS, RESERVA_CAIXA_SEGURANCA  # noqa: E402
from strategy.daytrade.lab.win_deslocamento_matinal import WinDeslocamentoMatinal  # noqa: E402

DATA = ROOT / "data" / "wdo-mt5"
ARQ = {"WIN@": "WIN@D_M1_202110010900_202610011717.csv",
       "WDO@": "WDO@D_M1_202109290900_202609291020.csv"}
#: (trade_tick_value, trade_tick_size) crus do MT5 -- `config_for` reescala pelo perfil.
ECONOMIA = {"WIN@": (0.2, 1.0), "WDO@": (0.01, 0.001)}

IS_INI, IS_FIM = pd.Timestamp("2021-10-01"), pd.Timestamp("2024-12-31")
OOS_INI, OOS_FIM = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-09-30")
#: sessoes de aquecimento antes da janela: a 1a sessao com ATR14 e' a de indice 15.
AQUECIMENTO = 15

#: V̄ = mediana do volume M1 (VOL) 10:30-12:30 BRT na IS (PRE_REGISTRO, secao 4).
V_BARRA = {"WIN@": 38_000.0, "WDO@": 6_700.0}
#: premissas de fila: nome -> multiplo de V̄ (None = calibracao oficial do simbolo).
PREMISSAS = {"P0": 0.0, "P1": 1.0, "P2": 2.0}

CAPITAL = {s: economics_for(s).margin_per_contract_brl * MARGIN_BUFFER_FUTUROS * RESERVA_CAIXA_SEGURANCA
           for s in ("WIN@", "WDO@")}


def carregar(simbolo: str) -> pd.DataFrame:
    """M1 do @D, so' pregoes completos (abre <=09:05 BRT e termina >=17:50 BRT)."""
    d = pd.read_csv(DATA / ARQ[simbolo], sep="\t")
    d.columns = [c.strip("<>").lower() for c in d.columns]
    dt = pd.to_datetime(d["date"] + " " + d["time"], format="%Y.%m.%d %H:%M:%S")
    df = pd.DataFrame({"open": d["open"].astype(float), "high": d["high"].astype(float),
                       "low": d["low"].astype(float), "close": d["close"].astype(float),
                       "tick_volume": d["tickvol"].astype(float),
                       "real_volume": d["vol"].astype(float)})
    df.index = dt + pd.Timedelta(hours=3)          # BRT -> UTC ingenuo
    dia = pd.Series(df.index.date, index=df.index)
    minuto = df.index.hour * 60 + df.index.minute  # UTC
    g = pd.DataFrame({"dia": dia.values, "m": minuto}, index=df.index).groupby("dia")["m"]
    ini, fim = g.min(), g.max()
    bons = ini.index[(ini <= 12 * 60 + 5) & (fim >= 20 * 60 + 50)]
    df = df[dia.isin(set(bons)).values]
    df["volume"] = df["real_volume"].where(df["real_volume"] > 0, df["tick_volume"])
    return df


def janela(df: pd.DataFrame, ini: pd.Timestamp, fim: pd.Timestamp) -> tuple[pd.DataFrame, list]:
    """Recorta [ini, fim] com AQUECIMENTO sessoes antes. Devolve (barras, dias_da_janela)."""
    dias = sorted(set(df.index.date))
    na = [d for d in dias if ini.date() <= d <= fim.date()]
    if not na:
        return df.iloc[0:0], []
    i0 = dias.index(na[0])
    usa = dias[max(0, i0 - AQUECIMENTO): dias.index(na[-1]) + 1]
    sel = df[pd.Series(df.index.date, index=df.index).isin(set(usa)).values]
    return sel, na


CAPITAL_NOMINAL = 1_000_000.0


def montar_config(simbolo: str, premissa: str, capital: float | None = None, nominal: bool = False):
    perfil = profile_for(simbolo)
    cap = CAPITAL_NOMINAL if nominal else (CAPITAL[simbolo] if capital is None else capital)
    kw = {"enforce_capital_cap": False} if nominal else {}
    if premissa == "CAL":      # calibracao oficial do simbolo (so' WDO@)
        pass
    else:
        q = PREMISSAS[premissa] * V_BARRA[simbolo]
        kw.update(queue_ahead_qty=q, exit_queue_ahead_qty=q)
    tv, ts = ECONOMIA[simbolo]
    return config_for(perfil, trade_tick_value=tv, trade_tick_size=ts, initial_capital=cap,
                      target_fills_as_maker=True, limit_fill_capped_by_volume=True,
                      anchor_exits_at_fill=True, **kw), cap


def estrategia(simbolo: str, **params) -> WinDeslocamentoMatinal:
    perfil = profile_for(simbolo)
    return WinDeslocamentoMatinal(symbol=simbolo, tick_size=perfil.price_tick_size, **params)


def rodar(simbolo: str, df: pd.DataFrame, dias_janela: list, params: dict, premissa: str,
          rotulo: str = "", nominal: bool = False) -> dict:
    """Roda UMA celula. `df` ja' vem com aquecimento (ver `janela`).
    `nominal=True`: capital R$1.000.000 sem teto por caixa (= capital reposto por pregao)."""
    est = estrategia(simbolo, **params)
    cfg, cap = montar_config(simbolo, premissa, nominal=nominal)
    res = run_intraday_backtest(df, est, cfg)
    set_janela = set(dias_janela)
    trades = [t for t in res.trades if t.entry_ts.date() in set_janela]
    item = linha_de_resultado(rotulo or "celula", res, cap, capital_nocional=nominal)
    sinais = [s for s in est.sinais if s[0].date() in set_janela]
    eq = res.equity_curve
    eq_j = eq[pd.Series(eq.index.date, index=eq.index).isin(set_janela).values]
    out = dict(res=res, item=dataclasses.replace(item, pregoes=len(dias_janela)), trades=trades,
               sinais=sinais, cap=cap, caixa_min=float(eq_j.min()) if len(eq_j) else cap,
               pregoes=len(dias_janela))
    return out


def estatisticas(trades, n_boot: int = 5000, seed: int = 7) -> dict:
    """win%, breakeven empirico, media R$/op, IC95% (bootstrap por pregao), liquido."""
    if not trades:
        return dict(n=0, liquido=0.0, media=np.nan, ic_lo=np.nan, ic_hi=np.nan,
                    win=np.nan, be=np.nan)
    pnl = np.array([t.pnl_brl for t in trades])
    dias = np.array([str(t.entry_ts.date()) for t in trades])
    ud, idx = np.unique(dias, return_inverse=True)
    soma = np.bincount(idx, weights=pnl)
    cont = np.bincount(idx)
    rng = np.random.default_rng(seed)
    meds = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.integers(0, len(ud), len(ud))
        meds[b] = soma[s].sum() / cont[s].sum()
    g, p = pnl[pnl > 0], -pnl[pnl <= 0]
    be = (p.mean() / (g.mean() + p.mean())) if len(g) and len(p) else np.nan
    return dict(n=len(pnl), liquido=float(pnl.sum()), media=float(pnl.mean()),
                ic_lo=float(np.percentile(meds, 2.5)), ic_hi=float(np.percentile(meds, 97.5)),
                win=float(100 * (pnl > 0).mean()), be=float(100 * be) if be == be else np.nan)


def por_ano(trades) -> dict:
    out: dict[int, tuple[int, float]] = {}
    for t in trades:
        n, s = out.get(t.entry_ts.year, (0, 0.0))
        out[t.entry_ts.year] = (n + 1, s + t.pnl_brl)
    return dict(sorted(out.items()))


def atrasos_min(trades, sinais) -> list[float]:
    """Atraso REALIZADO (min) entre o fim da decisao (rotulo da barra de decisao + 1 min) e o fill."""
    por_dia = {s[0].date(): s[0] for s in sinais}
    out = []
    for t in trades:
        s = por_dia.get(t.entry_ts.date())
        if s is not None:
            out.append((t.entry_ts - s) / pd.Timedelta(minutes=1) - 1.0)
    return out


def caminhada_caixa(trades, capital: float, piso: float) -> dict:
    """Aplica a regra do motor aos trades da corrida NOMINAL, em ordem cronologica: o sinal so' vira
    operacao se o caixa REALIZADO >= `piso` (margem crua) na hora; senao e' perdido (trade nao ocorre)."""
    caixa, minimo, exec_, perd = capital, capital, 0, 0
    for t in sorted(trades, key=lambda x: x.entry_ts):
        if caixa < piso:
            perd += 1
            continue
        caixa += t.pnl_brl
        exec_ += 1
        minimo = min(minimo, caixa)
    return dict(exec=exec_, perdidos=perd, caixa_final=caixa, caixa_min=minimo)


def prob_trava(trades, capital: float, piso: float, n: int = 10000, seed: int = 11) -> float:
    """P(caixa realizado cair abaixo de `piso` em algum ponto) embaralhando a ordem dos trades."""
    if not trades:
        return 0.0
    pnl = np.array([t.pnl_brl for t in sorted(trades, key=lambda x: x.entry_ts)])
    rng = np.random.default_rng(seed)
    trava = 0
    for _ in range(n):
        c = capital + np.cumsum(rng.permutation(pnl))
        if (c < piso).any():
            trava += 1
    return trava / n


def capital_para_sobreviver(trades, piso: float) -> float:
    """Capital inicial que a sequencia CRONOLOGICA inteira teria exigido para nunca cair abaixo de `piso`."""
    if not trades:
        return piso
    pnl = np.array([t.pnl_brl for t in sorted(trades, key=lambda x: x.entry_ts)])
    return float(piso - min(0.0, np.cumsum(pnl).min()))


# ---------------------------------------------------------------- grade e unidade de trabalho
GRADE_X = (0.3, 0.5)
GRADE_STOP = (0.15, 0.25, None)      # None = linha
GRADE_ALVO = (None, 0.30)


def celulas() -> list[dict]:
    return [dict(desloc_min_atr=x, stop_atr=s, alvo_atr=a)
            for x in GRADE_X for s in GRADE_STOP for a in GRADE_ALVO]


def nome_celula(p: dict) -> str:
    s = "lin" if p["stop_atr"] is None else f"{p['stop_atr']:.2f}"[1:]
    a = "-" if p["alvo_atr"] is None else f"{p['alvo_atr']:.2f}"[1:]
    v = "+V" if p.get("escala_volume") else ""
    return f"X{p['desloc_min_atr']:.1f} S{s} A{a}{v}"


def vizinhos(p: dict) -> list[dict]:
    """Celulas da grade que diferem em UM parametro por UM passo."""
    out = []
    for c in celulas():
        d = [k for k in ("desloc_min_atr", "stop_atr", "alvo_atr") if c[k] != p[k]]
        if len(d) != 1:
            continue
        k = d[0]
        dom = {"desloc_min_atr": GRADE_X, "stop_atr": GRADE_STOP, "alvo_atr": GRADE_ALVO}[k]
        if abs(dom.index(c[k]) - dom.index(p[k])) == 1:
            out.append(c)
    return out


def linhas_trades(trades) -> list[dict]:
    return [dict(entry_ts=str(t.entry_ts), exit_ts=str(t.exit_ts), side=t.side,
                 entry_price=t.entry_price, exit_price=t.exit_price,
                 pnl=t.pnl_brl, reason=t.exit_reason.name, detail=t.exit_detail or "")
            for t in trades]


def unidade(simbolo: str, ini: str, fim: str, params: dict, premissa: str, nominal: bool = True) -> dict:
    """Unidade de trabalho de um worker: carrega, roda, devolve linha formatada + trades."""
    import contextlib
    import io
    from backtest.intraday.report import cabecalho, linha
    df = carregar(simbolo)
    sel, dias = janela(df, pd.Timestamp(ini), pd.Timestamp(fim))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = rodar(simbolo, sel, dias, params, premissa, rotulo=f"{nome_celula(params)} {premissa}",
                  nominal=nominal)
    st = estatisticas(r["trades"])
    atr = atrasos_min(r["trades"], r["sinais"])
    extras = {"sinais": str(len(r["sinais"])), "fills": str(len(r["trades"])),
              "atraso p50/p90": (f"{np.percentile(atr, 50):.0f}/{np.percentile(atr, 90):.0f}" if atr else "—")}
    item = dataclasses.replace(r["item"], extras=extras)
    txt = linha(item, extras=tuple(extras), largura_extra=15)
    return dict(simbolo=simbolo, params=params, premissa=premissa, nominal=nominal, texto=txt,
                cab=cabecalho(tuple(extras), 15), stats=st, trades=linhas_trades(r["trades"]),
                n_sinais=len(r["sinais"]), n_dias=len(dias), caixa_min=r["caixa_min"],
                recusadas_capital=r["res"].ordens_recusadas_por_capital,
                wiped=r["res"].wiped_out_at is not None, puladas=len(r["res"].sessoes_puladas_por_capital))
