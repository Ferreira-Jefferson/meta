"""FIDELIDADE DE EXECUCAO por SIMBOLO -- quanta fila existe NA FRENTE da
nossa ordem-limite, dos DOIS lados, medida em operacao real.

Este modulo e' a resposta para uma pergunta que o motor respondia com um
otimismo silencioso: "quando o preco TOCA o nivel da minha limite, ela
preenche?". Ate 2026-09-09 a resposta do backtest era SIM, dos dois lados, no
primeiro toque -- como se o book estivesse vazio e a nossa ordem fosse a
primeira da fila. Nao e', e o erro nao e' de magnitude, e' de SINAL: no
pregao aferido abaixo o motor sem fila previa +R$3,82 por operacao num dia
que deu -R$3,00.

O motor ja tinha os dois parametros. O que faltava era o NUMERO:

  * `IntradayBacktestConfig.queue_ahead_qty` (fila da ENTRADA) existe desde
    2026-08-26 e NUNCA foi setado em lugar nenhum do repo -- ficou no default
    `0.0` por um mes inteiro. Toda medicao de robo maker feita nesse periodo
    encheu entrada de graca;
  * `IntradayBacktestConfig.exit_queue_ahead_qty` (fila da SAIDA) nasceu em
    2026-09-09, junto com esta calibracao.

Um parametro sem numero e' um parametro desligado (item 3.8 de
`LICOES_DE_PRODUCAO.md`). Por isso a tabela mora AQUI, e nao num argumento
que cada script lembra ou esquece de passar: `profiles.config_for` le' desta
tabela sozinho, e backtest, sombra e producao herdam juntos -- mesmo
precedente do deslize do alvo nativo (`costs.DESLIZE_ALVO_NATIVO_TICKS`).

## Como os numeros foram medidos (WDO@, 2026-09-09)

Simbolo real `WDOV26`, robo `wdo_grid_reload_maker` (WDO F1), magic
862399285. A janela de reconstrucao e' [2026-09-07, 2026-09-10) -- na
pratica dois pregoes, e a SAIDA so' tem observacao de 09-09 (ver o comentario
na entrada da tabela). Fonte: o terminal MT5, so' leitura --

  * `history_orders_get` da' o instante em que a ordem-limite ENTROU no book
    (`time_setup_msc`) e o instante em que ela preencheu ou foi cancelada
    (`time_done_msc`), mais o estado final (`ORDER_STATE_FILLED` ou nao);
  * `copy_ticks_range` da' todo negocio do dia com preco, volume e flags.

Q_frente de uma ordem = volume que negociou EXATAMENTE NO PRECO DELA entre
esses dois instantes. Ordem que preencheu: a fila valia aquilo. Ordem que foi
cancelada: a fila valia MAIS que aquilo -- e' observacao CENSURADA a direita,
nao descarte.

ESTIMADOR: **Kaplan-Meier**, mediana. Nao e' preciosismo estatistico -- e' a
correcao de um vies que so' anda para um lado. Ordem que preencheu e' ordem
que GANHOU a fila; usar so' as que preencheram (a "estimativa ingenua" da
tabela) joga fora exatamente as de fila grande e SUBESTIMA Q. A diferenca
medida foi de 21% a 24% por lado.

Ordens que preencheram em MENOS de 0,5s sao descartadas: elas ja' estavam
agressivas ao postar (a corretora executou na hora) e nunca entraram em fila
nenhuma -- mante-las como "evento em v=0" derrubaria a mediana por um motivo
que nao e' fila.

    lado     | esperaram | preencheram | censuradas | KM mediana | ingenua | Q1
    ---------|-----------|-------------|------------|------------|---------|-----
    ENTRADA  |    67     |     30      |     37     |    438     |   346   | 194
    SAIDA    |    25     |      8      |     17     |    489     |   374   | 207

(Alem dessas, 38 ordens de entrada e 5 de saida preencheram em menos de
0,5s e foram descartadas pela regra acima.)

A mediana (e nao a media) porque a distribuicao de fila e' de cauda longa: um
unico nivel muito disputado dominaria a media. Q1 fica registrado para quem
quiser rodar a sensibilidade otimista.

## O refinamento que foi MEDIDO e REFUTADO -- nao refaca

Hipotese razoavel: uma limite de VENDA parada na oferta so' e' executada por
quem COMPRA agredindo, entao so' o volume do agressor CONTRARIO deveria
consumir a nossa fila. Se metade do volume da barra fosse do lado errado, o
motor (que desconta o volume INTEIRO) estaria errado e o Q calibrado estaria
absorvendo esse erro disfarcado de tamanho de fila.

Medido no mesmo pregao, com `TICK_FLAG_BUY`/`TICK_FLAG_SELL`: no dia inteiro
o volume se divide em 50,1% comprador / 50,1% vendedor (as flags se
sobrepoem), mas NO NIVEL DA NOSSA PROPRIA ORDEM **99,3% do volume e' do lado
que executa contra nos**. O motivo, obvio depois de ver o numero: a nossa
limite esta' na MELHOR oferta, entao negocio naquele preco e', por definicao,
alguem agredindo a nossa ponta. O motor ja' estava certo ao descontar o
volume inteiro da barra, e nao ha' correcao a fazer.

## Afericao contra o extrato REAL

O robo rodou continuamente das 14:47 as 18:03 de 2026-09-09 -- 34 operacoes,
liquido -R$102,00 (-R$3,00 por operacao), 33,3% de preenchimento como limite
(9 alvos preenchidos contra 18 estouros de prazo e 7 stops). Simulando o
MESMO trecho, geometria T2/S6, `exit_ttl_bars=60`:

    configuracao                          | trades | R$/trade | fill%
    --------------------------------------|--------|----------|------
    REAL (extrato)                        |   34   |  -3,00   | 33,3
    Q_ent=0, Q_sai=0   (motor <=2026-09-08)|   --   |  +3,82   | 97,8
    Q_ent=0, Q_sai=400 (chute)            |   63   |  -0,50   | 44,4
    Q_ent=438, Q_sai=489 (ESTA tabela)    |   42   |  -3,48   | 44,1
    Q_ent=438, Q_sai=600                  |   45   |  -2,94   | 32,4

O motor sem fila nenhuma nao errava a magnitude: errava o SINAL. Com as duas
filas ligadas, encosta no real.

## LIMITACOES -- declaradas, nao escondidas

1. **Praticamente UM pregao.** Um simbolo, um robo, e o lado da SAIDA
   inteiro vem de 2026-09-09. Fila e' propriedade do LIVRO daquele
   instrumento naquele regime de liquidez; nao ha' motivo para supor que o
   numero de hoje valha em marco.
2. **A contagem de operacoes ainda fica ~30% acima da real** (42 simuladas
   contra 34). A fila explica o grosso da diferenca de resultado, nao toda a
   diferenca de comportamento -- sobra mecanismo nao modelado.
3. **O n da SAIDA e' 25.** Pouco. Cada pregao real novo quase dobra a
   amostra, e por isso `scripts/daytrade/wdof1_calibra_fila_real_2026_09_09.
   py` existe: ele RE-DERIVA estes numeros do terminal, para a calibracao ser
   refrescada em vez de envelhecer aqui dentro.
4. **O Q=600 da ultima linha da afericao foi escolhido DEPOIS de ver qual
   encaixava melhor.** Isso e' AJUSTE, nao validacao, e e' exatamente por
   isso que o valor adotado na tabela e' o **489 do Kaplan-Meier** -- uma
   estimativa que tem metodo -- e nao o 600 que melhor encaixa num n=34.
   Escolher o parametro que melhor reproduz a amostra que se quer explicar
   e' o mecanismo classico de fabricar concordancia.

## O que NAO entra aqui

  * **Deslize do alvo nativo** (`costs.DESLIZE_ALVO_NATIVO_TICKS`). E' o
    preco EXECUTADO estar pior que o pedido; fila e' SE a ordem executa. Dois
    custos independentes, e o alvo fatiado (ordem-limite real no livro)
    justamente paga fila e nao paga deslize.
  * **Economia do instrumento** (valor do ponto, tick, margem). Mora em
    `core.instruments`, e' propriedade do CONTRATO. Fila e' propriedade do
    LIVRO -- muda com a liquidez do dia sem o contrato mudar nada.
  * **Simbolo sem operacao real propria.** Nao ha' entrada "generica" nem
    default: sem pregao real medido, nao ha' numero, e `config_for` deixa os
    dois em 0,0 (o motor antigo, otimista) em vez de emprestar a fila do
    WDO@ para uma acao de centavos -- Gremah roda em acao da B3 e CopaWin no
    WIN@, e nenhum dos dois foi medido. Emprestar seria inventar. O que esse
    0,0 NAO pode ser e' silencioso: ele viaja como `IntradayCostModel.
    fidelidade_calibrada=False` ate' a TABELA PADRAO, que carimba `fila NAO
    CALIBRADA` na linha. Uma linha sem carimbo nenhum e' indistinguivel de
    uma linha que ninguem sabe se esta certa, e foi assim que o
    `queue_ahead_qty` ficou um mes desligado sem ninguem notar.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FidelidadeExecucao:
    """A fidelidade de execucao de UM simbolo: os dois tamanhos de fila mais
    a PROCEDENCIA deles.

    A procedencia (`medido_em`, `n_*`, `estimador`) e' campo obrigatorio, e
    nao comentario, por um motivo pratico: estes numeros vao envelhecer, vao
    ser re-derivados com amostra maior, e quem ler um resultado de backtest
    daqui a tres meses precisa poder perguntar ao proprio codigo "de quando
    e' esta fila, e com quantas ordens?". Um numero sem procedencia num
    modelo de custo vira folclore em duas semanas.
    """

    symbol: str
    #: Fila na frente da ordem-limite de ENTRADA, em contratos/acoes.
    #: Alimenta `IntradayBacktestConfig.queue_ahead_qty`.
    queue_ahead_qty: float
    #: Fila na frente da fatia de SAIDA (alvo fatiado como ordem-limite
    #: real no livro). Alimenta `IntradayBacktestConfig.exit_queue_ahead_qty`.
    exit_queue_ahead_qty: float
    #: Data do pregao de onde a amostra saiu (`AAAA-MM-DD`).
    medido_em: str
    #: Ordens de ENTRADA que de fato ESPERARAM em fila (>=0,5s) / quantas
    #: dessas preencheram. A diferenca sao as observacoes CENSURADAS.
    n_entrada: int
    n_entrada_fills: int
    #: O mesmo, do lado da SAIDA.
    n_saida: int
    n_saida_fills: int
    #: Como a mediana foi estimada. Texto livre de proposito: o que importa
    #: e' que a linha da tabela diga em voz alta que houve METODO, e qual.
    estimador: str = "Kaplan-Meier (mediana), censura a direita"

    def __post_init__(self) -> None:
        for campo in ("queue_ahead_qty", "exit_queue_ahead_qty"):
            valor = getattr(self, campo)
            if valor is None or float(valor) < 0:
                raise ValueError(
                    f"FidelidadeExecucao({self.symbol!r}): `{campo}` tem de ser "
                    f">= 0, recebeu {valor!r}. Zero e' legitimo (significa "
                    f"'book vazio na nossa frente', o motor antigo); negativo "
                    f"nao significa nada."
                )
        for campo in ("n_entrada", "n_entrada_fills", "n_saida", "n_saida_fills"):
            valor = getattr(self, campo)
            if valor is None or int(valor) < 0:
                raise ValueError(
                    f"FidelidadeExecucao({self.symbol!r}): `{campo}` tem de ser "
                    f">= 0, recebeu {valor!r} -- procedencia e' campo "
                    f"obrigatorio, ver a docstring da classe."
                )
        if self.n_entrada_fills > self.n_entrada or self.n_saida_fills > self.n_saida:
            raise ValueError(
                f"FidelidadeExecucao({self.symbol!r}): mais preenchimentos do "
                f"que ordens que esperaram (entrada {self.n_entrada_fills}/"
                f"{self.n_entrada}, saida {self.n_saida_fills}/{self.n_saida}) "
                f"-- os `n_*_fills` sao um SUBCONJUNTO dos `n_*`, e uma "
                f"amostra que nao fecha invalida a mediana de Kaplan-Meier "
                f"(ela depende de quantos ficaram em risco a cada evento)."
            )
        if not str(self.medido_em).strip() or not str(self.estimador).strip():
            raise ValueError(
                f"FidelidadeExecucao({self.symbol!r}): `medido_em` e "
                f"`estimador` nao podem ficar vazios -- fila sem procedencia "
                f"e' folclore, ver a docstring da classe."
            )

    @property
    def censuradas_entrada(self) -> int:
        """Ordens de entrada que esperaram e NAO preencheram. Sao elas que o
        Kaplan-Meier aproveita e a estimativa ingenua joga fora."""
        return self.n_entrada - self.n_entrada_fills

    @property
    def censuradas_saida(self) -> int:
        return self.n_saida - self.n_saida_fills


#: FONTE DA VERDADE da fila por simbolo. `profiles.config_for` le' DAQUI --
#: nenhum script redigita o numero, e refrescar a calibracao com mais pregoes
#: e' editar UMA linha (ver `scripts/daytrade/wdof1_calibra_fila_real_
#: 2026_09_09.py`, que re-deriva tudo do terminal).
#:
#: So' entra simbolo com operacao REAL medida. Nao ha' linha "padrao": ver a
#: secao "O que NAO entra aqui" na docstring do modulo.
FIDELIDADE: dict[str, FidelidadeExecucao] = {
    "WDO@": FidelidadeExecucao(
        symbol="WDO@",
        # 438 e 489 sao MEDIANAS de Kaplan-Meier. As estimativas ingenuas
        # (so' quem preencheu) davam 346 e 374 -- 21% e 24% menores, sempre
        # para baixo, que e' a assinatura do vies de sobrevivencia.
        # 2026-09-10, ORDEM DO DONO: a tabela passa a ser derivada SO' do
        # pregao de 2026-09-10. O de 2026-09-09 fica FORA -- ele rodou com
        # prazo na fatia de saida, entao 17 das 25 ordens foram canceladas
        # pelo relogio antes de mostrarem a fila delas (68% de censura) e o
        # numero saia de um estimador em vez de uma observacao. O pregao de
        # 2026-09-10 rodou SEM PRAZO, do jeito que a producao opera: censura
        # de 18%, e a mediana ingenua coincide com a de Kaplan-Meier (494 nos
        # dois), o que so' acontece quando nao ha' nada escondido atras do
        # estimador.
        #
        # A troca CONFIRMA o numero em vez de corrigi-lo: a saida era 489
        # (estimada sob 68% de censura) e virou 494 (observada sob 18%) --
        # 1% de diferenca, em regimes de execucao diferentes. Era a peca que
        # faltava para a fila deixar de ser argumento e virar medida.
        #
        # A ENTRADA cai de 438 para 329 e a amostra encolhe (n=67 -> n=11):
        # o pregao de 2026-09-10 durou 41 minutos, so' a abertura. E' o
        # numero do dia limpo, como pedido, mas e' o lado FRACO desta
        # calibracao -- e nao e' o que decide (o ponto de virada da geometria
        # e' ~170 de fila, e os dois lados estao muito acima).
        queue_ahead_qty=329.0,
        exit_queue_ahead_qty=494.0,
        # A janela de reconstrucao e' [2026-09-07, 2026-09-10), e a
        # assimetria entre os dois lados e' real: a SAIDA so' tem observacao
        # de 09-09 (a fatia de alvo como ordem-limite nasceu em 09-08 e nao
        # gerou ordem qualificada naquele dia), enquanto a ENTRADA aproveita
        # os dois pregoes. Restringir tudo a 09-09 daria n=40 e mediana 508
        # na entrada, com a saida intacta. A data declarada e' a do pregao
        # que decide -- o mesmo da afericao contra o extrato.
        medido_em="2026-09-10",
        n_entrada=11,        # ordens que ESPERARAM
        n_entrada_fills=9,   # -> 2 censuradas
        n_saida=11,          # ordens que ESPERARAM
        n_saida_fills=9,     # -> 2 censuradas (18%, contra 68% no regime com prazo)
    ),
}


def fidelidade_ou_none(symbol: str) -> FidelidadeExecucao | None:
    """A porta TOLERANTE da tabela: a calibracao do simbolo, ou `None`.

    Sao DUAS portas para a mesma tabela de proposito, e a diferenca nao e'
    estilo -- e' quem pode conviver com a ausencia:

      * `fidelidade_for` e' a pergunta "qual e' a fidelidade MEDIDA deste
        simbolo?". Para quem nao tem, a resposta honesta e' "nao existe", e
        ela levanta. Um default ali emprestaria a fila de um mini-dolar (438
        CONTRATOS) para uma acao de centavos com cara de numero medido;
      * esta aqui e' a pergunta "ESTE simbolo tem calibracao?", e quem
        pergunta assim ja' sabe lidar com o nao. E' a porta de
        `profiles.config_for`, que monta config para PMAM3, WIN@ e WDO@ pelo
        mesmo caminho e nao pode quebrar em dois deles porque so' o terceiro
        foi medido.

    O `None` NAO pode virar zero em silencio no caminho de quem chama: e'
    exatamente assim que `queue_ahead_qty` passou um mes desligado. Quem usa
    esta porta tem de propagar a ausencia ate' a saida -- `config_for` a
    propaga como `IntradayCostModel.fidelidade_calibrada=False`, e a TABELA
    PADRAO carimba `fila NAO CALIBRADA` na linha, que e' visivelmente
    diferente de `fila 0/0` (premissa deliberada) e de nao ter carimbo."""
    return FIDELIDADE.get(symbol)


def fidelidade_for(symbol: str) -> FidelidadeExecucao:
    """Fidelidade de execucao declarada de um simbolo. `KeyError` (nunca um
    default silencioso) para simbolo sem medicao.

    Devolver um default aqui seria emprestar a fila de um mini-dolar
    (438/489 contratos) para uma acao de centavos, ou o contrario -- e o
    parametro entraria no motor com cara de numero medido. O chamador que
    aceita "sem fila" tem de dizer isso em voz alta: use a porta tolerante
    `fidelidade_ou_none` (e propague a ausencia), ou passe
    `queue_ahead_qty=0.0` explicito em `config_for`."""
    try:
        return FIDELIDADE[symbol]
    except KeyError:
        raise KeyError(
            f"sem fidelidade de execucao declarada para {symbol!r} -- ver "
            f"`backtest.intraday.fidelidade.FIDELIDADE`. So' entra simbolo com "
            f"pregao REAL medido (`scripts/daytrade/wdof1_calibra_fila_real_"
            f"2026_09_09.py` re-deriva os numeros do terminal MT5). Se a "
            f"intencao era rodar SEM fila (o motor otimista de ate "
            f"2026-09-08), passe `queue_ahead_qty=0.0`/`exit_queue_ahead_qty="
            f"0.0` explicitos em `config_for`."
        ) from None
