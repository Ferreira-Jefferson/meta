"""ORB (Opening Range Breakout) do WDO@, no desenho de execucao FECHADO.

Rompimento da faixa dos primeiros `range_minutos` do pregao, ATE' DUAS
operacoes por pregao (a original, mais o fade do rompimento oposto -- ver
`fade_rompimento_oposto`), geometria tirada do proprio tamanho da faixa.
Todo o resto e' execucao -- e neste robo a execucao NAO e' detalhe: ela
responde por praticamente todo o resultado.

O numero, medido no IS congelado (72 pregoes, capital real R$375, fila
438/489 de `fidelidade.py`, entrada e alvo por ordem-limite):

    ==================================================================
    desenho                       trades  win%    BE emp   R$/op  liquido
    ------------------------------------------------------------------
    corte de tempo a MERCADO          58  51,72%  45,10%  +15,71  +911,00
    corte por ordem-LIMITE            58  56,90%  48,09%  +21,31  +1.236,00
    + aviso de ordem morta por prazo  72  56,94%  47,74%  +22,90  +1.649,00
    ==================================================================

+81% de liquido SEM tocar em um unico parametro de estrategia -- mesma
faixa, mesmo offset, mesmo alvo, mesmo stop. O que mudou foi (1) parar de
fechar a mercado quando o relogio bate e (2) o robo passar a SABER que a
ordem de entrada dele morreu. Ver `saida_limite_minutos` e
`on_order_expired`.

O QUE ESTE ROBO NAO E' (2026-09-10 -- SUPERADO em 2026-09-11, ver abaixo): o
veredito estatistico do robo SEM o fade era INDEFINIDO. Win 56,94% com IC95%
[45,4 ; 67,7] contra breakeven empirico de 47,74% -- o breakeven caia DENTRO
do intervalo.

O FADE DO ROMPIMENTO OPOSTO (2026-09-11, ver `fade_rompimento_oposto`) e' o
que mudou isso. Depois que a operacao do dia fecha, um rompimento da faixa
ORIGINAL para o lado CONTRARIO ao primeiro dispara uma SEGUNDA entrada,
apostando na volta pra dentro da faixa -- dia com dois rompimentos opostos
e' dia indeciso, e dia indeciso volta ao meio. Medido no IS (72 pregoes): o
fade sozinho adiciona 31 operacoes, win 67,74%, R$/op +38,53 -- melhor que o
robo original (+22,90) -- e leva o robo INTEIRO (103 operacoes) a IC95%
[50,5 ; 69,1] contra breakeven 48,58%: **primeira vez que o limite inferior
passa acima do breakeven.** CONFIRMADO no OOS (51 pregoes, teste as cegas,
nunca visto antes de 2026-09-11): as 28 operacoes que o fade adiciona la'
deram win 67,86%, R$/op +34,50, liquido +966,00 -- mesma direcao do IS, sem
nenhum ajuste entre as duas medicoes.

RISCO DE CAPITAL, achado no MESMO teste OOS: a caminhada REAL de caixa (a
sequencia cronologica de fato, nao a simulacao por-dia que reseta o
capital) travou com R$375 logo na 1a semana e meia da janela -- 6 de 79
operacoes chegaram a acontecer, caixa minimo R$117,00, e as outras 73
nunca teriam ocorrido de verdade. So' sobreviveu a janela OOS INTEIRA com
capital de R$500, e mesmo assim tocando um minimo de R$153,50 -- so' R$3,50
acima da margem de R$150. **R$375 (o piso de PARTIDA oficial do WDO@,
CLAUDE.md) nao e' capital suficiente para esta geometria sobreviver ao azar
COMUM, nao so' ao raro.** Ele esta em producao por decisao do dono, com 1
contrato, e o que decide e' o extrato -- nao esta tabela. Ver
LICOES_DE_PRODUCAO.md.

O DESENHO DE EXECUCAO (ordem do dono, 2026-09-10 -- ver CLAUDE.md):

  * entrada por `EnterLimit` PARADA no livro, nunca `Enter` a mercado. Num
    rompimento que nao volta, o trade simplesmente nao acontece: 19,4% dos
    pregoes do IS passam em branco por isso, e essa taxa e' o numero que
    decide se o setup sobrevive ao desenho real;
  * a ordem de entrada TEM prazo (`entrada_ttl_bars`). Sem prazo ela espera
    o pregao inteiro e preenche horas depois do sinal -- medido 269,7 min
    num robo irmao, e os fills atrasados foram os piores resultados;
  * alvo por ordem-limite REAL fatiada (`exit_split_unit=1`), SEM prazo
    (`EXIT_TTL_BARS_SEM_PRAZO`), nunca `tp` nativo -- o nativo e' gatilho
    varrido a mercado e come 57,9% do bruto (n=11, 10 contra 0 a favor);
  * `anchor_exits_at_fill=True`: stop e alvo ancoram no preco REALMENTE
    obtido. Aqui a flag vale de verdade, porque e' lida no caminho de
    preenchimento de `EnterLimit` (era no-op para `Enter`, item 4.23);
  * stop a MERCADO -- excecao unica. Protecao nao espera fila.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    AdjustTarget, Bar, EnterLimit, Exit, IntradayAction,
    IntradayOpenPosition, IntradayStrategy,
)

#: Prazo da fatia de saida por ALVO: sem prazo. NUNCA `None` -- `None` no
#: motor significa "comportamento antigo, sem fatia com prazo", e em execucao
#: REAL `machine._resolve_live_split_exit` levanta `NotImplementedError`.
#: Mesma constante/mesmo motivo de `wdo_grid_reload_maker.EXIT_TTL_BARS_SEM_
#: PRAZO` (ordem do dono, 2026-09-09): a limite do alvo fica parada ate' o
#: mercado PAGAR, e nunca sai a mercado por impaciencia.
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9


@dataclass
class WdoOrb(IntradayStrategy):
    """Rompimento da faixa de abertura do mini-dolar, ate' 2 operacoes por pregao"""

    name: str = "wdo_orb"
    version: str = "1.0.0"
    symbol: str = "WDO@"
    #: o alvo e' ordem-limite REAL parada no livro, nao `tp` nativo.
    target_fills_as_maker: bool = True
    #: vale de verdade aqui: a flag e' lida no caminho de `EnterLimit`.
    anchor_exits_at_fill: bool = True
    #: medido em base de TICK. Ver `entrada_ttl_bars` para o que isso faz com
    #: qualquer parametro contado em BARRAS.
    feed_kind: str = "tick"
    is_futuro: bool = True

    tick_size: float = 0.5
    #: faixa de abertura: os primeiros N minutos do pregao.
    range_minutos: float = 15.0
    #: O stop sai do TAMANHO DA FAIXA (1 tick de faixa = 1 tick de stop),
    #: limitado entre os dois. Distribuicao medida da faixa nos 72 pregoes do
    #: IS, em ticks: p0 13 · p25 23 · p50 35 · p75 42,5 · p95 64,5 · p100 93
    #: -- o piso morde em 13,9% dos pregoes, o teto em 31,9%, e em 54,2% a
    #: faixa passa livre.
    #:
    #: ATENCAO, risco conhecido e NAO mitigado: 40 ticks = R$200,00 de perda
    #: num contrato, e a margem do WDO@ e' R$150,00. Um stop cheio partindo do
    #: caixa de partida (R$375) deixa R$175; DOIS seguidos derrubam o caixa
    #: abaixo da margem e o robo para de operar (janela censurada -- ver
    #: CLAUDE.md, "o piso de capital e' indicacao de PARTIDA"). O maior stop
    #: que NAO consegue fazer isso sozinho e' 30 ticks (R$150 = a margem).
    #: Baixar o teto para 30 muda a estrategia medida, entao e' decisao do
    #: dono, nao default silencioso.
    stop_min_ticks: int = 20
    stop_max_ticks: int = 40
    #: alvo = stop x isto. TESTADO e' 2,0. Geometria FIXA (abaixo) foi testada
    #: e REFUTADA de forma monotonica: S10/T20 deu +R$0,88/op e S20/T40
    #: +R$2,34/op contra +R$15,71/op da faixa adaptativa, na MESMA janela. O
    #: mecanismo: com stop largo o perdedor sai pelo relogio com perda
    #: PEQUENA; com stop apertado o mesmo trade sai no stop CHEIO.
    alvo_multiplo: float = 2.0
    quantity: int = 1

    #: Fecha a posicao a MERCADO N minutos depois da entrada. E' o desenho
    #: ANTIGO -- deixado aqui so' para reproduzir a linha de base da tabela do
    #: topo. Em producao fica `None`: fechar a mercado paga `slippage_ticks`
    #: (1,0t = R$5,00 no WDO@) e esse corte era 67% das saidas do robo.
    exit_minutos: float | None = None
    #: O CORTE DO RELOGIO, versao maker: N minutos depois da entrada, move o
    #: alvo para o preco CORRENTE (`AdjustTarget`) e espera a ordem-limite
    #: preencher, em vez de atravessar o livro. A limite fica NO preco, nao
    #: alem dele -- e' ordem parada de verdade, nao ordem a mercado
    #: disfarcada: arma uma fatia nova e espera a fila daquele nivel.
    #:
    #: Sozinha, esta troca levou o deslize pago de R$265,00 para R$70,00 nos
    #: 72 pregoes e o R$/op de +15,71 para +21,31. De um ganho de +R$5,60/op,
    #: R$3,36 sao mecanicamente o deslize que deixou de ser pago; o resto e'
    #: o preco melhor de quem sai por limite.
    #:
    #: O que se ARRISCA: se a limite nao preencher, a posicao fica aberta ate'
    #: o achatamento de fim de pregao (que volta a ser a mercado). Aos 60 min
    #: a entrada ja' aconteceu entre 09:16 e 09:58 BRT (mediana 09:22), entao
    #: sobra pregao de sobra -- mas e' exposicao que o corte a mercado nao
    #: tinha.
    saida_limite_minutos: float | None = 60.0

    #: 0 = limite NO nivel do rompimento; N = N ticks ATRAS (esperando
    #: pullback). Mais offset = preco melhor para quem preenche e mais pregao
    #: em branco. Medido no IS: 2t deixa 19,4% dos pregoes sem trade e da'
    #: +15,71/op; 5t deixa 45,8% e da' -1,01/op. 2 e' o unico valor vivo.
    offset_ticks: int = 2
    #: Prazo da ordem de ENTRADA parada no livro, EM BARRAS.
    #:
    #: EM BASE DE TICK, BARRA NAO E' TEMPO (CLAUDE.md): a base mede mediana de
    #: 336 barras/minuto, p25 190 e p75 586 -- 5000 barras sao ~15 min na
    #: mediana, ~8,5 min num minuto agitado e ~26 min num minuto parado. O
    #: numero que vale reportar e' o atraso REALIZADO, e ele foi medido: p50
    #: 0,2 min · p90 2,3 min · max 8,6 min, com 19,4% dos pregoes sem
    #: preenchimento nenhum. O prazo curto (~5 min) foi medido junto e e' pior:
    #: 29,2% sem trade e +11,66/op.
    entrada_ttl_bars: int | None = 5000

    #: GEOMETRIA FIXA em ticks absolutos -- quando setados, ignoram a faixa.
    #: REFUTADA (ver `alvo_multiplo`), existe so' para reproduzir a medicao.
    #: A alcancabilidade do alvo e' em ticks ABSOLUTOS, nunca no multiplo:
    #: S40 x 2,0 pede 80 ticks (40 pontos, o movimento do WDO@ do dia inteiro
    #: em 60 min); S10 x 2,0 pede 20 ticks.
    stop_ticks_fixo: int | None = None
    alvo_ticks_fixo: int | None = None

    #: depois que a operacao do dia FECHA (preencheu e saiu, por qualquer
    #: motivo -- stop, alvo ou relogio), um rompimento da faixa ORIGINAL
    #: para o lado OPOSTO ao primeiro do dia dispara uma segunda entrada,
    #: apostando na volta pra dentro da faixa. Uma unica vez por pregao,
    #: no maximo (nunca mais de 2 operacoes no dia). Ver a docstring da
    #: classe para os numeros de IS e OOS.
    fade_rompimento_oposto: bool = True

    _open_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)
    _range_hi: float | None = field(default=None, init=False, repr=False)
    _range_lo: float | None = field(default=None, init=False, repr=False)
    _armou_hoje: bool = field(default=False, init=False, repr=False)
    _limite_posto: bool = field(default=False, init=False, repr=False)
    _preencheu_hoje: bool = field(default=False, init=False, repr=False)
    #: lado do PRIMEIRO rompimento do dia -- o fade so' dispara no lado
    #: contrario a este.
    _lado_primeiro: str | None = field(default=None, init=False, repr=False)
    #: uma fade por pregao, no maximo.
    _fade_usado: bool = field(default=False, init=False, repr=False)
    #: tinha posicao na barra anterior? -- so' existe para detectar a
    #: transicao "tinha e agora nao tem mais" (a posicao original fechou),
    #: o gatilho que libera o fade.
    _tinha_posicao: bool = field(default=False, init=False, repr=False)

    # ---------------- ficha do painel (`dashboard/robot_view.py`) ----------

    tagline: str = (
        "Rompe a faixa dos 15 primeiros minutos do mini-dolar, ate' 2x por dia"
    )

    plain_summary: tuple[str, ...] = (
        "Nos primeiros 15 minutos do pregao o robo so' OLHA: anota o ponto "
        "mais alto e o mais baixo que o mini-dolar negociou. Essa e' a faixa "
        "de abertura.",
        "Quando o preco sai dessa faixa, ele deixa uma ordem 2 ticks ATRAS do "
        "rompimento e espera o preco voltar para peg -- se nao voltar, o dia "
        "passa sem operacao (acontece em 1 de cada 5 pregoes).",
        "Depois que essa operacao fecha, se o preco romper a faixa para o "
        "lado OPOSTO ao primeiro rompimento, ele entra de novo apostando "
        "que o dia volta ao meio. No maximo 2 operacoes por pregao.",
        "Uma hora depois de entrar, se nem o alvo nem o stop tiverem sido "
        "atingidos, ele desiste da meta e passa a pedir o preco do momento -- "
        "por ordem parada, nunca a mercado.",
    )

    plain_example: tuple[str, ...] = (
        "09:00 as 09:15 -- o dolar anda entre 5.100,0 e 5.117,5. Faixa de 35 "
        "ticks: stop 35 ticks, alvo 70 ticks.",
        "09:22 -- rompe para cima. O robo deixa uma ordem de compra a "
        "5.116,5 (2 ticks abaixo do rompimento) e espera.",
        "09:23 -- o preco recua, encosta na ordem e ela preenche. Stop a "
        "5.099,0; alvo, como ordem parada no livro, a 5.151,5.",
        "10:23 -- ninguem pagou o alvo e o stop nao foi tocado. O robo troca "
        "o alvo pelo preco de agora e sai na primeira contraparte.",
    )

    watched_signals: tuple[str, ...] = (
        "Maxima e minima dos primeiros 15 minutos do pregao (a faixa).",
        "Fechamento de cada negocio, para saber se saiu da faixa.",
        "Relogio desde o preenchimento da entrada (o corte de 1 hora).",
    )

    entry_rules: tuple[str, ...] = (
        "Entra comprado se o preco fechar ACIMA da faixa; vendido se fechar "
        "ABAIXO.",
        "Nunca a mercado: ordem-limite parada 2 ticks atras do rompimento.",
        "A ordem tem prazo. Morreu sem preencher, o robo rearma no rompimento "
        "seguinte do mesmo dia -- mas so' enquanto nenhuma operacao aconteceu.",
        "Depois da 1a operacao fechar, um rompimento pro lado OPOSTO ao "
        "primeiro do dia abre uma 2a entrada (o fade). No maximo 2 por dia.",
    )

    exit_rules: tuple[str, ...] = (
        "Stop a MERCADO, do tamanho da faixa de abertura (entre 20 e 40 "
        "ticks). E' a unica saida a mercado do robo.",
        "Alvo = 2x o stop, como ordem-limite REAL parada no livro, fatiada e "
        "sem prazo -- espera o mercado pagar.",
        "1 hora depois da entrada, o alvo e' trocado pelo preco corrente: sai "
        "por ordem parada, nao a mercado.",
        "Nunca vira o dia: o que sobrar e' fechado no achatamento de fim de "
        "pregao.",
    )

    sizing_rules: tuple[str, ...] = (
        "1 contrato, fixo. Nao escala com o caixa.",
        "Caixa de partida OFICIAL R$375,00 (margem R$150 x folga 2,0 x "
        "reserva 1,25) -- mas o teste as cegas (OOS) travou com esse valor "
        "na 1a semana e meia. So' atravessou a janela inteira com R$500,00, "
        "e mesmo assim raspando (minimo tocado R$153,50).",
        "Um stop cheio (40 ticks) custa R$200,00: dois seguidos param o robo "
        "por falta de margem.",
    )

    # ---------------- ciclo ------------------------------------------------

    def on_session_start(self, session_date) -> None:
        self._open_ts = None
        self._range_hi = None
        self._range_lo = None
        self._armou_hoje = False
        self._limite_posto = False
        self._preencheu_hoje = False
        self._lado_primeiro = None
        self._fade_usado = False
        self._tinha_posicao = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """Recusa por teto/capital: a ordem morreu, o arme de hoje some."""
        self._armou_hoje = False

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        """Prazo estourado: idem -- e e' o caminho que MAIS acontece.

        Este metodo e' a correcao de um robo CEGO, nao uma otimizacao. Ate'
        2026-09-10 o motor cancelava a ordem por prazo sem avisar ninguem
        (so' `on_order_rejected` existia, e ele so' dispara na recusa por
        teto): `_armou_hoje` ficava ligado para sempre e o robo passava o
        resto do pregao em silencio achando que tinha ordem no livro. Em 14
        dos 72 pregoes do IS -- +R$1.236,00 contra +R$1.649,00.

        E os 14 pregoes recuperados NAO eram lixo: win 57,1% e +R$29,50/op,
        acima da media do proprio robo. Nao havia selecao adversa escondida
        ali; havia so' silencio.

        Nao e' rearme depois de um TRADE: `_preencheu_hoje` continua
        garantindo uma operacao por pregao. Isto so' devolve a visao.
        """
        self._armou_hoje = False

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._open_ts is None:
            self._open_ts = ts

        # --- a posicao original acabou de fechar? --------------------------
        # `_armou_hoje` so' e' zerado por `on_order_expired`/`on_order_
        # rejected` (eventos de ORDEM) -- nada zerava por evento de POSICAO
        # ate' aqui, entao depois de um fill o campo ficava True pro resto
        # do pregao e o fade nunca era alcancado. Libera o arme aqui, sem
        # tocar `_preencheu_hoje` (ele continua garantindo que o lado
        # ORIGINAL nao repete -- so' o fade tem licenca de operar de novo).
        if self._tinha_posicao and not positions:
            self._tinha_posicao = False
            if self.fade_rompimento_oposto:
                self._armou_hoje = False
                self._limite_posto = False
        if positions:
            self._tinha_posicao = True

        # --- (1) os primeiros minutos: so' olha e mede a faixa -------------
        if (ts - self._open_ts) < pd.Timedelta(minutes=self.range_minutos):
            self._range_hi = bar.high if self._range_hi is None else max(self._range_hi, bar.high)
            self._range_lo = bar.low if self._range_lo is None else min(self._range_lo, bar.low)
            return []

        # --- (2) posicao aberta: so' o relogio decide alguma coisa ---------
        if positions:
            self._preencheu_hoje = True
            pos = positions[0]
            if self.exit_minutos is not None:
                if (ts - pos.entry_ts) >= pd.Timedelta(minutes=self.exit_minutos):
                    return [Exit(reason="tempo_maximo")]
            if self.saida_limite_minutos is not None and not self._limite_posto:
                if (ts - pos.entry_ts) >= pd.Timedelta(minutes=self.saida_limite_minutos):
                    self._limite_posto = True
                    # NO preco corrente, nao alem dele: nao atravessa o livro,
                    # entao e' ordem parada de verdade. O motor cancela a fatia
                    # que estava no alvo antigo e arma outra no nivel novo --
                    # com fila CHEIA, que e' o que a corretora faz.
                    return [AdjustTarget(float(bar.close))]
            return []
        self._limite_posto = False

        # --- (3) sem posicao: arma (ou nao) a entrada ----------------------
        if self._armou_hoje:
            return []
        if self._range_hi is None or self._range_lo is None:
            return []

        if not self._preencheu_hoje:
            stop_ticks, alvo_ticks = self._geometria()
            off = self.offset_ticks * self.tick_size

            if bar.close > self._range_hi:
                # comprado: a limite fica ABAIXO do rompimento (espera o recuo)
                limite = bar.close - off
                self._armou_hoje = True
                self._lado_primeiro = "long"
                return [self._ordem("long", limite, stop_ticks, alvo_ticks,
                                    "orb_rompimento_alta")]
            if bar.close < self._range_lo:
                # vendido: a limite fica ACIMA do rompimento
                limite = bar.close + off
                self._armou_hoje = True
                self._lado_primeiro = "short"
                return [self._ordem("short", limite, stop_ticks, alvo_ticks,
                                    "orb_rompimento_baixa")]
            return []

        # --- (4) o FADE: operacao do dia ja fechou, rompimento CONTRARIO ---
        # ao primeiro do dia. Mesma faixa (nunca refeita), mesma formula de
        # geometria -- so' o lado inverte. Uma vez por pregao, no maximo.
        if (self.fade_rompimento_oposto and not self._fade_usado
                and self._lado_primeiro is not None):
            stop_ticks, alvo_ticks = self._geometria()
            off = self.offset_ticks * self.tick_size
            if self._lado_primeiro == "long" and bar.close < self._range_lo:
                self._fade_usado = True
                self._armou_hoje = True
                return [self._ordem("long", bar.close - off, stop_ticks,
                                    alvo_ticks, "orb_fade_volta_a_faixa")]
            if self._lado_primeiro == "short" and bar.close > self._range_hi:
                self._fade_usado = True
                self._armou_hoje = True
                return [self._ordem("short", bar.close + off, stop_ticks,
                                    alvo_ticks, "orb_fade_volta_a_faixa")]
        return []

    # ---------------- auxiliares (puros) -----------------------------------

    def _geometria(self) -> tuple[int, int]:
        """`(stop_ticks, alvo_ticks)` desta entrada -- da faixa, ou fixos."""
        if self.stop_ticks_fixo is not None:
            stop_ticks = self.stop_ticks_fixo
        else:
            assert self._range_hi is not None and self._range_lo is not None
            range_ticks = (self._range_hi - self._range_lo) / self.tick_size
            stop_ticks = max(self.stop_min_ticks,
                             min(self.stop_max_ticks, round(range_ticks)))
        alvo_ticks = (self.alvo_ticks_fixo if self.alvo_ticks_fixo is not None
                      else round(stop_ticks * self.alvo_multiplo))
        return int(stop_ticks), int(alvo_ticks)

    def _ordem(self, side, limite: float, stop_ticks: int, alvo_ticks: int,
               reason: str) -> EnterLimit:
        sinal = 1.0 if side == "long" else -1.0
        return EnterLimit(
            side=side,
            limit_price=limite,
            initial_stop=limite - sinal * stop_ticks * self.tick_size,
            initial_target=limite + sinal * alvo_ticks * self.tick_size,
            quantity=self.quantity,
            ttl_bars=self.entrada_ttl_bars,
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=reason,
        )
