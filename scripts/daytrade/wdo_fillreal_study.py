"""Estudo da Frente F3-wdo-fill-realismo: efeito de DUAS taticas de
colocacao de ordem (recuo de nivel, fatiamento de tamanho) sobre P&L e taxa
de preenchimento simulada do candidato grid-maker T1/S16 em WDO@.

So' IN-SAMPLE (`LockedBars.in_sample()`, corte 2026-06-13) -- NUNCA chama
`.unlock(...)`, regra desta rodada. Mora em `scripts/` (nao `backtest/`)
pelo mesmo motivo de `copa_lab.py`: precisa importar `backtest` E
`strategy` ao mesmo tempo.

IMPORTANTE (leia antes de usar qualquer numero deste arquivo): a estrategia
usada aqui (`strategy.daytrade.lab.wdo_fillreal_grid.WdoFillRealismGrid`) e'
uma reproducao best-effort da MECANICA do candidato estabelecido "T1 S16
x1" (mesma familia de `grid_reload_maker.py`, geometria T=1 tick / S=16
ticks) -- o arquivo/parametros EXATOS que produziram os +R$37.606,53 IS
citados no briefing desta frente nao foram encontrados neste estado do
repo. Uma pre-varredura de `level_spacing_ticks` (a UNICA geometria livre
que sobrou, feita ANTES de qualquer tatica de preenchimento, so' para achar
uma referencia -- ver `varredura_espacamento()`) mostrou win% consistente
85-88% em toda a grade testada, sempre ABAIXO do breakeven aritmetico de
1:16 (94,1%) -- ou seja, esta reproducao especifica e' estruturalmente
deficitaria na maior parte da grade, diferente do que o candidato
estabelecido reportou. As duas taticas desta frente sao medidas EM CIMA
desta reproducao, isolando o efeito de CADA tatica sobre o MESMO desenho de
base -- nao uma validacao nem uma refutacao do candidato original.
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
from strategy.daytrade.lab.wdo_fillreal_grid import WdoFillRealismGrid  # noqa: E402

SYMBOL = "WDO@"
CAPITAL_NOCIONAL = 1_000_000.0  # margem, nao caixa -- mesma convencao de `copa_lab.CAPITAL_NOCIONAL`.
TETO_CONTRATOS = 4  # folga sobre o que o dono opera hoje (1), pedido da missao: fixo, 1..4.
MIN_BARRAS_POR_PREGAO = 400  # mesmo corte de `copa_lab.py` -- meio pregao nao e' pregao.

#: Economia CONHECIDA do WDO@ (fallback quando o terminal MT5 nao esta aberto
#: nesta maquina) -- mesmos numeros de `scripts/daytrade/copa_lab.py.
#: `_ECONOMIA_CONHECIDA`, WDO@: (trade_tick_value, trade_tick_size) crus da
#: serie CONTINUA; `config_for` reescala pelo `price_tick_size` do perfil
#: (0,5) preservando o valor do ponto.
_ECONOMIA_WDO = (0.01, 0.001)

EXTRAS = ("recuo", "qtd", "fatiar", "preench%(contr)", "armados", "pedagio")


def barras_in_sample() -> pd.DataFrame:
    df = load_m1(SYMBOL)
    if df.empty:
        raise SystemExit(f"[wdo_fillreal] sem dado M1 salvo para {SYMBOL!r}.")
    profile = profile_for(SYMBOL)
    df = df.sort_index()
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    bars = LockedBars(df, split).in_sample()  # NUNCA .out_of_sample() nesta rodada.
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return bars[[d in completos for d in bars.index.date]]


def metade(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide `bars` em duas metades CRONOLOGICAS por numero de pregoes (nao
    por numero de barras -- pregoes tem tamanho quase igual aqui, mas o corte
    tem que cair numa fronteira de dia, nunca no meio de um pregao)."""
    dias = sorted(set(bars.index.date))
    corte = dias[len(dias) // 2]
    corte_ts = pd.Timestamp(corte, tz=bars.index.tz)
    return bars[bars.index.date < corte], bars[bars.index >= corte_ts]


def config(pedagio_ticks: float = 0.0, com_custo: bool = True,
           teto: int = TETO_CONTRATOS) -> IntradayBacktestConfig:
    """`pedagio_ticks` (portao G7 da familia copa, mesmo espirito aqui):
    pedagio artificial por PERNA MAKER (entrada `EnterLimit` + saida por
    alvo, `target_fills_as_maker=True` -- as duas pernas sao maker nesta
    estrategia, so' o stop e' a mercado) -- `pernas_maker=2` fixo."""
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=_ECONOMIA_WDO[0], trade_tick_size=_ECONOMIA_WDO[1],
        initial_capital=CAPITAL_NOCIONAL, target_fills_as_maker=True, max_open_contracts=teto,
    )
    custos = cfg.costs
    if not com_custo:
        custos = IntradayCostModel(point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
                                    fee_round_trip_brl=0.0, slippage_ticks=0.0, exchange_fee_pct_per_leg=0.0)
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
               split_exit: bool = False, level_spacing_ticks: int = 3,
               tick_size: float = 0.5, max_trades_per_side: int = 60,
               session_stop_brl: float = 1000.0) -> WdoFillRealismGrid:
    return WdoFillRealismGrid(
        symbol=SYMBOL, tick_size=tick_size, level_spacing_ticks=level_spacing_ticks,
        profit_ticks=1, stop_ticks=16, retreat_ticks=retreat_ticks, quantity=quantity,
        split_entry=split_entry, split_exit=split_exit, max_trades_per_side=max_trades_per_side,
        session_stop_brl=session_stop_brl,
    )


@dataclass(frozen=True)
class Rodada:
    rotulo: str
    resultado: IntradayBacktestResult
    strat: WdoFillRealismGrid
    pedagio_ticks: float

    def linha(self):
        fc = self.strat.fill_rate_pct
        preench_contr = f"{num_br(fc, 1)}%" if fc is not None else "—"
        return linha_de_resultado(
            self.rotulo, self.resultado, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={
                "recuo": str(self.strat.retreat_ticks),
                "qtd": str(self.strat.quantity),
                "fatiar": ("E" if self.strat.split_entry else "") + ("S" if self.strat.split_exit else "") or "—",
                "preench%(contr)": preench_contr,
                "armados": str(self.strat.orders_armed),
                "pedagio": num_br(self.pedagio_ticks, 1),
            },
        )


def rodar(bars: pd.DataFrame, rotulo: str, pedagio_ticks: float = 0.0, com_custo: bool = True,
          teto: int = TETO_CONTRATOS, **kw) -> Rodada:
    strat = estrategia(**kw)
    cfg = config(pedagio_ticks=pedagio_ticks, com_custo=com_custo, teto=teto)
    resultado = run_intraday_backtest(bars, strat, cfg)
    return Rodada(rotulo=rotulo, resultado=resultado, strat=strat, pedagio_ticks=pedagio_ticks)


# ---------- varredura em PARALELO (AGENTS.md: ProcessPoolExecutor, nunca ---
# serial, com resultado saindo assim que fica pronto) -----------------------

def _worker_task(spec: tuple) -> Rodada:
    """Roda UMA unidade da varredura -- funcao de MODULO (nao closure) de
    proposito: `ProcessPoolExecutor` no Windows usa `spawn`, que precisa
    conseguir importar/repicklar a funcao pelo nome em cada processo
    filho."""
    bars, rotulo, kw, pedagio_ticks, com_custo, teto = spec
    return rodar(bars, rotulo, pedagio_ticks=pedagio_ticks, com_custo=com_custo, teto=teto, **kw)


def rodar_paralelo(specs: list[tuple], max_workers: int = 4) -> dict[str, Rodada]:
    """`ProcessPoolExecutor` + `as_completed` (nunca `pool.map`, que so
    entrega na ORDEM de submissao e prende resultado pronto atras de unidade
    lenta) -- mesmo padrao de `scripts/daytrade/sweep_gremah_tick.py`
    (AGENTS.md). Cada unidade imprime a PROPRIA linha assim que termina
    (`flush=True`), nunca so no fim -- a maquina esta dividida entre varias
    frentes rodando ao mesmo tempo (2026-08-26), uma varredura muda pode
    levar dezenas de minutos por contencao de CPU alheia, e uma rodada que
    so fala no fim e' uma rodada que ninguem consegue acompanhar."""
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


# ---------- nulo por sign-flip (regra 5 do AGENTS.md desta rodada) ---------

def pnl_diario(trades) -> tuple[np.ndarray, np.ndarray]:
    """`(bruto_por_dia, custo_por_dia)` -- `custo_por_dia` e' MAGNITUDE
    POSITIVA (soma de `fees_total`, sempre >= 0), `bruto_por_dia` e' o P&L
    ANTES da tarifa (`pnl_brl + fees_total`). `liquido = bruto - custo`
    sempre (confere contra `sum(t.pnl_brl for t in trades)`)."""
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
    """Nulo CORRETO (regra 5): serie sintetica = `s_d*bruto_d - custo_d`,
    `s_d` sorteado em {-1,+1} por PREGAO -- o custo e' SEMPRE pago,
    independente do sorteio (nunca `s_d * liquido_d`, que faria o nulo
    GANHAR a corretagem quando `s_d=-1`, ver `costs.py`/AGENTS.md desta
    rodada). Roda >=5 sementes independentes; devolve o percentil do
    resultado REAL em cada uma."""
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


# ---------- serie sintetica sem estrutura (regra 8) -------------------------

def serie_sintetica_sem_estrutura(bars: pd.DataFrame, seed: int = 99) -> pd.DataFrame:
    """Embaralha os DELTAS de fechamento barra-a-barra (`close_t -
    close_{t-1}`, em pontos, DENTRO de cada pregao -- preserva o open real de
    cada sessao e o volume real casado a sua barra ORIGINAL, so desassocia
    preco de tempo) e reconstroi OHLC a partir do passeio aleatorio
    resultante. `high`/`low` sinteticos sao so' `max(open,close)`/
    `min(open,close)` da PROPRIA barra (sem pavio alem dos dois extremos) --
    isso SUBESTIMA range intrabar frente ao dado real, o que so' dificulta
    (nunca facilita) um toque/preenchimento no sintetico; o proposito aqui e'
    so' checar, de forma GROSSEIRA e deliberadamente conservadora (regra 8),
    se o padrao qualitativo da varredura de recuo sobrevive quando a
    estrutura temporal real e' destruida -- nao e' um simulador de mercado.
    UMA semente (nao 5+): calibracao grosseira de sanidade, nao o nulo
    principal (esse e' `nulo_sign_flip`, que usa >=5)."""
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
    """Toda unidade da varredura desta rodada, achatada numa lista SO' --
    submetida de uma vez ao pool (`rodar_paralelo`) para pagar o custo de
    subir os processos (`spawn`, caro no Windows) uma vez so', nao uma vez
    por secao do relatorio."""
    specs: list[tuple] = []

    # 1) TATICA A (headline): recuo de nivel, quantity=1 (restricao REAL do
    # dono hoje), spacing=3 ticks, x pedagio de fila {0, 1 tick}.
    for pedagio in (0.0, 1.0):
        for recuo in (0, 1, 2, 3):
            kw = dict(retreat_ticks=recuo, quantity=1, level_spacing_ticks=3)
            specs.append((bars, f"1|recuo={recuo}|pedagio={pedagio}", kw, pedagio, True, TETO_CONTRATOS))

    # 2) robustez: mesma tatica A, spacing=8 (unico ponto perto do empate a
    # custo zero na pre-varredura de geometria) -- so' 0 e 2 de recuo, para
    # nao dobrar o custo computacional so' de robustez.
    for recuo in (0, 2):
        kw = dict(retreat_ticks=recuo, quantity=1, level_spacing_ticks=8)
        specs.append((bars, f"2|recuo={recuo}|spacing=8", kw, 0.0, True, TETO_CONTRATOS))

    # 3) TATICA B: fatiamento de tamanho, quantity=3, spacing=3, recuo{0,2},
    # pedagio=0 (o cruzamento com pedagio fica para uma proxima rodada).
    for recuo in (0, 2):
        for fatiar in (False, True):
            kw = dict(retreat_ticks=recuo, quantity=3, split_entry=fatiar, split_exit=fatiar,
                       level_spacing_ticks=3)
            specs.append((bars, f"3|recuo={recuo}|fatiar={fatiar}", kw, 0.0, True, TETO_CONTRATOS))

    # 4) teste de metade: recuo x{0,1,2,3}, spacing=3, quantity=1, sem
    # pedagio, em cada metade cronologica do IS.
    for rotulo_metade, sub in (("M1", h1), ("M2", h2)):
        for recuo in (0, 1, 2, 3):
            kw = dict(retreat_ticks=recuo, quantity=1, level_spacing_ticks=3)
            specs.append((sub, f"4|{rotulo_metade}|recuo={recuo}", kw, 0.0, True, TETO_CONTRATOS))

    # 6) calibracao nula da varredura (regra 8): mesmo recuo x{0,2} sobre
    # serie SEM ESTRUTURA, 1 semente -- checagem grosseira, nao o nulo
    # principal (esse e' o sign-flip da secao 5, feito depois, sem re-rodar
    # backtest -- reusa os trades da secao 1).
    for recuo in (0, 2):
        kw = dict(retreat_ticks=recuo, quantity=1, level_spacing_ticks=3)
        specs.append((bars_sint, f"6|recuo={recuo}", kw, 0.0, True, TETO_CONTRATOS))

    return specs


if __name__ == "__main__":
    bars = barras_in_sample()
    pregoes = len(set(bars.index.date))
    print(f"[wdo_fillreal] IS: {len(bars)} barras, {pregoes} pregoes, "
          f"{bars.index.min()} -> {bars.index.max()}", flush=True)

    h1, h2 = metade(bars)
    print(f"[wdo_fillreal] metade 1: {len(set(h1.index.date))} pregoes "
          f"({h1.index.min()} -> {h1.index.max()})", flush=True)
    print(f"[wdo_fillreal] metade 2: {len(set(h2.index.date))} pregoes "
          f"({h2.index.min()} -> {h2.index.max()})", flush=True)

    bars_sint = serie_sintetica_sem_estrutura(bars, seed=99)

    specs = _monta_specs(bars, h1, h2, bars_sint)
    print(f"[wdo_fillreal] {len(specs)} unidades na fila, "
          f"ProcessPoolExecutor(max_workers=4)...\n", flush=True)

    resultados = rodar_paralelo(specs, max_workers=4)

    def _secao(prefixo: str) -> list[Rodada]:
        itens = sorted((kv for kv in resultados.items() if kv[0].startswith(prefixo)), key=lambda kv: kv[0])
        return [v for _, v in itens]

    print("\n" + "=" * 100)
    print("1) TATICA A -- recuo de nivel, quantity=1 (a restricao REAL do dono hoje), spacing=3 ticks")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("1|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("2) ROBUSTEZ -- mesma varredura de recuo, spacing=8 ticks (geometria quase-empate a custo zero)")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("2|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("3) TATICA B -- fatiamento de tamanho, quantity=3, spacing=3 ticks, sem pedagio")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("3|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("4) TESTE DE METADE -- recuo (spacing=3, quantity=1, sem pedagio) em cada metade cronologica do IS")
    print("=" * 100)
    print("\n  -- METADE 1 --")
    print(tabela([r.linha() for r in _secao("4|M1|")], extras=EXTRAS, largura_extra=16))
    print("\n  -- METADE 2 --")
    print(tabela([r.linha() for r in _secao("4|M2|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("5) NULO SIGN-FLIP -- recuo=2, quantity=1, spacing=3, sem pedagio (>=5 sementes)")
    print("=" * 100)
    alvo = resultados["1|recuo=2|pedagio=0.0"]
    nulo = nulo_sign_flip(alvo.resultado.trades)
    print(f"  liquido real: R$ {nulo['real_liquido']:.2f}  ({nulo['n_dias']} pregoes com trade)")
    print(f"  percentil por semente: {[round(p, 2) for p in nulo['percentis']]}")
    print(f"  media={nulo['media_pct']:.2f}%  min={nulo['min_pct']:.2f}%  max={nulo['max_pct']:.2f}%  "
          f"desvio={nulo['desvio_pct']:.2f}%  n_sementes={len(nulo['percentis'])}")

    print("\n" + "=" * 100)
    print("6) CALIBRACAO NULA DA VARREDURA -- recuo x{0,2} sobre serie SEM ESTRUTURA (1 semente, checagem grosseira)")
    print("=" * 100)
    print(tabela([r.linha() for r in _secao("6|")], extras=EXTRAS, largura_extra=16))

    print("\n" + "=" * 100)
    print("FIM -- so' trecho IN-SAMPLE (< 2026-06-13); nenhum dado OOS foi olhado nesta rodada.")
    print("=" * 100)
