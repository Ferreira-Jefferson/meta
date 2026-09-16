# -*- coding: utf-8 -*-
"""Auditoria da base M1 canonica -- a base tem buraco? os dados estao certos?

Pergunta do dono (2026-09-16): "os nossos dados nao tem nenhum gap? todos os
dados estao corretamente preenchidos?".

Existe porque ja aconteceu: a base de TICK do WDO@ estava com **19,3% dos
negocios faltando** e ninguem sabia ate 2026-09-07 -- todo numero medido em
cima dela antes dessa data estava viciado. O M1 nunca passou por essa
conferencia, e todos os numeros do `win_retangulo` saem dele.

## O que e' conferido

1. **Dias de pregao faltando** -- dia util sem NENHUMA barra, contra o
   calendario da B3 (`core.b3_session`), ja descontando feriado.
2. **Buracos DENTRO do pregao** -- minutos ausentes entre a primeira e a
   ultima barra do dia. Separa buraco de 1 minuto (normal: minuto sem negocio)
   de buraco longo (suspeito: feed caiu).
3. **Carimbos duplicados** -- mesma barra duas vezes.
4. **Campos vazios** (NaN) e **valores impossiveis** (preco <= 0, volume < 0).
5. **Coerencia OHLC** -- `high >= max(open, close)`, `low <= min(open, close)`,
   `high >= low`. Uma barra que viola isso faz o motor preencher ordem-limite
   num preco que nunca existiu.
6. **Saltos de preco** entre barras consecutivas, que denunciam remendo de
   contrato (rolagem) ou barra de outro ativo.
7. **Cobertura da sessao** -- quantos minutos dos ~565 do pregao (09:00 a
   18:25 BRT) cada dia tem.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/auditoria_base_m1_2026_09_16.py`
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from market_data_intraday.storage import load_m1  # noqa: E402

SIMBOLOS = ("WIN@", "WDO@")
#: Pregao do WIN@/WDO@ em UTC: 12:00 (09:00 BRT) a 21:25 (18:25 BRT).
ABERTURA_UTC = pd.Timestamp("2000-01-01 12:00").time()
FECHAMENTO_UTC = pd.Timestamp("2000-01-01 21:25").time()


def br(v, dec=0):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def audita(simbolo: str) -> None:
    df = load_m1(simbolo).sort_index()
    print("=" * 120)
    print(f"{simbolo} — base M1 canônica")
    print("=" * 120)
    print(f"  {br(len(df))} barras | {df.index[0]} a {df.index[-1]}")

    # -- 3. carimbos duplicados -------------------------------------------
    dup = df.index.duplicated().sum()
    print(f"\n  [1] carimbos DUPLICADOS .......... {dup}")

    # -- 4. vazios e impossiveis ------------------------------------------
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    nans = {c: int(df[c].isna().sum()) for c in cols}
    print(f"  [2] campos VAZIOS (NaN) .......... {nans}")
    precos = [c for c in ("open", "high", "low", "close") if c in df.columns]
    nao_positivo = int((df[precos] <= 0).any(axis=1).sum())
    print(f"  [3] preço <= 0 ................... {nao_positivo}")
    if "volume" in df.columns:
        vol_neg = int((df["volume"] < 0).sum())
        vol_zero = int((df["volume"] == 0).sum())
        print(f"  [4] volume negativo .............. {vol_neg}")
        print(f"      volume ZERO (barra sem negócio) {vol_zero} "
              f"({br(100*vol_zero/len(df),2)}% das barras)")

    # -- 5. coerencia OHLC ------------------------------------------------
    if set(("open", "high", "low", "close")).issubset(df.columns):
        alto = df[["open", "close"]].max(axis=1)
        baixo = df[["open", "close"]].min(axis=1)
        viola_h = int((df["high"] < alto - 1e-9).sum())
        viola_l = int((df["low"] > baixo + 1e-9).sum())
        viola_hl = int((df["high"] < df["low"] - 1e-9).sum())
        print(f"  [5] high < max(open,close) ....... {viola_h}")
        print(f"      low  > min(open,close) ....... {viola_l}")
        print(f"      high < low ................... {viola_hl}")

    # -- 1/2. dias e buracos ----------------------------------------------
    por_dia = df.groupby(df.index.date)
    dias = sorted(por_dia.groups)
    uteis = pd.bdate_range(dias[0], dias[-1]).date
    sem_barra = [d for d in uteis if d not in set(dias)]
    print(f"\n  [6] dias ÚTEIS sem NENHUMA barra . {len(sem_barra)} "
          f"de {len(uteis)} (feriados da B3 entram aqui)")
    if sem_barra:
        print("      " + ", ".join(str(d) for d in sem_barra))

    # buracos dentro do pregao
    faltas = Counter()
    dias_com_buraco_longo = []
    cobertura = {}
    for d, g in por_dia:
        idx = g.index
        # so' o miolo: entre a primeira e a ultima barra DAQUELE dia
        esperado = pd.date_range(idx[0], idx[-1], freq="1min")
        faltando = esperado.difference(idx)
        cobertura[d] = len(idx)
        if len(faltando) == 0:
            continue
        # agrupa minutos ausentes em blocos contiguos
        blocos = []
        atual = [faltando[0]]
        for t in faltando[1:]:
            if (t - atual[-1]) == pd.Timedelta(minutes=1):
                atual.append(t)
            else:
                blocos.append(atual)
                atual = [t]
        blocos.append(atual)
        for b in blocos:
            faltas[len(b)] += 1
        maior = max(len(b) for b in blocos)
        if maior >= 10:
            dias_com_buraco_longo.append((d, maior, len(faltando)))

    total_blocos = sum(faltas.values())
    total_min = sum(k * v for k, v in faltas.items())
    print(f"\n  [7] BURACOS dentro do pregão (minuto sem barra, no miolo do dia)")
    print(f"      blocos: {br(total_blocos)} | minutos ausentes: {br(total_min)}")
    for tam in sorted(faltas):
        if tam <= 5 or faltas[tam] > 1:
            print(f"        bloco de {tam:>3} min: {faltas[tam]:>5} ocorrência(s)")
    print(f"      dias com buraco de 10+ min: {len(dias_com_buraco_longo)}")
    for d, maior, tot in sorted(dias_com_buraco_longo, key=lambda x: -x[1])[:10]:
        print(f"        {d}  maior buraco {maior} min, {tot} min ausentes no dia")

    # -- 7. cobertura da sessao -------------------------------------------
    serie = pd.Series(cobertura)
    print(f"\n  [8] COBERTURA por pregão (barras no dia)")
    print(f"      mediana {int(serie.median())} | p10 {int(serie.quantile(.10))} | "
          f"mínimo {int(serie.min())} | máximo {int(serie.max())}")
    curtos = serie[serie < 400].sort_values()
    print(f"      pregões com < 400 barras (excluídos de toda medição): {len(curtos)}")
    for d, n in curtos.items():
        print(f"        {d}: {n} barras")

    # primeira/ultima barra do dia -- o pregao comeca e termina onde devia?
    inicios = Counter()
    fins = Counter()
    for d, g in por_dia:
        inicios[g.index[0].time()] += 1
        fins[g.index[-1].time()] += 1
    print(f"\n  [9] PRIMEIRA barra do dia (UTC; esperado 12:00 = 09:00 BRT)")
    for t, n in inicios.most_common(5):
        print(f"        {t}  em {n} pregões")
    print(f"      ÚLTIMA barra do dia (UTC; esperado ~21:2x = ~18:2x BRT)")
    for t, n in fins.most_common(5):
        print(f"        {t}  em {n} pregões")

    # -- 6. saltos de preco -----------------------------------------------
    if "close" in df.columns:
        mesmo_dia = pd.Series(df.index.date, index=df.index).eq(
            pd.Series(df.index.date, index=df.index).shift())
        variacao = (df["close"] / df["close"].shift() - 1).abs()
        intradia = variacao[mesmo_dia.values & variacao.notna().values]
        grandes = intradia[intradia > 0.01]
        print(f"\n  [10] SALTOS intradiários > 1% entre barras consecutivas: {len(grandes)}")
        for ts, v in grandes.sort_values(ascending=False).head(5).items():
            print(f"        {ts}  {br(100*v,2)}%")
    print()


def main():
    for s in SIMBOLOS:
        audita(s)
    print("=" * 120)
    print("COMO LER")
    print("=" * 120)
    print("  * Bloco de 1 minuto ausente é NORMAL: minuto sem nenhum negócio não gera barra.")
    print("    O que denuncia feed caído é bloco LONGO (10+ min) em pregão de liquidez normal.")
    print("  * Dia útil sem barra nenhuma é feriado da B3 na maioria dos casos — confira a")
    print("    lista contra o calendário antes de chamar de falha.")
    print("  * Violação de OHLC é a mais grave: uma barra com `high < close` faz o motor")
    print("    preencher ordem-limite num preço que nunca existiu no livro.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
