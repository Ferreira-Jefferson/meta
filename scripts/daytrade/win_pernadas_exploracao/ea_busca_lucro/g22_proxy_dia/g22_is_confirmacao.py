# -*- coding: utf-8 -*-
"""Geracao 22 -- confirmacao: roda a CLASSE FINAL
(`WinBuscaLucroG22RetanguloFiltroAmplitude`, filtro de dia aplicado DENTRO do
motor via `on_session_start`/`on_bar`) sobre o IS e confere que reproduz
EXATAMENTE os numeros da estratificacao pos-hoc de
`g22_candidato_filtro_amplitude.py` ("excluir_baixo", R$3.402,00/436 trades/
win 40,1%) -- a classe final nao pode divergir do calculo pos-hoc que a
escolheu, senao o mecanismo de filtro (zerar o pregao inteiro em `on_session_
start`) estaria fazendo algo diferente do que foi medido.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g22_proxy_dia/g22_is_confirmacao.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g22_base as b  # noqa: E402


def main() -> None:
    win_full = b.carrega_win()
    dias_is = b.dias_da_janela(win_full, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)

    res, strat, dias_habilitados = b.roda_g22_filtrado(dias_is, win_full=win_full)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_is)
    top5 = b.concentracao_topn(c["serie"], 5)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_is))
    pior_n, pior_brl = b.maior_sequencia_perdas(trades)

    print(f"Dias habilitados: {len(dias_habilitados)}/{len(dias_is)}")
    print(f"liquido={b.br(c['liquido'])}  n={c['n']}  win={100*c['win']:.1f}%  "
          f"BEemp={100*c['be']:.1f}%  IC95=[{100*c['lo']:.1f};{100*c['hi']:.1f}]  "
          f"veredito={c['veredito']}  top3/liq={100*c['concentracao_top3']:.0f}%  "
          f"top5/liq={100*top5:.0f}%  p_ruina={100*ru['p_ruina']:.1f}%  "
          f"pior_seq={pior_n}(R${b.br(pior_brl)})  sem_trade={c['sem_trade']}/{c['pregoes']}")

    esperado = dict(liquido=3402.00, n=436, dias_habilitados=81)
    bate = (abs(c["liquido"] - esperado["liquido"]) < 0.01 and c["n"] == esperado["n"]
            and len(dias_habilitados) == esperado["dias_habilitados"])
    print(f"\nConfere com a estratificacao pos-hoc "
          f"(liquido={b.br(esperado['liquido'])}, n={esperado['n']}, "
          f"dias={esperado['dias_habilitados']})? {'SIM' if bate else 'NAO -- INVESTIGAR'}")


if __name__ == "__main__":
    main()
