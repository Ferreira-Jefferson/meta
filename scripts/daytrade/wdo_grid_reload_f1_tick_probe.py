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

AVISO -- `buscar_ticks` estava ERRADA ate' 2026-09-07 (numeros antigos NAO
sao reproduziveis por este arquivo)
====================================================================
Esta funcao e' o fetcher COMPARTILHADO de toda a linha F1-tick (importada
por `wdo_grid_reload_f1_tick_lab.py`, `wdo_grid_reload_f1_tick_lab_oos_
2026_08_27.py` e, por tabela, por `wdof1_tick_cache_2026_08_27.py`,
`wdof1_rerun_tabela_2026_08_27.py`, `signal_quality_wdof1_*`,
`reversal_exit_wdof1_*`, `wdo_grid_reload_f1_tick_rejection_lab.py`,
`wdof1_tempo_fila_resultado_2026_09_04.py`, ...). Ate' 2026-09-07 ela tinha
os DOIS defeitos da familia de fuso do MT5, e nenhum deles levanta excecao:

1. Rotulava `time_msc` (hora de PAREDE do servidor = Brasilia, medido em
   `core/b3_session.py`) como UTC. Erro fixo de 3h no index.
2. Passava os limites de `copy_ticks_range` como `datetime` NAIVE. Medido
   2026-09-07: o pacote `MetaTrader5` converte o limite com `.timestamp()`,
   ou seja reinterpreta um naive no fuso da MAQUINA (Brasilia, aqui) -- a
   janela pedida andava +3h. Somado ao BUFFER de 2 min, a janela efetiva
   virava "das 14:58 as 18:29 de parede" em vez de "das 08:58 as 18:31".

Efeito MEDIDO no artefato que esta funcao gerou,
`data/raw_ticks/WDO_A_f1.parquet` (4.011.197 ticks, 123 pregoes): TODO
pregao cobre 14:58..18:29 -- 3h31 de um pregao de 9h30. O parquet gerado
pela rota CORRETA (`backfill_ticks.py` -> `fetch_ticks_full_history`),
`data/raw_ticks/WDO_A_.parquet`, cobre 12:00..21:29 UTC (= 09:00..18:29 de
Brasilia) e tem 16.624.744 ticks no mesmo periodo. Ou seja: a linha F1-tick
mediu ~24% dos negocios do pregao, so' a tarde, achando que media o dia.
(O rotulo 3h cedo tambem desloca a comparacao com `session_end_time` do
perfil, que a maquina le em UTC via `ts.time()`. No `WDO@` o corte e' 21:30
e o dado termina 21:29:59, entao esse flatten nao dispara nem certo nem
errado -- mas qualquer corte que caisse dentro de 12:00..21:29 UTC teria
disparado na hora errada, sem sintoma nenhum.)

A funcao foi CORRIGIDA (rota compartilhada `mt5_ticks_source.
fetch_ticks_range` + limite no relogio do servidor + folga de fetch), mas o
parquet em disco NAO foi regerado: enquanto ele nao for, `WDO_A_f1.parquet`
e todo numero publicado da linha F1-tick antes de 2026-09-07 (headline IS,
"ponto de morte" de pedagio, R$/pregao, OOS, tempo de fila) descrevem a
janela truncada, nao o pregao.

Uso: `python scripts/daytrade/wdo_grid_reload_f1_tick_probe.py`
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
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
from core.b3_session import utc_to_server_wall_clock  # noqa: E402
from market_data_intraday.mt5_ticks_source import fetch_ticks_range  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from market_data_intraday.tick_bars import ticks_to_degenerate_bars  # noqa: E402

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

#: Quanto o limite INFERIOR pedido ao terminal recua alem do que o pregao
#: exigiria. `copy_ticks_range` com `date_from` DENTRO de um pregao devolve
#: negocio incompleto ou ZERO sem levantar excecao (medido 2026-08-24,
#: Rico/XP -- e' a razao de `live/tick_feed.py::_SAFE_FETCH_LOOKBACK`
#: existir, com este mesmo numero). O recorte para a janela do dia continua
#: sendo feito DEPOIS, sobre o index ja corrigido de fuso.
FOLGA_FETCH = timedelta(days=1)


def _limite_servidor(instant_utc) -> datetime:
    """O limite a passar para `copy_ticks_range`: o relogio de PAREDE do
    servidor, rotulado como UTC.

    NAO e' o `datetime` naive que `live/tick_feed.py` usa, de proposito --
    ver o AVISO na docstring do modulo: o pacote `MetaTrader5` converte o
    limite com `.timestamp()`, entao um naive e' reinterpretado no fuso da
    MAQUINA e a janela anda o offset local inteiro (+3h nesta). Um tz-aware
    UTC cujo relogio de parede ja e' o do servidor e' imune a isso em
    qualquer maquina. Medido 2026-09-07: pedir naive 12:00 devolveu negocios
    de 15:00 de parede; pedir 15:00 UTC devolveu exatamente 15:00 de parede.
    """
    instant = pd.Timestamp(instant_utc).to_pydatetime()
    return utc_to_server_wall_clock(instant).replace(tzinfo=timezone.utc)


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
    """Trade ticks dos `dias`, como barra degenerada, index em UTC de
    VERDADE.

    Delega a `market_data_intraday.mt5_ticks_source.fetch_ticks_range` -- a
    MESMA rota que `live/tick_feed.py` -- em vez de chamar `copy_ticks_range`
    na mao: e' ela que converte `time_msc` (parede do servidor) para UTC pelo
    FUSO declarado em `core.b3_session`, e nao por uma constante. Ver o AVISO
    na docstring do modulo para o que esta funcao devolvia antes de
    2026-09-07."""
    erros: list[tuple[str, Exception]] = []
    chunks = []
    for d in dias:
        dia_bars = m1_subset[[idx == d for idx in m1_subset.index.date]]
        inicio = dia_bars.index.min() - BUFFER
        fim = dia_bars.index.max() + BUFFER
        # Pede alem do necessario (`FOLGA_FETCH` para tras) e recorta depois:
        # e' a unica defesa contra o fetch PARCIAL silencioso.
        ticks = fetch_ticks_range(
            SYMBOL,
            _limite_servidor(inicio - FOLGA_FETCH),
            _limite_servidor(fim),
            on_error=lambda k, e: erros.append((k, e)),
        )
        if not ticks.empty:
            ticks = ticks[(ticks.index >= inicio) & (ticks.index <= fim)]
        if ticks.empty:
            print(f"[tick_probe] AVISO: 0 ticks em {d} ({inicio} -> {fim} UTC), erros={erros[-1:]}")
            continue
        chunks.append(ticks_to_degenerate_bars(ticks))
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
