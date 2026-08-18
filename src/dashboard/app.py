from __future__ import annotations

import asyncio
import csv
import io
import json
import queue
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import BENCHMARK, WATCHLIST
from core.indicators import sma
from dashboard import live_control, live_service, simulate as sim_mgr
from journal import reader
from live import clock
from market_data.download import download_macro
from market_data.loader import load_one
from scheduler import refresh_champion_rankings, refresh_market_data
from strategy.registry import get_strategy, list_strategies

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _static_v(css_filename: str) -> int:
    """Mtime do arquivo CSS, usado como query-string cache-buster nos <link>.

    Sem isso, o navegador pode servir uma versão antiga de pages.css do cache
    depois de uma edição — o HTML (nunca cacheado) mostra a estrutura nova mas
    o estilo fica o velho, um bug confuso de diagnosticar. Muda sozinho a cada
    edição do arquivo, sem precisar lembrar de bump manual.
    """
    try:
        return int((BASE_DIR / "static" / "css" / css_filename).stat().st_mtime)
    except FileNotFoundError:
        return 0


TEMPLATES.env.globals["static_v"] = _static_v

MACRO_REFRESH_SECONDS  = 10 * 60          # 10 min: Selic + USD/BRL (fast, ~2s)
MARKET_REFRESH_SECONDS = 60 * 60          # 1 h : OHLCV yfinance (~10s por ticker)
CHAMPION_REFRESH_SECONDS = 6 * 60 * 60    # 6 h : rerroda o ranking automático de robôs


async def _wait_for_active_window() -> None:
    """Dorme até a janela ativa (pregão B3 ±1h, ver `live.clock`) abrir de
    novo — nada aqui muda fora do horário de mercado, então não há motivo
    para os 3 loops abaixo ficarem baixando dado a noite inteira ou no fim
    de semana. `seconds_until_active_window` já sabe a data exata (feriado
    incluso); um `asyncio.sleep(0)` quando já estamos dentro da janela."""
    wait = clock.seconds_until_active_window()
    if wait > 0:
        await asyncio.sleep(wait)


async def _macro_refresh_loop() -> None:
    """Baixa Selic + USD/BRL do BCB SGS a cada MACRO_REFRESH_SECONDS, só
    dentro da janela ativa de pregão."""
    while True:
        await _wait_for_active_window()
        try:
            written = await asyncio.to_thread(download_macro)
            if written:
                names = ", ".join(sorted(written.keys()))
                print(f"[macro-refresh {datetime.now().strftime('%H:%M:%S')}] atualizado: {names}")
        except Exception as e:
            print(f"[macro-refresh] erro: {e}")
        await asyncio.sleep(MACRO_REFRESH_SECONDS)


async def _market_refresh_loop() -> None:
    """Baixa OHLCV (yfinance) periodicamente, só dentro da janela ativa."""
    await asyncio.sleep(30)
    while True:
        await _wait_for_active_window()
        try:
            await asyncio.to_thread(refresh_market_data)
        except Exception as e:
            print(f"[market-refresh] erro: {e}")
        await asyncio.sleep(MARKET_REFRESH_SECONDS)


async def _champion_refresh_loop() -> None:
    """Rerroda o ranking automático (todo robô descoberto, janelas FULL + 5Y + 1Y)
    sempre que os dados avançarem. É isso que mantém o pódio da home honesto
    sem promoção manual — ver `scheduler.refresh_champion_rankings`. Só roda
    dentro da janela ativa: o ranking não muda enquanto o dado de mercado
    (que ele consome) também não muda.
    """
    await asyncio.sleep(5)
    while True:
        await _wait_for_active_window()
        try:
            summary = await asyncio.to_thread(refresh_champion_rankings)
            if summary["refreshed"]:
                print(f"[champion-refresh] {len(summary['refreshed'])} runs atualizadas")
        except Exception as e:
            print(f"[champion-refresh] erro: {e}")
        await asyncio.sleep(CHAMPION_REFRESH_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(_macro_refresh_loop()),
        asyncio.create_task(_market_refresh_loop()),
        asyncio.create_task(_champion_refresh_loop()),
    ]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass


app = FastAPI(title="meta — Terminal Editorial", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _tags_by_trade(rows: list[dict]) -> dict[int, list[dict]]:
    return {t["id"]: reader.trade_tags(t["id"]) for t in rows}


def _latest_available_date() -> str:
    """Última data OHLCV comum a todos os tickers da watchlist + benchmark."""
    latest: pd.Timestamp | None = None
    for t in list(WATCHLIST) + [BENCHMARK]:
        try:
            idx_last = load_one(t).index[-1]
        except FileNotFoundError:
            continue
        if latest is None or idx_last < latest:
            latest = idx_last
    return latest.strftime("%Y-%m-%d") if latest is not None else pd.Timestamp.today().strftime("%Y-%m-%d")


# ============ HOME = STRATEGIES ==========================================

RUNS_PAGE_SIZE = 10


def _parse_float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    runs = reader.list_runs(limit=RUNS_PAGE_SIZE, offset=0)
    top3_full = reader.top_strategies_by_final_capital(top_n=3, run_kind="champion_full")
    top3_5y = reader.top_strategies_by_final_capital(top_n=3, run_kind="champion_5y")
    top3_1y = reader.top_strategies_by_final_capital(top_n=3, run_kind="champion_1y")
    window_full = reader.latest_champion_window("champion_full")
    window_5y = reader.latest_champion_window("champion_5y")
    window_1y = reader.latest_champion_window("champion_1y")
    # Rótulo "N anos" da janela FULL calculado ao vivo (não hardcoded) — cresce
    # sozinho conforme os dados avançam, em vez de ficar "16 anos" congelado.
    full_years_label = None
    if window_full:
        span_days = (pd.Timestamp(window_full[1]) - pd.Timestamp(window_full[0])).days
        full_years_label = int(span_days / 365.25)
    # Grid "Robôs disponíveis": todo robô descoberto automaticamente
    # (strategy.discovery via registry) — não só os que já venceram um pódio.
    all_strategies = list_strategies()
    ctx = {
        "strategies": all_strategies,
        "watchlist": list(WATCHLIST),
        "default_end": _latest_available_date(),
        "recent_runs": runs,
        "top3_full": top3_full,
        "top3_5y": top3_5y,
        "top3_1y": top3_1y,
        "start_5y": window_5y[0] if window_5y else None,
        "end_5y": window_5y[1] if window_5y else None,
        "start_1y": window_1y[0] if window_1y else None,
        "end_1y": window_1y[1] if window_1y else None,
        "start_full": window_full[0] if window_full else None,
        "end_full": window_full[1] if window_full else None,
        "full_years_label": full_years_label,
        # Filtro "Robô" na tabela: todo robô conhecido pelo registry.
        "run_strategies": [s.key for s in all_strategies],
        "run_tickers": reader.distinct_run_tickers(),
        "has_more": len(runs) == RUNS_PAGE_SIZE,
        "next_offset": RUNS_PAGE_SIZE,
        "filters": {"strategy": "", "start_from": "", "end_to": "", "capital_min": "", "capital_max": "", "ticker": ""},
        "page": "strategies",
    }
    return TEMPLATES.TemplateResponse(request, "strategies_list.html", ctx)


@app.get("/runs/list", response_class=HTMLResponse)
def runs_list_fragment(
    request: Request,
    strategy: str = "",
    start_from: str = "",
    end_to: str = "",
    capital_min: str = "",
    capital_max: str = "",
    ticker: str = "",
    offset: int = 0,
):
    """Endpoint HTMX que devolve fragmento com linhas de runs (para filtro + paginação)."""
    runs = reader.list_runs(
        strategy=strategy or None,
        start_from=start_from or None,
        end_to=end_to or None,
        capital_min=_parse_float(capital_min),
        capital_max=_parse_float(capital_max),
        ticker=ticker or None,
        limit=RUNS_PAGE_SIZE,
        offset=offset,
    )
    ctx = {
        "recent_runs": runs,
        "has_more": len(runs) == RUNS_PAGE_SIZE,
        "next_offset": offset + RUNS_PAGE_SIZE,
        "filters": {
            "strategy": strategy, "start_from": start_from, "end_to": end_to,
            "capital_min": capital_min, "capital_max": capital_max, "ticker": ticker,
        },
        "append_mode": offset > 0,
    }
    return TEMPLATES.TemplateResponse(request, "partials/runs_rows.html", ctx)


@app.get("/strategies/{key}", response_class=HTMLResponse)
def strategy_detail(request: Request, key: str):
    try:
        info = get_strategy(key)
    except KeyError:
        return PlainTextResponse("Robô não encontrado.", status_code=404)
    runs = reader.list_runs(strategy=key, limit=RUNS_PAGE_SIZE, offset=0)
    ctx = {
        "strategy": info,
        "watchlist": list(WATCHLIST),
        "default_start": "2015-01-01",
        "default_end": _latest_available_date(),
        "default_capital": 1_000,
        "recent_runs": runs,
        "run_tickers": reader.distinct_run_tickers(),
        "has_more": len(runs) == RUNS_PAGE_SIZE,
        "next_offset": RUNS_PAGE_SIZE,
        "filters": {
            "strategy": key, "start_from": "", "end_to": "",
            "capital_min": "", "capital_max": "", "ticker": "",
        },
    }
    return TEMPLATES.TemplateResponse(request, "strategy_detail.html", ctx)


@app.post("/strategies/{key}/run")
async def strategies_run(
    request: Request,
    key: str,
    start_date: str = Form(...),
    capital: float = Form(1_000.0),
    fractional: str | None = Form(None),
):
    try:
        get_strategy(key)
    except KeyError:
        return PlainTextResponse("Robô não encontrado.", status_code=404)
    form = await request.form()
    tickers = form.getlist("tickers")
    if not tickers:
        return PlainTextResponse("Selecione ao menos um ativo.", status_code=400)
    end_date = _latest_available_date()
    lot_size = 1 if fractional else 100
    sim = sim_mgr.start(
        strategy_key=key,
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        capital=capital,
        lot_size=lot_size,
    )
    return RedirectResponse(url=f"/sim/{sim.id}", status_code=303)


# ============ OPERAÇÃO AO VIVO ===========================================

def _parse_optional_float(raw: str | None) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


def _parse_optional_pct(raw: str | None) -> float | None:
    """Campos de perda máxima vêm do form em porcentagem (ex.: '5' = 5%)."""
    val = _parse_optional_float(raw)
    return val / 100 if val is not None else None


OPERACAO_POLL_ACTIVE_SECONDS = 20     # dentro da janela de pregão ±1h
OPERACAO_POLL_IDLE_CAP_SECONDS = 1800  # teto fora da janela (30 min) — nunca fica cego


def _operacao_poll_seconds() -> int:
    """Intervalo do polling HTMX de `/operacao`: 20s dentro da janela ativa
    de pregão (ver `live.clock`), bem mais espaçado fora dela — sem sentido
    recarregar a tela a cada 20s de madrugada ou no fim de semana, quando
    nada no status muda. Perto da janela abrir, o intervalo encolhe sozinho
    (é o próprio `seconds_until_active_window`), então a tela volta a
    atualizar rápido bem no instante em que o pregão abre, sem precisar dar
    F5 na mão."""
    if clock.in_active_window():
        return OPERACAO_POLL_ACTIVE_SECONDS
    return min(int(clock.seconds_until_active_window()) + 1, OPERACAO_POLL_IDLE_CAP_SECONDS)


def _operacao_ctx(**extra) -> dict:
    """Contexto comum a toda rota que renderiza `operacao.html`/
    `operacao_body.html` — evita repetir as 4 chamadas em cada handler e
    esquecer uma delas (já aconteceu com `creds`/`creds_status` antes de
    virar helper)."""
    return {
        "status": live_service.get_status(),
        "proc": live_control.status(),
        "config_anterior": live_control.last_config(),
        "creds": live_control.display_credentials(),
        "creds_status": live_control.credential_status(),
        "poll_seconds": _operacao_poll_seconds(),
        **extra,
    }


@app.get("/operacao", response_class=HTMLResponse)
def operacao(request: Request):
    ctx = _operacao_ctx(page="operacao")
    return TEMPLATES.TemplateResponse(request, "operacao.html", ctx)


@app.get("/operacao/fragment", response_class=HTMLResponse)
def operacao_fragment(request: Request):
    """Corpo que o polling HTMX troca — mesmo parcial usado no load inicial
    (ver `operacao.html`), assim a página nunca duplica a marcação."""
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", _operacao_ctx())


@app.post("/operacao/iniciar", response_class=HTMLResponse)
async def operacao_iniciar(request: Request):
    """Um clique cria a conta (se preciso) e sobe o supervisor como processo
    próprio — o mesmo que `scripts/run_live.py init` + `loop` fariam na mão.
    Mode/capital só vêm do form na PRIMEIRA vez (conta ainda não existe);
    depois disso a conta já fixou os dois e não são mais editáveis por aqui."""
    form = await request.form()
    from journal import live_store

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, live_service.ACCOUNT_NAME)

    erro = None
    if conta is not None:
        # conta já existe: modo/capital são da conta, NUNCA do form — evita
        # subir o loop com um broker que não bate com o que a conta espera.
        mode, capital = conta.mode, conta.initial_capital
    else:
        mode = form.get("mode", "paper")
        capital = float(form.get("capital") or live_service.DEFAULT_CAPITAL)
        if mode == "mt5" and not form.get("confirmar_real"):
            erro = "Para operar em MT5 (dinheiro real), marque a confirmação antes de iniciar."

    if erro is None:
        try:
            cfg = live_control.ProcessConfig(
                mode=mode, capital=capital,
                floor=_parse_optional_float(form.get("floor")),
                daily_loss_limit=_parse_optional_pct(form.get("daily_loss_limit")),
                monthly_loss_limit=_parse_optional_pct(form.get("monthly_loss_limit")),
                notify_min_level=form.get("notify_min_level") or "warn",
            )
            live_control.start(cfg)
        except RuntimeError as e:
            erro = str(e)

    ctx = _operacao_ctx(erro=erro)
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", ctx)


@app.post("/operacao/parar", response_class=HTMLResponse)
def operacao_parar(request: Request):
    live_control.stop()
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", _operacao_ctx())


@app.post("/operacao/credenciais", response_class=HTMLResponse)
async def operacao_credenciais(request: Request):
    """Login da corretora (MT5) e canais de alerta (Telegram/e-mail) — salvos
    localmente (`live_control.save_credentials`) e passados ao processo do
    robô só como variável de ambiente (nunca argv). Campo em branco mantém o
    valor já salvo; a caixa "remover" de cada seção apaga só aquele canal."""
    form = await request.form()
    clear = {canal for canal in ("telegram", "smtp", "mt5") if form.get(f"remover_{canal}")}
    updates = {field: form.get(field) for field in live_control.CREDENTIAL_FIELDS}
    live_control.save_credentials(updates, clear=clear)
    ctx = _operacao_ctx(creds_msg="Credenciais salvas.")
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", ctx)


# ============ SIMULATION LIFECYCLE =======================================

@app.get("/sim/{sim_id}", response_class=HTMLResponse)
def sim_page(request: Request, sim_id: str):
    sim = sim_mgr.get(sim_id)
    if not sim:
        return PlainTextResponse("Simulação não encontrada.", status_code=404)
    try:
        info = get_strategy(sim.strategy_key)
        strategy_name = info.name
    except KeyError:
        strategy_name = sim.strategy_key
    ctx = {
        "sim": {
            "id": sim.id,
            "strategy_key": sim.strategy_key,
            "strategy_name": strategy_name,
            "tickers": sim.tickers,
            "start": sim.start,
            "end": sim.end,
            "capital": sim.capital,
            "status": sim.status,
            "run_id": sim.run_id,
        },
    }
    return TEMPLATES.TemplateResponse(request, "sim_result.html", ctx)


@app.get("/sim/{sim_id}/stream")
async def sim_stream(sim_id: str):
    sim = sim_mgr.get(sim_id)
    if not sim:
        return PlainTextResponse("Simulação não encontrada.", status_code=404)

    loop = asyncio.get_event_loop()

    async def event_gen():
        yield f"event: hello\ndata: {json.dumps({'status': sim.status})}\n\n"

        for log_evt in sim.log_history:
            yield f"event: log\ndata: {json.dumps(log_evt)}\n\n"
        for prog_evt in sim.equity_history:
            yield f"event: progress\ndata: {json.dumps(prog_evt)}\n\n"

        if sim.status in ("done", "error"):
            if sim.done_payload:
                yield f"event: done\ndata: {json.dumps(sim.done_payload)}\n\n"
            if sim.error_payload:
                yield f"event: error\ndata: {json.dumps(sim.error_payload)}\n\n"
            return

        seen_progress = len(sim.equity_history)
        seen_logs = len(sim.log_history)
        while True:
            try:
                kind, payload = await loop.run_in_executor(None, sim.events.get, True, 30)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if kind == "log":
                if seen_logs > 0:
                    seen_logs -= 1
                    continue
            elif kind == "progress":
                if seen_progress > 0:
                    seen_progress -= 1
                    continue
            yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
            if kind in ("done", "error"):
                break

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ============ RUN DETAIL (visão do resultado persistido) ================

@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: int):
    run = reader.get_run(run_id)
    if not run:
        return PlainTextResponse("Run não encontrada.", status_code=404)
    stats = reader.equity_stats(run_id) or {}
    ctx = {
        "run": run,
        "runs": reader.list_runs(),
        "equity_json": json.dumps(reader.equity_curve(run_id)),
        "stats": stats,
        "tickers": reader.distinct_tickers(run_id),
    }
    return TEMPLATES.TemplateResponse(request, "run_detail.html", ctx)


@app.get("/runs/{run_id}/trades", response_class=HTMLResponse)
def run_trades(
    request: Request,
    run_id: int,
    ticker: str | None = None,
    year: str | None = None,
    outcome: str | None = None,
    exit_reason: str | None = None,
):
    run = reader.get_run(run_id)
    if not run:
        return PlainTextResponse("Run não encontrada.", status_code=404)
    year_i = int(year) if year else None
    rows = reader.list_trades(
        run_id, ticker=ticker or None, year=year_i,
        outcome=outcome or None, exit_reason=exit_reason or None,
    )
    ctx = {
        "run": run,
        "trades": rows,
        "tags_by_trade": _tags_by_trade(rows),
        "tickers": reader.distinct_tickers(run_id),
        "years": reader.distinct_years(run_id),
        "filters": {
            "ticker": ticker or "",
            "year": year or "",
            "outcome": outcome or "",
            "exit_reason": exit_reason or "",
        },
    }
    template = "partials/trades_tbody.html" if request.headers.get("HX-Request") else "trades.html"
    return TEMPLATES.TemplateResponse(request, template, ctx)


@app.get("/runs/{run_id}/insights", response_class=HTMLResponse)
def run_insights(request: Request, run_id: int):
    run = reader.get_run(run_id)
    if not run:
        return PlainTextResponse("Run não encontrada.", status_code=404)
    ctx = {
        "run": run,
        "by_signal_quality": reader.pnl_by_tag(run_id, "signal_quality"),
        "by_regime": reader.pnl_by_tag(run_id, "market_regime_at_entry"),
        "by_exit": reader.pnl_by_tag(run_id, "exit_type"),
        "by_vol": reader.pnl_by_tag(run_id, "volatility_bucket"),
        "ifr_data_json": json.dumps(reader.ifr_distribution(run_id)),
        "ticker_ranking": reader.ticker_ranking_with_benchmark(run_id),
    }
    return TEMPLATES.TemplateResponse(request, "insights.html", ctx)


@app.get("/runs/{run_id}/trades/export.csv")
def run_trades_export(
    run_id: int,
    ticker: str | None = None,
    year: str | None = None,
    outcome: str | None = None,
    exit_reason: str | None = None,
):
    run = reader.get_run(run_id)
    if not run:
        return PlainTextResponse("run not found", status_code=404)
    year_i = int(year) if year else None
    rows = reader.list_trades(
        run_id, ticker=ticker or None, year=year_i,
        outcome=outcome or None, exit_reason=exit_reason or None,
    )
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="trades_run{run_id}.csv"'},
    )


@app.get("/trades/{trade_id}", response_class=HTMLResponse)
def trade_detail(request: Request, trade_id: int):
    trade = reader.get_trade(trade_id)
    if not trade:
        return PlainTextResponse("trade not found", status_code=404)
    run = reader.get_run(trade["run_id"])
    snapshots = reader.trade_snapshots(trade_id)
    tags = reader.trade_tags(trade_id)
    ctx = {
        "run": run,
        "trade": trade,
        "entry": snapshots.get("entry"),
        "exit": snapshots.get("exit"),
        "tags": tags,
    }
    return TEMPLATES.TemplateResponse(request, "trade_detail.html", ctx)


@app.get("/api/trades/{trade_id}/chart")
def trade_chart(trade_id: int, window: int = 40):
    trade = reader.get_trade(trade_id)
    if not trade:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        df = load_one(trade["ticker"])
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)

    entry = pd.Timestamp(trade["entry_date"])
    exit_ = pd.Timestamp(trade["exit_date"]) if trade["exit_date"] else df.index[-1]
    lo = entry - pd.Timedelta(days=window)
    hi = exit_ + pd.Timedelta(days=window)
    sl = df.loc[(df.index >= lo) & (df.index <= hi)].copy()
    sl["mm50"] = sma(sl["close"], 50)
    sl["mm200"] = sma(sl["close"], 200)

    return JSONResponse({
        "ticker": trade["ticker"],
        "entry_date": trade["entry_date"],
        "exit_date": trade["exit_date"],
        "entry_price": trade["entry_price"],
        "exit_price": trade["exit_price"],
        "dates": [d.strftime("%Y-%m-%d") for d in sl.index],
        "open":   [None if pd.isna(v) else float(v) for v in sl["open"]],
        "high":   [None if pd.isna(v) else float(v) for v in sl["high"]],
        "low":    [None if pd.isna(v) else float(v) for v in sl["low"]],
        "close":  [None if pd.isna(v) else float(v) for v in sl["close"]],
        "mm50":   [None if pd.isna(v) else float(v) for v in sl["mm50"]],
        "mm200":  [None if pd.isna(v) else float(v) for v in sl["mm200"]],
    })


@app.get("/api/runs")
def api_runs():
    return JSONResponse(reader.list_runs())


# ============ OPERAÇÃO · HISTÓRICO =======================================

@app.get("/operacao/historico", response_class=HTMLResponse)
def operacao_historico(request: Request):
    """Retrospecto da conta de operação: curva de patrimônio + toda intenção
    já decidida + saques já executados. Só leitura, mesma disciplina de
    `/operacao` — nunca cria a conta."""
    from journal import live_store

    with live_store.live_journal() as conn:
        account = live_store.load_account(conn, live_service.ACCOUNT_NAME)
        if account is None:
            ctx = {"existe": False}
        else:
            ctx = {
                "existe": True,
                "conta": account.name,
                "capital_inicial": account.initial_capital,
                "equity_json": json.dumps(live_store.equity_series(conn, account.id)),
                "intents": live_store.all_intents(conn, account.id, limit=200),
                "withdrawals": live_store.withdrawals(conn, account.id),
            }
    return TEMPLATES.TemplateResponse(request, "historico.html", ctx)
