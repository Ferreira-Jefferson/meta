# -*- coding: utf-8 -*-
"""`win_retangulo` -- a LARGURA do retangulo prevê o resultado da operacao?

E' a pergunta que fecha a do dono ("existe teto ideal deduzivel do dado
previo?"). Um teto de largura so' faz sentido se retangulo largo pagar PIOR.
Se pagar melhor -- e o piso de 328 pontos existe justamente porque os largos
pagam melhor --, entao todo teto e' abrir mao de edge, e o valor dele sai do
CAIXA, nunca do backtest.

## Por que nao da' para ler isso numa varredura de teto

Mexer no teto muda QUAIS retangulos o robo detecta depois (recusado um, ele
continua procurando e acha outro), entao cada celula da varredura tem uma
populacao de operacoes diferente. Comparar celulas mistura "largura paga
menos" com "a outra celula pegou outros retangulos".

Aqui a medicao e' direta: **uma rodada so', sem teto nenhum**, e cada operacao
recebe a largura do retangulo que a gerou. A largura e' anotada no instante em
que a ordem e' ARMADA (nada de olhar a frente) e casada com a operacao pelo
`entry_ts` -- o preenchimento cai dentro das `ttl_barras` seguintes ao
armamento, entao o casamento e' o ultimo armamento em ate 11 barras antes.

Sai tambem o RISCO por faixa (stop = 0,50 x largura x R$0,20), que e' o que o
teto de fato controla, para separar "quanto paga" de "quanto arrisca".

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_largura_paga_2026_09_15.py`
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

from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "estr_lp", Path(__file__).with_name("copawin_retangulo_estrategias_2026_09_15.py"))
_estr = importlib.util.module_from_spec(_spec)
sys.modules["estr_lp"] = _estr
_spec.loader.exec_module(_estr)

_base = _estr._base
SYMBOL = _base.SYMBOL
CORTE_OOS = pd.Timestamp("2026-06-13").date()
CAPITAL = 1_100.0
CORTES = [328, 400, 470, 550, 650, 800, 1000, np.inf]


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


class RetanguloAnotado(WinRetangulo):
    """Igual ao robo, mas anota (instante do armamento -> largura)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.armamentos: list[tuple[pd.Timestamp, float]] = []

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if acoes and self._retangulo is not None:
            self.armamentos.append((ts, float(self._retangulo["largura"])))
        return acoes


def _unidade(args):
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for

    janela, dias = args
    strat = RetanguloAnotado(risco_maximo_brl=float("inf"))   # SEM teto
    df, _ = _base._df()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(SYMBOL)
    cfg = config_for(profile, trade_tick_value=0.20, trade_tick_size=1.0,
                     initial_capital=CAPITAL,
                     target_fills_as_maker=strat.target_fills_as_maker,
                     limit_fill_capped_by_volume=True,
                     queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)

    arm = sorted(strat.armamentos)
    ts_arm = [a[0] for a in arm]
    import bisect
    linhas = []
    for t in res.trades:
        i = bisect.bisect_right(ts_arm, t.entry_ts) - 1
        if i < 0:
            continue
        ts_a, L = arm[i]
        if (t.entry_ts - ts_a) > pd.Timedelta(minutes=11):
            continue
        linhas.append(dict(largura=L, pnl=t.pnl_brl,
                           risco=0.50 * L * 0.20,
                           ganhou=1 if t.pnl_brl > 0 else 0))
    return dict(janela=janela, linhas=linhas, n_trades=len(list(res.trades)))


def main():
    df, dias_todos = _base._df()
    JAN = {"IS": [d for d in dias_todos if d < CORTE_OOS],
           "OOS": [d for d in dias_todos if d >= CORTE_OOS]}

    print("=" * 112)
    print("win_retangulo -- a LARGURA do retangulo preve o resultado?")
    print("=" * 112)
    print("  uma rodada SEM teto por janela; cada operacao carrega a largura do")
    print("  retangulo que a gerou, anotada no instante do ARMAMENTO\n", flush=True)

    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, (jn, dd)) for jn, dd in JAN.items()]
        for fut in as_completed(futs):
            r = fut.result()
            out[r["janela"]] = r
            print(f"  ok {r['janela']}: {len(r['linhas'])} de {r['n_trades']} "
                  f"operacoes casadas com um retangulo", flush=True)

    for jn in JAN:
        d = pd.DataFrame(out[jn]["linhas"])
        if d.empty:
            print(f"\n  {jn}: nenhuma operacao casada")
            continue
        print("\n" + "=" * 112)
        print(f"{jn} -- resultado por FAIXA DE LARGURA ({len(d)} operacoes)")
        print("=" * 112)
        print(f"  {'faixa (pontos)':<18}{'n':>6}{'R$/op':>10}{'win%':>8}{'soma R$':>12}"
              f"{'risco medio':>13}{'R$ por R$ de risco':>21}")
        for a, b in zip(CORTES[:-1], CORTES[1:]):
            m = d[(d.largura >= a) & (d.largura < b)]
            if len(m) == 0:
                continue
            rot = f"{a:.0f}-{b:.0f}" if np.isfinite(b) else f"{a:.0f}+"
            risco = m.risco.mean()
            print(f"  {rot:<18}{len(m):>6}{br(m.pnl.mean()):>10}"
                  f"{(br(100*m.ganhou.mean(),1)+'%'):>8}{br(m.pnl.sum()):>12}"
                  f"{br(risco):>13}{br(m.pnl.mean()/risco, 3):>21}")
        rho = float(d.largura.rank().corr(d.pnl.rank()))
        rho_r = float(d.largura.rank().corr((d.pnl / d.risco).rank()))
        print(f"\n  correlacao de POSTO largura x resultado em R$ : {br(rho,3)}")
        print(f"  correlacao de POSTO largura x resultado/risco  : {br(rho_r,3)}")

    print("\n" + "=" * 112)
    print("LEITURA")
    print("=" * 112)
    print("  Se R$/op CRESCE com a largura, todo teto de largura corta o que paga --")
    print("  e o teto passa a ser exclusivamente um limite de RISCO, cujo valor sai")
    print("  do caixa disponivel e nunca do backtest.")
    print("  A ultima coluna normaliza pelo risco: e' 'quanto paga por real arriscado',")
    print("  que e' a comparacao justa entre faixas -- retangulo largo ganha mais em")
    print("  R$ so' porque aposta mais, e essa coluna tira isso da conta.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
