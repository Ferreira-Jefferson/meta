"""Hipóteses pré-registradas pelos analistas nos 40 pregões de descoberta (2026-10-09). Escritas ANTES do teste.

Prefixos: A = lente do alvo, C = lente do contexto antes da entrada, T = lente do trailing.
Em cada hipótese a 1ª variante é a central; as outras são os vizinhos (platô).
Contexto "na entrada" = barra de confirmação (p.tc), ATR de referência A0 = ATR nela.
"""
import numpy as np
import pandas as pd
import indicadores as ind
from stop import estrutura, melhor


def colunas(b):
    v = b.real_volume.astype(float)
    b["vol_rel20"] = v / v.rolling(20).mean().shift(1)
    hhmm = b.index.strftime("%H%M")
    b["vol_rel_hora"] = v / v.groupby(hhmm).transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))
    b["mme21"], b["mme9"] = ind.mme(b.close, 21), ind.mme(b.close, 9)
    b["estoc14"] = ind.estocastico(b, 14, 3)
    b["mms17"], b["mms34"] = ind.mms(b.close, 17), ind.mms(b.close, 34)
    b["hora"] = b.index.hour + b.index.minute / 60
    g = b.groupby("dia")
    b["amp_dia"] = (g.high.cummax() - g.low.cummin()) / b.atr
    dia = g.agg(hi=("high", "max"), lo=("low", "min")).shift(1)
    b["max_ant"], b["min_ant"] = b.dia.map(dia.hi), b.dia.map(dia.lo)


A0 = lambda p, D: D["atr"][p.tc]


# ---------------- A: alvo ----------------
def climax(amp=1.5, v20=1.4, hora=16.0, offset=0.25):
    """Barra a favor com amplitude >= amp ATR e volume >= v20 x média, antes de `hora`: arma limite em c + offset ATR."""
    def alvo(t, p, D):
        if getattr(p, "L", None) is None and t > p.t_ent and D["hora"][t] < hora:
            o, h, l, c, a = D["open"][t], D["high"][t], D["low"][t], D["close"][t], D["atr"][t]
            if p.lado * (c - o) > 0 and h - l >= amp * a and D["vol_rel20"][t] >= v20:
                p.L = c + p.lado * offset * a
        return getattr(p, "L", None)
    return alvo


def rapido(k=2.5, n=4):
    """Alvo em entrada + k x A0 só nas n primeiras barras da posição."""
    return lambda t, p, D: p.px + p.lado * k * A0(p, D) if t - p.t_ent < n else None


def maxmin_ant(lo=0.5, hi=3.0):
    """Alvo na máxima (compra) / mínima (venda) do dia anterior, se ela estiver entre lo e hi x A0 à frente."""
    def alvo(t, p, D):
        nivel = D["max_ant"][p.tc] if p.lado == 1 else D["min_ant"][p.tc]
        return nivel if lo <= p.lado * (nivel - p.px) / A0(p, D) <= hi else None
    return alvo


def mme21_esticada(k=4.0):
    return lambda t, p, D: D["mme21"][t] + p.lado * k * D["atr"][t]


def fim_do_dia(hora=16.0, k=0.5):
    """Controle negativo: depois de `hora`, limite em ext - k ATR (realiza perto do preço)."""
    return lambda t, p, D: p.ext - p.lado * k * D["atr"][t] if D["hora"][t] >= hora else None


# ---------------- C: contexto na entrada ----------------
def alvo_se(cond, k=1.5, em_R=False):
    """Alvo limitado em entrada + k x A0 (ou k x R) só se cond(p, D) na entrada; senão deixa correr."""
    def alvo(t, p, D):
        if not cond(p, D): return None
        return p.px + p.lado * (k * p.R if em_R else k * A0(p, D))
    return alvo


madura = lambda corte: (lambda p, D: p.lado * (D["mms17"][p.tc] - D["mms34"][p.tc]) / A0(p, D) > corte)
dia_amplo = lambda corte: (lambda p, D: D["amp_dia"][p.tc] > corte)
vol_hora_baixo = lambda corte: (lambda p, D: D["vol_rel_hora"][p.tc] < corte)


def trava_se(cond, gatilho=1.5, trava=0.75):
    """Estrutura; e, se cond na entrada e a posição já andou gatilho x A0, trava o stop em entrada + trava x A0."""
    def mover(stop, t, p, D):
        stop = estrutura(stop, t, p, D)
        if cond(p, D) and p.lado * (p.ext - p.px) >= gatilho * A0(p, D):
            stop = melhor(stop, p.px + p.lado * trava * A0(p, D), p.lado)
        return stop
    return mover


def folga_se_esticada(corte=1.2, folga=0.5):
    """Se a entrada está a mais de `corte` ATR da MME21, cada novo pivô do trailing fica `folga` x A0 mais longe."""
    def mover(stop, t, p, D):
        piv = D["pivos"].get(t)
        if piv is None or piv[0] != ("F" if p.lado == 1 else "T"): return stop
        f = folga * A0(p, D) if p.lado * (D["close"][p.tc] - D["mme21"][p.tc]) / A0(p, D) > corte else 0.0
        return melhor(stop, piv[2] - p.lado * f, p.lado)
    return mover


def pular_vol_hora(corte=0.91):
    return lambda b, s: b.vol_rel_hora.to_numpy()[s.pos.to_numpy()] < corte


# ---------------- T: trailing depois da entrada (só aperta: melhor(estrutura, candidato)) ----------------
TICK = 5
mfe_R = lambda p: p.lado * (p.ext - p.px) / p.R


def trava_impulso(K=3, M=1.5, L=0.5):
    """Se a posição faz MFE >= M R em até K barras da entrada, trava L do MFE (acompanha o extremo). K=None: uniforme."""
    def mover(stop, t, p, D):
        stop = estrutura(stop, t, p, D)
        if not getattr(p, "armado", False) and (K is None or t - p.t_ent <= K) and mfe_R(p) >= M: p.armado = True
        return melhor(stop, p.px + L * (p.ext - p.px), p.lado) if getattr(p, "armado", False) else stop
    return mover


def meio_climax(B=1.0, V=1.2, M=1.0, f=0.5):
    """Barra a favor com corpo >= B ATR e volume >= V x média, com MFE >= M R: stop no ponto f do corpo."""
    def mover(stop, t, p, D):
        stop = estrutura(stop, t, p, D)
        o, c = D["open"][t], D["close"][t]
        if p.lado * (c - o) / D["atr"][t] >= B and D["vol_rel20"][t] >= V and mfe_R(p) >= M:
            stop = melhor(stop, o + f * (c - o), p.lado)
        return stop
    return mover


def estagnacao(M=1.5, N=3):
    """MFE >= M R e N barras sem novo extremo: stop além do extremo contrário das barras desde o pico."""
    def mover(stop, t, p, D):
        stop = estrutura(stop, t, p, D)
        if getattr(p, "ext_ult", None) != p.ext: p.ext_ult, p.t_pico = p.ext, t
        if mfe_R(p) >= M and t - p.t_pico >= N:
            seg = slice(p.t_pico + 1, t + 1)
            stop = melhor(stop, D["low"][seg].min() - TICK if p.lado == 1 else D["high"][seg].max() + TICK, p.lado)
        return stop
    return mover


def perde_mme9(M=1.5):
    """MFE >= M R e close do lado errado da MME9: stop além da barra."""
    def mover(stop, t, p, D):
        stop = estrutura(stop, t, p, D)
        if mfe_R(p) >= M and p.lado * (D["close"][t] - D["mme9"][t]) < 0:
            stop = melhor(stop, D["low"][t] - TICK if p.lado == 1 else D["high"][t] + TICK, p.lado)
        return stop
    return mover


def estoc_vira(alto=90, baixo=70, M=1.5):
    """Estocástico a favor passa de `alto` na posição e depois cai abaixo de `baixo`, com MFE >= M R: stop além das 2 últimas barras."""
    def mover(stop, t, p, D):
        stop = estrutura(stop, t, p, D)
        k = D["estoc14"][t] if p.lado == 1 else 100 - D["estoc14"][t]
        if k >= alto: p.estoc_alto = True
        if getattr(p, "estoc_alto", False) and k < baixo and mfe_R(p) >= M:
            stop = melhor(stop, min(D["low"][t], D["low"][t - 1]) - TICK if p.lado == 1 else max(D["high"][t], D["high"][t - 1]) + TICK, p.lado)
        return stop
    return mover


def juntos(*movers):
    def mover(stop, t, p, D):
        for m in movers: stop = melhor(stop, m(stop, t, p, D), p.lado)
        return stop
    return mover


VARIANTES = {
    "A1": {"clímax 1,5 ATR, vol 1,4, antes 16h, c+0,25": dict(alvo=climax()),
           "offset 0": dict(alvo=climax(offset=0)), "offset 0,5": dict(alvo=climax(offset=0.5)),
           "amplitude 1,25": dict(alvo=climax(amp=1.25)), "amplitude 1,75": dict(alvo=climax(amp=1.75)),
           "vol 1,2": dict(alvo=climax(v20=1.2)), "vol 1,6": dict(alvo=climax(v20=1.6)),
           "antes 15h30": dict(alvo=climax(hora=15.5)), "antes 16h30": dict(alvo=climax(hora=16.5))},
    "A2": {"2,5 A0 nas 4 primeiras barras": dict(alvo=rapido()),
           "3 barras": dict(alvo=rapido(n=3)), "6 barras": dict(alvo=rapido(n=6)),
           "2 A0": dict(alvo=rapido(k=2)), "3 A0": dict(alvo=rapido(k=3))},
    "A3": {"clímax (A1) só 1 contrato": dict(alvo=climax(), contratos_alvo=1),
           "offset 0, 1 contrato": dict(alvo=climax(offset=0), contratos_alvo=1),
           "offset 0,5, 1 contrato": dict(alvo=climax(offset=0.5), contratos_alvo=1),
           "amplitude 1,25, 1 contrato": dict(alvo=climax(amp=1.25), contratos_alvo=1),
           "amplitude 1,75, 1 contrato": dict(alvo=climax(amp=1.75), contratos_alvo=1)},
    "A4": {"máx/mín D-1 a 0,5-3 A0": dict(alvo=maxmin_ant()),
           "1-3 A0": dict(alvo=maxmin_ant(lo=1.0)), "0,5-4 A0": dict(alvo=maxmin_ant(hi=4.0))},
    "A5": {"MME21 + 4 ATR": dict(alvo=mme21_esticada()),
           "+3,5 ATR": dict(alvo=mme21_esticada(3.5)), "+4,5 ATR": dict(alvo=mme21_esticada(4.5))},
    "A6": {"CONTROLE: após 16h limite em ext-0,5 ATR": dict(alvo=fim_do_dia()),
           "após 16h30": dict(alvo=fim_do_dia(16.5)), "após 17h": dict(alvo=fim_do_dia(17.0)),
           "1,0 ATR": dict(alvo=fim_do_dia(k=1.0))},
    "C1": {"madura (MMS17-34 > 1,5 ATR): alvo 1,5 A0": dict(alvo=alvo_se(madura(1.5))),
           "corte 1,3": dict(alvo=alvo_se(madura(1.3))), "corte 1,8": dict(alvo=alvo_se(madura(1.8))),
           "alvo 1,25 A0": dict(alvo=alvo_se(madura(1.5), 1.25)), "alvo 2 A0": dict(alvo=alvo_se(madura(1.5), 2.0)),
           "alvo 1R": dict(alvo=alvo_se(madura(1.5), 1.0, em_R=True))},
    "C2": {"dia amplo (> 6,5 ATR): alvo 1,5 A0": dict(alvo=alvo_se(dia_amplo(6.5))),
           "corte 5,5": dict(alvo=alvo_se(dia_amplo(5.5))), "corte 6": dict(alvo=alvo_se(dia_amplo(6.0))),
           "corte 7": dict(alvo=alvo_se(dia_amplo(7.0))),
           "alvo 1,25 A0": dict(alvo=alvo_se(dia_amplo(6.5), 1.25)), "alvo 2 A0": dict(alvo=alvo_se(dia_amplo(6.5), 2.0))},
    "C3": {"madura: trava 0,75 A0 após 1,5 A0": dict(mover=trava_se(madura(1.5))),
           "trava 0,5": dict(mover=trava_se(madura(1.5), 1.5, 0.5)), "trava 1,0": dict(mover=trava_se(madura(1.5), 1.5, 1.0)),
           "gatilho 2, trava 1": dict(mover=trava_se(madura(1.5), 2.0, 1.0))},
    "C4": {"vol do horário < 1: alvo 1,5 A0": dict(alvo=alvo_se(vol_hora_baixo(1.0))),
           "corte 0,9": dict(alvo=alvo_se(vol_hora_baixo(0.9))), "corte 1,1": dict(alvo=alvo_se(vol_hora_baixo(1.1))),
           "corte 1,2": dict(alvo=alvo_se(vol_hora_baixo(1.2))),
           "alvo 1,25 A0": dict(alvo=alvo_se(vol_hora_baixo(1.0), 1.25)), "alvo 2 A0": dict(alvo=alvo_se(vol_hora_baixo(1.0), 2.0))},
    "C5": {"esticada da MME21 (> 1,2): pivô 0,5 A0 mais longe": dict(mover=folga_se_esticada()),
           "corte 1,0": dict(mover=folga_se_esticada(1.0)), "corte 1,4": dict(mover=folga_se_esticada(1.4)),
           "folga 0,25": dict(mover=folga_se_esticada(folga=0.25)), "folga 1,0": dict(mover=folga_se_esticada(folga=1.0))},
    "C6": {"pular se vol do horário < 0,91": dict(pular=pular_vol_hora()),
           "corte 0,85": dict(pular=pular_vol_hora(0.85)), "corte 1,0": dict(pular=pular_vol_hora(1.0))},
    "T1": {"impulso rápido: MFE 1,5R em 3 barras, trava 0,5 do MFE": dict(mover=trava_impulso()),
           "K 2": dict(mover=trava_impulso(K=2)), "K 4": dict(mover=trava_impulso(K=4)),
           "M 1,0": dict(mover=trava_impulso(M=1.0)), "M 2,0": dict(mover=trava_impulso(M=2.0)),
           "L 0,33": dict(mover=trava_impulso(L=0.33)), "L 0,67": dict(mover=trava_impulso(L=0.67))},
    "T1c": {"CONTROLE: mesma trava sem limite de barras (uniforme)": dict(mover=trava_impulso(K=None))},
    "T2": {"meio do candle de clímax (corpo 1 ATR, vol 1,2, MFE 1R)": dict(mover=meio_climax()),
           "corpo 0,75": dict(mover=meio_climax(B=0.75)), "corpo 1,25": dict(mover=meio_climax(B=1.25)),
           "vol 1,0": dict(mover=meio_climax(V=1.0)), "vol 1,5": dict(mover=meio_climax(V=1.5)),
           "MFE 0,75R": dict(mover=meio_climax(M=0.75)), "MFE 1,5R": dict(mover=meio_climax(M=1.5)),
           "abertura do candle (f=0)": dict(mover=meio_climax(f=0.0))},
    "T3": {"estagnação: MFE 1,5R e 3 barras sem extremo": dict(mover=estagnacao()),
           "M 1,0": dict(mover=estagnacao(M=1.0)), "M 2,0": dict(mover=estagnacao(M=2.0)),
           "N 2": dict(mover=estagnacao(N=2)), "N 4": dict(mover=estagnacao(N=4))},
    "T4": {"perde a MME9 após MFE 1,5R": dict(mover=perde_mme9()),
           "M 1,0": dict(mover=perde_mme9(1.0)), "M 2,0": dict(mover=perde_mme9(2.0))},
    "T5": {"estocástico 90 -> 70 após MFE 1,5R": dict(mover=estoc_vira()),
           "85 -> 60": dict(mover=estoc_vira(85, 60)), "95 -> 80": dict(mover=estoc_vira(95, 80)),
           "MFE 1,0R": dict(mover=estoc_vira(M=1.0))},
    "T6": {"T1 + T2 juntos": dict(mover=juntos(trava_impulso(), meio_climax()))},
}
