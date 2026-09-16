# -*- coding: utf-8 -*-
"""`win_retangulo` rodando COMO ROBO OPERA, pela REGUA PADRAO do projeto.

Pedido do dono (2026-09-15): "nao quero que suba um robo agora, quero que rode
como um robo opera, ou seja seguindo a regua de testes".

A simulacao anterior (`simulacao_hoje_dois_robos_2026_09_15.py`) estava FORA da
regua em dois pontos, e os dois importam:

  1. **Corte artificial de 17:20.** Aquele era um pedido pontual. Um robo nao
     tem corte proprio: ele para quando o PERFIL manda parar. Aqui o corte vem
     de `config_for` sem nenhum `dataclasses.replace` -- achatamento as 18:20
     BRT (`flatten_cut_time`, recuado de `FOLGA_ACHATAMENTO_MINUTOS`), atividade
     ate 18:25. Exatamente o que a producao faz.
  2. **Tabela inventada.** Toda medicao de day trade deste repo sai por
     `backtest/intraday/report.py` -- `linha_de_resultado()` + `tabela()`, as
     12 colunas base na ordem fixa, extras DEPOIS. Inventar colunas e' como
     duas rodadas deixam de ser comparaveis.

Ganha-se de brinde os avisos que a linha padrao carimba sozinha e que nenhuma
tabela caseira lembra de mostrar: conta ZERADA, pregoes PULADOS por capital,
deslize do alvo e **a premissa de FILA**. WIN@ nao tem entrada em
`fidelidade.py`, entao a linha sai marcada `fila NAO CALIBRADA` -- que e' a
ressalva mais importante desta estrategia inteira, e agora ela viaja junto com
o numero em vez de depender de eu lembrar de escreve-la.

## As janelas

  IS   -- pregoes < 2026-06-13, onde o desenho foi construido
  OOS  -- pregoes >= 2026-06-13, a janela cega
  HOJE -- 2026-09-15, **PARCIAL**: o dado vai ate 17:23 BRT, entao o
          achatamento das 18:20 ainda nao aconteceu. Uma linha de pregao
          incompleto nao e' um pregao -- vai declarada como tal.

Capital: **R$1.100**, o piso medido do robo (rebaixamento por operacao
R$989,50 + margem crua R$100), nunca um valor redondo de teste.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_regua_padrao_2026_09_15.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import daytrade_robot_class, get_daytrade_robot  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
CAPITAL = float(daytrade_robot_class("win_retangulo").capital_minimo_recomendado_brl)
#: MESMO piso de completude das outras medicoes desta linha (400 barras M1),
#: para as janelas continuarem comparaveis. Rodar com 300 admite pregoes
#: curtos que nenhuma medicao anterior viu, e ai a tabela nova nao compara
#: com a antiga -- ela SUBSTITUI, sem avisar.
MIN_BARRAS_POR_PREGAO = 400
EXTRAS = ("pts/op", "BEemp%", "veredito", "sem trade", "pior op.")


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ic95(k: int, n: int) -> tuple[float, float]:
    """Wilson. Sem ele o win% e' um numero sem dispersao -- e comparar um
    ponto com o breakeven e' o erro que este repo ja cometeu."""
    if n == 0:
        return float("nan"), float("nan")
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - r) / d, (c + r) / d


def _unidade(args):
    rotulo, dias, parcial = args
    strat = get_daytrade_robot("win_retangulo")
    df = load_m1("WIN@").sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(strat.symbol)
    # SEM `dataclasses.replace`: o corte de achatamento e' o do PERFIL, que e'
    # o que a producao usa. Mexer aqui inventa um pregao que o robo nao opera.
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
    # O breakeven empirico so' EXISTE com os DOIS lados da amostra. Sem
    # nenhum acerto, `gm = 0` e a formula devolve 1,0 POR CONSTRUCAO --
    # todo intervalo cai abaixo disso e o veredito sai 'NEGATIVO' sem ter
    # medido nada. Foi o que a 1a rodada deste script fez com o pregao de
    # hoje (3 operacoes, 0 acertos).
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    lo, hi = _ic95(len(g), len(trades))
    veredito = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if be == be and trades else "--"
    com_trade = {t.exit_ts.date() for t in trades}
    pts = ((sum(t.pnl_brl for t in trades) / len(trades)) / 0.20) if trades else float("nan")

    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "veredito": veredito,
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}",
        "pior op.": br(min(p)) if p else "—",
    }
    linha = linha_de_resultado(rotulo, res, CAPITAL, extras=extras)
    return dict(rotulo=rotulo, linha=linha, parcial=parcial,
                ic=(lo, hi), be=be, n=len(trades),
                corte=cfg.session_end_time, politica=cfg.session_end_policy,
                fila=(cfg.queue_ahead_qty, cfg.exit_queue_ahead_qty))


def main():
    df = load_m1("WIN@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]
    barras_hoje = int(contagem.get(HOJE, 0))

    print("=" * 150)
    print("win_retangulo -- RODANDO COMO ROBO OPERA, pela regua padrao do projeto")
    print("=" * 150)
    print(f"  capital R$ {br(CAPITAL,0)} (piso MEDIDO do robo) | 1 contrato | "
          f"corte de achatamento vindo do PERFIL, nao digitado")
    print(f"  IS {len(IS)} pregoes | OOS {len(OOS)} pregoes | hoje {barras_hoje} barras "
          f"(pregao PARCIAL)\n", flush=True)

    tarefas = [("IS  (< 2026-06-13)", IS, False),
               ("OOS (>= 2026-06-13)", OOS, False),
               ("HOJE 15/09 (parcial)", [HOJE], True)]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[r["rotulo"]] = r
            print(f"  ok {r['rotulo']}", flush=True)

    primeiro = out[tarefas[0][0]]
    print(f"\n  corte de achatamento em vigor: {primeiro['corte']} UTC "
          f"(politica '{primeiro['politica']}') = 18:20 BRT")
    print(f"  fila assumida: {primeiro['fila'][0]:.0f} entrada / "
          f"{primeiro['fila'][1]:.0f} saida\n")

    print(tabela([out[r]["linha"] for r, _d, _p in tarefas], extras=EXTRAS))

    print("\n" + "=" * 150)
    print("O NULO AO LADO DO ACERTO -- sem isto o win% nao quer dizer nada")
    print("=" * 150)
    print(f"  {'janela':<24}{'operacoes':>11}{'IC95 do acerto':>22}"
          f"{'breakeven empirico':>21}{'veredito':>14}")
    for rot, _d, _p in tarefas:
        r = out[rot]
        ic = (f"[{br(100*r['ic'][0],1)} ; {br(100*r['ic'][1],1)}]"
              if r["n"] else "--")
        be = (br(100 * r["be"], 1) + "%") if r["be"] == r["be"] else "--"
        print(f"  {rot:<24}{r['n']:>11}{ic:>22}{be:>21}"
              f"{out[rot]['linha'].extras.get('veredito','--'):>14}")

    print("\n" + "=" * 150)
    print("O QUE ESTA LINHA NAO DIZ")
    print("=" * 150)
    print("  * HOJE e' PREGAO PARCIAL: o dado vai ate 17:23 BRT e o achatamento das")
    print("    18:20 nao aconteceu. Um pregao incompleto nao e' um pregao.")
    print("  * `fila NAO CALIBRADA` no aviso da linha nao e' detalhe: WIN@ nao tem")
    print("    entrada em `fidelidade.py`, entao TODA ordem-limite preenche no TOQUE,")
    print("    dos dois lados. E' a premissa OTIMISTA, e ela ja inverteu o sinal de um")
    print("    robo deste repo quando foi medida de verdade (WDO F1: +R$3,82/op")
    print("    previsto contra -R$3,00 realizado).")
    print("  * Backtest nunca aferido contra extrato e' hipotese, nao previsao. O slot")
    print("    de sombra `dt-win_retangulo-win@-shadow` existe para fechar isso.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
