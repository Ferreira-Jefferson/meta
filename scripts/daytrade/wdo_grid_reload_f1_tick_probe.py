"""Frente F1-wdo-consolidacao, RODADA 3 -- teste de resolucao tick (proximo
passo prescrito pelo critico da rodada 2: a hipotese mecanica de que M1 SUB-
CONTA toques/recargas porque `WdoGridReloadMaker.on_bar` so' reagenda apos
ficar flat, permitindo no maximo 1 fill-check por barra M1 por nivel,
enquanto em tick o MESMO nivel pode preencher-fechar-rearmar varias vezes
dentro do que seria 1 minuto).

VIABILIDADE (checada ANTES de escrever este arquivo, ver o relato da
rodada): o terminal MT5 (Rico) so' guarda tick a tick de WDO@ a partir de
2026-02-27 -- NAO cobre a janela IS inteira (2025-12-09..2026-06-12, 123
pregoes). Cobertura real: 72 dos 123 pregoes IS (58,5%), faltando os 51
primeiros pregoes (2025-12-09..2026-02-26). Isto e' um teste de VIABILIDADE
MECANICA sobre o SUBCONJUNTO disponivel -- NUNCA um substituto do numero IS
completo. Comparacao e' sempre por TAXA DIARIA (R$/pregao), nao soma total,
porque a janela tick e' mais curta que a janela do ballpark (123 pregoes).

Nao usa `tick_storage.merge_ticks`/`data/raw_ticks/WDO@.parquet` (o local
CANONICO e compartilhado) de proposito -- 9 frentes rodam em paralelo no
mesmo diretorio de trabalho e uma race de merge/escrita nesse arquivo
compartilhado e' um risco desnecessario para um teste que so' precisa
rodar uma vez. Busca do MT5 e' local e RAPIDA (medido: ~90 mil ticks em
<0,1s, terminal ja' tem o dado em cache) -- best refazer o fetch a cada
execucao deste script do que persistir.

NAO destrava OOS: os dias buscados sao um SUBCONJUNTO dos dias que
`LockedBars.in_sample()` ja' devolveria para o M1 (filtrados por
`>= TICK_AVAIL_START` e sempre `< frozen_cutoff`) -- `.out_of_sample()`
nunca e' chamado.

Uso: `python scripts/daytrade/wdo_grid_reload_f1_tick_probe.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import profile_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

# Reaproveita a MONTAGEM ja escrita nesta mesma frente (round 1/2) --
# arquivo proprio desta frente, nao "shared file" de outra frente.
sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))
from wdo_grid_reload_f1_lab import (  # noqa: E402
    CANDIDATO_PARAMS,
    CAPITAL_NOCIONAL,
    BALLPARK_IS_LIQUIDO_BRL,
    MIN_BARRAS_POR_PREGAO,
    montar_config,
    rodar,
)

SYMBOL = "WDO@"
TICK_AVAIL_START = pd.Timestamp("2026-02-27").tz_localize("UTC")
#: buffer em torno de min/max de cada pregao no M1, para garantir que o
#: tick busca cobre a sessao inteira mesmo se o primeiro/ultimo negocio do
#: dia cair fora do timestamp exato da primeira/ultima barra M1.
BUFFER = pd.Timedelta(minutes=2)
BALLPARK_POR_PREGAO_BRL = BALLPARK_IS_LIQUIDO_BRL / 123.0  # 123 pregoes IS conhecidos


def dias_is_com_tick_disponivel() -> tuple[LockedBars, list, pd.DataFrame]:
    """Devolve (locked_m1, lista_de_dias_elegiveis, m1_subset_desses_dias).
    `locked_m1` continua sendo o objeto travado do M1 completo -- so' usamos
    `.in_sample()` dele; a lista de dias e' um SUBCONJUNTO desse resultado
    (nunca um dia >= cutoff)."""
    df = load_m1(SYMBOL).sort_index()
    profile = profile_for(SYMBOL)
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(df, split)
    is_bars = locked.in_sample()
    contagem = is_bars.groupby(is_bars.index.date).size()
    dias = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    dias_com_tick = [d for d in dias if pd.Timestamp(d, tz="UTC") >= TICK_AVAIL_START]
    m1_subset = is_bars[[d in set(dias_com_tick) for d in is_bars.index.date]]
    return locked, dias_com_tick, m1_subset


def buscar_ticks(dias: list, m1_subset: pd.DataFrame) -> pd.DataFrame:
    import MetaTrader5 as mt5
    ok = mt5.initialize()
    if not ok:
        raise SystemExit(f"[tick_probe] falha ao conectar MT5: {mt5.last_error()}")
    mt5.symbol_select(SYMBOL, True)
    chunks = []
    for d in dias:
        dia_bars = m1_subset[[idx == d for idx in m1_subset.index.date]]
        start = (dia_bars.index.min() - BUFFER).tz_convert(None).to_pydatetime()
        end = (dia_bars.index.max() + BUFFER).tz_convert(None).to_pydatetime()
        raw = mt5.copy_ticks_range(SYMBOL, start, end, mt5.COPY_TICKS_TRADE)
        if raw is None or len(raw) == 0:
            print(f"[tick_probe] AVISO: 0 ticks em {d} ({start} -> {end}), last_error={mt5.last_error()}")
            continue
        df = pd.DataFrame(raw)
        # CUIDADO: `pd.DataFrame({"col": serie}, index=novo_indice)` faz
        # ALINHAMENTO por rotulo entre `serie.index` (RangeIndex 0..n-1, o
        # default de `pd.DataFrame(raw)`) e `novo_indice` (DatetimeIndex) --
        # como os dois nunca compartilham rotulo nenhum, o resultado seria
        # TUDO NaN (bug real, pego rodando este script: `no_tick` explodiu
        # com "cannot convert float NaN to integer"). Atribui o indice
        # DIRETO no `df` (mesmo padrao de `mt5_ticks_source._ticks_to_df`)
        # em vez de passar pro construtor, o que preserva alinhamento
        # POSICIONAL em vez de por rotulo.
        df.index = pd.to_datetime(df["time_msc"], unit="ms").dt.tz_localize("UTC")
        vol = df["volume_real"].where(df["volume_real"] > 0, df["volume"])
        chunks.append(pd.DataFrame({
            "open": df["last"], "high": df["last"], "low": df["last"],
            "close": df["last"], "volume": vol,
        }))
    mt5.shutdown()
    if not chunks:
        raise SystemExit("[tick_probe] nenhum tick recebido para nenhum dia -- aborta.")
    bars = pd.concat(chunks).sort_index()
    bars.index.name = "time"
    return bars


def main() -> None:
    locked_m1, dias, m1_subset = dias_is_com_tick_disponivel()
    print(f"[tick_probe] {SYMBOL}: {len(dias)} pregoes IS com tick disponivel "
          f"({dias[0]} -> {dias[-1]}) de 123 pregoes IS totais "
          f"(faltam {123 - len(dias)} pregoes no INICIO do IS, sem tick no terminal).")
    print(f"[tick_probe] ballpark conhecido: R${num_br(BALLPARK_IS_LIQUIDO_BRL)} / 123 pregoes "
          f"= R${num_br(BALLPARK_POR_PREGAO_BRL)}/pregao")

    tick_bars = buscar_ticks(dias, m1_subset)
    print(f"[tick_probe] {len(tick_bars)} ticks baixados do MT5, "
          f"{tick_bars.index.min()} -> {tick_bars.index.max()}")

    # Trava estrutural extra (defesa em profundidade): embora `dias` ja'
    # venha filtrado de `locked_m1.in_sample()`, garante que NENHUM tick
    # baixado cruzou o cutoff por engano (ex.: BUFFER empurrando a ultima
    # barra do ultimo dia elegivel para depois do corte).
    cutoff = locked_m1.split.cutoff
    if tick_bars.index.tz is not None and cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize(tick_bars.index.tz)
    além_do_corte = tick_bars.index[tick_bars.index >= cutoff]
    if len(além_do_corte):
        raise SystemExit(
            f"[tick_probe] {len(além_do_corte)} tick(s) cairam em/depois do cutoff "
            f"{cutoff} -- corta antes de rodar (nao pode vazar para OOS)."
        )

    n_pregoes_tick = len(dias)

    cfg = montar_config()  # config padrao: fee + slippage 1 tick, fill capped por volume
    resultado_tick = rodar(tick_bars, cfg)
    resultado_m1_mesmos_dias = rodar(m1_subset, cfg)  # MESMOS dias, resolucao M1 -- comparacao maca-a-maca

    print("\n=== comparacao maca-a-maca: MESMOS 72 pregoes, tick vs M1 ===")
    item_tick = linha_de_resultado(f"tick ({n_pregoes_tick} pregoes)", resultado_tick,
                                    CAPITAL_NOCIONAL, capital_nocional=True)
    item_m1 = linha_de_resultado(f"M1 ({n_pregoes_tick} pregoes, mesmos dias)", resultado_m1_mesmos_dias,
                                  CAPITAL_NOCIONAL, capital_nocional=True)
    print(cabecalho())
    print(linha(item_tick))
    print(linha(item_m1))

    liquido_tick = sum(t.pnl_brl for t in resultado_tick.trades)
    liquido_m1 = sum(t.pnl_brl for t in resultado_m1_mesmos_dias.trades)
    taxa_tick = liquido_tick / n_pregoes_tick
    taxa_m1 = liquido_m1 / n_pregoes_tick
    print(f"\nR$/pregao -- tick: {num_br(taxa_tick)}  |  M1 (mesmos dias): {num_br(taxa_m1)}  |  "
          f"ballpark conhecido (123 pregoes completos): {num_br(BALLPARK_POR_PREGAO_BRL)}")
    print(f"tick como fracao do ballpark diario: {num_br(100.0 * taxa_tick / BALLPARK_POR_PREGAO_BRL, 1)}%")
    print(f"trades: tick={len(resultado_tick.trades)} ({num_br(len(resultado_tick.trades) / n_pregoes_tick, 1)}/pregao), "
          f"M1={len(resultado_m1_mesmos_dias.trades)} ({num_br(len(resultado_m1_mesmos_dias.trades) / n_pregoes_tick, 1)}/pregao)")

    # win rate explicito -- e' o numero que decide (breakeven ~94,1% pela
    # razao 1:16), reportado nas duas resolucoes.
    def win_rate(trades) -> float:
        if not trades:
            return float("nan")
        vencedores = sum(1 for t in trades if t.pnl_brl > 0)
        return 100.0 * vencedores / len(trades)
    print(f"win rate -- tick: {num_br(win_rate(resultado_tick.trades), 1)}%  |  "
          f"M1: {num_br(win_rate(resultado_m1_mesmos_dias.trades), 1)}%  |  "
          f"breakeven exigido pela razao 1:16 (T1/S16): ~94,1%")


if __name__ == "__main__":
    main()
