# -*- coding: utf-8 -*-
"""Teste barato: e se o LADO do wdo_retangulo estiver invertido?

Hipotese: o win% medido (20-30%, muito abaixo do breakeven ~38%) e' exatamente
o padrao que apareceria se COMPRA/VENDA estivessem trocados -- convencao de
direcao ja mordeu este projeto antes (convencao_direcao_instavel_2026_08_26).

Mesma calibracao (piso W20 tercil), mesmas janelas congeladas, mesmo capital
real R$375, mesma fila real -- SO troca lado<->lado na entrada. Nao mexe no
arquivo da estrategia: subclasse local, so' para o teste."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
MIN_BARRAS_POR_PREGAO = 500

IS_INICIO = pd.Timestamp("2026-02-27", tz="UTC")
IS_FIM = pd.Timestamp("2026-06-13", tz="UTC")
OOS_INICIO = pd.Timestamp("2026-06-15", tz="UTC")
OOS_FIM = pd.Timestamp("2026-08-26", tz="UTC")


def br(v, dec=1):
    if v != v:
        return "--"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    from market_data_intraday.storage import load_m1
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.base import EnterLimit, no_tick
    from strategy.daytrade.lab.wdo_retangulo import WdoRetangulo, detecta_retangulo
    from core.models import IntradayExitReason

    class WdoRetanguloInvertido(WdoRetangulo):
        """Mesma classe, SO troca qual lado (compra/venda) cada lado do meio
        dispara -- teste de convencao de direcao, nada mais."""

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            self._hist.append(bar)
            if self._retangulo is not None and self._morreu(bar):
                self._retangulo = None
                self._barras_esperando = None
            if self._retangulo is None:
                self._tenta_detectar()
                if self._retangulo is None:
                    return []
            if positions:
                self._barras_esperando = None
                return []
            if self._barras_esperando is not None:
                self._barras_esperando += 1
                if self._barras_esperando < self.ttl_barras:
                    return []
                self._barras_esperando = None

            r = self._retangulo
            meio, largura = r["meio"], r["largura"]
            # INVERTIDO: close<meio -> LONG (era short); close>meio -> SHORT (era long)
            if bar.close < meio:
                lado = "long"
                alvo = meio + self.alvo_fracao_largura * largura
                stop = meio - self.stop_fracao_largura * largura
            elif bar.close > meio:
                lado = "short"
                alvo = meio - self.alvo_fracao_largura * largura
                stop = meio + self.stop_fracao_largura * largura
            else:
                return []

            limite = no_tick(meio, self.tick_size)
            if lado == "short" and limite <= bar.close:
                return []
            if lado == "long" and limite >= bar.close:
                return []

            self._barras_esperando = 0
            return [EnterLimit(
                side=lado, limit_price=limite,
                initial_stop=no_tick(stop, self.tick_size),
                initial_target=no_tick(alvo, self.tick_size),
                quantity=self.quantidade, ttl_bars=self.ttl_barras,
                exit_split_unit=1, exit_ttl_bars=10 ** 9,
                reason=f"retangulo_INV_W{self.janela_barras}_L{largura:.1f}",
            )]

    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    df = df[[d in completos for d in df.index.date]]

    def dias_da_janela(inicio, fim):
        bars = df[(df.index >= inicio) & (df.index < fim)]
        dias = sorted({d for d in bars.index.date if d in completos})
        bars = bars[[d in set(dias) for d in bars.index.date]]
        return bars, dias

    bars_is, dias_is = dias_da_janela(IS_INICIO, IS_FIM)
    bars_oos, dias_oos = dias_da_janela(OOS_INICIO, OOS_FIM)

    def larguras_do_dia(bars_dia, W):
        high = bars_dia["high"].to_numpy(float)
        low = bars_dia["low"].to_numpy(float)
        close = bars_dia["close"].to_numpy(float)
        n = len(close)
        minimo_barras = 3 * W
        if n < minimo_barras:
            return []
        larguras, ret, fora = [], None, 0
        t = minimo_barras - 1
        while t < n:
            if ret is None:
                ini = t - W + 1
                ant_ini = t - 3 * W + 1
                amp_ant = (float(high[ant_ini:ini].max() - low[ant_ini:ini].min())
                           if ant_ini >= 0 else None)
                r = detecta_retangulo(high[ini:t+1], low[ini:t+1], close[ini:t+1], amp_ant)
                if r is not None:
                    larguras.append(r["largura"]); ret = r; fora = 0
                t += 1
            else:
                margem = 0.25 * ret["largura"]
                c = close[t]
                if c > ret["topo"] + margem or c < ret["piso"] - margem:
                    fora += 1
                    if fora >= 3:
                        ret = None; fora = 0
                else:
                    fora = 0
                t += 1
        return larguras

    todas_w20 = []
    for d in dias_is:
        bd = bars_is[bars_is.index.date == d]
        todas_w20.extend(larguras_do_dia(bd, 20))
    piso_w20 = float(np.quantile(todas_w20, 2 / 3))
    print(f"piso_w20 (mesmo da calibracao oficial) = {br(piso_w20, 2)} pts\n")

    def roda(dias, klass):
        alvo = set(dias)
        bars = df[[d in alvo for d in df.index.date]]
        strat = klass(janela_barras=20, largura_minima_pontos=piso_w20)
        profile = profile_for(SYMBOL)
        cfg = config_for(
            profile, trade_tick_value=0.01, trade_tick_size=0.001,
            initial_capital=CAPITAL_REAL_BRL,
            target_fills_as_maker=strat.target_fills_as_maker,
            anchor_exits_at_fill=strat.anchor_exits_at_fill,
            limit_fill_capped_by_volume=True,
        )
        return run_intraday_backtest(bars, strat, cfg)

    def resume(trades, n_dias):
        n = len(trades)
        liquido = sum(t.pnl_brl for t in trades)
        g = [t.pnl_brl for t in trades if t.pnl_brl > 0]
        p = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
        gm = (sum(g) / len(g)) if g else 0.0
        pm = (abs(sum(p) / len(p))) if p else 0.0
        be = pm / (gm + pm) if (gm + pm) > 0 else float("nan")
        win = len(g) / n if n else float("nan")
        dias_com_trade = len({pd.Timestamp(t.exit_ts).date() for t in trades})
        alvo_n = sum(1 for t in trades if t.exit_reason == IntradayExitReason.TARGET)
        stop_n = sum(1 for t in trades if t.exit_reason == IntradayExitReason.STOP)
        return dict(n=n, liquido=liquido, win=win, be=be, alvo=alvo_n, stop=stop_n,
                    sem_trade=n_dias - dias_com_trade)

    for nome, klass in (("ORIGINAL (produção do teste)", WdoRetangulo),
                        ("INVERTIDO (compra<->venda)", WdoRetanguloInvertido)):
        print(f"=== {nome} ===")
        for jn, dias in (("IS", dias_is), ("OOS", dias_oos)):
            res = roda(dias, klass)
            r = resume(list(res.trades), len(dias))
            pct = lambda x: (br(100 * x, 1) + "%") if x == x else "--"
            print(f"  {jn:<4} n={r['n']:>4}  liquido={br(r['liquido']):>10}  "
                  f"win={pct(r['win']):>7}  BEemp={pct(r['be']):>7}  "
                  f"alvo={r['alvo']:>3}  stop={r['stop']:>3}  sem_trade={r['sem_trade']}/{len(dias)}")
        print()


if __name__ == "__main__":
    main()
