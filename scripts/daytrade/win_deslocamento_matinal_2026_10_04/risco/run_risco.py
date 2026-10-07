"""Gestao de risco por valor (teto de stop em R$ ligado ao caixa) sobre win_deslocamento_matinal.
Capital R$1.000 CONTINUO (compoe), 1 contrato, fila P2. Teto lido do caixa que o motor entrega
(`on_capital_update`: capital inicial + PnL realizado ate' agora) -- sem look-ahead."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import comum as c  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402

CAPITAL = 1000.0
PV = 0.2  # R$/ponto/contrato


@dataclass
class WinRisco(c.WinDeslocamentoMatinal):
    regra: str = "BASE"      # BASE | T | MAX | MIN
    pct: float = 0.05
    forma: str = "APERTAR"   # APERTAR | PULAR
    dia_ini: object = None   # nao opera antes (aquecimento do ATR)
    _cash: float = field(default=CAPITAL, init=False, repr=False)
    _cash_ini: float | None = field(default=None, init=False, repr=False)
    _prev: float = field(default=0.0, init=False, repr=False)
    _dia: object = field(default=None, init=False, repr=False)
    _novo: bool = field(default=True, init=False, repr=False)
    log: list = field(default_factory=list, init=False, repr=False)

    def on_capital_update(self, cash_brl):
        self._cash = cash_brl

    def on_session_start(self, session_date):
        super().on_session_start(session_date)
        self._dia = session_date
        self._novo = True

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        if self._novo:
            self._novo = False
            self._prev = 0.0 if self._cash_ini is None else self._cash - self._cash_ini
            self._cash_ini = self._cash
        acts = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acts:
            return acts
        if self.dia_ini is not None and ts.date() < self.dia_ini:
            del self.sinais[-1:]
            return []
        if self.regra == "BASE":
            return acts
        a = acts[0]
        sgn = 1.0 if a.side == "long" else -1.0
        dist = abs(a.limit_price - a.initial_stop)
        base = self.pct * self._cash
        metade = 0.5 * self._prev
        if self.regra == "T":
            teto = base
        elif self.regra == "MAX":
            teto = max(base, metade) if self._prev > 0 else base
        else:
            teto = min(base, metade) if self._prev > 0 else base
        custo = dist * PV * self.quantity
        item = dict(ts=str(ts), cash=round(self._cash, 2), prev=round(self._prev, 2), teto=round(teto, 2),
                    stop_linha_rs=round(custo, 2))
        if custo <= teto:
            item["acao"] = "linha"
            self.log.append(item)
            return acts
        if self.forma == "PULAR":
            item["acao"] = "pulou"
            self.log.append(item)
            del self.sinais[-1:]
            return []
        d = int(teto / (PV * self.quantity) / self.tick_size) * self.tick_size
        d = max(d, 2 * self.tick_size)
        item["acao"] = "apertou"
        item["stop_rs"] = round(d * PV * self.quantity, 2)
        self.log.append(item)
        import dataclasses
        return [dataclasses.replace(a, initial_stop=a.limit_price - sgn * d)]


def celulas():
    out = {"BASE": dict(regra="BASE")}
    for forma in ("APERTAR", "PULAR"):
        for nome, regra in (("T5", "T"), ("T5_MAX", "MAX"), ("T5_MIN", "MIN")):
            out[f"{nome}_{forma}"] = dict(regra=regra, pct=0.05, forma=forma)
        for p in (3, 10, 15, 20):
            out[f"T{p}_{forma}"] = dict(regra="T", pct=p / 100, forma=forma)
    return out


CEL = celulas()
JAN = {"IS": ("2021-10-01", "2024-12-31"), "OOS": ("2025-01-01", "2026-09-30")}


def unid(cid, jan):
    ini, fim = JAN[jan]
    df = c.carregar("WIN@")
    sel, dias = c.janela(df, pd.Timestamp(ini), pd.Timestamp(fim))
    perfil = c.profile_for("WIN@")
    est = WinRisco(symbol="WIN@", tick_size=perfil.price_tick_size, desloc_min_atr=0.3, stop_atr=None,
                   alvo_atr=None, dia_ini=dias[0], **CEL[cid])
    cfg, cap = c.montar_config("WIN@", "P2", capital=CAPITAL, nominal=False)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = run_intraday_backtest(sel, est, cfg)
    ds = set(dias)
    tr = [t for t in res.trades if t.entry_ts.date() in ds]
    trades = c.linhas_trades(tr)
    return dict(cid=cid, jan=jan, trades=trades, log=est.log, n_dias=len(dias),
                puladas_cap=len([s for s in res.sessoes_puladas_por_capital if s.date() in ds]),
                recusadas=res.ordens_recusadas_por_capital, wiped=res.wiped_out_at is not None,
                n_sinais=len([s for s in est.sinais if s[0].date() in ds]))


def metr(r):
    t = r["trades"]
    p = np.array([x["pnl"] for x in t]) if t else np.array([])
    out = dict(cel=r["cid"], jan=r["jan"], trades=len(p), pulados_regra=sum(1 for l in r["log"] if l["acao"] == "pulou"),
               apertados=sum(1 for l in r["log"] if l["acao"] == "apertou"), sem_sinal_caixa=r["puladas_cap"] + r["recusadas"],
               parados_caixa=r["puladas_cap"], wiped=r["wiped"])
    if len(p) == 0:
        out.update(liq=0.0, cap_final=CAPITAL)
        return out
    g, l = p[p > 0], p[p < 0]
    eq = CAPITAL + np.cumsum(p)
    pico = np.maximum.accumulate(np.concatenate([[CAPITAL], eq]))[1:]
    dd = pico - eq
    k = m = 0
    for v in p:
        k = k + 1 if v < 0 else 0
        m = max(m, k)
    gm = g.mean() if len(g) else 0.0
    pm = -l.mean() if len(l) else np.nan
    anos = {}
    for x in t:
        anos[x["entry_ts"][:4]] = anos.get(x["entry_ts"][:4], 0) + x["pnl"]
    out.update(liq=p.sum(), cap_final=CAPITAL + p.sum(), r_op=p.mean(), acerto=100 * (p > 0).mean(), ganho=gm,
               perda=pm, payoff=gm / pm if pm == pm else np.nan, stops=sum(1 for x in t if x["reason"] == "STOP"),
               maxdd_rs=dd.max(), maxdd_pct=100 * (dd / pico).max(), fr=p.sum() / dd.max() if dd.max() else np.nan,
               seq_perdas=m, caixa_min=eq.min(), anos=" ".join(f"{a}:{v:.0f}" for a, v in sorted(anos.items())))
    return out


def main():
    res = []
    with ProcessPoolExecutor(max_workers=3) as ex:
        fut = [ex.submit(unid, cid, j) for j in JAN for cid in CEL]
        for f in as_completed(fut):
            r = f.result()
            res.append(r)
            m = metr(r)
            print(f"[{m['jan']}] {m['cel']:<14} n={m['trades']} liq={m['liq']:.1f} capfinal={m['cap_final']:.1f} "
                  f"pul={m['pulados_regra']} apert={m['apertados']} paradoCx={m['parados_caixa']} wiped={m['wiped']}", flush=True)
    (HERE / "saida_risco.json").write_text(json.dumps(res, default=str), encoding="utf-8")
    pd.DataFrame([metr(r) for r in res]).sort_values(["jan", "cel"]).to_csv(HERE / "risco.csv", index=False, sep=";", decimal=",")


if __name__ == "__main__":
    main()
