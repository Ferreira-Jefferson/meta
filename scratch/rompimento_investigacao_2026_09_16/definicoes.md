# Definições de lateralização e de rompimento — WIN@ M1, IS (129 pregões, 2025-12-01 a 2026-06-12)

Território deste documento: **o que É uma lateralização e o que É um rompimento** —
não a anatomia do que acontece depois (isso é `rompimento_retangulo_fenomeno_2026_09_16.py`,
outro agente) nem a executabilidade (fila/deslize).

Scripts fonte:
- `scripts/daytrade/lateralizacao_catalogo_definicoes_2026_09_16.py` (+ `.log`)
- `scripts/daytrade/lateralizacao_rompimento_definicoes_2026_09_16.py` (+ `.log`)

Regras respeitadas: só IS (< 2026-06-13), `MIN_BARRAS_POR_PREGAO=400`, `detecta_retangulo`
de produção importado (nunca reimplementado), ProcessPoolExecutor por unidade.

---

## 1. Quantas definições de lateralização existem, e quanto cada uma produz

Sete definições, todas CAUSAIS (só olham para trás), medidas com o mesmo piso de dado
(IS, 129 pregões, 72.730 barras). Limiares de 2-7 são ESCOLHAS documentadas no script,
não calibração — catalogar vem antes de otimizar.

| definição | n eventos | eventos/pregão | duração mediana (barras) | largura mediana (pts) | cobertura (% do tempo de sessão) | pico horário |
|---|---:|---:|---:|---:|---:|---|
| `retangulo_producao` (W=20, tol=0,20, larg.mín=328) | 434 | 3,36 | 16 | 434 | 16,1% | 10h BRT |
| `bollinger_squeeze` (bandwidth ≤ pctl 20 em 120b) | 660 | 5,12 | 17 | 307 | 18,3% | 12h BRT |
| `volume_secando` (vol20/vol20‑40b ≤ 0,70) | 491 | 3,81 | 23 | 416 | 18,1% | 12h BRT |
| `inside_bar_seq` (≥30% inside numa janela de 20) | 399 | 3,09 | 18 | 318 | 11,0% | 17h BRT |
| `nr7_cluster` (≥30% NR7 numa janela de 20) | 127 | 0,98 | 14 | 292 | 2,7% | 17h BRT |
| `atr_compressao` (ATR14/ATR14‑40b ≤ 0,60) | 71 | 0,55 | 14 | 409 | 1,6% | 9h BRT |
| `razao_amplitude_atr` (amp20/(ATR14·√20) ≤ 1,20) | 1.112 | 8,62 | 39 | 642 | **76,9%** | 9h BRT |

**Conjectura 1.** `razao_amplitude_atr` no limiar escolhido (1,20) é um discriminador
FRACO: cobre 76,9% do tempo de sessão, ou seja, sob esse critério o mercado está "lateral"
quase sempre. Não é achado de mercado, é limiar mal calibrado — precisa de corte bem mais
apertado (talvez ≤0,7-0,8) antes de comparar com as outras. Registrado para a próxima
rodada, não recalibrado aqui (fora do escopo desta passada de catálogo).

**Conjectura 2.** `atr_compressao` e `nr7_cluster` são os mais RAROS (0,55 e 0,98/pregão,
cobertura 1,6% e 2,7%) — condição estrita demais para descrever "lateralização" como o
dono a define (ele descreve um padrão que aparece ~3/pregão, perto do retângulo).

**Conjectura 3.** O pico horário do retângulo de produção é 10h BRT (28,0% dos eventos
contra 10,6% das barras da sessão nesse horário — 2,6× o nulo). `atr_compressao` e
`razao_amplitude_atr` concentram-se ainda mais forte às 9h (43,7% e 14,0% dos eventos vs
~10,4% do nulo) — plausível: é a hora de abertura, ATR14 ainda "aquecendo" (poucos
períodos acumulados), o que pode ser artefato do indicador, não do mercado. Já
`inside_bar_seq` e `nr7_cluster` picam às 17h (23,6% e 17,3% vs 10,6% do nulo) — perto do
fechamento, mercado "cansado". **Nenhum destes horários foi testado por significância
(agenda aberta, ver §5).**

### Distribuição por pregão (retângulo de referência)

- Eventos/pregão: mediana 3,0, média 3,36, min 0, max 11 (nulo uniforme seria 3,36 todo
  dia — a variância entre pregões é real, não um artefato do piso de barras).
- **7 de 129 pregões (5,4%) não produziram nenhum retângulo.**
- Por dia da semana: nenhum desvio grande do nulo (fração de pregões) — quinta-feira leva
  23,0% dos eventos contra 19,4% do nulo (n=100 vs esperado ~84), o maior desvio da
  semana, mas com n pequeno por categoria não é conclusivo.

**Conjectura 4.** A concentração horária (§ pico) é um sinal mais forte que o dia da
semana — vale investigar o horário como possível FILTRO antes do dia da semana.

### Taxa de rompimento (Q5 — existe lateralização que nunca rompe?)

Sob a regra de morte de PRODUÇÃO (fechamento além da borda + 25% da largura, por 3
barras consecutivas):

- **417/434 (96,1%) morreram por rompimento** (número EXATAMENTE igual ao medido de
  forma independente por `rompimento_retangulo_fenomeno_2026_09_16.py` — validação
  cruzada da reimplementação da máquina de estado).
- **17/434 (3,9%) NUNCA rompeu**: ficou vivo até o fechamento do pregão.

**Conjectura 5.** Sob a definição de morte de produção, "nunca rompe" é RARO (3,9%) — a
grande maioria dos retângulos eventualmente rompe dentro do próprio pregão. Isto é
sensível à definição de rompimento (ver §3): definições mais exigentes (k=0,50/N=3, ou
m=2,0×ATR) fariam essa fração subir, porque menos retângulos alcançam o limiar mais alto
dentro do horizonte de 200 barras (ver tabela §3 — a linha `atr m=2.0` só dispara em
90,3% da população, ou seja, quase 10% "não rompe" sob ESSA régua).

---

## 2. Elas descrevem o mesmo fenômeno? (matriz de concordância)

P(coluna=lateral | linha=lateral), barra a barra, todo o IS. Nulo de cada célula = fração
da COLUNA que é lateral no IS inteiro (concordância esperada por acaso, se independentes).

|  | retângulo | atr_compr | bollinger | raz.amp/atr | nr7 | inside | vol.seca |
|---|---:|---:|---:|---:|---:|---:|---:|
| **retângulo** | 100,0% | 4,1% | 38,5% | 97,2% | 5,7% | 11,7% | 37,3% |
| **atr_compr** | 24,9% | 100,0% | 35,1% | 94,9% | 12,0% | 24,9% | 65,3% |
| **bollinger** | 26,2% | 3,9% | 100,0% | 99,7% | 9,3% | 21,9% | 48,8% |
| **raz.amp/atr** | 19,6% | 3,2% | 29,5% | 100,0% | 6,8% | 17,7% | 25,6% |
| **nr7** | 14,8% | 5,1% | 35,2% | 87,9% | 100,0% | 25,4% | 32,9% |
| **inside** | 11,4% | 4,0% | 31,4% | 85,6% | 9,6% | 100,0% | 31,7% |
| **vol.seca** | 28,0% | 8,1% | 53,6% | 95,1% | 9,5% | 24,3% | 100,0% |
| nulo (coluna) | 16,1% | 2,6% | 23,5% | 79,6% | 6,2% | 16,4% | 21,4% |

**Conjectura 6.** Toda linha concorda com `razao_amplitude_atr` em 85-99% — mas isso é
quase inteiramente o artefato da Conjectura 1 (essa definição cobre 79,6% do tempo
sozinha), não concordância genuína. Ignorando essa coluna, a concordância mais forte e
não-trivial é **retângulo × bollinger_squeeze** (38,5% vs nulo de 23,5% — 1,6× acima do
acaso) e **volume_secando × bollinger_squeeze** (53,6% vs nulo 23,5% — 2,3× acima do
acaso).

**Conjectura 7.** `atr_compressao` e `nr7_cluster` mal concordam com o retângulo de
produção (24,9% e 14,8%, ambos perto ou abaixo do nulo marginal do retângulo que seria
16,1% olhando a diagonal invertida) — indício de que medem algo DIFERENTE do que o dono
descreveu como retângulo (visitas às bordas, cruzamentos do meio), não uma variação da
mesma coisa. `inside_bar_seq` é a que MENOS concorda com o retângulo (11,4%, abaixo do
nulo marginal do retângulo de 16,1%) — sequências de inside bars parecem ser um fenômeno
quase-independente da lateralização do dono.

**Conjectura 8.** Nenhuma das 6 alternativas é um substituto do retângulo: a maior
concordância não-inflacionada (bollinger, 38,5%) ainda deixa 61,5% das barras do
retângulo sem confirmação daquela definição alternativa. **O retângulo de produção
continua sendo a definição mais específica para o que o dono descreveu** — as
alternativas testadas não convergem para o mesmo fenômeno; na melhor das hipóteses
(bollinger, volume) capturam uma parte dele.

---

## 3. O que muda a CONTAGEM de rompimentos — tabela contagem × atraso × falso alarme

População fixa: 434 retângulos de produção (mesma do §1). Variando só a REGRA de
rompimento. Atraso medido do PREÇO NO DISPARO até a BORDA CRUA (nunca borda+margem) —
por isso k e N aparecem no próprio número do atraso, tornando toda linha comparável
entre famílias.

| variante | n/434 dispararam | atraso mediano (pts) | atraso mediano (% da largura) | desrompe K=5 | desrompe K=10 | desrompe K=20 |
|---|---:|---:|---:|---:|---:|---:|
| fechamento k=0,00 N=1 | 427 (98,4%) | 46 | 10,3% | 60,6% | 68,9% | 75,9% |
| fechamento k=0,00 N=2 | 422 (97,2%) | 90 | 20,6% | 46,4% | 57,6% | 66,1% |
| fechamento k=0,00 N=3 | 421 (97,0%) | 120 | 27,4% | 35,5% | 48,8% | 59,8% |
| fechamento k=0,10 N=1 | 427 (98,4%) | 95 | 20,0% | 48,8% | 59,4% | 68,6% |
| fechamento k=0,10 N=3 | 417 (96,1%) | 183 | 38,0% | 26,9% | 40,0% | 53,2% |
| **fechamento k=0,25 N=3 (= regra de PRODUÇÃO)** | **414 (95,4%)** | **262** | **55,5%** | **20,3%** | **32,1%** | **45,2%** |
| fechamento k=0,50 N=3 | 393 (90,6%) | 374 | 80,5% | 7,9% | 16,5% | 30,3% |
| extremo (toque) k=0,00 | 433 (99,8%) | 53 | 11,6% | 71,3% | 77,5% | 82,9% |
| extremo k=0,25 | 424 (97,7%) | 167 | 35,6% | 48,1% | 59,2% | 68,5% |
| atr m=0,0 | 427 (98,4%) | 46 | 10,3% | 60,6% | 68,9% | 75,9% |
| atr m=1,0 | 415 (95,6%) | 232 | 49,5% | 21,5% | 36,0% | 48,6% |
| atr m=2,0 | 392 (90,3%) | 407 | 89,8% | 5,9% | 14,9% | 26,5% |
| volume p=75 | 418 (96,3%) | 105 | 22,5% | 46,4% | 56,5% | 63,6% |
| volume p=90 | 407 (93,8%) | 165 | 36,9% | 35,1% | 42,3% | 51,6% |

(tabela completa das 21 variantes no `.log` do script — inclui N=2 e k=0,10/0,50
intermediários de cada família)

**Conjectura 9.** A troca é um GRADIENTE SUAVE, não um penhasco (ao contrário do que se
viu na sensibilidade do deslize do WDO F1): todo incremento de k, N, m ou p reduz o falso
alarme e aumenta o atraso de forma monotônica, sem salto abrupto em nenhuma família.
Verificação de consistência interna: `atr m=0,0` e `fechamento k=0,00 N=1` deram
NÚMEROS IDÊNTICOS (46pts, 68,9% desrompe K=10) — esperado, porque com margem zero as
duas regras são matematicamente a mesma condição (fechar além da borda crua, 1 barra);
isso valida a implementação.

**Conjectura 10.** A regra de PRODUÇÃO (k=0,25/N=3) já opera num ponto de bom
compromisso: 95,4% de cobertura da população, atraso de 55,5% da largura, falso alarme de
32,1% em K=10. Comparado a `atr m=2,0` (a mais tardia testada), ela detecta MUITO mais
cedo (55,5% vs 89,8% da largura) com falso alarme parecido (32,1% vs 14,9% — a de ATR é
de fato mais limpa, mas ao custo de quase dobrar o atraso). **Candidato a investigar na
próxima rodada: `atr m=1,0` fica entre as duas (49,5% da largura, 36,0% de falso alarme)
— quase o mesmo atraso da regra de produção com falso alarme parecido, e usa uma escala
que se adapta à volatilidade do dia em vez de ser fixa em fração da largura.**

**Conjectura 11.** `extremo` (toque de máxima/mínima) é sistematicamamente mais eager e
mais ruidosa que `fechamento` no mesmo k: a k=0,25, extremo dispara com atraso de 35,6%
da largura e falso alarme de 59,2% (K=10), contra 55,5%/32,1% do fechamento na régua de
produção — ou seja, o fechamento (que já é o que a produção usa) filtra falso alarme
melhor que o toque, ao custo de mais atraso. Isso é coerente com a lógica: pavio que
toca e volta é exatamente o "quase-rompimento" que o falso-alarme mede.

**Conjectura 12.** `volume` como filtro de rompimento (fechar além da borda com volume
alto) tem comportamento intermediário entre fechamento e extremo — não parece adicionar
poder discriminante que as famílias baseadas em preço já não tenham (p=75 fica entre
k=0,10 e k=0,25 de fechamento, tanto em atraso quanto em falso alarme). **Não
investigado: se volume alto CONFIRMA um rompimento por fechamento já disparado (redução
adicional de falso alarme) em vez de ser usado como gatilho isolado — agenda aberta.**

---

## 4. Conjectura final — qual par definição×rompimento é o mais promissor

**Lateralização:** manter `retangulo_producao` (`detecta_retangulo`, W=20, tol=0,20,
largura mín. 328) como referência. Nenhuma das 6 alternativas convergiu para o mesmo
fenômeno (concordância máxima não-inflacionada de 38,5% — Conjectura 8), e a definição
do dono é a única calibrada e já validada em produção (win_retangulo).

**Rompimento:** a regra de produção (fechamento, k=0,25, N=3) não é claramente dominada
por nenhuma variante testada — está no meio do platô suave da Conjectura 9. O único
candidato que se destaca o suficiente para valer medição adicional é
**`atr m=1,0`** (fechamento além da borda + 1×ATR14 congelado no nascimento): atraso
próximo (49,5% vs 55,5% da largura) com falso alarme comparável (36,0% vs 32,1% em
K=10), mas a régua se ADAPTA à volatilidade do dia em vez de ser uma fração fixa da
largura do próprio retângulo — dois retângulos de largura igual em dias de volatilidade
diferente teriam limiares de rompimento diferentes sob ATR, o que a régua de produção não
faz. **Isto é conjectura, não resultado: a anatomia pós-disparo dessa variante (MFE/MAE,
reteste, corrida alvo×stop) não foi medida aqui — é o próximo passo natural, e caberia ao
território do agente de anatomia.**

---

## 5. Perguntas que ficaram abertas (agenda da próxima rodada)

1. **Recalibrar `razao_amplitude_atr`** com limiar mais apertado (Conjectura 1) antes de
   julgá-la — no limiar testado (1,20) ela não discrimina nada.
2. **Testar significância da concentração horária** (10h para o retângulo, 9h para
   ATR/amplitude, 17h para inside/NR7) — aqui só foi comparado contra o nulo de barras
   por hora, sem teste estatístico formal (ex.: qui-quadrado, ou bootstrap por pregão).
3. **`volume` como CONFIRMAÇÃO em vez de gatilho isolado** (Conjectura 12) — cruzar
   fechamento k=0,25/N=3 (produção) com volume alto SÓ na barra de disparo, medindo se
   o subconjunto "confirmado por volume" tem falso alarme menor que o total.
4. **`atr m=1,0` merece a anatomia completa** (MFE/MAE do preço de detecção, reteste,
   corrida alvo×stop) nos mesmos moldes de `rompimento_retangulo_fenomeno_2026_09_16.py`,
   comparando com a régua de produção lado a lado.
5. **Por que 17/434 (3,9%) nunca rompem** — são retângulos mais largos, mais estreitos,
   de algum horário específico? Não caracterizado aqui.
6. **Dia da semana**: quinta-feira teve 23,0% dos eventos contra 19,4% esperado — não
   testado por significância, n pequeno por categoria (~25-27 pregões cada).
7. **Overlap matrix restrita a barras "maduras"** (após aquecimento de cada indicador,
   ex. ≥140 barras do dia para o squeeze de Bollinger) não foi feita — a matriz atual
   inclui barras de warmup tratadas como False para as definições mais exigentes, o que
   pode subestimar levemente a concordância marginal delas.
