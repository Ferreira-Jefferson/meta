"""Pregão 2024-01-19 (WIN M15). Gap de alta (+580 pts, ~0,33 ATRd) que não se sustenta: queda até 13:45
(-1.395 pts da abertura) e recuperação em V na tarde. Todas as regras usam só o passado do instante."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np


def HORA(t):
    return t.hour + t.minute / 60


# ---------------- FAZER ----------------
def f1_rompe_minima_1a_hora(ctx):
    """Natureza: rompimento da faixa da 1ª hora. Vende quando uma vela M15 fecha abaixo da mínima das 4 primeiras
    velas (09:00-10:00), entre 10:00 e 14:00, uma vez por dia; stop na máxima da 1ª hora (limitado a 600 pts), alvo 1,5x o risco.
    Condição: dia que sai da faixa da abertura para baixo. Provavelmente geral (ORB de 1h clássico)."""
    h = ctx.hoje
    if len(h) < 5 or not (10 <= HORA(ctx.t) <= 14) or ctx.ops_hoje:
        return None
    f = h.iloc[:4]
    c = h.close.iloc[-1]
    if c < f.low.min() and h.close.iloc[:-1].min() >= f.low.min():
        risco = min(f.high.max() - c, 600)
        return dict(lado="venda", stop=c + risco, alvo=c - 1.5 * risco)
    return None


def f2_gap_alta_perde_abertura(ctx):
    """Natureza: gap. Com gap de alta (abertura > fechamento de ontem + 0,2 ATRd), vende quando o preço fecha abaixo da
    abertura do dia entre 10:00 e 13:00, buscando o preenchimento do gap. Stop 1 ATR15 acima, alvo abaixo do fechamento de ontem.
    Condição: gap que perde a abertura sem recuperar. Ajustada ao dia (o fade de gap não replicou em amostras do projeto)."""
    h = ctx.hoje
    if not (10 <= HORA(ctx.t) <= 13) or ctx.ops_hoje:
        return None
    ont = ctx.diario.close.iloc[-1]
    ab = h.open.iloc[0]
    c = h.close.iloc[-1]
    if ab - ont > 0.2 * ctx.atrd and c < ab:
        alvo = ont - 1.5 * ctx.atr15
        if alvo < c:
            return dict(lado="venda", stop=c + min(ctx.atr15, 600), alvo=alvo)
    return None


def f3_rompe_minima_de_ontem(ctx):
    """Natureza: nível de ontem. Vende quando o fechamento M15 perde a mínima de ontem (primeira vez no dia) entre 10:00 e
    14:00, com o dia aberto acima dela e o mercado em baixa de vários dias (fechamento de ontem < fechamento de 3 pregões atrás).
    Stop 1,2 ATR15 acima, sem alvo (deixa correr); gerir arrasta o stop 1 ATR15 atrás do preço depois de 1 ATR15 a favor.
    Provavelmente geral (continuação em tendência)."""
    h = ctx.hoje
    if not (10 <= HORA(ctx.t) <= 14) or ctx.ops_hoje or len(ctx.diario) < 4:
        return None
    mn = ctx.diario.low.iloc[-1]
    tendencia = ctx.diario.close.iloc[-1] < ctx.diario.close.iloc[-4]
    c = h.close.iloc[-1]
    if tendencia and c < mn and h.close.iloc[:-1].min() >= mn and h.open.iloc[0] > mn:
        return dict(lado="venda", stop=c + min(1.2 * ctx.atr15, 600), alvo=None)
    return None


def g3(ctx, pos):
    """Arrasta o stop 1 ATR15 atrás do preço depois de 1 ATR15 a favor."""
    px = ctx.m1.close.iloc[-1]
    if pos["preco"] - px > ctx.atr15:
        return max(px, 0) + 1.0 * ctx.atr15 if px + ctx.atr15 < pos["stop"] else None
    return None


def f4_falha_da_minima_do_dia(ctx):
    """Natureza: reversão em falha. Entre 13:00 e 16:00, se a mínima do dia ficou >= 2 velas para trás, o dia caiu > 0,6 ATRd
    da abertura e o fechamento volta acima da máxima da vela da mínima, compra. Stop na mínima do dia (<= 600 pts), alvo 1,5x risco.
    Ajustada ao dia: reversão tem fundamento, mas o projeto mediu continuação > reversão; só vale com o filtro de queda grande."""
    h = ctx.hoje
    if not (13 <= HORA(ctx.t) <= 16) or ctx.ops_hoje or len(h) < 8:
        return None
    i = int(np.argmin(h.low.values))
    if len(h) - 1 - i < 2:
        return None
    c = h.close.iloc[-1]
    if h.open.iloc[0] - h.low.min() > 0.6 * ctx.atrd and c > h.high.iloc[i] and h.close.iloc[-2] <= h.high.iloc[i]:
        risco = min(c - h.low.min(), 600)
        return dict(lado="compra", stop=c - risco, alvo=c + 1.5 * risco)
    return None


def f5_recuo_a_media_apos_virada(ctx):
    """Natureza: recuo a favor da tendência (curta). Entre 14:30 e 16:30, depois que o dia esteve abaixo da média de 20 velas
    M15, compra a vela que toca a média (mínima até 0,3 ATR15 acima dela) e fecha acima, com a vela anterior já acima.
    Stop 1,5 ATR15 abaixo, alvo 1,5 ATR15 acima. Ajustada ao dia (a virada foi vista)."""
    h = ctx.hoje
    if not (14.5 <= HORA(ctx.t) <= 16.5) or ctx.ops_hoje or len(h) < 6:
        return None
    m = ctx.m15.close.rolling(20).mean()
    if m.isna().iloc[-1]:
        return None
    c = h.close.iloc[-1]
    ant = (h.close.iloc[:-3].values < m.iloc[-len(h):-3].values).any()
    if ant and c > m.iloc[-1] and h.low.iloc[-1] <= m.iloc[-1] + 0.3 * ctx.atr15 and h.close.iloc[-2] > m.iloc[-2]:
        return dict(lado="compra", stop=c - min(1.5 * ctx.atr15, 600), alvo=c + 1.5 * ctx.atr15)
    return None


# ---------------- NÃO FAZER ----------------
def n1_compra_gap_de_alta(ctx):
    """Armadilha: comprar a continuação do gap de alta (09:30, fechamento acima da abertura do dia, gap > 0,2 ATRd).
    Veto: não comprar gap de alta contra baixa de vários dias (fechamento de ontem < o de 3 pregões atrás); o gap se desfaz."""
    h = ctx.hoje
    if ctx.ops_hoje or not (9.4 <= HORA(ctx.t) <= 9.6) or len(h) < 2:
        return None
    if h.open.iloc[0] > ctx.diario.close.iloc[-1] + 0.2 * ctx.atrd and h.close.iloc[-1] > h.open.iloc[0]:
        c = h.close.iloc[-1]
        return dict(lado="compra", stop=c - 600, alvo=c + 600)
    return None


def n2_compra_queda_de_1atr(ctx):
    """Armadilha: comprar a queda de 1 ATR15 abaixo da abertura (reversão à média), entre 10:00 e 13:00, alvo na abertura.
    Veto: não comprar 'barato' em dia de queda com mínimas descendentes e volume alto na descida (continuação)."""
    h = ctx.hoje
    if ctx.ops_hoje or not (10 <= HORA(ctx.t) <= 13):
        return None
    c = h.close.iloc[-1]
    if c < h.open.iloc[0] - ctx.atr15:
        return dict(lado="compra", stop=c - 500, alvo=h.open.iloc[0])
    return None


def n3_vende_nova_minima_tarde(ctx):
    """Armadilha: vender a nova mínima do dia entre 13:00 e 15:00 quando o dia já caiu > 0,6 ATRd da abertura.
    Veto: não vender extensão de queda tardia depois de movimento esticado (exaustão); sinais pioram depois das 13h."""
    h = ctx.hoje
    if ctx.ops_hoje or not (13 <= HORA(ctx.t) <= 15):
        return None
    c = h.close.iloc[-1]
    if h.low.iloc[-1] <= h.low.min() and h.open.iloc[0] - c > 0.6 * ctx.atrd:
        return dict(lado="venda", stop=c + 400, alvo=c - 800)
    return None


def n4_compra_teste_da_minima_de_ontem(ctx):
    """Armadilha: comprar o teste da mínima de ontem como suporte (fechamento até 0,5 ATR15 acima dela, entre 10:00 e 12:00).
    Veto: não comprar suporte de ontem em baixa de vários dias com volume crescente: o nível quebra em vez de segurar."""
    h = ctx.hoje
    if ctx.ops_hoje or not (10 <= HORA(ctx.t) <= 12):
        return None
    mn = ctx.diario.low.iloc[-1]
    c = h.close.iloc[-1]
    if 0 < c - mn <= 0.5 * ctx.atr15:
        return dict(lado="compra", stop=mn - 400, alvo=c + 600)
    return None


def n5_vende_rompimento_de_maxima_tarde(ctx):
    """Armadilha: vender a vela que rompe a máxima das 8 velas anteriores depois das 15:00 (apostar contra o rompimento 'esticado'),
    stop curto de 150 pts. Veto: não vender contra virada intradiária já em curso (mínimas e máximas ascendentes desde o fundo)."""
    h = ctx.hoje
    if ctx.ops_hoje or not (15 <= HORA(ctx.t) <= 16.5) or len(h) < 10:
        return None
    c = h.close.iloc[-1]
    if c > h.high.iloc[-9:-1].max():
        return dict(lado="venda", stop=c + 150, alvo=c - 600)
    return None


FAZER = [("rompe mínima da 1ª hora", f1_rompe_minima_1a_hora, None),
         ("gap de alta perde abertura (fecha o gap)", f2_gap_alta_perde_abertura, None),
         ("rompe mínima de ontem em baixa de vários dias", f3_rompe_minima_de_ontem, g3),
         ("falha da mínima do dia (reversão)", f4_falha_da_minima_do_dia, None),
         ("recuo à média 20 após virada", f5_recuo_a_media_apos_virada, None)]
NAO_FAZER = [("compra continuação do gap de alta", n1_compra_gap_de_alta, None),
             ("compra queda de 1 ATR da abertura", n2_compra_queda_de_1atr, None),
             ("vende nova mínima após 13h", n3_vende_nova_minima_tarde, None),
             ("compra teste da mínima de ontem", n4_compra_teste_da_minima_de_ontem, None),
             ("vende rompimento de máxima após 15h", n5_vende_rompimento_de_maxima_tarde, None)]

if __name__ == "__main__":
    import base
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, g in lista:
            res = base.resumo(base.simula_dia("2024-01-19", r, g))
            print(f"{grupo:9} {nome:48} ops={res['ops']} R$={res['brl']:9.2f}")
            for x in res["lista"]:
                print("          ", x)
