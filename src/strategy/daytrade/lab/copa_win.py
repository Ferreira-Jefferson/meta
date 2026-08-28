"""`copa_win` — rompimento de faixa intradiaria no mini-indice (WIN),
desenhado para a Copa BTG Trader.

## Por que ROMPIMENTO aqui, e nao a grade maker que o repo ja conhece

Pela economia MEDIDA do instrumento, nao por gosto. Um round-trip custa
R$0,50/contrato de tarifa (`FUTURES_FEE_ROUND_TRIP_BRL`) mais a slippage de
1 tick por perna a mercado. No WIN o tick vale 5 pontos (R$1,00/contrato),
entao:

| | custo de 1 round-trip | em ticks do WIN |
|---|---|---|
| tarifa | 2,5 pontos | 0,50 tick |
| entrada a mercado (taker) | 5 pontos | 1,00 tick |
| saida no alvo (ordem parada, maker) | 0 | 0 |
| **total** | **7,5 pontos** | **1,5 tick** |

Um alvo de 1 tick (5 pontos) NASCE negativo. E' o oposto do WDO, onde a
mesma tarifa e' um decimo de tick e o giro alto se paga -- foi essa
economia que motivou uma grade maker de muitos trades pequenos para WDO@
(`CopaWdo`), mas a tentativa zerou a conta sob capital real de day trade e
foi removida em 2026-08-27; WDO@ hoje nao tem estrategia propria nesta
familia.
Dai o desenho: no WIN o robo precisa de POUCOS trades GRANDES, cada um
pagando 1,5 tick de pedagio para tentar capturar dezenas de ticks. Foi essa
assimetria que fechou a decisao do dono de nao ter uma estrategia so' para os
dois ativos.

Calibra o alvo pela VOLATILIDADE recente do proprio pregao, nao por um numero
fixo de pontos: o range diario mediano do WIN e' 2.968 pontos, mas o intervalo
p25–p75 vai de 2.296 a 4.054 (182 pregoes medidos) — um alvo fixo seria
grande demais em metade dos dias e pequeno demais na outra.

## Tudo reinicia no pregao

Nenhum indicador de NIVEL de preco atravessa a virada: a faixa, a
volatilidade, o stop e o alvo saem exclusivamente das barras de HOJE. Nao e'
zelo — a serie continua (`WIN@`) tem emenda de rolagem, e o salto de preco
dela (+742, +786, +630, +510 pontos nos 4 dias de rolagem medidos) se esconde
DENTRO do ruido overnight normal (mediano 499, p95 1.746), ou seja, e'
indetectavel por outlier. A unica defesa estrutural e' nunca deixar um nivel
de preco cruzar a sessao.

## O teto de contratos e' ENTRADA, nunca constante

`teto_contratos` e' obrigatorio no construtor e TODO tamanho e' fracao dele
(`_qtd`). Os numeros de 2025 (WIN 15) podem mudar antes de 14/09/2026; um
literal aqui viraria um robo que so' sabe operar as regras do ano passado.

## Realocacao dinamica por CAPITAL (2026-08-27, ADITIVA e OPT-IN)

`teto_contratos` continua sendo o teto OFICIAL da competicao -- ele NUNCA
muda de significado. O que passou a existir e' um segundo teto, o que o
CAIXA REAL do dono sustenta agora (`contracts_from_capital`, `strategy.
daytrade.base`), e a entrada usa o MENOR dos dois. Por default
(`margin_per_contract_brl=None`) este segundo teto nao existe e o
comportamento e' byte-a-byte o de antes: so' quem passa `margin_per_
contract_brl` explicito ativa a realocacao (mesma convencao aditiva de
`config_for`/`contracts_from_capital`).

Por que nao reaproveitar `teto_contratos` para isto: ele e' o teto da
COMPETICAO (pode ser MAIOR do que o capital atual sustenta -- o robo
comeca com R$200 e o teto oficial e' 15 contratos), enquanto o teto por
capital so' pode ENCOLHER a entrada, nunca cresce-la acima do que a
competicao permite. Um caixa que crescesse o suficiente para sustentar
mais contratos do que `teto_contratos` nao deve fazer o robo violar o
regulamento -- e' por isso que a formula e' `min(teto_contratos,
contracts_from_capital(...))`, nunca so' o segundo termo.

`on_capital_update` segue o MESMO padrao ja usado por `Gremah`
(`_cash_atual_brl`, atualizado pelo motor logo antes de cada `on_bar`,
comeca em 0.0): enquanto o motor nunca chamou o hook (replay de
`warm_start_calibration`, ou a primeira barra do backtest), o robo nao
"sabe" quanto caixa tem -- e o piso de 1 contrato ja existente
(`max(1, round(...))`) cobre esse caso sem precisar de um segundo estado.
"""
from __future__ import annotations

from collections import deque

import pandas as pd

from strategy.daytrade.base import (
    MARGIN_BUFFER_FUTUROS,
    AdjustStop,
    Bar,
    Enter,
    EnterLimit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    contracts_from_capital,
    no_tick,
)


class CopaWin(IntradayStrategy):
    """Rompimento de faixa rolante intradiaria, com alvo e stop escalados
    pela volatilidade do proprio pregao e stop que so' aperta.

    Uma posicao por vez (o motor recusa `Enter` com posicao aberta), com
    tamanho igual a uma FRACAO do teto de contratos da competicao."""

    name = "copa_win"
    version = "0.1"
    symbol = "WIN@"
    is_futuro = True
    # A saida por alvo e' ordem PARADA no nivel (maker, sem slippage); a
    # entrada e' a mercado de proposito -- nao existe ordem-limite que compre
    # um rompimento PARA CIMA (uma compra parada acima do preco viraria
    # execucao imediata; uma abaixo espera o preco VOLTAR, que e' o sinal
    # oposto). O robo paga 1 tick para entrar e nao paga nada para sair no
    # alvo: e' a assimetria honesta deste desenho, nao um favor do motor.
    target_fills_as_maker = True
    feed_kind = "m1"
    #: Pernas MAKER por round-trip -- 1 com entrada a mercado (so' o alvo e'
    #: ordem parada), 2 com `entrada_maker=True`. Multiplicador do portao G7
    #: (pedagio de 1 tick em todo fill maker): um backtest em barra M1 nao
    #: enxerga POSICAO NA FILA, entao assume que a ordem parada preencheu
    #: sempre que o preco tocou o nivel. Se o edge morre com 1 tick de
    #: pedagio, ele era ficcao de fila. Vira atributo de INSTANCIA no
    #: `__init__`, porque depende de `entrada_maker`.
    pernas_maker = 1

    def __init__(
        self,
        teto_contratos: int,
        symbol: str = "WIN@",
        tick_size: float = 5.0,
        point_value_brl: float = 0.20,
        fracao_entrada: float = 0.5,
        janela_rompimento: int = 20,
        alvo_vol: float = 2.0,
        stop_vol: float = 1.0,
        vol_min_ticks: float = 2.0,
        trail_vol: float | None = 1.0,
        aquecimento_barras: int = 15,
        max_entradas_dia: int = 10,
        entrada_maker: bool = False,
        entrada_ttl_barras: int = 5,
        perda_max_dia_pontos: float | None = None,
        margin_per_contract_brl: float | None = None,
        margin_buffer: float = MARGIN_BUFFER_FUTUROS,
    ):
        """`teto_contratos`: teto de contratos SIMULTANEOS da competicao.
        Obrigatorio e sem default -- e' o unico limitador de tamanho num
        ambiente de margem infinita, e herdar um numero em silencio aqui seria
        o mesmo erro que `Gremah` evita ao recusar simbolo sem calibracao.

        `fracao_entrada`: tamanho da posicao como fracao do teto. `0.5` com
        teto 12 = 6 contratos; com teto 15 = 8. O robo NUNCA le 12 nem 15.

        `janela_rompimento`: barras M1 da faixa rolante. Tambem e' a janela da
        volatilidade de referencia -- uma so', porque as duas medem a mesma
        coisa ("o que este pregao andou nos ultimos N minutos").

        `alvo_vol`/`stop_vol`: alvo e stop em multiplos dessa volatilidade.

        `vol_min_ticks`: nao opera enquanto a volatilidade de referencia for
        menor que isto (em ticks). Um "rompimento" de faixa achatada e'
        quantizacao do tick, nao sinal -- mesmo motivo do `min_range_price` da
        `OpeningRangeBreakout`, so' que medido em volatilidade em vez de range
        absoluto.

        `trail_vol`: aperta o stop para `trail_vol` volatilidades atras do
        preco corrente, uma vez que o trade esteja a favor. `None` desliga.
        O motor so' aceita stop MAIS protetor (`AdjustStop`), entao isto nunca
        afrouxa nada.

        `aquecimento_barras`: barras da abertura sem operar. A abertura do WIN
        concentra o leilao e o repique dele; entrar em cima disso e' apostar
        no ruido de formacao de preco.

        `max_entradas_dia`: teto de entradas por pregao -- limita quantas
        vezes o pedagio de 1,5 tick e' pago num dia sem sinal bom.

        `entrada_maker`: entra por RETESTE em vez de perseguir o rompimento.
        Rompeu para cima, deixa uma compra PARADA no nivel rompido (o teto da
        faixa) e espera o preco voltar nele. Existe por medicao (2026-08-25):
        com entrada a mercado o custo por round-trip no WIN e' ~10,4 pontos
        por contrato contra ~10,6 pontos de edge BRUTO -- praticamente todo o
        ganho vai embora no spread da entrada, e a ordem parada nao paga esse
        tick. O preco disso e' real e nao e' estimavel a priori: o rompimento
        que nunca retesta simplesmente nao e' operado, e o que retesta pode
        ser justamente o rompimento fraco. E' hipotese a MEDIR, por isso e'
        parametro e nao o desenho.

        `entrada_ttl_barras`: barras que a ordem de reteste espera antes de o
        motor cancela-la. O robo so' re-arma depois do prazo, sincronizado com
        o motor -- re-armar a cada barra substituiria a propria ordem e o
        prazo nunca se cumpriria.

        `perda_max_dia_pontos`: perda-limite do pregao, em pontos por
        contrato do teto (`pontos x point_value x teto`). `None` (default)
        desliga: a funcao objetivo e' lucro total, e um freio diario e' uma
        hipotese a MEDIR na varredura, nao uma premissa.

        `margin_per_contract_brl`: ATIVA a realocacao dinamica por capital
        (ver a secao do modulo). `None` (default) -- comportamento IDENTICO
        ao de antes desta rodada: `quantidade_por_entrada` so' olha
        `teto_contratos x fracao_entrada`, nunca o caixa. Setado, o teto
        efetivo de contratos passa a ser `min(teto_contratos,
        contracts_from_capital(caixa_atual, margin_per_contract_brl,
        margin_buffer))` -- o caixa real NUNCA deixa a entrada ultrapassar o
        teto oficial da competicao, so' pode encolhe-la abaixo dele.

        `margin_buffer`: multiplicador de seguranca sobre a margem por
        contrato, mesmo parametro/mesmo default de `contracts_from_capital`
        (`MARGIN_BUFFER_FUTUROS=2.0`) -- so' importa quando
        `margin_per_contract_brl` esta setado."""
        if teto_contratos < 1:
            raise ValueError(
                f"copa_win: `teto_contratos` tem de ser >= 1, veio {teto_contratos!r}. "
                "O teto e' entrada de configuracao (as regras da Copa podem mudar "
                "antes de 14/09/2026), nunca constante no codigo."
            )
        self.symbol = symbol
        self.teto_contratos = int(teto_contratos)
        self.tick_size = float(tick_size)
        self.point_value_brl = float(point_value_brl)
        self.fracao_entrada = float(fracao_entrada)
        self.janela_rompimento = int(janela_rompimento)
        self.alvo_vol = float(alvo_vol)
        self.stop_vol = float(stop_vol)
        self.vol_min_ticks = float(vol_min_ticks)
        self.trail_vol = None if trail_vol is None else float(trail_vol)
        self.aquecimento_barras = int(aquecimento_barras)
        self.max_entradas_dia = int(max_entradas_dia)
        self.entrada_maker = bool(entrada_maker)
        self.entrada_ttl_barras = int(entrada_ttl_barras)
        self.perda_max_dia_pontos = perda_max_dia_pontos
        self.margin_per_contract_brl = (
            None if margin_per_contract_brl is None else float(margin_per_contract_brl)
        )
        self.margin_buffer = float(margin_buffer)
        # A entrada parada e' a SEGUNDA perna maker (a primeira e' o alvo) --
        # ver o comentario do atributo de classe.
        self.pernas_maker = 2 if self.entrada_maker else 1

        # Atualizado por `on_capital_update`, chamado pelo motor logo antes
        # de cada `on_bar` -- 0.0 so' antes da primeira barra real (warm
        # start via replay nunca chama `on_capital_update`; mesmo padrao de
        # `Gremah._cash_atual_brl`). So' importa quando
        # `margin_per_contract_brl` esta setado.
        self._cash_atual_brl = 0.0

        self._faixa: deque[Bar] = deque(maxlen=self.janela_rompimento)
        self._barras_hoje = 0
        self._entradas_hoje = 0
        self._encerrado_hoje = False
        # Barras desde que a ordem de reteste foi armada; `None` = nenhuma em
        # pe'. Espelha `IntradaySessionMachine.resting_limit_bars_waited` de
        # fora.
        self._espera: int | None = None

    # ---------- tamanho: sempre fracao do teto ----------------------------

    @property
    def quantidade_por_entrada(self) -> int:
        """`max(1, round(teto_efetivo x fracao))` -- piso de 1 contrato
        porque uma entrada de zero contratos nao e' "menor", e' nenhuma.

        `teto_efetivo` e' `teto_contratos` (comportamento de sempre) quando
        `margin_per_contract_brl` e' `None`. Setado, vira `min(teto_
        contratos, contracts_from_capital(caixa_atual, margin_per_
        contract_brl, margin_buffer))` -- o caixa real do robo so' pode
        ENCOLHER a entrada abaixo do teto oficial da competicao, nunca
        cresce-la acima dele (ver a secao do modulo)."""
        teto_efetivo = self.teto_contratos
        if self.margin_per_contract_brl is not None:
            teto_por_caixa = contracts_from_capital(
                self._cash_atual_brl, self.margin_per_contract_brl, self.margin_buffer,
            )
            teto_efetivo = min(self.teto_contratos, teto_por_caixa)
        return max(1, round(teto_efetivo * self.fracao_entrada))

    def on_capital_update(self, cash_brl: float) -> None:
        """Guarda o caixa acumulado (`config.initial_capital + machine.
        realized_pnl`, ver `IntradayStrategy.on_capital_update`) para
        `quantidade_por_entrada` usar na proxima entrada -- so' tem efeito
        quando `margin_per_contract_brl` esta setado."""
        self._cash_atual_brl = cash_brl

    @property
    def perda_max_dia_brl(self) -> float | None:
        if self.perda_max_dia_pontos is None:
            return None
        return abs(self.perda_max_dia_pontos) * self.point_value_brl * self.teto_contratos

    # ---------- ciclo do pregao -------------------------------------------

    def on_session_start(self, session_date) -> None:
        """Zera TUDO. E' aqui que a regra "nenhum nivel de preco atravessa a
        virada" vira codigo: a faixa do pregao anterior nao sobrevive, entao a
        emenda de rolagem da serie continua nunca entra num nivel."""
        self._faixa = deque(maxlen=self.janela_rompimento)
        self._barras_hoje = 0
        self._entradas_hoje = 0
        self._encerrado_hoje = False
        self._espera = None

    # ---------- decisao ----------------------------------------------------

    def _volatilidade(self) -> float:
        """Amplitude MEDIA das barras da faixa. Media (nao mediana) de
        proposito: aqui a barra grande isolada e' informacao, nao ruido a
        descartar -- e' ela que diz que o alvo precisa ser maior agora."""
        if not self._faixa:
            return 0.0
        return sum(b.high - b.low for b in self._faixa) / len(self._faixa)

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._barras_hoje += 1
        acoes: list[IntradayAction] = []
        faixa_pronta = len(self._faixa) == self.janela_rompimento
        vol = self._volatilidade()

        try:
            if self._encerrado_hoje:
                return acoes

            limite = self.perda_max_dia_brl
            if limite is not None and session_pnl_brl <= -limite:
                # Encerra o dia. Nao emite `Exit`: quem esta comprado tem stop
                # proprio, e um `Exit` a mercado aqui pagaria slippage para
                # fechar uma posicao que pode estar a caminho do alvo. O freio
                # e' sobre ABRIR de novo.
                self._encerrado_hoje = True
                return acoes

            if positions:
                self._espera = None
                acoes.extend(self._trailing(positions, bar, vol))
                return acoes

            if self._espera is not None:
                # Ordem de reteste ainda viva no motor -- substitui-la agora
                # zeraria o prazo dela a cada barra.
                self._espera += 1
                if self._espera < self.entrada_ttl_barras:
                    return acoes
                self._espera = None

            if not faixa_pronta or self._barras_hoje <= self.aquecimento_barras:
                return acoes
            if self._entradas_hoje >= self.max_entradas_dia:
                return acoes
            if vol < self.vol_min_ticks * self.tick_size:
                return acoes

            teto_faixa = max(b.high for b in self._faixa)
            piso_faixa = min(b.low for b in self._faixa)
            if bar.close > teto_faixa:
                acoes.append(self._entrada("long", bar.close, teto_faixa, vol))
            elif bar.close < piso_faixa:
                acoes.append(self._entrada("short", bar.close, piso_faixa, vol))
            return acoes
        finally:
            # SEMPRE no fim, e depois de a decisao ja ter sido tomada: a barra
            # corrente nao pode fazer parte da faixa contra a qual ela propria
            # e' comparada (seria comparar o preco com ele mesmo, e nenhum
            # rompimento existiria).
            self._faixa.append(bar)

    def _entrada(self, lado: str, preco: float, nivel_rompido: float,
                 vol: float) -> Enter | EnterLimit:
        """`preco` e' o fechamento que rompeu; `nivel_rompido` e' a borda da
        faixa. A mercado, o robo entra no fechamento; por reteste, espera
        parado na borda -- e stop/alvo saem sempre do preco em que ele
        REALMENTE entraria, nunca de um preco de referencia diferente."""
        self._entradas_hoje += 1
        base = nivel_rompido if self.entrada_maker else preco
        alvo_dist = self.alvo_vol * vol
        stop_dist = self.stop_vol * vol
        if lado == "long":
            stop = no_tick(base - stop_dist, self.tick_size)
            alvo = no_tick(base + alvo_dist, self.tick_size)
        else:
            stop = no_tick(base + stop_dist, self.tick_size)
            alvo = no_tick(base - alvo_dist, self.tick_size)
        side = "long" if lado == "long" else "short"
        metadata = {"vol_ref": vol, "entrada_n": self._entradas_hoje,
                    "nivel_rompido": nivel_rompido}
        if not self.entrada_maker:
            return Enter(side=side, quantity=self.quantidade_por_entrada,
                         initial_stop=stop, initial_target=alvo,
                         metadata=metadata, reason=f"rompimento_{lado}")
        self._espera = 0
        return EnterLimit(
            side=side,
            limit_price=no_tick(base, self.tick_size),
            quantity=self.quantidade_por_entrada,
            initial_stop=stop,
            initial_target=alvo,
            ttl_bars=self.entrada_ttl_barras,
            metadata=metadata,
            reason=f"reteste_{lado}",
        )

    def _trailing(self, positions: list[IntradayOpenPosition], bar: Bar,
                  vol: float) -> list[IntradayAction]:
        """Stop arrastado a `trail_vol` volatilidades do preco corrente.

        Nao devolve nada se o novo nivel nao for mais protetor que o atual --
        o motor recusaria de qualquer forma (`AdjustStop` so' aperta), e
        emitir a acao mesmo assim encheria o diario de ruido."""
        if self.trail_vol is None or vol <= 0:
            return []
        acoes: list[IntradayAction] = []
        for pos in positions:
            if pos.side == "long":
                novo = no_tick(bar.close - self.trail_vol * vol, self.tick_size)
                if pos.current_stop is None or novo > pos.current_stop:
                    acoes.append(AdjustStop(new_stop=novo))
            else:
                novo = no_tick(bar.close + self.trail_vol * vol, self.tick_size)
                if pos.current_stop is None or novo < pos.current_stop:
                    acoes.append(AdjustStop(new_stop=novo))
            break  # uma posicao por vez neste desenho; o motor aplica a todas
        return acoes
