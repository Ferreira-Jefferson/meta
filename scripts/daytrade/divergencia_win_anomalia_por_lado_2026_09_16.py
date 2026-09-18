# -*- coding: utf-8 -*-
"""Fecha a ÚNICA ponta solta do catálogo de divergência (2026-09-16).

O catálogo (`divergencia_oscilador_catalogo_2026_09_16.py`) deu 0 de 48
células significativas na corrida simétrica — a métrica declarada como
decisória. Mas o deslocamento assinado em H=60 barras ficou NEGATIVO nas 8
células do WIN@ (REGULAR e OCULTA), contra ~0 no CONTROLE e ~0 na linha
incondicional, e ~0 em todas as células do WDO@.

Isso não pode ser edge direcional, e o motivo é aritmético: num pivô de TOPO,
`REGULAR` entra VENDIDO e `OCULTA` entra COMPRADO. Se os dois perdem, o que
perde não é o lado — é o instante. Mas "não pode ser" é argumento, não
medição, e argumento não fecha achado.

Este script parte os mesmos eventos por TIPO DE PIVÔ (topo × fundo) e por
LADO (short × long). As duas leituras possíveis:

  (a) dentro de cada tipo de pivô os dois grupos perdem -> é ARTEFATO DE
      ENTRADA: entrar na abertura seguinte à confirmação (L barras depois do
      extremo) paga um pedágio que independe da direção. Nada a explorar,
      e vale como aviso de método para qualquer sinal confirmado por pivô.

  (b) a perda se concentra num lado -> sobra um viés direcional do WIN@ no
      período, que NÃO é divergência (o CONTROLE teria de mostrá-lo também) e
      que a corrida simétrica já rejeitou em ±4/±8/±16 ticks.

Só IS, mesmos parâmetros do catálogo, nenhum limiar novo.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/divergencia_win_anomalia_por_lado_2026_09_16.py`
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

_spec = importlib.util.spec_from_file_location(
    "_cat_div", Path(__file__).with_name("divergencia_oscilador_catalogo_2026_09_16.py"))
_cat = importlib.util.module_from_spec(_spec)
sys.modules["_cat_div"] = _cat
_spec.loader.exec_module(_cat)

from core.indicators import ifr  # noqa: E402
from core.instruments import economics_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

br, ic95, z_vs_meio, Z95 = _cat.br, _cat.ic95, _cat.z_vs_meio, _cat.Z95


def coleta(simbolo: str, nome_osc: str, L: int) -> pd.DataFrame:
    tick = economics_for(simbolo).price_tick_size
    df = load_m1(simbolo)
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df = df.copy()
    df.index = idx.tz_convert(_cat.SAO_PAULO)
    linhas: list[dict] = []
    for dia, g in df.groupby(df.index.normalize()):
        if dia.date() >= _cat.CORTE_OOS or len(g) < _cat.MIN_BARRAS_POR_PREGAO:
            continue
        osc = (ifr(g["close"], window=14) if nome_osc == "IFR14"
               else _cat.macd_linha(g["close"]))
        evs = _cat.eventos_do_pregao(g, osc, L)
        medidos = _cat.mede_eventos(g, evs, tick, dia.date())
        for ev, m in zip(evs, medidos):
            m["topo"] = ev["topo"]
            linhas.append(m)
    return pd.DataFrame(linhas)


def main() -> None:
    print("DIVERGÊNCIA — a anomalia do WIN@ partida por TIPO DE PIVÔ e por LADO (só IS)\n")
    print("Se dentro do MESMO tipo de pivô os dois grupos perdem, a perda é do INSTANTE,")
    print("não da direção — e não há nada a inverter.\n")

    for nome_osc, L in (("MACD", 5), ("IFR14", 3)):
        for simbolo in ("WIN@", "WDO@"):
            ev = coleta(simbolo, nome_osc, L)
            print("=" * 100)
            print(f"{simbolo} · {nome_osc} · L={L}    (n={len(ev)})")
            print("=" * 100)
            print(f"  {'pivô':<8}{'grupo':<11}{'lado':<8}{'n':>6}"
                  f"{'H=60 mediana':>16}{'H=60 média ± IC95':>26}{'corrida ±16t':>15}{'z':>8}")
            print("  " + "-" * 96)
            for topo in (True, False):
                for grupo in ("REGULAR", "OCULTA", "CONTROLE"):
                    sub = ev[(ev["topo"] == topo) & (ev["grupo"] == grupo)]
                    if sub.empty:
                        continue
                    lado = "short" if int(sub["lado"].iloc[0]) < 0 else "long"
                    x = sub["desl_60"].to_numpy(float)
                    mu = float(np.mean(x))
                    e = Z95 * float(np.std(x, ddof=1)) / np.sqrt(len(x)) if len(x) > 1 else float("nan")
                    r = sub["corrida_16"]
                    k, p = int((r == 1).sum()), int((r == -1).sum())
                    win = f"{br(100 * k / (k + p), 2)}%" if (k + p) else "—"
                    print(f"  {'topo' if topo else 'fundo':<8}{grupo:<11}{lado:<8}{len(sub):>6}"
                          f"{br(float(np.median(x)), 2):>16}"
                          f"{br(mu, 2) + ' ± ' + br(e, 2):>26}{win:>15}"
                          f"{br(z_vs_meio(k, k + p), 2):>8}")
            print()


if __name__ == "__main__":
    main()
