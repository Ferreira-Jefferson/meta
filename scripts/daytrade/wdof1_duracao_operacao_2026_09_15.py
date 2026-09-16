"""WDO F1 (`wdo_grid_reload_maker`, T2/S16 de producao): a DURACAO de cada
operacao contra o resultado dela.

ORIGEM: observacao do dono (2026-09-15) olhando o historico de operacoes do
robo -- "as operacoes que falham sao acima de um determinado tempo; acima de
6 minutos foram as que deram prejuizo".

O QUE ESTA PARTE FAZ (descritiva, n grande): roda o motor de PRODUCAO sobre
os 132 pregoes reais de tick e devolve TODA operacao com (entrada, saida,
duracao em segundos, R$, motivo). Nada e' filtrado nem cortado -- o objetivo
e' so' medir a distribuicao conjunta de duracao e resultado num n de cinco
digitos, em vez dos 107 trades de 2 pregoes de sombra que originaram a
pergunta.

AVISO DE LEITURA, que vale antes de qualquer tabela: duracao NAO e'
observavel na entrada -- e' consequencia do desfecho. Com alvo de 2 ticks e
stop de 16, um vencedor precisa de um movimento pequeno a favor e um
perdedor de um movimento 8x maior contra. Vencedor curto e perdedor longo e'
o comportamento MECANICO esperado, nao um sinal. A unica versao acionavel da
hipotese e' um CORTE POR TEMPO (fechar a mercado aos N minutos), que muda
quais trades acontecem -- e essa e' a Parte B
(`wdof1_corte_por_tempo_2026_09_15.py`), nao esta.

MOTOR: identico ao de producao -- `config_for`/`profile_for`, fila calibrada
de `backtest.intraday.fidelidade` (438/489), alvo fatiado real sem prazo,
`anchor_exits_at_fill=True`, `feed_kind="tick"`, geometria herdada de
`get_daytrade_robot("wdo_grid_reload_maker")`. Capital real R$375 por pregao,
cada pregao uma observacao independente.

BASE E SPLIT: mesmos de `wdof1_reload_delay_is_oos_2026_09_11.py` --
`data/raw_ticks/WDO_A_.parquet` + os 2 extras cacheados (09-08, 09-09),
corte cronologico 2/3-1/3: IS 88 pregoes, OOS 44.

Uso: `python -u scripts/daytrade/wdof1_duracao_operacao_2026_09_15.py`
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
#: SEGUNDA passada, DIAGNOSTICA (nao e' verdito de retorno -- ver o topo).
#: Com R$375 o robo e' calado pelo portao de capital em quase todo pregao
#: (476 recusas / 4 trades em 2026-09-04), e a amostra de duracao que sobra
#: e' so' o comeco de cada pregao. Uma passada com caixa folgado NAO mede
#: retorno (a regra do repo continua valendo), mas devolve a distribuicao
#: conjunta duracao x desfecho SEM a censura do caixa, que e' a pergunta
#: desta parte.
CAPITAL_DIAGNOSTICO_BRL = 15000.0  # abaixo do marco do 2o contrato (R$16.000 a S16): 1 contrato sempre
CAPITAIS = [CAPITAL_REAL_BRL, CAPITAL_DIAGNOSTICO_BRL]

TICK_PARQUET_LOCAL = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)
SAIDA_CSV = RAIZ / "scratch" / "wdof1_duracao_operacoes_2026_09_15.csv"


def _bars_path(dia: date) -> Path:
    dia_str = dia.isoformat()
    for prefixo in ("WDOV26_", "WDO_at_", "WDO_hist_"):
        p = BARS_DIR / f"{prefixo}{dia_str}.parquet"
        if p.exists():
            return p
    return BARS_DIR / f"WDO_hist_{dia_str}.parquet"


def _roda_pregao(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    import inspect

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    dia: date = spec["dia"]
    capital = float(spec["capital"])
    bars = pd.read_parquet(_bars_path(dia))
    if bars.empty:
        return {"dia": dia.isoformat(), "capital": capital, "erro": "bars vazio", "trades": []}

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    params = [p for p in inspect.signature(WdoGridReloadMaker.__init__).parameters if p != "self"]
    strat = WdoGridReloadMaker(**{p: getattr(robo, p) for p in params})

    contador = {"recusas": 0}
    _orig = strat.on_order_rejected

    def _contado(ts, _o=_orig, _c=contador):
        _c["recusas"] += 1
        return _o(ts)

    strat.on_order_rejected = _contado

    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    linhas = []
    for t in res.trades:
        linhas.append({
            "dia": dia.isoformat(),
            "capital": capital,
            "side": t.side,
            "entry_ts": t.entry_ts.isoformat(),
            "exit_ts": t.exit_ts.isoformat(),
            "dur_s": (t.exit_ts - t.entry_ts).total_seconds(),
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "qty": t.quantity,
            "reason": str(getattr(t.exit_reason, "value", t.exit_reason)),
            "detail": t.exit_detail or "",
            "pnl": t.pnl_brl,
        })
    eq = res.equity_curve
    return {
        "dia": dia.isoformat(),
        "capital": capital,
        "trades": linhas,
        "pnl": sum(l["pnl"] for l in linhas),
        "caixa_min": float(eq.min()) if len(eq) else float("nan"),
        "recusas": contador["recusas"],
    }


def main() -> None:
    t0 = time.perf_counter()
    ticks_meta = pd.read_parquet(TICK_PARQUET_LOCAL, columns=["last"])
    dias_locais = sorted(set(ticks_meta.index.date))
    del ticks_meta
    extras = [d for d in (date(2026, 9, 8), date(2026, 9, 9)) if _bars_path(d).exists()]
    dias = sorted(set(dias_locais) | set(extras))
    corte = round(len(dias) * 2 / 3)
    IS, OOS = dias[:corte], dias[corte:]
    print(f"[split] IS  = {IS[0]} .. {IS[-1]} ({len(IS)} pregoes)")
    print(f"[split] OOS = {OOS[0]} .. {OOS[-1]} ({len(OOS)} pregoes)", flush=True)

    faltando = [d for d in dias if not _bars_path(d).exists()]
    if faltando:
        from market_data_intraday.tick_bars import ticks_to_degenerate_bars
        print(f"[cache] convertendo {len(faltando)} pregoes ...", flush=True)
        ticks = pd.read_parquet(TICK_PARQUET_LOCAL)
        alvo = set(faltando)
        for d, sub in ticks.groupby(ticks.index.date):
            if d in alvo and not sub.empty:
                ticks_to_degenerate_bars(sub).to_parquet(BARS_DIR / f"WDO_hist_{d.isoformat()}.parquet")
        del ticks

    todas: list[dict] = []
    feitos = 0
    with ProcessPoolExecutor(max_workers=8) as pool:
        specs = [{"dia": d, "capital": c} for d in dias for c in CAPITAIS]
        futs = {pool.submit(_roda_pregao, s): s for s in specs}
        for fut in as_completed(futs):
            r = fut.result()
            feitos += 1
            if "erro" in r:
                print(f"  [{feitos}/{len(specs)}] {r['dia']}: ERRO {r['erro']}", flush=True)
                continue
            todas.extend(r["trades"])
            print(f"  [{feitos}/{len(specs)}] {r['dia']} cap={r['capital']:>7.0f}  n={len(r['trades']):>5}  "
                  f"pnl=R${r['pnl']:>10.2f}  caixa_min=R${r['caixa_min']:>8.2f}  "
                  f"recusas={r['recusas']}", flush=True)

    df = pd.DataFrame(todas)
    SAIDA_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA_CSV, index=False)
    print(f"\n[ok] {len(df)} operacoes gravadas em {SAIDA_CSV} "
          f"({(time.perf_counter()-t0)/60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
