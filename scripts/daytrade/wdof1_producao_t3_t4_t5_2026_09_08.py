"""IS/OOS da `WdoGridReloadMaker` medindo T3, T4 e T5 (profit_ticks=3/4/5)
ao lado do T2 de producao, na mesma base de tick CORRIGIDA (2026-09-07) e no
mesmo split IS/OOS congelado usado por
`wdof1_producao_is_oos_2026_09_07.py` -- este script e' o mesmo metodo,
so' com mais variantes de `profit_ticks` na grade.

## Objetivo

`wdof1_producao_is_oos_2026_09_07.py` fechou o buraco de medicao do T2
(producao atual) na base corrigida, apos a correcao do portao de capital em
`297bc6a`. O dono quer agora saber se afastar o alvo de T2 para T3/T4/T5
muda o resultado nas MESMAS janelas IS/OOS congeladas, com a MESMA config
real de producao (so' `profit_ticks` varia) e o MESMO capital real de
partida (R$375). T2 entra como referencia ao lado das novas variantes, nao
e' remedido de forma diferente.

## T1 esta PROIBIDO -- decisao do dono, 2026-09-08 (nao negociavel)

Este sweep comeca em T2. `profit_ticks=1` NUNCA entra em nenhuma medicao do
WDO F1 nem da familia maker -- nem como candidato, nem como baseline, nem
como "linha de referencia". O motor nao modela o deslize que o TP nativo
sofre na corretora real, e um alvo de 1 tick e' MENOR que esse deslize: na
1a operacao real do robo (entrada 5150,0 / alvo 5150,5 / saida 5150,0) o TP
derrapou o tick inteiro e apagou o bruto inteiro -- R$0,00 bruto, -R$0,50
de corretagem (item 4.8 de `LICOES_DE_PRODUCAO.md`). A grade de 250 celulas
que consagrou T1 rodou nesse mesmo motor sem custo de deslize -- ela nao
escolheu a melhor geometria, escolheu a que mais explora a lacuna do
modelo de preenchimento. Nao reintroduzir T1 aqui "so' para comparar".

## Metodo (identico ao script de referencia)

- `strategy.daytrade.registry.get_daytrade_robot("wdo_grid_reload_maker")`
  para pegar a config REAL de producao -- isso inclui o dimensionamento
  DINAMICO por capital que o registry liga por cima dos defaults da classe
  (`margin_per_contract_brl=150.0`, `hard_cap_contratos=5`,
  `risco_pct_por_trade=0.01`, `point_value_brl=10.0`, decisao
  2026-08-29). Os kwargs completos vem de `CAMPOS_KWARGS` copiados da
  instancia de producao; so' `profit_ticks` e' sobrescrito por variante.
- `CAPITAL_REAL_BRL = 375.0` (margem R$150 x buffer 2.0 x reserva 1.25 --
  NUNCA um capital nocional arbitrario).
- `data/raw_ticks/WDO_A_f1.parquet`, coluna `janela` ja rotulada
  ("IS"/"OOS"). Split CONGELADO -- os dias de IS/OOS nao sao mexidos aqui.
- `ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`), uma
  tarefa por (janela, variante) -- 8 no total (T2/T3/T4/T5 x IS/OOS).
  Parquet lido 1x por PROCESSO (cache por janela). Cada tarefa monta a
  linha formatada dela dentro de `contextlib.redirect_stdout` e devolve o
  texto pronto; o processo PAI imprime assim que o `future` completa --
  nenhuma tarefa espera as outras para falar.
- Tabela de saida via `backtest/intraday/report.py` (`linha_de_resultado`,
  `cabecalho`, `linha`) com as mesmas colunas extras do script de
  referencia: `pior_janela_60s` (teto ao vivo e' 30,
  `live.intraday_runtime.MAX_ENVIOS_POR_MINUTO` -- estourar liga
  `disaster_halt`), `saida_alvo`/`saida_stop`/`saida_flatten`
  (`IntradayTrade.exit_reason`), `pregoes_sem_trade` (janela censurada --
  nao ler `liquido` sem olhar esta coluna), `qtd_max` (sanity check do
  dimensionamento dinamico), `zerou`/`caixa_min` (risco de ruina --
  `caixa_min` mede PATRIMONIO com mark-to-market, nao o numero que o
  portao de capital olha; ver a docstring do script de referencia para o
  detalhe).

Uso: `python -u scripts/daytrade/wdof1_producao_t3_t4_t5_2026_09_08.py`
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"

#: Capital REAL do slot ao vivo (WDO@, R$375 = margem R$150 x buffer 2.0 x
#: reserva 1.25 -- ver LICOES_DE_PRODUCAO.md/CLAUDE.md, "capital inicial
#: nunca arbitrario"), NAO um capital nocional de calibracao.
CAPITAL_REAL_BRL = 375.0

#: Todo parametro de `WdoGridReloadMaker.__init__` (menos `self`), na ordem
#: declarada -- usado para clonar a instancia de PRODUCAO
#: (`get_daytrade_robot`) via kwargs, sobrescrevendo so' `profit_ticks` por
#: variante.
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

EXTRAS = ("pior_janela_60s", "saida_alvo", "saida_stop", "saida_flatten",
          "pregoes_sem_trade", "qtd_max", "zerou", "caixa_min")

#: Kwargs que o REGISTRY liga por cima dos defaults de classe.
_CAMPOS_DIVERGENTES = ("margin_per_contract_brl", "hard_cap_contratos",
                       "risco_pct_por_trade", "point_value_brl")

#: Parquet lido 1x por PROCESSO, dividido em IS/OOS -- cache por chave de
#: janela (mesmo padrao do script de referencia).
_DF_CACHE: dict[str, pd.DataFrame] = {}


#: Colunas realmente usadas -- o parquet tambem carrega `fonte` (str) e
#: `dia` (object), que soh' sozinhas somam ~1,07 GB dos ~2,28 GB do arquivo
#: cheio (medido com `df.memory_usage(deep=True)`). Ler so' estas 6 evita
#: pagar esse custo em CADA processo do pool -- ver a nota de memoria no
#: `main()` sobre por que este script, com 8 tarefas (o dobro do script de
#: referencia, que tinha so' 2), nao pode usar 1 processo por tarefa.
_COLUNAS = ("open", "high", "low", "close", "volume", "janela")


def _bars_do_processo(janela: str) -> pd.DataFrame:
    if not _DF_CACHE:
        df = pd.read_parquet(CACHE, columns=list(_COLUNAS))
        for j in ("IS", "OOS"):
            sub = df[df["janela"] == j]
            _DF_CACHE[j] = sub[["open", "high", "low", "close", "volume"]].sort_index()
    return _DF_CACHE[janela]


def _pior_janela_60s(envios_ts: list) -> int:
    """Pior contagem, numa janela ROLANTE de 60s, de `EnterLimit` emitidas
    -- mesma grandeza que `live.intraday_runtime.MAX_ENVIOS_POR_MINUTO`
    (30) limita ao vivo. `0` se o candidato nunca armou nada."""
    if not envios_ts:
        return 0
    serie = pd.Series(1, index=pd.DatetimeIndex(sorted(envios_ts)))
    return int(serie.rolling("60s").sum().max())


def _roda_uma(spec: dict):
    """Executado no processo FILHO. Devolve `(janela, rotulo, LinhaResultado,
    texto_pronto_pra_imprimir, dt_segundos)`."""
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado
    from strategy.daytrade.base import EnterLimit
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    class _ComContadorEnvios(WdoGridReloadMaker):
        """Mesma classe de producao -- so' registra o timestamp de toda
        `EnterLimit` emitida por `on_bar` (armamento novo, reprecificacao
        OU rearme pos-recusa contam igual -- cada uma e' um `place_limit`
        ao vivo). Nao muda nenhum comportamento herdado -- existe so' para
        medir `pior_janela_60s`."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.envios_ts: list[pd.Timestamp] = []

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            actions = super().on_bar(ts, bar, positions, session_pnl_brl)
            for action in actions:
                if isinstance(action, EnterLimit):
                    self.envios_ts.append(pd.Timestamp(ts))
            return actions

    bars = _bars_do_processo(spec["janela"])

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    if spec["profit_ticks_override"] is not None:
        kwargs["profit_ticks"] = spec["profit_ticks_override"]
    strat = _ComContadorEnvios(**kwargs)

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )

    t0 = time.perf_counter()
    resultado = run_intraday_backtest(bars, strat, cfg)
    dt = time.perf_counter() - t0

    trades = list(resultado.trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    qtd_max = max((t.quantity for t in trades), default=0)

    # "o caixa chegou a zerar?" -- `wiped_out_at` e' o campo AUTORITATIVO
    # (patrimonio realizado + mark-to-market <= 0; o motor PARA de simular a
    # partir dai). `caixa_min` complementa: o menor ponto da curva de
    # patrimonio, para saber a que distancia do zero a coisa passou, e nao
    # so' se cruzou.
    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "pior_janela_60s": str(_pior_janela_60s(strat.envios_ts)),
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        "saida_flatten": str(contagem.get("forced_flatten", 0)),
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "qtd_max": str(qtd_max),
        "zerou": ("NAO" if resultado.wiped_out_at is None
                  else str(resultado.wiped_out_at)),
        "caixa_min": f"{caixa_min:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, CAPITAL_REAL_BRL,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{spec['janela']}, {dt:5.1f}s] {linha(item, EXTRAS)}", flush=True)
    return spec["janela"], spec["rotulo"], item, buf.getvalue(), dt


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_producao_t3_t4_t5] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from strategy.daytrade.registry import get_daytrade_robot

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs_producao = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    print("[wdof1_producao_t3_t4_t5] kwargs de producao "
          "(get_daytrade_robot('wdo_grid_reload_maker')):")
    for campo in CAMPOS_KWARGS:
        print(f"    {campo} = {kwargs_producao[campo]!r}")
    print("\n[wdof1_producao_t3_t4_t5] dimensionamento DINAMICO por capital "
          "(registry._KWARGS_PADRAO, decisao 2026-08-29) ligado por cima dos "
          "defaults de classe: " + ", ".join(
              f"{c}={kwargs_producao[c]!r}" for c in _CAMPOS_DIVERGENTES)
          + " -- usado aqui via get_daytrade_robot(...) por ser o caminho "
          "REAL de scripts/run_live.py::build_intraday.\n", flush=True)

    # T1 NAO entra (decisao do dono, 2026-09-08 -- proibicao permanente,
    # ver docstring do modulo). A grade comeca em T2 (producao/referencia)
    # e sobe para T3/T4/T5.
    variantes = (
        (None, "T2/S16 (producao)"),
        (3, "T3/S16"),
        (4, "T4/S16"),
        (5, "T5/S16"),
    )
    specs = []
    for janela in ("IS", "OOS"):
        for profit_ticks_override, nome in variantes:
            specs.append(dict(janela=janela,
                               profit_ticks_override=profit_ticks_override,
                               rotulo=f"[{janela}] {nome}"))

    # Retomada apos interrupcao (ex.: processo pai morto pelo host antes das
    # 8 tarefas terminarem, cada tarefa IS leva ~44min sozinha). Default e'
    # "" (roda as 8) -- so' usado manualmente pra nao repetir tarefa ja'
    # concluida e' impressa em rodada anterior, ver o rotulo exato no log.
    _skip = {r.strip() for r in os.environ.get("WDOF1_SKIP_ROTULOS", "").split(",") if r.strip()}
    if _skip:
        specs = [s for s in specs if s["rotulo"] not in _skip]
        print(f"[wdof1_producao_t3_t4_t5] retomada -- pulando {sorted(_skip)}\n",
              flush=True)

    # ATENCAO -- teto de processos e' de MEMORIA, nao de CPU (achado
    # rodando este script: 8 processos travaram a maquina por >30min e
    # morreram com ArrayMemoryError). Cada processo le' o parquet 1x
    # (`_bars_do_processo`, cache por PROCESSO) -- mesmo com so' as 6
    # colunas usadas (`_COLUNAS`), o pico transiente por processo (df
    # cheiro + os dois subconjuntos IS/OOS vivos ao mesmo tempo) fica perto
    # de 2,2 GB, e o script de referencia (2 tarefas, 2 processos) e' o
    # unico ponto ja' confirmado seguro. Este script tem 8 tarefas -- usar
    # `min(len(specs), cpu_count)` (aqui, 8) tentaria 8 leituras
    # simultaneas do parquet inteiro e repete o OOM. `MAX_WORKERS_MEMORIA`
    # limita o pool ao mesmo teto de concorrencia do script de referencia
    # (2 processos, unico ponto ja' confirmado seguro nesta maquina);
    # tarefas em excesso apenas ESPERAM um processo livre
    # (`ProcessPoolExecutor` enfileira sozinho) e reaproveitam o cache
    # daquele processo pras tarefas seguintes -- so' os `MAX_WORKERS_MEMORIA`
    # primeiros processos pagam a leitura do parquet.
    MAX_WORKERS_MEMORIA = 2
    n_workers = max(1, min(len(specs), os.cpu_count() or 4, MAX_WORKERS_MEMORIA))
    print(f"[wdof1_producao_t3_t4_t5] capital real R${CAPITAL_REAL_BRL:.2f}, "
          f"{len(specs)} tarefas, {n_workers} processos (teto de memoria, "
          f"nao de CPU -- ver comentario acima)\n", flush=True)

    t0 = time.perf_counter()
    resultados: dict = {}
    concluidos = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            janela, rotulo, item, texto_pronto, dt = future.result()
            resultados[(janela, rotulo)] = item
            concluidos += 1
            print(f"[{concluidos}/{len(specs)}] {texto_pronto}", end="", flush=True)
    dt_total = time.perf_counter() - t0
    print(f"\n[wdof1_producao_t3_t4_t5] motor: {dt_total:.1f}s em {n_workers} processos\n")

    from backtest.intraday.report import cabecalho, linha as linha_fmt

    for janela in ("IS", "OOS"):
        rotulos = [s["rotulo"] for s in specs if s["janela"] == janela]
        print(f"\n=== tabela {janela} ===")
        print(cabecalho(EXTRAS))
        for rotulo in rotulos:
            print(linha_fmt(resultados[(janela, rotulo)], EXTRAS))


if __name__ == "__main__":
    main()
