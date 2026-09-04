"""Varredura da saida defensiva de RECUO (`WdoGridReloadMaker.defesa_ativa`,
2026-09-03, pedido do dono) -- "chegou a 80% do stop e depois o preco voltar
a 1% do alvo, a posicao e' fechada", generalizado nos dois parametros
`defesa_gatilho_stop_pct` (fracao do stop, em ticks, que a posicao precisa
sofrer CONTRA ela para a defesa ARMAR) e `defesa_alvo_proximidade_pct`
(depois de armada, fracao da distancia RESTANTE ate o alvo abaixo da qual a
posicao fecha antecipada). Ver a docstring do parametro `defesa_ativa` em
`strategy.daytrade.lab.wdo_grid_reload_maker.WdoGridReloadMaker.__init__`
para a mecanica/formula exata -- este script so' varre e reporta.

Config de PRODUCAO desta estrategia (`T1 S16 x1`: `level_spacing_ticks=1,
profit_ticks=1, stop_ticks=16`) NUNCA muda de default aqui -- so' passamos
os 3 parametros novos, aditivos e OPT-IN, por cima dela. O robo ao vivo
(slot `dt-wdo_grid_reload_maker-wdo@-live`) continua rodando com `defesa_
ativa=False` (default da classe) o tempo todo; nada aqui reinicia processo
nenhum nem toca `db/live.sqlite`/`db/live_process.json`/`strategy.daytrade.
registry` -- pesquisa OFFLINE, sobre dado ja salvo em parquet.

DEGENERESCENCIA A CONFIRMAR (nao assumida): com `profit_ticks=1` o preco so'
se move em ticks inteiros -- nao ha' estado intermediario entre "0% do alvo"
e "100% do alvo" (bateu, ja fechado pelo motor ANTES de `on_bar` rodar, ver
a prioridade "(1) stop/target automatico" em `backtest/intraday/machine.py`).
Ou seja, para QUALQUER `defesa_alvo_proximidade_pct < 100%`, a defesa pode
nunca ver a condicao de fechar bater na config de producao. Este script
CONTA quantos trades fecharam por `defesa_recuo` em cada combinacao (coluna
extra `defesa_recuo_n`) para o numero decidir, e roda tambem UMA linha de
CONTROLE com `profit_ticks=5` (folga de sobra para ter mais de 1 tick de
resolucao no alvo) -- se o mecanismo estiver correto, o controle TEM que
disparar (`defesa_recuo_n > 0`).

## Como o motor guarda o motivo de um `Exit` da estrategia

`core.models.IntradayExitReason` e' um Enum FECHADO com so' 5 valores (stop,
target, forced_flatten, manual, signal) -- `backtest/intraday/machine.py`
mapeia QUALQUER `Exit(reason=...)` retornado pela estrategia para `IntradayExitReason.
SIGNAL` (confirmado lendo `_on_closed_bar_core`, passo "(3) executa acao
filada": as duas chamadas a `_close_position` para uma `Exit` da estrategia
passam `IntradayExitReason.SIGNAL` fixo, nunca o texto de `Exit.reason`). O
texto livre ("defesa_recuo", "stop_agregado_sessao") NAO sobrevive no
`IntradayTrade` -- so' a familia SIGNAL. Como `session_stop_brl` fica em
`None` (default, nunca setado neste script) em TODA rodada aqui, o UNICO
jeito de um trade sair com `exit_reason==SIGNAL` neste script e' a defesa de
recuo -- contar `SIGNAL` e' portanto uma contagem exata de disparos de
`defesa_recuo`, nao uma aproximacao.

## Cache de dado, capital, paralelismo

Cache TICK (nao M1 -- `feed_kind="tick"`, e a nova regra e' sensivel ao
caminho intra-barra) em `data/raw_ticks/WDO_A_f1.parquet` (4.011.197 tick-
barras, IS+OOS ja concatenados e ordenados por tempo -- mesmo metodo ja
validado em `wdof1_rerun_paralelo_2026_08_27.py`: o historico completo E' a
concatenacao das duas janelas).

Capital: R$375,00 -- o capital REAL do slot ao vivo que motivou o pedido
(`dt-wdo_grid_reload_maker-wdo@-live`), NAO o `CAPITAL_NOCIONAL=R$1.000.000`
de calibracao do lab (CLAUDE.md, "capital inicial nunca arbitrario"). `cfg`
sai de `wdo_grid_reload_f1_lab.montar_config()` (nao reescrito aqui) com
`initial_capital` substituido via `dataclasses.replace` (`IntradayBacktestConfig`
e' `@dataclass(frozen=True)`).

Paralelismo: `ProcessPoolExecutor` com `submit`/`as_completed` (nunca
`pool.map`), uma tarefa por COMBINACAO (37 no total: 1 baseline + 36 da
grade + 1 controle), `redirect_stdout` por tarefa, `flush=True`, cada
combinacao imprime a linha dela assim que termina -- ver
`scripts/daytrade/sweep_gremah_tick.py` para o mesmo padrao de streaming.

Uso: `python scripts/daytrade/wdof1_defesa_recuo_sweep_2026_09_03.py`
"""
from __future__ import annotations

import contextlib
import dataclasses
import io
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CACHE = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

#: Capital REAL do slot ao vivo que motivou o pedido -- ver a docstring do
#: modulo, secao "capital". NUNCA o nocional de calibracao do lab.
CAPITAL_REAL_BRL = 375.0

#: Grade de varredura (pedido do dono): 9 x 4 = 36 combinacoes + 1 baseline.
GATILHO_STOP_PCT_GRID = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
ALVO_PROXIMIDADE_PCT_GRID = [0.01, 0.02, 0.05, 0.10]

#: Linha de CONTROLE (diagnostico, NAO candidata a producao) -- `profit_ticks=5`
#: em vez de 1 (config de producao), com folga de sobra para o alvo ter mais
#: de 1 tick de resolucao. Ver a secao "degenerescencia" da docstring do
#: modulo: se o mecanismo estiver correto, esta linha TEM que disparar a
#: defesa pelo menos uma vez (`defesa_recuo_n > 0`).
CONTROLE_PROFIT_TICKS = 5
CONTROLE_GATILHO_STOP_PCT = 0.5
CONTROLE_ALVO_PROXIMIDADE_PCT = 0.10

#: Colunas EXTRA desta rodada -- entram DEPOIS das 12 da base
#: (`backtest/intraday/report.py`), nunca no lugar delas.
EXTRAS = ("gatilho_stop%", "alvo_prox%", "defesa_recuo_n")

#: Parquet lido UMA vez por processo (nao por tarefa) -- mesmo padrao de
#: `wdof1_rerun_paralelo_2026_08_27.py`: 37 tarefas em N processos nao devem
#: ler o arquivo de 4M linhas 37 vezes, so' N.
_DF_PROC = None


def _df_do_processo() -> pd.DataFrame:
    global _DF_PROC
    if _DF_PROC is None:
        df = pd.read_parquet(CACHE)
        _DF_PROC = df[["open", "high", "low", "close", "volume"]]
    return _DF_PROC


def _monta_specs() -> list[dict]:
    """As 38 combinacoes desta rodada: 1 baseline (defesa desligada, config
    de producao intacta) + 36 da grade (config de producao + defesa) + 1
    controle (profit_ticks=5, diagnostico)."""
    specs: list[dict] = [dict(
        rotulo="baseline (defesa off, T1 S16 x1)", defesa_ativa=False,
        gatilho=None, alvo=None, profit_ticks=None, controle=False,
    )]
    for gatilho in GATILHO_STOP_PCT_GRID:
        for alvo in ALVO_PROXIMIDADE_PCT_GRID:
            specs.append(dict(
                rotulo=f"g{gatilho*100:.0f}% a{alvo*100:.0f}%", defesa_ativa=True,
                gatilho=gatilho, alvo=alvo, profit_ticks=None, controle=False,
            ))
    specs.append(dict(
        rotulo=f"CONTROLE T{CONTROLE_PROFIT_TICKS} g{CONTROLE_GATILHO_STOP_PCT*100:.0f}% "
               f"a{CONTROLE_ALVO_PROXIMIDADE_PCT*100:.0f}%",
        defesa_ativa=True, gatilho=CONTROLE_GATILHO_STOP_PCT,
        alvo=CONTROLE_ALVO_PROXIMIDADE_PCT, profit_ticks=CONTROLE_PROFIT_TICKS,
        controle=True,
    ))
    return specs


def _roda_uma(spec: dict) -> tuple[str, dict]:
    """Executado no processo FILHO. Devolve (texto_ja_formatado_da_linha,
    dict_leve_com_os_campos_da_LinhaResultado) -- o pai imprime o texto na
    hora (streaming, nunca espera as outras 36 tarefas) e usa o dict pra
    remontar a tabela final na ORDEM logica (baseline primeiro, grade depois,
    controle por ultimo), que a ordem de conclusao do pool nao garante."""
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from core.models import IntradayExitReason
    from wdo_grid_reload_f1_lab import montar_config, rodar
    from backtest.intraday.report import linha, linha_de_resultado, num_br

    df = _df_do_processo()
    cfg = dataclasses.replace(montar_config(), initial_capital=CAPITAL_REAL_BRL)

    kwargs = {}
    if spec["defesa_ativa"]:
        kwargs["defesa_ativa"] = True
        kwargs["defesa_gatilho_stop_pct"] = spec["gatilho"]
        kwargs["defesa_alvo_proximidade_pct"] = spec["alvo"]
    if spec["profit_ticks"] is not None:
        kwargs["profit_ticks"] = spec["profit_ticks"]

    resultado = rodar(df, cfg, **kwargs)
    n_defesa = sum(1 for t in resultado.trades if t.exit_reason == IntradayExitReason.SIGNAL)

    extras = {
        "gatilho_stop%": "—" if spec["gatilho"] is None else num_br(spec["gatilho"] * 100, 0),
        "alvo_prox%": "—" if spec["alvo"] is None else num_br(spec["alvo"] * 100, 0),
        "defesa_recuo_n": str(n_defesa),
    }
    item = linha_de_resultado(
        spec["rotulo"], resultado, CAPITAL_REAL_BRL, capital_nocional=False, extras=extras,
    )

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item, EXTRAS), flush=True)

    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        retorno_pct=item.retorno_pct, maxdd_pct=item.maxdd_pct, capital_final=item.capital_final,
        extras=item.extras, aviso=item.aviso, n_defesa=n_defesa, controle=spec["controle"],
        eh_baseline=(spec["gatilho"] is None and not spec["controle"]),
    )
    return buf.getvalue(), campos


def _rotulos_ja_concluidos(caminho_log: str) -> set[str]:
    """Le um log de uma rodada ANTERIOR deste mesmo script (texto cru, stdout
    redirecionado) e devolve o conjunto de rotulos que ja tem linha
    "N/M concluido(s) (rotulo)" -- existe so' para RETOMAR uma rodada
    interrompida (2026-09-04, o processo morreu no meio de uma rodada de
    ~74min sem excecao nenhuma -- ambiente mata processo em background apos
    algum tempo) sem repetir trabalho ja' pago. Nao tenta remontar a
    `LinhaResultado` de cada linha antiga (o texto ja' formatado nao volta
    limpo a numero) -- quem chama funde as duas tabelas (a velha, ja
    impressa, e a nova, so' com o que faltou) por FORA deste script."""
    import re
    padrao = re.compile(r"concluido\(s\)\s+\((.+)\)\s*$")
    rotulos: set[str] = set()
    with open(caminho_log, "r", encoding="utf-8", errors="replace") as f:
        for linha_txt in f:
            m = padrao.search(linha_txt.rstrip("\n"))
            if m:
                rotulos.add(m.group(1))
    return rotulos


def main() -> None:
    if not CACHE.exists():
        raise SystemExit(
            f"[wdof1_defesa_recuo_sweep] cache ausente: {CACHE}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    from backtest.intraday.report import LinhaResultado, cabecalho, tabela

    t0 = time.perf_counter()
    specs = _monta_specs()

    retomar = None
    for i, arg in enumerate(sys.argv):
        if arg == "--retomar-de" and i + 1 < len(sys.argv):
            retomar = sys.argv[i + 1]
    if retomar:
        ja_feitos = _rotulos_ja_concluidos(retomar)
        antes = len(specs)
        specs = [s for s in specs if s["rotulo"] not in ja_feitos]
        print(f"[wdof1_defesa_recuo_sweep] retomando de {retomar!r}: "
              f"{len(ja_feitos)} rotulo(s) ja' concluido(s), "
              f"{antes - len(specs)} pulado(s), {len(specs)} restante(s)", flush=True)
    if not specs:
        print("[wdof1_defesa_recuo_sweep] nada a fazer -- todos os rotulos ja' concluidos.")
        return

    n_workers = max(1, min(len(specs), os.cpu_count() or 4))
    print(f"[wdof1_defesa_recuo_sweep] {len(specs)} combinacoes, capital real "
          f"R${CAPITAL_REAL_BRL:.2f}, {n_workers} processos", flush=True)
    print(cabecalho(EXTRAS), flush=True)

    resultados_por_rotulo: dict[str, dict] = {}
    concluidos = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma, spec): spec["rotulo"] for spec in specs}
        for future in as_completed(futures):
            concluidos += 1
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados_por_rotulo[futures[future]] = campos
            print(f"[wdof1_defesa_recuo_sweep] {concluidos}/{len(specs)} concluido(s) "
                  f"({futures[future]})", flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[wdof1_defesa_recuo_sweep] motor: {dt:.1f}s em {n_workers} processos\n")

    # Tabela final na ORDEM LOGICA (baseline, grade na ordem da grade,
    # controle por ultimo) -- a ordem de streaming acima e' a de CONCLUSAO,
    # que o pool nao garante ser a mesma.
    ordenados = [resultados_por_rotulo[spec["rotulo"]] for spec in specs]
    linhas_finais = [
        LinhaResultado(
            variante=c["variante"], liquido_brl=c["liquido_brl"], maxdd_brl=c["maxdd_brl"],
            win_rate_pct=c["win_rate_pct"], trades=c["trades"], pregoes=c["pregoes"],
            retorno_pct=c["retorno_pct"], maxdd_pct=c["maxdd_pct"], capital_final=c["capital_final"],
            extras=c["extras"], aviso=c["aviso"],
        )
        for c in ordenados
    ]
    print("=== tabela final (ordem logica: baseline, grade, controle) ===")
    print(tabela(linhas_finais, EXTRAS))

    baseline = ordenados[0]
    grade = ordenados[1:-1]
    controle = ordenados[-1]
    n_grade_com_disparo = sum(1 for c in grade if c["n_defesa"] > 0)
    print(f"\n[diagnostico] baseline defesa_recuo_n = {baseline['n_defesa']} "
          f"(esperado 0 -- defesa_ativa=False)")
    print(f"[diagnostico] das {len(grade)} combinacoes da grade (config de PRODUCAO, "
          f"profit_ticks=1), {n_grade_com_disparo} dispararam defesa_recuo pelo menos 1x "
          f"(esperado 0, ver a degenerescencia na docstring do modulo -- CONFIRMAR, nao assumir)")
    print(f"[diagnostico] linha de CONTROLE (profit_ticks={CONTROLE_PROFIT_TICKS}) "
          f"defesa_recuo_n = {controle['n_defesa']} "
          f"(esperado > 0 -- ha' folga de mais de 1 tick de resolucao no alvo)")


if __name__ == "__main__":
    main()
