"""Port PADRAO do Win.mq5 (v2.05) e do Win_c1.mq5 (v2.06): tempo grafico H1, filtro superior H3.

Desde 2026-10-06 (frente Z1, escolha do dono a partir da Y1b) os dois EAs calculam em H1 com o filtro superior em
H3, fixos no codigo. Este modulo e' o port de referencia desse padrao:
  - a logica vem de `combinacoes/y_tempos/win/port_win_tf.py` (copia parametrizada de `port_win.py`, provada
    byte a byte contra o original no M5 na Y1);
  - o par base -> superior e' o do wrapper `combinacoes/y_tempos/win/roda_y1b.py` (SUPB: 60 -> 180), o mesmo
    usado na Y1b (Win H1 +1.570, Win_c1 H1 +2.267 com custo, 2022-2026).

`port_win.py` NAO muda: ele e' o M5 historico (v2.04/v2.05) de que outros estudos dependem.

Desde 2026-10-06 (frente Z8; EAs Win v2.06 / Win_c1 v2.07): regra NaoOperarGapATR = 1,0 -- nenhuma entrada no dia
em que |abertura - fechamento anterior| >= 1,0 x ATR14 D1 (`filtro_gap.py`, mesma definicao do z7.py). Em 2026 os
dias bloqueados sao 03/03, 08/04 e 05/10. `rodar(..., gap=False)` reproduz a versao anterior.

Rodado como script, grava `resultados/Win.csv` e `resultados/Win_c1.csv` em H1 (2026-01-02 -> 2026-10-05, formato de
`dados.trade` / `dados.salvar`). Antes de gravar, os CSVs M5 que estiverem la' sao movidos uma unica vez para
`resultados_M5_historico/` (se ja' houver copia la', nada e' movido de novo).

Uso: python port_win_padrao.py [--inicio 2026-01-02] [--fim 2026-10-05] [--so Win|Win_c1] [--sem-salvar]
"""
import argparse, shutil, sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI / "combinacoes" / "y_tempos" / "win"))

import dados as D
import filtro_gap
import port_win_tf as P

TF_MIN, SUP_MIN = 60, 180     # H1 / H3 (roda_y1b.SUPB[60] = 180)
PARAMS = {**P.PARAMS, "tf_min": TF_MIN, "sup_min": SUP_MIN}
PARAMS_C1 = {**P.PARAMS_C1, "tf_min": TF_MIN, "sup_min": SUP_MIN}
ROBOS = (("Win", PARAMS), ("Win_c1", PARAMS_C1))
HIST_M5 = AQUI / "resultados_M5_historico"


def rodar(nome: str, inicio: date = date(2026, 1, 2), fim: date = date(2026, 10, 5), salvar=True, verbose=True,
          gap=True):
    """gap=True (padrao v2.06/v2.07): tira as operacoes com ENTRADA em dia bloqueado pela regra NaoOperarGapATR
    (filtro_gap.py, k=1,0, dias do WIN$N). Pode remover: o robo e' day trade (0 operacoes atravessam a noite) e o
    replay nao guarda estado que dependa das operacoes de um dia para o outro (nem saldo)."""
    p = PARAMS_C1 if nome == "Win_c1" else PARAMS
    out = P.rodar(nome, p, inicio, fim, salvar=False, verbose=verbose)
    if gap:
        n0 = len(out)
        out = filtro_gap.filtra(out)
        if verbose:
            print(f"[{nome}] NaoOperarGapATR: {n0 - len(out)} operacoes removidas em dias bloqueados", flush=True)
    if salvar:
        print("salvo:", D.salvar(nome, out), flush=True)
    return out


def guarda_m5(nome: str):
    """Move resultados/<nome>.csv (M5) para resultados_M5_historico/ antes do 1o H1. So' uma vez."""
    src = AQUI / "resultados" / f"{nome}.csv"
    dst = HIST_M5 / f"{nome}.csv"
    if src.exists() and not dst.exists():
        HIST_M5.mkdir(exist_ok=True)
        shutil.move(str(src), str(dst))
        print("M5 historico:", dst, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", default="2026-01-02"); ap.add_argument("--fim", default="2026-10-05")
    ap.add_argument("--so", default=None); ap.add_argument("--sem-salvar", action="store_true")
    a = ap.parse_args()
    ini, fim = date.fromisoformat(a.inicio), date.fromisoformat(a.fim)
    for nome, _ in ROBOS:
        if a.so and a.so != nome:
            continue
        if not a.sem_salvar:
            guarda_m5(nome)
        P.resumo(nome, rodar(nome, ini, fim, salvar=not a.sem_salvar))
