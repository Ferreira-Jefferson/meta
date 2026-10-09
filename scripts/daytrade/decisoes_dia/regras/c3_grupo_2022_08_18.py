"""Ciclo 3 - grupo dos dias 2022-08-18 e 2022-09-21 (negativos do robo_v3).

Duas coisas neste arquivo:
 1. Propostas COMUNS aos dois dias (G1..G3), alem das 10+10 regras de cada dia (c3_2022_08_18.py e c3_2022_09_21.py):
    G1a  FAZER nos dois lados -> entra no lado da perna do dia (sinal de fecho-abertura), em vez de nao entrar.
    G1b  FAZER nos dois lados -> entra no unico lado que nao esta vetado (se exatamente um estiver livre).
    G2   FAZER compra de exaustao com volume (c3_2022_09_21 F1) + falha da minima de ontem (F3) + spring (F2): "compra a favor da reversao".
    G3   A2 condicional (c3_2022_09_21 N1): veto de venda em faixa de rotacao apos 12h.
 2. O avaliador: `python -m regras.c3_grupo_2022_08_18` roda cada proposta ISOLADA sobre o robo_v3 nos 70 dias de dias_usados.json
    (ciclos 0 a 3) e imprime: R$ total, R$/dia REPONDERADO (2 estratos: direcional ef >= 0,25 = 3,8% / nao-direcional = 96,2%), delta contra o
    v3, delta no estrato nao-direcional, delta nos 20 dias do ciclo 3 (os unicos sorteados ao calendario real), dias piores/melhores e pior dia.
    Resultado em analises/c3_avaliacao_70.json.
Nenhum arquivo existente e editado. Nenhum dia fora de dias_usados.json e rodado.
"""
import sys, json
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ)); sys.path.insert(0, str(RAIZ / "ciclo3"))
import numpy as np
import pandas as pd

IDS_V3 = ["C8", "C7", "C6", "C4"]
PULL = "2022_11_16:venda pullback EMA20 em baixa"


# ------------------------------------------------------------------ motor com variante para "FAZER nos dois lados"
def roda_ambos(dia, cfg, modo):
    """Copia de cfg3.roda; unica diferenca: quando ha FAZER nos dois lados, `modo` decide (perna | livre)."""
    import robo, cfg3
    fz, nf, prio, post = cfg.fz, cfg.nf, cfg.prio, cfg.post

    def decide(ctx):
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
            if modo == "perna":
                h = ctx.hoje; d = float(h.close.iloc[-1] - h.open.iloc[0])
                lado = "compra" if d > 0 else "venda"
            else:  # livre
                livres = [l for l in lados if not vetos[l]]
                if len(livres) != 1:
                    info["nota"] = "dois lados: nao entra"; return None, info, None
                lado = livres[0]
            sins = [x for x in sins if x[1]["lado"] == lado]
        for n, s, g in sins:
            if robo._agressiva(s, ctx):
                info["nota"] += f"[{n} limitada agressiva] "; continue
            if vetos[s["lado"]]:
                info["nota"] += f"[{n} VETADA] "; return None, info, None
            info["entrou"] = n
            for f in post: s, g = f(n, s, g, ctx)
            return s, info, g
        return None, info, None
    return robo._roda(dia, decide)


# ------------------------------------------------------------------ propostas: nome -> (aplica(cfg), modo_ambos, descricao)
def _fz(fn, nome):
    def ap(cfg): cfg.fz = cfg.fz + [(nome, fn, None)]
    return ap


def _nf(fn, nome):
    def ap(cfg): cfg.nf = cfg.nf + [(nome, fn, None)]
    return ap


def _sub_pull(fn):
    def ap(cfg):
        assert any(n == PULL for n, _, _ in cfg.fz)
        cfg.fz = [(n, fn, g) if n == PULL else (n, r, g) for n, r, g in cfg.fz]
    return ap


def _noop(cfg): pass


def propostas():
    from regras import c3_2022_08_18 as a, c3_2022_09_21 as b
    P = {}
    for k, (n, f, g) in enumerate(a.FAZER, 1):
        P[f"A-F{k}"] = (_sub_pull(f) if k == 5 else _fz(f, f"c3a:{n}"), None, "0818 FAZER: " + n)
    for k, (n, f, g) in enumerate(a.NAO_FAZER, 1):
        P[f"A-N{k}"] = (_nf(f, f"c3a:{n}"), None, "0818 NAO: " + n)
    for k, (n, f, g) in enumerate(b.FAZER, 1):
        P[f"B-F{k}"] = (_fz(f, f"c3b:{n}"), None, "0921 FAZER: " + n)
    for k, (n, f, g) in enumerate(b.NAO_FAZER, 1):
        P[f"B-N{k}"] = (_nf(f, f"c3b:{n}"), None, "0921 NAO: " + n)
    P["G1a"] = (_noop, "perna", "FAZER nos 2 lados -> lado da perna do dia")
    P["G1b"] = (_noop, "livre", "FAZER nos 2 lados -> lado nao vetado")

    def g2(cfg):
        for f, n in ((b.f1_compra_exaustao_com_volume_na_minima, "F1"), (b.f3_compra_falha_da_minima_de_ontem, "F3"),
                     (b.f2_compra_spring_na_minima_do_dia, "F2")):
            cfg.fz = cfg.fz + [(f"c3b:{n}", f, None)]
    P["G2"] = (g2, None, "pacote de compra de reversao (B-F1+B-F2+B-F3)")
    P["G3"] = (_nf(b.n1_vender_em_faixa_de_rotacao_apos_12h, "c3b:A2cond"), None, "A2 condicional (= B-N1)")
    return _extras(P)



# ------------------------------------------------------------------ rodada 2 (POS-HOC: desenhada depois de ver os 70 dias; ler como hipotese, nao como validacao)
def _prio(fn, nome):
    def ap(cfg): cfg.prio = cfg.prio + [(nome, fn, None)]
    return ap


def n_vende_faixa_estreita(ctx):
    """H4: A2 condicional MAIS ESTREITO que c3_2022_09_21.N1: apos 12:00, eficiencia do dia < 0,12 e faixa das 8 velas anteriores <= 2 ATR15."""
    h = ctx.hoje
    if ctx.t.hour < 12 or len(h) < 10: return None
    a = h.iloc[-9:-1]; s = float((h.high - h.low).sum())
    ef = abs(float(h.close.iloc[-1] - h.open.iloc[0])) / s if s > 0 else 0.0
    if ef < 0.12 and float(a.high.max() - a.low.min()) <= 2 * ctx.atr15:
        return dict(lado="venda", stop=float(h.close.iloc[-1]) + 300, alvo=None)


def n_compra_meio_da_faixa(ctx):
    """H5: veto de compra no MEIO da faixa do dia (30%-70%) entre 10:00 e 11:00 com eficiencia do dia < 0,2 (versao de A-N2 que age sobre o
    trade real de 18/08: a eficiencia das 10:15 era 0,16, nao < 0,1)."""
    h = ctx.hoje; hm = ctx.t.hour * 60 + ctx.t.minute
    if not (600 <= hm <= 660) or len(h) < 4: return None
    hi, lo = float(h.high.max()), float(h.low.min())
    s = float((h.high - h.low).sum())
    ef = abs(float(h.close.iloc[-1] - h.open.iloc[0])) / s if s > 0 else 0.0
    if hi > lo and 0.3 <= (float(h.close.iloc[-1]) - lo) / (hi - lo) <= 0.7 and ef < 0.2:
        return dict(lado="compra", stop=float(h.close.iloc[-1]) - 300, alvo=None)


def _extras(P):
    from regras import c3_2022_09_21 as b
    P["H1"] = (_prio(b.f1_compra_exaustao_com_volume_na_minima, "c3b:F1p"), None, "B-F1 como PRIORITARIA (fora dos vetos de compra de queda)")
    P["H2"] = (_prio(b.f3_compra_falha_da_minima_de_ontem, "c3b:F3p"), None, "B-F3 como PRIORITARIA")
    def h3(cfg):
        cfg.prio = cfg.prio + [("c3b:F1p", b.f1_compra_exaustao_com_volume_na_minima, None), ("c3b:F3p", b.f3_compra_falha_da_minima_de_ontem, None)]
    P["H3"] = (h3, None, "B-F1 + B-F3 prioritarias")
    P["H4"] = (_nf(n_vende_faixa_estreita, "c3:H4"), None, "A2 condicional estreito (efic<0,12, faixa 2h<=2 ATR15)")
    P["H5"] = (_nf(n_compra_meio_da_faixa, "c3:H5"), None, "veto compra meio da faixa, efic<0,2")
    def h6(cfg):
        h3(cfg); cfg.nf = cfg.nf + [("c3:H4", n_vende_faixa_estreita, None), ("c3:H5", n_compra_meio_da_faixa, None)]
    P["H6"] = (h6, None, "H3+H4+H5")
    def h7(cfg):
        cfg.nf = cfg.nf + [("c3:H4", n_vende_faixa_estreita, None), ("c3b:N5", b.n5_vender_minima_nova_com_volume_extremo, None)]
    P["H7"] = (h7, None, "H4 + B-N5 (os dois vetos que nao pioram o estrato nao-direcional)")
    return P


# ------------------------------------------------------------------ avaliacao
def _um(args):
    chave, dia = args
    import cfg3
    ap, modo, _ = propostas()[chave] if chave != "v3" else (_noop, None, "")
    cfg = cfg3.monta(IDS_V3)
    ap(cfg)
    if modo is None:
        r = cfg3.resultado_dia(dia, cfg)
        return chave, dia, r["brl"], r["ops"]
    tr, log = roda_ambos(dia, cfg, modo)
    ok = [x for x in tr if x.t_ent is not None]
    return chave, dia, round(sum(x.brl for x in ok), 2), len(ok)


def dias70():
    du = json.load(open(RAIZ / "dias_usados.json"))
    out = [(d, "c0") for d in du["ciclo0"]["dias"]]
    for c in ("ciclo1", "ciclo2", "ciclo3"):
        out += [(x["dia"], c.replace("ciclo", "c")) for x in du[c]["dias"]]
    return out


def main(chaves=None):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import pickle
    D = dias70(); DIAS = [d for d, _ in D]; CIC = np.array([c for _, c in D])
    ef = json.load(open(RAIZ / "ciclo3" / "ef_todos.json"))
    N = len(ef); f_dir = sum(e >= 0.25 for e in ef.values()) / N; FR = {"dir": f_dir, "nd": 1 - f_dir}
    EST = np.array(["dir" if ef[d] >= 0.25 else "nd" for d in DIAS])
    M3 = CIC == "c3"

    def rep(v): return sum(FR[e] * v[EST == e].mean() for e in FR)
    cache_f = RAIZ / "ciclo3" / "cache_c3_grupo.pkl"
    cache = pickle.load(open(cache_f, "rb")) if cache_f.exists() else {}
    P = propostas()
    chaves = ["v3"] + list(chaves or P.keys())
    falta = [(k, d) for k in chaves for d in DIAS if (k, d) not in cache]
    if falta:
        with ProcessPoolExecutor(10) as ex:
            fut = [ex.submit(_um, a) for a in falta]
            for i, f in enumerate(as_completed(fut)):
                k, d, brl, ops = f.result(); cache[(k, d)] = (brl, ops)
                if i % 100 == 0: print(f"  {i}/{len(falta)}", flush=True)
        pickle.dump(cache, open(cache_f, "wb"))
    vb = np.array([cache[("v3", d)][0] for d in DIAS])
    print(f"v3: total {vb.sum():.2f}  rep {rep(vb):.2f}  nd {vb[EST=='nd'].mean():.2f}  dir {vb[EST=='dir'].mean():.2f}  "
          f"c3 {vb[M3].sum():.2f}  pior dia {vb.min():.2f}  (dias dir={int((EST=='dir').sum())}, nd={int((EST=='nd').sum())})")
    saida = {}
    print(f"{'prop':6s} {'dRep':>8s} {'dNd':>8s} {'dDir':>8s} {'dTot':>9s} {'dC3':>8s} {'d50':>8s} {'pior/mel':>9s} {'piorDia':>9s}  desc")
    for k in chaves[1:]:
        v = np.array([cache[(k, d)][0] for d in DIAS]); d = v - vb
        l = dict(d_rep=rep(v) - rep(vb), d_nd=d[EST == "nd"].mean(), d_dir=d[EST == "dir"].mean(), d_tot=d.sum(), d_c3=d[M3].sum(),
                 d_50=d[~M3].sum(), pior=int((d < -0.5).sum()), melhor=int((d > 0.5).sum()), pior_dia=v.min(),
                 dias_mudados=[DIAS[i] for i in np.nonzero(np.abs(d) > 0.5)[0]], d_por_dia={DIAS[i]: float(d[i]) for i in np.nonzero(np.abs(d) > 0.5)[0]})
        saida[k] = l
        print(f"{k:6s} {l['d_rep']:+8.2f} {l['d_nd']:+8.2f} {l['d_dir']:+8.2f} {l['d_tot']:+9.1f} {l['d_c3']:+8.1f} {l['d_50']:+8.1f} "
              f"{l['pior']:>4d}/{l['melhor']:<4d} {l['pior_dia']:9.1f}  {P[k][2]}", flush=True)
    json.dump(dict(v3=dict(total=float(vb.sum()), rep=float(rep(vb))), props=saida), open(RAIZ / "analises" / "c3_avaliacao_70.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
