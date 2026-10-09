"""Ciclo 3 - GRUPO (propostas comuns aos dois dias negativos 2024-09-05 e 2024-10-25) + motor de avaliacao nos 70 dias.

Os dois dias sao de ROTACAO (ef 0,044 e 0,071) com a mesma assinatura: o robo vende no FECHO de uma vela que acabou de
fazer a MINIMA do dia e fechou longe dela (pavio inferior de 90-98% da faixa: 2024-09-05 10:00 F2, 2024-10-25 13:30
pullback EMA20) e o mercado devolve. Nada aqui edita arquivos existentes: o v3 e montado por `cfg3.monta`, e cada proposta
e uma funcao `ap_*(cfg)` que MUDA SO A COPIA da configuracao.

Uso:  python -m regras.c3_grupo_2024_09_05 conj     (efeito de cada proposta do grupo nos 70 dias)
Metrica que decide (INSTRUCOES_CICLO3): R$/dia REPONDERADO (direcional 3,8% / nao-direcional 96,2%), nao a soma dos dias.
"""
import sys, json, pickle
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
import base, robo, robo_v3, cfg3, av

TETO = 590.0
H1 = pd.Timedelta(hours=1)
CACHE = Path(__file__).resolve().parent / "__pycache__" / "c3_cache70_0905.pkl"


# ------------------------------------------------------------------ dias e estratos
def dias70():
    du = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in du["ciclo0"]["dias"]]
    out += [(x["dia"], "c1") for x in du["ciclo1"]["dias"]]
    out += [(x["dia"], "c2") for x in du["ciclo2"]["dias"]]
    out += [(x["dia"], "c3") for x in du["ciclo3"]["dias"]]
    return out


EF = av.eficiencia_todos()
_N = len(EF)
FR2 = {"dir": sum(av.estrato(e) == "bom" for e in EF.values()) / _N}
FR2["nd"] = 1 - FR2["dir"]
D70 = dias70()
DIAS = [d for d, _ in D70]
CIC = np.array([c for _, c in D70])
EST2 = np.array(["dir" if EF[d] >= 0.25 else "nd" for d in DIAS])
M3 = CIC == "c3"


def repond(v):
    return sum(f * (v[EST2 == e].mean() if (EST2 == e).any() else 0.0) for e, f in FR2.items())


# ------------------------------------------------------------------ helpers (so passado)
def _hm(ctx): return ctx.t.hour * 60 + ctx.t.minute


def _vwap(h):
    tp = (h.high + h.low + h.close) / 3
    return float((tp * h.vol).sum() / h.vol.sum())


def _efic(ctx):
    """eficiencia do dia ate agora: |fecho - abertura| / soma das faixas M15."""
    h = ctx.hoje
    s = float((h.high - h.low).sum())
    return abs(float(h.close.iloc[-1] - h.open.iloc[0])) / s if s > 0 else 0.0


def rej_minima(ctx, k=0.6, nb=3, dist=1.5):
    """Rejeicao RECENTE da minima do dia: nas ultimas `nb` velas fechadas existe a que fez a minima do dia (tolerancia 5 pts) e fechou no
    terco superior da propria faixa (>= k acima da minima), e o fecho atual ainda esta a <= dist x ATR15 dessa minima.
    (nb=3 porque a FAZER de venda continua disparando nas velas seguintes: com nb=1 o veto so adiava a entrada em 15 min.)"""
    h = ctx.hoje
    if len(h) < 4: return False
    lo = float(h.low.min()); c = float(h.close.iloc[-1])
    if c - lo > dist * ctx.atr15: return False
    for i in range(1, nb + 1):
        u = h.iloc[-i]
        if u.low <= lo + 5 and u.high > u.low and (u.close - u.low) / (u.high - u.low) >= k:
            return True
    return False


def rej_maxima(ctx, k=0.6, nb=3, dist=1.5):
    h = ctx.hoje
    if len(h) < 4: return False
    hi = float(h.high.max()); c = float(h.close.iloc[-1])
    if hi - c > dist * ctx.atr15: return False
    for i in range(1, nb + 1):
        u = h.iloc[-i]
        if u.high >= hi - 5 and u.high > u.low and (u.high - u.close) / (u.high - u.low) >= k:
            return True
    return False


def _ord(ctx, lado, risco, alvo_k=None, alvo=None):
    p = float(ctx.hoje.close.iloc[-1]); s = 1 if lado == "compra" else -1
    r = min(risco, TETO)
    return dict(lado=lado, preco=p, stop=p - s * r, alvo=(p + s * alvo_k * r if alvo is None else float(alvo)), contratos=1)


# ------------------------------------------------------------------ G1 / G1m  (NAO_FAZER)
def g1_nf_vender_rejeicao_de_minima(ctx):
    """NAO_FAZER. Condicao de mercado: a vela que acaba de fechar fez a MINIMA do dia e fechou no terco superior da propria faixa
    (rejeicao da minima: o preco foi vendido ate la e recomprado na mesma vela). Vender no fecho dela e entrar contra a rejeicao
    com o suporte do dia colado: nos dois dias negativos o robo vendeu exatamente isso (09-05 10:00, pavio 90%; 10-25 13:30, pavio
    98%) e o preco devolveu 370-550 pts. Veto de venda em qualquer horario (o corte de >= 4 velas evita a abertura)."""
    if rej_minima(ctx):
        return _ord(ctx, "venda", 120, 2)


def g1m_nf_comprar_rejeicao_de_maxima(ctx):
    """NAO_FAZER (espelho de G1, definido sem olhar resultado). Nao comprar no fecho da vela que fez a MAXIMA do dia e rejeitou."""
    if rej_maxima(ctx):
        return _ord(ctx, "compra", 120, 2)


# ------------------------------------------------------------------ G2 / G2m  (FAZER)
def g2_fz_comprar_rejeicao_de_minima(ctx):
    """FAZER. Spring/rejeicao: a vela fez a minima do dia e fechou no terco superior (>= 60% da faixa) -> compra no fecho,
    stop 0,3 ATR15 abaixo da minima (teto 590), alvo 2R. Natureza: reversao em rejeicao de suporte. Quando existe a FAZER de venda no
    mesmo fecho, o robo cai em 'FAZER nos dois lados: nao entra' (so vale junto com G1 ou G3)."""
    if rej_minima(ctx, nb=1):
        u = ctx.hoje.iloc[-1]; p = float(u.close)
        return _ord(ctx, "compra", p - (float(u.low) - 0.3 * ctx.atr15), 2)


def g2m_fz_vender_rejeicao_de_maxima(ctx):
    """FAZER (espelho de G2)."""
    if rej_maxima(ctx, nb=1):
        u = ctx.hoje.iloc[-1]; p = float(u.close)
        return _ord(ctx, "venda", (float(u.high) + 0.3 * ctx.atr15) - p, 2)


# ------------------------------------------------------------------ G3  (conflito de lados)
def desempate_maioria(ctx, sins):
    """Lado com mais FAZER sinalizando; empate -> nao entra."""
    c = sum(1 for _, s, _ in sins if s["lado"] == "compra"); v = len(sins) - c
    return "compra" if c > v else ("venda" if v > c else None)


def desempate_vwap(ctx, sins):
    """Lado a favor do VWAP do dia: fecho acima do VWAP -> compra, abaixo -> venda."""
    h = ctx.hoje; c = float(h.close.iloc[-1]); v = _vwap(h)
    return "compra" if c > v else ("venda" if c < v else None)


def desempate_abertura(ctx, sins):
    """Lado a favor do deslocamento desde a abertura do dia."""
    h = ctx.hoje; d = float(h.close.iloc[-1] - h.open.iloc[0])
    return "compra" if d > 0 else ("venda" if d < 0 else None)


def desempate_vwap_e_maioria(ctx, sins):
    """So desempata quando VWAP e maioria apontam o mesmo lado."""
    a, b = desempate_vwap(ctx, sins), desempate_maioria(ctx, sins)
    return a if a == b else None


# ------------------------------------------------------------------ G4  (A2 de venda condicional)
def a2c_veto_venda_rompimento(ctx):
    """NAO_FAZER (versao CONDICIONAL do A2 do ciclo 1). O A2 deixou de vetar a venda abaixo da minima da 1a hora quando ela ja fechou
    >= 0,5 ATR15 abaixo (rompimento 'fundo'), e esse fundo liberou perdas em 5 dias do ciclo 3. Condicional, so com estado observavel
    na hora: o veto VOLTA quando o rompimento fundo acontece SEM dia direcional de baixa (fecho a menos de 0,35 ATRd abaixo da abertura)
    OU sem volume (vela < volume medio do dia). Rompimento fundo COM deslocamento de baixa e volume continua liberado."""
    h = ctx.hoje
    if len(h) < 5: return None
    p1 = h[h.index < h.index[0] + H1]
    lo = float(p1.low.min()); u = h.iloc[-1]; c = float(u.close)
    if c < lo - 0.5 * ctx.atr15:
        desloc = float(h.open.iloc[0]) - c
        if desloc < 0.35 * ctx.atrd or u.vol < h.vol.mean():
            return _ord(ctx, "venda", 120, 2)



# ------------------------------------------------------------------ G5 / G5m  (NAO_FAZER: espaco insuficiente)
def g5_nf_vender_sem_espaco(ctx):
    """NAO_FAZER. Condicao de mercado: venda com o fecho entre 0,25 e 1,0 ATR15 ACIMA da minima do dia, em dia ainda estreito (faixa < 1 ATRd).
    A minima do dia e o suporte; sobra menos de 1 ATR15 de espaco ate ele e o alvo (1 ATR ou mais) fica alem do suporte. Rompimento
    de minima (fecho a <= 0,25 ATR15 dela) nao entra no veto."""
    h = ctx.hoje
    if len(h) < 4: return None
    hi, lo, c = float(h.high.max()), float(h.low.min()), float(h.close.iloc[-1])
    if hi - lo < ctx.atrd and 0.25 * ctx.atr15 < c - lo < 1.0 * ctx.atr15:
        return _ord(ctx, "venda", 120, 2)


def g5m_nf_comprar_sem_espaco(ctx):
    """NAO_FAZER (espelho de G5)."""
    h = ctx.hoje
    if len(h) < 4: return None
    hi, lo, c = float(h.high.max()), float(h.low.min()), float(h.close.iloc[-1])
    if hi - lo < ctx.atrd and 0.25 * ctx.atr15 < hi - c < 1.0 * ctx.atr15:
        return _ord(ctx, "compra", 120, 2)


# ------------------------------------------------------------------ montagem
def _add_nf(nome, fn):
    def ap(cfg): cfg.nf = cfg.nf + [(nome, fn, None)]
    return ap


def _add_fz(nome, fn, ger=None):
    def ap(cfg): cfg.fz = cfg.fz + [(nome, fn, ger)]
    return ap


def _set_desempate(fn):
    def ap(cfg): cfg.desempate = fn
    return ap


# id -> (tipo, descricao, aplicador)
PROPS = {
    "G1":  ("NAO_FAZER", "nao vender no fecho de vela que rejeitou a minima do dia", _add_nf("c3g:G1", g1_nf_vender_rejeicao_de_minima)),
    "G1m": ("NAO_FAZER", "espelho: nao comprar no fecho de vela que rejeitou a maxima do dia", _add_nf("c3g:G1m", g1m_nf_comprar_rejeicao_de_maxima)),
    "G2":  ("FAZER", "comprar a rejeicao da minima do dia (spring), stop 0,3 ATR15 abaixo, alvo 2R", _add_fz("c3g:G2", g2_fz_comprar_rejeicao_de_minima)),
    "G2m": ("FAZER", "espelho: vender a rejeicao da maxima do dia", _add_fz("c3g:G2m", g2m_fz_vender_rejeicao_de_maxima)),
    "G3a": ("FAZER (conflito)", "FAZER nos dois lados: entra o lado da maioria", _set_desempate(desempate_maioria)),
    "G3b": ("FAZER (conflito)", "FAZER nos dois lados: entra o lado do VWAP", _set_desempate(desempate_vwap)),
    "G3c": ("FAZER (conflito)", "FAZER nos dois lados: entra o lado do deslocamento desde a abertura", _set_desempate(desempate_abertura)),
    "G3d": ("FAZER (conflito)", "FAZER nos dois lados: entra so se VWAP e maioria concordam", _set_desempate(desempate_vwap_e_maioria)),
    "G5":  ("NAO_FAZER", "nao vender entre 0,25 e 1 ATR15 acima da minima do dia em dia estreito (sem espaco)", _add_nf("c3g:G5", g5_nf_vender_sem_espaco)),
    "G5m": ("NAO_FAZER", "espelho: nao comprar entre 0,25 e 1 ATR15 abaixo da maxima do dia", _add_nf("c3g:G5m", g5m_nf_comprar_sem_espaco)),
    "G4":  ("NAO_FAZER", "A2 condicional: veto da venda de rompimento fundo volta sem deslocamento de baixa ou sem volume", _add_nf("c3g:G4", a2c_veto_venda_rompimento)),
}
REG = {}          # modulos de dia registram aqui seus PROPS (id -> tupla)
REG.update(PROPS)


def monta(ids):
    cfg = cfg3.monta(robo_v3.IDS)
    cfg.desempate = None
    for i in ids:
        REG[i][2](cfg)
    return cfg


# ------------------------------------------------------------------ motor (copia de cfg3.roda com desempate opcional)
def roda(dia, cfg):
    fz, nf, prio, post = cfg.fz, cfg.nf, cfg.prio, cfg.post
    desemp = getattr(cfg, "desempate", None)

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
        if len({s["lado"] for _, s, _ in sins}) > 1:
            lado = desemp(ctx, sins) if desemp else None
            if lado is None:
                info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
            sins = [x for x in sins if x[1]["lado"] == lado]
            info["nota"] = f"desempate -> {lado} "
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


def resultado(dia, ids):
    tr, log = roda(dia, monta(ids))
    ok = [x for x in tr if x.t_ent is not None]
    return dict(brl=round(sum(x.brl for x in ok), 2), ops=len(ok),
                trades=[(x.fonte[:45], x.lado, str(x.t_sinal.time()), x.motivo, round(x.brl, 2)) for x in ok])


# ------------------------------------------------------------------ avaliacao paralela com cache
def _um(args):
    modulos, ids, dia = args
    import importlib
    for m in modulos: importlib.import_module(m)
    return ids, dia, resultado(dia, list(ids))


def _cache():
    return pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}


def avalia(lista_ids, modulos=("regras.c3_grupo_2024_09_05",), dias=None, workers=8):
    """lista_ids: lista de tuplas de ids. Devolve {ids: {dia: resultado}} (cache em __pycache__)."""
    dias = dias or DIAS
    cache = _cache()
    falta = [(modulos, ids, d) for ids in dict.fromkeys(map(tuple, lista_ids)) for d in dias if (ids, d) not in cache]
    if falta:
        with ProcessPoolExecutor(workers) as ex:
            fut = [ex.submit(_um, a) for a in falta]
            for f in as_completed(fut):
                ids, d, r = f.result(); cache[(ids, d)] = r
        pickle.dump(cache, open(CACHE, "wb"))
    return {tuple(ids): {d: cache[(tuple(ids), d)] for d in dias} for ids in lista_ids}


def vec(res): return np.array([res[d]["brl"] for d in DIAS])


def linha(v, vb):
    d = v - vb
    return dict(total=float(v.sum()), d_total=float(d.sum()), rep=repond(v), d_rep=repond(v) - repond(vb),
                d_dir=float(d[EST2 == "dir"].mean()), d_nd=float(d[EST2 == "nd"].mean()), d_c3=float(d[M3].sum()),
                piora=int((d < -0.5).sum()), melhora=int((d > 0.5).sum()), pior_dia=float(v.min()))


def imprime(titulo, ids_list, modulos, dias_alvo=()):
    todos = [()] + [tuple(i) for i in ids_list]
    R = avalia(todos, modulos)
    vb = vec(R[()])
    print(f"{titulo}\nbase v3 (70 dias): total {vb.sum():.1f}  reponderado {repond(vb):.2f} R$/dia  dir {vb[EST2=='dir'].mean():.1f}  nd {vb[EST2=='nd'].mean():.1f}  c3 {vb[M3].sum():.1f}")
    print("ids | R$ nos dias-alvo | d_rep | d_dir | d_nd | d_total70 | d_c3(20) | melhora/piora | pior_dia")
    out = {}
    for ids in todos[1:]:
        v = vec(R[ids]); l = linha(v, vb)
        alvo = " ".join(f"{R[ids][d]['brl']:+.1f}" for d in dias_alvo)
        print(f"{'+'.join(ids):14s} | {alvo:18s} | {l['d_rep']:+7.2f} | {l['d_dir']:+7.2f} | {l['d_nd']:+6.2f} | {l['d_total']:+8.1f} | {l['d_c3']:+7.1f} | {l['melhora']}/{l['piora']} | {l['pior_dia']:.1f}", flush=True)
        out["+".join(ids)] = l
    return R, out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "conj":
        imprime("GRUPO", [(k,) for k in PROPS], ("regras.c3_grupo_2024_09_05",), ("2024-09-05", "2024-10-25"))
