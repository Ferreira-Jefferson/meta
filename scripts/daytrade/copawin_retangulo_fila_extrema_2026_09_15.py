# -*- coding: utf-8 -*-
"""WIN@ retangulo -- a cauda da varredura de fila: onde o desenho MORRE.

A varredura principal (`copawin_retangulo_fechar_abertos_2026_09_15.py`, bloco
C) foi ate 25.000 contratos na frente (~1 barra M1 mediana do WIN@) e o
resultado continuava positivo nas duas janelas. Isso e' informacao boa, mas
incompleta: um eixo que nao mata nao prova robustez, so' prova que o intervalo
varrido era curto demais. Aqui ele vai ate 400.000 -- 16 barras medianas de
volume paradas na frente da nossa ordem -- para achar o PONTO DE MORTE e poder
dizer quanta margem existe, em vez de dizer "aguentou tudo que testei".

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_retangulo_fila_extrema_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "fecha_ext", Path(__file__).with_name("copawin_retangulo_fechar_abertos_2026_09_15.py"))
_f = importlib.util.module_from_spec(_spec)
sys.modules["fecha_ext"] = _f
_spec.loader.exec_module(_f)

FILAS = (25_000.0, 50_000.0, 100_000.0, 200_000.0, 400_000.0)
VOL_BARRA_MEDIANA = 24_956.0


def main():
    df, dias = _f._base._df()
    IS = [d for d in dias if d < _f.CORTE_OOS]
    OOS = [d for d in dias if d >= _f.CORTE_OOS]

    print("=" * 104)
    print("WIN@ retangulo -- CAUDA da sensibilidade a fila (ate 16 barras medianas de volume)")
    print("=" * 104)
    print(f"  volume mediano de uma barra M1 do WIN@: {_f.br(VOL_BARRA_MEDIANA,0)} contratos")
    print("  SENSIBILIDADE, nao calibracao -- WIN@ nao tem entrada em fidelidade.py\n",
          flush=True)

    tarefas = []
    for q in FILAS:
        for jn, dd in (("IS", IS), ("OOS", OOS)):
            tarefas.append(("C", jn, f"{q:.0f}", dd, "real", dict(_f.GEO, W=20), q, q))

    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_f._unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["janela"], r["rotulo"])] = r["c"]
            print(f"  ok {r['janela']:<5}{r['rotulo']}", flush=True)

    hdr = (f"\n  {'fila':>10}{'x barra':>9}{'liq IS':>11}{'trd IS':>8}{'win IS':>8}"
           f"{'pts IS':>8}{'liq OOS':>11}{'trd OOS':>9}{'win OOS':>9}{'pts OOS':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 3))
    for q in FILAS:
        a, b = out[("IS", f"{q:.0f}")], out[("OOS", f"{q:.0f}")]
        pc = lambda x: (_f.br(100 * x, 1) + "%") if x == x else "--"
        print(f"  {_f.br(q,0):>10}{_f.br(q/VOL_BARRA_MEDIANA,1):>9}"
              f"{_f.br(a['liquido']):>11}{a['n']:>8}{pc(a['win']):>8}{_f.br(a['pts'],1):>8}"
              f"{_f.br(b['liquido']):>11}{b['n']:>9}{pc(b['win']):>9}{_f.br(b['pts'],1):>9}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
