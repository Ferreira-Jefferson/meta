# -*- coding: utf-8 -*-
"""Quanto do ALVO e do STOP cada operacao do `copa_win` de fato alcanca.

Pedido do dono (2026-09-11): "analisar quantos % do alvo ou stop que de fato
cada operacao alcanca para poder definir o alvo com base nessa informacao --
a estrategia diz que o alvo deve ser 100, mas em varios trades ele alcanca
60%, entao podemos testar se colocar o alvo a 60% do sugerido nao aumenta a
taxa de acerto do alvo e talvez mantenha o resultado positivo mesmo sem
depender tanto do tempo".

E' analise de EXCURSAO (MFE/MAE): para cada trade, o quanto o preco andou a
FAVOR (`mfe`) e CONTRA (`mae`) enquanto a posicao esteve aberta, medido em
FRACAO da distancia que a propria estrategia pediu naquela entrada.

MOTIVACAO, medida em `copawin_teto_perda_diagnostico_2026_09_11.py`: o alvo
de producao (`alvo_vol=19,0`) e' alcancado em 6,9% dos trades e 56,1% das
saidas sao por achatamento de fim de pregao. Na pratica o robo nao tem alvo,
tem RELOGIO -- e e' por isso que o resultado depende de onde o dia fechou.

O QUE ESTE SCRIPT RESPONDE (e o que ele NAO responde):

  * RESPONDE: se o alvo estivesse em X% do pedido, quantos trades teriam
    ENCOSTADO nele em algum momento da vida do trade. E' a taxa de acerto
    POTENCIAL por fracao.
  * NAO RESPONDE: quanto isso da em dinheiro. Baixar o alvo muda o que
    acontece DEPOIS -- o trade fecha mais cedo, o robo volta a poder entrar
    no mesmo pregao (`max_entradas_dia=10`), e a sequencia inteira do dia
    muda. Por isso a taxa aqui e' um TETO da melhora, nunca a previsao do
    resultado; quem mede resultado e' a varredura de `alvo_vol` que vem
    depois.

DUAS RESSALVAS DE METODO que precisam viajar com qualquer numero daqui:

  1. A excursao de um trade que morreu no STOP e' CENSURADA A DIREITA -- o
     stop encerrou a observacao, e nao da' para saber ate onde o preco teria
     ido a favor depois. Por isso a tabela separa por MOTIVO DE SAIDA em vez
     de so' agregar: misturar os dois puxa a media para baixo exatamente da
     mesma forma que estimar fila so' com as ordens que preencheram puxa
     para cima (item 4.21/4.22 de LICOES_DE_PRODUCAO.md, vies de
     sobrevivencia -- aqui ele anda para o outro lado).
  2. Dentro de uma barra M1 nao se sabe a ORDEM de `high` e `low`. Um trade
     cuja barra tocou o alvo novo E o stop na mesma barra fica ambiguo; o
     motor resolve isso de forma pessimista (o stop ganha) e a varredura
     herda essa convencao. Aqui a fracao usa o extremo da barra, entao ela e'
     OTIMISTA nesse caso de borda -- mais um motivo para a tabela ser teto.

Uso: `.venv/Scripts/python.exe -u scripts/daytrade/copawin_excursao_alvo_stop_2026_09_11.py`
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SYMBOL = "WIN@"
CAPITAL = 3_000.0          # nao censurado -- aqui a pergunta e' sobre a POPULACAO de trades
MIN_BARRAS_POR_PREGAO = 400
OOS_INICIO = pd.Timestamp("2026-06-13").date()
FRACOES = [1.00, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10]


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float, dec: int = 1) -> str:
    return br(100 * v, dec) + "%"


def main() -> None:
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from market_data_intraday.storage import load_m1
    from strategy.daytrade.lab.copa_win import CopaWin
    from strategy.daytrade.registry import get_daytrade_robot

    # ---- robo instrumentado: registra a GEOMETRIA PEDIDA em cada entrada --
    # Subclasse em vez de mexer no robo: a geometria (alvo/stop em pontos)
    # nao sobrevive no `IntradayTrade`, e reconstrui-la de fora exigiria
    # redigitar `alvo_vol x vol`, que e' a mesma conta em dois lugares.
    class CopaWinInstrumentada(CopaWin):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.registros: list[dict] = []
            self._ts_corrente = None

        def on_bar(self, ts, bar, positions, cash_brl):
            self._ts_corrente = ts
            return super().on_bar(ts, bar, positions, cash_brl)

        def _entrada(self, lado, preco, nivel_rompido, vol):
            acao = super()._entrada(lado, preco, nivel_rompido, vol)
            base = getattr(acao, "limit_price", None)
            if base is None:
                base = preco
            self.registros.append(dict(
                ts=self._ts_corrente, side=acao.side, base=base,
                alvo_dist=abs(acao.initial_target - base),
                stop_dist=abs(acao.initial_stop - base),
                vol=vol,
            ))
            return acao

    padrao = get_daytrade_robot("copa_win", symbol=SYMBOL)
    kw = {k: getattr(padrao, k) for k in (
        "teto_contratos", "symbol", "tick_size", "point_value_brl", "fracao_entrada",
        "janela_rompimento", "alvo_vol", "stop_vol", "vol_min_ticks", "trail_vol",
        "aquecimento_barras", "max_entradas_dia", "entrada_maker", "entrada_ttl_barras",
        "margin_per_contract_brl", "margin_buffer", "risco_pct_por_trade",
        "defesa_ativa", "defesa_gatilho_stop_pct", "defesa_alvo_proximidade_pct",
        "corte_persistencia_ativo", "corte_persistencia_min_barras",
        "corte_persistencia_frac_adverso",
    )}
    strat = CopaWinInstrumentada(**kw)

    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    bars = df[[d in completos for d in df.index.date]]
    print(f"WIN@ M1: {len(completos)} pregoes completos "
          f"({min(completos)} -> {max(completos)}), capital R$ {br(CAPITAL)}", flush=True)
    print(f"geometria de producao: alvo_vol={br(strat.alvo_vol, 1)} "
          f"stop_vol={br(strat.stop_vol, 1)} (razao {br(strat.alvo_vol / strat.stop_vol, 2)})\n",
          flush=True)

    cfg = config_for(
        profile_for(SYMBOL), trade_tick_value=0.20, trade_tick_size=1.0,
        initial_capital=CAPITAL, target_fills_as_maker=strat.target_fills_as_maker,
        limit_fill_capped_by_volume=True,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    print(f"{len(trades)} trades, {len(strat.registros)} entradas pedidas "
          f"(nem toda ordem-limite preenche)\n", flush=True)

    # ---- casa cada trade com a geometria que o robo pediu ----------------
    por_lado: dict[str, list[dict]] = defaultdict(list)
    for r in strat.registros:
        por_lado[r["side"]].append(r)

    linhas = []
    sem_par = 0
    for t in trades:
        cands = [r for r in por_lado[t.side]
                 if r["ts"] <= t.entry_ts and abs(r["base"] - t.entry_price) < 1e-6]
        if not cands:
            sem_par += 1
            continue
        reg = max(cands, key=lambda r: r["ts"])
        janela = bars.loc[t.entry_ts:t.exit_ts]
        if janela.empty:
            sem_par += 1
            continue
        if t.side == "long":
            mfe = float(janela["high"].max()) - t.entry_price
            mae = t.entry_price - float(janela["low"].min())
        else:
            mfe = t.entry_price - float(janela["low"].min())
            mae = float(janela["high"].max()) - t.entry_price
        linhas.append(dict(
            trade=t, motivo=t.exit_reason.value,
            frac_alvo=max(0.0, mfe) / reg["alvo_dist"] if reg["alvo_dist"] > 0 else 0.0,
            frac_stop=max(0.0, mae) / reg["stop_dist"] if reg["stop_dist"] > 0 else 0.0,
            alvo_dist=reg["alvo_dist"], stop_dist=reg["stop_dist"],
            oos=t.exit_ts.date() >= OOS_INICIO,
        ))
    print(f"casados {len(linhas)}/{len(trades)} trades com a geometria pedida"
          + (f" ({sem_par} sem par -- EXCLUIDOS)" if sem_par else ""), flush=True)

    # ---- 1. quanto do ALVO cada trade alcancou --------------------------
    print("\n\n1. QUANTO DO ALVO O PRECO ALCANCOU (excursao favoravel / alvo pedido)")
    print("   censura: a linha 'stop' e' CENSURADA A DIREITA -- o stop encerrou a")
    print("   observacao, nao da' pra saber ate onde teria ido.\n")
    print(f"   {'motivo':<16} {'n':>5} {'media':>8} {'p25':>8} {'p50':>8} "
          f"{'p75':>8} {'p90':>8} {'max':>8}")
    grupos = [("TODOS", linhas)] + [
        (m, [l for l in linhas if l["motivo"] == m])
        for m, _ in Counter(l["motivo"] for l in linhas).most_common()
    ]
    for nome, sub in grupos:
        if not sub:
            continue
        s = pd.Series([l["frac_alvo"] for l in sub])
        print(f"   {nome:<16} {len(sub):>5} {pct(s.mean()):>8} {pct(s.quantile(.25)):>8} "
              f"{pct(s.median()):>8} {pct(s.quantile(.75)):>8} {pct(s.quantile(.90)):>8} "
              f"{pct(s.max()):>8}")

    # ---- 2. a tabela que o dono pediu -----------------------------------
    print("\n\n2. SE O ALVO FOSSE X% DO PEDIDO, QUANTOS TRADES TERIAM ENCOSTADO NELE")
    print("   TETO da melhora, nao previsao: baixar o alvo faz o trade fechar mais")
    print("   cedo e muda tudo o que vem depois no mesmo pregao.\n")
    print(f"   {'alvo':>8} {'em pontos':>11} {'acerto TODOS':>14} {'acerto IS':>11} "
          f"{'acerto OOS':>11} {'razao alvo:stop':>16}")
    alvo_med = pd.Series([l["alvo_dist"] for l in linhas]).median()
    is_l = [l for l in linhas if not l["oos"]]
    oos_l = [l for l in linhas if l["oos"]]
    for f in FRACOES:
        def taxa(sub):
            return sum(1 for l in sub if l["frac_alvo"] >= f) / len(sub) if sub else 0.0
        razao = (strat.alvo_vol * f) / strat.stop_vol
        print(f"   {pct(f, 0):>8} {br(alvo_med * f, 0):>11} {pct(taxa(linhas)):>14} "
              f"{pct(taxa(is_l)):>11} {pct(taxa(oos_l)):>11} "
              f"{br(razao, 2) + ':1':>16}")

    # ---- 3. o outro lado: quanto do STOP foi sofrido --------------------
    print("\n\n3. QUANTO DO STOP CADA TRADE SOFREU (excursao adversa / stop pedido)")
    print("   por que importa aqui: se a maioria dos VENCEDORES sofre pouco, um stop")
    print("   menor nao os mataria -- e' o que decide se da' pra apertar os dois.\n")
    print(f"   {'motivo':<16} {'n':>5} {'media':>8} {'p25':>8} {'p50':>8} "
          f"{'p75':>8} {'p90':>8} {'max':>8}")
    for nome, sub in grupos:
        if not sub:
            continue
        s = pd.Series([l["frac_stop"] for l in sub])
        print(f"   {nome:<16} {len(sub):>5} {pct(s.mean()):>8} {pct(s.quantile(.25)):>8} "
              f"{pct(s.median()):>8} {pct(s.quantile(.75)):>8} {pct(s.quantile(.90)):>8} "
              f"{pct(s.max()):>8}")

    # ---- 4. o cruzamento que decide -------------------------------------
    print("\n\n4. O CRUZAMENTO: entre os trades que NAO bateram o alvo de hoje,")
    print("   quantos chegaram a X% do alvo -- e o que eles renderam de fato")
    print("   (sao esses que um alvo menor converteria)\n")
    nao_bateram = [l for l in linhas if l["motivo"] != "target"]
    print(f"   {'alvo':>8} {'n que encostaram':>18} {'% dos que nao bateram':>23} "
          f"{'R$/op que tiveram':>19}")
    for f in FRACOES:
        sub = [l for l in nao_bateram if l["frac_alvo"] >= f]
        if not sub:
            print(f"   {pct(f, 0):>8} {0:>18} {pct(0):>23} {'--':>19}")
            continue
        rs = sum(l["trade"].pnl_brl / l["trade"].quantity for l in sub) / len(sub)
        print(f"   {pct(f, 0):>8} {len(sub):>18} {pct(len(sub) / len(nao_bateram)):>23} "
              f"{br(rs):>19}")


if __name__ == "__main__":
    main()
