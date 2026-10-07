"""`win_busca_lucro_g26_retangulo_tendencia` — Geração 26 da busca por EA
lucrativo de day trade do WIN (`scripts/daytrade/win_pernadas_exploracao/
ea_busca_lucro/`, ver `ORQUESTRACAO.md`).

## Por que esta geração existe

Pedido do dono, 2026-10-05, depois de OLHAR o replay de operações da G21
(`.claude/artifacts/g21_retangulo/index.html`): em vários dos prejuízos
visíveis, a entrada ia CONTRA a direção do movimento mais amplo do pregão —
ex. o robô vendia (short) numa retomada até o meio do retângulo, dentro de
um dia que no todo subia. A G21 decide o LADO só pela posição do preço
relativo ao MEIO do retângulo detectado numa janela de 20 barras de 1 min
(20 minutos) — um sinal local, sem nenhuma leitura da tendência mais ampla
do pregão. Isto nunca foi testado nesta busca: a Fase 1 testou tendência
sobre sinais de PREÇO PURO (R43-R47 em `REGRAS.md`, contra-tendência pior
que o acaso) e a G10 testou tendência sobre o ORB/momentum — nenhuma testou
sobre a família retângulo/reversão-ao-meio, que tem uma lógica de direção
estruturalmente diferente (local, de 20 min, não a pernada de 750 nem o
drift do dia inteiro).

## O que esta classe faz

Subclasse de `WinBuscaLucroG21Retangulo1000` — NENHUMA lógica de detecção
nem de geometria de entrada/saída é reimplementada ou alterada. Mantém um
histórico PRÓPRIO e mais longo de barras (`janela_tendencia` M1, até 480 =
8h) só para medir a direção do movimento mais amplo, e intercepta a ação
que `on_bar` do pai devolveria: se for `EnterLimit` e o lado da entrada for
CONTRA a tendência medida, a ação é descartada (retorna `[]` em vez de
mandar a ordem) — a barra de espera (`_barras_esperando`) do pai já foi
zerada por ele mesmo antes de devolver a ação, então o filtro só impede a
ORDEM, não trava o detector nem o relógio de novas tentativas.

**Medida de tendência** (duas famílias, declaradas, não escolhidas depois de
ver o resultado):
  - `"drift_bars"`: sinal de `close[-1] - close[-W]`, com `W` em barras M1
    (1h/2h/4h/8h = 60/120/240/480).
  - `"drift_dia"`: sinal de `close[-1] - abertura_da_sessão` (desde as 09:00
    do próprio pregão) — janela que cresce ao longo do dia, não é um N fixo.

`estrito=False` (default): tendência NEUTRA (sinal 0, ex. `close[-1] ==
close[-W]`) deixa passar os dois lados — só BLOQUEIA quando há tendência
OPOSTA clara. `estrito=True`: só entradas com tendência a favor CLARA (sinal
≠0 e concordante) passam; tendência neutra bloqueia os dois lados também.

## Capital, execução, janelas

Idênticos à G21 (R$1.000, `EnterLimit`/alvo limite fatiado/só stop a
mercado, IS jan-jun → OOS-1 jul-ago único → OOS-2 set só se passar com
folga). Esta classe SÓ adiciona o filtro de tendência; a geometria vencedora
do IS da G21 (`stop_fracao_largura=0,45`, `alvo_fracao_largura=0,90`) é
herdada via `kwargs` no construtor, não hardcoded aqui.
"""
from __future__ import annotations

from collections import deque

from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.win_busca_lucro_g21_retangulo_1000 import (
    WinBuscaLucroG21Retangulo1000,
)

JANELAS_VALIDAS = (60, 120, 240, 480)
MEDIDAS_VALIDAS = ("drift_bars", "drift_dia")


class WinBuscaLucroG26RetanguloTendencia(WinBuscaLucroG21Retangulo1000):
    name = "win_busca_lucro_g26_retangulo_tendencia"
    version = "1.0.0"

    def __init__(
        self,
        medida: str = "drift_bars",
        janela_tendencia: int = 240,
        estrito: bool = False,
        **kwargs,
    ) -> None:
        if medida not in MEDIDAS_VALIDAS:
            raise ValueError(f"medida={medida!r} inválida: {MEDIDAS_VALIDAS}")
        if medida == "drift_bars" and janela_tendencia not in JANELAS_VALIDAS:
            raise ValueError(
                f"janela_tendencia={janela_tendencia} fora da grade declarada "
                f"{JANELAS_VALIDAS} — escolha antes de ver o resultado, não depois")
        super().__init__(**kwargs)
        self.medida = medida
        self.janela_tendencia = int(janela_tendencia)
        self.estrito = bool(estrito)
        self._hist_tend: deque[Bar] = deque(maxlen=self.janela_tendencia + 2)
        self._abertura_sessao: float | None = None

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._hist_tend.clear()
        self._abertura_sessao = None

    def _tendencia(self) -> int:
        """+1 alta, -1 baixa, 0 neutra/sem dado suficiente. Só olha o
        passado (o bar atual já foi appendado antes desta chamada)."""
        if self.medida == "drift_dia":
            if self._abertura_sessao is None or not self._hist_tend:
                return 0
            atual = self._hist_tend[-1].close
            d = atual - self._abertura_sessao
        else:
            if len(self._hist_tend) <= self.janela_tendencia:
                return 0
            atual = self._hist_tend[-1].close
            passado = self._hist_tend[-1 - self.janela_tendencia].close
            d = atual - passado
        return 1 if d > 0 else (-1 if d < 0 else 0)

    def on_bar(
        self,
        ts,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._abertura_sessao is None:
            self._abertura_sessao = bar.open
        self._hist_tend.append(bar)

        acoes = super().on_bar(ts, bar, positions, session_pnl_brl)
        if not acoes:
            return acoes

        tendencia = self._tendencia()
        filtradas: list[IntradayAction] = []
        for acao in acoes:
            lado = getattr(acao, "side", None)
            if lado is None:
                filtradas.append(acao)
                continue
            sinal_lado = 1 if lado == "long" else -1
            if self.estrito:
                passa = (tendencia == sinal_lado)
            else:
                passa = (tendencia == 0) or (tendencia == sinal_lado)
            if passa:
                filtradas.append(acao)
            # ação descartada: a favor da regra do dono (só a favor da
            # tendência) -- `_barras_esperando` do pai já foi zerado antes
            # de devolver a ação, então o detector tenta de novo na próxima
            # barra elegível, não fica travado.
        return filtradas
