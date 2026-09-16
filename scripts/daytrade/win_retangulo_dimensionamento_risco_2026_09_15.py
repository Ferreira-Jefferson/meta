# -*- coding: utf-8 -*-
"""`win_retangulo` -- HA' ESPACO para dimensionar por risco (mais de 1 contrato)
com o capital REAL de R$1.100?

Frente C da rodada de economia. Regra do dono, sem excecao: "NAO teste com
capital inflado" -- se o capital real nao sustenta, a resposta e' "nao ha'
espaco" com o numero, e a frente fecha aqui.

## A conta que abre a pergunta (sem rodar nada)

WIN@: margem R$100/contrato, `MARGIN_BUFFER_FUTUROS=2,0`,
`RESERVA_CAIXA_SEGURANCA=1,25` -> pilha de ESCALAR = 100 x 2,0 x 1,25 =
R$250/contrato (`strategy.daytrade.base.contracts_from_capital_operacional`).
Com R$1.100: floor(1100/250) = **4 contratos por MARGEM**. Isso pareceria
sobrar espaco -- mas margem nao e' a restricao ativa nesta estrategia: o
`risco_maximo_brl=80` (teto de risco por OPERACAO) e' quem hoje decide qual
retangulo entra, e ele nao escala com a quantidade automaticamente porque
`quantidade` e' um parametro FIXO da classe, nunca dinamico
(`WinRetangulo.__init__`: "dimensionamento NUNCA foi medido nesta linha").

`risco_por_operacao = stop_fracao_largura x largura x R$0,20/ponto x
quantidade`. Com `quantidade=2` e o MESMO teto de R$80, o maior L aceito
cai pela METADE (de ~800 para ~400 pontos) -- e e' exatamente a faixa
328-400 que a analise de `win_retangulo_largura_paga_2026_09_15.py` mostrou
pagar PIOR por real arriscado (0,055 IS / 0,051 OOS, contra 0,2-0,4 nas
faixas largas). Dobrar `quantidade` SEM subir o teto proporcionalmente nao
e' "o mesmo robo com mais contrato": e' um robo DIFERENTE, que so' opera a
faixa ruim.

Este script mede as DUAS alternativas reais, sem inflar capital:

  (a) `quantidade=2`, teto de risco 80 INALTERADO -- mede o robo que a
      pilha de margem de fato permitiria hoje, e quanto ele perde de
      geometria por isso.
  (b) `quantidade=2`, teto de risco dobrado para 160 (preserva a MESMA
      populacao de retangulos do robo de producao) -- mede quanto de caixa
      isso exige, para responder "quanto capital seria preciso" sem
      fingir que R$1.100 alcanca.

Capital usado nas DUAS rodadas: **R$1.100, o real** -- rodar com o dobro
seria exatamente o capital inflado que a ordem do dono proibe. Se (b)
zerar/pular pregoes, e' a resposta: NAO HA ESPACO, e o numero de capital
que faltaria fica registrado (rebaixamento medido + margem) sem ser
adotado.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_dimensionamento_risco_2026_09_15.py`
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
from strategy.daytrade.base import contracts_from_capital_operacional  # noqa: E402
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
_PRODUCAO = get_daytrade_robot("win_retangulo")
CAPITAL = float(_PRODUCAO.capital_minimo_recomendado_brl)  # R$1.100 -- NAO inflar
SYMBOL = _PRODUCAO.symbol
MIN_BARRAS_POR_PREGAO = 400
MARGEM_WIN = 100.0
EXTRAS = ("BEemp%", "pior op.", "caixa min", "rebaix.op.", "piso equiv.", "sem trade")

VARIANTES = [
    ("1 contrato, teto 80 (PRODUCAO)", dict(quantidade=1, risco_maximo_brl=80.0)),
    ("2 contratos, teto 80 (o que a margem PERMITE hoje)", dict(quantidade=2, risco_maximo_brl=80.0)),
    ("2 contratos, teto 160 (preserva a geometria)", dict(quantidade=2, risco_maximo_brl=160.0)),
]


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _caixa_realizado(trades, capital):
    """(caixa minimo NESTA ordem historica, rebaixamento POR OPERACAO -- pico a
    vale da curva de patrimonio ao nivel de operacao, o mesmo conceito que fixou
    o piso de R$1.100 do robo). Os dois divergem quando a curva sobe antes de
    cair: o primeiro so' ve' o nivel absoluto, o segundo e' robusto a QUANDO no
    historico o pior trecho aconteceu -- e' o numero certo para dizer quanto
    caixa uma mudanca de risco EXIGE."""
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    if not seq:
        return capital, 0.0
    acum = np.cumsum(seq)
    eq_path = capital + acum
    maxdd_trade = float((np.maximum.accumulate(eq_path) - eq_path).max())
    return float(eq_path.min()), maxdd_trade


def _unidade(args):
    rotulo_var, kw, jn, dias = args
    strat = WinRetangulo(**kw)
    df = load_m1(strat.symbol).sort_index()
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
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = pm / (gm + pm) if (g and p) else float("nan")
    com_trade = {t.exit_ts.date() for t in trades}
    caixa_min, rebaix_op = _caixa_realizado(trades, CAPITAL)
    puladas = len(getattr(res, "sessoes_puladas_por_capital", []) or [])
    extras = {
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "pior op.": br(min(p)) if p else "—",
        "caixa min": br(caixa_min),
        "rebaix.op.": br(rebaix_op),
        "piso equiv.": br(rebaix_op + 100.0),
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}"
                     + (f" (+{puladas} pulado/capital)" if puladas else ""),
    }
    linha = linha_de_resultado(rotulo_var, res, CAPITAL, extras=extras)
    return dict(rotulo_var=rotulo_var, jn=jn, linha=linha, n=len(trades),
                caixa_min=caixa_min, rebaix_op=rebaix_op, puladas=puladas,
                zerado=getattr(res, "wiped_out_at", None) is not None)


def main():
    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    teto_margem = contracts_from_capital_operacional(CAPITAL, MARGEM_WIN)
    print("=" * 150)
    print("win_retangulo -- DIMENSIONAMENTO POR RISCO: ha' espaco com o capital REAL (R$1.100)?")
    print("=" * 150)
    print(f"  capital R$ {br(CAPITAL,0)} (REAL, nao inflado) | margem WIN@ R$100/contrato | "
          f"buffer 2,0 | reserva 1,25")
    print(f"  contratos que a PILHA DE MARGEM permitiria hoje: {teto_margem} "
          f"(contracts_from_capital_operacional) -- ISSO NAO E' a restricao ativa, ver abaixo\n",
          flush=True)

    tarefas = [(rot, kw, jn, dd) for rot, kw in VARIANTES
               for jn, dd in (("IS", IS), ("OOS", OOS))]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[(r["rotulo_var"], r["jn"])] = r
            print(f"  ok {r['rotulo_var']} / {r['jn']}: n={r['n']} caixa_min={br(r['caixa_min'])} "
                  f"zerado={r['zerado']}", flush=True)

    for jn in ("IS", "OOS"):
        linhas = [out[(rot, jn)]["linha"] for rot, _kw in VARIANTES]
        print("\n" + "=" * 150)
        print(f"{jn} -- tabela padrao")
        print("=" * 150)
        print(tabela(linhas, extras=EXTRAS))

    print("\n" + "=" * 150)
    print("LEITURA")
    print("=" * 150)
    print("  A pilha de MARGEM (contracts_from_capital_operacional) sozinha sugeriria espaco")
    print("  para ate 4 contratos com R$1.100 -- mas essa funcao NAO esta' conectada a esta")
    print("  estrategia (quantidade e' fixo, nao dinamico), e o teto de risco por operacao")
    print("  (`risco_maximo_brl`), que E' a restricao ativa, nao escala com a quantidade")
    print("  sozinho. As duas linhas de 2 contratos mostram as duas faces do mesmo problema:")
    print("  manter o teto em R$80 muda a GEOMETRIA (so' sobra a faixa de largura que paga")
    print("  pior); subir o teto para preservar a geometria dobra o 'caixa min' realizado --")
    print("  compare contra o caixa min de 1 contrato para ver quanto capital FALTARIA, sem")
    print("  adotar esse capital maior (a ordem do dono proibe testar com capital inflado).")
    print("\nFIM.")


if __name__ == "__main__":
    main()
