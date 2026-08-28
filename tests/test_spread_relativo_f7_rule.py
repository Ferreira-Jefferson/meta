"""Teste da mecanica de `scripts/daytrade/spread_relativo_f7_rule.py` com
cenario sintetico (AGENTS.md: toda regra de entrada/saida nova precisa de
teste com cenario sintetico). Nao e' um `IntradayStrategy` (o motor padrao e'
de 1 simbolo so'; um spread de 2 pernas simultaneas nao cabe nele -- ver
docstring do script), entao o teste chama as funcoes do script diretamente
em vez de `run_intraday_backtest`.

Cobre os pontos onde um bug silencioso invalidaria o VEREDITO do passo 2/3
(que e' negativo -- custo mata a regra): direcao correta do P&L bruto de
CADA perna, custo = tarifa fixa (2 pernas) + slippage de 4 fills, flatten
forcado no ultimo preco quando o dia acaba com posicao aberta, ausencia de
look-ahead no z-score (o nivel da PROPRIA barra nunca entra na janela que
computa a media/desvio usados para pontua-la), e a formula do nulo sign-flip
(regra 5: so' o BRUTO e' sorteado, o CUSTO nunca inverte de sinal -- e' o bug
exato que a missao pede para nao cometer)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "scripts" / "daytrade"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import spread_relativo_f7_rule as m  # noqa: E402


def _dia_constante(n: int, win: float = 100_000.0, wdo: float = 5_000.0) -> pd.DataFrame:
    """DataFrame de `n` barras com os 4 precos CONSTANTES -- ponto de
    partida que os testes sobrescrevem so' nos indices que importam."""
    return pd.DataFrame({
        "win_open": [win] * n, "win_close": [win] * n,
        "wdo_open": [wdo] * n, "wdo_close": [wdo] * n,
    })


# ------------------------- simular_dia: 1 trade fechado por reversao -------

def test_simular_dia_long_reverte_direcao_e_custo_das_2_pernas():
    """z bem negativo dispara LONG (aposta que o spread, hoje baixo, sobe de
    volta); z volta para dentro da banda de saida fecha o trade. Preco WIN
    sobe (lucro na perna long) e WDO cai (prejuizo na perna long) -- bruto
    tem que ser a SOMA assinada das duas pernas, nao so' uma delas."""
    n = 35
    dia = _dia_constante(n)
    dia.loc[31, "win_open"] = 100_000.0
    dia.loc[33, "win_open"] = 100_200.0  # +200 pts enquanto comprado -> lucro
    dia.loc[31, "wdo_open"] = 5_000.0
    dia.loc[33, "wdo_open"] = 4_995.0    # -5 pts enquanto comprado -> prejuizo

    z = np.full(n, np.nan)
    z[m.JANELA_Z] = -2.0       # < -entry_z (1.5) -> entra LONG no fechamento da barra 30
    z[m.JANELA_Z + 1] = -2.5   # ainda fora da banda de saida -> segura
    z[m.JANELA_Z + 2] = 0.1    # |z| < EXIT_Z (0.3) -> fecha

    trades = m.simular_dia(dia, z, entry_z=1.5, n_win=1, n_wdo=1)

    assert len(trades) == 1
    # bruto = 1*(100200-100000)*0.2 (WIN) + 1*(4995-5000)*10.0 (WDO) = 40 - 50 = -10
    assert trades[0]["bruto_brl"] == pytest.approx(-10.0)
    # custo = fee(0,5*2 contratos) + 2*(1 tick WIN=R$1 + 1 tick WDO=R$5) = 1 + 2*6 = 13
    assert trades[0]["custo_brl"] == pytest.approx(13.0)


def test_simular_dia_short_direcao_oposta_do_long():
    """Mesmo desenho do teste acima, so' que z cruza para CIMA do limiar
    (spread hoje alto, aposta que cai) -- o sinal do P&L bruto tem que
    inverter em relacao ao teste long para os MESMOS precos."""
    n = 35
    dia = _dia_constante(n)
    dia.loc[31, "win_open"] = 100_000.0
    dia.loc[33, "win_open"] = 100_200.0
    dia.loc[31, "wdo_open"] = 5_000.0
    dia.loc[33, "wdo_open"] = 4_995.0

    z = np.full(n, np.nan)
    z[m.JANELA_Z] = 2.0
    z[m.JANELA_Z + 1] = 2.5
    z[m.JANELA_Z + 2] = 0.1

    trades = m.simular_dia(dia, z, entry_z=1.5, n_win=1, n_wdo=1)

    assert len(trades) == 1
    # short: sinal=-1 -> bruto = -1*(200*0.2) + -1*(-5*10.0) = -40 + 50 = +10
    assert trades[0]["bruto_brl"] == pytest.approx(10.0)
    assert trades[0]["custo_brl"] == pytest.approx(13.0)


def test_simular_dia_nao_entra_abaixo_do_limiar():
    n = 35
    dia = _dia_constante(n)
    z = np.full(n, np.nan)
    z[m.JANELA_Z:] = 1.0  # nunca ultrapassa entry_z=1.5
    trades = m.simular_dia(dia, z, entry_z=1.5, n_win=1, n_wdo=1)
    assert trades == []


def test_simular_dia_flatten_forcado_no_fim_do_dia_usa_ultimo_fechamento():
    """Entra perto do fim do pregao e o dado acaba antes de reverter --
    tem que fechar no ULTIMO fechamento disponivel (nao ha barra seguinte
    para executar como as saidas normais fazem)."""
    n = m.JANELA_Z + 2  # so' 1 barra de dado depois do gatilho
    dia = _dia_constante(n)
    ultimo = n - 1
    dia.loc[ultimo, "win_open"] = 100_000.0
    dia.loc[ultimo, "win_close"] = 100_150.0  # +150 pts
    dia.loc[ultimo, "wdo_open"] = 5_000.0
    dia.loc[ultimo, "wdo_close"] = 5_010.0    # +10 pts

    z = np.full(n, np.nan)
    z[m.JANELA_Z] = -2.0  # entra long no ultimo indice processavel pelo loop

    trades = m.simular_dia(dia, z, entry_z=1.5, n_win=1, n_wdo=1)

    assert len(trades) == 1
    # bruto = 1*(100150-100000)*0.2 + 1*(5010-5000)*10.0 = 30 + 100 = 130
    assert trades[0]["bruto_brl"] == pytest.approx(130.0)
    assert trades[0]["custo_brl"] == pytest.approx(13.0)


# ------------------------- z-score: sem look-ahead --------------------------

def test_zscore_nao_olha_a_propria_barra_nem_o_futuro():
    """Mudar so' o ULTIMO fechamento do dia (que so' afeta o retorno/nivel do
    ULTIMO indice) nao pode mudar nenhum z ANTERIOR -- e' exatamente a
    garantia de "decide com o fechado, nunca com o que ainda nao existia"
    que o resto do repo ja aplica em granularidade de barra."""
    n = 40
    rng = np.random.default_rng(7)
    win_c = 100_000.0 * np.cumprod(1 + rng.normal(0, 0.001, n))
    wdo_c = 5_000.0 * np.cumprod(1 + rng.normal(0, 0.0005, n))
    dia1 = pd.DataFrame({"win_open": win_c, "win_close": win_c,
                          "wdo_open": wdo_c, "wdo_close": wdo_c})
    dia2 = dia1.copy()
    dia2.loc[n - 1, "win_close"] = dia2.loc[n - 1, "win_close"] * 1.05  # so' o ultimo fechamento

    _, z1 = m.nivel_e_z(dia1, a=0.0, b=0.0, janela=m.JANELA_Z)
    _, z2 = m.nivel_e_z(dia2, a=0.0, b=0.0, janela=m.JANELA_Z)

    # todo indice ANTERIOR ao ultimo tem que ser IDENTICO nas duas series
    np.testing.assert_array_equal(z1[:-1], z2[:-1])
    # o ultimo pode (e deve) mudar -- e' a barra que de fato mudou
    assert z1[-1] != z2[-1] or np.isnan(z1[-1])


# ------------------------- estimar_beta --------------------------------------

def test_estimar_beta_recupera_coeficiente_conhecido():
    """wdo_r sintetico + win_r = beta_verdadeiro * wdo_r (sem ruido) -- a OLS
    pooled tem que recuperar o coeficiente exato."""
    beta_verdadeiro = -0.8
    rng = np.random.default_rng(11)
    dias = {}
    for d in range(3):
        wdo_r = rng.normal(0, 0.002, 60)
        win_r = beta_verdadeiro * wdo_r
        wdo_c = 5_000.0 * np.concatenate([[1.0], np.cumprod(1 + wdo_r)])
        win_c = 100_000.0 * np.concatenate([[1.0], np.cumprod(1 + win_r)])
        dias[d] = pd.DataFrame({"win_open": win_c, "win_close": win_c,
                                 "wdo_open": wdo_c, "wdo_close": wdo_c})
    a, b = m.estimar_beta(dias, list(dias))
    assert b == pytest.approx(beta_verdadeiro, abs=1e-9)
    assert a == pytest.approx(0.0, abs=1e-12)


# ------------------------- nulo sign-flip: regra 5 ---------------------------

def test_nulo_sign_flip_so_inverte_o_bruto_nunca_o_custo():
    """Custo sempre positivo/subtraido, NUNCA sorteado -- e' o bug que a
    missao explicitamente probe (`s_d * liquido_d` inverteria o custo
    tambem, fazendo o nulo GANHAR a corretagem)."""
    bruto_d = np.array([0.0])
    custo_d = np.array([10.0])
    nulo = m.nulo_sign_flip(bruto_d, custo_d, n_sementes=200)
    assert np.all(nulo == -10.0)  # sempre -custo, nunca +custo


def test_nulo_sign_flip_flipa_o_bruto():
    bruto_d = np.array([100.0])
    custo_d = np.array([0.0])
    nulo = m.nulo_sign_flip(bruto_d, custo_d, n_sementes=200)
    assert set(np.unique(nulo)) == {100.0, -100.0}
    assert (nulo == 100.0).any() and (nulo == -100.0).any()
