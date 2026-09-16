# -*- coding: utf-8 -*-
"""REVIVER o `win_retangulo` com o rompimento+reentrada como gatilho de entrada
EXTRA -- WIN@ M1, IS apenas (129 pregoes, < 2026-06-13).

## O pedido, textual (dono, 2026-09-16)

"usamos este conhecimento de que volta e entra novamente no retangulo para
testar e talvez ate usar isso como novos pontos de entrada da propria
estrategia win_retangulo". NAO e' o fade-na-borda ja testado e refutado em
`rompimento_fade_retest_2026_09_16.py` (0/12 geometrias escapam do IC95%) --
e' reviver o proprio MECANISMO de producao (entrada no MEIO, geometria
`alvo_fracao_largura=0,80` / `stop_fracao_largura=0,50`, EnterLimit com TTL)
num retangulo que MORREU e voltou pra dentro das bordas antigas, em vez de
descartar o evento pra sempre como o robo de producao faz hoje.

## O que ja se sabe e NAO e' remedido aqui (`scratch/rompimento_investigacao_
## 2026_09_16/`, ler `anatomia.md` e `fade_do_retest.md` por inteiro antes de
## mexer neste script)

417 rompimentos no IS; 82% retestam a borda em ate 60 barras (mediana 7);
dado que retesta, 83% ENTRAM de volta (fecham do lado de dentro da borda
rompida -- a MESMA definicao usada aqui: `close < topo` para rompimento de
alta, `close > piso` para baixa) contra 17% que retomam o rompimento; dado
que entra, 65,8% saem rasos pelo mesmo lado (mediana 0,4xL) e 29,6%
atravessam ate a oposta (mediana 1,7xL). O fade NA BORDA (entrar exatamente
no retest) ja foi testado e refutado -- 12 geometrias, 0 escapam do IC95% do
breakeven. Esta rodada e' DIFERENTE: em vez de entrar na borda, o retangulo
MORTO e' revivido e a entrada volta a ser a de sempre -- no MEIO, mirando
ALEM da borda oposta.

## Duas hipoteses, medidas juntas nesta rodada

**A -- entrada EXTRA por revivencia.** Em vez de descartar `self._retangulo`
pra sempre quando ele morre, guarda as bordas por uma janela curta
(`janela_revivencia_barras`). Se o fechamento confirma a reentrada (mesma
definicao de `anatomia.md`), arma UMA `EnterLimit` no MEIO do retangulo
revivido, com a geometria EXATA de producao (`alvo_fracao_largura=0,80`,
`stop_fracao_largura=0,50`, `ttl_barras=10`). Isto e' uma operacao que o robo
de HOJE nunca faz. Pergunta: essas operacoes extras tem edge, ISOLADAS (nao
no agregado)?

**B -- filtro de qualidade nas entradas NORMAIS.** Das entradas que o
`win_retangulo` de producao ja faz (deteccao do zero, sem rompimento
envolvido), separa as que nasceram num retangulo cuja janela de FORMACAO
(as 3xW barras antes da deteccao) incluiu um evento de rompimento-e-
reentrada de OUTRO retangulo, contra as que nao. Pergunta: a subpopulacao
"sobrevivente de rompimento" e' melhor?

## Desenho -- como as duas hipoteses coexistem numa unica classe sem
## reimplementar `WinRetangulo`

`WinRetanguloRevivencia(WinRetangulo)` SUBCLASSE (nao entra em `src/`, nao
toca producao). Com `revivencia_ativa=False` ela e' um WinRetangulo
BYTE-IDENTICO em decisao (mesma formula de meio/alvo/stop/checagem mecanica,
copiada -- nao herdada por `super().on_bar()`, porque o controle de fluxo da
base retorna cedo demais para eu injetar a revivencia no meio dele) --
só adiciona um RÓTULO por trade (via um log proprio da instancia, casado por
ORDEM DE PREENCHIMENTO com `res.trades`, ja que so existe UMA ordem pendente
por vez -- nunca pyramida). Rodada com `revivencia_ativa=False` serve DUAS
finalidades: (1) confere que a subclasse reproduz os numeros conhecidos da
producao (615 trades, R$3.720,70, IS) e (2) fornece os rotulos da Hipotese B.

Com `revivencia_ativa=True`, um retangulo MORTO fica de pe' por
`janela_revivencia_barras` (medido em {20, 60}) e, na reentrada confirmada,
arma UMA entrada revivida -- ou permite MULTIPLAS entradas do mesmo evento
morto (`permitir_multiplas_revivencias`, medido {False, True}) ate a janela
expirar. Confere MECANICAMENTE o lado da ordem antes de aceitar (mesma
checagem que `WinRetangulo._entrada` ja faz) e conta quando a checagem
falha, e quando a revivencia queria armar mas o motor nao deixa (posicao
ja aberta / ordem ja pendente -- o motor NAO piramida).

## Regras de medicao respeitadas (sem excecao)

  * So o IS (< 2026-06-13). O OOS fica INTACTO -- ja foi gasto por 18
    familias da Copa e por dois parametros do win_retangulo.
  * `MIN_BARRAS_POR_PREGAO = 400`.
  * Desenho de execucao FECHADO: so `EnterLimit` com `ttl_bars`; alvo so
    como limite real (`target_fills_as_maker=True`); stop e' a UNICA ordem a
    mercado. Checagem MECANICA do lado antes de armar, reportada.
  * Capital: comeca de R$1.100 (piso do win_retangulo) -- recalculado no fim
    se o rebaixamento por operacao da variante com revivencia for maior.
  * WIN@ NAO tem `fidelidade.py` calibrada -- `fila NAO CALIBRADA` carimbada
    pela propria linha padrao, premissa OTIMISTA dos dois lados.
  * Tabela padrao (`linha_de_resultado`+`tabela`), 12 colunas base, extras
    depois. `trades` e `sem trade` sempre reportados -- janela onde o robo
    parou e' censurada.
  * `ProcessPoolExecutor` com `submit`/`as_completed`, `redirect_stdout` por
    unidade, streaming.
  * Breakeven empirico so' com os dois lados da amostra; Wilson IC95% pro
    acerto. Decimal BR.
  * Ordem de chegada nunca `MFE>=X e MAE<X` -- nao se aplica aqui (nao ha
    corrida MFE/MAE nesta medicao, so' economia de trade fechado pelo motor).

Uso: `.venv\\Scripts\\python.exe -u scripts/daytrade/win_retangulo_revivencia_rompimento_2026_09_16.py`
"""
from __future__ import annotations

import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from backtest.intraday.engine import run_intraday_backtest  # noqa: E402
from backtest.intraday.profiles import config_for, profile_for  # noqa: E402
from backtest.intraday.report import linha_de_resultado, tabela  # noqa: E402
from market_data_intraday.storage import load_m1  # noqa: E402
from strategy.daytrade.base import Bar, EnterLimit, IntradayAction  # noqa: E402
from strategy.daytrade.base import IntradayOpenPosition, no_tick  # noqa: E402
from strategy.daytrade.lab.win_retangulo import (BARRAS_MORTE,  # noqa: E402
                                                  MARGEM_MORTE, WinRetangulo,
                                                  detecta_retangulo)

SIMBOLO = "WIN@"
MIN_BARRAS_POR_PREGAO = 400
CORTE_OOS = pd.Timestamp("2026-06-13").date()
CAPITAL_REFERENCIA = 1_100.0   # piso medido do win_retangulo -- ponto de partida
MARGEM_WIN = 100.0             # margem crua do WIN@ (core.instruments.FUTUROS)


def br(v, dec=2):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, dec=1):
    return "—" if x != x else br(100 * x, dec) + "%"


def _ic95(k: int, n: int) -> tuple[float, float]:
    """Wilson. Sem ele o win% e' um numero sem dispersao."""
    if n == 0:
        return float("nan"), float("nan")
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - r) / d, (c + r) / d


def _breakeven_empirico(pnls: list[float]) -> float:
    g = [p for p in pnls if p > 0]
    p = [p for p in pnls if p <= 0]
    if not g or not p:
        return float("nan")
    gm = sum(g) / len(g)
    pm = abs(sum(p) / len(p))
    return pm / (gm + pm)


# ---------------------------------------------------------------------------
# Rastreador INDEPENDENTE de rompimento+reentrada -- so' para ROTULAR as
# entradas normais (Hipotese B). Nunca decide nada, nunca influencia o motor.
# Reusa `detecta_retangulo`/MARGEM_MORTE/BARRAS_MORTE de producao -- a MESMA
# regra de morte e a MESMA definicao de "entra" (`close < topo` / `> piso`)
# que `anatomia.md` e `rompimento_fade_retest_2026_09_16.py` ja usam.
# ---------------------------------------------------------------------------
class _HistoricoRompimentos:
    def __init__(self, janela_barras: int, tolerancia: float, largura_minima: float,
                 janela_memoria_barras: int):
        self.W = janela_barras
        self.tol = tolerancia
        self.largura_min = largura_minima
        self.janela_memoria = janela_memoria_barras
        self._hist: deque[Bar] = deque(maxlen=3 * janela_barras + 2)
        self._retangulo: dict | None = None
        self._fora_seguidas = 0
        self._rompido: dict | None = None   # {topo, piso, lado} esperando reentrada
        self._eventos: deque[int] = deque()  # indices de barra em que a REENTRADA foi confirmada
        self._n = 0

    def reset_sessao(self) -> None:
        self._hist.clear()
        self._retangulo = None
        self._fora_seguidas = 0
        self._rompido = None
        self._eventos.clear()
        # `_n` NAO zera: e' so' um contador monotonico para medir distancia
        # em barras, e o rompido/eventos ja foram limpos na virada de sessao
        # (nada de nivel de preco atravessa o pregao).

    def _janelas(self):
        W = self.W
        h = list(self._hist)
        recente = h[-W:]
        anterior = h[-3 * W:-W]
        return (
            np.array([b.high for b in recente], dtype=float),
            np.array([b.low for b in recente], dtype=float),
            np.array([b.close for b in recente], dtype=float),
            float(max(b.high for b in anterior) - min(b.low for b in anterior)),
        )

    def _tenta_detectar(self) -> None:
        if len(self._hist) < 3 * self.W:
            return
        high, low, close, amp_ant = self._janelas()
        ret = detecta_retangulo(high, low, close, amp_ant, tolerancia=self.tol)
        if ret is None or ret["largura"] < self.largura_min:
            return
        self._retangulo = ret
        self._fora_seguidas = 0

    def registra(self, bar: Bar) -> None:
        self._n += 1
        self._hist.append(bar)
        if self._retangulo is not None:
            r = self._retangulo
            margem = MARGEM_MORTE * r["largura"]
            if bar.close > r["topo"] + margem or bar.close < r["piso"] - margem:
                self._fora_seguidas += 1
                if self._fora_seguidas >= BARRAS_MORTE:
                    lado = "alta" if bar.close > r["topo"] + margem else "baixa"
                    self._rompido = dict(topo=r["topo"], piso=r["piso"], lado=lado)
                    self._retangulo = None
                    self._fora_seguidas = 0
            else:
                self._fora_seguidas = 0
        if self._retangulo is None and self._rompido is None:
            self._tenta_detectar()
        if self._rompido is not None:
            r = self._rompido
            reentrou = (bar.close < r["topo"]) if r["lado"] == "alta" else (bar.close > r["piso"])
            if reentrou:
                self._eventos.append(self._n)
                self._rompido = None
        while self._eventos and (self._n - self._eventos[0]) > self.janela_memoria:
            self._eventos.popleft()

    def houve_evento_recente(self) -> bool:
        return len(self._eventos) > 0


@dataclass
class _RegistroArmada:
    ts: pd.Timestamp
    origem: str                      # "normal" | "revivencia"
    hist_rompimento: bool | None     # so' para origem=="normal"
    preenchida: bool = False


@dataclass
class DiagRevivencia:
    mortos_capturados: int = 0
    mortos_substituidos_sem_reviver: int = 0
    mortos_expirados_sem_reviver: int = 0
    revivencias_armadas: int = 0
    revivencias_expiradas_sem_fill: int = 0
    revivencias_preenchidas: int = 0
    mec_falhou_revivencia: int = 0
    perdidas_posicao_aberta: int = 0
    perdidas_ordem_pendente: int = 0


class WinRetanguloRevivencia(WinRetangulo):
    """`WinRetangulo` + entrada EXTRA por revivencia de retangulo morto
    (Hipotese A) + rotulo de historico de rompimento nas entradas NORMAIS
    (Hipotese B). Ver docstring do modulo.

    `on_bar` e' reescrito, NAO chama `super().on_bar()`: o controle de fluxo
    da base retorna `[]` assim que nao ha retangulo VIVO, antes de checar
    posicao ou ordem pendente -- nao ha ponto de injecao no meio dele. A
    formula de entrada (`_monta_entrada`) e' uma copia literal da da base,
    conferida linha a linha; com `revivencia_ativa=False` os dois produzem
    EXATAMENTE os mesmos trades (verificado no `main()` deste script)."""

    name = "win_retangulo_revivencia_lab"

    def __init__(self, *, revivencia_ativa: bool = True,
                 janela_revivencia_barras: int = 20,
                 permitir_multiplas_revivencias: bool = False,
                 janela_memoria_historico_barras: int | None = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        if revivencia_ativa and janela_revivencia_barras <= 0:
            raise ValueError("janela_revivencia_barras deve ser positiva com revivencia ativa")
        self.revivencia_ativa = bool(revivencia_ativa)
        self.janela_revivencia_barras = int(janela_revivencia_barras)
        self.permitir_multiplas_revivencias = bool(permitir_multiplas_revivencias)
        janela_memoria = janela_memoria_historico_barras or (3 * self.janela_barras)
        self._historico = _HistoricoRompimentos(
            self.janela_barras, self.tolerancia_borda, self.largura_minima_pontos,
            janela_memoria)
        self._morto: dict | None = None
        self._indice_pendente: int | None = None
        self.log_armadas: list[_RegistroArmada] = []
        self.diag = DiagRevivencia()

    # -- sessao --------------------------------------------------------
    def _reset_sessao(self) -> None:
        super()._reset_sessao()
        self._morto = None
        self._indice_pendente = None

    def on_session_start(self, session_date) -> None:
        if self._morto is not None:
            self.diag.mortos_expirados_sem_reviver += 1
        self._historico.reset_sessao()
        super().on_session_start(session_date)

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        super().on_order_rejected(ts)
        self._finaliza_pendente()

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        super().on_order_expired(ts)
        self._finaliza_pendente()

    def _finaliza_pendente(self) -> None:
        if self._indice_pendente is not None:
            reg = self.log_armadas[self._indice_pendente]
            if reg.origem == "revivencia" and not reg.preenchida:
                self.diag.revivencias_expiradas_sem_fill += 1
            self._indice_pendente = None

    # -- geometria compartilhada (copia literal da base) ----------------
    def _monta_entrada(self, bar: Bar, meio: float, largura: float, contratos: int,
                        reason_prefix: str) -> EnterLimit | None:
        if bar.close < meio:
            lado = "short"
            alvo = meio - self.alvo_fracao_largura * largura
            stop = meio + self.stop_fracao_largura * largura
        elif bar.close > meio:
            lado = "long"
            alvo = meio + self.alvo_fracao_largura * largura
            stop = meio - self.stop_fracao_largura * largura
        else:
            return None
        limite = no_tick(meio, self.tick_size)
        if lado == "short" and limite <= bar.close:
            return None
        if lado == "long" and limite >= bar.close:
            return None
        self._barras_esperando = 0
        return EnterLimit(
            side=lado, limit_price=limite, initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size), quantity=contratos,
            ttl_bars=self.ttl_barras, reason=f"{reason_prefix}_L{largura:.0f}")

    def _tenta_armar_normal(self, ts: pd.Timestamp, bar: Bar) -> list[IntradayAction] | None:
        r = self._retangulo
        acao = self._monta_entrada(bar, r["meio"], r["largura"], self._contratos, "retangulo")
        if acao is None:
            return None
        hist = self._historico.houve_evento_recente()
        self.log_armadas.append(_RegistroArmada(ts=ts, origem="normal", hist_rompimento=hist))
        self._indice_pendente = len(self.log_armadas) - 1
        return [acao]

    def _tenta_armar_revivencia(self, ts: pd.Timestamp, bar: Bar) -> list[IntradayAction] | None:
        r = self._morto
        contratos = self._dimensiona()
        acao = self._monta_entrada(bar, r["meio"], r["largura"], contratos,
                                    f"revivencia_{r['lado']}")
        if acao is None:
            self.diag.mec_falhou_revivencia += 1
            return None
        self.log_armadas.append(_RegistroArmada(ts=ts, origem="revivencia", hist_rompimento=None))
        self._indice_pendente = len(self.log_armadas) - 1
        self.diag.revivencias_armadas += 1
        if not self.permitir_multiplas_revivencias:
            self._morto = None
        return [acao]

    # -- loop ------------------------------------------------------------
    def on_bar(self, ts: pd.Timestamp, bar: Bar, positions: list[IntradayOpenPosition],
               session_pnl_brl: float) -> list[IntradayAction]:
        self._historico.registra(bar)
        self._hist.append(bar)

        # 1. envelhece / expira o retangulo morto
        if self._morto is not None:
            self._morto["idade"] += 1
            if self._morto["idade"] > self.janela_revivencia_barras:
                self.diag.mortos_expirados_sem_reviver += 1
                self._morto = None

        # 2. vida/morte do retangulo NORMAL -- identico a producao
        if self._retangulo is not None and self._morreu(bar):
            r = self._retangulo
            margem = MARGEM_MORTE * r["largura"]
            lado = "alta" if bar.close > r["topo"] + margem else "baixa"
            if self.revivencia_ativa:
                if self._morto is not None:
                    self.diag.mortos_substituidos_sem_reviver += 1
                self.diag.mortos_capturados += 1
                self._morto = dict(topo=r["topo"], piso=r["piso"], meio=r["meio"],
                                    largura=r["largura"], lado=lado, idade=0)
            self._retangulo = None
            self._barras_esperando = None
        if self._retangulo is None:
            self._tenta_detectar()

        reentrou_morto = False
        if self.revivencia_ativa and self._morto is not None:
            r = self._morto
            reentrou_morto = (bar.close < r["topo"]) if r["lado"] == "alta" else (bar.close > r["piso"])

        # posicao aberta: motor cuida de stop/alvo, robo nao arma por cima
        if positions:
            if reentrou_morto:
                self.diag.perdidas_posicao_aberta += 1
            if self._indice_pendente is not None:
                reg = self.log_armadas[self._indice_pendente]
                reg.preenchida = True
                if reg.origem == "revivencia":
                    self.diag.revivencias_preenchidas += 1
                    if not self.permitir_multiplas_revivencias:
                        self._morto = None
                self._indice_pendente = None
            self._barras_esperando = None
            return []

        # ordem ja parada no livro: nao rearma por cima
        if self._barras_esperando is not None:
            if reentrou_morto:
                self.diag.perdidas_ordem_pendente += 1
            self._barras_esperando += 1
            if self._barras_esperando < self.ttl_barras:
                return []
            self._barras_esperando = None

        # 3. entrada NORMAL tem prioridade (identico a producao)
        if self._retangulo is not None:
            acao = self._tenta_armar_normal(ts, bar)
            if acao:
                return acao

        # 4. entrada por REVIVENCIA
        if self.revivencia_ativa and self._morto is not None and reentrou_morto:
            acao = self._tenta_armar_revivencia(ts, bar)
            if acao:
                return acao

        return []


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _caixa_realizado(trades, capital):
    seq = [t.pnl_brl for t in sorted(trades, key=lambda t: t.exit_ts)]
    if not seq:
        return capital, 0.0
    acum = np.cumsum(seq)
    eq_path = capital + acum
    maxdd_trade = float((np.maximum.accumulate(eq_path) - eq_path).max())
    return float(eq_path.min()), maxdd_trade


def _rotula_trades(strat, trades):
    """Casa cada trade FECHADO com o registro de armada que o gerou, por
    ORDEM DE PREENCHIMENTO -- so existe UMA ordem pendente por vez (o motor
    nao piramida, e o robo so' arma de novo depois que a anterior resolveu),
    entao a sequencia de armadas PREENCHIDAS e a sequencia de trades por
    `entry_ts` sao a MESMA ordem. Levanta se as contagens nao baterem (bug de
    contabilidade, nao dado ruim)."""
    preenchidas = [r for r in strat.log_armadas if r.preenchida]
    trades_ordenados = sorted(trades, key=lambda t: t.entry_ts)
    if len(preenchidas) != len(trades_ordenados):
        raise AssertionError(
            f"log de armadas preenchidas ({len(preenchidas)}) != trades ({len(trades_ordenados)})")
    return list(zip(preenchidas, trades_ordenados))


def _cfg_padrao(strat, capital):
    profile = profile_for(strat.symbol)
    return config_for(
        profile,
        trade_tick_value=0.01 * float(profile.point_value_brl or 1.0),
        trade_tick_size=0.01,
        initial_capital=capital,
        target_fills_as_maker=strat.target_fills_as_maker,
        anchor_exits_at_fill=strat.anchor_exits_at_fill,
        limit_fill_capped_by_volume=True,
    )


def _unidade(args):
    rotulo, dias, kwargs_extra, capital = args
    strat = WinRetanguloRevivencia(**kwargs_extra)
    df = load_m1(strat.symbol).sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    cfg = _cfg_padrao(strat, capital)
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)

    trades = list(res.trades)
    parelhas = _rotula_trades(strat, trades)  # levanta se a contabilidade divergir

    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    ganhos = [t.pnl_brl for t in trades if t.pnl_brl > 0]
    be = _breakeven_empirico([t.pnl_brl for t in trades])
    com_trade = {t.exit_ts.date() for t in trades}
    caixa_min, rebaix_op = _caixa_realizado(trades, capital)
    puladas = len(getattr(res, "sessoes_puladas_por_capital", []) or [])
    d = strat.diag

    revivencia_pnls = [t.pnl_brl for reg, t in parelhas if reg.origem == "revivencia"]
    normal_pnls = [t.pnl_brl for reg, t in parelhas if reg.origem == "normal"]
    hist1_pnls = [t.pnl_brl for reg, t in parelhas if reg.origem == "normal" and reg.hist_rompimento is True]
    hist0_pnls = [t.pnl_brl for reg, t in parelhas if reg.origem == "normal" and reg.hist_rompimento is False]

    extras = {
        "morto captur.": str(d.mortos_capturados),
        "reviv.armada": str(d.revivencias_armadas),
        "reviv.preench.": str(d.revivencias_preenchidas),
        "reviv.expira": str(d.revivencias_expiradas_sem_fill),
        "mec.falhou": str(d.mec_falhou_revivencia),
        "perd.pos.ab.": str(d.perdidas_posicao_aberta),
        "perd.ord.pen.": str(d.perdidas_ordem_pendente),
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "pior op.": br(min(perdas)) if perdas else "—",
        "caixa min": br(caixa_min),
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}"
                     + (f" (+{puladas} pulado/capital)" if puladas else ""),
    }
    linha = linha_de_resultado(rotulo, res, capital, extras=extras)
    return dict(
        rotulo=rotulo, linha=linha, n=len(trades), diag=d,
        caixa_min=caixa_min, rebaix_op=rebaix_op, be=be,
        n_revivencia=len(revivencia_pnls), pnl_revivencia=sum(revivencia_pnls),
        revivencia_pnls=revivencia_pnls,
        n_normal=len(normal_pnls), pnl_normal=sum(normal_pnls),
        hist1_pnls=hist1_pnls, hist0_pnls=hist0_pnls,
        zerado=getattr(res, "wiped_out_at", None) is not None,
    )


def _unidade_pura(args):
    """Producao PURA (`WinRetangulo`, zero subclasse) -- a confirmacao de que
    o baseline reproduz os numeros conhecidos (615 trades, R$3.720,70 no IS).

    `escala_por_caixa` (kwarg opcional) existe so' para o DIAGNOSTICO do
    PASSO 0 -- producao de verdade nunca passa isto, sempre usa o default
    (`True`, herdado do registry)."""
    rotulo, dias, capital, kwargs_extra = args
    strat = WinRetangulo(**kwargs_extra)
    df = load_m1(strat.symbol).sort_index()
    alvo = set(dias)
    bars = df[[d in alvo for d in df.index.date]]
    cfg = _cfg_padrao(strat, capital)
    buf = StringIO()
    with redirect_stdout(buf):
        res = run_intraday_backtest(bars, strat, cfg)
    trades = list(res.trades)
    perdas = [t.pnl_brl for t in trades if t.pnl_brl <= 0]
    be = _breakeven_empirico([t.pnl_brl for t in trades])
    com_trade = {t.exit_ts.date() for t in trades}
    caixa_min, rebaix_op = _caixa_realizado(trades, capital)
    extras = {
        "BEemp%": (br(100 * be, 1) + "%") if be == be else "--",
        "pior op.": br(min(perdas)) if perdas else "—",
        "caixa min": br(caixa_min),
        "sem trade": f"{len(dias) - len(com_trade)}/{len(dias)}",
    }
    linha = linha_de_resultado(rotulo, res, capital, extras=extras)
    return dict(rotulo=rotulo, linha=linha, n=len(trades), be=be,
                caixa_min=caixa_min, rebaix_op=rebaix_op, trades=trades)


VARIANTES_REVIVENCIA: dict[str, dict] = {
    "1 instrumentado (rev.OFF)": dict(revivencia_ativa=False),
    "2 revivencia j=20 unica": dict(revivencia_ativa=True, janela_revivencia_barras=20,
                                     permitir_multiplas_revivencias=False),
    "3 revivencia j=60 unica": dict(revivencia_ativa=True, janela_revivencia_barras=60,
                                     permitir_multiplas_revivencias=False),
    "4 revivencia j=20 multipla": dict(revivencia_ativa=True, janela_revivencia_barras=20,
                                        permitir_multiplas_revivencias=True),
    "5 revivencia j=60 multipla": dict(revivencia_ativa=True, janela_revivencia_barras=60,
                                        permitir_multiplas_revivencias=True),
}

EXTRAS = ("morto captur.", "reviv.armada", "reviv.preench.", "reviv.expira", "mec.falhou",
          "perd.pos.ab.", "perd.ord.pen.", "BEemp%", "pior op.", "caixa min", "sem trade")
EXTRAS_PURO = ("BEemp%", "pior op.", "caixa min", "sem trade")


def main():
    df = load_m1(SIMBOLO).sort_index()
    contagem = df.groupby(df.index.date).size()
    IS = sorted(d for d, n in contagem.items() if n >= MIN_BARRAS_POR_PREGAO and d < CORTE_OOS)

    print("=" * 190)
    print("REVIVER O win_retangulo -- rompimento+reentrada como gatilho de entrada EXTRA (Hipotese A) "
          "e como filtro de qualidade das entradas normais (Hipotese B)")
    print("=" * 190)
    print(f"  {SIMBOLO} M1 | IS {len(IS)} pregoes ({IS[0]} a {IS[-1]}) | capital de referencia "
          f"R$ {br(CAPITAL_REFERENCIA,0)} (piso do win_retangulo)")
    print("  desenho de execucao FECHADO: EnterLimit com ttl, alvo so' como limite real, "
          "stop e' a UNICA ordem a mercado")
    print("  fila NAO CALIBRADA para WIN@ -- premissa OTIMISTA dos dois lados, igual em toda a linha\n",
          flush=True)

    # -- (0) BASELINE PURO -- confirma os numeros conhecidos de producao ----
    print("-" * 190)
    print("PASSO 0 -- baseline PURO (WinRetangulo de producao, zero subclasse) -- confere os numeros conhecidos")
    print("-" * 190)
    r0 = _unidade_pura(("0 BASELINE producao pura (escala_por_caixa=True, DEFAULT)", IS, CAPITAL_REFERENCIA, {}))
    print(tabela([r0["linha"]], extras=EXTRAS_PURO))
    liquido0 = r0["linha"].liquido_brl
    n0 = r0["n"]
    esperado_liquido, esperado_n = 3_720.70, 615
    trades_batem = (n0 == esperado_n)
    liquido_bate = abs(liquido0 - esperado_liquido) < 0.01
    print(f"\n  esperado (docstring de win_retangulo.py / anatomia.md): R$ {br(esperado_liquido)} liquido, "
          f"{esperado_n} trades")
    print(f"  medido agora (default atual, escala_por_caixa=True):    R$ {br(liquido0)} liquido, {n0} trades")
    if trades_batem and liquido_bate:
        print("  >>> BATE EXATAMENTE <<<\n", flush=True)
    elif trades_batem and not liquido_bate:
        # O numero de TRADES (a assinatura estrutural mais dificil de
        # coincidir por acaso -- depende de deteccao, geometria e prazo, nao
        # de um parametro de tamanho de posicao) BATE EXATO. So' o LIQUIDO
        # diverge -- diagnostico automatico: roda de novo com
        # escala_por_caixa=False (o comportamento de ANTES das commits
        # 4806636/ca252a7, "o robo dimensiona contrato pelo caixa", ambas de
        # 2026-09-15, POSTERIORES a quando R$3.720,70 foi escrito no
        # docstring) para confirmar a causa antes de prosseguir.
        print("  >>> trades BATEM exato, liquido DIVERGE -- diagnosticando (nao e' bug ainda) <<<")
        r0b = _unidade_pura(("0b diagnostico (escala_por_caixa=False)", IS, CAPITAL_REFERENCIA,
                              dict(escala_por_caixa=False)))
        liq_sem_escala = r0b["linha"].liquido_brl
        explica = abs(liq_sem_escala - esperado_liquido) < 0.01
        print(f"  com escala_por_caixa=False (comportamento pre-2026-09-15): R$ {br(liq_sem_escala)} liquido, "
              f"{r0b['n']} trades")
        if explica:
            print("  >>> EXPLICADO, NAO E' BUG <<< -- o numero documentado (R$3.720,70) foi escrito ANTES do "
                  "robo escalar contrato pelo caixa (commits 4806636/ca252a7, 2026-09-15 21:40) e nunca foi "
                  "atualizado no docstring depois. A ESCALA por caixa e' o comportamento de PRODUCAO hoje "
                  "(default da classe, e' o que `strategy.daytrade.registry.get_daytrade_robot('win_retangulo')` "
                  "de fato instancia) -- por isso esta rodada usa R$3.536,60/615 trades, NAO R$3.720,70, como o "
                  "baseline de referencia daqui pra frente. O invariante que de fato importa (615 trades, "
                  "identico) BATEU exato -- deteccao/geometria/prazo nao mudaram.\n", flush=True)
            bate = True
        else:
            print("  >>> NAO EXPLICADO -- a hipotese da escala por caixa nao fecha a conta. PARANDO. <<<")
            bate = False
    else:
        bate = False
        print("  >>> NAO BATE (nem trades) -- PARAR E INVESTIGAR <<<\n", flush=True)
    if not bate:
        print("ABORTANDO: baseline nao reproduz os numeros conhecidos -- ver mensagem acima.")
        return

    # -- (1)-(5) variantes instrumentadas/revivencia -------------------------
    tarefas = [(rot, IS, kw, CAPITAL_REFERENCIA) for rot, kw in VARIANTES_REVIVENCIA.items()]
    resultados: dict[str, dict] = {}
    print("-" * 190)
    print(f"PASSO 1 -- {len(tarefas)} variantes (instrumentado + 4 combinacoes de revivencia)")
    print("-" * 190)
    with ProcessPoolExecutor() as pool:
        futs = {pool.submit(_unidade, t): t[0] for t in tarefas}
        for fut in as_completed(futs):
            rot = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                print(f"  [ERRO] {rot}: {e!r}", flush=True)
                continue
            resultados[rot] = r
            print(f"  ok {rot:<30} trades={r['n']:>5}  liquido={br(r['linha'].liquido_brl):>12}  "
                  f"reviv.preench={r['diag'].revivencias_preenchidas:>4}  caixa_min={br(r['caixa_min'])}",
                  flush=True)

    # -- confere que o instrumentado (revivencia OFF) reproduz o baseline ---
    r1 = resultados.get("1 instrumentado (rev.OFF)")
    print("\n" + "-" * 190)
    print("CONFERENCIA -- subclasse instrumentada com revivencia OFF tem de ser BYTE-IDENTICA ao baseline puro")
    print("-" * 190)
    if r1 is not None:
        igual = (r1["n"] == n0) and abs(r1["linha"].liquido_brl - liquido0) < 0.01
        print(f"  baseline puro: {n0} trades, R$ {br(liquido0)}  |  instrumentado: {r1['n']} trades, "
              f"R$ {br(r1['linha'].liquido_brl)}  ->  {'IDENTICO' if igual else 'DIVERGIU -- BUG'}")
    print()

    print("=" * 190)
    print("TABELA PADRAO -- baseline puro + 5 variantes instrumentadas")
    print("=" * 190)
    linhas = [r0["linha"]] + [resultados[rot]["linha"] for rot in VARIANTES_REVIVENCIA if rot in resultados]
    print(tabela(linhas, extras=EXTRAS, largura_extra=13))

    # -- ISOLADO: economia das operacoes de REVIVENCIA, por variante --------
    print("\n" + "=" * 190)
    print("HIPOTESE A -- economia ISOLADA das operacoes de REVIVENCIA (nao o agregado)")
    print("=" * 190)
    print(f"  {'variante':<30}{'n reviv.':>10}{'R$ total reviv.':>18}{'R$/op reviv.':>14}"
          f"{'win% reviv.':>13}{'BEemp reviv.':>14}{'IC95 reviv.':>22}{'pior reviv.':>13}")
    for rot in VARIANTES_REVIVENCIA:
        r = resultados.get(rot)
        if r is None or r["n_revivencia"] == 0:
            print(f"  {rot:<30}{'0':>10}   (nenhuma operacao de revivencia preencheu)")
            continue
        pnls = r["revivencia_pnls"]
        n = len(pnls)
        ganhos = sum(1 for p in pnls if p > 0)
        win = ganhos / n
        be = _breakeven_empirico(pnls)
        lo, hi = _ic95(ganhos, n)
        print(f"  {rot:<30}{n:>10}{br(sum(pnls)):>18}{br(sum(pnls)/n):>14}{pct(win):>13}"
              f"{pct(be) if be==be else '--':>14}[{pct(lo)} ; {pct(hi)}]{br(min(pnls)):>13}")

    # -- piso de capital recalculado -----------------------------------------
    print("\n" + "=" * 190)
    print("PISO DE CAPITAL -- recalculado se a revivencia rebaixar mais que o baseline")
    print("=" * 190)
    rebaix_baseline = r0["rebaix_op"]
    print(f"  baseline puro: rebaixamento por operacao R$ {br(rebaix_baseline)} -> piso "
          f"R$ {br(rebaix_baseline + MARGEM_WIN)}")
    pior_rebaix = rebaix_baseline
    pior_rotulo = "0 BASELINE producao pura"
    for rot, r in resultados.items():
        print(f"  {rot:<30}: rebaixamento por operacao R$ {br(r['rebaix_op'])} -> piso "
              f"R$ {br(r['rebaix_op'] + MARGEM_WIN)}   caixa minimo atingido R$ {br(r['caixa_min'])}")
        if r["rebaix_op"] > pior_rebaix:
            pior_rebaix = r["rebaix_op"]
            pior_rotulo = rot
    piso_real = pior_rebaix + MARGEM_WIN
    print(f"\n  PIOR REBAIXAMENTO por operacao entre TODAS as variantes: R$ {br(pior_rebaix)} "
          f"({pior_rotulo})")
    print(f"  PISO REAL recomendado (rebaixamento + margem crua R$100): R$ {br(piso_real)}"
          + (f"  (> R$1.100 do win_retangulo original -- NAO adotar 1.100 se for perseguir esta linha)"
             if piso_real > CAPITAL_REFERENCIA else "  (nao muda o piso original)"))

    # -- HIPOTESE B -- filtro de qualidade das entradas normais -------------
    print("\n" + "=" * 190)
    print("HIPOTESE B -- entradas NORMAIS (sem revivencia), separadas por historico de rompimento-sobrevivido")
    print("=" * 190)
    if r1 is not None:
        for rotulo_grupo, pnls in (("COM rompimento nas 3xW barras antes", r1["hist1_pnls"]),
                                    ("SEM rompimento nas 3xW barras antes", r1["hist0_pnls"])):
            n = len(pnls)
            if n == 0:
                print(f"  {rotulo_grupo:<40} n=0 -- sem operacoes neste grupo")
                continue
            ganhos = sum(1 for p in pnls if p > 0)
            win = ganhos / n
            be = _breakeven_empirico(pnls)
            lo, hi = _ic95(ganhos, n)
            aviso = "" if n >= 100 else "   *** AMOSTRA PEQUENA -- nao da para separar com confianca ***"
            print(f"  {rotulo_grupo:<40} n={n:<6} liquido=R$ {br(sum(pnls)):<12} R$/op={br(sum(pnls)/n):<9} "
                  f"win={pct(win):<8} BEemp={pct(be) if be==be else '--':<8} "
                  f"IC95=[{pct(lo)} ; {pct(hi)}]{aviso}")
        n_total = len(r1["hist1_pnls"]) + len(r1["hist0_pnls"])
        print(f"\n  total de entradas normais rotuladas: {n_total} (deve bater com o trades do "
              f"'1 instrumentado' na tabela acima)")
    else:
        print("  variante '1 instrumentado' nao rodou -- Hipotese B nao pode ser lida.")

    # -- funil da revivencia, por variante ------------------------------------
    print("\n" + "=" * 190)
    print("FUNIL DA REVIVENCIA -- por variante (mostra onde a oportunidade nasce e onde ela morre)")
    print("=" * 190)
    for rot in VARIANTES_REVIVENCIA:
        r = resultados.get(rot)
        if r is None:
            continue
        d = r["diag"]
        print(f"  {rot}")
        print(f"    mortos capturados: {d.mortos_capturados}  |  substituidos sem reviver: "
              f"{d.mortos_substituidos_sem_reviver}  |  expirados sem reviver: {d.mortos_expirados_sem_reviver}")
        print(f"    revivencias armadas: {d.revivencias_armadas}  |  preenchidas: "
              f"{d.revivencias_preenchidas}  |  expiraram sem fill: {d.revivencias_expiradas_sem_fill}  |  "
              f"checagem mecanica falhou: {d.mec_falhou_revivencia}")
        print(f"    oportunidade perdida (motor nao piramida): posicao ja aberta "
              f"{d.perdidas_posicao_aberta}x  |  ordem ja pendente {d.perdidas_ordem_pendente}x")

    print("\n" + "=" * 190)
    print("COMO LER")
    print("=" * 190)
    print("  * So' o IS. O OOS fica INTACTO -- nao foi consultado nesta rodada.")
    print("  * 'fila NAO CALIBRADA' para WIN@: premissa OTIMISTA dos dois lados, igual em toda linha.")
    print("  * Regra do dono: se o efeito nao for evidente (poucas operacoes, ou breakeven dentro do")
    print("    IC95%), NAO ha para que mudar a producao.")
    print("\nFIM.")


if __name__ == "__main__":
    main()
