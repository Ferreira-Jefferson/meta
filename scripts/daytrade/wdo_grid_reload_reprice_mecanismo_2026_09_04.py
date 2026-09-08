"""Entendendo o salto de 10x medido em `wdo_grid_reload_reprice_fix_
validacao_2026_09_04.py` (item 4.9 do LICOES_DE_PRODUCAO.md): pedido do
dono foi "pare e entenda", nao "corrija mais nada" -- este script so'
instrumenta o mecanismo pra confirmar (ou refutar) a hipotese com dado
real, num UNICO pregao (rapido, cache local, sem MT5).

Hipotese: reancorar em TODA barra (o fix) transforma a ordem de "parada
num nivel fixo, esperando o preco voltar" para "persegue o preco a
`level_spacing_ticks` de distancia, sempre". Como o item anterior desta
mesma rodada (investigacao do zero-stops) mediu autocorrelacao lag-1 de
-0,44 no tape do WDO@ (89,3% dos ticks que se movem revertem o anterior),
uma ordem que persegue o preco a 1 tick de distancia deveria ser tocada
quase toda vez que o preco reverte -- ou seja, a maioria dos trades deveria
precisar de SO' 1 reprecificacao (a que acabou de armar/mover a ordem)
antes do fill, nao uma sequencia longa de reprecificacoes perseguindo um
movimento grande.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wdo_grid_reload_f1_lab import montar_config  # noqa: E402
from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from strategy.daytrade.base import EnterLimit  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker  # noqa: E402

CACHE_TICK = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"
CANDIDATO = dict(level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)


class _Instrumentado(WdoGridReloadMaker):
    """Por 'episodio de armamento' (do instante em que pending_side sai de
    None ate' voltar a None, por fill OU fim de pregao): quantas EnterLimit
    foram emitidas (1 = armou e nunca reprecificou; 2+ = reprecificou N-1
    vezes antes do desfecho) e quantos ticks (barras) se passaram."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.episodios: list[dict] = []
        self._reprecos_episodio_atual = 0  # so' conta quando o NIVEL muda de verdade
        self._ticks_episodio_atual = 0

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        pendente_antes = self._state.pending_side
        nivel_antes = self._level_price(pendente_antes) if pendente_antes is not None else None
        actions = super().on_bar(ts, bar, positions, session_pnl_brl)
        tem_pendente_agora = self._state.pending_side is not None

        if pendente_antes is not None or tem_pendente_agora:
            self._ticks_episodio_atual += 1
        # MESMO criterio de `_WdoGridReloadMakerComContador` (script de
        # validacao desta rodada): so' conta como reprico se o NIVEL de
        # fato mudou -- o `on_bar` de producao reemite EnterLimit em TODA
        # barra pendente, mesmo quando o nivel repete (o motor trata como
        # no-op), entao contar toda emissao superestimaria reprecos de
        # verdade por um fator grande (muitos ticks tem preco igual ao
        # anterior).
        if (pendente_antes is not None and actions
                and isinstance(actions[0], EnterLimit)
                and abs(actions[0].limit_price - nivel_antes) > 1e-9):
            self._reprecos_episodio_atual += 1

        if pendente_antes is not None and not tem_pendente_agora:
            self.episodios.append({
                "ts_fim": ts, "reprecos": self._reprecos_episodio_atual,
                "ticks": self._ticks_episodio_atual,
            })
            self._reprecos_episodio_atual = 0
            self._ticks_episodio_atual = 0
        return actions


def main() -> None:
    df = pd.read_parquet(CACHE_TICK)
    is_df = df[df["janela"] == "IS"][["open", "high", "low", "close", "volume"]]
    um_dia = sorted(set(is_df.index.date))[10]  # dia do meio do IS, nao o 1o (warm-up)
    bars = is_df[[d == um_dia for d in is_df.index.date]]
    print(f"[mecanismo] pregao {um_dia}: {len(bars):,} ticks")

    cfg = montar_config()
    strat = _Instrumentado(**CANDIDATO)
    resultado = run_intraday_backtest(bars, strat, cfg)
    print(f"[mecanismo] {len(resultado.trades)} trades fechados no dia")

    reprecos = pd.Series([e["reprecos"] for e in strat.episodios])
    ticks = pd.Series([e["ticks"] for e in strat.episodios])
    print(f"\n{len(reprecos)} episodios de armamento (fill ou fim de sessao)")
    print("distribuicao de REPRICOS DE VERDADE por episodio (0 = encheu no nivel do armamento, sem reprecar):")
    print(reprecos.value_counts().sort_index().head(15))
    print(f"\nmedia de reprecos/episodio: {reprecos.mean():.2f} | mediana: {reprecos.median():.0f}")
    print(f"% episodios com 0 reprecos (fill no primeiro nivel, sem NUNCA reprecar): "
          f"{100*(reprecos == 0).mean():.1f}%")
    print(f"% episodios com <=1 reprico: {100*(reprecos <= 1).mean():.1f}%")
    print(f"\nmedia de ticks/episodio ate' o desfecho: {ticks.mean():.2f} | mediana: {ticks.median():.0f}")
    print(f"total de reprecos neste pregao: {reprecos.sum()} (bate com o contador do script de validacao)")


if __name__ == "__main__":
    main()
