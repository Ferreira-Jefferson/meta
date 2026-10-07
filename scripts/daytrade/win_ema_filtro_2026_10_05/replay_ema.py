"""Replay do Win.mq5 sobre TICKS REAIS (bid/ask/last) do WINV26.

Replica a logica do EA (filtros de entrada, stop na roxa +/- K x ATR, saida por canal, saida por esticada, sinal velho
do dia anterior ignorado, zerar no fim do pregao) e executa tick a tick: compra entra no ask / venda no bid, stop
dispara pelo preco `last` (chart_mode do WIN) e sai no bid/ask do tick do disparo, com latencia (fixa ou aleatoria)
em toda ordem. Os sinais saem das barras M5 construidas das barras M1 do MT5, como no EA.

Nao cobre: corretagem/emolumentos, fila de execucao, slippage alem do bid/ask do tick. O sinal e' o mesmo da
simulacao M1, entao so' a EXECUCAO e' independente.

Uso:  python win_replay_ticks.py --inicio 2026-09-01 --fim 2026-09-30 --latencia 0
Ticks baixados do MT5 ficam em data/cache_win_ticks/<ativo>/<dia>.pkl (dias fechados).
"""
import argparse, json, sys, threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from core.indicators import lwma, smma

CACHE = ROOT / "data" / "cache_win_ticks"
TICK = 5.0       # tamanho do tick do WIN, em pontos
RS_PONTO = 0.20  # R$ por ponto, 1 contrato
LOCK_MT5 = threading.Lock()

# Mesmos nomes/valores dos inputs do Win.mq5 v2.00 (0 desliga os filtros que o EA permite desligar)
PARAMS_PADRAO = dict(
    periodo=34, periodo_atr=14, k_atr=0.6,
    idade_max=9, dist_min=15.0, gap_max_atr=3.0,
    ext_roxa_min_atr=1.4, dist_verde_min_atr=1.2,
    esticada_arma_atr=2.5, esticada_recuo_atr=0.75,
    janela_toques=20, toques_max=14,
    hora_fim=18, minuto_fim=0, min_sem_entrada=30, min_zerar=10,
    horas_sem_entrada="11,15,16,17",   # horas cheias do servidor sem entrada nova; "" desliga
    # filtros candidatos (NAO fazem parte do Win.mq5 v2.01; padrao desligado = identico ao EA)
    alinhar_m15=True,    # so entra se a ultima M15 FECHADA na entrada tem close do lado do sinal da roxa M15 e verde M15 do lado oposto
    # break-even a mercado (Win.mq5 v2.05): 0 = desligado (identico a v2.04); 15 = a regra testada
    be_minutos=0,        # a partir de N min apos a abertura da M5 de entrada, no 1o tick de cada M1: se o flutuante (bid na compra / ask na venda) <= colchao pts a favor, fecha a mercado
    ema_periodo=0,       # filtro EMA (copia de pesquisa, nao existe no EA): 0 = desligado
    ema_modo="close",    # close: close da M5 do sinal vs EMA; vela: vela inteira do lado (low>EMA / high<EMA)
    be_colchao_pts=7.0,  # colchao do break-even, em pontos a favor (7 = custo 5 + slippage 2)
)


def _utc(d: date, h=0, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)  # o tempo das barras/ticks do MT5 e' o do servidor, lido como UTC


def _mt5():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError("MT5 nao inicializou: abra o terminal do MetaTrader 5")
    return mt5


def carregar_m1(ativo: str, inicio: date, fim: date) -> pd.DataFrame:
    """Barras M1 de [inicio-7d, fim] (a folga inicial alimenta MM/ATR no comeco do periodo)."""
    with LOCK_MT5:
        mt5 = _mt5()
        if mt5.symbol_info(ativo) is None:
            raise RuntimeError(f"o simbolo {ativo} nao existe neste terminal do MT5")
        mt5.symbol_select(ativo, True)
        linhas, d0 = [], inicio - timedelta(days=7)
        while d0 <= fim:
            d1 = min(d0 + timedelta(days=5), fim + timedelta(days=1))
            r = mt5.copy_rates_range(ativo, mt5.TIMEFRAME_M1, _utc(d0), _utc(d1))
            if r is not None and len(r):
                linhas.append(pd.DataFrame(r))
            d0 += timedelta(days=5)
    if not linhas:
        raise RuntimeError(f"o MT5 nao tem barras M1 de {ativo} entre {inicio} e {fim} (verifique o simbolo e o periodo)")
    m1 = pd.concat(linhas).drop_duplicates("time")
    m1.index = pd.to_datetime(m1["time"], unit="s")
    return m1.sort_index()[["open", "high", "low", "close"]].astype(float)


def preparar_barras(m1: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Barras M5 com roxa/verde/ATR e o sinal ja' filtrado (+1 compra, -1 venda, 0 nada) em cada vela FECHADA."""
    m5 = m1.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    m5["wma"], m5["smma"] = lwma(m5.close, p["periodo"]), smma(m5.close, p["periodo"])
    tr = pd.concat([m5.high - m5.low, (m5.high - m5.close.shift()).abs(), (m5.low - m5.close.shift()).abs()], axis=1).max(axis=1)
    m5["atr"] = tr.rolling(p["periodo_atr"]).mean()
    comp = (m5.low > m5.wma) & (m5.smma < m5.wma)
    vend = (m5.high < m5.wma) & (m5.smma > m5.wma)
    sinal = pd.Series(np.where(comp, 1, np.where(vend, -1, 0)), index=m5.index)
    sinal[m5.wma.isna() | m5.smma.isna() | m5.atr.isna()] = 0
    ok = pd.Series(True, index=m5.index)
    if p["idade_max"] > 0:
        lado = np.sign(m5.close - m5.wma).fillna(0)
        idade = lado.groupby((lado != lado.shift()).cumsum()).cumcount() + 1
        ok &= idade <= p["idade_max"]
    ok &= np.where(sinal == 1, m5.low - m5.wma, m5.wma - m5.high) >= p["dist_min"]
    if p["gap_max_atr"] > 0:
        ok &= (m5.wma - m5.smma).abs() / m5.atr < p["gap_max_atr"]
    if p["ext_roxa_min_atr"] > 0:
        ok &= np.where(sinal == 1, m5.high - m5.wma, m5.wma - m5.low) / m5.atr >= p["ext_roxa_min_atr"]
    if p["dist_verde_min_atr"] > 0:
        ok &= sinal * (m5.close - m5.smma) / m5.atr >= p["dist_verde_min_atr"]
    if p["janela_toques"] > 0:
        j = int(p["janela_toques"])
        toq_c = (m5.low <= m5.wma).astype(float).rolling(j).sum()
        toq_v = (m5.high >= m5.wma).astype(float).rolling(j).sum()
        ok &= np.where(sinal == 1, toq_c, toq_v) <= p["toques_max"]
    if p.get("alinhar_m15"):   # M15 so' vale a partir do FECHAMENTO da barra: o instante da entrada e' a abertura da M5 seguinte
        m15 = m1.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        m15["w"], m15["s"] = lwma(m15.close, p["periodo"]), smma(m15.close, p["periodo"])
        m15.index = m15.index + pd.Timedelta(minutes=15)
        k = m15.reindex(m5.index + pd.Timedelta(minutes=5), method="ffill")
        d = sinal.to_numpy()
        ok &= pd.Series((np.sign(k.close.to_numpy() - k.w.to_numpy()) == d) &
                        np.where(d == 1, k.s.to_numpy() < k.w.to_numpy(), k.s.to_numpy() > k.w.to_numpy()), index=m5.index)
    if p.get("ema_periodo"):
        e = m5.close.ewm(span=int(p["ema_periodo"]), adjust=False, min_periods=int(p["ema_periodo"])).mean()
        if p.get("ema_modo", "close") == "close":
            f = np.where(sinal == 1, m5.close > e, np.where(sinal == -1, m5.close < e, False))
        else:
            f = np.where(sinal == 1, m5.low > e, np.where(sinal == -1, m5.high < e, False))
        ok &= pd.Series(f, index=m5.index)
    m5["sinal"] = sinal.where(ok.fillna(False), 0).astype(int)
    horas = [int(h) for h in str(p.get("horas_sem_entrada", "")).replace(";", ",").split(",") if h.strip()]
    if horas:   # a hora que vale e' a da vela em que a ordem entra (a seguinte a do sinal), como no EA
        m5.loc[np.isin((m5.index + pd.Timedelta(minutes=5)).hour, horas), "sinal"] = 0
    return m5


def carregar_ticks(ativo: str, dia: date):
    """(tempo_ms, bid, ask, last) do dia; baixa do MT5 se nao estiver no cache. Dia sem pregao -> arrays vazios."""
    arq = CACHE / ativo / f"{dia}.pkl"
    if arq.exists():
        x = pd.read_pickle(arq)
    else:
        with LOCK_MT5:
            mt5 = _mt5()
            r = mt5.copy_ticks_range(ativo, _utc(dia, 8, 30), _utc(dia, 18, 30), mt5.COPY_TICKS_ALL)  # dia inteiro: janela estreita perde ticks
            if r is None:   # None = erro do MT5 (diferente de "sem ticks"): nao vira dia vazio no cache
                raise RuntimeError(f"MT5 falhou ao baixar os ticks de {dia}: {mt5.last_error()}")
        x = pd.DataFrame(r)[["time_msc", "bid", "ask", "last", "volume", "flags"]] if r is not None and len(r) else pd.DataFrame(
            columns=["time_msc", "bid", "ask", "last", "volume", "flags"])
        if dia < date.today() and len(x):   # dia vazio nao vai pro cache: pode ser falha passageira, nao ausencia real
            arq.parent.mkdir(parents=True, exist_ok=True)
            x.to_pickle(arq)
    return x.time_msc.to_numpy(), x.bid.to_numpy(), x.ask.to_numpy(), x["last"].to_numpy()


def _arred(v):
    return np.round(v / TICK) * TICK


def replay_dia(dia, bars, tick, p, lat, trades):
    tms, bid, ask, last = tick
    n = len(tms)
    if n == 0:
        return
    fi = lambda t: min(int(np.searchsorted(tms, t)), n - 1)
    ini = pd.Timestamp(dia).value // 10**6
    t_zera = ini + (p["hora_fim"] * 60 + p["minuto_fim"] - p["min_zerar"]) * 60000
    t_sem = ini + (p["hora_fim"] * 60 + p["minuto_fim"] - p["min_sem_entrada"]) * 60000
    idx = bars.index
    W, S, C, A, G = (bars[c].to_numpy() for c in ("wma", "smma", "close", "atr", "sinal"))
    pos = None

    def scan(q, i_from, i_to):
        if i_to <= i_from:
            return None
        seg = last[i_from:i_to]
        c = (seg <= q["sl"]) if q["d"] == 1 else (seg >= q["sl"])
        return i_from + int(np.argmax(c)) if c.any() else None

    def fechar(q, i, mot):
        px = bid[i] if q["d"] == 1 else ask[i]
        trades.append(dict(dia=str(dia), te=q["te"], tx=pd.Timestamp(int(tms[i]), unit="ms"), d=q["d"], pe=float(q["e"]), px=float(px),
                           mot=mot, rs=float(q["d"] * (px - q["e"]) * RS_PONTO)))

    be_on = int(p["be_minutos"]) > 0
    prev_tb = None

    def be_win(t0, t1):
        """Break-even a mercado nas aberturas de M1 em [t0, t1): no 1o tick de cada minuto (como o EA no 1o tick da barra M1),
        a partir do prazo, se o flutuante (bid na compra / ask na venda) <= colchao pts a favor, fecha a mercado com latencia.
        O stop nativo continua valendo ate' a ordem chegar (scan)."""
        nonlocal pos
        for tm in range(int(t0), int(t1), 60000):
            if pos is None:
                return
            if tm < pos["dl"]:
                continue
            i_m = fi(tm)
            if tms[i_m] < tm or tms[i_m] >= tm + 60000:
                continue
            j = scan(pos, pos["chk"], i_m)
            if j is not None:
                fechar(pos, fi(tms[j] + lat()), "stop"); pos = None
                return
            pos["chk"] = max(pos["chk"], i_m)
            d = pos["d"]
            if d * ((bid[i_m] if d == 1 else ask[i_m]) - pos["e"]) <= p["be_colchao_pts"]:
                ib = fi(tms[i_m] + lat())
                j = scan(pos, i_m, ib)
                fechar(pos, fi(tms[j] + lat()) if j is not None else ib, "stop" if j is not None else "break_even"); pos = None
                return

    for k in range(len(idx)):
        tb = (idx[k] + pd.Timedelta(minutes=5)).value // 10**6   # a vela k fechou: o EA age no 1o tick da seguinte
        if pos is not None and be_on and prev_tb is not None:
            be_win(prev_tb, min(tb, t_zera))
        prev_tb = tb
        if tb >= t_zera:
            break
        i0 = fi(tb)
        if tms[i0] < tb:
            continue
        ia = fi(tms[i0] + lat())
        if pos is not None:
            j = scan(pos, pos["chk"], ia)          # o stop antigo vale ate' a ordem chegar
            if j is not None:
                fechar(pos, fi(tms[j] + lat()), "stop"); pos = None
                continue
            d = pos["d"]; est = d * (C[k] - W[k]) / A[k]; ex = None
            if min(W[k], S[k]) < C[k] < max(W[k], S[k]):
                ex = "canal"
            elif p["esticada_arma_atr"] > 0:
                if est >= p["esticada_arma_atr"]:
                    pos["arm"] = True
                pos["pico"] = max(pos["pico"], est)
                if pos["arm"] and est <= pos["pico"] - p["esticada_recuo_atr"]:
                    ex = "esticada"
            novo = _arred(W[k] + d * p["k_atr"] * A[k])
            if ex is None:
                pr = bid[i0] if d == 1 else ask[i0]
                if (d == 1 and novo > pr - TICK) or (d == -1 and novo < pr + TICK):
                    ex = "stop_alcancado"
            if ex:
                fechar(pos, ia, ex); pos = None
            else:
                pos["sl"] = novo; pos["cur"] = pos["chk"] = ia
            continue
        s = int(G[k])
        if s == 0 or tms[i0] >= t_sem:
            continue
        pdec = ask[i0] if s == 1 else bid[i0]
        sl = _arred(W[k] + s * p["k_atr"] * A[k])
        if (s == 1 and sl > pdec - TICK) or (s == -1 and sl < pdec + TICK):
            continue                                # stop do lado errado do preco: o EA ignora a entrada
        e = ask[ia] if s == 1 else bid[ia]
        pos = dict(d=s, e=float(e), sl=float(sl), cur=ia, chk=ia, te=pd.Timestamp(int(tms[ia]), unit="ms"), arm=False, pico=-1e9,
                   dl=int(tms[ia]) // 300000 * 300000 + int(p["be_minutos"]) * 60000)   # prazo do BE: abertura da M5 de entrada + N min
    if pos is not None and be_on and prev_tb is not None:
        be_win(prev_tb, t_zera)
    if pos is not None:
        ia = fi(tms[fi(t_zera)] + lat())
        j = scan(pos, pos["chk"], ia)
        fechar(pos, fi(tms[j] + lat()) if j is not None else ia, "stop" if j is not None else "zera")


def metricas(t: pd.DataFrame, dias: int) -> dict:
    if t.empty:
        return dict(n=0, liquido=0.0, dd=0.0, win=0.0, pf=0.0, dias_neg=0, dias=dias, por_op=0.0)
    t = t.sort_values("tx")
    eq = t.rs.cumsum(); dd = float((eq.cummax().clip(lower=0) - eq).max())
    g = t.rs[t.rs > 0].sum(); l = -t.rs[t.rs < 0].sum(); d = t.groupby("dia").rs.sum()
    return dict(n=int(len(t)), liquido=round(float(t.rs.sum()), 2), dd=round(dd, 2), win=round(100 * float((t.rs > 0).mean()), 1),
                pf=round(float(g / l), 2) if l else None, dias_neg=int((d < 0).sum()), dias=dias, por_op=round(float(t.rs.mean()), 2))


def replay(inicio: date, fim: date, latencia_s=0.0, modo="fixa", params=None, ativo="WINV26", progresso=None) -> dict:
    p = {**PARAMS_PADRAO, **(params or {})}
    rng = np.random.default_rng(1)
    L = int(round(float(latencia_s) * 1000))
    lat = (lambda: int(rng.uniform(0, L))) if modo == "aleatoria" else (lambda: L)
    if progresso: progresso(0, 1, "lendo barras M1 do MT5")
    bars = preparar_barras(carregar_m1(ativo, inicio, fim), p)
    dias = sorted(d for d in set(bars.index.date) if inicio <= d <= fim)
    trades, sem_ticks, avisos = [], [], []
    for k, dia in enumerate(dias):
        if progresso: progresso(k, len(dias), f"{dia}: {'lendo ticks' if (CACHE / ativo / f'{dia}.pkl').exists() else 'baixando ticks do MT5'}")
        try:
            tick = carregar_ticks(ativo, dia)
            if len(tick[0]) == 0:
                sem_ticks.append(str(dia)); continue
            replay_dia(dia, bars[bars.index.date == dia], tick, p, lat, trades)
        except Exception as e:   # um dia ruim nao derruba o periodo: segue e avisa
            sem_ticks.append(str(dia)); avisos.append(f"{dia}: {type(e).__name__}: {e}")
    if dias and len(sem_ticks) == len(dias):
        raise RuntimeError(f"o MT5 nao tem ticks de {ativo} em nenhum dos {len(dias)} pregoes entre {inicio} e {fim} "
                           f"(o historico de ticks da corretora e' limitado; tente um periodo mais recente)" + (f". Primeiro erro: {avisos[0]}" if avisos else ""))
    if not dias:
        raise RuntimeError(f"nenhum pregao com barras de {ativo} entre {inicio} e {fim}")
    if sem_ticks:
        avisos.insert(0, f"{len(sem_ticks)} de {len(dias)} pregoes ficaram de fora por falta de ticks; o resultado cobre os {len(dias) - len(sem_ticks)} restantes")
    t = pd.DataFrame(trades)
    ndias = len(dias) - len(sem_ticks)
    por_mes = []
    if not t.empty:
        for mes, g in t.groupby(t.dia.str[:7]):
            por_mes.append({"mes": mes, **metricas(g, int(len({d for d in dias if str(d)[:7] == mes}))) })
    if progresso: progresso(len(dias), len(dias), "pronto")
    out = t.assign(te=t.te.dt.strftime("%Y-%m-%d %H:%M:%S"), tx=t.tx.dt.strftime("%Y-%m-%d %H:%M:%S")).round(2).to_dict("records") if not t.empty else []
    return dict(ativo=ativo, inicio=str(inicio), fim=str(fim), latencia_s=latencia_s, modo=modo, params=p,
                resumo=metricas(t, ndias), por_mes=por_mes, trades=out, dias_sem_ticks=sem_ticks, avisos=avisos)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--inicio", required=True); ap.add_argument("--fim", required=True)
    ap.add_argument("--latencia", type=float, default=0.0, help="segundos")
    ap.add_argument("--modo", choices=["fixa", "aleatoria"], default="fixa")
    ap.add_argument("--ativo", default="WINV26")
    ap.add_argument("--params", default="{}", help='JSON com qualquer chave de PARAMS_PADRAO, ex: \'{"k_atr":0.5}\'')
    a = ap.parse_args()
    r = replay(date.fromisoformat(a.inicio), date.fromisoformat(a.fim), a.latencia, a.modo, json.loads(a.params), a.ativo,
               lambda k, n, m: print(f"[{k}/{n}] {m}", flush=True))
    print(json.dumps({k: r[k] for k in ("resumo", "por_mes", "dias_sem_ticks")}, ensure_ascii=False, indent=1))
