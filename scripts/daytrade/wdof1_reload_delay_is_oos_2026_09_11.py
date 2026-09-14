"""WDO F1 (grid maker puro, T2/S16): teste do UNICO eixo de cadencia do
`reload` ainda nao tocado nas 12 hipoteses ja refutadas (7 sinais de timing +
5 ajustes estruturais, ver `LICOES_DE_PRODUCAO.md`/memoria
`wdo_grid_timing_signals_refutados_2026_09_11` e
`wdo_grid_ajustes_estruturais_refutados_2026_09_11`) -- um ATRASO MINIMO
entre o FECHAMENTO de uma posicao (por alvo OU por stop) e o REARME da
ordem-limite seguinte no mesmo nivel.

POR QUE ISTO E' DIFERENTE das hipoteses ja refutadas: aquelas eram
classificacoes POST-HOC dos MESMOS trades (ex.: "trades logo apos um stop
tem taxa de acerto pior?" -- rotula trades que ja aconteceram e descobre que
a taxa de acerto do rotulo = taxa de acerto do dia, sem separacao real).
Aqui o atraso e' ESTRUTURAL: impor `reload_min_segundos>0` MUDA quais trades
acontecem (menos trades totais, potencialmente evitando reentrar durante um
movimento direcional que ainda nao esgotou logo apos um stop) -- nao e' uma
reclassificacao do que ja saiu do motor.

EXPERIMENTO, NAO PRODUCAO -- por pedido explicito: `wdo_grid_reload_maker.py`
NAO e' editado. O parametro novo (`reload_min_segundos`, default 0.0 =
byte-a-byte identico ao motor atual) vive numa SUBCLASSE local
(`WdoGridReloadMakerComAtrasoDeReload`, definida neste arquivo), que
sobrescreve so' o ponto exato de decisao onde o rearme pos-fechamento
acontece -- ver a docstring da classe abaixo para o mecanismo.

DIFERENCA DELIBERADA frente a `reancora_min_segundos` (ja existente,
default 10s): aquele freio EXPLICITAMENTE nao atrasa o rearme pos-FILL ("Nao
atrasa o rearme depois de um FILL (a mecanica de reload)", docstring da
classe de producao) -- ele so' throttla (a) reprecificacao de ordem pendente
e (b) rearme apos RECUSA por capital insuficiente. Este script testa o
terceiro caso, que nunca teve freio: o rearme apos um FECHAMENTO (alvo OU
stop). Os dois parametros sao independentes -- este roda por CIMA do freio de
producao (`reancora_min_segundos=10.0` continua ligado, herdado de
`get_daytrade_robot`), nunca no lugar dele.

MOTOR: o MESMO de producao, sem relaxar nada -- `config_for`/`profile_for`,
fila calibrada de `backtest.intraday.fidelidade` (438/489), alvo fatiado real
(`fatiar_saida_alvo=True`, sem prazo -- `EXIT_TTL_BARS_SEM_PRAZO`),
`anchor_exits_at_fill=True`, `feed_kind="tick"`, geometria T2/S16 herdada de
`get_daytrade_robot("wdo_grid_reload_maker")` (que ja inclui
`risco_pct_por_trade=0.01`/`margin_per_contract_brl` etc.). Capital real
R$375/pregao, NUNCA reposto entre pregoes -- cada pregao e' uma observacao
independente (mesmo padrao dos scripts WDO F1 anteriores).

BASE DE DADOS E SPLIT IS/OOS: MESMA logica de
`wdof1_combo_t3_is_oos_real_2026_09_11.py` -- `data/raw_ticks/WDO_A_.parquet`
(dias reais canonicos) + os 2 dias extras ja cacheados em barra degenerada
(2026-09-08, 2026-09-09), corte cronologico 2/3-1/3 SEM sobreposicao:

    IS  = 2026-02-27 .. 2026-07-06  (88 pregoes)
    OOS = 2026-07-07 .. 2026-09-09  (44 pregoes)

METODO: varredura no IS primeiro, {0 (controle), 2, 5, 10, 30, 60} segundos,
`ProcessPoolExecutor` com `submit`/`as_completed` (nunca serial nem
`pool.map`), streaming de resultado por celula. So' se algum valor mostrar
IC95% de Wilson do win% (contra o breakeven EMPIRICO do proprio periodo)
inteiramente ACIMA, liquido positivo E sem censura excessiva no IS, o
candidato UNICO e' confirmado no OOS -- disciplina identica ao combo_T3
(escolhe 1 no IS, testa so' esse no OOS, sem multiple-comparison)."""
from __future__ import annotations

import inspect
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0

TICK_PARQUET_LOCAL = RAIZ / "data" / "raw_ticks" / "WDO_A_.parquet"
BARS_DIR = Path(
    r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
    r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_bars"
)

VALORES_IS = [0.0, 2.0, 5.0, 10.0, 30.0, 60.0]


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


# ------------------------------------------------------------- cache de barras
def _bars_path(dia: date) -> Path:
    dia_str = dia.isoformat()
    for prefixo in ("WDOV26_", "WDO_at_", "WDO_hist_"):
        p = BARS_DIR / f"{prefixo}{dia_str}.parquet"
        if p.exists():
            return p
    return BARS_DIR / f"WDO_hist_{dia_str}.parquet"


def preparar_cache_de_barras(dias: list[date]) -> None:
    """Mesma logica de `wdof1_combo_t3_is_oos_real_2026_09_11.py` -- converte
    so' o que ainda nao esta cacheado, numa unica passada pelo parquet
    canonico. Como o cache ja existe (rodadas anteriores da mesma sessao),
    isto normalmente e' um no-op."""
    faltando = {d for d in dias if not _bars_path(d).exists()}
    if not faltando:
        print(f"[cache] {len(dias)} pregoes ja cacheados em barra degenerada -- nada a converter.", flush=True)
        return
    print(f"[cache] convertendo {len(faltando)} pregoes de tick local -> barra "
          f"degenerada (fonte: {TICK_PARQUET_LOCAL.name}) ...", flush=True)
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars

    ticks = pd.read_parquet(TICK_PARQUET_LOCAL)
    convertidos = 0
    for d, sub in ticks.groupby(ticks.index.date):
        if d not in faltando or sub.empty:
            continue
        bars = ticks_to_degenerate_bars(sub)
        bars.to_parquet(BARS_DIR / f"WDO_hist_{d.isoformat()}.parquet")
        convertidos += 1
    del ticks
    print(f"[cache] {convertidos}/{len(faltando)} pregoes convertidos e gravados em {BARS_DIR}", flush=True)
    ainda_faltando = sorted(d for d in faltando if not _bars_path(d).exists())
    if ainda_faltando:
        print(f"[cache] AVISO -- sem tick local para: {ainda_faltando} (seguem de fora do teste)")


# ------------------------------------------------------------ variante nova
def construir_classe_com_atraso():
    """Devolve a subclasse `WdoGridReloadMakerComAtrasoDeReload`, construida
    aqui (nao em modulo separado) para o worker do `ProcessPoolExecutor`
    conseguir importa-la por nome deste proprio arquivo."""
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker

    class WdoGridReloadMakerComAtrasoDeReload(WdoGridReloadMaker):
        """`WdoGridReloadMaker` + `reload_min_segundos` (ADITIVO, OPT-IN,
        default 0.0 = comportamento IDENTICO ao motor de producao).

        MECANISMO. O rearme pos-fechamento (a mecanica de "reload" que da'
        nome ao robo) acontece dentro de `on_bar`, no mesmo `on_bar` que
        detecta o fechamento: quando `positions` fica vazio e
        `state.open_side` ainda carregava o lado que tinha acabado de fechar,
        a classe-mae contabiliza o fechamento e, na SEQUENCIA da MESMA
        chamada (mesmo `on_bar`), passa a decidir se arma uma `EnterLimit`
        nova -- via `_pode_armar_apos_recusa` (que so' olha para RECUSA por
        capital, `state.ultima_recusa_ts`, e devolve `True` sempre que o
        ultimo evento foi um FILL, por desenho: "Apaga o relogio de recusa
        para o rearme pos-fechamento ... sair na hora, sem freio nenhum").

        Esta subclasse insere o atraso em DOIS pontos, sem duplicar a logica
        de ~200 linhas de `on_bar`:

        1. `on_bar` (override fino): ANTES de chamar `super().on_bar(...)`,
           detecta se ESTA chamada e' exatamente a que vai processar um
           fechamento -- `not positions and self._state.open_side is not
           None` (o motor ja fechou a posicao antes de chamar `on_bar`; a
           contabilidade `open_side -> None` da classe-mae ainda nao rodou
           nesta chamada). Se for, grava `self._ultimo_fechamento_ts = ts`
           ANTES de delegar -- assim, quando a classe-mae (na MESMA chamada)
           chegar em `_pode_armar_apos_recusa`, o carimbo ja existe.
        2. `_pode_armar_apos_recusa` (override): primeiro exige o veredito da
           classe-mae (preserva o freio de RECUSA existente, independente
           deste); depois, so' se `reload_min_segundos>0` e houve fechamento
           registrado, exige `(bar.ts - ultimo_fechamento_ts) >=
           reload_min_segundos`. `reload_min_segundos<=0` ou nenhum
           fechamento ainda visto (1a entrada do pregao) devolvem `True`
           direto -- byte-a-byte o comportamento antigo.

        Por que isto cobre TODOS os fechamentos (alvo, stop, ou saida
        explicita da estrategia via `Exit`) sem distinguir a causa: os tres
        caminhos convergem no MESMO ponto -- `positions` fica vazio na
        proxima chamada de `on_bar` e `state.open_side` ainda aponta pro lado
        que fechou. O ponto de deteccao nao precisa saber COMO fechou."""

        def __init__(self, *args, reload_min_segundos: float = 0.0, **kwargs):
            if reload_min_segundos < 0:
                raise ValueError(
                    "reload_min_segundos nao pode ser negativo (0 = sem "
                    "atraso, comportamento identico ao motor de producao)."
                )
            super().__init__(*args, **kwargs)
            self.reload_min_segundos = float(reload_min_segundos)
            self._ultimo_fechamento_ts: pd.Timestamp | None = None

        def on_session_start(self, session_date) -> None:
            super().on_session_start(session_date)
            self._ultimo_fechamento_ts = None

        def on_bar(self, ts, bar, positions, session_pnl_brl):
            if not positions and self._state.open_side is not None:
                # Esta chamada vai processar o fechamento que aconteceu entre
                # a barra anterior e esta (a classe-mae ainda vai rodar a
                # contabilidade `open_side -> None` dentro de `super().
                # on_bar` abaixo) -- grava ANTES de delegar, para o gate de
                # `_pode_armar_apos_recusa` ja' enxergar o carimbo na MESMA
                # chamada, que e' exatamente onde o rearme sem atraso
                # aconteceria.
                self._ultimo_fechamento_ts = ts
            return super().on_bar(ts, bar, positions, session_pnl_brl)

        def _pode_armar_apos_recusa(self, bar, state) -> bool:
            if not super()._pode_armar_apos_recusa(bar, state):
                return False
            if self.reload_min_segundos <= 0 or self._ultimo_fechamento_ts is None:
                return True
            espera = (bar.ts - self._ultimo_fechamento_ts).total_seconds()
            return espera >= self.reload_min_segundos

    return WdoGridReloadMakerComAtrasoDeReload


# ------------------------------------------------------------------- worker
def _roda_celula(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot

    dia = spec["dia"]
    atraso = spec["atraso"]
    caminho = _bars_path(dia)
    bars = pd.read_parquet(caminho)
    if bars.empty:
        return {"spec": spec, "erro": "bars vazio"}

    Cls = construir_classe_com_atraso()
    robo = get_daytrade_robot("wdo_grid_reload_maker")
    params = [p for p in inspect.signature(WdoGridReloadMaker.__init__).parameters if p != "self"]
    kwargs = {p: getattr(robo, p) for p in params}
    strat = Cls(reload_min_segundos=atraso, **kwargs)

    _contador = {"recusas": 0}
    _on_rejected_original = strat.on_order_rejected

    def _on_order_rejected_contado(ts, _orig=_on_rejected_original, _c=_contador):
        _c["recusas"] += 1
        return _orig(ts)

    strat.on_order_rejected = _on_order_rejected_contado

    cfg = config_for(
        profile_for(SYMBOL),
        trade_tick_value=0.01, trade_tick_size=0.001,
        initial_capital=CAPITAL_REAL_BRL,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )
    res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    equity = res.equity_curve
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    perdas = [t.pnl_brl for t in trades if t.pnl_brl < 0]
    return {
        "spec": {"dia": dia.isoformat(), "atraso": atraso},
        "n": len(trades),
        "n_ganhos": len(ganhos),
        "n_perdas": len(perdas),
        "soma_ganhos": sum(ganhos),
        "soma_perdas": sum(perdas),
        "pnl": sum(t.pnl_brl for t in trades),
        "maxdd_brl": _maxdd(equity),
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "recusas_capital": _contador["recusas"],
        "fila_entrada_qty": float(getattr(res, "fila_entrada_qty", 0.0) or 0.0),
        "fila_saida_qty": float(getattr(res, "fila_saida_qty", 0.0) or 0.0),
        "deslize_alvo_ticks": float(getattr(res, "deslize_alvo_ticks", 0.0) or 0.0),
    }


def _maxdd(equity: pd.Series) -> float:
    if equity is None or equity.empty:
        return 0.0
    pico = equity.cummax()
    return float((pico - equity).max())


# ------------------------------------------------------------------- agregacao
def _resumir(cels: list[dict]) -> dict:
    n = sum(c["n"] for c in cels)
    n_ganhos = sum(c["n_ganhos"] for c in cels)
    n_perdas = sum(c["n_perdas"] for c in cels)
    soma_ganhos = sum(c["soma_ganhos"] for c in cels)
    soma_perdas = sum(c["soma_perdas"] for c in cels)
    liquido_total = sum(c["pnl"] for c in cels)
    maxdd_total = max((c["maxdd_brl"] for c in cels), default=0.0)
    n_dias = len(cels)
    n_pos = sum(1 for c in cels if c["pnl"] > 0)
    n_neg = sum(1 for c in cels if c["pnl"] < 0)
    n_cens = sum(1 for c in cels if c["recusas_capital"] > 0)
    caixa_min = min((c["caixa_min"] for c in cels), default=float("nan"))
    ganho_medio = soma_ganhos / n_ganhos if n_ganhos else float("nan")
    perda_media = abs(soma_perdas / n_perdas) if n_perdas else float("nan")
    be_emp = (100.0 * perda_media / (ganho_medio + perda_media)
              if n_ganhos and n_perdas else float("nan"))
    win = 100.0 * n_ganhos / n if n else float("nan")
    lo, hi = ic_wilson(n_ganhos, n)
    if n == 0 or math.isnan(be_emp):
        veredito = "sem dado"
    elif hi < be_emp:
        veredito = "NEGATIVA"
    elif lo > be_emp:
        veredito = "POSITIVA"
    else:
        veredito = "indefinido"
    liq_preg = liquido_total / n_dias if n_dias else float("nan")
    trd_preg = n / n_dias if n_dias else float("nan")
    return dict(n=n, n_ganhos=n_ganhos, n_perdas=n_perdas, win=win,
                ganho_medio=ganho_medio, perda_media=perda_media, be_emp=be_emp,
                lo=lo, hi=hi, veredito=veredito, liquido_total=liquido_total,
                liq_preg=liq_preg, trd_preg=trd_preg, n_pos=n_pos, n_neg=n_neg,
                n_cens=n_cens, n_dias=n_dias, maxdd_total=maxdd_total,
                caixa_min=caixa_min)


def _imprime_tabela(titulo: str, resumo: dict, valores: list[float]) -> None:
    print("=" * 150)
    print(titulo)
    print("=" * 150)
    cab = (f"{'atraso(s)':<10}{'n':>6}{'win%':>8}{'ganho_med':>11}{'perda_med':>11}"
           f"{'BE emp.':>9}{'IC95 win%':>18}{'veredito':>12}{'liq. total':>13}"
           f"{'liq/preg':>11}{'trd/preg':>9}{'MaxDD R$':>11}{'caixa min':>11}"
           f"{'preg +':>7}{'preg -':>7}{'preg cens.':>11}{'pregoes':>9}")
    print(cab)
    print("-" * len(cab))
    for v in valores:
        r = resumo[v]
        ic_txt = f"[{r['lo']:.2f};{r['hi']:.2f}]"
        print(f"{v:<10.1f}{r['n']:>6}{r['win']:>7.2f}%{r['ganho_medio']:>11.2f}"
              f"{r['perda_media']:>11.2f}{r['be_emp']:>8.2f}%"
              f"{ic_txt:>18}{r['veredito']:>12}"
              f"{r['liquido_total']:>13.2f}{r['liq_preg']:>11.2f}{r['trd_preg']:>9.1f}"
              f"{r['maxdd_total']:>11.2f}{r['caixa_min']:>11.2f}"
              f"{r['n_pos']:>7}{r['n_neg']:>7}{r['n_cens']:>11}{r['n_dias']:>9}")
    print("-" * len(cab))


def main() -> None:
    t_inicio = time.perf_counter()

    if not TICK_PARQUET_LOCAL.exists():
        raise SystemExit(f"[erro] nao encontrei {TICK_PARQUET_LOCAL}")

    print(f"[dado] carregando lista de pregoes de {TICK_PARQUET_LOCAL} ...", flush=True)
    ticks_meta = pd.read_parquet(TICK_PARQUET_LOCAL, columns=["last"])
    dias_locais = sorted(set(ticks_meta.index.date))
    del ticks_meta
    dias_extras = [d for d in (date(2026, 9, 8), date(2026, 9, 9))
                   if _bars_path(d).exists()]
    dias_todos = sorted(set(dias_locais) | set(dias_extras))
    print(f"[dado] {len(dias_locais)} pregoes no parquet canonico local "
          f"({dias_locais[0]} .. {dias_locais[-1]}) + {len(dias_extras)} pregoes "
          f"ja cacheados ({[d.isoformat() for d in dias_extras]}) = "
          f"{len(dias_todos)} pregoes reais totais.\n", flush=True)

    n = len(dias_todos)
    corte = round(n * 2 / 3)
    IS_DIAS = dias_todos[:corte]
    OOS_DIAS = dias_todos[corte:]
    print(f"[split] IS  = {IS_DIAS[0]} .. {IS_DIAS[-1]}  ({len(IS_DIAS)} pregoes)")
    print(f"[split] OOS = {OOS_DIAS[0]} .. {OOS_DIAS[-1]}  ({len(OOS_DIAS)} pregoes)\n", flush=True)

    preparar_cache_de_barras(dias_todos)

    # -------------------------------------------------------------- IS
    specs_is = [{"dia": d, "atraso": a} for d in IS_DIAS for a in VALORES_IS]
    print(f"[IS] {len(specs_is)} celulas ({len(VALORES_IS)} valores de atraso x "
          f"{len(IS_DIAS)} pregoes), motor de producao, capital R${CAPITAL_REAL_BRL:.0f}/"
          f"pregao NUNCA reposto, fila calibrada, sem prazo\n", flush=True)

    resultados_is: list[dict] = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs_is}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            resultados_is.append(r)
            s = r["spec"]
            if "erro" in r:
                print(f"  [{feitos}/{len(specs_is)}] {s['dia']} atraso={s['atraso']}s: ERRO {r['erro']}", flush=True)
            else:
                print(f"  [{feitos}/{len(specs_is)}] {s['dia']} atraso={s['atraso']:>5.1f}s  "
                      f"n={r['n']:>4}  pnl=R${r['pnl']:>9.2f}  caixa_min=R${r['caixa_min']:>7.2f}  "
                      f"recusas={r['recusas_capital']}", flush=True)

    print(f"\n[IS] {len(resultados_is)} celulas em "
          f"{(time.perf_counter()-t_inicio)/60:.1f} min\n", flush=True)

    por_atraso_is: dict[float, list[dict]] = {a: [] for a in VALORES_IS}
    for r in resultados_is:
        if "erro" not in r:
            por_atraso_is[r["spec"]["atraso"]].append(r)

    resumo_is = {a: _resumir(cels) for a, cels in por_atraso_is.items()}
    _imprime_tabela("RESULTADO IS -- varredura de reload_min_segundos (0=controle/baseline)",
                     resumo_is, VALORES_IS)

    print("\nLEITURA:")
    print(" - BE emp. = perda_media/(ganho_medio+perda_media), nulo EMPIRICO de cada celula.")
    print(" - IC95 win% e' Wilson sobre n_ganhos/n pooled dentro de cada valor de atraso.")
    print(" - veredito POSITIVA exige IC95 inteiro ACIMA do BE empirico.")
    print(" - 'preg cens.' = pregoes com >=1 recusa de capital (portao de R$375, nao geometria).")
    fila_ent = next((c["fila_entrada_qty"] for cels in por_atraso_is.values() for c in cels), 0.0)
    fila_sai = next((c["fila_saida_qty"] for cels in por_atraso_is.values() for c in cels), 0.0)
    print(f" - fila calibrada usada: entrada={fila_ent:.0f} / saida={fila_sai:.0f} "
          f"(backtest.intraday.fidelidade, herdada de config_for)")

    # ------------------------------------------------- escolha do candidato
    candidatos = []
    for a in VALORES_IS:
        r = resumo_is[a]
        censura_ok = r["n_cens"] <= 0.1 * r["n_dias"]  # <=10% dos pregoes censurados
        if (r["veredito"] == "POSITIVA" and r["liquido_total"] > 0 and censura_ok):
            candidatos.append(a)

    print(f"\n[decisao] candidatos que passam (POSITIVA + liquido>0 + censura<=10% no IS): "
          f"{candidatos if candidatos else 'NENHUM'}", flush=True)

    if not candidatos:
        print("\n[VEREDITO] Nenhum valor de reload_min_segundos produziu IC95% do win% "
              "inteiramente acima do breakeven empirico com liquido positivo e censura "
              "controlada no IS. Hipotese 13 (atraso de cadencia no rearme pos-fechamento) "
              "e' REFUTADA/NULA pelo mesmo criterio das 12 anteriores -- OOS NAO sera' "
              "rodado (disciplina de nao gastar o teste cego sem candidato do IS).")
        print(f"\n[fim] tempo total {(time.perf_counter()-t_inicio)/60:.1f} min", flush=True)
        return

    # Disciplina anti multiple-comparison: escolhe 1 so' candidato (o de
    # maior liquido total dentre os que passaram) para confirmar no OOS --
    # mesmo espirito do combo_T3 (so' o limiar/variante ja ESCOLHIDO no IS
    # gasta o teste cego).
    escolhido = max(candidatos, key=lambda a: resumo_is[a]["liquido_total"])
    print(f"[decisao] candidato UNICO escolhido para confirmacao OOS: "
          f"reload_min_segundos={escolhido}s (maior liquido total entre os aprovados)\n", flush=True)

    specs_oos = [{"dia": d, "atraso": a} for d in OOS_DIAS for a in (0.0, escolhido)]
    print(f"[OOS] {len(specs_oos)} celulas (baseline 0s + candidato {escolhido}s x "
          f"{len(OOS_DIAS)} pregoes)\n", flush=True)

    resultados_oos: list[dict] = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs_oos}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            resultados_oos.append(r)
            s = r["spec"]
            if "erro" in r:
                print(f"  [{feitos}/{len(specs_oos)}] {s['dia']} atraso={s['atraso']}s: ERRO {r['erro']}", flush=True)
            else:
                print(f"  [{feitos}/{len(specs_oos)}] {s['dia']} atraso={s['atraso']:>5.1f}s  "
                      f"n={r['n']:>4}  pnl=R${r['pnl']:>9.2f}  caixa_min=R${r['caixa_min']:>7.2f}  "
                      f"recusas={r['recusas_capital']}", flush=True)

    por_atraso_oos: dict[float, list[dict]] = {0.0: [], escolhido: []}
    for r in resultados_oos:
        if "erro" not in r:
            por_atraso_oos[r["spec"]["atraso"]].append(r)
    resumo_oos = {a: _resumir(cels) for a, cels in por_atraso_oos.items()}
    _imprime_tabela(f"RESULTADO OOS -- confirmacao do candidato {escolhido}s vs baseline 0s",
                     resumo_oos, [0.0, escolhido])

    print(f"\n[fim] tempo total {(time.perf_counter()-t_inicio)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
