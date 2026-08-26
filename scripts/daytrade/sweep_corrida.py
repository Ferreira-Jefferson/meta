"""Varredura IN-SAMPLE de `CopaWinCorrida` (segue a corrida de barras M1) no
WIN@ -- irma de `sweep_copa.py`, em arquivo PROPRIO porque outro agente esta
editando `sweep_copa.py`/`run_copa_score.py` ao mesmo tempo (nao tocar).

SO' IN-SAMPLE. Nao tem `--unlock-oos` e nunca tera': o trecho out-of-sample
e' rodado UMA vez, depois, com o parametro ja escolhido -- uma varredura que
enxerga o OOS nao esta testando nada, esta escolhendo o parametro que ganha
no proprio gabarito.

Paraleliza por COMBINACAO (`ProcessPoolExecutor` + `submit`/`as_completed`,
nunca `pool.map`): resultado sai assim que fica pronto, nunca so no fim
(regra do dono, ver `AGENTS.md`).

Uso:
    python scripts/daytrade/sweep_corrida.py
    python scripts/daytrade/sweep_corrida.py --teto 12 --top 20
    python scripts/daytrade/sweep_corrida.py --jobs 8
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
import time as time_mod
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import copa_lab as L  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import (  # noqa: E402
    LARGURA_VARIANTE,
    cabecalho,
    linha,
)
from strategy.daytrade.lab.copa_win_corrida import CopaWinCorrida  # noqa: E402

SYMBOL = "WIN@"

# ---------------------------------------------------------------------------
# JANELAS de horario (UTC -- mesma convencao de `IntradayBacktestConfig.
# session_end_time`, comparado direto contra `ts.time()`). O pregao do WIN
# comeca ~12:03 UTC (09:03 Brasilia). "abre3h"/"abre5h" testam a hipotese de
# que a ABERTURA concentra o movimento (medido em `copa_win.py`: range
# diario mediano de 2.968 pts, boa parte dele nas primeiras horas) --
# rotulos em BRASILIA (mais legivel), valores em UTC (o que o motor compara).
# ---------------------------------------------------------------------------
JANELAS: dict[str, tuple[time | None, time | None]] = {
    "full": (None, None),                       # pregao inteiro
    "abre3h": (time(12, 0), time(15, 0)),        # 09:00-12:00 Brasilia
    "abre5h": (time(12, 0), time(17, 0)),        # 09:00-14:00 Brasilia
}

GRADE = {
    "confirmacao_barras": [2, 3, 4, 5],
    "fracao_entrada": [0.25, 0.5, 1.0],
    "stop_pontos": [None, 100.0, 200.0, 400.0],
    "max_entradas_dia": [None, 20, 40],
    "janela": list(JANELAS),
}

#: Abreviacao de cada parametro no rotulo da linha -- uma letra por
#: dimensao, a coluna `variante` da tabela padrao tem largura fixa
#: (`LARGURA_VARIANTE`).
_ABREV = {
    "confirmacao_barras": "k", "fracao_entrada": "f", "stop_pontos": "s",
    "max_entradas_dia": "n", "janela": "h",
}


def _valor(v) -> str:
    """`None` vira "-" (nao "off") -- mesmo motivo de `sweep_copa.py`: um
    rotulo truncado no display faz duas combinacoes DIFERENTES parecerem a
    mesma linha."""
    if v is None:
        return "-"
    if isinstance(v, (int, float)):
        return f"{v:g}"
    return str(v)


def _chaves_variaveis(grade: dict) -> list[str]:
    return [k for k, valores in grade.items() if len(valores) > 1]


def _rotulo(params: dict, chaves: list[str]) -> str:
    """Rotulo curto, ESTAVEL e UNICO -- derivado das chaves que a grade
    VARIA, nunca de uma lista escrita a mao (a versao antiga de
    `sweep_copa.py` teve um bug exatamente aqui: chaves omitidas faziam
    combinacoes diferentes colidirem e o dicionario de resultados
    sobrescrevia em silencio)."""
    return " ".join(f"{_ABREV[k]}{_valor(params[k])}" for k in chaves)


def _combinacoes(grade: dict) -> list[dict]:
    chaves = list(grade)
    return [dict(zip(chaves, valores)) for valores in itertools.product(*(grade[k] for k in chaves))]


# `bars` vive num global do processo filho -- mesmo motivo de `sweep_copa.py`:
# com dezenas de milhares de barras M1, mandar o DataFrame junto de CADA
# tarefa custaria mais em serializacao do que a propria simulacao.
_BARS: dict = {}


def _preparar() -> None:
    _BARS["bars"] = L.barras(SYMBOL).in_sample()


def _rodar(teto: int, rotulo: str, params: dict) -> L.Rodada:
    """Monta `CopaWinCorrida` + a config REALISTA do motor (custo padrao:
    tarifa + slippage de mercado nas duas pernas -- o mesmo que qualquer
    outro robo `copa` roda por default) com o MESMO teto, roda o motor,
    devolve `Rodada` (reusa o relatorio da familia `copa` -- 12 colunas da
    base + extras, ver `backtest/intraday/report.py`).

    `pernas_maker=0`: `CopaWinCorrida` nao tem perna maker nenhuma (entrada
    e saida sao sempre ordem a mercado) -- ver `CopaWinCorrida.pernas_maker`
    e o comentario em `copa_lab.config`."""
    p = dict(params)
    hora_inicio, hora_fim = JANELAS[p.pop("janela")]
    instancia = CopaWinCorrida(
        teto_contratos=teto, symbol=SYMBOL,
        hora_inicio=hora_inicio, hora_fim=hora_fim,
        **p,
    )
    cfg = L.config(SYMBOL, teto, pernas_maker=0)
    resultado = run_intraday_backtest(_BARS["bars"], instancia, cfg)
    return L.Rodada(rotulo=rotulo, resultado=resultado, teto=teto, pedagio_ticks=0.0)


def _medir(teto: int, params: dict, chaves: list[str]) -> tuple[str, dict]:
    rotulo = _rotulo(params, chaves)
    rodada = _rodar(teto, rotulo, params)
    return rotulo, {
        "linha": rodada.linha(),
        "liquido": rodada.liquido_brl,
        "params": params,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--teto", type=int, default=None,
                        help="teto de contratos simultaneos desta varredura "
                             "(default: o teto de TESTE, com folga sobre o oficial de 2025)")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--jobs", type=int, default=None)
    args = parser.parse_args()

    teto = args.teto if args.teto is not None else L.TETO_DE_TESTE[SYMBOL]
    combos = _combinacoes(GRADE)
    chaves = _chaves_variaveis(GRADE)
    rotulos = {_rotulo(p, chaves) for p in combos}
    if len(rotulos) != len(combos):
        raise SystemExit(
            f"[sweep_corrida] {len(combos)} combinacoes produzem so' {len(rotulos)} rotulos "
            "distintos -- o rotulo nao distingue a grade e resultados seriam "
            "sobrescritos em silencio. Ajuste `_ABREV`/`_chaves_variaveis`."
        )
    maior = max(len(r) for r in rotulos)
    if maior > LARGURA_VARIANTE:
        raise SystemExit(
            f"[sweep_corrida] rotulo de {maior} caracteres nao cabe na coluna "
            f"`variante` ({LARGURA_VARIANTE}) -- duas combinacoes diferentes "
            "apareceriam como a MESMA linha na tabela. Encurte `_ABREV`."
        )
    workers = args.jobs or max(1, (os.cpu_count() or 4) - 2)

    ins = L.barras(SYMBOL).in_sample()
    print(f"=== {SYMBOL} — IN-SAMPLE: {L.descreve_janela(ins)} ===", flush=True)
    print(f"[sweep_corrida] teto={teto} contratos, {len(combos)} combinacoes "
          f"em ate {workers} processo(s)", flush=True)

    resultados: dict[str, dict] = {}
    inicio = time_mod.time()
    print()
    print(cabecalho(L.EXTRAS), flush=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=_preparar) as pool:
        # `as_completed`, nunca `pool.map` -- ver `AGENTS.md` ("A suite roda
        # em PARALELO"). `flush=True` em todo print porque stdout
        # redirecionado a arquivo e' bufferizado em bloco.
        futuros = {pool.submit(_medir, teto, p, chaves): p for p in combos}
        melhor_ate_agora = float("-inf")
        for i, futuro in enumerate(as_completed(futuros), start=1):
            rotulo, dados = futuro.result()
            resultados[rotulo] = dados
            marca = ""
            if dados["liquido"] > melhor_ate_agora:
                melhor_ate_agora = dados["liquido"]
                marca = "  <-- melhor ate agora"
            print(linha(dados["linha"], L.EXTRAS) + marca, flush=True)
            if i % 50 == 0 or i == len(combos):
                decorrido = time_mod.time() - inicio
                print(f"[sweep_corrida] {i}/{len(combos)} ({decorrido:.0f}s, "
                      f"{decorrido / i:.1f}s/combinacao, melhor "
                      f"R${melhor_ate_agora:,.0f})", flush=True)

    ordenados = sorted(resultados.values(), key=lambda d: d["liquido"], reverse=True)
    print()
    print(f"--- TOP {args.top} de {len(ordenados)} (teto={teto}) ---")
    print(cabecalho(L.EXTRAS))
    for dados in ordenados[:args.top]:
        print(linha(dados["linha"], L.EXTRAS))
    if len(ordenados) > args.top:
        print(f"  ... {len(ordenados) - args.top} combinacao(oes) fora do top-{args.top}")

    melhor = ordenados[0]
    print()
    print(f"[sweep_corrida] melhor no IS (teto={teto}): {melhor['linha'].variante}")
    print(f"[sweep_corrida] parametros: {melhor['params']}")

    # Reporta tambem o TETO OFICIAL (15) para a MESMA combinacao vencedora --
    # nao re-varre a grade inteira (432 combinacoes x 2 tetos seria o dobro
    # do custo so para uma pergunta de SENSIBILIDADE, nao de escolha de
    # parametro: o teto nunca decide qual combinacao ganha, ver
    # `IntradayBacktestConfig.max_open_contracts`).
    if teto != 15:
        # `_BARS` so' foi populado pelo `initializer` dentro dos processos
        # FILHOS do pool (que ja encerrou) -- o processo PAI (aqui) nunca
        # rodou `_preparar()`. Sem isto, `_rodar` levanta `KeyError: 'bars'`.
        _preparar()
        rotulo_15, dados_15 = _medir(15, melhor["params"], chaves)
        print()
        print(f"[sweep_corrida] mesma combinacao a teto=15 (oficial 2025):")
        print(cabecalho(L.EXTRAS))
        print(linha(dados_15["linha"], L.EXTRAS))

    print()
    print("[sweep_corrida] o IS NAO aprova nada -- confirmar no OOS e' um "
          "tiro so', fora do escopo desta rodada.")


if __name__ == "__main__":
    main()
