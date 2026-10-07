# -*- coding: utf-8 -*-
"""`WinBuscaLucroG03RecuoRaso` -- Geracao 3 da busca por um EA lucrativo do WIN.

Mandato do dono (`ORQUESTRACAO.md`, Geracoes 1 e 2): as duas geracoes
anteriores mataram R61 e R65 por FREQUENCIA -- 14 e depois 4 operacoes em 6
meses de IS, amostra pequena demais para qualquer leitura confiavel mesmo
quando a qualidade do sinal parecia OK no papel. Esta geracao busca um
gatilho de MAIOR FREQUENCIA: `REGRAS.md` registra, na familia "recuo raso"
(rodada 6), um sinal que CONFIRMOU com amostra grande (n=380 em jul-ago) mas
ficou perto do breakeven -- R57. A hipotese: filtrar R57 por R59 (e
opcionalmente R58, horario) pode empurrar a fatia selecionada para ACIMA do
breakeven, mantendo frequencia bem maior que R61/R65.

## R57 -- recuo raso, entrada no reteste

Depois de um avanco A (pernada de referencia, zigzag causal sobre o CAMINHO
da vela -- mesma definicao congelada em 2026-10-04 usada pelo R43/R65 da
G1/G2: vela de alta anda minima->maxima, vela de baixa anda maxima->minima),
o 1o recuo (retracao) desse avanco e' "raso" quando o fundo dele cai em
[23%, 38%] da distancia do avanco. Entrada por `EnterLimit` a `m` pontos
ACIMA do fundo (reteste, favor do avanco), stop NO FUNDO (menos 1 tick de
folga -- ver nota de `m=0` abaixo), alvo = `alvo_multiplo` x o risco
(distancia entrada-stop).

**Definicao operacional de "recuo" desta geracao (nao e' replica byte-a-byte
do script original da rodada 6, que nao esta disponivel neste repo --
aproxima o MESMO espirito, documentado explicitamente para quem revisitar
isto no futuro):** um recuo comeca quando o preco (ponto do caminho da vela)
se afasta do extremo corrente da perna; o "fundo candidato" e' o ponto mais
adverso alcancado desde entao. O recuo "FECHA" -- e so' nesse momento a
fracao [23%,38%] e' avaliada -- na primeira vez que o preco volta e supera o
fundo candidato por >= `reversao_minima_recuo_pontos` (sub-zigzag interno,
independente do zigzag de 500/750 pontos da perna maior; default 50 pontos,
NAO e' parametro desta geracao -- so' um limiar de ruido). Isto e' o mesmo
principio de um indicador ZigZag padrao (desvio minimo antes de confirmar
um pivo), aplicado numa escala menor DENTRO da perna maior.

"1o fundo": a contagem de recuos fechados dentro da MESMA perna reinicia a
cada vez que o zigzag da perna maior muda de direcao (nova perna = nova
contagem). R57 so' avalia entrada no 1o recuo fechado de cada perna --
recuos subsequentes da mesma perna so' atualizam a referencia usada por R59
(abaixo), nunca geram entrada.

## R59 -- filtro de fundos ascendentes/descendentes ENTRE pernas

"O fundo do recuo atual e' >= (numa alta) ou <= (numa baixa) o fundo do
recuo anterior" -- interpretado aqui como o fundo do 1o recuo da perna
ANTERIOR da MESMA direcao (nao um 2o recuo dentro da mesma perna -- isso e'
R56, que `REGRAS.md` ja registra como NEGATIVO/= acaso). E' a estrutura
classica de "fundos ascendentes" (alta) / "topos descendentes" (baixa) entre
avancos sucessivos. `_fundo_recuo1_anterior[direcao]` guarda essa referencia,
atualizada toda vez que um 1o recuo fecha (esteja ele dentro da faixa
23-38% ou nao) -- e' sinal estrutural, nao condicionado ao gatilho R57.
Sem referencia anterior (1a perna da sessao naquela direcao), o filtro R59
REJEITA por falta de evidencia (nao ha' "anterior" para comparar).

## R58 -- janela de horario como PARAMETRO (nao portao fixo)

Mesmo espirito da G2 (`WinBuscaLucroG02R65`): `janela_inicio`/`janela_fim`
delimitam quando o robo pode EMITIR a ordem -- o estado do gatilho (zigzag,
recuo, fechamento) continua sendo atualizado em TODA barra, dentro ou fora
da janela.

## Direcao -- SEMPRE a favor da pernada maior (R43, princ. inegociavel)

O recuo so' e' avaliado DENTRO de uma perna em andamento, e a entrada
resultante e' sempre na direcao de RETOMADA dessa perna (compra num recuo de
alta, venda num recuo de baixa) -- nunca contra ela. Nao ha' parametro que
desligue isto.

## m=0 e o risco minimo

Com `m_pontos=0`, entrada = fundo exatamente. Sem nenhuma folga adicional o
risco seria ZERO (entrada = stop), ordem invalida. Por isso o stop fica
sempre `fundo -/+ 1 tick` (nunca exatamente NO fundo) -- risco minimo
garantido = 1 tick, mesmo com m=0. E' a UNICA diferenca em relacao a leitura
literal "stop no fundo" de `REGRAS.md`; documentada aqui porque muda o
risco efetivo de toda celula com m pequeno.

## Execucao -- o desenho fechado, sem excecao (CLAUDE.md)

Entrada so' por `EnterLimit` com `ttl_bars` obrigatorio; alvo so' como
ordem-limite real fatiada (`exit_split_unit`), SEM prazo
(`exit_ttl_bars=None`); so' o stop e' a mercado; `anchor_exits_at_fill=True`;
`target_fills_as_maker=True`. Conferencia MECANICA antes de armar (limite de
compra so' descansa ABAIXO do preco corrente, de venda so' ACIMA -- e' um
reteste: o preco ja' subiu/desceu `reversao_minima_recuo_pontos` antes do
fechamento do recuo ser confirmado, entao a entrada quase sempre fica atras
do preco corrente).

## Fila -- WIN@ nao tem fidelidade calibrada

Mesma ressalva de toda a linha G1/G2/`WinRetangulo`: toda medicao desta
classe roda com `queue_ahead_qty=0`/`exit_queue_ahead_qty=0` (enche no
toque), premissa OTIMISTA declarada, identica nas duas janelas.

## Capital e dimensionamento

1 contrato FIXO (`quantity=1`, sem escala por caixa) -- dimensionamento
dinamico fica para geracao futura, mesma decisao da G1/G2.

## Contadores de auditoria (licao da Geracao 2)

Um bug de ORDEM DE OPERACOES dentro de `on_bar` (atualizar estado antes de
checar se ha' ordem pendente) fez a G1/G2 nunca emitirem ordem de R65 por
DUAS geracoes, silenciosamente. Aqui a atualizacao de estado (zigzag, recuo,
fechamento, contagem) roda SEMPRE, em toda barra; a decisao "posso emitir
ordem AGORA" (`pode_armar`) e' calculada no INICIO de `on_bar`, com o estado
que existia ANTES de qualquer atualizacao desta mesma chamada, e so' entao
passada para o processamento -- nunca o inverso. `stats_bruto_r57` conta TODA
ocorrencia do gatilho R57 (1o recuo fechado, fracao na faixa, a favor da
perna), batizada "BRUTA" porque conta ANTES de qualquer filtro de
execucao/capital/pode_armar; `stats_ordens_emitidas` conta so' as que viraram
`EnterLimit` de verdade. Se a razao emitidas/bruta cair para perto de zero
sem explicacao (filtro R59/horario conhecido), e' sinal do mesmo bug
reaparecendo.
"""
from __future__ import annotations

import datetime as _dt
from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

#: Limiar da pernada de referencia (zigzag causal sobre o caminho da vela,
#: mesma definicao de R43). PARAMETRO desta geracao (500 ou 750).
PERNADA_PONTOS = 750.0
#: Sub-zigzag interno que confirma o FECHAMENTO de um recuo -- NAO e'
#: parametro desta geracao (ver docstring do modulo), so' limiar de ruido.
REVERSAO_MINIMA_RECUO_PONTOS = 50.0
#: Faixa do recuo "raso" (R57, congelada em REGRAS.md -- nao e' parametro).
FAIXA_RECUO_MIN = 0.23
FAIXA_RECUO_MAX = 0.38
#: Prazo da ordem-limite de ENTRADA (ver CLAUDE.md "O desenho de execucao").
TTL_BARRAS_ENTRADA = 10
#: Multiplo do risco que vira alvo -- REGRAS.md mede 5x; disciplina do dono
#: exige >=3x.
ALVO_MULTIPLO = 5.0
#: Buffer m (pontos acima/abaixo do fundo) -- PARAMETRO desta geracao.
M_PONTOS = 10.0


def _caminho_da_barra(bar: Bar) -> tuple[float, float]:
    """Os DOIS pontos do "caminho" desta vela, na ordem em que o preco
    provavelmente passou por eles -- definicao CONGELADA em `REGRAS.md`:
    vela de alta (fecha >= abre) anda minima->maxima; vela de baixa anda
    maxima->minima. Pura (so' le o `Bar` recebido), identica a` usada em
    R43/R65 (G1/G2)."""
    if bar.close >= bar.open:
        return (bar.low, bar.high)
    return (bar.high, bar.low)


def _parse_hhmm(texto: str) -> _dt.time:
    h, m = texto.split(":")
    return _dt.time(int(h), int(m))


class WinBuscaLucroG03RecuoRaso(IntradayStrategy):  # CONGELADO v03 -- OOS-1, 2026-10-05
    """R57 (recuo raso, 1o fundo em 23-38% do avanco) + filtros opcionais
    R59 (fundos ascendentes/descendentes entre pernas) e R58 (janela de
    horario) -- Geracao 3 da busca por um EA lucrativo do WIN
    (`ORQUESTRACAO.md`). Sempre a favor da pernada maior (R43)."""

    name = "win_busca_lucro_g03_recuo_raso"
    version = "0.1.0"
    symbol = "WIN@"
    is_futuro = True
    target_fills_as_maker = True
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        pernada_pontos: float = PERNADA_PONTOS,
        reversao_minima_recuo_pontos: float = REVERSAO_MINIMA_RECUO_PONTOS,
        m_pontos: float = M_PONTOS,
        alvo_multiplo: float = ALVO_MULTIPLO,
        usar_filtro_r59: bool = False,
        janela_inicio: str = "00:00",
        janela_fim: str = "23:59",
        ttl_barras_entrada: int = TTL_BARRAS_ENTRADA,
        quantity: int = 1,
    ) -> None:
        if pernada_pontos <= 0:
            raise ValueError("pernada_pontos tem que ser positivo")
        if reversao_minima_recuo_pontos <= 0:
            raise ValueError("reversao_minima_recuo_pontos tem que ser positivo")
        if m_pontos < 0:
            raise ValueError("m_pontos nao pode ser negativo")
        if alvo_multiplo < 3.0:
            raise ValueError(
                f"alvo_multiplo={alvo_multiplo} abaixo de 3x -- fere a disciplina "
                f"alvo >= 3x o stop do mandato do dono"
            )
        if ttl_barras_entrada is None or ttl_barras_entrada <= 0:
            raise ValueError(
                "ttl_barras_entrada e' obrigatorio: limite de entrada sem prazo "
                "vira ordem esquecida no livro (ver CLAUDE.md)"
            )
        if symbol is not None:
            self.symbol = symbol
        self.pernada_pontos = float(pernada_pontos)
        self.reversao_minima_recuo_pontos = float(reversao_minima_recuo_pontos)
        self.m_pontos = float(m_pontos)
        self.alvo_multiplo = float(alvo_multiplo)
        self.usar_filtro_r59 = bool(usar_filtro_r59)
        self.janela_inicio = _parse_hhmm(janela_inicio)
        self.janela_fim = _parse_hhmm(janela_fim)
        self.ttl_barras_entrada = int(ttl_barras_entrada)
        self.quantity = int(quantity)

        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size
        self.valor_do_ponto_brl = economia.point_value_brl

        # -- contadores de auditoria (licao da Geracao 2, ver docstring) --
        self.stats_bruto_r57 = 0
        self.stats_ordens_emitidas = 0

        self._reset_sessao()

    # -- janela de horario (PARAMETRO, nao portao fixo) ----------------------
    def _dentro_da_janela(self, ts: pd.Timestamp) -> bool:
        t = ts.time()
        return self.janela_inicio <= t <= self.janela_fim

    # -- estado por sessao ----------------------------------------------------
    def _reset_sessao(self) -> None:
        # zigzag da perna maior (R43) -- reseta a cada pregao: `WIN@` e' serie
        # continua com emenda de rolagem, nenhum nivel de preco atravessa a
        # sessao (mesmo motivo de `WinRetangulo`/G1/G2).
        self._origem: float | None = None
        self._extremo: float | None = None
        self._direcao: int | None = None
        self._contagem_recuos_na_perna = 0
        self._fundo_candidato: float | None = None
        # referencia de R59, por direcao -- tambem reseta por sessao.
        self._fundo_recuo1_anterior: dict[int, float] = {}
        # ordem pendente (uma por vez)
        self._espera: int | None = None
        self._hist: deque[Bar] = deque(maxlen=4)

    def on_session_start(self, session_date) -> None:
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._espera = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        self._espera = None

    # -- perna maior + recuo (R43 + R57/R59) ----------------------------------
    def _inicia_perna(self, nova_direcao: int, origem_nova: float, extremo_novo: float) -> None:
        self._direcao = nova_direcao
        self._origem = origem_nova
        self._extremo = extremo_novo
        self._contagem_recuos_na_perna = 0
        self._fundo_candidato = None

    def _monta_entrada(self, s: int, fundo: float, bar: Bar) -> IntradayAction | None:
        buffer_pts = self.tick_size if self.tick_size > 0 else 0.01
        if s == 1:
            entrada = fundo + self.m_pontos
            stop = fundo - buffer_pts
            risco = entrada - stop
            lado = "long"
        else:
            entrada = fundo - self.m_pontos
            stop = fundo + buffer_pts
            risco = stop - entrada
            lado = "short"
        if risco <= 0:
            return None
        alvo = entrada + self.alvo_multiplo * risco if s == 1 else entrada - self.alvo_multiplo * risco

        limite = no_tick(entrada, self.tick_size)
        # Conferencia MECANICA (mesmo criterio de `WinRetangulo`/`WinBuscaLucroG02R65`):
        # e' um RETESTE -- o preco ja' se afastou do fundo por >=
        # reversao_minima_recuo_pontos antes do fechamento ser confirmado, entao a
        # entrada quase sempre fica atras do preco corrente. Limite de compra so'
        # descansa ABAIXO do preco corrente, de venda so' ACIMA.
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
            reason=f"r57_recuo_raso_T{int(self.pernada_pontos)}_m{self.m_pontos:.0f}",
        )

    def _fecha_recuo_e_avalia(
        self, ts: pd.Timestamp, bar: Bar, pode_armar: bool, s: int,
    ) -> list[IntradayAction]:
        fundo = self._fundo_candidato
        extremo = self._extremo
        origem = self._origem
        avanco = abs(extremo - origem)
        retrocesso = abs(extremo - fundo)
        fracao = (retrocesso / avanco) if avanco > 0 else float("nan")
        self._contagem_recuos_na_perna += 1
        eh_primeiro = self._contagem_recuos_na_perna == 1
        self._fundo_candidato = None  # recuo fechado -- pronto para o proximo

        acoes: list[IntradayAction] = []
        if not eh_primeiro or fracao != fracao:
            return acoes
        na_faixa = FAIXA_RECUO_MIN <= fracao <= FAIXA_RECUO_MAX
        if na_faixa:
            # BRUTO: conta SEMPRE que o gatilho literal ocorre, antes de
            # qualquer filtro de execucao/capital/pode_armar -- ver docstring
            # do modulo sobre a licao da Geracao 2.
            self.stats_bruto_r57 += 1
            aceita = True
            if self.usar_filtro_r59:
                anterior = self._fundo_recuo1_anterior.get(s)
                if anterior is None:
                    aceita = False
                elif s == 1 and fundo < anterior:
                    aceita = False
                elif s == -1 and fundo > anterior:
                    aceita = False
            if aceita and not self._dentro_da_janela(ts):
                aceita = False
            if aceita and pode_armar:
                acao = self._monta_entrada(s, fundo, bar)
                if acao is not None:
                    acoes.append(acao)
                    self.stats_ordens_emitidas += 1
        # referencia de R59 para a PROXIMA perna desta direcao -- atualiza
        # sempre que fecha o 1o recuo, DENTRO ou FORA da faixa 23-38% (e'
        # sinal estrutural, nao condicionado ao gatilho R57).
        self._fundo_recuo1_anterior[s] = fundo
        return acoes

    def _processa_ponto(self, ts: pd.Timestamp, bar: Bar, p: float, pode_armar: bool) -> list[IntradayAction]:
        if self._origem is None:
            self._origem = p
            self._extremo = p
            return []
        s = self._direcao
        if s is None:
            if p - self._origem >= self.pernada_pontos:
                self._inicia_perna(1, self._origem, p)
            elif self._origem - p >= self.pernada_pontos:
                self._inicia_perna(-1, self._origem, p)
            return []
        if s == 1:
            if p > self._extremo:
                self._extremo = p
                self._fundo_candidato = None
                return []
            if self._fundo_candidato is None:
                self._fundo_candidato = p
            else:
                self._fundo_candidato = min(self._fundo_candidato, p)
            if self._extremo - p >= self.pernada_pontos:
                self._inicia_perna(-1, self._extremo, p)
                return []
            if p - self._fundo_candidato >= self.reversao_minima_recuo_pontos:
                return self._fecha_recuo_e_avalia(ts, bar, pode_armar, s)
            return []
        else:
            if p < self._extremo:
                self._extremo = p
                self._fundo_candidato = None
                return []
            if self._fundo_candidato is None:
                self._fundo_candidato = p
            else:
                self._fundo_candidato = max(self._fundo_candidato, p)
            if p - self._extremo >= self.pernada_pontos:
                self._inicia_perna(1, self._extremo, p)
                return []
            if self._fundo_candidato - p >= self.reversao_minima_recuo_pontos:
                return self._fecha_recuo_e_avalia(ts, bar, pode_armar, s)
            return []

    # -- loop -------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)

        # Decide ANTES de atualizar qualquer estado se este robo PODE armar
        # uma ordem nova nesta barra -- com o `_espera` que existia no INICIO
        # da barra, nunca um valor que o processamento abaixo ainda vai
        # setar (licao da Geracao 2 -- ver docstring do modulo).
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

        acoes: list[IntradayAction] = []
        for p in _caminho_da_barra(bar):
            novas = self._processa_ponto(ts, bar, p, pode_armar)
            if novas:
                acoes = novas
                break
        return acoes if pode_armar else []
