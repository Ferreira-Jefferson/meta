"""Filtros de entrada da v4.1, lidos na barra de confirmação (M15 fechada). Cada um devolve um array booleano
alinhado aos sinais: True = o filtro deixa operar. Venda = espelho da compra."""
import numpy as np
import pandas as pd
import indicadores as ind

AQUECIMENTO_H4 = 30  # barras H4 fechadas antes de o estado do H4 valer (médias aquecidas)


def _no_sinal(serie, s):
    return np.asarray(serie)[s.pos.to_numpy()]


def h1_a_favor(b, s):
    """H1 fechado até o início da barra de confirmação com tendência MME 9/21/34 a favor."""
    c = b.close.resample("60min").last().dropna()
    ten = ind.tendencia(c).to_numpy()
    fim = (c.index + pd.Timedelta("60min")).values
    i = np.searchsorted(fim, b.index.values[s.pos.to_numpy()], side="right") - 1
    return np.where(i >= 0, ten[np.maximum(i, 0)], 0) * s.lado.to_numpy() == 1


def lado_da_abertura(b, s):
    """Close da confirmação do lado a favor da abertura do pregão."""
    abertura = b.groupby("dia").open.transform("first")
    return (_no_sinal(b.close - abertura, s) * s.lado.to_numpy()) > 0


def mms17_acima_mms34(b, s):
    return _no_sinal(np.sign(ind.mms(b.close, 17) - ind.mms(b.close, 34)), s) * s.lado.to_numpy() == 1


def mms72_open_inclinada(b, s):
    return _no_sinal(ind.inclinacao(ind.mms(b.open, 72)), s) * s.lado.to_numpy() == 1


def tendencia_h4(b):
    """Tendência MME 9/21/34 do H4 (blocos 9-13, 13-17, 17-fim) e o instante em que cada barra H4 fecha."""
    h = b.index.hour
    chave = b.index.normalize() + pd.to_timedelta(np.where(h < 13, 9, np.where(h < 17, 13, 17)), unit="h")
    g = b.groupby(chave)
    close = g.close.last()
    fim = (g.apply(lambda x: x.index.max()) + pd.Timedelta("15min")).to_numpy()
    return ind.tendencia(close).to_numpy(), fim


def sinal_bom(b, s, estoc_max=70):
    """Estocástico 14 (suav. 3) abaixo de 70 a favor OU H4 fechado neutro."""
    L = s.lado.to_numpy()
    k = _no_sinal(ind.estocastico(b, 14, 3), s)
    nao_esticado = np.where(L == 1, k, 100 - k) < estoc_max
    ten, fim = tendencia_h4(b)
    fim_conf = b.index.values[s.pos.to_numpy()] + np.timedelta64(15, "m")
    i = np.searchsorted(fim, fim_conf, side="right") - 1
    h4_neutro = (i >= AQUECIMENTO_H4) & (ten[np.maximum(i, 0)] == 0)
    return nao_esticado | h4_neutro
