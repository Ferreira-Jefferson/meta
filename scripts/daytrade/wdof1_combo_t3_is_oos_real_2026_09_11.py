"""WDO F1 (grid maker puro): teste IS/OOS REAL de `combo_T3` (filtro de
regime `fade_off/20min` + alvo maior `profit_ticks=3`, mantendo `stop_ticks=
16` e a fila calibrada 438/489 sem prazo de saida) sobre TODO o historico de
tick REAL disponivel do WDO@, para substituir o teste pooled de 19 pregoes
(`wdof1_regime_alvo_combinado_2026_09_11.py`, +R$169,50 liquido, IC95% de
Wilson do win% ainda atravessando o breakeven empirico -- estatisticamente
INDEFINIDO). Aquele teste tinha vies de selecao adicional: a variante foi
ESCOLHIDA depois de ja funcionar nos 2 primeiros dias do proprio conjunto
testado (2026-09-10/11) -- nao um teste independente.

DE ONDE VEM O DADO -- descoberta desta rodada, nao presumida:
`data/raw_ticks/WDO_A_.parquet` e' o parquet CANONICO de tick continuo do
WDO@, regenerado em 2026-09-07 (ver memoria `wdo-tick-canonico-regenerado`)
depois que um bug de fuso comeu 19,3% dos minutos de pregao em silencio por
meses. A versao atual (pos-reparo) cobre 130 pregoes REAIS, 2026-02-27 a
2026-09-04, com 99,5% dos minutos de pregao presentes (residuo honesto:
2026-08-03/08-04 ausentes -- retencao real do terminal, nao recuperavel).
Mais 2 pregoes (2026-09-08, 2026-09-09) ja estavam cacheados em barra
degenerada por `wdof1_regime_alvo_combinado_2026_09_11.py`, na mesma janela
de sessao (12:00-21:30 UTC) -- reaproveitados aqui em vez de reconvertidos.
Total: 132 pregoes reais, 2026-02-27 .. 2026-09-09 -- MUITO mais que os 19
do teste pooled anterior, e mais que os "2-3 meses" pedidos (e' ~6,5 meses).

2026-09-10 e 2026-09-11 ficam de FORA dos dois periodos de proposito: foram
os 2 dias que motivaram a escolha da variante combo_T3 (ver a docstring de
`wdof1_regime_alvo_combinado_2026_09_11.py`), entao nao servem como OOS para
ELA -- seria o mesmo vies de selecao que este script existe pra corrigir.

CORTE IS/OOS -- cronologico, limpo, SEM sobreposicao, 2/3-1/3 do total
disponivel (nao arbitrario: e' o ponto que da IS bem acima do minimo pedido
de 2-3 meses e deixa o OOS com massa suficiente para um IC de Wilson que nao
seja so' ruido):

    IS  = 2026-02-27 .. 2026-07-06  (88 pregoes, ~4,3 meses corridos)
    OOS = 2026-07-07 .. 2026-09-09  (44 pregoes, ~2,1 meses corridos)

RECALIBRACAO DO LIMIAR DE REGIME (fade_off/20min): percentil 70 de |retorno
em 20min| (M1, construido por resample do proprio tick para close-por-minuto
-- ver `_m1_close_do_dia`), calculado SOMENTE nos 88 pregoes do IS acima.
NUNCA ve' os 44 pregoes do OOS -- diferente do teste pooled anterior, cujo
limiar (8,11 ticks) foi calibrado em 2026-06-15..2026-08-14, uma janela que
SOBREPUNHA boa parte dos 19 dias daquele teste.

MOTOR: o MESMO de producao, sem relaxar nada -- `config_for`/`profile_for`,
fila calibrada de `backtest.intraday.fidelidade` (438/489), alvo fatiado
real (`fatiar_saida_alvo=True`, sem prazo -- `EXIT_TTL_BARS_SEM_PRAZO`),
capital REAL R$375/pregao, NUNCA reposto entre pregoes -- cada pregao e' uma
observacao independente (mesmo padrao de todos os scripts WDO F1 anteriores,
`get_daytrade_robot("wdo_grid_reload_maker")` fornece os kwargs de producao).

REUTILIZACAO DE CODIGO (pedido explicito): `RegimeLookup`, `RegimeReloadVariant`,
`variante_class` e `ic_wilson` sao IMPORTADOS de
`wdof1_regime_medio_prazo_2026_09_11.py`, nao reescritos. So' a construcao do
regime (`_construir_regime`) e' local, porque ela depende da JANELA de
calibracao e da LISTA de dias -- que sao diferentes em CADA script (mesmo
padrao que `wdof1_regime_alvo_combinado_2026_09_11.py` ja usa, pela mesma
razao, documentada na docstring dele)."""
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
MARGEM_CRUA_BRL = 150.0  # margem WDO@ x1 contrato -- piso de SOBREVIVENCIA (CLAUDE.md)

TICK_PARQUET_LOCAL = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)

ESCALA_MIN = 20
PERCENTIL_LIMIAR = 70.0

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
    """Converte, numa UNICA passada pelo parquet canonico local (21,5M ticks),
    os pregoes que ainda nao tem barra degenerada cacheada em `BARS_DIR`.
    Nao chama MT5 -- o dado ja esta local e verificado (canonico, regenerado
    2026-09-07). Roda no processo PRINCIPAL, sequencial: e' I/O + um groupby,
    nao vale paralelizar (os workers do backtest, que sao a parte cara, ja
    sao paralelos)."""
    faltando = {d for d in dias if not _bars_path(d).exists()}
    if not faltando:
        print(f"[cache] {len(dias)} pregoes ja cacheados em barra degenerada -- nada a converter.")
        return
    print(f"[cache] convertendo {len(faltando)} pregoes de tick local -> barra "
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
    print(f"[cache] {convertidos}/{len(faltando)} pregoes convertidos e gravados em {BARS_DIR}", flush=True)
    ainda_faltando = sorted(d for d in faltando if not _bars_path(d).exists())
    if ainda_faltando:
        print(f"[cache] AVISO -- sem tick local para: {ainda_faltando} (seguem de fora do teste)")


def _m1_close_do_dia(dia: date) -> pd.Series | None:
    """Close-por-minuto do pregao, construido por resample do PROPRIO tick/
    barra degenerada cacheada (coluna `close`, 1 linha por negocio) --
    equivalente ao M1 real (mesmo alinhamento de minuto, mesma fonte
    canonica), sem precisar de uma segunda chamada ao MT5."""
    caminho = _bars_path(dia)
    if not caminho.exists():
        return None
    bars = pd.read_parquet(caminho)
    if bars.empty:
        return None
    s = bars["close"].resample("1min").last().dropna()
    return s if not s.empty else None


def construir_regime(dias_calibracao: list[date], dias_todos: list[date], tick_size: float):
    """Percentil `PERCENTIL_LIMIAR` de |retorno em `ESCALA_MIN` min| calculado
    SOMENTE em `dias_calibracao` (o IS) -- devolve (limiar, {dia: serie
    'up'/'down'/'neutral' indexada no timestamp CLOSE-SAFE = open+1min})."""
    partes = []
    for d in dias_todos:
        s = _m1_close_do_dia(d)
        if s is None:
            continue
        partes.append(pd.DataFrame({"close": s, "dia": d}))
    m1 = pd.concat(partes).sort_index()

    ret = m1.groupby("dia")["close"].transform(lambda s: s.diff(ESCALA_MIN)) / tick_size
    calib_mask = m1["dia"].isin(set(dias_calibracao))
    amostra = ret[calib_mask].dropna().abs()
    if amostra.empty:
        raise SystemExit("[regime] amostra de calibracao vazia -- sem M1 no periodo IS?")
    limiar = float(amostra.quantile(PERCENTIL_LIMIAR / 100.0))

    series: dict[date, pd.Series] = {}
    for d in dias_todos:
        sub = m1[m1["dia"] == d]
        if sub.empty:
            continue
        ts_close_safe = sub.index + pd.Timedelta(minutes=1)
        ret_dia = ret.loc[sub.index]
        rotulo = pd.Series("neutral", index=ts_close_safe)
        rotulo[ret_dia.values > limiar] = "up"
        rotulo[ret_dia.values < -limiar] = "down"
        series[d] = rotulo.sort_index()
    return limiar, series, len(amostra)


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


def main() -> None:
    from core.instruments import economics_for

    t_inicio = time.perf_counter()

    if not TICK_PARQUET_LOCAL.exists():
        raise SystemExit(f"[erro] nao encontrei {TICK_PARQUET_LOCAL}")

    print(f"[dado] carregando lista de pregoes de {TICK_PARQUET_LOCAL} ...", flush=True)
    ticks_meta = pd.read_parquet(TICK_PARQUET_LOCAL, columns=["last"])
    dias_locais = sorted(set(ticks_meta.index.date))
    del ticks_meta
    dias_extras = [d for d in (date(2026, 9, 8), date(2026, 9, 9))
                   if _bars_path(d).exists()]
    dias_todos = sorted(set(dias_locais) | set(dias_extras))
    print(f"[dado] {len(dias_locais)} pregoes no parquet canonico local "
          f"({dias_locais[0]} .. {dias_locais[-1]}) + {len(dias_extras)} pregoes "
          f"ja cacheados ({[d.isoformat() for d in dias_extras]}) = "
          f"{len(dias_todos)} pregoes reais totais.\n", flush=True)

    n = len(dias_todos)
    corte = round(n * 2 / 3)
    IS_DIAS = dias_todos[:corte]
    OOS_DIAS = dias_todos[corte:]
    print(f"[split] IS  = {IS_DIAS[0]} .. {IS_DIAS[-1]}  ({len(IS_DIAS)} pregoes)")
    print(f"[split] OOS = {OOS_DIAS[0]} .. {OOS_DIAS[-1]}  ({len(OOS_DIAS)} pregoes)")
    print("[split] 2026-09-10 e 2026-09-11 EXCLUIDOS dos dois -- ja usados na "
          "escolha da variante combo_T3, nao servem como OOS para ela.\n", flush=True)

    preparar_cache_de_barras(dias_todos)

    tick_size = economics_for("WDO@").price_tick_size
    limiar, series, n_amostra_calib = construir_regime(IS_DIAS, dias_todos, tick_size)
    print(f"[regime] limiar fade_off/{ESCALA_MIN}min = {limiar:.2f} ticks "
          f"(percentil {PERCENTIL_LIMIAR:.0f}, calibrado em {n_amostra_calib} "
          f"observacoes M1 SOMENTE do IS, {IS_DIAS[0]} .. {IS_DIAS[-1]} -- "
          f"nenhum dia do OOS entra nesta janela)\n", flush=True)

    import wdof1_regime_medio_prazo_2026_09_11 as regime_mod

    specs = []
    dias_com_dado = [d for d in dias_todos if d in series]
    faltando_regime = sorted(set(dias_todos) - set(dias_com_dado))
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
    dias_str = {"IS": [d.isoformat() for d in IS_DIAS if d in series],
                "OOS": [d.isoformat() for d in OOS_DIAS if d in series]}

    resumo = {}
    for periodo, lista_dias in dias_str.items():
        for v in VARIANTES:
            cels = [por_dia_variante[(d, v)] for d in lista_dias if (d, v) in por_dia_variante]
            resumo[(periodo, v)] = _resumir(cels)

    print("=" * 130)
    print("RESULTADO IS x OOS -- combo_T3 (fade_off/20min + T3/S16) vs baseline T2/S16")
    print("=" * 130)
    cab = (f"{'periodo':<8}{'variante':<12}{'n':>6}{'win%':>8}{'ganho_med':>11}{'perda_med':>11}"
           f"{'BE emp.':>9}{'IC95 win%':>18}{'veredito':>12}{'liq. total':>13}"
           f"{'liq/preg':>11}{'preg +':>8}{'preg -':>8}{'preg cens.':>11}{'pregoes':>9}")
    print(cab)
    print("-" * len(cab))
    for periodo in ("IS", "OOS"):
        for v in VARIANTES:
            r = resumo[(periodo, v)]
            ic_txt = f"[{r['lo']:.2f};{r['hi']:.2f}]"
            print(f"{periodo:<8}{v:<12}{r['n']:>6}{r['win']:>7.2f}%{r['ganho_medio']:>11.2f}"
                  f"{r['perda_media']:>11.2f}{r['be_emp']:>8.2f}%"
                  f"{ic_txt:>18}{r['veredito']:>12}"
                  f"{r['liquido_total']:>13.2f}{r['liq_preg']:>11.2f}{r['n_pos']:>8}{r['n_neg']:>8}"
                  f"{r['n_cens']:>11}{r['n_dias']:>9}")
        print("-" * len(cab))

    print("\nLEITURA:")
    print(" - BE emp. = perda_media/(ganho_medio+perda_media), o nulo EMPIRICO do proprio")
    print("   periodo/variante (nao o nominal T2/S16=88,9%).")
    print(" - IC95 win% e' Wilson sobre n_ganhos/n pooled DENTRO de cada periodo.")
    print(" - veredito POSITIVA exige IC95 inteiro ACIMA do BE empirico -- so' assim e'")
    print("   estatisticamente diferente do nulo. 'indefinido' = atravessa. 'NEGATIVA' = IC abaixo.")
    print(" - 'preg cens.' = pregoes com >=1 recusa de capital (motor parou de operar por falta")
    print("   de caixa -- mede o portao de R$375, nao a geometria; ver CLAUDE.md, 'piso de capital').")
    print(f" - limiar de regime = {limiar:.2f} ticks, calibrado SOMENTE no IS ({IS_DIAS[0]} .. "
          f"{IS_DIAS[-1]}) -- nunca visto o OOS.")
    print(f" - 2026-09-10/09-11 (os 2 dias que motivaram escolher combo_T3) NAO entram em IS nem OOS.")


if __name__ == "__main__":
    main()
