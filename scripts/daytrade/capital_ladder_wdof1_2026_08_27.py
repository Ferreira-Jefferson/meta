"""Escada de capital da `WdoGridReloadMaker` F1 (WDO@, "T1 S16 x1") --
2026-08-27. MESMA estrutura de `capital_ladder_copawin_2026_08_27.py`
(ler aquele arquivo primeiro para a prova de monotonicidade e o desenho da
busca binaria -- nao repetida aqui em detalhe).

Pergunta do dono: para cada teto de contratos N (1..10, ESTATICO -- `quantity
=N` no construtor, `margin_per_contract_brl=None`, SEM a realocacao dinamica
de `capital_dinamico_rerun_2026_08_27.py`), qual e' o MENOR capital inicial
que sobrevive ao teste de rejeicao de fila (i.i.d. p=50%, 30 sementes) sem
NENHUMA semente arruinar (equity <= 0) em algum ponto do IN-SAMPLE? E o
quanto esse numero excede o "piso ingenuo" N x R$150 (margem/contrato) x
MARGIN_BUFFER_FUTUROS (2.0).

## Resolucao: TICK, nao M1

`capital_dinamico_rerun_2026_08_27.py` (o rerun mais recente que mede esta
MESMA estrategia neste MESMO simbolo) usa `wdo_grid_reload_f1_tick_lab.
carregar_tick_bars()` -- 72 dos 123 pregoes IS que tem tick history retido
pelo terminal MT5 (Rico), 2026-02-27..2026-06-12 -- e nao M1. Este script usa
a MESMA resolucao (tick), pelo MESMO motivo (numeros comparaveis com a
memoria oficial mais recente, `capital_dinamico_rerun_2026_08_27` /
`gremah_calibracao...` etc nao se aplicam aqui, mas o padrao de "usar a
leitura mais recente da mesma frente" sim). RESSALVA que se aplica a todo
numero deste arquivo: e' um subconjunto de 58,5% do IS (faltam os 51
PRIMEIROS pregoes, sem tick history), nao o candidato IS completo -- ver
`wdo_grid_reload_f1_tick_lab.py` para o levantamento de viabilidade.

## Modo ESTATICO, de proposito

`WdoGridReloadMaker(quantity=N, margin_per_contract_brl=None, ...)` --
`margin_per_contract_brl=None` (default) e' o modo em que `self.quantity`
viaja DIRETO para cada `EnterLimit`, nunca reagindo ao caixa
(`wdo_grid_reload_maker.py:242-256`). E' o modo que
`capital_dinamico_rerun_2026_08_27.py` chama de "ESTATICO" -- a realocacao
dinamica fica fora de escopo aqui por instrucao explicita da missao.

`config.max_open_contracts` fica FIXO em `TETO_MOTOR_FIXO=10` (>= todo N
testado, 1..10) para NENHUMA rodada esbarrar na armadilha de engine
(`_cabe_no_teto`/`_recusa_por_teto`, `machine.py:763-778`) -- mesmo desenho
de `TETO_MOTOR=15` em `capital_ladder_copawin_2026_08_27.py`.

**Teto OFICIAL da Copa BTG para WDO@ e' 5 contratos** (`profiles.py:235`,
regra especifica da competicao ja encerrada, NAO um limite fisico) --
`TETO_MOTOR_FIXO=10` deliberadamente NAO usa esse numero (que capparia N=6..
10 em silencio via `_cabe_no_teto` se fosse usado como teto do motor). Os
resultados de N=6..10 abaixo SAO reportados, mas marcados
`excede_teto_copa_btg=true` no JSON e sinalizados na tabela final -- podem
nao fazer sentido se a regra da competicao (encerrada) voltar a importar.

## Diferenca real frente a' `CopaWin`: fills PODEM variar com N

`montar_config()` usa `limit_fill_capped_by_volume=True` (padrao de teste do
repo desde 2026-08-23) -- uma ordem parada (entrada OU alvo, as DUAS maker
neste robo) so preenche se o volume real da barra/tick cobrir a `quantity`
pedida. Ao contrario de `CopaWin` (onde as 10 rodadas de `roda_base`
mediram EXATAMENTE 1.086 trades para todo N -- volume nunca foi o gargalo
la'), aqui N MAIOR pode, em tese, preencher MENOS (nivel toca mas o negocio
daquele tick/barra nao tem volume pra cobrir N contratos) -- entao a
rodada do motor e' feita de VERDADE, uma vez por N (nunca reaproveitando o
trade log de outro N), exatamente como a missao pede.

## Atalho computacional -- DECLARADO explicitamente

Assim como em `capital_ladder_copawin_2026_08_27.py`: a rodada do MOTOR
roda **UMA UNICA VEZ por N** (capital NOCIONAL, `wdo_grid_reload_f1_lab.
CAPITAL_NOCIONAL=1.000.000`, grande o bastante pra nunca disparar o freio de
ruina do motor mesmo com N=10), e a sequencia de trades resultante e'
reaproveitada para TODAS as avaliacoes da busca binaria (todo capital
candidato, todas as 30 sementes) -- NENHUMA rodada do motor com o capital
REAL candidato acontece. Isto e' correto pela MESMA prova de
`capital_ladder_copawin_2026_08_27.py`, ponto a ponto:

  1. `quantity=N` fixo (`margin_per_contract_brl=None`) nunca olha o caixa
     -- `wdo_grid_reload_maker.py:251-256`.
  2. `enforce_capital_minimo` resolve para `profile.max_open_contracts is
     None` quando nao passado explicito (`profiles.py:408-409`) -- WDO@
     declara `max_open_contracts=5` no perfil (nao usado aqui como teto do
     MOTOR, so' como fato do instrumento), entao esse portao fica `False` e
     nenhum pregao e' pulado por capital.
  3. As unicas leituras de `config.initial_capital` dentro do motor sao
     `on_capital_update` (so' importa com `margin_per_contract_brl` setado)
     e o metadado `capital_base` de `IntradayTrade` (nao entra em
     `pnl_brl`).

Ou seja: rodar o motor de novo para cada capital candidato produziria os
MESMOS trades, byte-a-byte -- so' a leitura POS-HOC do equity muda. A
reconstrucao pos-hoc por semente (mesma tecnica de
`capital_dinamico_rerun_2026_08_27.py::rejeicao_p_alvo`) e' uma OTIMIZACAO
exata: as 30 sementes completas sao usadas em TODO passo da busca binaria,
nenhuma reducao foi necessaria (a reconstrucao pos-hoc e' barata: numpy/loop
puro sobre uma lista de ~poucos milhares de trades ja computada, sem
remontar a maquina).

O CARO aqui e' a rodada do motor em si -- resolucao TICK, ~2,83M linhas de
tick por N (medido: ~125s/rodada nesta maquina) -- 10 rodadas (N=1..10) =~
21 minutos so' de motor, antes de qualquer busca binaria.

## "Ruina" e busca binaria

Identico a `capital_ladder_copawin_2026_08_27.py`: `equity = capital_inicial`,
depois um degrau por trade ACEITO (sorteio i.i.d. p=0,5, independente do
resultado do trade), na ORDEM cronologica original; se a curva toca <=0 em
algum degrau, a semente "zerou" -- mesmo criterio do freio incondicional do
motor (`engine.py`: `if equity_atual <= 0: wiped_out_at = ts; break`). Os
aceitos sao gerados por semente/`n` (nunca por capital), entao "zerou" e'
monotonico NAO-CRESCENTE em capital -- garante que a busca binaria converge
para o minimo correto (mesma prova do modulo irmao).

Busca: comeca no piso ingenuo; se ja for seguro, busca para BAIXO (metade em
metade) ate achar um ponto inseguro; senao, expande para CIMA
geometricamente (x1,5) ate achar um ponto seguro; bisecta entre o par
(inseguro, seguro) ate a faixa convergir dentro de
`max(TOL_ABS_BRL, TOL_REL x lado seguro)`. Tolerancia mais fina que a de
`CopaWin` (R$20 / 1% contra R$500 / 5% la') porque a escala de capital aqui
e' bem menor (piso ingenuo 1..10 contratos: R$300..R$3.000, contra
R$200..R$2.000 do WIN mas com MaxDD por contrato tipicamente maior no WDO --
ver a tabela final) e o custo computacional da busca e' o mesmo (pos-hoc,
sem rerodar o motor) -- nao ha' motivo pra aceitar uma faixa larga. O
resultado final e' arredondado para CIMA em multiplos de `ARREDONDA_BRL=R$10`
(preserva a garantia de seguranca, por monotonicidade) e reverificado com as
30 sementes completas.

Janela: SO' o IN-SAMPLE tick (`wdo_grid_reload_f1_tick_lab.
carregar_tick_bars()`, subconjunto de `LockedBars.in_sample()`) -- o corte
congelado `OOS_CUTOFF=2026-06-13` (`profiles.py:103`) nunca e' tocado,
`.unlock()` nunca e' chamado.

Uso: `python -u scripts/daytrade/capital_ladder_wdof1_2026_08_27.py`
"""
from __future__ import annotations

import csv
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br, maxdd_brl  # noqa: E402
from strategy.daytrade.base import MARGIN_BUFFER_FUTUROS  # noqa: E402

import wdo_grid_reload_f1_lab as G  # noqa: E402
import wdo_grid_reload_f1_tick_lab as GT  # noqa: E402

# ---------------------------------------------------------------------------
# constantes da missao
# ---------------------------------------------------------------------------
SYMBOL = "WDO@"
MARGEM_CONTRATO_BRL = 150.0      # margem/contrato conhecida (portao de capital real, 2026-08-27)
TETO_MOTOR_FIXO = 10             # >= todo N testado (1..10) -- NAO o teto oficial Copa BTG (5, ver docstring)
TETO_OFICIAL_COPA_BTG = 5        # profiles.py:235 -- regra da competicao ja encerrada, so' para SINALIZAR
N_SEMENTES = 30
P_REJEICAO = 0.5
SEED_BASE = 0
N_VALUES = list(range(1, 11))

TOL_ABS_BRL = 20.0
TOL_REL = 0.01
ARREDONDA_BRL = 10.0

OUT_DIR = ROOT / "scripts" / "daytrade"
TRADE_LOG_N1_CSV = OUT_DIR / "capital_ladder_wdof1_n1_trades_2026_08_27.csv"
RESULT_JSON = OUT_DIR / "capital_ladder_wdof1_result_2026_08_27.json"


# ---------------------------------------------------------------------------
# rodada do motor -- UMA VEZ por N (ver docstring do modulo: "atalho
# computacional" -- diferente de CopaWin, aqui o RESULTADO do motor pode
# genuinamente variar entre N por causa de `limit_fill_capped_by_volume`,
# entao cada N tem sua PROPRIA rodada real, nunca reaproveitada de outro N).
# ---------------------------------------------------------------------------

def roda_base(n: int, tick_bars: pd.DataFrame):
    """`quantity=n`, ESTATICO (`margin_per_contract_brl` nao passado -- fica
    `None`), capital NOCIONAL (`G.montar_config()` ja usa
    `G.CAPITAL_NOCIONAL=1.000.000`) e `max_open_contracts` elevado para
    `TETO_MOTOR_FIXO` (>= n sempre)."""
    cfg_nocional = G.montar_config()  # config padrao: fee + slippage 1 tick, fill capped por volume
    cfg = dataclasses.replace(cfg_nocional, max_open_contracts=TETO_MOTOR_FIXO)
    return G.rodar(tick_bars, cfg, quantity=n)


# ---------------------------------------------------------------------------
# rejeicao i.i.d. p=50% pos-hoc -- mesma tecnica de
# `capital_ladder_copawin_2026_08_27.py` / `capital_dinamico_rerun_2026_08_27.
# py::rejeicao_p_alvo`, sem rerodar o motor (justificativa completa na
# docstring do modulo).
# ---------------------------------------------------------------------------

def _mascara(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random(n) < P_REJEICAO if n else np.array([], dtype=bool)


def n_zerou(trades: list, capital: float, n_sementes: int = N_SEMENTES,
            seed_base: int = SEED_BASE) -> int:
    """Quantas das `n_sementes` sementes tocam equity<=0 em algum ponto,
    partindo de `capital`. Pos-hoc, sem rerodar o motor."""
    if capital <= 0:
        return n_sementes
    n = len(trades)
    count = 0
    for s in range(n_sementes):
        aceita = _mascara(n, seed_base + s)
        acc = capital
        zerou = False
        for t, a in zip(trades, aceita):
            if not a:
                continue
            acc += t.pnl_brl
            if acc <= 0:
                zerou = True
                break
        if zerou:
            count += 1
    return count


def maxdd_sementes(trades: list, capital: float, n_sementes: int = N_SEMENTES,
                    seed_base: int = SEED_BASE) -> np.ndarray:
    """MaxDD (R$) por semente, curva reconstruida a partir de `capital`."""
    n = len(trades)
    out = np.empty(n_sementes)
    for s in range(n_sementes):
        aceita = _mascara(n, seed_base + s)
        curva = [capital]
        acc = capital
        for t, a in zip(trades, aceita):
            if not a:
                continue
            acc += t.pnl_brl
            curva.append(acc)
        out[s] = maxdd_brl(pd.Series(curva))
    return out


# ---------------------------------------------------------------------------
# busca binaria pelo menor capital seguro (identico a
# `capital_ladder_copawin_2026_08_27.py::busca_capital_minimo`)
# ---------------------------------------------------------------------------

def busca_capital_minimo(trades: list, piso_ingenuo: float) -> tuple[float, float]:
    """Devolve `(capital_minimo_seguro, ultimo_ponto_inseguro_conhecido)`.

    Monotonicidade (ver docstring do modulo): "zerou" e' nao-crescente em
    capital para uma sequencia de trades e sementes fixas -- garante que a
    bisseccao converge para o minimo correto."""
    if n_zerou(trades, piso_ingenuo) == 0:
        seguro = piso_ingenuo
        inseguro = 0.0
        cand = piso_ingenuo
        while cand > 1.0:
            cand2 = cand / 2.0
            if n_zerou(trades, cand2) == 0:
                seguro = cand2
                cand = cand2
            else:
                inseguro = cand2
                break
    else:
        inseguro = piso_ingenuo
        seguro = piso_ingenuo
        fator = 1.5
        guarda = 0
        while n_zerou(trades, seguro) > 0:
            inseguro = seguro
            seguro *= fator
            guarda += 1
            if guarda > 200:
                raise RuntimeError(
                    f"[capital_ladder_wdof1] busca para cima nao convergiu (inseguro={inseguro}, "
                    f"seguro={seguro}) -- travado apos {guarda} expansoes geometricas."
                )

    while (seguro - inseguro) > max(TOL_ABS_BRL, TOL_REL * seguro):
        meio = (inseguro + seguro) / 2.0
        if n_zerou(trades, meio) == 0:
            seguro = meio
        else:
            inseguro = meio

    seguro_arred = ARREDONDA_BRL * (int(seguro // ARREDONDA_BRL) + (1 if seguro % ARREDONDA_BRL else 0))
    if n_zerou(trades, seguro_arred) != 0:
        # salva-guarda: se o arredondamento (que so' pode subir) quebrar a
        # garantia por algum efeito de borda, sobe de ARREDONDA_BRL em
        # ARREDONDA_BRL ate' resolver, em vez de reportar um numero errado.
        while n_zerou(trades, seguro_arred) != 0:
            seguro_arred += ARREDONDA_BRL
    return seguro_arred, inseguro


# ---------------------------------------------------------------------------
# trade log (N=1) -- CSV (mesmas colunas de `capital_ladder_copawin_
# 2026_08_27.py::salva_trade_log`)
# ---------------------------------------------------------------------------

def salva_trade_log(trades: list, path: Path) -> None:
    campos = ["entry_ts", "exit_ts", "entry_price", "exit_price", "side",
              "quantity", "pnl_brl", "exit_reason"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(campos)
        for t in trades:
            w.writerow([
                t.entry_ts.isoformat(), t.exit_ts.isoformat(),
                t.entry_price, t.exit_price, t.side, t.quantity,
                t.pnl_brl, t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason),
            ])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    dias, tick_bars = GT.carregar_tick_bars()
    janela_desc = (f"{len(tick_bars)} ticks, {len(dias)} pregoes IS com tick disponivel "
                   f"({dias[0]} -> {dias[-1]}), subconjunto de 123 pregoes IS totais "
                   f"(cobertura tick a partir de 2026-02-27 no terminal MT5)")
    print(f"[capital_ladder_wdof1] {SYMBOL} -- resolucao TICK -- {janela_desc}")
    print(f"[capital_ladder_wdof1] candidato: T{G.CANDIDATO_PARAMS['profit_ticks']} "
          f"S{G.CANDIDATO_PARAMS['stop_ticks']} x{G.CANDIDATO_PARAMS['level_spacing_ticks']}, "
          f"quantity=N ESTATICO (margin_per_contract_brl=None)")
    print(f"[capital_ladder_wdof1] margem/contrato=R${num_br(MARGEM_CONTRATO_BRL,0)} | "
          f"MARGIN_BUFFER_FUTUROS={MARGIN_BUFFER_FUTUROS} | teto do MOTOR (fixo, todo N)={TETO_MOTOR_FIXO} | "
          f"teto OFICIAL Copa BTG (historico, NAO usado como teto do motor aqui)={TETO_OFICIAL_COPA_BTG}")
    print(f"[capital_ladder_wdof1] rejeicao i.i.d. p={num_br(P_REJEICAO*100,0)}%, {N_SEMENTES} sementes "
          f"(seed_base={SEED_BASE}), tolerancia de convergencia = max(R${num_br(TOL_ABS_BRL,0)}, "
          f"{num_br(TOL_REL*100,0)}%)\n")

    linhas: list[dict] = []

    for n in N_VALUES:
        resultado = roda_base(n, tick_bars)
        trades = list(resultado.trades)
        piso_ingenuo = n * MARGEM_CONTRATO_BRL * MARGIN_BUFFER_FUTUROS
        excede_teto_copa = n > TETO_OFICIAL_COPA_BTG

        if trades and any(t.quantity != n for t in trades):
            qtds = sorted({t.quantity for t in trades})
            print(f"    [diag][N={n}] AVISO: quantity dos trades nao e' uniformemente {n} -- "
                  f"valores observados: {qtds} (fill parcial por volume insuficiente?)")

        if n == 1:
            salva_trade_log(trades, TRADE_LOG_N1_CSV)
            print(f"[capital_ladder_wdof1] N=1: trade log salvo em {TRADE_LOG_N1_CSV} ({len(trades)} trades)")

        seguro, inseguro = busca_capital_minimo(trades, piso_ingenuo)
        razao = seguro / piso_ingenuo if piso_ingenuo else float("nan")
        dds = maxdd_sementes(trades, seguro)
        n_zerou_final = n_zerou(trades, seguro)

        linha = dict(
            n=n, trades=len(trades), piso_ingenuo_brl=piso_ingenuo,
            capital_minimo_seguro_brl=seguro, ultimo_inseguro_conhecido_brl=inseguro,
            razao=razao, maxdd_media_brl=float(dds.mean()),
            maxdd_std_brl=float(dds.std(ddof=1)) if len(dds) > 1 else 0.0,
            maxdd_pior_semente_brl=float(dds.max()),
            zerou_no_seguro=n_zerou_final,
            ordens_recusadas_por_teto=resultado.ordens_recusadas_por_teto,
            excede_teto_copa_btg=excede_teto_copa,
        )
        linhas.append(linha)

        aviso = "  [EXCEDE TETO OFICIAL COPA BTG=5]" if excede_teto_copa else ""
        print(f"N={n:>2} | trades={len(trades):>5} | recusadas_por_teto={resultado.ordens_recusadas_por_teto} | "
              f"piso ingenuo=R${num_br(piso_ingenuo,0):>9} | "
              f"capital minimo seguro=R${num_br(seguro,0):>10} | razao={num_br(razao,2)}x | "
              f"MaxDD@seguro=R${num_br(float(dds.mean()),0)} +/- R${num_br(float(dds.std(ddof=1)) if len(dds)>1 else 0.0,0)} "
              f"(pior semente=R${num_br(float(dds.max()),0)}) | "
              f"zerou@seguro={n_zerou_final}/{N_SEMENTES} (deve ser 0){aviso}", flush=True)

    RESULT_JSON.write_text(json.dumps({
        "symbol": SYMBOL, "resolucao": "tick",
        "candidato_params": G.CANDIDATO_PARAMS,
        "margem_contrato_brl": MARGEM_CONTRATO_BRL,
        "margin_buffer_futuros": MARGIN_BUFFER_FUTUROS, "teto_motor_fixo": TETO_MOTOR_FIXO,
        "teto_oficial_copa_btg_historico": TETO_OFICIAL_COPA_BTG,
        "n_sementes": N_SEMENTES, "p_rejeicao": P_REJEICAO, "seed_base": SEED_BASE,
        "tol_abs_brl": TOL_ABS_BRL, "tol_rel": TOL_REL, "arredonda_brl": ARREDONDA_BRL,
        "janela": janela_desc,
        "resultados": linhas,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[capital_ladder_wdof1] resultado agregado salvo em {RESULT_JSON}")

    print("\n\n=== ESCADA DE CAPITAL -- WdoGridReloadMaker F1 (WDO@), ESTATICO, IN-SAMPLE (TICK) ===")
    print(f"{'N':>3}{'piso ingenuo':>16}{'capital minimo seguro':>24}{'razao':>10}"
          f"{'trades':>10}{'MaxDD@seguro':>26}{'':>10}")
    print("-" * 100)
    for l in linhas:
        aviso = " *" if l["excede_teto_copa_btg"] else ""
        print(f"{l['n']:>3}{('R$'+num_br(l['piso_ingenuo_brl'],0)):>16}"
              f"{('R$'+num_br(l['capital_minimo_seguro_brl'],0)):>24}{num_br(l['razao'],2)+'x':>10}"
              f"{l['trades']:>10}"
              f"{('R$'+num_br(l['maxdd_media_brl'],0)+' +/- R$'+num_br(l['maxdd_std_brl'],0)):>26}"
              f"{aviso:>10}")
    print("* excede o teto OFICIAL da Copa BTG para WDO@ (5 contratos, profiles.py:235) -- "
          "regra especifica da competicao ja encerrada, NAO um limite fisico.")


if __name__ == "__main__":
    main()
