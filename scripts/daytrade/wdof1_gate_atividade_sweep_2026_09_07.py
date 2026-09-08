"""Medicao do gate de atividade pre-entrada (`WdoGridReloadMaker.
gate_atividade_ativo`/`gate_volume_min`/`gate_janela_segundos`, 2026-09-07) --
pedido do dono depois da correlacao achada por
`scripts/daytrade/wdof1_mfe_mae_semana_2026_09_04.py` (analise Opus 5,
Spearman rho~=-0,33, p<0,002 nos QUATRO eixos -- volume_15s/60s_antes,
volatilidade_ticks_15s/60s_antes -- contra a DURACAO do trade que se seguiu,
sobrevive correcao por multiplos testes): mais atividade (volume) ANTES de
uma entrada prevê preenchimento MAIS RAPIDO da ordem-limite.

Isto e' PESQUISA (medir candidatos, nao escolher um) -- o gate nasce OPT-IN
e DESLIGADO por default (`gate_atividade_ativo=False`); nenhum limiar tem
"vencedor" decidido. RESSALVA que o proprio achado original levantou, e que
este script NAO resolve sozinho: a correlacao medida e' sobre VELOCIDADE de
preenchimento, nao QUALIDADE do trade -- a amostra de 177 trades tinha 0
stops, entao ninguem sabe se atividade alta tambem prevê MAIS risco (e'
exatamente onde os stops poderiam morar, sem dado pra confirmar ou refutar).
Este script mede liquido/MaxDD/win%/trades/R$-dia (tabela padrao), MAIS
quantas entradas o gate BLOQUEOU e se a mistura de trades ficou mais RAPIDA
ou nao -- nao assume que o gate melhora o resultado.

Config de ENTRADA identica a producao (`level_spacing_ticks=1,
profit_ticks=2, stop_ticks=16`, com o fix do item 4.9 -- reancoragem
continua da ordem pendente -- ja embutido no DEFAULT da classe,
`reanchor_mode="rolling_last_price"`). O UNICO eixo que muda entre as
variantes e' o gate.

## 3 limiares por janela -- percentil 25/50/75 do volume, NA PROPRIA janela

Nada de chutar um `gate_volume_min` fixo desconectado da escala real: para
cada janela (IS, SEMANA), calcula a soma ROLANTE de volume em janelas de
`GATE_JANELA_SEGUNDOS=15` segundos sobre a PROPRIA serie de ticks daquela
janela (a MESMA grandeza que `WdoGridReloadMaker._volume_recente()` soma em
producao -- ver a docstring do parametro `gate_atividade_ativo`), e usa os
percentis 25/50/75 dessa distribuicao como os 3 candidatos de limiar. IS e
SEMANA tem regimes de liquidez bem diferentes -- por isso os limiares NAO
sao os mesmos numeros nas duas tabelas finais.

## Duas janelas pedidas

  1. IS completo -- `data/raw_ticks/WDO_A_f1.parquet` filtro `janela=="IS"`
     (72 pregoes, 2026-02-27..2026-06-12).
  2. Semana atual -- tick FRESCO do MT5, 2026-08-31..2026-09-04 (mesma
     funcao de `wdof1_mfe_mae_semana_2026_09_04.py::buscar_ticks_semana`).

## "Trades rapidos vs devagar" -- o teste mais direto da correlacao original

Por janela, a mediana de duracao (`exit_ts - entry_ts`) do BASELINE (sem
gate) e' o corte fixo usado em TODAS as variantes daquela janela (baseline
incluido) -- `trades_rapidos_pct` = fracao de trades com duracao <= esse
corte. Se o gate estiver fazendo o que a correlacao original sugere,
`trades_rapidos_pct` deveria SUBIR nas variantes com gate ligado (mais
volume antes da entrada -> preenchimento mais rapido -> trade mais curto),
comparado ao baseline (por construcao, ~50% no baseline).

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`), uma
tarefa por (janela, variante) -- 8 no total (4 variantes x 2 janelas: 1
baseline + 3 limiares). A janela SEMANA e' buscada UMA vez no processo PAI
(MT5 so' aceita conexao no processo que chama `mt5.initialize()`) e passada
por argumento; a janela IS e' lida do parquet DENTRO de cada worker (dataset
grande -- ler 1x por processo, nao serializar por IPC), mesmo padrao de
`scripts/daytrade/wdof1_trailing_lucro_sweep_2026_09_04.py`. Os percentis de
volume (que definem os limiares testados) sao calculados no processo PAI
ANTES de despachar as tarefas -- os workers so' recebem o `gate_volume_min`
ja' resolvido, nunca recalculam o percentil.

A comparacao "rapidos vs devagar" so' pode ser calculada DEPOIS que a
mediana do baseline de cada janela e' conhecida -- por isso o script guarda
o resultado CRU (duracoes por trade) de cada tarefa e monta a tabela final
(com a coluna comparativa) so' depois que TODAS as tarefas da janela
retornaram, em vez de imprimir a linha completa tarefa a tarefa.

Uso: `python -u scripts/daytrade/wdof1_gate_atividade_sweep_2026_09_07.py`
"""
from __future__ import annotations

import dataclasses
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CACHE_IS = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

#: Capital REAL do slot ao vivo (WDO@, R$375 = margem R$150 x buffer 2.0 x
#: reserva 1.25 -- ver `LICOES_DE_PRODUCAO.md`/CLAUDE.md, "capital inicial
#: nunca arbitrario"), NAO um capital nocional de calibracao.
CAPITAL_REAL_BRL = 375.0

#: Config de ENTRADA de producao -- ver a docstring do modulo. Reutilizada
#: em toda variante, gate ligado ou nao.
CANDIDATO_PARAMS = dict(level_spacing_ticks=1, profit_ticks=2, stop_ticks=16)

GATE_JANELA_SEGUNDOS = 15
PERCENTIS = (25, 50, 75)

EXTRAS = ("gate_volume_min", "entradas_bloqueadas", "duracao_mediana_s", "trades_rapidos_pct")

#: Parquet IS lido UMA vez por PROCESSO (nao por tarefa).
_DF_IS_PROC = None


def _is_bars_do_processo() -> pd.DataFrame:
    global _DF_IS_PROC
    if _DF_IS_PROC is None:
        df = pd.read_parquet(CACHE_IS)
        is_df = df[df["janela"] == "IS"]
        _DF_IS_PROC = is_df[["open", "high", "low", "close", "volume"]].sort_index()
    return _DF_IS_PROC


def _percentis_de_volume(bars: pd.DataFrame, janela_segundos: int = GATE_JANELA_SEGUNDOS) -> dict[int, float]:
    """Percentis 25/50/75 da soma ROLANTE de volume em janelas de
    `janela_segundos` segundos, medidos NA PROPRIA serie `bars` -- a MESMA
    grandeza que `WdoGridReloadMaker._volume_recente()` soma em producao
    (ver a docstring do parametro `gate_atividade_ativo`), para os limiares
    testados nao serem um numero chutado fora da escala real desta janela."""
    somas = bars["volume"].sort_index().rolling(f"{janela_segundos}s").sum().dropna()
    return {p: float(np.percentile(somas.to_numpy(), p)) for p in PERCENTIS}


def _monta_specs(is_percentis: dict[int, float], semana_percentis: dict[int, float] | None) -> list[dict]:
    specs: list[dict] = []
    percentis_por_janela = {"IS": is_percentis}
    if semana_percentis is not None:
        percentis_por_janela["SEMANA"] = semana_percentis
    for janela, percentis in percentis_por_janela.items():
        specs.append(dict(
            janela=janela, rotulo=f"[{janela}] baseline (sem gate)",
            gate_atividade_ativo=False, gate_volume_min=None,
        ))
        for p in PERCENTIS:
            limiar = percentis[p]
            specs.append(dict(
                janela=janela, rotulo=f"[{janela}] gate p{p} (volume_min={limiar:.1f})",
                gate_atividade_ativo=True, gate_volume_min=limiar,
            ))
    return specs


def _roda_uma(spec: dict, semana_bars: pd.DataFrame | None):
    """Executado no processo FILHO (IS) ou passada direto (SEMANA, dataset
    pequeno). Devolve `(janela, rotulo, LinhaResultado_parcial, duracoes_seg)`
    -- a linha ainda NAO tem `duracao_mediana_s`/`trades_rapidos_pct` (essas
    duas dependem da mediana do BASELINE da mesma janela, so' conhecida
    depois que TODAS as tarefas voltarem -- ver a docstring do modulo)."""
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.report import linha_de_resultado, num_br
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from wdo_grid_reload_f1_lab import montar_config

    bars = _is_bars_do_processo() if spec["janela"] == "IS" else semana_bars
    cfg = dataclasses.replace(montar_config(), initial_capital=CAPITAL_REAL_BRL)

    kwargs = dict(CANDIDATO_PARAMS)
    if spec["gate_atividade_ativo"]:
        kwargs.update(
            gate_atividade_ativo=True,
            gate_volume_min=spec["gate_volume_min"],
            gate_janela_segundos=GATE_JANELA_SEGUNDOS,
        )
    strat = WdoGridReloadMaker(**kwargs)
    resultado = run_intraday_backtest(bars, strat, cfg)

    item = linha_de_resultado(
        spec["rotulo"], resultado, CAPITAL_REAL_BRL, capital_nocional=False,
        extras={
            "gate_volume_min": "—" if spec["gate_volume_min"] is None else num_br(spec["gate_volume_min"], 1),
            "entradas_bloqueadas": str(strat.gate_bloqueios),
        },
    )
    duracoes_seg = [(t.exit_ts - t.entry_ts).total_seconds() for t in resultado.trades]
    return spec["janela"], spec["rotulo"], item, duracoes_seg


def main() -> None:
    if not CACHE_IS.exists():
        raise SystemExit(
            f"[wdof1_gate_atividade_sweep] cache IS ausente: {CACHE_IS}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    from backtest.intraday.report import LinhaResultado, num_br, tabela
    from wdof1_mfe_mae_semana_2026_09_04 import buscar_ticks_semana

    t0 = time.perf_counter()

    print("[wdof1_gate_atividade_sweep] calculando percentis de volume do IS "
          f"(janela de {GATE_JANELA_SEGUNDOS}s) ...", flush=True)
    is_percentis = _percentis_de_volume(_is_bars_do_processo())
    print(f"[wdof1_gate_atividade_sweep] percentis IS: "
          + ", ".join(f"p{p}={num_br(v, 1)}" for p, v in is_percentis.items()), flush=True)

    print("[wdof1_gate_atividade_sweep] buscando ticks frescos da semana "
          "(2026-08-31..2026-09-04) no MT5 ...", flush=True)
    try:
        semana_bars = buscar_ticks_semana()
        pregoes_semana = sorted(set(semana_bars.index.date))
        print(f"[wdof1_gate_atividade_sweep] semana: {len(semana_bars):,} ticks, "
              f"{len(pregoes_semana)} pregoes: {pregoes_semana}", flush=True)
        semana_percentis = _percentis_de_volume(semana_bars)
        print(f"[wdof1_gate_atividade_sweep] percentis SEMANA: "
              + ", ".join(f"p{p}={num_br(v, 1)}" for p, v in semana_percentis.items()), flush=True)
    except SystemExit as erro:
        print(f"[wdof1_gate_atividade_sweep] AVISO -- sem MT5/tick fresco da semana "
              f"({erro}); rodando SO' a janela IS.", flush=True)
        semana_bars = None
        semana_percentis = None

    specs = _monta_specs(is_percentis, semana_percentis)
    n_workers = max(1, min(len(specs), os.cpu_count() or 4))
    print(f"[wdof1_gate_atividade_sweep] {len(specs)} combinacoes, capital real "
          f"R${CAPITAL_REAL_BRL:.2f}, {n_workers} processos", flush=True)

    # (janela, rotulo) -> (LinhaResultado parcial, duracoes_seg)
    brutos: dict[tuple[str, str], tuple[LinhaResultado, list[float]]] = {}
    concluidos = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_roda_uma, spec, semana_bars if spec["janela"] == "SEMANA" else None): spec["rotulo"]
            for spec in specs
        }
        for future in as_completed(futures):
            concluidos += 1
            janela, rotulo, item, duracoes_seg = future.result()
            brutos[(janela, rotulo)] = (item, duracoes_seg)
            print(f"[wdof1_gate_atividade_sweep] {concluidos}/{len(specs)} concluido: {rotulo} "
                  f"({item.trades} trades, bloqueios={item.extras['entradas_bloqueadas']})", flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[wdof1_gate_atividade_sweep] motor: {dt:.1f}s em {n_workers} processos\n")

    for janela in ("IS", "SEMANA"):
        rotulos_janela = [s["rotulo"] for s in specs if s["janela"] == janela]
        if not rotulos_janela:
            continue
        rotulo_baseline = rotulos_janela[0]
        _, duracoes_baseline = brutos[(janela, rotulo_baseline)]
        mediana_baseline = float(np.median(duracoes_baseline)) if duracoes_baseline else None

        linhas_finais: list[LinhaResultado] = []
        for rotulo in rotulos_janela:
            item, duracoes = brutos[(janela, rotulo)]
            if duracoes and mediana_baseline is not None:
                duracao_mediana_s = num_br(float(np.median(duracoes)), 1)
                rapidos_pct = 100.0 * sum(1 for d in duracoes if d <= mediana_baseline) / len(duracoes)
                trades_rapidos_pct = f"{num_br(rapidos_pct, 1)}%"
            else:
                duracao_mediana_s = "—"
                trades_rapidos_pct = "—"
            item = dataclasses.replace(item, extras={
                **item.extras,
                "duracao_mediana_s": duracao_mediana_s,
                "trades_rapidos_pct": trades_rapidos_pct,
            })
            linhas_finais.append(item)

        print(f"\n=== tabela final -- janela {janela} (baseline primeiro, depois p25/p50/p75) ===")
        print(f"corte 'rapido vs devagar': mediana de duracao do BASELINE = "
              f"{'—' if mediana_baseline is None else num_br(mediana_baseline, 1) + 's'}")
        print(tabela(linhas_finais, EXTRAS))


if __name__ == "__main__":
    main()
