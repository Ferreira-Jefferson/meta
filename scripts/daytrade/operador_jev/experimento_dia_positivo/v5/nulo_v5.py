"""Nulo da v5 COM O MESMO PORTAO E AS MESMAS REGRAS: em cada dia, sorteia tantas velas quanto a v5 teve ORDENS PREENCHIDAS nesse dia, entre as velas de decisao que passam
o portao (eficiencia >= 0,20, lado a favor do dia); em cada vela sorteada, se ha flat e as regras 3 (risco 6%) e 4 (max 3, espera 2 velas apos perda) deixam, entra
com uma geometria (stop, alvo, maos, trail) sorteada das ordens preenchidas da v5; gestao = regra 1 sem respostas (manter ate stop/alvo/fim). Mesmo motor (SessaoL)."""
from __future__ import annotations
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
PAI = EXP.parent
for p in (str(PAI), str(EXP / "v4"), str(EXP / "v3")):
    if p not in sys.path:
        sys.path.insert(0, p)
import regras_v4 as rg  # noqa: E402

_MK = None
_CTX = None
_DIAS: dict = {}


def _init():
    global _MK, _CTX
    from mercado import Mercado
    from decisoes import Ctx
    _MK = Mercado.carregar()
    _CTX = Ctx(_MK)


def candidatos(mk, datas):
    from decisoes import ks_decisao
    out = {}
    for d in datas:
        dia = mk.dia(d, 1)
        lst = []
        for k in ks_decisao(dia, "09:15", "17:30"):
            er, desl = rg.er_dia(dia, k)
            if er >= rg.LIMIAR_ER and desl != 0:
                lst.append((k, 1 if desl > 0 else -1))
        out[d] = lst
    return out


def _sorteio(args):
    seed, cands, n_dia, geos = args
    from decisoes import VALIDADE_VELAS
    from decisoes_v4 import decisao_gestao_v4, CFG_V4
    from sessao_l import SessaoL
    from rodar_v3 import run_cls
    rng = np.random.default_rng(seed)
    tot = 0.0
    for d in sorted(cands):
        m = n_dia.get(d, 0)
        if m == 0 or not cands[d]:
            continue
        if d not in _DIAS:
            _DIAS[d] = _MK.dia(d, 1)
        dia = _DIAS[d]
        idx = rng.choice(len(cands[d]), min(m, len(cands[d])), replace=False)
        alvo_ks = {cands[d][i][0]: cands[d][i][1] for i in idx}
        gs = {k: geos[rng.integers(len(geos))] for k in alvo_ks}

        def decidir(k, s, dia=dia, alvo_ks=alvo_ks, gs=gs):
            if s.pos:
                if getattr(s, "exit_pend", None):
                    return dict(acao="manter"), {}
                return decisao_gestao_v4(None, _CTX, dia, k, s.pos, CFG_V4)
            if s.pend or k not in alvo_ks:
                return dict(acao="manter"), {}
            lado, g = alvo_ks[k], gs[k]
            ok, _ = rg.reentrada(s.trades, k)
            if not ok:
                return dict(acao="manter"), {}
            px = float(dia.m15[k, 3])
            n = g["n"]
            caixa = rg.CAIXA_INI_DIA + sum(t["brl"] for t in s.trades)
            n2, _, _ = rg.risco(px, px - lado * g["ds"], n, caixa)
            if n2 == 0:
                return dict(acao="manter"), {}
            return dict(acao="comprar_limite" if lado > 0 else "vender_limite", preco=px, stop=px - lado * g["ds"],
                        alvo=(px + lado * g["da"]) if g["da"] else None, contratos=n2, validade_velas=VALIDADE_VELAS, trail=g["trail"]), {}
        ss, _ = run_cls(_MK, dia, decidir, SessaoL)
        tot += sum(t["brl"] for t in ss.trades)
    return tot


def nulo(sess_v5, cands, sorteios, workers, seed0=7000):
    """sess_v5: lista de dicts {data, ordens, pontos, trades}. Devolve distribuicao do total (R$)."""
    from avaliar import _geometrias
    geos = _geometrias(sess_v5)
    n_dia = {pd.Timestamp(s["data"]): sum(1 for o in s["ordens"] if o.get("fill")) for s in sess_v5}
    cands = {pd.Timestamp(d): v for d, v in cands.items()}
    out = np.zeros(sorteios)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        futs = {ex.submit(_sorteio, (seed0 + i, cands, n_dia, geos)): i for i in range(sorteios)}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    return out, len(geos)
