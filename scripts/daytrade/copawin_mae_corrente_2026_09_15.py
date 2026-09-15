"""copa_win: a excursao adversa CORRENTE como gatilho de saida antecipada.

De onde veio: o diagnostico Q27 (`copawin_trajetoria_diagnostico_2026_09_15
.py`) achou uma separacao gigante e assimetrica entre vencedor e perdedor na
excursao ADVERSA maxima:

  alvo   (n=182): MAE mediana 0,09 do stop | so' 2 trades (1,1%) passaram de 0,50
  stop   (n= 58): MAE mediana 1,03 do stop | 100% passaram de 0,80 (por definicao)

E o Q23 achou que o stop e' morte por EROSAO, nao por impulso: mediana de 45
min para sofrer metade do stop e mais 51 min ate o stop cheio, com ZERO stops
resolvidos em ate 15 min. Ou seja, ha' TEMPO de agir.

O precedente do projeto (`wdo_orb_perfil_operacao_sem_preditor`) diz "so' o
MAE separa, e ele e' POS-RESULTADO". Isso vale para o MAE FINAL. O MAE
CORRENTE -- quanto ja' se sofreu ate agora -- e' conhecido a cada barra e
pode virar gatilho. E' essa a distincao que este script explora.

## O contrafactual

Para cada limiar `x` (fracao da distancia ate o stop): na PRIMEIRA barra em
que a excursao adversa acumulada cruza `x`, fecha a posicao A MERCADO pelo
fechamento daquela barra, pagando 1 tick de derrapagem + tarifa. Trades que
nunca cruzam `x` ficam com o desfecho original.

## As tres ressalvas que decidem se o numero vale

1. **Preenchimento otimista por construcao.** Sair "no fechamento da barra
   que cruzou" assume que se percebe o cruzamento e se executa dentro do
   mesmo minuto. Ao vivo a decisao so' pode ser tomada com a barra JA
   FECHADA, entao a execucao real cai na barra SEGUINTE. Por isso o script
   roda as duas convencoes (`mesma_barra` e `barra_seguinte`) e a honesta
   e' a segunda.
2. **O motor nao piramida.** Sair antes LIBERA o robo para entrar de novo no
   mesmo pregao -- ganho que este contrafactual NAO captura (ele so' encurta
   trades existentes, nunca cria novos). O efeito medido aqui e' portanto um
   PISO do efeito real.
3. **Gatilho de MAE e' quase a definicao de "esta' perdendo".** O nulo certo
   nao e' "melhor que nada", e' "melhor que o `corte_persistencia` que ja'
   esta' ligado em producao". Por isso a base PRODUCAO e' a primaria: o
   ganho medido e' o INCREMENTO sobre as regras que ja' existem.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "scratch"
LIMIARES = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
TICK_PTS = 5.0
PONTO_BRL = 0.20
TARIFA_BRL = 0.50
CORTE_OOS = pd.Timestamp("2026-06-13")


def br(x, casas=2):
    if pd.isna(x):
        return "-"
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def simula(tr, ba, x, atraso_barras):
    """Devolve o pnl por trade sob a regra 'sai ao cruzar x do stop'."""
    ba = ba.sort_values(["trade_id", "bar_idx"])
    cruz = ba[ba["exc_adversa_acum_frac_stop"] >= x]
    primeiro = cruz.groupby("trade_id").head(1).set_index("trade_id")
    saidas = {}
    for tid, linha in primeiro.iterrows():
        alvo_idx = linha["bar_idx"] + atraso_barras
        g = ba[(ba["trade_id"] == tid) & (ba["bar_idx"] == alvo_idx)]
        if g.empty:                       # a barra seguinte nao existe: trade ja' acabou
            continue
        saidas[tid] = float(g.iloc[0]["close"])
    out = []
    for _, t in tr.iterrows():
        tid = t["trade_id"]
        if tid in saidas:
            preco = saidas[tid]
            sinal = 1.0 if t["lado"] == "long" else -1.0
            bruto = (preco - t["entry_price"]) * sinal * PONTO_BRL * t["quantity"]
            custo = (TICK_PTS * PONTO_BRL + TARIFA_BRL) * t["quantity"]
            out.append(dict(trade_id=tid, pnl=bruto - custo, tocado=True,
                            era=t["exit_reason"], pnl_orig=t["pnl_brl"],
                            data=t["data"]))
        else:
            out.append(dict(trade_id=tid, pnl=t["pnl_brl"], tocado=False,
                            era=t["exit_reason"], pnl_orig=t["pnl_brl"],
                            data=t["data"]))
    return pd.DataFrame(out)


def relatorio(nome, tr, ba):
    tr = tr.copy()
    tr["data"] = pd.to_datetime(tr["data"])
    print("\n" + "=" * 112)
    print(f"BASE {nome} -- saida ao cruzar x% da distancia ate o STOP")
    print("=" * 112)
    print(f"  original: {len(tr)} trades, liquido R$ {br(tr['pnl_brl'].sum())}, "
          f"{int((tr['exit_reason'] == 'stop').sum())} stops")
    for atraso, rot in ((0, "mesma barra (OTIMISTA)"), (1, "barra seguinte (HONESTO)")):
        print(f"\n  --- execucao na {rot} ---")
        hdr = (f"{'limiar':>8}{'tocados':>9}{'venc. mortos':>14}{'perd. salvos':>14}"
               f"{'liquido R$':>14}{'delta R$':>12}{'IS delta':>12}{'OOS delta':>12}")
        print("  " + hdr)
        print("  " + "-" * len(hdr))
        for x in LIMIARES:
            r = simula(tr, ba, x, atraso)
            r["data"] = pd.to_datetime(r["data"])
            toc = r[r["tocado"]]
            mortos = int(((toc["era"] == "target") | (toc["pnl_orig"] > 0)).sum())
            salvos = int((toc["pnl_orig"] < 0).sum())
            delta = r["pnl"].sum() - tr["pnl_brl"].sum()
            dis = (r[r["data"] < CORTE_OOS]["pnl"].sum()
                   - tr[tr["data"] < CORTE_OOS]["pnl_brl"].sum())
            doos = (r[r["data"] >= CORTE_OOS]["pnl"].sum()
                    - tr[tr["data"] >= CORTE_OOS]["pnl_brl"].sum())
            print(f"  {br(100 * x, 0) + '%':>8}{len(toc):>9}{mortos:>14}{salvos:>14}"
                  f"{br(r['pnl'].sum()):>14}{br(delta):>12}{br(dis):>12}{br(doos):>12}")
    print("\n  'venc. mortos' = trades que davam lucro e a regra cortou. 'perd. salvos' = davam")
    print("  prejuizo e a regra cortou antes. Delta positivo no IS E no OOS e' o minimo para")
    print("  qualquer conversa; delta que so' aparece numa janela e' sign-flip, ja refutado 4x hoje.")


def main():
    for nome, (t, b) in {
        "PRODUCAO": ("copawin_trajetoria_trades_producao_2026_09_15.csv",
                     "copawin_trajetoria_barras_producao_2026_09_15.csv"),
        "LIVRE": ("copawin_trajetoria_trades_livre_2026_09_15.csv",
                  "copawin_trajetoria_barras_livre_2026_09_15.csv"),
    }.items():
        tr = pd.read_csv(SCRATCH / t)
        ba = pd.read_csv(SCRATCH / b)
        relatorio(nome, tr, ba)
    print("\n\nRESSALVAS: (1) o contrafactual so' ENCURTA trades, nunca cria os que a saida")
    print("antecipada liberaria -- e' um PISO. (2) Na base PRODUCAO o ganho e' o INCREMENTO")
    print("sobre `corte_persistencia`+`defesa`, que ja' estao ligados. (3) WIN@ sem fila")
    print("calibrada; saida a mercado paga 1 tick + tarifa, ja' embutidos.\n\nFIM.")


if __name__ == "__main__":
    main()
