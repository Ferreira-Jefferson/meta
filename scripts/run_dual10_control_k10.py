"""Controle k=10: o ganho do liquid_dual10 e da segunda faixa, ou so de ter 10 sleeves?

A pergunta
----------
`liquid_dual10` (10 sleeves: 5 no top-20 de liquidez + 5 na faixa 21-40) mediu,
nas 48 janelas do holdout congelado (`run_holdout_frozen.HOLDOUT`), CAGR mediano
11,0%, pior janela +4,9%, MaxDD pior -17,0%, pior 12m -11,6%, exposicao media
43,9%, contra o campeao (5 sleeves, so top-20) com 5,0% / -0,7% / -34,4% /
-29,7% / 76,3%.

Suspeita: o ganho pode nao vir da SEGUNDA FAIXA, e sim so de o tamanho de cada
posicao ter caido pela metade (10 sleeves em vez de 5). O jeito de separar as
duas coisas e rodar k=10 sobre o MESMO top-20 -- `LiquidChampion(sleeve_count=10)`,
dez sleeves fatiando os mesmos 20 papeis, SEM segunda faixa. Se k=10 chegar nos
mesmos numeros do dual10, a segunda faixa e decoracao. `strategy/liquid_champion.py`
ja registra que k=10 sobre o MESMO universo, medido nas cinco janelas de
CALIBRACAO (nao no holdout), reduzia MaxDD so por segurar mais caixa parado --
este script refaz a comparacao nas 48 janelas do holdout, contra o dual10, nao
so contra o campeao puro.

CRITERIO DECLARADO ANTES DE RODAR
----------------------------------
A segunda faixa e DECORACAO se o dual10 vencer o k10 por MENOS de 1,0 p.p. de
CAGR mediano E por MENOS de 2,0 p.p. de MaxDD pior. Nesse caso o liquid_dual10
nao se sustenta como campeao. A segunda faixa FAZ TRABALHO REAL se o dual10
vencer por MAIS que isso em pelo menos um dos dois. Este e o unico veredito
deste script -- nao ha meio-termo, e o criterio nao muda depois de ver o
resultado.

Bracos, mesmas 48 janelas, mesma config
-----------------------------------------
Os quatro bracos abaixo sao medidos no MESMO processo, com o MESMO pareamento
por janela, para a comparacao nao depender de numero copiado de outro log.

  1. campeao -> LiquidChampion()               (k=5,  top-20)  -- referencia
  2. k10     -> LiquidChampion(sleeve_count=10) (k=10, top-20)  -- o controle novo
  3. dual10  -> LiquidDual10()                  (5+5,  duas faixas)
  4. ibov    -> hf.ibov_janela

Config: `BacktestConfig(initial_capital=1000.0, lot_size=1,
cash_yield_path="data/raw/selic.parquet")`, janelas de 5 anos, universo pleno
(`run_sleeve_validation.full_panels()`) para os tres robos.

PAREAMENTO: um dict de registros por janela (chave = data de inicio). So
entram na tabela as janelas em que os TRES robos (campeao, k10, dual10)
produziram equity_curve com >= 250 pontos (o mesmo piso de
`run_holdout_frozen.medir`). Nao ha listas paralelas filtradas
independentemente e nao ha comparacao por indice de posicao -- tudo e por
data de inicio, no mesmo dict.

Sobre exposicao
----------------
Se k10 e dual10 tiverem exposicao media parecida (diferenca <= 5 p.p.), a
comparacao direta entre eles e limpa: nenhum dos dois tem vantagem de caixa
parado sobre o outro, e qualquer diferenca de CAGR/MaxDD vem do desenho (10
sleeves no mesmo universo vs. 5+5 em duas faixas), nao de quanto dinheiro cada
um deixa comprado. Se as exposicoes divergirem muito, este script avisa em
destaque que a comparacao fica contaminada e que faltaria uma mistura de
igualacao (no padrao de `run_champion_k_control.py`) antes de qualquer
conclusao.

Uso: .venv/Scripts/python.exe scripts/run_dual10_control_k10.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

import run_holdout_frozen as hf
from run_sleeve_validation import full_panels

from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_dual10 import LiquidDual10

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"

# limiar do criterio declarado (em p.p., ja multiplicado por 100 na comparacao)
LIMIAR_CAGR_PP = 1.0
LIMIAR_DD_PP = 2.0
# limiar para considerar a comparacao de exposicao "limpa"
LIMIAR_EXPOSICAO_PP = 5.0


class _ExposureMixin:
    """Anota a exposicao (fracao do patrimonio em acoes) a cada pregao.

    Mesmo padrao de `_Watched` em `scripts/run_champion_k_control.py` e do
    `_ExposureMixin` de `scripts/run_dual10_holdout.py` -- aqui sem a
    decomposicao por faixa daquele script (FURO 2), porque nao faz sentido
    para o k10: os dez sleeves do k10 vivem TODOS no top-20, entao dividir
    "sleeve 0-4" de "sleeve 5-9" la seria so ruido, nao duas faixas de
    liquidez de verdade. As classes de producao (LiquidChampion, LiquidDual10)
    continuam intocadas.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.expostos: list[float] = []
        self._closes: dict[str, pd.Series] = {}

    def initialize(self, panels, ibov) -> None:
        super().initialize(panels, ibov)
        self._closes = {t: df["close"] for t, df in panels.items()}

    def _mark(self, ticker: str, date) -> float:
        s = self._closes.get(ticker)
        if s is None or date not in s.index:
            return 0.0
        v = s.loc[date]
        return 0.0 if pd.isna(v) else float(v)

    def on_bar(self, date, open_positions, cash_available):
        mkt = sum(self._mark(t, date) * p.quantity for t, p in open_positions.items())
        eq = cash_available + mkt
        if eq > 0:
            self.expostos.append(mkt / eq)
        return super().on_bar(date, open_positions, cash_available)


class _WatchedChampion(_ExposureMixin, LiquidChampion):
    """Usada tanto para o campeao (k=5, default) quanto para o controle k10
    (`sleeve_count=10` passado na fabrica) -- e a MESMA classe de producao,
    so muda o parametro de construcao."""

    name = "liquid_champion_watched"
    candidate = False


class _WatchedDual10(_ExposureMixin, LiquidDual10):
    name = "liquid_dual10_watched"
    candidate = False


def medir(factory, u, start: pd.Timestamp) -> dict | None:
    """Mesmo piso de `run_holdout_frozen.medir` (>=250 pontos), mais exposicao."""
    end = start + pd.DateOffset(years=hf.ANOS)
    cfg = BacktestConfig(initial_capital=INITIAL, lot_size=1, cash_yield_path=SELIC)
    bot = factory()
    r = run_bt(u, bot, cfg, start=str(start.date()), end=str(end.date()))
    eq = r.equity_curve
    if len(eq) < 250:
        return None
    return {
        "cagr": float(r.metrics["cagr"]),
        "dd": float(r.metrics["max_drawdown"]),
        "w12": float((eq / eq.shift(252) - 1).min()),
        "trades": len(r.trades),
        "exp": float(np.mean(bot.expostos)) if bot.expostos else 0.0,
    }


def resumo(nome: str, rows: list[dict], ib_cagr: list[float]) -> dict:
    g = np.array([m["cagr"] for m in rows])
    ibg = np.array(ib_cagr)
    return {
        "nome": nome, "n": len(rows),
        "p05": float(np.percentile(g, 5)), "med": float(np.median(g)),
        "p95": float(np.percentile(g, 95)), "pior": float(g.min()),
        "dd": min(m["dd"] for m in rows), "w12": min(m["w12"] for m in rows),
        "neg": int((g < 0).sum()),
        "bate_ibov": int((g > ibg).sum()),
        "trades": int(np.median([m["trades"] for m in rows])),
        "exp": float(np.mean([m["exp"] for m in rows])),
    }


def linha(r: dict) -> str:
    return (f"{r['nome']:24s} {r['n']:4d} {r['p05']*100:7.1f}% {r['med']*100:7.1f}% "
            f"{r['p95']*100:7.1f}% {r['pior']*100:7.1f}% {r['dd']*100:7.1f}% "
            f"{r['w12']*100:7.1f}% {r['neg']:4d} {r['bate_ibov']:4d} "
            f"{r['trades']:5d} {r['exp']*100:7.1f}%")


def sim_nao(b: bool) -> str:
    return "SIM" if b else "NAO"


def main() -> None:
    print(__doc__.split("Uso:")[0])

    u = full_panels()
    total = len(hf.HOLDOUT)

    campeao_rows: dict[pd.Timestamp, dict] = {}
    k10_rows: dict[pd.Timestamp, dict] = {}
    dual10_rows: dict[pd.Timestamp, dict] = {}
    ibov_rows: dict[pd.Timestamp, dict] = {}
    descartadas: list[pd.Timestamp] = []

    for i, start in enumerate(hf.HOLDOUT, 1):
        c = medir(lambda: _WatchedChampion(), u, start)
        k = medir(lambda: _WatchedChampion(sleeve_count=10), u, start)
        d = medir(lambda: _WatchedDual10(), u, start)
        if c is None or k is None or d is None:
            descartadas.append(start)
            print(f"janela {i}/{total} inicio {start.date()} descartada "
                  f"(campeao={'ok' if c else 'curto'}, k10={'ok' if k else 'curto'}, "
                  f"dual10={'ok' if d else 'curto'})", flush=True)
            continue
        campeao_rows[start] = c
        k10_rows[start] = k
        dual10_rows[start] = d
        ibov_rows[start] = hf.ibov_janela(start)
        print(f"janela {i}/{total} inicio {start.date()} ok", flush=True)

    comuns = sorted(campeao_rows)  # so janelas presentes nos tres bracos
    print(f"\n{len(descartadas)} janela(s) descartada(s) de {total}: "
          f"{[str(s.date()) for s in descartadas] if descartadas else 'nenhuma'}")
    print(f"{len(comuns)} janelas pareadas para a comparacao\n")

    campeao = [campeao_rows[s] for s in comuns]
    k10 = [k10_rows[s] for s in comuns]
    dual10 = [dual10_rows[s] for s in comuns]
    ib_cagr = [ibov_rows[s]["cagr"] for s in comuns]

    r_campeao = resumo("campeao (liquid_champion)", campeao, ib_cagr)
    r_k10 = resumo("k10 (LiquidChampion k=10)", k10, ib_cagr)
    r_dual10 = resumo("dual10 (liquid_dual10)", dual10, ib_cagr)
    # O IBOV entra na tabela com exp=100%: o indice esta sempre comprado, e e
    # justamente essa a coluna que separa diversificacao de caixa parado.
    r_ibov = resumo("IBOV", [{**ibov_rows[s], "exp": 1.0} for s in comuns], ib_cagr)

    hdr = (f"{'robo':24s} {'n':>4s} {'p05':>8s} {'mediana':>8s} {'p95':>8s} "
           f"{'pior':>8s} {'DDpior':>8s} {'12m':>8s} {'neg':>4s} {'>ibov':>5s} "
           f"{'trd':>5s} {'exposto':>8s}")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    print(linha(r_ibov))
    print(linha(r_campeao))
    print(linha(r_k10))
    print(linha(r_dual10))
    print("=" * len(hdr))

    # ---------------------------------------------------- comparacao direta
    delta_cagr_pp = (r_dual10["med"] - r_k10["med"]) * 100
    delta_dd_pp = (r_dual10["dd"] - r_k10["dd"]) * 100
    delta_exp_pp = (r_dual10["exp"] - r_k10["exp"]) * 100

    ganha_cagr = sum(1 for s in comuns if dual10_rows[s]["cagr"] > k10_rows[s]["cagr"])
    ganha_dd = sum(1 for s in comuns if dual10_rows[s]["dd"] > k10_rows[s]["dd"])

    print("\nCOMPARACAO DIRETA: dual10 vs k10 (o ponto deste script)")
    print(f"  delta CAGR mediano (dual10 - k10)........ {delta_cagr_pp:+6.1f} p.p.")
    print(f"  delta MaxDD pior   (dual10 - k10)........ {delta_dd_pp:+6.1f} p.p. "
          f"(positivo = dual10 tem MaxDD melhor, menos negativo)")
    print(f"  delta exposicao media (dual10 - k10)..... {delta_exp_pp:+6.1f} p.p.")
    print(f"  dual10 teve CAGR maior que k10 em........ {ganha_cagr}/{len(comuns)} janelas (pareado)")
    print(f"  dual10 teve MaxDD melhor que k10 em...... {ganha_dd}/{len(comuns)} janelas (pareado)")

    # -------------------------------------------------- aviso de exposicao
    if abs(delta_exp_pp) <= LIMIAR_EXPOSICAO_PP:
        print(f"\nexposicao media de k10 ({r_k10['exp']*100:.1f}%) e dual10 "
              f"({r_dual10['exp']*100:.1f}%) sao parecidas (diferenca "
              f"{abs(delta_exp_pp):.1f} p.p. <= {LIMIAR_EXPOSICAO_PP:.0f} p.p.) -- "
              f"a comparacao direta acima e LIMPA: nenhum dos dois robos tem "
              f"vantagem de caixa parado sobre o outro, entao qualquer diferenca "
              f"de CAGR/MaxDD vem do desenho (universo unico vs. duas faixas), "
              f"nao de quanto dinheiro cada um deixa comprado.")
    else:
        print(f"\n*** ATENCAO: exposicao media de k10 ({r_k10['exp']*100:.1f}%) e "
              f"dual10 ({r_dual10['exp']*100:.1f}%) DIVERGEM MUITO (diferenca "
              f"{abs(delta_exp_pp):.1f} p.p. > {LIMIAR_EXPOSICAO_PP:.0f} p.p.) -- "
              f"a comparacao direta acima esta CONTAMINADA por caixa parado: o "
              f"robo com mais exposicao pode estar ganhando (ou perdendo) so por "
              f"ter mais dinheiro comprado, nao por causa da segunda faixa. "
              f"Faltaria uma mistura de igualacao (no padrao de "
              f"`run_champion_k_control.py`, robo x Selic ate igualar a "
              f"exposicao media) antes de aceitar qualquer conclusao daqui. ***")

    # -------------------------------------------------------------- veredito
    trabalho_real = (delta_cagr_pp >= LIMIAR_CAGR_PP) or (delta_dd_pp >= LIMIAR_DD_PP)
    decoracao = not trabalho_real

    print(f"\nCRITERIO DECLARADO: decoracao se dual10 vencer k10 por MENOS de "
          f"{LIMIAR_CAGR_PP:.1f} p.p. de CAGR mediano E por MENOS de "
          f"{LIMIAR_DD_PP:.1f} p.p. de MaxDD pior. Trabalho real se vencer por "
          f"MAIS que isso em pelo menos um dos dois.")
    print(f"  delta CAGR mediano = {delta_cagr_pp:+.1f} p.p. "
          f"({'>=' if delta_cagr_pp >= LIMIAR_CAGR_PP else '<'} {LIMIAR_CAGR_PP:.1f})")
    print(f"  delta MaxDD pior   = {delta_dd_pp:+.1f} p.p. "
          f"({'>=' if delta_dd_pp >= LIMIAR_DD_PP else '<'} {LIMIAR_DD_PP:.1f})")
    if decoracao:
        print(f"\nVEREDITO: a segunda faixa (rank_offset 20, faixa 21-40) e "
              f"DECORACAO -- dual10 nao vence k10 por margem suficiente em "
              f"nenhuma das duas colunas. liquid_dual10 nao se sustenta como "
              f"campeao: o ganho aparente contra o campeao de 5 sleeves vem de "
              f"ter 10 sleeves (posicao menor, mais diluicao), nao da segunda "
              f"faixa de liquidez.")
    else:
        print(f"\nVEREDITO: a segunda faixa (rank_offset 20, faixa 21-40) FAZ "
              f"TRABALHO REAL -- dual10 vence k10 por mais que a margem "
              f"declarada em pelo menos uma coluna, entao a melhora do dual10 "
              f"contra o campeao NAO se explica so por ter 10 sleeves; parte "
              f"dela vem de fato da faixa 21-40.")
    print("ressalva: o numero da faixa 21-40 dentro do dual10 continua inflado "
          "por empresas mortas ausentes do pool (vies de sobrevivencia "
          "assimetrico, ver docstring de strategy/liquid_dual10.py) -- isso vale "
          "para o dual10 nas duas comparacoes (contra o campeao e contra o k10).")


if __name__ == "__main__":
    main()
