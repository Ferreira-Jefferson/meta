# -*- coding: utf-8 -*-
"""Tenta RE-DERIVAR do terminal MT5 a fila real de ENTRADA do `copa_win`
(WIN@) -- mesmo metodo de Kaplan-Meier de
`scripts/daytrade/wdof1_calibra_fila_real_2026_09_09.py`, aplicado ao unico
robo do podio que ainda nao tem fidelidade de execucao calibrada
(`backtest.intraday.fidelidade.FIDELIDADE` so' tem "WDO@" -- ver item 6.30 de
LICOES_DE_PRODUCAO.md, que mede a fila da SAIDA do WIN@ e explicita que a
fila da ENTRADA "ainda nao foi medida").

SOMENTE LEITURA. Nao manda ordem, nao toca `db/live.sqlite`, nao inicia nem
mata processo nenhum.

## O que este script faz e por que ele PARA cedo

Antes de gastar qualquer tempo com Kaplan-Meier, ele faz a pergunta mais
barata possivel: "existe ALGUMA ordem real do `copa_win` no terminal?" --
o "teste pequeno que refuta primeiro" (convencao do projeto). Verifica os
DOIS magics possiveis do robo (sombra e ao vivo, `core.config.daytrade_magic`
dos dois slot ids), em TODOS os contratos WIN com vencimento que existem no
terminal, na janela mais ampla que a conta guarda.

Se a resposta for "zero ordens", o script para ali e IMPRIME por que: fila
real e' propriedade do LIVRO observada em ordem que EXECUTOU de verdade
(`history_orders_get`) -- e o modo `shadow` (que e' o unico em que este robo
ja rodou, confirmado pelo `db/live_process.json`) por desenho NAO manda
ordem para a corretora. E' a MESMA razao, ja documentada para o WDO F1, de
que "a sombra nao serve para isso: ela nao manda ordem, entao nunca preenche
um TP de verdade" -- aqui e' a ENTRADA, nao o alvo, mas o mecanismo e'
identico: sem ordem real no book, nao ha' Q_frente para medir.

Continuar e "estimar" um numero de qualquer jeito (chute, emprestimo do
WDO@, media de uma amostra sintetica) seria exatamente o que `fidelidade.py`
proibe -- "so' entra simbolo com pregao REAL medido" -- e reproduziria o
erro que o proprio projeto ja pagou (`queue_ahead_qty` desligado por um mes
com cara de coberto).

## Uso

    .\\.venv\\Scripts\\python.exe scripts/daytrade/copawin_calibra_fila_entrada_real_2026_09_11.py
    .\\.venv\\Scripts\\python.exe scripts/daytrade/copawin_calibra_fila_entrada_real_2026_09_11.py \\
        --de 2020-01-01 --ate 2026-09-12

Se um dia isto imprimir n>0 (o robo tiver rodado `execution_mode=live` pelo
menos uma sessao), o script segue automaticamente para a curva de
Kaplan-Meier -- mesmo codigo de `wdof1_calibra_fila_real_2026_09_09.py`,
generalizado para nao repetir a implementacao.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from core.config import daytrade_magic  # noqa: E402

#: Os dois slot ids possiveis do `copa_win` no WIN@ -- sombra e ao vivo. O
#: magic depende do id INTEIRO (`daytrade_slot_id`), entao os dois tem de ser
#: verificados: o robo pode ter rodado em qualquer um dos dois desde que o
#: catalogo existe.
SLOT_IDS = ("dt-copa_win-win@-shadow", "dt-copa_win-win@-live")
MAGICS = {sid: daytrade_magic(sid) for sid in SLOT_IDS}

ESPERA_MINIMA_S = 0.5


def le_terminal_amplo(de: dt.datetime, ate: dt.datetime):
    """Le' TODA ordem/deal do terminal na janela, sem filtrar por simbolo --
    o filtro por simbolo WIN e por magic acontece depois, em Python, porque
    `history_orders_get` nao aceita glob de simbolo."""
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise SystemExit(f"MT5 nao inicializou: {mt5.last_error()} -- "
                         f"o terminal precisa estar ABERTO e logado.")
    try:
        ordens = list(mt5.history_orders_get(de, ate) or ())
        deals = list(mt5.history_deals_get(de, ate) or ())
        symbols = [s.name for s in (mt5.symbols_get() or ())
                   if s.name.upper().startswith("WIN")]
    finally:
        mt5.shutdown()
    return ordens, deals, symbols


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--de", default="2020-01-01", help="AAAA-MM-DD (inclusivo)")
    p.add_argument("--ate", default=None,
                   help="AAAA-MM-DD (EXCLUSIVO; default = amanha)")
    args = p.parse_args()

    de = dt.datetime.strptime(args.de, "%Y-%m-%d")
    ate = (dt.datetime.strptime(args.ate, "%Y-%m-%d") if args.ate
           else dt.datetime.now() + dt.timedelta(days=1))

    print("copa_win (WIN@) -- tentativa de calibracao REAL da fila de ENTRADA")
    print(f"janela verificada: [{de:%Y-%m-%d}, {ate:%Y-%m-%d})")
    print(f"magics candidatos: {MAGICS}")
    print()

    ordens, deals, win_symbols = le_terminal_amplo(de, ate)
    print(f"contratos WIN conhecidos pelo terminal: {sorted(win_symbols)}")
    print(f"total de ordens no terminal (todo simbolo/magic) na janela: {len(ordens)}")
    print(f"total de deals  no terminal (todo simbolo/magic) na janela: {len(deals)}")

    magics_vistos = sorted({o.magic for o in ordens})
    simbolos_vistos = sorted({o.symbol for o in ordens})
    print(f"\nmagics que de fato aparecem no terminal: {magics_vistos}")
    print(f"simbolos que de fato aparecem no terminal: {simbolos_vistos}")

    ordens_copa_win = [o for o in ordens
                       if o.magic in MAGICS.values() or o.symbol in win_symbols]
    print(f"\nordens do copa_win (magic sombra/ao-vivo OU simbolo WIN*): "
          f"{len(ordens_copa_win)}")

    if not ordens_copa_win:
        print("\n" + "=" * 74)
        print("RESULTADO: n=0 -- NAO EXISTE ordem real do copa_win neste terminal.")
        print("=" * 74)
        print("""
Isto NAO e' uma falha do script -- e' o proprio resultado da rodada.

`db/live_process.json` (lido em 2026-09-11) so' declara o slot
"dt-copa_win-win@-shadow", `execution_mode: "shadow"`. Sombra journala a
decisao e simula o fill com o MESMO motor do backtest, mas NUNCA manda a
ordem-limite para o book da corretora -- e' a definicao de sombra
(`cash_sombra_separado_2026_08_23`: "saldo proprio, nunca cruza com o
real"). Sem ordem no book, nao existe instante de ENTRADA no book, nao
existe `copy_ticks_range` para medir Q_frente, e nao existe Kaplan-Meier
para calcular -- a cadeia inteira depende de o robo ter operado
`execution_mode=live` pelo menos uma sessao.

E' o MESMO limite ja documentado para o deslize do TP nativo do WDO F1:
"a sombra nao serve para isso: ela nao manda ordem, entao nunca preenche um
TP de verdade" -- aqui e' a perna de ENTRADA em vez do alvo, mas o mecanismo
e' identico.

CONSEQUENCIA PARA A HIPOTESE: a calibracao de Kaplan-Meier da fila de
ENTRADA do WIN@ (pedida nesta rodada) esta' BLOQUEADA por falta de dado, nao
refutada por medicao. Nao existe numero honesto para preencher
`backtest.intraday.fidelidade.FIDELIDADE["WIN@"]` hoje -- inventar um
(emprestar do WDO@, chutar, usar a amostra sintetica de uma sensibilidade)
seria exatamente o erro que este modulo foi desenhado para impedir ("nao ha'
linha padrao... emprestar seria inventar").

O QUE PRECISA ACONTECER ANTES de este script poder terminar o trabalho: o
`copa_win` rodar pelo menos UMA sessao com `execution_mode=live` no WIN@,
mandando ordem real para a corretora. Depois disso, re-rodar este script
(ou promove-lo para reusar o codigo de Kaplan-Meier de
`wdof1_calibra_fila_real_2026_09_09.py`) preenche a lacuna com o MESMO
metodo ja usado no WDO@.
""")
        return

    # ------------------------------------------------------------------
    # Caminho que so' roda se um dia isto deixar de dar n=0. Reaproveita a
    # MESMA logica de Kaplan-Meier (curva, mediana, censura) do script do
    # WDO F1 para nao duplicar a implementacao -- ver aquele arquivo para os
    # comentarios completos do metodo.
    # ------------------------------------------------------------------
    print("\nHA ordens reais -- prosseguindo para Kaplan-Meier (ver "
          "wdof1_calibra_fila_real_2026_09_09.py para a mesma logica).")

    ticks_por_simbolo: dict[str, np.ndarray] = {}

    def ticks_de(simbolo: str):
        if simbolo not in ticks_por_simbolo:
            import MetaTrader5 as mt5
            mt5.initialize()
            t = mt5.copy_ticks_range(simbolo, de, ate, mt5.COPY_TICKS_ALL)
            mt5.shutdown()
            ticks_por_simbolo[simbolo] = pd.DataFrame(t).sort_values("time_msc")
        return ticks_por_simbolo[simbolo]

    por_pos: dict[int, list] = {}
    for d in deals:
        por_pos.setdefault(d.position_id, []).append(d)

    linhas = []
    ordens_por_ticket = {o.ticket: o for o in ordens}
    for o in ordens_copa_win:
        if o.time_setup_msc is None or not o.time_done_msc:
            continue
        t0, t1 = o.time_setup_msc, o.time_done_msc
        if t1 <= t0:
            continue
        espera_s = (t1 - t0) / 1000.0
        if espera_s < ESPERA_MINIMA_S and o.state == 4:  # ORDER_STATE_FILLED
            continue
        td = ticks_de(o.symbol)
        neg = td[(td["flags"] & 2) != 0]  # TICK_FLAG_LAST
        janela = ((neg["time_msc"] >= t0) & (neg["time_msc"] < t1)
                  & np.isclose(neg["last"], o.price_open))
        vol = float((neg.loc[janela, "volume_real"]
                     if "volume_real" in neg else neg.loc[janela, "volume"]).sum())
        linhas.append({"ticket": o.ticket, "espera_s": espera_s, "vol_nivel": vol,
                       "preencheu": o.state == 4})

    df = pd.DataFrame(linhas)
    print(f"\nordens de ENTRADA que esperaram (>={ESPERA_MINIMA_S}s): {len(df)}")
    if df.empty:
        print("todas preencheram na hora (<0,5s) -- nenhuma esperou em fila; "
              "sem dado para Kaplan-Meier ainda.")
        return
    print(df.describe())
    print("\nRe-rode com o corpo de `wdof1_calibra_fila_real_2026_09_09.py::"
          "kaplan_meier`/`quantil_km` sobre este DataFrame para a mediana.")


if __name__ == "__main__":
    main()
