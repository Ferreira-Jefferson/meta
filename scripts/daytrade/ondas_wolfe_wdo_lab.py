"""EXPERIMENTO (nao produzao) -- Ondas de Wolfe no WDO@, desenho de execucao
FECHADO, testado sobre uma janela GRANDE (nao as 2 celulas efetivas de
2026-09-10, ver `setups_publicos_rodada_refutada_2026_09_10` na memoria do
projeto).

## Por que este arquivo existe e o que ele NAO e'

Este NAO e' `strategy/daytrade/lab/*` -- de proposito. E' hipotese em
validacao, nao candidato promovido; fica em `scripts/daytrade/` ate' (e SE)
ganhar o direito de virar estrategia de producao. Nao mexe em
`strategy/daytrade/registry.py`.

## Divergencia importante com a premissa do pedido

O pedido descreve a rodada de 2026-09-10 como tendo usado "geometria
identica... alvo por limite real fatiada sem prazo, ancorada no fill" --
ou seja, ja o desenho FECHADO. Isso NAO bate com o registro do projeto:
`LICOES_DE_PRODUCAO.md` item 4.24 e a memoria `setups_publicos_rodada_
refutada_2026_09_10` dizem, sem ambiguidade, que TODOS os cinco setups
daquela rodada -- Ondas de Wolfe inclusive -- foram medidos com `Enter`
(entrada A MERCADO) e `target_fills_as_maker=False` (alvo a mercado). O
item 6.23 (breakeven empirico) descreve a MESMA familia de teste (Wolfe,
T4/S16) citando "o gap entre o fechamento do sinal e a abertura do fill",
que e' a assinatura de execucao a mercado na barra seguinte, nao de
ordem-limite.

Ou seja: o desenho fechado (`EnterLimit`, alvo fatiado sem prazo, stop a
mercado, `anchor_exits_at_fill=True`) NUNCA foi testado nas Ondas de Wolfe
antes deste script. A diferenca real desta rodada nao e' so' a AMOSTRA (n
grande) -- e' tambem o MECANISMO de execucao, que passa a ser o mesmo
desenho fechado que rege todo o resto do projeto desde a ordem do dono de
2026-09-10. Isso e' relatado explicitamente no resultado final, porque
contradiz a premissa como o pedido descreveu a rodada anterior.

## O mecanismo (zigzag + estrutura de 5 pontos)

Zigzag causal (sem look-ahead: um pivo so' e' confirmado quando o preco
reverte `zigzag_reversal_ticks` alem do extremo -- e' o mesmo tipo de
confirmacao atrasada que o item 6.24 pede para auditar com um oraculo,
ver o rodape deste arquivo) sobre barras M1 CONSTRUIDAS a partir do feed de
TICK (agregacao interna -- o motor continua recebendo tick a tick, que e'
o que a calibracao de fila de `fidelidade.py` exige).

Onda de alta (reversao para CIMA): pivos 1-3-5 sao MINIMAS, 2-4 sao
MAXIMAS. Condicao de exaustao (pedida no enunciado): a onda 5 NAO alcanca a
extensao da reta 1-3 (a reta que liga os dois minimas anteriores, projetada
no tempo do pivo 5) -- ou seja, o pivo 5 fica ACIMA de onde a reta 1-3
projetaria, sinal de que o movimento de queda perdeu forca. Onda de baixa e'
o espelho (pivos 1-3-5 maximas, exaustao = pivo 5 fica ABAIXO da projecao).

Entrada: `EnterLimit` no ROMPIMENTO da reta 1-4 (a reta que liga o pivo 1 ao
pivo 4 -- a "linha de gatilho" classica de Wolfe), com o MESMO offset de
pullback que a ORB usa (`offset_ticks`, ver `wdo_orb.py`) -- a ordem fica
`offset_ticks` ATRAS do fechamento que confirmou o rompimento, esperando um
recuo, nunca perseguindo a mercado.

Alvo: NAO e' a reta de projecao classica de Wolfe (2-4/EPA) -- simplificado
para `alvo_multiplo x stop`, mesma convencao de `wdo_orb.alvo_multiplo`,
para manter a geometria comparavel ao resto do projeto e testavel sem
reimplementar projecao geometrica de reta adicional. Isso e' uma
SIMPLIFICACAO deliberada da regra classica de Wolfe (que usa a reta 2-4
como alvo), registrada aqui para quem for comparar com literatura externa.

Stop: alem do extremo do pivo 5 (que e' o nivel que precisa segurar para a
tese de exaustao ser valida), clampado em [stop_min_ticks, stop_max_ticks]
-- mesmo padrao de clamp do `wdo_orb` (a faixa de abertura tambem e'
clampada) para nao deixar nem stop de 1 tick nem stop de centenas de ticks
passar sem controle.

## O DESENHO DE EXECUCAO (identico ao `wdo_orb`, ordem do dono 2026-09-10)

  * entrada por `EnterLimit` parada no livro, nunca `Enter` a mercado;
  * `entrada_ttl_bars` (em TICKS -- feed_kind="tick", CLAUDE.md: base mede
    ~336 barras/minuto, NAO traduza sem calibrar -- o atraso REALIZADO em
    minutos e' medido e reportado pelo script de execucao, nao aqui);
  * alvo por ordem-limite real fatiada (`exit_split_unit=1`), SEM prazo
    (`EXIT_TTL_BARS_SEM_PRAZO`, nunca `None`);
  * `anchor_exits_at_fill=True`: stop e alvo ancoram no preco REALMENTE
    obtido;
  * stop a MERCADO -- excecao unica.

## O que NAO esta' medido aqui (limitacoes declaradas)

- O alvo classico de Wolfe (reta 2-4) nao foi implementado -- ver acima.
- Sem controle-oraculo (item 6.24) nesta primeira passada -- se o resultado
  sobreviver ao teste pequeno E ao IS completo, RODAR o oraculo (marcar os
  pivos na barra do evento, sem esperar a confirmacao do zigzag) antes de
  tratar qualquer numero como decisao, porque pivo de zigzag e' exatamente
  a familia de sinal que o item 6.24 pede para conferir.
- Sem teto de ondas por pregao (ao contrario do `wdo_orb`, que capa fades):
  decisao deliberada para nao morrer de amostra pequena na 1a passada -- se
  sobreviver, o teto por pregao e' o proximo eixo a varrer, nao um default
  silencioso.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayOpenPosition, IntradayStrategy,
)

#: Mesma constante/mesmo motivo de `wdo_orb.EXIT_TTL_BARS_SEM_PRAZO`: a
#: limite do alvo fica parada ate' o mercado pagar, nunca sai a mercado por
#: impaciencia. NUNCA `None` (`None` no motor = "sem fatia com prazo", e em
#: execucao REAL isso levanta `NotImplementedError`).
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


# ---------------------------------------------------------------------------
# Zigzag causal, puro -- sem pandas/estado externo, testavel isoladamente.
# ---------------------------------------------------------------------------

@dataclass
class Pivo:
    ts: pd.Timestamp
    preco: float
    tipo: str  # "alta" (maxima) ou "baixa" (minima)


class ZigzagCausal:
    """Zigzag classico, CONFIRMADO com atraso (sem look-ahead): um pivo so'
    entra na lista quando o preco ja reverteu `reversal` alem do extremo --
    o mesmo pivo, no instante em que de fato ocorreu, nao era conhecido
    como pivo ainda. Alimentado barra a barra (`update`), nunca com o
    dataframe inteiro de uma vez."""

    def __init__(self, reversal: float):
        self.reversal = reversal
        self.pivos: list[Pivo] = []
        self._direcao: str | None = None  # "alta" = procurando maxima; "baixa" = procurando minima
        self._extremo_preco: float | None = None
        self._extremo_ts: pd.Timestamp | None = None
        # fase de inicializacao: ainda nao sabemos a direcao do primeiro pivo
        self._hi0: float | None = None
        self._hi0_ts: pd.Timestamp | None = None
        self._lo0: float | None = None
        self._lo0_ts: pd.Timestamp | None = None

    def reset(self) -> None:
        self.pivos.clear()
        self._direcao = None
        self._extremo_preco = None
        self._extremo_ts = None
        self._hi0 = self._hi0_ts = self._lo0 = self._lo0_ts = None

    def update(self, ts: pd.Timestamp, high: float, low: float) -> Pivo | None:
        """Barra M1 fechada. Devolve o pivo recem-CONFIRMADO nesta barra, se
        houver (no maximo um por barra, pelo desenho do algoritmo)."""
        if self._direcao is None:
            if self._hi0 is None or high > self._hi0:
                self._hi0, self._hi0_ts = high, ts
            if self._lo0 is None or low < self._lo0:
                self._lo0, self._lo0_ts = low, ts
            if (self._hi0 - self._lo0) >= self.reversal:
                if self._hi0_ts <= self._lo0_ts:
                    pivo = Pivo(self._hi0_ts, self._hi0, "alta")
                    self._direcao = "baixa"
                    self._extremo_preco, self._extremo_ts = self._lo0, self._lo0_ts
                else:
                    pivo = Pivo(self._lo0_ts, self._lo0, "baixa")
                    self._direcao = "alta"
                    self._extremo_preco, self._extremo_ts = self._hi0, self._hi0_ts
                self.pivos.append(pivo)
                return pivo
            return None

        if self._direcao == "alta":  # ultimo pivo foi minima; procurando maxima
            if high > self._extremo_preco:
                self._extremo_preco, self._extremo_ts = high, ts
                return None
            if (self._extremo_preco - low) >= self.reversal:
                pivo = Pivo(self._extremo_ts, self._extremo_preco, "alta")
                self.pivos.append(pivo)
                self._direcao = "baixa"
                self._extremo_preco, self._extremo_ts = low, ts
                return pivo
            return None

        # self._direcao == "baixa": ultimo pivo foi maxima; procurando minima
        if low < self._extremo_preco:
            self._extremo_preco, self._extremo_ts = low, ts
            return None
        if (high - self._extremo_preco) >= self.reversal:
            pivo = Pivo(self._extremo_ts, self._extremo_preco, "baixa")
            self.pivos.append(pivo)
            self._direcao = "alta"
            self._extremo_preco, self._extremo_ts = high, ts
            return pivo
        return None


def _valor_na_reta(p_ini: Pivo, p_fim: Pivo, ts: pd.Timestamp) -> float:
    """Valor da reta que liga `p_ini` a `p_fim`, projetada (ou interpolada)
    no instante `ts`. Reta degenerada (mesmos timestamps) devolve o preco
    do ponto final -- nunca ocorre na pratica (pivos alternados tem
    timestamps estritamente crescentes), guarda so' contra ZeroDivision."""
    dt_total = (p_fim.ts - p_ini.ts).total_seconds()
    if dt_total <= 0:
        return p_fim.preco
    inclinacao = (p_fim.preco - p_ini.preco) / dt_total
    return p_ini.preco + inclinacao * (ts - p_ini.ts).total_seconds()


@dataclass
class OndaWolfe:
    p1: Pivo
    p2: Pivo
    p3: Pivo
    p4: Pivo
    p5: Pivo
    direcao: str  # "long" (reversao de baixa pra alta) ou "short"


def detectar_onda(pivos: list[Pivo]) -> OndaWolfe | None:
    """Os ULTIMOS 5 pivos de `pivos` formam uma Onda de Wolfe valida?
    Exige alternancia estrita (1-3-5 do mesmo tipo, 2-4 do outro) e a
    condicao de exaustao (onda 5 nao alcanca a extensao da reta 1-3)."""
    if len(pivos) < 5:
        return None
    p1, p2, p3, p4, p5 = pivos[-5:]
    tipos = (p1.tipo, p2.tipo, p3.tipo, p4.tipo, p5.tipo)
    if tipos == ("baixa", "alta", "baixa", "alta", "baixa"):
        # reversao de BAIXA para ALTA: 1-3-5 minimas, exaustao = p5 ACIMA
        # da projecao da reta 1-3 (nao conseguiu fazer minima proporcional).
        projecao = _valor_na_reta(p1, p3, p5.ts)
        if p5.preco > projecao:
            return OndaWolfe(p1, p2, p3, p4, p5, "long")
        return None
    if tipos == ("alta", "baixa", "alta", "baixa", "alta"):
        # reversao de ALTA para BAIXA: espelho.
        projecao = _valor_na_reta(p1, p3, p5.ts)
        if p5.preco < projecao:
            return OndaWolfe(p1, p2, p3, p4, p5, "short")
        return None
    return None


# ---------------------------------------------------------------------------
# Estrategia (IntradayStrategy) -- agrega tick -> M1 internamente, decide em
# cima do M1, executa no feed de TICK (fidelidade calibrada).
# ---------------------------------------------------------------------------

@dataclass
class OndasWolfeWdo(IntradayStrategy):
    """EXPERIMENTO -- nao e' robo de producao. Ver docstring do modulo."""

    name: str = "ondas_wolfe_wdo_lab"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    feed_kind: str = "tick"
    is_futuro: bool = True

    tick_size: float = 0.5
    #: limiar de reversao do zigzag, em TICKS. Ver a nota de calibracao no
    #: topo do modulo (range diario mediano do WDO@ e' 49,3 pontos = 98,6
    #: ticks -- este limiar precisa ser bem menor que isso para formar 5
    #: pivos dentro de 1 pregao).
    zigzag_reversal_ticks: float = 24.0
    #: mesma convencao do `wdo_orb`: ordem fica ATRAS do rompimento,
    #: esperando um recuo, nunca perseguindo a mercado.
    offset_ticks: int = 2
    stop_min_ticks: int = 10
    stop_max_ticks: int = 60
    alvo_multiplo: float = 2.0
    quantity: int = 1
    #: prazo da ordem de ENTRADA, em TICKS (feed_kind="tick" -- CLAUDE.md:
    #: nao e' tempo, calibre/relate o atraso REALIZADO em minutos).
    entrada_ttl_bars: int | None = 3000

    _cur_min_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _cur_o: float = field(default=0.0, init=False, repr=False)
    _cur_h: float = field(default=0.0, init=False, repr=False)
    _cur_l: float = field(default=0.0, init=False, repr=False)
    _cur_c: float = field(default=0.0, init=False, repr=False)
    _zz: ZigzagCausal = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _onda: OndaWolfe | None = field(default=None, init=False, repr=False)
    _trigger_side: str | None = field(default=None, init=False, repr=False)
    _trigger_preco: float | None = field(default=None, init=False, repr=False)
    _armado: bool = field(default=False, init=False, repr=False)
    _tinha_posicao: bool = field(default=False, init=False, repr=False)
    #: diagnostico -- quantas ondas validas foram detectadas no pregao
    #: (usadas ou nao), para conferir se o mecanismo dispara na base real.
    ondas_detectadas_no_dia: int = field(default=0, init=False, repr=False)

    def on_session_start(self, session_date) -> None:
        self._cur_min_ts = None
        self._zz = ZigzagCausal(self.zigzag_reversal_ticks * self.tick_size)
        self._onda = None
        self._trigger_side = None
        self._trigger_preco = None
        self._armado = False
        self._tinha_posicao = False
        self.ondas_detectadas_no_dia = 0

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._armado = False
        self._onda = None
        self._trigger_side = None
        self._trigger_preco = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        # mesma logica de `on_order_rejected` -- ver a nota do wdo_orb sobre
        # o robo ficar CEGO sem este aviso. Aqui tambem descartamos a onda:
        # se o rompimento nao foi capturado dentro do prazo, a validade da
        # tese de exaustao ja e' outra (o preco teve tempo de se mover mais).
        self._armado = False
        self._onda = None
        self._trigger_side = None
        self._trigger_preco = None

    def _fecha_m1(self, m1_ts: pd.Timestamp) -> None:
        pivo = self._zz.update(m1_ts, self._cur_h, self._cur_l)
        if pivo is not None:
            # invalida a onda corrente se um NOVO pivo do MESMO tipo do
            # pivo 5 aparecer alem dele, na direcao da exaustao -- a tese
            # "onda 5 nao alcancou a extensao 1-3" deixa de valer se a onda
            # continuou.
            if self._onda is not None and pivo.tipo == self._onda.p5.tipo:
                if self._onda.direcao == "long" and pivo.preco < self._onda.p5.preco:
                    self._onda = None
                elif self._onda.direcao == "short" and pivo.preco > self._onda.p5.preco:
                    self._onda = None
            if self._onda is None:
                candidata = detectar_onda(self._zz.pivos)
                if candidata is not None:
                    self._onda = candidata
                    self.ondas_detectadas_no_dia += 1
                    self._trigger_side = None
                    self._trigger_preco = None

        # rompimento da reta 1-4, avaliado no FECHAMENTO desta M1.
        if self._onda is not None and self._trigger_side is None:
            nivel = _valor_na_reta(self._onda.p1, self._onda.p4, m1_ts)
            if self._onda.direcao == "long" and self._cur_c > nivel:
                self._trigger_side = "long"
                self._trigger_preco = self._cur_c
            elif self._onda.direcao == "short" and self._cur_c < nivel:
                self._trigger_side = "short"
                self._trigger_preco = self._cur_c

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list["EnterLimit"]:
        if self.feed_kind == "m1":
            # `bar` JA' e' a M1 fechada -- decide direto, sem agregar tick.
            # Modo mais RAPIDO (usado no teste de amostra grande, ver a
            # docstring do modulo para o custo de fidelidade que isso paga:
            # `queue_ahead_qty`/`exit_queue_ahead_qty` foram calibrados
            # tick-a-tick e aplicar o MESMO numero contra o volume agregado
            # de 1 minuto inteiro e' otimista -- a fila "gasta" pelo volume
            # do minuto todo, nao so' o que aconteceu ate' o toque).
            self._cur_h, self._cur_l, self._cur_c = bar.high, bar.low, bar.close
            self._fecha_m1(ts)
        else:
            minuto = ts.floor("1min")
            if self._cur_min_ts is None:
                self._cur_min_ts = minuto
                self._cur_o = self._cur_h = self._cur_l = self._cur_c = bar.close
            elif minuto != self._cur_min_ts:
                self._fecha_m1(self._cur_min_ts)
                self._cur_min_ts = minuto
                self._cur_o = self._cur_h = self._cur_l = self._cur_c = bar.close
            else:
                self._cur_h = max(self._cur_h, bar.close)
                self._cur_l = min(self._cur_l, bar.close)
                self._cur_c = bar.close

        # transicao "tinha posicao, agora nao tem" -- posicao fechou (stop,
        # alvo ou flatten): libera a busca por uma onda nova.
        if self._tinha_posicao and not positions:
            self._tinha_posicao = False
            self._armado = False
            self._onda = None
            self._trigger_side = None
            self._trigger_preco = None
        if positions:
            self._tinha_posicao = True
            return []

        if self._armado:
            return []
        if self._trigger_side is None or self._trigger_preco is None:
            return []

        sinal = 1.0 if self._trigger_side == "long" else -1.0
        off = self.offset_ticks * self.tick_size
        limite = self._trigger_preco - sinal * off

        dist_ticks = abs(limite - self._onda.p5.preco) / self.tick_size
        stop_ticks = max(self.stop_min_ticks, min(self.stop_max_ticks, round(dist_ticks)))
        alvo_ticks = round(stop_ticks * self.alvo_multiplo)

        self._armado = True
        return [EnterLimit(
            side=self._trigger_side,
            limit_price=limite,
            initial_stop=limite - sinal * stop_ticks * self.tick_size,
            initial_target=limite + sinal * alvo_ticks * self.tick_size,
            quantity=self.quantity,
            ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=f"wolfe_{self._trigger_side}",
        )]
