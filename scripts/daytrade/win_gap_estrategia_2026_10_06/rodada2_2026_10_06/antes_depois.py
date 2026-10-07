# -*- coding: utf-8 -*-
"""(a) ANTES (semantica do motor, barra a barra) x DEPOIS (tick) nas celulas de saida sem estado (stop/alvo fixos):
trades com stop/alvo dentro da barra do fill, pior trade contra o stop nominal, liquido (R$1.000/pregao, q=2).
(b) sensibilidade de preenchimento mais dura nas 10 melhores celulas (por t): atravessa 3 e 5 ticks."""
from __future__ import annotations

import pickle
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import ctx as C  # noqa: E402
import regras as R  # noqa: E402
import sim as S  # noqa: E402
import sizing as Z  # noqa: E402
import ticks_prep as TP  # noqa: E402

_G = {}


def sem_estado(ex):
    return ex["trail"] is None and ex["be"] is None and ex["partial"] is None and ex["tstop"] is None


def unidade(dia, ids_top):
    if "bj" not in _G:
        bj, dj, ctx = C.constroi()
        _G.update(bj=bj, ctx=ctx, grade=R.grade())
    c = _G["ctx"][dia]
    b = C.barras_do_dia(_G["bj"], dia)
    t, p = TP.carrega(dia)
    d = S.DiaTicks(t=t, p=p, bst=b["st"], bo=b["o"], bh=b["h"], bl=b["l"], bc=b["c"])
    tsig = int(b["st"][0] + S.M5)
    q = Z.n_contratos(Z.CAPITAL)
    saida = []
    for g in _G["grade"]:
        s = R.gatilho(c, g["ent"])
        if s == 0:
            continue
        lim = R.limite(c, s, g["ent"]["recuo"])
        sa = R.saida_de(c, s, lim, g["ex"], s, lim)
        if sa is None:
            continue
        if sem_estado(g["ex"]):
            tb = S.simula_barra(d, s, lim, sa.stop, sa.target, q, "toque", tsig)
            tk = S.simula_tick(d, s, lim, sa, q, "toque", tsig)
            nom = abs(lim - sa.stop)
            saida.append(("ad", g["id"], dia, None if tb is None else (tb.pnl, tb.pior_pts, tb.legs[-1].reason),
                          None if tk is None else (tk.pnl, tk.pior_pts, tk.legs[-1].reason, tk.sai_na_barra_do_fill), nom))
        if g["id"] in ids_top:
            for nt in (3, 5):
                tr = _tick_n(d, s, lim, sa, q, nt, tsig)
                saida.append(("fill%d" % nt, g["id"], dia, None if tr is None else tr.pnl, None, None))
    return saida


def _tick_n(d, s, lim, sa, q, nt, tsig):
    """atravessa `nt` ticks: reusa simula_tick com o limite deslocado so' no teste de fill (fill ao preco do limite)."""
    f = None
    i0 = int(np.searchsorted(d.t, tsig, side="left"))
    i1 = int(np.searchsorted(d.t, tsig + S.TTL_BARRAS * S.M5, side="left"))
    seg = d.p[i0:i1]
    nivel = lim - nt * S.TICK * s
    m = seg <= nivel if s > 0 else seg >= nivel
    if not m.any():
        return None
    # simula a partir do fill achado: troca a janela de busca de fill chamando a funcao interna via monkey simples
    orig = S.procura_fill
    k = i0 + int(m.argmax())
    S.procura_fill = lambda *a, **kw: k
    try:
        return S.simula_tick(d, s, lim, sa, q, "toque", tsig)
    finally:
        S.procura_fill = orig


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    an = pickle.load(open(AQUI / "out" / "analise.pkl", "rb"))
    ids = an["ids"]
    t = an["out"]["toque"]["tobs"]
    top = [ids[j] for j in np.argsort(-t)[:10]]
    dias = an["dias"]
    brutos = []
    with ProcessPoolExecutor(max_workers=5) as ex:
        fut = {ex.submit(unidade, d, set(top)): d for d in dias}
        for f in as_completed(fut):
            brutos += f.result()
    pickle.dump(brutos, open(AQUI / "out" / "antes_depois.pkl", "wb"))
    ad = [b for b in brutos if b[0] == "ad"]
    cels = sorted({b[1] for b in ad})
    print(f"=== (a) ANTES (motor/barra) x DEPOIS (tick): {len(cels)} celulas sem estado, R$1.000/pregao, q={Z.n_contratos(Z.CAPITAL)} ===")
    n_tr = n_fill_bar_stop = n_fill_bar_alvo = n_tr_tk = 0
    pior_b, pior_t = [], []
    liq_b = liq_t = 0.0
    for c in cels:
        L = [b for b in ad if b[1] == c]
        tk = [b[4] for b in L if b[4] is not None]
        tb = [b[3] for b in L if b[3] is not None]
        n_tr_tk += len(tk)
        n_fill_bar_stop += sum(1 for x in tk if x[3] and x[2] == "stop")
        n_fill_bar_alvo += sum(1 for x in tk if x[3] and x[2] == "alvo")
        liq_b += sum(x[0] for x in tb); liq_t += sum(x[0] for x in tk)
        nom = float(np.median([b[5] for b in L]))
        pior_b.append((c, min(x[1] for x in tb) if tb else 0, min(x[1] for x in tk) if tk else 0, nom))
    print(f"trades (soma sobre celulas) {n_tr_tk}: saida por STOP dentro da barra do fill = {n_fill_bar_stop} ({100*n_fill_bar_stop/n_tr_tk:.1f}%); por ALVO dentro da barra do fill = {n_fill_bar_alvo} ({100*n_fill_bar_alvo/n_tr_tk:.1f}%)")
    print("antes (motor): essas saidas eram ignoradas na barra do fill e so' saiam na abertura da barra seguinte; depois (tick): 0 ignoradas, por construcao")
    print(f"liquido somado das celulas: barra/motor {liq_b:,.0f} | tick {liq_t:,.0f}")
    print("\npior trade (pontos por contrato; stop nominal = mediana das distancias da celula):")
    print(f"{'celula':<34}{'nominal':>9}{'pior barra':>12}{'pior tick':>11}{'pior barra / nom':>18}{'pior tick / nom':>17}")
    for c, pb, pt, nom in sorted(pior_b, key=lambda x: x[0]):
        print(f"{c:<34}{nom:9.0f}{pb:12.0f}{pt:11.0f}{abs(pb)/nom:18.2f}{abs(pt)/nom:17.2f}")
    print("\n=== (b) preenchimento mais duro, 10 melhores celulas (modo B, q=2, real): liquido toque -> atravessa 1t -> 3t -> 5t ===")
    f1 = {i: an["out"]["atrav+1t"]["obs"][ids.index(i)] for i in top}
    f0 = {i: an["out"]["toque"]["obs"][ids.index(i)] for i in top}
    for i in top:
        r3 = [b for b in brutos if b[0] == "fill3" and b[1] == i]; r5 = [b for b in brutos if b[0] == "fill5" and b[1] == i]
        s3 = sum(b[3] for b in r3 if b[3] is not None); n3 = sum(1 for b in r3 if b[3] is not None)
        s5 = sum(b[3] for b in r5 if b[3] is not None); n5 = sum(1 for b in r5 if b[3] is not None)
        print(f"{i:<34} toque {f0[i]:10,.0f} | 1t {f1[i]:10,.0f} | 3t {s3:10,.0f} (fills {n3}/{len(r3)}) | 5t {s5:10,.0f} (fills {n5}/{len(r5)})")


if __name__ == "__main__":
    main()
