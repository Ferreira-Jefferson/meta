"""Frente F4-wdo-geometria-sessao (2026-08-26) -- varredura de geometria do
grid-maker no WDO@, IN-SAMPLE (< `backtest.intraday.profiles.OOS_CUTOFF`,
NUNCA `.unlock(...)` chamado aqui).

O QUE ESTE SCRIPT RESPONDE (missao da rodada):
  1. Alvo T diferente de 1 tick (2, 3, 4) sobre a mesma grade de
     stop/espacamento -- confirma se T=1 realmente vence e por que.
  2. O edge se concentra em algum horario do pregao ou e' uniforme.
  3. Multiplos niveis "simultaneos" (rodizio de distancia -- ver a ressalva
     estrutural abaixo) ajudam ou so' produzem mais trades no mesmo edge.

DUAS MECANICAS testadas lado a lado, porque o script que mediu o candidato
citado na missao ("T1 S16 x1", +R$37.606,53) NAO esta neste repositorio --
procurado (`grep` por "37606", "S16", nomes de arquivo "*wdo*") e nao
encontrado. Ele so' pode ter sido produzido numa sessao anterior nao
persistida aqui. Em vez de adivinhar um unico jeito de reproduzir o numero
(e arriscar recortar a busca em torno de um alvo, o erro que a nota
`feedback_sem_antolhos` do dono adverte), este script mede as DUAS
variantes que a familia `gremah` ja documenta como polos opostos --
`grid_reload_maker` (nivel FIXO na abertura da sessao) e a fase ROLANTE de
`Gremah.on_bar` (ancora = `bar.close`, reancora por estagnacao) -- ver
`strategy/daytrade/lab/wdo_geo_grid_reload.py` e
`wdo_geo_grid_rolling.py` para a adaptacao de cada uma ao tick de PONTOS do
futuro.

RESSALVA ESTRUTURAL (lida no motor antes de escrever isto):
`IntradaySessionMachine.resting_limit` (src/backtest/intraday/machine.py)
e' um campo SINGULAR, nao uma lista -- o motor nunca tem duas ordens-limite
penduradas ao mesmo tempo. `n_levels` das duas estrategias testa RODIZIO de
distancia (a proxima recarga usa a distancia seguinte, nao sempre a mesma),
nao niveis simultaneos de verdade. Simular concorrencia real exigiria
editar `machine.py` para `resting_limit` virar lista -- fora do escopo
desta frente (arquivo compartilhado, dono e' a Frente F0).

DISCIPLINA (AGENTS.md desta rodada):
- Custo (R$0,50/contrato round-trip) e slippage (1 tick, so' nas pernas a
  MERCADO -- o stop de protecao) SEMPRE aplicados no numero principal.
- Pedagio de fila (`pedagio_ticks`, mesmo padrao de `scripts/daytrade/
  copa_lab.py::config`) testado a parte, lado a lado, nunca escondido --
  ver a FASE 3.
- IS/OOS travado por `LockedBars`; so' `.in_sample()` chamado.
- Teste de metade + nulo sign-flip (formula correta: `s_d*bruto_d -
  custo_d`, NUNCA `s_d*liquido_d`) no candidato final.

Uso:
    python scripts/daytrade/wdo_geo_sweep.py --jobs 10
    python scripts/daytrade/wdo_geo_sweep.py --fase grade     # so' a grade principal
    python scripts/daytrade/wdo_geo_sweep.py --fase tudo      # default
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.costs import IntradayCostModel  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import (  # noqa: E402
    LinhaResultado, linha_de_resultado, maxdd_brl, num_br, tabela,
)
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.wdo_geo_grid_reload import WdoGeoGridReload  # noqa: E402
from strategy.daytrade.lab.wdo_geo_grid_rolling import WdoGeoGridRolling  # noqa: E402

SYMBOL = "WDO@"
MIN_BARRAS_POR_PREGAO = 400  # ver copa_lab.py: meio pregao nao e' um pregao
CAPITAL_NOCIONAL = 1_000_000.0
#: Fallback declarado (mesmo numero de `copa_lab._ECONOMIA_CONHECIDA`) --
#: roda sem MT5 aberto. point_value_brl = 0.01/0.001 = 10.0 R$/ponto, o
#: numero conhecido do WDO (`profiles.py` confirma na tabela de medicao).
ECONOMIA_WDO = (0.01, 0.001)
EXTRAS = ("mecanica", "T", "S", "espac", "niveis", "reancora")


# ---------------------------------------------------------------- dados ----

@lru_cache(maxsize=1)
def _bars_is() -> pd.DataFrame:
    df = load_m1(SYMBOL).sort_index()
    profile = profile_for(SYMBOL)
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(df, split)
    is_bars = locked.in_sample()
    counts = is_bars.groupby(is_bars.index.date).size()
    completos = {d for d, n in counts.items() if n >= MIN_BARRAS_POR_PREGAO}
    return is_bars[[d in completos for d in is_bars.index.date]]


def _metade(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide o IS em duas metades CRONOLOGICAS por numero de pregoes (nao
    por linha) -- pregoes tem numero de barras desigual, dividir por linha
    deixaria uma metade com mais dias que a outra."""
    dias = sorted(set(bars.index.date))
    corte = dias[len(dias) // 2]
    primeira = bars[[d < corte for d in bars.index.date]]
    segunda = bars[[d >= corte for d in bars.index.date]]
    return primeira, segunda


@lru_cache(maxsize=1)
def _base_config() -> IntradayBacktestConfig:
    profile = profile_for(SYMBOL)
    return config_for(
        profile, trade_tick_value=ECONOMIA_WDO[0], trade_tick_size=ECONOMIA_WDO[1],
        initial_capital=CAPITAL_NOCIONAL, target_fills_as_maker=True, max_open_contracts=4,
    )


def _config_com_pedagio(pedagio_ticks: float = 0.0, pernas_maker: int = 2) -> IntradayBacktestConfig:
    """`pernas_maker=2` por padrao: entrada (`EnterLimit`) E alvo
    (`initial_target`, `target_fills_as_maker=True`) sao as DUAS pernas
    maker deste desenho -- o stop de protecao e' a mercado e ja paga
    slippage, nao pedagio de fila."""
    cfg = _base_config()
    if not pedagio_ticks:
        return cfg
    extra = pedagio_ticks * cfg.costs.tick_size * cfg.costs.point_value_brl * pernas_maker
    custos = IntradayCostModel(
        point_value_brl=cfg.costs.point_value_brl, tick_size=cfg.costs.tick_size,
        fee_round_trip_brl=cfg.costs.fee_round_trip_brl + extra,
        slippage_ticks=cfg.costs.slippage_ticks, exchange_fee_pct_per_leg=0.0,
    )
    return IntradayBacktestConfig(
        costs=custos, initial_capital=cfg.initial_capital, default_quantity=cfg.default_quantity,
        session_end_time=cfg.session_end_time, session_end_policy=cfg.session_end_policy,
        target_fills_as_maker=True, limit_fill_capped_by_volume=cfg.limit_fill_capped_by_volume,
        enforce_capital_minimo=cfg.enforce_capital_minimo, max_open_contracts=cfg.max_open_contracts,
    )


def _monta_robo(mechanic: str, tick_size: float, T: int, S: int, spacing: int,
                 n_levels: int, reanchor_bars: int):
    if mechanic == "reload":
        return WdoGeoGridReload(symbol=SYMBOL, tick_size=tick_size, level_spacing_ticks=spacing,
                                 profit_ticks=T, stop_ticks=S, n_levels=n_levels, quantity=1)
    if mechanic == "rolling":
        return WdoGeoGridRolling(symbol=SYMBOL, tick_size=tick_size, level_spacing_ticks=spacing,
                                  profit_ticks=T, stop_ticks=S, n_levels=n_levels,
                                  rolling_reanchor_after_bars=reanchor_bars, quantity=1)
    raise ValueError(f"mecanica desconhecida: {mechanic!r}")


def _variante(mechanic: str, T: int, S: int, spacing: int, n_levels: int, reanchor_bars: int) -> str:
    sufixo = f"L{n_levels}" if n_levels > 1 else ""
    base = f"{mechanic[:4]} T{T} S{S} sp{spacing}{sufixo}"
    if mechanic == "rolling":
        base += f" r{reanchor_bars}"
    return base


@dataclass(frozen=True)
class Celula:
    """Uma celula da grade + o `IntradayBacktestResult` cru (guardado so'
    para a celula CAMPEA -- ver `main()` -- as demais descartam o objeto
    pesado depois de extrair `LinhaResultado`, para nao acumular milhares
    de `IntradayTrade` de toda a grade em memoria ao mesmo tempo)."""

    mechanic: str
    T: int
    S: int
    spacing: int
    n_levels: int
    reanchor_bars: int
    pedagio_ticks: float
    linha: LinhaResultado


def _rodar_celula(mechanic: str, T: int, S: int, spacing: int, n_levels: int = 1,
                   reanchor_bars: int = 1, pedagio_ticks: float = 0.0) -> Celula:
    bars = _bars_is()
    cfg = _config_com_pedagio(pedagio_ticks)
    strat = _monta_robo(mechanic, cfg.costs.tick_size, T, S, spacing, n_levels, reanchor_bars)
    resultado = run_intraday_backtest(bars, strat, cfg)
    linha = linha_de_resultado(
        _variante(mechanic, T, S, spacing, n_levels, reanchor_bars), resultado,
        CAPITAL_NOCIONAL, capital_nocional=True,
        extras={
            "mecanica": mechanic, "T": str(T), "S": str(S), "espac": str(spacing),
            "niveis": str(n_levels), "reancora": str(reanchor_bars) if mechanic == "rolling" else "-",
        },
    )
    return Celula(mechanic=mechanic, T=T, S=S, spacing=spacing, n_levels=n_levels,
                  reanchor_bars=reanchor_bars, pedagio_ticks=pedagio_ticks, linha=linha)


# ------------------------------------------------------------- fase 1/2: grade principal ----

def _grade_reload() -> list[tuple]:
    return [
        ("reload", T, S, spacing, 1, 1)
        for T in (1, 2, 3, 4)
        for S in (8, 12, 16, 20, 24, 32)
        for spacing in (8, 16, 32)
    ]


def _grade_rolling() -> list[tuple]:
    return [
        ("rolling", T, S, spacing, 1, 1)
        for T in (1, 2, 3, 4)
        for S in (8, 16, 32)
        for spacing in (1, 2, 4, 8, 16, 32)
    ]


def _roda_lote(unidades: list[tuple], jobs: int, rotulo: str) -> list[Celula]:
    max_workers = jobs or min(len(unidades), os.cpu_count() or 4)
    print(f"\n[{rotulo}] {len(unidades)} celula(s) em ate {max_workers} processo(s)...", flush=True)
    celulas: list[Celula] = []
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_rodar_celula, *u): u for u in unidades}
        feitas = 0
        for future in as_completed(futures):
            u = futures[future]
            try:
                c = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"[{rotulo}] FALHOU {u}: {type(exc).__name__}: {exc}", flush=True)
                continue
            celulas.append(c)
            feitas += 1
            if feitas % 20 == 0 or feitas == len(unidades):
                print(f"[{rotulo}] {feitas}/{len(unidades)} prontas...", flush=True)
    return celulas


def _imprime_top(celulas: list[Celula], n: int, titulo: str) -> None:
    ordenadas = sorted(celulas, key=lambda c: c.linha.liquido_brl, reverse=True)[:n]
    print(f"\n=== {titulo} (top {len(ordenadas)} por liquido R$) ===")
    print(tabela([c.linha for c in ordenadas], extras=EXTRAS, largura_extra=9))


def _imprime_surface_por_T(celulas: list[Celula], mechanic: str) -> None:
    print(f"\n=== Superficie completa -- mecanica={mechanic} (mediana de liquido R$ por T, "
          f"agregando todos os S/espacamento testados) ===")
    for T in sorted({c.T for c in celulas if c.mechanic == mechanic}):
        valores = [c.linha.liquido_brl for c in celulas if c.mechanic == mechanic and c.T == T]
        positivos = sum(1 for v in valores if v > 0)
        print(f"  T={T}: n={len(valores):3d}  mediana={num_br(statistics.median(valores),2):>12}  "
              f"min={num_br(min(valores),2):>12}  max={num_br(max(valores),2):>12}  "
              f"positivas={positivos}/{len(valores)}")


# ------------------------------------------------------------- fase 3: pedagio ----

def _fase_pedagio(top: list[Celula], jobs: int) -> list[Celula]:
    unidades = [(c.mechanic, c.T, c.S, c.spacing, c.n_levels, c.reanchor_bars) for c in top]
    print(f"\n[pedagio] reavaliando {len(unidades)} celula(s) do topo com 1 tick de pedagio "
          f"por perna maker (entrada + alvo)...")
    com_pedagio = []
    max_workers = jobs or min(len(unidades), os.cpu_count() or 4)
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_rodar_celula, mech, T, S, sp, nl, rb, 1.0): (mech, T, S, sp, nl, rb)
            for mech, T, S, sp, nl, rb in unidades
        }
        for future in as_completed(futures):
            com_pedagio.append(future.result())

    print(f"\n=== Sensibilidade a pedagio de fila (1 tick/perna, 2 pernas) -- lado a lado ===")
    linhas = []
    by_key = {(c.mechanic, c.T, c.S, c.spacing, c.n_levels, c.reanchor_bars): c for c in com_pedagio}
    for c0 in sorted(top, key=lambda c: c.linha.liquido_brl, reverse=True):
        key = (c0.mechanic, c0.T, c0.S, c0.spacing, c0.n_levels, c0.reanchor_bars)
        c1 = by_key[key]
        sobrevive = "SOBREVIVE" if c1.linha.liquido_brl > 0 else "morre"
        print(f"  {c0.linha.variante:<26} sem_pedagio={num_br(c0.linha.liquido_brl,2):>12}  "
              f"com_pedagio={num_br(c1.linha.liquido_brl,2):>12}   [{sobrevive}]")
        linhas.append(c1)
    return com_pedagio


# ------------------------------------------------------------- fase 4: horario ----

_BUCKETS_BRT = [
    ("abertura 09-10h", 9, 10),
    ("manha 10-12h", 10, 12),
    ("tarde 12-15h", 12, 15),
    ("fechamento 15-18h30", 15, 19),
]


def _fase_horario(mechanic: str, T: int, S: int, spacing: int, n_levels: int, reanchor_bars: int) -> None:
    bars = _bars_is()
    cfg = _config_com_pedagio(0.0)
    strat = _monta_robo(mechanic, cfg.costs.tick_size, T, S, spacing, n_levels, reanchor_bars)
    resultado = run_intraday_backtest(bars, strat, cfg)
    trades = resultado.trades
    print(f"\n=== Segmentacao por horario de sessao (BRT) -- "
          f"{_variante(mechanic, T, S, spacing, n_levels, reanchor_bars)}, {len(trades)} trades ===")
    if not trades:
        print("  sem trades.")
        return
    horas_brt = [pd.Timestamp(t.entry_ts).tz_convert("America/Sao_Paulo").hour for t in trades]
    for rotulo, h0, h1 in _BUCKETS_BRT:
        sel = [t for t, h in zip(trades, horas_brt) if h0 <= h < h1]
        if not sel:
            print(f"  {rotulo:<22} 0 trades")
            continue
        liquido = sum(t.pnl_brl for t in sel)
        vencedores = sum(1 for t in sel if t.pnl_brl > 0)
        print(f"  {rotulo:<22} n={len(sel):5d} ({100.0*len(sel)/len(trades):5.1f}%)  "
              f"liquido={num_br(liquido,2):>12}  win%={num_br(100.0*vencedores/len(sel),1):>6}  "
              f"R$/trade={num_br(liquido/len(sel),3):>8}")


# ------------------------------------------------------------- fase 5: niveis ----

def _fase_niveis(mechanic: str, T: int, S: int, spacing: int, reanchor_bars: int, jobs: int) -> None:
    unidades = [(mechanic, T, S, spacing, nl, reanchor_bars) for nl in (1, 2, 3, 4)]
    celulas = _roda_lote(unidades, jobs, f"niveis-{mechanic}")
    celulas.sort(key=lambda c: c.n_levels)
    print(f"\n=== Rodizio de niveis (n_levels) -- {mechanic} T{T} S{S} sp{spacing} ===")
    print(tabela([c.linha for c in celulas], extras=EXTRAS, largura_extra=9))


# ------------------------------------------------------------- fase 6: metade ----

def _fase_metade(top: list[Celula], jobs: int) -> None:
    bars = _bars_is()
    primeira, segunda = _metade(bars)
    d1 = sorted(set(primeira.index.date))
    d2 = sorted(set(segunda.index.date))
    print(f"\n[metade] 1a metade: {len(d1)} pregoes ({d1[0]}..{d1[-1]}); "
          f"2a metade: {len(d2)} pregoes ({d2[0]}..{d2[-1]})")

    def _roda_em(bars_sub: pd.DataFrame, c: Celula) -> float:
        cfg = _config_com_pedagio(0.0)
        strat = _monta_robo(c.mechanic, cfg.costs.tick_size, c.T, c.S, c.spacing, c.n_levels, c.reanchor_bars)
        resultado = run_intraday_backtest(bars_sub, strat, cfg)
        return sum(t.pnl_brl for t in resultado.trades)

    linhas = []
    for c in top:
        liq1 = _roda_em(primeira, c)
        liq2 = _roda_em(segunda, c)
        linhas.append((c, liq1, liq2))

    linhas.sort(key=lambda x: x[1], reverse=True)
    campea_1a_metade = linhas[0]
    print(f"\n=== Teste de metade (top {len(linhas)} candidatas, ranking pela 1a metade) ===")
    print(f"{'variante':<26}{'liquido 1a met.':>16}{'liquido 2a met.':>16}{'rank na 2a':>12}")
    ranking_2a = sorted(linhas, key=lambda x: x[2], reverse=True)
    rank_2a_de = {id(item[0]): i + 1 for i, item in enumerate(ranking_2a)}
    for c, liq1, liq2 in linhas:
        marca = " <- campea na 1a metade" if c is campea_1a_metade[0] else ""
        print(f"{c.linha.variante:<26}{num_br(liq1,2):>16}{num_br(liq2,2):>16}"
              f"{rank_2a_de[id(c)]:>12}{marca}")
    print(f"\nCampea na 1a metade ({campea_1a_metade[0].linha.variante}): "
          f"liquido 2a metade = {num_br(campea_1a_metade[2],2)} "
          f"({'positivo' if campea_1a_metade[2] > 0 else 'negativo'}, "
          f"rank {rank_2a_de[id(campea_1a_metade[0])]}/{len(linhas)} na 2a metade)")


# ------------------------------------------------------------- fase 7: nulo sign-flip ----

def _fase_nulo(mechanic: str, T: int, S: int, spacing: int, n_levels: int, reanchor_bars: int,
               n_sementes: int = 20) -> None:
    """Nulo por sign-flip com a formula CORRETA (`s_d*bruto_d - custo_d`,
    NUNCA `s_d*liquido_d`): separa bruto (P&L sem custo) e custo (sempre
    <= 0) por PREGAO, sorteia o sinal so' do bruto."""
    bars = _bars_is()
    cfg_com_custo = _config_com_pedagio(0.0)
    cfg_sem_custo = IntradayCostModel(
        point_value_brl=cfg_com_custo.costs.point_value_brl, tick_size=cfg_com_custo.costs.tick_size,
        fee_round_trip_brl=0.0, slippage_ticks=0.0, exchange_fee_pct_per_leg=0.0,
    )
    cfg_bruto = IntradayBacktestConfig(
        costs=cfg_sem_custo, initial_capital=cfg_com_custo.initial_capital,
        default_quantity=cfg_com_custo.default_quantity, session_end_time=cfg_com_custo.session_end_time,
        session_end_policy=cfg_com_custo.session_end_policy, target_fills_as_maker=True,
        limit_fill_capped_by_volume=cfg_com_custo.limit_fill_capped_by_volume,
        enforce_capital_minimo=cfg_com_custo.enforce_capital_minimo,
        max_open_contracts=cfg_com_custo.max_open_contracts,
    )

    strat_liq = _monta_robo(mechanic, cfg_com_custo.costs.tick_size, T, S, spacing, n_levels, reanchor_bars)
    res_liq = run_intraday_backtest(bars, strat_liq, cfg_com_custo)
    strat_bruto = _monta_robo(mechanic, cfg_com_custo.costs.tick_size, T, S, spacing, n_levels, reanchor_bars)
    res_bruto = run_intraday_backtest(bars, strat_bruto, cfg_bruto)

    def _por_dia(trades) -> dict:
        acc: dict = {}
        for t in trades:
            d = pd.Timestamp(t.entry_ts).date()
            acc[d] = acc.get(d, 0.0) + t.pnl_brl
        return acc

    liquido_por_dia = _por_dia(res_liq.trades)
    bruto_por_dia = _por_dia(res_bruto.trades)
    dias = sorted(set(liquido_por_dia) | set(bruto_por_dia))
    bruto_d = [bruto_por_dia.get(d, 0.0) for d in dias]
    # `delta_custo_d` = liquido - bruto, sempre <= 0 (custo SUBTRAI do bruto).
    # E' o `custo_d` da missao com o sinal ja embutido: a serie sintetica
    # "s_d*bruto_d - custo_d" (custo_d ali como MAGNITUDE positiva) e
    # "s_d*bruto_d + delta_custo_d" (aqui, delta_custo_d negativo) sao a
    # MESMA conta -- o que importa (e' o que evita o vies do nulo "ganhar"
    # corretagem) e' o custo NUNCA flipar de sinal com `s_d`, so' o bruto.
    delta_custo_d = [liquido_por_dia.get(d, 0.0) - bruto_por_dia.get(d, 0.0) for d in dias]
    liquido_real = sum(liquido_por_dia.values())
    liquido_recomposto = sum(b + c for b, c in zip(bruto_d, delta_custo_d))
    assert abs(liquido_real - liquido_recomposto) < 1e-6, "bruto+custo nao bate com o liquido medido"

    resultados_nulos = []
    for seed in range(n_sementes):
        rng = random.Random(seed)
        s = [rng.choice((-1.0, 1.0)) for _ in dias]
        sintetico = sum(sd * b + c for sd, b, c in zip(s, bruto_d, delta_custo_d))
        resultados_nulos.append(sintetico)

    resultados_nulos.sort()
    abaixo = sum(1 for v in resultados_nulos if v < liquido_real)
    percentil = 100.0 * abaixo / len(resultados_nulos)
    print(f"\n=== Nulo sign-flip (formula correta: s_d*bruto_d - custo_d), "
          f"{n_sementes} sementes -- {_variante(mechanic, T, S, spacing, n_levels, reanchor_bars)} ===")
    print(f"  pregoes considerados: {len(dias)}")
    print(f"  liquido REAL: {num_br(liquido_real, 2)}")
    print(f"  nulo: media={num_br(statistics.mean(resultados_nulos),2)}  "
          f"desvio={num_br(statistics.pstdev(resultados_nulos),2)}  "
          f"min={num_br(resultados_nulos[0],2)}  max={num_br(resultados_nulos[-1],2)}")
    print(f"  percentil do resultado real na distribuicao do nulo: {percentil:.1f}% "
          f"({abaixo}/{len(resultados_nulos)} sementes do nulo ficaram ABAIXO do real)")


# ---------------------------------------------------------------- main -----

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=None)
    parser.add_argument("--fase", default="tudo",
                         choices=["grade", "pedagio", "niveis", "horario", "metade", "nulo", "tudo"])
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args()

    bars = _bars_is()
    dias = sorted(set(bars.index.date))
    print(f"[wdo_geo_sweep] WDO@ IS: {len(bars)} barras, {len(dias)} pregoes "
          f"({dias[0]}..{dias[-1]}), corte OOS = {profile_for(SYMBOL).frozen_cutoff}")

    unidades = []
    if args.fase in ("grade", "tudo"):
        unidades = _grade_reload() + _grade_rolling()
    if not unidades and args.fase not in ("grade", "tudo"):
        print("[wdo_geo_sweep] --fase != grade/tudo ainda nao tem um modo standalone "
              "neste script simplificado; rode --fase tudo.")
        return

    celulas = _roda_lote(unidades, args.jobs, "grade")
    _imprime_surface_por_T(celulas, "reload")
    _imprime_surface_por_T(celulas, "rolling")
    _imprime_top(celulas, args.top_n, "GRADE COMPLETA")

    top = sorted(celulas, key=lambda c: c.linha.liquido_brl, reverse=True)[:args.top_n]
    com_pedagio = _fase_pedagio(top, args.jobs)

    # candidata FINAL: a de MAIOR liquido COM pedagio (sobrevivente robusta);
    # se nenhuma sobreviver, cai para a melhor SEM pedagio e avisa.
    sobreviventes = [c for c in com_pedagio if c.linha.liquido_brl > 0]
    if sobreviventes:
        campea_pedagio = max(sobreviventes, key=lambda c: c.linha.liquido_brl)
        by_key = {(c.mechanic, c.T, c.S, c.spacing, c.n_levels, c.reanchor_bars): c for c in celulas}
        campea = by_key[(campea_pedagio.mechanic, campea_pedagio.T, campea_pedagio.S,
                         campea_pedagio.spacing, campea_pedagio.n_levels, campea_pedagio.reanchor_bars)]
        print(f"\n[wdo_geo_sweep] candidata FINAL (sobrevive a 1 tick de pedagio): "
              f"{campea.linha.variante}")
    else:
        campea = top[0]
        print(f"\n[wdo_geo_sweep] NENHUMA das top {len(top)} sobrevive a 1 tick de pedagio de fila -- "
              f"candidata final = melhor SEM pedagio (fragil, reportado como tal): "
              f"{campea.linha.variante}")

    _fase_horario(campea.mechanic, campea.T, campea.S, campea.spacing, campea.n_levels, campea.reanchor_bars)
    _fase_niveis(campea.mechanic, campea.T, campea.S, campea.spacing, campea.reanchor_bars, args.jobs)
    _fase_metade(top, args.jobs)
    _fase_nulo(campea.mechanic, campea.T, campea.S, campea.spacing, campea.n_levels, campea.reanchor_bars)

    print(f"\n[wdo_geo_sweep] baseline conhecida da missao: T1/S16/x1 = +R$37.606,53 "
          f"(script original nao encontrado neste repo, nao reproduzido bit-a-bit).")
    print(f"[wdo_geo_sweep] melhor SEM pedagio nesta grade: "
          f"{top[0].linha.variante} = {num_br(top[0].linha.liquido_brl, 2)}")


if __name__ == "__main__":
    main()
