# -*- coding: utf-8 -*-
"""copa_win: quanto CUSTA cada minuto de folga do corte de achatamento?

PERGUNTA DO DONO, 2026-09-14. Em 2026-09-14 o corte de achatamento de fim de
pregao passou a ser "fim do pregao - 5 minutos" (`core.b3_session.
FOLGA_ACHATAMENTO_MINUTOS = 5`; para futuro, `SymbolProfile.flatten_cut_time`,
lido por `config_for` e entregue ao motor como `IntradayBacktestConfig.
session_end_time`). Antes era o fim do pregao CRAVADO, e por isso o
achatamento nunca disparava ao vivo (itens 4.28/4.29 de LICOES_DE_PRODUCAO.md).

A parte MECANICA ja esta' respondida e NAO e' remedida aqui: uma barra M1
rotulada em T so fica consumivel em T+60s, e a janela de atividade fecha no
fim do pregao -- folga de 1min da' 0 tentativas de fechar (o bug de novo),
2min da' 1, 3min da' 2, 5min da' 4. O que falta e' o PRECO de cada minuto, e
e' so' isso que este script mede: `copa_win` (WIN@, config de PRODUCAO
importada DIRETO de `strategy.daytrade.registry._KWARGS_PADRAO`, nunca
redigitada) sob folga de achatamento de 2, 3, 4 e 5 minutos.

Como a folga e' variada: `config_for(profile_for("WIN@"), ...)` monta a
config inteira (custos, capital, teto de contratos etc.) igual sempre; so' o
campo `session_end_time` e' trocado por `dataclasses.replace(cfg,
session_end_time=_recua(profile.session_end_time, N))` -- a MESMA funcao
`_recua` que `backtest.intraday.profiles._futures_profile` usa para computar
`flatten_cut_time` com N=`FOLGA_ACHATAMENTO_MINUTOS`. Nenhum horario e'
digitado a mao aqui; folga=5 reproduz byte a byte o corte de producao (ha'
uma conferencia disso no arranque do script).

Capital: R$3.000 (o que o slot usa hoje). Janelas: IS (<2026-06-13), OOS
(>=2026-06-13) e HISTORICO COMPLETO -- as mesmas tres de
`copawin_parada_dia_is_oos_2026_09_14.py`, que e' o molde deste script (carga
da base, metricas de consistencia, tabela padrao com os mesmos extras,
robustez por data de inicio, paralelismo).

RESSALVAS:
  - WIN@ NAO tem fila calibrada (`backtest/intraday/fidelidade.py` so' tem
    WDO@) -- toda linha aqui assume preenchimento no TOQUE
    (`queue_ahead_qty=0.0`, `exit_queue_ahead_qty=0.0`). Carimbado na tabela.
  - O OOS do WIN@ ja foi gasto varias vezes; nao e' teste cego.
  - Este script NAO escolhe a folga. So' mede o preco de cada minuto e
    imprime a tabela crua -- a decisao e' do dono.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_folga_achatamento_2026_09_14.py`
"""
from __future__ import annotations

import dataclasses
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
BLOCO = 20                          # pregoes por bloco rolante de constancia
HORIZONTE_INICIO = 40               # pregoes a frente, robustez por data de inicio
PASSO_INICIO = 2                    # 1 a cada N pregoes como data de inicio
CAPITAL = 3_000.0                   # o que o slot usa hoje (db/live_process.json)
FOLGAS_MINUTOS = [2, 3, 4, 5]        # 1min e' o bug (0 tentativas) -- fora de proposito

_CACHE: dict = {}


def br(v: float, dec: int = 2) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int):
    """Wilson score, mesma formula/reproducao de
    `copawin_parada_dia_is_oos_2026_09_14.py`."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


def _construir_estrategia():
    """`CopaWin` de PRODUCAO, kwargs vindos direto de
    `registry._KWARGS_PADRAO` -- nunca redigitados aqui."""
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.lab.copa_win import CopaWin
    from strategy.daytrade.registry import _KWARGS_PADRAO

    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = SYMBOL
    return CopaWin(**kwargs)


# ---------------------------------------------------------------------------
# metricas de consistencia (mesmas de copawin_parada_dia_is_oos_2026_09_14.py,
# + contagem/soma explicita das saidas por ACHATAMENTO)
# ---------------------------------------------------------------------------

def consistencia(trades, dias_da_janela):
    por_dia: dict = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    serie = pd.Series([por_dia.get(d, 0.0) for d in dias_da_janela],
                       index=pd.to_datetime(dias_da_janela))

    com_trade = list(por_dia.values())
    preg_pos = sum(1 for v in com_trade if v > 0)

    blocos = [float(serie.iloc[i:i + BLOCO].sum())
              for i in range(0, max(1, len(serie) - BLOCO + 1))]
    blocos_pos = sum(1 for b in blocos if b > 0)

    mes = serie.groupby([serie.index.year, serie.index.month]).sum()
    meses_pos = int((mes > 0).sum())

    ganhos_dia = sorted((v for v in com_trade if v > 0), reverse=True)
    bruto_pos = sum(ganhos_dia)
    top5 = (sum(ganhos_dia[:5]) / bruto_pos) if bruto_pos > 0 else float("nan")

    seq = pior = 0
    for v in serie.values:
        if v < 0:
            seq += 1
            pior = max(pior, seq)
        elif v > 0:
            seq = 0

    liquido = float(serie.sum())
    flat_trades = [t for t in trades if t.exit_reason.value == "forced_flatten"]
    flat = sum(t.pnl_brl for t in flat_trades)
    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = (abs(sum(p) / len(p))) if p else 0.0
    gd = float(pd.Series(g).std(ddof=1)) if len(g) > 1 else 0.0
    pd_ = float(pd.Series(p).std(ddof=1)) if len(p) > 1 else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    ver = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if be == be and n else "--"

    return dict(
        liquido=liquido, n=n, pregoes=len(dias_da_janela),
        com_trade=len(com_trade), sem_trade=len(dias_da_janela) - len(com_trade),
        preg_pos=preg_pos,
        frac_preg=(preg_pos / len(com_trade)) if com_trade else float("nan"),
        blocos=len(blocos), frac_bl=(blocos_pos / len(blocos)) if blocos else float("nan"),
        meses=len(mes), frac_mes=(meses_pos / len(mes)) if len(mes) else float("nan"),
        top5=top5, seq_neg=pior,
        flat_n=len(flat_trades), flat_soma=flat,
        flat_share=(flat / liquido) if liquido else float("nan"),
        win=(len(g) / n) if n else float("nan"), be=be, lo=lo, hi=hi, veredito=ver,
        ganho_medio=gm, perda_media=pm, ganho_dp=gd, perda_dp=pd_,
        pnl_dia_media=float(serie.mean()) if len(serie) else float("nan"),
        pnl_dia_dp=float(serie.std(ddof=1)) if len(serie) > 1 else float("nan"),
        serie=serie,
    )


def _df():
    if "df" not in _CACHE:
        sys.path.insert(0, str(ROOT / "src"))
        from market_data_intraday.storage import load_m1

        df = load_m1(SYMBOL).sort_index()
        contagem = df.groupby(df.index.date).size()
        completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
        _CACHE["df"] = df[[d in set(completos) for d in df.index.date]]
        _CACHE["dias"] = completos
    return _CACHE["df"], _CACHE["dias"]


def _cfg_com_folga(folga_min: int, capital: float, strat):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.profiles import _recua, config_for, profile_for

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
        queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    corte = _recua(profile.session_end_time, folga_min)
    return dataclasses.replace(cfg, session_end_time=corte), corte


def _roda_janela(capital: float, folga_min: int, dias_janela: list):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest

    df, _ = _df()
    alvo = set(dias_janela)
    bars = df[[d in alvo for d in df.index.date]]
    strat = _construir_estrategia()
    cfg, corte = _cfg_com_folga(folga_min, capital, strat)
    res = run_intraday_backtest(bars, strat, cfg)
    return res, corte


def _unidade_tabela(args):
    capital, janela_nome, folga_min, dias_janela = args
    buf = StringIO()
    with redirect_stdout(buf):
        res, corte = _roda_janela(capital, folga_min, dias_janela)
    c = consistencia(list(res.trades), dias_janela)
    return dict(
        capital=capital, janela=janela_nome, folga=folga_min, corte=corte,
        c=c, res=res,
    )


def _unidade_inicio(args):
    capital, folga_min, i_inicio = args
    buf = StringIO()
    with redirect_stdout(buf):
        df, dias = _df()
        janela = dias[i_inicio:i_inicio + HORIZONTE_INICIO]
        res, _ = _roda_janela(capital, folga_min, janela)
    trades = list(res.trades)
    com = len({t.entry_ts.date() for t in trades})
    liquido = sum(t.pnl_brl for t in trades)
    zerou = getattr(res, "wiped_out_at", None) is not None
    calou = (len(janela) - com) > 0
    return dict(
        capital=capital, folga=folga_min, inicio=dias[i_inicio],
        liquido=liquido, positivo=(liquido > 0), zerou=zerou, calou=calou,
        trades=len(trades),
    )


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.profiles import FOLGA_ACHATAMENTO_MINUTOS as _FOLGA_PROD  # noqa: N811
    from backtest.intraday.profiles import _recua, profile_for

    profile = profile_for(SYMBOL)
    # conferencia: folga=5 tem de reproduzir byte a byte o corte de producao.
    corte_5 = _recua(profile.session_end_time, 5)
    assert corte_5 == profile.flatten_cut_time == _recua(profile.session_end_time, _FOLGA_PROD), (
        "folga=5 nao bateu com o corte de producao -- pare e investigue antes de ler qualquer numero"
    )

    df, dias = _df()
    corte_oos = pd.Timestamp("2026-06-13").date()
    janelas = {
        "IS (<2026-06-13)": [d for d in dias if d < corte_oos],
        "OOS (>=2026-06-13)": [d for d in dias if d >= corte_oos],
        "HISTORICO COMPLETO": dias,
    }

    print("=" * 100)
    print("copa_win -- PRECO de cada minuto de folga do corte de achatamento (WIN@, R$3.000)")
    print("=" * 100)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]}), "
          f"IS={len(janelas['IS (<2026-06-13)'])} OOS={len(janelas['OOS (>=2026-06-13)'])}")
    print("config de PRODUCAO importada de registry._KWARGS_PADRAO['copa_win'] "
          "(alvo_vol=7,6 / stop_vol=12,0 / entrada_ttl_barras=5 / entrada_maker=True "
          "/ fatiar_saida_alvo=True) -- nao redigitada aqui.")
    print(f"fim de pregao (perfil, UTC): {profile.session_end_time}  |  "
          f"cortes testados: " + ", ".join(
              f"folga {n}min -> {_recua(profile.session_end_time, n)} UTC" for n in FOLGAS_MINUTOS))
    print("RESSALVA: WIN@ nao tem fila calibrada em fidelidade.py -- toda linha assume "
          "preenchimento no TOQUE (queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0).")
    print("RESSALVA: OOS do WIN@ ja foi gasto varias vezes; nao e' teste cego.\n", flush=True)

    # ---------------- FASE 1: tabela padrao, 4 folgas x 3 janelas ----------------
    tarefas = []
    for janela_nome, dias_janela in janelas.items():
        for folga_min in FOLGAS_MINUTOS:
            tarefas.append((CAPITAL, janela_nome, folga_min, dias_janela))

    print(f"FASE 1: {len(tarefas)} rodadas (tabela padrao)...", flush=True)
    resultados_tabela = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade_tabela, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            chave = r["janela"]
            resultados_tabela.setdefault(chave, {})[r["folga"]] = r
            c = r["c"]
            print(f"  folga={r['folga']}min ({r['corte']} UTC) {r['janela']:<20} "
                  f"liquido={br(c['liquido']).rjust(12)}  trades={c['n']:>5}  "
                  f"sem_trade={c['sem_trade']:>3}d  flat_n={c['flat_n']:>4}  "
                  f"flat$={br(c['flat_soma']).rjust(10)}",
                  flush=True)

    from backtest.intraday.report import linha_de_resultado, tabela

    EXTRAS = ("preg+", "bl20+", "mes+", "top5", "seq-", "flatN", "flat$", "BEemp%", "veredito", "sem_tr")
    for janela_nome in janelas:
        bloco = resultados_tabela[janela_nome]
        print(f"\n\n===== WIN@, R$ {br(CAPITAL,0)} -- {janela_nome} =====")
        linhas = []
        for folga_min in FOLGAS_MINUTOS:
            r = bloco[folga_min]
            c = r["c"]
            nome = f"folga {folga_min}min"
            extras = {
                "preg+": (br(100 * c["frac_preg"], 0) + "%") if c["frac_preg"] == c["frac_preg"] else "--",
                "bl20+": (br(100 * c["frac_bl"], 0) + "%") if c["frac_bl"] == c["frac_bl"] else "--",
                "mes+": (br(100 * c["frac_mes"], 0) + "%") if c["frac_mes"] == c["frac_mes"] else "--",
                "top5": (br(100 * c["top5"], 0) + "%") if c["top5"] == c["top5"] else "--",
                "seq-": str(c["seq_neg"]),
                "flatN": str(c["flat_n"]),
                "flat$": (br(100 * c["flat_share"], 0) + "%") if c["flat_share"] == c["flat_share"] else "--",
                "BEemp%": (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
                "veredito": c["veredito"],
                "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
            }
            linhas.append(linha_de_resultado(nome, r["res"], CAPITAL, extras=extras))
        print(tabela(linhas, extras=EXTRAS))

        print("\n  dispersao (n, media R$, desvio R$) -- trades vencedores / perdedores / dia:")
        for folga_min in FOLGAS_MINUTOS:
            c = bloco[folga_min]["c"]
            ng = int(round(c["win"] * c["n"])) if c["n"] and c["win"] == c["win"] else 0
            npd = c["n"] - ng
            print(f"    folga {folga_min}min         vencedor: n={ng:>4} media={br(c['ganho_medio']).rjust(10)} "
                  f"dp={br(c['ganho_dp']).rjust(9)}  |  perdedor: n={npd:>4} "
                  f"media=-{br(c['perda_media']).rjust(9)} dp={br(c['perda_dp']).rjust(9)}  |  "
                  f"dia: n={c['pregoes']:>3} media={br(c['pnl_dia_media']).rjust(9)} "
                  f"dp={br(c['pnl_dia_dp']).rjust(9)}  |  flat$ absoluto={br(c['flat_soma']).rjust(11)} "
                  f"(n={c['flat_n']})")

        print("\n  DELTA entre folgas consecutivas (liquido e flat$):")
        anterior = None
        for folga_min in FOLGAS_MINUTOS:
            c = bloco[folga_min]["c"]
            if anterior is not None:
                d_liq = c["liquido"] - anterior["liquido"]
                d_flat = c["flat_soma"] - anterior["flat_soma"]
                print(f"    {anterior_folga}min -> {folga_min}min: "
                      f"d(liquido)={br(d_liq).rjust(12)}   d(flat$)={br(d_flat).rjust(12)}   "
                      f"d(flat_n)={c['flat_n'] - anterior['flat_n']:+d}")
            anterior = c
            anterior_folga = folga_min

    # ---------------- FASE 2: robustez por DATA DE INICIO, por folga ----------------
    print("\n\n" + "=" * 100)
    print(f"FASE 2: robustez por DATA DE INICIO -- horizonte fixo {HORIZONTE_INICIO} pregoes, "
          f"R$ {br(CAPITAL,0)}, por folga de achatamento")
    print("=" * 100)
    inicios = list(range(0, len(dias) - HORIZONTE_INICIO + 1, PASSO_INICIO))
    tarefas_inicio = [(CAPITAL, folga_min, i) for folga_min in FOLGAS_MINUTOS for i in inicios]
    print(f"{len(inicios)} inicios x {len(FOLGAS_MINUTOS)} folgas = {len(tarefas_inicio)} rodadas...",
          flush=True)
    por_folga_inicio: dict = {n: [] for n in FOLGAS_MINUTOS}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade_inicio, t): t for t in tarefas_inicio}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            por_folga_inicio[r["folga"]].append(r)
            done += 1
            if done % 60 == 0:
                print(f"  {done}/{len(tarefas_inicio)}", flush=True)

    print(f"\nfracao de DATAS DE INICIO cuja curva acumulada de {HORIZONTE_INICIO} pregoes "
          f"termina POSITIVA, por folga (n={len(inicios)} inicios cada, R$ {br(CAPITAL,0)}):")
    hdr = ("folga".ljust(12) + "positivas".rjust(11) + "zeraram".rjust(9)
           + "calaram".rjust(9) + "liquido mediano".rjust(17) + "liquido medio".rjust(15)
           + "pior liquido".rjust(14) + "desvio".rjust(12))
    print(hdr)
    print("-" * len(hdr))
    resumo_inicio = {}
    for folga_min in FOLGAS_MINUTOS:
        rs = por_folga_inicio[folga_min]
        liq = pd.Series([r["liquido"] for r in rs])
        pos = sum(1 for r in rs if r["positivo"])
        zerou = sum(1 for r in rs if r["zerou"])
        calou = sum(1 for r in rs if r["calou"] and not r["zerou"])
        resumo_inicio[folga_min] = dict(
            frac_pos=pos / len(rs), mediana=float(liq.median()), media=float(liq.mean()),
            pior=float(liq.min()), desvio=float(liq.std(ddof=1)), zerou=zerou, calou=calou,
        )
        print(f"{folga_min}min".ljust(12)
              + (br(100 * pos / len(rs), 1) + "%").rjust(11)
              + str(zerou).rjust(9) + str(calou).rjust(9)
              + br(liq.median()).rjust(17) + br(liq.mean()).rjust(15)
              + br(liq.min()).rjust(14) + br(float(liq.std(ddof=1))).rjust(12))

    print("\nDELTA no PIOR LIQUIDO e no LIQUIDO MEDIANO entre folgas consecutivas (o numero que decide):")
    anterior_f = None
    for folga_min in FOLGAS_MINUTOS:
        r = resumo_inicio[folga_min]
        if anterior_f is not None:
            d_pior = r["pior"] - anterior_f["pior"]
            d_med = r["mediana"] - anterior_f["mediana"]
            d_frac = 100 * (r["frac_pos"] - anterior_f["frac_pos"])
            print(f"  {anterior_folga_min}min -> {folga_min}min: "
                  f"d(pior liquido)={br(d_pior).rjust(12)}   d(mediana)={br(d_med).rjust(12)}   "
                  f"d(frac positivas)={br(d_frac,1).rjust(7)}pp")
        anterior_f = r
        anterior_folga_min = folga_min

    print("\n\nFIM.")


if __name__ == "__main__":
    main()
