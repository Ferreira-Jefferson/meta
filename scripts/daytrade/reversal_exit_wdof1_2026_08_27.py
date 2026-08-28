"""SINAL DE SAIDA ANTECIPADA (reversao) -- `WdoGridReloadMaker` F1 (WDO@,
"T1 S16 x1"), 2026-08-27 -- terceira etapa da mesma investigacao (depois da
"Escada de capital" e da "Qualidade de sinal DE ENTRADA"). Pergunta do dono:
nos trades que fecham mal (stop ou pnl negativo), o preco chegou a rodar a
favor (MFE positivo) ANTES de reverter contra a posicao? Se sim, uma regra de
saida por reversao, sem look-ahead, calibrada numa metade do IS e testada
mecanicamente na outra, teria evitado ou reduzido a perda -- ao custo de
cortar cedo demais alguns vencedores?

## Reuso de dado das duas etapas anteriores -- NENHUM rerun do motor

Trade log: N=1, ESTATICO, IN-SAMPLE (2.773 trades) de
`capital_ladder_wdof1_2026_08_27.py`
(`capital_ladder_wdof1_n1_trades_2026_08_27.csv`), relido do CSV -- o motor
NAO e' rerrodado. Caminho de preco: `wdo_grid_reload_f1_tick_lab.
carregar_tick_bars()`, a MESMA funcao/MESMA janela (72 pregoes IS com tick
disponivel no terminal MT5, 2026-02-27..2026-06-12, 2.832.170 ticks) que
gerou o trade log e que `signal_quality_wdof1_2026_08_27.py` ja usou para as
features de entrada. `OOS_CUTOFF=2026-06-13` nunca e' tocado, `.unlock()`
nunca e' chamado.

## Casamento trade -> tick: ENTRADA por preco+timestamp, SAIDA por timestamp

Entrada reusa (import, nao copia) `_acha_toque_rapido` de
`signal_quality_wdof1_2026_08_27.py` -- busca binaria pelo timestamp de
entrada, desempate pelo primeiro tick no mesmo instante que satisfaz o
criterio de toque (mesmo criterio de `_limit_touched`).

Saida usa uma regra DIFERENTE, por bom motivo: o preco de saida registrado
(`exit_price`) as vezes inclui slippage (stop e forced_flatten pagam 1 tick
de slippage a mercado -- `machine.py::_close_position`, `is_maker_target`
so' e' `True` para `target`), entao nem sempre bate exato com o preco de
algum tick real -- casar por PRECO como na entrada deixaria de fora uma
fatia dos stops/forced_flatten sem necessidade (mesmo problema e mesma
solucao ja documentados em `reversal_exit_gremahtick_2026_08_27.py`). Em vez
disso, `exit_pos` = posicao do ULTIMO tick com timestamp <= `exit_ts`
(`np.searchsorted(ts_ns, exit_ts_ns, side="right") - 1`) -- o motor tick
processa cada linha de `tick_bars` como seu proprio "bar" (`Bar.open==high==
low==close==preco do negocio`, ver `wdo_grid_reload_f1_tick_probe.
buscar_ticks`), entao `exit_ts` E' o timestamp de um tick real (nao um
timestamp sintetico de barra M1) -- o casamento por timestamp e' exato por
construcao, so' o PRECO registrado pode diferir do preco do tick pela
slippage/gap-through ja descritos. Verificado empiricamente antes de
reportar (ver a saida do script): fracao exata e desvio medio/maximo,
mesma disciplina de `reversal_exit_gremahtick_2026_08_27.py`.

## MFE / MAE -- definicao (resolucao TICK, sem ambiguidade de OHLC)

Para cada trade casado, com `ep`=posicao do tick de entrada e `xp`=posicao
do tick de saida (por timestamp, acima), o caminho de preco e'
`preco[ep:xp+1]` (INCLUSIVE a saida -- excluir esse tick esconderia
justamente o instante que importa, mesma razao ja documentada em
`copa_win_reversal_exit_lab_2026_08_27.py`). Como cada linha de `tick_bars`
e' um negocio real (nao uma barra OHLC agregada), NAO ha ambiguidade de
"qual tocou primeiro dentro da mesma barra" -- toda a familia de problemas
que `ambiguous_bar_resolution` resolve por convencao no motor M1 simplesmente
nao existe aqui.

    fav_ticks[j]  = sinal * (preco[j] - entry_price) / tick_size   (sinal=+1 long, -1 short)
    running_mfe   = maximo cumulativo de fav_ticks desde ep ate' j
    MFE_ticks     = fav_ticks.max() (>= 0 sempre, o proprio ep entra com fav=0)
    MAE_ticks     = (-fav_ticks).max() (>= 0 sempre, mesma convencao)

## A REGRA DE REVERSAO TESTADA (uma so', formato "retracao do MFE")

Formato pedido pela missao. Em cada tick `j` ESTRITAMENTE entre a entrada e
a saida real (`ep < j < xp` -- nem o proprio tick de entrada, que sempre tem
fav=0 e nada para "devolver" ainda, nem o tick de saida real, que fica de
fora pela mesma razao de `copa_win_reversal_exit_lab_2026_08_27.py`: um
trade so' conta como "a regra teria saido mais cedo" quando o gatilho
dispara ESTRITAMENTE antes da saida verdadeira -- sem isso, um trade onde a
regra e a saida real coincidem exatamente no mesmo tick empataria por
acidente de convencao, nao por antecipacao real):

    peak_ate_j    = running_mfe em j (usa so' preco ATE' j, disponivel no
                    instante da decisao -- SEM look-ahead)
    giveback_j    = peak_ate_j - fav_ticks[j]
    dispara em j se peak_ate_j >= ARM_TICKS E giveback_j >= X * peak_ate_j

`X` e' o UNICO parametro livre, calibrado por grade (0%, 10%, ..., 100%) na
METADE 1 cronologica dos trades casados (maximiza o P&L TOTAL simulado
dentro da propria metade1); o `X` vencedor e' aplicado MECANICAMENTE (sem
reajuste) na metade2 -- mesma disciplina de split das duas etapas
anteriores desta investigacao.

## ARM_TICKS -- piso de armamento, reusado (nao um numero novo aqui)

`ARM_TICKS = 1.0`, o MESMO piso e a MESMA justificativa de
`reversal_exit_gremahtick_2026_08_27.py` (candidato irmao de motor TICK,
"com menos de 1 tick de folga acumulada nao ha nada real para 'devolver',
so' ruido") -- NAO o `vol_min_ticks` que `copa_win_reversal_exit_lab_
2026_08_27.py` reusa (a `WdoGridReloadMaker` nao tem um parametro de
volatilidade minima analogo; o candidato tem alvo de 1 tick e stop de 16
ticks, entao 1 tick de excursao favoravel ja e' o proprio tamanho do alvo --
o piso mais pequeno defensavel, nao arbitrario).

## Preco/custo da saida SIMULADA

Preco de saida simulado = `apply_intraday_slippage(preco[j], lado_de_saida,
costs)` -- MESMO modelo de custo do motor (`backtest.intraday.costs`), MESMA
direcao de slippage que uma saida a mercado (stop) ja paga hoje (a regra de
reversao e' uma saida de PROTECAO/urgencia, no mesmo espirito do stop, nunca
maker). `costs` vem de `wdo_grid_reload_f1_lab.montar_config()` -- a MESMA
config (fee + slippage 1 tick, fill capped por volume) que gerou o trade log
original, entao o P&L simulado e o P&L real sao diretamente comparaveis
(mesma tarifa fixa por round-trip, `exchange_fee_pct_per_leg=0.0` no perfil
de futuro).

## Diagnostico extra (contexto, NAO faz parte da regra tradavel): o que
## aconteceu logo DEPOIS da saida real

Para os trades que saem por STOP, olha ate' `POS_EXIT_TICKS=30` ticks DEPOIS
de `exit_ts` (nunca cruza a virada do pregao) e mede a excursao favoravel
MAXIMA (orientada pelo lado do trade ORIGINAL) a partir do preco de saida
real. Isto NAO informa a regra (seria look-ahead) -- e' so' para responder
"o stop foi seguido de reversao de volta a favor (whipsaw) ou de
continuacao adversa (o stop se justificou)?", puramente descritivo -- mesma
secao de `copa_win_reversal_exit_lab_2026_08_27.py` /
`reversal_exit_gremahtick_2026_08_27.py`, adaptada a tick.

Nada em `src/` foi tocado; nenhum arquivo existente foi editado; nada
commitado; OOS nunca destravado.

Uso: `python -u scripts/daytrade/reversal_exit_wdof1_2026_08_27.py`
"""
from __future__ import annotations

import csv
import dataclasses
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

from backtest.intraday.costs import (  # noqa: E402
    apply_intraday_slippage,
    fees_round_trip_brl,
    gross_pnl_brl,
)
from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402

import wdo_grid_reload_f1_lab as G  # noqa: E402
from signal_quality_wdof1_2026_08_27 import _acha_toque_rapido  # noqa: E402
from wdo_grid_reload_f1_tick_lab import carregar_tick_bars  # noqa: E402
from wdo_grid_reload_f1_tick_rejection_lab import _tick_arrays  # noqa: E402

SYMBOL = "WDO@"
OUT_DIR = ROOT / "scripts" / "daytrade"
TRADE_LOG_CSV = OUT_DIR / "capital_ladder_wdof1_n1_trades_2026_08_27.csv"
MFE_MAE_CSV_OUT = OUT_DIR / "reversal_exit_wdof1_mfe_mae_2026_08_27.csv"
CALIBRACAO_CSV_OUT = OUT_DIR / "reversal_exit_wdof1_calibracao_metade1_2026_08_27.csv"
METADE2_CSV_OUT = OUT_DIR / "reversal_exit_wdof1_metade2_2026_08_27.csv"

#: Piso de armamento -- reusa o mesmo numero/justificativa de
#: `reversal_exit_gremahtick_2026_08_27.py` (ver docstring do modulo).
ARM_TICKS = 1.0

#: Grade do UNICO parametro livre (fracao de retracao do MFE), calibrada so'
#: na metade1 -- mesma grade de `reversal_exit_gremahtick_2026_08_27.py`.
GRID_X_PCT = list(range(0, 101, 10))

#: Janela de contexto (ticks) DEPOIS da saida real -- so' diagnostico, nunca
#: entra na regra. Clampada na virada do pregao.
POS_EXIT_TICKS = 30


# ---------------------------------------------------------------------------
# 0. trade log (CSV ja' computado -- nenhum rerun do motor)
# ---------------------------------------------------------------------------

def carrega_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True, format="ISO8601")
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True, format="ISO8601")
    df = df.sort_values("entry_ts").reset_index(drop=True)
    assert df["entry_ts"].is_monotonic_increasing, "trade log fora de ordem cronologica"
    return df


# ---------------------------------------------------------------------------
# 1. casamento trade -> tick (entrada por preco+ts, saida por ts) + caminho
# ---------------------------------------------------------------------------

@dataclass
class TradePath:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    side: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl_brl: float
    exit_reason: str
    entry_pos: int
    exit_pos: int
    mfe_ticks: float
    mae_ticks: float
    # arrays de gatilho -- SO' ticks estritamente entre entrada e saida
    trig_running_mfe_ticks: np.ndarray
    trig_fav_ticks: np.ndarray
    trig_pos_abs: np.ndarray  # posicao ABSOLUTA no array de ticks, por elemento de trig_*
    pos_exit_fav_ticks: float  # contexto: excursao favoravel MAXIMA nos ate' POS_EXIT_TICKS ticks apos a saida


def constroi_paths(df: pd.DataFrame, ts_ns: np.ndarray, preco: np.ndarray,
                    dias_arr: np.ndarray, tick_size: float) -> tuple[list[TradePath], int, dict]:
    n = len(df)
    entry_ts_ns = df["entry_ts"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    exit_ts_ns = df["exit_ts"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    exit_pos_arr = np.searchsorted(ts_ns, exit_ts_ns, side="right") - 1

    out: list[TradePath] = []
    sem_match = 0
    diffs_exit_price = []

    for i, row in enumerate(df.itertuples(index=False)):
        entry_pos = _acha_toque_rapido(ts_ns, preco, int(entry_ts_ns[i]), float(row.entry_price), row.side)
        exit_pos = int(exit_pos_arr[i])
        if entry_pos is None or exit_pos < entry_pos:
            sem_match += 1
            continue

        diffs_exit_price.append(abs(float(preco[exit_pos]) - float(row.exit_price)))

        side = row.side
        entry_price = float(row.entry_price)
        sign = 1.0 if side == "long" else -1.0

        caminho = preco[entry_pos:exit_pos + 1]
        fav_ticks = sign * (caminho - entry_price) / tick_size
        mfe_ticks = float(fav_ticks.max())
        mae_ticks = float((-fav_ticks).max())

        # ---- arrays de gatilho: ticks ESTRITAMENTE entre entrada e saida ----
        if exit_pos - entry_pos >= 2:
            trig_fav = fav_ticks[1:-1]
            trig_running_mfe = np.maximum.accumulate(fav_ticks)[1:-1]
            trig_pos_abs = np.arange(entry_pos + 1, exit_pos)
        else:
            trig_fav = np.empty(0)
            trig_running_mfe = np.empty(0)
            trig_pos_abs = np.empty(0, dtype=np.int64)

        # ---- contexto pos-saida (nao entra na regra) ----
        dia_saida = dias_arr[exit_pos]
        fim = exit_pos
        limite = min(exit_pos + POS_EXIT_TICKS, len(ts_ns) - 1)
        while fim < limite and dias_arr[fim + 1] == dia_saida:
            fim += 1
        if fim > exit_pos:
            janela = preco[exit_pos + 1:fim + 1]
            exit_price = float(row.exit_price)
            pos_fav = float((sign * (janela - exit_price) / tick_size).max())
        else:
            pos_fav = float("nan")

        out.append(TradePath(
            entry_ts=row.entry_ts, exit_ts=row.exit_ts, side=side,
            entry_price=entry_price, exit_price=float(row.exit_price),
            quantity=int(row.quantity), pnl_brl=float(row.pnl_brl),
            exit_reason=str(row.exit_reason), entry_pos=entry_pos, exit_pos=exit_pos,
            mfe_ticks=mfe_ticks, mae_ticks=mae_ticks,
            trig_running_mfe_ticks=trig_running_mfe, trig_fav_ticks=trig_fav,
            trig_pos_abs=trig_pos_abs, pos_exit_fav_ticks=pos_fav,
        ))

    diag = dict(
        n_sanity=len(diffs_exit_price),
        diff_medio=float(np.mean(diffs_exit_price)) if diffs_exit_price else float("nan"),
        diff_max=float(np.max(diffs_exit_price)) if diffs_exit_price else float("nan"),
        frac_exata=float(np.mean(np.array(diffs_exit_price) < 1e-6)) if diffs_exit_price else float("nan"),
    )
    return out, sem_match, diag


def salva_mfe_mae_csv(paths: list[TradePath], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["entry_ts", "exit_ts", "side", "exit_reason", "pnl_brl",
                    "mfe_ticks", "mae_ticks", "pos_exit_fav_ticks_30t"])
        for p in paths:
            w.writerow([p.entry_ts.isoformat(), p.exit_ts.isoformat(), p.side, p.exit_reason,
                        p.pnl_brl, p.mfe_ticks, p.mae_ticks, p.pos_exit_fav_ticks])


# ---------------------------------------------------------------------------
# 2. simulacao da regra para um X dado
# ---------------------------------------------------------------------------

@dataclass
class ResultadoSimulado:
    triggered: bool
    exit_price_sim: float
    pnl_sim: float


def _lado_saida(side: str) -> str:
    return "sell" if side == "long" else "buy"


def simula_trade(p: TradePath, x: float, preco: np.ndarray, costs) -> ResultadoSimulado:
    mfe = p.trig_running_mfe_ticks
    if mfe.size == 0:
        return ResultadoSimulado(False, p.exit_price, p.pnl_brl)
    armado = mfe >= ARM_TICKS
    giveback = mfe - p.trig_fav_ticks
    dispara = armado & (giveback >= x * mfe)
    onde = np.flatnonzero(dispara)
    if onde.size == 0:
        return ResultadoSimulado(False, p.exit_price, p.pnl_brl)
    j_abs = int(p.trig_pos_abs[onde[0]])
    preco_bruto = float(preco[j_abs])
    preco_saida = apply_intraday_slippage(preco_bruto, _lado_saida(p.side), costs)
    bruto = gross_pnl_brl(p.entry_price, preco_saida, p.quantity, p.side, costs)
    liquido = bruto - fees_round_trip_brl(p.quantity, p.entry_price, preco_saida, costs)
    return ResultadoSimulado(True, preco_saida, liquido)


def simula_grupo(paths: list[TradePath], x: float, preco: np.ndarray, costs) -> list[ResultadoSimulado]:
    return [simula_trade(p, x, preco, costs) for p in paths]


# ---------------------------------------------------------------------------
# 3. calibracao por grade -- SO' na metade1
# ---------------------------------------------------------------------------

@dataclass
class LinhaGrade:
    x_pct: int
    n_triggered: int
    pnl_atual: float
    pnl_sim: float
    delta: float
    maxdd_atual: float
    maxdd_sim: float


def _curva(pnls: list[float]) -> pd.Series:
    return pd.Series(np.concatenate(([0.0], np.cumsum(pnls))))


def avalia_x(paths: list[TradePath], x_pct: int, preco: np.ndarray, costs) -> LinhaGrade:
    sims = simula_grupo(paths, x_pct / 100.0, preco, costs)
    pnl_atual = [p.pnl_brl for p in paths]
    pnl_sim = [s.pnl_sim for s in sims]
    return LinhaGrade(
        x_pct=x_pct, n_triggered=sum(1 for s in sims if s.triggered),
        pnl_atual=float(sum(pnl_atual)), pnl_sim=float(sum(pnl_sim)),
        delta=float(sum(pnl_sim) - sum(pnl_atual)),
        maxdd_atual=maxdd_brl(_curva(pnl_atual)), maxdd_sim=maxdd_brl(_curva(pnl_sim)),
    )


def calibra_grade(metade1: list[TradePath], preco: np.ndarray, costs) -> tuple[list[LinhaGrade], int]:
    linhas = [avalia_x(metade1, x, preco, costs) for x in GRID_X_PCT]
    melhor = max(linhas, key=lambda ln: ln.pnl_sim)
    return linhas, melhor.x_pct


def salva_calibracao_csv(linhas: list[LinhaGrade], path: Path) -> None:
    campos = [f.name for f in dataclasses.fields(LinhaGrade)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(campos)
        for ln in linhas:
            w.writerow([getattr(ln, c) for c in campos])


# ---------------------------------------------------------------------------
# 4. teste mecanico na metade2
# ---------------------------------------------------------------------------

def salva_metade2_csv(paths: list[TradePath], sims: list[ResultadoSimulado], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["entry_ts", "exit_ts", "side", "exit_reason_atual", "pnl_atual",
                    "triggered", "pnl_sim", "mfe_ticks", "mae_ticks"])
        for p, s in zip(paths, sims):
            w.writerow([p.entry_ts.isoformat(), p.exit_ts.isoformat(), p.side, p.exit_reason,
                        p.pnl_brl, s.triggered, s.pnl_sim, p.mfe_ticks, p.mae_ticks])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    trades = carrega_trades(TRADE_LOG_CSV)
    print(f"[reversal_exit_wdof1] trade log: {TRADE_LOG_CSV} -- {len(trades)} trades "
          f"(liquido = R${num_br(float(trades['pnl_brl'].sum()))})")
    print(f"[reversal_exit_wdof1] exit_reason: {dict(trades['exit_reason'].value_counts())}")

    dias, tick_bars = carregar_tick_bars()
    print(f"[reversal_exit_wdof1] tick bars: {len(tick_bars)} ticks, {len(dias)} pregoes IS "
          f"({dias[0]} -> {dias[-1]})")

    ts_ns, preco, _volume = _tick_arrays(tick_bars)
    dias_arr = tick_bars.index.date

    cfg = G.montar_config()
    costs = cfg.costs
    tick_size = costs.tick_size
    print(f"[reversal_exit_wdof1] tick_size={tick_size} | ARM_TICKS={num_br(ARM_TICKS,1)} | "
          f"grade de X: {GRID_X_PCT}% | janela de contexto pos-saida={POS_EXIT_TICKS} ticks")

    paths, sem_match, diag = constroi_paths(trades, ts_ns, preco, dias_arr, tick_size)
    print(f"[reversal_exit_wdof1] caminhos reconstruidos para {len(paths)}/{len(trades)} trades "
          f"({sem_match} sem tick correspondente -- deveria ser 0)")
    print(f"[reversal_exit_wdof1] sanity casamento de SAIDA (por timestamp): "
          f"diff medio |exit_price - preco(exit_pos)| = {num_br(diag['diff_medio'], 4)} pontos "
          f"({num_br(diag['diff_medio']/tick_size, 3)} ticks), "
          f"max={num_br(diag['diff_max'], 4)} pontos ({num_br(diag['diff_max']/tick_size, 1)} ticks), "
          f"frac exata(<1e-6)={num_br(diag['frac_exata']*100, 1)}%")
    salva_mfe_mae_csv(paths, MFE_MAE_CSV_OUT)
    print(f"[reversal_exit_wdof1] MFE/MAE por trade salvo em {MFE_MAE_CSV_OUT}")

    # ---------------- PARTE A: MFE/MAE descritivo ----------------
    mfe_arr = np.array([p.mfe_ticks for p in paths])
    mae_arr = np.array([p.mae_ticks for p in paths])
    pnl_arr = np.array([p.pnl_brl for p in paths])
    reason_arr = np.array([p.exit_reason for p in paths])

    print(f"\n=== PARTE A: MFE / MAE (ticks), toda a amostra (n={len(paths)}) -- ANTES da saida real ===")
    print(f"{'grupo':<24}{'n':>6}{'MFE medio':>12}{'MFE mediana':>13}"
          f"{'MAE medio':>12}{'MAE mediana':>13}{'MFE-MAE (medio)':>18}")
    print("-" * 98)

    def _linha(nome: str, mask: np.ndarray) -> None:
        if mask.sum() == 0:
            print(f"{nome:<24}{0:>6}")
            return
        mfe_m, mfe_md = mfe_arr[mask].mean(), float(np.median(mfe_arr[mask]))
        mae_m, mae_md = mae_arr[mask].mean(), float(np.median(mae_arr[mask]))
        print(f"{nome:<24}{int(mask.sum()):>6}{num_br(mfe_m,3):>12}{num_br(mfe_md,3):>13}"
              f"{num_br(mae_m,3):>12}{num_br(mae_md,3):>13}{num_br(mfe_m-mae_m,3):>18}")

    todos = np.ones(len(paths), dtype=bool)
    _linha("todos", todos)
    _linha("vencedores (pnl>0)", pnl_arr > 0)
    _linha("perdedores (pnl<=0)", pnl_arr <= 0)
    for motivo in ("target", "stop", "forced_flatten"):
        _linha(f"exit={motivo}", reason_arr == motivo)

    print(f"\n[reversal_exit_wdof1] SIMETRIA MFE x MAE (todos os {len(paths)} trades): "
          f"media MFE={num_br(float(mfe_arr.mean()),4)} ticks | media MAE={num_br(float(mae_arr.mean()),4)} ticks | "
          f"razao MFE/MAE={num_br(float(mfe_arr.mean()/mae_arr.mean()) if mae_arr.mean() else float('nan'),3)}")
    print("(comparacao: familia Copa WIN@/WDO@ documentou MFE~=MAE -- achado registrado em memoria)")

    # ---------------- oportunidade de reversao: STOP / P&L negativo ----------------
    stop_mask = reason_arr == "stop"
    perdedor_mask = pnl_arr <= 0
    for nome, mask in (("saida por STOP", stop_mask), ("P&L negativo (todos motivos)", perdedor_mask)):
        n = int(mask.sum())
        com_mfe = int((mask & (mfe_arr >= ARM_TICKS)).sum())
        com_mfe_pos = int((mask & (mfe_arr > 0)).sum())
        print(f"\n[reversal_exit_wdof1] entre {n} trades com {nome}: "
              f"{com_mfe_pos} ({num_br(100.0*com_mfe_pos/n,1) if n else '-'}%) tiveram MFE>0 antes de fechar; "
              f"{com_mfe} ({num_br(100.0*com_mfe/n,1) if n else '-'}%) chegaram a MFE >= {num_br(ARM_TICKS,1)} "
              f"tick(s) (piso de armamento) -- MFE medio nesse subgrupo = "
              f"{num_br(float(mfe_arr[mask & (mfe_arr>=ARM_TICKS)].mean()),3) if com_mfe else '-'} ticks")

    # ---------------- contexto pos-saida (so' STOP) ----------------
    pos_fav_stop = np.array([p.pos_exit_fav_ticks for p in paths if p.exit_reason == "stop"])
    pos_fav_stop = pos_fav_stop[~np.isnan(pos_fav_stop)]
    if len(pos_fav_stop):
        print(f"\n=== contexto: excursao favoravel MAXIMA nos {POS_EXIT_TICKS} ticks APOS o STOP "
              f"(n={len(pos_fav_stop)}, nao entra na regra, so' diagnostico) ===")
        print(f"  media={num_br(float(pos_fav_stop.mean()),3)} ticks | mediana={num_br(float(np.median(pos_fav_stop)),3)} ticks | "
              f"frac com alguma reversao a favor (>0)={num_br(float((pos_fav_stop>0).mean())*100,1)}%")

    # ---------------- PARTE B: calibra X na metade1, aplica na metade2 ----------------
    print(f"\n\n=== PARTE B: regra de reversao (retracao do MFE, ARM_TICKS={num_br(ARM_TICKS,1)}) ===")
    meio = len(paths) // 2
    metade1, metade2 = paths[:meio], paths[meio:]
    print(f"[reversal_exit_wdof1] split cronologico: metade1 n={len(metade1)} "
          f"({metade1[0].entry_ts:%Y-%m-%d} -> {metade1[-1].entry_ts:%Y-%m-%d}) | "
          f"metade2 n={len(metade2)} ({metade2[0].entry_ts:%Y-%m-%d} -> {metade2[-1].entry_ts:%Y-%m-%d})")

    linhas_grade, x_estrela = calibra_grade(metade1, preco, costs)
    salva_calibracao_csv(linhas_grade, CALIBRACAO_CSV_OUT)
    print(f"\n=== calibracao de X -- GRADE COMPLETA na METADE 1 (n={len(metade1)} trades) ===")
    print(f"{'X%':>5}{'triggered':>11}{'pnl atual':>14}{'pnl sim':>14}{'delta':>12}"
          f"{'maxdd atual':>14}{'maxdd sim':>12}")
    print("-" * 84)
    for ln in linhas_grade:
        print(f"{ln.x_pct:>4}%{ln.n_triggered:>11}{num_br(ln.pnl_atual):>14}"
              f"{num_br(ln.pnl_sim):>14}{num_br(ln.delta):>12}"
              f"{num_br(ln.maxdd_atual):>14}{num_br(ln.maxdd_sim):>12}")
    print(f"\n[reversal_exit_wdof1] X* escolhido na metade1 (maior pnl simulado) = {x_estrela}%")
    if x_estrela == 0:
        print("  ATENCAO: X=0% venceu -- extremo da grade (sair no 1o tick que nao faz novo pico), "
              "sinal de que a regra em si nao ajuda nesta janela (grade sem otimo interior).")
    if x_estrela == 100:
        print("  ATENCAO: X=100% venceu -- outro extremo (so' sai devolvendo o MFE inteiro), "
              "equivalente a quase nunca disparar antes da saida real.")
    print(f"[reversal_exit_wdof1] tabela de calibracao salva em {CALIBRACAO_CSV_OUT}")

    # ---------------- teste MECANICO na metade 2, X fixo ----------------
    sims_m2 = simula_grupo(metade2, x_estrela / 100.0, preco, costs)
    salva_metade2_csv(metade2, sims_m2, METADE2_CSV_OUT)

    pnl_atual_m2 = np.array([p.pnl_brl for p in metade2])
    pnl_sim_m2 = np.array([s.pnl_sim for s in sims_m2])
    trig_m2 = np.array([s.triggered for s in sims_m2])

    print(f"\n=== TESTE MECANICO na METADE 2 (n={len(metade2)}), X*={x_estrela}% vindo SO' da metade 1 ===")
    print(f"trades onde a regra disparou ANTES da saida real: {int(trig_m2.sum())}/{len(metade2)} "
          f"({num_br(100.0*trig_m2.sum()/len(metade2),1)}%)")
    print(f"P&L medio por trade -- ATUAL: R${num_br(pnl_atual_m2.mean(),4)} | "
          f"SIMULADO: R${num_br(pnl_sim_m2.mean(),4)} | diferenca: R${num_br(pnl_sim_m2.mean()-pnl_atual_m2.mean(),4)}")
    print(f"P&L total           -- ATUAL: R${num_br(pnl_atual_m2.sum())} | "
          f"SIMULADO: R${num_br(pnl_sim_m2.sum())} | diferenca: R${num_br(pnl_sim_m2.sum()-pnl_atual_m2.sum())}")
    print(f"MaxDD               -- ATUAL: R${num_br(maxdd_brl(_curva(list(pnl_atual_m2))))} | "
          f"SIMULADO: R${num_br(maxdd_brl(_curva(list(pnl_sim_m2))))}")
    print(f"win rate            -- ATUAL: {num_br(float((pnl_atual_m2>0).mean())*100,2)}% | "
          f"SIMULADO: {num_br(float((pnl_sim_m2>0).mean())*100,2)}%")

    # decomposicao: perdedores originais vs vencedores originais (na metade 2)
    era_perdedor = pnl_atual_m2 <= 0
    era_vencedor = pnl_atual_m2 > 0
    delta = pnl_sim_m2 - pnl_atual_m2
    print("\n--- decomposicao (metade 2): efeito SEPARADO em quem era perdedor vs vencedor no ORIGINAL ---")
    for nome, mask in (("ERA PERDEDOR (pnl<=0)", era_perdedor), ("ERA VENCEDOR (pnl>0)", era_vencedor)):
        n = int(mask.sum())
        n_trig = int((mask & trig_m2).sum())
        soma_delta = float(delta[mask].sum())
        media_delta = float(delta[mask].mean()) if n else 0.0
        print(f"  {nome:<24} n={n:>4} | disparou={n_trig:>4} | "
              f"delta total (sim-atual)=R${num_br(soma_delta)} | delta medio/trade=R${num_br(media_delta,4)}")
    print(f"  saldo liquido do efeito = R${num_br(float(delta.sum()))} (deveria bater com "
          f"P&L simulado - P&L atual = R${num_br(pnl_sim_m2.sum()-pnl_atual_m2.sum())})")

    print(f"\n[reversal_exit_wdof1] trades trade-a-trade da metade2 (atual vs simulado) salvos em {METADE2_CSV_OUT}")


if __name__ == "__main__":
    main()
