"""WDO F1 -- SAIDA ASSIMETRICA: inverte a razao ganho:perda do T2/S16, em vez
de tentar de novo filtrar QUANDO entrar (7 hipoteses de timing ja refutadas
hoje, 2026-09-11 -- ver o historico da sessao). O problema medido nao e' a
entrada: e' que o robo ganha +1,20 pts (alvo fixo de 2 ticks) e perde -8,5
pts (stop a mercado de 16 ticks) quando erra, exigindo 87,6% de acerto so'
para empatar -- e o acerto real trava em 82-84% (3 amostras independentes).

TRES IDEIAS, MEDIDAS SOBRE O MESMO MOTOR REALISTA (fila calibrada de
`backtest.intraday.fidelidade`, sem prazo, `config_for`/`profile_for`,
`backtest.intraday.engine.run_intraday_backtest`, capital REAL R$375 por
pregao -- nunca um valor arbitrario, ver CLAUDE.md):

  (A) TRAILING/BREAKEVEN STOP -- alvo fixo de 2 ticks REMOVIDO
      (`initial_target=None`, nunca uma ordem a mercado no meio do
      caminho): o STOP (unica excecao ao "nunca a mercado" do desenho
      fechado -- ver CLAUDE.md secao "O desenho de execucao e FECHADO")
      sobe conforme o preco anda a favor, via `AdjustStop` (o motor so'
      aceita se for MAIS protetor -- nunca afrouxa, `machine.py` linha
      ~1658). O alvo NUNCA fecha a posicao: so' o stop (que comeca largo,
      16 ticks, e aperta) ou o achatamento de fim de pregao. Implementado
      em `WdoTrailingStopMaker` abaixo, subclasse de `WdoGridReloadMaker`
      que reaproveita TODA a mecanica de entrada/reancoragem/capital do
      robo de producao e intercepta so' dois pontos da saida do `on_bar`
      do pai: (1) remove o `initial_target` da `EnterLimit` armada, (2)
      quando ha posicao aberta e o pai devolveria `[]` (alvo/defesa/
      trailing nativos desligados de proposito), calcula o `AdjustStop`
      do trailing novo. NAO usa o `trailing_ativo` ja existente na classe
      porque aquele fecha via `Exit(reason="trailing_lucro")`, que o
      motor executa A MERCADO na abertura da proxima barra (`machine.py`,
      ramo `isinstance(action, (Enter, Exit))` -> `_close_position(...,
      bar.open, ...)`) -- exatamente o padrao de "alvo a mercado" que o
      desenho fechado proibe (ja custou ~50 celulas, ver CLAUDE.md).
      Sub-variantes: breakeven puro (sem trailing continuo depois de
      armar) e trailing continuo (gap fixo atras do pico).

  (B) STOP MAIS APERTADO -- T2 fixo, stop 6/8/10/12 (mantem o motor
      corrigido pos-2026-09-09: fila calibrada, sem prazo, fatia real).

  (C) ALVO MAIOR -- T3/T4, S16 fixo.

Os dois dias reais disponiveis: 2026-09-10 (a sessao do freio duro, perda
real R$116,00) e 2026-09-11 (sombra real -R$144,00). Tick a tick, baixado
DIRETO do terminal MT5 (Rico, WDOV26 -- front month por CALENDARIO, ver
`core.instruments.front_month_contract`) porque os parquets canonicos do
projeto (`data/raw_ticks/WDO_A_*.parquet`) sao de 2026-09-07 e nao cobrem
essas duas sessoes ainda.

Capital: R$375 (piso real do WDO@ com reserva, `contracts_from_capital_
com_reserva`), UM pregao por vez, NUNCA reposto entre os dois -- so' ha 2
dias, cada um e' uma observacao unica, nao uma media de varias.

2 pregoes e' pouco dado -- declarado aqui e no relatorio. O que se pode
afirmar com 2 pregoes e' MAGNITUDE e DIRECAO, nunca significancia."""
from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace as dc_replace
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)
DIAS = ["2026-09-10", "2026-09-11"]

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
CORRETAGEM_RT = 0.50
VALOR_TICK = 5.0


# ---------------------------------------------------------------------------
# Variante A -- trailing/breakeven stop (definida no MODULO, nao dentro de
# main(), para o ProcessPoolExecutor conseguir fazer pickle da classe).
# ---------------------------------------------------------------------------
def _build_trailing_stop_class():
    from strategy.daytrade.base import AdjustStop, EnterLimit
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker

    class WdoTrailingStopMaker(WdoGridReloadMaker):
        """Ver a docstring do modulo -- alvo fixo removido, stop sobe."""

        name = "wdo_trailing_stop_maker_experimental"

        def __init__(self, *args, trail_arm_ticks: int = 2,
                     trail_breakeven_ticks: float = 0.0,
                     trail_gap_ticks: float | None = None, **kwargs):
            kwargs.setdefault("trailing_ativo", False)
            kwargs.setdefault("defesa_ativa", False)
            super().__init__(*args, **kwargs)
            if self.trailing_ativo or self.defesa_ativa:
                raise ValueError(
                    "WdoTrailingStopMaker e' experimental e nao combina com "
                    "trailing_ativo/defesa_ativa (os dois fecham via Exit a "
                    "mercado -- ver a docstring do modulo)."
                )
            self.trail_arm_ticks = trail_arm_ticks
            self.trail_breakeven_ticks = trail_breakeven_ticks
            self.trail_gap_ticks = trail_gap_ticks
            self._trail_armado: dict = {}
            self._trail_pico: dict = {}

        def on_session_start(self, session_date) -> None:
            super().on_session_start(session_date)
            self._trail_armado = {}
            self._trail_pico = {}

        def _trailing_stop_action(self, pos, bar):
            chave = (pos.side, pos.entry_ts)
            preco_favoravel = bar.high if pos.side == "long" else bar.low
            pico_anterior = self._trail_pico.get(chave, pos.entry_price)
            pico = (max(pico_anterior, preco_favoravel) if pos.side == "long"
                    else min(pico_anterior, preco_favoravel))
            self._trail_pico[chave] = pico

            ticks_do_pico = abs(pico - pos.entry_price) / self.tick_size
            if ticks_do_pico + 1e-9 < self.trail_arm_ticks:
                return None  # ainda nao andou o suficiente a favor -- nao arma

            ja_armado = self._trail_armado.get(chave, False)
            self._trail_armado[chave] = True

            if self.trail_gap_ticks is None:
                if ja_armado:
                    return None  # breakeven puro: move 1x, nunca mais
                offset = self.trail_breakeven_ticks * self.tick_size
                novo_stop = (pos.entry_price + offset if pos.side == "long"
                             else pos.entry_price - offset)
            else:
                offset = self.trail_gap_ticks * self.tick_size
                novo_stop = (pico - offset if pos.side == "long"
                             else pico + offset)
            return AdjustStop(new_stop=novo_stop)

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            actions = super().on_bar(ts, bar, positions, session_pnl_brl)
            if positions:
                # O pai (com trailing_ativo/defesa_ativa desligados aqui)
                # so' devolve [] neste ramo, ou [Exit(...)] se
                # session_stop_brl disparar (nao usado nesta variante,
                # default None) -- adiciona o trailing-stop novo por cima.
                novas = list(actions)
                for pos in positions:
                    acao = self._trailing_stop_action(pos, bar)
                    if acao is not None:
                        novas.append(acao)
                return novas
            # Sem posicao: se o pai armou/reancorou uma EnterLimit, remove o
            # alvo estatico -- e' o UNICO ponto de intervencao necessario no
            # caminho de entrada (reancoragem, freio, capital, quantidade:
            # tudo herdado sem mudanca).
            return [
                (dc_replace(a, initial_target=None) if isinstance(a, EnterLimit) else a)
                for a in actions
            ]

    return WdoTrailingStopMaker


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


def _roda(spec: dict):
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    dia = spec["dia"]
    bars = pd.read_parquet(BARS_DIR / f"WDOV26_{dia}.parquet")
    if bars.empty:
        return None

    robo_prod = get_daytrade_robot("wdo_grid_reload_maker")
    campos_comuns = (
        "symbol", "tick_size", "level_spacing_ticks",
        "reanchor_mode", "reancora_min_segundos", "reancora_min_ticks",
        "max_trades_per_side", "session_stop_brl",
        "margin_per_contract_brl", "margin_buffer", "hard_cap_contratos",
        "point_value_brl", "risco_pct_por_trade",
    )
    base_kwargs = {c: getattr(robo_prod, c) for c in campos_comuns}

    variante = spec["variante"]
    if variante == "A":
        WdoTrailingStopMaker = _build_trailing_stop_class()
        kwargs = dict(base_kwargs)
        kwargs["stop_ticks"] = spec["stop_inicial"]
        kwargs["profit_ticks"] = spec.get("profit_ticks_nominal", 2)  # so' documental (alvo removido)
        kwargs["fatiar_saida_alvo"] = False  # sem alvo, nao ha' o que fatiar
        kwargs["exit_ttl_bars"] = None
        strat = WdoTrailingStopMaker(
            trail_arm_ticks=spec["arm"],
            trail_breakeven_ticks=spec["breakeven"],
            trail_gap_ticks=spec["gap"],
            **kwargs,
        )
    else:
        kwargs = dict(base_kwargs)
        kwargs["profit_ticks"] = spec["alvo"]
        kwargs["stop_ticks"] = spec["stop"]
        kwargs["fatiar_saida_alvo"] = True
        from strategy.daytrade.lab.wdo_grid_reload_maker import EXIT_TTL_BARS_SEM_PRAZO
        kwargs["exit_ttl_bars"] = EXIT_TTL_BARS_SEM_PRAZO
        strat = WdoGridReloadMaker(**kwargs)

    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
        # fila NUNCA se digita aqui -- `config_for` resolve por
        # `backtest.intraday.fidelidade` (WDO@ 438/489, Kaplan-Meier).
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    equity = res.equity_curve
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl < 0]
    return {
        "dia": dia, "variante": spec["rotulo"],
        "n": len(trades),
        "n_ganhos": len(ganhos), "n_perdas": len(perdas),
        "pnl": sum(t.pnl_brl for t in trades),
        "ganho_medio": (sum(ganhos) / len(ganhos)) if ganhos else float("nan"),
        "perda_media": (sum(perdas) / len(perdas)) if perdas else float("nan"),
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "caixa_fim": float(equity.iloc[-1]) if len(equity) else float("nan"),
    }


def main() -> None:
    for dia in DIAS:
        if not (BARS_DIR / f"WDOV26_{dia}.parquet").exists():
            raise SystemExit(f"faltam barras de {dia} em {BARS_DIR}")

    specs = []
    # --- baseline (producao) ---
    specs.append({"dia": None, "variante": "baseline", "alvo": 2, "stop": 16,
                  "rotulo": "T2/S16 (baseline)"})
    # --- (B) stop mais apertado, T2 fixo ---
    for s in (6, 8, 10, 12):
        specs.append({"dia": None, "variante": "B", "alvo": 2, "stop": s,
                      "rotulo": f"T2/S{s}"})
    # --- (C) alvo maior, S16 fixo ---
    for a in (3, 4):
        specs.append({"dia": None, "variante": "C", "alvo": a, "stop": 16,
                      "rotulo": f"T{a}/S16"})
    # --- (A) trailing/breakeven stop ---
    specs.append({"dia": None, "variante": "A", "arm": 2, "breakeven": 0.0,
                  "gap": None, "stop_inicial": 16,
                  "rotulo": "A1 breakeven+0 (arm2/S16i)"})
    specs.append({"dia": None, "variante": "A", "arm": 2, "breakeven": 1.0,
                  "gap": None, "stop_inicial": 16,
                  "rotulo": "A2 breakeven+1 (arm2/S16i)"})
    specs.append({"dia": None, "variante": "A", "arm": 2, "breakeven": 0.0,
                  "gap": 4.0, "stop_inicial": 16,
                  "rotulo": "A3 trailing gap4 (arm2/S16i)"})
    specs.append({"dia": None, "variante": "A", "arm": 2, "breakeven": 0.0,
                  "gap": 8.0, "stop_inicial": 16,
                  "rotulo": "A4 trailing gap8 (arm2/S16i)"})

    jobs = []
    for spec in specs:
        for dia in DIAS:
            job = dict(spec)
            job["dia"] = dia
            jobs.append(job)

    print(f"[saida assimetrica] {len(jobs)} execucoes ({len(specs)} variantes "
          f"x {len(DIAS)} pregoes), capital R${CAPITAL_REAL_BRL:.0f}/pregao, "
          f"fila calibrada (fidelidade.py), sem prazo\n", flush=True)

    resultados: dict[str, dict[str, dict]] = {}
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda, j): j for j in jobs}
        feitos = 0
        for fut in as_completed(futuros):
            j = futuros[fut]
            r = fut.result()
            feitos += 1
            if r is None:
                print(f"  [{feitos}/{len(jobs)}] {j['rotulo']} {j['dia']}: SEM DADO")
                continue
            resultados.setdefault(r["variante"], {})[r["dia"]] = r
            print(f"  [{feitos}/{len(jobs)}] {r['variante']:<28}{r['dia']}  "
                  f"n={r['n']:<5} pnl=R${r['pnl']:>10.2f}  caixa_min=R${r['caixa_min']:>8.2f}",
                  flush=True)

    # ---- tabela final -----------------------------------------------
    print()
    cab = (f"{'variante':<28}{'dia':<12}{'n':>5}{'win%':>8}{'ganho_med':>11}"
           f"{'perda_med':>11}{'BE emp.':>9}{'IC95 win%':>18}{'liquido R$':>12}"
           f"{'caixa_min':>11}")
    print(cab)
    print("-" * len(cab))
    for spec in specs:
        rot = spec["rotulo"]
        por_dia = resultados.get(rot, {})
        for dia in DIAS:
            r = por_dia.get(dia)
            if r is None:
                print(f"{rot:<28}{dia:<12}{'--':>5}")
                continue
            n = r["n"]
            win = 100.0 * r["n_ganhos"] / n if n else float("nan")
            ganho_med = r["ganho_medio"]
            perda_med = abs(r["perda_media"]) if r["n_perdas"] else float("nan")
            be_emp = (100.0 * perda_med / (ganho_med + perda_med)
                      if (r["n_ganhos"] and r["n_perdas"]) else float("nan"))
            lo, hi = ic_wilson(r["n_ganhos"], n)
            ic_txt = f"[{lo:.1f};{hi:.1f}]" if n else "--"
            print(f"{rot:<28}{dia:<12}{n:>5}{win:>7.1f}%"
                  f"{ganho_med:>11.2f}{r['perda_media']:>11.2f}"
                  f"{be_emp:>8.1f}%{ic_txt:>18}{r['pnl']:>12.2f}"
                  f"{r['caixa_min']:>11.2f}")
        print()

    print("LEITURA: BE emp. = perda_media/(ganho_medio+perda_media) -- o nulo "
          "empirico da PROPRIA amostra, nao o nominal em ticks (que nao se "
          "aplica a variante A, onde o alvo nao e' fixo). IC95 win% e' Wilson "
          "sobre n_ganhos/n; compare contra BE emp. da MESMA linha.")
    print("2 pregoes: qualquer numero aqui e' MAGNITUDE/DIRECAO, nao "
          "significancia -- n por variante e' de dezenas a poucas centenas.")


if __name__ == "__main__":
    main()
