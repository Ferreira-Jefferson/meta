"""Regra literal do dono, 2026-08-28: "se ele falar pra comprar eu vendo,
se falar pra nao operar eu respeito e nao opero".

## O que a regra faz -- uma consequencia que precisa ficar clara antes do
## numero

O sinal de DIA (fracionario, ja' medido) da' 3 respostas por instante:
compra, venda ou nao-opera (empate 2 a 2). A regra do dono muda so' o que
acontece quando ele diz COMPRA -- vira VENDA. O caso "sinal diz VENDER"
nao foi mencionado, entao fica como estava (venda continua venda).

Consequencia algebrica, que precisa ser dita antes de qualquer tabela: a
aposta final SO' TEM DOIS ESTADOS -- VENDE (sempre que o sinal nao
empatar, nao importa se ele tinha dito compra ou venda) ou NAO OPERA
(quando empata). A DIRECAO original do sinal deixa de decidir nada; so'
decide SE ele disparou. A pergunta deixa de ser "inverter ajuda" e vira
"vender sempre que o sinal tiver uma opiniao bate vender em QUALQUER
instante (empate incluso)?".

## Por que NAO testar so' no dia de origem (2026-07-31)

Foi la' que a observacao nasceu: comprar errou 91,2% das vezes (31 de 34).
Inverter um sinal que errou 91% NAQUELE DIA acerta 91% NAQUELE DIA por
ALGEBRA -- nao e' descoberta, e' definicao (se X errou 91% das vezes,
1-X acerta 91% das MESMAS vezes, sempre, em qualquer serie). A pergunta
que importa e' se o desalinhamento aparece nos OUTROS 32 dias tambem, ou
se 07-31 foi so' um dia de reversao forte que nao se repete. Por isso
este script roda nos 33 pregoes inteiros, com 07-31 destacado a' parte
so' como referencia de onde a ideia veio -- NUNCA como prova.

## Nulo correto

A aposta final e' CONSTANTE (venda, sempre que dispara) -- o mesmo
problema do teste aninhado anterior: girar um sinal constante no tempo
nao muda nada (`com_nulo`/`linha` ficariam degenerados de novo). O nulo
aqui gira a MASCARA "disparou" (nao empatou) contra a serie de
desfechos, exatamente como `null_de_selecao` do script anterior.

Horizonte fixo em 30 barras (convencao ja' estabelecida). Nunca atravessa
a noite. 33 pregoes.

Uso: `python -u scripts/daytrade/wdof1_regra_so_vende_2026_08_28.py`
"""
from __future__ import annotations

import random
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
    _letras,
    direcao_do_padrao,
)
from wdof1_padrao_semana_2026_08_28 import HORIZONTE  # noqa: E402

N_DESLOCAMENTOS = 400
SEMENTE = 20260828
DIA_ORIGEM = pd.Timestamp("2026-07-31").date()


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

    original, sessoes_i, movs = [], [], []
    for i in range(len(fech)):
        n = int(sessao_da_barra[i])
        dia_start = inicios[n]
        limite = fim[n]
        p = _letras(fech, i, dia_start)
        d = direcao_do_padrao(p) if p else None
        if i + HORIZONTE > limite:
            continue                    # o desfecho NUNCA atravessa a noite
        delta = fech[i + HORIZONTE] - fech[i]
        if delta == 0:
            continue
        original.append(0 if d is None else d)   # +1 compra / -1 venda / 0 empate
        sessoes_i.append(sessoes[i])
        movs.append(1 if delta > 0 else -1)
    return np.array(original), np.array(sessoes_i), np.array(movs), n_sessoes


def null_de_selecao(mask: np.ndarray, movs: np.ndarray):
    """Gira a MASCARA (quem disparou), nao o sinal -- a aposta e' constante
    (venda) sempre que a mascara e' verdadeira, entao girar o SINAL seria
    degenerado (mesmo bug do script anterior)."""
    real = 100.0 * float((movs[mask] == -1).mean()) if mask.any() else 0.0
    rng = random.Random(SEMENTE)
    n = len(movs)
    nulos = []
    for _ in range(N_DESLOCAMENTOS):
        k = rng.randrange(1, n)
        m2 = np.roll(mask, k)
        if m2.any():
            nulos.append(100.0 * float((movs[m2] == -1).mean()))
    nulos.sort()
    p = (sum(1 for x in nulos if x >= real) + 1) / (len(nulos) + 1)
    p05, p95 = nulos[int(0.05 * len(nulos))], nulos[int(0.95 * len(nulos))]
    return real, int(mask.sum()), p05, p95, p


def main() -> None:
    df = pd.read_parquet(M1)
    original, sessoes_i, movs, n_sessoes = montar(df)

    print("=" * 100)
    print("REGRA: sinal diz COMPRAR -> eu VENDO | sinal diz NAO-OPERA -> eu NAO OPERO")
    print("=" * 100)
    print(f"{n_sessoes} pregoes | {len(movs):,} instantes | horizonte fixo {HORIZONTE} barras\n")
    print("Consequencia algebrica: a aposta final so' tem 2 estados -- VENDE sempre que o")
    print("sinal nao empatar (nao importa se dizia compra ou venda), ou NAO OPERA.")

    mask_dispara = original != 0
    mask_era_compra = original == 1
    mask_era_venda = original == -1
    print(f"\ninstantes: {int(mask_dispara.sum()):,} com sinal (nao-empate), "
          f"{int((~mask_dispara).sum()):,} empate (nao opera)")

    print("\n--- contexto: acerto do sinal ORIGINAL, sem inverter, 33 pregoes ---")
    acc_compra_orig = 100 * (movs[mask_era_compra] == 1).mean()
    acc_venda_orig = 100 * (movs[mask_era_venda] == -1).mean()
    print(f"  quando dizia COMPRAR: n={int(mask_era_compra.sum()):,}  "
          f"acerto original={num_br(acc_compra_orig, 1)}%")
    print(f"  quando dizia VENDER : n={int(mask_era_venda.sum()):,}  "
          f"acerto original={num_br(acc_venda_orig, 1)}%")

    print("\n--- a REGRA (vende sempre que o sinal disparar) -- 33 pregoes ---")
    real, n, p05, p95, p = null_de_selecao(mask_dispara, movs)
    lado_fixo = 100 * float((movs == -1).mean())
    print(f"  n={n:,}  acerto da regra={num_br(real, 1)}%  "
          f"(mercado caiu no periodo todo: {num_br(lado_fixo, 1)}%)")
    print(f"  acaso (deslocamento da mascara): [{num_br(p05, 1)}% , {num_br(p95, 1)}%]  "
          f"p={num_br(p, 3)}")
    print("  ACIMA do acaso" if p <= 0.05 else "  dentro do acaso")

    print("\n--- so' no dia de ORIGEM (2026-07-31), referencia -- NAO decide nada ---")
    m_dia = sessoes_i == DIA_ORIGEM
    if m_dia.any():
        real_d, n_d, p05_d, p95_d, p_d = null_de_selecao(mask_dispara & m_dia, movs)
        print(f"  n={n_d}  acerto da regra={num_br(real_d, 1)}%  p={num_br(p_d, 3)}")
        print("  (mesmo dia que gerou a ideia -- bater bem aqui e' esperado por algebra,")
        print("  nao e' confirmacao de nada)")

    print("\n--- pregao a pregao (so' sessoes com n >= 30) -- a dispersao real ---")
    por_dia = defaultdict(list)
    for s, disp, m in zip(sessoes_i, mask_dispara, movs):
        if disp:
            por_dia[s].append(m)
    linhas = []
    for s, ms in sorted(por_dia.items()):
        if len(ms) < 30:
            continue
        acc = 100 * sum(1 for m in ms if m == -1) / len(ms)
        linhas.append((s, len(ms), acc))
    print(f"{'pregao':>12} {'n':>5} {'acerto':>8}")
    print("-" * 28)
    for s, n_, acc in linhas:
        marca = "  <- dia de origem" if s == DIA_ORIGEM else ""
        print(f"{str(s):>12} {n_:>5} {num_br(acc, 1) + '%':>8}{marca}")
    if linhas:
        vs = sorted(a for _, _, a in linhas)
        acima50 = sum(1 for a in vs if a > 50)
        print(f"\n{len(linhas)} pregoes | mediana {num_br(vs[len(vs) // 2], 1)}% | "
              f"pior {num_br(vs[0], 1)}% | melhor {num_br(vs[-1], 1)}%")
        print(f"acima de 50% em {acima50}/{len(linhas)} pregoes")


if __name__ == "__main__":
    main()
