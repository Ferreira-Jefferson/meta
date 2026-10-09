# Análise grupo_a: 5 dias (WIN M15)

Dias estudados: 2026-07-02 (+479), 2025-12-05 (-524), 2026-09-04 (+408), 2026-09-02 (-459), 2026-09-22 (+387). Só olhei esses cinco (barras M15 do dia, diário anterior, `sessoes_dec/OOS/<data>.json`). Valores em pontos (1 pt = R$0,20). "ATRd" = ATR diário (14) até ontem; "ATR15" = ATR M15 da vela. Números aproximados, lidos das barras.

## Perguntas propostas (resumo; texto completo na tabela final)

- P1 `rompe_ontem`: a vela fechada fechou além da máxima/mínima de ontem, com volume >=1,5x a média das últimas 20 velas?
- P2 `faixa_rompida`: 12+ velas de hoje em faixa < 1 ATRd, e a vela atual fechou fora dela com amplitude >=1,5 ATR15?
- P3 `desloc_abertura`: onde está o preço contra a abertura, em ATRd?
- P4 `reconquista_abertura`: depois de >=0,5 ATRd do outro lado da abertura, fechou de volta no lado oposto?
- P5 `h1_direcao`: H1 e M15 apontam alta, baixa ou nada?
- P6 `perna_esgotada`: perna > 1 ATRd e 3 velas sem novo extremo?
- P7 `lateral_morta`: 8 velas com amplitude < 0,5 ATRd e volume fraco?
- P8 `seguimento_rompimento`: após rompimento, as 2 velas seguintes seguiram ou falharam?
- P9 `tendencia_forte_sem_alvo`: tendência forte e limpa (segurar sem alvo fixo)?

---

## 2026-07-02 (quinta, OOS, Jev +479: 4 vendas, 4 alvos)

### Retrospectiva
- Abertura 174555 (gap ~0), ATRd 3016. Dia de **pico de abertura e devolução**: 09:30 sobe +1690 pts numa vela (volume 1,24M), 10:30 faz a máxima 177055 (+2500 da abertura, 0,83 ATRd) e a partir das 10:45 devolve tudo até 174830 (11:30). Das 12:00 às 15:00 faixa morta de ~500 pts com volume caindo (de 550k para 220k); depois deriva levemente para cima, sem utilidade.
- Melhores entradas: venda após 10:45 (a vela fez 177055 e fechou 175925, rejeição de 1130 pts). Realista pelas regras do motor: venda ~176000 até ~174700 = ~1300 pts em uma operação. Comprar o 09:30 renderia ~+500 até 10:30 e devolveria.
- Jev: vendeu 09:45 (176355), 10:00, 10:45 e 11:00; todas bateram alvo (+2395 pts líquidos, R$479). Acertou por vender **depois da falha** do rompimento (09:45 e 10:00 fecharam abaixo de 176355 sem seguimento). É contra-tendência que deu certo porque o rompimento falhou, não porque "vender alta" funcione em geral.

### Momentos de decisão
1. 09:30 (fecha 176355, rompe a máxima de ontem 174685 com volume 1,24M): comprar ou esperar o seguimento? Esperar.
2. 09:45/10:00: duas velas sem fechar acima de 176355. O rompimento falhou: sustenta vender.
3. 10:45: nova falha na máxima do dia (177055, fechamento 175925): vender.
4. 12:00-15:00: faixa morta; ficar fora.

### Perguntas por momento
- M1: **P1** = `acima_com_volume`; **P8** = `sem_rompimento` (ainda sem as duas velas seguintes): sustenta **ficar fora e esperar o seguimento**.
- M2: **P8** = `falhou` (as duas velas seguintes fecharam abaixo do fechamento da vela de rompimento): **entrar vendendo**.
- M3: **P8** = `falhou` de novo (fecha 175925 abaixo do fechamento de 10:30): **manter/entrar vendendo**. **P6** vira sim por volta de 11:15 (perna 1,04 ATRd, 3 velas sem nova máxima): confirma.
- M4: **P7** = sim (12:30-15:00, amplitude ~0,15 ATRd, volume < 50% do pico): **ficar fora**.

---

## 2025-12-05 (sexta, OOS, Jev -524: venda +55, duas compras stopadas)

### Retrospectiva
- Abertura 165250, ontem fechou 165390 (gap ~0), ATRd 1798. **Dia de tendência de baixa explosiva**: 09:00-12:30 faixa 165785-164790 (~1000 pts, 0,55 ATRd, ATR15 ~240). 12:45 vela de -2340 pts (volume 1,59M, ~2,5x a média), 13:15 mais -2435 (perde a mínima de ontem 162650 com volume 1,28M). Cai quase sem pausa até 158055 às 15:45 (-7730 do topo, 4,3 ATRd). Fecha ~158400.
- Melhor entrada: venda em 13:00-13:15 (limite no repique, ~164000). Segurando sem alvo, com stop estrutural, 4000+ pts; com o motor, realista ~2500-4000 pts (R$500-800).
- Jev: vendeu 12:45 em 165770 com alvo curto (+285 pts, R$55), correto mas saiu em 8 min; depois **comprou a queda duas vezes** (14:00 e 15:16), ambas stopadas (-R$579). Erro clássico: "barato". O dia estava a 1,7 ATRd abaixo da abertura, com H1 em baixa.

### Momentos de decisão
1. 12:45: faixa de 3h rompida para baixo com volume enorme.
2. 13:15: perde a mínima de ontem com volume: vender/segurar.
3. 14:00: Jev compra a 162215, dia a -1,7 ATRd da abertura: não comprar.
4. 15:16: Jev compra de novo: não comprar.
5. 16:30: perna de ~4 ATRd, três velas com mínimas crescentes: cobrir.

### Perguntas por momento
- M1: **P2** = sim (faixa de 12 velas ~0,55 ATRd; vela de 2340 pts, ~8x o ATR15): **entrar vendendo**, sem alvo curto.
- M2: **P1** = `abaixo_com_volume` (fecha 161350 < 162650, volume 1,28M); **P8** = `seguiu`: **segurar a venda**.
- M3: **P3** = `abaixo_forte` (-3035 pts = -1,7 ATRd) e **P5** = `baixa`: **ficar fora de compra**. **P9** = sim: sem alvo fixo.
- M4: idem M3 (**P3** `abaixo_forte`, -4750 = -2,6 ATRd): **ficar fora de compra**.
- M5: **P6** = sim (perna >1 ATRd; 16:00-16:30 três velas sem nova mínima): **sair da venda / apertar stop**.

---

## 2026-09-04 (sexta, OOS, Jev +408: 2 compras e 1 venda, todas alvo)

### Retrospectiva
- Abertura 187865 (ontem 187850, gap 0), ATRd 3686. **Queda de abertura com V de recuperação e esgotamento à tarde**: 09:30 e 10:15 fazem mínimas 185950 e 185520 (-2345 da abertura, 0,64 ATRd); 10:30 reverte (volume 1,30M); 11:00-11:45 sobe (cruza a abertura em 11:30, fecha 187960; topo 188240 às 11:45); 12:45-13:15 topo 188990; depois deriva para 187025 (16:30), faixa estreita no fim.
- Melhor entrada: compra a 186620 (10:30, após reversão) ou 187240 (11:00). Alvo realista ~3000 pts (186600 -> 188900).
- Jev: comprou 10:45 e 11:15 (+630 e +715), vendeu 13:00 em 188800 (+725). Acertou. A queda terminou em V, com volume na mínima e cruzamento da abertura: sinal distinto de "RSI baixo".

### Momentos de decisão
1. 09:30: fecha abaixo da mínima de ontem (186915 < 187215). Seguimento em 10:00/10:15 -> vender? Dava ~1400 pts.
2. 10:30: vela de reversão com volume; ficar fora até a confirmação.
3. 11:15-11:30: fecha acima do topo da manhã e cruza a abertura: comprar.
4. 13:00-13:45: topo da faixa, volume caindo: sair da compra, não segurar.

### Perguntas por momento
- M1: **P1** = `abaixo_com_volume` (volume 930k vs média ~650k = ~1,4x, marginal); **P8** = `seguiu` em 10:00/10:15: **vender**.
- M2: **P5** = `misto` (H1 descendo, M15 virando) e **P3** = `abaixo_leve`: **ficar fora**.
- M3: **P4** = sim (esteve -2345 = 0,64 ATRd abaixo da abertura e fechou 187960 > 187865 às 11:30): **entrar comprando**.
- M4: **P6** = não (perna ~0,93 ATRd); **P7** = sim a partir de ~13:45 (amplitude ~0,3 ATRd, volume 250-490k): **sair / não abrir novas**.

---

## 2026-09-02 (quarta, OOS, Jev -459: 5 vendas, 1 alvo, 4 stops)

### Retrospectiva
- Abertura 182045 (ontem 182330), ATRd 3296. **Tendência de alta forte**: 09:00-10:00 faixa 182535-183630 (~1100 pts, 0,33 ATRd). 10:15 vela de +1800 (volume 1,63M, ~2,3x a média), rompe a máxima de ontem (183670) fechando 184565; segue 10:30 (185680), 11:00 (187025), topo 188930 às 12:00 (+6180 da mínima das 10:00 = 1,9 ATRd). Depois lateral 187000-188500 até o fim.
- Melhor entrada: compra 10:15 (184565, limite no repique ~184300), saída ~12:15-12:30 (~188000). Realista ~3500 pts (R$700).
- Jev: **5 vendas contra a alta**, 4 stops (R$-180, -199, -230, -29) e 1 alvo (+179 já no topo). Vendeu cada vela mais alta por "esticado". O dia mostrava o contrário: 1,3 a 1,9 ATRd acima da abertura e H1 em alta.

### Momentos de decisão
1. 10:15: rompe a máxima de ontem com volume e sai da faixa da manhã: comprar.
2. 10:30/10:45: Jev vende, mas P3/P5/P8 dizem alta forte: não vender.
3. 11:15: preço a +1,5 ATRd da abertura, Jev vende de novo: só segurar a compra.
4. 12:30: perna de 1,9 ATRd, três velas sem nova máxima: sair da compra; vender aqui seria curto e sem tendência, melhor ficar fora.

### Perguntas por momento
- M1: **P2** = sim (faixa 3h ~1100 pts < 1 ATRd; vela 2045 pts vs ATR15 592 = 3,5x); **P1** = `acima_com_volume`: **entrar comprando**.
- M2: **P3** = `acima_forte` (10:45: 186355-182045 = 4310 = 1,3 ATRd), **P5** = `alta`, **P8** = `seguiu`: **não vender**.
- M3: **P9** = sim: **segurar sem alvo fixo**.
- M4: **P6** = sim: **sair da compra / apertar stop**; depois **P7** = sim (a partir de ~13:30): **ficar fora**.

---

## 2026-09-22 (terça, OOS, Jev +387: 4 compras, 3 alvos + 1 fim do pregão)

### Retrospectiva
- Abertura 187230 (ontem 187895, gap -665 = -0,17 ATRd), ATRd 3867. **Lateral com rompimento tardio**: mínima 186195 às 10:15, faixa 186200-187700 até 14:30 (~0,4 ATRd). 14:45 rompe para cima (fecha 188130, vela de 625 pts vs ATR15 387), 15:00 (188460), topo 189145 às 16:45, depois lateral.
- Melhor entrada: compra a 188130 (14:45), mantida até ~16:30 (~189000): +900 pts em uma operação; ou compras de faixa (186400-186600 -> 187200), ~700 pts. Realista ~1500 pts.
- Jev: 4 compras; 3 alvos pequenos na faixa (R$80, 95, 100) e uma às 15:00 (188130) mantida até o fim (R$112, +570 pts). Total 1935 pts. Lado certo, mas deixou ganho na mesa (alvos curtos; última sem trailing devolveu ~450 pts até 18:19).

### Momentos de decisão
1. 10:00-10:15: mínimas da manhã, volatilidade baixa: fora ou compra curta.
2. 11:45-14:30: faixa morta, volume 250-400k: ficar fora.
3. 14:45: rompe a faixa de 3h com o maior volume desde 11:00: comprar.
4. 16:45: topo 189145 e devolução: sair/apertar stop.

### Perguntas por momento
- M1: **P3** = `perto` (±0,25 ATRd da abertura) e **P5** = `misto`: **ficar fora**.
- M2: **P7** = sim (12:45-14:30 amplitude ~0,22 ATRd): **ficar fora**.
- M3: **P2** = sim (faixa 187045-187955 = 0,24 ATRd; fecha 188130 > 187955; amplitude 625 vs ATR15 387 = 1,6x); **P8** = `seguiu` às 15:00 (188460 > 188130): **comprar**.
- M4: **P6** = não (perna ~0,76 ATRd); **P7** = sim a partir de ~17:15: **sair antes do fim, não segurar até 18:19**.

---

## O que os cinco dias dizem (honesto)

- **Perdedores (D2, D4)**: dias de tendência com rompimento e volume; Jev operou contra (comprou queda, vendeu alta). P1, P2, P3, P5, P8, P9 apontam o lado certo ou mandam ficar fora nos dois.
- **Ganhadores (D1, D3, D5)**: D5 é continuação (lado certo, mas deixou correr pouco). D1 é venda de topo **depois da falha** do rompimento (P8 = `falhou`). D3 é compra da queda **depois** do V com cruzamento da abertura (P4). Os dois dias de "reversão" que o Jev ganhou têm sinal visível de falha/recuperação, não de "RSI extremo". Uma pergunta de RSI extremo sustentaria D1 e D3 mas destruiria D2 e D4: não a propus.
- P4 tem 1 dia só: é hipótese. P8 é a que separa D1 (falhou) dos demais (seguiu).
- Todas usam só o pacote (M15 até a vela fechada, diário anterior, H1). P1 e P7 precisam de média de volume das últimas 20 velas M15 (as 40 velas do pacote bastam). Nenhum campo novo é indispensável; ajudaria expor "ATR diário" já em múltiplos (distância da abertura em ATRd).
- Limite da amostra: 5 dias, selecionados por resultado do Jev; sem nulo nem OOS próprio. Tudo isso é leitura retrospectiva, não evidência.

---

# Tabela consolidada

"dias" = em quantos dos 5 dias a pergunta foi base de uma decisão.

| id | tipo | instructions (completo) | categorias/níveis | resposta-alvo | decisão que sustenta | geral/específica | dias |
|---|---|---|---|---|---|---|---|
| P1 `rompe_ontem` | choice | "Compare o fechamento da última vela M15 fechada com a máxima e a mínima do dia anterior (linha 'ontem: max ... min ...' do estado). Ela fechou além de alguma delas? Se sim, o volume da vela (coluna Volume) é pelo menos 1,5 vez a média do volume das últimas 20 velas M15 listadas? Responda só com o que as velas fechadas mostram. 'Nenhum rompimento' é uma resposta válida e comum." | `acima_com_volume`: fechou acima da máxima de ontem com volume >=1,5x; `abaixo_com_volume`: idem abaixo da mínima de ontem; `sem_volume`: fechou fora de ontem mas com volume menor; `nenhum`: dentro da faixa de ontem | `acima_com_volume` -> lado comprador; `abaixo_com_volume` -> lado vendedor; demais -> sem sinal | entrar a favor (só com seguimento, ver P8) / ficar fora | geral | 4 (D1, D2, D3, D4) |
| P2 `faixa_rompida` | noul | "Considere só as velas de hoje. Há pelo menos 13 velas M15 fechadas hoje? Se sim: a faixa (maior máxima menos menor mínima) das 12 velas anteriores à última é menor que 1 ATR diário, a última vela fechou fora dessa faixa e a amplitude dela (máxima menos mínima) é pelo menos 1,5 vez o ATR M15? Se faltarem velas, ou a vela não saiu da faixa, responda não." | P(sim) | sim -> o movimento começou; o lado é o do fechamento | entrar a favor do rompimento (limite, sem perseguir) | geral | 3 (D2, D4, D5) |
| P3 `desloc_abertura` | choice | "Onde está o último fechamento em relação à abertura do dia (linha 'Abertura do dia'), medido em ATR diário (linha 'ATR diário')? Calcule (fechamento - abertura) / ATR diário e escolha a faixa." | `acima_forte`: > +1,0; `acima_leve`: +0,25 a +1,0; `perto`: -0,25 a +0,25; `abaixo_leve`: -1,0 a -0,25; `abaixo_forte`: < -1,0 | `acima_forte` bloqueia venda; `abaixo_forte` bloqueia compra; `perto` -> sem tendência do dia | ficar fora do lado contrário ao dia | geral | 4 (D2, D3, D4, D5) |
| P4 `reconquista_abertura` | noul | "Hoje, o preço chegou a ficar pelo menos 0,5 ATR diário de um lado da abertura (linha 'Abertura do dia') e a última vela fechada fechou do outro lado dela? Responda sim só se o cruzamento aconteceu nas últimas 3 velas fechadas. Caso contrário, não." | P(sim) | sim -> recuperação da abertura | entrar a favor do lado reconquistado | específica (1 dia) | 1 (D3) |
| P5 `h1_direcao` | choice | "Olhe os H1 completos de hoje (últimas 3 horas fechadas): os fechamentos H1 vêm subindo, descendo ou sem direção? E a última vela M15 fechou do mesmo lado do fechamento H1 de 3 horas atrás? Só diga 'alta' ou 'baixa' se os dois concordam." | `alta`: H1 subindo e M15 acima do fechamento de 3 h atrás; `baixa`: o inverso; `misto`: não concordam ou menos de 3 H1 completos hoje | `alta`/`baixa` na direção da operação; `misto` -> sem sinal | entrar só a favor do H1 / ficar fora | geral | 4 (D2, D3, D4, D5) |
| P6 `perna_esgotada` | noul | "A perna atual (do último pivô de 8 velas M15 até a máxima, se subiu, ou a mínima, se caiu) andou mais de 1 ATR diário? E nas últimas 3 velas fechadas não houve nova máxima (perna de alta) nem nova mínima (perna de baixa)? Se uma das duas coisas não é verdade, responda não." | P(sim) | sim -> perna parou depois de longa extensão | sair da posição a favor / apertar o stop; não abrir nova entrada na mesma direção | geral | 3 (D1, D2, D4) |
| P7 `lateral_morta` | noul | "Nas últimas 8 velas M15 fechadas, a faixa total (maior máxima menos menor mínima) é menor que 0,5 ATR diário E o volume médio dessas 8 velas é menor que 70% do volume médio das velas de hoje até agora? Se sim, o mercado está parado. Se não, responda não." | P(sim) | sim -> mercado parado | ficar fora / não abrir; sair se estiver posicionado | geral | 5 (D1, D2, D3, D4, D5) |
| P8 `seguimento_rompimento` | choice | "Se nas últimas 3 velas fechadas houve uma vela que fechou além da máxima/mínima de ontem ou da faixa de 3 horas: nas duas velas seguintes, o fechamento ficou além do fechamento da vela de rompimento (seguiu), ou voltou para dentro/atrás dele (falhou)? Se não houve rompimento recente, responda `sem_rompimento`." | `seguiu`: seguimento confirmado; `falhou`: voltou; `sem_rompimento`: nenhum rompimento nas últimas 3 velas | `seguiu` -> a favor do rompimento; `falhou` -> contra; `sem_rompimento` -> sem sinal | entrar a favor / entrar contra o rompimento falho / ficar fora | geral | 5 (D1 falhou; D2, D3, D4, D5 seguiu) |
| P9 `tendencia_forte_sem_alvo` | noul | "O fechamento está a mais de 1 ATR diário da abertura, o H1 está na mesma direção, e nenhuma das últimas 6 velas M15 fechou contra essa direção por mais de 0,5 ATR M15 (diferença entre abertura e fechamento da vela)? Se sim, o dia é de tendência limpa." | P(sim) | sim -> tendência limpa | segurar a posição a favor sem alvo fixo, só com stop de trailing | geral (resposta 'não' nos dias sem tendência) | 2 (D2, D4); 'não' nos demais |
