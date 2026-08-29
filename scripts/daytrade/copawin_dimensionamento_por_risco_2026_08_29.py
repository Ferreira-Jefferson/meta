"""Segunda ideia do dono (2026-08-29) pra resolver o achado do item 3.9
(`LICOES_DE_PRODUCAO.md`: CopaWin com R$3.000 real foi de R$3.000 a R$68,50
num unico trade, porque `contracts_from_capital_com_reserva` escala
CONTRATOS linearmente com o caixa): "separar" uma fatia do caixa a cada
marco de crescimento (ex.: +60%) e parar de contar essa fatia como caixa
operacional.

Testada em `copawin_ratchet_skim_teste_2026_08_29.py` -- RESULTADO: no
limiar que o dono pediu (+60%/10%), o mecanismo nunca dispara nesta janela
(o salto fatal aconteceu com o caixa crescendo so' 43%, abaixo do gatilho) --
resultado IDENTICO ao baseline. Baixando o limiar pra disparar antes (39%,
30%, 19%, 10%) o resultado PIORA: a conta vai a EQUITY NEGATIVA
(-R$212,80/-R$215,80), pior que o baseline (nunca negativo). Causa: "separar"
aqui e' so' contabil -- o dinheiro nunca sai da mesma conta/mesma posicao, e
o valor separado fica CONGELADO em reais enquanto o caixa flutua; quando o
caixa recupera depois de uma perda, a fatia separada vira uma fracao cada vez
MENOR do caixa atual, e o tamanho da entrada volta a inflar sem um novo
gatilho de separacao -- a protecao nao acompanha o RISCO atual, so' o
HISTORICO de onde ela foi calculada uma vez.

Este script mede a alternativa: dimensionar direto pelo RISCO, nao pela
margem. `contratos = floor((caixa_atual x risco_pct) / (distancia_do_stop_em_
pontos x point_value_brl))`, recalculado em TODA entrada (nunca ancorado num
marco antigo) -- o analogo, em day trade, do "arrisque X% do patrimonio por
operacao" que qualquer mesa de risco pede. Guarda `_ultimo_stop_dist_pontos`
antes de chamar `CopaWin._entrada` (que ja sabe `vol`/`stop_vol`) pra
`quantidade_por_entrada` usar sem duplicar a conta de stop.

Roda os MESMOS 182 pregoes de WIN@, MESMO capital real R$3.000, 4 niveis de
risco_pct -- pra comparar linha a linha contra o baseline (margem linear) e
o ratchet-skim (ambos ja medidos, valores fixos abaixo pela referencia).

Uso: `python -u scripts/daytrade/copawin_dimensionamento_por_risco_2026_08_29.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.registry import _KWARGS_PADRAO  # noqa: E402
from strategy.daytrade.lab.copa_win import CopaWin  # noqa: E402

CAPITAL_INICIAL = 3_000.0
NIVEIS_RISCO_PCT = (0.02, 0.05, 0.08, 0.10)

#: Ja medido (ver `podio_stress_capital_real_historico_completo.py` e o
#: item 3.9) -- impresso ao final so' pra comparacao lado a lado, nao
#: recalculado aqui.
BASELINE_MARGEM_LINEAR = dict(trades=5, liquido=-2_931.50, equity_final=68.50, equity_min=68.50)
RATCHET_SKIM_60_10 = dict(trades=5, liquido=-2_931.50, equity_final=68.50, equity_min=68.50)
RATCHET_SKIM_39_10 = dict(trades=10, liquido=2_700.20, equity_final=-212.80, equity_min=-212.80)


def br(v: float, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def make_risk_sized_copawin(risco_pct: float) -> type[CopaWin]:
    class CopaWinRiscoPct(CopaWin):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._ultimo_stop_dist_pontos: float | None = None

        def _entrada(self, lado, preco, nivel_rompido, vol):
            self._ultimo_stop_dist_pontos = self.stop_vol * vol
            return super()._entrada(lado, preco, nivel_rompido, vol)

        @property
        def quantidade_por_entrada(self) -> int:
            if self._ultimo_stop_dist_pontos is None or self._cash_atual_brl <= 0:
                return 1
            risco_reais = self._cash_atual_brl * risco_pct
            risco_por_contrato = self._ultimo_stop_dist_pontos * self.point_value_brl
            if risco_por_contrato <= 0:
                return 1
            qtd = int(risco_reais // risco_por_contrato)
            return max(1, min(qtd, self.teto_contratos))

    return CopaWinRiscoPct


def main() -> None:
    df = load_m1("WIN@").sort_index()
    contagem = df.groupby(df.index.date).size()
    completos = {d for d, n in contagem.items() if n >= 400}
    bars = df[[d in completos for d in df.index.date]]
    profile = profile_for("WIN@")

    print(f"=== CopaWin dimensionado por RISCO (WIN@, capital R${br(CAPITAL_INICIAL)}, "
          f"{len(set(bars.index.date))} pregoes) ===\n")

    for risco_pct in NIVEIS_RISCO_PCT:
        Cls = make_risk_sized_copawin(risco_pct)
        kwargs = dict(_KWARGS_PADRAO["copa_win"])
        strat = Cls(**kwargs)
        cfg = config_for(
            profile, trade_tick_value=0.20, trade_tick_size=1.0,
            initial_capital=CAPITAL_INICIAL, target_fills_as_maker=strat.target_fills_as_maker,
            limit_fill_capped_by_volume=True,
        )
        resultado = run_intraday_backtest(bars, strat, cfg)
        liquido = sum(t.pnl_brl for t in resultado.trades)
        equity_final = float(resultado.equity_curve.iloc[-1]) if not resultado.equity_curve.empty else CAPITAL_INICIAL
        equity_min = float(resultado.equity_curve.min()) if not resultado.equity_curve.empty else CAPITAL_INICIAL
        pior = min(resultado.trades, key=lambda t: t.pnl_brl) if resultado.trades else None
        qtys = [t.quantity for t in resultado.trades]
        print(f"risco={int(risco_pct*100)}%/trade: trades={len(resultado.trades)} "
              f"| qty maxima={max(qtys) if qtys else 0} "
              f"| liquido=R${br(liquido)} | equity final=R${br(equity_final)} "
              f"| equity MINIMA=R${br(equity_min)}")
        if pior is not None:
            print(f"    pior trade: {pior.entry_ts} qty={pior.quantity} pnl=R${br(pior.pnl_brl)}")

    print("\n--- referencia (ja medidos) ---")
    print(f"margem linear (producao atual): {BASELINE_MARGEM_LINEAR}")
    print(f"ratchet-skim +60%/10% (ideia do dono, limiar nunca disparou): {RATCHET_SKIM_60_10}")
    print(f"ratchet-skim +39%/10% (limiar mais sensivel, PIOROU -> negativo): {RATCHET_SKIM_39_10}")


if __name__ == "__main__":
    main()
