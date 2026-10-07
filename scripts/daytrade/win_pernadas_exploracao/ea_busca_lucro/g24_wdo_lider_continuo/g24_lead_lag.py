# -*- coding: utf-8 -*-
"""PASSO 1 do mandato (G24): correlacao cruzada WDO->WIN e WIN->WDO, em
varias defasagens, DENTRO do IS -- confirma ou refuta R26 ("o dolar nao
antecipa o WIN") de novo, com metodo explicito de defasagem (REGRAS.md so'
tinha medido concordancia de sinal contemporanea, nunca lag-a-lag).

Metodo: para cada dia do IS (reset por sessao -- `groupby(dia).diff(1)`,
nunca atravessa a virada de sessao), retorno de 1 MINUTO de cada instrumento.
Para `lag` em {0, 1, 2, 3, 5}:
  - WDO lidera: corr(ret_wdo[t], ret_win[t+lag])
  - WIN lidera: corr(ret_win[t], ret_wdo[t+lag])
IC95% via Fisher z (apropriado p/ n grande -- milhares de minutos).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g24_wdo_lider_continuo/g24_lead_lag.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g24_base as b  # noqa: E402

LAGS = [0, 1, 2, 3, 5]


def main() -> None:
    win = b.carrega_win()
    wdo = b.carrega_wdo()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Lead-lag G24 -- IS (jan-jun/2026, {len(dias_is)} pregoes).")
    print("Retorno de 1 minuto, dentro do pregao (reset por sessao). "
          "IC95% via Fisher z.\n", flush=True)

    ret_win = b.retornos_1min(win, dias_is)
    ret_wdo = b.retornos_1min(wdo, dias_is)
    # Alinha os dois instrumentos no MESMO indice de minutos antes de
    # qualquer deslocamento -- os dois CSVs podem ter minutos faltantes
    # distintos (feriado parcial, falha pontual de feed).
    idx_comum = ret_win.index.intersection(ret_wdo.index).sort_values()
    ret_win = ret_win.reindex(idx_comum)
    ret_wdo = ret_wdo.reindex(idx_comum)

    print(f"{'lag(min)':>8} | {'WDO lidera WIN':<34} | {'WIN lidera WDO':<34}")
    print(f"{'':>8} | {'r':>8} {'IC95%':>18} {'n':>7} | {'r':>8} {'IC95%':>18} {'n':>7}")
    print("-" * 92)
    for lag in LAGS:
        if lag == 0:
            wdo_lidera = b.corr_com_ic(ret_wdo, ret_win)
            win_lidera = wdo_lidera  # contemporaneo -- mesma coisa nos dois sentidos
        else:
            win_deslocado = b.desloca_dentro_do_dia(ret_win, lag)
            wdo_deslocado = b.desloca_dentro_do_dia(ret_wdo, lag)
            wdo_lidera = b.corr_com_ic(ret_wdo, win_deslocado)   # ret_wdo[t] x ret_win[t+lag]
            win_lidera = b.corr_com_ic(ret_win, wdo_deslocado)   # ret_win[t] x ret_wdo[t+lag]
        ic_a = f"[{wdo_lidera['lo']:+.4f};{wdo_lidera['hi']:+.4f}]"
        ic_b = f"[{win_lidera['lo']:+.4f};{win_lidera['hi']:+.4f}]"
        print(f"{lag:>8} | {wdo_lidera['r']:>+8.4f} {ic_a:>18} {wdo_lidera['n']:>7} | "
              f"{win_lidera['r']:>+8.4f} {ic_b:>18} {win_lidera['n']:>7}", flush=True)

    print("\nLeitura: r negativo e' esperado em lag=0 (WIN/WDO andam em "
          "correlacao negativa forte minuto a minuto, ja' documentado desde "
          "a G4). A pergunta desta geracao e' se |r| em lag>=1 e' GRANDE o "
          "bastante para virar sinal executavel -- nao so' estatisticamente "
          "diferente de zero (n grande torna isso quase garantido).")


if __name__ == "__main__":
    main()
