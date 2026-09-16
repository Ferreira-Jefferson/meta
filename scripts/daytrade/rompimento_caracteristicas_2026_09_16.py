# -*- coding: utf-8 -*-
"""ROMPIMENTO de retângulo: CARACTERÍSTICAS do evento e o que elas predizem.

Pedido do dono (2026-09-16): "medir quantos rompimentos acontecem por pregão,
quais as características, tamanhos, volumes, etc". Este script é o território
das CARACTERÍSTICAS -- não redefine o fenômeno (isso é
`rompimento_retangulo_fenomeno_2026_09_16.py`, território separado) nem a
anatomia dos desfechos: ele IMPORTA de lá `excursao`/`quem_chega_primeiro`/
`HORIZONTE` para garantir que o alvo medido aqui é o MESMO alvo, e usa isso só
como RÓTULO para testar se alguma característica observável NO INSTANTE do
rompimento prediz o resultado.

## O aviso que governa a leitura deste script

No `wdo_orb` foram testadas 15 variáveis no momento do sinal e NENHUMA
previu a operação perdedora (`wdo_orb_perfil_operacao_sem_preditor_2026_09_14`)
-- só o MAE separava, e MAE é pós-resultado, logo inútil para decidir. A
taxa-base deste tipo de investigação no projeto é próxima de zero. Isso não é
motivo para não medir -- é motivo para relatar refutação com o mesmo cuidado
de um achado, e desconfiar de qualquer variável que "funcione" sem mecanismo.

## As DUAS armadilhas de método já identificadas nesta linha -- evitadas aqui

1. Ponto de referência com vantagem de largada: o rompimento só é DETECTADO
   ~263 pontos além da borda (mediana). Toda característica e todo desfecho
   aqui usam o preço/instante de DETECÇÃO, nunca a borda, como ponto zero.
2. "Anda X a favor antes de X contra" não é `MFE>=X e MAE<X`. O desfecho
   binário usa `quem_chega_primeiro` (índice do primeiro toque), importado
   -- não redefinido -- do script do fenômeno.

## Rótulo (desfecho), para servir de alvo às características

`outcome_continuo = MFE - MAE` a partir do preço de detecção, horizonte de
`HORIZONTE` barras (60, herdado do script do fenômeno). Positivo = a
excursão a favor superou a excursão contra; é a versão contínua, mais
informativa que o binário para correlação de posto.

`favor_60` = 1 se +60 pontos é tocado antes de -60 (a partir da detecção),
0 se o contrário, NaN se nenhum dos dois no horizonte -- o mesmo
`quem_chega_primeiro` do script do fenômeno, no limiar central da tabela
deles. Serve de tabela de "% a favor" por quartil, mais fácil de ler que a
média contínua.

## Sem look-ahead

Toda característica é computável NO INSTANTE do rompimento (barra `i`, a
3a barra fora da banda): usa só `high/low/close/volume[:i+1]` e o histórico
do próprio retângulo (`nascimento..i`). `ordem_no_dia` conta rompimentos
JÁ ACONTECIDOS naquele pregão -- nunca o total do dia (que exigiria ver o
futuro do próprio pregão).

## Regras duras herdadas do pedido

Só IS (< 2026-06-13, 129 pregões). `MIN_BARRAS_POR_PREGAO=400`. Retângulo:
`detecta_retangulo` de produção (W=20, tolerância 0,20, largura mínima 328).
Correlação de posto (Spearman) calculada manualmente via `rank()` +
`corrcoef` -- projeto não depende de scipy (ver `pyproject.toml`), e
`pandas.Series.corr(method="spearman")` já cobre o cálculo sem a
dependência extra. Significância aproximada via `SE(rho) ~= 1/sqrt(n-1)`
(assintótica, sem scipy), marcada com `*` quando `|rho| > 1,96*SE`.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/rompimento_caracteristicas_2026_09_16.py`
"""
from __future__ import annotations

import importlib.util
import itertools
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.lab.win_retangulo import (  # noqa: E402
    BARRAS_MORTE, MARGEM_MORTE, detecta_retangulo)


def _carrega(nome, apelido):
    spec = importlib.util.spec_from_file_location(apelido, Path(__file__).with_name(nome))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Território dos DESFECHOS: importa, não redefine.
_fen = _carrega("rompimento_retangulo_fenomeno_2026_09_16.py", "_fen_caract")

SIMBOLO = "WIN@"
JANELA = 20
TOLERANCIA = 0.20
LARGURA_MINIMA = 328.0
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
HORIZONTE = _fen.HORIZONTE
LIMIARES_ALVO = (40, 60, 100)
LIMIAR_PRIMARIO = 60


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x):
    if x is None or x != x:
        return "—"
    return br(100 * x, 1) + "%"


def _volume(g: pd.DataFrame) -> np.ndarray:
    real = g["real_volume"].fillna(0.0).to_numpy(float) if "real_volume" in g.columns \
        else np.zeros(len(g))
    tickv = g["tick_volume"].fillna(0.0).to_numpy(float) if "tick_volume" in g.columns \
        else np.zeros(len(g))
    return np.where(real > 0, real, tickv)


@lru_cache(maxsize=1)
def _df_completo() -> pd.DataFrame:
    return load_m1(SIMBOLO).sort_index()


@lru_cache(maxsize=1)
def _dias_todos() -> tuple:
    df = _df_completo()
    return tuple(sorted(set(df.index.date)))


def eventos_do_pregao(dia_iso: str) -> list[dict]:
    """Todo rompimento validado naquele pregão, com features causais e o
    desfecho importado do território dos DESFECHOS."""
    df = _df_completo()
    d = pd.Timestamp(dia_iso).date()
    g = df[df.index.date == d]
    if len(g) < MIN_BARRAS_POR_PREGAO:
        return []

    dias = _dias_todos()
    pos = dias.index(d)
    prev_close = float("nan")
    if pos > 0:
        gp = df[df.index.date == dias[pos - 1]]
        if len(gp):
            prev_close = float(gp["close"].iloc[-1])

    h = g["high"].to_numpy(float)
    l = g["low"].to_numpy(float)
    c = g["close"].to_numpy(float)
    o = g["open"].to_numpy(float)
    vol = _volume(g)
    horas_utc = g.index.hour.to_numpy(float)
    minutos_utc = g.index.minute.to_numpy(float)
    hora_brt = ((horas_utc + minutos_utc / 60.0) - 3.0) % 24.0
    n = len(g)
    open_dia = float(o[0])
    weekday = d.weekday()

    ret = None
    fora = 0
    nascimento = 0
    ordem = 0
    achados: list[dict] = []
    i = 3 * JANELA
    while i < n:
        if ret is None:
            anterior = float(h[i - 3 * JANELA:i - JANELA].max()
                             - l[i - 3 * JANELA:i - JANELA].min())
            r = detecta_retangulo(h[i - JANELA:i], l[i - JANELA:i], c[i - JANELA:i],
                                  anterior, tolerancia=TOLERANCIA)
            if r is not None and r["largura"] >= LARGURA_MINIMA:
                ret, fora, nascimento = r, 0, i
            i += 1
            continue
        margem = MARGEM_MORTE * ret["largura"]
        acima = c[i] > ret["topo"] + margem
        abaixo = c[i] < ret["piso"] - margem
        if acima or abaixo:
            fora += 1
            if fora >= BARRAS_MORTE:
                lado = "alta" if acima else "baixa"
                borda = float(ret["topo"] if acima else ret["piso"])
                preco_deteccao = float(c[i])
                ordem += 1
                largura = float(ret["largura"])

                amplitude_dia = float(h[:i + 1].max() - l[:i + 1].min())
                largura_rel_dia = largura / amplitude_dia if amplitude_dia > 0 else float("nan")
                barras_vivo = i - nascimento
                afastamento_pts = (preco_deteccao - borda) if lado == "alta" \
                    else (borda - preco_deteccao)
                afastamento_rel = afastamento_pts / largura if largura > 0 else float("nan")

                j0 = i - BARRAS_MORTE + 1
                amp3_pts = float(h[j0:i + 1].max() - l[j0:i + 1].min())
                amp3_rel = amp3_pts / largura if largura > 0 else float("nan")
                vol_romp = float(vol[j0:i + 1].mean())
                vol_ret = float(vol[nascimento:i].mean()) if i > nascimento else float("nan")
                vol_ratio_romp_ret = (vol_romp / vol_ret
                                      if vol_ret == vol_ret and vol_ret > 0 else float("nan"))

                dia_high = float(h[:i + 1].max())
                dia_low = float(l[:i + 1].min())
                dist_topo_pts = dia_high - preco_deteccao
                dist_fundo_pts = preco_deteccao - dia_low
                posicao_no_range = ((preco_deteccao - dia_low) / (dia_high - dia_low)
                                    if dia_high > dia_low else float("nan"))

                tendencia_bps = 10000.0 * (preco_deteccao - open_dia) / open_dia \
                    if open_dia else float("nan")
                gap_pts = (open_dia - prev_close) if prev_close == prev_close else float("nan")

                # Desfecho: TERRITÓRIO ALHEIO, só importado.
                e_det = _fen.excursao(g, i, lado, preco_deteccao, horizonte=HORIZONTE)
                mfe, mae = e_det["mfe"], e_det["mae"]
                outcome_continuo = (mfe - mae) if (mfe == mfe and mae == mae) else float("nan")
                favores = {}
                for t in LIMIARES_ALVO:
                    res = _fen.quem_chega_primeiro(g, i, lado, preco_deteccao, t,
                                                   horizonte=HORIZONTE)
                    favores[f"favor_{t}"] = float("nan") if res is None else (1.0 if res else 0.0)

                achados.append(dict(
                    dia=dia_iso, idx=i, lado=lado,
                    direcao=1.0 if lado == "alta" else 0.0,
                    vol_acum_dia=float(vol[:i + 1].sum()),
                    largura_pts=largura, largura_rel_dia=largura_rel_dia,
                    barras_vivo=float(barras_vivo), hora_brt=float(hora_brt[i]),
                    toques_totais=float(ret["toques_topo"] + ret["toques_piso"]),
                    visitas_totais=float(ret["visitas_topo"] + ret["visitas_piso"]),
                    trocas=float(ret["trocas"]), cruzamentos=float(ret["cruzamentos"]),
                    contencao=float(ret["contencao"]), deriva_frac=float(ret["deriva_frac"]),
                    contracao=float(ret["contracao"]),
                    afastamento_pts=afastamento_pts, afastamento_rel=afastamento_rel,
                    amp3_pts=amp3_pts, amp3_rel=amp3_rel,
                    vol_ratio_romp_retangulo=vol_ratio_romp_ret,
                    dist_topo_pts=dist_topo_pts, dist_fundo_pts=dist_fundo_pts,
                    posicao_no_range_dia=posicao_no_range,
                    tendencia_bps=tendencia_bps, gap_pts=gap_pts,
                    dia_semana=float(weekday), ordem_no_dia=float(ordem),
                    outcome_continuo=outcome_continuo, **favores,
                ))
                ret, fora = None, 0
        else:
            fora = 0
        i += 1
    return achados


def volume_baseline(dias: list) -> dict:
    """Mediana do volume ACUMULADO do pregão até a barra `idx`, através dos
    dias -- o "típico" contra o qual o volume acumulado de cada rompimento é
    comparado. Cálculo cru (não precisa de paralelismo: soma ~72 mil barras)."""
    df = _df_completo()
    por_idx: dict[int, list] = {}
    for d in dias:
        g = df[df.index.date == d]
        cum = np.cumsum(_volume(g))
        for idx, v in enumerate(cum):
            por_idx.setdefault(idx, []).append(v)
    return {idx: float(np.median(vs)) for idx, vs in por_idx.items()}


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    ok = x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 30:
        return float("nan"), n
    rx, ry = x.rank(), y.rank()
    rho = float(np.corrcoef(rx, ry)[0, 1])
    return rho, n


def reporta_feature(d: pd.DataFrame, col: str, rotulo: str) -> dict | None:
    s = d[col].replace([np.inf, -np.inf], np.nan)
    dd = d.assign(_f=s).dropna(subset=["_f", "outcome_continuo"])
    n = len(dd)
    if n < 60:
        print(f"  {rotulo:<34} n={n:<4}  amostra insuficiente (<60) — não avaliada", flush=True)
        return None
    rho, n_rho = spearman(dd["_f"], dd["outcome_continuo"])
    se = 1.0 / np.sqrt(max(n_rho - 1, 1))
    limiar_sig = 1.96 * se
    sig = "*" if abs(rho) > limiar_sig else " "
    nun = dd["_f"].nunique()
    if nun <= 5:
        dd = dd.copy()
        dd["grp"] = dd["_f"]
    else:
        try:
            dd = dd.copy()
            dd["grp"] = pd.qcut(dd["_f"], 4, labels=["Q1(baixo)", "Q2", "Q3", "Q4(alto)"],
                                duplicates="drop")
        except Exception:
            dd = dd.copy()
            dd["grp"] = pd.qcut(dd["_f"].rank(method="first"), 4,
                                labels=["Q1(baixo)", "Q2", "Q3", "Q4(alto)"])
    print(f"  {rotulo:<34} n={n:<5} rho={br(rho,3):>7}{sig} "
          f"(limiar~{br(limiar_sig,3)} p/5%)", flush=True)
    for grp, gd in dd.groupby("grp", observed=True):
        m = gd["outcome_continuo"].mean()
        sdv = gd["outcome_continuo"].std(ddof=1) if len(gd) > 1 else float("nan")
        win = gd["favor_60"].mean() if "favor_60" in gd else float("nan")
        print(f"      {str(grp):<14} n={len(gd):<5} outcome méd={br(m,1):>9} "
              f"desvio={br(sdv,1) if sdv==sdv else '—':>7}  favor60%={_pct(win):>7}", flush=True)
    return dict(rotulo=rotulo, col=col, n=n, rho=rho, sig=bool(abs(rho) > limiar_sig))


def main():
    df = _df_completo()
    cont = df.groupby(df.index.date).size()
    dias_is = sorted(d for d, k in cont.items() if k >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    print("=" * 148)
    print("ROMPIMENTO DE RETÂNGULO — CARACTERÍSTICAS do evento e o que elas predizem (IS apenas)")
    print("=" * 148)
    print(f"  {SIMBOLO} M1 | {len(dias_is)} pregões | {dias_is[0]} a {dias_is[-1]}")
    print(f"  retângulo W={JANELA}, tolerância {TOLERANCIA}, largura mínima {br(LARGURA_MINIMA,0)}")
    print(f"  desfecho importado do território dos DESFECHOS: outcome_continuo=MFE-MAE, "
          f"favor_{LIMIAR_PRIMARIO}=quem chega primeiro, horizonte {HORIZONTE} barras\n", flush=True)

    print("Calculando linha de base de volume acumulado por barra (todos os pregões IS)...",
          flush=True)
    baseline = volume_baseline(dias_is)

    eventos: list[dict] = []
    print(f"Detectando rompimentos em {len(dias_is)} pregões (paralelo)...", flush=True)
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(eventos_do_pregao, str(d)): d for d in dias_is}
        feitos = 0
        for fut in as_completed(futs):
            d = futs[fut]
            rs = fut.result()
            eventos.extend(rs)
            feitos += 1
            print(f"  [{feitos:>3}/{len(dias_is)}] {d}: {len(rs)} rompimento(s)", flush=True)

    ev = pd.DataFrame(eventos)
    ev["vol_dia_relativo"] = ev.apply(
        lambda row: row["vol_acum_dia"] / baseline[int(row["idx"])]
        if int(row["idx"]) in baseline and baseline[int(row["idx"])] > 0 else np.nan, axis=1)

    n = len(ev)
    dias_com_evento = ev.groupby("dia").size()
    rompimentos_por_dia = pd.Series(0, index=[str(d) for d in dias_is])
    rompimentos_por_dia.update(dias_com_evento)

    print("\n" + "=" * 148)
    print("(A) PERFIL DESCRITIVO DO ROMPIMENTO TÍPICO — média, mediana, desvio, n")
    print("=" * 148)
    print(f"  rompimentos: n={n} em {len(dias_is)} pregões — "
          f"média {br(rompimentos_por_dia.mean(),2)}/pregão, mediana {br(rompimentos_por_dia.median(),1)}, "
          f"desvio {br(rompimentos_por_dia.std(ddof=1),2)}, min {int(rompimentos_por_dia.min())}, "
          f"max {int(rompimentos_por_dia.max())}")
    print(f"  pregões sem NENHUM rompimento: {int((rompimentos_por_dia==0).sum())} de {len(dias_is)} "
          f"({_pct((rompimentos_por_dia==0).mean())})")
    alta = int((ev["direcao"] == 1).sum())
    print(f"  direção: ALTA {alta} ({_pct(alta/n)})  BAIXA {n-alta} ({_pct((n-alta)/n)})")

    def _linha(col, rotulo, dec=1):
        s = ev[col].replace([np.inf, -np.inf], np.nan).dropna()
        print(f"  {rotulo:<38} média {br(s.mean(),dec):>9}  mediana {br(s.median(),dec):>9}  "
              f"desvio {br(s.std(ddof=1),dec):>9}  n={len(s)}")

    for col, rot in [
        ("largura_pts", "largura do retângulo (pts)"),
        ("barras_vivo", "vida do retângulo até romper (barras)"),
        ("afastamento_pts", "já andou da borda até detecção (pts)"),
        ("amp3_pts", "amplitude das 3 barras do rompimento (pts)"),
        ("toques_totais", "toques totais (topo+piso)"),
        ("cruzamentos", "cruzamentos do meio"),
        ("vol_ratio_romp_retangulo", "volume rompimento / volume médio retângulo"),
        ("vol_dia_relativo", "volume acumulado do dia / típico no mesmo instante"),
        ("hora_brt", "hora do rompimento (BRT, 0-24)"),
    ]:
        _linha(col, rot, dec=3 if "ratio" in col or "relativo" in col else 1)

    print("\n" + "=" * 148)
    print("(B) TODAS AS CARACTERÍSTICAS TESTADAS CONTRA O DESFECHO (outcome=MFE-MAE, "
          f"favor{LIMIAR_PRIMARIO}%=quem chega primeiro em +{LIMIAR_PRIMARIO}/-{LIMIAR_PRIMARIO})")
    print("=" * 148)
    print("  rho = Spearman manual (rank+corrcoef); '*' = |rho| > limiar assintótico de 5% "
          "(SE~1/sqrt(n-1), sem scipy)\n")

    FEATURES = [
        ("largura_pts", "largura do retângulo (pts)"),
        ("largura_rel_dia", "largura / amplitude do dia até ali"),
        ("barras_vivo", "duração do retângulo (barras)"),
        ("hora_brt", "hora da sessão (BRT)"),
        ("toques_totais", "toques totais (topo+piso)"),
        ("visitas_totais", "visitas totais (topo+piso)"),
        ("trocas", "trocas de lado"),
        ("cruzamentos", "cruzamentos do meio"),
        ("contencao", "contenção da banda"),
        ("deriva_frac", "deriva (fração da largura)"),
        ("contracao", "contração vs 2W barras anteriores"),
        ("afastamento_pts", "já andou da borda até detecção (pts)"),
        ("afastamento_rel", "já andou / largura"),
        ("amp3_pts", "amplitude das 3 barras do rompimento (pts)"),
        ("amp3_rel", "amplitude das 3 barras / largura"),
        ("vol_ratio_romp_retangulo", "volume rompimento / volume médio retângulo"),
        ("vol_dia_relativo", "volume acumulado do dia / típico no instante"),
        ("dist_topo_pts", "distância ao topo do dia (pts)"),
        ("dist_fundo_pts", "distância ao fundo do dia (pts)"),
        ("posicao_no_range_dia", "posição no range do dia (0=fundo,1=topo)"),
        ("tendencia_bps", "tendência do pregão até ali (bps desde a abertura)"),
        ("gap_pts", "gap de abertura vs fechamento anterior (pts) [rollover contamina]"),
        ("dia_semana", "dia da semana (0=seg..4=sex)"),
        ("direcao", "direção (1=alta, 0=baixa)"),
        ("ordem_no_dia", "ordem do rompimento no pregão (1o, 2o, ...)"),
    ]
    print(f"  *** {len(FEATURES)} características testadas, uma a uma, contra o mesmo desfecho ***\n")

    resultados = []
    for col, rot in FEATURES:
        r = reporta_feature(ev, col, rot)
        if r is not None:
            resultados.append(r)

    n_sig = sum(1 for r in resultados if r["sig"])
    print(f"\n  resumo: {len(resultados)} características avaliadas, {n_sig} com |rho| acima do "
          f"limiar assintótico de 5% — sob H0 pura, esperar-se-iam ~{br(0.05*len(resultados),1)} "
          "por acaso.")

    print("\n" + "=" * 148)
    print("(C) VOLUME — rodada própria (pedido explícito do dono)")
    print("=" * 148)
    print("  conjectura clássica: 'rompimento com volume CONTINUA, sem volume FALHA'.")
    vr = next((r for r in resultados if r["col"] == "vol_ratio_romp_retangulo"), None)
    vd = next((r for r in resultados if r["col"] == "vol_dia_relativo"), None)
    for r, nome in [(vr, "volume do rompimento / volume médio do retângulo"),
                    (vd, "volume acumulado do dia / típico no instante")]:
        if r is None:
            print(f"  {nome}: não avaliável (amostra insuficiente).")
        else:
            veredito = "SOBREVIVE (rho significativo)" if r["sig"] else "NÃO sobrevive (dentro do ruído)"
            print(f"  {nome}: rho={br(r['rho'],3)} — {veredito}")
    print("  ver tabela por quartil em (B) para os dois — a leitura decisiva é lá: quartil "
          "extremo isolado ('sorte no extremo') não conta como sinal.")

    print("\n" + "=" * 148)
    print("(D) ORDEM DO ROMPIMENTO NO PREGÃO — o 1o é diferente do 3o?")
    print("=" * 148)
    print(f"  {'ordem':<10}{'n':>7}{'outcome méd':>14}{'desvio':>10}{'favor60%':>11}")
    ev["ordem_grp"] = ev["ordem_no_dia"].clip(upper=3).map({1.0: "1o", 2.0: "2o", 3.0: "3o+"})
    for grp, gd in ev.groupby("ordem_grp", observed=True):
        m = gd["outcome_continuo"].mean()
        sdv = gd["outcome_continuo"].std(ddof=1) if len(gd) > 1 else float("nan")
        win = gd["favor_60"].mean()
        print(f"  {grp:<10}{len(gd):>7}{br(m,1):>14}{br(sdv,1) if sdv==sdv else '—':>10}"
              f"{_pct(win):>11}")

    print("\n" + "=" * 148)
    print("(E) COMBINAÇÕES — pares dentre o TOP-5 |rho| isolado (declarado, controla o número)")
    print("=" * 148)
    top5 = sorted(resultados, key=lambda r: abs(r["rho"]) if r["rho"] == r["rho"] else 0,
                  reverse=True)[:5]
    pares = list(itertools.combinations([r["col"] for r in top5], 2))
    print(f"  top-5 por |rho| isolado: {[r['rotulo'] for r in top5]}")
    print(f"  *** {len(pares)} combinações testadas (pares do top-5) *** — a alpha=5%, "
          f"esperar-se-ia ~{br(0.05*len(pares),2)} positiva por acaso, somada aos "
          f"~{br(0.05*len(resultados),1)} já esperados em (B)\n")
    for a, b in pares:
        dd = ev[[a, b, "outcome_continuo"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(dd) < 80:
            print(f"  {a} x {b}: amostra insuficiente ({len(dd)})")
            continue
        ma, mb = dd[a].median(), dd[b].median()
        quads = {
            "lo/lo": dd[(dd[a] <= ma) & (dd[b] <= mb)],
            "lo/hi": dd[(dd[a] <= ma) & (dd[b] > mb)],
            "hi/lo": dd[(dd[a] > ma) & (dd[b] <= mb)],
            "hi/hi": dd[(dd[a] > ma) & (dd[b] > mb)],
        }
        print(f"  {a} (mediana {br(ma,2)}) x {b} (mediana {br(mb,2)}):")
        for k, g in quads.items():
            m = g["outcome_continuo"].mean() if len(g) else float("nan")
            print(f"      {k:<8} n={len(g):<5} outcome méd={br(m,1)}")

    print("\n" + "=" * 148)
    print("COMO LER")
    print("=" * 148)
    print("  * Território: CARACTERÍSTICAS do rompimento e o que predizem. O fenômeno em si")
    print("    (existe? continua? retesta?) é medido em rompimento_retangulo_fenomeno_2026_09_16.py.")
    print("  * Toda característica é causal: computável na barra do rompimento, sem look-ahead.")
    print(f"  * {len(FEATURES)} características testadas isoladamente + {len(pares)} combinações —")
    print("    ambos os números contam para o total de comparações feitas nesta rodada.")
    print("  * Só o IS. A janela cega fica intacta para o que sobreviver.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
