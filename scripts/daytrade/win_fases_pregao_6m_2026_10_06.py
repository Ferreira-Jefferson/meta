"""Tabela diaria do WIN por fase do pregao -- pre-abertura, pregao (negociacao continua) e call de fechamento --
nos ultimos 6 meses, a partir dos NEGOCIOS reais (ticks) do WIN$N no MT5.

Fronteiras de cada dia vem da grade oficial da B3 vigente naquela data (`data/b3_grade_horaria_win.csv`).

O que cada fase contem, e por que:
- PRE-ABERTURA: na pre-abertura nao ha negocio -- so oferta e preco teorico. O unico negocio que ela produz e'
  o leilao de abertura, que cruza todas as ordens de uma vez, num preco so, num instante so (que cai entre
  ~09:00 e ~09:04, nao exatamente em 09:00). Por isso inicio = fim = preco do leilao. O preco teorico de 08:55
  nao existe na fonte: o WIN$N so traz `last` (bid=ask=0) e os contratos vencidos nao estao mais no terminal.
- PREGAO: negocios depois do leilao de abertura e antes do fim da negociacao normal da grade.
- POS (CALL DE FECHAMENTO): negocios a partir do fim da negociacao normal -- o leilao de fechamento.

Saida: data/win_fases_pregao_6m.csv (separador ';').

Lacunas de ticks na fonte (v2, 2026-10-06): o MT5 as vezes nao devolve minutos inteiros de ticks (re-baixar nao
resolve: testado COPY_TICKS_ALL/TRADE, WIN$N e WINV26). Cada dia e' conferido minuto a minuto contra o M1 do
WIN$N (`data/comparativo_win_2026/m1_WIN$N.parquet`). Minuto com volume de tick faltando (>15% do M1 e >5 mil
contratos) e' completado pelo M1: volume += (M1 - ticks); maxima/minima do pregao ampliadas pelas do minuto M1;
negocios NAO sao completados. A linha ganha `fonte` = "ticks" ou "ticks+M1" e a `observacao` diz o que veio de onde.
Se os ticks comecam depois de 09:10 mas o M1 tem barras antes (caso 2026-09-24), o leilao de abertura e' lido da 1a
barra M1: preco = open, hora = minuto da barra (os segundos nao existem), volume = ESTIMATIVA (excesso da barra sobre a
mediana das 5 seguintes), negocios idem pelo tick_volume; o preco do 1o negocio continuo nao e' conhecido e fica
igual ao do leilao.
"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GRADE = ROOT / "data" / "b3_grade_horaria_win.csv"
SAIDA = ROOT / "data" / "win_fases_pregao_6m.csv"
M1 = ROOT / "data" / "comparativo_win_2026" / "m1_WIN$N.parquet"
SIMB = "WIN$N"
GAP_REL, GAP_ABS = 0.15, 5000  # minuto com ticks faltando: dif > 15% do M1 e > 5 mil contratos
INICIO, FIM = date(2026, 4, 6), date(2026, 10, 5)  # 6 meses, ate o ultimo pregao completo
JANELA_LEILAO_MS = 5  # o cruzamento do leilao sai em 0-2 ms, num preco so; o continuo comeca ~4 ms depois
INICIO_TARDIO = "09:10"  # primeiro negocio depois disso = abertura ausente na fonte, nao leilao


def grade_do_dia(grade, d):
    ok = grade[(grade.vigencia_inicio <= pd.Timestamp(d)) & (grade.negociacao_inicio.notna())]
    ok = ok[ok.vigencia_fim.isna() | (ok.vigencia_fim >= pd.Timestamp(d))]
    if ok.empty:
        return None
    return ok.sort_values("vigencia_inicio").iloc[-1]


def hhmm(d, s):
    h, m = map(int, s.split(":"))
    return pd.Timestamp(datetime(d.year, d.month, d.day, h, m))


def fase(x):
    if x.empty:
        return dict(ini=None, fim=None, max=None, min=None, vol=0, neg=0, hora_ini=None, hora_fim=None)
    return dict(ini=x["last"].iloc[0], fim=x["last"].iloc[-1], max=x["last"].max(), min=x["last"].min(),
                vol=int(x.volume.sum()), neg=len(x),
                hora_ini=x.ts.iloc[0].strftime("%H:%M:%S.%f")[:-3], hora_fim=x.ts.iloc[-1].strftime("%H:%M:%S.%f")[:-3])


def completa_com_m1(d, x, fim_neg, m1, leilao, preg):
    """Devolve (minutos_lacuna, vol_extra, max_extra, min_extra) -- minutos do continuo com ticks faltando."""
    mm = m1[m1.index.normalize() == pd.Timestamp(d)]
    mm = mm[(mm.index >= hhmm(d, "09:00")) & (mm.index < fim_neg - pd.Timedelta(minutes=1))]
    mm = mm.astype("float64")
    if mm.empty:
        return [], 0, None, None
    tk = x.set_index("ts").volume.astype("float64").resample("1min").sum().reindex(mm.index).fillna(0)
    dif = mm.real_volume - tk
    ruim = dif[(dif > GAP_ABS) & (dif > GAP_REL * mm.real_volume)]
    if ruim.empty:
        return [], 0, None, None
    sel = mm.loc[ruim.index]
    return list(ruim.index), int(ruim.sum()), float(sel.high.max()), float(sel.low.min())


def main():
    m1 = pd.read_parquet(M1)
    grade = pd.read_csv(GRADE, parse_dates=["vigencia_inicio", "vigencia_fim"])
    assert mt5.initialize(), mt5.last_error()
    mt5.symbol_select(SIMB, True)
    linhas, d = [], INICIO
    while d <= FIM:
        if d.weekday() >= 5:
            d += timedelta(days=1); continue
        g = grade_do_dia(grade, d)
        r = mt5.copy_ticks_range(SIMB, datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                                 datetime(d.year, d.month, d.day, 23, 59, tzinfo=timezone.utc), mt5.COPY_TICKS_ALL)
        if r is None or len(r) == 0 or g is None:
            d += timedelta(days=1); continue
        x = pd.DataFrame(r)
        x = x[(x["last"] > 0) & (x.volume > 0)].sort_values("time_msc", kind="stable")
        x["ts"] = pd.to_datetime(x.time_msc, unit="ms")
        fim_neg = hhmm(d, g.negociacao_fim)
        t0 = x.time_msc.iloc[0]
        obs = []
        fonte = "ticks"
        mm_dia = m1[(m1.index.normalize() == pd.Timestamp(d)) & (m1.index >= hhmm(d, "09:00"))]
        leilao_m1 = None
        if x.ts.iloc[0] >= hhmm(d, INICIO_TARDIO) and len(mm_dia) and mm_dia.index[0] < x.ts.iloc[0].floor("min"):
            # ticks comecam tarde mas o M1 tem barras reais antes: o leilao sai da 1a barra M1 (estimado)
            b = mm_dia.iloc[0]; viz = mm_dia.iloc[1:6]
            vol = int(max(0, b.real_volume - viz.real_volume.median()))
            neg = int(max(0, b.tick_volume - viz.tick_volume.median()))
            leilao_m1 = dict(hora=mm_dia.index[0], preco=float(b.open), vol=vol, neg=neg, high=float(b.high), low=float(b.low))
            leilao = x.iloc[0:0]
            fonte = "ticks+M1"
            obs.append(f"ticks da fonte so comecam as {x.ts.iloc[0]:%H:%M:%S}; leilao de abertura lido da 1a barra M1 "
                       f"({mm_dia.index[0]:%H:%M}): preco=open da barra, hora=minuto da barra (sem segundos), "
                       f"volume={vol} ESTIMADO (excesso sobre a mediana das 5 barras seguintes); "
                       f"negocios do leilao desconhecidos (excesso de tick_volume {neg}: o M1 nao traz o numero de negocios; fica {neg}); "
                       f"preco do 1o negocio continuo desconhecido: igual ao do leilao; "
                       f"pregao ate {x.ts.iloc[0]:%H:%M} vem do M1")
        elif x.ts.iloc[0] >= hhmm(d, INICIO_TARDIO):
            # a fonte nao tem o leilao de abertura: nao inventa -- pre fica vazio e o pregao comeca no 1o negocio
            leilao = x.iloc[0:0]
            obs.append(f"sem negocios na fonte antes de {x.ts.iloc[0]:%H:%M:%S}; abertura nao classificada como leilao")
        else:
            p0 = x["last"].iloc[0]
            mesmo = (x["last"] == p0) & (x.time_msc <= t0 + JANELA_LEILAO_MS)
            leilao = x[mesmo.cummin()]
        preg = x.iloc[len(leilao):]
        preg = preg[preg.ts < fim_neg]
        pos = x[x.ts >= fim_neg]
        a, p, c = fase(leilao), fase(preg), fase(pos)
        minutos, vol_extra, mx, mn = completa_com_m1(d, x, fim_neg, m1, leilao, preg)
        if leilao_m1 is not None:
            a = dict(ini=leilao_m1["preco"], fim=leilao_m1["preco"], max=None, min=None, vol=leilao_m1["vol"],
                     neg=leilao_m1["neg"], hora_ini=f"{leilao_m1['hora']:%H:%M:%S}.000", hora_fim=None)
            vol_extra -= leilao_m1["vol"]
            p["hora_ini"] = a["hora_ini"]; p["ini"] = a["ini"]
        if minutos:
            fonte = "ticks+M1"
            p["vol"] += vol_extra
            p["max"] = max(p["max"], mx); p["min"] = min(p["min"], mn)
            ini, fimm = minutos[0], minutos[-1] + pd.Timedelta(minutes=1)
            obs.append(f"{len(minutos)} minuto(s) com ticks faltando na fonte ({ini:%H:%M}-{fimm:%H:%M}); "
                       f"volume, maxima e minima do pregao completados pelo M1 (volume +{vol_extra}); negocios NAO completados")
        linhas.append({
            "data": d.isoformat(), "dia_semana": ["seg", "ter", "qua", "qui", "sex"][d.weekday()],
            "grade_preabertura": g.preabertura_inicio, "grade_negociacao": f"{g.negociacao_inicio}-{g.negociacao_fim}",
            "grade_call": g.call_fechamento_inicio,
            "pre_hora_leilao": a["hora_ini"], "pre_preco_inicio": a["ini"], "pre_preco_fechamento": a["fim"],
            "pre_volume": a["vol"], "pre_negocios": a["neg"],
            "pregao_hora_inicio": p["hora_ini"], "pregao_hora_fim": p["hora_fim"],
            "pregao_preco_inicio": p["ini"], "pregao_maxima": p["max"], "pregao_minima": p["min"],
            "pregao_preco_fechamento": p["fim"], "pregao_volume": p["vol"], "pregao_negocios": p["neg"],
            "pos_hora_leilao": c["hora_ini"], "pos_preco_inicio": c["ini"], "pos_preco_fechamento": c["fim"],
            "pos_volume": c["vol"], "pos_negocios": c["neg"],
            "volume_total_dia": a["vol"] + p["vol"] + c["vol"],
            "pos_leilao_preco_unico": (c["max"] == c["min"]) if c["neg"] else None,
            "fonte": fonte, "observacao": "; ".join(obs),
        })
        print(d, f"leilao {a['hora_ini']} {a['ini']} v={a['vol']} | pregao {p['ini']}->{p['fim']} v={p['vol']} "
                 f"| call {c['hora_ini']} {c['ini']} v={c['vol']}", flush=True)
        d += timedelta(days=1)
    out = pd.DataFrame(linhas)
    out.to_csv(SAIDA, sep=";", index=False, encoding="utf-8-sig")
    print("salvo", SAIDA, len(out), "pregoes", flush=True)


if __name__ == "__main__":
    sys.exit(main())
