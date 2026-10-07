# -*- coding: utf-8 -*-
"""`WinBuscaLucroG04CrossWdo` -- Geracao 4 da busca por um EA lucrativo do WIN.

Mandato do dono (`ORQUESTRACAO.md`, Geracoes 1-3): as tres geracoes anteriores
morreram por FREQUENCIA (R61 14 trades, R65 4 trades) ou por geometria que so'
sobra positiva quando o stop e' pequeno demais para o M1 resolver com
confianca (R57, stop mediano 35 pontos, 66,7% das saidas do OOS-1 trocaram de
sinal nos ticks reais -- item 6.47). Esta geracao parte de um achado de um
estudo ANTERIOR, fora desta linha (2026-09-15, "confirmacao cruzada
WIN x WDO, estado anomalo"): WIN@ e WDO@ normalmente andam em correlacao
NEGATIVA forte nos incrementos de minuto; existe um estado RARO em que os
DOIS andam na MESMA direcao por uma janela curta -- uma anomalia, dado que
deveriam andar opostos -- e a hipotese e' que a correlacao negativa tende a
se RESTAURAR depois dessa anomalia (reversao) ou que a propria anomalia
carrega informacao nova que se confirma (continuacao). O numero do estudo
antigo NAO e' reaproveitado aqui (pode ter usado janela fora de jan-jun/2026)
-- esta geracao REMEDE a correlacao e redefine o estado anomalo do zero,
so' com dado desta busca (jan-jun/2026 IS, jul-ago/2026 OOS-1).

## Excecao DECLARADA a regra 2 do AGENTS.md (estrategia pura de 1 simbolo)

A hipotese e' estruturalmente de DOIS instrumentos: o estado anomalo so'
existe na relacao entre os incrementos do WIN e do WDO. O motor
(`backtest/intraday/engine.py`) e `IntradayStrategy.on_bar` so' entregam a
barra do SIMBOLO operado (WIN@) -- nao ha' caminho para a estrategia ler WDO@
barra a barra sem mudar o motor (fora do escopo desta geracao). A solucao
adotada: o estado anomalo cruzado e' uma FUNCAO PURA module-level,
`estado_anomalo_cruzado(close_win, close_wdo, ...)`, que recebe as DUAS series
de fechamento M1 alinhadas por timestamp e devolve (anomalo: bool, direcao:
int) por minuto -- CAUSAL (so' usa dado <= t; o quantil de corte usa so' dias
INTEIROS estritamente ANTERIORES ao dia corrente, nunca o dia em curso nem o
futuro). O harness (`g04_base.py`) chama essa funcao UMA VEZ, fora do loop do
motor, e passa o resultado pre-computado ao construtor da estrategia como
duas `pd.Series` (`wdo_anomalo`, `wdo_direcao`) -- `on_bar` so' faz
`dict.get(ts)`, nenhum calculo de estado cruzado acontece dentro do loop.
Isto preserva o espirito da regra (sinal = funcao deterministica e CAUSAL do
dado de mercado, sem I/O, sem banco) mesmo precisando de dois simbolos; ao
portar para MQL5 o equivalente e' ler `iClose("WDO$", PERIOD_M1, i)` do
simbolo irmao e recalcular o mesmo quantil causal -- o METODO e' portavel,
so' o jeito de entregar o dado a` funcao muda (chamada direta no lugar de
tabela pre-computada).

## O estado anomalo

`janela_min` minutos de "delta" (fechamento atual menos fechamento de
`janela_min` barras atras, DENTRO do mesmo pregao -- nunca atravessa a
virada de sessao) para os DOIS instrumentos. Anomalia = os dois deltas tem o
MESMO sinal (nao-zero) E cada `|delta|` esta acima do quantil `quantil`
calculado causalmente (ver acima). `janela_min` e `quantil` sao parametros a
testar no IS (nao chutados do estudo antigo).

## A aposta tradavel -- so' no WIN@, WDO so' como FILTRO

Ao identificar uma anomalia NOVA (borda de subida: anomalo(t) e nao
anomalo(t-1) -- o estado so' dispara uma vez por episodio, nao a cada barra
em que a condicao continua verdadeira), a direcao da aposta e' PARAMETRO:

- `direcao_aposta="continuacao"`: WIN entra NA MESMA direcao do movimento
  conjunto (aposta que o movimento anomalo carrega informacao nova).
- `direcao_aposta="reversao"`: WIN entra NA DIRECAO CONTRARIA (aposta que a
  correlacao negativa normal se restaura via reversao do WIN).

## Principio do dono -- inegociavel, sem parametro que desligue

A direcao implicada pela anomalia so' vira ordem se coincidir com a direcao
da PERNADA MAIOR do WIN em curso (zigzag causal de `pernada_pontos`, mesma
definicao de R43/G1-G3: zigzag sobre o CAMINHO da vela -- vela de alta anda
minima->maxima, vela de baixa anda maxima->minima). Se a anomalia apontar
contra a pernada maior, a entrada e' DESCARTADA -- contada em
`stats_contra_tendencia`, nunca vira `EnterLimit`.

## Execucao -- o desenho fechado, sem excecao (CLAUDE.md)

Entrada so' por `EnterLimit` com `ttl_barras_entrada` obrigatorio, limite
colocada `buffer_entrada_pontos` pontos ATRAS do fechamento corrente (espera
um pequeno recuo a favor, mesma logica mecanica de `WinRetangulo`/G3: limite
de compra so' descansa ABAIXO do preco corrente, de venda so' ACIMA). Stop e
alvo em PONTOS fixos (`stop_pontos`, `alvo_multiplo x stop_pontos`,
`alvo_multiplo >= 3.0` por construcao -- `ValueError` abaixo disso). Alvo so'
como ordem-limite real fatiada (`exit_split_unit`), SEM prazo
(`exit_ttl_bars=None`); so' o stop e' a mercado; `anchor_exits_at_fill=True`;
`target_fills_as_maker=True`. 1 contrato FIXO (sem escala por caixa --
dimensionamento dinamico fica para geracao futura, mesma decisao de
G1-G3/`WinRetangulo`).

## Fila -- WIN@ nao tem fidelidade calibrada

Mesma ressalva de toda a linha: `queue_ahead_qty=0`/`exit_queue_ahead_qty=0`
(enche no toque), premissa OTIMISTA declarada, identica nas duas janelas.

## Contadores de auditoria (licao da Geracao 2 / item 6.48 de LICOES_DE_PRODUCAO.md)

`stats_bruto` conta toda ocorrencia BRUTA da BORDA de anomalia com direcao
definida (sinal != 0), ANTES de qualquer filtro de tendencia/execucao/capital
-- e' o contador que teria denunciado mais cedo o bug de ordem-de-operacoes
da G2 (zero ordens emitidas com bruto>0 sem explicacao). `stats_contra_
tendencia` conta as descartadas so' pelo filtro de tendencia (R43).
`stats_ordens_emitidas` conta so' as que viraram `EnterLimit` de verdade. A
checagem "estado calculado ANTES de checar ordem pendente" (o bug da G2) e'
replicada aqui: `on_bar` decide `pode_armar` com o `_espera` do INICIO da
barra, atualiza a perna maior e le a borda de anomalia depois, e so' entao
decide se emite -- nunca o inverso.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

#: Limiar da pernada maior (zigzag causal sobre o caminho da vela, R43).
#: Nao e' parametro desta geracao -- e' o mesmo valor usado em G1-G3.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Dias INTEIROS de historico, estritamente anteriores ao dia corrente,
#: exigidos antes do quantil causal comecar a valer. Antes disso o estado
#: anomalo fica sempre False (sem historico suficiente para definir "raro").
MIN_DIAS_BURN_IN = 20


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela, na ordem em que o preco
    provavelmente passou por eles -- definicao CONGELADA em `REGRAS.md`,
    identica a` usada em R43/R65/R57 (G1-G3). Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


def estado_anomalo_cruzado(
    close_win: pd.Series,
    close_wdo: pd.Series,
    janela_min: int = 15,
    quantil: float = 0.75,
    min_dias_burn_in: int = MIN_DIAS_BURN_IN,
) -> tuple[pd.Series, pd.Series]:
    """Funcao PURA (ver docstring do modulo sobre a excecao declarada a`
    regra 2 do AGENTS.md): recebe as series de fechamento M1 (index =
    timestamp) dos DOIS instrumentos e devolve `(anomalo, direcao)`, ambas
    indexadas como `close_win`.

    `anomalo[t]` e' True quando os deltas de `janela_min` minutos (DENTRO do
    mesmo pregao -- `groupby(dia).diff`, nunca atravessa a virada de sessao)
    dos dois instrumentos tem o MESMO sinal e cada `|delta|` esta acima do
    quantil causal daquele instrumento (calculado so' com dias INTEIROS
    estritamente anteriores ao dia de `t`, burn-in de `min_dias_burn_in`
    dias -- nunca olha o dia corrente nem o futuro).

    `direcao[t]` e' o sinal comum (+1/-1) quando `anomalo[t]`, 0 caso
    contrario.
    """
    idx = close_win.index.intersection(close_wdo.index).sort_values()
    win = close_win.reindex(idx)
    wdo = close_wdo.reindex(idx)
    dia = pd.Series(idx.date, index=idx)

    delta_win = win.groupby(dia).diff(janela_min)
    delta_wdo = wdo.groupby(dia).diff(janela_min)
    abs_win = delta_win.abs()
    abs_wdo = delta_wdo.abs()

    dias_ordenados = sorted(dia.unique())
    thr_win_por_dia: dict = {}
    thr_wdo_por_dia: dict = {}
    acumulado_win: list[np.ndarray] = []
    acumulado_wdo: list[np.ndarray] = []
    for i, d in enumerate(dias_ordenados):
        if i >= min_dias_burn_in:
            vals_win = np.concatenate(acumulado_win)
            vals_wdo = np.concatenate(acumulado_wdo)
            thr_win_por_dia[d] = float(np.quantile(vals_win, quantil))
            thr_wdo_por_dia[d] = float(np.quantile(vals_wdo, quantil))
        else:
            thr_win_por_dia[d] = None
            thr_wdo_por_dia[d] = None
        mask_dia = (dia == d).values
        acumulado_win.append(abs_win.values[mask_dia][~np.isnan(abs_win.values[mask_dia])])
        acumulado_wdo.append(abs_wdo.values[mask_dia][~np.isnan(abs_wdo.values[mask_dia])])

    thr_win = dia.map(thr_win_por_dia)
    thr_wdo = dia.map(thr_wdo_por_dia)

    tem_historico = thr_win.notna() & thr_wdo.notna()
    sinal_win = np.sign(delta_win)
    sinal_wdo = np.sign(delta_wdo)
    mesmo_sinal = (sinal_win == sinal_wdo) & (sinal_win != 0)
    acima_win = abs_win >= thr_win.astype(float)
    acima_wdo = abs_wdo >= thr_wdo.astype(float)

    anomalo = (tem_historico & mesmo_sinal & acima_win & acima_wdo).fillna(False)
    direcao = pd.Series(np.where(anomalo, sinal_win, 0), index=idx).astype(int)
    anomalo = anomalo.reindex(close_win.index, fill_value=False)
    direcao = direcao.reindex(close_win.index, fill_value=0)
    return anomalo, direcao


class WinBuscaLucroG04CrossWdo(IntradayStrategy):
    """Opera o WIN@ quando WIN@ e WDO@ andam, por uma janela curta, na MESMA
    direcao -- estado ANOMALO dado que normalmente andam opostos. WDO entra
    so' como FILTRO/GATILHO (nunca como posicao). Sempre a favor da pernada
    maior do WIN (R43, principio inegociavel) -- Geracao 4 da busca por um
    EA lucrativo do WIN (`ORQUESTRACAO.md`)."""

    name = "win_busca_lucro_g04_cross_wdo"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        wdo_anomalo: pd.Series,
        wdo_direcao: pd.Series,
        symbol: str | None = None,
        direcao_aposta: str = "reversao",
        pernada_pontos: float = PERNADA_PONTOS,
        stop_pontos: float = 150.0,
        alvo_multiplo: float = 5.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        if direcao_aposta not in ("continuacao", "reversao"):
            raise ValueError(f"direcao_aposta={direcao_aposta!r} invalido -- "
                              "'continuacao' ou 'reversao'")
        if pernada_pontos <= 0:
            raise ValueError("pernada_pontos tem que ser positivo")
        if stop_pontos <= 0:
            raise ValueError("stop_pontos tem que ser positivo")
        if alvo_multiplo < 3.0:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo de 3x -- fere a disciplina "
                f"alvo >= 3x o stop do mandato do dono")
        if buffer_entrada_pontos < 0:
            raise ValueError("buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if symbol is not None:
            self.symbol = symbol
        self._wdo_anomalo = wdo_anomalo.to_dict() if isinstance(wdo_anomalo, pd.Series) else dict(wdo_anomalo)
        self._wdo_direcao = wdo_direcao.to_dict() if isinstance(wdo_direcao, pd.Series) else dict(wdo_direcao)
        self.direcao_aposta = direcao_aposta
        self.pernada_pontos = float(pernada_pontos)
        self.stop_pontos = float(stop_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (licao da G2 / item 6.48) --
        self.stats_bruto = 0
        self.stats_contra_tendencia = 0
        self.stats_ordens_emitidas = 0

        self._reset_sessao()

    # -- estado por sessao --------------------------------------------------
    def _reset_sessao(self) -> None:
        # pernada maior (R43) -- WIN@ e' serie continua com emenda de
        # rolagem, nenhum nivel de preco atravessa a sessao (mesmo motivo de
        # WinRetangulo/G1-G3).
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        # borda de anomalia (dispara so' na TRANSICAO False->True)
        self._anomalo_anterior = False
        # ordem pendente (uma por vez)
        self._espera: int | None = None
        self._hist: deque[Bar] = deque(maxlen=4)

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._espera = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._espera = None

    # -- pernada maior (R43) --------------------------------------------------
    def _atualiza_perna(self, p: float) -> None:
        if self._origem is None:
            self._origem = p
            self._extremo = p
            return
        s = self._direcao
        if s is None:
            if p - self._origem >= self.pernada_pontos:
                self._direcao = 1
                self._extremo = p
            elif self._origem - p >= self.pernada_pontos:
                self._direcao = -1
                self._extremo = p
            return
        if s == 1:
            if p > self._extremo:
                self._extremo = p
            elif self._extremo - p >= self.pernada_pontos:
                self._origem = self._extremo
                self._direcao = -1
                self._extremo = p
        else:
            if p < self._extremo:
                self._extremo = p
            elif p - self._extremo >= self.pernada_pontos:
                self._origem = self._extremo
                self._direcao = 1
                self._extremo = p

    def _monta_entrada(self, direcao_entrada: int, bar: Bar) -> IntradayAction | None:
        buf = self.buffer_entrada_pontos
        if direcao_entrada == 1:
            lado = "long"
            limite = bar.close - buf
            stop = limite - self.stop_pontos
            alvo = limite + self.alvo_multiplo * self.stop_pontos
        else:
            lado = "short"
            limite = bar.close + buf
            stop = limite + self.stop_pontos
            alvo = limite - self.alvo_multiplo * self.stop_pontos

        limite = no_tick(limite, self.tick_size)
        # Conferencia MECANICA (mesmo criterio de WinRetangulo/G3): limite de
        # compra so' descansa ABAIXO do preco corrente, de venda so' ACIMA --
        # uma limite do lado errado e' ordem a mercado disfarcada.
        if lado == "long" and limite >= bar.close:
            return None
        if lado == "short" and limite <= bar.close:
            return None

        self._espera = 0
        return EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=f"g04_cross_wdo_{self.direcao_aposta}_s{self.stop_pontos:.0f}_a{self.alvo_multiplo:.0f}x",
        )

    # -- loop -----------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)

        # Decide ANTES de atualizar qualquer estado se este robo PODE armar
        # uma ordem nova nesta barra -- com o `_espera` que existia no INICIO
        # da barra (licao da Geracao 2 / item 6.48, ver docstring do modulo).
        pode_armar = True
        if positions:
            self._espera = None
            pode_armar = False
        elif self._espera is not None:
            self._espera += 1
            if self._espera < self.ttl_barras_entrada:
                pode_armar = False
            else:
                self._espera = None

        # Atualiza a pernada maior (sempre roda, nao condicionado a pode_armar).
        for p in _caminho_da_barra(bar):
            self._atualiza_perna(p)

        # Le a borda de anomalia PRE-COMPUTADA (lookup puro, nenhum calculo
        # cruzado acontece aqui).
        anomalo_agora = bool(self._wdo_anomalo.get(ts, False))
        direcao_sinal = int(self._wdo_direcao.get(ts, 0))
        disparo_novo = anomalo_agora and not self._anomalo_anterior
        self._anomalo_anterior = anomalo_agora

        if not (disparo_novo and direcao_sinal != 0):
            return []

        # BRUTO: toda borda de anomalia com direcao definida, ANTES de
        # qualquer filtro de tendencia/execucao/capital.
        self.stats_bruto += 1
        direcao_entrada = direcao_sinal if self.direcao_aposta == "continuacao" else -direcao_sinal

        if self._direcao != direcao_entrada:
            # Contra a pernada maior (ou pernada ainda nao definida) --
            # DESCARTA. Principio do dono, sem parametro que desligue.
            self.stats_contra_tendencia += 1
            return []

        if not pode_armar:
            return []

        acao = self._monta_entrada(direcao_entrada, bar)
        if acao is None:
            return []
        self.stats_ordens_emitidas += 1
        return [acao]
