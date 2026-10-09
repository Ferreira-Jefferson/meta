"""Motor multi-posicao para medir as mudancas. Com Cfg padrao (maxc=1) reproduz o robo v2 exatamente."""
import sys
import pandas as pd
sys.path.insert(0, ".")
import base, robo
from base import Trade, VALIDADE, FURA
from motor import estado, brl


class Cfg:
    nome = "base"
    veto_fn = None      # (nomes, s, est, ctx) -> True se o veto vale
    teto_fn = None      # (feitos, ctx) -> max ops
    cascata = False
    dois_fn = None      # (sins, est_fn, ctx) -> lado a seguir ou None
    maxc = 1            # posicoes simultaneas (mesmo lado)
    ajusta_fn = None    # (s, est, ctx) -> s ajustado
    pira_fn = None      # (abertas, s, est, ctx) -> True se pode somar posicao


def roda(dia, fz, nf, cfg):
    m1 = base.carrega(dia, 0); d = pd.Timestamp(dia)
    m1d = m1[m1.index.normalize() == d]
    fim = m1d.index[m1d["ultima_continua"]].max() if m1d["ultima_continua"].any() else m1d.index.max()
    trades, abertas = [], []
    for t, ctx in base.contextos(dia):
        for a in abertas:
            if a.t_ent is not None and a.gerir is not None:
                ctx.posicao = dict(lado=a.lado, preco=a.preco, stop=a.stop, alvo=a.alvo, t_ent=a.t_ent, contratos=a.contratos)
                ns = a.gerir(ctx, ctx.posicao)
                if ns is not None:
                    if a.lado == "compra" and ns > a.stop: a.stop = float(ns)
                    if a.lado == "venda" and ns < a.stop: a.stop = float(ns)
        feitos = [x for x in trades if x.t_ent is not None]
        teto = cfg.teto_fn(feitos, ctx) if cfg.teto_fn else 3
        pode_novo = t <= fim and len(feitos) + len([a for a in abertas if a.t_ent is None]) < teto
        if t <= fim and len(feitos) < teto and (not abertas or (cfg.maxc > 1 and len(abertas) < cfg.maxc)):
            ctx.ops_hoje = feitos
            sins = []
            for n, r, g in fz:
                s = robo._chama(r, ctx)
                if s and "erro" not in s: sins.append((n, s, g))
            if sins:
                vetos = {"compra": [], "venda": []}
                for n, r, g in nf:
                    s = robo._chama(r, ctx)
                    if s and "erro" not in s and s.get("lado") in vetos: vetos[s["lado"]].append(n)
                lados = {s["lado"] for _, s, _ in sins}
                if len(lados) > 1:
                    lado_ok = cfg.dois_fn(sins, ctx) if cfg.dois_fn else None
                    sins = [x for x in sins if x[1]["lado"] == lado_ok] if lado_ok else []
                for n, s, g in sins:
                    if robo._agressiva(s, ctx): continue
                    if abertas:   # piramide
                        if any(a.t_ent is None or a.lado != s["lado"] for a in abertas): break
                        if cfg.pira_fn is None or not cfg.pira_fn(abertas, s, estado(ctx, s["lado"]), ctx): break
                    vv = vetos[s["lado"]]
                    if vv and cfg.veto_fn is not None:
                        if not cfg.veto_fn(vv, s, estado(ctx, s["lado"]), ctx): vv = []
                    if vv:
                        if cfg.cascata: continue
                        break
                    if cfg.ajusta_fn: s = cfg.ajusta_fn(dict(s), estado(ctx, s["lado"]), ctx)
                    a = Trade(lado=s["lado"], contratos=min(2, int(s.get("contratos", 1))), t_sinal=t,
                              preco=float(s.get("preco", ctx.hoje.close.iloc[-1])), stop=float(s["stop"]),
                              alvo=(float(s["alvo"]) if s.get("alvo") is not None else None))
                    a.stop_ini = a.stop; a.fonte = n; a.gerir = g
                    trades.append(a); abertas.append(a)
                    break
        if abertas:
            janela = m1d[(m1d.index >= t) & (m1d.index < t + pd.Timedelta(minutes=15))]
            for ts, r in janela.iterrows():
                for a in list(abertas):
                    if a.t_sinal > ts: continue
                    if a.t_ent is None:
                        if ts >= a.t_sinal + VALIDADE: a.motivo = "nao_encheu"; abertas.remove(a); continue
                        if (r.low <= a.preco - FURA) if a.lado == "compra" else (r.high >= a.preco + FURA): a.t_ent = ts
                        continue
                    c = a.lado == "compra"
                    bs = (r.low <= a.stop) if c else (r.high >= a.stop)
                    ba = a.alvo is not None and ((r.high >= a.alvo + FURA) if c else (r.low <= a.alvo - FURA))
                    if bs:
                        px = min(r.open, a.stop) if c else max(r.open, a.stop)
                        a.t_sai, a.preco_sai, a.motivo = ts, px, "stop"; abertas.remove(a)
                    elif ba: a.t_sai, a.preco_sai, a.motivo = ts, a.alvo, "alvo"; abertas.remove(a)
                    elif ts >= fim: a.t_sai, a.preco_sai, a.motivo = ts, r.close, "fim"; abertas.remove(a)
    for a in abertas:
        if a.t_ent is None: a.motivo = "nao_encheu"
        else: a.t_sai, a.preco_sai, a.motivo = fim, float(m1d.loc[fim].close), "fim"
    return trades
