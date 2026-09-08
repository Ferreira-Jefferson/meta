"""Impacto de PARAR de operar nos dias/horarios menos favoraveis -- pedido do
dono, 2026-09-04, seguindo `wdo_win_padrao_dia_horario_2026_09_04.py`: "e se
parassemos de operar nos dias e horarios menos favoraveis, qual o impacto
disso no lucro e na acertividade?"

## Por que isto NAO reusa o achado do script anterior direto

O script anterior mediu dia/hora sobre o HISTORICO INTEIRO (IS+OOS
misturados) -- valido para DESCREVER o que ja aconteceu, mas usar esse mesmo
numero para ESCOLHER uma regra e depois "confirmar" que ela funciona no
MESMO historico seria julgar a prova com a resposta na mao (o erro que este
projeto ja cometeu e corrigiu: `frozen_split_scope_2026_08_21`,
`copa_oos_gasto_2026_08_26`). Aqui a regra de exclusao e' escolhida SO' com
o trecho IS (`< OOS_CUTOFF`, o mesmo corte congelado da familia inteira,
`backtest.intraday.profiles.OOS_CUTOFF = "2026-06-13"`), e o numero que
DECIDE e' o impacto no trecho OOS -- nunca visto pela regra. O numero no
historico INTEIRO tambem e' mostrado, mas so' como referencia (nao e' prova
de nada: o IS dele foi usado pra escolher a propria regra).

## Regra de exclusao (calculada, nao digitada a mao)

- **pior dia**: o dia da semana com menor liquido/pregao no IS -- sempre
  existe 1, mesmo que todos sejam positivos ("menos favoravel" nao exige ser
  negativo, e' so' o pior dos cinco).
- **horas ruins**: toda hora local com liquido/pregao NEGATIVO no IS -- se
  nenhuma for negativa (caso raro), cai para a unica pior hora.

## Mecanismo: FiltroDiaHora (wrapper -- NAO muda uma linha do robo)

Envolve o robo de producao (`get_daytrade_robot`) e bloqueia SO' as acoes
`Enter`/`EnterLimit` propostas por ele quando a barra cai numa janela
excluida -- `Exit`/`AdjustStop`/`AdjustTarget` e qualquer posicao ja aberta
seguem sob o comando NORMAL do robo (nao existe "abandonar posicao": parar
de operar e' parar de ABRIR, nunca deixar de GERENCIAR o que ja esta aberto).

**Detalhe que quebraria tudo sem cuidado** (achado lendo `wdo_grid_reload_
maker.py` antes de escrever isto): a `WdoGridReloadMaker` marca
`state.pending_side` ANTES de devolver a `EnterLimit` (linha 725), e so' o
FILL (via `positions`) ou `on_order_rejected` zeram isso de volta. Se este
wrapper so' descartasse a acao sem avisar o robo, `pending_side` ficaria
preso para SEMPRE (a barra seguinte cai direto em `if state.pending_side is
not None: return []`, linha 707) -- o robo pararia de propor QUALQUER coisa
pelo resto do historico inteiro, muito depois da janela excluida terminar.
Por isso este wrapper chama `self._inner.on_order_rejected(ts)` toda vez que
suprime uma entrada -- exatamente o aviso que o motor real dá quando uma
ordem morre sem preencher (`IntradayStrategy.on_order_rejected`), e o motivo
de esse hook existir (incidente de 2026-08-28, "travando o robo pelo resto
da sessao", ver `LICOES_DE_PRODUCAO.md`). Confirmado nas duas classes:
`WdoGridReloadMaker` so' propoe `Enter`/`EnterLimit` no ramo SEM posicao
(nunca conflita com a precondicao "nenhuma posicao resultou dela"); `CopaWin`
nem sobrescreve o hook (no-op seguro).

## Tres variantes testadas, contra o MESMO baseline (config de producao,
## capital com folga -- mesmos R$5.000/R$3.000 de `wdo_win_padrao_dia_
## horario_2026_09_04.py`, pelo mesmo motivo: nao confundir "dia ruim" com
## "faltou caixa")

1. `sem_pior_dia` -- so' bloqueia o dia.
2. `sem_horas_ruins` -- so' bloqueia as horas.
3. `sem_ambos` -- os dois juntos.

Cada variante roda a MESMA passada continua sobre o historico INTEIRO (o
filtro vale desde o primeiro pregao -- nao ha' como "comecar a filtrar so' no
OOS" sem quebrar a continuidade de caixa de que o dimensionamento dinamico
depende). O numero que decide fica isolado DEPOIS, cortando trades/equity por
data de entrada >= OOS_CUTOFF.

Uso: `python -u scripts/daytrade/wdo_win_filtro_dia_horario_impacto_2026_09_04.py`
"""
from __future__ import annotations

import datetime
import sys
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TZ = "America/Sao_Paulo"
MIN_BARRAS_POR_PREGAO = 400
DIAS_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta")
#: Mesmo corte congelado de `backtest.intraday.profiles.OOS_CUTOFF`,
#: reaproveitado (nao redescoberto) para nao inventar um corte novo so' para
#: este teste -- ver a nota longa la' sobre por que futuro reusa o corte da
#: familia de acoes.
OOS_CUTOFF = "2026-06-13"

ROBOS = (
    dict(label="WDO F1 maker", symbol="WDO@", key="wdo_grid_reload_maker",
         economia=(0.01, 0.001), capital=5_000.0),
    dict(label="CopaWin", symbol="WIN@", key="copa_win",
         economia=(0.2, 1.0), capital=3_000.0),
)


def br(v, casas: int = 2) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _to_local(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(TZ)


def _carregar_bars(symbol: str) -> pd.DataFrame:
    sys.path.insert(0, str(ROOT / "src"))
    from market_data_intraday.storage import load_m1

    df = load_m1(symbol).sort_index()
    if df.empty:
        raise SystemExit(f"sem dado M1 salvo para {symbol!r}.")
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    return df[[d in completos for d in df.index.date]]


def _rodar_variante(symbol: str, key: str, economia: tuple[float, float], capital: float,
                     dias_excluidos: frozenset[int], horas_excluidas: frozenset[int]):
    """Roda no PROCESSO FILHO -- constroi tudo aqui dentro (nada de classe
    dinamica cruzando o boundary de pickle: so' os parametros primitivos)."""
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.base import Enter, EnterLimit, IntradayStrategy
    from strategy.daytrade.registry import get_daytrade_robot

    class FiltroDiaHora(IntradayStrategy):
        def __init__(self, inner: IntradayStrategy):
            self._inner = inner
            self.name = inner.name
            self.version = inner.version
            self.symbol = inner.symbol
            self.target_fills_as_maker = inner.target_fills_as_maker
            self.feed_kind = inner.feed_kind
            self.is_futuro = inner.is_futuro

        def initialize(self, bars):
            return self._inner.initialize(bars)

        def on_session_start(self, session_date):
            return self._inner.on_session_start(session_date)

        def on_capital_update(self, cash_brl):
            return self._inner.on_capital_update(cash_brl)

        def on_order_rejected(self, ts):
            return self._inner.on_order_rejected(ts)

        def seed_volume_window(self, previous_session_tail):
            return self._inner.seed_volume_window(previous_session_tail)

        def seed_daily_volatility(self, previous_daily_bars):
            return self._inner.seed_daily_volatility(previous_daily_bars)

        def seed_typical_trade_size(self, previous_daily_medians):
            return self._inner.seed_typical_trade_size(previous_daily_medians)

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            acoes = self._inner.on_bar(ts, bar, positions, session_pnl_brl)
            local = _to_local(pd.Timestamp(ts))
            bloqueado = local.weekday() in dias_excluidos or local.hour in horas_excluidas
            if not bloqueado:
                return acoes
            permitidas = []
            suprimiu_entrada = False
            for a in acoes:
                if isinstance(a, (Enter, EnterLimit)):
                    suprimiu_entrada = True
                else:
                    permitidas.append(a)
            if suprimiu_entrada:
                # Ver docstring do modulo: sem isto, `WdoGridReloadMaker`
                # trava para sempre com `pending_side` preso.
                self._inner.on_order_rejected(ts)
            return permitidas

    bars = _carregar_bars(symbol)
    strat: IntradayStrategy = get_daytrade_robot(key, symbol=symbol)
    if dias_excluidos or horas_excluidas:
        strat = FiltroDiaHora(strat)
    profile = profile_for(symbol)
    trade_tick_value, trade_tick_size = economia
    cfg = config_for(
        profile, trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    sessoes = sorted(set(_to_local(pd.Timestamp(ts)).date() for ts in bars.index))
    return sessoes, resultado


def _pior_dia_e_horas_ruins(sessoes_is: list, trades_is: list):
    n_por_dia = Counter(d.weekday() for d in sessoes_is)
    liquido_por_dia: dict = defaultdict(float)
    liquido_por_hora: dict = defaultdict(float)
    for t in trades_is:
        local = _to_local(pd.Timestamp(t.entry_ts))
        liquido_por_dia[local.weekday()] += t.pnl_brl
        liquido_por_hora[local.hour] += t.pnl_brl
    pnl_pregao_dia = {d: liquido_por_dia.get(d, 0.0) / n for d, n in n_por_dia.items() if n}
    pior_dia = min(pnl_pregao_dia, key=pnl_pregao_dia.get)
    n_pregoes_is = len(sessoes_is)
    pnl_pregao_hora = {h: v / n_pregoes_is for h, v in liquido_por_hora.items()} if n_pregoes_is else {}
    horas_ruins = {h for h, v in pnl_pregao_hora.items() if v < 0}
    if not horas_ruins and pnl_pregao_hora:
        horas_ruins = {min(pnl_pregao_hora, key=pnl_pregao_hora.get)}
    return pior_dia, horas_ruins, pnl_pregao_dia, pnl_pregao_hora


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import cabecalho, linha, linha_de_resultado

    cutoff = datetime.date.fromisoformat(OOS_CUTOFF)
    print(f"[wdo_win_filtro_dia_horario_impacto] regra escolhida SO com IS "
          f"(< {OOS_CUTOFF}), impacto medido SO no OOS (>= {OOS_CUTOFF})\n", flush=True)

    resultados: dict = defaultdict(dict)  # symbol -> variante -> (sessoes, resultado)
    regra: dict = {}
    pending = {}

    with ProcessPoolExecutor(max_workers=8) as ex:
        for robo in ROBOS:
            fut = ex.submit(_rodar_variante, robo["symbol"], robo["key"], robo["economia"],
                             robo["capital"], frozenset(), frozenset())
            pending[fut] = dict(robo=robo, variante="baseline")

        while pending:
            done, _ = wait(list(pending.keys()), return_when=FIRST_COMPLETED)
            for fut in done:
                meta = pending.pop(fut)
                sessoes, resultado = fut.result()
                robo, variante = meta["robo"], meta["variante"]
                symbol = robo["symbol"]
                resultados[symbol][variante] = (sessoes, resultado)
                print(f"[pronto] {robo['label']:15s} variante={variante:16s} "
                      f"{len(resultado.trades):5d} trades", flush=True)

                if variante == "baseline":
                    sessoes_is = [d for d in sessoes if d < cutoff]
                    trades_is = [t for t in resultado.trades
                                 if _to_local(pd.Timestamp(t.entry_ts)).date() < cutoff]
                    pior_dia, horas_ruins, pnl_dia, pnl_hora = _pior_dia_e_horas_ruins(
                        sessoes_is, trades_is)
                    regra[symbol] = dict(pior_dia=pior_dia, horas_ruins=horas_ruins,
                                          pnl_dia=pnl_dia, pnl_hora=pnl_hora,
                                          n_pregoes_is=len(sessoes_is))
                    print(f"  regra ({robo['label']}, {len(sessoes_is)} pregoes IS): "
                          f"pior dia={DIAS_SEMANA[pior_dia]} ({br(pnl_dia[pior_dia])}/pregao) | "
                          f"horas ruins={sorted(horas_ruins)}h "
                          f"({', '.join(f'{h}h={br(pnl_hora[h])}' for h in sorted(horas_ruins))})",
                          flush=True)
                    variantes = {
                        "sem_pior_dia": (frozenset({pior_dia}), frozenset()),
                        "sem_horas_ruins": (frozenset(), frozenset(horas_ruins)),
                        "sem_ambos": (frozenset({pior_dia}), frozenset(horas_ruins)),
                    }
                    for nome, (dias, horas) in variantes.items():
                        f2 = ex.submit(_rodar_variante, symbol, robo["key"], robo["economia"],
                                       robo["capital"], dias, horas)
                        pending[f2] = dict(robo=robo, variante=nome)

    print()
    ordem_variantes = ("baseline", "sem_pior_dia", "sem_horas_ruins", "sem_ambos")
    for robo in ROBOS:
        symbol = robo["symbol"]
        print("=" * 100)
        print(f"{robo['label']} ({symbol}) -- capital R${br(robo['capital'], 0)}")
        print("=" * 100)

        print("\n--- historico INTEIRO (referencia -- a regra viu o IS disto, nao e prova) ---")
        print(cabecalho())
        for nome in ordem_variantes:
            sessoes, resultado = resultados[symbol][nome]
            item = linha_de_resultado(nome, resultado, robo["capital"])
            print(linha(item))

        print(f"\n--- SO OOS (>= {OOS_CUTOFF}) -- o numero que decide, a regra nunca viu isto ---")
        print(cabecalho())
        linhas_oos = {}
        for nome in ordem_variantes:
            sessoes, resultado = resultados[symbol][nome]
            trades_oos = [t for t in resultado.trades
                          if _to_local(pd.Timestamp(t.entry_ts)).date() >= cutoff]
            eq = resultado.equity_curve
            if eq is not None and not eq.empty:
                local_idx = pd.DatetimeIndex([_to_local(pd.Timestamp(ts)) for ts in eq.index])
                eq_oos = eq[local_idx.date >= cutoff]
            else:
                eq_oos = eq
            fake = SimpleNamespace(trades=trades_oos, equity_curve=eq_oos)
            item = linha_de_resultado(f"{nome} [OOS]", fake, initial_capital=0, capital_nocional=True)
            linhas_oos[nome] = item
            print(linha(item))

        base = linhas_oos["baseline"]
        melhor_nome = max(ordem_variantes[1:], key=lambda n: linhas_oos[n].liquido_brl)
        melhor = linhas_oos[melhor_nome]
        print(f"\nOOS baseline: R${br(base.liquido_brl)} liquido, {br(base.win_rate_pct,1)}% win, "
              f"{base.trades} trades")
        print(f"OOS melhor variante ({melhor_nome}): R${br(melhor.liquido_brl)} liquido "
              f"({'+' if melhor.liquido_brl >= base.liquido_brl else ''}"
              f"{br(melhor.liquido_brl - base.liquido_brl)}), "
              f"{br(melhor.win_rate_pct,1)}% win "
              f"({'+' if melhor.win_rate_pct >= base.win_rate_pct else ''}"
              f"{br(melhor.win_rate_pct - base.win_rate_pct,1)}pp), "
              f"{melhor.trades} trades ({melhor.trades - base.trades:+d})")
        print()


if __name__ == "__main__":
    main()
