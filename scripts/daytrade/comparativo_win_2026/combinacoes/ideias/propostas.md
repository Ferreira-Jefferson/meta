# Combinações das 6 estratégias WIN 2026: outras possibilidades além do consenso (A) e da nota (B)

Base: CSVs de `resultados/`, de 02/01 a 05/10/2026, R$1.000, 1 contrato, sem custo, mais o que a F0 entrega: votos por M1 (lado favorecido, força, posição real, sinal), a tabela de eventos com MFE/MAE e o simulador de saída genérico.

## 1. O que os CSVs já mostram e que muda o desenho de qualquer combinação

| par / estratégia | fato | consequência |
|---|---|---|
| Win × Win_c1 | correlação do resultado diário 0,97; mesmo lado em 100% dos dias em que as duas operam | é **um voto só**. Contar as duas transforma "maioria de 6" em "maioria de 5 com um voto em dobro" |
| Win, WinCincoMedias, WinDeslocamentoMatinal | mesmo lado em 79–92% dos dias em que operam juntas; correlação diária 0,13–0,36 | família **tendência**. Concordar entre elas é quase automático e acrescenta pouca informação |
| WinRetanguloEma34, WdoRetangulo | mesmo lado que a família tendência em 43–63% dos dias; correlação diária com as outras de −0,08 a +0,10 | família **retângulo**. É a única fonte de voto independente |
| WdoRetangulo | o lucro vem de aposta direcional que segura até 18:20, e o holdout jan–jul não passou do p95 do sorteio de lado (memória `win_retangulo_acidental_tick_bug`) | serve como **voto placebo**, não como voto informativo |
| WinCincoMedias | o filtro pela abertura do mês foi escolhido em 2026 e caiu de PF 1,54 para 1,04 em 2025 (memória `win_hipoteses_regime_mes`) | o +8.859 é em boa parte ajuste a 2026 |
| WinRetanguloEma34 | 733 operações | com R$2/op paga R$1.466 de custo sobre +2.307. Qualquer combinação que dê peso a ela muda muito entre "sem custo" e "com R$2" |
| soma das 6, sem teto | +24.018, MaxDD R$1.587 (melhor isolada: Cinco +8.859, DD R$826) | a diversificação existe, mas exige até 6 contratos ao mesmo tempo |

**Ressalva que vale para todas as ideias.** As seis estratégias tiveram regras ou parâmetros escolhidos olhando 2026. O walk-forward mensal protege só a camada de combinação, e não a seleção das bases. Uma combinação que "melhora" 2026 mede ganho relativo sobre bases já otimistas. Não existe holdout externo nesta base, porque o M1 começa em 2025-10. A única validação limpa é out/2026 em diante, em regime forward. Por isso o ranking privilegia ideias com poucos parâmetros, teste pareado (as mesmas entradas, só muda a regra) e mecanismo explicável.

**Controles transversais, que entram em toda ideia além dos do protocolo:**
- **Placebo de votante.** Troca-se o voto de uma estratégia por um lado sorteado com o mesmo horário, pelo menos 200 vezes. Se a regra ganha o mesmo com o placebo, o ganho não vem da informação do voto.
- **Win_c1 fora dos votos.** Ela só entra como alternativa ao Win, nunca junto.
- **Contagem de células.** Toda tabela informa quantas variantes foram olhadas, para que o percentil contra o aleatório seja lido com Bonferroni aproximado.

## 2. Ranking

Critério: chance de valer a pena × baixo custo. As frentes A e B não estão aqui.

| # | ideia | custo | chance | depende da F0 |
|---|---|---|---|---|
| 1 | Portfólio com teto de exposição simultânea | rápido | média-alta | não (só CSVs) |
| 2 | Estado das 10:30 do Deslocamento como regime diário para as outras | rápido | média | parcial (sinal do dia) |
| 3 | Saída pela virada da outra família (teste pareado) | médio | média | sim (votos + simulador) |
| 4 | Veto cruzado por posição real contrária de outra família | rápido | média-baixa | sim (posição real) |
| 5 | Ordem de chegada: 1ª entrada × entrada que confirma outra família | rápido | média-baixa | sim (posição real) |
| 6 | Volatilidade e horário como moderadores de stop e alvo, sem mexer no lado | médio | média-baixa | sim (eventos MFE/MAE + simulador) |
| 7 | Revezamento por horário: cada estratégia só na sua faixa | médio | baixa | não |
| 8 | Peso por desempenho recente e desligar após queda | rápido | baixa | não |
| 9 | Clusters de estados de votos por família | médio | baixa | sim |
| 10 | Meta-rotulagem das entradas com os votos das outras | pesado | baixa | sim |

**Testar primeiro: 1, 2, 3 e 4.**

---

## 3. As propostas

### 1. Portfólio com teto de exposição simultânea (rápido)

**Hipótese.** Como as famílias são descorrelacionadas no dia (correlação de −0,08 a +0,10), rodar várias estratégias ao mesmo tempo com teto de K contratos dá lucro/DD maior que a melhor isolada, sem quebrar R$1.000.

**Desenho.**
- Entram os CSVs de 5 estratégias: Win (ou Win_c1, como variante), Cinco, Desloc, RetEma34 e WdoRet. Uma segunda rodada exclui WdoRet, que é o placebo.
- Fila de eventos por horário de entrada e saída. Uma entrada é aceita se, naquele instante, as posições abertas forem < K e o caixa (R$1.000 + resultado fechado) for ≥ K_aberto × margem do WIN (`contracts_from_capital_operacional`). Uma entrada recusada some.
- Regra de prioridade quando duas entradas chegam no mesmo minuto com o teto cheio:
  - (a) quem chegou primeiro;
  - (b) a ordem de R$/op dos meses anteriores (walk-forward).
- Grade: K ∈ {1, 2, 3, sem teto} × prioridade {a, b} × com ou sem WdoRet, 16 células.
- K e a prioridade são escolhidos por walk-forward: no mês m vale a célula com melhor lucro/DD em 1..m−1. Janeiro usa K=2 com a prioridade (a).

**Aproximação aceitável.** As estratégias não interagem: cada uma decide sozinha, e o teto só descarta. A exceção é o teto de 10% do saldo do Deslocamento, que usa o saldo dela. No portfólio esse saldo passa a ser o caixa comum, e é preciso recalcular o stop dela ou declarar o desvio.

**Métrica.** Líquido, MaxDD R$, lucro/DD, pior mês, meses positivos e caixa mínimo, sem custo e com R$2/op, na tabela por mês do protocolo.

**Controles.**
- Melhor isolada (Cinco: +8.859, DD 826).
- Soma sem teto.
- Prioridade sorteada (200 sorteios). Neste caso o "filtro aleatório de mesma fração" é descartar ao acaso o mesmo número de entradas que o teto descartou.

**Sobreajuste.** Baixo: 2 parâmetros discretos e nenhum limiar contínuo. O risco real está nas bases. Se o portfólio só ganha porque soma Cinco e RetEma34, que foram escolhidas em 2026, ele herda o otimismo delas. Ler também o resultado sem Cinco.

**Por que não repete o refutado.** G14–G15 (memória `ea_win_orquestracao`) viram a ruína subir no portfólio, mas a R$250 e com 1 contrato, onde o caixa não se divide. Aqui o caixa é de R$1.000 e o teto é explícito. As sleeves F2 das Ondas 4/5 eram da mesma família (correlação mensal 0,44–0,85). Aqui as famílias são outras e a correlação é ~0.

---

### 2. Estado das 10:30 do Deslocamento como regime diário (rápido)

**Hipótese.** A decisão das 10:30 do WinDeslocamentoMatinal classifica o dia. Com |preço − abertura| ≥ 0,3 ATR e sem cruzar a abertura, é dia de tendência. Sem sinal, é dia lateral. As estratégias de tendência (Win, Cinco) devem render mais depois das 10:30 nos dias com sinal e do lado dele. RetEma34, que opera retângulo, deve render mais nos dias sem sinal.

**Desenho.**
- Para cada dia, o estado às 10:30 sai da F0 (o voto "sinal" do Deslocamento, calculado mesmo quando a limitada não enche): {compra, venda, sem sinal}. Também a variante contínua: deslocamento/ATR às 10:30 em tercis.
- Para cada operação das outras com entrada ≥ 10:31, marcar o estado e se o lado dela é a favor ou contra.
- Tabela R$/op e n por estratégia × {a favor do sinal, contra o sinal, sem sinal}.
- A regra é fixada antes, não otimizada: tendência só a favor do sinal ou sem sinal; retângulo só sem sinal. Existe uma única variante alternativa, que vem do walk-forward: em cada mês, bloquear as células com R$/op < 0 nos meses anteriores.
- No máximo 4 células.

**Métrica.** Δ líquido e Δ lucro/DD contra a mesma estratégia sem a regra, por mês.

**Controles.**
- Filtro aleatório que descarta a mesma fração de operações depois das 10:30, por dia inteiro (sorteia dias, não operações, porque o regime é diário).
- Melhor isolada.

**Sobreajuste.** Médio-baixo, porque a regra é escrita antes de olhar. Há cerca de 50 dias com sinal em 9 meses (o Deslocamento operou 65 dias), então cada célula tem poucas dezenas de operações e o IC vai ser largo. Se a variante pré-registrada não passar do p95, encerra.

**Relação com o refutado.** "Dias sem cruzar a abertura" não validou como fato isolado (memória `win_memoria_curto_prazo`). Aqui ele não é usado como sinal de direção: é usado como moderador do edge de outra estratégia, uma pergunta que não foi feita. A memória também diz que o passado recente indica escala, não direção, e o regime de tendência × lateral é uma pergunta de escala.

---

### 3. Saída pela virada da outra família, em teste pareado (médio)

**Hipótese.** Uma posição de X que passa a ter a outra família votando contra (posição real ou lado favorecido) tende a devolver o ganho. Sair nesse instante melhora o R$/op das mesmas entradas.

**Desenho.**
- Entram todas as operações de X ∈ {Win, Cinco, Desloc, RetEma34}.
- Saída alternativa: o primeiro M1 fechado depois da entrada em que a família oposta (ou, na variante, ≥ 2 das outras 4 estratégias deduplicadas) fica contra. A execução é a mercado no 1º tick do M1 seguinte, pelo simulador da F0. A saída original continua valendo se chegar antes. O stop nunca é afrouxado.
- Grade:
  - tipo de voto {posição real, lado favorecido};
  - quorum {família oposta, ≥ 2 de 4};
  - carência {0, 5 min} antes de a regra poder agir.
- São 8 células por estratégia, 32 no total. Na variante walk-forward, a célula de cada estratégia é escolhida nos meses anteriores.

**Métrica.** Diferença pareada por operação (R$ da nova saída − R$ da original), com média, IC por bootstrap de dias e fração de operações afetadas. Depois, a tabela mensal.

**Controles.**
- Saída num instante sorteado, com a mesma distribuição de "minutos após a entrada" das saídas acionadas: separa "sair mais cedo" de "sair quando a outra vira".
- Placebo de votante, com WdoRet ou com um lado sorteado.

**Sobreajuste.** Médio. O teste pareado tem muito mais poder que comparar líquidos, o que é bom com 9 meses. São 32 células, e a correção de multiplicidade é obrigatória.

**Por que vale.** Na memória, os achados mais consistentes do WIN são de **saída**, não de entrada:
- "vela fecha contra a LWMA34" foi positivo em EXPLORE/VALID/COFRE;
- "saída fixa > trailing" parece estrutural;
- o Cinco "aperta quando vai contra" melhorou 2025 e 2026.

A ressalva da mesma memória vale aqui: a saída que melhorava a F2 sumia com 5 min de atraso. Por isso a execução tem de ser imediata, e a carência de 5 min entra como teste de robustez, não como otimização.

---

### 4. Veto cruzado por posição real contrária (rápido, depois da F0)

**Hipótese.** Uma entrada de X que chega enquanto outra família tem **posição real** aberta do lado oposto é pior que a média de X. Bloquear só esses casos melhora X sem exigir consenso, porque o veto é assimétrico: a outra estratégia só bloqueia, nunca dispara entrada.

**Desenho.**
- Entram os eventos da F0. Para cada entrada de X, conta-se quantas outras estratégias (deduplicadas, sem Win_c1) estão posicionadas contra naquele M1.
- Regra: veta se houver ≥ 1 posicionada contra.
- Grade:
  - vetador ∈ {família oposta, mesma família, qualquer};
  - tipo de voto ∈ {posição real, lado favorecido com força acima da mediana do passado}.
- São 6 células por X; o vetador é escolhido por walk-forward.
- Diferença para a frente A: A exige concordância (filtro positivo), e esta proposta só remove o conflito ativo (filtro negativo). Nos dados, A deve cortar a maioria das entradas da família retângulo; o veto corta menos.

**Métrica.** Δ líquido, Δ R$/op e fração vetada.

**Controles.**
- Filtro aleatório com a mesma fração vetada, 200 sorteios, percentil.
- Placebo de votante.

**Sobreajuste.** Médio. A fração vetada deve ser pequena (posições abertas ao mesmo tempo em lados opostos são raras fora do RetEma34), e o n vetado pode ficar em poucas dezenas.

**Relação com o refutado.** Na roxa+verde, "concordância piora" e "ausência de concordância" inverteram no cofre (R1/R2, memória `win_roxa_verde_variacoes_cofre`). Aquilo era o **mesmo** sinal em outro tempo gráfico. Aqui o vetador é outra lógica, com correlação ~0. Se der o mesmo padrão de inversão entre metades do ano (jan–mai × jun–out), encerra.

---

### 5. Ordem de chegada: a entrada que confirma (rápido, depois da F0)

**Hipótese.** A 2ª entrada no mesmo lado, que chega quando outra família já está posicionada a favor há ≥ m minutos **e no lucro**, tem R$/op diferente da 1ª. O sinal esperado não é óbvio: maior pela confirmação, ou menor por entrar tarde. O teste mede a direção do efeito antes de qualquer regra.

**Desenho.**
- Para cada entrada de X, classifica-se:
  - **1ª**: ninguém posicionado;
  - **2ª a favor**: outra família posicionada no mesmo lado, com MTM > 0;
  - **2ª a favor no prejuízo**: mesmo lado, MTM ≤ 0;
  - **contra**: o caso da proposta 4.
- Tabela R$/op por classe e estratégia.
- Só se uma classe se destacar nas duas metades do ano, testar a regra "dobrar a mão (2 contratos) na classe boa" ou "pular na classe ruim", com caixa ≥ margem.
- Parâmetro m ∈ {0, 15} min.

**Métrica.** R$/op por classe com IC por bootstrap de dias; depois, Δ líquido e Δ DD da regra.

**Controles.**
- Nulo por permutação: embaralhar o horário de entrada das outras estratégias dentro do mesmo dia, preservando a contagem.
- Filtro aleatório de mesma fração.

**Sobreajuste.** Médio. A regra só nasce depois da descritiva, então a descritiva tem de ser lida nas duas metades separadamente. A frente B pode absorver isto como uma feature ("classe de chegada"); combinar com ela para não testar duas vezes.

---

### 6. Volatilidade e horário como moderadores de stop e alvo, sem mexer no lado (médio)

**Hipótese.** A direção é imprevisível, mas a magnitude não é. A memória mostra |retorno 60 min| de 214 pts à tarde contra 503 às 10:00, crescendo com o ATR relativo. Ajustar stop e alvo de cada estratégia pela excursão esperada naquele horário e naquele ATR, mantendo a entrada e o lado originais, melhora o R$/op porque para de usar stop e alvo de tamanho fixo em regimes de escala diferente.

**Desenho.**
- Entra a tabela de eventos da F0, com MFE/MAE em pontos e em múltiplos do ATR14 M5.
- Para cada evento, escala prevista = mediana do |retorno 30 min| no mesmo bloco horário (30 min) nos 20 pregões anteriores. É causal.
- Stop = s × escala e alvo = a × escala, pelo simulador genérico.
- Grade: s ∈ {0,75, 1, 1,5} × a ∈ {1,5, 2, 3}, com piso de alvo ≥ 1,5 × stop. São 9 células por estratégia; a célula é escolhida por walk-forward.
- Não aplicar ao Deslocamento: a memória diz que qualquer alvo corta os dias de tendência.

**Métrica.** R$/op e lucro/DD contra as saídas originais e contra stop e alvo **fixos em pontos** de mesma mediana (o controle que separa "adaptar à escala" de "mudar a geometria").

**Controles.** Escala embaralhada entre dias, mantendo a distribuição.

**Sobreajuste.** Médio-alto, porque são 9 células × 5 estratégias. Ler só o platô: a célula vencedora tem de ter vizinhas boas.

**Relação com o refutado.** Alvos fixo, trailing e de estrutura deram ruído no Cinco, e alvo em R deu ruído no Deslocamento. A diferença aqui é a escala ser **condicional ao horário e à volatilidade**. Se não bater o controle de escala fixa, encerra. Também é o candidato natural a ser absorvido pela frente B ("tamanho do alvo e do stop"); combinar com ela.

---

### 7. Revezamento por horário (médio)

**Hipótese.** As estratégias têm horários diferentes:
- Win: 9–10 h e 12–14 h;
- RetEma34: 10–13 h;
- Desloc: 10:30;
- Cinco: o dia todo.

Dar a cada faixa horária só à estratégia com melhor R$/op nela, no passado, reduz exposição sem perder lucro.

**Desenho.**
- Blocos de 1 h (9–18 h).
- Em cada mês, para cada bloco, fica a estratégia (ou as 2) com maior R$/op nos meses anteriores, com mínimo de 10 operações; as outras são bloqueadas naquele bloco.
- Grade: top-1 × top-2.

**Métrica.** Líquido, DD e lucro/DD.

**Controles.**
- Escolha da estratégia do bloco por sorteio.
- Melhor isolada.
- Portfólio da proposta 1.

**Sobreajuste.** Alto: 9 blocos × 5 estratégias, com poucas operações por célula e por mês. A memória mostra efeito de horário menor que o custo na roxa+verde. Só vale se a proposta 1 mostrar que o teto de exposição está descartando muita coisa boa.

---

### 8. Peso por desempenho recente e desligar após queda (rápido)

**Hipótese.** Uma estratégia que foi bem nos últimos N meses continua bem no mês seguinte (momentum de estratégia). Dar 1 contrato só às que estão positivas, ou desligar a que cair X% do seu pico, melhora o portfólio.

**Desenho.**
- Rebalanceamento mensal.
- Ativas no mês m: as estratégias com resultado > 0 em m−N..m−1, com N ∈ {1, 2, 3}.
- Variante de queda: desligar quando o DD próprio da estratégia ≥ D ∈ {30%, 50%} do pico de lucro dela, e religar no mês seguinte.
- São 5 células.

**Métrica e controle.** Contra o portfólio da proposta 1 sem rotação, e contra o portfólio com ativas sorteadas em mesma quantidade.

**Sobreajuste.** Alto: são só 8 decisões mensais. A tabela por mês mostra alternância forte, com sinais trocando mês a mês no WdoRet e no Win de abril a maio, o que sugere reversão e não momentum.

**Relação com o refutado.** "Parar após k perdas" ficou sempre abaixo do baseline (memória `win_hipoteses_regime_mes`). O dono também corrigiu de forma enfática a ideia de usar o resultado de um trade para decidir o próximo (memória `feedback_autopsia_por_trade`). A rotação mensal entre **estratégias** é outra pergunta, mas o parentesco é próximo. Por isso fica em último entre as rápidas: barata e com prior ruim. Rodar só se sobrar tempo, e reportar já como teste de um análogo refutado.

---

### 9. Clusters de estados de votos por família (médio)

**Hipótese.** Alguns estados conjuntos das famílias precedem retornos de M1 favoráveis, independentemente de quem entrou. Exemplos: tendência comprada com retângulo neutro, ou todas neutras.

**Desenho.**
- Estado por M1 = (família tendência ∈ {+, 0, −}, família retângulo ∈ {+, 0, −}), 9 estados; voto da família = soma dos lados favorecidos, por sinal.
- Para cada estado, retorno dos 30 e 60 min seguintes.
- Regra: operar o lado do estado só nos estados com retorno médio positivo nos meses anteriores, com entrada limitada e stop/alvo do simulador.
- Uma variante usa k-means (k ∈ {4, 6}) sobre o vetor de forças, ajustado só no passado.

**Controles.** Nulo que embaralha os dias, preservando o estado e o horário dentro do dia.

**Sobreajuste.** Alto.

**Relação com o refutado.** O "mapa de vantagem" de 23 estados, com ~5.000 células, deu −16,5 pts/op fora da amostra, no percentil 75 do nulo. A única diferença aqui é que os estados vêm de estratégias, não de features brutas, e isso é pouca diferença. Só vale como diagnóstico barato se a F0 já entregar os votos por M1 prontos.

---

### 10. Meta-rotulagem das entradas (pesado)

**Hipótese.** Com o lado definido por cada estratégia (modelo primário), um classificador simples treinado no passado, com features = votos e forças das outras, hora, ATR relativo e distância da abertura do dia, separa as entradas boas das ruins o bastante para pular as piores.

**Desenho.**
- Regressão logística com no máximo 8 features, regularizada, por estratégia ou em pool com dummy de estratégia.
- Walk-forward mensal: treina em 1..m−1 e aplica em m.
- Pula a entrada se a probabilidade prevista for < o breakeven empírico do passado.

**Controles.** Filtro aleatório de mesma fração e modelo com rótulos embaralhados.

**Sobreajuste.** Alto, com pouco dado no início do ano: janeiro e fevereiro treinam com 1 ou 2 meses.

**Relação com o refutado.** O multi-fator com 78 features (ridge/logística) deu IC fora da amostra de 0,006–0,032 (memória `ea_win_orquestracao`, Ondas 4/5). Esta proposta é praticamente a frente B com outro nome. Só rodar se B não cobrir "pular a entrada" e se as propostas 4 e 5 mostrarem que alguma feature de voto tem sinal sozinha.

---

## 4. Ordem sugerida e dependências

1. **Proposta 1** pode rodar já, só com os CSVs. Ela também calibra o teto de exposição que as outras devem respeitar quando operarem em conjunto.
2. **Proposta 2** precisa da F0 só para o estado do Deslocamento nos dias em que a limitada não encheu. Até lá dá para fazer uma prévia com os 65 dias operados, declarando o viés.
3. **Propostas 3 e 4** precisam dos votos (posição real) e do simulador da F0, e compartilham a mesma infraestrutura.
4. As propostas 5 e 6 devem ser coordenadas com a frente B para não duplicar trabalho. As propostas 7 a 10 só fazem sentido se as anteriores mostrarem sinal.
