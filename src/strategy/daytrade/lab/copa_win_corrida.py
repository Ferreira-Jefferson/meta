"""`copa_win_corrida` — segue a CORRIDA de barras M1 consecutivas no mesmo
sentido no mini-indice (WIN), em vez de romper faixa (`copa_win.py`).

## Definicao de corrida (a mesma da medicao independente)

Barras M1 consecutivas, dentro do MESMO pregao, com o mesmo sinal de
`close_t - close_{t-1}`. Barra de retorno ZERO nao quebra nem estende a
corrida — fica fora da analise direcional, o estado (direcao + comprimento)
so muda numa barra com `close_t != close_{t-1}`.

## O numero que motivou o desenho

Medicao independente (pandas puro, sem o motor, sobre
`data/raw_intraday/WIN_A_.parquet` ate 2026-06-12): esperar a corrida
confirmar k barras seguidas e entrar NA DIRECAO dela, saindo quando ela
quebra, deu saldo positivo por pregao/contrato mesmo com custo TOTAL
(tarifa + slippage de mercado nas duas pernas). k=3 e' a linha EXAUSTIVA —
toda corrida que chega a 3 barras vira ou `len==3` (erro: quebra na barra
seguinte) ou `len>=4` (acerto: continua), sem meio-termo — e mediu
+R$1.372,82/pregao. Ver `tests/test_copa_win_corrida.py` para os casos
sinteticos e `scripts/daytrade/sweep_corrida.py`/o relatorio da validacao
para a comparacao motor x medicao.

O motor REAL diverge do pandas idealizado em pontos conhecidos e
INTENCIONAIS, nao bugs: (1) toda acao (`Enter`/`Exit`) so executa na
ABERTURA da barra SEGUINTE a que a gerou, nunca no fechamento que a gerou
(regra 4 do AGENTS.md); (2) o motor zera a posicao a forca no fim do
pregao mesmo que a corrida nao tenha quebrado ainda; (3) as duas pernas
pagam slippage de mercado de verdade (`Enter` e `Exit` sao sempre ordem a
mercado aqui — nao ha ordem-limite/maker neste desenho, `pernas_maker=0`).

## Nada de nivel de preco atravessa a virada do pregao

A corrida (direcao + comprimento + ultimo fechamento visto) reseta inteira
em `on_session_start` — mesmo motivo de `copa_win.py`: a serie continua
(`WIN@`) tem emenda de rolagem que se esconde dentro do ruido overnight
normal, e um sinal calculado sobre `close_t - close_{t-1}` que atravessasse
a virada mediria a rolagem como se fosse movimento real do pregao.

## O teto de contratos e' ENTRADA, nunca constante

Mesma regra de `copa_win.CopaWin`: `teto_contratos` e' obrigatorio, sem
default, e todo tamanho e' fracao dele (`quantidade_por_entrada`). Nenhum
literal 12/15 aparece neste arquivo.

## Versao 1: deliberadamente crua, fiel a medicao

`stop_pontos=None` e `max_entradas_dia=None` por padrao — a medicao
original nao tinha stop e nao limitava entradas (~65 gatilhos/pregao em
k=3). Os dois parametros EXISTEM so para o sweep (`scripts/daytrade/
sweep_corrida.py`) testar depois; um default restritivo aqui esconderia
exatamente o resultado que esta versao existe para validar.
"""
from __future__ import annotations

from datetime import time

import pandas as pd

from strategy.daytrade.base import (
    Bar,
    Enter,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    no_tick,
)


class CopaWinCorrida(IntradayStrategy):
    """Segue a corrida: confirma `confirmacao_barras` seguidas no mesmo
    sentido e entra NA DIRECAO dela; sai quando a corrida quebra (barra
    fecha contra a direcao vigente). Uma posicao por vez — o motor recusa
    `Enter` com posicao ja aberta (ver `backtest/intraday/machine.py`,
    `IntradaySessionMachine.on_closed_bar`, comentario "Enter com posicao
    ja aberta ... descartado")."""

    name = "copa_win_corrida"
    version = "0.1"
    symbol = "WIN@"
    feed_kind = "m1"
    # As duas pernas (entrada por confirmacao, saida por quebra) sao SEMPRE
    # ordem a mercado — nao ha EnterLimit/target neste desenho. Zero para o
    # pedagio de fila (`copa_lab.config`, `pedagio_ticks x pernas_maker`) nao
    # ter efeito nenhum aqui: fila so importa para quem fica PARADO no
    # nivel, e este robo nunca fica.
    pernas_maker = 0

    def __init__(
        self,
        teto_contratos: int,
        symbol: str = "WIN@",
        confirmacao_barras: int = 3,
        fracao_entrada: float = 1.0,
        stop_pontos: float | None = None,
        max_entradas_dia: int | None = None,
        hora_inicio: time | None = None,
        hora_fim: time | None = None,
        tick_size: float = 5.0,
    ):
        """`teto_contratos`: teto de contratos SIMULTANEOS da competicao —
        obrigatorio e sem default, mesma regra de `copa_win.CopaWin`: e' o
        unico limitador de tamanho num ambiente de margem infinita, e
        herdar um numero em silencio aqui seria o mesmo erro que `Gremah`
        evita ao recusar simbolo sem calibracao.

        `confirmacao_barras` (k): comprimento de corrida exigido antes de
        entrar. k=3 (default) e' a linha EXAUSTIVA da medicao — toda
        corrida que chega a 3 barras vira `len==3` (erro) ou `len>=4`
        (acerto), sem meio-termo.

        `fracao_entrada`: fracao do teto por entrada. Default 1.0 (nao
        0.5 como `CopaWin`) porque a medicao original nao fracionava — a
        versao 1 tem que ser fiel a ela; o sweep testa fracoes menores.

        `stop_pontos`: distancia do stop em PONTOS a partir do fechamento
        que confirmou a entrada. `None` (default) desliga — a medicao
        original NAO TINHA stop algum, e esta versao 1 reproduz isso
        fielmente. Existe so para o sweep testar depois.

        `max_entradas_dia`: teto de entradas por pregao. `None` (default,
        deliberado) — a medicao nao limitava (~65 gatilhos/pregao em k=3),
        e um teto congelado aqui e' exatamente o tipo de limite que
        esconderia o resultado que esta tarefa existe para validar.

        `hora_inicio`/`hora_fim`: janela de horario (mesma convencao de
        `IntradayBacktestConfig.session_end_time` — UTC, comparado direto
        contra `ts.time()`, porque as barras salvas por
        `market_data_intraday` tem index UTC) em que NOVAS entradas sao
        aceitas. So filtra ENTRADA — uma posicao ja aberta continua
        vigiada (a corrida pode quebrar e sair) mesmo fora da janela.
        `None` (default) = pregao inteiro.

        `tick_size`: grade de preco do WIN (5,0 pontos, `WINV26` — a serie
        continua reporta 1,0, ver `backtest.intraday.profiles.
        SymbolProfile.price_tick_size`). So usado para arredondar o stop
        (`stop_pontos`) na grade do book, quando declarado."""
        if teto_contratos < 1:
            raise ValueError(
                f"copa_win_corrida: `teto_contratos` tem de ser >= 1, veio "
                f"{teto_contratos!r}. O teto e' entrada de configuracao (as "
                "regras da Copa podem mudar antes de 14/09/2026), nunca "
                "constante no codigo."
            )
        if confirmacao_barras < 1:
            raise ValueError(
                f"copa_win_corrida: `confirmacao_barras` tem de ser >= 1, "
                f"veio {confirmacao_barras!r}."
            )
        self.symbol = symbol
        self.teto_contratos = int(teto_contratos)
        self.confirmacao_barras = int(confirmacao_barras)
        self.fracao_entrada = float(fracao_entrada)
        self.stop_pontos = None if stop_pontos is None else float(stop_pontos)
        self.max_entradas_dia = None if max_entradas_dia is None else int(max_entradas_dia)
        self.hora_inicio = hora_inicio
        self.hora_fim = hora_fim
        self.tick_size = float(tick_size)

        # Ultimo fechamento visto NESTE pregao — `None` na primeira barra do
        # dia (ainda nao ha o que diferenciar). `_run_dir`: +1 alta, -1
        # baixa, 0 nenhuma corrida em curso ainda.
        self._last_close: float | None = None
        self._run_dir: int = 0
        self._run_len: int = 0
        self._entradas_hoje = 0

    # ---------- tamanho: sempre fracao do teto ----------------------------

    @property
    def quantidade_por_entrada(self) -> int:
        """`max(1, round(teto x fracao))` — piso de 1 contrato porque uma
        entrada de zero contratos nao e' "menor", e' nenhuma."""
        return max(1, round(self.teto_contratos * self.fracao_entrada))

    # ---------- ciclo do pregao -------------------------------------------

    def on_session_start(self, session_date) -> None:
        """Zera tudo — nenhum nivel/estado de corrida atravessa a virada do
        pregao (regra dura: a emenda de rolagem da serie continua se
        esconde dentro do ruido overnight normal, ver a docstring do
        modulo)."""
        self._last_close = None
        self._run_dir = 0
        self._run_len = 0
        self._entradas_hoje = 0

    # ---------- decisao ----------------------------------------------------

    def _dentro_da_janela(self, ts: pd.Timestamp) -> bool:
        hora = ts.time()
        if self.hora_inicio is not None and hora < self.hora_inicio:
            return False
        if self.hora_fim is not None and hora > self.hora_fim:
            return False
        return True

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        acoes: list[IntradayAction] = []
        try:
            if self._last_close is None:
                # primeira barra do pregao -- ainda nao ha um `close_{t-1}`
                # para comparar (regra 4 do AGENTS.md: nada de olhar o dia
                # anterior para preencher isso).
                return acoes

            diff = bar.close - self._last_close
            if diff > 0:
                quebrou = self._run_dir == -1
                self._run_len = self._run_len + 1 if self._run_dir == 1 else 1
                self._run_dir = 1
            elif diff < 0:
                quebrou = self._run_dir == 1
                self._run_len = self._run_len + 1 if self._run_dir == -1 else 1
                self._run_dir = -1
            else:
                # retorno zero: nao estende nem quebra a corrida -- fora da
                # analise direcional, mesma convencao da medicao.
                quebrou = False

            if positions:
                if quebrou:
                    acoes.append(Exit(reason="corrida_quebrou"))
                return acoes

            if self._run_len != self.confirmacao_barras:
                return acoes
            if self.max_entradas_dia is not None and self._entradas_hoje >= self.max_entradas_dia:
                return acoes
            if not self._dentro_da_janela(ts):
                return acoes

            self._entradas_hoje += 1
            side = "long" if self._run_dir == 1 else "short"
            stop = None
            if self.stop_pontos is not None:
                nivel = bar.close - self.stop_pontos if side == "long" else bar.close + self.stop_pontos
                stop = no_tick(nivel, self.tick_size)
            acoes.append(Enter(
                side=side,
                quantity=self.quantidade_por_entrada,
                initial_stop=stop,
                metadata={"run_len": self._run_len, "entrada_n": self._entradas_hoje},
                reason=f"corrida_{side}_{self.confirmacao_barras}",
            ))
            return acoes
        finally:
            # SEMPRE no fim, depois da decisao ja tomada: `close_t` so vira
            # `close_{t-1}` (referencia da PROXIMA barra) depois que a barra
            # corrente terminou de ser julgada contra o `close_{t-1}` dela
            # mesma -- mesmo padrao de `copa_win.py` (`self._faixa.append`
            # em `finally`), so que aqui o que atravessa e' um escalar, nao
            # uma janela.
            self._last_close = bar.close
