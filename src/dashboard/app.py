from __future__ import annotations

import asyncio
import csv
import io
import json
import queue
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from core.config import BENCHMARK, WATCHLIST
from core.indicators import sma
from dashboard import live_control, live_service, robot_view, simulate as sim_mgr
from journal import reader
from live import clock
from market_data.download import download_macro
from market_data.loader import load_one
from scheduler import (
    CHAMPION_CAPITAL,
    CHAMPION_FRACTIONAL_FEE,
    refresh_champion_rankings,
    refresh_market_data,
)
from strategy import registry as strategy_registry
from strategy.registry import candidate_keys, get_strategy, list_strategies

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
# Uma frase da ficha técnica do robô virando HTML: escapa tudo e traduz
# `crase` em <code>. Filtro (e não `|safe` num texto já montado em Python)
# porque assim o template nunca recebe HTML cru de lugar nenhum — o escape
# acontece no último passo, onde é auditável. Ver `strategy/registry.py`.
# `Markup` no dashboard, não em `strategy/`: o `<code>` já sai escapado de
# `inline_html`, e é aqui (camada de apresentação) que se declara "este HTML
# pode passar". Sem o wrapper, o autoescape do Jinja mostrava `&lt;code&gt;`
# literal na tela.
TEMPLATES.env.filters["inline_code"] = lambda t: Markup(strategy_registry.inline_html(t or ""))


def _static_v(filename: str) -> int:
    """Mtime do arquivo estático, usado como query-string cache-buster.

    Sem isso, o navegador pode servir uma versão antiga de pages.css do cache
    depois de uma edição — o HTML (nunca cacheado) mostra a estrutura nova mas
    o estilo fica o velho, um bug confuso de diagnosticar. Muda sozinho a cada
    edição do arquivo, sem precisar lembrar de bump manual.

    A pasta sai da EXTENSÃO (`.js` → `static/js/`, resto → `static/css/`) para
    os chamadores continuarem passando só o nome. Antes só resolvia CSS, e um
    `.js` caía no `except` devolvendo 0 — cache-buster constante, ou seja,
    nenhum: exatamente o bug que esta função existe para evitar.
    """
    sub = "js" if filename.endswith(".js") else "css"
    try:
        return int((BASE_DIR / "static" / sub / filename).stat().st_mtime)
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
    top3_full = reader.top_strategies_by_final_capital(
                top_n=3, run_kind="champion_full", only=candidate_keys())
    top3_5y = reader.top_strategies_by_final_capital(
        top_n=3, run_kind="champion_5y", only=candidate_keys())
    top3_1y = reader.top_strategies_by_final_capital(
        top_n=3, run_kind="champion_1y", only=candidate_keys())
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
    # CATÁLOGO ÚNICO — swing e day trade no mesmo formato de cartão (ver
    # `dashboard/robot_view.py`). Robô de day trade não entra no discovery de
    # swing (motor/timeframe incomparável ao ranking FULL/5Y/1Y) e por isso
    # não disputa o pódio acima; o que ele NÃO precisava era de uma segunda
    # seção com outra anatomia de cartão, que foi como ele entrou na home
    # primeiro.
    robots = robot_view.catalog(candidate_keys())
    ctx = {
        "robots": robots,
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
        # Capital e taxa do critério oficial vêm do `scheduler`, não escritos
        # à mão no template: a tela dizia "R$ 1.000" muito depois de o
        # ranking ter mudado de capital seria mentira difícil de notar.
        "ranking_capital": CHAMPION_CAPITAL,
        "ranking_fee": CHAMPION_FRACTIONAL_FEE,
        # Filtro "Robô" na tabela: todo robô conhecido pelo registry.
        "run_strategies": [s.key for s in all_strategies],
        "run_tickers": reader.distinct_run_tickers(),
        "has_more": len(runs) == RUNS_PAGE_SIZE,
        "next_offset": RUNS_PAGE_SIZE,
        "filters": {"strategy": "", "start_from": "", "end_to": "", "capital_min": "", "capital_max": "", "ticker": ""},
        "page": "robots",
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


_JANELAS_RANKING = (
    ("1 ano", "champion_1y"),
    ("5 anos", "champion_5y"),
    ("Período completo", "champion_full"),
)


def _medicoes_do_robo(key: str) -> list[dict]:
    """A última run OFICIAL deste robô em cada janela do ranking.

    Mesma fonte do pódio da home (`journal.reader`), não um número reescrito
    aqui: a ficha do robô mostrando um capital final diferente do pódio seria
    a mesma medição contada de dois jeitos. Sem `only=` de propósito — a ficha
    de um robô APOSENTADO também deve mostrar o que ele mediu enquanto
    competia; quem filtra candidato é o pódio, não o histórico.
    """
    medicoes = []
    for rotulo, run_kind in _JANELAS_RANKING:
        linhas = reader.top_strategies_by_final_capital(
            top_n=1, run_kind=run_kind, only=[key], include_disqualified=True)
        if linhas:
            medicoes.append({"janela": rotulo, **linhas[0]})
    return medicoes


@app.get("/strategies/{key}", response_class=HTMLResponse)
def strategy_detail(request: Request, key: str):
    """Ficha de UM robô — de swing OU de day trade.

    Até 2026-08-21 esta rota só resolvia o registry de swing, então
    `/strategies/gremah` era 404 e o cartão de day trade da home tinha de
    apontar para `/operacao`: clicar em dois robôs na mesma grade levava a
    dois lugares diferentes. `robot_view.detail()` resolve os dois catálogos e
    devolve a MESMA ficha, com `can_simulate` dizendo se o formulário de
    simulação de carteira faz sentido para aquele motor.
    """
    robot = robot_view.detail(key, candidate_keys())
    if robot is None:
        return PlainTextResponse("Robô não encontrado.", status_code=404)
    runs = reader.list_runs(strategy=key, limit=RUNS_PAGE_SIZE, offset=0)
    ctx = {
        "robot": robot,
        "medicoes": _medicoes_do_robo(key),
        "watchlist": list(WATCHLIST),
        "default_start": "2015-01-01",
        "default_end": _latest_available_date(),
        # Mesmo capital do ranking, para o formulário de simulação não
        # sugerir um regime que o dono não consegue executar.
        "default_capital": int(CHAMPION_CAPITAL),
        "ranking_capital": CHAMPION_CAPITAL,
        "ranking_fee": CHAMPION_FRACTIONAL_FEE,
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
OPERACAO_POLL_IDLE_CAP_SECONDS = 3600  # teto fora da janela (1h, pedido do dono 2026-08-25) — nunca fica cego


def _operacao_poll_seconds() -> int:
    """Intervalo do polling HTMX de `/operacao`: 20s dentro da janela ativa
    de pregão (ver `live.clock`), teto de 1h fora dela — sem sentido
    recarregar a tela a cada 20s de madrugada ou no fim de semana, quando
    nada no status muda. Perto da janela abrir, o intervalo encolhe sozinho
    (é o próprio `seconds_until_active_window`), então a tela volta a
    atualizar rápido bem no instante em que o pregão abre, sem precisar dar
    F5 na mão."""
    if clock.in_active_window():
        return OPERACAO_POLL_ACTIVE_SECONDS
    return min(int(clock.seconds_until_active_window()) + 1, OPERACAO_POLL_IDLE_CAP_SECONDS)


#: Quantas linhas de posição um cartão mostra antes do "ver mais". Eventos
#: não usam mais um limite NUMÉRICO como este: o console de eventos sempre
#: mostra o pregão inteiro (ver `IntradayLiveRuntime.status`/`LiveRuntime.
#: status`) e rola por dentro (`.console` em pages.css) em vez de paginar —
#: o botão "Diário Completo"/"Diário do dia" troca esse filtro por um
#: booleano (`eventos_full`), não por um teto crescente feito este. Mesmo número da
#: lista de simulações da home, de propósito — é o mesmo gesto na mesma
#: aplicação.
OPS_PAGINA = 10
#: Teto do "ver mais" de posições. A URL do fragmento é pública e digitável;
#: sem teto, `?posicoes=99999999` mandaria montar em memória uma lista que o
#: cartão nunca exibiria — e o polling repetiria isso a cada 20 segundos.
OPS_PAGINA_MAX = 500

#: Primeira página do "Diário Completo" (histórico inteiro da conta, não só
#: hoje) e tamanho de cada página SEGUINTE, carregada por scroll infinito
#: (pedido do dono, 2026-08-25: o clique estava lento carregando até 1000
#: linhas de uma vez só). Ver `operacao_eventos_mais_antigos` e o sentinela
#: `hx-trigger="revealed"` em `operacao_slot_live.html`.
OPS_EVENTOS_PAGINA_INICIAL = 30
OPS_EVENTOS_PAGINA_SEGUINTE = 10


def _slot_ctx(slot, posicoes_limit: int = OPS_PAGINA, eventos_full: bool = False) -> dict:
    """Tudo o que UM cartão de slot precisa: status da conta, processo,
    caixa do ledger manual e se o botão "Iniciar" pode estar habilitado.

    Correção pós-code-review (item 5, hipótese-agente): `live_service.
    get_status()` pode levantar `journal.live_store.LegacyPaperAccountError`
    (conta legada `mode='paper'` bloqueando o rebuild do vocabulário) — sem
    capturar isso aqui, ela subia crua até o handler e virava um 500 em
    `/operacao`. Captura ESPECIFICAMENTE essa exceção (não `Exception`
    genérico) e degrada para o estado "sem conta" com a mensagem real no
    banner de erro, em vez de estourar. `LegacyManualAccountError` (modo
    manual descontinuado) é a mesma situação por um motivo diferente —
    mesmo tratamento.

    `KeyError` entra pelo mesmo motivo: uma conta cujo `investment_robot`
    gravado não existe mais no registry (robô removido do catálogo, ou linha
    corrompida) não pode virar 500 — degrada com a mensagem do próprio
    `KeyError` (ver `strategy.daytrade.registry.get_daytrade_robot`/
    `strategy.registry.get_strategy`, os dois levantam `KeyError` com o
    motivo em texto).

    O modo (sombra/real) é fixo desde a criação do slot (`slot.
    execution_mode`, 2026-08-24) — não é mais escolhido num `<select>` do
    form de iniciar, então não há eco de escolha-ainda-não-salva pra
    carregar aqui (havia um `exec_mode_override` antes desta data, removido
    junto do select).

    `eventos_full` é o botão "Diário Completo"/"Diário do dia" do cartão de
    eventos: troca nos dois sentidos entre o filtro padrão (só o pregão
    atual) e TODO o histórico da conta. Vem da URL do fragmento, mesmo
    motivo de `posicoes_limit` (ver docstring de `operacao_fragment`). Ligado,
    a PRIMEIRA página vem daqui (`OPS_EVENTOS_PAGINA_INICIAL`) e o resto do
    histórico é scroll infinito (`operacao_eventos_mais_antigos`) — por isso
    o poll de fundo deste cartão fica PAUSADO enquanto `eventos_full` está
    ligado (ver `frag_url`/`hx-trigger` condicional em
    `operacao_slot_live.html`): sem pausar, o refresh a cada 20s recriaria o
    nó inteiro e resetaria de volta pra página inicial o que o dono já tinha
    rolado pra baixo."""
    from journal import live_store

    erro = None
    try:
        status_payload = live_service.get_status(
            slot.id, full=eventos_full,
            limit=OPS_EVENTOS_PAGINA_INICIAL if eventos_full else 1000,
        )
    except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError) as e:
        status_payload = {"conta": slot.id, "existe": False, "kind": slot.kind}
        erro = str(e)
    except KeyError as e:
        status_payload = {"conta": slot.id, "existe": False, "kind": slot.kind}
        erro = str(e)
    # Sentinela do scroll infinito só faz sentido se a página VEIO CHEIA --
    # menos que isso e' o fim do historico (nao ha mais nada mais antigo pra
    # buscar), mesmo criterio que `operacao_eventos_mais_antigos` usa pra
    # decidir se emite a proxima sentinela.
    if eventos_full:
        status_payload["eventos_mais"] = (
            len(status_payload.get("eventos") or []) == OPS_EVENTOS_PAGINA_INICIAL
        )
    config_anterior = live_control.last_config(slot.id)
    # Swing nunca teve modo sombra; day trade sempre tem (fixo no slot).
    execution_mode = slot.execution_mode if slot.is_intraday else "live"
    caixa = live_control.available_cash(slot.id, execution_mode) or 0.0
    proc = live_control.status(slot.id)
    # Robô que vai de fato rodar: o da conta já existente, ou o default
    # sugerido pra conta nova (o mesmo pré-selecionado no `<select>` do
    # template) — `min_cash_for` usa isso pra achar o piso de caixa DESTE
    # robô, não um número cego ao símbolo (ver docstring de `min_cash_for`).
    robo_previsto = status_payload.get("robo_investimento") or None
    piso = live_control.min_cash_for(slot, robo_previsto)
    # Posições cortadas AQUI (e não no SQL como os eventos): elas vêm da conta
    # já carregada em memória e são poucas por construção — o teto de posições
    # do robô. O corte existe para o cartão ter um comportamento só, não
    # porque a lista fosse grande.
    posicoes = status_payload.get("posicoes") or []
    status_payload["posicoes_total"] = len(posicoes)
    status_payload["posicoes_ha_mais"] = len(posicoes) > posicoes_limit
    status_payload["posicoes"] = posicoes[:posicoes_limit]
    return {
        "slot": slot,
        "status": status_payload,
        "proc": proc,
        "posicoes_limit": posicoes_limit,
        "eventos_full": eventos_full,
        "config_anterior": config_anterior,
        "caixa_ledger": caixa,
        "caixa_minima": piso,
        "caixa_ok": caixa >= piso,
        "erro_slot": erro,
    }


def _robot_options(slot, bloco: dict) -> list[dict]:
    """Opções do select "Robô" do form de conta NOVA deste slot — vazio se a
    conta já existe (o robô dela já está fixado, ver `operacao_iniciar`).

    Só o SWING usa isto hoje: TOP-3 do ranking automático (janela FULL) —
    pódio recalculado a cada 6h, PODE ficar vazio (ver `operacao_iniciar`).
    Restringir a consulta a este caso (conta nova) não é micro-otimização:
    sem isso, cada cartão de day trade dispararia uma consulta ao banco de
    BACKTESTS (`journal.reader`, arquivo separado do live) a cada poll de
    20s, por um número que ele nem mostra.

    Day trade não passa mais por aqui: desde 2026-08-22 a escolha do robô e
    do ativo acontece ANTES da conta existir, no formulário "novo robô" (ver
    `_novo_robo_ctx`) — quando o cartão aparece, o par robô+ativo dele já
    está decidido e é o próprio id do slot."""
    if bloco["status"].get("existe") or slot.is_intraday:
        return []
    top3 = reader.top_strategies_by_final_capital(
        top_n=3, run_kind="champion_full", only=candidate_keys())
    # Sem o capital final na label: a POSIÇÃO na lista (ordenada pelo
    # ranking) já mostra qual é o melhor — repetir o número aqui era
    # redundante e envelhecia entre um refresh do scheduler e outro.
    return [{"value": c["strategy_name"], "label": c["strategy_name"]} for c in top3]


def _novo_robo_ctx(conn) -> dict:
    """O formulário "novo robô de day trade": que robôs existem e, para cada
    um, que ativos ele aceita — ordenados por CAPITAL MÍNIMO (o mais barato
    primeiro), com a marca de quem já está alocado.

    A ordem é por capital mínimo porque é a primeira pergunta de quem escolhe
    ("qual cabe no que eu tenho?"), e não a ordem de medição do robô. Ativo
    sem preço salvo vai para o fim: sem preço não dá para dizer quanto exige,
    e fingir R$0 o colocaria em primeiro lugar — o pior lugar possível para
    uma informação ausente.

    `em_uso` é o que o painel desenha como bolinha verde/anel — e é POR ROBÔ,
    não por símbolo sozinho (pedido do dono, 2026-08-24): se `gremah` já
    opera PMAM3, isso marca a opção "gremah · PMAM3" (evita recriar o mesmo
    cartão à toa), mas NÃO marca "gremah_tick · PMAM3" — dois robôs
    DIFERENTES no mesmo ativo é uma comparação válida (ambos em sombra, por
    exemplo) e só vira problema se os dois tentarem operar dinheiro de
    verdade ao mesmo tempo, o que é checado (e bloqueado, com o motivo
    específico) em `live_control._assert_slots_disjuntos` na hora de
    Iniciar — não aqui, onde bloquear cedo demais escondia uma combinação
    que podia ser perfeitamente segura.

    `modos_usados` é o que falta para o MODO não repetir: o índice é
    agrupado por (robô, ativo, modo) — antes disto era só por `symbol`, que
    colapsava dois slots do mesmo ativo (sombra e real, ou dois robôs
    diferentes) num só e podia deixar `em_uso` apagado justamente para o
    slot que ficou de fora da colisão, deixando o painel oferecer "Criar" num
    par (robô, ativo, modo) que já existe e que `operacao_novo_robo` só ia
    recusar depois do clique.
    """
    from dashboard import slots as slots_mod
    from dashboard.robot_view import _ultimo_preco
    from strategy.daytrade.base import capital_minimo_brl
    from strategy.daytrade.registry import list_daytrade_robots, symbols_for_robot

    slots_por_robo_ativo: dict[tuple[str, str], dict[str, object]] = {}
    for slot in slots_mod.daytrade_slots(conn):
        if not slot.symbol:
            continue
        slots_por_robo_ativo.setdefault((slot.robot_key, slot.symbol), {})[slot.execution_mode] = slot

    todos_slot_ids = [s.id for modos in slots_por_robo_ativo.values() for s in modos.values()]
    rodando = live_control.status_all(todos_slot_ids)
    robos = []
    for info in list_daytrade_robots():
        ativos = []
        for symbol in symbols_for_robot(info.key):
            preco, data = _ultimo_preco(symbol)
            minimo = capital_minimo_brl(preco) if preco else None
            modos = slots_por_robo_ativo.get((info.key, symbol), {})
            modos_usados = sorted(modos)
            algum_slot = next(iter(modos.values()), None)
            ativos.append({
                "symbol": symbol,
                "preco": preco,
                "preco_data": data,
                "minimo": minimo,
                "em_uso": bool(modos_usados),
                "modos_usados": modos_usados,
                # Por MODO, não por par -- é o que permite o rótulo do
                # `<option>` mudar em cima do hora (`static/js/operacao.js`,
                # `atualizaAtivos`) conforme o dono troca o Modo: o
                # mesmo PMAM3 mostra "parado" quando Simulação está
                # selecionado (o slot sombra existe e está parado) e "○ sem
                # aviso nenhum" quando troca pra Real (aquele trio ainda nem
                # existe) -- ver o pedido do dono de 2026-08-25.
                "modos_rodando": sorted(m for m, s in modos.items() if rodando.get(s.id)),
                "slot_id": algum_slot.id if algum_slot else None,
                "rodando": any(rodando.get(s.id) for s in modos.values()),
            })
        ativos.sort(key=lambda a: (a["minimo"] is None, a["minimo"] or 0.0))
        # `rank` e `feed_kind` vêm do registry (ver o comentário sobre
        # `_ROBOTS` lá): a ordem da lista JÁ é o pódio, mas ordem sozinha não
        # se lê como recomendação dentro de um `<select>` de dois itens — o
        # rótulo é o que diz qual é o TOP-1. `feed_kind` distingue dois robôs
        # do mesmo desenho pela única coisa que os separa.
        robos.append({"key": info.key, "label": info.key, "rank": info.rank,
                      "feed_kind": info.feed_kind,
                      "description": info.description, "ativos": ativos})
    return {"robos": robos, "livres": sum(
        1 for r in robos for a in r["ativos"] if not a["em_uso"])}


def _operacao_ctx(**extra) -> dict:
    """Contexto comum a toda rota que renderiza `operacao.html`/
    `operacao_body.html`: um bloco por slot existente (day trade em cima),
    o formulário de robô novo, os avisos de capital, e o que é global
    (credenciais, poll)."""
    from core.config import ordered_slots
    from dashboard import slots as slots_mod
    from journal import live_store

    # Uma conexão só para as três leituras que dependem do banco. O `try`
    # existe porque `live_journal()` roda `ensure_tables`, que RECUSA um banco
    # com conta legada (`mode='paper'`/`'manual'`) — e essa recusa chegava aqui
    # antes de `_slot_ctx`, que já sabia degradar, ter chance de rodar: a
    # página inteira virava 500 justamente quando o dono precisa dela para ler
    # a mensagem que explica como consertar o banco.
    try:
        with live_store.live_journal() as conn:
            todos = slots_mod.all_slots(conn)
            novo_robo = _novo_robo_ctx(conn)
            avisos = live_store.capital_signals(conn)
    except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError) as e:
        extra.setdefault("erro", str(e))
        todos = list(ordered_slots())
        novo_robo = {"robos": [], "livres": 0}
        avisos = []

    slots = [_slot_ctx(s) for s in todos]
    for bloco in slots:
        if bloco["erro_slot"]:
            extra.setdefault("erro", bloco["erro_slot"])
        bloco["robot_options"] = _robot_options(bloco["slot"], bloco)
    return {
        "slots": slots,
        "novo_robo": novo_robo,
        "avisos": avisos,
        "avisos_pendentes": sum(1 for a in avisos if not a["acknowledged_at"]),
        "creds": live_control.display_credentials(),
        "creds_status": live_control.credential_status(),
        "poll_seconds": _operacao_poll_seconds(),
        **extra,
    }


def _valor_brl(texto) -> float | None:
    """Lê um valor em reais no formato brasileiro. `None` se não for número.

    O campo de caixa é `type="text"` com máscara de moeda (o `type="number"`
    deixava digitar `0,0444410` para só então acusar — ver o template), então
    o que chega aqui é "1.234,56". O `float(x.replace(",", "."))` de antes
    quebrava justamente nesse formato: virava "1.234.56".

    Regras, nesta ordem:
      * tem vírgula  -> ela é o decimal, e os pontos são milhar ("1.234,56");
      * só pontos, em grupos de 3 -> são milhar ("1.234" = mil duzentos e
        trinta e quatro), o caso de quem digita sem JS e sem centavos;
      * qualquer outro ponto -> é decimal ("1234.56", o formato canônico).

    O SINAL é lido antes da limpeza e reaplicado no fim. Não é detalhe: um
    "-5" que voltasse como `5.0` passaria pela guarda `valor < 0` do chamador
    e GRAVARIA cinco reais no caixa em vez de recusar a entrada.
    """
    bruto = str(texto).strip()
    negativo = bruto.startswith("-")
    limpo = re.sub(r"[^\d,.]", "", bruto)
    if not limpo:
        return None
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", limpo):
        limpo = limpo.replace(".", "")
    try:
        valor = float(limpo)
    except ValueError:
        return None
    return -valor if negativo else valor


def _slot_or_404(slot_id: str):
    from core.config import slot_by_id

    try:
        return slot_by_id(slot_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _recarrega_a_pagina() -> Response:
    """Resposta vazia que manda o HTMX recarregar a página inteira.

    Corpo nenhum: `HX-Refresh` dispara `location.reload()` e o que viesse
    junto seria descartado. Instância NOVA a cada chamada (e não uma
    constante de módulo) porque um `Response` é mutável — middleware que
    grave header ou cookie nele vazaria para as requisições seguintes.
    """
    return Response(status_code=200, headers={"HX-Refresh": "true"})


def _slot_sumiu(slot_id: str) -> bool:
    """A aba está pedindo um cartão de um robô que não existe mais?

    Passou a acontecer quando os slots viraram removíveis (2026-08-22), e por
    dois caminhos: o dono clica "Remover" numa janela com outra aberta, ou a
    conta some do banco por fora. Antes disso a lista de slots era fixa e o
    caso não existia.

    Sem tratamento o polling degrada de dois jeitos ruins, ambos silenciosos:
    id que nem parseia (um `daytrade` de antes desta versão) 404 a cada 20s
    para sempre, e id dinâmico cuja conta foi apagada continua respondendo 200
    com um cartão vazio. Nos dois o cartão CONGELA exibindo o último estado —
    inclusive "operando" — de um robô que não existe. Um painel que mente
    sobre dinheiro é pior que um painel que recarrega.

    Erro ao consultar (banco travado, conta legada) responde `False` de
    propósito: segue o caminho normal, que sabe degradar num banner. Mandar
    recarregar aqui arriscaria um laço de reload contra um banco doente.
    """
    from core.config import slot_by_id

    try:
        slot_by_id(slot_id)
    except KeyError:
        return True
    try:
        from dashboard.slots import all_slots

        return slot_id not in {s.id for s in all_slots()}
    except Exception:
        return False


@app.get("/operacao", response_class=HTMLResponse)
def operacao(request: Request):
    ctx = _operacao_ctx(page="operacao")
    return TEMPLATES.TemplateResponse(request, "operacao.html", ctx)


@app.get("/operacao/{slot_id}/fragment", response_class=HTMLResponse)
def operacao_fragment(request: Request, slot_id: str,
                      posicoes: int = OPS_PAGINA,
                      eventos_full: int = 0,
                      rodando: int | None = None):
    """Fragmento que o polling HTMX troca (ver `hx-trigger` em
    `operacao_slot_live.html`) -- só o painel operacional DESTE slot (status,
    capital, posições, eventos), NUNCA credenciais e nunca o form de caixa.

    Achado ao vivo: quando esse polling trocava o `#ops-body` inteiro,
    qualquer <details> aberto (credenciais, opções avançadas) fechava sozinho
    a cada refresh de fundo, porque o servidor sempre renderiza fechado e
    `outerHTML` recria o nó do zero. O form de caixa fica fora pelo mesmo
    motivo, agravado: um `<input>` sendo digitado seria apagado no meio da
    digitação. Credencial, caixa e setup inicial são configuração do usuário,
    não dado que o robô gera.

    Um poll por slot (não um poll global): cada cartão troca só o seu nó,
    então o refresh de um robô não recria o DOM do outro.

    `posicoes` é o "ver mais" da lista de posições (eventos não pagina mais —
    ver `OPS_PAGINA`). Vem na URL, e não num estado guardado no servidor, por
    causa do polling: o botão "ver mais" aponta para ESTA rota com o limite
    maior e troca o mesmo nó, e o nó novo já nasce com o `hx-get` do poll
    carregando o limite novo. Sem isso, o "ver mais" duraria até o refresh
    seguinte apagá-lo — que é o que aconteceria copiando o `hx-swap=
    "beforeend"` da lista de simulações da home, que não tem polling nenhum.

    `eventos_full` é o mesmo gesto para o cartão de eventos, nos dois
    sentidos: "Diário Completo" aponta para ESTA rota com `eventos_full=1`,
    "Diário do dia" com `eventos_full=0`, e o `frag_url` do nó novo carrega o
    valor escolhido adiante — senão o polling seguinte reverteria a escolha
    sozinho."""
    if _slot_sumiu(slot_id):
        return _recarrega_a_pagina()
    slot = _slot_or_404(slot_id)
    # Teto: a URL é digitável, e `?posicoes=999999999` faria montar em
    # memória uma lista que o cartão nunca vai mostrar.
    bloco = _slot_ctx(slot,
                      posicoes_limit=max(OPS_PAGINA, min(int(posicoes), OPS_PAGINA_MAX)),
                      eventos_full=bool(eventos_full))
    ctx = {
        **bloco,
        "poll_seconds": _operacao_poll_seconds(),
        # O painel usa isto para decidir se o botão "Iniciar" pode estar
        # habilitado — sem credencial MT5 salva não há como operar.
        "creds_status": live_control.credential_status(),
        "robot_options": _robot_options(slot, bloco),
        # Liga o swap fora-de-banda do resumo do cabeçalho: ele mora no
        # `<summary>`, FORA deste nó, e sem isso um cartão recolhido ficaria
        # dizendo "operando" depois de o robô parar. Falso no render inicial,
        # onde o resumo já é desenhado no lugar certo (duplicaria o id).
        "fragmento": True,
        # A barra de controle também vive fora deste nó, mas ao contrário do
        # resumo NÃO pode ser reemitida a cada poll: ela tem o `<select>` de
        # modo de execução, e trocá-la resetaria a escolha do dono no meio —
        # nas duas direções ("Real" virando "Sombra" e o inverso), as duas
        # perigosas. Então só sai quando o estado do processo mudou de fato
        # em relação ao que o navegador tem na tela, que é o que `rodando`
        # (posto pelo próprio nó anterior na URL do poll) informa.
        #
        # `None` = primeira carga do fragmento sem o parâmetro: nada a
        # corrigir, o navegador acabou de receber a barra pelo render inicial.
        "controle_mudou": rodando is not None and bool(rodando) != bool(bloco["proc"]),
    }
    return TEMPLATES.TemplateResponse(request, "partials/operacao_slot_live.html", ctx)


@app.get("/operacao/{slot_id}/eventos", response_class=HTMLResponse)
def operacao_eventos_mais_antigos(request: Request, slot_id: str, before_id: int):
    """Próxima página do scroll infinito do "Diário Completo" (ver o
    sentinela `hx-trigger="revealed"` em `operacao_slot_live.html` e
    `operacao_eventos_lote.html`) -- pega os `OPS_EVENTOS_PAGINA_SEGUINTE`
    eventos mais antigos que `before_id` e devolve o lote junto da PRÓXIMA
    sentinela (ou nenhuma, se acabou o histórico da conta).

    De propósito NÃO passa por `_slot_ctx`/`live_service.get_status()`: essa
    rota só existe pra ler mais log velho, então não há por que reconstruir o
    runtime inteiro (posições, feed, disjuntor...) a cada 10 linhas de
    scroll -- só a conta (pra achar `account_id`) e a fatia de eventos
    pedida."""
    from journal import live_store as store

    slot = _slot_or_404(slot_id)
    with store.live_journal() as conn:
        account = store.load_account(conn, slot.id)
        eventos = (
            store.recent_events(conn, account.id, limit=OPS_EVENTOS_PAGINA_SEGUINTE,
                                before_id=before_id)
            if account is not None else []
        )
    ctx = {"slot": slot, "eventos": eventos, "pagina": OPS_EVENTOS_PAGINA_SEGUINTE}
    return TEMPLATES.TemplateResponse(request, "partials/operacao_eventos_lote.html", ctx)


@app.post("/operacao/{slot_id}/iniciar", response_class=HTMLResponse)
async def operacao_iniciar(request: Request, slot_id: str):
    """Um clique cria a conta deste slot (se preciso) e sobe o supervisor como
    processo próprio — o mesmo que `scripts/run_live.py --slot X init` +
    `loop` fariam na mão. Capital/robô só vêm do form na PRIMEIRA vez (conta
    ainda não existe); depois disso a conta já os fixou e não são mais
    editáveis por aqui."""
    slot = _slot_or_404(slot_id)
    form = await request.form()
    from journal import live_store

    try:
        with live_store.live_journal() as conn:
            conta = live_store.load_account(conn, slot.id)
    except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError) as e:
        # Correção pós-code-review (item 5): renderiza a mensagem no banner
        # de erro em vez de deixar a exceção subir crua até virar 500.
        ctx = _operacao_ctx(erro=str(e))
        return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", ctx)

    erro = None
    # "Nunca começou" != "não existe": `POST /operacao/{slot}/caixa` cria a
    # linha contábil só para guardar o caixa digitado, com `investment_robot`
    # vazio de propósito -- quem escolhe o robô é este handler. Sem esta
    # distinção, informar o caixa antes de iniciar congelaria o robô do slot
    # e o ranking do swing nunca seria consultado.
    nunca_comecou = conta is None or not conta.investment_robot
    capital = conta.initial_capital if not nunca_comecou else 0.0
    strategy_key = None

    # Robô ANTES da detecção de "ações por lote" abaixo: ela precisa saber
    # qual robô vai rodar, porque o SÍMBOLO é propriedade do robô (não do
    # slot desde 2026-08-21) — dois robôs de day trade registrados podem
    # operar símbolos diferentes.
    if not nunca_comecou:
        # conta já em operação: robô é o da conta, NUNCA do form -- evita que
        # a conta troque de robô sozinha só porque o ranking automático (ou
        # o catálogo de day trade) mudou depois da criação (decisão do dono,
        # 2026-08-19: "nada automático").
        strategy_key = conta.investment_robot
    elif slot.is_intraday:
        # Day trade: o robô é o do PRÓPRIO SLOT — o cartão só existe porque o
        # dono escolheu robô+ativo em "novo robô", e essa escolha É o id
        # (`dt-<robô>-<ativo>`). O form não tem voz aqui, nem precisa: trocar
        # o robô de um cartão significaria trocar o ativo dele junto, o que é
        # outro cartão. Este ramo só roda se a conta perdeu o
        # `investment_robot` (linha criada à mão, migração antiga) — o slot
        # sabe reconstruí-lo.
        from strategy.daytrade.registry import list_daytrade_robots

        valid_keys = {r.key for r in list_daytrade_robots()}
        strategy_key = slot.robot_key
        if strategy_key not in valid_keys:
            erro = (
                f"o robô '{slot.robot_key}' do slot '{slot.id}' não está no "
                "catálogo de day trade — remova este robô e crie outro."
            )
    else:
        # Primeira conta de swing: o robô vem do TOP-3 do ranking automático
        # (janela FULL) mostrado no form -- nunca uma chave arbitrária, mesmo
        # que o form venha adulterado/desatualizado (mesmo espírito de floor/
        # disjuntor, ver teste `..._ignora_piso_e_disjuntor_arbitrarios...`).
        top3 = reader.top_strategies_by_final_capital(
                top_n=3, run_kind="champion_full", only=candidate_keys())
        valid_keys = {c["strategy_name"] for c in top3}
        strategy_key = form.get("robo") or slot.robot_key
        if not valid_keys:
            erro = (
                "O ranking automático ainda não tem nenhum robô qualificado "
                "para operar -- aguarde o próximo recálculo (a cada 6h) antes "
                "de iniciar."
            )
        elif strategy_key not in valid_keys:
            erro = "Escolha um robô da lista antes de iniciar."

    # O modo é fixo desde a CRIAÇÃO do slot (2026-08-24) — parte do próprio
    # `slot.id` (`dt-<robô>-<ativo>-<modo>`), não mais uma escolha feita
    # aqui em "Iniciar". Só o slot intradiário tem modo; swing sempre envia
    # de verdade, nunca teve modo sombra.
    #
    # Calculado AQUI (e não mais logo antes do `ProcessConfig`, ver histórico
    # git): o piso de caixa abaixo precisa saber o modo ANTES de escolher
    # qual saldo (`cash`/`cash_sombra`) checar (dono, 2026-08-23).
    execution_mode = slot.execution_mode if slot.is_intraday else "live"

    # "Ações por lote" é parâmetro do TERMINAL MT5 do usuário, não da
    # estratégia nem da sessão -- detectado sozinho a cada clique em
    # "Iniciar operação" via `detect_shares_per_lot()` (consulta o
    # symbol_info do terminal MT5 já conectado), nunca digitado pelo
    # usuário (decisão do dono, 2026-08-20; substitui o campo manual em
    # Acesso e credenciais, que por sua vez substituiu o workaround ainda
    # mais antigo que reexibia o campo no form de retomada).
    mt5_shares_per_lot = None
    if erro is None:
        mt5_shares_per_lot = live_control.detect_shares_per_lot(slot.id, strategy_key)
        if mt5_shares_per_lot is None or mt5_shares_per_lot <= 0:
            erro = (
                "Não foi possível detectar 'ações por lote' automaticamente — "
                "confirme que o terminal MetaTrader 5 está aberto e logado nesta "
                "máquina (ou que login/senha/servidor MT5 foram salvos em 'Acesso "
                "e credenciais') e que os papéis deste robô têm o mesmo "
                "contract_size no seu terminal."
            )

    if erro is None:
        # Piso de caixa: checado SEMPRE (não só na conta nova). O botão
        # desabilitado no template não cobre um POST repetido, um fragmento
        # HTMX velho nem a linha de comando; `live_control.start()` checa de
        # novo, mas aqui a mensagem pode dizer o número em vez de só falhar.
        #
        # `strategy_key` já está resolvido aqui (robô ESCOLHIDO, não o
        # default do slot) — `min_cash_for` usa o piso daquele robô
        # especificamente, não `slot.min_cash_brl` cego ao símbolo (ver
        # docstring de `min_cash_for`, 2026-08-22).
        piso = live_control.min_cash_for(slot, strategy_key)
        # Mode-aware (dono, 2026-08-23): em sombra, o piso é conferido contra
        # `cash_sombra`, não `cash` -- sem isto, um robô com saldo de sombra
        # de sobra continuava bloqueado por um caixa real insuficiente, só
        # para (se o gate fosse burlado) parar de operar no primeiro pregão
        # de qualquer jeito, porque `IntradayLiveRuntime._check_capital` já
        # confere o mesmo saldo (ver `AccountState.cash_for`).
        ledger = live_control.available_cash(slot.id, execution_mode) or 0.0
        # Soma o que já está comprometido numa posição aberta deste slot
        # (2026-08-24, mesmo dia da correção que passou a debitar o custo da
        # entrada do caixa em `live.intraday_runtime._on_opened`) -- mesma
        # regra de `live_control.start()` (ver o comentário lá para o
        # raciocínio completo): sem isto, reiniciar o processo para só
        # continuar vigiando uma posição que já existe ficava bloqueado pelo
        # piso, porque o caixa LIVRE caiu abaixo dele assim que a entrada
        # começou a ser debitada.
        comprometido = (
            sum(abs(p.quantity) * p.entry_price for p in conta.positions.values())
            if conta is not None else 0.0
        )
        if (ledger + comprometido) < piso:
            rotulo_saldo = "sombra" if execution_mode == "shadow" else "real"
            erro = (
                f"Informe o caixa {rotulo_saldo} destinado a este robô (mínimo "
                f"R$ {piso:.2f}) antes de iniciar — o valor atual é "
                f"R$ {ledger:.2f}"
                f"{f' (+ R$ {comprometido:.2f} já em posição aberta)' if comprometido else ''}."
            )
        else:
            # Capital que dimensiona a posição (`ProcessConfig.capital` ->
            # `IntradayLiveRuntime.initial_capital`) = o saldo ATUAL do modo
            # escolhido, sempre -- não só na primeira vez. Antes disto, uma
            # conta já existente sizava contra `conta.initial_capital`
            # congelado na criação (podendo estar bem defasado do ledger
            # atual, achado ao vivo em `dt-gremah-pmam3`: cash=30,
            # initial_capital=0) em vez do caixa que o dono efetivamente
            # destinou ao robô agora. Não é lido da corretora (ver o
            # comentário no lugar de `live_control.detect_broker_capital`,
            # removida em 2026-08-21): o saldo do MT5 atrasa em relação ao da
            # Rico, e com dois robôs disputando a mesma conta um número
            # atrasado viraria dois livros-caixa errados.
            capital = ledger

    mt5_fractional_map = None
    if erro is None and not slot.is_intraday:
        # Mapa fracionário (ver docstring de `detect_fractional_symbol_map`):
        # detectado sozinho a cada clique, igual "ações por lote" -- falha
        # aqui NUNCA bloqueia o início, só degrada para só lote padrão (mesmo
        # comportamento de antes desta detecção existir). O broker decide, a
        # cada ordem, entre lote padrão (grátis na Rico) e fracionário (paga
        # por ordem) conforme a quantidade pedida — nunca fixo por conta.
        #
        # Day trade NUNCA passa por aqui (pedido explícito do dono,
        # 2026-08-22): `mt5_fractional_map` fica `None` sempre para um slot
        # intradiário, mesmo que o terminal tenha símbolo fracionário para o
        # papel. Não é degradação silenciosa que o robô tolera -- é política:
        # giro alto (`gremah.sizing_rules`) paga taxa de bolsa a cada
        # round-trip, e uma ordem fracionária custa R$1,90 fixos por ordem na
        # Rico, inviabilizando o robô se ele algum dia cair nesse caminho.
        # Quantidade que não fecha o lote padrão tem de ser REJEITADA
        # (`MT5Broker._send`), nunca reencaminhada ao mercado fracionário.
        mt5_fractional_map = live_control.detect_fractional_symbol_map(slot.id, strategy_key)

    if erro is None and nunca_comecou and conta is not None:
        # A conta já existia só como linha de caixa (criada por
        # `operacao_caixa`, sem robô): grava o robô e o capital escolhidos
        # AGORA. `live_store.ensure_account` é `ON CONFLICT DO NOTHING` —
        # sozinho, ele deixaria `investment_robot` vazio para sempre e o
        # painel não teria como montar o runtime de leitura.
        #
        # `conta.initial_capital` grava sempre o caixa REAL (nunca `capital`,
        # que pode ser o saldo de SOMBRA quando `execution_mode="shadow"`):
        # este campo alimenta `ja_aportado_brl` em `_avaliar_sugestao_de_
        # capital` (quanto o dono JÁ pôs de dinheiro de verdade nos robôs), e
        # um robô testado só em sombra ainda não recebeu nenhum aporte real
        # -- gravar o saldo de sombra ali inflaria essa conta com dinheiro
        # que não existe.
        with live_store.live_journal() as conn:
            conta = live_store.load_account(conn, slot.id)
            conta.investment_robot = strategy_key
            conta.initial_capital = live_control.available_cash(slot.id, "live") or 0.0
            live_store.save_account(conn, conta)

    if erro is None:
        try:
            cfg = live_control.ProcessConfig(
                mode="mt5", capital=capital, strategy=strategy_key,
                slot=slot.id,
                execution_mode=execution_mode,
                notify_min_level=form.get("notify_min_level") or "warn",
                mt5_shares_per_lot=mt5_shares_per_lot,
                mt5_fractional_map=mt5_fractional_map,
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


@app.post("/operacao/daytrade/novo", response_class=HTMLResponse)
async def operacao_novo_robo(request: Request):
    """Cria um cartão de robô de day trade: um par robô+ativo, com conta,
    caixa e processo próprios.

    Só cria a LINHA da conta (caixa zero, nada rodando). Informar o caixa e
    clicar "Iniciar operação" continuam sendo dois passos separados e
    explícitos — abrir o cartão não pode ser o mesmo gesto que começar a
    operar dinheiro.

    Aceita um ativo que já tem robô (2026-08-24, pedido do dono): criar o
    cartão nunca manda ordem nenhuma, então dois robôs DIFERENTES no mesmo
    ativo (ex.: gremah e gremah_tick em PMAM3, ambos em sombra) é uma
    comparação válida, e bloquear aqui escondia essa combinação mesmo quando
    era perfeitamente segura. O risco real -- a conta da Rico é NETTING, dois
    robôs mandando ordem de verdade no mesmo papel viram uma posição só e os
    dois caixas passam a mentir -- só existe quando algum dos dois de fato
    tenta operar dinheiro, e é isso que `live_control._assert_slots_disjuntos`
    checa (e bloqueia, com o motivo específico) na hora de Iniciar.

    MODO entra aqui, não mais em "Iniciar" (2026-08-24, pedido do dono): faz
    parte da identidade do slot (`daytrade_slot_id`), o que permite o MESMO
    robô no MESMO ativo ter um cartão sombra e um cartão real, cada um com
    processo/conta/caixa próprios. Por isso, ao contrário do robô+ativo, o
    par completo (robô, ativo, modo) NÃO pode repetir — `ensure_account`
    sozinho seria um no-op silencioso (`ON CONFLICT DO NOTHING`, mesmo
    `slot.id`) e o dono clicaria "Criar" sem nada aparecer de novo.
    """
    from core.config import DAYTRADE_EXECUTION_MODES, daytrade_slot
    from journal import live_store
    from strategy.daytrade.registry import get_daytrade_robot

    form = await request.form()
    robot_key = (form.get("robot") or "").strip()
    symbol = (form.get("symbol") or "").strip().upper()
    execution_mode = (form.get("execution_mode") or "").strip().lower()
    erro = None
    if not robot_key or not symbol:
        erro = "Escolha o robô e o ativo."
    elif execution_mode not in DAYTRADE_EXECUTION_MODES:
        erro = "Escolha o modo (sombra ou real)."
    else:
        try:
            # O ROBÔ é quem valida o ativo: `Gremah.__init__` levanta
            # `ValueError` para símbolo sem calibração própria em vez de
            # herdar a de outro papel. Instanciar aqui é o que impede o painel
            # de criar um cartão que nunca conseguiria subir.
            get_daytrade_robot(robot_key, symbol=symbol)
            slot = daytrade_slot(robot_key, symbol, execution_mode)
            with live_store.live_journal() as conn:
                if live_store.load_account(conn, slot.id) is not None:
                    erro = (
                        f"o robô '{robot_key}' já existe em {symbol} no modo "
                        f"{'sombra' if execution_mode == 'shadow' else 'real'} "
                        "— escolha outro ativo, outro robô ou o outro modo."
                    )
                else:
                    live_store.ensure_account(
                        conn, name=slot.id, mode="mt5", initial_capital=0.0,
                        investment_robot=robot_key, withdrawal_robot="", symbol=symbol,
                    )
        except (KeyError, ValueError, RuntimeError) as e:
            erro = str(e)

    ctx = _operacao_ctx(erro=erro)
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", ctx)


@app.post("/operacao/{slot_id}/remover", response_class=HTMLResponse)
async def operacao_remover_robo(request: Request, slot_id: str):
    """Remove um robô de day trade e libera o ativo dele.

    Recusa se o processo estiver rodando (pare antes — remover a conta não
    mata o processo, que continuaria operando contra uma conta inexistente),
    e `live_store.delete_account` recusa de novo se houver posição aberta ou
    caixa. Slot estático (swing) não é removível: ele não foi criado aqui.
    """
    slot = _slot_or_404(slot_id)
    from journal import live_store

    erro = None
    if not slot.is_dynamic:
        erro = f"O slot '{slot.label}' é fixo — só robôs de day trade criados aqui podem ser removidos."
    elif live_control.status(slot.id) is not None:
        erro = f"O robô '{slot.label}' está rodando — pare a operação antes de remover."
    else:
        try:
            with live_store.live_journal() as conn:
                live_store.delete_account(conn, slot.id)
        except ValueError as e:
            erro = str(e)

    ctx = _operacao_ctx(erro=erro)
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", ctx)


@app.post("/operacao/daytrade/reordenar", response_class=HTMLResponse)
async def operacao_reordenar_daytrade(request: Request):
    """Grava a ordem dos cartões de day trade depois de o dono arrastar um
    cartão FECHADO para outra posição (pedido do dono, 2026-08-24) — a ordem
    tem de sobreviver a F5 e a reiniciar o `dev.bat`, então mora no banco
    (`live_accounts.sort_order`), não no navegador.

    `ordem` chega como uma string só, ids separados por vírgula, na ordem
    final desejada de cima pra baixo — é o próprio JS do painel
    (`static/js/operacao.js`) que lê essa ordem do DOM depois do drop e
    manda aqui; não há "vizinho" para trocar feito um botão de mover, o
    cartão pode ser largado em QUALQUER posição.
    """
    form = await request.form()
    ordem = [nome for nome in str(form.get("ordem", "")).split(",") if nome]
    from journal import live_store

    with live_store.live_journal() as conn:
        live_store.set_daytrade_account_order(conn, ordem)
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", _operacao_ctx())


@app.post("/operacao/avisos/{signal_id}/feito", response_class=HTMLResponse)
async def operacao_aviso_feito(request: Request, signal_id: int):
    """Marca um aviso de capital como resolvido. Idempotente: um POST repetido
    (F5, duplo clique) não é erro — `acknowledge_capital_signal` já devolve
    `False` sem mexer em nada."""
    from journal import live_store

    with live_store.live_journal() as conn:
        live_store.acknowledge_capital_signal(conn, signal_id)
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", _operacao_ctx())


@app.post("/operacao/{slot_id}/parar", response_class=HTMLResponse)
def operacao_parar(request: Request, slot_id: str):
    slot = _slot_or_404(slot_id)
    live_control.stop(slot.id)
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", _operacao_ctx())


@app.post("/operacao/{slot_id}/caixa", response_class=HTMLResponse)
async def operacao_caixa(request: Request, slot_id: str):
    """LEDGER MANUAL de caixa deste robô — a fonte de verdade do capital que
    ele pode usar.

    Substituiu, em 2026-08-21, os dois caminhos anteriores: o sync automático
    do saldo da corretora (`LiveRuntime.reconcile_broker_cash`, removido) e o
    override manual único (`POST /operacao/saldo-observado`, removido). Os
    dois pressupunham UM robô e UM saldo. Dois motivos derrubaram isso:

    1. Achado ao vivo (2026-08-21): o saldo que o terminal MetaTrader 5
       reporta NÃO acompanha o da Rico — um depósito real não aparecia nem em
       `account_info()` nem em `history_deals_get()`, com o terminal
       conectado e `trade_allowed=True`.
    2. Com dois robôs, "o saldo da corretora" não responde à pergunta que
       importa ("quanto ESTE robô pode usar?"). Cada slot tem a sua linha em
       `live_accounts`, e cada robô só mexe no seu número.

    Define um saldo ABSOLUTO (não soma um valor), o que o torna naturalmente
    idempotente contra duplo-clique/F5/retry: reenviar o mesmo valor já
    convergido cai dentro da tolerância de `live_store.reconcile_cash` e não
    grava nada de novo, sem precisar de nenhuma guarda de dedup em memória.

    `tolerance=0.005` (não o default `1.0`): num caixa de R$ 50 o default
    engoliria uma correção de R$ 0,50 em silêncio — 1% do capital do robô.

    Sem broker/`LiveRuntime` aqui de propósito — é contabilidade pura; não há
    decisão de estratégia envolvida."""
    slot = _slot_or_404(slot_id)
    form = await request.form()
    from journal import live_store

    erro = None
    caixa_msg = None
    valor = _valor_brl(form.get("caixa", ""))
    if valor is None or valor < 0:
        erro = "Informe o caixa destinado a este robô (maior ou igual a zero)."
    else:
        try:
            with live_store.live_journal() as conn:
                conta = live_store.load_account(conn, slot.id)
                if conta is None:
                    # Conta ainda não existe: cria só a linha CONTÁBIL, com o
                    # caixa informado. Nada sobe, nada opera — mas o número
                    # digitado tem de sobreviver ao F5, senão o piso de R$50
                    # nunca é alcançável antes de iniciar.
                    #
                    # `investment_robot=""` de propósito: quem escolhe o robô é
                    # "Iniciar operação" (ranking automático no swing, catálogo
                    # do slot no day trade). Gravar um robô aqui faria informar
                    # o caixa decidir, de lado, qual robô opera o dinheiro.
                    #
                    # Day trade é a EXCEÇÃO e grava robô+ativo: neles a conta
                    # não é "uma linha de caixa à espera de um robô", é a
                    # própria existência do cartão (`dashboard.slots` lista os
                    # slots pelas contas COM `symbol`). Criar sem isso faria o
                    # cartão sumir da tela no F5 seguinte. E não há escolha
                    # sendo feita de lado aqui: robô e ativo já foram
                    # decididos em "novo robô" e estão no id do slot.
                    conta = live_store.ensure_account(
                        conn, name=slot.id, mode="mt5", initial_capital=valor,
                        investment_robot=slot.robot_key if slot.is_dynamic else "",
                        withdrawal_robot="",
                        symbol=slot.symbol if slot.is_dynamic else "",
                    )
                # Modo "shadow" edita `cash_sombra`, nunca `cash` -- pedido do
                # dono (2026-08-23): "separação dos campos de saldo, pra o
                # sombra ter seu saldo e o real o seu". O modo é fixo no
                # próprio slot desde 2026-08-24 (não mais um campo de form) --
                # swing não tem `cash_sombra` nem modo.
                editando_sombra = slot.is_intraday and slot.execution_mode == "shadow"
                if editando_sombra:
                    diff, aplicado = live_store.reconcile_cash_sombra(
                        conn, conta, valor, tolerance=0.005,
                    )
                else:
                    diff, aplicado = live_store.reconcile_cash(
                        conn, conta, valor, clock.session_date(), origin="manual_ledger",
                        note=(f"caixa destinado ao robô do slot '{slot.id}', informado "
                              "manualmente pelo dono"),
                        tolerance=0.005,
                    )
                if aplicado:
                    saldo_novo = conta.cash_sombra if editando_sombra else conta.cash
                    descricao = "caixa sombra" if editando_sombra else "caixa"
                    live_store.log_event(
                        conn, conta.id, "info" if diff > 0 else "warn", "operacao",
                        f"{descricao} do slot '{slot.id}' definido manualmente: "
                        f"{saldo_novo - diff:.2f} -> {saldo_novo:.2f} "
                        f"(diferença R$ {diff:.2f}) -- ledger manual, não veio do MT5.",
                        {"diferenca": diff, "slot": slot.id, "sombra": editando_sombra},
                    )
                    caixa_msg = (f"{descricao.capitalize()} de '{slot.label}' atualizado "
                                 f"para R$ {valor:.2f} (diferença R$ {diff:+.2f}).")
                else:
                    caixa_msg = "O valor informado já é o caixa atual — nada para atualizar."
        except (live_store.LegacyPaperAccountError, live_store.LegacyManualAccountError) as e:
            erro = str(e)

    ctx = _operacao_ctx(erro=erro, caixa_msg=caixa_msg)
    return TEMPLATES.TemplateResponse(request, "partials/operacao_body.html", ctx)


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
def operacao_historico(request: Request, slot: str = live_service.DEFAULT_SLOT):
    """Retrospecto da conta de operação de UM slot: curva de patrimônio +
    toda intenção já decidida + saques já executados. Só leitura, mesma
    disciplina de `/operacao` — nunca cria a conta.

    `?slot=` porque o histórico é por conta e cada slot tem a sua; sem o
    parâmetro cai no primeiro slot do catálogo (day trade)."""
    from core.config import ordered_slots
    from journal import live_store

    escolhido = _slot_or_404(slot)
    try:
        with live_store.live_journal() as conn:
            account = live_store.load_account(conn, escolhido.id)
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
    ctx["slot"] = escolhido
    ctx["slots"] = ordered_slots()
    return TEMPLATES.TemplateResponse(request, "historico.html", ctx)
