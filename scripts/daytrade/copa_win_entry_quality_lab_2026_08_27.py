"""Qualidade de SINAL de ENTRADA da `CopaWin` (WIN@) -- 2026-08-27.

Pergunta do dono: quais CARACTERISTICAS DE ENTRADA (disponiveis no instante
do toque, sem olhar o resultado do trade) distinguem trade vencedor de
perdedor -- o suficiente para servir de FILTRO e reduzir ruido/operar mais
seguro? Usa o trade log N=1 (1.086 trades, IN-SAMPLE, estatico) produzido por
`capital_ladder_copawin_2026_08_27.py` e as MESMAS barras M1 do IS
(`copa_lab.barras("WIN@").in_sample()`, 72.730 barras, 129 pregoes,
2025-12-01 -> 2026-06-12) -- OOS_CUTOFF=2026-06-13 nunca tocado, `.unlock()`
nunca chamado.

## Reuso deliberado do padrao de `copa_rejection_lab.py`

Este arquivo NAO reescreve a logica de correlacao/permutacao/reproducibilidade
-- importa direto de `copa_rejection_lab.py`: `testa_proxy` (Pearson +
permutacao bicaudal + diferenca por tercil), `proxies_reproduziveis` (gate:
MESMO sinal E p<0,05 no pool E p<0,10 em CADA metade cronologica) e
`_split_half` (usado aqui so' para preencher a tabela cheia com os 4 numeros
por metade -- `proxies_reproduziveis` ja usa a mesma funcao internamente para
decidir, entao nao ha duplicacao de CRITERIO, so' de LEITURA dos numeros que
ele ja calculou para poder reporta-los).

Diferenca de escopo vs `copa_rejection_lab.py`: aquele arquivo pergunta "o
preenchimento foi disputado?" (gap-through/volume/velocidade da barra de
TOQUE, sob a lente de adverse selection de fila). Este pergunta "o SETUP em
si era bom?" -- hora do pregao, momentum de TENDENCIA (nao de aproximacao ao
nivel), distancia a referencias de preco (abertura do dia, media movel
curta) e regime de volatilidade (curto vs longo). Onde os dois tocam o mesmo
dado bruto (volume da barra de toque, volume da janela pre-toque), os
resultados podem legitimamente divergir do relatorio anterior porque a
pergunta e' outra.

## Entrada e' RETESTE (`entrada_maker=True`) -- o que isso implica nas features

`CALIBRACAO_IS["WIN@"]` tem `entrada_maker=True`: o robo arma uma ordem
PARADA no nivel rompido e so' preenche quando o preco VOLTA la' (reteste).
Duas consequencias diretas no desenho das features:

1. `entry_price` do trade log JA E' o nivel rompido (arredondado ao tick) --
   "distancia ao nivel rompido" seria ~0 por construcao e NAO entra como
   feature (diferente de `copa_rejection_lab.gap_ticks`, que mede o TOQUE
   contra o low/high da barra, nao contra o nivel). Em vez disso, as
   distancias usadas aqui sao a referencias INDEPENDENTES do nivel:
   abertura do pregao e media movel curta.
2. O `entry_ts` e' o instante do TOQUE (fill), que pode vir varias barras
   DEPOIS do rompimento original (ate' `entrada_ttl_barras=15` barras) -- as
   janelas de momentum/volume/volatilidade abaixo sao medidas ANTES do toque
   (nunca incluem a barra de fill), exatamente como `copa_rejection_lab.
   computa_proxies`.

## Correcao deliberada sobre `copa_rejection_lab.computa_proxies`: fronteira de pregao

As janelas de lookback aqui NUNCA atravessam a virada do pregao (clampadas
em `dia_inicio_pos`) -- `copa_win.py::on_session_start` zera a faixa/estado
do robo a cada pregao ("nenhum indicador de NIVEL de preco atravessa a
virada"), entao um momentum/volatilidade que vazasse para o fechamento do
pregao anterior mediria uma coisa que o proprio robo nunca ve. `copa_
rejection_lab.computa_proxies` nao faz esse clamp (janela so' e' limitada por
`max(0, pos-janela)`, sem checar a data) -- pontualmente diferente aqui de
proposito, nao por descuido.

## Convencao de sinal: MOMENTUM DE TENDENCIA, nao velocidade de aproximacao

`copa_rejection_lab.ProxyTrade.velocidade` mede "quao rapido o preco se
aproximou do nivel" (positivo = preco correndo NA DIRECAO do toque, o que
para uma ordem de RETESTE compradora e' o preco CAINDO de volta ate' o
nivel -- ou seja, positivo la' e' o preco indo CONTRA a tendencia da entrada).
Aqui o `momentum_tendencia_ticks` mede o oposto conceitualmente: quanto o
preco already andou NA DIRECAO DO TRADE (positivo = tendencia a favor da
entrada) nas `K` barras anteriores ao toque. Mesma barra bruta, pergunta
diferente -- documentado aqui para nao virar uma "contradicao" com o
relatorio anterior quando na verdade sao duas leituras de sinais diferentes
do mesmo movimento de preco.

## Limiar do filtro: fronteira do tercil, calibrada so' na METADE 1 -- NAO e' busca em grade

Para toda feature que sobrevive ao gate de reproducibilidade, o limiar do
filtro e' a MESMA fronteira que `testa_proxy` ja usa para o teste de
diferenca por tercil (33/67 percentil), computada SO' na metade cronologica
1 do subconjunto valido para aquela feature. Direcao do filtro segue o sinal
da correlacao no POOL (jah exigido pelo gate: mesmo sinal em ambas as
metades): correlacao positiva -> descarta o tercio de BAIXO ('so' entra se
feature >= p33(metade1)'); negativa -> descarta o tercio de CIMA ('so' entra
se feature <= p67(metade1)'). E' um limiar PRE-DEFINIDO pela propria
metodologia de teste, nunca uma otimizacao de grade sobre o P&L -- a mesma
razao pela qual `proxies_reproduziveis` exige robustez split-half em vez de
so' olhar o pool.

## Universo do teste "com/sem filtro": so' os trades com a feature DEFINIDA

Trades sem janela minima disponivel (perto do inicio do pregao, mesmo apos o
aquecimento de 45 barras) ficam de fora do teste de aquela feature -- ficariam
de fora dos dois lados (com e sem filtro) para a comparacao ser justa (nao
misturar "faltou dado" com "reprovou o filtro"). Cada feature pode ter um n
valido diferente; reportado explicitamente na tabela.

Uso: `python -u scripts/daytrade/copa_win_entry_quality_lab_2026_08_27.py`
"""
from __future__ import annotations

import csv
import dataclasses
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

from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402

import copa_lab as L  # noqa: E402
from copa_rejection_lab import (  # noqa: E402
    ResultadoCorrelacao,
    _split_half,
    proxies_reproduziveis,
    testa_proxy,
)

SYMBOL = "WIN@"
TRADE_LOG_CSV = ROOT / "scripts" / "daytrade" / "capital_ladder_copawin_n1_trades_2026_08_27.csv"
FEATURES_CSV_OUT = ROOT / "scripts" / "daytrade" / "copa_win_entry_quality_features_2026_08_27.csv"
RESULTADOS_CSV_OUT = ROOT / "scripts" / "daytrade" / "copa_win_entry_quality_resultados_2026_08_27.csv"
FILTROS_CSV_OUT = ROOT / "scripts" / "daytrade" / "copa_win_entry_quality_filtros_2026_08_27.csv"

#: Janelas em BARRAS M1 (nunca atravessam a virada do pregao -- ver docstring
#: do modulo). CURTA casa com `janela_rompimento=10` da propria `CopaWin`
#: (CALIBRACAO_IS); LONGA e' 6x isso (~1h) para dar um baseline de regime
#: genuinamente diferente da janela curta; SMA fica no meio (2x a curta).
JANELA_CURTA = 10
JANELA_LONGA = 60
JANELA_SMA = 20
MIN_BARRAS_CURTA = 5
MIN_BARRAS_LONGA = 20
MIN_BARRAS_SMA = 10


# ---------------------------------------------------------------------------
# trade log -- le' o CSV da etapa anterior (nao reroda o motor)
# ---------------------------------------------------------------------------

def carrega_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["entry_ts", "exit_ts"])
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    df = df.sort_values("entry_ts").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# posicao de cada bar dentro do proprio pregao (para clampar as janelas na
# virada) + preco de abertura do pregao, broadcastado por bar
# ---------------------------------------------------------------------------

def _dia_inicio_pos(bars: pd.DataFrame) -> np.ndarray:
    datas = np.asarray(bars.index.date)
    troca = np.concatenate(([True], datas[1:] != datas[:-1]))
    dia_id = np.cumsum(troca) - 1
    primeiras_pos = np.where(troca)[0]
    return primeiras_pos[dia_id]


def _volume_bar(bars: pd.DataFrame) -> np.ndarray:
    """Mesma regra de `backtest.intraday.engine._bar_volume` e de
    `copa_rejection_lab._volume_bar`: `real_volume` quando reportado (>0),
    senao `tick_volume`."""
    real = bars["real_volume"].to_numpy(dtype=np.float64)
    tickv = bars["tick_volume"].to_numpy(dtype=np.float64)
    return np.where(real > 0, real, tickv)


# ---------------------------------------------------------------------------
# uma linha de features por trade (NaN onde a janela minima nao esta
# disponivel -- filtrado por feature na hora do teste, nunca imputado)
# ---------------------------------------------------------------------------

@dataclass
class LinhaFeatures:
    entry_ts: pd.Timestamp
    pnl_brl: float
    hora_pregao_min: float
    momentum_tendencia_ticks: float
    volume_toque: float
    volume_janela_pretoque: float
    dist_abertura_ticks: float
    dist_sma_curta_ticks: float
    vol_regime_curto_ticks: float
    vol_regime_longo_ticks: float
    vol_expansao_razao: float


def computa_features(trades: pd.DataFrame, bars: pd.DataFrame, tick_size: float) -> tuple[list[LinhaFeatures], int]:
    idx = bars.index
    opens = bars["open"].to_numpy(dtype=np.float64)
    highs = bars["high"].to_numpy(dtype=np.float64)
    lows = bars["low"].to_numpy(dtype=np.float64)
    closes = bars["close"].to_numpy(dtype=np.float64)
    volumes = _volume_bar(bars)
    dia_inicio_pos = _dia_inicio_pos(bars)
    barra_do_dia = np.arange(len(bars)) - dia_inicio_pos
    abertura_por_bar = opens[dia_inicio_pos]

    posicoes = idx.get_indexer(pd.to_datetime(trades["entry_ts"], utc=True))

    out: list[LinhaFeatures] = []
    sem_match = 0
    for row, pos in zip(trades.itertuples(index=False), posicoes):
        if pos < 0:
            sem_match += 1
            continue
        side = row.side
        entry_price = float(row.entry_price)
        dia_ini = dia_inicio_pos[pos]

        # ---- hora do pregao (posicao do bar de TOQUE dentro do pregao) ----
        hora_min = float(barra_do_dia[pos])

        # ---- momentum de TENDENCIA, janela curta, clampado no pregao ----
        ini_c = max(dia_ini, pos - JANELA_CURTA)
        fechos_c = closes[ini_c:pos]
        if len(fechos_c) >= MIN_BARRAS_CURTA:
            if side == "long":
                momentum = (fechos_c[-1] - fechos_c[0]) / tick_size
            else:
                momentum = (fechos_c[0] - fechos_c[-1]) / tick_size
        else:
            momentum = np.nan

        # ---- volume no toque e na janela curta pre-toque (mesma janela) ----
        vol_toque = float(volumes[pos])
        vol_janela = float(volumes[ini_c:pos].mean()) if len(fechos_c) >= MIN_BARRAS_CURTA else np.nan

        # ---- distancia a' abertura do pregao ----
        abertura = abertura_por_bar[pos]
        if side == "long":
            dist_abertura = (entry_price - abertura) / tick_size
        else:
            dist_abertura = (abertura - entry_price) / tick_size

        # ---- distancia a' media movel curta (fechos, janela SMA, clampada) ----
        ini_sma = max(dia_ini, pos - JANELA_SMA)
        fechos_sma = closes[ini_sma:pos]
        if len(fechos_sma) >= MIN_BARRAS_SMA:
            sma = float(fechos_sma.mean())
            if side == "long":
                dist_sma = (entry_price - sma) / tick_size
            else:
                dist_sma = (sma - entry_price) / tick_size
        else:
            dist_sma = np.nan

        # ---- regime de volatilidade: range medio curto vs longo ----
        range_c = highs[ini_c:pos] - lows[ini_c:pos]
        vol_curto = float(range_c.mean()) / tick_size if len(range_c) >= MIN_BARRAS_CURTA else np.nan

        ini_l = max(dia_ini, pos - JANELA_LONGA)
        range_l = highs[ini_l:pos] - lows[ini_l:pos]
        vol_longo = float(range_l.mean()) / tick_size if len(range_l) >= MIN_BARRAS_LONGA else np.nan

        if not np.isnan(vol_curto) and not np.isnan(vol_longo) and vol_longo > 0:
            vol_expansao = vol_curto / vol_longo
        else:
            vol_expansao = np.nan

        out.append(LinhaFeatures(
            entry_ts=row.entry_ts, pnl_brl=float(row.pnl_brl), hora_pregao_min=hora_min,
            momentum_tendencia_ticks=momentum, volume_toque=vol_toque,
            volume_janela_pretoque=vol_janela, dist_abertura_ticks=dist_abertura,
            dist_sma_curta_ticks=dist_sma, vol_regime_curto_ticks=vol_curto,
            vol_regime_longo_ticks=vol_longo, vol_expansao_razao=vol_expansao,
        ))
    return out, sem_match


def salva_features_csv(linhas: list[LinhaFeatures], path: Path) -> None:
    campos = [f.name for f in dataclasses.fields(LinhaFeatures)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(campos)
        for ln in linhas:
            valores = [getattr(ln, c) for c in campos]
            valores[0] = ln.entry_ts.isoformat()
            w.writerow(valores)


# ---------------------------------------------------------------------------
# avaliacao por feature: reusa testa_proxy + _split_half (mesma logica de
# copa_rejection_lab), so' preenche a tabela cheia com os numeros das 2
# metades para reportar mesmo as que NAO sobrevivem.
# ---------------------------------------------------------------------------

@dataclass
class LinhaResultadoFeature:
    nome: str
    n: int
    corr_pool: float
    p_pool: float
    corr_metade1: float
    p_metade1: float
    corr_metade2: float
    p_metade2: float
    reproduzivel: bool


def _valido(x_full: np.ndarray, y_full: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = ~np.isnan(x_full)
    return x_full[mask], y_full[mask]


def avalia_todas(linhas: list[LinhaFeatures]) -> tuple[dict[str, tuple[np.ndarray, np.ndarray, ResultadoCorrelacao]],
                                                        list[LinhaResultadoFeature]]:
    pnl_full = np.array([ln.pnl_brl for ln in linhas])
    especificacoes = [
        ("hora_pregao_min", np.array([ln.hora_pregao_min for ln in linhas])),
        ("momentum_tendencia_ticks", np.array([ln.momentum_tendencia_ticks for ln in linhas])),
        ("volume_toque", np.array([ln.volume_toque for ln in linhas])),
        ("volume_janela_pretoque", np.array([ln.volume_janela_pretoque for ln in linhas])),
        ("dist_abertura_ticks", np.array([ln.dist_abertura_ticks for ln in linhas])),
        ("dist_sma_curta_ticks", np.array([ln.dist_sma_curta_ticks for ln in linhas])),
        ("vol_regime_curto_ticks", np.array([ln.vol_regime_curto_ticks for ln in linhas])),
        ("vol_regime_longo_ticks", np.array([ln.vol_regime_longo_ticks for ln in linhas])),
        ("vol_expansao_razao", np.array([ln.vol_expansao_razao for ln in linhas])),
    ]

    candidatos: dict[str, tuple[np.ndarray, np.ndarray, ResultadoCorrelacao]] = {}
    for seed, (nome, x_full) in enumerate(especificacoes):
        x, y = _valido(x_full, pnl_full)
        r = testa_proxy(nome, x, y, seed=seed + 1)
        candidatos[nome] = (x, y, r)

    print("\n=== correlacao proxy <-> P&L do trade (permutacao, n_perm=5000), TODAS as features ===")
    for nome, (x, y, r) in candidatos.items():
        print(f"\nproxy: {nome} (n={r.n})")
        print(f"  correlacao de Pearson = {num_br(r.corr_real, 4)} | "
              f"percentil no nulo = {num_br(r.percentil, 1)}% | p bicaudal = {num_br(r.p_two_sided, 4)}")
        print(f"  tercil BAIXO: pnl medio R${num_br(r.tercil_baixo_media)} | "
              f"tercil ALTO: R${num_br(r.tercil_alto_media)} | diff = R${num_br(r.diff_tercil)} | "
              f"p = {num_br(r.diff_tercil_p, 4)}")

    reproduziveis = proxies_reproduziveis(candidatos)
    nomes_reproduziveis = {nome for nome, _, _ in reproduziveis}

    linhas_tabela: list[LinhaResultadoFeature] = []
    for nome, (x, y, r) in candidatos.items():
        c1, c2, p1, p2 = _split_half(x, y, seed=100)
        linhas_tabela.append(LinhaResultadoFeature(
            nome=nome, n=r.n, corr_pool=r.corr_real, p_pool=r.p_two_sided,
            corr_metade1=c1, p_metade1=p1, corr_metade2=c2, p_metade2=p2,
            reproduzivel=nome in nomes_reproduziveis,
        ))
    return candidatos, linhas_tabela


def imprime_tabela_resultados(linhas: list[LinhaResultadoFeature]) -> None:
    print("\n\n=== TABELA CRUA -- TODAS as features testadas (sobreviventes e nao-sobreviventes) ===")
    print(f"{'feature':<28}{'n':>6}{'corr pool':>11}{'p pool':>9}"
          f"{'corr M1':>10}{'p~M1':>8}{'corr M2':>10}{'p~M2':>8}{'reproduzivel':>14}")
    print("-" * 104)
    for ln in linhas:
        print(f"{ln.nome:<28}{ln.n:>6}{num_br(ln.corr_pool, 4):>11}{num_br(ln.p_pool, 4):>9}"
              f"{num_br(ln.corr_metade1, 4):>10}{num_br(ln.p_metade1, 3):>8}"
              f"{num_br(ln.corr_metade2, 4):>10}{num_br(ln.p_metade2, 3):>8}"
              f"{str(ln.reproduzivel):>14}")


def salva_resultados_csv(linhas: list[LinhaResultadoFeature], path: Path) -> None:
    campos = [f.name for f in dataclasses.fields(LinhaResultadoFeature)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(campos)
        for ln in linhas:
            w.writerow([getattr(ln, c) for c in campos])


# ---------------------------------------------------------------------------
# filtro simples: limiar calibrado na METADE 1 (fronteira de tercil, mesma
# usada por testa_proxy), efeito medido na METADE 2 -- so' para features
# reproduziveis.
# ---------------------------------------------------------------------------

@dataclass
class LinhaFiltro:
    nome: str
    direcao_corr: str
    regra: str
    limiar: float
    n_total_m2: int
    n_mantidos_m2: int
    n_descartados_m2: int
    pnl_sem_filtro_m2: float
    pnl_com_filtro_m2: float
    maxdd_sem_filtro_m2: float
    maxdd_com_filtro_m2: float


def simula_filtro(nome: str, x: np.ndarray, y: np.ndarray, corr_pool: float) -> LinhaFiltro:
    """`x`, `y` ja' vem SO' com os trades validos para esta feature, em ordem
    CRONOLOGICA (mesmo subconjunto que passou pelo gate de reproducibilidade
    -- ver docstring do modulo, secao "universo do teste")."""
    meio = len(x) // 2
    x1, x2 = x[:meio], x[meio:]
    y2 = y[meio:]

    if corr_pool > 0:
        limiar = float(np.percentile(x1, 100.0 / 3.0))
        mask2 = x2 >= limiar
        regra = f"entra so' se {nome} >= {num_br(limiar, 4)} (descarta tercio de BAIXO, calibrado na metade 1)"
    else:
        limiar = float(np.percentile(x1, 200.0 / 3.0))
        mask2 = x2 <= limiar
        regra = f"entra so' se {nome} <= {num_br(limiar, 4)} (descarta tercio de CIMA, calibrado na metade 1)"

    curva_sem = np.concatenate(([0.0], np.cumsum(y2)))
    curva_com = np.concatenate(([0.0], np.cumsum(y2[mask2])))

    return LinhaFiltro(
        nome=nome, direcao_corr="positiva" if corr_pool > 0 else "negativa", regra=regra,
        limiar=limiar, n_total_m2=len(y2), n_mantidos_m2=int(mask2.sum()),
        n_descartados_m2=int(len(y2) - mask2.sum()),
        pnl_sem_filtro_m2=float(y2.sum()), pnl_com_filtro_m2=float(y2[mask2].sum()),
        maxdd_sem_filtro_m2=maxdd_brl(pd.Series(curva_sem)),
        maxdd_com_filtro_m2=maxdd_brl(pd.Series(curva_com)),
    )


def imprime_filtro(ln: LinhaFiltro) -> None:
    print(f"\n--- filtro: {ln.nome} (correlacao {ln.direcao_corr} no pool) ---")
    print(f"  regra: {ln.regra}")
    print(f"  metade 2 (fora da calibracao): {ln.n_total_m2} trades validos -> "
          f"{ln.n_mantidos_m2} mantidos, {ln.n_descartados_m2} descartados")
    print(f"  P&L sem filtro: R${num_br(ln.pnl_sem_filtro_m2)} | com filtro: R${num_br(ln.pnl_com_filtro_m2)}")
    print(f"  MaxDD sem filtro: R${num_br(ln.maxdd_sem_filtro_m2)} | com filtro: R${num_br(ln.maxdd_com_filtro_m2)}")


def salva_filtros_csv(linhas: list[LinhaFiltro], path: Path) -> None:
    if not linhas:
        return
    campos = [f.name for f in dataclasses.fields(LinhaFiltro)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(campos)
        for ln in linhas:
            w.writerow([getattr(ln, c) for c in campos])


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    bars = L.barras(SYMBOL).in_sample()
    print(f"[entry_quality] {SYMBOL} IN-SAMPLE: {L.descreve_janela(bars)}")
    print(f"[entry_quality] trade log: {TRADE_LOG_CSV}")

    trades = carrega_trades(TRADE_LOG_CSV)
    print(f"[entry_quality] {len(trades)} trades carregados do CSV "
          f"(liquido = R${num_br(float(trades['pnl_brl'].sum()))})")

    tick_size = L.config(SYMBOL, 1).costs.tick_size
    print(f"[entry_quality] tick_size={tick_size} pontos | janelas: curta={JANELA_CURTA} "
          f"longa={JANELA_LONGA} sma={JANELA_SMA} barras (clampadas na virada do pregao)")

    linhas_features, sem_match = computa_features(trades, bars, tick_size)
    print(f"[entry_quality] features computadas para {len(linhas_features)}/{len(trades)} trades "
          f"({sem_match} sem barra correspondente -- deveria ser 0)")
    salva_features_csv(linhas_features, FEATURES_CSV_OUT)
    print(f"[entry_quality] features por trade salvas em {FEATURES_CSV_OUT}")

    candidatos, tabela = avalia_todas(linhas_features)
    imprime_tabela_resultados(tabela)
    salva_resultados_csv(tabela, RESULTADOS_CSV_OUT)
    print(f"\n[entry_quality] tabela de resultados salva em {RESULTADOS_CSV_OUT}")

    reproduziveis = [ln.nome for ln in tabela if ln.reproduzivel]
    print(f"\n=== features REPRODUZIVEIS (sobreviveram ao gate split-half): {reproduziveis or 'NENHUMA'} ===")

    filtros: list[LinhaFiltro] = []
    if reproduziveis:
        print("\n\n=== EFEITO DO FILTRO -- limiar calibrado na METADE 1, medido na METADE 2 ===")
        for nome in reproduziveis:
            x, y, r = candidatos[nome]
            ln = simula_filtro(nome, x, y, r.corr_real)
            filtros.append(ln)
            imprime_filtro(ln)
        salva_filtros_csv(filtros, FILTROS_CSV_OUT)
        print(f"\n[entry_quality] efeito dos filtros salvo em {FILTROS_CSV_OUT}")
    else:
        print("\nNenhuma feature testada (hora do pregao, momentum de tendencia, volume no "
              "toque/janela pre-toque, distancia a' abertura/media movel curta, regime de "
              "volatilidade curto/longo/expansao) sobreviveu ao gate de reproducibilidade "
              "split-half -- sem filtro a propor. Reportado honestamente: nao ha evidencia "
              "MENSURAVEL nesta resolucao (M1) de que essas caracteristicas de entrada "
              "distinguem trade vencedor de perdedor, em vez de forcar um filtro em cima de ruido.")


if __name__ == "__main__":
    main()
