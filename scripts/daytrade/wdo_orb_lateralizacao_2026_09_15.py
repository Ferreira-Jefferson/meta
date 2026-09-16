"""LATERALIZACAO (2026-09-15) -- o wdo_orb opera melhor em mercado parado?

## A pergunta do dono

"O sistema consegue identificar lateralizacao do mercado, em varios minutos?
Podemos medir para descobrir quais sao os resultados quando se opera em
lateralizacao."

Resposta curta da PRIMEIRA parte: hoje NAO. O `wdo_orb` mede a LARGURA da
faixa dos 15 minutos de abertura (`_range_hi`/`_range_lo`) e usa isso so' para
dimensionar o stop, clampeado entre 20 e 30 ticks. Largura nao e'
lateralizacao, e ela nunca decide se o robo opera.

## Por que isto NAO e' o filtro de agitacao que ja' caiu

O teste de 2026-09-14 (H2, 1 confirmacao em 8) e as 15 variaveis do perfil
(0 de 15 passam Benjamini-Hochberg) mediram QUANTO o mercado se mexe --
volume, amplitude, velocidade, numero de negocios -- e PARA ONDE ele foi nos
ultimos minutos (`retorno_5min_ticks`, `alinhamento_ticks`).

Nenhuma delas mede EFICIENCIA: a razao entre o deslocamento liquido e o
caminho percorrido. E' uma coisa diferente das duas anteriores, e e' a que
separa os dois regimes que a amplitude confunde:

    amplitude ALTA + deslocamento ALTO  = tendencia forte
    amplitude ALTA + deslocamento BAIXO = LATERALIZACAO violenta

A amplitude e' grande nos dois casos. O `retorno_5min` e' grande so' num, mas
sozinho nao distingue "andou 10 ticks porque foi direto" de "andou 10 ticks
depois de percorrer 90". A razao distingue.

## A medida: razao de eficiencia de Kaufman, sobre fechamentos de MINUTO

    ER_N = (fecha[ts] - fecha[ts-N]) / soma(|variacoes minuto a minuto|)

Vive em [-1, +1] por construcao, sem constante arbitraria de escala: +1 e'
subida em linha reta, -1 queda em linha reta, 0 e' vaivem que nao foi a lugar
nenhum. O SINAL e' direcao; o MODULO e' o regime. Aqui interessa o modulo --
|ER| perto de 0 e' lateralizacao.

ARMADILHA JA' MEDIDA NESTE REPO, nao repetir: sobre TICK a soma do caminho e'
enorme (~130 mil negocios num pregao) e o ER de qualquer janela desaba para
~0,002 -- mede microestrutura, nao regime. Por isso o calculo e' sobre
fechamento de MINUTO, reamostrado da propria base de tick. Ver
`wdof1_tendencia_confirmacao_2026_08_28.py`, que usou a mesma regua no WDO F1
para outra pergunta (direcao como confirmacao, nao regime).

"Varios minutos" (pedido do dono) = 5, 15, 30 e 60 minutos antes do sinal,
mais a janela desde a abertura do pregao.

## A medida ESPECIFICA de ORB, que a ER nao captura

`dentro_faixa_pct`: dos minutos entre o fim da faixa de 15 min e o instante do
sinal, que fracao fechou DENTRO de [faixa_lo, faixa_hi]. Um pregao que passa o
tempo todo voltando para dentro da faixa de abertura e' lateral no sentido que
mais importa para um robo de rompimento -- e essa e' informacao que o robo ja'
tem em maos e joga fora.

## A HIPOTESE, com direcao declarada ANTES de medir

Isto nao e' pesca. O mecanismo vem do que ja' foi medido: a perna de FADE paga
(+41,60/op no IS e +44,50 no OOS) e a perna de ROMPIMENTO esta quebrada
(+17,28 no IS e -8,60 no OOS). Fade ganhar e rompimento perder E' a assinatura
de mercado lateral. Ou seja, a suspeita e' que o `wdo_orb` ja' seja na pratica
um robo de lateralizacao e nao saiba disso.

Disso sai uma predicao ARRISCADA, que pode dar errado:

    |ER| BAIXO (lateral)   -> fade melhor, rompimento pior
    |ER| ALTO  (tendencia) -> rompimento melhor, fade pior

Criterio congelado agora, antes de ver o numero: o efeito so' conta se tiver
o MESMO SENTIDO no IS e no OOS_LIMPO. Sentido trocado entre as duas janelas
cegas REFUTA -- e' o mesmo sign-flip que ja' matou o filtro dia/hora, os 7
sinais de timing, os 5 ajustes estruturais e o filtro de agitacao. Efeito que
so' aparece na DESCOBERTA nao conta para nada: ela gerou as hipoteses.

## O que este script NAO faz

Nao filtra, nao decide, nao promove nada. E' FASE 1, descritiva: mede se
existe estrutura e se ela tem o sentido previsto. Se passar, a fase 2 mede o
gating no desenho de execucao vigente, com bootstrap emparelhado por pregao e
criterio congelado -- exatamente como a familia de excursao parcial foi
medida e encerrada hoje. Ver a memoria
`wdo_orb_devolucao_recuperacao_refutado_2026_09_15`.

Uso: `python -u scripts/daytrade/wdo_orb_lateralizacao_2026_09_15.py`
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from wdo_orb_4semanas_coleta_2026_09_14 import (  # noqa: E402
    CAPITAL_PARTIDA_BRL, TICK_SIZE, WdoOrbInstrumentado, carregar_bars,
    monta_config,
)
from wdo_orb_fade_agitacao_is_oos_2026_09_14 import (  # noqa: E402
    JANELAS, classifica_saida, pregoes_da_janela,
)

SAIDA = RAIZ / "scratch" / "wdo_orb_lateralizacao_2026_09_15"
MAX_WORKERS = min(12, (os.cpu_count() or 4))

#: "varios minutos" -- as janelas de retrovisor do ER, em minutos.
LOOKBACKS = (5, 15, 30, 60)
#: minimo de fechamentos de minuto para a janela valer. Abaixo disso o ER e'
#: ruido de 2 pontos, e chutar 0 seria AFIRMAR "nao ha direcao".
MIN_MINUTOS = 4


def er_kaufman(closes: pd.Series) -> float:
    """Razao de eficiencia com sinal. `nan` se a janela for curta demais ou se
    o caminho for zero (preco literalmente parado -- indefinido, nao 0)."""
    if len(closes) < MIN_MINUTOS:
        return float("nan")
    caminho = float(np.abs(np.diff(closes.to_numpy())).sum())
    if caminho <= 0.0:
        return float("nan")
    return float((closes.iloc[-1] - closes.iloc[0]) / caminho)


def roda_pregao(dia: str) -> list[dict]:
    bars = carregar_bars(dia, dia)
    if bars.empty:
        return []

    strat = WdoOrbInstrumentado()          # producao, alvo 1,5x
    res = run_intraday_backtest(bars, strat, monta_config(strat, CAPITAL_PARTIDA_BRL))
    if not res.trades:
        return []

    # fechamento de MINUTO, reamostrado do proprio tick (ver a armadilha na
    # docstring: sobre tick o ER desaba para ~0,002 e mede microestrutura).
    minuto = bars["close"].resample("1min").last().dropna()

    ordens = sorted(strat._log_ordens, key=lambda o: o["sinal_ts"])
    linhas = []
    for t in sorted(res.trades, key=lambda x: x.entry_ts):
        ordem = None
        for o in ordens:
            if o["sinal_ts"] <= t.entry_ts:
                ordem = o
            else:
                break
        if ordem is None:
            continue

        # o instante da DECISAO, nao o do preenchimento: e' nele que um filtro
        # teria de responder, e e' o unico que nao olha para o futuro.
        ts_sinal = pd.Timestamp(ordem["sinal_ts"])
        reg: dict = {
            "data": dia,
            "sinal_utc": ts_sinal.strftime("%H:%M:%S"),
            "tipo": ordem["tipo"],
            "side": t.side,
            "faixa_ticks": ordem["faixa_ticks"],
        }

        for n in LOOKBACKS:
            jan = minuto.loc[ts_sinal - pd.Timedelta(minutes=n):ts_sinal]
            er = er_kaufman(jan)
            reg[f"er_{n}min"] = round(er, 4) if er == er else float("nan")
            reg[f"aber_{n}min"] = abs(er) if er == er else float("nan")

        desde = minuto.loc[:ts_sinal]
        er_ab = er_kaufman(desde)
        reg["er_abertura"] = round(er_ab, 4) if er_ab == er_ab else float("nan")
        reg["aber_abertura"] = abs(er_ab) if er_ab == er_ab else float("nan")

        # lateralizacao no sentido do ORB: quanto do tempo pos-faixa o preco
        # passou DE VOLTA dentro da faixa de abertura.
        hi, lo = ordem["faixa_hi"], ordem["faixa_lo"]
        if hi is not None and lo is not None:
            pos = minuto.loc[:ts_sinal]
            pos = pos.iloc[15:] if len(pos) > 15 else pos.iloc[0:0]
            # MIN_MINUTOS tambem aqui: com 1 minuto pos-faixa a fracao so' pode
            # dar 0% ou 100%, e os dois extremos cairiam direto nos tercos
            # como se fossem regime. Sinal que rompe logo depois da faixa nao
            # tem historia suficiente para ser chamado de lateral ou nao.
            reg["dentro_faixa_pct"] = (
                round(100.0 * float(((pos >= lo) & (pos <= hi)).mean()), 1)
                if len(pos) >= MIN_MINUTOS else float("nan"))
            reg["minutos_pos_faixa"] = int(len(pos))
        else:
            reg["dentro_faixa_pct"] = float("nan")
            reg["minutos_pos_faixa"] = 0

        pnl_ticks = (((t.exit_price - t.entry_price) if t.side == "long"
                      else (t.entry_price - t.exit_price)) / TICK_SIZE)
        razao = (t.exit_reason.value if hasattr(t.exit_reason, "value")
                 else str(t.exit_reason))
        reg["pnl_brl"] = round(t.pnl_brl, 2)
        reg["venceu"] = int(t.pnl_brl > 0)
        reg["saida_efetiva"] = classifica_saida(razao, pnl_ticks, ordem["alvo_ticks"])
        linhas.append(reg)
    return linhas


def tabela_por_faixa(df: pd.DataFrame, coluna: str, cortes: tuple[float, float],
                     rotulo: str) -> pd.DataFrame:
    """Resultado por terco da medida, separado por PERNA -- e' a separacao que
    a hipotese preve, entao ela tem de aparecer na tabela, nao no agregado."""
    def bucket(v):
        if v != v:
            return "indefinido"
        if v <= cortes[0]:
            return "1-lateral"
        if v <= cortes[1]:
            return "2-meio"
        return "3-direcional"

    d = df.copy()
    d["bucket"] = d[coluna].map(bucket)
    linhas = []
    for perna in ("rompimento", "fade", "TODAS"):
        s0 = d if perna == "TODAS" else d[d.tipo == perna]
        for b in sorted(s0.bucket.unique()):
            s = s0[s0.bucket == b]
            linhas.append({
                "medida": rotulo, "perna": perna, "faixa": b, "n": len(s),
                "liquido": round(s.pnl_brl.sum(), 2),
                "rs_por_op": round(s.pnl_brl.mean(), 2) if len(s) else float("nan"),
                "win_pct": round(100.0 * s.venceu.mean(), 1) if len(s) else float("nan"),
            })
    return pd.DataFrame(linhas)


def main() -> None:
    dias_por_janela, todos = {}, []
    for rotulo, ini, fim, _ in JANELAS:
        dias = pregoes_da_janela(ini, fim)
        dias_por_janela[rotulo] = set(dias)
        todos.extend(dias)
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(f"[lateral] {len(todos)} pregoes, producao (alvo 1,5x), "
          f"{MAX_WORKERS} processos\n", flush=True)

    linhas, feitos = [], 0
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futuros = {pool.submit(roda_pregao, d): d for d in todos}
        for fut in as_completed(futuros):
            feitos += 1
            try:
                linhas.extend(fut.result())
            except Exception as exc:
                print(f"[{futuros[fut]}] ERRO: {exc!r}", flush=True)
            if feitos % 25 == 0:
                print(f"  ... {feitos}/{len(todos)}", flush=True)

    df = pd.DataFrame(linhas)
    df["janela"] = df["data"].map(
        lambda d: next(r for r, s in dias_por_janela.items() if d in s))
    df.to_csv(SAIDA / "01_lateralizacao_trades.csv", index=False, encoding="utf-8")
    print(f"\n[lateral] {len(df)} operacoes -> 01_lateralizacao_trades.csv\n", flush=True)

    medidas = [(f"aber_{n}min", f"|ER| {n}min") for n in LOOKBACKS]
    medidas += [("aber_abertura", "|ER| abertura"),
                ("dentro_faixa_pct", "% dentro da faixa")]

    # Cortes de terco congelados no IS e APLICADOS as outras janelas. Recalcular
    # o terco dentro de cada janela testaria "acima do terco local", que e'
    # outro criterio -- e foi assim que a agitacao virou achado no proprio
    # conjunto que a gerou. E' a mesma decisao do LIMIARES_DESCOBERTA.
    is_df = df[df.janela == "IS"]
    cortes_is = {}
    for col, _ in medidas:
        v = is_df[col].dropna()
        cortes_is[col] = ((float(v.quantile(1 / 3)), float(v.quantile(2 / 3)))
                          if len(v) >= 9 else (float("nan"), float("nan")))

    print("=" * 120)
    print("CORTES DE TERCO CONGELADOS NO IS (aplicados as tres janelas)")
    print("=" * 120)
    print(pd.DataFrame([{"medida": r, "corte_baixo": round(cortes_is[c][0], 4),
                         "corte_alto": round(cortes_is[c][1], 4)}
                        for c, r in medidas]).to_string(index=False))

    todas_tabs = []
    for rotulo, _, _, nota in JANELAS:
        sub = df[df.janela == rotulo]
        print("\n" + "=" * 120)
        print(f"JANELA {rotulo}  ({len(dias_por_janela[rotulo])} pregoes, "
              f"{len(sub)} operacoes) -- {nota}")
        print("=" * 120)
        for col, rot in medidas:
            if cortes_is[col][0] != cortes_is[col][0]:
                continue
            tab = tabela_por_faixa(sub, col, cortes_is[col], rot)
            tab.insert(0, "janela", rotulo)
            todas_tabs.append(tab)
            print(tab[tab.perna != "TODAS"].to_string(index=False))
            print()

    tudo = pd.concat(todas_tabs, ignore_index=True)
    tudo.to_csv(SAIDA / "02_lateralizacao_por_faixa.csv", index=False, encoding="utf-8")

    # ---- o teste que decide: o SENTIDO bate nas duas janelas cegas? --------
    print("=" * 120)
    print("O SENTIDO PREVISTO SE REPETE NAS DUAS JANELAS CEGAS?")
    print("  previsto ANTES de medir: lateral -> fade melhor que direcional;")
    print("                           direcional -> rompimento melhor que lateral")
    print("=" * 120)
    ver = []
    for col, rot in medidas:
        if cortes_is[col][0] != cortes_is[col][0]:
            continue
        linha = {"medida": rot}
        for rotulo in ("IS", "OOS_LIMPO", "DESCOBERTA"):
            t = tudo[(tudo.janela == rotulo) & (tudo.medida == rot)]
            for perna, sigla in (("fade", "fade"), ("rompimento", "romp")):
                p = t[t.perna == perna]
                lat = p[p.faixa == "1-lateral"]
                dir_ = p[p.faixa == "3-direcional"]
                delta = ((lat.rs_por_op.iloc[0] - dir_.rs_por_op.iloc[0])
                         if len(lat) and len(dir_) else float("nan"))
                linha[f"{rotulo[:3]}_{sigla}"] = round(delta, 2)
        ver.append(linha)
    v = pd.DataFrame(ver)
    print("  (valor = R$/op no LATERAL menos R$/op no DIRECIONAL, por perna)")
    print("  previsto: coluna _fade POSITIVA, coluna _romp NEGATIVA\n")
    print(v.to_string(index=False))

    print("\n  veredito por medida (so' IS e OOS_LIMPO votam):")
    for _, r in v.iterrows():
        ok_f = (r.get("IS_fade", float("nan")) > 0) and (r.get("OOS_fade", float("nan")) > 0)
        ok_r = (r.get("IS_romp", float("nan")) < 0) and (r.get("OOS_romp", float("nan")) < 0)
        print(f"    {r['medida']:<22} fade {'OK ' if ok_f else 'NAO'} | "
              f"rompimento {'OK ' if ok_r else 'NAO'} | "
              f"{'SENTIDO CONFIRMADO' if (ok_f and ok_r) else 'nao replica'}")
    v.to_csv(SAIDA / "03_sentido_entre_janelas.csv", index=False, encoding="utf-8")
    print(f"\n[lateral] arquivos em {SAIDA}")


if __name__ == "__main__":
    main()
