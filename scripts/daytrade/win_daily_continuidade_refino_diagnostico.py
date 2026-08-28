"""DIAGNOSTICO da degradacao metade1->metade2 do candidato
`continuidade_diaria_reversal` em WIN@ (+R$8.832,30 IS, 127 trades, 55,9%
acerto; metade1 lucro/DD=2,26, metade2 lucro/DD=0,34) -- RODADA DE REFINO
pedida pelo dono em cima do estagio B da rodada `continuidade_*`
(2026-08-27): "ele teve algum ganho, o que se pode fazer e' refinar ele,
ver o que faz com que numa segunda rodada ele pare de ganhar."

Reusa (IMPORTA, nunca copia/cola) `carregar_is_bars` de
`continuidade_stats.py` e `_metade`, `_series_bruto_custo`,
`nulo_sign_flip`, `rodar`, `_config`, `DIRECTION_BY_SYMBOL`,
`CAPITAL_NOCIONAL` de `continuidade_daily_rule.py` -- NAO edita nenhum dos
dois arquivos.

So' WIN@: e' o simbolo com liquido POSITIVO no IS inteiro (o "forte
candidato" citado pelo dono). WDO@ reversal ja fecha negativo no IS
inteiro (-R$3.225,37) -- fora do escopo desta rodada de refino.

## Angulos investigados (nesta ordem)

1. Autocorrelacao lag-1 ROLANTE (janelas de 40/60/80 pregoes) ao longo do
   tempo inteiro -- a dependencia bruta e' ESTAVEL ou muda de sinal entre
   a metade 1 e a metade 2? A regra usa `direction="reversal"` FIXO no
   periodo inteiro -- se o regime de autocorrelacao muda, a direcao fixa
   vira o problema, nao o edge em si.
2. P&L diario da regra CUSTADA, acumulado ao longo do periodo INTEIRO (nao
   so' as 2 metades agregadas) -- em blocos de 10 (decis cronologicos) e
   dia-a-dia -- para distinguir degradacao GRADUAL (drift) de um BREAK
   abrupto numa data especifica.
3. Magnitude do retorno do dia anterior (o que decide o sinal, MESMA
   formula de `ContinuidadeDiaria.seed_daily_volatility`: `close[D] -
   close[D-1]`, pontos) -- dias com sinal fraco (retorno minusculo) geram
   trade mais ruidoso? Corta por tercil de |retorno| dentro de cada
   metade.
4. Regime de volatilidade -- range diario mediano TRAILING (mesmo padrao
   anti-look-ahead de `strategy.daytrade.base.JanelaVolatilidadeDiaria`:
   so' dias JA CONCLUIDOS antes do pregao da decisao) -- a regra ganha
   mais/perde mais em regime de vol alta ou baixa? A vol trailing tambem
   MUDOU de patamar entre a metade 1 e a metade 2?
5. Dia da semana / virada de mes.

Todo numero usa o MESMO custo real (`backtest.intraday.profiles.
FUTURES_PROFILES['WIN@']`) da rodada original -- nada aqui e' bruto sem
custo, exceto onde marcado explicitamente "BRUTO" (secao 1, que mede a
dependencia estatistica, nao o P&L)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from continuidade_daily_rule import (  # noqa: E402
    CAPITAL_NOCIONAL,
    DIRECTION_BY_SYMBOL,
    _metade,
    rodar,
)
from continuidade_stats import carregar_is_bars  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402

SYMBOL = "WIN@"
DIRECTION = DIRECTION_BY_SYMBOL[SYMBOL]  # "reversal"


# ---------------------------------------------------------------------------
# dados diarios auxiliares (closes com DATA, nao so' o array bruto de
# `continuidade_stats.daily_returns` -- precisamos alinhar cada retorno a um
# dia de calendario para tudo que segue)
# ---------------------------------------------------------------------------

def daily_closes(bars: pd.DataFrame) -> pd.Series:
    """Fechamento por pregao, indexado por DATA (nao timestamp) -- base de
    tudo que segue neste script."""
    s = bars.groupby(bars.index.date)["close"].last().sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def daily_range_mediano(bars: pd.DataFrame) -> pd.Series:
    """`high - low` por pregao, indexado por DATA -- insumo do regime de
    volatilidade (secao 4)."""
    g = bars.groupby(bars.index.date)
    s = (g["high"].max() - g["low"].min()).sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def signal_previous_return(closes: pd.Series) -> pd.Series:
    """`close[D] - close[D-1]` em PONTOS, indexado pelo dia D (o dia
    CONCLUIDO que gera o sinal) -- EXATA mesma formula de
    `ContinuidadeDiaria.seed_daily_volatility` (`previous_daily_bars[-1].
    close - previous_daily_bars[-2].close`). O TRADE do dia D+1 usa este
    valor; para alinhar com o dia em que o trade ACONTECE, desloque +1
    posicao (`.shift(-1)` neste index ordenado por pregao == "meu proximo
    pregao usa este retorno")."""
    return closes.diff()


# ---------------------------------------------------------------------------
# 1) autocorrelacao lag-1 ROLANTE
# ---------------------------------------------------------------------------

def secao_1_autocorr_rolante(closes: pd.Series) -> None:
    print("\n" + "=" * 100)
    print("1) AUTOCORRELACAO LAG-1 ROLANTE (retorno % fechamento-a-fechamento, BRUTA -- sem custo)")
    print("=" * 100)
    rets = closes.pct_change().dropna()
    n = len(rets)
    datas = rets.index
    meio_idx = n // 2
    print(f"{n} retornos diarios, corte metade1/metade2 no indice {meio_idx} "
          f"({datas[meio_idx-1].date()} | {datas[meio_idx].date()})")

    for janela in (40, 60, 80):
        prev = rets.shift(1)
        roll = rets.rolling(janela).corr(prev)
        roll_valid = roll.dropna()
        print(f"\n--- janela rolante = {janela} pregoes ---")
        if roll_valid.empty:
            print("  (poucos dados para esta janela)")
            continue
        # amostra a cada ~10 pontos para nao poluir, sempre incluindo o
        # primeiro/ultimo ponto de cada metade
        passo = max(1, len(roll_valid) // 20)
        for i in range(0, len(roll_valid), passo):
            data = roll_valid.index[i]
            metade_lbl = "M1" if data < datas[meio_idx] else "M2"
            print(f"    {data.date()}  [{metade_lbl}]  corr_rolante={roll_valid.iloc[i]:+.4f}")
        media_m1 = roll_valid[roll_valid.index < datas[meio_idx]].mean()
        media_m2 = roll_valid[roll_valid.index >= datas[meio_idx]].mean()
        n_sinal_troca = int(np.sum(np.diff(np.sign(roll_valid.to_numpy())) != 0))
        frac_negativa = float((roll_valid < 0).mean())
        print(f"  media corr_rolante metade1={media_m1:+.4f}  metade2={media_m2:+.4f}  "
              f"(direction='reversal' aposta que corr < 0 -- quanto mais negativa, melhor "
              f"para a regra)")
        print(f"  fracao do tempo com corr_rolante < 0: {frac_negativa*100:.1f}%  "
              f"trocas de sinal ao longo da janela: {n_sinal_troca}")

    corr_full = float(rets.corr(rets.shift(1)))
    corr_h1 = float(rets[:meio_idx].corr(rets[:meio_idx].shift(1)))
    corr_h2 = float(rets[meio_idx:].corr(rets[meio_idx:].shift(1)))
    print(f"\ncorrelacao lag-1 do PERIODO INTEIRO (referencia, = medido em "
          f"continuidade_stats.py): {corr_full:+.4f}")
    print(f"correlacao lag-1 SO' metade1: {corr_h1:+.4f}   SO' metade2: {corr_h2:+.4f}")


# ---------------------------------------------------------------------------
# 2) P&L diario acumulado, decis cronologicos + dia a dia
# ---------------------------------------------------------------------------

def _sem_tz(ts: pd.Timestamp) -> pd.Timestamp:
    """Normaliza para meia-noite e derruba timezone -- `closes`/`ranges`
    (indexados por `bars.index.date`, sempre tz-naive) precisam comparar
    com a data do trade sem conflito de tz-aware x tz-naive."""
    ts = pd.Timestamp(ts).normalize()
    return ts.tz_localize(None) if ts.tzinfo is not None else ts


def _trades_diarios(result) -> pd.DataFrame:
    trades = result.trades
    df = pd.DataFrame({
        "data": [_sem_tz(t.exit_ts) for t in trades],
        "pnl": [t.pnl_brl for t in trades],
        "side": [t.side for t in trades],
    }).sort_values("data").reset_index(drop=True)
    return df


def secao_2_pnl_acumulado(df_trades: pd.DataFrame) -> None:
    print("\n" + "=" * 100)
    print("2) P&L DIARIO ACUMULADO (regra custada, IS inteiro) -- decis cronologicos + dia a dia")
    print("=" * 100)
    df = df_trades.copy()
    df["pnl_acum"] = df["pnl"].cumsum()
    n = len(df)

    print(f"\n{n} trades/pregoes com sinal, {df['data'].min().date()} -> {df['data'].max().date()}")
    print("\n--- por DECIL cronologico (10 blocos ~iguais de trades, NAO de dias corridos) ---")
    df["decil"] = pd.qcut(np.arange(n), 10, labels=False, duplicates="drop")
    resumo = df.groupby("decil").agg(
        inicio=("data", "min"), fim=("data", "max"), n_trades=("pnl", "size"),
        liquido=("pnl", "sum"), win_pct=("pnl", lambda s: 100.0 * (s > 0).mean()),
    )
    resumo["liquido_acum"] = resumo["liquido"].cumsum()
    for decil, row in resumo.iterrows():
        print(f"  decil {int(decil)+1:2d}  {row['inicio'].date()} -> {row['fim'].date()}  "
              f"n={int(row['n_trades']):3d}  liquido=R${num_br(row['liquido']):>12}  "
              f"win={num_br(row['win_pct'],1)}%  acumulado=R${num_br(row['liquido_acum']):>12}")

    print("\n--- pico da curva de patrimonio (P&L acumulado) e distancia ate o fim ---")
    pico_idx = int(df["pnl_acum"].idxmax())
    pico_data = df.loc[pico_idx, "data"]
    pico_valor = df.loc[pico_idx, "pnl_acum"]
    valor_final = df["pnl_acum"].iloc[-1]
    print(f"  pico em {pico_data.date()} (trade #{pico_idx+1}/{n}): R${num_br(pico_valor)}")
    print(f"  valor final ({df['data'].iloc[-1].date()}): R${num_br(valor_final)}")
    print(f"  do pico ate o fim: R${num_br(valor_final - pico_valor)} em "
          f"{n - pico_idx - 1} trades ({(n-pico_idx-1)/n*100:.0f}% da amostra restante)")

    print("\n--- maior sequencia de perda consecutiva (dias) ---")
    perde = (df["pnl"] < 0).to_numpy()
    melhor_seq, atual = 0, 0
    melhor_fim_idx = -1
    for i, p in enumerate(perde):
        if p:
            atual += 1
            if atual > melhor_seq:
                melhor_seq = atual
                melhor_fim_idx = i
        else:
            atual = 0
    if melhor_seq > 0:
        ini_idx = melhor_fim_idx - melhor_seq + 1
        print(f"  {melhor_seq} trades perdedores seguidos: "
              f"{df.loc[ini_idx,'data'].date()} -> {df.loc[melhor_fim_idx,'data'].date()}")


# ---------------------------------------------------------------------------
# 3) magnitude do retorno do dia anterior
# ---------------------------------------------------------------------------

def secao_3_magnitude(df_trades: pd.DataFrame, closes: pd.Series, meio_data: pd.Timestamp) -> None:
    print("\n" + "=" * 100)
    print("3) MAGNITUDE do retorno do dia anterior (o que decide o sinal, custo aplicado)")
    print("=" * 100)
    prev_ret = signal_previous_return(closes)  # indexado pelo dia D (concluido)
    df = df_trades.copy()
    # o trade do dia `data` foi decidido pelo retorno do PENULTIMO pregao
    # concluido antes dele -- o mesmo valor que `seed_daily_volatility`
    # calculou usando os DOIS ultimos `previous_daily_bars`. Como `prev_ret`
    # ja esta' indexado pelo dia que GERA o sinal (D), e o trade ACONTECE no
    # proximo pregao com dado, basta olhar o valor de `prev_ret` na ultima
    # data < data do trade.
    idx_ordenado = closes.index
    sinais = []
    for d in df["data"]:
        pos = idx_ordenado.searchsorted(d)
        # pos = posicao de `d` em `closes.index`; o retorno que decidiu o
        # trade de `d` e' `prev_ret` na posicao pos-1 (o pregao concluido
        # imediatamente anterior a `d`)
        sinais.append(prev_ret.iloc[pos - 1] if pos >= 1 else np.nan)
    df["retorno_sinal_pts"] = sinais
    df["retorno_sinal_abs"] = df["retorno_sinal_pts"].abs()
    df["metade"] = np.where(df["data"] < meio_data, "M1", "M2")

    print("\n--- tercis de |retorno do dia anterior| (pontos), full IS ---")
    df["tercil"] = pd.qcut(df["retorno_sinal_abs"], 3, labels=["fraco", "medio", "forte"])
    resumo = df.groupby("tercil", observed=True).agg(
        n=("pnl", "size"), liquido=("pnl", "sum"),
        win_pct=("pnl", lambda s: 100.0 * (s > 0).mean()),
        media_abs_pts=("retorno_sinal_abs", "mean"),
    )
    for tercil, row in resumo.iterrows():
        print(f"  {tercil:<6}  n={int(row['n']):3d}  |ret|medio={num_br(row['media_abs_pts'],0)}pts  "
              f"liquido=R${num_br(row['liquido']):>12}  win={num_br(row['win_pct'],1)}%  "
              f"R$/trade={num_br(row['liquido']/row['n'],2)}")

    print("\n--- MESMOS tercis, separado por metade (tercil calculado dentro de CADA metade) ---")
    for m in ("M1", "M2"):
        sub = df[df["metade"] == m].copy()
        sub["tercil_m"] = pd.qcut(sub["retorno_sinal_abs"], 3, labels=["fraco", "medio", "forte"],
                                   duplicates="drop")
        resumo_m = sub.groupby("tercil_m", observed=True).agg(
            n=("pnl", "size"), liquido=("pnl", "sum"),
            win_pct=("pnl", lambda s: 100.0 * (s > 0).mean()),
        )
        print(f"  [{m}]")
        for tercil, row in resumo_m.iterrows():
            print(f"    {tercil:<6}  n={int(row['n']):3d}  liquido=R${num_br(row['liquido']):>12}  "
                  f"win={num_br(row['win_pct'],1)}%  R$/trade={num_br(row['liquido']/row['n'],2)}")


# ---------------------------------------------------------------------------
# 4) regime de volatilidade TRAILING (mesmo padrao anti-look-ahead de
#    `JanelaVolatilidadeDiaria`: so' dias ja concluidos antes do pregao)
# ---------------------------------------------------------------------------

def secao_4_regime_vol(df_trades: pd.DataFrame, ranges: pd.Series, meio_data: pd.Timestamp,
                        janela_dias: int = 20) -> None:
    print("\n" + "=" * 100)
    print(f"4) REGIME DE VOLATILIDADE -- range diario mediano TRAILING ({janela_dias} pregoes, "
          f"so' dias ja concluidos)")
    print("=" * 100)
    trailing_mediano = ranges.rolling(janela_dias, min_periods=5).median().shift(1)
    # .shift(1): a mediana do dia `d` so' pode usar dias ATE d-1 (o pregao
    # `d` ainda nao aconteceu quando a decisao de `d` e' tomada)

    idx_ordenado = ranges.index
    df = df_trades.copy()
    vals = []
    for d in df["data"]:
        pos = idx_ordenado.searchsorted(d)
        vals.append(trailing_mediano.iloc[pos] if pos < len(trailing_mediano) else np.nan)
    df["vol_trailing"] = vals
    df["metade"] = np.where(df["data"] < meio_data, "M1", "M2")
    df = df.dropna(subset=["vol_trailing"])

    print(f"\nvol trailing mediana, full IS: {num_br(float(df['vol_trailing'].median()),0)}pts  "
          f"metade1: {num_br(float(df.loc[df['metade']=='M1','vol_trailing'].median()),0)}pts  "
          f"metade2: {num_br(float(df.loc[df['metade']=='M2','vol_trailing'].median()),0)}pts")

    print("\n--- tercis de vol trailing (calculado no FULL IS), liquido/win por tercil ---")
    df["tercil"] = pd.qcut(df["vol_trailing"], 3, labels=["baixa", "media", "alta"])
    resumo = df.groupby("tercil", observed=True).agg(
        n=("pnl", "size"), liquido=("pnl", "sum"),
        win_pct=("pnl", lambda s: 100.0 * (s > 0).mean()),
    )
    for tercil, row in resumo.iterrows():
        print(f"  {tercil:<6}  n={int(row['n']):3d}  liquido=R${num_br(row['liquido']):>12}  "
              f"win={num_br(row['win_pct'],1)}%  R$/trade={num_br(row['liquido']/row['n'],2)}")

    print("\n--- MESMO tercil (full IS), quebrado por metade (quantos trades de cada regime "
          "caem em cada metade, e o liquido) ---")
    for tercil in ("baixa", "media", "alta"):
        sub = df[df["tercil"] == tercil]
        for m in ("M1", "M2"):
            s2 = sub[sub["metade"] == m]
            if len(s2) == 0:
                continue
            print(f"    vol={tercil:<6} [{m}]  n={len(s2):3d}  liquido=R${num_br(float(s2['pnl'].sum())):>12}  "
                  f"win={num_br(100.0*(s2['pnl']>0).mean(),1)}%")


# ---------------------------------------------------------------------------
# 5) dia da semana / virada de mes
# ---------------------------------------------------------------------------

def secao_5_calendario(df_trades: pd.DataFrame, meio_data: pd.Timestamp) -> None:
    print("\n" + "=" * 100)
    print("5) DIA DA SEMANA e VIRADA DE MES")
    print("=" * 100)
    df = df_trades.copy()
    df["metade"] = np.where(df["data"] < meio_data, "M1", "M2")
    dias_semana = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
    df["dow"] = df["data"].dt.dayofweek.map(lambda i: dias_semana[i])

    print("\n--- por dia da semana, full IS ---")
    resumo = df.groupby("dow").agg(n=("pnl", "size"), liquido=("pnl", "sum"),
                                    win_pct=("pnl", lambda s: 100.0 * (s > 0).mean()))
    resumo = resumo.reindex([d for d in dias_semana if d in resumo.index])
    for dow, row in resumo.iterrows():
        print(f"  {dow}  n={int(row['n']):3d}  liquido=R${num_br(row['liquido']):>12}  "
              f"win={num_br(row['win_pct'],1)}%  R$/trade={num_br(row['liquido']/row['n'],2)}")

    print("\n--- por dia da semana, separado por metade ---")
    for m in ("M1", "M2"):
        sub = df[df["metade"] == m]
        resumo_m = sub.groupby("dow").agg(n=("pnl", "size"), liquido=("pnl", "sum"))
        resumo_m = resumo_m.reindex([d for d in dias_semana if d in resumo_m.index])
        linha_txt = "  ".join(f"{dow}:R${num_br(row['liquido'],0)}({int(row['n'])})"
                               for dow, row in resumo_m.iterrows())
        print(f"  [{m}] {linha_txt}")

    print("\n--- virada de mes (3 primeiros / 3 ultimos pregoes com dado de cada mes) vs resto ---")
    df["ano_mes"] = df["data"].dt.to_period("M")
    # posicao do trade dentro do seu mes de calendario (por ORDEM de pregao
    # com trade, aproximacao razoavel -- pregoes sem sinal sao raros aqui)
    df["pos_no_mes"] = df.groupby("ano_mes").cumcount()
    df["tam_mes"] = df.groupby("ano_mes")["pnl"].transform("size")
    df["virada"] = (df["pos_no_mes"] < 3) | (df["pos_no_mes"] >= df["tam_mes"] - 3)
    resumo_v = df.groupby("virada").agg(n=("pnl", "size"), liquido=("pnl", "sum"),
                                         win_pct=("pnl", lambda s: 100.0 * (s > 0).mean()))
    for virada, row in resumo_v.iterrows():
        rotulo = "virada de mes" if virada else "meio do mes"
        print(f"  {rotulo:<15} n={int(row['n']):3d}  liquido=R${num_br(row['liquido']):>12}  "
              f"win={num_br(row['win_pct'],1)}%  R$/trade={num_br(row['liquido']/row['n'],2)}")


def main() -> None:
    print(f"[win_daily_continuidade_refino_diagnostico] {SYMBOL} direction={DIRECTION}")
    bars = carregar_is_bars(SYMBOL)
    closes = daily_closes(bars)
    ranges = daily_range_mediano(bars)
    meio_idx = len(closes) // 2
    meio_data = closes.index[meio_idx]
    print(f"IS: {len(closes)} pregoes ({closes.index.min().date()} -> {closes.index.max().date()}); "
          f"corte metade1/metade2 em {meio_data.date()} (MESMO corte de `_metade` -- por CONTAGEM de "
          f"pregoes, nao de dias corridos)")

    resultado_full = rodar(SYMBOL, bars, DIRECTION)
    linha_full = linha_de_resultado(f"continuidade_diaria_{DIRECTION}", resultado_full,
                                     CAPITAL_NOCIONAL, capital_nocional=True)
    print("\n=== baseline (reproduzido, deve bater com `continuidade_daily_rule.py`) ===")
    print(tabela([linha_full]))

    df_trades = _trades_diarios(resultado_full)

    secao_1_autocorr_rolante(closes)
    secao_2_pnl_acumulado(df_trades)
    secao_3_magnitude(df_trades, closes, meio_data)
    secao_4_regime_vol(df_trades, ranges, meio_data)
    secao_5_calendario(df_trades, meio_data)


if __name__ == "__main__":
    main()
