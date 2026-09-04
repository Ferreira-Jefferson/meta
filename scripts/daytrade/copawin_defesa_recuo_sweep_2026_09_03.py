"""Varredura da saida defensiva de RECUO (`CopaWin.defesa_ativa`, 2026-09-03,
pedido do dono) em `CopaWin` (WIN@, M1) -- MESMA ideia ja varrida em
`WdoGridReloadMaker` (`scripts/daytrade/wdof1_defesa_recuo_sweep_2026_09_03.py`):
"chegou a X% do stop e depois o preco voltar a Y% do alvo, a posicao e'
fechada", nos dois parametros `defesa_gatilho_stop_pct` (fracao da distancia
do STOP que precisa ser sofrida, em excursao ADVERSA nao realizada, para a
defesa ARMAR) e `defesa_alvo_proximidade_pct` (depois de armada, fracao da
distancia RESTANTE ate o alvo abaixo da qual a posicao fecha antecipada). Ver
a docstring do parametro `defesa_ativa` em
`strategy.daytrade.lab.copa_win.CopaWin.__init__` para a mecanica/formula
exata -- este script so' varre e reporta.

## Por que aqui, e nao so' na WDO F1

A varredura na WDO F1 achou DEGENERADO: com o alvo de producao de 1 tick, nao
existe estado intermediario entre "0% do alvo" e "100%" (bateu, ja fechado
pelo motor ANTES de `on_bar` rodar) -- a defesa nunca via a condicao de
fechar antes da saida normal. O `CopaWin` tem alvo de producao `alvo_vol=19,0`
(dezenas de pontos de espaco real contra `stop_vol=12,0`) -- "quase la'" e' um
estado que existe de fato aqui, entao esta rodada espera disparos REAIS de
`defesa_recuo`, nao degenerados.

## Config de PRODUCAO -- nunca redigitada a mao

Os kwargs de producao (`janela_rompimento=10, alvo_vol=19.0, stop_vol=12.0,
trail_vol=None, vol_min_ticks=8.0, fracao_entrada=1.0, aquecimento_barras=45,
max_entradas_dia=10, entrada_maker=True, entrada_ttl_barras=15,
teto_contratos=15, margin_per_contract_brl=100.0, risco_pct_por_trade=0.05`,
ver `strategy.daytrade.registry._KWARGS_PADRAO[CopaWin.name]`, NAO EDITADO
por este script) sao lidos de uma instancia via `get_daytrade_robot("copa_win",
symbol="WIN@")` (`_kwargs_producao` abaixo) em vez de redigitados aqui -- um
numero declarado em dois lugares e' um numero que vai divergir (mesmo
argumento de `backtest/intraday/profiles.py`).

## Dois niveis de capital, os dois justificados (CLAUDE.md, "capital inicial
## nunca arbitrario")

- **R$434,00** -- o capital REAL atual do slot `dt-copa_win-win@-shadow`.
  Mostra o que acontece HOJE de verdade: poucas entradas (o piso fino real do
  CopaWin e' ~R$750, ver a memoria `copawin-e-gremah-piso-capital-2026-08-29`)
  -- ESPERADO, nao e' bug.
- **R$3.000,00** -- nivel de FOLGA, ja usado em
  `scripts/daytrade/podio_stress_capital_real_historico_completo.py` e
  `copawin_seguranca_capital_alto_2026_08_29.py`, onde o robo opera livre do
  teto de capital (276 trades no historico, liquido ~R$9.830 na config
  baseline sem defesa).

`enforce_capital_cap` fica no default de `config_for` (liga sozinho para
perfil de futuro com `margin_per_contract_brl` conhecido, que e' o caso do
WIN@) -- os dois niveis rodam sob o MESMO teto dinamico por caixa que a
producao usa, nunca margem infinita.

## Como o motor guarda o motivo de um `Exit` da estrategia

`core.models.IntradayExitReason` e' um Enum FECHADO (stop, target,
forced_flatten, manual, signal) -- `backtest/intraday/machine.py` mapeia
QUALQUER `Exit(reason=...)` retornado pela estrategia para
`IntradayExitReason.SIGNAL`, nunca o texto livre. `CopaWin` so' emite `Exit`
pela defesa de recuo (o freio diario `perda_max_dia_brl` explicitamente NAO
emite `Exit`, ver a docstring de `on_bar`) -- contar `SIGNAL` e' portanto uma
contagem EXATA de disparos de `defesa_recuo`, nao uma aproximacao.

## Cache de dado, paralelismo

`market_data_intraday.storage.load_m1("WIN@")`, filtrado para sessoes com
>= 400 barras M1 (mesmo filtro de `podio_stress_capital_real_historico_
completo.py`) -- 184 pregoes completos, 2025-12-01..2026-08-31 (104.323
barras brutas antes do filtro).

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`), uma
tarefa por (capital x combinacao) -- 2 x 37 = 74 tarefas (2 baselines + 2x36
da grade), `redirect_stdout` por tarefa, `flush=True`, cada tarefa imprime a
linha dela assim que termina.

Uso: `python scripts/daytrade/copawin_defesa_recuo_sweep_2026_09_03.py`
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
    """Formato BR (milhar com ponto, decimal com virgula) -- placeholder-swap,
    nao `.replace(",", ".")` direto (isso quebraria `1,234.56` -> `1.234.56`)."""
    s = f"{v:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


SYMBOL = "WIN@"
MIN_BARRAS_M1_FUTURO = 400

#: Economia do WIN@ (ver `scripts/daytrade/podio_stress_capital_real_
#: historico_completo.py`, referencia ja validada desta estrategia).
TRADE_TICK_VALUE = 0.20
TRADE_TICK_SIZE = 1.0

#: Dois niveis de capital, os dois justificados -- ver a docstring do modulo.
CAPITAL_REAL_BRL = 434.0
CAPITAL_FOLGA_BRL = 3_000.0
NIVEIS_CAPITAL = (CAPITAL_REAL_BRL, CAPITAL_FOLGA_BRL)

#: Grade de varredura (pedido do dono, mesma da WDO F1): 9 x 4 = 36
#: combinacoes + 1 baseline, POR nivel de capital.
GATILHO_STOP_PCT_GRID = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
ALVO_PROXIMIDADE_PCT_GRID = [0.01, 0.02, 0.05, 0.10]

#: Colunas EXTRA desta rodada -- entram DEPOIS das 12 da base
#: (`backtest/intraday/report.py`), nunca no lugar delas. `recusa_capital`
#: (`ordens_recusadas_por_capital`) explica por que R$434 tem poucos trades
#: -- nao e' bug, e' o piso de capital real (ver a docstring do modulo).
EXTRAS = ("gatilho_stop%", "alvo_prox%", "defesa_recuo_n", "recusa_capital")

#: Barras M1 lidas UMA vez por PROCESSO (nao por tarefa) -- 74 tarefas em N
#: processos nao devem ler o parquet 74 vezes, so' N.
_BARS_PROC: pd.DataFrame | None = None


def _bars_do_processo() -> pd.DataFrame:
    global _BARS_PROC
    if _BARS_PROC is None:
        sys.path.insert(0, str(RAIZ / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_M1_FUTURO}
        _BARS_PROC = df[[d in completos for d in df.index.date]]
    return _BARS_PROC


def _kwargs_producao() -> dict:
    """Le os kwargs de PRODUCAO de uma instancia default (`get_daytrade_
    robot`), em vez de redigita-los aqui -- ver a docstring do modulo."""
    from strategy.daytrade.registry import get_daytrade_robot

    r = get_daytrade_robot("copa_win", symbol=SYMBOL)
    return dict(
        symbol=r.symbol, tick_size=r.tick_size, point_value_brl=r.point_value_brl,
        fracao_entrada=r.fracao_entrada, janela_rompimento=r.janela_rompimento,
        alvo_vol=r.alvo_vol, stop_vol=r.stop_vol, vol_min_ticks=r.vol_min_ticks,
        trail_vol=r.trail_vol, aquecimento_barras=r.aquecimento_barras,
        max_entradas_dia=r.max_entradas_dia, entrada_maker=r.entrada_maker,
        entrada_ttl_barras=r.entrada_ttl_barras, perda_max_dia_pontos=r.perda_max_dia_pontos,
        margin_per_contract_brl=r.margin_per_contract_brl, margin_buffer=r.margin_buffer,
        risco_pct_por_trade=r.risco_pct_por_trade, teto_contratos=r.teto_contratos,
    )


def _monta_specs() -> list[dict]:
    """(1 baseline + 36 da grade) x 2 niveis de capital = 74 combinacoes."""
    specs: list[dict] = []
    for capital in NIVEIS_CAPITAL:
        rotulo_capital = f"R${br(capital, 0)}"
        specs.append(dict(
            rotulo=f"{rotulo_capital} baseline (defesa off)", capital=capital,
            defesa_ativa=False, gatilho=None, alvo=None,
        ))
        for gatilho in GATILHO_STOP_PCT_GRID:
            for alvo in ALVO_PROXIMIDADE_PCT_GRID:
                specs.append(dict(
                    rotulo=f"{rotulo_capital} g{gatilho*100:.0f}% a{alvo*100:.0f}%",
                    capital=capital, defesa_ativa=True, gatilho=gatilho, alvo=alvo,
                ))
    return specs


def _roda_uma(spec: dict) -> tuple[str, dict]:
    """Executado no processo FILHO. Devolve (texto_ja_formatado_da_linha,
    dict_leve_com_os_campos_da_LinhaResultado) -- o pai imprime o texto na
    hora (streaming) e usa o dict pra remontar a tabela final na ORDEM
    logica (capital, depois baseline/grade), que a ordem de conclusao do
    pool nao garante."""
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from core.models import IntradayExitReason
    from strategy.daytrade.lab.copa_win import CopaWin

    bars = _bars_do_processo()
    profile = profile_for(SYMBOL)

    kwargs = _kwargs_producao()
    if spec["defesa_ativa"]:
        kwargs.update(
            defesa_ativa=True,
            defesa_gatilho_stop_pct=spec["gatilho"],
            defesa_alvo_proximidade_pct=spec["alvo"],
        )
    strat = CopaWin(**kwargs)
    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=spec["capital"], target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )

    resultado = run_intraday_backtest(bars, strat, cfg)
    n_defesa = sum(1 for t in resultado.trades if t.exit_reason == IntradayExitReason.SIGNAL)

    extras = {
        "gatilho_stop%": "—" if spec["gatilho"] is None else num_br(spec["gatilho"] * 100, 0),
        "alvo_prox%": "—" if spec["alvo"] is None else num_br(spec["alvo"] * 100, 0),
        "defesa_recuo_n": str(n_defesa),
        "recusa_capital": str(resultado.ordens_recusadas_por_capital),
    }
    item = linha_de_resultado(
        spec["rotulo"], resultado, spec["capital"], capital_nocional=False, extras=extras,
    )

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item, EXTRAS), flush=True)

    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        retorno_pct=item.retorno_pct, maxdd_pct=item.maxdd_pct, capital_final=item.capital_final,
        extras=item.extras, aviso=item.aviso, n_defesa=n_defesa, capital=spec["capital"],
        eh_baseline=(spec["gatilho"] is None),
    )
    return buf.getvalue(), campos


def main() -> None:
    from backtest.intraday.report import LinhaResultado, cabecalho, tabela

    t0 = time.perf_counter()
    specs = _monta_specs()
    n_workers = max(1, min(len(specs), os.cpu_count() or 4))
    print(f"[copawin_defesa_recuo_sweep] {len(specs)} combinacoes "
          f"({len(NIVEIS_CAPITAL)} niveis de capital x 37 cada), {n_workers} processos", flush=True)
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
            print(f"[copawin_defesa_recuo_sweep] {concluidos}/{len(specs)} concluido(s) "
                  f"({futures[future]})", flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[copawin_defesa_recuo_sweep] motor: {dt:.1f}s em {n_workers} processos\n")

    # Uma tabela POR nivel de capital -- ordem logica (baseline primeiro,
    # grade na ordem da grade), nao a ordem de conclusao do pool.
    for capital in NIVEIS_CAPITAL:
        specs_deste_nivel = [s for s in specs if s["capital"] == capital]
        campos_deste_nivel = [resultados_por_rotulo[s["rotulo"]] for s in specs_deste_nivel]
        linhas = [
            LinhaResultado(
                variante=c["variante"], liquido_brl=c["liquido_brl"], maxdd_brl=c["maxdd_brl"],
                win_rate_pct=c["win_rate_pct"], trades=c["trades"], pregoes=c["pregoes"],
                retorno_pct=c["retorno_pct"], maxdd_pct=c["maxdd_pct"], capital_final=c["capital_final"],
                extras=c["extras"], aviso=c["aviso"],
            )
            for c in campos_deste_nivel
        ]
        print(f"\n=== tabela final -- capital inicial R${br(capital, 2)} ===")
        print(tabela(linhas, EXTRAS))

        baseline = campos_deste_nivel[0]
        grade = campos_deste_nivel[1:]
        n_grade_com_disparo = sum(1 for c in grade if c["n_defesa"] > 0)
        melhor = max(grade, key=lambda c: c["liquido_brl"])
        rotulo_cap = f"R${br(capital, 2)}"
        print(f"\n[diagnostico {rotulo_cap}] baseline: liquido=R${br(baseline['liquido_brl'])}, "
              f"trades={baseline['trades']}, defesa_recuo_n={baseline['n_defesa']} (esperado 0)")
        print(f"[diagnostico {rotulo_cap}] das {len(grade)} combinacoes da grade, "
              f"{n_grade_com_disparo} dispararam defesa_recuo pelo menos 1x")
        print(f"[diagnostico {rotulo_cap}] melhor liquido da grade: {melhor['variante']} "
              f"(R${br(melhor['liquido_brl'])}, defesa_recuo_n={melhor['n_defesa']}) "
              f"vs baseline R${br(baseline['liquido_brl'])}")


if __name__ == "__main__":
    main()
