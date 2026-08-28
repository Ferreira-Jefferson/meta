"""SINAL DE SAIDA ANTECIPADA (reversao) -- familia GREMAH, PMAM3, motor M1
(2026-08-27), a partir do MESMO trade log ja gerado por
`capital_ladder_gremah_2026_08_27.py` (N=1 lote fixo, 1231 trades, mesmo IS:
`_geometria_comum.carregar_is("PMAM3", motor="m1")`, corte congelado em
`profiles.OOS_CUTOFF="2026-06-13"`, `LockedBars.unlock()` NUNCA chamado). Este
script NAO re-roda o motor: so' le' o CSV do trade log e as barras M1 do IS
(mesmo loader de todas as etapas anteriores).

## Pergunta do dono

Para cada trade, reconstruir o caminho de preco entre entrada e saida (e um
pouco alem da saida real) e medir MFE (excursao maxima favoravel) / MAE
(excursao maxima adversa) atingidas ANTES da saida real. Focar em trades que
saem por STOP ou com P&L negativo: houve excursao favoravel que reverteu?
Propor e testar UMA regra de saida por reversao SEM look-ahead, calibrada na
metade 1 do IS e testada MECANICAMENTE (sem recalibrar) na metade 2.

## Por que MFE/MAE do "toque" do stop podem estar contaminados (achado, nao
suposicao) -- `_resolve_stop_target_hit` (`backtest/intraday/machine.py`)

Quando STOP e TARGET tocam na MESMA barra M1, o motor usa
`ambiguous_bar_resolution="stop_first"` (default) -- ou seja, um trade
rotulado "stop" pode muito bem ter tido a barra de saida tocando TAMBEM o
nivel de alvo (so' nao sabemos a ordem intrabar com dado OHLC de 1 minuto).
Isso e' justamente o tipo de "excursao favoravel que reverteu" que a
pergunta do dono busca -- e da' suporte a olhar tambem a barra de saida em
separado da janela ANTES dela.

## Convencao de MFE/MAE (duas versoes, as duas reportadas)

  - `*_pre_exit`: SO' barras ESTRITAMENTE ANTES da barra de saida real
    (`bars[pos_entry:pos_exit]`, exclui a barra de saida). Sem ambiguidade
    de ordem intrabar -- e' o que se sabia ANTES do evento de saida
    acontecer. Trade de 1 barra so' (`pos_entry==pos_exit`) nao tem essa
    janela (fica `None`, contado a parte).
  - `*_full`: TODAS as barras do trade, INCLUSIVE a barra de saida
    (`bars[pos_entry:pos_exit+1]`). Mais completo (e' o que a literatura de
    MFE/MAE normalmente reporta), mas a barra de saida pode conter preco
    ALEM do nivel que fechou a posicao (o motor fecha exatamente no toque,
    nao no extremo da barra) -- pode SUPERESTIMAR levemente MFE/MAE dessa
    barra. Caveat divulgado, nao escondido.

## Regra de reversao testada (UMA so', sem look-ahead)

"Trailing stop sobre o MFE ja atingido": acompanha o pico favoravel (`MFE
ate agora`, so' com barras JA FECHADAS antes da barra corrente -- nunca
usa o proprio pico desta barra para disparar a saida NESTA barra, pra
nao ter circularidade "a barra cria o pico E dispara a saida dele"). Uma
vez que o pico > 0, calcula um NIVEL de preco = retracao de `X` fracao do
pico (mesma unidade de ticks da geometria do robo) e verifica TOQUE
(`bar.low`/`bar.high`) exatamente como `_stop_target_touch` do motor real;
se tocar, preenche no MESMO criterio de `_exit_fill_price` (nivel, ou o
`open` da barra se ela abriu em gap alem do nivel -- pior caso, igual ao
stop real). So' conta como "saida antecipada" se o toque acontecer
ESTRITAMENTE ANTES da barra de saida real (empate na mesma barra e'
descartado por ambiguidade de ordem intrabar -- ver acima -- e o trade
fica IGUAL ao real, escolha conservadora que nao infla o resultado da
regra).

`X` (unico parametro livre) e' calibrado na METADE 1 cronologica do IS
(grade 0,1..1,0 em passos de 0,1, objetivo = P&L medio/trade simulado
MAIOR na metade 1) e aplicado CRU (sem recalibrar) na METADE 2 -- mesmo
padrao de `gremah_signal_quality_2026_08_27.py::calibra_e_testa_filtro`.

## Custo da saida simulada

O motor real cobra custo (spread/taxa) que nao temos decomposto por perna
neste CSV -- so' o `pnl_brl` final. Assumindo que esse custo e'
aproximadamente FIXO por round-trip (medido: media R$-0,0586, desvio-padrao
R$0,016 nos 1231 trades reais -- variacao pequena frente a media, ver
`main()`), o P&L simulado de uma saida antecipada reusa o MESMO custo do
trade real: `pnl_sim = ticks_sim * tick_value * quantity + custo_trade_real`,
onde `custo_trade_real = pnl_real - ticks_real * tick_value * quantity`.
Aproximacao explicita, nao um novo modelo de custo.

Nenhum arquivo rastreado foi editado; nada foi commitado. Janela: IN-SAMPLE
apenas, OOS (`>=2026-06-13`) jamais tocado.

Uso: `python -u scripts/daytrade/gremah_reversal_signal_2026_08_27.py`
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

SYMBOL = "PMAM3"
MOTOR = "m1"

#: Trade log ja gerado pela etapa de escada de capital (N=1 lote fixo,
#: geometria/entradas/saidas da Gremah original intocadas). Este script NAO
#: re-roda o motor: so' le' o CSV e as barras do IS.
TRADE_LOG_CSV = ROOT / "scratch" / "scripts" / "capital_ladder_gremah_pmam3_n1_trades_2026_08_27.csv"

SCRATCH_DIR = ROOT / "scratch" / "scripts"
CSV_MFE_MAE = SCRATCH_DIR / "gremah_reversal_mfe_mae_trades_2026_08_27.csv"
CSV_CALIBRACAO = SCRATCH_DIR / "gremah_reversal_calibracao_metade1_2026_08_27.csv"
CSV_RESULTADO = SCRATCH_DIR / "gremah_reversal_resultado_metade2_2026_08_27.csv"

#: Quantas barras M1 olhar DEPOIS da saida real, so' descritivo (nunca entra
#: na regra nem na simulacao -- e' pra responder "o que aconteceu logo
#: depois", nao pra desenhar a regra com informacao do futuro).
POST_BARS = 15

#: Grade de calibracao do unico parametro livre da regra (fracao do MFE ja
#: atingido que, se devolvida, dispara a saida antecipada).
GRADE_X = tuple(round(x, 2) for x in np.arange(0.1, 1.01, 0.1))


# ---------------------------------------------------------------------------
# localizacao de barras por trade (vetorizado) + MFE/MAE descritivo
# ---------------------------------------------------------------------------

@dataclass
class TradeCtx:
    idx: int
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl_brl: float
    exit_reason: str
    pos_entry: int
    pos_exit: int
    n_bars: int
    mfe_full: float
    mae_full: float
    mfe_pre: float | None
    mae_pre: float | None
    ticks_real: float
    custo_trade: float


def _fav_adv(side: str, entry_price: float, high, low, tick_size: float):
    if side == "long":
        fav = (high - entry_price) / tick_size
        adv = (entry_price - low) / tick_size
    else:
        fav = (entry_price - low) / tick_size
        adv = (high - entry_price) / tick_size
    return fav, adv


def constroi_contexto(trades_df: pd.DataFrame, bars: pd.DataFrame, tick_size: float,
                       tick_value: float) -> tuple[list[TradeCtx], int]:
    idx = bars.index
    highs = bars["high"].to_numpy(dtype=np.float64)
    lows = bars["low"].to_numpy(dtype=np.float64)

    pos_entry_all = idx.get_indexer(pd.to_datetime(trades_df["entry_ts"], utc=True))
    pos_exit_all = idx.get_indexer(pd.to_datetime(trades_df["exit_ts"], utc=True))

    out: list[TradeCtx] = []
    sem_match = 0
    for i, row in enumerate(trades_df.itertuples(index=False)):
        pe, px = int(pos_entry_all[i]), int(pos_exit_all[i])
        if pe < 0 or px < 0 or px < pe:
            sem_match += 1
            continue
        side = row.side
        entry_price = float(row.entry_price)
        exit_price = float(row.exit_price)

        h_full = highs[pe:px + 1]
        l_full = lows[pe:px + 1]
        fav_full, adv_full = _fav_adv(side, entry_price, h_full, l_full, tick_size)
        mfe_full = float(fav_full.max())
        mae_full = float(adv_full.max())

        if px > pe:
            fav_pre, adv_pre = fav_full[:-1], adv_full[:-1]
            mfe_pre = float(fav_pre.max())
            mae_pre = float(adv_pre.max())
        else:
            mfe_pre = None
            mae_pre = None

        if side == "long":
            ticks_real = (exit_price - entry_price) / tick_size
        else:
            ticks_real = (entry_price - exit_price) / tick_size
        pnl_brl = float(row.pnl_brl)
        quantity = float(row.quantity)
        custo_trade = pnl_brl - ticks_real * tick_value * quantity

        out.append(TradeCtx(
            idx=i, side=side, entry_price=entry_price, exit_price=exit_price,
            quantity=quantity, pnl_brl=pnl_brl, exit_reason=row.exit_reason,
            pos_entry=pe, pos_exit=px, n_bars=(px - pe + 1),
            mfe_full=mfe_full, mae_full=mae_full, mfe_pre=mfe_pre, mae_pre=mae_pre,
            ticks_real=ticks_real, custo_trade=custo_trade,
        ))
    return out, sem_match


# ---------------------------------------------------------------------------
# regra de reversao: trailing stop sobre o MFE ja atingido (SEM look-ahead)
# ---------------------------------------------------------------------------

def simula_saida_antecipada(ctx: TradeCtx, opens: np.ndarray, highs: np.ndarray,
                             lows: np.ndarray, tick_size: float, x: float) -> tuple[int | None, float | None]:
    """Devolve `(pos_saida_sim, preco_saida_sim)` se a regra disparar
    ESTRITAMENTE ANTES da barra de saida real; `(None, None)` senao (trade
    fica IGUAL ao real). `running_mfe` so' usa barras JA FECHADAS antes da
    barra corrente -- a barra corrente so' e' usada para o TOQUE do nivel
    (igual a `_stop_target_touch`/`_exit_fill_price` do motor real), nunca
    para estabelecer o pico que ela mesma dispararia (sem circularidade)."""
    running_mfe = 0.0
    for pos in range(ctx.pos_entry, ctx.pos_exit):
        o, h, l = opens[pos], highs[pos], lows[pos]
        if running_mfe > 0.0:
            retracao_ticks = running_mfe * x
            nivel_ticks = running_mfe - retracao_ticks
            if ctx.side == "long":
                level = ctx.entry_price + nivel_ticks * tick_size
                if l <= level:
                    return pos, min(o, level)
            else:
                level = ctx.entry_price - nivel_ticks * tick_size
                if h >= level:
                    return pos, max(o, level)
        if ctx.side == "long":
            fav_bar = (h - ctx.entry_price) / tick_size
        else:
            fav_bar = (ctx.entry_price - l) / tick_size
        running_mfe = max(running_mfe, fav_bar)
    return None, None


def pnl_simulado(ctx: TradeCtx, exit_price_sim: float, tick_value: float, tick_size: float) -> float:
    if ctx.side == "long":
        ticks_sim = (exit_price_sim - ctx.entry_price) / tick_size
    else:
        ticks_sim = (ctx.entry_price - exit_price_sim) / tick_size
    return ticks_sim * tick_value * ctx.quantity + ctx.custo_trade


def roda_regra(trades: list[TradeCtx], opens: np.ndarray, highs: np.ndarray, lows: np.ndarray,
               tick_size: float, tick_value: float, x: float) -> pd.DataFrame:
    linhas = []
    for ctx in trades:
        pos_sim, preco_sim = simula_saida_antecipada(ctx, opens, highs, lows, tick_size, x)
        if pos_sim is None:
            pnl_sim = ctx.pnl_brl
            disparou = False
        else:
            pnl_sim = pnl_simulado(ctx, preco_sim, tick_value, tick_size)
            disparou = True
        linhas.append(dict(idx=ctx.idx, exit_reason=ctx.exit_reason, pnl_real=ctx.pnl_brl,
                            pnl_sim=pnl_sim, disparou=disparou))
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    run_bars, profile, referencia = carregar_is(SYMBOL, motor=MOTOR)
    if run_bars.empty:
        raise SystemExit(f"[reversal_signal] sem dado local IS para {SYMBOL!r} (motor={MOTOR!r})")
    pregoes_is = len(set(run_bars.index.date))
    print(f"[reversal_signal] {SYMBOL} motor={MOTOR} -- IS: {len(run_bars)} barras, "
          f"{pregoes_is} pregoes, {run_bars.index.min()} -> {run_bars.index.max()}")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    tick_size = economics.trade_tick_size
    tick_value = economics.trade_tick_value
    print(f"[reversal_signal] tick_size={tick_size} tick_value={tick_value}")

    if not TRADE_LOG_CSV.exists():
        raise SystemExit(f"[reversal_signal] trade log nao encontrado: {TRADE_LOG_CSV}")
    trades_df = pd.read_csv(TRADE_LOG_CSV)
    trades_df["entry_ts"] = pd.to_datetime(trades_df["entry_ts"], utc=True)
    trades_df["exit_ts"] = pd.to_datetime(trades_df["exit_ts"], utc=True)
    trades_df = trades_df.sort_values("entry_ts", kind="stable").reset_index(drop=True)
    print(f"[reversal_signal] trade log: {len(trades_df)} trades, "
          f"{trades_df['entry_ts'].min()} -> {trades_df['exit_ts'].max()}")

    trades, sem_match = constroi_contexto(trades_df, run_bars, tick_size, tick_value)
    print(f"[reversal_signal] contexto (MFE/MAE) construido para {len(trades)}/{len(trades_df)} "
          f"trades ({sem_match} sem barra correspondente -- deveria ser 0)")

    custo_arr = np.array([t.custo_trade for t in trades])
    print(f"[reversal_signal] custo estimado por trade (pnl_real - ticks_real*tick_value*qty): "
          f"media=R${num_br(custo_arr.mean(), 4)} desvio={num_br(custo_arr.std(ddof=1), 4)} "
          f"(assumido ~fixo por round-trip -- usado para precificar a saida simulada)")

    # ------------------------------------------------------------------
    # dump por-trade (MFE/MAE) -- auditoria/reproducao
    # ------------------------------------------------------------------
    pd.DataFrame([dict(
        idx=t.idx, exit_reason=t.exit_reason, pnl_brl=t.pnl_brl, n_bars=t.n_bars,
        mfe_full_ticks=t.mfe_full, mae_full_ticks=t.mae_full,
        mfe_pre_exit_ticks=t.mfe_pre, mae_pre_exit_ticks=t.mae_pre,
    ) for t in trades]).to_csv(CSV_MFE_MAE, index=False)
    print(f"[reversal_signal] MFE/MAE por trade salvo em {CSV_MFE_MAE}")

    # ------------------------------------------------------------------
    # 1) MFE/MAE -- foco em STOP / pnl negativo
    # ------------------------------------------------------------------
    print(f"\n=== 1. MFE/MAE -- {SYMBOL} motor={MOTOR}, {len(trades)} trades ===")

    def descreve(vals: np.ndarray, nome: str) -> None:
        if len(vals) == 0:
            print(f"  {nome}: n=0")
            return
        print(f"  {nome}: n={len(vals)} media={num_br(vals.mean(), 3)} mediana={num_br(np.median(vals), 3)} "
              f"min={num_br(vals.min(), 3)} max={num_br(vals.max(), 3)}")

    mfe_full_all = np.array([t.mfe_full for t in trades])
    mae_full_all = np.array([t.mae_full for t in trades])
    print("\n-- simetria MFE x MAE (janela completa, INCLUSIVE a barra de saida) --")
    descreve(mfe_full_all, "MFE_full (ticks)")
    descreve(mae_full_all, "MAE_full (ticks)")
    diff_full = mfe_full_all - mae_full_all
    print(f"  MFE_full - MAE_full: media={num_br(diff_full.mean(), 3)} "
          f"mediana={num_br(np.median(diff_full), 3)} "
          f"| razao media MFE/MAE = {num_br(mfe_full_all.mean() / mae_full_all.mean(), 3)}")

    pre_pairs = [(t.mfe_pre, t.mae_pre) for t in trades if t.mfe_pre is not None]
    n_single_bar = len(trades) - len(pre_pairs)
    print(f"\n-- simetria MFE x MAE (SO' barras ANTES da saida, exclui a barra de saida) -- "
          f"{n_single_bar} trades de 1 barra so' (sem janela pre-saida) ficam de fora --")
    if pre_pairs:
        mfe_pre_arr = np.array([p[0] for p in pre_pairs])
        mae_pre_arr = np.array([p[1] for p in pre_pairs])
        descreve(mfe_pre_arr, "MFE_pre (ticks)")
        descreve(mae_pre_arr, "MAE_pre (ticks)")
        diff_pre = mfe_pre_arr - mae_pre_arr
        print(f"  MFE_pre - MAE_pre: media={num_br(diff_pre.mean(), 3)} "
              f"mediana={num_br(np.median(diff_pre), 3)}")

    print("\n-- por exit_reason (janela completa) --")
    for reason in sorted({t.exit_reason for t in trades}):
        sub = [t for t in trades if t.exit_reason == reason]
        mfe_r = np.array([t.mfe_full for t in sub])
        mae_r = np.array([t.mae_full for t in sub])
        print(f"  {reason} (n={len(sub)}): MFE_full media={num_br(mfe_r.mean(), 3)} | "
              f"MAE_full media={num_br(mae_r.mean(), 3)}")

    # grupo de interesse: STOP ou pnl negativo
    grupo = [t for t in trades if t.exit_reason == "stop" or t.pnl_brl < 0]
    print(f"\n-- grupo de interesse (exit_reason=='stop' OU pnl_brl<0): {len(grupo)} trades --")
    por_motivo = pd.Series([t.exit_reason for t in grupo]).value_counts()
    print(f"  composicao por exit_reason: {dict(por_motivo)}")

    grupo_com_pre = [t for t in grupo if t.mfe_pre is not None]
    n_sem_pre = len(grupo) - len(grupo_com_pre)
    reverteu = [t for t in grupo_com_pre if t.mfe_pre > 0]
    print(f"  {len(grupo_com_pre)}/{len(grupo)} tem janela pre-saida ({n_sem_pre} sao trade de 1 "
          f"barra so', sem como medir 'antes')")
    if grupo_com_pre:
        frac = len(reverteu) / len(grupo_com_pre)
        print(f"  desses, {len(reverteu)}/{len(grupo_com_pre)} ({num_br(frac * 100, 1)}%) tiveram "
              f"MFE_pre > 0 -- ou seja, excursao favoravel real ANTES de reverter para stop/perda")
        if reverteu:
            mfe_rev = np.array([t.mfe_pre for t in reverteu])
            descreve(mfe_rev, "  MFE_pre entre os que reverteram (ticks)")

    # ------------------------------------------------------------------
    # 2) o que aconteceu POUCO DEPOIS da saida real (so' descritivo)
    # ------------------------------------------------------------------
    print(f"\n=== 2. o que aconteceu ate' {POST_BARS} barras DEPOIS da saida real "
          f"(so' descritivo, nunca usado na regra) ===")
    opens_all = run_bars["open"].to_numpy(dtype=np.float64)
    highs_all = run_bars["high"].to_numpy(dtype=np.float64)
    lows_all = run_bars["low"].to_numpy(dtype=np.float64)
    n_bars_total = len(run_bars)

    reversoes_pos_saida = []
    n_sem_janela_pos = 0
    for t in grupo:
        ini = t.pos_exit + 1
        fim = min(ini + POST_BARS, n_bars_total)
        if ini >= fim:
            n_sem_janela_pos += 1
            continue
        h = highs_all[ini:fim]
        l = lows_all[ini:fim]
        # "favoravel" aqui e' relativo ao preco de SAIDA, no MESMO lado do
        # trade que acabou de fechar (positivo = teria valido a pena
        # continuar/reentrar).
        if t.side == "long":
            fav_pos = float((h - t.exit_price).max() / tick_size)
        else:
            fav_pos = float((t.exit_price - l).max() / tick_size)
        reversoes_pos_saida.append(fav_pos)
    if reversoes_pos_saida:
        rev_arr = np.array(reversoes_pos_saida)
        frac_reverteu_pos = float((rev_arr > 0).mean())
        print(f"  grupo de interesse com janela pos-saida disponivel: {len(rev_arr)} "
          f"({n_sem_janela_pos} sem barras suficientes depois, fim do IS/pregao)")
        print(f"  fracao com ALGUMA excursao favoravel (>0 ticks) nos {POST_BARS} min seguintes "
              f"(mesma direcao do trade que fechou) = {num_br(frac_reverteu_pos * 100, 1)}%")
        descreve(rev_arr, "  excursao favoravel pos-saida (ticks)")
        print("  caveat: para trades 'forced_flatten' esta janela normalmente cruza para o "
              "PROXIMO pregao (robo nao opera overnight) -- reversao ali e' o pregao seguinte "
              "comecando, nao continuacao do mesmo regime intradiario.")

    # ------------------------------------------------------------------
    # 3) regra de reversao -- calibra na metade 1, testa CRU na metade 2
    # ------------------------------------------------------------------
    meio = len(trades) // 2
    metade1 = trades[:meio]
    metade2 = trades[meio:]
    print(f"\n=== 3. regra de reversao (trailing stop sobre o MFE) -- calibracao/teste ===")
    print(f"metade 1 (calibracao): {len(metade1)} trades | metade 2 (teste cru): {len(metade2)} trades")

    print(f"\n-- grade de calibracao na METADE 1 (objetivo: P&L medio/trade simulado) --")
    linhas_grade = []
    for x in GRADE_X:
        df1 = roda_regra(metade1, opens_all, highs_all, lows_all, tick_size, tick_value, x)
        pnl_medio_sim = df1["pnl_sim"].mean()
        pnl_medio_real = df1["pnl_real"].mean()
        n_disparou = int(df1["disparou"].sum())
        curva_sim = np.concatenate([[0.0], np.cumsum(df1["pnl_sim"].to_numpy())])
        maxdd_sim = maxdd_brl(pd.Series(curva_sim))
        linhas_grade.append(dict(x=x, n_disparou=n_disparou, pnl_medio_real=pnl_medio_real,
                                  pnl_medio_sim=pnl_medio_sim, maxdd_sim=maxdd_sim))
        print(f"  X={num_br(x, 2)} | disparou em {n_disparou}/{len(metade1)} trades | "
              f"P&L medio/trade real={num_br(pnl_medio_real, 4)} sim={num_br(pnl_medio_sim, 4)} | "
              f"MaxDD sim={num_br(maxdd_sim)}")
    df_grade = pd.DataFrame(linhas_grade)
    df_grade.to_csv(CSV_CALIBRACAO, index=False)
    print(f"[reversal_signal] grade de calibracao (metade 1) salva em {CSV_CALIBRACAO}")

    x_estrela = float(df_grade.loc[df_grade["pnl_medio_sim"].idxmax(), "x"])
    print(f"\nX* escolhido na metade 1 (maior P&L medio/trade simulado) = {num_br(x_estrela, 2)}")

    print(f"\n-- teste CRU na METADE 2 (X={num_br(x_estrela, 2)}, SEM recalibrar) --")
    df2 = roda_regra(metade2, opens_all, highs_all, lows_all, tick_size, tick_value, x_estrela)
    df2_ctx = pd.DataFrame([dict(idx=t.idx, exit_reason=t.exit_reason, pnl_real0=t.pnl_brl)
                             for t in metade2])
    df2 = df2.merge(df2_ctx, on=["idx", "exit_reason"], how="left")

    n2 = len(df2)
    n_disp2 = int(df2["disparou"].sum())
    pnl_medio_real2 = df2["pnl_real"].mean()
    pnl_medio_sim2 = df2["pnl_sim"].mean()
    pnl_total_real2 = df2["pnl_real"].sum()
    pnl_total_sim2 = df2["pnl_sim"].sum()
    curva_real2 = np.concatenate([[0.0], np.cumsum(df2["pnl_real"].to_numpy())])
    curva_sim2 = np.concatenate([[0.0], np.cumsum(df2["pnl_sim"].to_numpy())])
    maxdd_real2 = maxdd_brl(pd.Series(curva_real2))
    maxdd_sim2 = maxdd_brl(pd.Series(curva_sim2))

    print(f"  {n2} trades | regra disparou (saida antecipada) em {n_disp2} "
          f"({num_br(100 * n_disp2 / n2, 1)}%)")
    print(f"  P&L TOTAL: real=R${num_br(pnl_total_real2)} | sim=R${num_br(pnl_total_sim2)}")
    print(f"  P&L MEDIO/trade: real=R${num_br(pnl_medio_real2, 4)} | sim=R${num_br(pnl_medio_sim2, 4)}")
    print(f"  MaxDD (curva acumulada): real=R${num_br(maxdd_real2)} | sim=R${num_br(maxdd_sim2)}")

    disparados2 = df2[df2["disparou"]]
    perdedores_antes = disparados2[disparados2["pnl_real"] < 0]
    vencedores_antes = disparados2[disparados2["pnl_real"] >= 0]
    ganho_em_perdedores = float((perdedores_antes["pnl_sim"] - perdedores_antes["pnl_real"]).sum())
    perda_em_vencedores = float((vencedores_antes["pnl_sim"] - vencedores_antes["pnl_real"]).sum())
    print(f"\n  DENTRE OS {n_disp2} TRADES ONDE A REGRA DISPAROU (metade 2):")
    print(f"    eram PERDEDORES no real (pnl_real<0): {len(perdedores_antes)} trades -- "
          f"efeito liquido da regra = R${num_br(ganho_em_perdedores)} "
          f"({'reduziu/evitou perda' if ganho_em_perdedores > 0 else 'piorou'})")
    print(f"    eram VENCEDORES/empate no real (pnl_real>=0): {len(vencedores_antes)} trades -- "
          f"efeito liquido da regra = R${num_br(perda_em_vencedores)} "
          f"({'cortou ganho cedo demais' if perda_em_vencedores < 0 else 'nao piorou'})")
    print(f"    soma dos dois efeitos = R${num_br(ganho_em_perdedores + perda_em_vencedores)} "
          f"(bate com pnl_total_sim - pnl_total_real = R${num_br(pnl_total_sim2 - pnl_total_real2)})")

    df2.to_csv(CSV_RESULTADO, index=False)
    print(f"\n[reversal_signal] resultado por trade (metade 2, atual vs simulado) salvo em {CSV_RESULTADO}")


if __name__ == "__main__":
    main()
