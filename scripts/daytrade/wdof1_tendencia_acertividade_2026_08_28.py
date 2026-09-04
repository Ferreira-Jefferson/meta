"""A tendencia anterior AUMENTA A ACERTIVIDADE? (pergunta do dono,
2026-08-28) -- pregao daquele dia, contrato WDO em `SYMBOL_REAL` (importado
de `wdof1_tendencia_confirmacao_2026_08_28.py`).

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

## O instrumento -- e as duas correcoes do dono

A PRIMEIRA versao deste arquivo amostrava a cada fechamento de minuto,
para os dois lados, entrando ao preco corrente. Estava errado por dois
motivos, os dois apontados pelo dono:

1. **Amostras SOBREPOSTAS.** A decisao das 10:00 podia so' resolver as
   10:07, e nesse meio-tempo ja havia decisao das 10:01, 10:02, ... todas
   correndo pelo MESMO pedaco de futuro. Um unico movimento decidia
   dezenas de "decisoes" de uma vez. Nao eram 1.105 observacoes: era um
   punhado de eventos contados muitas vezes, com n inflado e desfechos
   amarrados uns aos outros ("acumula a incerteza do mercado").
2. **O desfecho contaminava a proxima decisao.** Se alvo e stop definem o
   resultado, as barras ATE um deles ser acionado nao podem servir de
   ponto de partida para outra medicao -- um interfere no outro.

Correcao: amostragem **SEQUENCIAL e sem sobreposicao**. Uma decisao por
vez; so' se decide de novo na barra seguinte a' que acionou alvo ou stop.
E' tambem o que a realidade impoe -- o robo so' tem uma posicao por vez.

E, ja que virou sequencial, vale ser fiel a' MECANICA inteira em vez de
entrar a mercado. Cada ciclo:

    1. ancora = preco corrente; arma limite a 1 tick da ancora
    2. espera o TOQUE do nivel (a ordem e' maker: so' entra se o preco vier)
    3. do toque em diante, corre alvo (+1 tick) contra stop (-4 ticks)
    4. resolvido -> ACERTOU (alvo) ou ERROU (stop); proximo ciclo comeca na
       barra seguinte

A leitura de tendencia e' tirada no passo 1 -- o instante em que a decisao
"entrar deste lado" e' de fato tomada. Um ciclo que nao resolve ate o fim
do pregao e' descartado, nunca contado como acerto.

Um lado por sequencia (uma serie so' de long, outra so' de short): lados
diferentes resolvem em tempos diferentes, e mistura-los numa unica linha
do tempo reintroduziria a sobreposicao que esta versao existe para tirar.

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
    PESOS,
    SYMBOL,
    SYMBOL_REAL,
    TendenciaDaSessao,
    carregar_barras_de_hoje,
    montar_config,
)

PROFIT_TICKS = 1        # geometria de PRODUCAO de hoje
STOP_TICKS = 4
N_DESLOCAMENTOS = 400   # nulo por deslocamento circular
SEMENTE = 20260828


@dataclass
class Decisao:
    """Um ciclo completo: armou deste lado, entrou no toque, resolveu."""

    i_decisao: int
    ts: pd.Timestamp
    lado: str
    nivel: float
    i_entrada: int
    i_saida: int
    acertou: bool
    ind_media: float
    ind_acordo: float
    n_janelas: int

    @property
    def barras_esperando(self) -> int:
        return self.i_entrada - self.i_decisao

    @property
    def barras_na_posicao(self) -> int:
        return self.i_saida - self.i_entrada


# ---------------------------------------------------------------------------
# 1. um ciclo da mecanica: arma -> toque -> alvo x stop
# ---------------------------------------------------------------------------

def sufixos(precos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(minimo, maximo)` do preco de cada indice ate o FIM da serie.

    Existe por causa de um bug que quase virou resultado: sem esta
    checagem, uma ancora na MINIMA do dia gera um nivel de compra que
    nunca mais e' tocado, e a varredura ingenua percorre o resto do pregao
    inteiro para descobrir isso -- a cada tentativa. Com o sufixo a
    pergunta "esse nivel ainda e' alcancavel?" custa O(1)."""
    return (np.minimum.accumulate(precos[::-1])[::-1],
            np.maximum.accumulate(precos[::-1])[::-1])


def ciclo(precos: np.ndarray, i: int, lado: str, tick: float,
          suf_min: np.ndarray, suf_max: np.ndarray
          ) -> tuple[bool, int, int, float] | None:
    """Do instante `i` ate a resolucao. Devolve
    `(acertou, i_entrada, i_saida, nivel)`, ou `None` quando este ciclo NAO
    ACONTECE -- o nivel nunca e' tocado, ou o trade nao resolve ate o fim
    do pregao.

    `None` significa "esta tentativa nao virou trade", NAO "acabou o
    pregao": quem chama segue para a proxima barra. Confundir os dois foi
    exatamente o bug de 2026-08-28 -- a serie de long morria as 09:02,
    quando a ancora caiu na minima do dia e o nivel de compra (1 tick
    abaixo) nunca mais foi tocado, e o resultado saia com 4 longs contra
    227 shorts.

    Fiel a' mecanica de producao: o nivel fica a 1 tick da ancora e e'
    MAKER (so' entra se o preco vier ate ele); dali corre alvo de
    `PROFIT_TICKS` contra stop de `STOP_TICKS`. A varredura para a frente
    e' a definicao do DESFECHO, nunca insumo de decisao -- a decisao usou
    so' o que existia ate `i`."""
    n = len(precos)
    if i + 1 >= n:
        return None
    ancora = precos[i]
    if lado == "long":
        nivel = ancora - tick
        alvo, stop = nivel + PROFIT_TICKS * tick, nivel - STOP_TICKS * tick
        if suf_min[i + 1] > nivel:
            return None                     # nivel inalcancavel: nao ha trade
    else:
        nivel = ancora + tick
        alvo, stop = nivel - PROFIT_TICKS * tick, nivel + STOP_TICKS * tick
        if suf_max[i + 1] < nivel:
            return None

    resto = precos[i + 1:]
    toque = (resto <= nivel) if lado == "long" else (resto >= nivel)
    entrada = i + 1 + int(np.argmax(toque))

    if entrada + 1 >= n:
        return None
    depois = precos[entrada + 1:]
    if lado == "long":
        bate_alvo, bate_stop = depois >= alvo, depois <= stop
    else:
        bate_alvo, bate_stop = depois <= alvo, depois >= stop
    tem_alvo, tem_stop = bool(bate_alvo.any()), bool(bate_stop.any())
    if not tem_alvo and not tem_stop:
        return None                         # nao resolve ate o fim do pregao
    j_alvo = int(np.argmax(bate_alvo)) if tem_alvo else n
    j_stop = int(np.argmax(bate_stop)) if tem_stop else n
    acertou = j_alvo <= j_stop
    return acertou, entrada, entrada + 1 + min(j_alvo, j_stop), nivel


# ---------------------------------------------------------------------------
# 2. amostra SEQUENCIAL, sem sobreposicao -- um lado por sequencia
# ---------------------------------------------------------------------------

def montar_amostra(bars: pd.DataFrame, pesos: dict[str, float]) -> list[Decisao]:
    """Percorre o pregao uma vez por lado. Depois de cada resolucao, a
    proxima decisao so' pode nascer na barra SEGUINTE -- nenhum par de
    ciclos divide o mesmo pedaco de futuro (correcao do dono)."""
    precos = bars["close"].to_numpy(dtype=float)
    tempos = bars.index
    tick = profile_for(SYMBOL).price_tick_size
    suf_min, suf_max = sufixos(precos)

    amostra: list[Decisao] = []
    for lado in ("long", "short"):
        tend = TendenciaDaSessao()
        liberado_em = 0
        for i in range(len(precos)):
            tend.observa(tempos[i], float(precos[i]))
            if i < liberado_em:
                continue
            leitura = tend.leitura(tempos[i], pesos)
            if not leitura.por_janela:
                continue                    # cedo demais: nenhuma janela definida
            saida = ciclo(precos, i, lado, tick, suf_min, suf_max)
            if saida is None:
                continue                    # nao virou trade -- proxima barra
            acertou, i_ent, i_sai, nivel = saida
            amostra.append(Decisao(
                i_decisao=i, ts=tempos[i], lado=lado, nivel=nivel,
                i_entrada=i_ent, i_saida=i_sai, acertou=acertou,
                ind_media=leitura.indicacao(lado),
                ind_acordo=leitura.acordo(lado),
                n_janelas=len(leitura.por_janela),
            ))
            liberado_em = i_sai + 1         # so' volta a contar DEPOIS da saida
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
    print(f"A tendencia anterior AUMENTA A ACERTIVIDADE? -- {SYMBOL_REAL}, 2026-08-28")
    print("=" * 96)
    print("Ciclo medido, fiel a' mecanica: arma a limite 1 tick da ancora ->")
    print("espera o TOQUE -> corre alvo (+1 tick) contra stop (-4 ticks).")
    print("ACERTOU = alvo antes do stop. ERROU = stop antes do alvo -- o stop")
    print("ESTA contado; nao ha terceira categoria alem de 'nao resolveu'.")
    print("Amostragem SEQUENCIAL: a proxima decisao so' nasce na barra seguinte")
    print("a' saida, entao nenhum par de ciclos divide o mesmo futuro.")

    custos = montar_config().costs
    ganho = PROFIT_TICKS * custos.tick_size * custos.point_value_brl
    perda = (STOP_TICKS + custos.slippage_ticks) * custos.tick_size * custos.point_value_brl
    taxa = custos.fee_round_trip_brl
    breakeven = 100.0 * (perda + taxa) / (ganho + perda)
    print(f"\ngeometria: acerto +R$ {num_br(ganho)} | erro -R$ {num_br(perda)} "
          f"(inclui {num_br(custos.slippage_ticks, 1)} tick de deslize no stop) "
          f"| tarifa R$ {num_br(taxa)}")
    print(f"BREAKEVEN desta geometria: {num_br(breakeven, 2)}% de acerto. "
          "Abaixo disso a taxa alta nao salva.")

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
        erros = sum(1 for d in amostra if not d.acertou)
        print(f"amostra: {len(amostra):,} ciclos SEM sobreposicao "
              f"({len(longs):,} long, {len(shorts):,} short) -- "
              f"{len(amostra) - erros:,} acertos, {erros:,} stops")
        if longs and shorts:
            print(f"taxa base por lado: long "
                  f"{num_br(100 * sum(d.acertou for d in longs) / len(longs), 2)}%  |  "
                  f"short {num_br(100 * sum(d.acertou for d in shorts) / len(shorts), 2)}%")
            espera = statistics.median(d.barras_esperando for d in amostra)
            dentro = statistics.median(d.barras_na_posicao for d in amostra)
            print(f"mediana: {num_br(espera, 0)} negocios esperando o toque, "
                  f"{num_br(dentro, 0)} negocios em posicao")

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
