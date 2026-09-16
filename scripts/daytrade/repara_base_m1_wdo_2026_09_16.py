# -*- coding: utf-8 -*-
"""Repara os pregoes TRUNCADOS da base M1 canonica do WDO@.

Achado da auditoria de 2026-09-16 (`auditoria_base_m1_2026_09_16.py`): tres
pregoes recentes do WDO@ estao mutilados na base canonica, e o terminal MT5
tem os tres COMPLETOS.

    dia         base canonica              terminal
    11/09    371 barras  12:00 -> 18:10    570 barras  12:00 -> 21:29
    14/09     67 barras  20:23 -> 21:29    570 barras  12:00 -> 21:29
    15/09    534 barras  12:00 -> 20:53    570 barras  12:00 -> 21:29

O 14/09 e' o pior: 67 de 570 barras, falta o pregao inteiro ate as 17:23 BRT.
A mediana da base e' 570 barras por pregao.

O WIN@ nao entra aqui -- a mesma auditoria mostrou a base dele integra (17
minutos ausentes em 110.014 barras, maior buraco de 6 minutos, zero violacao
de OHLC).

## O procedimento seguro (o mesmo de 2026-09-07)

BACKUP -> fetch novo -> COMPARA -> uniao -> confere. Nunca apagar.

A uniao usa `storage.merge_m1`, que ja tem a regra certa: em carimbo
sobreposto o fetch NOVO vence (correcao legitima do provedor vale), e barra
antiga ausente do fetch novo e' SEMPRE resgatada. Isso importa porque a
janela do servidor MT5 rola para frente -- hoje ela cobre 100.000 barras a
partir de 30/12/2025, enquanto o parquet guarda desde 08/12/2025. Uma barra
que saiu da janela pode ser a UNICA copia que existe dela.

Por isso NAO se regenera o parquet do zero: isso jogaria fora ~3 semanas de
historia que so' existem no nosso arquivo.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/repara_base_m1_wdo_2026_09_16.py`
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from dashboard.live_control import load_credentials  # noqa: E402
from market_data_intraday.mt5_source import fetch_m1_full_history  # noqa: E402
from market_data_intraday import storage  # noqa: E402

SIMBOLO = "WDO@"
SUSPEITOS = ("2026-09-11", "2026-09-14", "2026-09-15")


def br(v, dec=0):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _resumo(df: pd.DataFrame, dias=SUSPEITOS) -> None:
    for d in dias:
        g = df[df.index.date == pd.Timestamp(d).date()]
        if len(g):
            print(f"      {d}: {len(g):>4} barras  {g.index[0].time()} -> {g.index[-1].time()} UTC")
        else:
            print(f"      {d}: AUSENTE")


def main():
    caminho = storage._parquet_path(SIMBOLO)
    antes = storage.load_m1(SIMBOLO).sort_index()
    print("=" * 100)
    print(f"REPARO DA BASE M1 — {SIMBOLO}")
    print("=" * 100)
    print(f"  arquivo: {caminho}")
    print(f"  ANTES: {br(len(antes))} barras | {antes.index[0]} a {antes.index[-1]}")
    _resumo(antes)

    # -- 1. BACKUP --------------------------------------------------------
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = caminho.with_suffix(f".parquet.bak-{carimbo}")
    shutil.copy2(caminho, backup)
    print(f"\n  [1] BACKUP gravado: {backup.name} "
          f"({br(backup.stat().st_size / 1_048_576, 1)} MB)")

    # -- 2. FETCH ---------------------------------------------------------
    c = load_credentials()
    cred = dict(login=int(c["mt5_login"]), password=c["mt5_password"],
                server=c["mt5_server"], path=c["mt5_terminal_path"])
    erros: list = []
    novo = fetch_m1_full_history(SIMBOLO, on_error=lambda k, e: erros.append((k, str(e)[:120])),
                                 **cred)
    if erros:
        print(f"  [2] ERROS no fetch: {erros}")
    if novo.empty:
        print("  [2] fetch vazio — NADA foi alterado. Terminal fechado?")
        return
    print(f"  [2] FETCH do terminal: {br(len(novo))} barras | "
          f"{novo.index[0]} a {novo.index[-1]}")
    _resumo(novo)

    # -- 3. COMPARA -------------------------------------------------------
    so_no_parquet = antes.index.difference(novo.index)
    so_no_terminal = novo.index.difference(antes.index)
    comuns = antes.index.intersection(novo.index)
    print(f"\n  [3] COMPARAÇÃO")
    print(f"      só no parquet (fora da janela do servidor): {br(len(so_no_parquet))}")
    print(f"      só no terminal (o que vai entrar) .......: {br(len(so_no_terminal))}")
    print(f"      em comum ................................: {br(len(comuns))}")
    if len(comuns):
        cols = [x for x in ("open", "high", "low", "close") if x in antes.columns]
        difere = (antes.loc[comuns, cols] - novo.loc[comuns, cols]).abs().max().max()
        print(f"      maior divergência de preço nas barras comuns: {difere}")

    # -- 4. UNIÃO, SÓ NOS TRÊS DIAS ---------------------------------------
    # NUNCA a base inteira. `WDO@` e' contrato CONTINUO: a corretora
    # RE-ENCADEIA o historico a cada rolagem, entao o mesmo carimbo tem preco
    # diferente dependendo de QUANDO foi baixado. Medido nesta rodada: 93.159
    # das 107.242 barras comuns divergem, com deslocamento de ~37 a ~42 pontos,
    # e a fronteira e' a rolagem de 28/08 (de la' para ca' a divergencia e'
    # 0,000; antes dela, ~37,4). Unir a base inteira reescreveria oito meses de
    # preco com outro encadeamento e deixaria o arquivo EMENDADO -- pior que o
    # buraco que este script veio consertar. Os tres dias furados estao todos
    # depois da fronteira, entao so' eles entram.
    dias = {pd.Timestamp(d).date() for d in SUSPEITOS}
    recorte = novo[[d in dias for d in novo.index.date]]
    print("")
    print("  [4] recorte do fetch: " + br(len(recorte))
          + f" barras, só {SUSPEITOS}")
    depois, genuinamente_novas = storage.merge_m1(SIMBOLO, recorte)
    print(f"\n  [4] UNIÃO gravada (atômica). Linhas novas: {br(genuinamente_novas)}")

    # -- 5. CONFERE -------------------------------------------------------
    depois = storage.load_m1(SIMBOLO).sort_index()
    print(f"\n  [5] DEPOIS: {br(len(depois))} barras | {depois.index[0]} a {depois.index[-1]}")
    _resumo(depois)
    por_dia = depois.groupby(depois.index.date).size()
    curtos = por_dia[por_dia < 400]
    print(f"\n      pregões com < 400 barras agora: {len(curtos)}")
    for d, n in curtos.items():
        print(f"        {d}: {n} barras")
    print(f"      nenhuma barra antiga perdida: "
          f"{'SIM' if antes.index.isin(depois.index).all() else 'NÃO — INVESTIGAR'}")
    print("\nFIM.")


if __name__ == "__main__":
    main()
