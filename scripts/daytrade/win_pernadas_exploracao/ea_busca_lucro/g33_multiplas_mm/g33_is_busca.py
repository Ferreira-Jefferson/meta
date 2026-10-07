# -*- coding: utf-8 -*-
"""IS (jan-jun/2026, 122 pregoes) da Geracao 33 -- 2 blocos:

(A) TIPO da media: sma/ema/wma, periodo 34 (igual a G29 pra EMA, so' troca
    o tipo) -- responde "faz diferenca mudar o tipo?".
(B) COMBINACAO de medias: 1 (so' 34, igual G29), 2 (34+68, 34+100), 3
    (34+68+100) -- sempre EMA (o tipo vencedor esperado do bloco A, ou o
    mesmo da G29 se o bloco A nao mudar nada) -- responde "exigir
    concordancia entre escalas ajuda?".

Referencia (G29, EMA34 so' fechamento): liquido R$2.805,50, n=467, win
38,8%, BEemp=33,8%, top3/liq=32,5%.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import g33_base as b  # noqa: E402


def avalia(dias_is, mms) -> dict:
    res, _ = b.roda(dias_is, mms=mms)
    trades = list(res.trades)
    c = b.consistencia(trades, dias_is)
    top5 = b.concentracao_topn(c["serie"], 5)
    pior_seq_n, pior_seq_brl = b.maior_sequencia_perdas(trades)
    ru = b.ruina_do_resultado(trades, pregoes_da_janela=len(dias_is))
    return dict(c=c, top5=top5, pior_seq_n=pior_seq_n, pior_seq_brl=pior_seq_brl, ru=ru)


def imprime(nome: str, r: dict) -> None:
    c = r["c"]
    print(f"{nome:20s} liquido={b.br(c['liquido']):>10s}  n={c['n']:4d}  "
          f"win={b.br(100*c['win'],1) if c['n'] else '--':>5s}%  "
          f"BEemp={b.br(100*c['be'],1) if c['be']==c['be'] else '--':>5s}%  "
          f"IC95=[{b.br(100*c['lo'],1)};{b.br(100*c['hi'],1)}]  "
          f"veredito={c['veredito']:10s}  "
          f"top3/liq={b.br(100*c['concentracao_top3'],1) if c['concentracao_top3']==c['concentracao_top3'] else '--':>6s}%  "
          f"top5/liq={b.br(100*r['top5'],1) if r['top5']==r['top5'] else '--':>6s}%  "
          f"p_ruina={b.br(100*r['ru']['p_ruina'],1) if r['ru']['p_ruina']==r['ru']['p_ruina'] else '--'}%",
          flush=True)


def main() -> None:
    win = b.carrega_win()
    dias_is = b.dias_da_janela(win, b.CORTE_IS_INICIO, b.CORTE_IS_FIM)
    print(f"IS (jan-jun/2026, {len(dias_is)} pregoes) -- geometria herdada da G21 "
          f"(stop={b.STOP_FRACAO}, alvo={b.ALVO_FRACAO})\n", flush=True)
    print(f"{'G29 referencia':20s} liquido={b.br(2805.50):>10s}  n= 467  win=38,8%  "
          f"BEemp=33,8%  veredito=POSITIVO    top3/liq= 32,5%  top5/liq= 49,4%\n")

    print("-- (A) tipo da media, periodo 34 --")
    for tipo in ("sma", "ema", "wma"):
        r = avalia(dias_is, mms=[(tipo, 34)])
        imprime(f"{tipo}34", r)

    print("\n-- (B) combinacao de medias (EMA) --")
    combos = {
        "ema34 (=G29)": [("ema", 34)],
        "ema34+68": [("ema", 34), ("ema", 68)],
        "ema34+100": [("ema", 34), ("ema", 100)],
        "ema34+68+100": [("ema", 34), ("ema", 68), ("ema", 100)],
    }
    for nome, mms in combos.items():
        r = avalia(dias_is, mms=mms)
        imprime(nome, r)


if __name__ == "__main__":
    main()
