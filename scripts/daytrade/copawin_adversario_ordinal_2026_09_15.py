# -*- coding: utf-8 -*-
"""copa_win: LENTE 5/5 (ADVERSARIO) -- o excesso de stops na 1a operacao do
dia e' fenomeno de mercado ou artefato de contagem?

Achado sob ataque (`copawin_onde_perde_2026_09_14.py`, config de PRODUCAO,
corte de achatamento de producao folga=5min, 191 pregoes, 564 trades, 58
stops): a 1a operacao do pregao e' 33,9% dos trades e concentra 62,1% dos
STOPS (36 de 58), P(stop)=18,8% contra 7,2%/5,6%/11,5%/0% das ordens
seguintes. O padrao sobrevive ao corte IS/OOS (63,2%/60,0% dos stops na 1a).

Este script NAO tenta explicar o efeito -- as outras 4 lentes fazem isso.
Aqui o trabalho e' o oposto: tentar DERRUBAR o achado como artefato de como
os trades sao contados, em 6 frentes independentes. As duas saidas (derrubou
/ nao derrubou) sao vitoria -- o que nao pode acontecer e' o achado sobreviver
sem ter sido atacado.

FRENTES:
  1. Sobrevivencia no ordinal -- quantos pregoes ALCANCAM cada ordinal (o
     balde "5a+" so' existe em dias que ja passaram por 4 operacoes que nao
     encerraram o dia). P(stop) condicionado a alcancar e' o numero certo,
     nao o numero cru.
  2. Causalidade reversa -- um stop na 1a op. encurta o dia (menos trades,
     sessao mais curta)? Se sim, o proprio stop reduz o denominador dos
     ordinais seguintes e infla a fatia da 1a por conta corrente, nao por
     ela ser mais arriscada.
  3. O NULO CORRETO -- permutacao DENTRO DE CADA PREGAO (embaralha qual
     trade do dia leva o rotulo "1a", preservando o conjunto de desfechos
     do dia e quantos trades cada dia teve -- ou seja, preserva a propria
     estrutura de sobrevivencia do ataque 1). Sob H0 ("a posicao no dia
     NAO importa, so' importa o conjunto de desfechos"), qual e' a
     distribuicao de "quantos stops caem no rotulo 1a" e onde o observado
     (36) cai nela? Ao lado, o nulo INGENUO (ignora o dia, so' embaralha os
     564 trades) para comparacao.
  4. Tempo de exposicao -- a 1a operacao fica aberta mais tempo? Duracao
     media/mediana por ordinal.
  5. Confusao com o horario -- entre trades do MESMO horario de entrada
     (BRT), o que e' 1a do dia stopa mais do que o que e' 2a/3a no mesmo
     horario? Se nao houver diferenca, ordinal nao e' a variavel -- e'
     coincidencia com o relogio (ja' testado e refutado como solucionavel
     por filtro em `copawin_ordem_vs_relogio_2026_09_14.py`; aqui a
     pergunta e' so' se o RESIDUO depois de fixar a hora ainda mostra
     ordinal importando).
  6. Robustez de medicao -- o excesso sobrevive a capital NOCIONAL (sem
     portao de caixa), ao corte de achatamento ANTIGO (cravado, sem folga),
     e a geometrias vizinhas da producao (alvo/ttl)?

Reaproveita carregador e config de `copawin_encerrar_mais_cedo_2026_09_14.py`
e a funcao de ordinal de `copawin_onde_perde_2026_09_14.py` (redigitada aqui
so' porque aquele script nao a expoe como funcao reutilizavel de fora).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_adversario_ordinal_2026_09_15.py`
"""
from __future__ import annotations

import dataclasses
import importlib.util
import math
import random
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base_adv", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

CAPITAL = _base.CAPITAL                 # R$3.000 -- o que o slot usa hoje
FOLGA_PRODUCAO = 5                      # corte de achatamento de producao
CAPITAL_NOCIONAL = 300_000.0            # so' pra tirar o portao de caixa da equacao
BRT = "America/Sao_Paulo"
TETO = 5                                # baldes 1,2,3,4,"5+" -- igual ao achado citado
N_PERM_PRINCIPAL = 20_000
N_PERM_ROBUSTEZ = 5_000
SEED = 42


def br(x, casas=2):
    if x is None or (isinstance(x, float) and x != x):
        return "--"
    return f"{x:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - m), min(1.0, c + m))


def _por_dia(trades):
    d = defaultdict(list)
    for t in trades:
        d[t.entry_ts.date()].append(t)
    return d


def _ordem(por_dia):
    """id(trade) -> 1, 2, 3... pela ordem de ENTRADA dentro do proprio
    pregao (reinicia a cada dia, igual a `copawin_onde_perde`)."""
    ordem = {}
    for dia, ts in por_dia.items():
        for i, t in enumerate(sorted(ts, key=lambda x: x.entry_ts), start=1):
            ordem[id(t)] = i
    return ordem


# ---------------------------------------------------------------------------
# ATAQUE 1 -- sobrevivencia no ordinal: quantos pregoes ALCANCAM cada balde
# ---------------------------------------------------------------------------

def ataque1_sobrevivencia(trades, ordem, por_dia, teto=TETO):
    n_dias = len(por_dia)
    print(f"\n--- ATAQUE 1: SOBREVIVENCIA -- quantos pregoes ALCANCAM cada ordinal "
          f"(de {n_dias} pregoes) ---")
    hdr = f"{'ordinal':<9}{'pregoes q alcancam':>20}{'% dos pregoes':>15}{'n trades':>10}{'stops':>7}{'P(stop)':>10}{'IC95%':>18}"
    print(hdr)
    print("-" * len(hdr))
    linhas = []
    for k in range(1, teto + 1):
        if k < teto:
            ts_k = [t for t in trades if ordem[id(t)] == k]
        else:
            ts_k = [t for t in trades if ordem[id(t)] >= teto]
        n_reach = len({t.entry_ts.date() for t in ts_k})
        stops = sum(1 for t in ts_k if t.exit_reason.value == "stop")
        lo, hi = wilson(stops, len(ts_k))
        rot = f"{k}a" if k < teto else f"{teto}a+"
        linhas.append((rot, n_reach, len(ts_k), stops, lo, hi))
        print(f"{rot:<9}{n_reach:>20}{br(100*n_reach/n_dias,1)+'%':>15}{len(ts_k):>10}"
              f"{stops:>7}{br(100*stops/len(ts_k) if ts_k else float('nan'),1)+'%':>10}"
              f"{'['+br(100*lo,1)+';'+br(100*hi,1)+']':>18}")
    print("  LEITURA: a coluna 'pregoes q alcancam' cai monotonicamente -- e' esperado por")
    print("  construcao (um dia so' chega na 5a operacao se as 4 primeiras nao o encerraram).")
    print("  O que importa e' se P(stop) tambem cai monotonicamente DENTRO dessa populacao")
    print("  cada vez mais seleta -- se cair, a selecao (dias 'bons' sobrando) e' candidata a")
    print("  explicar por que os ordinais altos parecem mais seguros, SEM que a 1a operacao")
    print("  seja especial: seria so' o efeito de que so' dias ruins df acabam cedo.")
    return linhas


# ---------------------------------------------------------------------------
# ATAQUE 2 -- causalidade reversa: stop na 1a encurta o dia?
# ---------------------------------------------------------------------------

def ataque2_causalidade_reversa(por_dia):
    print("\n--- ATAQUE 2: CAUSALIDADE REVERSA -- um stop na 1a operacao encurta o dia? ---")
    grupos = defaultdict(list)
    for dia, ts in por_dia.items():
        ts_ord = sorted(ts, key=lambda x: x.entry_ts)
        primeira = ts_ord[0]
        grp = "1a=STOP" if primeira.exit_reason.value == "stop" else "1a=outro"
        duracao_dia_min = (ts_ord[-1].exit_ts - ts_ord[0].entry_ts).total_seconds() / 60.0
        grupos[grp].append(dict(
            n=len(ts_ord), duracao=duracao_dia_min,
            tem2=len(ts_ord) >= 2, tem3=len(ts_ord) >= 3,
            tem4=len(ts_ord) >= 4, tem5=len(ts_ord) >= 5,
        ))
    hdr = (f"{'grupo':<12}{'n dias':>8}{'trades/dia (media)':>20}{'trades/dia (mediana)':>22}"
           f"{'dur. dia min (media)':>22}{'%>=2':>7}{'%>=3':>7}{'%>=4':>7}{'%>=5':>7}")
    print(hdr)
    print("-" * len(hdr))
    for grp in sorted(grupos):
        ds = grupos[grp]
        n = len(ds)
        ns = sorted(d["n"] for d in ds)
        media_n = sum(ns) / n
        mediana_n = ns[n // 2] if n % 2 else (ns[n // 2 - 1] + ns[n // 2]) / 2
        media_dur = sum(d["duracao"] for d in ds) / n
        print(f"{grp:<12}{n:>8}{br(media_n,2):>20}{br(mediana_n,1):>22}{br(media_dur,1):>22}"
              f"{br(100*sum(d['tem2'] for d in ds)/n,1)+'%':>7}"
              f"{br(100*sum(d['tem3'] for d in ds)/n,1)+'%':>7}"
              f"{br(100*sum(d['tem4'] for d in ds)/n,1)+'%':>7}"
              f"{br(100*sum(d['tem5'] for d in ds)/n,1)+'%':>7}")
    print("  LEITURA: se '1a=STOP' tiver MENOS trades/dia e sessao mais curta que '1a=outro',")
    print("  o proprio stop e' quem reduz o denominador dos ordinais seguintes -- causalidade")
    print("  reversa: nao e' que a 2a/3a operacao seja mais segura, e' que dias que tiveram")
    print("  stop na 1a produzem MENOS 2a/3a/4a/5a para a conta (vies de selecao no denominador).")


# ---------------------------------------------------------------------------
# ATAQUE 3 -- o nulo correto: permutacao dentro do pregao + nulo ingenuo
# ---------------------------------------------------------------------------

def ataque3_permutacao(trades, por_dia, n_perm=N_PERM_PRINCIPAL, seed=SEED):
    print(f"\n--- ATAQUE 3: O NULO CORRETO (n_perm={n_perm}, seed={seed}) ---")
    dias = list(por_dia.values())
    # por_dia nao vem ordenado por entry_ts -- ordena aqui explicitamente, e' o
    # que define quem e' a "1a" real de cada pregao (outs[0]).
    outcomes_por_dia = [
        [t.exit_reason.value == "stop" for t in sorted(ts, key=lambda x: x.entry_ts)]
        for ts in dias
    ]
    obs_stat = sum(1 for outs in outcomes_por_dia if outs[0])
    n_trades = len(trades)
    n_stops = sum(1 for t in trades if t.exit_reason.value == "stop")
    n_ord1 = len(outcomes_por_dia)  # 1 por dia, sempre existe

    # --- nulo A: PERMUTACAO DENTRO DO PREGAO (preserva a estrutura de sobrevivencia) ---
    rng = random.Random(seed)
    perm_stats = []
    for _ in range(n_perm):
        total = 0
        for outs in outcomes_por_dia:
            i = rng.randrange(len(outs))
            if outs[i]:
                total += 1
        perm_stats.append(total)
    perm_stats.sort()
    p_perm = (sum(1 for x in perm_stats if x >= obs_stat) + 1) / (n_perm + 1)
    media_perm = sum(perm_stats) / n_perm
    dp_perm = statistics.pstdev(perm_stats)
    lo_perm = perm_stats[int(0.025 * n_perm)]
    hi_perm = perm_stats[int(0.975 * n_perm)]

    # --- nulo B: INGENUO -- ignora o dia, embaralha os 564 trades e olha quantos
    # stops caem entre os n_ord1 (=191) que labels de "1a" ocupariam por acaso.
    # Exato via hipergeometrica: P(X >= obs | N=n_trades, K=n_stops, n=n_ord1).
    def hipergeom_sf(N, K, n, x_obs):
        total = float(math.comb(N, n))
        s = 0.0
        for x in range(x_obs, min(K, n) + 1):
            s += math.comb(K, x) * math.comb(N - K, n - x)
        return s / total

    p_ingenuo = hipergeom_sf(n_trades, n_stops, n_ord1, obs_stat)
    media_ingenua = n_stops * n_ord1 / n_trades

    print(f"  observado: {obs_stat} stops no rotulo '1a operacao' (de {n_stops} stops totais, "
          f"{n_ord1} pregoes/rotulos)")
    print(f"  NULO A (permutacao DENTRO do pregao -- preserva quantos trades cada dia teve E o")
    print(f"          conjunto de desfechos do dia; so' embaralha QUEM leva o rotulo '1a'):")
    print(f"          media={br(media_perm,2)}  desvio={br(dp_perm,2)}  IC95%=[{lo_perm};{hi_perm}]  "
          f"p(observado>=isto por acaso)={br(p_perm,5)}")
    print(f"  NULO B (ingenuo -- ignora o dia, hipergeometrica exata sobre os {n_trades} trades):")
    print(f"          media esperada={br(media_ingenua,2)}  p={br(p_ingenuo,6)} (P(X>={obs_stat}) sob "
          f"N={n_trades},K={n_stops},n={n_ord1})")
    print("  LEITURA: os dois nulos respondem perguntas diferentes. B testa 'stops caem ao acaso")
    print("  entre TODOS os trades' (ignora que trades do mesmo dia sao correlacionados). A testa")
    print("  a hipotese mais dificil de derrubar: 'dentro do MESMO conjunto de desfechos de cada")
    print("  dia, a posicao temporal (quem e' 1o) nao importa'. Se o observado estourar os DOIS")
    print("  intervalos, o excesso nao e' artefato de contagem -- sobrevive ao nulo mais rigoroso.")
    return dict(obs=obs_stat, n_stops=n_stops, n_ord1=n_ord1, n_trades=n_trades,
                p_perm=p_perm, media_perm=media_perm, dp_perm=dp_perm,
                lo_perm=lo_perm, hi_perm=hi_perm, p_ingenuo=p_ingenuo, media_ingenua=media_ingenua)


# ---------------------------------------------------------------------------
# ATAQUE 4 -- tempo de exposicao por ordinal
# ---------------------------------------------------------------------------

def ataque4_duracao(trades, ordem, teto=TETO):
    print("\n--- ATAQUE 4: TEMPO DE EXPOSICAO -- duracao (minutos) por ordinal ---")
    baldes = defaultdict(list)
    for t in trades:
        k = min(ordem[id(t)], teto)
        dur_min = (t.exit_ts - t.entry_ts).total_seconds() / 60.0
        baldes[k].append(dur_min)
    hdr = f"{'ordinal':<9}{'n':>6}{'media min':>12}{'mediana min':>14}{'desvio min':>12}"
    print(hdr)
    print("-" * len(hdr))
    for k in sorted(baldes):
        arr = sorted(baldes[k])
        n = len(arr)
        media = sum(arr) / n
        mediana = arr[n // 2] if n % 2 else (arr[n // 2 - 1] + arr[n // 2]) / 2
        dp = statistics.pstdev(arr) if n > 1 else 0.0
        rot = f"{k}a" if k < teto else f"{teto}a+"
        print(f"{rot:<9}{n:>6}{br(media,1):>12}{br(mediana,1):>14}{br(dp,1):>12}")
    print("  LEITURA: se a 1a operacao ficar sistematicamente mais tempo aberta que as demais,")
    print("  ela tem mais CHANCE MECANICA de tocar o stop so' por estar exposta mais tempo --")
    print("  explicacao que nao precisa de nenhuma hipotese sobre 'ser a primeira' ser especial.")


# ---------------------------------------------------------------------------
# ATAQUE 5 -- confusao com o horario: mesma hora, 1a vs 2a+
# ---------------------------------------------------------------------------

def ataque5_mesma_hora(trades, ordem, min_n=8):
    print(f"\n--- ATAQUE 5: MESMA HORA -- entre trades do MESMO horario de entrada (BRT), "
          f"'1a do dia' stopa mais que '2a+ do dia'? (so' horas com n>={min_n} dos dois lados) ---")
    baldes = defaultdict(lambda: {"1a": [], "2a+": []})
    for t in trades:
        hora = t.entry_ts.tz_convert(BRT).hour
        k = "1a" if ordem[id(t)] == 1 else "2a+"
        baldes[hora][k].append(t)
    hdr = f"{'hora BRT':<10}{'n 1a':>7}{'stop 1a':>9}{'P(stop) 1a':>12}{'n 2a+':>8}{'stop 2a+':>10}{'P(stop) 2a+':>13}{'delta pp':>10}"
    print(hdr)
    print("-" * len(hdr))
    deltas = []
    for h in sorted(baldes):
        g1, g2 = baldes[h]["1a"], baldes[h]["2a+"]
        n1, n2 = len(g1), len(g2)
        if n1 < min_n or n2 < min_n:
            continue
        s1 = sum(1 for t in g1 if t.exit_reason.value == "stop")
        s2 = sum(1 for t in g2 if t.exit_reason.value == "stop")
        p1, p2 = 100 * s1 / n1, 100 * s2 / n2
        deltas.append(p1 - p2)
        print(f"{h:02d}h{'':<6}{n1:>7}{s1:>9}{br(p1,1)+'%':>12}{n2:>8}{s2:>10}{br(p2,1)+'%':>13}"
              f"{br(p1-p2,1):>10}")
    if deltas:
        print(f"\n  {len(deltas)} horas comparaveis. delta medio (1a - 2a+) = {br(sum(deltas)/len(deltas),1)}pp, "
              f"todas positivas: {all(d>0 for d in deltas)}")
    else:
        print("  nenhuma hora com n suficiente dos dois lados nesta janela -- sem leitura.")
    print("  LEITURA: se o delta for consistentemente positivo (1a stopa mais que 2a+ na MESMA")
    print("  hora), o ordinal explica algo que o relogio sozinho nao explica. Se os deltas forem")
    print("  proximos de zero ou trocarem de sinal, o horario e' a variavel real e o ordinal e'")
    print("  so' colinear com ele (ja' documentado: pular sinais nao resolve, atrasar resolve --")
    print("  este ataque pergunta se ainda sobra alguma coisa DEPOIS de fixar a hora).")


# ---------------------------------------------------------------------------
# ATAQUE 6 -- robustez a escolhas de medicao
# ---------------------------------------------------------------------------

def _construir_estrategia(overrides=None):
    sys.path.insert(0, str(ROOT / "src"))
    from strategy.daytrade.lab.copa_win import CopaWin
    from strategy.daytrade.registry import _KWARGS_PADRAO

    kwargs = dict(_KWARGS_PADRAO.get("copa_win", {}))
    kwargs["symbol"] = _base.SYMBOL
    if overrides:
        kwargs.update(overrides)
    return CopaWin(**kwargs)


def _roda_variante(dias_janela, capital, folga_min, overrides=None):
    sys.path.insert(0, str(ROOT / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import _recua, config_for, profile_for

    df, _ = _base._df()
    alvo = set(dias_janela)
    bars = df[[d in alvo for d in df.index.date]]
    strat = _construir_estrategia(overrides)
    profile = profile_for(_base.SYMBOL)
    cfg = config_for(profile, trade_tick_value=0.20, trade_tick_size=1.0,
                      initial_capital=capital,
                      target_fills_as_maker=strat.target_fills_as_maker,
                      limit_fill_capped_by_volume=True,
                      queue_ahead_qty=0.0, exit_queue_ahead_qty=0.0)
    cfg = dataclasses.replace(cfg, session_end_time=_recua(profile.session_end_time, folga_min))
    return run_intraday_backtest(bars, strat, cfg)


def _unidade_robustez(args):
    rotulo, dias_janela, capital, folga_min, overrides = args
    with redirect_stdout(StringIO()):
        res = _roda_variante(dias_janela, capital, folga_min, overrides)
    trades = list(res.trades)
    por_dia = _por_dia(trades)
    ordem = _ordem(por_dia)
    dias_ord = list(por_dia.values())
    outcomes = [[t.exit_reason.value == "stop" for t in sorted(ts, key=lambda x: x.entry_ts)]
                for ts in dias_ord]
    obs = sum(1 for o in outcomes if o[0])
    n_trades = len(trades)
    n_stops = sum(1 for t in trades if t.exit_reason.value == "stop")
    n_ord1 = len(outcomes)
    rng = random.Random(SEED)
    perm_stats = []
    for _ in range(N_PERM_ROBUSTEZ):
        total = 0
        for o in outcomes:
            i = rng.randrange(len(o))
            if o[i]:
                total += 1
        perm_stats.append(total)
    p_perm = (sum(1 for x in perm_stats if x >= obs) + 1) / (N_PERM_ROBUSTEZ + 1)
    stops_ord1 = obs
    pct_stops_ord1 = 100 * stops_ord1 / n_stops if n_stops else float("nan")
    p_stop_ord1 = 100 * obs / n_ord1 if n_ord1 else float("nan")
    return dict(rotulo=rotulo, n_trades=n_trades, n_stops=n_stops, n_ord1=n_ord1,
                stops_ord1=stops_ord1, pct_stops_ord1=pct_stops_ord1,
                p_stop_ord1=p_stop_ord1, p_perm=p_perm, dias_com=len(por_dia))


def ataque6_robustez(dias_completo):
    print("\n--- ATAQUE 6: ROBUSTEZ A ESCOLHAS DE MEDICAO (historico completo, "
          f"n_perm={N_PERM_ROBUSTEZ}) ---")
    variantes = [
        ("CONTROLE (producao, R$3.000, folga5)", dias_completo, CAPITAL, 5, None),
        ("nocional R$300.000, folga5", dias_completo, CAPITAL_NOCIONAL, 5, None),
        ("corte cravado (folga0, sem margem)", dias_completo, CAPITAL, 0, None),
        ("alvo 9,5 / ttl15", dias_completo, CAPITAL, 5,
         dict(alvo_vol=9.5, entrada_ttl_barras=15)),
        ("alvo 7,6 / ttl8", dias_completo, CAPITAL, 5,
         dict(alvo_vol=7.6, entrada_ttl_barras=8)),
    ]
    resultados = {}
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade_robustez, v): v[0] for v in variantes}
        for fut in as_completed(futs):
            r = fut.result()
            resultados[r["rotulo"]] = r
            print(f"  ...concluido: {r['rotulo']}", flush=True)

    hdr = (f"{'variante':<38}{'dias c/op':>10}{'trades':>8}{'stops':>7}{'stops na 1a':>12}"
           f"{'% dos stops':>12}{'P(stop) 1a':>11}{'p(permutacao)':>14}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for rotulo, _, _, _, _ in variantes:
        r = resultados[rotulo]
        print(f"{rotulo:<38}{r['dias_com']:>10}{r['n_trades']:>8}{r['n_stops']:>7}"
              f"{r['stops_ord1']:>12}{br(r['pct_stops_ord1'],1)+'%':>12}"
              f"{br(r['p_stop_ord1'],1)+'%':>11}{br(r['p_perm'],5):>14}")
    print("  LEITURA: se '% dos stops' na 1a operacao ficar bem acima da fatia de trades que a")
    print("  1a representa (~34%) e p(permutacao) continuar pequeno em TODAS as variantes, o")
    print("  achado nao e' fragil a nenhuma escolha isolada de medicao testada aqui.")


def main():
    df, dias = _base._df()
    corte_oos = pd.Timestamp("2026-06-13").date()
    janelas = [
        ("IS (<2026-06-13)", [d for d in dias if d < corte_oos]),
        ("OOS (>=2026-06-13)", [d for d in dias if d >= corte_oos]),
        ("HISTORICO COMPLETO", dias),
    ]
    print("=" * 112)
    print("copa_win -- LENTE 5/5 (ADVERSARIO): o excesso de stops na 1a operacao e' real ou artefato?")
    print("=" * 112)
    print(f"{len(dias)} pregoes completos ({dias[0]} a {dias[-1]}), config de PRODUCAO "
          f"(registry._KWARGS_PADRAO['copa_win']), corte de achatamento producao (folga {FOLGA_PRODUCAO}min), "
          f"capital R$ {br(CAPITAL,0)}.")
    print("RESSALVA: WIN@ sem fila calibrada em fidelidade.py; OOS ja' gasto varias vezes -- "
          "este script nao propoe acao, so' ataca a robustez estatistica do achado.\n", flush=True)

    for nome, dias_janela in janelas:
        res, _ = _base._roda_janela(CAPITAL, FOLGA_PRODUCAO, dias_janela)
        trades = list(res.trades)
        por_dia = _por_dia(trades)
        ordem = _ordem(por_dia)
        n_stops_total = sum(1 for t in trades if t.exit_reason.value == "stop")
        print("\n" + "=" * 112)
        print(f"JANELA: {nome}  ({len(dias_janela)} pregoes, {len(por_dia)} com operacao, "
              f"{len(trades)} trades, {n_stops_total} stops)")
        print("=" * 112, flush=True)

        ataque1_sobrevivencia(trades, ordem, por_dia)
        ataque2_causalidade_reversa(por_dia)
        ataque3_permutacao(trades, por_dia,
                            n_perm=N_PERM_PRINCIPAL if nome.startswith("HISTORICO") else 8000)
        ataque4_duracao(trades, ordem)
        ataque5_mesma_hora(trades, ordem)

    ataque6_robustez(dias)

    print("\n\nFIM.")


if __name__ == "__main__":
    main()
