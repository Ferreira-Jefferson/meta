"""Varredura IN-SAMPLE da familia `copa` (Copa BTG Trader) — WIN ou WDO, um
ativo por vez.

SO' IN-SAMPLE. Este script nao tem `--unlock-oos` e nunca tera': o trecho
out-of-sample e' rodado UMA vez, depois, com o parametro ja escolhido, por
`run_copa_score.py`. Uma varredura que enxerga o OOS nao esta testando nada --
esta escolhendo o parametro que ganha no proprio gabarito.

Paraleliza por FAIXA DE PARAMETROS dentro do ativo (`ProcessPoolExecutor` +
`submit`/`as_completed`, nunca `pool.map`): as grades dos dois ativos sao
incomparaveis entre si, entao nao ha' o que ganhar rodando os dois juntos, e
uma unica combinacao leva ~15s -- o paralelismo tem de estar DENTRO da grade.

Uso:
    python scripts/daytrade/sweep_copa.py --symbol WIN@
    python scripts/daytrade/sweep_copa.py --symbol WDO@ --teto 4 --top 20
    python scripts/daytrade/sweep_copa.py --symbol WIN@ --grade dirigida --jobs 10
    python scripts/daytrade/sweep_copa.py --symbol WDO@ --grade borda --top 20
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import copa_lab as L  # noqa: E402
from backtest.intraday.report import (  # noqa: E402
    LARGURA_VARIANTE,
    cabecalho,
    linha,
)

# ---------------------------------------------------------------------------
# GRADES. "fina" e' o primeiro passe, barato e amplo em alvo/stop;
# "dirigida" e' o segundo, montado A PARTIR do que o primeiro mostrou; "borda"
# e' o terceiro e existe por DISCIPLINA, nao por ambicao: um otimo que caiu no
# MAIOR (ou no MENOR) valor de uma dimensao nao e' um otimo, e' o ponto onde a
# grade acabou -- reporta-lo como calibracao seria descrever a grade e chamar
# isso de mercado. Ela ESTENDE as dimensoes que ficaram encostadas e mantem as
# outras BRACADAS em torno do vencedor, para que a pergunta "interior ou
# borda?" tenha resposta dimensao por dimensao (o comentario de cada uma
# registra o que foi visto). Toda dimensao aqui e' uma
# HIPOTESE que a medicao vai
# aceitar ou recusar -- nenhuma delas e' premissa (o freio diario, por
# exemplo, entra desligado E ligado, porque "limitar perda diaria ajuda" e'
# exatamente o tipo de crenca que este repo ja viu ser refutada).
# ---------------------------------------------------------------------------

GRADES = {
    "WIN@": {
        "fina": {
            "janela_rompimento": [10, 20, 40, 60],
            "alvo_vol": [1.0, 2.0, 3.0, 5.0],
            "stop_vol": [0.5, 1.0, 2.0],
            "trail_vol": [None, 1.0, 2.0],
            "vol_min_ticks": [1.0],
            "fracao_entrada": [0.5],
            "aquecimento_barras": [15],
            "max_entradas_dia": [10],
        },
        # Montada A PARTIR do 1o passe (grade "fina", 2026-08-25, 144
        # combinacoes): `janela_rompimento=10` e `stop_vol=2` dominaram o
        # topo, e TODAS as combinacoes fecharam o dia com exatamente 10
        # entradas -- ou seja, `max_entradas_dia` estava amarrando e o sinal
        # disparava o tempo todo. Esta grade abre justamente as duas
        # dimensoes de SELETIVIDADE que a primeira manteve fixas
        # (`vol_min_ticks`, `max_entradas_dia`) e alarga alvo/stop na direcao
        # que venceu. Continua 100% in-sample.
        "dirigida": {
            "janela_rompimento": [10, 20, 40],
            "alvo_vol": [2.0, 3.0, 4.0, 6.0],
            "stop_vol": [1.5, 2.0, 3.0],
            "trail_vol": [None, 2.0],
            "vol_min_ticks": [1.0, 8.0],
            "fracao_entrada": [0.5],
            "aquecimento_barras": [15],
            "max_entradas_dia": [4, 10],
            # A dimensao que o diagnostico de custo apontou: com entrada a
            # mercado o spread come praticamente todo o edge bruto (~10,4 de
            # 10,6 pontos por contrato). Entrar por RETESTE nao paga esse tick
            # -- ao preco de perder o rompimento que nunca volta ao nivel.
            "entrada_maker": [False, True],
            "entrada_ttl_barras": [5, 15],
        },
        # 3o passe do WIN, em DUAS perguntas.
        #
        # (1) BORDA. O 2o passe ("dirigida", 2026-08-26, 1152 combinacoes;
        # melhor `j10 a4 s2 t- v8 n10 M1 T15`, +R$36.987 em 129 pregoes) parou
        # com o vencedor encostado em QUATRO dimensoes: `janela_rompimento=10`
        # era o MENOR valor e `vol_min_ticks=8`, `max_entradas_dia=10` e
        # `entrada_ttl_barras=15` os MAIORES. Numero lido de uma borda nao e'
        # um otimo: e' o artefato de onde a grade parou. A extensao rodou
        # (324 combinacoes, 2026-08-26, arquivo `sweep_win_borda_v1_*`) e
        # devolveu as quatro para o INTERIOR, sem mover o vencedor:
        #   janela 5/10/20  -> 33.658 / 36.987 / 27.999 (as duas pontas piores)
        #   vol_min 1/8/16  -> 36.589 / 36.987 / 29.693
        #   entradas 4/10/20-> 10.211 / 36.987 / 29.579
        #   ttl 5/15/30/60  -> 22.860 / 36.987 / <36.987 / <36.987
        # Por isso `alvo_vol=4` (interior em [2,3,4,6]), `stop_vol=2`
        # (interior em [1,5;2;3]) e `vol_min_ticks=8` ficam FIXOS aqui: sao as
        # dimensoes ja resolvidas, e congela-las e' o que paga o orcamento de
        # combinacoes da pergunta (2). `janela_rompimento` e
        # `entrada_ttl_barras` continuam abertas porque foram as bordas de
        # efeito grande.
        #
        # (2) AS TRES DIMENSOES QUE NUNCA FORAM VARRIDAS. `fracao_entrada`,
        # `aquecimento_barras` e o TETO de `max_entradas_dia` estiveram
        # congelados nos passes 1 e 2 -- ou seja, os R$36.987 acima foram
        # medidos com o robo usando METADE do teto (6 de 12 contratos) e com
        # um teto de 10 entradas/dia que o proprio comentario do 1o passe
        # acusou de estar AMARRANDO. Nenhum dos tres numeros foi escolhido por
        # medicao; os tres sao default herdado, que e' a forma mais silenciosa
        # de um resultado ser um artefato de configuracao. `fracao_entrada`
        # dobra a exposicao sem tocar no sinal (e e' onde `max_open_contracts`
        # comeca a MORDER de verdade -- coluna `recusas%`), e
        # `max_entradas_dia` ate 100 remove o teto na pratica.
        #
        # `aquecimento_barras` vai ate 60, e nao ate 30 como no 1o desenho
        # desta grade: com [5,15,30] o vencedor saiu em 30, ou seja, EM CIMA
        # DA BORDA outra vez, e a sonda que estendeu (30/45/60/90/120 no
        # vencedor) mediu 80.651 / 96.353 / 57.610 / 53.186 / 38.171 -- o
        # otimo real e' 45 e so' aparece se a grade chegar la'. Uma calibracao
        # que a propria grade declarada nao reproduz e' um numero sem
        # procedencia, entao o valor entra na grade em vez de ficar so' no
        # relatorio. Continua 100% in-sample.
        "borda": {
            "janela_rompimento": [5, 10, 20],
            "alvo_vol": [4.0],
            "stop_vol": [2.0],
            "trail_vol": [None],
            "vol_min_ticks": [8.0],
            "fracao_entrada": [0.5, 0.75, 1.0],
            "aquecimento_barras": [5, 15, 30, 45, 60],
            "max_entradas_dia": [10, 25, 50, 100],
            "entrada_maker": [True],
            "entrada_ttl_barras": [15, 30, 60],
        },
    },
    "WDO@": {
        "fina": {
            "entrada_ticks": [1.0, 2.0, 4.0],
            "alvo_ticks": [1.0, 2.0, 4.0],
            "stop_ticks": [2.0, 6.0, 12.0],
            "ttl_barras": [5, 15],
            "ancora_fixa_barras": [0, 120],
            "pecas": [1, 2],
            "fracao_entrada": [1.0],
            "max_rodadas_dia": [60],
        },
        # Montada A PARTIR do 1o passe (grade "fina", 216 combinacoes): o
        # topo inteiro tinha `stop_ticks=12` (o MAIOR da grade) e
        # `ancora_fixa_barras=0` (rolante desde a abertura); `pecas` nao muda
        # P&L nenhum (os filhos preenchem na mesma barra, ao mesmo preco),
        # entao sai da grade e fica fixo em 1. O diagnostico tambem mostrou
        # que 71% do custo total vem da slippage de SAIDA A MERCADO (987
        # stops), o que aponta para stop mais largo e menos rodadas.
        "dirigida": {
            "entrada_ticks": [1.0, 2.0, 4.0, 8.0],
            "alvo_ticks": [3.0, 4.0, 6.0, 10.0],
            "stop_ticks": [12.0, 20.0, 30.0, 60.0],
            "ttl_barras": [15, 40],
            "ancora_fixa_barras": [0],
            "pecas": [1],
            "fracao_entrada": [1.0],
            "max_rodadas_dia": [10, 20, 60],
        },
        # Montada A PARTIR do 2o passe (grade "dirigida", 2026-08-26, 384
        # combinacoes; melhor = `e1 a10 s60 T15 n20`, +R$35.436 em 123
        # pregoes). Mesmo diagnostico do WIN: o vencedor ficou na BORDA de
        # tres dimensoes -- `alvo_ticks=10` e `stop_ticks=60` eram os MAIORES
        # da grade e `ttl_barras=15` o MENOR. Um otimo encostado na borda diz
        # que o otimizador ainda queria andar naquela direcao, e o numero
        # reportado dali descreve onde a grade parou, nao onde o edge para.
        # Esta grade DOBRA e QUADRUPLICA alvo e stop (ate 24 e 240 ticks),
        # devolve `ttl_barras=5` para bracar 15 por baixo, e mantem
        # `max_rodadas_dia` nas tres opcoes em que 20 ja se mostrou INTERIOR.
        #
        # `entrada_ticks` fica em [1, 2] e NAO e' estendido para baixo de
        # proposito: 1 tick e' o menor passo que existe no book, e
        # `_armar` arredonda o preco com `no_tick` -- `entrada_ticks=0,5`
        # nao seria "meia distancia", seria 0 ou 1 tick conforme a paridade da
        # referencia. Essa borda e' do INSTRUMENTO, nao da grade, e por isso
        # nao se estende. Continua 100% in-sample.
        "borda": {
            "entrada_ticks": [1.0, 2.0],
            "alvo_ticks": [6.0, 10.0, 16.0, 24.0],
            "stop_ticks": [30.0, 60.0, 120.0, 240.0],
            "ttl_barras": [5, 15, 40],
            "ancora_fixa_barras": [0],
            "pecas": [1],
            "fracao_entrada": [1.0],
            "max_rodadas_dia": [10, 20, 60],
        },
    },
}


#: Abreviacao de cada parametro no rotulo da linha. Uma letra por dimensao,
#: porque a coluna `variante` da tabela padrao tem largura fixa.
_ABREV = {
    "janela_rompimento": "j", "alvo_vol": "a", "stop_vol": "s", "trail_vol": "t",
    "vol_min_ticks": "v", "max_entradas_dia": "n", "fracao_entrada": "f",
    "aquecimento_barras": "w", "entrada_maker": "M", "entrada_ttl_barras": "T",
    "entrada_ticks": "e", "alvo_ticks": "a", "stop_ticks": "s",
    "ttl_barras": "T", "ancora_fixa_barras": "A", "pecas": "p",
    "max_rodadas_dia": "n",
}


def _valor(v) -> str:
    """`None` vira "-" (nao "off"): a coluna `variante` da tabela padrao tem 26
    caracteres, e o rotulo mais longo desta familia cabe nela por 1 caractere.
    Um rotulo truncado no display faz duas combinacoes DIFERENTES parecerem a
    mesma linha -- foi assim que uma varredura ja pareceu ter repetido o mesmo
    resultado varias vezes."""
    return "-" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def _chaves_variaveis(grade: dict) -> list[str]:
    """So' as dimensoes que a grade REALMENTE varre. Uma dimensao fixa nao
    entra no rotulo -- ela nao distingue nada e so' gastaria largura."""
    return [k for k, valores in grade.items() if len(valores) > 1]


def _rotulo(params: dict, chaves: list[str]) -> str:
    """Rotulo curto, ESTAVEL e UNICO -- e' o que identifica a combinacao
    vencedora na hora de rodar o OOS.

    Derivado das chaves que a grade varre, nunca de uma lista escrita a mao:
    a versao anterior omitia duas dimensoes (`vol_min_ticks`,
    `max_entradas_dia`), nove combinacoes diferentes recebiam o MESMO rotulo e
    o dicionario de resultados sobrescrevia oito delas em silencio -- uma
    varredura que descarta 8/9 do proprio trabalho sem avisar."""
    return " ".join(f"{_ABREV.get(k, k[0])}{_valor(params[k])}" for k in chaves)


def _combinacoes(grade: dict) -> list[dict]:
    chaves = list(grade)
    return [dict(zip(chaves, valores)) for valores in itertools.product(*(grade[k] for k in chaves))]


# `bars` vive num global do processo filho: com ~70 mil barras M1, mandar o
# DataFrame junto de CADA tarefa custaria mais em serializacao do que a
# propria simulacao. `initializer` carrega uma vez por processo.
_BARS = {}


def _preparar(symbol: str) -> None:
    _BARS[symbol] = L.barras(symbol).in_sample()


def _medir(symbol: str, teto: int, params: dict, chaves: list[str]) -> tuple[str, dict]:
    rotulo = _rotulo(params, chaves)
    rodada = L.rodar(symbol, _BARS[symbol], teto, rotulo, **params)
    return rotulo, {
        "linha": rodada.linha(),
        "liquido": rodada.liquido_brl,
        "params": params,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", required=True, choices=sorted(GRADES))
    parser.add_argument("--teto", type=int, default=None,
                        help="teto de contratos simultaneos desta varredura "
                             "(default: o teto de TESTE, com folga sobre o oficial de 2025)")
    parser.add_argument("--grade", choices=("fina", "dirigida", "borda"), default="fina")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--jobs", type=int, default=None)
    args = parser.parse_args()

    symbol = args.symbol
    teto = args.teto if args.teto is not None else L.TETO_DE_TESTE[symbol]
    grade = GRADES[symbol][args.grade]
    combos = _combinacoes(grade)
    chaves = _chaves_variaveis(grade)
    rotulos = {_rotulo(p, chaves) for p in combos}
    if len(rotulos) != len(combos):
        raise SystemExit(
            f"[sweep_copa] {len(combos)} combinacoes produzem so' {len(rotulos)} rotulos "
            "distintos -- o rotulo nao distingue a grade e resultados seriam "
            "sobrescritos em silencio. Ajuste `_ABREV`/`_chaves_variaveis`."
        )
    maior = max(len(r) for r in rotulos)
    if maior > LARGURA_VARIANTE:
        raise SystemExit(
            f"[sweep_copa] rotulo de {maior} caracteres nao cabe na coluna "
            f"`variante` ({LARGURA_VARIANTE}) -- duas combinacoes diferentes "
            "apareceriam como a MESMA linha na tabela. Encurte `_ABREV`."
        )
    workers = args.jobs or max(1, (os.cpu_count() or 4) - 2)

    ins = L.barras(symbol).in_sample()
    print(f"=== {symbol} — IN-SAMPLE: {L.descreve_janela(ins)} ===", flush=True)
    print(f"[sweep_copa] teto={teto} contratos, grade '{args.grade}' = {len(combos)} "
          f"combinacoes em ate {workers} processo(s)", flush=True)

    resultados: dict[str, dict] = {}
    inicio = time.time()
    # Resultado SAI ASSIM QUE FICA PRONTO, um por linha, no formato da tabela
    # padrao -- regra do dono (2026-08-25): "os testes tambem, quando
    # possivel, nao devem esperar todos terminarem para mostrar o resultado;
    # conforme cada um termina ja vai respondendo". Uma varredura de 20
    # minutos que so' fala no fim e' uma varredura que ninguem consegue
    # interromper com informacao -- e interromper cedo, ao ver que o espaco
    # inteiro esta negativo, e' metade do valor de varrer.
    print()
    print(cabecalho(L.EXTRAS), flush=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=_preparar,
                             initargs=(symbol,)) as pool:
        # `as_completed`, nunca `pool.map`: `map` so' entrega na ORDEM de
        # submissao, e uma combinacao rapida (poucos trades) ficaria presa
        # atras de uma lenta ja tendo terminado ha muito tempo. `flush=True`
        # em todo print porque stdout redirecionado a arquivo e' bufferizado
        # em bloco -- sem isso a varredura parece travada ate o fim.
        futuros = {pool.submit(_medir, symbol, teto, p, chaves): p for p in combos}
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
                decorrido = time.time() - inicio
                print(f"[sweep_copa] {i}/{len(combos)} ({decorrido:.0f}s, "
                      f"{decorrido / i:.1f}s/combinacao, melhor "
                      f"R${melhor_ate_agora:,.0f})", flush=True)

    ordenados = sorted(resultados.values(), key=lambda d: d["liquido"], reverse=True)
    print()
    print(f"--- TOP {args.top} de {len(ordenados)} ---")
    print(cabecalho(L.EXTRAS))
    for dados in ordenados[:args.top]:
        print(linha(dados["linha"], L.EXTRAS))
    if len(ordenados) > args.top:
        print(f"  ... {len(ordenados) - args.top} combinacao(oes) fora do top-{args.top}")

    melhor = ordenados[0]
    print()
    print(f"[sweep_copa] melhor no IS: {melhor['linha'].variante}")
    print(f"[sweep_copa] parametros: {melhor['params']}")
    print("[sweep_copa] o IS NAO aprova nada -- confirme UMA vez com "
          "`run_copa_score.py --unlock-oos \"<motivo>\"`.")


if __name__ == "__main__":
    main()
