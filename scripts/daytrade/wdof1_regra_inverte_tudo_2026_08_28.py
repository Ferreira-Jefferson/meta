"""Regra corrigida, 2026-08-28: "se disser comprar eu vendo, se disser
vender eu compro" -- inversao TOTAL do sinal de dia, nao so' da perna de
compra.

## Diferenca do teste anterior

`wdof1_regra_so_vende_2026_08_28.py` testou uma regra ASSIMETRICA (so'
invertia compra; vender ficava vender), leitura literal do primeiro
pedido -- que colapsava a aposta final num unico estado (vende-ou-nao-
opera) e saiu pior que 50% ate no dia de origem. A intencao real era o
OPOSTO completo: compra vira venda E venda vira compra. Empate continua
sem operar -- isso nao mudou.

## O que isso e', antes do numero

Inverter TODAS as apostas de um sinal e' ALGEBRA, nao descoberta: se o
original acertava X% num conjunto de instantes, o invertido acerta
EXATAMENTE (100-X)% nos MESMOS instantes -- todo acerto vira erro e todo
erro vira acerto, sempre. O sinal de dia (fracionario, h=30 ja' medido em
`wdof1_padrao_semana_2026_08_28.py`) acertava 48,3% em 9.296 instantes; a
inversao total tem de dar, por definicao, 51,7% nos MESMOS 9.296. Isto
nao e' resultado novo, e' o mesmo numero visto do outro lado. O que
PRECISA ser medido de novo e' se 51,7% bate o acaso (ou se e' so' o "lado
fixo" -- apostar sempre no lado que mais aparece -- por outro nome) e a
dispersao pregao a pregao, que a algebra nao entrega sozinha.

Horizonte fixo em 30 barras (convencao ja' estabelecida). 33 pregoes.

Uso: `python -u scripts/daytrade/wdof1_regra_inverte_tudo_2026_08_28.py`
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
    _letras,
    cabecalho,
    direcao_do_padrao,
    linha,
)
from wdof1_padrao_semana_2026_08_28 import HORIZONTE  # noqa: E402

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
        original.append(0 if d is None else d)
        sessoes_i.append(sessoes[i])
        movs.append(1 if delta > 0 else -1)
    return np.array(original), np.array(sessoes_i), np.array(movs), n_sessoes


def main() -> None:
    df = pd.read_parquet(M1)
    original, sessoes_i, movs, n_sessoes = montar(df)
    invertido = -original       # compra(+1)->venda(-1) E venda(-1)->compra(+1); empate(0) continua 0

    print("=" * 100)
    print("REGRA: COMPRAR -> vendo | VENDER -> compro  (inversao TOTAL do sinal de dia)")
    print("=" * 100)
    print(f"{n_sessoes} pregoes | {len(movs):,} instantes | horizonte fixo {HORIZONTE} barras\n")

    print("--- sinal ORIGINAL (referencia, ja' medido antes) ---")
    cabecalho(f"desfecho em {HORIZONTE} barras")
    linha("sinal de DIA, original", original.tolist(), movs.tolist())
    print("\n--- sinal INVERTIDO (a regra pedida agora) ---")
    linha("sinal de DIA, invertido (compra<->venda)", invertido.tolist(), movs.tolist())
    print("\n(as duas linhas somam 100% de acerto sobre o MESMO n -- e' algebra, nao dado novo)")

    print("\n--- so' no dia de ORIGEM (2026-07-31), onde a ideia nasceu ---")
    m_dia = sessoes_i == DIA_ORIGEM
    if m_dia.any():
        sin_dia, mv_dia = invertido[m_dia], movs[m_dia]
        mask = sin_dia != 0
        acc = 100 * float((sin_dia[mask] == mv_dia[mask]).mean()) if mask.any() else float("nan")
        print(f"  n={int(mask.sum())}  acerto={num_br(acc, 1)}%  "
              "(a versao assimetrica anterior tinha dado so' 42,4% aqui)")

    print("\n--- pregao a pregao, sinal INVERTIDO (so' sessoes com n >= 30) ---")
    por_dia = defaultdict(list)
    for s, sin, m in zip(sessoes_i, invertido, movs):
        if sin != 0:
            por_dia[s].append((int(sin), int(m)))
    linhas = []
    for s, pares in sorted(por_dia.items()):
        if len(pares) < 30:
            continue
        acc = 100 * sum(1 for a, b in pares if a == b) / len(pares)
        linhas.append((s, len(pares), acc))
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
