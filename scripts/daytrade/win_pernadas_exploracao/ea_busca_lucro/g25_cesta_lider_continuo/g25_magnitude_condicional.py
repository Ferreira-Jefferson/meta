# -*- coding: utf-8 -*-
"""PASSO 2 do mandato (G25): teste de MAGNITUDE condicional -- quando a
CESTA se move MUITO num curto intervalo, isso carrega mais informacao sobre
o WIN do que um movimento qualquer? MESMO metodo exato da G24 (que testou o
WDO), agora com o indice sintetico causal da cesta no lugar do WDO.

Desenho CAUSAL, sem reaproveitar a janela do proprio evento (evita so'
redescobrir a correlacao CONTEMPORANEA do passo 1, lag=0):

  ret_cesta_passado_k(t) = media(retorno % das 24 acoes, k min, ate' t)
  ret_win_futuro_k(t)    = WIN.close[t+k] - WIN.close[t]  (estritamente > t,
                                                             janela NAO sobreposta)

"Movimento grande" = `|ret_cesta_passado_k(t)|` acima do quantil causal
(burn-in de 20 dias INTEIROS anteriores, expanding -- mesma disciplina da
G4/G24) -- quartil (0,75) e decil (0,90). Compara, para cada `k` em
{1,3,5}:

  - taxa de "mesma direcao" (sign(ret_win_futuro_k) == sign(ret_cesta_passado_k))
    no grupo CONDICIONAL (movimento grande) vs no grupo de TODOS os eventos
    validos (baseline).
  - magnitude media de |ret_win_futuro_k| nos dois grupos (transmissao de
    VOLATILIDADE, independente de direcao) -- mesma pergunta que a G24 achou
    positiva para o WDO (+27,9% a +50,9%).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g25_cesta_lider_continuo/g25_magnitude_condicional.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import g25_base as b  # noqa: E402

KS = [1, 3, 5]
QUANTIS = [0.75, 0.90]


def _linha(rotulo: str, acerto: np.ndarray, mag: np.ndarray) -> str:
    n = len(acerto)
    if n == 0:
        return f"      {rotulo:<28} n=0"
    k = int(acerto.sum())
    lo, hi = b.ic95_wilson(k, n)
    return (f"      {rotulo:<28} n={n:>6}  mesma_dir={k:>6} ({100*k/n:5.1f}%, "
             f"IC95=[{100*lo:5.1f}%;{100*hi:5.1f}%])  |ret_win_fwd|_medio={mag.mean():7.2f}pts")


def main() -> None:
    win = b.carrega_win()
    cesta = b.carrega_cesta()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"Magnitude condicional G25 (cesta) -- IS (jan-jun/2026, {len(dias_is)} pregoes).")
    print("ret_cesta_passado_k(t) = media(retorno % das 24 acoes, k min, causal, <= t)")
    print("ret_win_futuro_k(t)    = WIN[t+k]-WIN[t]  (estritamente futuro, nao sobreposta)")
    print("Quantil CAUSAL de |ret_cesta_passado_k|, burn-in 20 dias.\n", flush=True)

    win_bars = b.bars_dos_dias(win, dias_is)
    grade = win_bars.index

    for k in KS:
        ret_cesta_passado = b.retorno_k_cesta(cesta, grade, k)
        ret_win_futuro_bruto = b.retorno_k_min(win, dias_is, k)
        # ret_win_futuro_k(t) = WIN[t+k]-WIN[t] == ret_win_futuro_bruto deslocado
        # k barras PARA TRAS no tempo (resultado[t] = serie_bruta[t+k]).
        ret_win_futuro = b.desloca_dentro_do_dia(ret_win_futuro_bruto, k)

        idx_comum = ret_cesta_passado.index.intersection(ret_win_futuro.index).sort_values()
        ret_cesta_passado = ret_cesta_passado.reindex(idx_comum)
        ret_win_futuro = ret_win_futuro.reindex(idx_comum)

        validos = ret_cesta_passado.notna() & ret_win_futuro.notna() & (ret_cesta_passado != 0)
        cesta_v = ret_cesta_passado[validos]
        win_v = ret_win_futuro[validos]
        mesma_dir_todos = (np.sign(cesta_v) == np.sign(win_v)).to_numpy()
        mag_todos = win_v.abs().to_numpy()

        print(f"  -- k={k}min (n_valido_baseline={len(cesta_v)}) --")
        print(_linha("BASELINE (todos os eventos)", mesma_dir_todos, mag_todos), flush=True)

        for q in QUANTIS:
            limiar = b.quantil_causal_abs(cesta_v, q)
            grande = (cesta_v.abs() >= limiar).fillna(False).to_numpy()
            if grande.sum() == 0:
                print(f"      quantil={q:.2f}: 0 eventos (burn-in insuficiente)")
                continue
            mesma_dir_grande = mesma_dir_todos[grande]
            mag_grande = mag_todos[grande]
            rotulo = f"movimento GRANDE (q>={q:.2f})"
            print(_linha(rotulo, mesma_dir_grande, mag_grande))
            lift_pp = 100 * (mesma_dir_grande.mean() - mesma_dir_todos.mean())
            lift_mag = 100 * (mag_grande.mean() / mag_todos.mean() - 1)
            print(f"      {'':<28} lift direcao = {lift_pp:+.1f}pp | "
                  f"lift magnitude = {lift_mag:+.1f}%", flush=True)
        print(flush=True)

    print("Leitura: baseline ~50% e' o esperado SE nao houver lead-lag "
          "nenhum (random walk). O mandato pede lift de direcao >= ~15-20pp "
          "(ou |r| bem acima do que a G24 ja descartou como ruido) para "
          "justificar montar geometria -- comparar os numeros acima contra "
          "esse limiar, e contra a G23 (+7,2pp) e a G24 (+0,9 a +2,3pp).")


if __name__ == "__main__":
    main()
