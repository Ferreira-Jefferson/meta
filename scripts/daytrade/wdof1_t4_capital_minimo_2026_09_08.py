"""Pergunta do dono, 2026-09-08, reagindo direto ao achado de
`wdof1_producao_t3_t4_t5_2026_09_08.py`: T4/S16 (profit_ticks=4,
stop_ticks=16) TRAVA no capital real do slot (R$375) -- 71/72 pregoes sem
trade no IS, 50/51 no OOS, liquido negativo nas duas janelas, `qtd_max=1`
(nunca escalou). "Qual e' o capital minimo pra T4 nao travar?"

## Metodo -- combina os DOIS precedentes

- **Fonte de dado e passada continua**: `wdof1_sobrevivencia_capital_baixo_
  2026_08_29.py` -- `market_data_intraday.storage.load_m1("WDO@")`,
  historico M1 SALVO INTEIRO (nao o parquet de tick, muito mais pesado),
  filtrando pregao incompleto com `MIN_BARRAS_POR_PREGAO=400`, rodando numa
  UNICA passada continua (nunca reinicia caixa por pregao -- e' isso que
  revela travamento por sequencia de perdas atravessando dias). A UNICA
  coisa que varia entre tarefas aqui e' o `initial_capital`, na mesma
  escada `NIVEIS_CAPITAL` do script de referencia.
- **Construcao da estrategia**: `wdof1_producao_t3_t4_t5_2026_09_08.py` --
  `strategy.daytrade.registry.get_daytrade_robot("wdo_grid_reload_maker")`
  para pegar a config REAL de producao (isso inclui o dimensionamento
  DINAMICO por capital que o registry liga por cima dos defaults da classe:
  `margin_per_contract_brl=150.0`, `hard_cap_contratos=5`,
  `risco_pct_por_trade=0.01`, `point_value_brl=10.0`, decisao 2026-08-29) --
  e' a MESMA config que produziu o achado de trava, so' clonada via kwargs
  com `profit_ticks=4`/`stop_ticks=16` fixados explicitamente (o segundo ja'
  e' o default de producao, mas fixar os dois deixa este script imune a uma
  mudanca futura de default).

`profit_ticks=1` (T1) nao entra em lugar nenhum aqui -- proibicao
permanente do dono, 2026-09-08 (motor nao cobra deslize do TP nativo, ver
`LICOES_DE_PRODUCAO.md`/`CLAUDE.md`). Este script nem varia `profit_ticks`;
fica travado em 4.

## O que cada linha reporta

Tabela padrao (`backtest/intraday/report.py::linha_de_resultado`/`tabela`,
decisao do dono 2026-08-25 -- nunca inventar coluna nova) + extras:
- `sem_trade`: pregoes SEM NENHUM trade, sobre o TOTAL de pregoes do
  historico filtrado (constante entre niveis) -- a METRICA CENTRAL desta
  pergunta. "Travou" = fracao alta; "destravou" = volta a operar quase todo
  pregao (como T2/T3 fazem em producao).
- `qtd_max`: maior `quantity` entre os trades fechados -- confirma se o
  dimensionamento dinamico chegou a ESCALAR (>1) ou ficou preso em 1
  contrato o tempo todo (sintoma do mesmo travamento).
- `zerou`: `resultado.wiped_out_at` -- ruina de verdade (patrimonio <= 0),
  distinto de travar (patrimonio positivo mas preso abaixo da margem crua).
- `caixa_min`: menor ponto da curva de patrimonio (mark-to-market) -- mede a
  DISTANCIA ate a margem crua (R$150) ou ate zero, nao so' se cruzou.
- `recusa_cap`: `ordens_recusadas_por_capital` -- quantas vezes o motor
  recusou uma entrada por falta de caixa (a causa MECANICA do travamento,
  quando > 0 e `sem_trade` alto ao mesmo tempo).

## Paralelismo e memoria

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`), uma
tarefa por nivel de capital (8 no total, mesma escada do script de
referencia) -- streaming: cada tarefa imprime a linha DELA assim que
termina, sem esperar a rodada inteira (`feedback_stream_results_as_ready`).

CUIDADO COM MEMORIA -- ja aconteceu neste repo (script irmao rodando dado
de TICK) 8 processos travarem a maquina e morrerem com `ArrayMemoryError`
cada um carregando o parquet de tick inteiro (~2,3 GB). M1 e' MUITO mais
leve (o parquet de `WDO@` inteiro tem ~1,9 MB em disco -- 3 ordens de
grandeza menor), mas o cache ainda e' 1x POR PROCESSO (nunca do pai) pelo
MESMO padrao do script de referencia, e o pool fica limitado a
`MAX_WORKERS_MEMORIA=4` por precaucao (nao ha' motivo pra 8 aqui: so' 8
tarefas, cabem confortavel em 4 processos revezando).

Uso: `python -u scripts/daytrade/wdof1_t4_capital_minimo_2026_09_08.py`
"""
from __future__ import annotations

import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SYMBOL = "WDO@"

#: T4/S16 FIXO -- a config que ja sabemos que trava em R$375
#: (`wdof1_producao_t3_t4_t5_2026_09_08.py`). So' o capital varia aqui.
PROFIT_TICKS = 4
STOP_TICKS = 16

#: MESMA escada de `wdof1_sobrevivencia_capital_baixo_2026_08_29.py`.
NIVEIS_CAPITAL = [375.0, 500.0, 750.0, 1_000.0, 1_500.0, 2_000.0, 3_000.0, 5_000.0]

MIN_BARRAS_POR_PREGAO = 400

#: Todo parametro de `WdoGridReloadMaker.__init__` (menos `self`), na ordem
#: declarada -- mesma tupla de `wdof1_producao_t3_t4_t5_2026_09_08.py`,
#: usada para clonar a instancia de PRODUCAO (`get_daytrade_robot`) via
#: kwargs, sobrescrevendo so' `profit_ticks`/`stop_ticks`.
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

EXTRAS = ("sem_trade", "qtd_max", "zerou", "caixa_min", "recusa_cap")

OUT_CSV = ROOT / "scripts" / "daytrade" / "wdof1_t4_capital_minimo_2026_09_08.csv"

_BARS_CACHE = None  # por processo -- o pool reusa processos entre tarefas


def _bars_do_processo() -> pd.DataFrame:
    global _BARS_CACHE
    if _BARS_CACHE is None:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
        _BARS_CACHE = df[[d in completos for d in df.index.date]]
    return _BARS_CACHE


def _roda(capital: float) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha_de_resultado
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    bars = _bars_do_processo()
    profile = profile_for(SYMBOL)

    robo_producao = get_daytrade_robot("wdo_grid_reload_maker")
    kwargs = {campo: getattr(robo_producao, campo) for campo in CAMPOS_KWARGS}
    kwargs["profit_ticks"] = PROFIT_TICKS
    kwargs["stop_ticks"] = STOP_TICKS
    strat = WdoGridReloadMaker(**kwargs)

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
    equity = resultado.equity_curve

    dias_totais = set(bars.index.date)
    dias_com_trade = {pd.Timestamp(t.entry_ts).date() for t in trades}
    sem_trade = len(dias_totais - dias_com_trade)
    qtd_max = max((t.quantity for t in trades), default=0)
    caixa_min = float(equity.min()) if len(equity) else float("nan")

    extras = {
        "sem_trade": f"{sem_trade}/{len(dias_totais)}",
        "qtd_max": str(qtd_max),
        "zerou": ("NAO" if resultado.wiped_out_at is None else str(resultado.wiped_out_at)),
        "caixa_min": f"{caixa_min:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."),
        "recusa_cap": str(resultado.ordens_recusadas_por_capital),
    }
    item = linha_de_resultado(f"T4/S16 R${capital:,.0f}".replace(",", "."), resultado,
                               capital, capital_nocional=False, extras=extras)

    return dict(
        capital=capital, dt=dt, item=item,
        trades=len(trades),
        liquido=sum(t.pnl_brl for t in trades),
        pregoes_totais=len(dias_totais),
        pregoes_com_trade=len(dias_com_trade),
        sem_trade=sem_trade,
        qtd_max=qtd_max,
        caixa_min=caixa_min,
        zerou=resultado.wiped_out_at is not None,
        zerou_em=str(resultado.wiped_out_at) if resultado.wiped_out_at is not None else "",
        recusadas_por_capital=resultado.ordens_recusadas_por_capital,
        recusadas_por_teto=resultado.ordens_recusadas_por_teto,
    )


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.report import cabecalho, linha as linha_fmt, num_br

    n_workers = max(1, min(len(NIVEIS_CAPITAL), os.cpu_count() or 4, 4))
    print(f"[wdof1_t4_capital_minimo] T4/S16 fixo, {len(NIVEIS_CAPITAL)} niveis de capital, "
          f"{n_workers} processos em paralelo (teto de memoria por precaucao, dado M1 e' leve)\n",
          flush=True)

    t0 = time.perf_counter()
    linhas: dict[float, dict] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        futuros = {ex.submit(_roda, cap): cap for cap in NIVEIS_CAPITAL}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            linhas[r["capital"]] = r
            feitos += 1
            print(f"[{feitos}/{len(NIVEIS_CAPITAL)} {r['dt']:5.1f}s] {linha_fmt(r['item'], EXTRAS)}",
                  flush=True)

    print(f"\ntotal: {time.perf_counter()-t0:.1f}s\n", flush=True)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        campos = ["capital", "trades", "liquido", "pregoes_totais", "pregoes_com_trade",
                   "sem_trade", "qtd_max", "caixa_min", "zerou", "zerou_em",
                   "recusadas_por_capital", "recusadas_por_teto"]
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for cap in NIVEIS_CAPITAL:
            l = linhas[cap]
            w.writerow({k: l[k] for k in campos})
    print(f"[wdof1_t4_capital_minimo] CSV salvo em {OUT_CSV}\n")

    print("=== tabela final, na ordem da escada de capital ===")
    print(cabecalho(EXTRAS))
    for cap in NIVEIS_CAPITAL:
        print(linha_fmt(linhas[cap]["item"], EXTRAS))

    print("\n=== veredito: primeiro nivel que destrava (sem_trade <= 10% dos pregoes) "
          "E fecha liquido positivo ===")
    candidato = None
    for cap in NIVEIS_CAPITAL:
        l = linhas[cap]
        frac_sem_trade = l["sem_trade"] / l["pregoes_totais"] if l["pregoes_totais"] else 1.0
        destravou = (not l["zerou"]) and frac_sem_trade <= 0.10
        if destravou and l["liquido"] > 0:
            candidato = l
            break
    if candidato is not None:
        print(f"*** R${num_br(candidato['capital'], 0)} -- trades={candidato['trades']}, "
              f"liquido=R${num_br(candidato['liquido'], 2)}, "
              f"sem_trade={candidato['sem_trade']}/{candidato['pregoes_totais']}, "
              f"qtd_max={candidato['qtd_max']} ***")
    else:
        print("*** NENHUM nivel testado (ate R$5.000) destrava E fecha liquido positivo "
              "ao mesmo tempo -- ver a tabela acima para o comportamento exato em cada nivel. ***")


if __name__ == "__main__":
    main()
