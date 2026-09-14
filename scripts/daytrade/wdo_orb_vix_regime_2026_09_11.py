"""HIPOTESE (2o lote de brainstorm, 2026-09-11): "Regime de Volatilidade
VIX-T1 na geometria do WDO@" -- no checkpoint pre-sessao, ler o VIX de
FECHAMENTO de T-1 (EOD, zero look-ahead), classificar ALTO/BAIXO pela
mediana MOVEL de 60 pregoes do proprio VIX e, em dia ALTO, escalar alvo E
stop do `wdo_orb` (o robo de PRODUCAO hoje, unico TOP-1 vivo do WDO@) por um
multiplicador comum -- mantendo a razao alvo:stop fixa (2:1, `alvo_multiplo`
nunca muda) -- travando o teto em 1 contrato (que ja' e' o default fixo do
robo, entao esse pedaco do mecanismo e' NO-OP aqui, ver a nota abaixo). Em
dia BAIXO, geometria de producao inalterada.

DADO DISPONIVEL NO REPO (achado ANTES de escrever qualquer linha de
estrategia, porque se nao existisse o veredito seria INVIAVEL na hora):
`data/raw/_VIX.parquet` (OHLC diario do VIX, CBOE, 2010-01-04 a 2026-08-14).
NAO ha' nenhum uso deste arquivo em `src/` -- e' dado baixado e nunca
conectado a nenhuma estrategia. Boa noticia: existe, cobre TODO o IS do
WDO F1/wdo_orb (2026-02-27..2026-06-12) e quase todo o OOS
(2026-06-15..2026-08-25, exceto os ultimos ~5-7 pregoes). Ma noticia: a
serie PARA em 2026-08-14 -- nao ha' VIX mais recente que isso no repo, entao
os pregoes de 2026-08-19 em diante (gap > 4 dias corridos ate' o ultimo
fechamento do VIX disponivel) ficam FORA do teste por falta de dado real
(nunca preenchidos com stale/proxy). Ver `_classificar_regime` e o print de
cobertura no `main()`.

MECANICA DE CLASSIFICACAO (zero look-ahead): para a sessao B3 de dia D, pega
o ULTIMO fechamento do VIX estritamente ANTERIOR a D (US fecha ~17-18h BRT
do dia anterior, disponivel MUITO antes do checkpoint das 08:55 BRT); compara
contra a mediana movel de 60 pregoes do PROPRIO VIX terminando nesse mesmo
fechamento (`pandas.Series.rolling(60, min_periods=60).median()`, sem
`shift` para frente -- o valor no indice T-1 ja' usa so' T-61..T-1). ALTO se
o fechamento > mediana; BAIXO caso contrario ou empate.

ROBO BASE: `strategy.daytrade.lab.wdo_orb.WdoOrb` com os defaults de CLASSE
(que SAO a producao -- `wdo_orb` nao aparece no registry.py com kwargs
proprios, ver o comentario la' dentro). `WdoOrbVixRegime` (definida abaixo,
SO' neste script -- nada em `strategy/` e' tocado) subclassa e sobrescreve
so' `_geometria()`: chama a formula original (faixa medida, clamp
min/max, alvo = stop*2) e, se o regime do dia for ALTO, multiplica os dois
resultados pelo MESMO fator -- a razao 2:1 nunca muda, entao o breakeven
TEORICO (stop/(stop+alvo) = 1/3 = 33,3%) tambem nao muda com o regime; o que
pode mudar e' o breakeven EMPIRICO (a corretagem fixa de R$0,50 pesa menos
sobre um stop maior) e a taxa de PREENCHIMENTO da limite mais distante.

NO-OP DECLARADO: "travar o teto em 1 contrato" ja' e' o comportamento do
`wdo_orb` em QUALQUER regime (`quantity: int = 1`, fixo, nao escala com
caixa -- ver a docstring da classe). Este pedaco do mecanismo da hipotese
nao muda nada aqui porque a producao ja' opera assim; reportado por
transparencia, nao e' um resultado.

DESENHO DE EXECUCAO: herdado sem alteracao do `WdoOrb` (entrada EnterLimit
com prazo, alvo fatiado sem prazo, `anchor_exits_at_fill=True`, stop a
mercado -- CLAUDE.md, "O desenho de execucao e' FECHADO"). Fila calibrada de
`backtest.intraday.fidelidade` (WDO@, 329/494 em 2026-09-11) herdada
automaticamente por `config_for`, NUNCA digitada na mao.

CAPITAL: R$375,00 (piso real do WDO@, margem R$150 x buffer 2,0 x reserva
1,25 -- CLAUDE.md), REPOSTO por pregao para isolar GEOMETRIA de RUINA (mesmo
padrao usado em `wdof1_familia_maker_encerrada_fila_2026_09_10` e nos scripts
irmaos de 2026-09-11) -- e uma caminhada de caixa CONTINUA (sem reposicao,
cronologica) e' calculada A PARTE, so' para o candidato final, como checagem
de sobrevivencia (ver `_caminhada_de_caixa`).

METODO: teste PEQUENO primeiro (20 primeiros pregoes do IS, 3 multiplicadores
candidatos {1.3, 1.5, 2.0}) antes de gastar a janela inteira -- "o minimo que
refuta primeiro" (convencao do projeto). So' expande para os 118 pregoes
validos (IS 72 + OOS truncado em 46, gap<=4 dias) se algum multiplicador
separar do controle no teste pequeno.
"""
from __future__ import annotations

import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
VIX_PARQUET = RAIZ / "data" / "raw" / "_VIX.parquet"
WDO_TICK_PARQUET = RAIZ / "data" / "raw_ticks" / "WDO_A_f1.parquet"
CACHE_DIR = (
    Path(r"C:\Users\Jeffe\AppData\Local\Temp\claude\c--Users-Jeffe-Documents-study-meta"
         r"\6ef1c650-f5e7-4b9e-8e69-7a1572bcec94\scratchpad\wdo_orb_vix_days")
)
GAP_MAXIMO_DIAS = 4  # acima disso o VIX disponivel esta' STALE demais para ser "T-1"
JANELA_MEDIANA = 60
MULTIPLICADORES_TESTE_PEQUENO = [1.3, 1.5, 2.0]
N_DIAS_TESTE_PEQUENO = 20


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


# ------------------------------------------------------- regime de VIX -----
def carregar_regime_vix() -> tuple[dict[date, str], pd.Series, pd.Series]:
    """Devolve {data_sessao_B3: "ALTO"|"BAIXO"} SO' para sessoes com VIX de
    T-1 disponivel com gap <= GAP_MAXIMO_DIAS corridos (zero look-ahead:
    so' usa fechamento estritamente anterior a' sessao). Sessoes fora dessa
    janela (VIX stale ou inexistente) simplesmente NAO entram no dict --
    quem usa precisa decidir explicitamente o que fazer com a ausencia
    (aqui: excluir do teste, nunca herdar um regime velho em silencio)."""
    vix = pd.read_parquet(VIX_PARQUET)
    close = vix["close"].sort_index()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    mediana60 = close.rolling(JANELA_MEDIANA, min_periods=JANELA_MEDIANA).median()

    wdo_dias = sorted(pd.to_datetime(
        pd.read_parquet(WDO_TICK_PARQUET, columns=["dia"])["dia"].unique()
    ))

    regime: dict[date, str] = {}
    linhas = []
    for d in wdo_dias:
        pos = close.index.searchsorted(d, side="left")
        if pos == 0:
            linhas.append((d.date(), None, None))
            continue
        last_vix_date = close.index[pos - 1]
        gap_dias = (d - last_vix_date).days
        m = mediana60.iloc[pos - 1]
        if pd.isna(m) or gap_dias > GAP_MAXIMO_DIAS:
            linhas.append((d.date(), None, gap_dias))
            continue
        c = close.iloc[pos - 1]
        r = "ALTO" if c > m else "BAIXO"
        regime[d.date()] = r
        linhas.append((d.date(), r, gap_dias))

    cobertura = pd.DataFrame(linhas, columns=["dia", "regime", "gap_dias"])
    return regime, cobertura, close


# ------------------------------------------------------- cache por pregao --
def _dia_path(d: date) -> Path:
    return CACHE_DIR / f"{d.isoformat()}.parquet"


def preparar_cache(dias: list[date]) -> None:
    faltando = {d for d in dias if not _dia_path(d).exists()}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not faltando:
        print(f"[cache] {len(dias)} pregoes ja cacheados.", flush=True)
        return
    print(f"[cache] fatiando {len(faltando)} pregoes de {WDO_TICK_PARQUET.name} ...",
          flush=True)
    cols = ["open", "high", "low", "close", "volume"]
    df = pd.read_parquet(WDO_TICK_PARQUET, columns=cols + ["dia"])
    convertidos = 0
    for d, sub in df.groupby(df["dia"]):
        dd = pd.Timestamp(d).date()
        if dd not in faltando or sub.empty:
            continue
        sub[cols].to_parquet(_dia_path(dd))
        convertidos += 1
    del df
    print(f"[cache] {convertidos}/{len(faltando)} pregoes gravados em {CACHE_DIR}",
          flush=True)


# ------------------------------------------------------- robo do experimento
def _construir_robo(vix_regime_by_date: dict[date, str] | None, alto_escala: float):
    """Fabrica: `WdoOrb` (controle) ou a subclasse `_WdoOrbVixRegime` definida
    AQUI DENTRO (nao no modulo, nao em `strategy/`) -- reimportada a cada
    chamada porque o worker roda em processo FILHO (`ProcessPoolExecutor`)."""
    from strategy.daytrade.lab.wdo_orb import WdoOrb

    @dataclass
    class _WdoOrbVixRegime(WdoOrb):
        name: str = "wdo_orb_vix_regime"
        vix_regime_by_date: dict = field(default_factory=dict, repr=False)
        alto_escala: float = 1.5
        _regime_hoje: str = field(default="BAIXO", init=False, repr=False)

        def on_session_start(self, session_date) -> None:
            super().on_session_start(session_date)
            d = session_date if isinstance(session_date, date) else pd.Timestamp(session_date).date()
            self._regime_hoje = self.vix_regime_by_date.get(d, "BAIXO")

        def _geometria(self) -> tuple[int, int]:
            stop_ticks, alvo_ticks = super()._geometria()
            if self._regime_hoje == "ALTO":
                stop_ticks = int(round(stop_ticks * self.alto_escala))
                alvo_ticks = int(round(alvo_ticks * self.alto_escala))
            return stop_ticks, alvo_ticks

    if vix_regime_by_date is None:
        return WdoOrb()
    return _WdoOrbVixRegime(vix_regime_by_date=vix_regime_by_date, alto_escala=alto_escala)


# ------------------------------------------------------------------- worker
def _roda_celula(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for

    dia: date = spec["dia"]
    variante = spec["variante"]  # "controle" ou multiplicador (float)
    regime_dict = spec["regime_dict"]
    regime_do_dia = spec["regime_do_dia"]

    caminho = _dia_path(dia)
    bars = pd.read_parquet(caminho)
    if bars.empty:
        return {"spec": spec, "erro": "bars vazio"}

    if variante == "controle":
        strat = _construir_robo(None, 1.0)
    else:
        strat = _construir_robo(regime_dict, float(variante))

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
    n_stops = sum(1 for t in trades if t.exit_reason == "stop")
    return {
        "spec": {"dia": dia.isoformat(), "variante": str(variante), "regime": regime_do_dia},
        "n": len(trades),
        "n_ganhos": len(ganhos),
        "n_perdas": len(perdas),
        "n_stops": n_stops,
        "soma_ganhos": sum(ganhos),
        "soma_perdas": sum(perdas),
        "pnl": sum(t.pnl_brl for t in trades),
        "maxdd_brl": _maxdd(equity),
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "trade_pnls": [(str(t.exit_ts), t.pnl_brl) for t in trades],
    }


def _maxdd(equity: pd.Series) -> float:
    if equity is None or equity.empty:
        return 0.0
    pico = equity.cummax()
    return float((pico - equity).max())


# ------------------------------------------------------------------ resumo
def _resumir(cels: list[dict]) -> dict:
    n = sum(c["n"] for c in cels)
    n_ganhos = sum(c["n_ganhos"] for c in cels)
    n_perdas = sum(c["n_perdas"] for c in cels)
    n_stops = sum(c["n_stops"] for c in cels)
    soma_ganhos = sum(c["soma_ganhos"] for c in cels)
    soma_perdas = sum(c["soma_perdas"] for c in cels)
    liquido_total = sum(c["pnl"] for c in cels)
    maxdd_total = max((c["maxdd_brl"] for c in cels), default=0.0)
    n_dias = len(cels)
    n_pos = sum(1 for c in cels if c["pnl"] > 0)
    n_neg = sum(1 for c in cels if c["pnl"] < 0)
    n_zero = sum(1 for c in cels if c["n"] == 0)
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
        veredito = "INDEFINIDA"
    return dict(n=n, n_ganhos=n_ganhos, n_perdas=n_perdas, n_stops=n_stops, win=win,
                ganho_medio=ganho_medio, perda_media=perda_media, be_emp=be_emp,
                lo=lo, hi=hi, veredito=veredito, liquido_total=liquido_total,
                n_pos=n_pos, n_neg=n_neg, n_zero=n_zero, n_dias=n_dias,
                maxdd_total=maxdd_total, caixa_min=caixa_min,
                maxdd_pct=(100.0 * maxdd_total / CAPITAL_REAL_BRL),
                pct_dias_pos=(100.0 * n_pos / n_dias if n_dias else float("nan")))


def _imprime_linha(rotulo: str, r: dict) -> None:
    ic_txt = f"[{r['lo']:.2f};{r['hi']:.2f}]" if not math.isnan(r["lo"]) else "[--]"
    print(f"{rotulo:<16}{r['n']:>6}{r['n_stops']:>7}{r['win']:>8.2f}%"
          f"{r['be_emp']:>9.2f}%{ic_txt:>16}{r['veredito']:>12}"
          f"{r['liquido_total']:>13.2f}{r['maxdd_total']:>11.2f}{r['maxdd_pct']:>8.1f}%"
          f"{r['caixa_min']:>11.2f}{r['pct_dias_pos']:>9.1f}%"
          f"{r['n_pos']:>7}{r['n_zero']:>7}{r['n_dias']:>9}")


def _cabecalho() -> None:
    cab = (f"{'variante':<16}{'n':>6}{'stops':>7}{'win%':>9}{'BE emp.':>10}"
           f"{'IC95 win%':>16}{'veredito':>12}{'liq. R$':>13}{'MaxDD R$':>11}{'MaxDD %':>9}"
           f"{'caixa min':>11}{'dias +%':>10}{'dias+':>7}{'dias 0':>7}{'pregoes':>9}")
    print(cab)
    print("-" * len(cab))


def _caminhada_de_caixa(cels: list[dict], capital_inicial: float) -> tuple[float, float, bool]:
    """Caminhada CRONOLOGICA continua de caixa (sem repor por pregao) --
    checagem de SOBREVIVENCIA a parte do liquido isolado por geometria.
    Devolve (caixa_minimo_atingido, caixa_final, travou_abaixo_da_margem)."""
    todos_trades = []
    for c in cels:
        todos_trades.extend(c.get("trade_pnls", []))
    todos_trades.sort(key=lambda x: x[0])
    caixa = capital_inicial
    minimo = capital_inicial
    for _, pnl in todos_trades:
        caixa += pnl
        minimo = min(minimo, caixa)
    margem_wdo = 150.0
    return minimo, caixa, minimo < margem_wdo


def main() -> None:
    t0 = time.perf_counter()

    if not VIX_PARQUET.exists():
        print(f"[VEREDITO] INVIAVEL -- dado necessario ausente: {VIX_PARQUET} nao existe. "
              f"Seria preciso obter serie diaria do VIX (CBOE, EOD) cobrindo o periodo de "
              f"teste antes de prosseguir.")
        return
    if not WDO_TICK_PARQUET.exists():
        raise SystemExit(f"[erro] nao encontrei {WDO_TICK_PARQUET}")

    print(f"[dado] VIX: {VIX_PARQUET}")
    print(f"[dado] WDO tick (IS+OOS congelados): {WDO_TICK_PARQUET}\n")

    regime_dict, cobertura, vix_close = carregar_regime_vix()
    total = len(cobertura)
    validos = cobertura["regime"].notna().sum()
    excluidos = cobertura[cobertura["regime"].isna()]
    print(f"[VIX] serie de {vix_close.index.min().date()} a {vix_close.index.max().date()} "
          f"({len(vix_close)} pregoes de VIX).")
    print(f"[VIX] {validos}/{total} pregoes do WDO com regime valido "
          f"(gap<=<{GAP_MAXIMO_DIAS+1} dias corridos ate' o ultimo fechamento do VIX).")
    if len(excluidos):
        print(f"[VIX] EXCLUIDOS por VIX stale/ausente ({len(excluidos)}): "
              f"{excluidos['dia'].min()} .. {excluidos['dia'].max()} -- "
              f"LIMITACAO DECLARADA: o repo nao tem VIX mais recente que "
              f"{vix_close.index.max().date()}; estes pregoes ficam FORA de todo teste "
              f"abaixo (nunca preenchidos com dado stale).")
    contagem_regime = pd.Series(regime_dict).value_counts()
    print(f"[VIX] distribuicao nos dias validos: {dict(contagem_regime)}\n", flush=True)

    dias_validos = sorted(regime_dict.keys())
    dias_is_validos = [d for d in dias_validos if d <= date(2026, 6, 12)]
    dias_oos_validos = [d for d in dias_validos if d >= date(2026, 6, 15)]
    print(f"[janela] IS valido: {len(dias_is_validos)} pregoes "
          f"({dias_is_validos[0]}..{dias_is_validos[-1]})")
    print(f"[janela] OOS valido (truncado pela cobertura de VIX): {len(dias_oos_validos)} pregoes "
          f"({dias_oos_validos[0]}..{dias_oos_validos[-1]})\n", flush=True)

    # ===================================================== FASE 1: TESTE PEQUENO
    dias_teste = dias_is_validos[:N_DIAS_TESTE_PEQUENO]
    print(f"[FASE 1 -- teste pequeno] {len(dias_teste)} primeiros pregoes validos do IS "
          f"({dias_teste[0]}..{dias_teste[-1]}), controle + multiplicadores "
          f"{MULTIPLICADORES_TESTE_PEQUENO}\n", flush=True)

    preparar_cache(dias_teste)

    variantes_fase1 = ["controle"] + MULTIPLICADORES_TESTE_PEQUENO
    specs = [{"dia": d, "variante": v, "regime_dict": regime_dict, "regime_do_dia": regime_dict[d]}
              for d in dias_teste for v in variantes_fase1]

    resultados: list[dict] = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            resultados.append(r)
            s = r["spec"]
            if "erro" in r:
                print(f"  [{feitos}/{len(specs)}] {s['dia']} var={s['variante']}: ERRO {r['erro']}", flush=True)
            else:
                print(f"  [{feitos}/{len(specs)}] {s['dia']} var={s['variante']:>9} "
                      f"regime={s['regime']:<6} n={r['n']:>2} pnl=R${r['pnl']:>9.2f}", flush=True)

    por_variante: dict[str, list[dict]] = {v: [] for v in variantes_fase1}
    for r in resultados:
        if "erro" not in r:
            por_variante[r["spec"]["variante"] if r["spec"]["variante"] == "controle"
                         else float(r["spec"]["variante"])].append(r)

    print(f"\n{'='*140}")
    print(f"RESULTADO FASE 1 -- teste pequeno ({len(dias_teste)} pregoes IS), capital "
          f"R${CAPITAL_REAL_BRL:.0f}/pregao REPOSTO (isola geometria)")
    print("=" * 140)
    _cabecalho()
    resumo_fase1 = {}
    for v in variantes_fase1:
        r = _resumir(por_variante[v])
        resumo_fase1[v] = r
        rotulo = "controle" if v == "controle" else f"M={v}"
        _imprime_linha(rotulo, r)
    print("-" * 140)
    r_ctrl1 = resumo_fase1["controle"]
    print(f"\n[controle] liquido R${r_ctrl1['liquido_total']:.2f}, win% {r_ctrl1['win']:.2f}%, "
          f"BE emp. {r_ctrl1['be_emp']:.2f}%, {r_ctrl1['n_zero']}/{r_ctrl1['n_dias']} pregoes sem trade\n")

    candidatos = []
    for v in MULTIPLICADORES_TESTE_PEQUENO:
        r = resumo_fase1[v]
        if r["n"] == 0:
            continue
        if r["liquido_total"] > r_ctrl1["liquido_total"] and r["maxdd_total"] <= r_ctrl1["maxdd_total"] * 1.5:
            candidatos.append(v)

    print(f"[decisao fase 1] candidatos que batem o controle em liquido (sem piorar MaxDD "
          f">50%): {candidatos if candidatos else 'NENHUM'}\n", flush=True)

    if not candidatos:
        print("[VEREDITO PARCIAL] Nenhum multiplicador testado no teste pequeno melhora o "
              "controle. Nao expande para a janela completa (disciplina: teste pequeno "
              "refuta primeiro, sem gastar tempo de maquina numa janela maior sem sinal).")
        _resumo_final(resumo_fase1, r_ctrl1, escolhido=None, cels_ctrl=por_variante["controle"],
                      cels_cand=None, t0=t0, fase="1 (pequena, 20 pregoes IS)")
        return

    escolhido = max(candidatos, key=lambda v: resumo_fase1[v]["liquido_total"])
    print(f"[decisao fase 1] candidato escolhido para a janela completa: M={escolhido}\n", flush=True)

    # ===================================================== FASE 2: JANELA COMPLETA
    dias_completos = dias_is_validos + dias_oos_validos
    print(f"[FASE 2 -- janela completa] {len(dias_completos)} pregoes validos "
          f"(IS {len(dias_is_validos)} + OOS truncado {len(dias_oos_validos)}), "
          f"controle vs M={escolhido}\n", flush=True)

    preparar_cache(dias_completos)

    variantes_fase2 = ["controle", escolhido]
    specs2 = [{"dia": d, "variante": v, "regime_dict": regime_dict, "regime_do_dia": regime_dict[d]}
               for d in dias_completos for v in variantes_fase2]

    resultados2: list[dict] = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs2}
        feitos = 0
        for fut in as_completed(futuros):
            r = fut.result()
            feitos += 1
            resultados2.append(r)
            if feitos % 20 == 0 or feitos == len(specs2):
                print(f"  [{feitos}/{len(specs2)}] concluidos ...", flush=True)

    por_variante2: dict = {v: [] for v in variantes_fase2}
    por_variante2_is: dict = {v: [] for v in variantes_fase2}
    por_variante2_oos: dict = {v: [] for v in variantes_fase2}
    for r in resultados2:
        if "erro" in r:
            continue
        v = r["spec"]["variante"] if r["spec"]["variante"] == "controle" else float(r["spec"]["variante"])
        por_variante2[v].append(r)
        d = date.fromisoformat(r["spec"]["dia"])
        (por_variante2_is if d <= date(2026, 6, 12) else por_variante2_oos)[v].append(r)

    print(f"\n{'='*140}")
    print(f"RESULTADO FASE 2 -- janela completa ({len(dias_completos)} pregoes), capital "
          f"R${CAPITAL_REAL_BRL:.0f}/pregao REPOSTO")
    print("=" * 140)
    _cabecalho()
    resumo_fase2 = {}
    for v in variantes_fase2:
        r = _resumir(por_variante2[v])
        resumo_fase2[v] = r
        rotulo = "controle" if v == "controle" else f"M={v}"
        _imprime_linha(rotulo, r)
    print("-" * 140)

    print(f"\n-- quebra IS ({len(dias_is_validos)} pregoes) --")
    _cabecalho()
    for v in variantes_fase2:
        r = _resumir(por_variante2_is[v])
        rotulo = "controle" if v == "controle" else f"M={v}"
        _imprime_linha(rotulo, r)

    print(f"\n-- quebra OOS truncado ({len(dias_oos_validos)} pregoes) --")
    _cabecalho()
    for v in variantes_fase2:
        r = _resumir(por_variante2_oos[v])
        rotulo = "controle" if v == "controle" else f"M={v}"
        _imprime_linha(rotulo, r)

    r_ctrl2 = resumo_fase2["controle"]
    r_cand2 = resumo_fase2[escolhido]
    _resumo_final(resumo_fase2, r_ctrl2, escolhido=escolhido,
                  cels_ctrl=por_variante2["controle"], cels_cand=por_variante2[escolhido],
                  t0=t0, fase="2 (completa, IS+OOS truncado)")


def _resumo_final(resumo: dict, r_ctrl: dict, escolhido, cels_ctrl, cels_cand, t0, fase: str) -> None:
    print(f"\n{'#'*140}")
    print(f"RESUMO FINAL -- fase {fase}")
    print("#" * 140)
    print("LEITURA:")
    print(" - BE emp. = perda_media/(ganho_medio+perda_media): nulo empirico (payoff realizado).")
    print(" - BE TEORICO desta geometria (ratio 2:1, invariante ao regime) = 33,33%.")
    print(" - IC95 win% e' Wilson sobre n_ganhos/n pooled; veredito POSITIVA exige IC95 inteiro")
    print("   ACIMA do BE empirico.")
    print(" - 'dias 0' = pregoes sem NENHUM trade (o rompimento nao voltou pro offset -- ja'")
    print("   esperado, ~19% na producao; NAO e' censura de capital, e' o desenho por design).")

    caixa_min_walk, caixa_final_walk, travou = _caminhada_de_caixa(cels_ctrl, CAPITAL_REAL_BRL)
    print(f"\n[caminhada continua -- CONTROLE] caixa minimo R${caixa_min_walk:.2f}, "
          f"caixa final R${caixa_final_walk:.2f}, {'TRAVOU abaixo da margem R$150' if travou else 'nunca travou'}")
    if cels_cand is not None:
        caixa_min_c, caixa_final_c, travou_c = _caminhada_de_caixa(cels_cand, CAPITAL_REAL_BRL)
        print(f"[caminhada continua -- M={escolhido}] caixa minimo R${caixa_min_c:.2f}, "
              f"caixa final R${caixa_final_c:.2f}, {'TRAVOU abaixo da margem R$150' if travou_c else 'nunca travou'}")

    if escolhido is None:
        print(f"\n[VEREDITO FINAL] NEGATIVA/INDEFINIDA -- nenhum multiplicador de escala "
              f"VIX-ALTO melhora o controle no teste pequeno. A hipotese nao sobrevive ao "
              f"minimo que a refutaria; janela completa NAO foi gasta.")
    else:
        r_cand = resumo[escolhido]
        print(f"\n[controle]       liquido R${r_ctrl['liquido_total']:.2f}  win% {r_ctrl['win']:.2f}%  "
              f"veredito {r_ctrl['veredito']}  MaxDD R${r_ctrl['maxdd_total']:.2f}  "
              f"stops {r_ctrl['n_stops']}  dias+ {r_ctrl['pct_dias_pos']:.1f}%")
        print(f"[M={escolhido}] liquido R${r_cand['liquido_total']:.2f}  win% {r_cand['win']:.2f}%  "
              f"veredito {r_cand['veredito']}  MaxDD R${r_cand['maxdd_total']:.2f}  "
              f"stops {r_cand['n_stops']}  dias+ {r_cand['pct_dias_pos']:.1f}%")
        melhora_liquido = r_cand["liquido_total"] > r_ctrl["liquido_total"]
        nao_piora_dd = r_cand["maxdd_total"] <= r_ctrl["maxdd_total"] * 1.2
        veredito_ok = r_cand["veredito"] in ("POSITIVA",)
        if melhora_liquido and nao_piora_dd and veredito_ok:
            print(f"\n[VEREDITO FINAL] POSITIVA -- M={escolhido} bate o controle em liquido, "
                  f"nao piora MaxDD e o win% do candidato fica com IC95 inteiramente acima do "
                  f"BE empirico.")
        elif melhora_liquido:
            print(f"\n[VEREDITO FINAL] INDEFINIDA -- M={escolhido} bate o controle em liquido "
                  f"mas o veredito estatistico do win% e/ou o MaxDD nao confirmam com a "
                  f"confianca exigida (amostra pequena em regime ALTO).")
        else:
            print(f"\n[VEREDITO FINAL] NEGATIVA -- M={escolhido} nao se sustenta na janela "
                  f"completa (liquido nao superou o controle fora do teste pequeno).")

    print(f"\n[fim] tempo total {(time.perf_counter()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
