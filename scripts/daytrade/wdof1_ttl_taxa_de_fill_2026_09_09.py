"""Com que FREQUENCIA o alvo fatiado preenche na limite, em vez de estourar o
prazo e sair a mercado? (WDO F1, T2/S16, 10 pregoes do IS, capital R$375.)

## A pergunta, e por que ela nao e' a mesma que "qual ttl lucra mais"

A varredura de `exit_ttl_bars` (`wdof1_exit_ttl_bars_micro_2026_09_09.py`)
comparou LIQUIDO e saiu serrilhada: vizinhos diferem mais entre si do que a
tendencia da faixa, ou seja, 10 pregoes nao separam o parametro por P&L.

Mas o dono fez outra pergunta, e essa tem resposta mais estavel: subir o prazo
**aumenta a chance de sair na limite**? Isso e' uma TAXA, nao um P&L -- nao
depende de qual sequencia de trades a amostra sorteou, entao um n de 10
pregoes ja diz alguma coisa.

E' a pergunta que importa por dois motivos, e o segundo so' apareceu hoje:

 1. Toda saida a mercado paga o deslize que `fatiar_saida_alvo` existe para
    evitar (item 4.8/6.19 de LICOES_DE_PRODUCAO.md).
 2. **Toda saida a mercado e' uma ordem a mais viajando enquanto a
    ordem-limite ainda esta viva no livro.** Em 2026-09-09, no primeiro dia
    real com o fatiar ligado, foi exatamente essa colisao que abriu um short
    de 2 CONTRATOS numa conta de 1 e custou R$80,00: o fechamento a mercado
    executou, a resposta do MT5 nao confirmou, o robo se achou comprado ainda
    e reverteu -- e a limite orfa de saida preencheu como ENTRADA nova.
    Menos estouro de prazo e' menos exposicao a esse modo de falha, mesmo
    depois de o bug ser corrigido.

## Como a medicao distingue as duas saidas

`machine._resolve_simulated_split_exit` fecha a fatia de dois jeitos, e AMBOS
viram `exit_reason=TARGET` no trade -- contar por motivo nao separa nada
(mesmo ponto cego do diario ao vivo):

  * preencheu na limite -> `exit_price` e' EXATAMENTE o nivel do alvo;
  * estourou o prazo     -> fecha a MERCADO, em `bar.close`, que so' por
                            coincidencia cairia no nivel.

Entao o discriminador e' `exit_price == alvo declarado`, com o alvo
reconstruido da propria posicao (`entry_price +/- profit_ticks * tick`). O
mesmo criterio que `live.intraday_runtime` usa via `deslize_vs_alvo_brl`.

Uso: `python -u scripts/daytrade/wdof1_ttl_taxa_de_fill_2026_09_09.py`
      `WDOF1_TTLS=8,20 python -u ...`  (roda so' os pedidos)
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
ATE_DIA = date(2026, 3, 12)
MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "4"))

#: `exit_ttl_bars` sai daqui -- e' o eixo varrido.
CAMPOS_KWARGS = (
    "symbol", "tick_size", "level_spacing_ticks", "profit_ticks", "stop_ticks",
    "reanchor_mode", "reancora_min_segundos", "reancora_min_ticks",
    "max_trades_per_side", "session_stop_brl", "quantity",
    "margin_per_contract_brl", "margin_buffer", "hard_cap_contratos",
    "risco_pct_por_trade", "point_value_brl",
    "defesa_ativa", "defesa_gatilho_stop_pct", "defesa_alvo_proximidade_pct",
    "trailing_ativo", "trailing_recuo_ticks",
    "gate_atividade_ativo", "gate_volume_min", "gate_janela_segundos",
)

TTLS_PADRAO = (5, 8, 12, 20, 30, 60, 130)


def _ttls() -> tuple[int, ...]:
    bruto = os.environ.get("WDOF1_TTLS", "").strip()
    if not bruto:
        return TTLS_PADRAO
    return tuple(int(p) for p in bruto.split(",") if p.strip())


_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars() -> pd.DataFrame:
    if "bars" not in _DF_CACHE:
        _DF_CACHE["bars"] = pd.read_parquet(
            CACHE, columns=["open", "high", "low", "close", "volume"],
            filters=[("janela", "==", "IS"), ("dia", "<=", ATE_DIA)],
        ).sort_index()
    return _DF_CACHE["bars"]


def _roda_uma(ttl: int) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from core.models import IntradayExitReason
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars()
    robo = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {c: getattr(robo, c) for c in CAMPOS_KWARGS}
    kwargs["fatiar_saida_alvo"] = True
    kwargs["exit_ttl_bars"] = ttl
    strat = WdoGridReloadMaker(**kwargs)

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    tick = cfg.costs.tick_size
    pv = cfg.costs.point_value_brl

    t0 = time.perf_counter()
    res = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    alvos = [t for t in res.trades if t.exit_reason == IntradayExitReason.TARGET]
    na_limite, a_mercado, perdido = 0, 0, 0.0
    for t in alvos:
        # O nivel que a estrategia declarou para ESTE trade.
        alvo = (t.entry_price + strat.profit_ticks * tick if t.side == "long"
                else t.entry_price - strat.profit_ticks * tick)
        faltou = (alvo - t.exit_price) if t.side == "long" else (t.exit_price - alvo)
        if abs(faltou) < tick / 4:
            na_limite += 1
        else:
            a_mercado += 1
            perdido += faltou * pv * t.quantity

    return {
        "ttl": ttl, "dt": dt,
        "alvos": len(alvos), "na_limite": na_limite, "a_mercado": a_mercado,
        "pct_limite": (100.0 * na_limite / len(alvos)) if alvos else float("nan"),
        "perdido_brl": perdido,
        "liquido": res.net_profit_brl if hasattr(res, "net_profit_brl") else None,
        "trades": len(res.trades),
    }


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(f"cache ausente: {CACHE}")
    ttls = _ttls()
    print(f"[ttl_taxa_de_fill] T2 fatiado, 10 pregoes IS, R${CAPITAL_REAL_BRL:.0f}, "
          f"ttls={list(ttls)}, {MAX_WORKERS} processos\n", flush=True)

    out: dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=max(1, min(len(ttls), MAX_WORKERS))) as pool:
        futs = {pool.submit(_roda_uma, t): t for t in ttls}
        for f in as_completed(futs):
            r = f.result()
            out[r["ttl"]] = r
            print(f"  ttl {r['ttl']:>4}: {r['na_limite']:>5}/{r['alvos']:<5} na limite "
                  f"({r['pct_limite']:5.1f}%)  |  {r['a_mercado']:>4} a mercado  |  "
                  f"deslize R$ {r['perdido_brl']:>10,.2f}  [{r['dt']:.0f}s]", flush=True)

    print(f"\n{'ttl':>5} | {'~tempo':>7} | {'alvos':>6} | {'na limite':>10} | "
          f"{'a mercado':>10} | {'% limite':>8} | {'deslize R$':>12}")
    print("-" * 78)
    for t in ttls:
        r = out.get(t)
        if not r:
            continue
        seg = t * 0.062  # mediana medida de espacamento entre negocios
        print(f"{t:>5} | {seg:>6.1f}s | {r['alvos']:>6} | {r['na_limite']:>10} | "
              f"{r['a_mercado']:>10} | {r['pct_limite']:>7.1f}% | {r['perdido_brl']:>12,.2f}")


if __name__ == "__main__":
    main()
