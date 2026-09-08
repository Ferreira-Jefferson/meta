"""Frente F1-wdo-consolidacao -- CONFIRMACAO OOS (2026-08-27), primeira vez
que este trecho e' aberto para `WdoGridReloadMaker` (WDO@, "T1 S16 x1").

O dono AUTORIZOU EXPLICITAMENTE destravar o OOS agora (>=2026-06-13) para
esta validacao final -- `LockedBars.unlock(reason=...)` e' chamado aqui de
proposito, uma unica vez, com o motivo abaixo (`OOS_UNLOCK_REASON`).

AVISO 2026-09-07 -- este e' um REGISTRO de rodada; os numeros abaixo foram
medidos com `buscar_ticks` ainda defeituosa (janela pedida ao terminal
deslocada +3h e index rotulado 3h cedo, cobrindo so' 14:58..18:29 de cada
pregao). A funcao foi corrigida no probe, este arquivo NAO foi re-rodado.
Ler o AVISO no topo de `wdo_grid_reload_f1_tick_probe.py`. (A cobertura de
tick descrita abaixo continua valendo: re-testado em 2026-09-07 pela rota
corrigida, 2026-08-03 e 2026-08-04 seguem devolvendo 0 ticks -- e' gap de
retencao do terminal de verdade, nao efeito do defeito.)

## Cobertura de tick no trecho OOS -- CONFIRMADA (item 1 da missao)

O terminal MT5 (Rico) tem 51 pregoes OOS elegiveis (>=400 barras M1),
2026-06-15..2026-08-25 (de 52 dias corridos com barra M1 salva, 1 descartado
por ter so' 357 barras -- feriado/pregao parcial). Tick history cobre 49
desses 51 (96,1%) -- SO' 2026-08-03 e 2026-08-04 vieram com 0 ticks do MT5
(`copy_ticks_range` devolveu array vazio, `last_error()=(1,'Success')`, ou
seja nao e' erro de conexao: o terminal simplesmente nao tem tick retido
para esses 2 dias -- gap pontual de retencao, nao um problema de cobertura
em bloco como o do IS pre-2026-02-27).

Decisao (a pergunta explicita da missao: "cai pra M1 no trecho do OOS sem
tick?"): SIM, so' para esses 2 dias -- ao contrario do IS (onde os 51
pregoes sem tick eram o INICIO em bloco de uma janela sem tick nenhum, e a
escolha la' foi excluir o subconjunto inteiro), aqui e' um buraco de 2 dias
NO MEIO de uma janela com tick disponivel -- excluir silenciosamente 2 dos
51 pregoes OOS (3,9%) para uma confirmacao que so' vai rodar UMA VEZ jogaria
fora dado real sem necessidade, quando M1 real desses 2 dias existe e cobre
o buraco. Efeito esperado do fallback: CONSERVADOR, nao otimista -- M1
SUBCONTA toques (`WdoGridReloadMaker.on_bar` so' reagenda apos ficar flat,
tick nao; ver `wdo_grid_reload_f1_tick_probe.py`, win rate tick 99,4% vs M1
89,3% nos MESMOS 72 dias do IS) -- ou seja, se algo, o fallback M1 SUBESTIMA
o resultado desses 2 dias, nunca infla.

`bars_mixed` (o produto principal deste modulo) e' portanto: tick nos 49
dias com tick real + M1 nativo (mas com o VOLUME normalizado, nao o
DataFrame cru de `load_m1` -- ver bug abaixo) nos 2 dias sem tick,
concatenado e ordenado por timestamp -- MESMAS colunas
(open/high/low/close/volume) nos dois casos, entao `run_intraday_backtest`
(que agrupa por `bars.index.date`, ver `engine.py:167`) processa cada
pregao de forma independente sem se importar com a resolucao mudar de um
dia pro outro.

## BUG achado e corrigido NESTA rodada -- concat naive de tick+M1 zerava o
## OOS inteiro em silencio (nenhum trade nos 49 dias de tick)

`load_m1()` devolve `open/high/low/close/tick_volume/spread/real_volume`
(nomes nativos do MT5) -- NUNCA uma coluna `volume`; `buscar_ticks` (tick)
devolve so' `open/high/low/close/volume`. A primeira versao deste modulo
fazia `pd.concat([tick_only_bars, m1_fallback_bars_RAW])` direto -- `concat`
UNE as colunas dos dois lados, entao toda linha TICK ganhava
`real_volume`/`tick_volume` = NaN (colunas que ela nunca teve).
`engine._bar_volume` LE ESSAS COLUNAS PRIMEIRO
(`row.get("real_volume", 0.0)` devolve o NaN GUARDADO, nao o default 0.0 --
a CHAVE existe, so' o VALOR e' NaN) -- resultado: `bar.volume = NaN` em
TODA barra tick do dataframe combinado. Com
`limit_fill_capped_by_volume=True` (padrao do repo), NENHUM toque preenche
com volume NaN -- as 49 sessoes tick do OOS produziam ZERO trades, SEM erro
nenhum (medido durante a bissecao dia-a-dia desta rodada: tick_only_bars
sozinho = 1.667 trades nos mesmos 49 dias; `bars_mixed` ANTES da correcao =
50 trades, todos nos 2 dias de fallback M1). O bug so' aparece quando as
DUAS resolucoes sao misturadas no MESMO dataframe -- `tick_only_bars`
sozinho e `m1_fallback_bars` sozinho sempre funcionaram, cada um sem a
coluna do outro.

Correcao (aplicada abaixo, em `carregar_oos_bars`): normaliza o M1 de
fallback para a MESMA formula de precedencia de `engine._bar_volume`
(`real_volume` quando >0, senao `tick_volume`) numa UNICA coluna `volume`,
e DESCARTA `tick_volume`/`spread`/`real_volume` ANTES de concatenar --
depois disso nenhuma linha tick ganha coluna nova por uniao, e
`_bar_volume` cai direto no `volume` de verdade dos dois lados (identico
ao que ja acontecia em `wdo_grid_reload_f1_tick_probe.py`, que NUNCA
mistura os dois no mesmo dataframe -- roda tick e M1 em rodadas SEPARADAS
do motor, por isso nunca bateu neste bug).

## O que NAO e' misturado

O subconjunto TICK-SO' (`tick_only_bars`, 49 dias) e' exposto separadamente
-- usado pelo reteste de qualidade de sinal (`signal_quality_wdof1_oos_
2026_08_27.py`), que precisa de volume de NEGOCIO individual (a feature
`volume_toque` so' faz sentido no tick; no M1 seria volume agregado do
MINUTO inteiro, escala completamente diferente -- misturar contaminaria a
correlacao com 2 pontos fora de escala). Trades dos 2 dias M1-fallback
simplesmente NAO encontram tick correspondente quando o reteste busca no
`tick_only_bars` (`touch_idx is None`) e caem em `sem_match`, excluidos
automaticamente -- comportamento correto SEM precisar de filtro extra.

## Reuso -- nada de infra reescrita

`buscar_ticks` (busca no MT5, formata tick como barra OHLC=`last`) e'
importado DIRETO de `wdo_grid_reload_f1_tick_probe.py`, generico em
`(dias, m1_subset)`, ja tolera dias com 0 ticks (imprime AVISO e pula --
`wdo_grid_reload_f1_tick_probe.py:100-102`). `MIN_BARRAS_POR_PREGAO` vem de
`wdo_grid_reload_f1_lab.py` (mesmo numero usado no IS, 400).

Uso: `python -u scripts/daytrade/wdo_grid_reload_f1_tick_lab_oos_2026_08_27.py`
(roda so' a confirmacao de cobertura + imprime o resumo; os scripts de
escada de capital e qualidade de sinal importam `carregar_oos_bars()` daqui).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts" / "daytrade") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "daytrade"))

from backtest.intraday.frozen_split import LockedBars, declare_frozen_split  # noqa: E402
from backtest.intraday.profiles import profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402

from wdo_grid_reload_f1_lab import MIN_BARRAS_POR_PREGAO  # noqa: E402
from wdo_grid_reload_f1_tick_probe import buscar_ticks  # noqa: E402

SYMBOL = "WDO@"

#: Motivo explicito exigido por `LockedBars.unlock()` -- autorizacao do dono
#: (conversa 2026-08-27) para esta confirmacao final, uma unica vez.
OOS_UNLOCK_REASON = (
    "Validacao final autorizada pelo dono em 2026-08-27 para consolidar "
    "capital/sinal antes de atualizar producao"
)


def dias_oos_elegiveis() -> tuple[LockedBars, list, pd.DataFrame]:
    """Devolve `(locked, dias_oos, m1_subset_oos)` -- `locked` ja' vem
    DESTRAVADO (`.unlock()` chamado aqui, motivo acima). `dias_oos` = todo
    pregao OOS (>= `profile.frozen_cutoff`) com pelo menos
    `MIN_BARRAS_POR_PREGAO` barras M1 -- mesma regra de elegibilidade do
    IS, nenhuma flexibilizada para o OOS ter mais dias."""
    df = load_m1(SYMBOL).sort_index()
    profile = profile_for(SYMBOL)
    split = declare_frozen_split(cutoff=profile.frozen_cutoff, note=profile.frozen_note)
    locked = LockedBars(df, split)
    locked.unlock(reason=OOS_UNLOCK_REASON)
    oos_bars = locked.out_of_sample()
    contagem = oos_bars.groupby(oos_bars.index.date).size()
    dias = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    m1_subset = oos_bars[[d in set(dias) for d in oos_bars.index.date]]
    return locked, dias, m1_subset


def carregar_oos_bars() -> dict:
    """Produto principal do modulo. Devolve um dict com:
      - `dias_oos`: todos os pregoes OOS elegiveis (51).
      - `dias_tick`: subconjunto com tick real disponivel no MT5 (49).
      - `dias_m1_fallback`: subconjunto SEM tick, preenchido com M1 (2:
        2026-08-03, 2026-08-04 -- ver docstring do modulo).
      - `tick_only_bars`: DataFrame so' com os 49 dias de tick (para o
        reteste de qualidade de sinal, que exige resolucao tick).
      - `m1_fallback_bars`: DataFrame so' com os 2 dias M1 (OHLCV nativo).
      - `bars_mixed`: concatenacao ordenada dos dois acima -- 51 pregoes,
        cobertura OOS COMPLETA (usado na escada de capital)."""
    locked, dias, m1_subset = dias_oos_elegiveis()
    tick_only_bars = buscar_ticks(dias, m1_subset)
    dias_tick = sorted(set(tick_only_bars.index.date))
    dias_m1_fallback = sorted(set(dias) - set(dias_tick))
    m1_fallback_bars_raw = m1_subset[[d in set(dias_m1_fallback) for d in m1_subset.index.date]]

    # BUG achado e corrigido nesta rodada (2026-08-27): `load_m1()` devolve
    # `tick_volume`/`spread`/`real_volume` (nomes nativos do MT5), NUNCA uma
    # coluna `volume` -- `buscar_ticks` (tick) devolve so' `volume`. Um
    # `pd.concat` NAIVE dos dois una as colunas: toda linha TICK ganha
    # `real_volume`/`tick_volume` = NaN (colunas que ela nunca teve), e
    # `engine._bar_volume` LE ESSAS COLUNAS PRIMEIRO (`row.get("real_volume",
    # 0.0)` devolve o NaN, nao o default 0.0, porque a CHAVE existe -- so' o
    # VALOR e' NaN) -- resultado: `bar.volume = NaN` em TODA barra tick do
    # dataframe combinado, `limit_fill_capped_by_volume=True` nunca preenche
    # nada com volume NaN, e as 49 sessoes tick do OOS silenciosamente
    # produziam ZERO trades (medido: 1.667 trades tick-only vira 50, todos
    # nos 2 dias de fallback M1 -- achado durante esta propria rodada de
    # confirmacao, via bissecao dia-a-dia). Correcao: normaliza o M1 de
    # fallback para a MESMA formula de precedencia do motor
    # (`real_volume` > 0 senao `tick_volume`) e reduz para as MESMAS 5
    # colunas do tick (`open/high/low/close/volume`) ANTES de concatenar --
    # depois disso nenhuma linha tick ganha coluna nova, `_bar_volume` cai
    # direto no `volume` de verdade dos dois lados.
    real_vol = m1_fallback_bars_raw["real_volume"].astype(float)
    tick_vol = m1_fallback_bars_raw["tick_volume"].astype(float)
    volume_m1 = real_vol.where(real_vol > 0, tick_vol)
    m1_fallback_bars = m1_fallback_bars_raw.assign(volume=volume_m1)[
        ["open", "high", "low", "close", "volume"]
    ]
    bars_mixed = pd.concat([tick_only_bars, m1_fallback_bars]).sort_index()

    # defesa em profundidade: tudo aqui tem que estar EM/DEPOIS do cutoff --
    # confirma que nao vazou nenhuma barra do IS por engano (buffer de
    # busca de tick, engano de indice, etc).
    cutoff = locked.split.cutoff
    if bars_mixed.index.tz is not None and cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize(bars_mixed.index.tz)
    antes_do_corte = bars_mixed.index[bars_mixed.index < cutoff]
    if len(antes_do_corte):
        raise SystemExit(
            f"[tick_lab_oos] {len(antes_do_corte)} barra(s) caem ANTES do cutoff "
            f"{cutoff} -- vazamento do IS para dentro do lote OOS, aborta."
        )

    return dict(
        dias_oos=dias, dias_tick=dias_tick, dias_m1_fallback=dias_m1_fallback,
        tick_only_bars=tick_only_bars, m1_fallback_bars=m1_fallback_bars,
        bars_mixed=bars_mixed, cutoff=locked.split.cutoff,
    )


def main() -> None:
    r = carregar_oos_bars()
    print(f"[tick_lab_oos] {SYMBOL} OOS (corte congelado >= {r['cutoff'].date()}):")
    print(f"  pregoes OOS elegiveis (>={MIN_BARRAS_POR_PREGAO} barras M1): {len(r['dias_oos'])} "
          f"({r['dias_oos'][0]} -> {r['dias_oos'][-1]})")
    print(f"  com tick real no MT5: {len(r['dias_tick'])}/{len(r['dias_oos'])} "
          f"({100.0 * len(r['dias_tick']) / len(r['dias_oos']):.1f}%)")
    print(f"  SEM tick (fallback M1): {r['dias_m1_fallback']}")
    print(f"  tick_only_bars: {len(r['tick_only_bars'])} ticks")
    print(f"  m1_fallback_bars: {len(r['m1_fallback_bars'])} barras M1")
    print(f"  bars_mixed (produto final, escada de capital): {len(r['bars_mixed'])} linhas, "
          f"{len(set(r['bars_mixed'].index.date))} pregoes, "
          f"{r['bars_mixed'].index.min()} -> {r['bars_mixed'].index.max()}")


if __name__ == "__main__":
    main()
