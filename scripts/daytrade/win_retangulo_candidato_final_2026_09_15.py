# -*- coding: utf-8 -*-
"""WIN@ retangulo D1 -- A PASSADA FINAL, OOS incluido (UMA UNICA VEZ).

Toda a investigacao anterior (`win_retangulo_criterios_2026_09_15.py`,
`win_retangulo_tol_refinamento_2026_09_15.py`,
`win_retangulo_offset_e_seguranca_2026_09_15.py`) rodou SO' NO IS. O OOS
(>=2026-06-13) nunca foi lido antes deste script -- esta e' a UNICA vez que
ele e' consultado nesta linha de trabalho, com tudo congelado a partir do que
o IS decidiu.

## O que o IS decidiu (recapitulando, tudo medido SO' no IS)

  - Afrouxar a TOLERANCIA de borda (TOL) de 8% para 20% da largura foi o
    UNICO relaxamento de criterio que aumentou trades E liquido E manteve o
    win% confortavelmente acima do breakeven empirico -- ganho vem de
    RECONHECER retangulos que a zona de 8% rejeitava por um triz (o preco
    tocou perto da borda mas nao encostou o suficiente), nao de aceitar
    formas piores.
  - A grade fina (tol x deriva_max x contencao_min) mostrou que desligar
    deriva_max/contencao_min JUNTO com tol alto (>=25%) QUEBRA o desenho
    (liquido negativo, win% abaixo do breakeven) -- e' um PENHASCO, nao um
    platô. tol=20-30% com deriva_max e contencao_min ORIGINAIS e' platô
    (10-35% todos positivos, folga confortavel de win% sobre breakeven).
    Escolhido tol=20%: fica no MEIO do platô seguro, longe do penhasco, com
    caixa minimo realizado (R$405,50 a R$650 de capital) bem acima da
    margem crua (R$100) -- tol=30% rende mais mas deixa so' R$203 de folga.
  - OFFSET de entrada (para qualquer lado do meio exato) so' PIOROU --
    REFUTADO. O meio exato ja' e' o melhor nivel.
  - TETO DE RISCO por operacao (pular quando stop_frac x L x R$0,20 > teto):
    R$80 corta a pior perda de R$110,50 para R$80,50 e melhora o caixa
    minimo realizado de R$405,50 para R$541,90, custando ~14% do liquido
    IS -- e' a alavanca de SEGURANCA, oferecida como variante, nao como
    substituicao.

## As TRES linhas desta tabela final

  1. BASELINE       -- desenho congelado original (tol=8%), inalterado.
  2. CANDIDATO       -- so' tol 8%->20%, resto igual ao baseline.
  3. CANDIDATO+TETO  -- CANDIDATO + teto de risco R$80/operacao.

Capital R$650 (piso medido). WIN@ sem fila calibrada -- queue_ahead_qty=0 e
exit_queue_ahead_qty=0 nas duas pontas, preenchimento no TOQUE (premissa
OTIMISTA, igual em toda a linha do retangulo ate' aqui, vale igualmente para
IS e OOS -- a COMPARACAO entre janelas e' honesta, o NIVEL absoluto nao e'
previsao).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_candidato_final_2026_09_15.py`
"""
from __future__ import annotations

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


def _carrega(nome, apelido):
    spec = importlib.util.spec_from_file_location(apelido, Path(__file__).with_name(nome))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[apelido] = mod
    spec.loader.exec_module(mod)
    return mod


_off = _carrega("win_retangulo_offset_e_seguranca_2026_09_15.py", "off_final")
_estr = _off._estr
_base = _off._base
CAPITAL = _off.CAPITAL
GEO_BASE = _off.GEO_BASE
LARGURA_328 = _off.LARGURA_328
RetanguloOffsetSeguro = _off.RetanguloOffsetSeguro
CORTE_OOS = pd.Timestamp("2026-06-13").date()

VARIANTES = {
    "1 BASELINE (tol=8%, congelado)": dict(GEO_BASE, largura_min_pontos=LARGURA_328,
                                            tol=0.08),
    "2 CANDIDATO (tol=20%)": dict(GEO_BASE, largura_min_pontos=LARGURA_328,
                                   tol=0.20),
    "3 CANDIDATO + teto risco R$80": dict(GEO_BASE, largura_min_pontos=LARGURA_328,
                                           tol=0.20, teto_risco_brl=80.0),
}


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _roda(dias, kw):
    from backtest.intraday.engine import run_intraday_backtest

    strat = RetanguloOffsetSeguro(**kw)
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    cfg, _corte = _base._cfg_com_folga(_estr.FOLGA_PRODUCAO, CAPITAL, strat)
    return run_intraday_backtest(bars, strat, cfg)


def _maxdd_diario(serie: pd.Series) -> float:
    if len(serie) == 0:
        return float("nan")
    eq = serie.cumsum()
    return float((eq.cummax() - eq).max())


def _caixa_realizado(trades, capital):
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    if not seq:
        return capital, capital
    acum = np.cumsum(seq)
    eq_path = capital + acum
    maxdd_trade = float((np.maximum.accumulate(eq_path) - eq_path).max())
    return float(eq_path.min()), maxdd_trade


def _unidade(args):
    janela_nome, rot, dias, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _roda(dias, kw)
    trades = list(res.trades)
    c = _base.consistencia(trades, dias)
    c["maxdd"] = _maxdd_diario(c["serie"])
    caixa_min, maxdd_trade = _caixa_realizado(trades, CAPITAL)
    c["caixa_min"] = caixa_min
    c["maxdd_trade"] = maxdd_trade
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    c["lucro_dd"] = (c["liquido"] / c["maxdd"]) if c["maxdd"] and c["maxdd"] > 0 else float("nan")
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    c["pior_perda"] = float(min(perdas)) if perdas else 0.0
    c.pop("serie", None)
    return dict(janela=janela_nome, rotulo=rot, c=c, res=res)


def _pc(x):
    return (br(100 * x, 1) + "%") if x == x else "--"


def main():
    df, dias_todos = _base._df()
    IS = [d for d in dias_todos if d < CORTE_OOS]
    OOS = [d for d in dias_todos if d >= CORTE_OOS]
    JAN = {"IS (<2026-06-13)": IS, "OOS (>=2026-06-13)": OOS}

    print("=" * 140)
    print("WIN@ retangulo D1 -- PASSADA FINAL, IS + OOS (OOS consultado pela 1a e UNICA vez nesta linha)")
    print("=" * 140)
    print(f"  IS {len(IS)} pregoes ({IS[0]} a {IS[-1]}) | OOS {len(OOS)} pregoes ({OOS[0]} a {OOS[-1]})")
    print(f"  capital R$ {br(CAPITAL,0)} (piso real: MaxDD IS medido + margem R$100, nunca R$3.000)")
    print("  WIN@ sem fila calibrada em fidelidade.py -- queue_ahead_qty=0, exit_queue_ahead_qty=0, "
          "preenchimento no TOQUE nas duas pontas.\n", flush=True)

    tarefas = [(jn, rot, dd, kw) for jn, dd in JAN.items() for rot, kw in VARIANTES.items()]
    print(f"{len(tarefas)} rodadas...\n", flush=True)
    out: dict = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out.setdefault(r["janela"], {})[r["rotulo"]] = r
            c = r["c"]
            print(f"  {r['janela']:<22}{r['rotulo']:<32} liquido={br(c['liquido']).rjust(11)}  "
                  f"trades={c['n']:>5}  win={br(100*c['win'],1) if c['n'] else '--':>5}%  "
                  f"sem_tr={c['sem_trade']:>3}/{c['pregoes']}", flush=True)

    from backtest.intraday.report import linha_de_resultado, tabela

    EXTRAS = ("BEemp%", "veredito", "pts/op", "pior perda", "caixa min", "sem_tr")
    for jn, dd in JAN.items():
        print(f"\n\n===== WIN@ D1, R$ {br(CAPITAL,0)}, 1 contrato -- {jn} ({len(dd)} pregoes) =====")
        linhas = []
        for rot in VARIANTES:
            r = out[jn][rot]
            c = r["c"]
            extras = {
                "BEemp%": (br(100 * c["be"], 1) + "%") if c["be"] == c["be"] else "--",
                "veredito": c["veredito"],
                "pts/op": br(c["pts"], 1) if c["pts"] == c["pts"] else "--",
                "pior perda": br(c["pior_perda"]),
                "caixa min": br(c["caixa_min"]),
                "sem_tr": f"{c['sem_trade']}/{c['pregoes']}",
            }
            linhas.append(linha_de_resultado(rot, r["res"], CAPITAL, extras=extras))
        print(tabela(linhas, extras=EXTRAS))

    print("\n\n" + "=" * 140)
    print("RESUMO LADO A LADO -- IS x OOS, as 3 variantes")
    print("=" * 140)
    hdr = (f"  {'variante':<32}{'IS liq':>11}{'IS trd':>7}{'IS win':>8}{'IS be':>7}"
           f"{'OOS liq':>11}{'OOS trd':>8}{'OOS win':>8}{'OOS be':>7}{'':>4}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for rot in VARIANTES:
        ci = out["IS (<2026-06-13)"][rot]["c"]
        co = out["OOS (>=2026-06-13)"][rot]["c"]
        ok = ci["liquido"] > 0 and co["liquido"] > 0 and ci["win"] > ci["be"] and co["win"] > co["be"]
        print(f"  {rot:<32}{br(ci['liquido']):>11}{ci['n']:>7}{_pc(ci['win']):>8}{_pc(ci['be']):>7}"
              f"{br(co['liquido']):>11}{co['n']:>8}{_pc(co['win']):>8}{_pc(co['be']):>7}"
              f"{('  <<<' if ok else ''):>4}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
