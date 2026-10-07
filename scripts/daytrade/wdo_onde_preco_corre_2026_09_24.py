"""WDO@ -- ONDE O PRECO CORRE (descoberta honesta), 2026-09-24.

Ideia do dono: entrar, seguir o preco tick a tick, nunca sair no 1o tick;
quando o lucro passar do custo, proteger e deixar correr o mais longe
possivel, sair a MERCADO numa reversao real. As tres rodadas de HOJE
(`wdo_cor_minuto_saida_dinamica_2026_09_24.py`,
`wdo_oscilacao_lado_saida_dinamica_2026_09_24.py`,
`wdo_saida_deixa_correr_2026_09_24.py`) foram desenhadas para REFUTAR --
piso armado em +2 ticks na entrada+1 zerou 55-81% dos trades, e so' 3 sinais
de entrada foram tentados (MFE medio pos-entrada: 1,2-2,2 ticks). O dono
pediu, com razao, uma rodada de DESCOBERTA: onde o preco de fato corre, e so'
DEPOIS desenhar a saida em cima disso.

## Janela -- IS de 72 pregoes (nao os 18 dos scripts de hoje)

O split IS/OOS congelado do WDO F1 (`scripts/daytrade/
wdof1_deslize_alvo_is_oos_2026_09_08.py`, linha 83): **IS 72 pregoes,
2026-02-27..2026-06-12; OOS 51 pregoes, 2026-06-15..2026-08-25 -- INTACTO,
nunca se mexe**. O tick canonico (`data/raw_ticks/WDO_A_.parquet`) comeca
exatamente em 2026-02-27 e os 72 pregoes do IS tem tick COMPLETO (104k-399k
negocios/pregao, checado antes de escrever este script) -- e' a janela mais
longa disponivel que nao toca o OOS. Corte cronologico dentro do IS:
DESCOBERTA = 1os 48 pregoes (2/3), CONFIRMACAO = ultimos 24 (1/3). O OOS
congelado nunca e' lido por este script.

## Step 1 -- onde o preco corre (o entregavel principal)

Para CADA fechamento de barra M1 (momento candidato de entrada), OS DOIS
lados, sem look-ahead (toda feature usa so' dado ATE' o fechamento da
propria barra): resolve nos TICKS se o preco alcanca +R ticks favoraveis
ANTES do stop inicial (`max(2, round(1,5 x mediana21))`), R em {5,8},
dentro de uma janela de 30min (MFE/MAE tambem gravados nessa janela). Bucket
de ~13 features (tercil/quintil, calibrado em DESCOBERTA e aplicado igual em
CONFIRMACAO): hora do dia (30min), mediana21, expansao 10v21, distancia da
abertura, distancia do extremo do dia, rompimento de N barras (15/30/60),
volume vs mediana21, sinal do retorno de 1 e 10 barras, gap do dia, minutos
desde a abertura. Baseline = P(corrida>=R) incondicional por lado. Bucket so'
conta se o LIFT (vs baseline) replica em sinal E n>=100 na CONFIRMACAO. Nulo
de multiplos testes: shuffle da coluna `side` (shuffled-side null, pedido
explicito do coordenador) -- conta quantos buckets cruzariam o mesmo corte
de |lift| por puro acaso.

## Step 2 -- a saida com espaco pra respirar

Para as top-3 condicoes REPLICADAS (ou top-3 por descoberta, se nenhuma
replicar): grade de saida "deixa correr" generalizada (`resolver_saida_
grade`, mesma familia de `_saida_dinamica_tick_sim.
resolver_saida_deixa_correr`, mas com `arm_ticks`/`floor_ticks` agora
PARAMETROS em vez de constante de modulo -- duplicado de proposito, mesmo
motivo do proprio script de hoje: os tres scripts anteriores ja rodam sobre
aquelas funcoes e nao podem quebrar por uma mudanca de assinatura aqui):

  * `arm_floor_at` em {2,4,6} ticks de MFE
  * `floor` em {entrada+0, entrada+1}
  * `trail` em {1x,2x,3x} da mediana21 congelada na entrada, minimo 2 ticks
  * saida a mercado, 1 tick de deslize; achata no fim do pregao

Entrada via `EnterLimit` no preco de fechamento do sinal (fila de
`fidelidade.fidelidade_for("WDO@")`, TTL 5min, fill%/atraso reportados).
ESCOPO reduzido por disciplina de tempo de maquina (assuncao explicita, ver
o relatorio final): a grade de 18 celulas roda INTEIRA so' para a entrada
limite; a linha de referencia "teto a mercado" e o controle as-cegas (mesmos
instantes, lado invertido) rodam so' na MELHOR celula de cada condicao
(por R$/op em DESCOBERTA), replicada em CONFIRMACAO. Rodar as 18 celulas
tambem para controle-cego e teto multiplicaria o tempo de maquina por ~3 sem
mudar a pergunta que decide (a melhor geometria ja fica clara na grade
limite).

Capital SEMPRE R$375 (piso real WDO@, 2 lotes / reserva de seguranca --
`CLAUDE.md` "Capital inicial: sempre o minimo real do instrumento"). Tabela
padrao (`backtest/intraday/report.py`), `ProcessPoolExecutor` submit/
as_completed, `flush=True`, resultado impresso assim que fica pronto.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import _saida_dinamica_tick_sim as sim  # noqa: E402

TICK_SIZE = sim.TICK_SIZE
POINT_VALUE_BRL = sim.POINT_VALUE_BRL
FEE_ROUND_TRIP_BRL = sim.FEE_ROUND_TRIP_BRL
CAPITAL_REAL_BRL = sim.CAPITAL_REAL_BRL
MARGEM_1_CONTRATO_BRL = sim.MARGEM_1_CONTRATO_BRL

WINDOW_STEP1_MIN = 30  # janela de resolucao da corrida/MFE/MAE (Step 1)
R_TICKS = (5.0, 8.0)
R_SELECAO = 5.0  # R usado para ranquear/selecionar condicoes replicadas

#: Split IS/OOS congelado do WDO F1 -- ver docstring do modulo. NUNCA mexer.
IS_INICIO = dt.date(2026, 2, 27)
IS_FIM = dt.date(2026, 6, 12)
OOS_INICIO = dt.date(2026, 6, 15)  # so' para o assert de seguranca abaixo

N_SHUFFLES_NULO = 100
SEED_NULO = 20260924

#: Teto de CPU (ordem do dono, "rapido o quanto der") -- deixa 1 de fora para
#: o processo principal/SO nao competir com os workers. Este e' so' o teto de
#: CPU; o numero REALMENTE usado (`decidir_n_workers`) tambem respeita RAM
#: livre -- ver a nota de 2026-09-24 sobre o incidente de memoria abaixo.
N_WORKERS_CPU = max(1, (os.cpu_count() or 2) - 1)

#: RAM que fica de FORA da conta (SO + outras sessoes) e teto duro de RAM
#: total para os workers -- ordem do coordenador depois do incidente de
#: 2026-09-24: a 1a versao do Step 2 dava para cada worker uma copia
#: INTEIRA dos 72 pregoes (via `initializer` do `ProcessPoolExecutor`,
#: ~4GB/worker medido) -- 11 workers x 4GB ~ 44GB, derrubou a RAM livre a
#: perto de 0 e e' a causa mais provavel do travamento da maquina no mesmo
#: dia. A correcao de FUNDO e' arquitetural (Step 2 agora roda por PREGAO --
#: cada task recebe so' o pregao dela, nao a janela inteira, ver
#: `_roda_dia_step2`); isto aqui e' o CINTO DE SEGURANCA por cima: mede o
#: pico de RSS de verdade num pool pequeno antes de decidir quantos workers
#: o pool grande pode ter.
RAM_RESERVADA_GB = 4.0
RAM_TETO_TOTAL_WORKERS_GB = 10.0


def _peak_rss_mb() -> float:
    """Pico de working-set (RSS) do processo ATUAL, em MB. So' Windows
    (`K32GetProcessMemoryInfo` via ctypes -- sem dependencia nova, `psutil`
    nao esta' instalado neste venv e AGENTS.md pede para nao adicionar
    dependencia sem justificativa). `nan` se a chamada falhar por qualquer
    motivo (nunca derruba o worker por causa de uma medicao).

    Usa `K32GetProcessMemoryInfo` do `kernel32` (nao `psapi.dll` direto):
    `ctypes.windll.psapi.GetProcessMemoryInfo` sem `argtypes`/`restype`
    explicitos devolveu `ok=0` (falha silenciosa, `GetLastError=0`) na
    calibracao deste script -- o alias em `kernel32`, com `argtypes`
    declarado, e' a forma que de fato funciona (testado antes de subir)."""
    try:
        import ctypes

        class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_current_process = k32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        fn = k32.K32GetProcessMemoryInfo
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS), ctypes.c_ulong]
        fn.restype = ctypes.c_int

        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
        h = get_current_process()
        ok = fn(h, ctypes.byref(counters), counters.cb)
        if ok:
            return counters.PeakWorkingSetSize / 1e6
    except Exception:
        pass
    return float("nan")


def _free_ram_gb() -> float:
    """RAM fisica DISPONIVEL agora, em GB (Windows, `GlobalMemoryStatusEx`
    via ctypes -- mesma justificativa de `_peak_rss_mb`)."""
    try:
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullAvailPhys / 1e9
    except Exception:
        return float("nan")


def decidir_n_workers(peak_worker_gb: float, teto_cpu: int = N_WORKERS_CPU) -> int:
    """`min(cpu-1, floor((RAM_livre - reserva) / pico_medido_por_worker))`,
    com teto duro de `RAM_TETO_TOTAL_WORKERS_GB` no total. `peak_worker_gb`
    vem de uma MEDICAO real (pool pequeno de calibracao), nunca de um
    chute -- foi exatamente um numero chutado (a suposicao implicita de que
    cada worker custa pouco) que causou o incidente de RAM de 2026-09-24."""
    livre = _free_ram_gb()
    if not np.isfinite(livre) or not np.isfinite(peak_worker_gb) or peak_worker_gb <= 0:
        # Medicao falhou -- nao adivinha, cai para o minimo seguro.
        return 1
    por_ram = int((livre - RAM_RESERVADA_GB) // peak_worker_gb)
    por_teto_total = int(RAM_TETO_TOTAL_WORKERS_GB // peak_worker_gb)
    return max(1, min(teto_cpu, por_ram, por_teto_total))


def _print_eta(nome: str, done: int, total: int, t_inicio: float) -> None:
    """ETA por regra de tres simples sobre o que ja terminou -- chamado a
    cada conclusao dos pools de Step 1/Step 2 para o dono ver progresso sem
    esperar a rodada inteira falar (mesma regra de `sweep_copa.py`)."""
    if done == 0 or done % max(1, total // 10) != 0:
        return
    elapsed = time.perf_counter() - t_inicio
    taxa = elapsed / done
    restante = taxa * (total - done)
    print(f"  [{nome}] progresso {done}/{total} -- decorrido {elapsed:.0f}s -- "
          f"ETA restante ~{restante:.0f}s (~{restante/60:.1f}min)", flush=True)


# ---------------------------------------------------------------------------
# Carregamento + features (sem look-ahead: tudo usa so' dado ATE a barra i)
# ---------------------------------------------------------------------------

def carregar_dias_is() -> list[dt.date]:
    df = pd.read_parquet(RAIZ / "data" / "raw_intraday" / "WDO_A_.parquet", columns=["close"])
    df.index = df.index.tz_convert(sim.TZ)
    dias = sorted(set(df.loc[(df.index.date >= IS_INICIO) & (df.index.date <= IS_FIM)].index.date))
    if len(dias) != 72:
        raise AssertionError(
            f"esperava 72 pregoes no IS congelado do WDO F1 ({IS_INICIO}..{IS_FIM}), "
            f"achei {len(dias)} -- confira profiles.py/wdof1_deslize_alvo_is_oos antes de seguir."
        )
    if dias[-1] >= OOS_INICIO:
        raise AssertionError(f"vazou para dentro do OOS congelado ({OOS_INICIO}+) -- NAO seguir.")
    return dias


def _time_bucket30(ts: pd.Timestamp) -> str:
    minutos = ts.hour * 60 + ts.minute
    ini = (minutos // 30) * 30
    h, m = divmod(ini, 60)
    return f"{h:02d}:{m:02d}"


def _sign(x: float) -> str | None:
    if pd.isna(x):
        return None
    if x > 0:
        return "up"
    if x < 0:
        return "down"
    return "flat"


def _breakout(close: float, hi: float, lo: float) -> str | None:
    if pd.isna(hi) or pd.isna(lo):
        return None
    if close > hi:
        return "up"
    if close < lo:
        return "down"
    return "none"


def carregar_m1_features(dias: list[dt.date]) -> dict[dt.date, pd.DataFrame]:
    """M1 nativo + TODAS as features cruas (continuas) de Step 1/Step 2, uma
    unica passada -- fonte unica para as duas etapas (evita features
    recalculadas duas vezes divergirem)."""
    df = pd.read_parquet(RAIZ / "data" / "raw_intraday" / "WDO_A_.parquet",
                          columns=["open", "high", "low", "close", "real_volume"])
    df.index = df.index.tz_convert(sim.TZ)
    todos_os_dias = sorted(set(df.index.date))

    out: dict[dt.date, pd.DataFrame] = {}
    for dia in dias:
        sub = df.loc[df.index.date == dia]
        sub = sub.between_time(sim.SESSION_START, sim.FLATTEN_CUTOFF, inclusive="left")
        if sub.empty:
            continue
        sub = sub.copy()
        sub["range_ticks"] = (sub["high"] - sub["low"]) / TICK_SIZE
        sub["median21_ticks"] = sub["range_ticks"].rolling(sim.MEDIAN_LOOKBACK).median()
        sub["media10_ticks"] = sub["range_ticks"].rolling(10).mean()
        sub["expansion_ratio"] = sub["media10_ticks"] / sub["median21_ticks"]
        sub["vol_median21"] = sub["real_volume"].rolling(sim.MEDIAN_LOOKBACK).median()
        sub["volume_ratio"] = sub["real_volume"] / sub["vol_median21"]
        sub["fecha_ts"] = sub.index + pd.Timedelta(minutes=1)
        sub["session_open"] = float(sub["open"].iloc[0])
        sub["day_high_so_far"] = sub["high"].cummax()
        sub["day_low_so_far"] = sub["low"].cummin()
        sub["dist_open_ticks"] = (sub["close"] - sub["session_open"]).abs() / TICK_SIZE
        sub["dist_extreme_ticks"] = np.minimum(sub["day_high_so_far"] - sub["close"],
                                                sub["close"] - sub["day_low_so_far"]) / TICK_SIZE
        sub["ret1_ticks"] = sub["close"].diff()
        sub["ret10_ticks"] = sub["close"].diff(10)
        sub["ret1_sign"] = sub["ret1_ticks"].apply(_sign)
        sub["ret10_sign"] = sub["ret10_ticks"].apply(_sign)
        for n in (15, 30, 60):
            hi = sub["close"].shift(1).rolling(n).max()
            lo = sub["close"].shift(1).rolling(n).min()
            sub[f"breakout{n}"] = [
                _breakout(c, h, l) for c, h, l in zip(sub["close"], hi, lo)
            ]
        sub["minutes_since_open"] = (sub.index - sub.index[0]).total_seconds() / 60.0
        sub["time_bucket30"] = [_time_bucket30(ts) for ts in sub["fecha_ts"]]

        idx_all = todos_os_dias.index(dia)
        gap_ticks = float("nan")
        if idx_all > 0:
            prev_dia = todos_os_dias[idx_all - 1]
            prev_sub = df.loc[df.index.date == prev_dia]
            if not prev_sub.empty:
                gap_ticks = (float(sub["session_open"].iloc[0]) - float(prev_sub["close"].iloc[-1])) / TICK_SIZE
        sub["gap_ticks"] = gap_ticks
        out[dia] = sub
    return out


def carregar_ticks_rapido(dias: list[dt.date]) -> dict[dt.date, pd.DataFrame]:
    """Substitui `_saida_dinamica_tick_sim.carregar_ticks` para janelas GRANDES
    (72 pregoes -- os scripts de hoje usavam 18). Duas correcoes de
    performance, nao so' de estilo:

    1. `columns=["last","volume"]` no `read_parquet` -- o parquet tem 6
       colunas (bid/ask/last/volume/volume_real/flags); ler so' as 2
       necessarias evita decodificar as outras 4 (medido: ~0,6s p/ 21,5M
       linhas contra 65-100s lendo tudo).
    2. `df.index.date` calculado UMA VEZ e agrupado (`groupby`), nao
       recalculado a cada pregao. `sim.carregar_ticks` faz `t.loc[t.index.
       date==dia]` DENTRO do loop `for dia in dias` -- cada comparacao
       reconverte o DatetimeIndex inteiro (21,5M timestamps) em objetos
       `datetime.date` do zero. Para 18 pregoes (F1) isso e' 18 passadas;
       para os 72 do IS e' 72 passadas sobre 21,5M linhas cada -- e' essa
       segunda causa, nao I/O de disco, que fez o Step 2 da 1a tentativa
       deste script ficar horas parado (72 dias x ~6,5s/passada, x8
       processos brigando por CPU ao mesmo tempo)."""
    path = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
    df = pd.read_parquet(path, columns=["last", "volume"])
    df.index = df.index.tz_convert(sim.TZ)
    datas = df.index.date  # UMA passada
    dias_set = set(dias)
    out: dict[dt.date, pd.DataFrame] = {}
    for dia, sub in df.groupby(datas, sort=False):
        if dia not in dias_set:
            continue
        sub = sub.between_time(sim.SESSION_START, sim.FLATTEN_CUTOFF, inclusive="left")
        if sub.empty:
            continue
        out[dia] = sub
    return out


# ---------------------------------------------------------------------------
# Step 1 -- resolucao do "onde corre" por barra/lado (worker por PREGAO)
# ---------------------------------------------------------------------------

FEATURES_CONTINUAS = ("median21_ticks", "expansion_ratio", "dist_open_ticks", "dist_extreme_ticks",
                       "volume_ratio", "gap_ticks", "minutes_since_open")
FEATURES_CATEGORICAS = ("time_bucket30", "ret1_sign", "ret10_sign", "breakout15", "breakout30", "breakout60")
TODAS_FEATURES = FEATURES_CONTINUAS + FEATURES_CATEGORICAS


def _resolver_evento(ticks_ts: np.ndarray, ticks_px: np.ndarray, start_idx: int, end_idx: int,
                      side: str, fill_price: float, stop_ticks: float) -> tuple | None:
    px = ticks_px[start_idx + 1:end_idx]
    if len(px) == 0:
        return None
    if side == "long":
        favor = (px - fill_price) / TICK_SIZE
        bate_stop = px <= (fill_price - stop_ticks * TICK_SIZE)
    else:
        favor = (fill_price - px) / TICK_SIZE
        bate_stop = px >= (fill_price + stop_ticks * TICK_SIZE)
    idx_stop = int(np.argmax(bate_stop)) if bate_stop.any() else None
    mfe = float(favor.max())
    mae = float(max(0.0, -float(favor.min())))
    resultados = {}
    for r in R_TICKS:
        bate_r = favor >= r
        idx_r = int(np.argmax(bate_r)) if bate_r.any() else None
        if idx_r is not None and (idx_stop is None or idx_r <= idx_stop):
            outcome = "target"
            ev = r * TICK_SIZE * POINT_VALUE_BRL - FEE_ROUND_TRIP_BRL
        elif idx_stop is not None:
            outcome = "stop"
            ev = -stop_ticks * TICK_SIZE * POINT_VALUE_BRL - FEE_ROUND_TRIP_BRL
        else:
            outcome = "timeout"
            ev = float(favor[-1]) * TICK_SIZE * POINT_VALUE_BRL - FEE_ROUND_TRIP_BRL
        resultados[r] = (outcome, ev)
    return mfe, mae, resultados


def eventos_dia(dia: dt.date, m1_dia: pd.DataFrame, ticks_dia: pd.DataFrame) -> pd.DataFrame:
    ticks_ts = ticks_dia.index.values
    ticks_px = ticks_dia["last"].values.astype(float)
    cutoff_ts = pd.Timestamp.combine(dia, sim.FLATTEN_CUTOFF).tz_localize(sim.TZ).to_datetime64()

    linhas = []
    for i in range(len(m1_dia)):
        bar = m1_dia.iloc[i]
        median_ticks = bar["median21_ticks"]
        if pd.isna(median_ticks) or pd.isna(bar["media10_ticks"]) or pd.isna(bar["vol_median21"]):
            continue
        fecha_ts = bar["fecha_ts"]
        fecha_np = fecha_ts.to_datetime64()
        fill_idx = int(np.searchsorted(ticks_ts, fecha_np, side="left"))
        if fill_idx >= len(ticks_ts) or ticks_ts[fill_idx] >= cutoff_ts:
            continue
        fill_price = float(ticks_px[fill_idx])
        window_end_np = min((fecha_ts + pd.Timedelta(minutes=WINDOW_STEP1_MIN)).to_datetime64(), cutoff_ts)
        end_idx = int(np.searchsorted(ticks_ts, window_end_np, side="left"))
        if end_idx <= fill_idx + 1:
            continue
        stop_ticks = max(2.0, round(1.5 * float(median_ticks)))

        feats = {f: bar[f] for f in TODAS_FEATURES}
        for side in ("long", "short"):
            res = _resolver_evento(ticks_ts, ticks_px, fill_idx, end_idx, side, fill_price, stop_ticks)
            if res is None:
                continue
            mfe, mae, outcomes = res
            linha = dict(feats, dia=dia, ts=fecha_ts, side=side, mfe_ticks=mfe, mae_ticks=mae,
                         stop_ticks=stop_ticks)
            for r, (outcome, ev) in outcomes.items():
                linha[f"outcome_R{int(r)}"] = outcome
                linha[f"ev_R{int(r)}"] = ev
            linhas.append(linha)
    return pd.DataFrame(linhas)


def _worker_eventos_dia(args):
    idx, total, dia, m1_dia, ticks_dia = args
    t0 = time.perf_counter()
    df = eventos_dia(dia, m1_dia, ticks_dia)
    peak_rss = _peak_rss_mb()
    print(f"[step1] [{idx}/{total}] {dia} -- {len(df)} eventos em {time.perf_counter()-t0:.1f}s "
          f"(RSS pico do worker: {peak_rss:.0f}MB)", flush=True)
    return dia, df, peak_rss


# ---------------------------------------------------------------------------
# Bucketizacao -- edges SEMPRE calibrados em DESCOBERTA, aplicados nos dois
# ---------------------------------------------------------------------------

@dataclass
class Edges:
    continuas: dict[str, np.ndarray] = field(default_factory=dict)


def calibrar_edges(eventos_descoberta: pd.DataFrame, n_buckets: int = 3) -> Edges:
    edges = Edges()
    for feat in FEATURES_CONTINUAS:
        vals = eventos_descoberta[feat].dropna()
        try:
            _, bins = pd.qcut(vals, n_buckets, retbins=True, duplicates="drop")
        except ValueError:
            bins = np.array([vals.min(), vals.max()])
        bins = bins.copy()
        bins[0], bins[-1] = -np.inf, np.inf
        edges.continuas[feat] = bins
    return edges


def aplicar_buckets(eventos: pd.DataFrame, edges: Edges) -> pd.DataFrame:
    eventos = eventos.copy()
    for feat in FEATURES_CONTINUAS:
        bins = edges.continuas[feat]
        rotulos = [f"{feat}[{i+1}/{len(bins)-1}]" for i in range(len(bins) - 1)]
        eventos[f"{feat}__bucket"] = pd.cut(eventos[feat], bins=bins, labels=rotulos, include_lowest=True)
    for feat in FEATURES_CATEGORICAS:
        eventos[f"{feat}__bucket"] = eventos[feat]
    return eventos


def colunas_bucket() -> list[str]:
    return [f"{f}__bucket" for f in TODAS_FEATURES]


# ---------------------------------------------------------------------------
# Estatisticas por bucket + replicacao + nulo shuffled-side
# ---------------------------------------------------------------------------

def stats_por_bucket(eventos: pd.DataFrame, r: float) -> pd.DataFrame:
    """`n`, `P(target)`, `ev_medio` por (feature, bucket, side); + baseline
    por side (feature='__baseline__')."""
    col_outcome, col_ev = f"outcome_R{int(r)}", f"ev_R{int(r)}"
    linhas = []
    for side, sub_side in eventos.groupby("side"):
        base_p = float((sub_side[col_outcome] == "target").mean())
        base_ev = float(sub_side[col_ev].mean())
        linhas.append(dict(feature="__baseline__", bucket="__baseline__", side=side,
                            n=len(sub_side), p_target=base_p, ev_medio=base_ev, lift=0.0))
        for feat in TODAS_FEATURES:
            col = f"{feat}__bucket"
            for bucket, sub in sub_side.groupby(col, observed=True):
                if len(sub) == 0:
                    continue
                p = float((sub[col_outcome] == "target").mean())
                ev = float(sub[col_ev].mean())
                linhas.append(dict(feature=feat, bucket=str(bucket), side=side, n=len(sub),
                                    p_target=p, ev_medio=ev, lift=p - base_p))
    return pd.DataFrame(linhas)


def nulo_shuffled_side(eventos_desc: pd.DataFrame, r: float, limiar_lift: float,
                        n_shuffles: int = N_SHUFFLES_NULO, seed: int = SEED_NULO) -> list[int]:
    """Embaralha a coluna `side` (nulo pedido pelo coordenador: "shuffled-side
    null") e conta, a cada shuffle, quantos buckets cruzam o MESMO corte de
    |lift| usado nos buckets reais -- estimativa de quantos passariam so' por
    acaso, dado o numero de buckets testados."""
    rng = np.random.default_rng(seed)
    col_outcome = f"outcome_R{int(r)}"
    alvo = (eventos_desc[col_outcome] == "target").to_numpy()
    side_original = eventos_desc["side"].to_numpy()
    cols_bucket = colunas_bucket()
    bucket_vals = {c: eventos_desc[c].to_numpy() for c in cols_bucket}
    contagens = []
    for _ in range(n_shuffles):
        side_shuf = rng.permutation(side_original)
        n_pass = 0
        for lado in ("long", "short"):
            mask_lado = side_shuf == lado
            base_p = alvo[mask_lado].mean() if mask_lado.any() else float("nan")
            for c in cols_bucket:
                vals = bucket_vals[c][mask_lado]
                alvo_lado = alvo[mask_lado]
                for bucket in pd.unique(vals[~pd.isna(vals)]):
                    m = vals == bucket
                    if m.sum() < 30:
                        continue
                    p = alvo_lado[m].mean()
                    if abs(p - base_p) >= limiar_lift:
                        n_pass += 1
        contagens.append(n_pass)
    return contagens


# ---------------------------------------------------------------------------
# Step 2 -- saida "deixa correr" generalizada (arm/floor/trail em grade)
# ---------------------------------------------------------------------------

ARM_LEVELS = (2.0, 4.0, 6.0)
FLOOR_LEVELS = (0.0, 1.0)
TRAIL_MULTS = (1.0, 2.0, 3.0)


@dataclass
class SaidaGrade:
    exit_price: float
    exit_ts: pd.Timestamp
    exit_detail: str
    ativou: bool
    mfe_ticks: float
    capturado_ticks: float


def resolver_saida_grade(ticks_ts: np.ndarray, ticks_px: np.ndarray, start_idx: int, end_idx_cap: int,
                          side: str, fill_price: float, stop_ticks_inicial: float, arm_ticks: float,
                          floor_ticks: float, trail_ticks: float) -> SaidaGrade:
    px = ticks_px[start_idx + 1:end_idx_cap]
    ts = ticks_ts[start_idx + 1:end_idx_cap]
    if len(px) == 0:
        exit_price = sim._aplica_slippage(fill_price, side, saida=True)
        return SaidaGrade(exit_price, sim._ts_tz(ticks_ts[start_idx]), "forced_flatten", False, 0.0, 0.0)

    if side == "long":
        favor = (px - fill_price) / TICK_SIZE
        stop_inicial_nivel = fill_price - stop_ticks_inicial * TICK_SIZE
        floor_nivel = fill_price + floor_ticks * TICK_SIZE
        bate_inicial = px <= stop_inicial_nivel
    else:
        favor = (fill_price - px) / TICK_SIZE
        stop_inicial_nivel = fill_price + stop_ticks_inicial * TICK_SIZE
        floor_nivel = fill_price - floor_ticks * TICK_SIZE
        bate_inicial = px >= stop_inicial_nivel

    ativa_mask = favor >= arm_ticks
    idx_inicial = int(np.argmax(bate_inicial)) if bate_inicial.any() else None
    idx_ativacao = int(np.argmax(ativa_mask)) if ativa_mask.any() else None
    ativou = idx_ativacao is not None and (idx_inicial is None or idx_inicial > idx_ativacao)

    if not ativou:
        if idx_inicial is not None:
            exit_idx_abs, detail = idx_inicial, "inicial"
        else:
            exit_idx_abs, detail = len(px) - 1, "forced_flatten"
    else:
        sub_px = px[idx_ativacao:]
        if side == "long":
            extremo = np.maximum.accumulate(sub_px)
            nivel = np.maximum(floor_nivel, extremo - trail_ticks * TICK_SIZE)
            bate = sub_px <= nivel
        else:
            extremo = np.minimum.accumulate(sub_px)
            nivel = np.minimum(floor_nivel, extremo + trail_ticks * TICK_SIZE)
            bate = sub_px >= nivel
        idx_rel = int(np.argmax(bate)) if bate.any() else None
        if idx_rel is not None:
            exit_idx_abs = idx_ativacao + idx_rel
            detail = "piso" if abs(float(nivel[idx_rel]) - floor_nivel) < 1e-9 else "trailing"
        else:
            exit_idx_abs, detail = len(px) - 1, "forced_flatten"

    exit_px_raw = float(px[exit_idx_abs])
    exit_price = sim._aplica_slippage(exit_px_raw, side, saida=True)
    mfe_ticks = float(favor[:exit_idx_abs + 1].max())
    capturado_ticks = float(favor[exit_idx_abs])
    return SaidaGrade(exit_price, sim._ts_tz(ts[exit_idx_abs]), detail, ativou, mfe_ticks, capturado_ticks)


@dataclass
class DiagnosticoTrade:
    ativou: bool
    mfe_ticks: float
    capturado_ticks: float
    holding_min: float


@dataclass
class ResultadoCelula:
    trades: list = field(default_factory=list)
    diagnosticos: list = field(default_factory=list)
    tentativas_limite: list = field(default_factory=list)
    dias_com_trade: set = field(default_factory=set)


def simular_grade(dias: list[dt.date], m1_por_dia: dict, ticks_por_dia: dict, sinais_por_dia: dict,
                   arm_ticks: float, floor_ticks: float, trail_mult: float, modo_entrada: str,
                   queue_ahead_qty: float, capital_inicial: float | None) -> ResultadoCelula:
    from backtest.intraday.machine import IntradayTrade
    from core.models import IntradayExitReason

    resultado = ResultadoCelula()
    capital = capital_inicial

    for dia in dias:
        m1 = m1_por_dia.get(dia)
        ticks = ticks_por_dia.get(dia)
        if m1 is None or ticks is None or ticks.empty:
            continue
        sinais = sinais_por_dia.get(dia)
        if sinais is None:
            continue

        ticks_ts = ticks.index.values
        ticks_px = ticks["last"].values.astype(float)
        ticks_vol = ticks["volume"].values.astype(float)
        cutoff_ts = pd.Timestamp.combine(dia, sim.FLATTEN_CUTOFF).tz_localize(sim.TZ).to_datetime64()
        cutoff_idx = int(np.searchsorted(ticks_ts, cutoff_ts, side="left"))

        n = len(m1)
        i = 0
        while i < n:
            side = sinais.iloc[i]
            if side is None or (isinstance(side, float) and pd.isna(side)):
                i += 1
                continue
            if capital is not None and capital < MARGEM_1_CONTRATO_BRL:
                i += 1
                continue

            bar = m1.iloc[i]
            median_ticks = bar["median21_ticks"]
            if pd.isna(median_ticks):
                i += 1
                continue
            fecha_ts = bar["fecha_ts"]
            stop_ticks_inicial = max(2.0, round(1.5 * float(median_ticks)))
            trail_ticks = max(2.0, round(trail_mult * float(median_ticks)))

            fecha_ts_np = fecha_ts.to_datetime64()
            if modo_entrada == "teto":
                fill_idx = int(np.searchsorted(ticks_ts, fecha_ts_np, side="left"))
                if fill_idx >= len(ticks_ts) or ticks_ts[fill_idx] >= cutoff_ts:
                    i += 1
                    continue
                fill_price = sim._aplica_slippage(float(ticks_px[fill_idx]), side, saida=False)
                fill_ts = sim._ts_tz(ticks_ts[fill_idx])
                start_idx = fill_idx
            elif modo_entrada == "limite":
                janela_ini = int(np.searchsorted(ticks_ts, fecha_ts_np, side="left"))
                if janela_ini >= len(ticks_ts):
                    resultado.tentativas_limite.append(sim.TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                ordem_preco = float(ticks_px[janela_ini])
                ttl_ts = (fecha_ts + pd.Timedelta(minutes=sim.ENTRY_LIMIT_TTL_MIN)).to_datetime64()
                janela_fim = int(np.searchsorted(ticks_ts, min(ttl_ts, cutoff_ts), side="left"))
                if janela_ini >= janela_fim:
                    resultado.tentativas_limite.append(sim.TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                px_janela = ticks_px[janela_ini:janela_fim]
                vol_janela = ticks_vol[janela_ini:janela_fim]
                no_preco = np.isclose(px_janela, ordem_preco, atol=1e-9)
                vol_acumulado = np.cumsum(np.where(no_preco, vol_janela, 0.0))
                preenche = no_preco & (vol_acumulado >= queue_ahead_qty)
                if not preenche.any():
                    resultado.tentativas_limite.append(sim.TentativaEntradaLimite(False, None))
                    i += 1
                    continue
                idx_rel = int(np.argmax(preenche))
                fill_idx = janela_ini + idx_rel
                fill_price = ordem_preco
                fill_ts = sim._ts_tz(ticks_ts[fill_idx])
                atraso_min = (fill_ts - fecha_ts).total_seconds() / 60.0
                resultado.tentativas_limite.append(sim.TentativaEntradaLimite(True, atraso_min))
                start_idx = fill_idx
            else:
                raise ValueError(f"modo_entrada desconhecido: {modo_entrada!r}")

            saida = resolver_saida_grade(ticks_ts, ticks_px, start_idx, cutoff_idx, side, fill_price,
                                          stop_ticks_inicial, arm_ticks, floor_ticks, trail_ticks)

            razao = (IntradayExitReason.FORCED_FLATTEN if saida.exit_detail == "forced_flatten"
                     else IntradayExitReason.STOP)
            trade = IntradayTrade(
                symbol=sim.SYMBOL, strategy_name="onde_preco_corre", strategy_version="2026-09-24",
                side=side, entry_ts=fill_ts, entry_price=fill_price,
                exit_ts=saida.exit_ts, exit_price=saida.exit_price, quantity=1,
                exit_reason=razao, point_value_brl=POINT_VALUE_BRL,
                capital_base=capital_inicial or CAPITAL_REAL_BRL, fees_total=FEE_ROUND_TRIP_BRL,
                slippage_total=sim.SLIPPAGE_TICKS * TICK_SIZE * POINT_VALUE_BRL, exit_detail=saida.exit_detail,
            )
            resultado.trades.append(trade)
            resultado.dias_com_trade.add(dia)
            holding_min = (saida.exit_ts - fill_ts).total_seconds() / 60.0
            resultado.diagnosticos.append(DiagnosticoTrade(saida.ativou, saida.mfe_ticks,
                                                             saida.capturado_ticks, holding_min))
            if capital is not None:
                capital += trade.pnl_brl

            prox = m1.index[m1["fecha_ts"] > saida.exit_ts]
            if len(prox) == 0:
                break
            i = m1.index.get_loc(prox[0])

    return resultado


def estatisticas(trades: list) -> dict:
    pnls = np.array([t.pnl_brl for t in trades], dtype=float)
    n = len(pnls)
    if n == 0:
        return dict(n=0, media=float("nan"), desvio=float("nan"), ic95=(float("nan"), float("nan")),
                    win_pct=float("nan"), breakeven_empirico=float("nan"))
    media = float(pnls.mean())
    desvio = float(pnls.std(ddof=1)) if n > 1 else 0.0
    se = desvio / (n ** 0.5) if n > 1 else 0.0
    ic95 = (media - 1.96 * se, media + 1.96 * se)
    vit, perd = pnls[pnls > 0], pnls[pnls < 0]
    win_pct = 100.0 * len(vit) / n
    ganho_medio = float(vit.mean()) if len(vit) else 0.0
    perda_media = float(-perd.mean()) if len(perd) else 0.0
    breakeven = (perda_media / (ganho_medio + perda_media)) * 100.0 if (ganho_medio + perda_media) > 0 else float("nan")
    return dict(n=n, media=media, desvio=desvio, ic95=ic95, win_pct=win_pct, breakeven_empirico=breakeven)


def monta_resultado(trades: list, capital_inicial: float):
    from backtest.metrics import max_drawdown

    @dataclass
    class ResultadoFake:
        trades: list
        equity_curve: pd.Series
        metrics: dict
        wiped_out_at = None
        sessoes_puladas_por_capital: list = field(default_factory=list)
        deslize_alvo_ticks: float = 0.0
        fila_entrada_qty: float = 0.0
        fila_saida_qty: float = 0.0
        fila_calibrada: bool | None = None

    trades_ordenados = sorted(trades, key=lambda t: t.exit_ts)
    valores, idx = [], []
    acumulado = capital_inicial
    for t in trades_ordenados:
        acumulado += t.pnl_brl
        valores.append(acumulado)
        idx.append(t.exit_ts)
    if not idx:
        equity = pd.Series([capital_inicial], index=[pd.Timestamp.now(tz=sim.TZ)])
    else:
        equity = pd.Series(valores, index=pd.DatetimeIndex(idx))
    metrics = {"max_drawdown": max_drawdown(equity) if len(equity) > 1 else 0.0}
    return ResultadoFake(trades=trades_ordenados, equity_curve=equity, metrics=metrics)


# ---------------------------------------------------------------------------
# Sinal por condicao (feature=bucket & side) e controle as-cegas
# ---------------------------------------------------------------------------

def sinal_condicao(m1_por_dia: dict, dias: list[dt.date], feature: str, bucket_label: str,
                    side: str, edges: Edges, inverter: bool = False) -> dict:
    lado_efetivo = ("short" if side == "long" else "long") if inverter else side
    sinais = {}
    for dia in dias:
        m1 = m1_por_dia.get(dia)
        if m1 is None:
            continue
        if feature in FEATURES_CONTINUAS:
            bins = edges.continuas[feature]
            rotulos = [f"{feature}[{i+1}/{len(bins)-1}]" for i in range(len(bins) - 1)]
            bucket_vals = pd.cut(m1[feature], bins=bins, labels=rotulos, include_lowest=True).astype(object)
        else:
            bucket_vals = m1[feature]
        elegivel = (bucket_vals == bucket_label) & m1["median21_ticks"].notna()
        s = pd.Series(None, index=m1.index, dtype=object)
        s[elegivel.fillna(False)] = lado_efetivo
        sinais[dia] = s
    return sinais


# ---------------------------------------------------------------------------
# Rodada de UMA celula da grade Step 2 (usada pelo pool)
# ---------------------------------------------------------------------------

EXTRAS_STEP2 = ("R$/op", "IC95 R$/op", "win%", "breakeven%", "ativou%", "MFE tk med", "capt tk med",
                "hold min", "%inicial", "%piso", "%trail", "%flat", "fill%", "atraso min", "preg s/trade")


def aplicar_portao_capital(trades: list, capital_inicial: float, margem: float) -> tuple[list, set]:
    """Reconstroi o efeito do PORTAO de capital (so' abre com caixa >=
    margem, ver `simular_grade`) a PARTIR da lista de trades SEM portao
    (`capital_inicial=None`), em vez de simular DUAS vezes.

    Isto so' e' correto porque cada trade e' inteiramente contido num unico
    PREGAO (day trade nunca carrega posicao overnight -- `FLATTEN_CUTOFF`
    garante) e porque, dentro de um pregao, `simular_grade` ja' pula para a
    barra seguinte ao FECHAMENTO de cada trade antes de considerar o
    proximo sinal -- ou seja, a lista `trades` SEM portao, ordenada por
    `entry_ts`, e' EXATAMENTE a mesma sequencia de oportunidades que uma
    rodada com portao veria (o portao so' pode ACEITAR ou PULAR cada
    oportunidade nessa mesma ordem, nunca criar uma nova). Caminha essa
    sequencia aplicando o MESMO teste (`capital < margem` antes de aceitar,
    capital so' anda quando um trade ACEITO fecha) -- equivalente ao portao
    bar-a-bar original, so' que num passe barato em vez de uma 2a
    simulacao tick-a-tick."""
    trades_ordenados = sorted(trades, key=lambda t: t.entry_ts)
    aceitos: list = []
    capital = capital_inicial
    dias_com_trade: set = set()
    for t in trades_ordenados:
        if capital < margem:
            continue
        aceitos.append(t)
        dias_com_trade.add(t.entry_ts.date())
        capital += t.pnl_brl
    return aceitos, dias_com_trade


def _linha_step2(rotulo: str, trades: list, diagnosticos: list, tentativas: list, dias_janela: list,
                  modo: str):
    from backtest.intraday.report import linha_de_resultado, num_br

    aceitos, dias_com_trade = aplicar_portao_capital(trades, CAPITAL_REAL_BRL, MARGEM_1_CONTRATO_BRL)
    resultado = monta_resultado(aceitos, CAPITAL_REAL_BRL)
    stats = estatisticas(trades)  # "livre" = todos os trades, SEM portao de capital
    n = len(trades)
    ativou_pct = 100.0 * sum(d.ativou for d in diagnosticos) / n if n else float("nan")
    mfe_med = float(np.mean([d.mfe_ticks for d in diagnosticos])) if n else float("nan")
    capt_med = float(np.mean([d.capturado_ticks for d in diagnosticos])) if n else float("nan")
    hold_med = float(np.mean([d.holding_min for d in diagnosticos])) if n else float("nan")
    contagem = Counter(t.exit_detail for t in trades)
    pct = lambda chave: 100.0 * contagem.get(chave, 0) / n if n else float("nan")  # noqa: E731

    if modo == "limite":
        fill_pct = 100.0 * sum(1 for t in tentativas if t.preenchida) / len(tentativas) if tentativas else float("nan")
        atrasos = [t.atraso_min for t in tentativas if t.preenchida]
        atraso_med = float(pd.Series(atrasos).median()) if atrasos else float("nan")
        fill_txt, atraso_txt = f"{num_br(fill_pct, 1)}%", num_br(atraso_med, 2)
    else:
        fill_txt, atraso_txt = "—", "—"

    extras = {
        "R$/op": num_br(stats["media"], 2),
        "IC95 R$/op": f"[{num_br(stats['ic95'][0], 2)};{num_br(stats['ic95'][1], 2)}]",
        "win%": f"{num_br(stats['win_pct'], 1)}%",
        "breakeven%": f"{num_br(stats['breakeven_empirico'], 1)}%",
        "ativou%": f"{num_br(ativou_pct, 1)}%",
        "MFE tk med": num_br(mfe_med, 2),
        "capt tk med": num_br(capt_med, 2),
        "hold min": num_br(hold_med, 2),
        "%inicial": f"{num_br(pct('inicial'), 1)}%",
        "%piso": f"{num_br(pct('piso'), 1)}%",
        "%trail": f"{num_br(pct('trailing'), 1)}%",
        "%flat": f"{num_br(pct('forced_flatten'), 1)}%",
        "fill%": fill_txt,
        "atraso min": atraso_txt,
        "preg s/trade": str(len(dias_janela) - len(dias_com_trade)),
    }
    item = linha_de_resultado(rotulo, resultado, CAPITAL_REAL_BRL, capital_nocional=False, extras=extras)
    return item, stats


# ---------------------------------------------------------------------------
# Step 2, worker POR PREGAO -- correcao do incidente de RAM de 2026-09-24
# ---------------------------------------------------------------------------
#
# A 1a versao desta secao dava a CADA worker uma copia inteira dos 72
# pregoes (via `initializer` do `ProcessPoolExecutor`) e deixava essa copia
# viva pelo tempo de vida do processo -- medido em ~4GB/worker. Com 11
# workers isso e' ~44GB, derrubou a RAM livre da maquina perto de zero e e'
# a causa mais provavel do travamento relatado no mesmo dia. A correcao NAO
# e' so' diminuir o numero de workers -- e' ARQUITETURAL: cada trade de day
# trade cabe inteiro DENTRO de um pregao (nunca carrega posicao overnight),
# entao a unidade de trabalho de Step 2 pode ser "um pregao", nao "uma
# janela inteira". Cada task agora recebe SO' o pregao dela (m1 + ticks de
# 1 dia, poucos MB) e calcula TODAS as combinacoes condicao x celula de
# saida (`unidades`) PARA AQUELE PREGAO, sempre com `capital_inicial=None`
# (sem portao -- o portao e' reconstruido DEPOIS, no processo principal, por
# `aplicar_portao_capital`, sobre a lista de trades ja' agregada -- ver a
# docstring de la' para a prova de que os dois caminhos dao o MESMO
# resultado). O processo principal agrega por pregao (na ordem cronologica
# de `dias_desc`/`dias_conf`) em vez de cada worker manter uma janela
# inteira em memoria.


def _roda_dia_step2(args: tuple) -> tuple:
    janela_nome, dia, m1_dia, ticks_dia, unidades, edges, queue_ahead_qty = args
    m1_por_dia_1 = {dia: m1_dia}
    ticks_por_dia_1 = {dia: ticks_dia}
    resultados: dict = {}
    cache_sinal: dict = {}
    for u in unidades:
        chave_sinal = (u["feature"], u["bucket"], u["side"], u["inverter"])
        if chave_sinal not in cache_sinal:
            cache_sinal[chave_sinal] = sinal_condicao(m1_por_dia_1, [dia], u["feature"], u["bucket"],
                                                        u["side"], edges, inverter=u["inverter"])
        sinais = cache_sinal[chave_sinal]
        res = simular_grade([dia], m1_por_dia_1, ticks_por_dia_1, sinais, u["arm"], u["floor"],
                             u["trail_mult"], u["modo"], queue_ahead_qty, None)
        chave = (u["feature"], u["bucket"], u["side"], u["arm"], u["floor"], u["trail_mult"],
                 u["modo"], u["inverter"])
        resultados[chave] = (res.trades, res.diagnosticos, res.tentativas_limite)
    return janela_nome, dia, resultados, _peak_rss_mb()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    from backtest.intraday.fidelidade import fidelidade_for
    from backtest.intraday.report import cabecalho, linha

    t0 = time.perf_counter()
    livre_inicial_gb = _free_ram_gb()
    print(f"[onde_preco_corre] cpu_count={os.cpu_count()} (teto CPU={N_WORKERS_CPU}) -- "
          f"RAM livre agora: {livre_inicial_gb:.2f}GB", flush=True)
    dias = carregar_dias_is()
    _limite_smoke = os.environ.get("WDO_ONDE_SMOKE_DIAS")
    if _limite_smoke:
        dias = dias[: int(_limite_smoke)]
        print(f"[onde_preco_corre] *** SMOKE TEST *** limitando a {len(dias)} pregoes via "
              f"WDO_ONDE_SMOKE_DIAS -- NAO usar para o resultado final", flush=True)
    n_desc = round(len(dias) * 2 / 3)
    dias_desc, dias_conf = dias[:n_desc], dias[n_desc:]
    print(f"[onde_preco_corre] IS {len(dias)} pregoes ({dias[0]}..{dias[-1]}); "
          f"DESCOBERTA {len(dias_desc)} ({dias_desc[0]}..{dias_desc[-1]}), "
          f"CONFIRMACAO {len(dias_conf)} ({dias_conf[0]}..{dias_conf[-1]})", flush=True)

    print("[onde_preco_corre] carregando M1+features (todo o IS)...", flush=True)
    m1_por_dia = carregar_m1_features(dias)
    print(f"[onde_preco_corre] carregando ticks (todo o IS, so' as colunas last/volume, "
          f"1 passada de groupby)... ({time.perf_counter()-t0:.1f}s)", flush=True)
    ticks_por_dia = carregar_ticks_rapido(dias)
    t_dados = time.perf_counter() - t0
    eta_step1 = (len(dias) / N_WORKERS_CPU) * 12.0  # ~12s/pregao observado em smoke test (10 pregoes)
    print(f"[onde_preco_corre] dado carregado em {t_dados:.1f}s -- ETA Step 1 (estimativa estatica, "
          f"~12s/pregao / {N_WORKERS_CPU} workers): ~{eta_step1:.0f}s (~{eta_step1/60:.1f}min)", flush=True)

    # ---------------- STEP 1: resolucao "onde corre" por pregao (paralelo) --
    # Cada task ja' recebe SO' o pregao dela (nunca a janela inteira) --
    # Step 1 nunca teve o problema de RAM do Step 2 (nao tinha initializer
    # nenhum), mas o pool serve TAMBEM de calibracao: mede o RSS de pico de
    # verdade antes de decidir quantos workers o Step 2 pode ter.
    tasks = [(i + 1, len(dias), dia, m1_por_dia[dia], ticks_por_dia[dia])
             for i, dia in enumerate(dias) if dia in m1_por_dia and dia in ticks_por_dia]
    eventos_por_dia: dict[dt.date, pd.DataFrame] = {}
    picos_rss_mb: list[float] = []
    t_step1 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=N_WORKERS_CPU) as pool:
        futs = {pool.submit(_worker_eventos_dia, t): t[2] for t in tasks}
        done = 0
        for fut in as_completed(futs):
            dia, df, peak_rss = fut.result()
            eventos_por_dia[dia] = df
            if np.isfinite(peak_rss):
                picos_rss_mb.append(peak_rss)
            done += 1
            _print_eta("Step1", done, len(tasks), t_step1)

    pico_rss_medido_gb = (max(picos_rss_mb) / 1024.0) if picos_rss_mb else float("nan")
    livre_pos_step1_gb = _free_ram_gb()
    # Margem de seguranca: Step 2 cabe MAIS unidade por task (ate' 60
    # combinacoes condicao x celula por pregao, ver `_roda_dia_step2`)
    # contra 1088 eventos/dia do Step 1 -- 3x o pico medido cobre essa
    # folga sem depender de o Step 1 ter parecido barato.
    pico_step2_estimado_gb = (pico_rss_medido_gb * 3.0) if np.isfinite(pico_rss_medido_gb) else float("nan")
    n_workers_step2 = decidir_n_workers(pico_step2_estimado_gb)
    print(f"\n[onde_preco_corre] calibracao de RAM (medida no pool do Step 1, {len(picos_rss_mb)} amostras): "
          f"pico RSS/worker={pico_rss_medido_gb:.3f}GB -- RAM livre agora={livre_pos_step1_gb:.2f}GB -- "
          f"estimativa p/ Step 2 (3x margem)={pico_step2_estimado_gb:.3f}GB/worker -- "
          f"N_WORKERS Step 2 = min(cpu-1={N_WORKERS_CPU}, "
          f"floor((livre-{RAM_RESERVADA_GB:.0f})/pico)), teto {RAM_TETO_TOTAL_WORKERS_GB:.0f}GB total "
          f"=> {n_workers_step2}", flush=True)

    eventos = pd.concat(eventos_por_dia.values(), ignore_index=True)
    ev_desc = eventos[eventos["dia"].isin(dias_desc)].reset_index(drop=True)
    ev_conf = eventos[eventos["dia"].isin(dias_conf)].reset_index(drop=True)
    print(f"\n[onde_preco_corre] Step 1: {len(eventos)} eventos totais "
          f"({len(ev_desc)} descoberta, {len(ev_conf)} confirmacao) -- {time.perf_counter()-t0:.1f}s", flush=True)

    edges = calibrar_edges(ev_desc, n_buckets=3)
    ev_desc_b = aplicar_buckets(ev_desc, edges)
    ev_conf_b = aplicar_buckets(ev_conf, edges)

    print("\n=== STEP 1 -- BASELINE (P de corrida >= R antes do stop, por lado) ===")
    for r in R_TICKS:
        col = f"outcome_R{int(r)}"
        for janela_nome, ev in (("DESCOBERTA", ev_desc_b), ("CONFIRMACAO", ev_conf_b)):
            for side, sub in ev.groupby("side"):
                p = 100.0 * (sub[col] == "target").mean()
                print(f"  R={r:.0f}t {janela_nome:12s} {side:5s}: P={p:5.2f}%  n={len(sub)}")

    print("\n=== STEP 1 -- top buckets por |lift| em DESCOBERTA (R=5t), replicacao em CONFIRMACAO ===")
    st_desc = stats_por_bucket(ev_desc_b, R_SELECAO)
    st_conf = stats_por_bucket(ev_conf_b, R_SELECAO)
    st_desc_real = st_desc[st_desc["feature"] != "__baseline__"].copy()
    st_desc_real["abs_lift"] = st_desc_real["lift"].abs()
    st_desc_real = st_desc_real.sort_values("abs_lift", ascending=False)

    conf_idx = st_conf.set_index(["feature", "bucket", "side"])
    linhas_report = []
    for _, row in st_desc_real.head(30).iterrows():
        chave = (row["feature"], row["bucket"], row["side"])
        conf_row = conf_idx.loc[chave] if chave in conf_idx.index else None
        if conf_row is not None:
            replica = (conf_row["n"] >= 100) and (np.sign(conf_row["lift"]) == np.sign(row["lift"])) and row["lift"] != 0
            linhas_report.append(dict(feature=row["feature"], bucket=row["bucket"], side=row["side"],
                                       n_desc=row["n"], p_desc=row["p_target"], lift_desc=row["lift"],
                                       n_conf=conf_row["n"], p_conf=conf_row["p_target"], lift_conf=conf_row["lift"],
                                       replica=replica))
        else:
            linhas_report.append(dict(feature=row["feature"], bucket=row["bucket"], side=row["side"],
                                       n_desc=row["n"], p_desc=row["p_target"], lift_desc=row["lift"],
                                       n_conf=0, p_conf=float("nan"), lift_conf=float("nan"), replica=False))
    df_report = pd.DataFrame(linhas_report)
    for _, r in df_report.iterrows():
        flag = "REPLICA" if r["replica"] else "-"
        print(f"  {r['feature']:20s} {str(r['bucket']):22s} {r['side']:5s}  "
              f"desc P={100*r['p_desc']:5.2f}% lift={100*r['lift_desc']:+6.2f}pp n={int(r['n_desc']):5d}  |  "
              f"conf P={100*r['p_conf']:5.2f}% lift={100*r['lift_conf']:+6.2f}pp n={int(r['n_conf']):5d}  [{flag}]")

    # Selecao para o Step 2: SO' lift POSITIVO (P(corrida)>baseline -- "aqui o
    # preco corre MAIS", a pergunta do dono) entre as REPLICADAS, ranqueadas
    # por lift (nao |lift|). O ranking do topo-30 acima usa |lift| de
    # proposito (mostra tambem onde EVITAR, ex.: 18:00 tem lift muito
    # NEGATIVO nos dois lados -- artefato conhecido: a janela de 30min do
    # Step 1 e' truncada no achatamento de 18:25, entao barras perto do fim
    # do pregao tem MENOS TEMPO para rodar R ticks antes da janela fechar,
    # empurrando P para baixo nos DOIS lados por construcao, nao por edge.
    # Ranquear por lift positivo evita alimentar o Step 2 com essa condicao
    # "pior que o baseline" travestida de "top |lift|").
    df_report["lift_desc_signed"] = df_report["lift_desc"]
    positivas = df_report[(df_report["replica"]) & (df_report["lift_desc_signed"] > 0)].copy()
    positivas = positivas.sort_values("lift_desc_signed", ascending=False)
    replicadas = positivas
    if len(replicadas) >= 3:
        top3 = replicadas.head(3)
        origem_top3 = "REPLICADAS, lift POSITIVO (onde o preco corre MAIS que o baseline)"
    else:
        top3 = df_report.head(3)
        origem_top3 = "TOP-3 POR DESCOBERTA (nenhuma/poucas replicaram)"
    print(f"\n[onde_preco_corre] condicoes escolhidas para Step 2: {origem_top3}")
    for _, r in top3.iterrows():
        print(f"  {r['feature']} = {r['bucket']}  side={r['side']}")

    # -------- nulo shuffled-side --------
    limiar_lift = float(df_report["lift_desc"].abs().iloc[min(14, len(df_report) - 1)])  # ~top-15
    print(f"\n[onde_preco_corre] rodando nulo shuffled-side ({N_SHUFFLES_NULO}x, "
          f"limiar |lift|>={100*limiar_lift:.2f}pp -- corte do 15o bucket real)...", flush=True)
    contagens_nulo = nulo_shuffled_side(ev_desc_b, R_SELECAO, limiar_lift)
    n_real_pass = int((df_report["lift_desc"].abs() >= limiar_lift).sum())
    print(f"[onde_preco_corre] nulo: media={np.mean(contagens_nulo):.1f} buckets cruzam o corte por acaso "
          f"(p10={np.percentile(contagens_nulo,10):.0f} p90={np.percentile(contagens_nulo,90):.0f}, "
          f"max={max(contagens_nulo)}) contra {n_real_pass} reais no mesmo corte (topo-30 listado, "
          f"universo testado = {len(st_desc_real)} buckets)")

    # ---------------- STEP 2: grade de saida, top-3 condicoes (POR PREGAO) ---
    fid = fidelidade_for("WDO@")
    print(f"\n[onde_preco_corre] Step 2 -- fidelidade WDO@: queue_ahead_qty(entrada)={fid.queue_ahead_qty} "
          f"medido_em={fid.medido_em}", flush=True)
    print(f"[onde_preco_corre] Step 2 workers: {n_workers_step2} (decidido pela calibracao de RAM acima, "
          f"nao pelo teto de CPU)", flush=True)

    condicoes = list(top3.itertuples(index=False))

    def _roda_fase_step2(unidades: list[dict], fase: str) -> dict:
        """Submete UMA task por (janela, pregao) -- cada task recebe so' o
        pregao dela (poucos MB) e calcula TODAS as `unidades` (condicao x
        celula) para aquele pregao. Agrega por (janela, chave_unidade) no
        processo principal. Substitui a versao antiga que dava a cada
        WORKER uma copia inteira da janela via `initializer` -- ver a nota
        de RAM na docstring de `_roda_dia_step2`."""
        tarefas = []
        for janela_nome, dias_janela in (("descoberta", dias_desc), ("confirmacao", dias_conf)):
            for dia in dias_janela:
                if dia not in m1_por_dia or dia not in ticks_por_dia:
                    continue
                tarefas.append((janela_nome, dia, m1_por_dia[dia], ticks_por_dia[dia], unidades,
                                 edges, fid.queue_ahead_qty))
        agregados: dict[tuple, dict] = {}
        t_fase = time.perf_counter()
        with ProcessPoolExecutor(max_workers=n_workers_step2) as pool:
            futs = [pool.submit(_roda_dia_step2, t) for t in tarefas]
            done = 0
            picos_fase: list[float] = []
            for fut in as_completed(futs):
                janela_nome, dia, resultados_dia, peak_rss = fut.result()
                if np.isfinite(peak_rss):
                    picos_fase.append(peak_rss)
                for chave_unidade, (trades, diags, tent) in resultados_dia.items():
                    chave = (janela_nome,) + chave_unidade
                    slot = agregados.setdefault(chave, dict(trades=[], diagnosticos=[], tentativas=[]))
                    slot["trades"].extend(trades)
                    slot["diagnosticos"].extend(diags)
                    slot["tentativas"].extend(tent)
                done += 1
                _print_eta(f"Step2-{fase}", done, len(tarefas), t_fase)
        if picos_fase:
            print(f"  [Step2-{fase}] RSS pico observado nesta fase: max={max(picos_fase):.0f}MB "
                  f"(n={len(picos_fase)} tasks)", flush=True)
        return agregados

    unidades_grade = []
    for cond in condicoes:
        for arm in ARM_LEVELS:
            for floor in FLOOR_LEVELS:
                for trail_mult in TRAIL_MULTS:
                    unidades_grade.append(dict(feature=cond.feature, bucket=cond.bucket, side=cond.side,
                                                arm=arm, floor=floor, trail_mult=trail_mult, modo="limite",
                                                inverter=False))
    n_celulas = len(unidades_grade)
    print(f"[onde_preco_corre] grade: {n_celulas} celulas (3 condicoes x 18 arm/floor/trail) x 2 janelas, "
          f"unidade de trabalho = 1 pregao (nao 1 celula -- ver nota de RAM), {len(dias)} tasks totais\n",
          flush=True)
    agregados_grade = _roda_fase_step2(unidades_grade, "grade")

    resultados: dict[tuple, object] = {}
    stats_por_spec: dict[tuple, dict] = {}
    print("\n" + cabecalho(EXTRAS_STEP2, 11))
    for chave, slot in sorted(agregados_grade.items(), key=lambda kv: str(kv[0])):
        janela_nome, feature, bucket, side, arm, floor, trail_mult, modo, inverter = chave
        rotulo = f"{feature}={bucket}|{side} a{arm:.0f}f{floor:.0f}t{trail_mult:.0f}x"
        item, stats = _linha_step2(rotulo, slot["trades"], slot["diagnosticos"], slot["tentativas"],
                                    dias_desc if janela_nome == "descoberta" else dias_conf, modo)
        chave_compat = (feature, bucket, side, arm, floor, trail_mult, janela_nome)
        resultados[chave_compat] = item
        stats_por_spec[chave_compat] = stats
        print(f"[{janela_nome}] {linha(item, EXTRAS_STEP2, 11)}")

    print(f"\n[onde_preco_corre] Step 2 grade limite: {time.perf_counter()-t0:.1f}s total (acumulado)", flush=True)

    # -------- melhor celula por condicao (R$/op em DESCOBERTA) + teto/cego --
    unidades_ref = []
    melhores: dict = {}
    for cond in condicoes:
        chaves_desc = [k for k in stats_por_spec if k[0] == cond.feature and k[1] == cond.bucket
                        and k[2] == cond.side and k[6] == "descoberta"]
        melhor = max(chaves_desc, key=lambda k: (stats_por_spec[k]["media"] if stats_por_spec[k]["n"] > 0 else -1e9))
        _, _, _, arm, floor, trail_mult, _ = melhor
        melhores[(cond.feature, cond.bucket, cond.side)] = (arm, floor, trail_mult)
        unidades_ref.append(dict(feature=cond.feature, bucket=cond.bucket, side=cond.side, arm=arm, floor=floor,
                                  trail_mult=trail_mult, modo="teto", inverter=False))
        unidades_ref.append(dict(feature=cond.feature, bucket=cond.bucket, side=cond.side, arm=arm, floor=floor,
                                  trail_mult=trail_mult, modo="limite", inverter=True))

    print(f"\n[onde_preco_corre] {len(unidades_ref)} unidades de referencia (teto a mercado + controle "
          f"as-cegas, na MELHOR geometria de cada condicao)\n", flush=True)
    agregados_ref = _roda_fase_step2(unidades_ref, "ref")

    print("\n" + cabecalho(EXTRAS_STEP2, 11))
    for chave, slot in sorted(agregados_ref.items(), key=lambda kv: str(kv[0])):
        janela_nome, feature, bucket, side, arm, floor, trail_mult, modo, inverter = chave
        sufixo = "TETO-ref" if modo == "teto" else "CEGO"
        rotulo = f"{feature}={bucket}|{side} a{arm:.0f}f{floor:.0f}t{trail_mult:.0f}x {sufixo}"
        item, stats = _linha_step2(rotulo, slot["trades"], slot["diagnosticos"], slot["tentativas"],
                                    dias_desc if janela_nome == "descoberta" else dias_conf, modo)
        chave_compat = ("ref", rotulo, janela_nome)
        resultados[chave_compat] = item
        stats_por_spec[chave_compat] = stats
        print(f"[{janela_nome}] {linha(item, EXTRAS_STEP2, 11)}")

    print(f"\n[onde_preco_corre] total geral: {time.perf_counter()-t0:.1f}s")

    # -------- resumo final por condicao, discovery x confirmation --------
    print("\n=== RESUMO -- melhor celula por condicao, DESCOBERTA x CONFIRMACAO ===")
    for cond in condicoes:
        chaves_desc = [k for k in stats_por_spec if isinstance(k, tuple) and len(k) == 7 and k[0] == cond.feature
                        and k[1] == cond.bucket and k[2] == cond.side and k[6] == "descoberta"]
        if not chaves_desc:
            continue
        melhor = max(chaves_desc, key=lambda k: (stats_por_spec[k]["media"] if stats_por_spec[k]["n"] > 0 else -1e9))
        chave_conf = melhor[:6] + ("confirmacao",)
        st_d, st_c = stats_por_spec[melhor], stats_por_spec.get(chave_conf)
        print(f"\n  {cond.feature}={cond.bucket}|{cond.side}  arm={melhor[3]:.0f} floor={melhor[4]:.0f} "
              f"trail={melhor[5]:.0f}x")
        print(f"    descoberta:   R$/op={st_d['media']:7.2f}  IC95=[{st_d['ic95'][0]:7.2f};{st_d['ic95'][1]:7.2f}]  "
              f"n={st_d['n']:4d}  win%={st_d['win_pct']:5.1f}  breakeven%={st_d['breakeven_empirico']:5.1f}")
        if st_c is not None:
            print(f"    confirmacao:  R$/op={st_c['media']:7.2f}  IC95=[{st_c['ic95'][0]:7.2f};{st_c['ic95'][1]:7.2f}]  "
                  f"n={st_c['n']:4d}  win%={st_c['win_pct']:5.1f}  breakeven%={st_c['breakeven_empirico']:5.1f}")
            positivo_nos_dois = (st_d['ic95'][0] > 0) and (st_c['ic95'][0] > 0)
            print(f"    >>> IC95 > 0 nas DUAS janelas: {'SIM' if positivo_nos_dois else 'nao'}")


if __name__ == "__main__":
    main()
