"""H2 vira robo unico? `liquid_dual10` (10 sleeves, 2 faixas) contra o campeao no holdout.

A pergunta
----------
`liquid_champion` (top-20 de liquidez, 5 sleeves) e uma peca equivalente na
faixa 21-40 (mesmo sinal, `rank_offset=20`, apagada depois de servir a esta
medicao) foram medidos lado a lado nas 48 janelas de `run_holdout_frozen.py`
tiveram correlacao diaria mediana 0,46 e a mistura estatica 50/50 teve MaxDD
melhor que a media dos dois isolados em 48/48 janelas. `strategy/liquid_dual10.py`
testa se isso pode virar UM robo -- 10 sleeves numa conta so, 5 no top-20 e 5 na
faixa 21-40, zero parametro novo de sinal.

Protocolo, declarado ANTES de rodar
------------------------------------
As MESMAS 48 janelas de 5 anos do holdout congelado (`run_holdout_frozen.HOLDOUT`,
inicio mensal 2010-01 a 2013-12), a MESMA config (`BacktestConfig(initial_capital
=1000.0, lot_size=1, cash_yield_path="data/raw/selic.parquet")`). Tres bracos:
`campeao` (`LiquidChampion`), `dual10` (`LiquidDual10`), `ibov`.

PAREAMENTO: um dict de registros por janela (chave = data de inicio), so entram
na tabela as janelas em que campeao E dual10 produziram equity_curve com pelo
menos 250 pontos (o mesmo piso de `run_holdout_frozen.medir`). Nao ha listas
paralelas filtradas independentemente -- a mediana, o pior caso e o "bate IBOV"
sao todos calculados sobre o MESMO conjunto de janelas para os dois robos.

Por janela e por robo mede-se: CAGR, MaxDD, pior retorno de 12 meses
(eq/eq.shift(252)-1).min(), numero de trades e EXPOSICAO MEDIA (fracao do
patrimonio em acoes, no padrao `_Watched` de `run_champion_k_control.py` --
subclasses vigiadas criadas neste proprio script, sem tocar nas classes de
producao).

Os QUATRO CRITERIOS, declarados antes de rodar
------------------------------------------------
  (1) pior MaxDD do dual10 >= pior MaxDD do campeao E pior janela (CAGR) do
      dual10 >= pior janela do campeao -- nao pode piorar o pior caso.
  (2) CAGR mediano do dual10 >= CAGR mediano do campeao, nas mesmas janelas.
  (3) CONTROLE DE EXPOSICAO. Se a exposicao media do dual10 for MENOR que a do
      campeao, constroi-se a mistura estatica por janela
        w * (campeao normalizado) + (1-w) * (caixa Selic normalizado)
      com w = exp_media(dual10) / exp_media(campeao), usando
      `backtest.costs.cash_yield_series` exatamente como
      `run_champion_k_control.py`. O criterio PASSA se o dual10 for melhor que
      essa mistura em pior MaxDD E em pior 12 meses. Se a exposicao do dual10
      for maior ou igual a do campeao, o criterio passa automaticamente (nao
      ha caixa parado a explicar) e o script diz isso explicitamente.
  (4) dual10 bate o IBOV em mais de 24 das 48 janelas.

O veredito impresso no fim e so a conjuncao dos quatro. Nao ha meio-termo.

Vies residual declarado
------------------------
`strategy/liquid_dual10.py` documenta o vies de sobrevivencia ASSIMETRICO: o
`POOL` so tem empresas vivas em 2026, e isso infla a faixa 21-40 MAIS do que o
top-20, porque a mortalidade da B3 mora tipicamente fora das blue chips.
Qualquer numero de dual10 que venha da faixa 21-40 esta inflado por empresas
mortas ausentes do pool -- este script reimprime a ressalva ao lado do
veredito, nao so na docstring.

Uso: .venv/Scripts/python.exe scripts/run_dual10_holdout.py
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

from backtest.costs import cash_yield_series
from backtest.runner import run as run_bt
from core.config import BacktestConfig
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_dual10 import LiquidDual10

INITIAL = 1000.0
SELIC = "data/raw/selic.parquet"


class _ExposureMixin:
    """Anota a exposicao (fracao do patrimonio em acoes) a cada pregao.

    Mesmo padrao de `_Watched` em `scripts/run_champion_k_control.py`, aqui
    como mixin para nao duplicar o corpo entre o campeao e o dual10 -- as
    duas classes de producao continuam intocadas.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.expostos: list[float] = []
        self._closes: dict[str, pd.Series] = {}
        # Decomposicao por faixa (FURO 2) -- so faz sentido para o dual10 (10
        # sleeves: 0-4 sao o top-20, 5-9 sao a faixa 21-40). Ficam vazias para
        # o campeao (5 sleeves), protegido pelo `len(self._sleeves) == 10` em
        # `on_bar` abaixo -- nao muda nada do que o campeao ja media.
        self.faixa_top: list[float] = []
        self.faixa_mid: list[float] = []
        self.faixa_sem_dono: list[float] = []
        self.tem_top: list[bool] = []
        self.tem_mid: list[bool] = []

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

        # FURO 2: decomposicao por faixa, so para o dual10 (10 sleeves).
        # Le `self._owner` ANTES de chamar super().on_bar() de proposito:
        # `LiquidSleeves5.on_bar` reescreve `self._owner` bem no INICIO da
        # chamada a partir do MESMO `open_positions` que chega aqui (ver
        # `strategy/liquid_sleeves5.py`), entao o `self._owner` de ENTRADA
        # nesta chamada ja e exatamente o dono usado pela producao para
        # marcar estas MESMAS posicoes neste MESMO pregao -- e o dado mais
        # fresco e mais consistente possivel com o `mkt` acima (que tambem
        # usa o `open_positions` pre-trade). Ler DEPOIS de super() obrigaria
        # a lidar com saidas do dia (ja removidas de `_owner` mas ainda
        # presentes em `open_positions` pre-trade, virando "sem dono" a
        # toa) e com entradas do dia (que nem aparecem em `open_positions`
        # pre-trade) -- so ruido para o que se quer medir aqui. Posicao sem
        # dono conhecido (primeira barra, restart, carteira herdada) cai em
        # "sem dono" em vez de adivinhar por elegibilidade.
        if len(self._sleeves) == 10 and eq > 0:
            mkt_top = 0.0
            mkt_mid = 0.0
            mkt_sem = 0.0
            for t, p in open_positions.items():
                v = self._mark(t, date) * p.quantity
                i = self._owner.get(t)
                if i is None:
                    mkt_sem += v
                elif i < 5:
                    mkt_top += v
                else:
                    mkt_mid += v
            self.faixa_top.append(mkt_top / eq)
            self.faixa_mid.append(mkt_mid / eq)
            self.faixa_sem_dono.append(mkt_sem / eq)
            self.tem_top.append(mkt_top > 0)
            self.tem_mid.append(mkt_mid > 0)

        return super().on_bar(date, open_positions, cash_available)


class _WatchedChampion(_ExposureMixin, LiquidChampion):
    name = "liquid_champion_watched"
    candidate = False


class _WatchedDual10(_ExposureMixin, LiquidDual10):
    name = "liquid_dual10_watched"
    candidate = False


def medir(factory, u, start: pd.Timestamp) -> dict | None:
    """Mesmo piso de `run_holdout_frozen.medir` (>=250 pontos), mais exposicao e curva."""
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
        "eq": eq,
        # FURO 2 -- vazio (0.0) para o campeao, populado so para o dual10
        # (mixin protege por len(self._sleeves) == 10).
        "faixa_top": float(np.mean(bot.faixa_top)) if bot.faixa_top else 0.0,
        "faixa_mid": float(np.mean(bot.faixa_mid)) if bot.faixa_mid else 0.0,
        "faixa_sem_dono": float(np.mean(bot.faixa_sem_dono)) if bot.faixa_sem_dono else 0.0,
        "tem_top": float(np.mean(bot.tem_top)) if bot.tem_top else 0.0,
        "tem_mid": float(np.mean(bot.tem_mid)) if bot.tem_mid else 0.0,
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
    dual10_rows: dict[pd.Timestamp, dict] = {}
    ibov_rows: dict[pd.Timestamp, dict] = {}
    descartadas: list[pd.Timestamp] = []

    for i, start in enumerate(hf.HOLDOUT, 1):
        c = medir(_WatchedChampion, u, start)
        d = medir(_WatchedDual10, u, start)
        if c is None or d is None:
            descartadas.append(start)
            print(f"janela {i}/{total} inicio {start.date()} descartada "
                  f"(campeao={'ok' if c else 'curto'}, dual10={'ok' if d else 'curto'})",
                  flush=True)
            continue
        campeao_rows[start] = c
        dual10_rows[start] = d
        ibov_rows[start] = hf.ibov_janela(start)
        print(f"janela {i}/{total} inicio {start.date()} ok", flush=True)

    comuns = sorted(campeao_rows)  # so janelas presentes nos dois braços
    print(f"\n{len(descartadas)} janela(s) descartada(s) de {total}: "
          f"{[str(s.date()) for s in descartadas] if descartadas else 'nenhuma'}")
    print(f"{len(comuns)} janelas pareadas para a comparacao\n")

    campeao = [campeao_rows[s] for s in comuns]
    dual10 = [dual10_rows[s] for s in comuns]
    ib_cagr = [ibov_rows[s]["cagr"] for s in comuns]

    r_campeao = resumo("campeao (liquid_champion)", campeao, ib_cagr)
    r_dual10 = resumo("dual10 (liquid_dual10)", dual10, ib_cagr)
    # O IBOV entra na tabela com `exp` = 100%: o indice esta sempre comprado, e
    # e justamente essa a coluna que separa diversificacao de caixa parado.
    r_ibov = resumo("IBOV", [{**ibov_rows[s], "exp": 1.0} for s in comuns], ib_cagr)

    hdr = (f"{'robo':24s} {'n':>4s} {'p05':>8s} {'mediana':>8s} {'p95':>8s} "
           f"{'pior':>8s} {'DDpior':>8s} {'12m':>8s} {'neg':>4s} {'>ibov':>5s} "
           f"{'trd':>5s} {'exposto':>8s}")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    print(linha(r_ibov))
    print(linha(r_campeao))
    print(linha(r_dual10))
    print("=" * len(hdr))

    # ---------------------------------------------- FURO 2 (informativo, so dual10)
    faixa_top_vals = [dual10_rows[s]["faixa_top"] for s in comuns]
    faixa_mid_vals = [dual10_rows[s]["faixa_mid"] for s in comuns]
    faixa_sem_vals = [dual10_rows[s]["faixa_sem_dono"] for s in comuns]
    exp_faixa_top = float(np.mean(faixa_top_vals))
    exp_faixa_mid = float(np.mean(faixa_mid_vals))
    exp_faixa_sem = float(np.mean(faixa_sem_vals))
    ativo_top = float(np.mean([dual10_rows[s]["tem_top"] for s in comuns]))
    ativo_mid = float(np.mean([dual10_rows[s]["tem_mid"] for s in comuns]))
    print("\ndecomposicao da exposicao do dual10 por faixa (informativo, so dual10 -- "
          "o campeao nao tem duas faixas):")
    print(f"  faixa top-20 (sleeves 0-4): exposicao media {exp_faixa_top*100:.1f}%, "
          f"com >=1 posicao aberta em {ativo_top*100:.1f}% dos pregoes")
    print(f"  faixa 21-40  (sleeves 5-9): exposicao media {exp_faixa_mid*100:.1f}%, "
          f"com >=1 posicao aberta em {ativo_mid*100:.1f}% dos pregoes")
    print(f"  sem dono conhecido (deveria ser ~0): {exp_faixa_sem*100:.2f}%")
    print(f"  soma top-20 + 21-40: {(exp_faixa_top + exp_faixa_mid)*100:.1f}% "
          f"(exposicao total do dual10 medida acima: {r_dual10['exp']*100:.1f}%)")

    # ---------------------------------------------------------- criterio 1
    c1 = (r_dual10["dd"] >= r_campeao["dd"]) and (r_dual10["pior"] >= r_campeao["pior"])
    print(f"\n(1) pior caso nao piora: DDpior dual10 {r_dual10['dd']*100:.1f}% >= "
          f"campeao {r_campeao['dd']*100:.1f}%  E  pior janela dual10 "
          f"{r_dual10['pior']*100:.1f}% >= campeao {r_campeao['pior']*100:.1f}%  "
          f"-> {sim_nao(c1)}")

    # ---------------------------------------------------------- criterio 2
    c2 = r_dual10["med"] >= r_campeao["med"]
    print(f"(2) CAGR mediano: dual10 {r_dual10['med']*100:.1f}% >= campeao "
          f"{r_campeao['med']*100:.1f}%  -> {sim_nao(c2)}")

    # ---------------------------------------------------------- criterio 3
    exp_campeao = r_campeao["exp"]
    exp_dual10 = r_dual10["exp"]
    if exp_dual10 >= exp_campeao:
        c3 = True
        print(f"(3) exposicao media: dual10 {exp_dual10*100:.1f}% >= campeao "
              f"{exp_campeao*100:.1f}% -- nao ha caixa parado a explicar, "
              f"criterio passa automaticamente -> {sim_nao(c3)}")
    else:
        w = exp_dual10 / exp_campeao if exp_campeao else 0.0
        misturas = []
        for s in comuns:
            eqc = campeao_rows[s]["eq"]
            rate = cash_yield_series(SELIC, eqc.index)
            caixa = (1.0 + rate).cumprod() if rate is not None else pd.Series(1.0, index=eqc.index)
            blend = w * (eqc / eqc.iloc[0]) + (1.0 - w) * (caixa / caixa.iloc[0])
            anos = (blend.index[-1] - blend.index[0]).days / 365.25
            cagr = (blend.iloc[-1] / blend.iloc[0]) ** (1.0 / anos) - 1.0
            misturas.append({
                "dd": float((blend / blend.cummax() - 1).min()),
                "w12": float((blend / blend.shift(252) - 1).min()),
                "cagr": float(cagr),
            })
        blend_dd = min(m["dd"] for m in misturas)
        blend_w12 = min(m["w12"] for m in misturas)
        c3 = (r_dual10["dd"] > blend_dd) and (r_dual10["w12"] > blend_w12)
        print(f"(3) exposicao media: dual10 {exp_dual10*100:.1f}% < campeao "
              f"{exp_campeao*100:.1f}% -- mistura estatica w={w:.2f} campeao + "
              f"{1-w:.2f} Selic: DDpior mistura {blend_dd*100:.1f}%, 12m pior mistura "
              f"{blend_w12*100:.1f}%; dual10 DDpior {r_dual10['dd']*100:.1f}%, 12m pior "
              f"{r_dual10['w12']*100:.1f}%  -> {sim_nao(c3)}")

        # ------------------------------------------------ FURO 1 (informativo)
        # O controle que aposentou o k=10 (`run_champion_k_control.py`, ver
        # docstring de `strategy/liquid_champion.py`) tambem comparava CAGR
        # mediano e pior janela, nao so DD e 12m. NAO muda `c3` nem o
        # veredito -- so acrescenta a mesma comparacao completa aqui.
        blend_cagr_med = float(np.median([m["cagr"] for m in misturas]))
        blend_cagr_pior = min(m["cagr"] for m in misturas)
        print(f"\ninformativo, fora do criterio declarado -- controle completo "
              f"(CAGR mediano e pior janela), mesmo padrao que aposentou o k=10:")
        print(f"{'':30s} {'CAGR mediano':>13s} {'pior janela':>12s} "
              f"{'DDpior':>8s} {'12m pior':>9s}")
        print(f"{'mistura w=' + f'{w:.2f}' + ' campeao+Selic':30s} "
              f"{blend_cagr_med*100:12.1f}% {blend_cagr_pior*100:11.1f}% "
              f"{blend_dd*100:7.1f}% {blend_w12*100:8.1f}%")
        print(f"{'dual10':30s} {r_dual10['med']*100:12.1f}% "
              f"{r_dual10['pior']*100:11.1f}% {r_dual10['dd']*100:7.1f}% "
              f"{r_dual10['w12']*100:8.1f}%")
        colunas_dual10_ganha = [
            r_dual10["med"] > blend_cagr_med,
            r_dual10["pior"] > blend_cagr_pior,
            r_dual10["dd"] > blend_dd,
            r_dual10["w12"] > blend_w12,
        ]
        print(f"dual10 ganha da mistura em {sum(colunas_dual10_ganha)}/4 colunas "
              f"(informativo, fora do criterio declarado -- o veredito de (3) "
              f"continua sendo so DD e 12m)")

    # ---------------------------------------------------------- criterio 4
    c4 = r_dual10["bate_ibov"] > 24
    print(f"(4) bate IBOV em {r_dual10['bate_ibov']}/{len(comuns)} janelas "
          f"(precisa > 24)  -> {sim_nao(c4)}")

    veredito = c1 and c2 and c3 and c4
    print(f"\nVEREDITO (conjuncao dos 4 criterios): {sim_nao(veredito)}")
    print("ressalva: o numero da faixa 21-40 dentro do dual10 esta inflado por "
          "empresas mortas ausentes do pool (vies de sobrevivencia assimetrico, "
          "ver docstring de strategy/liquid_dual10.py)")


if __name__ == "__main__":
    main()
