"""QUALIDADE DE SINAL da `GremahTick` (PMAM3, motor tick), 2026-08-27 --
continuacao direta da "Escada de capital GremahTick" (mesmo dia, mesmo
arquivo de trades). Pergunta: que CARACTERISTICAS DE ENTRADA, calculaveis
SO' com dado disponivel ATE o instante do toque (nunca com o resultado do
trade), distinguem trade vencedor de perdedor -- e' um filtro de ruido
possivel, ou nao ha' sinal mensuravel?

## Entrada de dado (reaproveitada, nao recalculada)

Trade log: `scratch/scripts/capital_ladder_gremahtick_pmam3_n1_trades_2026_08_27.
csv` (1.310 trades, N=1 lote fixo, PMAM3, motor tick -- gerado por
`capital_ladder_gremahtick_2026_08_27.py`, ja' documentado la' como IS puro).
Barras: `_geometria_comum.carregar_is("PMAM3", motor="tick")` -- A MESMA
funcao usada na etapa anterior (chama `market_data_intraday.tick_storage.
load_ticks` + `tick_bars.ticks_to_degenerate_bars`, corta pelo mesmo split
congelado `LockedBars`/`OOS_CUTOFF`). `unlock()` nunca e' chamado.

## Padrao reaproveitado de `copa_rejection_lab.py` (nao reescrito do zero)

O nucleo estatistico -- `testa_proxy` (correlacao de Pearson + teste de
permutacao + diferenca por tercil, tambem por permutacao) e
`proxies_reproduziveis` (gate de split-half: MESMO sinal E p<0,05 no pool
E p<0,10 em CADA metade cronologica) -- e' copiado quase literal daquele
arquivo (que por sua vez generaliza em `(x, y)`, sem nada especifico de
WIN@/WDO@). So' a camada de proxy muda: em vez da barra M1 de preenchimento
de uma ordem `EnterLimit` da familia `copa`, aqui os proxies vem do TICK de
toque e da janela de ticks anteriores da `GremahTick` (`computa_features`,
abaixo) -- adaptado as colunas do trade log desta estrategia, como pedido.

## Por que NAO usamos o `anchor` real da estrategia como referencia de distancia

`GremahTick.on_bar` (gremah_tick.py:1264-1273): na fase FIXA (`ts.time() <
fixed_anchor_until=14:00 UTC`, so' a 1a hora do pregao) o anchor e' o preco
de ABERTURA do dia -- reconstrutivel. Mas na fase ROLANTE (o resto do
pregao, onde cai a maioria dos trades) o anchor e' `bar.close` NO INSTANTE
em que a ordem foi ARMADA (`state.pending_since_ts`), que pode ser
REARMADA varias vezes antes do toque real (`stale_rolling_order`, a cada
`rolling_reanchor_after_seconds`) -- e' um estado que só existe DENTRO do
loop do motor, nao reconstruivel so' com as barras e o trade log (exigiria
reinstrumentar a estrategia, replicando o padrao de
`GremahTickLoteFixo.snapshots` da etapa anterior). Para nao reabrir esse
custo e manter o metodo 100% "dado-e-trade-log" (mesmo espirito de
`copa_rejection_lab.computa_proxies`, que tambem nunca olha estado interno
da estrategia), usamos DUAS referencias so' com dado observavel, as duas
ja sugeridas pela missao como alternativa explicita ao anchor: (a) o preco
de ABERTURA do dia (proxy fiel so' na fase fixa, aproximado na rolante) e
(b) uma media movel curta dos ticks anteriores (referencia local, valida
nas duas fases). Reportado honestamente abaixo se (a) ou (b) mostrou sinal.

## As 10 features candidatas (as 5 categorias da missao, cada uma com
primaria + variante de robustez onde fazia sentido)

  1. minutos_desde_abertura     -- hora do pregao (minutos desde o 1o tick do dia)
  2. velocidade_10t / 3.velocidade_30t -- momentum nos K ticks antes do toque,
     sinal alinhado ao LADO (positivo = mercado andou na direcao que levou
     ao toque -- queda antes de um long, alta antes de um short)
  4. volume_toque               -- volume do PROPRIO tick de toque
  5. volume_janela_10t / 6. volume_janela_30t -- volume medio dos K ticks antes
  7. distancia_abertura_ticks   -- distancia (ticks, sinal alinhado ao lado)
     entre o preco de entrada e o preco de abertura do dia
  8. distancia_sma20_ticks      -- idem, contra a media movel dos ultimos 20
     ticks (referencia local, ver nota do anchor acima)
  9. range_20t_ticks / 10. range_50t_ticks -- regime de volatilidade recente
     (max-min dos closes na janela, em ticks)

Toda janela e' cortada na FRONTEIRA DA SESSAO (nunca atravessa a virada de
pregao) e exige uma contagem minima de ticks (`MIN_FRAC` da janela pedida,
piso de 3) -- trade sem janela valida fica de fora SO' daquela feature
(mesmo padrao de `velocidade_valida` em copa_rejection_lab.py), nunca do
resto da tabela.

## Filtro (so' para features que sobrevivem ao gate de reproducao)

Metade 1 cronologica calibra o limiar (mediana da feature naquela metade,
na direcao do sinal da correlacao -- maior-e-melhor ou menor-e-melhor);
metade 2 cronologica SO' aplica esse numero ja fechado (sem re-calibrar) e
mede o efeito liquido: trades descartados, P&L com/sem filtro, MaxDD
com/sem filtro. Split identico ao usado no proprio gate de reproducao
(mesmo corte cronologico, sem reaproveitar dado da metade 2 pra decidir o
limiar).

Janela: SO' o trade log do IS (ja' filtrado na etapa anterior) e as barras
IS (`carregar_is`, corte `OOS_CUTOFF` congelado). Nada em `src/` foi
tocado; nenhum arquivo existente foi editado.

Uso:
    python -u scripts/daytrade/signal_quality_gremahtick_2026_08_27.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.continuidade_permutation import pearson_corr  # noqa: E402
from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402

from _geometria_comum import carregar_economics, carregar_is  # noqa: E402

# ---------------------------------------------------------------------------
# entrada
# ---------------------------------------------------------------------------
SYMBOL = "PMAM3"
MOTOR = "tick"
CSV_TRADE_LOG = ROOT / "scratch" / "scripts" / "capital_ladder_gremahtick_pmam3_n1_trades_2026_08_27.csv"

SCRATCH_DIR = ROOT / "scratch" / "scripts"
CSV_FEATURES_RESUMO = SCRATCH_DIR / "signal_quality_gremahtick_features_2026_08_27.csv"
CSV_FILTRO_EFEITO = SCRATCH_DIR / "signal_quality_gremahtick_filtro_efeito_2026_08_27.csv"

N_PERM = 5000
N_PERM_SPLIT = 3000
MIN_FRAC = 0.5  # fracao minima da janela pedida que precisa estar presente
MIN_TICKS_PISO = 3


# ---------------------------------------------------------------------------
# casamento trade -> posicao na serie de ticks (robusto a timestamp duplicado
# -- tick data tem MUITOS timestamps repetidos, negocios diferentes no mesmo
# milissegundo; `Index.get_indexer` exige indice UNICO e quebraria aqui).
# Ponteiro monotono: como os trades estao em ordem cronologica (verificado
# abaixo, `entry_ts.is_monotonic_increasing`), cada casamento comeca a
# procurar a partir de onde o casamento anterior parou -- nunca re-casa um
# tick ja' consumido por um trade anterior.
# ---------------------------------------------------------------------------

def casa_trades_com_ticks(entry_ts: pd.DatetimeIndex, entry_price: np.ndarray,
                           bars_index: pd.DatetimeIndex, bars_close: np.ndarray) -> tuple[np.ndarray, int]:
    n_bars = len(bars_index)
    ptr = 0
    posicoes = np.full(len(entry_ts), -1, dtype=np.int64)
    sem_match = 0
    for i, (ts, price) in enumerate(zip(entry_ts, entry_price)):
        pos = max(int(bars_index.searchsorted(ts, side="left")), ptr)
        achado = -1
        p = pos
        while p < n_bars and bars_index[p] == ts:
            if abs(bars_close[p] - price) < 1e-6:
                achado = p
                break
            p += 1
        posicoes[i] = achado
        if achado < 0:
            sem_match += 1
        else:
            ptr = achado + 1
    return posicoes, sem_match


# ---------------------------------------------------------------------------
# fronteiras de sessao (posicao do 1o tick do dia, por posicao) -- vetorizado
# ---------------------------------------------------------------------------

def posicoes_inicio_sessao(bars_index: pd.DatetimeIndex) -> np.ndarray:
    dias = bars_index.date
    n = len(dias)
    novo_dia = np.empty(n, dtype=bool)
    novo_dia[0] = True
    novo_dia[1:] = dias[1:] != dias[:-1]
    inicios = np.nonzero(novo_dia)[0]
    idx_do_inicio = np.searchsorted(inicios, np.arange(n), side="right") - 1
    return inicios[idx_do_inicio]


# ---------------------------------------------------------------------------
# features por trade -- toda janela e' cortada em [inicio_sessao, pos), NUNCA
# inclui o proprio tick de toque nem atravessa a virada de pregao.
# ---------------------------------------------------------------------------

@dataclass
class Features:
    pnl_brl: np.ndarray
    entry_ts: pd.DatetimeIndex
    valores: dict[str, np.ndarray] = field(default_factory=dict)
    validos: dict[str, np.ndarray] = field(default_factory=dict)


def _janela_valida(inicio_sessao: int, pos: int, k: int) -> tuple[int, int, bool]:
    lo = max(inicio_sessao, pos - k)
    tamanho = pos - lo
    minimo = max(MIN_TICKS_PISO, int(round(k * MIN_FRAC)))
    return lo, pos, tamanho >= minimo


def computa_features(df: pd.DataFrame, bars: pd.DataFrame, tick_size: float) -> tuple[Features, int]:
    bars_index = bars.index
    closes = bars["close"].to_numpy(dtype=np.float64)
    volumes = bars["volume"].to_numpy(dtype=np.float64)
    inicio_sessao_por_pos = posicoes_inicio_sessao(bars_index)

    entry_ts = pd.DatetimeIndex(df["entry_ts"]).astype(bars_index.dtype)
    entry_price = df["entry_price"].to_numpy(dtype=np.float64)
    side = df["side"].to_numpy()
    pnl = df["pnl_brl"].to_numpy(dtype=np.float64)

    posicoes, sem_match = casa_trades_com_ticks(entry_ts, entry_price, bars_index, closes)

    n = len(df)
    minutos_desde_abertura = np.full(n, np.nan)
    vel10 = np.full(n, np.nan); vel10_ok = np.zeros(n, dtype=bool)
    vel30 = np.full(n, np.nan); vel30_ok = np.zeros(n, dtype=bool)
    vol_toque = np.full(n, np.nan)
    vol_j10 = np.full(n, np.nan); vol_j10_ok = np.zeros(n, dtype=bool)
    vol_j30 = np.full(n, np.nan); vol_j30_ok = np.zeros(n, dtype=bool)
    dist_abert = np.full(n, np.nan)
    dist_sma20 = np.full(n, np.nan); dist_sma20_ok = np.zeros(n, dtype=bool)
    range20 = np.full(n, np.nan); range20_ok = np.zeros(n, dtype=bool)
    range50 = np.full(n, np.nan); range50_ok = np.zeros(n, dtype=bool)
    matched = np.zeros(n, dtype=bool)

    for i in range(n):
        pos = posicoes[i]
        if pos < 0:
            continue
        matched[i] = True
        s = side[i]
        sinal = 1.0 if s == "long" else -1.0
        inicio_sessao = inicio_sessao_por_pos[pos]

        minutos_desde_abertura[i] = (bars_index[pos] - bars_index[inicio_sessao]).total_seconds() / 60.0
        vol_toque[i] = volumes[pos]
        dist_abert[i] = sinal * (closes[inicio_sessao] - entry_price[i]) / tick_size

        lo, hi, ok = _janela_valida(inicio_sessao, pos, 10)
        if ok:
            janela_c = closes[lo:hi]
            vel10[i] = sinal * (janela_c[0] - janela_c[-1]) / tick_size
            vel10_ok[i] = True
            vol_j10[i] = float(volumes[lo:hi].mean())
            vol_j10_ok[i] = True

        lo, hi, ok = _janela_valida(inicio_sessao, pos, 30)
        if ok:
            janela_c = closes[lo:hi]
            vel30[i] = sinal * (janela_c[0] - janela_c[-1]) / tick_size
            vel30_ok[i] = True
            vol_j30[i] = float(volumes[lo:hi].mean())
            vol_j30_ok[i] = True

        lo, hi, ok = _janela_valida(inicio_sessao, pos, 20)
        if ok:
            janela_c = closes[lo:hi]
            dist_sma20[i] = sinal * (float(janela_c.mean()) - entry_price[i]) / tick_size
            dist_sma20_ok[i] = True
            range20[i] = (janela_c.max() - janela_c.min()) / tick_size
            range20_ok[i] = True

        lo, hi, ok = _janela_valida(inicio_sessao, pos, 50)
        if ok:
            janela_c = closes[lo:hi]
            range50[i] = (janela_c.max() - janela_c.min()) / tick_size
            range50_ok[i] = True

    feats = Features(
        pnl_brl=pnl,
        entry_ts=entry_ts,
        valores=dict(
            minutos_desde_abertura=minutos_desde_abertura,
            velocidade_10t=vel10, velocidade_30t=vel30,
            volume_toque=vol_toque, volume_janela_10t=vol_j10, volume_janela_30t=vol_j30,
            distancia_abertura_ticks=dist_abert, distancia_sma20_ticks=dist_sma20,
            range_20t_ticks=range20, range_50t_ticks=range50,
        ),
        validos=dict(
            minutos_desde_abertura=matched.copy(),
            velocidade_10t=matched & vel10_ok, velocidade_30t=matched & vel30_ok,
            volume_toque=matched.copy(), volume_janela_10t=matched & vol_j10_ok, volume_janela_30t=matched & vol_j30_ok,
            distancia_abertura_ticks=matched.copy(), distancia_sma20_ticks=matched & dist_sma20_ok,
            range_20t_ticks=matched & range20_ok, range_50t_ticks=matched & range50_ok,
        ),
    )
    return feats, sem_match


# ---------------------------------------------------------------------------
# nucleo estatistico -- copiado (adaptado em nomes) de
# `copa_rejection_lab.py::testa_proxy` / `_permuta_correlacao` /
# `_permuta_diff_tercil` / `_split_half` / `proxies_reproduziveis`, que ja'
# eram genericos em `(x, y)` (nao especificos de WIN@/WDO@) -- reusados em
# vez de reescritos.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResultadoCorrelacao:
    nome: str
    n: int
    corr_real: float
    percentil: float
    p_two_sided: float
    tercil_baixo_media: float
    tercil_alto_media: float
    diff_tercil: float
    diff_tercil_p: float


def _permuta_correlacao(x: np.ndarray, y: np.ndarray, n_perm: int, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    real = pearson_corr(x, y)
    nulo = np.empty(n_perm)
    for i in range(n_perm):
        nulo[i] = pearson_corr(rng.permutation(x), y)
    n_ge = int(np.sum(nulo >= real))
    n_le = int(np.sum(nulo <= real))
    p_two = min(2.0 * min((n_ge + 1) / (n_perm + 1), (n_le + 1) / (n_perm + 1)), 1.0)
    percentil = 100.0 * float(np.mean(nulo <= real))
    return percentil, p_two


def _permuta_diff_tercil(x: np.ndarray, y: np.ndarray, n_perm: int, seed: int) -> tuple[float, float, float, float]:
    def _diff(xx: np.ndarray, yy: np.ndarray) -> tuple[float, float, float]:
        ordem = np.argsort(xx)
        n = len(xx)
        corte = n // 3
        baixo = yy[ordem[:corte]]
        alto = yy[ordem[-corte:]]
        return float(baixo.mean()), float(alto.mean()), float(alto.mean() - baixo.mean())

    b_real, a_real, real = _diff(x, y)
    rng = np.random.default_rng(seed)
    nulo = np.empty(n_perm)
    for i in range(n_perm):
        _, _, nulo[i] = _diff(rng.permutation(x), y)
    n_ge = int(np.sum(nulo >= real))
    n_le = int(np.sum(nulo <= real))
    p_two = min(2.0 * min((n_ge + 1) / (n_perm + 1), (n_le + 1) / (n_perm + 1)), 1.0)
    return b_real, a_real, real, p_two


def testa_proxy(nome: str, x: np.ndarray, y: np.ndarray, n_perm: int = N_PERM, seed: int = 0) -> ResultadoCorrelacao:
    percentil, p_corr = _permuta_correlacao(x, y, n_perm, seed)
    b_media, a_media, diff, p_diff = _permuta_diff_tercil(x, y, n_perm, seed + 1)
    return ResultadoCorrelacao(
        nome=nome, n=len(x), corr_real=pearson_corr(x, y), percentil=percentil,
        p_two_sided=p_corr, tercil_baixo_media=b_media, tercil_alto_media=a_media,
        diff_tercil=diff, diff_tercil_p=p_diff,
    )


def imprime_correlacao(r: ResultadoCorrelacao) -> None:
    print(f"\nfeature: {r.nome} (n={r.n})")
    print(f"  correlacao de Pearson (feature, pnl_brl do trade) = {num_br(r.corr_real, 4)} "
          f"| percentil no nulo por permutacao = {num_br(r.percentil, 1)}% "
          f"| p bicaudal = {num_br(r.p_two_sided, 4)}")
    print(f"  tercil BAIXO da feature: pnl medio R${num_br(r.tercil_baixo_media)} | "
          f"tercil ALTO: R${num_br(r.tercil_alto_media)} | "
          f"diferenca (alto-baixo) = R${num_br(r.diff_tercil)} | p bicaudal = {num_br(r.diff_tercil_p, 4)}")


def _split_half(x: np.ndarray, y: np.ndarray, seed: int) -> tuple[float, float, float, float]:
    meio = len(x) // 2
    p1, _ = _permuta_correlacao(x[:meio], y[:meio], N_PERM_SPLIT, seed)
    p2, _ = _permuta_correlacao(x[meio:], y[meio:], N_PERM_SPLIT, seed + 1)
    c1 = pearson_corr(x[:meio], y[:meio])
    c2 = pearson_corr(x[meio:], y[meio:])
    return c1, c2, p1, p2


@dataclass(frozen=True)
class LinhaFeatureCrua:
    """Uma linha da tabela CRUA final -- TODAS as features testadas, mesmo as
    que nao sobreviveram (nao esconder negativo)."""
    nome: str
    n: int
    corr_pool: float
    p_pool: float
    corr_metade1: float
    p_metade1_aprox: float
    corr_metade2: float
    p_metade2_aprox: float
    diff_tercil: float
    p_diff_tercil: float
    reproduzivel: bool


def proxies_reproduziveis(candidatos: dict[str, tuple[np.ndarray, np.ndarray, ResultadoCorrelacao]]
                           ) -> tuple[list[tuple[str, np.ndarray, np.ndarray]], list[LinhaFeatureCrua]]:
    """Exige MESMO sinal E p<0,05 no pool inteiro E p<0,10 nas DUAS metades
    cronologicas -- identico ao gate de `copa_rejection_lab.py` (mesma
    armadilha ja documentada la': proxy pode ter p<0,05 no pool e ser
    artefato de um sub-periodo)."""
    print("\n--- split-half (reprodutibilidade): correlacao na 1a vs 2a metade cronologica ---")
    reproduziveis: list[tuple[str, np.ndarray, np.ndarray]] = []
    linhas: list[LinhaFeatureCrua] = []
    for nome, (x, y, r) in candidatos.items():
        c1, c2, perc1, perc2 = _split_half(x, y, seed=100)
        mesmo_sinal = (c1 > 0) == (c2 > 0) == (r.corr_real > 0)
        p1_aprox = min(2 * min(perc1, 100 - perc1) / 100.0, 1.0)
        p2_aprox = min(2 * min(perc2, 100 - perc2) / 100.0, 1.0)
        ok = mesmo_sinal and r.p_two_sided < 0.05 and p1_aprox < 0.10 and p2_aprox < 0.10
        print(f"  {nome}: 1a metade corr={num_br(c1, 4)} (p~{num_br(p1_aprox, 3)}), "
              f"2a metade corr={num_br(c2, 4)} (p~{num_br(p2_aprox, 3)}), "
              f"pool p={num_br(r.p_two_sided, 4)}, n={r.n} -- reproduzivel E significativo? {ok}")
        linhas.append(LinhaFeatureCrua(
            nome=nome, n=r.n, corr_pool=r.corr_real, p_pool=r.p_two_sided,
            corr_metade1=c1, p_metade1_aprox=p1_aprox, corr_metade2=c2, p_metade2_aprox=p2_aprox,
            diff_tercil=r.diff_tercil, p_diff_tercil=r.diff_tercil_p, reproduzivel=ok,
        ))
        if ok:
            reproduziveis.append((nome, x, y))
    return reproduziveis, linhas


# ---------------------------------------------------------------------------
# filtro simples: calibra limiar na metade1 (mediana, na direcao do sinal da
# correlacao), aplica O MESMO NUMERO na metade2, mede efeito liquido.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EfeitoFiltro:
    nome: str
    direcao: str
    limiar: float
    n_metade2: int
    n_mantidos: int
    n_descartados: int
    pnl_sem_filtro: float
    pnl_com_filtro: float
    pnl_por_trade_sem_filtro: float
    pnl_por_trade_com_filtro: float
    maxdd_sem_filtro: float
    maxdd_com_filtro: float
    win_rate_sem_filtro: float
    win_rate_com_filtro: float


def simula_filtro(nome: str, x: np.ndarray, y: np.ndarray, corr_real: float) -> EfeitoFiltro:
    meio = len(x) // 2
    x1, y1 = x[:meio], y[:meio]
    x2, y2 = x[meio:], y[meio:]

    maior_e_melhor = corr_real > 0
    limiar = float(np.median(x1))
    mask2 = (x2 >= limiar) if maior_e_melhor else (x2 <= limiar)

    curva_sem = pd.Series(np.concatenate([[0.0], np.cumsum(y2)]))
    curva_com = pd.Series(np.concatenate([[0.0], np.cumsum(y2[mask2])]))

    n_mantidos = int(mask2.sum())
    return EfeitoFiltro(
        nome=nome, direcao=(">=" if maior_e_melhor else "<="), limiar=limiar,
        n_metade2=len(y2), n_mantidos=n_mantidos, n_descartados=int((~mask2).sum()),
        pnl_sem_filtro=float(y2.sum()), pnl_com_filtro=float(y2[mask2].sum()),
        pnl_por_trade_sem_filtro=float(y2.mean()) if len(y2) else 0.0,
        pnl_por_trade_com_filtro=float(y2[mask2].mean()) if n_mantidos else 0.0,
        maxdd_sem_filtro=maxdd_brl(curva_sem), maxdd_com_filtro=maxdd_brl(curva_com),
        win_rate_sem_filtro=float((y2 > 0).mean()) if len(y2) else 0.0,
        win_rate_com_filtro=float((y2[mask2] > 0).mean()) if n_mantidos else 0.0,
    )


def imprime_filtro(ef: EfeitoFiltro) -> None:
    print(f"\nfiltro calibrado em '{ef.nome}' (limiar aprendido na metade1, aplicado na metade2)")
    print(f"  regra: entra so' se {ef.nome} {ef.direcao} {num_br(ef.limiar, 4)}")
    print(f"  metade2: {ef.n_metade2} trades -> {ef.n_mantidos} mantidos, {ef.n_descartados} descartados")
    print(f"  P&L metade2 SEM filtro = R${num_br(ef.pnl_sem_filtro)} | COM filtro = R${num_br(ef.pnl_com_filtro)}")
    print(f"  P&L POR TRADE SEM filtro = R${num_br(ef.pnl_por_trade_sem_filtro, 4)} | "
          f"COM filtro = R${num_br(ef.pnl_por_trade_com_filtro, 4)}")
    print(f"  MaxDD metade2 SEM filtro = R${num_br(ef.maxdd_sem_filtro)} | COM filtro = R${num_br(ef.maxdd_com_filtro)}")
    print(f"  P&L/MaxDD (Calmar bruto) SEM filtro = {num_br(ef.pnl_sem_filtro / ef.maxdd_sem_filtro, 2) if ef.maxdd_sem_filtro else '—'} | "
          f"COM filtro = {num_br(ef.pnl_com_filtro / ef.maxdd_com_filtro, 2) if ef.maxdd_com_filtro else '—'}")
    print(f"  win rate SEM filtro = {num_br(ef.win_rate_sem_filtro * 100, 1)}% | "
          f"COM filtro = {num_br(ef.win_rate_com_filtro * 100, 1)}%")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CSV_TRADE_LOG)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    assert df["entry_ts"].is_monotonic_increasing, "trade log nao esta em ordem cronologica -- split-half quebraria"
    print(f"[signal_quality] trade log: {CSV_TRADE_LOG} -- {len(df)} trades, "
          f"{df['entry_ts'].min()} -> {df['entry_ts'].max()}")

    run_bars, profile, referencia = carregar_is(SYMBOL, motor=MOTOR)
    if run_bars.empty:
        raise SystemExit(f"[signal_quality] sem dado local IS para {SYMBOL!r} (motor={MOTOR!r})")
    print(f"[signal_quality] IS: {len(run_bars)} ticks, {run_bars.index.min()} -> {run_bars.index.max()}")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    tick_size = economics.trade_tick_size
    print(f"[signal_quality] tick_size {SYMBOL} = {tick_size}")

    feats, sem_match = computa_features(df, run_bars, tick_size)
    n_matched = int(sum(feats.validos["minutos_desde_abertura"]))
    print(f"[signal_quality] casamento trade -> tick de toque: {n_matched}/{len(df)} "
          f"({sem_match} sem match -- deveria ser 0)")
    if sem_match:
        print("  ATENCAO: trades sem match sao excluidos de TODAS as features (nao entram em nenhuma tabela).")

    nomes_ordem = [
        "minutos_desde_abertura", "velocidade_10t", "velocidade_30t",
        "volume_toque", "volume_janela_10t", "volume_janela_30t",
        "distancia_abertura_ticks", "distancia_sma20_ticks",
        "range_20t_ticks", "range_50t_ticks",
    ]

    print(f"\n=== {SYMBOL} motor={MOTOR} -- PARTE B: correlacao feature <-> P&L do trade "
          f"(permutacao, n_perm={N_PERM}) ===")
    candidatos: dict[str, tuple[np.ndarray, np.ndarray, ResultadoCorrelacao]] = {}
    for idx_seed, nome in enumerate(nomes_ordem):
        mask = feats.validos[nome]
        x = feats.valores[nome][mask]
        y = feats.pnl_brl[mask]
        n_validos = int(mask.sum())
        print(f"\n[{nome}] {n_validos}/{len(df)} trades com janela valida")
        if n_validos < 30:
            print(f"  MENOS DE 30 trades validos -- pulando teste estatistico para esta feature.")
            continue
        r = testa_proxy(nome, x, y, seed=idx_seed)
        imprime_correlacao(r)
        candidatos[nome] = (x, y, r)

    reproduziveis, linhas_cruas = proxies_reproduziveis(candidatos)

    # ---------------- tabela CRUA -- todas as features, sobrevivendo ou nao ----------------
    print(f"\n\n=== {SYMBOL} motor={MOTOR} -- TABELA CRUA: TODAS as features testadas ===")
    cab = (f"{'feature':<26}{'n':>6}{'corr_pool':>11}{'p_pool':>9}{'corr_m1':>10}{'p_m1~':>9}"
           f"{'corr_m2':>10}{'p_m2~':>9}{'diff_tercil_R$':>16}{'p_diff':>9}{'reprod?':>9}")
    print(cab)
    print("-" * len(cab))
    for ln in linhas_cruas:
        print(f"{ln.nome:<26}{ln.n:>6}{num_br(ln.corr_pool, 4):>11}{num_br(ln.p_pool, 4):>9}"
              f"{num_br(ln.corr_metade1, 4):>10}{num_br(ln.p_metade1_aprox, 3):>9}"
              f"{num_br(ln.corr_metade2, 4):>10}{num_br(ln.p_metade2_aprox, 3):>9}"
              f"{num_br(ln.diff_tercil):>16}{num_br(ln.p_diff_tercil, 4):>9}"
              f"{str(ln.reproduzivel):>9}")

    pd.DataFrame([dict(
        feature=ln.nome, n=ln.n, corr_pool=ln.corr_pool, p_pool=ln.p_pool,
        corr_metade1=ln.corr_metade1, p_metade1_aprox=ln.p_metade1_aprox,
        corr_metade2=ln.corr_metade2, p_metade2_aprox=ln.p_metade2_aprox,
        diff_tercil_brl=ln.diff_tercil, p_diff_tercil=ln.p_diff_tercil,
        reproduzivel=ln.reproduzivel,
    ) for ln in linhas_cruas]).to_csv(CSV_FEATURES_RESUMO, index=False)
    print(f"\n[signal_quality] tabela de features salva em {CSV_FEATURES_RESUMO}")

    # ---------------- filtro (so' para quem sobreviveu) ----------------
    print(f"\n\n=== {SYMBOL} motor={MOTOR} -- VEREDITO E FILTRO ===")
    if not reproduziveis:
        print("Nenhuma das 10 features testadas (hora do pregao, momentum em 2 horizontes, "
              "volume no toque e em 2 janelas, distancia a' abertura e a' media movel curta, "
              "range em 2 janelas) mostrou correlacao significativa E reproduzivel (split-half) "
              "com o P&L do trade. Sem evidencia de sinal de entrada MENSURAVEL nesta resolucao "
              "-- reportado honestamente como risco NAO-mensuravel, sem forcar um filtro em cima "
              "de ruido.")
        return

    linhas_filtro = []
    for nome, x, y in reproduziveis:
        corr_real = pearson_corr(x, y)
        ef = simula_filtro(nome, x, y, corr_real)
        imprime_filtro(ef)
        linhas_filtro.append(dict(
            feature=ef.nome, direcao=ef.direcao, limiar=ef.limiar,
            n_metade2=ef.n_metade2, n_mantidos=ef.n_mantidos, n_descartados=ef.n_descartados,
            pnl_sem_filtro_brl=ef.pnl_sem_filtro, pnl_com_filtro_brl=ef.pnl_com_filtro,
            pnl_por_trade_sem_filtro_brl=ef.pnl_por_trade_sem_filtro, pnl_por_trade_com_filtro_brl=ef.pnl_por_trade_com_filtro,
            maxdd_sem_filtro_brl=ef.maxdd_sem_filtro, maxdd_com_filtro_brl=ef.maxdd_com_filtro,
            win_rate_sem_filtro_pct=ef.win_rate_sem_filtro * 100, win_rate_com_filtro_pct=ef.win_rate_com_filtro * 100,
        ))
    pd.DataFrame(linhas_filtro).to_csv(CSV_FILTRO_EFEITO, index=False)
    print(f"\n[signal_quality] efeito do(s) filtro(s) salvo em {CSV_FILTRO_EFEITO}")


if __name__ == "__main__":
    main()
