"""Os "4Ds dos investimentos" do vídeo, calculados sobre a curva da carteira.

  1. Rentabilidade — bateu o Ibovespa e o CDI? (CAGR, total, ano a ano)
  2. Risco         — volatilidade, beta, queda máxima, Sharpe/Sortino
  3. Ciclos        — como foi nas altas e nas quedas do Ibovespa
                     (regimes detectados por ±20% e captura de alta/baixa)
  4. Técnicos      — taxa de acerto e payoff das operações (ação × período)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DIAS_ANO = 252


def _cagr(s: pd.Series) -> float:
    s = s.dropna()
    if len(s) < 2:
        return np.nan
    anos = (s.index[-1] - s.index[0]).days / 365.25
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / anos) - 1) if anos > 0 else np.nan


def _max_dd(s: pd.Series) -> tuple[float, int]:
    pico = s.cummax()
    dd = s / pico - 1
    # duração máxima debaixo d'água, em pregões
    debaixo = (dd < 0).astype(int)
    dur = debaixo.groupby((debaixo == 0).cumsum()).cumsum().max()
    return float(dd.min()), int(dur)


def regimes_ibov(ibov: pd.Series, limiar: float = 0.20) -> list[dict]:
    """Divide o Ibovespa em pernas de alta e de queda de pelo menos `limiar`."""
    s = ibov.dropna()
    if s.empty:
        return []
    pernas, tipo, ini, ext = [], None, s.index[0], s.iloc[0]
    ext_data = s.index[0]
    for d, v in s.items():
        if tipo in (None, "alta"):
            if v > ext:
                ext, ext_data = v, d
            elif v <= ext * (1 - limiar):
                if tipo == "alta":
                    pernas.append(("alta", ini, ext_data))
                tipo, ini, ext, ext_data = "queda", ext_data, v, d
        if tipo in (None, "queda"):
            if v < ext:
                ext, ext_data = v, d
            elif v >= ext * (1 + limiar):
                if tipo == "queda":
                    pernas.append(("queda", ini, ext_data))
                tipo, ini, ext, ext_data = "alta", ext_data, v, d
    if tipo:
        pernas.append((tipo, ini, s.index[-1]))
    return [{"tipo": t, "inicio": a, "fim": b} for t, a, b in pernas if b > a]


def calcular(carteira: pd.Series, ibov: pd.Series, cdi: pd.Series,
             operacoes: pd.DataFrame | None = None, giro: pd.Series | None = None) -> dict:
    c = carteira.dropna()
    ib = ibov.reindex(c.index).ffill()
    cd = cdi.reindex(c.index).ffill()
    rc, ri, rcdi = c.pct_change().dropna(), ib.pct_change().dropna(), cd.pct_change().fillna(0)

    # 1. Rentabilidade
    anual = pd.DataFrame({
        "carteira": c.resample("YE").last().pct_change(),
        "ibov": ib.resample("YE").last().pct_change(),
        "cdi": cd.resample("YE").last().pct_change(),
    })
    # primeiro ano parcial: relativo ao primeiro dia
    primeiro = c.index[0].year
    anual.loc[anual.index.year == primeiro, "carteira"] = c[c.index.year == primeiro].iloc[-1] / c.iloc[0] - 1
    anual.loc[anual.index.year == primeiro, "ibov"] = ib[ib.index.year == primeiro].iloc[-1] / ib.iloc[0] - 1
    anual.loc[anual.index.year == primeiro, "cdi"] = cd[cd.index.year == primeiro].iloc[-1] / cd.iloc[0] - 1
    anual.index = anual.index.year
    cagr, cagr_i, cagr_c = _cagr(c), _cagr(ib), _cagr(cd)
    rent = {
        "retorno_total": float(c.iloc[-1] / c.iloc[0] - 1),
        "cagr": cagr, "cagr_ibov": cagr_i, "cagr_cdi": cagr_c,
        "excesso_ibov": cagr - cagr_i, "excesso_cdi": cagr - cagr_c,
        "anos_bate_ibov": int((anual.carteira > anual.ibov).sum()), "anos": int(len(anual)),
        "anual": {int(a): {k: (None if pd.isna(v) else float(v)) for k, v in r.items()} for a, r in anual.iterrows()},
    }

    # 2. Risco
    vol = float(rc.std() * np.sqrt(DIAS_ANO))
    alinh = pd.concat([rc, ri], axis=1, join="inner").dropna()
    beta = float(np.cov(alinh.iloc[:, 0], alinh.iloc[:, 1])[0, 1] / alinh.iloc[:, 1].var()) if len(alinh) > 20 else np.nan
    exc = rc - rcdi.reindex(rc.index).fillna(0)
    sharpe = float(exc.mean() / exc.std() * np.sqrt(DIAS_ANO)) if exc.std() > 0 else np.nan
    neg = exc[exc < 0]
    sortino = float(exc.mean() / np.sqrt((neg ** 2).mean()) * np.sqrt(DIAS_ANO)) if len(neg) else np.nan
    dd, dur = _max_dd(c)
    dd_i, _ = _max_dd(ib)
    mens = c.resample("ME").last().pct_change().dropna()
    risco = {"volatilidade": vol, "volatilidade_ibov": float(ri.std() * np.sqrt(DIAS_ANO)),
             "beta": beta, "sharpe": sharpe, "sortino": sortino,
             "max_drawdown": dd, "max_drawdown_ibov": dd_i, "dias_drawdown": dur,
             "pior_mes": float(mens.min()) if len(mens) else np.nan,
             "recuperacao": float(rent["retorno_total"] / abs(dd)) if dd < 0 else np.nan}

    # 3. Ciclos de mercado
    regs = []
    for r in regimes_ibov(ib):
        a, b = r["inicio"], r["fim"]
        regs.append({"tipo": r["tipo"], "inicio": str(a.date()), "fim": str(b.date()),
                     "ibov": float(ib.loc[b] / ib.loc[a] - 1), "carteira": float(c.loc[b] / c.loc[a] - 1)})
    mi = ib.resample("ME").last().pct_change().dropna()
    mc = mens.reindex(mi.index)
    sobe, desce = mi > 0, mi < 0
    ciclos = {
        "regimes": regs,
        "captura_alta": float(mc[sobe].mean() / mi[sobe].mean()) if sobe.any() else np.nan,
        "captura_queda": float(mc[desce].mean() / mi[desce].mean()) if desce.any() else np.nan,
        "meses_positivos": float((mens > 0).mean()) if len(mens) else np.nan,
    }

    # 4. Técnicos
    tec = {}
    if operacoes is not None and len(operacoes):
        r = operacoes.retorno.dropna()
        ganho, perda = r[r > 0], r[r <= 0]
        tec = {"operacoes": int(len(r)), "taxa_acerto": float((r > 0).mean()),
               "payoff": float(ganho.mean() / abs(perda.mean())) if len(ganho) and len(perda) and perda.mean() != 0 else np.nan,
               "ganho_medio": float(ganho.mean()) if len(ganho) else np.nan,
               "perda_media": float(perda.mean()) if len(perda) else np.nan,
               "bate_ibov": float((operacoes.retorno > operacoes.retorno_ibov).mean())}
    if giro is not None and len(giro) > 1:
        tec["giro_medio"] = float(giro.iloc[1:].mean())
    return {"rentabilidade": rent, "risco": risco, "ciclos": ciclos, "tecnicos": tec}


def resumo(m: dict) -> dict:
    """Linha plana para tabelas e ranking de estudos."""
    r, k, t = m["rentabilidade"], m["risco"], m["tecnicos"]
    return {"cagr": r["cagr"], "cagr_ibov": r["cagr_ibov"], "cagr_cdi": r["cagr_cdi"],
            "excesso_ibov": r["excesso_ibov"], "excesso_cdi": r["excesso_cdi"],
            "sharpe": k["sharpe"], "volatilidade": k["volatilidade"], "beta": k["beta"],
            "max_drawdown": k["max_drawdown"], "taxa_acerto": t.get("taxa_acerto"),
            "payoff": t.get("payoff"), "giro_medio": t.get("giro_medio"),
            "anos_bate_ibov": f'{r["anos_bate_ibov"]}/{r["anos"]}'}
