"""Varredura do corte por PERSISTENCIA no lado ADVERSO
(`CopaWin.corte_persistencia_ativo`, 2026-09-03, pedido do dono) em `CopaWin`
(WIN@, M1) -- versao CAUSAL do achado retrospectivo de `scripts/daytrade/
copawin_duracao_operacoes_2026_09_03.py` (secao bonus): "estar do lado
adverso por uma fracao alta das barras JA VIVIDAS desde a entrada
(`IntradayOpenPosition.bars_held`) prediz STOP com alta probabilidade -- feche
antes, com um prejuizo menor". Ver a docstring do parametro `corte_
persistencia_ativo` em `strategy.daytrade.lab.copa_win.CopaWin.__init__` para
a mecanica/formula exata -- este script so' varre e reporta.

## Diferenca do mecanismo IRMAO (`defesa_ativa`)

`defesa_ativa` (mesma classe, `copawin_defesa_recuo_sweep_2026_09_03.py`) mede
DISTANCIA de preco (chegou perto do stop, depois voltou perto do alvo).
`corte_persistencia` mede TEMPO/PERSISTENCIA (quanto tempo, em barras, a
posicao ja resistiu do lado errado) -- os dois sao mecanismos DIFERENTES,
coexistem como parametros independentes na mesma classe, e este script so'
varre o segundo (a combinacao dos dois e' o bonus, ao final, se sobrar tempo).

## DISCIPLINA IS/OOS -- diferente das rodadas exploratorias anteriores desta
## linha (`copawin_defesa_recuo_sweep_2026_09_03.py`, `copawin_duracao_
## operacoes_2026_09_03.py`, que rodaram no historico INTEIRO sem split)

Isto mexe numa regra de SAIDA de uma estrategia candidata a producao --
`backtest.intraday.frozen_split.LockedBars`, corte declarado no PERFIL do
WIN@ (`profile_for("WIN@").frozen_cutoff`, `OOS_CUTOFF = "2026-06-13"` em
`backtest/intraday/profiles.py`). `.in_sample()` e `.out_of_sample()` sao
SEMPRE reportados SEPARADOS, nunca so' a soma.

### AVISO METODOLOGICO -- repetir sempre que um numero de OOS parecer bom

Esta MESMA janela OOS (>= 2026-06-13) do WIN@ ja' foi usada pelo menos UMA VEZ
antes: na recalibracao de `alvo_vol=19,0`/`stop_vol=12,0` do proprio `CopaWin`,
confirmada em OOS em 2026-08-28 (ver o comentario perto de `CopaWin.name` em
`strategy/daytrade/registry.py`, e a memoria `copa-win-recalibracao-alvo-
stop-2026-08-28`). Ou seja: esta janela NAO e' mais um teste cego de verdade
para esta estrategia -- ja foi espiada uma vez para validar o par 19/12
(alvo/stop). Um resultado bom aqui no "OOS" e' evidencia MAIS FRACA do que um
OOS genuinamente nunca visto -- mesmo principio da memoria `copa-oos-gasto-
2026-08-26` (18 familias rodadas no OOS da Copa em 26/08, janela deixou de ser
cega para elas). Isto NAO invalida o numero, so' pesa menos do que um OOS
limpo pesaria.

## Dois niveis de capital (CLAUDE.md, "capital inicial nunca arbitrario"),
## MESMOS do sweep irmao `defesa_recuo`

- **R$434,00** -- capital REAL atual do slot `dt-copa_win-win@-shadow`.
- **R$3.000,00** -- nivel de FOLGA (`copawin_seguranca_capital_alto_2026_08_
  29.py`), livre do teto de capital.

Mesma economia (`trade_tick_value=0.20, trade_tick_size=1.0`), mesmo filtro de
sessoes completas (>= 400 barras M1/pregao).

## Grade

`corte_persistencia_min_barras` em [10, 20, 30, 45, 60, 90] x `corte_
persistencia_frac_adverso` em [0.6, 0.7, 0.8, 0.9, 1.0] -- 1.0 e' o valor
NEUTRO da classe (100% das barras passadas do lado adverso e' o extremo raro,
"quase nunca dispara sozinho"), incluido na grade como o canto "quase
desligado" dela. Mais 1 baseline SEPARADO (`corte_persistencia_ativo=False`,
byte-a-byte identico ao comportamento de antes desta rodada) -- mesmo desenho
de `copawin_defesa_recuo_sweep_2026_09_03.py` (1 baseline + N da grade).

30 combinacoes da grade + 1 baseline = 31 variantes, x 2 janelas (IS/OOS) x 2
niveis de capital = 124 tarefas.

## Paralelismo

`ProcessPoolExecutor` com `submit`/`as_completed` (nunca `pool.map`),
`redirect_stdout` por tarefa, `flush=True`, streaming (cada tarefa imprime a
linha dela assim que termina). N de processos reduzido de proposito (nao o
maximo de nucleos): a maquina tem robos de day trade/swing rodando AO VIVO
com dinheiro real (`dev.bat`) durante o horario normal de trabalho -- ver
`_n_workers()` abaixo.

Uso: `python scripts/daytrade/copawin_corte_persistencia_sweep_2026_09_03.py`
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

#: Economia do WIN@ (mesma referencia ja validada dos sweeps irmaos).
TRADE_TICK_VALUE = 0.20
TRADE_TICK_SIZE = 1.0

#: Dois niveis de capital, os dois justificados -- ver a docstring do modulo.
CAPITAL_REAL_BRL = 434.0
CAPITAL_FOLGA_BRL = 3_000.0
NIVEIS_CAPITAL = (CAPITAL_REAL_BRL, CAPITAL_FOLGA_BRL)

#: Grade pedida pelo dono: 6 x 5 = 30 combinacoes + 1 baseline, POR janela x
#: POR nivel de capital.
MIN_BARRAS_GRID = [10, 20, 30, 45, 60, 90]
FRAC_ADVERSO_GRID = [0.6, 0.7, 0.8, 0.9, 1.0]

#: Colunas EXTRA desta rodada -- entram DEPOIS das 12 da base
#: (`backtest/intraday/report.py`), nunca no lugar delas.
EXTRAS = ("corte_min", "corte_frac%", "corte_persist_n", "recusa_capital")

UNLOCK_REASON = (
    "Corte por persistencia (2026-09-03) mexe em regra de SAIDA de estrategia "
    "candidata a producao -- disciplina IS/OOS exigida por AGENTS.md/CLAUDE.md "
    "para 'melhorar estrategia'. Janela OOS ja' foi espiada antes (recalibracao "
    "alvo_vol/stop_vol confirmada em 2026-08-28) -- ver o aviso metodologico "
    "no relatorio final; isto NAO invalida o numero, so' pesa menos do que um "
    "OOS genuinamente nunca visto."
)

#: Barras M1 lidas UMA vez por PROCESSO (nao por tarefa).
_BARS_PROC: pd.DataFrame | None = None


def _bars_do_processo() -> pd.DataFrame:
    """Carrega e filtra as barras completas UMA vez por processo filho, e
    devolve o split IS/OOS ja' DESTRAVADO (o motivo do destravamento e'
    documentado uma unica vez em `UNLOCK_REASON`, reaproveitado por todo
    processo)."""
    global _BARS_PROC
    if _BARS_PROC is None:
        sys.path.insert(0, str(RAIZ / "src"))
        from backtest.intraday.frozen_split import LockedBars, declare_frozen_split
        from backtest.intraday.profiles import profile_for
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_M1_FUTURO}
        df = df[[d in completos for d in df.index.date]]

        profile = profile_for(SYMBOL)
        split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
        locked = LockedBars(df, split)
        locked.unlock(UNLOCK_REASON)
        _BARS_PROC = locked
    return _BARS_PROC


def _kwargs_producao() -> dict:
    """Le os kwargs de PRODUCAO de uma instancia default (`get_daytrade_
    robot`), em vez de redigita-los aqui -- um numero declarado em dois
    lugares e' um numero que vai divergir (mesmo argumento de `backtest/
    intraday/profiles.py`)."""
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
    """(1 baseline + 30 da grade) x 2 janelas x 2 niveis de capital = 124."""
    specs: list[dict] = []
    for capital in NIVEIS_CAPITAL:
        rotulo_capital = f"R${br(capital, 0)}"
        for janela in ("IS", "OOS"):
            specs.append(dict(
                rotulo=f"{rotulo_capital} {janela} baseline (corte off)",
                capital=capital, janela=janela,
                corte_ativo=False, min_barras=None, frac_adverso=None,
            ))
            for min_barras in MIN_BARRAS_GRID:
                for frac_adverso in FRAC_ADVERSO_GRID:
                    specs.append(dict(
                        rotulo=f"{rotulo_capital} {janela} m{min_barras} f{frac_adverso*100:.0f}%",
                        capital=capital, janela=janela, corte_ativo=True,
                        min_barras=min_barras, frac_adverso=frac_adverso,
                    ))
    return specs


def _roda_uma(spec: dict) -> tuple[str, dict]:
    """Executado no processo FILHO. Devolve (texto_ja_formatado_da_linha,
    dict_leve_com_os_campos_da_LinhaResultado) -- o pai imprime o texto na
    hora (streaming) e usa o dict pra remontar as tabelas finais na ORDEM
    logica, que a ordem de conclusao do pool nao garante."""
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from core.models import IntradayExitReason
    from strategy.daytrade.lab.copa_win import CopaWin

    locked = _bars_do_processo()
    bars = locked.in_sample() if spec["janela"] == "IS" else locked.out_of_sample()
    profile = profile_for(SYMBOL)

    kwargs = _kwargs_producao()
    if spec["corte_ativo"]:
        kwargs.update(
            corte_persistencia_ativo=True,
            corte_persistencia_min_barras=spec["min_barras"],
            corte_persistencia_frac_adverso=spec["frac_adverso"],
        )
    strat = CopaWin(**kwargs)
    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=spec["capital"], target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )

    resultado = run_intraday_backtest(bars, strat, cfg)
    n_corte = sum(1 for t in resultado.trades if t.exit_reason == IntradayExitReason.SIGNAL)

    extras = {
        "corte_min": "—" if spec["min_barras"] is None else str(spec["min_barras"]),
        "corte_frac%": "—" if spec["frac_adverso"] is None else num_br(spec["frac_adverso"] * 100, 0),
        "corte_persist_n": str(n_corte),
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
        extras=item.extras, aviso=item.aviso, n_corte=n_corte,
        capital=spec["capital"], janela=spec["janela"],
        eh_baseline=(not spec["corte_ativo"]),
        min_barras=spec["min_barras"], frac_adverso=spec["frac_adverso"],
    )
    return buf.getvalue(), campos


def _n_workers(n_tarefas: int) -> int:
    """Reduzido de proposito -- a maquina roda robos de day trade/swing AO
    VIVO com dinheiro real (`dev.bat`), e este sweep nao deve disputar CPU com
    eles. Nunca mais que 6, mesmo com nucleos sobrando."""
    return max(1, min(n_tarefas, 6, os.cpu_count() or 4))


def main() -> None:
    from backtest.intraday.report import LinhaResultado, cabecalho, num_br, tabela

    t0 = time.perf_counter()
    specs = _monta_specs()
    n_workers = _n_workers(len(specs))
    print(f"[copawin_corte_persistencia_sweep] {len(specs)} tarefas "
          f"({len(NIVEIS_CAPITAL)} capitais x 2 janelas x 31 variantes), "
          f"{n_workers} processos", flush=True)
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
            print(f"[copawin_corte_persistencia_sweep] {concluidos}/{len(specs)} concluido(s) "
                  f"({futures[future]})", flush=True)

    dt = time.perf_counter() - t0
    print(f"\n[copawin_corte_persistencia_sweep] motor: {dt:.1f}s em {n_workers} processos\n")

    print("=" * 90)
    print("AVISO METODOLOGICO (repetido -- nao e' opcional): a janela OOS "
          "(>=2026-06-13) do WIN@ ja' foi espiada antes, na recalibracao "
          "alvo_vol=19,0/stop_vol=12,0 confirmada em OOS em 2026-08-28 "
          "(`strategy/daytrade/registry.py`, memoria "
          "`copa-win-recalibracao-alvo-stop-2026-08-28`). Um resultado bom no "
          "OOS abaixo e' evidencia MAIS FRACA do que um OOS genuinamente nunca "
          "visto -- mesmo principio de `copa-oos-gasto-2026-08-26`.")
    print("=" * 90)

    melhores: dict[float, dict] = {}
    for capital in NIVEIS_CAPITAL:
        rotulo_cap = f"R${br(capital, 2)}"
        print(f"\n{'#'*90}\ncapital inicial {rotulo_cap}\n{'#'*90}")

        campos_por_janela: dict[str, list[dict]] = {"IS": [], "OOS": []}
        for spec in specs:
            if spec["capital"] != capital:
                continue
            campos_por_janela[spec["janela"]].append(resultados_por_rotulo[spec["rotulo"]])

        for janela in ("IS", "OOS"):
            campos = campos_por_janela[janela]
            linhas = [
                LinhaResultado(
                    variante=c["variante"], liquido_brl=c["liquido_brl"], maxdd_brl=c["maxdd_brl"],
                    win_rate_pct=c["win_rate_pct"], trades=c["trades"], pregoes=c["pregoes"],
                    retorno_pct=c["retorno_pct"], maxdd_pct=c["maxdd_pct"],
                    capital_final=c["capital_final"], extras=c["extras"], aviso=c["aviso"],
                )
                for c in campos
            ]
            print(f"\n=== {rotulo_cap} -- janela {janela} ===")
            print(tabela(linhas, EXTRAS))

        # ---- comparacao lado a lado IS vs OOS, combo a combo ----------------
        is_por_chave = {(c["min_barras"], c["frac_adverso"]): c for c in campos_por_janela["IS"]}
        oos_por_chave = {(c["min_barras"], c["frac_adverso"]): c for c in campos_por_janela["OOS"]}
        chaves_grade = [(m, f) for m in MIN_BARRAS_GRID for f in FRAC_ADVERSO_GRID]

        print(f"\n--- {rotulo_cap}: IS vs OOS lado a lado (grade completa) ---")
        cab = (f"{'variante':<18}{'IS liquido':>14}{'IS trd':>8}{'IS corte_n':>12}"
               f"{'OOS liquido':>14}{'OOS trd':>9}{'OOS corte_n':>13}")
        print(cab)
        print("-" * len(cab))
        baseline_is = is_por_chave.get((None, None)) or next(
            c for c in campos_por_janela["IS"] if c["eh_baseline"])
        baseline_oos = oos_por_chave.get((None, None)) or next(
            c for c in campos_por_janela["OOS"] if c["eh_baseline"])
        print(f"{'baseline (off)':<18}{('R$'+num_br(baseline_is['liquido_brl'])):>14}"
              f"{baseline_is['trades']:>8}{baseline_is['n_corte']:>12}"
              f"{('R$'+num_br(baseline_oos['liquido_brl'])):>14}{baseline_oos['trades']:>9}"
              f"{baseline_oos['n_corte']:>13}")
        for m, f in chaves_grade:
            ci = is_por_chave[(m, f)]
            co = oos_por_chave[(m, f)]
            rotulo_combo = f"m{m} f{f*100:.0f}%"
            print(f"{rotulo_combo:<18}{('R$'+num_br(ci['liquido_brl'])):>14}"
                  f"{ci['trades']:>8}{ci['n_corte']:>12}"
                  f"{('R$'+num_br(co['liquido_brl'])):>14}{co['trades']:>9}"
                  f"{co['n_corte']:>13}")

        # ---- melhor combinacao POR JANELA (escolhida DENTRO da propria janela) ----
        melhor_is = max((is_por_chave[k] for k in chaves_grade), key=lambda c: c["liquido_brl"])
        melhor_oos = max((oos_por_chave[k] for k in chaves_grade), key=lambda c: c["liquido_brl"])
        print(f"\n[diagnostico {rotulo_cap}] baseline IS: liquido=R${br(baseline_is['liquido_brl'])} "
              f"({baseline_is['trades']} trades) | baseline OOS: liquido=R${br(baseline_oos['liquido_brl'])} "
              f"({baseline_oos['trades']} trades)")
        print(f"[diagnostico {rotulo_cap}] MELHOR combo NO IS: m{melhor_is['min_barras']} "
              f"f{melhor_is['frac_adverso']*100:.0f}% -> IS=R${br(melhor_is['liquido_brl'])} "
              f"(vs baseline IS R${br(baseline_is['liquido_brl'])}); a MESMA combinacao no OOS: "
              f"R${br(oos_por_chave[(melhor_is['min_barras'], melhor_is['frac_adverso'])]['liquido_brl'])} "
              f"(vs baseline OOS R${br(baseline_oos['liquido_brl'])})")
        print(f"[diagnostico {rotulo_cap}] MELHOR combo NO OOS (referencia -- OOS JA FOI ESPIADO, "
              f"ver aviso metodologico): m{melhor_oos['min_barras']} f{melhor_oos['frac_adverso']*100:.0f}% "
              f"-> OOS=R${br(melhor_oos['liquido_brl'])} (vs baseline OOS R${br(baseline_oos['liquido_brl'])}); "
              f"a MESMA combinacao no IS: "
              f"R${br(is_por_chave[(melhor_oos['min_barras'], melhor_oos['frac_adverso'])]['liquido_brl'])} "
              f"(vs baseline IS R${br(baseline_is['liquido_brl'])})")

        melhores[capital] = dict(melhor_is=melhor_is, melhor_oos=melhor_oos,
                                  baseline_is=baseline_is, baseline_oos=baseline_oos)

    print(f"\n{'='*90}\nAVISO METODOLOGICO (repetido de novo, de proposito -- nao e' rodape "
          "decorativo): qualquer numero 'bom' de OOS acima descreve uma janela que ja' foi "
          "espiada antes (recalibracao alvo_vol/stop_vol de 2026-08-28). Trate como confirmacao "
          "mais fraca do que um OOS nunca visto, nao como validacao independente.")
    print(f"\n[copawin_corte_persistencia_sweep] total: {time.perf_counter() - t0:.1f}s")


# ============================================================================
# BONUS (pedido do dono, "so' se sobrar tempo"): a COMBINACAO de `corte_
# persistencia` com `defesa_ativa` (mecanismo IRMAO, ja existente na mesma
# classe, distancia de preco em vez de tempo/persistencia) e' complementar ou
# redundante? `--bonus` na linha de comando roda so' esta secao.
#
# `defesa_gatilho_stop_pct=0.20, defesa_alvo_proximidade_pct=0.10` NAO e'
# chute -- e' o melhor combo medido por `copawin_defesa_recuo_sweep_2026_09_
# 03.py` no historico COMBINADO (aquele script nao faz split IS/OOS): R$3.000
# g20% a10% -> R$12.808,00 vs baseline R$9.830,00 (rodado de novo agora para
# conferencia, ver a saida deste script com `--bonus`). Em R$434 o mesmo
# sweep achou 0 disparos de `defesa_recuo` na grade inteira -- o piso de
# capital real do CopaWin (~R$750, ver a memoria `copawin-e-gremah-piso-
# capital-2026-08-29`) deixa poucos trades acontecerem ali, e' esperado.
BONUS_DEFESA_GATILHO = 0.20
BONUS_DEFESA_ALVO_PROX = 0.10

#: 3 candidatos de `corte_persistencia` -- desligado, o "melhor no IS" (mais
#: extremo/possivelmente overfit) e um "robusto" que melhorou IS E OOS ao
#: mesmo tempo na varredura principal (ver o relatorio final) -- combinados
#: com `defesa_ativa` ligado/desligado, 3 x 2 x 2 janelas x 2 capitais = 24
#: tarefas.
BONUS_CORTE_CANDIDATOS = [
    ("off", False, None, None),
    ("melhor_is (m10 f100%)", True, 10, 1.0),
    ("robusto (m20 f60%)", True, 20, 0.6),
]


def _roda_uma_bonus(spec: dict) -> tuple[str, dict]:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from backtest.intraday.report import linha, linha_de_resultado, num_br
    from core.models import IntradayExitReason
    from strategy.daytrade.lab.copa_win import CopaWin

    locked = _bars_do_processo()
    bars = locked.in_sample() if spec["janela"] == "IS" else locked.out_of_sample()
    profile = profile_for(SYMBOL)

    kwargs = _kwargs_producao()
    if spec["corte_ativo"]:
        kwargs.update(
            corte_persistencia_ativo=True,
            corte_persistencia_min_barras=spec["min_barras"],
            corte_persistencia_frac_adverso=spec["frac_adverso"],
        )
    if spec["defesa_ativa"]:
        kwargs.update(
            defesa_ativa=True,
            defesa_gatilho_stop_pct=BONUS_DEFESA_GATILHO,
            defesa_alvo_proximidade_pct=BONUS_DEFESA_ALVO_PROX,
        )
    strat = CopaWin(**kwargs)
    cfg = config_for(
        profile, trade_tick_value=TRADE_TICK_VALUE, trade_tick_size=TRADE_TICK_SIZE,
        initial_capital=spec["capital"], target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    resultado = run_intraday_backtest(bars, strat, cfg)
    n_corte = sum(1 for t in resultado.trades if t.exit_reason == IntradayExitReason.SIGNAL)
    extras = {
        "corte_min": "—" if spec["min_barras"] is None else str(spec["min_barras"]),
        "corte_frac%": "—" if spec["frac_adverso"] is None else num_br(spec["frac_adverso"] * 100, 0),
        "corte_persist_n": str(n_corte),
        "recusa_capital": str(resultado.ordens_recusadas_por_capital),
    }
    item = linha_de_resultado(
        spec["rotulo"], resultado, spec["capital"], capital_nocional=False, extras=extras,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(linha(item, EXTRAS), flush=True)
    campos = dict(
        variante=item.variante, liquido_brl=item.liquido_brl, trades=item.trades,
        n_corte=n_corte, capital=spec["capital"], janela=spec["janela"],
        corte_rotulo=spec["corte_rotulo"], defesa_ativa=spec["defesa_ativa"],
    )
    return buf.getvalue(), campos


def main_bonus() -> None:
    from backtest.intraday.report import cabecalho

    t0 = time.perf_counter()
    specs: list[dict] = []
    for capital in NIVEIS_CAPITAL:
        for janela in ("IS", "OOS"):
            for corte_rotulo, corte_ativo, min_barras, frac_adverso in BONUS_CORTE_CANDIDATOS:
                for defesa_lig in (False, True):
                    rotulo = (f"R${br(capital, 0)} {janela} corte={corte_rotulo} "
                              f"defesa={'ON' if defesa_lig else 'off'}")
                    specs.append(dict(
                        rotulo=rotulo, capital=capital, janela=janela,
                        corte_ativo=corte_ativo, min_barras=min_barras, frac_adverso=frac_adverso,
                        corte_rotulo=corte_rotulo, defesa_ativa=defesa_lig,
                    ))

    n_workers = _n_workers(len(specs))
    print(f"[bonus] {len(specs)} tarefas (combinacao corte_persistencia x defesa_ativa), "
          f"{n_workers} processos", flush=True)
    print(cabecalho(EXTRAS), flush=True)

    resultados: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_roda_uma_bonus, spec): spec["rotulo"] for spec in specs}
        concluidos = 0
        for future in as_completed(futures):
            concluidos += 1
            texto, campos = future.result()
            print(texto, end="", flush=True)
            resultados[futures[future]] = campos
            print(f"[bonus] {concluidos}/{len(specs)} concluido(s)", flush=True)

    print(f"\n[bonus] motor: {time.perf_counter() - t0:.1f}s\n")
    print("=" * 90)
    print("AVISO METODOLOGICO (vale aqui tambem): a janela OOS ja' foi espiada antes "
          "(recalibracao alvo_vol/stop_vol confirmada em 2026-08-28) -- resultado bom no OOS "
          "e' confirmacao mais fraca do que um OOS nunca visto.")
    print("=" * 90)

    for capital in NIVEIS_CAPITAL:
        rotulo_cap = f"R${br(capital, 0)}"
        print(f"\n--- {rotulo_cap}: corte_persistencia x defesa_ativa, IS e OOS lado a lado ---")
        cab = (f"{'corte':<26}{'defesa':<8}{'IS liquido':>14}{'IS trd':>8}"
               f"{'OOS liquido':>14}{'OOS trd':>9}")
        print(cab)
        print("-" * len(cab))
        for corte_rotulo, *_ in BONUS_CORTE_CANDIDATOS:
            for defesa_lig in (False, True):
                ci = resultados[f"{rotulo_cap} IS corte={corte_rotulo} defesa={'ON' if defesa_lig else 'off'}"]
                co = resultados[f"{rotulo_cap} OOS corte={corte_rotulo} defesa={'ON' if defesa_lig else 'off'}"]
                print(f"{corte_rotulo:<26}{('ON' if defesa_lig else 'off'):<8}"
                      f"{('R$'+br(ci['liquido_brl'])):>14}{ci['trades']:>8}"
                      f"{('R$'+br(co['liquido_brl'])):>14}{co['trades']:>9}")

    print(f"\n[bonus] total: {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    if "--bonus" in sys.argv:
        main_bonus()
    else:
        main()
