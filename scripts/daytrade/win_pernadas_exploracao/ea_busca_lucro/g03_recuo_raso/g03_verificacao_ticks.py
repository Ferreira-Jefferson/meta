# -*- coding: utf-8 -*-
"""Verificacao com TICKS REAIS do vencedor da Geracao 3 (stop mediano IS=35pts,
OOS-1=30pts -- abaixo do piso de 100pts do item 6.47 de `LICOES_DE_PRODUCAO.md`:
"stop curto simulado com caminho de 2 pontos por vela M1 e' OTIMISTA").

Nao re-deriva o SINAL (fundo/fracao do recuo) a partir de ticks -- isso exigiria
reimplementar o zigzag inteiro em resolucao de tick, fora do orcamento desta
rodada. Em vez disso, verifica o que e' diretamente checavel: para cada trade
REAL da janela OOS-1 (congelada), reconstroi stop/alvo a partir do preco de
ENTRADA (anchor_exits_at_fill=True preserva a distancia declarada) e confere,
na sequencia REAL de negocios (tick cache `data/cache_win_ticks/WIN@D`), se o
nivel que o motor M1 registrou como "tocado primeiro" (stop ou alvo) e' de
fato o que toca primeiro na resolucao de tick -- a ambiguidade classica de
barra M1 em que stop E alvo estao dentro do range high-low da MESMA barra.

Cita tambem o achado PRONTO de `REGRAS.md` ("Nota de metodo", rodada 6): a
MESMA familia de regras (R51-R60, que inclui R57) ja foi re-medida com ticks
(mar-jun, n=763) e "o acerto fica igual a` ruina do jogador e a esperanca em
~0 pts/op (IC -11 a +11), sem vantagem" -- evidencia direta e anterior de que
o caminho de 2 pontos por vela infla o sinal desta familia especifica.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g03_recuo_raso/g03_verificacao_ticks.py`
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "src"))

import g03_base as b  # noqa: E402
from g03_oos1 import KWARGS_CONGELADOS  # noqa: E402

TICK_DIR = b.ROOT / "data" / "cache_win_ticks" / "WIN@D"
TICK_SIZE = 5.0
M_PONTOS = KWARGS_CONGELADOS["m_pontos"]
ALVO_MULTIPLO = KWARGS_CONGELADOS["alvo_multiplo"]
RISCO_PTS = M_PONTOS + TICK_SIZE  # ver WinBuscaLucroG03RecuoRaso._monta_entrada


def _carrega_ticks(dia) -> pd.DataFrame | None:
    f = TICK_DIR / f"{dia}.pkl"
    if not f.exists():
        return None
    with open(f, "rb") as fh:
        df = pickle.load(fh)
    # Conferido diretamente (2026-10-05): `time_msc` decodifica para
    # `09:00:47` no primeiro negocio do pregao -- ja' esta' em horario local
    # B3, igual a` base M1 (`WIN@D_M1_...csv`). SEM ajuste de fuso.
    df["ts_brt"] = pd.to_datetime(df["time_msc"], unit="ms")
    return df[["ts_brt", "last"]].sort_values("ts_brt")


def main() -> None:
    dias_oos1 = b.dias_da_janela(b.carrega_df(), b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    res, strat = b.roda_congelado(dias_oos1, **KWARGS_CONGELADOS)
    trades = list(res.trades)
    print(f"OOS-1: {len(trades)} trades fechados. Verificando com ticks reais "
          f"(risco declarado = m({M_PONTOS:.0f}) + 1 tick({TICK_SIZE:.0f}) = {RISCO_PTS:.0f} pts; "
          f"alvo = {ALVO_MULTIPLO:.0f}x = {ALVO_MULTIPLO*RISCO_PTS:.0f} pts).\n")

    sem_tick = 0
    concordam = 0
    discordam = 0
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
            veredito = "nenhum nivel tocado nos ticks da janela (saida por TTL/flatten?)"
        elif pd.isna(ts_alvo) or (not pd.isna(ts_stop) and ts_stop <= ts_alvo):
            primeiro_tick = "stop"
            veredito = "CONCORDA" if "stop" in reason else "DISCORDA"
        else:
            primeiro_tick = "target"
            veredito = "CONCORDA" if "target" in reason else "DISCORDA"
        if veredito == "CONCORDA":
            concordam += 1
        elif veredito == "DISCORDA":
            discordam += 1
        print(f"  {t.entry_ts}  {t.side:<5}  entry={t.entry_price:>9.1f}  "
              f"exit={t.exit_price:>9.1f}  motor={reason:<12}  tick={veredito}")

    print(f"\nResumo: concordam={concordam}  discordam={discordam}  sem_tick/sem_janela={sem_tick}  "
          f"total={len(trades)}")
    print("\nAchado ja' existente em REGRAS.md (rodada 6, 'Nota de metodo') sobre a MESMA familia "
          "de regras (R51-R60, que inclui R57): com ticks (mar-jun, n=763) 'o acerto fica igual a` "
          "ruina do jogador e a esperanca em ~0 pts/op (IC -11 a +11), sem vantagem' -- o caminho de "
          "2 pontos por vela M1 gera ~5x mais eventos de recuo em escala pequena e INFLA o resultado "
          "desta familia especifica.")


if __name__ == "__main__":
    main()
