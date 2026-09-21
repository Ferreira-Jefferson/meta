"""O LACO EVOLUTIVO -- ilhas em passo travado, fitness ruidoso de proposito.

## As tres escolhas que definem esta busca

**1. As especies avancam JUNTAS, sobre a MESMA amostra.** A cada geracao um
subconjunto de pregoes e' sorteado uma unica vez e serve as 6 ilhas. Isso nao
e' economia: e' o que torna o fitness de `cega` comparavel ao de `rompimento`
naquela geracao. Se cada ilha visse pregoes diferentes, a que tivesse sorteado
os dias faceis pareceria melhor, e o painel estaria mostrando sorte de
sorteio com cara de progresso evolutivo.

**2. A amostra MUDA a cada geracao.** Comecou como necessidade de tempo
(metade dos pregoes, metade do custo), mas o efeito que importa e' outro: nao
existe janela fixa para o individuo decorar. Um genoma que so' funciona em
marco e' desmascarado na geracao em que marco nao cair no sorteio. O preco e'
fitness RUIDOSO, e ele e' pago logo abaixo.

**3. Os elites sao REAVALIADOS, nunca carregados.** Com fitness ruidoso,
elitismo ingenuo e' uma catraca de sorte: o individuo que teve o sorteio mais
generoso entra no hall e nunca mais e' questionado, e em 40 geracoes a
populacao inteira descende de um golpe de sorte da geracao 3. Aqui todo
individuo -- elite inclusive -- e' medido de novo na amostra da geracao
corrente. Um campeao que so' era campeao naquele sorteio cai sozinho.

## O que este arquivo NAO decide

Nao decide nada sobre mercado. Fitness mora em `avaliacao.py`, as premissas em
`especies.py`, o que pode ser expresso em `genoma.py`. Aqui so' ha' selecao,
cruzamento, mutacao e contabilidade -- de proposito, para que trocar o
criterio de selecao nao possa mudar em silencio o que esta' sendo medido.
"""
from __future__ import annotations

import json
import random
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from strategy.daytrade.evo import features as F
from strategy.daytrade.evo.genoma import (
    Genoma, cruzar, mutar,
)

from evo.avaliacao import (
    FITNESS_SEM_AMOSTRA, avalia, fitness_medido, fitness_morte,
    min_trades, resumo_pontos)
from evo.dados import CAPITAL_PARTIDA_BRL, MARGEM_WDO_BRL, pregoes
from evo.especies import Especie

#: Quantos individuos disputam cada vaga de reproducao. 3 e' o classico: 2
#: e' quase sorteio (pressao seletiva fraca demais para 40 geracoes) e 5+
#: converge cedo demais, que e' exatamente o que o modelo de ilhas existe
#: para evitar.
TORNEIO = 3

#: Quantos melhores passam direto para a geracao seguinte -- REAVALIADOS na
#: amostra nova, ver a parte 3 da docstring.
N_ELITE = 2

#: Fracao da nova geracao que nasce de sorteio puro, em vez de cruzamento.
#: E' a valvula contra a ilha inteira virar clone do mesmo ancestral: sem
#: ela, populacao pequena em espaco continuo perde diversidade em ~15
#: geracoes e as ultimas 25 nao procuram mais nada.
FRACAO_SANGUE_NOVO = 0.10

#: Em quantos blocos DISJUNTOS cada individuo e' medido por geracao. O escore
#: e' o PIOR deles -- ver `_avalia_worker`. Tres blocos de 17 cobrem os 52
#: pregoes do treino inteiro, entao a loteria de "que trecho calhou" some.
N_BLOCOS_FITNESS = 3


def blocos_da_geracao(dias_treino: list[str], amostra: int, semente: int,
                      g: int) -> list[list[str]]:
    """Os `N_BLOCOS_FITNESS` blocos DISJUNTOS e CONTIGUOS de uma geracao.

    Disjuntos porque medir o mesmo genoma duas vezes no mesmo trecho nao
    acrescenta informacao nenhuma, so' custo. Contiguos porque o resultado
    depende do CAMINHO -- o caixa anda de um pregao para o seguinte, entao
    encadear dias que na realidade estavam a semanas de distancia produz uma
    trajetoria que nunca existiu (ver `avaliacao.py`).

    O deslocamento sorteado por geracao move as FRONTEIRAS da particao; ele
    nao escolhe mais "qual trecho vale", porque todo individuo enfrenta os
    tres blocos e e' julgado pelo pior deles."""
    folga = len(dias_treino) - N_BLOCOS_FITNESS * amostra
    desloc = random.Random(semente * 100_000 + g).randrange(
        0, max(1, folga + 1))
    blocos = [dias_treino[desloc + j * amostra: desloc + (j + 1) * amostra]
              for j in range(N_BLOCOS_FITNESS)]
    return [b for b in blocos if len(b) >= 2]


def _avalia_worker(carga):
    """Roda num processo separado. Recebe e devolve so' coisa picklavel --
    o vetor cru do genoma, nunca a instancia do robo (que carrega deques e
    estado de sessao).

    ## Pontua pelo PIOR bloco, nao pela media deles

    `carga` traz VARIOS blocos disjuntos, e cada um e' uma vida inteira:
    o caixa volta a R$500 no comeco de cada um. O escore do individuo e' o
    **minimo** entre os blocos, e as metricas reportadas sao as DESSE bloco
    -- o numero que aparece e' o numero que pontuou.

    MEDIDO em 2026-09-19, e e' a razao de isto existir: na rodada de um
    bloco so', o fitness de treino correlacionou **-0,555** com o R$/op na
    janela cega, nas 10 ilhas. As duas ilhas de MAIOR fitness foram as duas
    PIORES fora da amostra. Um bloco sorteado de 18 pregoes nao mede
    estrategia, mede quanto o genoma se encaixou naquele trecho -- e
    selecionar pelo maximo de um sorteio e' selecionar ruido.

    Minimo e nao media porque a ordem do dono e' sobreviver SEMPRE: um
    individuo que prospera em dois blocos e quebra a banca no terceiro
    quebrou a banca. A media perdoaria isso; o minimo nao.

    ## As portas valem em niveis diferentes -- e isto e' conserto de bug

    MORTE vale POR BLOCO: quem quebra a banca num trecho quebrou, ponto.
    AMOSTRA vale no AGREGADO: o piso e' sobre o total de operacoes nos tres
    blocos, nao dentro de cada um.

    Ate' 2026-09-19 as duas valiam por bloco, e o efeito medido foi este --
    o campeao da ilha `vwap`, o MESMO genoma, pontuava **-54,4** com a
    particao comecando no dia 0 e **-995,0** comecando no dia 1:

        desloc=0    -8,3    +4,3   -54,4   ->  pior  -54,4
        desloc=1   +19,5  -995,0   -23,3   ->  pior -995,0

    Um dia de deslocamento derrubou um bloco de 7 para 5 operacoes, ele
    atravessou o piso de amostra, e o individuo inteiro virou sentinela --
    o mesmo escore de um genoma que nunca opera. Isso nao mede estrategia,
    mede onde a fronteira do bloco caiu. Ver `avaliacao.fitness_medido`."""
    cru, blocos, feed = carga
    if blocos and isinstance(blocos[0], str):      # compat: um bloco so'
        blocos = [blocos]
    g = Genoma(cru=cru)
    rs = [avalia(g, list(b), feed=feed) for b in blocos]

    mortos = [x for x in rs if x.morreu]
    if mortos:
        r = min(mortos, key=fitness_morte)
        fit = fitness_morte(r)
    elif sum(x.n_trades for x in rs) < min_trades(
            sum(x.pregoes_vividos for x in rs)):
        r = min(rs, key=lambda x: x.n_trades)
        fit = FITNESS_SEM_AMOSTRA + sum(x.n_trades for x in rs)
    else:
        r = min(rs, key=fitness_medido)
        fit = fitness_medido(r)
    return {
        "cru": cru, "fitness": fit, "n_blocos": len(blocos),
        # o piso de amostra e' do AGREGADO, entao o painel precisa do total
        "n_trades_total": sum(x.n_trades for x in rs),
        "pregoes_total": sum(x.pregoes_vividos for x in rs), "morreu": r.morreu,
        "pregoes_vividos": r.pregoes_vividos,
        "pregoes_oferecidos": r.pregoes_oferecidos,
        "caixa_final": r.caixa_final, "caixa_minimo": r.caixa_minimo,
        "dd_relativo": r.dd_relativo, "dd_absoluto": r.dd_absoluto,
        "folga": r.folga, "n_trades": r.n_trades, "liquido": r.liquido,
        "r_por_op": r.r_por_op, "win_pct": r.win_pct,
        "breakeven_emp": r.breakeven_emp, "r_por_pregao": r.r_por_pregao,
        "pregoes_com_op": r.pregoes_com_op, "desvio_op": r.desvio_op,
        **resumo_pontos(r),
    }


@dataclass
class EstadoIlha:
    """O que uma ilha carrega entre geracoes."""

    especie: Especie
    populacao: list[Genoma]
    rng: random.Random
    melhor: dict | None = None
    historico: list[dict] = field(default_factory=list)

    @property
    def nome(self) -> str:
        return self.especie.nome


#: Quantos candidatos sortear por vaga na triagem de atividade. 6 e' o
#: suficiente medido: cerca de 1 em 4 genomas aleatorios opera, entao 6
#: tentativas enchem quase toda vaga.
CANDIDATOS_POR_VAGA = 6


def _populacao_inicial(esp: Especie, tamanho: int, rng: random.Random
                       ) -> list[Genoma]:
    """Populacao inicial SEM triagem -- usada quando nao ha sonda disponivel.

    Ver `_triagem_de_atividade` para por que a versao com sonda existe."""
    pop = [esp.projeta(g) for g in esp.sementes][:tamanho]
    while len(pop) < tamanho:
        pop.append(esp.aleatorio(rng))
    return pop


def _triagem_de_atividade(pop: list[Genoma], atividade: list[int],
                          tamanho: int, imunes: int = 0) -> list[Genoma]:
    """Fica com os que OPERAM, completando com os mudos se faltarem.

    ## O problema que isto resolve, e ele foi medido

    A maioria dos genomas sorteados e' MUDA: numa amostra de 8 individuos por
    ilha na geracao 1, `fade` operou em 1 de 8, `retangulo` em 1 de 8 e
    `cega` em 3 de 8. Com ~75% da populacao sem operar, duas coisas ruins
    acontecem ao mesmo tempo:

      * a populacao EFETIVA e' um quarto do tamanho nominal -- paga-se o
        tempo de 30 individuos para ter a diversidade de 8;
      * dentro da faixa "sem amostra" o fitness e' `-1000 + n_operacoes`,
        entao todos os mudos empatam em -1000 e o torneio entre eles vira
        sorteio pure. A ilha sai do buraco por sorte de mutacao, nao por
        selecao -- que e' o oposto do que uma busca evolutiva deveria fazer.

    ## Por que isto NAO e' selecionar antes de selecionar

    A triagem olha UMA coisa: o individuo emitiu ordem que preencheu? Ela e'
    cega a lucro, a caixa, a acerto e a drawdown. Um genoma que opera e perde
    passa exatamente como um que opera e ganha.

    A distincao importa: filtrar por RESULTADO na janela de treino antes da
    geracao 1 seria dar ao ponto de partida uma informacao que ele deveria
    ter de conquistar, e o campeao final carregaria essa escolha sem que ela
    aparecesse em lugar nenhum. Filtrar por ATIVIDADE so' remove individuos
    que o proprio fitness ja' descartaria por falta de amostra -- adianta uma
    eliminacao inevitavel em vez de antecipar uma preferencia.

    ## As SEMENTES sao imunes -- e isto foi um bug real

    MEDIDO em 2026-09-19, rodando cada semente na sonda exata que a rodada
    longa usou: a do `retangulo` e a do `vwap` fizeram ZERO operacoes nos 6
    pregoes da sonda e foram DESCARTADAS por esta funcao, antes da geracao
    1. Essas duas ilhas rodaram 65 geracoes como 60 genomas sorteados com um
    rotulo em cima -- e o `retangulo` fez o recorde dele na geracao 1 e nunca
    mais melhorou, que e' a assinatura de busca aleatoria.

    O argumento de "adiantar uma eliminacao inevitavel" nao vale para a
    semente: o que o fitness eliminaria e' um individuo qualquer, enquanto a
    semente e' a HIPOTESE da ilha. Uma semente muda em 6 pregoes e' um dado
    sobre aqueles 6 pregoes, nao sobre a premissa -- e apaga-la faz a especie
    deixar de existir sem que nada no relatorio diga isso.
    """
    protegidos = pop[:imunes]
    resto = pop[imunes:]
    at = atividade[imunes:]
    ativos = [g for g, n in zip(resto, at) if n > 0]
    mudos = [g for g, n in zip(resto, at) if n == 0]
    return (protegidos + ativos + mudos)[:tamanho]


def _seleciona(avaliados: list[dict], rng: random.Random) -> Genoma:
    disputa = [avaliados[rng.randrange(len(avaliados))] for _ in range(TORNEIO)]
    vencedor = max(disputa, key=lambda d: d["fitness"])
    return Genoma(cru=tuple(vencedor["cru"]))


def _proxima_geracao(ilha: EstadoIlha, avaliados: list[dict], tamanho: int
                     ) -> list[Genoma]:
    rng = ilha.rng
    ordenados = sorted(avaliados, key=lambda d: d["fitness"], reverse=True)
    nova = [Genoma(cru=tuple(d["cru"])) for d in ordenados[:N_ELITE]]
    n_novos = max(1, int(tamanho * FRACAO_SANGUE_NOVO))
    while len(nova) < tamanho - n_novos:
        filho = cruzar(_seleciona(avaliados, rng), _seleciona(avaliados, rng),
                       rng)
        nova.append(ilha.especie.projeta(mutar(filho, rng)))
    while len(nova) < tamanho:
        nova.append(ilha.especie.aleatorio(rng))
    return nova


def _rotulo_cego(nome: str, c: dict) -> str:
    """Uma celula da linha CEGO no terminal. Morte e silencio tem de aparecer
    como o que sao -- um `-1000,00` cru ja' foi lido como desastre quando era
    uma ilha de caixa intacto que nao operou."""
    if c["morreu"]:
        return f"{nome[:10]} MORREU({c['pregoes_vividos']})"
    if c["n_trades"] == 0:
        return f"{nome[:10]} mudo"
    return f"{nome[:10]} {c['r_por_op']:+.2f}/op"


def _leitura_cega(campeoes: dict[str, dict], pool, feed: str) -> dict:
    """O campeao de cada ilha medido na janela de VALIDACAO, toda geracao.

    ## Por que isto existe

    Pedido do dono, 2026-09-19: *"eu passei horas achando que estava bom, pra
    no final voce me mostrar que somente rompimento tinha resultado
    positivo"*. E ele estava certo -- o painel mostrava o fitness de TREINO,
    que e' o numero que ELEGEU o individuo e por isso o mais favoravel que
    existe. Pior: na rodada de 65 geracoes esse numero correlacionou
    **-0,555** com o resultado na janela cega. Nao era so' otimista, era
    invertido. Quem olhasse o painel por nove horas estaria lendo o oposto
    do que ia acontecer.

    Custa 10 campeoes x 20 pregoes = 200 avaliacoes-pregao (~3s) por geracao,
    contra ~480s da geracao em si. E' barato demais para nao estar na tela.

    ## O que isto NAO autoriza

    A busca continua CEGA a este numero: ele nao entra no fitness, nao
    ordena a reproducao e nao escolhe nada. E' leitura. O risco que sobra e'
    humano -- parar a rodada no instante em que a janela cega ficou bonita
    seria selecionar nela pelas nossas maos, e ai' ela deixa de ser cega. O
    numero de geracoes se decide ANTES de comecar."""
    dias = pregoes("VALID")
    nomes = list(campeoes)
    cargas = [(campeoes[n]["cru"], [dias], feed) for n in nomes]
    saida = {}
    for nome, r in zip(nomes, pool.map(_avalia_worker, cargas, chunksize=1)):
        saida[nome] = {
            "banda": _banda(r), "morreu": r["morreu"],
            "n_trades": r["n_trades"], "r_por_op": r["r_por_op"],
            "liquido": r["liquido"], "caixa_final": r["caixa_final"],
            "caixa_minimo": r["caixa_minimo"],
            "dd_relativo": r["dd_relativo"], "win_pct": r["win_pct"],
            "breakeven_emp": r["breakeven_emp"],
            "pregoes_vividos": r["pregoes_vividos"],
            "pregoes_oferecidos": r["pregoes_oferecidos"],
        }
    return saida


def _banda(melhor: dict | None) -> str:
    """Em qual das tres faixas de `avaliacao._fitness` este individuo caiu.

    `"medido"` e' a unica em que o fitness e' um numero com unidade (R$ por
    pregao, ja descontados desvio, drawdown relativo e falta de folga). Nas
    outras duas ele e' um SENTINELA e nao deve ser lido como dinheiro.

    A classificacao usa os MESMOS criterios de `avaliacao._fitness` -- morte
    e piso de amostra --, nunca o valor do fitness. A versao antiga
    perguntava `fitness <= FITNESS_SEM_AMOSTRA + 1000`, ou seja
    `fitness <= 0`, e com isso qualquer individuo que simplesmente PERDEU
    dinheiro era rotulado "sem amostra". Ficou visivel quando a penalidade de
    drawdown virou quadratica e os fitness negativos passaram a ser comuns:
    um campeao com 10 operacoes na janela cega apareceu no painel como se
    nao tivesse operado. Faixa e' fato sobre o que aconteceu, nao sobre onde
    o escore caiu."""
    if not melhor:
        return "vazio"
    if melhor.get("morreu"):
        return "morto"
    # No agregado quando houve varios blocos (`n_trades_total`), no proprio
    # bloco quando foi um so'. O piso tem de ser lido no mesmo nivel em que
    # foi aplicado, senao o painel discorda do fitness.
    trades = melhor.get("n_trades_total", melhor.get("n_trades", 0))
    vividos = melhor.get("pregoes_total") or melhor.get("pregoes_vividos") or 0
    if trades < min_trades(vividos):
        return "sem_amostra"
    return "medido"


def _resumo_encaixes(g: Genoma) -> list[str]:
    """Os encaixes de um individuo em texto curto, para o painel."""
    saida = []
    for e in g.encaixes:
        nome = F.NOMES[e.idx]
        if e.porta:
            sinal = ">=" if e.b >= 0 else "<="
            saida.append(f"porta: {nome} {sinal} {e.a:+.2f}")
        elif abs(e.a) > 0.05 or abs(e.b) > 0.05:
            saida.append(f"{nome}: C{e.a:+.2f} V{e.b:+.2f}")
    return saida or ["(nenhum encaixe ativo)"]


class Progresso:
    """Escreve o estado da busca em disco a cada geracao, em dois formatos.

    O `.json` e' o bruto (para analise posterior). O `.js` existe por um
    motivo chato e pratico: uma pagina aberta por `file://` nao consegue
    fazer `fetch` de um arquivo vizinho (o navegador bloqueia por CORS), mas
    consegue carregar um `<script src=...>`. Escrever os dois e' mais barato
    que exigir um servidor de pe' so' para olhar a evolucao rodando."""

    def __init__(self, pasta: Path) -> None:
        self.pasta = pasta
        pasta.mkdir(parents=True, exist_ok=True)
        self.inicio = time.time()

    def escreve(self, payload: dict) -> None:
        payload = dict(payload, segundos=round(time.time() - self.inicio, 1))
        texto = json.dumps(payload, ensure_ascii=False)
        (self.pasta / "progresso.json").write_text(texto, encoding="utf-8")
        (self.pasta / "progresso.js").write_text(
            "window.EVO = " + texto + ";", encoding="utf-8")


def evolui(especies: list[Especie], dias_treino: list[str], *,
           tamanho_pop: int, geracoes: int, amostra: int, semente: int,
           pasta_saida: Path, max_workers: int,
           feed: str = "m1") -> dict[str, EstadoIlha]:
    """Roda todas as ilhas em passo travado. Devolve o estado final de cada
    uma, com o hall da fama em `melhor` e a serie em `historico`."""
    ilhas = {
        e.nome: EstadoIlha(
            especie=e,
            populacao=_populacao_inicial(
                e, tamanho_pop * CANDIDATOS_POR_VAGA,
                random.Random(semente + i * 1000)),
            rng=random.Random(semente + i * 1000 + 7),
        )
        for i, e in enumerate(especies)
    }
    progresso = Progresso(pasta_saida)
    amostra = min(amostra, len(dias_treino) // N_BLOCOS_FITNESS)
    if amostra < 2:
        raise SystemExit(
            f'treino de {len(dias_treino)} pregoes nao comporta '
            f'{N_BLOCOS_FITNESS} blocos disjuntos utilizaveis')

    print(f"{len(ilhas)} especies x {tamanho_pop} individuos x {geracoes} "
          f"geracoes = {len(ilhas) * tamanho_pop * geracoes} avaliacoes",
          flush=True)
    print(f"{N_BLOCOS_FITNESS} blocos DISJUNTOS de {amostra} pregoes por "
          f"geracao (de {len(dias_treino)}), escore = o PIOR deles; "
          f"{max_workers} processos", flush=True)
    print(f"caixa de partida R${CAPITAL_PARTIDA_BRL:.2f}, morte abaixo de "
          f"R${MARGEM_WDO_BRL:.2f} (margem crua)\n", flush=True)

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        # --- triagem de atividade, uma vez, antes da geracao 1 -----------
        # Sonda CURTA (os primeiros pregoes do treino) e criterio CEGO A
        # LUCRO: so' pergunta se o individuo opera. Ver `_triagem_de_
        # atividade` para por que isso nao e' selecionar antes de selecionar.
        sonda = dias_treino[:max(3, amostra // 3)]
        t0 = time.time()
        cargas, dono = [], []
        for nome, ilha in ilhas.items():
            for ind in ilha.populacao:
                cargas.append((ind.cru, [sonda], feed))
                dono.append(nome)
        triagem = list(pool.map(_avalia_worker, cargas, chunksize=4))
        por_ilha_tri: dict[str, list[int]] = {n: [] for n in ilhas}
        for nome, res in zip(dono, triagem):
            por_ilha_tri[nome].append(res["n_trades"])
        resumo_tri = []
        for nome, ilha in ilhas.items():
            atividade = por_ilha_tri[nome]
            ativos = sum(1 for n in atividade if n > 0)
            ilha.populacao = _triagem_de_atividade(
                ilha.populacao, atividade, tamanho_pop,
                imunes=len(ilha.especie.sementes))
            resumo_tri.append(f"{nome} {min(ativos, tamanho_pop)}/{tamanho_pop}")
        print(f"triagem de atividade em {len(sonda)} pregoes "
              f"({time.time() - t0:.0f}s) -- vagas preenchidas por individuo "
              f"que OPERA:", flush=True)
        print("  " + "   ".join(resumo_tri) + "\n", flush=True)

        for g in range(1, geracoes + 1):
            # UM bloco por geracao, servindo todas as ilhas -- ver a parte 1
            # da docstring do modulo. CONTIGUO, nao sorteio disperso: o caixa
            # anda de um pregao para o seguinte, entao encadear dias que na
            # realidade estavam a semanas de distancia produziria uma
            # trajetoria que nunca existiu (ver `avaliacao.py`).
            blocos = blocos_da_geracao(dias_treino, amostra, semente, g)
            dias = [d for b in blocos for d in b]

            cargas, dono = [], []
            for nome, ilha in ilhas.items():
                for ind in ilha.populacao:
                    cargas.append((ind.cru, blocos, feed))
                    dono.append(nome)

            t0 = time.time()
            resultados = list(pool.map(_avalia_worker, cargas, chunksize=1))
            dt = time.time() - t0

            por_ilha: dict[str, list[dict]] = {n: [] for n in ilhas}
            for nome, res in zip(dono, resultados):
                por_ilha[nome].append(res)

            linha_painel = []
            for nome, ilha in ilhas.items():
                avaliados = por_ilha[nome]
                melhor = max(avaliados, key=lambda d: d["fitness"])
                fits = sorted(d["fitness"] for d in avaliados)
                mediana = fits[len(fits) // 2]
                # O hall da fama guarda o melhor JA VISTO, mas o numero dele
                # veio de uma amostra especifica -- por isso ele carrega a
                # geracao em que foi medido. Comparar dois campeoes de
                # geracoes diferentes sem isso e' comparar dois sorteios.
                if (ilha.melhor is None
                        or melhor["fitness"] > ilha.melhor["fitness"]):
                    ilha.melhor = dict(melhor, geracao=g, dias=list(dias))
                # O que o painel precisa para responder "ela esta'
                # APRENDENDO?", que nao e' a mesma pergunta que "quanto ela
                # ganhou". O campeao sozinho e' o MAXIMO da populacao e sobe
                # por sorte; quem mostra aprendizado e' a populacao inteira
                # mudando de faixa ao longo das geracoes.
                bandas = {"morto": 0, "sem_amostra": 0, "medido": 0}
                for dd_ in avaliados:
                    bandas[_banda(dd_)] = bandas.get(_banda(dd_), 0) + 1
                vivos = len(avaliados) - bandas["morto"]
                ilha.historico.append({
                    "geracao": g,
                    "melhor": melhor["fitness"],
                    "mediana": mediana,
                    "vivos": len(avaliados) - bandas["morto"],
                    "pop": len(avaliados),
                    "morto": bandas["morto"],
                    "sem_amostra": bandas["sem_amostra"],
                    "medido": bandas["medido"],
                    "r_por_op": melhor["r_por_op"],
                    "n_trades": melhor["n_trades"],
                    "win_pct": melhor["win_pct"],
                    "caixa_final": melhor["caixa_final"],
                })
                ilha.populacao = _proxima_geracao(ilha, avaliados, tamanho_pop)
                linha_painel.append(
                    f"{nome[:10]:<10}{melhor['fitness']:>+8.2f} "
                    f"({vivos:>2}/{len(avaliados)} vivos)")

            # A leitura CEGA do campeao de cada ilha -- ~3s contra ~480s da
            # geracao. E' o unico numero da tela que nao foi escolhido por
            # si mesmo. Ver `_leitura_cega`.
            cego = _leitura_cega(
                {n: max(por_ilha[n], key=lambda d: d["fitness"])
                 for n in ilhas}, pool, feed)
            for nome, ilha in ilhas.items():
                c = cego[nome]
                ilha.historico[-1].update({
                    "cego_r_por_op": c["r_por_op"],
                    "cego_caixa": c["caixa_final"],
                    "cego_morreu": c["morreu"],
                    "cego_n_trades": c["n_trades"],
                    "cego_win_pct": c["win_pct"],
                    "cego_breakeven": c["breakeven_emp"],
                    "cego_dd": c["dd_relativo"],
                })

            print(f"[g{g:>3}/{geracoes}] {dt:>5.1f}s  " + "  ".join(linha_painel),
                  flush=True)
            print("           CEGO: " + "  ".join(
                _rotulo_cego(n, cego[n]) for n in ilhas), flush=True)

            progresso.escreve({
                "geracao": g, "geracoes": geracoes,
                "tamanho_pop": tamanho_pop, "amostra": amostra,
                "n_pregoes_treino": len(dias_treino),
                "janela": [dias[0], dias[-1]] if dias else [],
                "capital": CAPITAL_PARTIDA_BRL, "margem": MARGEM_WDO_BRL,
                "segundos_geracao": round(dt, 1),
                "ilhas": [
                    {
                        "nome": nome,
                        "premissa": ilha.especie.premissa,
                        "historico": ilha.historico,
                        # O numero que DECIDE. Fica no payload ao lado do de
                        # treino de proposito: quem olha o painel tem de ver
                        # os dois juntos e notar quando discordam -- foi a
                        # discordancia (r = -0,555) que passou despercebida
                        # por nove horas em 2026-09-18.
                        "cego": cego[nome],
                        "janela_cega": [pregoes("VALID")[0],
                                        pregoes("VALID")[-1]],
                        "melhor": {
                            # O `cru` VIAJA. Em 2026-09-19 o processo da
                            # rodada longa travou antes de escrever o
                            # `finalistas.json`, e como o payload do painel
                            # removia o genoma "para nao carregar peso
                            # morto", os 10 campeoes de 9h de maquina
                            # existiam apenas na memoria do processo travado.
                            # 33 floats por ilha por geracao nao sao peso; a
                            # unica coisa insubstituivel da rodada e'.
                            **{k: v for k, v in (ilha.melhor or {}).items()
                               if k != "dias"},
                            # A FAIXA viaja junto do numero porque o numero
                            # sozinho engana: -1000 nao e' "perdeu mil reais
                            # por pregao", e' o sentinela de "nao operou o
                            # bastante para ser julgado". O painel mostrou
                            # "-997,00 R$/preg" para uma ilha cujo caixa
                            # estava intacto, e a leitura natural foi de
                            # desastre onde havia silencio.
                            "banda": _banda(ilha.melhor),
                            "encaixes": _resumo_encaixes(
                                Genoma(cru=tuple(ilha.melhor["cru"])))
                            if ilha.melhor else [],
                            "geometria": (
                                Genoma(cru=tuple(ilha.melhor["cru"])).geometria
                                if ilha.melhor else {}),
                        },
                    }
                    for nome, ilha in ilhas.items()
                ],
            })

    return ilhas
