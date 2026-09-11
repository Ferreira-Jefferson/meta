# -*- coding: utf-8 -*-
"""O que "GANHAR POUCO, MAS SEMPRE" quer dizer em numero -- linha de base.

Pedido do dono, 2026-09-11: "descubra como fazer essa estrategia se tornar
ganhadora mesmo que pouco, mas constante".

ESTE SCRIPT NAO BUSCA NADA. Ele faz a coisa que tem de vir antes da busca:
DECLARAR a funcao objetivo e medir onde a producao esta' nela hoje. Sem isso
a varredura seguinte reotimizaria `liquido R$` -- que e' exatamente a metrica
que produziu o robo atual, o que ganha muito e perde tudo.

AS SEIS METRICAS DE CONSTANCIA (declaradas ANTES de rodar qualquer grade):

  1. `preg+`   fracao dos pregoes COM operacao que fecharam positivos. E' a
               pergunta do dono na forma mais crua: "em quantos dias eu
               ganho?".
  2. `bl20+`   fracao dos blocos ROLANTES de 20 pregoes que fecharam
               positivos (todos os deslocamentos, nao so' os disjuntos).
               Mede se o resultado sobrevive a QUANDO voce comecou -- e' a
               versao continua do teste de data de inicio que fixou o piso
               de capital em R$3.000.
  3. `mes+`    fracao dos meses-calendario positivos. Granularidade em que o
               dono de fato sente o resultado.
  4. `top5`    fracao do lucro BRUTO que veio dos 5 melhores pregoes. Alto =
               o resultado e' uma loteria com poucos bilhetes premiados; um
               robo "constante" tem isto BAIXO. E' a metrica que a auditoria
               de overfitting de 2026-08-17 usou (1 trade = 53,7% do lucro).
  5. `seq-`    maior sequencia de pregoes negativos consecutivos. E' o que
               quebra a conta e a paciencia, nesta ordem.
  6. `flat$`   fracao do lucro liquido que saiu por ACHATAMENTO de fim de
               pregao. O medo declarado do dono ("se baseia muito no
               fechamento do dia"): quanto do resultado depende de onde o
               sino pegou a posicao, e nao de uma tese que se pagou.

CRITERIO DE VERDADE, inalterado (itens 6.22/6.23): IC95% do win% contra o
BREAKEVEN EMPIRICO `perda_media/(ganho_media+perda_media)`. As seis metricas
acima ORDENAM candidatos; elas nao promovem nenhum. Um robo com `preg+` de
70% e IC que atravessa o breakeven continua sendo cara-ou-coroa bem vestida.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_consistencia_diagnostico_2026_09_11.py`
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
CAPITAL = 3_000.0          # piso declarado do robo
#: Mesmo corte IS/OOS de toda a familia copa_win (ver os scripts de 2026-09-11).
OOS_INICIO = pd.Timestamp("2026-06-13").date()
BLOCO = 20                 # pregoes por bloco rolante


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def ic95(k: int, n: int):
    if n == 0:
        return (0.0, 0.0)
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


def consistencia(trades, dias_da_janela):
    """As seis metricas + o veredito. `dias_da_janela` sao TODOS os pregoes
    da janela (inclusive os sem trade) -- um pregao sem operacao nao conta
    como positivo nem como negativo em `preg+`, mas conta como 0 no bloco
    rolante, que e' o comportamento certo: o bloco mede dinheiro no periodo,
    nao acerto por operacao."""
    por_dia = {}
    for t in trades:
        por_dia[t.exit_ts.date()] = por_dia.get(t.exit_ts.date(), 0.0) + t.pnl_brl
    serie = pd.Series([por_dia.get(d, 0.0) for d in dias_da_janela],
                      index=pd.to_datetime(dias_da_janela))

    com_trade = list(por_dia.values())
    preg_pos = sum(1 for v in com_trade if v > 0)

    blocos = [float(serie.iloc[i:i + BLOCO].sum())
              for i in range(0, max(1, len(serie) - BLOCO + 1))]
    blocos_pos = sum(1 for b in blocos if b > 0)

    mes = serie.groupby([serie.index.year, serie.index.month]).sum()
    meses_pos = int((mes > 0).sum())

    ganhos_dia = sorted((v for v in com_trade if v > 0), reverse=True)
    bruto_pos = sum(ganhos_dia)
    top5 = (sum(ganhos_dia[:5]) / bruto_pos) if bruto_pos > 0 else float("nan")

    seq = pior = 0
    for v in serie.values:
        if v < 0:
            seq += 1
            pior = max(pior, seq)
        elif v > 0:
            seq = 0

    liquido = float(serie.sum())
    flat = sum(t.pnl_brl for t in trades if t.exit_reason.value == "forced_flatten")
    n = len(trades)
    g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    gm = sum(g) / len(g) if g else 0.0
    pm = abs(sum(p) / len(p)) if p else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    lo, hi = ic95(len(g), n)
    ver = ("POSITIVO" if lo > be else "NEGATIVO" if hi < be else "indefinido") \
        if be == be and n else "--"

    return dict(
        liquido=liquido, n=n, pregoes=len(dias_da_janela),
        com_trade=len(com_trade), preg_pos=preg_pos,
        frac_preg=(preg_pos / len(com_trade)) if com_trade else float("nan"),
        blocos=len(blocos), frac_bl=(blocos_pos / len(blocos)) if blocos else float("nan"),
        meses=len(mes), frac_mes=(meses_pos / len(mes)) if len(mes) else float("nan"),
        top5=top5, seq_neg=pior,
        flat_share=(flat / liquido) if liquido else float("nan"),
        win=(len(g) / n) if n else float("nan"), be=be, lo=lo, hi=hi, veredito=ver,
        serie=serie,
    )


def main() -> None:
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.registry import get_daytrade_robot

    df = load_m1(SYMBOL).sort_index()
    cont = df.groupby(df.index.date).size()
    dias = sorted(d for d, n in cont.items() if n >= MIN_BARRAS_POR_PREGAO)
    df = df[[d in set(dias) for d in df.index.date]]
    corte = OOS_INICIO

    janelas = {
        "IS  (< " + str(corte) + ")": [d for d in dias if d < corte],
        "OOS (>= " + str(corte) + ")": [d for d in dias if d >= corte],
        "HISTORICO INTEIRO": dias,
    }
    print("copa_win de PRODUCAO -- alvo_vol 9,5 / stop_vol 12,0 / trail DESLIGADO")
    print("capital R$ " + br(CAPITAL, 0) + " (piso declarado do robo)")
    print(str(len(dias)) + " pregoes completos, " + str(dias[0]) + " a " + str(dias[-1]))
    print()

    resultados = {}
    for nome, ds in janelas.items():
        alvo = set(ds)
        bars = df[[d in alvo for d in df.index.date]]
        strat = get_daytrade_robot("copa_win", symbol=SYMBOL)
        cfg = config_for(
            profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
            initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
            limit_fill_capped_by_volume=True,
            queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0,
        )
        res = run_intraday_backtest(bars, strat, cfg)
        resultados[nome] = (consistencia(list(res.trades), ds), res)
        print("  " + nome + " rodado (" + str(len(res.trades)) + " operacoes)", flush=True)

    print("\n\n===== AS SEIS METRICAS DE CONSTANCIA =====")
    hdr = ("janela".ljust(22) + "liquido".rjust(12) + "ops".rjust(6)
           + "preg+".rjust(9) + "bl20+".rjust(9) + "mes+".rjust(9)
           + "top5".rjust(8) + "seq-".rjust(6) + "flat$".rjust(9)
           + "win%".rjust(8) + "BE%".rjust(8) + "veredito".rjust(12))
    print(hdr)
    print("-" * len(hdr))
    for nome, (c, _) in resultados.items():
        print(nome.ljust(22) + br(c["liquido"]).rjust(12) + str(c["n"]).rjust(6)
              + (br(100 * c["frac_preg"], 0) + "%").rjust(9)
              + (br(100 * c["frac_bl"], 0) + "%").rjust(9)
              + (br(100 * c["frac_mes"], 0) + "%").rjust(9)
              + (br(100 * c["top5"], 0) + "%").rjust(8)
              + str(c["seq_neg"]).rjust(6)
              + (br(100 * c["flat_share"], 0) + "%").rjust(9)
              + (br(100 * c["win"], 1) + "%").rjust(8)
              + (br(100 * c["be"], 1) + "%").rjust(8)
              + c["veredito"].rjust(12))

    print("\nlegenda: preg+ = pregoes com operacao que fecharam positivos |"
          " bl20+ = blocos ROLANTES de 20 pregoes positivos | mes+ = meses"
          " positivos | top5 = quanto do lucro bruto veio dos 5 melhores dias |"
          " seq- = maior sequencia de pregoes negativos | flat$ = quanto do"
          " liquido saiu por achatamento de fim de pregao")

    # ---- a distribuicao do dia, que e' onde mora a (in)constancia ---------
    print("\n\n===== DISTRIBUICAO DO RESULTADO DIARIO (historico inteiro) =====")
    s = resultados["HISTORICO INTEIRO"][0]["serie"]
    viv = s[s != 0]
    for rot, q in (("pior dia", viv.min()), ("p05", viv.quantile(0.05)),
                   ("p25", viv.quantile(0.25)), ("MEDIANA", viv.median()),
                   ("p75", viv.quantile(0.75)), ("p95", viv.quantile(0.95)),
                   ("melhor dia", viv.max()), ("MEDIA", viv.mean())):
        print("  " + rot.ljust(12) + br(float(q)).rjust(12))

    print("\nos 8 piores pregoes:")
    for d, v in viv.nsmallest(8).items():
        print("  " + str(d.date()) + br(float(v)).rjust(14))
    print("os 8 melhores pregoes:")
    for d, v in viv.nlargest(8).items():
        print("  " + str(d.date()) + br(float(v)).rjust(14))

    # ---- decomposicao por motivo de saida --------------------------------
    print("\n\n===== DE ONDE VEM O DINHEIRO, por motivo de saida "
          "(historico inteiro) =====")
    res = resultados["HISTORICO INTEIRO"][1]
    por_motivo = {}
    for t in res.trades:
        k = t.exit_reason.value
        a = por_motivo.setdefault(k, [0, 0.0, 0])
        a[0] += 1
        a[1] += t.pnl_brl
        a[2] += 1 if t.pnl_brl > 0 else 0
    total = sum(v[1] for v in por_motivo.values())
    print("motivo".ljust(20) + "ops".rjust(7) + "% ops".rjust(9)
          + "liquido".rjust(13) + "% do liq".rjust(11) + "win%".rjust(8)
          + "R$/op".rjust(11))
    n_tot = sum(v[0] for v in por_motivo.values())
    for k, (n, pnl, w) in sorted(por_motivo.items(), key=lambda kv: -abs(kv[1][1])):
        print(k.ljust(20) + str(n).rjust(7) + (br(100 * n / n_tot, 1) + "%").rjust(9)
              + br(pnl).rjust(13)
              + ((br(100 * pnl / total, 1) + "%") if total else "--").rjust(11)
              + (br(100 * w / n, 1) + "%").rjust(8) + br(pnl / n).rjust(11))


if __name__ == "__main__":
    main()
