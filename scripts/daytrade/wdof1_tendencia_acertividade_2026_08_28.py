"""A tendencia anterior AUMENTA A ACERTIVIDADE? (pergunta do dono,
2026-08-28) -- pregao de hoje, WDOU26.

## Por que este arquivo existe separado do de P&L

A primeira rodada mediu R$. Foi o instrumento errado, e o dono corrigiu:
"aqui nao estamos medindo valores, estamos medindo acertividade, decidir
entrar ou nao entrar, pra cima ou pra baixo".

Ele esta certo, e o motivo e' aritmetico. Com alvo de 1 tick e stop de 4,
cada perda apaga ~4 ganhos: o liquido do dia inteiro e' quase inteiramente
uma funcao de QUANTAS PERDAS caem. A baseline de hoje fez 48 trades com
2 perdas. Medir "o filtro melhorou?" em cima de 2 eventos e' ler ruido --
e, pior, um filtro que so' reduz atividade parece bom em R$ sem acertar
nada (foi o que a rodada de P&L mostrou: bloquear na mesma taxa POR
SORTEIO alcancava o mesmo numero, e exigir a tendencia CONTRA o lado
rendia igual ou mais).

Acertividade nao tem esse problema: ela nao melhora por operar menos.

## O instrumento

Em vez de julgar pelos poucos trades que o robo fez, o pregao inteiro
vira amostra. A cada fechamento de MINUTO, e para CADA lado, pergunta-se
uma coisa so' e binaria:

    entrando AGORA neste lado, com alvo de 1 tick e stop de 4 ticks,
    o que o preco toca primeiro daqui pra frente?

    toca o alvo  -> ACERTOU
    toca o stop  -> ERROU
    nao toca nem um nem outro ate o fim do pregao -> descartado

E' exatamente a geometria de producao (T1/S4), aplicada a todo instante em
vez de so' aos instantes em que o robo por acaso tinha ordem armada. Da'
~500 decisoes por lado no dia em vez de 48 -- amostra suficiente para uma
TAXA fazer sentido, que era o gargalo.

Depois: a taxa de acerto conditional a leitura de tendencia FEITA ANTES da
decisao. Se a tendencia informa, a taxa sobe quando ela concorda com o
lado e cai quando discorda. Se nao informa, a taxa fica na base.

## As duas leituras comparadas

    MEDIA   -- media ponderada do ER das 4 janelas (abertura, ult_50,
               ult_25, ult_10), virada em percentual por lado. Foi a
               primeira tentativa, minha.
    ACORDO  -- percentual do PESO cujas janelas apontam PARA o lado.
               Achado do dono: as 11:58:59, quando a conta vendeu, a MEDIA
               dava 49,0% (empate, "sem tendencia") porque +0,153 da
               abertura cancelava -0,211 dos ultimos 10%. Mas 3 das 4
               janelas apontavam para CIMA: o acordo com o lado vendido
               era 25%. A media destruia a informacao que o acordo
               preserva.

## O nulo, e por que nao e' permutacao simples

Amostras de minutos vizinhos sao fortemente correlacionadas (o preco nao
se reinventa a cada minuto, e as janelas se sobrepoem). Embaralhar o
indicador quebraria essa correlacao e produziria um nulo estreito demais,
que faria qualquer coisa parecer significativa.

O nulo aqui e' **deslocamento circular**: o vetor do indicador e' girado
por um deslocamento aleatorio contra o vetor de desfechos. Isso preserva
a autocorrelacao dos DOIS lados e destroi apenas o alinhamento temporal
entre eles -- que e' exatamente a hipotese sob teste. Repetido
`N_DESLOCAMENTOS` vezes, da' a faixa de separacao que o acaso produz
sozinho neste mesmo dia.

## Limite

A entrada hipotetica e' AO PRECO CORRENTE, nao na ordem-limite parada 1
tick fora que o robo de verdade usa. E' simplificacao deliberada -- a
pergunta aqui e' "este lado, agora, esta certo?", nao "quanto rende a
mecanica" -- mas ela nao e' neutra: a ordem real so' preenche quando o
preco VEM ate ela, ou seja, sempre num extremo local, e a distribuicao
condicional de um extremo local nao e' a de um instante qualquer. Se um
dia a separacao sair de dentro do acaso, refazer com toque de nivel antes
de acreditar.

UM pregao. A taxa de acerto tem amostra suficiente (~1.100 decisoes), mas
todas vem do MESMO dia, com o MESMO regime -- hoje o WDO abriu em 5.164 e
bateu 5.232,5, um dia de alta. Um filtro que diga "nao venda" acerta hoje
por construcao. O nulo por deslocamento circular controla o acaso DENTRO
do dia; ele nao controla o dia. Generalizar exige rodar a mesma medicao em
muitos pregoes, e isso e' outra rodada.

Uso: `python -u scripts/daytrade/wdof1_tendencia_acertividade_2026_08_28.py`
"""
from __future__ import annotations

import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.profiles import profile_for  # noqa: E402
from backtest.intraday.report import num_br  # noqa: E402
from wdof1_tendencia_confirmacao_2026_08_28 import (  # noqa: E402
    DIA,
    JANELAS,
    PESOS,
    SYMBOL,
    SYMBOL_REAL,
    TendenciaDaSessao,
    carregar_barras_de_hoje,
)

PROFIT_TICKS = 1        # geometria de PRODUCAO de hoje
STOP_TICKS = 4
N_DESLOCAMENTOS = 400   # nulo por deslocamento circular
SEMENTE = 20260828


@dataclass
class Decisao:
    """Uma decisao hipotetica: entrar neste lado, neste instante."""

    i_tick: int
    ts: pd.Timestamp
    lado: str
    preco: float
    acertou: bool
    ind_media: float
    ind_acordo: float
    n_janelas: int


# ---------------------------------------------------------------------------
# 1. desfecho de uma entrada hipotetica -- alvo 1 tick x stop 4 ticks
# ---------------------------------------------------------------------------

def desfecho(precos: np.ndarray, i: int, lado: str, preco: float,
             tick: float) -> bool | None:
    """`True` se o ALVO e' tocado antes do STOP daqui pra frente, `False` se
    o stop vem primeiro, `None` se nenhum dos dois e' tocado ate o fim da
    serie (decisao nao resolvida -- descartada, nunca contada como acerto).

    Varredura para a FRENTE a partir de `i+1`: nao ha look-ahead nenhum
    aqui, e' a definicao do desfecho, nao insumo de decisao. A decisao usa
    so' o que existia ate `i` (ver `TendenciaDaSessao`)."""
    if lado == "long":
        alvo, stop = preco + PROFIT_TICKS * tick, preco - STOP_TICKS * tick
        for j in range(i + 1, len(precos)):
            p = precos[j]
            if p >= alvo:
                return True
            if p <= stop:
                return False
    else:
        alvo, stop = preco - PROFIT_TICKS * tick, preco + STOP_TICKS * tick
        for j in range(i + 1, len(precos)):
            p = precos[j]
            if p <= alvo:
                return True
            if p >= stop:
                return False
    return None


# ---------------------------------------------------------------------------
# 2. montar a amostra: uma decisao por lado a cada fechamento de minuto
# ---------------------------------------------------------------------------

def montar_amostra(bars: pd.DataFrame, pesos: dict[str, float]) -> list[Decisao]:
    precos = bars["close"].to_numpy(dtype=float)
    tempos = bars.index
    tick = profile_for(SYMBOL).price_tick_size

    # indice do ULTIMO tick de cada minuto -- o instante em que a leitura de
    # tendencia acabou de ganhar um minuto fechado.
    minutos = tempos.floor("min")
    ultimo_do_minuto = {}
    for i, m in enumerate(minutos):
        ultimo_do_minuto[m] = i
    marcos = sorted(ultimo_do_minuto.values())

    tend = TendenciaDaSessao()
    amostra: list[Decisao] = []
    proximo = 0
    for i in range(len(precos)):
        tend.observa(tempos[i], float(precos[i]))
        if proximo < len(marcos) and i == marcos[proximo]:
            proximo += 1
            leitura = tend.leitura(tempos[i], pesos)
            if not leitura.por_janela:
                continue                    # cedo demais: nenhuma janela definida
            for lado in ("long", "short"):
                ok = desfecho(precos, i, lado, float(precos[i]), tick)
                if ok is None:
                    continue                # nao resolvida ate o fim do pregao
                amostra.append(Decisao(
                    i_tick=i, ts=tempos[i], lado=lado, preco=float(precos[i]),
                    acertou=ok,
                    ind_media=leitura.indicacao(lado),
                    ind_acordo=leitura.acordo(lado),
                    n_janelas=len(leitura.por_janela),
                ))
    return amostra


# ---------------------------------------------------------------------------
# 3. taxa de acerto por faixa do indicador
# ---------------------------------------------------------------------------

FAIXAS = ((0, 25), (25, 50), (50, 50), (50, 75), (75, 100))


def _com_sinal(valor: float, casas: int = 2) -> str:
    """`num_br` devolve texto, entao `:+` do format nao funciona nele."""
    return ("+" if valor >= 0 else "-") + num_br(abs(valor), casas)


def _rotulo(lo: int, hi: int) -> str:
    if lo == hi:
        return f"= {lo}%"
    return f"{lo}-{hi}%"


def _na_faixa(valor: float, lo: int, hi: int) -> bool:
    if lo == hi:
        return abs(valor - lo) < 1e-9
    if lo == 0:
        return valor < hi
    if hi == 100:
        return valor > lo
    return lo < valor < hi


def tabela_por_faixa(amostra: list[Decisao], campo: str, titulo: str) -> None:
    print(f"\n--- {titulo} ---")
    base = 100.0 * sum(1 for d in amostra if d.acertou) / len(amostra)
    print(f"taxa de acerto SEM filtro (todas as {len(amostra):,} decisoes): "
          f"{num_br(base, 2)}%")
    cab = f"{'faixa':>12} {'decisoes':>10} {'acertos':>9} {'taxa':>8} {'vs base':>9}"
    print(cab)
    print("-" * len(cab))
    for lo, hi in FAIXAS:
        sub = [d for d in amostra if _na_faixa(getattr(d, campo), lo, hi)]
        if not sub:
            print(f"{_rotulo(lo, hi):>12} {'0':>10} {'-':>9} {'-':>8} {'-':>9}")
            continue
        acertos = sum(1 for d in sub if d.acertou)
        taxa = 100.0 * acertos / len(sub)
        print(f"{_rotulo(lo, hi):>12} {len(sub):>10,} {acertos:>9,} "
              f"{num_br(taxa, 2) + '%':>8} {_com_sinal(taxa - base):>9}")


def separacao(amostra: list[Decisao], valores: np.ndarray) -> float:
    """Estatistica sob teste: quanto a taxa de acerto ACIMA de 50% supera a
    taxa ABAixo de 50%, em pontos percentuais. Positivo = o indicador
    aponta para o lado certo."""
    acertos = np.array([d.acertou for d in amostra], dtype=bool)
    alto, baixo = valores > 50.0, valores < 50.0
    if not alto.any() or not baixo.any():
        return 0.0
    return 100.0 * (acertos[alto].mean() - acertos[baixo].mean())


def nulo_deslocamento(amostra: list[Decisao], campo: str) -> tuple[float, list[float]]:
    """Faixa de separacao que o ACASO produz neste mesmo dia, girando o
    indicador contra os desfechos (preserva a autocorrelacao dos dois)."""
    valores = np.array([getattr(d, campo) for d in amostra], dtype=float)
    real = separacao(amostra, valores)
    rng = random.Random(SEMENTE)
    n = len(valores)
    nulos = []
    for _ in range(N_DESLOCAMENTOS):
        k = rng.randrange(1, n)
        nulos.append(separacao(amostra, np.roll(valores, k)))
    return real, sorted(nulos)


def veredito(real: float, nulos: list[float]) -> str:
    acima = sum(1 for x in nulos if x >= real)
    p = (acima + 1) / (len(nulos) + 1)
    p05, p95 = nulos[int(0.05 * len(nulos))], nulos[int(0.95 * len(nulos))]
    marca = "ACIMA do acaso" if p <= 0.05 else "dentro do acaso"
    return (f"separacao {_com_sinal(real):>7} pp   |   acaso: mediana "
            f"{_com_sinal(statistics.median(nulos)):>6}, faixa 5-95% "
            f"[{_com_sinal(p05):>6} , {_com_sinal(p95):>6}]   |   p={num_br(p, 3)}  "
            f"-> {marca}")


# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 96)
    print("A tendencia anterior AUMENTA A ACERTIVIDADE? -- WDOU26, 2026-08-28")
    print("=" * 96)
    print("Pergunta medida: entrando AGORA neste lado, com alvo 1 tick e stop 4,")
    print("o preco toca o alvo antes do stop? (a geometria T1/S4 de producao)")
    print("Uma decisao por LADO a cada fechamento de minuto -- o pregao inteiro")
    print("vira amostra, em vez dos 48 trades que o robo por acaso fez.")

    bars = carregar_barras_de_hoje()
    brt = bars.index.tz_convert("America/Sao_Paulo")
    print(f"\ndado: {len(bars):,} negocios de {SYMBOL_REAL}, "
          f"{brt.min():%H:%M:%S} -> {brt.max():%H:%M:%S} (Brasilia)")
    print(f"preco: abertura {num_br(float(bars['close'].iloc[0]), 1)} -> "
          f"maximo {num_br(float(bars['high'].max()), 1)} -> "
          f"ultimo {num_br(float(bars['close'].iloc[-1]), 1)}  "
          "(dia de ALTA -- ver o limite no cabecalho do arquivo)")

    for nome_peso, pesos in PESOS.items():
        print("\n" + "=" * 96)
        print(f"PESOS '{nome_peso}'")
        print("=" * 96)
        amostra = montar_amostra(bars, pesos)
        longs = [d for d in amostra if d.lado == "long"]
        shorts = [d for d in amostra if d.lado == "short"]
        print(f"amostra: {len(amostra):,} decisoes resolvidas "
              f"({len(longs):,} long, {len(shorts):,} short)")
        if longs and shorts:
            print(f"taxa base por lado: long "
                  f"{num_br(100 * sum(d.acertou for d in longs) / len(longs), 2)}%  |  "
                  f"short {num_br(100 * sum(d.acertou for d in shorts) / len(shorts), 2)}%")

        tabela_por_faixa(amostra, "ind_media", "leitura MEDIA (a minha)")
        real, nulos = nulo_deslocamento(amostra, "ind_media")
        print(veredito(real, nulos))

        tabela_por_faixa(amostra, "ind_acordo", "leitura ACORDO (a do dono)")
        real, nulos = nulo_deslocamento(amostra, "ind_acordo")
        print(veredito(real, nulos))

    print("\n" + "=" * 96)
    print("Leia a coluna 'vs base': e' quanto o filtro adiciona a taxa de acerto.")
    print("'dentro do acaso' significa que girar o indicador no tempo produz a")
    print("mesma separacao -- ou seja, ele nao esta prevendo, esta coincidindo.")
    print("UM pregao, de ALTA. O nulo controla o acaso dentro do dia, nao o dia.")


if __name__ == "__main__":
    main()
