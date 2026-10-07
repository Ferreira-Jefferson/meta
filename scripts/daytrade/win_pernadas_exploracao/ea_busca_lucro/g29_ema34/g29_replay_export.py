# -*- coding: utf-8 -*-
"""Exporta o JSON de replay (candles M5 + EMA34 + operações + retângulo
detectado) da candidata PADRÃO atual (G21 + filtro EMA34, `g29`), nas 3
janelas de 2026 (descoberta, conferência, setembro). Substitui
`g21_replay_export.py` como fonte da página de replay, porque EMA34 agora
é o padrão (ver `ORQUESTRACAO.md`, "PADRÃO ATUAL").

Só visualização -- não re-valida nada, não muda nenhum número já reportado.
Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/g29_ema34/g29_replay_export.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import g29_base as b  # noqa: E402

sys.path.insert(0, str(b.ROOT / "src"))
from strategy.daytrade.lab.win_retangulo import detecta_retangulo  # noqa: E402

JANELA_BARRAS = 20
TOLERANCIA_BORDA = 0.20
PERIODO_EMA = 34

OUT = Path(__file__).parent / "replay_g29.json"


def box_antes_da_entrada(win_m1: pd.DataFrame, entry_ts: pd.Timestamp) -> dict | None:
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


def m5_do_dia(win_m1: pd.DataFrame, ema: pd.Series, dia) -> dict:
    dia_df = win_m1[win_m1.index.date == dia]
    m5 = dia_df.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    ema_dia = ema.reindex(dia_df.index).resample("5min", label="left", closed="left").last() \
        if len(dia_df) else ema.reindex(m5.index)
    ema_dia = ema_dia.reindex(m5.index)
    return {
        "t": [ts.strftime("%Y-%m-%d %H:%M:%S") for ts in m5.index],
        "o": [round(float(v), 1) for v in m5["open"]],
        "h": [round(float(v), 1) for v in m5["high"]],
        "l": [round(float(v), 1) for v in m5["low"]],
        "c": [round(float(v), 1) for v in m5["close"]],
        "ema": [round(float(v), 1) if v == v else None for v in ema_dia],
    }


def exporta_janela(nome: str, dias: list, congelado: bool, win_m1: pd.DataFrame, ema: pd.Series) -> dict:
    res, _ = b.roda(dias, congelado=congelado, periodo=PERIODO_EMA)
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
        candles = m5_do_dia(win_m1, ema, dia)
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
        "params": f"retângulo + EMA{PERIODO_EMA}: janela={JANELA_BARRAS}barras · stop=0,45×largura · "
                  f"alvo=0,90×largura (2× o stop) · venda só com fechamento ≤ EMA{PERIODO_EMA}, "
                  f"compra só com fechamento ≥ EMA{PERIODO_EMA} · capital teste R$1.000",
        "nota": "PADRÃO ATUAL (2026-10-05): candidata nº1 com o filtro de EMA34 — melhorou o "
                "resultado nos 3 períodos sem exceção frente ao retângulo sem filtro (ver "
                "ORQUESTRACAO.md). Ainda NÃO validada para operar ao vivo: setembro continua "
                "negativo, com 80,8% de chance de ruína projetada. Entrada no meio do retângulo "
                "(limite), stop e alvo fatiados por ordem-limite real, só o stop a mercado; fila "
                "WIN@ não calibrada (premissa otimista, enche no toque). A faixa tracejada "
                "amarela é o retângulo RECONSTRUÍDO fora da estratégia (ilustrativo); a linha "
                "laranja é a EMA34 que decide se a operação passa ou é descartada.",
        "tot": {"liq": round(liq_total, 2), "n": n_total, "w": w_total, "win": win_pct,
                "dias": len(dias)},
        "dias": dias_json,
    }


def main() -> None:
    win_m1 = b.carrega_win()
    ema = win_m1["close"].ewm(span=PERIODO_EMA, adjust=False).mean()

    dias_is = b.dias_da_janela(win_m1, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    dias_oos1 = b.dias_da_janela(win_m1, b.CORTE_IS_FIM, b.CORTE_OOS1_FIM)
    dias_oos2 = b.dias_da_janela(win_m1, b.CORTE_OOS1_FIM, b.CORTE_OOS2_FIM)

    testes = [
        exporta_janela("Descoberta (jan-jun/26)", dias_is, congelado=False, win_m1=win_m1, ema=ema),
        exporta_janela("Conferência (jul-ago/26)", dias_oos1, congelado=True, win_m1=win_m1, ema=ema),
        exporta_janela("Setembro/26 (teste final)", dias_oos2, congelado=True, win_m1=win_m1, ema=ema),
    ]
    for i, t in enumerate(testes, start=1):
        t["num"] = i

    OUT.write_text(json.dumps(testes, ensure_ascii=False), encoding="utf-8")
    tamanho_mb = OUT.stat().st_size / 1_048_576
    print(f"\nSalvo em {OUT} ({tamanho_mb:.2f} MB)", flush=True)


if __name__ == "__main__":
    main()
