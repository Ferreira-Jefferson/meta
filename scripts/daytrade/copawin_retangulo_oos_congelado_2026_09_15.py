# -*- coding: utf-8 -*-
"""WIN@ retangulo -- A PASSADA NO OOS, com o desenho CONGELADO.

Ordem do dono (2026-09-15): "rode em oos".

Toda a investigacao do retangulo (detector, geometria alvo/stop, politica de
re-armar, janela de deteccao W=20, piso de largura, filtro de volume) foi feita
DENTRO do IS, exatamente para que este script exista: uma passada so', com
tudo fixo, sobre os pregoes >= 2026-06-13 que nunca foram lidos nesta linha.

## O que esta congelado, e de onde cada numero veio (TODOS medidos no IS)

    W                    = 20      escolha do dono apos a medicao de deteccao
                                   precoce (ganho 1,78x sobre o nulo, 8 barras
                                   de antecedencia)
    modo                 = centro  D1 do dono: limite no meio do retangulo
    alvo_frac            = 1,60    => alvo a 0,80xL do centro (a matriz de
                                   trajetoria mostrou que o alvo tem de ser
                                   MAIOR, nao menor que os 90% iniciais)
    stop_frac            = 0,50    => stop na borda oposta
    max_barras_apos      = None    plato de 43/44 celulas na varredura
    uma_por_retangulo    = False   re-armar enquanto o retangulo vive
    barras_extra_morte   = 0
    largura_min_pontos   = 328,0   terco SUPERIOR da largura do W=20 NO IS
    vol_por_ponto_max    = 94,617  terco INFERIOR do volume/ponto NO IS

Os dois limiares sao HARDCODED nos valores do IS de proposito. Recalcular o
quantil dentro do OOS usaria a janela cega para definir o parametro, que e'
exatamente o que a janela cega nao pode fazer.

## As linhas da tabela

  1. CANDIDATO          -- o desenho congelado acima. E' a unica linha que
                           conta como teste. As outras sao contexto.
  2. sem filtro de vol  -- o pai imediato. A pergunta do dono era se o volume
                           torna os trades mais confiaveis; sem o pai ao lado a
                           resposta nao existe.
  3. sem filtro nenhum  -- W=20 operando todo retangulo. Mede quanto os dois
                           filtros carregam.
  4. W=30 largos (ref)  -- a janela anterior, para saber se trocar W ajudou.

## Premissa de execucao declarada

WIN@ nao tem fila calibrada em `fidelidade.py` (so' o WDO@), entao este
backtest roda com `queue_ahead_qty=0` nas duas pontas: **toda ordem-limite
preenche no TOQUE**. E' a premissa OTIMISTA. Ela vale igual no IS e no OOS,
entao a COMPARACAO entre janelas e' honesta; o NIVEL nao e' previsao.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_oos_congelado_2026_09_15.py`
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

_spec = importlib.util.spec_from_file_location(
    "estr_oos", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_oos"] = _estr
_spec.loader.exec_module(_estr)

_base = _estr._base
CAPITAL = _estr.CAPITAL
CORTE_OOS = pd.Timestamp("2026-06-13").date()

LARGURA_IS_Q67 = 328.0      # congelado: terco superior da largura W=20 no IS
VOL_PONTO_IS_Q33 = 94.617   # congelado: terco inferior de volume/ponto no IS
LARGURA_W30_IS = 401.0

GEO = dict(modo="centro", alvo_frac=1.6, stop_frac=0.5,
           max_barras_apos=None, uma_por_retangulo=False,
           barras_extra_apos_morte=0)

VARIANTES = [
    ("1 CANDIDATO  W20 largo+vol", dict(GEO, W=20, largura_min_pontos=LARGURA_IS_Q67,
                                        vol_por_ponto_max=VOL_PONTO_IS_Q33)),
    ("2 W20 largo, sem filtro vol", dict(GEO, W=20, largura_min_pontos=LARGURA_IS_Q67)),
    ("3 W20 todos, sem filtro", dict(GEO, W=20, largura_min_pontos=0.0)),
    ("4 W30 largos (referencia)", dict(GEO, W=30, largura_min_pontos=LARGURA_W30_IS)),
]


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _maxdd(serie: pd.Series) -> float:
    if len(serie) == 0:
        return float("nan")
    eq = serie.cumsum()
    return float((eq.cummax() - eq).max())


def _unidade(args):
    janela, rotulo, dias, kw = args
    buf = StringIO()
    with redirect_stdout(buf):
        res = _estr._roda(dias, **kw)
    c = _base.consistencia(list(res.trades), dias)
    c["maxdd"] = _maxdd(c["serie"])
    c["pts"] = (c["liquido"] / c["n"]) / 0.20 if c["n"] else float("nan")
    c["lucro_dd"] = (c["liquido"] / c["maxdd"]) if c["maxdd"] and c["maxdd"] > 0 else float("nan")
    c.pop("serie", None)
    return dict(janela=janela, rotulo=rotulo, c=c)


def main():
    df, dias_todos = _base._df()
    janelas = {
        "IS  (< 2026-06-13)": [d for d in dias_todos if d < CORTE_OOS],
        "OOS (>= 2026-06-13)": [d for d in dias_todos if d >= CORTE_OOS],
    }

    print("=" * 126)
    print("WIN@ retangulo -- PASSADA NO OOS COM O DESENHO CONGELADO")
    print("=" * 126)
    for nome, dd in janelas.items():
        print(f"  {nome}: {len(dd)} pregoes  ({dd[0]} a {dd[-1]})")
    print()
    print("  congelado (todos os numeros medidos NO IS):")
    print("    W=20 | modo centro | alvo 0,80xL | stop 0,50xL | re-arma enquanto vive |")
    print(f"    largura minima {br(LARGURA_IS_Q67,0)} pts (q67 do IS) | "
          f"volume/ponto <= {br(VOL_PONTO_IS_Q33,3)} (q33 do IS)")
    print(f"    1 contrato | capital R$ {br(CAPITAL,0)} | custo ida-e-volta 7,5 pontos")
    print("  premissa de execucao: WIN@ SEM fila calibrada -> limite preenche no TOQUE")
    print("    (otimista, mas IDENTICA nas duas janelas)\n", flush=True)

    tarefas = [(jn, rot, dd, kw) for jn, dd in janelas.items() for rot, kw in VARIANTES]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): (t[0], t[1]) for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["janela"], r["rotulo"])] = r["c"]
            print(f"  ok {r['janela']:<22}{r['rotulo']}", flush=True)

    hdr = (f"  {'variante':<30}{'liquido':>11}{'trades':>8}{'win%':>7}{'BEemp%':>9}"
           f"{'IC95 win':>16}{'veredito':>12}{'pts/op':>9}{'MaxDD':>10}{'luc/DD':>9}"
           f"{'preg+':>7}{'bl20+':>7}{'seq-':>6}{'sem_tr':>9}")
    for nome in janelas:
        print("\n" + "=" * 126)
        print(nome)
        print("=" * 126)
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for rot, _kw in VARIANTES:
            c = out[(nome, rot)]
            pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
            ic = f"[{br(100*c['lo'],1)} ; {br(100*c['hi'],1)}]" if c["n"] else "--"
            print(f"  {rot:<30}{br(c['liquido']):>11}{c['n']:>8}{pc(c['win']):>7}"
                  f"{pc(c['be']):>9}{ic:>16}{c['veredito']:>12}{br(c['pts'],2):>9}"
                  f"{br(c['maxdd']):>10}{br(c['lucro_dd'],2):>9}"
                  f"{pc(c['frac_preg']):>7}{pc(c['frac_bl']):>7}{c['seq_neg']:>6}"
                  f"{str(c['sem_trade'])+'/'+str(c['pregoes']):>9}")

    print("\n" + "=" * 126)
    print("IS x OOS -- o que replica e o que inverte")
    print("=" * 126)
    h2 = (f"  {'variante':<30}{'liq IS':>11}{'liq OOS':>11}{'pts IS':>9}{'pts OOS':>9}"
          f"{'win IS':>8}{'win OOS':>9}{'BE IS':>8}{'BE OOS':>8}{'sinal':>12}")
    print(h2)
    print("  " + "-" * (len(h2) - 2))
    ks = list(janelas)
    for rot, _kw in VARIANTES:
        a, b = out[(ks[0], rot)], out[(ks[1], rot)]
        if a["liquido"] > 0 and b["liquido"] > 0:
            sinal = "replica +"
        elif a["liquido"] < 0 and b["liquido"] < 0:
            sinal = "replica -"
        else:
            sinal = "INVERTE"
        pc = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
        print(f"  {rot:<30}{br(a['liquido']):>11}{br(b['liquido']):>11}"
              f"{br(a['pts'],2):>9}{br(b['pts'],2):>9}"
              f"{pc(a['win']):>8}{pc(b['win']):>9}{pc(a['be']):>8}{pc(b['be']):>8}"
              f"{sinal:>12}")

    print("\n  veredito = IC95 do win% contra o breakeven EMPIRICO (nulo certo):")
    print("             POSITIVO so' se o intervalo inteiro fica ACIMA do breakeven.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
