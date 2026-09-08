"""IS/OOS da `WdoGridReloadMaker` na config EXATA de producao, na base de
tick CORRIGIDA (2026-09-07) -- fecha o buraco de medicao descrito abaixo.

## Por que esta medicao nao existia ainda

Todo o historico de validacao IS/OOS deste robo (R$148,89/pregao combinado,
89% de retencao, 30/30 blocos positivos -- a razao de ele ser TOP-1, ver
`strategy.daytrade.registry`) foi medido em DUAS bases hoje conhecidas como
furadas:

1. `data/raw_ticks/WDO_A_.parquet` (canonico) faltava 19,3% dos minutos de
   pregao (63 lacunas de ~3h, concentradas de manha) -- regenerado em
   2026-09-07 (16.624.744 -> 21.524.225 ticks, 126 -> 130 pregoes).
2. `data/raw_ticks/WDO_A_f1.parquet` (o recorte que ESTE robo consome) tinha
   um SEGUNDO bug de fuso -- indice rotulado 3h cedo, cada pregao comecava
   as 11:58 BRT na mediana em vez de 09:00 -- regenerado no mesmo dia a
   partir do canonico ja corrigido (4.011.197 -> 20.646.379 ticks,
   cobertura de minuto de pregao 38,2% -> 100,0%). Os DIAS de IS/OOS
   ficaram INTACTOS de proposito (IS: 72 dias, 2026-02-27..2026-06-12; OOS:
   51 dias, 2026-06-15..2026-08-25, 2 deles fallback M1) -- o split
   congelado e' decisao do dono e nao se mexe ao reparar dado.

Alem disso, a geometria de producao MUDOU desde as medicoes antigas: era
T1/S16, hoje e' T2/S16 (2026-09-04, item 4.8 de LICOES_DE_PRODUCAO.md --
deslize de 1 tick no alvo nativo zerava o lucro do trade com alvo de 1
tick). Resultado: nao existia nenhuma medicao IS/OOS da geometria que vai
operar, na base corrigida. E' esse buraco que este script fecha.

## Divergencia achada entre o pedido desta rodada e o codigo

O pedido descreve a config de producao como profit_ticks=2, stop_ticks=16,
level_spacing_ticks=1, reancora_min_segundos=10.0, reancora_min_ticks=1,
max_trades_per_side=200, trailing_ativo=False, gate_atividade_ativo=False,
reanchor_mode=default -- todos batem, um a um, os defaults de
`WdoGridReloadMaker.__init__` (conferido linha a linha antes de rodar).
MAS o caminho que `scripts/run_live.py::build_intraday` de fato usa
(`strategy.daytrade.registry.get_daytrade_robot`) tambem aplica
`_KWARGS_PADRAO["wdo_grid_reload_maker"]`, que LIGA dimensionamento
DINAMICO por capital -- `margin_per_contract_brl=150.0`,
`hard_cap_contratos=5`, `risco_pct_por_trade=0.01`, `point_value_brl=10.0`
(decisao do dono em 2026-08-29, memoria `wdo-dinamico-producao-2026-08-29`)
-- e isto NAO estava na lista de 8 parametros do pedido. Este script usa
`get_daytrade_robot(...)` (a config REAL que roda ao vivo), nunca uma
reconstrucao manual so' com os 8 parametros listados -- ver o print no topo
de `main()` para os kwargs completos usados, e a coluna extra `qtd_max`
para conferir se o caixa acumulado ao longo da janela chegou a destravar
mais de 1 contrato (com R$375 -- exatamente o piso -- o teto por margem/
risco arredonda pra 0 e o `max(1, ...)` da propria estrategia mantem 1
contrato enquanto o caixa nao sobra de verdade; ver
`wdof1_sobrevivencia_capital_baixo_2026_08_29.py`).

## As duas linhas de cada tabela

`T2/S16 (producao atual)`: kwargs de `get_daytrade_robot(...)`, sem
sobrescrever nada -- a config que vai operar dinheiro real.
`T1/S16 (referencia)`: OS MESMOS kwargs, so' `profit_ticks=1` sobrescrito --
isola o efeito da troca de alvo (o motivo real foi deslize de execucao,
nao backtest) sem misturar com o freio de cadencia/reancoragem continua,
que sao defaults de classe iguais nos dois lados.

## Base de dados

`data/raw_ticks/WDO_A_f1.parquet`, coluna `janela` ja rotulada
("IS"/"OOS"). Split INTACTO -- nao mexido aqui.

## Extras reportados

`pior_janela_60s` (teto ao vivo e' 30, `live.intraday_runtime.
MAX_ENVIOS_POR_MINUTO`) -- pior contagem, numa janela ROLANTE de 60s, de
`EnterLimit` emitidas por `on_bar` (armamento novo, reprecificacao e rearme
pos-recusa contam igual: cada uma e' um `place_limit` ao vivo, mesma
grandeza que `_check_cadencia_de_ordens` mede ao vivo). `saida_alvo`/
`saida_stop`/`saida_flatten` -- contagem de `IntradayTrade.exit_reason`.
`pregoes_sem_trade` -- pregoes da janela sem nenhum trade fechado.
`qtd_max` -- maior `quantity` visto num trade (sanity check do
dimensionamento dinamico no capital real).

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`), uma
tarefa por (janela, variante) -- 4 no total. Parquet lido 1x por PROCESSO
(cache por janela, mesmo padrao de `wdof1_gate_atividade_sweep_2026_09_07.
py`). Cada tarefa monta a linha formatada dela dentro de
`contextlib.redirect_stdout` (mesmo padrao de
`gremah_defesa_corte_sweep_2026_09_03.py`) e devolve o texto pronto; o
processo PAI imprime assim que o `future` completa -- nenhuma tarefa espera
as outras para falar. A tabela ordenada (producao primeiro, depois
referencia) vem depois, por janela.

Uso: `python -u scripts/daytrade/wdof1_producao_is_oos_2026_09_07.py`

## RESULTADO MEDIDO (2026-09-08, base ja corrigida, capital R$375,00)

    janela variante         retorno    liquido R$   win%  trades trd/dia  p60  alvo  stop  flat  s/trade  qtd_max
    IS     T2 (producao)  91.961,3%    344.855,00  94,2%   19835   275,5   23 18688  1102    45        0        5
    IS     T1 (ref.)     113.899,2%    427.122,00  98,8%   28782   399,8   36 28425   357     0        0        5
    OOS    T2 (producao)     -20,3%        -76,00  50,0%       2     0,0    6     1     1     0       50        1
    OOS    T1 (ref.)      74.331,3%    278.742,50  98,9%   19786   388,0   39 19562   222     2        0        5

LEIA ISTO ANTES DE USAR QUALQUER NUMERO ACIMA:

1. **A linha OOS de producao esta CENSURADA, nao e' um resultado negativo.**
   Ela fez 2 trades em 51 pregoes -- 1 alvo e 1 stop -- e parou. Nao ha'
   edge medido ali, nem para bem nem para mal. O mecanismo esta em
   `wdo_grid_reload_maker` (docstring do modulo, secao "REARME APOS
   RECUSA"): o piso para abrir 1 contrato e' `150 x 2,0 x 1,25 = R$375,00`
   e o capital de partida e' EXATAMENTE R$375,00. Um stop custa
   `16 x 0,5 x 10 = R$80,00`. R$375 - R$76 = R$299 < R$375, entao o motor
   passa a recusar toda entrada com `capital_insuficiente` e o robo fica
   inerte pelos 50 pregoes restantes (`pregoes_sem_trade = 50`, `qtd_max`
   preso em 1 -- ele nunca teve caixa para 2 contratos).

2. **IS e OOS aqui nao sao duas medidas da mesma coisa; sao duas amostras
   de UMA moeda.** Comecando no piso exato, o robo precisa acumular R$80
   de lucro antes do primeiro stop para nao morrer -- a ~R$9,50 liquidos
   por alvo (2 ticks x R$5 menos corretagem), sao ~9 alvos. Com o win rate
   de 94,2% medido no IS, `0,942^9 ~= 58%`. O IS ganhou esse sorteio e
   composto ate' o teto de 5 contratos; o OOS perdeu no segundo trade. A
   diferenca entre as duas linhas NAO mede degradacao de edge fora da
   amostra -- mede o resultado de um Bernoulli em cada janela.

3. **Os retornos de 4 e 5 digitos sao artefato de composicao sobre um
   caixa minusculo, nao previsao.** R$375 -> R$345 mil em 72 pregoes sai
   de reinvestir tudo num robo que satura `max_trades_per_side` e cujo
   fill maker e' otimista por construcao (`target_fills_as_maker=True`).
   Servem para comparar T1 contra T2 sob a MESMA regra, nada alem disso.

4. **A linha T1 e' INEXEQUIVEL ao vivo, apesar de parecer melhor.**
   `pior_janela_60s` da' 36 (IS) e 39 (OOS), acima do teto de 30 de
   `live.intraday_runtime.MAX_ENVIOS_POR_MINUTO` -- ela teria ligado
   `disaster_halt` e calado o robo. T2 fica em 23 (IS) e 6 (OOS), dentro
   do teto. A troca T1->T2 foi decidida por deslize de execucao no TP
   nativo (item 4.8 de LICOES_DE_PRODUCAO.md), e esta medicao mostra que
   ela ainda traz de brinde a cadencia para dentro do limite.
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
#: (`get_daytrade_robot`) via kwargs, sobrescrevendo so' `profit_ticks` na
#: linha de referencia. Lista conferida contra o `__init__` do modulo antes
#: de rodar (ver a docstring deste arquivo para a divergencia achada).
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
          "pregoes_sem_trade", "qtd_max")

#: Kwargs que o REGISTRY liga por cima dos defaults de classe -- a
#: divergencia frente a lista do pedido (ver docstring do modulo).
_CAMPOS_DIVERGENTES = ("margin_per_contract_brl", "hard_cap_contratos",
                       "risco_pct_por_trade", "point_value_brl")

#: Parquet lido 1x por PROCESSO, dividido em IS/OOS -- cache por chave de
#: janela (mesmo padrao de `wdof1_gate_atividade_sweep_2026_09_07.py`).
_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars_do_processo(janela: str) -> pd.DataFrame:
    if not _DF_CACHE:
        df = pd.read_parquet(CACHE)
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
        ao vivo, ver a docstring do modulo). Nao muda nenhum comportamento
        herdado -- existe so' para medir `pior_janela_60s`."""

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

    extras = {
        "pior_janela_60s": str(_pior_janela_60s(strat.envios_ts)),
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        "saida_flatten": str(contagem.get("forced_flatten", 0)),
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "qtd_max": str(qtd_max),
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
            f"[wdof1_producao_is_oos] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from strategy.daytrade.registry import get_daytrade_robot

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs_producao = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    print("[wdof1_producao_is_oos] kwargs de producao "
          "(get_daytrade_robot('wdo_grid_reload_maker')):")
    for campo in CAMPOS_KWARGS:
        print(f"    {campo} = {kwargs_producao[campo]!r}")
    print("\n[wdof1_producao_is_oos] DIVERGENCIA vs a lista de 8 parametros do pedido: "
          + ", ".join(f"{c}={kwargs_producao[c]!r}" for c in _CAMPOS_DIVERGENTES))
    print("  -- dimensionamento DINAMICO por capital (registry._KWARGS_PADRAO, "
          "decisao 2026-08-29), nao mencionado na lista do pedido. Usado aqui "
          "via get_daytrade_robot(...) por ser o caminho REAL de "
          "scripts/run_live.py::build_intraday -- ver a coluna qtd_max.\n",
          flush=True)

    specs = []
    for janela in ("IS", "OOS"):
        specs.append(dict(janela=janela, profit_ticks_override=None,
                           rotulo=f"[{janela}] T2/S16 (producao atual)"))
        specs.append(dict(janela=janela, profit_ticks_override=1,
                           rotulo=f"[{janela}] T1/S16 (referencia antiga)"))

    n_workers = max(1, min(len(specs), os.cpu_count() or 4))
    print(f"[wdof1_producao_is_oos] capital real R${CAPITAL_REAL_BRL:.2f}, "
          f"{len(specs)} tarefas, {n_workers} processos\n", flush=True)

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
    print(f"\n[wdof1_producao_is_oos] motor: {dt_total:.1f}s em {n_workers} processos\n")

    from backtest.intraday.report import cabecalho, linha as linha_fmt

    for janela in ("IS", "OOS"):
        rotulos = [s["rotulo"] for s in specs if s["janela"] == janela]
        print(f"\n=== tabela {janela} (producao atual primeiro, depois "
              "referencia T1/S16) ===")
        print(cabecalho(EXTRAS))
        for rotulo in rotulos:
            print(linha_fmt(resultados[(janela, rotulo)], EXTRAS))


if __name__ == "__main__":
    main()
