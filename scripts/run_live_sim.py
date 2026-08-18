"""Simulador acelerado do AMBIENTE AO VIVO (nao do backtest).

Por que isto existe
--------------------
O robo real gera pouquissimas decisoes (o campeao atual fez 26 trades em 16
anos) — esperar em tempo real pra ver se uma ordem entra corretamente, se o
stop e registrado direito, se o saque dispara no dia certo, levaria anos.
Este script reproduz o HISTORICO REAL dia a dia atraves do `LiveRuntime` de
verdade — o MESMO objeto que vai rodar no servidor —, so que sem esperar
nenhum segundo entre um pregao e o proximo. Nao testa se a ESTRATEGIA e boa
(isso e o backtest); testa se o ENCANAMENTO operacional (decisao -> intencao
-> ordem -> posicao -> stop -> saque -> diario) funciona igual ao que o
backtest ja validou.

A prova mais forte que a maquinaria esta fiel: reproduzir o `run_backtest`
oficial da MESMA janela e comparar. Sizing, custo e stop default vem do
MESMO modulo (`backtest/sizing.py`) nos dois lados — se a maquinaria ao vivo
esta correta, os numeros tem que ficar proximos (nao identicos: a ordem ao
vivo executa contra a cotacao do momento em vez do open exato do dia
seguinte, e o stop intra-dia dispara sobre um preco pontual em vez de
`low[D]` — ver `live/robots.py`; divergencias pequenas sao esperadas e
documentadas, uma divergencia GRANDE e sinal de bug na maquinaria).

Conta e banco SEPARADOS da operacao real
-----------------------------------------
Usa uma conta dedicada ("simulacao") num arquivo `.sqlite` proprio
(`db/live_sim.sqlite` por padrao) — nunca toca na conta "principal" nem no
diario oficial. Por padrao o banco de simulacao e APAGADO no inicio de cada
rodada (e um artefato descartavel do proprio script); use `--keep` pra manter
o historico entre rodadas.

Uso:
    .venv/Scripts/python.exe scripts/run_live_sim.py
    .venv/Scripts/python.exe scripts/run_live_sim.py --years 5 --capital 10000
    .venv/Scripts/python.exe scripts/run_live_sim.py --start 2015-01-01 --end 2020-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from backtest.runner import run as run_backtest_dispatch
from backtest.withdrawal import official_policy
from core.config import BENCHMARK, DB_PATH, HISTORY_START, LIVE_DB_PATH, ROOT, WATCHLIST, BacktestConfig
from core.live_models import IntentKind, IntentStatus
from journal import live_store as store
from live.broker import PaperBroker
from live.feed import ReplayFeed
from live.runtime import LiveRuntime
from market_data.loader import load_universe
from scheduler import latest_common_date
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio

ACCOUNT_NAME = "simulacao"
# Absoluto (ROOT, não `Path("db/...")` relativo ao cwd) — FEAT-000: rodar
# `python scripts/run_live_sim.py` de outro diretório criava (e apagava) um
# `db/` no lugar errado.
SIM_DB = ROOT / "db" / "live_sim.sqlite"


def _ensure_disposable_sim_db(path: Path) -> None:
    """Recusa `path` se ele coincidir com um banco NÃO-descartável.

    `main()` apaga `SIM_DB` no início de cada rodada (é um artefato
    descartável do próprio script — ver docstring do módulo). Esta função
    existe para o dia em que `SIM_DB` apontar, por engano, para o banco ao
    vivo real (`LIVE_DB_PATH`) ou para o de backtest (`DB_PATH`) — sem ela, o
    `.unlink()` de `main()` apagaria dado de produção sem aviso nenhum.

    `SystemExit` (nunca `assert`): uma salvaguarda contra apagar o banco real
    não pode evaporar sob `python -O`, que remove `assert` do bytecode.
    """
    resolved = path.resolve()
    for guarded in (LIVE_DB_PATH, DB_PATH):
        if resolved == guarded.resolve():
            raise SystemExit(
                f"[sim] recusando: {path} resolve para {guarded}, que NÃO é "
                "descartável (banco de operação real ou de backtest)."
            )


def money(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def main() -> None:
    _ensure_disposable_sim_db(SIM_DB)
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--capital", type=float, default=1_000.0)
    p.add_argument("--years", type=float, default=None,
                   help="simula os ultimos N anos (default: janela FULL inteira)")
    p.add_argument("--start", default=None, help="YYYY-MM-DD, sobrescreve --years")
    p.add_argument("--end", default=None, help="YYYY-MM-DD, default = ultima data comum")
    p.add_argument("--keep", action="store_true",
                   help="nao apaga o banco de simulacao anterior antes de rodar")
    args = p.parse_args()

    end_ts = pd.Timestamp(args.end) if args.end else latest_common_date()
    if args.start:
        start_ts = pd.Timestamp(args.start)
    elif args.years:
        start_ts = end_ts - pd.DateOffset(years=args.years)
    else:
        start_ts = pd.Timestamp(HISTORY_START)

    if SIM_DB.exists() and not args.keep:
        print(f"[sim] apagando banco de simulacao anterior ({SIM_DB})")
        SIM_DB.unlink()

    print(f"[sim] janela {start_ts.date()} -> {end_ts.date()} | capital R$ {args.capital:,.2f}"
          .replace(",", "."))

    universe = load_universe(list(WATCHLIST))
    tickers = [t for t in WATCHLIST]
    all_dates = pd.DatetimeIndex(sorted(
        set.intersection(*(set(df.loc[start_ts:end_ts].index) for t, df in universe.items()
                          if t != BENCHMARK))
    ))
    if len(all_dates) < 2:
        print("[sim] janela tem menos de 2 pregoes em comum entre os tickers — nada a simular.")
        return

    feed = ReplayFeed()
    broker = PaperBroker(feed)
    config = BacktestConfig(initial_capital=args.capital, lot_size=1)
    rt = LiveRuntime(
        account_name=ACCOUNT_NAME, strategy=DipTop1Portfolio(),
        policy=official_policy(args.capital), feed=feed, broker=broker,
        config=config, tickers=tickers, db_path=SIM_DB, data_dir=None,
    )
    rt.ensure_account()

    entradas = saidas = stops = saques = expiradas = 0
    for i, d in enumerate(all_dates):
        today = d.date()
        df_by_ticker = {t: universe[t] for t in tickers}

        # abertura: aplica o que foi decidido no fecho anterior
        opn = {t: float(df_by_ticker[t].at[d, "open"]) for t in tickers if d in df_by_ticker[t].index}
        for t, px in opn.items():
            feed.set(t, px)
        exec_report = rt.execute_session(today)
        entradas += exec_report.detail.get("entradas", 0)
        saidas += exec_report.detail.get("saidas", 0)
        saques += exec_report.detail.get("saques", 0)
        expiradas += exec_report.detail.get("expiradas", 0)

        # intra-dia: cotacao no minimo do dia, checagem conservadora de stop
        # (mais proxima do `low[D] <= stop` que o backtest usa)
        low = {t: float(df_by_ticker[t].at[d, "low"]) for t in tickers if d in df_by_ticker[t].index}
        for t, px in low.items():
            feed.set(t, px)
        tick_report = rt.intraday_tick(today)
        stops += tick_report.detail.get("stops", 0)

        # fecho: decide para o proximo pregao
        rt.close_and_decide(today)

        if i % 250 == 0 or i == len(all_dates) - 1:
            with store.live_journal(SIM_DB) as conn:
                acc = store.load_account(conn, ACCOUNT_NAME)
            print(f"  [{today}] equity R$ {acc.cash + acc.invested({t: low.get(t, 0) for t in tickers}):,.2f}"
                  .replace(",", "."))

    with store.live_journal(SIM_DB) as conn:
        acc = store.load_account(conn, ACCOUNT_NAME)
        wds = store.withdrawals(conn, acc.id)
        equity_hist = store.equity_series(conn, acc.id)

    marks = {t: float(universe[t].loc[:end_ts, "close"].iloc[-1]) for t in tickers}
    carteira = acc.equity(marks)
    patrimonio = acc.patrimonio(marks)

    print("\n" + "=" * 70)
    print("RESULTADO DO SIMULADOR (maquinaria ao vivo, dado historico real)")
    print("=" * 70)
    print(f"pregões simulados        {len(all_dates)}")
    print(f"entradas executadas      {entradas}")
    print(f"saídas executadas        {saidas}")
    print(f"stops disparados intra-dia {stops}")
    print(f"saques executados        {saques}")
    print(f"intenções expiradas      {expiradas}  (deveria ser 0 — indicaria bug de atraso)")
    print(f"posições abertas no fim  {len(acc.positions)}")
    print(f"caixa final              {money(acc.cash)}")
    print(f"carteira final           {money(carteira)}")
    print(f"caixa externo (saques)   {money(acc.external_cash)}")
    print(f"patrimônio final         {money(patrimonio)}")
    if wds:
        print(f"saques no período: {len(wds)}, total {money(sum(w['executed'] for w in wds))}")

    # ---------- comparação com o backtest oficial da mesma janela ----------
    print("\n" + "-" * 70)
    print("Comparação com o backtest oficial (mesma estratégia, mesma janela)")
    print("-" * 70)
    ref = run_backtest_dispatch(
        universe, DipTop1Portfolio(), config,
        start=start_ts.strftime("%Y-%m-%d"), end=end_ts.strftime("%Y-%m-%d"),
    )
    diff_pct = (carteira / ref.metrics["final_capital"] - 1.0) * 100 if ref.metrics["final_capital"] else 0.0
    print(f"backtest capital final   {money(ref.metrics['final_capital'])}  ({ref.metrics['trades_count']} trades)")
    print(f"simulador carteira final {money(carteira)}")
    print(f"diferença                {diff_pct:+.2f}%  "
          f"({'dentro do esperado (execução com preço/momento diferente)' if abs(diff_pct) < 5 else 'GRANDE — investigar a maquinaria antes de confiar'})")

    print(f"\nBanco de simulação: {SIM_DB} (conta '{ACCOUNT_NAME}') — inspecione com "
          f"'python scripts/run_live.py status' apontando pra esse banco, ou pelas tabelas live_* direto.")


if __name__ == "__main__":
    main()
