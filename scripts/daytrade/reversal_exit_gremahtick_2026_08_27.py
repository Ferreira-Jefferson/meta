"""SINAL DE SAIDA ANTECIPADA (reversao) da `GremahTick` (PMAM3, motor tick),
2026-08-27 -- terceira etapa da mesma investigacao (depois da "Escada de
capital" e da "Qualidade de sinal DE ENTRADA"). Pergunta desta etapa: nos
trades que fecham mal (stop ou pnl negativo), o preco chegou a rodar a favor
(MFE positivo) ANTES de reverter contra a posicao? Se sim, uma regra de saida
por reversao, sem look-ahead, poderia ter evitado ou reduzido a perda -- ao
custo de cortar cedo demais alguns vencedores?

## Entrada de dado (reaproveitada, nao recalculada)

Trade log: `scratch/scripts/capital_ladder_gremahtick_pmam3_n1_trades_2026_08_27.
csv` (1.310 trades, N=1 lote fixo, PMAM3, motor tick, IS puro -- o MESMO
arquivo das duas etapas anteriores). Barras: `_geometria_comum.carregar_is
("PMAM3", motor="tick")` -- a MESMA funcao, mesmo corte `OOS_CUTOFF`
congelado, `unlock()` nunca chamado. Casamento trade->tick de ENTRADA
reaproveita literalmente `casa_trades_com_ticks` de
`signal_quality_gremahtick_2026_08_27.py` (import, nao copia): 1.276/1.310
trades casados, as mesmas 34 exclusoes ja documentadas la'.

## Casamento da SAIDA -- por que timestamp, nao preco

A saida (`exit_price`) as vezes inclui `slippage_total` (ex.: no 1o trade do
log, slippage=R$1,00 = 1 tick), entao nem sempre bate exato com o close de
algum tick real -- tentar casar por PRECO como na entrada devolveria "sem
match" numa fatia dos stops/forced_flatten sem necessidade. Em vez disso
usa-se `bars_index.searchsorted(exit_ts, side="right") - 1`: a posicao do
ULTIMO tick com timestamp <= exit_ts. Verificado empiricamente antes de
escrever a analise: 93,7% dos casamentos por timestamp caem EXATO no preco de
saida registrado (diff < 1e-6), e o maior desvio entre os 6,3% restantes e'
de 3 ticks (R$0,03) -- consistente com slippage real de stop/forced_flatten,
nao um bug de casamento. Nenhum trade teve `exit_pos < entry_pos`.

## MFE / MAE -- definicao

Para cada trade casado, com `ep`=posicao do tick de entrada e `xp`=posicao do
tick de saida (por timestamp, acima), o CAMINHO de preco e' `closes[ep:xp+1]`
e o P&L marcado a mercado em cada ponto do caminho (BRUTO -- sem taxas/
slippage, mesma convencao usada nas duas etapas anteriores para "excursao")
e':

    pnl_path[j] = sinal * (closes[j] - entry_price) * quantity * point_value_brl

`sinal = +1` se long, `-1` se short. Como o proprio ponto de entrada (j=ep)
entra no caminho com pnl=0, `MFE = max(pnl_path) >= 0` e `MAE = min(pnl_path)
<= 0` SEMPRE (a excursao "trivial" de nao se mover e' o piso/teto natural).
Em PMAM3 motor tick, 1 tick = R$0,01 e quantity*point_value_brl = 100, entao
1 tick de excursao = R$1,00 exatos -- usado para converter BRL<->ticks sem
reler `symbol_economics`.

## A REGRA DE REVERSAO TESTADA (uma so', como pedido)

"Depois que a posicao ja acumulou pelo menos 1 tick de excursao favoravel
(MFE_corrente >= ARM_TICKS, `ARM_TICKS=1` FIXO -- com menos de 1 tick de
folga acumulada nao ha nada real para 'devolver', so' ruido), sair se o preco
DEVOLVER (retrair) uma fracao X do MFE_corrente ja atingido." Formalmente, a
cada tick `j` do caminho, computado APENAS com dado ate' `j` (sem
look-ahead):

    peak_ticks_ate_j   = max(pnl_path[ep..j]) / 1 tick
    giveback_ticks_j   = (peak_ate_j - pnl_path[j]) / 1 tick
    dispara em j se peak_ticks_ate_j >= ARM_TICKS E giveback_ticks_j >= X * peak_ticks_ate_j

X e' o UNICO parametro calibrado: grade de 0%,10%,...,100% testada na METADE1
cronologica dos trades casados (maximizando P&L TOTAL simulado na metade1);
o X vencedor e' aplicado MECANICAMENTE (sem recalibrar) na metade2 -- mesmo
padrao de split cronologico das duas etapas anteriores.

Se a regra dispara em `j < xp` (antes da saida real), o trade simulado fecha
em `j` com `pnl_simulado = pnl_path[j] - fees_total_original` (aproximacao:
reusa a MESMA taxa do trade original, zera slippage hipotetico -- nao ha' como
saber o slippage de uma saida que nunca aconteceu de verdade; declarado como
limitacao, nao escondido). Se nunca dispara antes de `xp`, o trade simulado
e' EXATAMENTE o original (`pnl_brl` da CSV, ja liquido de taxa e slippage
reais).

## O que NAO fizemos

Nao reconstruimos o "anchor" real da estrategia (mesma limitacao ja
documentada em `signal_quality_gremahtick_2026_08_27.py`: na fase rolante ele
e' um estado interno do motor, nao reconstruivel so' com barras+trade log).
A regra de reversao usa so' `entry_price` (dado do proprio trade), nunca o
anchor. Tambem nao testamos a variante "K ticks seguidos de momentum
invertido" sugerida pela missao como alternativa -- a missao pede UMA regra;
escolhemos a de retracao do MFE por falar diretamente a pergunta central
(MFE positivo que reverteu).

Janela: SO' o trade log do IS (ja' filtrado nas etapas anteriores) e as
barras IS (`carregar_is`, corte `OOS_CUTOFF` congelado). Nada em `src/` foi
tocado; nenhum arquivo existente foi editado; nada commitado.

Uso:
    python -u scripts/daytrade/reversal_exit_gremahtick_2026_08_27.py
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

from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402

from _geometria_comum import carregar_economics, carregar_is  # noqa: E402
from signal_quality_gremahtick_2026_08_27 import casa_trades_com_ticks  # noqa: E402

# ---------------------------------------------------------------------------
# entrada
# ---------------------------------------------------------------------------
SYMBOL = "PMAM3"
MOTOR = "tick"
CSV_TRADE_LOG = ROOT / "scratch" / "scripts" / "capital_ladder_gremahtick_pmam3_n1_trades_2026_08_27.csv"

SCRATCH_DIR = ROOT / "scratch" / "scripts"
CSV_MFE_MAE = SCRATCH_DIR / "reversal_exit_gremahtick_mfe_mae_2026_08_27.csv"
CSV_CALIBRACAO = SCRATCH_DIR / "reversal_exit_gremahtick_calibracao_metade1_2026_08_27.csv"
CSV_METADE2 = SCRATCH_DIR / "reversal_exit_gremahtick_metade2_atual_vs_simulado_2026_08_27.csv"

ARM_TICKS = 1.0
GRID_X_PCT = list(range(0, 101, 10))  # 0%, 10%, ..., 100%
POST_WINDOW_TICKS = 20  # so' para a analise DESCRITIVA de "o que aconteceu depois do stop"


# ---------------------------------------------------------------------------
# caminho de preco por trade -- MFE/MAE, sem look-ahead na regra (ver abaixo)
# ---------------------------------------------------------------------------

@dataclass
class Caminhos:
    matched: np.ndarray
    entry_pos: np.ndarray
    exit_pos: np.ndarray
    mfe_brl: np.ndarray
    mae_brl: np.ndarray
    n_path_ticks: np.ndarray
    argmax_rel: np.ndarray  # posicao (relativa a entry_pos) onde o MFE ocorre


def casa_saidas_por_timestamp(exit_ts: pd.DatetimeIndex, bars_index: pd.DatetimeIndex) -> np.ndarray:
    """Posicao do ULTIMO tick com timestamp <= exit_ts (ver docstring do
    modulo: casamento por preco deixaria de fora stop/forced_flatten com
    slippage; por timestamp bate exato em 93,7% dos casos e o resto e' so'
    alguns ticks de slippage real)."""
    return bars_index.searchsorted(exit_ts, side="right") - 1


def computa_caminhos(df: pd.DataFrame, bars: pd.DataFrame, entry_pos: np.ndarray) -> Caminhos:
    bars_index = bars.index
    closes = bars["close"].to_numpy(dtype=np.float64)
    n = len(df)

    entry_price = df["entry_price"].to_numpy(dtype=np.float64)
    side = df["side"].to_numpy()
    qty = df["quantity"].to_numpy(dtype=np.float64)
    pv = df["point_value_brl"].to_numpy(dtype=np.float64)

    exit_ts = pd.DatetimeIndex(df["exit_ts"]).astype(bars_index.dtype)
    exit_pos_ts = casa_saidas_por_timestamp(exit_ts, bars_index)

    matched = entry_pos >= 0
    mfe_brl = np.full(n, np.nan)
    mae_brl = np.full(n, np.nan)
    n_path_ticks = np.full(n, np.nan)
    argmax_rel = np.full(n, np.nan)
    exit_pos = np.full(n, -1, dtype=np.int64)

    for i in range(n):
        if not matched[i]:
            continue
        ep, xp = int(entry_pos[i]), int(exit_pos_ts[i])
        if xp < ep:
            matched[i] = False  # nao deveria acontecer (verificado: nunca aconteceu) -- defensivo
            continue
        exit_pos[i] = xp
        sign = 1.0 if side[i] == "long" else -1.0
        path_close = closes[ep:xp + 1]
        pnl_path = sign * (path_close - entry_price[i]) * qty[i] * pv[i]
        mfe_brl[i] = pnl_path.max()
        mae_brl[i] = pnl_path.min()
        n_path_ticks[i] = xp - ep
        argmax_rel[i] = int(np.argmax(pnl_path))

    return Caminhos(matched=matched, entry_pos=entry_pos, exit_pos=exit_pos,
                     mfe_brl=mfe_brl, mae_brl=mae_brl, n_path_ticks=n_path_ticks, argmax_rel=argmax_rel)


# ---------------------------------------------------------------------------
# a regra de reversao -- simulacao tick a tick, SEM look-ahead: a cada ponto
# do caminho so' usa max/min do que ja' foi visto ATE ali.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResultadoRegra:
    pnl_simulado: float
    disparou_antes: bool
    pos_disparo: int | None  # posicao absoluta no array de bars, se disparou


def simula_regra_um_trade(ep: int, xp: int, closes: np.ndarray, entry_price: float, sign: float,
                           qty: float, pv: float, fees_original: float, pnl_original: float,
                           x_frac: float, arm_ticks: float, unit_brl_por_tick: float) -> ResultadoRegra:
    # `xp` (exclusivo) -- a regra so' conta como "disparo" se antecipa a saida
    # real; se a condicao so' fosse satisfeita EXATAMENTE no tick da saida
    # real (j==xp), nao houve antecipacao nenhuma e o trade deve permanecer
    # EXATAMENTE igual ao original (liquido de taxa e slippage reais, nao a
    # reconstrucao bruta) -- por isso o tick xp fica de fora do loop.
    peak = 0.0
    for j in range(ep + 1, xp):
        pnl_j = sign * (closes[j] - entry_price) * qty * pv
        if pnl_j > peak:
            peak = pnl_j
        peak_ticks = peak / unit_brl_por_tick
        if peak_ticks >= arm_ticks:
            giveback_ticks = (peak - pnl_j) / unit_brl_por_tick
            if giveback_ticks >= x_frac * peak_ticks and giveback_ticks > 0:
                pnl_sim = pnl_j - fees_original
                return ResultadoRegra(pnl_simulado=pnl_sim, disparou_antes=True, pos_disparo=j)
    return ResultadoRegra(pnl_simulado=pnl_original, disparou_antes=False, pos_disparo=None)


def simula_regra_lote(idx: np.ndarray, caminhos: Caminhos, df: pd.DataFrame, closes: np.ndarray,
                       x_frac: float, unit_brl_por_tick: float) -> pd.DataFrame:
    entry_price = df["entry_price"].to_numpy(dtype=np.float64)
    side = df["side"].to_numpy()
    qty = df["quantity"].to_numpy(dtype=np.float64)
    pv = df["point_value_brl"].to_numpy(dtype=np.float64)
    fees = df["fees_total"].to_numpy(dtype=np.float64)
    pnl_original = df["pnl_brl"].to_numpy(dtype=np.float64)

    linhas = []
    for i in idx:
        ep, xp = int(caminhos.entry_pos[i]), int(caminhos.exit_pos[i])
        sign = 1.0 if side[i] == "long" else -1.0
        r = simula_regra_um_trade(ep, xp, closes, entry_price[i], sign, qty[i], pv[i],
                                   fees[i], pnl_original[i], x_frac, ARM_TICKS, unit_brl_por_tick)
        linhas.append(dict(idx=i, pnl_original=pnl_original[i], pnl_simulado=r.pnl_simulado,
                            disparou_antes=r.disparou_antes))
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# resumo padrao (P&L total, por trade, MaxDD, win rate) -- mesmo formato das
# duas etapas anteriores.
# ---------------------------------------------------------------------------

def resumo(pnl: np.ndarray) -> dict:
    curva = pd.Series(np.concatenate([[0.0], np.cumsum(pnl)]))
    return dict(
        n=len(pnl),
        pnl_total=float(pnl.sum()),
        pnl_por_trade=float(pnl.mean()) if len(pnl) else 0.0,
        maxdd=maxdd_brl(curva),
        win_rate_pct=float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
    )


def imprime_resumo(nome: str, r: dict) -> None:
    print(f"  {nome}: n={r['n']} | P&L total=R${num_br(r['pnl_total'])} | "
          f"P&L/trade=R${num_br(r['pnl_por_trade'], 4)} | MaxDD=R${num_br(r['maxdd'])} | "
          f"win rate={num_br(r['win_rate_pct'], 1)}%")


# ---------------------------------------------------------------------------
# descritivo: o que aconteceu DEPOIS do stop (so' faz sentido pra stop --
# forced_flatten "depois" e' o pregao seguinte, outra posicao, irrelevante
# pra ESTE trade).
# ---------------------------------------------------------------------------

def janela_pos_stop(df: pd.DataFrame, caminhos: Caminhos, bars: pd.DataFrame) -> pd.DataFrame:
    bars_index = bars.index
    closes = bars["close"].to_numpy(dtype=np.float64)
    entry_price = df["entry_price"].to_numpy(dtype=np.float64)
    side = df["side"].to_numpy()
    qty = df["quantity"].to_numpy(dtype=np.float64)
    pv = df["point_value_brl"].to_numpy(dtype=np.float64)
    pnl_original = df["pnl_brl"].to_numpy(dtype=np.float64)

    linhas = []
    stops = np.nonzero((df["exit_reason"].to_numpy() == "stop") & caminhos.matched)[0]
    dia_exit = bars_index.date
    for i in stops:
        xp = int(caminhos.exit_pos[i])
        sign = 1.0 if side[i] == "long" else -1.0
        dia = dia_exit[xp]
        fim = xp
        while fim + 1 < len(bars_index) and dia_exit[fim + 1] == dia and (fim - xp) < POST_WINDOW_TICKS:
            fim += 1
        path_post = closes[xp:fim + 1]
        pnl_post = sign * (path_post - entry_price[i]) * qty[i] * pv[i]
        linhas.append(dict(
            idx=i, side=side[i], pnl_no_stop=pnl_original[i],
            n_ticks_pos_stop=fim - xp,
            melhor_pnl_pos_stop=float(pnl_post.max()),
            pior_pnl_pos_stop=float(pnl_post.min()),
            ficou_pior_ainda=bool(pnl_post.min() < pnl_post[0]),
        ))
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CSV_TRADE_LOG)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True, format="mixed")
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True, format="mixed")
    assert df["entry_ts"].is_monotonic_increasing, "trade log fora de ordem cronologica"
    print(f"[reversal_exit] trade log: {CSV_TRADE_LOG} -- {len(df)} trades, "
          f"{df['entry_ts'].min()} -> {df['entry_ts'].max()}")
    print(f"[reversal_exit] exit_reason: {dict(df['exit_reason'].value_counts())}")

    run_bars, profile, referencia = carregar_is(SYMBOL, motor=MOTOR)
    if run_bars.empty:
        raise SystemExit(f"[reversal_exit] sem dado local IS para {SYMBOL!r} (motor={MOTOR!r})")
    bars_index = run_bars.index
    closes = run_bars["close"].to_numpy(dtype=np.float64)
    print(f"[reversal_exit] IS: {len(run_bars)} ticks, {bars_index.min()} -> {bars_index.max()}")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    tick_size = economics.trade_tick_size
    unit_brl_por_tick = 100.0 * 1.0 * tick_size  # quantity=100, point_value_brl=1.0 em todo o log (verificado)
    assert (df["quantity"] == 100).all() and (df["point_value_brl"] == 1.0).all(), \
        "premissa 'quantity=100, point_value_brl=1.0 em todo trade' quebrou -- unit_brl_por_tick errado"
    print(f"[reversal_exit] tick_size={tick_size} -> 1 tick = R${num_br(unit_brl_por_tick, 4)} de P&L")

    entry_pos, sem_match = casa_trades_com_ticks(
        pd.DatetimeIndex(df["entry_ts"]).astype(bars_index.dtype),
        df["entry_price"].to_numpy(dtype=np.float64), bars_index, closes)
    print(f"[reversal_exit] casamento de ENTRADA: {len(df) - sem_match}/{len(df)} "
          f"({sem_match} sem match -- mesmas exclusoes da etapa 'qualidade de sinal')")

    caminhos = computa_caminhos(df, run_bars, entry_pos)
    n_matched = int(caminhos.matched.sum())
    print(f"[reversal_exit] casamento de SAIDA por timestamp: {n_matched}/{len(df)} trades com caminho valido")

    # sanity: diff entre exit_price registrado e o close do tick casado
    idx_m = np.nonzero(caminhos.matched)[0]
    diffs = np.abs(closes[caminhos.exit_pos[idx_m]] - df["exit_price"].to_numpy()[idx_m])
    print(f"[reversal_exit] sanity casamento de SAIDA: diff medio |exit_price - close(exit_pos)| = "
          f"R${num_br(float(diffs.mean()), 4)}, max=R${num_br(float(diffs.max()), 4)}, "
          f"frac exata(<1e-6)={num_br(float((diffs < 1e-6).mean()) * 100, 1)}%")

    df = df.copy()
    df["mfe_brl"] = caminhos.mfe_brl
    df["mae_brl"] = caminhos.mae_brl
    df["mfe_ticks"] = caminhos.mfe_brl / unit_brl_por_tick
    df["mae_ticks"] = caminhos.mae_brl / unit_brl_por_tick
    df["n_path_ticks"] = caminhos.n_path_ticks
    df["matched"] = caminhos.matched

    dfm = df[df["matched"]].reset_index(drop=True)
    idx_dfm = np.nonzero(caminhos.matched)[0]  # posicao original em df / caminhos, na mesma ordem de dfm

    dfm[["symbol", "side", "exit_reason", "entry_ts", "exit_ts", "entry_price", "exit_price",
         "pnl_brl", "mfe_brl", "mae_brl", "mfe_ticks", "mae_ticks", "n_path_ticks"]].to_csv(
        CSV_MFE_MAE, index=False)
    print(f"\n[reversal_exit] MFE/MAE por trade salvo em {CSV_MFE_MAE}")

    # ---------------- PARTE A: MFE/MAE descritivo ----------------
    print(f"\n=== {SYMBOL} motor={MOTOR} -- PARTE A: MFE / MAE (n={len(dfm)} trades casados) ===")

    print("\n-- por exit_reason --")
    for reason, g in dfm.groupby("exit_reason"):
        print(f"  {reason:<16} n={len(g):>5} | MFE medio={num_br(g.mfe_ticks.mean(), 3)} ticks | "
              f"MAE medio={num_br(g.mae_ticks.mean(), 3)} ticks | P&L medio=R${num_br(g.pnl_brl.mean(), 4)}")

    stops = dfm[dfm.exit_reason == "stop"]
    print(f"\n-- foco STOP (n={len(stops)}) --")
    print(f"  trades com MFE > 0 (rodou a favor antes do stop): {(stops.mfe_brl > 0).sum()}/{len(stops)}")
    print(f"  MFE ticks: min={num_br(stops.mfe_ticks.min(),3)} max={num_br(stops.mfe_ticks.max(),3)} "
          f"media={num_br(stops.mfe_ticks.mean(),3)}")
    print(f"  MAE ticks: media={num_br(stops.mae_ticks.mean(),3)} (distancia media do stop)")

    neg = dfm[dfm.pnl_brl < 0]
    print(f"\n-- foco PNL NEGATIVO, todos os motivos (n={len(neg)}) --")
    print(f"  trades com MFE > 0 antes da perda: {(neg.mfe_brl > 0).sum()}/{len(neg)} "
          f"({num_br(float((neg.mfe_brl > 0).mean()) * 100, 1)}%)")
    print(f"  MFE ticks entre os negativos: media={num_br(neg.mfe_ticks.mean(),3)} "
          f"mediana={num_br(neg.mfe_ticks.median(),3)}")
    print("  por exit_reason, dentro dos negativos:")
    for reason, g in neg.groupby("exit_reason"):
        print(f"    {reason:<16} n={len(g):>4} | frac com MFE>0={num_br(float((g.mfe_brl>0).mean())*100,1)}% | "
              f"MFE medio={num_br(g.mfe_ticks.mean(),3)} ticks")

    print(f"\n-- SIMETRIA MFE x MAE (todos os {len(dfm)} trades casados) --")
    print(f"  media MFE = {num_br(dfm.mfe_ticks.mean(), 4)} ticks | media |MAE| = {num_br(dfm.mae_ticks.abs().mean(), 4)} ticks "
          f"| razao MFE/|MAE| = {num_br(dfm.mfe_ticks.mean() / dfm.mae_ticks.abs().mean(), 2)}")
    print(f"  mediana MFE = {num_br(dfm.mfe_ticks.median(), 4)} ticks | mediana |MAE| = {num_br(dfm.mae_ticks.abs().median(), 4)} ticks")
    print("  (para comparacao: familia Copa WIN@/WDO@ documentou MFE~=MAE, achado registrado em memoria)")

    post = janela_pos_stop(df, caminhos, run_bars)
    if not post.empty:
        print(f"\n-- descritivo: o que aconteceu ATE {POST_WINDOW_TICKS} ticks DEPOIS do stop (n={len(post)}) --")
        print(f"  em quantos o preco ainda pioraria mais (novo pior ponto) apos o stop: "
              f"{int(post.ficou_pior_ainda.sum())}/{len(post)}")
        print(f"  melhor P&L alcancado na janela pos-stop (media, contrafactual 'nao teria saido'): "
              f"R${num_br(post.melhor_pnl_pos_stop.mean(), 4)} (comparar com o P&L NO stop, media R${num_br(post.pnl_no_stop.mean(),4)})")

    # ---------------- PARTE B: calibra X na metade1, aplica na metade2 ----------------
    print(f"\n\n=== {SYMBOL} motor={MOTOR} -- PARTE B: regra de reversao (retracao do MFE) ===")
    meio = len(dfm) // 2
    idx1 = idx_dfm[:meio]  # posicoes em `df`/`caminhos`, metade1 cronologica
    idx2 = idx_dfm[meio:]  # metade2 cronologica
    print(f"[reversal_exit] split cronologico: metade1 n={len(idx1)} ({dfm.entry_ts.iloc[0]} -> "
          f"{dfm.entry_ts.iloc[meio-1]}), metade2 n={len(idx2)} ({dfm.entry_ts.iloc[meio]} -> "
          f"{dfm.entry_ts.iloc[-1]})")

    print(f"\n-- calibracao de X na metade1 (grade {GRID_X_PCT[0]}%..{GRID_X_PCT[-1]}%, ARM_TICKS={ARM_TICKS} fixo) --")
    linhas_calib = []
    for x_pct in GRID_X_PCT:
        x_frac = x_pct / 100.0
        sim = simula_regra_lote(idx1, caminhos, df, closes, x_frac, unit_brl_por_tick)
        r = resumo(sim["pnl_simulado"].to_numpy())
        n_disp = int(sim["disparou_antes"].sum())
        linhas_calib.append(dict(x_pct=x_pct, n_disparos=n_disp, **r))
        print(f"  X={x_pct:>3}% | disparos={n_disp:>4}/{len(idx1)} | P&L total=R${num_br(r['pnl_total'])} | "
              f"P&L/trade=R${num_br(r['pnl_por_trade'],4)} | MaxDD=R${num_br(r['maxdd'])}")
    pd.DataFrame(linhas_calib).to_csv(CSV_CALIBRACAO, index=False)
    print(f"[reversal_exit] grade de calibracao salva em {CSV_CALIBRACAO}")

    melhor = max(linhas_calib, key=lambda r: r["pnl_total"])
    x_escolhido = melhor["x_pct"]
    baseline_metade1 = resumo(df["pnl_brl"].to_numpy()[idx1])
    print(f"\n[reversal_exit] X escolhido (maior P&L total na metade1) = {x_escolhido}% "
          f"(P&L metade1 com a regra=R${num_br(melhor['pnl_total'])} vs SEM regra=R${num_br(baseline_metade1['pnl_total'])})")
    if x_escolhido == 0:
        print("  ATENCAO: X=0% venceu -- e' o extremo da grade (sair no 1o tick que nao faz novo pico), "
              "sinal de que a regra em si nao ajuda nesta janela (grade nao teve otimo interior).")
    if x_escolhido == 100:
        print("  ATENCAO: X=100% venceu -- e' o outro extremo (so' sai devolvendo o MFE inteiro), "
              "equivalente a quase nunca disparar antes da saida real.")

    print(f"\n-- aplicacao MECANICA de X={x_escolhido}% na metade2 (fora da amostra de calibracao) --")
    sim2 = simula_regra_lote(idx2, caminhos, df, closes, x_escolhido / 100.0, unit_brl_por_tick)
    pnl_original2 = df["pnl_brl"].to_numpy()[idx2]
    atual = resumo(pnl_original2)
    simulado = resumo(sim2["pnl_simulado"].to_numpy())
    print("ATUAL (saida real, alvo/stop/forced_flatten):")
    imprime_resumo("atual", atual)
    print(f"SIMULADO (com a regra de reversao, X={x_escolhido}%):")
    imprime_resumo("simulado", simulado)

    disparou = sim2["disparou_antes"].to_numpy()
    era_perdedor = pnl_original2 < 0
    era_vencedor = pnl_original2 > 0
    cortados_perdedores = disparou & era_perdedor
    cortados_vencedores = disparou & era_vencedor

    ganho_em_perdedores = float((sim2.loc[cortados_perdedores, "pnl_simulado"].to_numpy()
                                  - pnl_original2[cortados_perdedores]).sum())
    perda_em_vencedores = float((sim2.loc[cortados_vencedores, "pnl_simulado"].to_numpy()
                                  - pnl_original2[cortados_vencedores]).sum())

    print(f"\n-- decomposicao do efeito na metade2 (n disparos={int(disparou.sum())}/{len(idx2)}) --")
    print(f"  disparos em trades que eram PERDEDORES no original: {int(cortados_perdedores.sum())} -- "
          f"ganho liquido (perda evitada/reduzida) = R${num_br(ganho_em_perdedores)}")
    print(f"  disparos em trades que eram VENCEDORES no original: {int(cortados_vencedores.sum())} -- "
          f"perda liquida (cortados cedo demais) = R${num_br(perda_em_vencedores)}")
    print(f"  saldo liquido do efeito = R${num_br(ganho_em_perdedores + perda_em_vencedores)} "
          f"(deveria bater com P&L simulado - P&L atual = R${num_br(simulado['pnl_total'] - atual['pnl_total'])})")

    out2 = dfm.iloc[meio:].copy()
    out2["pnl_simulado"] = sim2["pnl_simulado"].to_numpy()
    out2["disparou_antes"] = disparou
    out2[["symbol", "side", "exit_reason", "entry_ts", "pnl_brl", "pnl_simulado", "disparou_antes",
          "mfe_ticks", "mae_ticks"]].to_csv(CSV_METADE2, index=False)
    print(f"\n[reversal_exit] tabela trade-a-trade da metade2 (atual vs simulado) salva em {CSV_METADE2}")


if __name__ == "__main__":
    main()
