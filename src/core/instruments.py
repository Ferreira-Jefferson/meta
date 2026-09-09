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
