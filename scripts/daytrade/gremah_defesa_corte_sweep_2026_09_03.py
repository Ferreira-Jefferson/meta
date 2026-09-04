"""Varredura de `defesa_recuo` e `corte_persistencia` PORTADOS para `Gremah`
(M1, 2026-09-03) -- mesmos dois mecanismos ja medidos em `CopaWin`
(`copawin_defesa_recuo_sweep_2026_09_03.py`,
`copawin_corte_persistencia_sweep_2026_09_03.py`), agora na familia `gremah`,
nos DOIS simbolos que hoje operam `Gremah` com DINHEIRO REAL em producao:
PMAM3 (`_GEOMETRIA_TICKS_BY_SYMBOL["PMAM3"] = (1, 1, 16)`) e KLBN3
(`_GEOMETRIA_TICKS_BY_SYMBOL["KLBN3"] = (1, 1, 4)`).

## Hipotese a CONFIRMAR OU REFUTAR por medicao (nao presumir)

A familia `gremah` tem o ALVO travado em 1 tick estrutural em 9 dos 10
simbolos calibrados (`_ticks_from_pct`, "profit_pct satura no piso de 1
tick"). PMAM3 e KLBN3 confirmam isso via `_GEOMETRIA_TICKS_BY_SYMBOL`
(alvo=1 tick nos dois). E' EXATAMENTE a mesma degenerescencia que
`WdoGridReloadMaker` mostrou ter com `defesa_ativa` (alvo de 1 tick nao deixa
espaco para um estado "quase no alvo" entre 0% e 100% -- o preco real so'
anda em multiplos do proprio tick, entao a fracao restante so' pode ser 0%
-- ja bateu o alvo pelo caminho normal -- ou 100%, nunca intermediaria).
Bem provavel que `defesa_recuo` seja igualmente degenerado aqui, mas PRECISA
ser medido -- o mesmo mecanismo teve falsos-positivos na WDO F1 rastreados a
um GAP de dado, entao o numero real importa, nao a analogia. `corte_
persistencia` NAO depende da largura do alvo (mede barras decorridas), entao
nao ha' motivo a priori para ele degenerar -- tambem medido, nao presumido.

## Disciplina IS/OOS (AGENTS.md/CLAUDE.md -- mexe em regra de SAIDA de
## estrategia em producao)

`backtest.intraday.frozen_split.LockedBars`, corte declarado no PERFIL de
cada simbolo (`profile_for(symbol).frozen_cutoff`, `OOS_CUTOFF="2026-06-13"`
em `backtest/intraday/profiles.py` -- MESMO corte para toda a familia
`gremah`, congelado em 2026-08-22 antes de qualquer varredura de parametro).
`.in_sample()`/`.out_of_sample()` sempre reportados SEPARADOS.

### AVISO METODOLOGICO -- esta janela OOS ja' foi espiada antes

A mesma janela OOS (>=2026-06-13) ja' foi usada para confirmar a geometria em
ticks de PMAM3/KLBN3 (`_GEOMETRIA_TICKS_BY_SYMBOL`, 2026-08-26) e para varias
outras medidas da familia desde entao (capacidade de caixa, filtro de
qualidade de entrada, `dividir_entrada`/`exit_ttl_bars`). Um resultado bom
aqui no "OOS" e' evidencia MAIS FRACA do que um OOS genuinamente nunca
visto -- mesmo principio de `copa-oos-gasto-2026-08-26`. Isto NAO invalida o
numero, so' pesa menos do que um OOS limpo pesaria.

## Capital (CLAUDE.md, "capital inicial nunca arbitrario")

`capital_minimo_brl(preco_de_referencia)` -- o preco de referencia e' o
OPEN da PRIMEIRA barra de CADA janela (IS e OOS recebem capitais DIFERENTES,
de proposito: PMAM3 mudou de patamar de preco dentro do proprio historico,
ver `pmam3_colapso_de_preco_2026_08_26`, entao herdar o capital do IS para o
OOS seria a mesma arbitrariedade que capital fixo -- mesmo desenho de
`capital_ladder_gremah_oos_2026_08_27.py`).

## Grade

`defesa_gatilho_stop_pct` em [0,10 / 0,25 / 0,50] x `defesa_alvo_
proximidade_pct` em [0,10 / 0,25 / 0,50] -- 9 combinacoes.
`corte_persistencia_min_barras` em [5 / 15 / 30] x `corte_persistencia_
frac_adverso` em [0,50 / 0,75 / 1,00] -- 9 combinacoes.
Mais 1 baseline (os dois mecanismos desligados, geometria de producao
intacta) -- 19 variantes x 2 simbolos x 2 janelas = 76 tarefas.

Contagem de disparos REAL de cada mecanismo (nao um proxy): subclasse
`_GremahInstrumentado` conta toda vez que `_defesa_deve_fechar`/`_corte_
persistencia_deve_fechar` devolve `True` -- `IntradayTrade.exit_reason` so'
guarda o ENUM agregado (`IntradayExitReason.SIGNAL`), que tambem cobre
`stop_agregado_sessao` (a perda-limite diaria, sempre ativa nesta classe,
nao opt-in) -- contar SIGNAL cru misturaria os dois em Gremah (diferente de
`CopaWin`, que nao tem perda diaria ligada por padrao nos sweeps irmaos).

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`),
`redirect_stdout` por tarefa, `flush=True`, streaming (cada tarefa imprime a
linha dela assim que termina). N de processos reduzido (maquina roda robos
de day trade/swing AO VIVO com dinheiro real durante o horario normal).

Uso: `python -u scripts/daytrade/gremah_defesa_corte_sweep_2026_09_03.py`
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))


def br(v: float, dec: int = 2) -> str:
    """Formato BR (milhar com ponto, decimal com virgula)."""
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


SYMBOLS = ("PMAM3", "KLBN3")

#: Data a partir da qual o regime de preco ATUAL de cada simbolo comeca --
#: MESMOS valores de `scripts/daytrade/_geometria_comum.py::REGIME_START`
#: (duplicados aqui, nao importados: aquele modulo tambem importa
#: `market_data_intraday.mt5_source.symbol_economics`, que fala com o
#: terminal MT5 -- este script nao precisa e nao deve abrir essa conexao).
REGIME_START = {"PMAM3": "2025-12-16", "KLBN3": "2025-03-10"}

#: Giro de ACAO e' bem mais baixo que futuro -- limiar de sessao "completa"
#: bem mais frouxo que o `MIN_BARRAS_M1_FUTURO=400` dos sweeps de WIN@/WDO@
#: (mesmo valor usado em `gremah_pmam3_stop16_capital_2026_08_31.py`).
MIN_BARRAS_M1_ACAO = 20

#: Toda acao da familia gremah reporta tick_value=tick_size=0.01 no cache de
#: economics (`data/_economics_cache.json`, conferido para PMAM3 e KLBN3) --
#: hardcoded aqui pelo MESMO motivo de `gremah_pmam3_stop16_capital_2026_08_
#: 31.py`: nao abrir conexao MT5 num sweep que so' precisa do numero, ja
#: sabido e igual nos dois simbolos.
TRADE_TICK_VALUE = 0.01
TRADE_TICK_SIZE = 0.01

#: Grade de `defesa_recuo` -- ver a docstring do modulo.
DEFESA_GATILHO_GRID = [0.10, 0.25, 0.50]
DEFESA_PROXIMIDADE_GRID = [0.10, 0.25, 0.50]

#: Grade de `corte_persistencia` -- ver a docstring do modulo.
CORTE_MIN_BARRAS_GRID = [5, 15, 30]
CORTE_FRAC_ADVERSO_GRID = [0.50, 0.75, 1.00]

#: Colunas EXTRA desta rodada -- entram DEPOIS das 12 da base
#: (`backtest/intraday/report.py`), nunca no lugar delas.
EXTRAS = ("mecanismo", "param1", "param2", "n_disparos", "pulou")

UNLOCK_REASON = (
    "defesa_recuo/corte_persistencia (2026-09-03) mexem em regra de SAIDA de "
    "estrategia em producao -- disciplina IS/OOS exigida por AGENTS.md/"
    "CLAUDE.md. Janela OOS ja' foi espiada antes (geometria em ticks "
    "confirmada 2026-08-26, capacidade/filtro de qualidade depois) -- ver o "
    "aviso metodologico no relatorio final; isto NAO invalida o numero, so' "
    "pesa menos do que um OOS genuinamente nunca visto."
)

#: Barras M1 lidas UMA vez por SIMBOLO por PROCESSO.
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


def _monta_specs() -> list[dict]:
    specs: list[dict] = []
    for symbol in SYMBOLS:
        for janela in ("IS", "OOS"):
            specs.append(dict(
                rotulo=f"{symbol} {janela} baseline (off)",
                symbol=symbol, janela=janela, mecanismo="baseline",
                param1=None, param2=None,
            ))
            for gatilho in DEFESA_GATILHO_GRID:
                for proximidade in DEFESA_PROXIMIDADE_GRID:
                    specs.append(dict(
                        rotulo=f"{symbol} {janela} defesa g{gatilho*100:.0f}% p{proximidade*100:.0f}%",
                        symbol=symbol, janela=janela, mecanismo="defesa_recuo",
                        param1=gatilho, param2=proximidade,
                    ))
            for min_barras in CORTE_MIN_BARRAS_GRID:
                for frac_adverso in CORTE_FRAC_ADVERSO_GRID:
                    specs.append(dict(
                        rotulo=f"{symbol} {janela} corte m{min_barras} f{frac_adverso*100:.0f}%",
                        symbol=symbol, janela=janela, mecanismo="corte_persistencia",
                        param1=min_barras, param2=frac_adverso,
                    ))
    return specs


def _roda_uma(spec: dict) -> tuple[str, dict]:
    """Executado no processo FILHO. Devolve (texto_ja_formatado_da_linha,
    dict_leve_com_os_campos) -- o pai imprime o texto na hora (streaming) e
    usa o dict pra remontar as tabelas finais na ORDEM logica."""
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.lab.gremah import Gremah

    class _GremahInstrumentado(Gremah):
        """MESMA Gremah, so' conta toda vez que cada mecanismo novo devolve
        `True` -- `IntradayTrade.exit_reason` guarda so' o enum agregado
        (`SIGNAL`), que tambem cobre `stop_agregado_sessao` (sempre ativo,
        nao opt-in), entao contar SIGNAL cru misturaria os dois nesta
        classe. Ver a docstring do modulo."""

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.n_defesa_disparos = 0
            self.n_corte_disparos = 0

        def _defesa_deve_fechar(self, pos, bar):
            disparou = super()._defesa_deve_fechar(pos, bar)
            if disparou:
                self.n_defesa_disparos += 1
            return disparou

        def _corte_persistencia_deve_fechar(self, pos, bar):
            disparou = super()._corte_persistencia_deve_fechar(pos, bar)
            if disparou:
                self.n_corte_disparos += 1
            return disparou

    symbol = spec["symbol"]
    locked = _bars_do_processo(symbol)
    bars = locked.in_sample() if spec["janela"] == "IS" else locked.out_of_sample()
    profile = profile_for(symbol)

    if bars.empty:
        raise SystemExit(f"[{spec['rotulo']}] janela vazia -- sem dado local para {symbol!r}")
    preco_ref = float(bars.iloc[0]["open"])
    capital = capital_minimo_brl(preco_ref)

    kwargs: dict = dict(symbol=symbol)
    if spec["mecanismo"] == "defesa_recuo":
        kwargs.update(defesa_ativa=True, defesa_gatilho_stop_pct=spec["param1"],
                      defesa_alvo_proximidade_pct=spec["param2"])
    elif spec["mecanismo"] == "corte_persistencia":
        kwargs.update(corte_persistencia_ativo=True, corte_persistencia_min_barras=spec["param1"],
                      corte_persistencia_frac_adverso=spec["param2"])
    strat = _GremahInstrumentado(**kwargs)
    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )

    resultado = run_intraday_backtest(bars, strat, cfg)
    n_disparos = strat.n_defesa_disparos if spec["mecanismo"] == "defesa_recuo" else (
        strat.n_corte_disparos if spec["mecanismo"] == "corte_persistencia" else 0)
    pulou = len(resultado.sessoes_puladas_por_capital)

    extras = {
        "mecanismo": spec["mecanismo"],
        "param1": "—" if spec["param1"] is None else num_br(spec["param1"], 2),
        "param2": "—" if spec["param2"] is None else num_br(spec["param2"], 2),
        "n_disparos": str(n_disparos),
        "pulou": str(pulou),
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
        symbol=symbol, janela=spec["janela"], mecanismo=spec["mecanismo"],
        param1=spec["param1"], param2=spec["param2"], capital=capital,
        n_disparos=n_disparos, pulou=pulou,
    )
    return buf.getvalue(), campos


def _n_workers(n_tarefas: int) -> int:
    """Reduzido de proposito -- a maquina roda robos de day trade/swing AO
    VIVO com dinheiro real (`dev.bat`). Nunca mais que 6."""
    return max(1, min(n_tarefas, 6, os.cpu_count() or 4))


def main() -> None:
    from backtest.intraday.report import LinhaResultado, cabecalho, num_br, tabela

    t0 = time.perf_counter()
    specs = _monta_specs()
    n_workers = _n_workers(len(specs))
    print(f"[gremah_defesa_corte_sweep] {len(specs)} tarefas "
          f"({len(SYMBOLS)} simbolos x 2 janelas x 19 variantes), "
          f"{n_workers} processos", flush=True)
    print(cabecalho(EXTRAS), flush=True)

    resultados: dict[str, dict] = {}
    concluidos = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            concluidos += 1
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados[futures[future]] = campos
            print(f"[gremah_defesa_corte_sweep] {concluidos}/{len(specs)} concluido(s) "
                  f"({futures[future]})", flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[gremah_defesa_corte_sweep] motor: {dt:.1f}s em {n_workers} processos\n")

    print("=" * 90)
    print("AVISO METODOLOGICO (repetido -- nao e' opcional): a janela OOS "
          "(>=2026-06-13) de PMAM3/KLBN3 ja' foi espiada antes (geometria em "
          "ticks confirmada 2026-08-26, capacidade de caixa e filtro de "
          "qualidade de entrada depois). Um resultado bom no OOS abaixo e' "
          "evidencia MAIS FRACA do que um OOS genuinamente nunca visto.")
    print("=" * 90)

    for symbol in SYMBOLS:
        for janela in ("IS", "OOS"):
            campos_janela = [c for c in resultados.values()
                              if c["symbol"] == symbol and c["janela"] == janela]
            baseline = next(c for c in campos_janela if c["mecanismo"] == "baseline")
            defesa = [c for c in campos_janela if c["mecanismo"] == "defesa_recuo"]
            corte = [c for c in campos_janela if c["mecanismo"] == "corte_persistencia"]

            print(f"\n{'#'*90}\n{symbol} -- janela {janela} -- capital "
                  f"R${br(baseline['capital'])} (preco de referencia do inicio da janela)\n{'#'*90}")

            linhas = [LinhaResultado(
                variante=c["variante"], liquido_brl=c["liquido_brl"], maxdd_brl=c["maxdd_brl"],
                win_rate_pct=c["win_rate_pct"], trades=c["trades"], pregoes=c["pregoes"],
                retorno_pct=c["retorno_pct"], maxdd_pct=c["maxdd_pct"],
                capital_final=c["capital_final"], extras=c["extras"], aviso=c["aviso"],
            ) for c in [baseline] + defesa + corte]
            print(tabela(linhas, EXTRAS))

            n_defesa_disparos_total = sum(c["n_disparos"] for c in defesa)
            n_corte_disparos_total = sum(c["n_disparos"] for c in corte)
            melhor_defesa = max(defesa, key=lambda c: c["liquido_brl"]) if defesa else None
            melhor_corte = max(corte, key=lambda c: c["liquido_brl"]) if corte else None

            print(f"\n[diagnostico {symbol} {janela}] baseline: liquido=R${br(baseline['liquido_brl'])} "
                  f"({baseline['trades']} trades, {baseline['pulou']} pregoes pulados por capital)")
            print(f"[diagnostico {symbol} {janela}] defesa_recuo: SOMA de disparos na grade inteira "
                  f"(9 combos) = {n_defesa_disparos_total} -- "
                  f"{'CONFIRMA degenerescencia (0 disparos em toda a grade)' if n_defesa_disparos_total == 0 else 'NAO degenerado -- houve disparo real'}")
            if melhor_defesa is not None:
                print(f"    melhor combo defesa_recuo no liquido: g{melhor_defesa['param1']*100:.0f}% "
                      f"p{melhor_defesa['param2']*100:.0f}% -> liquido=R${br(melhor_defesa['liquido_brl'])} "
                      f"(vs baseline R${br(baseline['liquido_brl'])}), {melhor_defesa['n_disparos']} disparos")
            print(f"[diagnostico {symbol} {janela}] corte_persistencia: SOMA de disparos na grade "
                  f"inteira (9 combos) = {n_corte_disparos_total}")
            if melhor_corte is not None:
                print(f"    melhor combo corte_persistencia no liquido: m{melhor_corte['param1']} "
                      f"f{melhor_corte['param2']*100:.0f}% -> liquido=R${br(melhor_corte['liquido_brl'])} "
                      f"(vs baseline R${br(baseline['liquido_brl'])}), {melhor_corte['n_disparos']} disparos")

    print(f"\n{'='*90}\nAVISO METODOLOGICO (repetido de novo, de proposito): qualquer numero "
          "'bom' de OOS acima descreve uma janela ja' espiada antes. Trate como confirmacao mais "
          "fraca do que um OOS nunca visto, nao como validacao independente.")
    print(f"\n[gremah_defesa_corte_sweep] total: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
