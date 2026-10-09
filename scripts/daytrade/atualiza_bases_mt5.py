"""Acrescenta às bases versionadas os pregões COMPLETOS que faltam, direto do MT5 (terminal aberto e logado).

  WIN  data/win_sem_leiloes/m1_WIN$N.parquet (CONGELADA) + m1_WIN$N_AAAA-MM.parquet (um por mês)
       Mesmo tratamento da base original (scripts/daytrade/gera_bases_win_sem_leiloes_2026_10_06.py):
       M1 do WIN$N -> fases do pregão medidas pelos NEGÓCIOS (ticks) -> carrega_win_m1_sem_leiloes (tira leilão
       de abertura e call). A conta das fases é a de scripts/daytrade/win_fases_pregao_6m_2026_10_06.py (removido
       na limpeza de 2026-10-07; recuperável com `git show 988e8e4^:<caminho>`), aqui só para os dias novos.
       Validado (2026-10-09) reprocessando 02 e 05/10/2026: preços, volume e marcações idênticos à base.
  WDO  data/wdo-mt5/WDO@D_M1_202109290900_202609291020.csv (CONGELADA) + WDO@D_M1_AAAA-MM.csv (um por mês)
       + bases.csv (quando cada arquivo foi coletado) + ajustes.csv (rolagens detectadas e o deslocamento).
       WDO@D é ajustado por DIFERENÇA: a cada rolagem todo o histórico desloca por uma constante. Em vez de
       regravar 5 anos (o git guardaria o arquivo inteiro de novo todo mês), o deslocamento vai para ajustes.csv,
       medido na sobreposição com a série atual do MT5 (tem de ser constante, senão aborta).

  Leitura: market_data_intraday.bases_versionadas (le_win, le_wdo) junta os pedaços e aplica os ajustes.
Pregão completo = o contínuo da grade (data/b3_grade_horaria_win.csv) acabou há mais de 15 min. O dia em curso
fica de fora (barra final e call ainda não existem); rode de novo depois do fechamento.

Leitura do MT5 sempre por DIA INTEIRO (copy_rates_range numa janela estreita já devolveu horário errado).

Uso: python scripts/daytrade/atualiza_bases_mt5.py            (WIN e WDO)
     python scripts/daytrade/atualiza_bases_mt5.py --so win
"""
import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from market_data_intraday.bases_versionadas import WDO_DIR, le_wdo, le_win, tabelas_wdo  # noqa: E402
from market_data_intraday.win_sem_leiloes import carrega_grade, carrega_win_m1_sem_leiloes, fim_continuo  # noqa: E402

GRADE = ROOT / "data" / "b3_grade_horaria_win.csv"
WIN = ROOT / "data" / "win_sem_leiloes" / "m1_WIN$N.parquet"
MARGEM_FIM = pd.Timedelta(minutes=15)
GAP_REL, GAP_ABS = 0.15, 5000      # minuto com ticks faltando: dif > 15% do M1 e > 5 mil contratos
JANELA_LEILAO_MS = 5               # o leilão cruza em 0-2 ms num preço só; o contínuo começa ~4 ms depois
INICIO_TARDIO = "09:10"            # 1º negócio depois disso = abertura ausente na fonte, não leilão
COLS = ["open", "high", "low", "close", "tick_volume", "real_volume"]


def utc(d, h=0, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)


def m1_do_dia(simb, d):
    r = mt5.copy_rates_range(simb, mt5.TIMEFRAME_M1, utc(d), utc(d, 23, 59))
    if r is None or len(r) == 0:
        return pd.DataFrame(columns=COLS)
    x = pd.DataFrame(r)
    x["time"] = pd.to_datetime(x.time, unit="s")
    x = x.set_index("time").sort_index()
    return x[x.index.normalize() == pd.Timestamp(d)][COLS].astype("float64")


def pregoes_completos(desde, grade):
    """Dias úteis > desde cujo contínuo já acabou (o MT5 diz se houve pregão: dia sem M1 é pulado depois)."""
    agora = pd.Timestamp(datetime.now())
    d, out = desde + timedelta(days=1), []
    while d <= agora.date():
        if d.weekday() < 5 and agora >= fim_continuo(pd.Timestamp(d), grade) + MARGEM_FIM:
            out.append(d)
        d += timedelta(days=1)
    return out


# ------------------------------------------------------------------ WIN: fases por tick (lógica de 2026-10-06)
def _fase(x):
    if x.empty:
        return dict(ini=None, fim=None, max=None, min=None, vol=0, neg=0, hora_ini=None, hora_fim=None)
    return dict(ini=x["last"].iloc[0], fim=x["last"].iloc[-1], max=x["last"].max(), min=x["last"].min(),
                vol=int(x.volume.sum()), neg=len(x),
                hora_ini=x.ts.iloc[0].strftime("%H:%M:%S.%f")[:-3], hora_fim=x.ts.iloc[-1].strftime("%H:%M:%S.%f")[:-3])


def fases_do_dia(d, mm, fim_neg):
    """Uma linha da tabela de fases (colunas que carrega_win_m1_sem_leiloes lê). None se não há ticks."""
    r = mt5.copy_ticks_range("WIN$N", utc(d), utc(d, 23, 59), mt5.COPY_TICKS_ALL)
    if r is None or len(r) == 0:
        return None
    x = pd.DataFrame(r)
    x = x[(x["last"] > 0) & (x.volume > 0)].sort_values("time_msc", kind="stable")
    if x.empty:
        return None
    x["ts"] = pd.to_datetime(x.time_msc, unit="ms")
    t0, obs, fonte = x.time_msc.iloc[0], [], "ticks"
    abre = pd.Timestamp(d) + pd.Timedelta(hours=9)
    tardio = pd.Timestamp(f"{d} {INICIO_TARDIO}")
    mm_dia = mm[mm.index >= abre]
    leilao_m1 = None
    if x.ts.iloc[0] >= tardio and len(mm_dia) and mm_dia.index[0] < x.ts.iloc[0].floor("min"):
        b, viz = mm_dia.iloc[0], mm_dia.iloc[1:6]
        leilao_m1 = dict(hora=mm_dia.index[0], preco=float(b.open), vol=int(max(0, b.real_volume - viz.real_volume.median())),
                         neg=int(max(0, b.tick_volume - viz.tick_volume.median())))
        leilao, fonte = x.iloc[0:0], "ticks+M1"
        obs.append(f"leilão lido da 1a barra M1 ({mm_dia.index[0]:%H:%M}), volume estimado")
    elif x.ts.iloc[0] >= tardio:
        leilao = x.iloc[0:0]
        obs.append(f"sem negócios antes de {x.ts.iloc[0]:%H:%M:%S}; abertura não classificada como leilão")
    else:
        mesmo = (x["last"] == x["last"].iloc[0]) & (x.time_msc <= t0 + JANELA_LEILAO_MS)
        leilao = x[mesmo.cummin()]
    preg = x.iloc[len(leilao):]
    preg, pos = preg[preg.ts < fim_neg], x[x.ts >= fim_neg]
    a, p, c = _fase(leilao), _fase(preg), _fase(pos)
    # minutos do contínuo com ticks faltando: completa volume/máx/mín do pregão pelo M1
    mc = mm[(mm.index >= abre) & (mm.index < fim_neg - pd.Timedelta(minutes=1))]
    extra, falta = 0, False
    if len(mc):
        tk = preg.set_index("ts").volume.astype("float64").resample("1min").sum().reindex(mc.index).fillna(0)
        dif = mc.real_volume - tk
        ruim = dif[(dif > GAP_ABS) & (dif > GAP_REL * mc.real_volume)]
        if len(ruim):
            extra, falta = int(ruim.sum()), True; sel = mc.loc[ruim.index]
            fonte = "ticks+M1"
            p["max"] = max(p["max"], float(sel.high.max())); p["min"] = min(p["min"], float(sel.low.min()))
            obs.append(f"{len(ruim)} minuto(s) com ticks faltando; volume/máx/mín do pregão completados pelo M1")
    if leilao_m1 is not None:
        a = dict(ini=leilao_m1["preco"], fim=leilao_m1["preco"], vol=leilao_m1["vol"], neg=leilao_m1["neg"],
                 hora_ini=f"{leilao_m1['hora']:%H:%M:%S}.000")
        extra -= leilao_m1["vol"]
        p["hora_ini"], p["ini"] = a["hora_ini"], a["ini"]
    if falta:
        p["vol"] += extra
    return {"data": pd.Timestamp(d), "pre_hora_leilao": a["hora_ini"], "pre_preco_inicio": a["ini"],
            "pre_preco_fechamento": a["fim"], "pre_volume": a["vol"], "pre_negocios": a["neg"],
            "pregao_hora_inicio": p["hora_ini"], "pregao_hora_fim": p["hora_fim"], "pregao_preco_inicio": p["ini"],
            "pregao_maxima": p["max"], "pregao_minima": p["min"], "pregao_preco_fechamento": p["fim"],
            "pregao_volume": p["vol"], "pregao_negocios": p["neg"], "pos_hora_leilao": c["hora_ini"],
            "pos_preco_inicio": c["ini"], "pos_preco_fechamento": c["fim"], "pos_volume": c["vol"],
            "pos_negocios": c["neg"], "fonte": fonte, "observacao": "; ".join(obs)}


def grava_pedacos_win(novo):
    """Um parquet por mês ao lado da base congelada (m1_WIN$N_AAAA-MM.parquet); o mês existente é completado."""
    for mes, x in novo.groupby(novo.index.to_period("M")):
        arq = WIN.with_name(f"{WIN.stem}_{mes}.parquet")
        if arq.exists():
            x = pd.concat([pd.read_parquet(arq), x]); x = x[~x.index.duplicated(keep="last")].sort_index()
        x.to_parquet(arq)
        print(f"WIN: {arq.name} com {x.index.normalize().nunique()} pregões", flush=True)


def atualiza_win(grade):
    ultimo = le_win(WIN).index.max().date()
    dias = pregoes_completos(ultimo, grade)
    mt5.symbol_select("WIN$N", True)
    brutos, fases = [], []
    for d in dias:
        mm = m1_do_dia("WIN$N", d)
        if mm.empty:
            print(f"WIN {d}: sem barras no MT5 (feriado?) -- pulado", flush=True); continue
        f = fases_do_dia(d, mm, fim_continuo(pd.Timestamp(d), grade))
        if f is None:
            print(f"WIN {d}: sem ticks -- fica na aproximação sem tick (proxy)", flush=True)
        else:
            fases.append(f)
        brutos.append(mm)
        print(f"WIN {d}: {len(mm)} barras M1, fases {'por tick (' + f['fonte'] + ')' if f else 'AUSENTES'}", flush=True)
    if not brutos:
        print(f"WIN: nada a acrescentar (base até {ultimo})", flush=True); return
    fs = pd.DataFrame(fases) if fases else pd.DataFrame(columns=["data"])
    novo = carrega_win_m1_sem_leiloes(pd.concat(brutos), fases=fs, grade=grade).barras
    grava_pedacos_win(novo)
    print(f"WIN: +{novo.index.normalize().nunique()} pregões, +{len(novo)} barras; série até {novo.index.max()}", flush=True)


# ------------------------------------------------------------------ WDO@D (ajuste por diferença)
def _linhas_mt5(x):
    return pd.DataFrame({"<DATE>": x.index.strftime("%Y.%m.%d"), "<TIME>": x.index.strftime("%H:%M:%S"),
                         "<OPEN>": x.open, "<HIGH>": x.high, "<LOW>": x.low, "<CLOSE>": x.close,
                         "<TICKVOL>": x.tick_volume.astype("int64"), "<VOL>": x.real_volume.astype("int64"),
                         "<SPREAD>": 0}, index=x.index)


def atualiza_wdo(grade):
    """Pedaços mensais WDO@D_M1_AAAA-MM.csv + bases.csv (quando cada arquivo foi coletado) + ajustes.csv (rolagens)."""
    agora = pd.Timestamp(datetime.now()).floor("s")
    atual = le_wdo(WDO_DIR)
    ultimo = atual.index.max().date()
    mt5.symbol_select("WDO@D", True)
    dias = [ultimo] + pregoes_completos(ultimo, grade)       # o último dia gravado costuma estar incompleto
    novos = {d: m1_do_dia("WDO@D", d) for d in dias}
    # rolagem desde a última coleta: o MT5 mostra o histórico deslocado por uma constante
    sob = novos[ultimo].join(atual[atual.index.normalize() == pd.Timestamp(ultimo)][["<OPEN>", "<CLOSE>"]], how="inner")
    if sob.empty:
        raise SystemExit(f"WDO: sem sobreposição em {ultimo} para medir o ajuste")
    dc = (sob.close - sob["<CLOSE>"]).round(3).to_numpy(); do = (sob.open - sob["<OPEN>"]).round(3).to_numpy()
    if not (np.allclose(dc, dc[0]) and np.allclose(do, dc[0])):
        raise SystemExit(f"WDO: deslocamento não é constante na sobreposição ({dc.min()} a {dc.max()}): não emendo")
    delta = float(dc[0])
    bases, ajustes = tabelas_wdo(WDO_DIR)
    if delta:
        ajustes = pd.concat([ajustes, pd.DataFrame({"detectado_em": [agora], "delta": [delta]})])
        ajustes.to_csv(WDO_DIR / "ajustes.csv", sep=";", index=False, date_format="%Y-%m-%d %H:%M:%S", float_format="%.3f")
        print(f"WDO: rolagem detectada, histórico deslocado {delta:+.3f}", flush=True)
    linhas = [_linhas_mt5(x) for d, x in novos.items() if not x.empty]
    if len(linhas) <= 1 and novos[ultimo].index.max() <= atual.index.max():
        print(f"WDO: nada a acrescentar (base até {atual.index.max()})", flush=True); return
    novo = pd.concat(linhas)
    for mes, x in novo.groupby(novo.index.to_period("M")):
        nome = f"WDO@D_M1_{mes}.csv"
        if (WDO_DIR / nome).exists():                         # completa o mês já gravado, trazido ao ajuste de hoje
            antigo = pd.read_csv(WDO_DIR / nome, sep="\t")
            antigo = le_wdo(WDO_DIR).loc[pd.to_datetime(antigo["<DATE>"] + " " + antigo["<TIME>"], format="%Y.%m.%d %H:%M:%S")]
            x = pd.concat([antigo, x]); x = x[~x.index.duplicated(keep="last")].sort_index()
        x.to_csv(WDO_DIR / nome, sep="\t", index=False, float_format="%.3f")
        bases = pd.concat([bases[bases.arquivo != nome], pd.DataFrame({"arquivo": [nome], "coletado_em": [agora]})])
        print(f"WDO: {nome} com {x.index.normalize().nunique()} pregões", flush=True)
    bases.to_csv(WDO_DIR / "bases.csv", sep=";", index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"WDO: série até {novo.index.max()}", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", choices=["win", "wdo"])
    a = ap.parse_args()
    assert mt5.initialize(), mt5.last_error()
    grade = carrega_grade(GRADE)
    if a.so in (None, "win"): atualiza_win(grade)
    if a.so in (None, "wdo"): atualiza_wdo(grade)
    mt5.shutdown()


if __name__ == "__main__":
    main()
