# -*- coding: utf-8 -*-
"""Cruzamento do simulador com o MOTOR (R$1.000, via config_for, sizing de producao).

  (i)  motor  x  `simula_barra` (conta continua): entrada, quantidade, motivo, preco e P&L por perna iguais.
  (ii) `simula_barra` x `simula_tick` (R$1.000 por pregao): nos trades em que a saida por stop/alvo NAO ocorreu
       dentro da barra do fill, entrada/motivo/barra de saida iguais.
Seis celulas: stop em pontos, ATR, 1a barra, estrutural, alvo-gap e RR.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ctx as C  # noqa: E402
import regras as R  # noqa: E402
import sim as S  # noqa: E402
import sizing as Z  # noqa: E402
import ticks_prep as TP  # noqa: E402
from strategy.daytrade.base import EnterLimit, IntradayStrategy  # noqa: E402

CELULAS = ["V2 r150 | S350", "V2 r150 | S700 T700", "V1 r150 | S.3atr T.6atr", "V3 r150 | Sbar1 T2R",
           "V2 r150 | S700 Tgap", "V2 r150 | S1R1 T2R1"]


class EstrategiaNiveis(IntradayStrategy):
    """Emite, na 1a barra M5 fechada, a ordem que `regras` calculou para o dia (mesma funcao do simulador)."""
    name, version, symbol = "xcheck_niveis", "0", "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    quantity_e_unidade = True

    def __init__(self, ordens: dict):
        self.ordens, self._dia, self._n = ordens, None, 0

    def on_session_start(self, session_date):
        self._dia, self._n = session_date, 0

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._n += 1
        o = self.ordens.get(self._dia)
        if self._n != 1 or o is None:
            return []
        side, lim, stop, tgt = o
        return [EnterLimit(side="long" if side > 0 else "short", limit_price=lim, initial_stop=stop,
                           initial_target=tgt, quantity=1, ttl_bars=S.TTL_BARRAS, exit_split_unit=1,
                           exit_ttl_bars=None, reason="xcheck")]


def ordens_do_dia(ctx, cel):
    out = {}
    for dia, c in ctx.items():
        s = R.gatilho(c, cel["ent"])
        if s == 0:
            continue
        lim = R.limite(c, s, cel["ent"]["recuo"])
        sa = R.saida_de(c, s, lim, cel["ex"], s, lim)
        if sa is None:
            continue
        out[dia] = (s, lim, sa)
    return out


def dia_ticks(bj, dia):
    b = C.barras_do_dia(bj, dia)
    t, p = TP.carrega(dia)
    return b, S.DiaTicks(t=t, p=p, bst=b["st"], bo=b["o"], bh=b["h"], bl=b["l"], bc=b["c"])


def agrega(L):
    m = {}
    for dia, sd, q, e, x, r, pnl in L:
        a = m.setdefault((dia, sd, e, x, r), [0, 0.0])
        a[0] += q
        a[1] += pnl
    return {k: (v[0], round(v[1], 2)) for k, v in m.items()}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(AQUI.parent))
    import runner
    from backtest.intraday.engine import run_intraday_backtest
    bj, dj, ctx = C.constroi()
    grade = {g["id"]: g for g in R.grade()}
    cfg = runner.monta_config(Z.CAPITAL)
    print("config_for R$1.000: max_open_contracts=%s margem=%s escada=%s session_end=%s" % (
        cfg.max_open_contracts, cfg.margin_per_contract_brl, cfg.escada_risco_progressivo, cfg.session_end_time))
    assert cfg.max_open_contracts == Z.HARD_CAP
    resumo = []
    for cid in CELULAS:
        cel = grade[cid]
        od = ordens_do_dia(ctx, cel)
        est = EstrategiaNiveis({d: (s, lim, sa.stop, sa.target) for d, (s, lim, sa) in od.items()})
        res = run_intraday_backtest(bj, est, cfg)
        mt = sorted(res.trades, key=lambda t: t.entry_ts)
        cash, sb = Z.CAPITAL, []
        for dia in sorted(od):
            s, lim, sa = od[dia]
            b, d = dia_ticks(bj, dia)
            n = Z.n_contratos(cash)
            if n < 1:
                continue
            tr = S.simula_barra(d, s, lim, sa.stop, sa.target, n, "toque", int(b["st"][0] + S.M5))
            if tr is not None:
                sb.append((dia, tr))
                cash += tr.pnl
        mlegs = [(t.entry_ts.date(), t.side, t.quantity, t.entry_price, t.exit_price,
                  str(getattr(t.exit_reason, "value", t.exit_reason)), round(t.pnl_brl, 2)) for t in mt]
        slegs = []
        for dia, tr in sb:
            for g in tr.legs:
                pnl = ((g.exit_price - tr.entry_price) * tr.side) * S.PV * g.qty - S.FEE * g.qty
                slegs.append((dia, "long" if tr.side > 0 else "short", g.qty, tr.entry_price, g.exit_price,
                              {"alvo": "target", "stop": "stop", "flatten": "forced_flatten"}[g.reason], round(pnl, 2)))
        am, as_ = agrega(mlegs), agrega(slegs)
        igual = am == as_
        dif = {k: (am.get(k), as_.get(k)) for k in set(am) | set(as_) if am.get(k) != as_.get(k)}
        qm = sorted({sum(t.quantity for t in mt if t.entry_ts.date() == dd) for dd in {t.entry_ts.date() for t in mt}})
        print(f"\n[{cid}] ordens={len(od)} | motor: {len({t.entry_ts.date() for t in mt})} trades, liquido={sum(t.pnl_brl for t in mt):.2f}"
              f" | sim_barra: {len(sb)} trades, liquido={sum(tr.pnl for _, tr in sb):.2f} | IGUAIS={igual}"
              f" | contratos por trade motor {qm}, sim {sorted({tr.qty for _, tr in sb})}", flush=True)
        for k, v in list(dif.items())[:5]:
            print("   diferenca", k, v)
        resumo.append(dict(cel=cid, igual=bool(igual), n_motor=len({t.entry_ts.date() for t in mt}), n_sim=len(sb),
                           liq_motor=round(sum(t.pnl_brl for t in mt), 2), liq_sim=round(sum(tr.pnl for _, tr in sb), 2)))
        tot = ok_rest = sai_fill = 0
        difs = []
        q = Z.n_contratos(Z.CAPITAL)
        for dia in sorted(od):
            s, lim, sa = od[dia]
            b, d = dia_ticks(bj, dia)
            tsig = int(b["st"][0] + S.M5)
            tb = S.simula_barra(d, s, lim, sa.stop, sa.target, q, "toque", tsig)
            tk = S.simula_tick(d, s, lim, sa, q, "toque", tsig)
            if tb is None and tk is None:
                continue
            tot += 1
            if (tb is None) != (tk is None):
                difs.append((str(dia), "fill diferente"))
                continue
            if tk.sai_na_barra_do_fill:
                sai_fill += 1
                continue
            kb_t = int(np.searchsorted(d.bst, tk.legs[-1].exit_t, side="right") - 1)
            kb_b = int(np.searchsorted(d.bst, tb.legs[-1].exit_t, side="right") - 1)
            mesmo = (tk.legs[-1].reason == tb.legs[-1].reason) and kb_t == kb_b and tk.entry_price == tb.entry_price
            ok_rest += int(mesmo)
            if not mesmo:
                difs.append((str(dia), tb.legs[-1].reason, tk.legs[-1].reason, kb_b, kb_t, round(tb.pnl, 1), round(tk.pnl, 1)))
        print(f"   barra x tick (q={q}): trades={tot}, saida dentro da barra do fill (so' o tick enxerga)={sai_fill}, "
              f"restantes iguais em entrada/motivo/barra de saida={ok_rest}/{tot - sai_fill}; divergencias: {difs[:6]}", flush=True)
        resumo[-1].update(barra_x_tick=dict(trades=tot, sai_na_barra_fill=sai_fill, restantes_iguais=ok_rest,
                                            restantes=tot - sai_fill, divergencias=difs))
    json.dump(resumo, open(AQUI / "out" / "crosscheck.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
