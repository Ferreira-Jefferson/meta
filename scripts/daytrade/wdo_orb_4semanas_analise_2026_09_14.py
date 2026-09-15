"""ANALISE (2026-09-14) -- le a coleta das 4 semanas e escreve um arquivo por
recorte pedido pelo dono.

Entrada: `scratch/wdo_orb_4semanas_2026_09_14/0*.csv`
         (produzidos por `wdo_orb_4semanas_coleta_2026_09_14.py`)

Nenhum numero novo e' simulado aqui -- este script so' agrega o que ja' foi
medido. Cada recorte vira um CSV proprio, para o dono abrir um de cada vez.

## A decisao de metodo que governa tudo

As 4 semanas isoladas partem de R$375,00 e, em duas delas (S1 e S3), o caixa
cai abaixo da margem e o motor passa a RECUSAR ordem: 149 e 77 recusas por
capital. Uma janela em que o robo parou de operar esta' CENSURADA -- ela mede
a restricao que o calou, nao a estrategia (CLAUDE.md, item 6.15 de
LICOES_DE_PRODUCAO.md).

Por isso a populacao de analise e' a corrida CONTINUA de R$1.000 (CONT1K):
19 pregoes, 28 operacoes, ZERO recusas por capital, caixa minimo R$396,00 --
nunca perto da margem. E' a unica leitura das 4 semanas em que todo sinal que
apareceu virou operacao. As semanas a R$375 continuam no relatorio, mas num
recorte SEPARADO, que mede exatamente a censura.

## Aviso de tamanho de amostra

28 operacoes. Todo recorte por hora / dia da semana / faixa de volume cai
para baldes de 2 a 8 trades. Isso NAO decide nada -- a coluna `n` vai em
todas as tabelas de proposito, e o teste de sequencias (`14_sequencias.csv`)
existe justamente para medir se o padrao que a vista percebe sobrevive ao
acaso.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

DIR = RAIZ / "scratch" / "wdo_orb_4semanas_2026_09_14"
POP = "CONT1K"


def _le(nome: str) -> pd.DataFrame:
    return pd.read_csv(DIR / nome)


def _grava(nome: str, df: pd.DataFrame, titulo: str) -> None:
    df.to_csv(DIR / nome, index=False, encoding="utf-8")
    print(f"\n=== {titulo}  ({nome}) ===")
    print(df.to_string(index=False))


def _resumo(g: pd.DataFrame) -> pd.Series:
    pnl = g["pnl_brl"]
    ganhos, perdas = pnl[pnl > 0], pnl[pnl <= 0]
    return pd.Series({
        "n": len(g),
        "liquido": round(pnl.sum(), 2),
        "rs_por_op": round(pnl.mean(), 2),
        "win_pct": round(100.0 * len(ganhos) / len(g), 1) if len(g) else float("nan"),
        "ganho_medio": round(ganhos.mean(), 2) if len(ganhos) else float("nan"),
        "perda_media": round(perdas.mean(), 2) if len(perdas) else float("nan"),
        "melhor": round(pnl.max(), 2), "pior": round(pnl.min(), 2),
    })


# ---------------------------------------------------------------------------

def classifica_saida(row) -> str:
    """Como a operacao REALMENTE terminou.

    `exit_reason=target` esconde DUAS saidas muito diferentes: o alvo cheio
    (o preco pagou os `alvo_ticks` pedidos) e o CORTE DO RELOGIO -- 60 min
    depois da entrada a estrategia troca o alvo pelo preco corrente
    (`saida_limite_minutos=60`), e a saida continua carimbada como `target`.
    Sem separar os dois, uma saida de -R$30,50 entra na conta como se o robo
    tivesse batido o alvo."""
    if row["exit_reason"] == "stop":
        return "stop"
    if row["exit_reason"] != "target":
        return row["exit_reason"]
    if row["pnl_ticks"] >= row["alvo_ticks"] * 0.95:
        return "alvo_cheio"
    return "corte_relogio"


def teste_de_runs(seq: list[str]) -> dict:
    """Wald-Wolfowitz: a sequencia de G/P tem MENOS blocos (runs) do que o
    acaso produziria? Menos runs = resultados grudam em sequencias longas,
    que e' exatamente a "tendencia longa" que o dono descreve. Mais runs =
    alternancia. z proximo de 0 = indistinguivel de cara-ou-coroa."""
    n1 = sum(1 for x in seq if x == "G")
    n2 = sum(1 for x in seq if x == "P")
    n = n1 + n2
    if n1 == 0 or n2 == 0:
        return {"runs": 1, "esperado": float("nan"), "z": float("nan")}
    runs = 1 + sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    esperado = 1 + (2 * n1 * n2) / n
    var = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n * n * (n - 1))
    z = (runs - esperado) / math.sqrt(var) if var > 0 else float("nan")
    return {"runs": runs, "esperado": round(esperado, 2), "z": round(z, 2)}


def main() -> None:
    trades = _le("01_trades.csv")
    pregoes = _le("03_pregoes.csv")
    semanas = _le("04_semanas.csv")

    trades["saida_efetiva"] = trades.apply(classifica_saida, axis=1)
    trades.to_csv(DIR / "01_trades.csv", index=False, encoding="utf-8")

    t = trades[trades.janela == POP].reset_index(drop=True)
    p = pregoes[pregoes.janela == POP].reset_index(drop=True)

    print(f"POPULACAO DE ANALISE: {POP} -- {len(t)} operacoes em {len(p)} pregoes")

    # 10 -- semanas ---------------------------------------------------------
    t["semana"] = pd.to_datetime(t["data"]).dt.isocalendar().week
    rotulo = {34: "S1 17-21/08", 35: "S2 24-28/08", 36: "S3 31/08-04/09",
              37: "S4 08-11/09"}
    por_semana = t.groupby("semana").apply(_resumo, include_groups=False).reset_index()
    por_semana["janela"] = por_semana["semana"].map(rotulo)
    caixa_fim = t.groupby("semana")["caixa_depois"].last()
    por_semana["caixa_fim_semana"] = por_semana["semana"].map(caixa_fim)
    _grava("10_por_semana.csv",
           por_semana[["janela", "n", "liquido", "rs_por_op", "win_pct",
                        "ganho_medio", "perda_media", "melhor", "pior",
                        "caixa_fim_semana"]],
           "1) QUAIS SEMANAS PERDEM (corrida continua R$1.000)")

    # 11 -- pregoes ---------------------------------------------------------
    det = p[["data", "dia_semana", "n_ops", "pnl_brl", "faixa_ticks",
             "primeira_op", "primeira_op_tipo", "primeira_op_pnl", "recuperou",
             "seq_resultados", "caixa_fechamento", "ordens_sem_fill"]].copy()
    det = det.sort_values("pnl_brl")
    _grava("11_por_pregao.csv", det,
           "2) CADA PREGAO, do pior para o melhor")

    # 12 -- dia da semana ---------------------------------------------------
    dow = t.groupby("dia_semana").apply(_resumo, include_groups=False).reset_index()
    ordem = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4}
    dow = dow.sort_values("dia_semana", key=lambda s: s.map(ordem))
    _grava("12_por_dia_semana.csv", dow, "3) POR DIA DA SEMANA")

    # 13 -- qual operacao do dia perde --------------------------------------
    porop = t.groupby(["op_do_dia", "tipo"]).apply(_resumo, include_groups=False).reset_index()
    _grava("13_por_operacao_do_dia.csv", porop,
           "4) EM QUAL OPERACAO DO DIA AS PERDAS COMECAM")

    # 14 -- sequencias ------------------------------------------------------
    seq = list(t["resultado"])
    runs = teste_de_runs(seq)
    blocos = []
    atual, tamanho, ini = seq[0], 1, 0
    for i in range(1, len(seq)):
        if seq[i] == atual:
            tamanho += 1
        else:
            blocos.append((atual, tamanho, t.loc[ini, "data"], t.loc[i - 1, "data"],
                           round(t.loc[ini:i - 1, "pnl_brl"].sum(), 2)))
            atual, tamanho, ini = seq[i], 1, i
    blocos.append((atual, tamanho, t.loc[ini, "data"], t.loc[len(seq) - 1, "data"],
                   round(t.loc[ini:, "pnl_brl"].sum(), 2)))
    df_seq = pd.DataFrame(blocos, columns=["tipo", "tamanho", "de", "ate", "pnl_brl"])
    _grava("14_sequencias.csv", df_seq,
           f"5) SEQUENCIAS -- runs={runs['runs']} esperado por acaso="
           f"{runs['esperado']} z={runs['z']}")
    print(f"    [leitura] z negativo = sequencias MAIS longas que o acaso "
          f"(tendencia); |z|<1,96 = indistinguivel de cara-ou-coroa. z={runs['z']}")

    # 15 -- recuperacao -----------------------------------------------------
    comecou_perdendo = p[p.primeira_op == "P"]
    comecou_ganhando = p[p.primeira_op == "G"]
    rec = pd.DataFrame([
        {"abertura_do_dia": "perdeu a 1a", "n_pregoes": len(comecou_perdendo),
         "terminaram_positivos": int((comecou_perdendo.pnl_brl > 0).sum()),
         "pnl_medio_do_dia": round(comecou_perdendo.pnl_brl.mean(), 2) if len(comecou_perdendo) else float("nan"),
         "pnl_total": round(comecou_perdendo.pnl_brl.sum(), 2)},
        {"abertura_do_dia": "ganhou a 1a", "n_pregoes": len(comecou_ganhando),
         "terminaram_positivos": int((comecou_ganhando.pnl_brl > 0).sum()),
         "pnl_medio_do_dia": round(comecou_ganhando.pnl_brl.mean(), 2) if len(comecou_ganhando) else float("nan"),
         "pnl_total": round(comecou_ganhando.pnl_brl.sum(), 2)},
    ])
    _grava("15_recuperacao.csv", rec,
           "6) O DIA QUE COMECA PERDENDO, RECUPERA?")

    # 16 -- horario ---------------------------------------------------------
    hora = t.groupby("hora_entrada").apply(_resumo, include_groups=False).reset_index()
    _grava("16_por_horario.csv", hora, "7) POR HORARIO DE ENTRADA (BRT)")

    # 17 -- contexto de mercado ---------------------------------------------
    ctx_linhas = []
    for col, nome in [("vol_5min", "volume 5min antes"),
                      ("vol_15min", "volume 15min antes"),
                      ("amplitude_ticks_5min", "amplitude 5min (ticks)"),
                      ("amplitude_ticks_15min", "amplitude 15min (ticks)"),
                      ("nticks_5min", "negocios 5min (velocidade)"),
                      ("faixa_ticks", "faixa de abertura (ticks)")]:
        mediana = t[col].median()
        for rotulo_b, sub in [("<= mediana", t[t[col] <= mediana]),
                              ("> mediana", t[t[col] > mediana])]:
            if sub.empty:
                continue
            r = _resumo(sub)
            ctx_linhas.append({"variavel": nome, "corte": f"{rotulo_b} ({mediana:.0f})",
                                **r.to_dict()})
    _grava("17_contexto_mercado.csv", pd.DataFrame(ctx_linhas),
           "8) VOLUME / VOLATILIDADE NO MOMENTO DO SINAL")

    # 18 -- como a operacao termina de verdade ------------------------------
    saida = t.groupby("saida_efetiva").apply(_resumo, include_groups=False).reset_index()
    saida["pct_das_ops"] = (100.0 * saida["n"] / len(t)).round(1)
    _grava("18_saida_efetiva.csv", saida,
           "9) COMO A OPERACAO REALMENTE TERMINA (alvo cheio x corte de relogio x stop)")

    # 19 -- MFE/MAE ---------------------------------------------------------
    mm = t.groupby("resultado")[["mfe_ticks", "mae_ticks", "duracao_min",
                                  "atraso_fill_min"]].agg(["mean", "median", "max"]).round(1)
    mm.columns = ["_".join(c) for c in mm.columns]
    mm = mm.reset_index()
    _grava("19_excursao_mfe_mae.csv", mm,
           "10) QUANTO O TRADE ANDOU A FAVOR ANTES DE FECHAR (MFE/MAE em ticks)")

    # 20 -- drawdown da curva ------------------------------------------------
    eq = t[["data", "entrada_brt", "pnl_brl", "caixa_depois"]].copy()
    eq["pico"] = eq["caixa_depois"].cummax()
    eq["dd_brl"] = (eq["caixa_depois"] - eq["pico"]).round(2)
    eq["dd_pct"] = (100.0 * eq["dd_brl"] / eq["pico"]).round(1)
    _grava("20_drawdown.csv", eq, "11) A CAMINHADA DO CAIXA E O RECUO DO PICO")

    # 21 -- censura por capital (as 4 semanas a R$375) ----------------------
    cens = semanas[["janela", "capital_inicial", "pregoes", "trades", "ordens",
                    "ordens_sem_fill", "recusadas_capital", "pregoes_sem_trade",
                    "win_pct", "liquido_brl", "capital_final", "caixa_minimo"]].copy()
    cens["censurada"] = (cens["recusadas_capital"] > 0).map({True: "SIM", False: "nao"})
    _grava("21_censura_capital.csv", cens,
           "12) O QUE O CAPITAL DE R$375 FAZ COM A MEDICAO")

    # 22 -- direcao ----------------------------------------------------------
    lado = t.groupby("side").apply(_resumo, include_groups=False).reset_index()
    _grava("22_por_direcao.csv", lado, "13) COMPRA x VENDA")

    print(f"\n[analise] arquivos em {DIR}")


if __name__ == "__main__":
    main()
