# grupo_b — perguntas para o dia positivo (5 dias)

Dias: 2026-07-10 OOS (Jev −432), 2026-06-25 OOS (+362), 2026-02-03 OOS (−400), 2026-06-26 OOS (+354), 2022-09-06 IS (−395).
Fontes: `sessoes_dec/<periodo>/<data>.json` (barras, trades), `mercado.py` (abertura, gap, ATR diário, dias anteriores). Nada de API.

Convenções: "vela HH:MM" = vela M15 que ABRE nesse horário (fecha 15 min depois; o Jev decide no fechamento e a ordem limitada vale na vela seguinte). `ATRd` = ATR diário (14, até ontem, do pacote). `c-ab` = último fechamento menos abertura do dia, em ATRd. Pontos são brutos de custo, salvo quando disse "liq". 1 contrato = R$ 0,20/pt. Os ganhos "realistas" abaixo são estimativas feitas olhando as barras com o futuro à vista, com as regras do motor (limite, stop a mercado, 10 pts de custo); não foram simuladas no motor.

As 7 perguntas novas (`gb_01` a `gb_07`) têm o texto completo na tabela consolidada, no fim. Em cada dia abaixo cito só id, resposta-alvo e decisão. Perguntas que JÁ existem nas 54 e continuam úteis: `b5_q39`/`d9` (fase do pregão, tempo restante), `a1` (sem alvo), `stop` (pivô), `g_acao`.


---

## 2026-07-10 (sexta, OOS) — Jev −R$ 432 (5 vendas, 1 acerto)

**Tipo de dia.** Tendência de alta limpa. Gap +515 (0,19 ATRd; ATRd 2766) que nunca foi preenchido (mínima do dia = abertura 175.905). Abre 175.905, sobe a 180.605 no fim (c-ab +1,70 ATRd), amplitude 1,72 ATRd. Mínimas M15 ascendentes o dia todo; fechamento acima da média de 20 velas em 12/12 velas durante o dia inteiro. A 1ª vela (09:00) contém o leilão: abre 175.905, fecha 177.630.

**Melhores entradas/saídas.** Compra depois do recuo curto: vela 10:45 (fecha 178.505, fundo 177.825 acima do fundo de 09:30 = 177.475); stop no pivô 177.475 (ou 1,5 ATR M15 ≈ 400 pts, que ali seria pego pela mínima 178.005 de 11:30, então o pivô é melhor); sem alvo, trailing em pivôs. O trailing por pivô sairia entre ~179.300 e o fim (~180.600): +1.000 a +2.000 pts liq por contrato (R$ 200–400). Reentrada em rompimento de máxima (vela 13:45, fecha 179.375 > máxima 179.300; vela 15:00 fecha 179.810; vela 17:00 fecha 180.260) é possível, mas a posição já aberta fazia o trabalho.

**O que o Jev fez e por quê errou.** Vendeu 5 vezes num dia de alta dirigida:
1. vela 09:00 (decisão 09:15, venda 177.630): vendeu o topo do leilão. Stop −270 liq.
2. vela 09:45 (venda 178.315): acertou (+430) porque a vela tinha pavio de 985 pts, mas a tendência seguiu.
3. vela 10:15 (venda 178.020): **−1.295**; segurou 3h10 contra a tendência até o stop.
4. vela 13:30 (venda 179.270, a 30 pts da máxima do dia): −780.
5. vela 17:00 (venda 180.260, logo após novo máximo): −245.
Total −R$ 432. O Jev respondeu "compra" em `b0_q9` (0,92) e "tendência_alta" em `b1_q5` (0,81) já na primeira vela, mas o `acao` do modelo foi "vender" (a decisão não obedece às respostas de contexto): exatamente o erro do "compra a queda e vende a alta" descrito nas lições.

**Momentos de decisão.**
- M1: vela 09:00 (hora do primeiro fechamento). Não vender o leilão. Decisão: ficar fora até ver o 1º recuo.
- M2: vela 10:15 e 10:30. Preço acima da abertura por 0,76 ATRd, sem perder o fundo de 09:30. Decisão: ficar fora de venda; comprar no recuo retomado (vela 10:45).
- M3: vela 13:30/13:45. Preço rompe a máxima do dia. Decisão: nunca vender; se comprado, segurar.
- M4: vela 17:00. Novo máximo do dia. Decisão: nunca vender; se comprado, manter e subir o stop ao pivô.

**Perguntas por momento (resposta-alvo → decisão).**
- M1 `gb_01` (tipo do dia): **alta_dirigida** (c-ab +0,62, amplitude 0,64 ATRd, eficiência 0,97 — mas atenção: 1ª vela com leilão). → só comprar ou ficar fora; vender proibido. `gb_05` (gap): **a_favor_sem_preencher** (+515 > 0,15 ATRd). → mesmo sentido.
- M2 `gb_01`: **alta_dirigida** (c-ab +0,76; amplitude 1,23 ATRd; eficiência 0,62, no limite). → vender proibido. `gb_03` (pullback retomado): em 10:45 **sim** (fecha em alta 178.505, fundo 177.825 > 177.475) → entrar comprando, stop no pivô.
- M3 `gb_02` (rompimento do extremo do dia): em 13:45 **rompeu_alta** (179.375 > 179.300) → entrar/segurar comprado; não vender.
- M4 `gb_02`: **rompeu_alta** (180.260 > 179.955). `gb_06` (gestão, se comprado): **sim** (último fundo 179.905 intacto) → manter.

Falsos positivos de `gb_04` neste dia: nenhum (devolução máxima do deslocamento ≈ 25%).

---

## 2026-06-25 (quinta, OOS) — Jev +R$ 362 (3 vendas, 3 alvos)

**Tipo de dia.** Faixa ampla com idas e voltas: abre 174.315, fecha 174.760 (c-ab +0,15 ATRd; ATRd 2922); amplitude do dia 0,86 ATRd. Gap +100 (0,03 ATRd: irrelevante). Três ondas: sobe a 175.560 (vela 10:00), cai a 173.860 (vela 10:30), sobe a 176.275 (vela 11:30), e depois devolve tudo até 174.760. Tarde morta (volume 0,3–0,9 da média de 10 velas).

**Melhores entradas/saídas.** Com as regras de continuação, o dia dá pouco: entrar a favor nas quebras (vela 10:00 ou 11:15) leva stop (11:15: compra a 175.900; 11:45 tem mínima 175.385 e o stop de 1,5 ATR M15 ≈ 380 pts fica em 175.520). O ganho real foi de reversão em topos da faixa, que o Jev pegou: vendas em 175.475 (+490 liq), 174.825 (+570), 175.900 (+750). Dá para pegar também uma compra no fundo defendido: vela 11:00 (fecha 175.120, mínima do dia 173.755 testada em 173.860, fechamento a 71% da amplitude) com alvo 1,5 ATR M15 (≈ +540, atingido na vela 11:15). Realista: +500 a +1.800 pts liq. A parte acima de ~+500 depende de reversão, o que as lições dizem que não generaliza.

**O que o Jev fez e por quê acertou.** Acertou 3/3 por reversão em dia de faixa, não por tendência. É o único dos meus dias em que a venda contra o movimento recente funciona; foi sorte do regime, e o dia seguinte (06-26) fez o oposto.

**Momentos de decisão.**
- M1: vela 10:00 (fecha 175.475, perto da máxima do dia 175.560 e abaixo da vela anterior em volume). Decisão do Jev: vender (+490). O que dá para justificar: dia sem direção e preço no topo da faixa.
- M2: vela 10:15/10:30. Fundo do dia testado (173.860). Decisão possível: não vender mais; comprar o fundo defendido na vela 11:00.
- M3: vela 11:15 (fecha 175.900, topo da faixa; 0,54 ATRd acima da abertura). Decisão do Jev: vender (+750 até 14:20). Decisão neutra: ficar fora, porque `gb_01` diz alta_dirigida (eficiência 0,71) e daria um falso positivo (bloqueia um acerto do Jev).
- M4: vela 14:15–15:00. Preço devolve a alta da manhã. Decisão: se vendido, segurar; entrada nova: fora.

**Perguntas por momento.**
- M1 `gb_01`: vela 10:00: **alta_dirigida** (eficiência 0,65; c-ab +0,40) → bloquearia a venda de 10:15 (que ganhou +490). Vela 10:15: **sem_direcao** (c-ab +0,17) → ficar fora (consistente, mas sem lucro). `gb_07` (extremo defendido) em 10:00: **nenhum** → fora.
- M2 `gb_07`: vela 11:00: **fundo_defendido** (mínima 173.860 a 105 pts da mínima do dia 173.755, ≤ 0,35 ATR M15 = 125; fechamento no alto da vela). → entrar comprando com alvo 1,5 ATR M15, só se `gb_01` ≠ baixa_dirigida (aqui sem_direcao).
- M3 `gb_01` em 11:15: **alta_dirigida** (eficiência 0,71) mas `gb_04` nas velas seguintes: vela 11:45 devolução 39%; vela 15:00 devolução 60% → **sim** → "o dia perdeu a direção da manhã" → sair/apertar stop de compras; não abrir novas na direção da manhã.
- Observação de sanidade: **neste dia `gb_01` produz erro (bloqueia 2 dos 3 acertos do Jev)**. Em compensação, o motor de continuação não ganha nada com ele; o dia positivo só sai com `gb_07` (compra no fundo defendido) ou com a reversão do Jev.

---

## 2026-02-03 (terça, OOS) — Jev −R$ 400 (6 vendas, 2 acertos)

**Tipo de dia.** Tendência de alta de manhã, devolução à tarde, rebote no fim. Gap +700 (0,18 ATRd; ATRd 3932), nunca preenchido (mínima do dia 184.490 > fechamento anterior 183.800). Sobe de 184.500 a 188.315 (vela 11:45), amplitude 0,97 ATRd. Depois cai a 185.700 (vela 15:15, devolução de ~62% da alta máxima) e fecha 186.355.

**Melhores entradas/saídas.** Compra na vela 10:30 (fecha 186.370, acima do fundo de 185.845) ou na 10:15 (fecha 186.010); stop pivô ≈ 185.155 (grande, ~1.200 pts) ou 1,5 ATR M15 ≈ 510 (185.860; a mínima 185.845 da 10:30 o tocaria; funciona se a entrada for a limite de 186.370 com stop 185.860 depois que a vela 10:30 fechou). Trailing em pivôs sai em ~187.100–187.300 (+900 a +1.300 pts liq). Segunda perna: venda quando o fundo de 13:45 (186.805) quebra, vela 14:00 (fecha 186.465), alvo 2 ATR M15 ≈ 800 → ~185.700 (+700). Total realista ≈ +1.600 a +2.000 pts liq (R$ 320–400), contra −R$ 400 do Jev.

**O que o Jev fez.** Vendeu 6 vezes em dia de alta: 09:15 (−595), 09:30 (+415), 10:15 (−785), 10:45 (−885), 11:30 (+615, único acerto real: vendeu exatamente o topo do dia em 187.985, que reverteu 12:00), 14:30 (−765, vendido na mínima do movimento, depois rebote). Mesmo padrão do 07-10: respondeu "tendência_alta"/"compra" (`b1_q5` 0,79, `b0_q9` 0,91) e vendeu.

**Momentos de decisão.**
- M1: vela 09:30/10:15, preço acima da abertura, mínimas ascendentes. Decisão: ficar fora de venda; comprar o recuo retomado.
- M2: vela 10:45 e 11:30, novos máximos do dia. Decisão: não vender. (A venda de 11:30 acertou; cuidado: é o único acerto de contra-tendência do dia.)
- M3: vela 12:00–14:00, devolução do dia. Decisão: sair da compra ou apertar o stop ao pivô; entrada nova só após quebra de fundo de H1.
- M4: vela 14:30, preço 62% abaixo da alta máxima, devolução já grande. Decisão: não vender no fundo do movimento; ficar fora.

**Perguntas por momento.**
- M1 `gb_01`: vela 09:15 **sem_direcao** (c-ab +0,19 < 0,25) → ficar fora (evita −595); vela 09:30 **alta_dirigida** (c-ab +0,30, eficiência 0,77) → só comprar; velas 10:15 e 10:45 **alta_dirigida** (0,84; 0,99). `gb_05` (gap): **a_favor_sem_preencher** → só a favor. `gb_03` (pullback): vela 10:30 **sim** (fecha 186.370 > abertura da própria vela, fundo 185.845 > 185.155... atenção: perdeu o fundo de 09:30 = 185.220? 185.155 < 185.220 sim perdeu; com o critério estrito "sem perder o último fundo do dia" dá **não** em 10:15 e **sim** em 10:30 (fundo a considerar: 185.845 com fundo anterior 185.155) → entrar comprando.
- M2 `gb_02`: vela 10:45 **rompeu_alta** (187.105 > 186.590); vela 11:30 **rompeu_alta** (187.985 > 187.620). → não vender (isso também mataria o único acerto do dia, mas evita −885 e −785).
- M3 `gb_04` (devolução > 50%): vela 14:00 devolução 48% → **não** (limite); vela 14:30 **sim** (62%) → sair/apertar a compra.
- M4 `gb_01` em 14:30: **sem_direcao** (c-ab +0,36, eficiência 0,37 < 0,6) → ficar fora (evita −765).

---

## 2026-06-26 (sexta, OOS) — Jev +R$ 354 (1 compra mantida do meio-dia ao fim)

**Tipo de dia.** Gap de baixa −750 (−0,26 ATRd; ATRd 2916) que o dia preenche, depois alta de continuação. 1ª vela: leilão sobe a 175.140 e abre fechando 175.085; cai a 173.765 (mínima do dia, vela 10:15 e 10:45 testam 173.795/173.835), vira em 10:45 e sobe quase sem recuo até 176.920 (vela 15:15). Amplitude 1,08 ATRd. Meio-dia à tarde: faixa de 176.200–176.790.

**Melhores entradas/saídas.** Compra defendendo o duplo fundo: vela 10:45 (fecha 174.550, a 94% da amplitude, mínima 173.835 a ~60 pts da mínima do dia), stop no pivô 173.790, sem alvo, trailing por pivôs. Máximo possível: 176.920; um stop de pivô real sai em ~176.300 (o Jev saiu em 176.330 na vela 16:00: +1.770 liq). Não há mais lucro realista depois do meio-dia: o preço fica dentro de uma faixa estreita de 600 pts.

**O que o Jev fez.** Ficou fora até 10:45 (`reversao_do_gap` p=0,72 no 1º ponto, `acao`=fora), comprou na vela 10:45 e segurou até o stop por pivô. É o dia em que a decisão do Jev foi simplesmente boa: uma entrada, nenhum erro, trailing por estrutura. Acertou por deixar correr (como a escada v4.1), não por reversão do gap em si.

**Momentos de decisão.**
- M1: velas 09:00–10:30, preço sem direção, queda com fundo testado. Decisão: ficar fora (e não vender o fundo).
- M2: vela 10:45. Fundo duplo defendido, fechamento forte. Decisão: entrar comprando, stop no pivô, sem alvo.
- M3: velas 12:15–15:15. Faixa estreita, posição a favor. Decisão: segurar; stop sobe aos pivôs.
- M4: vela 15:30–16:00. Perde o pivô. Decisão: sair (o stop fez).

**Perguntas por momento.**
- M1 `gb_01`: velas 09:15–10:30 **sem_direcao** (c-ab entre +0,37 e −0,01, eficiência < 0,6 na maior parte: 0,37/0,62=0,60 em 09:00 mas c-ab cai) → ficar fora. `gb_05` (gap): gap de baixa −0,26 ATRd **a_favor_sem_preencher** até a vela 11:15 (o preço não volta ao fechamento anterior 174.760); a partir daí **preenchido** (n=1, sem viés próprio).
- M2 `gb_07`: vela 10:45 **fundo_defendido** (2 toques ≤ 0,35 ATR M15 = 107 pts da mínima do dia 173.765: 173.795 e 173.835; fechamento 94% da amplitude) → entrar comprando, stop no pivô, `a1` sem alvo.
- M3 `gb_06` (gestão): vela 12:15–15:15 **sim** (nenhum fechamento abaixo do último fundo M15 após a entrada) → manter. `gb_02` em 12:15: **rompeu_alta** (176.305 > 176.070): serve como entrada tardia (±0 pts liq em simulação aproximada, porque a faixa de 600 pts a seguir não paga), não como a razão do lucro.
- M4 `gb_06`: vela 15:45 **não** (fechamento 176.415 e 176.430 abaixo do pivô anterior 176.540) → apertar/sair.
- Observação: `gb_01` sozinha **não** gera a compra de 10:45 (c-ab +0,19 → sem_direcao); só `gb_07` gera. Em 11:15 `gb_01` já diz alta_dirigida (eficiência 0,69) e a entrada atrasada ainda rende ≈ +1.000 pts.

---

## 2022-09-06 (terça, IS) — Jev −R$ 395 (6 compras, 1 acerto)

**Tipo de dia.** Tendência de baixa na manhã e lateral à tarde. Gap −220 (0,11 ATRd; ATRd 2066): irrelevante; ontem tinha subido +1.400 e fechado a 74% da amplitude, mas hoje abre 113.350 e cai de forma contínua até 110.660 (vela 11:00, −2.690 = 1,3 ATRd). A partir das 11:30 o preço fica entre 110.580 e 111.395 (amplitude 0,35 ATRd em 6 horas). Fecha 110.725 (c-ab −1,27).

**Melhores entradas/saídas.** Venda na vela 09:45 (fecha 112.460, topos descendentes: 113.070 → 112.715 → 112.625) ou, melhor, na quebra da vela 10:00 (fecha 112.070 < mínima 112.430); stop 1,5 ATR M15 ≈ 255 (acima de 112.715) é seguro até a vela 10:00; sem alvo, trailing por pivôs: sai em ~111.200 (repique de 11:15–11:30). Realista: +900 a +1.300 pts liq por contrato (R$ 180–260). Depois das 11:30 não há lucro realista: ficar fora.

**O que o Jev fez.** Comprou 6 vezes a queda: 09:30 (−545), 10:30 (−415), 10:45 (−470), 11:45 (−515, comprou o fundo de um dia que ainda não tinha ido a lugar nenhum), 16:00 (+265), 16:45 (−295). O erro clássico das lições: vende alta e compra queda. Respondeu "tendência_baixa" (`b1_q5` 0,68) e `b0_q9`=venda (0,78) no primeiro ponto, e mesmo assim comprou.

**Momentos de decisão.**
- M1: vela 09:15–09:45, queda ordenada. Decisão: ficar fora de compra; vender no repique curto.
- M2: vela 10:00–10:45, quebras sucessivas de mínima. Decisão: não comprar nenhuma delas; vender se ainda não vendido.
- M3: vela 11:30–11:45, repique pequeno a 111.255, depois lateral. Decisão: fora (ou, se vendido, apertar o stop ao pivô).
- M4: velas 14:00–16:45, tarde lateral, 5 compras do Jev. Decisão: fora.

**Perguntas por momento.**
- M1 `gb_01`: vela 09:15 **baixa_dirigida** (c-ab −0,33, eficiência 0,92) → só vender; vela 09:30: baixa (−0,41/0,46=0,89). Compra proibida.
- M2 `gb_02`: vela 10:00 **rompeu_baixa** (112.070 < 112.430), vela 10:15 **rompeu_baixa**, 10:30 **rompeu_baixa**, 10:45 **rompeu_baixa** (cada vez um fechamento abaixo da mínima do dia até a vela anterior) → vender/segurar vendido; não comprar.
- M3 `gb_01` em 11:30: **baixa_dirigida** ainda (c-ab −1,06, eficiência 0,81); `gb_04` (devolução do deslocamento máximo): 22% → **não** → manter vendido; sem entradas novas (o dia saiu da região de preço de entrada).
- M4 `gb_01` em 15:45: **baixa_dirigida** (−1,26/1,35 = 0,93) → comprar proibido (evita −295 e a compra de 16:00 que só ganhou +265 por sorte). `gb_07` na vela 15:00: mínima 110.795 está a 215 pts da mínima do dia (110.580), mais que 0,35 ATR M15 (~86): **nenhum**. Além disso `gb_07` só vale se `gb_01` ≠ baixa_dirigida, e aqui o veto de `gb_01` prevalece.

# Tabela consolidada

| id | tipo | instructions (completo) | categorias / níveis | resposta-alvo | decisão que sustenta | geral/específica | dias em que decidiu (de 5) |
|---|---|---|---|---|---|---|---|
| `gb_01` | choice | "Desde a abertura do dia até o último fechamento M15, o deslocamento líquido (fechamento atual menos abertura do dia) é pelo menos 0,25 ATR diário e pelo menos 60% da amplitude do dia (máxima menos mínima desde a abertura)? Se for para cima, o dia é de alta dirigida; se for para baixo, de baixa dirigida; se não cumprir as duas condições, o dia ainda não tem direção. Responda só com o que as velas fechadas do estado mostram." | `alta_dirigida`: deslocamento para cima nas duas condições; `baixa_dirigida`: para baixo nas duas condições; `sem_direcao`: não cumpre uma das condições (deslocamento pequeno ou o dia andou nos dois sentidos) | 07-10: alta_dirigida (10:15, 13:30, 17:00); 02-03: sem_direcao em 09:15 e 14:30, alta_dirigida em 09:30–11:30; 2022: baixa_dirigida em 09:15–16:30; 06-25: alta_dirigida em 10:00 e 11:15 (**falso positivo**), sem_direcao em 10:15; 06-26: sem_direcao até 11:00, alta_dirigida a partir de 11:15 | alta_dirigida: só entrar comprando ou ficar fora; baixa_dirigida: só vender ou fora; sem_direcao: ficar fora (sem posição nova a favor) | **geral** nos 4 dias de tendência (07-10, 02-03, 2022, 06-26 tarde). **Específica de regime / falha** no 06-25 (dia de faixa em que bloqueia 2 dos 3 acertos do Jev) | 5/5 |
| `gb_02` | choice | "A vela M15 que acabou de fechar fechou além da máxima (ou da mínima) do dia até a vela anterior? Compare o fechamento da última vela com a máxima do dia e com a mínima do dia, ambas calculadas só até a vela anterior à última. Responda só com o que as velas fechadas do estado mostram." | `rompeu_alta`: fechamento acima da máxima do dia até a vela anterior; `rompeu_baixa`: fechamento abaixo da mínima do dia até a vela anterior; `nenhum`: fechou dentro da faixa do dia | 07-10: rompeu_alta em 09:45, 13:45, 15:00, 17:00; 02-03: rompeu_alta em 10:45, 11:30; 2022: rompeu_baixa em 10:00, 10:15, 10:30, 10:45; 06-26: rompeu_alta em 12:15; 06-25: nenhum nos momentos de venda do Jev, rompeu_alta em 10:00 e 11:15 | rompeu_alta: entrar comprando ou segurar comprado, e não vender; rompeu_baixa: entrar vendendo ou segurar vendido, e não comprar; nenhum: sem informação nova | **geral** (continuação; a lição de que o WIN M15 continua). Ressalva: tira também acertos de contra-tendência (02-03 vela 11:30, 06-25 vela 11:15) | 4/5 (07-10, 02-03, 2022, 06-26; no 06-25 só como sinal que o Jev ignora) |
| `gb_03` | noul | "Numa tendência dirigida do dia (alta ou baixa), o preço recuou contra ela por 1 a 3 velas M15 e a última vela fechou de volta no sentido do dia (fechamento acima da própria abertura numa alta; abaixo numa baixa), sem perder o último fundo (alta) ou topo (baixa) já formado hoje? Responda só com o que as velas fechadas do estado mostram." | P(sim) | sim em 07-10 (vela 10:45) e 02-03 (vela 10:30, com a ressalva do fundo 185.155 já perdido na 10:15); não nas demais velas de teste | sim: entrar a favor do dia com ordem limitada no fechamento, stop no pivô, sem alvo; não: ficar fora ou segurar | **geral** (é a entrada da escada v4.1 em linguagem de pergunta) | 2/5 com certeza (07-10, 02-03); 2022 e 06-26 sem exemplo limpo |
| `gb_04` | noul | "O preço devolveu mais de 50% do deslocamento máximo que o dia fez a partir da abertura? Meça o deslocamento máximo como a distância entre a abertura e o extremo do dia (máxima numa alta, mínima numa baixa); devolveu mais de 50% se o último fechamento voltou mais da metade desse caminho em direção à abertura. Responda só com o que as velas fechadas do estado mostram." | P(sim) | sim em 02-03 (a partir das 14:30, 62%) e 06-25 (vela 15:00, 60%); não em 07-10 (máx 25%), 06-26 (máx 25%), 2022 (máx 34%) | sim: sair ou apertar o stop de posição aberta na direção da manhã; não abrir novas posições na direção da manhã; não: manter a posição | **geral** (cai nos dias de tendência que viram, e é inerte nos que seguem) | 2/5 decisivo (02-03, 06-25); 3/5 serve como "não" (inerte) |
| `gb_05` | choice | "Existe gap de abertura relevante hoje (diferença entre a abertura do dia e o fechamento de ontem de pelo menos 0,15 ATR diário)? Se sim, o preço já voltou a tocar o fechamento de ontem durante o dia? Responda só com o que as velas fechadas do estado mostram." | `a_favor_sem_preencher`: gap relevante e o preço nunca voltou ao fechamento de ontem (o dia segue no sentido do gap); `preenchido`: gap relevante e o preço já voltou ao fechamento de ontem; `irrelevante`: gap < 0,15 ATR diário | 07-10: a_favor_sem_preencher; 02-03: a_favor_sem_preencher; 06-26: gap −0,26 ATRd, **ainda não preenchido** (agrupado em a_favor_sem_preencher até a vela 11:15; preenchido a partir daí); 06-25 e 2022: irrelevante | a_favor_sem_preencher: só entrar no sentido do gap (reforça `gb_01`); irrelevante: sem viés; preenchido: sem viés próprio, depende de `gb_01` | **geral** em 3/5 dias; evidência fraca para "preenchido" (n=1 em 06-26) | 3/5 (07-10, 02-03, 06-26) |
| `gb_06` | noul (gestão, com posição) | "Para a posição aberta, o último fundo M15 (compra) ou topo M15 (venda) formado depois da entrada continua sem ser perdido por nenhum fechamento, e o preço fez novo extremo a favor nas últimas 8 velas M15 ou está a menos de 1 ATR M15 dele? Responda só com o que as velas fechadas do estado mostram." | P(sim) | sim em 06-26 (12:15–15:15) e em 07-10 se comprado (10:45–18:15); não em 06-26 vela 15:45 (fechamentos 176.415 e 176.430 abaixo do pivô 176.540) | sim: manter, sem alvo (`g_acao` = manter) ou stop no pivô; não: apertar o stop ao pivô ou zerar | **geral** (é o mecanismo "deixar correr, sair quando a estrutura quebra" da escada) | 2/5 (06-26, 07-10) com posição; 02-03 manhã também (compra hipotética) |
| `gb_07` | choice | "A mínima (ou máxima) do dia foi testada pelo menos 2 vezes, em velas M15 diferentes, a menos de 0,35 ATR M15 de distância dela, sem nenhum fechamento além dela, e a última vela fechou afastando-se do extremo (fechamento na metade oposta da própria amplitude, a pelo menos 60% dela)? Responda só com o que as velas fechadas do estado mostram." | `fundo_defendido`: mínima do dia testada 2x ou mais, sem fechar abaixo, e a última vela fechou subindo longe dela; `topo_defendido`: o mesmo na máxima do dia, fechando longe para baixo; `nenhum`: não aconteceu | 06-26: fundo_defendido na vela 10:45 (173.795 e 173.835 vs mínima 173.765, fechamento 94% da amplitude); 06-25: fundo_defendido na vela 11:00 (mínima 173.860 vs 173.755); 07-10, 02-03, 2022 (09:15–10:45): nenhum | fundo_defendido: entrar comprando (alvo 1,5 ATR M15 no dia de faixa; stop no pivô; sem alvo se virar dia dirigido); topo_defendido: entrar vendendo; **só vale se `gb_01` ≠ baixa_dirigida (para compra) / ≠ alta_dirigida (para venda)** | **específica** (2/5, ambos dias de faixa; contradiz a lição "continuação", portanto condicionada a `gb_01`); em 2022 às 15:00 daria sinal marginal que `gb_01` vetaria | 2/5 (06-25, 06-26) |

## Limites do que foi feito (para quem consolidar)

- **Eficiência 0,6 e ATR 0,25 em `gb_01`** são limiares escolhidos olhando os 5 dias; falham em 06-25 (dia de faixa: eficiência 0,65 em 10:00 e 0,71 em 11:15, dois falsos positivos). Precisa ser testada nos dias de treino dos outros grupos e na base inteira.
- O **06-25 não tem solução por continuação**: o lucro do Jev veio de reversão num dia de faixa. A única pergunta que o captura (`gb_07`) é específica. Não generalizar.
- O **06-26** só rende o lucro do Jev com `gb_07` (entrada 10:45) ou com `gb_01` em 11:15 (entrada atrasada, ~+1.000 pts); `gb_02` (12:15) dá ≈ 0.
- Nenhum campo novo no pacote é necessário: tudo sai de abertura, máx, mín, último fechamento, fechamento de ontem, ATR diário e ATR M15, que já estão em `montar_pacote`. A máxima e a mínima "do dia até a vela anterior" (`gb_02`) e o "deslocamento máximo" (`gb_04`) exigem o modelo ler as velas M15 de hoje; elas estão no pacote.
- Valores de reta (ganhos realistas) são estimativas manuais, não simulação do motor.
