"""Modelo de REJEICAO PROBABILISTICA de ordem parada (pedido do dono,
2026-08-27), aplicado aos candidatos da familia `copa` (WIN@ e WDO@) --
MESMA metodologia ja rodada em `wdo_grid_reload_f1_tick_rejection_lab.py`
para a familia WDO grid-maker, replicada aqui em vez de reinventada.

## Por que este teste NAO reabre a linha Copa

A linha `copa` (WIN@ + WDO@, `strategy/daytrade/lab/copa*.py`) foi ENCERRADA
em 2026-08-26 por 6 motivos INDEPENDENTES, nenhum deles sobre fila/
preenchimento: previsao de direcao nao bate o acaso (80,8% de acerto por
barra virou 35% de trade lucrativo), MFE=MAE simetrico (sem assimetria pra
gestao colher), e a confirmacao final em OOS cego FALHOU. O modelo de
atrito de FILA (pedagio fixo de 1 tick/perna maker, portao G7) e' so' UM
angulo ja medido, e nao foi ele que reprovou o portao. Este arquivo so'
responde "o modelo antigo de fila era conservador demais?" -- mesmo que a
resposta seja sim, isso NAO reabre a linha: os outros motivos de fechamento
continuam de pe' e sao ortogonais a este.

## Modo de entrada do candidato WIN@ (achado, nao suposicao)

`CopaWin._entrada` aceita `entrada_maker=True/False` (mercado vs reteste
parado). `run_copa_score.CALIBRACAO_IS["WIN@"]` -- a calibracao MEDIDA que
passou pela pesquisa (540 combinacoes da grade "borda", 2026-08-26) -- tem
`entrada_maker=True`. Ou seja, o candidato final da Copa entra por RETESTE,
nao a mercado: tem risco de fila real na entrada (E' o que este arquivo
mede), nao so' na saida.

## Adaptacao de resolucao: M1, nao tick

`wdo_grid_reload_f1_tick_rejection_lab.py` usou tick cru pros proxies da
Parte B (gap/crowding/velocidade negocio a negocio). A familia `copa`
inteira e' M1 (`feed_kind = "m1"` nas duas classes) e a pesquisa original
(`copa_lab.py`/`sweep_copa.py`/`run_copa_score.py`) nunca carregou tick --
reproduzir aqui exigiria um pipeline de dado novo, que a missao desta
rodada probe explicitamente. Os proxies saem por isso da PROPRIA barra M1
de preenchimento e das barras anteriores (nunca do resultado do trade):
mais grosseiro que tick, mas na MESMA resolucao que toda a pesquisa Copa
usou pra escolher o candidato.

Parte A: sorteio i.i.d. por trade sobre a lista JA computada por
`copa_lab.rodar` -- preenchimento otimista padrao do motor (toda
`EnterLimit` que TOCA o nivel, sujeita a `limit_fill_capped_by_volume=True`,
default do repo desde 2026-08-23, vira fill). Parte B: proxy de "quao
disputado" a partir da barra de preenchimento (gap-through: quanto ela foi
ALEM do nivel; volume da barra de toque e das anteriores; velocidade de
aproximacao) -- so' dado disponivel ANTES/NO instante do toque.

Uso: `python -u scripts/daytrade/copa_rejection_lab.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
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

import copa_lab as L  # noqa: E402
from run_copa_score import CALIBRACAO_IS  # noqa: E402

#: Grade de taxa de aceitacao -- identica a' rodada anterior (WDO grid-maker).
GRADE_P = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)
N_SEMENTES = 30

#: Janela de lookback em BARRAS M1 (nao segundos -- ver a nota de resolucao
#: no cabecalho) para os proxies de velocidade/volume pre-toque. 5 e' o
#: primario; 10 roda na auto-revisao (robustez).
JANELA_PROXY_BARRAS = 5
JANELA_PROXY_BARRAS_ROBUSTEZ = 10
MIN_BARRAS_VELOCIDADE = 3


# ---------------------------------------------------------------------------
# Parte A -- rejeicao i.i.d. (identica a' rodada anterior, generica em pnls)
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
    do P&L de cada um -- a decisao de aceitar nunca olha `pnls[i]`)."""
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
# Parte B -- proxies de "quao disputado" a partir da BARRA M1 de toque
# ---------------------------------------------------------------------------

@dataclass
class ProxyTrade:
    pnl_brl: float
    gap_ticks: float          # 0 = toque no nivel exato; >0 = barra foi ALEM
    velocidade: float         # movimento (ticks) na direcao do toque, N barras antes
    velocidade_valida: bool
    volume_toque: float       # volume da PROPRIA barra de preenchimento
    volume_janela: float      # volume medio das N barras ANTES do toque


def _volume_bar(bars: pd.DataFrame) -> np.ndarray:
    """Mesma regra de `backtest.intraday.engine._bar_volume`: `real_volume`
    quando reportado (>0), senao `tick_volume` -- vetorizado em vez de
    linha a linha (a barra de preenchimento e' consultada por milhares de
    trades, um loop Python por linha custaria caro sem necessidade)."""
    real = bars["real_volume"].to_numpy(dtype=np.float64)
    tickv = bars["tick_volume"].to_numpy(dtype=np.float64)
    return np.where(real > 0, real, tickv)


def computa_proxies(trades: list[IntradayTrade], bars: pd.DataFrame, tick_size: float,
                     janela_barras: int = JANELA_PROXY_BARRAS) -> tuple[list[ProxyTrade], int]:
    """Um `ProxyTrade` por `IntradayTrade`, calculado SO' com a barra do
    proprio toque (permitido pela missao -- dado disponivel NO instante em
    que a decisao de aceitar/rejeitar teria que ser tomada) e barras
    ANTERIORES. Devolve tambem a contagem de trades sem barra correspondente
    (deveria ser 0 -- todo `entry_ts` de trade veio de uma linha de `bars`)."""
    idx = bars.index
    lows = bars["low"].to_numpy(dtype=np.float64)
    highs = bars["high"].to_numpy(dtype=np.float64)
    closes = bars["close"].to_numpy(dtype=np.float64)
    volumes = _volume_bar(bars)

    posicoes = idx.get_indexer(pd.to_datetime([pd.Timestamp(t.entry_ts) for t in trades]))
    out: list[ProxyTrade] = []
    sem_match = 0
    for t, pos in zip(trades, posicoes):
        if pos < 0:
            sem_match += 1
            continue
        if t.side == "long":
            # preenchimento e' sempre no NIVEL exato (`order.limit_price`,
            # ver `machine._resolve_limit_fills`) -- o gap so' aparece
            # comparando contra o LOW/HIGH cru da barra, nunca contra o
            # proprio preco de entrada do trade.
            gap = max(0.0, (t.entry_price - lows[pos]) / tick_size)
        else:
            gap = max(0.0, (highs[pos] - t.entry_price) / tick_size)

        inicio = max(0, pos - janela_barras)
        janela_close = closes[inicio:pos]     # exclui a propria barra de toque
        janela_vol = volumes[inicio:pos]
        if len(janela_close) >= MIN_BARRAS_VELOCIDADE:
            if t.side == "long":
                vel = (janela_close[0] - janela_close[-1]) / tick_size
            else:
                vel = (janela_close[-1] - janela_close[0]) / tick_size
            vel_valida = True
        else:
            vel = 0.0
            vel_valida = False
        vol_janela = float(janela_vol.mean()) if len(janela_vol) else 0.0

        out.append(ProxyTrade(
            pnl_brl=t.pnl_brl, gap_ticks=gap, velocidade=vel, velocidade_valida=vel_valida,
            volume_toque=float(volumes[pos]), volume_janela=vol_janela,
        ))
    return out, sem_match


# ---------------------------------------------------------------------------
# correlacao + teste de permutacao (proxy <-> pnl do trade) -- identico a'
# rodada anterior, generico em (x, y)
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


def _split_half(x: np.ndarray, y: np.ndarray, seed: int) -> tuple[float, float, float, float]:
    meio = len(x) // 2
    p1, _ = _permuta_correlacao(x[:meio], y[:meio], 3000, seed)
    p2, _ = _permuta_correlacao(x[meio:], y[meio:], 3000, seed + 1)
    c1 = pearson_corr(x[:meio], y[:meio])
    c2 = pearson_corr(x[meio:], y[meio:])
    return c1, c2, p1, p2


def proxies_reproduziveis(candidatos: dict[str, tuple[np.ndarray, np.ndarray, ResultadoCorrelacao]]) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """Exige MESMO sinal E p<0,05 no pool inteiro E p<0,10 nas DUAS metades
    cronologicas -- nao so' significativo no pool, que pode ser dominado por
    um sub-periodo (mesma armadilha ja documentada: um proxy com p=0,04 se
    revelou artefato de 4 trades em 2.773 numa rodada anterior)."""
    print("\n--- split-half (reprodutibilidade): correlacao na 1a vs 2a metade cronologica ---")
    reproduziveis: list[tuple[str, np.ndarray, np.ndarray]] = []
    for nome, (x, y, r) in candidatos.items():
        c1, c2, perc1, perc2 = _split_half(x, y, seed=100)
        mesmo_sinal = (c1 > 0) == (c2 > 0) == (r.corr_real > 0)
        p1_aprox = min(2 * min(perc1, 100 - perc1) / 100.0, 1.0)
        p2_aprox = min(2 * min(perc2, 100 - perc2) / 100.0, 1.0)
        ok = mesmo_sinal and r.p_two_sided < 0.05 and p1_aprox < 0.10 and p2_aprox < 0.10
        print(f"  {nome}: 1a metade corr={num_br(c1, 4)} (p~{num_br(p1_aprox, 3)}), "
              f"2a metade corr={num_br(c2, 4)} (p~{num_br(p2_aprox, 3)}), "
              f"pool p={num_br(r.p_two_sided, 4)}, n={r.n} -- reproduzivel E significativo? {ok}")
        if ok:
            reproduziveis.append((nome, x, y))
    return reproduziveis


# ---------------------------------------------------------------------------
# Parte B -- rejeicao CORRELACIONADA com o proxy vencedor (so' se houver um)
# ---------------------------------------------------------------------------

def sweep_correlacionado(pnls: np.ndarray, proxy: np.ndarray, grade: tuple[float, ...] = GRADE_P,
                          n_sementes: int = N_SEMENTES, seed_base: int = 10_000) -> list[LinhaSweep]:
    n = len(pnls)
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
# por simbolo
# ---------------------------------------------------------------------------

def relata_modo_entrada_win() -> None:
    print("=== 0. modo de entrada do candidato WIN@ (achado da pesquisa, nao suposicao) ===")
    p = CALIBRACAO_IS["WIN@"]
    print(f"entrada_maker na CALIBRACAO_IS de run_copa_score.py = {p['entrada_maker']!r}")
    if p["entrada_maker"]:
        print("MAKER (EnterLimit, reteste): pernas_maker=2 (entrada + alvo). "
              "Risco de fila real na entrada -- Parte A + Parte B rodam abaixo.")
    else:
        print("MERCADO (Enter): sem risco de fila na entrada (o risco dela e' "
              "slippage, ja no custo, nao rejeicao). Parte A/B da entrada nao "
              "fazem sentido e NAO sao forcadas.")


def roda_simbolo(symbol: str) -> None:
    params = dict(CALIBRACAO_IS[symbol])
    teto = L.TETO_DE_TESTE[symbol]
    ins = L.barras(symbol).in_sample()
    rodada = L.rodar(symbol, ins, teto, f"{symbol} candidato IS", **params)
    trades = list(rodada.resultado.trades)
    pnls = np.array([t.pnl_brl for t in trades])
    liquido = float(pnls.sum())
    tick_size = L.config(symbol, teto).costs.tick_size

    print(f"\n{'=' * 100}\n{symbol} -- candidato: {params}\n{'=' * 100}")
    print(f"IS ({L.descreve_janela(ins)}), teto {teto} contratos: {len(trades)} trades, "
          f"liquido = R${num_br(liquido)}")
    if not trades:
        print(f"[{symbol}] zero trades no IS -- nada a rejeitar, encerra aqui.")
        return

    # ---------------- Parte A ----------------
    linhas_a = sweep_iid(pnls)
    imprime_sweep(f"{symbol} -- PARTE A (rejeicao i.i.d., sorteio por trade, sem olhar o P&L)", linhas_a)
    escala_linear = all(
        abs(ln.media - liquido * ln.p) <= 3.0 * (ln.desvio if ln.desvio > 0 else 1.0)
        for ln in linhas_a
    )
    print(f"\nliquido medio escala ~linear com p (dentro de 3 desvios-padrao de p*liquido(100%) "
          f"em TODOS os pontos da grade)? {escala_linear}")
    print(f"permanece positivo em toda a grade testada (10%..100%)? "
          f"{all(ln.media > 0 for ln in linhas_a)}")

    # ---------------- Parte B: proxies ----------------
    proxies, sem_match = computa_proxies(trades, ins, tick_size)
    print(f"\n[{symbol}] proxies calculados para {len(proxies)}/{len(trades)} trades "
          f"({sem_match} sem barra correspondente encontrada -- deveria ser 0)")
    validos_vel = [pt for pt in proxies if pt.velocidade_valida]
    print(f"[{symbol}] {len(validos_vel)}/{len(proxies)} trades com janela de "
          f"{JANELA_PROXY_BARRAS} barras valida (>= {MIN_BARRAS_VELOCIDADE}) para o proxy de velocidade")

    pnl_arr = np.array([pt.pnl_brl for pt in proxies])
    gap_arr = np.array([pt.gap_ticks for pt in proxies])
    vol_toque_arr = np.array([pt.volume_toque for pt in proxies])
    vol_janela_arr = np.array([pt.volume_janela for pt in proxies])
    vel_arr = np.array([pt.velocidade for pt in validos_vel])
    pnl_vel_arr = np.array([pt.pnl_brl for pt in validos_vel])

    print(f"\n=== {symbol} -- PARTE B: correlacao proxy <-> P&L do trade (permutacao, n_perm=5000) ===")
    r_gap = testa_proxy("gap-through (ticks alem do nivel na barra de toque)", gap_arr, pnl_arr, seed=1)
    r_vol_toque = testa_proxy("volume da barra de toque", vol_toque_arr, pnl_arr, seed=2)
    r_vol_janela = testa_proxy(f"volume medio das {JANELA_PROXY_BARRAS} barras pre-toque", vol_janela_arr, pnl_arr, seed=3)
    r_vel = testa_proxy(f"velocidade de aproximacao ({JANELA_PROXY_BARRAS} barras, direcao do toque)",
                         vel_arr, pnl_vel_arr, seed=4)
    for r in (r_gap, r_vol_toque, r_vol_janela, r_vel):
        imprime_correlacao(r)

    candidatos = {
        "gap-through": (gap_arr, pnl_arr, r_gap),
        "volume (barra de toque)": (vol_toque_arr, pnl_arr, r_vol_toque),
        "volume (janela pre-toque)": (vol_janela_arr, pnl_arr, r_vol_janela),
        "velocidade": (vel_arr, pnl_vel_arr, r_vel),
    }
    reproduziveis = proxies_reproduziveis(candidatos)

    if not reproduziveis:
        print(f"\n=== {symbol} -- VEREDITO PARTE B ===")
        print("nenhum proxy testado (gap-through, volume-toque, volume-janela, velocidade) "
              "mostrou correlacao significativa E reproduzivel (split-half) com o P&L do trade. "
              "Sem evidencia de adverse selection MENSURAVEL no dado M1 disponivel -- reportado "
              "honestamente como risco NAO-mensuravel nesta resolucao, sem forcar um modelo de "
              "rejeicao correlacionada em cima de ruido.")
    else:
        for nome, x, y in reproduziveis:
            linhas_corr = sweep_correlacionado(y, x)
            linhas_iid_mesma_base = sweep_iid(y)  # MESMA base de trades (y), comparacao justa
            imprime_comparacao(linhas_iid_mesma_base, linhas_corr, nome)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    relata_modo_entrada_win()
    for symbol in ("WIN@", "WDO@"):
        roda_simbolo(symbol)


if __name__ == "__main__":
    main()
