"""DIA (4 janelas do pregao) x ULTIMOS 10% sozinho -- qual acerta mais?
Pergunta direta do dono, 2026-08-28.

Reaproveita as pecas ja' medidas (`_letras`, `direcao_do_padrao`,
`com_nulo`, `linha` de `wdof1_padrao_multiescala_2026_08_28.py`) mas monta
os DOIS sinais sobre o MESMO conjunto de instantes e o MESMO desfecho --
os scripts anteriores tinham cada um seu proprio recorte de admissao, e
comparar numeros de amostras diferentes seria comparar coisas diferentes.

  dia  = majoria das 4 janelas fracionarias do PREGAO inteiro (t1=100% do
         dia .. t4=ultimos 10% do dia) -- o sinal original.
  10%  = so' a janela t4 SOZINHA (compara agora contra o inicio dos
         ultimos 10% do dia), sem combinar com as outras 3.

Desfecho fixo em 30 barras (convencao ja' estabelecida), nunca atravessa
a noite. 33 pregoes.

Uso: `python -u scripts/daytrade/wdof1_dia_vs_ultimos10_2026_08_28.py`
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br  # noqa: E402
from wdof1_padrao_multiescala_2026_08_28 import (  # noqa: E402
    M1,
    MIN_BARRAS_JANELA,
    _letras,
    cabecalho,
    direcao_do_padrao,
    linha,
)
from wdof1_padrao_semana_2026_08_28 import HORIZONTE  # noqa: E402

FRACAO_10 = 0.10


def montar(df: pd.DataFrame):
    fech = df["close"].to_numpy(dtype=float)
    idx = pd.DatetimeIndex(df.index).tz_convert("America/Sao_Paulo")
    sessoes = idx.date
    inicios = [k for k, s in enumerate(sessoes) if k == 0 or s != sessoes[k - 1]]
    n_sessoes = len(inicios)
    fim = {}
    for n, ini in enumerate(inicios):
        fim[n] = (inicios[n + 1] - 1) if n + 1 < n_sessoes else len(fech) - 1
    sessao_da_barra = np.empty(len(fech), dtype=int)
    for n, ini in enumerate(inicios):
        sessao_da_barra[ini:fim[n] + 1] = n

    dias_dia, dias_10, sessoes_i, movs = [], [], [], []
    for i in range(len(fech)):
        n = int(sessao_da_barra[i])
        dia_start = inicios[n]
        limite = fim[n]
        decorrido = i - dia_start
        base10 = i - int(round(decorrido * FRACAO_10))

        p_dia = _letras(fech, i, dia_start)
        d_dia = direcao_do_padrao(p_dia) if p_dia else None

        d_10 = None
        if i - base10 >= MIN_BARRAS_JANELA and fech[i] != fech[base10]:
            d_10 = 1 if fech[i] > fech[base10] else -1

        if d_dia is None and d_10 is None:
            continue
        if i + HORIZONTE > limite:
            continue                    # o desfecho NUNCA atravessa a noite
        delta = fech[i + HORIZONTE] - fech[i]
        if delta == 0:
            continue

        dias_dia.append(d_dia if d_dia is not None else 0)
        dias_10.append(d_10 if d_10 is not None else 0)
        sessoes_i.append(sessoes[i])
        movs.append(1 if delta > 0 else -1)
    return dias_dia, dias_10, sessoes_i, movs, n_sessoes


def main() -> None:
    df = pd.read_parquet(M1)
    dias_dia, dias_10, sessoes_i, movs, n_sessoes = montar(df)

    print("=" * 100)
    print(f"DIA (4 janelas do pregao) x ULTIMOS 10% sozinho (t4) -- mesmo conjunto, "
          f"{n_sessoes} pregoes")
    print("=" * 100)
    print(f"{len(movs):,} instantes com desfecho valido, horizonte fixo {HORIZONTE} barras\n")

    cabecalho(f"desfecho em {HORIZONTE} barras")
    linha("sinal de DIA (4 janelas do pregao inteiro)", dias_dia, movs)
    linha("sinal dos ULTIMOS 10% sozinho (t4)", dias_10, movs)

    print("\n--- pregao a pregao, os dois lado a lado (so' sessoes com n >= 30) ---")
    agr = defaultdict(lambda: {"dia": [], "d10": [], "mov": []})
    for d, d10, s, m in zip(dias_dia, dias_10, sessoes_i, movs):
        agr[s]["dia"].append(d)
        agr[s]["d10"].append(d10)
        agr[s]["mov"].append(m)

    print(f"{'pregao':>12} {'n':>5} {'dia':>8} {'ult.10%':>9}")
    print("-" * 38)
    difs = []
    for s in sorted(agr):
        dd, d10, mv = agr[s]["dia"], agr[s]["d10"], agr[s]["mov"]
        if len(mv) < 30:
            continue
        n_dia = sum(1 for a in dd if a != 0)
        n_10 = sum(1 for a in d10 if a != 0)
        acc_dia = (100 * sum(1 for a, b in zip(dd, mv) if a != 0 and a == b) / n_dia
                   if n_dia else float("nan"))
        acc_10 = (100 * sum(1 for a, b in zip(d10, mv) if a != 0 and a == b) / n_10
                  if n_10 else float("nan"))
        print(f"{str(s):>12} {len(mv):>5} {num_br(acc_dia, 1) + '%':>8} "
              f"{num_br(acc_10, 1) + '%':>9}")
        if n_dia and n_10:
            difs.append(acc_10 - acc_dia)

    if difs:
        venceu10 = sum(1 for d in difs if d > 0)
        print(f"\nultimos 10% vence o dia em {venceu10}/{len(difs)} pregoes | "
              f"diferenca mediana {num_br(sorted(difs)[len(difs) // 2], 1)} pp")
        print("Nenhum dos dois bateu o acaso na tabela agregada -- esta comparacao")
        print("diz qual erra MENOS, nao qual acerta de verdade.")


if __name__ == "__main__":
    main()
