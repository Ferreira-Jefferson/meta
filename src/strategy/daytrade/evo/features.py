"""O BANCO DE FEATURES -- as 33 coordenadas que o robo evoluido pode olhar.

## A tensao que este arquivo resolve

Havia duas pressoes opostas no desenho, e as duas sao legitimas:

  * **a do metodo**: com 52 pregoes de treino nao ha evidencia para
    redescobrir o mercado do zero. A literatura de inducao de regra de
    trading por algoritmo evolutivo e' majoritariamente um cemiterio por
    isso (Allen & Karjalainen 1999: as regras nao batem buy-and-hold fora da
    amostra depois do custo), e o remedio que ela aponta e' parcimonia;
  * **a do dono** (2026-09-18): *"queremos uma IA que consiga ver o que nao
    estamos vendo, que vença instintivamente, que tenha lucro mesmo parecendo
    que nao esta' seguindo uma regra. O conhecimento acumulado e' util, mas
    nao podemos limitar a evolucao ao que sabemos."*

Elas parecem incompativeis e nao sao, porque **o que protege contra decorar
nao e' o banco de features ser pequeno -- e' o GENOMA ser pequeno.** O
individuo escolhe 6 coordenadas entre as 33. Dobrar o banco nao acrescenta um
unico parametro livre: muda so' o alcance de um indice que ja' existia. O
espaco de DESCOBERTA cresce; o espaco de MEMORIZACAO nao.

Por isso o banco tem dois blocos, e os dois estao em pe de igualdade na hora
do sorteio:

  * **0-16, o bloco destilado** -- a forma numerica do que este projeto ja'
    mediu. Nao esta' aqui como verdade a ser obedecida, e sim como atalho:
    sao coordenadas em que ja' se sabe que ha' estrutura, entao a busca nao
    precisa gastar geracoes redescobrindo que existe uma faixa de abertura;
  * **17-32, o bloco CRU** -- geometria de barra, sequencias, distancia a
    extremos, irregularidade de fluxo, hora redonda, preco redondo. Nenhuma
    dessas tem hipotese associada neste repo. Varias provavelmente nao
    significam nada. Estao aqui exatamente para a busca poder discordar do
    que nos achamos que importa, e para uma combinacao que nenhum humano
    escreveria poder aparecer.

A honestidade que acompanha isso: **liberdade para descobrir nao e'
liberdade para acreditar.** Um espaco de busca maior significa mais
tentativas efetivas, e mais tentativas efetivas significam que o melhor
resultado dentro da amostra e' mais provavelmente sorte (e' o argumento do
Deflated Sharpe Ratio). O que decide continua sendo replicar no OOS, e essa
barra sobe -- nao desce -- quando o espaco abre.

## O que continua fora, e nao por conservadorismo

  * qualquer coisa que dependa de uma barra que ainda nao fechou;
  * qualquer coisa que dependa do DIA INTEIRO. `dist_max_sessao` e' a
    distancia a maxima ATE AGORA, nao a maxima do dia -- ao vivo, as 10:30, o
    robo nao sabe qual sera' a maxima das 17h. Um banco montado com
    `df.rolling(...)` sobre a sessao inteira tem esse vazamento embutido e
    ele e' invisivel na leitura. Aqui tudo e' acumulado em `registrar()`,
    barra a barra, na mesma ordem em que o feed entrega. Nao e' zelo: uma
    busca evolutiva nao COMETE o erro de olhar o futuro, ela CONVERGE para
    ele, porque olhar o futuro e' a melhor estrategia que existe;
  * preco ABSOLUTO. Toda feature e' adimensional. Com acesso ao nivel de
    preco, a busca decora datas.

## Normalizacao

Tudo em [-1, 1] (ou [0, 1] para as sem sinal). A politica e' uma soma
ponderada: feature de escala livre faz o peso significar coisas diferentes em
dias diferentes, e a busca "corrige" isso decorando a escala tipica da janela
de treino. O divisor de quase todas e' o RANGE DIARIO MEDIANO dos dias
anteriores (`JanelaVolatilidadeDiaria`), a unica escala disponivel ao vivo
antes de o pregao comecar.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import Bar

#: A ORDEM e' contrato: o genoma guarda INDICES nesta lista, entao mexer na
#: ordem (ou remover um nome) renomeia silenciosamente as features de todo
#: genoma ja' salvo em disco. Para acrescentar, acrescente NO FIM.
NOMES: tuple[str, ...] = (
    # ---- bloco DESTILADO: o que o projeto ja' mediu ---------------------
    "pos_faixa",        # 0  onde o preco esta' na faixa de abertura
    "larg_faixa",       # 1  largura da faixa / range diario mediano
    "dentro_faixa",     # 2  1 se o preco esta' dentro da faixa agora
    "rompeu_cima",      # 3  quantas vezes o dia rompeu para cima
    "rompeu_baixo",     # 4  idem, para baixo
    "hora",             # 5  fracao do pregao ja' decorrida
    "vol_rel",          # 6  volume 5min / media do dia ate agora
    "acel_vol",         # 7  volume medio 5min / volume medio 15min
    "amplit_rel",       # 8  amplitude 15min / range diario mediano
    "drift_norm",       # 9  deslocamento 15min / amplitude 15min
    "dist_vwap",        # 10 (close - vwap da sessao) / range diario mediano
    "dist_abert",       # 11 (close - abertura) / range diario mediano
    "gap_abertura",     # 12 (abertura - fechamento de ontem) / range
    "em_retangulo",     # 13 1 se as ultimas W barras couberam numa faixa fina
    "pos_retangulo",    # 14 onde o preco esta' nesse retangulo
    "pnl_sessao",       # 15 PnL da sessao / risco de uma operacao
    "ops_hoje",         # 16 operacoes ja feitas hoje / teto do genoma
    # ---- bloco CRU: sem hipotese associada ------------------------------
    "corpo_rel",        # 17 corpo da barra / amplitude da barra
    "sombra_sup",       # 18 sombra superior / amplitude da barra
    "sombra_inf",       # 19 sombra inferior / amplitude da barra
    "ret_1",            # 20 retorno da ultima barra / range diario mediano
    "ret_15",           # 21 retorno de 15min / range diario mediano
    "seq_direcao",      # 22 barras consecutivas na mesma direcao (com sinal)
    "reversao_5",       # 23 produto dos dois ultimos retornos de 5min
    "dist_max_sessao",  # 24 (close - maxima ATE AGORA) / range
    "dist_min_sessao",  # 25 (close - minima ATE AGORA) / range
    "idade_extremo",    # 26 tempo desde o ultimo extremo / tempo decorrido
    "irreg_volume",     # 27 desvio dos volumes 15min / media deles
    "contracao",        # 28 amplitude 5min / amplitude 15min
    "dia_semana",       # 29 posicao do dia na semana
    "minuto_hora",      # 30 posicao dentro da hora cheia
    "preco_redondo",    # 31 distancia ao multiplo de 5 pontos mais proximo
    "assimetria_ret",   # 32 assimetria dos retornos dos ultimos 15min
)
N_FEATURES = len(NOMES)

#: Janela do detector de retangulo, em MINUTOS, e a tolerancia de largura.
#: Os numeros vem do `win_retangulo` (W=30 e 20%, os dois confirmados em OOS
#: congelado). Ficam constantes e NAO entram no genoma de proposito: sao
#: parametros de um detector ja' validado, e reabri-los aqui seria re-tunar
#: no IS algo que ja' passou pelo teste cego.
RETANGULO_MINUTOS = 30
RETANGULO_TOLERANCIA = 0.20

#: Grade de "preco redondo" do WDO, em pontos. 5 pontos = 10 ticks.
GRADE_REDONDA_PONTOS = 5.0

_MINUTOS_CURTO = 5
_MINUTOS_MEDIO = 15

#: As janelas em NANOSSEGUNDOS, pre-calculadas.
#:
#: Nao e' microotimizacao gratuita -- foi medido. Com `pd.Timedelta(minutes=
#: n)` construido a cada chamada, `_podar` sozinha respondia por 13% do tempo
#: TOTAL de uma avaliacao (0,705s de 5,24s num perfil de 6 pregoes), porque
#: ela roda tres vezes por barra e aritmetica de `Timestamp` custa dezenas de
#: microssegundos. Guardando os instantes como inteiros, a comparacao vira
#: subtracao de int.
#:
#: Numa busca evolutiva isso importa de um jeito que nao importaria num
#: script normal: o banco de features roda uma vez por barra por individuo
#: por geracao -- na ordem de 10^8 chamadas numa rodada.
_NS_MINUTO = 60 * 1_000_000_000
_NS_CURTO = _MINUTOS_CURTO * _NS_MINUTO
_NS_MEDIO = _MINUTOS_MEDIO * _NS_MINUTO
_NS_RETANGULO = RETANGULO_MINUTOS * _NS_MINUTO


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    if x != x:  # NaN
        return 0.0
    return lo if x < lo else (hi if x > hi else x)


def _razao(numerador: float, denominador: float) -> float:
    """Razao segura: denominador nulo/negativo/NaN devolve 0,0.

    Zero e' o valor certo para "nao sei" aqui porque a politica e' uma soma
    ponderada: uma feature em 0 nao empurra a decisao para lado nenhum, que
    e' exatamente o que se quer de uma medida indisponivel. NaN contaminaria
    o score inteiro; um default positivo daria a ausencia de informacao o
    poder de virar um voto."""
    if denominador is None or denominador != denominador or denominador <= 0:
        return 0.0
    if numerador != numerador:
        return 0.0
    return numerador / denominador


@dataclass
class BancoDeFeatures:
    """Estado acumulado de UMA sessao, atualizado barra a barra.

    Nao guarda o historico inteiro: so' as janelas curtas (`deque` podado por
    minutos) e os acumuladores de que a VWAP, as medias e os extremos
    precisam. Isso nao e' economia de memoria -- e' a garantia ESTRUTURAL de
    que nao ha' como consultar uma barra que o robo ao vivo ja' teria
    esquecido, nem uma que ele ainda nao teria visto."""

    range_minutos: float = 15.0

    #: Preenchidos pelo robo a partir do que o MOTOR entrega (dias PASSADOS).
    range_diario_mediano: float | None = field(default=None)
    fechamento_vespera: float | None = field(default=None)

    # --- estado da sessao ------------------------------------------------
    # Os instantes sao guardados em NANOSSEGUNDOS (int), nunca como
    # `pd.Timestamp` -- ver `_NS_CURTO` para o custo medido da alternativa.
    _abertura_ts: int | None = field(default=None, init=False)
    _abertura_preco: float = field(default=float("nan"), init=False)
    _fim_ts: int | None = field(default=None, init=False)
    _faixa_hi: float | None = field(default=None, init=False)
    _faixa_lo: float | None = field(default=None, init=False)
    _rompeu_cima: int = field(default=0, init=False)
    _rompeu_baixo: int = field(default=0, init=False)
    _lado_anterior: int = field(default=0, init=False)

    _soma_pv: float = field(default=0.0, init=False)   # preco x volume
    _soma_v: float = field(default=0.0, init=False)
    _n_barras: int = field(default=0, init=False)
    _soma_vol: float = field(default=0.0, init=False)

    _max_sessao: float | None = field(default=None, init=False)
    _min_sessao: float | None = field(default=None, init=False)
    _ts_extremo: int | None = field(default=None, init=False)
    _seq: int = field(default=0, init=False)
    _fech_anterior: float | None = field(default=None, init=False)

    _curto: deque = field(default_factory=deque, init=False)   # 5 min
    _medio: deque = field(default_factory=deque, init=False)   # 15 min
    _retang: deque = field(default_factory=deque, init=False)  # 30 min
    #: Retornos de 5 minutos, os dois ultimos -- alimenta `reversao_5`.
    _ret5: deque = field(default_factory=lambda: deque(maxlen=2), init=False)
    _ancora_ret5: float | None = field(default=None, init=False)
    _ts_ancora_ret5: int | None = field(default=None, init=False)

    def iniciar_sessao(self, fim_ts: pd.Timestamp | None = None) -> None:
        """`fim_ts` e' o instante nominal de fechamento da sessao, usado so'
        para normalizar a feature `hora`. Chega como `Timestamp` (e' o que o
        robo tem em maos) e e' guardado em nanossegundos."""
        self._abertura_ts = None
        self._abertura_preco = float("nan")
        self._fim_ts = None if fim_ts is None else fim_ts.value
        self._faixa_hi = self._faixa_lo = None
        self._rompeu_cima = self._rompeu_baixo = 0
        self._lado_anterior = 0
        self._soma_pv = self._soma_v = self._soma_vol = 0.0
        self._n_barras = 0
        self._max_sessao = self._min_sessao = None
        self._ts_extremo = None
        self._seq = 0
        self._fech_anterior = None
        self._curto.clear()
        self._medio.clear()
        self._retang.clear()
        self._ret5.clear()
        self._ancora_ret5 = None
        self._ts_ancora_ret5 = None

    # -- acumulacao --------------------------------------------------------

    @property
    def faixa_pronta(self) -> bool:
        return self._faixa_hi is not None and self._faixa_lo is not None

    def registrar(self, ts: pd.Timestamp, bar: Bar) -> None:
        """Absorve uma barra que JA FECHOU. Chamada uma vez por barra, sempre
        antes de `vetor()`, e nunca com uma barra fora de ordem.

        Os instantes viram inteiros (nanossegundos) logo na entrada: a partir
        daqui nenhuma comparacao de tempo constroi objeto do pandas. Ver
        `_NS_CURTO` para o que isso custava."""
        agora = ts.value
        if self._abertura_ts is None:
            self._abertura_ts = agora
            self._abertura_preco = bar.open
            self._ts_extremo = agora
            self._ancora_ret5 = bar.open
            self._ts_ancora_ret5 = agora

        em_formacao = (agora - self._abertura_ts) < (
            self.range_minutos * _NS_MINUTO)
        if em_formacao:
            self._faixa_hi = bar.high if self._faixa_hi is None else max(
                self._faixa_hi, bar.high)
            self._faixa_lo = bar.low if self._faixa_lo is None else min(
                self._faixa_lo, bar.low)
        elif self.faixa_pronta:
            # Um rompimento so' conta quando o preco TROCA de regiao -- sem
            # isso, um dia que passa a tarde inteira acima da faixa somaria
            # centenas de "rompimentos" e o contador viraria um relogio
            # disfarcado. O que interessa e' quantas VEZES o dia mudou de
            # ideia, que e' o que a perna de fade do `wdo_orb` explora.
            lado = 1 if bar.close > self._faixa_hi else (
                -1 if bar.close < self._faixa_lo else 0)
            if lado != 0 and lado != self._lado_anterior:
                if lado > 0:
                    self._rompeu_cima += 1
                else:
                    self._rompeu_baixo += 1
            if lado != 0:
                self._lado_anterior = lado

        volume = float(bar.volume or 0.0)
        self._soma_pv += bar.close * volume
        self._soma_v += volume
        self._soma_vol += volume
        self._n_barras += 1

        # Extremos da sessao ATE AGORA (nunca do dia inteiro -- ver a
        # docstring do modulo) e quando o ultimo deles aconteceu.
        if self._max_sessao is None or bar.high > self._max_sessao:
            self._max_sessao = bar.high
            self._ts_extremo = agora
        if self._min_sessao is None or bar.low < self._min_sessao:
            self._min_sessao = bar.low
            self._ts_extremo = agora

        if self._fech_anterior is not None:
            direcao = (1 if bar.close > self._fech_anterior
                       else (-1 if bar.close < self._fech_anterior else 0))
            if direcao == 0:
                self._seq = 0
            elif (self._seq > 0) == (direcao > 0) and self._seq != 0:
                self._seq += direcao
            else:
                self._seq = direcao
        self._fech_anterior = bar.close

        if self._ts_ancora_ret5 is not None:
            if (agora - self._ts_ancora_ret5) >= _NS_CURTO:
                self._ret5.append(bar.close - (self._ancora_ret5 or bar.close))
                self._ancora_ret5 = bar.close
                self._ts_ancora_ret5 = agora

        item = (agora, bar)
        self._curto.append(item)
        self._medio.append(item)
        self._retang.append(item)
        self._podar(self._curto, agora - _NS_CURTO)
        self._podar(self._medio, agora - _NS_MEDIO)
        self._podar(self._retang, agora - _NS_RETANGULO)

    @staticmethod
    def _podar(fila: deque, corte_ns: int) -> None:
        while fila and fila[0][0] < corte_ns:
            fila.popleft()

    # -- leitura -----------------------------------------------------------

    def vetor(self, ts: pd.Timestamp, bar: Bar, ops_hoje: int,
              max_ops: int, pnl_sessao_brl: float,
              risco_brl: float) -> list[float]:
        """As 33 features, na ordem de `NOMES`, todas em [-1, 1].

        `risco_brl` e' o tamanho em reais de UM stop -- e' o que torna
        `pnl_sessao` comparavel entre geometrias diferentes (perder um stop
        e' -1, com stop de 10 ou de 40 ticks)."""
        f = [0.0] * N_FEATURES
        escala = self.range_diario_mediano

        # ---- bloco destilado ------------------------------------------
        if self.faixa_pronta:
            hi, lo = self._faixa_hi, self._faixa_lo
            meio = (hi + lo) / 2.0
            semi = max((hi - lo) / 2.0, 1e-9)
            f[0] = _clip((bar.close - meio) / semi / 3.0)
            f[1] = _clip(_razao(hi - lo, escala))
            f[2] = 1.0 if lo <= bar.close <= hi else 0.0
        f[3] = min(self._rompeu_cima, 3) / 3.0
        f[4] = min(self._rompeu_baixo, 3) / 3.0

        agora = ts.value
        decorrido = 0.0
        if self._abertura_ts is not None:
            decorrido = agora - self._abertura_ts
            if self._fim_ts is not None:
                f[5] = _clip(_razao(decorrido, self._fim_ts - self._abertura_ts),
                             0.0, 1.0)

        media_vol_dia = _razao(self._soma_vol, self._n_barras)
        media_vol_curto = 0.0
        amp_curta = 0.0
        if self._curto:
            media_vol_curto = _razao(
                sum(float(b.volume or 0.0) for _, b in self._curto),
                len(self._curto))
            # /2: duas vezes a media do dia ja' satura em 1,0.
            f[6] = _clip(_razao(media_vol_curto, media_vol_dia) / 2.0, 0.0, 1.0)
            amp_curta = (max(b.high for _, b in self._curto)
                         - min(b.low for _, b in self._curto))

        amp_media = 0.0
        if self._medio:
            amp_media = (max(b.high for _, b in self._medio)
                         - min(b.low for _, b in self._medio))
            f[8] = _clip(_razao(amp_media, escala), 0.0, 1.0)
            primeiro = self._medio[0][1].open
            f[9] = _clip(_razao(bar.close - primeiro, amp_media))
            f[21] = _clip(_razao(bar.close - primeiro, escala))
            media_vol_medio = _razao(
                sum(float(b.volume or 0.0) for _, b in self._medio),
                len(self._medio))
            # Aceleracao: o fluxo dos ultimos 5min contra o dos ultimos
            # 15min. Diferente de `vol_rel` (que compara com o dia todo) --
            # este pega a virada de regime DENTRO da janela curta.
            f[7] = _clip(_razao(media_vol_curto, media_vol_medio) / 2.0,
                         0.0, 1.0)

        vwap = _razao(self._soma_pv, self._soma_v)
        if vwap:
            f[10] = _clip(_razao(bar.close - vwap, escala))
        if self._abertura_preco == self._abertura_preco:
            f[11] = _clip(_razao(bar.close - self._abertura_preco, escala))
            if self.fechamento_vespera is not None:
                f[12] = _clip(_razao(
                    self._abertura_preco - self.fechamento_vespera, escala))

        # Retangulo: mesmo criterio do `win_retangulo` (largura <= tolerancia
        # x escala), com a tolerancia de 20% que ja' passou por OOS congelado.
        if len(self._retang) >= 2 and escala:
            r_hi = max(b.high for _, b in self._retang)
            r_lo = min(b.low for _, b in self._retang)
            largura = r_hi - r_lo
            if 0 < largura <= RETANGULO_TOLERANCIA * escala:
                f[13] = 1.0
                f[14] = _clip((bar.close - (r_hi + r_lo) / 2.0)
                              / max(largura / 2.0, 1e-9))

        # Saturam em 3 stops: alem disso o dia ja' e' extremo, e a diferenca
        # entre -3 e -5 stops nao muda que decisao faz sentido.
        f[15] = _clip(_razao(pnl_sessao_brl, risco_brl) / 3.0)
        if max_ops > 0:
            f[16] = _clip(ops_hoje / float(max_ops), 0.0, 1.0)

        # ---- bloco cru --------------------------------------------------
        amp_barra = bar.high - bar.low
        if amp_barra > 0:
            f[17] = _clip((bar.close - bar.open) / amp_barra)
            f[18] = _clip((bar.high - max(bar.open, bar.close)) / amp_barra,
                          0.0, 1.0)
            f[19] = _clip((min(bar.open, bar.close) - bar.low) / amp_barra,
                          0.0, 1.0)
        if len(self._curto) >= 2:
            anterior = self._curto[-2][1].close
            f[20] = _clip(_razao(bar.close - anterior, escala) * 10.0)

        f[22] = _clip(self._seq / 5.0)
        if len(self._ret5) == 2:
            a, b = self._ret5[0], self._ret5[1]
            # Sinal do produto, com magnitude amortecida: +1 = os dois
            # movimentos na mesma direcao (continuidade), -1 = viraram.
            f[23] = _clip(math.copysign(
                min(1.0, abs(a * b) / max((escala or 1.0) ** 2 / 16.0, 1e-9)),
                a * b) if a * b != 0 else 0.0)

        if self._max_sessao is not None:
            f[24] = _clip(_razao(bar.close - self._max_sessao, escala))
        if self._min_sessao is not None:
            f[25] = _clip(_razao(bar.close - self._min_sessao, escala))
        if self._ts_extremo is not None and decorrido > 0:
            f[26] = _clip(_razao(agora - self._ts_extremo, decorrido), 0.0, 1.0)

        if len(self._medio) >= 3:
            vols = [float(b.volume or 0.0) for _, b in self._medio]
            m = sum(vols) / len(vols)
            if m > 0:
                dp = math.sqrt(sum((v - m) ** 2 for v in vols) / len(vols))
                f[27] = _clip(dp / m / 2.0, 0.0, 1.0)
        f[28] = _clip(_razao(amp_curta, amp_media), 0.0, 1.0)

        f[29] = ts.weekday() / 4.0 if ts.weekday() <= 4 else 1.0
        f[30] = ts.minute / 59.0
        resto = bar.close % GRADE_REDONDA_PONTOS
        dist = min(resto, GRADE_REDONDA_PONTOS - resto)
        f[31] = _clip(dist / (GRADE_REDONDA_PONTOS / 2.0), 0.0, 1.0)

        if len(self._medio) >= 4:
            fechs = [b.close for _, b in self._medio]
            rets = [fechs[i] - fechs[i - 1] for i in range(1, len(fechs))]
            m = sum(rets) / len(rets)
            dp = math.sqrt(sum((r - m) ** 2 for r in rets) / len(rets))
            if dp > 0:
                assim = sum(((r - m) / dp) ** 3 for r in rets) / len(rets)
                f[32] = _clip(assim / 3.0)
        return f


def vetor_nomeado(v: list[float]) -> dict[str, float]:
    """`{nome: valor}` -- so' para diagnostico e relatorio. O robo nunca usa
    isto no caminho quente."""
    return dict(zip(NOMES, v))
