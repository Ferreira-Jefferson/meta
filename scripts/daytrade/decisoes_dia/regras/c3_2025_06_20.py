"""Ciclo 3 -> 4, dia 2025-06-20 (WIN M15, ef 0,177 = intermediario; v3 = -R$39,16; v1 = +R$61,56).

O DIA: abre 141.580 (gap -95 sobre 141.675), cai quase sem pausa ate 139.305 (12:15): 2.035 pts do fecho da 1a vela (09:15).
v3: F2 vende a falha da maxima as 10:00 (alvo de 1,5 ATR em 10:52: +R$61,56, quando o preco ainda tinha 770 pts ate o fundo);
as vendas de rompimento das 10:45-11:15 (isoladas +R$173 a +R$180, alvo em 12:19) foram vetadas por A2-raso e N2-rotacao;
F1 vende o rompimento da minima da 1a hora as 12:15 NO FUNDO (139.425; o dia ja andou 1,12 ATRd; 7 das 8 velas anteriores
fecharam abaixo do nivel) -> stop em 13:04 (-R$108,71). F3 +R$8 no fim.

Cada FAZER/NAO_FAZER devolve o sinal; `APLICA[id](cfg)` monta a candidata sobre o robo_v3 (Cfg de ciclo3/ag2_lib.py).
`python ciclo3/ag2_roda_0620.py` mede todas nos 70 dias (R$/dia reponderado).
Regras puras: so usam o passado do instante da decisao.
"""
import pandas as pd

H1 = pd.Timedelta(hours=1)
V_STOP_CURTO = "2023_08_21:vende_rompimento_stop_curto"


def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


def _p1(ctx):
    h = ctx.hoje
    return h[h.index < h.index[0] + H1]


def _ampl(ctx): return float(ctx.hoje.high.max() - ctx.hoje.low.min()) / ctx.atrd


def _efic(ctx):
    h = ctx.hoje; s = float((h.high - h.low).sum())
    return abs(float(h.close.iloc[-1] - h.open.iloc[0])) / s if s > 0 else 0.0


def _desloc(ctx):
    h = ctx.hoje
    return float(h.close.iloc[-1] - h.open.iloc[0]) / ctx.atrd


def _ord(ctx, lado, k=1.5, alvo_r=None):
    p = float(ctx.hoje.close.iloc[-1]); r = min(k * ctx.atr15, 600.0); s = 1 if lado == "compra" else -1
    return dict(lado=lado, preco=p, stop=p - s * r, alvo=None if alvo_r is None else p + s * alvo_r * r, contratos=1)


# ============================================================ NAO_FAZER / AJUSTES DO VETO A2 (versao condicional)
def _raso(ctx):
    h = ctx.hoje
    lo = float(_p1(ctx).low.min()); c = float(h.close.iloc[-1])
    return lo - 0.5 * ctx.atr15 < c < lo


def _abaixo(ctx):
    return float(ctx.hoje.close.iloc[-1]) < float(_p1(ctx).low.min())


def _veto_venda(ctx):
    c = float(ctx.hoje.close.iloc[-1])
    return dict(lado="venda", stop=c + 120, alvo=c - 240, contratos=1)


def a2f_veto_raso_ou_velho(ctx):
    """AJUSTE do A2 (veto da venda abaixo da minima da 1a hora; A2 da v2 = so veta o rompimento RASO). Acrescenta: veta tambem o
    rompimento VELHO, quando >= 3 das 8 velas anteriores ja fecharam abaixo da minima da 1a hora (o preco esta morando abaixo do
    nivel, nao rompendo). Estado observavel na vela. 2025-06-20 12:15: 7 de 8 velas abaixo -> vetado (v1 +61)."""
    h = ctx.hoje
    if len(h) < 5: return None
    lo = float(_p1(ctx).low.min()); c = float(h.close.iloc[-1])
    if not c < lo: return None
    if lo - 0.5 * ctx.atr15 < c or int((h.close.iloc[-9:-1] < lo).sum()) >= 3:
        return _veto_venda(ctx)


def a2t_veto_raso_ou_tarde(ctx):
    """AJUSTE do A2: veta o rompimento raso OU qualquer rompimento da minima da 1a hora a partir das 12:00 (rompimento tardio
    de dia ja desenvolvido)."""
    h = ctx.hoje
    if len(h) < 5 or not _abaixo(ctx): return None
    if _raso(ctx) or _hm(ctx) >= 12 * 60: return _veto_venda(ctx)


def a2e_veto_raso_ou_extenso(ctx):
    """AJUSTE do A2: veta o rompimento raso OU o rompimento com o dia ja >= 1,0 ATRd de amplitude (perna consumida)."""
    h = ctx.hoje
    if len(h) < 5 or not _abaixo(ctx): return None
    if _raso(ctx) or _ampl(ctx) >= 1.0: return _veto_venda(ctx)


def a2v_veto_raso_ou_sem_volume_tarde(ctx):
    """AJUSTE do A2: veta o rompimento raso OU o rompimento a partir das 11:30 em vela de volume abaixo da media do dia."""
    h = ctx.hoje
    if len(h) < 5 or not _abaixo(ctx): return None
    if _raso(ctx) or (_hm(ctx) >= 11 * 60 + 30 and float(h.vol.iloc[-1]) < float(h.vol.mean())): return _veto_venda(ctx)


# ============================================================ FAZER novos (continuacao / entrada cedo, a favor da perna)
def e1_continuacao_vela1(ctx):
    """FAZER (continuacao cedo, 09:15): a 1a vela M15 tem faixa >= 1,5 ATR15 e fecha no quarto extremo da faixa (venda: fecho no
    quarto inferior e vela de baixa; compra: o espelho) -> entra a favor, limitada no fecho, stop 1,5 ATR15 (<=600), alvo 2R.
    2025-06-20: faixa 505 (2,0 ATR15), fecho a 20% da minima -> vende 141.340."""
    h = ctx.hoje
    if len(h) != 1: return None
    u = h.iloc[-1]; rng = float(u.high - u.low)
    if rng < 1.5 * ctx.atr15: return None
    pos = float(u.close - u.low) / rng
    if pos <= 0.25 and u.close < u.open: return _ord(ctx, "venda", 1.5, 2.0)
    if pos >= 0.75 and u.close > u.open: return _ord(ctx, "compra", 1.5, 2.0)


def e1s_continuacao_vela1_sem_alvo(ctx):
    """Igual a e1, sem alvo (sai no stop ou no fim) - a versao 'deixa correr'."""
    s = e1_continuacao_vela1(ctx)
    if s: s["alvo"] = None
    return s


def e2_rompe_extremo_30min(ctx):
    """FAZER (continuacao cedo, 09:45): a vela que acabou de fechar rompeu o extremo das 2 primeiras velas na direcao do
    deslocamento desde a abertura (|desloc| >= 0,3 ATRd), com corpo >= 60% da faixa. Limitada no fecho, stop 1,5 ATR15, alvo 2R.
    2025-06-20 09:45: a vela 09:30 fecha 140.390 < 140.725 (minima das 2 primeiras), desloc -0,39 ATRd -> vende."""
    h = ctx.hoje
    if len(h) != 3: return None
    u = h.iloc[-1]; rng = float(u.high - u.low)
    if rng <= 0 or abs(float(u.close - u.open)) < 0.6 * rng: return None
    d = _desloc(ctx)
    if d <= -0.3 and u.close < float(h.low.iloc[:2].min()): return _ord(ctx, "venda", 1.5, 2.0)
    if d >= 0.3 and u.close > float(h.high.iloc[:2].max()): return _ord(ctx, "compra", 1.5, 2.0)


def e3_pullback_curto_na_perna(ctx):
    """FAZER (continuacao, 09:30-10:30): perna do dia em curso (|desloc| >= 0,5 ATRd da abertura, eficiencia >= 0,4), a vela
    anterior recuou (cor oposta) e a atual retoma na direcao da perna fechando alem da extrema da anterior -> entra a favor;
    stop 1,5 ATR15, alvo 2R."""
    h = ctx.hoje
    if len(h) < 3 or not (9 * 60 + 30 <= _hm(ctx) <= 10 * 60 + 30): return None
    d = _desloc(ctx)
    if abs(d) < 0.5 or _efic(ctx) < 0.4: return None
    u, a = h.iloc[-1], h.iloc[-2]
    if d < 0 and a.close > a.open and u.close < u.open and u.close < a.low: return _ord(ctx, "venda", 1.5, 2.0)
    if d > 0 and a.close < a.open and u.close > u.open and u.close > a.high: return _ord(ctx, "compra", 1.5, 2.0)


# ============================================================ gestao adaptativa (estado -> alvo)
def post_alvo_estendido_na_perna(n, s, g, ctx):
    """GESTAO: se a entrada e a favor da perna do dia (|desloc| >= 0,5 ATRd na mesma direcao) e o dia e eficiente (>= 0,4), o alvo
    vai a 2x a distancia original; senao fica como esta. (2025-06-20 10:00: F2 vendeu com desloc -0,56 e efic 0,53.)"""
    if s.get("alvo") is None: return s, g
    d = _desloc(ctx); sg = 1 if s["lado"] == "compra" else -1
    if sg * d >= 0.5 and _efic(ctx) >= 0.4:
        s = dict(s); p = float(s.get("preco", ctx.hoje.close.iloc[-1])); s["alvo"] = p + 2.0 * (float(s["alvo"]) - p)
    return s, g


# ============================================================ aplicacao sobre o robo_v3 (cfg = ag2_lib.Cfg2)
def _sub_veto(cfg, fn):
    assert any(n == V_STOP_CURTO for n, _, _ in cfg.nf)
    cfg.nf = [(n, fn, g) if n == V_STOP_CURTO else (n, r, g) for n, r, g in cfg.nf]


def _add_fz(nome, fn):
    def ap(cfg): cfg.fz = cfg.fz + [(nome, fn, None)]
    return ap


def _add_fz_front(nome, fn):
    def ap(cfg): cfg.fz = [(nome, fn, None)] + cfg.fz
    return ap


def _ap_post(f):
    def ap(cfg): cfg.post = cfg.post + [f]
    return ap


APLICA = {
    "A2F": lambda cfg: _sub_veto(cfg, a2f_veto_raso_ou_velho),
    "A2T": lambda cfg: _sub_veto(cfg, a2t_veto_raso_ou_tarde),
    "A2E": lambda cfg: _sub_veto(cfg, a2e_veto_raso_ou_extenso),
    "A2V": lambda cfg: _sub_veto(cfg, a2v_veto_raso_ou_sem_volume_tarde),
    "E1": _add_fz_front("c3:E1 continuacao_vela1", e1_continuacao_vela1),
    "E1s": _add_fz_front("c3:E1s continuacao_vela1_sem_alvo", e1s_continuacao_vela1_sem_alvo),
    "E2": _add_fz_front("c3:E2 rompe_extremo_30min", e2_rompe_extremo_30min),
    "E3": _add_fz("c3:E3 pullback_curto_na_perna", e3_pullback_curto_na_perna),
    "G1": _ap_post(post_alvo_estendido_na_perna),
}


def _g1(dmin, emin, mult):
    def post(n, s, g, ctx):
        if s.get("alvo") is None: return s, g
        d = _desloc(ctx); sg = 1 if s["lado"] == "compra" else -1
        if sg * d >= dmin and _efic(ctx) >= emin:
            s = dict(s); p = float(s.get("preco", ctx.hoje.close.iloc[-1])); s["alvo"] = p + mult * (float(s["alvo"]) - p)
        return s, g
    return post


# vizinhanca de G1 (desloc minimo, eficiencia minima, multiplicador do alvo): id "G1_<d>_<e>_<m>"
for _d in (0.3, 0.5, 0.7):
    for _e in (0.3, 0.4, 0.5):
        for _m in (1.5, 2.0, 3.0):
            APLICA[f"G1_{_d}_{_e}_{_m}"] = _ap_post(_g1(_d, _e, _m))
