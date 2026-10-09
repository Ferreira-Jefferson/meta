"""Ciclo 1, dia 2023-07-27 (WIN, "bom", direcional de baixa; robo -R$2).

O robo vendeu o gap as 09:30 (+R$44), comprou `falha_de_queda_1a_hora` as 10:15 (stop em 2 min, -R$46) e depois
os VETOS de venda calaram todos os rompimentos da minima da 1a hora que davam +R$139 a +R$222 cada.

Contem:
  FAZER / NAO_FAZER : 5 + 5 propostas (regras novas e ajustes de FAZER/vetos existentes, como novas funcoes)
  AJUSTES           : como cada proposta entra no robo (substitui/adiciona/remove) -> usado por avalia()
  `python -m regras.c1_2023_07_27`  imprime o resultado no dia (isolada e dentro do robo) e o efeito no conjunto.
Nada de r_*.py nem robo.py e editado: as variantes montam as listas em memoria.
"""
import pandas as pd

H1 = pd.Timedelta(hours=1)
MAXR = 590.0  # risco maximo por contrato (6% de R$2.000)


def _hm(ctx):
    return ctx.t.hour * 60 + ctx.t.minute


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _p1(ctx):
    h = ctx.hoje
    return h[h.index < h.index[0] + H1]


def _vwap(ctx):
    h = ctx.hoje
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


# =====================================================================================================
# 5 maneiras de deixar o dia positivo (A1, A2 = ajustes; A3, A4, A5 = regras novas)
# =====================================================================================================

# ---- A1 (ajuste de FAZER): so comprar suporte que SEGUROU / spring de verdade ----------------------
def a1_falha_de_queda_varredura_real(ctx):
    """AJUSTE de `2022_11_29:falha_de_queda_1a_hora`. A original dispara se a vela perde a minima da 1a hora por QUALQUER
    margem e fecha de volta acima. Aqui a vela das 10:00 perdeu a minima por 40 pts (0,13 ATR15 = ruido) e o robo comprou
    um 'spring' que nao existia; 2 min depois a vela das 10:15 fez -680 pts. Condicao nova: a varredura abaixo da minima da
    1a hora tem de ser >= 0,5 ATR15 (stops de verdade varridos) e a vela ter volume >= a media do dia. Resto igual
    (fecha de volta acima, terco superior, antes das 12h, stop abaixo da varredura, alvo 2R).
    Geral: 'falha' so e falha quando o rompimento foi real; rompimento de 0,1 ATR nao varreu ninguem."""
    h = ctx.hoje
    if len(h) < 5 or _hm(ctx) > 12 * 60: return None
    mn = float(_p1(ctx).low.min())
    u = h.iloc[-1]
    if u.low < mn - 0.5 * ctx.atr15 and u.close > mn and (u.close - u.low) > 0.6 * (u.high - u.low) and u.vol >= h.vol.mean():
        p = float(u.close)
        st = max(float(u.low - 20), p - MAXR)
        return dict(lado="compra", preco=p, stop=st, alvo=p + 2 * (p - st), contratos=1)


def a1b_compra_suporte_que_segurou(ctx):
    """AJUSTE de `2025_06_04:F5 compra suporte na rotacao da manha` (2o comprador do mesmo 10:15; com A1 sozinha o robo
    trocava -R$46 por -R$95 nesta compra). 'Suporte' deveria ser um nivel que SEGUROU. Aqui a vela das 10:00 fez MINIMA NOVA
    do dia (123.225 < 123.265) e a regra comprou assim mesmo (faca caindo, -R$94,9). Condicao nova: a minima da vela
    de entrada nao pode ser a minima do dia ate ali (a vela tem de ter defendido uma minima anterior). Resto igual. Geral."""
    h = ctx.hoje
    if len(h) < 4 or not (10 <= ctx.t.hour < 11): return None
    hi, lo = h.high.max(), h.low.min()
    u = h.iloc[-1]
    if u.low <= h.low.iloc[:-1].min(): return None
    if (hi - lo) < 0.6 * ctx.atrd and u.close <= lo + 0.55 * (hi - lo) and u.close > u.open:
        p = float(u.close)
        return dict(lado="compra", preco=p, stop=p - min(1.5 * ctx.atr15, 590.0), alvo=hi, contratos=1)


# ---- A2 (ajuste de VETO): vende_rompimento_stop_curto so no rompimento RASO (a2 abaixo; a2v/a2b = variantes) --
def a2v_veto_raso_e_sem_volume(ctx):
    """[VARIANTE de A2, nao proposta: conjunto +R$233 contra +R$788 da A2] AJUSTE do veto `2023_08_21:vende_rompimento_stop_curto`. O original veta TODA venda com fechamento abaixo da
    minima da 1a hora - que e exatamente o sinal da FAZER 'rompe minima da 1a hora'. Vetou 94 entradas (+R$4.386 nos 20 dias)
    e aqui bloqueou 14 vendas que davam ate +R$222 enquanto o dia caia 3.400 pts.
    A condicao de mercado que faz o rompimento virar armadilha e a falta de participacao: vela de rompimento com volume
    abaixo da media do dia E o rompimento raso (fecha a menos de 0,5 ATR15 da minima da 1a hora). Rompimento com
    volume ou que ja andou >= 0,5 ATR15 abaixo da minima nao e vetado. Geral (volume e distancia sao relativos)."""
    h = ctx.hoje
    if len(h) < 5: return None
    lo = float(_p1(ctx).low.min())
    u = h.iloc[-1]
    c = float(u.close)
    if c < lo and c > lo - 0.5 * ctx.atr15 and u.vol < h.vol.mean():
        return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def a2b_veto_so_volume(ctx):
    """Variante de A2: veta venda abaixo da minima da 1a hora so se o volume da vela < media do dia (sem a distancia)."""
    h = ctx.hoje
    if len(h) < 5: return None
    lo = float(_p1(ctx).low.min()); u = h.iloc[-1]; c = float(u.close)
    if c < lo and u.vol < h.vol.mean():
        return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def a2_veto_rompimento_raso(ctx):
    """AJUSTE do veto `2023_08_21:vende_rompimento_stop_curto`. O original veta TODA venda com fechamento abaixo da
    minima da 1a hora - que e exatamente o sinal da FAZER 'rompe minima da 1a hora'. Vetou 94 entradas (+R$4.386 nos 20 dias)
    e aqui bloqueou 14 vendas que davam ate +R$222 enquanto o dia caia 3.400 pts.
    Condicao de mercado que faz o rompimento virar armadilha: ele e RASO, o fechamento ainda a menos de 0,5 ATR15 da minima da
    1a hora (o preco so encostou na faixa; o ruido normal de uma vela M15 e maior que isso). Rompimento que ja fechou >= 0,5 ATR15
    abaixo da minima nao e vetado. Geral (so usa ATR relativo). Variantes testadas: A2v (raso E volume < media) e A2b (so volume)."""
    h = ctx.hoje
    if len(h) < 5: return None
    lo = float(_p1(ctx).low.min()); c = float(h.close.iloc[-1])
    if lo - 0.5 * ctx.atr15 < c < lo:
        return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def a3b_veto_faixa_estreita(ctx):
    """Variante de A3: so a faixa do dia < 0,8 ATRd (sem a distancia da abertura)."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 12): return None
    if float(h.high.max() - h.low.min()) < 0.8 * ctx.atrd and h.close.iloc[-1] <= h.close.iloc[-4:].min():
        c = float(h.close.iloc[-1]); a = ctx.atr15
        return dict(lado="venda", stop=c + 1.5 * a, alvo=c - 1.5 * a, contratos=1)


# ---- A6 (extra, NAO proposta): ajuste do veto de venda na rotacao -----------------------------------
def a3_veto_venda_minima_so_em_rotacao(ctx):
    """[A6 - nao proposta: nao melhora o dia sozinha e piora o conjunto] AJUSTE do veto `2025_06_04:N2 vender minima na rotacao da manha`. O docstring original diz 'rotacao da manha (faixa
    estreita)', mas o codigo veta qualquer fechamento na minima de 4 velas entre 10:00 e 12:00, sem checar rotacao. Aqui
    vetou as vendas das 10:30-11:30, em que a faixa do dia ja era ~1 ATR diario (nao e rotacao, e tendencia).
    Condicao nova (a que o docstring descreve): so veta se a faixa do dia ate agora for < 0,6 ATR diario e o preco estiver
    a menos de 1 ATR15 da abertura. Geral."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 12): return None
    faixa = float(h.high.max() - h.low.min())
    if faixa < 0.6 * ctx.atrd and abs(float(h.close.iloc[-1]) - float(h.open.iloc[0])) < ctx.atr15 \
            and h.close.iloc[-1] <= h.close.iloc[-4:].min():
        c = float(h.close.iloc[-1])
        return dict(lado="venda", stop=c + 1.5 * ctx.atr15, alvo=c - 1.5 * ctx.atr15, contratos=1)


# ---- A3 (regra nova): reteste da minima de ontem pelo lado de baixo ----------------------------------
def a3_perda_minima_de_ontem(ctx):
    """FAZER nova (nome mantido por compatibilidade: e o RETESTE da minima de ontem, nao a 1a perda). O dia abriu DENTRO da faixa
    de ontem (abertura acima da minima de ontem) e ja FECHOU abaixo dela ao menos uma vez (suporte perdido). Depois, uma vela
    de queda volta a tocar a minima de ontem por baixo (maxima >= minima de ontem - 0,3 ATR15) e fecha abaixo dela e abaixo da
    VWAP: o suporte virou resistencia. Venda limitada no fechamento, stop 0,5 ATR15 acima da minima de ontem (limitado a 590),
    alvo 2R, entre 11:00 e 16:00. A entrada na 1a perda nao enche (o preco nao volta); o reteste enche porque e o pullback.
    Neste dia: 11:15 fecha 121.690, vende, +R$234 no alvo. Natureza: nivel de ontem (suporte vira resistencia). Geral na ideia;
    perde se o preco recupera o nivel."""
    h = ctx.hoje
    if len(h) < 6 or not (11 * 60 <= _hm(ctx) <= 16 * 60): return None
    mn = float(ctx.diario.low.iloc[-1])
    u = h.iloc[-1]
    c = float(u.close)
    if h.open.iloc[0] > mn and (h.close.iloc[:-1] < mn).any() and u.high >= mn - 0.3 * ctx.atr15 and c < mn             and c < _vwap(ctx) and u.close < u.open:
        st = min(mn + 0.5 * ctx.atr15, c + MAXR)
        return dict(lado="venda", preco=c, stop=st, alvo=c - 2 * (st - c), contratos=1)


# ---- A4 (regra nova): barra de expansao com volume -> continuacao ------------------------------------
def a4_barra_de_expansao_continua(ctx):
    """FAZER nova. Barra de expansao: a vela M15 fechada tem faixa >= 1,6 ATR15 (do ATR ate a vela anterior), volume >= 1,5x a
    media do dia e fecha nos 25% extremos na direcao do movimento, entre 10:00 e 15:00. Entra a favor, limitada no fechamento
    da barra; stop na outra ponta da barra (limitado a 590), alvo 1,5R. As 10:15 a vela fez 685 pts (2,1 ATR15), volume 1,7x,
    fechou na minima: venda a 122.760 -> alvo. Natureza: momentum / expansao de volatilidade. Provavelmente geral (no WIN M15 a
    continuacao domina a reversao); perde em barra de noticia seguida de devolucao."""
    h = ctx.hoje
    if len(h) < 4 or not (10 * 60 <= _hm(ctx) <= 15 * 60): return None
    u = h.iloc[-1]
    rng = float(u.high - u.low)
    atr_ant = float(ctx.m15.iloc[:-1].pipe(lambda d: (d.high - d.low).iloc[-14:].mean()))
    if rng < 1.6 * atr_ant or u.vol < 1.5 * h.vol.iloc[:-1].mean(): return None
    c = float(u.close)
    if c <= u.low + 0.25 * rng:
        st = min(float(u.high), c + MAXR)
        return dict(lado="venda", preco=c, stop=st, alvo=c - 1.5 * (st - c), contratos=1)
    if c >= u.high - 0.25 * rng:
        st = max(float(u.low), c - MAXR)
        return dict(lado="compra", preco=c, stop=st, alvo=c + 1.5 * (c - st), contratos=1)


# ---- A5 (regra nova): quebra de compressao no meio do dia -------------------------------------------
def a5_quebra_de_compressao(ctx):
    """FAZER nova. Compressao: as ultimas 8 velas M15 (2h) tem faixa total < 2,5 ATR15 e a vela atual fecha rompendo a
    maxima/minima dessas 8 anteriores, com o dia ja deslocado >= 1 ATR diario da abertura NA MESMA direcao e preco do lado
    certo da VWAP. Entra a favor, limitada no fechamento, stop na outra ponta da faixa (limitado a 590), alvo 2R, antes das
    17:00. Neste dia: 12:00-14:45 virou faixa de ~300 pts e a quebra das 15:00 (fecha 121.245) levou 1.000 pts no mesmo
    sentido. Natureza: compressao -> expansao com tendencia do dia. Geral na ideia; o filtro de deslocamento e o que a segura."""
    h = ctx.hoje
    if len(h) < 12 or not (11 * 60 <= _hm(ctx) <= 17 * 60): return None
    ant = h.iloc[-9:-1]
    hi, lo = float(ant.high.max()), float(ant.low.min())
    if hi - lo >= 2.5 * ctx.atr15: return None
    u = h.iloc[-1]
    c = float(u.close)
    ab = float(h.open.iloc[0])
    v = _vwap(ctx)
    if c < lo and ab - c >= ctx.atrd and c < v:
        st = min(hi, c + MAXR)
        return dict(lado="venda", preco=c, stop=st, alvo=c - 2 * (st - c), contratos=1)
    if c > hi and c - ab >= ctx.atrd and c > v:
        st = max(lo, c - MAXR)
        return dict(lado="compra", preco=c, stop=st, alvo=c + 2 * (c - st), contratos=1)


# ---- A5b (ajuste de VETO): vender_gap_de_alta so com o que o docstring diz ---------------------------
def a5b_veto_vender_gap_de_alta_fiel(ctx):
    """AJUSTE do veto `2022_11_29:vender_gap_de_alta`. O docstring diz 'nao vender gap de alta se a 1a vela fechou acima da
    abertura', mas o codigo veta todo gap > 0,1 ATRd. Aqui a 1a vela fechou ABAIXO da abertura (123.480 < 123.655): o gap ja
    estava sendo devolvido e o veto adiou a venda de 09:15 para 09:30. Condicao fiel ao docstring. Geral."""
    h = ctx.hoje
    if len(h) != 1 or ctx.ops_hoje: return None
    gap = float(h.open.iloc[0] - ctx.diario.close.iloc[-1])
    if gap > 0.1 * ctx.atrd and h.close.iloc[-1] > h.open.iloc[0]:
        p = float(h.close.iloc[-1])
        return dict(lado="venda", preco=p, stop=p + 400, alvo=float(ctx.diario.close.iloc[-1]), contratos=1)


# =====================================================================================================
# 5 coisas a NAO fazer (cada uma da R$ < 0 neste dia; docstring = condicao que vira veto)
# =====================================================================================================
def n1_compra_spring_raso(ctx):
    """NAO fazer: comprar a 'falha de queda' quando a varredura abaixo da minima da 1a hora for rasa (< 0,5 ATR15).
    Armadilha: 40 pts abaixo da minima nao varrem stop nenhum; e a faixa de abertura sendo testada antes de ceder.
    Dia: comprou 123.425, stop 123.205 em 2 min, -R$46. Veto: nao comprar depois do 'spring' raso da 1a hora."""
    h = ctx.hoje
    if len(h) < 5 or _hm(ctx) > 12 * 60: return None
    mn = float(_p1(ctx).low.min())
    u = h.iloc[-1]
    if mn - 0.5 * ctx.atr15 <= u.low < mn and u.close > mn:
        p = float(u.close)
        st = max(float(u.low - 20), p - MAXR)
        return dict(lado="compra", preco=p, stop=st, alvo=p + 2 * (p - st), contratos=1)


def n2_compra_recuo_em_dia_abaixo_da_vwap(ctx):
    """NAO fazer: comprar vela de alta que fecha acima da anterior quando o dia ja esta mais de 1 ATR15 abaixo da abertura,
    abaixo da VWAP e a EMA21 M15 cai. Armadilha: repique dentro de tendencia de baixa (no WIN M15 a continuacao domina).
    Veto de compra: dia sob a abertura e sob a VWAP com media caindo. Stop 1 ATR15, alvo 1 ATR15."""
    h = ctx.hoje
    if len(h) < 8 or not (10 * 60 + 30 <= _hm(ctx) < 17 * 60): return None
    e = _ema(ctx.m15.close, 21)
    u = h.iloc[-1]
    c = float(u.close)
    if h.open.iloc[0] - c > ctx.atr15 and c < _vwap(ctx) and e.iloc[-1] < e.iloc[-4] and u.close > u.open \
            and u.close > h.close.iloc[-2]:
        a = ctx.atr15
        return dict(lado="compra", preco=c, stop=c - a, alvo=c + a, contratos=1)


def n3_compra_lateral_do_almoco(ctx):
    """NAO fazer: comprar o fundo da lateral do almoco (12:00-14:30) quando o dia ja devolveu o gap e esta abaixo da
    minima de ontem. Armadilha: a lateral com volume secando (< 0,7x media) em dia de baixa e pausa, nao reversao; a quebra vem
    para baixo. Veto de compra: faixa estreita + volume seco + preco sob a minima de ontem. Stop 1 ATR15, alvo 1 ATR15."""
    h = ctx.hoje
    if len(h) < 12 or not (12 * 60 <= _hm(ctx) <= 14 * 60 + 30): return None
    u = h.iloc[-1]
    c = float(u.close)
    ant = h.iloc[-7:]
    if c < float(ctx.diario.low.iloc[-1]) and ant.vol.mean() < 0.7 * h.vol.mean() and c <= float(ant.low.min()) + 0.3 * ctx.atr15:
        a = ctx.atr15
        return dict(lado="compra", preco=c, stop=c - a, alvo=c + a, contratos=1)


def n4_compra_tres_altas_sob_vwap(ctx):
    """NAO fazer: comprar depois de 3 velas de alta consecutivas quando o preco segue abaixo da VWAP e a 1a vela do dia ja foi
    superada para baixo, depois das 10:30. Armadilha: 3 altas seguidas sob a VWAP em dia vendedor e repique de cobertura, nao
    reversao; o preco volta a VWAP/minima. Dia: compra 12:15, stop de 1 ATR15 (-R$75,8). Veto de compra: sequencia de altas
    sob a VWAP com o dia abaixo da abertura. Stop 1 ATR15, alvo 1,5 ATR15."""
    h = ctx.hoje
    if len(h) < 8 or _hm(ctx) < 10 * 60 + 30: return None
    u = h.iloc[-3:]
    c = float(h.close.iloc[-1])
    if (u.close > u.open).all() and c < _vwap(ctx) and c < float(h.open.iloc[0]):
        a = ctx.atr15
        return dict(lado="compra", preco=c, stop=c - a, alvo=c + 1.5 * a, contratos=1)


def n5_compra_vela_de_pavio_apos_15h(ctx):
    """NAO fazer: comprar vela com pavio inferior grande (> 50% da faixa) depois das 15:00 em dia que ja caiu mais de 1 ATR
    diario da abertura. Armadilha: o ultimo ciclo do dia continua a tendencia (queda de 1.000 pts nas 2h finais); pavio
    de fim de dia nao e reversao. Veto de compra: pavio inferior depois das 15h com dia abaixo da abertura - 1 ATRd.
    Stop 1 ATR15, alvo 1,5 ATR15."""
    h = ctx.hoje
    if len(h) < 12 or not (15 * 60 <= _hm(ctx) <= 17 * 60 + 30): return None
    u = h.iloc[-1]
    c = float(u.close)
    rng = float(u.high - u.low)
    if rng > 0 and (min(u.open, u.close) - u.low) > 0.5 * rng and h.open.iloc[0] - c > ctx.atrd:
        a = ctx.atr15
        return dict(lado="compra", preco=c, stop=c - a, alvo=c + 1.5 * a, contratos=1)


FAZER = [
    ("A1 ajuste: falha de queda com varredura real", a1_falha_de_queda_varredura_real, None),
    ("A2 ajuste de veto: so veta rompimento raso", a2_veto_rompimento_raso, None),
    ("A3 reteste da minima de ontem (venda)", a3_perda_minima_de_ontem, None),
    ("A4 barra de expansao continua", a4_barra_de_expansao_continua, None),
    ("A5 quebra de compressao com tendencia", a5_quebra_de_compressao, None),
]
NAO_FAZER = [
    ("N1 comprar spring raso", n1_compra_spring_raso, None),
    ("N2 comprar recuo sob VWAP em baixa", n2_compra_recuo_em_dia_abaixo_da_vwap, None),
    ("N3 comprar lateral do almoco sob minima de ontem", n3_compra_lateral_do_almoco, None),
    ("N4 comprar 3 altas seguidas sob a VWAP", n4_compra_tres_altas_sob_vwap, None),
    ("N5 comprar pavio apos 15h em dia de baixa", n5_compra_vela_de_pavio_apos_15h, None),
]

# ---- como cada proposta entra no robo -----------------------------------------------------------------
# chaves: sub_fazer / sub_veto {nome_original: (funcao, gerir)}, add_fazer / add_veto [(nome, funcao, gerir)]
V_STOP_CURTO = "2023_08_21:vende_rompimento_stop_curto"
V_ROTACAO = "2025_06_04:N2 vender minima na rotacao da manha"
V_GAP = "2022_11_29:vender_gap_de_alta"
F_FALHA = "2022_11_29:falha_de_queda_1a_hora"
F_F5 = "2025_06_04:F5 compra suporte na rotacao da manha"
AJUSTES = {
    "A1": dict(sub_fazer={F_FALHA: (a1_falha_de_queda_varredura_real, None), F_F5: (a1b_compra_suporte_que_segurou, None)}),
    "A2b": dict(sub_veto={V_STOP_CURTO: (a2b_veto_so_volume, None)}),
    "A2v": dict(sub_veto={V_STOP_CURTO: (a2v_veto_raso_e_sem_volume, None)}),
    "A3b": dict(sub_veto={V_ROTACAO: (a3b_veto_faixa_estreita, None)}),
    "A2": dict(sub_veto={V_STOP_CURTO: (a2_veto_rompimento_raso, None)}),
    "A3": dict(add_fazer=[("c1:A3 reteste_minima_de_ontem", a3_perda_minima_de_ontem, None)]),
    "A6": dict(sub_veto={V_ROTACAO: (a3_veto_venda_minima_so_em_rotacao, None)}),
    "A3f": dict(add_fazer_front=[("c1:A3 reteste_minima_de_ontem", a3_perda_minima_de_ontem, None)]),
    "A4f": dict(add_fazer_front=[("c1:A4 barra_de_expansao", a4_barra_de_expansao_continua, None)]),
    "A5f": dict(add_fazer_front=[("c1:A5 quebra_de_compressao", a5_quebra_de_compressao, None)]),
    "A4": dict(add_fazer=[("c1:A4 barra_de_expansao", a4_barra_de_expansao_continua, None)]),
    "A5": dict(add_fazer=[("c1:A5 quebra_de_compressao", a5_quebra_de_compressao, None)]),
    "A5b": dict(sub_veto={V_GAP: (a5b_veto_vender_gap_de_alta_fiel, None)}),
    "N1": dict(add_veto=[("c1:N1 spring_raso", n1_compra_spring_raso, None)]),
    "N2": dict(add_veto=[("c1:N2 recuo_sob_vwap", n2_compra_recuo_em_dia_abaixo_da_vwap, None)]),
    "N3": dict(add_veto=[("c1:N3 lateral_almoco", n3_compra_lateral_do_almoco, None)]),
    "N4": dict(add_veto=[("c1:N4 tres_altas_sob_vwap", n4_compra_tres_altas_sob_vwap, None)]),
    "N5": dict(add_veto=[("c1:N5 pavio_apos_15h", n5_compra_vela_de_pavio_apos_15h, None)]),
    
}
# A1 e N1 fazem o mesmo servico de lados opostos (A1 corrige a FAZER; N1 veta). Se A1 ja esta ligada, N1 nao muda nada.


def monta(fz, nf, chaves):
    """Aplica as propostas `chaves` as listas do robo e devolve (fz, nf) novas."""
    fz, nf = list(fz), list(nf)
    for k in chaves:
        a = AJUSTES[k]
        for orig, (fn, g) in a.get("sub_fazer", {}).items():
            fz = [(n, fn, g) if n == orig else (n, r, gg) for n, r, gg in fz]
        for orig, (fn, g) in a.get("sub_veto", {}).items():
            nf = [(n, fn, g) if n == orig else (n, r, gg) for n, r, gg in nf]
        fz = list(a.get("add_fazer_front", [])) + fz + a.get("add_fazer", [])
        nf += a.get("add_veto", [])
    return fz, nf


# ---- avaliacao ---------------------------------------------------------------------------------------
def _dias_usados():
    import json
    from pathlib import Path
    j = json.load(open(Path(__file__).resolve().parents[1] / "dias_usados.json"))
    return list(j["ciclo0"]["dias"]) + [x["dia"] for x in j["ciclo1"]["dias"]]


def _um(args):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import robo
    from regras import c1_2023_07_27 as c1
    chaves, dia = args
    fz, nf = robo.carrega_regras()
    fz, nf = c1.monta(fz, nf, chaves)
    tr, log, contra = robo.roda_robo(dia, fz, nf)
    ok = [x for x in tr if x.t_ent]
    return chaves, dia, round(sum(x.brl for x in ok), 2), len(ok), [(x.fonte[:45], x.lado, str(x.t_ent.time()), x.motivo, round(x.brl, 1)) for x in ok]


def avalia(configs, dias=None, workers=10):
    """configs: lista de tuplas de chaves de AJUSTES. Devolve {chaves: {dia: (brl, ops, trades)}} (conjunto de dias usados)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    dias = dias or _dias_usados()
    res = {tuple(c): {} for c in configs}
    with ProcessPoolExecutor(workers) as ex:
        fut = [ex.submit(_um, (tuple(c), d)) for c in configs for d in dias]
        for f in as_completed(fut):
            ch, d, brl, ops, tr = f.result()
            res[ch][d] = (brl, ops, tr)
    return res


def isolada(dia, regra, gerir=None):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    return base.resumo(base.simula_dia(dia, regra, gerir, max_ops=3))


DIA = "2023-07-27"

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = isolada(DIA, r, g)
            print(f"{grupo:9s} {nome:52s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
            for x in res["lista"]:
                print("     ", x["lado"], x["sinal"], x["ent"], x["preco"], "stop", x["stop"], "->", x["sai"], x["preco_sai"], x["motivo"], x["brl"])
    base_c = [()] + [(k,) for k in AJUSTES]
    res = avalia(base_c)
    b = res[()]
    print("\nconfig | R$ no dia | R$ conjunto (30 dias) | dias que pioraram | dias que melhoraram")
    for c, r in res.items():
        tot = sum(v[0] for v in r.values())
        pi = [d for d in r if r[d][0] < b[d][0] - 0.005]
        me = [d for d in r if r[d][0] > b[d][0] + 0.005]
        print(f"{'+'.join(c) or 'BASE':14s} dia {r[DIA][0]:8.2f}  conj {tot:9.2f}  piorou {len(pi)} {pi}  melhorou {len(me)}", flush=True)
