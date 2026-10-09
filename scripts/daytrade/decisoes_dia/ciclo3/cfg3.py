"""Motor e candidatas do ciclo 3. Sobre o v2 (robo_v2.monta_v2). Nada existente e editado.
Cfg = (fz, nf, prio, post). `post` = transformacoes de sinal aplicadas na entrada escolhida: fn(nome, s, g, ctx) -> (s, g)."""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

C3 = Path(__file__).resolve().parent
RAIZ = C3.parent
sys.path.insert(0, str(RAIZ))
import base, robo, robo_v2
from regras import (c1_2023_07_27 as c1a, c2_2022_05_24 as c22, c2_2023_09_04 as c23, c2_2023_10_17 as c2310,
                    c2_2024_04_22 as c2404, c2_2024_11_04 as c2411, c2_2025_04_07 as c2504, c2_2025_06_06 as c2506)

MAXPTS = 600.0
V_STOP_CURTO = "2023_08_21:vende_rompimento_stop_curto"


class Cfg:
    def __init__(self, fz, nf, prio=None, post=None):
        self.fz, self.nf, self.prio, self.post = list(fz), list(nf), list(prio or []), list(post or [])


def base_v2():
    fz, nf = robo_v2.monta_v2()
    return Cfg(fz, nf)


# ------------------------------------------------------------------ motor
def roda(dia, cfg):
    """Mesma decisao de robo.roda_robo (estrutura v1) + prioritarias + post. Sem prio/post == robo_v2.roda_v2."""
    fz, nf, prio, post = cfg.fz, cfg.nf, cfg.prio, cfg.post

    def decide(ctx):
        for n, r, g in prio:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and not robo._agressiva(s, ctx):
                return s, dict(fazer=[(n, s["lado"])], vetos={}, entrou=n, nota="prioritaria"), g
        sins = []
        for n, r, g in fz:
            s = robo._chama(r, ctx)
            if s and "erro" not in s: sins.append((n, s, g))
        if not sins:
            return None, None, None
        vetos = {"compra": [], "venda": []}
        for n, r, g in nf:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
        info = dict(fazer=[(n, s["lado"]) for n, s, g in sins], vetos={k: v for k, v in vetos.items() if v}, entrou=None, nota="")
        if len({s["lado"] for _, s, _ in sins}) > 1:
            info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
        for n, s, g in sins:
            if robo._agressiva(s, ctx):
                info["nota"] += f"[{n} limitada agressiva] "; continue
            if vetos[s["lado"]]:
                info["nota"] += f"[{n} VETADA por {len(vetos[s['lado']])}] "
                return None, info, None
            info["entrou"] = n
            for f in post:
                s, g = f(n, s, g, ctx)
            return s, info, g
        return None, info, None

    return robo._roda(dia, decide)


def resultado_dia(dia, cfg):
    tr, log = roda(dia, cfg)
    ok = [x for x in tr if x.t_ent is not None]
    return dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok),
                trades=[dict(fonte=x.fonte, lado=x.lado, contratos=x.contratos, sinal=str(x.t_sinal.time()), ent=str(x.t_ent.time()),
                             sai=str(x.t_sai.time()), preco=x.preco, preco_sai=x.preco_sai, stop=x.stop_ini, alvo=x.alvo,
                             motivo=x.motivo, pts=round(x.pts, 1), brl=round(x.brl, 2)) for x in ok])


# ------------------------------------------------------------------ helpers de estado
def natureza(nome):  # copia de gestao_adaptativa/coleta.py
    s = nome.lower()
    if any(k in s for k in ("rompimento", "expansao", "breakout", "inversao")): return "rompimento"
    if any(k in s for k in ("fade", "falha", "spring", "faixa", "gap", "retorno", "esticada")): return "reversao"
    if any(k in s for k in ("recuo", "tendencia", "pullback")): return "continuacao"
    return "outra"


def _sg(s): return 1 if s["lado"] == "compra" else -1


def _preco(s, ctx): return float(s.get("preco", ctx.hoje.close.iloc[-1]))


# ------------------------------------------------------------------ candidatas: pos-sinal (gestao)
def post_sem_alvo(k, filtro=None):
    def f(n, s, g, ctx):
        if filtro is not None and not filtro(n): return s, g
        s = dict(s); p = _preco(s, ctx); sg = _sg(s)
        s["stop"] = p - sg * min(k * ctx.atr15, MAXPTS); s["alvo"] = None
        return s, None
    return f


def post_vol4(n, s, g, ctx):
    h = ctx.hoje
    v4 = float((h.high - h.low).iloc[-4:].mean()) / ctx.atr15
    k = 2.0 if v4 >= 1.0 else 1.0
    s = dict(s); p = _preco(s, ctx); sg = _sg(s)
    s["stop"] = p - sg * min(k * ctx.atr15, MAXPTS); s["alvo"] = None
    return s, None


def post_alvo15(n, s, g, ctx):
    if s.get("alvo") is None: return s, g
    h = ctx.hoje; p = _preco(s, ctx)
    desloc = _sg(s) * (float(h.close.iloc[-1]) - float(h.open.iloc[0])) / ctx.atr15
    if desloc >= 1.0:
        s = dict(s); s["alvo"] = p + 1.5 * (float(s["alvo"]) - p)
    return s, g


# ------------------------------------------------------------------ candidatas: mudancas de listas
def _sub_veto(cfg, orig, fn, g=None):
    assert any(n == orig for n, _, _ in cfg.nf), orig
    cfg.nf = [(n, fn, g) if n == orig else (n, r, gg) for n, r, gg in cfg.nf]


def _modulo_monta(mod, chaves):
    def ap(cfg):
        out = mod.monta(cfg.fz, cfg.nf, chaves)
        cfg.fz, cfg.nf = list(out[0]), list(out[1])
        if len(out) > 2: cfg.prio = cfg.prio + list(out[2])
    return ap


def ap_c5m(cfg):
    """Espelho de C5 para venda: os vetos de venda de rompimento/minima nova da manha so valem fora de dia direcional de baixa."""
    nomes = {V_STOP_CURTO, "2025_06_04:N2 vender minima na rotacao da manha", "2022_11_29:vender_quebra_minima_cedo"}

    def wrap(r):
        def w(ctx):
            if c2411._desloc(ctx) == -1: return None
            return r(ctx)
        return w
    achou, novo = 0, []
    for n, r, g in cfg.nf:
        if n in nomes: r = wrap(r); achou += 1
        novo.append((n, r, g))
    assert achou == 3, achou
    cfg.nf = novo


def ap_c8(cfg):
    _sub_veto(cfg, c22.V_SEMVOL, c22.n_rompimento_sem_volume_corpo_forte)
    _sub_veto(cfg, c22.V_SUPORTE, c22.n_compra_suporte_ontem_abaixo_vwap)
    cfg.fz = cfg.fz + [("c2:C8 expansao_compressao", c22.f_expansao_apos_compressao, c22.gerir_adaptativo)]


def ap_c10a(cfg):
    fz0, nf0 = robo.carrega_regras()
    orig = dict((n, r) for n, r, g in nf0)[V_STOP_CURTO]
    _sub_veto(cfg, V_STOP_CURTO, orig)


def ap_c10b(cfg):
    _sub_veto(cfg, V_STOP_CURTO, c1a.a2v_veto_raso_e_sem_volume)


def ap_c11(cfg): cfg.nf = cfg.nf + [("c2a N1", c2310.n1_comprar_logo_apos_vela_de_queda_forte, None)]


def ap_c12(cfg): cfg.fz = cfg.fz + [("c2a F2", c2310.f2_compra_rompe_maxima_1a_hora_alvo_1atr, None)]


def ap_post(f):
    def ap(cfg): cfg.post = cfg.post + [f]
    return ap


# id -> (descricao, origem, funcao_aplica, grupo_exclusivo)
CAND = {
    "C1":   ("alvo x1,5 se desloc a favor >= 1 ATR", "oportunidades_perdidas", ap_post(post_alvo15), None),
    "C2":   ("sem alvo, stop 1,5 ATR (<=600) global", "gestao_adaptativa", ap_post(post_sem_alvo(1.5)), "gestao"),
    "C2b2": ("sem alvo, stop 2 ATR (<=600) global", "gestao_adaptativa", ap_post(post_sem_alvo(2.0)), "gestao"),
    "C2c":  ("sem alvo stop 1,5 so em continuacao", "gestao_adaptativa", ap_post(post_sem_alvo(1.5, lambda n: natureza(n) == "continuacao")), "gestao"),
    "C2d":  ("sem alvo stop 1,5 em continuacao+rompimento", "gestao_adaptativa",
             ap_post(post_sem_alvo(1.5, lambda n: natureza(n) in ("continuacao", "rompimento"))), "gestao"),
    "C3":   ("stop por vol4 (alta 2 ATR / baixa 1 ATR), sem alvo", "gestao_adaptativa", ap_post(post_vol4), "gestao"),
    "C4":   ("rompimento 1a hora c/ volume>=1,5x, alvo 1R; vetos so sem volume", "c2_2023_09_04 P2", _modulo_monta(c23, ["P2"]), "vetos_romp_compra"),
    "C5":   ("vetos de compra N4/N3 so fora de dia direcional de alta", "c2_2024_11_04 P1", _modulo_monta(c2411, ["P1"]), "vetos_romp_compra"),
    "C5m":  ("espelho: vetos de venda so fora de dia direcional de baixa", "c2_2024_11_04 P1 (espelho)", ap_c5m, None),
    "C6":   ("N4 + N1 + F1 (VWAP rotacao, ATR>=1,5x teto, pullback alvo 1R)", "c2_2025_04_07", _modulo_monta(c2504, ["N4", "N1", "F1"]), None),
    "C7":   ("N5 vender minima nova com range/volume encolhendo", "c2_2024_04_22", _modulo_monta(c2404, ["N5"]), None),
    "C8":   ("A1+A2+F2 (afrouxa 2 vetos de compra + expansao pos-compressao)", "c2_2022_05_24", ap_c8, None),
    "C9":   ("N5+N4+P5 (ATR expandido, perto da minima pos-15h, trailing A3)", "c2_2025_06_06", _modulo_monta(c2506, ["N5", "N4", "P5"]), None),
    "C10a": ("A2 desfeito: veto original da v1", "c1_2023_07_27 / c2_2024_04_22", ap_c10a, "veto_a2"),
    "C10b": ("A2v: veto so raso E sem volume", "c1_2023_07_27 (variante)", ap_c10b, "veto_a2"),
    "C11":  ("N1 nao comprar logo apos vela de queda forte c/ volume", "c2_2023_10_17 N1", ap_c11, None),
    "C12":  ("F2 compra rompe maxima 1a hora alvo 1 ATR", "c2_2023_10_17 F2", ap_c12, None),
    "C13":  ("falha_maxima so fora de dia direcional de alta", "c2_2024_11_04 P2", _modulo_monta(c2411, ["P2"]), None),
    "C14":  ("V1 nao vender em dia direcional de alta", "c2_2024_11_04 V1", _modulo_monta(c2411, ["V1"]), None),
    "C15":  ("F2A exaustao vendedora prioritaria + chandelier", "c2_2025_04_07 F2A", _modulo_monta(c2504, ["F2A"]), None),
}
ORDEM = list(CAND.keys())


def monta(ids):
    """Cfg do v2 + candidatas `ids`, em ordem fixa (a gestao C2.. vem antes de C1? nao: C1 e o primeiro da ordem, mas
    as transformacoes de gestao REESCREVEM o alvo; por isso `post` e reordenado: gestao antes, C1 depois)."""
    cfg = base_v2()
    for i in ORDEM:
        if i in ids: CAND[i][2](cfg)
    # gestao antes de C1
    if post_alvo15 in cfg.post and len(cfg.post) > 1:
        cfg.post = [f for f in cfg.post if f is not post_alvo15] + [post_alvo15]
    return cfg


# ------------------------------------------------------------------ dias
def dias50():
    du = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in du["ciclo0"]["dias"]]
    out += [(x["dia"], "c1") for x in du["ciclo1"]["dias"]]
    out += [(x["dia"], "c2") for x in du["ciclo2"]["dias"]]
    return out
