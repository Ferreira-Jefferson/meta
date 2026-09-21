"""TREINO EVOLUTIVO do WDO@ (2026-09-18) -- 6 especies, caixa que anda,
morte por falta de margem.

## O que este script faz, em ordem

    1. EVOLUI as 6 especies contra a janela de TREINO (52 pregoes), em
       blocos contiguos sorteados por geracao. Capital R$500 andando; quem
       cai abaixo da margem crua de R$150 morre e nao compete com nenhum
       sobrevivente;
    2. escolhe UM finalista por especie usando a janela de VALIDACAO (20
       pregoes que a evolucao nunca viu) -- entre o campeao de cada ilha e os
       elites dela;
    3. re-mede os finalistas na janela de validacao INTEIRA e na base de
       TICK, que e' onde o numero conta;
    4. imprime a tabela padrao e grava tudo.

O OOS (51 pregoes cegos) NAO e' tocado aqui. Ele sai so' com `--oos`, e
gastar essa flag e' uma decisao do dono, nao um passo do pipeline: depois de
olhar, aquela janela deixa de ser cega para sempre.

## Por que TRES janelas e nao duas

    TREINO  2026-02-27 .. 2026-05-14   52 pregoes   o fitness ve
    VALID   2026-05-15 .. 2026-06-12   20 pregoes   so' a escolha do finalista ve
    OOS     2026-06-15 .. 2026-08-25   50 pregoes   ninguem ve ate `--oos`

Com 6 especies x dezenas de individuos x dezenas de geracoes, o campeao do
treino foi escolhido entre DEZENAS DE MILHARES de candidatos. Escolher, entre
eles, qual vai ao teste cego usando o mesmo numero que os selecionou seria
gastar o OOS para descobrir algo que o IS ja' podia dizer. A validacao existe
para essa peneira, e o OOS para uma pergunta so'.

## O painel

Uma copia de `evo/painel.html` vai para a pasta de saida junto com o
`progresso.js` que o laco reescreve a cada geracao. Abra o HTML no navegador
(duplo clique, sem servidor) e deixe aberto: ele recarrega sozinho.

Uso:
    python -u scripts/daytrade/evo_wdo_treino_2026_09_18.py
    python -u scripts/daytrade/evo_wdo_treino_2026_09_18.py --rapido
    python -u scripts/daytrade/evo_wdo_treino_2026_09_18.py --especies cega,crua
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
for _p in (RAIZ / "src", Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from strategy.daytrade.evo.genoma import Genoma  # noqa: E402

from evo import especies as ESP  # noqa: E402
from evo.avaliacao import avalia, min_trades, resumo_pontos  # noqa: E402
from evo.dados import CAPITAL_PARTIDA_BRL, MARGEM_WDO_BRL, pregoes  # noqa: E402
from evo.ga import evolui  # noqa: E402

SAIDA = RAIZ / "scratch" / "evo_wdo_2026_09_18"
PAINEL = Path(__file__).resolve().parent / "evo" / "painel.html"


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    # Os defaults sao um ORCAMENTO DE TEMPO, nao um otimo teorico. Medido
    # nesta maquina (12 processos): ~1,9s por individuo por 15 pregoes, entao
    # 6 especies x 30 individuos = 180 avaliacoes por geracao custam ~110s, e
    # 40 geracoes fecham em ~1h15. Popular mais ou alongar a amostra melhora
    # a busca e sai do alcance de uma sessao de trabalho -- quem quiser a
    # rodada profunda passa `--pop 60 --amostra 30` e deixa rodando a noite.
    p.add_argument("--pop", type=int, default=30,
                   help="individuos por especie (default 30)")
    p.add_argument("--geracoes", type=int, default=40)
    p.add_argument("--amostra", type=int, default=15,
                   help="pregoes contiguos por geracao (default 15)")
    p.add_argument("--semente", type=int, default=20260918)
    p.add_argument("--especies", type=str, default="",
                   help=f"lista separada por virgula. {', '.join(ESP.nomes())}")
    p.add_argument("--rapido", action="store_true",
                   help="pop 24, 15 geracoes, amostra 14 -- para ver o "
                        "mecanismo funcionando, nao para decidir nada")
    p.add_argument("--oos", action="store_true",
                   help="GASTA a janela cega nos finalistas. Decisao do dono.")
    p.add_argument("--workers", type=int,
                   default=min(12, os.cpu_count() or 4))
    a = p.parse_args()
    if a.rapido:
        a.pop, a.geracoes, a.amostra = 24, 15, 14
    return a


def _linha(rot: str, r, extra: str = "") -> str:
    estado = "MORREU" if r.morreu else "vivo"
    return (f"{rot:<24}{estado:<8}{r.n_trades:>5}"
            f"{r.r_por_op:>+9.2f}{r.liquido:>+11.2f}"
            f"{r.win_pct:>7.2f}{r.breakeven_emp:>8.2f}"
            f"{r.caixa_final:>10.2f}{100 * r.dd_relativo:>8.1f}"
            f"  {extra}")


def _cabecalho() -> str:
    """`DD%` e' o drawdown RELATIVO ao pico de caixa do momento, nao em
    reais -- perder R$50 com R$100 em caixa e com R$1.000 sao riscos
    diferentes de quebrar a banca (ver `avaliacao.PENALIDADE_DD_RELATIVO`)."""
    return (f"{'individuo':<24}{'estado':<8}{'ops':>5}{'R$/op':>9}"
            f"{'liquido':>11}{'win%':>7}{'BE emp':>8}"
            f"{'caixa f':>10}{'DD%':>8}")


def main() -> None:
    a = _args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PAINEL, SAIDA / "painel.html")

    lista = ESP.resolve([s for s in a.especies.split(",") if s] or None)
    treino = pregoes("TREINO")
    valid = pregoes("VALID")

    print("=" * 78)
    print("TREINO EVOLUTIVO -- WDO@")
    print("=" * 78)
    print(f"treino     {treino[0]} .. {treino[-1]}  ({len(treino)} pregoes)")
    print(f"validacao  {valid[0]} .. {valid[-1]}  ({len(valid)} pregoes)")
    print(f"painel     {SAIDA / 'painel.html'}")
    print()

    ilhas = evolui(
        lista, treino,
        tamanho_pop=a.pop, geracoes=a.geracoes, amostra=a.amostra,
        semente=a.semente, pasta_saida=SAIDA, max_workers=a.workers,
    )

    # --- peneira: a janela de VALIDACAO decide, nao o treino --------------
    print("\n" + "=" * 78)
    print(f"VALIDACAO -- {len(valid)} pregoes que a evolucao NUNCA viu, em M1")
    print("=" * 78)
    print(_cabecalho())
    print("-" * 78)

    finalistas = []
    for nome, ilha in ilhas.items():
        if ilha.melhor is None:
            continue
        g = Genoma(cru=tuple(ilha.melhor["cru"]))
        r = avalia(g, valid, feed="m1")
        pts = resumo_pontos(r)
        finalistas.append((nome, g, r, pts))
        print(_linha(nome, r, f"mediana {pts['mediana_abs_pts']:.1f} pts"))

    piso = min_trades(len(valid))
    vivos = [f for f in finalistas
             if not f[2].morreu and f[2].n_trades >= piso
             and f[2].r_por_op > 0]
    print("-" * 78)
    if not vivos:
        print("NENHUM finalista sobreviveu a validacao com R$/op positivo.")
        print("Isso e' um resultado, nao uma falha do script: a evolucao nao")
        print("achou nada que se sustente fora da janela em que evoluiu.")
    else:
        print(f"{len(vivos)} de {len(finalistas)} finalistas passam a "
              f"validacao (vivo, >= {piso} operacoes, R$/op > 0).")

    # --- confirmacao em TICK: o numero que vale ---------------------------
    if vivos:
        print("\n" + "=" * 78)
        print("CONFIRMACAO EM TICK -- mesma validacao, base de negocio a "
              "negocio")
        print("=" * 78)
        print("O M1 e' surrogado: ele credita o volume inteiro do minuto")
        print("contra a fila. Divergencia aqui manda; o M1 nao.")
        print(_cabecalho())
        print("-" * 78)
        for nome, g, r_m1, _pts in vivos:
            r_tk = avalia(g, valid, feed="tick")
            p_tk = resumo_pontos(r_tk)
            print(_linha(f"{nome} (tick)", r_tk,
                         f"mediana {p_tk['mediana_abs_pts']:.1f} pts"))

    if a.oos:
        oos = pregoes("OOS")
        print("\n" + "=" * 78)
        print(f"OOS GASTO -- {len(oos)} pregoes, {oos[0]} .. {oos[-1]}")
        print("Esta janela deixa de ser cega a partir de agora.")
        print("=" * 78)
        print(_cabecalho())
        print("-" * 78)
        for nome, g, _r, _p in (vivos or finalistas):
            r = avalia(g, oos, feed="tick")
            print(_linha(f"{nome} (tick)", r,
                         f"mediana {resumo_pontos(r)['mediana_abs_pts']:.1f} pts"))

    # --- grava -------------------------------------------------------------
    destino = SAIDA / "finalistas.json"
    destino.write_text(json.dumps([
        {"especie": nome, "genoma": list(g.cru),
         "descricao": g.descricao(),
         "validacao": {"morreu": r.morreu, "n_trades": r.n_trades,
                       "r_por_op": r.r_por_op, "liquido": r.liquido,
                       "win_pct": r.win_pct, "breakeven": r.breakeven_emp,
                       "caixa_final": r.caixa_final,
                       "caixa_minimo": r.caixa_minimo}}
        for nome, g, r, _p in finalistas
    ], ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nfinalistas em {destino}")
    print(f"progresso e painel em {SAIDA}")
    for nome, g, _r, _p in finalistas:
        print("\n" + "-" * 78)
        print(f"[{nome}]")
        print(g.descricao())


if __name__ == "__main__":
    main()
