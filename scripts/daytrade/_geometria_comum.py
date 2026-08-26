"""Peca comum aos scripts da rodada de GEOMETRIA EM TICKS (2026-08-26):
`snapshot_baseline.py`, `mapa_geometria.py` e
`sweep_gremah_ticks_independentes.py`.

Existe por dois motivos concretos, os dois aprendidos neste repo:

1. `REGIME_START` ja estava copiado em TRES scripts (`run_backtest_ticks.py`,
   `sweep_gremah_tick.py`, `sweep_gremah_vol.py`) -- conferi em 2026-08-26 que
   os tres estao identicos hoje, mas uma quarta e uma quinta copia e' como
   comeca a divergencia silenciosa. Os scripts novos leem daqui.

2. `symbol_economics` fala com o TERMINAL MT5, e o terminal e' o mesmo que o
   robo de dinheiro real usa. Oito processos de sweep abrindo conexao ao mesmo
   tempo e' carga que a operacao nao precisa levar. Pior: o valor lido do
   terminal pode MUDAR entre duas rodadas, e a rodada "antes"/"depois" do
   snapshot de compatibilidade so' vale se as duas usarem exatamente o mesmo
   numero -- senao o diff acusa diferenca que nao veio da mudanca de codigo.
   Por isso `carregar_economics` le' UMA vez, no processo pai, e grava um
   cache JSON que as rodadas seguintes reusam.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import PROFILES  # noqa: E402
from market_data_intraday.mt5_source import symbol_economics  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402
from market_data_intraday.tick_storage import load_ticks  # noqa: E402
from strategy.daytrade.lab.gremah import _CALIBRATION_BY_SYMBOL, Gremah  # noqa: E402
from strategy.daytrade.lab.gremah_tick import _CALIBRATION_BY_SYMBOL_TICK, GremahTick  # noqa: E402

#: A partir de quando o preco do ativo deixou de ser outro patamar. Propriedade
#: do ATIVO, nao da fonte de dado -- a mesma data vale em M1 e em tick.
REGIME_START = {
    "PMAM3": "2025-12-16", "KLBN4": "2025-09-02", "CSAN3": "2025-09-22",
    "DASA3": "2025-09-11", "PCAR3": "2025-08-21", "CLSC4": "2025-05-12",
    "KLBN3": "2025-03-10", "GRND3": "2025-09-05", "LPSB3": "2022-12-20",
    "BMGB4": "2025-06-04",
}

#: Os dois motores da familia, pela chave curta usada na linha de comando.
#: `Gremah` le' barra de 1 minuto; `GremahTick` le' negocio a negocio.
MOTORES = ("m1", "tick")

SIMBOLOS = tuple(sorted(_CALIBRATION_BY_SYMBOL))


def classe_do_motor(motor: str):
    if motor == "m1":
        return Gremah
    if motor == "tick":
        return GremahTick
    raise ValueError(f"motor desconhecido: {motor!r} (esperado: {MOTORES})")


def calibracao_do_motor(motor: str):
    return _CALIBRATION_BY_SYMBOL if motor == "m1" else _CALIBRATION_BY_SYMBOL_TICK


@dataclass(frozen=True)
class Economics:
    """So' os dois numeros que `config_for` precisa, ja destacados do objeto do
    MT5 para poderem atravessar um `ProcessPoolExecutor` e um arquivo JSON."""

    trade_tick_value: float
    trade_tick_size: float


def carregar_economics(symbols, cache_path: Path) -> dict[str, Economics]:
    """Le' do cache se existir; senao pergunta ao terminal UMA vez e grava.

    Apagar o arquivo de cache forca reler o terminal -- e invalida qualquer
    comparacao com um snapshot gerado antes disso."""
    cache_path = Path(cache_path)
    fora: dict[str, Economics] = {}
    if cache_path.exists():
        cru = json.loads(cache_path.read_text(encoding="utf-8"))
        fora = {s: Economics(**v) for s, v in cru.items()}

    # O cache pode ter sido gravado por uma rodada de UM simbolo so'. Completar
    # o que falta (em vez de devolver o arquivo inteiro como se fosse completo)
    # e' o que impede um `KeyError` na primeira rodada de 10 depois de um teste
    # de fumaca com `--symbol`. Simbolo ja cacheado NUNCA e' relido: o valor
    # velho e' justamente o que faz "antes" e "depois" comparaveis.
    faltando = [s for s in symbols if s not in fora]
    if not faltando:
        return fora

    for symbol in faltando:
        econ = symbol_economics(symbol)
        if econ is None:
            raise RuntimeError(
                f"symbol_economics devolveu None para {symbol!r} -- terminal MT5 aberto? "
                "Nenhum snapshot foi gravado; nada foi alterado."
            )
        fora[symbol] = Economics(float(econ.trade_tick_value), float(econ.trade_tick_size))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({s: {"trade_tick_value": e.trade_tick_value,
                        "trade_tick_size": e.trade_tick_size}
                    for s, e in sorted(fora.items())}, indent=2),
        encoding="utf-8",
    )
    return fora


def carregar_is(symbol: str, motor: str, tail: int | None = None):
    """Barras IN-SAMPLE do simbolo no motor pedido, ja cortadas no regime de
    preco e no split congelado. NUNCA chama `unlock()` -- o OOS nao passa por
    aqui.

    Devolve `(run_bars, profile, preco_referencia)`. `run_bars` vazio significa
    'sem dado local para este par', e quem chama reporta em vez de quebrar."""
    profile = PROFILES[symbol]
    if motor == "m1":
        bars = load_m1(symbol)
    else:
        ticks = load_ticks(symbol)
        bars = ticks_to_degenerate_bars(ticks) if not ticks.empty else pd.DataFrame()
    if bars.empty:
        return pd.DataFrame(), profile, 0.0

    regime_start = pd.Timestamp(REGIME_START[symbol], tz="UTC")
    bars = bars.loc[bars.index >= regime_start]
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    run_bars = LockedBars(bars, split).in_sample()
    if tail is not None and len(run_bars) > tail:
        # Corte de TEMPO, nao de escopo: ainda dentro do IS declarado, so' os
        # ultimos N registros antes do corte OOS. Mesmo mecanismo de
        # `sweep_gremah_tick.py --tail-ticks`, pelo mesmo motivo (simbolo com
        # volume de tick alto demais pra rodada inteira caber em tempo util).
        run_bars = run_bars.tail(tail)
    if run_bars.empty:
        return run_bars, profile, 0.0
    return run_bars, profile, float(run_bars.iloc[0]["close"])
