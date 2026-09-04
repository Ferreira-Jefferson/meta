"""MOMENTO CURTO -- janelas de TAMANHO FIXO (10/5/2/1 barras), pedido do
dono, 2026-08-28.

## A pergunta

Dia, multi-dia e semana foram todos refutados (cara-ou-coroa nas 3
escalas). O dono levantou a hipotese oposta: talvez os poucos MINUTOS
antes da decisao carreguem mais informacao do que qualquer periodo longo.

Ate aqui as janelas eram FRACOES do tempo decorrido (crescem junto com o
pregao: "ultimos 10%" sao 15 minutos as 10h e 90 minutos as 16h). Agora
elas sao TAMANHO FIXO, ancoradas no presente:

    t1 (100%) = das ultimas 10 barras ate agora
    t2 (50%)  = das ultimas  5 barras ate agora
    t3 (25%)  = das ultimas  2 barras ate agora
    t4 (10%)  = a barra IMEDIATAMENTE anterior

Mesma mecanica de sempre: cada janela vira so' ALTA ou QUEDA (delta
exatamente zero descarta o instante inteiro -- nunca vira "zero" a
forca), maioria manda, empate 2 a 2 nao opera.

## Em qual dia

Pedido do dono: testar no dia em que o sinal ANTIGO (dia inteiro,
fracionario) mais ERROU -- se o momento curto ajuda justamente nos
minutos em que olhar o pregao inteiro atrapalhou, e' o teste mais direto
que existe. Este script RANQUEIA os 33 pregoes pela acertividade do sinal
de DIA (o mesmo de `wdof1_padrao_semana_2026_08_28.py`, horizonte ja'
fixo em 30 barras, a convencao estabelecida) e escolhe o PIOR com pelo
menos 30 decisoes -- nao chuta qual foi, mede.

## O que NAO fazer com o resultado

Isto e' UM dia, escolhido por ser o pior de OUTRO sinal -- exploracao
dirigida, nao confirmacao. "O pior dia de um sinal e' o melhor dia de
outro" e' exatamente o tipo de coincidencia que so' amostra grande decide
-- foi assim que 28/08 pareceu bom sozinho e nao era (33 pregoes
mostraram cara-ou-coroa). Se o momento curto aparecer bom aqui, o proximo
passo obrigatorio e' rodar nos 33 pregoes inteiros, nunca acreditar so'
neste.

Uso: `python -u scripts/daytrade/wdof1_padrao_momentum_curto_2026_08_28.py`
"""
from __future__ import annotations

import sys
from collections import Counter
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
    SYMBOL_LABEL,
    _letras,
    cabecalho,
    direcao_do_padrao,
    linha,
)
from wdof1_padrao_semana_2026_08_28 import HORIZONTE  # noqa: E402
from wdof1_padrao_semana_2026_08_28 import montar as montar_dia_semana  # noqa: E402

#: Janelas FIXAS, em barras para tras -- nao mais fracao do tempo decorrido.
OFFSETS = (10, 5, 2, 1)
MINIMO_N_RANKING = 30


def _sinal(v: int | None) -> int:
    return v if v is not None else 0


def escolher_pior_dia(df: pd.DataFrame, minimo_n: int = MINIMO_N_RANKING):
    """Ranqueia os pregoes pela acertividade do sinal de DIA (fracionario,
    horizonte fixo `HORIZONTE`, a convencao ja' estabelecida) e devolve a
    lista ordenada do PIOR para o melhor -- a escolha do dono e' medida,
    nao suposta."""
    instantes, _n_sessoes, _n_semanas = montar_dia_semana(df)
    por_dia: dict[object, list] = {}
    for inst in instantes:
        if inst.dir_dia is not None:
            por_dia.setdefault(inst.sessao, []).append(inst)
    ranking = []
    for dia, sub in por_dia.items():
        if len(sub) < minimo_n:
            continue
        acc = 100 * sum(1 for i in sub if i.dir_dia == i.desfecho) / len(sub)
        ranking.append((acc, dia, len(sub)))
    ranking.sort()
    return ranking


def padrao_fixo(fech: np.ndarray, i: int) -> str | None:
    """As 4 letras usando janelas de TAMANHO FIXO (10/5/2/1 barras para
    tras), nunca fracao do tempo decorrido. `None` se faltar historico ou
    alguma janela nao tiver direcao (delta exatamente zero)."""
    letras = []
    for off in OFFSETS:
        j = i - off
        if j < 0:
            return None
        delta = fech[i] - fech[j]
        if delta == 0:
            return None
        letras.append("A" if delta > 0 else "Q")
    return "".join(letras)


def main() -> None:
    if not M1.exists():
        raise SystemExit(f"[momentum] falta {M1} -- rode o cache do M1 primeiro.")
    df = pd.read_parquet(M1)

    print("=" * 108)
    print(f"MOMENTO CURTO (janelas fixas: 10/5/2/1 barras) -- {SYMBOL_LABEL} M1")
    print("=" * 108)
    print("t1(100%)=ult.10 barras | t2(50%)=ult.5 | t3(25%)=ult.2 | t4(10%)=a anterior")
    print(f"Desfecho fixo em {HORIZONTE} barras -- a convencao ja' estabelecida.")

    ranking = escolher_pior_dia(df)
    print(f"\n{len(ranking)} pregoes ranqueados pela acertividade do sinal de DIA "
          f"(fracionario, horizonte {HORIZONTE}, n >= {MINIMO_N_RANKING})")
    print("--- 3 piores e 3 melhores, para contexto ---")
    print(f"{'posicao':>8} {'pregao':>12} {'n':>6} {'acerto (dia)':>13}")
    for pos, (acc, dia, n) in enumerate(ranking, 1):
        if pos <= 3 or pos > len(ranking) - 3:
            print(f"{pos:>8} {str(dia):>12} {n:>6,} {num_br(acc, 1) + '%':>13}")
        elif pos == 4:
            print(f"{'...':>8}")

    acc_pior, dia_escolhido, n_pior = ranking[0]
    print(f"\nESCOLHIDO (o pior): {dia_escolhido} -- sinal de dia acertou so' "
          f"{num_br(acc_pior, 1)}% em {n_pior} decisoes")

    idx = pd.DatetimeIndex(df.index).tz_convert("America/Sao_Paulo")
    bars_dia = df[idx.date == dia_escolhido]
    print(f"barras deste pregao: {len(bars_dia)}")

    fech = bars_dia["close"].to_numpy(dtype=float)
    n = len(fech)
    sinal_dia, sinal_curto, padroes_curto, desfechos = [], [], [], []
    for i in range(n):
        if i + HORIZONTE >= n:
            continue
        delta_out = fech[i + HORIZONTE] - fech[i]
        if delta_out == 0:
            continue
        # `_letras(fech, i, 0)`: base=0 NESTA fatia local e' o inicio deste
        # MESMO pregao -- resultado identico ao sinal de dia global usado
        # no ranking (a funcao so' usa diferencas relativas).
        p_dia = _letras(fech, i, 0)
        p_curto = padrao_fixo(fech, i)
        if p_dia is None and p_curto is None:
            continue
        d_dia = direcao_do_padrao(p_dia) if p_dia else None
        d_curto = direcao_do_padrao(p_curto) if p_curto else None
        sinal_dia.append(_sinal(d_dia))
        sinal_curto.append(_sinal(d_curto))
        padroes_curto.append(p_curto)
        desfechos.append(1 if delta_out > 0 else -1)

    print(f"\ndecisoes neste pregao (pelo menos um dos dois sinais disponivel): "
          f"{len(desfechos)}")

    print("\n--- comparacao direta, sobre o MESMO pregao e o MESMO desfecho ---")
    cabecalho(f"pregao {dia_escolhido}, desfecho em {HORIZONTE} barras")
    linha("sinal de DIA (fracionario, o antigo -- ja' era ruim aqui)", sinal_dia, desfechos)
    linha("MOMENTO CURTO (10/5/2/1 barras, o novo)", sinal_curto, desfechos)

    print("\n--- padroes de momento curto, neste pregao (n >= 10) ---")
    contagem = Counter(p for p in padroes_curto if p is not None)
    print(f"{'padrao':>8} {'aposta':>8} {'n':>5} {'acerto':>8}")
    print("-" * 34)
    for padrao, _n in contagem.most_common():
        pares = [(s, m) for p, s, m in zip(padroes_curto, sinal_curto, desfechos)
                 if p == padrao]
        if len(pares) < 10:
            continue
        acc = 100 * sum(1 for s, m in pares if s == m) / len(pares)
        d = direcao_do_padrao(padrao)
        aposta = "compra" if d == 1 else ("venda" if d == -1 else "-")
        print(f"{padrao:>8} {aposta:>8} {len(pares):>5} {num_br(acc, 1) + '%':>8}")

    print(f"\nUM pregao, escolhido por ser o PIOR de outro sinal -- exploracao dirigida,")
    print("nao confirmacao. Promissor aqui pede rodar nos 33 pregoes inteiros antes de")
    print("acreditar, pelo mesmo motivo que o dia 28/08 parecia bom sozinho e nao era.")


if __name__ == "__main__":
    main()
