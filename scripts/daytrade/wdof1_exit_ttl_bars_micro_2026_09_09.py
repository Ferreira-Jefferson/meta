"""MICRO-TESTE: calibrar `exit_ttl_bars` do alvo fatiado do WDO F1 (T2/S16,
10 primeiros pregoes do IS, capital real R$375).

## Por que existe

`fatiar_saida_alvo=True` foi ligado em producao em 2026-09-08 e validado em
IS/OOS (`wdof1_fatiar_saida_alvo_is_oos_2026_09_08.py`: T2 +R$239.936,50 no
IS e +R$77.833,50 no OOS, 0 pregoes sem trade nas duas). Mas o `exit_ttl_bars`
que foi junto e' **8**, EMPRESTADO de `gremah.py::EXIT_TTL_BARS_PADRAO` --
varrido em PMAM3 (acao B3 de centavos, fila lenta), nunca no WDO F1.

Que o numero NAO e' detalhe ficou provado no proprio IS/OOS: a previa rodou
sem prazo (`None`) e deu T3 fatiado +R$12.928,50; a janela cheia rodou com
prazo 8 e deu -R$248,50 com 70 de 72 pregoes parados. Mesma geometria, mesmo
fatiamento -- so' o prazo mudou.

## A natureza do WDO@ e a UNIDADE do prazo

CORRECAO 2026-09-09 (a primeira versao desta docstring dizia "barras de 1
minuto" e estava ERRADA): este robo declara `feed_kind="tick"`, entao BARRA
E' NEGOCIO. Na base canonica sao 159.440 barras num pregao, mediana de 62 ms
entre elas -- `exit_ttl_bars=8` e' da ordem de MEIO SEGUNDO, nao 8 minutos.
Quem ler a tabela abaixo pensando em minutos erra a escala por ~1000x.

Isso torna o emprestimo da `gremah` pior do que parecia: ela roda
`feed_kind="m1"`, logo o 8 dela sao 8 MINUTOS. O mesmo numero mudou de
UNIDADE ao atravessar de um robo para o outro.

O que o prazo mede e' "quanto tempo a ordem-limite do alvo fica parada no
livro antes de desistir e ir a mercado". Tres fatos do instrumento definem a
faixa que faz sentido:

  * O alvo do T2 esta' a **2 ticks = 1,0 ponto** do preco de entrada, e o
    prazo conta em NEGOCIOS. Um punhado de negocios a 62 ms nao e' "tempo de
    espera" em nenhum sentido humano -- e' quase o instante do toque.
  * O robo negocia ~285 trades/dia no regime fatiado (medido no IS), com
    capital no piso exato (R$375, 1 contrato): posicao pendurada e' caixa
    indisponivel para a proxima entrada.
  * O WDO@ e' liquido: a barreira nao e' achar contraparte (como na PMAM3,
    de onde o 8 veio), e' o preco ir embora antes da fila andar.

A faixa varrida: 1, 2, 3, 5, 8 (o de producao), 12, 20 -- depois preenchida
com 6, 10 e 15.

REGISTRO DE UMA INTUICAO ERRADA, que e' por que a varredura existe: eu previ
que o otimo ficaria ABAIXO de 8, raciocinando sobre "8 minutos de espera".
Errado duas vezes -- a unidade nao era minuto, e a tendencia do liquido vai
no sentido CONTRARIO (ttl 1 e' o pior de todos, e o topo operavel esta' em
20). Esperar mais rende mais porque cada estouro de prazo vira saida a
mercado, que e' o custo que fatiar existe para evitar.

`None` (sem prazo) entra como REFERENCIA, nao como candidato: e' outro
caminho no motor (`_resolve_target_partial_fill`, preenche na propria barra
do toque, espera indefinidamente) e **nao e' operavel com dinheiro real** --
`machine._resolve_live_split_exit` exige prazo por assert, porque limite sem
prazo e' posicao exposta para sempre. Serve para separar "quanto do resultado
vem de fatiar" de "quanto vem do prazo escolhido".

## Escopo

So' **T2** (a geometria de producao). T3 fatiado ficou de fora de proposito:
na janela cheia ele deu -R$248,50 no IS com 70 de 72 pregoes parados, ou
seja, ja' esta' refutado como alternativa -- calibrar prazo para uma
geometria morta e' tempo de maquina gasto. `profit_ticks=1` (T1) nunca entra
(ordem do dono, CLAUDE.md).

10 pregoes e' MICRO-teste, e o dono pediu assim: serve para achar a REGIAO
do otimo e descartar o que e' claramente ruim, nao para cravar o numero
final. Confira `pregoes_sem_trade`/`trades` antes do liquido (item 6.15 de
LICOES_DE_PRODUCAO.md) -- com capital no piso, a linha censurada mede o
portao de caixa, nao o prazo.

Uso: `python -u scripts/daytrade/wdof1_exit_ttl_bars_micro_2026_09_09.py`
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

#: Capital REAL do slot ao vivo (WDO@). Ordem do dono: nunca capital de folga.
CAPITAL_REAL_BRL = 375.0

#: O 10o pregao do IS (a janela comeca em 2026-02-27) -- corte no LEITOR do
#: parquet, nunca depois de carregar (o arquivo sao 20,6 milhoes de linhas).
ATE_DIA = date(2026, 3, 12)

MAX_WORKERS = int(os.environ.get("WDOF1_WORKERS", "4"))

#: `exit_ttl_bars` sai daqui de proposito -- e' o eixo varrido.
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

EXTRAS = ("trades", "saida_alvo", "saida_stop", "saida_flatten",
          "pregoes_sem_trade", "caixa_min")

#: `(rotulo, exit_ttl_bars)`. `None` = sem prazo, REFERENCIA nao-operavel.
_VARIANTES_PADRAO = (
    ("ttl None (ref, nao operavel)", None),
    ("ttl  1",                       1),
    ("ttl  2",                       2),
    ("ttl  3",                       3),
    ("ttl  5",                       5),
    ("ttl  8 (producao hoje)",       8),
    ("ttl 12",                       12),
    ("ttl 20",                       20),
)


def _variantes() -> tuple[tuple[str, int | None], ...]:
    """Valores de `exit_ttl_bars` a rodar. `WDOF1_TTLS` (lista separada por
    virgula, ex.: `WDOF1_TTLS=6,10,15`) roda SO' os pedidos -- existe para
    preencher buraco na curva sem re-rodar as celulas que ja' sairam, que a
    ~400s cada seria tempo de maquina jogado fora. Sem a variavel, roda a
    faixa padrao acima."""
    bruto = os.environ.get("WDOF1_TTLS", "").strip()
    if not bruto:
        return _VARIANTES_PADRAO
    valores = [p.strip() for p in bruto.split(",") if p.strip()]
    return tuple(
        (("ttl None (ref, nao operavel)" if v.lower() == "none" else f"ttl {int(v):>2}"),
         (None if v.lower() == "none" else int(v)))
        for v in valores
    )


VARIANTES = _variantes()

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
    """Executado no processo FILHO."""
    import contextlib
    import io

    sys.path.insert(0, str(RAIZ / "src"))

    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars()

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    kwargs["fatiar_saida_alvo"] = True
    kwargs["exit_ttl_bars"] = spec["ttl"]
    strat = WdoGridReloadMaker(**kwargs)

    capital = float(spec["capital"])
    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=capital,
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
    equity = resultado.equity_curve
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "trades": str(len(trades)),
        "saida_alvo": str(contagem.get("target", 0)),
        "saida_stop": str(contagem.get("stop", 0)),
        "saida_flatten": str(contagem.get("forced_flatten", 0)),
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
        raise SystemExit(f"[wdof1_exit_ttl] cache ausente: {CACHE}")
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt

    print(f"[wdof1_exit_ttl] MICRO -- IS ate' {ATE_DIA} (10 pregoes), T2 "
          f"fatiado, capital R${CAPITAL_REAL_BRL:.2f}, {len(VARIANTES)} "
          f"valores de exit_ttl_bars, {MAX_WORKERS} processos\n", flush=True)

    specs = [dict(capital=CAPITAL_REAL_BRL, rotulo=rotulo, ttl=ttl)
             for rotulo, ttl in VARIANTES]

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

    print(f"\n[wdof1_exit_ttl] motor: {time.perf_counter() - t0:.1f}s\n")

    print("=== MICRO exit_ttl_bars -- T2 fatiado, 10 pregoes IS, R$375 ===")
    print(cabecalho(EXTRAS))
    for rotulo, _ttl in VARIANTES:
        item = resultados.get(rotulo)
        if item is not None:
            print(linha_fmt(item, EXTRAS))


if __name__ == "__main__":
    main()
