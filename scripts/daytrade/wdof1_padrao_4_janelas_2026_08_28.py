"""O PADRAO das 4 janelas de tendencia -- desenho do dono, 2026-08-28.

## O que muda em relacao a `wdof1_tendencia_acertividade_2026_08_28.py`

As JANELAS sao as mesmas (100%, 50%, 25% e 10% do tempo decorrido do
pregao, todas terminando AGORA). Tudo o mais muda, e a mudanca e' o
conserto de um erro meu:

    eu fazia                          o dono descreve
    -----------------------------     ------------------------------
    cada janela vira um numero        cada janela vira so' ALTA ou
    de -1 a +1 (a "forca")            QUEDA (so' o sinal)
    junto as 4 pela MEDIA             olho o PADRAO dos 4 sinais
    3 contra 1 vira ~50% e some       3 contra 1 opera, marcado a' parte
    qual janela discorda: ignorado    qual discorda IMPORTA
    nao opera: abaixo do limiar       nao opera: empate 2 a 2

Tirar media de quatro sinais joga fora exatamente a informacao procurada:
QUAL combinacao apareceu. Sao 2^4 = 16 combinacoes, e a pergunta e' se
alguma delas acerta mais que as outras. A media colapsava as 16 num
numero so'.

Exemplos do proprio dono, com A=alta e Q=queda na ordem t1 t2 t3 t4:

    A A A A  -> compra              (as 4 concordam)
    Q Q Q Q  -> vende               (as 4 concordam)
    A A Q Q  -> NAO OPERA           (empate 2 a 2)
    Q A Q Q  -> vende, marcado      (3 a 1)
    A A A Q  -> compra, marcado     (so' a mais RECENTE discorda)
    Q A A A  -> compra, marcado     (so' a mais ANTIGA discorda)

As duas ultimas tem a mesma contagem (3 a 1) e sao situacoes diferentes:
numa a divergencia esta no curto prazo, na outra no longo. Por isso o
relatorio mostra as 16 linhas separadas, nunca so' "3 a 1".

## Regra de admissao

"Se eu ainda nao conseguir ter os tempos, eu nao opero" -- no comeco do
pregao as janelas curtas nao existem (10% de 10 minutos e' 1 minuto).
Aqui: toda janela precisa de pelo menos `MIN_BARRAS_JANELA` barras
fechadas, senao o instante inteiro e' descartado.

## O desfecho, e por que aqui a sobreposicao NAO atrapalha

O arquivo anterior media "o trade ganhou ou perdeu", que dura um tempo
VARIAVEL -- por isso decisoes vizinhas se embolavam e a amostragem tinha
de ser sequencial.

Aqui o desfecho e' outro e tem prazo FIXO: **para onde o preco foi nos
proximos H minutos**. Com prazo fixo da' para medir barra a barra, como o
dono disse. As amostras continuam correlacionadas (janelas vizinhas se
sobrepoem), o que proibe tratar cada minuto como independente na hora do
p -- e e' exatamente por isso que o nulo e' por DESLOCAMENTO CIRCULAR:
gira o padrao contra os desfechos, preservando a autocorrelacao dos dois
e destruindo so' o alinhamento.

ACERTOU = o lado que o padrao mandaria tomar bate com o sinal do
movimento nos H minutos seguintes. Movimento exatamente zero e'
descartado (nao e' acerto nem erro).

Uso: `python -u scripts/daytrade/wdof1_padrao_4_janelas_2026_08_28.py`
"""
from __future__ import annotations

import random
import statistics
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
from wdof1_tendencia_confirmacao_2026_08_28 import (  # noqa: E402
    SYMBOL_REAL,
    carregar_barras_de_hoje,
)

#: Fracao do tempo DECORRIDO coberta por cada janela, na ordem t1..t4.
FRACOES = (1.00, 0.50, 0.25, 0.10)
NOMES = ("t1 abertura", "t2 ult-50%", "t3 ult-25%", "t4 ult-10%")

#: Barras fechadas minimas para uma janela existir. Abaixo disso o
#: instante inteiro e' descartado ("nao consigo ter os tempos, nao opero").
MIN_BARRAS_JANELA = 3

#: Horizontes do desfecho, em barras do timeframe usado.
HORIZONTES = (1, 5, 15, 30)

N_DESLOCAMENTOS = 400
SEMENTE = 20260828


@dataclass
class Instante:
    i: int
    ts: pd.Timestamp
    padrao: str                 # 4 letras, A ou Q, na ordem t1..t4
    lado: str | None            # "long", "short" ou None (empate 2 a 2)
    desfecho: dict[int, int]    # horizonte -> +1 subiu, -1 caiu, 0 parado


# ---------------------------------------------------------------------------
# 1. o padrao das 4 janelas num instante
# ---------------------------------------------------------------------------

def padrao_em(fechamentos: np.ndarray, tempos: pd.DatetimeIndex, i: int) -> str | None:
    """As 4 letras no instante `i`, ou `None` se alguma janela nao tiver
    barras suficientes. Cada letra e' so' o SINAL do deslocamento da
    janela: onde o preco esta agora contra onde estava no inicio dela."""
    decorrido = tempos[i] - tempos[0]
    letras = []
    for fracao in FRACOES:
        inicio = tempos[i] - decorrido * fracao
        # `tempos.searchsorted`, nao `np.searchsorted(tempos.asi8, ...)`:
        # `asi8` devolve o inteiro na unidade DO INDICE (ms, quando ele vem
        # de `time_msc`) e `Timestamp.value` e' sempre ns -- mil vezes
        # maior. A comparacao nao levanta erro, so' devolve o fim do array
        # sempre, e o teste inteiro sai com zero instantes.
        j = int(tempos.searchsorted(inicio, side="left"))
        if i - j < MIN_BARRAS_JANELA:
            return None
        delta = fechamentos[i] - fechamentos[j]
        if delta == 0:
            return None            # janela sem direcao: instante descartado
        letras.append("A" if delta > 0 else "Q")
    return "".join(letras)


def lado_do_padrao(padrao: str) -> str | None:
    """Regra do dono: maioria manda; empate 2 a 2 nao opera."""
    altas = padrao.count("A")
    if altas == 2:
        return None
    return "long" if altas > 2 else "short"


def rotulo_do_padrao(padrao: str) -> str:
    """Texto curto que diz QUE tipo de entrada e' -- e' o que separa
    'A A A Q' de 'Q A A A', que a contagem sozinha nao separa."""
    altas = padrao.count("A")
    if altas == 2:
        return "empate — nao opera"
    if altas in (0, 4):
        return "as 4 concordam"
    discordante = padrao.index("Q") if altas == 3 else padrao.index("A")
    return f"3 a 1 — discorda {NOMES[discordante].split()[0]}"


# ---------------------------------------------------------------------------
# 2. varrer o pregao inteiro, barra a barra
# ---------------------------------------------------------------------------

def montar(bars_tf: pd.DataFrame) -> list[Instante]:
    fechamentos = bars_tf["close"].to_numpy(dtype=float)
    tempos = bars_tf.index
    n = len(fechamentos)
    instantes: list[Instante] = []
    for i in range(n):
        padrao = padrao_em(fechamentos, tempos, i)
        if padrao is None:
            continue
        desfecho = {}
        for h in HORIZONTES:
            if i + h >= n:
                continue
            d = fechamentos[i + h] - fechamentos[i]
            desfecho[h] = 0 if d == 0 else (1 if d > 0 else -1)
        if not desfecho:
            continue
        instantes.append(Instante(i=i, ts=tempos[i], padrao=padrao,
                                  lado=lado_do_padrao(padrao), desfecho=desfecho))
    return instantes


def acertou(inst: Instante, h: int) -> bool | None:
    """`None` quando nao ha aposta (empate) ou o preco nao andou."""
    if inst.lado is None or h not in inst.desfecho or inst.desfecho[h] == 0:
        return None
    quer = 1 if inst.lado == "long" else -1
    return inst.desfecho[h] == quer


# ---------------------------------------------------------------------------
# 3. tabelas
# ---------------------------------------------------------------------------

def tabela_por_padrao(instantes: list[Instante], h: int) -> None:
    print(f"\n--- horizonte: {h} barra(s) a frente ---")
    cab = (f"{'padrao':>8} {'t1 t2 t3 t4':>13} {'tipo':>26} {'aposta':>7} "
           f"{'n':>5} {'acerto':>8}")
    print(cab)
    print("-" * len(cab))
    contagem = Counter(i.padrao for i in instantes)
    for padrao in sorted(contagem, key=lambda p: -contagem[p]):
        sub = [i for i in instantes if i.padrao == padrao]
        resolvidos = [a for a in (acertou(i, h) for i in sub) if a is not None]
        lado = lado_do_padrao(padrao)
        aposta = {"long": "compra", "short": "venda", None: "—"}[lado]
        if not resolvidos:
            taxa = "—"
        else:
            taxa = num_br(100 * sum(resolvidos) / len(resolvidos), 1) + "%"
        print(f"{padrao:>8} {' '.join(padrao):>13} {rotulo_do_padrao(padrao):>26} "
              f"{aposta:>7} {len(sub):>5} {taxa:>8}")


def taxa_global(instantes: list[Instante], h: int) -> tuple[float, int]:
    resolvidos = [a for a in (acertou(i, h) for i in instantes) if a is not None]
    if not resolvidos:
        return 0.0, 0
    return 100.0 * sum(resolvidos) / len(resolvidos), len(resolvidos)


def nulo(instantes: list[Instante], h: int) -> tuple[float, list[float]]:
    """Gira o PADRAO contra os desfechos. Preserva a autocorrelacao dos
    dois lados; destroi so' o alinhamento, que e' a hipotese sob teste."""
    lados = np.array([1 if i.lado == "long" else (-1 if i.lado == "short" else 0)
                      for i in instantes])
    movs = np.array([i.desfecho.get(h, 0) for i in instantes])

    def taxa(l: np.ndarray) -> float:
        valido = (l != 0) & (movs != 0)
        if not valido.any():
            return 0.0
        return 100.0 * (l[valido] == movs[valido]).mean()

    real = taxa(lados)
    rng = random.Random(SEMENTE)
    nulos = sorted(taxa(np.roll(lados, rng.randrange(1, len(lados))))
                   for _ in range(N_DESLOCAMENTOS))
    return real, nulos


# ---------------------------------------------------------------------------

def main() -> None:
    ticks = carregar_barras_de_hoje()
    print("=" * 92)
    print(f"PADRAO das 4 janelas -- {SYMBOL_REAL}, 2026-08-28")
    print("=" * 92)
    print("t1 = desde a abertura | t2 = ultimos 50% | t3 = ultimos 25% | t4 = ultimos 10%")
    print("Cada janela vira so' ALTA(A) ou QUEDA(Q). Maioria manda; empate 2 a 2 nao opera.")
    print("Desfecho: para onde o preco foi H barras a frente. Prazo FIXO, entao")
    print("da' para medir barra a barra (o nulo cuida da correlacao entre vizinhas).")

    for rotulo, regra in (("M1", "1min"), ("M5", "5min")):
        bars_tf = ticks.resample(regra).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna()
        instantes = montar(bars_tf)
        opera = [i for i in instantes if i.lado is not None]
        print("\n" + "=" * 92)
        print(f"{rotulo} -- {len(bars_tf)} barras, {len(instantes)} instantes com os "
              f"4 tempos disponiveis, {len(opera)} com aposta "
              f"({len(instantes) - len(opera)} empates 2 a 2)")
        print("=" * 92)

        tabela_por_padrao(instantes, HORIZONTES[1])

        print(f"\n{'horizonte':>10} {'apostas':>9} {'padrao':>8} {'so comprar':>11} "
              f"{'so vender':>10} {'acaso 5-95%':>18} {'p':>7}  veredito")
        print("-" * 100)
        for h in HORIZONTES:
            real, nulos = nulo(opera, h)
            _t, n = taxa_global(opera, h)
            # Baseline que importa de verdade: apostar SEMPRE no mesmo lado.
            # Num dia de alta, "so' comprar" acerta muito sem saber de nada --
            # o padrao tem de bater ISSO, nao os 50% de cara-ou-coroa.
            movs = [i.desfecho.get(h, 0) for i in opera]
            andou = [m for m in movs if m != 0]
            so_compra = 100.0 * sum(1 for m in andou if m > 0) / len(andou) if andou else 0.0
            acima = sum(1 for x in nulos if x >= real)
            p = (acima + 1) / (len(nulos) + 1)
            p05, p95 = nulos[int(0.05 * len(nulos))], nulos[int(0.95 * len(nulos))]
            melhor_fixo = max(so_compra, 100.0 - so_compra)
            print(f"{h:>10} {n:>9,} {num_br(real, 1) + '%':>8} "
                  f"{num_br(so_compra, 1) + '%':>11} {num_br(100 - so_compra, 1) + '%':>10} "
                  f"{'[' + num_br(p05, 1) + ' , ' + num_br(p95, 1) + ']':>18} "
                  f"{num_br(p, 3):>7}  "
                  f"{'ACIMA do acaso' if p <= 0.05 else 'dentro do acaso'}"
                  f"{'' if real > melhor_fixo else '  <- pior que apostar sempre no mesmo lado'}")

    print("\n" + "=" * 92)
    print("UM pregao. 16 padroes possiveis reparte a amostra em pedacos pequenos --")
    print("leia a coluna 'n' antes da coluna 'acerto' em cada linha.")


if __name__ == "__main__":
    main()
