"""copa_win: os tres diagnosticos BARATOS que decidem se o banco de
perguntas de trajetoria tem onde existir.

Sao as perguntas Q27, Q23 e Q2 do banco gerado em 2026-09-15. Ficaram na
frente de todas as outras de proposito: elas nao geram regra nenhuma, mas
dizem se as regras das outras 27 perguntas PODEM existir. Rodar isso antes
evita gastar o banco inteiro num espaco vazio.

  Q27 (mapa MAE x MFE)  -- quantos dos stops chegaram perto do alvo antes de
      morrer, e quantos dos alvos sofreram quase o stop inteiro antes de
      pagar? Se quase nenhum stop chegou perto do alvo, toda regra de
      "proteger lucro" e' irrelevante por falta de populacao. Se muitos
      alvos sofreram quase tudo, qualquer corte agressivo mata vencedor.

  Q23 (modo de morte)   -- o stop vem por IMPULSO (rapido) ou por EROSAO
      (lento)? Se e' impulso, nenhuma regra baseada em barra M1 chega a
      tempo, e o banco inteiro deve ser lido com expectativa menor.

  Q2  (forma da hazard) -- a taxa instantanea de cada desfecho cresce ou
      decai com o tempo de posicao aberta? Decrescente para o stop => quem
      sobreviveu esta' mais seguro, e nenhum time-stop pode funcionar.
      Crescente => existe prazo a partir do qual segurar e' negativo.

Mais a comparacao AGREGADA producao x trajetoria livre, que e' a unica
comparacao valida entre as duas bases (elas nao sao casaveis trade a trade:
desligar as saidas muda a propria sequencia de entradas -- ver a ressalva 4
do construtor da base).

TUDO AQUI E' DIAGNOSTICO E RETROSPECTIVO. Nenhuma coluna usada abaixo esta'
disponivel no instante de decidir; `frac_duracao_decorrida` e MFE/MAE FINAIS
sao pos-resultado por construcao. Servem para calibrar a expectativa do
banco, nunca para gerar gatilho -- foi exatamente a forma "fracao da duracao
eventual" que ja produziu neste projeto um achado de 84,4% que nao existia
ao vivo.

Fonte: os 4 CSVs de `copawin_trajetoria_barra_a_barra_2026_09_15.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "scratch"
BASES = {
    "PRODUCAO": ("copawin_trajetoria_trades_producao_2026_09_15.csv",
                 "copawin_trajetoria_barras_producao_2026_09_15.csv"),
    "LIVRE": ("copawin_trajetoria_trades_livre_2026_09_15.csv",
              "copawin_trajetoria_barras_livre_2026_09_15.csv"),
}
MARCOS = [5, 10, 15, 20, 30, 45, 60, 90, 120]


def br(x, casas=2):
    if pd.isna(x):
        return "-"
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def carrega(nome):
    t, b = BASES[nome]
    tr = pd.read_csv(SCRATCH / t, parse_dates=["entry_ts", "exit_ts"])
    ba = pd.read_csv(SCRATCH / b, parse_dates=["ts"])
    return tr, ba


def extremos(ba):
    """MFE e MAE FINAIS por trade, em fracao do alvo / do stop."""
    g = ba.groupby("trade_id")
    return pd.DataFrame({
        "mfe_frac_alvo": g["exc_favoravel_acum_frac_alvo"].max(),
        "mae_frac_stop": g["exc_adversa_acum_frac_stop"].max(),
        "barras": g["bar_idx"].max() + 1,
    })


def q27(tr, ba, nome):
    print("\n" + "=" * 100)
    print(f"Q27 -- MAPA MAE x MFE por desfecho  [{nome}]  (DIAGNOSTICO, pos-resultado)")
    print("=" * 100)
    d = tr.set_index("trade_id").join(extremos(ba))
    hdr = (f"{'desfecho':<16}{'n':>5}{'MFE med':>10}{'MFE p75':>10}"
           f"{'MAE med':>10}{'MAE p75':>10}{'>=80% alvo':>12}{'>=80% stop':>12}")
    print(hdr)
    print("-" * len(hdr))
    for motivo, g in d.groupby("exit_reason"):
        print(f"{motivo:<16}{len(g):>5}"
              f"{br(g['mfe_frac_alvo'].median()):>10}{br(g['mfe_frac_alvo'].quantile(.75)):>10}"
              f"{br(g['mae_frac_stop'].median()):>10}{br(g['mae_frac_stop'].quantile(.75)):>10}"
              f"{br(100 * (g['mfe_frac_alvo'] >= 0.8).mean(), 1) + '%':>12}"
              f"{br(100 * (g['mae_frac_stop'] >= 0.8).mean(), 1) + '%':>12}")
    st = d[d["exit_reason"] == "stop"]
    al = d[d["exit_reason"] == "target"]
    print(f"\n  LEITURA-CHAVE:")
    print(f"    dos {len(st)} STOPS, {int((st['mfe_frac_alvo'] >= 0.5).sum())} "
          f"({br(100 * (st['mfe_frac_alvo'] >= 0.5).mean(), 1)}%) chegaram a >=50% do alvo antes de morrer")
    print(f"      -> e' a POPULACAO de qualquer regra de 'proteger lucro'. Pequena = regra irrelevante.")
    print(f"    dos {len(al)} ALVOS, {int((al['mae_frac_stop'] >= 0.5).sum())} "
          f"({br(100 * (al['mae_frac_stop'] >= 0.5).mean(), 1)}%) sofreram >=50% do stop antes de pagar")
    print(f"      -> e' quem um corte agressivo MATARIA. Grande = corte agressivo destroi vencedor.")


def q23(tr, ba, nome):
    print("\n" + "=" * 100)
    print(f"Q23 -- MODO DE MORTE do stop: impulso ou erosao?  [{nome}]  (DIAGNOSTICO)")
    print("=" * 100)
    stops = tr[tr["exit_reason"] == "stop"]["trade_id"]
    b = ba[ba["trade_id"].isin(stops)]
    linhas = []
    for tid, g in b.groupby("trade_id"):
        g = g.sort_values("bar_idx")
        meio = g[g["exc_adversa_acum_frac_stop"] >= 0.5]["minutos_desde_entrada"]
        fim = g["minutos_desde_entrada"].max()
        ult = g.tail(1).iloc[0]
        linhas.append(dict(
            trade_id=tid,
            t_meio=(meio.iloc[0] if len(meio) else np.nan),
            t_total=fim,
            range_barra_do_stop=ult["high"] - ult["low"],
        ))
    s = pd.DataFrame(linhas)
    s["t_segunda_metade"] = s["t_total"] - s["t_meio"]
    print(f"  n={len(s)} stops")
    for col, rot in (("t_meio", "minutos ate sofrer METADE do stop"),
                     ("t_segunda_metade", "minutos da metade ate o stop cheio"),
                     ("t_total", "duracao total do trade (min)")):
        v = s[col].dropna()
        print(f"    {rot:<38} mediana {br(v.median(), 1):>7}  media {br(v.mean(), 1):>7}  "
              f"p25 {br(v.quantile(.25), 1):>7}  p75 {br(v.quantile(.75), 1):>7}  n={len(v)}")
    rapidos = (s["t_total"] <= 15).mean()
    print(f"\n  stops resolvidos em <=15 min: {br(100 * rapidos, 1)}%  "
          f"| em <=30 min: {br(100 * (s['t_total'] <= 30).mean(), 1)}%")
    print("    -> fracao alta = MORTE POR IMPULSO: nenhuma regra em barra M1 chega a tempo.")


def q2(tr, ba, nome):
    print("\n" + "=" * 100)
    print(f"Q2 -- HAZARD por marco de tempo  [{nome}]  (risco concorrente)")
    print("=" * 100)
    dur = ba.groupby("trade_id")["minutos_desde_entrada"].max().rename("dur")
    d = tr.set_index("trade_id").join(dur)
    hdr = (f"{'marco':>7}{'coorte':>9}" + "".join(f"{m[:9]:>11}" for m in
           ["alvo", "stop", "sinal", "achatam."]) + f"{'  (% da coorte que morre nos 5 min seguintes)':<10}")
    print(hdr)
    print("-" * 78)
    mapa = {"target": "alvo", "stop": "stop", "signal": "sinal", "forced_flatten": "achatam."}
    for m in MARCOS:
        coorte = d[d["dur"] >= m]
        if len(coorte) < 10:
            continue
        janela = coorte[(coorte["dur"] >= m) & (coorte["dur"] < m + 5)]
        linha = f"{m:>6}m{len(coorte):>9}"
        for motivo in ["target", "stop", "signal", "forced_flatten"]:
            q = (janela["exit_reason"] == motivo).sum()
            linha += f"{br(100 * q / len(coorte), 2) + '%':>11}"
        print(linha)
    print("\n  hazard do STOP decrescente => quem sobreviveu esta' mais seguro; time-stop nao pode funcionar.")
    print("  hazard do STOP crescente  => existe prazo a partir do qual segurar e' negativo.")


def comparacao(trA, trB):
    print("\n" + "=" * 100)
    print("PRODUCAO x TRAJETORIA LIVRE -- comparacao AGREGADA (a unica valida entre as bases)")
    print("=" * 100)
    hdr = f"{'base':<12}{'trades':>8}{'liquido R$':>14}{'R$/trade':>11}{'dur. mediana':>14}"
    print(hdr)
    print("-" * len(hdr))
    for nome, t in (("PRODUCAO", trA), ("LIVRE", trB)):
        print(f"{nome:<12}{len(t):>8}{br(t['pnl_brl'].sum()):>14}"
              f"{br(t['pnl_brl'].mean()):>11}{br(t['duracao_min'].median(), 1):>14}")
    print("\n  por motivo de saida:")
    hdr2 = f"{'motivo':<18}{'A: n':>7}{'A: R$':>13}{'A: R$/tr':>11}{'B: n':>7}{'B: R$':>13}{'B: R$/tr':>11}"
    print("  " + hdr2)
    print("  " + "-" * len(hdr2))
    for motivo in ["target", "stop", "signal", "forced_flatten"]:
        a = trA[trA["exit_reason"] == motivo]
        b = trB[trB["exit_reason"] == motivo]
        print(f"  {motivo:<18}{len(a):>7}{br(a['pnl_brl'].sum()):>13}"
              f"{br(a['pnl_brl'].mean()) if len(a) else '-':>11}"
              f"{len(b):>7}{br(b['pnl_brl'].sum()):>13}"
              f"{br(b['pnl_brl'].mean()) if len(b) else '-':>11}")
    print("\n  CUIDADO: as duas bases NAO sao casaveis trade a trade -- desligar as saidas muda a")
    print("  sequencia de entradas (posicao que vive mais bloqueia o sinal seguinte). A diferenca")
    print("  de liquido mistura 'as saidas valiam a pena' com 'o robo operou menos vezes'.")


def main():
    for f in BASES.values():
        for x in f:
            if not (SCRATCH / x).exists():
                sys.exit(f"faltando {SCRATCH / x}")
    trA, baA = carrega("PRODUCAO")
    trB, baB = carrega("LIVRE")
    print("=" * 100)
    print("copa_win -- DIAGNOSTICOS DE TRAJETORIA (Q27, Q23, Q2 do banco) + producao x livre")
    print("=" * 100)
    print(f"BASE PRODUCAO: {len(trA)} trades / {len(baA):,} barras".replace(",", "."))
    print(f"BASE LIVRE   : {len(trB)} trades / {len(baB):,} barras".replace(",", "."))
    comparacao(trA, trB)
    for nome, tr, ba in (("PRODUCAO", trA, baA), ("LIVRE", trB, baB)):
        q27(tr, ba, nome)
        q23(tr, ba, nome)
        q2(tr, ba, nome)
    print("\n\nFIM.")


if __name__ == "__main__":
    main()
