"""Grid RELOAD maker adaptado para MINI-FUTURO WDO@ (2026-08-26) -- Frente
F1-wdo-consolidacao ("robo lucrativo em day trade de futuro, fora das
amarras da Copa BTG", ver o cabecalho da missao desta rodada).

MESMA mecanica central de `grid_reload_maker.py::GridReloadMaker`
(calibrada para ACAO -- PMAM3): uma ordem-limite (maker) fica parada a
`level_spacing_ticks` do preco de ABERTURA da sessao; se tocada, carrega
alvo (`profit_ticks`, maker tambem) e stop de protecao
(`stop_ticks`, a mercado); assim que a posicao fecha -- por alvo OU por
stop --, REARMA no MESMO nivel (nao avanca para um nivel mais distante
que pode nunca ser tocado), alternando de lado pelo lado que NAO acabou
de fechar. Este arquivo REESCREVE essa logica em vez de importar
`GridReloadMaker` de proposito -- regra desta rodada: nenhuma frente edita
arquivo compartilhado, e um import cruzado entre duas frentes rodando ao
mesmo tempo no mesmo diretorio de trabalho e' o mesmo risco de colisao
que editar o arquivo direto.

O candidato ORIGINAL, medido fora deste repo (ver o cabecalho da missao) e'
apelidado "T1 S16 x1": alvo 1 tick, stop 16 ticks, nivel a 1 tick (x1) do
preco de abertura, com confirmacao OOS (R$148,89/pregao IS+OOS, 89% de
retencao, ver `wdo-grid-reload-maker-top1-promocao-2026-08-27`).

2026-08-28, decisao do dono: o default de `stop_ticks` abaixo MUDOU de 16
para 4 apos a varredura completa profit_ticks/stop_ticks 1..20 (250
celulas, `scripts/daytrade/wdof1_grid_1a5_2026_08_28.py` e
`_6a20_2026_08_28.py`) achar que T1 S4 domina T1 S16 em toda metrica no IS
(liquido R$11.563,00 vs R$11.233,50, MaxDD R$72,00 vs R$121,50, calmar
160,60 vs 92,46) -- ver a memoria `wdof1-grid-1a20-encerrada-2026-08-28`.
RESSALVA que nao mudou com a troca: T1 S4 nunca foi medido no OOS. A
confirmacao OOS citada acima (R$148,89/pregao etc.) descreve especifica-
mente T1 S16, nao o default de entao.

2026-08-29, REVERTIDO de volta para 16: a ressalva acima se confirmou.
Rodando o historico COMPLETO salvo (177 pregoes, 2025-12-09 a 2026-08-28)
com CAIXA REAL (nao nocional) nos dois candidatos, T1 S4 nunca sobrevive ao
proprio historico com capital realista -- trava (fica abaixo do piso de
capital pra abrir 1 contrato, ver `LICOES_DE_PRODUCAO.md` item 1.14/3.9, e
NUNCA recupera dai em diante) em TODO nivel testado ate R$20.000, e so'
sobrevive com R$30.000 -- e mesmo assim fecha em +R$4.586,87 (líquido
R$-25.413,13 sobre R$30.000, quase so' devolvendo o capital). T1 S16
sobrevive o historico inteiro com so' R$5.000 e fecha estavel em
+R$2.671,80 líquido a partir dai (mesmo resultado de R$5.000 a R$30.000 --
uma vez que o caixa nao aperta mais, o robo nao depende de mais capital).
Win rate no mesmo teste: 65,7% (S4) contra 90,3% (S16) -- S4 e' uma
configuracao estruturalmente pior (razao risco:retorno 1:4 exige >80% de
acerto pra empatar; 65,7% fica abaixo disso), nao so' "medida numa amostra
diferente". Ver `scripts/daytrade/wdof1_stress_capital_real_historico_
completo.py` (achou o travamento) e a memoria `wdof1-stop-ticks-4-
producao-2026-08-28` (atualizada com a reversao). A confirmacao OOS citada
no paragrafo anterior (R$148,89/pregao, 89% de retencao) volta a descrever
o default ATUAL.

`tick_size` NAO tem default de instrumento nenhum
embutido aqui (fica 0.5, o `price_tick_size` do WDO@ documentado em
`backtest.intraday.profiles`, so' como conveniencia) -- quem instancia
para rodar de verdade sempre passa o tick vindo do PERFIL
(`profile_for("WDO@").price_tick_size`), nunca hardcoded numa segunda vez
(mesmo argumento do modulo `profiles.py`: um numero declarado em dois
lugares e' um numero que vai divergir).

Tres diferencas deliberadas frente ao original de acao:

1. `reanchor_mode` (ver `ReanchorMode` abaixo) -- dimensao que
   `GridReloadMaker` (acao) NAO tem, porque nunca precisou dela: o robo de
   acao sempre foi medido com ancora FIXA (`open_price` da sessao, uma vez
   so'). ACHADO desta frente (checagem de sanidade em
   `wdo_grid_reload_f1_lab.py`): reproduzir essa MESMA ancora fixa em
   WDO@ da' liquido NEGATIVO no IS (win rate ~84%, abaixo do breakeven de
   ~94,1% que a razao risco:retorno 1:16 exige) -- fica LONGE do ballpark
   conhecido (+R$37.606,53). Reancorar de forma ROLANTE (ao FECHAMENTO da
   barra em que cada ordem e' armada, mesmo espirito do modo "rolling" de
   `Gremah`) melhora win rate para ~89% e chega perto do breakeven, mas
   TAMBEM nao reproduz o ballpark -- fica o DEFAULT por ser a leitura mais
   proxima das duas, NAO por ter sido validada como a mecanica correta.
   Ver o relatorio desta frente para o veredito completo (nenhuma das
   leituras tentadas reproduziu o numero conhecido; a diferenca continua
   sem explicacao e fica registrada para uma proxima rodada investigar).
2. `session_stop_brl` DEFAULT `None` (desligado), nao herdado do default
   de acao (30.0 -- calibrado para PMAM3, tick de R$0,01, onde 20-30
   ticks de stop custam uma fracao de real). No WDO@ o tick vale R$5,00
   (0,5 pt x R$10,00/pt): SOZINHO, um stop de 16 ticks custa ~R$80,00 por
   contrato -- um `session_stop_brl=30` herdado desligaria a sessao
   inteira depois da PRIMEIRA perda parcial, o que nao e' o desenho que
   esta sendo medido ("alvo 1 tick, stop 16 ticks, espacamento x1", sem
   mencao de teto agregado de sessao). Fica opcional: quem quiser testar
   um teto de sessao passa o valor explicito, e o proprio teste de
   sensibilidade a pedagio desta frente NUNCA precisa dele.
3. `max_trades_per_side` default bem mais alto (200 contra 15 na acao) --
   o WDO@ tem ~570 barras M1/pregao (perfil medido) e, no modo rolante,
   rearma com muito mais frequencia que a acao (~41 trades/dia medidos
   contra ~14 na PMAM3) -- um teto baixo herdado apertaria essa frequencia
   de um jeito que nao foi o que se pretende medir aqui. Alto o bastante
   para nao morder em uso normal (o proprio script de medicao desta frente
   confere `ordens_recusadas_por_teto`/`max_trades_per_side` batido contra
   o numero de trades real, para o teto nunca decidir o resultado em
   silencio).

`quantity=None` (default) deixa o MOTOR decidir via
`IntradayBacktestConfig.default_quantity` -- 1 CONTRATO fixo por ordem, a
restricao real do dono nesta rodada (ver o cabecalho da missao: "so'
consegue operar 1 contrato no comeco"). A futura frente de escalonamento
por MARGEM antecipada aqui chegou em 2026-08-27 (`margin_per_contract_brl`,
ver abaixo) -- este paragrafo original fica registrado por historico, mas
o comportamento de 1 contrato fixo continua sendo o DEFAULT.

## Realocacao dinamica por CAPITAL (2026-08-27, ADITIVA e OPT-IN)

Equivalente, em FUTURO, do `_lotes_por_realocacao` de `Gremah` (caixa
acumulado -> mais contratos na proxima entrada, encolhe de volta se o
caixa cair) -- via `contracts_from_capital` (`strategy.daytrade.base`),
ja usado de forma ESTATICA (calculada 1x na config do backtest) em
`backtest.intraday.profiles.config_for`. Aqui vira DINAMICO: recalculado
a CADA `EnterLimit`, nao 1x por rodada.

Por default (`margin_per_contract_brl=None`) este modo nao existe e o
comportamento e' byte-a-byte o de antes: `quantity` (que pode ser `None`)
viaja direto para `EnterLimit`, exatamente como sempre foi. So' quem passa
`margin_per_contract_brl` explicito ativa a realocacao -- e nesse modo
`self.quantity` e' IGNORADO por completo: os dois parametros sao
MUTUAMENTE EXCLUSIVOS (capital dinamico OU quantidade fixa, nunca os dois
juntos disputando qual manda na mesma ordem). `hard_cap_contratos`
(opcional) e' o teto SUPERIOR do resultado de `contracts_from_capital` --
sem ele a formula cresce sem limite conforme o caixa sobe, o que nao faz
sentido para um instrumento com teto OFICIAL de contratos simultaneos
(ex.: 5 no WDO@, `profile_for("WDO@").max_open_contracts`).

`on_capital_update` segue o MESMO padrao ja usado por `Gremah`
(`_cash_atual_brl`, atualizado pelo motor logo antes de cada `on_bar`,
comeca em 0.0) -- enquanto o hook nunca foi chamado (replay de
`warm_start_calibration`, ou a primeira barra do backtest), `contracts_
from_capital(0.0, ...)` devolve 0, e o `max(1, ...)` aplicado no ponto de
uso garante pelo menos 1 contrato mesmo assim (mesmo espirito do piso ja
existente em `Gremah._lotes_por_realocacao`).

## Incidente REAL de 2026-08-28 -- teto agregado passou a morar no MOTOR

Este robo (WDO@, capital real R$300, primeira operacao ao vivo) ZEROU a
conta: saldo final -R$298,60, equity NEGATIVA. Forense confirmado no MT5:
dois deals de ABERTURA (`475209192` 11:58:59, `475209197` 11:59:04, mesmo
magic, volume 1 cada) -- duas entradas INDEPENDENTES, consolidadas pela
conta NETTING numa posicao de -2 contratos. Com 2 contratos a margem
exigida dobrou, a margem livre ficou negativa, e a corretora recusou ate a
ordem de FECHAMENTO (`[MG51] Para abrir novas posicoes`) -- a conta ficou
presa numa posicao perdedora sem conseguir sair.

A causa NAO estava neste arquivo -- `_next_side_to_arm`/`state.pending_side`
ja impediam esta estrategia de pedir uma segunda entrada enquanto a primeira
ainda estivesse pendente ou aberta. A causa era a config REAL ao vivo
carregar `max_open_contracts=5` (o teto REGULATORIO da Copa BTG, sem
nenhuma relacao com o caixa real de R$300) como UNICO teto agregado do
motor -- duas entradas independentes (de QUALQUER origem: bug de execucao,
race, retomada de processo) passavam por ele sem problema.

O fechamento (2026-08-28): `backtest.intraday.machine.IntradaySessionMachine`
ganhou um teto DINAMICO por CAPITAL (`IntradayBacktestConfig.margin_per_
contract_brl`/`margin_buffer`), recalculado a cada barra contra o caixa DE
VERDADE, com uma reserva de seguranca adicional (`strategy.daytrade.base.
RESERVA_CAIXA_SEGURANCA`) -- e `backtest.intraday.profiles.config_for` liga
isso por PADRAO para todo perfil de futuro com margem conhecida, o mesmo
caminho que `scripts/run_live.py::build_intraday` usa para montar a config
real. `_quantidade_da_entrada` abaixo tambem passou a usar
`contracts_from_capital_com_reserva` (em vez da versao pura) no modo
dinamico opt-in, para o que este robo PEDE nunca ficar mais otimista do que
o motor de fato deixa abrir -- mas quem tem a palavra final sobre recusar
uma entrada por capital insuficiente e' sempre o MOTOR, nao esta classe."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategy.daytrade.base import (
    MARGIN_BUFFER_FUTUROS,
    Bar,
    EnterLimit,
    Exit,
    IntradayAction,
    IntradayOpenPosition,
    IntradayStrategy,
    contracts_from_capital_com_reserva,
    contracts_from_risk,
    no_tick,
)

#: Tick de PRECO do WDO@ (contrato cheio WDOV26, 0,5 pt) -- a serie
#: continua do MT5 reporta 0,001, errado para posicionar ordem (ver
#: `backtest.intraday.profiles.SymbolProfile.price_tick_size`). So' um
#: DEFAULT de conveniencia para quem instancia sem passar o valor do
#: perfil -- rodar de verdade sempre passa `tick_size=` explicito, vindo
#: de `profile_for("WDO@").price_tick_size`.
WDO_TICK_SIZE = 0.5


@dataclass
class _SessionState:
    open_price: float | None = None
    anchor_price: float | None = None  # referencia ATUAL do nivel -- ver `ReanchorMode`
    session_halted: bool = False
    pending_side: str | None = None  # lado da EnterLimit pendente (ainda nao preenchida), ou None
    open_side: str | None = None  # lado da posicao CONFIRMADA aberta agora, ou None
    long_fills: int = 0
    short_fills: int = 0
    last_closed_side: str | None = None  # qual lado acabou de fechar (pra decidir o proximo a recarregar)


#: Duas formas de ancorar o nivel do grid -- ver a checagem de sanidade em
#: `wdo_grid_reload_f1_lab.py` para o que cada uma mediu de fato:
#:   "fixed_session_open" -- a ancora e' o preco de ABERTURA da sessao, uma
#:       vez, nunca muda (mesma mecanica de `grid_reload_maker.py::
#:       GridReloadMaker`, calibrada para PMAM3). Medido: liquido NEGATIVO
#:       no IS do WDO@.
#:   "rolling_last_price" -- a ancora e' o FECHAMENTO da barra em que a nova
#:       ordem e' armada (rearma seguindo o preco, mesmo espirito do modo
#:       "rolling" de `Gremah`/`gremah.py::on_bar`). Medido: mais proximo do
#:       breakeven que o modo fixo, mas AINDA nao reproduz o ballpark
#:       conhecido (+R$37.606,53) -- fica o DEFAULT por ser a leitura menos
#:       ruim das duas testadas, nao por ter sido confirmada como a
#:       mecanica original.
#: Ver a docstring do modulo para o relato completo da investigacao.
ReanchorMode = Literal["fixed_session_open", "rolling_last_price"]


class WdoGridReloadMaker(IntradayStrategy):
    """Grid maker com recarga do mesmo nivel apos cada fechamento (alvo ou
    stop largo), calibrado para o mini-futuro WDO@ -- ver a docstring do
    modulo para a mecanica completa e o porque de nao herdar/importar
    `GridReloadMaker` (acao)."""

    name = "wdo_grid_reload_maker"
    version = "0.1"
    symbol = "WDO@"
    is_futuro = True
    # A saida por alvo deste robo e' uma ordem-limite parada no nivel: e' o
    # centro do desenho (capturar o spread em vez de paga-lo), nao um
    # detalhe de modelagem. Ver `IntradayStrategy.target_fills_as_maker`.
    target_fills_as_maker = True
    # CORRIGIDO 2026-08-27 (era "m1", herdado de quando este modulo so'
    # tinha a checagem de sanidade em M1): a consolidacao F1 (leitura tick)
    # achou que o numero em M1 e' dominado por um artefato de
    # `machine.py::_exit_fill_price` (a barra de 1 minuto "melhora" o preco
    # de saida sempre que abre alem do alvo de 1 tick -- com alvo tao
    # apertado isso acontece o tempo todo). Em tick esse artefato cai para
    # 1,6% do lucro. O numero VALIDADO (R$148,89/pregao IS+OOS, 89% de
    # retencao no OOS, 30/30 blocos de 4 pregoes positivos) e' o de TICK --
    # rodar isto ao vivo ou no painel em M1 reproduziria o numero inflado,
    # nao o validado. Ver `scripts/daytrade/wdo_grid_reload_f1_tick_lab.py`
    # e a memoria `oos-split-sobreviventes-m5-2026-08-27`.
    feed_kind = "tick"

    # Promovido ao podio de day trade em 2026-08-27 (TOP-1, ver `strategy.
    # daytrade.registry`). Texto para humano, no mesmo espirito da
    # `gremah_tick`: o que o robo faz, com a ressalva que sustenta ou nao a
    # posicao -- nunca so' o numero bonito sem o que falta medir.
    tagline = (
        "Uma ordem parada 1 tick do preco de abertura, dos dois lados, no "
        "mini-dolar. Quando um lado toca, sai com alvo de 1 tick e stop de "
        "16 -- e rearma no mesmo lugar. O lucro de cada ida e volta e' de "
        "centavos; o numero medido depende de quanto disso e' fila real, "
        "nao so' de o sinal existir."
    )
    plain_summary = (
        "Assim que o pregao abre, o robo deixa uma ordem de compra parada 1 "
        "tick abaixo do preco de abertura e uma de venda 1 tick acima -- as "
        "duas ao mesmo tempo, sem escolher lado. Quando uma delas e' tocada, "
        "ele sai com um alvo pequeno (1 tick de lucro) ou um stop mais largo "
        "(16 ticks de perda) se o mercado virar contra. Fechada a posicao, "
        "rearma no MESMO nivel -- nunca persegue o preco para um nivel mais "
        "distante que pode nunca ser tocado.",
        "E' um robo de EXECUCAO, nao de previsao de direcao: ele nao aposta "
        "se o dolar vai subir ou cair, aposta que o preco vai oscilar de "
        "um lado para o outro do nivel dele repetidamente ao longo do "
        "pregao -- e' por isso que a mesma familia (chamada 'gremah' em "
        "acoes) sobrevive mesmo quando prever direcao no futuro nao "
        "funciona (ver a linha da Copa BTG, encerrada por refutacao "
        "direcional em 2026-08-26).",
        "2026-08-28: o stop foi trocado de 16 para 4 ticks apos varredura "
        "completa (1..20 x 1..20) mostrar T1 S4 dominando T1 S16 no IS. "
        "2026-08-29: REVERTIDO de volta para 16 -- a ressalva de entao se "
        "confirmou. Rodando o historico completo salvo (177 pregoes) com "
        "CAIXA REAL, T1 S4 nunca sobrevive ao proprio historico com capital "
        "realista (trava e nunca recupera em todo nivel testado ate "
        "R$20.000; so' sobrevive com R$30.000, e mesmo assim fecha quase so' "
        "devolvendo o capital). T1 S16 sobrevive com so' R$5.000 e fecha "
        "estavel em lucro a partir dai. Win rate no mesmo teste: 65,7% (S4) "
        "contra 90,3% (S16) -- S4 e' estruturalmente pior (1:4 de risco:"
        "retorno exige >80% de acerto pra empatar; 65,7% fica abaixo disso), "
        "nao so' uma amostra diferente.",
        "Os dois (S16 e S4) dependem do mesmo ponto cego: o numero so' "
        "existe se a ordem parada for de fato preenchida no toque -- e "
        "isso NUNCA foi medido com dado de livro real. O motor de teste "
        "preenche no toque; uma ordem parada real e' preenchida justamente "
        "quando o fluxo vem contra ela, o que o dado disponivel nao "
        "modela.",
        "Por isso ele entra no painel, mas o proximo passo antes de "
        "qualquer capital maior nao e' mais backtest -- e' medir a taxa de "
        "preenchimento passivo com 1 contrato ao vivo (T1 S16 ja tem "
        "confirmacao OOS de sinal -- R$148,89/pregao, 89% de retencao -- so' "
        "falta a taxa de fila real).",
    )
    plain_example = (
        "O dolar abre a R$ 5.079,00 (WDO@, tick de R$0,50). O robo deixa "
        "duas ordens paradas: compra a R$ 5.078,50 (1 tick abaixo) e venda "
        "a R$ 5.079,50 (1 tick acima).",
        "O preco cai e toca R$ 5.078,50 -- a compra e' preenchida. Na hora, "
        "o robo pendura a venda de saida em R$ 5.079,00 (alvo de 1 tick de "
        "lucro) e um stop a mercado em R$ 5.071,00 (16 ticks abaixo).",
        "Se o preco sobe de volta a R$ 5.079,00 antes de cair mais, a venda "
        "de saida e' tocada: ganhou R$5,00 (1 tick x R$5,00 x 1 contrato), "
        "menos a tarifa. O robo rearma IMEDIATAMENTE as duas ordens no "
        "mesmo nivel de antes (R$ 5.078,50 / R$ 5.079,50) -- nao persegue "
        "o novo preco.",
        "Se em vez disso o preco despenca 16 ticks sem voltar, o stop "
        "dispara: perde R$80,00 (16 x R$5,00), dezesseis vezes o ganho de "
        "um acerto. E' por isso que a taxa de acerto tem de ficar perto de "
        "94% para o resultado ficar positivo -- uma unica perda apaga "
        "cerca de dezesseis ganhos.",
    )

    def __init__(
        self,
        symbol: str = "WDO@",
        tick_size: float = WDO_TICK_SIZE,
        level_spacing_ticks: int = 1,   # "x1"
        profit_ticks: int = 1,          # "T1"
        stop_ticks: int | None = 16,    # "S16" -- ver nota 2026-08-29 no topo do modulo (S4 revertido)
        reanchor_mode: ReanchorMode = "rolling_last_price",
        max_trades_per_side: int = 200,
        session_stop_brl: float | None = None,
        quantity: int | None = None,
        margin_per_contract_brl: float | None = None,
        margin_buffer: float = MARGIN_BUFFER_FUTUROS,
        hard_cap_contratos: int | None = None,
        risco_pct_por_trade: float | None = None,
        point_value_brl: float | None = None,
    ):
        """Ver a docstring do modulo para a mecanica completa e para os
        parametros existentes acima (`tick_size`, `level_spacing_ticks`,
        `profit_ticks`, `stop_ticks`, `reanchor_mode`, `max_trades_per_side`,
        `session_stop_brl`, `quantity`). So' os quatro novos (2026-08-27/29)
        tem prosa aqui.

        `margin_per_contract_brl`: ATIVA a realocacao dinamica por capital
        (ver a secao do modulo). `None` (default) -- comportamento IDENTICO
        ao de antes: `quantity` viaja direto para cada `EnterLimit`. Setado,
        `quantity` e' IGNORADO e a quantidade de cada entrada vira `max(1,
        contracts_from_capital(caixa_atual, margin_per_contract_brl,
        margin_buffer, hard_cap=hard_cap_contratos))` -- os dois modos
        (capital dinamico OU quantidade fixa) sao MUTUAMENTE EXCLUSIVOS.

        `margin_buffer`: multiplicador de seguranca sobre a margem por
        contrato, mesmo parametro/mesmo default de `contracts_from_capital`
        (`MARGIN_BUFFER_FUTUROS=2.0`) -- so' importa quando
        `margin_per_contract_brl` esta setado.

        `hard_cap_contratos`: teto SUPERIOR opcional sobre o resultado de
        `contracts_from_capital` (ex.: o teto oficial do perfil, 5 no
        WDO@) -- sem ele a quantidade cresce sem limite conforme o caixa
        sobe. So' importa quando `margin_per_contract_brl` esta setado.

        `risco_pct_por_trade`/`point_value_brl` (2026-08-29, item 3.9 de
        LICOES_DE_PRODUCAO.md -- achado no `CopaWin`, nao ainda medido AQUI
        porque o modo dinamico deste robo e' OPT-IN e nao e' o default de
        producao hoje): SEGUNDO teto, independente do teto por margem acima
        -- a entrada usa o MENOR entre os dois (nenhum substitui o outro; ver
        `strategy.daytrade.base.contracts_from_risk`). Como o stop deste robo
        e' FIXO em ticks (`stop_ticks x tick_size`, nao por volatilidade do
        dia como no `CopaWin`), o risco em reais por contrato e' CONSTANTE:
        `stop_ticks x tick_size x point_value_brl`. Os dois precisam vir
        JUNTOS (um sem o outro nao computa nada) -- `None`/`None` (default)
        desliga, comportamento IDENTICO ao de antes."""
        if (risco_pct_por_trade is None) != (point_value_brl is None):
            raise ValueError(
                "wdo_grid_reload_maker: passe `risco_pct_por_trade` e "
                "`point_value_brl` JUNTOS (um sem o outro nao computa nada) "
                "ou nenhum dos dois."
            )
        self.symbol = symbol
        self.tick_size = tick_size
        self.level_spacing_ticks = level_spacing_ticks
        self.profit_ticks = profit_ticks
        self.stop_ticks = stop_ticks
        self.reanchor_mode = reanchor_mode
        self.max_trades_per_side = max_trades_per_side
        self.session_stop_brl = None if session_stop_brl is None else abs(session_stop_brl)
        self.quantity = quantity
        self.margin_per_contract_brl = (
            None if margin_per_contract_brl is None else float(margin_per_contract_brl)
        )
        self.margin_buffer = float(margin_buffer)
        self.hard_cap_contratos = hard_cap_contratos
        self.risco_pct_por_trade = (
            None if risco_pct_por_trade is None else float(risco_pct_por_trade)
        )
        self.point_value_brl = None if point_value_brl is None else float(point_value_brl)

        self._state = _SessionState()
        # Atualizado por `on_capital_update`, chamado pelo motor logo antes
        # de cada `on_bar` -- 0.0 so' antes da primeira barra real (warm
        # start via replay nunca chama `on_capital_update`; mesmo padrao de
        # `Gremah._cash_atual_brl`). So' importa quando
        # `margin_per_contract_brl` esta setado.
        self._cash_atual_brl = 0.0

    def on_session_start(self, session_date) -> None:
        self._state = _SessionState()

    def on_capital_update(self, cash_brl: float) -> None:
        """Guarda o caixa acumulado para a proxima `EnterLimit` usar -- so'
        tem efeito quando `margin_per_contract_brl` esta setado."""
        self._cash_atual_brl = cash_brl

    def on_order_rejected(self, ts: pd.Timestamp) -> None:
        """Zera `pending_side` -- sem isto, uma `EnterLimit` recusada pelo
        teto de capital (`backtest.intraday.machine`) trava este robo pelo
        resto da sessao: `on_bar` (linha 476) so' rearma quando
        `pending_side is None`, e o unico outro lugar que zera isto e' o
        FILL confirmado (`if positions:`), que nunca acontece para uma ordem
        recusada. Bug real, incidente WDO F1 2026-08-28 (`LICOES_DE_
        PRODUCAO.md`, item 1.14): 20/20 recusas por capital amostradas
        deixavam o robo mudo pelo resto do pregao antes deste hook existir."""
        self._state.pending_side = None

    def _quantidade_da_entrada(self) -> int | None:
        """`self.quantity` intacto (pode ser `None`) por default -- o motor
        decide via `IntradayBacktestConfig.default_quantity`, exatamente
        como sempre foi. Com `margin_per_contract_brl` setado, ignora
        `self.quantity` e recalcula pelo caixa atual, com piso de 1 contrato
        (mesmo espirito de `Gremah._lotes_por_realocacao`: caixa
        genuinamente insuficiente ou ainda DESCONHECIDO -- `_cash_atual_brl`
        comeca em 0.0 -- nao pode virar uma entrada de zero contrato, que
        nao e' "menor", e' nenhuma).

        `contracts_from_capital_com_reserva` (nao a versao pura) desde
        2026-08-28 -- MESMA reserva de seguranca que o motor aplica no teto
        agregado (`backtest.intraday.machine.IntradaySessionMachine.
        _cap_capital_atual`), para o que esta estrategia PEDE nunca ficar
        mais otimista que o que o motor de fato deixa ABRIR (ver
        `strategy.daytrade.base.RESERVA_CAIXA_SEGURANCA`). O piso de 1
        continua por CIMA da reserva -- uma entrada calculada em 0 contratos
        (caixa insuficiente COM a reserva) ainda vira 1 aqui; e' o motor,
        nao a estrategia, quem tem a palavra final sobre recusar essa
        entrada por capital (`OrderRejected(reason="capital_insuficiente")`)
        -- ver a nota no proprio motor sobre porque a recusa mora la, nao
        aqui.

        `risco_pct_por_trade`/`point_value_brl` (2026-08-29, item 3.9),
        quando setados, aplicam um SEGUNDO teto por CIMA do de margem -- o
        stop deste robo e' fixo em ticks, entao o risco em reais por
        contrato tambem e': `stop_ticks x tick_size x point_value_brl`.
        Nunca cresce a entrada, so' pode encolhe-la mais ainda."""
        if self.margin_per_contract_brl is None:
            return self.quantity
        teto = contracts_from_capital_com_reserva(
            self._cash_atual_brl, self.margin_per_contract_brl, self.margin_buffer,
            hard_cap=self.hard_cap_contratos,
        )
        if self.risco_pct_por_trade is not None and self.stop_ticks is not None:
            stop_reais_por_contrato = self.stop_ticks * self.tick_size * self.point_value_brl
            if stop_reais_por_contrato > 0:
                teto_por_risco = contracts_from_risk(
                    self._cash_atual_brl, self.risco_pct_por_trade, stop_reais_por_contrato,
                )
                teto = min(teto, teto_por_risco)
        return max(1, teto)

    def _level_price(self, side: str) -> float:
        offset = self.level_spacing_ticks * self.tick_size
        anchor = self._state.anchor_price
        return (anchor - offset) if side == "long" else (anchor + offset)

    def _target_price(self, side: str, level_price: float) -> float:
        offset = self.profit_ticks * self.tick_size
        return level_price + offset if side == "long" else level_price - offset

    def _stop_price(self, side: str, level_price: float) -> float | None:
        if self.stop_ticks is None:
            return None
        offset = self.stop_ticks * self.tick_size
        return level_price - offset if side == "long" else level_price + offset

    def _fills_of(self, side: str) -> int:
        return self._state.long_fills if side == "long" else self._state.short_fills

    def _next_side_to_arm(self) -> str | None:
        # Alterna comecando pelo lado que NAO acabou de fechar -- mesmo
        # espirito de `GridReloadMaker`: os dois lados rearmam de forma
        # independente, so' existe UMA ordem pendente por vez (o motor so'
        # permite uma posicao aberta simultanea, dado `quantity` fixo).
        candidates = ["long", "short"]
        if self._state.last_closed_side in candidates:
            candidates.remove(self._state.last_closed_side)
            candidates.append(self._state.last_closed_side)
        for side in candidates:
            if self._fills_of(side) < self.max_trades_per_side:
                return side
        return None

    def on_bar(
        self,
        ts: pd.Timestamp,
        bar: Bar,
        positions: list[IntradayOpenPosition],
        session_pnl_brl: float,
    ) -> list[IntradayAction]:
        state = self._state
        actions: list[IntradayAction] = []

        if state.open_price is None:
            # `no_tick`: a serie CONTINUA do MT5 (`WDO@`) reporta preco fora
            # da grade real de negociacao (ex.: 5769,053, quando o WDOV26
            # so' negocia em multiplos de 0,5) -- ancorar o grid num preco
            # assim faria TODOS os niveis derivados carem fora da grade
            # tambem (offset multiplo de `tick_size` somado a um preco ja
            # torto continua torto). Ver a armadilha medida documentada em
            # `backtest.intraday.profiles.SymbolProfile.price_tick_size`.
            state.open_price = no_tick(bar.open, self.tick_size)
            state.anchor_price = state.open_price

        if (self.session_stop_brl is not None and not state.session_halted
                and session_pnl_brl <= -self.session_stop_brl):
            state.session_halted = True
            if positions:
                actions.append(Exit(reason="stop_agregado_sessao"))
            return actions

        if state.session_halted:
            return actions

        if positions:
            # Confirma o preenchimento da EnterLimit pendente (a entrada),
            # se for o caso -- so' acontece na PRIMEIRA chamada com posicao
            # aberta apos a ordem ter sido emitida.
            if state.pending_side is not None:
                if state.pending_side == "long":
                    state.long_fills += 1
                else:
                    state.short_fills += 1
                state.open_side = state.pending_side
                state.pending_side = None
            return []  # alvo e stop ja sao geridos pelo motor (initial_target/initial_stop)

        # Sem posicao. Se `open_side` ainda estava marcado, a posicao que
        # existia na chamada anterior fechou entre uma chamada e outra (via
        # alvo ou stop, geridos pelo motor sem passar por uma acao explicita
        # da estrategia) -- registra qual lado foi, pra decidir o proximo a
        # recarregar.
        if state.open_side is not None:
            state.last_closed_side = state.open_side
            state.open_side = None

        if state.pending_side is not None:
            return actions  # ja ha ordem-limite pendente (entrada ainda nao preenchida), so' espera

        next_side = self._next_side_to_arm()
        if next_side is None:
            return actions  # os dois lados esgotaram max_trades_per_side nesta sessao

        if self.reanchor_mode == "rolling_last_price":
            # Rearma seguindo o preco -- a ancora vira o FECHAMENTO da barra
            # que acabou de fechar (`bar`, ja conhecida, sem look-ahead: a
            # ordem so' executa em barra FUTURA). Mesmo espirito do modo
            # "rolling" de `Gremah` (`gremah.py::on_bar`, `anchor = bar.
            # close`) -- ver `ReanchorMode` para o porque de nao usar
            # "fixed_session_open" por default.
            state.anchor_price = no_tick(bar.close, self.tick_size)
        # "fixed_session_open": `state.anchor_price` ja' foi fixado em
        # `state.open_price` na primeira barra da sessao e nunca muda.

        state.pending_side = next_side
        level_price = self._level_price(next_side)
        return [EnterLimit(
            side=next_side,
            limit_price=level_price,
            initial_target=self._target_price(next_side, level_price),
            initial_stop=self._stop_price(next_side, level_price),
            quantity=self._quantidade_da_entrada(),
            reason="wdo_grid_reload_" + next_side,
        )]
