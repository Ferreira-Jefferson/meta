"""Ciclo 2, dia 2024-04-22 (WIN, "ruim"/rotacao, ef 0,003; v1 +R$82, v2 -R$4).

Causa: o A2 (veto so no rompimento raso) liberou a F1 `2025_06_04:F1 rompe minima da 1a hora (venda)` as 11:00. A vela das 10:45
(volume 1,03M, o maior do dia) ja tinha feito 126.145 e a das 11:00 fez nova minima do dia (126.125) mas FECHOU em 126.370, a 92% do
range de 265 pts (pavio inferior de 245 pts: rejeicao). A F1 vendeu a vela de rejeicao no fim de uma queda de 945 pts (3,4 ATR15) e
foi stopada as 11:17 (-R$86). O preco voltou a 127.600 as 14:00.

Contem:
  FAZER / NAO_FAZER : 5 + 5 propostas (todas regras NOVAS, nenhum r_*.py editado)
  AJUSTES           : como cada proposta entra no robo v2 (add_fazer no FIM / add_veto)
  `python -m regras.c2_2024_04_22` imprime o resultado isolado no dia e o efeito nos 50 dias usados.
"""
import pandas as pd

H1 = pd.Timedelta(hours=1)
MAXR = 590.0


def _vwap(ctx):
    h = ctx.hoje
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _ord(ctx, lado, stop_atr=1.5, alvo_atr=3.0):
    p = float(ctx.hoje.close.iloc[-1]); a = ctx.atr15
    s = min(stop_atr * a, MAXR)
    if lado == "venda":
        return dict(lado="venda", preco=p, stop=p + s, alvo=p - alvo_atr * a, contratos=1)
    return dict(lado="compra", preco=p, stop=p - s, alvo=p + alvo_atr * a, contratos=1)


def _pos(u):
    """posicao do fechamento no range da vela (0 = minima, 1 = maxima)"""
    r = float(u.high - u.low)
    return (float(u.close) - float(u.low)) / r if r > 0 else 0.5


# =====================================================================================================
# 5 maneiras de deixar o dia positivo (todas FAZER novas)
# =====================================================================================================
def f1_rejeicao_da_minima_do_dia(ctx):
    """FAZER (reversao em falha): compra a vela que faz MINIMA NOVA DO DIA e fecha no terco superior do range, range >= 0,8 ATR15,
    entre 10h e 14h. Stop 20 pts abaixo da minima (max 590), alvo 2R. Dia: 11:00 (low 126.125 = nova minima, fecha a 92%).
    Provavelmente geral (spring/rejeicao do extremo; nao usa data nem preco)."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 14): return None
    u = h.iloc[-1]
    if u.low < h.low.iloc[:-1].min() and _pos(u) >= 0.67 and (u.high - u.low) >= 0.8 * ctx.atr15:
        p = float(u.close); st = max(float(u.low) - 20, p - MAXR)
        return dict(lado="compra", preco=p, stop=st, alvo=p + 2 * (p - st), contratos=1)


def f2_climax_de_volume_e_confirmacao(ctx):
    """FAZER (exaustao): a vela ANTERIOR fez minima nova do dia com volume >= 1,4x a media do dia (clima vendedor) e a vela atual
    fecha ACIMA do fechamento anterior com corpo de alta. Compra no fechamento, stop abaixo da minima da vela climax - 20
    (max 590), alvo 2R. Natureza: absorcao/exaustao por volume. Dia: 10:45 foi o climax (1,03M), 11:00 confirmou.
    Provavelmente geral, mas o limiar de 1,4x foi visto no dia."""
    h = ctx.hoje
    if len(h) < 6 or not (10 <= ctx.t.hour < 15): return None
    a, u = h.iloc[-2], h.iloc[-1]
    if a.low < h.low.iloc[:-2].min() and a.vol >= 1.4 * h.vol.mean() and u.close > a.close and u.close > u.open:
        p = float(u.close); st = max(float(min(a.low, u.low)) - 20, p - MAXR)
        return dict(lado="compra", preco=p, stop=st, alvo=p + 2 * (p - st), contratos=1)


def f3_duplo_teste_de_minima(ctx):
    """FAZER (suporte testado duas vezes): a minima da vela atual fica a menos de 0,15 ATR15 da menor minima das 6 velas anteriores,
    a vela fecha em alta (close > open) acima do meio do range e o preco esta abaixo da VWAP. Compra; stop 20 pts abaixo da menor
    das duas minimas (max 590); alvo = VWAP (se >= 1R acima, senao 1,5R). Dia: 10:45 (126.145) e 11:00 (126.125) testam o mesmo
    piso. Provavelmente geral (duplo fundo / teste de suporte)."""
    h = ctx.hoje
    if len(h) < 7 or not (10 <= ctx.t.hour < 15): return None
    u = h.iloc[-1]; ant = h.iloc[-7:-1]
    mn = float(ant.low.min()); v = _vwap(ctx)
    if abs(float(u.low) - mn) <= 0.15 * ctx.atr15 and u.close > u.open and _pos(u) >= 0.5 and u.close < v:
        p = float(u.close); st = max(min(float(u.low), mn) - 20, p - MAXR)
        r = p - st
        alvo = v if v - p >= r else p + 1.5 * r
        return dict(lado="compra", preco=p, stop=st, alvo=alvo, contratos=1)


def f4_reclaim_da_vwap_apos_queda(ctx):
    """FAZER (retomada da media): o preco fechou >= 5 velas M15 seguidas abaixo da VWAP do dia e a vela atual fecha ACIMA dela com
    volume >= media do dia. Compra; stop = 0,8 ATR15 abaixo da VWAP (max 590), alvo 2R. Natureza: retomada da VWAP (valor justo do
    dia). Provavelmente geral."""
    h = ctx.hoje
    if len(h) < 8 or not (10 <= ctx.t.hour < 15): return None
    tp = (h.high + h.low + h.close) / 3
    vw = (tp * h.vol).cumsum() / h.vol.cumsum()
    abaixo = (h.close < vw)
    if h.close.iloc[-1] > vw.iloc[-1] and abaixo.iloc[-6:-1].all() and h.vol.iloc[-1] >= h.vol.mean():
        p = float(h.close.iloc[-1]); st = max(float(vw.iloc[-1]) - 0.8 * ctx.atr15, p - MAXR)
        return dict(lado="compra", preco=p, stop=st, alvo=p + 2 * (p - st), contratos=1)


def f5_rompe_maxima_1a_hora_tarde(ctx):
    """FAZER (rompimento da faixa inicial, compra): entre 12h e 15h, vela que FECHA acima da maxima da 1a hora (a anterior ainda
    estava abaixo), volume >= 0,8x a media do dia, num dia em que o preco ja ficou abaixo da abertura. Stop 1 ATR15, alvo 0,75 ATR15.
    AJUSTADA AO DIA (volume 0,8x e alvo curto escolhidos vendo o dia: 13:30 fechou 127.340 > 127.315, volume 594k contra media 600k,
    e a maxima posterior foi so +315 pts)."""
    h = ctx.hoje
    if len(h) < 8 or not (12 <= ctx.t.hour < 15): return None
    p1 = h[h.index < h.index[0] + H1]
    u = h.iloc[-1]
    if u.close > p1.high.max() and h.close.iloc[-2] <= p1.high.max() and u.vol >= 0.8 * h.vol.mean() and h.low.min() < h.open.iloc[0]:
        return _ord(ctx, "compra", 1.0, 0.75)


FAZER = [
    ("F1 rejeicao da minima do dia (compra)", f1_rejeicao_da_minima_do_dia, None),
    ("F2 climax de volume + confirmacao (compra)", f2_climax_de_volume_e_confirmacao, None),
    ("F3 duplo teste de minima sob a VWAP (compra)", f3_duplo_teste_de_minima, None),
    ("F4 retomada da VWAP apos queda (compra)", f4_reclaim_da_vwap_apos_queda, None),
    ("F5 rompe maxima da 1a hora tarde (compra)", f5_rompe_maxima_1a_hora_tarde, None),
]


# =====================================================================================================
# 5 coisas a NAO fazer (cada uma = condicao de mercado que vira veto; sinaliza o lado a vetar)
# =====================================================================================================
def n1_vender_vela_de_rejeicao(ctx):
    """NAO FAZER vender quando a vela de sinal e de REJEICAO de baixa: fecha no terco superior do proprio range (>= 0,67) e o range
    e >= 0,8 ATR15, entre 10h e 17h. Condicao de mercado: o preco foi varrido para baixo e devolvido; vender o fechamento paga o pior
    preco (11:00: fechou a 92% do range, a F1 vendeu e perdeu R$86). Geral (so usa a forma da vela)."""
    h = ctx.hoje
    if len(h) < 4 or not (10 <= ctx.t.hour < 17): return None
    u = h.iloc[-1]
    if _pos(u) >= 0.67 and (u.high - u.low) >= 0.8 * ctx.atr15:
        return _ord(ctx, "venda")


def n2_vender_esticado_abaixo_da_vwap(ctx):
    """NAO FAZER vender quando o fechamento esta >= 1,5 ATR15 abaixo da VWAP do dia (esticado): o preco ja pagou boa parte da queda e
    o retorno a media e mais provavel que a continuacao. Geral (distancia relativa ao ATR)."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 17): return None
    if _vwap(ctx) - float(h.close.iloc[-1]) >= 1.5 * ctx.atr15:
        return _ord(ctx, "venda")


def n3_vender_apos_climax_de_volume(ctx):
    """NAO FAZER vender na vela seguinte a uma vela de CLIMAX (volume >= 1,4x a media do dia e minima nova do dia): volume maximo no
    extremo e esgotamento do lado vendedor, nao inicio. Dia: 10:45 teve o maior volume (1,03M) e fez a minima; a F1 vendeu a
    vela seguinte. Geral na forma; o limiar 1,4 foi visto no dia."""
    h = ctx.hoje
    if len(h) < 6 or not (10 <= ctx.t.hour < 17): return None
    a = h.iloc[-2]
    if a.low < h.low.iloc[:-2].min() and a.vol >= 1.4 * h.vol.mean():
        return _ord(ctx, "venda")


def n4_vender_queda_ja_estendida(ctx):
    """NAO FAZER vender quando o fechamento ja esta >= 3 ATR15 abaixo da maxima do dia ate ali (queda estendida): sobra pouco
    caminho ate o alvo e o stop fica exposto a retracao. Dia: 11:00 = 945 pts (3,4 ATR15) abaixo da maxima. Geral na forma."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 17): return None
    if float(h.high.max() - h.close.iloc[-1]) >= 3.0 * ctx.atr15:
        return _ord(ctx, "venda")


def n5_vender_com_range_encolhendo(ctx):
    """NAO FAZER vender minima nova quando a vela de sinal tem range <= 70% do range da anterior E volume menor que o da anterior
    (a queda perde forca). Dia: 11:00 range 265 contra 405 e volume 686k contra 1,03M. Geral na forma; limiares ajustados ao dia."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 17): return None
    a, u = h.iloc[-2], h.iloc[-1]
    if u.low < h.low.iloc[:-1].min() and (u.high - u.low) <= 0.7 * (a.high - a.low) and u.vol < a.vol:
        return _ord(ctx, "venda")


NAO_FAZER = [
    ("N1 vender vela de rejeicao de baixa", n1_vender_vela_de_rejeicao, None),
    ("N2 vender esticado abaixo da VWAP", n2_vender_esticado_abaixo_da_vwap, None),
    ("N3 vender apos climax de volume", n3_vender_apos_climax_de_volume, None),
    ("N4 vender queda ja estendida", n4_vender_queda_ja_estendida, None),
    ("N5 vender com range e volume encolhendo", n5_vender_com_range_encolhendo, None),
]

AJUSTES = {f"F{i+1}": dict(add_fazer=[(f"c2:{n}", r, g)]) for i, (n, r, g) in enumerate(FAZER)}
AJUSTES.update({f"N{i+1}": dict(add_veto=[(f"c2:{n}", r, g)]) for i, (n, r, g) in enumerate(NAO_FAZER)})

DIA = "2024-04-22"


# ---- avaliacao nos 50 dias usados (robo v2 como base) -------------------------------------------------
def monta(fz, nf, chaves):
    fz, nf = list(fz), list(nf)
    for k in chaves:
        a = AJUSTES[k]
        fz += a.get("add_fazer", [])
        nf += a.get("add_veto", [])
    return fz, nf


def _dias_usados():
    import json
    from pathlib import Path
    j = json.load(open(Path(__file__).resolve().parents[1] / "dias_usados.json"))
    return list(j["ciclo0"]["dias"]) + [x["dia"] for x in j["ciclo1"]["dias"]] + [x["dia"] for x in j["ciclo2"]["dias"]]


def _um(args):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import robo, robo_v2
    from regras import c2_2024_04_22 as c2
    chaves, dia = args
    fz, nf = robo_v2.monta_v2()
    fz, nf = c2.monta(fz, nf, chaves)
    tr, log, contra = robo_v2.roda_v2(dia, fz, nf)
    ok = [x for x in tr if x.t_ent]
    return chaves, dia, round(sum(x.brl for x in ok), 2), len(ok), [(x.fonte[:45], x.lado, str(x.t_ent.time()), x.motivo, round(x.brl, 1)) for x in ok]


def avalia(configs, dias=None, workers=8):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    dias = dias or _dias_usados()
    res = {tuple(c): {} for c in configs}
    with ProcessPoolExecutor(workers) as ex:
        fut = [ex.submit(_um, (tuple(c), d)) for c in configs for d in dias]
        for f in as_completed(fut):
            ch, d, brl, ops, tr = f.result()
            res[ch][d] = (brl, ops, tr)
    return res


if __name__ == "__main__":
    import sys, json
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia(DIA, r, g, max_ops=3))
            print(f"{grupo:9s} {nome:48s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
    res = avalia([()] + [(k,) for k in AJUSTES])
    b = res[()]
    saida = {}
    print("\nconfig | R$ no dia (robo v2+mudanca) | R$ 50 dias | dias piorou | dias melhorou")
    for c, r in res.items():
        tot = sum(v[0] for v in r.values())
        pi = sorted(d for d in r if r[d][0] < b[d][0] - 0.005)
        me = sorted(d for d in r if r[d][0] > b[d][0] + 0.005)
        saida["+".join(c) or "BASE"] = dict(dia=r[DIA][0], total=round(tot, 2), piorou=pi, melhorou=me,
                                           delta_pior=round(sum(r[d][0] - b[d][0] for d in pi), 2), delta_melhor=round(sum(r[d][0] - b[d][0] for d in me), 2))
        print(f"{'+'.join(c) or 'BASE':6s} dia {r[DIA][0]:8.2f}  conj {tot:9.2f}  piorou {len(pi)}  melhorou {len(me)}", flush=True)
    json.dump(saida, open(Path(__file__).resolve().parents[1] / "analises" / "c2_2024_04_22_eval.json", "w"), indent=1)
