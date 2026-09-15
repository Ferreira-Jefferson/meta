# -*- coding: utf-8 -*-
"""copa_win: e' o DIA que e' hostil, ou e' a 1a OPERACAO?

LENTE 4 de 5 (pedido do dono, 2026-09-15). O FATO ja medido (nao remedido
aqui): config de PRODUCAO, corte de achatamento -5min, 191 pregoes, 564
trades, 58 stops -- a 1a operacao do pregao tem P(stop)=18,8% (2a: 7,2%) e
concentra 62,1% dos stops. Estavel IS (63,2%) / OOS (60,0%).

Hipotese alternativa deste script: a 1a operacao nao e' ruim por ser a
primeira -- ela e' ruim porque certos PREGOES sao hostis, e a 1a operacao e'
a UNICA que todo pregao hostil chega a ter. Num dia ruim o robo stopa cedo e
opera pouco; num dia bom ele encadeia varias operacoes boas. Se for isso, o
"defeito da 1a" e' sombra da composicao dos dias, nao um vies proprio da
ordem.

Cinco perguntas (README completo no corpo do pedido):
  1. Distribuicao dos stops da 1a por PREGAO -- espalham ou concentram no
     tempo? (runs test na serie binaria cronologica + tabela por mes)
  2. O que caracteriza um pregao em que a 1a stopa, usando SO' informacao
     disponivel ANTES da abertura ou no comeco do dia: gap overnight,
     resultado/amplitude/volatilidade do pregao ANTERIOR, dia da semana,
     dias ate a rolagem do contrato, amplitude dos primeiros 30min do
     PROPRIO dia.
  3. Dado que a 1a stopou, qual o resultado medio do RESTO do pregao? E
     dado que a 1a foi alvo?
  4. Quantas operacoes o pregao tem, condicionado ao desfecho da 1a -- o
     ponto de maior risco de confusao causal (um stop na 1a pode ENCURTAR
     o dia e inflar mecanicamente a participacao da 1a nos stops).
  5. Tudo separado em IS (<2026-06-13) e OOS (>=2026-06-13).

Reaproveita `copawin_encerrar_mais_cedo_2026_09_14.py` (_df, CAPITAL,
_roda_janela, _cfg_com_folga) e a folga de producao (5min) de
`copawin_onde_perde_2026_09_14.py`. A rolagem do WIN vem de
`core.instruments.FUTURES_ROLLOVER_MONTHS` (nunca redigitada).

Sem scipy no venv deste projeto -- runs test e teste-t de Welch usam
aproximacao NORMAL (math.erf), valida para os tamanhos de amostra aqui
(dezenas a centenas); ressalva reforcada onde os n forem pequenos (<15).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_dia_hostil_nao_trade_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import math
import statistics as stats
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL          # R$3.000 -- o que o slot usa hoje
FOLGA_PRODUCAO = 5               # mesmo corte de producao dos dois scripts anteriores
CORTE_OOS = date(2026, 6, 13)    # mesmo corte de sempre


def br(x, casas=2):
    if x is None or (isinstance(x, float) and x != x):
        return "--"
    s = f"{x:,.{casas}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


# ---------------------------------------------------------------------------
# 1. features de PRE-ABERTURA / COMECO DO DIA, calculadas so' com barras M1
#    (independem de capital/janela -- calculadas UMA vez sobre a serie
#    completa e contigua de `dias`, pra que o "dia anterior" de um dia no
#    limite IS/OOS ainda seja o pregao anterior de verdade).
# ---------------------------------------------------------------------------

def _dias_ate_rolagem(d: date) -> int:
    """Dias corridos ate' o proximo 1o-dia-do-mes-PAR (fev/abr/jun/ago/out/
    dez) >= d -- proxy CALENDARIO da rolagem do WIN (`core.instruments.
    FUTURES_ROLLOVER_MONTHS["WIN"]`), sem ajuste de dia util nem consulta ao
    terminal. Ressalva: e' aproximacao (~0-3 dias de folga contra o dia util
    exato), nao confirmada contra o MT5 como o modulo fonte confirma o MES."""
    from core.instruments import FUTURES_ROLLOVER_MONTHS
    meses = FUTURES_ROLLOVER_MONTHS["WIN"]
    for m in meses:
        cand = date(d.year, m, 1)
        if cand >= d:
            return (cand - d).days
    alvo = date(d.year + 1, meses[0], 1)
    return (alvo - d).days


def _features_por_dia(df, dias):
    """dict[date] -> features pre-abertura/comeco do dia. `dias` e' a lista
    COMPLETA e contigua (nao so' a janela), pra que dias[i-1] seja sempre o
    pregao anterior de verdade."""
    import numpy as np

    por_dia_bars = {}
    idx_dates = df.index.date
    for d in dias:
        mask = idx_dates == d
        por_dia_bars[d] = df.loc[mask]

    feats = {}
    for i, d in enumerate(dias):
        bars = por_dia_bars[d]
        if len(bars) == 0:
            continue
        abertura = float(bars["open"].iloc[0])
        maxima = float(bars["high"].max())
        minima = float(bars["low"].min())
        fechamento = float(bars["close"].iloc[-1])
        primeiros30 = bars.iloc[:30]
        f30_amp_pts = float(primeiros30["high"].max() - primeiros30["low"].min())
        f30_amp_pct = 100.0 * f30_amp_pts / abertura if abertura else float("nan")

        rets = np.log(bars["close"] / bars["close"].shift(1)).dropna()
        vol_dia_pct = 100.0 * float(rets.std(ddof=1)) if len(rets) > 1 else float("nan")

        f = dict(
            date=d, dow=d.weekday(),  # 0=seg .. 4=sex
            abertura=abertura, maxima=maxima, minima=minima, fechamento=fechamento,
            n_bars=len(bars),
            f30_amp_pts=f30_amp_pts, f30_amp_pct=f30_amp_pct,
            vol_intradia_pct=vol_dia_pct,
            dias_ate_rolagem=_dias_ate_rolagem(d),
        )
        if i > 0:
            d_ant = dias[i - 1]
            b_ant = feats.get(d_ant)
            if b_ant is not None:
                f["gap_pts"] = abertura - b_ant["fechamento"]
                f["gap_pct"] = 100.0 * f["gap_pts"] / b_ant["fechamento"]
                f["prev_range_pts"] = b_ant["maxima"] - b_ant["minima"]
                f["prev_range_pct"] = 100.0 * f["prev_range_pts"] / b_ant["fechamento"]
                f["prev_result_pts"] = b_ant["fechamento"] - b_ant["abertura"]
                f["prev_result_pct"] = 100.0 * f["prev_result_pts"] / b_ant["abertura"]
                f["prev_vol_pct"] = b_ant["vol_intradia_pct"]
        feats[d] = f
    return feats


# ---------------------------------------------------------------------------
# 2. trades -> nivel de DIA (ordinal, 1a/resto, contagem)
# ---------------------------------------------------------------------------

def _dia_a_dia_de_trades(trades):
    """dict[date] -> dict com a 1a operacao, o resto, contagens e desfechos."""
    por_dia = defaultdict(list)
    for t in trades:
        por_dia[t.entry_ts.date()].append(t)
    out = {}
    for d, ts in por_dia.items():
        ts_ord = sorted(ts, key=lambda x: x.entry_ts)
        primeira = ts_ord[0]
        resto = ts_ord[1:]
        out[d] = dict(
            n_trades=len(ts_ord),
            primeira_motivo=primeira.exit_reason.value,
            primeira_pnl=primeira.pnl_brl,
            primeira_ts=primeira.entry_ts,
            algum_stop=any(t.exit_reason.value == "stop" for t in ts_ord),
            n_resto=len(resto),
            resto_pnl_soma=sum(t.pnl_brl for t in resto),
            resto_pnl_medio=(sum(t.pnl_brl for t in resto) / len(resto)) if resto else float("nan"),
            resto_stops=sum(1 for t in resto if t.exit_reason.value == "stop"),
            ultima_ts=ts_ord[-1].exit_ts,
        )
    return out


# ---------------------------------------------------------------------------
# estatistica (sem scipy) -- aproximacao NORMAL
# ---------------------------------------------------------------------------

def _p_dois_lados(z):
    if z != z:
        return float("nan")
    return math.erfc(abs(z) / math.sqrt(2))


def runs_test(seq):
    """Wald-Wolfowitz sobre a serie binaria `seq` (0/1), na ORDEM dada
    (cronologica). runs < esperado => os 1s (e os 0s) vem em BLOCOS
    (concentram no tempo); runs > esperado => alternam mais que o acaso
    (espalham demais); runs ~ esperado => aleatorio no tempo (nem
    concentram nem espalham de forma distinguivel)."""
    n = len(seq)
    n1 = sum(seq)
    n0 = n - n1
    if n1 == 0 or n0 == 0 or n < 2:
        return dict(n=n, n1=n1, n0=n0, runs=None, esperado=None, z=float("nan"), p=float("nan"))
    runs = 1
    for i in range(1, n):
        if seq[i] != seq[i - 1]:
            runs += 1
    esperado = 2 * n1 * n0 / n + 1
    var = (2 * n1 * n0 * (2 * n1 * n0 - n)) / (n * n * (n - 1))
    if var <= 0:
        return dict(n=n, n1=n1, n0=n0, runs=runs, esperado=esperado, z=float("nan"), p=float("nan"))
    z = (runs - esperado) / math.sqrt(var)
    return dict(n=n, n1=n1, n0=n0, runs=runs, esperado=esperado, z=z, p=_p_dois_lados(z))


def welch(a, b):
    a = [x for x in a if x == x]
    b = [x for x in b if x == x]
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return dict(na=na, nb=nb, ma=(stats.mean(a) if a else float("nan")),
                     mb=(stats.mean(b) if b else float("nan")),
                     sa=float("nan"), sb=float("nan"), t=float("nan"), p=float("nan"))
    ma, mb = stats.mean(a), stats.mean(b)
    va, vb = stats.variance(a), stats.variance(b)
    se = math.sqrt(va / na + vb / nb)
    t = (ma - mb) / se if se > 0 else float("nan")
    return dict(na=na, nb=nb, ma=ma, mb=mb, sa=math.sqrt(va), sb=math.sqrt(vb),
                se=se, t=t, p=_p_dois_lados(t))


def desc(vals):
    vals = [v for v in vals if v == v]
    n = len(vals)
    if n == 0:
        return dict(n=0, media=float("nan"), mediana=float("nan"), dp=float("nan"),
                     minimo=float("nan"), maximo=float("nan"))
    return dict(
        n=n, media=stats.mean(vals), mediana=stats.median(vals),
        dp=(stats.stdev(vals) if n > 1 else 0.0), minimo=min(vals), maximo=max(vals),
    )


def _fmt_desc(nome, d, casas=3):
    return (f"{nome:<20} n={d['n']:>4}  media={br(d['media'], casas):>10}  "
            f"mediana={br(d['mediana'], casas):>10}  dp={br(d['dp'], casas):>9}  "
            f"[{br(d['minimo'], casas)} ; {br(d['maximo'], casas)}]")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

FEATURES_PRE_ABERTURA = [
    ("gap_pct", "gap overnight (%)"),
    ("prev_result_pct", "resultado pregao ant. (%)"),
    ("prev_range_pct", "amplitude pregao ant. (%)"),
    ("prev_vol_pct", "vol. intradia ant. (%, dp ret 1min)"),
    ("dias_ate_rolagem", "dias ate rolagem WIN"),
    ("f30_amp_pct", "amplitude 30min do proprio dia (%)"),
]


def _analisa_janela(nome, dias_janela, feats_todos):
    print("\n" + "=" * 100)
    print(f"JANELA: {nome}  ({len(dias_janela)} pregoes)")
    print("=" * 100)

    res, corte = _base._roda_janela(CAPITAL, FOLGA_PRODUCAO, dias_janela)
    trades = list(res.trades)
    zerou = getattr(res, "wiped_out_at", None)
    dia_a_dia = _dia_a_dia_de_trades(trades)
    dias_com_trade = sorted(dia_a_dia)
    dias_sem_trade = [d for d in dias_janela if d not in dia_a_dia]

    print(f"trades={len(trades)}  pregoes_com_trade={len(dias_com_trade)}  "
          f"pregoes_sem_trade={len(dias_sem_trade)}/{len(dias_janela)}  "
          f"zerou_conta={'SIM em ' + str(zerou) if zerou else 'nao'}")

    stops_1a = [d for d in dias_com_trade if dia_a_dia[d]["primeira_motivo"] == "stop"]
    alvo_1a = [d for d in dias_com_trade if dia_a_dia[d]["primeira_motivo"] != "stop"]
    total_stops = sum(1 for t in trades if t.exit_reason.value == "stop")
    print(f"\nstops totais={total_stops}  |  stops na 1a operacao={len(stops_1a)}  "
          f"({br(100*len(stops_1a)/total_stops,1) if total_stops else '--'}% dos stops)  "
          f"|  P(1a stopa)={br(100*len(stops_1a)/len(dias_com_trade),1)}% "
          f"(n={len(dias_com_trade)} pregoes com trade)")

    # -------------------- PERGUNTA 1: espalha ou concentra no tempo? --------
    print("\n--- Q1: a 1a stopa se ESPALHA ou CONCENTRA no tempo (pregoes com trade, ordem cronologica) ---")
    serie = [1 if dia_a_dia[d]["primeira_motivo"] == "stop" else 0 for d in dias_com_trade]
    rt = runs_test(serie)
    if rt["runs"] is not None:
        leitura = ("CONCENTRA (menos blocos que o acaso)" if rt["z"] < -1.0 else
                    "ESPALHA/alterna mais que o acaso" if rt["z"] > 1.0 else
                    "compativel com aleatorio no tempo")
        print(f"  runs observados={rt['runs']}  esperado sob acaso={br(rt['esperado'],2)}  "
              f"z={br(rt['z'],2)}  p(2 lados, aprox normal)={br(rt['p'],4)}  -> {leitura}")
    else:
        print("  runs test nao aplicavel (n1 ou n0 = 0)")

    por_mes = defaultdict(lambda: [0, 0])   # (com_trade, stop_na_1a)
    for d in dias_com_trade:
        chave = (d.year, d.month)
        por_mes[chave][0] += 1
        if dia_a_dia[d]["primeira_motivo"] == "stop":
            por_mes[chave][1] += 1
    print("  por MES (pregoes com trade / stops na 1a / taxa):")
    for chave in sorted(por_mes):
        n_c, n_s = por_mes[chave]
        print(f"    {chave[0]}-{chave[1]:02d}: n={n_c:>3}  stops_1a={n_s:>2}  "
              f"taxa={br(100*n_s/n_c,1) if n_c else '--'}%")

    # -------------------- PERGUNTA 2: o que caracteriza o dia --------------
    print("\n--- Q2: features PRE-ABERTURA/COMECO DO DIA -- 1a STOPOU vs 1a NAO STOPOU ---")
    for chave, rotulo in FEATURES_PRE_ABERTURA:
        vals_stop = [feats_todos[d][chave] for d in stops_1a if chave in feats_todos.get(d, {})]
        vals_ok = [feats_todos[d][chave] for d in alvo_1a if chave in feats_todos.get(d, {})]
        d_stop, d_ok = desc(vals_stop), desc(vals_ok)
        w = welch(vals_stop, vals_ok)
        print(f"\n  {rotulo}")
        print("    " + _fmt_desc("1a STOPOU", d_stop))
        print("    " + _fmt_desc("1a nao stopou", d_ok))
        print(f"    Welch (aprox normal): delta_media={br(w['ma']-w['mb'],3)}  "
              f"t~z={br(w['t'],2)}  p(2 lados)={br(w['p'],4)}"
              + ("   [n<15 nalgum lado -- leia com cautela]" if min(w["na"], w["nb"]) < 15 else ""))

    # dia da semana -- tabela de contingencia, nao media
    print("\n  dia da semana (seg..sex), contagem e taxa de stop-na-1a:")
    dow_nomes = ["seg", "ter", "qua", "qui", "sex"]
    por_dow = defaultdict(lambda: [0, 0])
    for d in dias_com_trade:
        dw = feats_todos.get(d, {}).get("dow")
        if dw is None or dw > 4:
            continue
        por_dow[dw][0] += 1
        if dia_a_dia[d]["primeira_motivo"] == "stop":
            por_dow[dw][1] += 1
    for dw in range(5):
        n_c, n_s = por_dow.get(dw, [0, 0])
        print(f"    {dow_nomes[dw]}: n={n_c:>3}  stops_1a={n_s:>2}  "
              f"taxa={br(100*n_s/n_c,1) if n_c else '--'}%")

    # -------------------- PERGUNTA 3: dado o desfecho da 1a, o resto do dia -
    print("\n--- Q3: dado o desfecho da 1a, resultado do RESTO do pregao (dias com n_resto>=1) ---")
    for rotulo, grupo in (("1a STOPOU", stops_1a), ("1a foi ALVO/outro", alvo_1a)):
        com_resto = [d for d in grupo if dia_a_dia[d]["n_resto"] >= 1]
        soma = desc([dia_a_dia[d]["resto_pnl_soma"] for d in com_resto])
        media_trade = desc([dia_a_dia[d]["resto_pnl_medio"] for d in com_resto])
        stops_resto = sum(dia_a_dia[d]["resto_stops"] for d in com_resto)
        trades_resto = sum(dia_a_dia[d]["n_resto"] for d in com_resto)
        print(f"\n  {rotulo}  (n_dias_com_resto={len(com_resto)} de {len(grupo)})")
        print("    " + _fmt_desc("soma R$ do resto/dia", soma, 2))
        print("    " + _fmt_desc("media R$/trade do resto", media_trade, 2))
        print(f"    stops no RESTO do dia: {stops_resto}/{trades_resto} trades "
              f"({br(100*stops_resto/trades_resto,1) if trades_resto else '--'}%)")

    # -------------------- PERGUNTA 4: confusao causal -- dia encurta? -------
    print("\n--- Q4: quantidade de operacoes do pregao, condicionada ao desfecho da 1a ---")
    n_stop = desc([dia_a_dia[d]["n_trades"] for d in stops_1a])
    n_ok = desc([dia_a_dia[d]["n_trades"] for d in alvo_1a])
    w = welch([dia_a_dia[d]["n_trades"] for d in stops_1a],
              [dia_a_dia[d]["n_trades"] for d in alvo_1a])
    print("  " + _fmt_desc("n_trades | 1a STOPOU", n_stop, 2))
    print("  " + _fmt_desc("n_trades | 1a nao stopou", n_ok, 2))
    print(f"  Welch (aprox normal): delta_media={br(w['ma']-w['mb'],2)}  t~z={br(w['t'],2)}  "
          f"p(2 lados)={br(w['p'],4)}")
    so_1_trade_stop = sum(1 for d in stops_1a if dia_a_dia[d]["n_trades"] == 1)
    so_1_trade_ok = sum(1 for d in alvo_1a if dia_a_dia[d]["n_trades"] == 1)
    print(f"  pregoes que PARARAM na 1a operacao (n_trades==1): "
          f"{so_1_trade_stop}/{len(stops_1a)} quando 1a stopou "
          f"({br(100*so_1_trade_stop/len(stops_1a),1) if stops_1a else '--'}%) vs "
          f"{so_1_trade_ok}/{len(alvo_1a)} quando 1a nao stopou "
          f"({br(100*so_1_trade_ok/len(alvo_1a),1) if alvo_1a else '--'}%)")

    print("\n  consequencia mecanica: se 1a-stop ENCURTA o dia (menos trades no RESTO), "
          "o denominador de oportunidades nos ordinais 2+ fica MENOR nos dias que comecaram mal, "
          "o que empurra a taxa de stop dos ordinais 2+ para BAIXO so' por sobrarem menos tentativas "
          "-- e infla a fatia da 1a nos stops totais por CONSTRUCAO, nao por risco maior da 1a em si.")

    return dict(
        dias_com_trade=dias_com_trade, stops_1a=stops_1a, alvo_1a=alvo_1a,
        dia_a_dia=dia_a_dia, total_stops=total_stops, zerou=zerou,
        dias_sem_trade=dias_sem_trade,
    )


def main():
    print("=" * 100)
    print("copa_win -- LENTE 4/5: e' o DIA que e' hostil, ou e' a 1a OPERACAO? (WIN@, R$3.000)")
    print("=" * 100)

    df, dias = _base._df()
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]})")
    print("config de PRODUCAO (registry._KWARGS_PADRAO['copa_win']), corte de achatamento -5min, "
          "capital R$3.000 -- nenhum dos dois neutralizado; portao de capital do WIN@ e' R$200, "
          "bem abaixo do capital usado, entao nao e' esperado censurar por caixa.")

    print("\ncalculando features de PRE-ABERTURA/COMECO DO DIA (gap, dia anterior, rolagem, "
          "30min do proprio dia) sobre a serie COMPLETA e contigua...", flush=True)
    feats = _features_por_dia(df, dias)

    dias_is = [d for d in dias if d < CORTE_OOS]
    dias_oos = [d for d in dias if d >= CORTE_OOS]
    janelas = [
        ("IS (<2026-06-13)", dias_is),
        ("OOS (>=2026-06-13)", dias_oos),
    ]

    resultados = {}
    for nome, dias_janela in janelas:
        resultados[nome] = _analisa_janela(nome, dias_janela, feats)

    # -------------------- resumo comparativo IS vs OOS ---------------------
    print("\n\n" + "=" * 100)
    print("RESUMO -- estavel entre IS e OOS?")
    print("=" * 100)
    hdr = f"{'':<28}{'IS':>18}{'OOS':>18}"
    print(hdr)
    for nome, r in resultados.items():
        pass
    r_is, r_oos = resultados["IS (<2026-06-13)"], resultados["OOS (>=2026-06-13)"]
    for rotulo, chave_fn in (
        ("P(1a stopa) %", lambda r: 100 * len(r["stops_1a"]) / len(r["dias_com_trade"])),
        ("stops-1a / stops totais %", lambda r: 100 * len(r["stops_1a"]) / r["total_stops"] if r["total_stops"] else float("nan")),
        ("pregoes com trade", lambda r: len(r["dias_com_trade"])),
        ("pregoes sem trade", lambda r: len(r["dias_sem_trade"])),
    ):
        print(f"{rotulo:<28}{br(chave_fn(r_is),1):>18}{br(chave_fn(r_oos),1):>18}")

    print("\n" + "=" * 100)
    print("O QUE NAO CONSEGUI MEDIR E POR QUE")
    print("=" * 100)
    print("""
  1. Rolagem do contrato WIN e' proxy de CALENDARIO (1o dia do mes par mais
     proximo), nao a data real de rolagem de volume/book confirmada contra o
     terminal MT5 -- pode errar por ~0-3 dias uteis. Nao ha' no repo uma
     tabela de datas de rolagem REALIZADA do WIN@ para calibrar isso melhor
     (so' existe a REGRA de qual mes e' o corrente, em `core.instruments`).
  2. Sem scipy no venv -- runs test e teste-t usam aproximacao NORMAL
     (math.erf), nao a distribuicao exata. Para os grupos com n<15 (marcados
     na tabela) o p-valor e' indicativo, nao uma prova.
  3. 'Amplitude dos primeiros 30 minutos' usa as PRIMEIRAS 30 BARRAS de cada
     pregao, nao um recorte por relogio (09:00-09:30 BRT) -- se algum pregao
     abriu atrasado (feed, leilao estendido) a janela desliza junto. Nao
     verifiquei pregao a pregao se isso acontece; e' o mesmo pressuposto que
     `MIN_BARRAS_POR_PREGAO=400` ja assume implicitamente ao aceitar o dia
     como completo.
  4. O teste de causalidade (Q4) e' associacional -- mostra que dias com
     1a-stop tem MENOS trades no resto (ou nao), mas nao isola SE isso vem de
     caixa consumido, cota de entradas do robo, ou o dia realmente acabar
     cedo por regime de mercado; qualquer um dos tres produziria o mesmo
     padrao observavel aqui.
  5. Nao recomputei o veredito do FATO original (P(stop)=18,8%/7,2%,
     62,1% dos stops) -- ele e' o insumo desta lente, nao o alvo dela.
""")
    print("FIM.")


if __name__ == "__main__":
    main()
