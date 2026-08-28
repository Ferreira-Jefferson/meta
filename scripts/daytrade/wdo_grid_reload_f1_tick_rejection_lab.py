"""Frente F1-wdo-consolidacao -- teste do modelo de REJEICAO PROBABILISTICA
de ordem pedido pelo dono (conversa 2026-08-27), como ALTERNATIVA ao modelo
de pedagio de fila FIXO por trade ja medido em `wdo_grid_reload_f1_tick_lab.py`
(secao 4: `p*tick_size*point_value_brl*pernas_maker` somado a TODO round-trip,
vencedor ou nao -- morre em ~0,41 tick/perna).

Objecao do dono ao modelo fixo: uma ordem-limite que NUNCA preenche nao
deveria pagar custo nenhum -- ela simplesmente nao vira trade. Pedido:
"colocar um percentual que aleatoriamente faz a ordem ser aceita ou nao --
a cada sinal de entrada roda um numero aleatorio, se cair um dos numeros que
diz que a ordem nao foi aceita, nao computamos a entrada. No final a
estrategia tem que ser assertiva nas ordens que sao aceitas, nao importa se
e' menos ordens, o importante e' que nas que sao aceitas eu tenha ganhos."

Duas partes, OBRIGATORIAS as duas (ver a missao completa para a explicacao
matematica de cada uma):

  A. Rejeicao i.i.d. (SORTEIO independente por trade, SEM olhar o P&L do
     trade -- so' decide se ele "existe" ou nao) sobre a lista de trades ja
     computada pelo run TICK atrito-zero-de-fila (`wdo_grid_reload_f1_tick_
     lab.py`). Matematicamente TEM que escalar ~linear com p e continuar
     positivo pra quase todo p>0 (reduzir uma amostra aleatoria de trades
     JA lucrativos, sem mudar o P&L de cada um, preserva o sinal em
     esperanca) -- e' a BASELINE de comparacao, nao o achado.

  B. Rejeicao CORRELACIONADA com um proxy de "quao disputado estava aquele
     preco no instante do toque" (adverse selection / "maldicao do market
     maker"), calculado A PARTIR DO TICK CRU (nao do trade): velocidade de
     aproximacao ao nivel, volume/contagem de negocios NO MESMO PRECO antes
     do toque, e se o toque foi um "gap through" (o preco pulou o nivel, nao
     tocou exatamente nele) -- os tres proxies sugeridos pelo dono. Testa
     correlacao real (permutacao) entre cada proxy e o P&L do trade; SO' se
     achar correlacao (p<0,05, reproduzivel em split-half) constroi um
     modelo de rejeicao onde p_rejeicao CRESCE com o proxy, e compara o
     liquido resultante contra a Parte A no MESMO p medio.

DISCIPLINA anti-look-ahead (a mesma do resto do repo, reforcada pelo dono
nesta rodada): todo proxy usa SO' ticks ANTES do toque (ou o proprio tick do
toque, que e' informacao disponivel no INSTANTE em que a decisao de
aceitar/rejeitar teria que ser tomada) -- NUNCA o resultado do trade.

Reaproveita (nao reescreve) `carregar_tick_bars`/`montar_config`/`rodar` de
`wdo_grid_reload_f1_tick_lab.py`/`wdo_grid_reload_f1_lab.py` -- MESMA regra
de fronteira ja documentada la (import, nunca edicao de infra consolidada).

Uso: `python -u scripts/daytrade/wdo_grid_reload_f1_tick_rejection_lab.py`
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
from backtest.intraday.machine import IntradayTrade  # noqa: E402
from backtest.intraday.report import num_br  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WDO_TICK_SIZE  # noqa: E402
from wdo_grid_reload_f1_tick_lab import carregar_tick_bars  # noqa: E402
from wdo_grid_reload_f1_lab import montar_config, rodar  # noqa: E402

#: Grade de taxa de aceitacao pedida pela missao.
GRADE_P = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)
N_SEMENTES = 30

#: Janela de lookback (SEGUNDOS antes do toque) para os proxies de
#: velocidade/crowding -- tempo, nao contagem de ticks, porque a densidade
#: de negocios varia muito ao longo do pregao (abertura/fechamento vs meio
#: do dia); uma janela de tempo fixa e' comparavel entre esses regimes, uma
#: janela de N ticks nao seria (N ticks na abertura cobre segundos, N ticks
#: as 12h pode cobrir minutos). 15s e' o primario; 30s roda tambem na
#: auto-revisao (robustez, ver `main`).
JANELA_PROXY_S = 15
#: Minimo de ticks dentro da janela para o proxy de VELOCIDADE ser
#: considerado valido (crowding/gap nao precisam disso -- contam 0 se
#: vazio, o que e' informativo por si so).
MIN_TICKS_VELOCIDADE = 3


# ---------------------------------------------------------------------------
# Parte A -- rejeicao i.i.d.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LinhaSweep:
    p: float
    media: float
    desvio: float
    minimo: float
    maximo: float
    trades_medio: float


def sweep_iid(pnls: np.ndarray, n_sementes: int = N_SEMENTES,
               grade: tuple[float, ...] = GRADE_P, seed_base: int = 0) -> list[LinhaSweep]:
    """Sorteio i.i.d. POR TRADE (Bernoulli(p), independente entre trades e
    independente do P&L de cada um -- a decisao de aceitar nunca olha
    `pnls[i]`) -- confirma (ou refuta) que o liquido esperado escala
    ~linear com p e fica positivo pra quase todo p, exatamente a matematica
    que a missao pede pra nao pular."""
    n = len(pnls)
    linhas = []
    for p in grade:
        liquidos = np.empty(n_sementes)
        n_aceitos = np.empty(n_sementes)
        for s in range(n_sementes):
            rng = np.random.default_rng(seed_base + s)
            aceita = rng.random(n) < p  # sorteio POR TRADE, sem olhar pnls
            liquidos[s] = float(pnls[aceita].sum())
            n_aceitos[s] = int(aceita.sum())
        linhas.append(LinhaSweep(
            p=p, media=float(liquidos.mean()), desvio=float(liquidos.std(ddof=1)),
            minimo=float(liquidos.min()), maximo=float(liquidos.max()),
            trades_medio=float(n_aceitos.mean()),
        ))
    return linhas


def imprime_sweep(titulo: str, linhas: list[LinhaSweep]) -> None:
    print(f"\n=== {titulo} ===")
    print(f"{'p':>6} | {'liquido medio':>16} | {'desvio-padrao':>16} | "
          f"{'minimo':>14} | {'maximo':>14} | {'trades (media)':>14}")
    print("-" * 92)
    for ln in linhas:
        print(f"{num_br(ln.p * 100, 0):>5}% | R${num_br(ln.media):>13} | "
              f"R${num_br(ln.desvio):>13} | R${num_br(ln.minimo):>11} | "
              f"R${num_br(ln.maximo):>11} | {num_br(ln.trades_medio, 1):>14}")


# ---------------------------------------------------------------------------
# Parte B -- proxies de "quao disputado" a partir do TICK CRU
# ---------------------------------------------------------------------------

@dataclass
class ProxyTrade:
    pnl_brl: float
    gap_ticks: float           # 0 = toque EXATO no nivel; >0 = "gap through"
    velocidade: float          # movimento (em ticks) na DIRECAO do toque, janela pre-toque
    velocidade_valida: bool
    crowd_count: int           # negocios NO MESMO PRECO do nivel, janela pre-toque
    crowd_volume: float        # volume NO MESMO PRECO do nivel, janela pre-toque


def _tick_arrays(tick_bars: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(ts_ns, preco, volume)` -- arrays planos, ja ordenados (tick_bars
    vem de `buscar_ticks`, que ja faz `sort_index()`). `preco` = coluna
    `close` (OHLC == last do negocio nesta resolucao, ver a docstring de
    `wdo_grid_reload_f1_tick_probe.buscar_ticks`)."""
    ts_ns = tick_bars.index.values.astype("datetime64[ns]").astype(np.int64)
    preco = tick_bars["close"].to_numpy(dtype=np.float64)
    volume = tick_bars["volume"].to_numpy(dtype=np.float64)
    return ts_ns, preco, volume


def _acha_toque(ts_ns: np.ndarray, preco: np.ndarray, entry_ts_ns: int,
                 entry_price: float, side: str) -> int | None:
    """Posicao (indice em `ts_ns`/`preco`) do tick que efetivamente causou o
    toque -- pode haver mais de um tick com o MESMO timestamp (varios
    negocios no mesmo milissegundo); escolhe o PRIMEIRO, na ordem em que o
    motor os processou (`session_df.iterrows()`, ordem do array ja
    ordenado), que satisfaz a condicao de toque (`_limit_touched`: `preco <=
    limit_price` compra, `preco >= limit_price` venda) -- mesmo criterio
    exato de `backtest.intraday.machine._limit_touched`, so' fora do motor.
    `None` se nenhum tick bater o timestamp (nao deveria acontecer -- todo
    `entry_ts` de um trade tick veio de uma linha de `tick_bars`)."""
    candidatos = np.flatnonzero(ts_ns == entry_ts_ns)
    if len(candidatos) == 0:
        return None
    if len(candidatos) == 1:
        return int(candidatos[0])
    for idx in candidatos:
        p = preco[idx]
        if (p <= entry_price) if side == "long" else (p >= entry_price):
            return int(idx)
    return int(candidatos[0])


def computa_proxies(trades: list[IntradayTrade], tick_bars: pd.DataFrame,
                     tick_size: float = WDO_TICK_SIZE,
                     janela_s: int = JANELA_PROXY_S) -> tuple[list[ProxyTrade], int]:
    """Um `ProxyTrade` por `IntradayTrade`, calculado SO' com ticks ANTES do
    toque (ou o proprio tick do toque, permitido pela missao: 'velocidade/
    volume/gap ANTES ou NO momento do toque, nunca o resultado do trade em
    si'). Devolve tambem a contagem de trades sem tick correspondente
    encontrado (deveria ser 0; serve de checagem de sanidade)."""
    ts_ns, preco, volume = _tick_arrays(tick_bars)
    janela_ns = int(janela_s * 1_000_000_000)
    out: list[ProxyTrade] = []
    sem_match = 0
    for t in trades:
        entry_ts_ns = int(pd.Timestamp(t.entry_ts).value)
        touch_idx = _acha_toque(ts_ns, preco, entry_ts_ns, t.entry_price, t.side)
        if touch_idx is None:
            sem_match += 1
            continue
        touch_price = preco[touch_idx]
        # gap-through: 0 = tocou exatamente no nivel (t.entry_price); >0 =
        # o negocio que causou o toque ja tinha ido ALEM do nivel (a
        # simulacao preenche otimista, no PRECO DO NIVEL -- ver
        # `_resolve_limit_fills`: `order.limit_price`, nao o preco real do
        # negocio -- entao a diferenca so aparece comparando contra o tick
        # cru, nunca contra o proprio `IntradayTrade`).
        if t.side == "long":
            gap = max(0.0, (t.entry_price - touch_price) / tick_size)
        else:
            gap = max(0.0, (touch_price - t.entry_price) / tick_size)

        # janela pre-toque (estritamente ANTES do proprio tick de toque):
        # busca por tempo, nao por contagem de ticks -- ver `JANELA_PROXY_S`.
        limite_inferior_ns = entry_ts_ns - janela_ns
        inicio = int(np.searchsorted(ts_ns, limite_inferior_ns, side="left"))
        fim = touch_idx  # exclusivo -- nao inclui o proprio tick de toque
        janela_precos = preco[inicio:fim]
        janela_vol = volume[inicio:fim]

        if len(janela_precos) >= MIN_TICKS_VELOCIDADE:
            # velocidade: quanto o preco ja se moveu NA DIRECAO do toque
            # dentro da janela -- positivo = aproximacao rapida/direcional;
            # perto de 0 = preco parado/lateral antes de tocar.
            if t.side == "long":
                vel = (janela_precos[0] - janela_precos[-1]) / tick_size
            else:
                vel = (janela_precos[-1] - janela_precos[0]) / tick_size
            vel_valida = True
        else:
            vel = 0.0
            vel_valida = False

        no_nivel = np.isclose(janela_precos, t.entry_price, atol=1e-9)
        crowd_count = int(no_nivel.sum())
        crowd_volume = float(janela_vol[no_nivel].sum())

        out.append(ProxyTrade(
            pnl_brl=t.pnl_brl, gap_ticks=gap, velocidade=vel,
            velocidade_valida=vel_valida, crowd_count=crowd_count,
            crowd_volume=crowd_volume,
        ))
    return out, sem_match


# ---------------------------------------------------------------------------
# correlacao + teste de permutacao (proxy <-> pnl do trade)
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
    """Embaralha `x` (o proxy) `n_perm` vezes, mantendo `y` (pnl) fixo --
    destroi o PAREAMENTO proxy<->trade preservando as duas distribuicoes
    marginais, mesmo espirito de `continuidade_permutation.permutation_test`
    (so' que sem a estrutura de grupos/lag, que nao se aplica aqui: cada
    trade e' uma observacao independente, nao uma serie ordenada)."""
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
    """Diferenca de media de `y` entre tercil ALTO e tercil BAIXO de `x`,
    com p-valor por permutacao (embaralha `x`, recalcula a diferenca)."""
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


def testa_proxy(nome: str, x: np.ndarray, y: np.ndarray, n_perm: int = 5000, seed: int = 0) -> ResultadoCorrelacao:
    percentil, p_corr = _permuta_correlacao(x, y, n_perm, seed)
    b_media, a_media, diff, p_diff = _permuta_diff_tercil(x, y, n_perm, seed + 1)
    return ResultadoCorrelacao(
        nome=nome, n=len(x), corr_real=pearson_corr(x, y), percentil=percentil,
        p_two_sided=p_corr, tercil_baixo_media=b_media, tercil_alto_media=a_media,
        diff_tercil=diff, diff_tercil_p=p_diff,
    )


def imprime_correlacao(r: ResultadoCorrelacao) -> None:
    print(f"\nproxy: {r.nome} (n={r.n})")
    print(f"  correlacao de Pearson (proxy, pnl_brl do trade) = {num_br(r.corr_real, 4)} "
          f"| percentil no nulo por permutacao = {num_br(r.percentil, 1)}% "
          f"| p bicaudal = {num_br(r.p_two_sided, 4)}")
    print(f"  tercil BAIXO do proxy: pnl medio R${num_br(r.tercil_baixo_media)} | "
          f"tercil ALTO: R${num_br(r.tercil_alto_media)} | "
          f"diferenca (alto-baixo) = R${num_br(r.diff_tercil)} | p bicaudal = {num_br(r.diff_tercil_p, 4)}")


# ---------------------------------------------------------------------------
# Parte B -- rejeicao CORRELACIONADA com o proxy vencedor
# ---------------------------------------------------------------------------

def sweep_correlacionado(pnls: np.ndarray, proxy: np.ndarray, grade: tuple[float, ...] = GRADE_P,
                          n_sementes: int = N_SEMENTES, seed_base: int = 10_000) -> list[LinhaSweep]:
    """Mesmo espirito de `sweep_iid`, mas a probabilidade de REJEICAO de
    cada trade cresce com o RANK do proxy (maior proxy = mais disputado =
    menos provavel ser o primeiro da fila, exatamente o mecanismo que o
    dono descreveu) em vez de ser uniforme -- ainda ASSIM um sorteio
    aleatorio por trade (`u_i ~ Uniform(0,1)`, nunca olha `pnls[i]`), so'
    que a PROBABILIDADE do sorteio varia por trade. `slope` usa o maximo
    linear que mantem `p_rejeicao` dentro de [0,1] para qualquer rank
    (`2*min(q, 1-q)`) -- o cenario mais forte/adversarial que a missao
    permite testar em vez de um efeito diluido que so' interpolaria para o
    resultado da Parte A."""
    n = len(pnls)
    # mid-rank em (0,1): (posicao + 0,5) / n, maior proxy = maior rank.
    ordem = np.argsort(proxy)
    rank = np.empty(n)
    rank[ordem] = (np.arange(n) + 0.5) / n

    linhas = []
    for p in grade:
        q = 1.0 - p
        slope = 2.0 * min(q, 1.0 - q)
        p_rejeicao = np.clip(q + slope * (rank - 0.5), 0.0, 1.0)
        liquidos = np.empty(n_sementes)
        n_aceitos = np.empty(n_sementes)
        for s in range(n_sementes):
            rng = np.random.default_rng(seed_base + s)
            u = rng.random(n)
            aceita = u >= p_rejeicao  # sorteio POR TRADE, sem olhar pnls
            liquidos[s] = float(pnls[aceita].sum())
            n_aceitos[s] = int(aceita.sum())
        linhas.append(LinhaSweep(
            p=p, media=float(liquidos.mean()), desvio=float(liquidos.std(ddof=1)),
            minimo=float(liquidos.min()), maximo=float(liquidos.max()),
            trades_medio=float(n_aceitos.mean()),
        ))
    return linhas


def imprime_comparacao(iid: list[LinhaSweep], corr: list[LinhaSweep], nome_proxy: str) -> None:
    print(f"\n=== comparacao: rejeicao i.i.d. vs CORRELACIONADA ({nome_proxy}), mesmo p medio ===")
    print(f"{'p':>6} | {'liquido i.i.d.':>16} | {'liquido correl.':>16} | {'diferenca':>14} | pior que i.i.d.?")
    print("-" * 92)
    for a, b in zip(iid, corr):
        assert abs(a.p - b.p) < 1e-9
        diff = b.media - a.media
        pior = "SIM" if diff < 0 else "nao"
        print(f"{num_br(a.p * 100, 0):>5}% | R${num_br(a.media):>13} | R${num_br(b.media):>13} | "
              f"R${num_br(diff):>11} | {pior}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    dias, tick_bars = carregar_tick_bars()
    cfg = montar_config()
    headline = rodar(tick_bars, cfg)
    trades = list(headline.trades)
    pnls = np.array([t.pnl_brl for t in trades])
    liquido_100 = float(pnls.sum())
    print(f"[rejection_lab] headline (tick, atrito zero de fila): {len(trades)} trades, "
          f"{len(dias)} pregoes, liquido = R${num_br(liquido_100)} "
          f"(esperado ~R$11.233,50 pelo relato da rodada anterior)")

    # ---------------- Parte A ----------------
    linhas_a = sweep_iid(pnls)
    imprime_sweep("PARTE A -- rejeicao i.i.d. (sorteio por trade, sem olhar o P&L)", linhas_a)
    escala_linear = all(
        abs(ln.media - liquido_100 * ln.p) <= 3.0 * (ln.desvio if ln.desvio > 0 else 1.0)
        for ln in linhas_a
    )
    print(f"\nliquido medio escala ~linear com p (dentro de 3 desvios-padrao de p*liquido(100%) "
          f"em TODOS os pontos da grade)? {escala_linear}")
    print(f"permanece positivo em toda a grade testada (10%..100%)? "
          f"{all(ln.media > 0 for ln in linhas_a)}")

    # ---------------- Parte B: proxies ----------------
    proxies, sem_match = computa_proxies(trades, tick_bars)
    print(f"\n[rejection_lab] proxies calculados para {len(proxies)}/{len(trades)} trades "
          f"({sem_match} sem tick correspondente encontrado -- deveria ser 0)")
    validos_vel = [pt for pt in proxies if pt.velocidade_valida]
    print(f"[rejection_lab] {len(validos_vel)}/{len(proxies)} trades com janela de "
          f"{JANELA_PROXY_S}s valida (>= {MIN_TICKS_VELOCIDADE} ticks) para o proxy de velocidade")

    pnl_arr = np.array([pt.pnl_brl for pt in proxies])
    gap_arr = np.array([pt.gap_ticks for pt in proxies])
    crowd_count_arr = np.array([pt.crowd_count for pt in proxies], dtype=np.float64)
    crowd_vol_arr = np.array([pt.crowd_volume for pt in proxies])
    vel_arr = np.array([pt.velocidade for pt in validos_vel])
    pnl_vel_arr = np.array([pt.pnl_brl for pt in validos_vel])

    print("\n=== PARTE B -- correlacao proxy <-> P&L do trade (permutacao, n_perm=5000) ===")
    r_gap = testa_proxy("gap-through (ticks alem do nivel no toque)", gap_arr, pnl_arr, seed=1)
    r_crowd_n = testa_proxy("crowding (contagem de negocios no nivel, pre-toque)", crowd_count_arr, pnl_arr, seed=2)
    r_crowd_v = testa_proxy("crowding (volume no nivel, pre-toque)", crowd_vol_arr, pnl_arr, seed=3)
    r_vel = testa_proxy(f"velocidade de aproximacao (ticks/{JANELA_PROXY_S}s, direcao do toque)",
                         vel_arr, pnl_vel_arr, seed=4)
    for r in (r_gap, r_crowd_n, r_crowd_v, r_vel):
        imprime_correlacao(r)

    # split-half (reprodutibilidade): mesma correlacao, so' na 1a/2a metade
    # CRONOLOGICA dos trades -- exige o MESMO sinal E p<0,10 nas duas
    # metades pra contar como "reproduzivel" (nao so' significativo no pool
    # inteiro, que pode ser dominado por um sub-periodo).
    def _split_half(x: np.ndarray, y: np.ndarray, seed: int) -> tuple[float, float, float, float]:
        meio = len(x) // 2
        p1, _ = _permuta_correlacao(x[:meio], y[:meio], 3000, seed)
        p2, _ = _permuta_correlacao(x[meio:], y[meio:], 3000, seed + 1)
        c1 = pearson_corr(x[:meio], y[:meio])
        c2 = pearson_corr(x[meio:], y[meio:])
        return c1, c2, p1, p2

    print("\n--- split-half (reprodutibilidade): correlacao na 1a vs 2a metade cronologica ---")
    candidatos = {
        "gap-through": (gap_arr, pnl_arr, r_gap),
        "crowding (contagem)": (crowd_count_arr, pnl_arr, r_crowd_n),
        "crowding (volume)": (crowd_vol_arr, pnl_arr, r_crowd_v),
        "velocidade": (vel_arr, pnl_vel_arr, r_vel),
    }
    reproduziveis: list[tuple[str, np.ndarray, np.ndarray]] = []
    for nome, (x, y, r) in candidatos.items():
        c1, c2, perc1, perc2 = _split_half(x, y, seed=100)
        mesmo_sinal = (c1 > 0) == (c2 > 0) == (r.corr_real > 0)
        # p bicaudal aproximado a partir do percentil (simetrico): distancia
        # a borda mais proxima, dobrada.
        p1_aprox = min(2 * min(perc1, 100 - perc1) / 100.0, 1.0)
        p2_aprox = min(2 * min(perc2, 100 - perc2) / 100.0, 1.0)
        ok = mesmo_sinal and r.p_two_sided < 0.05 and p1_aprox < 0.10 and p2_aprox < 0.10
        print(f"  {nome}: 1a metade corr={num_br(c1, 4)} (p~{num_br(p1_aprox, 3)}), "
              f"2a metade corr={num_br(c2, 4)} (p~{num_br(p2_aprox, 3)}), "
              f"pool p={num_br(r.p_two_sided, 4)} -- reproduzivel E significativo? {ok}")
        if ok:
            reproduziveis.append((nome, x, y))

    if not reproduziveis:
        print("\n=== VEREDITO PARTE B ===")
        print("nenhum proxy testado (gap-through, crowding-contagem, crowding-volume, velocidade) "
              "mostrou correlacao significativa E reproduzivel (split-half) com o P&L do trade. "
              "Nao ha' evidencia de adverse selection MENSURAVEL com o dado disponivel -- reportado "
              "honestamente como risco NAO-mensuravel (mesma lacuna ja registrada: taxa de fill "
              "passivo real nunca foi medida ao vivo para este candidato), sem forcar um modelo "
              "de rejeicao correlacionada em cima de ruido.")
    else:
        for nome, x, y in reproduziveis:
            linhas_corr = sweep_correlacionado(y, x)
            linhas_iid_mesma_base = sweep_iid(y)  # MESMA base de trades (y), p/ comparacao justa
            imprime_comparacao(linhas_iid_mesma_base, linhas_corr, nome)


if __name__ == "__main__":
    main()
