"""Tempo em fila (quanto tempo a ordem-limite do `WdoGridReloadMaker` F1
fica PARADA ate ser tocada) correlaciona com o RESULTADO do trade que ela
abre? Pergunta do dono, 2026-09-04, olhando ao vivo uma ordem sell limit do
WDO (PMAM3/WDOV26) parada ha' um tempo abaixo do gatilho: "se ela ficar
muito tempo abaixo e so' entao for pega, a chance de fechar em ganho e'
maior?" -- generalizada para os dois lados (compra e venda, nao so' o lado
que a pergunta original citou) e testada com o MESMO metodo ja usado por
`signal_quality_wdof1_2026_08_27.py` para as outras features de entrada.

## Por que da' pra medir isto SEM rodar o motor de novo

O robo REARMA no MESMO nivel IMEDIATAMENTE apos cada fechamento -- mesma
chamada de `on_bar` (`backtest.intraday.machine._on_closed_bar_core`, passo
"(5) decisao do robo para a PROXIMA barra", que roda DEPOIS do passo "(1)
stop/target automatico" na MESMA barra): a `EnterLimit` que rearma e'
emitida na MESMA barra em que a posicao anterior fechou. Logo, para o trade
i que nao seja o 1o do pregao:

    tempo_fila_i = entry_ts_i - exit_ts_(i-1)

Confirmado EMPIRICAMENTE no trade log ja existente (2.701 pares dentro do
mesmo pregao, ver `capital_ladder_wdof1_n1_trades_2026_08_27.csv`): o gap
e' SEMPRE >= 0 (nunca negativo, o que seria impossivel de qualquer forma
dado que os trades ja saem ordenados por `entry_ts` -- a checagem serve so'
para confirmar que a hipotese de rearme-na-mesma-barra bate com o dado
real), mediana 7s, p75 35s, maximo 11.893s (~3h18min). Para o 1o trade de
cada pregao, `tempo_fila_1 = entry_ts_1 - primeiro_tick_do_pregao` (a
ancora tambem e' o fechamento da 1a barra sob
`reanchor_mode="rolling_last_price"`, o default de producao -- ver
`WdoGridReloadMaker.on_bar`, bloco `if state.open_price is None`).

Reusa 100% de dado ja computado (trade log CSV + tick bars do subconjunto
IS com tick disponivel no terminal MT5, MESMA janela de
`signal_quality_wdof1_2026_08_27.py`, 72/123 pregoes IS) -- nenhum rerun do
motor, e ZERO mudanca em `backtest/`/`strategy/`. Deliberado: outra sessao
esta editando `live/` em paralelo agora (ver `db/live_process.json`), e a
regra ja registrada nesta frente e' nenhuma rodada editar arquivo
compartilhado enquanto outra roda ao mesmo tempo.

## Metodo -- identico a `signal_quality_wdof1_2026_08_27.py` (nada novo)

`testa_proxy`/`imprime_correlacao`/`proxies_reproduziveis` de
`copa_rejection_lab.py`: correlacao de Pearson (proxy, pnl_brl do trade) +
teste de permutacao (n_perm=5000) + diferenca por tercil + gate de
reproducao split-half (MESMO sinal E p<0,05 no pool E p<0,10 em CADA metade
cronologica). Testado SEPARADO por LADO (long/short) -- a pergunta original
era especifica de venda (short: ordem parada ACIMA do preco, tocada quando
o preco SOBE ate ela -- exatamente o caso do ticket mostrado ao dono),
long entra por simetria/honestidade (nao testar so' o lado que "parece"
confirmar a hipotese). Tambem testado em log1p(tempo_fila_s) alem do valor
cru -- a distribuicao de tempo em fila e' fortemente assimetrica (cauda
longa ate 3h+), e Pearson sobre a variavel crua pode ser dominado por
poucos pontos extremos.

## Ressalva de poder estatistico (MESMA do signal_quality_wdof1)

O candidato (T1 S16 x1) acerta ~99% dos trades -- qualquer correlacao com
`pnl_brl` bruto e' mecanicamente dominada por poucos perdedores de alta
alavancagem estatistica. A tabela de WIN RATE por quartil de tempo_fila_s
(CRUA, sem veredito imposto -- o numero fala, a leitura fica pro dono)
complementa a correlacao de Pearson porque e' mais direta de ler sobre um
alvo quase binario (bateu alvo de 1 tick ou bateu stop de 16).

Uso: `python -u scripts/daytrade/wdof1_tempo_fila_resultado_2026_09_04.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br  # noqa: E402

from copa_rejection_lab import (  # noqa: E402
    ResultadoCorrelacao,
    imprime_correlacao,
    proxies_reproduziveis,
    testa_proxy,
)
from signal_quality_wdof1_2026_08_27 import _aberturas_por_dia  # noqa: E402
from wdo_grid_reload_f1_tick_lab import carregar_tick_bars  # noqa: E402

OUT_DIR = ROOT / "scripts" / "daytrade"
TRADE_LOG_CSV = OUT_DIR / "capital_ladder_wdof1_n1_trades_2026_08_27.csv"
FEATURES_CSV = OUT_DIR / "wdof1_tempo_fila_features_2026_09_04.csv"


# ---------------------------------------------------------------------------
# 0. trade log + tempo em fila (por trade)
# ---------------------------------------------------------------------------

def carregar_trade_log(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True, format="ISO8601")
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True, format="ISO8601")
    df = df.sort_values("entry_ts").reset_index(drop=True)
    if not df["quantity"].eq(1).all():
        raise SystemExit(f"[tempo_fila] esperava quantity==1 em TODA linha de {path} (N=1) -- "
                          f"valores encontrados: {sorted(df['quantity'].unique())}")
    return df


def computa_tempo_fila(df: pd.DataFrame, aberturas: dict) -> pd.DataFrame:
    """`tempo_fila_s` (segundos) por trade -- ver a docstring do modulo para
    a formula e a validacao empirica (gap sempre >= 0)."""
    df = df.copy()
    dias = df["entry_ts"].dt.date
    prev_exit = df["exit_ts"].shift(1)
    prev_dia = dias.shift(1)
    mesmo_pregao = dias == prev_dia

    placed_ts = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    placed_ts[mesmo_pregao] = prev_exit[mesmo_pregao]
    for idx in df.index[~mesmo_pregao.fillna(False)]:
        dia = dias.loc[idx]
        if dia not in aberturas:
            continue  # sem tick de abertura para este dia -- fica NaT, descartado abaixo
        abertura_ts_ns, _ = aberturas[dia]
        placed_ts.loc[idx] = pd.Timestamp(abertura_ts_ns, tz="UTC")

    df["placed_ts"] = placed_ts
    df["tempo_fila_s"] = (df["entry_ts"] - df["placed_ts"]).dt.total_seconds()
    return df


# ---------------------------------------------------------------------------
# 1. correlacao (Pearson + permutacao + tercil + split-half), por lado
# ---------------------------------------------------------------------------

def _resultados_por_lado(sub: pd.DataFrame, rotulo_lado: str) -> None:
    print(f"\n=== correlacao tempo_fila_s <-> pnl_brl -- lado {rotulo_lado} (n={len(sub)}) ===")
    x_bruto = sub["tempo_fila_s"].to_numpy(dtype=float)
    x_log = np.log1p(x_bruto)
    y = sub["pnl_brl"].to_numpy(dtype=float)

    r_bruto = testa_proxy(f"tempo_fila_s ({rotulo_lado})", x_bruto, y, seed=1)
    imprime_correlacao(r_bruto)
    r_log = testa_proxy(f"tempo_fila_log1p_s ({rotulo_lado})", x_log, y, seed=2)
    imprime_correlacao(r_log)

    proxies_reproduziveis({
        f"tempo_fila_s ({rotulo_lado})": (x_bruto, y, r_bruto),
        f"tempo_fila_log1p_s ({rotulo_lado})": (x_log, y, r_log),
    })


# ---------------------------------------------------------------------------
# 2. tabela crua: win rate / pnl medio por quartil de tempo_fila_s
# ---------------------------------------------------------------------------

def _tabela_por_quartil(sub: pd.DataFrame, rotulo_lado: str) -> None:
    print(f"\n--- TABELA CRUA -- win rate / pnl por quartil de tempo_fila_s, lado {rotulo_lado} (n={len(sub)}) ---")
    quartis = pd.qcut(sub["tempo_fila_s"], 4, duplicates="drop")
    g = sub.groupby(quartis, observed=True).agg(
        n=("pnl_brl", "size"),
        tempo_fila_s_min=("tempo_fila_s", "min"),
        tempo_fila_s_max=("tempo_fila_s", "max"),
        win_rate_pct=("pnl_brl", lambda s: 100.0 * float((s > 0).mean())),
        pnl_medio_brl=("pnl_brl", "mean"),
        pnl_total_brl=("pnl_brl", "sum"),
    )
    with pd.option_context("display.width", 160, "display.float_format", "{:,.2f}".format):
        print(g.to_string())


def _decis_extremos(sub: pd.DataFrame, rotulo_lado: str) -> None:
    """Resposta direta a pergunta literal: comparando o decil de MAIOR
    tempo_fila_s (ordem ficou parada muito tempo antes de ser tocada) contra
    o decil de MENOR (tocada quase na hora), o win rate muda?"""
    n = len(sub)
    corte = max(1, n // 10)
    ordenado = sub.sort_values("tempo_fila_s")
    baixo = ordenado.iloc[:corte]
    alto = ordenado.iloc[-corte:]
    print(f"\n--- decil de tempo_fila_s MENOR vs MAIOR, lado {rotulo_lado} (n={corte} cada ponta) ---")
    print(f"  MENOR tempo em fila (<= {num_br(float(baixo['tempo_fila_s'].max()), 1)}s): "
          f"win rate {num_br(100.0 * float((baixo['pnl_brl'] > 0).mean()), 2)}% | "
          f"pnl medio R${num_br(float(baixo['pnl_brl'].mean()))}")
    print(f"  MAIOR tempo em fila (>= {num_br(float(alto['tempo_fila_s'].min()), 1)}s): "
          f"win rate {num_br(100.0 * float((alto['pnl_brl'] > 0).mean()), 2)}% | "
          f"pnl medio R${num_br(float(alto['pnl_brl'].mean()))}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    trades = carregar_trade_log(TRADE_LOG_CSV)
    print(f"[tempo_fila] {len(trades)} trades carregados de {TRADE_LOG_CSV}")

    dias, tick_bars = carregar_tick_bars()
    aberturas = _aberturas_por_dia(tick_bars)
    print(f"[tempo_fila] tick bars: {len(tick_bars)} ticks, {len(dias)} pregoes IS "
          f"({dias[0]} -> {dias[-1]})")

    trades = computa_tempo_fila(trades, aberturas)
    sem_placed = trades["placed_ts"].isna().sum()
    if sem_placed:
        print(f"[aviso] {sem_placed}/{len(trades)} trades sem placed_ts resolvido (1o trade de um "
              f"pregao sem abertura tick correspondente) -- excluidos do resto da analise.")
    trades = trades.dropna(subset=["placed_ts"]).reset_index(drop=True)

    negativos = int((trades["tempo_fila_s"] < 0).sum())
    print(f"[tempo_fila] validacao: {negativos} trade(s) com tempo_fila_s NEGATIVO "
          f"(esperado 0 -- rearme e' sempre na mesma barra ou depois do fechamento anterior)")

    print("\n=== descritivo de tempo_fila_s (segundos), por lado ===")
    with pd.option_context("display.float_format", "{:,.2f}".format):
        print(trades.groupby("side")["tempo_fila_s"].describe().to_string())

    trades.to_csv(FEATURES_CSV, index=False)
    print(f"\n[tempo_fila] tabela por-trade (com tempo_fila_s) salva em {FEATURES_CSV}")

    for lado in ("short", "long"):
        sub = trades[trades["side"] == lado]
        if sub.empty:
            print(f"\n[aviso] nenhum trade do lado {lado} -- pulando.")
            continue
        _resultados_por_lado(sub, lado)
        _tabela_por_quartil(sub, lado)
        _decis_extremos(sub, lado)

    print("\n=== TODOS os lados juntos (referencia) ===")
    _resultados_por_lado(trades, "long+short")
    _tabela_por_quartil(trades, "long+short")


if __name__ == "__main__":
    main()
