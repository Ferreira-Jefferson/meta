"""Sinal de REVERSAO / SAIDA ANTECIPADA da `CopaWin` (WIN@) -- 2026-08-27.

Pergunta do dono: nos trades que saem por STOP (ou com P&L negativo), houve
em algum momento ANTES da saida uma excursao favoravel (MFE positivo) que
depois reverteu ate o stop? Se sim, uma regra de saida antecipada por
"sinal de reversao" (sem look-ahead, calibrada numa metade do IS e testada
mecanicamente na outra) reduziria a perda? E, separadamente: MFE e' ~= MAE
nesta calibracao especifica (o que a familia Copa ja documentou para outros
candidatos, evidencia de que a geometria alvo/stop e' onde mora o edge, nao
a gestao de saida) ou ha' assimetria explorável aqui?

## Reuso de dado das etapas anteriores -- NENHUM rerun do motor

Entrada: o trade log N=1 (1.086 trades, estatico, IN-SAMPLE) de
`capital_ladder_copawin_2026_08_27.py`, relido do CSV -- o motor NAO e'
rerrodado. Caminho de preco: `copa_lab.barras("WIN@").in_sample()` (72.730
barras M1, 129 pregoes, 2025-12-01 -> 2026-06-12), a MESMA janela que gerou
o trade log. `OOS_CUTOFF=2026-06-13` nunca e' tocado, `.unlock()` nunca e'
chamado.

## MFE/MAE: resolucao de BARRA M1, mesma convencao do motor

O motor inteiro (`_stop_target_touch`, `machine.py:367-380`) decide
stop/alvo por TOQUE de `bar.high`/`bar.low` contra o nivel -- nunca ve
ordem intrabarra. MFE/MAE aqui usam a MESMA convencao: para cada barra do
range `[entry_pos, exit_pos]` (inclusive a barra da propria saida, porque e'
nela que o toque que gerou a saida aconteceu -- excluir essa barra
esconderia justamente o instante que importa), a excursao favoravel e'
`high-entry` (long) / `entry-low` (short) e a adversa e' o espelho. O
"MFE atingido ANTES da saida real" e' o maximo cumulativo dessas excursoes
favoraveis ao longo de todo o range -- mais grosseiro que tick, mas a MESMA
resolucao que toda a pesquisa Copa usou para escolher o candidato (ver
`copa_rejection_lab.py`).

## A regra testada: RETRACAO do MFE ja atingido -- SEM look-ahead

Formato pedido pela missao ("sair se o preco retrair X% do MFE ja
atingido"). Em cada barra `t` estritamente ANTES da barra de saida real
(`entry_pos <= t < exit_pos` -- a barra de saida fica de fora de proposito,
ver a secao seguinte), depois de a barra `t` ja ter FECHADO (dado real,
disponivel no instante da decisao):

1. Atualiza `running_mfe(t)` = maximo cumulativo da excursao favoravel
   (`high`/`low` de `t`) desde a entrada ate `t`, inclusive.
2. So' "arma" quando `running_mfe(t) >= FLOOR_TICKS` (ver constante abaixo)
   -- sem isto, um MFE de 0 ou quase-0 dispararia a regra na primeira barra
   adversa, o que seria "corta no primeiro sinal contra", nao "reversao
   depois de favoravel" (o que a missao pede).
3. Calcula o "giveback" = `running_mfe(t) - close_fav(t)`, onde
   `close_fav(t)` e' a distancia do FECHAMENTO de `t` ate a entrada,
   orientada pelo lado (pode ser negativo se o fechamento ja esta pior que
   a entrada).
4. Dispara se `giveback(t) >= X * running_mfe(t)` -- "devolveu X% do maximo
   favoravel ja visto, medido pelo fechamento da barra". `X` e' o UNICO
   parametro livre, calibrado por grade na METADE 1 (secao mais abaixo).

Preco de saida simulado = `apply_intraday_slippage(close(t), lado_de_saida,
costs)` -- MESMO modelo de custo do motor (`backtest.intraday.costs`), MESMA
direcao de slippage que uma saida a mercado (stop) ja paga hoje. A tarifa
fixa por round-trip (`fees_round_trip_brl`) tambem e' recalculada no preco
simulado -- para WIN@ ela e' uma taxa FIXA por contrato
(`exchange_fee_pct_per_leg=0.0` no perfil de futuro, `profiles.py:204`), ou
seja, o CUSTO nao muda com o preco de saida, so' o P&L bruto muda.

## Por que a barra de saida real fica de FORA da busca do gatilho

Se a regra e a saida real (stop/alvo/forced_flatten) tocassem na MESMA
barra M1, nao ha como saber qual chegou primeiro so' com OHLC de 1 minuto
-- a mesma ambiguidade que `ambiguous_bar_resolution` resolve por
CONVENCAO no motor (`machine.py:387-389`). Aqui, em vez de inventar uma
convencao para favorecer a regra nova, a busca do gatilho PARA uma barra
antes da saida real: um trade so' conta como "a regra teria saido mais
cedo" quando o gatilho dispara numa barra ESTRITAMENTE anterior a saida
verdadeira. Trades onde a regra nunca dispara antes disso ficam
INALTERADOS (P&L simulado = P&L real) -- nunca sao contados como
"melhorados" nem "piorados" por acidente de empate.

## Split calibra/testa -- mesma disciplina de `copa_rejection_lab.py`

Trades ja vem ORDENADOS por `entry_ts` (mesmo `carrega_trades` de
`copa_win_entry_quality_lab_2026_08_27.py`). Metade 1 = primeira metade
cronologica (calibra `X` por grade, maximizando o LIQUIDO simulado
somado); metade 2 = segunda metade (aplica o `X*` da metade 1 SEM
reajuste, mede o efeito). A grade e' testada tambem inteira na metade 1 e
reportada crua (nao so' o vencedor) -- ver `feedback_present_tables_no_
verdict` na memoria do dono: tabela primeiro, veredito depois e curto.

## Piso de armamento (`FLOOR_TICKS`): reusa `vol_min_ticks` da propria
## `CopaWin`, nao e' um numero novo inventado aqui

`FLOOR_TICKS = CALIBRACAO_IS["WIN@"]["vol_min_ticks"]` (=8.0 ticks). Esse e'
o MESMO piso que a propria estrategia ja usa para decidir "isto e' ruido,
nao sinal" (o robo nem abre posicao se a volatilidade de referencia for
menor que isso -- `copa_win.py:353`). Exigir o mesmo tamanho de MFE antes
de a regra de reversao armar e' consistente com o proprio filtro de ruido
do robo, nao uma escolha livre escondida como parametro fixo.

## Diagnostico extra (contexto, NAO faz parte da regra tradavel): o que
## aconteceu logo DEPOIS da saida real

Para cada trade, olha ate `POS_EXIT_BARRAS=10` barras DEPOIS de `exit_ts`
(nunca cruza a virada do pregao -- `CopaWin.on_session_start` zera tudo, e
`forced_flatten` existe exatamente para isso) e mede a excursao favoravel
MAXIMA (orientada pelo lado do trade ORIGINAL) a partir do preco de saida
real. Isto NAO informa a regra (seria look-ahead) -- e' so' para responder
"o stop foi seguido de reversao de volta a favor (whipsaw) ou de
continuacao adversa (o stop se justificou)?", puramente descritivo.

Uso: `python -u scripts/daytrade/copa_win_reversal_exit_lab_2026_08_27.py`
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

import copa_lab as L  # noqa: E402
from run_copa_score import CALIBRACAO_IS  # noqa: E402

SYMBOL = "WIN@"
TRADE_LOG_CSV = ROOT / "scripts" / "daytrade" / "capital_ladder_copawin_n1_trades_2026_08_27.csv"
MFE_MAE_CSV_OUT = ROOT / "scripts" / "daytrade" / "copa_win_reversal_exit_mfe_mae_2026_08_27.csv"
CALIBRACAO_CSV_OUT = ROOT / "scripts" / "daytrade" / "copa_win_reversal_exit_calibracao_metade1_2026_08_27.csv"
RESULTADO_CSV_OUT = ROOT / "scripts" / "daytrade" / "copa_win_reversal_exit_trades_metade2_2026_08_27.csv"

#: Piso de armamento da regra -- reusa `vol_min_ticks` da propria calibracao
#: campea (ver docstring do modulo). NAO e' calibrado aqui.
FLOOR_TICKS = float(CALIBRACAO_IS[SYMBOL]["vol_min_ticks"])

#: Grade do UNICO parametro livre (fracao de retracao do MFE). Calibrada so'
#: na metade 1.
GRID_X = [round(0.1 * i, 1) for i in range(1, 10)]  # 0.1 .. 0.9

#: Janela de contexto (barras M1) DEPOIS da saida real -- so' diagnostico,
#: nunca entra na regra. Clampada na virada do pregao.
POS_EXIT_BARRAS = 10


# ---------------------------------------------------------------------------
# trade log -- mesma leitura de `copa_win_entry_quality_lab_2026_08_27.py`
# ---------------------------------------------------------------------------

def carrega_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["entry_ts", "exit_ts"])
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    df = df.sort_values("entry_ts").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# fronteira de pregao (para clampar a janela DE CONTEXTO pos-saida)
# ---------------------------------------------------------------------------

def _dia_fim_pos(bars: pd.DataFrame) -> np.ndarray:
    """Para cada barra, a posicao (indice inteiro) da ULTIMA barra do MESMO
    pregao -- usada so' para clampar a janela de contexto pos-saida."""
    datas = np.asarray(bars.index.date)
    n = len(datas)
    troca_prox = np.concatenate((datas[1:] != datas[:-1], [True]))
    fins = np.where(troca_prox)[0]
    dia_id = np.cumsum(np.concatenate(([True], datas[1:] != datas[:-1]))) - 1
    return fins[dia_id]


# ---------------------------------------------------------------------------
# caminho de preco por trade: MFE/MAE completos + arrays de gatilho
# (prefixo estritamente ANTES da barra de saida) + contexto pos-saida
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
    mfe_ticks: float
    mae_ticks: float
    pos_exit_fav_ticks: float           # contexto: excursao favoravel MAXIMA nas ate POS_EXIT_BARRAS apos a saida
    # arrays de gatilho, SO' para barras estritamente antes da saida (podem ser vazios)
    trig_running_mfe_ticks: np.ndarray
    trig_giveback_ticks: np.ndarray
    trig_close_price: np.ndarray


def constroi_paths(trades: pd.DataFrame, bars: pd.DataFrame, tick_size: float) -> tuple[list[TradePath], int]:
    idx = bars.index
    highs = bars["high"].to_numpy(dtype=np.float64)
    lows = bars["low"].to_numpy(dtype=np.float64)
    closes = bars["close"].to_numpy(dtype=np.float64)
    dia_fim = _dia_fim_pos(bars)

    entry_pos_arr = idx.get_indexer(pd.to_datetime(trades["entry_ts"], utc=True))
    exit_pos_arr = idx.get_indexer(pd.to_datetime(trades["exit_ts"], utc=True))

    out: list[TradePath] = []
    sem_match = 0
    for row, epos, xpos in zip(trades.itertuples(index=False), entry_pos_arr, exit_pos_arr):
        if epos < 0 or xpos < 0:
            sem_match += 1
            continue
        side = row.side
        entry_price = float(row.entry_price)

        h = highs[epos:xpos + 1]
        l = lows[epos:xpos + 1]
        c = closes[epos:xpos + 1]
        if side == "long":
            fav = h - entry_price
            close_fav = c - entry_price
        else:
            fav = entry_price - l
            close_fav = entry_price - c
        running_mfe = np.maximum.accumulate(fav)
        mfe_ticks = float(running_mfe[-1] / tick_size)

        if side == "long":
            adv = entry_price - l
        else:
            adv = h - entry_price
        running_mae = np.maximum.accumulate(adv)
        mae_ticks = float(running_mae[-1] / tick_size)

        # ---- arrays de gatilho: barras estritamente ANTES da saida ----
        trig_running_mfe_ticks = running_mfe[:-1] / tick_size
        trig_close_fav = close_fav[:-1]
        trig_giveback_ticks = (running_mfe[:-1] - trig_close_fav) / tick_size
        trig_close_price = c[:-1]

        # ---- contexto pos-saida (nao entra na regra) ----
        fim = dia_fim[xpos]
        janela_fim = min(xpos + POS_EXIT_BARRAS, fim)
        if janela_fim > xpos:
            h_pos = highs[xpos + 1:janela_fim + 1]
            l_pos = lows[xpos + 1:janela_fim + 1]
            exit_price = float(row.exit_price)
            if side == "long":
                pos_fav = float((h_pos - exit_price).max() / tick_size)
            else:
                pos_fav = float((exit_price - l_pos).max() / tick_size)
        else:
            pos_fav = float("nan")

        out.append(TradePath(
            entry_ts=row.entry_ts, exit_ts=row.exit_ts, side=side,
            entry_price=entry_price, exit_price=float(row.exit_price),
            quantity=int(row.quantity), pnl_brl=float(row.pnl_brl),
            exit_reason=str(row.exit_reason), mfe_ticks=mfe_ticks, mae_ticks=mae_ticks,
            pos_exit_fav_ticks=pos_fav,
            trig_running_mfe_ticks=trig_running_mfe_ticks,
            trig_giveback_ticks=trig_giveback_ticks,
            trig_close_price=trig_close_price,
        ))
    return out, sem_match


def salva_mfe_mae_csv(paths: list[TradePath], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["entry_ts", "exit_ts", "side", "exit_reason", "pnl_brl",
                    "mfe_ticks", "mae_ticks", "pos_exit_fav_ticks_10b"])
        for p in paths:
            w.writerow([p.entry_ts.isoformat(), p.exit_ts.isoformat(), p.side, p.exit_reason,
                        p.pnl_brl, p.mfe_ticks, p.mae_ticks, p.pos_exit_fav_ticks])


# ---------------------------------------------------------------------------
# simulacao da regra para um X dado -- vetorizavel por trade (arrays ja
# precomputados em `constroi_paths`)
# ---------------------------------------------------------------------------

@dataclass
class ResultadoSimulado:
    triggered: bool
    exit_price_sim: float
    pnl_sim: float


def _lado_saida(side: str) -> str:
    return "sell" if side == "long" else "buy"


def simula_trade(p: TradePath, x: float, costs) -> ResultadoSimulado:
    mfe = p.trig_running_mfe_ticks
    if mfe.size == 0:
        return ResultadoSimulado(False, p.exit_price, p.pnl_brl)
    armado = mfe >= FLOOR_TICKS
    dispara = armado & (p.trig_giveback_ticks >= x * mfe)
    onde = np.flatnonzero(dispara)
    if onde.size == 0:
        return ResultadoSimulado(False, p.exit_price, p.pnl_brl)
    t = int(onde[0])
    preco_bruto = float(p.trig_close_price[t])
    preco_saida = apply_intraday_slippage(preco_bruto, _lado_saida(p.side), costs)
    bruto = gross_pnl_brl(p.entry_price, preco_saida, p.quantity, p.side, costs)
    liquido = bruto - fees_round_trip_brl(p.quantity, p.entry_price, preco_saida, costs)
    return ResultadoSimulado(True, preco_saida, liquido)


def simula_grupo(paths: list[TradePath], x: float, costs) -> list[ResultadoSimulado]:
    return [simula_trade(p, x, costs) for p in paths]


# ---------------------------------------------------------------------------
# calibracao por grade -- SO' na metade 1
# ---------------------------------------------------------------------------

@dataclass
class LinhaGrade:
    x: float
    n_triggered: int
    pnl_atual: float
    pnl_sim: float
    delta: float
    maxdd_atual: float
    maxdd_sim: float


def _curva(pnls: list[float]) -> pd.Series:
    return pd.Series(np.concatenate(([0.0], np.cumsum(pnls))))


def avalia_x(paths: list[TradePath], x: float, costs) -> LinhaGrade:
    sims = simula_grupo(paths, x, costs)
    pnl_atual = [p.pnl_brl for p in paths]
    pnl_sim = [s.pnl_sim for s in sims]
    return LinhaGrade(
        x=x, n_triggered=sum(1 for s in sims if s.triggered),
        pnl_atual=float(sum(pnl_atual)), pnl_sim=float(sum(pnl_sim)),
        delta=float(sum(pnl_sim) - sum(pnl_atual)),
        maxdd_atual=maxdd_brl(_curva(pnl_atual)), maxdd_sim=maxdd_brl(_curva(pnl_sim)),
    )


def calibra_grade(metade1: list[TradePath], costs) -> tuple[list[LinhaGrade], float]:
    linhas = [avalia_x(metade1, x, costs) for x in GRID_X]
    melhor = max(linhas, key=lambda ln: ln.pnl_sim)
    return linhas, melhor.x


def salva_calibracao_csv(linhas: list[LinhaGrade], path: Path) -> None:
    campos = [f.name for f in dataclasses.fields(LinhaGrade)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(campos)
        for ln in linhas:
            w.writerow([getattr(ln, c) for c in campos])


# ---------------------------------------------------------------------------
# teste mecanico na metade 2 -- decomposicao perdedores vs vencedores
# ---------------------------------------------------------------------------

@dataclass
class LinhaMetade2:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    side: str
    exit_reason_atual: str
    pnl_atual: float
    triggered: bool
    pnl_sim: float


def testa_metade2(metade2: list[TradePath], x_estrela: float, costs) -> list[LinhaMetade2]:
    sims = simula_grupo(metade2, x_estrela, costs)
    return [
        LinhaMetade2(entry_ts=p.entry_ts, exit_ts=p.exit_ts, side=p.side,
                     exit_reason_atual=p.exit_reason, pnl_atual=p.pnl_brl,
                     triggered=s.triggered, pnl_sim=s.pnl_sim)
        for p, s in zip(metade2, sims)
    ]


def salva_metade2_csv(linhas: list[LinhaMetade2], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["entry_ts", "exit_ts", "side", "exit_reason_atual", "pnl_atual", "triggered", "pnl_sim"])
        for ln in linhas:
            w.writerow([ln.entry_ts.isoformat(), ln.exit_ts.isoformat(), ln.side,
                        ln.exit_reason_atual, ln.pnl_atual, ln.triggered, ln.pnl_sim])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    bars = L.barras(SYMBOL).in_sample()
    print(f"[reversal_exit] {SYMBOL} IN-SAMPLE: {L.descreve_janela(bars)}")
    print(f"[reversal_exit] trade log: {TRADE_LOG_CSV}")

    trades = carrega_trades(TRADE_LOG_CSV)
    print(f"[reversal_exit] {len(trades)} trades carregados "
          f"(liquido = R${num_br(float(trades['pnl_brl'].sum()))})")

    cfg = L.config(SYMBOL, 1)
    tick_size = cfg.costs.tick_size
    costs = cfg.costs
    print(f"[reversal_exit] tick_size={tick_size} pontos | FLOOR_TICKS={num_br(FLOOR_TICKS,1)} "
          f"(= vol_min_ticks da CALIBRACAO_IS) | grade de X: {GRID_X} | "
          f"janela de contexto pos-saida={POS_EXIT_BARRAS} barras")

    paths, sem_match = constroi_paths(trades, bars, tick_size)
    print(f"[reversal_exit] caminhos reconstruidos para {len(paths)}/{len(trades)} trades "
          f"({sem_match} sem barra correspondente -- deveria ser 0)")
    salva_mfe_mae_csv(paths, MFE_MAE_CSV_OUT)
    print(f"[reversal_exit] MFE/MAE por trade salvos em {MFE_MAE_CSV_OUT}")

    # ---------------- MFE vs MAE: simetria ou assimetria? ----------------
    mfe_arr = np.array([p.mfe_ticks for p in paths])
    mae_arr = np.array([p.mae_ticks for p in paths])
    pnl_arr = np.array([p.pnl_brl for p in paths])
    print("\n=== MFE vs MAE (ticks) -- toda a amostra, ANTES da saida real ===")
    print(f"{'grupo':<22}{'n':>6}{'MFE medio':>12}{'MFE mediana':>13}"
          f"{'MAE medio':>12}{'MAE mediana':>13}{'MFE-MAE (medio)':>18}")
    print("-" * 96)

    def _linha(nome: str, mask: np.ndarray) -> None:
        if mask.sum() == 0:
            print(f"{nome:<22}{0:>6}")
            return
        mfe_m, mfe_md = mfe_arr[mask].mean(), np.median(mfe_arr[mask])
        mae_m, mae_md = mae_arr[mask].mean(), np.median(mae_arr[mask])
        print(f"{nome:<22}{int(mask.sum()):>6}{num_br(mfe_m,2):>12}{num_br(mfe_md,2):>13}"
              f"{num_br(mae_m,2):>12}{num_br(mae_md,2):>13}{num_br(mfe_m-mae_m,2):>18}")

    todos = np.ones(len(paths), dtype=bool)
    _linha("todos", todos)
    _linha("vencedores (pnl>0)", pnl_arr > 0)
    _linha("perdedores (pnl<=0)", pnl_arr <= 0)
    for motivo in ("stop", "target", "forced_flatten"):
        _linha(f"exit={motivo}", np.array([p.exit_reason for p in paths]) == motivo)

    # ---------------- oportunidade de reversao: perdedores/stop com MFE relevante ----------------
    stop_mask = np.array([p.exit_reason == "stop" for p in paths])
    perdedor_mask = pnl_arr <= 0
    for nome, mask in (("saida por STOP", stop_mask), ("P&L negativo", perdedor_mask)):
        n = int(mask.sum())
        com_mfe = int((mask & (mfe_arr >= FLOOR_TICKS)).sum())
        print(f"\n[reversal_exit] entre {n} trades com {nome}: {com_mfe} "
              f"({num_br(100.0*com_mfe/n,1) if n else '-'}%.) chegaram a ter MFE >= "
              f"{num_br(FLOOR_TICKS,1)} ticks (piso de armamento) antes de fechar -- "
              f"MFE medio nesse subgrupo = {num_br(mfe_arr[mask & (mfe_arr>=FLOOR_TICKS)].mean(),2) if com_mfe else '-'} ticks")

    # ---------------- contexto pos-saida (STOP vs TARGET) ----------------
    print("\n=== contexto: excursao favoravel MAXIMA nas 10 barras APOS a saida real "
          "(nao entra na regra, so' diagnostico) ===")
    for motivo in ("stop", "target", "forced_flatten"):
        vals = np.array([p.pos_exit_fav_ticks for p in paths if p.exit_reason == motivo])
        vals = vals[~np.isnan(vals)]
        if len(vals):
            print(f"  exit={motivo:<15} n={len(vals):>5} | media={num_br(vals.mean(),2)} ticks | "
                  f"mediana={num_br(float(np.median(vals)),2)} ticks")

    # ---------------- split cronologico ----------------
    meio = len(paths) // 2
    metade1, metade2 = paths[:meio], paths[meio:]
    print(f"\n[reversal_exit] split cronologico: metade1 n={len(metade1)} "
          f"({metade1[0].entry_ts:%Y-%m-%d} -> {metade1[-1].entry_ts:%Y-%m-%d}) | "
          f"metade2 n={len(metade2)} ({metade2[0].entry_ts:%Y-%m-%d} -> {metade2[-1].entry_ts:%Y-%m-%d})")

    # ---------------- calibracao da grade, SO' na metade 1 ----------------
    linhas_grade, x_estrela = calibra_grade(metade1, costs)
    salva_calibracao_csv(linhas_grade, CALIBRACAO_CSV_OUT)
    print(f"\n=== calibracao de X -- GRADE COMPLETA na METADE 1 (n={len(metade1)} trades) ===")
    print(f"{'X':>6}{'triggered':>11}{'pnl atual':>14}{'pnl sim':>14}{'delta':>12}"
          f"{'maxdd atual':>14}{'maxdd sim':>12}")
    print("-" * 85)
    for ln in linhas_grade:
        print(f"{num_br(ln.x,1):>6}{ln.n_triggered:>11}{num_br(ln.pnl_atual):>14}"
              f"{num_br(ln.pnl_sim):>14}{num_br(ln.delta):>12}"
              f"{num_br(ln.maxdd_atual):>14}{num_br(ln.maxdd_sim):>12}")
    print(f"\n[reversal_exit] X* escolhido na metade1 (maior pnl simulado) = {num_br(x_estrela,1)}")
    print(f"[reversal_exit] tabela de calibracao salva em {CALIBRACAO_CSV_OUT}")

    # ---------------- teste MECANICO na metade 2, X fixo ----------------
    linhas_m2 = testa_metade2(metade2, x_estrela, costs)
    salva_metade2_csv(linhas_m2, RESULTADO_CSV_OUT)

    pnl_atual_m2 = np.array([ln.pnl_atual for ln in linhas_m2])
    pnl_sim_m2 = np.array([ln.pnl_sim for ln in linhas_m2])
    trig_m2 = np.array([ln.triggered for ln in linhas_m2])

    print(f"\n=== TESTE MECANICO na METADE 2 (n={len(linhas_m2)}), X*={num_br(x_estrela,1)} "
          f"vindo SO' da metade 1 ===")
    print(f"trades onde a regra disparou ANTES da saida real: {int(trig_m2.sum())}/{len(linhas_m2)} "
          f"({num_br(100.0*trig_m2.sum()/len(linhas_m2),1)}%)")
    print(f"P&L medio por trade -- ATUAL: R${num_br(pnl_atual_m2.mean())} | "
          f"SIMULADO: R${num_br(pnl_sim_m2.mean())} | diferenca: R${num_br(pnl_sim_m2.mean()-pnl_atual_m2.mean())}")
    print(f"P&L total           -- ATUAL: R${num_br(pnl_atual_m2.sum())} | "
          f"SIMULADO: R${num_br(pnl_sim_m2.sum())} | diferenca: R${num_br(pnl_sim_m2.sum()-pnl_atual_m2.sum())}")
    print(f"MaxDD               -- ATUAL: R${num_br(maxdd_brl(_curva(list(pnl_atual_m2))))} | "
          f"SIMULADO: R${num_br(maxdd_brl(_curva(list(pnl_sim_m2))))}")

    # decomposicao: perdedores originais vs vencedores originais (na metade 2)
    era_perdedor = pnl_atual_m2 <= 0
    era_vencedor = pnl_atual_m2 > 0
    delta = pnl_sim_m2 - pnl_atual_m2
    print("\n--- decomposicao (metade 2): efeito SEPARADO em quem era perdedor vs vencedor ---")
    for nome, mask in (("ERA PERDEDOR (pnl<=0)", era_perdedor), ("ERA VENCEDOR (pnl>0)", era_vencedor)):
        n = int(mask.sum())
        n_trig = int((mask & trig_m2).sum())
        soma_delta = float(delta[mask].sum())
        media_delta = float(delta[mask].mean()) if n else 0.0
        print(f"  {nome:<24} n={n:>4} | disparou={n_trig:>4} | "
              f"delta total (sim-atual)=R${num_br(soma_delta)} | delta medio/trade=R${num_br(media_delta)}")

    print("\n[reversal_exit] trades simulados da metade 2 salvos em", RESULTADO_CSV_OUT)


if __name__ == "__main__":
    main()
