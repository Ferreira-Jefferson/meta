# -*- coding: utf-8 -*-
"""`WinBuscaLucroG19OrbSizingGraduado` -- Geracao 19 (Parte 1) da busca por
um EA lucrativo do WIN.

## Mandato (dono, 2026-10-05) -- Parte 1

A R$1.000 cabem de verdade ate' ~4 contratos (`contracts_from_capital_
operacional`: 1o exige so' a margem crua R$100, do 2o em diante a pilha
cheia R$250 cada). A G11 (`win_busca_lucro_g11_orb_tamanho_graduado.py`,
R$250, 1 contrato) so' podia traduzir "tamanho de mao graduado pela forca
do sinal" como SELECAO binaria (opera/nao opera o balde) -- e mediu, por
estratificacao POS-HOC dos 121 trades reais da REF (item 6.50, nunca
simulacoes exclusivas separadas), que a forca do rompimento ORB NAO
correlaciona com o resultado do trade (corr(forca,pnl)=-0,027,
corr(forca,venceu?)=-0,023, z forte-vs-fraco=-0,09 -- indistinguivel de
ruido). Esta geracao reconfirma esse achado com CONTRATOS DE VERDADE
variando por balde (nao mais 0/1) e mede o efeito na VARIANCIA/RUINA,
nao na esperanca -- a predicao matematica (Kelly) e' que graduar o
TAMANHO por uma metrica que NAO correlaciona com o resultado nao muda a
esperanca por operacao, so' redistribui o RISCO entre operacoes.

## Copia deliberada da G18 (mesma geometria vencedora, capital R$1.000)

Esta classe e' copia DELIBERADA de `WinBuscaLucroG18OrbCapital1000`
(mesma deteccao de rompimento da faixa de abertura, mesmo teto de 1
operacao real/pregao, mesma geometria vencedora `stop_max=140,
alvo_multiplo=3,0x`) + a instrumentacao de forca da G11 (`_forca_
rompimento`, `stats_forcas`, `stats_forca_das_entradas` -- identica, nao
reimplementada do zero). A UNICA mudanca de SINAL/EXECUCAO: a `quantity`
da ordem de entrada deixa de ser uma constante `self.quantity` e passa a
ser `self.contratos_por_balde[indice_do_balde]`, escolhido pelos cortes
`self.forca_cortes=(p33,p67)` -- o motor (`contracts_from_capital_
operacional`) so' pode ENCOLHER o que a estrategia pede, nunca aumentar,
entao o teto de capital REAL continua decidindo o teto de contratos de
fato executado a cada entrada (nunca hardcoded aqui).

Arquivo separado (nao subclasse de G18), mesmo motivo de toda geracao
anterior desta busca: cada geracao congela seu proprio modulo.
"""
from __future__ import annotations

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG19OrbSizingGraduado"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de toda a linha desta busca.
TTL_BARRAS_ENTRADA = 10

#: Piso INEGOCIAVEL (decisao do dono, 2026-10-05, mesma porta da G17/G18):
#: alvo/stop nunca cai para <=1x.
ALVO_MULTIPLO_MINIMO = 2.0


class WinBuscaLucroG19OrbSizingGraduado(IntradayStrategy):
    """Rompimento da faixa de abertura do WIN@ (logica IDENTICA a` G07/G08/
    G18), no MAXIMO 1 operacao real por pregao, com a QUANTIDADE de
    contratos da entrada GRADUADA por um balde de forca relativa do
    rompimento (`forca_cortes`) -- Geracao 19, Parte 1: testa se graduar o
    TAMANHO (nao so' SELECIONAR, como a G11 fez a R$250) muda a esperanca ou
    so' a variancia/ruina, quando a metrica de graduacao nao correlaciona
    com o resultado do trade (achado da G11)."""

    name = "win_busca_lucro_g19_orb_sizing_graduado"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        range_minutos: float = 5.0,
        stop_min_pontos: float = 50.0,
        stop_max_pontos: float = 140.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        forca_cortes: tuple[float, float] = (float("inf"), float("inf")),
        contratos_por_balde: tuple[int, int, int] = (1, 1, 1),
    ) -> None:
        if range_minutos <= 0:
            raise ValueError("range_minutos tem que ser positivo")
        if stop_min_pontos <= 0:
            raise ValueError("stop_min_pontos tem que ser positivo")
        if stop_max_pontos < stop_min_pontos:
            raise ValueError("stop_max_pontos tem que ser >= stop_min_pontos")
        if alvo_multiplo < ALVO_MULTIPLO_MINIMO:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo do piso de "
                f"{ALVO_MULTIPLO_MINIMO}x -- perder>=ganhar e' proibido "
                f"(principio inegociavel do dono)")
        if buffer_entrada_pontos < 0:
            raise ValueError("buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if len(forca_cortes) != 2 or forca_cortes[0] > forca_cortes[1]:
            raise ValueError("forca_cortes tem que ser (p_baixo, p_alto) com p_baixo<=p_alto")
        if len(contratos_por_balde) != 3 or any(c < 1 for c in contratos_por_balde):
            raise ValueError("contratos_por_balde tem que ter 3 inteiros >= 1 (fraco,medio,forte)")
        if symbol is not None:
            self.symbol = symbol
        self.range_minutos = float(range_minutos)
        self.stop_min_pontos = float(stop_min_pontos)
        self.stop_max_pontos = float(stop_max_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.forca_cortes = (float(forca_cortes[0]), float(forca_cortes[1]))
        self.contratos_por_balde = tuple(int(c) for c in contratos_por_balde)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49) --
        self.stats_bruto = 0
        self.stats_ja_operou_hoje = 0
        self.stats_ordens_emitidas = 0
        #: forca_relativa de TODA borda bruta (antes de qualquer filtro) --
        #: populacao usada pelo harness para definir os cortes de balde.
        self.stats_forcas: list[float] = []
        #: forca_relativa DA ORDEM QUE VIROU TRADE (preenchida), uma entrada
        #: por trade real, mesma ordem cronologica de `result.trades` --
        #: estratificacao POS-HOC (item 6.50), nunca simulacao exclusiva.
        self.stats_forca_das_entradas: list[float] = []
        #: quantidade PEDIDA (antes do teto de capital) em cada entrada --
        #: o motor so' pode ENCOLHER, entao comparar contra `trade.quantity`
        #: real do diario mede quanto o teto de capital mordeu.
        self.stats_quantidade_pedida: list[int] = []
        self._pendente_forca: float = 0.0

        self._reset_sessao()

    # -- estado por sessao ---------------------------------------------------
    def _reset_sessao(self) -> None:
        self._open_ts: pd.Timestamp | None = None
        self._range_hi: float | None = None
        self._range_lo: float | None = None
        self._fora_hi = False
        self._fora_lo = False
        self._armou_hoje = False
        self._preencheu_hoje = False
        self._tinha_posicao_anterior = False

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    # -- geometria (pura) -----------------------------------------------------
    def _geometria(self) -> tuple[float, float]:
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        stop = max(self.stop_min_pontos, min(self.stop_max_pontos, range_pontos))
        stop = round(stop / self.tick_size) * self.tick_size
        alvo = round((stop * self.alvo_multiplo) / self.tick_size) * self.tick_size
        return float(stop), float(alvo)

    def _forca_rompimento(self, bar_close: float, nova_alta: bool) -> float:
        """Identica a` `WinBuscaLucroG11OrbTamanhoGraduado._forca_rompimento`
        -- magnitude ALEM da faixa, relativa ao tamanho da propria faixa de
        abertura, causal (so' usa a faixa ja' fechada e o fechamento da
        PROPRIA barra de rompimento)."""
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        if range_pontos <= 0:
            return 0.0
        if nova_alta:
            return (bar_close - self._range_hi) / range_pontos
        return (self._range_lo - bar_close) / range_pontos

    def _balde(self, forca: float) -> int:
        """0=fraco, 1=medio, 2=forte -- pelos cortes `forca_cortes`."""
        p_baixo, p_alto = self.forca_cortes
        if forca < p_baixo:
            return 0
        if forca < p_alto:
            return 1
        return 2

    def _ordem(self, side: str, limite: float, stop_pontos: float,
               alvo_pontos: float, quantidade: int, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(limite, self.tick_size)
        return EnterLimit(
            side=side,
            limit_price=limite,
            initial_stop=no_tick(limite - sinal * stop_pontos, self.tick_size),
            initial_target=no_tick(limite + sinal * alvo_pontos, self.tick_size),
            quantity=quantidade,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=quantidade,
            exit_ttl_bars=None,
            reason=reason,
        )

    # -- loop -------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._open_ts is None:
            self._open_ts = ts

        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            self._preencheu_hoje = True
            self.stats_forca_das_entradas.append(self._pendente_forca)
        self._tinha_posicao_anterior = tem_posicao_agora

        if (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos):
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            return []

        if self._range_hi is None or self._range_lo is None:
            return []

        rompeu_alta = bar.close > self._range_hi
        rompeu_baixa = bar.close < self._range_lo

        nova_alta = rompeu_alta and not self._fora_hi
        nova_baixa = rompeu_baixa and not self._fora_lo
        self._fora_hi = rompeu_alta
        self._fora_lo = rompeu_baixa

        if not (nova_alta or nova_baixa):
            return []

        self.stats_bruto += 1
        forca = self._forca_rompimento(bar.close, nova_alta)
        self.stats_forcas.append(forca)

        if positions:
            return []
        if self._preencheu_hoje:
            self.stats_ja_operou_hoje += 1
            return []
        if self._armou_hoje:
            return []

        quantidade = self.contratos_por_balde[self._balde(forca)]
        stop_pontos, alvo_pontos = self._geometria()
        buf = self.buffer_entrada_pontos
        self._pendente_forca = forca
        self.stats_quantidade_pedida.append(quantidade)
        if nova_alta:
            limite = bar.close - buf
            self._armou_hoje = True
            self.stats_ordens_emitidas += 1
            return [self._ordem("long", limite, stop_pontos, alvo_pontos, quantidade,
                                "g19_orb_sizing_graduado_rompimento_alta")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos, quantidade,
                            "g19_orb_sizing_graduado_rompimento_baixa")]
