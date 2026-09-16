# Reviver o `win_retangulo` com rompimento+reentrada -- WIN@, IS (129 pregoes, < 2026-06-13)

Territorio: NAO e' o fade na borda (ja testado e refutado em `fade_do_retest.md`,
0/12 geometrias escapam do IC95%). Aqui o retangulo MORTO e' revivido e a
entrada volta a ser a de sempre -- no MEIO, geometria exata de producao
(`alvo_fracao_largura=0,80`, `stop_fracao_largura=0,50`, `ttl_barras=10`).
Pedido textual do dono: "usamos este conhecimento de que volta e entra
novamente no retangulo para testar e talvez ate usar isso como novos pontos
de entrada da propria estrategia win_retangulo". Script:
`scripts/daytrade/win_retangulo_revivencia_rompimento_2026_09_16.py` (+ `.log`).

## Decisao 0 -- o baseline "conhecido" (R$3.720,70) esta desatualizado, e isso quase parou a rodada

O PASSO 0 do script confere o baseline contra o numero documentado no proprio
docstring de `win_retangulo.py` (615 trades, R$3.720,70 no IS). Medido agora
com o robo de producao SEM NENHUMA modificacao
(`strategy.daytrade.registry.get_daytrade_robot("win_retangulo")`): **615
trades (bate exato) mas R$3.536,60 (diverge R$184,10, ~4,9%)**.

Diagnostico automatico do proprio script: rodar de novo com
`escala_por_caixa=False` reproduz **R$3.720,70 exato, 615 trades** -- prova
que a causa e' a escalada de contrato por caixa (commits `4806636`/`ca252a7`,
2026-09-15 21:40, POSTERIORES a quando o docstring foi escrito), que
ocasionalmente libera um 2º contrato mais tarde na janela IS (uma vez que o
caixa ultrapassa R$2.933) -- e nesta amostra a escalada PIORA o resultado
(uma operacao maior num trecho ruim pesa mais do que ajuda nos trechos bons).
**Nao e' bug**: e' o robo de producao de HOJE, com o parametro default real
(`escala_por_caixa=True`), divergindo de um numero que ficou desatualizado no
proprio arquivo fonte. Esta rodada usa **R$3.536,60 / 615 trades** como
baseline de referencia dai em diante -- e' o que o registry de fato
instancia.

**Achado colateral que nao e' desta rodada mas precisa ser dito**: o piso de
capital documentado do `win_retangulo` (`PISO_UM_CONTRATO_BRL = R$1.100`,
calculado a partir de R$989,50 de rebaixamento por operacao) tambem foi
medido ANTES da escalada por caixa. Rodando o baseline puro atual (escala
ligada, capital de partida R$1.100) o rebaixamento por operacao sai em
**R$1.979,00** -- quase o DOBRO do que sustenta o piso publicado. Ver a nota
no fim deste documento; nao e' escopo desta tarefa (revivencia), mas e' dado
que custa dinheiro real se ignorado.

## Decisao 1 -- desenho da revivencia

Subclasse `WinRetanguloRevivencia(WinRetangulo)`
(`scripts/daytrade/win_retangulo_revivencia_rompimento_2026_09_16.py`, nao
entra em `src/`). Quando o retangulo normal morre (mesma regra de producao,
`MARGEM_MORTE=0,25`, `BARRAS_MORTE=3`), em vez de descartar pra sempre, guarda
`{topo, piso, meio, largura, lado}` por uma janela de `janela_revivencia_barras`
barras. Na reentrada confirmada por FECHAMENTO (`close < topo` se rompeu
alta, `close > piso` se rompeu baixa -- a MESMA definicao de "entra" que
`anatomia.md` e `fade_do_retest.md` ja usam), arma `EnterLimit` no MEIO do
retangulo revivido com a geometria EXATA de producao. Confere o lado
mecanicamente antes de aceitar (mesma checagem de `WinRetangulo._entrada`).

Duas janelas medidas: **20 e 60 barras** (coerente com os horizontes ja
usados em `anatomia.md`/`fade_do_retest.md`). Duas politicas de consumo:
**unica** (arma uma vez e descarta o morto, nao tenta reviver o MESMO evento
de novo) e **multipla** (mantem o morto vivo ate a janela expirar, podendo
armar varias vezes o mesmo evento). 4 combinacoes.

A subclasse tambem ROTULA (sem mudar nenhuma decisao) as entradas NORMAIS com
um rastreador independente de rompimento+reentrada (`_HistoricoRompimentos`,
mesmos `detecta_retangulo`/`MARGEM_MORTE`/`BARRAS_MORTE` de producao) para a
Hipotese B. Confirmado: com `revivencia_ativa=False` a subclasse e'
BYTE-IDENTICA ao `WinRetangulo` puro (615 trades, R$3.536,60 nos dois) --
o rotulo nao interfere na decisao.

## Hipotese A -- REJEITADA, consistente nas 4 variantes

Economia ISOLADA das operacoes de revivencia (nao o agregado):

| variante | n reviv. | R$ total | R$/op | win% | BEemp | IC95% |
|---|---:|---:|---:|---:|---:|---|
| j=20 unica | 78 | -761,60 | -9,76 | 37,2% | 42,9% | [27,3% ; 48,3%] |
| j=60 unica | 101 | -1.073,20 | -10,63 | 36,6% | 43,5% | [27,9% ; 46,4%] |
| j=20 multipla | 141 | -1.282,10 | -9,09 | 36,2% | 42,1% | [28,7% ; 44,4%] |
| j=60 multipla | 260 | -1.432,50 | -5,51 | 38,5% | 42,3% | [32,8% ; 44,5%] |

**As 4 variantes, sem excecao, tem R$/op NEGATIVO e win% abaixo do
breakeven empirico.** Nao e' ruido disperso em torno de zero -- e' negativo
nas 4 combinacoes de janela (20/60) e politica (unica/multipla), com n
crescente de 78 a 260 (o maior n, j=60 multipla, e' tambem o mais proximo do
zero mas continua negativo). O IC95% do win% inclui o breakeven em todas
(amostra nao e' grande o bastante pra cravar estatisticamente), mas a
CONSISTENCIA de sinal nas 4 variantes independentes e' o que decide aqui --
nao existe uma unica configuracao onde a revivencia isolada pague.

**Efeito no AGREGADO tambem e' negativo nas 4 variantes** -- o liquido total
cai em toda combinacao (baseline R$3.536,60 -> R$3.398,30 / R$2.027,20 /
R$3.122,30 / R$2.946,90), apesar do numero de trades SUBIR (615 -> 656 a
812). Isso acontece por DOIS motivos, os dois medidos:

1. As proprias operacoes de revivencia perdem dinheiro (tabela acima).
2. A revivencia RECEBE OPORTUNIDADE que seria da entrada NORMAL, e o
   contrario tambem acontece -- o motor NAO piramida, entao so' uma ordem
   pode estar pendente por vez. Comparando trades totais: j=20 unica tem 656
   trades (615 normais - ~37 canibalizados + 78 de revivencia); o numero
   LIQUIDO de trades normais efetivamente caiu quando a revivencia estava
   ligada, porque o slot de ordem pendente as vezes ficava ocupado por uma
   entrada revivida bem na hora em que um retangulo novo teria armado.

**O motor NAO piramidar tambem bloqueia a PROPRIA revivencia, com forca
crescente na variante multipla**: "oportunidade perdida" (reentrada
confirmada mas posicao/ordem ja ocupava o slot) foi 33-119 vezes nas
variantes UNICA, mas **2.416 (posicao aberta) + 2.589 (ordem pendente) =
5.005 vezes** na variante j=60 multipla -- a politica multipla gera MUITO
mais tentativas de revivencia do que o motor consegue de fato executar, e a
maioria delas nunca chega a virar ordem.

**Piso de capital piora em todas as 4 variantes**, nunca melhora:

| variante | rebaixamento/op | piso real (rebaix.+R$100) |
|---|---:|---:|
| baseline (rev. OFF) | R$1.979,00 | R$2.079,00 |
| j=20 unica | R$2.068,00 | R$2.168,00 |
| j=60 unica | R$2.212,70 | R$2.312,70 |
| j=20 multipla | R$2.283,50 | R$2.383,50 |
| **j=60 multipla** | **R$2.311,10** | **R$2.411,10** |

**Veredito A: NAO perseguir.** Perde dinheiro isolada (4/4 variantes),
piora o agregado (4/4), piora o piso de capital (4/4), e a versao mais
agressiva (multipla) desperdica a maior parte das tentativas contra o
proprio motor nao-piramidar. Regra do dono aplicada: efeito grande em
numero de operacoes (78 a 260) mas na direcao ERRADA em toda variante --
nao e' "efeito nao evidente", e' evidencia clara de que a linha NAO paga.

## Hipotese B -- sem evidencia de melhora, e o sinal (fraco) aponta pro lado contrario

Entradas NORMAIS da variante instrumentada (615 trades, identica ao
baseline), separadas por "houve rompimento+reentrada de OUTRO retangulo nas
3xW barras antes da deteccao":

| grupo | n | liquido | R$/op | win% | BEemp | IC95% |
|---|---:|---:|---:|---:|---:|---|
| COM rompimento antes | 141 | R$600,50 | R$4,26 | 41,1% | 38,7% | [33,4% ; 49,4%] |
| SEM rompimento antes | 474 | R$2.936,10 | R$6,19 | 46,0% | 42,0% | [41,6% ; 50,5%] |

Os dois grupos tem o proprio breakeven empirico DENTRO do IC95% (nenhum dos
dois e' distinguivel de jogo justo isoladamente). Comparando os dois: o
grupo "COM rompimento" tem R$/op e win% **menores** que "SEM rompimento" --
o OPOSTO da hipotese testada ("sobrevivente de rompimento e' melhor"). Os
dois intervalos de confianca se sobrepoem fortemente ([33,4;49,4] x
[41,6;50,5]), entao a diferenca NAO e' estatisticamente distinguivel de
ruido -- mas nao ha' NENHUM sinal, nem fraco, na direcao que a hipotese
previa.

**Aviso de tamanho de amostra**: n=141 para o grupo "COM rompimento" e' o
grupo MENOR dos dois (615 trades totais divididos numa proporcao ~23%/77%) --
suficiente para um IC95% de ~±8pp, nao suficiente para separar dois grupos
cuja diferenca de win% e' de so' 4,9pp.

**Veredito B: sem evidencia de melhora.** Nao ha' justificativa para
condicionar a entrada normal do `win_retangulo` a um historico de rompimento
sobrevivido -- na melhor leitura e' inerte, na leitura literal do ponto
central e' levemente contra.

## Veredito final desta rodada

**Nenhuma das duas hipoteses sustenta mudanca em producao.** A Hipotese A
(entrada extra por revivencia) tem sinal negativo CONSISTENTE (4/4
variantes, isolado e agregado, com n de 78 a 260 operacoes) -- nao e' "fraco
demais para decidir", e' "decidido, e decidido contra". A Hipotese B (filtro
de qualidade) nao mostra edge em nenhuma direcao, com uma leve tendencia
(nao significativa) na direcao OPOSTA a hipotese.

Regra do dono aplicada sem meio-termo: **abandonar as duas linhas**. Nao
perseguir mais parametro dentro deste desenho (janela de revivencia, politica
de consumo) -- os 4 pontos testados na Hipotese A ja cobrem o espaco
razoavel (20/60 barras x unica/multipla) e todos concordam no sinal.

## O que NAO foi medido aqui (agenda, se alguem quiser continuar)

1. Rastrear MULTIPLOS retangulos mortos em paralelo (aqui so' o ULTIMO e'
   guardado) -- mudanca de desenho, nao de parametro; dado o veredito
   negativo da Hipotese A, nao ha' motivo para perseguir isto agora.
2. Geometria DIFERENTE para a revivencia (alvo/stop proprios, nao herdados
   de producao) -- fora do pedido original ("a propria estrategia
   win_retangulo" implicava a MESMA geometria); poderia ser proximo passo se
   alguem quiser reabrir a linha, mas o sinal negativo desta rodada nao
   sugere que valha a pena.
3. O achado colateral do piso de capital desatualizado (Decisao 0) merece
   remedicao/atualizacao do `capital_minimo_recomendado_brl` do
   `WinRetangulo` -- fora do escopo desta tarefa, reportado separadamente.

## OOS

**Nao consultado.** So' o IS foi usado nesta rodada, e o veredito (abandonar)
nao precisa dele -- ir ao OOS para confirmar uma linha ja' rejeitada no IS
gastaria o teste cego sem necessidade. Decisao do dono, nao desta rodada.
