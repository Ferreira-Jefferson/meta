"""Estrategia de perguntas (WIN M15). Cada pergunta e uma funcao nomeada pela pergunta, devolvendo array booleano
alinhado as barras M15 (True = SIM) para compra (lado=+1); venda = espelho via lado=-1. So velas fechadas.
Nao sabe de que robo veio cada pergunta: soma respostas.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(r"C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\topos_fundos")))
import dados, escada, filtros, indicadores as ind, operacao, stop  # noqa

GAP_MIN_PTS, GAP_ATR_MAX, ANDOU_ATR_MIN, FAIXA_N, FAIXA_ATR_MAX = 5, 1.0, 0.5, 20, 1.5


def atr_diario(periodo):
    """ATR diario = media simples de 14 TR diarios ate D-1 (montado do M1; usa o arquivo inteiro p/ aquecer)."""
    m1 = dados.le_win(dados.RAIZ / dados.PERIODOS[periodo][0])
    d = m1.resample("1D").agg(dict(high="max", low="min", close="last")).dropna()
    pc = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(14).mean().shift(1)  # indexado por dia; valor em D = ate D-1


def _S(b, lado):
    return pd.DataFrame(dict(pos=np.arange(len(b)), lado=lado))


# ---- perguntas de contexto (True = respondida como esperado) ----
def tendencia_h1_esta_contra_ou_indefinida_NAO(b, lado): return filtros.h1_a_favor(b, _S(b, lado))
def preco_esta_do_lado_contrario_da_abertura_NAO(b, lado): return filtros.lado_da_abertura(b, _S(b, lado))
def medias_rapida_e_lenta_contra_ou_empatadas_NAO(b, lado): return filtros.mms17_acima_mms34(b, _S(b, lado))
def media_longa_inclinada_contra_ou_plana_NAO(b, lado): return filtros.mms72_open_inclinada(b, _S(b, lado))
def preco_esticado_NAO_ou_H4_neutro_SIM(b, lado): return filtros.sinal_bom(b, _S(b, lado))
def gap_de_abertura_maior_que_1_atr_NAO(b, atrd):
    pc = b.close.groupby(b.dia).last().shift(1).reindex(b.dia).to_numpy()
    gap = np.abs(b.groupby("dia").open.transform("first").to_numpy() - pc)
    return (gap / atrd.to_numpy()) < GAP_ATR_MAX
def pregao_ja_andou_meio_atr_SIM(b, atrd):
    amp = b.high.groupby(b.dia).cummax() - b.low.groupby(b.dia).cummin()
    return ((amp / atrd) >= ANDOU_ATR_MIN).to_numpy()
def contexto_virou_H1_SIM(b, lado): return ~filtros.h1_a_favor(b, _S(b, lado))  # X1


# ---- gatilhos ----
def estrutura_confirmou_virada_a_favor_agora(b, dias):
    """T1: dict lado -> array bool por barra (pos global)."""
    out = {1: np.zeros(len(b), bool), -1: np.zeros(len(b), bool)}
    for D in dias:
        for i, p in enumerate(D["piv"]):
            lado, est = escada.estagio(D["piv"], i)
            if est is not None and est >= 1: out[lado][D["ini"] + p[3]] = True
    return out

def fechou_fora_da_faixa_20_velas_a_favor_agora(b, atrd):
    """T2 (faixa de 20 velas anteriores <= 1,5 ATR diario)."""
    hh = b.high.rolling(FAIXA_N).max().shift(1); ll = b.low.rolling(FAIXA_N).min().shift(1)
    ok = ((hh - ll) <= FAIXA_ATR_MAX * atrd).to_numpy()
    return {1: ((b.close > hh).to_numpy() & ok), -1: ((b.close < ll).to_numpy() & ok)}

def primeira_vela_fechou_contra_o_gap_agora(b):
    """T3: 1a vela do dia fechou contra o gap (gap>=5 pts); direcao = a do fechamento."""
    prim = (b.dia != b.dia.shift(1)).to_numpy()
    gap = (b.open - b.close.shift(1)).to_numpy()
    cor = (b.close - b.open).to_numpy()
    return {1: prim & (gap <= -GAP_MIN_PTS) & (cor > 0), -1: prim & (gap >= GAP_MIN_PTS) & (cor < 0)}

def medias_9_21_34_alinharam_a_favor_agora(b):
    """T4: MME9>21>34 a favor nesta vela e nao na anterior."""
    r, m, l = ind.mme(b.close, 9), ind.mme(b.close, 21), ind.mme(b.close, 34)
    up, dn = (r > m) & (m > l), (r < m) & (m < l)
    return {1: (up & ~up.shift(1, fill_value=False)).to_numpy(), -1: (dn & ~dn.shift(1, fill_value=False)).to_numpy()}


def preparar(periodo):
    b = dados.m15(periodo)
    b["mme38"] = ind.mme(b.close, stop.MME_APERTO)
    atrd = pd.Series(atr_diario(periodo).reindex(b.dia).to_numpy(), index=b.index)
    ctx, h1c = {}, {}
    for lado in (1, -1):
        L = np.full(len(b), lado)
        q = np.vstack([tendencia_h1_esta_contra_ou_indefinida_NAO(b, L), preco_esta_do_lado_contrario_da_abertura_NAO(b, L),
                       medias_rapida_e_lenta_contra_ou_empatadas_NAO(b, L), media_longa_inclinada_contra_ou_plana_NAO(b, L),
                       preco_esticado_NAO_ou_H4_neutro_SIM(b, L), gap_de_abertura_maior_que_1_atr_NAO(b, atrd),
                       pregao_ja_andou_meio_atr_SIM(b, atrd)]).astype(int)
        ctx[lado] = q.sum(0)
        h1c[lado] = contexto_virou_H1_SIM(b, L).astype(float)
    b["h1virou_b"], b["h1virou_s"] = h1c[1], h1c[-1]
    dias = escada.pregoes(b)
    gat = {"T1": estrutura_confirmou_virada_a_favor_agora(b, dias), "T2": fechou_fora_da_faixa_20_velas_a_favor_agora(b, atrd),
           "T3": primeira_vela_fechou_contra_o_gap_agora(b), "T4": medias_9_21_34_alinharam_a_favor_agora(b)}
    return dict(b=b, dias=dias, ctx=ctx, gat=gat, n=len(b))


def sinais(P, k, usar=("T1", "T2", "T3", "T4")):
    dias = P["dias"]
    disp = {}
    for lado in (1, -1):
        g = np.zeros(P["n"], bool)
        for t in usar: g |= P["gat"][t][lado]
        disp[lado] = g & (P["ctx"][lado] >= k)
    rows = []
    for seg, D in enumerate(dias):
        n = len(D["open"])
        for t in range(n - 1):
            pos = D["ini"] + t
            cb, cs = disp[1][pos], disp[-1][pos]
            if cb == cs: continue  # nenhum, ou compra e venda juntas
            lado = 1 if cb else -1
            marc = "".join(x for x in ("T1", "T2", "T3", "T4") if P["gat"][x][lado][pos])
            tipo = "F" if lado == 1 else "T"
            ult = [p for p in D["piv"] if p[0] == tipo and p[3] <= t]
            if ult: st = ult[-1][2]
            elif t >= 3 and D["atr"][t] == D["atr"][t]:
                st = (D["low"][t-3:t+1].min() - D["atr"][t]) if lado == 1 else (D["high"][t-3:t+1].max() + D["atr"][t])
            else: continue
            rows.append(dict(seg=seg, t0=t + 1, pos=pos, lado=lado, stop=st, gat=marc, score=int(P["ctx"][lado][pos])))
    return pd.DataFrame(rows)


def mover_x1(stop_, t, p, D):
    s = stop.estrutura(stop_, t, p, D)
    if D["h1virou_b" if p.lado == 1 else "h1virou_s"][t] == 1:  # X1: stop vai para o fechamento da vela
        s = stop.melhor(s, D["close"][t], p.lado)
    return s


def rodar(P, k, x1=False, usar=("T1", "T2", "T3", "T4")):
    s = sinais(P, k, usar)
    if s.empty: return pd.DataFrame(), s
    tr = operacao.operar(s, P["dias"], stop.inicial_v41, mover_x1 if x1 else stop.estrutura)
    if len(tr): tr = tr.merge(s[["pos", "lado", "gat", "score"]], on=["pos", "lado"], how="left")
    return tr, s


def painel(tr, b):
    """ops, total, pior queda, fator recuperacao, fator lucro, acerto, pior mes, %meses +, Sharpe diario."""
    dias_all = pd.Series(0.0, index=pd.Index(b.dia.unique()))
    if len(tr):
        x = tr.pts.to_numpy(); eq = np.cumsum(x); dd = (np.maximum.accumulate(eq) - eq).max()
        d = tr.groupby("dia").pts.sum(); dias_all.loc[d.index] = d.values
        g, pd_ = x[x > 0].sum(), -x[x < 0].sum()
        m = dias_all.groupby(dias_all.index.to_period("M")).sum()
        sh = dias_all.mean() / dias_all.std() * np.sqrt(252) if dias_all.std() > 0 else np.nan
        return dict(ops=len(x), total=x.sum(), dd=dd, recup=x.sum() / dd if dd else np.nan, fl=g / pd_ if pd_ else np.nan,
                    acerto=(x > 0).mean(), pior_mes=m.min(), meses_pos=(m > 0).mean(), sharpe=sh, reais=x.sum() * 0.2)
    return dict(ops=0, total=0, dd=0, recup=np.nan, fl=np.nan, acerto=np.nan, pior_mes=0, meses_pos=np.nan, sharpe=np.nan, reais=0)
