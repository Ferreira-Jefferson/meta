"""Baixa OHLCV via yfinance e séries macro do BCB SGS. Salva em Parquet."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf

from core.config import BENCHMARK, DATA_DIR, HISTORY_START, WATCHLIST
from market_data.quality import check, consensus_calendar, fill_gaps


BCB_SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"
BCB_MACRO_SERIES: dict[str, int] = {
    "selic":     11,   # Selic diária (% a.d.)
    "usd_brl":    1,   # Dólar comercial venda
    "ipca":     433,   # IPCA mensal % a.m.
    "desemprego": 24369, # PNAD Contínua taxa desocupação %
}


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    keep = ["open", "high", "low", "close", "adj close", "volume"]
    df = df[[c for c in keep if c in df.columns]]
    df = df.rename(columns={"adj close": "adj_close"})
    return df.dropna(how="all")


INCREMENTAL_LOOKBACK_DAYS = 15


def incremental_start(ticker: str, default_start: str, out_dir: Path = DATA_DIR) -> str:
    """Data de início do download para ESTA rodada.

    Sem parquet em disco: bootstrap completo desde `default_start`. Com parquet
    em disco: não faz sentido rebaixar 16 anos de história do yfinance toda vez
    só para atualizar o pregão de hoje — pede apenas os últimos
    `INCREMENTAL_LOOKBACK_DAYS` dias corridos (janela de folga para reruns no
    mesmo pregão e para o provedor corrigir um close recém-publicado).

    `merge_preserving_history` recoloca a história antiga intacta (o "resgate"
    dela é justamente o mecanismo que já existia); esta função só evita pedir
    de novo o que a rodada anterior já garantiu.
    """
    path = parquet_path(ticker, out_dir)
    if not path.exists():
        return default_start
    old = pd.read_parquet(path)
    if old.empty:
        return default_start
    last = pd.to_datetime(old.index).max()
    lookback = last - pd.Timedelta(days=INCREMENTAL_LOOKBACK_DAYS)
    floor = pd.Timestamp(default_start)
    return max(lookback, floor).strftime("%Y-%m-%d")


def download_one(ticker: str, start: str = HISTORY_START) -> pd.DataFrame:
    raw = yf.download(
        ticker,
        start=start,
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    if raw.empty:
        raise RuntimeError(f"Sem dados para {ticker}")
    return _clean(raw)


def parquet_path(ticker: str, out_dir: Path = DATA_DIR) -> Path:
    safe = ticker.replace("^", "_").replace(".", "_")
    return out_dir / f"{safe}.parquet"


def write_parquet_atomico(df: pd.DataFrame, path: Path) -> Path:
    """Grava o parquet num temporario ao lado e o RENOMEIA para `path`.

    `df.to_parquet(path)` grava no lugar: o arquivo passa por um estado
    truncado/parcial no meio da escrita. Isso e um problema real com um unico
    processo — o supervisor ao vivo chama `sync_data()` enquanto o painel e
    qualquer backtest leem os MESMOS parquets — e vira corrupcao com dois
    (nao existe guarda de instancia unica no projeto). Quem le durante a
    escrita ou levanta excecao no meio de um pregao, ou, pior, le uma serie
    incompleta e decide com ela.

    `os.replace` e atomico no mesmo volume tanto no Windows quanto no POSIX:
    o leitor ve o arquivo antigo ou o novo, nunca um pela metade. O
    temporario e criado no MESMO diretorio de proposito — em `%TEMP%` ele
    poderia cair em outro volume e o replace deixaria de ser atomico.

    Falha na escrita nao pode destruir o parquet que ja existia: o
    temporario e removido e o original fica intocado.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        df.to_parquet(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def save_parquet(ticker: str, df: pd.DataFrame, out_dir: Path = DATA_DIR) -> Path:
    return write_parquet_atomico(df, parquet_path(ticker, out_dir))


def merge_preserving_history(
    ticker: str, df_new: pd.DataFrame, out_dir: Path = DATA_DIR
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Une o download novo ao parquet existente, sem perder pregão já baixado.

    Motivo (bug real, 2026-08-17): o yfinance devolve, de forma intermitente,
    séries com pregões FALTANDO no trecho recente — cada download vem com um
    conjunto diferente de buracos. Como `download_all` sobrescrevia o parquet às
    cegas, uma barra que desaparecia levava o robô a mudar de decisão: numa
    execução ele rotacionava de CSMG3 para BRAP4 em 2026-08-03, na outra não, e
    o capital final da janela FULL oscilava 6% (R$169.636 vs R$179.864) sem nada
    ter mudado no código nem na estratégia. `download_macro` já protegia dado
    macro assim ("não zera dado válido"); OHLCV não tinha proteção nenhuma.

    Os valores do download novo têm prioridade em datas sobrepostas (correção
    legítima do provedor vale); só as datas que o novo download PERDEU são
    preservadas do parquet antigo. Como `download_one` usa `auto_adjust=False`,
    o OHLC bruto é estável no tempo e essa união não mistura escalas de ajuste.

    Retorna (dataframe final, datas resgatadas do parquet antigo).
    """
    path = parquet_path(ticker, out_dir)
    if not path.exists():
        return df_new, []
    old = pd.read_parquet(path)
    old.index = pd.to_datetime(old.index)
    rescued = [d for d in old.index if d not in df_new.index and d <= df_new.index.max()]
    if not rescued:
        return df_new, []
    merged = df_new.combine_first(old.loc[rescued]).sort_index()
    return merged, rescued


def _bcb_fetch_chunk(code: int, start: str, end: str) -> list[dict]:
    """Uma janela de fetch da API do BCB SGS. Retorna lista bruta de {data, valor}."""
    ini = pd.to_datetime(start).strftime("%d/%m/%Y")
    fim = pd.to_datetime(end).strftime("%d/%m/%Y")
    url = BCB_SGS_URL.format(code=code, ini=ini, fim=fim)
    # BCB API rejeita User-Agents "de browser" (406 Not Acceptable) mas aceita
    # UAs simples estilo curl. Descoberto empiricamente.
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "curl/8.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _bcb_fetch(code: int, start: str, end: str, chunk_years: int = 10) -> pd.DataFrame:
    """Baixa uma série SGS. BCB limita a faixa por request (>~10 anos → 406),
    então divide em janelas de `chunk_years` anos.
    """
    s, e = pd.to_datetime(start), pd.to_datetime(end)
    payload: list[dict] = []
    cur = s
    while cur <= e:
        stop = min(cur + pd.DateOffset(years=chunk_years) - pd.Timedelta(days=1), e)
        payload.extend(_bcb_fetch_chunk(code, cur.strftime("%Y-%m-%d"), stop.strftime("%Y-%m-%d")))
        cur = stop + pd.Timedelta(days=1)
    if not payload:
        raise RuntimeError(f"BCB SGS {code}: resposta vazia para {start}..{end}")
    df = pd.DataFrame(payload)
    df["date"]  = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = df["valor"].astype(float)
    df = df.set_index("date")[["valor"]].sort_index()
    df = df[~df.index.duplicated(keep="last")]  # sobreposição entre chunks (raro)
    df.index.name = "date"
    return df


def download_macro(
    series: dict[str, int] = BCB_MACRO_SERIES,
    start: str = HISTORY_START,
    out_dir: Path = DATA_DIR,
) -> dict[str, Path]:
    """Baixa séries macro do BCB SGS até hoje. Idempotente: reescreve o parquet.

    Se a API falhar para uma série, mantém o parquet antigo (não zera dado válido).
    Retorna dict {nome: path_do_parquet_atualizado}.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    written: dict[str, Path] = {}
    for name, code in series.items():
        path = out_dir / f"{name}.parquet"
        try:
            df = _bcb_fetch(code, start=start, end=today)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            # Preserva parquet existente se a API falhar
            if path.exists():
                print(f"[macro] {name}: falha na API ({e}); mantendo parquet local")
            else:
                print(f"[macro] {name}: falha na API ({e}); sem parquet local")
            continue
        write_parquet_atomico(df, path)
        written[name] = path
    return written


def download_all(
    tickers: Iterable[str] = WATCHLIST,
    include_benchmark: bool = True,
    include_macro: bool = True,
    start: str = HISTORY_START,
) -> dict[str, Path]:
    written: dict[str, Path] = {}
    universe = list(tickers)
    if include_benchmark and BENCHMARK not in universe:
        universe.append(BENCHMARK)

    frames: dict[str, pd.DataFrame] = {}
    for t in universe:
        t_start = incremental_start(t, start, DATA_DIR)
        df = download_one(t, start=t_start)
        df, rescued = merge_preserving_history(t, df, DATA_DIR)
        # Com start incremental, a maior parte de `rescued` é história antiga
        # que nem foi pedida nesta rodada (reanexação esperada, não anomalia).
        # Só vale alertar quando o yfinance perdeu um pregão DENTRO da janela
        # que acabamos de pedir — isso sim é o flapping que este mecanismo existe
        # para pegar.
        flapped = [d for d in rescued if d >= pd.Timestamp(t_start)]
        if flapped:
            dates = ", ".join(d.strftime("%Y-%m-%d") for d in flapped[-5:])
            print(f"[ohlcv] {t}: download veio sem {len(flapped)} pregão(ões) dentro da "
                  f"janela pedida — preservados do parquet local (últimos: {dates})")
        frames[t] = df

    # Calendário de consenso do universo baixado NESTA rodada. Um buraco pontual
    # (yfinance falha para 1 ticker num pregão que os demais têm) vira barra
    # sintética (close anterior carregado); um feriado/fim de semana real, como
    # a maioria não tem, nunca entra no calendário e não é "corrigido" à toa.
    calendar = consensus_calendar(frames)

    for t, df in frames.items():
        if calendar is not None:
            df, filled = fill_gaps(df, calendar)
            if filled:
                dates = ", ".join(d.strftime("%Y-%m-%d") for d in filled[-5:])
                print(f"[ohlcv] {t}: {len(filled)} sessão(ões) ausente(s) vs. consenso do "
                      f"universo — preenchida(s) com close anterior (últimas: {dates})")
        report = check(t, df, calendar)
        if not report.ok():
            print(f"[ohlcv] {t}: qualidade suspeita — nan={report.nan_count} "
                  f"gap_max={report.max_gap_days}d dup={report.duplicated_index} "
                  f"missing={len(report.missing_sessions)}")
        written[t] = save_parquet(t, df)

    if include_macro:
        for name, path in download_macro(start=start).items():
            written[f"macro:{name}"] = path
    return written
