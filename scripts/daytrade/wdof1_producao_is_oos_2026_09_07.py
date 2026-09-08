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

## T1 nao e' referencia -- nao meça (decisao do dono, 2026-09-08)

Este script MEDIU T1/S16 ao lado do T2 na primeira rodada. Nao mede mais, e
nenhum trabalho futuro deve reintroduzi-lo "so' como baseline". A razao nao
e' preferencia:

**T1 so' existe no backtest.** O alvo de 1 tick e' menor que o deslize que o
TP nativo sofre na corretora de verdade. Na 1a operacao real do robo
(entrada 5150,0 / alvo 5150,5 / saida 5150,0) o TP derrapou 1 tick e apagou
o bruto INTEIRO -- R$0,00 bruto, -R$0,50 de corretagem (item 4.8 de
`LICOES_DE_PRODUCAO.md`). Com alvo de 1 tick, 1 tick de deslize e' 100% do
ganho, entao a mesma geometria que o motor pinta como campea entrega
prejuizo no extrato.

**Consequencia que vale para toda a familia maker:** a varredura de 250
celulas de `profit_ticks x stop_ticks` que consagrou T1 rodou num motor que
NAO cobra deslize de TP. Ela nao escolheu a melhor geometria -- escolheu a
que melhor explora a otimizacao que falta no modelo de preenchimento. Um
otimo que mora no ponto onde o simulador e' mais otimista que a realidade
nao e' um otimo; e' o sintoma de um modelo incompleto. Enquanto o motor nao
cobrar esse deslize, alvo=1 nao e' candidato a nada.

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

## RODADA 1 (2026-09-08) -- INVALIDADA pelo portao de capital, mantida como
## registro do bug que ela revelou

    janela variante         retorno    liquido R$   win%  trades trd/dia  p60  alvo  stop  flat  s/trade  qtd_max
    IS     T2 (producao)  91.961,3%    344.855,00  94,2%   19835   275,5   23 18688  1102    45        0        5
    OOS    T2 (producao)     -20,3%        -76,00  50,0%       2     0,0    6     1     1     0       50        1

A linha OOS acima NAO e' resultado negativo -- e' CENSURA. Ela fez 2 trades
em 51 pregoes (1 alvo, 1 stop) e parou, porque o motor cobrava a pilha de
seguranca inteira (`150 x 2,0 x 1,25 = R$375`) a CADA entrada, inclusive
para o 1o contrato: um stop de R$80 sobre um caixa que comecou nos proprios
R$375 de partida derrubava o caixa para R$299 e toda entrada passava a ser
recusada com `capital_insuficiente`, em silencio, pelos 50 pregoes
restantes.

Isso foi corrigido em 2026-09-08 (commit `297bc6a`,
`strategy.daytrade.base.contracts_from_capital_operacional`): o piso cheio
e' INDICACAO DE PARTIDA, checada 1x no painel; depois disso manter 1
contrato exige so' a margem crua (R$150), e a pilha inteira volta a valer
para abrir o 2o em diante. **Os numeros acima sao da regra ANTIGA e nao
descrevem a estrategia** -- a rodada 2, abaixo, e' a que vale.

Duas ressalvas que sobrevivem a correcao e valem para qualquer rodada
deste script:

- **Retorno de 4-5 digitos e' artefato de composicao sobre caixa minusculo,
  nao previsao.** R$375 -> R$345 mil em 72 pregoes sai de reinvestir tudo
  num robo que satura `max_trades_per_side` e cujo fill maker e' otimista
  por construcao (`target_fills_as_maker=True`). Use valor absoluto por
  pregao e contagem de trades, nunca o percentual.
- **Partindo exatamente do piso, IS e OOS nao sao duas medidas da mesma
  coisa** -- a sequencia das primeiras operacoes domina o resto da janela.
  Ver item 6.15 de `LICOES_DE_PRODUCAO.md`.

## RODADA 2 (2026-09-08, apos `297bc6a`) -- so' T2, regra de capital nova

    janela liquido R$  MaxDD R$  win%  trades trd/dia  p60  alvo stop flat s/trade qtd_max zerou caixa_min
    IS     344.855,00  2.905,00 94,2%   19835   275,5   23 18688 1102   45       0       5   NAO    370,00
    OOS    135.618,50  2.650,00 94,4%    9446   185,2   42  8918  485   43       0       5   NAO    290,00

**A correcao mudou o OOS e NAO mudou o IS** -- e o par explica o porque. O
OOS foi de 2 trades / -R$76 / 50 pregoes inertes para 9.446 trades / 0
inertes; o IS saiu numericamente IDENTICO a RODADA 1, ate' a ultima casa.
Motivo: no IS o caixa REALIZADO nunca desceu abaixo dos R$375, entao o
portao antigo nunca mordeu ali. Confirma o enquadramento do item 6.15 --
o IS ganhou o sorteio das primeiras operacoes e nunca chegou perto do
piso; o OOS perdeu no 2o trade.

`caixa_min` MEDE PATRIMONIO, NAO O NUMERO QUE O PORTAO OLHA. A curva e'
`initial_capital + realized_pnl + unrealized_brl(close)` (`engine.py`), com
mark-to-market; o portao usa `initial_capital + realized_pnl`, SEM MTM. Por
isso o IS pode marcar `caixa_min = R$370,00` (abaixo dos R$375) sem que o
portao tenha recusado nada -- aquele fundo e' posicao aberta no vermelho,
nao caixa. Nao leia essas duas colunas como a mesma grandeza.

`zerou = NAO` nas duas janelas (`IntradayBacktestResult.wiped_out_at is
None`): o patrimonio nunca cruzou o zero. Mas ZERAR e PARALISAR sao modos
de falha diferentes, e a esta capitalizacao quem morde e' o segundo -- no
fundo do OOS a folga sobre o piso de sobrevivencia era de R$140, ~1,75
stops.

### BLOQUEIO DE PRODUCAO encontrado nesta rodada

`pior_janela_60s`: **42 no OOS**, contra `MAX_ENVIOS_POR_MINUTO = 30` de
`live.intraday_runtime` -- ao vivo isso liga `disaster_halt` e cala o robo
pelo resto do pregao. No IS da' 23, dentro do teto.

E' TAIL, NAO REGIME, e o par IS/OOS prova: o IS tem MAIS fills por pregao
(275,5 contra 185,2) e pico MENOR (23 contra 42). Logo o pico nao e' funcao
da taxa media de preenchimento -- e' um minuto especifico de rajada em
algum pregao do OOS. Nao conclua "o robo estoura sempre"; ele estourou pelo
menos uma vez em 51 pregoes, e uma vez ja' basta para calar o dia.

De onde vem: `reancora_min_segundos` cobre reprecificacao e rearme
pos-RECUSA e, por desenho, NAO cobre o rearme pos-FILL (ver a docstring de
`reancora_min_segundos` em `wdo_grid_reload_maker`: freia-lo "seria trocar
o desenho"). A 10s os dois caminhos freados somam no MAXIMO 12 envios/min,
entao >=30 dos 42 sao obrigatoriamente do caminho pos-fill. Isso e'
aritmetica dos tetos, nao medicao direta -- o script conta `EnterLimit` sem
distinguir origem; instrumentar por origem e' o passo seguinte se a decisao
for mexer no detector.

Por que a calibracao de `reancora_min_segundos=10` nao viu isso: ela rodou
pregao a pregao com caixa REPOSTO em R$375 todo dia, sob a regra de capital
ANTIGA -- ou seja, em cada pregao o robo operava ate' o primeiro stop e
depois so' rearmava a 1x/10s. Media um robo que parava cedo todo dia.
Nenhum valor da grade 6-20s cobre um caminho que o freio nao percorre,
entao NAO re-varri: seria queimar CPU. A decisao (contar so' envios
improdutivos no detector, subir o teto, ou frear o pos-fill) e' do dono.
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
          "pregoes_sem_trade", "qtd_max", "zerou", "caixa_min")

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

    # "o caixa chegou a zerar?" -- `wiped_out_at` e' o campo AUTORITATIVO
    # (patrimonio realizado + mark-to-market <= 0; o motor PARA de simular a
    # partir dai). `caixa_min` complementa: o menor ponto da curva de
    # patrimonio, para saber a que distancia do zero a coisa passou, e nao
    # so' se cruzou. Os dois juntos respondem a pergunta -- `wiped_out_at`
    # sozinho nao diz se passou perto.
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

    # T1 NAO entra (decisao do dono, 2026-09-08 -- ver "T1 nao e' referencia"
    # no topo do modulo). Medir uma geometria que o motor sabe simular e a
    # corretora nao sabe executar so' produz uma coluna bonita e enganosa.
    specs = []
    for janela in ("IS", "OOS"):
        specs.append(dict(janela=janela, profit_ticks_override=None,
                           rotulo=f"[{janela}] T2/S16 (producao atual)"))

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
        print(f"\n=== tabela {janela} ===")
        print(cabecalho(EXTRAS))
        for rotulo in rotulos:
            print(linha_fmt(resultados[(janela, rotulo)], EXTRAS))


if __name__ == "__main__":
    main()
