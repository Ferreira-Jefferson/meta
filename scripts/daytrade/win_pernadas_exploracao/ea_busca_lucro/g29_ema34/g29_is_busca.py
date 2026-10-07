# -*- coding: utf-8 -*-
"""IS (jan-jun/2026, 122 pregoes) da Geracao 29 -- filtro de posicao do
preco contra EMA classica (34 = pedido do dono; 21/55 = vizinhos, para
sensibilidade ao periodo). Referencia SEM filtro (G21): liquido R$2.790,00,
n=562, win 37,9%, BEemp 33,8%, top3/liq=41%, top5/liq=64%.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g29_base as b  # noqa: E402


def avalia(dias_is, **kwargs) -> dict:
    res, _ = b.roda(dias_is, **kwargs)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_is)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_is))
    return dict(c=c, top5=top5, pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, ru=ru)


def imprime(nome: str, r: dict) -> None:
    c = r["c"]
    print(f"{nome:14s} liquido={b.br(c['liquido']):>10s}  n={c['n']:4d}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>5s}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>5s}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  "
          f"veredito={c['veredito']:10s}  "
          f"top3/liq={b.br(100*c['concentracao_top3'],1) if c['concentracao_top3']==c['concentracao_top3'] else '--':>6s}%  "
          f"top5/liq={b.br(100*r['top5'],1) if r['top5']==r['top5'] else '--':>6s}%  "
          f"p_ruina={b.br(100*r['ru']['p_ruina'],1) if r['ru']['p_ruina']==r['ru']['p_ruina'] else '--'}%",
          flush=True)


def main() -> None:
    win = b.carrega_win()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"IS (jan-jun/2026, {len(dias_is)} pregoes) -- geometria herdada da G21 "
          f"(stop={b.STOP_FRACAO}, alvo={b.ALVO_FRACAO})\n", flush=True)
    print(f"{'SEM FILTRO':14s} liquido={b.br(2790.00):>10s}  n= 562  "
          f"win={b.br(37.9,1):>5s}%  BEemp={b.br(33.8,1):>5s}%  veredito=POSITIVO    "
          f"top3/liq={b.br(40.9,1):>6s}%  top5/liq={b.br(64.5,1):>6s}%\n", flush=True)

    for periodo in (21, 34, 55):
        r = avalia(dias_is, periodo=periodo)
        imprime(f"EMA{periodo}", r)


if __name__ == "__main__":
    main()
