"""Nulo de entradas aleatorias COM O MESMO PORTAO da v4: cada geometria (stop, alvo, maos, trail) das ordens preenchidas vira uma entrada sorteada, mas so entre as
velas (dia, vela) que passam o portao (eficiencia direcional do dia >= limiar) e SO NO LADO A FAVOR do dia (fech - abertura). Mesmo motor (SessaoL), mesma validade.
Serve para separar "portao bom" de "Jev bom": se o resultado da v4 fica dentro da distribuicao deste nulo, o ganho (se houver) e do portao, nao do Jev."""
from __future__ import annotations
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
AQUI = Path(__file__).resolve().parent
EXP = AQUI.parent
PAI = EXP.parent
for p in (str(PAI), str(AQUI), str(EXP / "v3")):
    if p not in sys.path:
        sys.path.insert(0, p)
import regras_v4 as rg  # noqa: E402

_MK = None
_CTX = None
_DIAS: dict = {}


def _init_worker():
    global _MK, _CTX
    from mercado import Mercado
    from decisoes import Ctx
    _MK = Mercado.carregar()
    _CTX = Ctx(_MK)


def candidatos(mk, datas, hora_ini="09:15", hora_fim="17:30", limiar=rg.LIMIAR_ER, so_portao=True):
    """{dia: [(k, lado)]} das velas de decisao. so_portao=True: so as que passam o portao e no lado a favor; False: todas, com os dois lados."""
    from decisoes import ks_decisao
    out = {}
    for d in datas:
        dia = mk.dia(d, 1)
        lst = []
        for k in ks_decisao(dia, hora_ini, hora_fim):
            er, desl = rg.er_dia(dia, k)
            if so_portao:
                if er >= limiar and desl != 0:
                    lst.append((k, 1 if desl > 0 else -1))
            else:
                lst += [(k, 1), (k, -1)]
        if lst:
            out[pd.Timestamp(d)] = lst
    return out


def _um_sorteio(args):
    seed, cands, geos, hora_ini, hora_fim = args
    from decisoes import decisao_gestao, VALIDADE_VELAS
    from sessao_l import SessaoL
    from rodar_v3 import run_cls
    rng = np.random.default_rng(seed)
    datas = sorted(cands)
    for d in datas:
        if d not in _DIAS:
            _DIAS[d] = _MK.dia(d, 1)
    tot = 0.0
    for geo in geos:
        for _ in range(40):
            d = datas[rng.integers(len(datas))]
            k, lado = cands[d][rng.integers(len(cands[d]))]
            dia = _DIAS[d]
            px = float(dia.m15[k, 3])

            def decidir(kk, s, k=k, lado=lado, px=px, geo=geo, dia=dia):
                if s.pos:
                    dec, _ = decisao_gestao(None, _CTX, dia, kk, s.pos)
                    return dec, {}
                if kk != k or s.pend:
                    return dict(acao="manter"), {}
                return dict(acao="comprar_limite" if lado > 0 else "vender_limite", preco=px, stop=px - lado * geo["ds"],
                            alvo=(px + lado * geo["da"]) if geo["da"] else None, contratos=geo["n"],
                            validade_velas=VALIDADE_VELAS, trail=geo["trail"]), {}
            ss, _ = run_cls(_MK, dia, decidir, SessaoL)
            if ss.trades:
                tot += ss.trades[0]["brl"]
                break
    return tot


def nulo(sess, cands, sorteios, workers, hora_ini="09:15", hora_fim="17:30", seed0=5000):
    """Distribuicao do total (R$) de `sorteios` repeticoes; geometrias = ordens preenchidas de `sess` (lista de sessoes)."""
    from avaliar import _geometrias
    geos = _geometrias(sess)
    out = np.zeros(sorteios)
    if not geos or not cands:
        return out, len(geos)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        futs = {ex.submit(_um_sorteio, (seed0 + i, cands, geos, hora_ini, hora_fim)): i for i in range(sorteios)}
        for f in as_completed(futs):
            out[futs[f]] = f.result()
    return out, len(geos)
