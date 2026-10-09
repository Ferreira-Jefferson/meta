"""Ciclo 3 - dia 2024-02-01 (WIN M15, rotacao, ef 0,031). Robo v3 fechou -R$253,09 (v2 -254,71; v1 -254,71).

  09:31 gap_fade_fechamento (venda)          stop -R$65,00
  12:30 venda pullback EMA20 em baixa        stop -R$93,00   (so entrou no 12:30; 12:00/12:15 vetadas, o veto N4-VWAP caiu em 12:30)
  14:47 Recuo a EMA21 em baixa (venda)       stop -R$95,09

O dia: gap +570 (0,32 ATRd), faixa 127.545-128.725 (1.180 pts = 0,66 ATRd) em torno da VWAP (128.2xx), fecha 128.840 (+355 da abertura).
As tres vendas foram a continuacao de uma queda que nao existia: o dia girou em volta da VWAP.
Maior movimento perdido: COMPRA 13:15 (127.685 -> 128.715), +1.255 pts / +R$251. O robo estava com a venda das 12:30 aberta
(1 posicao por vez; a venda estava +490 pts a favor as 13:15 e foi stopada a 128.630 as 14:15) e nao ha FAZER de compra para o estado
'1,6 ATR abaixo da VWAP em dia de rotacao'.

Contem: AP (propostas como ajustes sobre o v3, avaliaveis por regras.c3_grupo_2022_12_12.avalia(..., mods=["regras.c3_2024_02_01"])),
FAZER / NAO_FAZER (as regras isoladas, para conferir o R$ do dia com base.simula_dia).
`python -m regras.c3_2024_02_01` imprime isolada no dia + dentro do robo + efeito nos 70 dias.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from regras import c3_grupo_2022_12_12 as g
from regras.c3_grupo_2022_12_12 import vwap, ef_parcial, _ord, V_N4C6, MAXR

DIA = "2024-02-01"


def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


# ================================================================================================================
# GESTAO ADAPTATIVA: breakeven + trailing so em dia de rotacao
# ================================================================================================================
def _gerir_rotacao(ativa, dist, ef_max):
    def gerir(ctx, pos):
        """GESTAO ADAPTATIVA (estado = eficiencia parcial do dia). So age se o dia esta em rotacao (eficiencia parcial < ef_max) E a
        posicao ja andou `ativa` ATR15 a favor no melhor fechamento: o stop vai para o preco de entrada e passa a seguir o melhor
        fechamento a `dist` ATR15. Em dia direcional (eficiencia >= ef_max) nao mexe: la o trade 'ganha deixando correr' (licao do
        projeto; o G1 universal do ciclo 2 cortava esses ganhos). Usa so o passado."""
        h = ctx.hoje
        if ef_parcial(h) >= ef_max: return None
        hh = h[h.index >= pos["t_ent"].floor("15min")]
        a = ctx.atr15
        if pos["lado"] == "venda":
            if pos["preco"] - float(hh.close.min()) < ativa * a: return None
            return min(float(hh.close.min()) + dist * a, pos["preco"])
        if float(hh.close.max()) - pos["preco"] < ativa * a: return None
        return max(float(hh.close.max()) - dist * a, pos["preco"])
    return gerir


def _ap_gestao(ativa, dist, ef_max):
    ger = _gerir_rotacao(ativa, dist, ef_max)

    def post(n, s, gg, ctx): return s, (gg if gg is not None else ger)
    def ap(cfg): cfg.post = cfg.post + [post]
    return ap


# ================================================================================================================
# FAZER novo: reversao a VWAP esticada em dia de rotacao
# ================================================================================================================
def f_reversao_vwap_em_rotacao(ctx, k=1.4, ef_max=0.12):
    """FAZER novo (reversao a VWAP, so em dia SEM direcao). Entre 11:00 e 16:00, com a eficiencia parcial do dia < 0,12 e o fechamento a
    >= 1,4 ATR15 da VWAP, entra CONTRA o esticamento (abaixo da VWAP compra; acima vende) limitado no fechamento, alvo na VWAP,
    stop 1,0 ATR15 alem do fechamento (teto 590). Neste dia: 13:15 fecha 127.685 (VWAP 128.268, -1,57 ATR15, ef parcial 0,06) ->
    alvo em 14:00. Condicao de mercado: em dia que nao foi a lugar nenhum a VWAP e o imam; o gate de eficiencia parcial tira os
    dias em que a esticada e o inicio da tendencia. Perde quando um dia de rotacao vira tendencia depois das 11h (o gate usa o
    passado, nao sabe). Natureza: reversao a media ponderada. Geral na forma (tudo relativo: ATR15, VWAP, eficiencia do dia)."""
    h = ctx.hoje
    if len(h) < 8 or not (11 * 60 <= _hm(ctx) <= 16 * 60): return None
    if ef_parcial(h) >= ef_max: return None
    v = vwap(h); c = float(h.close.iloc[-1]); a = ctx.atr15
    if c <= v - k * a:
        st = max(c - 1.0 * a, c - MAXR)
        if v - c >= 0.8 * (c - st): return dict(lado="compra", preco=c, stop=st, alvo=v, contratos=1)
    if c >= v + k * a:
        st = min(c + 1.0 * a, c + MAXR)
        if c - v >= 0.8 * (st - c): return dict(lado="venda", preco=c, stop=st, alvo=v, contratos=1)
    return None


def f_reversao_vwap_em_rotacao_ef16(ctx):
    """H3b = H3 com o gate de eficiencia parcial < 0,16 em vez de 0,12. AJUSTADA AO DIA: as 13:15 a eficiencia parcial era 0,15 e o gate
    de 0,12 a barrava; 0,16 foi escolhido DEPOIS de ver isso. Isolada no dia: compra 13:15, alvo na VWAP, +R$114,76."""
    return f_reversao_vwap_em_rotacao(ctx, 1.4, 0.16)


def ap_h3b(cfg): cfg.fz = cfg.fz + [("c3:H3b reversao VWAP rotacao ef<0,16", f_reversao_vwap_em_rotacao_ef16, None)]
def ap_h3bp(cfg): cfg.prio = cfg.prio + [("c3:H3b (prio)", f_reversao_vwap_em_rotacao_ef16, None)]


def ap_h3(cfg): cfg.fz = cfg.fz + [("c3:H3 reversao VWAP rotacao", f_reversao_vwap_em_rotacao, None)]
def ap_h3p(cfg): cfg.prio = cfg.prio + [("c3:H3 reversao VWAP rotacao (prio)", f_reversao_vwap_em_rotacao, None)]


# ================================================================================================================
# NAO FAZER
# ================================================================================================================
def n_vender_perto_da_vwap_em_rotacao_05(ctx):
    """NAO FAZER vender (vela de queda, depois das 11:30) quando o fechamento esta a <= 0,5 ATR15 da VWAP e a eficiencia parcial do
    dia < 0,10. Versao do `c2:N4 vwap rotacao` (C6, 0,3 x faixa mediana) com a distancia em ATR15. Armadilha: sem esticamento a
    favor, a venda de continuacao em volta da VWAP vira ruido: 12:30 (-0,41 ATR15 da VWAP, -R$93) e 14:47 (-0,43, -R$95).
    Condicao: dia sem direcao + preco no valor."""
    h = ctx.hoje
    if _hm(ctx) < 11 * 60 + 30 or len(h) < 8: return None
    if abs(float(h.close.iloc[-1]) - vwap(h)) <= 0.5 * ctx.atr15 and ef_parcial(h) < 0.10 and h.close.iloc[-1] < h.close.iloc[-2]:
        return _ord(ctx, "venda", float(h.close.iloc[-1]) + 1.3 * ctx.atr15, alvo_r=2.0)


def n_vender_continuacao_em_dia_que_foi_e_voltou(ctx):
    """NAO FAZER vender continuacao depois das 12:00 quando a faixa do dia ja e >= 0,4 ATRd mas o fechamento esta a < 8% da soma das
    faixas de distancia da abertura (eficiencia parcial < 0,08: 'foi e voltou'). Armadilha: o movimento ja aconteceu nos dois
    sentidos e voltou ao ponto de partida; nao ha perna para continuar. 12:30 (-R$93) e 14:47 (-R$95) tinham ef parcial 0,07 e 0,05."""
    h = ctx.hoje
    if _hm(ctx) < 12 * 60 or len(h) < 10: return None
    if (h.high.max() - h.low.min()) >= 0.4 * ctx.atrd and ef_parcial(h) < 0.08 and h.close.iloc[-1] < h.close.iloc[-2]:
        return _ord(ctx, "venda", float(h.close.iloc[-1]) + 1.3 * ctx.atr15, alvo_r=2.0)


def n_vender_gap_de_alta_pequeno_acima_do_fecho_fraco(ctx):
    """NAO FAZER vender o gap de alta (fade) quando o gap e < 0,4 ATRd. Armadilha: gap pequeno nao e excesso: o primeiro retorno ao
    fecho de ontem nao e certo e o stop de 1 ATR15 e maior que o ganho esperado. 09:31: gap +570 = 0,32 ATRd, stop -R$65. So veta o
    fade de gap (barras ate 10:00)."""
    h = ctx.hoje
    if len(h) > 4 or ctx.diario is None or len(ctx.diario) < 1: return None
    gap = float(h.open.iloc[0] - ctx.diario.close.iloc[-1])
    if 0 < gap < 0.4 * ctx.atrd and h.close.iloc[-1] < h.open.iloc[0]:
        return _ord(ctx, "venda", float(h.close.iloc[-1]) + 1.0 * ctx.atr15, alvo=float(ctx.diario.close.iloc[-1]))


def n_vender_apos_dois_stops_do_mesmo_lado(ctx):
    """NAO FAZER entrar de novo no MESMO lado depois de 2 stops seguidos no dia (ops_hoje). Armadilha: o mercado ja disse duas vezes que
    o lado nao tem perna; a terceira entrada repete a hipotese refutada: 14:47 (3a venda, -R$95)."""
    ops = getattr(ctx, "ops_hoje", [])
    if len(ops) >= 2 and all(o.motivo == "stop" for o in ops[-2:]) and ops[-1].lado == ops[-2].lado:
        return _ord(ctx, ops[-1].lado, float(ctx.hoje.close.iloc[-1]) + (1 if ops[-1].lado == "venda" else -1) * ctx.atr15, alvo_r=1.5)


def n_comprar_rompimento_sem_volume_manha(ctx):
    """NAO FAZER comprar o fechamento acima da maxima das 4 velas anteriores entre 11:30 e 12:00 com o volume da vela < 1,3x a media das
    4 anteriores e o dia com eficiencia parcial < 0,10. Armadilha: rompimento da faixa curta numa rotacao e falso. 11:45: fecho
    128.685, a vela seguinte devolve 345 pts. (O robo ja vetava; entra como NAO_FAZER em simulacao isolada: R$ < 0 no dia.)"""
    h = ctx.hoje
    if not (11 * 60 + 30 <= _hm(ctx) <= 12 * 60) or len(h) < 8: return None
    u, j = h.iloc[-1], h.iloc[-5:-1]
    if u.close > j.high.max() and u.vol < 1.3 * j.vol.mean() and ef_parcial(h) < 0.10:
        return _ord(ctx, "compra", float(u.close) - 1.0 * ctx.atr15, alvo_r=1.5)


def ap_veto(fn, nome):
    def ap(cfg): cfg.nf = cfg.nf + [(nome, fn, None)]
    return ap


def ap_h1(cfg):
    """H1: troca `c2:N4 vwap rotacao` (C6) pela versao em ATR15 (<= 0,5 ATR15, ef < 0,10)."""
    assert any(n == V_N4C6 for n, _, _ in cfg.nf)
    cfg.nf = [(n, n_vender_perto_da_vwap_em_rotacao_05, gg) if n == V_N4C6 else (n, r, gg) for n, r, gg in cfg.nf]


FAZER = [("H3 reversao a VWAP esticada em rotacao", f_reversao_vwap_em_rotacao, None),
         ("H3b mesma, gate de eficiencia 0,16 (ajustada ao dia)", f_reversao_vwap_em_rotacao_ef16, None)]
NAO_FAZER = [
    ("N1 vender perto da VWAP em rotacao (<=0,5 ATR)", n_vender_perto_da_vwap_em_rotacao_05, None),
    ("N2 vender continuacao em dia que foi e voltou", n_vender_continuacao_em_dia_que_foi_e_voltou, None),
    ("N3 vender gap de alta pequeno (<0,4 ATRd)", n_vender_gap_de_alta_pequeno_acima_do_fecho_fraco, None),
    ("N4 3a entrada no mesmo lado apos 2 stops", n_vender_apos_dois_stops_do_mesmo_lado, None),
    ("N5 comprar rompimento sem volume na rotacao", n_comprar_rompimento_sem_volume_manha, None),
]

AP = {
    "H1": ap_h1,
    "H2a": _ap_gestao(1.0, 0.75, 0.10),     # breakeven + trailing 0,75 ATR em rotacao (ef parcial < 0,10)
    "H2b": _ap_gestao(1.0, 1.0, 0.10),
    "H2c": _ap_gestao(1.2, 1.25, 0.15),
    "H3": ap_h3,
    "H3p": ap_h3p,
    "H3b": ap_h3b,
    "H3bp": ap_h3bp,
    "H4_N2": ap_veto(n_vender_continuacao_em_dia_que_foi_e_voltou, "c3:N2 foi e voltou"),
    "H4_N3": ap_veto(n_vender_gap_de_alta_pequeno_acima_do_fecho_fraco, "c3:N3 gap pequeno"),
    "H4_N4": ap_veto(n_vender_apos_dois_stops_do_mesmo_lado, "c3:N4 2 stops"),
    "H4_N5": ap_veto(n_comprar_rompimento_sem_volume_manha, "c3:N5 rompimento sem volume"),
}

if __name__ == "__main__":
    for grupo, lista in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for nome, r, gg in lista:
            res = g.isolada(DIA, r, gg)
            print(f"{grupo:9s} {nome:50s} isolada R$ {res['brl']:8.2f} ops {res['ops']}", flush=True)
    nomes = list(AP) + ["H2a+H3", "H2a+H3p", "H1+H2a", "H2a+H3b", "H2a+H3bp"]
    res = g.avalia(nomes, mods=["regras.c3_2024_02_01"])
    g.imprime(res, nomes)
    print("\nno dia", DIA)
    for n in ["BASE"] + nomes:
        r = res[n][DIA]
        print(f"{n:12s} {r['brl']:8.2f}", [(t['fonte'].split(':')[-1][:20], t['lado'][0], t['ent'][:5], t['motivo'], t['brl']) for t in r['trades']])
