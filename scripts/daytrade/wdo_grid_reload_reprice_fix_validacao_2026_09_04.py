"""Validacao ANTES/DEPOIS do fix de 2026-09-04 (LICOES_DE_PRODUCAO.md item
4.9) em `strategy.daytrade.lab.wdo_grid_reload_maker.WdoGridReloadMaker.
on_bar`.

## O bug corrigido

No modo `reanchor_mode="rolling_last_price"` (o DEFAULT), a ancora so' era
recalculada no INSTANTE em que a `EnterLimit` era armada -- depois disso,
enquanto a ordem ficava pendente (sem preencher), `on_bar` devolvia cedo e a
ordem ficava ESTACIONADA pelo resto do pregao se o preco se afastasse e nao
voltasse a toca-la. Medido em producao (dado real de tick MT5, semana de
2026-08-31 a 2026-09-04): o robo ficou "ativo" (1a entrada ate' ultima
saida) so' 0%/8,0%/14,3%/11,1%/0% de cada pregao, chegando a NAO OPERAR em
2 dos 5 dias.

## O fix

`on_bar` agora reancora em TODA barra (nao so' no instante de armar), MESMO
com ordem pendente, e reemite a `EnterLimit` no nivel atualizado para o
MESMO lado. O motor ja' trata isso como cancela-e-substitui quando o nivel
muda (`_reancoragem_no_mesmo_nivel`/`LimitPlaced(replaced=...)`) -- nenhum
mecanismo novo, mesmo usado pelo rearme por tempo de `Gremah`. Sem
timeout/limiar de distancia novo (nao foi pedido).

## O que este script mede

Duas janelas, MESMO candidato T1/S16/x1 (`profit_ticks=1, stop_ticks=16,
level_spacing_ticks=1`) nos dois lados (ANTIGO x NOVO):

  1. IS historico completo: `data/raw_ticks/WDO_A_f1.parquet`, filtro
     `janela=="IS"` (72 pregoes congelados, 2.832.170 tick-barras,
     2026-02-27..2026-06-12) -- dado TICK, nao M1 (a classe documenta que
     M1 infla o numero por artefato de `_exit_fill_price`; ver `feed_kind`
     em `WdoGridReloadMaker`). `wdo_grid_reload_f1_lab.carregar_barras()`
     NAO e' usado aqui de proposito -- ela carrega M1 (`load_m1`), o feed
     ERRADO para este robo.
  2. Semana atual (2026-08-31 a 2026-09-04), tick fresco do MT5, mesmo
     padrao de `wdof1_mfe_mae_semana_2026_09_04.py::buscar_ticks_semana`.

Para cada lado: liquido, MaxDD, win%, trades, R$/dia (tabela padrao,
`backtest.intraday.report`), MAIS duas colunas extras desta rodada:
`ativo%_med` (media, entre os pregoes com dado, de "1a entrada ate' ultima
saida" dividido pela duracao real da sessao naquele pregao -- e' o numero
que mostra se o fix resolve a inatividade) e `repreco/preg` (media de
quantas vezes por pregao uma ordem pendente foi de fato reprecificada para
um nivel DIFERENTE -- risco a MEDIR, nao a prevenir, pedido explicito do
dono: sem limiar novo aqui, so' o numero para ele decidir depois).

O lado ANTIGO e' reproduzido por uma subclasse local (`_WdoGridReloadMaker
Antigo`) que copia o `on_bar` de antes do fix -- nao existe mais no modulo
de producao, preservado aqui SO' para esta comparacao.

Mora em `scripts/` pela mesma regra de fronteira de `wdo_grid_reload_f1_
lab.py` (precisa importar `backtest` e `strategy` ao mesmo tempo).

Uso: `python scripts/daytrade/wdo_grid_reload_reprice_fix_validacao_2026_09_04.py`
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wdo_grid_reload_f1_lab import montar_config  # noqa: E402
from wdof1_mfe_mae_semana_2026_09_04 import buscar_ticks_semana  # noqa: E402

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.report import cabecalho, linha, linha_de_resultado, num_br  # noqa: E402
from strategy.daytrade.base import EnterLimit, Exit, no_tick  # noqa: E402
from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker  # noqa: E402

CANDIDATO = dict(level_spacing_ticks=1, profit_ticks=1, stop_ticks=16)
CAPITAL_NOCIONAL = 1_000_000.0

#: Cache TICK do IS+OOS ja concatenado (mesmo arquivo usado por
#: `wdof1_defesa_recuo_sweep_2026_09_03.py` e outras rodadas desta frente) --
#: tem coluna `janela` ("IS"/"OOS") ja rotulada na geracao do cache.
CACHE_TICK = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"


def _bars_is_tick() -> pd.DataFrame:
    df = pd.read_parquet(CACHE_TICK)
    df = df[df["janela"] == "IS"]
    return df[["open", "high", "low", "close", "volume"]]


class _WdoGridReloadMakerAntigo(WdoGridReloadMaker):
    """Copia LITERAL de `on_bar` de ANTES do fix de 2026-09-04 (item 4.9):
    uma vez armada a `EnterLimit` pendente, devolve cedo pelo resto do
    pregao se o preco nao voltar a tocar o nivel -- nunca reprecifica,
    nunca cancela. So' existe aqui para a comparacao ANTES/DEPOIS desta
    rodada -- nao usar em producao, nao importar fora deste script."""

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        state = self._state
        actions: list = []

        if state.open_price is None:
            state.open_price = no_tick(bar.open, self.tick_size)
            state.anchor_price = state.open_price

        if (self.session_stop_brl is not None and not state.session_halted
                and session_pnl_brl <= -self.session_stop_brl):
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if positions:
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
            if self.defesa_ativa:
                for pos in positions:
                    if self._defesa_deve_fechar(pos, bar):
                        return [Exit(reason="defesa_recuo")]
            return []

        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        if state.pending_side is not None:
            return actions  # comportamento ANTIGO (bug): nunca reprecifica, nunca cancela

        next_side = self._next_side_to_arm()
        if next_side is None:
            return actions

        if self.reanchor_mode == "rolling_last_price":
            state.anchor_price = no_tick(bar.close, self.tick_size)

        state.pending_side = next_side
        level_price = self._level_price(next_side)
        return [EnterLimit(
            side=next_side,
            limit_price=level_price,
            initial_target=self._target_price(next_side, level_price),
            initial_stop=self._stop_price(next_side, level_price),
            quantity=self._quantidade_da_entrada(),
            reason="wdo_grid_reload_" + next_side,
        )]


class _WdoGridReloadMakerComContador(WdoGridReloadMaker):
    """MESMA classe de producao (comportamento NOVO, pos-fix) -- so' conta,
    por pregao, quantas vezes `on_bar` de fato reprecificou uma ordem
    pendente para um nivel DIFERENTE (o que o motor trataria como
    cancela-e-substitui, `LimitPlaced(replaced=...)`). Existe so' para a
    medicao de frequencia desta rodada -- ver a secao "Risco a medir" do
    pedido original."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reprecos_por_dia: dict[date, int] = {}

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        pendente_antes = self._state.pending_side
        nivel_antes = self._level_price(pendente_antes) if pendente_antes is not None else None
        actions = super().on_bar(ts, bar, positions, session_pnl_brl)
        if (pendente_antes is not None and actions
                and isinstance(actions[0], EnterLimit)
                and abs(actions[0].limit_price - nivel_antes) > 1e-9):
            dia = pd.Timestamp(ts).date()
            self.reprecos_por_dia[dia] = self.reprecos_por_dia.get(dia, 0) + 1
        return actions


def _pct_pregao_ativo_por_dia(bars: pd.DataFrame, trades: list) -> dict[date, float]:
    """Por pregao com dado: `100 x (ultima_saida - 1a_entrada) / duracao_
    real_da_sessao` (janela min->max das PROPRIAS barras do dia, nao um
    horario nominal). 0,0 num dia sem nenhum trade."""
    resultado: dict[date, float] = {}
    for dia, grupo in bars.groupby(bars.index.date):
        inicio_sessao = grupo.index.min()
        fim_sessao = grupo.index.max()
        duracao_sessao = (fim_sessao - inicio_sessao).total_seconds()
        trades_do_dia = [t for t in trades if pd.Timestamp(t.entry_ts).date() == dia]
        if not trades_do_dia or duracao_sessao <= 0:
            resultado[dia] = 0.0
            continue
        primeira_entrada = min(pd.Timestamp(t.entry_ts) for t in trades_do_dia)
        ultima_saida = max(pd.Timestamp(t.exit_ts) for t in trades_do_dia)
        resultado[dia] = 100.0 * (ultima_saida - primeira_entrada).total_seconds() / duracao_sessao
    return resultado


def _roda_e_reporta(rotulo_janela: str, bars: pd.DataFrame) -> None:
    print(f"\n=== {rotulo_janela} ===")
    pregoes = sorted(set(bars.index.date))
    print(f"{len(bars):,} barras/ticks, {len(pregoes)} pregoes: "
          f"{pregoes[0]} .. {pregoes[-1]}")
    cfg = montar_config()

    strat_antigo = _WdoGridReloadMakerAntigo(**CANDIDATO)
    resultado_antigo = run_intraday_backtest(bars, strat_antigo, cfg)
    ativo_antigo = _pct_pregao_ativo_por_dia(bars, resultado_antigo.trades)

    strat_novo = _WdoGridReloadMakerComContador(**CANDIDATO)
    resultado_novo = run_intraday_backtest(bars, strat_novo, cfg)
    ativo_novo = _pct_pregao_ativo_por_dia(bars, resultado_novo.trades)

    media_ativo_antigo = sum(ativo_antigo.values()) / len(ativo_antigo) if ativo_antigo else 0.0
    media_ativo_novo = sum(ativo_novo.values()) / len(ativo_novo) if ativo_novo else 0.0
    reprecos = list(strat_novo.reprecos_por_dia.values())
    media_reprecos = sum(reprecos) / len(pregoes) if pregoes else 0.0
    max_reprecos = max(reprecos) if reprecos else 0

    linhas = [
        linha_de_resultado(
            "ANTIGO (bug, estaciona)", resultado_antigo, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={"ativo%_med": num_br(media_ativo_antigo, 1), "repreco/preg": "0,0"},
        ),
        linha_de_resultado(
            "NOVO (fix item 4.9)", resultado_novo, CAPITAL_NOCIONAL, capital_nocional=True,
            extras={"ativo%_med": num_br(media_ativo_novo, 1),
                    "repreco/preg": num_br(media_reprecos, 1)},
        ),
    ]
    print(cabecalho(("ativo%_med", "repreco/preg")))
    for item in linhas:
        print(linha(item, ("ativo%_med", "repreco/preg")))

    print(f"\n% do pregao ativo por dia -- ANTIGO: "
          + ", ".join(f"{d}={num_br(v, 1)}%" for d, v in sorted(ativo_antigo.items())))
    print(f"% do pregao ativo por dia -- NOVO:   "
          + ", ".join(f"{d}={num_br(v, 1)}%" for d, v in sorted(ativo_novo.items())))
    print(f"reprecos por pregao (NOVO), so' onde > 0: "
          + (", ".join(f"{d}={n}" for d, n in sorted(strat_novo.reprecos_por_dia.items()) if n)
             or "nenhum"))
    print(f"reprecos/pregao -- media={num_br(media_reprecos, 1)}, "
          f"maximo num pregao={max_reprecos} (n={len(pregoes)} pregoes)")
    if max_reprecos >= 100:
        print("[SINALIZACAO] pelo menos 1 pregao passou de 100 reprecificacoes -- "
              "frequencia operacionalmente ALTA (nao foi pedido limiar novo, so' "
              "reportar para o dono decidir).")


def main() -> None:
    print("[validacao_reprice_fix] === 1. IS historico completo (tick) ===")
    bars_is = _bars_is_tick()
    _roda_e_reporta("IS completo (tick, janela=='IS')", bars_is)

    print("\n[validacao_reprice_fix] === 2. semana atual (tick MT5 fresco) ===")
    bars_semana = buscar_ticks_semana()
    _roda_e_reporta("semana 2026-08-31..2026-09-04 (ticks)", bars_semana)


if __name__ == "__main__":
    main()
