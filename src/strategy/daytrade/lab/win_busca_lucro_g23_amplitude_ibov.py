# -*- coding: utf-8 -*-
"""`WinBuscaLucroG23AmplitudeIbov` -- Geracao 23 da busca por um EA lucrativo
de day trade do WIN (`scripts/daytrade/win_pernadas_exploracao/ea_busca_lucro/`,
ver `ORQUESTRACAO.md`, secao "Fase 3 -- fonte externa").

## Por que esta geracao existe

As Geracoes 17-22 (Fase 2) convergiram 4 de 4 vezes para o MESMO modo de
falha -- concentracao do liquido em poucos pregoes que PIORA do IS para o
OOS-1 (itens 6.52/6.53 de `LICOES_DE_PRODUCAO.md`) -- usando SO' preco/volume
do proprio WIN/WDO. O dono decidiu (2026-10-05) abrir uma Fase 3 com fonte de
informacao genuinamente EXTERNA ao OHLCV do proprio instrumento operado: esta
geracao usa a AMPLITUDE (folego/breadth) de uma cesta de acoes liquidas do
Ibovespa -- quantos papeis sobem vs caem, minuto a minuto -- como sinal de
confirmacao/divergencia para pernadas NASCENTES do WIN.

## Excecao DECLARADA a regra 2 do AGENTS.md (mesmo precedente da G4)

A hipotese e' estruturalmente de MUITOS instrumentos (o WIN + uma cesta de
~20 acoes). O motor (`backtest/intraday/engine.py`) so' entrega ao `on_bar`
a barra do simbolo operado (WIN@). A solucao e' IDENTICA a` da G4
(`win_busca_lucro_g04_cross_wdo.py`): o folego da cesta e' uma FUNCAO PURA
module-level, `folego_ibov(fechamentos, grade, ...)`, que recebe as series
de fechamento M1 de TODOS os papeis da cesta (ja alinhadas/convertidas para
BRT pelo harness) e devolve UMA serie indexada pela GRADE do WIN -- CAUSAL
(cada ponto usa so' dado <= aquele instante: `groupby(dia).diff` reseta por
pregao, nunca atravessa a virada de sessao, e o `ffill` so' carrega para a
FRENTE). O harness (`g23_base.py`) chama essa funcao UMA VEZ fora do loop do
motor e passa o resultado pre-computado ao construtor da estrategia como uma
`pd.Series` -- `on_bar` so' faz `dict.get(ts)`, nenhum calculo de cesta
acontece dentro do loop. Ao portar para MQL5 o METODO e' portavel (ler os
fechamentos dos simbolos irmaos e recalcular o mesmo folego), so' o jeito de
entregar o dado muda.

## A pernada NASCENTE -- dois limiares do MESMO zigzag causal (R43)

`RastreadorPernadaNascente` e' o MESMO mecanismo de zigzag causal sobre o
CAMINHO da vela (vela de alta anda minima->maxima, de baixa maxima->minima)
usado em R43/G1-G22, so' que com DOIS limiares em vez de um:

- `nascente_pontos` (parametro desta geracao, testado no passo de validacao
  causal, tipicamente bem menor que 750): toda vez que o zigzag CONFIRMA uma
  perna nova neste limiar pequeno, isso e' uma "pernada NASCENTE" -- o
  evento tradavel.
- `pernada_pontos=750.0` (constante, a MESMA definicao oficial de pernada de
  toda a busca, NUNCA retunada aqui): se a mesma perna, antes de reverter
  `nascente_pontos` a partir do seu extremo provisorio (o que a mataria e
  comecaria uma nova na direcao oposta), chegar a `pernada_pontos` de
  distancia da origem, ela "CONFIRMOU" -- virou de fato uma pernada oficial.

Isso da' o par (evento nascente, desfecho: confirmou ou morreu) que o passo
1 do mandato mede por tercil de concordancia com o folego ANTES de montar
qualquer estrategia (ver `g23_validacao_causal.py`).

## A aposta tradavel

Ao nascer uma perna nova (`novo_nascente`), mede-se a CONCORDANCIA entre o
folego da cesta e a direcao da perna nascente:
`concordancia = folego[ts] * direcao_nascente` (positivo = a cesta confirma
a mesma direcao da pernada nascente; negativo = a cesta diverge). Direcao da
aposta e' PARAMETRO, testado nas duas leituras (mandato, item 4):

- `direcao_aposta="confirmacao"`: entra NA MESMA direcao da pernada nascente
  quando `concordancia >= limiar_concordancia` (a cesta confirma com forca).
- `direcao_aposta="divergencia"`: entra NA DIRECAO CONTRARIA da pernada
  nascente quando `concordancia <= -limiar_concordancia` (a cesta diverge
  com forca -- aposta que a pernada nascente vai falhar/reverter).

## Execucao -- o desenho fechado, sem excecao (CLAUDE.md)

Entrada so' por `EnterLimit` com `ttl_barras_entrada` obrigatorio, limite
colocada `buffer_entrada_pontos` pontos ATRAS do fechamento corrente (mesma
mecanica de G3/G4/G21: limite de compra so' descansa ABAIXO do preco
corrente, de venda so' ACIMA). Stop e alvo em PONTOS fixos (`stop_pontos`,
`alvo_multiplo x stop_pontos`, `alvo_multiplo >= MULTIPLO_MINIMO=2.0` --
piso do mandato 2026-10-05, `ValueError` abaixo disso). Alvo so' como
ordem-limite real fatiada (`exit_split_unit=quantity`), SEM prazo
(`exit_ttl_bars=None`); so' o stop e' a mercado; `anchor_exits_at_fill=True`;
`target_fills_as_maker=True`. 1 contrato FIXO (sem escala por caixa, mesma
decisao de G1-G21).

## Fila -- WIN@ nao tem fidelidade calibrada

Mesma ressalva de toda a linha: `queue_ahead_qty=0`/`exit_queue_ahead_qty=0`
(enche no toque), premissa OTIMISTA declarada, identica em todas as janelas.

## Contadores de auditoria (licao da Geracao 2 / item 6.48)

`stats_bruto` conta toda ocorrencia BRUTA de pernada nascente com direcao
definida, ANTES de qualquer filtro de folego/execucao/capital.
`stats_sem_confirmacao_externa` conta as descartadas so' porque a
concordancia nao passou o limiar. `stats_ordens_emitidas` conta so' as que
viraram `EnterLimit` de verdade. A ordem de operacoes (decidir `pode_armar`
com o `_espera` do INICIO da barra, atualizar o rastreador depois, e so'
entao decidir se emite) replica a correcao da G2/G4 -- nunca o inverso.
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

#: Limiar oficial da pernada maior (zigzag causal, R43) -- NAO e' parametro
#: desta geracao, e' o mesmo valor usado em G1-G22.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela, na ordem em que o preco
    provavelmente passou por eles -- definicao CONGELADA em `REGRAS.md`,
    identica a` usada em R43/R65/R57/G4 (G1-G22). Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


class RastreadorPernadaNascente:
    """Zigzag causal de DOIS limiares sobre o caminho da barra (mesma
    convencao R43/G1-G22). `nascente_pontos` marca o nascimento observavel de
    uma possivel pernada nova; se a MESMA perna, antes de reverter
    `nascente_pontos` a partir do seu extremo provisorio (o que a mataria),
    chegar a `pernada_pontos` de distancia da origem, ela CONFIRMOU -- virou
    pernada oficial (mesma definicao de toda a busca). Pura, roda ponto a
    ponto, para ser IDENTICA entre a validacao causal (`g23_validacao_
    causal.py`) e o `on_bar` da estrategia -- nunca duas implementacoes do
    mesmo zigzag (risco de divergencia silenciosa)."""

    def __init__(self, nascente_pontos: float, pernada_pontos: float = PERNADA_PONTOS) -> None:
        if not 0 < nascente_pontos < pernada_pontos:
            raise ValueError(
                f"nascente_pontos={nascente_pontos} tem que estar em "
                f"(0; {pernada_pontos}) -- o limiar nascente e' sempre MENOR "
                f"que a pernada oficial")
        self.nascente_pontos = float(nascente_pontos)
        self.pernada_pontos = float(pernada_pontos)
        self._origem: float | None = None
        self._direcao: int | None = None
        self._extremo: float | None = None
        self._ja_confirmou = False

    def processa(self, p: float) -> dict:
        """Um ponto do caminho. Devolve os eventos desta chamada:
        `novo_nascente` (bool), `direcao_nascente` (int, so' valido quando
        `novo_nascente`), `confirmou_750` (bool -- a perna EM CURSO, nao a
        que acabou de nascer nesta MESMA chamada, atingiu `pernada_pontos`;
        edge-triggered, uma vez por perna)."""
        ev = dict(novo_nascente=False, direcao_nascente=0, confirmou_750=False)
        if self._origem is None:
            self._origem = p
            self._extremo = p
            return ev
        s = self._direcao
        if s is None:
            if p - self._origem >= self.nascente_pontos:
                self._direcao, self._extremo = 1, p
                self._ja_confirmou = False
                ev["novo_nascente"], ev["direcao_nascente"] = True, 1
            elif self._origem - p >= self.nascente_pontos:
                self._direcao, self._extremo = -1, p
                self._ja_confirmou = False
                ev["novo_nascente"], ev["direcao_nascente"] = True, -1
            return ev
        if s == 1:
            if p > self._extremo:
                self._extremo = p
            elif self._extremo - p >= self.nascente_pontos:
                self._origem, self._direcao, self._extremo = self._extremo, -1, p
                self._ja_confirmou = False
                ev["novo_nascente"], ev["direcao_nascente"] = True, -1
                return ev
        else:
            if p < self._extremo:
                self._extremo = p
            elif p - self._extremo >= self.nascente_pontos:
                self._origem, self._direcao, self._extremo = self._extremo, 1, p
                self._ja_confirmou = False
                ev["novo_nascente"], ev["direcao_nascente"] = True, 1
                return ev
        if not self._ja_confirmou and abs(self._extremo - self._origem) >= self.pernada_pontos:
            self._ja_confirmou = True
            ev["confirmou_750"] = True
        return ev


def folego_ibov(
    fechamentos: dict[str, pd.Series],
    grade: pd.DatetimeIndex,
    janela_min: int = 15,
    ffill_limite_min: int = 10,
    min_fracao_validos: float = 0.5,
) -> pd.Series:
    """Folego (breadth) CAUSAL da cesta, indexado pela `grade` (tipicamente
    os timestamps das proprias barras do WIN@ operadas nos dias em questao).

    Para cada papel: reindexa o fechamento M1 do papel na `grade` com
    `ffill` (limitado a `ffill_limite_min` posicoes -- so' carrega o ultimo
    preco conhecido por alguns minutos de silencio, nunca atravessa a virada
    de pregao: o `groupby(dia).diff` abaixo zera o delta nos primeiros
    `janela_min` minutos de cada dia de qualquer forma, e' o proprio pandas
    que faz isso). Delta de `janela_min` minutos DENTRO do mesmo pregao
    (`groupby(dia).diff(janela_min)`); sinal do delta (+1 subiu, -1 caiu,
    0/NaN sem informacao). Folego = media dos sinais validos naquele minuto,
    em [-1; +1] -- NaN se menos de `min_fracao_validos` dos papeis da cesta
    tem sinal valido (ex.: antes da abertura das acoes, que comeca depois do
    WIN@).
    """
    if janela_min <= 0:
        raise ValueError("janela_min tem que ser positivo")
    if not fechamentos:
        raise ValueError("fechamentos vazio -- nenhum papel na cesta")
    dia = pd.Series(grade.date, index=grade)
    sinais = []
    for serie in fechamentos.values():
        s = serie.sort_index()
        s = s[~s.index.duplicated(keep="first")]
        precos = s.reindex(grade, method="ffill", limit=ffill_limite_min)
        delta = precos.groupby(dia).diff(janela_min)
        sinais.append(np.sign(delta.to_numpy()))
    mat = np.vstack(sinais)  # (n_papeis, len(grade))
    validos = (~np.isnan(mat)).sum(axis=0)
    soma = np.nansum(mat, axis=0)
    minimo = min_fracao_validos * len(fechamentos)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = soma / np.maximum(validos, 1)
    breadth = np.where(validos >= minimo, media, np.nan)
    return pd.Series(breadth, index=grade)


class WinBuscaLucroG23AmplitudeIbov(IntradayStrategy):
    """Entra a favor (ou contra, conforme `direcao_aposta`) de uma pernada
    NASCENTE do WIN quando o folego de uma cesta de acoes liquidas do
    Ibovespa concorda (ou diverge) com forca suficiente -- Geracao 23 da
    busca por um EA lucrativo do WIN, Fase 3 (fonte EXTERNA), ORQUESTRACAO.md."""

    name = "win_busca_lucro_g23_amplitude_ibov"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    #: Piso do mandato 2026-10-05.
    MULTIPLO_MINIMO = 2.0

    def __init__(
        self,
        folego: pd.Series,
        symbol: str | None = None,
        direcao_aposta: str = "confirmacao",
        nascente_pontos: float = 300.0,
        pernada_pontos: float = PERNADA_PONTOS,
        stop_pontos: float | None = None,
        alvo_multiplo: float = 3.0,
        limiar_concordancia: float = 0.2,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        if direcao_aposta not in ("confirmacao", "divergencia"):
            raise ValueError(
                f"direcao_aposta={direcao_aposta!r} invalido -- "
                "'confirmacao' ou 'divergencia'")
        if nascente_pontos <= 0:
            raise ValueError("nascente_pontos tem que ser positivo")
        stop_pontos = float(stop_pontos) if stop_pontos is not None else float(nascente_pontos)
        if stop_pontos <= 0:
            raise ValueError("stop_pontos tem que ser positivo")
        if alvo_multiplo < self.MULTIPLO_MINIMO:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo de {self.MULTIPLO_MINIMO}x -- "
                f"fere o piso do mandato 2026-10-05 (perda>=ganho continua proibido)")
        if not 0.0 <= limiar_concordancia <= 1.0:
            raise ValueError("limiar_concordancia tem que estar em [0; 1]")
        if buffer_entrada_pontos < 0:
            raise ValueError("buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if symbol is not None:
            self.symbol = symbol
        self._folego = folego.to_dict() if isinstance(folego, pd.Series) else dict(folego)
        self.direcao_aposta = direcao_aposta
        self.nascente_pontos = float(nascente_pontos)
        self.pernada_pontos = float(pernada_pontos)
        self.stop_pontos = stop_pontos
        self.alvo_multiplo = float(alvo_multiplo)
        self.limiar_concordancia = float(limiar_concordancia)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (licao da G2/G4 -- item 6.48) --
        self.stats_bruto = 0
        self.stats_sem_confirmacao_externa = 0
        self.stats_ordens_emitidas = 0

        self._reset_sessao()

    # -- estado por sessao --------------------------------------------------
    def _reset_sessao(self) -> None:
        # WIN@ e' serie continua com emenda de rolagem -- nenhum nivel de
        # preco atravessa a sessao (mesmo motivo de G4/G21).
        self._rastreador = RastreadorPernadaNascente(self.nascente_pontos, self.pernada_pontos)
        self._espera: int | None = None

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._espera = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._espera = None

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
        # Conferencia MECANICA (mesmo criterio de G3/G4/G21): limite de
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
            reason=(f"g23_amplitude_{self.direcao_aposta}_n{self.nascente_pontos:.0f}"
                    f"_s{self.stop_pontos:.0f}_a{self.alvo_multiplo:.1f}x"),
        )

    # -- loop -----------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        # Decide ANTES de atualizar qualquer estado se este robo PODE armar
        # uma ordem nova nesta barra -- com o `_espera` que existia no INICIO
        # da barra (licao da G2/G4 / item 6.48 de LICOES_DE_PRODUCAO.md).
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

        # Atualiza o rastreador de pernada nascente (sempre roda, nao
        # condicionado a pode_armar) -- os DOIS pontos do caminho da vela.
        direcao_nascente = 0
        nasceu = False
        for p in _caminho_da_barra(bar):
            ev = self._rastreador.processa(p)
            if ev["novo_nascente"]:
                nasceu = True
                direcao_nascente = ev["direcao_nascente"]

        if not (nasceu and direcao_nascente != 0):
            return []

        # BRUTO: toda pernada nascente com direcao definida, ANTES de
        # qualquer filtro de folego/execucao/capital.
        self.stats_bruto += 1

        concordancia = float(self._folego.get(ts, float("nan"))) * direcao_nascente
        if concordancia != concordancia:  # NaN -- folego indisponivel nesta barra
            self.stats_sem_confirmacao_externa += 1
            return []

        if self.direcao_aposta == "confirmacao":
            if concordancia < self.limiar_concordancia:
                self.stats_sem_confirmacao_externa += 1
                return []
            direcao_entrada = direcao_nascente
        else:  # "divergencia"
            if concordancia > -self.limiar_concordancia:
                self.stats_sem_confirmacao_externa += 1
                return []
            direcao_entrada = -direcao_nascente

        if not pode_armar:
            return []

        acao = self._monta_entrada(direcao_entrada, bar)
        if acao is None:
            return []
        self.stats_ordens_emitidas += 1
        return [acao]
