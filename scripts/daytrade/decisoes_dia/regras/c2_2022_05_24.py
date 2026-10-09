"""Ciclo 2 - dia 2022-05-24 (WIN M15, ruim, ef 0,094): abertura 110.200 (gap -1.205 pts = -0,48 ATRd sobre 111.405),
faixa 109.125-110.640 ate as 16:00, e so depois sobe ate 111.470 (fecha o gap no fim). O robo v2 fez 3 stops (-R$283,36).
Regras puras: so usam o passado do instante da decisao. Execucao e risco como em INSTRUCOES.md.
Tudo aqui sao NOVAS funcoes; nenhum r_*.py foi alterado. `PROPOSTAS` diz como cada uma se encaixa no robo v2."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from regras import r_2024_06_18 as r18, r_2022_11_16 as r16

CAP = 590.0
GAP = "2024_06_18:gap_fade_fechamento"
V_SEMVOL = "2024_06_18:rompimento_sem_volume"
V_SUPORTE = "2022_11_16:compra suporte minima de ontem"


def _ema(s, n): return s.ewm(span=n, adjust=False).mean()


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).cumsum().iloc[-1] / h.vol.cumsum().iloc[-1])


def _hr(ctx): return ctx.t.hour + ctx.t.minute / 60


def _ord(ctx, lado, stop_atr, alvo_atr):
    p = float(ctx.hoje.close.iloc[-1]); a = ctx.atr15
    stop_atr = min(stop_atr, CAP / a); s = 1 if lado == "compra" else -1
    return dict(lado=lado, preco=p, stop=p - s * stop_atr * a, alvo=(p + s * alvo_atr * a) if alvo_atr else None, contratos=1)


def _ef(h): return abs(h.close.iloc[-1] - h.open.iloc[0]) / float((h.high - h.low).sum())


# ---------------- gestao adaptativa (usada por 3 das FAZER) ----------------
def gerir_adaptativo(ctx, pos):
    """Trailing que le o estado do dia. Nao mexe no stop ate o trade andar 1 ATR15 a favor (ai vai para a entrada = zero a zero);
    depois segue o melhor fechamento desde a entrada com folga k*ATR15, onde k=1,5 se o dia ainda e de rotacao (eficiencia parcial < 0,15:
    perna curta, protege cedo) e k=2,5 se o dia ja e direcional (perna forte: deixa respirar). Sem alvo: a saida e o stop ou o fim."""
    h = ctx.hoje; a = ctx.atr15; desde = h[h.index >= pos["t_ent"].floor("15min")]
    k = 1.5 if _ef(h) < 0.15 else 2.5
    if pos["lado"] == "compra":
        melhor = desde.close.max()
        if melhor - pos["preco"] < a: return None
        return max(pos["preco"], melhor - k * a)
    melhor = desde.close.min()
    if pos["preco"] - melhor < a: return None
    return min(pos["preco"], melhor + k * a)


def _sem_alvo(s):
    if s:
        s = dict(s); s["alvo"] = None
    return s


# =============== FAZER (ordenadas pelo retorno no dia) ===============
def f_reconquista_vwap_gap_baixa(ctx):
    """FAZER (natureza: recuperacao de gap com reconquista de valor). Em dia que abriu >= 0,3 ATRd abaixo do fechamento de ontem, o preco ficou
    abaixo do VWAP em >= 7 das 8 velas anteriores e a vela que acabou de fechar fecha acima do VWAP: compra. Stop 1,5 ATR15, SEM alvo, gestao adaptativa.
    Condicao: gap de baixa sendo preenchido por mudanca de lado do valor. 11:00-15:00. Dia: compra 110.120 (12:45) -> fim 111.470 = +R$268,00. Ajustada ao dia
    (1 ocorrencia no dia; fundamento geral: gap tende a fechar, mas o projeto ja viu gap-fade nao replicar)."""
    h = ctx.hoje
    if len(h) < 10 or not (11 <= ctx.t.hour < 15): return None
    ont = ctx.diario.iloc[-1]
    if h.open.iloc[0] >= ont.close - 0.3 * ctx.atrd: return None
    tp = (h.high + h.low + h.close) / 3; vw = (tp * h.vol).cumsum() / h.vol.cumsum()
    if (h.close < vw).iloc[-9:-1].sum() >= 7 and h.close.iloc[-1] > vw.iloc[-1]:
        return _sem_alvo(_ord(ctx, "compra", 1.5, 2.0))


def f_expansao_apos_compressao(ctx):
    """FAZER (natureza: rompimento de compressao, os dois lados). Vela de corpo >= 1,5 ATR15 e >= 70% da sua faixa, depois de 6 velas cuja faixa media
    e <= 1 ATR15: segue a direcao da vela. Stop 1,5 ATR15, SEM alvo, gestao adaptativa. Condicao: energia acumulada em faixa estreita liberada
    por uma vela de expansao. 10:00-15:00. Dia: mesma entrada 12:45 (compra 110.120) = +R$268,00. Provavelmente geral (compressao-expansao e
    fundamento classico), 1 ocorrencia no dia."""
    h = ctx.hoje
    if len(h) < 10 or not (10 <= ctx.t.hour < 15): return None
    u = h.iloc[-1]; a = ctx.atr15; ant = h.iloc[-7:-1]
    if (ant.high - ant.low).mean() > 1.0 * a: return None
    b = u.close - u.open
    if abs(b) >= 1.5 * a and abs(b) >= 0.7 * (u.high - u.low):
        return _sem_alvo(_ord(ctx, "compra" if b > 0 else "venda", 1.5, 2.0))


def f_reversao_fundo_volume_seco(ctx):
    """FAZER (natureza: exaustao vendedora no fundo da faixa). Entre 11:00 e 15:00, a vela chega a 0,35 ATR15 da minima do dia (ate ali), com volume
    < 80% da media das 8 anteriores (venda sem pressa), fecha em alta no terco superior: compra. Stop 1,5 ATR15, alvo 2 ATR15.
    Dia: 12:30 compra 109.470 -> alvo = +R$189,57. Ajustada ao dia (volume seco no fundo ocorreu 1 vez)."""
    h = ctx.hoje
    if len(h) < 10 or not (11 <= ctx.t.hour < 15): return None
    u = h.iloc[-1]; a = ctx.atr15; lo = h.low.iloc[:-1].min()
    if u.low <= lo + 0.35 * a and u.vol < 0.8 * h.vol.iloc[-9:-1].mean() and u.close > u.open and u.close > u.low + 0.6 * (u.high - u.low):
        return _ord(ctx, "compra", 1.5, 2.0)


def f_segue_maxima_do_dia_tarde(ctx):
    """FAZER (natureza: rompimento da maxima do dia na tarde, acima do VWAP). Entre 15:30 e 17:00, fechamento acima da maxima do dia ate a vela anterior
    e acima do VWAP: compra. Stop 1,5 ATR15, SEM alvo, gestao adaptativa. Condicao: a faixa do dia e resolvida para cima no fim. Dia: 16:30 compra
    110.670 -> fim 111.470 = +R$158,00 (no robo v2 nao existe: ele ja gastou os 3 ops as 14:00). Ajustada ao dia; depois das 15h os
    sinais pioram segundo o projeto."""
    h = ctx.hoje
    if len(h) < 14 or not (15.5 <= _hr(ctx) < 17): return None
    u = h.iloc[-1]
    if u.close > h.high.iloc[:-1].max() and u.close > _vwap(h):
        return _sem_alvo(_ord(ctx, "compra", 1.5, 2.0))


def f_gap_fade_alvo_na_abertura(ctx):
    """AJUSTE de 2024_06_18:gap_fade_fechamento. Mesmo gatilho e stop, alvo na ABERTURA do dia (fecha so ~metade do gap) em vez do fechamento de
    ontem. Condicao: gap que so enche em parte. Dia: compra 109.890 -> alvo 110.200 = +R$60,00 (o original, com alvo 111.405, stopou -R$49).
    Ajustada ao dia: o conjunto de 50 dias piora (ver tabela)."""
    s = r18.f_gap_fade_fechamento(ctx)
    if not s: return None
    o = float(ctx.hoje.open.iloc[0])
    if abs(o - s["preco"]) < 150: return None
    s = dict(s); s["alvo"] = o
    return s


# =============== NAO FAZER (vetos; cada um descreve uma condicao de mercado) ===============
def n_vender_continuacao_de_gap_grande(ctx):
    """NAO FAZER: vender depois das 10:30 em dia que abriu >= 0,3 ATRd abaixo do fechamento de ontem. Armadilha: o gap grande rotaciona/preenche em vez de
    continuar; a venda a favor do gap e pisada. Dia: -R$240 (2 stops). Ajustada ao dia."""
    h = ctx.hoje
    if len(h) < 8: return None
    if (h.open.iloc[0] - ctx.diario.close.iloc[-1]) / ctx.atrd <= -0.3 and 10.5 <= _hr(ctx) < 15:
        return _ord(ctx, "venda", 1.5, 3.0)


def n_vender_pullback_em_media_plana(ctx):
    """NAO FAZER: vender com a EMA20 M15 plana (|inclinacao em 4 velas| < 0,15 ATR15) e o preco a < 0,5 ATR15 dela, 10:00-15:00. Armadilha: recuo a
    media sem tendencia; a media nao e resistencia, e so o meio da rotacao. Dia: -R$120. Ajustada ao dia."""
    h = ctx.hoje
    if len(h) < 8 or not (10 <= ctx.t.hour < 15): return None
    e = _ema(ctx.m15.close, 20)
    if abs(e.iloc[-1] - e.iloc[-5]) / ctx.atr15 < 0.15 and abs(h.close.iloc[-1] - e.iloc[-1]) < 0.5 * ctx.atr15:
        return _ord(ctx, "venda", 1.5, 3.0)


def n_vender_dia_sem_direcao(ctx):
    """NAO FAZER: vender depois das 11:00 quando a eficiencia parcial do dia (|fecha-abre| / soma das faixas M15) < 0,05: o preco voltou a abertura,
    dia sem direcao. Armadilha: rompimento para baixo em rotacao pura volta. Dia: -R$120. Ajustada ao dia."""
    h = ctx.hoje
    if len(h) < 8 or not (11 <= ctx.t.hour < 15): return None
    if _ef(h) < 0.05: return _ord(ctx, "venda", 1.5, 3.0)


def n_vender_vela_de_indecisao(ctx):
    """NAO FAZER: vender 10:30-15:00 quando a vela do sinal tem corpo < 0,25 ATR15 (doji/indecisao) e fecha a < 0,5 ATR15 da minima das 4 anteriores.
    Armadilha: rompimento feito por vela sem conviccao. Dia: -R$120. Ajustada ao dia."""
    h = ctx.hoje; u = h.iloc[-1]
    if len(h) < 4 or not (10.5 <= _hr(ctx) < 15): return None
    if abs(u.close - u.open) < 0.25 * ctx.atr15 and u.close < h.low.iloc[-5:-1].min() + 0.5 * ctx.atr15:
        return _ord(ctx, "venda", 1.5, 3.0)


def n_vender_colado_na_minima_do_dia(ctx):
    """NAO FAZER: vender 11:00-15:00 com o fechamento a <= 0,8 ATR15 da minima do dia e o dia abaixo da abertura. Armadilha: vender onde o dia ja
    esgotou o movimento; o suporte do dia e testado e o preco devolve. Dia: -R$120. Ajustada ao dia."""
    h = ctx.hoje
    if len(h) < 8 or not (11 <= ctx.t.hour < 15): return None
    if h.close.iloc[-1] <= h.low.min() + 0.8 * ctx.atr15 and h.close.iloc[-1] < h.open.iloc[0]:
        return _ord(ctx, "venda", 1.5, 3.0)


# =============== AJUSTES de vetos existentes (novas versoes das funcoes) ===============
def n_rompimento_sem_volume_corpo_forte(ctx):
    """AJUSTE de 2024_06_18:rompimento_sem_volume: igual ao original, mas NAO veta se a vela tem corpo >= 1,5 ATR15 (vela de expansao confirma por si so).
    Dia: libera a compra das 12:45 (expansao de +650 pts) que o veto original bloqueou."""
    s = r18.n_rompimento_sem_volume(ctx)
    u = ctx.hoje.iloc[-1]
    if s and abs(u.close - u.open) >= 1.5 * ctx.atr15: return None
    return s


def n_compra_suporte_ontem_abaixo_vwap(ctx):
    """AJUSTE de 2022_11_16:compra suporte minima de ontem: so veta se o preco esta ABAIXO do VWAP (suporte que vira resistencia so quando o valor do dia
    esta acima do preco). Dia: libera a compra das 12:45 (fechamento 110.120 acima do VWAP)."""
    s = r16.n_compra_suporte_ontem(ctx)
    if s and ctx.hoje.close.iloc[-1] > _vwap(ctx.hoje): return None
    return s


FAZER = [("reconquista VWAP em gap de baixa (adaptativa)", f_reconquista_vwap_gap_baixa, gerir_adaptativo),
         ("expansao apos compressao (adaptativa)", f_expansao_apos_compressao, gerir_adaptativo),
         ("reversao no fundo com volume seco", f_reversao_fundo_volume_seco, None),
         ("rompe maxima do dia na tarde (adaptativa)", f_segue_maxima_do_dia_tarde, gerir_adaptativo),
         ("gap-fade alvo na abertura (ajuste)", f_gap_fade_alvo_na_abertura, None)]
NAO_FAZER = [("vender continuacao de gap grande", n_vender_continuacao_de_gap_grande, None),
             ("vender pullback em media plana", n_vender_pullback_em_media_plana, None),
             ("vender em dia sem direcao", n_vender_dia_sem_direcao, None),
             ("vender vela de indecisao", n_vender_vela_de_indecisao, None),
             ("vender colado na minima do dia", n_vender_colado_na_minima_do_dia, None)]

# Como cada proposta se encaixa no robo v2 (sub = troca FAZER; sub_veto = troca veto; add_* = acrescenta ao FIM).
_AJ = {V_SEMVOL: n_rompimento_sem_volume_corpo_forte, V_SUPORTE: n_compra_suporte_ontem_abaixo_vwap}
PROPOSTAS = {
    "F1 reconquista_vwap": dict(add_fazer=[(f_reconquista_vwap_gap_baixa, gerir_adaptativo)]),
    "F2 expansao_compressao": dict(add_fazer=[(f_expansao_apos_compressao, gerir_adaptativo)]),
    "F3 reversao_fundo_vol_seco": dict(add_fazer=[(f_reversao_fundo_volume_seco, None)]),
    "F4 maxima_do_dia_tarde": dict(add_fazer=[(f_segue_maxima_do_dia_tarde, gerir_adaptativo)]),
    "F5 gap_fade_alvo_abertura": dict(sub={GAP: f_gap_fade_alvo_na_abertura}),
    "N1 gap_grande": dict(add_veto=[n_vender_continuacao_de_gap_grande]),
    "N2 pullback_media_plana": dict(add_veto=[n_vender_pullback_em_media_plana]),
    "N3 dia_sem_direcao": dict(add_veto=[n_vender_dia_sem_direcao]),
    "N4 vela_indecisao": dict(add_veto=[n_vender_vela_de_indecisao]),
    "N5 colado_minima": dict(add_veto=[n_vender_colado_na_minima_do_dia]),
    "A1 veto_semvol_corpo_forte": dict(sub_veto={V_SEMVOL: n_rompimento_sem_volume_corpo_forte}),
    "A2 veto_suporte_abaixo_vwap": dict(sub_veto={V_SUPORTE: n_compra_suporte_ontem_abaixo_vwap}),
    "A1+A2+F1+F2": dict(sub_veto=_AJ, add_fazer=[(f_reconquista_vwap_gap_baixa, gerir_adaptativo),
                                                  (f_expansao_apos_compressao, gerir_adaptativo)]),
    "A1+A2+F1+F2+F4": dict(sub_veto=_AJ, add_fazer=[(f_reconquista_vwap_gap_baixa, gerir_adaptativo),
                                                     (f_expansao_apos_compressao, gerir_adaptativo),
                                                     (f_segue_maxima_do_dia_tarde, gerir_adaptativo)]),
}

if __name__ == "__main__":
    import base
    DIA = "2022-05-24"
    for tipo, lst in (("FAZER", FAZER), ("NAO_FAZER", NAO_FAZER)):
        for n, r, g in lst:
            res = base.resumo(base.simula_dia(DIA, r, g))
            print(tipo, n, "R$", res["brl"], "ops", res["ops"], [(x["sinal"], x["motivo"], x["brl"]) for x in res["lista"]])
