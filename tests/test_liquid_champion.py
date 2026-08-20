"""O campeao novo, a aposentadoria do antigo, e o que a aposentadoria NAO pode quebrar.

O risco real coberto aqui nao e o robo novo dar numero errado — e a troca de
campeao derrubar coisa que ja esta rodando. Aposentar um robo mexe em tres
lugares que nao tem nada a ver entre si: a auto-descoberta, o registry que
resolve chave em objeto, e o diario que guarda o pódio. Errar qualquer um deles
so aparece em producao.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from journal import reader
from journal.writer import init_db, journal
from strategy.discovery import discover_strategies
from strategy.liquid_champion import LiquidChampion
from strategy.liquid_sleeves5 import LiquidSleeves5
from strategy.liquid_sleeve import POOL
from strategy.portfolio_dip2_hw40 import DipTop1Portfolio
from strategy.registry import REGISTRY, candidate_keys, get_strategy, list_strategies


# --------------------------------------------------------------- o robo novo

def test_campeao_e_candidato_e_instanciavel_sem_argumentos():
    chaves = [d.key for d in discover_strategies()]
    assert "liquid_champion" in chaves
    bot = LiquidChampion()
    assert bot.name == "liquid_champion"


def test_campeao_opera_o_pool_de_liquidez_e_nao_a_watchlist_de_hindsight():
    """O universo e o pool bruto — e dele que o filtro de liquidez escolhe.

    Se este atributo voltasse a ser a WATCHLIST, o robo continuaria rodando sem
    erro nenhum e operaria 7 papeis escolhidos com gabarito. Silencioso.
    """
    from core.config import WATCHLIST

    assert LiquidChampion().universe_tickers == POOL
    assert set(WATCHLIST) != set(POOL)


def test_campeao_tem_cinco_sleeves_disjuntos():
    bot = LiquidChampion()
    assert bot.sleeve_count == 5
    assert len(bot._sleeves) == 5
    assert [s.sleeve_index for s in bot._sleeves] == [0, 1, 2, 3, 4]


def test_campeao_usa_grandfathering_e_nao_despejo():
    """Despejo forca venda no dia do calendario; foi decidido que nao entra."""
    assert all(s.evict_on_refresh is False for s in LiquidChampion()._sleeves)


def test_campeao_usa_top20_com_epoca_de_12_meses():
    """A regra de universo do campeao, fixada pelo holdout de 48 janelas.

    Se `refresh_months` ou `universe_n` mudarem, o holdout deixa de valer para
    este robo — os numeros do docstring foram medidos nesta configuracao.
    """
    for s in LiquidChampion()._sleeves:
        assert s.refresh_months == 12
        assert s.universe_n == 20
        assert s.liquidity_window == 252
        assert s.min_history_days == 504


def test_campeao_nao_muda_o_comportamento_do_sleeves5():
    """O campeao E o `liquid_sleeves5` promovido — a promocao nao pode alterar nada.

    Vale mais do que parece: todo numero que justifica o campeao (holdout de 48
    janelas, sensibilidade ao dia de rebalanceamento, janela FULL do ranking) foi
    medido no sleeves5. Se a promocao mudasse um parametro que fosse, esses
    numeros deixariam de valer para ele e o docstring estaria mentindo.
    """
    novo, antigo = LiquidChampion(), LiquidSleeves5()
    comparaveis = ("sleeve_count", "dip_pct", "high_window", "satellite_pct")
    for attr in comparaveis:
        assert getattr(novo, attr) == getattr(antigo, attr), attr
    for a, b in zip(novo._sleeves, antigo._sleeves):
        assert type(a) is type(b)
        for attr in ("universe_n", "refresh_months", "liquidity_window",
                     "min_history_days", "evict_on_refresh", "sleeve_index"):
            assert getattr(a, attr) == getattr(b, attr), attr


# ------------------------------------------------------------ a aposentadoria

@pytest.mark.parametrize("chave", ["portfolio_dip2_hw40", "liquid_sleeves5", "liquid_flow5"])
def test_robo_aposentado_sai_do_podio(chave):
    assert chave not in candidate_keys()
    assert chave not in [i.key for i in list_strategies()]


@pytest.mark.parametrize("chave", ["portfolio_dip2_hw40", "liquid_sleeves5", "liquid_flow5"])
def test_robo_aposentado_continua_resolvivel_por_chave(chave):
    """Uma conta ao vivo que ja opera o robo aposentado nao pode quebrar.

    Este e o teste que impede a curadoria do pódio de virar incidente: se
    `get_strategy` levantasse `KeyError`, `run_live.py` e o painel `/operacao`
    morreriam na proxima execucao de uma conta real que ja estava rodando.
    """
    info = get_strategy(chave)
    assert info.key == chave
    assert info.factory() is not None
    assert chave in REGISTRY


def test_o_podio_tem_um_robo_so_e_e_o_campeao():
    """Decisao explicita de 2026-08-20: pódio com um robo, o `liquid_champion`.

    O teste existe para a decisao ser VISIVEL. Adicionar um arquivo novo em
    `strategy/` o torna candidato automaticamente (`discovery.py`), entao sem
    este teste o pódio voltaria a ter varios robos sem ninguem decidir isso —
    e a escolha de operar um so deixaria de ser uma escolha.
    """
    from strategy.registry import candidate_keys as _ck

    assert sorted(_ck()) == ["liquid_champion"]


def test_campeao_antigo_continua_sendo_a_base_da_familia():
    """Aposentar nao e apagar: o sinal dele nunca foi o problema."""
    assert issubclass(LiquidChampion, DipTop1Portfolio)


# ------------------------------------------------------- o pódio no diario

def _diario_com_runs(tmp_path: Path, nomes_e_kinds) -> Path:
    db = tmp_path / "journal.db"
    init_db(db_path=db)
    with journal(db) as conn:
        for nome, kind, final in nomes_e_kinds:
            conn.execute(
                "INSERT INTO runs (strategy_name, strategy_version, period_start, "
                "period_end, initial_capital, final_capital, run_kind, neg_years, "
                "max_drawdown) VALUES (?, '1.0', '2010-01-01', '2026-01-01', 1000.0, "
                "?, ?, 0, -0.30)",
                (nome, final, kind),
            )
    return db


def test_podio_ignora_robo_aposentado_mesmo_com_run_antiga_no_diario(tmp_path):
    """O caso que realmente importa na troca de campeao.

    O robo aposentado tem capital final MAIOR (era o TOP-1 justamente por isso).
    Se o filtro nao existisse, aposenta-lo nao mudaria nada: ele para de ser
    rerrodado e congela em primeiro lugar com o ultimo numero, para sempre.
    """
    db = _diario_com_runs(tmp_path, [
        ("portfolio_dip2_hw40", "champion_full", 170_000.0),
        ("liquid_champion", "champion_full", 9_000.0),
    ])
    todos = reader.top_strategies_by_final_capital(db_path=db)
    assert [r["strategy_name"] for r in todos][0] == "portfolio_dip2_hw40"

    podio = reader.top_strategies_by_final_capital(db_path=db, only={"liquid_champion"})
    assert [r["strategy_name"] for r in podio] == ["liquid_champion"]


def test_filtro_do_podio_nao_apaga_a_run_do_aposentado(tmp_path):
    """Filtrar, nao deletar: a run e o registro do que foi medido.

    AGENTS.md: "nao descarte dado". Curadoria de pódio nao pode destruir
    medicao — o numero do robo aposentado continua consultavel no historico.
    """
    db = _diario_com_runs(tmp_path, [("portfolio_dip2_hw40", "champion_full", 170_000.0)])
    reader.top_strategies_by_final_capital(db_path=db, only={"liquid_champion"})
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_sem_filtro_o_comportamento_antigo_continua(tmp_path):
    """`only=None` nao pode mudar em silencio quem chama sem conhecer o parametro."""
    db = _diario_com_runs(tmp_path, [("liquid_champion", "champion_full", 9_000.0)])
    assert len(reader.top_strategies_by_final_capital(db_path=db)) == 1


# ------------------------------------- o pregao pela metade que travava tudo

def test_loader_corta_pregao_sem_fechamento_no_fim_da_serie(tmp_path):
    """Barra do dia baixada com o mercado aberto: tem `open`, nao tem `close`.

    Era o que impedia QUALQUER robo do pool de entrar no ranking: o backtest
    fechava a posicao aberta no ultimo dia a um preco NaN, e o INSERT do trade
    estourava `NOT NULL` em `fees_total` (NaN vira NULL no SQLite), derrubando
    a run inteira. Falha barulhenta no lugar errado, causa silenciosa no dado.
    """
    from market_data.loader import _drop_incomplete_tail

    idx = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14"])
    df = pd.DataFrame({"open": [1.0, 2.0, 3.0], "close": [1.1, 2.1, float("nan")]}, index=idx)
    cortado = _drop_incomplete_tail(df, "X.SA")
    assert len(cortado) == 2
    assert cortado.index[-1] == pd.Timestamp("2026-08-13")


def test_loader_preserva_buraco_no_MEIO_da_serie(tmp_path):
    """Buraco interno e outro problema — tratado na origem por `quality.py`.

    Cortar aqui esconderia exatamente o que aquele modulo procura.
    """
    from market_data.loader import _drop_incomplete_tail

    idx = pd.to_datetime(["2026-08-11", "2026-08-12", "2026-08-13"])
    df = pd.DataFrame({"open": [1.0, 2.0, 3.0], "close": [1.1, float("nan"), 3.1]}, index=idx)
    assert len(_drop_incomplete_tail(df, "X.SA")) == 3


# --------------------------------------- os portoes do pódio contra o indice

def _run_com_curva(tmp_path: Path, *, dd_robo: float, dd_bench: float,
                   final: float = 5_000.0, neg_robo: int = 0) -> Path:
    """Cria uma run com curva de robô e de índice, com o MaxDD pedido em cada.

    Curva de dois trechos: sobe, cai o drawdown pedido, sobe de novo. Duas datas
    dentro do mesmo ano-calendário para o cálculo de anos negativos ficar sob
    controle do parâmetro e não do formato da curva.
    """
    db = tmp_path / "journal.db"
    init_db(db_path=db)
    datas = pd.date_range("2020-01-01", periods=8, freq="ME")
    robo = [100.0, 120.0, 120.0 * (1 + dd_robo), 120.0, 130.0, 140.0, 150.0, 160.0]
    bench = [100.0, 120.0, 120.0 * (1 + dd_bench), 120.0, 130.0, 140.0, 150.0, 160.0]
    with journal(db) as conn:
        cur = conn.execute(
            "INSERT INTO runs (strategy_name, strategy_version, period_start, "
            "period_end, initial_capital, final_capital, run_kind, neg_years, "
            "max_drawdown) VALUES ('liquid_champion', '1.0', '2020-01-01', "
            "'2020-08-31', 1000.0, ?, 'champion_full', ?, ?)",
            (final, neg_robo, dd_robo),
        )
        rid = cur.lastrowid
        for d, e, b in zip(datas, robo, bench):
            conn.execute(
                "INSERT INTO equity_curve (run_id, date, equity, benchmark) VALUES (?,?,?,?)",
                (rid, d.strftime("%Y-%m-%d"), e, b),
            )
    return db


def test_portao_reprova_robo_com_drawdown_pior_que_o_indice(tmp_path):
    db = _run_com_curva(tmp_path, dd_robo=-0.40, dd_bench=-0.20)
    assert reader.top_strategies_by_final_capital(db_path=db) == []


def test_portao_aprova_robo_com_drawdown_melhor_que_o_indice(tmp_path):
    db = _run_com_curva(tmp_path, dd_robo=-0.20, dd_bench=-0.40)
    podio = reader.top_strategies_by_final_capital(db_path=db)
    assert [r["strategy_name"] for r in podio] == ["liquid_champion"]
    assert podio[0]["bench_max_drawdown"] == pytest.approx(-0.40, abs=1e-9)


def test_portao_nao_e_mais_o_numero_do_campeao_aposentado(tmp_path):
    """-35,12% era o MaxDD exato do `portfolio_dip2_hw40`.

    Um robô com -36% de MaxDD reprovava no portão antigo por definicao. Agora a
    pergunta e outra: -36% e pior que o indice? Se o indice fez -48%, nao e.
    """
    db = _run_com_curva(tmp_path, dd_robo=-0.36, dd_bench=-0.48)
    assert len(reader.top_strategies_by_final_capital(db_path=db)) == 1


def test_portao_reprova_robo_com_mais_anos_negativos_que_o_indice(tmp_path):
    db = _run_com_curva(tmp_path, dd_robo=-0.10, dd_bench=-0.40, neg_robo=3)
    assert reader.top_strategies_by_final_capital(db_path=db) == []


def test_run_sem_benchmark_passa_marcada_em_vez_de_sumir(tmp_path):
    """Falta de dado nao pode reprovar em silencio nem aprovar em silencio."""
    db = tmp_path / "journal.db"
    init_db(db_path=db)
    with journal(db) as conn:
        conn.execute(
            "INSERT INTO runs (strategy_name, strategy_version, period_start, "
            "period_end, initial_capital, final_capital, run_kind, neg_years, "
            "max_drawdown) VALUES ('liquid_champion', '1.0', '2020-01-01', "
            "'2020-12-31', 1000.0, 5000.0, 'champion_full', 0, -0.30)"
        )
    podio = reader.top_strategies_by_final_capital(db_path=db)
    assert len(podio) == 1
    assert podio[0]["gate_unavailable"] is True


# ---------- pregao perdido: o campeao e composto, o repasse tem de existir ----

def _campeao_inicializado():
    """Campeao com `initialize()` rodado sobre um painel sintetico minimo.

    `on_missed_bars` consulta `_month_end`, que so existe depois de
    `initialize()` — testar antes disso passaria por acidente.
    """
    import pandas as pd

    from strategy.liquid_champion import LiquidChampion

    dias = pd.bdate_range("2028-01-03", periods=600)
    painel = pd.DataFrame(
        {"open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 1_000_000.0},
        index=pd.DatetimeIndex(dias, name="date"),
    )
    ibov = painel.copy()
    bot = LiquidChampion()
    bot.initialize({t: painel.copy() for t in bot.universe_tickers[:6]}, ibov)
    fim_de_mes = [d for d in dias if d.month != (d + pd.offsets.BDay(1)).month]
    return bot, dias, fim_de_mes


def test_fim_de_mes_perdido_deixa_rotacao_devida_nos_CINCO_sleeves():
    """O campeao nao rebalanceia nada por conta propria: `on_bar` delega tudo
    aos cinco sleeves. Se `on_missed_bars` parasse no objeto de fora, o
    pendente ficaria num lugar que nao decide, os cinco sleeves voltariam
    achando que nao devem nada, e o robo passaria o mes sem rotacao — em
    silencio, porque o alerta do runtime teria sido emitido normalmente.
    """
    bot, _dias, fim_de_mes = _campeao_inicializado()
    assert not any(s._pending_rebalance for s in bot._sleeves)

    bot.on_missed_bars([fim_de_mes[3]])

    assert all(s._pending_rebalance for s in bot._sleeves), (
        "repasse aos sleeves nao aconteceu — rotacao devida ficou orfa")


def test_pregao_comum_perdido_nao_deixa_nada_devido_no_campeao():
    """Contraprova: sem isto o campeao passaria a rebalancear em qualquer dia
    em que o processo tenha piscado, trocando cadencia mensal por cadencia de
    uptime da maquina."""
    import pandas as pd

    bot, dias, fim_de_mes = _campeao_inicializado()
    comum = next(d for d in dias if d not in set(fim_de_mes))

    bot.on_missed_bars([pd.Timestamp(comum)])

    assert not any(s._pending_rebalance for s in bot._sleeves)


def test_rotacao_devida_dos_sleeves_sobrevive_a_restart():
    """`state()`/`restore()` ja serializavam `_sleeve_pending` para o blackout;
    o pendente que vem de pregao perdido usa o MESMO campo e tem de sobreviver
    igual — um restart depois do buraco nao pode apagar a rotacao devida."""
    bot, _dias, fim_de_mes = _campeao_inicializado()
    bot.on_missed_bars([fim_de_mes[3]])

    outro, _d2, _f2 = _campeao_inicializado()
    outro.restore(bot.state())

    assert all(s._pending_rebalance for s in outro._sleeves)
