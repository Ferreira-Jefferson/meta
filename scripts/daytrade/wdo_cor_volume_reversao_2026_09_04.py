"""Teste pedido pelo dono (2026-09-04): "faca um teste em wdo usando cores,
se as ultimas 3 velas forem da mesma cor, e tiver mais volume de pra cor
contraria, abra uma posicao pra cor contraria" -- rodado nos ULTIMOS 3
MESES de WDO@ M1 salvo localmente, capital R$375 (minimo real do
instrumento COM a reserva de seguranca -- `strategy.daytrade.base.
contracts_from_capital_com_reserva(375, 150, 2.0, 1.25) == 1`, nunca um
capital nocional/arbitrario).

Rodada 2 (mesmo dia, pedido seguinte do dono): "vamos parar de olhar pra
volume, quero bastante trade, coloque o t20 s5" -- desliga o filtro de
volume (`CorVolumeReversao.exigir_volume_contrario=False`, sinal vira so'
"3 velas consecutivas da mesma cor", sem condicao nenhuma de volume) e
troca o par alvo/stop de 5/5 para **alvo 20 ticks / stop 5 ticks** (4:1).

Rodada 3 (mesmo dia, pedido seguinte): "perfeito, agora vamos inverter,
mantendo alvo 20 e stop 5, se vier um sinal de compra deve vender e vice
versa" -- `inverter_direcao=True`: o lado final vira o OPOSTO do fade
original (3 velas verdes -> compra, 3 velas vermelhas -> vende), ou seja
CONTINUACAO da sequencia em vez de fade, alvo/stop e ausencia de filtro
de volume mantidos identicos a rodada 2.

Regra de trade e interpretacao declarada (cor neutra, nunca piramida) em
`strategy.daytrade.lab.cor_volume_reversao.CorVolumeReversao` -- este
script so' carrega dado, monta config e imprime a TABELA PADRAO
(`backtest/intraday/report.py`), sem veredito (convencao do projeto:
numero cru, o dono julga).

Uso: `python -u scripts/daytrade/wdo_cor_volume_reversao_2026_09_04.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import (  # noqa: E402
    contracts_from_capital_com_reserva,
)
from strategy.daytrade.lab.cor_volume_reversao import CorVolumeReversao  # noqa: E402

SYMBOL = "WDO@"
#: Economia conhecida da serie continua WDO@ (`trade_tick_value`, `trade_tick_size`
#: como o MT5 reporta -- `config_for` reescala para o tick REAL de 0,5pt via
#: `profile.price_tick_size`, ver `backtest/intraday/profiles.py`).
ECONOMIA_WDO = (0.01, 0.001)
MARGEM_WDO_BRL = 150.0

#: Capital do teste: minimo real COM reserva de seguranca (LICOES_DE_PRODUCAO.md,
#: "capital inicial nunca arbitrario" + memoria `feedback_wdo_capital_teste_375`)
#: -- nunca um numero nocional/arredondado.
CAPITAL_TESTE_BRL = 375.0

TARGET_TICKS = 20
STOP_TICKS = 5
EXIGIR_VOLUME_CONTRARIO = False  # pedido do dono: "vamos parar de olhar pra volume"
INVERTER_DIRECAO = True  # pedido do dono: "se vier um sinal de compra deve vender e vice versa"
MIN_BARRAS_POR_PREGAO = 400  # descarta pregao incompleto -- mesmo corte de outras rodadas WDO F1


def _janela_3_meses(bars: pd.DataFrame) -> pd.DataFrame:
    contagem = bars.groupby(bars.index.date).size()
    completos = {d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO}
    bars = bars[[d in completos for d in bars.index.date]]
    if bars.empty:
        return bars
    fim = bars.index.max()
    inicio = fim - pd.DateOffset(months=3)
    return bars[bars.index >= inicio]


def main() -> None:
    bars = load_m1(SYMBOL)
    if bars.empty:
        raise SystemExit(f"sem dado M1 salvo para {SYMBOL!r}.")
    bars = _janela_3_meses(bars)
    if bars.empty:
        raise SystemExit("sem pregao completo na janela de 3 meses.")
    pregoes = sorted(set(bars.index.date))

    profile = profile_for(SYMBOL)
    teto_contratos = contracts_from_capital_com_reserva(CAPITAL_TESTE_BRL, MARGEM_WDO_BRL)

    print(f"[wdo_cor_volume_reversao] {SYMBOL} -- {pregoes[0]}..{pregoes[-1]} "
          f"({len(pregoes)} pregoes completos, {len(bars):,} barras M1)")
    print(f"capital R${num_br(CAPITAL_TESTE_BRL, 0)} -> teto de contratos "
          f"COM reserva: {teto_contratos} | alvo/stop: {TARGET_TICKS}/{STOP_TICKS} "
          f"ticks (tick={profile.price_tick_size}pt = R${num_br(ECONOMIA_WDO[0]/ECONOMIA_WDO[1]*profile.price_tick_size)})\n",
          flush=True)

    #: Duas variantes, MESMO capital inicial -- a primeira e' o pedido literal
    #: do dono (R$375, trava dinamica de capital LIGADA, comportamento de
    #: producao); a segunda desliga so' a trava (`enforce_capital_cap=False`)
    #: para separar "a regra nao gera sinal" de "a trava travou a conta depois
    #: da 1a perda" (ver LICOES_DE_PRODUCAO.md, "dois pisos censuram todo
    #: backtest") -- sem isso um numero pequeno de trades pode enganar sobre
    #: qual das duas causas explica o resultado.
    VARIANTES = (
        ("com trava de capital (producao)", True),
        ("sem trava de capital (so' a regra)", False),
    )

    linhas = []
    for rotulo, trava in VARIANTES:
        strat = CorVolumeReversao(
            symbol=SYMBOL,
            tick_size=profile.price_tick_size,
            target_ticks=TARGET_TICKS,
            stop_ticks=STOP_TICKS,
            exigir_volume_contrario=EXIGIR_VOLUME_CONTRARIO,
            inverter_direcao=INVERTER_DIRECAO,
        )
        cfg = config_for(
            profile,
            trade_tick_value=ECONOMIA_WDO[0],
            trade_tick_size=ECONOMIA_WDO[1],
            initial_capital=CAPITAL_TESTE_BRL,
            target_fills_as_maker=strat.target_fills_as_maker,
            limit_fill_capped_by_volume=True,
            enforce_capital_cap=trava,
        )
        resultado = run_intraday_backtest(bars, strat, cfg)
        trades = list(resultado.trades)
        perdas_brl = sum(t.pnl_brl for t in trades if t.pnl_brl < 0)
        ganhos_brl = sum(t.pnl_brl for t in trades if t.pnl_brl > 0)
        extras = {"ganhos R$": num_br(ganhos_brl), "perdas R$": num_br(perdas_brl)}
        linhas.append((
            linha_de_resultado(rotulo, resultado, CAPITAL_TESTE_BRL, extras=extras),
            resultado, trades,
        ))

    nomes_extra = ("ganhos R$", "perdas R$")
    print(cabecalho(extras=nomes_extra, largura_extra=13))
    for linha_res, resultado, trades in linhas:
        print(linha(linha_res, extras=nomes_extra, largura_extra=13))
        if resultado.wiped_out_at is not None:
            print(f"    *** ZERADO em {resultado.wiped_out_at}. ***")
        puladas = len(getattr(resultado, "sessoes_puladas_por_capital", []) or [])
        if puladas:
            print(f"    *** {puladas} pregao(s) pulado(s) por capital insuficiente. ***")
    if not any(trades for _, _, trades in linhas):
        print("\nsem trades fechados nesta janela, em nenhuma variante.")


if __name__ == "__main__":
    main()
