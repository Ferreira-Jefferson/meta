"""Roda `WdoGridReloadMaker` (config de producao) numa unica passada CONTINUA
sobre TODO o historico M1 salvo de WDO@ (2025-12-08 -> 2026-08-28, ~8,5
meses), com capital REAL (nao nocional) -- pergunta direta do dono depois do
incidente de 2026-08-28 (`LICOES_DE_PRODUCAO.md` Parte 0): "em algum dia o
capital e' zerado?"

Usa `config_for(profile_for("WDO@"), ...)` SEM passar `max_open_contracts`
nem `enforce_capital_cap` -- e' o MESMO caminho que `scripts/run_live.py::
build_intraday` usa pra montar a config real (ver a docstring de
`config_for`), entao isto testa exatamente a PROTECAO que existe em producao
hoje (teto dinamico por caixa, `contracts_from_capital_com_reserva` com
`RESERVA_CAIXA_SEGURANCA=1.25` ja aplicada), nao uma config de laboratorio
a parte.

`run_intraday_backtest` para' sozinho na primeira barra em que
`equity <= 0` (`wiped_out_at`) -- rodar o historico INTEIRO numa passada so'
(nao dia a dia) e' o que deixa essa checagem valer de verdade: se parasse e
reiniciasse o caixa a cada dia, nunca veria uma sequencia de perdas
ATRAVESSAR dias, que e' exatamente como uma conta real funciona.

4 niveis de capital testados, todos justificados (nenhum arbitrario):
  - R$300  = minimo real da tabela do CLAUDE.md (margem WDO x2 lotes),
             o que a conta tinha no dia do incidente.
  - R$375  = limiar exato citado na mesma tabela pra abrir 1 contrato JA
             com a reserva de seguranca (R$300 fica inerte por design).
  - R$3.000 = capital com folga (varios contratos possiveis), pra separar
             "trava por caixa" de "trava por perda de verdade".
  - R$5.000 = MEDIDO (2026-08-29, ver a nota de reversao no topo do modulo
             `strategy/daytrade/lab/wdo_grid_reload_maker.py`) como o piso
             real pra T1/S16 (o default de producao apos a reversao)
             sobreviver ao historico INTEIRO sem travar -- abaixo disso
             (inclusive os R$3.000 acima) ainda trava.

Uso: `python scripts/daytrade/wdof1_stress_capital_real_historico_completo.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

SYMBOL = "WDO@"
_ECONOMIA_WDO = (0.01, 0.001)
NIVEIS_CAPITAL = [300.0, 375.0, 3_000.0, 5_000.0]
MIN_BARRAS_POR_PREGAO = 400


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def carregar_bars() -> pd.DataFrame:
    df = load_m1(SYMBOL).sort_index()
    if df.empty:
        raise SystemExit(f"sem dado M1 salvo para {SYMBOL!r}.")
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    incompletos = sorted(set(contagem.index) - completos)
    if incompletos:
        print(f"[aviso] {len(incompletos)} pregao(oes) incompleto(s) descartado(s) "
              f"(< {MIN_BARRAS_POR_PREGAO} barras): {incompletos}")
    return df[[d in completos for d in df.index.date]]


def montar_cfg(capital: float):
    profile = profile_for(SYMBOL)
    trade_tick_value, trade_tick_size = _ECONOMIA_WDO
    # SEM max_open_contracts/enforce_capital_cap explicitos -- mesmo caminho
    # de `scripts/run_live.py::build_intraday` (config REAL de producao).
    return config_for(
        profile,
        trade_tick_value=trade_tick_value, trade_tick_size=trade_tick_size,
        initial_capital=capital,
        target_fills_as_maker=True,
        limit_fill_capped_by_volume=True,
    )


def main() -> None:
    bars = carregar_bars()
    dias = sorted(set(bars.index.date))
    print(f"[wdof1_stress] {SYMBOL}: {len(bars):,} barras M1, {len(dias)} pregoes completos, "
          f"{dias[0]} -> {dias[-1]}\n")

    for capital in NIVEIS_CAPITAL:
        strat = get_daytrade_robot("wdo_grid_reload_maker")
        cfg = montar_cfg(capital)
        print(f"=== capital inicial R${br(capital)} (max_open_contracts oficial do perfil = "
              f"{profile_for(SYMBOL).max_open_contracts}, teto dinamico por caixa ATIVO) ===")
        resultado = run_intraday_backtest(bars, strat, cfg)

        liquido = sum(t.pnl_brl for t in resultado.trades)
        pregoes_cobertos = len(set(pd.DatetimeIndex(resultado.equity_curve.index).date))
        equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else capital

        print(f"pregoes cobertos ate parar (ou ate o fim): {pregoes_cobertos}/{len(dias)}")
        print(f"trades: {len(resultado.trades)} | recusados por teto: {resultado.ordens_recusadas_por_teto} "
              f"| aceitos: {resultado.ordens_aceitas}")
        print(f"liquido acumulado: R${br(liquido)} | equity final: R${br(equity_final)}")
        if resultado.wiped_out_at is not None:
            print(f"*** ZERADO em {resultado.wiped_out_at} *** "
                  f"(equity <= 0 -- backtest interrompido nesse ponto, dias seguintes NAO rodados)")
        else:
            print("nunca zerou no historico inteiro.")
        if resultado.sessoes_puladas_por_capital:
            print(f"pregoes pulados de saida por capital insuficiente na abertura: "
                  f"{len(resultado.sessoes_puladas_por_capital)}")
        print()


if __name__ == "__main__":
    main()
