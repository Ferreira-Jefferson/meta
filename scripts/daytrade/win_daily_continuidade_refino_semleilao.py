"""REFEITO 2026-10-06 sem os leiloes (auditoria A2) -- o refino da continuidade diaria
`continuidade_diaria_reversal` em WIN, com SINAL e SAIDA no continuo.

Defeito do original (`win_daily_continuidade_refino_rodada2.py` e a regra de
`continuidade_daily_rule.py`): base `WIN@` UTC (parquet `WIN_A_`), sinal =
close[D-1]-close[D-2] onde o close da ultima barra e' o CALL, e 100% das saidas
no close da ultima barra (21:24 UTC = call).

Aqui: a base e' `WIN$N` (preco NAO ajustado; a memoria diz que `WIN@` M1 e' AJUSTADO)
passada por `carrega_win_m1_sem_leiloes` (close da ultima barra = ultimo negocio
continuo, volume sem leilao/call), deslocada +3h para o relogio UTC que o perfil
`WIN@` do motor espera. Nao altera machine.py/profiles.py/nenhum arquivo antigo: reaproveita
as funcoes do original trocando `carregar_is_bars` (e, na variante `corte`, o
`session_end_time` da config no proprio script).

Nota: o perfil `WIN@` ATUAL ja' tem `flatten_cut_time` 21:20 UTC (folga de 5 min), entao o motor de hoje,
sobre a base original, ja' NAO zera mais no call. O numero publicado (+R$8.832,30) vem do motor antigo
(corte 21:25 = ultima barra = call). Por isso quatro modos:

Uso: python win_daily_continuidade_refino_semleilao.py {antes_velho|antes|continuo|corte}
  antes_velho = base original (WIN_A_) com corte 21:25 forcado: reproduz o motor antigo (saida no call)
  antes       = base original (WIN_A_) com o perfil atual (corte 21:20 UTC = 18:20 BRT)
  continuo    = WIN$N sem leiloes, corte 21:25 forcado: zera na ULTIMA BARRA CONTINUA (close = ultimo negocio continuo)
  corte       = WIN$N sem leiloes, perfil atual (zera 18:20 BRT, antes do fim do pregao)
"""
from __future__ import annotations

import dataclasses
import sys
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(Path(__file__).resolve().parent)]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import continuidade_daily_rule as rule  # noqa: E402
import win_daily_continuidade_refino_rodada2 as r2  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, num_br, tabela  # noqa: E402
from market_data_intraday.win_sem_leiloes import carrega_win_m1_sem_leiloes  # noqa: E402

MODO = sys.argv[1] if len(sys.argv) > 1 else "continuo"
SYMBOL = "WIN@"
_orig_carregar = r2.carregar_is_bars
_orig_config = rule._config
CAPTURA: dict = {}


def carregar_semleilao(symbol: str) -> pd.DataFrame:
    perfil = profile_for(symbol)
    split = declare_frozen_split(cutoff=perfil.frozen_cutoff, note=perfil.frozen_note)
    r = carrega_win_m1_sem_leiloes("m1_WIN$N.parquet", "2025-12-01", "2026-12-31", "M1")
    b = r.barras[["open", "high", "low", "close", "tick_volume", "real_volume"]].copy()
    b["spread"] = 0
    b.index = (b.index + pd.Timedelta(hours=3)).tz_localize("UTC")
    isb = LockedBars(b, split).in_sample()
    cont = isb.groupby(isb.index.date).size()
    ok = set(cont[cont >= 400].index)
    isb = isb[[d in ok for d in isb.index.date]]
    CAPTURA["proxy_dias"] = int(r.dias.loc[r.dias.index.isin(pd.DatetimeIndex(sorted(ok)))]["proxy"].sum())
    return isb


def config_ate_ultima_barra(symbol: str):
    """Sem corte antes do fim: zera so' na ultima barra do dia (motor antigo / ultima barra continua)."""
    cfg = _orig_config(symbol)
    return dataclasses.replace(cfg, session_end_time=time(21, 25))


def rodar_capturando(symbol, bars, direction):
    res = _orig_rodar(symbol, bars, direction)
    CAPTURA.setdefault("bars", bars)
    CAPTURA.setdefault("res", res)
    return res


_orig_rodar = rule.rodar
if MODO in ("continuo", "corte"):
    r2.carregar_is_bars = carregar_semleilao
if MODO in ("antes_velho", "continuo"):
    rule._config = config_ate_ultima_barra
    r2._config = config_ate_ultima_barra
rule.rodar = rodar_capturando
r2.rodar = rodar_capturando


def saidas_no_call(res, bars) -> str:
    """Conta saidas na ultima barra do dia (= call na base original; = ultimo negocio continuo na nova)."""
    ult = bars.groupby(bars.index.date).apply(lambda g: g.index[-1])
    ult_ts = set(pd.Timestamp(x).tz_localize(None) if pd.Timestamp(x).tzinfo else pd.Timestamp(x) for x in ult)
    n = tot = 0
    for t in res.trades:
        e = pd.Timestamp(t.exit_ts)
        e = e.tz_localize(None) if e.tzinfo else e
        tot += 1
        n += e in ult_ts
    hist = pd.Series([pd.Timestamp(t.exit_ts).strftime("%H:%M") for t in res.trades]).value_counts().head(4).to_dict()
    return f"{n}/{tot} saidas na ultima barra do dia ({n / tot * 100:.1f}%); horas de saida mais comuns (UTC) {hist}"


def extra_baseline() -> None:
    bars, res = CAPTURA["bars"], CAPTURA["res"]
    print(f"\n### MODO={MODO}  proxy(dias sem fases)={CAPTURA.get('proxy_dias', 'n/a')}")
    print("### baseline:", saidas_no_call(res, bars))
    h1, h2 = rule._metade(bars, 1), rule._metade(bars, 2)
    l1 = linha_de_resultado("metade 1", rule.rodar(SYMBOL, h1, "reversal"), rule.CAPITAL_NOCIONAL, capital_nocional=True)
    l2 = linha_de_resultado("metade 2", rule.rodar(SYMBOL, h2, "reversal"), rule.CAPITAL_NOCIONAL, capital_nocional=True)
    print(tabela([l1, l2]))
    liq, pct = rule.nulo_sign_flip(res)
    print(f"### baseline nulo sign-flip: liquido {num_br(liq)} percentis {[round(p, 2) for p in pct]} media={np.mean(pct):.2f}%")


if __name__ == "__main__":
    import atexit
    atexit.register(lambda: None)
    try:
        r2.main()
    finally:
        pass
    extra_baseline()
