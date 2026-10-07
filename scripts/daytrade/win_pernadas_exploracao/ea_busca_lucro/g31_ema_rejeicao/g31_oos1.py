# -*- coding: utf-8 -*-
"""OOS-1 (jul-ago/2026, 44 pregoes) da Geracao 31 -- candidato CONGELADO
`periodo=34` (pedido literal do dono; 21/55 confirmaram o mesmo sentido no
IS -- ganho forte em win%/concentracao/ruina, perda em liquido total por
causa do n menor).

Codigo CONGELADO em
`win_busca_lucro_g31_retangulo_ema_rejeicao_congelado_v31.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g31_base as b  # noqa: E402


def main() -> None:
    win = b.carrega_win()
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    print(f"OOS-1 (jul-ago/2026, {len(dias_oos1)} pregoes), G31 congelado v31, "
          f"EMA34 rejeicao, geometria G21 (stop={b.STOP_FRACAO}, alvo={b.ALVO_FRACAO})\n")
    print("-- referencias: SEM FILTRO liquido=+650,00 n=98 win=39,8% top3=97,2%; "
          "G29(close) liquido=+736,50 n=77 win=41,6% top3=88,3% --\n")

    res, _ = b.roda(dias_oos1, congelado=True, periodo=34)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos1))
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
    print(f"\nRetorno sobre R${b.br(b.CAPITAL,0)}: {b.br(retorno_pct,1)}% em {len(dias_oos1)} pregoes "
          f"({b.br(retorno_pct/2,1)}%/mes medio, 2 meses)")


if __name__ == "__main__":
    main()
