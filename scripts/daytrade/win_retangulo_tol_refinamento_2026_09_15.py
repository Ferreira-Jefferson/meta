# -*- coding: utf-8 -*-
"""WIN@ retangulo D1 -- REFINAMENTO do achado da FASE 1/2 de
`win_retangulo_criterios_2026_09_15.py`: afrouxar a TOLERANCIA de borda
(TOL, a zona em fracao da largura que conta como "toque") foi o UNICO
relaxamento que aumentou trades E liquido E manteve win% acima do breakeven
empirico -- 8%->20% deu 615 trades / R$4.366,70 (baseline: 403 / R$2.834,10),
e cruzado com "sem deriva_max" (desligar o teste de horizontalidade) deu
732 trades / R$5.055,40, sem_tr caindo de 33/129 para 4/129 pregoes.

Isto NAO e' o resultado final -- e' o candidato que sobrou da FASE 1/2, e
precisa de tres coisas antes de virar recomendacao (tudo AINDA no IS):

  1. GRADE FINA em tol x deriva_max (e' plato ou pico isolado? 0,20 foi o
     maior valor testado -- sera' que 0,25/0,30 continua subindo ou já
     inverteu?), cruzada com "sem contencao_min" (a 3a melhor alavanca
     isolada, nao entrou na FASE 2 por criterio de corte de trades).
  2. CAIXA REALIZADO ao longo da sequencia cronologica de trades (nao so' o
     MaxDD por serie DIARIA agregada, que pode esconder o caminho intra-dia)
     -- e' o mesmo cuidado de `copawin_retangulo_escada_capital_2026_09_15.py`:
     uma janela onde o motor teria recusado entrada por capital insuficiente
     e' censurada, nao mede a estrategia.
  3. Robustez por BLOCO (20 pregoes rolantes) e sequencia de perdas -- um
     liquido maior construido em cima de MENOS pregoes positivos nao e'
     melhora, e' concentracao.

Capital: R$650 (piso medido, nunca R$3.000). SO' O IS -- o OOS fica
intocado ate' este script escolher UM candidato final.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_tol_refinamento_2026_09_15.py`
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


_crit = _carrega("win_retangulo_criterios_2026_09_15.py", "crit_ref")
_estr = _crit._estr
_base = _crit._base
CAPITAL = _crit.CAPITAL
GEO_BASE = _crit.GEO_BASE
LARGURA_328 = _crit.LARGURA_328
RetanguloFlex = _crit.RetanguloFlex
CORTE_OOS = pd.Timestamp("2026-06-13").date()


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _roda(dias, kw):
    from backtest.intraday.engine import run_intraday_backtest

    strat = RetanguloFlex(**kw)
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
    """Caixa MINIMO ao longo da sequencia CRONOLOGICA de trades (nao da serie
    diaria agregada) -- o que o motor de verdade enxerga a cada fechamento.
    Mesmo metodo de `copawin_retangulo_escada_capital_2026_09_15.py`."""
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    if not seq:
        return capital, capital
    acum = np.cumsum(seq)
    eq_path = capital + acum
    maxdd_trade = float((np.maximum.accumulate(eq_path) - eq_path).max())
    return float(eq_path.min()), maxdd_trade


def _unidade(args):
    fase, rot, dias, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _roda(dias, kw)
    trades = list(res.trades)
    c = _base.consistencia(trades, dias)
    c["maxdd_diario"] = _maxdd_diario(c["serie"])
    caixa_min, maxdd_trade = _caixa_realizado(trades, CAPITAL)
    c["caixa_min"] = caixa_min
    c["maxdd_trade"] = maxdd_trade
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    c["lucro_dd"] = (c["liquido"] / c["maxdd_trade"]) if c["maxdd_trade"] and c["maxdd_trade"] > 0 else float("nan")
    c.pop("serie", None)
    return dict(fase=fase, rotulo=rot, c=c)


def _pc(x):
    return (br(100 * x, 1) + "%") if x == x else "--"


def main():
    df, dias_todos = _base._df()
    IS = [d for d in dias_todos if d < CORTE_OOS]

    print("=" * 140)
    print("WIN@ retangulo D1 -- REFINAMENTO DO ACHADO (tolerancia de borda) -- SO' NO IS")
    print("=" * 140)
    print(f"  IS: {len(IS)} pregoes | capital R$ {br(CAPITAL,0)} | margem WIN@ R$100/contrato\n", flush=True)

    TOLS = (0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35)
    DERIVAS = {"deriva original (25%)": 0.25, "sem deriva_max": float("inf")}
    CONTENCAO = {"contencao original (95%)": 0.95, "sem contencao_min": 0.0}

    tarefas = []
    for tol in TOLS:
        for rd, dv in DERIVAS.items():
            for rc, cv in CONTENCAO.items():
                rot = f"tol {int(tol*100)}% | {rd} | {rc}"
                tarefas.append(("grade", rot, IS,
                                dict(GEO_BASE, largura_min_pontos=LARGURA_328,
                                     tol=tol, deriva_max=dv, contencao_min=cv)))

    print(f"{len(tarefas)} rodadas (grade tol x deriva x contencao)...\n", flush=True)
    out = {}
    feitos = 0
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out[r["rotulo"]] = r["c"]
            feitos += 1
            if feitos % 12 == 0:
                print(f"  ... {feitos}/{len(tarefas)}", flush=True)

    print("\n" + "=" * 140)
    print("GRADE COMPLETA (IS) -- ordenada por liquido")
    print("=" * 140)
    hdr = (f"  {'variante':<48}{'liquido':>11}{'trades':>8}{'win%':>7}{'be%':>7}"
           f"{'pts/op':>8}{'MaxDD trd':>11}{'luc/DD':>8}{'caixa min':>11}{'sem_tr':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for rot, c in sorted(out.items(), key=lambda kv: kv[1]["liquido"], reverse=True):
        print(f"  {rot:<48}{br(c['liquido']):>11}{c['n']:>8}{_pc(c['win']):>7}{_pc(c['be']):>7}"
              f"{br(c['pts'],1):>8}{br(c['maxdd_trade']):>11}{br(c['lucro_dd'],2):>8}"
              f"{br(c['caixa_min']):>11}{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")

    print("\n" + "=" * 140)
    print("SO' TOL, deriva/contencao ORIGINAIS (isola o efeito puro da tolerancia)")
    print("=" * 140)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for tol in TOLS:
        rot = f"tol {int(tol*100)}% | deriva original (25%) | contencao original (95%)"
        c = out[rot]
        print(f"  {rot:<48}{br(c['liquido']):>11}{c['n']:>8}{_pc(c['win']):>7}{_pc(c['be']):>7}"
              f"{br(c['pts'],1):>8}{br(c['maxdd_trade']):>11}{br(c['lucro_dd'],2):>8}"
              f"{br(c['caixa_min']):>11}{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")

    melhor_rot = max(out, key=lambda r: out[r]["liquido"])
    melhor = out[melhor_rot]
    baseline = out["tol 8% | deriva original (25%) | contencao original (95%)"]

    print("\n" + "=" * 140)
    print(f"MELHOR CELULA DA GRADE (por liquido): {melhor_rot}")
    print("=" * 140)
    print(f"  liquido {br(melhor['liquido'])} (baseline {br(baseline['liquido'])}) | "
          f"trades {melhor['n']} (baseline {baseline['n']}) | win {_pc(melhor['win'])} "
          f"vs be {_pc(melhor['be'])} | pts/op {br(melhor['pts'],1)} (baseline {br(baseline['pts'],1)}) | "
          f"MaxDD(trades) {br(melhor['maxdd_trade'])} (baseline {br(baseline['maxdd_trade'])}) | "
          f"lucro/DD {br(melhor['lucro_dd'],2)} (baseline {br(baseline['lucro_dd'],2)}) | "
          f"caixa minimo realizado {br(melhor['caixa_min'])} (capital R$ {br(CAPITAL,0)}) | "
          f"sem_trade {melhor['sem_trade']}/{melhor['pregoes']} (baseline {baseline['sem_trade']}/{baseline['pregoes']})")
    if melhor["caixa_min"] < 100.0:
        print("  ALERTA: caixa minimo realizado FICOU ABAIXO da margem crua (R$100) em algum ponto do "
              "caminho -- esta janela seria CENSURADA pelo motor real (recusa de entrada por capital "
              "insuficiente); o numero acima superestima o que a producao entregaria.")
    else:
        print("  caixa minimo realizado ficou ACIMA da margem crua (R$100) o tempo todo -- "
              "nenhuma censura por capital nesta janela, a R$650.")

    print("\n  robustez (consistencia() completa da melhor celula):")
    print(f"    blocos de 20 pregoes positivos: {_pc(melhor['frac_bl'])} | "
          f"pregoes com trade positivos: {_pc(melhor['frac_preg'])} | "
          f"pior sequencia de pregoes negativos seguidos: {melhor['seq_neg']} | "
          f"top5 dias / lucro bruto: {_pc(melhor['top5'])}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
