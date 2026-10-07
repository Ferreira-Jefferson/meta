# Frente N — pré-registro (N1, 2026-10-06)

Uma candidata, **RDT — Recuo no Dia de Tendência**. A segunda vaga fica vazia de propósito: as outras quatro direções exploradas no DEV morreram lá (seção 3), e preencher a vaga com a menos ruim delas seria escolher pelo DEV o que o próprio DEV refutou.

Dado: WIN$N M1 cru do MT5 (`data/comparativo_win_2026/m1_WIN$N_2022_2025.parquet`, 0 barras fora da grade de 5 pts), interface `n_nova/dados_dev.py`. Toda a exploração usou só o bloco DEV (2022-01-03 → 2024-06-28, 622 pregões). Do VAL só se conferiu que o dado existe (315 pregões).

---

## 1. Candidata RDT

### Hipótese e mecanismo
Às 10:30 o WIN às vezes já declarou o lado do dia: o preço está a ≥ 0,3 ATR diário da abertura e não voltou a cruzá-la. Nesses dias sobra uma deriva pequena a favor até o fim do pregão. No DEV, +0,071 ATR em 115 dias (ep 0,050), positiva nos três anos. Nos outros dias a deriva é zero: −0,006 ATR em 504 dias. Sozinha, essa deriva paga pouco e pede um stop largo, o da linha da abertura, com mediana de R$209 no DEV. Com esse stop, R$1.000 quebram no DEV (caixa mínimo −R$787).

A RDT mantém o lado e o stop da linha da abertura e muda só o **preço de entrada**. Em vez de entrar às 10:30, deixa uma ordem-limite no meio do caminho entre a abertura e o preço das 10:30, o recuo fundo. Isso traz dois efeitos.

- **Stop menor.** A distância até a linha cai à metade (mediana de R$103 no DEV), e a operação continua a favor do lado do dia. É o "perder de colherinha" do dono, porque o lucro segue sem alvo até o fim do pregão.
- **Preço melhor.** O preço melhora em 0,5 × deslocamento. Isso compensa a seleção adversa: os dias que enchem o recuo são, em média, piores para quem entrou às 10:30.

### Conceitos de origem
- **Regime.** Vem do WinDeslocamentoMatinal: o estado das 10:30 como regime do dia, uma das ideias do dono.
- **Entrada.** Vem da família retângulo e limite (WinRetanguloEma34): ordem-limite parada num nível de estrutura, esperando o preço voltar.
- **Saída.** Vem da família tendência: sem alvo, segura até o fim, porque a memória do Deslocamento mostra que qualquer alvo corta os dias de tendência.
- **Achado independente.** Em `win_correcao_multitf`, "ordem-limite no recuo de 40–50% de uma pernada bate o nulo no IS e no OOS". Recuos rasos (10–30%) davam nulo.

### Por que não é algo já refutado
| refutado | diferença |
|---|---|
| Deslocamento + recuo na EMA20 M5 (52–64 fills, piorou) | era um recuo raso até uma média que anda com o preço, com prazo de 15 min. Aqui o recuo é fundo, até um nível fixo da estrutura do dia (fração do deslocamento), válido por horas, com o stop na mesma linha da abertura |
| Deslocamento + alvo em R ou alvo que se aproxima | a RDT não tem alvo; a saída é a mesma do Deslocamento (zera) |
| Deslocamento + filtros de média móvel | a RDT não tem filtro de média nenhum |
| fade contra a abertura às 11:00 / retângulo que segura até 18:20 (WdoRet) | a RDT opera a favor do lado do dia e não aposta em reversão |
| "dias sem cruzar a abertura" como fato isolado | a RDT não usa isso como previsão de direção sozinha: é o regime já pré-registrado do Deslocamento (+0,10 ATR, z 1–2 em 5 anos) |

### Regras exatas
Valem para todo bloco, com horário do servidor, 1 contrato e 1 operação por dia.
1. **Abertura O** = abertura da 1ª M1 do pregão. **ATRd** = média simples do True Range das 14 D1 fechadas. As D1 são montadas das M1 da série ajustada por diferença no dia do vencimento (a quarta mais próxima do dia 15 dos meses pares), o que tira o degrau de rolagem do WIN$N. A implementação está em `explora_lib.m1_ajustada`.
2. **Decisão às 10:30**, no 1º tick da M1 das 10:30, usando só M1 fechadas (a última é a das 10:29). Desl = (fechamento da M1 10:29 − O)/ATRd.
   - Sinal de compra: Desl ≥ **k** e nenhuma M1 fechada desde a abertura com fechamento < O − 0,05·ATRd.
   - Sinal de venda: o espelho.
   - Sem sinal, o dia fica em branco.
3. **Entrada.** Ordem-limite a favor, no preço P = O + **f**·(c₁₀:₂₉ − O), arredondado à grade de 5. A ordem é enviada às 10:30, vale até **ate** e é cancelada se não encher. A execução segue o Testador: enche quando o `last` toca, no preço do limite, a partir do tick seguinte ao envio.
4. **Stop**, a mercado e controlado pelo EA desde o tick do preenchimento: linha = O − 0,05·ATRd na compra, O + 0,05·ATRd na venda, na grade. Dispara quando o `last` toca ou atravessa e executa no `last` desse tick. O stop não se move.
5. **Sem alvo.** A posição é zerada a mercado no 1º tick ≥ **17:50**. O horário é fixo em todos os blocos, porque em 2022 e 2023 o pregão termina às 17:54 em parte do ano.
6. Não há teto de stop por % do caixa. Com f ≤ 0,75 o stop do DEV ficou em mediana de R$58 a R$156. Se o caixa < margem, não opera (regra geral do Testador).

### Parâmetros e grade do DEV (12 células, explorada só no DEV)
| eixo | valores |
|---|---|
| f (fração do caminho abertura → 10:30) | 0,25 · 0,50 · 0,75 |
| ate (validade da limite) | 12:00 · 14:00 |
| k (deslocamento mínimo, ATRd) | 0,30 · 0,40 |

Fixos (não entram na busca): decisão às 10:30, folga da linha de 0,05 ATRd, ATR de 14 D1, zeragem às 17:50, sem alvo, 1 contrato.

**Regra de escolha da célula que congela**, decidida antes de rodar a grade:
- Entre as células com líquido do DEV (com R$2/op) > 0, cujos vizinhos em f e em ate (mesmo k) também têm líquido > 0, e cujo caixa mínimo partindo de R$1.000 fica ≥ R$500, vence a de maior lucro/DD no DEV.
- Empate: vence o menor stop mediano.
- Se nenhuma célula cumpre as três condições, a RDT é refutada no DEV e não vai ao VAL.

### Controles
1. **Controle aleatório**, com mesma frequência e mesmo horário, em 200 sorteios por bloco. Cada sorteio:
   - escolhe, em cada mês, o mesmo número de pregões que a RDT sinalizou naquele mês, entre todos os pregões do mês;
   - sorteia o lado;
   - aplica a mesma geometria em ATR: limite a (1−f)·d ATRd contra o lado a partir do fechamento das 10:29, e stop (f·d + 0,05) ATRd além do limite. O d vem de um dia de sinal real sorteado, o que preserva a distribuição de stops;
   - usa a mesma validade e a mesma zeragem.

   A medida é o percentil do líquido da RDT contra os 200 sorteios.
2. **Lado invertido**, descritivo: os mesmos dias de sinal, com o lado oposto e a geometria espelhada. O esperado é negativo.
3. **Referência:** o Deslocamento puro (f = 1, limite no fechamento das 10:29, prazo de 15 min, mesmo stop, zera às 17:50) no mesmo bloco, para separar o efeito do recuo do efeito do regime.

### Critério de sucesso (o do TODO, definido antes)
- **VAL**, uma vez:
  - lucro com custo > 0;
  - ≥ 60% dos meses positivos;
  - PF ≥ 1,2;
  - sem quebrar com R$1.000;
  - acima do p95 do controle aleatório 1.
- **HOLDOUT 2026**, uma vez: com custo > 0 e sem quebra.

**Ponto fraco conhecido, que o orquestrador precisa decidir antes da N2 rodar o VAL.** A RDT opera pouco: no DEV, 40–58 operações em 30 meses, de 1,3 a 2 por mês. Vários meses não têm nenhuma operação. Lendo o TODO ao pé da letra (mês sem operação ≠ mês positivo), a melhor célula do DEV teve 13/30 meses positivos (43%), o que **reprova** o critério de meses. Contando só os meses com operação, foram 13/23 (57%), também abaixo de 60%. A N2 reporta as duas leituras. A oficial é a do TODO, a menos que o orquestrador registre outra **antes** do VAL.

### O que torna a RDT refutada
- **No DEV**, e aí não vai ao VAL:
  - nenhuma célula cumpre a regra de escolha;
  - a célula escolhida fica abaixo do p90 do controle aleatório no DEV;
  - tirando as 2 melhores operações, o líquido do DEV fica ≤ 0.
- **No VAL:** falhar qualquer item do critério de sucesso. Isso inclui a regra dos meses, se o orquestrador não a redefinir antes.
- **No HOLDOUT:** líquido com custo ≤ 0 ou quebra.
- **Sinal de alerta**, que não refuta sozinho: no VAL, o resultado da RDT nos dias que encheram ficar abaixo do da referência nesses mesmos dias. Isso indicaria que a melhora de preço deixou de compensar a seleção adversa.

### Números do DEV que motivaram a RDT
Vêm de `explora_3_recuo.py`, com k = 0,30, R$2/op e R$1.000 contínuo. São de uma olhada antes da grade formal: a N2 roda a grade de 12 células de novo, em script próprio.

| célula | ops | fill | líquido R$ | R$/op | PF | MaxDD R$ | caixa mín. | sem as 2 melhores | meses + (de 30) | 2022 / 2023 / 2024 |
|---|---|---|---|---|---|---|---|---|---|---|
| f 0,50 até 12:00 | 40 | 35% | **+2.169** | +54 | 2,30 | 412 | 1.210 | +1.194 | 13 (23 c/ op) | +1.223 / +455 / +491 |
| f 0,50 até 14:00 | 58 | 50% | +1.470 | +25 | 1,51 | 629 | 1.235 | +495 | 13 | +1.357 / +156 / −43 |
| f 0,25 até 14:00 | 40 | 35% | +1.166 | +29 | 1,71 | 752 | 1.207 | +37 | 9 | +979 / −7 / +194 |
| f 0,75 até 12:00 | 76 | 66% | +1.299 | +17 | 1,30 | 1.521 | **−71** | +458 | 16 | +551 / +632 / +116 |
| referência Deslocamento (f = 1) | 114 | 99% | +2.509 | +22 | 1,33 | 2.159 | **−787** | +1.439 | 16 | +1.029 / +1.941 / −461 |

As 9 células com f < 1 e saída por zeragem (f 0,25/0,50/0,75 × até 12:00/14:00/16:30) dão todas líquido positivo, de +R$331 a +R$2.169, então há platô em f e em ate. Quanto mais cedo a validade, melhor, o que concorda com a lição de que a limite sem prazo enche tarde e mal. Os dias que encheram f 0,50 até 12:00 dariam −145 pts/op líquidos com a entrada das 10:30, e dão +271 com o recuo. O ganho vem do preço e do stop, não de escolher dias melhores.

Erro padrão por operação: ~138 pts com n = 40, z ≈ 2. É um indício, não uma prova.

### Ressalvas de contaminação (declaradas)
- O regime das 10:30 foi pré-registrado no estudo do Deslocamento usando WIN@D 2021-10 → 2024 como IS, o que inclui todo o DEV. O conceito é anterior a este pré-registro.
- O achado "recuo fundo de 40–50%" usou IS até 2024-06 e OOS dali em diante, que coincide com o bloco VAL. O VAL já foi visto num nível de conceito (outra regra, outra definição de pernada), nunca com esta regra.
- 2026 está contaminado: o Deslocamento foi ajustado olhando 2026, inclusive o teto de 10%, que a RDT **não** usa.
- O DEV usa ticks sintéticos (4 por M1). O stop da RDT é largo (R$58–156) em relação ao M1, então o otimismo do stop curto em M1 (LICOES 6.47) pesa pouco aqui. Mesmo assim, a fila da limite não é modelada (enche no toque), e isso é otimista, porque a entrada da RDT é toda por limite.

### Congelamento (preencher na N2 ANTES de rodar o VAL)
- célula escolhida pela regra:
- arquivo do backtest e SHA-256:
- data/hora do congelamento:

---

## 2. Execução (vale para a N2)
- Ticks sintéticos 4/M1 (`dados_dev.ticks`) no DEV e no VAL. No HOLDOUT, `dados.ticks` (reais desde 20/02/2026).
- Regras do Testador de `dados.py`. A entrada é por **limite**, o stop **a mercado**, sem alvo, com zeragem a mercado às 17:50.
- O custo de R$2/op é sempre reportado junto com o resultado sem custo, e o capital é de R$1.000 contínuo, com a quebra marcada.
- Tabela por mês e total, com operações, pregões com sinal, fill%, pregões sem operação e o caixa mínimo.

---

## 3. Direções exploradas no DEV e descartadas (não viram candidatas)
| direção (ideia do pedido) | script | resultado no DEV (R$2/op) |
|---|---|---|
| Família retângulo só em dia NEUTRO (fade das bordas da faixa da manhã, alvo no meio ou na borda oposta) | `explora_2_gatilhos.py` | NEUTRO: −24 e −32 pts/op (n = 658). O dia neutro não é mais lateral: a amplitude da tarde é 0,81 ATR, contra 0,80 no dia de tendência |
| Regime das 10:30 + gatilho rápido da roxa M5 (conceito Win), só a favor | `explora_2_gatilhos.py` | A_FAVOR: +7,7 pts bruto, −2,3 líquido (n = 203). Melhor que NEUTRO (−20) e CONTRA (−30), mas não paga o custo. Seguir o stop pela roxa destrói a RDT (todas as células negativas) |
| Regime em outros horários (11:30–13:30) para operar mais | `explora_4_horarios.py` | Poucos dias (4–36) e deriva de ~0 ou negativa. O efeito é das 10:30 |
| Reversão da 1ª hora (fade de impulso M5 com limite) | `explora_5_reversao_manha.py` | −12 a −47 pts brutos/op: a limite contra o impulso enche os piores casos |
| Mecanismo da RDT com impulso do M30 de 5 EMAs (conceito Cinco, sem o filtro do mês) | `explora_6_recuo_m30.py`, `explora_6b_grade.py` | De −20 a +5 pts líquidos/op em 8 células. Só 2023 é positivo; 2022 e 2024 são negativos. O recuo fundo não generaliza para fora do regime das 10:30 |

---
## DECISÃO DO ORQUESTRADOR antes do VAL (2026-10-06) — critério de consistência para baixa frequência
A RDT opera de 1,3 a 2 vezes por mês, então "≥60% dos meses positivos" mede mais o acaso de quantas operações caem no mês do que a consistência. A decisão foi tomada só com o DEV, antes de qualquer olhada no VAL:
- O critério de consistência passa a ser **TRIMESTRAL**: ≥ 60% dos trimestres do VAL positivos com custo (o VAL tem 5 trimestres, de jul/24 a set/25, então são precisos ≥ 3 de 5).
- Os demais critérios ficam iguais:
  - líquido com custo > 0;
  - PF ≥ 1,2;
  - não quebrar com R$1.000;
  - acima do p95 do controle aleatório (sorteio de dia e lado, mesma contagem por mês, mesmo horário e mesma geometria).
- O controle p95 é o critério que mais pesa. Se só ele falhar, a candidata está REFUTADA.
- As duas leituras mensais continuam sendo reportadas, só como informação.

---
## CONGELADA (N2, 2026-10-06 09:40) -- gravada ANTES de rodar o VAL
- Celula escolhida pela regra pre-registrada (maior lucro/DD no DEV entre as elegiveis): **f = 0,50, ate = 12:00, k = 0,40**.
  DEV com R$2/op: 21 operacoes (79 sinais), liquido +R$1.573 (sem custo +R$1.615), PF 2,77, DD R$272, caixa minimo R$1.000, lucro/DD 5,78, stop mediano R$106, sem as 2 melhores +R$618. Controle aleatorio DEV (200 sorteios): percentil 97,5 (p95 = R$1.263).
- Parametros fixos: decisao 10:30, folga 0,05 ATRd, ATR de 14 D1, zera 17:50, sem alvo, 1 contrato.
- Arquivo do backtest: `n_nova/n2_rdt.py` -- SHA-256: `ed31fee66739a54ebea4884bafc25abe645071825040b7ed07700f0e1ae1fd36`
- Data/hora do congelamento: 2026-10-06 09:40
