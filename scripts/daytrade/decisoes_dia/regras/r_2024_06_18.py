"""Pregão 2024-06-18 (WIN M15). Abre -380 pts abaixo do fechamento de ontem, sobe 1.500 pts até 10:45
(impulso das 10:30) e depois rotaciona numa faixa 121.200-121.800 até o fim. Dia de impulso + rotação."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import datetime as dt
import base

T = dt.time


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _stop_ok(preco, stop):
    return abs(preco - stop) <= 590


# ------------------------------------------------------------------ FAZER
def f_rompe_faixa_1h(ctx):
    """Rompimento da faixa da 1ª hora (09:00-10:00): depois das 10:00, fechamento acima da máxima da 1ª hora
    com corpo forte (>=0,4 ATR15) compra; abaixo da mínima, vende. Stop no meio da faixa, alvo 1,5x o risco.
    Condição: dia que sai da abertura com impulso (faixa da 1ª hora estreita vs ATR diário). Provavelmente
    geral (rompimento de faixa inicial é fundamento clássico), mas aqui o ganho veio de um único impulso."""
    h = ctx.hoje
    if ctx.t.time() < T(10, 15) or ctx.t.time() > T(12, 0) or len(h) < 5:
        return None
    pri = h[h.index < h.index[0].normalize() + dt.timedelta(hours=10)]
    hi, lo = pri.high.max(), pri.low.min()
    if (hi - lo) > 0.6 * ctx.atrd:
        return None
    u = h.iloc[-1]
    if abs(u.close - u.open) < 0.4 * ctx.atr15:
        return None
    if u.close > hi and h.high.iloc[:-1].max() <= hi + 50:
        stop = (hi + lo) / 2
        if _stop_ok(u.close, stop):
            return dict(lado="compra", stop=stop, alvo=u.close + 1.5 * (u.close - stop), preco=u.close)
    if u.close < lo and h.low.iloc[:-1].min() >= lo - 50:
        stop = (hi + lo) / 2
        if _stop_ok(u.close, stop):
            return dict(lado="venda", stop=stop, alvo=u.close - 1.5 * (stop - u.close), preco=u.close)
    return None


def f_gap_fade_fechamento(ctx):
    """Gap de abertura contra o fechamento de ontem (>=0,15 ATRd) dentro da faixa de ontem: compra (gap de
    baixa) mirando o fechamento de ontem; vice-versa. Só entre 09:15 e 10:00. Condição: gap que não rompe
    máxima/mínima de ontem, dia sem notícia. Ajustada ao dia (gap-fade não replicou nos estudos do projeto)."""
    h = ctx.hoje
    if not (T(9, 15) <= ctx.t.time() <= T(10, 0)):
        return None
    ont = ctx.diario.iloc[-1]
    gap = h.open.iloc[0] - ont.close
    if abs(gap) < 0.15 * ctx.atrd or not (ont.low < h.open.iloc[0] < ont.high):
        return None
    px = h.close.iloc[-1]
    if gap < 0:
        stop = h.low.min() - 60
        if px < ont.close - 100 and _stop_ok(px, stop):
            return dict(lado="compra", stop=stop, alvo=ont.close, preco=px)
    else:
        stop = h.high.max() + 60
        if px > ont.close + 100 and _stop_ok(px, stop):
            return dict(lado="venda", stop=stop, alvo=ont.close, preco=px)
    return None


def f_recuo_tendencia(ctx):
    """Recuo a favor do impulso: após movimento do dia >=0,6 ATRd desde a abertura, se o preço devolveu entre
    20% e 62% do impulso e a vela fecha em alta acima do fechamento anterior, compra. Stop 40 pts abaixo da
    mínima das 4 últimas velas; alvo em 60% do caminho de volta à máxima do dia. Condição: tendência
    intradiária definida com recuo raso. Provavelmente geral (recuo a favor)."""
    h = ctx.hoje
    if len(h) < 6 or ctx.t.time() > T(14, 0):
        return None
    hi = h.high.max()
    imp = hi - h.open.iloc[0]
    if imp < 0.6 * ctx.atrd:
        return None
    u, p = h.iloc[-1], h.iloc[-2]
    ret = (hi - u.close) / imp
    if 0.2 <= ret <= 0.62 and u.close > u.open and u.close > p.close:
        stop = h.low.iloc[-4:].min() - 40
        if _stop_ok(u.close, stop) and hi - u.close > 150:
            return dict(lado="compra", stop=stop, alvo=u.close + 0.6 * (hi - u.close), preco=u.close)
    return None


def f_falha_maxima(ctx):
    """Reversão em falha: vela que chega a 30 pts da máxima do dia (testa o topo) mas fecha em baixa, abaixo do
    fechamento anterior e com volume menor que a vela anterior, após impulso >=0,6 ATRd. Vende, stop 40 pts
    acima da máxima, alvo no meio da faixa do dia. Condição: topo de impulso com volume decrescente.
    Ajustada ao dia."""
    h = ctx.hoje
    if len(h) < 6 or ctx.t.time() > T(13, 0):
        return None
    u = h.iloc[-1]
    topo = h.high.max()
    if u.high >= topo - 30 and topo - h.open.iloc[0] >= 0.6 * ctx.atrd             and u.close < u.open and u.close < h.close.iloc[-2] and u.vol < h.vol.iloc[-2]:
        stop = topo + 40
        alvo = (topo + h.low.min()) / 2
        if _stop_ok(u.close, stop) and u.close - alvo > 150:
            return dict(lado="venda", stop=stop, alvo=alvo, preco=u.close)
    return None


def f_faixa_tarde(ctx):
    """Rotação de faixa: entre 11:30 e 15:30, com faixa das últimas 8 velas M15 <=0,55 ATRd e volume seco,
    compra no 25% inferior da faixa e vende no 25% superior; alvo no meio, stop 150 pts além da borda.
    Condição: dia de rotação após impulso, volume secando. Provavelmente geral em dia lateral, mas depende
    do regime lateral (limiares ajustados ao dia)."""
    h = ctx.hoje
    if not (T(11, 30) <= ctx.t.time() <= T(15, 30)) or len(h) < 10:
        return None
    j = h.iloc[-8:]
    hi, lo = j.high.max(), j.low.min()
    if hi - lo > 0.55 * ctx.atrd or hi - lo < 250:
        return None
    if j.vol.mean() > 0.7 * h.vol.iloc[:6].mean():
        return None
    px = h.close.iloc[-1]
    pos = (px - lo) / (hi - lo)
    meio = (hi + lo) / 2
    if pos <= 0.25 and meio - px > 120:
        return dict(lado="compra", stop=lo - 150, alvo=meio, preco=px)
    if pos >= 0.75 and px - meio > 120:
        return dict(lado="venda", stop=hi + 150, alvo=meio, preco=px)
    return None


# ------------------------------------------------------------------ NAO FAZER
def n_vender_rali_1atr(ctx):
    """ARMADILHA: vender cada rali de 1 ATR15 acima da mínima das últimas 4 velas (stop 1,0 ATR, alvo 1,0 ATR).
    Num dia que sobe em impulso e depois lateraliza, o rali é a perna dominante e a venda é pisada. Veto: não
    vender rali quando o dia tem viés comprador (abertura abaixo, fechamento corrente acima da abertura) e a
    volatilidade é de impulso. Geral (comportamento comum de quem vende esticado)."""
    h = ctx.hoje
    if len(h) < 6 or ctx.t.time() > T(17, 30):
        return None
    u = h.iloc[-1]
    if u.close - h.low.iloc[-4:].min() >= 1.0 * ctx.atr15:
        return dict(lado="venda", stop=u.close + 1.0 * ctx.atr15, alvo=u.close - 1.0 * ctx.atr15, preco=u.close)
    return None


def n_vender_maxima_nova(ctx):
    """ARMADILHA: vender cada máxima nova do dia antes das 12:00. Num impulso de abertura com volume
    crescente a máxima nova continua. Veto: não vender máxima nova quando o volume da vela é maior que o da
    anterior e o dia anda >0,6 ATRd desde a abertura. Geral."""
    h = ctx.hoje
    if len(h) < 4 or ctx.t.time() > T(12, 0):
        return None
    u = h.iloc[-1]
    if u.high >= h.high.max() and h.high.max() > h.high.iloc[:-1].max():
        return dict(lado="venda", stop=u.high + 250, alvo=u.close - 500, preco=u.close)
    return None


def n_rompimento_sem_volume(ctx):
    """ARMADILHA: entrar no rompimento da máxima/mínima das 4 velas anteriores entre 11:00 e 15:00 quando o
    volume da vela não passa 1,3x a média delas (sem confirmação). Rompimento sem volume em faixa de rotação é
    falso. Veto: não seguir rompimento de faixa curta sem volume >1,3x a média das velas anteriores. Geral."""
    h = ctx.hoje
    if not (T(11, 0) <= ctx.t.time() <= T(15, 0)) or len(h) < 6:
        return None
    u, j = h.iloc[-1], h.iloc[-5:-1]
    if u.vol >= 1.3 * j.vol.mean():
        return None
    if u.close > j.high.max():
        return dict(lado="compra", stop=u.close - 300, alvo=u.close + 450, preco=u.close)
    if u.close < j.low.min():
        return dict(lado="venda", stop=u.close + 300, alvo=u.close - 450, preco=u.close)
    return None


def n_seguir_tarde(ctx):
    """ARMADILHA: entre 15:00 e 17:00 seguir a direção das últimas 6 velas (1,5 h). Em dia de rotação o fluxo da tarde não
    continua e os sinais pioram depois das 15h (lição do projeto). Veto: sem entrada de continuação depois
    das 15:00 em dia lateral. Geral."""
    h = ctx.hoje
    if not (T(15, 0) <= ctx.t.time() <= T(17, 0)) or len(h) < 8:
        return None
    u = h.iloc[-1]
    d = h.close.iloc[-1] - h.close.iloc[-7]
    if d > 100:
        return dict(lado="compra", stop=u.close - 300, alvo=u.close + 300, preco=u.close)
    if d < -100:
        return dict(lado="venda", stop=u.close + 300, alvo=u.close - 300, preco=u.close)
    return None


def n_fade_impulso_cedo(ctx):
    """ARMADILHA: vender o primeiro fechamento com corpo forte acima da máxima da 1ª hora (tratar o
    rompimento como falso) entre 10:15 e 11:30. Com gap contra a faixa de ontem e corpo forte o rompimento é
    real. Veto: não fadear rompimento da faixa da 1ª hora com corpo >0,4 ATR15. Geral."""
    h = ctx.hoje
    if not (T(10, 15) <= ctx.t.time() <= T(11, 30)) or len(h) < 5:
        return None
    pri = h[h.index < h.index[0].normalize() + dt.timedelta(hours=10)]
    u = h.iloc[-1]
    if u.close > pri.high.max() and abs(u.close - u.open) > 0.4 * ctx.atr15:
        return dict(lado="venda", stop=u.close + 400, alvo=u.close - 600, preco=u.close)
    return None


FAZER = [("rompe_faixa_1h", f_rompe_faixa_1h, None), ("gap_fade_fechamento", f_gap_fade_fechamento, None),
         ("recuo_tendencia", f_recuo_tendencia, None), ("falha_maxima", f_falha_maxima, None),
         ("faixa_tarde", f_faixa_tarde, None)]
NAO_FAZER = [("vender_rali_1atr", n_vender_rali_1atr, None), ("vender_maxima_nova", n_vender_maxima_nova, None),
             ("rompimento_sem_volume", n_rompimento_sem_volume, None), ("seguir_tarde", n_seguir_tarde, None),
             ("fade_impulso_cedo", n_fade_impulso_cedo, None)]

if __name__ == "__main__":
    for grupo, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, rg, ge in lst:
            r = base.resumo(base.simula_dia("2024-06-18", rg, ge))
            print(f"{grupo:9s} {nome:24s} R$ {r['brl']:9.2f} ops {r['ops']}", flush=True)
            for x in r["lista"]:
                print("    ", x["lado"], x["sinal"], x["ent"], x["sai"], x["motivo"], x["pts"], x["brl"])
