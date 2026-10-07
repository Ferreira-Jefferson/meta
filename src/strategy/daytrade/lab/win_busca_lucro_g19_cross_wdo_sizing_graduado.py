# -*- coding: utf-8 -*-
"""`WinBuscaLucroG19CrossWdoSizingGraduado` -- Geracao 19 (Parte 2) da busca
por um EA lucrativo do WIN.

## Mandato (dono, 2026-10-05) -- Parte 2

A G17 (`win_busca_lucro_g17_cross_wdo_capital1000.py`) achou, a R$1.000 e
`alvo=4x/stop=150`, um candidato que passa o gate LITERAL do OOS-1
(liquido +R$93,50) mas NAO "com folga": concentracao top3/liquido=383%,
PIOR que a R$250 -- o sinal (confirmacao cruzada WIN x WDO) dispara em
RAJADA dentro de poucos pregoes de regime forte, nao se espalha
uniformemente. A pergunta desta geracao: a MAGNITUDE da propria anomalia
(o quanto `|delta 20min|` dos dois instrumentos excede o quantil causal
0,75 -- uma medida de CONVICCAO do sinal que gerou a entrada, diferente da
forca do rompimento ORB que a G11 ja' mostrou ser incidental) correlaciona
com o resultado do trade? Se sim, graduar CONTRATOS por magnitude pode (a)
melhorar IC/p_ruina e (b) reduzir a concentracao, SE os episodios de maior
magnitude forem mais espalhados no tempo que os medios (hipotese a
TESTAR, nao assumida).

## O que foi reaproveitado por IMPORT direto (mandato explicito)

`estado_anomalo_cruzado` de `win_busca_lucro_g04_cross_wdo` NAO e'
reimplementada -- e' importada e usada so' para um teste de PARIDADE no
harness (confirmar que `magnitude_anomalo_cruzado`, abaixo, devolve o
MESMO `anomalo`/`direcao`, bit a bit, que a funcao original da G4). A
estrutura geral da classe (pernada maior R43 inegociavel, `EnterLimit` com
buffer de entrada, execucao fechada) e' copia deliberada de
`WinBuscaLucroG17CrossWdoCapital1000` -- mesmo motivo de toda geracao
anterior desta busca (congelar o proprio modulo sem afetar o que ja foi
medido).

## Por que uma funcao NOVA (`magnitude_anomalo_cruzado`) em vez de so'
## importar `estado_anomalo_cruzado` da G4

A funcao da G4 devolve so' `(anomalo: bool, direcao: int)` -- ela calcula
`abs_win`/`abs_wdo`/os limiares causais `thr_win`/`thr_wdo` internamente e
NUNCA os expoe. Para medir "quanto a anomalia excedeu o quantil" e' preciso
o MESMO calculo causal (mesma janela, mesmo burn-in, mesmo quantil) mais a
RAZAO `abs/thr` dos dois instrumentos -- por isso esta funcao duplica a
matematica da G4 linha a linha (nao e' uma invencao nova) e so' ACRESCENTA
uma terceira serie, `magnitude`. O harness verifica a paridade com a G4
antes de qualquer backtest (ver `g19_base.py::verifica_paridade_magnitude`).

`magnitude[t]` (so' definida quando `anomalo[t]`, NaN caso contrario) =
`min(abs_win[t]/thr_win[t], abs_wdo[t]/thr_wdo[t])` -- o MENOR dos dois
excessos relativos, porque a anomalia so' dispara quando AMBOS os
instrumentos excedem o proprio quantil, e e' o mais fraco dos dois elos
que limita a "conviccao" conjunta do episodio (1,0 = exatamente no
quantil; 2,0 = o elo mais fraco andou o DOBRO do corte).

## Sizing -- a UNICA mudanca de contrato em relacao a` G17

A classe NUNCA rejeita um sinal por magnitude (isso reintroduziria o vies
de filtro exclusivo que o item 6.50 ja mostrou fabricar gradiente onde nao
ha' -- toda anomalia nova, a favor da pernada, ainda vira ordem). O que
muda e' so' a QUANTIDADE pedida na `EnterLimit`, escolhida pelo balde de
`magnitude_cortes` -- o motor (`contracts_from_capital_operacional`) so'
pode ENCOLHER o que a estrategia pede, nunca aumentar.
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

__all__ = ["WinBuscaLucroG19CrossWdoSizingGraduado", "magnitude_anomalo_cruzado"]

#: Limiar da pernada maior (zigzag causal sobre o caminho da vela, R43).
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Dias INTEIROS de historico, estritamente anteriores ao dia corrente,
#: exigidos antes do quantil causal comecar a valer -- identico a` G4/G17.
MIN_DIAS_BURN_IN = 20
#: Piso INEGOCIAVEL da grade (decisao do dono, 2026-10-05): alvo/stop nunca
#: cai para <=1x (perder>=ganhar e' proibido).
ALVO_MULTIPLO_MINIMO = 2.0


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela -- definicao CONGELADA em
    `REGRAS.md`, identica a` usada em R43/R65/R57/G4/G17. Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


def magnitude_anomalo_cruzado(
    close_win: pd.Series,
    close_wdo: pd.Series,
    janela_min: int = 20,
    quantil: float = 0.75,
    min_dias_burn_in: int = MIN_DIAS_BURN_IN,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Funcao PURA -- mesma matematica CAUSAL de
    `win_busca_lucro_g04_cross_wdo.estado_anomalo_cruzado` (duplicada de
    proposito, ver docstring do modulo para o porque), devolvendo tambem a
    MAGNITUDE do episodio: `min(abs_win/thr_win, abs_wdo/thr_wdo)` nos
    pontos anomalos, NaN caso contrario. `(anomalo, direcao)` tem que bater
    byte a byte com a saida da funcao da G4 para os MESMOS argumentos --
    verificado no harness, nao aqui (funcao pura nao faz asserts de
    paridade em producao)."""
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

    thr_win = dia.map(thr_win_por_dia).astype(float)
    thr_wdo = dia.map(thr_wdo_por_dia).astype(float)

    tem_historico = thr_win.notna() & thr_wdo.notna()
    sinal_win = np.sign(delta_win)
    sinal_wdo = np.sign(delta_wdo)
    mesmo_sinal = (sinal_win == sinal_wdo) & (sinal_win != 0)
    acima_win = abs_win >= thr_win
    acima_wdo = abs_wdo >= thr_wdo

    anomalo = (tem_historico & mesmo_sinal & acima_win & acima_wdo).fillna(False)
    direcao = pd.Series(np.where(anomalo, sinal_win, 0), index=idx).astype(int)

    # -- magnitude: o MENOR dos dois excessos relativos, so' definida onde
    # anomalo=True (thr_win/thr_wdo > 0 sempre que tem_historico, porque
    # |delta| nunca e' negativo e o quantil de uma serie de modulos so' e'
    # zero num caso degenerado que o burn-in de 20 dias praticamente exclui).
    with np.errstate(divide="ignore", invalid="ignore"):
        razao_win = abs_win / thr_win
        razao_wdo = abs_wdo / thr_wdo
    magnitude_bruta = np.minimum(razao_win, razao_wdo)
    magnitude = pd.Series(np.where(anomalo, magnitude_bruta, np.nan), index=idx)

    anomalo = anomalo.reindex(close_win.index, fill_value=False)
    direcao = direcao.reindex(close_win.index, fill_value=0)
    magnitude = magnitude.reindex(close_win.index, fill_value=np.nan)
    return anomalo, direcao, magnitude


class WinBuscaLucroG19CrossWdoSizingGraduado(IntradayStrategy):
    """Opera o WIN@ quando WIN@ e WDO@ andam, por uma janela curta, na MESMA
    direcao (estado ANOMALO cruzado) -- IDENTICA a` G17 na deteccao de
    sinal/geometria/execucao. A UNICA mudanca: a `quantity` da entrada e'
    GRADUADA pelo balde de MAGNITUDE do proprio episodio anomalo
    (`magnitude_cortes`), nunca usada para REJEITAR um sinal -- Geracao 19,
    Parte 2 da busca por um EA lucrativo do WIN."""

    name = "win_busca_lucro_g19_cross_wdo_sizing_graduado"
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
        wdo_magnitude: pd.Series,
        symbol: str | None = None,
        direcao_aposta: str = "continuacao",
        pernada_pontos: float = PERNADA_PONTOS,
        stop_pontos: float = 150.0,
        alvo_multiplo: float = 4.0,
        buffer_entrada_pontos: float = 30.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        magnitude_cortes: tuple[float, float] = (float("inf"), float("inf")),
        contratos_por_balde: tuple[int, int, int] = (1, 1, 1),
    ) -> None:
        if direcao_aposta not in ("continuacao", "reversao"):
            raise ValueError(f"direcao_aposta={direcao_aposta!r} invalido -- "
                              "'continuacao' ou 'reversao'")
        if pernada_pontos <= 0:
            raise ValueError("pernada_pontos tem que ser positivo")
        if stop_pontos <= 0:
            raise ValueError("stop_pontos tem que ser positivo")
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
        if len(magnitude_cortes) != 2 or magnitude_cortes[0] > magnitude_cortes[1]:
            raise ValueError("magnitude_cortes tem que ser (m_baixo, m_alto) com m_baixo<=m_alto")
        if len(contratos_por_balde) != 3 or any(c < 1 for c in contratos_por_balde):
            raise ValueError("contratos_por_balde tem que ter 3 inteiros >= 1 (baixo,medio,alto)")
        if symbol is not None:
            self.symbol = symbol
        self._wdo_anomalo = wdo_anomalo.to_dict() if isinstance(wdo_anomalo, pd.Series) else dict(wdo_anomalo)
        self._wdo_direcao = wdo_direcao.to_dict() if isinstance(wdo_direcao, pd.Series) else dict(wdo_direcao)
        self._wdo_magnitude = wdo_magnitude.to_dict() if isinstance(wdo_magnitude, pd.Series) else dict(wdo_magnitude)
        self.direcao_aposta = direcao_aposta
        self.pernada_pontos = float(pernada_pontos)
        self.stop_pontos = float(stop_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.magnitude_cortes = (float(magnitude_cortes[0]), float(magnitude_cortes[1]))
        self.contratos_por_balde = tuple(int(c) for c in contratos_por_balde)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (licao da G2/G4 / item 6.48) --
        self.stats_bruto = 0
        self.stats_contra_tendencia = 0
        self.stats_ordens_emitidas = 0
        #: magnitude de TODO episodio bruto (antes do filtro de tendencia),
        #: populacao usada pelo harness para os cortes de balde.
        self.stats_magnitudes: list[float] = []
        #: magnitude DA ORDEM QUE VIROU TRADE (preenchida), uma entrada por
        #: trade real, registrada na transicao SEM->COM posicao (mesmo
        #: padrao de `WinBuscaLucroG11OrbTamanhoGraduado` -- nunca na
        #: emissao da ordem, porque uma ordem armada pode expirar/ser
        #: rejeitada sem nunca virar trade) -- estratificacao POS-HOC (item
        #: 6.50), nunca simulacoes exclusivas por balde.
        self.stats_magnitude_das_entradas: list[float] = []
        #: quantidade PEDIDA na ordem que de fato preencheu (mesmo padrao
        #: acima) -- o motor so' pode ENCOLHER, entao comparar contra
        #: `trade.quantity` real mede quanto o teto de capital mordeu.
        self.stats_quantidade_pedida: list[int] = []
        self._pendente_magnitude: float = float("nan")
        self._pendente_quantidade: int = 0

        self._reset_sessao()

    # -- estado por sessao --------------------------------------------------
    def _reset_sessao(self) -> None:
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        self._anomalo_anterior = False
        self._espera: int | None = None
        self._hist: deque[Bar] = deque(maxlen=4)
        self._tinha_posicao_anterior = False

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

    def _balde(self, magnitude: float) -> int:
        """0=baixo (no quantil), 1=medio (moderadamente acima), 2=alto
        (muito acima) -- pelos cortes `magnitude_cortes`."""
        m_baixo, m_alto = self.magnitude_cortes
        if magnitude < m_baixo:
            return 0
        if magnitude < m_alto:
            return 1
        return 2

    def _monta_entrada(self, direcao_entrada: int, bar: Bar, quantidade: int) -> IntradayAction | None:
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
            quantity=quantidade,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=quantidade,
            exit_ttl_bars=None,
            reason=f"g19_cross_wdo_sizing_{self.direcao_aposta}_s{self.stop_pontos:.0f}_a{self.alvo_multiplo:.1f}x",
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

        # Transicao de posicao -- estado do INICIO da barra (item 6.48),
        # mesma disciplina de `WinBuscaLucroG11OrbTamanhoGraduado`: registra
        # a magnitude/quantidade PENDENTE so' quando a posicao de fato
        # aparece (fill real), nunca na emissao da ordem.
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            self.stats_magnitude_das_entradas.append(self._pendente_magnitude)
            self.stats_quantidade_pedida.append(self._pendente_quantidade)
        self._tinha_posicao_anterior = tem_posicao_agora

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

        for p in _caminho_da_barra(bar):
            self._atualiza_perna(p)

        anomalo_agora = bool(self._wdo_anomalo.get(ts, False))
        direcao_sinal = int(self._wdo_direcao.get(ts, 0))
        magnitude_agora = float(self._wdo_magnitude.get(ts, float("nan")))
        disparo_novo = anomalo_agora and not self._anomalo_anterior
        self._anomalo_anterior = anomalo_agora

        if not (disparo_novo and direcao_sinal != 0):
            return []

        self.stats_bruto += 1
        self.stats_magnitudes.append(magnitude_agora)
        direcao_entrada = direcao_sinal if self.direcao_aposta == "continuacao" else -direcao_sinal

        if self._direcao != direcao_entrada:
            self.stats_contra_tendencia += 1
            return []

        if not pode_armar:
            return []

        quantidade = self.contratos_por_balde[self._balde(magnitude_agora)]
        acao = self._monta_entrada(direcao_entrada, bar, quantidade)
        if acao is None:
            return []
        self._pendente_magnitude = magnitude_agora
        self._pendente_quantidade = quantidade
        self.stats_ordens_emitidas += 1
        return [acao]
