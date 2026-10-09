"""Ciclo 3 - dia 2022-12-12 (WIN M15, intermediario, ef 0,173). Robo v3 fechou -R$213,00 (v2 -213; v1 -93).

  09:30 F1 falha da minima de ontem (compra)     stop -R$93,00
  12:30 F1 rompe minima da 1a hora (venda)       stop -R$120,00   (so entrou porque o A2 da v2 soltou o veto; a v1 nao operou)

O dia: gap de alta +250, 1a vela de queda forte (-605), rotacao ate 10:30, e entao QUEDA de 107.615 (10:30) ate 103.765 (12:00): 3.670
pts a partir do fecho das 10:30 (R$734 por contrato), 1,37 ATRd. O robo so vendeu as 12:30, depois de a queda ja ter andado 3,8
ATR15 abaixo da minima da 1a hora, e foi stopado no repique das 14:00.
Dinheiro na mesa: venda das 10:30 (+3.670 pts). 10:30: FAZER nos dois lados (pullback de venda x F5 compra) = nao entra, e as duas
estavam vetadas (compra_queda_1atr; vender_rali_1atr). 10:45: vela de expansao de 925 pts (2,4 ATR15, volume 1,7x, fecha na minima):
A4 sinalizou venda, vetada so pelo N2 (vender minima na rotacao da manha). 11:00-12:00: sinais de venda vetados por N2, N5 (C7) e
rompimento_sem_volume. Ou seja: 5 vetos desenhados para a ROTACAO calaram uma perna de expansao.

Contem: AP (ajustes sobre o v3, avaliaveis por regras.c3_grupo_2022_12_12.avalia(..., mods=["regras.c3_2022_12_12"])) e
FAZER / NAO_FAZER (regras isoladas). As propostas comuns (G1..G7, S1/S2) estao em regras/c3_grupo_2022_12_12.py.
`python -m regras.c3_2022_12_12` imprime o resultado isolado no dia, dentro do robo e o efeito nos 70 dias.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regras import c3_grupo_2022_12_12 as g
from regras.c3_grupo_2022_12_12 import vwap, ef_parcial, _ord, expansao, MAXR

DIA = "2022-12-12"


def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


# ================================================================================================================
# NAO FAZER
# ================================================================================================================
def n_comprar_apos_abertura_de_queda_forte(ctx):
    """NAO FAZER comprar (ate 10:00) quando a 1a vela do dia foi de QUEDA FORTE (corpo >= 70% da faixa, faixa >= 1,2 ATR15) e a vela
    atual ainda fecha abaixo da abertura do dia. Armadilha: a compra de 'falha da minima de ontem' acha que o fundo foi varrido, mas
    o dia abriu em 'drive' vendedor e a 1a vela e a perna dominante. 09:30: 1a vela -605 (corpo 72%), fecho 107.425 < abertura 107.895;
    a F1 de compra perdeu -R$93. Condicao: drive de abertura contra o lado da compra."""
    h = ctx.hoje
    if len(h) < 2 or ctx.t.hour >= 10: return None
    p = h.iloc[0]; rng = float(p.high - p.low)
    if rng >= 1.2 * ctx.atr15 and (p.open - p.close) >= 0.7 * rng and h.close.iloc[-1] < p.open:
        return _ord(ctx, "compra", float(h.close.iloc[-1]) - 1.0 * ctx.atr15, alvo_r=1.5)


def n_comprar_gap_de_alta_ja_preenchido(ctx):
    """NAO FAZER comprar ate 10:30 quando o dia abriu com gap de ALTA e o fechamento ja esta abaixo do fecho de ontem (gap totalmente
    preenchido). Armadilha: o gap preenchido cedo e o comprador de abertura derrotado; 'falha da minima de ontem' compra o que o
    dia ja mostrou que nao segura. 09:30: abertura 107.895 (+250 sobre o fecho 107.645), fecho 107.425 < 107.645: perdeu -R$93."""
    h = ctx.hoje
    if ctx.t.hour * 60 + ctx.t.minute > 10 * 60 + 30 or ctx.diario is None or len(ctx.diario) < 1: return None
    fo = float(ctx.diario.close.iloc[-1])
    if h.open.iloc[0] > fo and h.close.iloc[-1] < fo:
        return _ord(ctx, "compra", float(h.close.iloc[-1]) - 1.0 * ctx.atr15, alvo_r=1.5)


def n_vender_perseguindo_queda_de_1_2_atrd(ctx):
    """NAO FAZER vender depois de 12:00 quando o fechamento ja esta >= 1,2 ATRd abaixo da MAXIMA do dia. Armadilha: o que o dia
    costuma dar de amplitude diaria ja foi pago; a venda chega no fim da perna e o stop de 1,5 ATR15 (inflado pela volatilidade da
    queda) fica no meio do repique. 12:30: queda de 3.500 pts = 1,3 ATRd, ATR15 658; stop -R$120 no repique das 14:00."""
    h = ctx.hoje
    if _hm(ctx) < 12 * 60 or len(h) < 10: return None
    if h.high.max() - h.close.iloc[-1] >= 1.2 * ctx.atrd:
        return _ord(ctx, "venda", float(h.close.iloc[-1]) + 1.5 * ctx.atr15, alvo_r=2.0)


def n_comprar_contra_ema_caindo_abaixo_da_abertura(ctx):
    """NAO FAZER comprar entre 10:00 e 14:00 quando a EMA20 M15 caiu nas 3 ultimas velas E o fechamento esta abaixo da abertura do dia
    E o preco esta abaixo da EMA20. Armadilha: comprar 'suporte' contra a media que cai, num dia que perde a abertura: o suporte vira
    resistencia. 10:30: EMA20 caindo, fecho 107.445 < abertura 107.895 (a F5 de compra era o outro lado do empate; entraria e perderia).
    Condicao: tendencia de baixa em formacao."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= ctx.t.hour < 14): return None
    e = ctx.m15.close.ewm(span=20, adjust=False).mean()
    c = float(h.close.iloc[-1])
    if e.iloc[-1] < e.iloc[-4] and c < float(h.open.iloc[0]) and c < float(e.iloc[-1]):
        return _ord(ctx, "compra", c - 1.0 * ctx.atr15, alvo_r=1.5)


def n_vender_exaustao_volume_seco_sob_vwap(ctx):
    """NAO FAZER vender depois de 11:30 com o fechamento a >= 2 ATR15 abaixo da VWAP e o volume da vela < 0,75x a media do dia.
    Armadilha: queda esticada sem participacao: os vendedores sumiram e o repique encontra pouca oferta. 12:30: -2,3 ATR15 da VWAP,
    volume 0,69x; stop -R$120."""
    h = ctx.hoje
    if _hm(ctx) < 11 * 60 + 30 or len(h) < 10: return None
    c = float(h.close.iloc[-1])
    if (c - vwap(h)) <= -2.0 * ctx.atr15 and h.vol.iloc[-1] < 0.75 * h.vol.mean():
        return _ord(ctx, "venda", c + 1.5 * ctx.atr15, alvo_r=2.0)


def ap_veto(fn, nome):
    def ap(cfg): cfg.nf = cfg.nf + [(nome, fn, None)]
    return ap


FAZER = [("G5 recuo pos-expansao (continuacao)", g.f_recuo_pos_expansao, None),
         ("G6 impulso da 1a vela (entrada cedo)", g.f_impulso_primeira_vela, None)]
NAO_FAZER = [
    ("N1 comprar apos 1a vela de queda forte", n_comprar_apos_abertura_de_queda_forte, None),
    ("N2 comprar gap de alta ja preenchido", n_comprar_gap_de_alta_ja_preenchido, None),
    ("N3 vender perseguindo queda >= 1,2 ATRd", n_vender_perseguindo_queda_de_1_2_atrd, None),
    ("N4 comprar contra EMA20 caindo sob a abertura", n_comprar_contra_ema_caindo_abaixo_da_abertura, None),
    ("N5 vender exaustao sob a VWAP com volume seco", n_vender_exaustao_volume_seco_sob_vwap, None),
]

AP = {
    "D1_N1": ap_veto(n_comprar_apos_abertura_de_queda_forte, "c3:N1 comprar apos queda forte"),
    "D1_N2": ap_veto(n_comprar_gap_de_alta_ja_preenchido, "c3:N2 gap preenchido"),
    "D1_N3": ap_veto(n_vender_perseguindo_queda_de_1_2_atrd, "c3:N3 perseguir queda"),
    "D1_N4": ap_veto(n_comprar_contra_ema_caindo_abaixo_da_abertura, "c3:N4 comprar contra EMA"),
    "D1_N5": ap_veto(n_vender_exaustao_volume_seco_sob_vwap, "c3:N5 exaustao vol seco"),
}

if __name__ == "__main__":
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, gg in lista:
            res = g.isolada(DIA, r, gg)
            print(f"{grupo:9s} {nome:50s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
    nomes = list(AP) + ["G7a+S2", "G7a+G3", "G7a+D1_N1", "G7a+S2+D1_N1"]
    res = g.avalia(nomes, mods=["regras.c3_2022_12_12"])
    g.imprime(res, nomes)
    print("\nno dia", DIA)
    for n in ["BASE"] + nomes:
        r = res[n][DIA]
        print(f"{n:14s} {r['brl']:8.2f}", [(t['fonte'].split(':')[-1][:20], t['lado'][0], t['ent'][:5], t['motivo'], t['brl']) for t in r['trades']])
