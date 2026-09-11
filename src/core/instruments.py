"""Economia de um INSTRUMENTO -- quanto vale 1 ponto, em que passo de preco
ele negocia e quanta margem 1 contrato exige.

Mora em `core/` por imposicao da regra 1 do AGENTS.md, e nao por gosto de
camada: estes numeros sao propriedade do INSTRUMENTO (dois robos no mesmo
simbolo tem obrigatoriamente o mesmo valor de ponto), e DUAS features
precisam deles ao mesmo tempo --

  * `backtest.intraday.profiles.SymbolProfile`, que monta custo/tamanho de
    posicao para o motor e para a operacao ao vivo;
  * `strategy.daytrade.registry`, que instancia o robo de producao com o
    dimensionamento por margem/risco ligado (`_KWARGS_PADRAO`).

`strategy/` e' feature e nao pode importar `backtest/`, entao ate 2026-09-09
o registry REDIGITAVA os mesmos numeros (WDO@ 10,0/150,0; WIN@ 0,20/100,0) e
o que impedia os dois lados de divergirem era um TESTE de amarracao
(`tests/test_intraday_profiles.py::test_registry_espelha_a_economia_do_
perfil_do_instrumento`). Teste de amarracao e' rede, nao conserto: ele avisa
DEPOIS que alguem digitou o numero errado, e so' se a suite rodar. A propria
regra 1 ja prescrevia a saida -- "se uma feature precisa de dado de outra, o
dado sobe para `core/`" -- e e' isto aqui.

O que NAO entra nesta tabela, de proposito:

  * **Teto de contratos** (`SymbolProfile.max_open_contracts`, 15 no WIN@ e 5
    no WDO@). Nao e' economia do instrumento: e' o REGULAMENTO da Copa BTG
    2025. O mesmo WDO@ operado fora da competicao nao tem esse teto, e um
    numero de regulamento numa tabela de instrumento convidaria alguem a
    trata-lo como fato do mercado.
  * **Custo/tarifa** (`fee_round_trip_brl`, `exchange_fee_pct_per_leg`). E'
    propriedade da CORRETORA e do regime tributario, nao do contrato -- muda
    de Rico para Clear sem o instrumento mudar nada.
  * **Horario de pregao** (`session_end_time`/`session_start_time`). E' do
    CALENDARIO (ver `core.b3_session`), e o perfil ja resolve isso.

Nao ha entrada de ACAO aqui: toda acao da B3 em lote padrao tem a MESMA
economia (1 ponto = R$1,00, passo de R$0,01, sem margem por contrato), entao
uma tabela por papel teria dez linhas identicas -- as constantes
`ACAO_B3_*` abaixo dizem a mesma coisa uma vez so'.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


#: 1 ponto de uma ACAO da B3 vale R$1,00 -- o preco ja e' em reais por acao.
#: Constante, e nao entrada por papel, porque vale para os dez papeis da
#: familia gremah e para qualquer papel que entre depois.
ACAO_B3_POINT_VALUE_BRL = 1.0

#: Passo de preco de qualquer acao da B3: R$0,01.
ACAO_B3_PRICE_TICK_SIZE = 0.01


@dataclass(frozen=True)
class InstrumentEconomics:
    """A economia de UM contrato de futuro, num lugar so'.

    Os tres campos sao obrigatorios e positivos, e o `__post_init__` recusa
    qualquer outra coisa. O motivo de cada guard esta' escrito no proprio
    erro; em resumo, os tres ja custaram incidente:

      * `point_value_brl` -- o multiplicador dos itens 5.7/5.19 de
        `LICOES_DE_PRODUCAO.md`: 52 pontos de WDO@ contabilizados como
        R$52,00 em vez de R$520,00, em TRES caminhos de codigo diferentes.
        Chutar 1,0 erra por 10x num WDO@.
      * `margin_per_contract_brl` -- ausente, o teto de contratos por caixa
        fica desligado e so' sobra o teto regulatorio, que nao conhece o
        dinheiro do dono. Foi esse o estado do WDO F1 no dia em que zerou a
        conta (2026-08-28).
      * `price_tick_size` -- o passo do contrato REAL com vencimento, que a
        serie continua NAO reporta direito (medido 2026-08-25: `WIN@`
        devolve 1,0 e `WDO@`, 0,001, contra 5,0 e 0,5 de verdade). Uma ordem
        limite fora da grade nao existe no book, e o backtest preencheria
        uma ordem que a corretora recusaria.
    """

    symbol: str
    #: Quantos REAIS vale 1 PONTO de preco, por contrato.
    point_value_brl: float
    #: Passo de preco do contrato REAL com vencimento (nao o que a serie
    #: continua reporta -- ver a nota acima).
    price_tick_size: float
    #: Margem exigida pela corretora para segurar 1 contrato, em reais.
    #: VALOR APROXIMADO, nao verificado via MT5 (`order_calc_margin` nao e'
    #: consultado neste repo -- ver a nota longa em `strategy.daytrade.base.
    #: MARGIN_BUFFER_FUTUROS`): vem da margem PROMOCIONAL de day trade que o
    #: dono relatou em 2026-08-27 (~R$100 mini-indice, ~R$150 mini-dolar).
    margin_per_contract_brl: float

    def __post_init__(self) -> None:
        for campo in ("point_value_brl", "price_tick_size", "margin_per_contract_brl"):
            valor = getattr(self, campo)
            if valor is None or float(valor) <= 0:
                raise ValueError(
                    f"InstrumentEconomics({self.symbol!r}): `{campo}` tem de ser "
                    f"> 0, recebeu {valor!r} -- ver a docstring da classe para o "
                    f"incidente que cada um destes campos ja custou."
                )

    @property
    def tick_value_brl(self) -> float:
        """Quantos reais vale 1 TICK (o que o terminal MT5 chama de
        `trade_tick_value`). Derivado, nunca declarado: declarar os tres
        numeros -- ponto, tick e valor do tick -- deixaria dois deles livres
        para contradizer o terceiro."""
        return self.point_value_brl * self.price_tick_size


#: Mini-futuros da B3, series CONTINUAS (`@` = o MT5 emenda os vencimentos).
#: FONTE DA VERDADE dos tres numeros -- `backtest.intraday.profiles.
#: FUTURES_PROFILES` e `strategy.daytrade.registry._KWARGS_PADRAO` leem
#: DAQUI, nenhum dos dois redigita.
FUTUROS: dict[str, InstrumentEconomics] = {
    "WIN@": InstrumentEconomics(
        symbol="WIN@",
        # Tick de 5 pts = R$1,00 -> 1 ponto = R$0,20.
        point_value_brl=0.20,
        price_tick_size=5.0,   # WINV26; a continua reporta 1,0
        margin_per_contract_brl=100.0,
    ),
    "WDO@": InstrumentEconomics(
        symbol="WDO@",
        # Tick de 0,5 pt = R$5,00 -> 1 ponto = R$10,00. E' o multiplicador do
        # incidente 5.19: sem ele, 52 pontos de perda viraram R$52,00.
        point_value_brl=10.0,
        price_tick_size=0.5,   # WDOV26; a continua reporta 0,001
        margin_per_contract_brl=150.0,
    ),
}


def economics_for(symbol: str) -> InstrumentEconomics:
    """Economia declarada de um instrumento. `KeyError` (nunca um default
    silencioso) para simbolo desconhecido: assumir a economia de outro
    contrato e' exatamente o erro de 10x que esta tabela existe para
    impedir."""
    try:
        return FUTUROS[symbol]
    except KeyError:
        raise KeyError(
            f"sem economia declarada para o instrumento {symbol!r} -- ver "
            f"`core.instruments.FUTUROS`. Acao da B3 nao entra nessa tabela: "
            f"usa `ACAO_B3_POINT_VALUE_BRL`/`ACAO_B3_PRICE_TICK_SIZE`."
        ) from None


# ---------- regra de ROLAGEM (rollover) dos futuros continuos -----------
#
# Incidente 2026-09-11: `live.broker_mt5.MT5Broker.detect_futures_symbol_map`
# escolhia o contrato corrente por VOLUME RECENTE entre os candidatos —
# criterio que se apoia em ter negocio acontecendo AGORA. Os dois slots de
# WDO@ foram iniciados as 05:48-05:49 UTC, madrugada, mercado fechado em
# TODOS os contratos: sem sinal de volume confiavel, um artefato de barras
# antigas e esparsas do WDOF27 (vencimento jan/2027, morto) bateu por acaso
# o WDOV26 (o certo, out/2026) — os dois robos ficaram a manha inteira sem
# barra nova. O proprio terminal MT5 sabia o certo o tempo todo
# (`symbol_info("WDO@").description` = "... (WDOV26) ..."), so' a funcao
# errou.
#
# Correcao do dono do projeto (2026-09-11): a rolagem da B3 e' CALENDARIO,
# nao mercado — o contrato de um instrumento vence sempre no 1o dia util do
# MES do proprio nome, e daqui sai uma regra fixa por RAIZ que nao depende
# de nenhum negocio ter acontecido. O volume vira FALLBACK, so' usado
# quando o contrato indicado pela data nao tem book de dois lados no
# momento (feriado, atraso da B3) — ver `live.broker_mt5.
# detect_futures_symbol_map`.
#
# Mora aqui, e nao em `live/broker_mt5.py`, pelo mesmo motivo que
# `InstrumentEconomics` mora aqui: e' uma constante do INSTRUMENTO (a B3
# rola o mesmo WDO/WIN pra qualquer robo, qualquer corretora), nao um
# detalhe de como uma funcao de deteccao decide — guardar constante de
# instrumento fora do instrumento e' o padrao que os itens 5.19/5.21/5.22/
# 5.23 de `LICOES_DE_PRODUCAO.md` ja pagaram para aprender.

#: Letra de vencimento B3/CME por MES (1=Jan .. 12=Dez). Convencao fixa da
#: bolsa, igual para qualquer futuro — nao e' escolha deste projeto.
FUTURES_MONTH_LETTERS: tuple[str, ...] = (
    "F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z",
)

#: Em quais MESES (1-12, ordem crescente) cada RAIZ de futuro continuo
#: vence. E' o calendario que decide qual e' o contrato CORRENTE (front
#: month) numa data qualquer, sem depender de volume/book — so'
#: `front_month_contract()` abaixo le esta tabela.
#:
#:   * **WDO** (mini-dolar) rola TODO MES: o contrato do mes N vence no 1o
#:     dia util do proprio mes N, entao o corrente durante o mes N-1
#:     inteiro e' sempre "mes atual + 1". Regra dada pelo dono do projeto,
#:     2026-09-11 (nao medida — e' a regra publicada da B3).
#:   * **WIN** (mini-indice) rola a cada DOIS MESES, so' em meses PARES
#:     (fev/abr/jun/ago/out/dez) — CONFIRMADO contra o terminal MT5 real em
#:     2026-09-11, nao suposto: `symbol_info("WIN@").description` apontava
#:     "WINV26" (out/2026) durante setembro, e entre os candidatos
#:     `WIN[letra][ano]` com book de dois lados (`WING27`=fev/27,
#:     `WINV26`=out/26, `WINZ26`=dez/26) nenhum mes IMPAR aparecia — so' os
#:     pares tem contrato vivo.
FUTURES_ROLLOVER_MONTHS: dict[str, tuple[int, ...]] = {
    "WDO": tuple(range(1, 13)),
    "WIN": (2, 4, 6, 8, 10, 12),
}


def front_month_contract(root: str, today: date) -> str:
    """Codigo do contrato de vencimento (RAIZ+LETRA+ANO2, ex. `"WDOV26"`)
    que a regra FIXA de rolagem da B3 diz que deveria ser o CORRENTE (front
    month) em `today` — nunca uma consulta a corretora, so' calendario, por
    isso e' testavel com data fixa.

    `root` e' a raiz SEM o sufixo `"@"` do ticker continuo (`"WDO"`,
    `"WIN"`) — a mesma raiz que `live.broker_mt5.MT5Broker.
    detect_futures_symbol_map` ja calcula tirando o `"@"` do ticker.

    Regra: o contrato do proprio mes de `today` ja venceu (1o dia util
    daquele mes ja passou, ou e' hoje — a rolagem so' importa na virada do
    mes, nao na hora do dia), entao o corrente e' o PROXIMO mes presente em
    `FUTURES_ROLLOVER_MONTHS[root]`; se nenhum mes do calendario for maior
    que o mes de hoje (ex.: WDO em dezembro, WIN em novembro/dezembro),
    vira o ano e usa o primeiro mes da lista.

    `KeyError` para raiz sem regra declarada — nunca um default silencioso,
    mesma politica de `economics_for` acima."""
    meses = FUTURES_ROLLOVER_MONTHS.get(root)
    if meses is None:
        raise KeyError(
            f"sem regra de rolagem declarada para a raiz {root!r} -- ver "
            f"`core.instruments.FUTURES_ROLLOVER_MONTHS`."
        )
    mes_alvo = next((m for m in meses if m > today.month), None)
    ano_alvo = today.year if mes_alvo is not None else today.year + 1
    if mes_alvo is None:
        mes_alvo = meses[0]
    letra = FUTURES_MONTH_LETTERS[mes_alvo - 1]
    return f"{root}{letra}{ano_alvo % 100:02d}"
