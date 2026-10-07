"""Ficha completa da MELHOR ATUAL do WIN (EMA 9/21/34/100/200 alinhadas e
inclinadas, saida na quebra, M5, WINV26). Pedido do dono, 2026-10-05."""
import importlib.util as u
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
s = u.spec_from_file_location("base", AQUI / "win_alinhamento_3emas_candle_2026_10_05.py")
b = u.module_from_spec(s); s.loader.exec_module(b)
V26 = b.RAIZ / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"


def seq_max(x):
    m = c = 0
    for v in x:
        c = c + 1 if v else 0
        m = max(m, c)
    return m


def ficha(tr, eq):
    df = pd.DataFrame(tr, columns=["pnl", "dia", "pts", "t", "lado", "t_saida", "qty"])
    g, p = df.pnl[df.pnl > 0], -df.pnl[df.pnl < 0]
    liq = df.pnl.sum()
    pico = eq.cummax(); dd = (pico - eq).max(); ddp = ((pico - eq) / pico).max() * 100
    pd_dia = df.groupby("dia").pnl.sum()
    pregoes = len(set(eq.index.date))
    se = df.pts.std(ddof=1) / np.sqrt(len(df))
    dur = (df.t_saida - df.t).dt.total_seconds() / 60
    br = lambda v, c=2: b.num_br(float(v), c)
    compras, vendas = df[df.lado == 1], df[df.lado == -1]
    return {
        "Líquido R$": br(liq),
        "Retorno s/ R$1.000": br(liq / 10, 1) + "%",
        "Capital final R$": br(b.CAP0 + liq),
        "Lucro bruto / Prejuízo bruto R$": f"{br(g.sum())} / −{br(p.sum())}",
        "Custos pagos R$": br(len(df) * b.FEE_RT),
        "Trades": str(len(df)),
        "Ganhos / Perdas / Zero": f"{len(g)} / {len(p)} / {len(df)-len(g)-len(p)}",
        "Taxa de acerto": br(100 * len(g) / len(df), 1) + "%",
        "Breakeven (acerto p/ empatar)": br(100 * p.mean() / (g.mean() + p.mean()), 1) + "%",
        "Ganho médio / Perda média R$": f"{br(g.mean())} / −{br(p.mean())}",
        "Payoff (ganho médio ÷ perda média)": br(g.mean() / p.mean()),
        "Fator de lucro (bruto ganho ÷ perda)": br(g.sum() / p.sum()),
        "Expectativa R$/trade": br(liq / len(df)),
        "Expectativa pts/trade [IC 95%]": f"{br(df.pts.mean(),1)} [{br(df.pts.mean()-1.96*se,1)} ; {br(df.pts.mean()+1.96*se,1)}]",
        "Maior ganho / Maior perda R$": f"{br(g.max())} / −{br(p.max())}",
        "Máx. ganhos seguidos / perdas seguidas": f"{seq_max(df.pnl > 0)} / {seq_max(df.pnl < 0)}",
        "Drawdown máximo R$": br(dd),
        "Drawdown máximo %": br(ddp, 1) + "%",
        "Fator de recuperação (líquido ÷ DD)": br(liq / dd),
        "Caixa mínimo R$": br(eq.min()),
        "Pregões / com trade": f"{pregoes} / {df.dia.nunique()}",
        "Dias positivos / negativos": f"{(pd_dia > 0).sum()} / {(pd_dia < 0).sum()}",
        "Melhor dia / Pior dia R$": f"{br(pd_dia.max())} / {br(pd_dia.min())}",
        "Média R$/pregão": br(liq / pregoes),
        "Trades por pregão": br(len(df) / pregoes, 1),
        "Duração mediana (máx) min": f"{br(dur.median(),0)} ({br(dur.max(),0)})",
        "Compras: n / acerto / R$": f"{len(compras)} / {br(100*(compras.pnl>0).mean(),1)}% / {br(compras.pnl.sum())}",
        "Vendas: n / acerto / R$": f"{len(vendas)} / {br(100*(vendas.pnl>0).mean(),1)}% / {br(vendas.pnl.sum())}",
    }


def main():
    d = b.ler(V26, "M5")
    cols = {}
    for jn, a, z in b.JANELAS:
        cols[jn] = ficha(*b.simula(d, ini=a, fim=z, **b.MELHOR))
    t = pd.DataFrame(cols)
    print("MELHOR ATUAL: EMA 9/21/34/100/200, saida na quebra, M5, WINV26, R$1.000, 1 contrato", flush=True)
    print(t.to_string(), flush=True)
    t.to_csv(Path(__file__).with_suffix(".csv"), encoding="utf-8-sig")


if __name__ == "__main__":
    main()
