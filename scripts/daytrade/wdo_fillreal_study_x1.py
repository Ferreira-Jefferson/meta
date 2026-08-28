"""Estudo da Frente F3-wdo-fill-realismo, RODADA 2 (2026-08-27): repete a
MESMA bateria da rodada 1 (recuo de nivel x pedagio de fila, fatiamento de
tamanho, teste de metade, nulo sign-flip, calibracao nula sobre serie sem
estrutura) trocando a base de `WdoFillRealismGrid` (spacing=3, ancora fixa)
para `WdoFillRealismGridX1` (spacing=1 -- o "x1" REAL do candidato "T1 S16
x1" -- com `reanchor_mode` explicito, default "rolling_last_price").

CHECAGEM DE SANIDADE JA FEITA (nao repetida aqui como backtest -- reusa o
resultado ja medido por `scripts/daytrade/wdo_grid_reload_f1_lab.py`, que
testa exatamente esta geometria x1 nas duas ancoras via
`WdoGridReloadMaker`, mecanica equivalente mas classe DIFERENTE, sem cruzar
import entre frentes): NENHUMA das tres leituras (rolling+fill-capped,
rolling+slippage0, fixed) chega perto do ballpark conhecido (+R$37.606,53)
com spacing=1 -- desvios de -104,1%, -96,7% e -129,7%. Ou seja, o problema
de base identificado na rodada 1 desta frente NAO era so' o spacing=3: com
x1 (a geometria real do candidato), em QUALQUER ancora testada, o resultado
continua muito longe do numero conhecido. Ver o relatorio da rodada 2 para
a leitura completa; este script mede o efeito das taticas de preenchimento
SOBRE a leitura MENOS ruim (x1, rolling, custo padrao ou slippage=0) --
ainda uma medicao "efeito da tatica sobre uma base fraca", nunca uma
validacao do candidato original.

So' IN-SAMPLE (`LockedBars.in_sample()`, corte 2026-06-13) -- NUNCA chama
`.unlock(...)`, regra desta rodada. Mora em `scripts/` pelo mesmo motivo de
`copa_lab.py`/`wdo_fillreal_study.py`: precisa importar `backtest` E
`strategy` ao mesmo tempo.
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.intraday.costs import IntradayCostModel  # noqa: E402
from backtest.intraday.engine import IntradayBacktestResult, run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.wdo_fillreal_grid_x1 import WdoFillRealismGridX1  # noqa: E402

SYMBOL = "WDO@"
CAPITAL_NOCIONAL = 1_000_000.0  # margem, nao caixa -- mesma convencao das rodadas/frentes anteriores.
TETO_CONTRATOS = 5  # folga sobre o teste de qtd=5 na tatica de fatiamento (secao 2).
MIN_BARRAS_POR_PREGAO = 400

#: Economia CONHECIDA do WDO@ -- mesmos numeros de `wdo_fillreal_study.py`/`copa_lab.py`.
_ECONOMIA_WDO = (0.01, 0.001)

EXTRAS = ("recuo", "ancora", "qtd", "fatiar", "preench%(contr)", "armados", "pedagio")


def barras_in_sample() -> pd.DataFrame:
    df = load_m1(SYMBOL)
    if df.empty:
        raise SystemExit(f"[wdo_fillreal_x1] sem dado M1 salvo para {SYMBOL!r}.")
    profile = profile_for(SYMBOL)
    df = df.sort_index()
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    bars = LockedBars(df, split).in_sample()  # NUNCA .out_of_sample() nesta rodada.
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return bars[[d in completos for d in bars.index.date]]


def metade(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dias = sorted(set(bars.index.date))
    corte = dias[len(dias) // 2]
    corte_ts = pd.Timestamp(corte, tz=bars.index.tz)
    return bars[bars.index.date < corte], bars[bars.index >= corte_ts]


def config(pedagio_ticks: float = 0.0, com_custo: bool = True,
           teto: int = TETO_CONTRATOS, slippage_ticks: float | None = None) -> IntradayBacktestConfig:
    """Identico a `wdo_fillreal_study.config()`, com `slippage_ticks`
    opcional (a leitura "rolling, slippage=0" da checagem de sanidade e' a
    unica positiva no IS entre as tres testadas -- vale medir as taticas
    tambem sobre ELA, nao so' sobre a config padrao com slippage=1 tick)."""
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=_ECONOMIA_WDO[0], trade_tick_size=_ECONOMIA_WDO[1],
        initial_capital=CAPITAL_NOCIONAL, target_fills_as_maker=True, max_open_contracts=teto,
    )
    custos = cfg.costs
    if not com_custo:
        custos = IntradayCostModel(point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
                                    fee_round_trip_brl=0.0, slippage_ticks=0.0, exchange_fee_pct_per_leg=0.0)
    elif slippage_ticks is not None:
        custos = IntradayCostModel(point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
                                    fee_round_trip_brl=custos.fee_round_trip_brl, slippage_ticks=slippage_ticks,
                                    exchange_fee_pct_per_leg=custos.exchange_fee_pct_per_leg)
    if pedagio_ticks:
        pernas_maker = 2
        extra = pedagio_ticks * custos.tick_size * custos.point_value_brl * pernas_maker
        custos = IntradayCostModel(point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
                                    fee_round_trip_brl=custos.fee_round_trip_brl + extra,
                                    slippage_ticks=custos.slippage_ticks,
                                    exchange_fee_pct_per_leg=custos.exchange_fee_pct_per_leg)
    return IntradayBacktestConfig(
        costs=custos, initial_capital=cfg.initial_capital, session_end_time=cfg.session_end_time,
        session_end_policy=cfg.session_end_policy, target_fills_as_maker=cfg.target_fills_as_maker,
        limit_fill_capped_by_volume=cfg.limit_fill_capped_by_volume,
        enforce_capital_minimo=cfg.enforce_capital_minimo, max_open_contracts=cfg.max_open_contracts,
    )


def estrategia(retreat_ticks: int = 0, quantity: int = 1, split_entry: bool = False,
               split_exit: bool = False, reanchor_mode: str = "rolling_last_price",
               tick_size: float = 0.5, max_trades_per_side: int = 200) -> WdoFillRealismGridX1:
    return WdoFillRealismGridX1(
        symbol=SYMBOL, tick_size=tick_size, level_spacing_ticks=1, profit_ticks=1, stop_ticks=16,
        reanchor_mode=reanchor_mode, retreat_ticks=retreat_ticks, quantity=quantity,
        split_entry=split_entry, split_exit=split_exit, max_trades_per_side=max_trades_per_side,
        session_stop_brl=None,
    )


@dataclass(frozen=True)
class Rodada:
    rotulo: str
    resultado: IntradayBacktestResult
    strat: WdoFillRealismGridX1
    pedagio_ticks: float

    def linha(self):
        fc = self.strat.fill_rate_pct
        preench_contr = f"{num_br(fc, 1)}%" if fc is not None else "—"
        return linha_de_resultado(
            self.rotulo, self.resultado, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={
                "recuo": str(self.strat.retreat_ticks),
                "ancora": "roll" if self.strat.reanchor_mode == "rolling_last_price" else "fix",
                "qtd": str(self.strat.quantity),
                "fatiar": ("E" if self.strat.split_entry else "") + ("S" if self.strat.split_exit else "") or "—",
                "preench%(contr)": preench_contr,
                "armados": str(self.strat.orders_armed),
                "pedagio": num_br(self.pedagio_ticks, 1),
            },
        )


def rodar(bars: pd.DataFrame, rotulo: str, pedagio_ticks: float = 0.0, com_custo: bool = True,
          teto: int = TETO_CONTRATOS, slippage_ticks: float | None = None, **kw) -> Rodada:
    strat = estrategia(**kw)
    cfg = config(pedagio_ticks=pedagio_ticks, com_custo=com_custo, teto=teto, slippage_ticks=slippage_ticks)
    resultado = run_intraday_backtest(bars, strat, cfg)
    return Rodada(rotulo=rotulo, resultado=resultado, strat=strat, pedagio_ticks=pedagio_ticks)


def _worker_task(spec: tuple) -> Rodada:
    bars, rotulo, kw, pedagio_ticks, com_custo, teto, slippage_ticks = spec
    return rodar(bars, rotulo, pedagio_ticks=pedagio_ticks, com_custo=com_custo, teto=teto,
                 slippage_ticks=slippage_ticks, **kw)


def rodar_paralelo(specs: list[tuple], max_workers: int = 4) -> dict[str, Rodada]:
    resultados: dict[str, Rodada] = {}
    total = len(specs)
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_worker_task, spec): spec[1] for spec in specs}
        concluidos = 0
        for future in as_completed(futures):
            rotulo = futures[future]
            r = future.result()
            resultados[rotulo] = r
            concluidos += 1
            liquido = sum(t.pnl_brl for t in r.resultado.trades)
            print(f"  [{concluidos}/{total}] {rotulo} -> trades={len(r.resultado.trades)} "
                  f"liquido={liquido:.2f} fill%(contr)={r.strat.fill_rate_pct}", flush=True)
    return resultados


def pnl_diario(trades) -> tuple[np.ndarray, np.ndarray]:
    por_dia: dict = {}
    for t in trades:
        dia = t.exit_ts.date()
        bruto, custo = por_dia.get(dia, (0.0, 0.0))
        por_dia[dia] = (bruto + t.pnl_brl + t.fees_total, custo + t.fees_total)
    dias = sorted(por_dia)
    bruto = np.array([por_dia[d][0] for d in dias])
    custo = np.array([por_dia[d][1] for d in dias])
    return bruto, custo


def nulo_sign_flip(trades, seeds=(1, 2, 3, 4, 5), draws_por_semente: int = 4000) -> dict:
    bruto, custo = pnl_diario(trades)
    if len(bruto) == 0:
        return {"real_liquido": 0.0, "percentis": [], "n_dias": 0}
    real_liquido = float(bruto.sum() - custo.sum())
    custo_total = float(custo.sum())
    percentis = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        sinais = rng.choice([-1.0, 1.0], size=(draws_por_semente, len(bruto)))
        sinteticos = sinais @ bruto - custo_total
        percentil = 100.0 * float((sinteticos < real_liquido).mean())
        percentis.append(percentil)
    return {"real_liquido": real_liquido, "percentis": percentis, "n_dias": len(bruto),
            "media_pct": float(np.mean(percentis)), "min_pct": float(np.min(percentis)),
            "max_pct": float(np.max(percentis)), "desvio_pct": float(np.std(percentis))}


def serie_sintetica_sem_estrutura(bars: pd.DataFrame, seed: int = 99) -> pd.DataFrame:
    """Identica a `wdo_fillreal_study.serie_sintetica_sem_estrutura` -- ver
    la' para a justificativa completa (embaralha deltas de fechamento
    DENTRO de cada pregao, preserva open/volume reais, high/low sinteticos
    sem pavio extra -- deliberadamente conservador, so' dificulta o
    preenchimento no sintetico)."""
    rng = np.random.default_rng(seed)
    saida = bars.copy()
    for dia, idx in bars.groupby(bars.index.date).groups.items():
        sub = bars.loc[idx]
        deltas = sub["close"].diff().to_numpy(copy=True)
        deltas[0] = 0.0
        embaralhado = rng.permutation(deltas)
        closes = float(sub["open"].iloc[0]) + np.cumsum(embaralhado)
        closes[0] = float(sub["open"].iloc[0])
        opens = np.concatenate([[float(sub["open"].iloc[0])], closes[:-1]])
        highs = np.maximum(opens, closes)
        lows = np.minimum(opens, closes)
        saida.loc[idx, "open"] = opens
        saida.loc[idx, "high"] = highs
        saida.loc[idx, "low"] = lows
        saida.loc[idx, "close"] = closes
    return saida


def _monta_specs(bars: pd.DataFrame, h1: pd.DataFrame, h2: pd.DataFrame,
                  bars_sint: pd.DataFrame) -> list[tuple]:
    specs: list[tuple] = []

    # 1) TATICA A (headline): recuo de nivel, quantity=1, ancora ROLLING
    # (a leitura menos ruim da checagem de sanidade), x pedagio {0, 1 tick}.
    for pedagio in (0.0, 1.0):
        for recuo in (0, 1, 2, 3):
            kw = dict(retreat_ticks=recuo, quantity=1, reanchor_mode="rolling_last_price")
            specs.append((bars, f"1|recuo={recuo}|pedagio={pedagio}", kw, pedagio, True, TETO_CONTRATOS, None))

    # 1b) mesma tatica, ancora FIXED (a leitura mais ruim da checagem de
    # sanidade) -- comparacao lado a lado, nao escondida (disciplina #2).
    for pedagio in (0.0, 1.0):
        for recuo in (0, 2):
            kw = dict(retreat_ticks=recuo, quantity=1, reanchor_mode="fixed_session_open")
            specs.append((bars, f"1b|recuo={recuo}|pedagio={pedagio}", kw, pedagio, True, TETO_CONTRATOS, None))

    # 2) TATICA B: fatiamento de tamanho, quantity em {3,5} (rodada 1 so'
    # testou 3 -- aqui cruza com um tamanho maior para checar se o efeito
    # nulo era teto estrutural do tamanho pequeno), recuo{0,2}, ancora
    # rolling, sem pedagio.
    for quantity in (3, 5):
        for recuo in (0, 2):
            for fatiar in (False, True):
                kw = dict(retreat_ticks=recuo, quantity=quantity, split_entry=fatiar, split_exit=fatiar,
                           reanchor_mode="rolling_last_price")
                specs.append((bars, f"2|qtd={quantity}|recuo={recuo}|fatiar={fatiar}", kw, 0.0, True,
                              TETO_CONTRATOS, None))

    # 3) teste de metade: recuo x{0,1,2,3}, ancora rolling, quantity=1, sem
    # pedagio, em cada metade cronologica do IS.
    for rotulo_metade, sub in (("M1", h1), ("M2", h2)):
        for recuo in (0, 1, 2, 3):
            kw = dict(retreat_ticks=recuo, quantity=1, reanchor_mode="rolling_last_price")
            specs.append((sub, f"3|{rotulo_metade}|recuo={recuo}", kw, 0.0, True, TETO_CONTRATOS, None))

    # 5) calibracao nula da varredura (regra 8): mesmo recuo x{0,2} sobre
    # serie SEM ESTRUTURA, 1 semente.
    for recuo in (0, 2):
        kw = dict(retreat_ticks=recuo, quantity=1, reanchor_mode="rolling_last_price")
        specs.append((bars_sint, f"5|recuo={recuo}", kw, 0.0, True, TETO_CONTRATOS, None))

    return specs


if __name__ == "__main__":
    bars = barras_in_sample()
    pregoes = len(set(bars.index.date))
    print(f"[wdo_fillreal_x1] IS: {len(bars)} barras, {pregoes} pregoes, "
          f"{bars.index.min()} -> {bars.index.max()}", flush=True)

    h1, h2 = metade(bars)
    print(f"[wdo_fillreal_x1] metade 1: {len(set(h1.index.date))} pregoes "
          f"({h1.index.min()} -> {h1.index.max()})", flush=True)
    print(f"[wdo_fillreal_x1] metade 2: {len(set(h2.index.date))} pregoes "
          f"({h2.index.min()} -> {h2.index.max()})", flush=True)

    bars_sint = serie_sintetica_sem_estrutura(bars, seed=99)

    specs = _monta_specs(bars, h1, h2, bars_sint)
    print(f"[wdo_fillreal_x1] {len(specs)} unidades na fila, "
          f"ProcessPoolExecutor(max_workers=4)...\n", flush=True)

    resultados = rodar_paralelo(specs, max_workers=4)

    def _secao(prefixo: str) -> list[Rodada]:
        itens = sorted((kv for kv in resultados.items() if kv[0].startswith(prefixo)), key=lambda kv: kv[0])
        return [v for _, v in itens]

    print("\n" + "=" * 100)
    print("1) TATICA A -- recuo de nivel, quantity=1, ancora ROLLING (a menos ruim da checagem de sanidade), x1")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("1|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("1b) MESMA TATICA, ancora FIXED (a mais ruim da checagem de sanidade) -- comparacao lado a lado")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("1b|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("2) TATICA B -- fatiamento de tamanho, quantity em {3,5}, recuo{0,2}, ancora rolling, sem pedagio")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("2|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("3) TESTE DE METADE -- recuo (ancora rolling, quantity=1, sem pedagio) em cada metade cronologica do IS")
    print("=" * 100)
    print("\n  -- METADE 1 --")
    print(tabela([r.linha() for r in _secao("3|M1|")], extras=EXTRAS, largura_extra=16))
    print("\n  -- METADE 2 --")
    print(tabela([r.linha() for r in _secao("3|M2|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("4) NULO SIGN-FLIP -- melhor recuo achado na secao 1 (ancora rolling, quantity=1, sem pedagio), >=5 sementes")
    print("=" * 100)
    secao1 = _secao("1|recuo")
    # melhor recuo = maior liquido entre os 4 pontos sem pedagio (pedagio=0.0) da secao 1.
    candidatos_sem_pedagio = [(k, v) for k, v in resultados.items()
                               if k.startswith("1|") and k.endswith("pedagio=0.0")]
    melhor_rotulo, melhor = max(candidatos_sem_pedagio, key=lambda kv: sum(t.pnl_brl for t in kv[1].resultado.trades))
    print(f"  variante escolhida: {melhor_rotulo}")
    nulo = nulo_sign_flip(melhor.resultado.trades)
    print(f"  liquido real: R$ {nulo['real_liquido']:.2f}  ({nulo['n_dias']} pregoes com trade)")
    print(f"  percentil por semente: {[round(p, 2) for p in nulo['percentis']]}")
    if nulo["percentis"]:
        print(f"  media={nulo['media_pct']:.2f}%  min={nulo['min_pct']:.2f}%  max={nulo['max_pct']:.2f}%  "
              f"desvio={nulo['desvio_pct']:.2f}%  n_sementes={len(nulo['percentis'])}")

    print("\n" + "=" * 100)
    print("5) CALIBRACAO NULA DA VARREDURA -- recuo x{0,2} sobre serie SEM ESTRUTURA (1 semente, checagem grosseira)")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("5|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("FIM -- so' trecho IN-SAMPLE (< 2026-06-13); nenhum dado OOS foi olhado nesta rodada.")
    print("=" * 100)
