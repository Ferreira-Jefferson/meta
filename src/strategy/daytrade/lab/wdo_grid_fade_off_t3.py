"""WDO F1 grid maker -- variante `combo_T3`, 2026-09-11: filtro de regime de
TENDENCIA (`fade_off`, escala 20min) + alvo maior (T3 em vez de T2, mantendo
S16). Formaliza como estrategia REAL (arquivo proprio, registravel) o
candidato medido em `scripts/daytrade/wdof1_regime_alvo_combinado_2026_09_11.py`
sobre 19 pregoes reais de tick -- NAO edita `wdo_grid_reload_maker.py` (arquivo
de producao) nem herda comportamento por copia: e' uma SUBCLASSE que so'
sobrescreve `_next_side_to_arm`/`on_bar`/`on_session_start`, tudo o mais
(reprecificacao, histerese, capital dinamico, fatia de saida, fila) e' herdado
sem mudanca nenhuma da classe base.

O QUE MOTIVOU (ver `wdof1_regime_medio_prazo_2026_09_11.py` e
`wdof1_regime_alvo_combinado_2026_09_11.py` para o experimento completo):
7 hipoteses de sinal de timing em janela de SEGUNDOS falharam contra as
perdas reais de 2026-09-11 -- todas as perdas eram o MESMO padrao (SELL
fadando uma alta sustentada de dezenas de minutos, ou o espelho). A escala
que faltava era 5-20 minutos, nao segundos nem o dia inteiro.

MECANICA DO FILTRO `fade_off` (identica ao mixin `RegimeReloadVariant` do
script de origem, reimplementada aqui SELF-CONTAINED em vez de importada de
`scripts/` -- uma estrategia de producao nao importa modulo de laboratorio):
a cada nova entrada (apos um fechamento, nunca cancela uma ordem ja pendente),
calcula o retorno dos ultimos `JANELA_REGIME_MINUTOS` minutos em TICKS a
partir da propria serie de precos que o robo ja recebe em `on_bar` (deque
`(ts, close)`, mesmo espirito de `strategy.daytrade.base.RollingVolumeWindow`
-- nenhum dado novo e' buscado, nenhuma I/O nova existe: `strategy/` continua
so' decidindo a partir do que o motor entrega barra a barra). Se o retorno
ultrapassar `LIMIAR_REGIME_TICKS` para cima, o lado SHORT (que fadaria a alta)
e' removido dos candidatos desta rodada; se ultrapassar para baixo, o lado
LONG e' removido. Regime neutro ou lado unico restante -> alternancia normal
(a mecanica de sempre).

DECISAO DE DESENHO que NAO estava especificada e teve de ser tomada aqui: o
script de origem calculava o regime a partir de M1 buscado SEPARADAMENTE do
MT5 (`market_data_intraday.mt5_source.fetch_m1_range`) e injetava um
`RegimeLookup` (callable) via kwarg do construtor -- viavel num script de
laboratorio com acesso direto ao terminal, mas exigiria um mecanismo NOVO de
segunda fonte de dado (M1 paralelo ao feed tick que este robo realmente usa)
para rodar em backtest/sombra/produção, o que violaria a regra de `strategy/`
so' importar `core` e nao fazer I/O propria. Este arquivo evita esse
mecanismo novo computando o retorno de 20min diretamente da serie de precos
que a propria estrategia ja recebe em `on_bar` (`feed_kind="tick"`, herdado
de `WdoGridReloadMaker`) -- mesmo padrao ja usado por `RollingVolumeWindow`/
`JanelaVolatilidadeDiaria` em `strategy/daytrade/base.py` (janela ROLANTE
construida so' com o que a propria chamada de `on_bar` ja trouxe). E'
conceitualmente a MESMA grandeza (retorno acumulado nos ultimos 20 minutos),
so' amostrada em tick em vez de M1 -- mais fina, nao mais grosseira -- e sem
exigir nenhum hook novo em `backtest/intraday/engine.py` nem em
`live/intraday_runtime.py`. O LIMIAR (8,11 ticks) continua sendo o mesmo
numero calibrado no experimento original (ver abaixo) porque e' a mesma
pergunta ("quanto de retorno em 20min conta como tendencia forte, medido
fora da amostra de teste"); a fonte da SERIE mudou, o LIMIAR nao.

LIMIAR: 8,11 ticks -- percentil 70 de |retorno M1 acumulado em 20 minutos|,
calibrado em 25.437 barras M1 de WDO@ entre 2026-06-15 e 2026-08-14 (janela
FIXA, anterior a TODOS os 19 pregoes de teste -- ver
`wdof1_regime_alvo_combinado_2026_09_11.log`, linha
"[combinado] limiar fade_off/20min = 8.11 ticks").

O NUMERO, 19 pregoes reais de tick (2026-08-17 a 2026-09-09 uteis + 09-10/11),
motor de producao (fila calibrada de `backtest.intraday.fidelidade`, sem
prazo de saida, capital REAL R$375/pregao nunca reposto): baseline T2/S16
puro fecha NEGATIVO (liquido -R$2.856,00, IC95% do win% inteiro abaixo do
breakeven empirico); `combo_T3` (fade_off/20min + T3/S16) fecha
**+R$169,50** liquido, win% 84,04% [81,53;86,26] contra breakeven empirico
83,85% -- **veredito INDEFINIDO** (o IC atravessa o breakeven, nao esta acima
dele). O que a variante muda de forma inequivoca: 9 de 19 pregoes positivos
contra 4 de 19 do baseline (21%->47%), e so' 6 de 19 pregoes com alguma
recusa de capital contra 13 de 19 do baseline (68%->32% de censura pelo
portao de caixa).

O QUE ISTO NAO E': nao e' uma promocao. E' a melhor variante encontrada ate
agora numa amostra de 19 pregoes IS (a mesma amostra que ESCOLHEU a variante
-- vies de selecao declarado no proprio script de origem), sem confirmacao
OOS. Decisao do dono, 2026-09-11: formalizar como estrategia registravel e
observar em SOMBRA (nunca real) -- nao substitui `wdo_orb` (TOP-1 do podio) e
nao entra no podio por cima dele. Ver `strategy.daytrade.registry` para o
comentario datado da decisao."""
from __future__ import annotations

from collections import deque

import pandas as pd

from core.instruments import economics_for
from strategy.daytrade.base import Bar, IntradayAction, IntradayOpenPosition
from strategy.daytrade.lab.wdo_grid_reload_maker import (
    EXIT_TTL_BARS_SEM_PRAZO,
    WDO_TICK_SIZE,
    WdoGridReloadMaker,
)

#: Limiar de "tendencia forte" para o filtro `fade_off`, em TICKS de retorno
#: acumulado na janela de `JANELA_REGIME_MINUTOS`. Percentil 70 de
#: |retorno M1 de 20min| calibrado em 2026-09-11 sobre 25.437 barras M1 de
#: WDO@, janela 2026-06-15..2026-08-14 -- ANTERIOR aos 19 pregoes de teste do
#: experimento que validou esta variante (`wdof1_regime_alvo_combinado_
#: 2026_09_11.py`/`.log`). NAO re-otimizar contra dado de teste: o proprio
#: valor so' significa algo por ter sido calibrado fora da amostra que mediu
#: o resultado.
LIMIAR_REGIME_TICKS = 8.11

#: Janela do retorno acumulado que classifica o regime -- 20 minutos, a
#: escala que sobrou depois de 5 e 10 minutos serem medidas e descartadas
#: (ver `wdof1_regime_medio_prazo_2026_09_11.py`: as tres escalas foram
#: testadas, 20min foi a que o dono levou para a rodada de combinacao).
JANELA_REGIME_MINUTOS = 20.0


class WdoGridFadeOffT3(WdoGridReloadMaker):
    """`WdoGridReloadMaker` + filtro de regime `fade_off`/20min + alvo T3
    (stop S16 intacto) -- candidata `combo_T3` de 2026-09-11, em OBSERVACAO
    (sombra), estatisticamente INDEFINIDA. Ver a docstring do modulo."""

    name = "wdo_grid_fade_off_t3"
    version = "0.1"

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = WDO_TICK_SIZE,
        profit_ticks: int = 3,           # "T3" -- ver a docstring do modulo
        stop_ticks: int | None = 16,     # "S16" -- intacto, igual a producao
        margin_per_contract_brl: float | None = None,
        hard_cap_contratos: int | None = 5,
        risco_pct_por_trade: float | None = 0.01,
        point_value_brl: float | None = None,
        fatiar_saida_alvo: bool = True,
        exit_ttl_bars: int | None = EXIT_TTL_BARS_SEM_PRAZO,
        **kwargs,
    ):
        """Defaults replicam `strategy.daytrade.registry._KWARGS_PADRAO
        [WdoGridReloadMaker.name]` (o robo de producao) -- margem/valor do
        ponto vem de `core.instruments` quando nao passado explicito, mesmo
        argumento ja documentado em `wdo_grid_reload_maker.py` (a economia do
        instrumento nao se digita duas vezes). So' `profit_ticks` (2->3) e o
        filtro de regime (novo, ver `_next_side_to_arm`/`_regime_atual`
        abaixo) diferem da producao -- tudo o resto desta assinatura existe
        so' para reproduzir, nao para redefinir, a config real do WDO F1."""
        if margin_per_contract_brl is None:
            margin_per_contract_brl = economics_for(symbol).margin_per_contract_brl
        if point_value_brl is None:
            point_value_brl = economics_for(symbol).point_value_brl
        super().__init__(
            symbol=symbol,
            tick_size=tick_size,
            profit_ticks=profit_ticks,
            stop_ticks=stop_ticks,
            margin_per_contract_brl=margin_per_contract_brl,
            hard_cap_contratos=hard_cap_contratos,
            risco_pct_por_trade=risco_pct_por_trade,
            point_value_brl=point_value_brl,
            fatiar_saida_alvo=fatiar_saida_alvo,
            exit_ttl_bars=exit_ttl_bars,
            **kwargs,
        )
        # Janela rolante de (ts, close) dos ultimos `JANELA_REGIME_MINUTOS`
        # minutos -- construida so' com o que `on_bar` ja recebe (ver a nota
        # de desenho na docstring do modulo). Resetada em `on_session_start`,
        # mesmo padrao de `self._state`/`self._defesa_armada` da classe base.
        self._janela_regime: deque[tuple[pd.Timestamp, float]] = deque()
        # Contador de quantas vezes cada regime foi visto no momento de um
        # ARMAMENTO (nao de toda chamada de `on_bar`) -- mesmo espirito do
        # `regime_contagem` do script de origem, util para quem for auditar o
        # comportamento em sombra sem precisar reprocessar o journal inteiro.
        # NUNCA resetado em `on_session_start` (soma a vida inteira da
        # instancia), mesmo padrao de `self.gate_bloqueios` na classe base.
        self.regime_contagem = {"up": 0, "down": 0, "neutral": 0}

    def on_session_start(self, session_date) -> None:
        super().on_session_start(session_date)
        self._janela_regime = deque()

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        # Registra o preco ANTES de decidir -- `_next_side_to_arm` (chamado
        # de dentro de `super().on_bar`) precisa da janela ja atualizada com
        # o preco desta barra/tick.
        self._registrar_regime(ts, bar.close)
        return super().on_bar(ts, bar, positions, session_pnl_brl)

    def _registrar_regime(self, ts: pd.Timestamp, close: float) -> None:
        self._janela_regime.append((ts, close))
        limite = ts - pd.Timedelta(minutes=JANELA_REGIME_MINUTOS)
        while self._janela_regime and self._janela_regime[0][0] < limite:
            self._janela_regime.popleft()

    def _regime_atual(self) -> str | None:
        """`"up"`/`"down"`/`"neutral"` a partir do retorno acumulado na
        janela rolante -- `None` so' enquanto a janela ainda esta vazia
        (primeiro evento do pregao), tratado como neutro por quem chama."""
        if not self._janela_regime:
            return None
        preco_antigo = self._janela_regime[0][1]
        preco_atual = self._janela_regime[-1][1]
        retorno_ticks = (preco_atual - preco_antigo) / self.tick_size
        if retorno_ticks > LIMIAR_REGIME_TICKS:
            return "up"
        if retorno_ticks < -LIMIAR_REGIME_TICKS:
            return "down"
        return "neutral"

    def _next_side_to_arm(self) -> str | None:
        """Mesma alternancia da classe base, com UM lado removido dos
        candidatos quando o regime esta forte: `"up"` remove `"short"` (nao
        fada mais uma alta sustentada), `"down"` remove `"long"`. Regime
        neutro (ou janela ainda vazia) preserva o comportamento BYTE A BYTE
        de `WdoGridReloadMaker._next_side_to_arm` -- modo `fade_off` do
        experimento original, nunca `segue_tendencia` (nao medido para esta
        combinacao)."""
        regime = self._regime_atual()
        self.regime_contagem[regime or "neutral"] += 1
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        proibido = {"up": "short", "down": "long"}.get(regime)
        if proibido is not None:
            candidates = [c for c in candidates if c != proibido]
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None
