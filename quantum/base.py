"""Base em memória: carrega o SQLite uma vez e serve painéis por data.

`painel(D)` responde "o que um investidor sabia no fechamento de D?":
  - fundamentos: só documentos com `dt_receb < D` (entregues antes do dia)
  - preços: até o fechamento de D, inclusive
  - quantidade de ações do último documento, corrigida pelos desdobramentos
    ocorridos DEPOIS dele e até D (senão o valor de mercado pula 10× num
    grupamento entre dois balanços)

Valor de mercado usa o preço SEM ajuste (o `close` do Yahoo vem ajustado por
desdobramento para trás; aqui ele é desfeito) vezes as ações da época.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from . import armazem

ALIQUOTA_IR = 0.34
MAX_IDADE_BALANCO_DIAS = 460   # empresa que parou de entregar ITR/DFP sai do universo
MAX_DIAS_SEM_NEGOCIO = 10


class Base:
    def __init__(self, con=None):
        own = con is None
        con = con or armazem.conectar()
        try:
            self.empresas = armazem.ler(con, "SELECT * FROM empresas").set_index("cnpj")
            self.tickers = armazem.ler(con, "SELECT * FROM tickers")
            dem = armazem.ler(con, "SELECT * FROM demonstracoes")
            pr = armazem.ler(con, "SELECT ticker, data, close, adj_close, volume, dividendo, split FROM precos")
            idx = armazem.ler(con, "SELECT serie, data, valor FROM indices")
        finally:
            if own:
                con.close()
        dem["dt_receb"] = pd.to_datetime(dem.dt_receb)
        dem["dt_refer"] = pd.to_datetime(dem.dt_refer)
        self.dem = dem.sort_values(["dt_receb", "dt_refer"])
        pr["data"] = pd.to_datetime(pr.data)
        wide = {c: pr.pivot(index="data", columns="ticker", values=c).sort_index()
                for c in ("close", "adj_close", "volume", "dividendo", "split")}
        ibov = wide["close"].get("^BVSP")
        self.ibov = ibov.dropna() if ibov is not None else pd.Series(dtype=float)
        for k in wide:
            wide[k] = wide[k].drop(columns=["^BVSP"], errors="ignore")
        self.close = wide["close"]
        self.adj = wide["adj_close"]
        self.volume = wide["volume"].fillna(0.0)
        self.div = wide["dividendo"].fillna(0.0)
        sp = wide["split"].fillna(0.0).replace(0.0, 1.0)
        self.split = sp
        # fator para desfazer o ajuste: raw_t = close_t × Π split_s (s > t)
        fator = sp[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
        self.close_raw = self.close * fator
        self.fin_vol = (self.close * self.volume).rolling(21, min_periods=10).mean()
        self.datas = self.close.index
        idx["data"] = pd.to_datetime(idx.data)
        self.cdi = idx[idx.serie == "CDI"].set_index("data").valor.sort_index()
        tk = self.tickers[self.tickers.ticker.isin(self.close.columns)]
        self.ticker_cnpj = tk.set_index("ticker").cnpj
        self.por_unit = (tk.set_index("ticker").acoes_por_unit if "acoes_por_unit" in tk
                         else pd.Series(1.0, index=tk.ticker))
        self._cache: dict = {}

    # ── utilidades de calendário ───────────────────────────────────────────
    def pregao_ate(self, d) -> pd.Timestamp | None:
        """Último pregão <= d."""
        i = self.datas.searchsorted(pd.Timestamp(d), side="right") - 1
        return self.datas[i] if i >= 0 else None

    def pregao_depois(self, d, n: int = 1) -> pd.Timestamp | None:
        i = self.datas.searchsorted(pd.Timestamp(d), side="right") - 1 + n
        return self.datas[i] if 0 <= i < len(self.datas) else None

    # ── fundamentos conhecidos em D ────────────────────────────────────────
    def fundamentos_em(self, d: pd.Timestamp) -> pd.DataFrame:
        conhecido = self.dem[self.dem.dt_receb < d]
        ult = conhecido.sort_values("dt_refer").groupby("cnpj").tail(1).set_index("cnpj")
        ult = ult[(d - ult.dt_refer).dt.days <= MAX_IDADE_BALANCO_DIAS]
        # ações: se o último documento não trouxe, usa o mais recente que trouxe
        com_acoes = conhecido[conhecido.acoes.notna()].sort_values("dt_refer").groupby("cnpj").tail(1)
        ult["acoes_dt"] = com_acoes.set_index("cnpj").dt_refer.reindex(ult.index)
        ult["acoes"] = com_acoes.set_index("cnpj").acoes.reindex(ult.index)
        return ult

    def _dy_em(self, d: pd.Timestamp) -> pd.Series:
        """Dividend yield 12m em d (proventos dos 365 dias até d ÷ preço em d)."""
        janela = self.div.loc[(self.div.index > d - pd.Timedelta(days=365)) & (self.div.index <= d)]
        px = self.close.loc[:d].ffill().iloc[-1] if len(self.close.loc[:d]) else None
        if px is None:
            return pd.Series(dtype=float)
        return janela.sum() / px

    def painel(self, d) -> pd.DataFrame:
        """Uma linha por EMPRESA (ticker mais líquido) com todos os indicadores em d."""
        d = self.pregao_ate(d)
        if d is None:
            return pd.DataFrame()
        if d in self._cache:
            return self._cache[d]
        hist = self.close.loc[:d]
        ultimo_negocio = hist.apply(lambda s: s.last_valid_index())
        vivo = (d - pd.to_datetime(ultimo_negocio)).dt.days <= MAX_DIAS_SEM_NEGOCIO
        liq = self.fin_vol.loc[:d].iloc[-1]
        cand = pd.DataFrame({"ticker": liq.index, "liquidez": liq.values})
        cand = cand[vivo.reindex(cand.ticker).fillna(False).values & cand.liquidez.notna().values]
        cand["cnpj"] = self.ticker_cnpj.reindex(cand.ticker).values
        cand = cand.dropna(subset=["cnpj"]).sort_values("liquidez").groupby("cnpj").tail(1)

        f = self.fundamentos_em(d)
        p = cand.set_index("cnpj").join(f, how="inner")
        if p.empty:
            self._cache[d] = p
            return p
        t = p.ticker.values
        # ações corrigidas pelos desdobramentos depois do documento
        fat = []
        for tk, dt_a in zip(t, p.acoes_dt):
            if pd.isna(dt_a):
                fat.append(np.nan)
                continue
            s = self.split[tk]
            fat.append(float(s[(s.index > dt_a) & (s.index <= d)].prod()))
        p["acoes_d"] = p.acoes * np.array(fat)
        p["preco"] = self.close_raw.loc[:d, t].ffill().iloc[-1].values
        # unit (ex.: TAEE11 = 1 ON + 2 PN): preço por AÇÃO = preço da unit ÷ ações na unit
        por_unit = self.por_unit.reindex(t).values  # NaN (composição ilegível) → mcap em branco
        p["mcap"] = p.preco / por_unit * p.acoes_d
        p["ev"] = p.mcap + p.divida.fillna(0) - p.caixa.fillna(0)
        fin = self.empresas.financeira.reindex(p.index).fillna(0).astype(bool)
        p["financeira"] = fin.values
        pos = lambda s: s.where(s > 0)
        p["pl_ind"] = p.mcap / pos(p.lucro_contr)
        p["ey"] = p.lucro_contr / p.mcap                     # lucro/preço: ordena negativos também
        p["pvp"] = p.mcap / pos(p.pl_contr)
        p["ev_ebit"] = (p.ev / pos(p.ebit)).where(~p.financeira)
        p["roe"] = p.lucro_contr / pos(p.pl_contr)
        cap = pos(p.pl.fillna(0) + p.divida.fillna(0) - p.caixa.fillna(0))
        p["roic"] = (p.ebit * (1 - ALIQUOTA_IR) / cap).where(~p.financeira)
        p["roa"] = p.lucro / pos(p.ativo)
        rec = pos(p.receita)
        p["margem_bruta"] = (p.lucro_bruto / rec).where(~p.financeira)
        p["margem_ebit"] = (p.ebit / rec).where(~p.financeira)
        p["margem_liquida"] = p.lucro / rec
        p["div_liq_pl"] = ((p.divida.fillna(0) - p.caixa.fillna(0)) / pos(p.pl)).where(~p.financeira)

        # proventos: DY 12m e média de 3 anos (D, D−1a, D−2a), como no vídeo
        dys = [self._dy_em(self.pregao_ate(d - pd.DateOffset(years=k)) or d).reindex(t).values for k in range(3)]
        p["dy"] = dys[0]
        p["dy_med_3a"] = np.nanmean(np.vstack(dys), axis=0) if len(t) else []
        p["pagou_3a"] = (np.vstack(dys) > 0).all(axis=0)

        # momento e risco (preço ajustado por proventos)
        adj = self.adj.loc[:d, t].ffill()
        def ret(a, b):
            if len(adj) <= a:
                return np.full(len(t), np.nan)
            return (adj.iloc[-1 - b] / adj.iloc[-1 - a] - 1).values
        p["mom_12_1"] = ret(252, 21)
        p["mom_6"] = ret(126, 0)
        p["vol_1a"] = (adj.pct_change(fill_method=None).iloc[-252:].std() * np.sqrt(252)).values
        p["data"] = d
        p = p.reset_index()
        self._cache[d] = p
        return p

    def multiplos_historicos(self, cnpj: str, ticker: str, freq: str = "QE") -> pd.DataFrame:
        """P/L, P/VP, EV/EBIT, ROE e DY de UMA empresa ao fim de cada período,
        com as mesmas regras de `painel` (balanço só após a entrega), sem montar o
        painel do mercado inteiro."""
        dem = self.dem[self.dem.cnpj == cnpj]
        if ticker not in self.close or dem.empty:
            return pd.DataFrame()
        px = self.close_raw[ticker].dropna()
        if px.empty:
            return pd.DataFrame()
        por_unit = float(self.por_unit.get(ticker, 1.0))
        sp = self.split[ticker]
        div = self.div[ticker]
        close = self.close[ticker].ffill()
        linhas = []
        for d in pd.date_range(px.index[0], self.datas[-1], freq=freq):
            d = self.pregao_ate(d)
            k = dem[dem.dt_receb < d]
            if k.empty:
                continue
            f = k.sort_values("dt_refer").iloc[-1]
            if (d - f.dt_refer).days > MAX_IDADE_BALANCO_DIAS:
                continue
            ka = k[k.acoes.notna()].sort_values("dt_refer")
            if ka.empty or d not in px.index and px.loc[:d].empty:
                continue
            a = ka.iloc[-1]
            acoes = a.acoes * float(sp[(sp.index > a.dt_refer) & (sp.index <= d)].prod())
            mcap = float(px.loc[:d].iloc[-1]) / por_unit * acoes
            ev = mcap + (f.divida or 0) - (f.caixa or 0)
            dy = div[(div.index > d - pd.Timedelta(days=365)) & (div.index <= d)].sum() / close.loc[:d].iloc[-1]
            linhas.append({"data": str(d.date()),
                           "pl": mcap / f.lucro_contr if f.lucro_contr and f.lucro_contr > 0 else None,
                           "pvp": mcap / f.pl_contr if f.pl_contr and f.pl_contr > 0 else None,
                           "ev_ebit": ev / f.ebit if f.ebit and f.ebit > 0 else None,
                           "roe": f.lucro_contr / f.pl_contr if f.pl_contr and f.pl_contr > 0 else None,
                           "dy": float(dy)})
        return pd.DataFrame(linhas)

    def cobertura(self, d) -> dict:
        """Quantas empresas com balanço vivo têm preço — mede o viés de sobrevivência."""
        d = self.pregao_ate(d)
        f = self.fundamentos_em(d)
        f = f[f.index.isin(self.tickers.cnpj)]   # só quem tem ação listada
        p = self.painel(d)
        return {"com_balanco": int(len(f)), "com_preco": int(len(p)),
                "pct": float(len(p) / len(f)) if len(f) else 0.0}


@lru_cache(maxsize=1)
def _base_cache(chave: str) -> Base:
    return Base()


def base_atual() -> Base:
    """Base compartilhada pelo servidor; recarrega quando o banco muda."""
    from . import config
    m = config.BANCO.stat().st_mtime if config.BANCO.exists() else 0
    return _base_cache(str(m))
