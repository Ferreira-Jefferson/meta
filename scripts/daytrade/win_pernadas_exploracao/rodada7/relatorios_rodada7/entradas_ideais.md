# Entradas ideais no WIN: a combinação dos fatores decide uma entrada?

Janela: M1 de 2026 (aquecimento nov–dez/2025). Treino e seleção só em jan–jun; confirmação em jul–ago e set depois do congelamento (`entradas_ideais/congelado_ANTES_da_confirmacao.json`). Código e saídas: `rodada7/entradas_ideais/`.

## Veredito

**Não.** A combinação não cria uma fatia de entradas acima do breakeven que se sustente fora da amostra. Em validação cruzada por mês (jan–jun) a fatia superior parece boa (geometria escolhida: +62,7 pts/op, acerto 8,0% × breakeven 4,9%); em jul–ago cai para −24,7 pts/op (IC95 por dias −128 a +98) e em set para −91,6. O melhor resultado da busca inteira (900 geometrias) é igual ao que o mesmo pipeline produz com rótulos embaralhados (seção 4). O que se sustenta são fatores para NÃO operar (relógio e lateralização), não para entrar.

## 1. Entradas ideais (rótulo)

Candidato: fim de cada vela M1 numa grade de S minutos, com recuo em curso ≥ m pts a partir do extremo da pernada de 750 (zigzag causal), a favor (e contra) da pernada. Ordem-limite no fechamento, preenchida só se negociar 1 tick além (TTL 5 min); stop técnico = extremo das últimas N velas, com piso de 100 pts e de `piso`×ATR M1 do horário (média do mesmo bloco de 30 min nos 20 pregões anteriores); alvo = K×risco; execução do projeto (alvo +1 tick, stop +5 pts, custo 2 pts, stop e alvo no mesmo minuto = stop; sem desfecho até 17:00 sai a mercado). Universo: 12.024 candidatos (jan–jun 7.856; jul–ago 2.759; set 1.349), de 9:15 a 16:00.

Geometria de referência (N=5, piso 1, m=150, S=15), jan–jun, n=2.241:

| K | acerto a favor | breakeven emp. | esp. pts/op | acerto contra | esp. contra |
|---|---|---|---|---|---|
| 3 | 23,4% | 24,5% | −7,3 | 22,2% | −9,4 |
| 4 | 18,0% | 18,7% | −5,8 | 16,3% | −12,8 |
| 5 | 13,8% | 14,9% | −9,7 | 12,3% | −12,7 |
| 7 | 9,2% | 10,0% | −10,1 | 7,0% | −21,4 |
| 10 | 5,0% | 5,8% | −13,2 | 3,5% | −24,8 |

A favor é sempre melhor que contra (0,7–1,5 pp) e sempre abaixo do breakeven. Preenchimento 98–99%.

## 2. Como a geometria muda a base e a separabilidade (900 combinações, jan–jun, CV por mês)

AUC médio (logística L2, CV deixa-um-mês-fora) por K: 3 → 0,50; 4 → 0,51; 5 → 0,52; 7 → 0,53; 10 → 0,56. Esperança da fatia superior (20%) por K: −6,5 (K3), −10,5, −13,6, −13,2, −13,8 (K10). Por N (stop): −15,5 (3), −17,1 (5), −12,9 (7), −11,3 (10), −0,7 (15). Por S: 5 min −2,0; 15 min −9,8; 30 min −22,7 (S=5 tem mais amostra, mas sobreposta). Por m: 100: −9,4; 150: −9,4; 250: −10,6; 375: −16,7. Só 31% das 900 geometrias têm fatia superior positiva em CV.
A separabilidade sobe com K porque alvo distante é raro e coincide com horário/volatilidade; não vira lucro: K=10 tem acerto-base de 4,5% e esperança dominada por poucas vitórias de 10R.

## 3. O que veio antes (geometria de referência, jan–jun)

AUC univariada a favor / contra (variantes escolhidas por platô; tabela completa em `univariado_ref.csv`):

| fator (variante) | AUC favor | AUC contra | leitura |
|---|---|---|---|
| caixa 20–30 min (largura) | 0,55 / 0,54 | 0,51 | "vai andar": caixa estreita → acerto 7,6–9,0% × base 13,8% (Q1) |
| vol30/300, rh M15, onda 60 min | 0,53 | 0,47–0,49 | vol alta ajuda; efeito de nível |
| horário ajustado (tarde) | 0,46 | 0,48 | tarde pior (Q5 9,3%) |
| idade da perna | 0,45 | 0,46 | perna velha pior (8,5%) |
| recuo raso (23–38%) | 0,52 | 0,51 | +1,7 pp, 5/6 meses |
| dist. EMA M5/M15, posição no dia, TICKVOL | 0,51–0,53 | 0,44–0,49 | indica direção em jan–jul, inverte em set |
| vela M1 ≥ 2× (qualquer janela) | 0,50–0,52 | 0,48 | ≥2×: acerto 11,8–13,8%, ABAIXO da base em 5 de 6 janelas; só ≥1,5× nas últimas 20–30 velas dá +1,3–1,5 pp (6/6 meses) |
| saldo de velas, delta por corpo, esticado-continua, gap, alinhamento EMA | 0,48–0,52 | — | nulo |
| controles de ruído | 0,51 / 0,52 | 0,53 | ruído chega a AUC 0,52: nada abaixo de ~0,53 se distingue |

Sensibilidade a limiares (acerto condicional): caixa ≤150 pts/10 min 8,9% (n=124); ≤150/20 min quase nunca ocorre num recuo ≥150 (n=22); ≤300/30 min 5,2%. Saldo de 10–20 velas no quintil alto 12,1–14,0% (≤ base). Esticado-continua só aparece com subida ≥200 (15,6–16,0%, 4/6 meses) e some com ≥300. Recuo raso: faixa 20–35% +2,0 pp, 23–38% +1,7, 25–40% +0,9, 30–50% +0,4 (platô decrescente). Onda de 60 min: quintil baixo 9,8% (0/6 meses acima da base), alto 14,5%. Tabelas completas em `saida_s1a.txt`.

Redundâncias (|ρ| ≥ 0,6): distância ao VWAP × posição no dia 0,89; distância à máxima × posição −0,87; EMA M15 alinhamento × EMA H1 distância 0,87; hora × (tarde, manhã, vol30/300) 0,78–0,86; perna × ordem do recuo 0,79; vol30/300 × caixa 0,75; rh M5 × onda 60 0,73; recuo × profundidade 0,72; EMAs M5 × M15 distância 0,77–0,81.

## 4. Combinação

Modelo: regressão logística L2 (numpy), uma variante por família (platô de AUC mensal), 36 colunas; λ e grupos por CV mensal; geometria escolhida pela esperança suavizada da fatia superior (média das vizinhas N×piso×K). Três modelos congelados: SEL (m250 S5 N15 piso0,5 K10), K5 (melhor K=5: m250 S5 N10 piso0,5) e REF (geometria de referência).

CV jan–jun (fatia superior 20%): SEL AUC 0,599, acerto 8,0% × BE 4,9%, +62,7 pts/op; K5 AUC 0,560, +3,2; REF AUC 0,520, −17,1. A eliminação de grupos em CV tirou estrutura, fluxo e volatilidade do SEL.

Confirmação (limiares congelados; IC95 por bootstrap de dias; ops/dia sobre a grade amostrada):

| modelo | janela | AUC | top 10%: n, acerto × BE, esp pts/op [IC] | top 20%: n, acerto × BE, esp pts/op [IC] |
|---|---|---|---|---|
| SEL | jul–ago (n=1.505, base 3,2%) | 0,633 | 116 (2,6/dia): 4,3% × 2,2%, +31,9 [−154; +272] | 266 (6,1/dia): 4,5% × 6,1%, −24,7 [−128; +98] |
| SEL | set (base 4,8%) | 0,457 | 85: 3,5% × 16,9%, −173,9 [−289; −45] | 158: 3,2% × 10,5%, −91,6 [−184; +3] |
| K5 | jul–ago (base 14,4%) | 0,507 | 188: 17,6% × 13,2%, +49,6 [−48; +144] | 317: 14,8% × 13,1%, +16,6 [−49; +90] |
| K5 | set | 0,494 | 104: 13,5% × 17,4%, −47,8 [−199; +93] | 196: 14,3% × 15,9%, −18,4 [−113; +63] |
| REF | jul–ago (base 16,6%) | 0,515 | 51: 17,6% × 13,6%, +50,0 [−94; +200] | 115: 19,1% × 16,2%, +33,0 [−64; +135] |
| REF | set | 0,497 | 71: 16,9% × 19,0%, −29,7 [−151; +89] | 109: 12,8% × 16,6%, −52,5 [−137; +33] |

Calibração: os decis de probabilidade prevista não ordenam o acerto (SEL jul–ago: decil 1 = 0,0%, decil 4 = 5,3%, decil 10 = 4,0%; set: decil 10 = 3,9% e −180 pts/op). Sem sobreposição de posições (o motor não piramida), SEL top 10% em jul–ago: 54 operações, 1,2/dia, acerto 1,9%, +62,6 pts/op, soma +3.380 pts, pior sequência 9 perdas; em set −109,5 pts/op. K5 top 10%: jul–ago 109 operações, 19,3%, +80,9 pts/op (pior sequência 14); set −69,1.

Ablação (treino jan–jun sem o grupo, avaliado em jul–ago, SEL): sem relógio AUC 0,633 → 0,564 (único grupo que carrega o AUC); sem esticamento 0,626; sem micro 0,637; sem médias 0,625; sem dia 0,644. O AUC de jul–ago é o relógio; em set cai a 0,457.

Nulo na confirmação (rótulos embaralhados em blocos de ~5 dias, 500 vezes): AUC 0,50–0,51 (dp 0,02–0,05, p95 0,54–0,59). SEL jul–ago (0,633) passa do p95 (0,578), mas em set e nos outros dois modelos o AUC real fica dentro do nulo.
Nulo do pipeline inteiro (12 repetições, rótulos embaralhados em blocos de 10 pregões em jan–jun, subgrade de 300 geometrias): a melhor esperança suavizada da fatia superior sob o nulo tem média +39,0 pts/op (máx 68,2); a real na mesma subgrade é +20,5 (+30,6 nas 900). 75% das repetições do nulo igualam ou superam o real; AUC suavizado máximo: nulo 0,545, real 0,557 (42% das repetições o superam). A busca, como feita, não separa o real do acaso.

Tamanho de mão e ruína (motor, R$250, jul–set sem sobreposição): SEL top 10%: 97 operações, acerto 3,1%, p encolhido 4,0% < breakeven 4,3% → 0 contratos; top 20%: 141 operações, 5,7%, +33,2 pts/op, p encolhido 5,3% → 1 contrato, ruína MC (300 operações) 85%. K5 top 10%: 171 operações, 16,4%, +25,6 pts/op, 1 contrato, ruína 83%; top 20% 92%. REF: 0 contratos, ruína 81–91%. Com acerto de 3–16%, ganhos de 900–1.300 pts contra perdas de 45–220, a variância dos ganhos grandes domina e R$250 não sustenta a sequência de perdas esperada.

## 5. Checagem com ticks (mar–jun)

Rótulos refeitos com o caminho real de negócios (ticks alinhados ao M1 por deslocamento diário, 3 níveis no período, mediana minuto a minuto; ticks comprimidos às mudanças de preço), mesmas regras. Em SEL e K5 (stop técnico de 10–15 velas, piso 100 pts) os desfechos coincidem em 100% das 3.058 entradas (base 4,74% e 14,39%; esperança +5,8 e −3,3 pts/op; fatia superior +27,7 e −6,0, idênticas ao M1). Em REF (stop 100, N=5): concordância 99,9% (1.538 entradas), base 14,38% (ticks) × 14,37% (M1), esperança −1,05 × −1,29, fatia superior −6,4 × −7,5. Com piso de stop de 100 pts o caminho de 2 pontos por vela não distorce estes rótulos; a divergência medida por outro analista aparece em stops menores, que esta rodada não usa. Vale o resultado de ticks, e ele não difere.

## 6. Ficha de consolidação

Sinais por janela (jan–jun / jul–ago / set), três geometrias (`ficha_auc_por_janela.csv`).

| fator | classe | evidência |
|---|---|---|
| horário (tarde ≥ 13h aj. / hora alta) | NÃO OPERAR | AUC < 0,5 nas 3 janelas × 3 geometrias (0,36–0,48) |
| segunda-feira | NÃO OPERAR (fraco) | AUC 0,42–0,49 nas 3 × 3 |
| lateralização (caixa 20–30 min estreita), vol30/300 baixa | NÃO OPERAR | caixa: Q1 7,6–9,0% × base 13,8%; AUC > 0,5 em 8 de 9 (vol30/300) e 6 de 9 (caixa); some em set no K5/SEL |
| (nenhum) | USAR PARA ENTRAR | nada acrescenta fora da amostra; o único ganho de AUC é o relógio |
| distância ao VWAP, posição no dia, distância à máxima | REDUNDANTE (consolidar em posição no dia) + DESCARTAR | ρ 0,87–0,89; AUC +,+,− |
| hora, tarde, manhã, vol30/300; caixa × vol30/300 | REDUNDANTE (consolidar em hora e vol30/300) | ρ 0,74–0,86 |
| EMA M5, M15, H1 (alinhamento e distância; conjuntos 9/21/50, 8/20/50, 10/30/60, 12/26/72) | REDUNDANTE entre si (ρ 0,6–0,8) e DESCARTAR | AUC ≈ 0,5 em jan–jun; +,+,− com set invertido (0,26–0,45) |
| perna, ordem do recuo, recuo, profundidade, perna velha, nº de pivôs | DESCARTAR | sinal muda entre janelas |
| recuo raso 23–38% | DESCARTAR (fraco) | +1,7 pp em jan–jun; inverte em jul–ago e set |
| vela M1 ≥ 2× (≥2,5×, ≥3×) | DESCARTAR | acerto abaixo da base; só ≥1,5× nas últimas 20–30 velas dá +1,3–1,5 pp |
| esticado-continua, saldo de 5–20 velas, delta por corpo, TICKVOL, gap/ATR, sexta, minuto :00/:30, rh M5, onda 5–60 | DESCARTAR | AUC 0,48–0,53, dentro do ruído |

## 7. Contagem de testes e limitações

Variantes testadas: 88 variantes de feature em 39 famílias (incluindo 2 controles de ruído) × 2 rótulos × 3 janelas; ~110 condições de limiar; 900 geometrias × 6 dobras de CV; 6 valores de λ × 3 modelos; ~60 ajustes de eliminação de grupo; 3 modelos congelados; 12 repetições do nulo × 300 geometrias. Total de variantes de decisão ≈ 1.200.
Limitações: (1) o delta pela regra do tick não foi usado; o fluxo entra só por delta de corpo e TICKVOL. (2) Amostras com S=5 se sobrepõem; os ICs são por dias, mas o n efetivo é menor que o nominal. (3) O nulo da confirmação embaralha rótulos dentro de blocos de dias. (4) "A favor" usa a direção da pernada de 750; outras definições de tendência não foram testadas. (5) A primeira execução do nulo caiu com 4 workers (processo encerrado sem erro registrado) e foi refeita com 3; a RAM não foi medida. (6) Ablação em jul–ago e ficha por janela são diagnósticos pós-congelamento; nada foi reescolhido com eles. (7) A checagem com ticks cobre só mar–jun e os três modelos congelados, não as 900 geometrias.
