# -*- coding: utf-8 -*-
"""Le out/is_resultados.pkl, aplica o criterio de escolha declarado em sweep_is.py, checa se cada
eixo mexeu em alguma coisa e imprime a tabela padrao ordenada por celula."""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.stdout.reconfigure(encoding="utf-8")
import tabela  # noqa: E402
from sweep_is import grade  # noqa: E402


def main() -> None:
    res = pickle.load(open(AQUI / "out" / "is_resultados.pkl", "rb"))
    g = grade()
    ordem = sorted(res)
    for fill in ("toque", "atrav+1t"):
        print(f"\n=== IS, modo A (conta continua R$250), fill={fill} ===")
        print(tabela.tabela([res[i][fill]["la"] for i in ordem], tabela.EXTRAS, 11))
    for fill in ("toque", "atrav+1t"):
        print(f"\n=== IS, modo B (R$250 por pregao, capital nocional), fill={fill} ===")
        print(tabela.tabela([res[i][fill]["lb"] for i in ordem], tabela.EXTRAS, 11))

    # criterio 1: sobrevivencia da conta continua
    sob = [i for i in ordem if res[i]["toque"]["a"]["recusadas"] == 0 and res[i]["toque"]["a"]["eq_min"] >= 100.0]
    print(f"\nCriterio 1 (conta continua R$250 nao censurada): {len(sob)}/{len(ordem)} celulas sobrevivem")
    for i in ordem:
        a = res[i]["toque"]["a"]
        print(f"  {tabela.nome(g[i]):<26} trades={a['n']:>3} recusadas={a['recusadas']:>3} caixa_min={a['eq_min']:7.2f} sem_trade={a['sem_trade']}/{a['pregoes']}")

    # criterio 3 (modo B, toque)
    el = []
    base_ids = sob if sob else ordem          # criterio 1 e' eliminatorio quando alguem sobrevive
    for i in base_ids:
        b = res[i]["toque"]["b"]
        lb = res[i]["toque"]["lb"]
        if b["n"] >= 30 and b["liquido"] > 0 and b["win"] > b["be"]:
            el.append((lb.lucro_por_dd or -9e9, i))
    el.sort(reverse=True)
    print("\nElegiveis (modo B, n>=30, liquido>0, win%>BE emp), ordenadas por lucro/DD:")
    for ldd, i in el:
        b = res[i]["toque"]["b"]
        print(f"  {tabela.nome(g[i]):<26} lucro/DD={ldd:6.2f} liq={b['liquido']:9.2f} n={b['n']:>3} win={b['win']:.1f} BE={b['be']:.1f} p_nulo={b['p_nulo']:.3f}")
    escolha = g[el[0][1]] if el else None
    print("\nESCOLHA CONGELADA:", None if escolha is None else tabela.nome(escolha), escolha)

    # eixos vivos
    print("\nEixos: celulas que diferem (liquido, n) ao trocar so' o eixo, modo B toque")
    eixos = ["recuo_pts", "stop_pts", "alvo_pts", "vol_modo", "gap_min_pts"]
    def chave(i):
        s = g[i]; b = res[i]["toque"]["b"]
        return (b["liquido"], b["n"])
    for e in eixos:
        difere = tot = 0
        grupos: dict = {}
        for i, s in enumerate(g):
            outros = [a for a in ("variante", "recuo_pts", "stop_pts", "alvo_pts", "vol_modo", "gap_min_pts", "alvo_pequeno_pts") if a != e]
            if e == "vol_modo":
                outros.remove("alvo_pequeno_pts")
            k = tuple((a, str(s.get(a))) for a in outros)
            grupos.setdefault(k, []).append(i)
        for k, ids in grupos.items():
            if len(ids) < 2:
                continue
            tot += 1
            difere += int(len({chave(i) for i in ids}) > 1)
        print(f"  {e:<12} grupos comparaveis={tot:>2} grupos em que o eixo mudou o resultado={difere:>2}")
    json.dump(dict(escolha=escolha, n_sobrevivem=len(sob)), open(AQUI / "out" / "escolha_congelada.json", "w"), indent=1)


if __name__ == "__main__":
    main()
