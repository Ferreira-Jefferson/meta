# -*- coding: utf-8 -*-
"""A1: injeta o corte de zeragem do WIN@ (base UTC) SEM tocar motor/perfis.

Carregado em todo interpretador (inclusive workers spawn) via PYTHONPATH.
Env: A1_CORTE=2125|2120 ; A1_LOG=<jsonl> ; A1_MAXW=<n workers>.
Ativo so' quando A1_CORTE existe. Troca `session_end_time` do cfg devolvido por
`config_for` quando o perfil e' o do WIN (session_end_time==21:25), e registra
por run_intraday_backtest: n trades, saidas na ultima barra do dia (21:24+),
forced_flatten.
"""
import os
import sys
from datetime import time
from pathlib import Path

_c = os.environ.get("A1_CORTE")
if _c:
    ROOT = Path(__file__).resolve().parents[6]
    sys.path.insert(0, str(ROOT / "src"))
    import dataclasses
    import json

    import backtest.intraday.profiles as _p
    import backtest.intraday.engine as _e

    _CORTE = time(int(_c[:2]), int(_c[2:]))
    _orig_cfg = _p.config_for

    def _cfg(profile, *a, **k):
        cfg = _orig_cfg(profile, *a, **k)
        if profile.session_end_time == time(21, 25):
            cfg = dataclasses.replace(cfg, session_end_time=_CORTE)
        return cfg

    _p.config_for = _cfg
    _orig_run = _e.run_intraday_backtest

    def _run(bars, strat, cfg, *a, **k):
        res = _orig_run(bars, strat, cfg, *a, **k)
        try:
            tr = list(res.trades)
            ult = bars.groupby(bars.index.date).tail(1).index
            ult_set = set(ult)
            n_call = sum(1 for t in tr if t.exit_ts.time() >= time(21, 24))
            n_ult = sum(1 for t in tr if t.exit_ts in ult_set)
            n_ff = sum(1 for t in tr if t.exit_reason.value == "forced_flatten")
            n_ff_ult = sum(1 for t in tr if t.exit_reason.value == "forced_flatten" and t.exit_ts in ult_set)
            with open(os.environ.get("A1_LOG", "a1_stats.jsonl"), "a") as f:
                f.write(json.dumps(dict(corte=_c, n=len(tr), saida_2124=n_call, saida_ult_barra=n_ult,
                                        ff=n_ff, ff_ult=n_ff_ult)) + "\n")
        except Exception as ex:  # nunca derruba o estudo
            pass
        return res

    _e.run_intraday_backtest = _run

    _maxw = int(os.environ.get("A1_MAXW", "0"))
    if _maxw:
        import concurrent.futures.process as _cp
        _init = _cp.ProcessPoolExecutor.__init__

        def _pinit(self, max_workers=None, *a, **k):
            _init(self, min(max_workers or _maxw, _maxw), *a, **k)

        _cp.ProcessPoolExecutor.__init__ = _pinit

if _c and os.environ.get("A1_LEGADO") == "1":
    # config de producao ANTES de c6dc0ef (2026-09-11): alvo 9,5 / prazo 15
    import strategy.daytrade.registry as _r
    _r._KWARGS_PADRAO["copa_win"].update(alvo_vol=9.5, entrada_ttl_barras=15)

if _c and os.environ.get("A1_FIM"):
    # trunca a base na data (reproduz a janela de dados da epoca do estudo)
    import pandas as _pd
    import market_data_intraday.storage as _s
    _orig_load = _s.load_m1
    _fim = _pd.Timestamp(os.environ["A1_FIM"]).date()

    def _load(*a, **k):
        d = _orig_load(*a, **k)
        return d[[x <= _fim for x in d.index.date]] if len(d) else d

    _s.load_m1 = _load
