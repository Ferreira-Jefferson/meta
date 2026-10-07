# -*- coding: utf-8 -*-
"""OOS-2 (set/2026, gate FINAL) da Geracao 31 -- mesmo candidato congelado
`periodo=34`, SEM reajustar nada. Roda UMA VEZ.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g31_base as b  # noqa: E402


def main() -> None:
    win = b.carrega_win()
    dias_oos2 = b.dias_da_janela(win, b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM)
    print(f"OOS-2 (set/2026, {len(dias_oos2)} pregoes), GATE FINAL, G31 congelado v31, "
          f"EMA34 rejeicao, geometria G21 (stop={b.STOP_FRACAO}, alvo={b.ALVO_FRACAO})\n")
    print("-- referencias set/26: SEM FILTRO liquido=-909,50 win=29,2% p_ruina=93,6%; "
          "G29(close) liquido=-629,50 win=31,2% p_ruina=80,8% --\n")

    res, _ = b.roda(dias_oos2, congelado=True, periodo=34)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos2)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos2))
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
    print(f"\nRetorno sobre R${b.br(b.CAPITAL,0)}: {b.br(retorno_pct,1)}% em {len(dias_oos2)} pregoes")


if __name__ == "__main__":
    main()
