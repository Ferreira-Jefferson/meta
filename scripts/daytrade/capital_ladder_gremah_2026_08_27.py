"""ESCADA DE CAPITAL da familia GREMAH (2026-08-27) -- PMAM3, motor M1
(`strategy.daytrade.lab.gremah.Gremah`, o campeao/flagship documentado).

Pergunta do dono: Gremah e' DINAMICA por design em producao -- toda entrada
chama `self.quantity = self._lotes_por_realocacao(anchor, ts) * LOTE_PADRAO_B3`
(gremah.py:1287, sobrescreve qualquer `quantity=` passado no construtor).
Este script mede, para N=1..10 LOTES FIXOS (nao a formula dinamica real), o
menor capital inicial que sobrevive a rejeicao de fila i.i.d. p=50% (30
sementes) sem arruinar em nenhum ponto do IS -- e compara esse piso medido
contra o caixa em que a FORMULA DINAMICA REAL (intocada) ja teria liberado
aquele mesmo N, para flagar crescimento operacional prematuro.

COMO RODAR N LOTES FIXOS SEM EDITAR gremah.py: `_lotes_por_realocacao` e'
sobrescrita numa SUBCLASSE local (`GremahLoteFixo`, abaixo) que devolve uma
constante -- entradas/saidas/geometria da Gremah original ficam 100%
intocadas, so' o TAMANHO da entrada muda. `strategy/daytrade/lab/gremah.py`
e todo o resto de `src/` permanecem SEM NENHUMA EDICAO (regra do repo --
outras sessoes podem estar mexendo nesses arquivos ao mesmo tempo).

CAPITAL EXIGIDO NAO E' UM NUMERO FIXO: e' acao (renda variavel, sem margem),
e o preco da PMAM3 variou muito dentro do IS (colapsou de ~R$4,53 para
~R$0,13 -- ver memoria `pmam3_colapso_de_preco`). O custo de UMA entrada de N
lotes = N x 100 x preco_da_acao NO MOMENTO da entrada -- por isso, para cada
N, calculamos o PIOR CASO observado (a entrada mais cara de toda a janela)
como piso ingenuo, e SEPARADAMENTE buscamos por bisseccao o capital inicial
minimo que sobrevive a rejeicao de fila sem arruinar (definicao mais forte
que o piso ingenuo, porque tambem cobre a sequencia de perdas acumuladas).

METODOLOGIA DE ESTRESSE (obrigatoria, TEMPLATE = `scripts/daytrade/
capital_dinamico_rerun_2026_08_27.py`, lido inteiro antes de escrever este
script): rejeicao i.i.d. POR TRADE, p=50%, sorteio independente do
resultado, SEM re-rodar o motor por semente -- subamostra o `pnl_brl` de
UMA UNICA rodada-base (aqui, com N lotes fixos e capital nominal bem folgado
so' para a estrategia nao ser CENSURADA por `enforce_capital_minimo`/
wipeout durante a extracao da sequencia real de trades) e reconstroi a
curva de patrimonio cronologicamente a partir de CADA capital candidato.
Isso e' valido aqui porque, com `_lotes_por_realocacao` travado numa
constante, NADA na sequencia real de entradas/saidas depende do capital
candidato -- so' a curva de patrimonio reconstruida por cima muda. "Ruina"
= a curva (capital_inicial + pnl acumulado, evento a evento) toca <=0 em
QUALQUER ponto da janela IS, em qualquer sessao (mesmo criterio do freio
incondicional do motor, `engine.py`: `if equity_atual <= 0: wiped_out_at =
ts; break`).

ACHADO OPERACIONAL (item 4 da tarefa): `GremahLoteFixo._lotes_por_
realocacao` tambem GRAVA, a cada chamada, os ingredientes REAIS e
INTOCADOS da formula de producao (anchor, `passo`, teto de volume do dia,
teto de capacidade) -- sem consultar `self._cash_atual_brl` (que aqui
refletiria o capital NOMINAL da rodada-base, nao um capital real
qualquer). `capital_que_producao_libera` (abaixo) resolve OFFLINE, a partir
desses snapshots reais, em que nivel de CAIXA a formula (extraida de
gremah.py:1223-1238, SEM modificacao nenhuma na logica) cruzaria de N-1
para N lotes -- e reporta o MINIMO entre os instantes qualificados (o
gatilho mais barato observado no IS real, o cenario mais exposto a
crescimento prematuro).

Nenhum atalho computacional foi necessario: a bisseccao so' reamostra
`pnl_brl` de trades ja simulados (numpy puro, sem re-rodar o motor), entao
todo o script -- inclusive a busca binaria -- usa as 30 sementes cheias o
tempo todo (nao ha rodada "rapida" seguida de confirmacao "lenta").

Janela: IN-SAMPLE apenas (`_geometria_comum.carregar_is`, corte congelado em
`profiles.OOS_CUTOFF="2026-06-13"`, `LockedBars.unlock()` NUNCA chamado).

Uso:
    python -u scripts/daytrade/capital_ladder_gremah_2026_08_27.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for  # noqa: E402
from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402
from strategy.daytrade.base import LOTE_PADRAO_B3  # noqa: E402
from strategy.daytrade.lab.gremah import Gremah  # noqa: E402

from _geometria_comum import carregar_economics, carregar_is  # noqa: E402

# ---------------------------------------------------------------------------
# parametros da rodada
# ---------------------------------------------------------------------------
SYMBOL = "PMAM3"
MOTOR = "m1"
N_MIN, N_MAX = 1, 10
N_SEMENTES = 30
P_ALVO = 0.5
SEED_BASE = 0
#: Capital NOMINAL da rodada-base (p=100%) -- so' para a estrategia nao ser
#: CENSURADA por `enforce_capital_minimo` (recusa o pregao inteiro se o caixa
#: nao cobrir 2 lotes no preco de abertura) nem por wipeout (`equity<=0`)
#: durante a extracao da sequencia REAL de trades. Bem acima de qualquer
#: exigencia real de N<=10 lotes no maior preco observado da PMAM3 no IS
#: (~R$4,60 x 100 x 10 = ~R$4.600) -- existe so' para destravar a
#: simulacao, nunca e' usado como "capital seguro" de verdade (esse e'
#: medido por bisseccao, abaixo, a partir da MESMA sequencia de trades).
CAPITAL_NOMINAL_PROBE_BRL = 5_000_000.0
#: Teto de contratos do MOTOR (`IntradayBacktestConfig.max_open_contracts`)
#: -- TRAP conhecida (machine.py:763-778): se ficar menor que a quantidade
#: pedida pela estrategia, o excesso e' descartado em SILENCIO. Elevado bem
#: acima de qualquer N x LOTE_PADRAO_B3 testado aqui (N<=10 -> <=1.000
#: acoes) -- perfil de acao nao declara teto oficial nenhum (`SymbolProfile.
#: max_open_contracts=None`, sem teto por design; isto so' formaliza a
#: regra do dono de "sempre elevar", nao muda comportamento nenhum.
MAX_OPEN_CONTRACTS_TESTE = 100_000

SCRATCH_DIR = ROOT / "scratch" / "scripts"
CSV_TRADE_LOG_N1 = SCRATCH_DIR / "capital_ladder_gremah_pmam3_n1_trades_2026_08_27.csv"
JSON_RESULTADO = SCRATCH_DIR / "capital_ladder_gremah_pmam3_2026_08_27.json"


# ---------------------------------------------------------------------------
# subclasse de LOTE FIXO -- unica forma de rodar N lotes constantes sem
# editar gremah.py (regra do repo). Entradas/saidas/geometria da Gremah
# original ficam 100% intocadas; so' `_lotes_por_realocacao` muda.
# ---------------------------------------------------------------------------

class GremahLoteFixo(Gremah):
    """`Gremah` com `_lotes_por_realocacao` travada numa constante `n_lotes`
    -- `_build_entry` (gremah.py:1287) chama `self.quantity =
    self._lotes_por_realocacao(anchor, ts) * LOTE_PADRAO_B3` em TODA
    entrada, entao esta e' a UNICA forma de fixar o tamanho sem editar o
    arquivo original.

    Tambem INSTRUMENTA cada chamada (`self.snapshots`), gravando os
    ingredientes REAIS e INTOCADOS da formula de producao -- reproduzida
    aqui SEM alteracao alguma (duplicado de gremah.py:1223-1238, comparado
    linha a linha antes de rodar) a partir de `passo`/`max_lotes_dia`/
    `capacidade_brl` daquele instante. Deliberadamente NAO chama a formula
    original (nao usa `super()._lotes_por_realocacao`) nem le
    `self._cash_atual_brl`: essa leitura refletiria o capital NOMINAL desta
    rodada-base, que nao e' capital real nenhum -- so' os ingredientes que
    NAO dependem de caixa (anchor/volume/capacidade) importam aqui; a parte
    caixa-dependente e' resolvida OFFLINE por `capital_que_producao_libera`,
    tratando o caixa como incognita."""

    name = "gremah_lote_fixo"

    def __init__(self, n_lotes: int, **kwargs):
        super().__init__(**kwargs)
        self._n_lotes_fixo = int(n_lotes)
        self.snapshots: list[dict] = []

    def _lotes_por_realocacao(self, anchor: float, ts: pd.Timestamp) -> int:
        custo_do_lote = anchor * LOTE_PADRAO_B3
        passo = self.realocacao_limiar_caixa * custo_do_lote

        eventos = self._janela_volume.volumes_por_evento(ts)
        if len(eventos) >= self.capacidade_min_eventos:
            max_lotes_dia = max(1, int(median(eventos) * self.capacidade_negocio_mult) // LOTE_PADRAO_B3)
        else:
            media_volume_min = self._janela_volume.media_por_minuto(ts)
            teto_acoes = media_volume_min * self.realocacao_teto_pct_volume_minuto
            max_lotes_dia = max(1, int(teto_acoes) // LOTE_PADRAO_B3)

        tipico_estavel = self._janela_negocio_tipico.tipico_mediano()
        capacidade_brl = None
        if tipico_estavel is not None:
            teto_estavel_lotes = max(1, int(tipico_estavel * self.capacidade_negocio_mult) // LOTE_PADRAO_B3)
            capacidade_brl = self.capacidade_fracao * (teto_estavel_lotes - 1) * passo

        self.snapshots.append(dict(ts=ts, anchor=float(anchor), passo=float(passo),
                                    max_lotes_dia=int(max_lotes_dia),
                                    capacidade_brl=(None if capacidade_brl is None else float(capacidade_brl))))
        return self._n_lotes_fixo


# ---------------------------------------------------------------------------
# rodada-base (p=100%) por N -- UMA vez por N, capital nominal folgado, so'
# para extrair a sequencia REAL de trades (entry/exit/preco/lado/motivo).
# ---------------------------------------------------------------------------

def roda_base(n: int, run_bars: pd.DataFrame, profile, economics):
    strat = GremahLoteFixo(n_lotes=n, symbol=SYMBOL)
    cfg = config_for(
        profile,
        trade_tick_value=economics.trade_tick_value,
        trade_tick_size=economics.trade_tick_size,
        target_fills_as_maker=strat.target_fills_as_maker,
        initial_capital=CAPITAL_NOMINAL_PROBE_BRL,
        max_open_contracts=MAX_OPEN_CONTRACTS_TESTE,
    )
    resultado = run_intraday_backtest(run_bars, strat, cfg)
    return strat, resultado


# ---------------------------------------------------------------------------
# rejeicao i.i.d. p=50% -- MESMA tecnica de `capital_dinamico_rerun_2026_08_
# 27.py::rejeicao_p_alvo` (subamostra pnl de uma rodada-base, reconstroi a
# curva cronologicamente a partir do capital candidato). Aqui parametrizada
# em `capital_candidato` para servir de funcao-objetivo da bisseccao.
# ---------------------------------------------------------------------------

def rejeicao_stats(trades, capital_candidato: float, p: float = P_ALVO,
                    n_sementes: int = N_SEMENTES, seed_base: int = SEED_BASE) -> dict:
    n = len(trades)
    pnls_totais = [t.pnl_brl for t in trades]
    maxdd = np.empty(n_sementes)
    capital_final = np.empty(n_sementes)
    zerou = np.zeros(n_sementes, dtype=bool)
    for s in range(n_sementes):
        rng = np.random.default_rng(seed_base + s)
        aceita = rng.random(n) < p if n else np.array([], dtype=bool)
        pnls = [pnl for pnl, a in zip(pnls_totais, aceita) if a]
        curva = [capital_candidato]
        acc = capital_candidato
        for pnl in pnls:
            acc += pnl
            curva.append(acc)
        maxdd[s] = maxdd_brl(pd.Series(curva))
        capital_final[s] = curva[-1]
        zerou[s] = any(v <= 0 for v in curva)
    return dict(maxdd=maxdd, capital_final=capital_final, zerou=zerou)


def zerou_count(trades, capital_candidato: float) -> int:
    return int(rejeicao_stats(trades, capital_candidato)["zerou"].sum())


def busca_capital_minimo_seguro(trades, chute_inicial: float, tol_brl: float = 0.01) -> float:
    """Bisseccao: menor capital inicial tal que 0/30 sementes arruinam.
    Monotona por construcao (capital candidato so' desloca a curva para
    CIMA, os sorteios de aceite/rejeicao de cada semente sao FIXOS -- MESMOS
    `seed_base+s` -- e independentes do capital), entao existe um limiar
    unico e a bisseccao converge para ele. `hi` cresce (dobra) ate' passar
    (0/30) antes de comecar a fechar o intervalo -- cobre o caso do chute
    inicial ja nao ser suficiente."""
    lo, hi = 0.0, max(chute_inicial, 1.0)
    while zerou_count(trades, hi) > 0:
        hi *= 2.0
    while (hi - lo) > tol_brl:
        mid = (lo + hi) / 2.0
        if zerou_count(trades, mid) == 0:
            hi = mid
        else:
            lo = mid
    return hi


# ---------------------------------------------------------------------------
# achado operacional -- em que caixa a FORMULA DE PRODUCAO REAL (intocada)
# ja teria liberado N lotes, usando os anchors/volume/capacidade REAIS
# observados no IS (gravados em `strat.snapshots` durante a rodada-base).
# ---------------------------------------------------------------------------

def capital_que_producao_libera(snapshots: list[dict], target_n: int) -> float | None:
    """Caixa MINIMO, entre todos os instantes reais do IS, em que
    `lotes = 1 + floor(caixa/passo)` (com os tetos de volume/capacidade
    daquele instante) alcancaria `target_n`. `target_n<=1` nunca exige
    caixa (piso `max(1, lotes)`, achado 2026-08-23 documentado em
    gremah.py). Devolve `None` se NENHUM instante do IS real permite
    `target_n` (teto de volume do dia ou teto de capacidade saturam antes,
    caixa nenhum ajudaria)."""
    if target_n <= 1:
        return 0.0
    limiares = []
    for snap in snapshots:
        if snap["max_lotes_dia"] < target_n:
            continue
        limiar = (target_n - 1) * snap["passo"]
        cap = snap["capacidade_brl"]
        if cap is not None and cap < limiar:
            continue
        limiares.append(limiar)
    return min(limiares) if limiares else None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    run_bars, profile, referencia = carregar_is(SYMBOL, motor=MOTOR)
    if run_bars.empty:
        raise SystemExit(f"[capital_ladder] sem dado local IS para {SYMBOL!r} (motor={MOTOR!r})")
    pregoes_is = len(set(run_bars.index.date))
    print(f"[capital_ladder] {SYMBOL} motor={MOTOR} -- IS: {len(run_bars)} barras, "
          f"{pregoes_is} pregoes, {run_bars.index.min()} -> {run_bars.index.max()}, "
          f"preco de referencia (1a barra) R${num_br(referencia)}")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    print(f"[capital_ladder] economics (cache) {SYMBOL}: trade_tick_value="
          f"{economics.trade_tick_value} trade_tick_size={economics.trade_tick_size}")

    linhas: list[dict] = []
    trade_log_n1 = None

    for n in range(N_MIN, N_MAX + 1):
        print(f"\n=== N={n} lote(s) fixo(s) -- rodando BASE (capital nominal "
              f"R${num_br(CAPITAL_NOMINAL_PROBE_BRL, 0)}) ===", flush=True)
        strat, resultado = roda_base(n, run_bars, profile, economics)
        trades = list(resultado.trades)
        if getattr(resultado, "wiped_out_at", None) is not None:
            raise SystemExit(
                f"[capital_ladder] N={n}: a rodada-base ZEROU em {resultado.wiped_out_at} mesmo "
                f"com capital nominal de R${num_br(CAPITAL_NOMINAL_PROBE_BRL, 0)} -- capital de "
                "sondagem insuficiente, suba CAPITAL_NOMINAL_PROBE_BRL antes de confiar nos "
                "numeros abaixo (a sequencia de trades ficaria CENSURADA no meio do IS)."
            )
        puladas = len(getattr(resultado, "sessoes_puladas_por_capital", []) or [])
        if puladas:
            raise SystemExit(
                f"[capital_ladder] N={n}: {puladas} sessao(oes) pulada(s) por "
                "enforce_capital_minimo mesmo com capital nominal folgado -- investigar antes "
                "de confiar na sequencia de trades (ficaria CENSURADA)."
            )
        if n == N_MIN:
            trade_log_n1 = trades

        if trades:
            pior_caso = max(t.quantity * t.entry_price for t in trades)
        else:
            pior_caso = 0.0

        chute = max(pior_caso, 1.0)
        capital_seguro = busca_capital_minimo_seguro(trades, chute)
        stats_no_seguro = rejeicao_stats(trades, capital_seguro)
        assert int(stats_no_seguro["zerou"].sum()) == 0, (
            f"[capital_ladder] N={n}: bisseccao devolveu {capital_seguro} mas a confirmacao final "
            f"com 30 sementes NAO bateu 0/30 -- bug na busca."
        )

        libera_n = capital_que_producao_libera(strat.snapshots, n)
        if libera_n is None:
            libera_antes = "n/d (producao nunca alcanca N no IS real)"
        else:
            libera_antes = "sim" if libera_n < capital_seguro else "nao"

        maxdd_medio = float(stats_no_seguro["maxdd"].mean())
        maxdd_desvio = float(stats_no_seguro["maxdd"].std(ddof=1)) if N_SEMENTES > 1 else 0.0

        linha = dict(
            n_lotes=n,
            trades=len(trades),
            pior_caso_exigencia_capital_brl=pior_caso,
            capital_minimo_seguro_brl=capital_seguro,
            capital_que_producao_libera_n_brl=libera_n,
            producao_libera_antes_do_seguro=libera_antes,
            maxdd_medio_no_capital_seguro_brl=maxdd_medio,
            maxdd_desvio_no_capital_seguro_brl=maxdd_desvio,
        )
        linhas.append(linha)
        print(f"    trades={len(trades)} | pior_caso=R${num_br(pior_caso)} | "
              f"capital_minimo_seguro=R${num_br(capital_seguro)} | "
              f"producao_libera_N=R${'n/d' if libera_n is None else num_br(libera_n)} | "
              f"libera_antes_do_seguro={libera_antes} | "
              f"MaxDD(30 sementes, no capital seguro)=R${num_br(maxdd_medio)} +/- R${num_br(maxdd_desvio)}",
              flush=True)

    # ---------------------------------------------------------------
    # trade log do N=1 -> CSV (reusado pelas proximas etapas)
    # ---------------------------------------------------------------
    assert trade_log_n1 is not None
    df_log = pd.DataFrame([dict(
        entry_ts=t.entry_ts, exit_ts=t.exit_ts, entry_price=t.entry_price,
        exit_price=t.exit_price, side=t.side, quantity=t.quantity,
        pnl_brl=t.pnl_brl, exit_reason=(t.exit_reason.value if hasattr(t.exit_reason, "value")
                                         else str(t.exit_reason)),
    ) for t in trade_log_n1])
    df_log.to_csv(CSV_TRADE_LOG_N1, index=False)
    print(f"\n[capital_ladder] trade log N=1 ({len(df_log)} trades) salvo em {CSV_TRADE_LOG_N1}")

    with open(JSON_RESULTADO, "w", encoding="utf-8") as fh:
        json.dump(dict(
            symbol=SYMBOL, motor=MOTOR, pregoes_is=pregoes_is,
            janela_inicio=str(run_bars.index.min()), janela_fim=str(run_bars.index.max()),
            capital_nominal_probe_brl=CAPITAL_NOMINAL_PROBE_BRL,
            n_sementes=N_SEMENTES, p_alvo=P_ALVO, seed_base=SEED_BASE,
            linhas=linhas,
        ), fh, indent=2, ensure_ascii=False, default=str)
    print(f"[capital_ladder] resultado completo salvo em {JSON_RESULTADO}")

    # ---------------------------------------------------------------
    # tabela final -- CRUA, sem veredito embutido
    # ---------------------------------------------------------------
    print(f"\n\n=== ESCADA DE CAPITAL -- {SYMBOL} motor={MOTOR}, IS ({pregoes_is} pregoes), "
          f"rejeicao i.i.d. p={num_br(P_ALVO*100, 0)}% / {N_SEMENTES} sementes ===")
    cab = (f"{'N':>3}{'pior_caso_R$':>16}{'cap_min_seguro_R$':>20}{'cap_producao_libera_N_R$':>26}"
           f"{'libera_antes?':>16}{'trades':>9}{'MaxDD_R$(30 sementes)':>26}")
    print(cab)
    print("-" * len(cab))
    for linha in linhas:
        libera_txt = ("n/d" if linha["capital_que_producao_libera_n_brl"] is None
                      else num_br(linha["capital_que_producao_libera_n_brl"]))
        maxdd_txt = f"{num_br(linha['maxdd_medio_no_capital_seguro_brl'])} +/- {num_br(linha['maxdd_desvio_no_capital_seguro_brl'])}"
        print(f"{linha['n_lotes']:>3}{num_br(linha['pior_caso_exigencia_capital_brl']):>16}"
              f"{num_br(linha['capital_minimo_seguro_brl']):>20}{libera_txt:>26}"
              f"{linha['producao_libera_antes_do_seguro']:>16}{linha['trades']:>9}{maxdd_txt:>26}")


if __name__ == "__main__":
    main()
