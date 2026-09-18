"""`wdo_retangulo` -- lateralizacao/retangulo NATIVA para o WDO@ (mini-dolar).

## Genealogia: o que veio do WIN por REFERENCIA de METODO, e o que foi
## recalibrado com dado do PROPRIO WDO (2026-09-16)

Ponto de partida (nao copia literal): a pesquisa da lateralizacao "retangulo"
do dono no WIN@ (`scripts/daytrade/copawin_retangulo_lateral_2026_09_15.py`,
`..._estrategias_2026_09_15.py`, `..._oos_congelado_2026_09_15.py`) e o robo
`WinRetangulo` (`strategy/daytrade/lab/win_retangulo.py`), hoje em
producao/sombra no WIN@.

| o que                          | HERDADO do WIN (adimensional, portavel)        | RECALIBRADO no WDO |
|---------------------------------|-------------------------------------------------|---------------------|
| detector geometrico              | topo=q90(high) / piso=q10(low), TOL=8% da largura, >=2 visitas/borda, espalhamento>=W/3, >=2 trocas de lado, >=3 cruzamentos do meio, contencao>=95%, contracao<=55%, deriva<=25% | -- (fracoes, portaveis) |
| geometria de entrada (D1 centro) | limite so' descansa se o preco JA cruzou o meio (repique de volta); alvo = meio +/- 0,80xL; stop = meio -/+ 0,50xL | -- (ponto de PARTIDA herdado, nao re-otimizado nesta rodada -- ver nota abaixo) |
| morte do retangulo                | 3 fechamentos seguidos alem de 25% da largura   | -- |
| piso ESTRUTURAL de largura        | mesma FORMULA (4x o pedagio de execucao em ticks) | numero proprio: 4,4 ticks / 2,2 pontos (WIN: 6,0 ticks / 30 pontos) -- ver `LARGURA_MINIMA_TICKS` |
| piso EMPIRICO de largura (filtro do candidato) | mesmo METODO (terco superior da largura medida NO IS) | numero proprio, medido em `scripts/daytrade/wdo_retangulo_calibracao_is_oos_2026_09_16.py` -- NAO e' 328 pontos do WIN (outro instrumento, outra escala de preco) |
| execucao do alvo                  | entrada por `EnterLimit`, alvo NUNCA a mercado | WDO tem FILA REAL calibrada (`backtest.intraday.fidelidade`, 329/494 Kaplan-Meier) e deslize medido do TP nativo (`DESLIZE_ALVO_NATIVO_TICKS=1,0`). Por isso o alvo AQUI sai `exit_split_unit` + `exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO` -- o mesmo desenho de `wdo_orb` (a outra estrategia desta familia com fila calibrada), NAO o do `win_retangulo` (que nao precisa: WIN@ nao tem fidelidade medida, roda com fila zero) |
| dimensionamento                   | escada por caixa (`escala_por_caixa`)          | NAO PORTADO -- 1 contrato FIXO, de proposito: isola a GEOMETRIA do portao de capital, e R$375 (o minimo real do WDO@) ja E' exatamente o piso de 1 contrato -- escalar e' pergunta seguinte, nao esta |

## Por que a geometria de entrada e' a mesma (0,80xL / 0,50xL)

E' o ponto de PARTIDA herdado, nao uma verdade importada sem checagem: a
grade 7x6 medida no WIN foi um PLATO (39-40 de 42 celulas positivas nas duas
janelas: IS e OOS), entao o par congelado e' uma escolha robusta, nao um pico
fragil que so' vale no instrumento onde nasceu. Recalibrar a geometria de
alvo/stop para o WDO com o MESMO metodo (matriz de trajetoria, offline) e'
trabalho FUTURO, fora do escopo desta rodada -- o que esta rodada mede e' se
o DETECTOR + a geometria herdada sobrevivem no WDO com a fila REAL cobrada,
que e' exatamente a pergunta que decidiu o veredito do WDO F1 maker e do
`wdo_orb` antes deste robo (ver a secao "A base de fidelidade de execucao" do
`CLAUDE.md`).

## Execucao -- desenho FECHADO, sem excecao (CLAUDE.md)

Entrada por `EnterLimit` com prazo (`entrada_ttl_bars` -- sem prazo ela espera
o pregao inteiro e preenche horas depois do sinal, medido 269,7 min num robo
irmao). Alvo como ordem-limite real FATIADA (`exit_split_unit=1`), SEM prazo
(`exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO`, nunca `None`) -- por construcao isso
faz o deslize do TP nativo (medido, 57,9% do bruto teorico) sumir: a saida
fatiada nunca passa pelo caminho que cobra `target_slippage_ticks`. So' o
STOP e' a mercado (excecao unica do desenho fechado).
`anchor_exits_at_fill=True`: alvo e stop transladam para o preco REALMENTE
preenchido, preservando a distancia original.

## Nada de nivel de preco atravessa o pregao

`WDO@` e' serie continua com emenda de rolagem (medido 2026-09-16: ~37 a ~42
pontos de deslocamento no reencadeamento) -- a unica defesa estrutural e'
nunca deixar um nivel de preco cruzar a sessao. `on_session_start` zera tudo.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import (
    Bar, EnterLimit, IntradayAction, IntradayOpenPosition, IntradayStrategy,
    no_tick,
)

#: Prazo (barras M1) que a saida por alvo fica parada no livro sem cancelar --
#: mesma constante/mesmo motivo de `wdo_orb.EXIT_TTL_BARS_SEM_PRAZO` e
#: `wdo_grid_reload_maker.EXIT_TTL_BARS_SEM_PRAZO` (ordem do dono, 2026-09-09):
#: a limite do alvo espera o mercado PAGAR, nunca sai a mercado por
#: impaciencia. Repetida aqui (em vez de importada de la) porque `strategy/`
#: so' pode importar `core/` (AGENTS.md regra 1) -- as tres classes concordam
#: no VALOR, nao no import.
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

#: Tolerancia de toque nas bordas, fracao da largura -- HERDADA do WIN
#: (`copawin_retangulo_lateral_2026_09_15.TOL`), adimensional e portavel. NAO
#: recalibrada nesta rodada: e' fracao, nao numero absoluto, e o pedido era
#: recalibrar so' os FILTROS ABSOLUTOS (piso de largura) nos tercis do WDO.
TOLERANCIA_BORDA = 0.08
#: Toques minimos por borda antes de colapsar em visitas.
TOQUES_MINIMOS = 2
#: VISITAS por borda -- barras consecutivas encostadas colapsam em uma so'.
VISITAS_MINIMAS = 2
#: "Passa o meio e depois volta passando o meio no sentido contrario."
CRUZAMENTOS_MINIMOS = 3
#: Fracao dos fechamentos que tem de estar DENTRO da banda.
CONTENCAO_MINIMA = 0.95
#: O retangulo tem de ser estreito perto do movimento que veio antes dele.
CONTRACAO_MAXIMA = 0.55
#: Primeiro e ultimo toque de cada borda separados por >= W/3 barras.
ESPALHAMENTO_MINIMO = 1 / 3
#: Inclinacao maxima: deriva do primeiro ao ultimo terco, fracao da largura.
DERIVA_MAXIMA = 0.25

#: Piso ESTRUTURAL de largura, em ticks do PROPRIO instrumento -- mesma
#: FORMULA usada (retroativamente reconstruida) no `win_retangulo.
#: LARGURA_MINIMA_TICKS = 6.0`, aplicada aqui com os numeros do WDO@:
#:
#:     pedagio_ticks = fee_round_trip_brl / (point_value_brl x tick_size)
#:                     + slippage_ticks_do_stop
#:     piso_ticks    = 4 x pedagio_ticks
#:
#: WIN@: fee R$0,50 / (R$0,20/pt x 5,0pt/tick) = 0,50 tick de corretagem +
#: 1,0 tick de deslize do stop (`IntradayCostModel.slippage_ticks`, default) =
#: 1,50 tick de pedagio -> piso 4 x 1,50 = 6,00 ticks. Bate EXATO com o numero
#: congelado em `win_retangulo.py` -- o que valida a formula antes de
#: aplica-la a um instrumento novo, em vez de so' herdar o numero dele.
#:
#: WDO@: fee R$0,50 / (R$10,00/pt x 0,5pt/tick) = 0,10 tick de corretagem +
#: 1,0 tick de deslize do stop = 1,10 tick de pedagio -> piso 4 x 1,10 =
#: 4,40 ticks (2,20 pontos). `fee_round_trip_brl` (`FUTURES_FEE_ROUND_TRIP_
#: BRL`) e `slippage_ticks` moram em `backtest.intraday.profiles`/`costs`
#: (camada `backtest`, que `strategy/` nao pode importar -- AGENTS.md regra
#: 1) -- por isso o numero e' HARDCODED aqui, com a conta registrada em texto
#: em vez de escondida atras de um import que nao pode existir.
LARGURA_MINIMA_TICKS = 4.4

#: Morte do retangulo: N fechamentos CONSECUTIVOS alem de M x largura da
#: borda -- mesmo criterio TOLERANTE do WIN (matar no 1o fechamento fora
#: media vida de minutos, artefato do criterio, nao medida do mercado).
MARGEM_MORTE = 0.25
BARRAS_MORTE = 3


def detecta_retangulo(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    amplitude_anterior: float | None = None,
    tolerancia: float = TOLERANCIA_BORDA,
) -> dict | None:
    """O retangulo desta janela, ou `None` se ela nao qualifica.

    Pura: arrays de OHLC entram, dicionario sai -- nenhuma I/O, nenhum
    estado, nenhuma dependencia de simbolo (regra 1 do `AGENTS.md`: e' o que
    permite portar para MQL5). Identica, criterio a criterio, a
    `win_retangulo.detecta_retangulo` -- e' a parte ADIMENSIONAL herdada por
    metodo, nao os numeros absolutos.

    `amplitude_anterior` e' a amplitude das 2W barras ANTERIORES a' janela e
    serve so' ao teste de CONTRACAO. `None` (comeco do pregao, sem historico
    suficiente) pula o teste -- fica marcado em `contracao` como NaN, nunca
    escondido atras de um default que faria o criterio passar calado."""
    topo = float(np.quantile(high, 0.90))
    piso = float(np.quantile(low, 0.10))
    largura = topo - piso
    if largura <= 0:
        return None
    meio = (topo + piso) / 2.0
    zona = tolerancia * largura

    lados: list[int] = []
    pos_topo: list[int] = []
    pos_piso: list[int] = []
    for i, (h, lo) in enumerate(zip(high, low)):
        if h >= topo - zona:
            lados.append(1)
            pos_topo.append(i)
        elif lo <= piso + zona:
            lados.append(-1)
            pos_piso.append(i)
    if len(pos_topo) < TOQUES_MINIMOS or len(pos_piso) < TOQUES_MINIMOS:
        return None

    def _visitas(pos: list[int]) -> int:
        return 1 + sum(1 for a, b in zip(pos, pos[1:]) if b - a > 1)

    visitas_topo, visitas_piso = _visitas(pos_topo), _visitas(pos_piso)
    if visitas_topo < VISITAS_MINIMAS or visitas_piso < VISITAS_MINIMAS:
        return None

    minimo = ESPALHAMENTO_MINIMO * len(close)
    if (pos_topo[-1] - pos_topo[0]) < minimo or (pos_piso[-1] - pos_piso[0]) < minimo:
        return None

    trocas = sum(1 for a, b in zip(lados, lados[1:]) if a != b)
    if trocas < 2:
        return None

    acima = close > meio
    cruzamentos = int(np.sum(acima[1:] != acima[:-1]))
    if cruzamentos < CRUZAMENTOS_MINIMOS:
        return None

    contencao = float(np.mean((close >= piso) & (close <= topo)))
    if contencao < CONTENCAO_MINIMA:
        return None

    n = len(close)
    primeiro = float(np.mean(close[: n // 3]))
    ultimo = float(np.mean(close[-(n // 3):]))
    if abs(ultimo - primeiro) > DERIVA_MAXIMA * largura:
        return None

    contracao = float("nan")
    if amplitude_anterior is not None and amplitude_anterior > 0:
        contracao = largura / amplitude_anterior
        if contracao > CONTRACAO_MAXIMA:
            return None

    return dict(
        topo=topo, piso=piso, largura=largura, meio=meio, contracao=contracao,
        visitas_topo=visitas_topo, visitas_piso=visitas_piso,
        toques_topo=len(pos_topo), toques_piso=len(pos_piso), trocas=trocas,
        cruzamentos=cruzamentos, contencao=contencao,
        deriva_frac=abs(ultimo - primeiro) / largura,
    )


class WdoRetangulo(IntradayStrategy):
    """Entra por ordem-limite no MEIO de um retangulo (D1, "centro" -- ver a
    genealogia no topo do modulo), mirando ALEM da borda oposta, no WDO@."""

    name = "wdo_retangulo"
    version = "0.1.0"
    symbol = "WDO@"
    is_futuro = True
    #: O alvo e' ordem-limite REAL, fatiada e sem prazo -- nunca `tp` nativo.
    target_fills_as_maker = True
    #: A entrada e' limite, entao a ancora de saida no preco realmente obtido
    #: vale de verdade aqui (em robo que entra a mercado ela e' no-op
    #: silencioso -- item 4.23 de `LICOES_DE_PRODUCAO.md`).
    anchor_exits_at_fill = True
    feed_kind = "m1"

    def __init__(
        self,
        symbol: str | None = None,
        janela_barras: int = 20,
        largura_minima_pontos: float = 0.0,
        alvo_fracao_largura: float = 0.80,
        stop_fracao_largura: float = 0.50,
        ttl_barras: int = 10,
        quantidade: int = 1,
        tolerancia_borda: float = TOLERANCIA_BORDA,
    ) -> None:
        """`largura_minima_pontos=0.0` (sem filtro empirico) e' o default
        PURO desta classe de proposito: o numero calibrado no WDO IS (o
        equivalente ao `328.0` do `win_retangulo`, medido no proprio WDO em
        `scripts/daytrade/wdo_retangulo_calibracao_is_oos_2026_09_16.py`) e'
        passado EXPLICITO por quem monta o candidato, em vez de hardcoded
        aqui como se fosse verdade da classe -- esta estrategia ainda nao foi
        promovida a produção (nao esta no `registry`), entao carregar um
        numero medido numa unica rodada de pesquisa como default seria
        emprestar confianca que a promocao ainda nao ganhou.

        `janela_barras=20` -- o mesmo ponto de partida do `win_retangulo`
        (a escolha mais validada da linha WIN: deteccao precoce com ganho
        1,78x sobre o nulo, 8 barras de antecedencia). O calibrador testa
        tambem W=30 (o congelado ORIGINAL do WIN) para contexto.

        `alvo_fracao_largura=0.80` / `stop_fracao_largura=0.50` -- HERDADOS
        do candidato congelado do WIN (equivalente a `alvo_frac=1.6` na
        parametrizacao "a partir do meio" de `copawin_retangulo_
        estrategias_2026_09_15.py`), nao re-otimizados nesta rodada -- ver a
        secao do modulo.

        `ttl_barras=10` obrigatorio e positivo: uma limite de entrada sem
        prazo espera ate' o fim do pregao e preenche horas depois do sinal
        (medido: 269,7 min) -- nao e' o trade que a estrategia pediu."""
        if janela_barras < 6:
            raise ValueError(
                f"janela_barras={janela_barras} e' curto demais: o "
                f"espalhamento exige W/3 barras entre a primeira e a ultima "
                f"visita de cada borda"
            )
        if alvo_fracao_largura <= 0 or stop_fracao_largura <= 0:
            raise ValueError("alvo e stop tem de ser distancias positivas")
        if ttl_barras is None or ttl_barras <= 0:
            raise ValueError(
                "ttl_barras e' obrigatorio: limite de entrada sem prazo vira "
                "ordem esquecida no livro (medido: fill 269,7 min depois do sinal)"
            )
        if not 0 < tolerancia_borda < 0.5:
            raise ValueError(
                f"tolerancia_borda={tolerancia_borda} fora de (0; 0,5): acima "
                f"de 0,5 as duas bordas se encontram no meio"
            )
        if symbol is not None:
            self.symbol = symbol
        self.janela_barras = int(janela_barras)
        self.largura_minima_pontos = float(largura_minima_pontos)
        self.alvo_fracao_largura = float(alvo_fracao_largura)
        self.stop_fracao_largura = float(stop_fracao_largura)
        self.ttl_barras = int(ttl_barras)
        self.quantidade = int(quantidade)
        self.tolerancia_borda = float(tolerancia_borda)
        economia = economics_for(self.symbol)
        self.tick_size = economia.price_tick_size
        self.valor_do_ponto_brl = economia.point_value_brl
        self._reset_sessao()

    # -- estado --------------------------------------------------------
    def _reset_sessao(self) -> None:
        # 3xW barras: W para a janela do detector, 2W para a amplitude
        # anterior que o teste de CONTRACAO consome.
        self._hist: deque[Bar] = deque(maxlen=3 * self.janela_barras + 2)
        self._retangulo: dict | None = None
        self._fora_seguidas = 0
        self._barras_esperando: int | None = None

    def on_session_start(self, session_date) -> None:
        """Zera TUDO. Nenhum nivel de preco atravessa a virada -- ver a
        docstring do modulo sobre a emenda de rolagem do `WDO@`."""
        self._reset_sessao()

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """A ordem morreu por teto/capital sem abrir posicao -- sem isto o
        robo acharia para sempre que ainda tem ordem viva e travaria pelo
        resto da sessao (mesmo achado de `WdoGridReloadMaker`, item 3.x de
        `LICOES_DE_PRODUCAO.md`)."""
        self._barras_esperando = None

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        """A limite de entrada estourou o prazo e o motor ja' a cancelou --
        irmao de `on_order_rejected`, mesmo motivo (item 4.25 de
        `LICOES_DE_PRODUCAO.md`)."""
        self._barras_esperando = None

    # -- deteccao --------------------------------------------------------
    def _janelas(self):
        W = self.janela_barras
        h = list(self._hist)
        recente = h[-W:]
        anterior = h[-3 * W:-W]
        return (
            np.array([b.high for b in recente], dtype=float),
            np.array([b.low for b in recente], dtype=float),
            np.array([b.close for b in recente], dtype=float),
            float(max(b.high for b in anterior) - min(b.low for b in anterior)),
        )

    def _tenta_detectar(self) -> None:
        if len(self._hist) < 3 * self.janela_barras:
            return
        high, low, close, amplitude_anterior = self._janelas()
        ret = detecta_retangulo(high, low, close, amplitude_anterior,
                                tolerancia=self.tolerancia_borda)
        if ret is None:
            return
        if ret["largura"] < LARGURA_MINIMA_TICKS * self.tick_size:
            return
        if ret["largura"] < self.largura_minima_pontos:
            return
        self._retangulo = ret
        self._fora_seguidas = 0

    def _morreu(self, bar: Bar) -> bool:
        r = self._retangulo
        margem = MARGEM_MORTE * r["largura"]
        if bar.close > r["topo"] + margem or bar.close < r["piso"] - margem:
            self._fora_seguidas += 1
            return self._fora_seguidas >= BARRAS_MORTE
        self._fora_seguidas = 0
        return False

    # -- loop --------------------------------------------------------------
    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        self._hist.append(bar)

        if self._retangulo is not None and self._morreu(bar):
            self._retangulo = None
            self._barras_esperando = None
        if self._retangulo is None:
            self._tenta_detectar()
            if self._retangulo is None:
                return []

        # Posicao aberta: o motor cuida de stop e alvo -- este robo nao gere
        # posicao (mesma decisao do `win_retangulo`: 24 regras de gestao
        # testadas no `copa_win`, todas negativas).
        if positions:
            self._barras_esperando = None
            return []

        # Ordem ja parada no livro, dentro do prazo: nao rearma por cima.
        if self._barras_esperando is not None:
            self._barras_esperando += 1
            if self._barras_esperando < self.ttl_barras:
                return []
            self._barras_esperando = None

        r = self._retangulo
        meio, largura = r["meio"], r["largura"]
        # D1 "centro": a limite so' descansa se o preco JA CRUZOU o meio --
        # uma limite de VENDA so' descansa ACIMA do preco corrente, uma de
        # COMPRA, ABAIXO (desenho de execucao fechado, CLAUDE.md). Isso
        # captura o REPIQUE de volta ao meio, mirando a borda oposta.
        if bar.close < meio:
            lado = "short"
            alvo = meio - self.alvo_fracao_largura * largura
            stop = meio + self.stop_fracao_largura * largura
        elif bar.close > meio:
            lado = "long"
            alvo = meio + self.alvo_fracao_largura * largura
            stop = meio - self.stop_fracao_largura * largura
        else:
            # Fechou exatamente no meio: nao ha lado em que a limite descanse.
            return []

        # Conferencia MECANICA: depois do arredondamento ao tick a limite
        # pode cair em cima do preco -- uma limite do lado errado e' ordem a
        # mercado disfarcada, que o desenho de execucao deste projeto proibe.
        limite = no_tick(meio, self.tick_size)
        if lado == "short" and limite <= bar.close:
            return []
        if lado == "long" and limite >= bar.close:
            return []

        self._barras_esperando = 0
        return [EnterLimit(
            side=lado,
            limit_price=limite,
            initial_stop=no_tick(stop, self.tick_size),
            initial_target=no_tick(alvo, self.tick_size),
            quantity=self.quantidade,
            ttl_bars=self.ttl_barras,
            # Alvo SEMPRE ordem-limite real fatiada, sem prazo -- o que faz o
            # deslize do TP nativo (medido, 57,9% do bruto) e a fila cobrada
            # no toque (medida, 329/494) serem o unico custo do alvo, em vez
            # de tambem pagar o gatilho a mercado. Mesmo desenho de `wdo_orb`.
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=f"retangulo_W{self.janela_barras}_L{largura:.1f}",
        )]
