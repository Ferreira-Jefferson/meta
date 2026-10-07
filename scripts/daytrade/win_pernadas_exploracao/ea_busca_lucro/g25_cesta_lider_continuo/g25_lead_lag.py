# -*- coding: utf-8 -*-
"""PASSO 1 do mandato (G25): correlacao cruzada cesta->WIN e WIN->cesta, em
varias defasagens, DENTRO do IS -- MESMO metodo exato da G24 (que testou o
WDO), agora com o indice sintetico causal da cesta (`g25_base.
retorno_cesta_1min`, media de retorno percentual das 24 acoes, equal-weight)
no lugar do WDO.

Pergunta: existe LEAD genuino da cesta sobre o WIN (defasagem >=1 min), ou
a cesta so' se move CONTEMPORANEAMENTE ao WIN (o que seria esperado se o WIN
for tao rapido ou mais rapido que a media das acoes -- hipotese de mercado
eficiente intradiario levantada no mandato)?

Metodo: para cada dia do IS (reset por sessao), retorno de 1 MINUTO de cada
lado. Para `lag` em {0, 1, 2, 3, 5}:
  - cesta lidera: corr(ret_cesta[t], ret_win[t+lag])
  - WIN lidera:   corr(ret_win[t], ret_cesta[t+lag])
IC95% via Fisher z (apropriado p/ n grande).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g25_cesta_lider_continuo/g25_lead_lag.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g25_base as b  # noqa: E402

LAGS = [0, 1, 2, 3, 5]


def main() -> None:
    win = b.carrega_win()
    cesta = b.carrega_cesta()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Lead-lag G25 (cesta) -- IS (jan-jun/2026, {len(dias_is)} pregoes).")
    print("Retorno de 1 minuto, dentro do pregao (reset por sessao). "
          "Cesta = media simples do retorno percentual de 24 acoes liquidas "
          "(equal-weight), reindexada na grade do WIN. IC95% via Fisher z.\n",
          flush=True)

    win_bars = b.bars_dos_dias(win, dias_is)
    grade = win_bars.index
    ret_win = b.retornos_1min(win, dias_is)
    ret_cesta = b.retorno_cesta_1min(cesta, grade)
    # Alinha os dois lados no MESMO indice antes de qualquer deslocamento.
    idx_comum = ret_win.index.intersection(ret_cesta.index).sort_values()
    ret_win = ret_win.reindex(idx_comum)
    ret_cesta = ret_cesta.reindex(idx_comum)

    print(f"{'lag(min)':>8} | {'cesta lidera WIN':<34} | {'WIN lidera cesta':<34}")
    print(f"{'':>8} | {'r':>8} {'IC95%':>18} {'n':>7} | {'r':>8} {'IC95%':>18} {'n':>7}")
    print("-" * 94)
    for lag in LAGS:
        if lag == 0:
            cesta_lidera = b.corr_com_ic(ret_cesta, ret_win)
            win_lidera = cesta_lidera  # contemporaneo -- mesma coisa nos dois sentidos
        else:
            win_deslocado = b.desloca_dentro_do_dia(ret_win, lag)
            cesta_deslocada = b.desloca_dentro_do_dia(ret_cesta, lag)
            cesta_lidera = b.corr_com_ic(ret_cesta, win_deslocado)   # ret_cesta[t] x ret_win[t+lag]
            win_lidera = b.corr_com_ic(ret_win, cesta_deslocada)     # ret_win[t] x ret_cesta[t+lag]
        ic_a = f"[{cesta_lidera['lo']:+.4f};{cesta_lidera['hi']:+.4f}]"
        ic_b = f"[{win_lidera['lo']:+.4f};{win_lidera['hi']:+.4f}]"
        print(f"{lag:>8} | {cesta_lidera['r']:>+8.4f} {ic_a:>18} {cesta_lidera['n']:>7} | "
              f"{win_lidera['r']:>+8.4f} {ic_b:>18} {win_lidera['n']:>7}", flush=True)

    print("\nLeitura: diferente de WDO/WIN (G24, ambos ja' negociados em "
          "pontos do MESMO tipo de instrumento), cesta e WIN nao tem razao "
          "estrutural para correlacao negativa forte em lag=0 -- a cesta e' "
          "componente do MESMO indice que o WIN replica, entao lag=0 alto e "
          "POSITIVO e' o esperado por construcao (nao e' sinal, e' definicao). "
          "A pergunta que decide e' se |r| em lag>=1 e' GRANDE o bastante "
          "para virar sinal executavel -- nao so' estatisticamente diferente "
          "de zero (n grande torna isso quase garantido).")


if __name__ == "__main__":
    main()
