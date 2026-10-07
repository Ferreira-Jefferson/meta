# -*- coding: utf-8 -*-
"""Valida o port tick a tick contra o Python G41 (barra a barra, WIN@D) por mes: trades e liquido."""
import sys
from pathlib import Path
import pandas as pd

AQUI = Path(__file__).resolve().parent
B = AQUI.parents[0] / "win_pernadas_exploracao" / "ea_busca_lucro" / "g29_ema34"
sys.path.insert(0, str(B))
import g29_base as b  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from strategy.daytrade.lab.win_busca_lucro_g41_retangulo_zera_cedo import WinBuscaLucroG41RetanguloZeraCedo as E  # noqa: E402

win = b.carrega_win()
dias = b.dias_da_janela(win, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-10-01"))
st = E(hora_zerar="17:00", periodo=34, stop_fracao_largura=0.45, alvo_fracao_largura=0.90)
res = run_intraday_backtest(b.bars_dos_dias(win, dias), st, b.monta_config(1000.0))
rows = [dict(entrada=str(t.entry_ts), saida=str(t.exit_ts), lado=1 if t.side == "long" else -1, preco_entrada=t.entry_price,
             preco_saida=t.exit_price, rs=t.pnl_brl, motivo=str(getattr(t.exit_reason, "value", t.exit_reason))) for t in res.trades]
df = pd.DataFrame(rows); df.to_csv(AQUI / "ref_python_g41_trades.csv", index=False)
df["mes"] = df.saida.str[:7]
print(df.groupby("mes").rs.agg(["size", "sum"]).round(2).to_string(), flush=True)
print("TOTAL", len(df), round(df.rs.sum(), 2), df.motivo.value_counts().to_dict())
