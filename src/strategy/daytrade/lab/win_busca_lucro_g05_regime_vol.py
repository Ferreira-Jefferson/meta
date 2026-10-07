# -*- coding: utf-8 -*-
"""`WinBuscaLucroG05RegimeVol` -- Geracao 5 da busca por um EA lucrativo do WIN.

Pergunta desta geracao (`ORQUESTRACAO.md`, raciocinio deixado pela Geracao 4):
a Geracao 4 achou um gatilho que opera o WIN@ quando WIN@ e WDO@ andam, por
uma janela curta, na MESMA direcao (estado ANOMALO, dado que normalmente
andam em correlacao negativa) -- resultado positivo nas duas janelas (IS
+R$1.221,50/127 trades, OOS-1 +R$184,50/49 trades) mas FRAGIL: IC95 do win%
cruza o breakeven empirico nas duas janelas e a concentracao em poucos
pregoes PIOROU do IS (59%) para o OOS-1 (240%). A suspeita levantada no
raciocinio da G4: talvez o que funcione nao seja a CORRELACAO cruzada em si,
e sim os dois mercados sinalizarem "regime de movimento forte" ao mesmo
tempo -- e um proxy de volatilidade medido SO' no WIN (sem precisar do WDO)
capture o MESMO regime com amostra MAIOR, porque nao depende de dois
instrumentos concordarem no mesmo minuto.

Esta geracao testa essa pergunta com 3 proxies de "regime de movimento
forte", todos causais e SO' com dado do WIN@ (ver funcoes module-level
abaixo: `regime_amplitude_bloco`, `regime_vela_extrema`, `regime_volume_
bloco`), e a aposta tradavel e' SEMPRE continuacao da pernada maior do WIN em
curso (R43, principio inegociavel do dono -- NUNCA contra-tendencia) --
diferente da G4, aqui nao ha' "direcao implicada pelo gatilho": os proxies
desta geracao sao de MAGNITUDE (quao forte o movimento recente foi), nao de
DIRECAO, entao a direcao da aposta vem inteira da pernada maior em curso.

## Desenho -- generico, desacoplado da origem do regime

Ao contrario da G4 (que amarra a classe a` funcao `estado_anomalo_cruzado`
especifica de WDO), esta classe recebe uma UNICA serie pre-computada
`regime_ativo: pd.Series[bool]` (indexada por timestamp M1) -- nao importa
se veio do proxy (a), (b), (c) ou de um ENSEMBLE (>=2 proxies concordando
simultaneamente, OR booleano calculado fora da classe). Isto deixa a classe
IDENTICA para qualquer proxy testado e para a linha de referencia (G4
recalculada nesta geracao, reusando `estado_anomalo_cruzado` do modulo da
G4 e convertendo para este mesmo contrato `regime_ativo` antes de passar
para cá -- ver harness `g05_base.py`).

## Execucao -- o desenho fechado, sem excecao (CLAUDE.md) -- identico a` G4

Entrada so' por `EnterLimit` com `ttl_barras_entrada` obrigatorio, limite
colocada `buffer_entrada_pontos` pontos ATRAS do fechamento corrente. Stop e
alvo em PONTOS fixos (`stop_pontos`, `alvo_multiplo x stop_pontos`,
`alvo_multiplo >= 3.0` por construcao). Alvo so' como ordem-limite real
fatiada (`exit_split_unit`), SEM prazo (`exit_ttl_bars=None`); so' o stop e'
a mercado; `anchor_exits_at_fill=True`; `target_fills_as_maker=True`. 1
contrato FIXO. Fila WIN@ nao calibrada: `queue_ahead_qty=0`/`exit_queue_
ahead_qty=0` (enche no toque), premissa OTIMISTA declarada pelo harness.

## Contadores de auditoria (item 6.48 de LICOES_DE_PRODUCAO.md)

`stats_bruto` conta toda ocorrencia BRUTA da BORDA de regime (transicao
False->True de `regime_ativo`), ANTES de qualquer filtro de
tendencia/execucao/capital. `stats_sem_tendencia` conta as descartadas por
`self._direcao is None` (pernada maior ainda nao definida quando o regime
disparou -- nao ha' "contra-tendencia" nesta geracao porque o proxy nao tem
direcao propria, so' existe "tendencia definida" ou "nao definida ainda").
`stats_ordens_emitidas` conta so' as que viraram `EnterLimit` de verdade. A
ordem de operacoes de `on_bar` segue a mesma checagem da G2/G4: `pode_armar`
decidido com o `_espera` do INICIO da barra, perna maior atualizada, so'
entao a borda de regime e' lida e a decisao de emitir tomada.
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

#: Limiar da pernada maior (zigzag causal sobre o caminho da vela, R43).
#: Nao e' parametro desta geracao -- mesmo valor de G1-G4.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Dias INTEIROS de historico, estritamente anteriores ao dia corrente,
#: exigidos antes de qualquer quantil/media causal comecar a valer.
MIN_DIAS_BURN_IN = 20


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """O "caminho" desta vela -- definicao CONGELADA em `REGRAS.md`, identica
    a` usada em R43/R65/R57/G4. Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


def regime_amplitude_bloco(
    df_win: pd.DataFrame,
    janela_min: int = 15,
    quantil: float = 0.75,
    min_dias_burn_in: int = MIN_DIAS_BURN_IN,
) -> pd.Series:
    """PROXY (a) -- amplitude do bloco recente acima de um quantil causal
    CONDICIONADO AO HORARIO (mesma familia do R20, "bloco de 15min agitado
    para o horario"): `range_trail[t]` = maxima do `high` menos minima do
    `low` dos ultimos `janela_min` minutos, DENTRO do mesmo pregao (nunca
    atravessa a virada de sessao). O limiar em cada minuto-do-dia e' o
    quantil `quantil` dos valores HISTORICOS daquele MESMO minuto-do-dia
    (`HH:MM`), usando so' dias ESTRITAMENTE anteriores (burn-in de
    `min_dias_burn_in` OCORRENCIAS daquele minuto-do-dia -- 1 por pregao).
    Pura, causal. Devolve serie booleana indexada como `df_win`."""
    idx = df_win.index
    dia = pd.Series(idx.date, index=idx)
    high = df_win["high"]
    low = df_win["low"]
    range_trail = (
        high.groupby(dia).rolling(janela_min).max()
        - low.groupby(dia).rolling(janela_min).min()
    )
    range_trail.index = range_trail.index.droplevel(0)
    range_trail = range_trail.reindex(idx)

    minuto = pd.Series(idx.strftime("%H:%M"), index=idx)
    tmp = pd.DataFrame({"val": range_trail, "minuto": minuto})
    grp = tmp.groupby("minuto", sort=False)["val"]
    thr = grp.transform(lambda s: s.shift(1).expanding().quantile(quantil))
    cnt_prior = tmp.groupby("minuto", sort=False).cumcount()

    tem_historico = (cnt_prior >= min_dias_burn_in) & thr.notna() & range_trail.notna()
    ativo = (tem_historico & (range_trail >= thr)).fillna(False)
    return ativo.astype(bool)


def regime_vela_extrema(
    df_win: pd.DataFrame,
    multiplo: float = 2.0,
    n_dias_janela: int = 20,
    min_dias_burn_in: int = MIN_DIAS_BURN_IN,
) -> pd.Series:
    """PROXY (b) -- porta direta do R35 (ja' CONFIRMADO em `REGRAS.md`, "liga/
    tamanho"): a vela M1 do minuto `t` tem faixa (`high-low`) `>= multiplo x`
    a MEDIA da faixa do MESMO minuto-do-dia nos `n_dias_janela` pregoes
    ANTERIORES (janela movel, nao expanding -- "20 pregoes anteriores",
    nao "todo o historico"). Causal: so' usa pregoes estritamente anteriores
    ao dia corrente. Pura. Devolve serie booleana indexada como `df_win`."""
    idx = df_win.index
    faixa = (df_win["high"] - df_win["low"])
    minuto = pd.Series(idx.strftime("%H:%M"), index=idx)
    tmp = pd.DataFrame({"val": faixa, "minuto": minuto})
    grp = tmp.groupby("minuto", sort=False)["val"]
    media_hist = grp.transform(
        lambda s: s.shift(1).rolling(n_dias_janela, min_periods=n_dias_janela).mean()
    )
    cnt_prior = tmp.groupby("minuto", sort=False).cumcount()

    tem_historico = (cnt_prior >= min_dias_burn_in) & media_hist.notna() & faixa.notna()
    ativo = (tem_historico & (faixa >= multiplo * media_hist)).fillna(False)
    return ativo.astype(bool)


def regime_volume_bloco(
    df_win: pd.DataFrame,
    janela_min: int = 15,
    quantil: float = 0.75,
    min_dias_burn_in: int = MIN_DIAS_BURN_IN,
) -> pd.Series:
    """PROXY (c) -- soma do `tick_volume` dos ultimos `janela_min` minutos
    (DENTRO do pregao) acima de um quantil causal GLOBAL (nao condicionado a
    horario -- mesma familia de quantil da G4, so' que medido no proprio WIN,
    sem WDO). Historico de 2026-10-01 (`win_volume_indicador_descartado`) ja'
    registra que indicadores de volume do WIN nao replicaram nada alem do
    tamanho do movimento -- este proxy existe para CONFIRMAR ou REFUTAR essa
    leitura dentro desta busca especifica, nao para assumi-la. Causal, pura."""
    idx = df_win.index
    dia = pd.Series(idx.date, index=idx)
    vol = df_win["tick_volume"].astype(float)
    vol_trail = vol.groupby(dia).rolling(janela_min).sum()
    vol_trail.index = vol_trail.index.droplevel(0)
    vol_trail = vol_trail.reindex(idx)

    dias_ordenados = sorted(dia.unique())
    thr_por_dia: dict = {}
    acumulado: list = []
    import numpy as np
    for i, d in enumerate(dias_ordenados):
        if i >= min_dias_burn_in:
            vals = np.concatenate(acumulado)
            thr_por_dia[d] = float(np.quantile(vals, quantil))
        else:
            thr_por_dia[d] = None
        mask = (dia == d).values
        v = vol_trail.values[mask]
        acumulado.append(v[~np.isnan(v)])
    thr = dia.map(thr_por_dia)
    tem_historico = thr.notna() & vol_trail.notna()
    ativo = (tem_historico & (vol_trail >= thr.astype(float))).fillna(False)
    return ativo.astype(bool)


class WinBuscaLucroG05RegimeVol(IntradayStrategy):
    """Opera o WIN@ na direcao de CONTINUACAO da pernada maior em curso (R43)
    sempre que um proxy de "regime de movimento forte", pre-computado SO' com
    dado do WIN@ (ou um ensemble deles), dispara uma borda nova -- Geracao 5
    da busca por um EA lucrativo do WIN (`ORQUESTRACAO.md`)."""

    name = "win_busca_lucro_g05_regime_vol"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        regime_ativo: pd.Series,
        symbol: str | None = None,
        pernada_pontos: float = PERNADA_PONTOS,
        stop_pontos: float = 150.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 30.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
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
        self._regime_ativo = (
            regime_ativo.to_dict() if isinstance(regime_ativo, pd.Series) else dict(regime_ativo)
        )
        self.pernada_pontos = float(pernada_pontos)
        self.stop_pontos = float(stop_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (licao da G2/G4 / item 6.48) --
        self.stats_bruto = 0
        self.stats_sem_tendencia = 0
        self.stats_ordens_emitidas = 0

        self._reset_sessao()

    # -- estado por sessao --------------------------------------------------
    def _reset_sessao(self) -> None:
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        self._regime_anterior = False
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
            reason=f"g05_regime_vol_s{self.stop_pontos:.0f}_a{self.alvo_multiplo:.0f}x",
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

        ativo_agora = bool(self._regime_ativo.get(ts, False))
        disparo_novo = ativo_agora and not self._regime_anterior
        self._regime_anterior = ativo_agora

        if not disparo_novo:
            return []

        # BRUTO: toda borda de regime, ANTES de qualquer filtro de
        # tendencia/execucao/capital.
        self.stats_bruto += 1

        if self._direcao is None:
            # Pernada maior ainda nao definida quando o regime disparou --
            # nao ha' direcao a seguir. DESCARTA.
            self.stats_sem_tendencia += 1
            return []

        if not pode_armar:
            return []

        acao = self._monta_entrada(self._direcao, bar)
        if acao is None:
            return []
        self.stats_ordens_emitidas += 1
        return [acao]
