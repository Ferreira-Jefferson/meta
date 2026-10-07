# -*- coding: utf-8 -*-
"""OOS-1 (jul-ago/2026, 44 pregoes) da Geracao 21 -- vencedor do IS CONGELADO.

Vencedor do IS (ver `g21_is_busca_stdout.log`): `stop_fracao_largura=0,45`,
`alvo_multiplo=2,0` (`alvo_fracao_largura=0,90`) -- POSITIVO no IS (win 37,9%
contra BEemp 33,8%), menor p_ruina entre as celulas POSITIVO (5,1%),
concentracao top3/top5 = 41%/64% (a melhor de toda a grade de 15 celulas).

Roda UMA VEZ, SEM reajustar parametro nenhum -- protocolo do mandato.
Codigo CONGELADO em `win_busca_lucro_g21_retangulo_1000_congelado_v21.py`.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g21_retangulo_1000/g21_oos1.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g21_base as b  # noqa: E402

STOP_FRACAO = 0.45
ALVO_MULTIPLO = 2.0
ALVO_FRACAO = STOP_FRACAO * ALVO_MULTIPLO


def main() -> None:
    dias_oos1 = b.dias_da_janela(b.carrega_win(), b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    print(f"OOS-1 (jul-ago/2026, {len(dias_oos1)} pregoes), congelado v21, "
          f"stop_fracao={STOP_FRACAO}, alvo_multiplo={ALVO_MULTIPLO} "
          f"(alvo_fracao={ALVO_FRACAO}), capital R$1.000\n", flush=True)

    res, strat = b.roda(dias_oos1, congelado=True,
                         stop_fracao_largura=STOP_FRACAO, alvo_fracao_largura=ALVO_FRACAO)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos1))
    top3 = c["concentracao_top3"]
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    stop_pts = sorted(c["stop_dist_pts"])
    stop_mediano = stop_pts[len(stop_pts) // 2] if stop_pts else float("nan")

    print(f"liquido={b.br(c['liquido'])}  n={c['n']}  win={b.br(100*c['win'],1) if c['n'] else '--'}%  "
          f"BEnom=N/A  BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--'}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  veredito={c['veredito']}")
    print(f"sem_trade={c['sem_trade']}/{c['pregoes']}  equity_min={b.br(cs['equity_min'])}  "
          f"recusadas_capital={cs['ordens_recusadas_por_capital']}  "
          f"censura_capital={cs['censura_capital']}")
    print(f"top3/liq={b.br(100*top3,1) if top3==top3 else '--'}%  "
          f"top5/liq={b.br(100*top5,1) if top5==top5 else '--'}%")
    print(f"pior_seq={pior_seq_n} (R${b.br(pior_seq_brl)})  stop_mediano={stop_mediano:.0f}pts")
    print(f"p_ruina(MC, caixa=R${b.br(b.CAPITAL,0)}, piso=R${b.br(b.MARGEM_WIN_BRL,0)}, "
          f"n_ops={ru['n_ops']})={b.br(100*ru['p_ruina'],1) if ru['p_ruina']==ru['p_ruina'] else '--'}%  "
          f"ruina_formula={b.br(100*ru['ruina_formula'],1) if ru['ruina_formula']==ru['ruina_formula'] else '--'}%")

    retorno_pct = 100.0 * c["liquido"] / b.CAPITAL
    print(f"\nRetorno OOS-1 sobre R${b.br(b.CAPITAL,0)}: {b.br(retorno_pct,1)}% em {len(dias_oos1)} pregoes "
          f"({b.br(retorno_pct/2,1)}%/mes medio, 2 meses)")


if __name__ == "__main__":
    main()
