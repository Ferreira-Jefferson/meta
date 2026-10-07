"""Replay do WinDeslocamentoMatinal.mq5 sobre TICKS REAIS (bid/ask/last) do WIN.

Replica a logica do EA tick a tick:
  - decisao na virada para a vela M1 de abertura + `minutos_decisao` (90) minutos, olhando so' as M1 FECHADAS;
  - ATR = media do True Range de `periodo_atr` (14) dias ate' D-1 (diarias montadas das M1);
  - sinal: fechamento >= abertura +/- desloc_min_atr x ATR e nenhuma M1 do dia fechou do outro lado da abertura
    alem da banda (banda_atr x ATR);
  - entrada por LIMITE no ultimo fechamento M1; se ja' cruzou o livro (compra: limite >= ask; venda: limite <= bid)
    vai para a melhor oferta do proprio lado (bid na compra, ask na venda); prazo `entrada_ttl_min` (15 min);
  - stop do outro lado da abertura (abertura -/+ banda), enviado com a ordem e reancorado ao preco executado
    (mesma distancia); disparado pelo `last`, executado no bid (compra) / ask (venda) do tick do disparo;
  - zera no bid/ask `minutos_zerar` (5) antes do fim da sessao; 1 operacao por dia;
  - latencia (fixa ou aleatoria 0..N s) em TODA ordem: envio da limite, cancelamento por prazo, reancoragem do
    stop, saida por stop e saida de fim de pregao.

PREENCHIMENTO DA LIMITE (parametro `fill`). A fila do WIN NAO esta calibrada (`fidelidade.py` so' tem WDO@), entao:
  - "atravessar" (padrao, conservador): so' enche quando um negocio sai a preco MELHOR que o limite
    (last < limite na compra, last > limite na venda) -- toque nao e' preencher;
  - "tocar": enche quando o last toca o limite (otimista: ignora a fila).
Nas duas, se o livro vem ate' o limite (ask <= limite na compra, bid >= limite na venda) a ordem executa no
preco do livro, igual ou melhor.

Nao cobre: corretagem/emolumentos, fila alem da regra acima, slippage alem do bid/ask do tick. Horario = o do
servidor do MT5 (o mesmo dos ticks/barras do cache).

Uso:  python win_deslocamento_replay_ticks.py --inicio 2026-09-01 --fim 2026-09-30 --latencia 0 --fill atravessar
Ticks baixados do MT5 ficam em data/cache_win_ticks/<ativo>/<dia>.pkl (dias fechados).
"""
import argparse, json, sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import win_replay_ticks as base
from win_replay_ticks import CACHE, TICK, RS_PONTO, carregar_ticks, metricas

# Mesmos nomes/valores dos inputs do WinDeslocamentoMatinal.mq5 (+ fill, que e' do simulador)
PARAMS_PADRAO = dict(
    minutos_decisao=90, janela_decisao_min=5, desloc_min_atr=0.3, banda_atr=0.05, periodo_atr=14,
    entrada_ttl_min=15, minutos_zerar=5, hora_fim=18, minuto_fim=25,
    fill="atravessar",
)


def nt(v):
    return float(np.round(v / TICK) * TICK)


def carregar_m1(ativo: str, inicio: date, fim: date, avisos: list) -> pd.DataFrame:
    """M1 de [inicio-45d, fim] (a folga alimenta o ATR diario). Sem MT5, monta das ticks em cache."""
    try:
        return base.carregar_m1(ativo, inicio - timedelta(days=38), fim)
    except Exception as e:
        avisos.append(f"M1 do MT5 indisponivel ({type(e).__name__}: {e}); montei as barras a partir dos ticks em cache")
    linhas = []
    pasta = CACHE / ativo
    for arq in sorted(pasta.glob("*.pkl")) if pasta.exists() else []:
        d = date.fromisoformat(arq.stem)
        if not (inicio - timedelta(days=45) <= d <= fim):
            continue
        x = pd.read_pickle(arq)
        x = x[x["last"] > 0]
        if x.empty:
            continue
        s = pd.Series(x["last"].to_numpy(), index=pd.to_datetime(x.time_msc.to_numpy(), unit="ms"))
        linhas.append(s.resample("1min").ohlc().dropna())
    if not linhas:
        raise RuntimeError(f"sem barras M1 de {ativo}: MT5 indisponivel e sem ticks em cache")
    return pd.concat(linhas)


def diarias(m1: pd.DataFrame) -> pd.DataFrame:
    g = m1.groupby(m1.index.date)
    return pd.DataFrame({"high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})


def atr_ate(d1: pd.DataFrame, dia: date, n: int):
    """Media dos n True Ranges das ultimas n diarias ANTES de `dia` (igual ao AtrDiario() do EA)."""
    h = d1[d1.index < dia].tail(n + 1)
    if len(h) < n + 1:
        return None
    hi, lo, cl = h.high.to_numpy(), h.low.to_numpy(), h.close.to_numpy()
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    a = float(tr.mean())
    return a if a > 0 else None


def _ffill_nz(a: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    """Cotacao 0 = sem informacao: repete a ultima cotacao valida; sem nenhuma, usa o last."""
    a = a.astype(float).copy()
    a[a <= 0] = np.nan
    s = pd.Series(a).ffill().to_numpy()
    return np.where(np.isnan(s), fallback, s)


def replay_dia(dia, m1d: pd.DataFrame, atr, tick, p, lat, trades, diag):
    tms, bid, ask, last = tick
    n = len(tms)
    last = last.astype(float)
    bid, ask = _ffill_nz(bid, last), _ffill_nz(ask, last)
    fi = lambda t: min(int(np.searchsorted(tms, t)), n - 1)
    ini = pd.Timestamp(dia).value // 10**6
    fim_cfg = p["hora_fim"] * 60 + p["minuto_fim"]
    fim_dia = min(fim_cfg, int((m1d.index[-1].hour * 60 + m1d.index[-1].minute) + 1))   # sessao mais curta (ex.: 17:55)
    t_zera = ini + (fim_dia - p["minutos_zerar"]) * 60000
    if atr is None:
        diag["sem_atr"] += 1
        return
    t_open = m1d.index[0].value // 10**6
    t_dec = t_open + int(p["minutos_decisao"]) * 60000
    i0 = int(np.searchsorted(tms, t_dec))
    if i0 >= n or tms[i0] >= t_zera:
        diag["sem_decisao"] += 1
        return
    if (tms[i0] // 60000 * 60000 - t_open) / 60000 > p["minutos_decisao"] + p["janela_decisao_min"]:
        diag["decisao_atrasada"] += 1
        return
    fech = m1d[m1d.index.values.astype("datetime64[ms]").astype(np.int64) < tms[i0] // 60000 * 60000]
    if fech.empty:
        diag["sem_decisao"] += 1
        return
    ab = float(m1d.open.iloc[0]); banda = p["banda_atr"] * atr
    ultimo = float(fech.close.iloc[-1]); minC, maxC = float(fech.close.min()), float(fech.close.max())
    desloc = ultimo - ab
    if desloc >= p["desloc_min_atr"] * atr and minC >= ab - banda:
        s, linha = 1, ab - banda
    elif -desloc >= p["desloc_min_atr"] * atr and maxC <= ab + banda:
        s, linha = -1, ab + banda
    else:
        diag["sem_sinal"] += 1
        return
    diag["sinais"] += 1
    limite = nt(ultimo)
    if s == 1 and ask[i0] > 0 and limite >= ask[i0]:
        limite = nt(min(bid[i0], ask[i0] - TICK))
    if s == -1 and bid[i0] > 0 and limite <= bid[i0]:
        limite = nt(max(ask[i0], bid[i0] + TICK))
    dist = max(s * (limite - linha), TICK)
    sl0 = nt(limite - s * dist)

    # --- limite de entrada: chega na ordem apos a latencia; cancela no prazo (tambem com latencia)
    ia = fi(tms[i0] + lat())
    t_cancel = min(tms[i0] + p["entrada_ttl_min"] * 60000, t_zera)
    ic = fi(t_cancel + lat())
    j = None
    if ic > ia:
        sl_, bd, ak = last[ia:ic], bid[ia:ic], ask[ia:ic]
        atrav = p["fill"] != "tocar"
        if s == 1:
            c = ((sl_ > 0) & ((sl_ < limite) if atrav else (sl_ <= limite))) | (ak <= limite)
        else:
            c = ((sl_ > 0) & ((sl_ > limite) if atrav else (sl_ >= limite))) | (bd >= limite)
        if c.any():
            j = ia + int(np.argmax(c))
    if j is None:
        diag["nao_encheu"] += 1
        return
    e = limite
    if s == 1 and ask[j] <= limite:
        e = float(ask[j])
    if s == -1 and bid[j] >= limite:
        e = float(bid[j])
    diag["fills"] += 1

    # --- posicao: stop reancorado ao preco executado (depois da latencia), zera no fim do pregao
    sl1 = nt(e - s * dist)
    jr = fi(tms[j] + lat())
    iz = max(fi(t_zera + lat()), j)

    def scan(sl, a, b):
        if b <= a:
            return None
        seg = last[a:b]
        c = (seg > 0) & ((seg <= sl) if s == 1 else (seg >= sl))
        return a + int(np.argmax(c)) if c.any() else None

    k = scan(sl0, j + 1, min(jr, iz))
    sl_ativo = sl0
    if k is None:
        k = scan(sl1, max(jr, j + 1), iz)
        sl_ativo = sl1
    if k is not None:
        ix, mot = fi(tms[k] + lat()), "stop"
    else:
        ix, mot = iz, "zera"
    px = float(bid[ix] if s == 1 else ask[ix])
    trades.append(dict(dia=str(dia), te=pd.Timestamp(int(tms[j]), unit="ms"), tx=pd.Timestamp(int(tms[ix]), unit="ms"),
                       d=s, pe=float(e), px=px, mot=mot, rs=float(s * (px - e) * RS_PONTO),
                       sl=float(sl1), ab=ab, atr=round(atr, 1), lim=float(limite)))


def replay(inicio: date, fim: date, latencia_s=0.0, modo="fixa", params=None, ativo="WINV26", progresso=None) -> dict:
    p = {**PARAMS_PADRAO, **(params or {})}
    if p["fill"] not in ("atravessar", "tocar"):
        raise ValueError(f"fill invalido: {p['fill']!r} (use 'atravessar' ou 'tocar')")
    rng = np.random.default_rng(1)
    L = int(round(float(latencia_s) * 1000))
    lat = (lambda: int(rng.uniform(0, L))) if modo == "aleatoria" else (lambda: L)
    avisos: list = []
    if progresso: progresso(0, 1, "lendo barras M1")
    m1 = carregar_m1(ativo, inicio, fim, avisos)
    d1 = diarias(m1)
    dias = sorted(d for d in set(m1.index.date) if inicio <= d <= fim)
    trades, sem_ticks = [], []
    diag = dict(sinais=0, fills=0, nao_encheu=0, sem_sinal=0, sem_atr=0, sem_decisao=0, decisao_atrasada=0)
    for k, dia in enumerate(dias):
        if progresso: progresso(k, len(dias), f"{dia}: {'lendo ticks' if (CACHE / ativo / f'{dia}.pkl').exists() else 'baixando ticks do MT5'}")
        try:
            tick = carregar_ticks(ativo, dia)
            if len(tick[0]) == 0:
                sem_ticks.append(str(dia)); continue
            replay_dia(dia, m1[m1.index.date == dia], atr_ate(d1, dia, int(p["periodo_atr"])), tick, p, lat, trades, diag)
        except Exception as e:   # um dia ruim nao derruba o periodo: segue e avisa
            sem_ticks.append(str(dia)); avisos.append(f"{dia}: {type(e).__name__}: {e}")
    if dias and len(sem_ticks) == len(dias):
        raise RuntimeError(f"nao ha ticks de {ativo} em nenhum dos {len(dias)} pregoes entre {inicio} e {fim} "
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
            por_mes.append({"mes": mes, **metricas(g, int(len({d for d in dias if str(d)[:7] == mes})))})
    if progresso: progresso(len(dias), len(dias), "pronto")
    out = t.assign(te=t.te.dt.strftime("%Y-%m-%d %H:%M:%S"), tx=t.tx.dt.strftime("%Y-%m-%d %H:%M:%S")).round(2).to_dict("records") if not t.empty else []
    return dict(ativo=ativo, inicio=str(inicio), fim=str(fim), latencia_s=latencia_s, modo=modo, params=p,
                resumo=metricas(t, ndias), por_mes=por_mes, trades=out, diag=diag, dias_sem_ticks=sem_ticks, avisos=avisos)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--inicio", required=True); ap.add_argument("--fim", required=True)
    ap.add_argument("--latencia", type=float, default=0.0, help="segundos")
    ap.add_argument("--modo", choices=["fixa", "aleatoria"], default="fixa")
    ap.add_argument("--fill", choices=["atravessar", "tocar"], default="atravessar")
    ap.add_argument("--ativo", default="WINV26")
    ap.add_argument("--params", default="{}", help='JSON com qualquer chave de PARAMS_PADRAO, ex: \'{"desloc_min_atr":0.5}\'')
    a = ap.parse_args()
    r = replay(date.fromisoformat(a.inicio), date.fromisoformat(a.fim), a.latencia, a.modo, {**json.loads(a.params), "fill": a.fill}, a.ativo,
               lambda k, n, m: print(f"[{k}/{n}] {m}", flush=True))
    print(json.dumps({k: r[k] for k in ("resumo", "por_mes", "diag", "dias_sem_ticks", "avisos")}, ensure_ascii=False, indent=1))
    for o in r["trades"]:
        print(o["te"], o["tx"], "C" if o["d"] > 0 else "V", o["pe"], o["px"], "stop", o["sl"], o["mot"], o["rs"])
