from __future__ import annotations

import asyncio
import csv
import io
import json
import queue
import time
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

# Código de motivo (`Intent.reason`) -> frase de leitura humana. Mora aqui, na
# camada de APRESENTAÇÃO, e não em `core/`: o código curto é o dado de
# auditoria (estável, consultável, portável pro MQL5), a frase é enfeite de
# tela e pode mudar sem migração. A tabela mostra os DOIS — a frase para ler
# rápido, o código para conferir contra o diário.
#
# Entradas vêm de `Enter.reason` (`strategy/`), saídas de `ExitReason`, saque
# de `WithdrawalPolicy.label`. Motivo desconhecido cai no próprio código, sem
# inventar tradução: um robô novo aparece como o código dele até alguém
# escrever a frase, o que é honesto e não esconde nada.
_MOTIVO_LEGIVEL = {
    # entradas
    "dip_rank":            "topo do ranking de momentum, comprado numa queda",
    "dip_rank1":           "melhor momentum da lista, comprado numa queda",
    "dip_rank1_rotation":  "assumiu o lugar da posição anterior (rotação)",
    # saídas
    "cross_down":          "média curta cruzou para baixo",
    "stop":                "stop atingido",
    "trail_stop":          "stop móvel atingido",
    "ibov_defensive":      "defesa: IBOV abaixo da média longa",
    "defensive_absolute_mom": "defesa: momentum absoluto negativo",
    "rotation_out":        "saiu do topo do ranking (rotação)",
    "mean_reversion_done": "reversão à média concluída",
    "target_mid_band":     "alvo na banda média",
    "withdrawal":          "posição zerada para levantar caixa de saque",
    "manual":              "decisão manual",
    # saque (label da política em vigor, ver `backtest/withdrawal.py`)
    "floor_skim":          "saque mensal sobre o excedente acima do piso",
}


def motivo_legivel(reason: str) -> str:
    """Frase para o motivo, ou o próprio código quando não há tradução."""
    return _MOTIVO_LEGIVEL.get(reason or "", reason or "")


TEMPLATES.env.filters["motivo_legivel"] = motivo_legivel


# `{:,.2f}` do Python produz "1,234.56" (padrão en-US) e o resto dos templates
# corrige isso com `.replace(",", ".")` — que só funciona para valores SEM
# decimal: em "1,234.56" o replace produz "1.234.56", com dois pontos. A troca
# tem de ser SIMULTÂNEA, e é o que `str.translate` faz (o `.` não é reprocessado
# depois de virar `,`).
_SEPARADORES_BR = str.maketrans({",": ".", ".": ","})


def num_br(valor, casas: int | None = 2) -> str:
    """Número no formato brasileiro: 1.234,56. `casas=None` corta zeros à
    direita (para campo de gatilho, onde a precisão varia por robô).

    Devolve "—" para `None` e o próprio valor em texto para o que não for
    número: o payload de gatilho é dict livre da estratégia e pode trazer
    string (`rotated_from`) no meio dos números.
    """
    if valor is None:
        return "—"
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if casas is None:
        txt = f"{f:,.6f}".rstrip("0").rstrip(".")
    else:
        txt = f"{f:,.{casas}f}"
    return txt.translate(_SEPARADORES_BR)


TEMPLATES.env.filters["num_br"] = num_br


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
    virar helper).

    Correção pós-code-review (item 5, hipótese-agente): `live_service.
    get_status()` pode levantar `journal.live_store.LegacyPaperAccountError`
    (conta legada `mode='paper'` bloqueando o rebuild do vocabulário) — sem
    capturar isso aqui, ela subia crua até o handler e virava um 500 em
    `/operacao`. Captura ESPECIFICAMENTE essa exceção (não `Exception`
    genérico) e degrada para o estado "sem conta" com a mensagem real no
    banner de erro, em vez de estourar. `LegacyManualAccountError` (modo
    manual descontinuado) é a mesma situação por um motivo diferente —
    mesmo tratamento."""
    from journal import live_store

    try:
        status_payload = live_service.get_status()
    except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError) as e:
        status_payload = {"conta": live_service.ACCOUNT_NAME, "existe": False}
        extra.setdefault("erro", str(e))
    # `top3` só importa pro form de conta NOVA (o select "Robô") -- consulta
    # o diário de backtests (`journal.reader`, banco SEPARADO do live) só
    # quando ainda não há conta, pra não bater nele a cada poll HTMX de
    # 20s em 20s (`/operacao/fragment`) sobre uma conta já em operação.
    top3 = ([] if status_payload.get("existe")
            else reader.top_strategies_by_final_capital(top_n=3, run_kind="champion_full"))
    return {
        "status": status_payload,
        "proc": live_control.status(),
        "config_anterior": live_control.last_config(),
        "creds": live_control.display_credentials(),
        "creds_status": live_control.credential_status(),
        "poll_seconds": _operacao_poll_seconds(),
        "top3": top3,
        **extra,
    }


@app.get("/operacao", response_class=HTMLResponse)
def operacao(request: Request):
    ctx = _operacao_ctx(page="operacao")
    return TEMPLATES.TemplateResponse(request, "operacao.html", ctx)


@app.get("/operacao/fragment", response_class=HTMLResponse)
def operacao_fragment(request: Request):
    """Fragmento que o polling HTMX troca (ver `hx-trigger` em
    `operacao_live_panel.html`) -- só o painel operacional (status,
    capital, posições, eventos), NUNCA credenciais nem o form de conta
    nova. Achado ao vivo: quando esse polling trocava o `#ops-body`
    inteiro, qualquer <details> aberto (credenciais, opções avançadas)
    fechava sozinho a cada refresh de fundo, porque o servidor sempre
    renderiza fechado e `outerHTML` recria o nó do zero -- credencial e
    setup inicial são configuração do usuário, não dado que o robô gera,
    então saíram do escopo do poll (ver `operacao_body.html`).
    Se a conta ainda não existe (poll que sobrou de uma aba antiga,
    por exemplo), cai pro corpo inteiro -- o painel ao vivo pressupõe
    conta."""
    ctx = _operacao_ctx()
    template = (
        "partials/operacao_live_panel.html" if ctx["status"].get("existe")
        else "partials/operacao_body.html"
    )
    return TEMPLATES.TemplateResponse(request, template, ctx)


@app.post("/operacao/iniciar", response_class=HTMLResponse)
async def operacao_iniciar(request: Request):
    """Um clique cria a conta (se preciso) e sobe o supervisor como processo
    próprio — o mesmo que `scripts/run_live.py init` + `loop` fariam na mão.
    Mode/capital só vêm do form na PRIMEIRA vez (conta ainda não existe);
    depois disso a conta já fixou os dois e não são mais editáveis por aqui."""
    form = await request.form()
    from journal import live_store

    try:
        with live_store.live_journal() as conn:
            conta = live_store.load_account(conn, live_service.ACCOUNT_NAME)
    except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError) as e:
        # Correção pós-code-review (item 5): renderiza a mensagem no banner
        # de erro em vez de deixar a exceção subir crua até virar 500.
        ctx = _operacao_ctx(erro=str(e))
        return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", ctx)

    erro = None
    # "Ações por lote" é parâmetro do TERMINAL MT5 do usuário, não da
    # estratégia nem da sessão -- detectado sozinho a cada clique em
    # "Iniciar operação" via `detect_shares_per_lot()` (consulta o
    # symbol_info do terminal MT5 já conectado), nunca digitado pelo
    # usuário (decisão do dono, 2026-08-20; substitui o campo manual em
    # Acesso e credenciais, que por sua vez substituiu o workaround ainda
    # mais antigo que reexibia o campo no form de retomada).
    mt5_shares_per_lot = live_control.detect_shares_per_lot()
    if mt5_shares_per_lot is None or mt5_shares_per_lot <= 0:
        erro = (
            "Não foi possível detectar 'ações por lote' automaticamente — "
            "confirme que o terminal MetaTrader 5 está aberto e logado nesta "
            "máquina (ou que login/senha/servidor MT5 foram salvos em 'Acesso "
            "e credenciais') e que os papéis da watchlist têm o mesmo "
            "contract_size no seu terminal."
        )

    if erro is None and conta is not None:
        # conta já existe: modo/capital/robô são da conta, NUNCA do form --
        # evita subir o loop com um broker que não bate com o que a conta
        # espera, e evita a conta trocar de robô sozinha só porque o
        # ranking automático mudou depois da criação (decisão do dono,
        # 2026-08-19: "nada automático" na troca de robô).
        mode, capital, strategy_key = conta.mode, conta.initial_capital, conta.investment_robot
    elif erro is None:
        # Primeira conta: o robô vem do TOP-3 do ranking automático (janela
        # FULL) mostrado no form -- nunca uma chave arbitrária, mesmo que o
        # form venha adulterado/desatualizado (mesmo espírito de floor/
        # disjuntor, ver teste `..._ignora_piso_e_disjuntor_arbitrarios...`).
        mode = "mt5"
        top3 = reader.top_strategies_by_final_capital(top_n=3, run_kind="champion_full")
        valid_keys = {c["strategy_name"] for c in top3}
        strategy_key = form.get("robo")
        if not valid_keys:
            erro = (
                "O ranking automático ainda não tem nenhum robô qualificado "
                "para operar -- aguarde o próximo recálculo (a cada 6h) antes "
                "de iniciar."
            )
        elif strategy_key not in valid_keys:
            erro = "Escolha um robô da lista antes de iniciar."
        else:
            # Capital nunca é digitado -- é o saldo real da corretora (ver
            # `live_control.detect_broker_capital()`). Só consulta a
            # corretora depois das outras validações passarem, pra não
            # gastar uma tentativa de conexão MT5 num form incompleto.
            capital = live_control.detect_broker_capital()
            if capital is None:
                erro = (
                    "Não foi possível ler o saldo disponível na sua conta MetaTrader 5 — "
                    "confirme que o terminal MT5 está aberto e logado nesta máquina, ou "
                    "que o login/senha/servidor MT5 foram salvos em 'Acesso e credenciais', "
                    "e tente novamente."
                )

    if erro is None:
        try:
            cfg = live_control.ProcessConfig(
                mode=mode, capital=capital, strategy=strategy_key,
                notify_min_level=form.get("notify_min_level") or "warn",
                mt5_shares_per_lot=mt5_shares_per_lot,
            )
            # Correção pós-code-review (item 7): `live_control.start()` faz
            # `time.sleep(_STARTUP_GRACE_SECONDS)` de forma SÍNCRONA (prova
            # de vida do processo) — chamado direto dentro deste handler
            # `async def`, isso travava o event loop inteiro (todas as
            # outras rotas/polls do dashboard) por ~2s a cada clique em
            # "Iniciar". `asyncio.to_thread` roda a chamada bloqueante numa
            # thread separada, sem travar o loop.
            await asyncio.to_thread(live_control.start, cfg)
        except (RuntimeError, ValueError) as e:
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

    try:
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
                    # `intent_id` -> contexto de mercado da decisão, numa query
                    # só (ver `live_store.intent_snapshots`) em vez de uma por
                    # linha da tabela.
                    "snapshots": live_store.intent_snapshots(conn, account.id, limit=400),
                    "withdrawals": live_store.withdrawals(conn, account.id),
                }
    except live_store.LegacyPaperAccountError as e:
        # Correção pós-code-review (item 5): mensagem amigável em vez de 500
        # cru — este endpoint só lê, não tem template com banner de erro
        # próprio, então devolve texto simples em vez de estourar.
        return PlainTextResponse(str(e), status_code=200)
    return TEMPLATES.TemplateResponse(request, "historico.html", ctx)
