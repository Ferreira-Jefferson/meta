"""Teste da mecanica de `scripts/daytrade/spread_relativo_f7_regime_horizonte.py`
(rodada 2 da Frente F7 -- cenario sintetico, AGENTS.md). Cobre os 2 pedacos
novos desta rodada que, se tivessem bug, invalidariam o veredito: (1) a saida
por HORIZONTE FIXO fecha exatamente na barra `entry_i+1+horizonte`, ignora
qualquer preco intermediario (ao contrario da saida por threshold da rodada
1) e faz flatten forcado quando o dia acaba antes do horizonte completar; (2)
o corte de regime de volatilidade e' calculado UMA VEZ (na 1a metade) e
aplicado como o MESMO numero em outro conjunto de dias, sem recalcular
localmente -- e' a garantia de "sem reajuste" que a missao exige."""
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

import spread_relativo_f7_rule as f7  # noqa: E402
import spread_relativo_f7_regime_horizonte as m  # noqa: E402


def _dia_constante(n: int, win: float = 100_000.0, wdo: float = 5_000.0) -> pd.DataFrame:
    return pd.DataFrame({
        "win_open": [win] * n, "win_close": [win] * n,
        "wdo_open": [wdo] * n, "wdo_close": [wdo] * n,
    })


# --------------------- simular_dia_horizonte: fecha no horizonte -------------

def test_simular_dia_horizonte_fecha_exatamente_no_horizonte_ignora_precos_intermediarios():
    """A saida tem que acontecer na barra `entry_i+1+horizonte` em ponto --
    um preco "armadilha" no meio do periodo de espera (que uma saida por
    threshold pegaria) NAO pode influenciar o bruto do trade."""
    horizonte = m.HORIZONTE_FIXO
    n = f7.JANELA_Z + horizonte + 5
    dia = _dia_constante(n)
    entry_i = f7.JANELA_Z
    dia.loc[entry_i + 1, "win_open"] = 100_000.0
    dia.loc[entry_i + 1, "wdo_open"] = 5_000.0
    saida_i = entry_i + 1 + horizonte
    dia.loc[saida_i, "win_open"] = 100_300.0  # +300 pts enquanto comprado -> lucro
    dia.loc[saida_i, "wdo_open"] = 4_990.0    # -10 pts enquanto comprado -> prejuizo
    # armadilha: se a funcao fechasse cedo por engano, pegaria este preco absurdo
    dia.loc[entry_i + 3, "win_open"] = 999_999.0
    dia.loc[entry_i + 3, "wdo_open"] = 1.0

    z = np.full(n, np.nan)
    z[entry_i] = -2.0  # < -entry_z -> dispara LONG no fechamento da barra de decisao

    trades = m.simular_dia_horizonte(dia, z, entry_z=1.5, n_win=1, n_wdo=1, horizonte=horizonte)

    assert len(trades) == 1
    bruto_esperado = (
        1 * (100_300.0 - 100_000.0) * f7.POINT_VALUE_BRL["WIN@"]
        + 1 * (4_990.0 - 5_000.0) * f7.POINT_VALUE_BRL["WDO@"]
    )
    assert trades[0]["bruto_brl"] == pytest.approx(bruto_esperado)
    # custo = fee(0,5*2 contratos) + 2*(1 tick WIN + 1 tick WDO) = 1 + 2*6 = 13
    assert trades[0]["custo_brl"] == pytest.approx(13.0)


def test_simular_dia_horizonte_short_direcao_oposta_do_long():
    horizonte = m.HORIZONTE_FIXO
    n = f7.JANELA_Z + horizonte + 5
    dia = _dia_constante(n)
    entry_i = f7.JANELA_Z
    dia.loc[entry_i + 1, "win_open"] = 100_000.0
    dia.loc[entry_i + 1, "wdo_open"] = 5_000.0
    saida_i = entry_i + 1 + horizonte
    dia.loc[saida_i, "win_open"] = 100_300.0
    dia.loc[saida_i, "wdo_open"] = 4_990.0

    z = np.full(n, np.nan)
    z[entry_i] = 2.0  # > entry_z -> SHORT

    trades = m.simular_dia_horizonte(dia, z, entry_z=1.5, n_win=1, n_wdo=1, horizonte=horizonte)

    assert len(trades) == 1
    bruto_long = (
        1 * (100_300.0 - 100_000.0) * f7.POINT_VALUE_BRL["WIN@"]
        + 1 * (4_990.0 - 5_000.0) * f7.POINT_VALUE_BRL["WDO@"]
    )
    assert trades[0]["bruto_brl"] == pytest.approx(-bruto_long)


def test_simular_dia_horizonte_nao_entra_abaixo_do_limiar():
    n = f7.JANELA_Z + m.HORIZONTE_FIXO + 5
    dia = _dia_constante(n)
    z = np.full(n, np.nan)
    z[f7.JANELA_Z:] = 1.0  # nunca ultrapassa entry_z=1.5
    trades = m.simular_dia_horizonte(dia, z, entry_z=1.5, n_win=1, n_wdo=1)
    assert trades == []


def test_simular_dia_horizonte_flatten_forcado_quando_faltam_barras():
    """Entra perto do fim do pregao com horizonte maior que o dado restante
    -- tem que fechar no ULTIMO fechamento disponivel, nao esperar o
    horizonte completar (que nunca vai acontecer)."""
    horizonte = 5
    n = f7.JANELA_Z + 3  # so' 2 barras de dado depois do gatilho -- nao cobre horizonte=5
    dia = _dia_constante(n)
    entry_i = f7.JANELA_Z
    dia.loc[entry_i + 1, "win_open"] = 100_000.0
    dia.loc[entry_i + 1, "wdo_open"] = 5_000.0
    dia.loc[n - 1, "win_close"] = 100_150.0
    dia.loc[n - 1, "wdo_close"] = 5_010.0

    z = np.full(n, np.nan)
    z[entry_i] = -2.0

    trades = m.simular_dia_horizonte(dia, z, entry_z=1.5, n_win=1, n_wdo=1, horizonte=horizonte)

    assert len(trades) == 1
    bruto_esperado = (
        1 * (100_150.0 - 100_000.0) * f7.POINT_VALUE_BRL["WIN@"]
        + 1 * (5_010.0 - 5_000.0) * f7.POINT_VALUE_BRL["WDO@"]
    )
    assert trades[0]["bruto_brl"] == pytest.approx(bruto_esperado)
    assert trades[0]["custo_brl"] == pytest.approx(13.0)


def test_simular_dia_horizonte_reabre_apos_fechar():
    """Depois de fechar por horizonte, um novo sinal mais adiante no mesmo
    dia tem que abrir um SEGUNDO trade independente."""
    horizonte = 5
    n = f7.JANELA_Z + 2 * (horizonte + 1) + 5
    dia = _dia_constante(n)
    entry1 = f7.JANELA_Z
    entry2 = entry1 + horizonte + 3  # depois que o 1o trade ja fechou

    z = np.full(n, np.nan)
    z[entry1] = -2.0
    z[entry2] = -2.0

    trades = m.simular_dia_horizonte(dia, z, entry_z=1.5, n_win=1, n_wdo=1, horizonte=horizonte)
    assert len(trades) == 2


# --------------------- vol_do_dia --------------------------------------------

def test_vol_do_dia_recupera_desvio_padrao_conhecido():
    """Com `wdo` constante (retorno=0) e a=b=0, o residuo e' EXATAMENTE o
    retorno do WIN -- o desvio calculado tem que bater com `np.std` direto
    sobre o retorno sintetico usado para construir os precos."""
    n = 10
    rng = np.random.default_rng(3)
    win_r = rng.normal(0, 0.001, n)
    win_c = 100_000.0 * np.concatenate([[1.0], np.cumprod(1 + win_r)])
    wdo_c = np.full(n + 1, 5_000.0)
    dia = pd.DataFrame({"win_open": win_c, "win_close": win_c,
                         "wdo_open": wdo_c, "wdo_close": wdo_c})
    v = m.vol_do_dia(dia, a=0.0, b=0.0)
    assert v == pytest.approx(np.std(win_r, ddof=1))


# --------------------- corte de regime: calculado uma vez, aplicado sem reajuste --

def test_corte_alto_terco_e_percentil_67():
    vols = {"d1": 1.0, "d2": 2.0, "d3": 3.0}
    corte = m.corte_alto_terco(vols)
    assert corte == pytest.approx(np.quantile([1.0, 2.0, 3.0], m.TERCO))


def test_dias_do_terco_alto_aplica_corte_importado_sem_recalcular():
    """O corte vem de UM conjunto (a 1a metade); o filtro so' compara contra
    esse numero fixo em OUTRO conjunto -- nunca recomputa o quantile la'
    dentro (prova indireta: o corte proprio de h2 e' DIFERENTE do corte de
    h1, e o resultado do filtro usa o de h1, nao o de h2)."""
    vols_h1 = {"d1": 1.0, "d2": 2.0, "d3": 3.0}
    corte_h1 = m.corte_alto_terco(vols_h1)

    vols_h2 = {"e1": 0.5, "e2": 10.0, "e3": 10.5, "e4": 0.1}
    corte_h2_proprio = m.corte_alto_terco(vols_h2)
    assert corte_h2_proprio != pytest.approx(corte_h1)

    dias_alto = m.dias_do_terco_alto(vols_h2, corte_h1)
    esperado = sorted(d for d, v in vols_h2.items() if v > corte_h1)
    assert dias_alto == esperado
    # com o corte de h1 (baixo, ~2.33), 2 dos 4 dias de h2 entram (10.0 e 10.5)
    assert dias_alto == ["e2", "e3"]


# --------------------- rodar_variante: filtro de dias permitidos -------------

def test_rodar_variante_filtro_vazio_zera_trades_e_filtro_completo_bate_sem_filtro():
    n = f7.JANELA_Z + m.HORIZONTE_FIXO + 5
    rng = np.random.default_rng(5)

    def dia_com_sinal() -> pd.DataFrame:
        win_c = 100_000.0 + np.cumsum(rng.normal(0, 0.5, n))
        wdo_c = 5_000.0 + np.cumsum(rng.normal(0, 0.05, n))
        d = pd.DataFrame({"win_open": win_c, "win_close": win_c,
                           "wdo_open": wdo_c, "wdo_close": wdo_c})
        # salto grande logo apos a janela do z-score -- garante sinal forte
        d.loc[f7.JANELA_Z:, "win_close"] = d.loc[f7.JANELA_Z:, "win_close"] + 5_000.0
        d.loc[f7.JANELA_Z:, "win_open"] = d.loc[f7.JANELA_Z:, "win_open"] + 5_000.0
        return d

    dias = {"d1": dia_com_sinal(), "d2": dia_com_sinal()}
    subset = list(dias)

    r_vazio, por_dia_vazio = m.rodar_variante(
        "threshold", "terco_alto_vol", dias, subset, set(), 0.0, 0.0, 0.5, 1, 1)
    assert por_dia_vazio == {}
    assert r_vazio["trades"] == 0

    r_todos_via_filtro, por_dia_todos_via_filtro = m.rodar_variante(
        "threshold", "terco_alto_vol", dias, subset, set(subset), 0.0, 0.0, 0.5, 1, 1)
    r_sem_filtro, por_dia_sem_filtro = m.rodar_variante(
        "threshold", "todos_os_dias", dias, subset, None, 0.0, 0.0, 0.5, 1, 1)

    assert por_dia_todos_via_filtro.keys() == por_dia_sem_filtro.keys()
    assert r_todos_via_filtro["trades"] == r_sem_filtro["trades"]
    assert r_todos_via_filtro["trades"] > 0  # sanity: o desenho do dia gera sinal de verdade


def test_rodar_variante_filtro_parcial_so_usa_os_dias_permitidos():
    n = f7.JANELA_Z + m.HORIZONTE_FIXO + 5
    rng = np.random.default_rng(9)

    def dia_com_sinal() -> pd.DataFrame:
        win_c = 100_000.0 + np.cumsum(rng.normal(0, 0.5, n))
        wdo_c = 5_000.0 + np.cumsum(rng.normal(0, 0.05, n))
        d = pd.DataFrame({"win_open": win_c, "win_close": win_c,
                           "wdo_open": wdo_c, "wdo_close": wdo_c})
        d.loc[f7.JANELA_Z:, "win_close"] = d.loc[f7.JANELA_Z:, "win_close"] + 5_000.0
        d.loc[f7.JANELA_Z:, "win_open"] = d.loc[f7.JANELA_Z:, "win_open"] + 5_000.0
        return d

    dias = {"d1": dia_com_sinal(), "d2": dia_com_sinal(), "d3": dia_com_sinal()}
    subset = list(dias)

    r_parcial, por_dia_parcial = m.rodar_variante(
        "threshold", "terco_alto_vol", dias, subset, {"d2"}, 0.0, 0.0, 0.5, 1, 1)
    assert set(por_dia_parcial.keys()) <= {"d2"}
    assert r_parcial["trades"] > 0  # d2 sozinho ja tem sinal
