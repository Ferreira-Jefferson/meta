# -*- coding: utf-8 -*-
"""Sensibilidade (limite superior do efeito do leilao na faixa): alem de tudo que o
modo 'depois' faz, REMOVE a barra marcada como leilao (flag_leilao) das barras. A faixa
passa a comecar na barra seguinte. E' pessimista nos dias com tick (o leilao so' e'
extremo em ~9% dos dias) mas e' o unico recorte possivel nos dias 'proxy' (sem tick).
Roda os vencedores congelados de G07 (IS e OOS-1) e de G13/G08 (IS e OOS-1)."""
import os, sys
from pathlib import Path
os.environ["ORB_MODO"] = "depois"
sys.path.insert(0, str(Path(__file__).parent))
import patch_semleilao as P
P.aplica()
import g05_base as g05b
import pandas as pd
from market_data_intraday.win_sem_leiloes import carrega_win_m1_sem_leiloes

def _carrega():
    if "win_pula" not in g05b._CACHE:
        r = carrega_win_m1_sem_leiloes(g05b.CSV_WIN)
        b = r.barras
        g05b._CACHE["win_pula"] = b.loc[~b["flag_leilao"], P._COLS].copy()
    return g05b._CACHE["win_pula"]
g05b.carrega_win = _carrega

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "g07_orb")); sys.path.insert(0, str(R / "g13_orb_grade_fina"))
import g07_base as b7
import g13_base as b13
from backtest.intraday.report import linha_de_resultado, tabela


def main():
    win = b7.carrega_win()
    is_ = b7.dias_da_janela(win, b7.CORTE_IS_INICIO, b7.CORTE_IS_FIM)
    oos = b7.dias_da_janela(win, b7.CORTE_IS_FIM, b7.CORTE_OOS1_FIM)
    cases = [
        ("G07 5min/250/5x", b7.roda, dict(range_minutos=5.0, stop_min_pontos=100.0, stop_max_pontos=250.0, alvo_multiplo=5.0, buffer_entrada_pontos=20.0)),
        ("G13 5min/tec140/3x", b13.roda, dict(range_minutos=5.0, stop_family="tecnico", stop_min_pontos=50.0, stop_max_pontos=140.0, alvo_multiplo=3.0, confirma_pontos=0.0, buffer_entrada_pontos=20.0)),
    ]
    linhas = []
    for nome, fn, kw in cases:
        for jn, dias in (("IS", is_), ("OOS-1", oos)):
            res, st = fn(dias, **kw)
            tr = list(res.trades); c = b7.consistencia(tr, dias)
            print(f"{nome} {jn}: liquido={b7.br(c['liquido'])} trades={c['n']} win={b7.br(100*c['win'],1) if c['n'] else '--'}% "
                  f"sem_trade={c['sem_trade']}/{c['pregoes']} veredito={c['veredito']}", flush=True)
            linhas.append(linha_de_resultado(f"{nome} {jn} (pula leilao)", res, b7.CAPITAL))
    print(tabela(linhas))

if __name__ == "__main__":
    main()
