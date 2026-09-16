# -*- coding: utf-8 -*-
"""`win_retangulo` -- nas operacoes que morreram por STOP, o preco chegou perto
do ALVO antes de reverter, ou o alvo estava sistematicamente fora de alcance?

Frente D da rodada de economia. NAO e' para criar regra de gestao (24 regras
de trajetoria ja foram medidas e refutadas no copa_win -- trailing, zero-a-
zero, corte por tempo, todas negativas). E' para responder uma pergunta de
CALIBRACAO: o alvo (0,80xL) esta' plausivel, ou e' geometricamente inatingivel
na pratica, o que mudaria a leitura de qualquer proposta de reduzir o alvo?

## Por que so' STOP (nao achatamento)

A decomposicao por motivo (`win_retangulo_motivo_saida_2026_09_15.py`) ja
mediu: achatamento de fim de pregao e' 2,0% da amostra no IS (12/615) e 0,6%
no OOS (1/179), e o resultado medio dele e' proximo de zero (nem sistematica-
mente ganho nem perda). Nao ha' amostra para tirar leitura de MFE dali. STOP
e' 54% da amostra nas duas janelas -- e' o motivo que decide o breakeven.

## Metodo

Roda o robo de PRODUCAO (capital R$1.100, regua oficial). Para cada trade
fechado por STOP:

  1. `stop_pts = |pnl_brl| / 0,20` -- a distancia do stop em pontos (ignora o
     deslize de 1 tick do stop, que e' pequeno perto da geometria: stop e'
     0,50xL, alvo e' 0,80xL, razao FIXA de 1,6 independente de L).
  2. `alvo_pts = 1,6 x stop_pts` -- a distancia do alvo, reconstruida da
     RAZAO geometrica fixa (alvo_fracao/stop_fracao = 0,80/0,50), sem precisar
     conhecer L trade a trade.
  3. MFE = maior excursao a FAVOR da posicao entre o fill de entrada e o fill
     de saida, lida diretamente da serie M1 (post-hoc -- e' medicao, nao
     decisao causal do robo).
  4. `mfe_frac = MFE / alvo_pts` -- 0,0 = nunca saiu do zero a favor; 1,0 =
     chegou a tocar o preco do alvo (e portanto o alvo teria enchido primeiro
     SE tivesse chegado la' antes do stop -- nao e' garantia de fill, so' de
     que o NIVEL foi alcancado).

Reporta a distribuicao de `mfe_frac` (mediana, p75, p90, max) e a fracao de
stops que chegaram a >=50%/>=90%/>=100% do caminho ate o alvo, nas DUAS
janelas. Se a distribuicao tem uma PAREDE clara (ex.: quase nada passa de
30%) e ela REPLICA nas duas janelas, e' achado: o alvo e' geometricamente
distante da maioria dos stops, entao encurtar o alvo NAO adianta (paredes
ficam abaixo de onde o preco de fato andou). Se a distribuicao e' lisa (sem
parede, cauda longa e uniforme), e' refutacao igual de valida: nao ha'
assinatura de "alvo mal calibrado" nos stops.

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_mfe_stop_2026_09_15.py`
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from core.models import IntradayExitReason  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import get_daytrade_robot  # noqa: E402

CORTE_OOS = pd.Timestamp("2026-06-13").date()
HOJE = pd.Timestamp("2026-09-15").date()
_PRODUCAO = get_daytrade_robot("win_retangulo")
CAPITAL = float(_PRODUCAO.capital_minimo_recomendado_brl)
SYMBOL = _PRODUCAO.symbol
MIN_BARRAS_POR_PREGAO = 400
POINT_VALUE = 0.20
RAZAO_ALVO_STOP = 0.80 / 0.50  # 1,6 -- fixa, independente da largura L


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _unidade(args):
    rotulo, dias = args
    strat = get_daytrade_robot("win_retangulo")
    df = load_m1(strat.symbol).sort_index()
    alvo_dias = set(dias)
    bars = df[[d in alvo_dias for d in df.index.date]]
    profile = profile_for(strat.symbol)
    cfg = config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=CAPITAL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    trades = [t for t in res.trades if t.exit_reason == IntradayExitReason.STOP]

    mfe_fracs = []
    for t in trades:
        stop_pts = abs(t.pnl_brl) / POINT_VALUE
        if stop_pts <= 0:
            continue
        alvo_pts = RAZAO_ALVO_STOP * stop_pts
        janela = bars[(bars.index >= t.entry_ts) & (bars.index <= t.exit_ts)]
        if janela.empty:
            continue
        if t.side == "long":
            mfe_pts = float(janela["high"].max() - t.entry_price)
        else:
            mfe_pts = float(t.entry_price - janela["low"].min())
        mfe_fracs.append(max(0.0, mfe_pts) / alvo_pts)

    return dict(rotulo=rotulo, n=len(trades), mfe_fracs=mfe_fracs)


def main():
    df = load_m1(SYMBOL).sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO)
    IS = [d for d in completos if d < CORTE_OOS]
    OOS = [d for d in completos if CORTE_OOS <= d < HOJE]

    print("=" * 120)
    print("win_retangulo -- MFE das operacoes fechadas por STOP: chegaram perto do alvo?")
    print("=" * 120)
    print(f"  capital R$ {br(CAPITAL,0)} | IS {len(IS)} pregoes | OOS {len(OOS)} pregoes")
    print("  mfe_frac = excursao maxima a favor / distancia ate o alvo (reconstruida da razao")
    print("  fixa alvo/stop = 1,6x, valida para QUALQUER largura L)\n", flush=True)

    tarefas = [("IS  (< 2026-06-13)", IS), ("OOS (>= 2026-06-13)", OOS)]
    out = {}
    with ProcessPoolExecutor() as pool:
        futs = [pool.submit(_unidade, t) for t in tarefas]
        for fut in as_completed(futs):
            r = fut.result()
            out[r["rotulo"]] = r
            print(f"  ok {r['rotulo']}: {r['n']} stops, {len(r['mfe_fracs'])} com MFE medido",
                  flush=True)

    print("\n" + "=" * 120)
    print(f"  {'janela':<24}{'n':>6}{'mediana':>10}{'p75':>8}{'p90':>8}{'max':>8}"
          f"{'>=50%':>9}{'>=90%':>9}{'>=100%':>9}")
    for rot, _d in tarefas:
        arr = np.array(out[rot]["mfe_fracs"])
        n = len(arr)
        if n == 0:
            print(f"  {rot:<24}{0:>6}" + "     --" * 7)
            continue
        med, p75, p90, mx = (np.percentile(arr, 50), np.percentile(arr, 75),
                              np.percentile(arr, 90), arr.max())
        f50 = 100 * np.mean(arr >= 0.50)
        f90 = 100 * np.mean(arr >= 0.90)
        f100 = 100 * np.mean(arr >= 1.00)
        print(f"  {rot:<24}{n:>6}{br(med,3):>10}{br(p75,3):>8}{br(p90,3):>8}{br(mx,3):>8}"
              f"{br(f50,1)+'%':>9}{br(f90,1)+'%':>9}{br(f100,1)+'%':>9}")

    print("\n" + "=" * 120)
    print("LEITURA")
    print("=" * 120)
    print("  Se a fracao de stops que chega a >=90%/100% do caminho ate o alvo for ALTA e")
    print("  replicar nas duas janelas, o alvo esta' bem calibrado -- boa parte das perdas")
    print("  'quase' virou vitoria, e o breakeven e' genuinamente apertado, nao um alvo fora")
    print("  de alcance. Se a fracao for BAIXA (a maioria dos stops nunca anda mais que uma")
    print("  fracao pequena do caminho), o alvo de 0,80xL e' geometricamente distante do que")
    print("  a maioria das reversoes alcanca -- e' achado, mas NAO vira regra de gestao (ja")
    print("  refutada 24x no copa_win): serve so' para calibrar expectativa sobre o alvo.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
