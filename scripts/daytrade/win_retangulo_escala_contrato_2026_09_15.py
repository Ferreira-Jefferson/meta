# -*- coding: utf-8 -*-
"""`win_retangulo`: como dimensionar contrato pelo caixa, com o risco por
contrato DIMINUINDO a cada contrato novo.

Pedido do dono (2026-09-15): "ele tem que saber aumentar e diminuir contratos
de acordo com o capital que tem disponivel, sempre diminuindo o risco a cada
novo contrato".

## O que o robo faz HOJE

`WinRetangulo` pede `quantity=self.quantidade` com `quantidade=1` FIXO. O motor
so' sabe REDUZIR esse pedido (`_cap_capital_atual`), nunca aumentar. Entao o
robo ja sabe DIMINUIR por capital; o que falta e' AUMENTAR.

## A parte que precisa ser medida antes de virar default

"Diminuir o risco a cada novo contrato" nao e' uma regra, e' uma FAMILIA de
regras -- o que muda entre elas e' a taxa com que o teto por contrato cai:

- **S1 (risco total CONSTANTE)**: teto por contrato = R$80/n. Somando, a
  operacao inteira nunca arrisca mais que R$80, em qualquer quantidade. E' a
  leitura literal e a mais conservadora. Consequencia mecanica: como o stop e'
  0,50 x largura x R$0,20, o 2o contrato exige largura <= 400 pontos e o 3o
  exigiria <= 266, abaixo do piso de 328 -- ou seja, S1 trava em 2 contratos
  por construcao.
- **S2 (raiz)**: teto por contrato = R$80/raiz(n). O risco total cresce com
  raiz(n) em vez de n. Meio-termo.
- **S3 (teto por contrato CONSTANTE)**: teto = R$80 para cada contrato, risco
  total cresce LINEAR. Nao atende ao pedido; entra na tabela como o contrafactual
  que mostra o tamanho do efeito do freio.
- **S4 (risco como % do caixa)**: quantidade por `contracts_from_risk` com 1%
  do caixa por trade, que e' a forma ja validada neste repo.

## Por que o freio importa, com numero

Item 3.9 de `LICOES_DE_PRODUCAO.md`: margem protege a CORRETORA (chamada de
margem), nao o DONO (ruina por sequencia de stops). Medido no `CopaWin` (WIN@,
R$3.000 reais, 182 pregoes): o caixa subiu 43% num dia bom, o teto por margem
escalou a proxima entrada de 12 para 15 contratos, e o MESMO `stop_vol` de
sempre -- agora sobre 15 contratos -- perdeu R$3.457,50 num unico trade. A
conta foi de R$3.000,00 a R$68,50 (-97,7%) sem nunca ficar negativa, com margem
e reserva funcionando exatamente como desenhadas.

## Janelas

IS (< 2026-06-13) e OOS (>= 2026-06-13) congeladas, mais o ultimo mes
(2026-08-15 a 2026-09-15) pedido em separado. O pregao de 15/09 entra porque o
pedido diz "ate hoje", e sai tambem numa linha propria -- ele tinha ~501 barras
contra ~562 de um pregao completo quando isto rodou.

Capital inicial R$1.100 (piso medido) em todas as linhas, e o caixa ACUMULA: o
motor chama `on_capital_update(initial_capital + realized_pnl)` a cada barra.

`fila NAO CALIBRADA`: o WIN@ nao tem entrada em `fidelidade.py`, entao toda
ordem-limite enche no TOQUE, dos dois lados. Premissa otimista na entrada E no
alvo; honesta so' no stop, que e' a mercado.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_escala_contrato_2026_09_15.py`
"""
from __future__ import annotations

import math
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
from strategy.daytrade.base import (  # noqa: E402
    contracts_from_capital_operacional, contracts_from_risk)
from strategy.daytrade.lab.win_retangulo import WinRetangulo  # noqa: E402

CAPITAL = float(WinRetangulo.capital_minimo_recomendado_brl)
MARGEM_WIN = 100.0
MIN_BARRAS = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
INICIO_MES = pd.Timestamp("2026-08-15").date()
TETO_BASE = 80.0
RISCO_PCT = 0.01
EXTRAS = ("pts/op", "BEemp%", "ctr max", "ctr med", "sem trade", "pior op.", "risco max")


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ic95(k: int, n: int):
    if n == 0:
        return float("nan"), float("nan")
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - r) / d, (c + r) / d


#: Como o teto de risco POR CONTRATO cai conforme a posicao cresce.
#: `None` na chave "risco" = quantidade vem da margem; caso contrario vem do
#: risco por trade.
ESCALAS = {
    "S1": lambda n: TETO_BASE / n,
    "S2": lambda n: TETO_BASE / math.sqrt(n),
    "S3": lambda n: TETO_BASE,
    "S4": lambda n: TETO_BASE,
}


class RetanguloEscalado(WinRetangulo):
    """`WinRetangulo` que PEDE contrato conforme o caixa, com teto de risco por
    contrato decrescente.

    A quantidade e' recalculada a cada barra (`on_capital_update`), entao ela
    sobe E desce acompanhando o caixa -- o motor continua aplicando o teto dele
    por cima (`_cap_capital_atual`), que nunca deixa o pedido passar do que a
    margem sustenta.

    O teto de risco do robo e' avaliado na DETECCAO
    (`stop_fracao x largura x R$0,20 x quantidade`), entao com teto por contrato
    decrescente o retangulo largo deixa de caber em quantidade alta -- que e'
    exatamente o efeito pedido: mais contratos so' em retangulo mais apertado.
    """

    def __init__(self, *args, escala="S1", por_risco=False, **kw):
        super().__init__(*args, **kw)
        self.escala = escala
        self.por_risco = por_risco
        self._caixa = CAPITAL

    def on_capital_update(self, cash_brl: float) -> None:
        super().on_capital_update(cash_brl)
        self._caixa = float(cash_brl)
        if not self.por_risco:
            self._aplica(contracts_from_capital_operacional(self._caixa, MARGEM_WIN))

    def _aplica(self, n: int) -> None:
        self.quantidade = max(1, int(n))
        # Teto TOTAL da operacao = teto por contrato x quantidade. Com S1 isso
        # devolve R$80 fixos; com S3, R$80 x n.
        self.risco_maximo_brl = ESCALAS[self.escala](self.quantidade) * self.quantidade

    def _tenta_detectar(self) -> None:
        if not self.por_risco:
            return super()._tenta_detectar()
        # A quantidade por risco depende do stop DAQUELA entrada, que depende
        # da largura -- que so' se conhece depois de o retangulo passar. Avalia
        # o teto com 1 contrato, dimensiona em cima do retangulo aceito.
        self._aplica(1)
        super()._tenta_detectar()
        if self._retangulo is None:
            return
        stop_reais = (self.stop_fracao_largura * self._retangulo["largura"]
                      * self.valor_do_ponto_brl)
        self._aplica(contracts_from_risk(self._caixa, RISCO_PCT, stop_reais))


class RetanguloPorRiscoHarmonico(WinRetangulo):
    """O desenho CERTO: quem decide a quantidade e' o RISCO; a margem e' so' o
    teto de cima.

    "Sempre diminuindo o risco a cada novo contrato" (pedido do dono,
    2026-09-15) vira uma regra exata: o contrato `k` recebe um orcamento de
    risco `TETO_BASE / k`. O orcamento TOTAL de `n` contratos e' entao
    `TETO_BASE x H(n)`, com `H` o harmonico -- cresce, mas sempre menos que
    linear, e cada contrato novo entra com menos risco que o anterior.

    Na pratica: `n` contratos so' cabem se o risco por contrato daquela
    entrada couber em `TETO_BASE x H(n)/n`. Como o risco por contrato e'
    `0,50 x largura x R$0,20`, isso significa que quantidade alta so' aparece
    em retangulo mais APERTADO -- exatamente o efeito pedido.

    | n | orcamento total | largura maxima |
    |---|---|---|
    | 1 | R$ 80,00  | 800 pontos |
    | 2 | R$120,00  | 600 |
    | 3 | R$146,67  | 489 |
    | 4 | R$166,67  | 417 |
    | 5 | R$182,67  | 365 |

    A quantidade e' recalculada a cada barra pelo caixa (sobe E desce), e o
    motor ainda aplica o teto dele por cima (`_cap_capital_atual`).
    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._caixa = CAPITAL
        self._teto_margem = contracts_from_capital_operacional(CAPITAL, MARGEM_WIN)

    def on_capital_update(self, cash_brl: float) -> None:
        super().on_capital_update(cash_brl)
        self._caixa = float(cash_brl)
        self._teto_margem = contracts_from_capital_operacional(self._caixa, MARGEM_WIN)

    def _tenta_detectar(self) -> None:
        # Teto avaliado com 1 contrato: a quantidade so' pode ser decidida
        # depois de a largura ser conhecida.
        self.quantidade = 1
        self.risco_maximo_brl = TETO_BASE
        super()._tenta_detectar()
        if self._retangulo is None:
            return
        risco_unit = (self.stop_fracao_largura * self._retangulo["largura"]
                      * self.valor_do_ponto_brl)
        orc = self._orcamento()
        n = 0
        h = 0.0
        for k in range(1, max(1, self._teto_margem) + 1):
            h += 1.0 / k
            if risco_unit * k <= orc * h:
                n = k
            else:
                break
        self.quantidade = max(1, n)
        self.risco_maximo_brl = orc * sum(1.0 / k for k in range(1, self.quantidade + 1))

    def _orcamento(self) -> float:
        return TETO_BASE


#: Orcamento de risco do 1o contrato como FRACAO do caixa. Calibrado para
#: devolver exatamente os R$80 de hoje no piso de R$1.100 (80/1100), entao no
#: caixa minimo o robo se comporta como a producao atual e so' diverge quando o
#: caixa de fato cresce -- que e' o pedido ("de acordo com o capital que tem
#: disponivel"). Ancorar no caixa e' o que faz a quantidade subir E descer; com
#: orcamento absoluto o robo teria a MESMA alavancagem com R$1.100 ou R$10.000.
PCT_CAIXA = TETO_BASE / CAPITAL


class RetanguloPorCaixa(RetanguloPorRiscoHarmonico):
    """S5 com o orcamento ANCORADO NO CAIXA em vez de fixo em R$80."""

    def _orcamento(self) -> float:
        return PCT_CAIXA * self._caixa


VARIANTES = [
    ("S0 1 contrato fixo (producao)", None),
    ("S1 total constante (80/n)", dict(escala="S1")),
    ("S2 raiz (80/raiz n)", dict(escala="S2")),
    ("S3 por contrato 80 (linear)", dict(escala="S3")),
    ("S4 risco 1% do caixa", dict(escala="S4", por_risco=True)),
    ("S5 harmonico, orcamento fixo 80", "harmonico"),
    ("S6 harmonico, orcamento = % caixa", "por_caixa"),
]


def _unidade(args):
    janela, rotulo, kw, dias = args
    if kw is None:
        robo = WinRetangulo()
    elif kw == "harmonico":
        robo = RetanguloPorRiscoHarmonico()
    elif kw == "por_caixa":
        robo = RetanguloPorCaixa()
    else:
        robo = RetanguloEscalado(**kw)
    df = load_m1(robo.symbol).sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    profile = profile_for(robo.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01, initial_capital=CAPITAL,
        target_fills_as_maker=robo.target_fills_as_maker,
        anchor_exits_at_fill=robo.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True)
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, robo, cfg)
    trades = list(res.trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = (sum(g) / len(g)) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = (pm / (gm + pm)) if (g and p) else float("nan")
    qt = [int(getattr(t, "quantity", 1) or 1) for t in trades]
    pts = ((sum(t.pnl_brl for t in trades) / len(trades)) / 0.20) if trades else float("nan")
    com = {t.exit_ts.date() for t in trades}
    # Rebaixamento POR OPERACAO -- o que o portao de capital de fato ve.
    pico = acum = 0.0
    dd = 0.0
    for t in trades:
        acum += t.pnl_brl
        pico = max(pico, acum)
        dd = max(dd, pico - acum)
    extras = {
        "pts/op": br(pts, 1),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "ctr max": str(max(qt)) if qt else "—",
        "ctr med": br(sum(qt) / len(qt), 2) if qt else "—",
        "sem trade": f"{len(dias)-len(com)}/{len(dias)}",
        "pior op.": br(min(p)) if p else "—",
        "risco max": br(max(abs(v) for v in p)) if p else "—",
    }
    return (janela, rotulo,
            linha_de_resultado(rotulo, res, CAPITAL, extras=extras),
            dd, _ic95(len(g), len(trades)), be, len(trades))


def main():
    df = load_m1("WIN@").sort_index()
    c = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in c.items() if n >= MIN_BARRAS)
    janelas = [
        ("IS", [d for d in completos if d < CORTE_OOS]),
        ("OOS", [d for d in completos if CORTE_OOS <= d <= HOJE]),
        ("ULTIMO MES", [d for d in completos if INICIO_MES <= d <= HOJE]),
    ]

    print("=" * 178)
    print("win_retangulo -- dimensionar contrato pelo caixa, com risco por contrato DECRESCENTE")
    print("=" * 178)
    print(f"  capital inicial R$ {br(CAPITAL,0)} (piso medido), ACUMULANDO | margem WIN@ "
          f"R$ {br(MARGEM_WIN,0)}/contrato | fila NAO CALIBRADA")
    print(f"  ultimo mes: {janelas[2][1][0]} a {janelas[2][1][-1]} ({len(janelas[2][1])} pregoes); "
          f"15/09 incluido a pedido, com {int(c.get(HOJE,0))} barras contra ~562 de um completo\n")

    print("  ESCADA DE CONTRATOS por caixa (contracts_from_capital_operacional, margem R$100):")
    ant = None
    for caixa in range(100, 4000, 25):
        n = contracts_from_capital_operacional(float(caixa), MARGEM_WIN)
        if n != ant:
            print(f"    caixa a partir de R$ {br(caixa,0):>6}  ->  {n} contrato(s)")
            ant = n
    print("\n  TETO DE RISCO POR CONTRATO em cada escala (R$):")
    print(f"    {'n':<4}{'S1 total const':>16}{'S2 raiz':>12}{'S3 linear':>12}"
          f"{'| S1 total':>12}{'S2 total':>11}{'S3 total':>11}")
    for n in (1, 2, 3, 4, 5):
        print(f"    {n:<4}{br(ESCALAS['S1'](n)):>16}{br(ESCALAS['S2'](n)):>12}"
              f"{br(ESCALAS['S3'](n)):>12}{br(ESCALAS['S1'](n)*n):>12}"
              f"{br(ESCALAS['S2'](n)*n):>11}{br(ESCALAS['S3'](n)*n):>11}")
    print(flush=True)

    tarefas = [(jan, rot, kw, dias) for jan, dias in janelas for rot, kw in VARIANTES]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            jan, rot, linha, dd, ic, be, n = fut.result()
            out[(jan, rot)] = (linha, dd, ic, be, n)
            print(f"  [pronto] {jan:<11} {rot:<32} {n:>4} operacoes", flush=True)

    for jan, dias in janelas:
        print("\n" + "=" * 178)
        print(f"{jan}  ({len(dias)} pregoes)")
        print("=" * 178)
        print(tabela([out[(jan, rot)][0] for rot, _ in VARIANTES], extras=EXTRAS))
        print(f"\n  {'variante':<32}{'rebaix./operacao':>18}{'piso de caixa':>15}"
              f"{'IC95 do acerto':>22}{'BEemp':>9}{'margem pp':>11}")
        for rot, _ in VARIANTES:
            _l, dd, ic, be, _n = out[(jan, rot)]
            piso = dd + MARGEM_WIN
            margem = (100 * (ic[0] - be)) if (be == be and ic[0] == ic[0]) else float("nan")
            print(f"  {rot:<32}{br(dd):>18}{br(piso):>15}"
                  f"{('[' + br(100*ic[0],1) + ' ; ' + br(100*ic[1],1) + ']'):>22}"
                  f"{(br(100*be,1) + '%'):>9}{br(margem,1):>11}")

    print("\n" + "=" * 178)
    print("COMO LER")
    print("=" * 178)
    print("  * S0 e' o robo de PRODUCAO de hoje. S1-S4 sao desenhos novos: nenhum deles tem")
    print("    janela cega propria, porque o OOS ja foi visto ao escolher os parametros atuais.")
    print("  * `piso de caixa` = rebaixamento POR OPERACAO + margem crua R$100. E' o numero que")
    print("    o portao de capital de fato ve; a serie diaria suaviza e engana.")
    print("  * S3 (linear) nao atende ao pedido -- esta' aqui so' para medir o tamanho do freio.")
    print("  * O ULTIMO MES esta inteiro dentro do OOS: e' zoom nas mesmas operacoes.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
