"""Ciclo 3 - propostas COMUNS aos dois dias negativos do robo_v3 (2022-12-12 e 2024-02-01) + motor de avaliacao.

Nada existente e editado. Parte do `robo_v3` (cfg3.monta(["C8","C7","C6","C4"])) e aplica `ap_*(cfg)` sobre ele.

Motor `roda_ext`: copia de cfg3.roda com um gancho a mais: `cfg.empate == "lado_livre"` (quando ha FAZER nos dois lados,
entra o lado que nao esta vetado, se exatamente um estiver livre - o que a variante v2e do ciclo 2 fazia).

Avaliacao (`python -m regras.c3_grupo_2022_12_12`): roda cada proposta nos 70 dias de dias_usados.json (ciclos 0-3) em
paralelo e imprime: R$/dia REPONDERADO (direcional 3,8% / nao-direcional 96,2%), delta contra o v3, delta no estrato
nao-direcional, delta nos 20 dias do ciclo 3, dias piores/melhores, pior dia.
"""
import sys, json, pickle
from pathlib import Path
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
import base, robo, robo_v3, cfg3

IDS_V3 = robo_v3.IDS
MAXR = 590.0
V_N2 = "2025_06_04:N2 vender minima na rotacao da manha"
V_RALI = "2024_06_18:vender_rali_1atr"
V_SEMVOL = "2024_06_18:rompimento_sem_volume"
V_N5C7 = "c2:N5 vender com range e volume encolhendo"
V_N4C6 = "c2:N4 vwap rotacao"
V_MAXNOVA = "2024_06_18:vender_maxima_nova"
V_A2 = "2023_08_21:vende_rompimento_stop_curto"


# ------------------------------------------------------------------------------------------------ helpers de estado
def vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def ef_parcial(h):
    rng = float((h.high - h.low).sum())
    return abs(float(h.close.iloc[-1] - h.open.iloc[0])) / rng if rng > 0 else 0.0


def expansao(ctx, k_rng=1.6, k_vol=1.5):
    """Vela de expansao (A4 do ciclo 1): faixa >= k_rng x ATR ate a vela anterior, volume >= k_vol x media do dia, fecha nos 25%
    extremos. Devolve 'venda' (fecha na minima), 'compra' (na maxima) ou None."""
    h = ctx.hoje
    if len(h) < 3: return None
    u = h.iloc[-1]
    rng = float(u.high - u.low)
    atr_ant = float((ctx.m15.iloc[:-1].high - ctx.m15.iloc[:-1].low).iloc[-14:].mean())
    if rng < k_rng * atr_ant or u.vol < k_vol * h.vol.iloc[:-1].mean(): return None
    if u.close <= u.low + 0.25 * rng: return "venda"
    if u.close >= u.high - 0.25 * rng: return "compra"
    return None


def _ord(ctx, lado, stop, alvo_r=None, alvo=None):
    p = float(ctx.hoje.close.iloc[-1])
    if lado == "compra":
        st = max(float(stop), p - MAXR)
        al = alvo if alvo is not None else (p + alvo_r * (p - st) if alvo_r else None)
    else:
        st = min(float(stop), p + MAXR)
        al = alvo if alvo is not None else (p - alvo_r * (st - p) if alvo_r else None)
    return dict(lado=lado, preco=p, stop=st, alvo=al, contratos=1)


# ------------------------------------------------------------------------------------------------ motor
def roda_ext(dia, cfg):
    fz, nf, prio, post = cfg.fz, cfg.nf, cfg.prio, cfg.post
    empate = getattr(cfg, "empate", None)

    def decide(ctx):
        for n, r, g in prio:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and not robo._agressiva(s, ctx):
                return s, dict(fazer=[(n, s["lado"])], vetos={}, entrou=n, nota="prioritaria"), g
        sins = []
        for n, r, g in fz:
            s = robo._chama(r, ctx)
            if s and "erro" not in s: sins.append((n, s, g))
        if not sins: return None, None, None
        vetos = {"compra": [], "venda": []}
        for n, r, g in nf:
            s = robo._chama(r, ctx)
            if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
        info = dict(fazer=[(n, s["lado"]) for n, s, g in sins], vetos={k: v for k, v in vetos.items() if v}, entrou=None, nota="")
        lados = {s["lado"] for _, s, _ in sins}
        if len(lados) > 1:
            livres = {l for l in lados if not vetos[l]}
            if empate == "lado_livre" and len(livres) == 1:
                sins = [x for x in sins if x[1]["lado"] in livres]
                info["nota"] += "[empate: lado livre] "
            else:
                info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
        for n, s, g in sins:
            if robo._agressiva(s, ctx):
                info["nota"] += f"[{n} limitada agressiva] "; continue
            if vetos[s["lado"]]:
                info["nota"] += f"[{n} VETADA por {len(vetos[s['lado']])}] "
                return None, info, None
            info["entrou"] = n
            for f in post: s, g = f(n, s, g, ctx)
            return s, info, g
        return None, info, None

    return robo._roda(dia, decide)


def resultado(dia, cfg):
    tr, log = roda_ext(dia, cfg)
    ok = [x for x in tr if x.t_ent is not None]
    return dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok), log=log,
                trades=[dict(fonte=x.fonte, lado=x.lado, sinal=str(x.t_sinal.time()), ent=str(x.t_ent.time()), sai=str(x.t_sai.time()),
                             preco=x.preco, preco_sai=x.preco_sai, stop=x.stop_ini, alvo=x.alvo, motivo=x.motivo,
                             pts=round(x.pts, 1), brl=round(x.brl, 2)) for x in ok])


# ------------------------------------------------------------------------------------------------ utilitarios de cfg
def _wrap_veto(cfg, nomes, fn_wrap):
    achou, novo = 0, []
    for n, r, g in cfg.nf:
        if n in nomes: r = fn_wrap(r); achou += 1
        novo.append((n, r, g))
    assert achou == len(nomes), (achou, nomes)
    cfg.nf = novo


# ================================================================================================================
# PROPOSTAS COMUNS
# ================================================================================================================
# ---- G1: a vela de expansao confirma por si: ela isenta os vetos de rotacao do lado dela --------------------------
def _isenta_expansao(r):
    def w(ctx):
        s = r(ctx)
        if s and expansao(ctx) == s["lado"]: return None
        return s
    return w


def ap_g1_expansao_isenta_vetos_de_rotacao(cfg):
    """G1 (ajuste de 6 vetos). Vela de expansao (faixa >= 1,6 ATR, volume >= 1,5x, fecha nos 25% extremos) NAO e vetada pelos vetos
    que descrevem rotacao/ruido (N2 vender minima na rotacao da manha, N5 range/volume encolhendo, rompimento_sem_volume, vender
    rali 1 ATR, vender maxima nova, N4 VWAP rotacao): uma vela que ja andou 1,6 ATR com volume nao e ruido de rotacao. E o
    mesmo argumento que o C8 usou para `rompimento_sem_volume` (corpo >= 1,5 ATR), estendido a todos os vetos de rotacao.
    2022-12-12 10:45: vela de 925 pts (2,4 ATR15), volume 1,7x, fechou na minima; so o N2 a vetou (v3: nada; ver analise)."""
    _wrap_veto(cfg, {V_N2, V_RALI, V_SEMVOL, V_N5C7, V_N4C6, V_MAXNOVA}, _isenta_expansao)


# ---- G2: o veto do rali de 1 ATR passa a valer so quando o dia tem vies comprador (como diz o proprio docstring) ----
def _rali_com_vies(r):
    def w(ctx):
        s = r(ctx)
        if s and ctx.hoje.close.iloc[-1] <= ctx.hoje.open.iloc[0]: return None  # dia abaixo da abertura: nao ha vies comprador
        return s
    return w


def ap_g2_rali_so_com_vies_comprador(cfg):
    """G2 (ajuste de veto). `2024_06_18:vender_rali_1atr` diz no docstring que veta vender o rali 'quando o dia tem vies comprador
    (abertura abaixo, fechamento corrente acima da abertura)', mas o codigo so testa 'fechamento - minima de 4 velas >= 1 ATR'.
    Aqui o codigo passa a obedecer o docstring: com o fechamento do dia ABAIXO da abertura o veto nao vale.
    2022-12-12 10:30: dia 450 pts abaixo da abertura, o veto calava a venda do pullback."""
    _wrap_veto(cfg, {V_RALI}, _rali_com_vies)


# ---- G3: empate de lados resolvido pelo lado nao vetado (v2e) ------------------------------------------------------
def ap_g3_empate_lado_livre(cfg):
    """G3 (ajuste de estrutura). 'FAZER nos dois lados = nao entra' passa a 'entra o lado que nao esta vetado, se exatamente um
    estiver livre' (variante v2e do ciclo 2). 2022-12-12 10:30: pullback de venda x F5 de compra; so a compra estava vetada
    (compra_queda_1atr) se o veto de rali da venda cair (G2)."""
    cfg.empate = "lado_livre"


# ---- G4: A2 condicional --------------------------------------------------------------------------------------------
def a2c_veto_rompimento_raso_ou_esticado(ctx, max_atr=2.5):
    """A2c = versao condicional do A2 (pedido do ciclo 3). O A2 (v2) so veta a venda de rompimento RASO (fecho a < 0,5 ATR15 da
    minima da 1a hora) e libera todo o resto. A2c continua vetando o raso e passa a vetar tambem o ESTICADO: fecho a mais de
    `max_atr` ATR15 abaixo da minima da 1a hora (perseguir queda que ja andou 2,5 ATR e entrar no fim do movimento). So usa o
    estado no instante da decisao (minima da 1a hora e ATR15 atual). 2022-12-12 12:30: fecho 104.395, a 3,8 ATR15 abaixo da
    minima da 1a hora (106.920): vetaria a F1 que perdeu -R$120."""
    h = ctx.hoje
    if len(h) < 5: return None
    lo = float(h.iloc[:4].low.min()); c = float(h.close.iloc[-1])
    if lo - 0.5 * ctx.atr15 < c < lo or c < lo - max_atr * ctx.atr15:
        return dict(lado="venda", stop=c + 120, alvo=c - 240, preco=c)
    return None


def ap_g4_a2_condicional(cfg):
    cfg.nf = [(n, a2c_veto_rompimento_raso_ou_esticado, g) if n == V_A2 else (n, r, g) for n, r, g in cfg.nf]
    assert any(n == V_A2 for n, _, _ in cfg.nf)


# ---- G5: FAZER novo - reentrada no 1o recuo depois de vela de expansao ---------------------------------------------
def f_recuo_pos_expansao(ctx):
    """FAZER novo (continuacao a favor da perna). Houve uma vela de expansao (A4) numa das 3 velas anteriores; a vela atual e um
    recuo curto (retraiu <= 50% da faixa da expansao) que FECHA de volta na direcao da perna (venda: fecha abaixo da minima da vela
    anterior e em queda). Entra no fechamento; stop alem do extremo do recuo (teto 590), alvo 1,5R.
    Condicao de mercado: pernas de expansao com volume costumam ter segunda onda depois de um respiro raso. Perde quando o respiro
    era a reversao. Provavelmente geral na ideia; limiares (1,6 ATR / 1,5x / 50%) vem do A4."""
    h = ctx.hoje
    if len(h) < 6 or not (10 * 60 <= ctx.t.hour * 60 + ctx.t.minute <= 16 * 60): return None
    u, p = h.iloc[-1], h.iloc[-2]
    for k in (2, 3, 4):
        e = h.iloc[-k]
        atr_ant = float((ctx.m15.loc[:e.name].iloc[:-1].pipe(lambda d: d.high - d.low)).iloc[-14:].mean())
        rng = float(e.high - e.low)
        if rng < 1.6 * atr_ant or e.vol < 1.5 * h.vol.iloc[:-k].mean(): continue
        sub = h.iloc[-k + 1:]   # velas depois da expansao, incluindo a atual
        if e.close <= e.low + 0.25 * rng:   # expansao de baixa
            if sub.high.max() - e.close <= 0.5 * rng and u.close < p.low and u.close < u.open:
                return _ord(ctx, "venda", float(sub.high.max()) + 20, alvo_r=1.5)
        elif e.close >= e.high - 0.25 * rng:
            if e.close - sub.low.min() <= 0.5 * rng and u.close > p.high and u.close > u.open:
                return _ord(ctx, "compra", float(sub.low.min()) - 20, alvo_r=1.5)
    return None


def ap_g5_recuo_pos_expansao(cfg):
    cfg.fz = cfg.fz + [("c3:recuo pos-expansao", f_recuo_pos_expansao, None)]


# ---- G6: FAZER novo - impulso da 1a vela (entrada cedo) ---------------------------------------------------------------
def f_impulso_primeira_vela(ctx):
    """FAZER novo (entrada cedo, a favor da perna, sem saber se o dia sera direcional). Na 1a vela fechada do dia (09:15) com corpo
    >= 70% da faixa, faixa >= 1,2 ATR15 e volume >= 1,2x a media das 1as velas dos 10 dias anteriores, entra a favor do corpo no
    fechamento; stop na ponta oposta da vela (teto 590), alvo 1,5R. Condicao: o 'drive' de abertura costuma ter continuacao; perde
    em dia de rotacao em que a abertura e devolvida (maioria). Nao tem como saber de antemao: o teste mede se o ruim custa mais
    que o bom paga."""
    h = ctx.hoje
    if len(h) != 1: return None
    u = h.iloc[-1]
    rng = float(u.high - u.low)
    if rng <= 0 or abs(u.close - u.open) < 0.7 * rng or rng < 1.2 * ctx.atr15: return None
    m = ctx.m15
    prim = m[m.index.time == h.index[0].time()]
    prim = prim[prim.index < h.index[0]].vol.iloc[-10:]
    if len(prim) < 5 or u.vol < 1.2 * prim.mean(): return None
    if u.close > u.open: return _ord(ctx, "compra", float(u.low), alvo_r=1.5)
    return _ord(ctx, "venda", float(u.high), alvo_r=1.5)


def ap_g6_impulso_primeira_vela(cfg):
    cfg.fz = cfg.fz + [("c3:impulso 1a vela", f_impulso_primeira_vela, None)]


AP = {
    "G1": ap_g1_expansao_isenta_vetos_de_rotacao,
    "G2": ap_g2_rali_so_com_vies_comprador,
    "G3": ap_g3_empate_lado_livre,
    "G4": ap_g4_a2_condicional,
    "G5": ap_g5_recuo_pos_expansao,
    "G6": ap_g6_impulso_primeira_vela,
}


# ---- variantes estreitas do G1 (quais vetos a expansao isenta) ---------------------------------------------------------
def _ap_g1(nomes):
    def f(cfg): _wrap_veto(cfg, set(nomes), _isenta_expansao)
    return f


ap_g1a = _ap_g1({V_N2})
ap_g1b = _ap_g1({V_N2, V_N5C7})
ap_g1c = _ap_g1({V_N2, V_N5C7, V_SEMVOL})


# ---- G4b: A2 condicional por ATR expandido (em vez de distancia) ----------------------------------------------------
def _a2c_atr(k):
    def f(ctx):
        h = ctx.hoje
        if len(h) < 6: return None
        lo = float(h.iloc[:4].low.min()); c = float(h.close.iloc[-1])
        a0 = float(base._atr(ctx.m15).loc[h.index[3]])
        if (lo - 0.5 * ctx.atr15 < c < lo) or (c < lo and ctx.atr15 > k * a0):
            return dict(lado="venda", stop=c + 120, alvo=c - 240, preco=c)
        return None
    return f


def _ap_g4b(k):
    def f(cfg): cfg.nf = [(n, _a2c_atr(k), g) if n == V_A2 else (n, r, g) for n, r, g in cfg.nf]
    return f


# ---- G5p: recuo pos-expansao como PRIORITARIA (nao passa pelos vetos de rotacao) -------------------------------------
def ap_g5p(cfg):
    cfg.prio = cfg.prio + [("c3:recuo pos-expansao (prio)", f_recuo_pos_expansao, None)]


# ---- G7: entrada a favor de vela de expansao deixa correr (sem alvo, chandelier) ----------------------------------------
def gerir_chandelier(ctx, pos, ativa=1.0, dist=1.5):
    """stop segue o melhor fechamento a `dist` ATR15 depois que a posicao andou `ativa` ATR15 a favor (so anda a favor)."""
    h = ctx.hoje
    h = h[h.index >= pos["t_ent"].floor("15min")]
    a = ctx.atr15
    if pos["lado"] == "venda":
        if pos["preco"] - float(h.close.min()) < ativa * a: return None
        return min(float(h.close.min()) + dist * a, pos["preco"])
    if float(h.close.max()) - pos["preco"] < ativa * a: return None
    return max(float(h.close.max()) - dist * a, pos["preco"])


def post_expansao_corre(n, s, g, ctx):
    if s.get("alvo") is None or expansao(ctx) != s["lado"]: return s, g
    s = dict(s); s["alvo"] = None
    return s, gerir_chandelier


def ap_g7(cfg): cfg.post = cfg.post + [post_expansao_corre]


AP.update({"G1a": ap_g1a, "G1b": ap_g1b, "G1c": ap_g1c, "G4b2": _ap_g4b(2.0), "G4b15": _ap_g4b(1.5), "G5p": ap_g5p, "G7": ap_g7})


# ---- G7 parametrizado (vizinhanca) -------------------------------------------------------------------------------------
def _ap_g7(ativa, dist):
    def ger(ctx, pos): return gerir_chandelier(ctx, pos, ativa, dist)

    def post(n, s, g, ctx):
        if s.get("alvo") is None or expansao(ctx) != s["lado"]: return s, g
        s = dict(s); s["alvo"] = None
        return s, ger

    def ap(cfg): cfg.post = cfg.post + [post]
    return ap


# ---- veto novo comum: nao repetir o MESMO lado apos 2 stops seguidos (ver c3_2024_02_01) ------------------------------
def n_mesmo_lado_apos_dois_stops(ctx, k=2, qualquer_lado=False):
    ops = getattr(ctx, "ops_hoje", [])
    if len(ops) >= k and all(o.motivo == "stop" for o in ops[-k:]) and (qualquer_lado or len({o.lado for o in ops[-k:]}) == 1):
        l = ops[-1].lado
        return _ord(ctx, l, float(ctx.hoje.close.iloc[-1]) + (1 if l == "venda" else -1) * ctx.atr15, alvo_r=1.5)


def _ap_stops(k, qualquer):
    def veto(ctx): return n_mesmo_lado_apos_dois_stops(ctx, k, qualquer)
    def ap(cfg):
        # veta os dois lados quando qualquer_lado; senao so o lado do ultimo stop (o veto devolve esse lado)
        cfg.nf = cfg.nf + [(f"c3:stops k={k} qualquer={qualquer}", veto, None)]
    return ap


AP.update({"G7a": _ap_g7(1.0, 2.0), "G7b": _ap_g7(0.5, 1.0), "G7c": _ap_g7(1.5, 1.5), "G7d": _ap_g7(1.0, 1.0),
           "S2": _ap_stops(2, False), "S1": _ap_stops(1, False), "S2q": _ap_stops(2, True)})


# ================================================================================================================
# AVALIACAO NOS 70 DIAS
# ================================================================================================================
def dias70():
    j = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in j["ciclo0"]["dias"]]
    out += [(x["dia"], "c1") for x in j["ciclo1"]["dias"]]
    out += [(x["dia"], "c2") for x in j["ciclo2"]["dias"]]
    out += [(x["dia"], "c3") for x in j["ciclo3"]["dias"]]
    return out


def monta_proposta(nome, extras=None):
    """nome = 'BASE' | 'G1' | 'G1+G2' ... ; extras = dict nome->ap de outros modulos (ex.: regras.c3_2024_02_01.AP)."""
    cfg = cfg3.monta(IDS_V3)
    cfg.empate = None
    if nome == "BASE": return cfg
    tab = dict(AP)
    if extras: tab.update(extras)
    for k in nome.split("+"): tab[k](cfg)
    return cfg


def _um(args):
    nome, dia, mods = args
    import importlib
    ex = {}
    for m in mods: ex.update(importlib.import_module(m).AP)
    r = resultado(dia, monta_proposta(nome, ex))
    r.pop("log")
    return nome, dia, r


CACHE = Path(__file__).resolve().parent / "__c3_cache.pkl"


def avalia(nomes, mods=(), workers=11, usar_cache=True):
    """Devolve {nome: {dia: resultado}} nos 70 dias. Cache em disco por (nome, dia)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    dias = [d for d, _ in dias70()]
    cache = pickle.load(open(CACHE, "rb")) if (usar_cache and CACHE.exists()) else {}
    falta = [(n, d, tuple(mods)) for n in dict.fromkeys(["BASE"] + list(nomes)) for d in dias if (n, d) not in cache]
    if falta:
        with ProcessPoolExecutor(workers) as ex:
            for f in as_completed([ex.submit(_um, a) for a in falta]):
                n, d, r = f.result(); cache[(n, d)] = r
        pickle.dump(cache, open(CACHE, "wb"))
    return {n: {d: cache[(n, d)] for d in dias} for n in dict.fromkeys(["BASE"] + list(nomes))}


def metricas(res, nome):
    d70 = dias70()
    dias = [d for d, _ in d70]; cic = np.array([c for _, c in d70])
    ef = json.load(open(RAIZ / "ciclo3" / "ef_todos.json"))
    N = len(ef); fr_dir = sum(e >= 0.25 for e in ef.values()) / N
    est = np.array(["dir" if ef[d] >= 0.25 else "nd" for d in dias])
    v = np.array([res[nome][d]["brl"] for d in dias]); b = np.array([res["BASE"][d]["brl"] for d in dias])

    def rep(x): return fr_dir * x[est == "dir"].mean() + (1 - fr_dir) * x[est == "nd"].mean()
    dl = v - b
    return dict(total=v.sum(), rep=rep(v), d_rep=rep(v) - rep(b), d_nd=dl[est == "nd"].mean(), d_dir=dl[est == "dir"].mean(),
                d_c3=dl[cic == "c3"].sum(), d_c012=dl[cic != "c3"].sum(), d_tot=dl.sum(),
                pior=int((dl < -0.5).sum()), melhor=int((dl > 0.5).sum()), pior_dia=v.min(), pior_dia_base=b.min())


def imprime(res, nomes):
    print(f"{'proposta':22s} {'total70':>9s} {'rep R$/d':>9s} {'d_rep':>8s} {'d_nd':>7s} {'d_dir':>7s} {'d_c3(20d)':>10s} {'d_c0-2(50d)':>11s} {'pior/melh':>9s} {'pior dia':>9s}")
    for n in ["BASE"] + list(nomes):
        m = metricas(res, n)
        print(f"{n:22s} {m['total']:9.1f} {m['rep']:9.2f} {m['d_rep']:+8.2f} {m['d_nd']:+7.2f} {m['d_dir']:+7.2f} {m['d_c3']:+10.1f} {m['d_c012']:+11.1f} {m['pior']:>4d}/{m['melhor']:<4d} {m['pior_dia']:9.1f}", flush=True)


def isolada(dia, regra, gerir=None):
    return base.resumo(base.simula_dia(dia, regra, gerir, max_ops=3))


if __name__ == "__main__":
    nomes = list(AP.keys()) + ["G1a+G7", "G2+G3+G7", "G1a+G2+G3+G7", "G7+S2", "G1a+G2+G3+G7+S2"]
    res = avalia(nomes)
    imprime(res, nomes)
