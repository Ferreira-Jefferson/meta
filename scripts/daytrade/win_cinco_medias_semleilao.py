"""VERSAO SEM LEILOES (2026-10-06, refazer A3) de win_cinco_medias.py. A original NAO foi alterada.
Diferenca: `simula` zera na `ultima_continua` do dia (ao close do ultimo negocio continuo) quando `d` traz a coluna
`ultima_continua` (dados de `carregar_sl`); sem a coluna, comporta-se exatamente como a original (zera em c[-1]).
Os trades ganham a coluna `motivo` (zera_fim|saida|stop). `carregar_sl` usa src/market_data_intraday/win_sem_leiloes.py.

WIN — WinCincoMedias (v2.03, 2026-10-06: M30, EMAs 2/4/6/17/33, saida EMA4 + climax de volume contra + stop que aperta + Supertrend H1 contra). Referencia Python do EA mt5/WinCincoMedias.mq5.
A v1 (M5, 9/21/34/100/200, saida 21) continua reproduzivel: rodar_janelas(tf="5min", periodos=(9,21,34,100,200), ema_saida=21).
Estrategia NOVA e separada: nao tem relacao com o EA mt5/Win.mq5 (roxa/verde).

Tudo o que foi medido ate' 2026-10-06 sobre o WIN M5 esta' aqui, em um arquivo
so', sem depender dos scripts de pesquisa. O EA reproduz estas regras.

SINAL (barra M5 fechada, "barra do sinal")
  5 EMAs do fechamento: 9, 21, 34, 100, 200.
  COMPRA: EMA9 > EMA21 > EMA34 > EMA100 > EMA200 e as 5 subindo (EMA[t] > EMA[t-1]).
  VENDA : espelho.

FILTRO DE LADO PELO MES (regime)
  Abertura do mes = abertura da 1a barra do 1o pregao do mes.
  O mes so' conta a partir do dia em que o contrato virou o principal (dia
  seguinte ao vencimento do anterior); se o mes comecou em outro contrato, a
  "abertura do mes" e' a abertura do 1o pregao do contrato atual.
  Nos 5 primeiros pregoes do mes: regime = direcao do mes ANTERIOR
      (fechamento da ultima barra do mes anterior - abertura do mes anterior).
  Do 6o pregao em diante: regime = sinal(fechamento da barra do sinal - abertura do mes).
  Regime +1 -> so' compra; -1 -> so' vende; 0 (sem mes anterior / preco = abertura) -> os dois.

ENTRADA
  Ordem-LIMITE no fechamento da barra do sinal, valida 5 barras; cancela se o
  alinhamento sumir. Sem entrada a partir das 18:20. Uma posicao por vez.

SAIDA (a mercado na abertura da barra seguinte)
  Operacao A FAVOR do regime: sai quando uma barra FECHA do outro lado da EMA21.
  Operacao com regime 0: sai quando o alinhamento das 5 EMAs quebra.
  Fim do pregao: sai depois da barra das 18:20; e zera no fechamento da ultima barra.

Resultado de referencia (WIN@ sem ajuste, 2026, 14 janelas mensais, R$1.000 por
janela, 1 contrato, R$0,50/contrato, 1 tick de deslize nas saidas):
  +R$7.490,10 · 11/14 janelas positivas · pior janela -R$272,30 · PF 1,54 ·
  maior DD R$794,70 · 413 trades. (antes, EMAs puras: +R$4.968,60, 10/14, -987,10)
  NAO validado fora de 2026 (escolhido sobre os mesmos 9 meses).

Uso:  python scripts/daytrade/win_cinco_medias.py   (roda a validacao mes a mes)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ---- parametros (os mesmos inputs do EA) -----------------------------------
EMAS = (2, 4, 6, 17, 33)        # v2 (M30). v1 era M5 com (9, 21, 34, 100, 200) e saida 21
EMA_SAIDA = 4           # operacao a favor sai no fechamento do outro lado desta EMA (v1: 21)
TF = "30min"            # tempo grafico FIXO da estrategia (v1: "5min")
# saida por CLIMAX DE VOLUME CONTRA (v2.01): vela fechada com volume relativo no
# quantil SAIDA_VOL_Q do historico anterior e corpo contra a posicao -> sai na abertura seguinte
SAIDA_VOL = True
SAIDA_VOL_Q = 0.90
VOL_PREGOES = 20        # mediana do volume no MESMO horario dos N pregoes anteriores
VOL_MIN_PREG = 5        # minimo de pregoes para a mediana
VOL_MIN_HIST = 100      # minimo de velas no historico do quantil
# STOP QUE APERTA (v2.02): depois de STOP_APERTA_N velas fechadas desde a entrada, se o
# fechamento esta' no NEGATIVO, poe stop a mercado em entrada -/+ STOP_APERTA_K x ATR(14)
# da vela do sinal (vale da vela seguinte em diante; nunca afrouxa). N=4..10 sao inertes
# (o trade negativo ja' saiu pela EMA4/quebra); N=2 foi o melhor em 2026 e 2025.
STOP_APERTA_N = 2
STOP_APERTA_K = 1.0
# SAIDA PELO SUPERTREND H1 (v2.03): Supertrend(ST_H1_N, ST_H1_M) calculado em H1 desde o inicio do
# contrato, so' com barras H1 JA' FECHADAS na vela M30 do sinal; se a direcao dele esta' CONTRA a posicao,
# sai na abertura seguinte. 2026 +8.859,71 / 2025 +566,85 / 2022-24 +2.444,78 (v2.02: +8.377 / +284 / +1.405)
SAIDA_ST_H1 = True
ST_H1_N = 10
ST_H1_M = 3.0
DIAS_MES_ANTERIOR = 5   # pregoes iniciais do mes que usam a direcao do mes anterior
TTL_BARRAS = 5          # validade da ordem-limite de entrada, em barras M5
ULTIMA_ENTRADA = pd.Timestamp("18:20").time()
# ---- custos da simulacao ---------------------------------------------------
PONTO_BRL = 0.20
TICK = 5.0
CUSTO_RT = 0.50
CAPITAL = 1000.0
MARGEM = 100.0


def emas(c: pd.Series, periodos=EMAS) -> list[pd.Series]:
    return [c.ewm(span=p, adjust=False).mean() for p in periodos]


def alinhamento(d: pd.DataFrame, periodos=EMAS, inclina=None) -> np.ndarray:
    """+1 compra, -1 venda, 0 nada — na barra fechada.
    inclina = indices das medias que precisam estar subindo/descendo (None = todas)."""
    es = emas(d["c"], periodos)
    up = pd.Series(True, index=d.index); dn = up.copy()
    for a, b in zip(es, es[1:]):
        up &= a > b; dn &= a < b
    for i, e in enumerate(es):
        if inclina is None or i in inclina:
            up &= e.diff() > 0; dn &= e.diff() < 0
    return np.where(up, 1, np.where(dn, -1, 0))


def zona_ok(d: pd.DataFrame, periodos, zona) -> tuple[np.ndarray, np.ndarray]:
    """Filtro de posicao do preco na barra do sinal (compra, venda). None = sem filtro.
      'corpo>m1'  : corpo inteiro alem da media 1
      'candle>m1' : candle inteiro (pavio) alem da media 1
      'entre12'   : fechamento entre a media 1 e a 2 (recuo)
      'entre23'   : fechamento entre a media 2 e a 3
      'toque2'    : candle toca a media 2 e fecha do lado certo dela
    """
    n = len(d)
    if zona is None:
        return np.ones(n, bool), np.ones(n, bool)
    es = emas(d["c"], periodos)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    lo, hi = np.minimum(o, c), np.maximum(o, c)
    m1, m2, m3 = es[0], es[1], es[2]
    z = {
        "corpo>m1": (lo > m1, hi < m1),
        "candle>m1": (l > m1, h < m1),
        "entre12": ((c <= m1) & (c > m2), (c >= m1) & (c < m2)),
        "entre23": ((c <= m2) & (c > m3), (c >= m2) & (c < m3)),
        "toque2": ((l <= m2) & (c > m2), (h >= m2) & (c < m2)),
    }[zona]
    return np.asarray(z[0], bool), np.asarray(z[1], bool)


def regime_mes(d: pd.DataFrame, rolagem=None) -> np.ndarray:
    """+1/-1/0 por barra, usando so' informacao ate' o fechamento da barra.
    `rolagem` = 1o dia em que o contrato de `d` virou o principal. O mes so' e'
    medido dali em diante (antes disso o contrato e' pouco negociado e a abertura
    dele nao representa o mercado — foi o erro da 1a versao do EA). Antes da
    rolagem o regime e' 0."""
    if rolagem is not None:
        rolagem = pd.Timestamp(rolagem)
        r = np.zeros(len(d), dtype=int)
        depois = d.index >= rolagem
        if depois.any():
            r[depois] = regime_mes(d[depois])
        return r
    mes = d.index.to_period("M")
    abertura = d["o"].groupby(mes).transform("first")
    r = pd.Series(np.sign(d["c"] - abertura).astype(int).values, index=d.index)
    dia = pd.Series(d.index.normalize(), index=d.index)
    n_pregao = dia.groupby(mes).transform(lambda s: s.rank(method="dense")).values
    ultimo = r.groupby(mes).last()                  # direcao do mes ao fim dele
    anterior = pd.Series(mes, index=d.index).map(lambda p: ultimo.get(p - 1, 0)).astype(int)
    return np.where(n_pregao <= DIAS_MES_ANTERIOR, anterior.values, r.values)


def colunas_volume(d: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta 'vrel' = volume / mediana do mesmo horario nos VOL_PREGOES pregoes
    ANTERIORES (a vela j entra so' na propria vrel, nunca na mediana). Volume nao tem
    rolagem, entao pode ser calculado no historico inteiro."""
    d = d.copy()
    hh = pd.Series(d.index.time, index=d.index)
    v = d["v"].astype(float)
    med = v.groupby(hh).transform(lambda x: x.rolling(VOL_PREGOES, min_periods=VOL_MIN_PREG).median().shift(1))
    d["vrel"] = v / med
    return d


def supertrend(d: pd.DataFrame, n: int, m: float) -> np.ndarray:
    """Direcao do Supertrend (+1/-1, 0 enquanto o ATR(n) Wilder nao tem n barras). Banda = (h+l)/2 +- m x ATR."""
    pc = d["c"].shift()
    tr = pd.concat([d["h"] - d["l"], (d["h"] - pc).abs(), (d["l"] - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean().values
    h, l, c = d["h"].values, d["l"].values, d["c"].values
    N = len(c); dirr = np.zeros(N, int); fu = np.full(N, np.nan); fl = np.full(N, np.nan)
    hl2 = (h + l) / 2
    cur = 0
    for i in range(N):
        if np.isnan(a[i]):
            continue
        bu, bl = hl2[i] + m * a[i], hl2[i] - m * a[i]
        if i == 0 or np.isnan(fu[i - 1]):
            fu[i], fl[i] = bu, bl
            cur = 1 if c[i] >= hl2[i] else -1
        else:
            fu[i] = bu if (bu < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
            fl[i] = bl if (bl > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
            if cur == 1 and c[i] < fl[i]:
                cur = -1
            elif cur == -1 and c[i] > fu[i]:
                cur = 1
        dirr[i] = cur
    return dirr


def st_h1(d: pd.DataFrame, n: int = ST_H1_N, m: float = ST_H1_M) -> np.ndarray:
    """Direcao do Supertrend H1 vista em cada vela M30 de `d`, so' com H1 ja' fechadas:
    a vela M30 de :30 fecha junto com a H1 dela (usa a atual); a de :00 usa a H1 anterior."""
    h1 = d.resample("60min").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    s = pd.Series(supertrend(h1, n, m), index=h1.index)
    fl = d.index.floor("60min")
    cur = s.reindex(fl).values; prev = s.shift(1).reindex(fl).values
    return pd.Series(np.where(d.index.minute == 30, cur, prev)).fillna(0).astype(int).values


def simula(d: pd.DataFrame, ini, fim=None, rolagem=None, periodos=EMAS, inclina=None, zona=None,
           ema_saida=EMA_SAIDA, filtro_mes=True, extra=None, saida_vol=SAIDA_VOL,
           aperta=(STOP_APERTA_N, STOP_APERTA_K), saida_st=(ST_H1_N, ST_H1_M) if SAIDA_ST_H1 else None):
    """d = M5 de UM contrato (o,h,l,c; indice = inicio da barra). Indicadores sobre
    todo `d`; opera so' em [ini, fim). Devolve (trades, curva de caixa).
    extra = funcao f(d) -> (ok_compra, ok_venda), arrays bool alinhados a d.index,
    avaliados na barra do SINAL (ja' fechada). So' pode usar dados ate' essa barra
    (inclusive) — nunca a barra seguinte, onde a ordem e' executada."""
    est_all = alinhamento(d, periodos, inclina)
    zl_all, zs_all = zona_ok(d, periodos, zona)
    if extra is not None:
        el, es_ = extra(d)
        zl_all = zl_all & np.asarray(el, bool); zs_all = zs_all & np.asarray(es_, bool)
    reg_all = regime_mes(d, rolagem) if filtro_mes else np.zeros(len(d), dtype=int)
    e_saida_all = d["c"].ewm(span=ema_saida, adjust=False).mean().values
    if saida_vol:
        if "vrel" not in d.columns:
            d = colunas_volume(d)
        # limite = quantil SAIDA_VOL_Q das vrel ANTERIORES, desde o inicio do contrato (`d`),
        # com pelo menos VOL_MIN_HIST velas: nos ~6 primeiros pregoes do contrato nao ha saida por volume
        vthr = d["vrel"].expanding(min_periods=VOL_MIN_HIST).quantile(SAIDA_VOL_Q).shift(1)
        grande = (d["vrel"] >= vthr).fillna(False).values & vthr.notna().values
        corpo = np.sign(d["c"] - d["o"]).values
        vsl_all, vss_all = grande & (corpo < 0), grande & (corpo > 0)   # compra sai em vela de baixa; venda, de alta
    sel = d.index >= ini
    if fim is not None:
        sel &= d.index < fim
    idx = d.index[sel]
    o, h, l, c = (d[k].values[sel] for k in "ohlc")
    est, reg, e_saida = est_all[sel], reg_all[sel], e_saida_all[sel]
    zl, zs = zl_all[sel], zs_all[sel]
    if saida_vol:
        vsl, vss = vsl_all[sel], vss_all[sel]
    if saida_st is not None:
        sth1 = st_h1(d, *saida_st)[sel]
    dias, hora, n = idx.normalize(), idx.time, len(idx)
    ult = d["ultima_continua"].to_numpy(bool)[sel] if "ultima_continua" in d.columns else None

    pc = d["c"].shift()
    tr_ = pd.concat([d["h"] - d["l"], (d["h"] - pc).abs(), (d["l"] - pc).abs()], axis=1).max(axis=1)
    atr_all = tr_.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().values   # ATR(14) Wilder
    pos0 = int(np.flatnonzero(sel)[0]) if sel.any() else 0

    caixa = CAPITAL
    trades, curva = [], np.empty(n)
    pos = 0; preco = 0.0; a_favor = False; t_ent = None
    pend = 0; limite = 0.0; ttl = 0; pend_favor = False
    atr_e = np.nan; nb = 0; stop_x = -np.inf; t_ent_i = 0     # stop em "x" = lado * preco

    def fecha(saida, t, motivo="saida"):
        nonlocal caixa, pos
        pts = pos * (saida - preco)
        pnl = pts * PONTO_BRL - CUSTO_RT
        caixa += pnl
        trades.append(dict(entrada=t_ent, saida=idx[t], lado=pos, a_favor=a_favor, pts=pts, pnl=pnl, motivo=motivo))
        pos = 0

    for t in range(n):
        novo_dia = t == 0 or dias[t] != dias[t - 1]
        if novo_dia:
            pend = 0
        # 1) saida decidida no fechamento da barra anterior -> abertura desta
        if pos and t > 0 and not novo_dia:
            j = t - 1
            if hora[j] >= ULTIMA_ENTRADA:
                sai = True
            elif a_favor:
                sai = pos * (c[j] - e_saida[j]) <= 0
            else:
                sai = est[j] != pos
            if not sai and saida_vol:
                sai = bool(vsl[j]) if pos == 1 else bool(vss[j])
            if not sai and saida_st is not None:
                sai = sth1[j] == -pos
            if sai:
                fecha(o[t] - pos * TICK, t)
        # 2) ordem-limite pendente
        if pend and not pos:
            if (pend == 1 and l[t] <= limite) or (pend == -1 and h[t] >= limite):
                if caixa >= MARGEM:
                    pos, a_favor, t_ent = pend, pend_favor, idx[t]
                    preco = min(limite, o[t]) if pend == 1 else max(limite, o[t])
                    g = pos0 + t
                    atr_e = atr_all[g - 1] if g >= 1 else np.nan
                    nb = 0; stop_x = -np.inf; t_ent_i = t
                pend = 0
            else:
                ttl -= 1
                if ttl <= 0 or est[t] != pend:
                    pend = 0
        # 2b) stop dentro da barra (a mercado, 1 tick contra; gap -> abertura; na barra da entrada, sem gap)
        if pos and stop_x > -np.inf:
            ox = pos * o[t]
            lox = l[t] if pos == 1 else -h[t]
            if t != t_ent_i and ox <= stop_x:
                fecha(o[t], t, "stop")
            elif lox <= stop_x:
                fecha(pos * (stop_x - TICK), t, "stop")
        # 3) sinal novo
        if (not pos and not pend and est[t] != 0 and hora[t] < ULTIMA_ENTRADA and reg[t] in (est[t], 0)
                and (zl[t] if est[t] == 1 else zs[t])):
            pend, limite, ttl = est[t], c[t], TTL_BARRAS
            pend_favor = reg[t] == est[t]
        # 4) zera no fim do pregao (sem leiloes: na ultima barra do CONTINUO, ao close do ultimo negocio continuo)
        if pos and (t == n - 1 or dias[t + 1] != dias[t] or (ult is not None and ult[t])):
            fecha(c[t] - pos * TICK, t, "zera_fim")
        # 5) stop que aperta: decidido no fechamento desta vela, vale a partir da proxima
        if pos and aperta is not None:
            nb += 1
            an, ak = aperta
            if nb >= an and pos * (c[t] - preco) < 0 and not np.isnan(atr_e):
                stop_x = max(stop_x, pos * preco - ak * atr_e)
        curva[t] = caixa
    return pd.DataFrame(trades), pd.Series(curva, index=idx)


# ---- validacao mes a mes, segmentada por contrato -----------------------------
DADOS = Path(__file__).resolve().parents[2] / "data" / "wdo-mt5"
ARQUIVOS = {2026: "WIN@_M1_202601020900_202610051831.csv"}   # 2025 entra SO' na validacao final
FIM_DADOS = {2026: "2026-10-02"}   # corta onde a serie de referencia (+R$7.490,10) cortava


def vencimento_win(ano: int, mes: int) -> pd.Timestamp:
    """Quarta-feira mais proxima do dia 15 (mesma regra do EA)."""
    t15 = pd.Timestamp(ano, mes, 15)
    dif = 2 - t15.dayofweek          # pandas: segunda=0 -> quarta=2
    if dif > 3: dif -= 7
    if dif < -3: dif += 7
    return t15 + pd.Timedelta(days=dif)


def rolagens(ano: int) -> list[pd.Timestamp]:
    """Dias seguintes aos vencimentos (meses pares) que cobrem o ano, mais o fim."""
    v = [vencimento_win(ano - 1, 12)] + [vencimento_win(ano, m) for m in (2, 4, 6, 8, 10, 12)]
    return [x + pd.Timedelta(days=1) for x in v]


# ---- dados: SEM leiloes (carregar) e brutos com leiloes (carregar_bruta, so' para reproduzir o "antes") ----------
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from market_data_intraday.win_sem_leiloes import carrega_win_m1_sem_leiloes, _le_base   # noqa: E402

import os as _os
BASE = _os.environ.get("WINCM_BASE", "WIN$N")   # "WIN$N" (preco real do contrato; 2022-25 = m1_WIN$N_2022_2025.parquet) ou "WIN@" (CSV ajustado, como a original)
PARQUETS = {"WIN$N": ["m1_WIN$N_2022_2025.parquet", "m1_WIN$N.parquet"]}
# mesma janela de dados que a original lia (arquivo por ano + corte), para o "antes x depois" medir so' os leiloes
JANELA = {2026: ("2026-01-02", "2026-10-01"), 2025: ("2024-12-02", "2025-09-30"), 2024: ("2021-12-01", "2024-12-30"),
          2023: ("2021-12-01", "2024-12-30"), 2022: ("2021-12-01", "2024-12-30")}
ARQ_CSV = {2026: "WIN@_M1_202601020900_202610051831.csv", 2025: "WIN@_M1_202412020900_202510311824.csv",
           2024: "WIN@_M1_202112010900_202412301824.csv", 2023: "WIN@_M1_202112010900_202412301824.csv",
           2022: "WIN@_M1_202112010900_202412301824.csv"}


def _minutos(tf) -> int:
    t = str(tf).lower().replace("min", "").replace("m", "")
    return int(t)


def _bases(base):
    return PARQUETS[base] if base in PARQUETS else None


MODO = _os.environ.get("WINCM_MODO", "sl")   # "sl" = sem leiloes (padrao); "bruto" = com leiloes, zera em c[-1] (reproduz o "antes")


def carregar(ano: int = 2026, tf: str = TF, base: str | None = None) -> pd.DataFrame:
    """M1/M5/M30 SEM leiloes (colunas o,h,l,c,v,tv + ultima_continua, proxy, flag_leilao, hl_aprox).
    Com WINCM_MODO=bruto devolve a versao antiga (com leiloes) -> reproduz os numeros anteriores com o mesmo codigo."""
    base = base or BASE
    if MODO == "bruto":
        return carregar_bruta(ano, tf, base)
    ini, fim = JANELA[ano]
    fonte = _bases(base) or [ARQ_CSV[ano]]
    r = carrega_win_m1_sem_leiloes(fonte, ini, fim, tf=_minutos(tf))
    b = r.barras.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "real_volume": "v", "tick_volume": "tv"})
    b.index.name = None
    return b


def carregar_bruta(ano: int = 2026, tf: str = TF, base: str | None = None) -> pd.DataFrame:
    """Como a `carregar` ORIGINAL (com leiloes, sem `ultima_continua`), mas podendo vir de WIN$N. Para o "antes"."""
    base = base or BASE
    ini, fim = JANELA[ano]
    fonte = _bases(base) or [ARQ_CSV[ano]]
    d = pd.concat([_le_base(x) for x in fonte]) if len(fonte) > 1 else _le_base(fonte[0])
    d = d[~d.index.duplicated(keep="last")].sort_index()
    d = d[(d.index >= pd.Timestamp(ini)) & (d.index < pd.Timestamp(fim) + pd.Timedelta(days=1))]
    d = d.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "real_volume": "v", "tick_volume": "tv"})
    d.index.name = None
    if _minutos(tf) == 1:
        return d
    return d.resample(tf).agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum", "tv": "sum"}).dropna()


def carregar_m5() -> pd.DataFrame:
    return carregar(2026, "5min")


def rodar_janelas(ano: int = 2026, tf: str = TF, dados=None, **kw):
    """Roda a estrategia mes a mes, com as medias recomecando em cada contrato e
    operando do 4o pregao dele. kw vai para `simula`. Devolve (tabela, resumo)."""
    d = carregar(ano, tf) if dados is None else dados
    if kw.get("saida_vol", SAIDA_VOL) and "vrel" not in d.columns:
        d = colunas_volume(d)      # no historico inteiro, antes de cortar por contrato (volume nao tem rolagem)
    rol = rolagens(ano)
    linhas, todos = [], []
    for k in range(len(rol) - 1):
        seg = d[rol[k]:rol[k + 1] - pd.Timedelta(minutes=1)]
        dias = sorted(set(seg.index.normalize()))
        if len(dias) < 4:
            continue
        ini_op, ult = dias[3], dias[-1]
        for mes in pd.period_range(ini_op, ult, freq="M"):
            a = max(ini_op, mes.start_time); z = min(mes.end_time, ult + pd.Timedelta(days=1))
            if not len(seg[a:z]):
                continue
            tr, cv = simula(seg, a, z, **kw)
            g = tr.pnl[tr.pnl > 0].sum() if len(tr) else 0.0
            p = -tr.pnl[tr.pnl < 0].sum() if len(tr) else 0.0
            linhas.append(dict(janela=f"{mes} {a:%d}", liquido=round(cv.iloc[-1] - CAPITAL, 2), trades=len(tr),
                               acerto=round(100 * (tr.pnl > 0).mean(), 1) if len(tr) else 0.0,
                               PF=round(g / p, 2) if p else None,
                               maxDD=round(float((cv.cummax() - cv).max()), 2)))
            if len(tr):
                todos.append(tr)
    df = pd.DataFrame(linhas)
    t = pd.concat(todos) if todos else pd.DataFrame(columns=["pts", "pnl"])
    g, p = t.pnl[t.pnl > 0].sum(), -t.pnl[t.pnl < 0].sum()
    se = t.pts.std(ddof=1) / np.sqrt(len(t)) if len(t) > 1 else np.nan
    sem_set = df[~df.janela.str.startswith(f"{ano}-09")]
    resumo = dict(liquido=round(df.liquido.sum(), 2), janelas_pos=f"{(df.liquido > 0).sum()}/{len(df)}",
                  pior=round(df.liquido.min(), 2), trades=int(df.trades.sum()),
                  acerto=round(100 * (t.pnl > 0).mean(), 1) if len(t) else 0.0,
                  PF=round(g / p, 2) if p else None, pts_op=round(t.pts.mean(), 1) if len(t) else None,
                  ic95=(round(t.pts.mean() - 1.96 * se, 1), round(t.pts.mean() + 1.96 * se, 1)) if len(t) > 1 else None,
                  maior_DD=round(df.maxDD.max(), 2), liquido_sem_set=round(sem_set.liquido.sum(), 2))
    if "motivo" in t.columns and len(t):
        z = t[t.motivo == "zera_fim"]
        resumo.update(n_zera_fim=int(len(z)), pct_zera_fim=round(100 * len(z) / len(t), 1), pnl_zera_fim=round(float(z.pnl.sum()), 2))
    return df, resumo


def main():
    df, r = rodar_janelas(2026)
    print(df.to_string(index=False))
    print(f"\nTOTAL {r['liquido']:.2f} | janelas + {r['janelas_pos']} | pior {r['pior']:.2f} | "
          f"trades {r['trades']} | maior DD {r['maior_DD']:.2f}")
    print(r)



def usar_v202():
    """Volta o padrao de `simula` para a v2.02 (sem Supertrend H1). Os scripts da rodada f foram escritos sobre a v2.02."""
    global SAIDA_ST_H1
    SAIDA_ST_H1 = False
    simula.__defaults__ = tuple(None if x == (ST_H1_N, ST_H1_M) else x for x in simula.__defaults__)


if __name__ == "__main__":
    main()
