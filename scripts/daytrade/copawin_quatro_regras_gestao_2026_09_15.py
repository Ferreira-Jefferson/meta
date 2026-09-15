"""copa_win: as QUATRO regras de gestao que sobreviveram ao teste do MAE.

De onde vieram. O limiar de MAE corrente (`copawin_mae_corrente_2026_09_15
.py`) falhou, e a decomposicao disse exatamente por que: a 50% da distancia
do stop, a regra salvava +R$13.500 nos stops e perdia R$13.950 em trades que
teriam se recuperado -- inclusive 15 saidas que eram LUCRATIVAS (+R$156/
trade) e viravam -R$202. Conclusao: **estar sofrendo nao e' estar condenado**,
e uma regra de DISTANCIA pura nao distingue os dois casos.

As quatro abaixo sao as candidatas do banco de perguntas que atacam
justamente essa distincao -- todas usam FORMA ou TEMPO do caminho, nao
distancia:

  R1 RECENCIA (Q6)    -- fracao adversa das ULTIMAS k barras, em vez do
     acumulado desde a entrada. O acumulado nunca esquece: um trade que
     sofreu no comeco e virou continua marcado. A recencia esquece.

  R2 ESTAGNACAO (Q13) -- minutos desde o ultimo NOVO MAXIMO de excursao
     favoravel, avaliado so' quando o trade ainda nao chegou perto do alvo.
     "Nao avanca ha 45 min" e' diferente de "esta' aberto ha 45 min" -- e a
     hazard plana do Q2 ja' refutou o time-stop puro.

  R3 DEVOLUCAO (Q10)  -- devolveu uma fracao `d` do proprio pico, exigindo
     pico minimo `m0`. E' trailing PROPORCIONAL ao lucro nao realizado; o
     `trail_vol` ja' refutado neste projeto era de distancia FIXA, que e'
     outra coisa.

  R4 CRUZAMENTOS (Q8) -- sair no N-esimo cruzamento do preco de ENTRADA.
     Poucos cruzamentos = caminho monotono = rompimento legitimo; muitos =
     indecisao em torno do nivel.

## Convencoes (iguais as do teste do MAE, para os numeros serem comparaveis)

- Base PRODUCAO: o ganho medido e' o INCREMENTO sobre `corte_persistencia` e
  `defesa`, que ja' estao ligados. E' o numero que interessa.
- Execucao na BARRA SEGUINTE ao gatilho (a decisao so' pode ser tomada com a
  barra ja' fechada). Saida a mercado: 1 tick de derrapagem + tarifa.
- Delta tem de ser positivo no IS **e** no OOS. So' no OOS e' sign-flip --
  cinco ja' apareceram hoje.
- O contrafactual so' ENCURTA trades, nunca cria os que a saida antecipada
  liberaria (o motor nao piramida). Todo delta aqui e' um PISO.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "scratch"
TICK_PTS, PONTO_BRL, TARIFA_BRL = 5.0, 0.20, 0.50
CORTE_OOS = pd.Timestamp("2026-06-13")


def br(x, casas=2):
    if pd.isna(x):
        return "-"
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def prepara(ba):
    """Colunas derivadas que as quatro regras precisam."""
    ba = ba.sort_values(["trade_id", "bar_idx"]).copy()
    g = ba.groupby("trade_id")
    # R1: fracao adversa das ultimas k barras
    for k in (10, 20):
        ba[f"adv_ult{k}"] = (g["lado_adverso_fechamento"]
                             .transform(lambda s: s.rolling(k, min_periods=k).mean()))
    # R2: minutos desde o ultimo novo maximo de excursao favoravel
    ba["mfe_corrente"] = g["exc_favoravel_acum_frac_alvo"].cummax()
    # "novo maximo" = a acumulada CRESCEU em relacao a barra anterior. Comparar
    # com o proprio cummax nao serve: `exc_favoravel_acum_frac_alvo` ja e'
    # monotonica por construcao, entao TODA barra empataria com o cummax e a
    # estagnacao daria 0 em todo lugar (bug pego na 1a rodada -- as 3 celulas
    # de R2 dispararam zero vezes).
    anterior = g["exc_favoravel_acum_frac_alvo"].shift(1)
    novo = (ba["exc_favoravel_acum_frac_alvo"] > anterior + 1e-12) | anterior.isna()
    ba["ts_novo_max"] = np.where(novo, ba["minutos_desde_entrada"], np.nan)
    ba["ts_novo_max"] = ba.groupby("trade_id")["ts_novo_max"].ffill()
    ba["estagnacao_min"] = ba["minutos_desde_entrada"] - ba["ts_novo_max"]
    # R3: devolucao em fracao do proprio pico
    pos_fav = ba["pos_fechamento_norm"].clip(lower=0.0)
    ba["devolucao_frac_pico"] = np.where(
        ba["mfe_corrente"] > 1e-9,
        (ba["mfe_corrente"] - pos_fav) / ba["mfe_corrente"].replace(0, np.nan), 0.0)
    return ba


def aplica(tr, ba, gatilho, atraso=1):
    """`gatilho`: serie booleana alinhada a `ba`. Sai na barra `atraso` apos
    a primeira True de cada trade."""
    marc = ba[gatilho.fillna(False)]
    if marc.empty:
        return tr.assign(pnl=tr["pnl_brl"], tocado=False)
    primeiro = marc.groupby("trade_id")["bar_idx"].min().rename("bar_gatilho")
    alvo = primeiro + atraso
    chave = ba.set_index(["trade_id", "bar_idx"])["close"]
    precos = {}
    for tid, bidx in alvo.items():
        if (tid, bidx) in chave.index:
            precos[tid] = float(chave.loc[(tid, bidx)])
    out = tr.copy()
    sinal = np.where(out["lado"] == "long", 1.0, -1.0)
    novo = out["trade_id"].map(precos)
    bruto = (novo - out["entry_price"]) * sinal * PONTO_BRL * out["quantity"]
    custo = (TICK_PTS * PONTO_BRL + TARIFA_BRL) * out["quantity"]
    out["tocado"] = novo.notna()
    out["pnl"] = np.where(out["tocado"], bruto - custo, out["pnl_brl"])
    return out


def linha(nome, tr, r):
    toc = r[r["tocado"]]
    mortos = int((toc["pnl_brl"] > 0).sum())
    salvos = int((toc["pnl_brl"] < 0).sum())
    d = r["pnl"].sum() - tr["pnl_brl"].sum()
    dis = (r[r["data"] < CORTE_OOS]["pnl"].sum()
           - tr[tr["data"] < CORTE_OOS]["pnl_brl"].sum())
    doos = (r[r["data"] >= CORTE_OOS]["pnl"].sum()
            - tr[tr["data"] >= CORTE_OOS]["pnl_brl"].sum())
    marca = "  <<< positivo nas DUAS" if (dis > 0 and doos > 0) else ""
    print(f"  {nome:<34}{len(toc):>8}{mortos:>8}{salvos:>8}"
          f"{br(r['pnl'].sum()):>13}{br(d):>11}{br(dis):>11}{br(doos):>11}{marca}")
    return dict(nome=nome, delta=d, dis=dis, doos=doos, r=r, tocados=len(toc))


def main():
    tr = pd.read_csv(SCRATCH / "copawin_trajetoria_trades_producao_2026_09_15.csv")
    ba = pd.read_csv(SCRATCH / "copawin_trajetoria_barras_producao_2026_09_15.csv")
    tr["data"] = pd.to_datetime(tr["data"])
    ba = prepara(ba)

    print("=" * 124)
    print("copa_win -- QUATRO REGRAS DE GESTAO (recencia, estagnacao, devolucao, cruzamentos)")
    print("=" * 124)
    print(f"base PRODUCAO: {len(tr)} trades, liquido R$ {br(tr['pnl_brl'].sum())}, "
          f"{int((tr['exit_reason'] == 'stop').sum())} stops")
    print("execucao na BARRA SEGUINTE ao gatilho, a mercado (1 tick + tarifa). "
          "Delta tem de ser > 0 no IS E no OOS.\n")
    hdr = (f"{'regra':<34}{'tocados':>8}{'v.mortos':>8}{'p.salvos':>8}"
           f"{'liquido':>13}{'delta':>11}{'IS':>11}{'OOS':>11}")
    print("  " + hdr)
    print("  " + "-" * len(hdr))

    res = []
    # R1 -- recencia
    for k in (10, 20):
        for f in (0.8, 1.0):
            g = ba[f"adv_ult{k}"] >= f - 1e-9
            res.append(linha(f"R1 recencia: {int(f*100)}% das ult. {k}", tr, aplica(tr, ba, g)))
    # R2 -- estagnacao (so' quando ainda longe do alvo)
    for s0 in (30, 45, 60):
        for fmax in (0.5,):
            g = (ba["estagnacao_min"] >= s0) & (ba["mfe_corrente"] < fmax)
            res.append(linha(f"R2 estagnacao {s0}min (MFE<{fmax})", tr, aplica(tr, ba, g)))
    # R3 -- devolucao proporcional ao pico
    for d in (0.5, 0.67):
        for m0 in (0.3, 0.5):
            g = (ba["devolucao_frac_pico"] >= d) & (ba["mfe_corrente"] >= m0)
            res.append(linha(f"R3 devolveu {int(d*100)}% do pico (>={m0})", tr, aplica(tr, ba, g)))
    # R4 -- N-esimo cruzamento do preco de entrada
    for n in (2, 3, 4):
        g = ba["cruzamentos_acumulados"] >= n
        res.append(linha(f"R4 {n}o cruzamento da entrada", tr, aplica(tr, ba, g)))

    ok = [r for r in res if r["dis"] > 0 and r["doos"] > 0]
    print("\n" + "=" * 124)
    if not ok:
        print("NENHUMA das 11 celulas e' positiva nas DUAS janelas.")
        melhor = max(res, key=lambda r: r["delta"])
        print(f"A menos ruim foi '{melhor['nome']}' (delta {br(melhor['delta'])}), "
              f"e ainda assim IS {br(melhor['dis'])} / OOS {br(melhor['doos'])}.")
    else:
        print(f"{len(ok)} celula(s) positiva(s) nas duas janelas -- decomposicao de cada uma:")
        for r in ok:
            toc = r["r"][r["r"]["tocado"]]
            g = toc.groupby("exit_reason").agg(n=("pnl", "size"), era=("pnl_brl", "sum"),
                                               vira=("pnl", "sum"))
            g["delta"] = g["vira"] - g["era"]
            print(f"\n  --- {r['nome']} (tocou {r['tocados']}) ---")
            print(g.round(2).to_string())
    print("\nRESSALVA: contrafactual so' encurta trades, nunca cria os que a saida liberaria")
    print("(o motor nao piramida) -- todo delta e' PISO. 11 celulas testadas: a 5% isso")
    print("produz ~0,5 positivo falso, entao um unico positivo isolado ainda e' suspeito.\n\nFIM.")


if __name__ == "__main__":
    main()
