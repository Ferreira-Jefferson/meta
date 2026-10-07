# -*- coding: utf-8 -*-
"""OOS-1 (jul-ago/2026, 44 pregoes) da Geracao 26 -- DOIS candidatos
congelados ANTES de abrir esta janela (ver `g26_is_busca_stdout.log`):

  1. `drift_bars`, janela=240 barras M1 (4h, o MEIO do plato {120,240,480}
     frouxo -- nao o extremo, mesmo criterio que a G21 usou para escolher
     entre suas 2 celulas POSITIVO), `estrito=False`.
  2. `drift_dia` (desde a abertura da sessao, sem janela para escolher --
     medida unica, menor risco de multiplo teste), `estrito=False`.

NAO promovido: nenhuma celula `estrito=True` -- so' W=120 estrito pareceu
boa, mas W=240/480 estrito colapsam (n=96/19, top3/liq negativo ou >100%),
ou seja, nao ha' plato em "estrito": e' o mesmo padrao de "otimo na borda"
que ja' invalidou candidatos anteriores nesta busca (G3/G4). Descartado por
disciplina, nao testado no OOS-1.

Roda UMA VEZ cada, SEM reajustar parametro nenhum -- protocolo do mandato.
Codigo CONGELADO em `win_busca_lucro_g26_retangulo_tendencia_congelado_v26.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g26_base as b  # noqa: E402


def roda_congelado(dias_operar, **kwargs_estrategia):
    sys.path.insert(0, str(b.ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from strategy.daytrade.lab.win_busca_lucro_g26_retangulo_tendencia_congelado_v26 import (
        WinBuscaLucroG26RetanguloTendenciaCongeladoV26 as Estrategia,
    )
    win = b.carrega_win()
    bars = b.bars_dos_dias(win, dias_operar)
    strat = Estrategia(stop_fracao_largura=b.STOP_FRACAO, alvo_fracao_largura=b.ALVO_FRACAO,
                        **kwargs_estrategia)
    cfg = b.monta_config(b.CAPITAL)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, strat


def avalia(nome: str, dias_oos1, **kwargs) -> None:
    res, _ = roda_congelado(dias_oos1, **kwargs)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_oos1)
    cs = b.censura_separada(res, c)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_oos1))
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)

    print(f"\n=== {nome} ===")
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
    print(f"Retorno sobre R${b.br(b.CAPITAL,0)}: {b.br(retorno_pct,1)}% em {len(dias_oos1)} pregoes "
          f"({b.br(retorno_pct/2,1)}%/mes medio, 2 meses)")


def main() -> None:
    win = b.carrega_win()
    dias_oos1 = b.dias_da_janela(win, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    print(f"OOS-1 (jul-ago/2026, {len(dias_oos1)} pregoes), G26 congelado v26, "
          f"geometria G21 (stop={b.STOP_FRACAO}, alvo={b.ALVO_FRACAO})")

    print("\n-- referencia SEM filtro (G21, ja' medido em g21_oos1_stdout.log): "
          "liquido=+650,00  n=98  win=39,8%  BEemp=34,0%  top3/liq=97,2%  top5/liq=133,4% --")

    avalia("Candidato 1: drift_bars W=240 (meio do plato), frouxo",
           dias_oos1, medida="drift_bars", janela_tendencia=240, estrito=False)
    avalia("Candidato 2: drift_dia, frouxo",
           dias_oos1, medida="drift_dia", janela_tendencia=240, estrito=False)


if __name__ == "__main__":
    main()
