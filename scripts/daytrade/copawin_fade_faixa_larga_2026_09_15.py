# -*- coding: utf-8 -*-
"""copa_win: existe FADE executável no toque da borda, em lateralização VIOLENTA?

Pergunta do dono, 2026-09-15 -- FASE A de uma investigação em duas fases.

## O que já foi medido HOJE e não é remedido aqui

`copawin_lateralizacao_2026_09_15.py` (log ao lado) achou: (1) a
lateralização é mensurável e o sinal sobrevive ao OOS -- em 5 de 6 medidas o
terço lateral rende MENOS que o direcional nas DUAS janelas; (2) filtrar
ENTRADA por regime é REFUTADO, 0 de 12 células -- não existe subconjunto
perdedor pra remover, todo balde tem expectativa positiva, e um filtro
binário só pode subtrair.

## A hipótese desta FASE A

Lateralização aponta para FADE (apostar que a borda segura), não para
rompimento. Mas fade dentro de faixa normal é muitos trades PEQUENOS, e isso
não paga o pedágio do WIN: 1 round-trip custa **7,5 pontos** (tarifa 2,5
pontos, `FUTURES_FEE_ROUND_TRIP_BRL=R$0,50` / `point_value_brl=R$0,20` por
ponto = 2,5 pontos; mais 1 tick = 5 pontos de slippage na perna de entrada A
MERCADO -- ver a docstring de `strategy.daytrade.lab.copa_win`). A brecha
nunca medida: quando a faixa de 10 barras está LARGA (amplitude alta) mas
POUCO percorrida em linha reta (eficiência baixa) -- lateralização VIOLENTA,
não lateralização mansa -- o alvo de um fade da borda até o meio/outra borda
tem dezenas de pontos, espaço suficiente pra pagar o pedágio. Amplitude
sozinha NÃO isola esse regime (tendência forte também tem amplitude alta);
é a RAZÃO teto-piso / soma dos ranges que distingue.

Pergunta exata: depois de um TOQUE na borda da faixa de 10 barras SEM
rompimento, no regime amplitude-alta+eficiência-baixa, o preço volta pra
dentro o suficiente pra pagar 7,5 pontos -- e isso replica no IS e no OOS?

## Isto NÃO é backtest

Não há posição, não há motor, não há capital. É uma medição de PREÇO: dado
um evento de toque, o que o mercado fez depois. A FASE B (condicional, ver
o critério congelado abaixo) é que vira estratégia de verdade com o motor.

## Base e convenção anti-look-ahead -- EXATAMENTE a do robô

Base: `_df()` de `copawin_encerrar_mais_cedo_2026_09_14.py` (WIN@ M1, 191
pregões completos, >=400 barras), reaproveitada via `importlib` -- é o
padrão dos scripts irmãos (`copawin_preditor_stop_2026_09_15.py`).

Faixa: janela ROLANTE de `janela_rompimento` barras -- lido da instância de
PRODUÇÃO (`_KWARGS_PADRAO["copa_win"]`, nunca digitado: hoje é 10, mas se
mudar lá este script muda sozinho). Na barra `t`, a faixa é a `janela`
barras ANTERIORES a `t` -- a barra corrente NUNCA entra na faixa contra a
qual é comparada, mesma disciplina do `finally` de `CopaWin.on_bar` (o
`self._faixa.append(bar)` só roda DEPOIS da decisão). `teto=max(high)`,
`piso=min(low)` dessas `janela` barras.

Evento "toque sem rompimento" na barra `t`:
  - borda de BAIXO: `low<=piso` E `close>=piso` (tocou e voltou pra dentro)
    -> fade LONG, entrada no `close` da barra do toque.
  - borda de CIMA: `high>=teto` E `close<=teto` -> fade SHORT.
  - as duas bordas tocadas na mesma barra -> evento AMBÍGUO, descartado.
Note que isto é o COMPLEMENTO do sinal do robô (`close>teto` ou `close<piso`
dispara ROMPIMENTO, não fade) -- as duas populações não se sobrepõem.

Janela operável: `barras_hoje > aquecimento_barras` (lido da instância, hoje
45) E hora da barra ANTES do corte de achatamento de produção
(`backtest.intraday.profiles.profile_for("WIN@").flatten_cut_time`, que já
embute `FOLGA_ACHATAMENTO_MINUTOS` -- nenhum horário digitado a mão). O
caminho PARA FRENTE de cada evento também para no corte: barras depois dele
não entram no MFE/MAE nem na corrida alvo/stop, porque o robô real estaria
flat ali.

## Regime, cortes CONGELADOS no IS

Em cada faixa de 10 barras: `amplitude=média(high-low)` (é o `_volatilidade()`
do robô) e `eficiência=(teto-piso)/soma(high-low)` das mesmas 10 barras
(baixo = lateral/serrilhado; pode passar de 1,0 se houver gap entre barras
consecutivas -- caso raro, não é bug, é o preço tendo pulado sem negociar).

Corte IS/OOS: 2026-06-13 (padrão do repo). Quantis (`amplitude>=q60`,
`eficiência<=q40`) calculados SÓ na distribuição IS dos EVENTOS (não do
histórico de barras inteiro) e aplicados como limiar ABSOLUTO ao OOS --
recalcular quantil dentro do OOS testaria outro critério, não confirmação.

Quatro células (partição completa) + o agregado de TODOS os eventos como
nulo:
  * ALVO            -- amplitude alta + eficiência baixa (a hipótese)
  * ampl.alta+efic.alta   -- tendência forte (complementar)
  * ampl.baixa+efic.baixa -- lateral mansa (complementar)
  * ampl.baixa+efic.alta  -- pouco espaço, movimento limpo (complementar)

## A medição para frente

MFE (a favor do fade) e MAE (contra, além da borda) em pontos, nos
horizontes 5/10/15/30/60 minutos e "até o corte de achatamento".

Corrida alvo(A) x stop(S) -- geometria ESCALADA pela largura da própria
faixa (`largura=teto-piso`), nunca fixa:
  A em {0,3; 0,5; 1,0} x largura   S em {0,3; 0,5} x largura   (grade 3x2)

GEOMETRIA PRIMÁRIA CONGELADA ANTES DE RODAR (não escolhida depois de ver o
número): **A=0,5 x largura, S=0,3 x largura** -- ponto médio da grade, RR
~1,67:1. É esta que decide o critério de passagem; as outras 5 combinações
da grade entram só como tabela de robustez.

### ARMADILHA OBRIGATÓRIA

Barra M1 OHLC não diz se o `high` veio antes do `low`. Alvo e stop na MESMA
barra contam como STOP (pessimista). Se a corrida termina sem tocar nenhum
dos dois até o corte de achatamento, o resultado do evento é o MARK-TO-MARKET
no último `close` disponível antes do corte (é o que o robô real faria --
seria flatten ali) -- não é "censurado" no sentido de ficar fora da conta de
P&L, só fica marcado como "nenhum" na contagem de alvo/stop.

## O nulo que decide

Por evento: pontos líquidos = pontos da corrida MENOS 7,5 (custo do
round-trip, já embutido, nunca reportado bruto). Por célula/janela:
n, média, desvio, IC95% da média (normal, `1,96 x dp/sqrt(n)`), win%
(fração com pontos líquidos > 0, IC95% Wilson -- mesma `ic95()` do resto do
repo) e breakeven empírico (`perda_média/(ganho_médio+perda_média)`, sobre
pontos líquidos). As duas leituras (R$/op>0 e win%>breakeven) têm de
concordar -- se discordarem, parar e investigar antes de ler o resto.

## Critério de passagem para a FASE B (congelado, escrito ANTES de rodar)

O achado só conta se, na geometria PRIMÁRIA:
  1. célula ALVO tem >=30 eventos no IS E no OOS (senão "indefinido por
     amostra", não veredito);
  2. pontos líquidos/op médios da célula ALVO são POSITIVOS no IS E no OOS;
  3. média da célula ALVO é MAIOR que a média de CADA UMA das 3 células
     complementares, nas DUAS janelas.
Sinal trocado entre IS e OOS em qualquer perna REFUTA -- foi o que matou o
filtro dia/hora, os 7 sinais de timing, os 5 ajustes estruturais, o filtro
de agitação e as 24 regras de gestão (ver CLAUDE.md/LICOES_DE_PRODUCAO.md).

Se REFUTADO: reporta e para. FASE B só roda se os 3 itens acima passarem.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/copawin_fade_faixa_larga_2026_09_15.py`
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "_base", Path(__file__).with_name("copawin_encerrar_mais_cedo_2026_09_14.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

SYMBOL = _base.SYMBOL                      # "WIN@"
CORTE_OOS = pd.Timestamp("2026-06-13").date()

CUSTO_ROUNDTRIP_PONTOS = 7.5   # tarifa 2,5 + 1 tick (5 pontos) de slippage na
                                # entrada a mercado -- docstring de copa_win.py
A_FRACOES = [0.3, 0.5, 1.0]
S_FRACOES = [0.3, 0.5]
GEOMETRIA_PRIMARIA = (0.5, 0.3)   # congelada ANTES de rodar -- ver docstring
HORIZONTES_MIN = [5, 10, 15, 30, 60]
Q_AMPLITUDE = 0.60
Q_EFICIENCIA = 0.40
MIN_N_VEREDITO = 30


def br(x, casas=2):
    if x is None or (isinstance(x, float) and (x != x)):
        return "--"
    s = f"{x:,.{casas}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


# ---------------------------------------------------------------------------
# eventos
# ---------------------------------------------------------------------------

def _construir_eventos(df, dias, strat, corte_achatamento):
    janela = strat.janela_rompimento
    aquecimento = strat.aquecimento_barras
    eventos = []
    n_ambiguos = 0
    n_sem_forward = 0
    n_faixa_degenerada = 0

    for d in dias:
        bars = df[df.index.date == d]
        n = len(bars)
        if n <= janela:
            continue
        highs = bars["high"].to_numpy()
        lows = bars["low"].to_numpy()
        closes = bars["close"].to_numpy()
        times = bars.index

        elig_time = np.array([t.time() < corte_achatamento for t in times])
        if not elig_time.any():
            continue
        cutoff_idx = int(np.nonzero(elig_time)[0][-1])

        for i in range(janela, n):
            barras_hoje = i + 1
            if barras_hoje <= aquecimento:
                continue
            if i > cutoff_idx or not elig_time[i]:
                continue

            w_high = highs[i - janela:i]
            w_low = lows[i - janela:i]
            teto = float(w_high.max())
            piso = float(w_low.min())
            largura = teto - piso
            if largura <= 0:
                n_faixa_degenerada += 1
                continue
            amplitude = float((w_high - w_low).mean())
            soma_range = float((w_high - w_low).sum())
            eficiencia = (largura / soma_range) if soma_range > 0 else float("nan")

            low_i, high_i, close_i = float(lows[i]), float(highs[i]), float(closes[i])
            tocou_baixo = (low_i <= piso) and (close_i >= piso)
            tocou_cima = (high_i >= teto) and (close_i <= teto)
            if tocou_baixo and tocou_cima:
                n_ambiguos += 1
                continue
            if tocou_baixo:
                lado, borda = "long", piso
            elif tocou_cima:
                lado, borda = "short", teto
            else:
                continue

            if i >= cutoff_idx:
                n_sem_forward += 1
                continue

            fwd_high = highs[i + 1:cutoff_idx + 1]
            fwd_low = lows[i + 1:cutoff_idx + 1]
            fwd_close = closes[i + 1:cutoff_idx + 1]
            fwd_times = times[i + 1:cutoff_idx + 1]
            if len(fwd_high) == 0:
                n_sem_forward += 1
                continue

            eventos.append(dict(
                data=d, ts=times[i], lado=lado, entry=close_i, borda=borda,
                teto=teto, piso=piso, largura=largura, amplitude=amplitude,
                eficiencia=eficiencia,
                fwd_high=fwd_high, fwd_low=fwd_low, fwd_close=fwd_close,
                fwd_times=fwd_times,
            ))

    meta = dict(n_ambiguos=n_ambiguos, n_sem_forward=n_sem_forward,
                n_faixa_degenerada=n_faixa_degenerada)
    return eventos, meta


def _mfe_mae(ev, horizonte_min=None):
    lado, entry, borda = ev["lado"], ev["entry"], ev["borda"]
    fwd_high, fwd_low, fwd_times = ev["fwd_high"], ev["fwd_low"], ev["fwd_times"]
    if horizonte_min is None:
        sub_high, sub_low = fwd_high, fwd_low
    else:
        limite = ev["ts"] + pd.Timedelta(minutes=horizonte_min)
        mask = fwd_times <= limite
        sub_high, sub_low = fwd_high[mask], fwd_low[mask]
    if len(sub_high) == 0:
        return float("nan"), float("nan")
    if lado == "long":
        mfe = float(sub_high.max() - entry)
        mae = float(max(0.0, borda - sub_low.min()))
    else:
        mfe = float(entry - sub_low.min())
        mae = float(max(0.0, sub_high.max() - borda))
    return mfe, mae


def _race(ev, a_frac, s_frac):
    """Alvo A x stop S, ambos = fração x largura da faixa. Mesma barra
    tocando os dois -> STOP (pessimista, ver a ARMADILHA na docstring do
    módulo). Sem decisão até o corte -> mark-to-market no último close."""
    lado, entry, largura = ev["lado"], ev["entry"], ev["largura"]
    A = a_frac * largura
    S = s_frac * largura
    fwd_high, fwd_low, fwd_close = ev["fwd_high"], ev["fwd_low"], ev["fwd_close"]
    if lado == "long":
        alvo_px, stop_px = entry + A, entry - S
        for h, l in zip(fwd_high, fwd_low):
            if l <= stop_px:
                return "stop", -S
            if h >= alvo_px:
                return "alvo", A
        return "nenhum", float(fwd_close[-1] - entry)
    else:
        alvo_px, stop_px = entry - A, entry + S
        for h, l in zip(fwd_high, fwd_low):
            if h >= stop_px:
                return "stop", -S
            if l <= alvo_px:
                return "alvo", A
        return "nenhum", float(entry - fwd_close[-1])


def _celula(e, q_amp, q_efi):
    alta_amp = e["amplitude"] >= q_amp
    baixa_efi = e["eficiencia"] <= q_efi
    if alta_amp and baixa_efi:
        return "ALVO (ampl.alta+efic.baixa)"
    if alta_amp and not baixa_efi:
        return "ampl.alta+efic.alta"
    if not alta_amp and baixa_efi:
        return "ampl.baixa+efic.baixa"
    return "ampl.baixa+efic.alta"


def _janela_nome(e):
    return "IS" if e["data"] < CORTE_OOS else "OOS"


def _stats(subset, a_frac, s_frac):
    n = len(subset)
    if n == 0:
        return dict(n=0)
    pontos_liq, outcomes = [], []
    for e in subset:
        outcome, pontos = e["race"][(a_frac, s_frac)]
        pontos_liq.append(pontos - CUSTO_ROUNDTRIP_PONTOS)
        outcomes.append(outcome)
    pontos_liq = np.array(pontos_liq)
    media = float(pontos_liq.mean())
    dp = float(pontos_liq.std(ddof=1)) if n > 1 else 0.0
    ic_media = 1.959964 * dp / math.sqrt(n) if n > 1 else float("nan")
    g = pontos_liq[pontos_liq > 0]
    p = pontos_liq[pontos_liq <= 0]
    gm = float(g.mean()) if len(g) else 0.0
    pm = float(np.abs(p).mean()) if len(p) else 0.0
    be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
    win = len(g) / n
    lo, hi = _base.ic95(len(g), n)
    return dict(
        n=n, media=media, dp=dp, ic_media=ic_media, win=win, be=be, lo=lo, hi=hi,
        n_alvo=sum(1 for o in outcomes if o == "alvo"),
        n_stop=sum(1 for o in outcomes if o == "stop"),
        n_nenhum=sum(1 for o in outcomes if o == "nenhum"),
        r_brl_op=media * POINT_VALUE,
    )


def main() -> None:
    from backtest.intraday.profiles import profile_for

    strat = _base._construir_estrategia()
    global POINT_VALUE
    POINT_VALUE = strat.point_value_brl
    tick = strat.tick_size

    profile = profile_for(SYMBOL)
    corte_achatamento = profile.flatten_cut_time

    print("=" * 100)
    print("CONFERÊNCIA -- parâmetros lidos da instância de PRODUÇÃO (nunca digitados)")
    print("=" * 100)
    print(f"janela_rompimento (faixa) = {strat.janela_rompimento} barras")
    print(f"aquecimento_barras        = {strat.aquecimento_barras}")
    print(f"tick_size                 = {tick} pontos (R${POINT_VALUE:.2f}/ponto)")
    print(f"corte de achatamento      = {corte_achatamento} (UTC, já inclui a folga de produção)")
    print(f"custo round-trip assumido = {CUSTO_ROUNDTRIP_PONTOS} pontos "
          f"(R${CUSTO_ROUNDTRIP_PONTOS * POINT_VALUE:.2f}/contrato)")
    assert strat.janela_rompimento == 10, "janela_rompimento mudou na produção -- pare e confira"
    assert strat.aquecimento_barras == 45, "aquecimento_barras mudou na produção -- pare e confira"
    assert abs(tick - 5.0) < 1e-9, "tick_size do WIN@ mudou -- pare e confira"
    print("conferência OK.\n")

    df, dias = _base._df()
    print(f"base: {len(dias)} pregões completos ({dias[0]} .. {dias[-1]})")
    is_dias = [d for d in dias if d < CORTE_OOS]
    oos_dias = [d for d in dias if d >= CORTE_OOS]
    print(f"IS: {len(is_dias)} pregões  |  OOS: {len(oos_dias)} pregões\n")

    eventos, meta = _construir_eventos(df, dias, strat, corte_achatamento)
    print(f"eventos de toque-sem-rompimento: {len(eventos)}")
    print(f"  descartados por ambiguidade (tocou as 2 bordas na mesma barra): {meta['n_ambiguos']}")
    print(f"  descartados por faixa degenerada (teto<=piso): {meta['n_faixa_degenerada']}")
    print(f"  descartados por falta de barra seguinte antes do corte: {meta['n_sem_forward']}\n")

    for e in eventos:
        e["janela"] = _janela_nome(e)

    eventos_is = [e for e in eventos if e["janela"] == "IS"]
    amp_is = np.array([e["amplitude"] for e in eventos_is])
    efi_is = np.array([e["eficiencia"] for e in eventos_is])
    q_amp = float(np.quantile(amp_is, Q_AMPLITUDE))
    q_efi = float(np.quantile(efi_is, Q_EFICIENCIA))
    print(f"quantis CONGELADOS no IS (n={len(eventos_is)} eventos IS):")
    print(f"  amplitude >= q{int(Q_AMPLITUDE*100)} = {q_amp:.2f} pontos ({q_amp/tick:.2f} ticks)")
    print(f"  eficiência <= q{int(Q_EFICIENCIA*100)} = {q_efi:.4f}\n")

    for e in eventos:
        e["celula"] = _celula(e, q_amp, q_efi)

    print("calculando corrida alvo/stop (grade 3x2) e MFE/MAE por evento...")
    for e in eventos:
        e["race"] = {}
        for a in A_FRACOES:
            for s in S_FRACOES:
                e["race"][(a, s)] = _race(e, a, s)
        for h in HORIZONTES_MIN + [None]:
            mfe, mae = _mfe_mae(e, h)
            e.setdefault("mfe", {})[h] = mfe
            e.setdefault("mae", {})[h] = mae
    print("pronto.\n")

    celulas = [
        "ALVO (ampl.alta+efic.baixa)",
        "ampl.alta+efic.alta",
        "ampl.baixa+efic.baixa",
        "ampl.baixa+efic.alta",
    ]
    janelas = ["IS", "OOS"]

    # -----------------------------------------------------------------
    # tabela 1: geometria PRIMÁRIA, célula x janela (+ agregado)
    # -----------------------------------------------------------------
    a0, s0 = GEOMETRIA_PRIMARIA
    print("=" * 100)
    print(f"TABELA 1 -- geometria PRIMÁRIA congelada: alvo={a0}xlargura, stop={s0}xlargura")
    print("(pontos líquidos/op já com -7,5 pontos de custo embutidos)")
    print("=" * 100)
    header = (f"{'janela':6} {'célula':30} {'n':>5} {'pts.liq/op':>11} "
              f"{'±IC95':>9} {'R$/op':>9} {'win%':>7} {'IC95win':>15} "
              f"{'breakeven':>10} {'alvo/stop/nenhum':>18}")
    print(header)
    print("-" * len(header))

    resultados_primaria = {}
    for jn in janelas:
        subset_jn = [e for e in eventos if e["janela"] == jn]
        for cel in celulas + ["AGREGADO (todos)"]:
            subset = subset_jn if cel == "AGREGADO (todos)" else \
                [e for e in subset_jn if e["celula"] == cel]
            st = _stats(subset, a0, s0)
            resultados_primaria[(jn, cel)] = st
            if st["n"] == 0:
                print(f"{jn:6} {cel:30} {0:>5}")
                continue
            ic_win = f"[{st['lo']*100:.1f};{st['hi']*100:.1f}]"
            asn = f"{st['n_alvo']}/{st['n_stop']}/{st['n_nenhum']}"
            print(f"{jn:6} {cel:30} {st['n']:>5} {br(st['media']):>11} "
                  f"{br(st['ic_media']):>9} {br(st['r_brl_op']):>9} "
                  f"{st['win']*100:>6.1f}% {ic_win:>15} "
                  f"{st['be']*100:>9.1f}% {asn:>18}")
    print()

    # -----------------------------------------------------------------
    # tabela 2: grade completa, só célula ALVO, IS x OOS
    # -----------------------------------------------------------------
    print("=" * 100)
    print("TABELA 2 -- robustez: grade completa alvo x stop, só célula ALVO")
    print("=" * 100)
    header2 = (f"{'janela':6} {'A(xlargura)':>12} {'S(xlargura)':>12} {'n':>5} "
               f"{'pts.liq/op':>11} {'R$/op':>9} {'win%':>7} {'breakeven':>10}")
    print(header2)
    print("-" * len(header2))
    for jn in janelas:
        subset = [e for e in eventos if e["janela"] == jn and e["celula"] == celulas[0]]
        for a in A_FRACOES:
            for s in S_FRACOES:
                st = _stats(subset, a, s)
                marca = " <== primária" if (a, s) == GEOMETRIA_PRIMARIA else ""
                if st["n"] == 0:
                    print(f"{jn:6} {a:>12.1f} {s:>12.1f} {0:>5}{marca}")
                    continue
                print(f"{jn:6} {a:>12.1f} {s:>12.1f} {st['n']:>5} "
                      f"{br(st['media']):>11} {br(st['r_brl_op']):>9} "
                      f"{st['win']*100:>6.1f}% {st['be']*100:>9.1f}%{marca}")
    print()

    # -----------------------------------------------------------------
    # tabela 3: MFE/MAE por horizonte, célula ALVO x agregado
    # -----------------------------------------------------------------
    print("=" * 100)
    print("TABELA 3 -- MFE/MAE médio (pontos) por horizonte, ALVO x AGREGADO")
    print("=" * 100)
    header3 = (f"{'janela':6} {'célula':22} {'horizonte':>12} {'n':>5} "
               f"{'MFE méd':>9} {'MFE dp':>8} {'MAE méd':>9} {'MAE dp':>8}")
    print(header3)
    print("-" * len(header3))
    for jn in janelas:
        subset_jn = [e for e in eventos if e["janela"] == jn]
        for cel_nome, subset in (
            ("ALVO", [e for e in subset_jn if e["celula"] == celulas[0]]),
            ("AGREGADO", subset_jn),
        ):
            for h in HORIZONTES_MIN + [None]:
                mfes = np.array([e["mfe"][h] for e in subset if not math.isnan(e["mfe"][h])])
                maes = np.array([e["mae"][h] for e in subset if not math.isnan(e["mae"][h])])
                nome_h = "até corte" if h is None else f"{h}min"
                if len(mfes) == 0:
                    print(f"{jn:6} {cel_nome:22} {nome_h:>12} {0:>5}")
                    continue
                print(f"{jn:6} {cel_nome:22} {nome_h:>12} {len(mfes):>5} "
                      f"{br(mfes.mean()):>9} {br(mfes.std(ddof=1) if len(mfes)>1 else 0.0):>8} "
                      f"{br(maes.mean()):>9} {br(maes.std(ddof=1) if len(maes)>1 else 0.0):>8}")
    print()

    # -----------------------------------------------------------------
    # veredito do critério congelado
    # -----------------------------------------------------------------
    print("=" * 100)
    print("VEREDITO -- critério congelado ANTES de rodar (geometria primária "
          f"A={a0}xlargura, S={s0}xlargura)")
    print("=" * 100)

    r_alvo_is = resultados_primaria[("IS", celulas[0])]
    r_alvo_oos = resultados_primaria[("OOS", celulas[0])]

    amostra_ok = r_alvo_is["n"] >= MIN_N_VEREDITO and r_alvo_oos["n"] >= MIN_N_VEREDITO
    if not amostra_ok:
        print(f"INDEFINIDO POR AMOSTRA -- célula ALVO tem n_IS={r_alvo_is['n']}, "
              f"n_OOS={r_alvo_oos['n']} (mínimo exigido: {MIN_N_VEREDITO} nas DUAS janelas).")
        passou = False
    else:
        positivo_is = r_alvo_is["media"] > 0
        positivo_oos = r_alvo_oos["media"] > 0
        maior_que_complementares_is = all(
            r_alvo_is["media"] > resultados_primaria[("IS", c)]["media"]
            for c in celulas[1:] if resultados_primaria[("IS", c)]["n"] > 0
        )
        maior_que_complementares_oos = all(
            r_alvo_oos["media"] > resultados_primaria[("OOS", c)]["media"]
            for c in celulas[1:] if resultados_primaria[("OOS", c)]["n"] > 0
        )
        print(f"IS : n={r_alvo_is['n']:>5}  pts.liq/op={br(r_alvo_is['media'])}  "
              f"positivo={positivo_is}  vence complementares={maior_que_complementares_is}")
        print(f"OOS: n={r_alvo_oos['n']:>5}  pts.liq/op={br(r_alvo_oos['media'])}  "
              f"positivo={positivo_oos}  vence complementares={maior_que_complementares_oos}")
        passou = (positivo_is and positivo_oos and
                  maior_que_complementares_is and maior_que_complementares_oos)

    print()
    if passou:
        print("RESULTADO: PASSOU o critério congelado. FASE B autorizada (backtest de "
              "verdade com o motor, desenho de execução FECHADO).")
    else:
        print("RESULTADO: REFUTADO (ou indefinido). FASE B NÃO roda -- não inventar "
              "uma fase B pra salvar a hipótese.")
    print("=" * 100)


if __name__ == "__main__":
    main()
