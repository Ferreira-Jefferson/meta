"""BANCADA PADRAO para os finalistas evoluidos (2026-09-18) -- o mesmo teste
por que passou todo robo deste repo.

## Por que esta bancada existe, separada do treino

Ordem do dono, 2026-09-18: *"depois confirme com testes normais como fizemos
com todos os robos ate' aqui, para vermos se nao e' algo que funcionou apenas
neste cenario de teste da IA, mas nao viraria um robo de fato"*.

E' a pergunta certa, e ela nao e' respondida pelo numero do treino. O
ambiente de treino tem quatro particularidades que sao boas PARA BUSCAR e
ruins para CONCLUIR:

  * **roda pregao a pregao**, encadeando o caixa na mao, para poder matar o
    individuo no instante em que o caixa furа a margem. A bancada roda o
    motor UMA VEZ sobre a janela inteira, que e' como `wdo_orb`, `copa_win` e
    `win_retangulo` foram medidos -- e so' assim existem curva de patrimonio,
    MaxDD de verdade e as 12 colunas da tabela padrao;
  * **janelas de 18 pregoes**, sorteadas. A bancada usa IS e OOS inteiros;
  * **fitness**, que ja' embute desvio entre blocos, drawdown relativo e
    folga de caixa. A bancada mostra o liquido cru e deixa a leitura para
    quem le;
  * **M1**, que e' surrogado. A bancada confirma em TICK.

Se um genoma so' brilha sob as quatro, ele nao e' um robo -- e' um artefato
do ambiente que o produziu. Esta bancada e' onde isso aparece.

## O que a tabela mostra alem das 12 colunas fixas

Nos `extras`, e nunca no lugar da base (`backtest/intraday/report.py`):

  * **`BE emp`** -- o breakeven EMPIRICO, `perda_media/(ganho+perda)`. O nulo
    certo quando o payoff realizado foge do nominal, e num robo com corte de
    relogio ele sempre foge. Conferencia obrigatoria: `R$/dia > 0` e
    `win% > BE emp` sao a MESMA afirmacao -- se discordarem na tabela, o nulo
    esta no lugar errado (itens 6.22/6.23 de LICOES_DE_PRODUCAO);
  * **`IC95 win`** -- o intervalo do win%. Sem ele, "win 56%" contra
    "breakeven 48%" parece veredito e pode ser ruido de 30 operacoes;
  * **`s/trade`** -- pregoes sem nenhuma operacao. Janela em que o robo parou
    esta' CENSURADA: mede a restricao, nao a estrategia;
  * **`caixa min`** -- o menor caixa da caminhada. Abaixo de R$150 a
    corretora recusa, e o resto da linha e' ficcao;
  * **`pts med`** -- mediana do |resultado| em PONTOS. A checagem da ordem
    dos 3 pontos: um robo cuja operacao tipica anda menos que isso esta'
    vivendo de movimento do tamanho do proprio escorregao, mesmo que o alvo
    PEDIDO tenha sido 8 ticks.

Uso:
    python -u scripts/daytrade/evo_wdo_bancada_2026_09_18.py
    python -u scripts/daytrade/evo_wdo_bancada_2026_09_18.py --oos
    python -u scripts/daytrade/evo_wdo_bancada_2026_09_18.py --tick --oos
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
for _p in (RAIZ / "src", Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from strategy.daytrade.evo.genoma import Genoma  # noqa: E402
from strategy.daytrade.lab.wdo_orb import WdoOrb  # noqa: E402

from evo.avaliacao import monta_config, monta_robo  # noqa: E402
from evo.dados import (  # noqa: E402
    BARRAS_POR_MINUTO, CAPITAL_PARTIDA_BRL, MARGEM_WDO_BRL, bars_m1,
    bars_tick, pregoes,
)

SAIDA = RAIZ / "scratch" / "evo_wdo_2026_09_18"
FINALISTAS = SAIDA / "finalistas.json"

#: Colunas extras desta bancada, na ordem de exibicao. Depois da base.
EXTRAS = ("caixa min", "s/trade", "BE emp", "IC95 win", "pts med", "DD rel")


def _barras(janela: str, feed: str) -> pd.DataFrame:
    """A janela INTEIRA numa tacada -- e' o que da curva de patrimonio e
    MaxDD de verdade, ao contrario do treino, que roda pregao a pregao."""
    carregar = bars_m1 if feed == "m1" else bars_tick
    pedacos = [carregar(d) for d in pregoes(janela)]
    pedacos = [p for p in pedacos if not p.empty]
    return pd.concat(pedacos).sort_index(kind="mergesort")


def _ic95(acertos: int, n: int) -> str:
    """Intervalo de 95% do win%, aproximacao normal. Sem ele, um win% alto
    sobre 30 operacoes parece veredito e e' ruido."""
    if n == 0:
        return "--"
    p = acertos / n
    meio = 1.96 * math.sqrt(max(p * (1 - p), 1e-12) / n)
    return f"{100 * max(0, p - meio):.1f}-{100 * min(1, p + meio):.1f}"


def _extras(res, capital: float) -> dict[str, str]:
    trades = list(res.trades)
    n = len(trades)
    if not n:
        return {k: "--" for k in EXTRAS}
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [-t.pnl_brl for t in trades if t.pnl_brl < 0]
    gm = sum(ganhos) / len(ganhos) if ganhos else 0.0
    pm = sum(perdas) / len(perdas) if perdas else 0.0
    be = 100 * pm / (gm + pm) if (gm + pm) > 0 else 0.0

    # Caminhada de caixa na ordem cronologica REAL das operacoes, e o
    # drawdown RELATIVO ao pico -- perder R$50 com R$100 e com R$1.000 sao
    # riscos de quebrar a banca diferentes (ordem do dono).
    caixa = pico = capital
    minimo = capital
    dd_rel = 0.0
    for t in sorted(trades, key=lambda x: x.exit_ts):
        caixa += t.pnl_brl
        minimo = min(minimo, caixa)
        if caixa > pico:
            pico = caixa
        elif pico > 0:
            dd_rel = max(dd_rel, (pico - caixa) / pico)

    pontos = sorted(abs((t.exit_price - t.entry_price) if t.side == "long"
                        else (t.entry_price - t.exit_price)) for t in trades)
    mediana_pts = pontos[len(pontos) // 2]

    dias_com_op = {pd.Timestamp(t.entry_ts).date() for t in trades}
    equity = res.equity_curve
    total_dias = (len(set(pd.DatetimeIndex(equity.index).date))
                  if equity is not None and not equity.empty else 0)
    sem_op = max(0, total_dias - len(dias_com_op))

    return {
        "caixa min": f"{minimo:.2f}".replace(".", ","),
        "s/trade": f"{sem_op}/{total_dias}",
        "BE emp": f"{be:.2f}".replace(".", ","),
        "IC95 win": _ic95(len(ganhos), n),
        "pts med": f"{mediana_pts:.1f}".replace(".", ","),
        "DD rel": f"{100 * dd_rel:.1f}%".replace(".", ","),
    }


def _tarefa(carga):
    """Uma (variante, janela, feed) -- roda num processo proprio."""
    rotulo, cru, janela, feed = carga
    with redirect_stdout(StringIO()):
        bars = _barras(janela, feed)
        if bars.empty:
            return None
        if cru is None:
            # A linha de comparacao: `wdo_orb` de PRODUCAO. O unico parametro
            # traduzido e' o prazo da entrada, que foi calibrado em barras de
            # TICK (5000 barras / 349 por minuto ~= 15 min) e em M1 teria de
            # ser 15 barras. Nao traduzir compararia dois robos, nao duas
            # bases (CLAUDE.md).
            robo = WdoOrb(entrada_ttl_bars=5000 if feed == "tick" else 15)
        else:
            robo = monta_robo(Genoma(cru=tuple(cru)), feed)
        cfg = monta_config(feed, CAPITAL_PARTIDA_BRL)
        res = run_intraday_backtest(bars, robo, cfg)
        linha = linha_de_resultado(
            f"{rotulo} [{janela}/{feed}]", res, CAPITAL_PARTIDA_BRL,
            extras=_extras(res, CAPITAL_PARTIDA_BRL))
    return (janela, feed, linha)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--oos", action="store_true",
                   help="inclui a janela cega. Decisao do dono.")
    p.add_argument("--tick", action="store_true",
                   help="confirma em TICK (lento: ~75s por pregao)")
    p.add_argument("--genomas", type=str, default=str(FINALISTAS))
    p.add_argument("--workers", type=int,
                   default=min(12, os.cpu_count() or 4))
    a = p.parse_args()

    dados = json.loads(Path(a.genomas).read_text(encoding="utf-8"))
    # Baseline primeiro, sempre: a comparacao tem de ser imediata.
    variantes = [("wdo_orb (baseline)", None)]
    variantes += [(d["especie"], d["genoma"]) for d in dados]

    janelas = ["IS"] + (["OOS"] if a.oos else [])
    feeds = ["m1"] + (["tick"] if a.tick else [])

    cargas = [(rot, cru, j, f)
              for rot, cru in variantes for j in janelas for f in feeds]

    print("=" * 100)
    print("BANCADA PADRAO -- finalistas evoluidos contra o wdo_orb de producao")
    print("=" * 100)
    print(f"capital R${CAPITAL_PARTIDA_BRL:.2f} continuo, margem "
          f"R${MARGEM_WDO_BRL:.2f}  |  {len(cargas)} rodadas, "
          f"{a.workers} processos")
    print("A janela roda de UMA VEZ (nao pregao a pregao como no treino) --")
    print("e' isso que da curva de patrimonio, MaxDD e as 12 colunas fixas.\n")

    resultados: dict[tuple[str, str], list] = {}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futuros = {pool.submit(_tarefa, c): c for c in cargas}
        feitos = 0
        for fut in as_completed(futuros):
            feitos += 1
            saida = fut.result()
            if saida is None:
                continue
            janela, feed, linha = saida
            resultados.setdefault((janela, feed), []).append(linha)
            print(f"[{feitos:>3}/{len(cargas)}] {linha.variante}: "
                  f"{linha.liquido_brl:+.2f} em {linha.trades} operacoes",
                  flush=True)

    for janela in janelas:
        for feed in feeds:
            linhas = resultados.get((janela, feed))
            if not linhas:
                continue
            # Baseline primeiro, fora da ordenacao; o resto por liquido.
            base = [x for x in linhas if "baseline" in x.variante]
            resto = sorted((x for x in linhas if "baseline" not in x.variante),
                           key=lambda x: x.liquido_brl, reverse=True)
            print("\n" + "=" * 100)
            print(f"{janela} / {feed}")
            print("=" * 100)
            print(tabela(base + resto, extras=EXTRAS, largura_extra=11))

    print("\n" + "-" * 100)
    print("COMO LER: `R$/dia > 0` e `win% > BE emp` sao a MESMA afirmacao --")
    print("se discordarem, o nulo esta no lugar errado. Confira `s/trade`")
    print("antes do liquido (janela em que o robo parou esta censurada) e")
    print("`caixa min` antes de tudo (abaixo de R$150 a corretora recusa).")


if __name__ == "__main__":
    main()
