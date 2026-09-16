# -*- coding: utf-8 -*-
"""`win_retangulo` transplantado para o WDO@ -- a UNICA amostra genuinamente
FORA do lugar onde o robo foi desenhado e calibrado.

## A pergunta que esta rodada responde, e so ela

O OOS do WIN@ ja foi gasto -- pelas 18 familias da Copa e por dois parametros
deste proprio robo (`tolerancia_borda`, `risco_maximo_brl`). Rodar mais
janela do MESMO WIN@ estreita o IC, mas nao produz evidencia de FORA. O WDO@
nunca foi tocado por este detector. Se o retangulo tiver edge estrutural
(a forma "vai ao x, volta, retorna ao x" existe em qualquer instrumento que
lateraliza), ele deve aparecer aqui tambem -- com OUTRO custo de execucao
(WDO@ TEM fila calibrada em `fidelidade.py`, WIN@ nao) e OUTRA economia
(R$10,00/ponto contra R$0,20/ponto, tick 0,5 contra tick 5,0).

Isto NAO decide se o detector "funciona em geral". Decide uma coisa mais
estreita e mais util: se a margem de 0,2pp do OOS do WIN@ e' sorte de UM
instrumento ou sinal que se repete em outro. Ausencia de edge aqui tambem
e' informacao de primeira ordem -- e' relatada como tal, nao escondida.

## Como a largura minima foi traduzida (328 pontos do WIN@ nao significa nada
## em pontos de WDO@ -- ponto de WIN vale R$0,20, ponto de WDO vale R$10,00)

Tres metodos foram medidos (script de exploracao, nao salvo -- os numeros
estao aqui):

  1. **Percentil da PROPRIA distribuicao do instrumento** (o metodo que
     originou o 328: "o terco superior da largura dos retangulos W=20
     medido NO IS"). Rodando o detector puro (SEM piso de largura, SEM teto
     de risco) sobre os 129 pregoes IS do WIN@ com os criterios de forma
     atuais (tolerancia=0,20), 328 cai no percentil **59,8** da distribuicao
     de 1.028 retangulos naturalmente detectados (n>=TOQUES_MINIMOS etc.).
     Aplicando o MESMO percentil a distribuicao de 891 retangulos do WDO@
     (mesma janela IS, mesmos criterios de forma): **p60 = 6,18 pontos**.
  2. **Multiplo do pedagio de ida-e-volta.** Pedagio = fee_round_trip_brl/
     valor_do_ponto + slippage_ticks x tick_size. WIN@: 0,50/0,20 + 1x5,0 =
     7,5 pontos (bate com a docstring do robo). WDO@: 0,50/10,0 + 1x0,5 =
     0,55 pontos. 328/7,5 = 43,73x; aplicado ao WDO@: 43,73 x 0,55 = **24,05
     pontos** -- que cai no percentil **99,9** da distribuicao do WDO@ (so' 1
     de 891 retangulos e' esse largo; o maximo observado e' 24,83). Um piso
     nesse nivel deixa a estrategia praticamente INOPERAVEL no WDO@ -- nao e'
     traducao de parametro, e' proibicao por outro nome.
  3. **Razao de amplitude diaria** (2.968 pontos WIN@ / 49,3 pontos WDO@,
     numeros do proprio `profiles.py`): 328 / 60,2 = 5,45 pontos -- proximo
     do metodo 1.

Os metodos 1 e 3 concordam (5,4-6,2 pontos); o metodo 2 e' um outlier que
revela um fato estrutural, nao um erro de conta: **o retangulo natural do
WDO@, mesmo no percentil mais generoso, mal passa do pedagio** -- ao
contrario do WIN@, onde o retangulo mediano (281,7 pontos) ja vale 37x o
pedagio. Isso e' reportado como achado, nao escondido.

**Adotado: metodo 1, largura_minima_pontos=6,18** -- e' o unico que replica
a REGRA que gerou o 328 (percentil da propria distribuicao), nao um numero
emprestado.

## O que NAO foi traduzido, e por que

`risco_maximo_brl=80,0` (WIN@) pressupoe valor do ponto de R$0,20. Transplantar
o NUMEM (nao a formula) exigiria um piso de largura de 80/(0,50 x 10,0 x 1) =
16 pontos -- ACIMA do piso de largura traduzido (6,18) e do p90 da propria
distribuicao (9,42), ou seja, um teto de risco copiado ao pe da letra
tornaria quase toda deteccao INOPERAVEL antes mesmo de rodar. Por isso esta
rodada roda com `risco_maximo_brl=inf` (desligado) e reporta a distribuicao
de risco por operacao a parte -- exatamente o que a docstring do proprio robo
recomenda fazer quando o eixo "nao tem estrutura".

## Fila: WDO@ TEM calibracao real (WIN@ nao)

`config_for` resolve sozinho `queue_ahead_qty`/`exit_queue_ahead_qty` a partir
de `backtest.intraday.fidelidade` quando nao passados -- para o WDO@ isso
preenche os numeros medidos por Kaplan-Meier contra extrato real (nao os
"NAO CALIBRADA" do WIN@). Esta e' uma medicao MAIS rigorosa que a tabela
oficial do proprio robo, no sentido inverso do que se poderia esperar: WDO@
tem fila real cobrada, WIN@ nao.

## Capital

`CLAUDE.md`: piso de PARTIDA do WDO@ e' R$375 (margem R$150 x buffer 2,0 x
reserva 1,25). Rodado a partir dai; se o rebaixamento por operacao desta
configuracao pedir mais, o script recalcula e reporta o novo piso (mesma
regra que fixou R$1.100 no WIN@: rebaixamento por operacao + margem crua).

## As duas janelas, e o aviso de fila/deslize carimbado pela tabela padrao.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_transferencia_wdo_2026_09_15.py`
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
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
#: HOJE fica de FORA -- mesma regra da regua oficial do WIN@: o dado de hoje
#: pode passar do piso de completude (504 barras de WDO@ medidas ao rodar
#: este script) sem ter passado pelo achatamento oficial, e contaminaria a
#: janela OOS com um pregao que so' PARECE fechado.
HOJE = pd.Timestamp("2026-09-15").date()
MIN_BARRAS_POR_PREGAO = 400
CAPITAL_PARTIDA = 375.0  # piso de PARTIDA oficial do WDO@ (CLAUDE.md)
LARGURA_MINIMA_WDO = 6.18  # metodo 1 -- ver docstring
EXTRAS = ("pts/op", "BEemp%", "veredito", "sem trade", "pior op.", "risco max op.")


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
    rotulo, dias, capital = args
    strat = WinRetangulo(
        symbol="WDO@",
        janela_barras=20,
        largura_minima_pontos=LARGURA_MINIMA_WDO,
        alvo_fracao_largura=0.80,
        stop_fracao_largura=0.50,
        ttl_barras=10,
        quantidade=1,
        tolerancia_borda=0.20,
        risco_maximo_brl=float("inf"),
    )
    df = load_m1("WDO@").sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(strat.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.5 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.5,
        initial_capital=capital,
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
    pts = ((sum(t.pnl_brl for t in trades) / len(trades)) / (profile.point_value_brl or 1.0)) \
        if trades else float("nan")

    # Rebaixamento POR OPERACAO (nao da serie diaria) -- caixa acumulado
    # operacao a operacao, pior queda pico-a-vale. E' a mesma conta que
    # fixou o piso de R$1.100 no WIN@.
    caixa = capital
    pico = capital
    rebaix_max = 0.0
    caixa_min = capital
    riscos = []
    for t in trades:
        caixa += t.pnl_brl
        pico = max(pico, caixa)
        rebaix_max = max(rebaix_max, pico - caixa)
        caixa_min = min(caixa_min, caixa)
        riscos.append(abs(min(t.pnl_brl, 0.0)) if t.pnl_brl < 0 else 0.0)
    risco_max_op = max(riscos) if riscos else float("nan")

    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "veredito": veredito,
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}",
        "pior op.": br(min(p)) if p else "—",
        "risco max op.": br(risco_max_op) if risco_max_op == risco_max_op else "—",
    }
    linha = linha_de_resultado(rotulo, res, capital, extras=extras)
    return dict(
        rotulo=rotulo, linha=linha, ic=(lo, hi), be=be, n=len(trades),
        trades=trades, rebaix_max=rebaix_max, caixa_min=caixa_min,
        fila=(cfg.queue_ahead_qty, cfg.exit_queue_ahead_qty),
        fidelidade_calibrada=cfg.costs.fidelidade_calibrada,
    )


def main():
    df = load_m1("WDO@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    print("=" * 150)
    print("win_retangulo TRANSPLANTADO para WDO@ -- amostra de FORA do lugar onde foi calibrado")
    print("=" * 150)
    print(f"  largura_minima_pontos={LARGURA_MINIMA_WDO} (metodo: percentil da propria "
          f"distribuicao, replicando a regra que gerou 328 no WIN@)")
    print(f"  risco_maximo_brl=inf (DESLIGADO -- o numero do WIN@ nao transfere, ver docstring)")
    print(f"  capital de partida R$ {br(CAPITAL_PARTIDA,0)} (piso oficial CLAUDE.md, WDO@)")
    print(f"  IS {len(IS)} pregoes | OOS {len(OOS)} pregoes\n", flush=True)

    tarefas = [("IS  (< 2026-06-13)", IS, CAPITAL_PARTIDA),
               ("OOS (>= 2026-06-13)", OOS, CAPITAL_PARTIDA)]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t[0] for t in tarefas}
        for fut in as_completed(futs):
            r = fut.result()
            out[r["rotulo"]] = r
            print(f"  ok {r['rotulo']}: n={r['n']} rebaixamento-por-op R$ {br(r['rebaix_max'])} "
                  f"caixa-min R$ {br(r['caixa_min'])}", flush=True)

    print(f"\n  fila assumida (IS): entrada {out[tarefas[0][0]]['fila'][0]:.0f} / "
          f"saida {out[tarefas[0][0]]['fila'][1]:.0f} "
          f"(fidelidade_calibrada={out[tarefas[0][0]]['fidelidade_calibrada']})\n")

    print(tabela([out[r]["linha"] for r, _d, _c in tarefas], extras=EXTRAS))

    # Recalcula o piso se o rebaixamento por operacao pedir mais que a
    # partida oficial cobre -- mesma regra do WIN@ (rebaixamento + margem crua).
    piso_necessario = max(out[r]["rebaix_max"] for r, _d, _c in tarefas) + 150.0
    print(f"\n  piso NECESSARIO (rebaixamento-por-operacao max + margem crua R$150) = "
          f"R$ {br(piso_necessario, 0)}")
    if piso_necessario > CAPITAL_PARTIDA:
        print(f"  ATENCAO: capital de partida (R$ {br(CAPITAL_PARTIDA,0)}) e' MENOR que o "
              f"piso necessario -- as janelas acima podem estar CENSURADAS. Rerodando com o "
              f"piso corrigido...\n", flush=True)
        tarefas2 = [("IS  (piso corrigido)", IS, piso_necessario),
                    ("OOS (piso corrigido)", OOS, piso_necessario)]
        out2 = {}
        with ProcessPoolExecutor() as pool:
            futs = {pool.submit(_unidade, t): t[0] for t in tarefas2}
            for fut in as_completed(futs):
                r = fut.result()
                out2[r["rotulo"]] = r
                print(f"  ok {r['rotulo']}: n={r['n']} caixa-min R$ {br(r['caixa_min'])}", flush=True)
        print(tabela([out2[r]["linha"] for r, _d, _c in tarefas2], extras=EXTRAS))
        out.update(out2)
        tarefas = tarefas + tarefas2

    print("\n" + "=" * 150)
    print("O NULO AO LADO DO ACERTO")
    print("=" * 150)
    print(f"  {'janela':<24}{'operacoes':>11}{'IC95 do acerto':>22}"
          f"{'breakeven empirico':>21}{'veredito':>14}")
    for rot, _d, _c in tarefas:
        r = out[rot]
        ic = (f"[{br(100*r['ic'][0],1)} ; {br(100*r['ic'][1],1)}]" if r["n"] else "--")
        be = (br(100 * r["be"], 1) + "%") if r["be"] == r["be"] else "--"
        print(f"  {rot:<24}{r['n']:>11}{ic:>22}{be:>21}"
              f"{out[rot]['linha'].extras.get('veredito','--'):>14}")

    print("\n" + "=" * 150)
    print("O QUE ESTA LINHA NAO DIZ / LIMITES")
    print("=" * 150)
    print("  * Traducao de parametro, nao replicacao: `largura_minima_pontos` foi RE-CALIBRADA")
    print("    para o WDO@ pelo metodo do percentil (ver docstring). Nao e' o robo de producao")
    print("    do WIN@ rodando 'igual' em outro simbolo -- e' o MESMO detector com o piso de")
    print("    largura na escala certa. `risco_maximo_brl` ficou desligado (nao transferia).")
    print("  * `tolerancia_borda`, `alvo_fracao_largura`, `stop_fracao_largura`, `ttl_barras`")
    print("    NAO foram recalibrados para o WDO@ -- vieram direto do WIN@. Se o detector tiver")
    print("    edge aqui, um proximo passo legitimo e' recalibrar esses tres para o WDO@; esta")
    print("    rodada so' responde 'o edge aparece com os parametros do WIN@ transplantados'.")
    print("  * N pequeno e' esperado: retangulos exigem largura >=6,18 pontos, e o WDO@ produz")
    print("    poucos passando de um certo tamanho por pregao.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
