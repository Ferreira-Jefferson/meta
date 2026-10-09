"""Robô composto: junta TODAS as regras de regras/r_*.py (ciclo 1 do CICLO.md).

Em cada vela M15 fechada, sem posição:
  - avalia todas as FAZER e todas as NAO_FAZER (ordem fixa: arquivo por data, depois ordem na lista);
  - NAO_FAZER que sinaliza um lado veta esse lado nesta vela;
  - FAZER nos DOIS lados na mesma vela: não entra;
  - senão entra a primeira FAZER cujo lado não está vetado (e cuja limitada não é agressiva), com o
    stop/alvo/preço/contratos e o `gerir` dela.
1 posição por vez, máx 3 operações (enchidas) por dia. Execução idêntica à de base.simula_dia.
As regras recebem o estado do ROBÔ (ctx.ops_hoje = operações enchidas do robô).
"""
import importlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import base
from base import Trade, VALIDADE, FURA

MAX_OPS = 3


def carrega_regras():
    fz, nf = [], []
    for p in sorted((AQUI / "regras").glob("r_*.py")):
        m = importlib.import_module(f"regras.{p.stem}")
        tag = p.stem[2:]
        fz += [(f"{tag}:{n}", r, g) for n, r, g in m.FAZER]
        nf += [(f"{tag}:{n}", r, g) for n, r, g in m.NAO_FAZER]
    return fz, nf


def _chama(regra, ctx):
    try:
        return regra(ctx)
    except Exception as e:  # regra quebrada não derruba o dia; fica registrada
        return {"erro": repr(e)}


def _roda(dia, decide, max_ops=MAX_OPS):
    """Motor = base.simula_dia com decisão composta. decide(ctx)->(sinal|None, info|None, gerir|None).
    Devolve (trades, log). Cada trade ganha .fonte e .gerir."""
    m1 = base.carrega(dia, 0)
    d = pd.Timestamp(dia)
    m1d = m1[m1.index.normalize() == d]
    fim = m1d.index[m1d["ultima_continua"]].max() if m1d["ultima_continua"].any() else m1d.index.max()
    trades, log, aberta = [], [], None
    for t, ctx in base.contextos(dia):
        if aberta is not None and aberta.t_ent is not None and aberta.gerir is not None:
            ctx.posicao = dict(lado=aberta.lado, preco=aberta.preco, stop=aberta.stop, alvo=aberta.alvo,
                               t_ent=aberta.t_ent, contratos=aberta.contratos)
            ns = aberta.gerir(ctx, ctx.posicao)
            if ns is not None:
                if aberta.lado == "compra" and ns > aberta.stop: aberta.stop = float(ns)
                if aberta.lado == "venda" and ns < aberta.stop: aberta.stop = float(ns)
        feitos = [x for x in trades if x.t_ent is not None]
        if aberta is None and t <= fim and len(feitos) < max_ops:
            ctx.ops_hoje = feitos
            s, info, ger = decide(ctx)
            if info is not None:
                info["t"] = str(t.time()); log.append(info)
            if s:
                p = float(s.get("preco", ctx.hoje.close.iloc[-1]))
                aberta = Trade(lado=s["lado"], contratos=min(2, int(s.get("contratos", 1))), t_sinal=t, preco=p,
                               stop=float(s["stop"]), alvo=(float(s["alvo"]) if s.get("alvo") is not None else None))
                aberta.stop_ini = aberta.stop
                aberta.fonte = info["entrou"] if info else "?"
                aberta.gerir = ger
                trades.append(aberta)
        if aberta is not None:
            janela = m1d[(m1d.index >= t) & (m1d.index < t + pd.Timedelta(minutes=15))]
            for ts, r in janela.iterrows():
                if aberta.t_ent is None:
                    if ts >= aberta.t_sinal + VALIDADE:
                        aberta.motivo = "nao_encheu"; aberta = None; break
                    enche = (r.low <= aberta.preco - FURA) if aberta.lado == "compra" else (r.high >= aberta.preco + FURA)
                    if enche: aberta.t_ent = ts
                    continue
                c = aberta.lado == "compra"
                bateu_stop = (r.low <= aberta.stop) if c else (r.high >= aberta.stop)
                bateu_alvo = aberta.alvo is not None and ((r.high >= aberta.alvo + FURA) if c else (r.low <= aberta.alvo - FURA))
                if bateu_stop:
                    px = min(r.open, aberta.stop) if c else max(r.open, aberta.stop)
                    aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, px, "stop"; aberta = None; break
                if bateu_alvo:
                    aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, aberta.alvo, "alvo"; aberta = None; break
                if ts >= fim:
                    aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, r.close, "fim"; aberta = None; break
    if aberta is not None:
        if aberta.t_ent is None:
            aberta.motivo = "nao_encheu"
        else:
            aberta.t_sai, aberta.preco_sai, aberta.motivo = fim, float(m1d.loc[fim].close), "fim"
    return trades, log


def _agressiva(s, ctx):
    p = float(s.get("preco", ctx.hoje.close.iloc[-1])); ult = float(ctx.hoje.close.iloc[-1])
    return (s["lado"] == "compra" and p > ult) or (s["lado"] == "venda" and p < ult)


def roda_robo(dia, fz=None, nf=None):
    if fz is None:
        fz, nf = carrega_regras()
    contra = []  # entradas vetadas (candidata que teria entrado sem veto)

    def decide(ctx):
        sins = []
        for n, r, g in fz:
            s = _chama(r, ctx)
            if s and "erro" not in s: sins.append((n, s, g))
        if not sins:
            return None, None, None
        vetos = {"compra": [], "venda": []}
        for n, r, g in nf:
            s = _chama(r, ctx)
            if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
        info = dict(fazer=[(n, s["lado"]) for n, s, g in sins], vetos={k: v for k, v in vetos.items() if v},
                    entrou=None, nota="")
        lados = {s["lado"] for _, s, _ in sins}
        if len(lados) > 1:
            info["nota"] = "FAZER nos dois lados: nao entra"; return None, info, None
        for n, s, g in sins:
            if _agressiva(s, ctx):
                info["nota"] += f"[{n} limitada agressiva] "; continue
            if vetos[s["lado"]]:
                info["nota"] += f"[{n} VETADA por {len(vetos[s['lado']])}] "
                contra.append(dict(t=ctx.t, regra=n, s=s, g=g, vetos=list(vetos[s["lado"]])))
                return None, info, None  # a primeira candidata valida foi vetada: nao cai para a proxima
            info["entrou"] = n
            return s, info, g
        return None, info, None

    trades, log = _roda(dia, decide)
    return trades, log, contra


def simula_vetada(dia, c):
    """Simula a entrada vetada isolada (mesmo motor, sem outras regras) para saber o que teria rendido."""
    alvo_t = c["t"]; usada = []

    def decide(ctx):
        if ctx.t == alvo_t and not usada:
            usada.append(1)
            return c["s"], dict(entrou=c["regra"]), c["g"]
        return None, None, None
    tr, _ = _roda(dia, decide, max_ops=1)
    ok = [x for x in tr if x.t_ent is not None]
    return dict(ops=len(ok), brl=round(sum(x.brl for x in ok), 2), motivo=ok[0].motivo if ok else "nao_encheu")


def trade_dict(x):
    return dict(fonte=x.fonte, lado=x.lado, contratos=x.contratos, sinal=str(x.t_sinal.time()), ent=str(x.t_ent.time()),
                sai=str(x.t_sai.time()), preco=x.preco, preco_sai=x.preco_sai, motivo=x.motivo, pts=round(x.pts, 1),
                brl=round(x.brl, 2))


def eficiencia(dia):
    m1 = base.carrega(dia, 0); m1 = m1[m1.index.normalize() == pd.Timestamp(dia)]
    b = base._m15(m1)
    return abs(b.close.iloc[-1] - b.open.iloc[0]) / float((b.high - b.low).sum())


def sorteia_ciclo1(seed=20261014):
    m1 = base.m1_tudo()
    dias = pd.Series(m1.index.normalize().unique())
    dias = dias[(dias >= "2022-03-01") & (dias <= "2025-09-30")]
    usados = set(json.load(open(AQUI / "dias.json"))["dias"])
    cand = [str(d.date()) for d in dias if str(d.date()) not in usados]
    efs = {}
    for d in cand:
        mm = m1[m1.index.normalize() == pd.Timestamp(d)]
        if len(mm) < 300: continue
        efs[d] = eficiencia(d)
    bons = sorted(d for d, e in efs.items() if e >= 0.30)
    ruins = sorted(d for d, e in efs.items() if e < 0.15)
    rng = np.random.default_rng(seed)
    sb = sorted(rng.choice(bons, 10, replace=False).tolist()); sr = sorted(rng.choice(ruins, 10, replace=False).tolist())
    return sb, sr, efs, len(bons), len(ruins)
