"""HTML de prints do Win.mq5 em WINV26, SO' setembro/2026 (mes de refino).
Cada execucao e' um TESTE novo (Teste 1, 2, ...) guardado em testes.json; o HTML mostra o mais recente primeiro e
preserva todos. Dentro de um teste: um dia por vez (botoes), grafico M5 com roxa/verde e entradas/saidas simuladas.
Uso: python win_mq5_winv26_setembro_html.py [--stop 300 --alvo 600 --trail-on 100 --trail-dist 60 --nota "texto"]
Saida: .claude/artifacts/win_setembro/index.html (+ testes.json, plotly.min.js)"""
import argparse, json, sys
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd
import MetaTrader5 as mt5
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))
from core.indicators import lwma, smma
from win_ema8_wma8_sim_m1 import simular
MES, CUSTO, SLIP, R = "2026-09", 5.0, 2.0, 0.20
SEM_ENTRADA, ZERAR = 17 * 60 + 30, 17 * 60 + 50
OUT = ROOT / ".claude" / "artifacts" / "win_setembro"

def simular_canal(m1, stop_em="verde", folga_stop=0.0, max_tent=0, cond="sempre", custo=CUSTO, slip=SLIP, folga_atr=None, esticada=None, be=None):
    """Regra 'canal': stop = verde (SMMA34) ou roxa (WMA34) conforme stop_em, acompanhando a media a cada fechamento de M5; se uma M5 fecha ENTRE a roxa e a
    verde, sai na abertura da M5 seguinte. Sem alvo, sem trailing, sem stop fixo. Colunas verde/roxa/fech = M5 que acabou de fechar.
    be = (minutos, colchao_pts) liga o break-even a mercado do Win_c1.mq5 v2.05: na abertura de cada M1 a partir de abertura da M5 de entrada + minutos,
    se o flutuante (abertura da M1 contra a entrada) for <= colchao pts a favor, sai a mercado (so' o custo, sem slippage). Checado depois de
    canal/esticada/stop da barra e antes do stop intra-M1, como o simulador V_core."""
    o, h, l = (m1[k].to_numpy() for k in ("open", "high", "low"))
    sig, ab5 = m1["sinal"].to_numpy(), m1["abre5"].to_numpy()
    vd, rx, fc = m1["verde"].to_numpy(), m1["roxa"].to_numpy(), m1["fech"].to_numpy()
    nivel = rx if stop_em == "roxa" else vd
    fs = m1["fatr"].to_numpy() * folga_atr if folga_atr else np.full(len(m1), float(folga_stop))
    t = (m1.index.hour * 60 + m1.index.minute).to_numpy()
    dia = np.array(m1.index.date)
    onda = m1["onda"].to_numpy() if "onda" in m1 else np.zeros(len(m1))
    estado = {}  # (dia, onda) -> [tentativas, alguma_win, ultima_win]
    out, pos = [], None

    def permite(k):
        """max_tent=0 = sem limite. cond: sempre | ultima_win (so' reentra se a anterior foi win) | alguma_win (se alguma da onda foi win)."""
        e = estado.get(k)
        if e is None or e[0] == 0: return True
        if max_tent and e[0] >= max_tent: return False
        return cond == "sempre" or (cond == "ultima_win" and e[2]) or (cond == "alguma_win" and e[1])

    def reg(preco, mot, i, com_slip=False):
        rs = (pos["d"] * (preco - pos["e"]) - custo - (slip if com_slip else 0.0)) * R
        e = estado[pos["k"]]; e[1] = e[1] or rs > 0; e[2] = rs > 0
        out.append((pos["dia"], rs, mot, pos["t"], m1.index[i], pos["d"], pos["e"], preco))
    for i in range(len(m1)):
        if pos is not None:
            if t[i] >= ZERAR or dia[i] != pos["dia"]:
                reg(o[i], "zera", i); pos = None; continue
            if ab5[i]:
                if min(vd[i], rx[i]) < fc[i] < max(vd[i], rx[i]):
                    reg(o[i], "canal", i); pos = None; continue
                if esticada:  # saida por esticada: afastamento (fech - roxa) em ATR; armado acima de arma, sai ao recuar `recuo` do pico
                    est = pos["d"] * (fc[i] - rx[i]) / m1["fatr"].to_numpy()[i]
                    if est >= esticada[0]: pos["arm"] = True
                    pos["pico"] = max(pos["pico"], est)
                    if pos["arm"] and est <= pos["pico"] - esticada[1]:
                        reg(o[i], "esticada", i); pos = None; continue
                pos["sl"] = nivel[i] + pos["d"] * fs[i]
            if be and m1.index[i] >= pos["t"].floor("5min") + pd.Timedelta(minutes=be[0]) and pos["d"] * (o[i] - pos["e"]) <= be[1]:
                reg(o[i], "break_even", i); pos = None; continue
        elif ab5[i] and sig[i] != 0 and t[i] < SEM_ENTRADA and permite((dia[i], onda[i])):
            if folga_atr and int(sig[i]) * (o[i] - (nivel[i] + int(sig[i]) * fs[i])) <= 0:
                continue  # stop do lado errado do preco: o EA nao consegue colocar essa ordem, ignora a entrada
            k = (dia[i], onda[i]); estado.setdefault(k, [0, False, False])[0] += 1
            pos = {"d": int(sig[i]), "e": o[i], "sl": nivel[i] + int(sig[i]) * fs[i], "dia": dia[i], "t": m1.index[i], "k": k, "arm": False, "pico": -1e9}
        if pos is None:
            continue
        if pos["d"] == 1 and l[i] <= pos["sl"]:
            reg(min(pos["sl"], o[i]), "stop_" + stop_em, i, True); pos = None
        elif pos["d"] == -1 and h[i] >= pos["sl"]:
            reg(max(pos["sl"], o[i]), "stop_" + stop_em, i, True); pos = None
    return pd.DataFrame(out, columns=["dia", "rs", "mot", "t_entrada", "t_saida", "dir", "entrada", "saida"])


def simular_vela(m1, mult=2.0, custo=CUSTO, slip=SLIP):
    """Regra 'vela': stop na minima (compra) / maxima (venda) da ULTIMA M5 FECHADA (a vela do sinal); alvo = mult x a distancia
    entrada-stop. Fixos depois da entrada. Dentro de uma barra M1 o stop vale antes do alvo. Colunas vmin/vmax = M5 recem-fechada."""
    o, h, l = (m1[k].to_numpy() for k in ("open", "high", "low"))
    sig, ab5 = m1["sinal"].to_numpy(), m1["abre5"].to_numpy()
    vmin, vmax = m1["vmin"].to_numpy(), m1["vmax"].to_numpy()
    t = (m1.index.hour * 60 + m1.index.minute).to_numpy()
    dia = np.array(m1.index.date)
    out, pos = [], None

    def reg(preco, mot, i, com_slip=False):
        rs = (pos["d"] * (preco - pos["e"]) - custo - (slip if com_slip else 0.0)) * R
        out.append((pos["dia"], rs, mot, pos["t"], m1.index[i], pos["d"], pos["e"], preco))
    for i in range(len(m1)):
        if pos is not None:
            if t[i] >= ZERAR or dia[i] != pos["dia"]:
                reg(o[i], "zera", i); pos = None; continue
        elif ab5[i] and sig[i] != 0 and t[i] < SEM_ENTRADA:
            d = int(sig[i]); sl = vmin[i] if d == 1 else vmax[i]
            dist = d * (o[i] - sl)
            if dist > 0:
                pos = {"d": d, "e": o[i], "sl": sl, "tp": o[i] + d * mult * dist, "dia": dia[i], "t": m1.index[i]}
        if pos is None:
            continue
        if pos["d"] == 1:
            if l[i] <= pos["sl"]:
                reg(min(pos["sl"], o[i]), "stop", i, True); pos = None
            elif h[i] >= pos["tp"]:
                reg(pos["tp"], "alvo", i); pos = None
        else:
            if h[i] >= pos["sl"]:
                reg(max(pos["sl"], o[i]), "stop", i, True); pos = None
            elif l[i] <= pos["tp"]:
                reg(pos["tp"], "alvo", i); pos = None
    return pd.DataFrame(out, columns=["dia", "rs", "mot", "t_entrada", "t_saida", "dir", "entrada", "saida"])


ap = argparse.ArgumentParser()
ap.add_argument("--stop", type=float, default=300); ap.add_argument("--alvo", type=float, default=600)
ap.add_argument("--trail-on", type=float, default=100); ap.add_argument("--trail-dist", type=float, default=60)
ap.add_argument("--nota", default="")
ap.add_argument("--be-min", type=int, default=0, help="break-even a mercado (Win_c1.mq5 v2.05): minutos apos a abertura da M5 de entrada (0 = desligado)")
ap.add_argument("--be-colchao", type=float, default=7.0, help="break-even: colchao em pontos a favor")
ap.add_argument("--mes", default="2026-09", help="mes simulado (padrao: setembro, o mes de refino)")
ap.add_argument("--dry", action="store_true", help="so' imprime o resultado, sem gravar teste nem gerar o HTML")
ap.add_argument("--regra", choices=["padrao", "canal", "vela"], default="padrao")
ap.add_argument("--folga", type=float, default=None, help="so entra se a ponta do pavio estiver a <= N pontos da roxa")
ap.add_argument("--dist-min", type=float, default=None, help="so entra se a ponta do pavio estiver a >= N pontos da roxa (nao colado)")
ap.add_argument("--stop-folga", type=float, default=0.0, help="stop a N pontos da media, do lado do preco (fecha se chegar mais perto)")
ap.add_argument("--stop-folga-atr", type=float, default=None, help="como --stop-folga, mas N x ATR14 M5 (da M5 recem-fechada)")
ap.add_argument("--gap-atr-max", type=float, default=None, help="so entra se |roxa-verde| / ATR14 M5 da vela do sinal for < N")
ap.add_argument("--ext-roxa-min-atr", type=float, default=None, help="so entra se o extremo da vela do sinal estiver a >= N x ATR da roxa")
ap.add_argument("--dist-verde-min-atr", type=float, default=None, help="so entra se o fechamento da vela do sinal estiver a >= N x ATR da verde (no sentido da operacao)")
ap.add_argument("--esticada", type=float, nargs=2, default=None, metavar=("ARMA_ATR", "RECUO_ATR"), help="sai quando o afastamento do fechamento a roxa, ja' acima de ARMA ATR, recua RECUO ATR do pico")
ap.add_argument("--toques-max", type=int, default=None, help="so entra se, nas ultimas --toques-janela velas M5 fechadas, no maximo N tocaram a roxa")
ap.add_argument("--toques-janela", type=int, default=20)
ap.add_argument("--horas-sem-entrada", default=None, help="horas cheias do servidor sem entrada nova, ex: 11,15,16,17")
ap.add_argument("--alinhar-m15", action="store_true", help="so entra se a ultima M15 FECHADA na entrada (abertura da M5 seguinte) tem close do lado do sinal da roxa M15 e a verde M15 do lado oposto (AlinharM15 do Win.mq5 v2.02)")
ap.add_argument("--ema-filtro", type=int, default=None, metavar="PERIODO", help="so compra com o close da M5 do sinal ACIMA da EMA(PERIODO) do close M5 e so vende ABAIXO (decisao no fechamento, entrada na abertura da M5 seguinte)")
ap.add_argument("--max-tent", type=int, default=0, help="max entradas por onda (0 = sem limite)")
ap.add_argument("--cond", choices=["sempre", "ultima_win", "alguma_win"], default="sempre")
ap.add_argument("--idade-max", type=int, default=None, help="so entra se a vela do sinal for no maximo a N-esima vela M5 seguida do mesmo lado da roxa (fechamento)")
ap.add_argument("--mult", type=float, default=2.0)
ap.add_argument("--stop-em", choices=["verde", "roxa"], default="verde")
a = ap.parse_args()

assert mt5.initialize()
rows = []
for d0 in pd.date_range("2026-07-01", "2026-10-02", freq="5D"):
    r = mt5.copy_rates_range("WINV26", mt5.TIMEFRAME_M1, d0.to_pydatetime(), (d0 + pd.Timedelta(days=5)).to_pydatetime())
    if r is not None and len(r): rows.append(pd.DataFrame(r))
m1 = pd.concat(rows).drop_duplicates("time")
m1.index = pd.to_datetime(m1["time"], unit="s"); m1 = m1.sort_index()[["open","high","low","close"]].astype(float)
m5 = m1.resample("5min").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
m5["wma"], m5["smma"] = lwma(m5.close, 34), smma(m5.close, 34)
s5 = pd.Series(np.where((m5.low > m5.wma) & (m5.smma < m5.wma), 1, np.where((m5.high < m5.wma) & (m5.smma > m5.wma), -1, 0)), index=m5.index)
s5[m5.wma.isna() | m5.smma.isna()] = 0
nz = s5[s5 != 0]
onda5 = (nz != nz.shift()).cumsum().reindex(s5.index).ffill().fillna(0)  # onda = sequencia de sinais do mesmo lado (base, sem filtros)
if a.folga is not None:
    perto = np.where(s5 == 1, (m5.low - m5.wma) <= a.folga, np.where(s5 == -1, (m5.wma - m5.high) <= a.folga, True))
    s5[~perto] = 0
if a.idade_max is not None:
    lado = np.sign(m5.close - m5.wma).fillna(0)
    idade = lado.groupby((lado != lado.shift()).cumsum()).cumcount() + 1
    s5[(s5 != 0) & (idade > a.idade_max)] = 0
if a.dist_min is not None:
    longe = np.where(s5 == 1, (m5.low - m5.wma) >= a.dist_min, np.where(s5 == -1, (m5.wma - m5.high) >= a.dist_min, True))
    s5[~longe] = 0
if a.gap_atr_max is not None:
    tr0 = pd.concat([m5.high - m5.low, (m5.high - m5.close.shift()).abs(), (m5.low - m5.close.shift()).abs()], axis=1).max(axis=1)
    gap_atr = (m5.wma - m5.smma).abs() / tr0.rolling(14).mean()
    s5[(s5 != 0) & ~(gap_atr < a.gap_atr_max)] = 0
if a.ext_roxa_min_atr is not None or a.dist_verde_min_atr is not None:
    tr1 = pd.concat([m5.high - m5.low, (m5.high - m5.close.shift()).abs(), (m5.low - m5.close.shift()).abs()], axis=1).max(axis=1)
    atr5 = tr1.rolling(14).mean()
    if a.ext_roxa_min_atr is not None:
        ext = np.where(s5 == 1, m5.high - m5.wma, m5.wma - m5.low) / atr5
        s5[(s5 != 0) & ~(ext >= a.ext_roxa_min_atr)] = 0
    if a.dist_verde_min_atr is not None:
        dv = np.where(s5 == 1, m5.close - m5.smma, m5.smma - m5.close) / atr5
        s5[(s5 != 0) & ~(dv >= a.dist_verde_min_atr)] = 0
if a.toques_max is not None:
    tq = np.where(s5 == 1, m5.low <= m5.wma, np.where(s5 == -1, m5.high >= m5.wma, False)).astype(float)
    nt = pd.Series(np.nan, index=m5.index)
    for i in np.flatnonzero(s5.to_numpy() != 0):
        d = s5.iloc[i]; a0 = max(0, i - a.toques_janela + 1)
        seg = m5.iloc[a0:i + 1]
        nt.iloc[i] = ((seg.low <= seg.wma) if d == 1 else (seg.high >= seg.wma)).sum()
    s5[(s5 != 0) & ~(nt <= a.toques_max)] = 0
if a.alinhar_m15:   # M15 so' vale a partir do FECHAMENTO da barra: o instante da entrada e' a abertura da M5 seguinte
    m15 = m1.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    m15["w"], m15["s"] = lwma(m15.close, 34), smma(m15.close, 34)
    m15.index = m15.index + pd.Timedelta(minutes=15)
    k15 = m15.reindex(m5.index + pd.Timedelta(minutes=5), method="ffill")
    d15 = s5.to_numpy()
    ok15 = (np.sign(k15.close.to_numpy() - k15.w.to_numpy()) == d15) & np.where(d15 == 1, k15.s.to_numpy() < k15.w.to_numpy(), k15.s.to_numpy() > k15.w.to_numpy())
    s5[(s5 != 0) & ~ok15] = 0
if a.ema_filtro:   # EMA do close M5 na vela do sinal (fechada): sem look-ahead
    ema_f = m5.close.ewm(span=a.ema_filtro, adjust=False, min_periods=a.ema_filtro).mean()
    ok_e = np.where(s5 == 1, m5.close > ema_f, np.where(s5 == -1, m5.close < ema_f, True))
    s5[(s5 != 0) & ~ok_e] = 0
if a.horas_sem_entrada:
    hs = [int(h) for h in a.horas_sem_entrada.split(",") if h.strip()]
    s5[(s5 != 0) & np.isin((s5.index + pd.Timedelta(minutes=5)).hour, hs)] = 0
x = m1[m1.index.strftime("%Y-%m") == a.mes].copy()
x["sinal"] = pd.Series(s5.values, index=s5.index + pd.Timedelta(minutes=5)).reindex(x.index).fillna(0).astype(int)
x["troca"] = False; x["abre5"] = x.index.minute % 5 == 0
if a.regra == "vela":
    desl = s5.index + pd.Timedelta(minutes=5)
    for col, serie in (("vmin", m5.low), ("vmax", m5.high)):
        x[col] = pd.Series(serie.values, index=desl).reindex(x.index)
    t = simular_vela(x, a.mult)
elif a.regra == "canal":
    desl = s5.index + pd.Timedelta(minutes=5)
    for col, serie in (("verde", m5.smma), ("roxa", m5.wma), ("fech", m5.close)):
        x[col] = pd.Series(serie.values, index=desl).reindex(x.index)
    tr_ = pd.concat([m5.high - m5.low, (m5.high - m5.close.shift()).abs(), (m5.low - m5.close.shift()).abs()], axis=1).max(axis=1)
    x["fatr"] = pd.Series(tr_.rolling(14).mean().values, index=desl).reindex(x.index)
    x["onda"] = pd.Series(onda5.values, index=desl).reindex(x.index).fillna(0).astype(int)
    t = simular_canal(x, a.stop_em, a.stop_folga, a.max_tent, a.cond, folga_atr=a.stop_folga_atr, esticada=a.esticada, be=(a.be_min, a.be_colchao) if a.be_min else None)
else:
    t = simular(x, a.stop, a.alvo, trail_on=a.trail_on, trail_dist=a.trail_dist)
    t["pts"] = t.rs / R + CUSTO + np.where(t.mot.isin(["stop", "trail"]), SLIP, 0)
    t["saida"] = t.entrada + t["dir"] * t.pts

if a.dry:
    print("DRY", a.mes, "BE", a.be_min, a.be_colchao, "n", len(t), "liq", round(float(t.rs.sum()), 2), "win%", round(100 * float((t.rs > 0).mean()), 1), "motivos", t.mot.value_counts().to_dict(), flush=True)
    sys.exit(0)
fmt = lambda s: s.strftime("%Y-%m-%d %H:%M:%S")
dias = []
for dia, g in t.groupby("dia"):
    c = m5[m5.index.date == dia]
    dias.append({"dia": str(dia), "liq": round(float(g.rs.sum()), 2), "n": len(g), "win": int((g.rs > 0).sum()),
        "t": [fmt(i) for i in c.index], "o": c.open.tolist(), "h": c.high.tolist(), "l": c.low.tolist(), "c": c.close.tolist(),
        "w": [None if pd.isna(v) else round(v, 1) for v in c.wma], "s": [None if pd.isna(v) else round(v, 1) for v in c.smma],
        "ops": [{"te": fmt(r.t_entrada), "ts": fmt(r.t_saida), "d": int(r.dir), "e": float(r.entrada), "x": round(float(r.saida), 1),
                 "rs": round(float(r.rs), 2), "mot": r.mot} for r in g.itertuples()]})
teste = {"hora": datetime.now().strftime("%d/%m %H:%M"), "nota": a.nota + ("" if a.idade_max is None else f" · entrada só até a {a.idade_max}ª vela do mesmo lado da roxa") + ("" if not a.max_tent else f" · máx {a.max_tent} entrada(s) por onda ({a.cond.replace('_', ' ')})") + ("" if not a.stop_folga else f" · fecha se chegar a menos de {a.stop_folga:g} pts da {a.stop_em}") + ("" if not a.stop_folga_atr else f" · fecha se chegar a menos de {a.stop_folga_atr:g} x ATR da {a.stop_em}") + ("" if a.folga is None else f" · entrada só com a ponta do pavio a ≤ {a.folga:g} pts da roxa") + ("" if a.gap_atr_max is None else f" · entrada só com gap roxa-verde < {a.gap_atr_max:g} x ATR") + ("" if not a.horas_sem_entrada else f" · sem entrada nas horas {a.horas_sem_entrada} (servidor)") + ("" if a.toques_max is None else f" · no máx {a.toques_max} toques na roxa nas últimas {a.toques_janela} velas") + ("" if a.ext_roxa_min_atr is None else f" · extremo da vela a ≥ {a.ext_roxa_min_atr:g} x ATR da roxa") + ("" if a.dist_verde_min_atr is None else f" · fechamento a ≥ {a.dist_verde_min_atr:g} x ATR da verde") + ("" if not a.esticada else f" · sai por esticada: arma em {a.esticada[0]:g} x ATR da roxa, recuo de {a.esticada[1]:g} x ATR do pico") + ("" if a.dist_min is None else f" · entrada só com a ponta do pavio a ≥ {a.dist_min:g} pts da roxa (não colado)") + ("" if not a.ema_filtro else f" · EMA{a.ema_filtro} do close M5: compra só com o close da vela do sinal acima da EMA, venda só abaixo") + ("" if not a.alinhar_m15 else " · M15 alinhado (última M15 fechada: close do lado do sinal da roxa M15 e verde M15 do lado oposto)") + ("" if not a.be_min else f" · break-even a mercado: a partir de {a.be_min} min depois da abertura da M5 de entrada, fecha a mercado se o flutuante for ≤ {a.be_colchao:g} pts a favor"),
         "params": (f"stop na minima/maxima da vela anterior · alvo {a.mult:g}x o stop (fixos)" if a.regra == "vela" else f"stop na {a.stop_em} · sai se M5 fechar no canal roxa/verde (sem alvo, sem trailing)" if a.regra == "canal" else f"stop {a.stop:g} · alvo {a.alvo:g} · trailing {a.trail_on:g}/{a.trail_dist:g}"),
         "tot": {"liq": round(float(t.rs.sum()), 2), "n": len(t), "w": int((t.rs > 0).sum()),
                 "win": round(100 * float((t.rs > 0).mean()), 1), "dias": len(dias)}, "dias": dias}

OUT.mkdir(parents=True, exist_ok=True)
arq = OUT / "testes.json"
hist = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
teste["num"] = len(hist) + 1
hist.append(teste)
arq.write_text(json.dumps(hist), encoding="utf-8")
ordenado = sorted(hist, key=lambda z: -z["num"])  # mais recente primeiro

html = r"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Win setembro WINV26</title><script>__PLOTLY__</script>
<style>:root{--bg:#0e1116;--fg:#e6e9ee;--mut:#8a93a3;--card:#161b22;--bd:#262d38;--g:#4ade80;--r:#f87171}
@media (prefers-color-scheme:light){:root{--bg:#f6f7f9;--fg:#15181d;--mut:#5b6472;--card:#fff;--bd:#dde1e7;--g:#15803d;--r:#b91c1c}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}main{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 8px}.sub{color:var(--mut);margin-bottom:16px}.card{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:12px;margin-bottom:16px}
.h{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-weight:600}.pos{color:var(--g)}.neg{color:var(--r)}
table{border-collapse:collapse;width:100%;font-size:12px;margin-top:8px}th,td{padding:3px 8px;text-align:right;border-bottom:1px solid var(--bd)}th:first-child,td:first-child{text-align:left}
.chart{height:460px}summary{cursor:pointer}.rz{color:var(--fg);background:var(--card);border:1px solid var(--bd);border-radius:6px;padding:3px 10px;font-size:12px;cursor:pointer;margin-right:8px}
nav{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}nav button{color:var(--fg);background:var(--card);border:1px solid var(--bd);border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;font-weight:600}nav button.on{background:var(--fg);color:var(--bg)}nav button.neg:not(.on){color:var(--r)}nav button.pos:not(.on){color:var(--g)}
#tests button{font-size:13px;padding:6px 14px;text-align:left}#tests small{display:block;font-weight:400;opacity:.8}</style></head><body><main>
<h1>Win.mq5 em WINV26, setembro/2026 (refino)</h1><nav id="tests"></nav><div class="sub" id="sub"></div><nav id="nav"></nav><div id="view"></div></main>
<script>const TESTES=__TESTES__;const f=v=>v.toLocaleString('pt-BR',{minimumFractionDigits:2});
const tests=document.getElementById('tests'),nav=document.getElementById('nav'),view=document.getElementById('view'),sub=document.getElementById('sub');
const dark=!matchMedia('(prefers-color-scheme:light)').matches,fg=dark?'#e6e9ee':'#15181d',gr=dark?'#262d38':'#dde1e7';
let D=[],faixa=null;function resetaZoom(){if(faixa)Plotly.relayout('chart',faixa);}
TESTES.forEach((z,k)=>tests.insertAdjacentHTML('beforeend',`<button data-k="${k}" class="${z.tot.liq<0?'neg':'pos'}">Teste ${z.num}<small>${z.hora} · R$ ${f(z.tot.liq)}</small></button>`));
function teste(k){const z=TESTES[k];D=z.dias;
tests.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.k===k));
sub.innerHTML=`<b>Teste ${z.num}</b> (${z.hora}) · ${z.tot.n} operações em ${z.tot.dias} pregões · <b>win: ${z.tot.w}/${z.tot.n} · loss: ${z.tot.n-z.tot.w}/${z.tot.n}</b> · líquido <b class="${z.tot.liq<0?'neg':'pos'}">R$ ${f(z.tot.liq)}</b> · ${String(z.tot.win).replace('.',',')}% de win · ${z.params} · custo 5 pts + 2 de slippage no stop · simulação M1${z.nota?' · '+z.nota:''}. Compra ▲, venda ▼; linha tracejada liga entrada à saída.`;
nav.innerHTML='';D.forEach((d,i)=>nav.insertAdjacentHTML('beforeend',`<button data-i="${i}" class="${d.liq<0?'neg':'pos'}">${d.dia.slice(8)}</button>`));
mostra(0);}
function mostra(i){
const d=D[i];nav.querySelectorAll('button').forEach(b=>b.classList.toggle('on',+b.dataset.i===i));
const pts=o=>{const v=Math.round(o.rs/0.2);return (v>0?'+':'')+v+' pts';};
const rows=d.ops.map(o=>`<tr><td>${o.te.slice(11,16)}</td><td>${o.ts.slice(11,16)}</td><td>${o.d>0?'compra':'venda'}</td><td>${o.e}</td><td>${o.x}</td><td>${o.mot}</td><td class="${o.rs<0?'neg':'pos'}">${pts(o)}</td><td class="${o.rs<0?'neg':'pos'}">${f(o.rs)}</td></tr>`).join('');
view.innerHTML=`<section class="card"><div class="h"><span>${d.dia}</span><span>win: ${d.win}/${d.n} · loss: ${d.n-d.win}/${d.n} · <span class="${d.liq<0?'neg':'pos'}">R$ ${f(d.liq)}</span></span></div><div class="chart" id="chart"></div><button class="rz" onclick="resetaZoom()">resetar zoom (zoom out)</button>
<details><summary>operações</summary><table><tr><th>entrada</th><th>saída</th><th>lado</th><th>preço ent.</th><th>preço saí.</th><th>saída por</th><th>pontos</th><th>R$</th></tr>${rows}</table></details></section>`;
const lo=Math.min(...d.l),hi=Math.max(...d.h),mg=(hi-lo)*0.04;faixa={'xaxis.range':[d.t[0],d.t[d.t.length-1]],'yaxis.range':[lo-mg,hi+mg],'xaxis.autorange':false,'yaxis.autorange':false};
const dj=d.o.map((v,j)=>v===d.c[j]),nd=a=>a.map((v,j)=>dj[j]?null:v),so=a=>a.map((v,j)=>dj[j]?v:null);
const tr=[{type:'candlestick',x:d.t,open:nd(d.o),high:nd(d.h),low:nd(d.l),close:nd(d.c),name:'WINV26 M5',increasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#ffffff'},decreasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#000000'}},
{type:'candlestick',x:d.t,open:so(d.o),high:so(d.h),low:so(d.l),close:so(d.c),name:'doji',showlegend:false,increasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#9ca3af'},decreasing:{line:{color:'#ffffff',width:1.5},fillcolor:'#9ca3af'}},
{x:d.t,y:d.w,mode:'lines',name:'roxa WMA34',line:{color:'#a855f7',width:1.5}},{x:d.t,y:d.s,mode:'lines',name:'verde SMMA34',line:{color:'#22c55e',width:1.5}}];
d.ops.forEach(o=>{const c=o.rs>=0?'#4ade80':'#f87171';
tr.push({x:[o.te,o.ts],y:[o.e,o.x],mode:'lines',line:{color:c,width:1.5,dash:'dot'},showlegend:false,hoverinfo:'skip'});
tr.push({x:[o.te],y:[o.e],mode:'markers',marker:{symbol:o.d>0?'triangle-up':'triangle-down',size:11,color:c,line:{color:fg,width:1}},showlegend:false,hovertext:`${o.d>0?'compra':'venda'} ${o.te.slice(11,16)} @ ${o.e}`,hoverinfo:'text'});
tr.push({x:[o.ts],y:[o.x],mode:'markers',marker:{symbol:'x',size:8,color:c},showlegend:false,hovertext:`saída ${o.mot} ${o.ts.slice(11,16)} @ ${o.x} · ${pts(o)} · R$ ${f(o.rs)}`,hoverinfo:'text'});});
Plotly.newPlot('chart',tr,{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:fg},dragmode:'pan',margin:{l:55,r:10,t:10,b:30},xaxis:{rangeslider:{visible:false},gridcolor:gr},yaxis:{gridcolor:gr},legend:{orientation:'h',y:1.08}},{responsive:true,scrollZoom:true,doubleClick:'reset'}).then(resetaZoom);}
tests.addEventListener('click',e=>{const b=e.target.closest('button');if(b)teste(+b.dataset.k);});
nav.addEventListener('click',e=>{const b=e.target.closest('button');if(b)mostra(+b.dataset.i);});
teste(0);
</script></body></html>"""
(OUT / "index.html").write_text(html.replace("__TESTES__", json.dumps(ordenado)).replace("__PLOTLY__", (OUT / "plotly.min.js").read_text(encoding="utf-8")), encoding="utf-8")
from win_replay_painel_injetar import injetar
injetar(OUT / "index.html")  # painel do replay com ticks reais (servidor local)
print(OUT / "index.html", f"Teste {teste['num']}", teste["params"], teste["tot"], flush=True)
