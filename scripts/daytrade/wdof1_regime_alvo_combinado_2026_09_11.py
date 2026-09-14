"""WDO F1 (grid maker puro): COMBINA os dois achados de 2026-09-11 (filtro
de regime `fade_off/20min` + alvo maior T3/T4) e AMPLIA a amostra de 2 para
ate' 19 pregoes reais de tick.

CONTEXTO -- por que este script existe
---------------------------------------
Duas rodadas do mesmo dia mediram, cada uma isolada, sobre o MESMO motor de
producao (fila calibrada `backtest.intraday.fidelidade`, sem prazo de
saida, `config_for`/`profile_for`, capital REAL R$375, T2/S16 baseline):

  1. `wdof1_regime_medio_prazo_2026_09_11.py` -- filtro `fade_off/20min`
     (suspende so' o lado que fadaria uma tendencia de escala media): melhora
     os DOIS dias (09-10: -R$256,50 -> -R$86,50; 09-11: -R$240,00 ->
     +R$246,00), 0 recusas de capital nos dois.
  2. `wdof1_saida_assimetrica_2026_09_11.py` -- alvo maior T3/S16 e T4/S16
     (mantendo S16): unicas familias (alem da 1) com QUALQUER dia positivo
     (T3: 09-10 -R$233,00 / 09-11 +R$160,50; T4: 09-10 -R$257,00 / 09-11
     +R$384,00).

Nenhuma das duas isoladas prova edge com 2 dias. Este script faz DUAS
coisas, reaproveitando as classes ja escritas nos dois arquivos acima (nao
reescreve `RegimeReloadVariant`/`variante_class`/`RegimeLookup`/`ic_wilson`
-- importa do modulo 1):

  PARTE 1 -- COMBINA: filtro fade_off/20min + T3/S16 E + T4/S16 (o filtro
  ataca a causa da PERDA errada -- fade contra tendencia forte -- o alvo
  maior ataca o GANHO bruto por trade, que precisa passar de R$5 brutos
  para sobreviver a corretagem de R$0,50 e ao breakeven empirico).

  PARTE 2 -- AMPLIA: mais 17 pregoes reais de tick (2026-08-17 .. 2026-09-09,
  uteis, excluindo o feriado de 07/09 -- Independencia -- que o terminal
  devolveu 0 ticks) somados aos 2 originais (09-10, 09-11) = 19 pregoes.
  `WDO@` no MT5 e' o simbolo CONTINUO "Por Vencimento -- Ajuste
  Proporcional": a mesma chamada de tick historico ja devolve a serie
  correta por tras (nao e' preciso escolher WDOU26/WDOV26 na mao por
  pregao).

CALIBRACAO DO REGIME, RECALCULADA para nao vazar para os dias novos --
diferenca deliberada do script 1: la' o periodo de calibracao (2026-07-13 a
2026-09-09) INCLUiA quase todos os dias que este script agora testa, o que
seria a propria contaminacao que o script 1 evitava so' para os 2 dias
originais. Aqui o limiar do percentil 70 de |retorno| em 20min e'
recalibrado numa janela ANTERIOR a TODOS os 19 dias de teste
(2026-06-01 .. 2026-08-14), fixa, nunca vista pelos dias avaliados.

HONESTIDADE DE METODO (repetida do pedido do dono, para nao se perder no
relatorio): esta amostra de 19 pregoes e' IS (in-sample), NAO OOS -- a
variante testada aqui (fade_off/20min + T3/T4) foi ESCOLHIDA depois de ja
ter visto ela funcionar nos 2 primeiros dias (vies de selecao de variante).
Se ela passar aqui, o proximo passo correto antes de qualquer producao real
e' um periodo OOS futuro NUNCA visto -- nao mais dado do passado.

MOTOR: o MESMO de producao, capital REAL R$375/pregao, NUNCA reposto entre
pregoes -- cada pregao e' uma observacao independente. NENHUM parametro de
realismo relaxado (fila calibrada, sem prazo, fatia real de saida)."""
from __future__ import annotations

import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timezone, timedelta
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0

BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)

# Calibracao do regime: janela FIXA, anterior a TODOS os dias de teste
# abaixo (ver a nota de metodo na docstring do modulo -- diferente da janela
# do script 1, que so' precisava ficar antes de 2 dias).
CALIBRACAO_INICIO = pd.Timestamp("2026-06-15T00:00:00Z")
CALIBRACAO_FIM = pd.Timestamp("2026-08-14T23:59:59Z")
ESCALA_MIN = 20
PERCENTIL_LIMIAR = 70.0

# 19 pregoes: os 2 originais + 17 novos (2026-08-17 .. 2026-09-09, uteis).
# 2026-09-07 (segunda) fica de fora -- feriado de Independencia, terminal
# devolveu 0 ticks (confirmado por sondagem direta ao MT5 antes de rodar
# este script).
DIAS_TESTE = [
    "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
    "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28",
    "2026-08-31",
    "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
    "2026-09-08", "2026-09-09",
    "2026-09-10", "2026-09-11",
]

VARIANTES = ["baseline", "fade_off", "T3", "T4", "combo_T3", "combo_T4"]


def _limite_servidor(instant_utc):
    from core.b3_session import utc_to_server_wall_clock
    instant = pd.Timestamp(instant_utc).to_pydatetime()
    return utc_to_server_wall_clock(instant).replace(tzinfo=timezone.utc)


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


def _bars_path(dia_str: str) -> Path:
    # Os 2 dias originais ja foram cacheados por
    # `wdof1_saida_assimetrica_2026_09_11.py` sob o nome "WDOV26_*" -- reusa
    # em vez de baixar de novo (mesma janela de sessao, 12:00-21:30 UTC).
    legado = BARS_DIR / f"WDOV26_{dia_str}.parquet"
    if legado.exists():
        return legado
    return BARS_DIR / f"WDO_at_{dia_str}.parquet"


def _preparar_bars(dia_str: str) -> str:
    """Baixa tick real (se ainda nao estiver em cache) e grava as barras
    degeneradas em parquet. Roda no processo PRINCIPAL, sequencial -- so'
    dezessete pregoes novos, cada um poucos segundos; nao vale a
    complexidade de paralelizar chamadas ao MESMO terminal MT5 aqui (os
    workers do backtest, que sao a parte cara, ja' sao paralelos)."""
    from market_data_intraday.mt5_ticks_source import fetch_ticks_range
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars

    caminho = _bars_path(dia_str)
    if caminho.exists():
        return f"{dia_str}: cache ({caminho.name})"

    dia_ts = pd.Timestamp(dia_str, tz="UTC")
    inicio = dia_ts + pd.Timedelta(hours=12)
    fim = dia_ts + pd.Timedelta(hours=21, minutes=30)
    erros = []
    ticks = fetch_ticks_range(
        SYMBOL, _limite_servidor(inicio.to_pydatetime()), _limite_servidor(fim.to_pydatetime()),
        on_error=lambda k, e: erros.append((k, str(e))),
    )
    if ticks.empty:
        return f"{dia_str}: SEM TICKS ({erros})"
    bars = ticks_to_degenerate_bars(ticks)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(caminho)
    return f"{dia_str}: baixado, {len(bars)} barras -> {caminho.name}"


# --------------------------------------------------------------- regime
def construir_regime_20min(m1: pd.DataFrame, tick_size: float) -> tuple[float, dict]:
    """Mesma mecanica de `wdof1_regime_medio_prazo_2026_09_11.construir_
    regimes`, parametrizada para a janela de calibracao e a lista de dias
    DESTE script (ver a nota de metodo na docstring do modulo -- import
    direto da funcao original vazaria os globais do outro script, que
    apontam para so' 2 dias e outra janela de calibracao)."""
    m1 = m1.sort_index().copy()
    m1["dia"] = m1.index.date
    ret = m1.groupby("dia")["close"].transform(lambda s: s.diff(ESCALA_MIN)) / tick_size
    calib_mask = (m1.index >= CALIBRACAO_INICIO) & (m1.index <= CALIBRACAO_FIM)
    amostra = ret[calib_mask].dropna().abs()
    limiar = float(amostra.quantile(PERCENTIL_LIMIAR / 100.0))

    series: dict[str, pd.Series] = {}
    for dia_str in DIAS_TESTE:
        dia = pd.Timestamp(dia_str).date()
        sub = m1[m1["dia"] == dia]
        if sub.empty:
            continue
        ts_close_safe = sub.index + pd.Timedelta(minutes=1)
        ret_dia = ret.loc[sub.index]
        rotulo = pd.Series("neutral", index=ts_close_safe)
        rotulo[ret_dia.values > limiar] = "up"
        rotulo[ret_dia.values < -limiar] = "down"
        series[dia_str] = rotulo.sort_index()
    return limiar, series


# --------------------------------------------------------------- worker
def _roda_celula(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import inspect
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot
    import wdof1_regime_medio_prazo_2026_09_11 as regime_mod

    dia_str = spec["dia"]
    variante = spec["variante"]
    caminho = _bars_path(dia_str)
    bars = pd.read_parquet(caminho)
    if bars.empty:
        return {"spec": spec, "erro": "bars vazio"}

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    params = [p for p in inspect.signature(WdoGridReloadMaker.__init__).parameters if p != "self"]
    kwargs = {p: getattr(robo, p) for p in params}

    lookup = spec.get("regime_lookup")

    if variante == "baseline":
        strat = WdoGridReloadMaker(**kwargs)
    elif variante == "fade_off":
        Cls = regime_mod.variante_class(WdoGridReloadMaker)
        strat = Cls(regime_lookup=lookup, modo="fade_off", **kwargs)
    elif variante in ("T3", "T4"):
        alvo = 3 if variante == "T3" else 4
        kwargs2 = dict(kwargs)
        kwargs2["profit_ticks"] = alvo
        strat = WdoGridReloadMaker(**kwargs2)
    elif variante in ("combo_T3", "combo_T4"):
        alvo = 3 if variante == "combo_T3" else 4
        kwargs2 = dict(kwargs)
        kwargs2["profit_ticks"] = alvo
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
        "spec": {"dia": dia_str, "variante": variante},
        "n": len(trades),
        "n_ganhos": len(ganhos),
        "n_perdas": len(perdas),
        "soma_ganhos": sum(ganhos),
        "soma_perdas": sum(perdas),  # negativo
        "pnl": sum(t.pnl_brl for t in trades),
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "recusas_capital": _contador["recusas"],
    }


def main() -> None:
    from market_data_intraday.mt5_source import fetch_m1_range
    from core.instruments import economics_for
    import wdof1_regime_medio_prazo_2026_09_11 as regime_mod  # reaproveita as classes

    t_inicio = time.perf_counter()

    # ---- Parte 2a: baixar/cachear barras de tick real dos 19 pregoes ----
    print(f"[combinado] preparando barras de {len(DIAS_TESTE)} pregoes "
          f"(cache em {BARS_DIR}) ...", flush=True)
    for dia_str in DIAS_TESTE:
        print(f"  {_preparar_bars(dia_str)}", flush=True)

    dias_com_dado = [d for d in DIAS_TESTE if _bars_path(d).exists() and
                      pd.read_parquet(_bars_path(d)).shape[0] > 0]
    faltando = [d for d in DIAS_TESTE if d not in dias_com_dado]
    if faltando:
        print(f"[combinado] AVISO -- sem dado para: {faltando} (seguem de fora)")

    # ---- Parte 1b: calibrar o regime numa janela ANTERIOR a TODOS os dias ----
    # `copy_rates_range` deste terminal recusa ("Invalid params") pedidos
    # M1 acima de ~28.000 barras (medido por bisseccao: 28.287 OK, qualquer
    # coisa a mais falha) -- nao documentado, e' um teto de HISTORICO
    # carregado no terminal, nao do pacote MetaTrader5. Calibracao (~2 meses)
    # e sinal (~25 dias) juntos passariam do teto, entao os dois vem em
    # chamadas SEPARADAS e sao concatenados aqui.
    print(f"\n[combinado] baixando M1 para calibracao do regime "
          f"({CALIBRACAO_INICIO.date()} .. {CALIBRACAO_FIM.date()}, janela "
          f"fixa e ANTERIOR a todo dia de teste) ...", flush=True)
    erros_calib, erros_sinal = [], []
    m1_calib = fetch_m1_range(
        SYMBOL, _limite_servidor(CALIBRACAO_INICIO.to_pydatetime()),
        _limite_servidor(CALIBRACAO_FIM.to_pydatetime()),
        on_error=lambda k, e: erros_calib.append((k, str(e))),
    )
    print(f"[combinado] baixando M1 do sinal ({dias_com_dado[0]} .. "
          f"{dias_com_dado[-1]}) ...", flush=True)
    m1_sinal = fetch_m1_range(
        SYMBOL, _limite_servidor(pd.Timestamp(dias_com_dado[0] + "T00:00:00Z").to_pydatetime()),
        _limite_servidor(pd.Timestamp(dias_com_dado[-1] + "T23:59:59Z").to_pydatetime()),
        on_error=lambda k, e: erros_sinal.append((k, str(e))),
    )
    if m1_calib.empty or m1_sinal.empty:
        raise SystemExit(f"[combinado] MT5 nao devolveu M1 -- terminal fora do ar? "
                          f"erros_calib={erros_calib} erros_sinal={erros_sinal}")
    m1 = pd.concat([m1_calib, m1_sinal]).sort_index()
    m1 = m1[~m1.index.duplicated(keep="first")]
    tick_size = economics_for("WDO@").price_tick_size
    limiar, series = construir_regime_20min(m1, tick_size)
    print(f"[combinado] limiar fade_off/{ESCALA_MIN}min = {limiar:.2f} ticks "
          f"(percentil {PERCENTIL_LIMIAR:.0f}, calibrado em "
          f"{((m1.index >= CALIBRACAO_INICIO) & (m1.index <= CALIBRACAO_FIM)).sum()} "
          f"barras M1, {CALIBRACAO_INICIO.date()}..{CALIBRACAO_FIM.date()} -- "
          f"NENHUM dia de teste entra nesta janela)\n", flush=True)

    # ---- specs ----
    specs = []
    for dia_str in dias_com_dado:
        lookup = regime_mod.RegimeLookup(series.get(dia_str))
        for variante in VARIANTES:
            specs.append({"dia": dia_str, "variante": variante,
                          "regime_lookup": lookup if "fade" in variante or "combo" in variante else None})

    print(f"[combinado] {len(specs)} celulas ({len(VARIANTES)} variantes x "
          f"{len(dias_com_dado)} pregoes), motor de producao, capital "
          f"R${CAPITAL_REAL_BRL:.0f}/pregao, fila calibrada, sem prazo\n", flush=True)

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

    print(f"\n[combinado] {len(resultados)} celulas em "
          f"{(time.perf_counter()-t_inicio)/60:.1f} min\n", flush=True)

    # ---------------------------------------------------------- agregacao
    print("=" * 100)
    print("TABELA POR PREGAO (liquido R$, por variante)")
    print("=" * 100)
    cab = f"{'dia':<12}" + "".join(f"{v:>12}" for v in VARIANTES)
    print(cab)
    por_dia_variante = {(r["spec"]["dia"], r["spec"]["variante"]): r
                          for r in resultados if "erro" not in r}
    for dia_str in dias_com_dado:
        linha = f"{dia_str:<12}"
        for v in VARIANTES:
            r = por_dia_variante.get((dia_str, v))
            linha += f"{r['pnl']:>12.2f}" if r else f"{'--':>12}"
        print(linha)

    print("\n" + "=" * 130)
    print(f"TABELA AGREGADA -- {len(dias_com_dado)} pregoes pooled, TODOS os trades num unico conjunto por variante")
    print("=" * 130)
    cab2 = (f"{'variante':<12}{'n':>6}{'win%':>8}{'ganho_med':>11}{'perda_med':>11}"
            f"{'BE emp.':>9}{'IC95 win%':>18}{'veredito':>12}{'liq. total':>13}"
            f"{'liq/preg':>11}{'preg +':>8}{'preg -':>8}{'preg cens.':>11}")
    print(cab2)
    print("-" * len(cab2))

    resumo = {}
    for v in VARIANTES:
        cels = [r for (d, vv), r in por_dia_variante.items() if vv == v]
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
        resumo[v] = dict(n=n, win=win, ganho_medio=ganho_medio, perda_media=perda_media,
                          be_emp=be_emp, lo=lo, hi=hi, veredito=veredito,
                          liquido_total=liquido_total, liq_preg=liq_preg,
                          n_pos=n_pos, n_neg=n_neg, n_cens=n_cens, n_dias=n_dias)
        print(f"{v:<12}{n:>6}{win:>7.2f}%{ganho_medio:>11.2f}{perda_media:>11.2f}"
              f"{be_emp:>8.2f}%{f'[{lo:.2f};{hi:.2f}]':>18}{veredito:>12}"
              f"{liquido_total:>13.2f}{liq_preg:>11.2f}{n_pos:>8}{n_neg:>8}{n_cens:>11}")

    print("\nLEITURA:")
    print(" - BE emp. = perda_media/(ganho_medio+perda_media), o nulo EMPIRICO")
    print("   da PROPRIA amostra pooled (nao o nominal T2/S16=88,9%).")
    print(" - IC95 win% e' Wilson sobre n_ganhos/n pooled de TODOS os 19 pregoes.")
    print(" - veredito POSITIVA exige IC95 inteiro ACIMA do BE empirico -- so' assim")
    print("   e' estatisticamente diferente do nulo. 'indefinido' = atravessa.")
    print(" - 'preg cens.' = pregoes com >=1 recusa de capital (janela onde o motor")
    print("   parou de operar por falta de caixa -- mede restricao, nao geometria).")
    print("\nAVISO DE METODO (repetido do pedido do dono): esta e' uma amostra IS de")
    print("19 pregoes, NAO OOS -- fade_off/20min e T3/T4 foram escolhidos DEPOIS de")
    print("ja terem funcionado nos 2 primeiros dias (vies de selecao de variante).")
    print("Se alguma linha aqui vier POSITIVA, o proximo passo antes de producao")
    print("real e' um periodo OOS FUTURO nunca visto -- nunca mais dado do passado.")


if __name__ == "__main__":
    main()
