"""Frente F1-wdo-consolidacao, RODADA 3 -- bateria completa (teste de
metade + nulo sign-flip + curva de pedagio) na leitura TICK do candidato
"T1 S16 x1", no SUBCONJUNTO do IS onde ha' tick history no terminal MT5
(Rico): 72 dos 123 pregoes IS, 2026-02-27..2026-06-12. Ver
`wdo_grid_reload_f1_tick_probe.py` para a checagem de viabilidade
(cobertura de tick, 58,5% do IS) e o resultado headline ja' confirmado la':

    R$/pregao -- tick: 156,02 | M1 (mesmos 72 dias): 14,96 | ballpark
    conhecido (123 pregoes completos, fora deste repo): 305,74
    win rate -- tick: 99,4% | M1: 89,3% | breakeven da razao 1:16: ~94,1%

AVISO 2026-09-07 -- os numeros citados acima (e todos os deste arquivo) sao
de uma janela TRUNCADA. `buscar_ticks`, que este modulo importa do probe,
pedia a janela errada ao terminal e rotulava o resultado 3h cedo: cada
pregao vinha das 14:58 as 18:29 (3h31 de um pregao de 9h30). A funcao foi
corrigida -- ler o AVISO no topo de `wdo_grid_reload_f1_tick_probe.py` --
mas NADA aqui foi re-rodado, entao nenhum numero deste cabecalho e'
reproduzivel pelo codigo atual.

RESSALVA que se aplica a CADA numero deste arquivo, sem excecao: e' um
subconjunto de 58,5% do IS (faltam os 51 PRIMEIROS pregoes, sem tick
history retido pelo terminal/corretora) -- nada aqui e' "o candidato IS
completo". E' o teste da hipotese de RESOLUCAO (M1 subconta toques porque
`on_bar` so' reagenda apos ficar flat, tick nao) no subconjunto onde ela e'
testavel, seguindo o criterio de decisao explicito da missao desta rodada:
tick chegou a 51,0% do ballpark diario (ordem de grandeza da mesma faixa,
NAO a mesma faixa de -90%+ de desvio que M1 mostrava) -- isso aciona
"reporte o numero tick e refaca teste de metade + nulo + curva de pedagio
nessa nova leitura antes de declarar candidato", nao a saida REFUTADA.

## Otimizacao deliberada no item 4 (pedagio) -- leia antes de desconfiar do metodo

O motor marca patrimonio a CADA barra (`engine.py`: `equity_index.append(ts)`
dentro do loop por linha de `session_df`) -- numa run tick isso e' um ponto
de equity por NEGOCIO, nao por minuto: 72 pregoes = ~2,8 milhoes de pontos,
ordens de grandeza mais caro que M1 (570 barras/pregao). Rodar os 6 niveis
de pedagio como 6 reruns completos (como `wdo_grid_reload_f1_lab.py` faz
para M1) multiplicaria o tempo de execucao por 6x sobre um dataset ja'
muito mais pesado.

Em vez disso, uma UNICA run (a `headline`, pedagio=0) basta para os 6
niveis, porque o pedagio SO' entra no modelo de custo -- nunca na decisao
de entrada/saida: esta config nao usa `session_stop_brl` (None, default
desta frente) nem gate de capital minimo (`enforce_capital_minimo=False`,
documentado em `wdo_grid_reload_f1_lab.py`), entao a SEQUENCIA de trades e'
identica para qualquer pedagio -- so' o `fees_total` de cada trade muda, e
`IntradayTrade.pnl_brl` e' `gross - fees_total` (propriedade pura, ver
`machine.py`). `montar_config(pedagio_ticks=p)` soma
`p * tick_size * point_value_brl * pernas_maker` ao `fee_round_trip_brl`
de FORMA UNIFORME (mesmo valor pra todo trade, vencedor ou nao, TODO
round-trip, inclusive saida por stop -- "overcounting deliberado e
CONSERVADOR" ja documentado la'). Logo:

    pnl_brl_i(p) = pnl_brl_i(0) - extra_por_trade(p)      [TODO trade i]
    extra_por_trade(p) = (custos com pedagio=p).fee_round_trip_brl
                        - (custos com pedagio=0).fee_round_trip_brl

liquido/win%/trades/R$-por-dia para qualquer p saem exatos (nao
aproximados) recalculando so' isso, sem tocar o motor de novo. O MaxDD
tambem e' reconstruido exatamente (nao aproximado): a curva de patrimonio
original menos o custo extra ACUMULADO ate' cada timestamp -- uma funcao
DEGRAU que so' desce no instante em que cada trade FECHA (`exit_ts`), pelo
mesmo argumento (a parte nao-realizada da equity entre fechamentos nao
depende de custo). Isto e' VALIDADO (nao so' afirmado): `validar_projecao`
roda o motor de verdade em pedagio=0,3 e compara numero a numero (liquido,
trades, win%, MaxDD R$) contra a projecao analitica para o MESMO pedagio.

Uso: `python -u scripts/daytrade/wdo_grid_reload_f1_tick_lab.py`
"""
from __future__ import annotations

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

from backtest.intraday.machine import IntradayTrade  # noqa: E402
from backtest.intraday.report import (  # noqa: E402
    LinhaResultado,
    cabecalho,
    linha,
    linha_de_resultado,
    maxdd_brl,
    num_br,
)
from wdo_grid_reload_f1_lab import (  # noqa: E402
    BALLPARK_IS_LIQUIDO_BRL,
    CAPITAL_NOCIONAL,
    montar_config,
    rodar,
)
from wdo_grid_reload_f1_tick_probe import (  # noqa: E402
    buscar_ticks,
    dias_is_com_tick_disponivel,
)

BALLPARK_POR_PREGAO_BRL = BALLPARK_IS_LIQUIDO_BRL / 123.0


# ---------------------------------------------------------------------------
# 1. carregar tick bars (uma vez so') + rodar headline
# ---------------------------------------------------------------------------

def carregar_tick_bars() -> tuple[list, pd.DataFrame]:
    _locked_m1, dias, m1_subset = dias_is_com_tick_disponivel()
    print(f"[tick_lab] {len(dias)} pregoes IS com tick disponivel "
          f"({dias[0]} -> {dias[-1]}) de 123 pregoes IS totais.")
    tick_bars = buscar_ticks(dias, m1_subset)
    print(f"[tick_lab] {len(tick_bars)} ticks baixados, "
          f"{tick_bars.index.min()} -> {tick_bars.index.max()}")
    return dias, tick_bars


def _pregoes(bars: pd.DataFrame) -> int:
    return len(set(bars.index.date))


# ---------------------------------------------------------------------------
# 2. teste de metade (dentro do subconjunto tick)
# ---------------------------------------------------------------------------

def teste_de_metade(dias: list, tick_bars: pd.DataFrame) -> None:
    print("\n=== 2. teste de metade (dentro do SUBCONJUNTO tick, 72 pregoes) ===")
    corte = dias[len(dias) // 2]
    primeira = tick_bars[[d < corte for d in tick_bars.index.date]]
    segunda = tick_bars[[d >= corte for d in tick_bars.index.date]]
    print(f"1a metade: {_pregoes(primeira)} pregoes, {primeira.index.min()} -> {primeira.index.max()}")
    print(f"2a metade: {_pregoes(segunda)} pregoes, {segunda.index.min()} -> {segunda.index.max()}")
    cfg = montar_config()
    r1 = rodar(primeira, cfg)
    r2 = rodar(segunda, cfg)
    linhas = [
        linha_de_resultado("1a metade (tick)", r1, CAPITAL_NOCIONAL, capital_nocional=True),
        linha_de_resultado("2a metade (tick)", r2, CAPITAL_NOCIONAL, capital_nocional=True),
    ]
    print(cabecalho())
    for item in linhas:
        print(linha(item))
    ambas_positivas = all(item.liquido_brl > 0 for item in linhas)
    print(f"as duas metades positivas com o MESMO candidato (T1 S16 x1, leitura tick)? {ambas_positivas}")


# ---------------------------------------------------------------------------
# 3. nulo por sign-flip (a partir da run headline, ja rodada em main())
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DiaPnL:
    bruto: float
    custo: float


def _pnl_diario(trades: list[IntradayTrade]) -> list[_DiaPnL]:
    por_dia: dict = {}
    for t in trades:
        dia = pd.Timestamp(t.exit_ts).date()
        bruto_trade = t.pnl_brl + t.fees_total
        custo_trade = -t.fees_total
        b, c = por_dia.get(dia, (0.0, 0.0))
        por_dia[dia] = (b + bruto_trade, c + custo_trade)
    return [_DiaPnL(bruto=b, custo=c) for b, c in por_dia.values()]


def nulo_sign_flip(trades: list[IntradayTrade], n_sementes: int = 5,
                    draws_por_semente: int = 5000) -> None:
    print("\n=== 3. nulo por sign-flip (leitura tick, formula correta) ===")
    dias_pnl = _pnl_diario(trades)
    if not dias_pnl:
        print("sem trades -- nulo nao computavel.")
        return
    brutos = np.array([d.bruto for d in dias_pnl])
    custos = np.array([d.custo for d in dias_pnl])
    liquido_real = float(brutos.sum() + custos.sum())
    custo_total = float(custos.sum())
    print(f"{len(dias_pnl)} pregoes com trade. liquido real = R${num_br(liquido_real)}; "
          f"custo total pago = R${num_br(custo_total)}")

    percentis: list[float] = []
    for semente in range(n_sementes):
        rng = np.random.default_rng(semente)
        sinais = rng.choice([-1.0, 1.0], size=(draws_por_semente, len(dias_pnl)))
        sintetico = sinais @ brutos + custo_total
        percentil = float((sintetico <= liquido_real).mean() * 100.0)
        percentis.append(percentil)
    percentis_arr = np.array(percentis)
    print(f"percentil do liquido real na distribuicao nula, por semente: "
          + ", ".join(num_br(p, 1) + "%" for p in percentis_arr))
    print(f"media entre {n_sementes} sementes = {num_br(percentis_arr.mean(), 1)}% "
          f"(min {num_br(percentis_arr.min(), 1)}%, max {num_br(percentis_arr.max(), 1)}%, "
          f"desvio {num_br(percentis_arr.std(), 1)}pp, n_draws/semente={draws_por_semente})")


# ---------------------------------------------------------------------------
# 4. curva de pedagio -- projecao analitica a partir da run headline
# ---------------------------------------------------------------------------

def extra_por_trade(pedagio_ticks: float) -> float:
    """R$ extra por trade (TODO round-trip) para um dado `pedagio_ticks`,
    lido DIRETO de `montar_config` (nao hardcoded) -- mesma formula que a
    config real aplicaria, so' que fora do motor."""
    base = montar_config(pedagio_ticks=0.0).costs.fee_round_trip_brl
    com_pedagio = montar_config(pedagio_ticks=pedagio_ticks).costs.fee_round_trip_brl
    return com_pedagio - base


def projetar_pedagio(headline_result, capital_nocional: float, pedagio_ticks: float) -> LinhaResultado:
    trades: list[IntradayTrade] = list(headline_result.trades)
    extra = extra_por_trade(pedagio_ticks)
    pnl_ajustado = np.array([t.pnl_brl - extra for t in trades])
    liquido = float(pnl_ajustado.sum())
    vencedores = int((pnl_ajustado > 0).sum())
    win_rate = (100.0 * vencedores / len(trades)) if trades else 0.0
    pregoes = _pregoes_de_trades(trades)

    # MaxDD reconstruido: equity original menos custo extra ACUMULADO ate'
    # cada timestamp (degrau, um por trade FECHADO em `exit_ts`).
    equity0 = headline_result.equity_curve
    if equity0 is not None and not equity0.empty and trades:
        exit_arr = np.sort(pd.DatetimeIndex([t.exit_ts for t in trades]).values)
        idx_arr = equity0.index.values
        contagem = np.searchsorted(exit_arr, idx_arr, side="right")
        equity_ajustada = pd.Series(equity0.values - contagem * extra, index=equity0.index)
        dd = maxdd_brl(equity_ajustada)
    else:
        dd = 0.0

    return LinhaResultado(
        variante=f"pedagio {num_br(pedagio_ticks, 2)} tick (projetado)",
        liquido_brl=liquido, maxdd_brl=dd, win_rate_pct=win_rate,
        trades=len(trades), pregoes=pregoes,
        extras={"pedagio_ticks": num_br(pedagio_ticks, 2)},
    )


def _pregoes_de_trades(trades: list[IntradayTrade]) -> int:
    return len(set(pd.Timestamp(t.exit_ts).date() for t in trades))


def validar_projecao(tick_bars: pd.DataFrame, headline_result) -> bool:
    """Roda o motor DE VERDADE em pedagio=0,3 tick e compara contra a
    projecao analitica para o MESMO pedagio -- prova (nao so' afirma) que
    o atalho do item 4 e' exato, nao aproximado."""
    print("\n--- validacao da projecao analitica (rerun real em pedagio=0,3 tick) ---")
    p = 0.3
    cfg_real = montar_config(pedagio_ticks=p)
    resultado_real = rodar(tick_bars, cfg_real)
    real = linha_de_resultado(f"pedagio {num_br(p,2)} tick (RERUN REAL)", resultado_real,
                               CAPITAL_NOCIONAL, capital_nocional=True)
    projetado = projetar_pedagio(headline_result, CAPITAL_NOCIONAL, p)
    print(cabecalho(("pedagio_ticks",)))
    print(linha(real, ("pedagio_ticks",)))
    print(linha(projetado, ("pedagio_ticks",)))
    liquido_ok = abs(real.liquido_brl - projetado.liquido_brl) < 0.01
    trades_ok = real.trades == projetado.trades
    win_ok = abs(real.win_rate_pct - projetado.win_rate_pct) < 0.05
    dd_ok = abs(real.maxdd_brl - projetado.maxdd_brl) < 1.0
    print(f"liquido bate: {liquido_ok} | trades bate: {trades_ok} | "
          f"win% bate: {win_ok} | MaxDD R$ bate (tol R$1): {dd_ok}")
    return liquido_ok and trades_ok and win_ok and dd_ok


def curva_de_pedagio(headline_result, valida: bool,
                      grade: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)) -> None:
    print(f"\n=== 4. curva de pedagio de fila (leitura tick, PROJETADA a partir da headline"
          f"{' -- validada acima' if valida else ' -- SEM validacao (nao confie sem checar)'}) ===")
    linhas = [projetar_pedagio(headline_result, CAPITAL_NOCIONAL, p) for p in grade]
    print(cabecalho(("pedagio_ticks",)))
    for item in linhas:
        print(linha(item, ("pedagio_ticks",)))

    pontos = [(p, item.liquido_brl) for p, item in zip(grade, linhas)]
    ponto_morte = None
    for (p0, l0), (p1, l1) in zip(pontos, pontos[1:]):
        if l0 > 0 >= l1:
            frac = l0 / (l0 - l1) if (l0 - l1) != 0 else 0.0
            ponto_morte = p0 + frac * (p1 - p0)
            break
    if ponto_morte is None:
        if pontos[0][1] <= 0:
            print("ja nasce negativo mesmo com pedagio 0 -- sem ponto de morte a reportar.")
        else:
            print(f"nao morreu dentro da grade testada (positivo ate {pontos[-1][0]} tick/perna).")
        return
    preenchimento_minimo = 1.0 - ponto_morte
    print(f"ponto de morte (interpolado): ~{num_br(ponto_morte, 2)} tick/perna maker")
    print(f"traduzido em preenchimento passivo minimo necessario (1 - pedagio_ticks): "
          f"~{num_br(preenchimento_minimo * 100.0, 1)}%")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    dias, tick_bars = carregar_tick_bars()
    n_pregoes = len(dias)

    print(f"\n=== 1. headline (leitura tick, {n_pregoes} pregoes disponiveis de 123 IS) ===")
    cfg = montar_config()
    headline = rodar(tick_bars, cfg)
    item = linha_de_resultado(f"wdo_grid_reload T1 S16 x1 (TICK, {n_pregoes}/123 pregoes IS)",
                               headline, CAPITAL_NOCIONAL, capital_nocional=True)
    print(cabecalho())
    print(linha(item))
    taxa = item.liquido_brl / n_pregoes if n_pregoes else 0.0
    print(f"R$/pregao: {num_br(taxa)}  |  ballpark conhecido (123 pregoes completos): "
          f"{num_br(BALLPARK_POR_PREGAO_BRL)}  |  fracao do ballpark diario: "
          f"{num_br(100.0 * taxa / BALLPARK_POR_PREGAO_BRL, 1)}%")

    teste_de_metade(dias, tick_bars)
    nulo_sign_flip(list(headline.trades))
    ok = validar_projecao(tick_bars, headline)
    curva_de_pedagio(headline, valida=ok)

    print("\n=== 5. tabela padrao (linha unica, candidato completo, leitura tick, config padrao) ===")
    print(cabecalho())
    print(linha(item))


if __name__ == "__main__":
    main()
