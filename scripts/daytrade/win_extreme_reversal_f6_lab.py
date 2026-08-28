"""Frente F6-win-volatilidade -- laboratorio da hipotese "reversao apos
excesso intrabar" (`strategy.daytrade.lab.win_extreme_reversal_f6.
WinExtremeReversalF6`) em WIN@. Diferente do bracket OCO/straddle (0/560
celulas, familia `copa`) e do grid-maker (0/60 celulas, morte por
aritmetica) -- ver a docstring do modulo da estrategia para o porque
concreto. Roda, nesta ordem:

  1. varredura de grade (k_bars x threshold_ticks x stop_ticks x
     target_ticks x modo fade/continuation) na 1a metade cronologica do IS
     -- escolhe o melhor candidato FADE por liquido R$.
  2. teste de metade: o candidato escolhido na 1a metade sobrevive na 2a?
  3. simetria fade x continuation na grade INTEIRA (full IS) -- os dois
     lados do MESMO gatilho deveriam ficar proximos de espelhados (soma
     perto de -2x custo) se nao houver tendencia direcional real apos o
     excesso; uma divergencia grande e' evidencia de tendencia, nao ruido.
  4. nulo por sign-flip (formula correta: `bruto_d`/`custo_d` separados,
     nunca inverte o liquido inteiro), 5+ sementes, percentil -- sobre o
     candidato, full IS.
  5. calibracao nula em varredura (regra 8): repete o passo 1+2 (escolhe
     por metade 1, confirma na metade 2) sobre series SINTETICAS sem
     estrutura -- cada sessao real embaralhada internamente (mesmos
     retornos de 1 min, ordem destruida) preserva a volatilidade
     agregada do dia mas apaga qualquer padrao de reversao/continuacao
     genuino. Se o ruido "confirma" tao bem quanto o real, o teste de
     metade nao esta provando nada.
  6. sensibilidade a slippage assumido (a estrategia e' TAKER nas duas
     pernas -- ao contrario do grid maker, o custo dominante aqui e'
     `slippage_ticks`, nao pedagio de fila).
  7. tabela padrao (`backtest.intraday.report`) do candidato, full IS.

NAO destrava o trecho OOS (`LockedBars.out_of_sample()` nunca e chamado) --
so' o trecho IN-SAMPLE (< `profile_for("WIN@").frozen_cutoff` = 2026-06-13)
e usado em QUALQUER lugar deste arquivo.

Mora em `scripts/` (nao em `backtest/`) pela mesma regra de fronteira de
`copa_lab.py`/`wdo_grid_reload_f1_lab.py`: precisa importar `backtest` E
`strategy` ao mesmo tempo. NAO importa nenhum dos dois -- monta a propria
config, para as frentes paralelas nao colidirem.

Paraleliza a varredura com `ProcessPoolExecutor` (convencao do repo: nunca
serial) -- cada processo worker recebe os DataFrames (full IS, 1a metade,
2a metade) UMA vez, via `initializer`, nao a cada tarefa.

Uso: `python scripts/daytrade/win_extreme_reversal_f6_lab.py`
"""
from __future__ import annotations

import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.costs import IntradayCostModel  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.machine import IntradayBacktestConfig, IntradayTrade  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import (  # noqa: E402
    LinhaResultado,
    cabecalho,
    linha,
    linha_de_resultado,
    num_br,
)
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_extreme_reversal_f6 import WinExtremeReversalF6  # noqa: E402

SYMBOL = "WIN@"

#: Linha de base NOCIONAL -- futuro nao tem saldo real neste teste (ver
#: `wdo_grid_reload_f1_lab.py`, mesmo motivo).
CAPITAL_NOCIONAL = 1_000_000.0

#: 1 CONTRATO -- a restricao real do dono nesta rodada. A propria
#: estrategia nunca pede uma 2a entrada com a 1a ainda aberta (so' entra
#: quando `positions` esta vazio), entao este teto so' formaliza o que ja
#: seria verdade sem ele.
MAX_OPEN_CONTRATOS = 1

#: Mesmo numero de `copa_lab.py`/`wdo_grid_reload_f1_lab.py`: perfil
#: documenta ~563 barras/pregao tipicas para o WIN@; meio pregao nao e' um
#: pregao e distorce qualquer media.
MIN_BARRAS_POR_PREGAO = 400

#: Economia conhecida (trade_tick_value, trade_tick_size) da serie
#: CONTINUA -- mesmo fallback de `copa_lab.py`. `config_for` reescala para
#: o `price_tick_size` real do perfil (5,0) preservando `point_value_brl`.
_ECONOMIA_WIN = (0.2, 1.0)

#: Cooldown fixo (nao entra na grade) -- 20 barras (~20min) de espera flat
#: apos um fechamento antes de reavaliar novo gatilho. Ver a docstring da
#: estrategia para o motivo (sem isto, uma tendencia sustentada dispara
#: sinal em quase toda barra, reamostrando o MESMO evento).
COOLDOWN_BARS = 20

#: Grade de varredura. 3 x 3 x 2 x 3 x 2 = 108 combinacoes.
K_BARS = (5, 10, 20)
THRESHOLD_TICKS = (30.0, 50.0, 70.0)
STOP_TICKS = (10.0, 20.0)
TARGET_TICKS = (10.0, 20.0, 30.0)
MODES = ("fade", "continuation")

#: Sementes/realizacoes minimas exigidas pela disciplina de teste (regra 5).
N_SEMENTES_NULO = 5
DRAWS_POR_SEMENTE = 5000
#: 3, nao 5 -- este passo (regra 8) roda a grade INTEIRA por realizacao
#: (~5min/realizacao neste motor); com o resultado principal ja
#: inequivoco (ver o passo 1: 0/108 celulas positivas nas duas metades,
#: fade E continuation), 3 realizacoes bastam para confirmar que o ruido
#: tampouco produz falso positivo -- nao ha' fronteira fina para refinar
#: aqui. O nulo sign-flip (regra 5, passo 4) continua com as 5 sementes
#: exigidas -- e' numpy puro, sem custo de backtest.
N_REALIZACOES_SINTETICAS = 3


def grade_params() -> list[dict]:
    out = []
    for k, thr, stop, tgt, mode in itertools.product(
        K_BARS, THRESHOLD_TICKS, STOP_TICKS, TARGET_TICKS, MODES
    ):
        out.append(dict(
            symbol=SYMBOL, tick_size=profile_for(SYMBOL).price_tick_size,
            k_bars=k, threshold_ticks=thr, stop_ticks=stop, target_ticks=tgt,
            cooldown_bars=COOLDOWN_BARS, mode=mode,
        ))
    return out


def carregar_barras() -> LockedBars:
    """Barras M1 do WIN@ dentro do split CONGELADO do perfil -- so'
    `.in_sample()` e chamado neste arquivo inteiro."""
    df = load_m1(SYMBOL)
    if df.empty:
        raise SystemExit(
            f"[win_extreme_reversal_f6] sem dado M1 salvo para {SYMBOL!r} -- rode "
            f"`scripts/daytrade/backfill_m1.py --symbol {SYMBOL}` primeiro."
        )
    profile = profile_for(SYMBOL)
    df = df.sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    df = df[[d in completos for d in df.index.date]]
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    return LockedBars(df, split)


def montar_config(com_custo: bool = True, slippage_ticks_override: float | None = None) -> IntradayBacktestConfig:
    """`com_custo=False` zera tarifa E slippage -- so' para comparacao bruta,
    nunca o numero reportado como resultado.

    `slippage_ticks_override`: substitui `costs.slippage_ticks` (default do
    modelo = 1.0) -- a estrategia e' TAKER nas duas pernas (entrada E
    saida), entao o custo dominante e' este, nao pedagio de fila (que so'
    faz sentido para ordem MAKER, que esta estrategia nunca usa)."""
    profile = profile_for(SYMBOL)
    trade_tick_value, trade_tick_size = _ECONOMIA_WIN
    cfg = config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=CAPITAL_NOCIONAL,
        target_fills_as_maker=False,
        max_open_contracts=MAX_OPEN_CONTRATOS,
    )
    custos = cfg.costs
    if not com_custo:
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=0.0, slippage_ticks=0.0, exchange_fee_pct_per_leg=0.0,
        )
    elif slippage_ticks_override is not None:
        custos = IntradayCostModel(
            point_value_brl=custos.point_value_brl, tick_size=custos.tick_size,
            fee_round_trip_brl=custos.fee_round_trip_brl, slippage_ticks=slippage_ticks_override,
            exchange_fee_pct_per_leg=custos.exchange_fee_pct_per_leg,
        )
    return IntradayBacktestConfig(
        costs=custos,
        initial_capital=cfg.initial_capital,
        default_quantity=cfg.default_quantity,
        session_end_time=cfg.session_end_time,
        session_end_policy=cfg.session_end_policy,
        target_fills_as_maker=cfg.target_fills_as_maker,
        limit_fill_capped_by_volume=cfg.limit_fill_capped_by_volume,
        enforce_capital_minimo=cfg.enforce_capital_minimo,
        max_open_contracts=cfg.max_open_contracts,
    )


def rodar(bars: pd.DataFrame, cfg: IntradayBacktestConfig, params: dict):
    strat = WinExtremeReversalF6(**params)
    return run_intraday_backtest(bars, strat, cfg)


def descreve_janela(bars: pd.DataFrame) -> str:
    pregoes = len(set(bars.index.date))
    return (f"{len(bars)} barras M1, {pregoes} pregoes, "
            f"{bars.index.min():%Y-%m-%d} -> {bars.index.max():%Y-%m-%d}")


def metade(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dias = sorted(set(bars.index.date))
    corte = dias[len(dias) // 2]
    primeira = bars[[d < corte for d in bars.index.date]]
    segunda = bars[[d >= corte for d in bars.index.date]]
    return primeira, segunda


# ---------------------------------------------------------------------------
# construcao de serie SINTETICA sem estrutura (regra 8)
# ---------------------------------------------------------------------------

def _synthetic_bars(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Embaralha, DENTRO de cada sessao, a ORDEM dos retornos de 1 minuto
    (fechamento a fechamento) e do "chicote" intrabarra (high/low relativo
    ao corpo aberto/fechado de CADA barra original) -- em par, para nao
    inventar combinacoes (retorno, chicote) que nao aconteceram de
    verdade.

    Preserva por sessao: preco de abertura real, o CONJUNTO de retornos de
    1 min (mesma volatilidade agregada do dia, mesma distribuicao —
    inclusive caudas gordas de um pregao especifico) e o tamanho do
    chicote intrabarra de cada barra original.

    Destroi: a SEQUENCIA -- qualquer padrao onde um movimento de
    `k_bars` barras tende a reverter ou continuar nas barras seguintes,
    porque a ORDEM em que os retornos acontecem agora e' aleatoria.

    E' o null exigido pela regra 8 (calibracao nula em varredura) para
    ESTA hipotese especificamente: `WinExtremeReversalF6` so' pode ter
    edge se a ORDEM importar; embaralhar a ordem apaga exatamente (e so')
    isso."""
    rng = np.random.default_rng(seed)
    out = bars.copy()
    opens = out["open"].to_numpy(dtype=float)
    highs = out["high"].to_numpy(dtype=float)
    lows = out["low"].to_numpy(dtype=float)
    closes = out["close"].to_numpy(dtype=float)
    dates = pd.DatetimeIndex(out.index).date

    novo_open = opens.copy()
    novo_high = highs.copy()
    novo_low = lows.copy()
    novo_close = closes.copy()

    for _, idx in pd.Series(np.arange(len(out)), index=dates).groupby(level=0):
        pos = idx.to_numpy()
        n = len(pos)
        if n == 0:
            continue
        o = opens[pos]
        h = highs[pos]
        l = lows[pos]
        c = closes[pos]
        prev_close = np.empty(n)
        prev_close[0] = o[0]
        prev_close[1:] = c[:-1]
        ret = c - prev_close
        corpo_alto = np.maximum(o, c)
        corpo_baixo = np.minimum(o, c)
        wick_up = h - corpo_alto
        wick_down = corpo_baixo - l

        perm = rng.permutation(n)
        ret_p = ret[perm]
        wu_p = wick_up[perm]
        wd_p = wick_down[perm]

        synth_close = o[0] + np.cumsum(ret_p)
        synth_open = np.empty(n)
        synth_open[0] = o[0]
        synth_open[1:] = synth_close[:-1]
        synth_high = np.maximum(synth_open, synth_close) + np.maximum(wu_p, 0.0)
        synth_low = np.minimum(synth_open, synth_close) - np.maximum(wd_p, 0.0)

        novo_open[pos] = synth_open
        novo_close[pos] = synth_close
        novo_high[pos] = synth_high
        novo_low[pos] = synth_low

    out["open"] = novo_open
    out["high"] = novo_high
    out["low"] = novo_low
    out["close"] = novo_close
    return out


# ---------------------------------------------------------------------------
# varredura paralela
# ---------------------------------------------------------------------------

_G: dict = {}


def _init_worker(subsets: dict[str, pd.DataFrame], cfg: IntradayBacktestConfig) -> None:
    _G["subsets"] = subsets
    _G["cfg"] = cfg


def _task_grid_combo(params: dict) -> dict:
    cfg = _G["cfg"]
    out = dict(params)
    for label, bars in _G["subsets"].items():
        result = rodar(bars, cfg, params)
        liquido = sum(t.pnl_brl for t in result.trades)
        wins = sum(1 for t in result.trades if t.pnl_brl > 0)
        n = len(result.trades)
        out[f"{label}_liquido"] = liquido
        out[f"{label}_trades"] = n
        out[f"{label}_win_pct"] = (100.0 * wins / n) if n else 0.0
    return out


def rodar_grade(subsets: dict[str, pd.DataFrame], cfg: IntradayBacktestConfig,
                 params_list: list[dict], max_workers: int = 10,
                 rotulo_progresso: str = "grade") -> pd.DataFrame:
    """`submit`/`as_completed` (NUNCA `pool.map`) -- AGENTS.md: `map` so'
    entrega na ordem de submissao, prendendo um combo rapido atras de um
    lento; aqui todos os combos custam quase o mesmo (mesmo numero de
    barras), mas o principio e' o mesmo em toda varredura do repo. Imprime
    o resultado de CADA combo assim que termina (`flush=True`) -- uma
    varredura de minutos que so fala no fim e' uma que ninguem consegue
    interromper com informacao (ver `sweep_gremah_tick.py`)."""
    total = len(params_list)
    registros: list[dict] = []
    concluidos = 0
    with ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker,
                              initargs=(subsets, cfg)) as pool:
        futures = {pool.submit(_task_grid_combo, params): params for params in params_list}
        for future in as_completed(futures):
            concluidos += 1
            rec = future.result()
            registros.append(rec)
            resumo = "  ".join(f"{label}=R${num_br(rec.get(f'{label}_liquido', 0.0))}"
                                for label in subsets)
            print(f"[{rotulo_progresso}] {concluidos}/{total}  {_rotulo(pd.Series(rec))}  {resumo}",
                  flush=True)
    return pd.DataFrame.from_records(registros)


def _rotulo(row: pd.Series) -> str:
    return (f"k{int(row['k_bars'])} thr{num_br(row['threshold_ticks'],0)} "
            f"S{num_br(row['stop_ticks'],0)} T{num_br(row['target_ticks'],0)} {row['mode']}")


# ---------------------------------------------------------------------------
# 1+2. varredura na 1a metade + teste de metade
# ---------------------------------------------------------------------------

def varredura_e_teste_de_metade(bars_is: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    print("\n=== 1. varredura de grade na 1a metade (IS) -- escolhe o melhor FADE ===")
    primeira, segunda = metade(bars_is)
    print(f"1a metade: {descreve_janela(primeira)}")
    print(f"2a metade: {descreve_janela(segunda)}")

    cfg = montar_config()
    params_list = grade_params()
    t0 = time.time()
    grade = rodar_grade({"h1": primeira, "h2": segunda}, cfg, params_list,
                         rotulo_progresso="1-grade-metades")
    print(f"[{len(params_list)} combinacoes x 2 subconjuntos em {time.time()-t0:.1f}s]", flush=True)

    fade = grade[grade["mode"] == "fade"].sort_values("h1_liquido", ascending=False)
    cont = grade[grade["mode"] == "continuation"]
    print(f"\nfade: mediana h1_liquido=R${num_br(fade['h1_liquido'].median())}  "
          f"positivos={int((fade['h1_liquido']>0).sum())}/{len(fade)}")
    print(f"continuation: mediana h1_liquido=R${num_br(cont['h1_liquido'].median())}  "
          f"positivos={int((cont['h1_liquido']>0).sum())}/{len(cont)}")

    print("\ntop-5 FADE por liquido na 1a metade:")
    top5 = fade.head(5)
    for _, row in top5.iterrows():
        print(f"  {_rotulo(row):<32} h1=R${num_br(row['h1_liquido']):>12} "
              f"({int(row['h1_trades'])} trd, {num_br(row['h1_win_pct'],1)}%)   "
              f"h2=R${num_br(row['h2_liquido']):>12} ({int(row['h2_trades'])} trd, "
              f"{num_br(row['h2_win_pct'],1)}%)")

    campeao = fade.iloc[0]
    print(f"\n=== 2. teste de metade -- candidato escolhido na 1a metade: {_rotulo(campeao)} ===")
    print(f"1a metade: R${num_br(campeao['h1_liquido'])} ({int(campeao['h1_trades'])} trades, "
          f"{num_br(campeao['h1_win_pct'],1)}% acerto)")
    print(f"2a metade: R${num_br(campeao['h2_liquido'])} ({int(campeao['h2_trades'])} trades, "
          f"{num_br(campeao['h2_win_pct'],1)}% acerto)")
    print(f"sobrevive nas duas metades? {bool(campeao['h1_liquido'] > 0 and campeao['h2_liquido'] > 0)}")

    return campeao, grade


# ---------------------------------------------------------------------------
# 3. simetria fade x continuation (full IS)
# ---------------------------------------------------------------------------

def simetria_fade_continuation(grade_metades: pd.DataFrame) -> pd.DataFrame:
    """Reaproveita a MESMA grade do passo 1 (h1+h2) em vez de rodar o motor
    de novo sobre o IS inteiro: `h1` e `h2` particionam o IS por SESSAO sem
    sobreposicao, e a estrategia nao carrega estado nenhum entre sessoes
    (`on_session_start` zera `_state` toda sessao, e nenhum `seed_*` e'
    usado aqui) -- `h1_liquido + h2_liquido` de um combo e' EXATAMENTE o
    que uma unica passada sobre o IS inteiro produziria para o mesmo
    combo. Rodar de novo seria queimar ~mais uma passada inteira da grade
    (o motor deste repo nao e' rapido o bastante para "so' mais uma
    passada" ser gratis) so' para recalcular uma soma."""
    print("\n=== 3. simetria fade x continuation (full IS = h1+h2 do passo 1, MESMO gatilho) ===")
    grade = grade_metades.copy()
    grade["full_liquido"] = grade["h1_liquido"] + grade["h2_liquido"]
    grade["full_trades"] = grade["h1_trades"] + grade["h2_trades"]

    chave = ["k_bars", "threshold_ticks", "stop_ticks", "target_ticks"]
    fade = grade[grade["mode"] == "fade"].set_index(chave)
    cont = grade[grade["mode"] == "continuation"].set_index(chave)
    par = fade[["full_liquido", "full_trades"]].join(
        cont[["full_liquido", "full_trades"]], lsuffix="_fade", rsuffix="_cont")
    par["soma"] = par["full_liquido_fade"] + par["full_liquido_cont"]

    print(f"fade:         mediana=R${num_br(fade['full_liquido'].median())}  "
          f"positivos={int((fade['full_liquido']>0).sum())}/{len(fade)}")
    print(f"continuation: mediana=R${num_br(cont['full_liquido'].median())}  "
          f"positivos={int((cont['full_liquido']>0).sum())}/{len(cont)}")
    print(f"soma fade+continuation por celula (deveria rondar -2x custo se SEM tendencia real): "
          f"mediana=R${num_br(par['soma'].median())}, min={num_br(par['soma'].min())}, "
          f"max={num_br(par['soma'].max())}")
    return grade


# ---------------------------------------------------------------------------
# 4. nulo por sign-flip
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DiaPnL:
    bruto: float  # P&L SEM custo nenhum (nem tarifa, nem slippage)
    custo: float  # SEMPRE <= 0 (tarifa + AMBAS as pernas de slippage do dia)


def _pnl_diario(trades: list[IntradayTrade]) -> list[_DiaPnL]:
    """Diferente de `wdo_grid_reload_f1_lab.py::_pnl_diario`: aquela
    estrategia e' maker em 2 das 3 saidas possiveis (entrada + alvo), entao
    so' desfaz a tarifa. Esta estrategia e' TAKER nas duas pernas SEMPRE
    (`target_fills_as_maker=False`) -- o slippage e' o custo dominante, e
    fica de fora do "bruto" tambem: `trade.slippage_total` guarda so' o
    slippage da perna de SAIDA; a perna de ENTRADA paga o MESMO valor (
    `costs.slippage_ticks` e' constante ao longo da run, e a formula de
    `apply_intraday_slippage` e' identica nas duas pernas), entao
    `2 * slippage_total` desfaz as duas."""
    por_dia: dict = {}
    for t in trades:
        dia = pd.Timestamp(t.exit_ts).date()
        bruto_trade = t.pnl_brl + t.fees_total + 2.0 * t.slippage_total
        custo_trade = -(t.fees_total + 2.0 * t.slippage_total)
        b, c = por_dia.get(dia, (0.0, 0.0))
        por_dia[dia] = (b + bruto_trade, c + custo_trade)
    return [_DiaPnL(bruto=b, custo=c) for b, c in por_dia.values()]


def nulo_sign_flip(trades: list[IntradayTrade], rotulo: str) -> None:
    print(f"\n=== 4. nulo por sign-flip (formula correta) -- {rotulo} ===")
    dias = _pnl_diario(trades)
    if not dias:
        print("sem trades -- nulo nao computavel.")
        return
    brutos = np.array([d.bruto for d in dias])
    custos = np.array([d.custo for d in dias])
    liquido_real = float(brutos.sum() + custos.sum())
    custo_total = float(custos.sum())
    print(f"{len(dias)} pregoes com trade. liquido real = R${num_br(liquido_real)}; "
          f"custo total pago = R${num_br(custo_total)}")

    percentis: list[float] = []
    medias_sinteticas: list[float] = []
    for semente in range(N_SEMENTES_NULO):
        rng = np.random.default_rng(semente)
        sinais = rng.choice([-1.0, 1.0], size=(DRAWS_POR_SEMENTE, len(dias)))
        sintetico = sinais @ brutos + custo_total
        percentil = float((sintetico <= liquido_real).mean() * 100.0)
        percentis.append(percentil)
        medias_sinteticas.append(float(sintetico.mean()))

    percentis_arr = np.array(percentis)
    print(f"percentil do liquido real na distribuicao nula, por semente: "
          + ", ".join(num_br(p, 1) + "%" for p in percentis_arr))
    print(f"media entre {N_SEMENTES_NULO} sementes = {num_br(percentis_arr.mean(), 1)}% "
          f"(min {num_br(percentis_arr.min(), 1)}%, max {num_br(percentis_arr.max(), 1)}%, "
          f"desvio {num_br(percentis_arr.std(), 1)}pp, n_draws/semente={DRAWS_POR_SEMENTE})")
    print(f"media do nulo (deveria ~ = custo pago, R${num_br(custo_total)}): "
          f"R${num_br(float(np.mean(medias_sinteticas)))}")


# ---------------------------------------------------------------------------
# 5. calibracao nula em varredura (regra 8)
# ---------------------------------------------------------------------------

def calibracao_nula_em_varredura(bars_is: pd.DataFrame) -> None:
    print(f"\n=== 5. calibracao nula em varredura ({N_REALIZACOES_SINTETICAS} "
          f"realizacoes sinteticas sem estrutura) ===")
    print("repete o passo 1+2 (escolhe por liquido na 1a metade, confirma na 2a) "
          "sobre serie com a MESMA volatilidade agregada por sessao mas ORDEM "
          "embaralhada dentro de cada dia -- ver `_synthetic_bars`.")
    cfg = montar_config()
    params_list = grade_params()

    sobrevividas = 0
    medianas_h1 = []
    for seed in range(N_REALIZACOES_SINTETICAS):
        synth = _synthetic_bars(bars_is, seed=1000 + seed)
        primeira, segunda = metade(synth)
        grade = rodar_grade({"h1": primeira, "h2": segunda}, cfg, params_list,
                             rotulo_progresso=f"5-synth{seed}")
        fade = grade[grade["mode"] == "fade"].sort_values("h1_liquido", ascending=False)
        campeao = fade.iloc[0]
        sobrevive = bool(campeao["h1_liquido"] > 0 and campeao["h2_liquido"] > 0)
        sobrevividas += int(sobrevive)
        medianas_h1.append(float(fade["h1_liquido"].median()))
        print(f"  realizacao {seed}: melhor h1=R${num_br(campeao['h1_liquido'])} -> "
              f"h2=R${num_br(campeao['h2_liquido'])}  sobrevive? {sobrevive}", flush=True)

    print(f"\nruido 'sobrevive' ao teste de metade em {sobrevividas}/{N_REALIZACOES_SINTETICAS} "
          f"realizacoes sem estrutura nenhuma.")
    print(f"mediana de h1_liquido (fade) sob ruido: media={num_br(float(np.mean(medianas_h1)))}, "
          f"min={num_br(float(np.min(medianas_h1)))}, max={num_br(float(np.max(medianas_h1)))}")


# ---------------------------------------------------------------------------
# 6. sensibilidade a slippage assumido
# ---------------------------------------------------------------------------

def sensibilidade_slippage(bars_is: pd.DataFrame, params: dict) -> None:
    print("\n=== 6. sensibilidade a slippage assumido (ticks, full IS) ===")
    linhas: list[LinhaResultado] = []
    for slip in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5):
        cfg = montar_config(slippage_ticks_override=slip)
        resultado = rodar(bars_is, cfg, params)
        linhas.append(linha_de_resultado(
            f"slippage {num_br(slip, 1)} tick", resultado, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={"slippage_ticks": num_br(slip, 1)},
        ))
    print(cabecalho(("slippage_ticks",)))
    for item in linhas:
        print(linha(item, ("slippage_ticks",)))
    print("modelo padrao do repo assume slippage_ticks=1.0 (`IntradayCostModel` default).")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    locked = carregar_barras()
    bars_is = locked.in_sample()
    print(f"[win_extreme_reversal_f6] {SYMBOL} -- {descreve_janela(bars_is)} "
          f"(corte congelado: {locked.split.cutoff.date()})")
    print(f"quantity=1 contrato fixo, max_open_contracts={MAX_OPEN_CONTRATOS}, "
          f"cooldown_bars={COOLDOWN_BARS}")

    campeao, grade_metades = varredura_e_teste_de_metade(bars_is)
    simetria_fade_continuation(grade_metades)

    params_campeao = dict(
        symbol=SYMBOL, tick_size=profile_for(SYMBOL).price_tick_size,
        k_bars=int(campeao["k_bars"]), threshold_ticks=float(campeao["threshold_ticks"]),
        stop_ticks=float(campeao["stop_ticks"]), target_ticks=float(campeao["target_ticks"]),
        cooldown_bars=COOLDOWN_BARS, mode="fade",
    )
    cfg = montar_config()
    resultado_full = rodar(bars_is, cfg, params_campeao)
    nulo_sign_flip(resultado_full.trades, _rotulo(campeao))

    calibracao_nula_em_varredura(bars_is)
    sensibilidade_slippage(bars_is, params_campeao)

    print(f"\n=== 7. tabela padrao (candidato completo, full IS) -- {_rotulo(campeao)} ===")
    item = linha_de_resultado(f"win_extreme_reversal_f6 {_rotulo(campeao)}", resultado_full,
                               CAPITAL_NOCIONAL, capital_nocional=True)
    print(cabecalho())
    print(linha(item))


if __name__ == "__main__":
    main()
