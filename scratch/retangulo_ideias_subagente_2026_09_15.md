# Retângulo WIN@ — 8 desenhos novos (não implementados, não medidos)

Li `CLAUDE.md` e `AGENTS.md` antes de escrever isto. As restrições que governam
todo desenho abaixo, sem exceção:

- **Entrada só por `EnterLimit` com `ttl_bars`.** Ordem-stop (dispara a
  mercado quando o preço bate um nível) está banida — é ordem a mercado
  disfarçada, e o motor recusa `Enter` a mercado de propósito
  (`EntradaAMercadoNaoSuportada`). Verificação mecânica obrigatória em cada
  desenho abaixo: **uma venda-limite só descansa ACIMA do preço atual; uma
  compra-limite, ABAIXO.** Um desenho que pede "vender quando voltar para
  baixo até X" é ordem-stop e está fora.
- **Alvo só por ordem-limite real.** `tp` nativo é varrido a mercado — banido.
- **O stop é a ÚNICA exceção**: sempre a mercado.
- **Custo do WIN é irrelevante para a decisão de alvo**: round trip = 7,5
  pontos = R$1,50/contrato (tick 5 pontos, R$0,20/ponto). Toda largura de
  retângulo medida (297 a 406 pontos) paga isso com folga enorme — o
  problema destes desenhos nunca é custo, é DIREÇÃO (50/50, medido) e FILA
  (não calibrada para WIN@).
- **WIN@ não tem `fidelidade.py`.** Qualquer desenho que precise de uma
  ordem-limite encher num nível já tocado várias vezes está assumindo
  preenchimento no primeiro toque — a mesma suposição que, calibrada para o
  WDO@, virou 438/489 barras de fila e inverteu o sinal do resultado do
  WDO F1 maker. Marco isso em cada desenho que depende disso.
- **Capital**: R$3.000 partindo, margem WIN R$100/contrato — o portão de
  capital não é a restrição ativa em nenhum destes desenhos (mesmo com
  buffer 2,0× o mínimo de partida fica em ~R$200-250); a restrição ativa é
  sempre execução e amostra.

Os desenhos do dono (D1 — entrada no centro, D2 — falso rompimento) já vão
ser implementados por outro agente e não são repetidos aqui.

---

## 1. Retest da borda rompida — comprar/vender a FAVOR da quebra já resolvida

**Mecanismo.** Quando o retângulo morre por rompimento (critério TOLERANTE:
3 fechamentos seguidos além de 25% da largura), a borda que acabou de ser
rompida vira nível de referência natural para um retorno (retest). Em vez de
apostar QUAL lado vai romper — a pergunta que o dado mostra ser 50/50 — este
desenho só age DEPOIS que a moeda já caiu: espera o rompimento confirmado e
posiciona a favor da continuação, no retest da borda velha.

**Fato medido que sustenta.** A quebra é essencialmente simétrica e sem edge
de continuação de tendência anterior (678 cima / 733 baixo no IS, 48,1%
cima; item "continuação ≈ 50%", 3 de 56 células fora do nulo contra 2,8
esperadas por acaso) — ou seja, não vale prever o lado. Mas UMA VEZ que o
rompimento acontece, ele é factual, não uma previsão: 91-98% dos retângulos
(critério estrito) e 78-92% (tolerante) efetivamente rompem antes do fim do
pregão. A largura mediana (297-406 pontos) dá espaço de sobra para o retest
+ continuação pagar os 7,5 pontos de custo.

**Gatilho, entrada, alvo, stop.**
- Gatilho: retângulo confirmado morre por rompimento (tol_direcao = cima/baixo).
- Entrada: se rompeu para CIMA, `EnterLimit` de COMPRA na borda de TOPO
  antiga (agora abaixo do preço corrente — compra-limite descansa
  corretamente abaixo do mercado). Simétrico para baixo com venda-limite na
  borda de PISO antiga (acima do mercado). `ttl_bars` obrigatório — sem
  prazo a ordem fica esquecida até o fim do pregão (medido: 269,7 min de
  atraso em outro contexto). Sugestão de partida: prazo equivalente a ~15-20
  minutos calibrados em barras reais do dia (não em barras nominais — a base
  varia de 190 a 586 barras/minuto conforme regime).
- Alvo: ordem-limite real, projeção de continuação — ex. mais uma fração da
  largura do próprio retângulo (a favor da direção do rompimento) além do
  nível de entrada. Paga os 7,5 pontos com folga trivial dado o tamanho.
- Stop: a mercado (única exceção), abaixo/acima do extremo do retest por uma
  margem calibrada pela tabela de ruído de borda (mediana de desvio 10-21
  pontos, p90 até 131-165 pontos) — mas ATENÇÃO: essa tabela mede ruído
  ANTES do rompimento (toques dentro do retângulo vivo); ruído de um retest
  PÓS-morte é outra distribuição, não medida aqui.

**Oportunidades por pregão.** Só de W=30, ~92,2% dos ~5,24 retângulos/dia
rompem (≈4,8 rompimentos/dia); somando os cinco W's (com sobreposição, não
independentes) o número de EVENTOS de rompimento por dia é generoso. O que
NÃO está medido é **que fração desses rompimentos produz um retest
executável** — se for, por exemplo, 20%, ainda sobra ~1/dia, dá para validar
em 191 pregões; se for <5%, o desenho não tem amostra. Este é o primeiro
número que quem implementar precisa medir antes de gastar tempo em geometria
fina.

**O que o refuta (declarado antes de medir).** Win% do retest, contra o
breakeven implícito do R:R escolhido, não pode ficar acima do breakeven só
no IS — tem que ficar acima nas DUAS janelas. Se a frequência de retest for
tão baixa que a amostra IS ou OOS fique abaixo de ~30 eventos, o desenho é
inconclusivo por tamanho de amostra, não decidido.

**O que já contradiz.** Nada diretamente — mas a concordância M1/M5/M15
(seção 8 abaixo, desenho descartado (c)) **não pode** ser usada para
pré-filtrar a confiança do retest: o efeito de concordância já inverte de
sinal entre IS (44,6% a favor quando 3-de-3 alinhados) e OOS (55,3%).

---

## 2. Veto estrutural do robô hospedeiro (CopaWin) dentro do retângulo confirmado — filtro de AUSÊNCIA

**Mecanismo.** Enquanto existe um retângulo confirmado (qualquer W, ou uma
combinação deles) ainda vivo, suspende a entrada de um robô direcional (ex.
CopaWin) no mesmo instrumento: não manda ordem nova, deixa o estado do robô
intacto para retomar quando o retângulo morrer. Não é um trade novo — é o
uso "filtro de contexto para outra coisa" sugerido no pedido.

**Fato medido que sustenta.** Dentro de um retângulo confirmado, ≥95% dos
fechamentos ficam contidos entre as bordas por construção (critério de
contenção do próprio detector) e a quebra subsequente não favorece nenhuma
direção (continuação ≈ 50%, ver desenho 1). Uma estratégia direcional que
entra durante essa contenção está, por definição estrutural, apostando numa
faixa sem edge de direção conhecida.

**Gatilho, entrada, alvo, stop.** Gatilho: retângulo confirmado ativo (do
instante da confirmação até a morte, critério tolerante). Entrada: NENHUMA —
é veto puro. Alvo/stop: os do robô hospedeiro, inalterados nas entradas que
passam pelo filtro.

**Oportunidades por pregão (aqui, "cobertura do veto").** Usando só W=30
(5,24 retângulos/dia, vida tolerante mediana ~20 min cada) dá ~105 min/dia
de estado "ligado" — cerca de 30% de uma sessão de ~330 min. Somando as
outras janelas simultaneamente (do jeito que D1 já propõe operar vários W ao
mesmo tempo) a cobertura tende a ser maior, com alguma sobreposição entre
janelas que precisa ser deduplicada por quem medir. Suficiente para gerar
um número respeitável de entradas vetadas em 191 pregões, desde que o robô
hospedeiro opere com frequência comparável.

**O que o refuta.** Se o P&L médio das entradas do robô hospedeiro que
CAEM dentro do estado "retângulo ativo" não for pior do que o P&L das que
caem fora dele — nas duas janelas — o veto não tem o que vetar. Mede-se
exatamente como o script `wdo_orb_veto_lateralizacao_2026_09_15.py` já faz
para outra hipótese: contrafactual pareado por (data, hora do sinal), nunca
por posição no dia.

**O que já contradiz / com o que não confundir.** O repo já tem uma tentativa
PARALELA e DIFERENTE de "não operar em lateralização": o filtro por razão de
eficiência (ER) do `copawin_lateralizacao_2026_09_15.py`, ainda em avaliação
(o achado citado no pedido, "0/12 células", é dessa família ER-baseada, não
do detector geométrico de retângulo). São operacionalizações distintas da
mesma palavra — o próprio docstring do detector geométrico argumenta que ele
é seletivo o bastante para isolar algo que o escalar diluiu. **Não trate um
resultado negativo do veto por ER como veredito sobre este veto geométrico,
e vice-versa** — são hipóteses independentes que por acaso usam a mesma
palavra "lateralização".

---

## 3. Stop do robô hospedeiro ancorado na borda mais próxima do retângulo vivo

**Mecanismo.** Enquanto um retângulo está confirmado e vivo, e o robô
hospedeiro (CopaWin) abre uma posição, o stop de proteção passa a ser
ancorado na borda do retângulo mais próxima da entrada (mais a margem de
ruído medida), em vez do múltiplo fixo de ticks que o robô usa hoje. A ideia
é usar um nível de preço REAL e já demonstrado como zona de repique, em vez
de uma distância abstrata.

**Fato medido que sustenta.** A tabela de ruído de borda dá exatamente a
distância que separa "repique normal" de "rompimento de verdade": desvio
mediano de 10-21 pontos além da linha, mas p90 de 131 a 165 pontos, e a
fração de visitas que furam mais de 100 pontos e voltam é 14-20%. Um stop
plantado exatamente na borda (distância 0) seria atropelado por ruído em
50-60% das visitas (tabela C, `>5p`); um stop ~150 pontos além da borda
sobrevive a ~80-86% do ruído medido.

**Gatilho, entrada, alvo, stop.** Gatilho: robô hospedeiro sinaliza entrada
enquanto um retângulo está confirmado e vivo, com a entrada situada entre as
bordas. Entrada: a mesma ordem-limite do hospedeiro, sem alteração. Alvo: o
mesmo do hospedeiro. Stop: a mercado (permitido), reposicionado do múltiplo
de ticks fixo para "borda mais próxima na direção contrária à posição + ~150
pontos (calibrar contra o p90 medido, por W e por lado)". Não introduz
ordem nova nem lado inválido — só recalcula a distância de um stop que já
é a mercado por regra.

**Oportunidades por pregão.** Não gera trade — atua sempre que o hospedeiro
já opera com um retângulo vivo por perto. A cobertura é a mesma estimada no
desenho 2 (~30%+ da sessão coberta por pelo menos um retângulo ativo,
somando janelas). O que precisa ser medido é a fração das entradas do
hospedeiro que caem dentro dessa janela — se for pequena, o desenho tem
pouco efeito prático, não porque é falso, mas porque quase nunca dispara.

**O que o refuta.** Se o stop ancorado na borda não reduzir MaxDD/aumentar
lucro-por-DD frente ao stop fixo atual, em ambas as janelas, ou se ele
sistematicamente colocar o stop MAIS LONGE do que o fixo (aumentando
prejuízo por trade sem ganho de sobrevivência), o desenho está morto. Watch
especial: se a borda mais próxima estiver muito perto da entrada (retângulo
estreito), o stop calculado pode ficar mais curto que o mínimo de segurança
do robô — precisa de um piso.

**O que já contradiz.** Nenhuma medição direta — é território novo. Fica
adjacente à família de "5 ajustes estruturais REFUTADOS" do `wdo_orb`
(trailing/stop/alvo/regime/combo, 2026-09-11): lá, mudar a régua de stop de
um jeito estrutural não sobreviveu à amostra real. Não é o mesmo mecanismo
(lá era WDO/ORB, aqui é WIN/retângulo), mas é o mesmo TIPO de mudança
("trocar múltiplo fixo por regra adaptativa") que já falhou uma vez no
projeto — motivo para ceticismo extra, não para descartar sem medir.

---

## 4. Grade dupla nas duas bordas, mirando o meio — não aposta direção

**Mecanismo.** Assim que o retângulo é confirmado, arma DUAS ordens-limite
simultâneas: venda no topo mirando o meio, compra no piso mirando o meio.
Como a quebra é 50/50 e o meio é cruzado repetidas vezes depois da
confirmação, este desenho tenta capturar a oscilação em si, sem prever qual
lado vai ser tocado primeiro nem qual vai romper.

**Fato medido que sustenta.** "Mediana de 1-2 cruzamentos do MEIO depois da
confirmação (51-67% têm ≥1, 39-57% ≥2, 32-45% ≥3)" — ou seja, na maioria dos
retângulos confirmados o preço ainda visita o meio pelo menos uma vez depois
de reconhecível, o que dá a QUALQUER um dos dois lados da grade uma chance
real de ser tocado e ir a favor.

**Gatilho, entrada, alvo, stop.**
- Gatilho: retângulo confirmado.
- Entrada: `EnterLimit` de VENDA no topo (descansa acima do preço — válido,
  já que o preço no instante da confirmação está dentro da banda, abaixo do
  topo) e `EnterLimit` de COMPRA no piso (descansa abaixo do preço — válido)
  simultaneamente, cada uma com `ttl_bars` até a expectativa de vida restante
  (ver desenho 6).
- Alvo: cada perna mira o meio (metade da largura, tipicamente 148-203
  pontos) — paga os 7,5 pontos de custo com folga grande.
- Stop: a mercado, calibrado pelo ruído de borda (mesma tabela do desenho
  3), em CADA lado.
- **Ponto que quem implementar precisa resolver, não um detalhe**: se uma
  perna enche e depois o preço rompe para o lado oposto (perde o stop da
  perna que encheu), o que acontece com a ordem ainda pendente do outro
  lado? Ela precisa ser cancelada assim que a primeira enche, senão o
  desenho vira sem querer uma aposta direcional dobrada. Em conta NETTING
  (o terminal da corretora é NETTING, confirmado para o MT5 da Clear/Rico em
  outro contexto do projeto) as duas pernas nem podem coexistir como
  posições opostas — a segunda entrada inverteria/zeraria a primeira. Isto
  PRECISA ser verificado contra o comportamento real da conta antes de
  medir qualquer número.

**Oportunidades por pregão.** Usando a fração "≥1 cruzamento do meio depois"
(51-67%) sobre os retângulos confirmados por dia (W30: 5,24/dia) dá
~2,7-3,5 oportunidades de UMA perna preencher por dia só em W30; somando W's
menores (30,45,60, que têm counts maiores) o total plausível fica acima de
1/dia com folga para validar em 191 pregões.

**O que o refuta.** Net das duas pernas (incluindo a perna que paga o stop
quando o rompimento acontece de verdade) negativo ou instável entre IS/OOS.
Especificamente: a soma dos ganhos das pernas que fecham no meio precisa
superar a soma das perdas de stop das pernas que ficam presas do lado
errado quando o retângulo rompe de vez (91-98% eventualmente rompe).

**O que já contradiz.** Nenhuma medição direta contradiz — mas o mecanismo
de "duas ordens pendentes, cancelar uma quando a outra enche" é exatamente o
tipo de complexidade operacional que gerou bug em outros lugares do projeto
(ex. "Cancel silencioso e órfã" — cancelamento que falha sem levantar
exceção). Tratar isso como given é ingênuo; é um ponto de falha adicional
que os outros 7 desenhos não têm.

---

## 5. Multiplicador de alvo/stop do robô hospedeiro pela largura do retângulo mais recente

**Mecanismo.** Em vez de o hospedeiro (CopaWin) usar um múltiplo fixo de
ticks para alvo e stop, ele passa a escalar esses múltiplos pela largura do
retângulo confirmado mais recente no mesmo pregão (uma medida de "amplitude
típica do dia", calculada só com barras já fechadas — sem look-ahead).

**Fato medido que sustenta.** A largura mediana varia de forma consistente e
mensurável por W (297 pontos em W30 até 406 em W120) e por pregão — ou seja,
é um sinal real de regime de amplitude, não ruído: dias com retângulos mais
largos têm mercado mais amplo, dias com retângulos mais estreitos (ainda
acima do piso de 6 ticks) têm mercado mais contido. Isso é exatamente o tipo
de proxy de ATR adaptativo que dias diferentes pedem.

**Gatilho, entrada, alvo, stop.** Gatilho: robô hospedeiro gera sinal de
entrada. Entrada: a mesma ordem-limite do hospedeiro. Alvo/stop: os
múltiplos de tick do hospedeiro passam a ser recalculados como fração da
largura do último retângulo confirmado (ex. alvo = X% da largura, stop = Y%
da largura) em vez de um número fixo de ticks. Não introduz lado de ordem
novo — é puramente um recálculo de distância.

**Oportunidades por pregão.** Não gera trade — atua sempre que o hospedeiro
teria operado de qualquer forma; o que muda é a geometria de cada trade.
Frequência de "ter um retângulo de referência disponível" é alta cedo o
bastante no pregão só se pelo menos um W curto (30 ou 45, que juntos somam
quase 9/dia) já tiver confirmado — cold-start é um risco real nas primeiras
dezenas de minutos do pregão, quando ainda não há nenhum retângulo para
calibrar (mesmo problema já documentado para o `wdo_orb`: "cold-start
mascara resultado").

**O que o refuta.** Se a versão com múltiplo dinâmico não bater a versão com
múltiplo fixo em lucro/DD nas duas janelas, ou se o dinâmico só ganhar
porque comprime a amostra (menos trades, censura), o desenho não presta —
aplica-se a regra do CLAUDE.md de nunca ler líquido sem checar trades e
pregões sem trade.

**O que já contradiz.** Ver desenho 3: mesma família de "ajuste estrutural
de geometria" que já falhou para o `wdo_orb` em 2026-09-11 (5 ajustes
refutados). Testar de novo, num robô e instrumento diferentes, é legítimo,
mas o prior deveria ser cético, não neutro.

---

## 6. TTL adaptativo da entrada do hospedeiro pela vida esperada do retângulo

**Mecanismo.** A ordem de entrada do robô hospedeiro (`EnterLimit`) precisa
de `ttl_bars` — sem prazo ela some no livro até o fim do pregão. Em vez de
um prazo fixo arbitrário, este desenho usa a vida esperada do retângulo mais
recente (tempo total de duração menos tempo já decorrido) como teto do
prazo: se o regime que motivou o sinal só deve durar mais N minutos, não faz
sentido deixar a ordem pendente além disso.

**Fato medido que sustenta.** As medianas de duração TOTAL (61 min em W30
até 174 min em W120) e de "vida depois da confirmação" (20 a 34 min,
tolerante) dão uma estimativa concreta e observável (sem olhar o futuro,
porque usa só o histórico já visto do próprio retângulo) de quanto tempo
ainda falta para o regime morrer.

**Gatilho, entrada, alvo, stop.** Gatilho: robô hospedeiro gera sinal com um
retângulo confirmado por perto. Entrada: a mesma ordem-limite, com
`ttl_bars` recalculado a partir da vida esperada (convertida de minutos para
barras REAIS do dia, nunca barras nominais — a base varia de 190 a 586
barras/minuto). Alvo/stop: inalterados.

**Oportunidades por pregão.** Mesma cobertura dos desenhos 3 e 5 — não gera
trade próprio, só se aplica quando o hospedeiro já sinalizaria.

**O que o refuta.** Se a taxa de preenchimento e o atraso realizado (medido
em minutos reais, nunca no prazo nominal) não melhorarem frente ao `ttl_bars`
fixo atual — ou se o TTL mais curto simplesmente cortar trades sem
melhorar o R$/trade dos que sobram — o desenho não presta.

**O que já contradiz.** Nada diretamente, mas reforça uma regra já escrita
no CLAUDE.md ("nunca traduza prazo em barras para prazo em tempo sem
calibrar") — este desenho é, em parte, uma forma de nunca cometer esse erro
de novo, calibrando o prazo pelo próprio relógio do mercado em vez de um
número de barras chutado.

---

## 7. Fade na própria borda, sem esperar falso rompimento — stop calibrado por ruído

**Mecanismo.** Assim que o retângulo é confirmado, arma uma única
ordem-limite na borda (venda no topo ou compra no piso, na direção que o
preço estiver mais perto de tocar), mirando o meio, com o stop calibrado
pela tabela de ruído (não um múltiplo arbitrário do range, como o D2 do
dono usa). É uma versão mais simples do desenho 4 (só um lado, não os dois).

**Fato medido que sustenta.** Toques por borda são o critério que confirma o
retângulo em primeiro lugar (mediana de 3 visitas em W30, 5-6 em W120) — a
borda já demonstrou ser um nível respeitado váras vezes antes mesmo da
confirmação. A tabela de ruído dá o tamanho do stop: mediana de desvio
10-21 pontos, p90 de 131-165 pontos.

**Gatilho, entrada, alvo, stop.** Gatilho: retângulo confirmado, preço
ainda dentro da banda. Entrada: `EnterLimit` na borda mais próxima do preço
atual, do lado correto (venda acima do preço no topo, compra abaixo do
preço no piso — ambos válidos). Alvo: meio do retângulo, ordem-limite real.
Stop: a mercado, ~150 pontos além da borda (calibrar por W e por lado contra
o p90 medido).

**Oportunidades por pregão.** A tabela de ruído "depois da confirmação"
(parte B) mostra ~1 visita por retângulo em média em W30 (757 visitas topo /
685 retângulos IS ≈ 1,1), o que dá algo como ~5-6 oportunidades/dia somando
topo+piso em W30 — suficiente para validar em 191 pregões, MAS todas essas
"visitas" na tabela foram contadas pelo TOQUE, não pelo PREENCHIMENTO real
de uma ordem-limite. É exatamente aqui que mora o maior risco deste
desenho.

**O que o refuta.** Win% contra o breakeven implícito do alvo/stop
escolhidos, medido nas duas janelas — e, mais importante, uma vez que
alguém tenha dado ao menos uma calibração de fila para o WIN@ (ainda
inexistente), refazer a conta assumindo preenchimento no primeiro toque é
inválido por definição (mesma lição que já custou um mês de medição viciada
no WDO F1 maker).

**O que já contradiz.** Este é o desenho mais parecido, em espírito, com a
família de robôs maker do WDO F1 que foi ENCERRADA em 2026-09-10
(`wdof1_familia_maker_encerrada_fila_2026_09_10`: "lucro só com fila zero;
fila real calibrada mostra bruto R$0,45 < corretagem R$0,50"). O WIN não tem
o problema de custo alto do WDO (7,5 pontos = R$1,50, desprezível), então a
matemática pode ser diferente — mas a ausência TOTAL de calibração de fila
para o WIN@ significa que este desenho está exposto ao MESMO tipo de erro de
modelo que inverteu o sinal do resultado no WDO, só que aqui ninguém tem
sequer uma estimativa de quanto isso pesa. Colocar este desenho em produção
ou até em medição séria sem antes ao menos uma calibração exploratória de
fila para o WIN@ é repetir o erro já documentado de "parâmetro de realismo
que nasce desligado".

---

## 8. Filtro de dia por contagem de retângulos (especulativo, prioridade baixa)

**Mecanismo.** Conta quantos retângulos (qualquer W) já se confirmaram no
pregão até certo horário; se o número já estiver muito acima da mediana
histórica, marca o dia como "excepcionalmente lateral" e desarma as entradas
direcionais do hospedeiro pelo resto do pregão (filtro de DIA, não de
espera — igual à célula "A_PULA" do script de veto do wdo_orb).

**Fato medido que sustenta.** A frequência de retângulos por pregão tem uma
mediana conhecida e estável por W (5,24/dia em W30, etc.) — dá uma régua
objetiva (não ajustada ao resultado) para definir "dia mais lateral que o
normal" via percentil da própria distribuição histórica.

**Gatilho, entrada, alvo, stop.** Gatilho: contagem acumulada de retângulos
confirmados no dia, até um horário de corte, excede um percentil alto da
distribuição histórica (ex. p90). Entrada: nenhuma nova — é um filtro de
dia que desarma o hospedeiro. Alvo/stop: N/A.

**Oportunidades por pregão.** Este é, por construção, um evento de baixa
frequência (por definição, um percentil alto da distribuição só deveria
disparar em ~10% dos dias, ~19 de 191 pregões) — na fronteira do que dá para
validar com confiança. Precisa ser dito explicitamente: com esse n, qualquer
diferença de resultado observada tem intervalo de confiança largo.

**O que o refuta.** Se o corte (percentil e horário) só "funcionar" depois
de ajustado ao próprio conjunto de dados observado, é ajuste, não achado —
exatamente o erro que o projeto já documentou ao preferir Q_saída=489
(Kaplan-Meier) sobre 600 (o que mais "encaixava" no dia já visto). O corte
tem que ser fixado ANTES de olhar o resultado, e mesmo assim testado nas
duas janelas.

**O que já contradiz.** Filtros de dia/horário já foram tentados e
refutados neste projeto pelo menos duas vezes: "Filtro dia/horário
REFUTADO" (`wdo_win_filtro_dia_horario_refutado_2026_09_04`: cortar o pior
dia/hora piora o OOS) e o padrão geral de filtros de contexto que não
sobrevivem (candlestick 0/21, continuidade/momentum refutado, cor do minuto
0/26). O prior aqui deveria ser fortemente cético — este desenho está na
lista por completude de raciocínio ("retângulo como sinal de ausência" no
nível do dia), não porque haja razão para acreditar que vai escapar do
padrão.

---

# Desenhos que eu considerei e DESCARTEI

**(a) Rompimento direto: comprar acima do topo / vender abaixo do piso,
mirando a continuação do rompimento.** Morre na checagem MECÂNICA antes de
qualquer dado: uma ordem de compra acima do preço atual não é uma
ordem-limite que descansa no livro — ou é rejeitada, ou executa
imediatamente como uma ordem marcável, que é exatamente a definição de
ordem a mercado disfarçada de limite. É a mesma razão pela qual o motor
recusa `Enter` a mercado de propósito e pela qual ordem-stop está banida.
Não existe reformulação em limite pura para "entrar NA quebra, antes que ela
aconteça" — só dá para entrar DEPOIS que ela já aconteceu (é o que o
desenho 1 faz).

**(b) Gestão de posição aberta ancorada no meio do retângulo** — ex. "se um
retângulo se forma contra uma posição já aberta do CopaWin, mover o stop
para o meio ou realizar parcial ali". Descartado não por checagem mecânica,
mas por já ter sido refutado: `copawin_trajetoria_gestao_refutada_2026_09_15`
testou 24 regras de gestão de posição para exatamente este robô e nenhuma
sobreviveu — a conclusão registrada foi que a produção já é um ótimo local.
Trocar o GATILHO (agora é "aparecer um retângulo" em vez das 24 regras já
testadas) não muda o padrão estrutural que a medição encontrou; reabrir esse
eixo sem uma razão nova e específica seria ignorar um achado já pago.

**(c) Usar a concordância M1/M5/M15 para filtrar a direção do retest
(desenho 1) ou de qualquer outro desenho direcional.** Morre no próprio
dado que a rodada de hoje mediu: "3 de 3 alinhados" prevê a favor em 44,6%
no IS e 55,3% no OOS — sinal invertido entre as duas janelas, o padrão que o
projeto já nomeou de "convenção de direção instável". Um filtro que muda de
sinal entre IS e OOS não é um filtro, é ruído com aparência de sinal;
usá-lo para dar confiança extra a qualquer entrada seria pior do que não
usar nada.

**(d) Operar só retângulos W=120 com concordância tripla de prazos** (a
combinação que, à primeira vista, parece a mais "confiável" — meio já
convergido em 77-86% dos casos, retângulo mais largo). Morre por TAMANHO DE
AMOSTRA antes mesmo de chegar à checagem de edge: a própria tabela medida
marca essa célula com `n=11` no IS e `n=9` no OOS, ambos sinalizados no log
como `n<25`. Qualquer "resultado" dali — positivo ou negativo — é ruído de
amostra pequena, não uma leitura válida de edge, e não tem como virar
desenho até que uma amostra maior exista (o que, dado 0,56 retângulo/dia em
W120, exigiria bem mais de 191 pregões).
