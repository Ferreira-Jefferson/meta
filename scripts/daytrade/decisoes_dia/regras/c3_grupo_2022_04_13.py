"""Ciclo 3 - GRUPO (dias 2022-04-13 e 2022-05-17, negativos do robo_v3; ambos de ROTACAO, ef 0,024 e 0,033).
Pecas comuns aos dois dias: auxiliares puros, aplicadores de proposta sobre a `Cfg` do v3 (ciclo3/cfg3.py) e o avaliador de 70 dias.
Regras puras: so usam o passado do instante da decisao. Nada existente e editado.

Cada proposta e uma funcao `ap_<id>(cfg)` que altera a Cfg (cfg.fz / cfg.nf / cfg.prio / cfg.post), registrada em `CAND`.
`python -m regras.c3_grupo_2022_04_13 [ids...]` avalia (v3 + cada id isolada) nos 70 dias de dias_usados.json.
"""
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
import numpy as np
import pandas as pd

TETO = 590.0
IDS_V3 = ["C8", "C7", "C6", "C4"]


# ----------------------------------------------------------------------------- auxiliares
def hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


def ef_hoje(ctx):
    """eficiencia do dia ate agora: |fecho - abertura| / soma das faixas M15."""
    h = ctx.hoje
    s = float((h.high - h.low).sum())
    return abs(float(h.close.iloc[-1] - h.open.iloc[0])) / s if s > 0 else 0.0


def amp_atrd(ctx):
    return float(ctx.hoje.high.max() - ctx.hoje.low.min()) / ctx.atrd


def pos_na_faixa(ctx):
    """posicao do fecho dentro da faixa do dia ate agora: 0 = minima, 1 = maxima (None se a faixa for < 1 ATR15)."""
    h = ctx.hoje
    hi, lo = float(h.high.max()), float(h.low.min())
    if hi - lo < ctx.atr15: return None
    return (float(h.close.iloc[-1]) - lo) / (hi - lo)


def vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def ordem(ctx, lado, stop_pts, alvo_pts, preco=None):
    p = float(ctx.hoje.close.iloc[-1]) if preco is None else preco
    s = 1 if lado == "compra" else -1
    r = min(stop_pts, TETO)
    return dict(lado=lado, preco=p, stop=p - s * r, alvo=(p + s * alvo_pts) if alvo_pts else None, contratos=1)


def ambos(nome, fn_lado):
    """Veto de um lado so sinaliza esse lado; devolve (compra, venda) a partir de fn_lado(ctx, lado) -> bool."""
    def c(ctx): return ordem(ctx, "compra", 600, 600) if fn_lado(ctx, "compra") else None
    def v(ctx): return ordem(ctx, "venda", 600, 600) if fn_lado(ctx, "venda") else None
    return [(nome + " (compra)", c, None), (nome + " (venda)", v, None)]


# ----------------------------------------------------------------------------- gestao (post) -------------------------------------
def _comb(lado, a, b):
    xs = [x for x in (a, b) if x is not None]
    if not xs: return None
    return max(xs) if lado == "compra" else min(xs)


def post_alvo_curto(k=0.5, ef_max=0.10):
    """Em dia de rotacao (ef do dia ate agora < ef_max) o alvo vale k x a distancia original (alvo mais perto)."""
    def f(n, s, g, ctx):
        if s.get("alvo") is None or ef_hoje(ctx) >= ef_max: return s, g
        s = dict(s); p = float(s.get("preco", ctx.hoje.close.iloc[-1]))
        s["alvo"] = p + k * (float(s["alvo"]) - p)
        return s, g
    return f


def post_alvo_R(k_r=0.5, ef_max=0.10):
    """Em rotacao (ef do dia ate agora < ef_max) o alvo passa a ser k_r x R (R = distancia ao stop), se isso for MAIS PERTO que o original."""
    def f(n, s, g, ctx):
        if s.get("alvo") is None or ef_hoje(ctx) >= ef_max: return s, g
        s = dict(s); p = float(s.get("preco", ctx.hoje.close.iloc[-1])); sg = 1 if s["lado"] == "compra" else -1
        novo = p + sg * k_r * abs(p - float(s["stop"]))
        if abs(novo - p) < abs(float(s["alvo"]) - p): s["alvo"] = novo
        return s, g
    return f


def post_trava(trig=0.5, lock=20.0, ef_max=None):
    """Depois de andar `trig` x R a favor, o stop vai para entrada +/- `lock` pts a favor (zero a zero com custo). So anda a favor.
    ef_max: so em rotacao (ef do dia ate agora < ef_max) no instante da entrada."""
    def f(n, s, g, ctx):
        if ef_max is not None and ef_hoje(ctx) >= ef_max: return s, g
        p = float(s.get("preco", ctx.hoje.close.iloc[-1])); r0 = abs(p - float(s["stop"])); lado = s["lado"]

        def ger(c, pos):
            h = c.hoje[c.hoje.index >= pos["t_ent"].floor("15min")]
            fav = (float(h.high.max()) - pos["preco"]) if lado == "compra" else (pos["preco"] - float(h.low.min()))
            novo = None
            if fav >= trig * r0:
                novo = pos["preco"] + lock if lado == "compra" else pos["preco"] - lock
            outro = g(c, pos) if g is not None else None
            return _comb(lado, novo, outro)
        return s, ger
    return f


def post_cancela(cond, naturezas=None):
    """Cancela a entrada (s=None) se cond(ctx, s, nome) e (opcional) a natureza do nome esta em `naturezas`."""
    import cfg3
    def f(n, s, g, ctx):
        if naturezas is not None and cfg3.natureza(n) not in naturezas: return s, g
        return (None, g) if cond(ctx, s, n) else (s, g)
    return f


# ----------------------------------------------------------------------------- vetos / FAZER do grupo ----------------------------
def _borda_rotacao(ctx, lado, ef_max=0.10, frac=0.30, a_partir=10 * 60 + 30):
    """Veto: em rotacao (ef<ef_max, apos 10:30) nao VENDER no terco inferior da faixa do dia nem COMPRAR no superior
    (perseguir a borda de uma faixa que devolve). Condicao: dia sem direcao + preco ja na extremidade."""
    if hm(ctx) < a_partir or ef_hoje(ctx) >= ef_max: return False
    p = pos_na_faixa(ctx)
    if p is None: return False
    return (lado == "venda" and p <= frac) or (lado == "compra" and p >= 1 - frac)


def f_fade_borda_rotacao(ctx):
    """FAZER: em rotacao (ef<0,10, 10:45-15:30, faixa do dia >= 1,5 ATR15), vela que TOCA a borda inferior (superior) da faixa do dia
    (a 0,1 da faixa) e fecha a favor da rejeicao (alta/baixa), com o fecho nos 40% da borda -> compra (vende). Stop = alem do pavio
    (+0,1 faixa, minimo 0,25 faixa, <= 590), alvo 1R. Condicao: faixa sem direcao devolve da borda. Natureza: reversao a valor (fade de borda)."""
    h = ctx.hoje
    if not (10 * 60 + 45 <= hm(ctx) <= 15 * 60 + 30) or len(h) < 6 or ef_hoje(ctx) >= 0.10: return None
    hi, lo = float(h.high.max()), float(h.low.min()); fx = hi - lo
    if fx < 1.5 * ctx.atr15: return None
    u = h.iloc[-1]; c = float(u.close)
    if u.low <= lo + 0.1 * fx and u.close > u.open and c <= lo + 0.4 * fx:
        r = min(max(c - float(u.low) + 0.1 * fx, 0.25 * fx), TETO)
        return dict(lado="compra", preco=c, stop=c - r, alvo=c + r, contratos=1)
    if u.high >= hi - 0.1 * fx and u.close < u.open and c >= hi - 0.4 * fx:
        r = min(max(float(u.high) - c + 0.1 * fx, 0.25 * fx), TETO)
        return dict(lado="venda", preco=c, stop=c + r, alvo=c - r, contratos=1)


def f_continuacao_cedo(ctx, disp=1.0):
    """FAZER (entrada cedo, a favor da perna): 09:45-10:15, as 3 ultimas velas M15 fecham em sequencia na mesma direcao, o deslocamento
    desde a abertura e >= 1,0 ATR15 e o fecho esta nos 30% externos da faixa das 3 velas -> entra na direcao. Stop 1,3 ATR15 (<=590), alvo 2R.
    Condicao: a perna do dia ja comecou e nao devolveu. Natureza: continuacao cedo."""
    h = ctx.hoje
    if not (9 * 60 + 45 <= hm(ctx) <= 10 * 60 + 15) or len(h) < 3: return None
    u3 = h.iloc[-3:]; c = u3.close.values; o = float(h.open.iloc[0])
    fx = float(u3.high.max() - u3.low.min())
    if fx <= 0: return None
    r = min(1.3 * ctx.atr15, TETO)
    if c[0] < c[1] < c[2] and c[2] - o >= disp * ctx.atr15 and c[2] >= u3.low.min() + 0.7 * fx:
        return dict(lado="compra", preco=float(c[2]), stop=float(c[2]) - r, alvo=float(c[2]) + 2 * r, contratos=1)
    if c[0] > c[1] > c[2] and o - c[2] >= disp * ctx.atr15 and c[2] <= u3.low.min() + 0.3 * fx:
        return dict(lado="venda", preco=float(c[2]), stop=float(c[2]) + r, alvo=float(c[2]) - 2 * r, contratos=1)


# ----------------------------------------------------------------------------- aplicadores (Cfg) ------------------------------------
def ap_post(f):
    def ap(cfg): cfg.post = cfg.post + [f]
    return ap


def ap_nf(lst):
    def ap(cfg): cfg.nf = cfg.nf + list(lst)
    return ap


def ap_fz(nome, fn, g=None):
    def ap(cfg): cfg.fz = cfg.fz + [(nome, fn, g)]
    return ap


def _cond_cont_rot(ctx, s, n, ef_max=0.08, amp_max=0.5):
    return hm(ctx) >= 10 * 60 + 30 and ef_hoje(ctx) < ef_max and amp_atrd(ctx) < amp_max


CAND = {
    # gestao
    "G1_alvo_0.5_rot": ap_post(post_alvo_curto(0.5, 0.10)),
    "G1b_alvo_0.6_rot": ap_post(post_alvo_curto(0.6, 0.10)),
    "G1c_alvo_0.5R_rot": ap_post(post_alvo_R(0.5, 0.10)),
    "G1d_alvo_1R_rot": ap_post(post_alvo_R(1.0, 0.10)),
    "G2_trava_0.5R_global": ap_post(post_trava(0.5, 20.0, None)),
    "G2b_trava_0.5R_rot": ap_post(post_trava(0.5, 20.0, 0.10)),
    # veto / cancela
    "G3_veto_borda_rot": ap_nf(ambos("g:borda em rotacao", _borda_rotacao)),
    "G4_cancela_continuacao_rot": ap_post(post_cancela(_cond_cont_rot, ("continuacao",))),
    # FAZER
    "G5_fade_borda_rot": ap_fz("c3g:fade borda da faixa em rotacao", f_fade_borda_rotacao),
    "G6_continuacao_cedo": ap_fz("c3g:continuacao cedo", f_continuacao_cedo),
}


def _borda(ef_max, frac, so=None):
    def fn(ctx, lado):
        if so and lado != so: return False
        return _borda_rotacao(ctx, lado, ef_max, frac)
    return fn


# variantes de sensibilidade (mesma ideia, outro limiar): reportadas para mostrar vizinhanca, nao para escolher a melhor
for _e, _f in ((0.06, 0.3), (0.15, 0.3), (0.10, 0.2)):  # ambos os lados
    CAND[f"G3v_borda_ef{_e}_f{_f}"] = ap_nf(ambos("g:borda", _borda(_e, _f)))
CAND["G3v_borda_so_venda"] = ap_nf(ambos("g:borda", _borda(0.10, 0.3, "venda")))
CAND["G3v_borda_so_compra"] = ap_nf(ambos("g:borda", _borda(0.10, 0.3, "compra")))
for _e in (0.06, 0.10, 0.15):
    for _f in (0.2, 0.3, 0.4):
        CAND[f"G3n_venda_ef{_e}_f{_f}"] = ap_nf(ambos("g:borda venda", _borda(_e, _f, "venda")))
for _e, _a in ((0.05, 0.5), (0.12, 0.5), (0.08, 0.35), (0.08, 0.8)):
    CAND[f"G4v_cont_ef{_e}_amp{_a}"] = ap_post(post_cancela(lambda c, s, n, e=_e, a=_a: _cond_cont_rot(c, s, n, e, a), ("continuacao",)))
for _t, _l in ((0.8, 20.0), (1.0, 20.0), (0.8, 100.0), (1.0, 150.0)):
    CAND[f"G2v_trava_{_t}R_lock{int(_l)}_rot"] = ap_post(post_trava(_t, _l, 0.10))


for _e in (0.06, 0.08, 0.10):
    for _a in (0.25, 0.35, 0.45):
        CAND[f"G4n_cont_ef{_e}_amp{_a}"] = ap_post(post_cancela(lambda c, s, n, e=_e, a=_a: _cond_cont_rot(c, s, n, e, a), ("continuacao",)))
CAND["G6b_continuacao_cedo_disp1.5"] = ap_fz("c3g:continuacao cedo disp 1,5", lambda ctx: f_continuacao_cedo(ctx, 1.5))
CAND["G3r_venda_borda_amp0.5"] = ap_nf(ambos("g:borda venda amp<0,5", lambda ctx, lado: lado == "venda" and amp_atrd(ctx) < 0.5 and _borda_rotacao(ctx, lado, 0.10, 0.30)))
CAND["G2c_trava_0.5R_lock60_rot"] = ap_post(post_trava(0.5, 60.0, 0.10))
CAND["G1e_alvo_0.5R_ef0.15"] = ap_post(post_alvo_R(0.5, 0.15))


def cfg_de(ids, extra=None):
    """Cfg do v3 + propostas `ids` (do CAND do grupo ou de `extra`, dict id->ap)."""
    import cfg3
    cfg = cfg3.monta(IDS_V3)
    reg = dict(CAND); reg.update(extra or {})
    for i in ids: reg[i](cfg)
    return cfg


# ----------------------------------------------------------------------------- avaliacao nos 70 dias ------------------------------
def dias70():
    import json
    j = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in j["ciclo0"]["dias"]]
    for k in ("ciclo1", "ciclo2", "ciclo3"):
        out += [(x["dia"], "c" + k[-1]) for x in j[k]["dias"]]
    assert len(out) == 70
    return out


def _um(args):
    modulos, ids, dia = args
    import importlib
    extra = {}
    for m in modulos: extra.update(importlib.import_module(m).CAND)
    import cfg3
    return ids, dia, cfg3.resultado_dia(dia, cfg_de(ids, extra))


def avalia(configs, modulos=("regras.c3_grupo_2022_04_13",), workers=8, cache=None):
    """configs: lista de tuplas de ids. Devolve {ids: {dia: resultado}}. `cache`: dict mutavel opcional ((ids,dia)->res)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    dias = [d for d, _ in dias70()]
    cache = {} if cache is None else cache
    falta = [(modulos, tuple(c), d) for c in dict.fromkeys(map(tuple, configs)) for d in dias if (tuple(c), d) not in cache]
    if falta:
        with ProcessPoolExecutor(workers) as ex:
            for f in as_completed([ex.submit(_um, a) for a in falta]):
                k, d, r = f.result(); cache[(k, d)] = r
    return {tuple(c): {d: cache[(tuple(c), d)] for d in dias} for c in configs}


def metricas(res, base_res):
    """Reponderado (2 estratos: direcional ef>=0,25 = 3,8%; nao-direcional = 96,2%), por estrato, delta vs base, ciclo 3 (20 dias)."""
    import json
    ef = json.load(open(RAIZ / "ciclo3" / "ef_todos.json"))
    fr_dir = sum(e >= 0.25 for e in ef.values()) / len(ef)
    D = dias70(); dias = [d for d, _ in D]; ciclo = np.array([c for _, c in D])
    dire = np.array([ef[d] >= 0.25 for d in dias])
    v = np.array([res[d]["brl"] for d in dias]); b = np.array([base_res[d]["brl"] for d in dias])

    def rep(x): return fr_dir * x[dire].mean() + (1 - fr_dir) * x[~dire].mean()
    d = v - b
    return dict(total=v.sum(), rep=rep(v), d_rep=rep(v) - rep(b), d_dir=d[dire].mean(), d_nd=d[~dire].mean(),
                d_c3=d[ciclo == "c3"].sum(),
                d_c3_ext=d[(ciclo == "c3") & ~np.isin(dias, ["2022-04-13", "2022-05-17"])].sum(), d_total=d.sum(), piora=int((d < -0.5).sum()), melhora=int((d > 0.5).sum()),
                pior_dia=v.min(), dias_piora=[dias[i] for i in np.where(d < -0.5)[0]], dias_melhora=[dias[i] for i in np.where(d > 0.5)[0]])


if __name__ == "__main__":
    ids = sys.argv[1:] or list(CAND)
    base_k = ()
    cfgs = [base_k] + [(i,) for i in ids]
    import os, pickle
    cp = os.environ.get("C3_CACHE"); cache = pickle.load(open(cp, "rb")) if cp and os.path.exists(cp) else {}
    R = avalia(cfgs, cache=cache)
    if cp: pickle.dump(cache, open(cp, "wb"))
    print(f"v3 base: total R$ {sum(x['brl'] for x in R[base_k].values()):.2f}", flush=True)
    for i in ids:
        m = metricas(R[(i,)], R[base_k])
        print(f"{i:28s} d_rep {m['d_rep']:+7.2f}  d_dir {m['d_dir']:+7.2f}  d_nd {m['d_nd']:+7.2f}  d_c3 {m['d_c3']:+8.1f} (ext {m['d_c3_ext']:+7.1f})  d_total {m['d_total']:+8.1f}  "
              f"piora {m['piora']} melhora {m['melhora']}", flush=True)
