"""Qualidade de sinal -- WdoGridReloadMaker F1 (WDO@, "T1 S16 x1"), 2026-08-27.

Pergunta do dono: que CARACTERISTICAS DE ENTRADA distinguem trades
vencedores de perdedores neste candidato -- pode servir de FILTRO pra
operar mais seguro (reduzir ruido sem reoptimizar a estrategia em si)?

## Fonte dos dados -- NENHUM rerun do motor

Usa o trade log ja' computado por `capital_ladder_wdof1_2026_08_27.py`
(N=1, ESTATICO, `capital_ladder_wdof1_n1_trades_2026_08_27.csv`, 2.773
trades) como a lista definitiva de trades -- entry_ts/entry_price/side/
pnl_brl/exit_reason direto do CSV, sem reinstanciar `WdoGridReloadMaker`
nem re-simular o motor. As FEATURES de entrada (hora do pregao,
velocidade, volume, distancia a referencias, regime de volatilidade) sao
recalculadas a partir do TICK CRU original (`wdo_grid_reload_f1_tick_lab.
carregar_tick_bars()` -- MESMA funcao/MESMA janela de
`capital_ladder_wdof1_2026_08_27.py`, 72 pregoes IS com tick disponivel no
terminal MT5, 2026-02-27..2026-06-12), localizando o tick que causou cada
toque (mesmo criterio de `_limit_touched`, ja usado por
`wdo_grid_reload_f1_tick_rejection_lab.py::_acha_toque` -- aqui
reimplementado com `np.searchsorted` em vez de `np.flatnonzero` sobre o
array inteiro, O(log n) por trade em vez de O(n): a varredura linear
custaria ~2.773 x 2,83M comparacoes).

So' o IN-SAMPLE tick e' tocado (mesma janela travada da etapa anterior) --
`OOS_CUTOFF=2026-06-13` nunca e' tocado, `.unlock()` nunca e' chamado.

## Padrao reaproveitado (nao reescrito)

`testa_proxy`/`imprime_correlacao`/`proxies_reproduziveis` importados
DIRETO de `copa_rejection_lab.py` (genericos em `(x, y)`, nenhuma linha
copiada) -- correlacao de Pearson + teste de permutacao (n_perm=5000) +
diferenca por tercil + gate de reproducao split-half (MESMO sinal E
p<0,05 no pool E p<0,10 em CADA metade cronologica). So' features que
passam esse gate viram "validas" -- o resto entra na tabela crua igual,
marcado como NAO reproduzivel (nao escondido).

## Candidatos de feature (todas calculadas SO' com dado ANTES/NO instante
## do toque -- nunca o resultado do trade)

  A. hora do pregao      -- minutos_desde_abertura (abertura = 1o tick do
                             pregao no subconjunto tick, nao um horario
                             fixo hardcoded).
  B. momentum/velocidade -- velocidade_15s_ticks / velocidade_60s_ticks
                             (movimento em ticks, na DIRECAO do toque,
                             janela de tempo pre-toque -- mesma formula de
                             `wdo_grid_reload_f1_tick_rejection_lab.
                             computa_proxies`, duas janelas em vez de uma).
  C. volume              -- volume_toque (tick que causou o fill),
                             volume_janela_15s (soma, TODOS os ticks da
                             janela, nao so' os do mesmo preco -- mais
                             amplo que o `crowd_volume` da rodada
                             anterior), n_ticks_janela_15s (contagem =
                             proxy de atividade/liquidez).
  D. distancia a referencia -- dist_abertura_ticks (|entry_price - preco
                             do 1o tick do pregao| -- quanto o dia ja'
                             "andou" antes deste toque), dist_ma_curta_
                             ticks (|entry_price - media dos precos nos
                             180s anteriores|). NAO testa distancia a'
                             ANCORA da propria estrategia: com
                             `level_spacing_ticks=1` fixo em toda a
                             rodada, entry_price = ancora +/- exatamente 1
                             tick SEMPRE -- e' uma CONSTANTE por
                             construcao (variancia zero), nao uma feature
                             (ver `WdoGridReloadMaker._level_price`).
  E. regime de volatilidade -- range_5min_ticks ((max-min) dos precos nos
                             300s anteriores, em ticks -- proxy de ATR
                             nesta resolucao, ja que tick nao tem barra
                             OHLC nativa pra calcular ATR de verdade).

## Ressalva sobre poder estatistico -- LEIA antes de interpretar

O candidato tem 2.755 vencedores (quase todos +R$4,50, alvo de 1 tick) e
SO' 18 perdedores (15 stop a' -R$85,50, 3 forced_flatten entre -R$5,50 e
-R$45,50) em 2.773 trades -- 0,65% de perdas. Qualquer correlacao com
`pnl_brl` bruto e' MECANICAMENTE dominada por esses 18 pontos de alta
alavancagem estatistica (removendo ou trocando 1 deles move a correlacao
muito mais que trocar 100 vencedores entre si). Reportado explicitamente,
nao escondido -- e' o motivo mais provavel se NENHUMA feature passar o
gate de reproducao (baixo poder, nao ausencia de mecanismo).

## Filtro simulado (so' para features que passam o gate)

Direcao (tercil alto ou baixo e' "melhor") lida do sinal de `diff_tercil`
medido no POOL inteiro. Limiar calibrado SO' na metade1 cronologica
(percentil 33 ou 67, o MESMO corte de tercil ja usado no teste de
correlacao) -- aplicado 1x, sem reajuste, na metade2. Trade sem a feature
computavel (janela insuficiente) NUNCA e' descartado pelo filtro (passa
direto) -- o filtro so' pode agir onde ha' dado pra decidir.

Uso: `python -u scripts/daytrade/signal_quality_wdof1_2026_08_27.py`
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
from strategy.daytrade.lab.wdo_grid_reload_maker import WDO_TICK_SIZE  # noqa: E402

from copa_rejection_lab import (  # noqa: E402
    ResultadoCorrelacao,
    imprime_correlacao,
    proxies_reproduziveis,
    testa_proxy,
)
from wdo_grid_reload_f1_tick_lab import carregar_tick_bars  # noqa: E402
from wdo_grid_reload_f1_tick_rejection_lab import _tick_arrays  # noqa: E402

OUT_DIR = ROOT / "scripts" / "daytrade"
TRADE_LOG_CSV = OUT_DIR / "capital_ladder_wdof1_n1_trades_2026_08_27.csv"
FEATURES_CSV = OUT_DIR / "signal_quality_wdof1_features_2026_08_27.csv"
SUMMARY_CSV = OUT_DIR / "signal_quality_wdof1_resumo_2026_08_27.csv"
FILTROS_CSV = OUT_DIR / "signal_quality_wdof1_filtros_2026_08_27.csv"

JANELA_VEL_CURTA_S = 15
JANELA_VEL_LONGA_S = 60
JANELA_MA_S = 180
JANELA_RANGE_S = 300
MIN_TICKS_VEL_CURTA = 3
MIN_TICKS_VEL_LONGA = 5
MIN_TICKS_MA = 10
MIN_TICKS_RANGE = 10


# ---------------------------------------------------------------------------
# 0. trade log (CSV ja' computado -- nenhum rerun do motor)
# ---------------------------------------------------------------------------

@dataclass
class CsvTrade:
    entry_ts: pd.Timestamp
    side: str
    entry_price: float
    pnl_brl: float
    exit_reason: str


def carregar_trade_log(path: Path) -> list[CsvTrade]:
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True, format="ISO8601")
    df = df.sort_values("entry_ts").reset_index(drop=True)
    if not df["quantity"].eq(1).all():
        raise SystemExit(f"[signal_quality] esperava quantity==1 em TODA linha de {path} (N=1) -- "
                          f"valores encontrados: {sorted(df['quantity'].unique())}")
    return [
        CsvTrade(entry_ts=row.entry_ts, side=row.side, entry_price=float(row.entry_price),
                 pnl_brl=float(row.pnl_brl), exit_reason=row.exit_reason)
        for row in df.itertuples()
    ]


# ---------------------------------------------------------------------------
# 1. localizar o tick de toque -- O(log n) por trade via searchsorted
# ---------------------------------------------------------------------------

def _acha_toque_rapido(ts_ns: np.ndarray, preco: np.ndarray, entry_ts_ns: int,
                        entry_price: float, side: str) -> int | None:
    """Mesmo criterio de `wdo_grid_reload_f1_tick_rejection_lab._acha_toque`
    (posicao do tick que satisfaz `_limit_touched`, desempate pelo PRIMEIRO
    candidato no mesmo timestamp que bate a condicao de toque), so' que
    localiza o INTERVALO de indices com aquele timestamp via busca binaria
    (`ts_ns` ja vem ordenado) em vez de escanear o array inteiro -- ambos
    devolvem o MESMO indice, so' um e' O(log n) e o outro O(n) por trade."""
    lo = int(np.searchsorted(ts_ns, entry_ts_ns, side="left"))
    hi = int(np.searchsorted(ts_ns, entry_ts_ns, side="right"))
    if lo == hi:
        return None
    if hi - lo == 1:
        return lo
    for idx in range(lo, hi):
        p = preco[idx]
        if (p <= entry_price) if side == "long" else (p >= entry_price):
            return idx
    return lo


def _aberturas_por_dia(tick_bars: pd.DataFrame) -> dict:
    """`{data: (timestamp_ns_do_1o_tick, preco_do_1o_tick)}` -- abertura do
    pregao LIDA DO PROPRIO DADO (1o tick do subconjunto tick daquele dia),
    nao um horario fixo hardcoded (a sessao do WDO@ nao comeca no mesmo
    segundo todo dia no feed do MT5)."""
    aberturas: dict = {}
    for d, grp in tick_bars.groupby(tick_bars.index.date):
        aberturas[d] = (int(grp.index[0].value), float(grp["close"].iloc[0]))
    return aberturas


# ---------------------------------------------------------------------------
# 2. features por trade
# ---------------------------------------------------------------------------

@dataclass
class FeatureRow:
    pnl_brl: float
    minutos_desde_abertura: float
    velocidade_15s: float
    velocidade_15s_valida: bool
    velocidade_60s: float
    velocidade_60s_valida: bool
    volume_toque: float
    volume_janela_15s: float
    n_ticks_janela_15s: int
    dist_abertura_ticks: float
    dist_ma_curta_ticks: float
    dist_ma_curta_valida: bool
    range_5min_ticks: float
    range_5min_valida: bool
    exit_reason: str
    entry_ts: pd.Timestamp


def computa_features(trades: list[CsvTrade], tick_bars: pd.DataFrame,
                      tick_size: float = WDO_TICK_SIZE) -> tuple[list[FeatureRow], int]:
    ts_ns, preco, volume = _tick_arrays(tick_bars)
    aberturas = _aberturas_por_dia(tick_bars)
    out: list[FeatureRow] = []
    sem_match = 0

    def _vel(janela_p: np.ndarray, min_ticks: int, side: str) -> tuple[float, bool]:
        if len(janela_p) < min_ticks:
            return 0.0, False
        if side == "long":
            v = (janela_p[0] - janela_p[-1]) / tick_size
        else:
            v = (janela_p[-1] - janela_p[0]) / tick_size
        return float(v), True

    for t in trades:
        entry_ts_ns = int(t.entry_ts.value)
        touch_idx = _acha_toque_rapido(ts_ns, preco, entry_ts_ns, t.entry_price, t.side)
        if touch_idx is None:
            sem_match += 1
            continue

        dia = t.entry_ts.date()
        abertura_ts_ns, abertura_price = aberturas[dia]
        minutos = (entry_ts_ns - abertura_ts_ns) / 1e9 / 60.0
        dist_abertura = abs(t.entry_price - abertura_price) / tick_size

        def _inicio(seg: int) -> int:
            limite = entry_ts_ns - int(seg * 1_000_000_000)
            return int(np.searchsorted(ts_ns, limite, side="left"))

        i15, i60, i180, i300 = _inicio(JANELA_VEL_CURTA_S), _inicio(JANELA_VEL_LONGA_S), \
            _inicio(JANELA_MA_S), _inicio(JANELA_RANGE_S)

        # fim EXCLUSIVO = touch_idx em todas -- nunca inclui o proprio tick
        # de toque (disciplina anti-look-ahead ja documentada no cabecalho).
        j15_p, j60_p = preco[i15:touch_idx], preco[i60:touch_idx]
        j180_p, j300_p = preco[i180:touch_idx], preco[i300:touch_idx]
        j15_v = volume[i15:touch_idx]

        vel15, vel15_ok = _vel(j15_p, MIN_TICKS_VEL_CURTA, t.side)
        vel60, vel60_ok = _vel(j60_p, MIN_TICKS_VEL_LONGA, t.side)

        if len(j180_p) >= MIN_TICKS_MA:
            dist_ma, dist_ma_ok = abs(t.entry_price - float(j180_p.mean())) / tick_size, True
        else:
            dist_ma, dist_ma_ok = 0.0, False

        if len(j300_p) >= MIN_TICKS_RANGE:
            rng, rng_ok = (float(j300_p.max()) - float(j300_p.min())) / tick_size, True
        else:
            rng, rng_ok = 0.0, False

        out.append(FeatureRow(
            pnl_brl=t.pnl_brl, minutos_desde_abertura=minutos,
            velocidade_15s=vel15, velocidade_15s_valida=vel15_ok,
            velocidade_60s=vel60, velocidade_60s_valida=vel60_ok,
            volume_toque=float(volume[touch_idx]),
            volume_janela_15s=float(j15_v.sum()), n_ticks_janela_15s=int(touch_idx - i15),
            dist_abertura_ticks=dist_abertura,
            dist_ma_curta_ticks=dist_ma, dist_ma_curta_valida=dist_ma_ok,
            range_5min_ticks=rng, range_5min_valida=rng_ok,
            exit_reason=t.exit_reason, entry_ts=t.entry_ts,
        ))
    return out, sem_match


def salva_features_csv(feats: list[FeatureRow], path: Path) -> None:
    df = pd.DataFrame([dict(
        entry_ts=f.entry_ts.isoformat(), pnl_brl=f.pnl_brl, exit_reason=f.exit_reason,
        minutos_desde_abertura=f.minutos_desde_abertura,
        velocidade_15s=f.velocidade_15s, velocidade_15s_valida=f.velocidade_15s_valida,
        velocidade_60s=f.velocidade_60s, velocidade_60s_valida=f.velocidade_60s_valida,
        volume_toque=f.volume_toque, volume_janela_15s=f.volume_janela_15s,
        n_ticks_janela_15s=f.n_ticks_janela_15s, dist_abertura_ticks=f.dist_abertura_ticks,
        dist_ma_curta_ticks=f.dist_ma_curta_ticks, dist_ma_curta_valida=f.dist_ma_curta_valida,
        range_5min_ticks=f.range_5min_ticks, range_5min_valida=f.range_5min_valida,
    ) for f in feats])
    df.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# 3. filtro simulado (so' para features que passam o gate de reproducao)
# ---------------------------------------------------------------------------

def _aplica_e_mede(pnl2: np.ndarray, mantem: np.ndarray) -> dict:
    n_total2 = len(pnl2)
    n_mantidos = int(mantem.sum())
    pnl_sem = float(pnl2.sum())
    pnl_com = float(pnl2[mantem].sum())
    equity_sem = pd.Series(np.concatenate(([0.0], np.cumsum(pnl2))))
    equity_com = pd.Series(np.concatenate(([0.0], np.cumsum(pnl2[mantem]))))
    return dict(
        n_trades_metade2=n_total2, n_mantidos=n_mantidos, n_descartados=n_total2 - n_mantidos,
        pnl_sem_filtro_brl=pnl_sem, pnl_com_filtro_brl=pnl_com,
        maxdd_sem_filtro_brl=maxdd_brl(equity_sem), maxdd_com_filtro_brl=maxdd_brl(equity_com),
    )


def simula_filtro(nome: str, r: ResultadoCorrelacao, x_full: np.ndarray, pnl_full: np.ndarray) -> dict:
    """Limiar calibrado na METADE1 (percentil de TERCIL -- 33/67, o MESMO
    corte ja usado pelo `diff_tercil` do teste de correlacao, na direcao
    que o pool apontou), aplicado 1x na METADE2. Trade sem a feature
    computavel (NaN) NUNCA e' descartado -- passa direto."""
    n = len(pnl_full)
    meio = n // 2
    x1 = x_full[:meio]
    valid1 = ~np.isnan(x1)
    alto_melhor = r.diff_tercil > 0
    if alto_melhor:
        limiar = float(np.percentile(x1[valid1], 100.0 / 3.0))
        regra = f"manter so' se {nome} >= {num_br(limiar, 3)}"
    else:
        limiar = float(np.percentile(x1[valid1], 200.0 / 3.0))
        regra = f"manter so' se {nome} <= {num_br(limiar, 3)}"

    x2 = x_full[meio:]
    pnl2 = pnl_full[meio:]
    valid2 = ~np.isnan(x2)
    mantem = np.where(valid2, (x2 >= limiar) if alto_melhor else (x2 <= limiar), True)

    return dict(feature=nome, metodo="tercil_33_67_metade1", regra=regra,
                limiar_calibrado_metade1=limiar, **_aplica_e_mede(pnl2, mantem))


def simula_filtro_otimizado_metade1(nome: str, r: ResultadoCorrelacao, x_full: np.ndarray,
                                     pnl_full: np.ndarray) -> dict:
    """Alternativa mais rigorosa ao corte de tercil fixo: varre percentis
    1..99 (passo 1) SO' dentro da metade1 e escolhe o limiar que MAXIMIZA o
    P&L retido DENTRO da propria metade1 (nunca olha metade2 pra escolher)
    -- responde "existe ALGUM corte simples que ja' ajuda dentro dos dados
    de calibracao?" antes de aplicar cegamente na metade2. Reportado
    SEMPRE, mesmo se o melhor achado dentro da metade1 continuar negativo
    (nao esconde o resultado so' porque a busca nao encontrou nada bom)."""
    n = len(pnl_full)
    meio = n // 2
    x1, pnl1 = x_full[:meio], pnl_full[:meio]
    valid1 = ~np.isnan(x1)
    alto_melhor = r.diff_tercil > 0

    melhor_pct, melhor_delta1, melhor_limiar = None, -np.inf, None
    for pct in range(1, 100):
        lim = float(np.percentile(x1[valid1], pct if alto_melhor else 100 - pct))
        mask1 = np.where(valid1, (x1 >= lim) if alto_melhor else (x1 <= lim), True)
        delta1 = float(pnl1[mask1].sum() - pnl1.sum())
        if delta1 > melhor_delta1:
            melhor_delta1, melhor_pct, melhor_limiar = delta1, pct, lim

    regra = (f"manter so' se {nome} >= {num_br(melhor_limiar, 3)} (percentil {melhor_pct} da metade1)" if alto_melhor
             else f"manter so' se {nome} <= {num_br(melhor_limiar, 3)} (percentil {100 - melhor_pct} da metade1)")

    x2, pnl2 = x_full[meio:], pnl_full[meio:]
    valid2 = ~np.isnan(x2)
    mantem = np.where(valid2, (x2 >= melhor_limiar) if alto_melhor else (x2 <= melhor_limiar), True)

    saida = dict(feature=nome, metodo="grid_search_pct1-99_dentro_da_metade1", regra=regra,
                 limiar_calibrado_metade1=melhor_limiar,
                 delta_pnl_dentro_da_propria_metade1_brl=melhor_delta1,
                 **_aplica_e_mede(pnl2, mantem))
    return saida


def imprime_filtro(f: dict) -> None:
    print(f"\nfiltro -- {f['feature']} ({f['metodo']})")
    print(f"  regra ({f['regra']})")
    if "delta_pnl_dentro_da_propria_metade1_brl" in f:
        print(f"  honestidade: DENTRO da propria metade1 (dado de calibracao), este limiar muda o P&L "
              f"retido em R${num_br(f['delta_pnl_dentro_da_propria_metade1_brl'])} "
              f"(negativo = nem no melhor caso possivel o corte ajuda dentro da amostra que o escolheu)")
    print(f"  aplicado na metade2: {f['n_trades_metade2']} trades -> {f['n_mantidos']} mantidos, "
          f"{f['n_descartados']} descartados ({num_br(100.0 * f['n_descartados'] / f['n_trades_metade2'], 1)}%)")
    print(f"  P&L metade2 SEM filtro = R${num_br(f['pnl_sem_filtro_brl'])} | "
          f"COM filtro = R${num_br(f['pnl_com_filtro_brl'])}")
    print(f"  MaxDD metade2 SEM filtro = R${num_br(f['maxdd_sem_filtro_brl'])} | "
          f"COM filtro = R${num_br(f['maxdd_com_filtro_brl'])}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    trades = carregar_trade_log(TRADE_LOG_CSV)
    print(f"[signal_quality] {len(trades)} trades carregados de {TRADE_LOG_CSV}")
    perdedores = [t for t in trades if t.pnl_brl <= 0]
    print(f"[signal_quality] {len(trades) - len(perdedores)} vencedores / {len(perdedores)} perdedores "
          f"({num_br(100.0 * len(perdedores) / len(trades), 2)}% de perdas) -- ver ressalva de poder "
          f"estatistico na docstring do modulo.")

    dias, tick_bars = carregar_tick_bars()
    print(f"[signal_quality] tick bars: {len(tick_bars)} ticks, {len(dias)} pregoes IS "
          f"({dias[0]} -> {dias[-1]})")

    feats, sem_match = computa_features(trades, tick_bars)
    print(f"[signal_quality] features computadas para {len(feats)}/{len(trades)} trades "
          f"({sem_match} sem tick correspondente encontrado -- deveria ser 0)")
    salva_features_csv(feats, FEATURES_CSV)
    print(f"[signal_quality] tabela por-trade salva em {FEATURES_CSV}")

    # ---------------- descritivo por exit_reason (qualitativo, nao substitui o gate) ----------------
    print("\n=== 0. descritivo por exit_reason (qualitativo -- n muito pequeno em stop/forced_flatten) ===")
    df_desc = pd.DataFrame([dict(
        exit_reason=f.exit_reason, minutos_desde_abertura=f.minutos_desde_abertura,
        velocidade_15s=f.velocidade_15s if f.velocidade_15s_valida else np.nan,
        volume_toque=f.volume_toque, volume_janela_15s=f.volume_janela_15s,
        dist_abertura_ticks=f.dist_abertura_ticks,
        dist_ma_curta_ticks=f.dist_ma_curta_ticks if f.dist_ma_curta_valida else np.nan,
        range_5min_ticks=f.range_5min_ticks if f.range_5min_valida else np.nan,
    ) for f in feats])
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(df_desc.groupby("exit_reason").median(numeric_only=True))

    # ---------------- 1. correlacao proxy <-> pnl (todas as features) ----------------
    pnl_all = np.array([f.pnl_brl for f in feats])

    def _full(attr: str, attr_valida: str | None = None) -> np.ndarray:
        x = np.array([getattr(f, attr) for f in feats], dtype=float)
        if attr_valida is not None:
            v = np.array([getattr(f, attr_valida) for f in feats])
            x = np.where(v, x, np.nan)
        return x

    full_by_name = {
        "minutos_desde_abertura": _full("minutos_desde_abertura"),
        "velocidade_15s_ticks": _full("velocidade_15s", "velocidade_15s_valida"),
        "velocidade_60s_ticks": _full("velocidade_60s", "velocidade_60s_valida"),
        "volume_toque": _full("volume_toque"),
        "volume_janela_15s": _full("volume_janela_15s"),
        "n_ticks_janela_15s": _full("n_ticks_janela_15s"),
        "dist_abertura_ticks": _full("dist_abertura_ticks"),
        "dist_ma_curta_ticks": _full("dist_ma_curta_ticks", "dist_ma_curta_valida"),
        "range_5min_ticks": _full("range_5min_ticks", "range_5min_valida"),
    }

    print("\n=== 1. correlacao proxy <-> P&L do trade (permutacao, n_perm=5000) ===")
    resultados: dict[str, tuple[np.ndarray, np.ndarray, ResultadoCorrelacao]] = {}
    for i, (nome, x_full) in enumerate(full_by_name.items()):
        valid = ~np.isnan(x_full)
        x, y = x_full[valid], pnl_all[valid]
        r = testa_proxy(nome, x, y, seed=i + 1)
        imprime_correlacao(r)
        n_invalidos = int((~valid).sum())
        if n_invalidos:
            print(f"  ({n_invalidos}/{len(feats)} trades sem janela valida pra esta feature, excluidos do teste)")
        resultados[nome] = (x, y, r)

    reproduziveis = proxies_reproduziveis(resultados)

    # ---------------- 2. tabela resumo (TODAS as features, inclusive as que nao sobreviveram) ----------------
    linhas_resumo = []
    nomes_reproduziveis = {nome for nome, _, _ in reproduziveis}
    for nome, (x, y, r) in resultados.items():
        linhas_resumo.append(dict(
            feature=nome, n=r.n, corr_pearson=r.corr_real, p_bicaudal_pool=r.p_two_sided,
            tercil_baixo_brl=r.tercil_baixo_media, tercil_alto_brl=r.tercil_alto_media,
            diff_tercil_brl=r.diff_tercil, p_diff_tercil=r.diff_tercil_p,
            reproduzivel_split_half=nome in nomes_reproduziveis,
        ))
    df_resumo = pd.DataFrame(linhas_resumo)
    df_resumo.to_csv(SUMMARY_CSV, index=False)
    print(f"\n[signal_quality] tabela resumo (todas as features) salva em {SUMMARY_CSV}")
    print("\n=== TABELA CRUA -- todas as features testadas ===")
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.float_format", "{:,.4f}".format):
        print(df_resumo.to_string(index=False))

    # ---------------- 3. filtro simulado, so' para as reproduziveis ----------------
    if not reproduziveis:
        print("\n=== VEREDITO ===")
        print("nenhuma feature testada (hora do pregao, velocidade 15s/60s, volume no toque/janela, "
              "contagem de ticks, distancia a abertura/media curta, range de 5min) mostrou correlacao "
              "significativa E reproduzivel (split-half) com o P&L do trade. Sem filtro simulado -- "
              "nao ha' vencedor pra calibrar. Ver a ressalva de poder estatistico (18 perdas em 2.773 "
              "trades) na docstring do modulo antes de concluir 'sem sinal' -- pode ser 'sem poder'.")
        return

    print(f"\n[signal_quality] {len(reproduziveis)} feature(s) passaram o gate de reproducao: "
          + ", ".join(nome for nome, _, _ in reproduziveis))

    linhas_filtro = []
    for nome, _, _ in reproduziveis:
        r = resultados[nome][2]
        x_full = full_by_name[nome]
        f_tercil = simula_filtro(nome, r, x_full, pnl_all)
        imprime_filtro(f_tercil)
        linhas_filtro.append(f_tercil)
        f_otimo = simula_filtro_otimizado_metade1(nome, r, x_full, pnl_all)
        imprime_filtro(f_otimo)
        linhas_filtro.append(f_otimo)

    pd.DataFrame(linhas_filtro).to_csv(FILTROS_CSV, index=False)
    print(f"\n[signal_quality] resultado dos filtros salvo em {FILTROS_CSV}")


if __name__ == "__main__":
    main()
