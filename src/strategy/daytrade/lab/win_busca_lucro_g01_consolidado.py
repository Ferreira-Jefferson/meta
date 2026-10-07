# -*- coding: utf-8 -*-
"""`WinBuscaLucroG01` -- Geracao 1 da busca por um EA lucrativo do WIN.

Mandato do dono (2026-10-04, `ORQUESTRACAO.md`): nao e' uma ideia nova.
E' a SINTESE consolidada de 7 rodadas de pesquisa sobre o WIN (jan-set/2026,
`REGRAS.md`/`CADERNO.md`, 65 regras) -- os filtros de QUANDO/QUANTO que
replicaram nas tres janelas, e os dois UNICOS gatilhos de direcao que
sobreviveram ao escrutinio sem inverter (R61 e R65), ambos ainda com IC95 do
acerto cruzando o breakeven e amostra pequena (n<70). Esta classe e' o
veiculo para medir se a SOMA desses achados paga o custo real -- nao uma
afirmacao de que paga.

## Portao LIGAR (todas as condicoes, para PROCURAR entrada numa barra)

1. Horario < limite de manha, ajustado por DST dos EUA (R01/R02/R28): o
   "salto de Nova York" entra as 10:30 BRT no horario de verao americano (2o
   domingo de marco a 1o domingo de novembro) e as 11:30 fora dele. O limite
   nominal deste robo (11:00 para procurar entrada, 13:00 para parar de
   qualquer jeito) foi calibrado em cima do regime de DST; fora do DST as
   duas marcas deslocam 1h mais tarde (12:00 / 14:00) -- e' a leitura mais
   direta de "antes disso o resto das regras de horario se aplicam
   deslocadas 1h" do pedido original.
2. Horario < limite de tarde (R03): nunca procurar entrada depois disso,
   redundante com (1) mas mantido explicito porque sao papeis diferentes
   (R01/R02 e' "ONDE a maior parte das pernadas nasce"; R03 e' "a partir daqui
   quase nao nasce pernada nova").
3. NAO em caixa estreita (R36): amplitude das ultimas `janela_amplitude_
   barras` (20) barras M1 >= `amplitude_minima_20min` (150 pontos). Portao
   DURO -- sem isto nao ha disputa real de 750 pontos possivel na janela.
4. (NAO IMPLEMENTADO nesta geracao, decisao documentada) R20/R35, "onda de
   volatilidade" -- bloco de 15 min acima da mediana do mesmo horario nos
   ~20 pregoes anteriores, ou vela M1 >= 2x o mesmo minuto nos 20 pregoes
   anteriores. O proprio REGRAS.md classifica isto como BONUS ("nao e'
   portao duro"), e medi-lo exigiria estatistica CROSS-SESSAO (o mesmo
   minuto/bloco em pregoes PASSADOS) alimentada de fora por um hook de seed
   -- o mesmo padrao arquitetural de `seed_daily_volatility`/
   `JanelaVolatilidadeDiaria` ja usado no repo para nao quebrar a pureza da
   funcao de sinal (`strategy/` so' importa `core`, AGENTS.md regra 2). Para
   nao gastar o orcamento desta geracao nisso, o filtro fica DE FORA e
   marcado como proximo passo caso o resultado desta geracao seja
   "quase la'" -- ver o fim do modulo.

## Direcao -- NUNCA contra a pernada de 750 em curso (R43)

Zigzag causal de limiar `pernada_pontos` (750,0) sobre o CAMINHO da vela
(alta: minima->maxima; baixa: maxima->minima -- a definicao CONGELADA do
dono em 2026-10-04). A perna ATIVA (ainda nao revertida por 750 pontos) e' a
"pernada corrente"; o sentido dela e' o UNICO sentido em que este robo entra.
Reiniciado a cada pregao (`on_session_start`) -- mesma razao do
`WinRetangulo`: a serie continua `WIN@` tem saltos de rolagem que nao podem
atravessar a sessao disfarcados de movimento real.

## Gatilho 1 -- R61 (recuo de 62% de um avanco >= 500 na pernada corrente)

Dentro da perna ativa, assim que o avanco corrente (extremo - origem, no
sentido da perna) cruza `avanco_minimo_r61` (500,0) pela PRIMEIRA vez nesta
perna, o avanco e' CONGELADO (`extremo_ref`/`origem_ref`) e uma ordem-limite
e' armada no nivel de 62% de recuo desse avanco congelado, na direcao de
RETOMADA (compra se o avanco foi de alta). Stop = 1/3 da distancia
entrada->extremo, do lado de fora; alvo = o proprio extremo_ref. A razao
alvo:stop sai em `1 / stop_fracao_r61` SEMPRE (independente de
`recuo_fracao_r61`) -- o construtor RECUSA `stop_fracao_r61` que renda menos
de 3:1.

So' o 1o recuo conta: uma vez armado para esta perna (`_r61_ultima_perna_
armada`), nao se re-arma ate' a perna mudar (zigzag reverter 750 e comecar
nova perna). Se a propria perna continuar se estendendo depois do
congelamento, o nivel/stop/alvo NAO perseguem o novo extremo -- simplificacao
deliberada, documentada aqui por nao ser a unica leitura possivel da regra.

## Gatilho 2 -- R65 (M15 rompe so' a EMA9, H1 alinhado)

EMAs mantidas POR DENTRO do robo via agregacao causal de M1 em M15/H1
(fecha a cada `ts.minute % 15 == 14` / `ts.minute == 59`). Ao contrario do
zigzag de pernada, estas EMAs **atravessam a sessao** (nao resetam em
`on_session_start`) -- e' uma escolha deliberada e tem um motivo concreto:
a janela de busca deste robo fecha as ~11-14h, e um EMA9 de H1 reiniciado a
cada pregao nunca teria mais que 2-5 barras H1 fechadas dentro da propria
janela de busca, ou seja, NUNCA aqueceria a tempo de disparar nada. O risco
conhecido (o salto de rolagem do `WIN@` contaminar a EMA por uma barra) e'
MENOR que o de uma estrategia que nunca teria amostra: uma EMA absorve um
salto e volta a seguir o preco em poucos periodos; um NIVEL de preco fixo
(como a borda de um retangulo) carregaria o erro a sessao inteira. Fica
registrado como ponto a testar se esta geracao for promovida.

"Rompe so' a EMA9, nao a EMA21": o FECHAMENTO do M15 fica estritamente ENTRE
as duas EMAs (`ema9 < close < ema21` para alta, invertido para baixa) --
geometria que so' existe quando a EMA rapida ja' esta' do lado contrario a'
lenta (ou seja, exige as duas EMAs cruzadas/proximas, nao duas EMAs
alinhadas com preco rompendo as duas de uma vez). Disparo por BORDA (so' na
primeira vez que o M15 fechado entra nesta zona, nao em todo fechamento
dentro dela).

"H1 alinhado" (definicao operacional escolhida, das duas sugeridas):
fechamento do H1 do MESMO LADO da EMA9 do H1 (`close_h1 > ema9_h1` para
alinhamento de alta). Mais simples que inclinacao e nao exige guardar
historico extra de EMA.

Execucao: como o desenho fechado do projeto proibe ordem a mercado mesmo
numa entrada de ROMPIMENTO, a "entrada na direcao do rompimento" vira um
RETESTE -- ordem-limite no proprio nivel da EMA9 do M15 (o preco acabou de
romper para cima dela; a limite de compra descansa ABAIXO do preco corrente
exatamente nesse nivel, esperando o reteste). Stop tecnico = extremo das
ultimas `barras_stop_tecnico_r65` (10) velas M1 antes da entrada; alvo =
`alvo_multiplo_r65` (5,0, escolhido A PRIORI no ponto medio-baixo da faixa
"5-10x" do mandato do dono, NAO ajustado a partir do resultado do IS) vezes
esse risco.

## Execucao -- o desenho fechado, sem excecao (CLAUDE.md)

Entrada so' por `EnterLimit` com `ttl_bars` (prazo obrigatorio, nunca
`None`); alvo so' como ordem-limite real fatiada (`exit_split_unit`), SEM
prazo (`exit_ttl_bars=None`); so' o stop e' a mercado; `anchor_exits_at_
fill=True`; `target_fills_as_maker=True`. Conferencia MECANICA antes de
armar (limite de venda so' descansa ACIMA do preco corrente, de compra so'
ABAIXO) -- mesma rotina de `WinRetangulo`.

## Fila -- WIN@ nao tem fidelidade calibrada

`backtest.intraday.fidelidade` so' tem WDO@. Toda medicao desta classe roda
com `queue_ahead_qty=0`/`exit_queue_ahead_qty=0` (preenche no toque),
declarado EXPLICITAMENTE na config do script de teste -- precedente de
`WinRetangulo`. E' premissa OTIMISTA, identica nas duas janelas (IS/OOS),
entao a COMPARACAO e' honesta; o NIVEL absoluto nao e' previsao.

## Capital e dimensionamento

1 contrato FIXO nesta geracao (`quantity=1`, sem escala por caixa) --
dimensionamento dinamico e' pergunta de geracao futura, nao desta. O motor
aplica o teto por margem (`contracts_from_capital_operacional`) por cima de
qualquer jeito, entao o robo nunca abre mais do que o caixa realmente
sustenta mesmo pedindo sempre 1.
"""
from __future__ import annotations

from collections import deque
from datetime import date as _date, timedelta as _timedelta

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

#: Limiar da pernada "oficial" (R43/R61) -- zigzag sobre o caminho da vela.
PERNADA_PONTOS = 750.0
#: Avanco minimo dentro da pernada corrente para armar o R61 (rodada 6).
AVANCO_MINIMO_R61 = 500.0
#: Fracao de recuo do avanco onde a limite de entrada do R61 descansa.
RECUO_FRACAO_R61 = 0.62
#: Fracao da distancia entrada->extremo que vira stop (do lado de fora).
#: 1/3 da' razao alvo:stop = 3:1 exatamente, por construcao (ver docstring).
STOP_FRACAO_R61 = 1.0 / 3.0
#: R36 -- amplitude minima dos ultimos 20 min para a caixa nao estar "presa".
AMPLITUDE_MINIMA_20MIN = 150.0
JANELA_AMPLITUDE_BARRAS = 20
#: Prazo da ordem-limite de ENTRADA, nos dois gatilhos (meio da faixa 5-15
#: barras sugerida -- nunca `None`, ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Periodos das EMAs do R65.
EMA_RAPIDA_M15 = 9
EMA_LENTA_M15 = 21
EMA_H1 = 9
#: Velas M1 que definem o stop tecnico do R65.
BARRAS_STOP_TECNICO_R65 = 10
#: Multiplo do risco que vira alvo no R65 -- ponto medio-BAIXO da faixa
#: "5-10x" do mandato do dono, fixado A PRIORI (nao ajustado olhando o IS).
ALVO_MULTIPLO_R65 = 5.0


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela, na ordem em que o preco
    provavelmente passou por eles -- definicao CONGELADA em `REGRAS.md`:
    vela de alta (fecha >= abre) anda minima->maxima; vela de baixa anda
    maxima->minima. Pura (so' le o `Bar` recebido)."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


def _segunda_domingo(ano: int, mes: int) -> _date:
    d = _date(ano, mes, 1)
    primeiro_domingo = d + _timedelta(days=(6 - d.weekday()) % 7)
    return primeiro_domingo + _timedelta(days=7)


def _primeiro_domingo(ano: int, mes: int) -> _date:
    d = _date(ano, mes, 1)
    return d + _timedelta(days=(6 - d.weekday()) % 7)


def dst_eua(dia: _date) -> bool:
    """`True` se `dia` cai dentro do horario de verao dos EUA (2o domingo de
    marco ate' o dia ANTERIOR ao 1o domingo de novembro) -- R28. Pura,
    so' aritmetica de calendario."""
    inicio = _segunda_domingo(dia.year, 3)
    fim = _primeiro_domingo(dia.year, 11)
    return inicio <= dia < fim


class WinBuscaLucroG01(IntradayStrategy):
    """Sintese consolidada (R43 + R61 + R65 + filtros de horario/caixa) --
    Geracao 1 da busca por um EA lucrativo do WIN (`ORQUESTRACAO.md`)."""

    name = "win_busca_lucro_g01_consolidado"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        modo: str = "combinado",
        pernada_pontos: float = PERNADA_PONTOS,
        avanco_minimo_r61: float = AVANCO_MINIMO_R61,
        recuo_fracao_r61: float = RECUO_FRACAO_R61,
        stop_fracao_r61: float = STOP_FRACAO_R61,
        amplitude_minima_20min: float = AMPLITUDE_MINIMA_20MIN,
        janela_amplitude_barras: int = JANELA_AMPLITUDE_BARRAS,
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        ema_rapida_m15: int = EMA_RAPIDA_M15,
        ema_lenta_m15: int = EMA_LENTA_M15,
        ema_h1: int = EMA_H1,
        barras_stop_tecnico_r65: int = BARRAS_STOP_TECNICO_R65,
        alvo_multiplo_r65: float = ALVO_MULTIPLO_R65,
        quantity: int = 1,
    ) -> None:
        """`modo`: `"r61"` (so' o gatilho 1), `"r65"` (so' o gatilho 2) ou
        `"combinado"` (os dois -- cada bar so' pode armar UMA ordem por vez;
        se os dois dispararem na mesma barra, R61 tem precedencia por ser o
        unico com razao alvo:stop garantida por construcao)."""
        if modo not in ("r61", "r65", "combinado"):
            raise ValueError(f"modo={modo!r} invalido: use 'r61', 'r65' ou 'combinado'")
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)"
            )
        if not (0.0 < stop_fracao_r61 <= 1.0 / 3.0 + 1e-9):
            raise ValueError(
                f"stop_fracao_r61={stop_fracao_r61} tem de respeitar razao "
                f"alvo:stop >= 3:1 (1/stop_fracao_r61 >= 3) -- ordem do dono 2026-09-08"
            )
        if (1.0 / stop_fracao_r61) < 3.0 - 1e-9:
            raise ValueError("razao alvo:stop do R61 ficou abaixo de 3:1 -- recuse esta configuracao")
        if alvo_multiplo_r65 < 3.0:
            raise ValueError(
                f"alvo_multiplo_r65={alvo_multiplo_r65} abaixo de 3x -- fere a disciplina "
                f"alvo >= 3x o stop do mandato do dono"
            )
        if symbol is not None:
            self.symbol = symbol
        self.modo = modo
        self.pernada_pontos = float(pernada_pontos)
        self.avanco_minimo_r61 = float(avanco_minimo_r61)
        self.recuo_fracao_r61 = float(recuo_fracao_r61)
        self.stop_fracao_r61 = float(stop_fracao_r61)
        self.amplitude_minima_20min = float(amplitude_minima_20min)
        self.janela_amplitude_barras = int(janela_amplitude_barras)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.ema_rapida_m15 = int(ema_rapida_m15)
        self.ema_lenta_m15 = int(ema_lenta_m15)
        self.ema_h1 = int(ema_h1)
        self.barras_stop_tecnico_r65 = int(barras_stop_tecnico_r65)
        self.alvo_multiplo_r65 = float(alvo_multiplo_r65)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size
        self.valor_do_ponto_brl = economia.point_value_brl

        # -- EMAs do R65: atravessam a sessao (ver docstring do modulo) ------
        self._ema9_m15: float | None = None
        self._ema21_m15: float | None = None
        self._ema9_h1: float | None = None
        self._m15_estado_anterior: str | None = None

        self._reset_sessao()

    # -- EMA incremental -----------------------------------------------------
    @staticmethod
    def _ema_update(anterior: float | None, preco: float, periodo: int) -> float:
        if anterior is None:
            return preco
        alfa = 2.0 / (periodo + 1)
        return alfa * preco + (1.0 - alfa) * anterior

    # -- horario (R01/R02/R03/R28) -------------------------------------------
    def _limites_horario(self, ts: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
        dia = ts.date()
        if dst_eua(dia):
            inicio_h, fim_h = 11, 13
        else:
            inicio_h, fim_h = 12, 14
        base = ts.normalize()
        return (base + pd.Timedelta(hours=inicio_h), base + pd.Timedelta(hours=fim_h))

    def _dentro_do_horario(self, ts: pd.Timestamp) -> bool:
        limite_inicio, limite_fim = self._limites_horario(ts)
        return ts < limite_inicio and ts < limite_fim

    # -- estado por sessao -----------------------------------------------------
    def _reset_sessao(self) -> None:
        self._hist: deque[Bar] = deque(maxlen=max(self.janela_amplitude_barras,
                                                    self.barras_stop_tecnico_r65) + 2)
        # zigzag da pernada (R43/R61) -- reseta a cada pregao, ver docstring.
        self._zz_origem: float | None = None
        self._zz_extremo: float | None = None
        self._zz_direcao: int | None = None
        self._perna_id: int = 0
        self._r61_ultima_perna_armada: int | None = None
        # acumulador do M15 corrente (fecha a cada ts.minute % 15 == 14)
        self._m15_high: float | None = None
        self._m15_low: float | None = None
        self._m15_estado_anterior = None
        self._h1_close_atual: float | None = None
        # ordem pendente (dos dois gatilhos, so' uma por vez)
        self._espera: int | None = None

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._espera = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._espera = None

    # -- zigzag da pernada (R43 + base do R61) -------------------------------
    def _zz_atualiza(self, p: float) -> None:
        if self._zz_origem is None:
            self._zz_origem = p
            self._zz_extremo = p
            return
        if self._zz_direcao is None:
            if p - self._zz_origem >= self.pernada_pontos:
                self._zz_direcao = 1
                self._zz_extremo = p
            elif self._zz_origem - p >= self.pernada_pontos:
                self._zz_direcao = -1
                self._zz_extremo = p
            return
        if self._zz_direcao == 1:
            if p > self._zz_extremo:
                self._zz_extremo = p
            elif self._zz_extremo - p >= self.pernada_pontos:
                self._zz_origem = self._zz_extremo
                self._zz_direcao = -1
                self._zz_extremo = p
                self._perna_id += 1
        else:
            if p < self._zz_extremo:
                self._zz_extremo = p
            elif p - self._zz_extremo >= self.pernada_pontos:
                self._zz_origem = self._zz_extremo
                self._zz_direcao = 1
                self._zz_extremo = p
                self._perna_id += 1

    @property
    def _avanco_corrente(self) -> float | None:
        if self._zz_direcao is None:
            return None
        if self._zz_direcao == 1:
            return self._zz_extremo - self._zz_origem
        return self._zz_origem - self._zz_extremo

    # -- R61: recuo de 62% de um avanco >= 500 -------------------------------
    def _tenta_armar_r61(self, bar: Bar) -> list[IntradayAction]:
        if self._zz_direcao is None:
            return []
        avanco = self._avanco_corrente
        if avanco is None or avanco < self.avanco_minimo_r61:
            return []
        if self._r61_ultima_perna_armada == self._perna_id:
            return []
        self._r61_ultima_perna_armada = self._perna_id
        origem_ref, extremo_ref, sentido = self._zz_origem, self._zz_extremo, self._zz_direcao
        avanco_ref = extremo_ref - origem_ref if sentido == 1 else origem_ref - extremo_ref
        if sentido == 1:
            nivel = extremo_ref - self.recuo_fracao_r61 * avanco_ref
            dist_alvo = extremo_ref - nivel
            stop = nivel - self.stop_fracao_r61 * dist_alvo
            lado = "long"
        else:
            nivel = extremo_ref + self.recuo_fracao_r61 * avanco_ref
            dist_alvo = nivel - extremo_ref
            stop = nivel + self.stop_fracao_r61 * dist_alvo
            lado = "short"
        alvo = extremo_ref
        limite = no_tick(nivel, self.tick_size)
        # conferencia mecanica: limite de venda so' descansa ACIMA do preco
        # corrente; de compra, so' ABAIXO -- senao e' ordem a mercado disfarcada.
        if lado == "long" and limite >= bar.close:
            return []
        if lado == "short" and limite <= bar.close:
            return []
        self._espera = 0
        return [EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=f"r61_avanco{avanco_ref:.0f}_recuo{self.recuo_fracao_r61:.2f}",
        )]

    # -- R65: M15 rompe so' a EMA9, H1 alinhado ------------------------------
    def _atualiza_m15_h1(self, ts: pd.Timestamp, bar: Bar) -> list[IntradayAction]:
        if self._m15_high is None:
            self._m15_high, self._m15_low = bar.high, bar.low
        else:
            self._m15_high = max(self._m15_high, bar.high)
            self._m15_low = min(self._m15_low, bar.low)

        acoes: list[IntradayAction] = []
        if ts.minute % 15 == 14:
            fechamento_m15 = bar.close
            self._ema9_m15 = self._ema_update(self._ema9_m15, fechamento_m15, self.ema_rapida_m15)
            self._ema21_m15 = self._ema_update(self._ema21_m15, fechamento_m15, self.ema_lenta_m15)
            self._m15_high = None
            self._m15_low = None
            acoes = self._avalia_r65(ts, bar, fechamento_m15)
        if ts.minute == 59:
            self._ema9_h1 = self._ema_update(self._ema9_h1, bar.close, self.ema_h1)
            self._h1_close_atual = bar.close
        return acoes

    def _avalia_r65(self, ts: pd.Timestamp, bar: Bar, fechamento_m15: float) -> list[IntradayAction]:
        if self._ema9_m15 is None or self._ema21_m15 is None or self._ema9_h1 is None:
            return []
        ema9, ema21 = self._ema9_m15, self._ema21_m15
        if ema9 < fechamento_m15 < ema21:
            estado = "long"
        elif ema21 < fechamento_m15 < ema9:
            estado = "short"
        else:
            estado = "fora"
        disparou = estado in ("long", "short") and estado != self._m15_estado_anterior
        self._m15_estado_anterior = estado
        if not disparou:
            return []
        # H1 alinhado: fechamento do H1 do mesmo lado da EMA9 do H1.
        alinhado_long = self._h1_close_atual is not None and self._h1_close_atual > self._ema9_h1
        alinhado_short = self._h1_close_atual is not None and self._h1_close_atual < self._ema9_h1
        if estado == "long" and not alinhado_long:
            return []
        if estado == "short" and not alinhado_short:
            return []
        # R43: nunca contra a pernada de 750 em curso.
        sentido_pernada = self._zz_direcao
        if sentido_pernada is None:
            return []
        if estado == "long" and sentido_pernada != 1:
            return []
        if estado == "short" and sentido_pernada != -1:
            return []
        if len(self._hist) < self.barras_stop_tecnico_r65:
            return []
        ultimas = list(self._hist)[-self.barras_stop_tecnico_r65:]
        nivel = no_tick(ema9, self.tick_size)
        if estado == "long":
            lado = "long"
            stop_tecnico = min(b.low for b in ultimas)
            risco = nivel - stop_tecnico
            if risco <= 0:
                return []
            alvo = nivel + self.alvo_multiplo_r65 * risco
        else:
            lado = "short"
            stop_tecnico = max(b.high for b in ultimas)
            risco = stop_tecnico - nivel
            if risco <= 0:
                return []
            alvo = nivel - self.alvo_multiplo_r65 * risco
        if lado == "long" and nivel >= bar.close:
            return []
        if lado == "short" and nivel <= bar.close:
            return []
        self._espera = 0
        return [EnterLimit(
            side=lado,
            limit_price=nivel,
            initial_stop=no_tick(stop_tecnico, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantity,
            ttl_bars=self.ttl_barras_entrada,
            exit_split_unit=self.quantity,
            exit_ttl_bars=None,
            reason=f"r65_reteste_ema{self.ema_rapida_m15}",
        )]

    # -- loop -----------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)
        for p in _caminho_da_barra(bar):
            self._zz_atualiza(p)
        acoes_r65 = self._atualiza_m15_h1(ts, bar)

        if positions:
            self._espera = None
            return []
        if self._espera is not None:
            self._espera += 1
            if self._espera < self.ttl_barras_entrada:
                return []
            self._espera = None

        if not self._dentro_do_horario(ts):
            return []
        if len(self._hist) < self.janela_amplitude_barras:
            return []
        janela = list(self._hist)[-self.janela_amplitude_barras:]
        amplitude = max(b.high for b in janela) - min(b.low for b in janela)
        if amplitude < self.amplitude_minima_20min:
            return []

        if self.modo == "r61":
            return self._tenta_armar_r61(bar)
        if self.modo == "r65":
            return acoes_r65
        # combinado: R61 tem precedencia (razao alvo:stop garantida por
        # construcao); R65 so' entra se R61 nao armou nesta barra.
        acao_r61 = self._tenta_armar_r61(bar)
        if acao_r61:
            return acao_r61
        return acoes_r65
