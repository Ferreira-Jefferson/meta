"""Perfil economico por SIMBOLO intradiario — split congelado, custo real,
horario de flatten, tamanho de posicao.

Morava em `scripts/daytrade/run_backtest.py` ate 2026-08-21. Subiu para
`backtest/` quando a operacao ao vivo passou a precisar dos MESMOS numeros:
um `session_end_time` diferente entre backtest e producao faria o robô ao
vivo achatar em outro minuto do que o validado, e um custo diferente faria
o P&L em modo sombra nao bater com o backtest — que e' exatamente a
verificacao que o modo sombra existe para fazer. Um numero declarado em dois
lugares e' um numero que vai divergir.

Cada simbolo tem seu proprio perfil porque a economia de um instrumento nao
se transfere para outro: mesmo ponto de preco significa coisas diferentes,
mesmo lote significa coisas diferentes, e o horario de fechamento pode nem
seguir o mesmo calendario.

Hoje todos os perfis sao ACAO da B3 em lote padrao, e por isso quase tudo
neles e' identico — o que varia de verdade e' so o SPLIT (ate onde a pesquisa
podia olhar). Dai `_equity_profile()`: a parte comum fica escrita UMA vez, e
cada entrada da tabela declara so o que e' dela. Um instrumento com economia
propria (futuro, BDR, ETF) nao usa a fabrica — monta `SymbolProfile` na mao,
com o motivo escrito junto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from core.b3_session import FOLGA_ACHATAMENTO_MINUTOS
from core.instruments import (
    ACAO_B3_POINT_VALUE_BRL,
    ACAO_B3_PRICE_TICK_SIZE,
    InstrumentEconomics,
    economics_for,
)
from strategy.daytrade.base import (
    MARGIN_BUFFER_FUTUROS,
    capital_minimo_brl,
    contracts_from_capital,
)

from backtest.intraday.costs import (
    B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG,
    DESLIZE_ALVO_NATIVO_TICKS,
    IntradayCostModel,
)
from backtest.intraday.fidelidade import fidelidade_ou_none
from backtest.intraday.machine import IntradayBacktestConfig


@dataclass(frozen=True)
class SymbolProfile:
    frozen_cutoff: str
    frozen_note: str
    fee_round_trip_brl: float
    fee_note: str
    session_end_time: time
    default_quantity: int
    exchange_fee_pct_per_leg: float = 0.0
    # "b3_equities" tira o corte de flatten do calendario e IGNORA
    # `session_end_time`; "fixed" usa o campo tal qual. Todo perfil real hoje
    # e' acao, logo "b3_equities" — "fixed" existe para um instrumento com
    # horario proprio (futuro, por exemplo, cujo fechamento medido NAO desloca
    # com o horario de verao dos EUA) e para relogio sintetico de teste.
    session_end_policy: Literal["fixed", "b3_equities"] = "b3_equities"
    # ABERTURA do pregao do instrumento, em UTC -- o par de
    # `session_end_time`, e existe pelo MESMO motivo dele (ver a docstring
    # do modulo: "um numero declarado em dois lugares e' um numero que vai
    # divergir"). `None` (default, toda acao) = a abertura vem do calendario
    # de ACAO em `core.b3_session` (10:00 de Brasilia).
    #
    # Existe porque a ausencia dele custou 26,2% do pregao (2026-09-08): o
    # portao de `live.intraday_runtime.IntradayLiveRuntime.run_once` chamava
    # `live.clock.phase()`, que so' conhece o pregao de ACAO, e o robo de
    # FUTURO ficava `idle` das 09:00 as 10:00 e parava as 17:00 -- enquanto
    # o backtest media 09:00..18:29 com o `session_end_time` acima. Toda
    # validacao do WDO F1 descrevia um pregao 26% maior do que o robo jamais
    # operou, o que e' exatamente o que o invariante "live/ nao decide nada"
    # existe para impedir. `core.b3_session` ja avisava, na propria
    # docstring, que futuro NAO desloca e que aquele modulo "fala de ACAO".
    session_start_time: time | None = None
    # Rotulo, em UTC, da barra a partir da qual o motor ACHATA a posicao --
    # o que vira `IntradayBacktestConfig.session_end_time` em `config_for`.
    # `None` (toda acao) = o corte vem do calendario
    # (`session_end_policy="b3_equities"` -> `core.b3_session.flatten_cut_utc`)
    # e este campo nem e' lido.
    #
    # EXISTE PORQUE UM CAMPO SO' FAZIA O TRABALHO DE TRES (item 4.28 de
    # LICOES_DE_PRODUCAO.md, achado 2026-09-14). `session_end_time` respondia
    # ao mesmo tempo (a) "quando o mercado fecha", (b) "em que barra eu acho a
    # posicao" e (c) "ate' quando o robo pode agir" -- e (b) e (c) sao
    # incompativeis no mesmo instante: `live.clock.phase_em_janela` desliga o
    # robo em `session_end_time`, entao a barra que carregaria o achatamento
    # nunca chegava a ser lida. Resultado medido: ZERO eventos FLATTEN em toda
    # a historia de `db/live.sqlite`, contra 39,1% das saidas que o backtest
    # do `copa_win` credita ao sino.
    #
    # Agora `session_end_time` responde SO' (a) e (c) -- o fim de pregao
    # medido, que continua sendo o portao de atividade -- e este campo
    # responde (b), sempre ANTES dele. Derivado, nunca digitado a mao: o
    # recuo e' `core.b3_session.FOLGA_ACHATAMENTO_MINUTOS`, o mesmo do lado
    # de acao, para os dois caminhos nao divergirem em silencio.
    flatten_cut_time: time | None = None
    # Tamanho do TICK DE PRECO do instrumento, quando o simbolo de onde a
    # economia e' lida reporta um valor que nao serve para posicionar ordem.
    # `None` (default) = usa o que o terminal devolveu, o caso de toda acao.
    #
    # Existe por uma armadilha MEDIDA (2026-08-25) nas series CONTINUAS de
    # futuro: `WIN@` devolve `trade_tick_size=1.0` e `WDO@`, `0.001` -- mas o
    # contrato cheio que elas emendam (`WINV26`/`WDOV26`) negocia em passos de
    # 5,0 e 0,5. O `point_value_brl` sai correto nos dois casos (a razao
    # `trade_tick_value/trade_tick_size` da' 0,20 e 10,00 igual), entao a
    # continua e' segura para P&L; o que ela estraga e' o PRECO: uma ordem
    # limite colocada em 141.237 nao existe no book (so' multiplos de 5), e o
    # backtest preencheria uma ordem que a corretora recusaria.
    #
    # `config_for` preserva `point_value_brl` ao aplicar o override (reescala
    # `trade_tick_value` junto), entao trocar isto nunca mexe no P&L -- so' na
    # grade de precos e na slippage em ticks.
    price_tick_size: float | None = None
    # Teto de contratos SIMULTANEAMENTE abertos (ver `IntradayBacktestConfig.
    # max_open_contracts`). `None` = sem teto (toda acao). Instrumento de
    # competicao com teto de posicao declara o teto OFICIAL aqui, e quem roda
    # um teste com folga passa `max_open_contracts=` para `config_for`.
    max_open_contracts: int | None = None
    # `True` so' para um perfil de FUTURO (`_futures_profile`, nunca
    # `_equity_profile`) -- distingue os dois caminhos de dimensionamento de
    # `config_for` (caixa-por-lote em acao via `capital_minimo_brl`;
    # margem-por-contrato em futuro via `strategy.daytrade.base.
    # contracts_from_capital`, 2026-08-26). Campo explicito em vez de
    # inferir de `session_end_policy`/`price_tick_size` (que existem por
    # OUTRO motivo, documentado nos proprios campos) -- misturar duas
    # finalidades num campo so' e' o tipo de acoplamento que este modulo
    # ja evita (ver docstring de `_equity_profile`).
    is_futures: bool = False
    # Margem exigida por 1 contrato, em REAIS -- alimenta `contracts_from_
    # capital`/o painel (`dashboard/robot_view.py`), nunca o motor de
    # backtest (que usa `max_open_contracts`, nao caixa). `None` para toda
    # acao (o limitador la e' `capital_minimo_brl`, nao margem).
    #
    # VALOR APROXIMADO, nao verificado via MT5 (`order_calc_margin`/
    # `symbol_info_margin`, hoje NAO consultado neste repo -- ver a nota
    # longa em `strategy.daytrade.base.MARGIN_BUFFER_FUTUROS`). Vem da
    # margem PROMOCIONAL de day trade que o dono relatou (~R$100 mini-
    # indice, ~R$150 mini-dolar, 2026-08-27) -- o mesmo numero que
    # `daytrade_capital_real_gate_2026_08_27` ja usa em toda a escada de
    # capital.
    #
    # FONTE DA VERDADE desde 2026-09-09: `core.instruments.FUTUROS`. Este
    # campo e' COPIA dela (`_futures_profile` preenche), nao a declaracao --
    # o registry de `strategy/` precisa do mesmo numero e nao pode importar
    # `backtest/` (AGENTS.md, regra 1), entao o dado teve de subir para
    # `core/`. Nao digite um numero novo aqui.
    margin_per_contract_brl: float | None = None
    # Quantos REAIS vale 1 PONTO de preco deste instrumento, por unidade
    # (acao/contrato). Fonte da VERDADE do numero -- ele e' propriedade do
    # INSTRUMENTO, nunca de quem opera nele: dois robos no mesmo simbolo tem
    # obrigatoriamente o mesmo valor de ponto, e um robo novo que esquecesse
    # de declarar deixaria a contabilidade sem como converter ponto em real.
    #
    # Acao: 1,0 -- o preco ja e' em reais por acao (`_equity_profile`).
    # Futuro: vem de `core.instruments.FUTUROS` (R$0,20 no WIN@, R$10,00 no
    # WDO@), e e' o multiplicador cuja AUSENCIA custou tres incidentes de
    # contabilidade (itens 5.7, 5.19 de LICOES_DE_PRODUCAO.md: 52 pontos de
    # WDO@ contabilizados como R$52,00 em vez de R$520,00, em tres caminhos
    # de codigo diferentes).
    #
    # NAO substitui a economia lida do terminal em `config_for` -- ali o
    # valor continua saindo de `trade_tick_value/trade_tick_size`, e este
    # campo CONFERE os dois (ver o guard la'). Ele existe porque ha
    # consumidores que precisam converter ponto em real com o MT5 FECHADO e
    # com o processo do robo ja' morto -- a rotina de remocao de robo
    # (`dashboard/live_teardown.py`) e' o caso -- e para eles o terminal nao
    # e' fonte possivel. `cost_model_from_profile()` e' a porta desses.
    point_value_brl: float | None = None


#: Corte IS/OOS de TODA a familia de acoes calibrada em 2026-08-22. Declarado
#: ANTES da varredura de parametros: a varredura fina so enxergou o trecho
#: anterior a esta data, e o trecho posterior foi rodado UMA vez, ja com o par
#: escolhido, so para confirmar. Simbolo que ficou positivo no IS e negativo
#: no OOS foi DESCARTADO (aconteceu com CMIN3, BBDC3, EQTL3 e EUCA4) -- e' o
#: unico motivo de este corte existir.
#:
#: Substitui, para a PMAM3, o corte anterior de 2025-12-01 (declarado
#: 2026-08-21). Nao foi conveniencia: o preco da PMAM3 caiu de ~R$2,55 para
#: R$0,14, e o regime de preco em que ela opera HOJE (ver `regime_start`
#: abaixo) comeca em 2025-12-16 -- inteiramente DEPOIS do corte velho, que
#: portanto nao separava mais nada de util. Custo honesto dessa troca,
#: registrado para nao se perder: a calibracao da PMAM3 (0,32%/10x) foi
#: escolhida com dado que o corte de 2025-12-01 mantinha reservado, entao ela
#: tem menos independencia IS/OOS que as outras nove.
OOS_CUTOFF = "2026-06-13"

_FEE_NOTE = (
    "lote padrao (100 acoes): corretagem zero na Rico; taxa de bolsa em "
    "exchange_fee_pct_per_leg (2x a taxa real, margem de seguranca permanente). "
    "O mercado FRACIONARIO cobra R$1,90 fixos por ordem (confirmado pelo dono "
    "2026-08-22) e por isso day trade nunca opera nele -- ver "
    "`live/broker_mt5.py` e `scripts/run_live.py::build_intraday`, que nem "
    "recebem mapa fracionario no slot intradiario."
)


def _equity_profile(regime_start: str, oos_note: str) -> SymbolProfile:
    """Perfil de uma ACAO da B3 operada em lote padrao pela familia gremah.

    `regime_start`: primeiro dia do REGIME DE PRECO atual do papel — a data
    mais antiga a partir da qual o fechamento diario nunca mais saiu da faixa
    [0,5x, 2x] do preco de hoje. A calibracao so foi medida dai para frente,
    porque `profit_pct` vira TICKS (`Gremah._ticks_from_pct`) e portanto o
    mesmo percentual significa coisas diferentes em precos diferentes: medir
    CSAN3 desde 2021, quando ela valia o dobro, calibraria para um papel que
    nao existe mais.

    `session_end_time` e' preenchido so porque o dataclass exige um valor —
    `session_end_policy="b3_equities"` o IGNORA e tira o corte de flatten do
    calendario (`core.b3_session`), que anda 1h com o horario de verao dos
    EUA. O valor aqui e' o antigo corte fixo (19:54 UTC), que era so a moda de
    UM dos dois regimes de DST nas barras salvas.
    """
    return SymbolProfile(
        frozen_cutoff=OOS_CUTOFF,
        frozen_note=(
            f"regime de preco atual desde {regime_start}; IS {regime_start}..{OOS_CUTOFF} "
            f"(unico trecho que a varredura de parametros enxergou), OOS "
            f"{OOS_CUTOFF}..2026-08-21 confirmado positivo em 2026-08-22 ({oos_note}). "
            f"Capital do teste = `strategy.daytrade.base.capital_minimo_brl` no preco atual."
        ),
        fee_round_trip_brl=0.0,
        fee_note=_FEE_NOTE,
        exchange_fee_pct_per_leg=B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG,
        session_end_time=time(19, 54),
        session_end_policy="b3_equities",
        default_quantity=100,  # 1 lote padrao
        # Acao: o preco JA e' em reais por acao, entao 1 ponto = R$1,00.
        # Declarado (e nao deixado em `None`) porque quem converte ponto em
        # real fora do motor -- `cost_model_from_profile` -- precisa do
        # numero tambem para acao, e 'nao declarado' ali significa 'nao sei',
        # que apagaria o custo de bolsa do resultado de uma acao.
        point_value_brl=ACAO_B3_POINT_VALUE_BRL,
    )


#: Custo assumido por CONTRATO de mini-futuro em UM round-trip (ida e volta),
#: em reais -- R$0,25 por perna. Futuro cobra por CONTRATO, nao percentual do
#: notional: por isso `exchange_fee_pct_per_leg=0.0` nos perfis de futuro e
#: todo o custo vive aqui (o inverso exato do perfil de acao, onde a
#: corretagem e' zero e todo o custo e' percentual).
#:
#: Mesmo espirito conservador de `B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG` (2x a
#: taxa real): a tarifa de day trade em mini-contrato na B3 fica abaixo disto
#: e varias corretoras zeram a corretagem em mini. Assumir MAIS custo do que
#: se paga nunca inventa lucro; assumir menos, sim.
#:
#: A assimetria que este numero cria entre os dois instrumentos e' o motivo
#: principal de WIN e WDO nao poderem compartilhar calibracao: R$0,50 e' meio
#: tick no WIN (tick = 5 pts = R$1,00) e um DECIMO de tick no WDO (tick = 0,5
#: pt = R$5,00). O WDO tolera cinco vezes mais giro por unidade de edge.
FUTURES_FEE_ROUND_TRIP_BRL = 0.50

_FEE_NOTE_FUTURO = (
    "R$0,25 por perna, por CONTRATO (`FUTURES_FEE_ROUND_TRIP_BRL`), sem taxa "
    "percentual de notional. NAO se sabe se o simulador da Copa BTG cobra "
    "custo nenhum -- por isso todo relatorio da familia `copa` mostra o par "
    "COM e SEM custo, em vez de escolher uma das duas hipoteses."
)


def _recua(t: time, minutos: int) -> time:
    """`t` (hora do dia, UTC) recuada de `minutos`. Gemea em espirito de
    `core.b3_session.flatten_cut_utc`, que faz o mesmo para o calendario de
    ACAO -- aqui a hora e' fixa (futuro nao desloca), entao a data usada para
    a subtracao e' irrelevante e nao ha fuso envolvido."""
    return (datetime.combine(date(2026, 1, 1), t) - timedelta(minutes=minutos)).time()


def _futures_profile(
    economics: InstrumentEconomics,
    session_end_time: time,
    max_open_contracts: int,
    medicao: str,
) -> SymbolProfile:
    """Perfil de um MINI-FUTURO da B3 (serie continua) operado em contratos.

    Nao usa `_equity_profile` de proposito -- e' outro tarifario (por
    contrato, nao percentual), outro horario (o pregao de futuro NAO desloca
    com o horario de verao dos EUA, medido: a ultima barra M1 do WIN cai as
    18:24 de Brasilia em 179 dos 182 pregoes salvos) e outro limitador de
    tamanho (teto de contratos abertos, nao caixa).

    `session_end_time` em UTC, como todo perfil deste modulo -- as barras
    salvas por `market_data_intraday` tem index UTC e a maquina compara
    `ts.time()` direto contra este campo (`session_end_policy="fixed"`).

    `medicao`: o que foi medido no parquet deste simbolo, para o numero de
    corte nao ficar orfao de evidencia.

    `economics` (2026-09-09) traz os TRES numeros que sao propriedade do
    INSTRUMENTO -- valor do ponto, passo de preco e margem por contrato -- de
    `core.instruments.FUTUROS`, que e' a fonte da verdade deles. Nao sao
    parametros soltos deste montador de proposito: `strategy.daytrade.
    registry` precisa dos MESMOS numeros e nao pode importar `backtest/`
    (AGENTS.md, regra 1), entao ate 2026-09-09 ele os REDIGITAVA e o que
    impedia a divergencia era um teste de amarracao. Subir o dado para
    `core/` e' o que a propria regra 1 prescreve.

    Os tres continuam OBRIGATORIOS e positivos -- quem recusa agora e'
    `InstrumentEconomics.__post_init__`, na fonte, em vez de aqui na copia.
    O motivo de cada um esta' na docstring de la'; em resumo:
    `margin_per_contract_brl` ausente desliga o teto de contratos por caixa
    (o estado do WDO F1 no dia em que zerou a conta, 2026-08-28) e
    `point_value_brl` ausente e' o multiplicador de 10x dos itens 5.7/5.19."""
    return SymbolProfile(
        frozen_cutoff=OOS_CUTOFF,
        frozen_note=(
            f"corte IS/OOS reaproveitado da familia de acoes (congelado em "
            f"2026-08-22, ANTES de qualquer trabalho em futuro existir -- "
            f"logo nao pode ter sido escolhido para favorecer a familia "
            f"`copa`). {medicao}"
        ),
        fee_round_trip_brl=FUTURES_FEE_ROUND_TRIP_BRL,
        fee_note=_FEE_NOTE_FUTURO,
        exchange_fee_pct_per_leg=0.0,
        session_end_time=session_end_time,
        flatten_cut_time=_recua(session_end_time, FOLGA_ACHATAMENTO_MINUTOS),
        session_end_policy="fixed",
        # 09:00 de Brasilia. Igual para WIN e WDO, e NAO desloca com o
        # horario de verao dos EUA -- e' o mesmo fato que
        # `core.b3_session` ja declara na docstring ("Futuro (WIN) NAO
        # desloca: 09:00..18:24 cru nos dois lados das duas viradas") e que
        # a base de tick confirma (mediana de inicio de pregao 09:00 nos 130
        # pregoes de `WDO_A_.parquet`). Fica em UTC como `session_end_time`,
        # pelo mesmo motivo: e' assim que as barras salvas sao indexadas.
        session_start_time=time(12, 0),
        default_quantity=1,  # 1 CONTRATO -- futuro nao tem lote de 100
        price_tick_size=economics.price_tick_size,
        max_open_contracts=max_open_contracts,
        is_futures=True,
        margin_per_contract_brl=economics.margin_per_contract_brl,
        point_value_brl=economics.point_value_brl,
    )


#: Mini-futuros da B3, series CONTINUAS (`@` = o MT5 emenda os vencimentos).
#: Fora de `PROFILES` de proposito: aquela tabela e' a familia `gremah` (acao
#: em lote padrao, com calibracao propria por papel) e dois testes
#: (`tests/test_intraday_profiles.py`) leem cada entrada dela assumindo isso.
#: Um futuro nao tem calibracao `gremah`, nao opera lote de 100 e nao e'
#: limitado por caixa -- misturar os dois faria a tabela deixar de significar
#: uma coisa so'. `profile_for()` resolve os dois catalogos.
#:
#: Valor do ponto, passo de preco e margem NAO aparecem aqui: sao propriedade
#: do INSTRUMENTO e vem de `core.instruments.FUTUROS` (ver `_futures_profile`).
#: O que fica declarado aqui e' o que e' propriedade da MEDICAO/do
#: REGULAMENTO -- horario medido no parquet e teto de contratos da Copa BTG.
FUTURES_PROFILES: dict[str, SymbolProfile] = {
    "WIN@": _futures_profile(
        economics=economics_for("WIN@"),
        session_end_time=time(21, 25),  # 18:25 de Brasilia (fecho medido 18:24)
        max_open_contracts=15,          # teto oficial da Copa BTG 2025
        medicao=(
            "182 pregoes M1 (2025-12-01..2026-08-25): range diario mediano "
            "2.968 pts, soma|C-O| por pregao 29.722 pts, 563 barras/pregao, "
            "17,4M contratos/dia de giro."
        ),
    ),
    "WDO@": _futures_profile(
        economics=economics_for("WDO@"),
        session_end_time=time(21, 30),  # 18:30 de Brasilia (fecho medido 18:29)
        max_open_contracts=5,           # teto oficial da Copa BTG 2025
        medicao=(
            "177 pregoes M1 (2025-12-08..2026-08-25): range diario mediano "
            "49,3 pts, soma|C-O| por pregao 570 pts, 570 barras/pregao, "
            "2,4M contratos/dia de giro."
        ),
    ),
}


def profile_for(symbol: str) -> SymbolProfile:
    """Perfil economico de um simbolo, venha ele da tabela de ACAO
    (`PROFILES`) ou da de FUTURO (`FUTURES_PROFILES`). `KeyError` (nunca um
    default silencioso) para simbolo sem perfil -- operar com custo/horario
    de outro instrumento e' pior que nao operar."""
    if symbol in PROFILES:
        return PROFILES[symbol]
    if symbol in FUTURES_PROFILES:
        return FUTURES_PROFILES[symbol]
    raise KeyError(
        f"sem perfil economico declarado para {symbol!r} -- ver "
        f"`backtest.intraday.profiles.PROFILES` (acoes) e `FUTURES_PROFILES` "
        f"(mini-futuros)."
    )


#: Ordem = lucro OOS decrescente dentro de cada grupo, PMAM3 primeiro por ser
#: o papel original da familia. Toda entrada aqui tem calibracao propria em
#: `strategy.daytrade.lab.gremah._CALIBRATION_BY_SYMBOL` — as duas tabelas
#: precisam andar juntas, e `tests/test_intraday_profiles.py` falha se
#: divergirem (um simbolo calibrado sem perfil nao consegue operar ao vivo:
#: `scripts/run_live.py::build_intraday` o recusa).
PROFILES: dict[str, SymbolProfile] = {
    "PMAM3": _equity_profile(
        "2025-12-16", "319 trades, wr 83,1%, +R$177,79, pf 2,75, MaxDD -21,59%"),
    "KLBN4": _equity_profile(
        "2025-09-02", "671 trades, wr 98,7%, +R$425,02, pf 12,15, MaxDD -0,81%"),
    "CSAN3": _equity_profile(
        "2025-09-22", "627 trades, wr 98,2%, +R$347,48, pf 4,22, MaxDD -2,16%"),
    "DASA3": _equity_profile(
        "2025-09-11", "857 trades, wr 93,5%, +R$278,94, pf 1,77, MaxDD -4,24%"),
    "PCAR3": _equity_profile(
        "2025-08-21", "894 trades, wr 92,4%, +R$249,89, pf 1,59, MaxDD -4,55%"),
    # AMOSTRA FINA, e a acao mais cara da tabela por MUITO: R$151,95 -> lote de
    # R$15.195 -> minimo de R$30.390 em caixa. So 131 trades no IS e 14 no OOS
    # (as outras fazem centenas a milhares) porque o alvo de 0,42% num papel
    # caro e' muito maior em reais e o preco raramente percorre isso num dia.
    # Passou nos dois trechos, entao esta aqui; mas 14 trades nao provam edge,
    # e o capital exigido esta fora da realidade do dono hoje.
    "CLSC4": _equity_profile(
        "2025-05-12", "14 trades, wr 64,3%, +R$215,21, pf 1,56, MaxDD -0,99%"),
    "KLBN3": _equity_profile(
        "2025-03-10", "395 trades, wr 95,9%, +R$198,43, pf 3,63, MaxDD -1,48%"),
    "GRND3": _equity_profile(
        "2025-09-05", "334 trades, wr 97,3%, +R$189,70, pf 5,59, MaxDD -1,54%"),
    "LPSB3": _equity_profile(
        "2022-12-20", "171 trades, wr 94,2%, +R$139,51, pf 4,83, MaxDD -2,42%"),
    "BMGB4": _equity_profile(
        "2025-06-04", "316 trades, wr 97,5%, +R$137,72, pf 2,86, MaxDD -2,11%"),
}


class SymbolEconomicsError(ValueError):
    """A economia do simbolo passada a `config_for` nao serve para montar a
    run -- ou o terminal nao respondeu um numero utilizavel, ou ele
    contradiz o que o perfil declara.

    Subclasse de `ValueError` de proposito (todo chamador antigo que ja
    tratava `ValueError` continua funcionando), mas com NOME proprio para
    que quem puder degradar em vez de estourar consiga distinguir esta
    causa das outras oito validacoes de argumento que `config_for` faz --
    e para que um traceback num log de robo diga o que aconteceu na
    primeira linha, nao na quinta.

    Onde ela aparece hoje:

      * `scripts/run_live.py::build_intraday` -- processo PROPRIO do robo,
        levantada ANTES de qualquer ordem. O robo nao sobe, e a falha e'
        alta (traceback no log do slot, processo morto, cartao do painel
        mostra 'parado'). Isso e' deliberado -- ver o bloco de decisao em
        `_confere_valor_do_ponto`.
      * `dashboard/live_service.py::_build_intraday_runtime` -- runtime de
        LEITURA do painel, que deriva `trade_tick_value` do PROPRIO perfil
        (`0.01 * profile.point_value_brl`). Ali as duas fontes sao a mesma
        e a divergencia e' impossivel por construcao; se algum dia deixar
        de ser, `dashboard/app.py::_slot_ctx` NAO captura `ValueError` (so'
        `KeyError` e as duas `Legacy*Error`), entao viraria HTTP 500 em
        `/operacao`. Registrado aqui porque o conserto mora naquele arquivo,
        nao neste."""


#: Tolerancia RELATIVA aceita entre o valor do ponto DERIVADO da economia
#: lida do terminal (`trade_tick_value / trade_tick_size`) e o DECLARADO em
#: `core.instruments`.
#:
#: 0,5% NAO e' um numero calibrado contra dispersao medida, e afirmar que
#: fosse seria inventar evidencia: o valor do ponto de um contrato e' uma
#: constante decimal exata do regulamento (R$0,20 no WIN, R$10,00 no WDO),
#: e a razao que o terminal reporta divide exatamente (1,0/5,0 e 5,0/0,5).
#: Nao ha ruido economico para acomodar -- so' ruido de PONTO FLUTUANTE e
#: de arredondamento na casa que a corretora escolher publicar.
#:
#: A faixa exata nao decide nada, e e' por isso que ela pode ser generosa:
#: toda divergencia que pode acontecer de verdade esta' ordens de grandeza
#: fora dela. As duas familias reais sao (1) o terminal devolver ZERO
#: (simbolo fora do Market Watch), que `_checa_economia_do_terminal` pega
#: antes, e (2) o simbolo apontar para o contrato CHEIO em vez do mini --
#: DOL vale 5x o WDO e IND 5x o WIN, ou seja 400% de erro, 800 vezes esta
#: banda. Qualquer valor entre 1e-6 e 0,5 daria o MESMO veredito em todos
#: os casos possiveis; 0,005 fica no meio, longe do falso positivo (que
#: pararia o robo a toa) e longe do falso negativo (que deixaria passar um
#: erro de instrumento).
TOLERANCIA_VALOR_DO_PONTO = 0.005


def _symbol_do_perfil(profile: SymbolProfile) -> str:
    """O simbolo de um perfil das tabelas deste modulo, so' para escrever
    mensagem de erro que o dono consiga agir em cima. `SymbolProfile` nao
    carrega o proprio simbolo (a chave do dicionario e' que carrega), e uma
    mensagem que diz 'o perfil' sem dizer QUAL nao ajuda ninguem as 9h05.
    Perfil montado a mao (teste, script de laboratorio) nao esta' em tabela
    nenhuma e devolve `None`."""
    for tabela in (FUTURES_PROFILES, PROFILES):
        for symbol, candidato in tabela.items():
            if candidato is profile:
                return symbol
    return "?"


def _checa_economia_do_terminal(profile: SymbolProfile,
                                trade_tick_value: float,
                                trade_tick_size: float) -> None:
    """Recusa uma economia que nem chega a ser um numero utilizavel, ANTES
    de qualquer divisao.

    Existe porque o caminho seguinte (`trade_tick_value / trade_tick_size`,
    tanto no guard do valor do ponto quanto em `IntradayCostModel.
    from_symbol_info`) rebentava em `ZeroDivisionError` cru, sem dizer o
    simbolo nem o que fazer -- e `market_data_intraday.mt5_source.
    symbol_economics` devolve `float(info.trade_tick_value)` SEM validar
    nada. O caso comum nao e' hipotetico: o MT5 reporta `trade_tick_value=0`
    para simbolo que ainda nao foi sincronizado/selecionado no Market Watch,
    e um `point_value_brl=0` faria TODO P&L da run dar R$0,00 -- portao de
    capital cego, disjuntor que nunca dispara, diario cheio de trade
    gratuito. Zero e' o pior valor possivel justamente por ser silencioso."""
    for nome, valor in (("trade_tick_value", trade_tick_value),
                        ("trade_tick_size", trade_tick_size)):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            numero = math.nan
        if not math.isfinite(numero) or numero <= 0:
            symbol = _symbol_do_perfil(profile)
            raise SymbolEconomicsError(
                f"config_for({symbol}): a economia lida do terminal traz "
                f"`{nome}={valor!r}`, que nao e' um numero positivo -- nao da' "
                f"para montar custo nenhum com isso (0 zeraria o P&L da run "
                f"inteira em silencio; dividir por 0 quebraria com traceback "
                f"sem contexto).\n"
                f"CAUSA MAIS COMUM: o simbolo {symbol!r} nao esta' sincronizado "
                f"no terminal MT5 -- abra o MT5, coloque-o no Market Watch, "
                f"espere ele cotar, e inicie o robo de novo. Se o terminal "
                f"estiver certo e o numero ainda vier assim, o simbolo pedido "
                f"nao existe nesse servidor."
            )


def _confere_valor_do_ponto(profile: SymbolProfile,
                            trade_tick_value: float,
                            trade_tick_size: float) -> None:
    """O valor do ponto lido do terminal tem de bater com o declarado em
    `core.instruments` -- senao a run PARA (2026-09-09).

    ---------------------------------------------------------------------
    DECISAO (revisada 2026-09-09): ao vivo tambem RECUSA. Nao avisa-e-segue.
    ---------------------------------------------------------------------
    A objecao obvia e' o item 6.15 de `LICOES_DE_PRODUCAO.md` -- robo que
    para produz janela censurada, que depois se le como edge negativo. Ela
    NAO se aplica aqui, e a diferenca e' o que sustenta esta decisao:

      * o item 6.15 fala de robo que emudece NO MEIO do pregao, em silencio,
        por portao de caixa -- ninguem fica sabendo, e o numero sobrevive
        parecendo medicao. Aqui a recusa e' na MONTAGEM DA CONFIG, antes de
        existir ordem, e e' barulhenta: o processo do slot morre com
        traceback no log e o cartao do painel fica 'parado'. Falha alta e
        falha silenciosa nao tem o mesmo custo;
      * nao ha "seguir com o numero do perfil" que seja seguro, porque
        divergir nao diz QUAL das duas fontes esta' errada. Se o perfil
        estiver desatualizado e a corretora tiver mudado a especificacao, o
        numero do perfil e' o errado -- e o robo operaria um pregao inteiro
        com P&L, portao de caixa e disjuntor calculados sobre o
        multiplicador errado. Escolher em silencio qual das duas fontes
        vence e' exatamente a familia dos itens 5.7/5.19 (52 pontos de WDO@
        virando R$52,00 no lugar de R$520,00, em tres caminhos diferentes);
      * o erro que essa escolha silenciosa causa nao e' pequeno nem
        recuperavel dentro do pregao: as duas divergencias possiveis valem
        um fator de 5 (contrato cheio no lugar do mini) ou zeram tudo
        (terminal dessincronizado). Um pregao nao operado se recupera no
        dia seguinte; um pregao operado com o disjuntor lendo 1/10 da perda
        real foi como a conta zerou em 2026-08-28.

    O que a decisao CUSTA, e fica registrado: um dia em que a Rico publique
    a especificacao arredondada de outra forma (ex.: `trade_tick_value`
    com uma casa a menos) o robo nao sobe, e o conserto exige alguem
    editando `core.instruments`. E' aceito -- ver a banda em
    `TOLERANCIA_VALOR_DO_PONTO`, que e' 800x menor que a menor confusao
    real de instrumento, entao esse falso positivo teria de vir de um
    arredondamento grosseiro, nao de ruido.

    So' para FUTURO, de proposito. Em acao o preco ja e' em reais por acao,
    todo papel da B3 reporta a razao 1,0 e o perfil declara 1,0 -- checar la
    so' criaria um modo de falha novo (script de laboratorio que passa uma
    economia sintetica) sem proteger de nada que ja tenha acontecido."""
    if not profile.is_futures or profile.point_value_brl is None:
        return
    derivado = trade_tick_value / trade_tick_size
    declarado = float(profile.point_value_brl)
    if abs(derivado - declarado) <= max(1e-9, TOLERANCIA_VALOR_DO_PONTO * abs(declarado)):
        return
    symbol = _symbol_do_perfil(profile)
    fator = derivado / declarado if declarado else float("inf")
    raise SymbolEconomicsError(
        f"config_for({symbol}): as duas fontes do VALOR DO PONTO nao batem, "
        f"e seguir assim produziria P&L de outro instrumento.\n"
        f"  esperado (declarado): R${declarado:.6g} por ponto  <- "
        f"`core.instruments.FUTUROS[{symbol!r}].point_value_brl`\n"
        f"  recebido (terminal):  R${derivado:.6g} por ponto  <- "
        f"trade_tick_value={trade_tick_value!r} / trade_tick_size={trade_tick_size!r}\n"
        f"  o recebido e' {fator:.4g}x o esperado (tolerancia: "
        f"{TOLERANCIA_VALOR_DO_PONTO:.3%}).\n"
        f"O QUE FAZER -- so' uma das duas esta' errada, e a run nao tem como "
        f"adivinhar qual:\n"
        f"  (a) se o TERMINAL esta' certo (a corretora mudou a especificacao, "
        f"ou o simbolo aponta para outro contrato -- DOL vale 5x o WDO, IND "
        f"5x o WIN), corrija `src/core/instruments.py` -> "
        f"`FUTUROS[{symbol!r}].point_value_brl` para R${derivado:.6g}. O perfil "
        f"do backtest e o robo do registry leem DALI, entao um numero so' "
        f"conserta os dois lados;\n"
        f"  (b) se o PERFIL esta' certo, o terminal e' que respondeu por outro "
        f"simbolo -- confira {symbol!r} no Market Watch do MT5 e o "
        f"`--mt5-symbol-map` do slot.\n"
        f"NAO desligue esta conferencia para o robo subir: o numero errado "
        f"nao para no P&L, ele cega tambem o portao de capital e o disjuntor "
        f"(itens 5.7/5.19 de LICOES_DE_PRODUCAO.md)."
    )


def config_for(
    profile: SymbolProfile,
    trade_tick_value: float,
    trade_tick_size: float,
    default_quantity: int | None = None,
    target_fills_as_maker: bool = False,
    preco_atual: float | None = None,
    initial_capital: float | None = None,
    limit_fill_capped_by_volume: bool = True,
    enforce_capital_minimo: bool | None = None,
    max_open_contracts: int | None = None,
    cash_brl: float | None = None,
    margin_per_contract_brl: float | None = None,
    enforce_capital_cap: bool | None = None,
    margin_buffer: float = MARGIN_BUFFER_FUTUROS,
    target_slippage_ticks: float | None = None,
    limit_fill_at_bar_open: bool = False,
    anchor_exits_at_fill: bool = False,
    queue_ahead_qty: float | None = None,
    exit_queue_ahead_qty: float | None = None,
    exit_arms_at_fill: bool = False,
) -> IntradayBacktestConfig:
    """Monta o `IntradayBacktestConfig` de um perfil + a economia do simbolo
    lida do terminal (`market_data_intraday.mt5_source.symbol_economics`).

    Existe para o backtest e a operacao ao vivo montarem a config pelo MESMO
    caminho — `default_quantity` so e' sobrescrevivel porque ao vivo a
    quantidade sai do caixa destinado ao robo, nao do lote de referencia do
    perfil (ver `live/intraday_runtime.py`).

    `initial_capital`: sem default fixo (ver o motivo em `IntradayBacktestConfig.
    initial_capital`) -- passe-o explicitamente (backtest ao vivo sempre
    sobrescreve depois, via `IntradayLiveRuntime`) OU passe `preco_atual` para
    este montador computar o minimo real do simbolo (`capital_minimo_brl`).
    Passar os dois e' erro do chamador.

    `limit_fill_capped_by_volume`: `True` por padrao desde 2026-08-23 --
    PADRAO DE TESTE (pedido do dono: sem isso o percentual de acerto medido
    se afasta da realidade, porque assume que toda ordem parada preenche
    100% no toque, sem checar se existiu negocio real com volume suficiente).
    So' desliga quem passar `False` explicitamente (ex.: comparacao ad-hoc
    contra o comportamento antigo).

    `max_open_contracts`: teto de contratos simultaneos para ESTA run.
    `None` (default) usa o teto OFICIAL declarado no perfil
    (`SymbolProfile.max_open_contracts`, `None` em toda acao = sem teto).
    Passar um valor explicito e' como se roda com FOLGA deliberada (o plano
    da Copa calibra com 12 no WIN e 4 no WDO, e confirma no teto oficial 15/5
    depois) ou uma escada de sensibilidade -- o teto nunca e' constante no
    codigo da estrategia, e' entrada, porque os numeros de 2025 podem mudar
    antes da competicao de 2026.

    `enforce_capital_minimo`: `None` (default) resolve por INSTRUMENTO --
    `True` para acao (o caixa e' o limitador de verdade: `capital_minimo_brl`
    e' o custo de 2 lotes de 100 acoes) e `False` para um instrumento com
    teto de CONTRATOS declarado, onde `capital_minimo_brl` nao significa nada
    (o simulador da Copa declara margem infinita e nao tem saldo ficticio; o
    unico limitador la' e' quantos contratos ficam abertos ao mesmo tempo).
    `True`/`False` explicito sempre vence.

    Historico do `True` de acao, mantido -- desde 2026-08-23 e' a MESMA
    regra que `live.intraday_runtime.IntradayLiveRuntime._check_capital` ja
    aplica ao vivo (recusar o pregao se o caixa nao cobrir `capital_minimo_
    brl`), agora tambem no backtest (`run_intraday_backtest`). Achado ao
    medir CLSC4 com `initial_capital` incompativel com o preco dela: sem
    isto, o backtest deixava a estrategia "comprar" um lote que a conta nao
    pagaria de verdade, produzindo MaxDD abaixo de -100% (impossivel sem
    margem) -- o robo ao vivo jamais teria essa chance. So' desliga quem
    passar `False` explicitamente.

    `cash_brl`/`margin_per_contract_brl` (2026-08-26, ADITIVO -- objetivo
    novo do dono de escalar contratos de futuro sozinho conforme o
    caixa/margem permitir, ver `strategy.daytrade.base.contracts_from_
    capital`): caminho OPCIONAL para computar `max_open_contracts`
    AUTOMATICAMENTE a partir do capital, em vez de um numero fixo digitado
    a mao. So' entra em acao quando as TRES condicoes valem ao mesmo tempo:
    (1) os dois foram passados, (2) `max_open_contracts` explicito NAO foi
    passado (explicito sempre vence -- mesma regra de sempre), e (3)
    `profile.is_futures` (o teto por capital nao significa nada numa acao,
    que e' limitada por caixa via `enforce_capital_minimo`). Quando entra,
    o teto OFICIAL do perfil (`profile.max_open_contracts`, ex.: 15 no WIN,
    5 no WDO) e' usado como `hard_cap` de `contracts_from_capital` -- o robo
    escala com o capital, mas nunca ALEM do teto declarado. Passar os dois
    parametros para um perfil de acao (`is_futures=False`) e' erro do
    chamador (`ValueError`) -- confundir os dois seria misturar dois
    limitadores que nao tem nada a ver um com o outro.

    `enforce_capital_cap`/`margin_buffer` (2026-08-28, DEFAULT-ON para
    futuro -- incidente REAL: `wdo_grid_reload_maker`, WDO@, R$300, zerou a
    conta ao vivo abrindo 2 contratos simultaneos porque o UNICO teto que a
    config carregava era `max_open_contracts=5`, o numero REGULATORIO da
    Copa BTG, sem nenhuma relacao com o caixa real do dono). Diferente de
    `cash_brl`/`margin_per_contract_brl` acima (que computam um `max_open_
    contracts` ESTATICO, uma foto tirada 1x aqui dentro), este caminho liga
    `IntradayBacktestConfig.margin_per_contract_brl` (a partir de `profile.
    margin_per_contract_brl`, sem precisar de nenhum parametro novo com o
    valor -- ja esta' no perfil) para o motor recalcular o teto por capital a
    CADA barra, contra o caixa DE VERDADE (`initial_capital + realized_pnl`
    da propria run, ver `IntradaySessionMachine._cap_capital_atual`), com a
    reserva de seguranca de `strategy.daytrade.base.RESERVA_CAIXA_SEGURANCA`
    ja aplicada.

    `None` (default) ativa sozinho quando `profile.is_futures` e `profile.
    margin_per_contract_brl` sao conhecidos -- e' esse o caminho que
    `scripts/run_live.py::build_intraday` usa para montar a config real (sem
    passar nenhum destes parametros novos), entao a operacao ao vivo herda a
    protecao automaticamente, sem precisar de nenhuma mudanca em `live/`.
    `False` explicito desliga (ambiente de margem simulada infinita, Copa
    BTG, ou sensibilidade deliberada sem o teto por caixa). `True` explicito
    sem `profile.margin_per_contract_brl` conhecido e' erro do chamador
    (`ValueError`) -- pedir um teto que nao ha dado para calcular seria um
    "sem teto" silencioso disfarcado de pedido atendido.

    `target_slippage_ticks` (2026-09-08): quantos TICKS a saida por ALVO
    paga de deslize quando ela e' modelada como maker
    (`target_fills_as_maker=True`). `None` (default) RESOLVE SOZINHO:

      * `target_fills_as_maker=True`  -> `costs.DESLIZE_ALVO_NATIVO_TICKS`
        (1,0 tick). Um alvo maker que o robo nao varre e' o `tp` NATIVO
        amarrado no request da entrada, e a corretora o executa como gatilho
        a mercado: 8 de 8 saidas do WDO F1 em 2026-09-08 sairam PIORES que o
        nivel pedido, R$45,00 num pregao de -R$116,00 (item 4.8 de
        LICOES_DE_PRODUCAO.md).
      * `target_fills_as_maker=False` -> `0.0`. Ali o alvo ja e' uma ordem a
        MERCADO e ja paga `costs.slippage_ticks`; somar os dois contaria o
        mesmo custo duas vezes.

    LIGADO POR DEFAULT, e nao opt-in, por decisao de metodo: "parametro de
    seguranca opcional e' parametro desligado" (item 3.8 de
    LICOES_DE_PRODUCAO.md) -- e este e' o caminho que TODO backtest, sombra e
    a producao (`scripts/run_live.py::build_intraday`) usam para montar a
    config. Passe `0.0` EXPLICITO para reproduzir o motor antigo (a linha
    "sem deslize" de uma comparacao), ou outro numero para medir
    sensibilidade -- a amostra que ancora o 1,0 tem n=8, entao a
    sensibilidade importa.

    `limit_fill_at_bar_open`/`anchor_exits_at_fill` (2026-09-08, pergunta do
    dono: "e se o robo considerasse o preco em que ENTROU DE FATO para
    posicionar alvo e stop?"): repassados crus para os campos de mesmo nome
    de `IntradayBacktestConfig` -- o primeiro faz a ordem-limite atravessada
    preencher na ABERTURA da barra (melhor que o nivel) em vez de no nivel
    exato; o segundo translada alvo e stop para o preco preenchido,
    preservando a distancia original. Os dois ficam DESLIGADOS por default,
    ao contrario de `target_slippage_ticks` acima: aquele corrige um custo
    MEDIDO que o motor nao cobrava (nao ligar seria continuar otimista);
    estes dois mudam a GEOMETRIA de toda medicao ja' feita, e ligar por
    default tornaria numero novo incomparavel com numero antigo sem ninguem
    perceber. Ver as docstrings dos campos.

    `queue_ahead_qty`/`exit_queue_ahead_qty` (2026-09-09): quanta FILA existe
    na frente da nossa ordem-limite, na ENTRADA e na SAIDA. `None` (default)
    RESOLVE SOZINHO pela calibracao do simbolo em `backtest.intraday.
    fidelidade.FIDELIDADE` -- WDO@ recebe 438/489, medidos em operacao real
    por Kaplan-Meier; simbolo sem medicao fica em 0,0 (o motor otimista de
    ate 2026-09-08), nunca herdando a fila de outro instrumento.

    LIGADO POR DEFAULT pelo MESMO precedente de `target_slippage_ticks` acima
    (item 3.8 de LICOES_DE_PRODUCAO.md: "parametro de seguranca opcional e'
    parametro desligado"), e pelo mesmo motivo concreto: `queue_ahead_qty`
    existia desde 2026-08-26 e ficou UM MES no default 0,0 porque nenhum
    chamador o passava -- todo robo maker medido nesse periodo encheu entrada
    de graca. Aqui e' este montador que decide, entao backtest, sombra e
    producao (`scripts/run_live.py::build_intraday`) herdam juntos.

    O tamanho do erro que isso corrige nao e' de magnitude, e' de SINAL:
    simulando o pregao real de 2026-09-09 (WDO F1, 34 operacoes, -R$3,00 por
    operacao), o motor sem fila devolvia +R$3,82 por operacao com 97,8% de
    preenchimento; com 438/489 devolve -R$3,48 com 44,1%. Passe `0.0`
    EXPLICITO nos dois para reproduzir o motor antigo (a linha "sem fila" de
    uma comparacao), ou outro numero para sensibilidade -- a amostra da saida
    tem n=25, entao a sensibilidade importa. Ver a docstring de
    `backtest.intraday.fidelidade` para o metodo, o refinamento REFUTADO (so'
    o agressor contrario consome a fila: 99,3% do volume no nosso nivel ja'
    e' dele) e as quatro limitacoes declaradas.

    O teto por capital NUNCA aumenta `max_open_contracts` (o campo que este
    montador resolve logo acima, via `teto`) -- so' pode ENCOLHER o que a
    run permitiria durante a execucao, dinamicamente, conforme o caixa muda
    (ver a docstring do campo em `IntradayBacktestConfig`)."""
    # A fila resolve ANTES de qualquer outra coisa porque depende do SIMBOLO,
    # e o simbolo so' existe pela identidade do perfil nas tabelas deste
    # modulo (`SymbolProfile` nao carrega o proprio simbolo). Perfil montado
    # a mao (teste, laboratorio) devolve "?" e cai no ramo "sem calibracao",
    # que e' a resposta certa: um perfil sintetico nao tem pregao real
    # medido, e emprestar a fila do WDO@ para ele seria inventar numero.
    fid = fidelidade_ou_none(_symbol_do_perfil(profile))
    if queue_ahead_qty is None:
        queue_ahead_qty = fid.queue_ahead_qty if fid else 0.0
    if exit_queue_ahead_qty is None:
        exit_queue_ahead_qty = fid.exit_queue_ahead_qty if fid else 0.0
    if target_slippage_ticks is None:
        target_slippage_ticks = (DESLIZE_ALVO_NATIVO_TICKS if target_fills_as_maker else 0.0)
    if enforce_capital_cap is None:
        enforce_capital_cap = profile.is_futures and profile.margin_per_contract_brl is not None
    if enforce_capital_cap and (not profile.is_futures or profile.margin_per_contract_brl is None):
        raise ValueError(
            "config_for: enforce_capital_cap=True pedido, mas o perfil nao declara "
            "`is_futures`+`margin_per_contract_brl` -- nao ha dado para calcular o "
            "teto por capital (pedir um teto sem como calcula-lo viraria 'sem teto' "
            "silencioso)."
        )
    if (cash_brl is None) != (margin_per_contract_brl is None):
        raise ValueError(
            "config_for: passe `cash_brl` e `margin_per_contract_brl` JUNTOS "
            "(um sem o outro nao computa nada) ou nenhum dos dois."
        )
    if cash_brl is not None and not profile.is_futures:
        raise ValueError(
            "config_for: `cash_brl`/`margin_per_contract_brl` so fazem sentido "
            "para um perfil de FUTURO (`profile.is_futures=True`) -- uma acao e' "
            "limitada por caixa (`enforce_capital_minimo`/`capital_minimo_brl`), "
            "nunca por margem-por-contrato."
        )
    if initial_capital is None:
        if preco_atual is None:
            raise ValueError(
                "config_for precisa de `initial_capital` explicito OU `preco_atual` "
                "(para computar capital_minimo_brl) -- nao ha mais default implicito."
            )
        initial_capital = capital_minimo_brl(preco_atual)
    elif preco_atual is not None:
        raise ValueError("config_for: passe `initial_capital` OU `preco_atual`, nao os dois.")
    teto = profile.max_open_contracts if max_open_contracts is None else max_open_contracts
    if (
        max_open_contracts is None
        and profile.is_futures
        and cash_brl is not None
        and margin_per_contract_brl is not None
    ):
        teto = contracts_from_capital(
            cash_brl=cash_brl,
            margin_per_contract_brl=margin_per_contract_brl,
            hard_cap=profile.max_open_contracts,
        )
    if enforce_capital_minimo is None:
        enforce_capital_minimo = profile.max_open_contracts is None
    # A economia lida do terminal e' conferida em DOIS passos, nesta ordem,
    # e os dois levantam `SymbolEconomicsError` (ver a classe e as
    # docstrings dos dois helpers, onde mora a decisao de RECUSAR em vez de
    # avisar-e-seguir, e a base da tolerancia):
    #   1. ela e' um numero utilizavel? (>0 e finito -- senao a divisao
    #      abaixo rebentaria em ZeroDivisionError sem contexto, e um zero
    #      passaria zerando o P&L da run inteira em silencio);
    #   2. em FUTURO, ela concorda com o valor do ponto declarado em
    #      `core.instruments`? Duas fontes para o MESMO numero, e "um numero
    #      declarado em dois lugares e' um numero que vai divergir" e' a
    #      primeira frase deste modulo.
    _checa_economia_do_terminal(profile, trade_tick_value, trade_tick_size)
    _confere_valor_do_ponto(profile, trade_tick_value, trade_tick_size)

    if profile.price_tick_size is not None:
        # Preserva `point_value_brl` (= tick_value/tick_size) ao trocar so' a
        # GRADE de preco: reescala `trade_tick_value` junto. Sem isto, um
        # override de tick_size mudaria o valor do ponto e o P&L inteiro --
        # exatamente o oposto do problema que o override existe para
        # resolver (ver `SymbolProfile.price_tick_size`).
        point_value = trade_tick_value / trade_tick_size
        trade_tick_size = profile.price_tick_size
        trade_tick_value = point_value * profile.price_tick_size
    costs = IntradayCostModel.from_symbol_info(
        trade_tick_value=trade_tick_value,
        trade_tick_size=trade_tick_size,
        fee_round_trip_brl=profile.fee_round_trip_brl,
        exchange_fee_pct_per_leg=profile.exchange_fee_pct_per_leg,
        target_slippage_ticks=target_slippage_ticks,
        fidelidade_calibrada=fid is not None,
    )
    return IntradayBacktestConfig(
        costs=costs,
        initial_capital=initial_capital,
        # O motor chama este campo de CORTE DE ACHATAMENTO (ver a docstring
        # de `IntradayBacktestConfig.session_end_time`), que NAO e' o fim do
        # pregao -- ver `SymbolProfile.flatten_cut_time`.
        session_end_time=(profile.flatten_cut_time or profile.session_end_time),
        session_end_policy=profile.session_end_policy,
        default_quantity=(profile.default_quantity if default_quantity is None else default_quantity),
        target_fills_as_maker=target_fills_as_maker,
        limit_fill_capped_by_volume=limit_fill_capped_by_volume,
        enforce_capital_minimo=enforce_capital_minimo,
        max_open_contracts=teto,
        margin_per_contract_brl=(profile.margin_per_contract_brl if enforce_capital_cap else None),
        margin_buffer=margin_buffer,
        limit_fill_at_bar_open=limit_fill_at_bar_open,
        anchor_exits_at_fill=anchor_exits_at_fill,
        queue_ahead_qty=queue_ahead_qty,
        exit_queue_ahead_qty=exit_queue_ahead_qty,
        exit_arms_at_fill=exit_arms_at_fill,
    )


def cost_model_from_profile(profile: SymbolProfile) -> IntradayCostModel | None:
    """`IntradayCostModel` montado SO' com o que o PERFIL declara -- sem
    terminal, sem processo de robo vivo, sem I/O nenhum.

    Existe para um consumidor que precisa converter ponto em real e cobrar as
    mesmas taxas que o motor cobra, num momento em que `config_for` nao esta'
    disponivel: ele exige `trade_tick_value`/`trade_tick_size` lidos do MT5
    (`market_data_intraday.mt5_source.symbol_economics`), e ha caminhos que
    rodam com o terminal FECHADO e com o processo do robo ja' morto. O caso
    que motivou isto e' a rotina de remocao de robo
    (`dashboard/live_teardown.py::_encerrar_posicao_sombra`), que credita
    resultado no caixa de sombra: ate 2026-09-09 ela creditava BRUTO,
    enquanto um fechamento normal (`live.intraday_runtime._on_closed`) paga
    corretagem e emolumentos -- duas rotas para o mesmo evento com
    contabilidade diferente.

    O que ele NAO tem, e o chamador precisa saber:

      * `slippage_ticks=0`. Slippage e' um ajuste no PRECO de execucao, e
        quem chama aqui ja' tem o preco (ou uma marcacao a mercado). Cobrar
        os dois contaria o custo duas vezes;
      * `target_slippage_ticks=0`. O deslize do alvo NATIVO so' faz sentido
        numa saida por alvo simulada pelo motor (ver `costs.
        DESLIZE_ALVO_NATIVO_TICKS`), nao num fechamento a mercado pedido
        pelo dono;
      * `tick_size` e' o do perfil quando ele declara um
        (`price_tick_size`), senao R$0,01 -- o passo de qualquer acao da B3.
        Como as duas parcelas de slippage estao zeradas, este campo nao
        entra em conta nenhuma de `fees_round_trip_brl`/`gross_pnl_brl`; ele
        so' esta' preenchido porque o dataclass exige.

    `None` quando o perfil nao declara `point_value_brl` -- "nao sei quanto
    vale um ponto" nunca pode virar 1,0 por default (erra 10x num WDO@)."""
    if profile.point_value_brl is None:
        return None
    return IntradayCostModel(
        point_value_brl=float(profile.point_value_brl),
        tick_size=float(profile.price_tick_size or ACAO_B3_PRICE_TICK_SIZE),
        fee_round_trip_brl=profile.fee_round_trip_brl,
        slippage_ticks=0.0,
        exchange_fee_pct_per_leg=profile.exchange_fee_pct_per_leg,
        target_slippage_ticks=0.0,
    )
