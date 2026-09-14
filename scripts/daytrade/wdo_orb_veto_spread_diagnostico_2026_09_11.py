"""Veto de spread anormal sobre o `wdo_orb` -- BLOQUEADO por dado ausente,
nao por resultado. Este script documenta o bloqueio empiricamente (nao so
por leitura de docstring) e roda o unico diagnostico possivel com o dado
que EXISTE, deixado claramente rotulado como ilustrativo, nao validacao.

## A hipotese

"A cada tick, comparar spread_atual (ask-bid) contra a moda do spread do
proprio pregao; se alargar >=2x a moda por K ticks ou >=2s, suprimir
Enter/EnterLimit novo do wdo_orb (via on_order_rejected, sem travar
pending_side) enquanto durar."

O racional (spread alargado = book desequilibrado = risco de postar limite
agora) e' razoavel. O bloqueio nao e' de mecanismo -- e' de DADO.

## O bloqueio, verificado em TRES camadas (nao so' inferido)

1. **Arquivo canonico** (`data/raw_ticks/WDO_A_.parquet`, 21.524.225 ticks,
   72 pregoes IS + 58 pregoes ate 2026-09-04): `bid`/`ask` sao ZERO em
   21.524.225 de 21.524.225 linhas -- 0 nonzero, nao "raro", ZERO. Nao e'
   dado faltando por buraco; e' estrutural: `mt5_ticks_source.py` busca
   ticks com `mt5.COPY_TICKS_TRADE` (nao `COPY_TICKS_ALL`), por decisao
   DOCUMENTADA e medida em 2026-08-22 ("COPY_TICKS_ALL devolve 2 linhas por
   negocio -- uma de negocio, uma de bid/ask resultante; COPY_TICKS_TRADE
   devolve so' a de negocio"). O pipeline de dado deste projeto NUNCA
   guardou o lado de cotacao do book para o simbolo continuo.

2. **Feed AO VIVO, agora** (`mt5.symbol_info_tick("WDO@")`, terminal Rico
   conectado neste rodada): `bid=0.0, ask=0.0, last=5145.5`. O simbolo
   CONTINUO ("WDO@", o que `WdoOrb.symbol` declara e o que TODO backtest
   deste robo consome) e' um instrumento SINTETICO que o MT5/corretora
   mantem so' para grafico continuo entre vencimentos -- ele nao tem book
   proprio, entao nao tem bid/ask proprio, nem ao vivo. O contrato REAL por
   tras dele (`WDOV26`, checado no mesmo instante) tem bid/ask de verdade
   (5.145,5 / 5.147,5, spread ~4 ticks agora) -- mas e' outro simbolo, com
   OUTRO fluxo de tick, que o robo/backtest nunca le.

3. **Unica excecao encontrada no repo**: `data/raw_ticks/WDOU26_2026_08_28.
   parquet` -- 140.935 ticks do contrato REAL (WDOU26) com bid/ask validos,
   de UM pregao (2026-08-28, 09:00-17:43 BRT -- o dia do incidente que
   zerou a conta, capturado por outro motivo). E' o UNICO ponto de dado
   deste repo onde a hipotese e' sequer CALCULAVEL. Nao cobre a janela
   IS/OOS do wdo_orb (2026-02-27..2026-08-25) nem por perto -- e' 1 pregao
   contra 123.

## Por que isto e' INVIAVEL, nao INDEFINIDA

INDEFINIDA seria "temos o dado, a amostra e' pequena, o IC atravessa o
breakeven". Aqui nao ha' AMOSTRA nenhuma para medir o efeito do veto sobre
as entradas historicas do wdo_orb -- os tres achados acima significam que
NENHUMA reconstrucao retroativa e' possivel: os ticks de cotacao que
existiram durante os 123 pregoes de IS/OOS nunca foram salvos (o pipeline
pedia so' `COPY_TICKS_TRADE`) e nao ha' como "rebobinar" o book do passado.
Rodar o backtest do wdo_orb COM o veto, hoje, exigiria FABRICAR uma serie
de spread histórica -- exatamente o proxy inventado que o metodo desta
rodada probe reportar em vez de simular.

## O que SERIA preciso obter (a resposta ao item 4 do metodo)

1. Mudar `market_data_intraday/mt5_ticks_source.py` para tambem buscar
   `mt5.COPY_TICKS_ALL` (ou rodar uma segunda captura em paralelo so' de
   cotacao) do CONTRATO REAL correspondente ao mes vigente (nao do simbolo
   `@`, que a descoberta 2 acima mostra nao ter book propria) -- e' mudanca
   de pipeline de dado, fora do escopo de um script de experimento (nao
   editar producao nesta fase).
2. Coletar isso PARA FRENTE por semanas (a convencao do projeto pede
   "teste pequeno primeiro" -- aqui o minimo seria 1-4 semanas de pregao
   real gravado, nao retroativo) antes de ter QUALQUER amostra para testar
   o veto contra as entradas reais do wdo_orb.
3. Como o contrato real ROLA (WDOU26 -> WDOV26 -> ...), a captura precisa
   acompanhar o rollover (mesmo problema que `WDO_A_.parquet` resolve para
   preco/volume, mas ainda NAO resolvido para bid/ask).

## O diagnostico que ESTE script roda (ilustrativo, NAO validacao)

Com o unico pregao que tem bid/ask real (WDOU26, 2026-08-28), calcula a
moda CAUSAL (expanding, so' com ticks ESTRITAMENTE anteriores ao tick
corrente, dentro do mesmo pregao -- sem look-ahead) do spread em ticks, e
mede que FRACAO do pregao ficaria sob veto para uma pequena grade de
(multiplo, min_ticks, min_segundos). Isto NAO diz se o veto teria ajudado
ou atrapalhado o wdo_orb -- diz so' QUAO FREQUENTE o gatilho seria, num
unico dia real, o que ja e' informacao (se o veto disparasse 90% do
pregao ele seria inviavel por constancia, independente de qualquer
backtest). Paralelizado (`ProcessPoolExecutor`) por ser uma grade de
parametro, mesmo pequena -- convencao do projeto.

Uso: `python -u scripts/daytrade/wdo_orb_veto_spread_diagnostico_2026_09_11.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_REAL_COM_SPREAD = RAIZ / "data" / "raw_ticks" / "WDOU26_2026_08_28.parquet"
TICK_SIZE = 0.5

#: grade pequena de confirmacao -- (multiplo, min_ticks, min_segundos).
GRADE = [
    (1.5, 3, 1.0),
    (1.5, 5, 2.0),
    (2.0, 3, 1.0),
    (2.0, 5, 2.0),
    (2.0, 10, 3.0),
    (3.0, 5, 2.0),
]

#: tetos defensivos -- spread negativo ou absurdo e' tick sujo (book
#: cruzado/velho no feed), nao alargamento de verdade. 0,05% dos ticks do
#: dia caem fora de [0, 10] ticks (checado antes de escrever este filtro).
SPREAD_TICKS_MIN, SPREAD_TICKS_MAX = 0, 10
MIN_OBS_BASELINE = 100  # ticks minimos de historico do dia antes da moda valer


def _carrega_spread_ticks() -> tuple[np.ndarray, np.ndarray]:
    """`(ts, spread_ticks)` -- arrays POSICIONAIS (RangeIndex implicito),
    nunca indexados por timestamp: a base de tick tem timestamps
    DUPLICADOS (varios negocios no mesmo milissegundo), e usar o timestamp
    como rotulo de `.loc` faz o pandas expandir a selecao para TODAS as
    linhas daquele rotulo -- bug real encontrado ao escrever este script.
    Posicao inteira nao tem essa ambiguidade."""
    df = pd.read_parquet(ARQUIVO_REAL_COM_SPREAD)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    spread = (df["ask"] - df["bid"]).to_numpy()
    st = np.round(spread / TICK_SIZE)
    # UTC ja' e' um relogio absoluto -- tira o tz so' para virar
    # `datetime64[ns]` nativo (evita o aviso de conversao do numpy); a
    # diferenca ENTRE dois instantes UTC nao muda ao tirar o rotulo de fuso.
    ts = df.index.tz_convert("UTC").tz_localize(None).to_numpy()
    mask = (st >= SPREAD_TICKS_MIN) & (st <= SPREAD_TICKS_MAX)
    return ts[mask], st[mask].astype(np.int64)


def _moda_causal(spread_ticks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Moda EXPANDING do spread, usando so' ticks ESTRITAMENTE anteriores
    ao tick corrente (sem look-ahead). Devolve `(moda_causal, n_obs_causal)`
    -- `n_obs_causal` decide se ha baseline suficiente (`MIN_OBS_BASELINE`).

    Vetorizado: one-hot por valor inteiro de spread (0..10), cumsum,
    deslocado 1 posicao para excluir o proprio tick, argmax por linha =
    moda causal (empate resolvido pelo MENOR valor, `argmax` de numpy)."""
    valores = np.arange(SPREAD_TICKS_MIN, SPREAD_TICKS_MAX + 1)
    onehot = (spread_ticks[:, None] == valores[None, :]).astype(np.int64)
    cum = onehot.cumsum(axis=0)
    cum_antes = np.vstack([np.zeros((1, cum.shape[1]), dtype=np.int64), cum[:-1]])
    n_obs = cum_antes.sum(axis=1)
    moda_idx = cum_antes.argmax(axis=1)
    moda = valores[moda_idx]
    return moda, n_obs


def _veto_array(ts: np.ndarray, spread_ticks: np.ndarray, moda: np.ndarray,
                 n_obs: np.ndarray, multiplo: float, min_ticks: int,
                 min_segundos: float) -> np.ndarray:
    """Veto ativo: alargamento (>= multiplo x moda causal) sustentado por
    >= min_ticks ticks OU >= min_segundos, desde que ja haja baseline
    (`n_obs >= MIN_OBS_BASELINE`). Fica ativo ate o alargamento cessar.
    Tudo por POSICAO inteira -- ver a nota de `_carrega_spread_ticks`."""
    n = len(spread_ticks)
    alargado = (n_obs >= MIN_OBS_BASELINE) & (spread_ticks >= multiplo * moda) & (moda > 0)
    veto = np.zeros(n, dtype=bool)
    if not alargado.any():
        return veto

    mudou = np.empty(n, dtype=bool)
    mudou[0] = True
    mudou[1:] = alargado[1:] != alargado[:-1]
    run_id = np.cumsum(mudou) - 1

    # primeira posicao de cada run -- `np.minimum.at` para nao sobrescrever
    # com a ULTIMA ocorrencia (uma atribuicao posicional simples faria isso).
    inicio_por_run = np.full(run_id[-1] + 1, n, dtype=np.int64)
    np.minimum.at(inicio_por_run, run_id, np.arange(n))

    pos_no_run = np.arange(n) - inicio_por_run[run_id] + 1  # 1-indexado
    ts_ns = ts.astype("datetime64[ns]").astype(np.int64)
    elapsed_s = (ts_ns - ts_ns[inicio_por_run[run_id]]) / 1e9
    confirmado = (pos_no_run >= min_ticks) | (elapsed_s >= min_segundos)
    veto = alargado & confirmado
    return veto


def _roda_combo(spec: dict) -> str:
    ts, spread_ticks = _carrega_spread_ticks()
    moda, n_obs = _moda_causal(spread_ticks)
    veto = _veto_array(ts, spread_ticks, moda, n_obs,
                        spec["multiplo"], spec["min_ticks"], spec["min_segundos"])
    frac_ticks = float(veto.mean())
    inicio_veto = veto & ~np.concatenate(([False], veto[:-1]))
    fim_veto = veto & ~np.concatenate((veto[1:], [False]))
    n_episodios = int(inicio_veto.sum())
    ts_ns = ts.astype("datetime64[ns]").astype(np.int64)
    tempo_sob_veto_s = float(
        (ts_ns[fim_veto] - ts_ns[inicio_veto]).sum() / 1e9
    ) if n_episodios else 0.0
    return (f"multiplo={spec['multiplo']:.1f} min_ticks={spec['min_ticks']:>2} "
            f"min_s={spec['min_segundos']:.1f}  ->  "
            f"{frac_ticks*100:5.2f}% dos ticks sob veto, "
            f"{n_episodios:3d} episodios, "
            f"{tempo_sob_veto_s/60:6.1f} min de pregao suprimidos")


def main() -> None:
    print(__doc__.split("## O diagnostico")[0])

    if not ARQUIVO_REAL_COM_SPREAD.exists():
        print(f"[BLOQUEADO] {ARQUIVO_REAL_COM_SPREAD} nao existe -- nem o "
              f"diagnostico ilustrativo pode rodar. Veredito: INVIAVEL por "
              f"dado ausente (ver a docstring do modulo).")
        sys.exit(1)

    ts, spread_ticks = _carrega_spread_ticks()
    print(f"[wdo_orb_veto_spread] {ARQUIVO_REAL_COM_SPREAD.name}: "
          f"{len(spread_ticks)} ticks limpos (spread em [{SPREAD_TICKS_MIN},"
          f"{SPREAD_TICKS_MAX}] ticks), pregao {pd.Timestamp(ts.min())} .. "
          f"{pd.Timestamp(ts.max())}")
    valores, contagens = np.unique(spread_ticks, return_counts=True)
    print("[wdo_orb_veto_spread] distribuicao do spread (ticks, % do dia):")
    for v, c in zip(valores, contagens):
        print(f"    {int(v):>2} tick(s): {100*c/len(spread_ticks):5.2f}%")
    print()

    specs = [dict(multiplo=m, min_ticks=k, min_segundos=s) for (m, k, s) in GRADE]
    with ProcessPoolExecutor(max_workers=min(len(specs), 6)) as pool:
        futures = {pool.submit(_roda_combo, spec): spec for spec in specs}
        linhas = []
        for future in as_completed(futures):
            texto = future.result()
            print(f"[diagnostico] {texto}", flush=True)
            linhas.append(texto)

    print(
        "\n[wdo_orb_veto_spread] LEITURA: isto e' UM pregao real (o do "
        "incidente 2026-08-28), do contrato WDOU26 -- nao e' o wdo_orb, nao "
        "e' a janela IS/OOS, e nao mede se o veto teria ajudado ou "
        "atrapalhado nenhuma operacao. Mede so' a FREQUENCIA do gatilho: "
        "se ela for alta o bastante para acender quase o pregao inteiro, o "
        "veto e' inviavel por constancia mesmo antes de qualquer backtest; "
        "se for baixa, so diz que o mecanismo dispara raro NESTE dia -- "
        "nenhuma das duas leituras substitui a medicao real, que exige "
        "dado que nao existe (ver a secao 'O que SERIA preciso obter')."
    )


if __name__ == "__main__":
    main()
