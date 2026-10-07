"""Ribbon de 4 médias móveis a 34 períodos (SMA/EMA/SMMA/LWMA) sobre o
close, CONTÍNUAS entre pregões -- iguais às médias padrão que o MT5
desenha no gráfico (o dono opera olhando elas). Uma vela só "conta" se
o CORPO inteiro (open e close; pavio não conta) estiver fora do ribbon
-- acima da MM mais alta numa compra, abaixo da mais baixa numa venda.

COMPRA: N velas verdes limpas (tendência), depois EXATAMENTE UMA
vermelha limpa (contrária), e a verde limpa seguinte é o gatilho --
compra no fechamento dela; duas contrárias seguidas queimam a onda
(sem entrada até voltar ao ribbon). VENDA é o espelho. Qualquer vela
cujo corpo encoste em alguma MM cancela a espera. Da 1ª vela a favor
até o gatilho, se as 4 MMs pararem de apontar a favor em alguma vela
(comparada com a anterior), ou se uma MM cruzar outra CONTRA o lado
(compra: mais rápida furando para baixo de uma mais lenta), a espera
também é cancelada -- gatilho reprovado queima a onda.

Uma operação por onda: depois de uma entrada, nova entrada no mesmo
lado só depois de algum fechamento voltar para dentro do ribbon.
`max_entradas_dia`: só as N primeiras entradas do pregão (o ribbon
degrada depois de várias ondas no mesmo dia). `range_dia_max_pontos`:
bloqueia entrada se o range acumulado do pregão (máxima-mínima desde
a abertura) já passou disso.

Stop nasce e é reposicionado a cada fechamento colado na MM mais
próxima, e só aperta, nunca afrouxa (regra do motor para
`AdjustStop`). Alvo fixo = `alvo_multiplo_stop` x a largura do ribbon
(MM mais alta - mais baixa) no gatilho, não se move depois.

CONFIG PADRÃO -- achada via otimização real do MT5 (algoritmo
completo, "para frente" ago/2026->set/2026, critério "Fator de
Recuperação") e CONFERIDA de forma independente neste simulador nas
duas janelas (ver `wdo_ribbon_mm34_recorde_2026_09_29.md` na memória
do projeto): MMs apontando a favor em toda a espera, `max_entradas_dia
= 3`, `range_dia_max_pontos = 65.0`, `alvo_multiplo_stop = 25.0` (x a
largura do ribbon). Agosto: 45 ops/+79,5 pts. Setembro: 54 ops/
+133,5 pts -- 2,15 pts/operação, contra 1,85 pts/operação da config
anterior (só 5 ondas/dia, range<50) nas duas janelas.

ALTERNATIVAS JÁ TESTADAS E REJEITADAS (não reintroduzir sem medir de
novo -- números e datas na memória do projeto):
  - Alvo fixo em múltiplo do risco inicial (entrada-stop), ou pela
    distância até a abertura da 1ª vela a favor, ou pelo tamanho da
    vela do gatilho: todos perderam do alvo pela largura do ribbon.
  - Filtro "MMs em ordem" (empilhadas por velocidade LWMA>EMA>SMA>
    SMMA no gatilho): dominava o resultado DENTRO da amostra (ago/
    2026, 64% das combinações pareciam ótimas) mas quase não
    sobrevivia FORA dela (set/2026, só 2,9%) -- overfitting clássico.
  - Sem filtro de alinhamento nenhum: pior nos dois períodos.
  - Stop fixo (na vela contrária, ou parado onde nasceu na MM, sem
    trailing): piora muito -- o trailing é o que sustenta o alvo
    distante, deixando a operação boa correr.
  - Exigir o PAVIO inteiro fora do ribbon (não só o corpo): corta
    operações boas e deixa entrar mais tarde nas ruins.
  - Filtros de qualidade na entrada (risco mínimo, volume do gatilho
    acima da mediana, ribbon largo) cortavam volume demais para
    compensar o ganho por operação -- ficam como pista para limiares
    mais brandos numa rodada futura, não implementados hoje.
  - Uma tentativa manual de apertar para onda<=3 com range<45 NÃO se
    sustentou fora da amostra; a otimização completa do MT5 achou que
    onda<=3 SIM generaliza, mas só combinado com range mais alto
    (~65). O parâmetro isolado não era o problema -- era a combinação.

Entrada `Enter` (a mercado), a pedido explícito do dono -- este robô
está sendo testado sem seguir a regra geral do projeto de entrada só
via `EnterLimit` (ver CLAUDE.md, "O desenho de execução é FECHADO").
Roda em backtest (preenche no `open` da barra seguinte); em execução
REAL ao vivo não tem caminho hoje (`machine._entrar_a_mercado` levanta
`EntradaAMercadoNaoSuportada` de propósito).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from core.indicators import ema, lwma, sma, smma
from strategy.daytrade.base import (
    AdjustStop, Bar, Enter, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, no_tick,
)


@dataclass
class WdoRibbonMm34(IntradayStrategy):
    """Ribbon de 4 MMs a `periodo` (default 34). Entrada via `Enter` (a
    mercado) na barra seguinte ao fechamento de confirmação; stop
    inicial e trailing sempre colados na média mais próxima do preço,
    com folga de `stop_buffer_pontos` (em PONTOS de preço, não ticks)."""

    name: str = "wdo_ribbon_mm34"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = False
    anchor_exits_at_fill: bool = False
    feed_kind: str = "m1"
    is_futuro: bool = True
    tick_size: float = 0.5

    periodo: int = 34
    stop_buffer_pontos: float = 0.0
    #: alvo fixo = entrada +/- alvo_multiplo_stop x a largura do ribbon no gatilho.
    alvo_multiplo_stop: float = 25.0
    #: só as N primeiras entradas do pregão (None = sem limite); o ribbon
    #: degrada depois de várias ondas no mesmo dia.
    max_entradas_dia: int | None = 3
    #: bloqueia a entrada se o range acumulado do pregão (máxima-mínima de
    #: todas as barras desde a abertura até a barra do gatilho, inclusive)
    #: já for >= este valor em PONTOS. None = sem limite.
    range_dia_max_pontos: float | None = 65.0

    _ribbon_max_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _ribbon_min_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _medias_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    #: None | "long" | "short" -- lado da espera atual.
    _lado: str | None = field(default=None, init=False, repr=False)
    #: None | "tendencia" (ja' viu vela limpa a favor) | "contraria" (ja'
    #: viu vela limpa contra depois da tendencia; a proxima a favor dispara).
    _fase: str | None = field(default=None, init=False, repr=False)
    #: valores das 4 MMs na primeira vela da espera atual.
    _medias_referencia: tuple | None = field(default=None, init=False, repr=False)
    _medias_anteriores_por_ts: dict = field(default_factory=dict, init=False, repr=False)
    _sempre_apontando: bool = field(default=True, init=False, repr=False)
    #: largura do ribbon (MM mais alta - mais baixa) no gatilho.
    _largura_ribbon_gatilho: float = field(default=0.0, init=False, repr=False)
    #: uma operacao por onda: o lado fica travado depois de uma entrada ate'
    #: algum fechamento voltar para dentro do ribbon (ou passar para o outro lado).
    _travado: dict = field(default_factory=lambda: {"long": False, "short": False}, init=False, repr=False)
    #: contagem de entradas JA' FEITAS no pregao atual (1a entrada = 0 antes dela).
    _entradas_hoje: int = field(default=0, init=False, repr=False)
    #: maxima/minima acumuladas do pregao atual, atualizadas barra a barra.
    _dia_high: float | None = field(default=None, init=False, repr=False)
    _dia_low: float | None = field(default=None, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._reset()
        self._travado = {"long": False, "short": False}
        self._entradas_hoje = 0
        self._dia_high = None
        self._dia_low = None

    def _reset(self) -> None:
        self._lado = None
        self._fase = None
        self._medias_referencia = None

    def initialize(self, bars: pd.DataFrame) -> None:
        close = bars["close"]
        # MMs CONTINUAS entre pregoes -- iguais as medias padrao que o MT5
        # desenha no grafico (o dono opera olhando elas). O reset diario que
        # existiu aqui deixava o ribbon do robo em outro lugar no inicio do
        # pregao (03/09 09:41: topo 5110,6 no robo x 5114,7 no grafico).
        medias = pd.concat(
            [
                sma(close, self.periodo),
                ema(close, self.periodo),
                smma(close, self.periodo),
                lwma(close, self.periodo),
            ],
            axis=1,
        )
        ribbon_max = medias.max(axis=1)
        ribbon_min = medias.min(axis=1)
        self._ribbon_max_por_ts = {ts: float(v) for ts, v in ribbon_max.items() if pd.notna(v)}
        self._ribbon_min_por_ts = {ts: float(v) for ts, v in ribbon_min.items() if pd.notna(v)}
        self._medias_por_ts = {
            ts: tuple(row) for ts, row in medias.iterrows() if row.notna().all()
        }
        # MMs da vela imediatamente anterior no grafico (o iMA shift 2 do EA)
        anteriores = medias.shift(1)
        self._medias_anteriores_por_ts = {
            ts: tuple(row) for ts, row in anteriores.iterrows() if row.notna().all()
        }

    def _stop_compra(self, mm: float) -> float:
        # arredonda para LONGE da MM: distancia nunca menor que stop_buffer_pontos
        return math.floor((mm - self.stop_buffer_pontos) / self.tick_size + 1e-9) * self.tick_size

    def _stop_venda(self, mm: float) -> float:
        return math.ceil((mm + self.stop_buffer_pontos) / self.tick_size - 1e-9) * self.tick_size

    #: rapidez de cada MM (SMA, EMA, SMMA, LWMA): LWMA > EMA > SMA > SMMA.
    _VELOCIDADE = (1, 2, 0, 3)

    @classmethod
    def _cruzou_contra(cls, lado: str, ref: tuple, atual: tuple) -> bool:
        """Cruzamento CONTRA o lado: na compra, uma MM mais rapida que estava
        acima de uma mais lenta passou para baixo dela; na venda, o espelho.
        Cruzamento a favor (rapida furando para o lado da operacao) nao conta."""
        for i in range(4):
            for j in range(4):
                if cls._VELOCIDADE[i] <= cls._VELOCIDADE[j]:
                    continue
                if lado == "long" and ref[i] > ref[j] and atual[i] < atual[j]:
                    return True
                if lado == "short" and ref[i] < ref[j] and atual[i] > atual[j]:
                    return True
        return False

    @staticmethod
    def _apontam(lado: str, atual: tuple, antes: tuple | None) -> bool:
        if antes is None:
            return False
        if lado == "long":
            return all(a > b for a, b in zip(atual, antes))
        return all(a < b for a, b in zip(atual, antes))

    def on_bar(
        self, ts: pd.Timestamp, bar: Bar,
        positions: list[IntradayOpenPosition], session_pnl_brl: float,
    ) -> list[IntradayAction]:
        ribbon_max = self._ribbon_max_por_ts.get(ts)
        ribbon_min = self._ribbon_min_por_ts.get(ts)
        valores_mm = self._medias_por_ts.get(ts)
        if ribbon_max is None or ribbon_min is None or valores_mm is None:
            return []
        medias_anteriores = self._medias_anteriores_por_ts.get(ts)

        self._dia_high = bar.high if self._dia_high is None else max(self._dia_high, bar.high)
        self._dia_low = bar.low if self._dia_low is None else min(self._dia_low, bar.low)

        if bar.close <= ribbon_max:
            self._travado["long"] = False
        if bar.close >= ribbon_min:
            self._travado["short"] = False

        if positions:
            acao: list[IntradayAction] = []
            for pos in positions:
                if pos.side == "long":
                    candidato = self._stop_compra(ribbon_max)
                    if pos.current_stop is None or candidato > pos.current_stop:
                        acao.append(AdjustStop(new_stop=candidato))
                else:
                    candidato = self._stop_venda(ribbon_min)
                    if pos.current_stop is None or candidato < pos.current_stop:
                        acao.append(AdjustStop(new_stop=candidato))
            return acao

        verde = bar.close > bar.open
        vermelha = bar.close < bar.open
        corpo_baixo = min(bar.open, bar.close)
        corpo_alto = max(bar.open, bar.close)

        if corpo_baixo > ribbon_max:
            lado, a_favor, contra, ref = "long", verde, vermelha, ribbon_max
        elif corpo_alto < ribbon_min:
            lado, a_favor, contra, ref = "short", vermelha, verde, ribbon_min
        else:
            self._reset()
            return []

        if self._lado != lado or (
            self._lado is not None and self._cruzou_contra(lado, self._medias_referencia, valores_mm)
        ):
            self._reset()

        if self._fase is None:
            if a_favor and not self._travado[lado]:
                self._lado = lado
                self._fase = "tendencia"
                self._medias_referencia = valores_mm
                self._sempre_apontando = self._apontam(lado, valores_mm, medias_anteriores)
            return []
        self._sempre_apontando = self._sempre_apontando and self._apontam(lado, valores_mm, medias_anteriores)
        if self._fase == "tendencia":
            if contra:
                self._fase = "contraria"
            return []
        if contra:
            # segunda contraria seguida queima a onda: sem entrada ate' voltar ao ribbon
            self._reset()
            self._travado[lado] = True
            return []
        if not a_favor:
            return []
        if not self._sempre_apontando:
            # gatilho com MMs desalinhadas: nao opera esta onda
            self._reset()
            self._travado[lado] = True
            return []
        if self.max_entradas_dia is not None and self._entradas_hoje >= self.max_entradas_dia:
            # ja' passou do numero de ondas permitido no pregao: nao opera mais hoje
            self._reset()
            self._travado[lado] = True
            return []
        if self.range_dia_max_pontos is not None and (self._dia_high - self._dia_low) >= self.range_dia_max_pontos:
            # pregao ja' esta' agitado demais ate' aqui: nao opera esta onda
            self._reset()
            self._travado[lado] = True
            return []

        self._reset()
        self._travado[lado] = True
        self._entradas_hoje += 1
        stop = self._stop_compra(ref) if lado == "long" else self._stop_venda(ref)
        # o preco real de entrada so' existe na barra seguinte; aqui o close do
        # gatilho e' a estimativa (o EA usa o ask/bid do momento da ordem)
        self._largura_ribbon_gatilho = ribbon_max - ribbon_min
        alvo = self.alvo_para(lado, bar.close, stop)
        if alvo is None:
            return []
        return [Enter(side=lado, initial_stop=stop, initial_target=alvo, quantity=1, reason=self.name)]

    def alvo_para(self, lado: str, entrada: float, stop: float) -> float | None:
        """Alvo fixo para uma entrada a `entrada`. None = alvo nao fica do
        lado do lucro (distancia zerada ou negativa -- nao deve acontecer
        com o ribbon, e' so' salvaguarda)."""
        sinal = 1 if lado == "long" else -1
        distancia = self.alvo_multiplo_stop * self._largura_ribbon_gatilho
        if distancia < self.tick_size:
            return None
        return no_tick(entrada + sinal * distancia, self.tick_size)
