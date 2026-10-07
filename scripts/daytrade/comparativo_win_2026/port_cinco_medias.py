"""Port tick a tick do EA mt5/WinCincoMedias.mq5 (v2.03) para o replay Python do comparativo WIN 2026.

Sinais: M30 (montado do M1 do WIN$N, alinhado em :00/:30 do servidor), 5 EMAs 2/4/6/17/33 sobre o WIN$N
continuo (o EA so' reinicia no InicioContrato: volume relativo/quantil, Supertrend H1, regime do mes -- aqui igual).
Execucao: tick a tick com as regras do Testador (dados.py). O replay e' por eventos: em cada segmento de barra M30
procura-se com numpy (argmax) o proximo tick que toca limite / stop / horario de zerar -- nada de loop por tick.

Ordem dentro de um tick (como no Testador): 1) stop/limite pendente sao avaliados contra o tick; 2) OnTick do EA
(zerar; e, no 1o tick da vela nova, a logica de vela fechada). Decisoes de modelagem:
  - ordem-limite colocada no tick k: se ja' esta' "no mercado" (preco <= limite na compra) enche no proprio tick k
    ao preco do limite efetivo (min(limite, ask)); senao enche no 1o tick posterior que toca, ao preco do limite;
  - stop (SL) colocado no tick k vale a partir do tick k+1; dispara quando last toca e executa no last do tick;
  - fechamento "a mercado" executa no last do tick em que o EA mandou;
  - ordem pendente morre no fim do dia (ORDER_TIME_DAY); posicao que sobrar no fim dos ticks fecha no 1o tick
    do dia seguinte (de_outro_dia).
Uso:  python port_cinco_medias.py validar   |   python port_cinco_medias.py final
"""
from __future__ import annotations

import bisect
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados  # noqa: E402

NOME = "WinCincoMedias"
TICK = dados.TICK
# ---- inputs do EA (defaults v2.03) ----------------------------------------------------------------------------
EMAS = (2, 4, 6, 17, 33)
EMA_SAIDA = 4
DIAS_MES_ANT = 5
VALIDADE = 5
ULTIMA_ENT = 18 * 60 + 20
ZERAR = 18 * 60 + 24
LOTE = 1.0
SAIDA_VOL, VOL_Q, VOL_PREG = True, 0.90, 20
APERTA_N, APERTA_K = 2, 1.0
SAIDA_ST, ST_N, ST_M = True, 10, 3.0


def arred(x: float) -> float:
    return float(np.floor(x / TICK + 0.5) * TICK)


# ---- calendario de contrato ---------------------------------------------------------------------------------
def vencimento(ano: int, mes: int) -> date:
    t15 = date(ano, mes, 15)
    mql = (t15.weekday() + 1) % 7            # domingo = 0
    dif = 3 - mql
    if dif > 3: dif -= 7
    if dif < -3: dif += 7
    return t15 + timedelta(days=dif)


_ini_cache: dict = {}


def ini_contrato(d: date) -> date:
    if d in _ini_cache:
        return _ini_cache[d]
    ano, mes, r = d.year, d.month, None
    for _ in range(4):
        if mes % 2 == 0:
            v = vencimento(ano, mes)
            if v < d:
                r = v + timedelta(days=1); break
        mes -= 1
        if mes == 0: mes, ano = 12, ano - 1
    _ini_cache[d] = r
    return r


# ---- pre-computo por vela M30 (valores "vistos como vela 1", i.e. a vela que acabou de fechar) -----------------
def _supertrend_h1(h, l, c, n, m):
    atr = 0.0; fu = fl = 0.0; cur = 0; tem = False
    out = np.zeros(len(c), int)
    for i in range(len(c)):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        atr = tr if i == 0 else atr + (tr - atr) / n
        if i >= n - 1:
            hl2 = (h[i] + l[i]) / 2.0
            bu, bl = hl2 + m * atr, hl2 - m * atr
            if not tem:
                fu, fl, cur, tem = bu, bl, (1 if c[i] >= hl2 else -1), True
            else:
                pc = c[i - 1]
                nfu = bu if (bu < fu or pc > fu) else fu
                nfl = bl if (bl > fl or pc < fl) else fl
                fu, fl = nfu, nfl
                if cur == 1 and c[i] < fl: cur = -1
                elif cur == -1 and c[i] > fu: cur = 1
        out[i] = cur
    return out


def prepara(emas=EMAS, ema_saida=EMA_SAIDA, st=(ST_N, ST_M), vol_q=VOL_Q, vol_preg=VOL_PREG, dias_ant=DIAS_MES_ANT,
            ema_reinicia=False, vol_continuo=False, M=None):
    M = dados.m1() if M is None else M
    agg = dict(open="first", high="max", low="min", close="last", real_volume="sum", tick_volume="sum")
    b = M.resample("30min").agg(agg).dropna(subset=["open"])
    h1 = M.resample("60min").agg(agg).dropna(subset=["open"])
    N = len(b)
    ts = b.index
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    vol = b["real_volume"].to_numpy(float)       # o EA usa volume REAL se o simbolo tem (WIN tem)
    dia = np.array([t.date() for t in ts])
    tb = ts.values.astype("datetime64[ms]").astype(np.int64)
    slot = (ts.hour * 60 + ts.minute).to_numpy()
    ini = np.array([ini_contrato(d) for d in dia])
    P = dict(N=N, ts=ts, o=o, h=h, l=l, c=c, tb=tb, dia=dia, slot=slot, ini=ini)

    # EMAs / alinhamento (Alinhamento(1): vela j contra a anterior)
    if ema_reinicia:      # diagnostico: EMAs recomecam no inicio do contrato (como o win_cinco_medias.py)
        gid = pd.factorize(pd.Series([str(x) for x in ini]))[0]
        ewm = lambda p: pd.Series(c).groupby(gid).transform(lambda s_: s_.ewm(span=p, adjust=False).mean()).to_numpy()
    else:
        ewm = lambda p: pd.Series(c).ewm(span=p, adjust=False).mean().to_numpy()
    E = [ewm(p) for p in emas]
    up = np.ones(N, bool); dn = np.ones(N, bool)
    for a, bb in zip(E, E[1:]):
        up &= a > bb; dn &= a < bb
    for e in E:
        d = np.r_[np.nan, np.diff(e)]
        up &= d > 0; dn &= d < 0
    P["est"] = np.where(up, 1, np.where(dn, -1, 0))
    P["ema_s"] = ewm(ema_saida)

    # ATR(14) Wilder, TR da 1a vela = h-l
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    atr = np.empty(N); a = 0.0
    for i in range(N):
        a = tr[i] if i == 0 else a + (tr[i] - a) / 14.0
        atr[i] = a
    P["atr"] = atr

    # --- volume relativo + limite do quantil (so' pregoes do contrato atual) ---
    ts_d = ts.normalize()
    ini_dt = np.array([pd.Timestamp(x) for x in ini])
    vrel = np.full(N, -1.0)
    bySlot: dict = {}
    for j in range(N):
        lst = bySlot.setdefault(slot[j], [])
        # amostra: ate' vol_preg velas do mesmo horario, anteriores, do contrato, dentro de 800 velas
        am = []
        for jj in reversed(lst):
            if len(am) >= vol_preg or j - jj > 800 or (ts[jj] < ini_dt[j] and not vol_continuo):
                break
            am.append(vol[jj])
        lst.append(j)
        if len(am) >= 5:
            med = float(np.median(am))
            if med > 0:
                vrel[j] = vol[j] / med
    lim = np.full(N, -1.0)
    hist: list = []; ini_h = None
    for j in range(N):
        if ini[j] != ini_h:
            hist = []; ini_h = ini[j]
        if len(hist) >= 100:
            n = len(hist); pos = vol_q * (n - 1); lo = int(np.floor(pos)); hi = min(lo + 1, n - 1)
            lim[j] = hist[lo] + (pos - lo) * (hist[hi] - hist[lo])
        if vrel[j] >= 0:
            bisect.insort(hist, vrel[j])
    grande = (lim >= 0) & (vrel >= 0) & (vrel >= lim)
    P["clim_l"] = grande & (c < o)      # compra sai em vela de baixa
    P["clim_s"] = grande & (c > o)

    # --- Supertrend H1 (desde o inicio do contrato, so' H1 fechadas na vela M30 j) ---
    h1i = h1.index.values
    H, L, C = (h1[k].to_numpy(float) for k in ("high", "low", "close"))
    cache: dict = {}
    std = np.zeros(N, int)
    for j in range(N):
        i0 = pd.Timestamp(ini[j])
        if i0 not in cache:
            first = int(np.searchsorted(h1i, np.datetime64(i0), "left"))
            cache[i0] = (first, _supertrend_h1(H[first:], L[first:], C[first:], st[0], st[1]))
        first, dirs = cache[i0]
        ate = np.datetime64(ts[j] - pd.Timedelta(minutes=30))
        kk = int(np.searchsorted(h1i, ate, "right")) - 1
        if kk < first or ts[j] - pd.Timedelta(minutes=30) < i0:
            continue
        if kk - first + 1 < st[0]:
            continue
        std[j] = dirs[kk - first]
    P["st"] = std

    # --- regime do mes visto na vela j ---
    Dl = sorted(set(dia)); Dpos = {d: i for i, d in enumerate(Dl)}
    tsn = ts.values
    reg = np.zeros(N, int)
    for j in range(N):
        t = ts[j]; d = dia[j]
        ini_mes = date(d.year, d.month, 1); ict = ini[j]
        if ict is None:
            continue
        anc = max(ini_mes, ict)
        n_preg = Dpos[d] - bisect.bisect_left(Dl, anc) + 1
        if dias_ant > 0 and n_preg <= dias_ant:
            if ict >= ini_mes:
                reg[j] = 0; continue
            am, aa = d.month - 1, d.year
            if am == 0: am, aa = 12, aa - 1
            anc_ant = max(date(aa, am, 1), ict)
            k0 = int(np.searchsorted(tsn, np.datetime64(pd.Timestamp(anc_ant)), "left"))
            kf = int(np.searchsorted(tsn, np.datetime64(pd.Timestamp(ini_mes)), "left")) - 1
            if k0 >= N or tsn[k0] >= np.datetime64(pd.Timestamp(ini_mes)) or kf < 0:
                reg[j] = 0; continue
            reg[j] = int(np.sign(c[kf] - o[k0]))
        else:
            k0 = int(np.searchsorted(tsn, np.datetime64(pd.Timestamp(anc)), "left"))
            if k0 > j:
                reg[j] = 0; continue
            reg[j] = int(np.sign(c[j] - o[k0]))
    P["reg"] = reg
    return P


# ---- replay -----------------------------------------------------------------------------------------------------
def m1_winv26() -> pd.DataFrame:
    """M1 do contrato WINV26 (o que o Testador carrega): so' para validar. Identico ao WIN$N desde 13/08."""
    f = dados.ROOT / "data" / "wdo-mt5" / "WINV26_M1_202604151210_202610011824.csv"
    d = pd.read_csv(f, sep="	"); d.columns = [x.strip("<>") for x in d.columns]
    d.index = pd.to_datetime(d["DATE"] + " " + d["TIME"], format="%Y.%m.%d %H:%M:%S")
    return d.rename(columns={"OPEN": "open", "HIGH": "high", "LOW": "low", "CLOSE": "close", "VOL": "real_volume",
                             "TICKVOL": "tick_volume"})[["open", "high", "low", "close", "tick_volume", "real_volume"]]


def simular(P, d_ini: date, d_fim: date, aperta=(APERTA_N, APERTA_K), saida_vol=SAIDA_VOL, saida_st=SAIDA_ST,
            verbose=True, opera_desde=None):
    N, tb, dia = P["N"], P["tb"], P["dia"]
    est, reg, o, c, ema_s, atr = P["est"], P["reg"], P["o"], P["c"], P["ema_s"], P["atr"]
    clim_l, clim_s, st = P["clim_l"], P["clim_s"], P["st"]
    slot = P["slot"]
    trades: list = []
    S = dict(pos=0, pe=0.0, t_ent=0, j_ent=0, fav=False, sl=0.0, pend=0, plim=0.0, pj=-1, pfav=False, pdia=None)
    dias_j: dict = {}
    for j in range(N):
        dias_j.setdefault(dia[j], []).append(j)

    for dd in dados.dias():
        if dd < d_ini or dd > d_fim:
            continue
        t, p, _v, _r = dados.ticks(dd)
        n = len(t)
        mod = (t // 60000) % 1440
        zi = int(np.argmax(mod >= ZERAR)) if (mod >= ZERAR).any() else n
        js = dias_j.get(dd, [])

        def fecha(idx, motivo):
            pos = S["pos"]
            trades.append(dados.trade(NOME, S["t_ent"], t[idx], pos, LOTE, S["pe"], p[idx], motivo))
            S["pos"] = 0; S["sl"] = 0.0

        def abre(idx, preco, j):
            S.update(pos=S["pend"], pe=preco, t_ent=int(t[idx]), j_ent=j, fav=S["pfav"], sl=0.0, pend=0)

        if S["pos"]:                               # de_outro_dia: fecha no 1o tick
            fecha(0, "de outro dia")
        S["pend"] = 0
        if not js or n == 0:
            continue
        starts = np.searchsorted(t, tb[js], "left")
        ends = np.r_[starts[1:], n]

        def toca(i, e, lado, nivel):               # 1o tick em [i,e) em que last toca o nivel (compra: <=, venda: >=)
            if i >= e: return None
            seg = p[i:e]
            m = seg <= nivel if lado > 0 else seg >= nivel
            k = int(np.argmax(m))
            return i + k if m[k] else None

        def tick_events(idx, j, newbar):
            if S["pos"] and S["sl"] > 0 and S["pos"] * (p[idx] - S["sl"]) <= 0:
                fecha(idx, "stop")
            if S["pend"] and not S["pos"]:
                if (p[idx] <= S["plim"]) if S["pend"] > 0 else (p[idx] >= S["plim"]):
                    abre(idx, S["plim"], j)
            if S["pos"] and mod[idx] >= ZERAR:
                fecha(idx, "fim do pregao")
            if newbar:
                nova_vela(idx, j)

        def nova_vela(idx, j):
            ja = j - 1
            if ja < 0: return
            mesmo = dia[ja] == dia[j]
            est1 = int(est[ja])
            agora = int(mod[idx])
            m1_ = int(slot[ja])
            if S["pos"]:
                lado = S["pos"]
                sai, mot = False, ""
                if m1_ >= ULTIMA_ENT: sai, mot = True, "horario"
                elif S["fav"]:
                    if lado * (c[ja] - ema_s[ja]) <= 0.0: sai, mot = True, "fechou do outro lado da EMA saida"
                elif est1 != lado: sai, mot = True, "alinhamento quebrou"
                if not sai and saida_vol and (clim_l[ja] if lado > 0 else clim_s[ja]): sai, mot = True, "climax de volume contra"
                if not sai and saida_st and st[ja] == -lado: sai, mot = True, "Supertrend H1 contra"
                if sai:
                    fecha(idx, mot)
                elif aperta:
                    ajusta(idx, j, lado)
                return
            if S["pend"]:
                velas = j - S["pj"]
                if (not mesmo) or S["pdia"] != dia[j] or velas >= VALIDADE or est1 != S["pend"]:
                    S["pend"] = 0
                else:
                    return
            if (not mesmo) or est1 == 0: return
            if opera_desde and dia[j] < opera_desde: return
            if m1_ >= ULTIMA_ENT or agora >= ZERAR: return
            r = int(reg[ja])
            if r != 0 and r != est1: return
            limite = arred(c[ja])
            px = arred(p[idx])
            preco = min(limite, px) if est1 > 0 else max(limite, px)
            S.update(pend=est1, plim=preco, pj=j, pfav=(r == est1), pdia=dia[j])
            if (p[idx] <= preco) if est1 > 0 else (p[idx] >= preco):    # ja' no mercado: enche na hora
                abre(idx, preco, j)

        def ajusta(idx, j, lado):
            an, ak = aperta
            sh_e = j - S["j_ent"]
            if an <= 0 or sh_e < 1: return
            armou = any(lado * (c[j - sh] - S["pe"]) < 0 for sh in range(sh_e - an + 1, 0, -1))
            if not armou: return
            a = atr[S["j_ent"] - 1]
            if not (a > 0): return
            nivel = arred(S["pe"] - lado * ak * a)
            if nivel <= 0: return
            if S["sl"] > 0 and lado * (S["sl"] - nivel) >= 0: return
            pr = p[idx]
            if (pr <= nivel + TICK) if lado > 0 else (pr >= nivel - TICK):
                fecha(idx, "stop aperta (preco alem)")
                return
            S["sl"] = nivel

        for q, j in enumerate(js):
            s, e = int(starts[q]), int(ends[q])
            if s >= e: continue
            tick_events(s, j, True)
            i = s + 1
            while i < e:
                cand = []
                if S["pend"] and not S["pos"]:
                    k = toca(i, e, S["pend"], S["plim"])
                    if k is not None: cand.append(k)
                if S["pos"]:
                    if S["sl"] > 0:
                        k = toca(i, e, S["pos"], S["sl"])      # long: p <= sl ; short: p >= sl
                        if k is not None: cand.append(k)
                    kz = max(i, zi)
                    if kz < e: cand.append(kz)
                if not cand: break
                k = min(cand)
                tick_events(k, j, False)
                i = k + 1
        if verbose:
            print(f"{dd} trades={len(trades)} pos={S['pos']}", flush=True) if dd.day in (1, 15) else None
    if S["pos"]:                                    # fim do periodo
        pass
    return trades


def resumo(trades):
    df = pd.DataFrame(trades)
    if df.empty:
        return df, pd.Series(dtype=float)
    df["mes"] = df["entrada"].str[:7]
    return df, df.groupby("mes").rs.agg(["count", "sum"])


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "final"
    print("preparando...", flush=True)
    P = prepara()
    if modo == "validar":
        # Testador real (v2.01, WINV26, 13/08-30/09): 47 trades, +R$737. Esperado v2.03: 57 trades, ~+R$1.285.
        for fonte, PP in (("WIN$N", P), ("WINV26", prepara(M=m1_winv26()))):
            for nome, kw in (("v2.01", dict(aperta=None, saida_st=False)), ("v2.02", dict(saida_st=False)), ("v2.03", dict())):
                tr = simular(PP, date(2026, 8, 13), date(2026, 9, 30), verbose=False, **kw)
                print(f"{fonte} {nome}: {len(tr)} trades, liquido R$ {pd.DataFrame(tr).rs.sum():.2f}", flush=True)
    else:
        tr = simular(P, dados.INICIO, dados.FIM)
        out = dados.salvar(NOME, tr)
        df, m = resumo(tr)
        print(m.to_string(), flush=True)
        print(f"TOTAL {len(tr)} trades, R$ {df.rs.sum():.2f} -> {out}", flush=True)


if __name__ == "__main__":
    main()
