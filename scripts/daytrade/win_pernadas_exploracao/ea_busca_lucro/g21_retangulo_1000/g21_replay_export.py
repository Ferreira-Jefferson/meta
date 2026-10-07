# -*- coding: utf-8 -*-
"""Exporta o JSON de replay (candles M5 + operações + retângulo detectado)
da Geração 21 (`WinBuscaLucroG21Retangulo1000`), vencedor do IS (stop=0,45x
largura, alvo=2,0x) e seu OOS-1 congelado, para a página HTML de replay.

Só visualização -- não re-valida nada, não muda nenhum número já reportado
em ORQUESTRACAO.md. Os líquidos/win%/etc. recalculados aqui são os MESMOS da
G21 (bit a bit, mesmo código, mesmas janelas); o que este script acrescenta
é granularidade de operação (timestamps, preços) e candles M5 para plotar.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g21_retangulo_1000/g21_replay_export.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import g21_base as b  # noqa: E402

sys.path.insert(0, str(b.ROOT / "src"))
from strategy.daytrade.lab.win_retangulo import detecta_retangulo  # noqa: E402

STOP_FRACAO = 0.45
ALVO_MULTIPLO = 2.0
ALVO_FRACAO = STOP_FRACAO * ALVO_MULTIPLO
JANELA_BARRAS = 20  # default da classe, usado sem retune nas duas janelas
TOLERANCIA_BORDA = 0.20

OUT = Path(__file__).parent / "replay_g21.json"


def box_antes_da_entrada(win_m1: pd.DataFrame, entry_ts: pd.Timestamp) -> dict | None:
    """Reconstrói o retângulo (topo/piso) a partir das `JANELA_BARRAS` M1
    ANTERIORES à entrada -- mesma janela que `detecta_retangulo` usa dentro
    da estratégia. É uma reconstrução por fora (função pura, mesmos dados),
    não uma leitura do estado interno da classe -- por isso é rotulada como
    "aproximada" na página: pode divergir em até 1 barra do que a estratégia
    viu, dependendo do instante exato em que a decisão foi tomada dentro do
    `on_bar`."""
    janela = win_m1[win_m1.index < entry_ts].tail(JANELA_BARRAS)
    if len(janela) < JANELA_BARRAS:
        return None
    r = detecta_retangulo(
        janela["high"].to_numpy(), janela["low"].to_numpy(), janela["close"].to_numpy(),
        amplitude_anterior=None, tolerancia=TOLERANCIA_BORDA,
    )
    if r is None:
        return None
    return {"topo": r["topo"], "piso": r["piso"],
            "ini": janela.index[0].strftime("%Y-%m-%d %H:%M:%S"),
            "fim": janela.index[-1].strftime("%Y-%m-%d %H:%M:%S")}


def m5_do_dia(win_m1: pd.DataFrame, dia) -> dict:
    dia_df = win_m1[win_m1.index.date == dia]
    m5 = dia_df.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    return {
        "t": [ts.strftime("%Y-%m-%d %H:%M:%S") for ts in m5.index],
        "o": [round(float(v), 1) for v in m5["open"]],
        "h": [round(float(v), 1) for v in m5["high"]],
        "l": [round(float(v), 1) for v in m5["low"]],
        "c": [round(float(v), 1) for v in m5["close"]],
    }


def exporta_janela(nome: str, dias: list, congelado: bool, win_m1: pd.DataFrame) -> dict:
    res, _ = b.roda(dias, congelado=congelado,
                     stop_fracao_largura=STOP_FRACAO, alvo_fracao_largura=ALVO_FRACAO)
    trades = list(res.trades)
    print(f"{nome}: {len(trades)} trades em {len(dias)} pregões", flush=True)

    por_dia: dict = {}
    for tr in trades:
        dia = tr.entry_ts.date()
        por_dia.setdefault(dia, []).append(tr)

    dias_json = []
    liq_total = 0.0
    n_total = 0
    w_total = 0
    for dia in dias:
        ops = por_dia.get(dia, [])
        candles = m5_do_dia(win_m1, dia)
        if not candles["t"]:
            continue
        ops_json = []
        liq_dia = 0.0
        win_dia = 0
        for tr in ops:
            pnl = tr.pnl_brl
            liq_dia += pnl
            win_dia += 1 if pnl > 0 else 0
            box = box_antes_da_entrada(win_m1, tr.entry_ts)
            ops_json.append({
                "te": tr.entry_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "ts": tr.exit_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "d": 1 if tr.side == "long" else -1,
                "e": round(float(tr.entry_price), 1),
                "x": round(float(tr.exit_price), 1),
                "mot": str(tr.exit_reason.value if hasattr(tr.exit_reason, "value") else tr.exit_reason),
                "rs": round(float(pnl), 2),
                "box": box,
            })
        liq_total += liq_dia
        n_total += len(ops)
        w_total += win_dia
        dias_json.append({
            "dia": dia.strftime("%Y-%m-%d"), "liq": round(liq_dia, 2),
            "n": len(ops), "win": win_dia, "ops": ops_json, **candles,
        })

    win_pct = round(100.0 * w_total / n_total, 1) if n_total else 0.0
    return {
        "hora": nome, "num": None,
        "params": f"retângulo: janela={JANELA_BARRAS}barras · stop={STOP_FRACAO}×largura · "
                  f"alvo={ALVO_FRACAO:.2f}×largura ({ALVO_MULTIPLO}× o stop) · capital teste R$1.000",
        "nota": "entrada no meio do retângulo (limite), stop e alvo fatiados por ordem-limite real, "
                "só o stop a mercado; fila WIN@ não calibrada (premissa otimista, enche no toque); "
                "a faixa tracejada é o retângulo RECONSTRUÍDO fora da estratégia (mesma janela, "
                "mesma função pura) só para ilustrar — pode divergir em 1 barra do estado interno real.",
        "tot": {"liq": round(liq_total, 2), "n": n_total, "w": w_total, "win": win_pct,
                "dias": len(dias)},
        "dias": dias_json,
    }


def main() -> None:
    win_m1 = b.carrega_win()
    dias_is = b.dias_da_janela(win_m1, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    dias_oos1 = b.dias_da_janela(win_m1, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)

    testes = [
        exporta_janela("Descoberta (jan-jun/26)", dias_is, congelado=False, win_m1=win_m1),
        exporta_janela("Conferência (jul-ago/26)", dias_oos1, congelado=True, win_m1=win_m1),
    ]
    for i, t in enumerate(testes, start=1):
        t["num"] = i

    OUT.write_text(json.dumps(testes, ensure_ascii=False), encoding="utf-8")
    tamanho_mb = OUT.stat().st_size / 1_048_576
    print(f"\nSalvo em {OUT} ({tamanho_mb:.2f} MB)", flush=True)


if __name__ == "__main__":
    main()
