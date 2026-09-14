"""WDO F1 (grid maker puro): `combo_T3` (filtro de regime `fade_off/20min` +
alvo maior `profit_ticks=3`, `stop_ticks=16`) vs baseline `WdoGridReloadMaker`
T2/S16 puro, nas ULTIMAS DUAS SEMANAS DE PREGAO ate' hoje (2026-09-11,
pregao PARCIAL -- so' o que ja negociou ate' o momento em que este script
rodou).

NAO E' UM NOVO VEREDITO -- e' uma checagem de janela recente por cima do
teste que ja decide: `wdof1_combo_t3_is_oos_real_2026_09_11.py` mediu 132
pregoes reais (IS 88 dias 2026-02-27..07-06, OOS 44 dias 2026-07-07..09-09) e
achou combo_T3 NEGATIVO no IS e INDEFINIDO-mas-negativo no OOS (liquido
-R$1.629,50 em 44 pregoes). O LIMIAR DE REGIME (fade_off/20min = 11,00
ticks) e' EXATAMENTE o mesmo calibrado la' (percentil 70 de |retorno M1
20min|, 48.393 observacoes, SOMENTE 2026-02-27..2026-07-06) -- REAPROVEITADO
aqui sem recalibrar (o pedido explicito e' nao recalibrar de novo).

DIAS: 10 pregoes uteis, 2026-08-28 .. 2026-09-11, pulando fins de semana e o
feriado de 2026-09-07 (Independencia -- terminal devolve 0 ticks nesse dia,
ja confirmado em rodadas anteriores da mesma semana).

DADO: os 8 pregoes 2026-08-28..2026-09-09 vem de barra degenerada JA
CACHEADA (mesmo cache que o teste IS/OOS de 132 pregoes gerou, converte
direto do parquet canonico local `WDO_A_.parquet`). 2026-09-10 e 2026-09-11
NAO estao no parquet canonico (que para em 09-04) -- ja estavam cacheados de
rodadas anteriores desta mesma sessao via tick fresco do MT5
(`fetch_ticks_range`, simbolo continuo "WDO@" -> WDOV26 no terminal, mesmo
mapa que os 4 slots de sombra ativos usam agora, ver `db/live_process.json`).
O cache de HOJE (09-11) foi REFRESCADO por este script antes de rodar (ver
`refresh_hoje.py` na mesma sessao) para cobrir o maximo de pregao parcial
disponivel no momento da medicao (12:00:41 -> 18:33:31 UTC).

MOTOR: o MESMO de producao, sem relaxar nada -- `config_for`/`profile_for`,
fila calibrada de `backtest.intraday.fidelidade` (438/489), alvo fatiado
real (`fatiar_saida_alvo=True`, sem prazo -- `EXIT_TTL_BARS_SEM_PRAZO`),
capital REAL R$375/pregao, NUNCA reposto entre pregoes -- cada pregao e' uma
observacao independente (`get_daytrade_robot("wdo_grid_reload_maker")`
fornece os kwargs de producao, mesmo padrao de todos os scripts WDO F1
anteriores).

REUTILIZACAO DE CODIGO (pedido explicito): `RegimeLookup`, `RegimeReloadVariant`,
`variante_class` e `ic_wilson` sao IMPORTADOS de
`wdof1_regime_medio_prazo_2026_09_11.py` -- nao reescritos. So' a construcao
do regime com limiar FIXO (sem recalibrar) e' local."""
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0

TICK_PARQUET_LOCAL = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)

ESCALA_MIN = 20
LIMIAR_REGIME_TICKS = 11.00  # REAPROVEITADO de wdof1_combo_t3_is_oos_real_2026_09_11 -- NAO recalibrar

# 10 pregoes uteis, 2026-08-28..2026-09-11, pulando fim de semana e o feriado
# de 07/09 (Independencia). 09-11 e' HOJE -- pregao PARCIAL.
DIAS_TESTE = [
    date(2026, 8, 28), date(2026, 8, 31),
    date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4),
    date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10), date(2026, 9, 11),
]
DIA_HOJE_PARCIAL = date(2026, 9, 11)

VARIANTES = ["baseline", "combo_T3"]


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


# ------------------------------------------------------------- cache de barras
def _bars_path(dia: date) -> Path:
    dia_str = dia.isoformat()
    for prefixo in ("WDOV26_", "WDO_at_", "WDO_hist_"):
        p = BARS_DIR / f"{prefixo}{dia_str}.parquet"
        if p.exists():
            return p
    return BARS_DIR / f"WDO_hist_{dia_str}.parquet"


def preparar_cache_de_barras(dias: list[date]) -> None:
    """So' converte do parquet canonico local os dias que ainda faltam e que
    estao dentro da cobertura do parquet (ate' 2026-09-04) -- 09-08 em diante
    ja vieram cacheados de rodadas anteriores desta mesma sessao (tick MT5
    direto, ver docstring do modulo)."""
    faltando = {d for d in dias if not _bars_path(d).exists()}
    if not faltando:
        print(f"[cache] {len(dias)} pregoes ja cacheados em barra degenerada -- nada a converter.")
        return
    faltando_no_parquet = {d for d in faltando if TICK_PARQUET_LOCAL.exists()}
    print(f"[cache] convertendo {len(faltando_no_parquet)} pregoes de tick local -> barra "
          f"degenerada (fonte: {TICK_PARQUET_LOCAL.name}) ...", flush=True)
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars

    ticks = pd.read_parquet(TICK_PARQUET_LOCAL)
    convertidos = 0
    for d, sub in ticks.groupby(ticks.index.date):
        if d not in faltando or sub.empty:
            continue
        bars = ticks_to_degenerate_bars(sub)
        bars.to_parquet(BARS_DIR / f"WDO_hist_{d.isoformat()}.parquet")
        convertidos += 1
    del ticks
    print(f"[cache] {convertidos} pregoes convertidos e gravados em {BARS_DIR}", flush=True)
    ainda_faltando = sorted(d for d in faltando if not _bars_path(d).exists())
    if ainda_faltando:
        print(f"[cache] AVISO -- sem tick local/cacheado para: {ainda_faltando} "
              f"(ficam de fora do teste)")


def _m1_close_do_dia(dia: date) -> pd.Series | None:
    caminho = _bars_path(dia)
    if not caminho.exists():
        return None
    bars = pd.read_parquet(caminho)
    if bars.empty:
        return None
    s = bars["close"].resample("1min").last().dropna()
    return s if not s.empty else None


def construir_regime_limiar_fixo(dias_todos: list[date], tick_size: float, limiar_ticks: float):
    """Mesma mecanica de `construir_regime` do script IS/OOS, SEM calibrar --
    o limiar chega PRONTO (`LIMIAR_REGIME_TICKS`, reaproveitado). Devolve
    {dia: serie 'up'/'down'/'neutral' indexada no timestamp CLOSE-SAFE =
    open+1min}, mesmo contrato de `RegimeLookup`."""
    partes = []
    for d in dias_todos:
        s = _m1_close_do_dia(d)
        if s is None:
            continue
        partes.append(pd.DataFrame({"close": s, "dia": d}))
    if not partes:
        raise SystemExit("[regime] nenhum pregao com M1 disponivel")
    m1 = pd.concat(partes).sort_index()
    ret = m1.groupby("dia")["close"].transform(lambda s: s.diff(ESCALA_MIN)) / tick_size

    series: dict[date, pd.Series] = {}
    for d in dias_todos:
        sub = m1[m1["dia"] == d]
        if sub.empty:
            continue
        ts_close_safe = sub.index + pd.Timedelta(minutes=1)
        ret_dia = ret.loc[sub.index]
        rotulo = pd.Series("neutral", index=ts_close_safe)
        rotulo[ret_dia.values > limiar_ticks] = "up"
        rotulo[ret_dia.values < -limiar_ticks] = "down"
        series[d] = rotulo.sort_index()
    return series


# ------------------------------------------------------------------- worker
def _roda_celula(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import inspect
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot
    import wdof1_regime_medio_prazo_2026_09_11 as regime_mod

    dia = spec["dia"]
    variante = spec["variante"]
    caminho = _bars_path(dia)
    bars = pd.read_parquet(caminho)
    if bars.empty:
        return {"spec": spec, "erro": "bars vazio"}

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    params = [p for p in inspect.signature(WdoGridReloadMaker.__init__).parameters if p != "self"]
    kwargs = {p: getattr(robo, p) for p in params}

    lookup = spec.get("regime_lookup")

    if variante == "baseline":
        strat = WdoGridReloadMaker(**kwargs)
    elif variante == "combo_T3":
        kwargs2 = dict(kwargs)
        kwargs2["profit_ticks"] = 3
        Cls = regime_mod.variante_class(WdoGridReloadMaker)
        strat = Cls(regime_lookup=lookup, modo="fade_off", **kwargs2)
    else:
        raise ValueError(variante)

    _contador = {"recusas": 0}
    _on_rejected_original = strat.on_order_rejected

    def _on_order_rejected_contado(ts, _orig=_on_rejected_original, _c=_contador):
        _c["recusas"] += 1
        return _orig(ts)

    strat.on_order_rejected = _on_order_rejected_contado

    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    equity = res.equity_curve
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl < 0]
    return {
        "spec": {"dia": dia.isoformat(), "variante": variante},
        "n": len(trades),
        "n_ganhos": len(ganhos),
        "n_perdas": len(perdas),
        "soma_ganhos": sum(ganhos),
        "soma_perdas": sum(perdas),
        "pnl": sum(t.pnl_brl for t in trades),
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "recusas_capital": _contador["recusas"],
    }


# ------------------------------------------------------------------- agregacao
def _resumir(cels: list[dict]) -> dict:
    n = sum(c["n"] for c in cels)
    n_ganhos = sum(c["n_ganhos"] for c in cels)
    n_perdas = sum(c["n_perdas"] for c in cels)
    soma_ganhos = sum(c["soma_ganhos"] for c in cels)
    soma_perdas = sum(c["soma_perdas"] for c in cels)
    liquido_total = sum(c["pnl"] for c in cels)
    n_dias = len(cels)
    n_pos = sum(1 for c in cels if c["pnl"] > 0)
    n_neg = sum(1 for c in cels if c["pnl"] < 0)
    n_cens = sum(1 for c in cels if c["recusas_capital"] > 0)
    ganho_medio = soma_ganhos / n_ganhos if n_ganhos else float("nan")
    perda_media = abs(soma_perdas / n_perdas) if n_perdas else float("nan")
    be_emp = (100.0 * perda_media / (ganho_medio + perda_media)
              if n_ganhos and n_perdas else float("nan"))
    win = 100.0 * n_ganhos / n if n else float("nan")
    lo, hi = ic_wilson(n_ganhos, n)
    if n == 0 or math.isnan(be_emp):
        veredito = "sem dado"
    elif hi < be_emp:
        veredito = "NEGATIVA"
    elif lo > be_emp:
        veredito = "POSITIVA"
    else:
        veredito = "indefinido"
    liq_preg = liquido_total / n_dias if n_dias else float("nan")
    return dict(n=n, n_ganhos=n_ganhos, n_perdas=n_perdas, win=win,
                ganho_medio=ganho_medio, perda_media=perda_media, be_emp=be_emp,
                lo=lo, hi=hi, veredito=veredito, liquido_total=liquido_total,
                liq_preg=liq_preg, n_pos=n_pos, n_neg=n_neg, n_cens=n_cens, n_dias=n_dias)


def _fmt_dia(r):
    n, g = r["n"], r["n_ganhos"]
    win = 100.0 * g / n if n else float("nan")
    ganho = r["soma_ganhos"] / g if g else float("nan")
    perda = abs(r["soma_perdas"] / r["n_perdas"]) if r["n_perdas"] else float("nan")
    be = (100.0 * perda / (ganho + perda)) if g and r["n_perdas"] else float("nan")
    return n, win, ganho, perda, be


def main() -> None:
    from core.instruments import economics_for

    t_inicio = time.perf_counter()

    print(f"[dias] {len(DIAS_TESTE)} pregoes: {[d.isoformat() for d in DIAS_TESTE]}")
    print(f"[dias] hoje ({DIA_HOJE_PARCIAL.isoformat()}) e' PARCIAL -- so' o "
          f"que ja negociou ate' o momento em que este script rodou.\n", flush=True)

    preparar_cache_de_barras(DIAS_TESTE)

    tick_size = economics_for("WDO@").price_tick_size
    series = construir_regime_limiar_fixo(DIAS_TESTE, tick_size, LIMIAR_REGIME_TICKS)
    print(f"[regime] limiar fade_off/{ESCALA_MIN}min = {LIMIAR_REGIME_TICKS:.2f} ticks "
          f"(REAPROVEITADO de wdof1_combo_t3_is_oos_real_2026_09_11.py -- percentil 70, "
          f"48.393 obs. M1, SOMENTE 2026-02-27..2026-07-06 -- NAO recalibrado aqui)\n",
          flush=True)

    import wdof1_regime_medio_prazo_2026_09_11 as regime_mod

    specs = []
    dias_com_dado = [d for d in DIAS_TESTE if d in series]
    faltando_regime = sorted(set(DIAS_TESTE) - set(dias_com_dado))
    if faltando_regime:
        print(f"[aviso] sem M1/serie de regime para: {[d.isoformat() for d in faltando_regime]} "
              f"(ficam de fora do teste)\n")
    for d in dias_com_dado:
        lookup = regime_mod.RegimeLookup(series[d])
        for variante in VARIANTES:
            specs.append({"dia": d, "variante": variante,
                          "regime_lookup": lookup if variante == "combo_T3" else None})

    print(f"[specs] {len(specs)} celulas ({len(VARIANTES)} variantes x "
          f"{len(dias_com_dado)} pregoes), motor de producao, capital "
          f"R${CAPITAL_REAL_BRL:.0f}/pregao NUNCA reposto, fila calibrada, sem prazo\n",
          flush=True)

    resultados = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            resultados.append(r)
            s = r["spec"]
            if "erro" in r:
                print(f"  [{feitos}/{len(specs)}] {s['dia']} {s['variante']}: ERRO {r['erro']}", flush=True)
            else:
                print(f"  [{feitos}/{len(specs)}] {s['dia']} {s['variante']:<10} "
                      f"n={r['n']:>4}  pnl=R${r['pnl']:>9.2f}  caixa_min=R${r['caixa_min']:>7.2f}  "
                      f"recusas={r['recusas_capital']}", flush=True)

    print(f"\n[fim] {len(resultados)} celulas em "
          f"{(time.perf_counter()-t_inicio)/60:.1f} min\n", flush=True)

    por_dia_variante = {(r["spec"]["dia"], r["spec"]["variante"]): r
                          for r in resultados if "erro" not in r}

    # ---------------------------------------------------------- tabela por dia
    print("=" * 140)
    print("POR PREGAO -- combo_T3 (fade_off/20min limiar 11,00t + T3/S16) vs baseline T2/S16")
    print("=" * 140)
    cab = (f"{'pregao':<12}{'variante':<12}{'n':>6}{'win%':>8}{'ganho_med':>11}"
           f"{'perda_med':>11}{'BE emp.':>9}{'liquido R$':>13}{'recusas cap':>12}{'caixa_min':>11}")
    print(cab)
    print("-" * len(cab))
    for d in dias_com_dado:
        for v in VARIANTES:
            r = por_dia_variante.get((d.isoformat(), v))
            marca = "  <-- PARCIAL (hoje)" if d == DIA_HOJE_PARCIAL else ""
            if r is None:
                print(f"{d.isoformat():<12}{v:<12}  sem dado{marca}")
                continue
            n, win, ganho, perda, be = _fmt_dia(r)
            print(f"{d.isoformat():<12}{v:<12}{n:>6}{win:>7.2f}%{ganho:>11.2f}"
                  f"{perda:>11.2f}{be:>8.2f}%{r['pnl']:>13.2f}{r['recusas_capital']:>12}"
                  f"{r['caixa_min']:>11.2f}{marca}")
        print("-" * len(cab))

    # ------------------------------------------------------------- agregados
    dias_completos = [d.isoformat() for d in dias_com_dado if d != DIA_HOJE_PARCIAL]
    dias_pooled = [d.isoformat() for d in dias_com_dado]
    hoje_str = DIA_HOJE_PARCIAL.isoformat()

    grupos = {
        "POOLED (10 preg., c/ hoje parcial)": dias_pooled,
        "POOLED (9 preg. COMPLETOS, sem hoje)": dias_completos,
        f"SO' HOJE ({hoje_str}, PARCIAL)": [hoje_str] if DIA_HOJE_PARCIAL in dias_com_dado else [],
    }

    print("\n" + "=" * 140)
    print("AGREGADOS")
    print("=" * 140)
    cab2 = (f"{'grupo':<38}{'variante':<12}{'n':>6}{'win%':>8}{'ganho_med':>11}{'perda_med':>11}"
            f"{'BE emp.':>9}{'IC95 win%':>18}{'veredito':>12}{'liq. total':>13}"
            f"{'liq/preg':>10}{'preg +':>7}{'preg -':>7}{'preg cens.':>11}{'pregoes':>9}")
    print(cab2)
    print("-" * len(cab2))
    for nome_grupo, lista_dias in grupos.items():
        if not lista_dias:
            continue
        for v in VARIANTES:
            cels = [por_dia_variante[(d, v)] for d in lista_dias if (d, v) in por_dia_variante]
            if not cels:
                continue
            r = _resumir(cels)
            ic_txt = f"[{r['lo']:.2f};{r['hi']:.2f}]"
            print(f"{nome_grupo:<38}{v:<12}{r['n']:>6}{r['win']:>7.2f}%{r['ganho_medio']:>11.2f}"
                  f"{r['perda_media']:>11.2f}{r['be_emp']:>8.2f}%"
                  f"{ic_txt:>18}{r['veredito']:>12}"
                  f"{r['liquido_total']:>13.2f}{r['liq_preg']:>10.2f}{r['n_pos']:>7}{r['n_neg']:>7}"
                  f"{r['n_cens']:>11}{r['n_dias']:>9}")
        print("-" * len(cab2))

    print("\nLEITURA:")
    print(" - BE emp. = perda_media/(ganho_medio+perda_media), o nulo EMPIRICO do proprio")
    print("   grupo/variante (nao o nominal T2/S16=88,9%).")
    print(" - IC95 win% e' Wilson sobre n_ganhos/n pooled DENTRO de cada grupo.")
    print(" - veredito POSITIVA exige IC95 inteiro ACIMA do BE empirico. 'indefinido' = atravessa.")
    print(" - 'preg cens.' = pregoes com >=1 recusa de capital (portao de R$375, nao a geometria).")
    print(f" - limiar de regime = {LIMIAR_REGIME_TICKS:.2f} ticks, REAPROVEITADO de "
          f"wdof1_combo_t3_is_oos_real_2026_09_11.py, calibrado SO' em 2026-02-27..2026-07-06.")
    print(f" - {hoje_str} e' dado PARCIAL (sessao em andamento no momento da medicao) -- "
          f"reportado tambem separado, nao so' dentro do pool de 10.")
    print(" - 10 pregoes E' POUCO: isto e' checagem de janela recente, NAO um novo veredito.")
    print("   O veredito de amostra grande (132 pregoes) ja esta feito: combo_T3 NEGATIVO no IS,")
    print("   INDEFINIDO-mas-negativo no OOS (liquido -R$1.629,50 em 44 pregoes).")


if __name__ == "__main__":
    main()
