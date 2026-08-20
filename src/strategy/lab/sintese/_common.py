"""Andaime compartilhado da familia `sintese` (etapa E3) -- NAO e uma
estrategia.

So uma peca e reaproveitada entre as duas sinteses: a mascara de
elegibilidade "iliquidez relativa ao grupo de risco" que sobreviveu ao
controle C2 em `iliquidez_06_relativa_ao_grupo`
(`src/strategy/lab/iliquidez/hip_06.py`). Reproduzida aqui (nao importada de
la) porque aquele arquivo nao expoe a mascara como funcao -- e para nao
editar arquivo existente do repositorio (restricao do E3). O algoritmo e
byte-a-byte o mesmo: sem dado de setor no repositorio, o grupo de pares e
aproximado pela VOLATILIDADE REALIZADA de 63 pregoes (papeis de vol
parecida tendem a ser do mesmo tipo de negocio); dentro de cada terco de
vol, os 33% de MENOR giro financeiro relativos aos PARES daquele terco
entram no universo elegivel. Score final de qualquer sintese que use esta
mascara e SEMPRE come do proprio proxy da sintese (momentum, qualidade,
o que for) restrito a este universo -- a mascara nunca decide RANKING,
so ELEGIBILIDADE.

Ambas as sinteses de E3 usam esta mascara como o eixo CONSTANTE da
combinacao: `iliquidez_06` foi a hipotese de maior CAGR mediano entre as 5
sobreviventes do C2 (18,41%) e a familia iliquidez dominou a busca (4 das
10 primeiras). O que varia entre as duas sinteses e o SEGUNDO mecanismo
somado a este universo -- ver `hip_01.py` (ranking por qualidade/retorno
ajustado ao risco) e `hip_02.py` (dimensionamento por orcamento de risco
com stop ATR).
"""
from __future__ import annotations

import pandas as pd

from core.indicators import historical_volatility

VOL_WINDOW = 63
ADTV_WINDOW = 252
ADTV_FLOOR = 100_000.0
WITHIN_BUCKET_PCT = 0.33


def group_relative_illiquidity_mask(
    panels: dict[str, pd.DataFrame],
    ibov: pd.DataFrame,
    vol_window: int = VOL_WINDOW,
    adtv_window: int = ADTV_WINDOW,
    adtv_floor: float = ADTV_FLOOR,
    within_bucket_pct: float = WITHIN_BUCKET_PCT,
) -> pd.DataFrame:
    """Mascara booleana (index=ibov.index, colunas=tickers) de elegibilidade.

    `True` no ticker/dia em que o papel esta nos `within_bucket_pct` de MENOR
    giro financeiro DENTRO do proprio terco de volatilidade realizada, entre
    os papeis com ADTV acima do piso de capacidade. Computada so nos fins de
    mes (unico dia em que o score e consultado nas duas sinteses) e mantida
    constante (`ffill`) ate o proximo fim de mes -- sem uso de dado futuro,
    igual ao original em `iliquidez/hip_06.py`.
    """
    from core.calendar import is_month_end

    turnover: dict[str, pd.Series] = {}
    vol: dict[str, pd.Series] = {}
    for t, df in panels.items():
        if t.startswith("^") or "volume" not in df.columns:
            continue
        tv = (df["close"] * df["volume"]).dropna()
        adtv = tv.rolling(adtv_window, min_periods=adtv_window // 2).median()
        turnover[t] = adtv.reindex(ibov.index).ffill()
        v = historical_volatility(df["close"], window=vol_window)
        vol[t] = v.reindex(ibov.index).ffill()
    if not turnover:
        return pd.DataFrame(index=ibov.index)

    adtv_df = pd.DataFrame(turnover)
    vol_df = pd.DataFrame(vol)

    me = is_month_end(ibov.index)
    me_dates = ibov.index[me.reindex(ibov.index).fillna(False).astype(bool)]

    eligible_rows: dict[pd.Timestamp, pd.Series] = {}
    for d in me_dates:
        adtv_row = adtv_df.loc[d]
        vol_row = vol_df.loc[d]
        valid = adtv_row.notna() & vol_row.notna() & (adtv_row >= adtv_floor)
        if valid.sum() < 6:
            eligible_rows[d] = pd.Series(False, index=adtv_df.columns)
            continue
        vol_valid = vol_row[valid]
        try:
            bucket = pd.qcut(vol_valid, 3, labels=False, duplicates="drop")
        except ValueError:
            eligible_rows[d] = pd.Series(False, index=adtv_df.columns)
            continue
        elig = pd.Series(False, index=adtv_df.columns)
        for b in sorted(bucket.dropna().unique()):
            members = bucket[bucket == b].index
            if len(members) < 3:
                continue
            giro_grupo = adtv_row.loc[members]
            rank_pct = giro_grupo.rank(ascending=True, pct=True)
            elig.loc[rank_pct[rank_pct <= within_bucket_pct].index] = True
        eligible_rows[d] = elig

    return pd.DataFrame(eligible_rows).T.reindex(ibov.index).ffill().fillna(False).astype(bool)
