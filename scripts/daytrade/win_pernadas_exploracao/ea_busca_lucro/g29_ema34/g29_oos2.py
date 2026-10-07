# -*- coding: utf-8 -*-
"""OOS-2 (set/2026, gate FINAL) da Geracao 29 -- candidato CONGELADO
`periodo=34`, mesmo codigo do OOS-1 (`..._congelado_v29.py`), SEM
reajustar nada. Roda UMA VEZ. Depois deste gate nao ha' mais janela de
2026 intocada para esta candidata -- out/2026 em diante teria poucos dias
ainda, e 2025/anterior continua RESERVADO.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g29_base as b  # noqa: E402


def main() -> None:
    win = b.carrega_win()
    dias_oos2 = b.dias_da_janela(win, b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM)
    print(f"OOS-2 (set/2026, {len(dias_oos2)} pregoes), GATE FINAL, G29 congelado v29, "
          f"EMA34, geometria G21 (stop={b.STOP_FRACAO}, alvo={b.ALVO_FRACAO})\n")
    print("-- referencia SEM filtro (G21, set/2026 ja' tinha sido usada so' como referencia "
          "descritiva nas rodadas 1-7, nunca para P&L desta estrategia) --\n")

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
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  equity_min={b.br(cs['equity_min'])}  "
          f"recusadas_capital={cs['ordens_recusadas_por_capital']}  censura_capital={cs['censura_capital']}")
    print(f"top3/liq={b.br(100*c['concentracao_top3'],1) if c['concentracao_top3']==c['concentracao_top3'] else '--'}%  "
          f"top5/liq={b.br(100*top5,1) if top5==top5 else '--'}%")
    print(f"pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)})  "
          f"p_ruina(MC, caixa=R${b.br(b.CAPITAL,0)})={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%")
    retorno_pct = 100.0 * c["liquido"] / b.CAPITAL
    print(f"\nRetorno sobre R${b.br(b.CAPITAL,0)}: {b.br(retorno_pct,1)}% em {len(dias_oos2)} pregoes "
          f"({b.br(retorno_pct,1)}%/mes, 1 mes)")

    print("\n-- combinado IS+OOS-1+OOS-2 (jan-set/2026, 2026 inteiro usado) --")
    win_total = b.carrega_win()
    dias_todos = b.dias_da_janela(win_total, b.CORTE_IS_INICIO, b.CORTE_OOS2_FIM)
    res_t, _ = b.roda(dias_todos, congelado=True, periodo=34)
    c_t = b.consistencia(list(res_t.trades), dias_todos)
    top5_t = b.concentracao_topn(c_t["serie"], 5)
    print(f"liquido={b.br(c_t['liquido'])}  n={c_t['n']}  win={b.br(100*c_t['win'],1)}%  "
          f"BEemp={b.br(100*c_t['be'],1)}%  IC95=[{b.br(100*c_t['lo'],1)};{b.br(100*c_t['hi'],1)}]  "
          f"veredito={c_t['veredito']}  top3/liq={b.br(100*c_t['concentracao_top3'],1)}%  "
          f"top5/liq={b.br(100*top5_t,1)}%")


if __name__ == "__main__":
    main()
