"""WDO F1 (`wdo_grid_reload_maker`, T2/S16 de producao) -- PARTE B: o CORTE
POR TEMPO. Fechar a posicao a MERCADO quando ela passa de N segundos aberta.

ORIGEM: observacao do dono (2026-09-15) -- "as operacoes que falham sao acima
de um determinado tempo; acima de 6 minutos foram as que deram prejuizo".

POR QUE ESTA PARTE EXISTE, e por que a Parte A sozinha nao responde: duracao
nao e' observavel na entrada, e' consequencia do desfecho. Com alvo de 2
ticks e stop de 16, o vencedor precisa de um movimento pequeno a favor e o
perdedor de um 8x maior contra -- "vencedor curto, perdedor longo" e'
mecanica da geometria, nao previsao. A unica forma acionavel da hipotese e'
INTERVIR: cortar aos N minutos muda quais trades acontecem e a que preco
fecham. E cortar tem custo proprio -- mata tambem os vencedores lentos e paga
saida a mercado (`slippage_ticks`) onde antes esperava fila de alvo.

MECANISMO. `corte_segundos` NAO existe na classe de producao e este script
NAO edita `wdo_grid_reload_maker.py` -- vive numa subclasse local
(`WdoGridReloadMakerComCorteDeTempo`), mesmo padrao de
`wdof1_reload_delay_is_oos_2026_09_11.py`. O override e' fino: delega pra
classe-mae PRIMEIRO (que faz a contabilidade de fill/reload e pode ter
acoes proprias -- defesa, trailing, stop de sessao) e so' emite
`Exit(reason="corte_tempo")` quando a mae nao devolveu acao nenhuma E a
posicao mais antiga ja passou de `corte_segundos`. `corte_segundos<=0` e'
byte-a-byte o motor de producao (a linha de CONTROLE da tabela).

O `Exit` e' filado pelo motor e executa na ABERTURA da barra seguinte pagando
`slippage_ticks` (`machine.py`, `IntradayExitReason.SIGNAL`) -- em base de
tick a barra seguinte e' o negocio seguinte, entao e' saida a mercado
imediata, que e' exatamente o que um corte por tempo pode prometer ao vivo.
NAO e' violacao do desenho fechado de execucao: o desenho proibe ENTRADA e
ALVO a mercado; o corte por tempo e' protecao, mesma categoria do stop.

MOTOR: identico ao de producao -- `config_for`/`profile_for`, fila calibrada
(438/489), alvo fatiado real sem prazo, `anchor_exits_at_fill=True`, tick.

CAPITAL: duas passadas. R$375 e' a de PRODUCAO e e' a que decide (o corte
muda a perda por derrota, logo muda a censura por caixa, que e' efeito real).
R$15.000 e' DIAGNOSTICA -- abaixo do marco do 2o contrato (R$16.000 a S16),
entao sempre 1 contrato, sem censura: da' o efeito do corte sobre a
EXPECTATIVA por operacao com n ~10x maior. Nao e' verdito de retorno.

DISCIPLINA: varre no IS, escolhe NO MAXIMO UM valor, e so' esse vai ao OOS.

Uso: `python -u scripts/daytrade/wdof1_corte_por_tempo_2026_09_15.py`
"""
from __future__ import annotations

import math
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
CAPITAL_DIAG_BRL = 15000.0

TICK_PARQUET_LOCAL = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)

CORTES_S = [0.0, 60.0, 120.0, 180.0, 300.0, 360.0, 600.0]


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


def _bars_path(dia: date) -> Path:
    dia_str = dia.isoformat()
    for prefixo in ("WDOV26_", "WDO_at_", "WDO_hist_"):
        p = BARS_DIR / f"{prefixo}{dia_str}.parquet"
        if p.exists():
            return p
    return BARS_DIR / f"WDO_hist_{dia_str}.parquet"


def construir_classe_com_corte():
    """Subclasse local -- construida por funcao (nao em modulo separado) para
    o worker do `ProcessPoolExecutor` conseguir reconstrui-la importando este
    proprio arquivo."""
    from strategy.daytrade.base import Exit
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker

    class WdoGridReloadMakerComCorteDeTempo(WdoGridReloadMaker):
        def __init__(self, *args, corte_segundos: float = 0.0, **kwargs):
            if corte_segundos < 0:
                raise ValueError("corte_segundos nao pode ser negativo (0 = sem corte).")
            super().__init__(*args, **kwargs)
            self.corte_segundos = float(corte_segundos)

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
            if acoes or self.corte_segundos <= 0 or not positions:
                return acoes
            mais_antiga = min(p.entry_ts for p in positions)
            if (ts - mais_antiga).total_seconds() >= self.corte_segundos:
                return [Exit(reason="corte_tempo")]
            return acoes

    return WdoGridReloadMakerComCorteDeTempo


def _roda_celula(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    import inspect

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    dia: date = spec["dia"]
    corte = float(spec["corte"])
    capital = float(spec["capital"])
    bars = pd.read_parquet(_bars_path(dia))
    if bars.empty:
        return {"spec": spec, "erro": "bars vazio"}

    Cls = construir_classe_com_corte()
    robo = get_daytrade_robot("wdo_grid_reload_maker")
    params = [p for p in inspect.signature(WdoGridReloadMaker.__init__).parameters if p != "self"]
    strat = Cls(corte_segundos=corte, **{p: getattr(robo, p) for p in params})

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
    trades = list(res.trades)
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl < 0]
    eq = res.equity_curve
    n_corte = sum(1 for t in trades
                  if str(getattr(t.exit_reason, "value", t.exit_reason)) == "signal")
    soma_dur = sum((t.exit_ts - t.entry_ts).total_seconds() for t in trades)
    return {
        "spec": {"dia": dia.isoformat(), "corte": corte, "capital": capital},
        "n": len(trades),
        "n_ganhos": len(ganhos),
        "n_perdas": len(perdas),
        "soma_ganhos": sum(ganhos),
        "soma_perdas": sum(perdas),
        "pnl": sum(t.pnl_brl for t in trades),
        "n_corte": n_corte,
        "soma_dur_s": soma_dur,
        "maxdd_brl": float((eq.cummax() - eq).max()) if len(eq) else 0.0,
        "caixa_min": float(eq.min()) if len(eq) else float("nan"),
        "recusas": contador["recusas"],
    }


def _resumir(cels: list[dict]) -> dict:
    n = sum(c["n"] for c in cels)
    ng = sum(c["n_ganhos"] for c in cels)
    npd = sum(c["n_perdas"] for c in cels)
    sg = sum(c["soma_ganhos"] for c in cels)
    sp = sum(c["soma_perdas"] for c in cels)
    liq = sum(c["pnl"] for c in cels)
    dias = len(cels)
    ganho_medio = sg / ng if ng else float("nan")
    perda_media = abs(sp / npd) if npd else float("nan")
    be = 100.0 * perda_media / (ganho_medio + perda_media) if ng and npd else float("nan")
    win = 100.0 * ng / n if n else float("nan")
    lo, hi = ic_wilson(ng, n)
    if n == 0 or math.isnan(be):
        vd = "sem dado"
    elif hi < be:
        vd = "NEGATIVA"
    elif lo > be:
        vd = "POSITIVA"
    else:
        vd = "indefinido"
    return dict(
        n=n, win=win, ganho_medio=ganho_medio, perda_media=perda_media, be=be,
        lo=lo, hi=hi, veredito=vd, liquido=liq,
        por_op=liq / n if n else float("nan"),
        liq_preg=liq / dias if dias else float("nan"),
        trd_preg=n / dias if dias else float("nan"),
        maxdd=max((c["maxdd_brl"] for c in cels), default=0.0),
        caixa_min=min((c["caixa_min"] for c in cels), default=float("nan")),
        preg_pos=sum(1 for c in cels if c["pnl"] > 0),
        preg_neg=sum(1 for c in cels if c["pnl"] < 0),
        preg_cens=sum(1 for c in cels if c["recusas"] > 0),
        preg_sem_trade=sum(1 for c in cels if c["n"] == 0),
        dias=dias,
        pct_corte=100.0 * sum(c["n_corte"] for c in cels) / n if n else float("nan"),
        dur_media=sum(c["soma_dur_s"] for c in cels) / n if n else float("nan"),
    )


def _tabela(titulo: str, resumo: dict, chaves: list[float]) -> None:
    cab = (f"{'corte':<10}{'n':>7}{'win%':>8}{'BE emp':>8}{'IC95 win%':>17}{'veredito':>11}"
           f"{'R$/op':>8}{'liquido':>12}{'R$/preg':>10}{'trd/preg':>9}{'%cortes':>9}"
           f"{'dur.med':>9}{'MaxDD':>10}{'caixa min':>10}{'preg+':>7}{'preg-':>7}"
           f"{'cens':>6}{'s/trade':>8}")
    print("=" * len(cab))
    print(titulo)
    print("=" * len(cab))
    print(cab)
    print("-" * len(cab))
    for k in chaves:
        r = resumo[k]
        rot = "sem corte" if k == 0 else f"{k / 60:.0f} min"
        ic = f"[{r['lo']:.2f};{r['hi']:.2f}]"
        print(f"{rot:<10}{r['n']:>7}{r['win']:>7.2f}%{r['be']:>7.2f}%{ic:>17}{r['veredito']:>11}"
              f"{r['por_op']:>8.2f}{r['liquido']:>12.2f}{r['liq_preg']:>10.2f}{r['trd_preg']:>9.1f}"
              f"{r['pct_corte']:>8.1f}%{r['dur_media']:>8.0f}s{r['maxdd']:>10.2f}{r['caixa_min']:>10.2f}"
              f"{r['preg_pos']:>7}{r['preg_neg']:>7}{r['preg_cens']:>6}{r['preg_sem_trade']:>8}")
    print("-" * len(cab))


def main() -> None:
    t0 = time.perf_counter()
    meta = pd.read_parquet(TICK_PARQUET_LOCAL, columns=["last"])
    dias_locais = sorted(set(meta.index.date))
    del meta
    extras = [d for d in (date(2026, 9, 8), date(2026, 9, 9)) if _bars_path(d).exists()]
    dias = sorted(set(dias_locais) | set(extras))
    corte_split = round(len(dias) * 2 / 3)
    IS, OOS = dias[:corte_split], dias[corte_split:]
    print(f"[split] IS  = {IS[0]} .. {IS[-1]} ({len(IS)} pregoes)")
    print(f"[split] OOS = {OOS[0]} .. {OOS[-1]} ({len(OOS)} pregoes)\n", flush=True)

    specs = [{"dia": d, "corte": c, "capital": cap}
             for d in IS for c in CORTES_S
             for cap in (CAPITAL_REAL_BRL, CAPITAL_DIAG_BRL)]
    print(f"[IS] {len(specs)} celulas ({len(CORTES_S)} cortes x 2 capitais x "
          f"{len(IS)} pregoes)\n", flush=True)

    res: list[dict] = []
    feitos = 0
    with ProcessPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_roda_celula, s): s for s in specs}
        for fut in as_completed(futs):
            r = fut.result()
            feitos += 1
            if "erro" in r:
                print(f"  [{feitos}/{len(specs)}] ERRO {r['erro']}", flush=True)
                continue
            res.append(r)
            s = r["spec"]
            if feitos % 25 == 0 or feitos == len(specs):
                print(f"  [{feitos}/{len(specs)}] {s['dia']} corte={s['corte']:>5.0f}s "
                      f"cap={s['capital']:>6.0f} n={r['n']:>4} pnl=R${r['pnl']:>9.2f}",
                      flush=True)

    for cap, nome in (
        (CAPITAL_REAL_BRL, "PRODUCAO R$375 (e' esta que decide)"),
        (CAPITAL_DIAG_BRL, "DIAGNOSTICA R$15.000 -- 1 contrato, sem censura (NAO e' verdito de retorno)"),
    ):
        resumo = {c: _resumir([r for r in res
                               if r["spec"]["corte"] == c and r["spec"]["capital"] == cap])
                  for c in CORTES_S}
        _tabela(f"IS ({len(IS)} pregoes) -- corte por tempo -- {nome}", resumo, CORTES_S)
        print(flush=True)

    print(f"[fim] {(time.perf_counter() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
