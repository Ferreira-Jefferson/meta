"""Avaliacao da familia `copa` — in-sample de referencia, o portao G1–G7 no
out-of-sample CEGO, a escada de teto e as baterias da final presencial.

O OOS e' rodado UMA vez, com o parametro JA escolhido no IS, e so' depois de
`--unlock-oos "<motivo>"` (a trava e' estrutural, `LockedBars.out_of_sample()`
levanta sem ela). Sem a flag, este script roda so' o IS e o criterio de
parada -- que e' o comportamento util no dia a dia.

## O que cada etapa responde

| etapa | pergunta |
|---|---|
| IS | quanto o parametro escolhido rende no trecho que a varredura ja viu? |
| criterio de parada | vale a pena continuar, ou o dado ja nega o alvo? |
| OOS etapa A (teto de TESTE) | o edge sobrevive em dado que ninguem olhou? (G1–G5, G7) |
| OOS etapa B (teto OFICIAL) | nada quebra quando o teto sobe de 12/4 para 15/5? (G6) |
| escada de teto | qual a curva de saturacao, se a B3/BTG mexer no teto? |
| baterias 40/45 min | a final presencial e' ganhavel, e o robo nao devolve ganho depois do minuto 40? |

Uso:
    python scripts/daytrade/run_copa_score.py --symbol WIN@
    python scripts/daytrade/run_copa_score.py --symbol WIN@ --unlock-oos "confirmacao unica"
    python scripts/daytrade/run_copa_score.py --symbol WDO@ --escada 2,3,4,5,8
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import copa_lab as L  # noqa: E402
from backtest.intraday.copa_score import (  # noqa: E402
    MINUTOS_BATERIA,
    PREGOES_POR_FASE,
    blocos_de_fase,
    janelas_sprint,
    resultados_diarios,
    resumir_blocos,
    resumo_sprint,
)
from backtest.intraday.report import (  # noqa: E402
    cabecalho,
    linha,
    maxdd_intradiario_mediano_brl,
    num_br,
)

# ---------------------------------------------------------------------------
# CALIBRACAO escolhida NO IN-SAMPLE. Uma entrada por simbolo, com a evidencia
# junto -- mesma convencao das tabelas de calibracao da familia `gremah`.
# Trocar um numero aqui exige ter rodado `sweep_copa.py` de novo; e o OOS
# NUNCA participa da escolha.
# ---------------------------------------------------------------------------
CALIBRACAO_IS: dict[str, dict] = {
    # WIN@ -- melhor `liquido R$` de 540 combinacoes da grade "borda"
    # (2026-08-26), o passe que abriu `fracao_entrada`, `aquecimento_barras` e
    # o teto de `max_entradas_dia`, congelados nos dois passes anteriores.
    # Medido no IN-SAMPLE (2025-12-01 -> 2026-06-12, 129 pregoes com sessao
    # completa): +R$96.352,80 liquidos = R$746,92/pregao, lucro/DD 5,26,
    # win 38,3%, 1.086 trades, bloco mediano de 4 pregoes R$2.163, 23/32
    # blocos positivos, 0,0% de ordens recusadas pelo teto.
    #
    # DUAS RESSALVAS que o numero sozinho esconde:
    #
    # 1. `fracao_entrada=1,0` NAO e' sinal, e' escala. O P&L e' EXATAMENTE
    #    linear nela (36.987 / 55.480,50 / 73.974 para 0,5 / 0,75 / 1,0 no
    #    mesmo ponto) e `recusas%` fica em 0,0: o robo abre UMA posicao por
    #    vez, entao encosta no teto sem nunca ultrapassa-lo e
    #    `max_open_contracts` nunca recusa nada. Ou seja, dos R$96k, mais da
    #    metade do salto sobre a calibracao anterior e' so' ter parado de usar
    #    metade do teto -- e o unico jeito de multiplicar este desenho e'
    #    subir o TETO, nao melhorar o sinal.
    # 2. O otimo e' um PICO ESTREITO, nao um plato. Vizinhos imediatos, no
    #    proprio vencedor: `entrada_ttl_barras` 12/15/20 = 48.694 / 96.353 /
    #    59.609 e `aquecimento_barras` 30/45/60 = 80.651 / 96.353 / 57.610.
    #    Cair pela metade a 3 barras do otimo em 129 pregoes e' o formato de
    #    um numero que o OOS nao costuma confirmar.
    "WIN@": dict(janela_rompimento=10, alvo_vol=4.0, stop_vol=2.0, trail_vol=None,
                 vol_min_ticks=8.0, fracao_entrada=1.0, aquecimento_barras=45,
                 max_entradas_dia=10, entrada_maker=True, entrada_ttl_barras=15),
    # WDO@ -- melhor `liquido R$` de 384 combinacoes da grade "dirigida"
    # (2026-08-26) CONFIRMADO por 288 combinacoes da grade "borda" no mesmo
    # dia: o vencedor nao se moveu nem uma casa quando `alvo_ticks` foi
    # estendido ate 24 e `stop_ticks` ate 240. Medido no IN-SAMPLE
    # (2025-12-01 -> 2026-06-12, 123 pregoes com sessao completa):
    # +R$35.435,68 liquidos = R$288,09/pregao, lucro/DD 3,20, win 82,9%,
    # 1.218 trades, bloco mediano de 4 pregoes R$1.007, 22/30 blocos
    # positivos, 0,0% de ordens recusadas pelo teto.
    "WDO@": dict(entrada_ticks=1.0, alvo_ticks=10.0, stop_ticks=60.0, ttl_barras=15,
                 ancora_fixa_barras=0, pecas=1, fracao_entrada=1.0, max_rodadas_dia=20),
}

#: Teto OFICIAL da Copa 2025, por ativo. Vive aqui (script) e nao no robo: e'
#: um numero de REGULAMENTO, que pode mudar antes de 14/09/2026 -- o robo
#: recebe o teto, nunca o conhece.
TETO_OFICIAL = {"WIN@": 15, "WDO@": 5}

#: Escada de diagnostico default por ativo -- responde "e se o teto mudar?"
#: sem tocar em codigo nenhum.
ESCADA_PADRAO = {"WIN@": (6, 8, 10, 12, 15, 20), "WDO@": (2, 3, 4, 5, 8)}

#: Alvo do dono: superar o campeao de 2025 (R$108.745 nas classificatorias) em
#: 3-5x. Denominador CONSERVADOR de 8 pregoes (se o numero dele incluir a
#: semifinal, a regua cai e o alvo fica mais facil). RELATORIO, nunca portao.
DANILLO_POR_PREGAO_BRL = 108_745.0 / 8.0


@dataclass(frozen=True)
class Criterio:
    codigo: str
    pergunta: str
    passou: bool
    medido: str
    exigido: str


def _sim_nao(ok: bool) -> str:
    return "PASSA" if ok else "REPROVA"


def imprime_portao(criterios: list[Criterio]) -> bool:
    print(f"{'':<4}{'criterio':<46}{'medido':>22}{'exigido':>22}   veredito")
    print("-" * 100)
    for c in criterios:
        print(f"{c.codigo:<4}{c.pergunta:<46}{c.medido:>22}{c.exigido:>22}   "
              f"{_sim_nao(c.passou)}", flush=True)
    todos = all(c.passou for c in criterios)
    print(f"\n>>> PORTAO: {'APROVADO' if todos else 'REPROVADO'} "
          f"({sum(c.passou for c in criterios)}/{len(criterios)} criterios)\n")
    return todos


def portao(rodada_teste, rodada_pedagio, rodada_oficial) -> list[Criterio]:
    """G1–G7 do plano, com o numero medido ao lado do exigido.

    Nenhum criterio le `score_copa` (a regra de descartar o pior dia): a
    funcao objetivo escolhida pelo dono e' lucro total, convencional, e o
    score entra so' como numero de relatorio."""
    diarios = rodada_teste.diarios
    blocos = blocos_de_fase(diarios)
    r = resumir_blocos(blocos, diarios)
    dd_intra = maxdd_intradiario_mediano_brl(rodada_teste.resultado.equity_curve)
    minimo_positivos = int(round(0.75 * r.n_blocos))
    pior_bloco_perda = max(0.0, -r.pior_bloco_brl)

    return [
        Criterio("G1", "blocos de 4 pregoes positivos",
                 r.positivos >= minimo_positivos,
                 f"{r.positivos}/{r.n_blocos}", f">= {minimo_positivos}/{r.n_blocos}"),
        Criterio("G2", "bloco mediano > MaxDD intradiario mediano",
                 r.liquido_mediano_brl > max(dd_intra, 0.0),
                 f"R$ {num_br(r.liquido_mediano_brl, 0)}", f"> R$ {num_br(dd_intra, 0)}"),
        Criterio("G3", "pior bloco nao anula um bloco vencedor tipico",
                 pior_bloco_perda <= max(r.mediana_dos_vencedores_brl, 0.0),
                 f"R$ {num_br(-pior_bloco_perda, 0)}",
                 f">= R$ {num_br(-r.mediana_dos_vencedores_brl, 0)}"),
        Criterio("G4", "pior pregao >= -1x o pregao positivo tipico",
                 r.pior_pregao_brl >= -r.mediana_dos_pregoes_positivos_brl,
                 f"R$ {num_br(r.pior_pregao_brl, 0)}",
                 f">= R$ {num_br(-r.mediana_dos_pregoes_positivos_brl, 0)}"),
        Criterio("G5", "ordens recusadas pelo teto",
                 rodada_teste.recusas_pct < 5.0,
                 f"{num_br(rodada_teste.recusas_pct, 1)}%", "< 5,0%"),
        Criterio("G6", "P&L no teto OFICIAL >= P&L no teto de teste",
                 rodada_oficial.liquido_brl >= rodada_teste.liquido_brl,
                 f"R$ {num_br(rodada_oficial.liquido_brl, 0)}",
                 f">= R$ {num_br(rodada_teste.liquido_brl, 0)}"),
        Criterio("G7", "sobrevive a 1 tick de pedagio em todo fill maker",
                 rodada_pedagio.liquido_brl > 0,
                 f"R$ {num_br(rodada_pedagio.liquido_brl, 0)}", "> R$ 0"),
    ]


def secao(titulo: str) -> None:
    print(f"\n{'=' * 100}\n{titulo}\n{'=' * 100}", flush=True)


def _tabela(rodadas: list) -> None:
    print(cabecalho(L.EXTRAS))
    for r in rodadas:
        print(linha(r.linha(), L.EXTRAS), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", required=True, choices=sorted(CALIBRACAO_IS))
    parser.add_argument("--teto", type=int, default=None,
                        help="teto de TESTE desta avaliacao (default: com folga sobre o oficial)")
    parser.add_argument("--params", default=None,
                        help="JSON que sobrescreve a calibracao declarada (varredura ad-hoc)")
    parser.add_argument("--escada", default=None,
                        help="tetos separados por virgula para a curva de saturacao")
    parser.add_argument("--sprint", default=",".join(str(m) for m in MINUTOS_BATERIA),
                        help="minutos das baterias da final (default: 40,45)")
    parser.add_argument("--unlock-oos", default=None,
                        help="MOTIVO do desbloqueio do out-of-sample. Sem isto o "
                             "script roda so' o in-sample -- a trava e' estrutural.")
    args = parser.parse_args()

    symbol = args.symbol
    teto_teste = args.teto if args.teto is not None else L.TETO_DE_TESTE[symbol]
    teto_oficial = TETO_OFICIAL[symbol]
    params = dict(CALIBRACAO_IS[symbol])
    if args.params:
        params.update(json.loads(args.params))

    travadas = L.barras(symbol)
    ins = travadas.in_sample()

    secao(f"{symbol} — IN-SAMPLE (o trecho que a varredura JA viu)")
    print(f"janela: {L.descreve_janela(ins)}")
    print(f"parametros: {params}")
    print(f"teto de teste: {teto_teste} contratos | teto oficial 2025: {teto_oficial}\n")
    is_rodada = L.rodar(symbol, ins, teto_teste, "IS teto de teste", **params)
    is_sem_custo = L.rodar(symbol, ins, teto_teste, "IS sem custo", com_custo=False, **params)
    _tabela([is_rodada, is_sem_custo])

    secao("CRITERIO DE PARADA (avaliado no IS, onde e' legitimo olhar)")
    por_pregao = is_rodada.liquido_brl / max(1, is_rodada.linha().pregoes)
    resumo_is = is_rodada.resumo
    print(f"R$/pregao no IS: R$ {num_br(por_pregao, 2)}")
    print(f"1x Danillo (8 pregoes, WIN+WDO somados): R$ {num_br(DANILLO_POR_PREGAO_BRL, 2)}/pregao")
    print(f"bloco mediano de {PREGOES_POR_FASE} pregoes: R$ {num_br(resumo_is.liquido_mediano_brl, 2)}")
    if resumo_is.liquido_mediano_brl <= 0:
        print("\n>>> O bloco mediano do IS e' <= 0. Pelo criterio de parada do plano, esta "
              "calibracao e' DESCARTADA sem tocar no OOS -- rode `sweep_copa.py` de novo.")
    elif por_pregao < DANILLO_POR_PREGAO_BRL:
        print("\n>>> Abaixo de 1x Danillo no IS: 3x esta fora de alcance para esta "
              "calibracao. Segue-se com o melhor que o dado sustenta, sem inflar o numero.")

    if not args.unlock_oos:
        print("\n[run_copa_score] OOS NAO desbloqueado -- rode com "
              "`--unlock-oos \"<motivo>\"` quando o parametro estiver escolhido.")
        return

    travadas.unlock(args.unlock_oos)
    oos = travadas.out_of_sample()

    secao(f"OOS ETAPA A — teto de TESTE ({teto_teste} contratos)")
    print(f"janela: {L.descreve_janela(oos)}\n")
    a_rodada = L.rodar(symbol, oos, teto_teste, f"OOS teto {teto_teste}", **params)
    a_pedagio = L.rodar(symbol, oos, teto_teste, "OOS + pedagio 1 tick",
                        pedagio_ticks=1.0, **params)
    a_sem_custo = L.rodar(symbol, oos, teto_teste, "OOS sem custo", com_custo=False, **params)
    _tabela([a_rodada, a_pedagio, a_sem_custo])

    secao(f"OOS ETAPA B — teto OFICIAL 2025 ({teto_oficial} contratos)")
    print("Mesmos parametros, so' o teto muda. Se o lucro CAIR quando o teto sobe, o edge\n"
          "dependia de estar limitado -- ajuste acidental, e investigar isso vem antes de\n"
          "qualquer outra coisa.\n")
    b_rodada = L.rodar(symbol, oos, teto_oficial, f"OOS teto {teto_oficial}", **params)
    _tabela([a_rodada, b_rodada])

    secao("PORTAO DE ACEITACAO G1–G7 (todos obrigatorios)")
    aprovado = imprime_portao(portao(a_rodada, a_pedagio, b_rodada))

    escada = ([int(x) for x in args.escada.split(",")] if args.escada
              else list(ESCADA_PADRAO[symbol]))
    secao("ESCADA DE TETO — curva de saturacao")
    print("Responde direto a 'as regras podem mudar': se o teto subir ou descer, esta\n"
          "curva ja diz o efeito, sem tocar em codigo.\n")
    print(cabecalho(L.EXTRAS))
    for t in escada:
        r = L.rodar(symbol, oos, t, f"teto {t}", **params)
        print(linha(r.linha(), L.EXTRAS), flush=True)

    secao("FINAL PRESENCIAL — baterias deslizantes")
    print("40 min e' o tempo de PROJETO; 45 min entra como CONFIRMACAO. Se a mediana de\n"
          "45 for MENOR que a de 40, o robo devolve ganho depois do minuto 40 -- isso e'\n"
          "defeito, nao conservadorismo.\n")
    minutos = [int(m) for m in args.sprint.split(",")]
    resumos = {}
    print(f"{'bateria':<12}{'janelas':>9}{'pior':>14}{'p25':>14}{'mediana':>14}"
          f"{'p75':>14}{'melhor':>14}{'positivas':>12}")
    print("-" * 103)
    for m in minutos:
        resumos[m] = resumo_sprint(janelas_sprint(a_rodada.resultado.trades, minutos=m))
        s = resumos[m]
        print(f"{f'{m} min':<12}{s['janelas']:>9}{num_br(s['pior'], 0):>14}"
              f"{num_br(s['p25'], 0):>14}{num_br(s['mediana'], 0):>14}"
              f"{num_br(s['p75'], 0):>14}{num_br(s['melhor'], 0):>14}"
              f"{num_br(s['positivas_pct'], 1) + '%':>12}", flush=True)
    if 40 in resumos and 45 in resumos:
        ok = resumos[45]["mediana"] >= resumos[40]["mediana"]
        print(f"\nmediana(45) >= mediana(40): {_sim_nao(ok)}")

    secao("AMBICAO (reportada, nunca gateada)")
    diarios = a_rodada.diarios
    blocos = blocos_de_fase(diarios)
    if blocos:
        med = sorted(b.liquido_brl for b in blocos)[len(blocos) // 2]
        score = sorted(b.score_copa_brl for b in blocos)[len(blocos) // 2]
        alvo_1x = DANILLO_POR_PREGAO_BRL * PREGOES_POR_FASE
        print(f"bloco mediano de {PREGOES_POR_FASE} pregoes: R$ {num_br(med, 0)}")
        print(f"score Copa mediano (descartando o pior dia): R$ {num_br(score, 0)}")
        print(f"1x Danillo por bloco: R$ {num_br(alvo_1x, 0)} | "
              f"3x: R$ {num_br(3 * alvo_1x, 0)} | 5x: R$ {num_br(5 * alvo_1x, 0)}")
        print(f"multiplo alcancado: {num_br(med / alvo_1x, 2)}x")
    print(f"\n[run_copa_score] {symbol}: portao {'APROVADO' if aprovado else 'REPROVADO'}.")


if __name__ == "__main__":
    main()
