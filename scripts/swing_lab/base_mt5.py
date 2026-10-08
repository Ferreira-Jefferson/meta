"""Base diaria do MT5 para o laboratorio de swing, dividida em IS / OOS / VALIDACAO.

Decisao do dono, 2026-10-08: toda analise de melhoria da estrategia semanal usa
SO o diario do MT5 (Rico). O yfinance fica para depois, como teste de periodo
longo, quando tudo ja estiver validado aqui.

POR QUE O MT5. Ja vem ajustado por proventos e, nos 188 papeis conferidos, nao
tem os saltos falsos do yfinance (AZEV3 de R$0,00015 para R$328 num dia,
FRAS3/UGPA3/PCAR3 com 2-3x em um pregao). Limite: o servidor so entrega 5 anos
(D1, W1 e MN1 comecam todos em 08/10/2021). Por isso `exportar` MESCLA com o que
ja esta salvo: a janela do servidor anda um dia por pregao e o comeco da base
nao pode sumir junto.

A DIVISAO (pela data de ENTRADA da operacao):
  IS        2/3 dos papeis  2022-10-01 a 2025-09-30   escolher e ajustar regra
  OOS       1/3 dos papeis  2022-10-01 a 2025-09-30   conferir o que o IS escolheu
  VALIDACAO todos os papeis 2025-10-01 em diante      confirmacao final; so com autorizacao do dono
O comeco em out/2022 vem do aquecimento: a MME50 semanal precisa de 50 semanas.

POR QUE IS/OOS POR PAPEL E A VALIDACAO POR TEMPO. Medido em 2026-10-08: dividir
o tempo em blocos embaralhados vaza, porque a operacao dura meses (mediana ~45
dias, a mais longa 1.099 dias) e atravessa os blocos dos outros conjuntos
(66% das operacoes com blocos de 1 mes, 31% com blocos de 6). Encerrar a
operacao na borda do bloco tambem nao serve: as operacoes acima de 180 dias
somam mais que todo o lucro da estrategia. Dividindo IS e OOS por papel, os dois
passam pelos mesmos regimes de mercado e nenhuma operacao cruza de um para o
outro. O ponto fraco disso (papeis andam juntos com o mercado; uma regra que so
funcionou num regime passa nos dois) e o que a VALIDACAO cobre: ela e fora do
tempo, todos os papeis num periodo que nenhuma escolha viu.

A TRAVA. `carregar(tk, "validacao")` levanta erro sem `autorizacao="<motivo>"`,
e cada destrave fica registrado em `VALIDACAO_LOG.md`. Documentado e opcional,
estrutural nao e (mesmo principio de `backtest.intraday.frozen_split`).

SEM OLHAR O FUTURO. IS e OOS cortam o diario em 2025-09-30: uma operacao ainda
aberta ali e marcada no ultimo fechamento e nao enxerga preco da VALIDACAO.

CONTAMINACAO JA CONHECIDA. Em 2026-10-08, antes desta divisao, varias medicoes
rodaram sobre a janela inteira do MT5 (out/22-out/26) com todos os papeis,
inclusive o achado de que o recuo de verdade rende menos que as reversoes. Para
essas perguntas nenhum conjunto e virgem; para as proximas, sim.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PASTA = ROOT / "data" / "mt5_d1"
UNIVERSO = Path(__file__).with_name("universo_b3_2026_10_08.json")
GRUPOS = Path(__file__).with_name("grupos_is_oos_2026_10_08.json")
LOG = Path(__file__).with_name("VALIDACAO_LOG.md")

PESQUISA = ("2022-10-01", "2025-09-30")
VALIDACAO = ("2025-10-01", "2099-12-31")
SEMENTE = 20261008
DECLARADO_EM = "2026-10-08"


def universo() -> list[tuple[str, str]]:
    """Os 187 papeis (ticker, setor) da grade semanal, congelados em 2026-10-08.
    Escolhidos com a liquidez DE HOJE: entra so quem sobreviveu e e liquido
    agora, o que favorece estrategia comprada nos tres conjuntos."""
    return [tuple(x) for x in json.loads(UNIVERSO.read_text(encoding="utf-8"))]


def sortear_grupos() -> dict[str, str]:
    """Sorteio UNICO de 2/3 IS e 1/3 OOS, equilibrado por setor e liquidez:
    dentro de cada setor, papeis ordenados pela mediana do financeiro diario
    no periodo de pesquisa e repartidos em trincas (2 IS, 1 OOS, ordem
    sorteada). Grava em GRUPOS e nunca refaz se o arquivo ja existir."""
    if GRUPOS.exists():
        raise FileExistsError(f"{GRUPOS.name} ja existe; o sorteio e feito uma vez so")
    rng = np.random.default_rng(SEMENTE)
    por_setor: dict[str, list[tuple[float, str]]] = {}
    for tk, setor in universo():
        d = pd.read_parquet(PASTA / f"{tk}.parquet").loc[PESQUISA[0]:PESQUISA[1]]
        fin = float((d["close"] * d["volume"]).median()) if len(d) else 0.0
        por_setor.setdefault(setor, []).append((fin, tk))
    grupos: dict[str, str] = {}
    for setor in sorted(por_setor):
        lista = [tk for _, tk in sorted(por_setor[setor], reverse=True)]
        for i in range(0, len(lista), 3):
            trinca = lista[i:i + 3]
            rotulos = list(rng.permutation(["is", "is", "oos"]))[:len(trinca)]
            grupos.update(zip(trinca, rotulos))
    GRUPOS.write_text(json.dumps({"semente": SEMENTE, "declarado_em": DECLARADO_EM, "grupos": grupos},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    return grupos


def papeis(conjunto: str) -> list[str]:
    """Papeis de um conjunto. A VALIDACAO usa todos."""
    if conjunto == "validacao":
        return [tk for tk, _ in universo()]
    g = json.loads(GRUPOS.read_text(encoding="utf-8"))["grupos"]
    return [tk for tk, c in g.items() if c == conjunto]


def janela(conjunto: str) -> tuple[str, str]:
    """Intervalo das datas de ENTRADA do conjunto."""
    return VALIDACAO if conjunto == "validacao" else PESQUISA


def exportar(tickers: list[str] | None = None) -> dict[str, str]:
    """Baixa o D1 do terminal e mescla com o salvo (o salvo vence nas datas
    antigas que o servidor ja nao entrega). Retorna {ticker: erro}."""
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f"MT5 nao inicializou: {mt5.last_error()}")
    PASTA.mkdir(parents=True, exist_ok=True)
    falhas: dict[str, str] = {}
    try:
        for tk in tickers or [t for t, _ in universo()]:
            mt5.symbol_select(tk, True)
            r = mt5.copy_rates_range(tk, mt5.TIMEFRAME_D1, datetime(2000, 1, 1), datetime.now())
            if r is None or len(r) == 0:
                falhas[tk] = str(mt5.last_error())
                continue
            novo = pd.DataFrame(r)
            novo.index = pd.DatetimeIndex(pd.to_datetime(novo["time"], unit="s")).normalize()
            novo.index.name = "date"
            novo = novo[["open", "high", "low", "close", "real_volume"]].rename(columns={"real_volume": "volume"})
            novo["adj_close"] = novo["close"]  # o MT5 da Rico ja entrega ajustado por proventos
            p = PASTA / f"{tk}.parquet"
            if p.exists():
                velho = pd.read_parquet(p)
                novo = pd.concat([velho[velho.index < novo.index[0]], novo])
            novo.to_parquet(p)
            print(f"  {tk:7s} {len(novo):5d} pregoes {novo.index[0].date()} a {novo.index[-1].date()}", flush=True)
    finally:
        mt5.shutdown()
    return falhas


def carregar(tk: str, conjunto: str, autorizacao: str | None = None) -> pd.DataFrame:
    """Diario de `tk` para o `conjunto`. IS/OOS: so papeis do grupo, cortado
    no fim do periodo de pesquisa. VALIDACAO: exige `autorizacao` com o
    motivo, que vai para o log."""
    if conjunto == "validacao":
        if not (autorizacao and autorizacao.strip()):
            raise PermissionError(
                "conjunto de VALIDACAO travado: so com autorizacao do dono. "
                "Passe autorizacao='<motivo e quem autorizou>'."
            )
        _registrar(autorizacao)
        return pd.read_parquet(PASTA / f"{tk}.parquet")
    if conjunto not in ("is", "oos"):
        raise ValueError(f"conjunto desconhecido: {conjunto!r} (use 'is', 'oos' ou 'validacao')")
    if tk not in papeis(conjunto):
        raise ValueError(f"{tk} nao pertence ao conjunto {conjunto.upper()}")
    return pd.read_parquet(PASTA / f"{tk}.parquet").loc[: PESQUISA[1]]


_registrados: set[str] = set()


def _registrar(motivo: str) -> None:
    """Uma linha por motivo por processo (nao uma por papel)."""
    if motivo in _registrados:
        return
    _registrados.add(motivo)
    if not LOG.exists():
        LOG.write_text("# Destraves do conjunto de VALIDACAO\n\n| quando | motivo |\n|---|---|\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"| {datetime.now():%Y-%m-%d %H:%M} | {motivo.replace('|', '/')} |\n")


if __name__ == "__main__":
    f = exportar()
    print(f"falhas: {f}" if f else "ok")
