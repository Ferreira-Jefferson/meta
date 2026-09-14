"""Busca tick a tick (trade ticks) via o terminal MT5 local -- a menor
granularidade que o terminal oferece, abaixo do M1 de `mt5_source.py`.

Regra de fronteira (AGENTS.md #1): feature so importa `core/`. Mesmo padrao
de import LAZY do `MetaTrader5` de `mt5_source.py` -- nem todo ambiente que
importa este modulo tem o pacote instalado.

MT5 devolve tres tipos de tick misturados no mesmo stream: atualizacoes de
bid/ask (sem negocio nenhum), e ticks de NEGOCIO de verdade (`last`+`volume`
populados). So o segundo tipo importa para simular um robo maker (a decisao
"o preco tocou o nivel X" so' vale quando alguem efetivamente negociou ali) --
`mt5.COPY_TICKS_TRADE` ja filtra isso no proprio terminal, medido em
2026-08-22: um pedido com `COPY_TICKS_ALL` devolve 2 linhas por negocio (uma
de negocio, uma de bid/ask resultante); com `COPY_TICKS_TRADE` devolve so' a
linha de negocio.

Paginacao por TEMPO, nao por posicao: ao contrario de `copy_rates_from_pos`
(M1), a API de tick do MT5 nao tem "posicao" -- so' `copy_ticks_from(symbol,
data_inicio, count, flags)`. Cada pagina usa o `time_msc` do ULTIMO tick da
pagina anterior como proximo `data_inicio`, o que pode repetir esse tick na
pagina seguinte (o terminal nao documenta se a borda e inclusiva) -- por
isso `merge_ticks` (`tick_storage.py`) deduplica por LINHA INTEIRA, nao so'
por timestamp: dois negocios genuinos no MESMO milissegundo tem
bid/ask/last/volume proprios e sobrevivem; um tick repetido pela paginacao
tem todos os campos identicos e e' descartado.

`MAX_TICKS_PER_REQUEST`: sem limite documentado (testado ate 500k ticks
numa unica chamada sem erro), mas pagina em blocos menores por seguranca --
mesmo espirito defensivo de `mt5_source.MAX_BARS_PER_REQUEST`, so' que aqui
o numero e' precaucao, nao um limite medido do terminal.

FUSO NOS LIMITES -- o bug que ja COMEU 63 buracos de 3h do parquet canonico
===========================================================================
Todo `datetime` entregue ao pacote `MetaTrader5` passa por `.timestamp()`, e
`.timestamp()` de um NAIVE e' resolvido no fuso da MAQUINA que roda o
processo. Nesta maquina (Brasilia, o mesmo fuso do servidor) isso soma +3h
silenciosamente ao limite pedido. Um `datetime` tz-aware nao consulta o fuso
local -- por isso todo limite que sai daqui e' aware.

Duas rotas, com contratos DIFERENTES de proposito:

  - `fetch_ticks_range(symbol, start, end)`: `start`/`end` ja' chegam no
    relogio de PAREDE do servidor rotulado como UTC. Quem converte e' o
    chamador (`live/tick_feed.py::_limite_servidor`), porque so' ele sabe se
    o instante que tem em maos e' UTC de verdade.
  - `fetch_ticks_full_history`: o cursor de paginacao NAO precisa de
    conversao nenhuma -- `time_msc` ja' E' a parede do servidor. Precisa so'
    do ROTULO de UTC, que e' o que `_cursor_paginacao` poe.

O defeito era REAL (nao latente) na segunda rota: ate' 2026-09-07 o cursor
era naive, entao cada troca de pagina pedia a partir de `cursor + 3h` em vez
de `cursor`, pulando ate' 3h de negocio em CADA borda de pagina sem levantar
erro nenhum. MEDIDO no `data/raw_ticks/WDO_A_.parquet` (126 pregoes de WDO@
gerados por `scripts/daytrade/backfill_ticks.py`), 2026-09-07:

  - 63 lacunas de EXATAMENTE 180min, uma a cada ~198.500 linhas -- que e'
    o tamanho de uma pagina (`MAX_TICKS_PER_REQUEST` = 200.000, menos o tick
    de sobreposicao que o dedupe come);
  - 13.786 dos 71.316 minutos de pregao (19,3%) sem UM tick sequer;
  - 84 dos 126 pregoes com buraco; os outros 42 batem com a rota por
    INTERVALO tick a tick (`fetch_ticks_range` + `_dedupe_full_row`);
  - pior pregao medido, 2026-08-19: 75.710 ticks no parquet contra 134.439
    que a rota por intervalo devolve -- 43,7% do dia ausente, na faixa
    10:11..13:09.

Regerar o parquet e' o unico jeito de recuperar o dado."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

from core.b3_session import MT5_SERVER_TIMEZONE, server_utc_offset_hours
from market_data_intraday.mt5_connection import conectar

MAX_TICKS_PER_REQUEST = 200_000

DEFAULT_SERVER_UTC_OFFSET_HOURS = server_utc_offset_hours()

#: Data de partida da paginacao de historico completo -- so' precisa ser
#: "antes de qualquer tick real existir". O terminal retorna o tick mais
#: antigo que realmente tem (medido 2026-08-22: PMAM3 comeca em 2024-11-01
#: mesmo pedindo desde 2000), entao um numero redondo aqui nao trava nada.
#: `tzinfo=utc` pelo mesmo motivo de `_cursor_paginacao`: aqui o deslocamento
#: de 3h de um naive seria INOFENSIVO (2000-01-01 03:00 tambem e' antes de
#: qualquer tick), mas um naive escapando para a API do MT5 e' precisamente o
#: padrao que este modulo nao pode mais ter em lugar nenhum.
_GENESIS = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _cursor_paginacao(time_msc: int) -> datetime:
    """O `data_inicio` da PROXIMA pagina de `copy_ticks_from`: a parede do
    servidor do ultimo tick da pagina atual, ROTULADA como UTC.

    `time_msc` ja' e' a hora de parede do servidor em ms (o mesmo campo que
    `_ticks_to_df` converte para UTC de verdade na volta), entao aqui NAO ha
    conversao de fuso a fazer -- so' o rotulo. O rotulo e' o que impede o
    pacote `MetaTrader5` de resolver `.timestamp()` no fuso da maquina e
    empurrar a pagina seguinte 3h para frente (ver a secao "FUSO NOS LIMITES"
    na docstring do modulo, e `live/tick_feed.py::_limite_servidor` para a
    mesma correcao do lado do range).
    """
    return pd.to_datetime(int(time_msc), unit="ms", utc=True).to_pydatetime()


def _connect(mt5, login=None, password=None, server=None, path=None) -> bool:
    """Delega para `mt5_connection.conectar` -- uma sessao IPC por PROCESSO,
    nao uma por leitura.

    Ate 2026-09-14 isto (e o gemeo em `mt5_source.py`) chamava
    `mt5.initialize()` a cada busca, dizendo na docstring ser "idempotente".
    Nao era: com credenciais, `initialize()` repede autorizacao ao servidor da
    corretora, e 5 slots x 1 chamada a cada 5s derrubavam os CINCO feeds
    juntos com `-6 Terminal: Authorization failed` enquanto a sessao IPC que
    ja existia seguia lendo tick sem problema. A justificativa historica de
    duplicar o trecho ("pequeno demais para valer acoplamento") caiu junto: o
    pedaco deixou de ser pequeno quando passou a ter cache, invalidacao e
    retentativa -- e duas copias disso e' que seria caro. `mt5_connection` e
    da MESMA feature, entao nenhuma fronteira do AGENTS.md e' cruzada."""
    return conectar(mt5, login=login, password=password, server=server, path=path)


def _report_error(on_error: Optional[Callable[[str, Exception], None]], key: str, exc: Exception) -> None:
    if on_error is not None:
        on_error(key, exc)


def _falha_de_leitura(mt5, resultado, chamada: str) -> Optional[RuntimeError]:
    """Distingue "NAO HA negocio novo" de "NAO CONSEGUI ler" -- devolve o erro
    da segunda, `None` na primeira.

    A distincao que FALTOU em 2026-09-08. O terminal parou de entregar tick
    NOVO de WDO@ por 44,8 minutos e este modulo devolveu DataFrame vazio em
    538 chamadas seguidas sem chamar `on_error` uma unica vez -- `resultado is
    None or len(resultado) == 0 -> DataFrame()` engolia os dois casos no mesmo
    `return`. Sem sintoma nenhum, 45 minutos de cegueira ficaram
    indistinguiveis de um papel parado (item 5.17 do `LICOES_DE_PRODUCAO.md`).

    Os dois sinais que o pacote `MetaTrader5` DA e que estavam sendo jogados
    fora, medidos no terminal real (Rico-PRD, build 6182, 2026-09-08):

      - `copy_ticks_range` de simbolo inexistente -> `None`, e
        `last_error() == (-4, 'Terminal: Not found')`;
      - janela de madrugada, sem negocio nenhum -> array VAZIO, e
        `last_error() == (1, 'Success')`.

    Ou seja: vazio+`last_error` OK e' o caso normal (papel parado, janela sem
    negocio); `None`, ou vazio com codigo NEGATIVO, e' falha de leitura. O
    corte em `< 0` e' de proposito: todo codigo de erro do pacote e' negativo
    (`RES_E_*`), `1` e' `RES_S_OK` e `0` e' "nenhum erro registrado ainda" --
    tratar `0` como falha faria o feed gritar em processo recem-subido.
    """
    if resultado is None:
        return RuntimeError(f"{chamada} devolveu None (last_error={mt5.last_error()})")
    if len(resultado) == 0:
        erro = mt5.last_error()
        if isinstance(erro, (tuple, list)) and erro and int(erro[0]) < 0:
            return RuntimeError(f"{chamada} devolveu vazio com last_error={erro}")
    return None


def _ticks_to_df(ticks, server_utc_offset_hours: Optional[float]) -> pd.DataFrame:
    """Index em UTC de verdade (com milissegundo), a partir de `time_msc`
    (hora de parede do servidor, mesmo aviso de fuso de
    `mt5_source._bars_to_df` -- so' que em ms em vez de segundos inteiros,
    entao dois negocios no mesmo segundo nao colapsam num so' timestamp)."""
    df = pd.DataFrame(ticks)
    parede = pd.to_datetime(df["time_msc"], unit="ms")
    if server_utc_offset_hours is None:
        utc = parede.dt.tz_localize(MT5_SERVER_TIMEZONE, ambiguous="NaT",
                                    nonexistent="NaT").dt.tz_convert("UTC")
    else:
        utc = parede.dt.tz_localize("UTC") + pd.Timedelta(hours=server_utc_offset_hours)
    df = df[["bid", "ask", "last", "volume", "volume_real", "flags"]].copy()
    df.index = utc
    df.index.name = "time"
    df = df[df.index.notna()].sort_index()
    return df


def fetch_ticks_range(
    symbol: str,
    start: datetime,
    end: datetime,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: Optional[float] = None,
    **connect_kwargs,
) -> pd.DataFrame:
    """Trade ticks de `symbol` entre `start` e `end`. DataFrame vazio (nunca
    excecao) se o terminal/simbolo falhar -- mesmo contrato de
    `mt5_source.fetch_m1_range`.

    `start`/`end` tem de chegar no relogio de PAREDE do servidor, tz-aware
    (a receita esta em `live/tick_feed.py::_limite_servidor`): esta funcao
    NAO converte, porque so' o chamador sabe se o instante que ele tem e' UTC
    de verdade. Passar naive faz o pacote `MetaTrader5` resolver
    `.timestamp()` no fuso da maquina e deslocar a janela -- ver a secao
    "FUSO NOS LIMITES" na docstring do modulo."""
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # pragma: no cover - ambiente sem o pacote
        _report_error(on_error, "import", exc)
        return pd.DataFrame()

    if not _connect(mt5, **connect_kwargs):
        _report_error(
            on_error, "connect",
            RuntimeError(f"falha ao conectar ao terminal MT5 (last_error={mt5.last_error()})"),
        )
        return pd.DataFrame()

    try:
        mt5.symbol_select(symbol, True)
        ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_TRADE)
    except Exception as exc:
        _report_error(on_error, symbol, exc)
        return pd.DataFrame()

    falha = _falha_de_leitura(mt5, ticks, "copy_ticks_range")
    if falha is not None:
        _report_error(on_error, symbol, falha)
        return pd.DataFrame()
    if len(ticks) == 0:
        return pd.DataFrame()
    return _ticks_to_df(ticks, server_utc_offset_hours)


def fetch_ticks_full_history(
    symbol: str,
    on_error: Optional[Callable[[str, Exception], None]] = None,
    server_utc_offset_hours: Optional[float] = None,
    **connect_kwargs,
) -> pd.DataFrame:
    """Pagina `copy_ticks_from` a partir de `_GENESIS` ate um lote menor que
    `MAX_TICKS_PER_REQUEST` voltar (= alcancou o tick mais recente
    disponivel) -- mesmo espirito de `mt5_source.fetch_m1_full_history`,
    adaptado para paginacao por tempo (ver docstring do modulo).

    O cursor de cada pagina sai de `_cursor_paginacao`, NUNCA de um naive:
    era assim que 3h de pregao sumiam em cada borda de pagina, sem erro
    nenhum (ver "FUSO NOS LIMITES" na docstring do modulo)."""
    try:
        import MetaTrader5 as mt5
    except Exception as exc:  # pragma: no cover - ambiente sem o pacote
        _report_error(on_error, "import", exc)
        return pd.DataFrame()

    if not _connect(mt5, **connect_kwargs):
        _report_error(
            on_error, "connect",
            RuntimeError(f"falha ao conectar ao terminal MT5 (last_error={mt5.last_error()})"),
        )
        return pd.DataFrame()

    try:
        mt5.symbol_select(symbol, True)
    except Exception as exc:
        _report_error(on_error, symbol, exc)
        return pd.DataFrame()

    chunks: list[pd.DataFrame] = []
    cursor = _GENESIS
    while True:
        try:
            ticks = mt5.copy_ticks_from(symbol, cursor, MAX_TICKS_PER_REQUEST, mt5.COPY_TICKS_TRADE)
        except Exception as exc:
            _report_error(on_error, symbol, exc)
            break
        falha = _falha_de_leitura(mt5, ticks, "copy_ticks_from")
        if falha is not None:
            _report_error(on_error, symbol, falha)
            break
        if len(ticks) == 0:
            break
        chunks.append(_ticks_to_df(ticks, server_utc_offset_hours))
        if len(ticks) < MAX_TICKS_PER_REQUEST:
            break
        cursor = _cursor_paginacao(ticks[-1]["time_msc"])

    if not chunks:
        return pd.DataFrame()
    merged = pd.concat(chunks)
    # `duplicated()` sozinho so' olha colunas, ignorando o index -- dois
    # negocios diferentes com bid/ask/last/volume/flags identicos por
    # coincidencia (comum: mesmo lote redondo, mesmo preco) mas em
    # timestamps DIFERENTES nao podem ser tratados como o mesmo tick
    # repetido pela paginacao. Inclui o timestamp na comparacao.
    merged = merged.reset_index(names="time")
    merged = merged[~merged.duplicated(keep="last")].set_index("time")
    return merged.sort_index()
