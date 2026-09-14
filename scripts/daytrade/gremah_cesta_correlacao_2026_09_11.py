"""EXPERIMENTO (nao mexe em src/) -- "Cesta Gremah de baixa correlacao".

Hipotese do dono (2026-09-11): rodar `Gremah` em PMAM3 + 2 dos 8 simbolos ja
calibrados individualmente (BMGB4, KLBN3, DASA3, GRND3, PCAR3, LPSB3, CSAN3,
KLBN4), escolhidos pela MENOR correlacao de P&L DIARIO com a PMAM3 (nao pelo
maior lucro isolado), cada instancia com CAIXA PROPRIO (`capital_minimo_brl`),
SEM nenhuma transferencia de capital entre instancias. Medir o MaxDD da SOMA
dos tres caixas contra 3x o MaxDD de PMAM3 sozinha.

Racional: PMAM3 ja teve o proprio edge amassado quando o preco colapsou
(R$4,53 -> R$0,13 dentro da janela de calibracao, ver
`pmam3_colapso_de_preco_2026_08_26` na memoria do projeto) -- o robo fica
refem do regime de preco de UM papel so'. Diversificar com simbolos JA
validados isoladamente ataca esse risco de concentracao sem reintroduzir
geometria nao calibrada (diferente do universo de 138 ativos, refutado, que
transplantou geometria congelada sem calibrar -- 0/118, abaixo do p05 do
acaso).

## Metodo

1. TESTE PEQUENO PRIMEIRO (`--smoke`): roda os 9 simbolos numa janela de 4
   semanas (2025-12-16..2026-01-13) so' para confirmar que o pipeline nao
   quebra e produz numero plausivel, antes de gastar tempo na janela cheia.
2. JANELA COMUM: max(REGIME_START dos 9) = PMAM3 (2025-12-16) ate' o fim do
   parquet local mais curto (2026-08-21) -- nunca comparar dois simbolos em
   janelas diferentes (ver memoria `feedback_honest_period_comparison`).
   Split IS/OOS por DATA (nao por trade) em 2026-05-01, ~metade do caminho:
   a correlacao e' medida SO' no IS; o par escolhido e' CONFIRMADO no OOS
   (nunca re-selecionado usando dado OOS).
3. Cada simbolo roda com a PROPRIA config de producao (`Gremah(symbol=s)`,
   sem overrides) e o PROPRIO caixa (`capital_minimo_brl` no preco de
   abertura do 1o pregao da janela) -- 9 backtests INDEPENDENTES, motor M1,
   desenho de execucao herdado de `config_for` (entrada/alvo por
   ordem-limite, so' o stop a mercado -- `Gremah.target_fills_as_maker`
   decide, igual producao).
4. Correlacao de P&L diario (soma de `trade.pnl_brl` por data de SAIDA,
   dias sem trade = 0 -- e' sinal legitimo de "nao correlacionou", nao
   censura) entre PMAM3 e cada um dos outros 8, no IS. Os 2 MENORES
   (mais negativos/menos positivos) sao os escolhidos -- NAO os mais
   lucrativos.
5. Cesta = PMAM3 + os 2 escolhidos, cada um com o proprio caixa, SEM
   transferencia nenhuma (a soma e' so' ARITMETICA: como cada instancia e'
   financeiramente independente, a curva de patrimonio combinada e' a SOMA,
   ponto a ponto no tempo, das 3 curvas individuais -- reindexadas para um
   indice de minutos comum, forward-fill dentro do proprio historico de cada
   uma). MaxDD da soma (R$) e' medido com a MESMA formula do resto do
   projeto (`backtest.intraday.report.maxdd_brl`, pico-a-vale) e comparado
   contra 3x o MaxDD (R$) da PMAM3 sozinha, na MESMA janela.
6. Metricas agregadas da cesta (pool dos trades das 3 instancias): liquido
   R$, win% com IC95% de Wilson contra o breakeven EMPIRICO
   (perda_media/(ganho_medio+perda_media)), trades, STOPS, MaxDD %,
   fracao de pregoes positivos, capital total usado, pregoes sem trade
   (nenhuma das 3 operou).
7. Portao de capital: capital total = soma dos 3 `capital_minimo_brl`. Se
   passar de R$3.000, para (INVIAVEL) -- nao continua otimizando.

Paralelismo: `ProcessPoolExecutor` com submit/as_completed (nunca
`pool.map`), streaming por unidade.

Uso:
    python -u scripts/daytrade/gremah_cesta_correlacao_2026_09_11.py --smoke
    python -u scripts/daytrade/gremah_cesta_correlacao_2026_09_11.py
"""
from __future__ import annotations

import contextlib
import io
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

#: PMAM3 primeiro (e' o ativo-ancora da hipotese); os 8 candidatos na ordem
#: que o dono listou na missao.
PMAM3 = "PMAM3"
CANDIDATOS = ("BMGB4", "KLBN3", "DASA3", "GRND3", "PCAR3", "LPSB3", "CSAN3", "KLBN4")
TODOS = (PMAM3,) + CANDIDATOS

#: MESMOS valores de `scripts/daytrade/gremah_baseline_9_simbolos_2026_09_03.py`
#: (duplicados, nao importados -- aquele script nao expoe a tabela como API).
REGIME_START = {
    "PMAM3": "2025-12-16", "KLBN4": "2025-09-02", "CSAN3": "2025-09-22",
    "DASA3": "2025-09-11", "PCAR3": "2025-08-21", "KLBN3": "2025-03-10",
    "GRND3": "2025-09-05", "LPSB3": "2022-12-20", "BMGB4": "2025-06-04",
}

MIN_BARRAS_M1_ACAO = 20
TRADE_TICK_VALUE = 0.01
TRADE_TICK_SIZE = 0.01

# Janela COMUM (ver docstring do modulo -- max(REGIME_START) e' PMAM3, fim do
# parquet mais curto entre os 9 e' 2026-08-21). Split IS/OOS fixo, decidido
# ANTES de olhar qualquer numero (protocolo de sempre do projeto).
JANELA_COMUM_INICIO = "2025-12-16"
JANELA_COMUM_FIM = "2026-08-21"
SPLIT_IS_OOS = "2026-05-01"

# Janela de FUMACA (4 semanas) -- so' para confirmar que o pipeline roda sem
# quebrar antes de gastar tempo na janela cheia (convencao "teste pequeno
# primeiro" do projeto).
SMOKE_INICIO = "2025-12-16"
SMOKE_FIM = "2026-01-13"

ORCAMENTO_CAPITAL_BRL = 3000.0
ORCAMENTO_CAPITAL_DEFESA_BRL = 1000.0

CORRETAGEM_ROUND_TRIP_BRL = 0.0  # perfil atual (Rico, lote inteiro) -- ver profiles.py


def _naive(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """As curvas de equity vem com timestamp tz-aware (UTC, herdado do
    indice de `bars`); o P&L diario (`_pnl_diario`) e' tz-NAIVE (a data ja'
    foi extraida via `.date()` antes de virar string). Comparar os dois sem
    normalizar levanta `TypeError` do pandas -- esta funcao poe tudo no
    mesmo terreno (naive), sempre."""
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return idx


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """IC95% de Wilson para uma proporcao, em PERCENTUAL. `(nan, nan)` se n=0.
    Mesma formula usada em `scripts/daytrade/wdof1_regime_alvo_combinado_2026_09_11.py`."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


def _roda_simbolo(symbol: str, inicio: str, fim: str) -> dict:
    """Roda `Gremah(symbol=symbol)` (config de PRODUCAO, sem overrides) na
    janela [inicio, fim), com o proprio caixa (`capital_minimo_brl` no OPEN
    da 1a barra da janela). Devolve trades (como dicts, picklable) + a curva
    de patrimonio (serie) + metadados de capital/aviso."""
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.lab.gremah import Gremah

    df = load_m1(symbol).sort_index()
    if df.empty:
        raise SystemExit(f"[{symbol}] sem dado M1 local -- nada a rodar")
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_M1_ACAO}
    df = df[[d in completos for d in df.index.date]]

    ini_ts = pd.Timestamp(inicio, tz=df.index.tz)
    fim_ts = pd.Timestamp(fim, tz=df.index.tz)
    bars = df.loc[(df.index >= ini_ts) & (df.index < fim_ts)]
    if bars.empty:
        raise SystemExit(f"[{symbol}] janela [{inicio},{fim}) vazia")

    preco_ref = float(bars.iloc[0]["open"])
    capital = capital_minimo_brl(preco_ref)

    profile = profile_for(symbol)
    strat = Gremah(symbol=symbol)  # config de PRODUCAO -- so' o simbolo
    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    item = linha_de_resultado(symbol, resultado, capital, capital_nocional=False)

    trades_out = [
        dict(exit_date=str(t.exit_ts.date()), pnl_brl=t.pnl_brl,
             exit_reason=str(t.exit_reason.value if hasattr(t.exit_reason, "value") else t.exit_reason))
        for t in resultado.trades
    ]
    equity = resultado.equity_curve
    equity_dict = dict(zip([str(ts) for ts in equity.index], equity.values.tolist())) if equity is not None and not equity.empty else {}

    return dict(
        symbol=symbol, capital=capital, preco_ref=preco_ref,
        liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl, maxdd_pct=item.maxdd_pct,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        capital_final=item.capital_final, aviso=item.aviso,
        trades_detalhe=trades_out, equity=equity_dict,
        fila_calibrada=getattr(resultado, "fila_calibrada", None),
    )


def _roda_lote(symbols: tuple[str, ...], inicio: str, fim: str, rotulo: str) -> dict[str, dict]:
    """Roda uma lista de simbolos em paralelo (ProcessPoolExecutor,
    submit/as_completed), streaming o resultado de cada um assim que
    termina."""
    n_workers = max(1, min(len(symbols), 6, os.cpu_count() or 4))
    print(f"[{rotulo}] {len(symbols)} simbolos, {n_workers} processos, janela [{inicio},{fim})", flush=True)
    out: dict[str, dict] = {}
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_simbolo, s, inicio, fim): s for s in symbols}
        concluidos = 0
        for future in as_completed(futures):
            s = futures[future]
            concluidos += 1
            try:
                r = future.result()
            except Exception as exc:  # nao esconder falha de 1 simbolo
                print(f"[{rotulo}] {s} FALHOU: {exc}", flush=True)
                raise
            out[s] = r
            print(f"[{rotulo}] {concluidos}/{len(symbols)} {s:<6} liquido=R${br(r['liquido_brl'])} "
                  f"MaxDD=R${br(r['maxdd_brl'])} trades={r['trades']} pregoes={r['pregoes']} "
                  f"capital=R${br(r['capital'])} aviso='{r['aviso']}'", flush=True)
    print(f"[{rotulo}] concluido em {time.perf_counter() - t0:.1f}s", flush=True)
    return out


def _pnl_diario(resultado: dict, ini: str | None = None, fim: str | None = None) -> pd.Series:
    """Serie de P&L diario (data -> soma de pnl_brl das saidas naquele dia),
    recortada opcionalmente para [ini, fim)."""
    trades = resultado["trades_detalhe"]
    if not trades:
        return pd.Series(dtype=float)
    df = pd.DataFrame(trades)
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    serie = df.groupby("exit_date")["pnl_brl"].sum()
    if ini is not None:
        serie = serie[serie.index >= pd.Timestamp(ini)]
    if fim is not None:
        serie = serie[serie.index < pd.Timestamp(fim)]
    return serie.sort_index()


def _correlacao(pnl_a: pd.Series, pnl_b: pd.Series, calendario: pd.DatetimeIndex) -> float:
    """Correlacao de Pearson do P&L diario de A e B, alinhados por um
    CALENDARIO comum (uniao das datas em que qualquer um dos 9 simbolos
    operou na janela) -- dia sem trade de um dos dois vira 0.0 (sinal
    legitimo, nao censura). `nan` se um dos dois tiver variancia zero."""
    a = pnl_a.reindex(calendario, fill_value=0.0)
    b = pnl_b.reindex(calendario, fill_value=0.0)
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(a.corr(b))


def _equity_combinada(resultados: list[dict], ini: str, fim: str) -> pd.Series:
    """Soma, ponto a ponto no tempo, as curvas de patrimonio de N instancias
    INDEPENDENTES (sem transferencia de capital -- a soma aritmetica e' o
    caixa combinado de verdade). Reindexa cada curva para a UNIAO dos
    instantes das 3, forward-fill (cada uma mantem o ultimo patrimonio
    conhecido ate a proxima atualizacao propria), NaN residual (antes do
    1o instante daquela instancia dentro da janela) vira o proprio capital
    inicial dela -- nunca 0, que inventaria uma queda que nao existiu."""
    ini_ts = pd.Timestamp(ini)
    fim_ts = pd.Timestamp(fim)
    series = []
    for r in resultados:
        eq = pd.Series(r["equity"], dtype=float)
        if not eq.empty:
            eq.index = _naive(pd.to_datetime(eq.index))
            eq = eq.sort_index()
            eq = eq[(eq.index >= ini_ts) & (eq.index < fim_ts)]
        series.append((r["capital"], eq))
    todos_indices = sorted(set().union(*[set(eq.index) for _, eq in series if not eq.empty]))
    if not todos_indices:
        return pd.Series(dtype=float)
    df = pd.DataFrame(index=pd.DatetimeIndex(todos_indices))
    for i, (capital, eq) in enumerate(series):
        col = eq.reindex(df.index).ffill()
        col = col.fillna(capital)
        df[f"leg_{i}"] = col
    return df.sum(axis=1)


def maxdd_brl(equity_curve: pd.Series) -> float:
    """Mesma formula de `backtest.intraday.report.maxdd_brl` (pico-a-vale,
    R$, sempre >= 0) -- duplicada aqui so' para nao importar um modulo que
    espera objetos do motor (este recebe uma Series pura, ja combinada)."""
    if equity_curve is None or equity_curve.empty:
        return 0.0
    pico = equity_curve.cummax()
    return float((pico - equity_curve).max())


def _metricas_pool(resultados: list[dict], ini: str, fim: str) -> dict:
    """Metricas agregadas da CESTA (pool dos trades das N instancias),
    recortadas para [ini, fim) por data de SAIDA."""
    todos_trades = []
    for r in resultados:
        for t in r["trades_detalhe"]:
            d = pd.Timestamp(t["exit_date"])
            if d >= pd.Timestamp(ini) and d < pd.Timestamp(fim):
                todos_trades.append(t)

    n = len(todos_trades)
    vencedores = [t for t in todos_trades if t["pnl_brl"] > 0]
    perdedores = [t for t in todos_trades if t["pnl_brl"] <= 0]
    stops = [t for t in todos_trades if t["exit_reason"] == "stop"]
    k = len(vencedores)
    win_pct = 100.0 * k / n if n else 0.0
    ic_low, ic_high = ic_wilson(k, n)

    ganho_medio = sum(t["pnl_brl"] for t in vencedores) / len(vencedores) if vencedores else 0.0
    perda_media = abs(sum(t["pnl_brl"] for t in perdedores) / len(perdedores)) if perdedores else 0.0
    breakeven_empirico = (100.0 * perda_media / (ganho_medio + perda_media)
                           if (ganho_medio + perda_media) > 0 else float("nan"))

    liquido = sum(t["pnl_brl"] for t in todos_trades)

    # Pregoes: uniao das datas de sessao de qualquer uma das 3 instancias
    # (a partir da curva de equity de cada uma, que tem 1 ponto por barra
    # processada -- inclui dias sem trade tambem).
    datas_sessao: set = set()
    for r in resultados:
        eq = pd.Series(r["equity"], dtype=float)
        if eq.empty:
            continue
        idx = _naive(pd.to_datetime(eq.index))
        idx = idx[(idx >= pd.Timestamp(ini)) & (idx < pd.Timestamp(fim))]
        datas_sessao |= set(pd.DatetimeIndex(idx).date)

    datas_com_trade = {pd.Timestamp(t["exit_date"]).date() for t in todos_trades}
    pregoes_sem_trade = len(datas_sessao) - len(datas_com_trade)

    pnl_por_dia: dict = {}
    for t in todos_trades:
        d = pd.Timestamp(t["exit_date"]).date()
        pnl_por_dia[d] = pnl_por_dia.get(d, 0.0) + t["pnl_brl"]
    pregoes_positivos = sum(1 for v in pnl_por_dia.values() if v > 0)
    frac_pregoes_positivos = (100.0 * pregoes_positivos / len(datas_sessao)) if datas_sessao else float("nan")

    return dict(
        liquido_brl=liquido, trades=n, stops=len(stops), win_pct=win_pct,
        ic95_low=ic_low, ic95_high=ic_high, breakeven_empirico_pct=breakeven_empirico,
        ganho_medio=ganho_medio, perda_media=perda_media,
        pregoes=len(datas_sessao), pregoes_sem_trade=pregoes_sem_trade,
        frac_pregoes_positivos_pct=frac_pregoes_positivos,
    )


def _imprime_correlacoes(pnl_pmam3: pd.Series, resultados_is: dict[str, dict], calendario: pd.DatetimeIndex) -> list[tuple[str, float]]:
    linhas = []
    for s in CANDIDATOS:
        pnl_s = _pnl_diario(resultados_is[s])
        corr = _correlacao(pnl_pmam3, pnl_s, calendario)
        linhas.append((s, corr))
    linhas.sort(key=lambda x: (math.isnan(x[1]), x[1]))
    print("\ncorrelacao de P&L DIARIO com PMAM3, no IS (menor = mais diversificador):")
    for s, corr in linhas:
        print(f"  {s:<6} corr={corr:+.4f}" if not math.isnan(corr) else f"  {s:<6} corr=NaN (variancia zero)")
    return linhas


def _roda_smoke() -> None:
    print("=" * 90)
    print(f"FASE 0 -- TESTE PEQUENO (fumaca), janela [{SMOKE_INICIO},{SMOKE_FIM}), "
          f"{len(TODOS)} simbolos -- so' confirma que o pipeline roda sem quebrar.")
    print("=" * 90)
    resultados = _roda_lote(TODOS, SMOKE_INICIO, SMOKE_FIM, "smoke")
    for s in TODOS:
        r = resultados[s]
        if r["trades"] == 0:
            print(f"[smoke] AVISO: {s} nao operou nenhuma vez em 4 semanas -- "
                  f"pode faltar dado ou geometria fora de faixa nesta janela curta.")
    print("[smoke] OK -- pipeline nao quebrou em nenhum dos 9 simbolos. Prosseguindo para a janela cheia.\n")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="roda so' a fase de fumaca (4 semanas) e para")
    parser.add_argument("--skip-smoke", action="store_true", help="pula a fase de fumaca (ja rodada antes)")
    args = parser.parse_args()

    if not args.skip_smoke:
        _roda_smoke()
        if args.smoke:
            return

    print("=" * 90)
    print(f"FASE 1 -- IS, janela [{JANELA_COMUM_INICIO},{SPLIT_IS_OOS}), {len(TODOS)} simbolos "
          "(config de PRODUCAO, caixa proprio via capital_minimo_brl).")
    print("=" * 90)
    resultados_is = _roda_lote(TODOS, JANELA_COMUM_INICIO, SPLIT_IS_OOS, "IS")

    pnl_pmam3_is = _pnl_diario(resultados_is[PMAM3])
    calendario_is = pd.DatetimeIndex(sorted(set().union(*[
        set(_pnl_diario(resultados_is[s]).index) | (
            set(_naive(pd.to_datetime(list(resultados_is[s]["equity"].keys()))).normalize())
            if resultados_is[s]["equity"] else set()
        )
        for s in TODOS
    ])))
    ranking = _imprime_correlacoes(pnl_pmam3_is, resultados_is, calendario_is)
    escolhidos = [s for s, _ in ranking[:2]]
    print(f"\nESCOLHIDOS (menor correlacao com PMAM3 no IS): {escolhidos}")

    capital_total = resultados_is[PMAM3]["capital"] + sum(resultados_is[s]["capital"] for s in escolhidos)
    print(f"capital total da cesta (PMAM3 + {escolhidos[0]} + {escolhidos[1]}): R${br(capital_total)}")
    if capital_total > ORCAMENTO_CAPITAL_BRL:
        print(f"\nVEREDITO PRELIMINAR: INVIAVEL -- capital total R${br(capital_total)} "
              f"passa do orcamento de R${br(ORCAMENTO_CAPITAL_BRL)}. Parando (regra do dono: "
              f"nao continuar otimizando fora do orcamento).")
        return

    print("\n" + "=" * 90)
    print(f"FASE 2 -- OOS (confirmacao, simbolos JA escolhidos no IS), janela "
          f"[{SPLIT_IS_OOS},{JANELA_COMUM_FIM}).")
    print("=" * 90)
    simbolos_oos = (PMAM3,) + tuple(escolhidos)
    resultados_oos = _roda_lote(simbolos_oos, SPLIT_IS_OOS, JANELA_COMUM_FIM, "OOS")

    # Confirma a correlacao no OOS tambem (informativo -- NAO re-seleciona).
    pnl_pmam3_oos = _pnl_diario(resultados_oos[PMAM3])
    calendario_oos = pd.DatetimeIndex(sorted(set().union(*[
        set(_pnl_diario(resultados_oos[s]).index) for s in simbolos_oos
    ])))
    print("\ncorrelacao de P&L diario com PMAM3, no OOS (confirmacao, NAO re-seleciona):")
    for s in escolhidos:
        corr_oos = _correlacao(pnl_pmam3_oos, _pnl_diario(resultados_oos[s]), calendario_oos)
        print(f"  {s:<6} corr_OOS={corr_oos:+.4f}" if not math.isnan(corr_oos) else f"  {s:<6} corr_OOS=NaN")

    for rotulo, resultados, ini, fim in (
        ("IS", resultados_is, JANELA_COMUM_INICIO, SPLIT_IS_OOS),
        ("OOS", resultados_oos, SPLIT_IS_OOS, JANELA_COMUM_FIM),
    ):
        print("\n" + "-" * 90)
        print(f"CESTA ({rotulo}): PMAM3 + {escolhidos[0]} + {escolhidos[1]}, janela [{ini},{fim})")
        print("-" * 90)
        pernas = [resultados[PMAM3]] + [resultados[s] for s in escolhidos]
        for r in pernas:
            print(f"  perna {r['symbol']:<6} liquido=R${br(r['liquido_brl'])} MaxDD=R${br(r['maxdd_brl'])} "
                  f"trades={r['trades']} pregoes={r['pregoes']} capital=R${br(r['capital'])} "
                  f"fila_calibrada={r['fila_calibrada']} aviso='{r['aviso']}'")

        eq_combinada = _equity_combinada(pernas, ini, fim)
        maxdd_cesta = maxdd_brl(eq_combinada)
        maxdd_pmam3_sozinha = resultados[PMAM3]["maxdd_brl"]
        maxdd_3x = 3.0 * maxdd_pmam3_sozinha

        metricas = _metricas_pool(pernas, ini, fim)
        capital_total_janela = sum(r["capital"] for r in pernas)

        print(f"\n  MaxDD da CESTA (soma dos 3 caixas): R${br(maxdd_cesta)}")
        print(f"  3x MaxDD da PMAM3 sozinha:          R${br(maxdd_3x)}  (PMAM3 sozinha: R${br(maxdd_pmam3_sozinha)})")
        veredito_dd = "MELHOR (cesta < 3x PMAM3 sozinha)" if maxdd_cesta < maxdd_3x else "PIOR OU IGUAL (cesta >= 3x PMAM3 sozinha)"
        print(f"  -> {veredito_dd}")
        print(f"  MaxDD % sobre capital total ({rotulo}): {100.0 * maxdd_cesta / capital_total_janela:.2f}%" if capital_total_janela else "")

        print(f"\n  liquido pool (3 pernas): R${br(metricas['liquido_brl'])}")
        print(f"  trades={metricas['trades']}  stops={metricas['stops']}  "
              f"pregoes={metricas['pregoes']}  pregoes_sem_trade={metricas['pregoes_sem_trade']}")
        print(f"  win%={metricas['win_pct']:.2f}%  IC95%%[{metricas['ic95_low']:.2f}%,{metricas['ic95_high']:.2f}%]  "
              f"breakeven_empirico={metricas['breakeven_empirico_pct']:.2f}%")
        print(f"  ganho_medio=R${br(metricas['ganho_medio'])}  perda_media=R${br(metricas['perda_media'])}")
        print(f"  fracao de pregoes positivos: {metricas['frac_pregoes_positivos_pct']:.1f}%")
        print(f"  capital total usado nesta janela: R${br(capital_total_janela)}")

    print(f"\n[gremah_cesta_correlacao] capital total da cesta (referencia, capital IS): R${br(capital_total)}")


if __name__ == "__main__":
    main()
