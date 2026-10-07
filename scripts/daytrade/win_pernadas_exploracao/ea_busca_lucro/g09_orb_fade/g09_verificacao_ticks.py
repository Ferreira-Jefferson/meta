# -*- coding: utf-8 -*-
"""Verificacao com TICKS REAIS do vencedor composto da Geracao 9 no IS
(`AB M=10 stop_max=50`, stop mediano REALIZADO=55pts -- inclui 1 tick de
deslize do stop a mercado sobre o nominal de 50 -- abaixo do piso de 100pts
do item 6.47 de `LICOES_DE_PRODUCAO.md`: "stop curto simulado com caminho de
2 pontos por vela M1 e' OTIMISTA").

Mesmo metodo de `g03_verificacao_ticks.py`: nao re-deriva o SINAL (deteccao
de falha do rompimento) a partir de ticks -- isso exigiria reimplementar a
deteccao inteira em resolucao de tick, fora do orcamento desta geracao. Em
vez disso, verifica o que e' diretamente checavel: para cada trade REAL do
IS que tem cobertura de tick, reconstroi stop/alvo a partir do preco de
ENTRADA (anchor_exits_at_fill=True preserva a distancia declarada) e confere,
na sequencia REAL de negocios (`data/cache_win_ticks/WIN@D`), se o nivel que
o motor M1 registrou como "tocado primeiro" (stop ou alvo) e' de fato o que
toca primeiro na resolucao de tick.

Conveniencia desta geracao especificamente: no vencedor composto,
`stop_min_pontos == stop_max_pontos == 50`, entao o stop sai SEMPRE fixo em
50 pontos (o clip faz o "tamanho do extremo do rompimento" nunca importar --
ver a ressalva no relatorio) -- RISCO_PTS e' uma constante, como em
`g03_verificacao_ticks.py`, nao precisa reconstruir por trade.

LIMITACAO DECLARADA: o cache de ticks (`data/cache_win_ticks/WIN@D`) cobre
mar/2026 em diante -- NAO cobre jan-fev/2026, parte do IS. Trades de jan-fev
ficam "sem_tick" nesta verificacao (contados a parte, nao escondidos).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g09_orb_fade/g09_verificacao_ticks.py`
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g09_base as b  # noqa: E402

TICK_DIR = b.ROOT / "data" / "cache_win_ticks" / "WIN@D"
TICK_SIZE = 5.0
RISCO_PTS = 50.0       # stop_min_pontos == stop_max_pontos == 50 no vencedor
ALVO_MULTIPLO = 3.0

KWARGS_VENCEDOR = dict(
    range_minutos=5.0,
    falha_n_barras=10,
    stop_min_pontos=50.0,
    stop_max_pontos=50.0,
    stop_buffer_pontos=20.0,
    alvo_multiplo=3.0,
    buffer_entrada_pontos=20.0,
)


def _carrega_ticks(dia) -> pd.DataFrame | None:
    f = TICK_DIR / f"{dia}.pkl"
    if not f.exists():
        return None
    with open(f, "rb") as fh:
        df = pickle.load(fh)
    df["ts_brt"] = pd.to_datetime(df["time_msc"], unit="ms")
    return df[["ts_brt", "last"]].sort_values("ts_brt")


def main() -> None:
    win = b.carrega_win()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    res, strat = b.roda(dias_is, **KWARGS_VENCEDOR)
    trades = list(res.trades)
    print(f"IS: {len(trades)} trades fechados. Verificando com ticks reais "
          f"(risco declarado = {RISCO_PTS:.0f} pts fixo; "
          f"alvo = {ALVO_MULTIPLO:.0f}x = {ALVO_MULTIPLO*RISCO_PTS:.0f} pts).\n")

    sem_tick = 0
    concordam = 0
    discordam = 0
    nenhum_tocado = 0
    for t in trades:
        dia = t.entry_ts.date()
        ticks = _carrega_ticks(dia)
        if ticks is None:
            sem_tick += 1
            continue
        janela = ticks[(ticks["ts_brt"] >= t.entry_ts) & (ticks["ts_brt"] <= t.exit_ts)]
        if janela.empty:
            sem_tick += 1
            continue
        if t.side == "long":
            stop_px = t.entry_price - RISCO_PTS
            alvo_px = t.entry_price + ALVO_MULTIPLO * RISCO_PTS
            toca_stop = janela[janela["last"] <= stop_px]
            toca_alvo = janela[janela["last"] >= alvo_px]
        else:
            stop_px = t.entry_price + RISCO_PTS
            alvo_px = t.entry_price - ALVO_MULTIPLO * RISCO_PTS
            toca_stop = janela[janela["last"] >= stop_px]
            toca_alvo = janela[janela["last"] <= alvo_px]
        ts_stop = toca_stop["ts_brt"].min() if not toca_stop.empty else pd.NaT
        ts_alvo = toca_alvo["ts_brt"].min() if not toca_alvo.empty else pd.NaT
        reason = str(t.exit_reason.value).lower()
        if pd.isna(ts_stop) and pd.isna(ts_alvo):
            veredito = "nenhum nivel tocado nos ticks da janela"
            nenhum_tocado += 1
        elif pd.isna(ts_alvo) or (not pd.isna(ts_stop) and ts_stop <= ts_alvo):
            veredito = "CONCORDA" if "stop" in reason else "DISCORDA"
        else:
            veredito = "CONCORDA" if "target" in reason else "DISCORDA"
        if veredito == "CONCORDA":
            concordam += 1
        elif veredito == "DISCORDA":
            discordam += 1
        print(f"  {t.entry_ts}  {t.side:<5}  entry={t.entry_price:>9.1f}  "
              f"exit={t.exit_price:>9.1f}  motor={reason:<12}  tick={veredito}")

    checaveis = concordam + discordam
    print(f"\nResumo: concordam={concordam}  discordam={discordam}  "
          f"nenhum_nivel_tocado={nenhum_tocado}  sem_tick/sem_janela={sem_tick}  "
          f"total={len(trades)}")
    if checaveis:
        print(f"Taxa de discordancia entre os CHECAVEIS: {100*discordam/checaveis:.1f}% "
              f"({discordam}/{checaveis})")
    print("\nLIMITACAO: cache de ticks cobre mar/2026 em diante -- jan-fev/2026 "
          "(parte do IS) nao tem cobertura e cai em sem_tick.")


if __name__ == "__main__":
    main()
