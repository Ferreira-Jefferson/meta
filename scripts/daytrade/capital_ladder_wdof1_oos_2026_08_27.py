"""Escada de capital da `WdoGridReloadMaker` F1 (WDO@, "T1 S16 x1") --
CONFIRMACAO OOS, 2026-08-27. Primeira vez que o trecho >=2026-06-13 e'
aberto para esta estrategia -- autorizado explicitamente pelo dono para
consolidar capital/sinal antes de atualizar producao.

MESMA estrutura/formula de `capital_ladder_wdof1_2026_08_27.py` (importado
como `C` abaixo, reaproveitando `busca_capital_minimo`/`n_zerou`/
`maxdd_sementes`/`salva_trade_log`/TODAS as constantes de missao -- NENHUMA
logica de bisseccao/rejeicao reescrita). So' o dado de entrada (barras) e o
resultado sao novos aqui.

## Correcao de margem (JA aplicada e documentada hoje, mesma formula)

`capital_ladder_qualidade_sinal_reversao_2026_08_27` (memoria): a escada
original so' checava `capital_inicial + pnl_acumulado <= 0`, nunca se o
capital cobriria a MARGEM pra abrir a posicao. Correcao (aditiva, sem
rerodar a busca):

    capital_minimo_real(N) = capital_minimo_seguro_medido(N) + piso_ingenuo(N)

valido porque a curva de equity e' um deslocamento aditivo puro. Aplicada
aqui nos DOIS casos (OOS-only, combinado).

## Dois casos, SEMPRE reportados os dois (pedido explicito da missao)

  (a) OOS-only: `wdo_grid_reload_f1_tick_lab_oos_2026_08_27.carregar_oos_bars()`
      -- 51 pregoes (2026-06-15..2026-08-25), tick nos 49 com tick real no
      MT5 + M1 (volume normalizado para a MESMA coluna/formula do tick --
      ver o BUG achado e corrigido na docstring daquele modulo: concat
      naive de tick+M1 zerava `bar.volume` via NaN e derrubava os 49 dias
      de tick a ZERO trades, silenciosamente) nos 2 sem tick (2026-08-03/
      04 -- ver tambem ali a prova de que o fallback M1 e' CONSERVADOR,
      nunca otimista).
  (b) IS+OOS combinado: 72 pregoes IS-tick (`wdo_grid_reload_f1_tick_lab.
      carregar_tick_bars()`, reimportada aqui SEM rerodar a busca no MT5)
      + os 51 pregoes OOS acima = 123 pregoes.

## Atalho VALIDADO empiricamente nesta rodada: combinado = concatenacao de
## trade LISTS, NAO precisa rerodar o motor sobre os 123 dias juntos

`WdoGridReloadMaker` (modo ESTATICO, `margin_per_contract_brl=None`) nao
tem NENHUM estado que atravesse a fronteira de sessao: `on_session_start`
reseta `self._state` (`_SessionState`) inteiro a cada dia, e a classe NAO
sobrescreve `seed_volume_window`/`seed_daily_volatility`/
`seed_typical_trade_size` (os 3 ganchos que `run_intraday_backtest` usa
para passar o RABO da sessao anterior adiante, ver `engine.py:200-226`) --
ficam no no-op default de `IntradayStrategy`. `on_capital_update` tambem
nao afeta nada no modo estatico (`_quantidade_da_entrada` devolve
`self.quantity` direto quando `margin_per_contract_brl is None`, nunca le
`self._cash_atual_brl`). Ou seja: os trades de UMA sessao dependem SO' dos
proprios dados daquela sessao + `quantity=n` (constante) -- rodar 123 dias
de uma vez ou rodar 72 + 51 separadamente e' MATEMATICAMENTE identico,
trade a trade.

PROVADO (nao so' argumentado) nesta rodada: peguei os 2 ULTIMOS dias do
IS-tick (2026-06-11/12) + os 2 PRIMEIROS dias do OOS-tick (2026-06-15/16) e
comparei (a) rodar os 4 dias JUNTOS numa unica chamada de `G.rodar` contra
(b) rodar os 2+2 dias SEPARADOS e concatenar as listas de trade -- 170
trades nos dois casos, byte-a-byte identicos (mesmo `entry_ts`/`exit_ts`/
`side`/precos/`quantity`/`pnl_brl` em cada posicao da lista). Exatamente a
fronteira IS->OOS que importaria se houvesse vazamento de estado entre
sessoes -- nao ha'.

Consequencia pratica: cada N precisa de SO' 2 rodadas reais de motor
(IS-tick inteiro + OOS-mixed inteiro), NUNCA uma 3a rodada de 123 dias --
economiza ~23% do trabalho do motor por N (evita reprocessar os 72 dias do
IS uma SEGUNDA vez dentro de um dataframe combinado de 123 dias) e permite
paralelizar por N sem precisar materializar/psar um dataframe gigante de
123 dias entre processos.

## Paralelizacao por N (`ProcessPoolExecutor`, padrao do repo -- "nunca
## serial", ver `feedback_parallelize_sweeps`)

Cada N (1..10) roda em processo separado (`_init_worker` le' os dois
dataframes UMA VEZ por worker, de parquet -- nao via MT5 de novo, nao via
pickle gigante por tarefa). `max_workers` deliberadamente baixo (4): a
maquina tem 12 threads logicas mas esta' COMPARTILHADA com outras sessoes
concorrentes rodando as MESMAS frentes de confirmacao OOS para outras
estrategias (CopaWin/Gremah/GremahTick, arquivos irmaos `*_oos_2026_08_27.
py` vistos no working tree) -- usar todos os nucleos aqui derrubaria o
progresso alheio sem necessidade.

## Medicao empirica de velocidade -- por que a rodada tick e' mais lenta
## hoje do que a nota de `capital_ladder_wdof1_2026_08_27.py` (~125s/2,83M
## ticks) sugeria

Medido com `on_progress` (diagnostico desta rodada, script descartavel):
~4.000-8.000 linhas/s nesta maquina agora (vs a ~22.640 linhas/s implicita
naquela nota) -- provavelmente contencao de CPU com as outras sessoes
concorrentes citadas acima. Nao e' um bug: o numero de trades bate (1.667
no subconjunto tick de 49 dias, MaxDD/win-rate na faixa esperada) e a
COBERTURA por dia bate (`_checa_cobertura_dias` abaixo) -- so' o tempo de
parede mudou. Justifica a paralelizacao, nao muda nenhum resultado.

Uso: `python -u scripts/daytrade/capital_ladder_wdof1_oos_2026_08_27.py`
"""
from __future__ import annotations

import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import num_br  # noqa: E402

import capital_ladder_wdof1_2026_08_27 as C  # noqa: E402
import wdo_grid_reload_f1_lab as G  # noqa: E402
import wdo_grid_reload_f1_tick_lab as GT  # noqa: E402
from wdo_grid_reload_f1_tick_lab_oos_2026_08_27 import (  # noqa: E402
    OOS_UNLOCK_REASON,
    carregar_oos_bars,
)

OUT_DIR = ROOT / "scripts" / "daytrade"
SCRATCH_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\dee7aec5-41bc-4072-aa99-90f7fdf10599\scratchpad"
)
IS_BARS_PARQUET = SCRATCH_DIR / "wdof1_is_tick_bars_2026_08_27.parquet"
OOS_BARS_PARQUET = SCRATCH_DIR / "wdof1_oos_bars_mixed_2026_08_27.parquet"

TRADE_LOG_N1_OOS_CSV = OUT_DIR / "capital_ladder_wdof1_n1_trades_oos_2026_08_27.csv"
TRADE_LOG_N1_COMBINADO_CSV = OUT_DIR / "capital_ladder_wdof1_n1_trades_is_oos_combinado_2026_08_27.csv"
RESULT_JSON = OUT_DIR / "capital_ladder_wdof1_oos_result_2026_08_27.json"

MAX_WORKERS = 4


# ---------------------------------------------------------------------------
# worker (processo separado por N) -- ver docstring do modulo para a prova
# de que combinado = concatenacao de trade lists, nenhuma 3a rodada de 123
# dias necessaria.
# ---------------------------------------------------------------------------

_WORKER_BARS: dict = {}


def _init_worker(is_parquet: str, oos_parquet: str) -> None:
    import pandas as pd
    _WORKER_BARS["is"] = pd.read_parquet(is_parquet)
    _WORKER_BARS["oos"] = pd.read_parquet(oos_parquet)


def _run_n(n: int) -> dict:
    """Roda o motor DUAS vezes (IS-tick inteiro, OOS-mixed inteiro) para
    este `n` -- `C.roda_base` reaproveitado sem alteracao (mesma config
    nocional + `TETO_MOTOR_FIXO`)."""
    is_bars = _WORKER_BARS["is"]
    oos_bars = _WORKER_BARS["oos"]
    resultado_is = C.roda_base(n, is_bars)
    resultado_oos = C.roda_base(n, oos_bars)
    return dict(
        n=n,
        trades_is=list(resultado_is.trades),
        trades_oos=list(resultado_oos.trades),
        ordens_recusadas_is=resultado_is.ordens_recusadas_por_teto,
        ordens_recusadas_oos=resultado_oos.ordens_recusadas_por_teto,
    )


def _checa_quantity(trades: list, n: int, rotulo: str) -> None:
    if trades and any(t.quantity != n for t in trades):
        qtds = sorted({t.quantity for t in trades})
        print(f"    [diag][{rotulo}][N={n}] AVISO: quantity dos trades nao e' uniformemente {n} -- "
              f"valores observados: {qtds} (fill parcial por volume insuficiente?)")


def _checa_cobertura_dias(trades: list, n_dias_esperado: int, n: int, rotulo: str) -> None:
    """Salva-guarda contra a MESMA classe de bug achada e corrigida nesta
    rodada (`wdo_grid_reload_f1_tick_lab_oos_2026_08_27.py`: concat naive de
    tick+M1 zerava `bar.volume` via `real_volume`/`tick_volume` = NaN nas
    linhas tick, `limit_fill_capped_by_volume=True` nunca preenchia nada, e
    49/51 pregoes ficavam SILENCIOSAMENTE sem NENHUM trade -- sem excecao,
    sem AVISO, so' um numero de trades anormalmente baixo). Nao prova que o
    resultado esta certo, mas um numero de dias-com-trade muito abaixo do
    esperado e' o MESMO sintoma que expos o bug -- alerta alto e imprime o
    detalhe por dia em vez de deixar passar batido."""
    dias_com_trade = {t.entry_ts.date() for t in trades}
    if len(dias_com_trade) < 0.5 * n_dias_esperado:
        print(f"    [diag][{rotulo}][N={n}] AVISO SERIO: so' {len(dias_com_trade)}/{n_dias_esperado} "
              f"pregoes tem pelo menos 1 trade (<50%) -- mesmo sintoma do bug de volume NaN achado "
              f"nesta rodada, CONFERIR antes de confiar neste numero.")


def main() -> None:
    print(f"[capital_ladder_wdof1_oos] motivo de destravamento do OOS: {OOS_UNLOCK_REASON!r}\n")

    print("[capital_ladder_wdof1_oos] carregando IS-tick (reuso, sem rerodar busca no MT5 -- "
          "mesma funcao de capital_ladder_wdof1_2026_08_27.py)...")
    dias_is, is_tick_bars = GT.carregar_tick_bars()

    print("\n[capital_ladder_wdof1_oos] carregando OOS (tick + fallback M1, ja' corrigido)...")
    oos = carregar_oos_bars()
    oos_bars = oos["bars_mixed"]
    print(f"[capital_ladder_wdof1_oos] OOS: {len(oos['dias_oos'])} pregoes "
          f"({oos['dias_oos'][0]} -> {oos['dias_oos'][-1]}), "
          f"{len(oos['dias_tick'])} com tick real, fallback M1 em {oos['dias_m1_fallback']}")

    dias_combinado = sorted(set(is_tick_bars.index.date) | set(oos_bars.index.date))
    print(f"[capital_ladder_wdof1_oos] combinado (IS-tick + OOS, via concatenacao de trade lists "
          f"validada -- ver docstring do modulo): {len(dias_combinado)} pregoes, "
          f"{dias_combinado[0]} -> {dias_combinado[-1]}\n")

    print(f"[capital_ladder_wdof1_oos] margem/contrato=R${num_br(C.MARGEM_CONTRATO_BRL, 0)} | "
          f"MARGIN_BUFFER_FUTUROS={C.MARGIN_BUFFER_FUTUROS} | teto do MOTOR (fixo, todo N)={C.TETO_MOTOR_FIXO}")
    print(f"[capital_ladder_wdof1_oos] rejeicao i.i.d. p={num_br(C.P_REJEICAO * 100, 0)}%, "
          f"{C.N_SEMENTES} sementes (seed_base={C.SEED_BASE}) -- MESMO metodo do IS")
    print(f"[capital_ladder_wdof1_oos] paralelizando N=1..10 com {MAX_WORKERS} processos "
          f"(cada N roda IS-tick + OOS-mixed 1x cada, combinado sai por concatenacao)\n")

    is_tick_bars.to_parquet(IS_BARS_PARQUET)
    oos_bars.to_parquet(OOS_BARS_PARQUET)

    resultados_por_n: dict[int, dict] = {}
    with ProcessPoolExecutor(
        max_workers=MAX_WORKERS, initializer=_init_worker,
        initargs=(str(IS_BARS_PARQUET), str(OOS_BARS_PARQUET)),
    ) as pool:
        futuros = {pool.submit(_run_n, n): n for n in C.N_VALUES}
        for fut in as_completed(futuros):
            r = fut.result()
            resultados_por_n[r["n"]] = r
            print(f"[capital_ladder_wdof1_oos] motor OK -- N={r['n']:>2} | "
                  f"trades IS={len(r['trades_is']):>5} | trades OOS={len(r['trades_oos']):>5}", flush=True)

    linhas: list[dict] = []

    for n in C.N_VALUES:
        r = resultados_por_n[n]
        trades_is = r["trades_is"]
        trades_oos = r["trades_oos"]
        trades_comb = sorted(trades_is + trades_oos, key=lambda t: t.entry_ts)

        _checa_quantity(trades_oos, n, "OOS-only")
        _checa_cobertura_dias(trades_oos, len(oos["dias_oos"]), n, "OOS-only")
        _checa_quantity(trades_comb, n, "combinado")
        _checa_cobertura_dias(trades_comb, len(dias_combinado), n, "combinado")

        if n == 1:
            C.salva_trade_log(trades_oos, TRADE_LOG_N1_OOS_CSV)
            C.salva_trade_log(trades_comb, TRADE_LOG_N1_COMBINADO_CSV)
            print(f"[capital_ladder_wdof1_oos] N=1: trade logs salvos em {TRADE_LOG_N1_OOS_CSV} "
                  f"({len(trades_oos)} trades) e {TRADE_LOG_N1_COMBINADO_CSV} ({len(trades_comb)} trades)")

        piso_ingenuo = n * C.MARGEM_CONTRATO_BRL * C.MARGIN_BUFFER_FUTUROS
        excede_teto_copa = n > C.TETO_OFICIAL_COPA_BTG

        seguro_oos, inseguro_oos = C.busca_capital_minimo(trades_oos, piso_ingenuo)
        real_oos = seguro_oos + piso_ingenuo
        dds_oos = C.maxdd_sementes(trades_oos, seguro_oos)
        zerou_oos = C.n_zerou(trades_oos, seguro_oos)

        seguro_comb, inseguro_comb = C.busca_capital_minimo(trades_comb, piso_ingenuo)
        real_comb = seguro_comb + piso_ingenuo
        dds_comb = C.maxdd_sementes(trades_comb, seguro_comb)
        zerou_comb = C.n_zerou(trades_comb, seguro_comb)

        linha = dict(
            n=n, piso_ingenuo_brl=piso_ingenuo, excede_teto_copa_btg=excede_teto_copa,
            oos=dict(
                trades=len(trades_oos), capital_minimo_seguro_medido_brl=seguro_oos,
                capital_minimo_real_brl=real_oos, ultimo_inseguro_conhecido_brl=inseguro_oos,
                maxdd_media_brl=float(dds_oos.mean()),
                maxdd_std_brl=float(dds_oos.std(ddof=1)) if len(dds_oos) > 1 else 0.0,
                maxdd_pior_semente_brl=float(dds_oos.max()),
                zerou_no_seguro=zerou_oos,
                ordens_recusadas_por_teto=r["ordens_recusadas_oos"],
            ),
            combinado=dict(
                trades=len(trades_comb), capital_minimo_seguro_medido_brl=seguro_comb,
                capital_minimo_real_brl=real_comb, ultimo_inseguro_conhecido_brl=inseguro_comb,
                maxdd_media_brl=float(dds_comb.mean()),
                maxdd_std_brl=float(dds_comb.std(ddof=1)) if len(dds_comb) > 1 else 0.0,
                maxdd_pior_semente_brl=float(dds_comb.max()),
                zerou_no_seguro=zerou_comb,
                ordens_recusadas_por_teto=r["ordens_recusadas_is"] + r["ordens_recusadas_oos"],
            ),
        )
        linhas.append(linha)

        aviso = "  [EXCEDE TETO OFICIAL COPA BTG=5]" if excede_teto_copa else ""
        print(f"N={n:>2} | piso ingenuo=R${num_br(piso_ingenuo, 0):>9} || "
              f"OOS: trades={len(trades_oos):>5} capital_real=R${num_br(real_oos, 0):>9} "
              f"(seguro_medido=R${num_br(seguro_oos, 0)}) zerou={zerou_oos}/{C.N_SEMENTES} || "
              f"COMBINADO: trades={len(trades_comb):>5} capital_real=R${num_br(real_comb, 0):>9} "
              f"(seguro_medido=R${num_br(seguro_comb, 0)}) zerou={zerou_comb}/{C.N_SEMENTES}"
              f"{aviso}", flush=True)

    RESULT_JSON.write_text(json.dumps({
        "symbol": C.SYMBOL, "resolucao": "tick (49/51 pregoes OOS) + M1 fallback (2/51 pregoes OOS)",
        "oos_unlock_reason": OOS_UNLOCK_REASON,
        "candidato_params": {"level_spacing_ticks": 1, "profit_ticks": 1, "stop_ticks": 16},
        "margem_contrato_brl": C.MARGEM_CONTRATO_BRL,
        "margin_buffer_futuros": C.MARGIN_BUFFER_FUTUROS, "teto_motor_fixo": C.TETO_MOTOR_FIXO,
        "teto_oficial_copa_btg_historico": C.TETO_OFICIAL_COPA_BTG,
        "n_sementes": C.N_SEMENTES, "p_rejeicao": C.P_REJEICAO, "seed_base": C.SEED_BASE,
        "correcao_margem_formula": "capital_minimo_real(N) = capital_minimo_seguro_medido(N) + piso_ingenuo(N)",
        "combinado_metodo": "concatenacao de trade lists (IS-tick standalone ++ OOS-mixed standalone), "
                             "validada byte-a-byte contra rodada unica na fronteira 2026-06-11..16 -- "
                             "ver docstring do modulo",
        "janela_is_tick": f"{len(dias_is)} pregoes, {dias_is[0]} -> {dias_is[-1]}",
        "janela_oos": f"{len(oos['dias_oos'])} pregoes, {oos['dias_oos'][0]} -> {oos['dias_oos'][-1]} "
                      f"({len(oos['dias_tick'])} tick real + {len(oos['dias_m1_fallback'])} fallback M1: "
                      f"{[str(d) for d in oos['dias_m1_fallback']]})",
        "janela_combinada": f"{len(dias_combinado)} pregoes, {dias_combinado[0]} -> {dias_combinado[-1]}",
        "resultados": linhas,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[capital_ladder_wdof1_oos] resultado agregado salvo em {RESULT_JSON}")

    print("\n\n=== ESCADA DE CAPITAL (CORRIGIDA p/ margem) -- WdoGridReloadMaker F1 (WDO@), CONFIRMACAO OOS ===")
    print(f"{'N':>3} | {'capital_minimo_real OOS-only':>30} | {'capital_minimo_real IS+OOS combinado':>38}")
    print("-" * 80)
    for l in linhas:
        aviso = " *" if l["excede_teto_copa_btg"] else ""
        print(f"{l['n']:>3} | R${num_br(l['oos']['capital_minimo_real_brl'], 0):>27} | "
              f"R${num_br(l['combinado']['capital_minimo_real_brl'], 0):>35}{aviso}")
    print("* excede o teto OFICIAL da Copa BTG para WDO@ (5 contratos, profiles.py:235) -- "
          "regra especifica da competicao ja encerrada, NAO um limite fisico.")


if __name__ == "__main__":
    main()
