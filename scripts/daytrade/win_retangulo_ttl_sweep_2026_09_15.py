# -*- coding: utf-8 -*-
"""Varredura do `ttl_barras` da ENTRADA do `win_retangulo` -- {5, 8, 10, 15,
20, 30} -- nas duas janelas (IS/OOS), medindo o par (n, win%) de cada celula
e o ATRASO REALIZADO de preenchimento em minutos (mediana/p90), nao o prazo
nominal.

## Por que esta e' a frente C do pedido do dono

`ttl_barras=10` (producao) e' o corte entre "retangulo que virou operacao" e
"retangulo que expirou sem preencher". Alargar o prazo pode aumentar n (mais
tempo para o preco alcancar o meio do retangulo) -- mas AGENTS.md/CLAUDE.md ja
tem um precedente MEDIDO onde alargar prazo trouxe fill 269,7 minutos depois
do sinal, e os fills atrasados foram os PIORES resultados. `win_retangulo` e'
base M1 (nao tick), entao aqui 1 barra ~= 1 minuto de verdade (ao contrario do
robo tick onde `ttl_bars` NAO e' tempo) -- mas o atraso REALIZADO ainda pode
divergir do nominal por gaps de pregao, e por isso e' medido, nao assumido.

O que se procura: uma celula que aumente n SEM derrubar win%, dentro de um
PLATO que replique nas duas janelas -- nao um pico de uma so'.

## O que NAO muda

Geometria (alvo/stop), tolerancia de borda, largura minima, teto de risco e
capital (R$1.100, o piso MEDIDO do robo com ttl=10 -- nao recalculado por
celula: mudar o TTL nao muda o tamanho do stop, so' a CHANCE de a ordem
preencher, entao o pior-caso por operacao nao piora estruturalmente. Se uma
celula candidata sobreviver, o piso e' reconferido separadamente antes de
qualquer recomendacao.).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_ttl_sweep_2026_09_15.py`
"""
from __future__ import annotations

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

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import EnterLimit  # noqa: E402
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
#: HOJE fica de FORA das duas janelas, sempre -- mesma regra da regua oficial
#: (`win_retangulo_regua_padrao_2026_09_15.py`). Nao e' so' o pregao de hoje
#: estar PARCIAL na hora em que a regua oficial rodou: o dado de hoje pode
#: crescer DURANTE esta sessao de trabalho (measured: WIN@ tinha 501 barras
#: ao rodar este sweep, ja acima do piso de completude de 400) e ainda assim
#: nao ter passado pelo achatamento oficial das 18:20 BRT -- incluir um
#: pregao que so' PARECE completo contaminaria OOS sem aviso.
HOJE = pd.Timestamp("2026-09-15").date()
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 1_100.0
TTLS = (5, 8, 10, 15, 20, 30)
EXTRAS = ("pts/op", "BEemp%", "veredito", "sem trade", "atraso mediana(min)", "atraso p90(min)")


class WinRetanguloComAtraso(WinRetangulo):
    """Mesmo robo, so' que registra o instante do sinal (`EnterLimit`) e o
    instante do preenchimento real (`IntradayOpenPosition.entry_ts`), para
    medir o atraso REALIZADO -- e nao o prazo nominal em barras."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._sinal_ts = None
        self._entradas_vistas = set()
        self.atrasos_min: list[float] = []

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._sinal_ts = None

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        for acao in acoes:
            if isinstance(acao, EnterLimit):
                self._sinal_ts = ts
        if positions:
            pos = positions[0]
            chave = (pos.entry_ts, pos.side)
            if chave not in self._entradas_vistas and self._sinal_ts is not None:
                self._entradas_vistas.add(chave)
                atraso = (pos.entry_ts - self._sinal_ts).total_seconds() / 60.0
                if atraso >= 0:
                    self.atrasos_min.append(atraso)
                self._sinal_ts = None
        return acoes


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ic95(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - r) / d, (c + r) / d


def _unidade(args):
    rotulo, dias, ttl = args
    strat = WinRetanguloComAtraso(
        janela_barras=20,
        largura_minima_pontos=328.0,
        alvo_fracao_largura=0.80,
        stop_fracao_largura=0.50,
        ttl_barras=ttl,
        quantidade=1,
        tolerancia_borda=0.20,
        risco_maximo_brl=80.0,
    )
    df = load_m1("WIN@").sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(strat.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=CAPITAL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)

    trades = list(res.trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    lo, hi = _ic95(len(g), len(trades))
    veredito = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if be == be and trades else "--"
    com_trade = {t.exit_ts.date() for t in trades}
    pts = ((sum(t.pnl_brl for t in trades) / len(trades)) / 0.20) if trades else float("nan")
    atrasos = np.array(strat.atrasos_min) if strat.atrasos_min else np.array([])

    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "veredito": veredito,
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}",
        "atraso mediana(min)": br(float(np.median(atrasos)), 1) if len(atrasos) else "—",
        "atraso p90(min)": br(float(np.percentile(atrasos, 90)), 1) if len(atrasos) else "—",
    }
    linha = linha_de_resultado(f"TTL={ttl} {rotulo}", res, CAPITAL, extras=extras)
    return dict(rotulo=rotulo, ttl=ttl, linha=linha, ic=(lo, hi), be=be, n=len(trades),
                win=len(g), atrasos=atrasos)


def main():
    df = load_m1("WIN@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    print("=" * 160)
    print("win_retangulo -- VARREDURA de ttl_barras da entrada, IS e OOS, capital R$1.100")
    print("=" * 160)
    print(f"  IS {len(IS)} pregoes | OOS {len(OOS)} pregoes | TTLs testados: {TTLS}\n", flush=True)

    tarefas = []
    for ttl in TTLS:
        tarefas.append((f"IS  ttl={ttl:>2}", IS, ttl))
        tarefas.append((f"OOS ttl={ttl:>2}", OOS, ttl))

    out = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            key = (r["ttl"], r["rotulo"])
            out[key] = r
            print(f"  ok ttl={r['ttl']:>2} {r['rotulo']}: n={r['n']} win={r['win']}", flush=True)

    linhas_is = [out[(ttl, f"IS  ttl={ttl:>2}")]["linha"] for ttl in TTLS]
    linhas_oos = [out[(ttl, f"OOS ttl={ttl:>2}")]["linha"] for ttl in TTLS]

    print("\n" + "=" * 160)
    print("IS")
    print("=" * 160)
    print(tabela(linhas_is, extras=EXTRAS))
    print("\n" + "=" * 160)
    print("OOS")
    print("=" * 160)
    print(tabela(linhas_oos, extras=EXTRAS))

    print("\n" + "=" * 160)
    print("O PAR (n, win%) E O NULO -- e' isto que decide, nao o liquido")
    print("=" * 160)
    print(f"  {'ttl':>5}{'janela':>8}{'n':>8}{'win%':>8}{'IC95':>22}{'BEemp%':>10}{'veredito':>13}"
          f"{'atraso med(min)':>18}{'atraso p90(min)':>18}")
    for ttl in TTLS:
        for rot in (f"IS  ttl={ttl:>2}", f"OOS ttl={ttl:>2}"):
            r = out[(ttl, rot)]
            winpct = 100 * r["win"] / r["n"] if r["n"] else float("nan")
            ic = f"[{br(100*r['ic'][0],1)};{br(100*r['ic'][1],1)}]" if r["n"] else "--"
            be = br(100 * r["be"], 1) if r["be"] == r["be"] else "--"
            ved = r["linha"].extras.get("veredito", "--")
            amed = br(float(np.median(r["atrasos"])), 1) if len(r["atrasos"]) else "—"
            ap90 = br(float(np.percentile(r["atrasos"], 90)), 1) if len(r["atrasos"]) else "—"
            janela = "IS" if rot.startswith("IS") else "OOS"
            print(f"  {ttl:>5}{janela:>8}{r['n']:>8}{br(winpct,1):>8}{ic:>22}{be:>10}{ved:>13}"
                  f"{amed:>18}{ap90:>18}")

    print("\nFIM.")


if __name__ == "__main__":
    main()
