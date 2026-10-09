"""Regras do pregao 2025-08-01 (WIN M15). FAZER = 5 maneiras de ganhar, NAO_FAZER = 5 armadilhas.
Todas so usam o passado ate o fechamento da vela de decisao (ctx). Stop <= 580 pts (risco < 6% do caixa)."""


def HH(t):
    return t.hour + t.minute / 60.0


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3.0
    return float((tp * h.vol).sum() / h.vol.sum())


def _lim(entrada, stop, lado, maximo=580.0):
    """Limita o stop a `maximo` pts da entrada."""
    if lado == "compra":
        return max(stop, entrada - maximo)
    return min(stop, entrada + maximo)


# ---------------------------------------------------------------- FAZER
def f1_falha_minima_ontem(ctx):
    """FAZER 1 - reversao em falha da minima de ontem.
    Logica: o preco fura a minima do pregao anterior e a vela fecha de volta acima dela, com corpo de alta
    (armadilha de vendedores); compra no fechamento, stop 20 pts abaixo da minima da falha, alvo 1,5 ATR15.
    Condicao: antes das 11h, uma unica vez no dia.
    Geral: provavelmente geral (falso rompimento de nivel de ontem), mas com n baixo.
    Resultado no dia: ver saida do modulo."""
    h = ctx.hoje
    if ctx.ops_hoje or HH(ctx.t) > 11 or len(h) < 2:
        return None
    ml = float(ctx.diario.low.iloc[-1])
    if h.low.iloc[-1] < ml and h.close.iloc[-1] > ml and h.close.iloc[-1] > h.open.iloc[-1]:
        e = float(h.close.iloc[-1])
        return dict(lado="compra", stop=_lim(e, float(h.low.min()) - 20, "compra"), alvo=e + 1.5 * ctx.atr15, preco=e)


def f2_gap_baixa_preenche(ctx):
    """FAZER 2 - gap de baixa moderado tende a ser preenchido.
    Logica: abertura abaixo do fechamento de ontem entre 0,3 e 0,8 ATR diario; no fechamento da 1a vela
    compra mirando o fechamento de ontem, stop 500 pts.
    Condicao: gap de baixa moderado (gap grande costuma continuar).
    Geral: provavelmente geral como fundamento, mas WIN M15 e mais de continuacao: precisa de outros dias.
    Resultado no dia: ver saida."""
    h = ctx.hoje
    if len(h) != 1:
        return None
    gap = float(h.open.iloc[0]) - float(ctx.diario.close.iloc[-1])
    if -0.8 * ctx.atrd < gap < -0.3 * ctx.atrd:
        e = float(h.close.iloc[-1])
        return dict(lado="compra", stop=e - 500, alvo=float(ctx.diario.close.iloc[-1]), preco=e)


def f3_perde_vwap(ctx):
    """FAZER 3 - perda do VWAP do dia depois de subida forte de abertura.
    Logica: depois das 10:30, com a maxima do dia >= 0,9 ATRd acima da abertura, a vela fecha abaixo do VWAP
    acumulado e a anterior estava acima: vende, alvo = abertura do dia, stop 580 pts.
    Condicao: impulso de abertura que perde o preco medio = compradores exaustos.
    Geral: fundamento geral (VWAP), parametros ajustados ao dia.
    Resultado no dia: ver saida."""
    h = ctx.hoje
    if ctx.ops_hoje or HH(ctx.t) < 10.5 or len(h) < 4:
        return None
    if h.high.max() - h.open.iloc[0] < 0.9 * ctx.atrd:
        return None
    v, vp = _vwap(h), _vwap(h.iloc[:-1])
    if h.close.iloc[-1] < v and h.close.iloc[-2] >= vp:
        e = float(h.close.iloc[-1])
        return dict(lado="venda", stop=e + 580, alvo=float(h.open.iloc[0]), preco=e)


def f4_quebra_faixa_lateral(ctx):
    """FAZER 4 - quebra para baixo da faixa lateral do meio do dia.
    Logica: entre 13:30 e 15:30, a vela fecha abaixo da minima das 8 velas anteriores (faixa <= 2,5 ATR15)
    com volume menor que a media delas: vende, stop 400 acima, alvo -500 pts.
    Condicao: lateralizacao longa e quebra do suporte.
    Geral: rompimento de consolidacao e geral; o alvo curto foi escolhido vendo o dia (ajustada em parte).
    Resultado no dia: ver saida."""
    h = ctx.hoje
    if ctx.ops_hoje or not (13.5 <= HH(ctx.t) <= 15.5) or len(h) < 10:
        return None
    p = h.iloc[-9:-1]
    if (p.high.max() - p.low.min()) > 2.5 * ctx.atr15:
        return None
    if h.close.iloc[-1] < p.low.min() and h.vol.iloc[-1] < p.vol.mean():
        e = float(h.close.iloc[-1])
        return dict(lado="venda", stop=e + 400, alvo=e - 500, preco=e)


def f5_falha_rompimento_1a_hora(ctx):
    """FAZER 5 - falha do rompimento da maxima da 1a hora (reversao em falha de topo).
    Logica: o preco rompe acima da maxima de 9-10h e, entre 10:15 e 11h, uma vela fecha de volta abaixo
    dessa maxima sem fazer nova maxima: vende; stop 580, alvo no meio da faixa do dia.
    Condicao: rompimento sem seguimento.
    Geral: fundamento geral (falha de rompimento), parametros ajustados ao dia.
    Resultado no dia: ver saida."""
    h = ctx.hoje
    if ctx.ops_hoje or not (10.25 <= HH(ctx.t) <= 11) or len(h) < 5:
        return None
    pri = h.iloc[:4]
    if h.high.iloc[4:].max() > pri.high.max() and h.close.iloc[-1] < pri.high.max() and h.high.iloc[-1] < h.high.max():
        e = float(h.close.iloc[-1])
        return dict(lado="venda", stop=e + 580, alvo=(h.high.max() + pri.low.min()) / 2, preco=e)


FAZER = [("F1 falha da minima de ontem (compra)", f1_falha_minima_ontem, None),
         ("F2 gap de baixa preenche (compra)", f2_gap_baixa_preenche, None),
         ("F3 perde VWAP apos alta de abertura (venda)", f3_perde_vwap, None),
         ("F4 quebra da faixa lateral do meio do dia (venda)", f4_quebra_faixa_lateral, None),
         ("F5 falha do rompimento da 1a hora (venda)", f5_falha_rompimento_1a_hora, None)]


# ---------------------------------------------------------------- NAO FAZER
def n1_compra_rompimento_1a_hora(ctx):
    """NAO FAZER 1 - comprar o rompimento da maxima da 1a hora.
    Logica: entre 10h e 11h, vela fecha acima da maxima de 9-10h: compra, stop 580, alvo 1,5 ATR15.
    Armadilha: dia que ja subiu > 1 ATRd desde a abertura (rompimento esticado) e de rotacao: o rompimento
    vira topo. Veto: nao comprar rompimento com alta desde a abertura perto de 1 ATR diario.
    Resultado: ver saida."""
    h = ctx.hoje
    if ctx.ops_hoje or HH(ctx.t) < 10 or HH(ctx.t) > 11 or len(h) < 4:
        return None
    pri = h.iloc[:4]
    if h.close.iloc[-1] > pri.high.max():
        e = float(h.close.iloc[-1])
        return dict(lado="compra", stop=e - 580, alvo=e + 1.5 * ctx.atr15, preco=e)


def n2_vende_gap_de_baixa(ctx):
    """NAO FAZER 2 - vender a continuacao do gap de baixa na abertura.
    Logica: gap de baixa > 0,3 ATRd, 1a vela fecha vermelha: vende a favor do gap, stop 580, alvo 1,5 ATR15.
    Armadilha: gap de baixa moderado + varredura de minima de ontem (armadilha de vendedores) reverte.
    Veto: nao vender no fechamento da 1a vela com o preco colado na minima de ontem.
    Resultado: ver saida."""
    h = ctx.hoje
    if len(h) != 1:
        return None
    gap = float(h.open.iloc[0]) - float(ctx.diario.close.iloc[-1])
    if gap < -0.3 * ctx.atrd and h.close.iloc[-1] < h.open.iloc[0]:
        e = float(h.close.iloc[-1])
        return dict(lado="venda", stop=e + 580, alvo=e - 1.5 * ctx.atr15, preco=e)


def n3_compra_queda_no_meio_do_dia(ctx):
    """NAO FAZER 3 - comprar a queda no meio do dia.
    Logica: entre 11:30 e 14h, vela vermelha (corpo > 0,2 ATR15) fecha abaixo do VWAP e da media das 4
    anteriores: compra a queda, stop 580, alvo 1 ATR15.
    Armadilha: tarde de volume secando e preco abaixo do VWAP: a queda e continuacao, nao exagero.
    Veto: nao comprar queda com preco abaixo do VWAP do dia.
    Resultado: ver saida."""
    h = ctx.hoje
    if not (11.5 <= HH(ctx.t) <= 14) or len(h) < 6:
        return None
    if h.close.iloc[-1] < _vwap(h) and (h.open.iloc[-1] - h.close.iloc[-1]) > 0.2 * ctx.atr15 \
            and h.close.iloc[-1] < h.close.iloc[-5:-1].mean():
        e = float(h.close.iloc[-1])
        return dict(lado="compra", stop=e - 580, alvo=e + 1.0 * ctx.atr15, preco=e)


def n4_vende_minima_tarde(ctx):
    """NAO FAZER 4 - vender a minima nova depois das 15h45.
    Logica: entre 15:45 e 17:30, vela fecha abaixo da minima das 8 velas anteriores (quebra de suporte
    de tarde): vende, stop 300, alvo -1 ATR15.
    Armadilha: fim de pregao com volume baixo e faixa estreita: a quebra nao tem seguimento e volta.
    Veto: nao operar quebra depois das 15h45 com volume baixo.
    Resultado: ver saida."""
    h = ctx.hoje
    if HH(ctx.t) < 15.75 or HH(ctx.t) > 17.5 or len(h) < 6:
        return None
    if h.close.iloc[-1] < h.low.iloc[-9:-1].min():
        e = float(h.close.iloc[-1])
        return dict(lado="venda", stop=e + 300, alvo=e - 1.0 * ctx.atr15, preco=e)


def n5_compra_recuo_em_alta_da_manha(ctx):
    """NAO FAZER 5 - comprar o recuo a media depois da alta da manha (pullback em tendencia).
    Logica: entre 11h e 14h, com o dia >= 0,9 ATRd acima da abertura no maximo, vela vermelha fecha a menos
    de 0,5 ATR15 da media de 20 velas M15: compra o recuo, stop 580, alvo = maxima do dia.
    Armadilha: a alta foi impulso de abertura exaurido, a tarde e de rotacao para baixo.
    Veto: nao comprar pullback quando a alta toda foi feita antes das 10:15 e o volume decai.
    Resultado: ver saida."""
    h = ctx.hoje
    if ctx.ops_hoje or not (11 <= HH(ctx.t) <= 14) or len(h) < 8:
        return None
    if h.high.max() - h.open.iloc[0] < 0.9 * ctx.atrd:
        return None
    m20 = float(ctx.m15.close.iloc[-20:].mean())
    if abs(h.close.iloc[-1] - m20) < 0.5 * ctx.atr15 and h.close.iloc[-1] < h.close.iloc[-2]:
        e = float(h.close.iloc[-1])
        return dict(lado="compra", stop=e - 580, alvo=float(h.high.max()), preco=e)


NAO_FAZER = [("N1 comprar rompimento da 1a hora", n1_compra_rompimento_1a_hora, None),
             ("N2 vender continuacao do gap de baixa", n2_vende_gap_de_baixa, None),
             ("N3 comprar queda no meio do dia", n3_compra_queda_no_meio_do_dia, None),
             ("N4 vender minima nova depois das 15h45", n4_vende_minima_tarde, None),
             ("N5 comprar recuo a media apos alta da manha", n5_compra_recuo_em_alta_da_manha, None)]

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia("2025-08-01", r, g))
            print(f"{grupo:9s} {nome:52s} R$ {res['brl']:9.2f}  ops {res['ops']}")
            for x in res["lista"]:
                print("     ", x)
