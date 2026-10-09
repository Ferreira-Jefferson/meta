"""Motor parametrizavel do robo v2 + registro de TODAS as candidatas (inclusive as bloqueadas) + simulacao isolada.
Baseline (cfg padrao) reproduz robo_v2.roda_v2(estrutural=False)."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
PAI = AQUI.parent
sys.path.insert(0, str(PAI))
import base, robo, robo_v2
from base import Trade, VALIDADE, FURA, CUSTO, RS_PT


def dias50():
    du = json.load(open(PAI / "dias_usados.json"))
    out = [(d, "c0", 0) for d in du["ciclo0"]["dias"]]
    for k, n in (("ciclo1", 1), ("ciclo2", 2)):
        out += [(x["dia"], x["tipo"], n) for x in du[k]["dias"]]
    return out


def estado(ctx, lado):
    h = ctx.hoje; s = 1 if lado == "compra" else -1
    c = float(h.close.iloc[-1]); o = float(h.open.iloc[0]); atr = ctx.atr15 or np.nan
    rng = float((h.high - h.low).sum())
    ef = abs(c - o) / rng if rng > 0 else 0.0
    m = h[h.index.time < pd.Timestamp("12:00").time()]
    rm = float((m.high - m.low).sum()) if len(m) else 0.0
    efm = abs(float(m.close.iloc[-1]) - float(m.open.iloc[0])) / rm if rm > 0 else 0.0
    ult = h.tail(4)
    vol_rec = float((ult.high - ult.low).mean()) / atr
    v = ctx.m15.vol
    vol_rel = float(v.iloc[-1]) / float(v.iloc[-21:-1].mean()) if len(v) > 5 else np.nan
    m1h = ctx.m1[ctx.m1.index.normalize() == ctx.t.normalize()]
    tp = (m1h.high + m1h.low + m1h.close) / 3
    vw = float((tp * m1h.real_volume).sum() / max(m1h.real_volume.sum(), 1))
    cl = ctx.m15.close
    perna = float(cl.iloc[-1] - cl.iloc[-9]) / atr if len(cl) > 9 else np.nan
    return dict(ef_dia=ef, ef_manha=efm, desloc=s * (c - o) / atr, vol_rec=vol_rec, vol_rel=vol_rel,
                hora=ctx.t.hour + ctx.t.minute / 60, dist_vwap=s * (c - vw) / atr, perna=s * perna,
                dir_dia=(1 if c > o else -1) * s)


def sim_fast(m1d, fim, t_sinal, s):
    """Simula entrada isolada (sem gerir). Mesma semantica do motor base."""
    p = float(s.get("preco")); stop = float(s["stop"]); alvo = s.get("alvo"); alvo = None if alvo is None else float(alvo)
    c = s["lado"] == "compra"; ctr = min(2, int(s.get("contratos", 1)))
    j = m1d[m1d.index >= t_sinal]
    ent = None; px = None; mot = None
    for ts, r in zip(j.index, j.itertuples()):
        if ent is None:
            if ts >= t_sinal + VALIDADE: return 0.0, "nao_encheu", None
            if (r.low <= p - FURA) if c else (r.high >= p + FURA): ent = ts
            continue
        bs = (r.low <= stop) if c else (r.high >= stop)
        ba = alvo is not None and ((r.high >= alvo + FURA) if c else (r.low <= alvo - FURA))
        if bs:
            px = min(r.open, stop) if c else max(r.open, stop); mot = "stop"; break
        if ba: px = alvo; mot = "alvo"; break
        if ts >= fim: px = r.close; mot = "fim"; break
    if ent is None: return 0.0, "nao_encheu", None
    if px is None:
        px = float(m1d.loc[fim].close); mot = "fim"
    sg = 1 if c else -1
    return ((px - p) * sg - CUSTO) * RS_PT * ctr, mot, ent


def sim_cand(dia, c, m1d, fim):
    s = dict(c["s"]); s.setdefault("preco", None)
    if s["preco"] is None: s["preco"] = c["preco"]
    if c["g"] is None:
        brl, mot, ent = sim_fast(m1d, fim, c["t"], s)
        return dict(brl=round(brl, 2), motivo=mot, ent=str(ent.time()) if ent is not None else None)
    r = robo.simula_vetada(dia, c)
    return dict(brl=r["brl"], motivo=r["motivo"], ent=None)


class Cfg:
    veto_fn = None      # (nomes, s, est, ctx) -> bool (True = veto vale). None = sempre
    teto_fn = None      # (feitos, ctx) -> max ops permitido. None = 3
    cascata = False     # se a candidata e vetada, tenta a proxima
    extra = None        # (ctx, feitos) -> lista de sinais extras (n, s, g)


def roda(dia, fz, nf, cfg=None, log_cand=False):
    cfg = cfg or Cfg()
    m1 = base.carrega(dia, 0); d = pd.Timestamp(dia)
    m1d = m1[m1.index.normalize() == d]
    fim = m1d.index[m1d["ultima_continua"]].max() if m1d["ultima_continua"].any() else m1d.index.max()
    trades, aberta, cands = [], None, []
    for t, ctx in base.contextos(dia):
        if aberta is not None and aberta.t_ent is not None and aberta.gerir is not None:
            ctx.posicao = dict(lado=aberta.lado, preco=aberta.preco, stop=aberta.stop, alvo=aberta.alvo, t_ent=aberta.t_ent, contratos=aberta.contratos)
            ns = aberta.gerir(ctx, ctx.posicao)
            if ns is not None:
                if aberta.lado == "compra" and ns > aberta.stop: aberta.stop = float(ns)
                if aberta.lado == "venda" and ns < aberta.stop: aberta.stop = float(ns)
        feitos = [x for x in trades if x.t_ent is not None]
        teto = cfg.teto_fn(feitos, ctx) if cfg.teto_fn else 3
        livre = aberta is None and t <= fim and len(feitos) < teto
        if t <= fim and (livre or log_cand):
            ctx.ops_hoje = feitos
            sins = []
            for n, r, g in fz:
                s = robo._chama(r, ctx)
                if s and "erro" not in s: sins.append((n, s, g))
            if cfg.extra:
                sins += cfg.extra(ctx, feitos)
            if sins:
                vetos = {"compra": [], "venda": []}
                for n, r, g in nf:
                    s = robo._chama(r, ctx)
                    if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
                lados = {s["lado"] for _, s, _ in sins}

                def reg(n, s, g, causa):
                    if log_cand:
                        cands.append(dict(t=ctx.t, regra=n, s=s, g=g, lado=s["lado"], causa=causa,
                                          preco=float(s.get("preco", ctx.hoje.close.iloc[-1])),
                                          vetos=list(vetos[s["lado"]]), est=estado(ctx, s["lado"]), n_ops=len(feitos),
                                          pos_lado=(aberta.lado if aberta is not None else None),
                                          pos_enchida=(aberta.t_ent is not None if aberta is not None else None)))
                if not livre:
                    causa = "posicao_aberta" if aberta is not None else "teto_ops"
                    for n, s, g in sins:
                        if not robo._agressiva(s, ctx): reg(n, s, g, causa)
                elif len(lados) > 1:
                    for n, s, g in sins:
                        if not robo._agressiva(s, ctx): reg(n, s, g, "dois_lados")
                else:
                    entrou = False
                    for n, s, g in sins:
                        if robo._agressiva(s, ctx): continue
                        if entrou: reg(n, s, g, "outra_mesma_vela"); continue
                        vv = vetos[s["lado"]]
                        if vv and cfg.veto_fn is not None:
                            est = estado(ctx, s["lado"])
                            if not cfg.veto_fn(vv, s, est, ctx): vv = []
                        if vv:
                            reg(n, s, g, "veto")
                            if cfg.cascata: continue
                            break
                        aberta = Trade(lado=s["lado"], contratos=min(2, int(s.get("contratos", 1))), t_sinal=t,
                                       preco=float(s.get("preco", ctx.hoje.close.iloc[-1])), stop=float(s["stop"]),
                                       alvo=(float(s["alvo"]) if s.get("alvo") is not None else None))
                        aberta.stop_ini = aberta.stop; aberta.fonte = n; aberta.gerir = g
                        trades.append(aberta); entrou = True
                        if not log_cand: break
        if aberta is not None:
            janela = m1d[(m1d.index >= t) & (m1d.index < t + pd.Timedelta(minutes=15))]
            for ts, r in janela.iterrows():
                if aberta.t_ent is None:
                    if ts >= aberta.t_sinal + VALIDADE: aberta.motivo = "nao_encheu"; aberta = None; break
                    if (r.low <= aberta.preco - FURA) if aberta.lado == "compra" else (r.high >= aberta.preco + FURA): aberta.t_ent = ts
                    continue
                c = aberta.lado == "compra"
                bs = (r.low <= aberta.stop) if c else (r.high >= aberta.stop)
                ba = aberta.alvo is not None and ((r.high >= aberta.alvo + FURA) if c else (r.low <= aberta.alvo - FURA))
                if bs:
                    px = min(r.open, aberta.stop) if c else max(r.open, aberta.stop)
                    aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, px, "stop"; aberta = None; break
                if ba: aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, aberta.alvo, "alvo"; aberta = None; break
                if ts >= fim: aberta.t_sai, aberta.preco_sai, aberta.motivo = ts, r.close, "fim"; aberta = None; break
    if aberta is not None:
        if aberta.t_ent is None: aberta.motivo = "nao_encheu"
        else: aberta.t_sai, aberta.preco_sai, aberta.motivo = fim, float(m1d.loc[fim].close), "fim"
    return trades, cands, m1d, fim


def brl(trades):
    return round(sum(x.brl for x in trades if x.t_ent is not None), 2)
