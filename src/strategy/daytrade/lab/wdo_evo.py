"""WDO EVO -- o robo do WDO@ cuja politica de decisao e' EVOLUIDA, nao
escrita.

Este arquivo nao contem nenhuma hipotese de mercado. Ele contem o CORPO: como
uma decisao vira ordem, dentro do desenho de execucao fechado do projeto. O
cerebro sao 27 numeros (`strategy.daytrade.evo.genoma.Genoma`) que uma busca
evolutiva produz rodando este mesmo corpo milhares de vezes contra o motor de
producao.

A separacao importa: trocar o genoma nao muda uma linha de execucao, e mexer
na execucao invalida todos os genomas de uma vez (de forma visivel, porque o
relatorio carimba a premissa). E' a mesma disciplina que fez `live/` nao
decidir nada -- o robo que opera dinheiro e' literalmente a instancia que o
backtest rodou.

## Como uma barra vira ordem

    1. a barra que FECHOU entra no banco de features (17 numeros em [-1,1]);
    2. o genoma soma: `s_comprar = sum(w_c[i] * f[i])`, idem `s_vender`;
    3. age se o maior dos dois passa do limiar `theta`, e so' se a janela de
       operacao do genoma estiver aberta e o teto de operacoes do dia nao
       tiver estourado;
    4. a ordem sai como `EnterLimit` do lado FAVORAVEL do preco, com prazo,
       stop e alvo fixados, e a saida por alvo como ordem-limite real
       fatiada, sem prazo.

Nao ha nenhum caminho por onde uma decisao vire ordem a mercado. Ver a secao
"O desenho de execucao e' FECHADO" em CLAUDE.md -- a entrada a mercado nem
existe no motor (`EntradaAMercadoNaoSuportada`), e o alvo a mercado paga
R$55,00 de deslize contra R$95,00 de bruto teorico.

## O que este robo deliberadamente NAO faz

  * **nao implementa `initialize`.** Todo robo pode pre-computar indicador
    sobre o historico inteiro do backtest; este nao pode, e a ausencia do
    metodo e' a garantia. Uma busca evolutiva nao "comete o erro" de olhar
    o futuro -- ela CONVERGE para ele, porque olhar o futuro e' a melhor
    estrategia que existe. Sem `initialize`, o unico dado que chega ao robo
    e' a barra que acabou de fechar, pelo mesmo caminho do feed ao vivo;
  * **nao piramida.** Uma posicao por vez (o motor tambem nao piramida);
  * **nao dimensiona pelo caixa.** Sempre 1 contrato. O capital de partida
    deste projeto e' R$500 contra margem de R$150 -- escalar contrato aqui
    seria reabrir exatamente a exposicao agregada que zerou a conta em
    2026-08-28. `quantity_e_unidade=False`, entao a escada de risco do
    sistema funciona so' como TETO;
  * **nao muda de ideia com posicao aberta**, exceto pelo corte do relogio.

## Janela de pregao

Nao esta aqui. `config_for(profile_for("WDO@"))` traz 12:00-21:30 UTC
(09:00-18:30 BRT) com achatamento as 21:25, e e' o MESMO montador que
`scripts/run_live.py` usa para subir o robo sombra. O genoma so' escolhe um
pedaco de dentro dessa janela (`hora_ini`/`hora_fim`). Reimplementar horario
aqui criaria a divergencia classica: robo validado diferente do robo que
opera.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.daytrade.base import (
    AdjustTarget, Bar, EnterLimit, IntradayAction, IntradayOpenPosition,
    IntradayStrategy, JanelaVolatilidadeDiaria, Side, no_tick,
)
from strategy.daytrade.evo.features import BancoDeFeatures
from strategy.daytrade.evo.genoma import ALVO_MINIMO_PONTOS, Genoma

#: `exit_ttl_bars` que significa "sem prazo" sem ser `None`. Repetido do
#: `wdo_orb` pelo mesmo motivo que la': `None` NAO e' sem prazo, e' o
#: comportamento antigo de backtest (preenchimento guiado por volume, sem
#: ordem real). Quem opera fatia de alvo com dinheiro de verdade tem de
#: declarar um numero.
EXIT_TTL_BARS_SEM_PRAZO = 10 ** 9

#: Duracao nominal da sessao do WDO@ em minutos (09:00 -> 18:30 BRT). Usada
#: so' para normalizar a feature `hora` em [0,1]. Constante e nao lida do
#: perfil porque `strategy/` nao importa `backtest/` (AGENTS.md); entra pelo
#: construtor quem quiser outra.
MINUTOS_DE_SESSAO = 570.0


@dataclass
class WdoEvo(IntradayStrategy):
    """O corpo. `genoma` e' o cerebro; `feed_kind` diz em que base ele roda.

    `barras_por_minuto` existe porque o genoma pensa o prazo da ordem em
    MINUTOS e o motor conta BARRAS. Em M1 o fator e' 1; em tick a base do
    WDO@ mede mediana de 336 barras por minuto. Traduzir aqui, uma vez, e' o
    que permite o MESMO genoma rodar nas duas bases sem virar outro robo --
    o `wdo_orb` carrega `entrada_ttl_bars=5000` justamente por nao ter essa
    traducao, e o numero so' faz sentido em tick."""

    genoma: Genoma = None  # type: ignore[assignment]

    name: str = "wdo_evo"
    version: str = "0.1.0"
    symbol: str = "WDO@"
    target_fills_as_maker: bool = True
    anchor_exits_at_fill: bool = True
    is_futuro: bool = True
    feed_kind: str = "m1"
    quantity_e_unidade: bool = False

    tick_size: float = 0.5
    quantity: int = 1
    barras_por_minuto: float = 1.0
    minutos_de_sessao: float = MINUTOS_DE_SESSAO
    #: Janela do range diario mediano que escala quase toda feature. 20 dias
    #: e' o mesmo numero que `Gremah`/`GremahTick` ja usam.
    vol_janela_dias: int = 20
    #: Primeiros minutos do pregao em que o robo so' OLHA (mede a faixa de
    #: abertura e nao decide nada). Nao entra no genoma: e' o que DEFINE a
    #: feature `pos_faixa`, e deixar a busca mover a definicao da feature ao
    #: mesmo tempo que o peso dela torna o resultado ilegivel.
    range_minutos: float = 15.0
    #: Valor do ponto em reais -- so' para converter o stop em risco de R$ na
    #: feature `pnl_sessao`. WDO@: R$10,00 por ponto, 0,5 por tick -> R$5,00.
    valor_do_ponto_brl: float = 10.0

    _banco: BancoDeFeatures = field(init=False, repr=False, default=None)
    _vol: JanelaVolatilidadeDiaria = field(init=False, repr=False, default=None)
    _ops_hoje: int = field(default=0, init=False, repr=False)
    _pendente: bool = field(default=False, init=False, repr=False)
    _tinha_posicao: bool = field(default=False, init=False, repr=False)
    _corte_posto: bool = field(default=False, init=False, repr=False)
    _abertura_ts: pd.Timestamp | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.genoma is None:
            raise ValueError(
                "WdoEvo precisa de um `genoma` -- o corpo nao tem politica "
                "propria de proposito. Use `genoma.semear_do_orb()` para um "
                "ponto de partida conhecido.")
        self._vol = JanelaVolatilidadeDiaria(self.vol_janela_dias)
        self._banco = BancoDeFeatures(range_minutos=self.range_minutos)

    # -- ciclo de vida -------------------------------------------------------

    def on_session_start(self, session_date) -> None:
        self._ops_hoje = 0
        self._pendente = False
        self._tinha_posicao = False
        self._corte_posto = False
        self._abertura_ts = None
        self._banco.iniciar_sessao()
        self._banco.range_diario_mediano = self._vol.range_mediano()

    def seed_daily_volatility(self, previous_daily_bars: list[Bar]) -> None:
        """Recebe as barras DIARIAS das sessoes ANTERIORES (nunca a de hoje
        -- olhar o proprio dia seria look-ahead, e quem garante isso e' o
        motor). Guarda duas coisas: a escala (range mediano) e o fechamento
        da vespera, que e' o outro lado da feature `gap_abertura`."""
        for b in previous_daily_bars:
            self._vol.registrar_dia(b)
        self._banco.range_diario_mediano = self._vol.range_mediano()
        if previous_daily_bars:
            self._banco.fechamento_vespera = previous_daily_bars[-1].close

    def on_order_expired(self, ts: pd.Timestamp) -> None:
        """A ordem de entrada morreu de prazo sem preencher. Liberar o robo
        para decidir de novo vale +81% de liquido no `wdo_orb` -- sem isto
        ele fica esperando por uma ordem que nao existe mais."""
        self._pendente = False

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        self._pendente = False

    # -- decisao -------------------------------------------------------------

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        if self._abertura_ts is None:
            self._abertura_ts = ts
            self._banco.iniciar_sessao(
                fim_ts=ts + pd.Timedelta(minutes=self.minutos_de_sessao))
            self._banco.range_diario_mediano = self._vol.range_mediano()
        self._banco.registrar(ts, bar)

        g = self.genoma.geometria

        # --- posicao aberta: so' o relogio decide -----------------------
        if positions:
            if not self._tinha_posicao:
                self._tinha_posicao = True
                self._ops_hoje += 1
                self._pendente = False
                self._corte_posto = False
            pos = positions[0]
            if not self._corte_posto:
                if (ts - pos.entry_ts) >= pd.Timedelta(minutes=g["corte_min"]):
                    self._corte_posto = True
                    return [AdjustTarget(self._alvo_do_corte(pos, bar))]
            return []
        self._tinha_posicao = False
        self._corte_posto = False

        # --- sem posicao: arma (ou nao) a entrada -----------------------
        if self._pendente or self._ops_hoje >= g["max_ops_dia"]:
            return []
        if not self._banco.faixa_pronta:
            return []

        risco_brl = (g["stop_ticks"] * self.tick_size
                     * self.valor_do_ponto_brl)
        f = self._banco.vetor(ts, bar, self._ops_hoje, g["max_ops_dia"],
                              session_pnl_brl, risco_brl)

        hora = f[5]
        if not (g["hora_ini"] <= hora <= g["hora_fim"]):
            return []

        # Os SOMADORES constroem o score; as PORTAS o zeram. A ordem nao
        # importa (multiplicar por 0 comuta), e por isso os dois lacos sao
        # separados: uma porta avaliada no meio da soma dependeria da ordem
        # dos encaixes no genoma, e o cruzamento reordena encaixes o tempo
        # todo -- dois pais equivalentes gerariam filhos diferentes por um
        # motivo que nao e' genetico.
        s_comprar = 0.0
        s_vender = 0.0
        for e in self.genoma.encaixes:
            if not e.porta:
                s_comprar += e.a * f[e.idx]
                s_vender += e.b * f[e.idx]
        for e in self.genoma.encaixes:
            if e.porta and not e.aplica(f[e.idx]):
                return []

        theta = self.genoma.theta
        if max(s_comprar, s_vender) < theta:
            return []
        side: Side = "long" if s_comprar >= s_vender else "short"

        self._pendente = True
        return [self._ordem(side, bar.close, g)]

    # -- auxiliar (puro) -----------------------------------------------------

    def _alvo_do_corte(self, pos: IntradayOpenPosition, bar: Bar) -> float:
        """Onde o corte do relogio pendura o alvo novo.

        O mecanismo e' o do `wdo_orb`: desistir do alvo cheio e pendurar uma
        ordem-limite NO preco corrente, sem atravessar o livro -- continua
        sendo ordem parada de verdade, e o motor cancela a fatia do alvo
        antigo para armar outra no nivel novo, com fila CHEIA, que e' o que a
        corretora faz.

        A diferenca esta' no PISO, e ele existe por ordem do dono
        (2026-09-18, `ALVO_MINIMO_PONTOS`): o corte nunca pode pousar dentro
        da faixa de 3 pontos em torno da entrada. Sem esse piso o corte do
        relogio vira uma porta dos fundos para a geometria proibida -- um
        genoma com `corte_min` curto faturaria 1 ponto por operacao e a
        tabela mostraria win% alto, quando na pratica aquele ganho e' do
        tamanho do escorregao de preco que o produziu. Com o piso, o corte
        so' pode ABRIR MAO de um alvo grande por um menor-porem-legitimo;
        enquanto o preco estiver dentro da faixa, a limite fica esperando na
        borda dela (e a posicao sai pelo stop ou pelo achatamento, que e' o
        desfecho honesto)."""
        sinal = 1.0 if pos.side == "long" else -1.0
        piso = pos.entry_price + sinal * ALVO_MINIMO_PONTOS
        alvo = max(bar.close, piso) if sinal > 0 else min(bar.close, piso)
        return no_tick(alvo, self.tick_size)

    def _ordem(self, side: Side, preco: float, g: dict) -> EnterLimit:
        """A ordem, ja' na grade do instrumento e ja' do lado favoravel.

        `offset_ticks >= 1` vem do genoma (o espaco nao representa zero),
        entao a limite NUNCA nasce atravessando o livro. Compra fica ABAIXO
        do preco corrente, venda ACIMA -- e' o que faz dela uma ordem maker
        de verdade, que e' o unico desenho de entrada permitido no projeto."""
        sinal = 1.0 if side == "long" else -1.0
        offset = g["offset_ticks"] * self.tick_size
        limite = no_tick(preco - sinal * offset, self.tick_size)
        return EnterLimit(
            side=side,
            limit_price=limite,
            initial_stop=no_tick(limite - sinal * g["stop_ticks"]
                                 * self.tick_size, self.tick_size),
            initial_target=no_tick(limite + sinal * g["alvo_ticks"]
                                   * self.tick_size, self.tick_size),
            quantity=self.quantity,
            ttl_bars=max(1, int(round(g["ttl_min"] * self.barras_por_minuto))),
            exit_split_unit=1,
            exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO,
            reason=f"evo_{side}",
        )
