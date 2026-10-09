"""Ciclo 3 -> 4, dia 2025-07-11 (WIN M15, ef 0,061 = ruim; v3 = -R$208,04; v1 = -R$102,00).

O DIA: gap de baixa de -625 pts (0,30 ATRd, no limiar de 0,3 da F2 do gap), a 1a vela abre 138.100 e fecha 138.100 (martelo: minima
137.535). Cai ate 137.135 as 10:45, spike de +1.000 pts as 11:00 (138.150), e fica em rotacao 137.0k-137.8k ate o fim (ef 0,06).
v3: F2 `gap de baixa preenche` COMPRA 09:15 -> stop 10:15 (-R$102): o gap nao preencheu e o dia foi de baixa; enquanto a compra
estava aberta, a F2 `falha da maxima matinal` (venda, 10:00, isolada +R$60) ficou sem vez;
F1 venda 12:45 (rompimento da minima da 1a hora, 8a barra consecutiva abaixo dela desde 10:15) liberada pelo A2 -> stop 15:22 (-R$106,04).

`APLICA[id](cfg)` monta a candidata sobre o robo_v3 (Cfg de ciclo3/ag2_lib.py). Regras puras (so o passado do instante da decisao).
"""
from regras import c3_2025_06_20 as g

F_GAP = "2025_08_01:F2 gap de baixa preenche (compra)"


def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


def f2_gap_exige_vela_de_alta(ctx):
    """AJUSTE da FAZER `F2 gap de baixa preenche`: so compra o preenchimento se a 1a vela FECHOU ACIMA da abertura (compradores
    ja aparecendo). 2025-07-11: a 1a vela fechou igual a abertura (martelo sem corpo) e a compra foi stopada em 1h."""
    h = ctx.hoje
    if len(h) != 1: return None
    gap = float(h.open.iloc[0]) - float(ctx.diario.close.iloc[-1])
    if -0.8 * ctx.atrd < gap < -0.3 * ctx.atrd and float(h.close.iloc[-1]) > float(h.open.iloc[0]):
        e = float(h.close.iloc[-1])
        return dict(lado="compra", stop=e - 500, alvo=float(ctx.diario.close.iloc[-1]), preco=e)


def f2_gap_limiar_estrito(ctx):
    """AJUSTE da F2 do gap: faixa de gap 0,35-0,8 ATRd (em vez de 0,3-0,8): o gap de 0,30 ATRd esta no limiar e e ruido."""
    h = ctx.hoje
    if len(h) != 1: return None
    gap = float(h.open.iloc[0]) - float(ctx.diario.close.iloc[-1])
    if -0.8 * ctx.atrd < gap < -0.35 * ctx.atrd:
        e = float(h.close.iloc[-1])
        return dict(lado="compra", stop=e - 500, alvo=float(ctx.diario.close.iloc[-1]), preco=e)


def n_veto_venda_rotacao_tarde(ctx):
    """NAO_FAZER: nao vender (qualquer gatilho) depois das 12:00 com o dia em rotacao: eficiencia do dia < 0,15 e amplitude < 0,8 ATRd.
    Entrada de continuacao sem perna para continuar."""
    h = ctx.hoje
    if len(h) < 5 or _hm(ctx) < 12 * 60: return None
    if g._efic(ctx) < 0.15 and g._ampl(ctx) < 0.8:
        c = float(h.close.iloc[-1]); return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def n_veto_venda_rompimento_repetido(ctx):
    """NAO_FAZER: nao vender o rompimento da minima da 1a hora se >= 6 dos 12 fechamentos anteriores ja estavam abaixo do nivel
    (o 'rompimento' e a volta ao mesmo lugar). 2025-07-11 12:45: 8 velas abaixo desde 10:15."""
    h = ctx.hoje
    if len(h) < 8: return None
    lo = float(g._p1(ctx).low.min())
    if float(h.close.iloc[-1]) < lo and int((h.close.iloc[-13:-1] < lo).sum()) >= 6:
        c = float(h.close.iloc[-1]); return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def n_veto_compra_gap_baixa_abaixo_da_abertura(ctx):
    """NAO_FAZER: em dia de gap de baixa >= 0,25 ATRd, nao comprar (fade do gap, queda de suporte etc.) ate as 10:30 enquanto o
    fechamento esta abaixo da abertura do dia: o gap so esta 'preenchendo' quando o preco volta acima da abertura. 2025-07-11:
    gap -0,30 ATRd; as compras de 09:15, 09:30, 09:45, 10:00 e 10:00 (F5) fecharam abaixo da abertura e todas foram stopadas."""
    h = ctx.hoje
    if _hm(ctx) > 10 * 60 + 30: return None
    gap = float(h.open.iloc[0]) - float(ctx.diario.close.iloc[-1])
    if gap <= -0.25 * ctx.atrd and float(h.close.iloc[-1]) <= float(h.open.iloc[0]):
        c = float(h.close.iloc[-1]); return dict(lado="compra", stop=c - 120, alvo=c + 240, contratos=1)


def _sub_fz(fn):
    def ap(cfg):
        assert any(n == F_GAP for n, _, _ in cfg.fz)
        cfg.fz = [(n, fn, gg) if n == F_GAP else (n, r, gg) for n, r, gg in cfg.fz]
    return ap


def _add_nf(nome, fn):
    def ap(cfg): cfg.nf = cfg.nf + [(nome, fn, None)]
    return ap


def _conf(modo):
    def ap(cfg): cfg.conflito = modo
    return ap


APLICA = {
    "F2G": _sub_fz(f2_gap_exige_vela_de_alta),
    "F2L": _sub_fz(f2_gap_limiar_estrito),
    "NR": _add_nf("c3:NR venda_rotacao_tarde", n_veto_venda_rotacao_tarde),
    "N4T": _add_nf("c3:N4T venda_rompimento_repetido", n_veto_venda_rompimento_repetido),
    "NG": _add_nf("c3:NG compra_gap_baixa_sob_abertura", n_veto_compra_gap_baixa_abaixo_da_abertura),
    "CFd": _conf("dia"),
    "CFc": _conf("continuacao"),
}


def _ng(gap_min, hm_max, lado_bloq="compra"):
    """Fabrica de NG: veta `lado_bloq` ate `hm_max` (minutos) em dia de gap contra esse lado (>= gap_min ATRd) enquanto o fechamento
    esta do lado ruim da abertura. lado_bloq='compra' = gap de baixa; 'venda' = gap de alta (espelho)."""
    def f(ctx):
        h = ctx.hoje
        if _hm(ctx) > hm_max: return None
        gap = (float(h.open.iloc[0]) - float(ctx.diario.close.iloc[-1])) / ctx.atrd
        c = float(h.close.iloc[-1]); o = float(h.open.iloc[0])
        if lado_bloq == "compra" and gap <= -gap_min and c <= o:
            return dict(lado="compra", stop=c - 120, alvo=c + 240, contratos=1)
        if lado_bloq == "venda" and gap >= gap_min and c >= o:
            return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)
    return f


# vizinhanca de NG: id "NG_<gap>_<hora_max_em_hhmm>" e espelho "NGs_<gap>_<hhmm>"
for _g in (0.15, 0.25, 0.35, 0.5):
    for _h in (1000, 1030, 1100):
        _hm_ = (_h // 100) * 60 + _h % 100
        APLICA[f"NG_{_g}_{_h}"] = _add_nf(f"c3:NG_{_g}_{_h}", _ng(_g, _hm_, "compra"))
        APLICA[f"NGs_{_g}_{_h}"] = _add_nf(f"c3:NGs_{_g}_{_h}", _ng(_g, _hm_, "venda"))


def _ap_dois(a, b):
    def ap(cfg): a(cfg); b(cfg)
    return ap


APLICA["NGb"] = _ap_dois(APLICA["NG_0.25_1030"], APLICA["NGs_0.25_1030"])
