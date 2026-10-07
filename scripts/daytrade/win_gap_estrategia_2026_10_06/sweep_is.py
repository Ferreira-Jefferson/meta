# -*- coding: utf-8 -*-
"""Varredura IS (2026-04-06 .. 2026-10-05; os indicios nasceram aqui -> IS NAO e' evidencia).

28 celulas. Por celula: modo A (conta continua R$250), modo B (R$250 por pregao, com nulo exato de
direcao aleatoria) e a sensibilidade de preenchimento (toque x atravessa >=1 tick).

CRITERIO DE ESCOLHA (declarado ANTES de ver qualquer numero; feedback do dono de 2026-09-09):
  1. eliminatorio: celula cuja conta continua de R$250 nao foi censurada (nenhuma ordem recusada
     por capital e caixa minimo >= margem crua R$100);
  2. se NENHUMA sobrevive a (1): a pergunta de borda ("o indicio sobrevive fora da amostra?") nao
     pode ser respondida pela conta continua; segue-se so' com o modo B, dizendo isso na primeira
     linha;
  3. entre as elegiveis: n >= 30 operacoes, liquido > 0, win% > BE empirico; ordena por lucro/DD
     (modo B, fill=toque). A primeira e' congelada.
"""
from __future__ import annotations

import csv
import io
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

IS = ("2026", "2026-04-06", "2026-10-05")


def grade() -> list[dict]:
    g = []
    for rec in (0, 150):
        for st in (350, 700):
            for al in (None, 700):
                g.append(dict(variante="V1", recuo_pts=rec, stop_pts=st, alvo_pts=al))
    for rec in (0, 150):
        for st in (350, 700):
            for al in (None, 700):
                g.append(dict(variante="V2", recuo_pts=rec, stop_pts=st, alvo_pts=al))
    for rec in (0, 150):
        for st in (350, 700):
            for vm in ("skip", "alvo_menor"):
                g.append(dict(variante="V3", recuo_pts=rec, stop_pts=st, alvo_pts=700, vol_modo=vm,
                              alvo_pequeno_pts=350 if vm == "alvo_menor" else None))
    for rec in (0, 150):
        for st in (350, 700):
            g.append(dict(variante="V2", recuo_pts=rec, stop_pts=st, alvo_pts=700, gap_min_pts=400))
    return g


def unidade(i: int, spec: dict) -> dict:
    import runner
    import tabela
    sys.stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)
    base, ini, fim = IS
    saida = dict(i=i, spec=spec)
    for fill in ("toque", "atrav+1t"):
        a = runner.roda(spec, base, ini, fim, fill)
        rp = runner.roda_pregao(spec, base, ini, fim, fill)
        r = runner.resume_pregao(rp, spec)
        la = tabela.linha_a(a, spec)
        lb = tabela.linha_b(r, spec, fill)
        r = {k: v for k, v in r.items() if k not in ("trades", "dir_real", "pos", "neg")}
        r["pnl_dia"] = {str(k): v for k, v in r["pnl_dia"].items()}
        a = {k: v for k, v in a.items() if k not in ("_linha", "trades")}
        saida[fill] = dict(a=a, b=r, la=la, lb=lb)
    return saida


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from tabela import EXTRAS, tabela
    g = grade()
    print(f"IS {IS[1]}..{IS[2]} | {len(g)} celulas | capital R$250 | fila NAO calibrada", flush=True)
    res: dict = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=6) as pool:
        fut = {pool.submit(unidade, i, s): i for i, s in enumerate(g)}
        for f in as_completed(fut):
            u = f.result()
            res[u["i"]] = u
            print(f"[{len(res)}/{len(g)} {time.time() - t0:.0f}s]", flush=True)
            print(tabela([u["toque"]["la"], u["toque"]["lb"], u["atrav+1t"]["lb"]], EXTRAS, 11), flush=True)
    import pickle
    pickle.dump(res, open(AQUI / "out" / "is_resultados.pkl", "wb"))


if __name__ == "__main__":
    main()
