# -*- coding: utf-8 -*-
"""WIN@ retangulo -- QUAL E' O CAIXA MINIMO para operar o candidato?

Pergunta do dono (2026-09-15). Ela tem tres respostas diferentes e confundi-las
ja custou medicao inteira neste projeto (secao "O piso de capital e' indicacao
de PARTIDA, nunca condicao de continuidade", em CLAUDE.md):

  1. PISO DO INSTRUMENTO -- o que a corretora cobra. WIN@: margem R$100 por
     contrato. Abaixo disso quem recusa e' a corretora.
  2. PISO DE PARTIDA -- margem x buffer(2,0) x reserva(1,25) = **R$250**. E' o
     numero que o painel checa UMA VEZ, ao clicar em "Iniciar operacao".
  3. PISO DESTA ESTRATEGIA -- quanto caixa ela precisa para nao ser CALADA
     pelo proprio prejuizo no meio do caminho. Esse nao sai de tabela: tem de
     ser medido, porque depende do tamanho do stop e da sequencia de perdas.

Toda a medicao do retangulo rodou a R$3.000 (o que o slot usa hoje), nao no
minimo. Este script fecha essa lacuna: roda o desenho congelado partindo de
varios caixas e mostra onde a janela comeca a ficar CENSURADA -- pregoes
pulados por falta de caixa, operacoes que somem, caixa minimo atingido.

Uma janela em que o robo parou de operar nao mede a estrategia, mede a
restricao que o parou. O caixa minimo util e' o menor valor em que o numero
de operacoes ainda bate com o da linha R$3.000.

## O desenho sob teste (congelado)

    W=20 | centro | alvo 0,80xL | stop 0,50xL | largura >= 328 pts |
    re-arma enquanto vive | 1 contrato | custo ida-e-volta 7,5 pontos

Tambem sai a distribuicao do RISCO POR OPERACAO em R$ (o stop e' 0,50 x a
largura do retangulo, e a largura varia a cada lateralizacao), que e' a causa
mecanica de qualquer piso que aparecer.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_escada_capital_2026_09_15.py`
"""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "fecha_cap", Path(__file__).with_name("copawin_retangulo_fechar_abertos_2026_09_15.py"))
_f = importlib.util.module_from_spec(_spec)
sys.modules["fecha_cap"] = _f
_spec.loader.exec_module(_f)

_base = _f._base
SYMBOL = _f.SYMBOL
CORTE_OOS = _f.CORTE_OOS
GEO = _f.GEO

MARGEM_WIN = 100.0
CAPITAIS = (250.0, 275.0, 290.0, 300.0, 325.0, 350.0, 375.0, 400.0,
            500.0, 3000.0)


def _unidade(args):
    """(janela, dias, capital) -> metricas + caixa minimo realizado."""
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import _recua, config_for, profile_for

    janela, dias, capital = args
    strat = _f._estr.RetanguloLab(**dict(GEO, W=20))
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]

    profile = profile_for(SYMBOL)
    cfg = config_for(
        profile, trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=capital, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True, queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
    )
    cfg = dataclasses.replace(cfg, session_end_time=_recua(profile.session_end_time, 5))

    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    c = _base.consistencia(trades, dias)

    # caixa REALIZADO ao longo do caminho (o que o portao de capital enxerga)
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    acum = np.cumsum(seq) if seq else np.array([0.0])
    caixa_min = float(capital + acum.min()) if seq else capital

    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    pior = float(min(perdas)) if perdas else 0.0
    return dict(janela=janela, capital=capital, liquido=c["liquido"], n=c["n"],
                win=c["win"], sem_trade=c["sem_trade"], pregoes=c["pregoes"],
                caixa_min=caixa_min, pior_perda=pior,
                puladas=getattr(res, "sessoes_puladas_por_capital", None))


def _risco_por_operacao(dias):
    """Distribuicao do STOP em R$: 0,50 x largura do retangulo x R$0,20/ponto."""
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import _recua, config_for, profile_for

    strat = _f._estr.RetanguloLab(**dict(GEO, W=20))
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(SYMBOL)
    cfg = config_for(profile, trade_tick_value=0.20, trade_tick_size=1.0,
                     initial_capital=3000.0, target_fills_as_maker=True,
                     limit_fill_capped_by_volume=True,
                     queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
    cfg = dataclasses.replace(cfg, session_end_time=_recua(profile.session_end_time, 5))
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    return np.array([abs(t.pnl_brl) for t in res.trades if t.pnl_brl <= 0], dtype=float)


def main():
    df, dias_todos = _base._df()
    IS = [d for d in dias_todos if d < CORTE_OOS]
    OOS = [d for d in dias_todos if d >= CORTE_OOS]
    JAN = {"IS": IS, "OOS": OOS}

    br = _f.br
    print("=" * 118)
    print("WIN@ retangulo -- ESCADA DE CAPITAL: qual o caixa minimo para operar o candidato?")
    print("=" * 118)
    print(f"  margem WIN@: R$ {br(MARGEM_WIN,0)}/contrato | piso de PARTIDA "
          f"(margem x 2,0 x 1,25) = R$ 250")
    print(f"  desenho congelado: W=20 centro, alvo 0,80xL, stop 0,50xL, "
          f"largura >= 328 pts, 1 contrato")
    print("  o piso UTIL e' o menor caixa em que as operacoes ainda batem com "
          "a linha de R$ 3.000\n", flush=True)

    tarefas = [(jn, dd, cap) for jn, dd in JAN.items() for cap in CAPITAIS]
    out = {}
    feitos = 0
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["janela"], r["capital"])] = r
            feitos += 1
            if feitos % 6 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    for jn in JAN:
        print("\n" + "=" * 118)
        print(f"{jn} -- {len(JAN[jn])} pregoes")
        print("=" * 118)
        hdr = (f"  {'capital':>10}{'liquido':>11}{'retorno':>10}{'trades':>8}{'% das op.':>11}"
               f"{'win%':>7}{'caixa min':>11}{'pior perda':>12}{'sem trade':>12}")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        n_ref = out[(jn, 3000.0)]["n"]
        for cap in CAPITAIS:
            r = out[(jn, cap)]
            ret = r["liquido"] / cap if cap else float("nan")
            marca = ""
            if r["caixa_min"] < MARGEM_WIN:
                marca = "  <- CENSURADA (caixa abaixo da margem)"
            print(f"  {br(cap,0):>10}{br(r['liquido']):>11}{(br(100*ret,0)+'%'):>10}"
                  f"{r['n']:>8}{(br(100*r['n']/n_ref,0)+'%'):>11}"
                  f"{(br(100*r['win'],1)+'%') if r['win']==r['win'] else '--':>7}"
                  f"{br(r['caixa_min']):>11}{br(r['pior_perda']):>12}"
                  f"{str(r['sem_trade'])+'/'+str(r['pregoes']):>12}{marca}")

    print("\n" + "=" * 118)
    print("RISCO POR OPERACAO -- por que o piso e' o que e'")
    print("=" * 118)
    for jn, dd in JAN.items():
        v = _risco_por_operacao(dd)
        if len(v) == 0:
            continue
        print(f"  {jn}: {len(v)} operacoes perdedoras | perda media R$ {br(v.mean())} | "
              f"mediana R$ {br(float(np.median(v)))}")
        print(f"        p75 R$ {br(float(np.quantile(v,.75)))} | "
              f"p90 R$ {br(float(np.quantile(v,.90)))} | "
              f"p99 R$ {br(float(np.quantile(v,.99)))} | "
              f"MAIOR R$ {br(float(v.max()))}")
    print("\n  o stop e' 0,50 x a largura do retangulo, e a largura muda a cada")
    print("  lateralizacao -- entao o risco por operacao NAO e' fixo.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
