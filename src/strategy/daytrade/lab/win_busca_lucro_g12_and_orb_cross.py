# -*- coding: utf-8 -*-
"""`WinBuscaLucroG12AndOrbCross` -- Geracao 12 da busca por um EA lucrativo do WIN.

Mandato do COORDENADOR (`ORQUESTRACAO.md`, raciocinio da Geracao 11): o
orquestrador tinha concluido a busca na G10/11 (11 resultados honestos sem
edge validado). O coordenador pediu para continuar testando 4 alavancas ainda
nao tentadas; esta geracao ataca a alavanca (2) -- combinacao E (AND) de DOIS
SINAIS INDEPENDENTES, nao reentrada do mesmo gatilho (a G11 ja mostrou, com
dois metodos convergentes, que "forca" do PROPRIO rompimento ORB nao carrega
informacao -- aqui a aposta e' estruturalmente diferente: exigir que uma
segunda fonte de informacao, de ORIGEM DIFERENTE, concorde com a direcao do
rompimento ANTES de operar).

## Os dois sinais, cada um ja' uma geracao anterior desta busca

- **Sinal A -- ORB (G8, `WinBuscaLucroG08OrbSobrevivencia`):** rompimento da
  faixa de abertura (`range_minutos`), direcao = lado rompido (momentum).
  Logica de deteccao COPIADA literalmente da G08 (range/fora_hi/fora_lo/borda
  nova) -- nenhuma mudanca na deteccao do rompimento em si.
- **Sinal B -- estado anomalo WIN x WDO (G4, `estado_anomalo_cruzado` de
  `win_busca_lucro_g04_cross_wdo.py`, IMPORTADO, nao reimplementado):
  direcao = CONTINUACAO prevista (mandato desta geracao fixa
  `direcao_aposta="continuacao"`, janela_min=20, quantil=0.75 -- os mesmos
  parametros que a G4 tinha apontado como o unico candidato com liquido
  positivo no IS e OOS-1, antes de a concentracao/IC terem reprovado a G4
  sozinha). Igual a` G04, o estado e' pre-computado FORA da classe (funcao
  pura, duas series alinhadas por timestamp) e entregue ao construtor -- o
  motor so' entrega a barra do simbolo operado (WIN@), nao ha' caminho para
  ler WDO@ barra a barra dentro de `on_bar` sem mudar o motor (mesma excecao
  DECLARADA a` regra 2 do AGENTS.md que a G4 ja documentou).

## A regra de entrada combinada (o que esta geracao de fato testa)

So' entra no rompimento ORB (sinal A) se, numa janela CAUSAL de `k_minutos`
minutos terminando NO PROPRIO instante do rompimento (inclusive -- `k_minutos
=0` quer dizer "so' o mesmo minuto do rompimento", nunca um minuto no
futuro), o sinal B tambem esteve ATIVO e apontando para a MESMA direcao do
lado rompido em ALGUM instante dessa janela. "Ativo" = `anomalo[t]=True` (nao
precisa ser a borda de subida do episodio -- um episodio de anomalia que
comecou alguns minutos antes do rompimento e ainda esta' em curso TAMBEM
conta, porque a pergunta e' "a informacao nova do sinal B estava disponivel
recentemente", nao "o episodio nasceu exatamente agora"). A janela e'
mantida com um deque de `(timestamp, direcao_b_ou_zero)`, podada por tempo
(`ts - k_minutos minutos`) a cada barra -- nunca por contagem de barras, pela
mesma razao do item do CLAUDE.md sobre `ttl_bars` em base de tick (aqui a
base e' M1, entao bars==minutos, mas a comparacao e' sempre por TEMPO, nunca
por indice, para o codigo nao quebrar se um dia rodar em outra resolucao).

`k_minutos in {0, 5, 15, 30}` e' o eixo causal que o harness varre dentro do
IS (ver `g12_is_busca.py`) -- NAO e' parametro desta classe com default
escondido: e' passado explicito em cada celula testada.

## Geometria -- herdada da G8 como ponto de partida, retunavel dentro do IS

`stop = clip(faixa_de_abertura, stop_min_pontos, stop_max_pontos)`; `alvo =
stop x alvo_multiplo` (sempre >= 3x por construcao, mesma guarda de
G04/G06/G07/G08). Como o AND deve reduzir MUITO a frequencia (G8 bruto=1084
bordas no IS; a fracao que tambem bate o sinal B e' tipicamente uma minoria),
o harness desta geracao sente-se livre para retunar `stop_max_pontos` e
`alvo_multiplo` dentro do IS -- a amostra menor pode pedir um stop diferente
do vencedor isolado da G8 (140 pontos) para nao ficar censurada.

## Execucao -- o desenho FECHADO, sem excecao (CLAUDE.md)

`EnterLimit` com `ttl_barras_entrada` obrigatorio (nunca `Enter` a mercado);
limite `buffer_entrada_pontos` ATRAS do fechamento do rompimento; alvo so'
como ordem-limite real fatiada (`exit_split_unit`), SEM prazo
(`exit_ttl_bars=None` -- so' pesquisa/backtest, producao exigiria o valor
enorme de `EXIT_TTL_BARS_SEM_PRAZO`); `anchor_exits_at_fill=True`; so' o
STOP e' a mercado; `target_fills_as_maker=True`. Fila do WIN@ NAO calibrada
-- toda ordem-limite enche no TOQUE (premissa OTIMISTA declarada, precedente
G1-G11). Capital real R$250 (1 contrato fixo, mesma politica de toda a
linha G4-G11 a este capital).

## Contadores de auditoria (item 6.48/6.49 de LICOES_DE_PRODUCAO.md)

`stats_bruto_a` conta toda borda NOVA de rompimento ORB (sinal A), ANTES de
qualquer filtro -- identico ao `stats_bruto` da G08. `stats_bruto_b` conta
toda borda NOVA de episodio anomalo (sinal B) com direcao definida,
independente do ORB -- identico ao `stats_bruto` da G04. `stats_and_bruto`
conta as bordas de A em que o filtro B TAMBEM bateu (mesma direcao, dentro
da janela de `k_minutos`), calculado ANTES de qualquer filtro de posicao
aberta/ja-armado-hoje/ja-operou-hoje -- e' o "A∩B bruto" pedido pelo
mandato. `stats_ordens_emitidas` conta so' as que viraram `EnterLimit` de
verdade (depois de todos os filtros de execucao). A disciplina "estado
recalculado ANTES de checar ordem pendente" (bug da G2, item 6.48) e'
replicada aqui: a janela do sinal B e o estado fora_hi/fora_lo sao SEMPRE
atualizados, com posicao aberta ou nao; os filtros de armado/ja-operou leem
flags que so' MUDAM depois de emitir ou nos callbacks de rejeicao/expiracao,
nunca dentro do mesmo passo em que sao lidos.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

__all__ = ["WinBuscaLucroG12AndOrbCross"]

#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
#: Mesmo valor de G1-G11 desta busca.
TTL_BARRAS_ENTRADA = 10


class WinBuscaLucroG12AndOrbCross(IntradayStrategy):
    """Rompimento da faixa de abertura do WIN@ (sinal A, logica da G08), SO'
    executado quando o estado anomalo WIN x WDO (sinal B, logica da G04,
    direcao=continuacao) tambem concordou com a MESMA direcao dentro de uma
    janela causal de `k_minutos` -- Geracao 12 da busca por um EA lucrativo
    do WIN (`ORQUESTRACAO.md`), mandato do COORDENADOR: combinacao AND de
    dois sinais de origens DIFERENTES, nao reentrada do mesmo gatilho."""

    name = "win_busca_lucro_g12_and_orb_cross"
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
        range_minutos: float = 5.0,
        stop_min_pontos: float = 50.0,
        stop_max_pontos: float = 140.0,
        alvo_multiplo: float = 3.0,
        buffer_entrada_pontos: float = 20.0,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        k_minutos: float = 0.0,
        quantity: int = 1,
    ) -> None:
        if range_minutos <= 0:
            raise ValueError("range_minutos tem que ser positivo")
        if stop_min_pontos <= 0:
            raise ValueError("stop_min_pontos tem que ser positivo")
        if stop_max_pontos < stop_min_pontos:
            raise ValueError("stop_max_pontos tem que ser >= stop_min_pontos")
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
        if k_minutos < 0:
            raise ValueError("k_minutos nao pode ser negativo")
        if symbol is not None:
            self.symbol = symbol
        self._wdo_anomalo = wdo_anomalo.to_dict() if isinstance(wdo_anomalo, pd.Series) else dict(wdo_anomalo)
        self._wdo_direcao = wdo_direcao.to_dict() if isinstance(wdo_direcao, pd.Series) else dict(wdo_direcao)
        self.range_minutos = float(range_minutos)
        self.stop_min_pontos = float(stop_min_pontos)
        self.stop_max_pontos = float(stop_max_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.buffer_entrada_pontos = float(buffer_entrada_pontos)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.k_minutos = float(k_minutos)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size

        # -- contadores de auditoria (item 6.48/6.49) --
        self.stats_bruto_a = 0
        self.stats_bruto_b = 0
        self.stats_and_bruto = 0
        self.stats_ja_operou_hoje = 0
        self.stats_sem_confirmacao_b = 0
        self.stats_ordens_emitidas = 0

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
        self._anomalo_anterior = False
        # janela causal do sinal B -- NAO reseta entre pregoes por conta
        # propria (um episodio pode comecar perto do fechamento do pregao
        # anterior e o motor so' entrega barras do pregao seguinte depois de
        # `on_session_start`; na pratica o WDO/WIN nao carregam estado
        # noturno nesta busca -- ver docstring -- mas a janela e' esvaziada
        # aqui mesmo assim porque o primeiro `on_bar` do dia novo ja' poda
        # por tempo qualquer entrada antiga).
        self._janela_b: deque = deque()

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._armou_hoje = False

    # -- geometria (pura, identica a` G08) -------------------------------------
    def _geometria(self) -> tuple[float, float]:
        assert self._range_hi is not None and self._range_lo is not None
        range_pontos = self._range_hi - self._range_lo
        stop = max(self.stop_min_pontos, min(self.stop_max_pontos, range_pontos))
        stop = round(stop / self.tick_size) * self.tick_size
        alvo = round((stop * self.alvo_multiplo) / self.tick_size) * self.tick_size
        return float(stop), float(alvo)

    def _ordem(self, side: str, limite: float, stop_pontos: float,
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

    # -- sinal B (janela causal) ------------------------------------------------
    def _atualiza_janela_b(self, ts: pd.Timestamp) -> None:
        """Atualiza a janela deslizante do sinal B -- SEMPRE roda, com ou
        sem posicao aberta, antes de qualquer decisao (disciplina 6.48)."""
        anomalo_agora = bool(self._wdo_anomalo.get(ts, False))
        direcao_agora = int(self._wdo_direcao.get(ts, 0)) if anomalo_agora else 0

        disparo_novo = anomalo_agora and not self._anomalo_anterior
        self._anomalo_anterior = anomalo_agora
        if disparo_novo and direcao_agora != 0:
            self.stats_bruto_b += 1

        self._janela_b.append((ts, direcao_agora))
        limite_ts = ts - pd.Timedelta(minutes=self.k_minutos)
        while self._janela_b and self._janela_b[0][0] < limite_ts:
            self._janela_b.popleft()

    def _sinal_b_confirma(self, direcao_rompimento: int) -> bool:
        """True se o sinal B esteve ATIVO e na MESMA direcao do rompimento
        em QUALQUER instante dentro da janela causal de `k_minutos` (janela
        ja' podada por `_atualiza_janela_b`, inclui o proprio instante do
        rompimento)."""
        return any(d == direcao_rompimento for _, d in self._janela_b)

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

        # Transicao de posicao -- estado do INICIO da barra (item 6.48).
        tem_posicao_agora = bool(positions)
        if tem_posicao_agora and not self._tinha_posicao_anterior:
            self._preencheu_hoje = True
        self._tinha_posicao_anterior = tem_posicao_agora

        # Sinal B -- SEMPRE atualizado, independente de range/rompimento.
        self._atualiza_janela_b(ts)

        # (1) os primeiros `range_minutos`: so' olha e mede a faixa.
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

        # BRUTO A: toda borda de rompimento ORB, ANTES de qualquer filtro.
        self.stats_bruto_a += 1
        direcao_rompimento = 1 if nova_alta else -1

        # BRUTO A∩B: a borda de A em que B TAMBEM confirma a mesma direcao,
        # calculado ANTES de qualquer filtro de posicao/armado/ja-operou.
        b_confirma = self._sinal_b_confirma(direcao_rompimento)
        if b_confirma:
            self.stats_and_bruto += 1

        if positions:
            return []
        if self._preencheu_hoje:
            self.stats_ja_operou_hoje += 1
            return []
        if self._armou_hoje:
            return []
        if not b_confirma:
            self.stats_sem_confirmacao_b += 1
            return []

        stop_pontos, alvo_pontos = self._geometria()
        buf = self.buffer_entrada_pontos
        if nova_alta:
            limite = bar.close - buf
            self._armou_hoje = True
            self.stats_ordens_emitidas += 1
            return [self._ordem("long", limite, stop_pontos, alvo_pontos,
                                f"g12_and_orb_cross_alta_k{self.k_minutos:g}")]
        limite = bar.close + buf
        self._armou_hoje = True
        self.stats_ordens_emitidas += 1
        return [self._ordem("short", limite, stop_pontos, alvo_pontos,
                            f"g12_and_orb_cross_baixa_k{self.k_minutos:g}")]
