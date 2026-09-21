"""O GENOMA do robo evoluido -- 33 numeros, e por que sao 33.

## O tamanho e' a decisao central deste arquivo

A janela de treino tem 52 pregoes e produz, num robo desta familia, algo como
150 a 400 operacoes. Esse numero e' o orcamento de evidencia disponivel, e a
razao entre parametros livres e operacoes decide se a busca APRENDE ou
DECORA. Uma rede densa 33->8->3 teria 299 pesos livres -- razao pior que
1:1, que e' memorizacao com outro nome: ela produziria um IS espetacular e
nada fora dele. A literatura de inducao de regra de trading por algoritmo
evolutivo diz a mesma coisa de forma mais dura (Allen & Karjalainen 1999:
regras programadas geneticamente nao batem buy-and-hold fora da amostra
depois do custo), e aponta a "pressao de parcimonia" como o controle que mais
importa e que menos se usa.

Aqui a parcimonia nao e' uma penalidade no fitness que se possa afrouxar
depois: e' o TAMANHO DO VETOR. 33 numeros, razao ~1:8. Um individuo nao
tem como ficar complexo porque nao ha onde guardar a complexidade.

    6 encaixes x (indice de feature, a, b, modo)                     = 24
    1 limiar de acao                                                 =  1
    8 numeros de geometria e janela de operacao                      =  8
                                                                      ---
                                                                       33

O banco de features tem 33 coordenadas e o individuo escolhe 6. Isto e' o que
permitiu atender ao pedido do dono de "nao limitar a evolucao ao que sabemos"
sem inchar o genoma: DOBRAR o banco de features nao acrescenta um unico
parametro livre, muda so' o alcance de um indice que ja' existia. O espaco de
DESCOBERTA cresce; o de MEMORIZACAO nao. Ver a docstring de `features.py`.

## A segunda decisao: genoma ilegal e' IRREPRESENTAVEL

O vetor bruto vive em `[0, 1]^33` e SEMPRE decodifica para uma ordem que a
corretora aceita. Isso nao e' conveniencia de implementacao -- e' a defesa
principal contra a busca. Validar depois ("se o alvo for 1 tick, descarte")
seria porta que a evolucao arromba por acidente: basta um individuo cujo alvo
so' fica ilegal em alguns dias. O que nao pode existir nao precisa ser
vigiado.

O que fica de fora do espaco por construcao, e a procedencia de cada
proibicao (todas em CLAUDE.md):

  * **entrada a mercado** -- `offset_ticks >= 1` sempre, entao a limite
    nasce do lado FAVORAVEL do preco corrente e nunca atravessa o livro. O
    motor nem sequer sabe executar entrada a mercado (`EntradaAMercadoNao
    Suportada`), mas depender disso seria deixar a regra num `raise`;
  * **alvo de 1 tick** -- `ALVO_MINIMO_TICKS = 8`. A proibicao vale para
    qualquer robo com `target_fills_as_maker=True`, e hoje a razao nao e' so'
    o deslize do `tp` nativo: e' a FILA. Um nivel a poucos ticks da entrada
    e' o mais disputado do livro, e a calibracao real (329 na entrada, 494 na
    saida) ja' mostra que ate' alvo normal pena para preencher;
  * **ordem de entrada sem prazo** -- `ttl_min` e' limitado a [1, 30]
    minutos. Sem prazo a limite espera ate' o fim do pregao: ja' foi medido
    um preenchimento 269,7 minutos depois do sinal, que nao e' a operacao que
    a estrategia pediu, e' uma ordem esquecida no livro. E o prazo mora em
    MINUTOS, nao em barras, porque `ttl_bars` conta BARRAS e em base de tick
    isso nao e' tempo (~336 barras por minuto);
  * **stop menor que a barra** -- `STOP_TICKS` comeca em 8. Um stop mais
    apertado que a amplitude tipica de um minuto nao e' mensuravel em M1: a
    barra ambigua resolveria tudo, e a evolucao aprenderia a geometria do
    simulador em vez da do mercado.

## Por que 6 encaixes e nao 33 pesos

Com um peso por feature a politica teria 66 pesos e todas as coordenadas
sempre ligadas. Com 6 encaixes que APONTAM para features, a selecao de
variavel vira parte do que evolui: a maioria das 33 features fica de fora de
qualquer individuo, e quais entraram e' legivel direto no relatorio. Dois
encaixes podem cair na mesma feature -- e' inofensivo, apenas reduz a
dimensao efetiva daquele individuo, e e' uma forma de a busca se
auto-simplificar sem que ninguem tenha programado isso.

## Uma ressalva que tem de viajar junto com qualquer resultado daqui

Abrir o banco de features e admitir portas condicionais aumenta o numero de
TENTATIVAS EFETIVAS da busca. Isso e' desejado (e' o que permite achar o que
ninguem procurou), mas tem uma consequencia estatistica que nao se negocia:
quanto maior o espaco, mais provavel que o melhor individuo DENTRO da amostra
seja sorte. E' o argumento do Deflated Sharpe Ratio, e vale aqui literalmente
-- com 6 especies x dezenas de individuos x dezenas de geracoes, o campeao do
treino foi escolhido entre dezenas de milhares de candidatos.

A consequencia pratica: o numero que vale NUNCA e' o do treino. E' o da
janela cega, e a barra dela SOBE quando o espaco abre, nao desce.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from strategy.daytrade.evo import features

#: Quantas features UM individuo pode olhar. Ver a docstring do modulo.
N_ENCAIXES = 6

#: Quantos numeros cada encaixe ocupa: (indice, a, b, modo).
GENES_POR_ENCAIXE = 4

#: Acima deste valor o encaixe e' uma PORTA; abaixo, um somador. Ver
#: `Genoma.encaixes`.
MODO_PORTA = 0.5

#: ORDEM DO DONO, 2026-09-18: nenhuma geometria deste projeto trabalha com
#: menos de 3 PONTOS. "Menos que isso corre o risco de algum escorregao de
#: preco dar a impressao de um bom resultado, mas na pratica nao."
#:
#: A razao e' de medicao, nao de gosto. Um alvo de 2 pontos (4 ticks, R$20)
#: contra um deslize de 1 tick (R$5) entrega 25% do bruto ao atrito: o
#: resultado vira uma medida do custo, nao do sinal. E quanto menor o alvo,
#: maior a fracao do resultado que qualquer imprecisao do simulador consegue
#: fabricar -- que e' a mesma armadilha que fez a grade de 250 celulas eleger
#: o T1.
ALVO_MINIMO_PONTOS = 3.0
#: Tamanho do tick do WDO@ em pontos. Mora aqui (e nao lido do perfil) porque
#: `strategy/` nao importa `backtest/`; e' o mesmo 0,5 de
#: `SymbolProfile.price_tick_size`.
TICK_EM_PONTOS = 0.5

#: Piso do alvo em TICKS -- o mais restritivo entre a ordem dos 3 pontos
#: (6 ticks) e o piso proprio da familia maker (8 ticks). Os 8 ticks vem de
#: outra restricao, independente: a proibicao do T1 vale para qualquer robo
#: com `target_fills_as_maker=True`, e hoje a razao nao e' so' o deslize do
#: `tp` nativo, e' a FILA -- um nivel a poucos ticks da entrada e' o mais
#: disputado do livro. As duas regras existem por motivos diferentes e a que
#: manda e' a mais dura. NAO afrouxe nenhuma das duas sem um pregao real
#: medido ao lado mostrando preenchimento de alvo curto.
ALVO_MINIMO_TICKS = max(8, int(-(-ALVO_MINIMO_PONTOS // TICK_EM_PONTOS)))

#: (nome, minimo, maximo, inteiro?) -- os 8 numeros de geometria/janela, na
#: ordem em que ocupam o vetor depois dos encaixes e do limiar.
GEOMETRIA: tuple[tuple[str, float, float, bool], ...] = (
    # Onde pendurar a limite de entrada, em ticks do lado FAVORAVEL do preco
    # corrente. Comeca em 1: zero seria ordem a mercado disfarcada.
    ("offset_ticks", 1, 10, True),
    # Prazo da ordem de entrada, em MINUTOS.
    ("ttl_min", 1, 30, False),
    # Distancia do stop, em ticks. O teto de 40 vem do `wdo_orb`, cujo
    # `stop_max_ticks` foi baixado de 40 para 30 por medicao; deixo 40 como
    # teto do espaco para a busca poder DISCORDAR, e nao herdar o resultado
    # de outra geometria como se fosse lei.
    ("stop_ticks", 8, 40, True),
    # Alvo = stop x este multiplo, com piso de ALVO_MINIMO_TICKS.
    ("alvo_mult", 0.6, 3.0, False),
    # Teto de operacoes por pregao.
    ("max_ops_dia", 1, 4, True),
    # Janela de operacao DENTRO do pregao, em fracao da sessao. A sessao em
    # si (12:00-21:30 UTC, achatamento 21:25) nao esta aqui: ela e' do
    # PERFIL do simbolo, herdada de `config_for`, a mesma que sobe o robo
    # sombra. O genoma so' escolhe um pedaco de dentro dela.
    ("hora_ini", 0.0, 0.5, False),
    ("hora_fim", 0.5, 1.0, False),
    # Corte do relogio: N minutos depois da entrada, o alvo e' movido para o
    # preco corrente (vira ordem-limite parada no nivel novo, nao saida a
    # mercado). O mecanismo e' copiado do `wdo_orb`, onde valeu +81% de
    # liquido sem tocar num parametro de estrategia.
    ("corte_min", 15, 180, True),
)

N_GENES = N_ENCAIXES * GENES_POR_ENCAIXE + 1 + len(GEOMETRIA)

#: Limiar minimo e maximo do score para agir. Um limiar muito baixo faz o
#: robo operar toda barra; muito alto o cala. A busca escolhe onde ficar.
THETA_MIN, THETA_MAX = 0.05, 1.5

#: Peso minimo de um encaixe de NUCLEO para ele contar como participacao.
#:
#: MEDIDO em 2026-09-19: a ilha `vwap` satisfez o nucleo com um encaixe em
#: `dist_vwap` de peso |a|,|b| < 0,05 -- a feature estava no genoma e nao
#: fazia nada. O painel ate' o escondia, por trata-la como inerte. Era a saida
#: BARATA da restricao, e uma busca acha saida barata por construcao: ela nao
#: precisou abandonar a premissa, so' precisou zerar o peso dela.
#:
#: A licao generaliza para qualquer restricao imposta a um otimizador --
#: **restringir a FORMA sem restringir o EFEITO nao restringe nada.** Com
#: theta minimo em 0,05 e features em [-1,1], 0,15 e' peso que muda decisao
#: sem dominar o resto do genoma.
PESO_MINIMO_NUCLEO = 0.15


@dataclass(frozen=True)
class Encaixe:
    """Um dos 6 encaixes de um individuo -- quatro numeros que significam
    duas coisas diferentes conforme o modo.

    Os dois modos existem por um pedido explicito do dono (2026-09-18): a IA
    tem de poder "vencer instintivamente, ter lucro mesmo parecendo que nao
    esta' seguindo uma regra". Uma soma ponderada pura nao consegue isso --
    ela e' monotonica em toda feature, entao o comportamento dela e' sempre
    legivel como "quanto mais X, mais compra". O que produz decisao que nao
    parece regra e' CONDICAO: agir so' quando varias coisas coincidem.

      * **somador** (`porta=False`) -- contribui `a * f` para o score de
        comprar e `b * f` para o de vender. E' a coordenada continua;
      * **porta** (`porta=True`) -- nao contribui com nada; MULTIPLICA os
        dois scores por 0 ou 1 conforme `f` esteja do lado certo de `a`. O
        sinal de `b` escolhe o lado (`f >= a` ou `f <= a`). Duas portas em
        series produzem uma conjuncao, e uma conjuncao de tres features com
        uma soma por cima ja' e' uma funcao que nenhum humano escreveria.

    O custo disso e' UM numero por encaixe (o modo). O ganho e' a classe de
    funcoes deixar de ser linear sem o genoma inchar -- que e' a unica forma
    de abrir a busca sem abrir a porta para memorizacao."""

    idx: int
    a: float
    b: float
    porta: bool

    def aplica(self, valor: float) -> bool:
        """So' para o modo porta: o encaixe deixa passar?"""
        return valor >= self.a if self.b >= 0 else valor <= self.a


def _escala(u: float, lo: float, hi: float, inteiro: bool) -> float | int:
    u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else float(u))
    v = lo + u * (hi - lo)
    return int(round(v)) if inteiro else v


@dataclass(frozen=True)
class Genoma:
    """Um individuo. `cru` e' o vetor em [0,1]^27; tudo o mais e' leitura.

    Imutavel de proposito: mutacao e cruzamento produzem genomas NOVOS. Um
    individuo que pudesse ser alterado no lugar apareceria duas vezes no hall
    da fama com numeros diferentes, e o relatorio final nao teria como dizer
    qual foi medido."""

    cru: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.cru) != N_GENES:
            raise ValueError(
                f"genoma tem de ter {N_GENES} numeros, recebeu {len(self.cru)}"
                f" -- o comprimento e' contrato entre `genoma.py`, o operador "
                f"de cruzamento e todo genoma ja salvo em disco.")

    # -- leitura -----------------------------------------------------------

    @property
    def encaixes(self) -> list[Encaixe]:
        """Os 6 encaixes decodificados. Ver `Encaixe` para o que cada modo
        faz com os mesmos quatro numeros."""
        saida = []
        for k in range(N_ENCAIXES):
            base = k * GENES_POR_ENCAIXE
            idx = min(int(self.cru[base] * features.N_FEATURES),
                      features.N_FEATURES - 1)
            saida.append(Encaixe(
                idx=idx,
                a=self.cru[base + 1] * 2.0 - 1.0,
                b=self.cru[base + 2] * 2.0 - 1.0,
                porta=self.cru[base + 3] >= MODO_PORTA,
            ))
        return saida

    @property
    def theta(self) -> float:
        return _escala(self.cru[N_ENCAIXES * GENES_POR_ENCAIXE],
                       THETA_MIN, THETA_MAX, False)

    @property
    def geometria(self) -> dict:
        """Os 8 numeros de geometria/janela ja' escalados e ja' LEGAIS."""
        base = N_ENCAIXES * GENES_POR_ENCAIXE + 1
        d = {nome: _escala(self.cru[base + i], lo, hi, inteiro)
             for i, (nome, lo, hi, inteiro) in enumerate(GEOMETRIA)}
        # As duas correcoes abaixo sao o que torna o espaco fechado. Nao sao
        # validacoes (que poderiam falhar): sao projecoes, e todo ponto do
        # cubo cai dentro do conjunto legal.
        d["alvo_ticks"] = max(ALVO_MINIMO_TICKS,
                              int(round(d["stop_ticks"] * d["alvo_mult"])))
        if d["hora_fim"] <= d["hora_ini"]:
            d["hora_fim"] = min(1.0, d["hora_ini"] + 0.1)
        return d

    # -- persistencia ------------------------------------------------------

    def to_json(self) -> str:
        return json.dumps({"cru": list(self.cru)})

    @classmethod
    def from_json(cls, texto: str) -> "Genoma":
        return cls(cru=tuple(json.loads(texto)["cru"]))

    def descricao(self) -> str:
        """O individuo em texto legivel -- e' isto que vai para o relatorio e
        e' isto que alguem transcreve para MQL5. Um genoma que so' existe
        como 27 floats nao e' um robo que alguem consegue operar."""
        g = self.geometria
        linhas = [
            f"limiar  theta = {self.theta:.3f}",
            f"entrada limite a {g['offset_ticks']} tick(s) do preco, "
            f"prazo {g['ttl_min']:.1f} min",
            f"stop {g['stop_ticks']} ticks  |  alvo {g['alvo_ticks']} ticks "
            f"({g['alvo_mult']:.2f}x o stop)",
            f"ate' {g['max_ops_dia']} operacao(oes) por pregao, "
            f"entre {g['hora_ini']:.0%} e {g['hora_fim']:.0%} da sessao",
            f"corte do relogio: {g['corte_min']} min apos a entrada",
            "score =",
        ]
        for e in self.encaixes:
            nome = features.NOMES[e.idx]
            if e.porta:
                sinal = ">=" if e.b >= 0 else "<="
                linhas.append(f"    PORTA: so' age se {nome} {sinal} "
                              f"{e.a:+.3f}")
            else:
                linhas.append(f"    {nome:<16} comprar {e.a:+.3f}   "
                              f"vender {e.b:+.3f}")
        return "\n".join(linhas)


def genoma_aleatorio(rng, features_permitidas: Sequence[int] | None = None
                     ) -> Genoma:
    """Um individuo sorteado. `features_permitidas` restringe de quais
    coordenadas os encaixes podem sair -- e' o que define uma ESPECIE
    (`scripts/daytrade/evo/especies.py`): uma populacao proibida de olhar o
    bloco destilado so' pode descobrir coisa nova, porque nao tem acesso ao
    que ja' sabemos."""
    cru = [float(rng.random()) for _ in range(N_GENES)]
    if features_permitidas:
        for k in range(N_ENCAIXES):
            escolha = features_permitidas[
                rng.randrange(len(features_permitidas))]
            cru[k * GENES_POR_ENCAIXE] = _u_do_indice(escolha)
    return Genoma(cru=tuple(cru))


def _u_do_indice(idx: int) -> float:
    """O valor em [0,1] que decodifica para `idx` -- o centro da faixa, para
    uma mutacao pequena nao trocar de feature por acidente."""
    return (idx + 0.5) / features.N_FEATURES


def projeta_em(g: Genoma, features_permitidas: Sequence[int]) -> Genoma:
    """Puxa todo encaixe de `g` para dentro do conjunto permitido, escolhendo
    a feature permitida mais proxima.

    Chamado depois de mutacao/cruzamento dentro de uma especie restrita. Sem
    isto a restricao vazaria na primeira geracao: um gene de indice mutado
    sairia do conjunto e a especie "cega" passaria a enxergar. E' projecao e
    nao rejeicao pelo mesmo motivo de sempre -- o que nao pode existir nao
    precisa ser vigiado."""
    if not features_permitidas:
        return g
    cru = list(g.cru)
    for k in range(N_ENCAIXES):
        pos = k * GENES_POR_ENCAIXE
        idx = min(int(cru[pos] * features.N_FEATURES), features.N_FEATURES - 1)
        if idx not in features_permitidas:
            perto = min(features_permitidas, key=lambda c: abs(c - idx))
            cru[pos] = _u_do_indice(perto)
    return Genoma(cru=tuple(cru))


def semear(geometria: dict, encaixes: Sequence[tuple[int, float, float, bool]]
           ) -> Genoma:
    """Um individuo PLANTADO: geometria e encaixes escolhidos a mao.

    Serve para uma especie comecar na vizinhanca de uma hipotese conhecida em
    vez de no meio do nada. Nao e' trapaca nem atalho para o resultado: o
    semeado compete pelo mesmo fitness que todo mundo, e um unico plantado
    numa populacao de dezenas nao domina nada. O valor dele e' de LEITURA --
    se depois de N geracoes a especie nao tiver superado o ponto de partida
    que ja' se conhecia, isso e' um resultado claro ("a evolucao nao achou
    nada melhor") em vez de uma duvida sobre se ela chegou perto."""
    def inv(v, lo, hi):
        return min(1.0, max(0.0, (v - lo) / (hi - lo)))

    cru = [0.5] * N_GENES
    for k, (idx, a, b, porta) in enumerate(encaixes[:N_ENCAIXES]):
        pos = k * GENES_POR_ENCAIXE
        cru[pos] = _u_do_indice(idx)
        cru[pos + 1] = (a + 1.0) / 2.0
        cru[pos + 2] = (b + 1.0) / 2.0
        cru[pos + 3] = 0.9 if porta else 0.1
    base = N_ENCAIXES * GENES_POR_ENCAIXE
    cru[base] = inv(geometria.get("theta", 0.35), THETA_MIN, THETA_MAX)
    for i, (nome, lo, hi, _int) in enumerate(GEOMETRIA):
        if nome in geometria:
            cru[base + 1 + i] = inv(geometria[nome], lo, hi)
    return Genoma(cru=tuple(cru))


def cruzar(a: Genoma, b: Genoma, rng) -> Genoma:
    """Cruzamento UNIFORME por gene, com mistura aritmetica.

    Uniforme (e nao de ponto de corte) porque o vetor nao tem vizinhanca
    significativa: o gene 3 e o gene 4 pertencem a encaixes diferentes, entao
    preservar blocos contiguos nao preserva nada. A mistura (`u` continuo)
    entra em metade dos genes para a busca conseguir andar ENTRE dois pais
    bons, e nao so' escolher um dos dois -- num espaco continuo, so' trocar
    genes converge cedo demais."""
    filho = []
    for i in range(N_GENES):
        if rng.random() < 0.5:
            filho.append(a.cru[i] if rng.random() < 0.5 else b.cru[i])
        else:
            p = rng.random()
            filho.append(a.cru[i] * p + b.cru[i] * (1.0 - p))
    return Genoma(cru=tuple(filho))


def mutar(g: Genoma, rng, taxa: float = 0.15, forca: float = 0.20) -> Genoma:
    """Mutacao gaussiana por gene, refletida na borda do cubo.

    REFLETIDA e nao truncada: truncar em 0 e 1 acumula individuos exatamente
    na parede (todo gene que estoura vira 0,0 ou 1,0), e a populacao ganha um
    vies para os extremos do espaco que ninguem escolheu. Refletir mantem a
    densidade uniforme perto da borda."""
    novo = list(g.cru)
    for i in range(N_GENES):
        if rng.random() < taxa:
            v = novo[i] + rng.gauss(0.0, forca)
            while v < 0.0 or v > 1.0:
                v = -v if v < 0.0 else 2.0 - v
            novo[i] = v
    return Genoma(cru=tuple(novo))


def garante_nucleo(g: Genoma, nucleo: Sequence[int], minimo: int) -> Genoma:
    """Forca `minimo` encaixes de `g` a apontarem para dentro de `nucleo`.

    ## Por que isto existe (medido em 2026-09-19)

    Na primeira rodada longa a premissa de cada especie entrava de dois
    jeitos: `features_permitidas` (estrutural) e um individuo SEMEADO
    (sugestao). Ao fim de 65 geracoes, das 28 features semeadas nas 7
    especies que dependiam so' da semente, os campeoes ainda usavam **1**.
    As 2 especies cuja premissa era estrutural ficaram **100% dentro** dela.

    A conclusao e' mecanica, nao interpretativa: uma semente e' um individuo
    entre centenas e some na primeira geracao; uma restricao de
    representacao nao some nunca. Se a premissa de uma ilha nao for
    estrutural, a ilha nao tem premissa -- e dez ilhas sem premissa sao a
    MESMA busca dez vezes, com o custo estatistico de dez tentativas
    independentes e nenhuma da diversidade que justificava paga-lo.

    O nucleo e' deliberadamente PARCIAL: reserva `minimo` dos
    `N_ENCAIXES` encaixes e deixa o resto livre. A especie continua podendo
    descobrir o que quiser -- ela so' nao pode deixar de ser ela mesma.

    Projecao, nao rejeicao, pelo mesmo motivo de sempre: o que nao pode
    existir nao precisa ser vigiado. E o gene continua mandando em QUAL
    feature do nucleo o encaixe cai, entao a mutacao ainda se move dentro
    dele em vez de ficar presa num ponto."""
    if not nucleo or minimo <= 0:
        return g
    cru = list(g.cru)
    dentro = [k for k in range(N_ENCAIXES)
              if _indice_do_encaixe(cru, k) in nucleo]
    if len(dentro) >= minimo:
        return _com_peso(cru, dentro[:minimo], g)
    # Converte os ULTIMOS encaixes de fora -- os primeiros costumam carregar
    # a semente escrita a mao, e trocar justo eles apagaria a hipotese que o
    # nucleo existe para proteger.
    fora = [k for k in range(N_ENCAIXES) if k not in dentro]
    for k in reversed(fora[-(minimo - len(dentro)):] or fora):
        if len(dentro) >= minimo:
            break
        pos = k * GENES_POR_ENCAIXE
        alvo = nucleo[min(int(cru[pos] * len(nucleo)), len(nucleo) - 1)]
        cru[pos] = _u_do_indice(alvo)
        dentro.append(k)
    return _com_peso(cru, dentro[:minimo], g)


def _com_peso(cru: list[float], encaixes: Sequence[int], original: Genoma
              ) -> Genoma:
    """Garante que os encaixes de nucleo PESEM -- ver `PESO_MINIMO_NUCLEO`.

    Porta nao precisa de peso: ela veta, e vetar sempre age. So' o encaixe
    aditivo pode existir com coeficiente nulo e nao fazer nada.

    Empurra apenas o MAIOR dos dois coeficientes (compra / venda), preservando
    o sinal: forcar os dois mudaria a semantica do encaixe, e o gene continua
    mandando na direcao."""
    mexeu = False
    for k in encaixes:
        pos = k * GENES_POR_ENCAIXE
        if cru[pos + 3] >= MODO_PORTA:        # porta: age sempre
            continue
        a, b = cru[pos + 1] * 2.0 - 1.0, cru[pos + 2] * 2.0 - 1.0
        if max(abs(a), abs(b)) >= PESO_MINIMO_NUCLEO:
            continue
        j = pos + 1 if abs(a) >= abs(b) else pos + 2
        v = a if j == pos + 1 else b
        # A FOLGA de 1e-6 nao e' estetica. O gene guarda (peso+1)/2 e o
        # decodificador faz cru*2-1: gravar exatamente 0,15 devolve
        # 0,14999999999999991, um fio ABAIXO do limiar, e o invariante que
        # acabou de ser imposto falha na propria leitura seguinte. Qualquer
        # restricao gravada num espaco codificado tem de mirar dentro da
        # regiao legal, nunca na fronteira dela.
        margem = PESO_MINIMO_NUCLEO + 1e-6
        cru[j] = ((margem if v >= 0 else -margem) + 1.0) / 2.0
        mexeu = True
    return Genoma(cru=tuple(cru)) if mexeu or cru != list(original.cru) \
        else original


def _indice_do_encaixe(cru: Sequence[float], k: int) -> int:
    pos = k * GENES_POR_ENCAIXE
    return min(int(cru[pos] * features.N_FEATURES), features.N_FEATURES - 1)
