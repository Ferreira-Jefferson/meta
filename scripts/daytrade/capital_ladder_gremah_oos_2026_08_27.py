"""CONFIRMACAO OOS -- escada de capital (lote fixo N=1..10) da familia GREMAH
(2026-08-27), simbolo PMAM3, motor M1. Segue direto de
`capital_ladder_gremah_2026_08_27.py` (rodado hoje SO' no IS -- corte
congelado `profiles.OOS_CUTOFF="2026-06-13"`, `LockedBars.unlock()` nunca
chamado la').

O QUE JA' ERA CONHECIDO (nao repetido aqui como novidade): a geometria
DEFAULT da Gremah (a que roda em producao) ja' teve o OOS olhado antes e
bateu -- e' o que justificou adota-la em producao. Isso e' normal.

O QUE E' NOVO NESTE SCRIPT (nunca medido contra o OOS ate agora):
  1. a ESCADA DE CAPITAL por N fixo (`GremahLoteFixo`, subclasse que trava
     `_lotes_por_realocacao` numa constante -- so' testada no IS ate' hoje).
  2. os 2 filtros de qualidade de sinal validados HOJE, so' no IS
     (`minutos_desde_abertura>=216min`, `volume_toque<=3200`,
     `scratch/scripts/gremah_signal_quality_filtros_2026_08_27.csv`).

AUTORIZACAO EXPLICITA DO DONO (2026-08-27): destravar o OOS agora, para esta
validacao final, ANTES de atualizar producao com capital/sinal consolidados.
Isto NAO e' um "peek" contaminante -- e' a passada UNICA de confirmacao que o
protocolo do repo pede (mesmo desenho de `confirm_oos_ticks.py`): parametro
(aqui, N e os 2 filtros) escolhido no IS, OOS julga uma vez, sem segunda
tentativa se reprovar.

REUSO (import direto, NADA reescrito) do que ja' foi construido e rodado
hoje no IS:
  - `capital_ladder_gremah_2026_08_27`: `GremahLoteFixo` (subclasse de lote
    fixo), `roda_base` (roda o motor 1x por N, capital nominal folgado),
    `rejeicao_stats`/`busca_capital_minimo_seguro` (bisseccao de capital
    minimo seguro sob rejeicao i.i.d. p=50%/30 sementes -- MESMA funcao,
    MESMOS parametros: `N_SEMENTES`, `P_ALVO`, `SEED_BASE`),
    `capital_que_producao_libera` (achado operacional: em que caixa a
    formula REAL de producao ja liberaria N).
  - `_geometria_comum`: `REGIME_START` (corte de regime de preco por
    simbolo) e `carregar_economics` (cache de tick_value/tick_size).
  - `gremah_signal_quality_2026_08_27`: `computa_features` (MESMO calculo
    de `minutos_desde_abertura`/`volume_toque`/etc, aplicado aos trades do
    OOS em vez do IS).
  - `copa_rejection_lab`: `testa_proxy`/`imprime_correlacao` (correlacao +
    teste de permutacao, so' para reportar se a DIRECAO do efeito se
    mantem no OOS -- informativo, nao re-gateia nada).

NAO reusado (fora de escopo, pedido explicito da missao): a regra de saida
por reversao (giveback do MFE) -- ja morreu 0/4 no IS
(`capital_ladder_qualidade_sinal_reversao_2026_08_27`), nao vale gastar OOS
nela.

`_geometria_comum.carregar_is` (arquivo EXISTENTE, NAO editado por regra do
repo) so' devolve IS e nunca chama `unlock()`. `carregar_oos_e_combinado`
abaixo e' a funcao IRMA que falta -- construida aqui, num arquivo NOVO, em
vez de editar aquele.

CORRECAO DE MARGEM/NOTIONAL (mesma formula ja aplicada e documentada hoje em
`capital_ladder_qualidade_sinal_reversao_2026_08_27`, conferida bater com o
JSON do IS: N=1 -> 5,10+103,00=108,10~=R$108; N=5 -> 25,51+515,00=540,51~=
R$541; N=10 -> 51,02+1.030,00=1.081,02~=R$1.081 -- os 3 numeros da memoria
oficial): a bisseccao original de `capital_minimo_seguro` so' checa
`capital_candidato + pnl_acumulado <= 0` -- nunca checa se o capital cobre o
NOTIONAL cheio da entrada (PMAM3 e' acao, sem margem: N x 100 x preco).
Como a curva de equity e' um deslocamento aditivo puro (exigir
equity(t)>=M para todo t equivale a exigir equity(t)-M>=0, ou seja
capital_inicial+M),

    capital_minimo_real(N) = capital_minimo_seguro_medido(N)
                              + pior_caso_exigencia_capital(N)

e' EXATA (nao aproximada) -- reaplicada aqui para os DOIS casos (OOS puro e
IS+OOS combinado), cada um com o `pior_caso` medido NA PROPRIA janela (o
preco mais caro observado especificamente naquela janela, nao herdado do
IS -- a PMAM3 mudou MUITO de patamar dentro do IS, ver
`pmam3_colapso_de_preco_2026_08_26`, entao herdar seria errado).

Dois numeros de capital minimo real por N, sempre:
  (a) OOS-only -- motor rodado SO' nas barras >= corte (comeco "frio", sem
      nenhum aquecimento de janela de volume/tipico vindo do IS -- mesmo
      desenho de `confirm_oos_ticks.py`). Confirmacao ISOLADA.
  (b) IS+OOS combinado, cronologico -- motor rodado do INICIO do regime de
      preco (2025-12-16) ate' o fim do dado disponivel, sem nenhum corte no
      meio. Numero FINAL consolidado (valido porque o OOS ja' foi
      destravado por decisao do dono agora -- nao e' mais peek).

Uso:
    python -u scripts/daytrade/capital_ladder_gremah_oos_2026_08_27.py \
        --unlock-oos "MOTIVO"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES  # noqa: E402
from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

from _geometria_comum import REGIME_START, carregar_economics  # noqa: E402
from capital_ladder_gremah_2026_08_27 import (  # noqa: E402
    MAX_OPEN_CONTRACTS_TESTE,
    N_MAX,
    N_MIN,
    N_SEMENTES,
    P_ALVO,
    GremahLoteFixo,
    busca_capital_minimo_seguro,
    capital_que_producao_libera,
    rejeicao_stats,
    roda_base,
)
from copa_rejection_lab import imprime_correlacao, testa_proxy  # noqa: E402
from gremah_signal_quality_2026_08_27 import computa_features  # noqa: E402

SYMBOL = "PMAM3"
MOTOR = "m1"

SCRATCH_DIR = ROOT / "scratch" / "scripts"
JSON_RESULTADO = SCRATCH_DIR / "capital_ladder_gremah_pmam3_oos_2026_08_27.json"
CSV_TRADES_N1_OOS = SCRATCH_DIR / "capital_ladder_gremah_pmam3_oos_puro_n1_trades_2026_08_27.csv"
CSV_TRADES_N1_COMBINADO = SCRATCH_DIR / "capital_ladder_gremah_pmam3_isoos_combinado_n1_trades_2026_08_27.csv"
CSV_FILTROS_OOS = SCRATCH_DIR / "gremah_signal_quality_filtros_oos_2026_08_27.csv"

#: Motivo padrao do unlock -- o dono autorizou explicitamente esta redacao
#: (ver docstring do modulo). `--unlock-oos` pode sobrescrever na linha de
#: comando, mas o default ja documenta a autorizacao sem depender de
#: ninguem digitar o motivo certo na hora.
MOTIVO_UNLOCK_PADRAO = (
    "Validacao final autorizada pelo dono em 2026-08-27 para consolidar "
    "capital/sinal antes de atualizar producao"
)

#: Os 2 filtros de qualidade de sinal ja' CALIBRADOS hoje no IS
#: (`gremah_signal_quality_2026_08_27.py`, gate split-half: mesmo sinal E
#: p<0,05 no pool E p<0,10 em cada metade cronologica -- so' estes 2 das 7
#: features testadas passaram). FIXOS aqui -- o OOS testa se o efeito se
#: MANTEM em dado novo, nunca recalibra o limiar nele (senao vira uma
#: segunda rodada de escolha disfarcada de confirmacao).
FILTROS_IS = (
    dict(feature="minutos_desde_abertura", direcao=">=", limiar=216.0, corr_is=0.0806),
    dict(feature="volume_toque", direcao="<=", limiar=3200.0, corr_is=-0.1339),
)


# ---------------------------------------------------------------------------
# funcao IRMA de `_geometria_comum.carregar_is` -- destrava o OOS e devolve
# tambem o IS+OOS combinado cronologico. Vive aqui (arquivo NOVO) porque
# `_geometria_comum.py` e' arquivo EXISTENTE e a regra do repo nesta rodada
# e' nao editar nenhum rastreado.
# ---------------------------------------------------------------------------

def carregar_oos_e_combinado(symbol: str, motor: str, motivo_unlock: str):
    """Espelha `_geometria_comum.carregar_is` ate' o corte de regime, depois
    diverge: chama `LockedBars.unlock(motivo_unlock)` e devolve
    `(oos_bars, combinado_bars, profile)` -- `combinado_bars` e' IS+OOS
    concatenados na ordem cronologica original (IS inteiro seguido do OOS
    inteiro, sem sobreposicao nem buraco: e' literalmente o dado inteiro do
    regime de preco atual, do inicio ao fim disponivel)."""
    profile = PROFILES[symbol]
    if motor != "m1":
        raise ValueError(f"motor {motor!r} nao suportado aqui -- so' 'm1' (escopo da missao)")
    bars = load_m1(symbol)
    if bars.empty:
        return pd.DataFrame(), pd.DataFrame(), profile

    regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
    bars = bars.loc[bars.index >= regime_start]

    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(bars, split)
    is_bars = locked.in_sample()
    locked.unlock(motivo_unlock)
    oos_bars = locked.out_of_sample()
    combinado_bars = pd.concat([is_bars, oos_bars]).sort_index()
    return oos_bars, combinado_bars, profile


# ---------------------------------------------------------------------------
# escada de capital -- MESMO loop de `capital_ladder_gremah_2026_08_27.main`,
# parametrizado na janela (aqui reusado para OOS puro e para IS+OOS
# combinado), com a correcao de margem/notional somada por N.
# ---------------------------------------------------------------------------

def roda_escada(run_bars: pd.DataFrame, profile, economics, rotulo_janela: str):
    if run_bars.empty:
        raise SystemExit(f"[{rotulo_janela}] janela vazia -- nada a rodar")
    pregoes = len(set(run_bars.index.date))
    print(f"\n[{rotulo_janela}] {len(run_bars)} barras, {pregoes} pregoes, "
          f"{run_bars.index.min()} -> {run_bars.index.max()}", flush=True)

    linhas: list[dict] = []
    trade_log_n1 = None
    for n in range(N_MIN, N_MAX + 1):
        strat, resultado = roda_base(n, run_bars, profile, economics)
        trades = list(resultado.trades)
        if getattr(resultado, "wiped_out_at", None) is not None:
            raise SystemExit(
                f"[{rotulo_janela}] N={n}: rodada-base ZEROU em {resultado.wiped_out_at} mesmo "
                "com capital nominal folgado -- capital de sondagem insuficiente para esta janela."
            )
        puladas = len(getattr(resultado, "sessoes_puladas_por_capital", []) or [])
        if puladas:
            raise SystemExit(
                f"[{rotulo_janela}] N={n}: {puladas} sessao(oes) pulada(s) por "
                "enforce_capital_minimo mesmo com capital nominal folgado."
            )
        if n == N_MIN:
            trade_log_n1 = trades

        pior_caso = max((t.quantity * t.entry_price for t in trades), default=0.0)
        chute = max(pior_caso, 1.0)
        capital_seguro = busca_capital_minimo_seguro(trades, chute)
        stats_no_seguro = rejeicao_stats(trades, capital_seguro)
        assert int(stats_no_seguro["zerou"].sum()) == 0, (
            f"[{rotulo_janela}] N={n}: bisseccao devolveu {capital_seguro} mas a confirmacao "
            "final com 30 sementes NAO bateu 0/30 -- bug na busca."
        )
        capital_real = capital_seguro + pior_caso

        libera_n = capital_que_producao_libera(strat.snapshots, n)
        if libera_n is None:
            libera_txt = "n/d"
        else:
            libera_txt = "sim" if libera_n < capital_real else "nao"

        maxdd_medio = float(stats_no_seguro["maxdd"].mean())
        maxdd_desvio = float(stats_no_seguro["maxdd"].std(ddof=1)) if N_SEMENTES > 1 else 0.0

        linha = dict(
            n_lotes=n,
            trades=len(trades),
            pior_caso_exigencia_capital_brl=pior_caso,
            capital_minimo_seguro_medido_brl=capital_seguro,
            capital_minimo_real_brl=capital_real,
            capital_que_producao_libera_n_brl=libera_n,
            producao_libera_antes_do_real=libera_txt,
            maxdd_medio_no_capital_seguro_brl=maxdd_medio,
            maxdd_desvio_no_capital_seguro_brl=maxdd_desvio,
        )
        linhas.append(linha)
        print(f"    [{rotulo_janela}] N={n:>2} trades={len(trades):>5} | "
              f"pior_caso=R${num_br(pior_caso)} | seguro_medido=R${num_br(capital_seguro)} | "
              f"CAPITAL_MINIMO_REAL=R${num_br(capital_real)} | "
              f"producao_libera_N={'n/d' if libera_n is None else 'R$'+num_br(libera_n)} "
              f"(antes_do_real={libera_txt})", flush=True)

    return linhas, trade_log_n1


def _trade_log_para_df(trades) -> pd.DataFrame:
    return pd.DataFrame([dict(
        entry_ts=t.entry_ts, exit_ts=t.exit_ts, entry_price=t.entry_price,
        exit_price=t.exit_price, side=t.side, quantity=t.quantity,
        pnl_brl=t.pnl_brl,
        exit_reason=(t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)),
    ) for t in trades])


# ---------------------------------------------------------------------------
# reteste dos 2 filtros calibrados no IS -- aplicados CRUS (sem recalibrar)
# aos trades do OOS puro (N=1 lote fixo, mesmo desenho do trade log usado
# pela calibracao no IS).
# ---------------------------------------------------------------------------

def aplica_filtro_fixo(nome: str, direcao: str, limiar: float, corr_is: float,
                        x: np.ndarray, y: np.ndarray) -> dict:
    """`x`/`y' na ORDEM CRONOLOGICA dos trades do OOS puro (N=1). O filtro
    (direcao + limiar) vem PRONTO do IS -- nada aqui e' recalibrado: so' se
    mede o efeito de aplicar o MESMO corte a dado que o robo nunca viu
    durante a calibracao."""
    mantem = (x >= limiar) if direcao == ">=" else (x <= limiar)
    n = len(x)
    n_mantidos = int(mantem.sum())
    n_descartados = n - n_mantidos

    if n >= 2 and np.std(x) > 0:
        corr_oos = float(np.corrcoef(x, y)[0, 1])
        mesma_direcao = (corr_oos > 0) == (corr_is > 0)
    else:
        corr_oos = float("nan")
        mesma_direcao = False

    pnl_sem = float(y.sum())
    pnl_com = float(y[mantem].sum()) if n_mantidos else 0.0
    pnl_medio_sem = pnl_sem / n if n else 0.0
    pnl_medio_com = pnl_com / n_mantidos if n_mantidos else 0.0

    curva_sem = np.concatenate([[0.0], np.cumsum(y)])
    curva_com = np.concatenate([[0.0], np.cumsum(y[mantem])]) if n_mantidos else np.array([0.0])
    maxdd_sem = maxdd_brl(pd.Series(curva_sem))
    maxdd_com = maxdd_brl(pd.Series(curva_com))

    return dict(
        feature=nome, direcao=direcao, limiar=limiar,
        corr_is=corr_is, corr_oos=corr_oos, mesma_direcao_is_oos=mesma_direcao,
        n_oos=n, n_mantidos_oos=n_mantidos, n_descartados_oos=n_descartados,
        pnl_sem_filtro_brl=pnl_sem, pnl_com_filtro_brl=pnl_com,
        pnl_medio_sem_filtro_brl=pnl_medio_sem, pnl_medio_com_filtro_brl=pnl_medio_com,
        maxdd_sem_filtro_brl=maxdd_sem, maxdd_com_filtro_brl=maxdd_com,
    )


def imprime_filtro_oos(f: dict) -> None:
    veredito = "MANTEVE a direcao" if f["mesma_direcao_is_oos"] else "INVERTEU a direcao"
    print(f"\n  filtro (calibrado no IS, CRU no OOS): {f['feature']} {f['direcao']} "
          f"{num_br(f['limiar'], 4)}")
    print(f"  correlacao IS={num_br(f['corr_is'], 4)} | correlacao OOS={num_br(f['corr_oos'], 4)} "
          f"-> {veredito}")
    print(f"  OOS puro: {f['n_oos']} trades -- mantem {f['n_mantidos_oos']}, "
          f"descarta {f['n_descartados_oos']}")
    print(f"  P&L TOTAL OOS SEM filtro = R${num_br(f['pnl_sem_filtro_brl'])} | "
          f"COM filtro = R${num_br(f['pnl_com_filtro_brl'])}")
    print(f"  P&L MEDIO/trade OOS SEM filtro = R${num_br(f['pnl_medio_sem_filtro_brl'], 4)} | "
          f"COM filtro = R${num_br(f['pnl_medio_com_filtro_brl'], 4)}")
    print(f"  MaxDD OOS SEM filtro = R${num_br(f['maxdd_sem_filtro_brl'])} | "
          f"COM filtro = R${num_br(f['maxdd_com_filtro_brl'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unlock-oos", default=MOTIVO_UNLOCK_PADRAO,
                         help="motivo do destravamento -- fica no registro do split")
    args = parser.parse_args()

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    oos_bars, combinado_bars, profile = carregar_oos_e_combinado(SYMBOL, MOTOR, args.unlock_oos)
    if oos_bars.empty:
        raise SystemExit(f"[capital_ladder_oos] sem dado OOS local para {SYMBOL!r} (motor={MOTOR!r})")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    print(f"[capital_ladder_oos] {SYMBOL} motor={MOTOR} -- economics (cache): "
          f"trade_tick_value={economics.trade_tick_value} trade_tick_size={economics.trade_tick_size}")

    # ------------------------------------------------------------------
    # 1) escada de capital -- OOS puro
    # ------------------------------------------------------------------
    linhas_oos, trades_n1_oos = roda_escada(oos_bars, profile, economics, "OOS-puro")
    df_n1_oos = _trade_log_para_df(trades_n1_oos)
    df_n1_oos.to_csv(CSV_TRADES_N1_OOS, index=False)
    print(f"\n[capital_ladder_oos] trade log N=1 (OOS puro, {len(df_n1_oos)} trades) "
          f"salvo em {CSV_TRADES_N1_OOS}")

    # ------------------------------------------------------------------
    # 2) escada de capital -- IS+OOS combinado cronologico
    # ------------------------------------------------------------------
    linhas_combinado, trades_n1_combinado = roda_escada(
        combinado_bars, profile, economics, "IS+OOS-combinado")
    df_n1_combinado = _trade_log_para_df(trades_n1_combinado)
    df_n1_combinado.to_csv(CSV_TRADES_N1_COMBINADO, index=False)
    print(f"\n[capital_ladder_oos] trade log N=1 (IS+OOS combinado, {len(df_n1_combinado)} trades) "
          f"salvo em {CSV_TRADES_N1_COMBINADO}")

    # ------------------------------------------------------------------
    # 3) reteste dos 2 filtros de qualidade de sinal -- CRU, no OOS puro
    #    (N=1, mesmas features de `gremah_signal_quality_2026_08_27.py`)
    # ------------------------------------------------------------------
    tick_size = economics.trade_tick_size
    feats_oos, sem_match = computa_features(df_n1_oos, oos_bars, tick_size)
    print(f"\n[capital_ladder_oos] features (OOS puro) calculadas para {len(feats_oos)}/{len(df_n1_oos)} "
          f"trades ({sem_match} sem barra correspondente -- deveria ser 0)")

    pnl_oos = np.array([f.pnl_brl for f in feats_oos])
    minutos_oos = np.array([f.minutos_desde_abertura for f in feats_oos])
    voltoque_oos = np.array([f.volume_toque for f in feats_oos])

    candidatos_oos = {
        "minutos_desde_abertura": minutos_oos,
        "volume_toque": voltoque_oos,
    }

    print(f"\n=== {SYMBOL} -- correlacao proxy <-> P&L no OOS puro (informativo, "
          "sem re-gatear nada -- so' checa se a direcao do IS se mantem) ===")
    for cfg in FILTROS_IS:
        r = testa_proxy(cfg["feature"], candidatos_oos[cfg["feature"]], pnl_oos, seed=0)
        imprime_correlacao(r)

    print(f"\n=== {SYMBOL} -- filtros calibrados no IS, aplicados CRUS no OOS puro ===")
    linhas_filtro_oos = []
    for cfg in FILTROS_IS:
        x = candidatos_oos[cfg["feature"]]
        f = aplica_filtro_fixo(cfg["feature"], cfg["direcao"], cfg["limiar"], cfg["corr_is"], x, pnl_oos)
        imprime_filtro_oos(f)
        linhas_filtro_oos.append(f)
    pd.DataFrame(linhas_filtro_oos).to_csv(CSV_FILTROS_OOS, index=False)
    print(f"\n[capital_ladder_oos] resultado dos filtros (OOS puro) salvo em {CSV_FILTROS_OOS}")

    # ------------------------------------------------------------------
    # JSON consolidado
    # ------------------------------------------------------------------
    with open(JSON_RESULTADO, "w", encoding="utf-8") as fh:
        json.dump(dict(
            symbol=SYMBOL, motor=MOTOR,
            unlock_oos_motivo=args.unlock_oos,
            oos_pregoes=len(set(oos_bars.index.date)),
            oos_inicio=str(oos_bars.index.min()), oos_fim=str(oos_bars.index.max()),
            combinado_pregoes=len(set(combinado_bars.index.date)),
            combinado_inicio=str(combinado_bars.index.min()), combinado_fim=str(combinado_bars.index.max()),
            n_sementes=N_SEMENTES, p_alvo=P_ALVO,
            linhas_oos_puro=linhas_oos,
            linhas_is_oos_combinado=linhas_combinado,
            filtros_oos_puro=linhas_filtro_oos,
        ), fh, indent=2, ensure_ascii=False, default=str)
    print(f"[capital_ladder_oos] resultado completo salvo em {JSON_RESULTADO}")

    # ------------------------------------------------------------------
    # tabela final -- CRUA, sem veredito embutido
    # ------------------------------------------------------------------
    print(f"\n\n=== ESCADA DE CAPITAL REAL (medido + pior-caso) -- {SYMBOL} motor={MOTOR} ===")
    print(f"{'N':>3}{'trades_OOS':>12}{'cap_real_OOS_R$':>18}{'trades_IS+OOS':>15}{'cap_real_IS+OOS_R$':>20}")
    print("-" * 68)
    for lo, lc in zip(linhas_oos, linhas_combinado):
        assert lo["n_lotes"] == lc["n_lotes"]
        print(f"{lo['n_lotes']:>3}{lo['trades']:>12}{num_br(lo['capital_minimo_real_brl']):>18}"
              f"{lc['trades']:>15}{num_br(lc['capital_minimo_real_brl']):>20}")


if __name__ == "__main__":
    main()
