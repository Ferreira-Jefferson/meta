# Fade do retest de rompimento -- a aposta em REENTRADA (2026-09-16)

Território: a aposta OPOSTA à já testada em `executabilidade.md` (que apostava
em CONTINUAÇÃO). Aqui a aposta é que o preço REENTRA no retângulo depois de
romper -- o desfecho majoritário medido em `anatomia.md` (83% dos que
retestam). Script: `scripts/daytrade/rompimento_fade_retest_2026_09_16.py`
(+ `.log`). Motor de produção completo (`config_for` + `run_intraday_backtest`
+ `backtest/intraday/report.py`), não simulação de preço isolada.

## Decisão 1 -- a forma literal do pedido é INEXECUTÁVEL, e isso decide tudo o resto

Pedido original: "rompimento de ALTA -> limite de VENDA na borda de CIMA,
apostando que o preço volta a entrar". Testado mecanicamente (a mesma
conferência que `WinRetangulo` já faz: venda só é válida se `limite > close`;
compra só se `limite < close`):

No instante em que o rompimento é CONFIRMADO, o preço já está, por
construção da própria definição de rompimento, além da borda (fechamento >
topo + 25%×largura). Uma venda-limite NA borda nesse instante teria
`limite(topo) < close` -- do lado ERRADO para uma venda-limite (que só
descansa ACIMA do preço corrente). **A checagem falharia 100% das vezes, não
"quase sempre vale" como a formulação original supunha** -- não é resultado
empírico, é necessidade matemática (o rompimento só é confirmado quando o
preço já cruzou para o lado que invalida a ordem de fade nesse ponto). É
exatamente a Forma B já catalogada em `executabilidade.md` ("perseguir
exige... uma ordem STOP, ausente do motor") -- só que do lado da REVERSÃO,
não da continuação.

**Adaptação executável adotada:** armar a ordem só DEPOIS que o FECHAMENTO já
confirma a reentrada (`close < topo` para alta). Nesse instante o topo passa
para o lado ACIMA do fechamento, e a venda-limite se torna mecanicamente
válida -- apostando que o preço volte a testar a borda por dentro e falhe em
romper de novo. Medido: a checagem mecânica NESTE instante falha só 6 de 170
tentativas (3,5%, por arredondamento de tick) -- "quase sempre vale" bate
exatamente aqui, não no instante da confirmação.

**Consequência declarada:** esta variante não captura a reentrada inteira --
começa a contar só de onde o fechamento já está do lado de dentro. É uma
fatia mais tardia e mais conservadora dos mesmos 83%, não a coisa inteira.

## Bug de método encontrado e corrigido nesta rodada

Primeira passada: `self._rompido` não era limpo quando a ordem armada
PREENCHIA e virava posição. Como a condição de reentrada (`close < borda`)
continua verdadeira depois que o preço já está dentro do retângulo, o robô
re-armava OUTRA entrada para o MESMO evento de rompimento toda vez que o
preço voltava a tocar a borda -- `armadas` saía 2-3x maior que `rompimentos
confirmados` (350 armadas para 172 rompimentos, deveria ser <= rompimentos).
Fix: ao detectar `positions` não-vazio (ordem preencheu), zera `_rompido`
imediatamente -- o evento está CONSUMIDO, e o robô volta a caçar um
retângulo NOVO do zero quando a posição fechar. Depois do fix,
`armadas + nunca_reentra == rompimentos` exatamente, em toda variante --
conferência de consistência que validou o fix.

Efeito do bug na leitura teria sido enganoso: com o bug, o líquido de TODAS
as variantes saía fortemente negativo (a repetição de entradas no mesmo
nível já "gasto" é uma estratégia diferente, pior); depois do fix, as
variantes com alvo=OPOSTA viraram positivas (embora dentro do ruído, ver
Decisão 4).

## Decisão 2 -- STOP: extremo do rompimento + k×largura, k testado em {0,00 ; 0,15 ; 0,30}

Testado como pedido: o stop fica ALÉM do high/low mais distante atingido
entre a detecção e a confirmação da reentrada. k maior sempre reduz o
"pior op." em módulo (mais folga) mas não muda o sinal do resultado --
dentro da faixa testada o eixo do stop não separa vencedor de perdedor,
parecido com o achado histórico do `win_retangulo` ("o stop é ruído dentro
do platô"). k=0,30 teve o melhor lucro/DD entre os três, mas a diferença
para k=0,00/0,15 é pequena perto do ruído de amostra (n~150-165 em cada).

## Decisão 3 -- ALVO: meio (conservador) vs borda oposta -- ESTA É A QUE DECIDE

Resultado limpo e consistente nas 6 combinações de cada lado:

- **alvo=MEIO**: win% ALTO (66-74%) mas líquido SEMPRE negativo
  (-R$470 a -R$1.052 no IS) -- o mesmo padrão já registrado no histórico do
  `win_retangulo` ("o alvo tinha de ser MAIOR, não menor"): um alvo perto
  paga pouco por vitória e o stop distante (extremo do rompimento, tipicamente
  bem além da largura) cobra caro na cauda perdedora. Métrica que confirma:
  BE empírico sobe para 70-74% -- ACIMA do próprio win% nominal na maioria
  das linhas, ou seja, o payoff realizado é pior que o nominal.
- **alvo=OPOSTA**: win% menor (52-60%) mas líquido positivo em 3 das 6
  células (as de k=0,15 e k=0,30, ttl 20 e 60) -- R$190 a R$535 no IS.

**A largura do alvo é o eixo que decide, não o stop.** Alvo maior (oposta)
transforma um desenho claramente perdedor em um desenho perto de zero -- o
MESMO padrão do `win_retangulo`, replicado aqui num robô diferente e numa
direção oposta de aposta.

## Decisão 4 -- nenhuma configuração escapa do IC95% do breakeven

As 6 células de alvo=OPOSTA (as únicas com líquido positivo em pelo menos
metade delas) têm win% de 51,9% a 60,1%, sempre com o breakeven empírico
DENTRO do IC95% (ex.: melhor célula, k=0,30/ttl60: win 60,1%, BE emp. 58,5%,
IC95 [52,4% ; 67,9%] -- o BE cai bem no meio do intervalo, não na borda).
**Nenhuma das 12 variantes é distinguível de cara-ou-coroa.** Mesmo
resultado qualitativo do agente irmão que testou continuação
(`executabilidade.md`): também 0/5 geometrias escaparam do IC95%. As duas
apostas nesta população de rompimentos -- continuação E reentrada -- ficam
dentro do ruído.

## Decisão 5 -- TTL testado em {20, 60} minutos: não muda o veredito

ttl=60 é consistentemente um pouco melhor que ttl=20 nas células de
alvo=OPOSTA (mais tempo para a ordem preencher = mais trades, líquido maior
em módulo nos dois sinais), mas a diferença não muda o sinal de nenhuma
célula nem tira nenhuma do IC95%. Prazo não é o eixo que decide.

## A economia completa (três pernas), variante-referência k=0,30/oposta/ttl60

- **211 rompimentos confirmados** (nesta variante; a contagem oscila
  211-232 entre as 12 células -- ver limitação de cobertura abaixo).
- **(a) nunca reentra por fechamento: 47 (22,3%)** -- a ordem nunca chega a
  ser armada. Não é perda: é ausência de operação.
- **(b)+(c) reentra e ordem é armada: 164 (77,7%)**.
  - checagem mecânica falha em 6 dessas 170 tentativas (3,5%, arredondamento
    de tick) -- não vira ordem.
  - **(b) armada mas expira sem preencher: 11 (6,7% das armadas)** -- o
    preço não voltou a tocar a borda a tempo depois de reentrar. Oportunidade
    perdida, não perda de dinheiro.
  - **(c) preenche e vira trade: 153 (93,3% das armadas)** -- destes,
    60,1% vencedores (mediana de payoff assimétrica: perdas maiores que
    ganhos, dado BE empírico 58,5% > breakeven nominal do par 0,3L-stop/
    largura-até-oposta-alvo).

## Piso de capital -- MAIOR que o do win_retangulo, e isto é o número real, não redondo

Rebaixamento por operação medido (pico-a-vale da curva ao nível de operação,
mesmo conceito que fixou o R$1.100 do `win_retangulo`), variante k=0,30/
oposta: **R$1.530,70 (ttl60) a R$1.554,70 (ttl20)**. Piso real = rebaixamento
+ margem crua R$100: **R$1.630,70 a R$1.654,70** -- cerca de 1,5× o piso do
`win_retangulo` (R$1.100). Com capital de partida de R$1.100 (o de
referência desta rodada), o MaxDD chega a 54,6%-98,9% do caixa conforme a
variante -- em uma variante da PRIMEIRA passada (antes do fix do bug), a
conta chegou a ZERAR. Não adote R$1.100 para esta linha: é o piso de outra
estratégia, medido noutra geometria.

## Limitação declarada -- cobertura de população

O robô rastreia UM rompimento por vez (mesmo desenho do `WinRetangulo`):
enquanto espera a reentrada de um rompimento, ignora qualquer OUTRO
retângulo que se forme ou rompa em paralelo. Isso reduz a população
observada para 211-232 rompimentos por variante, contra os 417 medidos na
população completa do IS (`rompimento_retangulo_fenomeno_2026_09_16.py`) --
cobertura de ~51-56%. Não invalida o veredito de "sem edge que escape do
ruído" (o n disponível, 150-165 trades por célula, já é grande o bastante
para que o IC95% feche em torno de ±7-9pp, e o breakeven cai sempre dentro
dele) -- mas significa que rastrear MÚLTIPLOS rompimentos em paralelo é uma
mudança de desenho, não de parâmetro, e ficaria para quem quisesse
continuar esta linha.

## Veredito final

**Não há evidência de edge que escape do ruído em nenhuma das 12
variantes testadas.** alvo=MEIO é claramente ruim (payoff pobre, sempre
negativo). alvo=OPOSTA chega perto de zero e ocasionalmente positivo, mas o
win% cai sempre dentro do IC95% do breakeven empírico -- estatisticamente
indistinguível de cara-ou-coroa, na mesma linha do que já se mediu para a
aposta de continuação. Regra do dono ("se não for evidente uma melhora não
tem para que mudar") aplica-se por completo: NÃO perseguir esta linha com
mais varredura de parâmetro dentro do mesmo desenho -- stop e ttl já
mostraram ser eixos sem estrutura; o único eixo que mexeu alguma coisa foi o
tamanho do alvo, e mesmo no seu extremo testado (borda oposta) não escapou
do ruído.

## Próxima pergunta, se alguém quiser continuar esta linha

1. Rastrear MÚLTIPLOS rompimentos em paralelo (remove a limitação de
   cobertura de 51-56%) -- mudança de desenho do state machine, não de
   parâmetro.
2. Alvo AINDA maior que a borda oposta (ex.: oposta + fração adicional,
   como o `win_retangulo` faz com `alvo_fracao_largura=0,80` além do meio)
   -- o eixo do alvo foi o único que mexeu algo aqui; vale ver se ele
   continua melhorando além da borda oposta ou se já satura nela.
3. Medir se HÁ alguma característica do rompimento (largura, velocidade do
   afastamento, hora do dia) que separe os 22,3% que nunca reentram dos
   77,7% que reentram -- não medido nesta rodada (a `caracteristicas.md` já
   mostrou 0/25 características prevendo o desfecho do ROMPIMENTO em si, mas
   não testou especificamente a pergunta "reentra ou não", que é uma
   classificação binária diferente do outcome contínuo MFE-MAE usado lá).
