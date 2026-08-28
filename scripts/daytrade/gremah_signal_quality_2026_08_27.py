"""QUALIDADE DE SINAL da ENTRADA -- familia GREMAH, PMAM3, motor M1
(2026-08-27), a partir do trade log ja gerado por
`capital_ladder_gremah_2026_08_27.py` (N=1 lote fixo, 1231 trades, mesmo
IS: `_geometria_comum.carregar_is("PMAM3", motor="m1")`, corte congelado em
`profiles.OOS_CUTOFF="2026-06-13"`, `LockedBars.unlock()` NUNCA chamado).

Pergunta do dono: que CARACTERISTICAS DE ENTRADA distinguem trade vencedor
de perdedor -- o que pode reduzir ruido / servir de FILTRO pra operar mais
seguro. Reusa o padrao ja existente em `copa_rejection_lab.py` (import
direto, sem reescrever a logica): `testa_proxy` (correlacao de Pearson +
teste de permutacao + diferenca por tercil), `proxies_reproduziveis` (gate
de reproducao split-half -- mesmo sinal E p<0,05 no pool E p<0,10 em cada
metade cronologica) e `_volume_bar` (real_volume se reportado, senao
tick_volume). So' o CALCULO DAS FEATURES muda (colunas do trade log da
Gremah M1, nao do fill maker da Copa).

## Features testadas (candidatos da tarefa, adaptados ao sinal real do robo)

Todas calculadas SO' com dado disponivel ATE o instante do toque (a propria
barra de preenchimento e barras anteriores, nunca o resultado do trade), e
NUNCA cruzando a fronteira de sessao (todo lookback e' truncado na 1a barra
do PREGAO do trade -- a Gremah zera estado a cada sessao, misturar com o
fechamento do dia anterior seria vazamento de um regime diferente):

  - `minutos_desde_abertura`: minutos entre a 1a barra do pregao e o toque.
    Direto (nao "side-aware") -- e' literalmente o relogio do pregao, o
    mesmo que decide a troca ancora-fixa/ancora-rolante em `on_bar`
    (`fixed_anchor_until`, 14:00 UTC).
  - `drift_abertura_ticks`: distancia (em ticks) entre a ABERTURA do dia e o
    preco de entrada, SIDE-AWARE (positivo = preco se moveu na direcao que
    a entrada de reversao espera -- caiu antes de uma compra, subiu antes
    de uma venda). Na fase ANCORA-FIXA isto e' quase constante (a ancora E'
    a abertura, entao a distancia e' so' o espacamento fixo da geometria);
    so' varia de verdade na fase ANCORA-ROLANTE, onde captura quanto o
    pregao ja derivou da abertura ate a ancora rolante daquele momento.
  - `velocidade_pretoque` (K=5 barras): MESMA definicao de
    `copa_rejection_lab.computa_proxies` (movimento de preco na DIRECAO do
    toque, em ticks) -- momentum/velocidade de aproximacao nas barras
    imediatamente antes do preenchimento.
  - `volume_toque` / `volume_janela_pretoque` (media K=5 barras): volume da
    propria barra do toque e volume medio das barras imediatamente antes.
  - `dist_mm20_ticks`: distancia SIDE-AWARE entre o preco de entrada e a
    media movel simples de 20 barras (fechamentos ANTERIORES ao toque,
    nunca incluindo a barra do toque) -- proxy de "quao esticado" o preco
    esta' frente a uma referencia de curto prazo mais suave que a abertura
    ou a ancora do robo.
  - `vol_regime_ticks`: range medio (high-low) das mesmas 20 barras
    anteriores, em ticks -- proxy de regime de volatilidade recente (tipo
    ATR curto).

`distancia ate o anchor da estrategia` (um dos 3 candidatos de referencia
pedidos) NAO virou feature separada: a geometria em ticks da PMAM3 e'
FIXA (`_GEOMETRIA_TICKS_BY_SYMBOL["PMAM3"] = (1, 1, 4)`, espacamento
SEMPRE 1 tick, aplicado por ultimo em `_session_ticks` independente de
fase/preco -- ver `gremah.py`), entao a distancia entre preco de entrada e
ancora e' uma CONSTANTE (1 tick) por construcao, sem variancia nenhuma pra
testar. `drift_abertura_ticks` e `dist_mm20_ticks` acima sao os dois
proxies de referencia que de fato variam entre trades.

## Gate de validacao (NAO negociavel, pedido do dono)

So' reporta uma feature como "valida" se passar `proxies_reproduziveis`:
MESMO SINAL da correlacao E p<0,05 no pool inteiro E p<0,10 em CADA metade
cronologica do IS. Toda feature testada aparece na tabela final, inclusive
as que NAO passam -- negativo nao e' escondido.

## Filtro simples, calibrado numa metade e testado na outra

Para toda feature que sobreviver ao gate: limiar = mediana da feature na
METADE 1 (cronologica) da sub-amostra valida daquela feature; direcao do
filtro (`>=` ou `<=`) = sinal da correlacao medida na METADE 1. O filtro e'
aplicado CRU na METADE 2 (nunca recalibrado nela) e o efeito liquido
(trades descartados, P&L com/sem filtro, MaxDD com/sem filtro) e' reportado
sem veredito embutido.

Nenhum arquivo rastreado foi editado; nada foi commitado.

Uso: `python -u scripts/daytrade/gremah_signal_quality_2026_08_27.py`
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

from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402

from _geometria_comum import carregar_economics, carregar_is  # noqa: E402
from copa_rejection_lab import (  # noqa: E402
    ResultadoCorrelacao,
    _volume_bar,
    imprime_correlacao,
    proxies_reproduziveis,
    testa_proxy,
)

SYMBOL = "PMAM3"
MOTOR = "m1"

#: Trade log ja gerado pela etapa anterior (N=1 lote fixo, geometria/entradas/
#: saidas da Gremah original intocadas -- ver `capital_ladder_gremah_2026_08_
#: 27.py`). Este script NAO re-roda o motor: so' le o CSV e as barras do IS.
TRADE_LOG_CSV = ROOT / "scratch" / "scripts" / "capital_ladder_gremah_pmam3_n1_trades_2026_08_27.csv"

SCRATCH_DIR = ROOT / "scratch" / "scripts"
CSV_FEATURES_TRADES = SCRATCH_DIR / "gremah_signal_quality_trades_features_2026_08_27.csv"
CSV_RESUMO_FEATURES = SCRATCH_DIR / "gremah_signal_quality_resumo_2026_08_27.csv"
CSV_RESUMO_FILTROS = SCRATCH_DIR / "gremah_signal_quality_filtros_2026_08_27.csv"

#: Janelas de lookback em BARRAS M1, nunca cruzando a fronteira de sessao.
JANELA_MOMENTUM_BARRAS = 5
JANELA_REF_BARRAS = 20
MIN_BARRAS_MOMENTUM = 3
MIN_BARRAS_REF = 10


# ---------------------------------------------------------------------------
# features por trade -- so' dado disponivel ATE o toque, nunca cruza sessao
# ---------------------------------------------------------------------------

@dataclass
class FeatureTrade:
    pnl_brl: float
    minutos_desde_abertura: float
    drift_abertura_ticks: float
    velocidade_ticks: float
    velocidade_valida: bool
    volume_toque: float
    volume_janela: float
    dist_mm20_ticks: float
    dist_mm20_valida: bool
    vol_regime_ticks: float
    vol_regime_valida: bool


def computa_features(trades_df: pd.DataFrame, bars: pd.DataFrame, tick_size: float,
                      janela_momentum: int = JANELA_MOMENTUM_BARRAS,
                      janela_ref: int = JANELA_REF_BARRAS) -> tuple[list[FeatureTrade], int]:
    idx = bars.index
    opens = bars["open"].to_numpy(dtype=np.float64)
    highs = bars["high"].to_numpy(dtype=np.float64)
    lows = bars["low"].to_numpy(dtype=np.float64)
    closes = bars["close"].to_numpy(dtype=np.float64)
    volumes = _volume_bar(bars)

    # 1a posicao de barra de cada PREGAO (data, em UTC) -- todo lookback e'
    # truncado aqui, nunca pega barra de sessao anterior.
    dates = idx.date
    primeira_pos_do_dia: dict = {}
    for i, d in enumerate(dates):
        if d not in primeira_pos_do_dia:
            primeira_pos_do_dia[d] = i

    posicoes = idx.get_indexer(pd.to_datetime(trades_df["entry_ts"], utc=True))
    out: list[FeatureTrade] = []
    sem_match = 0
    for row, pos in zip(trades_df.itertuples(index=False), posicoes):
        if pos < 0:
            sem_match += 1
            continue
        pos_abertura = primeira_pos_do_dia[dates[pos]]
        minutos = (idx[pos] - idx[pos_abertura]).total_seconds() / 60.0

        side = row.side
        entry_price = float(row.entry_price)
        open_dia = float(opens[pos_abertura])
        if side == "long":
            drift = (open_dia - entry_price) / tick_size
        else:
            drift = (entry_price - open_dia) / tick_size

        inicio_mom = max(pos_abertura, pos - janela_momentum)
        janela_close_mom = closes[inicio_mom:pos]
        if len(janela_close_mom) >= MIN_BARRAS_MOMENTUM:
            if side == "long":
                vel = (janela_close_mom[0] - janela_close_mom[-1]) / tick_size
            else:
                vel = (janela_close_mom[-1] - janela_close_mom[0]) / tick_size
            vel_valida = True
        else:
            vel = 0.0
            vel_valida = False
        janela_vol_mom = volumes[inicio_mom:pos]
        vol_janela = float(janela_vol_mom.mean()) if len(janela_vol_mom) else 0.0

        inicio_ref = max(pos_abertura, pos - janela_ref)
        janela_close_ref = closes[inicio_ref:pos]
        if len(janela_close_ref) >= MIN_BARRAS_REF:
            mm20 = float(janela_close_ref.mean())
            if side == "long":
                dist_mm = (mm20 - entry_price) / tick_size
            else:
                dist_mm = (entry_price - mm20) / tick_size
            dist_mm_valida = True
            janela_hl_ref = highs[inicio_ref:pos] - lows[inicio_ref:pos]
            vol_regime = float(janela_hl_ref.mean()) / tick_size
            vol_regime_valida = True
        else:
            dist_mm = 0.0
            dist_mm_valida = False
            vol_regime = 0.0
            vol_regime_valida = False

        out.append(FeatureTrade(
            pnl_brl=float(row.pnl_brl), minutos_desde_abertura=minutos,
            drift_abertura_ticks=drift, velocidade_ticks=vel, velocidade_valida=vel_valida,
            volume_toque=float(volumes[pos]), volume_janela=vol_janela,
            dist_mm20_ticks=dist_mm, dist_mm20_valida=dist_mm_valida,
            vol_regime_ticks=vol_regime, vol_regime_valida=vol_regime_valida,
        ))
    return out, sem_match


# ---------------------------------------------------------------------------
# filtro simples: limiar calibrado na metade 1, testado CRU na metade 2
# ---------------------------------------------------------------------------

def calibra_e_testa_filtro(nome: str, x: np.ndarray, y: np.ndarray, r: ResultadoCorrelacao) -> dict:
    """`x`/`y` ja na ordem cronologica da sub-amostra valida daquela feature
    (mesma ordem de `trades_df`, filtrada por validade). Limiar = mediana de
    `x` na metade 1; direcao (`>=`/`<=`) = sinal da correlacao NA METADE 1
    (nao no pool inteiro -- calibracao usa so' o que a metade 1 sabe).
    Metade 2 nunca participa da calibracao, so' da medicao do efeito."""
    meio = len(x) // 2
    x1, y1 = x[:meio], y[:meio]
    x2, y2 = x[meio:], y[meio:]

    n1, n2 = len(x1), len(x2)
    if n1 < 2 or np.std(x1) == 0.0 or n2 < 2:
        corr1 = float("nan")
        sinal_pos = r.corr_real > 0
    else:
        corr1 = float(np.corrcoef(x1, y1)[0, 1])
        sinal_pos = corr1 > 0
    limiar = float(np.median(x1))
    mantem2 = (x2 >= limiar) if sinal_pos else (x2 <= limiar)

    n_com = int(mantem2.sum())
    n_descartados = n2 - n_com
    pnl_sem = float(y2.sum())
    pnl_com = float(y2[mantem2].sum()) if n_com else 0.0
    pnl_medio_sem = pnl_sem / n2 if n2 else 0.0
    pnl_medio_com = pnl_com / n_com if n_com else 0.0

    curva_sem = np.concatenate([[0.0], np.cumsum(y2)])
    curva_com = np.concatenate([[0.0], np.cumsum(y2[mantem2])]) if n_com else np.array([0.0])
    maxdd_sem = maxdd_brl(pd.Series(curva_sem))
    maxdd_com = maxdd_brl(pd.Series(curva_com))

    return dict(
        feature=nome, direcao=(">=" if sinal_pos else "<="), limiar=limiar,
        corr_metade1=corr1, n_metade2=n2, n_mantidos_metade2=n_com,
        n_descartados_metade2=n_descartados,
        pnl_sem_filtro_brl=pnl_sem, pnl_com_filtro_brl=pnl_com,
        pnl_medio_sem_filtro_brl=pnl_medio_sem, pnl_medio_com_filtro_brl=pnl_medio_com,
        maxdd_sem_filtro_brl=maxdd_sem, maxdd_com_filtro_brl=maxdd_com,
    )


def imprime_filtro(f: dict) -> None:
    print(f"\n  filtro calibrado: {f['feature']} {f['direcao']} {num_br(f['limiar'], 4)} "
          f"(mediana da metade 1, corr metade1={num_br(f['corr_metade1'], 4)})")
    print(f"  metade 2: {f['n_metade2']} trades -- mantem {f['n_mantidos_metade2']}, "
          f"descarta {f['n_descartados_metade2']}")
    print(f"  P&L TOTAL metade2 SEM filtro = R${num_br(f['pnl_sem_filtro_brl'])} | "
          f"COM filtro = R${num_br(f['pnl_com_filtro_brl'])} "
          f"(total cai mecanicamente ao descartar trade -- comparar tambem a MEDIA abaixo)")
    print(f"  P&L MEDIO/trade metade2 SEM filtro = R${num_br(f['pnl_medio_sem_filtro_brl'], 4)} | "
          f"COM filtro = R${num_br(f['pnl_medio_com_filtro_brl'], 4)}")
    print(f"  MaxDD metade2 SEM filtro = R${num_br(f['maxdd_sem_filtro_brl'])} | "
          f"COM filtro = R${num_br(f['maxdd_com_filtro_brl'])}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    run_bars, profile, referencia = carregar_is(SYMBOL, motor=MOTOR)
    if run_bars.empty:
        raise SystemExit(f"[signal_quality] sem dado local IS para {SYMBOL!r} (motor={MOTOR!r})")
    pregoes_is = len(set(run_bars.index.date))
    print(f"[signal_quality] {SYMBOL} motor={MOTOR} -- IS: {len(run_bars)} barras, "
          f"{pregoes_is} pregoes, {run_bars.index.min()} -> {run_bars.index.max()}")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    tick_size = economics.trade_tick_size
    print(f"[signal_quality] tick_size {SYMBOL} = {tick_size}")

    if not TRADE_LOG_CSV.exists():
        raise SystemExit(f"[signal_quality] trade log nao encontrado: {TRADE_LOG_CSV}")
    trades_df = pd.read_csv(TRADE_LOG_CSV)
    trades_df["entry_ts"] = pd.to_datetime(trades_df["entry_ts"], utc=True)
    trades_df["exit_ts"] = pd.to_datetime(trades_df["exit_ts"], utc=True)
    trades_df = trades_df.sort_values("entry_ts", kind="stable").reset_index(drop=True)
    print(f"[signal_quality] trade log: {len(trades_df)} trades, "
          f"{trades_df['entry_ts'].min()} -> {trades_df['entry_ts'].max()}")

    feats, sem_match = computa_features(trades_df, run_bars, tick_size)
    print(f"[signal_quality] features calculadas para {len(feats)}/{len(trades_df)} trades "
          f"({sem_match} sem barra correspondente -- deveria ser 0)")

    n_vel = sum(1 for f in feats if f.velocidade_valida)
    n_ref = sum(1 for f in feats if f.dist_mm20_valida)
    print(f"[signal_quality] {n_vel}/{len(feats)} com janela de momentum valida "
          f"(>= {MIN_BARRAS_MOMENTUM} barras / {JANELA_MOMENTUM_BARRAS}); "
          f"{n_ref}/{len(feats)} com janela de referencia valida "
          f"(>= {MIN_BARRAS_REF} barras / {JANELA_REF_BARRAS})")

    # dump por-trade (auditoria/reproducao)
    pd.DataFrame([dict(
        pnl_brl=f.pnl_brl, minutos_desde_abertura=f.minutos_desde_abertura,
        drift_abertura_ticks=f.drift_abertura_ticks,
        velocidade_ticks=(f.velocidade_ticks if f.velocidade_valida else None),
        volume_toque=f.volume_toque, volume_janela_pretoque=f.volume_janela,
        dist_mm20_ticks=(f.dist_mm20_ticks if f.dist_mm20_valida else None),
        vol_regime_ticks=(f.vol_regime_ticks if f.vol_regime_valida else None),
    ) for f in feats]).to_csv(CSV_FEATURES_TRADES, index=False)
    print(f"[signal_quality] features por trade salvas em {CSV_FEATURES_TRADES}")

    pnl_all = np.array([f.pnl_brl for f in feats])
    minutos_all = np.array([f.minutos_desde_abertura for f in feats])
    drift_all = np.array([f.drift_abertura_ticks for f in feats])
    voltoque_all = np.array([f.volume_toque for f in feats])
    voljan_all = np.array([f.volume_janela for f in feats])

    vel_validos = [f for f in feats if f.velocidade_valida]
    vel_arr = np.array([f.velocidade_ticks for f in vel_validos])
    pnl_vel = np.array([f.pnl_brl for f in vel_validos])

    ref_validos = [f for f in feats if f.dist_mm20_valida]
    distmm_arr = np.array([f.dist_mm20_ticks for f in ref_validos])
    volregime_arr = np.array([f.vol_regime_ticks for f in ref_validos])
    pnl_ref = np.array([f.pnl_brl for f in ref_validos])

    # {nome: (x, y)} -- ordem cronologica preservada em cada array (feats/
    # vel_validos/ref_validos sao filtrados de `feats`, que segue a ordem de
    # `trades_df` ja ordenado por entry_ts)
    candidatos_xy = {
        "minutos_desde_abertura": (minutos_all, pnl_all),
        "drift_abertura_ticks": (drift_all, pnl_all),
        "volume_toque": (voltoque_all, pnl_all),
        "volume_janela_pretoque": (voljan_all, pnl_all),
        "velocidade_pretoque": (vel_arr, pnl_vel),
        "dist_mm20_ticks": (distmm_arr, pnl_ref),
        "vol_regime_ticks": (volregime_arr, pnl_ref),
    }

    print(f"\n=== {SYMBOL} -- correlacao proxy <-> P&L do trade (permutacao, n_perm=5000) ===")
    resultados: dict[str, tuple[np.ndarray, np.ndarray, ResultadoCorrelacao]] = {}
    for i, (nome, (x, y)) in enumerate(candidatos_xy.items()):
        r = testa_proxy(nome, x, y, seed=i)
        imprime_correlacao(r)
        resultados[nome] = (x, y, r)

    reproduziveis = proxies_reproduziveis(resultados)
    nomes_reproduziveis = {nome for nome, _, _ in reproduziveis}

    # ------------------------------------------------------------------
    # tabela final CRUA -- TODAS as features, inclusive as que NAO passaram
    # ------------------------------------------------------------------
    linhas_resumo = []
    for nome, (x, y, r) in resultados.items():
        linhas_resumo.append(dict(
            feature=nome, n=r.n, corr_pearson=r.corr_real, p_permutacao=r.p_two_sided,
            tercil_baixo_pnl_medio=r.tercil_baixo_media, tercil_alto_pnl_medio=r.tercil_alto_media,
            diff_tercil_pnl=r.diff_tercil, p_diff_tercil=r.diff_tercil_p,
            passou_gate_split_half=(nome in nomes_reproduziveis),
        ))
    df_resumo = pd.DataFrame(linhas_resumo)
    df_resumo.to_csv(CSV_RESUMO_FEATURES, index=False)

    print(f"\n\n=== {SYMBOL} -- TABELA CRUA: TODAS as features testadas ===")
    cab = (f"{'feature':<26}{'n':>6}{'corr':>9}{'p_perm':>9}{'terc_baixo':>13}"
           f"{'terc_alto':>12}{'diff_terc':>12}{'p_diff':>9}{'passou_gate':>13}")
    print(cab)
    print("-" * len(cab))
    for ln in linhas_resumo:
        print(f"{ln['feature']:<26}{ln['n']:>6}{num_br(ln['corr_pearson'], 4):>9}"
              f"{num_br(ln['p_permutacao'], 4):>9}{num_br(ln['tercil_baixo_pnl_medio']):>13}"
              f"{num_br(ln['tercil_alto_pnl_medio']):>12}{num_br(ln['diff_tercil_pnl']):>12}"
              f"{num_br(ln['p_diff_tercil'], 4):>9}{str(ln['passou_gate_split_half']):>13}")
    print(f"\n[signal_quality] resumo por feature salvo em {CSV_RESUMO_FEATURES}")

    # ------------------------------------------------------------------
    # filtro simples para toda feature que passou o gate
    # ------------------------------------------------------------------
    if not reproduziveis:
        print(f"\n=== {SYMBOL} -- VEREDITO ===")
        print("nenhuma das 7 features testadas (minutos_desde_abertura, "
              "drift_abertura_ticks, volume_toque, volume_janela_pretoque, "
              "velocidade_pretoque, dist_mm20_ticks, vol_regime_ticks) mostrou "
              "correlacao com o P&L do trade significativa E reproduzivel "
              "(split-half) -- nenhum filtro foi calibrado. Reportado honestamente "
              "como risco NAO-mensuravel nesta resolucao de dado, sem forcar um "
              "filtro em cima de ruido.")
        return

    print(f"\n=== {SYMBOL} -- filtro calibrado na metade 1, testado CRU na metade 2 ===")
    linhas_filtro = []
    for nome, x, y in reproduziveis:
        r = resultados[nome][2]
        f = calibra_e_testa_filtro(nome, x, y, r)
        imprime_filtro(f)
        linhas_filtro.append(f)

    pd.DataFrame(linhas_filtro).to_csv(CSV_RESUMO_FILTROS, index=False)
    print(f"\n[signal_quality] resultado dos filtros salvo em {CSV_RESUMO_FILTROS}")


if __name__ == "__main__":
    main()
