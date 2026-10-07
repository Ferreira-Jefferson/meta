# -*- coding: utf-8 -*-
"""G21 (sem filtro nenhum) rodada em set/2026, so' para responder a
pergunta "antes (sem o filtro de EMA), quanto dava em setembro?" -- mesmo
codigo congelado (`_congelado_v21.py`), ja' usado para IS e OOS-1, nenhuma
retunagem nova. Nao e' um gate novo de validacao, e' a mesma referencia que
a G29 comparou em OOS-1, estendida a OOS-2 para comparacao direta.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g21_base as b  # noqa: E402


def main() -> None:
    win = b.carrega_win()
    dias_set = b.dias_da_janela(win, b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM)
    print(f"G21 SEM FILTRO em set/2026 ({len(dias_set)} pregoes), codigo congelado v21 "
          f"(stop={b.STOP_FRACAO if hasattr(b,'STOP_FRACAO') else 0.45}, mesmo da OOS-1)\n")

    res, _ = b.roda(dias_set, congelado=True, stop_fracao_largura=0.45, alvo_fracao_largura=0.90)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_set)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_set))
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)

    print(f"liquido={b.br(c['liquido'])}  n={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  equity_min={b.br(cs['equity_min'])}")
    print(f"top3/liq={b.br(100*c['concentracao_top3'],1) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liq={b.br(100*top5,1) if top5==top5 else '--'}%")
    print(f"pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)})  "
          f"p_ruina(MC, caixa=R${b.br(b.CAPITAL,0)})={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%")
    retorno_pct = 100.0 * c["liquido"] / b.CAPITAL
    print(f"\nRetorno sobre R${b.br(b.CAPITAL,0)}: {b.br(retorno_pct,1)}% em {len(dias_set)} pregoes")


if __name__ == "__main__":
    main()
