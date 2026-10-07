# -*- coding: utf-8 -*-
"""Geracao 22 -- avaliacao completa do UNICO proxy que separou dias bons de
ruins de forma real no IS (`g22_is_estratificacao.py`): `amplitude_ontem`
(high-low do pregao ANTERIOR do WIN@), p=0,0040 no teste de permutacao,
separacao MONOTONICA e sem reversao nos 3 tercis.

Compara os 2 filtros candidatos (limiares CONGELAVEIS, numeros absolutos em
pontos, calculados sobre o IS em `g22_is_estratificacao.py`):
  - "so_tercio_alto": opera so' quando amplitude_ontem > 3680,0pts (~1/3 dos
    pregoes)
  - "excluir_tercio_baixo": opera quando amplitude_ontem > 2558,3pts (~2/3
    dos pregoes, so' exclui o tercio de pior desempenho)

Para cada um: liquido, n, win%/BEemp/IC95, top3/top5 de concentracao,
p_ruina (MC), pior sequencia -- MESMAS metricas da G21, para decidir se
algum bate o criterio "concentracao MELHOR que a G21 (41%/64%) E liquido/
win% ainda positivo" (item 4 do mandato) antes de promover a OOS-1.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g22_proxy_dia/g22_candidato_filtro_amplitude.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g22_base as b  # noqa: E402

# Limiares CONGELADOS do IS (g22_is_estratificacao.py) -- NUNCA recalculados
# sobre o OOS-1.
LIMIAR_C1 = 2558.3   # tercio baixo/medio
LIMIAR_C2 = 3680.0   # tercio medio/alto


def _avalia(rotulo: str, trades_todos: list, dias_elegiveis: list) -> dict:
    m = b.metricas_por_grupo(trades_todos, dias_elegiveis, rotulo)
    trades_grupo = [t for t in trades_todos if t.exit_ts.date() in set(dias_elegiveis)]
    top5 = b.concentracao_topn(m["serie"], 5)
    ru = b.ruina_do_resultado(trades_grupo, pregoes_da_janela=len(dias_elegiveis))
    pior_n, pior_brl = b.maior_sequencia_perdas(trades_grupo)
    m.update(top5=top5, p_ruina=ru["p_ruina"], pior_seq_n=pior_n, pior_seq_brl=pior_brl)
    return m


def _imprime(m: dict) -> None:
    win_pct = f"{100*m['win']:.1f}" if m['win'] == m['win'] else "--"
    be_pct = f"{100*m['be']:.1f}" if m['be'] == m['be'] else "--"
    lo_pct = f"{100*m['lo']:.1f}" if m['lo'] == m['lo'] else "--"
    hi_pct = f"{100*m['hi']:.1f}" if m['hi'] == m['hi'] else "--"
    p_ruina_pct = f"{100*m['p_ruina']:.1f}" if m['p_ruina'] == m['p_ruina'] else "--"
    print(f"  {m['rotulo']:<22} dias_elegiveis={m['n_dias']:>3}  "
          f"(com_trade={m['com_trade']}/sem_trade={m['sem_trade']})  "
          f"n_trades={m['n_trades']:>4}  liquido={b.br(m['liquido']):>10}  "
          f"win={win_pct:>5}%  BEemp={be_pct:>5}%  IC95=[{lo_pct};{hi_pct}]  "
          f"veredito={m['veredito']:<10}  top3/liq={100*m['top3']:>4.0f}%  "
          f"top5/liq={100*m['top5']:>4.0f}%  p_ruina={p_ruina_pct:>5}%  "
          f"pior_seq={m['pior_seq_n']:>2}(R${b.br(m['pior_seq_brl'])})")


def main() -> None:
    win_full = b.carrega_win()
    wdo_full = b.carrega_wdo()
    dias_is = b.dias_da_janela(win_full, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Geracao 22 -- candidato final (IS, jan-jun/2026, {len(dias_is)} pregoes)\n", flush=True)

    res, strat = b.roda_g21_vencedor(dias_is)
    trades = list(res.trades)
    c_ref = b.consistencia(trades, dias_is)
    top5_ref = b.concentracao_topn(c_ref["serie"], 5)
    ru_ref = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_is))
    pior_n_ref, pior_brl_ref = b.maior_sequencia_perdas(trades)
    print(f"REFERENCIA (G21 sem filtro): liquido={b.br(c_ref['liquido'])}  n={c_ref['n']}  "
          f"win={100*c_ref['win']:.1f}%  BEemp={100*c_ref['be']:.1f}%  "
          f"veredito={c_ref['veredito']}  top3/liq={100*c_ref['concentracao_top3']:.0f}%  "
          f"top5/liq={100*top5_ref:.0f}%  p_ruina={100*ru_ref['p_ruina']:.1f}%  "
          f"pior_seq={pior_n_ref}(R${b.br(pior_brl_ref)})\n", flush=True)

    proxies = b.calcula_proxies(dias_is, win_full, wdo_full)

    dias_tercio_alto = list(proxies.index[proxies["amplitude_ontem"] > LIMIAR_C2])
    dias_excluir_baixo = list(proxies.index[proxies["amplitude_ontem"] > LIMIAR_C1])

    m_alto = _avalia(f"so_tercio_alto(>{LIMIAR_C2:.0f}pts)", trades, dias_tercio_alto)
    m_excl = _avalia(f"excluir_baixo(>{LIMIAR_C1:.0f}pts)", trades, dias_excluir_baixo)

    print("Candidatos (limiar CONGELADO, numero absoluto em pontos):")
    _imprime(m_alto)
    _imprime(m_excl)

    print("\nComparacao de concentracao contra a referencia G21 (41%/64%):")
    print(f"  so_tercio_alto:    top3 {100*m_alto['top3']:.0f}% "
          f"({'MELHOR' if m_alto['top3'] < c_ref['concentracao_top3'] else 'NAO melhor'}), "
          f"top5 {100*m_alto['top5']:.0f}% "
          f"({'MELHOR' if m_alto['top5'] < top5_ref else 'NAO melhor'})")
    print(f"  excluir_baixo:     top3 {100*m_excl['top3']:.0f}% "
          f"({'MELHOR' if m_excl['top3'] < c_ref['concentracao_top3'] else 'NAO melhor'}), "
          f"top5 {100*m_excl['top5']:.0f}% "
          f"({'MELHOR' if m_excl['top5'] < top5_ref else 'NAO melhor'})")


if __name__ == "__main__":
    main()
