# Camada de decisão e risco — WIN

Código: `rodada4/decisao/motor.py` (funções puras), `test_motor.py` (13 testes, passam), demos `demo_a.py`, `demo_bcd.py`, `demo_extra.py` (saídas em `out_*.txt` e `demo_*.csv`).

Contrato: R$0,20/pt, custo 2 pts + 5 pts de deslize só no stop. Capital de partida R$250 (mínimo real); ruína = caixa < R$100 (não segura 1 contrato); 2º contrato exige R$250 por contrato. Dados reais: só 2026 (188 pregões, 105.433 barras M1). **Toda vantagem das demos (b), (c) e (d) é hipotética (parâmetro), não medida.**

## Como usar o motor

| Pergunta | Função |
|---|---|
| Ganho/perda líquidos, breakeven, nulo, esperança, payoff | `ganho_perda`, `breakeven_p`, `nulo_p`, `esperanca`, `resumo_distribuicao` |
| Risco de ruína | `ruina_formula` (Lundberg, horizonte infinito), `ruina_mc` (Monte Carlo) |
| p com n pequeno | `p_encolhido(k,n,p_base,n0)`, `p_limite_inferior`, `n_para_confirmar` |
| Quantos contratos | `tamanho` / `tamanho_vec` (Kelly fracionário + teto de pior caso + margem), `tamanho_ajustado_vol` |
| Relógio de volatilidade | `dst_eua` (R28), `indice_vol_horario`, `vol_do_horario`, `stop_alvo_por_vol` |
| Vários sinais fracos | `combina_sinais` (log-odds, penaliza correlação, aceita encolhimento por sinal) |
| Parar no dia | `ParadaDia(perda_max_brl, n_max_ops, n_max_stops, ganho_trava_brl)` |
| Constância | `metricas_constancia` (líquido, meses positivos, pior mês, MaxDD, Ulcer, pior sequência), `ulcer_index`, `pior_sequencia` |

Fluxo: o sinal entrega `p` (acerto estimado) → `p_encolhido` → `tamanho(p, ganho, perda, caixa)`; stop/alvo vêm de `stop_alvo_por_vol(índice do horário)`; `ParadaDia` autoriza ou não a operação; `metricas_constancia` mede o resultado. Se a esperança líquida com p encolhido é ≤ 0, o tamanho é 0 (não entra, mas segue registrando na sombra para aprender).

## (a) Direção aleatória: nenhuma geometria paga o custo

Entrada em minuto sorteado (09:30–16:30), long e short, no fechamento da barra (limite assumido preenchido), stop vence empate na mesma M1, fim do pregão = saída a mercado. 25 geometrias (alvo e stop ∈ {50,100,150,250,500}), 9.400 operações cada (IC por pregão).

- **0 das 25 células tem esperança positiva; 0 com limite inferior do IC acima de zero.** A melhor: alvo 100 / stop 250, −1,3 pt (±2,8) — igual ao custo.
- O win% fica no nulo `stop/(alvo+stop)` (ex.: 100/100: 48,9% × 50,0%; 250/500: 64,3% × 66,7%) — R14 confirmada em simulação.
- Peso do custo: o breakeven sobe de 0,4 a 4,3 pp acima do nulo. Stop/alvo curtos sofrem mais: 50/50 perde −11,9 pts por operação (custo médio 4,9 pts, 9,7% do alvo; win 43,0% contra breakeven 54,3%); 500/500 perde −4,2 (0,8% do alvo, mas com dispersão enorme, IC ±0,07 só por ser quase tudo stop/alvo simétrico). Custo médio por operação = 2 + 5×P(stop): 2,5 a 6,5 pts.
- Em R$ por contrato: de −R$0,26 a −R$2,37 por operação.

Conclusão: o custo é piso; só vantagem de direção (acerto acima de `breakeven`, não de `nulo`) cria esperança.

## (b) Tamanho com vantagem hipotética (capital R$250, geometria 75/150, 250 pregões, ~1 sinal/dia, 2.000 trajetórias)

Geometria 75/150: ganho líquido 73 pts (R$14,60), perda líquida 157 pts (R$31,40), nulo 66,7%, **breakeven com custo 68,3%**. Esperança por operação a 1 contrato: +4pp = +5,6 pts (R$1,1); +15pp = +42 pts (R$8,4).

| cenário | política | líquido mediano R$ | líquido médio R$ | p5 R$ | ruína | MaxDD médio R$ | Ulcer | meses+ | pior seq. (ops) |
|---|---|---|---|---|---|---|---|---|---|
| nulo | fixo 1 | −159 | −81 | −179 | **78,8%** | 261 | 31 | 30% | 3,8 |
| nulo | Kelly 1/4 ingênuo | −94 | −46 | −149 | 3,8% | 184 | 36 | 16% | 3,1 |
| nulo | Kelly 1/4 encolhido | −38 | −33 | −146 | 2,4% | 124 | 23 | 11% | 2,2 |
| nulo | por volatilidade | −156 | −84 | −171 | 78,2% | 280 | 36 | 29% | 3,8 |
| +4pp | fixo 1 | +193 | +203 | −174 | **37,8%** | 250 | 24 | 50% | 3,9 |
| +4pp | Kelly 1/4 ingênuo | +50 | +170 | −148 | 3,0% | 241 | 32 | 38% | 3,6 |
| +4pp | Kelly 1/4 encolhido | 0 | +129 | −147 | 3,2% | 191 | 26 | 33% | 3,3 |
| +4pp | por volatilidade | +92 | +267 | −168 | 41,5% | 371 | 30 | 46% | 3,8 |
| +15pp raro (0,3 sinal/dia) | fixo 1 | +463 | +462 | +196 | 0,8% | 89 | 7 | 78% | 2,3 |
| +15pp raro | Kelly 1/4 ingênuo | +476 | +696 | +132 | 0,1% | 172 | 10 | 73% | 2,2 |
| +15pp raro | Kelly 1/4 encolhido | +362 | +360 | +58 | 0,0% | 82 | 7 | 63% | 2,1 |
| +15pp raro | por volatilidade | +573 | +648 | +158 | 0,9% | 145 | 9 | 77% | 2,3 |

(tempo mediano até quebrar, quando quebra: fixo ≈ 55–64 pregões; Kelly 100–140 pregões — a ruína do Kelly é rara e tardia.)

Leituras:
1. **A ruína de R$250 vem do tamanho da perda, não da vantagem**: a perda de 1 contrato (R$31,40) é 12,6% do capital e a ruína está a 5 perdas seguidas. Com +4pp, 38% quebram em 1 ano; com nulo, 79%.
2. Kelly ingênuo e encolhido trocam lucro por sobrevivência: ruína 38% → 3% com +4pp. O encolhido quase não opera até o n crescer (mediana 0 em +4pp: a vantagem líquida de custo é só 2,4 pp, e provar isso exige n≈1.000, ver abaixo). No nulo o encolhido perde menos (−R$38 contra −R$159) e quase nunca quebra.
3. **Tamanho por volatilidade não reduz ruína** (nulo 78%, +4pp 41,5%), porque com 1 contrato mínimo a perda em horário volátil sobe (até R$59). Seu ganho está no lucro (+R$267 contra +R$203 médio, custo pesa menos em stop largo), com MaxDD maior.
4. A 250 reais o tamanho é 0 ou 1: "mão proporcional" só existe de verdade com folga de capital (ver c).
5. Pior caso: um sinal tipo R29 em geometria 250/500 (perda líquida 507 pts = R$101) não cabe em 25% de R$250: `tamanho` dá 0 até a caixa chegar a ~R$406.

## (c) Mão pequena quando o sinal é fraco (hipotético: 20% fortes +12pp, 30% médios +4pp, 50% fracos −2pp sobre o nulo; 1 sinal/dia; 1.500 trajetórias)

| capital | política | líquido med. R$ | líquido médio R$ | p5 R$ | ruína | MaxDD R$ | Ulcer | meses+ | pior mês R$ |
|---|---|---|---|---|---|---|---|---|---|
| 250 | sempre 1 (entra em tudo) | −117 | +95 | −175 | **49,9%** | 256 | 26,6 | 42% | −135 |
| 250 | sempre 2 | −151 | +116 | −175 | 51,9% | 315 | 29,3 | 41% | −159 |
| 250 | Kelly 1/4 por tipo | **+309** | +302 | −141 | **1,1%** | 165 | 19,9 | **59%** | −85 |
| 250 | Kelly 1/2 por tipo | +319 | +393 | −141 | 1,1% | 203 | 21,0 | 59% | −102 |
| 1.000 | sempre 1 | +136 | +138 | −413 | 0,3% | 345 | 14,1 | 56% | −150 |
| 1.000 | sempre 2 | +253 | +260 | −738 | 3,2% | 652 | 25,0 | 55% | −294 |
| 1.000 | Kelly 1/4 por tipo | +713 | +817 | −8 | 0,0% | 332 | 8,9 | **70%** | −164 |
| 1.000 | Kelly 1/2 por tipo | +1.267 | +1.635 | −83 | 0,0% | 697 | 13,9 | 69% | −335 |

Quase todo o ganho vem de **não operar o sinal fraco** (esperança negativa depois do custo) e de pôr mais contratos só no forte. Isso supõe conhecer o tipo do sinal (calibrado): o que a pesquisa não demonstrou até agora.

## (d) Parada no dia (fixo 1 contrato, R$250, 3 sinais/dia, 250 pregões, 2.000 trajetórias)

| cenário | sem parada | máx 2 ops/dia | máx 1 stop/dia | perda máx R$40 | R$40 + 2 stops |
|---|---|---|---|---|---|
| nulo, dias iid: ruína | 93,3% | 86,1% | 88,7% | 92,9% | 92,2% |
| +4pp, dias iid: ruína / líq. mediano R$ | 43,6% / +443 | 41,1% / +306 | 41,2% / +324 | 43,4% / +410 | 43,2% / +388 |
| +4pp, dias ruins persistem (σ 6pp): ruína / líq. | 44,4% / +435 | 41,8% / +275 | **36,6% / +479** | 42,0% / +495 | 41,0% / +510 |
| nulo, dias ruins persistem: ruína | 93,4% | 86,8% | 85,2% | 91,8% | 91,9% |

Parar no dia **não cria vantagem**. Com dias independentes só reduz a exposição (ruína cai poucos pontos, lucro cai proporcionalmente). Só melhora o lucro e a ruína ao mesmo tempo se há persistência de dia ruim (σ 6pp no acerto diário, hipótese; as regras R20 mostram persistência de volatilidade, não de acerto). Com R$250 de capital o piso é outro limite: R$40 de perda diária ≈ 1 stop — equivale a "máx 1 stop/dia".

## Regras práticas

**Ruína × capital (1 contrato, geometria 75/150, 250 operações; fórmula/MC):**

| capital | nulo | +2,4pp (=breakeven) | +4pp | +8pp | +15pp |
|---|---|---|---|---|---|
| R$250 | 100%/78,5% | 99,8%/64,0% | 48,0%/39,0% | 13,3%/11,3% | 1,0%/0,6% |
| R$500 | 100%/41,7% | 99,5%/24,6% | 14,1%/7,7% | 0,5%/0,5% | 0% |
| R$1.000 | 100%/3,5% | 99,0%/0,9% | 1,2%/0,3% | 0% | 0% |

Capital mínimo para 1 contrato com ruína ≤5% em 250 operações: **+4pp: R$600; +8pp: R$350; +15pp: R$250**. Com R$250 a vantagem exigida é ≥ +15pp (acerto 82%) para operar a geometria 75/150.

**Encolhimento (n0=100, base = nulo 66,7%):** acerto observado 82% em n=10 → p usado 67,9% (abaixo do breakeven 68,3%: tamanho 0); em n=30 → 70,5%; n=100 → 74,3%; **n=178 (R29) → 76,5%** (não 82%); n=500 → 79,4%. Teto de contratos por n de operações observadas: n < 25 → 1; n < 100 → 2; n ≥ 100 → pleno (`teto_tamanho_por_n`).

**n para confirmar:** vantagem de +4pp sobre o nulo exige n=374 só para excluir o nulo e **n≈1.000** para provar que supera o breakeven com custo (2,4pp); +8pp: 94/143; +15pp: 27/33. Antes disso, o tamanho máximo é 1.

**Sinais fracos:** dois sinais de 70% (base 66,7%), correlação 0,5 → 71,1%, não 73,1%; três com ρ=0,8 → 70,5% (praticamente um só). Sem estimar ρ, somar sinais é superconfiança.

**Relógio → stop/alvo (base 150/75, regime DST-EUA):** 09:00 290/145; 10:30 280/140; 12:00 160/80; 13:00–15:00 115/60; 16:00 105/50. O custo de 7 pts pesa 2,5% do alvo às 09:00 e 6–8% à tarde. No inverno dos EUA o pico de NY se move para 11:30 (índice 1,50 contra 1,24 no verão). A perda de 1 contrato vai de R$59 às 09:00 a R$22 à tarde: com R$250 de capital, o stop da manhã excede 25% da caixa e o teto de pior caso bloqueia a entrada.

**Parada no dia:** use `n_max_stops=1–2` e perda diária ≈ 1 stop com capital mínimo; reduz ruína em 3–8 pp quando há persistência de dia ruim, e corta lucro proporcionalmente quando não há.

**Limitações:** vantagens, tipos de sinal e persistência de dia ruim são hipóteses; entradas da demo (a) assumem preenchimento da limite no fechamento (ignora fila); simulação de ruína usa operações independentes e geometria sempre com o nulo constante (R14).
