"""O padrao das 4 janelas na ESCALA DA SEMANA -- pedido do dono, 2026-08-28.

## A pergunta

Ate aqui as 4 janelas (100%, 50%, 25%, 10% do tempo decorrido) mediam o
PREGAO -- 100% = desde a abertura de HOJE. O dono pediu para subir mais um
nivel: 100% = desde a abertura da SEMANA (segunda-feira), 50% = ultimos
50% da semana decorrida, 25% e 10% na mesma logica. A pergunta e' se essa
leitura de escala MAIOR interfere na decisao de MINUTO -- por isso o
desfecho fica FIXO em 30 barras (o horizonte que deu o melhor sinal
isolado na rodada anterior, e o que o dono pediu para usar sempre daqui
em diante).

## Mecanica -- igual a' do dia, so' muda a BASE

`_letras(fech, i, base)` (importada de
`wdof1_padrao_multiescala_2026_08_28.py`) ja e' generica: conta em BARRAS
NEGOCIADAS entre `base` e `i`, sem se importar com o que `base`
representa. La', `base` era o inicio do PREGAO; aqui e' o inicio da
SEMANA (a primeira barra da primeira sessao da semana ISO). O array de
barras so' contem NEGOCIOS -- noites e fins de semana simplesmente nao
existem nele -- entao "ultimos 50% da semana" ja' sai medido em tempo de
mercado ABERTO, sem ajuste extra.

Consequencia esperada, que o relatorio precisa mostrar e nao so' assumir:
numa SEGUNDA-FEIRA de manha a semana "decorrida" e' quase nula -- o
padrao semanal fica quase identico ao diario (poucas barras elapsed). So'
por QUINTA/SEXTA a leitura de semana carrega historia de verdade. Por
isso o relatorio quebra por dia da semana antes de qualquer veredito.

## O desfecho continua sem atravessar a noite

O robo nunca carrega posicao de um dia para o outro -- entao, mesmo com o
SINAL olhando a semana inteira, o DESFECHO (o que o preco fez 30 barras a
frente) tem de caber no MESMO pregao. Perto do fechamento, o instante
simplesmente nao entra -- igual aos arquivos anteriores.

## O limite que mais importa aqui, dito antes da tabela

O padrao de DIA tinha 33 observacoes independentes (33 pregoes). O
padrao de SEMANA tem so' as SEMANAS -- um numero MUITO menor, e e' esse
numero, nao a contagem de milhares de barras, que decide se algo aqui e'
credivel. O relatorio imprime os dois lado a lado, e fecha com a
dispersao SEMANA a SEMANA -- a mesma disciplina que revelou, na rodada
anterior, que 1 pregao sozinho era o melhor entre 33.

Uso: `python -u scripts/daytrade/wdof1_padrao_semana_2026_08_28.py`
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
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

#: Fixo -- pedido do dono. Foi o horizonte com o melhor (embora ainda
#: dentro do acaso) p na rodada de 1 pregao.
HORIZONTE = 30
DIAS_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta")


@dataclass
class InstanteSemana:
    i: int
    sessao: object
    dia_semana: int          # 0=segunda .. 4=sexta
    dir_dia: int | None
    dir_semana: int | None
    desfecho: int             # sempre +1/-1 (0 ja' descartado na montagem)


def montar(df: pd.DataFrame) -> tuple[list[InstanteSemana], int, int]:
    fech = df["close"].to_numpy(dtype=float)
    idx = pd.DatetimeIndex(df.index).tz_convert("America/Sao_Paulo")
    sessoes = idx.date

    inicios: list[int] = []
    for k, s in enumerate(sessoes):
        if k == 0 or s != sessoes[k - 1]:
            inicios.append(k)
    n_sessoes = len(inicios)
    fim_da_sessao = {}
    for n, ini in enumerate(inicios):
        fim_da_sessao[n] = (inicios[n + 1] - 1) if n + 1 < n_sessoes else len(fech) - 1
    sessao_da_barra = np.empty(len(fech), dtype=int)
    for n, ini in enumerate(inicios):
        sessao_da_barra[ini:fim_da_sessao[n] + 1] = n

    semana_da_sessao: list[tuple[int, int]] = []
    dia_semana_da_sessao: list[int] = []
    for n, ini in enumerate(inicios):
        iso = sessoes[ini].isocalendar()
        semana_da_sessao.append((iso[0], iso[1]))
        dia_semana_da_sessao.append(iso[2] - 1)

    inicio_da_semana: dict[tuple[int, int], int] = {}
    for n, chave in enumerate(semana_da_sessao):
        inicio_da_semana.setdefault(chave, inicios[n])
    n_semanas = len(set(semana_da_sessao))

    instantes: list[InstanteSemana] = []
    for i in range(len(fech)):
        n = int(sessao_da_barra[i])
        p_dia = _letras(fech, i, inicios[n])
        p_sem = _letras(fech, i, inicio_da_semana[semana_da_sessao[n]])
        d_dia = direcao_do_padrao(p_dia) if p_dia else None
        d_sem = direcao_do_padrao(p_sem) if p_sem else None
        if d_dia is None and d_sem is None:
            continue
        limite = fim_da_sessao[n]
        if i + HORIZONTE > limite:
            continue                    # o desfecho NUNCA atravessa a noite
        delta = fech[i + HORIZONTE] - fech[i]
        if delta == 0:
            continue
        instantes.append(InstanteSemana(
            i=i, sessao=sessoes[i], dia_semana=dia_semana_da_sessao[n],
            dir_dia=d_dia, dir_semana=d_sem, desfecho=1 if delta > 0 else -1,
        ))
    return instantes, n_sessoes, n_semanas


def _sinal(valor: int | None) -> int:
    return valor if valor is not None else 0


def main() -> None:
    if not M1.exists():
        raise SystemExit(f"[semana] falta {M1} -- rode o cache do M1 primeiro.")
    df = pd.read_parquet(M1)
    instantes, n_sessoes, n_semanas = montar(df)

    print("=" * 108)
    print(f"PADRAO das 4 janelas na ESCALA DA SEMANA -- {SYMBOL_LABEL} M1, "
          f"desfecho fixo em {HORIZONTE} barras")
    print("=" * 108)
    print(f"{len(df):,} barras | {n_sessoes} pregoes | {n_semanas} SEMANAS | "
          f"{len(instantes):,} instantes com pelo menos um sinal (dia ou semana)")
    print(f"\nATENCAO: o numero que decide se isto e' credivel e' {n_semanas} -- as SEMANAS,")
    print("nao os milhares de barras. Cada semana e' UMA observacao independente da")
    print("pergunta 'a tendencia de uma semana carrega para dentro dela mesma'.")

    com_semana = [i for i in instantes if i.dir_semana is not None]
    print(f"\ninstantes com padrao de SEMANA maduro: {len(com_semana):,} de "
          f"{len(instantes):,} ({100 * len(com_semana) / len(instantes):.1f}%)")

    print("\n--- disponibilidade do padrao de semana, por dia da semana ---")
    print("(esperado: quase zero na segunda, crescente ate sexta)")
    print(f"{'dia':>10} {'instantes':>10} {'com semana':>11} {'%':>7}")
    print("-" * 44)
    for d in range(5):
        sub = [i for i in instantes if i.dia_semana == d]
        com = [i for i in sub if i.dir_semana is not None]
        pct = 100 * len(com) / len(sub) if sub else 0.0
        print(f"{DIAS_SEMANA[d]:>10} {len(sub):>10,} {len(com):>11,} {num_br(pct, 1):>6}%")

    print("\n--- sinal isolado x combinado (todos os instantes, desfecho fixo) ---")
    cabecalho(f"desfecho em {HORIZONTE} barras (nunca atravessa a noite)")
    movs = [i.desfecho for i in instantes]
    linha("dia isolado", [_sinal(i.dir_dia) for i in instantes], movs)
    linha("semana isolada", [_sinal(i.dir_semana) for i in instantes], movs)
    linha("dia E semana concordam", [
        i.dir_dia if (i.dir_dia is not None and i.dir_dia == i.dir_semana) else 0
        for i in instantes
    ], movs)
    print()
    linha("quando discordam -- aposta no DIA", [
        i.dir_dia if (i.dir_dia is not None and i.dir_semana is not None
                      and i.dir_dia != i.dir_semana) else 0
        for i in instantes
    ], movs)
    linha("quando discordam -- aposta na SEMANA", [
        i.dir_semana if (i.dir_dia is not None and i.dir_semana is not None
                         and i.dir_dia != i.dir_semana) else 0
        for i in instantes
    ], movs)

    print("\n--- so' SEXTA-FEIRA (a semana mais madura possivel) ---")
    sexta = [i for i in instantes if i.dia_semana == 4]
    if sexta:
        linha("semana isolada, so sexta", [_sinal(i.dir_semana) for i in sexta],
              [i.desfecho for i in sexta])
    else:
        print("(sem sexta-feira suficiente na amostra)")

    print(f"\n--- semana isolada, por DIRECAO (n >= 30) ---")
    for lado in (1, -1):
        sub = [i for i in com_semana if i.dir_semana == lado]
        if len(sub) < 30:
            continue
        acc = 100 * sum(1 for i in sub if i.desfecho == lado) / len(sub)
        rotulo = "maioria ALTA -> compra" if lado == 1 else "maioria QUEDA -> venda"
        print(f"  {rotulo:<24} n={len(sub):>6,}  acerto={num_br(acc, 1)}%")

    print("\n--- SEMANA a SEMANA (so' padrao de semana maduro) -- a dispersao real ---")
    chave_por_sessao: dict[object, tuple[int, int]] = {}
    for d in set(i.sessao for i in com_semana):
        iso = d.isocalendar()
        chave_por_sessao[d] = (iso[0], iso[1])
    por_semana: dict[tuple[int, int], list[InstanteSemana]] = {}
    for inst in com_semana:
        por_semana.setdefault(chave_por_sessao[inst.sessao], []).append(inst)

    linhas = []
    for chave, sub in sorted(por_semana.items()):
        acc = 100 * sum(1 for i in sub if i.dir_semana == i.desfecho) / len(sub)
        linhas.append((chave, len(sub), acc))
    print(f"{'semana ISO':>12} {'n':>7} {'acerto':>8}")
    print("-" * 32)
    for chave, n, acc in linhas:
        print(f"{str(chave):>12} {n:>7,} {num_br(acc, 1) + '%':>8}")
    valores = [a for _, _, a in linhas]
    if valores:
        v = sorted(valores)
        print(f"\nmediana {num_br(v[len(v) // 2], 1)}%  |  "
              f"pior {num_br(min(v), 1)}%  |  melhor {num_br(max(v), 1)}%")
    print(f"\n{len(linhas)} semanas independentes. Nenhum p-valor da tabela de cima")
    print("conserta uma amostra deste tamanho -- esta e' a que decide.")


if __name__ == "__main__":
    main()
