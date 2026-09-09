"""Desmontar um robô de day trade sem deixar rastro vivo na corretora.

Existe por um buraco que só aparece na hora de apagar: "Remover robô" apagava
a linha do banco e nada mais. O processo supervisor continuava rodando (o
endpoint recusava justamente por isso, empurrando o problema para o dono), e
o que estivesse pendurado no MT5 — ordem-limite esperando fila, posição
aberta — continuava lá, agora **invisível**, porque o cartão que o mostrava
tinha acabado de sumir da tela. Ordem órfã não é hipótese: em 25/08/2026 o
slot `dt-gremah_tick-pmam3-live` passou o pregão inteiro com uma limite viva
na Rico sendo reancorada a cada 30 min.

A regra que organiza este módulo: **conferir antes, agir depois, e nunca agir
sobre o que não deu para conferir**. `inspecionar()` só lê — é o que alimenta
o popup de confirmação; `remover()` só roda depois de o dono ver aquela lista
e confirmar. Entre uma e outra o mundo pode ter mudado (uma limite preencheu
no meio), então `remover()` relê tudo em vez de confiar no que a tela mostrou.

POR QUE ISTO FALA COM A CORRETORA DE DENTRO DO DASHBOARD

`live_service.get_status()` tem proibição explícita de disparar I/O na
corretora: ele roda a cada poll de 20s, em toda aba aberta. Aqui é o oposto
disso — uma ação única, iniciada por um clique, que só faz sentido contra o
estado REAL do terminal. É o mesmo caminho que `live_control.
_broker_for_detection()` já usa para descobrir `shares_per_lot` no clique de
"Iniciar operação".

O QUE ESTE MÓDULO NÃO É

Não é regra de trade. Não decide quando sair, a que preço, nem se vale a pena
— quem manda é o dono, com o número na frente. A única ordem que ele emite é
o fechamento a mercado do que o dono confirmou encerrar (decisão dele,
2026-08-25), e o P&L mostrado antes é ESTIMATIVA pelo último preço, nunca
promessa de execução.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from core.live_models import Fill, Order, OrderSide, OrderStatus, OrderType

#: Abaixo disto o caixa é considerado zerado — mesma tolerância que
#: `dashboard/app.py::operacao_caixa` usa no ledger manual (capital pequeno:
#: o default de R$1,00 de `reconcile_cash` engoliria meio real de um caixa de
#: R$30).
_TOLERANCIA_CAIXA = 0.005


# ---------- a economia de uma posição (AÇÃO x FUTURO) -----------------------
#
# Três números precisam estar certos para uma posição virar dinheiro, e em
# AÇÃO os três são tão triviais que dava para não pensar neles. Foi o que
# aconteceu -- e o dia em que um robô de FUTURO passou por aqui, os três
# erraram juntos (2026-09-09, `dt-wdo_grid_reload_maker-wdo@-shadow`: um
# short de 1 WDO@ @ 5133,0 encerrado deixou `cash_sombra = -R$4.706,00`):
#
#   * QUANTO VALE UM PONTO. Em ação, R$1,00 -- o preço já é em reais por
#     ação. Em futuro, o preço vem em PONTOS do dólar/índice: 1 ponto do
#     WDO@ vale R$10,00 e 1 do WIN@, R$0,20. Sem isso, 52 pontos de perda
#     viraram "R$52,00" em vez de R$520,00.
#   * QUANTO ESTÁ PRESO NO CAIXA. Em ação, o preço cheio do lote (comprar
#     100 x R$0,14 custa R$14,00 de verdade). Em futuro, só a MARGEM
#     (R$150 por contrato de WDO@): do nocional de ~R$5.100 nada é caixa.
#     Devolver o nocional ao fechar credita dinheiro que nunca saiu.
#   * O LADO, uma vez só. `live_positions.quantity` vem NEGATIVA numa
#     vendida (`IntradayLiveRuntime._on_opened`) E o lado está em
#     `metadata["side"]`; aplicar os dois inverte o resultado, e no caminho
#     do capital transforma um crédito num débito do tamanho do nocional.
#     Numa COMPRADA o mesmo código não debita: INFLA o caixa em ~R$5.100,
#     que é pior, porque não chama atenção de ninguém.
#
# As três funções abaixo são a resposta a cada um, e existem separadas para
# `inspecionar()` (o número do popup), `_limpar_na_corretora()` (o P&L do
# fechamento real) e `_encerrar_posicao_sombra()` (o que mexe no caixa)
# usarem exatamente a MESMA conta.


def _preco_de_saida(symbol: str) -> tuple[Optional[float], str]:
    """`(preço, origem)` para marcar uma posição a mercado AGORA.

    `live_control.preco_de_referencia`: cotação ao vivo do terminal
    primeiro, último fechamento de minuto salvo em parquet como retaguarda.
    `(None, "")` se nenhum dos dois responder.

    POR QUE NÃO O PARQUET DIRETO, que era o que estava aqui. Nada salva
    aquele arquivo sozinho -- o robô ao vivo lê barra direto do terminal e
    nunca escreve nele, o download é script manual. Medido em 2026-09-09:
    `_ultimo_preco("WDO@")` devolvia 5185,0 de 28/08, **12 dias velho**,
    enquanto o mini-dólar negociava a ~5133. Encerrar uma posição contra um
    preço de outra quinzena não é estimativa, é um número inventado com
    cara de dado. É o mesmo achado que já tinha custado o piso de caixa da
    PMAM3 (parquet parado 15 dias, +120% de defasagem) e criado
    `preco_de_referencia`; este caminho ficou para trás.

    O I/O NOVO NESTE CAMINHO, examinado e ACEITO (2026-09-09). Remover um
    robô de SOMBRA era 100% offline antes desta troca; agora pode abrir uma
    leitura no terminal. O que limita o custo, e é o que torna aceitável:

      * só roda QUANDO HÁ POSIÇÃO ABERTA. Os dois chamadores saem antes
        quando `conta.positions` não tem o símbolo (`inspecionar()` devolve
        `Pendencias(ordens=[])` e `remover()` nem chama
        `_encerrar_posicao_sombra`) -- que é o caso da esmagadora maioria
        das remoções. Sem posição não há preço para marcar, então a consulta
        não mudaria nada, e é por isso que ela não acontece;
      * é UMA leitura por remoção, não uma por chamada. `inspecionar()` e
        `_encerrar_posicao_sombra()` pedem o preço em sequência, mas
        `preco_de_referencia` guarda a cotação por `_PRECO_TTL_SEGUNDOS`
        (30s) num cache de processo compartilhado com o painel -- a segunda
        chamada é acerto de cache;
      * é `last_price` num `MT5Broker` de CONSULTA já instanciado
        (`live_control._preco_broker`, sem `magic`, que nunca manda ordem), o
        mesmo que o painel usa a cada repintura do piso de caixa. Não é uma
        porta nova para a corretora, é a porta que já estava aberta;
      * não bloqueia: qualquer falha (terminal fechado, credencial ausente)
        vira `None` dentro de `_cotacao_do_terminal` e cai no parquet.

    O que se compra com isso é o defeito nº 3 do item 5.19 -- encerrar uma
    posição contra um preço de 12 dias atrás. Custo de um clique manual
    contra um número inventado no caixa: o clique paga. Quando mesmo assim o
    preço vier do parquet, `_encerrar_posicao_sombra` AVISA o dono com a data
    dele, em vez de deixar a defasagem silenciosa.

    A troca NÃO custa robustez, que é o que o módulo precisava preservar:
    `preco_de_referencia` nunca levanta e nunca bloqueia por terminal
    fechado (cai no parquet e diz de onde veio), então "sem preço" continua
    caindo no preço de entrada em vez de travar a remoção. O I/O é LEITURA
    (`_cotacao_do_terminal` -> `last_price`), nunca ordem, e é o mesmo
    caminho que o painel já percorre a cada cálculo de piso de caixa. Na
    suíte ele fica desligado por `tests/conftest.py`, então todo teste
    continua lendo o parquet fixo do repo."""
    from dashboard.live_control import preco_de_referencia

    return preco_de_referencia(symbol)


#: Idade maxima, em DIAS CORRIDOS, de uma barra salva que ainda serve para
#: marcar uma posicao a mercado. Cinco cobre a maior distancia NORMAL entre
#: dois pregoes consecutivos da B3 -- feriado emendado no fim de semana
#: (quinta a terca) --, de modo que "o terminal estava fechado no fim de
#: semana" nunca cai na recusa, e "o parquet nao e' atualizado ha mais de uma
#: semana" sempre cai.
_IDADE_MAXIMA_DO_PRECO_DIAS = 5


def _preco_velho_demais(origem: str, entrada_em: Optional[date],
                        hoje: Optional[date] = None) -> Optional[str]:
    """Motivo para RECUSAR `origem` como marcacao a mercado, ou `None` quando
    ela serve. `origem` e' o segundo item de `_preco_de_saida`: `"agora"`
    (cotacao do terminal, sempre serve), `""` (nao veio preco nenhum, nao ha
    o que julgar) ou a data ISO da ultima barra salva em parquet.

    O QUE ESTA REGRA DECIDE, e o que ela deliberadamente NAO decide. Ela
    recusa o PRECO, nunca a remocao. Travar a remocao tambem e' um modo de
    falha -- e um caro: o robo fica preso no painel, com o cartao na tela e o
    ativo bloqueado para qualquer outro robo, por causa de um terminal
    fechado que o dono pode nem conseguir abrir agora. E o modulo ja tinha a
    saida certa escrita para o caso vizinho ("nao veio preco nenhum"):
    encerrar pelo PROPRIO preco de entrada, resultado bruto zero, e avisar. A
    escolha real nao e' "encerrar com preco velho x nao encerrar" -- e'
    "creditar um resultado inventado x creditar so' o custo conhecido", e a
    segunda e' a mesma que `_valor_do_ponto_brl` ja faz: numero errado no
    caixa e' pior que numero ausente.

    Isso importa porque o erro de um preco velho NAO e' pequeno nem
    aleatorio: ele credita um movimento de mercado que nunca aconteceu nesta
    posicao, com sinal arbitrario e tamanho ilimitado. No caso real de
    2026-09-09 o parquet do WDO@ estava em 5185,0 de 28/08 -- 12 dias -- e
    aquele numero sozinho decidia R$520,00 num caixa simulado de R$375,00. Um
    resultado bruto zero erra por no maximo o que a posicao realmente andou; o
    preco de outra quinzena erra pelo que o mercado andou em duas semanas.

    DOIS CRITERIOS, e o primeiro nao tem constante para discutir:

      1. **anterior a propria posicao.** Uma barra de antes de a posicao
         existir nao e' uma marcacao velha, e' uma impossibilidade logica --
         nao ha preco de saida que anteceda a entrada. Foi exatamente esta a
         forma do caso real (barra de 28/08 marcando uma posicao aberta em
         09/09), e ela dispensa qualquer juizo sobre "quanto e' velho demais";
      2. **mais de `_IDADE_MAXIMA_DO_PRECO_DIAS` dias corridos.** Pega o caso
         que o criterio 1 nao pega: robo morto ha semanas, cuja posicao e o
         parquet envelheceram JUNTOS. Aqui ha uma constante e ela e' uma
         escolha -- ver a nota dela.

    Data ilegivel devolve `None` de proposito: nao saber a idade nao autoriza
    inventar uma recusa (o aviso de "nao e' a cotacao de agora" continua
    saindo por outro caminho)."""
    if origem in ("", "agora"):
        return None
    try:
        quando = date.fromisoformat(origem)
    except ValueError:
        return None
    if entrada_em is not None and quando < entrada_em:
        return (f"a ultima barra salva e' de {origem}, ANTERIOR a abertura da "
                f"posicao ({entrada_em.isoformat()}) -- nao existe preco de saida "
                f"anterior a propria entrada")
    idade = ((hoje or date.today()) - quando).days
    if idade > _IDADE_MAXIMA_DO_PRECO_DIAS:
        return (f"a ultima barra salva e' de {origem}, {idade} dias atras "
                f"(o limite e' {_IDADE_MAXIMA_DO_PRECO_DIAS})")
    return None


def _valor_do_ponto_brl(symbol: str) -> Optional[float]:
    """Quantos REAIS vale 1 ponto de preco de `symbol`, por unidade.

    Sai do PERFIL do instrumento (`backtest.intraday.profiles.SymbolProfile.
    point_value_brl`) -- 1,0 em acao (o preco ja e' em reais por acao),
    R$0,20 no WIN@, R$10,00 no WDO@.

    ANTES (ate 2026-09-09) saia do ROBO do slot, por um parametro homonimo
    de `wdo_grid_reload_maker`/`copa_win`. Estava no lugar errado: valor do
    ponto e' propriedade do INSTRUMENTO, nao de quem opera nele -- dois
    robos no mesmo simbolo tem obrigatoriamente o mesmo numero, e um robo de
    futuro NOVO que esquecesse o parametro fazia esta rotina responder "nao
    sei quanto vale 1 ponto" e deixar de apurar o resultado da remocao.
    Ler do perfil tambem tira daqui a dependencia do catalogo de robos: uma
    conta criada com um robo que depois saiu do registry continua tendo o
    resultado apurado, porque o INSTRUMENTO nao mudou.

    Continua sem tocar no terminal, de proposito: este caminho roda depois
    de o processo do robo ja' ter morrido e precisa funcionar com o MT5
    fechado.

    `None` = perfil de futuro que nao declara o valor do ponto (hoje
    impossivel -- `_futures_profile` exige o campo -- mas o guard fica).
    Quem chama trata como "nao sei" e nao credita resultado nenhum: num WDO@
    o chute de 1,0 erraria por 10x, e numero errado no caixa e' pior que
    numero ausente."""
    from backtest.intraday.profiles import profile_for

    try:
        perfil = profile_for(symbol)
    except KeyError:
        # Sem perfil declarado so chega acao (simbolo novo, slot de swing):
        # futuro sem perfil nao consegue nem ser iniciado pelo painel.
        return 1.0
    if not perfil.is_futures:
        return 1.0
    valor = perfil.point_value_brl
    return float(valor) if valor else None


def _custos_de_saida(symbol: str, quantidade: int, entrada: float,
                     saida: float) -> Optional[float]:
    """Corretagem + emolumentos, em R$, de um round-trip de `quantidade`
    unidades de `symbol` entre `entrada` e `saida`. `None` quando o
    instrumento nao tem perfil (nao da' para saber o que ele cobra).

    MESMA formula e MESMOS numeros do fechamento normal: o motor cobra
    `backtest.intraday.costs.fees_round_trip_brl` uma vez, no fechamento,
    pelo round-trip inteiro (`IntradayTrade.pnl_brl` subtrai `fees_total`), e
    `live.intraday_runtime._on_closed` credita no caixa esse liquido. Sem
    isto, remover o robo com posicao aberta creditava um numero LEVEMENTE
    MELHOR do que fechar a mesma posicao pelo caminho normal -- duas rotas
    para o mesmo evento com contabilidade diferente, que e' a familia de bug
    dos itens 5.7/5.19 vista pelo lado do custo.

    POR QUE NAO `config_for` (que e' quem monta o modelo em todo o resto do
    projeto). Ele exige a economia lida do TERMINAL (`trade_tick_value`/
    `trade_tick_size`, via `market_data_intraday.mt5_source.symbol_economics`)
    e este caminho tem de funcionar com o MT5 fechado e com o processo do
    robo ja' morto -- pedir I/O de corretora aqui trocaria um erro de
    centavos por uma remocao que trava quando o terminal nao responde.
    `cost_model_from_profile` monta o modelo com os MESMOS campos do perfil
    que `config_for` leria (`fee_round_trip_brl`, `exchange_fee_pct_per_leg`,
    `point_value_brl`), que e' tudo que a conta de TAXA usa.

    O QUE FICA DE FORA, e e' separacao de responsabilidade, nao esquecimento:
    a SLIPPAGE. No motor ela nao e' uma taxa -- e' um ajuste no PRECO de
    execucao (`apply_intraday_slippage`) --, entao ela entra por
    `_preco_de_execucao_a_mercado` ANTES desta funcao, e o `saida` que chega
    aqui ja e' o preco executado. Cobra-la tambem como taxa contaria o mesmo
    custo duas vezes (e sobre o notional errado: a taxa percentual segue o
    preco REAL de cada perna)."""
    from backtest.intraday.costs import fees_round_trip_brl
    from backtest.intraday.profiles import cost_model_from_profile, profile_for

    try:
        perfil = profile_for(symbol)
    except KeyError:
        return None
    modelo = cost_model_from_profile(perfil)
    if modelo is None:
        return None
    return round(
        fees_round_trip_brl(abs(int(quantidade)), float(entrada), float(saida), modelo), 2)


def _preco_de_execucao_a_mercado(symbol: str, marcado: float, lado: str) -> float:
    """O preco que uma saida A MERCADO de `lado` (`"long"`/`"short"`) sairia,
    partindo da marcacao `marcado`: 1 tick CONTRA a posicao. Devolve `marcado`
    intacto quando o instrumento nao tem perfil (sem perfil nao ha tick, e
    chutar o passo de preco erraria por 50x entre uma acao e um WDO@).

    POR QUE ISTO EXISTE, e por que a resposta e' DIFERENTE nas duas rotas de
    fechamento deste modulo (2026-09-09). O texto anterior dizia que cobrar
    slippage aqui "inventaria um fill que ninguem observou" e deixava as duas
    rotas sem cobrar. Metade do argumento estava certa, e a metade certa e' a
    que se aplica a rota ERRADA:

      * `_limpar_na_corretora` (robo REAL) NAO passa por aqui, e nao pode
        passar: a corretora EXECUTOU, e `executada.avg_price` e' o preco
        observado -- a derrapagem ja aconteceu e ja esta DENTRO dele. Piorar
        esse numero em 1 tick seria cobrar duas vezes um custo que o extrato
        ja cobrou uma;
      * `_encerrar_posicao_sombra` (robo de SOMBRA) passa: ninguem executou
        nada, e e' exatamente por isso que o custo tem de ser MODELADO. A
        alternativa nao e' "nao inventar um fill" -- e' inventar um fill
        PERFEITO, ao preco de tela, que e' a unica coisa que a corretora
        garantidamente nao faz.

    Quem ja tinha decidido isto e' o proprio motor, e a regra aqui e' copia
    fiel dele: `machine._close_position` calcula `exec_px =
    apply_intraday_slippage(...)` e SO' o substitui pelo preco da corretora
    quando existe execucao real (`self.execution is not None`). Em sombra o
    motor fica com o preco deslizado -- ou seja, fechar a mesma posicao pelo
    caminho normal, em sombra, JA pagava o tick. Remover o robo era a unica
    rota que nao pagava, e "duas rotas para o mesmo evento com contabilidade
    diferente" e a familia de bug dos itens 5.7/5.19.

    O sinal do erro tambem manda: creditar de menos assusta o dono, creditar
    de MAIS nao chama atencao de ninguem e vira tamanho de posicao no pregao
    seguinte (item 5.19, "caixa inflado e' pior que caixa negativo").

    QUANTOS TICKS. `IntradayCostModel.slippage_ticks`, lido do proprio
    dataclass em vez de redigitado -- e' o numero que o motor usa em toda
    saida a mercado (1,0 hoje). `cost_model_from_profile` zera esse campo de
    proposito (a docstring de la' diz por que: quem chama normalmente ja tem
    o preco executado em maos), entao a reposicao acontece aqui, no unico
    ponto do modulo que precisa ESTIMAR uma execucao. Vale R$5,00 num
    contrato de WDO@ (tick de 0,5 pt x R$10,00/pt) e R$1,00 num lote de 100
    acoes de R$0,13 -- num papel de centavos o tick e' o custo dominante, e
    esconde-lo era o que fazia a remocao parecer barata."""
    from dataclasses import replace

    from backtest.intraday.costs import IntradayCostModel, apply_intraday_slippage
    from backtest.intraday.profiles import cost_model_from_profile, profile_for

    try:
        perfil = profile_for(symbol)
    except KeyError:
        return float(marcado)
    modelo = cost_model_from_profile(perfil)
    if modelo is None:
        return float(marcado)
    # `lado` e' o lado da POSICAO; a ordem que a fecha e' a oposta -- fechar
    # comprado e' vender (sai mais BAIXO), fechar vendido e' comprar (sai
    # mais ALTO). Mesma convencao de `machine._exit_side`.
    saida = "sell" if lado == "long" else "buy"
    return apply_intraday_slippage(
        float(marcado), saida,
        replace(modelo, slippage_ticks=IntradayCostModel.slippage_ticks))


def _capital_comprometido(pos, symbol: str) -> float:
    """R$ que esta posição prendeu no caixa ao abrir -- é o que volta a ele
    quando ela fecha. SEMPRE positivo, nos dois lados: capital comprometido é
    comprometido em compra e em venda (mesma razão de
    `LivePosition.market_value` usar `abs`).

    Preferência absoluta por `capital_allocated`, que é exatamente o número
    que `IntradayLiveRuntime._on_opened` DEBITOU (`_custo_posicao`: margem em
    futuro, preço cheio em ação). Devolver ao caixa uma conta diferente da
    que saiu dele é como um bookkeeping deixa de fechar -- e recalcular por
    fora é justamente o convite para as duas pontas divergirem.

    A retaguarda só serve a linha antiga ou sintética sem o campo preenchido:
    margem do perfil em futuro, preço de entrada em ação."""
    alocado = abs(float(getattr(pos, "capital_allocated", 0.0) or 0.0))
    if alocado:
        return alocado

    from backtest.intraday.profiles import profile_for

    quantidade = abs(int(pos.quantity))
    try:
        perfil = profile_for(symbol)
    except KeyError:
        perfil = None
    margem = perfil.margin_per_contract_brl if perfil is not None and perfil.is_futures else None
    if margem:
        return float(margem) * quantidade
    return float(pos.entry_price) * quantidade


def _pl_brl(entrada: float, saida: float, quantidade: int, lado: str,
            valor_do_ponto: Optional[float]) -> Optional[float]:
    """Resultado em R$ de fechar `quantidade` unidades a `saida`, ou `None`
    quando não se sabe quanto vale um ponto do instrumento.

    Mesma convenção de `backtest.intraday.costs.gross_pnl_brl`, a fórmula
    canônica do motor: o LADO decide o sinal dos pontos (`long` ganha quando
    o preço sobe, `short` quando cai) e a quantidade entra em MÓDULO. Aplicar
    o lado duas vezes -- uma nos pontos, outra na quantidade negativa de uma
    vendida -- é o que fez uma perda de 52 pontos aparecer como "lucro de
    R$52,00" em 2026-09-09.

    Bruto, sem corretagem, pelo mesmo motivo de sempre neste módulo: é
    estimativa para o dono decidir com ordem de grandeza na tela."""
    if valor_do_ponto is None:
        return None
    pontos = (entrada - saida) if lado == "short" else (saida - entrada)
    return round(pontos * abs(int(quantidade)) * float(valor_do_ponto), 2)


@dataclass(frozen=True)
class OrdemPendurada:
    """Uma ordem-limite viva na corretora, como ela é lá — não como o nosso
    diário acha que ela está."""

    ticket: str
    side: str
    quantity: int
    price: float
    symbol: str

    @property
    def descricao(self) -> str:
        return (f"#{self.ticket} — {self.side} de {self.quantity} {self.symbol} "
                f"a R$ {self.price:.2f}".replace(".", ","))


@dataclass(frozen=True)
class Pendencias:
    """Tudo que sobreviveria à remoção deste robô se ninguém fizesse nada.

    Os três `Optional` do meio carregam uma distinção que o painel precisa
    respeitar: `[]`/`None` em `ordens` não é a mesma coisa. `[]` é "perguntei
    à corretora e não há nenhuma"; `None` é "não consegui perguntar" — e
    apagar um robô real sem conseguir perguntar é exatamente como se cria uma
    ordem órfã."""

    slot_id: str
    label: str
    symbol: str
    modo: Optional[str]
    processo_pid: Optional[int]
    #: O saldo que o dono VÊ no cartão — `cash_for(modo)`, ou seja
    #: `cash_sombra` num robô de sombra e `cash` num real. É este que o
    #: diálogo nomeia: mostrar outro número aqui obrigaria o dono a decidir
    #: sobre um valor que ele nunca viu na tela (achado em 2026-08-26 no banco
    #: real: `dt-gremah-pmam3-shadow` tinha cash=20,00 e cash_sombra=35,92, e
    #: o cartão mostrava 35,92).
    caixa: float
    #: O ledger de dinheiro REAL alocado a este robô. Igual a `caixa` num robô
    #: real; num de sombra é a outra metade — e é o que `remover()` zera antes
    #: de apagar a conta, porque é o que `delete_account` guarda.
    caixa_real: float = 0.0
    ordens: Optional[list[OrdemPendurada]] = None
    posicao: Optional[dict] = None
    preco_atual: Optional[float] = None
    #: Por que o preço que existia foi RECUSADO como marcação a mercado
    #: (`_preco_velho_demais`), ou `None`. Quando está preenchido,
    #: `preco_atual` vem `None` de propósito -- não é "não achei preço", é
    #: "achei e não sirvo dele", e a tela precisa dizer qual dos dois.
    preco_recusado: Optional[str] = None
    erro_corretora: Optional[str] = None
    erro_processo: Optional[str] = None

    @property
    def valor_do_ponto(self) -> Optional[float]:
        """R$ por PONTO de preço deste instrumento -- 1,0 em ação, R$10,00 no
        WDO@ (ver `_valor_do_ponto_brl`). `None` = futuro cujo valor do ponto
        não se descobriu, e aí `pl_estimado` responde "não sei" em vez de
        mostrar ao dono um número 10x errado.

        DERIVADO DO SÍMBOLO, nunca recebido de fora (2026-09-09). Era um
        CAMPO com default 1,0, e isso deixava `pl_estimado` misturar duas
        fontes na mesma conta: o valor do ponto vinha do que o chamador
        tivesse passado, e as taxas de `_custos_de_saida` vinham do perfil
        resolvido por `self.symbol`. Nada impedia
        `Pendencias(symbol="WDO@", valor_do_ponto=1.0)` -- e o resultado não
        seria "errado por um fator conhecido", seria um número MISTO: pontos
        contados como reais no bruto, tarifa de contrato de futuro no
        desconto. É o modo de falha do item 5.19 pelo lado da entrada
        (multiplicador do instrumento errado), e a única defesa era ninguém
        digitar.

        Como propriedade, a incoerência deixa de ser possível em vez de
        depender de disciplina: as DUAS pontas da conta -- multiplicador e
        tarifa -- passam a sair do mesmo `profile_for(self.symbol)`. É a
        mesma decisão que tirou o valor do ponto do robô e o pôs no perfil
        (ver `_valor_do_ponto_brl`), agora aplicada ao último lugar que
        ainda aceitava o número por parâmetro."""
        return _valor_do_ponto_brl(self.symbol)

    @property
    def consultou_corretora(self) -> bool:
        return self.erro_corretora is None

    @property
    def e_sombra(self) -> bool:
        """Robô em modo sombra nunca mandou ordem para a corretora — é
        invariante do sistema (`IntradayLiveRuntime` nasce sem `executor` em
        sombra), não suposição otimista. Por isso um sombra pode ser apagado
        mesmo com o terminal fechado."""
        return self.modo == "shadow"

    @property
    def pl_estimado(self) -> Optional[float]:
        """Resultado que encerrar a posição a mercado realizaria, pelo preço
        de agora. `None` quando não há posição, não há preço ou não se sabe
        quanto vale um ponto do instrumento.

        LÍQUIDO de corretagem e emolumentos (2026-09-09) -- `_custos_de_
        saida`, a mesma conta que o motor cobra no fechamento. O texto que
        estava aqui dizia que somar taxa "daria falsa precisão a um número
        que já é estimativa", e isso confunde as duas incertezas: o que é
        estimativa neste número é o PREÇO (a fila decide onde a ordem sai);
        a taxa não é estimada nem inventada, está declarada no perfil do
        instrumento e é exatamente o que vai ser debitado. Deixá-la de fora
        fazia o popup prometer um número melhor do que o que a remoção
        credita em seguida -- as duas pontas do mesmo evento com
        contabilidade diferente, que é a família de bug dos itens 5.7/5.19.

        A quantidade entra em MÓDULO (2026-09-09). Numa posição vinda do
        BANCO ela é negativa quando vendida, e o `qtd <= 0` que estava aqui
        devolvia `None` para toda vendida: o popup apagava a linha do
        resultado justamente no lado em que o dono mais precisa vê-la, e
        parecia "não há preço" em vez de "não sei ler esta posição". Da
        corretora ela vem positiva com o lado à parte, então os dois
        caminhos passam a ler igual."""
        if not self.posicao or not self.preco_atual:
            return None
        entrada = float(self.posicao.get("price") or 0.0)
        qtd = abs(int(self.posicao.get("quantity") or 0))
        if entrada <= 0 or qtd <= 0:
            return None
        lado = self.posicao.get("side") or "long"
        # SLIPPAGE, como o motor (2026-09-09): `preco_atual` é a marcação, e
        # a saída é a MERCADO nos dois modos ("encerrada localmente" em
        # sombra é uma saída a mercado simulada; no real é uma de verdade).
        # O popup existe para PREVER o número que vem em seguida -- em
        # sombra, exatamente o que `_encerrar_posicao_sombra` vai creditar;
        # no real, o `avg_price` que a corretora vai devolver, que também
        # sai ~1 tick pior que a tela. Mostrar o preço de tela limpo fazia o
        # diálogo prometer um resultado melhor que o dos dois desfechos
        # possíveis -- o mesmo defeito que o desconto de taxa já tinha
        # fechado logo acima, no eixo que faltava.
        saida = _preco_de_execucao_a_mercado(self.symbol, float(self.preco_atual), lado)
        bruto = _pl_brl(entrada, saida, qtd, lado, self.valor_do_ponto)
        if bruto is None:
            return None
        taxas = _custos_de_saida(self.symbol, qtd, entrada, saida)
        return round(bruto - (taxas or 0.0), 2)

    @property
    def tem_o_que_desfazer(self) -> bool:
        """Há algo além de apagar uma linha do banco? É o que decide se o
        clique abre o popup de confirmação ou remove direto."""
        return bool(self.processo_pid
                    or self.ordens
                    or self.posicao
                    or abs(self.caixa) >= _TOLERANCIA_CAIXA
                    or abs(self.caixa_real) >= _TOLERANCIA_CAIXA)

    @property
    def impedimento(self) -> Optional[str]:
        """Motivo para NÃO deixar remover agora, ou `None`.

        Só um caso: robô que pôde mandar ordem de verdade e cuja corretora
        não respondeu. Aí "remover" não sabe o que está apagando."""
        if self.e_sombra or self.consultou_corretora:
            return None
        return (
            f"não consegui perguntar à corretora o que {self.label} tem pendurado "
            f"({self.erro_corretora}). Como ele opera em modo real, remover agora "
            "poderia deixar ordem ou posição viva no MT5 e invisível aqui — abra o "
            "terminal MT5 e tente de novo."
        )


@dataclass
class ResultadoRemocao:
    """O que de fato aconteceu, para a tela contar em vez de prometer."""

    slot_id: str
    label: str
    processo_encerrado: Optional[int] = None
    ordens_canceladas: list[str] = field(default_factory=list)
    posicao_encerrada: Optional[dict] = None
    caixa_zerado: Optional[float] = None
    conta_apagada: bool = False
    #: Removido do painel COM o histórico guardado (`archived_at`), em vez de
    #: apagado. Mutuamente exclusivo com `conta_apagada`: os dois são o mesmo
    #: fim de linha (o cartão sai da tela, o ativo fica livre) por caminhos
    #: diferentes.
    conta_arquivada: bool = False
    avisos: list[str] = field(default_factory=list)

    @property
    def removido(self) -> bool:
        """O robô saiu do painel? É o que separa "deu certo" de "parei no
        meio" — e não interessa por qual dos dois caminhos ele saiu."""
        return self.conta_apagada or self.conta_arquivada

    @property
    def resumo(self) -> str:
        partes = [f"Robô {self.label} removido" if self.removido
                  else f"Robô {self.label} NÃO foi removido"]
        if self.processo_encerrado:
            partes.append(f"processo {self.processo_encerrado} encerrado")
        if self.ordens_canceladas:
            partes.append(f"{len(self.ordens_canceladas)} ordem(ns) cancelada(s)")
        if self.posicao_encerrada:
            pl = self.posicao_encerrada.get("pl")
            preco = self.posicao_encerrada.get("price")
            texto = f"posição encerrada a R$ {preco:.2f}" if preco else "posição encerrada"
            if pl is not None:
                texto += f" ({'lucro' if pl >= 0 else 'prejuízo'} de R$ {abs(pl):.2f}"
                # O número é LÍQUIDO (ver `_custos_de_saida`); dizer o custo
                # junto é o que impede o dono de conferir contra o extrato e
                # achar que falta dinheiro.
                #
                # DOIS custos, somados aqui, separados no dicionário: taxa
                # (corretagem+emolumentos) e derrapagem. A derrapagem só
                # existe na rota de SOMBRA -- na real ela já está dentro do
                # `avg_price` da corretora e não tem como ser destacada (ver
                # `_preco_de_execucao_a_mercado`). Somar sem dizer o total
                # faria "já com R$ 0,50 de custo" aparecer ao lado de um
                # prejuízo em que R$5,00 vieram do tick.
                taxas = self.posicao_encerrada.get("taxas") or 0.0
                deslize = self.posicao_encerrada.get("deslize") or 0.0
                custo = taxas + deslize
                if custo and deslize:
                    texto += (f", já com R$ {custo:.2f} de custo — R$ {taxas:.2f} "
                              f"de taxa e R$ {deslize:.2f} de derrapagem)")
                else:
                    texto += f", já com R$ {custo:.2f} de custo)" if custo else ")"
            partes.append(texto)
        if self.caixa_zerado:
            partes.append(f"caixa de R$ {self.caixa_zerado:.2f} zerado")
        if self.conta_arquivada:
            partes.append("histórico guardado (recrie o mesmo robô neste ativo "
                          "para restaurá-lo)")
        return " · ".join(partes) + "."


# ---------- montagem do broker deste slot ----------------------------------

def _broker_do_slot(slot):
    """`MT5Broker` com o `magic` DESTE slot — sem isso a consulta enxergaria
    (e cancelaria) as ordens do robô vizinho, que divide a mesma conta
    NETTING. `shares_per_lot` sai da última config do processo para a
    quantidade aparecer em AÇÕES na tela, igual ao resto do painel."""
    from dashboard import live_control
    from live.broker_mt5 import MT5Broker

    creds = live_control.load_credentials()
    login = creds.get("mt5_login")
    config = live_control.last_config(slot.id) or {}
    return MT5Broker(
        magic=slot.magic,
        shares_per_lot=float(config.get("mt5_shares_per_lot") or 1.0),
        login=int(login) if login else None,
        password=creds.get("mt5_password"),
        server=creds.get("mt5_server"),
        path=creds.get("mt5_terminal_path"),
    )


def _modo_do_slot(slot, processo) -> Optional[str]:
    """`"live"`/`"shadow"` deste robô, na ordem em que essas fontes merecem
    confiança: o próprio slot (o modo é parte da IDENTIDADE dele desde
    2026-08-24, fixo na criação), depois o processo que está rodando agora,
    depois a última config gravada. `None` = nenhuma das três sabe, e aí
    `Pendencias` trata como real, que é o lado seguro."""
    from dashboard import live_control

    if slot.execution_mode:
        return slot.execution_mode
    if processo is not None and processo.execution_mode:
        return processo.execution_mode
    config = live_control.last_config(slot.id) or {}
    return config.get("execution_mode")


def _processo_do_slot(slot_id: str):
    """`ProcessoRobo` deste slot, ou `(None, erro)`. Usa o inventário do
    sistema operacional, e não `status()`: o caso que motivou tudo isto é
    justamente o processo que o arquivo de estado NÃO conhece mais."""
    from dashboard import live_control

    try:
        for processo in live_control.listar_processos():
            if processo.slot == slot_id:
                return processo, None
    except live_control._TasklistUnavailable as e:  # noqa: SLF001
        return None, str(e)
    return None, None


# ---------- leitura ---------------------------------------------------------

def inspecionar(slot) -> Pendencias:
    """O que este robô deixaria para trás. NÃO muta nada, nem no banco nem na
    corretora — é o que o popup mostra antes de o dono confirmar."""
    from journal import live_store

    processo, erro_processo = _processo_do_slot(slot.id)
    modo = _modo_do_slot(slot, processo)

    caixa = caixa_real = 0.0
    posicao_sombra = None
    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is not None:
            # `modo` pode ser `None` (nenhuma das três fontes sabe); aí vale o
            # lado seguro, o mesmo que `Pendencias.impedimento` assume: real.
            caixa = float(conta.cash_for(modo or "live"))
            caixa_real = float(conta.cash)
            if slot.symbol:
                posicao_sombra = conta.positions.get(slot.symbol)

    base = dict(
        slot_id=slot.id, label=slot.label, symbol=slot.symbol or "",
        modo=modo, processo_pid=processo.pid if processo else None,
        caixa=caixa, caixa_real=caixa_real, erro_processo=erro_processo,
    )

    # Sombra nunca mandou ordem: perguntar à corretora custaria uma conexão
    # para receber, por construção, lista vazia. Mas uma posição SIMULADA
    # (`live_positions`, a mesma tabela que o robô real usa) pode existir de
    # verdade -- ela é o que `delete_account`/`archive_account` recusam se
    # ninguém a encerrar antes (achado em 2026-08-28: robô de sombra parado
    # há um dia com posição aberta no registro, e a remoção falhava com uma
    # mensagem que fala de MT5 num robô que nunca chegou perto de um). Expor
    # aqui é o que faz o popup avisar e `remover()` saber o que fechar.
    if modo == "shadow" or not slot.symbol:
        if posicao_sombra is None:
            return Pendencias(ordens=[], **base)

        preco_atual, origem = _preco_de_saida(slot.symbol)
        # MESMA regra que `_encerrar_posicao_sombra` aplica na hora de
        # creditar (`_preco_velho_demais`): o popup não pode estimar o
        # resultado por um preço que a remoção vai recusar em seguida. Sem
        # isto o diálogo prometia "prejuízo de R$520,00" e a remoção
        # creditava só o custo -- as duas pontas do mesmo evento com
        # contabilidade diferente, de novo.
        recusado = _preco_velho_demais(origem, posicao_sombra.entry_date)
        posicao = {
            "side": posicao_sombra.metadata.get("side") or "long",
            # Em MÓDULO, como a posição que vem da CORRETORA (lá o lado é
            # campo à parte e a quantidade é sempre positiva). Sem isto o
            # popup escrevia "A posição de -1 WDO@ (vendida...)", com o lado
            # dito duas vezes e uma delas em forma de sinal.
            "quantity": abs(int(posicao_sombra.quantity)),
            "price": posicao_sombra.entry_price,
        }
        return Pendencias(
            ordens=[], posicao=posicao,
            preco_atual=None if recusado else preco_atual,
            preco_recusado=recusado if preco_atual is not None else None,
            **base)

    broker = _broker_do_slot(slot)
    try:
        if not broker.connect():
            return Pendencias(erro_corretora="terminal MT5 não respondeu", **base)
        ordens = broker.pending_orders(slot.symbol)
        if ordens is None:
            return Pendencias(
                erro_corretora="a consulta de ordens pendentes não voltou", **base)
        # `position_state`, não `open_position`: aquele achata "não há posição"
        # e "não consegui perguntar" no mesmo `None`, e aqui a diferença decide
        # se o dono pode apagar o robô. Ler errado deixaria uma posição real
        # órfã no terminal, que é a falha nº 1 da lista no topo deste arquivo.
        estado = broker.position_state(slot.symbol)
        if not estado.get("ok"):
            return Pendencias(
                erro_corretora=f"a leitura da posição não voltou: {estado.get('note', '')}",
                **base)
        posicao = estado.get("position")
        preco = broker.last_price(slot.symbol) if posicao else None
    except Exception as e:  # noqa: BLE001 - qualquer falha aqui é "não sei"
        return Pendencias(erro_corretora=f"{type(e).__name__}: {e}", **base)

    # Sem `_preco_velho_demais` aqui, de propósito: `broker.last_price` é a
    # cotação do terminal AGORA ou `None` -- não existe a categoria "barra
    # salva de outro dia" neste caminho, que é o que aquela regra julga.
    return Pendencias(
        ordens=[OrdemPendurada(**o) for o in ordens],
        posicao=posicao, preco_atual=preco, **base,
    )


# ---------- ação ------------------------------------------------------------

def remover(slot, apagar_historico: bool = False) -> ResultadoRemocao:
    """Desmonta o robô inteiro, nesta ordem — e a ordem importa:

      1. **mata o processo** primeiro. Enquanto ele vive, ele reancora
         ordem-limite a cada poucos segundos: cancelar antes de matar é
         cancelar algo que o robô recria em seguida;
      2. **cancela as ordens pendentes**, para nada mais poder virar posição;
      3. **encerra a posição a mercado**, se houver (decisão do dono,
         2026-08-25: remover não pode deixar posição órfã viva no MT5);
      4. tira o robô do painel — **guardando** ou **apagando** o histórico.

    Os passos 1 a 3 são iguais nos dois casos, e não são negociáveis: eles
    tratam de dinheiro exposto na corretora, não de registro. `apagar_historico`
    decide só o destino do que está no NOSSO banco (pedido do dono,
    2026-08-26):

      * `False` (padrão) — `archive_account`: a conta continua inteira, com
        diário, trades e caixa. O cartão sai da tela, o ativo fica livre, e
        recriar o mesmo trio (robô, ativo, modo) oferece restaurar tudo. O
        padrão é este porque é o único dos dois que dá para desfazer;
      * `True` — o de sempre: zera o caixa e `delete_account`, que leva junto
        tudo que pende da conta (`ON DELETE CASCADE`).

    Relê a corretora em vez de confiar na inspeção que alimentou o popup: um
    limite pode ter preenchido entre a tela e o clique, e cancelar por uma
    lista velha deixaria a posição nova para trás.

    Levanta `ValueError` — sem ter tocado em nada — quando o robô é real e a
    corretora não respondeu. Meio caminho é o pior desfecho possível aqui.
    """
    from journal import live_store

    pend = inspecionar(slot)
    if pend.impedimento:
        raise ValueError(pend.impedimento)

    resultado = ResultadoRemocao(slot_id=slot.id, label=slot.label)

    if pend.processo_pid is not None:
        from dashboard import live_control

        try:
            live_control.encerrar_processo(pend.processo_pid)
            resultado.processo_encerrado = pend.processo_pid
        except ValueError:
            # Morreu sozinho entre a inspeção e agora — o objetivo já está
            # cumprido, não é falha.
            resultado.avisos.append(
                f"o processo {pend.processo_pid} já não estava mais rodando.")

    if pend.e_sombra:
        # Sombra nunca teve corretora: a "posição" aqui é só uma linha em
        # `live_positions`, a mesma tabela que o robô real usa para
        # bookkeeping -- sem encerrá-la, `delete_account`/`archive_account`
        # recusam com o MESMO guard que protege um robô real de virar posição
        # órfã no MT5, só que não há MT5 nenhum para essa exposição existir.
        if pend.posicao:
            _encerrar_posicao_sombra(slot, resultado)
    elif pend.consultou_corretora and not pend.posicao:
        # A corretora CONFIRMOU que não há posição. Se o banco ainda tem uma,
        # os dois discordam -- e sem reconciliar aqui a remoção fica presa
        # para sempre (ver `_descartar_posicao_fantasma`). Ordens pendentes,
        # se houver, continuam sendo canceladas logo abaixo.
        _descartar_posicao_fantasma(slot, resultado)
        if pend.ordens and not _limpar_na_corretora(slot, resultado):
            resultado.avisos.append(
                f"a conta de {slot.label} NÃO foi apagada: sobrou ordem viva na "
                "corretora.")
            return resultado
    elif pend.ordens or pend.posicao:
        if not _limpar_na_corretora(slot, resultado):
            # Posição que não fechou é o único desfecho em que apagar a conta
            # seria PIOR que parar no meio: o robô sai da tela e a exposição
            # continua no MT5, que é exatamente a órfã invisível que este
            # módulo existe para impedir. O processo já morreu e as ordens já
            # foram canceladas — todo o progresso é no sentido seguro — e o
            # cartão continua ali para o dono ver e tentar de novo.
            resultado.avisos.append(
                f"a conta de {slot.label} NÃO foi apagada: enquanto houver posição "
                "aberta na corretora, remover o robô a deixaria viva e invisível "
                "aqui.")
            return resultado

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is None:
            resultado.conta_apagada = True
            return resultado
        if not apagar_historico:
            live_store.archive_account(conn, slot.id)
            resultado.conta_arquivada = True
            return resultado
        if abs(conta.cash) >= _TOLERANCIA_CAIXA:
            anterior = float(conta.cash)
            live_store.reconcile_cash(
                conn, conta, 0.0, date.today(), origin="remocao_robo",
                note=f"caixa zerado ao remover o robô {slot.label}",
                tolerance=_TOLERANCIA_CAIXA,
            )
            resultado.caixa_zerado = anterior
        live_store.delete_account(conn, slot.id)
        resultado.conta_apagada = True

    # A linha deste slot em `db/live_process.json` vira lixo no instante em
    # que a conta deixa de existir: ela guarda a config de retomada de um robô
    # que não tem mais para onde retomar. `stop()` só zera o `pid` (de
    # propósito -- ver a docstring dele: o formulário continua pré-preenchido
    # depois de parar), então quem apaga de vez é aqui.
    #
    # Só no caminho que APAGA. Com o histórico guardado, esta linha é parte do
    # que foi guardado: é ela que traz de volta capital, `shares_per_lot` e o
    # resto da config quando o dono restaurar o robô — sem ela, restaurar
    # devolveria o diário mas mandaria o dono redigitar a configuração.
    from dashboard import live_control

    live_control.esquecer(slot.id)
    return resultado


def _limpar_na_corretora(slot, resultado: ResultadoRemocao) -> bool:
    """Cancela as pendentes e encerra a posição, relendo a corretora agora.
    Devolve se a corretora ficou LIMPA — é o que autoriza apagar a conta.

    Falha de ordem vira AVISO em vez de exceção: uma que não cancelou não
    pode impedir que as outras cancelem nem que a posição seja encerrada, e o
    dono precisa terminar sabendo o que ficou para trás. Mas ela também
    **impede a conta de ser apagada** (`False`), junto com a posição aberta.

    Isso é uma CORREÇÃO de premissa (2026-08-28). O texto que estava aqui
    dizia que "ordem pendurada que sobrou não tem risco de mercado enquanto
    não preenche" — e é exatamente ao contrário: uma ordem-limite viva no
    book preenche sozinha, sem ninguém clicar em nada, e abre uma posição
    real. Apagar a conta nesse estado deixa essa posição nascendo sem robô,
    sem stop, sem diário e sem linha no painel. "Enquanto não preenche" não
    é uma garantia, é o intervalo antes do problema.

    Piorava por um segundo motivo, já corrigido: `MT5Broker.cancel` marcava
    `CANCELLED` mesmo quando a corretora RECUSAVA o cancelamento, então este
    laço via sucesso onde não houve e nunca chegava a avisar nada."""
    broker = _broker_do_slot(slot)
    if not broker.connect():
        resultado.avisos.append(
            "não consegui reconectar ao terminal MT5 para limpar a corretora — "
            "confira ordens e posição no MT5.")
        return False

    limpo = True
    ordens = broker.pending_orders(slot.symbol)
    if ordens is None:
        resultado.avisos.append(
            "a corretora não respondeu a lista de ordens pendentes — confira no MT5.")
        ordens = []
        # `None` é "não consegui perguntar", não "não há nenhuma" (ver a
        # docstring de `pending_orders`). Sem saber o que existe, não dá para
        # afirmar que a corretora ficou limpa.
        limpo = False
    for o in ordens:
        pedido = Order(
            ticker=slot.symbol,
            side=OrderSide.BUY if o["side"] == "compra" else OrderSide.SELL,
            quantity=int(o["quantity"]),
            order_type=OrderType.LIMIT,
            limit_price=float(o["price"]),
            broker_ref=str(o["ticket"]),
            sent_at=datetime.now(timezone.utc),
        )
        devolvida = broker.cancel(pedido)
        if devolvida.status == OrderStatus.CANCELLED:
            resultado.ordens_canceladas.append(str(o["ticket"]))
        else:
            resultado.avisos.append(
                f"a ordem #{o['ticket']} NÃO foi cancelada e pode preencher sozinha, "
                f"abrindo posição sem robô nenhum vigiando: {devolvida.note}")
            limpo = False

    estado = broker.position_state(slot.symbol)
    if not estado.get("ok"):
        # "Não consegui perguntar" nunca vira "não há posição" — apagar a
        # conta aqui deixaria uma posição real órfã no terminal.
        resultado.avisos.append(
            f"não consegui ler a posição de {slot.symbol} na corretora "
            f"({estado.get('note', '')}) — confira no MT5.")
        return False
    posicao = estado.get("position")
    if not posicao:
        return limpo
    fechamento = Order(
        ticker=slot.symbol,
        side=OrderSide.SELL if posicao["side"] == "long" else OrderSide.BUY,
        quantity=int(posicao["quantity"]),
        order_type=OrderType.MARKET,
        sent_at=datetime.now(timezone.utc),
    )
    # `close_position` (com o ticket), NUNCA `place()`: sem o campo
    # `"position"` no request o motor de risco da corretora trata a ordem
    # como ABERTURA nova e recusa quando a margem está esgotada -- foi
    # exatamente isso que travou ~24 tentativas de fechamento no incidente de
    # 2026-08-28 (`retcode=10006 [MG51] Para abrir novas posições`). Este era
    # o mesmo bug, no caminho de remover um robô: o lugar em que ele dói mais,
    # porque é o momento em que o dono está tentando sair de tudo.
    fechar_com_ticket = getattr(broker, "close_position", None)
    ticket = posicao.get("ticket")
    if fechar_com_ticket is not None and ticket is not None:
        executada = fechar_com_ticket(fechamento, ticket)
    else:
        executada = broker.place(fechamento)
    if executada.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL) or not executada.avg_price:
        resultado.avisos.append(
            f"a posição de {posicao['quantity']} {slot.symbol} NÃO foi encerrada "
            f"({executada.note or executada.status.value}) — ela continua aberta no "
            "MT5 e precisa ser fechada na mão.")
        return False
    preco = float(executada.avg_price)
    entrada = float(posicao.get("price") or 0.0)
    # `_pl_brl` converte PONTO em REAL (2026-09-09): sem isso o fechamento de
    # 1 contrato de WDO@ era reportado ao dono como "R$52,00" quando a
    # corretora tinha creditado/debitado R$520,00 -- 1 ponto do mini-dólar
    # vale R$10,00. Aqui é só o texto do resumo (o caixa REAL é o extrato da
    # corretora, este módulo nunca o escreve), mas um número 10x errado na
    # tela é o que o dono usa para decidir o que fazer em seguida.
    #
    # SEM SLIPPAGE, e é a diferença deliberada para o caminho de sombra
    # (2026-09-09 -- ver `_preco_de_execucao_a_mercado`). `executada.
    # avg_price` é o preço que a corretora EXECUTOU: a derrapagem não é uma
    # estimativa a somar, ela já aconteceu e já está dentro deste número.
    # Piorá-lo em 1 tick cobraria duas vezes o que o extrato cobra uma, e
    # faria o resumo da tela deixar de bater com o extrato -- que é
    # exatamente o que este bloco existe para garantir. Mesma regra do motor:
    # `machine._close_position` só troca o preço estimado pelo da corretora
    # quando há execução real.
    bruto = (_pl_brl(entrada, preco, int(posicao["quantity"]), posicao["side"],
                     _valor_do_ponto_brl(slot.symbol))
             if entrada > 0 else None)
    # LÍQUIDO, igual ao caminho de sombra e ao fechamento normal do motor
    # (2026-09-09). Aqui o caixa real é o extrato da corretora -- este módulo
    # nunca o escreve --, mas o número da tela é o que o dono compara com o
    # extrato: reportar bruto o faria procurar uma diferença que não existe.
    taxas = (None if bruto is None else
             _custos_de_saida(slot.symbol, int(posicao["quantity"]), entrada, preco))
    resultado.posicao_encerrada = {
        "quantity": int(posicao["quantity"]),
        "side": posicao["side"],
        "price": preco,
        "pl": None if bruto is None else round(bruto - (taxas or 0.0), 2),
        "taxas": taxas,
        # Sempre `None` nesta rota, e a chave existe para dizer isso: não é
        # "não houve derrapagem", é "ela está DENTRO do `avg_price` e não dá
        # para destacá-la". Só a rota de sombra, que modela o preço, sabe
        # quanto do resultado veio do tick.
        "deslize": None,
    }
    if executada.status == OrderStatus.PARTIAL:
        resultado.avisos.append(
            f"o fechamento preencheu só {executada.filled_qty} de "
            f"{posicao['quantity']} ações — o resto continua aberto no MT5.")
        return False
    return limpo


def _descartar_posicao_fantasma(slot, resultado: ResultadoRemocao) -> None:
    """O banco tem posição aberta, a CORRETORA CONFIRMOU que não tem nenhuma.
    Apaga a linha do banco -- ela é registro errado, não exposição.

    O IMPASSE QUE ISTO DESFAZ (achado ao vivo em 2026-09-09, com o dono
    tentando remover o robô e não conseguindo). O slot real tinha em
    `live_positions` um short de 1 WDO@ @ 5122,50 que o MT5 não tinha:

      * `inspecionar()` pergunta a posição à CORRETORA -- não há -- então
        `remover()` não tinha o que encerrar e seguia adiante;
      * `delete_account`/`archive_account` recusam olhando o BANCO -- "feche
        na corretora antes de remover o robô".

    Ou seja, a única instrução que a tela sabia dar era impossível de
    cumprir: não existe o que fechar. O robô ficava preso no painel para
    sempre. O guard dos dois lados está certo em separado; o que faltava era
    alguém reconciliar quando eles discordam.

    POR QUE É SEGURO apagar aqui, e só aqui: `Pendencias.impedimento` já
    barra a remoção inteira quando a corretora NÃO respondeu, e
    `position_state()` distingue "não há posição" de "não consegui
    perguntar" (é o motivo de ele existir em vez de `open_position`). Então,
    neste ponto, "não há posição" é uma afirmação CONFIRMADA pela corretora,
    não silêncio. Registro que contradiz a corretora é o registro que está
    errado -- a corretora é a fonte de verdade sobre o que existe.

    NÃO inventa trade nem P&L, e NÃO mexe no caixa. Não houve negócio: fechar
    "a mercado" uma posição que não existe escreveria um preço de execução
    que ninguém pagou (o mesmo erro do item 1.24, pelo avesso). O caixa é o
    ledger digitado pelo dono (ver CLAUDE.md, "Saldo do MT5 não é confiável")
    -- reconstruí-lo aqui seria chutar. Fica um `warn` no diário com os dois
    lados da divergência, para a auditoria achar depois."""
    from journal import live_store

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is None:
            return
        pos = conta.positions.get(slot.symbol)
        if pos is None:
            return
        lado = pos.metadata.get("side") or "long"
        live_store.delete_position(conn, conta.id, slot.symbol)
        live_store.save_account(conn, conta)
        live_store.log_event(
            conn, conta.id, "warn", "teardown",
            f"posição de {pos.quantity} {slot.symbol} @ {pos.entry_price:.4f} existia "
            f"no REGISTRO mas NÃO na corretora (consulta confirmada) -- linha "
            f"descartada na remoção do robô, sem trade e sem mexer no caixa: não "
            f"houve negócio para registrar.",
            {"quantity": pos.quantity, "side": lado,
             "entry_price": pos.entry_price, "motivo": "divergencia_registro_x_corretora"},
        )

    resultado.avisos.append(
        f"o registro tinha uma posição de {pos.quantity} {slot.symbol} @ "
        f"{pos.entry_price:.4f} que a corretora NÃO tem — a linha foi descartada "
        "(sem trade, sem mexer no caixa). Confira o extrato: registro e corretora "
        "estavam divergentes."
    )


def _encerrar_posicao_sombra(slot, resultado: ResultadoRemocao) -> None:
    """Fecha localmente a posição SIMULADA de um robô de sombra -- ele nunca
    teve corretora para consultar, então não há ordem para cancelar nem
    posição para encerrar lá fora. Sem isto, `delete_account`/
    `archive_account` recusam com o mesmo guard que protege um robô REAL de
    virar posição órfã no MT5 (`account.positions`), apesar de não haver
    nenhuma exposição de verdade -- só uma linha em `live_positions`, a
    mesma tabela que o robô real usa para bookkeeping.

    Relê a posição agora (não confia no que `inspecionar()` viu antes do
    processo morrer, mesmo motivo de `remover()` reler a corretora): o
    processo já foi encerrado no passo anterior, então nada mais está
    escrevendo nesta conta.

    Preço de saída, em duas etapas que não se misturam:

      * a MARCAÇÃO (`preco_marcado`) -- `_preco_de_saida`: cotação do
        terminal, parquet como retaguarda. Sem nenhum dos dois, ou com uma
        barra salva que `_preco_velho_demais` RECUSA, cai no próprio preço de
        entrada: estimar é melhor que travar a remoção, mas encerrar contra
        um preço de outra quinzena é pior que os dois (ver a docstring
        daquela função para por que a recusa é do PREÇO e nunca da remoção);
      * o preço EXECUTADO (`preco`) -- a marcação piorada em 1 tick por
        `_preco_de_execucao_a_mercado`, porque isto aqui é uma saída a
        mercado simulada e o motor cobra o tick nela (2026-09-09). É este
        que vira `Order`/`Fill` e resultado, como no motor.

    Credita em `cash_sombra` (nunca `cash`, o ledger manual real) -- mesma
    regra de `IntradayLiveRuntime._on_closed`.

    O CAIXA SE MOVE POR DOIS MOTIVOS SOMADOS, e eles são independentes (ver
    o bloco "a economia de uma posição" no topo do módulo):

      * `liberado` -- o capital que a ENTRADA prendeu volta inteiro. É
        `capital_allocated`, o mesmo número que `_on_closed` devolve: MARGEM
        num futuro (R$150/contrato de WDO@), preço cheio numa ação;
      * `pnl` -- o resultado, em REAIS, convertido do ponto do instrumento e
        LÍQUIDO dos DOIS custos que um fechamento a mercado paga
        (2026-09-09): corretagem/emolumentos (`_custos_de_saida`) e a
        derrapagem de 1 tick, que entra pelo PREÇO
        (`_preco_de_execucao_a_mercado`) e não como taxa, igual ao motor.
        Até 2026-09-09 ele era bruto nos dois eixos, e o efeito era que
        remover o robô com posição aberta creditava um número MELHOR do que
        fechar a mesma posição pelo caminho normal (`_on_closed`, que
        subtrai `IntradayTrade.fees_total` sobre um preço que a máquina já
        deslizou) -- duas rotas para o mesmo evento com contabilidade
        diferente.

    O que estava aqui somava as duas coisas erradas ao mesmo tempo, em
    2026-09-09, sobre um short de 1 WDO@ @ 5133,0 com `cash_sombra` de
    R$375,00: devolvia o NOCIONAL com o sinal da quantidade
    (`5133,00 x -1`) e chamava 52 pontos de perda de "lucro de R$52,00",
    fechando em **-R$4.706,00**. Com esta conta, o mesmo caso dá
    `375,00 + 150,00 - 520,00 = R$5,00`."""
    from journal import live_store

    with live_store.live_journal() as conn:
        conta = live_store.load_account(conn, slot.id)
        if conta is None:
            return
        pos = conta.positions.get(slot.symbol)
        if pos is None:
            return

        preco_atual, origem = _preco_de_saida(slot.symbol)
        # RECUSA de preço velho (item 5.19c, fechado em 2026-09-09). O aviso
        # sozinho não bastava: ele conta ao dono que o caixa recebeu um
        # número de outro dia DEPOIS de o número já estar lá, e ninguém
        # desfaz um crédito lendo um aviso. Barra salva anterior à própria
        # posição, ou com mais de `_IDADE_MAXIMA_DO_PRECO_DIAS` dias, não é
        # marcação -- cai no mesmo caminho de "não veio preço nenhum".
        recusado = _preco_velho_demais(origem, pos.entry_date)
        if recusado:
            preco_atual = None
        preco_marcado = preco_atual if preco_atual is not None else pos.entry_price
        lado = pos.metadata.get("side") or "long"
        # A saída é a MERCADO (simulada, mas a mercado): paga 1 tick, igual
        # ao que `machine._close_position` faz em sombra. Ver
        # `_preco_de_execucao_a_mercado` para por que a rota REAL não paga.
        preco = _preco_de_execucao_a_mercado(slot.symbol, preco_marcado, lado)
        # MÓDULO: o lado já está em `lado`, e `quantity` negativa de uma
        # vendida aplicaria o sinal uma segunda vez. Vale para a ordem e o
        # fill gravados também -- `Order.quantity` é TAMANHO, e `_on_closed`
        # grava sempre positivo.
        quantidade = abs(int(pos.quantity))
        valor_do_ponto = _valor_do_ponto_brl(slot.symbol)
        bruto = _pl_brl(pos.entry_price, preco, quantidade, lado, valor_do_ponto)
        # LÍQUIDO de corretagem/emolumentos, como `_on_closed` (ver
        # `_custos_de_saida`): creditar bruto aqui fazia remover o robô render
        # um pouco MAIS do que fechar a mesma posição pelo caminho normal. A
        # taxa percentual segue o preço EXECUTADO (`preco`, já com o tick de
        # derrapagem), não a marcação -- é sobre o notional real da perna que
        # a bolsa cobra.
        taxas = _custos_de_saida(slot.symbol, quantidade, pos.entry_price, preco)
        pnl = None if bruto is None else round(bruto - (taxas or 0.0), 2)
        liberado = _capital_comprometido(pos, slot.symbol)

        ordem = Order(
            ticker=slot.symbol,
            side=OrderSide.SELL if lado == "long" else OrderSide.BUY,
            quantity=quantidade,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            filled_qty=quantidade,
            avg_price=preco,
            sent_at=datetime.now(timezone.utc),
            note="encerrada ao remover o robô (sombra, sem corretora)",
        )
        order_id = live_store.record_order(conn, conta.id, ordem)
        live_store.record_fill(conn, Fill(
            order_id=order_id, quantity=quantidade, price=preco,
            ts=datetime.now(timezone.utc),
        ))
        live_store.delete_position(conn, conta.id, slot.symbol)
        # `pnl is None` = instrumento cujo valor do ponto não se descobriu.
        # O capital preso volta de qualquer jeito (esse número é certo), mas
        # o resultado NÃO é chutado: creditar pontos como se fossem reais
        # erraria por 10x num WDO@, e o dono fica sabendo pelo aviso.
        conta.cash_sombra += liberado + (pnl if pnl is not None else 0.0)
        live_store.save_account(conn, conta)
        resultado_txt = (
            f"{'lucro' if pnl >= 0 else 'prejuízo'} de R$ {abs(pnl):.2f}"
            if pnl is not None else
            f"resultado NÃO apurado: não sei quanto vale 1 ponto de {slot.symbol}")
        live_store.log_event(
            conn, conta.id, "info" if pnl is not None else "warn", "teardown",
            f"posição simulada de {quantidade} {slot.symbol} ({lado}) encerrada a "
            f"R$ {preco:.2f} ao remover o robô ({resultado_txt}; R$ {liberado:.2f} "
            f"de capital devolvido ao caixa de sombra)",
            # `price` é o EXECUTADO e `preco_marcado` é a marcação de onde
            # ele saiu: sem os dois no diário não dá para auditar depois nem
            # quanto de derrapagem foi cobrado nem de que preço ela partiu.
            # `preco_recusado` fica gravado mesmo valendo `None`, para uma
            # remoção que caiu no preço de entrada dizer POR QUE caiu.
            {"quantity": quantidade, "side": lado, "price": preco,
             "preco_marcado": preco_marcado, "origem_preco": origem,
             "preco_recusado": recusado, "pnl_brl": pnl, "pnl_bruto_brl": bruto,
             "taxas_brl": taxas, "liberado_brl": liberado,
             "valor_do_ponto_brl": valor_do_ponto},
        )

    if pnl is None:
        resultado.avisos.append(
            f"a posição simulada de {quantidade} {slot.symbol} foi encerrada e o "
            f"capital de R$ {liberado:.2f} voltou ao caixa de sombra, mas o "
            "RESULTADO não entrou nele: não sei quanto vale 1 ponto deste "
            "instrumento (robô fora do catálogo?). Confira o caixa de sombra.")

    # PREÇO VELHO É AVISO, NUNCA SILÊNCIO (item 5.19c) -- e, desde
    # 2026-09-09, velho DEMAIS é recusa, não só aviso. `origem` é `"agora"`
    # quando a cotação veio do terminal; qualquer outra coisa é a data da
    # última barra SALVA em parquet, e nada salva aquele arquivo sozinho --
    # foi assim que um WDO@ foi encerrado contra um preço de 12 dias antes,
    # em 2026-09-09. A remoção nunca trava por causa disso (travar deixaria o
    # robô preso no painel por causa de um terminal fechado); o que muda com
    # a idade é se aquele número entra ou não no caixa de sombra.
    #
    # Três desfechos, três textos -- e a diferença entre eles é o que o dono
    # precisa para saber se confere o extrato, espera o terminal abrir, ou
    # não faz nada:
    if recusado:
        # Havia preço, e ele foi RECUSADO. Este é o único dos três em que o
        # dono pode consertar o número: reabrir o MT5 (ou baixar o parquet) e
        # remover de novo daria um resultado de verdade.
        resultado.avisos.append(
            f"NÃO usei o preço salvo de {slot.symbol}: {recusado}. A posição foi "
            f"encerrada pelo PRÓPRIO preço de entrada (R$ {preco_marcado:.2f}), então "
            "o que entrou no caixa de sombra é só o custo do round-trip (corretagem "
            "e 1 tick de derrapagem), NÃO o resultado da posição. Marcar uma posição "
            "a um preço desses creditaria um movimento de mercado que ela nunca "
            "viveu — com o terminal MT5 aberto o número sai certo.")
    elif preco_atual is None:
        # Nem terminal nem parquet responderam. A posição sai pelo próprio
        # preço de entrada (resultado bruto zero) para não travar a remoção,
        # mas isso NÃO é "deu na mesma": é "não sei", e a diferença tem de
        # aparecer na tela.
        resultado.avisos.append(
            f"não consegui preço nenhum para {slot.symbol} (nem terminal, nem barra "
            f"salva): a posição foi encerrada pelo PRÓPRIO preço de entrada "
            f"(R$ {preco_marcado:.2f}), então o resultado creditado no caixa de "
            "sombra é só o custo do round-trip (corretagem e 1 tick de derrapagem), "
            "não o resultado de verdade.")
    elif origem and origem != "agora":
        # Velha, mas dentro do limite: vale mais que nada, e o dono lê a
        # data para julgar sozinho.
        resultado.avisos.append(
            f"o preço de saída de {slot.symbol} (R$ {preco_marcado:.2f}) NÃO é a "
            f"cotação de agora: veio da última barra salva em {origem} (terminal MT5 "
            "fechado ou sem resposta). O resultado creditado no caixa de sombra vale "
            "o que esse preço valer.")

    resultado.posicao_encerrada = {
        "quantity": quantidade, "side": lado, "price": preco, "pl": pnl,
        "taxas": taxas,
        # A derrapagem em REAIS, separada da taxa: as duas saem do bolso do
        # mesmo jeito, mas só uma aparece no extrato como linha de custo, e
        # confundi-las é o que faria o dono procurar R$5,00 que "sumiram".
        # `None` quando não se sabe converter ponto em real -- mesmo critério
        # do `pnl`, e pelo mesmo motivo (chutar erra 10x num WDO@).
        "deslize": (None if valor_do_ponto is None else
                    round(abs(preco - preco_marcado) * quantidade
                          * float(valor_do_ponto), 2)),
    }
