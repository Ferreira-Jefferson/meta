# -*- coding: utf-8 -*-
"""Recoleta o tape do WIN@ PREGAO A PREGAO, com medida de cobertura.

Pedido do dono, 2026-09-11 ("faça isso"): regenerar a base de tick do WIN@
para destravar a calibracao de fila -- ver
`scripts/daytrade/win_fila_real_por_tape_2026_09_11.py`, que mede a curva de
preenchimento e hoje esta BLOQUEADO por buraco de dado.

O QUE ESTAVA ERRADO NA BASE. Amostra de 34 pregoes espalhados, comparada
minuto a minuto com a base M1: `data/raw_ticks/WIN_A_.parquet` cobre a
MEDIANA de **32,2%** dos minutos do pregao, com dias em 1%, 2% e 4%, e
NENHUM pregao acima de 37%. Dois tercos dos negocios nao estao la'.

POR QUE NAO DA' PARA USAR `backfill_ticks.py` AQUI, e este e' o motivo de
existir um script novo em vez de rodar o que ja havia. `fetch_ticks_full_
history` pagina `copy_ticks_from` desde 2000 e ACUMULA tudo em memoria antes
de gravar. Funciona para PMAM3 e para o WDO@; no WIN@ nao funciona --
medido nesta data: **17,3 GB de RAM** em ~7 minutos, com a maquina (31,7 GB)
chegando a 1,4 GB de RAM e 0,3 GB de swap livres. Teve de ser morto antes de
derrubar o terminal MT5 junto. A base original nunca chegou a ser tocada
(backup em `WIN_A_.parquet.bak-2026-09-11`).

Suspeita sobre a causa, registrada mas NAO confirmada: o WIN@ negocia
~24.955 contratos por minuto, e `_cursor_paginacao` avanca o cursor pela
parede do `time_msc` do ultimo tick da pagina. Num simbolo em que muitos
negocios dividem o mesmo milissegundo, a pagina seguinte pode reentregar o
mesmo bloco, e a deduplicacao so' acontece no `merge_ticks` do fim -- ou
seja, depois de tudo ja estar na memoria. Quem for consertar
`fetch_ticks_full_history` comeca por ai.

O DESENHO DAQUI, que evita o problema por construcao: uma requisicao
`copy_ticks_range` por PREGAO, um arquivo por pregao. O pico de memoria e' um
dia (~50-100 MB no WIN@), nunca o historico. Dia que ja foi coletado com
cobertura boa e' pulado, entao rodar de novo e' barato e retoma de onde
parou.

DUAS ARMADILHAS DO TERMINAL, as duas ja pagas neste repo e respeitadas aqui:

  1. FUSO. `copy_ticks_range` quer o relogio de PAREDE do servidor, tz-aware
     (`live/tick_feed.py::_limite_servidor`). Passar naive faz o pacote
     `MetaTrader5` resolver `.timestamp()` no fuso da MAQUINA e deslocar a
     janela inteira -- medido 2026-09-07: pedir naive 12:00 devolveu negocio
     de 15:00 de parede.
  2. `date_from` DENTRO do pregao devolve negocio incompleto ou zero (bug
     medido do terminal, ver `_SAFE_FETCH_LOOKBACK`). Por isso a janela pedida
     comeca a MEIA-NOITE UTC do proprio dia -- 21:00 BRT da vespera, bem fora
     da sessao -- e o recorte para o pregao e' feito DEPOIS, sobre o index ja
     convertido de volta para UTC de verdade por `mt5_ticks_source`.

A COBERTURA E' MEDIDA, NAO PRESUMIDA: cada dia coletado e' comparado contra a
contagem de minutos da base M1 do mesmo dia, e a linha sai com o percentual.
Um coletor que nao mede o que coletou reproduz exatamente o problema que ele
existe para resolver.

Uso:
    .venv/Scripts/python.exe -u scripts/daytrade/win_recoleta_tape_por_pregao_2026_09_11.py --dias 5
    .venv/Scripts/python.exe -u scripts/daytrade/win_recoleta_tape_por_pregao_2026_09_11.py --dias 60
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
DESTINO = ROOT / "data" / "raw_ticks" / "win_por_pregao"
MIN_BARRAS_POR_PREGAO = 400
#: Abaixo disto o dia e' considerado mal coletado e sera' tentado de novo na
#: proxima rodada. 90% e' folga deliberada: minuto sem NENHUM negocio existe
#: de verdade (leilao, congelamento), entao exigir 100% pediria o impossivel.
COBERTURA_BOA = 0.90


def br(v, dec=1):
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def main() -> None:
    from core.b3_session import utc_to_server_wall_clock
    from market_data_intraday.mt5_ticks_source import fetch_ticks_range
    from market_data_intraday.storage import load_m1

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dias", type=int, default=5,
                    help="quantos pregoes MAIS RECENTES coletar (default 5)")
    ap.add_argument("--refazer", action="store_true",
                    help="recoleta mesmo os dias que ja tem cobertura boa")
    args = ap.parse_args()

    DESTINO.mkdir(parents=True, exist_ok=True)

    m1 = load_m1(SYMBOL).sort_index()
    cont = m1.groupby(m1.index.date).size()
    dias = [d for d, n in cont.items() if n >= MIN_BARRAS_POR_PREGAO]
    alvo = sorted(dias)[-args.dias:]

    print("recoleta do tape do WIN@, um pregao por requisicao")
    print("destino: " + str(DESTINO.relative_to(ROOT)))
    print(str(len(alvo)) + " pregoes: " + str(alvo[0]) + " a " + str(alvo[-1]) + "\n",
          flush=True)

    def limite(instante_utc: datetime) -> datetime:
        """Relogio de PAREDE do servidor, rotulado UTC -- ver a armadilha 1."""
        return utc_to_server_wall_clock(instante_utc).replace(tzinfo=timezone.utc)

    hdr = ("pregao".ljust(13) + "ticks".rjust(11) + "min.tape".rjust(10)
           + "min.M1".rjust(9) + "cobertura".rjust(12) + "  situacao")
    print(hdr)
    print("-" * len(hdr), flush=True)

    resumo = []
    for d in alvo:
        destino = DESTINO / (SYMBOL.replace("@", "_A_") + str(d) + ".parquet")
        esperado = int(cont[d])
        if destino.exists() and not args.refazer:
            ja = pd.read_parquet(destino)
            cob = ja.index.floor("min").nunique() / esperado
            if cob >= COBERTURA_BOA:
                print(str(d).ljust(13) + str(len(ja)).rjust(11)
                      + str(ja.index.floor("min").nunique()).rjust(10)
                      + str(esperado).rjust(9)
                      + (br(100 * cob) + "%").rjust(12) + "  ja tinha", flush=True)
                resumo.append((d, cob))
                continue

        # Meia-noite UTC do proprio dia = 21:00 BRT da vespera, FORA da sessao
        # -- respeita a armadilha 2 sem precisar puxar um dia inteiro a mais.
        ini = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
        fim = ini + timedelta(days=1)
        erros: list = []
        df = fetch_ticks_range(SYMBOL, limite(ini), limite(fim),
                               on_error=lambda k, e: erros.append((k, e)))
        if df.empty:
            print(str(d).ljust(13) + "0".rjust(11) + "--".rjust(10)
                  + str(esperado).rjust(9) + "--".rjust(12)
                  + "  VAZIO" + (f" {erros}" if erros else ""), flush=True)
            resumo.append((d, 0.0))
            continue

        df = df[[x == d for x in df.index.date]].sort_index()
        minutos = df.index.floor("min").nunique() if len(df) else 0
        cob = minutos / esperado if esperado else 0.0
        if len(df):
            df.to_parquet(destino)
        print(str(d).ljust(13) + str(len(df)).rjust(11) + str(minutos).rjust(10)
              + str(esperado).rjust(9) + (br(100 * cob) + "%").rjust(12)
              + ("  ok" if cob >= COBERTURA_BOA else "  INCOMPLETO"), flush=True)
        resumo.append((d, cob))

    cobs = pd.Series([c for _, c in resumo])
    bons = int((cobs >= COBERTURA_BOA).sum())
    print("\n" + str(bons) + " de " + str(len(resumo)) + " pregoes com cobertura >= "
          + br(100 * COBERTURA_BOA, 0) + "%")
    print("cobertura mediana: " + br(100 * float(cobs.median())) + "%"
          + "   (a base antiga inteira dava 32,2%)")


if __name__ == "__main__":
    main()
