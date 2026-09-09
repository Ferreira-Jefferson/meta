"""PREVIA: preenchimento favoravel da ordem-limite + ancoragem de alvo/stop no
preco REALMENTE preenchido (WDO F1, T2 e T3, 10 primeiros pregoes do IS).

## A pergunta do dono

"Hoje o robo calcula alvo e stop a partir do NIVEL PEDIDO da ordem-limite. E
se ele considerasse o preco em que ENTROU DE FATO?"

## Por que a pergunta so' faz sentido com DOIS flags, nao um

No motor de ate' 2026-09-08 a resposta e' "nada muda" -- e nao por acaso:
`_resolve_limit_fills` preenchia toda `EnterLimit` simulada EXATAMENTE em
`order.limit_price`, e a posicao nascia com `initial_stop`/`initial_target`
crus. Fill == nivel, entao ancorar no fill e' ancorar no nivel: NO-OP por
construcao. Este script CONFIRMA isso rodando (as duas primeiras linhas da
tabela tem de sair identicas), em vez de so' afirmar por leitura de codigo.

Para a pergunta ter conteudo, o fill precisa antes poder SAIR do nivel. Dai o
primeiro flag:

  * `IntradayBacktestConfig.limit_fill_at_bar_open` -- a barra que ABRE do
    lado bom do nivel preenche na ABERTURA (compra `min(limit_price,
    bar.open)`, venda `max(...)`), que e' o que a corretora faz de verdade:
    ninguem vende a 5,480 e recebe 5,500 sem motivo. O motor sempre assumiu
    o nivel exato -- premissa PESSIMISTA nesse caso especifico.
  * `IntradayBacktestConfig.anchor_exits_at_fill` -- a proposta do dono:
    alvo e stop transladam para o fill, preservando a DISTANCIA declarada
    pela estrategia (`initial_* - limit_price`). A distancia sai da propria
    ordem, nunca de `profit_ticks`/`stop_ticks`: o motor nao conhece os
    parametros da estrategia e nao pode conhecer (regra 2 de AGENTS.md).

Os dois ficam DESLIGADOS por default -- eles mudam a geometria de toda
medicao ja' feita neste repo, e ligar por default tornaria numero novo
incomparavel com numero antigo sem ninguem perceber.

## Escopo desta rodada: PREVIA, nao veredito

Ordem do dono, 2026-09-08: 10 pregoes, so' IS, so' T2 e T3. O objetivo e'
(1) provar que os dois flags funcionam no motor de verdade e (2) dimensionar
se a discussao importa. O numero que decide isso e' a FREQUENCIA com que o
preco atravessa o nivel: se ela for perto de zero, a mudanca e' irrelevante
por construcao e nao ha' o que medir em janela cheia.

10 pregoes NAO respondem "T2 ou T3 da lucro" -- nem se pretende. Ver "Como
LER" abaixo.

## As celulas

  1. `T2 nivel  (motor de hoje)`      -- fill no nivel, ancora no nivel.
  2. `T2 fill   (NO-OP esperado)`     -- fill no nivel, ancora no fill.
     IDENTICA a (1) se o motor antigo de fato so' preenche no nivel.
  3. `T2 favoravel + nivel`           -- fill na abertura, ancora no nivel.
  4. `T2 favoravel + FILL (DONO)`     -- fill na abertura, ancora no fill.
  5/6. o mesmo par (3)/(4) com T3.

O contraste que responde a pergunta e' (3) contra (4), e (5) contra (6): o
preenchimento favoravel ligado nos dois lados, mudando SO' a ancoragem.
`profit_ticks=1` (T1) nao entra em lugar nenhum -- ordem do dono, ver
CLAUDE.md.

## Como LER esta tabela

`liquido R$` aqui NAO e' veredito, por duas razoes empilhadas. (a) 10
pregoes com capital R$375 (o piso EXATO de 1 contrato do WDO@) e' o regime
CENSURADO de sempre: um stop de R$80 derruba o caixa abaixo do piso de
reabertura e o robo fica inerte -- olhe `trades` e `pregoes_sem_trade` ANTES
do liquido (item 6.15 de LICOES_DE_PRODUCAO.md). (b) 10 pregoes e' amostra
de smoke test.

O que esta rodada tem de conclusivo sao os extras de fill:
`fills_melhor`/`%_melhor`/`ticks_med`/`ticks_max` -- eles medem o MERCADO
(com que frequencia a barra atravessa o nivel armado), nao a estrategia, e
por isso ja' dizem se vale medir mais.

## Extras

  * `fills`        -- quantas entradas preencheram na run.
  * `fills_melhor` -- quantas delas sairam MELHOR que o nivel pedido.
  * `%_melhor`     -- a fracao acima, em %.
  * `ticks_med`    -- ganho medio de preco, em TICKS, sobre os fills que
                      sairam melhor (0 nas linhas sem preenchimento favoravel).
  * `ticks_max`    -- o maior desses ganhos.
  * `saida_alvo`/`saida_stop`/`pregoes_sem_trade`/`caixa_min` -- mesmas
    definicoes de `wdof1_deslize_alvo_is_oos_2026_09_08.py`.

Uso: `python -u scripts/daytrade/wdof1_fill_favoravel_ancoragem_previa_2026_09_08.py`
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

SYMBOL = "WDO@"

#: Capital REAL do slot ao vivo (WDO@) -- margem R$150 x buffer 2,0 x reserva
#: 1,25. Ordem expressa do dono (2026-09-08): nada de bateria com capital de
#: folga, ele nao tem esse capital.
CAPITAL_REAL_BRL = 375.0

#: Ultimo pregao da PREVIA -- o 10o do IS (a janela IS comeca em 2026-02-27).
#: Corta no LEITOR do parquet, nunca depois de carregar tudo: o arquivo
#: inteiro sao 20,6 milhoes de linhas.
ATE_DIA = date(2026, 3, 12)

MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "6"))

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

EXTRAS = ("fills", "fills_melhor", "%_melhor", "ticks_med", "ticks_max",
          "saida_alvo", "saida_stop", "pregoes_sem_trade", "caixa_min")

#: `(rotulo, profit_ticks, fill_favoravel, ancora_no_fill)`.
#: `profit_ticks=None` = default de producao (2).
VARIANTES = (
    ("T2 nivel (motor de hoje)",     None, False, False),
    ("T2 ancora fill (NO-OP esp.)",  None, False, True),
    ("T2 favoravel + nivel",         None, True,  False),
    ("T2 favoravel + FILL (DONO)",   None, True,  True),
    ("T3 favoravel + nivel",         3,    True,  False),
    ("T3 favoravel + FILL (DONO)",   3,    True,  True),
)

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _bars() -> pd.DataFrame:
    """Fatia OHLCV dos 10 primeiros pregoes do IS, cacheada por PROCESSO."""
    if "bars" not in _DF_CACHE:
        df = pd.read_parquet(
            CACHE,
            columns=["open", "high", "low", "close", "volume"],
            filters=[("janela", "==", "IS"), ("dia", "<=", ATE_DIA)],
        )
        _DF_CACHE["bars"] = df.sort_index()
        del df
    return _DF_CACHE["bars"]


def _roda_uma(spec: dict):
    """Executado no processo FILHO. Devolve `(rotulo, LinhaResultado,
    texto_pronto, dt_segundos)`."""
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday import machine as machine_mod
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars()

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    if spec["profit_ticks"] is not None:
        kwargs["profit_ticks"] = spec["profit_ticks"]
    strat = WdoGridReloadMaker(**kwargs)

    capital = float(spec["capital"])
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        limit_fill_at_bar_open=spec["fill_favoravel"],
        anchor_exits_at_fill=spec["ancora_no_fill"],
        # `target_slippage_ticks` fica no default de `config_for` (1,0 tick,
        # `DESLIZE_ALVO_NATIVO_TICKS`): esta rodada mede o motor CORRIGIDO de
        # hoje, nao o antigo.
    )
    tick = cfg.costs.tick_size

    # Instrumentacao do FILL: `_niveis_da_entrada` e' chamado exatamente uma
    # vez por entrada ACEITA, com a ordem (que carrega o nivel pedido) e o
    # preco preenchido -- e' o unico ponto do motor onde os dois numeros
    # existem juntos. Medir dentro de `_resolve_limit_fills` contaria toques
    # que o cap por volume ainda pode recusar.
    ganhos_em_ticks: list[float] = []
    original = machine_mod.IntradaySessionMachine._niveis_da_entrada

    def _com_medicao(self, order, fill_price):
        delta = (order.limit_price - fill_price) if order.side == "long" else (fill_price - order.limit_price)
        ganhos_em_ticks.append(delta / tick)
        return original(self, order, fill_price)

    machine_mod.IntradaySessionMachine._niveis_da_entrada = _com_medicao
    try:
        t0 = time.perf_counter()
        resultado = run_intraday_backtest(bars, strat, cfg)
        dt = time.perf_counter() - t0
    finally:
        machine_mod.IntradaySessionMachine._niveis_da_entrada = original

    trades = list(resultado.trades)
    contagem = Counter(t.exit_reason.value for t in trades)
    dias_janela = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}

    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    # tolerancia de 1/100 de tick: preco e' float, e "melhor por 0,0" e'
    # preenchimento no nivel, nao ganho.
    melhores = [g for g in ganhos_em_ticks if g > 0.01]
    n_fills = len(ganhos_em_ticks)

    extras = {
        "fills": str(n_fills),
        "fills_melhor": str(len(melhores)),
        "%_melhor": num_br(100.0 * len(melhores) / n_fills, 1) if n_fills else "-",
        "ticks_med": num_br(sum(melhores) / len(melhores), 2) if melhores else "-",
        "ticks_max": num_br(max(melhores), 2) if melhores else "-",
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        "pregoes_sem_trade": str(len(dias_janela - dias_com_trade)),
        "caixa_min": num_br(caixa_min, 2),
    }
    item = linha_de_resultado(spec["rotulo"], resultado, capital,
                              capital_nocional=False, extras=extras)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(f"[{dt:6.1f}s] {linha(item, EXTRAS)}", flush=True)
    return spec["rotulo"], item, buf.getvalue(), dt


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_fill_favoravel] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt

    print(f"[wdof1_fill_favoravel] PREVIA -- IS ate' {ATE_DIA} (10 pregoes), "
          f"capital R${CAPITAL_REAL_BRL:.2f}, deslize do alvo nativo LIGADO "
          f"(default de config_for), {len(VARIANTES)} celulas em "
          f"{MAX_WORKERS} processos\n", flush=True)

    specs = [dict(capital=CAPITAL_REAL_BRL, rotulo=rotulo, profit_ticks=pt,
                  fill_favoravel=fav, ancora_no_fill=anc)
             for rotulo, pt, fav, anc in VARIANTES]

    resultados: dict = {}
    t0 = time.perf_counter()
    concluidos = 0
    n_workers = max(1, min(len(specs), MAX_WORKERS))
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            rotulo, item, texto, _dt = future.result()
            resultados[rotulo] = item
            concluidos += 1
            print(f"[{concluidos}/{len(specs)}] {texto}", end="", flush=True)

    print(f"\n[wdof1_fill_favoravel] motor: {time.perf_counter() - t0:.1f}s\n")

    print("=== PREVIA -- 10 primeiros pregoes do IS, capital R$375 ===")
    print(cabecalho(EXTRAS))
    for rotulo, _pt, _fav, _anc in VARIANTES:
        item = resultados.get(rotulo)
        if item is not None:
            print(linha_fmt(item, EXTRAS))


if __name__ == "__main__":
    main()
