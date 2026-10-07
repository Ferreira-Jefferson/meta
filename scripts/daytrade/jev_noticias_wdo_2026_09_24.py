"""Estudo de evento: o Jev (OpenRouter, typesafe/jev-1.13), lendo manchetes de
noticia, preve a direcao do WDO nos minutos seguintes?

Fases (rodar em ordem, cada uma cacheia em jev_noticias_wdo_2026_09_24_out/):
  probe   -- Fase 0: 1 chamada de teste ao Jev, confirma formato e custo.
  gdelt   -- Fase 1: baixa manchetes do GDELT DOC 2.0, dia a dia, cache CSV.
  jev     -- Fase 2: monta a amostra estratificada e pergunta ao Jev (paralelo).
  result  -- Fase 3: cruza com o preco do WDO e imprime/grava a tabela.

Uso:
  .\\.venv\\Scripts\\python.exe scripts/daytrade/jev_noticias_wdo_2026_09_24.py probe
  .\\.venv\\Scripts\\python.exe scripts/daytrade/jev_noticias_wdo_2026_09_24.py gdelt
  .\\.venv\\Scripts\\python.exe scripts/daytrade/jev_noticias_wdo_2026_09_24.py jev
  .\\.venv\\Scripts\\python.exe scripts/daytrade/jev_noticias_wdo_2026_09_24.py result

A chave OPENROUTER_API_KEY vem de .env na raiz do repo. Nunca e' impressa,
logada ou gravada em nenhum arquivo de saida.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent / "jev_noticias_wdo_2026_09_24_out"
PRICE_PATH = REPO_ROOT / "data" / "raw_intraday" / "WDO_A_.parquet"
TICK_SIZE = 0.5

RAW_CSV = OUT_DIR / "gdelt_manchetes_raw.csv"
FETCH_STATE = OUT_DIR / "gdelt_fetch_state.json"
AMOSTRA_CSV = OUT_DIR / "amostra.csv"
AVALIACOES_CSV = OUT_DIR / "avaliacoes_jev.csv"
EVENTOS_CSV = OUT_DIR / "eventos_com_preco.csv"
TABELA_CSV = OUT_DIR / "tabela_resultado.csv"

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"

GDELT_START = date(2026, 6, 25)
GDELT_END = date(2026, 9, 15)
QUERIES = {
    "pt": '(dólar OR câmbio OR Copom OR "Banco Central" OR Galípolo OR Haddad OR '
    'fiscal OR "arcabouço" OR Fed OR Powell OR tarifa OR Trump) sourcelang:portuguese',
    "en": '("Brazilian real" OR "Brazil fiscal" OR Fed OR Powell OR Treasury) '
    "sourcelang:english",
}

PREGAO_INICIO_UTC_MIN = 12 * 60 + 5   # 09:05 BRT
PREGAO_FIM_UTC_MIN = 20 * 60 + 30     # 17:30 BRT

AMOSTRA_ALVO = 500
HORIZONTES = (1, 5, 15, 30)
N_PERMUTACOES = 5000

PADROES_RELATA_PRECO = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bdolar\s+(sobe|cai|fecha|recua|avanca|dispara|desaba|opera|sobre)\b",
        r"\breal\s+se\s+(valoriza|desvaloriza)\b",
        r"\bcambio\s+(sobe|cai|fecha|recua|avanca)\b",
        r"\bdolar\s+em\s+alta\b",
        r"\bdolar\s+em\s+baixa\b",
    ]
]


def _fmt(x: float, nd: int = 3) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/d"
    return f"{x:.{nd}f}".replace(".", ",")


def carregar_chave() -> str:
    load_dotenv(REPO_ROOT / ".env")
    import os

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY nao encontrada em .env")
    return key


def norm_titulo(t: str) -> str:
    t = t.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w ]", "", t)
    return t


def marca_relata_preco(titulo_norm: str) -> bool:
    return any(p.search(titulo_norm) for p in PADROES_RELATA_PRECO)


# --------------------------------------------------------------------------
# Fase 0 -- sonda
# --------------------------------------------------------------------------


def chamar_jev(api_key: str, manchete: str, idioma: str, fonte: str) -> dict:
    body = {
        "model": MODEL,
        "state": {"manchete": manchete, "idioma": idioma, "fonte": fonte},
        "questions": {
            "efeito_cambio": {
                "type": "choice",
                "instructions": (
                    "Qual o efeito provavel desta noticia sobre a cotacao do "
                    "dolar contra o real (USD/BRL) nos proximos minutos?"
                ),
                "criteria": {
                    "dolar_sobe": "O dolar deve subir em relacao ao real nos proximos minutos",
                    "dolar_cai": "O dolar deve cair em relacao ao real nos proximos minutos",
                    "sem_efeito": "Sem efeito relevante sobre a cotacao nos proximos minutos",
                },
            }
        },
    }
    resp = requests.post(
        DECISIONS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fase_probe() -> None:
    api_key = carregar_chave()
    manchete = "Banco Central eleva juros e dolar recua frente ao real"
    print("Fase 0 -- chamando o Jev com 1 manchete de teste...", flush=True)
    data = chamar_jev(api_key, manchete, "portuguese", "teste.local")
    print(json.dumps(data, indent=2, ensure_ascii=False), flush=True)
    custo = data.get("usage", {}).get("cost")
    if custo is None:
        print("AVISO: resposta sem usage.cost -- confira o formato acima.", flush=True)
        return
    print(f"\ncusto desta chamada: US${custo:.8f}", flush=True)
    projecao = custo * AMOSTRA_ALVO
    print(
        f"projecao para {AMOSTRA_ALVO} manchetes: US${projecao:.4f}"
        f" (orcamento duro: US$3,00 projetado / US$5,00 real)",
        flush=True,
    )
    if projecao > 3.0:
        print(
            "AVISO: projecao acima de US$3 -- reduza AMOSTRA_ALVO antes da Fase 2.",
            flush=True,
        )


# --------------------------------------------------------------------------
# Fase 1 -- GDELT
# --------------------------------------------------------------------------


def _load_fetch_state() -> dict:
    if FETCH_STATE.exists():
        return json.loads(FETCH_STATE.read_text(encoding="utf-8"))
    return {"feito": []}


def _save_fetch_state(state: dict) -> None:
    FETCH_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def gdelt_fetch(query: str, start_dt: datetime, end_dt: datetime, timeout: int = 30) -> tuple[str, list[dict]]:
    """Retorna (status, artigos). status='ok' inclui lista vazia (zero real);
    status='error' e' rate-limit/rede/HTTP esgotados -- NAO e' zero real."""
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": 250,
        "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end_dt.strftime("%Y%m%d%H%M%S"),
        "sort": "DateAsc",
    }
    for tentativa in range(2):
        try:
            r = requests.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            print(f"    erro de rede ({exc}), tentativa {tentativa + 1}/2", flush=True)
            time.sleep(15)
            continue
        if r.status_code == 429:
            espera = 20 * (tentativa + 1)
            print(f"    429 rate-limit, aguardando {espera}s...", flush=True)
            time.sleep(espera)
            continue
        if r.status_code != 200:
            print(f"    status {r.status_code} -- erro (nao e' zero real)", flush=True)
            return "error", []
        try:
            return "ok", r.json().get("articles", [])
        except ValueError:
            return "ok", []
    return "error", []


def _dias_uteis_espacados(start: date, end: date, n: int) -> list[date]:
    uteis = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            uteis.append(d)
        d += timedelta(days=1)
    if len(uteis) <= n:
        return uteis
    idx = np.linspace(0, len(uteis) - 1, n)
    return sorted({uteis[int(round(i))] for i in idx})


def _seed_contagem_pregao() -> set[str]:
    """Titulos ja em cache (rodadas anteriores) que caem dentro do pregao."""
    if not RAW_CSV.exists():
        return set()
    raw = pd.read_csv(RAW_CSV)
    raw["seendate_utc"] = pd.to_datetime(
        raw["seendate_utc"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    raw = raw.dropna(subset=["seendate_utc", "titulo"])
    minuto = raw["seendate_utc"].dt.hour * 60 + raw["seendate_utc"].dt.minute
    dentro = raw[(minuto >= PREGAO_INICIO_UTC_MIN) & (minuto <= PREGAO_FIM_UTC_MIN)]
    return set(dentro["titulo"].map(norm_titulo))


def fase_gdelt(
    start: date, end: date, max_manchetes: int = 500, max_dias: int = 25, orcamento_seg: int = 2400
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_fetch_state()
    feito = set(tuple(x) for x in state.get("feito_pregao", []))

    vistos = _seed_contagem_pregao()
    n_seed = len(vistos)
    print(f"cache existente dentro do pregao: {n_seed} manchetes unicas", flush=True)
    if n_seed >= max_manchetes:
        print("ja atingiu a meta com o cache existente -- nao ha necessidade de coletar mais.", flush=True)
        return

    dias = _dias_uteis_espacados(start, end, max_dias)
    print(f"{len(dias)} pregoes selecionados (espacados) entre {start} e {end}", flush=True)

    novo_arquivo = not RAW_CSV.exists()
    f = open(RAW_CSV, "a", newline="", encoding="utf-8")
    writer = csv.writer(f)
    if novo_arquivo:
        writer.writerow(["titulo", "dominio", "seendate_utc", "idioma", "query", "dia"])

    t_inicio = time.time()
    total_novas = 0
    for idx_dia, dia in enumerate(dias, start=1):
        if len(vistos) >= max_manchetes:
            print(f"meta de {max_manchetes} manchetes atingida -- parando a coleta.", flush=True)
            break
        if time.time() - t_inicio > orcamento_seg:
            print(f"orcamento de tempo ({orcamento_seg}s) esgotado -- parando com o que ha.", flush=True)
            break
        for nome_q, query in QUERIES.items():
            chave = (dia.isoformat(), nome_q)
            if chave in feito:
                continue
            janela_inicio = datetime(dia.year, dia.month, dia.day, tzinfo=timezone.utc) + timedelta(
                minutes=PREGAO_INICIO_UTC_MIN
            )
            janela_fim = datetime(dia.year, dia.month, dia.day, tzinfo=timezone.utc) + timedelta(
                minutes=PREGAO_FIM_UTC_MIN
            )
            status, artigos = gdelt_fetch(query, janela_inicio, janela_fim)
            if status == "error":
                print(f"  [{idx_dia}/{len(dias)}] {dia} query={nome_q}: FALHA -- fica pendente p/ proxima rodada", flush=True)
                time.sleep(6)
                continue
            if len(artigos) == 250:
                # teto atingido: subdivide a janela do pregao em 3 blocos
                print(f"    {dia} {nome_q}: bateu o teto de 250 -- subdividindo em 3 blocos", flush=True)
                passo = (janela_fim - janela_inicio) / 3
                artigos = []
                for b in range(3):
                    b_ini = janela_inicio + b * passo
                    b_fim = janela_inicio + (b + 1) * passo
                    st_b, art_b = gdelt_fetch(query, b_ini, b_fim)
                    if st_b == "ok":
                        artigos.extend(art_b)
                    time.sleep(6)
            n_novas_dia = 0
            for a in artigos:
                titulo = (a.get("title") or "").strip()
                if not titulo:
                    continue
                writer.writerow(
                    [
                        titulo,
                        a.get("domain", ""),
                        a.get("seendate", ""),
                        a.get("language", nome_q),
                        nome_q,
                        dia.isoformat(),
                    ]
                )
                total_novas += 1
                tnorm = norm_titulo(titulo)
                if tnorm not in vistos:
                    vistos.add(tnorm)
                    n_novas_dia += 1
            f.flush()
            feito.add(chave)
            state["feito_pregao"] = sorted(list(feito))
            _save_fetch_state(state)
            print(
                f"  [{idx_dia}/{len(dias)}] {dia} query={nome_q}: {len(artigos)} artigos "
                f"({n_novas_dia} titulos novos dentro do pregao; total unico: {len(vistos)})",
                flush=True,
            )
            time.sleep(6)
    f.close()
    print(
        f"Fase 1 concluida em {time.time() - t_inicio:.0f}s. {len(vistos)} manchetes unicas "
        f"dentro do pregao. CSV bruto em {RAW_CSV}",
        flush=True,
    )


# --------------------------------------------------------------------------
# Fase 2 -- amostra + Jev
# --------------------------------------------------------------------------


def _price_brt_dates() -> set[date]:
    df = pd.read_parquet(PRICE_PATH, columns=["open"])
    brt = df.index.tz_convert("America/Sao_Paulo")
    return set(pd.Series(brt.date).unique())


def montar_amostra() -> pd.DataFrame:
    if AMOSTRA_CSV.exists():
        return pd.read_csv(AMOSTRA_CSV, parse_dates=["seendate_utc"])

    raw = pd.read_csv(RAW_CSV)
    raw["seendate_utc"] = pd.to_datetime(
        raw["seendate_utc"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    raw = raw.dropna(subset=["seendate_utc", "titulo"])

    minuto_do_dia = raw["seendate_utc"].dt.hour * 60 + raw["seendate_utc"].dt.minute
    dentro_pregao = (minuto_do_dia >= PREGAO_INICIO_UTC_MIN) & (
        minuto_do_dia <= PREGAO_FIM_UTC_MIN
    )
    raw = raw[dentro_pregao].copy()

    dias_com_preco = _price_brt_dates()
    seendate_brt_date = raw["seendate_utc"].dt.tz_convert("America/Sao_Paulo").dt.date
    raw = raw[seendate_brt_date.isin(dias_com_preco)].copy()
    raw["dia_brt"] = seendate_brt_date[raw.index]

    raw["titulo_norm"] = raw["titulo"].map(norm_titulo)
    raw = raw.sort_values("seendate_utc")
    raw = raw.drop_duplicates(subset="titulo_norm", keep="first")

    raw["relata_preco"] = raw["titulo_norm"].map(marca_relata_preco)

    n_dias = raw["dia_brt"].nunique()
    if n_dias == 0:
        raise SystemExit("Nenhuma manchete sobrou apos os filtros -- confira o GDELT.")
    cap_por_dia = max(1, int(np.ceil(AMOSTRA_ALVO / n_dias)))

    rng = np.random.default_rng(20260924)
    partes = []
    for _dia, grupo in raw.groupby("dia_brt"):
        if len(grupo) > cap_por_dia:
            idx = rng.choice(grupo.index.to_numpy(), size=cap_por_dia, replace=False)
            partes.append(grupo.loc[idx])
        else:
            partes.append(grupo)
    amostra = pd.concat(partes).sort_values("seendate_utc")

    if len(amostra) > 600:
        idx = rng.choice(amostra.index.to_numpy(), size=600, replace=False)
        amostra = amostra.loc[sorted(idx)]

    amostra = amostra[
        ["titulo", "titulo_norm", "dominio", "seendate_utc", "idioma", "relata_preco", "dia_brt"]
    ]
    amostra.to_csv(AMOSTRA_CSV, index=False)
    print(
        f"amostra montada: {len(amostra)} manchetes, {n_dias} dias, "
        f"cap/dia={cap_por_dia}",
        flush=True,
    )
    return amostra


def fase_jev(workers: int = 8) -> None:
    api_key = carregar_chave()
    amostra = montar_amostra()

    ja_avaliadas: set[str] = set()
    if AVALIACOES_CSV.exists():
        existentes = pd.read_csv(AVALIACOES_CSV)
        ja_avaliadas = set(existentes["titulo_norm"])

    pendentes = amostra[~amostra["titulo_norm"].isin(ja_avaliadas)]
    print(f"{len(pendentes)} manchetes pendentes de {len(amostra)} na amostra", flush=True)

    novo_arquivo = not AVALIACOES_CSV.exists()
    f = open(AVALIACOES_CSV, "a", newline="", encoding="utf-8")
    writer = csv.writer(f)
    if novo_arquivo:
        writer.writerow(
            [
                "titulo",
                "titulo_norm",
                "dominio",
                "seendate_utc",
                "idioma",
                "relata_preco",
                "escolha",
                "p_sobe",
                "p_cai",
                "p_neutro",
                "confianca",
                "custo_usd",
            ]
        )
    lock = Lock()
    custo_total = [0.0]
    parar = [False]

    def trabalhar(row) -> tuple | None:
        if parar[0]:
            return None
        try:
            resp = chamar_jev(api_key, row.titulo, row.idioma, row.dominio)
        except requests.RequestException as exc:
            print(f"  falha em '{row.titulo[:60]}...': {exc}", flush=True)
            return None
        ans = resp.get("answers", {}).get("efeito_cambio", {})
        probs = ans.get("probabilities", {})
        custo = resp.get("usage", {}).get("cost", 0.0) or 0.0
        with lock:
            custo_total[0] += custo
            if custo_total[0] > 5.0:
                parar[0] = True
        return (
            row.titulo,
            row.titulo_norm,
            row.dominio,
            row.seendate_utc,
            row.idioma,
            row.relata_preco,
            ans.get("choice", ""),
            probs.get("dolar_sobe", ""),
            probs.get("dolar_cai", ""),
            probs.get("sem_efeito", ""),
            ans.get("confidence", ""),
            custo,
        )

    n_feitas = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(trabalhar, row): row for row in pendentes.itertuples()}
        for fut in as_completed(futs):
            resultado = fut.result()
            n_feitas += 1
            if resultado is None:
                continue
            writer.writerow(resultado)
            f.flush()
            print(
                f"  [{n_feitas}/{len(pendentes)}] custo acumulado US${custo_total[0]:.6f} :: "
                f"{resultado[0][:70]}",
                flush=True,
            )
            if parar[0]:
                print("ORCAMENTO DE US$5 ESTOURADO -- parando.", flush=True)
                break
    f.close()
    print(f"Fase 2 concluida. custo total real: US${custo_total[0]:.6f}", flush=True)


# --------------------------------------------------------------------------
# Fase 3 -- resultado no preco
# --------------------------------------------------------------------------


def _direcao(row) -> int:
    if row.escolha == "dolar_sobe":
        return 1
    if row.escolha == "dolar_cai":
        return -1
    return 0


def montar_eventos() -> pd.DataFrame:
    av = pd.read_csv(AVALIACOES_CSV, parse_dates=["seendate_utc"])
    av = av.dropna(subset=["escolha"])
    av["p_max"] = av[["p_sobe", "p_cai", "p_neutro"]].max(axis=1)
    av["direcao"] = av.apply(_direcao, axis=1)

    df = pd.read_parquet(PRICE_PATH, columns=["open", "close"])
    idx = df.index
    tz_brt = "America/Sao_Paulo"
    idx_brt_date = idx.tz_convert(tz_brt).date
    n = len(df)
    idx_values = idx.values

    linhas = []
    for row in av.itertuples():
        seendate = row.seendate_utc
        if seendate.tzinfo is None:
            seendate = seendate.tz_localize("UTC")
        t0_pos = int(np.searchsorted(idx_values, np.datetime64(seendate), side="right"))
        if t0_pos >= n:
            continue
        t0_time_brt = idx_brt_date[t0_pos]
        seendate_brt = seendate.tz_convert(tz_brt).date()
        if t0_time_brt != seendate_brt:
            continue
        t0 = df["open"].iloc[t0_pos]

        pre_target = seendate - pd.Timedelta(minutes=15)
        pre_pos = int(np.searchsorted(idx_values, np.datetime64(pre_target), side="right")) - 1
        pre_ticks = np.nan
        if pre_pos >= 0 and idx_brt_date[pre_pos] == t0_time_brt:
            pre_close = df["close"].iloc[pre_pos]
            pre_ticks = (t0 - pre_close) / TICK_SIZE

        retornos = {}
        for h in HORIZONTES:
            h_pos = t0_pos + h
            if h_pos >= n or idx_brt_date[h_pos] != t0_time_brt:
                retornos[f"ret_{h}"] = np.nan
            else:
                retornos[f"ret_{h}"] = (df["close"].iloc[h_pos] - t0) / TICK_SIZE

        linhas.append(
            {
                "titulo": row.titulo,
                "seendate_utc": seendate,
                "direcao": row.direcao,
                "p_max": row.p_max,
                "relata_preco": bool(row.relata_preco),
                "t0_time": idx[t0_pos],
                "pre_ticks": pre_ticks,
                **retornos,
            }
        )
    eventos = pd.DataFrame(linhas)
    eventos.to_csv(EVENTOS_CSV, index=False)
    return eventos


def _ic95(std: float, n: int) -> float:
    if n <= 1:
        return float("nan")
    return 1.959963985 * std / np.sqrt(n)


def _perm_pvalue(dirs: np.ndarray, rets: np.ndarray, n_perm: int = N_PERMUTACOES) -> float:
    n = len(dirs)
    if n < 2:
        return float("nan")
    obs = float(np.mean(dirs * rets))
    rng = np.random.default_rng(42)
    idx_perm = np.argsort(rng.random((n_perm, n)), axis=1)
    dirs_perm = dirs[idx_perm]
    medias = (dirs_perm * rets[None, :]).mean(axis=1)
    count = np.sum(np.abs(medias) >= abs(obs))
    return (count + 1) / (n_perm + 1)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def linha_stats(sub: pd.DataFrame, horizonte: int) -> dict | None:
    col = f"ret_{horizonte}"
    d = sub.dropna(subset=[col])
    n = len(d)
    if n == 0:
        return None
    dirs = d["direcao"].to_numpy(dtype=float)
    rets = d[col].to_numpy(dtype=float)
    signed = dirs * rets
    media = float(np.mean(signed))
    std = float(np.std(signed, ddof=1)) if n > 1 else float("nan")
    ic95 = _ic95(std, n)

    nz = d[d[col] != 0]
    if len(nz) > 0:
        acerto = float(
            np.mean(np.sign(nz[col].to_numpy(dtype=float)) == nz["direcao"].to_numpy(dtype=float))
        )
    else:
        acerto = float("nan")

    pval = _perm_pvalue(dirs, rets)

    dpre = d.dropna(subset=["pre_ticks"])
    corr_pre = _corr(dpre["direcao"].to_numpy(dtype=float), dpre["pre_ticks"].to_numpy(dtype=float))
    corr_pos = _corr(dirs, rets)

    n_minutos_unicos = d["t0_time"].nunique()
    cluster = d.assign(signed=signed).groupby("t0_time")["signed"].mean()
    n_cluster = len(cluster)
    if n_cluster > 1:
        media_cluster = float(cluster.mean())
        std_cluster = float(cluster.std(ddof=1))
        ic95_cluster = _ic95(std_cluster, n_cluster)
    else:
        media_cluster = float("nan")
        ic95_cluster = float("nan")

    return {
        "n": n,
        "media_ticks": media,
        "std_ticks": std,
        "ic95_ticks": ic95,
        "acerto_pct": acerto * 100 if not np.isnan(acerto) else float("nan"),
        "p_valor": pval,
        "corr_pre": corr_pre,
        "corr_pos": corr_pos,
        "n_minutos_unicos": n_minutos_unicos,
        "n_cluster": n_cluster,
        "media_cluster_ticks": media_cluster,
        "ic95_cluster_ticks": ic95_cluster,
    }


def fase_result() -> None:
    if not AVALIACOES_CSV.exists():
        raise SystemExit("Rode a fase 'jev' antes.")
    eventos = montar_eventos()

    total_amostra = pd.read_csv(AMOSTRA_CSV) if AMOSTRA_CSV.exists() else None
    n_coletadas_raw = sum(1 for _ in open(RAW_CSV, encoding="utf-8")) - 1 if RAW_CSV.exists() else 0
    n_amostra = len(total_amostra) if total_amostra is not None else len(eventos)
    n_avaliadas = len(pd.read_csv(AVALIACOES_CSV))
    n_nao_neutras = int((eventos["direcao"] != 0).sum())

    print("=" * 78, flush=True)
    print(
        f"manchetes GDELT (linhas brutas): {n_coletadas_raw} | amostra enviada ao Jev: "
        f"{n_amostra} | avaliadas: {n_avaliadas} | com evento de preco valido: {len(eventos)} | "
        f"direcao nao-neutra: {n_nao_neutras}",
        flush=True,
    )
    if len(eventos) > 0:
        print(
            f"periodo dos eventos: {eventos['seendate_utc'].min()} -> "
            f"{eventos['seendate_utc'].max()}",
            flush=True,
        )
    print("=" * 78, flush=True)

    nao_neutras = eventos[eventos["direcao"] != 0]
    subconjuntos = {
        "todas_nao_neutras": nao_neutras,
        "prob_max_ge_0.6": nao_neutras[nao_neutras["p_max"] >= 0.6],
        "sem_relata_preco": nao_neutras[~nao_neutras["relata_preco"]],
        "com_relata_preco": nao_neutras[nao_neutras["relata_preco"]],
    }

    linhas_saida = []
    for nome_sub, sub in subconjuntos.items():
        for h in HORIZONTES:
            r = linha_stats(sub, h)
            if r is None:
                print(f"{nome_sub:20s} h={h:2d}min  n=0 (sem eventos)", flush=True)
                continue
            aviso_cluster = ""
            if r["n_minutos_unicos"] < r["n"]:
                aviso_cluster = (
                    f"  [AVISO: {r['n']} eventos em {r['n_minutos_unicos']} minutos unicos"
                    f" de t0 -- n efetivo por cluster={r['n_cluster']}, media cluster="
                    f"{_fmt(r['media_cluster_ticks'])}t, IC95 cluster=+-{_fmt(r['ic95_cluster_ticks'])}t]"
                )
            print(
                f"{nome_sub:20s} h={h:3d}min  n={r['n']:4d}  "
                f"media={_fmt(r['media_ticks'])}t  desvio={_fmt(r['std_ticks'])}t  "
                f"IC95=+-{_fmt(r['ic95_ticks'])}t  acerto={_fmt(r['acerto_pct'],1)}%  "
                f"p={_fmt(r['p_valor'],4)}  corr_pre={_fmt(r['corr_pre'])}  "
                f"corr_pos={_fmt(r['corr_pos'])}{aviso_cluster}",
                flush=True,
            )
            linhas_saida.append({"subconjunto": nome_sub, "horizonte_min": h, **r})

    pd.DataFrame(linhas_saida).to_csv(TABELA_CSV, index=False)
    print(f"\ntabela gravada em {TABELA_CSV}", flush=True)
    print(f"eventos com preco gravados em {EVENTOS_CSV}", flush=True)


# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="fase", required=True)
    sub.add_parser("probe")
    p_gdelt = sub.add_parser("gdelt")
    p_gdelt.add_argument("--start", type=str, default=GDELT_START.isoformat())
    p_gdelt.add_argument("--end", type=str, default=GDELT_END.isoformat())
    p_gdelt.add_argument("--max-manchetes", type=int, default=500)
    p_gdelt.add_argument("--max-dias", type=int, default=25)
    p_gdelt.add_argument("--orcamento-seg", type=int, default=2400)
    p_jev = sub.add_parser("jev")
    p_jev.add_argument("--workers", type=int, default=8)
    sub.add_parser("result")

    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.fase == "probe":
        fase_probe()
    elif args.fase == "gdelt":
        fase_gdelt(
            date.fromisoformat(args.start),
            date.fromisoformat(args.end),
            max_manchetes=args.max_manchetes,
            max_dias=args.max_dias,
            orcamento_seg=args.orcamento_seg,
        )
    elif args.fase == "jev":
        fase_jev(workers=args.workers)
    elif args.fase == "result":
        fase_result()


if __name__ == "__main__":
    main()
