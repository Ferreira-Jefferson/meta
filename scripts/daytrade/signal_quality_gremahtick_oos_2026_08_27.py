"""CONFIRMACAO OOS -- os DOIS filtros de qualidade de sinal da `GremahTick`
(PMAM3, motor tick) validados HOJE so' no IS
(`signal_quality_gremahtick_2026_08_27.py`): `volume_toque<=400,0` e
`distancia_sma20_ticks>=0,70` (ambos sobreviveram ao gate de split-half
IS-metade1/IS-metade2). Pergunta desta etapa: a DIRECAO do efeito se mantem
fora do IS?

## Metodo -- limiar FIXO, sem recalibrar (isto NAO e' um novo split-half)

Os dois limiares (400,0 e 0,70) ja' foram ESCOLHIDOS hoje na metade1
cronologica do IS e confirmados na metade2 -- esta etapa nao reabre aquela
escolha. Aqui o limiar FIXO e' aplicado direto a TODOS os trades do OOS
(nenhuma recalibracao), e o que se mede e':

  1. correlacao (feature, pnl_brl do trade) nos trades do OOS -- mesmo sinal
     do IS (pool)? (`testa_proxy`, reusado sem alteracao);
  2. efeito liquido do corte de limiar fixo: trades mantidos/descartados,
     P&L com/sem filtro, MaxDD com/sem filtro, win rate com/sem filtro.

## Reuso -- NADA do nucleo estatistico e' reescrito

Importa (nao reescreve) de `signal_quality_gremahtick_2026_08_27.py`:
`casa_trades_com_ticks`, `posicoes_inicio_sessao`, `computa_features`,
`testa_proxy`, `imprime_correlacao`, `EfeitoFiltro`, `imprime_filtro`
(a UNICA peca nova e' `aplica_filtro_fixo`, abaixo -- versao de
`simula_filtro` que usa um limiar JA DADO em vez de recalibrar na metade1;
todo o resto -- P&L, MaxDD, win rate -- e' calculado com a MESMA formula).

Importa (nao reescreve) de `capital_ladder_gremahtick_oos_2026_08_27.py`
(mesma sessao, mesmo dia): `carregar_is_oos_combinado` + `MOTIVO_UNLOCK` --
o MESMO destrave de OOS, pelo MESMO motivo, chamado UMA vez (nao duplica a
autorizacao do dono em dois arquivos com textos diferentes).

Entrada de dado: `scratch/scripts/capital_ladder_gremahtick_pmam3_oos_n1_
trades_2026_08_27.csv` (881 trades, N=1 lote fixo, OOS-only, gerado por
`capital_ladder_gremahtick_oos_2026_08_27.py`).

Janela: OOS-only (o mesmo trecho destravado pelo script de capital, MESMA
autorizacao do dono -- nao chama `unlock()` de novo com outro motivo).

Uso:
    python -u scripts/daytrade/signal_quality_gremahtick_oos_2026_08_27.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.report import maxdd_brl, num_br  # noqa: E402

from _geometria_comum import carregar_economics  # noqa: E402

# reuso literal (import, nao reescrita) dos scripts de HOJE
import signal_quality_gremahtick_2026_08_27 as SQ27  # noqa: E402
from capital_ladder_gremahtick_oos_2026_08_27 import (  # noqa: E402
    MOTIVO_UNLOCK, SYMBOL, carregar_is_oos_combinado,
)

CSV_TRADE_LOG_OOS_N1 = ROOT / "scratch" / "scripts" / "capital_ladder_gremahtick_pmam3_oos_n1_trades_2026_08_27.csv"

SCRATCH_DIR = ROOT / "scratch" / "scripts"
CSV_FEATURES_OOS = SCRATCH_DIR / "signal_quality_gremahtick_oos_features_2026_08_27.csv"
CSV_FILTRO_OOS = SCRATCH_DIR / "signal_quality_gremahtick_oos_filtro_efeito_2026_08_27.csv"

#: os DOIS filtros validados HOJE no IS (`signal_quality_gremahtick_filtro_
#: efeito_2026_08_27.csv`) -- limiar aprendido na metade1 do IS, confirmado
#: na metade2 do IS. Aqui SO' aplicados (nao recalibrados) contra o OOS.
#: (nome, direcao, limiar, corr_pool_IS -- para conferir o sinal esperado)
FILTROS_VALIDADOS_NO_IS = (
    ("volume_toque", "<=", 400.0, -0.14513981151349933),
    ("distancia_sma20_ticks", ">=", 0.7000000000000117, 0.14877821219233364),
)


# ---------------------------------------------------------------------------
# adaptacao de `SQ27.simula_filtro`: aqui o limiar e' FIXO (ja aprendido no
# IS), aplicado a TODOS os trades da janela nova (sem recalibrar em metade
# nenhuma). Mesmas formulas de P&L/MaxDD/win-rate de `SQ27.EfeitoFiltro`.
# ---------------------------------------------------------------------------

def aplica_filtro_fixo(nome: str, x: np.ndarray, y: np.ndarray, direcao: str, limiar: float) -> "SQ27.EfeitoFiltro":
    mask = (x <= limiar) if direcao == "<=" else (x >= limiar)
    curva_sem = pd.Series(np.concatenate([[0.0], np.cumsum(y)]))
    curva_com = pd.Series(np.concatenate([[0.0], np.cumsum(y[mask])]))
    n_mantidos = int(mask.sum())
    return SQ27.EfeitoFiltro(
        nome=nome, direcao=direcao, limiar=limiar,
        n_metade2=len(y), n_mantidos=n_mantidos, n_descartados=int((~mask).sum()),
        pnl_sem_filtro=float(y.sum()), pnl_com_filtro=float(y[mask].sum()),
        pnl_por_trade_sem_filtro=float(y.mean()) if len(y) else 0.0,
        pnl_por_trade_com_filtro=float(y[mask].mean()) if n_mantidos else 0.0,
        maxdd_sem_filtro=maxdd_brl(curva_sem), maxdd_com_filtro=maxdd_brl(curva_com),
        win_rate_sem_filtro=float((y > 0).mean()) if len(y) else 0.0,
        win_rate_com_filtro=float((y[mask] > 0).mean()) if n_mantidos else 0.0,
    )


def main() -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CSV_TRADE_LOG_OOS_N1)
    # `format="ISO8601"`: ao contrario do trade log do IS, o log OOS mistura
    # timestamps com e sem microssegundos (alguns toques caem exatamente no
    # segundo cheio) -- o parser de formato UNICO do pandas rejeitaria a
    # mistura; ISO8601 aceita as duas variantes sem perder precisao nenhuma.
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True, format="ISO8601")
    assert df["entry_ts"].is_monotonic_increasing, "trade log OOS nao esta em ordem cronologica"
    print(f"[signal_quality_oos] trade log OOS-only: {CSV_TRADE_LOG_OOS_N1} -- {len(df)} trades, "
          f"{df['entry_ts'].min()} -> {df['entry_ts'].max()}")

    # MESMO destrave de OOS do script de capital (mesma autorizacao do dono,
    # motivo identico) -- so' precisamos das barras OOS-only para casar os
    # trades com o tick de toque e computar as features.
    _is_bars, oos_bars, _combinado, _profile = carregar_is_oos_combinado(SYMBOL, "tick", MOTIVO_UNLOCK)
    print(f"[signal_quality_oos] OOS bars: {len(oos_bars)} ticks, "
          f"{oos_bars.index.min()} -> {oos_bars.index.max()}")

    economics = carregar_economics([SYMBOL], ROOT / "data" / "_economics_cache.json")[SYMBOL]
    tick_size = economics.trade_tick_size
    print(f"[signal_quality_oos] tick_size {SYMBOL} = {tick_size}")

    feats, sem_match = SQ27.computa_features(df, oos_bars, tick_size)
    n_matched = int(sum(feats.validos["minutos_desde_abertura"]))
    print(f"[signal_quality_oos] casamento trade -> tick de toque: {n_matched}/{len(df)} "
          f"({sem_match} sem match -- deveria ser 0)")

    print(f"\n=== {SYMBOL} motor=tick OOS-only -- correlacao (feature, pnl_brl), "
          f"limiares JA APRENDIDOS no IS, so' APLICADOS aqui (sem recalibrar) ===")

    linhas_features = []
    linhas_filtro = []
    for nome, direcao, limiar, corr_pool_is in FILTROS_VALIDADOS_NO_IS:
        mask = feats.validos[nome]
        x = feats.valores[nome][mask]
        y = feats.pnl_brl[mask]
        n_validos = int(mask.sum())
        print(f"\n[{nome}] {n_validos}/{len(df)} trades OOS com janela valida "
              f"(IS: limiar {direcao} {num_br(limiar, 4)}, corr_pool_IS={num_br(corr_pool_is, 4)})")
        if n_validos < 30:
            print("  MENOS DE 30 trades validos no OOS -- resultado abaixo e' de baixa potencia estatistica.")

        r = SQ27.testa_proxy(nome, x, y, seed=0)
        SQ27.imprime_correlacao(r)
        mesmo_sinal_pool = (r.corr_real > 0) == (corr_pool_is > 0)
        print(f"  correlacao no OOS tem o MESMO SINAL da correlacao no IS (pool)? {mesmo_sinal_pool}")
        linhas_features.append(dict(
            feature=nome, n_oos=r.n, corr_oos=r.corr_real, p_oos=r.p_two_sided,
            corr_pool_is=corr_pool_is, mesmo_sinal_is_oos=mesmo_sinal_pool,
            diff_tercil_oos_brl=r.diff_tercil, p_diff_tercil_oos=r.diff_tercil_p,
        ))

        ef = aplica_filtro_fixo(nome, x, y, direcao, limiar)
        SQ27.imprime_filtro(ef)
        efeito_liquido_positivo = ef.pnl_por_trade_com_filtro > ef.pnl_por_trade_sem_filtro
        print(f"  filtro melhora P&L POR TRADE no OOS (mesma direcao do efeito visto no IS)? "
              f"{efeito_liquido_positivo}")
        linhas_filtro.append(dict(
            feature=ef.nome, direcao=ef.direcao, limiar=ef.limiar,
            n_oos=ef.n_metade2, n_mantidos=ef.n_mantidos, n_descartados=ef.n_descartados,
            pnl_sem_filtro_brl=ef.pnl_sem_filtro, pnl_com_filtro_brl=ef.pnl_com_filtro,
            pnl_por_trade_sem_filtro_brl=ef.pnl_por_trade_sem_filtro,
            pnl_por_trade_com_filtro_brl=ef.pnl_por_trade_com_filtro,
            maxdd_sem_filtro_brl=ef.maxdd_sem_filtro, maxdd_com_filtro_brl=ef.maxdd_com_filtro,
            win_rate_sem_filtro_pct=ef.win_rate_sem_filtro * 100, win_rate_com_filtro_pct=ef.win_rate_com_filtro * 100,
            efeito_pnl_por_trade_positivo=efeito_liquido_positivo,
        ))

    pd.DataFrame(linhas_features).to_csv(CSV_FEATURES_OOS, index=False)
    pd.DataFrame(linhas_filtro).to_csv(CSV_FILTRO_OOS, index=False)
    print(f"\n[signal_quality_oos] features (OOS) salvas em {CSV_FEATURES_OOS}")
    print(f"[signal_quality_oos] efeito do(s) filtro(s) (OOS) salvo em {CSV_FILTRO_OOS}")

    print(f"\n\n=== {SYMBOL} motor=tick -- VEREDITO OOS (direcao do efeito se mantem?) ===")
    cab = f"{'feature':<24}{'sinal IS':>10}{'sinal OOS':>11}{'mantem?':>9}{'P&L/trade melhora?':>20}"
    print(cab)
    print("-" * len(cab))
    for lf, ef in zip(linhas_features, linhas_filtro):
        sinal_is = "+" if lf["corr_pool_is"] > 0 else "-"
        sinal_oos = "+" if lf["corr_oos"] > 0 else "-"
        print(f"{lf['feature']:<24}{sinal_is:>10}{sinal_oos:>11}{str(lf['mesmo_sinal_is_oos']):>9}"
              f"{str(ef['efeito_pnl_por_trade_positivo']):>20}")


if __name__ == "__main__":
    main()
