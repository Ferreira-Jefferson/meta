"""Baixa do terminal MT5 os pregoes de tick do WDO@ que faltam no cache.

O cache canonico `data/raw_ticks/WDO_A_.parquet` termina em 2026-09-04. A
analise das "ultimas 4 semanas fechadas" (pedido do dono, 2026-09-14)
precisa da semana de 08..11/09 (07/09 e' feriado) -- justamente a semana que
ele acabou de viver ao vivo.

NAO sobrescreve o canonico: grava um parquet SEPARADO
(`WDO_A_semana_2026_09_08.parquet`, mesmo schema), que os scripts de analise
concatenam na leitura. Motivo: ha' 5 robos ao vivo neste terminal agora;
mexer no arquivo que eles podem vir a ler e' risco desnecessario para um
ganho de zero.

Fuso: mesma receita de `live/tick_feed.py::_limite_servidor` -- o pacote
`MetaTrader5` chama `.timestamp()` no limite recebido, entao o limite tem de
chegar com o relogio de PAREDE do servidor rotulado como UTC.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from core.b3_session import utc_to_server_wall_clock  # noqa: E402
from market_data_intraday.mt5_ticks_source import fetch_ticks_range  # noqa: E402

SIMBOLO_REAL = "WDOV26"
DESTINO = RAIZ / "data" / "raw_ticks" / "WDO_A_semana_2026_09_08.parquet"
DIAS = ["2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"]


def _limite_servidor(instant_utc: datetime) -> datetime:
    return utc_to_server_wall_clock(instant_utc).replace(tzinfo=timezone.utc)


def main() -> None:
    erros: list[str] = []

    def on_error(chave: str, exc: Exception) -> None:
        erros.append(f"{chave}: {exc}")

    pedacos = []
    for dia in DIAS:
        # pregao B3 do WDO: 09:00..18:25 BRT = 12:00..21:25 UTC. Folga dos
        # dois lados para nao cortar leilao de abertura/fechamento.
        inicio = pd.Timestamp(f"{dia} 10:00", tz="UTC").to_pydatetime()
        fim = pd.Timestamp(f"{dia} 22:30", tz="UTC").to_pydatetime()
        df = fetch_ticks_range(
            SIMBOLO_REAL, _limite_servidor(inicio), _limite_servidor(fim),
            on_error=on_error,
        )
        if df.empty:
            print(f"[tick] {dia}: VAZIO {erros[-1] if erros else ''}", flush=True)
            continue
        print(f"[tick] {dia}: {len(df):,} ticks  "
              f"{df.index.min()} -> {df.index.max()}  "
              f"last {df['last'].min()}..{df['last'].max()}", flush=True)
        pedacos.append(df)

    if not pedacos:
        print("[tick] nada baixado -- terminal indisponivel?")
        for e in erros:
            print("   ", e)
        return

    todo = pd.concat(pedacos).sort_index(kind="mergesort")
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    todo.to_parquet(DESTINO)
    print(f"\n[tick] {len(todo):,} ticks gravados em {DESTINO}")
    print(f"[tick] pregoes: {sorted(set(todo.index.date))}")
    if erros:
        print(f"[tick] {len(erros)} erro(s) durante a leitura:")
        for e in erros:
            print("   ", e)


if __name__ == "__main__":
    main()
