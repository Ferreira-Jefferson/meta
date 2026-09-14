"""HIPOTESE A VALIDAR (brainstorm rodada 2, dono 2026-09-11): "Gremah -- lote
por compressao de range M1". Antes de armar a `EnterLimit` padrao da familia
`gremah` (geometria em TICKS intocada -- `_GEOMETRIA_TICKS_BY_SYMBOL`, ja
validada), calcula ATR(20)/mediana(ATR(20), 120) em M1; comprimido (razao
<=0,7) tenta DOBRAR para 2 lotes (teto rigido 2, sujeito ao portao de capital
real); expandido (razao >=1,3) PULA a tentativa de entrada nesta barra;
faixa intermediaria opera como hoje (nenhuma mudanca).

Simbolos: CSAN3 e KLBN3 -- os DOIS unicos simbolos da familia com geometria
FIXA em ticks sem ambiguidade dinamica (`_GEOMETRIA_TICKS_BY_SYMBOL`, ver
[[gremah-calibracao-fina-m1-2026-08-27]]). PMAM3 excluida de proposito (ordem
explicita do dono desta rodada) -- colapsou de R$4,53 para R$0,13 dentro da
propria janela de calibracao ([[pmam3-colapso-de-preco-2026-08-26]]).

## Por que isto NAO duplica nada ja medido (ver MEMORY.md inteiro antes de
## rodar de novo)

- NAO e' [[gremah-ancora-fixa-refutada-2026-08-26]] (ancora fixa vs rolante)
  nem [[geometria-acoplada-gremah-2026-08-26]] (bug ja corrigido de
  profit_pct arrastando dois parametros) -- aqui os TRES ticks
  (profit/spacing/stop) ficam exatamente como `_GEOMETRIA_TICKS_BY_SYMBOL`
  ja define, nunca tocados.
- NAO e' [[capital_ladder_qualidade_sinal_reversao_2026_08_27]] (aquele
  trabalho testou `volume_toque`/`minutos_desde_abertura` como GATE DE
  ENTRADA -- entra ou nao entra -- e SAIDA por reversao/giveback de MFE; este
  aqui e' GATE DE QUANTIDADE PRE-TRADE por REGIME DE VOLATILIDADE, um eixo
  novo, e a entrada continua entrando na faixa intermediaria).
- NAO e' `_lotes_por_realocacao` (a escalada de lote por CAIXA ACUMULADO ja
  existente em producao) -- aqui a trava roda em CIMA dela: mantem a mesma
  chamada (`super()._lotes_por_realocacao`) como base "hoje" e so' aplica
  a MULTIPLICACAO por regime de vol quando comprimido, ou PULA a barra
  quando expandido. Nunca muda o percentual/tick, o financiamento por caixa
  continua o que ja era.

## Metodo (nao negociado -- convencoes centrais do projeto)

1. Experimento em `scripts/daytrade/`, subclasse de `Gremah` (producao
   intocada, nenhum arquivo em `src/strategy/` editado).
2. TESTE PEQUENO PRIMEIRO: os ultimos `N_PREGOES_TESTE_PEQUENO` pregoes do
   IS (janela pequena, real, mais recente) para as DUAS variantes (baseline
   producao vs vol-gate) nos DOIS simbolos -- 4 rodadas. So' se sobreviver
   (edge nao-negativo, sem zerar, trades>0) o script segue para o IS+OOS
   completo (disciplina de sempre: `LockedBars`, corte OFICIAL
   `OOS_CUTOFF=2026-06-13`, nunca reajustado por este achado).
3. Capital = `capital_minimo_brl(preco_de_referencia)` -- preco do OPEN da
   PRIMEIRA barra de CADA janela (mesmo padrao de
   `gremah_defesa_corte_sweep_2026_09_03.py`), nunca um valor redondo. Este e'
   TAMBEM o minimo que sustenta o HARD CAP de 2 lotes (a formula do projeto
   ja embute 2 lotes: `preco*100*2.0`), entao nao precisa de capital extra
   so' por causa desta hipotese -- o portao de capital real
   (`enforce_capital_minimo`, default True em acao) e o cheque de caixa
   dentro do proprio gate (`_cash_atual_brl >= 2*custo_do_lote`) sao quem
   FREIA o 2o lote se o caixa nao aguentar de verdade.
4. `ProcessPoolExecutor` (`submit`/`as_completed`, nunca `pool.map`),
   streaming por tarefa.
5. Tabela padrao (`backtest/intraday/report.py::tabela`), 12 colunas + extras
   (`n_pulos_expansao`, `n_dobras_compressao`) -- SEM inventar coluna nova na
   base. `fila NAO CALIBRADA` vai aparecer sozinha no aviso (Gremah em acao
   B3 nunca foi calibrada em `backtest/intraday/fidelidade.py` -- so' o WDO@
   foi, ver a docstring daquele modulo) -- declarado aqui, nao escondido.
6. IC95% de Wilson do win% contra o BREAKEVEN EMPIRICO
   (perda_media/(ganho_medio+perda_media)), win% E o nulo lado a lado
   (`feedback_present_tables_no_verdict` / regra do dono desta rodada:
   nao ler liquido sem os dois).
7. Sem look-ahead: o ratio de compressao usa SOMENTE a barra ATUAL (a de
   ARMAR a ordem) e o historico de barras JA FECHADAS antes dela -- mesma
   convencao que `filtro_volume_toque_max` ja usa na mesma classe (ver a
   docstring de `_passa_filtro_qualidade_entrada` em `gremah.py`: "a barra
   ATUAL e' a melhor proxy disponivel, sem look-ahead"). O ATR(20) e a
   mediana(120) sao causais (deque, atualizados bar a bar) e persistem
   ATRAVES de sessoes (regime de volatilidade e' propriedade continua do
   mercado, nao reseta a cada pregao -- so' o estado de SESSAO do robo
   reseta em `on_session_start`, nunca tocado aqui).

Uso: `python -u scripts/daytrade/gremah_lote_compressao_atr_2026_09_11.py`
"""
from __future__ import annotations

import contextlib
import io
import math
import os
import statistics
import sys
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


SYMBOLS = ("CSAN3", "KLBN3")

#: MESMOS valores de `PROFILES` em `backtest/intraday/profiles.py`
#: (duplicados aqui, nao importados via MT5 -- mesmo motivo de
#: `gremah_defesa_corte_sweep_2026_09_03.py`: nao abrir conexao com o
#: terminal num script que so' precisa da data).
REGIME_START = {"CSAN3": "2025-09-22", "KLBN3": "2025-03-10"}

MIN_BARRAS_M1_ACAO = 20
TRADE_TICK_VALUE = 0.01
TRADE_TICK_SIZE = 0.01

#: Parametros da hipotese, EXATAMENTE como o dono especificou.
ATR_WINDOW = 20
ATR_HIST_WINDOW = 120
RATIO_COMPRIMIDO = 0.7
RATIO_EXPANDIDO = 1.3

#: Teste pequeno primeiro -- ultimos N pregoes do IS (dado real, recente).
N_PREGOES_TESTE_PEQUENO = 15

EXTRAS = ("n_pulos_exp", "n_dobras_comp", "n_stops", "wr_ic95", "breakeven_emp", "dias_pos_pct")

UNLOCK_REASON = (
    "gremah_lote_compressao_atr (2026-09-11): hipotese NOVA de gate de "
    "QUANTIDADE pre-trade por regime de volatilidade (ATR20/mediana-ATR120), "
    "geometria em ticks intocada. Segue a disciplina padrao do projeto: "
    "teste pequeno no IS primeiro, IS/OOS completo so' se sobreviver."
)

_BARS_PROC: dict[str, object] = {}


def _bars_do_processo(symbol: str):
    global _BARS_PROC
    if symbol not in _BARS_PROC:
        from backtest.intraday.frozen_split import LockedBars, declare_frozen_split
        from backtest.intraday.profiles import profile_for
        from market_data_intraday.storage import load_m1

        df = load_m1(symbol).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_M1_ACAO}
        df = df[[d in completos for d in df.index.date]]
        regime_start = pd.Timestamp(REGIME_START[symbol], tz=df.index.tz)
        df = df.loc[df.index >= regime_start]

        profile = profile_for(symbol)
        split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
        locked = LockedBars(df, split)
        locked.unlock(UNLOCK_REASON)
        _BARS_PROC[symbol] = locked
    return _BARS_PROC[symbol]


def _make_strategy_classes():
    """Roda DENTRO do processo filho -- precisa do `sys.path` do filho."""
    from strategy.daytrade.lab.gremah import Gremah

    class GremahVolGate(Gremah):
        """MESMA Gremah (geometria em ticks intocada). Acrescenta um gate de
        QUANTIDADE pre-trade por regime de compressao/expansao de ATR(20)
        contra a mediana(ATR(20), 120) -- ver a docstring do modulo. Os DOIS
        pontos de extensao ja existem na classe-mae para exatamente este
        proposito (`_lotes_por_realocacao` decide QUANTOS lotes,
        `_passa_filtro_qualidade_entrada` decide SE arma a ordem nesta
        barra) -- nenhum outro metodo precisa mudar."""

        def __init__(self, *a, atr_window: int = ATR_WINDOW,
                     atr_hist_window: int = ATR_HIST_WINDOW,
                     ratio_comprimido: float = RATIO_COMPRIMIDO,
                     ratio_expandido: float = RATIO_EXPANDIDO,
                     **kw):
            super().__init__(*a, **kw)
            self.atr_window = atr_window
            self.atr_hist_window = atr_hist_window
            self.ratio_comprimido = ratio_comprimido
            self.ratio_expandido = ratio_expandido
            self._tr_hist: deque = deque(maxlen=atr_window)
            self._atr_hist: deque = deque(maxlen=atr_hist_window)
            self._prev_close: float | None = None
            self._vol_ratio_atual: float | None = None
            self.n_pulos_expansao = 0
            self.n_dobras_compressao = 0

        def _atualizar_regime_vol(self, bar) -> None:
            """Causal: usa so' a barra ATUAL (ja fechada, e' o que `on_bar`
            recebe) e o historico de TRs/ATRs ja acumulado ANTES dela. O
            historico persiste ATRAVES de sessoes de proposito (regime de
            vol e' continuo; so' resetaria se algo chamasse isto a partir de
            `on_session_start`, o que nunca acontece)."""
            if self._prev_close is None:
                tr = bar.high - bar.low
            else:
                tr = max(bar.high - bar.low,
                          abs(bar.high - self._prev_close),
                          abs(bar.low - self._prev_close))
            self._prev_close = bar.close
            self._tr_hist.append(tr)
            if len(self._tr_hist) < self.atr_window:
                self._vol_ratio_atual = None
                return
            atr_atual = sum(self._tr_hist) / len(self._tr_hist)
            if len(self._atr_hist) >= self.atr_hist_window:
                mediana = statistics.median(self._atr_hist)
                self._vol_ratio_atual = (atr_atual / mediana) if mediana > 0 else None
            else:
                self._vol_ratio_atual = None
            self._atr_hist.append(atr_atual)

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            self._atualizar_regime_vol(bar)
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        def _passa_filtro_qualidade_entrada(self, ts, bar) -> bool:
            if not super()._passa_filtro_qualidade_entrada(ts, bar):
                return False
            ratio = self._vol_ratio_atual
            if ratio is not None and ratio >= self.ratio_expandido:
                self.n_pulos_expansao += 1
                return False
            return True

        def _lotes_por_realocacao(self, anchor, ts) -> int:
            base = super()._lotes_por_realocacao(anchor, ts)
            ratio = self._vol_ratio_atual
            if ratio is not None and ratio <= self.ratio_comprimido:
                custo_do_lote = anchor * self.shares_per_lot
                if self._cash_atual_brl >= 2 * custo_do_lote:
                    self.n_dobras_compressao += 1
                    return 2
            return base

    return Gremah, GremahVolGate


def _roda_uma(spec: dict) -> tuple[str, dict]:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.machine import IntradayExitReason
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.base import capital_minimo_brl

    Gremah, GremahVolGate = _make_strategy_classes()

    symbol = spec["symbol"]
    locked = _bars_do_processo(symbol)
    if spec["janela"] == "IS":
        bars = locked.in_sample()
    elif spec["janela"] == "IS_PEQUENO":
        bars_full = locked.in_sample()
        dias = sorted(set(pd.DatetimeIndex(bars_full.index).date))
        dias_teste = set(dias[-N_PREGOES_TESTE_PEQUENO:])
        bars = bars_full[[d in dias_teste for d in bars_full.index.date]]
    else:
        bars = locked.out_of_sample()
    profile = profile_for(symbol)

    if bars.empty:
        raise SystemExit(f"[{spec['rotulo']}] janela vazia para {symbol!r}")
    preco_ref = float(bars.iloc[0]["open"])
    capital = capital_minimo_brl(preco_ref)

    if spec["variante"] == "baseline":
        strat = Gremah(symbol=symbol)
    else:
        strat = GremahVolGate(symbol=symbol)

    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )

    resultado = run_intraday_backtest(bars, strat, cfg)
    trades = list(resultado.trades)
    vencedores = [t for t in trades if t.pnl_brl > 0]
    perdedores = [t for t in trades if t.pnl_brl <= 0]
    n_stops = sum(1 for t in trades if t.exit_reason == IntradayExitReason.STOP)

    ganho_medio = (sum(t.pnl_brl for t in vencedores) / len(vencedores)) if vencedores else 0.0
    perda_media = (abs(sum(t.pnl_brl for t in perdedores) / len(perdedores))) if perdedores else 0.0
    breakeven_emp = (100.0 * perda_media / (ganho_medio + perda_media)
                      if (ganho_medio + perda_media) > 0 else float("nan"))
    lo, hi = ic_wilson(len(vencedores), len(trades)) if trades else (float("nan"), float("nan"))

    equity = resultado.equity_curve
    dias_pos_pct = float("nan")
    if equity is not None and not equity.empty:
        # equity ja acumula capital+pnl; delta dia-a-dia via diff do ULTIMO
        # valor de cada pregao (1o dia comparado contra o capital inicial).
        ultimos = equity.groupby(pd.DatetimeIndex(equity.index).date).last()
        deltas = ultimos.diff()
        deltas.iloc[0] = ultimos.iloc[0] - capital
        dias_pos_pct = 100.0 * float((deltas > 0).sum()) / float(len(deltas)) if len(deltas) else float("nan")

    n_pulos = getattr(strat, "n_pulos_expansao", 0)
    n_dobras = getattr(strat, "n_dobras_compressao", 0)
    pulou = len(resultado.sessoes_puladas_por_capital)

    extras = {
        "n_pulos_exp": str(n_pulos),
        "n_dobras_comp": str(n_dobras),
        "n_stops": str(n_stops),
        "wr_ic95": f"[{num_br(lo,1)};{num_br(hi,1)}]" if trades else "—",
        "breakeven_emp": f"{num_br(breakeven_emp,1)}%" if trades else "—",
        "dias_pos_pct": f"{num_br(dias_pos_pct,1)}%" if not math.isnan(dias_pos_pct) else "—",
    }
    item = linha_de_resultado(spec["rotulo"], resultado, capital, capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item, EXTRAS), flush=True)

    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        retorno_pct=item.retorno_pct, maxdd_pct=item.maxdd_pct, capital_final=item.capital_final,
        extras=item.extras, aviso=item.aviso,
        symbol=symbol, janela=spec["janela"], variante_key=spec["variante"], capital=capital,
        n_pulos=n_pulos, n_dobras=n_dobras, n_stops=n_stops, pulou=pulou,
        breakeven_emp=breakeven_emp, wr_lo=lo, wr_hi=hi, dias_pos_pct=dias_pos_pct,
        wiped_out=getattr(resultado, "wiped_out_at", None) is not None,
    )
    return buf.getvalue(), campos


def _n_workers(n_tarefas: int) -> int:
    return max(1, min(n_tarefas, 6, os.cpu_count() or 4))


def _monta_specs(janela: str) -> list[dict]:
    specs = []
    for symbol in SYMBOLS:
        for variante in ("baseline", "volgate"):
            specs.append(dict(
                rotulo=f"{symbol} {janela} {variante}",
                symbol=symbol, janela=janela, variante=variante,
            ))
    return specs


def _roda_lote(specs: list[dict]) -> dict[str, dict]:
    from backtest.intraday.report import cabecalho
    n_workers = _n_workers(len(specs))
    print(cabecalho(EXTRAS), flush=True)
    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados[futures[future]] = campos
    return resultados


def _imprime_tabela(resultados: dict[str, dict], rotulos: list[str]) -> None:
    from backtest.intraday.report import LinhaResultado, tabela
    linhas = [LinhaResultado(
        variante=resultados[r]["variante"], liquido_brl=resultados[r]["liquido_brl"],
        maxdd_brl=resultados[r]["maxdd_brl"], win_rate_pct=resultados[r]["win_rate_pct"],
        trades=resultados[r]["trades"], pregoes=resultados[r]["pregoes"],
        retorno_pct=resultados[r]["retorno_pct"], maxdd_pct=resultados[r]["maxdd_pct"],
        capital_final=resultados[r]["capital_final"], extras=resultados[r]["extras"],
        aviso=resultados[r]["aviso"],
    ) for r in rotulos]
    print(tabela(linhas, EXTRAS))


def _sobrevive_teste_pequeno(resultados: dict[str, dict]) -> bool:
    """Criterio de avanco (nao de veredito final): a variante `volgate` NAO
    pode zerar em nenhum simbolo e precisa ter tido pelo menos 1 trade em
    algum dos dois -- o minimo para justificar gastar a janela completa.
    Zero trades em ambos, ou conta zerada, encerra aqui (INVIAVEL/INDEFINIDA
    ja fica claro sem rodar IS/OOS inteiro)."""
    ok = True
    for symbol in SYMBOLS:
        rotulo = f"{symbol} IS_PEQUENO volgate"
        c = resultados.get(rotulo)
        if c is None:
            continue
        if c["wiped_out"]:
            print(f"[gate] {rotulo}: ZEROU a conta no teste pequeno -- nao avanca.")
            ok = False
    trades_totais = sum(resultados[f"{s} IS_PEQUENO volgate"]["trades"] for s in SYMBOLS
                         if f"{s} IS_PEQUENO volgate" in resultados)
    if trades_totais == 0:
        print("[gate] 0 trades em AMBOS os simbolos no teste pequeno -- nao avanca.")
        ok = False
    return ok


def main() -> None:
    t0 = time.perf_counter()

    print("=" * 100)
    print("FASE 1 -- TESTE PEQUENO PRIMEIRO "
          f"(ultimos {N_PREGOES_TESTE_PEQUENO} pregoes do IS, dado real)")
    print("=" * 100)
    specs_pequeno = _monta_specs("IS_PEQUENO")
    resultados_pequeno = _roda_lote(specs_pequeno)
    for symbol in SYMBOLS:
        print(f"\n-- {symbol} (teste pequeno, capital R${br(resultados_pequeno[f'{symbol} IS_PEQUENO baseline']['capital'])}) --")
        _imprime_tabela(resultados_pequeno, [f"{symbol} IS_PEQUENO baseline", f"{symbol} IS_PEQUENO volgate"])

    avanca = _sobrevive_teste_pequeno(resultados_pequeno)
    print(f"\n[gate] avanca para IS/OOS completo? {'SIM' if avanca else 'NAO'}")

    resultados_full: dict[str, dict] = {}
    if avanca:
        print("\n" + "=" * 100)
        print("FASE 2 -- IS COMPLETO + OOS (LockedBars, corte oficial OOS_CUTOFF=2026-06-13)")
        print("=" * 100)
        specs_full = _monta_specs("IS") + _monta_specs("OOS")
        resultados_full = _roda_lote(specs_full)
        for symbol in SYMBOLS:
            for janela in ("IS", "OOS"):
                print(f"\n-- {symbol} {janela} (capital R${br(resultados_full[f'{symbol} {janela} baseline']['capital'])}) --")
                _imprime_tabela(resultados_full, [f"{symbol} {janela} baseline", f"{symbol} {janela} volgate"])

    print(f"\n[gremah_lote_compressao_atr] total: {time.perf_counter() - t0:.1f}s")

    print("\n" + "=" * 100)
    print("RESUMO -- pulos por expansao / dobras por compressao / stops (todas as rodadas)")
    print("=" * 100)
    for rotulo, c in {**resultados_pequeno, **resultados_full}.items():
        if c["variante_key"] == "volgate":
            print(f"  {rotulo}: n_pulos_expansao={c['n_pulos']} n_dobras_compressao={c['n_dobras']} "
                  f"n_stops={c['n_stops']} pregoes_pulados_capital={c['pulou']} "
                  f"breakeven_emp={num_br_local(c['breakeven_emp'])}% "
                  f"IC95_win=[{num_br_local(c['wr_lo'])};{num_br_local(c['wr_hi'])}] "
                  f"dias_pos={num_br_local(c['dias_pos_pct'])}%")


def num_br_local(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return br(v, 1)


if __name__ == "__main__":
    main()
