"""Medicao do trailing sobre o lucro (`WdoGridReloadMaker.trailing_ativo`/
`trailing_recuo_ticks`, 2026-09-04) -- pedido do dono depois do item 4.8 de
`LICOES_DE_PRODUCAO.md` (a 1a operacao real derrapou 1 tick no alvo nativo de
1 tick e zerou o lucro do trade, o que ja motivou a troca de `profit_ticks`
de 1 para 2): "o target inicial deve ser de 2, depois tem que monitorar de
um em um [tick] pra ver ate onde foi".

Isto e' PESQUISA (medir candidatos, nao escolher um) -- a regra de QUANTO
recuar do pico pra fechar ainda nao foi decidida pelo dono. Varre N in
{0, 1, 2, 4} ticks de recuo tolerado desde o melhor preco alcancado DEPOIS
do piso de `profit_ticks=2` ser batido, contra o baseline ESTATICO atual
(T2/S16, `trailing_ativo=False`, o que ja esta' em producao hoje), nas DUAS
janelas pedidas:

  1. IS completo -- `data/raw_ticks/WDO_A_f1.parquet` filtro `janela=="IS"`
     (72 pregoes, 2.832.170 ticks, 2026-02-27..2026-06-12).
  2. Semana atual -- tick FRESCO do MT5, 2026-08-31..2026-09-04 (mesma
     funcao de `wdof1_mfe_mae_semana_2026_09_04.py::buscar_ticks_semana`).

Config de ENTRADA identica a producao (`level_spacing_ticks=1,
profit_ticks=2, stop_ticks=16`, com o fix do item 4.9 -- reancoragem
continua da ordem pendente -- ja embutido no DEFAULT da classe,
`reanchor_mode="rolling_last_price"`). So' a SAIDA por lucro muda entre as
5 variantes; `stop_ticks=16` nunca muda (o STOP e' gerido pelo motor do
jeito de sempre em toda variante, trailing ou nao).

## Por que a saida por trailing paga SLIPPAGE e o alvo estatico nao

Achado da investigacao do mecanismo (ver a docstring do parametro
`trailing_ativo` em `WdoGridReloadMaker.__init__`): o alvo ESTATICO fecha
como ordem MAKER (`target_fills_as_maker=True`, `IntradayExitReason.TARGET`,
zero slippage -- `machine.py::_close_position`, `is_maker_target = reason ==
TARGET and cfg.target_fills_as_maker`). O trailing fecha via `Exit()`
explicito da estrategia (`IntradayExitReason.SIGNAL`) -- que o motor SEMPRE
executa a MERCADO, pagando `slippage_ticks` (1 tick, padrao do perfil), a
MESMA saida que stop e flatten forcado ja pagavam. Ou seja: mesmo um
candidato N=0 que fechasse EXATAMENTE no piso, tick a tick, capturaria
sistematicamente menos liquido por trade que o alvo estatico, so' pelo
custo de execucao ser diferente (maker vs mercado) -- efeito real, medido
abaixo, nao hipotese.

## Colunas extra desta rodada

Alem da tabela padrao (`backtest.intraday.report`), para cada variante,
sobre os trades que NAO fecharam por STOP (um stop-out nunca chegou perto do
alvo, "quanto esticou" nao se aplica a ele):

  `ticks_alem_med` -- media de `ticks_capturados - profit_ticks` (ticks
      REAIS entre entrada e saida, ja com slippage/fill embutidos em
      `IntradayTrade.exit_price`) -- positivo quando o trailing esticou o
      lucro em media, negativo quando o atraso de 1 barra na execucao do
      `Exit` (anti-look-ahead: decisao na barra N executa na ABERTURA da
      barra N+1, nunca antes) devolveu mais do que ganhou.
  `no_piso_n` -- quantos fecharam com EXATAMENTE `profit_ticks` capturados
      (dentro de 1e-6 tick).
  `alem_n` -- quantos capturaram MAIS que o piso.
  `abaixo_n` -- quantos capturaram MENOS que o piso apesar de o PICO ter
      alcancado o piso (artefato do atraso de 1 barra na execucao do Exit
      -- so' pode ser > 0 quando `trailing_ativo=True`; no baseline
      estatico e' sempre 0 por construcao, o toque fecha exatamente no
      nivel).

Hipotese a CONFIRMAR (nao assumida -- autocorrelacao lag-1 de -0,44 medida
nesta mesma sessao no tape do WDO@, 89,3% dos ticks que se movem revertem o
anterior): N=0 deveria fechar quase sempre exatamente no piso (`no_piso_n`
alto, `ticks_alem_med` perto de 0 ou negativo por causa do slippage/atraso),
e N maiores deveriam capturar mais ticks por trade vencedor mas com menos
trades fechando favoravelmente (mais chance do preco reverter de verdade
antes do recuo tolerado, devolvendo o que tinha ganho ou virando stop).

Paralelismo: `ProcessPoolExecutor` com `submit`/`as_completed` (nunca
`pool.map`), uma tarefa por (janela, variante) -- 10 no total (5 variantes x
2 janelas). A janela SEMANA e' buscada UMA vez no processo PAI (MT5 so'
aceita conexao no processo que chama `mt5.initialize()`) e passada por
argumento (dataset pequeno, poucos dias); a janela IS e' lida do parquet
DENTRO de cada worker (dataset grande, 2,8M linhas -- ler 1x por processo,
nao serializar por IPC), mesmo padrao de
`scripts/daytrade/wdof1_defesa_recuo_sweep_2026_09_03.py`.

Uso: `python -u scripts/daytrade/wdof1_trailing_lucro_sweep_2026_09_04.py`
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CACHE_IS = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"

#: Capital REAL do slot ao vivo (WDO@, R$375 = margem R$150 x buffer 2.0 x
#: reserva 1.25 -- ver `LICOES_DE_PRODUCAO.md`/CLAUDE.md, "capital inicial
#: nunca arbitrario"), NAO o `CAPITAL_NOCIONAL` de calibracao do lab.
CAPITAL_REAL_BRL = 375.0

#: Config de ENTRADA de producao -- ver a docstring do modulo. Reutilizada
#: em toda variante, trailing ou nao.
CANDIDATO_PARAMS = dict(level_spacing_ticks=1, profit_ticks=2, stop_ticks=16)

#: Candidatos de recuo (N ticks desde o pico, apos o piso de 2 ser batido) --
#: pedido do dono, ver a docstring do modulo.
RECUO_GRID = (0, 1, 2, 4)

EXTRAS = ("ticks_alem_med", "no_piso_n", "alem_n", "abaixo_n")

#: Parquet IS lido UMA vez por PROCESSO (nao por tarefa).
_DF_IS_PROC = None


def _is_bars_do_processo() -> pd.DataFrame:
    global _DF_IS_PROC
    if _DF_IS_PROC is None:
        df = pd.read_parquet(CACHE_IS)
        is_df = df[df["janela"] == "IS"]
        _DF_IS_PROC = is_df[["open", "high", "low", "close", "volume"]]
    return _DF_IS_PROC


def _monta_specs() -> list[dict]:
    specs: list[dict] = []
    for janela in ("IS", "SEMANA"):
        specs.append(dict(
            janela=janela, rotulo=f"[{janela}] baseline estatico (T2/S16, sem trailing)",
            trailing_ativo=False, trailing_recuo_ticks=None,
        ))
        for n in RECUO_GRID:
            specs.append(dict(
                janela=janela, rotulo=f"[{janela}] trailing N={n}",
                trailing_ativo=True, trailing_recuo_ticks=n,
            ))
    return specs


def _stats_trailing(trades, tick_size: float, profit_ticks: int):
    """(`ticks_alem_med`, `no_piso_n`, `alem_n`, `abaixo_n`) sobre os trades
    que NAO fecharam por STOP -- ver a docstring do modulo para o porque
    (um stop-out nunca chegou perto do alvo, "quanto esticou" nao se
    aplica). `None` quando nao ha' nenhum trade nao-stop nesta variante."""
    from core.models import IntradayExitReason

    eps = 1e-6
    capturas = [
        abs(t.exit_price - t.entry_price) / tick_size
        for t in trades if t.exit_reason != IntradayExitReason.STOP
    ]
    if not capturas:
        return None, 0, 0, 0
    alem = [c - profit_ticks for c in capturas]
    no_piso_n = sum(1 for c in capturas if abs(c - profit_ticks) <= eps)
    alem_n = sum(1 for c in capturas if c > profit_ticks + eps)
    abaixo_n = sum(1 for c in capturas if c < profit_ticks - eps)
    media_alem = sum(alem) / len(alem)
    return media_alem, no_piso_n, alem_n, abaixo_n


def _roda_uma(spec: dict, semana_bars: pd.DataFrame | None) -> tuple[str, dict]:
    """Executado no processo FILHO (IS) ou passada direto (SEMANA, dataset
    pequeno). Devolve (texto_ja_formatado_da_linha, dict_leve) -- streaming
    na hora, remontagem da tabela final na ORDEM logica por fora."""
    sys.path.insert(0, str(RAIZ / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from wdo_grid_reload_f1_lab import montar_config, rodar
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    import dataclasses

    bars = _is_bars_do_processo() if spec["janela"] == "IS" else semana_bars
    cfg = dataclasses.replace(montar_config(), initial_capital=CAPITAL_REAL_BRL)

    kwargs = dict(CANDIDATO_PARAMS)
    if spec["trailing_ativo"]:
        kwargs["trailing_ativo"] = True
        kwargs["trailing_recuo_ticks"] = spec["trailing_recuo_ticks"]

    resultado = rodar(bars, cfg, **kwargs)
    media_alem, no_piso_n, alem_n, abaixo_n = _stats_trailing(
        resultado.trades, tick_size=0.5, profit_ticks=CANDIDATO_PARAMS["profit_ticks"],
    )

    extras = {
        "ticks_alem_med": "—" if media_alem is None else num_br(media_alem, 2),
        "no_piso_n": str(no_piso_n),
        "alem_n": str(alem_n),
        "abaixo_n": str(abaixo_n),
    }
    item = linha_de_resultado(
        spec["rotulo"], resultado, CAPITAL_REAL_BRL, capital_nocional=False, extras=extras,
    )

    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item, EXTRAS), flush=True)

    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, maxdd_brl=item.maxdd_brl,
        win_rate_pct=item.win_rate_pct, trades=item.trades, pregoes=item.pregoes,
        retorno_pct=item.retorno_pct, maxdd_pct=item.maxdd_pct, capital_final=item.capital_final,
        extras=item.extras, aviso=item.aviso, janela=spec["janela"],
    )
    return buf.getvalue(), campos


def main() -> None:
    if not CACHE_IS.exists():
        raise SystemExit(
            f"[wdof1_trailing_lucro_sweep] cache IS ausente: {CACHE_IS}\n"
            f"rode antes: scripts/daytrade/wdof1_tick_cache_2026_08_27.py"
        )
    from backtest.intraday.report import LinhaResultado, cabecalho, tabela
    from wdof1_mfe_mae_semana_2026_09_04 import buscar_ticks_semana

    t0 = time.perf_counter()

    print("[wdof1_trailing_lucro_sweep] buscando ticks frescos da semana "
          "(2026-08-31..2026-09-04) no MT5 ...", flush=True)
    try:
        semana_bars = buscar_ticks_semana()
        pregoes_semana = sorted(set(semana_bars.index.date))
        print(f"[wdof1_trailing_lucro_sweep] semana: {len(semana_bars):,} ticks, "
              f"{len(pregoes_semana)} pregoes: {pregoes_semana}", flush=True)
    except SystemExit as erro:
        print(f"[wdof1_trailing_lucro_sweep] AVISO -- sem MT5/tick fresco da semana "
              f"({erro}); rodando SO' a janela IS.", flush=True)
        semana_bars = None

    specs = _monta_specs()
    if semana_bars is None:
        specs = [s for s in specs if s["janela"] != "SEMANA"]

    n_workers = max(1, min(len(specs), os.cpu_count() or 4))
    print(f"[wdof1_trailing_lucro_sweep] {len(specs)} combinacoes, capital real "
          f"R${CAPITAL_REAL_BRL:.2f}, {n_workers} processos", flush=True)
    print(cabecalho(EXTRAS), flush=True)

    resultados_por_rotulo: dict[str, dict] = {}
    concluidos = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_roda_uma, spec, semana_bars if spec["janela"] == "SEMANA" else None): spec["rotulo"]
            for spec in specs
        }
        for future in as_completed(futures):
            concluidos += 1
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados_por_rotulo[futures[future]] = campos
            print(f"[wdof1_trailing_lucro_sweep] {concluidos}/{len(specs)} concluido(s) "
                  f"({futures[future]})", flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[wdof1_trailing_lucro_sweep] motor: {dt:.1f}s em {n_workers} processos\n")

    for janela in ("IS", "SEMANA"):
        campos_janela = [resultados_por_rotulo[s["rotulo"]] for s in specs if s["janela"] == janela]
        if not campos_janela:
            continue
        print(f"\n=== tabela final -- janela {janela} (baseline primeiro, depois N=0,1,2,4) ===")
        linhas_finais = [
            LinhaResultado(
                variante=c["variante"], liquido_brl=c["liquido_brl"], maxdd_brl=c["maxdd_brl"],
                win_rate_pct=c["win_rate_pct"], trades=c["trades"], pregoes=c["pregoes"],
                retorno_pct=c["retorno_pct"], maxdd_pct=c["maxdd_pct"], capital_final=c["capital_final"],
                extras=c["extras"], aviso=c["aviso"],
            )
            for c in campos_janela
        ]
        print(tabela(linhas_finais, EXTRAS))


if __name__ == "__main__":
    main()
