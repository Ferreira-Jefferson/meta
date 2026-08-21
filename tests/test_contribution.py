"""Testes de APORTE MENSAL (`BacktestConfig.monthly_contribution`), SAQUE
(`backtest.withdrawal`) e `irr_annual` — os tres compartilham a mesma
contabilidade de COTA (`units`) no engine de portfolio.

Cobre: (1) o default sem aporte tem de continuar byte-a-byte identico ao
comportamento historico do engine — 16 anos de diario gravado dependem disso;
(2) cadencia/contagem dos aportes, incluindo o mes do capital inicial NAO
receber aporte; (3) o aporte cai no primeiro PREGAO existente do mes, nunca
no dia 1 do calendario; (4) a curva de COTA isola desempenho de entrada de
dinheiro novo; (5) `irr_annual` acerta casos fechados e devolve `nan` quando
nao ha troca de sinal; (6) o aporte e cotizado pelo fechamento ANTERIOR,
nunca pelo preco do proprio dia (a mesma proibicao de look-ahead da regra 4
do AGENTS.md, aplicada ao dinheiro novo em vez de ao sinal); (7) saque REDIME
cotas e por isso NAO aparece como drawdown de cota; (8) TIR com aporte E
saque no mesmo run, verificada por VPL; (9) taxa de liquidacao do saque
continua derrubando a cota (e so ela, nao o valor sacado inteiro); (10) saque
sozinho, sem nenhum aporte, tambem ativa a contabilidade de cota — fluxo e
fluxo, nao importa o sentido.

Reusa os helpers de `tests/test_engine_portfolio.py` (`_StubStrategy`,
`_panel`, `_ohlc`) em vez de duplicar: sao exatamente o harness ja usado para
testar este mesmo engine — duplicar arriscaria as duas copias divergirem
silenciosamente se o formato do OHLCV mudar.
"""
from __future__ import annotations

import math
from datetime import date as _date
from datetime import timedelta

import pandas as pd
import pytest

from backtest.engine_portfolio import run_portfolio_backtest
from backtest.metrics import irr_annual
from backtest.sizing import plan_entry
from backtest.withdrawal import FloorSkim
from core.config import BENCHMARK, BacktestConfig, CostModel
from strategy.base import Enter
from tests.test_engine_portfolio import _StubStrategy, _panel


# ---------------------------------------------------------------------------
# (1) default sem aporte: nada pode mudar de valor
# ---------------------------------------------------------------------------

def test_default_sem_aporte_e_byte_a_byte_identico_ao_comportamento_historico():
    """Se isto falhar, os 16 anos de diario gravado SEM aporte deixam de ser
    reproduziveis: qualquer run antiga recalculada com o codigo novo passaria
    a divergir do que ja foi persistido, mesmo que ninguem tenha configurado
    aporte nenhum — a feature nova vazaria efeito colateral para quem nunca
    pediu por ela.
    """
    dates = pd.bdate_range("2024-01-02", periods=90)  # ~4 meses civis
    prices = [50.0 + 0.1 * i for i in range(90)]
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * 90),
    }
    strategy = _StubStrategy({dates[2]: [Enter(ticker="TEST.SA")]})
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0)
    assert config.monthly_contribution == 0.0  # confirma que estamos no default

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert r.contributions == []
    pd.testing.assert_series_equal(r.unit_curve, r.equity_curve, check_names=False)
    for key in ("irr", "cagr_unit", "max_drawdown_unit", "contributed_total", "contributions_count"):
        assert key not in r.metrics


# ---------------------------------------------------------------------------
# (2) cadencia e contagem: (meses civis - 1), mes do capital inicial pula
# ---------------------------------------------------------------------------

def test_cadencia_conta_meses_civis_menos_um_e_pula_o_mes_do_capital_inicial():
    """Se a contagem estiver errada — por exemplo, contar tambem o mes de
    abertura da conta, ou perder um mes no meio do periodo — `contributed_total`
    passa a descrever um valor que o usuario nunca depositou de verdade, e
    toda metrica derivada (capital final, IRR) fica calculada sobre um fluxo
    de caixa fictício.
    """
    dates = pd.bdate_range("2024-01-15", "2024-04-25")  # jan/fev/mar/abr = 4 meses civis
    prices = [100.0] * len(dates)
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * len(dates)),
    }
    strategy = _StubStrategy({})  # nenhuma acao — so interessa a contabilidade de aporte
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0, monthly_contribution=1_000.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    meses_distintos = len({(d.year, d.month) for d in dates})
    assert meses_distintos == 4
    assert len(r.contributions) == meses_distintos - 1 == 3
    assert r.metrics["contributions_count"] == 3
    assert r.metrics["contributed_total"] == pytest.approx(3 * 1_000.0)

    # O mes do capital inicial (janeiro) NAO recebe aporte — ele ja e o
    # primeiro deposito. O primeiro aporte tem de cair no mes SEGUINTE.
    primeira_data = r.contributions[0][0]
    assert (primeira_data.year, primeira_data.month) == (2024, 2)


# ---------------------------------------------------------------------------
# (3) aporte cai no primeiro PREGAO do mes, nao no dia 1 do calendario
# ---------------------------------------------------------------------------

def test_aporte_cai_no_primeiro_pregao_existente_nao_no_dia_1_do_calendario():
    """Se o engine decidisse o aporte olhando o calendario (dia 1) em vez do
    indice real de pregoes, um mes cujo dia 1 caia num feriado/fim de semana
    faria o aporte tentar acontecer numa data sem barra — na pratica, ou o
    dinheiro daquele mes simplesmente some, ou o codigo quebra tentando
    marcar a mercado uma data fora do universo.
    """
    full = pd.bdate_range("2024-01-15", "2024-02-15")
    fev1 = pd.Timestamp("2024-02-01")
    assert fev1 in full  # 2024-02-01 e quinta-feira: precisa estar no indice p/ o drop provar algo
    dates = full.drop(fev1)  # simula feriado no primeiro pregao "de calendario" de fevereiro
    prices = [100.0] * len(dates)
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(full, [100_000.0] * len(full)),
    }
    strategy = _StubStrategy({})
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0, monthly_contribution=1_000.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.contributions) == 1
    proximo_pregao_existente = dates[dates > fev1].min()
    assert proximo_pregao_existente.month == 2 and proximo_pregao_existente.day > 1
    assert r.contributions[0][0] == proximo_pregao_existente.date()


# ---------------------------------------------------------------------------
# (4) cota isola desempenho de dinheiro novo
# ---------------------------------------------------------------------------

def test_cota_fica_constante_com_preco_parado_mesmo_a_conta_crescendo_por_aporte():
    """Se a cota nao isolar o efeito do dinheiro novo, ela vira apenas um
    clone em outra escala da curva de patrimonio — a metrica que existe
    exatamente para responder 'quanto o gestor rendeu' passaria a mentir toda
    vez que houvesse aporte, fazendo um robo que nao fez ABSOLUTAMENTE NADA
    parecer que gerou retorno.
    """
    dates = pd.bdate_range("2024-01-15", "2024-05-15")
    prices = [100.0] * len(dates)  # preco totalmente parado
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * len(dates)),
    }
    strategy = _StubStrategy({})  # nenhuma acao — robo nao faz nada
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0, monthly_contribution=1_000.0,
                             cash_yield_path=None)  # caixa nao rende — nao pode poluir a cota

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.contributions) >= 1
    # Patrimonio cresceu — mas so porque entrou dinheiro novo, nao porque
    # rendeu nada.
    assert r.equity_curve.iloc[-1] > r.equity_curve.iloc[0] + 1.0
    assert r.unit_curve.iloc[0] == pytest.approx(100_000.0, abs=1e-6)
    assert r.unit_curve.iloc[-1] == pytest.approx(100_000.0, abs=1e-6)
    assert r.unit_curve.max() == pytest.approx(r.unit_curve.min(), abs=1e-6)


# ---------------------------------------------------------------------------
# (5) irr_annual — casos fechados
# ---------------------------------------------------------------------------

def test_irr_annual_1000_entra_1100_sai_em_1_ano_da_aproximadamente_10_por_cento():
    """Se a bissecção de `irr_annual` estiver errada, `metrics['irr']` — a
    UNICA medida de retorno honesta quando ha aporte, segundo o proprio
    docstring da funcao — passa a mentir para o usuario sobre quanto ele
    realmente ganhou por ano, sem que `cagr`/`cagr_unit` deem nenhum sinal
    disso (elas respondem outra pergunta).
    """
    t0 = _date(2024, 1, 2)
    t1 = t0 + timedelta(days=365)
    taxa = irr_annual([(t0, -1000.0), (t1, 1100.0)])
    assert taxa == pytest.approx(0.10, abs=2e-3)


def test_irr_annual_dois_aportes_verificado_por_vpl_proximo_de_zero():
    """Mesmo risco do teste anterior, mas no formato REAL de uso (mais de um
    fluxo negativo, como capital inicial + varios aportes mensais) — prova
    que a bissecção nao para de encontrar raiz so porque o fluxo tem mais de
    dois pontos.
    """
    t0 = _date(2024, 1, 2)
    flows = [
        (t0, -1000.0),
        (t0 + timedelta(days=180), -500.0),
        (t0 + timedelta(days=365), 1800.0),
    ]
    taxa = irr_annual(flows)
    assert not math.isnan(taxa)
    anos = [(d - t0).days / 365.25 for d, _ in flows]
    vpl = sum(v / ((1.0 + taxa) ** a) for (_, v), a in zip(flows, anos))
    assert vpl == pytest.approx(0.0, abs=1e-4)


def test_irr_annual_sem_troca_de_sinal_devolve_nan():
    """Um fluxo so de saidas de caixa (nunca uma entrada) nao tem taxa nenhuma
    que zere o VPL. Se a funcao devolvesse um numero aqui em vez de `nan`,
    quem consome `metrics['irr']` receberia um valor com CARA de taxa
    plausivel mas sem nenhum significado — e sem jeito de distinguir do caso
    valido.
    """
    t0 = _date(2024, 1, 2)
    flows = [(t0, -100.0), (t0 + timedelta(days=30), -50.0)]
    assert math.isnan(irr_annual(flows))


# ---------------------------------------------------------------------------
# (6) aporte nao vira look-ahead: cotizado pelo fechamento ANTERIOR
# ---------------------------------------------------------------------------

def test_aporte_e_cotizado_pelo_fechamento_anterior_nunca_pelo_salto_do_proprio_dia():
    """Se o aporte fosse cotizado pelo preco do PROPRIO dia, um salto grande
    de preco bem no dia do aporte mudaria quantas cotas o dinheiro novo
    compra usando uma informacao que so existe no FECHAMENTO daquele mesmo
    dia — exatamente a classe de look-ahead que a regra 4 do AGENTS.md proibe
    para o sinal de entrada, so que aplicada ao aporte em vez de ao sinal.
    Isso inflaria (ou diluiria) artificialmente as cotas de quem aporta perto
    de um movimento grande de mercado.
    """
    dates = pd.bdate_range("2024-01-15", "2024-02-10")
    feb1 = pd.Timestamp("2024-02-01")
    assert feb1 in dates
    idx_feb1 = dates.get_loc(feb1)
    # preco parado em 100 ate a vespera do aporte, depois salta para 500
    # exatamente no dia em que o aporte e creditado (e no dia seguinte).
    prices = [100.0] * idx_feb1 + [500.0] * (len(dates) - idx_feb1)
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * len(dates)),
    }
    strategy = _StubStrategy({dates[0]: [Enter(ticker="TEST.SA")]})  # entra no open de dates[1], preco 100
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0, monthly_contribution=1_000.0)

    plan = plan_entry(100_000.0, 100.0, None, config)
    cash_apos_entrada = 100_000.0 - plan.cost
    patrimonio_correto = cash_apos_entrada + 100.0 * plan.quantity        # marcado no fechamento ANTERIOR (100)
    patrimonio_se_fosse_look_ahead = cash_apos_entrada + 500.0 * plan.quantity  # marcado no preco do proprio dia (500)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool")

    assert len(r.contributions) == 1
    data_aporte, valor_aporte = r.contributions[0]
    assert data_aporte == feb1.date()

    # `equity_curve` e `unit_curve` sao gravadas no MESMO ponto do loop (apos
    # o aporte ja creditado), entao a razao entre as duas no dia do aporte
    # devolve o numero de cotas total naquele momento.
    unidades_apos_aporte = r.equity_curve.loc[feb1] / r.unit_curve.loc[feb1]
    unidades_esperadas_correto = 1.0 + valor_aporte / patrimonio_correto
    unidades_se_fosse_look_ahead = 1.0 + valor_aporte / patrimonio_se_fosse_look_ahead

    assert unidades_apos_aporte == pytest.approx(unidades_esperadas_correto, rel=1e-9)
    assert unidades_apos_aporte != pytest.approx(unidades_se_fosse_look_ahead, rel=1e-6)


# ---------------------------------------------------------------------------
# (7) saque REDIME cotas: nao aparece como drawdown de cota
# ---------------------------------------------------------------------------

def test_saque_nao_vira_drawdown_de_cota():
    """Espelho exato do teste (4), do lado do saque: se a cota nao redimir no
    saque, `equity/units` despenca a cada retirada como se a ESTRATEGIA
    tivesse perdido dinheiro — `max_drawdown_unit` passaria a reportar como
    risco de mercado algo que foi so o dono tirando dinheiro da propria
    conta. Preco parado + robo no-op isola exatamente esse efeito: qualquer
    queda de cota aqui SO pode vir de um saque mal contabilizado.
    """
    dates = pd.bdate_range("2024-01-15", "2024-04-25")
    prices = [100.0] * len(dates)  # preco totalmente parado
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * len(dates)),
    }
    strategy = _StubStrategy({})  # nenhuma acao — robo nao faz nada
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0)  # sem aporte (default 0.0)
    # pct=0.5/floor=0/min=0: saca metade do equity no 3o pregao de cada mes,
    # sem liquidar posicao (nao ha posicao — so caixa) e sem custo nenhum.
    policy = FloorSkim(pct=0.5, floor=0.0, day=3, cap=1e12, min_amount=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool",
                                withdrawal_policy=policy)

    assert len(r.withdrawals) >= 2, "precisa de mais de um saque para provar constancia, nao coincidencia"
    # Patrimonio caiu (dinheiro saiu de verdade) ...
    assert r.equity_curve.iloc[-1] < r.equity_curve.iloc[0]
    # ... mas a cota, que mede desempenho, ficou parada — nada rendeu, nada
    # caiu por causa de mercado.
    primeiro = r.unit_curve.iloc[0]
    assert primeiro == pytest.approx(100_000.0, rel=1e-9)
    for valor in r.unit_curve:
        assert valor == pytest.approx(primeiro, rel=1e-9)


# ---------------------------------------------------------------------------
# (8) TIR com aporte E saque no mesmo run — verificada por VPL
# ---------------------------------------------------------------------------

def test_irr_com_aporte_e_saque_verificado_por_vpl():
    """A TIR e a metrica que promete ser 'a unica honesta quando ha fluxo'.
    Ela so cumpre essa promessa se enxergar TODO fluxo — aporte (saida do
    bolso do dono) E saque (volta para o bolso do dono) — no mesmo run. Se o
    saque tivesse ficado de fora do fluxo (o defeito 1 original), o VPL
    calculado com a taxa devolvida NAO fecharia perto de zero.
    """
    dates = pd.bdate_range("2024-01-15", "2024-07-25")
    prices = [100.0] * len(dates)  # preco parado — todo o movimento e fluxo
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * len(dates)),
    }
    strategy = _StubStrategy({})
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0, monthly_contribution=1_000.0)
    policy = FloorSkim(pct=0.05, floor=0.0, day=5, cap=1e12, min_amount=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool",
                                withdrawal_policy=policy)

    assert len(r.contributions) >= 1
    assert len(r.withdrawals) >= 1
    assert "irr" in r.metrics
    taxa = r.metrics["irr"]
    assert not math.isnan(taxa)

    t0 = r.equity_curve.index[0].date()
    fluxos = [(t0, -config.initial_capital)]
    fluxos += [(d, -v) for d, v in r.contributions]
    fluxos += [(w.date.date(), float(w.executed)) for w in r.withdrawals]
    fluxos.append((r.equity_curve.index[-1].date(), float(r.equity_curve.iloc[-1])))

    anos = [(d - t0).days / 365.25 for d, _ in fluxos]
    vpl = sum(v / ((1.0 + taxa) ** a) for (_, v), a in zip(fluxos, anos))
    assert vpl == pytest.approx(0.0, abs=1e-3)


# ---------------------------------------------------------------------------
# (9) taxa de liquidacao do saque continua sendo prejuizo da cota
# ---------------------------------------------------------------------------

def test_taxa_de_liquidacao_do_saque_derruba_a_cota_so_pelo_valor_da_taxa():
    """Um saque que forca liquidacao paga taxa de verdade (`fees_paid`). Essa
    taxa e custo REAL da estrategia e tem de continuar reduzindo a cota — mas
    so ela. Se a redencao de cotas usasse `executed` (ou `executed+fees`) em
    vez de isolar a taxa, o dono seria cobrado duas vezes pelo mesmo saque:
    uma vez perdendo cota pela taxa (correto) e de novo perdendo cota pelo
    dinheiro que ele proprio recebeu de volta (errado).
    """
    dates = pd.bdate_range("2024-01-02", periods=5)
    universe = {
        "TEST.SA": _panel(dates, [100.0] * 5),
        BENCHMARK: _panel(dates, [100_000.0] * 5),
    }
    strategy = _StubStrategy({dates[0]: [Enter(ticker="TEST.SA", size_hint=1.0)]})
    # Slippage ZERADA de proposito: isola o custo do saque na taxa EXPLICITA
    # (`fees_paid`), sem misturar com o efeito de preco da slippage — senao a
    # conta "a cota cai so pela taxa" teria uma segunda variavel escondida.
    costs = CostModel(brokerage_pct=0.001, exchange_fees_pct=0.0, slippage_pct=0.0)
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0, costs=costs)
    policy = FloorSkim(pct=0.5, floor=0.0, day=3, cap=1e12, min_amount=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool",
                                withdrawal_policy=policy)

    assert len(r.withdrawals) == 1
    w = r.withdrawals[0]
    assert w.fees_paid > 0.0, "saque tem de forcar liquidacao de verdade para o teste provar algo"

    idx = r.unit_curve.index.get_loc(w.date)
    assert idx > 0
    unit_antes = r.unit_curve.iloc[idx - 1]
    unit_depois = r.unit_curve.iloc[idx]

    razao_esperada = 1.0 - w.fees_paid / (w.equity_before - w.executed)
    razao_observada = unit_depois / unit_antes
    assert razao_observada == pytest.approx(razao_esperada, rel=1e-9)

    # Falsificacao: a cota NAO pode ter caido como se o valor sacado inteiro
    # fosse prejuizo.
    razao_se_contasse_o_saque_inteiro = 1.0 - w.executed / w.equity_before
    assert razao_observada != pytest.approx(razao_se_contasse_o_saque_inteiro, rel=1e-6)


# ---------------------------------------------------------------------------
# (10) saque sozinho, sem aporte nenhum, tambem ativa a contabilidade de cota
# ---------------------------------------------------------------------------

def test_saque_sozinho_sem_aporte_tambem_ativa_metricas_de_cota():
    """Se a cota so fosse corrigida quando ha aporte, um run com saque e SEM
    aporte devolveria `unit_curve` identica a `equity_curve` — o defeito 2
    continuaria vivo justamente no caso mais comum (so saque) — e as
    metricas `cagr_unit`/`max_drawdown_unit`/`irr` ficariam ausentes de um
    resultado que TEM fluxo de caixa de verdade. Fluxo e fluxo, nao importa o
    sentido (aporte ou saque).
    """
    dates = pd.bdate_range("2024-01-15", "2024-04-25")
    prices = [100.0] * len(dates)
    universe = {
        "TEST.SA": _panel(dates, prices),
        BENCHMARK: _panel(dates, [100_000.0] * len(dates)),
    }
    strategy = _StubStrategy({})
    config = BacktestConfig(initial_capital=100_000.0, max_concurrent_positions=1,
                             lot_size=1, stop_loss_pct=0.0)  # monthly_contribution=0.0 (default)
    policy = FloorSkim(pct=0.5, floor=0.0, day=3, cap=1e12, min_amount=0.0)

    r = run_portfolio_backtest(universe, strategy, config,
                                start=dates[0].strftime("%Y-%m-%d"),
                                end=dates[-1].strftime("%Y-%m-%d"),
                                satellite_pct=0.0, redist_mode="pool",
                                withdrawal_policy=policy)

    assert r.contributions == []
    assert len(r.withdrawals) >= 1
    for key in ("irr", "cagr_unit", "max_drawdown_unit"):
        assert key in r.metrics
    assert not r.unit_curve.equals(r.equity_curve)
