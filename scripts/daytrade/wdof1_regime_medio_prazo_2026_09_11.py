"""WDO F1 (grid maker puro): um regime de TENDENCIA de escala MEDIA (5/10/20
minutos) muda a DIRECAO do reload em vez de filtrar timing de entrada?

CONTEXTO -- por que esta rodada existe
---------------------------------------
7 hipoteses de sinal de timing em janela de SEGUNDOS (VWAP do dia, EMA local,
volume, ritmo de tick, imbalance, ATR) foram testadas contra as 6 perdas reais
de 2026-09-11 e todas falharam (5 com efeito invertido). As 6 perdas foram
todas o MESMO padrao: SELL fadando uma alta sustentada de dezenas de minutos
(13:28-14:48 UTC, ~26 pontos), ou BUY fadando uma queda equivalente -- ou
seja, o robo perde quando um movimento de escala MEDIA (minutos a dezenas de
minutos) vira tendencia real em vez de ruido que reverte. Janela de segundos
e' curta demais para enxergar isso; VWAP do dia inteiro e' longa demais.

Esta rodada testa a escala que falta: 5/10/20 minutos, com DUAS respostas
possiveis ao regime detectado (nao filtro de "nao entrar" -- mudanca de qual
LADO entra):

  (a) fade_off        -- suspende so' o lado que FADARIA a tendencia (em
                          alta, nao abre SELL; continua abrindo BUY normal).
  (b) segue_tendencia -- INVERTE: em vez de fade, forca o lado A FAVOR da
                          tendencia (pullback-buy numa alta, pullback-sell
                          numa baixa), mesmo quando a alternancia normal
                          escolheria o outro lado.

MECANICA DO ROBO BASE (por que side="short" e' o lado que fada uma ALTA): a
ancora rola para o CLOSE da barra anterior (`reanchor_mode="rolling_last_
price"`) e duas ordens ficam paradas a 1 tick dela -- BUY abaixo, SELL acima.
Numa alta sustentada o preco tende a tocar mais vezes o lado de CIMA da
ancora (que acabou de rolar pra tras), entao mais SELLs sao abertos -- e cada
um deles aposta contra um movimento que continua. O mesmo, espelhado, para
BUY numa baixa. E' exatamente o padrao das 6 perdas reais.

NAO EDITA `wdo_grid_reload_maker.py` (arquivo de producao) -- as duas
variantes sao uma SUBCLASSE que so' troca `_next_side_to_arm`, injetada via
mixin (nao uma copia dos ~1900 linhas do arquivo original: tudo o mais --
reprecificacao, histerese, capital dinamico, fatia de saida, fila -- e'
herdado sem mudanca).

MOTOR: o MESMO de producao (fila calibrada de `backtest.intraday.fidelidade`,
sem prazo de saida, `config_for`/`profile_for`, capital REAL R$375) -- NENHUM
parametro de realismo e' relaxado. Ver `LICOES_DE_PRODUCAO.md`
(wdof1-familia-maker-encerrada-fila-2026-09-10): relaxar fila foi o que gerou
os +R$239 mil de mentira que encerraram esta familia inteira por refutacao.

DADO: tick real do MT5 (`WDO@`), pregoes de 2026-09-10 e 2026-09-11 (hoje,
sessao PARCIAL -- so' o que ja' negociou). Regime calculado a partir de M1
real do MESMO terminal (`copy_rates_range`), calibrado num periodo ANTERIOR
(2026-07-13 a 2026-09-09, ~40 pregoes) para nao contaminar o veredito com o
proprio resultado que se quer medir.

HONESTIDADE DE METODO, declarada aqui para nao se perder no relatorio: com
2 dias de dado this e' DIRECAO e MAGNITUDE de efeito, nao prova de edge. Duas
simplificacoes deliberadas: (1) o filtro de regime so' se aplica a uma NOVA
entrada (apos fechamento) -- uma ordem ja pendente nao e' cancelada se o
regime mudar enquanto ela espera; (2) o limiar "tendencia forte" e' o
percentil 70 da distribuicao de |retorno| daquela escala no periodo de
CALIBRACAO (nao otimizado contra os 2 dias de teste)."""
from __future__ import annotations

import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import timezone, timedelta
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

SYMBOL = "WDO@"
CAPITAL_REAL_BRL = 375.0
CORRETAGEM_RT = 0.50

CALIBRACAO_INICIO = pd.Timestamp("2026-07-13T00:00:00Z")
CALIBRACAO_FIM = pd.Timestamp("2026-09-09T23:59:59Z")  # exclui os 2 dias de teste
DIAS_TESTE = ["2026-09-10", "2026-09-11"]
ESCALAS_MIN = (5, 10, 20)
PERCENTIL_LIMIAR = 70.0


def _limite_servidor(instant_utc):
    from core.b3_session import utc_to_server_wall_clock
    instant = pd.Timestamp(instant_utc).to_pydatetime()
    return utc_to_server_wall_clock(instant).replace(tzinfo=timezone.utc)


def ic_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100.0 * (centro - meio), 100.0 * (centro + meio))


# ------------------------------------------------------------------ regime
class RegimeLookup:
    """Callable picklable (guarda so' uma `pd.Series` de strings 'up'/'down'/
    'neutral', indexada no timestamp CLOSE-SAFE -- ver `construir_regimes`) --
    `.asof(ts)` nunca ve' NaN (todo valor e' uma string valida), entao devolve
    sempre a ultima classificacao conhecida ANTES ou EM `ts`, nunca "carrega"
    um regime antigo por cima de um neutro mais recente."""

    def __init__(self, serie: pd.Series):
        self.serie = serie

    def __call__(self, ts: pd.Timestamp) -> str | None:
        if self.serie is None or self.serie.empty:
            return None
        v = self.serie.asof(ts)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return None if v == "neutral" else v


def construir_regimes(m1: pd.DataFrame, tick_size: float) -> tuple[dict, dict]:
    """Devolve (limiares, series) -- `limiares[W]` em TICKS (percentil 70 de
    |retorno| no periodo de CALIBRACAO); `series[(dia, W)]` e' a `pd.Series`
    'up'/'down'/'neutral' daquele pregao, indexada no timestamp CLOSE-SAFE
    (open da barra + 1 minuto -- a barra so' fecha entao, e o robo so' pode
    agir DEPOIS que ela fechou, nunca antes -- ver a docstring do modulo)."""
    m1 = m1.sort_index().copy()
    m1["dia"] = m1.index.date
    limiares: dict[int, float] = {}
    retornos_por_escala: dict[int, pd.Series] = {}
    for W in ESCALAS_MIN:
        ret = m1.groupby("dia")["close"].transform(lambda s: s.diff(W)) / tick_size
        retornos_por_escala[W] = ret
        calib_mask = (m1.index >= CALIBRACAO_INICIO) & (m1.index <= CALIBRACAO_FIM)
        amostra = ret[calib_mask].dropna().abs()
        limiares[W] = float(amostra.quantile(PERCENTIL_LIMIAR / 100.0))

    series: dict[tuple, pd.Series] = {}
    for dia_str in DIAS_TESTE:
        dia = pd.Timestamp(dia_str).date()
        sub = m1[m1["dia"] == dia]
        if sub.empty:
            continue
        ts_close_safe = sub.index + pd.Timedelta(minutes=1)
        for W in ESCALAS_MIN:
            ret_dia = retornos_por_escala[W].loc[sub.index]
            limiar = limiares[W]
            rotulo = pd.Series("neutral", index=ts_close_safe)
            rotulo[ret_dia.values > limiar] = "up"
            rotulo[ret_dia.values < -limiar] = "down"
            series[(dia_str, W)] = rotulo.sort_index()
    return limiares, series


# ------------------------------------------------------------------ variante
class RegimeReloadVariant:
    """Mixin injetado ANTES de `WdoGridReloadMaker` na MRO (ver a fabrica
    `variante_class` abaixo) -- so' troca `_next_side_to_arm`, tudo o resto
    (reprecificacao, histerese, capital dinamico, fatia de saida, defesa,
    trailing) e' herdado sem mudanca nenhuma da classe de producao.

    `modo="fade_off"`: sob regime forte, REMOVE da lista de candidatos o
    lado que FADARIA a tendencia (short numa alta, long numa baixa) --
    continua alternando normalmente entre os dois lados quando o regime e'
    neutro, ou entre o(s) lado(s) que sobrarem.

    `modo="segue_tendencia"`: sob regime forte, o lado A FAVOR da tendencia
    (long numa alta, short numa baixa) e' forcado -- e ARMADO NO NIVEL DO
    LADO OPOSTO (`_level_price` invertido, ver abaixo). Leitura literal do
    pedido: "em vez de fade (SELL quando toca uma resistencia local), abra
    BUY na MESMA situacao" -- a mesma SITUACAO e' o preco tocar o nivel
    ACIMA da ancora (onde o SELL nasceria), e' so' a DIRECAO da ordem que
    inverte (breakout-buy no lugar de fade-sell). Isto e' o que torna esta
    variante MECANICAMENTE diferente de `fade_off`: numa grade de so' 2
    lados, "suspender o lado errado" e "preferir o lado certo" dariam o
    MESMO resultado se os dois usassem o nivel PADRAO do lado escolhido --
    so' a inversao de NIVEL cria uma segunda geometria de fato (entra no
    rompimento, nao no recuo). So' cai na alternancia normal (nivel padrao)
    se o lado preferido ja' esgotou `max_trades_per_side` ou o regime esta'
    neutro."""

    def __init__(self, *args, regime_lookup=None, modo: str = "fade_off", **kwargs):
        super().__init__(*args, **kwargs)
        assert modo in ("fade_off", "segue_tendencia")
        self._regime_lookup = regime_lookup
        self._modo = modo
        self._ultimo_ts = None
        self._nivel_invertido = False  # so' usado em modo="segue_tendencia" -- ver `_level_price`
        self.regime_contagem = {"up": 0, "down": 0, "neutral": 0, "sem_dado": 0}

    def on_bar(self, ts, bar, positions, session_pnl_brl):
        self._ultimo_ts = ts
        return super().on_bar(ts, bar, positions, session_pnl_brl)

    def _regime_atual(self) -> str | None:
        if self._regime_lookup is None or self._ultimo_ts is None:
            return None
        return self._regime_lookup(self._ultimo_ts)

    def _next_side_to_arm(self):
        regime = self._regime_atual()
        self.regime_contagem[regime or "neutral"] = self.regime_contagem.get(regime or "neutral", 0) + 1
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)

        self._nivel_invertido = False
        if self._modo == "segue_tendencia":
            preferido = {"up": "long", "down": "short"}.get(regime)
            if preferido is not None and self._fills_of(preferido) < self.max_trades_per_side:
                self._nivel_invertido = True  # arma NO NIVEL do lado oposto -- ver `_level_price`
                return preferido
            # regime neutro OU lado preferido ja' esgotado -- alternancia normal, nivel padrao
        else:  # fade_off
            proibido = {"up": "short", "down": "long"}.get(regime)
            if proibido is not None:
                candidates = [c for c in candidates if c != proibido]

        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def _level_price(self, side: str) -> float:
        """`segue_tendencia`, quando `_nivel_invertido`: usa o nivel do lado
        OPOSTO -- long arma no nivel ACIMA da ancora (onde o short/fade
        nasceria), short arma no nivel ABAIXO (onde o long/fade nasceria).
        Persiste por RODADA (setado so' em `_next_side_to_arm`, nunca
        chamado de novo enquanto a ordem so' reprecifica) -- o `_level_price`
        do MOTOR e' chamado a CADA reancoragem, e sem persistir isto a ordem
        voltaria ao nivel padrao no proximo reprice, no meio da mesma
        rodada. `fade_off` e o baseline nunca setam a flag -- comportamento
        IDENTICO ao da classe base."""
        if self._modo == "segue_tendencia" and self._nivel_invertido:
            side = "short" if side == "long" else "long"
        return super()._level_price(side)


def variante_class(base):
    class _Variante(RegimeReloadVariant, base):
        pass
    return _Variante


# ------------------------------------------------------------------- worker
def _roda_celula(spec: dict) -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from backtest.intraday.engine import run_intraday_backtest
    from backtest.intraday.profiles import config_for, profile_for
    from market_data_intraday.mt5_ticks_source import fetch_ticks_range
    from market_data_intraday.tick_bars import ticks_to_degenerate_bars
    from strategy.daytrade.lab.wdo_grid_reload_maker import WdoGridReloadMaker
    from strategy.daytrade.registry import get_daytrade_robot
    import inspect

    dia_str = spec["dia"]
    dia_ts = pd.Timestamp(dia_str, tz="UTC")
    inicio = dia_ts + pd.Timedelta(hours=12)
    fim = dia_ts + pd.Timedelta(hours=21, minutes=30)
    erros = []
    ticks = fetch_ticks_range(
        SYMBOL, _limite_servidor(inicio - timedelta(days=1)), _limite_servidor(fim),
        on_error=lambda k, e: erros.append((k, str(e))),
    )
    if ticks.empty:
        return {"spec": spec, "erro": f"sem ticks: {erros}"}
    ticks = ticks[(ticks.index >= inicio) & (ticks.index <= fim)]
    if ticks.empty:
        return {"spec": spec, "erro": "0 ticks apos recorte de sessao"}
    bars = ticks_to_degenerate_bars(ticks)

    robo = get_daytrade_robot("wdo_grid_reload_maker")
    params = [p for p in inspect.signature(WdoGridReloadMaker.__init__).parameters if p != "self"]
    kwargs = {p: getattr(robo, p) for p in params}

    if spec["variante"] == "baseline":
        strat = WdoGridReloadMaker(**kwargs)
    else:
        Cls = variante_class(WdoGridReloadMaker)
        strat = Cls(regime_lookup=spec["regime_lookup"], modo=spec["variante"], **kwargs)

    # Instrumentacao (2026-09-11): conta RECUSAS de capital -- ver a docstring
    # do modulo. Uma celula com muitas recusas descreve o PORTAO de capital,
    # nao a geometria (mesmo aviso de "janela censurada" do CLAUDE.md, item
    # 6.15) -- por isso o numero e' reportado ao lado do liquido, nunca
    # escondido. Monkeypatch da instancia (nao da classe): nao muda
    # comportamento nenhum, so' incrementa um contador antes de chamar o
    # hook real.
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
    ganho_medio = sum(ganhos) / len(ganhos) if ganhos else float("nan")
    perda_media = abs(sum(perdas) / len(perdas)) if perdas else float("nan")
    breakeven_empirico = (100.0 * perda_media / (ganho_medio + perda_media)
                           if ganhos and perdas else float("nan"))
    return {
        "spec": {k: v for k, v in spec.items() if k != "regime_lookup"},
        "n": len(trades),
        "ganhos": len(ganhos),
        "perdas": len(perdas),
        "pnl": sum(t.pnl_brl for t in trades),
        "ganho_medio": ganho_medio,
        "perda_media": perda_media,
        "breakeven_empirico": breakeven_empirico,
        "caixa_min": float(equity.min()) if len(equity) else float("nan"),
        "regime_contagem": getattr(strat, "regime_contagem", None),
        "recusas_capital": _contador["recusas"],
    }


def main() -> None:
    from market_data_intraday.mt5_source import fetch_m1_range

    print(f"[regime] baixando M1 de {SYMBOL} para calibracao + sinal "
          f"({CALIBRACAO_INICIO.date()} .. {DIAS_TESTE[-1]}) ...", flush=True)
    m1 = fetch_m1_range(
        SYMBOL, _limite_servidor(CALIBRACAO_INICIO),
        _limite_servidor(pd.Timestamp(DIAS_TESTE[-1] + "T23:59:59Z")),
    )
    if m1.empty:
        raise SystemExit("[regime] MT5 nao devolveu M1 -- terminal fora do ar?")
    from core.instruments import economics_for
    tick_size = economics_for("WDO@").price_tick_size
    limiares, series = construir_regimes(m1, tick_size)
    print(f"[regime] limiares (percentil {PERCENTIL_LIMIAR:.0f} de |retorno|, "
          f"calibrados em {(m1.index <= CALIBRACAO_FIM).sum()} barras M1 ate' "
          f"{CALIBRACAO_FIM.date()}):")
    for W, lim in limiares.items():
        print(f"    {W:>2} min -> {lim:.2f} ticks")

    specs = []
    for dia_str in DIAS_TESTE:
        specs.append({"dia": dia_str, "variante": "baseline", "escala": None,
                      "regime_lookup": None})
        for W in ESCALAS_MIN:
            serie = series.get((dia_str, W))
            lookup = RegimeLookup(serie) if serie is not None else None
            for modo in ("fade_off", "segue_tendencia"):
                specs.append({"dia": dia_str, "variante": modo, "escala": W,
                              "regime_lookup": lookup})

    print(f"\n[regime] {len(specs)} celulas (baseline + 2 variantes x "
          f"{len(ESCALAS_MIN)} escalas, {len(DIAS_TESTE)} dias)\n", flush=True)

    t0 = time.perf_counter()
    resultados = []
    with ProcessPoolExecutor(max_workers=min(8, len(specs))) as pool:
        futuros = {pool.submit(_roda_celula, s): s for s in specs}
        for fut in as_completed(futuros):
            r = fut.result()
            resultados.append(r)
            s = r["spec"]
            rot = f"{s['dia']} {s['variante']}" + (f"/{s['escala']}min" if s["escala"] else "")
            if "erro" in r:
                print(f"  [{rot}] ERRO: {r['erro']}", flush=True)
            else:
                print(f"  [{rot}] n={r['n']:>4}  pnl=R${r['pnl']:>10.2f}  "
                      f"caixa_min=R${r['caixa_min']:.2f}  "
                      f"recusas_capital={r['recusas_capital']}", flush=True)

    print(f"\n[regime] {len(resultados)} celulas em {(time.perf_counter()-t0)/60:.1f} min\n")

    # ---------------------------------------------------------- tabela final
    cab = (f"{'dia':<12}{'variante':<16}{'escala':>8}{'n':>6}{'win%':>8}"
           f"{'breakeven emp':>14}{'IC95% win%':>20}{'veredito':>12}"
           f"{'R$/op':>9}{'liquido R$':>12}{'caixa min':>11}{'recusas cap':>12}")
    print(cab)
    print("-" * len(cab))
    for r in sorted(resultados, key=lambda x: (x["spec"]["dia"], x["spec"]["variante"] != "baseline",
                                                x["spec"]["variante"], x["spec"]["escala"] or 0)):
        s = r["spec"]
        if "erro" in r:
            print(f"{s['dia']:<12}{s['variante']:<16}{str(s['escala']):>8}  ERRO: {r['erro']}")
            continue
        n, g = r["n"], r["ganhos"]
        win = 100.0 * g / n if n else float("nan")
        be = r["breakeven_empirico"]
        lo, hi = ic_wilson(g, n)
        if n == 0:
            veredito = "sem trade"
        elif math.isnan(be):
            veredito = "sem perda" if r["perdas"] == 0 else "sem ganho"
        elif hi < be:
            veredito = "NEGATIVA"
        elif lo > be:
            veredito = "POSITIVA"
        else:
            veredito = "indefinido"
        escala_txt = f"{s['escala']}min" if s["escala"] else "-"
        print(f"{s['dia']:<12}{s['variante']:<16}{escala_txt:>8}{n:>6}{win:>7.2f}%"
              f"{be:>13.2f}%{f'[{lo:.1f};{hi:.1f}]':>20}{veredito:>12}"
              f"{(r['pnl']/n if n else float('nan')):>9.2f}{r['pnl']:>12.2f}{r['caixa_min']:>11.2f}"
              f"{r['recusas_capital']:>12}")

    print("\nLEITURA: veredito compara o IC95% de Wilson do win% contra o "
          "BREAKEVEN EMPIRICO da propria celula (perda_media/(ganho_medio+"
          "perda_media)), nao o breakeven nominal da geometria T2/S16.")
    print("Contagem de regime por celula (quantos on_bar viram 'up'/'down'/"
          "'neutral' no momento de decidir o proximo armamento):")
    for r in resultados:
        if "erro" in r or r["regime_contagem"] is None:
            continue
        s = r["spec"]
        print(f"  {s['dia']} {s['variante']}/{s['escala']}min: {r['regime_contagem']}")


if __name__ == "__main__":
    main()
