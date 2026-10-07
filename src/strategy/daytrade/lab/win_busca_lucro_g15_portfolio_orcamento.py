# -*- coding: utf-8 -*-
"""`WinBuscaLucroG15PortfolioOrcamento` -- Geracao 15 da busca por um EA
lucrativo do WIN (`ORQUESTRACAO.md`): corrige o MECANISMO que a G14
diagnosticou, nao testa parametro novo de geometria.

## O que a G14 mediu e por que nao basta repetir

A G14 testou alternancia OU-logica entre ORB (G8/G13) e confirmacao cruzada
WIN x WDO (G4) sobre o MESMO caixa de R$250 (1 contrato, nunca 2 posicoes
simultaneas). A correlacao diaria de P&L entre as duas familias deu
essencialmente ZERO (0,0117, n=122) -- a premissa de portfolio classico
(diversificar risco entre apostas descorrelacionadas) era verdadeira -- e
AINDA ASSIM a probabilidade de ruina SUBIU (33,5% contra 24,8% da melhor
familia sozinha, G8), nao caiu. O mecanismo identificado: a R$250 so' cabe 1
contrato, entao o caixa NUNCA e' dividido entre as duas familias -- ele e'
REEXPOSTO a cada disparo de QUALQUER uma. Como as duas raramente competem
pela MESMA barra (so' 1 empate em 122 pregoes), o "OU logico" nao escolhe
entre gatilhos concorrentes -- ele quase SOMA a frequencia (244 trades contra
121-127 solo). Mais tentativas sobre o mesmo caixa nao-reposto aumentam a
maior sequencia de perdas esperada, mesmo com correlacao diaria zero -- e e'
essa sequencia, nao a correlacao agregada, que decide ruina.

## A correcao desta geracao: ORCAMENTO DE EXPOSICAO fixo

Se o problema e' que o portfolio SOMA tentativas, a correcao direta e' nao
deixar a soma acontecer: um orcamento de exposicao TOTAL, do tamanho de UMA
familia sozinha (~121, o n da G8 solo no mesmo periodo) -- o portfolio ganha
o DIREITO as mesmas ~121 tentativas que uma familia sozinha teria, e a
pergunta vira QUAL familia usa cada vaga, nao SE o total de tentativas cresce.
Duas politicas de alocacao, controladas por `orcamento_modo` e
`politica_prioridade`:

- **FIFO ("primeiro a disparar ganha a vaga")** -- `politica_prioridade=
  "fifo"`: contador de vagas restantes, decrementado a cada ordem emitida por
  QUALQUER familia (a prioridade de empate na MESMA barra continua "ORB
  vence", identica a G14 -- o empate e' raro, nao e' o mecanismo em jogo
  aqui). `orcamento_modo="unico"` nao reabastece (um orcamento so' para o
  semestre inteiro); `orcamento_modo="mensal"` reabastece a cada mes
  corrente (`orcamento_valor` vagas por mes).
- **Por REGIME ("a vaga pertence a quem o regime favorece")** --
  `politica_prioridade="regime"`: um corte de horario (`regime_corte_hora`,
  descoberto por diagnostico ANTES desta classe, nao adivinhado) decide qual
  familia tem DIREITO a vaga em cada barra -- antes do corte so' ORB pode
  consumir orcamento, no/depois do corte so' o cruzado pode. Um sinal da
  familia "errada" para o regime corrente e' REJEITADO inteiro (nao so'
  deprioritizado), mesmo que haja vaga sobrando -- a vaga fica reservada pro
  regime certo. Isto NAO e' o mesmo filtro AND da G12 (que exigia os DOIS
  sinais na MESMA barra): aqui cada familia continua disparando sozinha, so'
  que so' numa metade do pregao.

`orcamento_modo="ilimitado"` (`orcamento_valor=None`) reproduz exatamente o
comportamento da G14 -- usado so' como controle/regressao, nunca como
candidato desta geracao.

## Composicao -- identica a G14 em tudo que NAO e' o orcamento

Mesma copia deliberada das duas familias (ORB de
`WinBuscaLucroG08OrbSobrevivencia`, cruzado de `WinBuscaLucroG04CrossWdo`,
passada como series pre-computadas -- mesmo padrao G4/G12/G14), mesmo portao
compartilhado (`_ordem_pendente_origem`, nunca 2 posicoes/ordens
simultaneas), mesma prioridade de empate ORB-vence-a-barra, mesmas
disciplinas de reentrada herdadas (ORB sem fade -- 1 operacao real/pregao;
cruzado sem teto diario), mesmo rastreio de origem por `entry_ts` (o motor
nao carrega `reason` em `IntradayTrade`).

## Desenho de execucao e capital -- identicos a toda a linha (CLAUDE.md, FECHADO)

`EnterLimit` com `ttl_bars` (nunca `Enter` a mercado); alvo por ordem-limite
real fatiada, SEM prazo; `anchor_exits_at_fill=True`; so' o STOP e' a
mercado; `target_fills_as_maker=True`; alvo sempre >= 3x o stop nas DUAS
geometrias (ValueError se nao). Fila do WIN@ NAO calibrada (premissa
otimista declarada pelo harness). Capital real R$250, 1 contrato fixo,
NUNCA 2 posicoes simultaneas (ver portao acima).
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG15PortfolioOrcamento"]

#: Pernada maior (R43) -- filtro de tendencia do sinal B, identico a G1-G14.
PERNADA_PONTOS = 750.0
#: Prazo da ordem-limite de ENTRADA (CLAUDE.md, "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10

_MODOS_ORCAMENTO = ("ilimitado", "unico", "mensal")
_POLITICAS = ("fifo", "regime")


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela -- definicao congelada em
    `REGRAS.md`, identica a R43/G1-G14. Pura."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


class WinBuscaLucroG15PortfolioOrcamento(IntradayStrategy):
    """Cesta de DUAS familias (ORB G8 + confirmacao cruzada WIN x WDO G4),
    OU logico sobre o MESMO caixa (identico a G14), mas limitada por um
    ORCAMENTO DE EXPOSICAO total -- o mecanismo que a G14 identificou como
    causa da ruina maior (soma de frequencia, nao divisao de risco).
    Geracao 15."""

    name = "win_busca_lucro_g15_portfolio_orcamento"
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
        # -- geometria ORB (sinal A, vencedor da G8/G13, herdada) -----------
        orb_range_minutos: float = 5.0,
        orb_stop_min_pontos: float = 50.0,
        orb_stop_max_pontos: float = 140.0,
        orb_alvo_multiplo: float = 3.0,
        orb_buffer_entrada_pontos: float = 20.0,
        # -- geometria cruzado (sinal B, vencedor da G4, herdada) -----------
        cross_direcao_aposta: str = "continuacao",
        cross_pernada_pontos: float = PERNADA_PONTOS,
        cross_stop_pontos: float = 150.0,
        cross_alvo_multiplo: float = 3.0,
        cross_buffer_entrada_pontos: float = 30.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
        # -- orcamento de exposicao (o MECANISMO novo desta geracao) --------
        orcamento_modo: str = "ilimitado",
        orcamento_valor: int | None = None,
        politica_prioridade: str = "fifo",
        regime_corte_hora: int | None = None,
    ) -> None:
        if orb_range_minutos <= 0:
            raise ValueError("orb_range_minutos tem que ser positivo")
        if orb_stop_min_pontos <= 0:
            raise ValueError("orb_stop_min_pontos tem que ser positivo")
        if orb_stop_max_pontos < orb_stop_min_pontos:
            raise ValueError("orb_stop_max_pontos tem que ser >= orb_stop_min_pontos")
        if orb_alvo_multiplo < 3.0:
            raise ValueError(
                f"orb_alvo_multiplo={orb_alvo_multiplo} abaixo de 3x -- fere a "
                f"disciplina alvo >= 3x o stop do mandato do dono")
        if orb_buffer_entrada_pontos < 0:
            raise ValueError("orb_buffer_entrada_pontos nao pode ser negativo")
        if cross_direcao_aposta not in ("continuacao", "reversao"):
            raise ValueError(f"cross_direcao_aposta={cross_direcao_aposta!r} invalido "
                              "-- 'continuacao' ou 'reversao'")
        if cross_pernada_pontos <= 0:
            raise ValueError("cross_pernada_pontos tem que ser positivo")
        if cross_stop_pontos <= 0:
            raise ValueError("cross_stop_pontos tem que ser positivo")
        if cross_alvo_multiplo < 3.0:
            raise ValueError(
                f"cross_alvo_multiplo={cross_alvo_multiplo} abaixo de 3x -- fere a "
                f"disciplina alvo >= 3x o stop do mandato do dono")
        if cross_buffer_entrada_pontos < 0:
            raise ValueError("cross_buffer_entrada_pontos nao pode ser negativo")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)")
        if orcamento_modo not in _MODOS_ORCAMENTO:
            raise ValueError(f"orcamento_modo={orcamento_modo!r} invalido -- "
                              f"{_MODOS_ORCAMENTO}")
        if orcamento_modo != "ilimitado" and (orcamento_valor is None or orcamento_valor <= 0):
            raise ValueError("orcamento_valor e' obrigatorio (>0) quando "
                              "orcamento_modo != 'ilimitado'")
        if politica_prioridade not in _POLITICAS:
            raise ValueError(f"politica_prioridade={politica_prioridade!r} invalido -- "
                              f"{_POLITICAS}")
        if politica_prioridade == "regime" and regime_corte_hora is None:
            raise ValueError("regime_corte_hora e' obrigatorio quando "
                              "politica_prioridade='regime'")
        if symbol is not None:
            self.symbol = symbol

        self._wdo_anomalo = wdo_anomalo.to_dict() if isinstance(wdo_anomalo, pd.Series) else dict(wdo_anomalo)
        self._wdo_direcao = wdo_direcao.to_dict() if isinstance(wdo_direcao, pd.Series) else dict(wdo_direcao)

        self.orb_range_minutos = float(orb_range_minutos)
        self.orb_stop_min_pontos = float(orb_stop_min_pontos)
        self.orb_stop_max_pontos = float(orb_stop_max_pontos)
        self.orb_alvo_multiplo = float(orb_alvo_multiplo)
        self.orb_buffer_entrada_pontos = float(orb_buffer_entrada_pontos)

        self.cross_direcao_aposta = cross_direcao_aposta
        self.cross_pernada_pontos = float(cross_pernada_pontos)
        self.cross_stop_pontos = float(cross_stop_pontos)
        self.cross_alvo_multiplo = float(cross_alvo_multiplo)
        self.cross_buffer_entrada_pontos = float(cross_buffer_entrada_pontos)

        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        self.orcamento_modo = orcamento_modo
        self.orcamento_valor = int(orcamento_valor) if orcamento_valor is not None else None
        self.politica_prioridade = politica_prioridade
        self.regime_corte_hora = regime_corte_hora

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49, herdados da G14) ------
        self.stats_bruto_orb = 0
        self.stats_bruto_cross = 0
        self.stats_orb_ja_operou_hoje = 0
        self.stats_cross_contra_tendencia = 0
        self.stats_cross_perdeu_empate_pra_orb = 0
        self.stats_ordens_emitidas_orb = 0
        self.stats_ordens_emitidas_cross = 0
        # -- contadores NOVOS desta geracao: por que uma vaga NAO foi usada -
        self.stats_recusado_por_orcamento_orb = 0
        self.stats_recusado_por_orcamento_cross = 0
        self.stats_recusado_por_regime_orb = 0
        self.stats_recusado_por_regime_cross = 0
        # -- diagnostico (hora-do-dia de cada sinal BRUTO, independente de
        # portao/orcamento/regime -- usado so' para a tabela de concentracao
        # temporal, nao influencia nenhuma decisao de trading). -------------
        self.horas_bruto_orb: list[int] = []
        self.horas_bruto_cross: list[int] = []

        #: `entry_ts` (do FILL) -> "orb"/"cross" -- casado por `entry_ts`
        #: depois do backtest (identico a G14).
        self.origem_por_entry_ts: dict[pd.Timestamp, str] = {}

        self._reset_sessao()

    # -- estado por sessao ---------------------------------------------------
    def _reset_sessao(self) -> None:
        # ORB (sinal A)
        self._open_ts: pd.Timestamp | None = None
        self._range_hi: float | None = None
        self._range_lo: float | None = None
        self._fora_hi = False
        self._fora_lo = False
        self._orb_preencheu_hoje = False
        # cruzado (sinal B) -- pernada maior (R43), nunca atravessa sessao
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        self._anomalo_anterior = False
        self._hist: deque[Bar] = deque(maxlen=4)
        # compartilhado
        self._tinha_posicao_anterior = False
        self._ordem_pendente_origem: str | None = None

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._ordem_pendente_origem = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._ordem_pendente_origem = None

    # -- orcamento (o mecanismo novo) -----------------------------------------
    def _inicializa_orcamento_se_preciso(self, ts: pd.Timestamp) -> None:
        if self.orcamento_modo == "ilimitado":
            return
        if self.orcamento_modo == "unico":
            if not hasattr(self, "_orcamento_restante"):
                self._orcamento_restante = self.orcamento_valor
            return
        # mensal: reabastece a cada troca de mes corrente.
        mes_atual = ts.year * 100 + ts.month
        if getattr(self, "_mes_orcamento", None) != mes_atual:
            self._mes_orcamento = mes_atual
            self._orcamento_restante = self.orcamento_valor

    def _ha_vaga(self) -> bool:
        if self.orcamento_modo == "ilimitado":
            return True
        return self._orcamento_restante > 0

    def _consome_vaga(self) -> None:
        if self.orcamento_modo == "ilimitado":
            return
        self._orcamento_restante -= 1

    def _regime_permite(self, origem: str, ts: pd.Timestamp) -> bool:
        """So' relevante quando `politica_prioridade='regime'`: decide se
        `origem` ("orb"/"cross") tem DIREITO a vaga na hora corrente. Antes
        do corte, so' ORB; no/depois do corte, so' cruzado -- corte
        descoberto por diagnostico (ver harness), nao parametro livre desta
        classe."""
        if self.politica_prioridade != "regime":
            return True
        antes_do_corte = ts.hour < self.regime_corte_hora
        return origem == "orb" if antes_do_corte else origem == "cross"

    # -- geometria ORB (pura, identica a G08/G14) -----------------------------
    def _geometria_orb(self) -> tuple[float, float]:
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        stop = max(self.orb_stop_min_pontos, min(self.orb_stop_max_pontos, range_pontos))
        stop = round(stop / self.tick_size) * self.tick_size
        alvo = round((stop * self.orb_alvo_multiplo) / self.tick_size) * self.tick_size
        return float(stop), float(alvo)

    def _ordem_orb(self, side: str, limite: float, stop_pontos: float,
                    alvo_pontos: float, reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        limite = no_tick(limite, self.tick_size)
        return EnterLimit(
            side=side,
            limit_price=limite,
            initial_stop=no_tick(limite - sinal * stop_pontos, self.tick_size),
            initial_target=no_tick(limite + sinal * alvo_pontos, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=reason,
        )

    # -- pernada maior (R43, identica a G04/G14) ------------------------------
    def _atualiza_perna(self, p: float) -> None:
        if self._origem is None:
            self._origem = p
            self._extremo = p
            return
        s = self._direcao
        if s is None:
            if p - self._origem >= self.cross_pernada_pontos:
                self._direcao = 1
                self._extremo = p
            elif self._origem - p >= self.cross_pernada_pontos:
                self._direcao = -1
                self._extremo = p
            return
        if s == 1:
            if p > self._extremo:
                self._extremo = p
            elif self._extremo - p >= self.cross_pernada_pontos:
                self._origem = self._extremo
                self._direcao = -1
                self._extremo = p
        else:
            if p < self._extremo:
                self._extremo = p
            elif p - self._extremo >= self.cross_pernada_pontos:
                self._origem = self._extremo
                self._direcao = 1
                self._extremo = p

    def _monta_entrada_cross(self, direcao_entrada: int, bar: Bar) -> IntradayAction | None:
        buf = self.cross_buffer_entrada_pontos
        if direcao_entrada == 1:
            lado = "long"
            limite = bar.close - buf
            stop = limite - self.cross_stop_pontos
            alvo = limite + self.cross_alvo_multiplo * self.cross_stop_pontos
        else:
            lado = "short"
            limite = bar.close + buf
            stop = limite + self.cross_stop_pontos
            alvo = limite - self.cross_alvo_multiplo * self.cross_stop_pontos

        limite = no_tick(limite, self.tick_size)
        if lado == "long" and limite >= bar.close:
            return None
        if lado == "short" and limite <= bar.close:
            return None

        return EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=f"g15_cross_{self.cross_direcao_aposta}_s{self.cross_stop_pontos:.0f}_a{self.cross_alvo_multiplo:.0f}x",
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
        self._hist.append(bar)
        self._inicializa_orcamento_se_preciso(ts)

        # -- transicao de posicao (estado do INICIO da barra, item 6.48) ----
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            origem = self._ordem_pendente_origem
            if positions:
                self.origem_por_entry_ts[positions[0].entry_ts] = origem or "desconhecida"
            if origem == "orb":
                self._orb_preencheu_hoje = True
            self._ordem_pendente_origem = None
        self._tinha_posicao_anterior = tem_posicao_agora

        # -- sinal A (ORB): faixa de abertura SEMPRE atualizada, com ou sem
        # posicao/pendencia/orcamento (item 6.48, identico a G08/G14). ------
        dentro_da_faixa = (ts - self._open_ts) < pd.Timedelta(minutes=self.orb_range_minutos)
        if dentro_da_faixa:
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            nova_alta = nova_baixa = False
        else:
            if self._range_hi is None or self._range_lo is None:
                nova_alta = nova_baixa = False
            else:
                rompeu_alta = bar.close > self._range_hi
                rompeu_baixa = bar.close < self._range_lo
                nova_alta = rompeu_alta and not self._fora_hi
                nova_baixa = rompeu_baixa and not self._fora_lo
                self._fora_hi = rompeu_alta
                self._fora_lo = rompeu_baixa

        if nova_alta or nova_baixa:
            self.stats_bruto_orb += 1
            self.horas_bruto_orb.append(ts.hour)

        # -- sinal B (cruzado): pernada maior SEMPRE atualizada (identico a
        # G04/G14, "nao condicionado a pode_armar"). -------------------------
        for p in _caminho_da_barra(bar):
            self._atualiza_perna(p)

        anomalo_agora = bool(self._wdo_anomalo.get(ts, False))
        direcao_sinal = int(self._wdo_direcao.get(ts, 0))
        disparo_novo_cross = anomalo_agora and not self._anomalo_anterior
        self._anomalo_anterior = anomalo_agora
        if disparo_novo_cross and direcao_sinal != 0:
            self.stats_bruto_cross += 1
            self.horas_bruto_cross.append(ts.hour)

        # -- portao compartilhado: nunca 2 posicoes, nunca 2 pendentes ------
        pode_emitir = (not tem_posicao_agora) and self._ordem_pendente_origem is None
        ja_emitiu_nesta_barra = False
        acoes: list[IntradayAction] = []

        # (1) ORB tem PRIORIDADE declarada no empate (ver docstring, identico
        # a G14). -------------------------------------------------------------
        orb_disparou_aqui = False
        if nova_alta or nova_baixa:
            if self._orb_preencheu_hoje:
                self.stats_orb_ja_operou_hoje += 1
            elif not self._regime_permite("orb", ts):
                self.stats_recusado_por_regime_orb += 1
            elif pode_emitir:
                if not self._ha_vaga():
                    self.stats_recusado_por_orcamento_orb += 1
                else:
                    stop_pontos, alvo_pontos = self._geometria_orb()
                    buf = self.orb_buffer_entrada_pontos
                    if nova_alta:
                        limite = bar.close - buf
                        acao = self._ordem_orb("long", limite, stop_pontos, alvo_pontos,
                                                "g15_orb_rompimento_alta")
                    else:
                        limite = bar.close + buf
                        acao = self._ordem_orb("short", limite, stop_pontos, alvo_pontos,
                                                "g15_orb_rompimento_baixa")
                    acoes.append(acao)
                    self._ordem_pendente_origem = "orb"
                    self._consome_vaga()
                    self.stats_ordens_emitidas_orb += 1
                    ja_emitiu_nesta_barra = True
                    orb_disparou_aqui = True

        # (2) cruzado -- so' considerado se o ORB NAO disparou NESTA barra. -
        if disparo_novo_cross and direcao_sinal != 0:
            direcao_entrada = direcao_sinal if self.cross_direcao_aposta == "continuacao" else -direcao_sinal
            if self._direcao != direcao_entrada:
                self.stats_cross_contra_tendencia += 1
            elif orb_disparou_aqui:
                self.stats_cross_perdeu_empate_pra_orb += 1
            elif not self._regime_permite("cross", ts):
                self.stats_recusado_por_regime_cross += 1
            elif pode_emitir and not ja_emitiu_nesta_barra:
                if not self._ha_vaga():
                    self.stats_recusado_por_orcamento_cross += 1
                else:
                    acao = self._monta_entrada_cross(direcao_entrada, bar)
                    if acao is not None:
                        acoes.append(acao)
                        self._ordem_pendente_origem = "cross"
                        self._consome_vaga()
                        self.stats_ordens_emitidas_cross += 1

        return acoes
