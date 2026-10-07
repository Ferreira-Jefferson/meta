# Tendência maior × recuo como entrada × "perder de colherinha" — WIN, 2026

Código: `rodada5/tendencia/` (`base.py` features e simulador, `run.py` grade, `analise1-4.py`, `null.py`, `null2.py`, `an5.py`, `an6.py`). Resultados brutos: `grade_resultado.csv` (1.620 células × 2 convenções de fill × 3 períodos), `congelado_ANTES_da_confirmacao.json`, `congeladas_desc_conf.csv`, `nulo2_vs_real.csv`, `filtros_interacao.csv`.

## Dados e regras
- WIN@D M1 contínuo, só 2026 (jan–set; 185 pregões; out/26 não lido). **Dez/2025 foi lido SÓ como aquecimento** de médias diárias (10/20 dias) e de EMAs M15/H1; nenhuma operação nem resultado de dez/25. Nada de 2025 em diante para trás foi aberto.
- **Descoberta jan–jun (121 pregões). Confirmação jul–ago (43). Set/26 só referência (21).** As 8 regras da confirmação foram escolhidas só com a descoberta e gravadas em `congelado_ANTES_da_confirmacao.json` antes de qualquer leitura de jul–ago.

## Execução simulada
Entrada e alvo por **ordem-limite**, stop **a mercado** (+5 pts de deslize), custo 2 pts/op, R$0,20/pt. Convenção **conservadora ("cons")**: a limite só enche se o preço negociar 1 tick além do nível (entrada e alvo); **otimista ("otim")**: basta tocar. Empate na mesma M1 = stop. Ordem de entrada com prazo de 10 barras e cancelada se a tendência virar. Uma operação por vez; **depois de uma operação só rearma com extremo novo do dia** (senão o robô refaz o mesmo recuo 40×/dia). Entradas 09:15–16:30; o que não resolveu até o fechamento sai a mercado no último candle (contado à parte: **< 1,5% das operações**, ver coluna "não resolvidas"). Nenhuma geometria com alvo < stop. Ganho líquido = alvo − 2; perda líquida = stop + 7. Para 100/750: breakeven 12,6%, nulo de passeio aleatório 11,8%.

**Entrada (a favor):** com tendência de alta, limite em `máxima do dia − X` (X = 150 ou 300 pts) ou na EMA60 do M1 ("mm"); o espelho na baixa. Stop 75/100/150/200; alvo 600/750/1000. **Contra** = a mesma entrada com o sinal da tendência invertido (em alta, vende no repique de X acima da mínima do dia). **Sem filtro** = long e short, duas execuções independentes (é exatamente favor ∪ contra).

**Tendências (todas causais, conhecidas no fechamento da vela):** diárias — `d_ma10`/`d_ma20` (fechamento de ontem vs média de 10/20 dias), `d_slope` (inclinação da MM10), `d_seq` (3 fechamentos consecutivos), `d_wkprev` (semana anterior), `d_wkcur` (preço vs abertura da semana); intradiárias — `i_open` (vs abertura), `i_vwap`, `i_leg` (direção da pernada de 750 pts do zigzag, confirmada), `i_m15`/`i_h1` (inclinação da EMA20); concordância — `conc3` (d_ma20 + i_open + i_vwap) e `conc5` (+ i_m15 + i_h1). **Observação:** `i_leg` usa zigzag de 750 sobre o caminho da vela M1, não barra H1 (ver limitações).
Filtros "liga": `cedo` = antes das 11:00 (12:00 fora do horário de verão dos EUA, R28) e `vela` = alguma M1 com range ≥ 2× a média do mesmo minuto (20 pregões anteriores) nos últimos 15 min.

## 1. A tendência maior muda a assertividade? Média das 12 geometrias (X × stop × alvo), convenção cons

Acerto das operações resolvidas, em %. "dif" = a favor − contra (pp). Nulo teórico médio das geometrias: 14,6%.

| escala | **descoberta** favor / contra / sem filtro, dif | **confirmação** favor / contra / sem filtro, dif | set (ref.) dif |
|---|---|---|---|
| conc5 | 14,3 / 10,7 / 13,7, **+3,6** | 9,9 / 15,0 / 12,8, −5,1 | +11,9 |
| conc3 | 14,1 / 12,1 / 13,7, +2,0 | 8,1 / 10,8 / 12,8, −2,7 | +10,0 |
| d_wkprev | 15,0 / 12,2 / 13,7, +2,9 | 10,3 / 15,4 / 12,8, −5,1 | +11,4 |
| i_leg | 13,9 / 11,5 / 13,7, +2,3 | 14,6 / 9,3 / 12,8, **+5,3** | +8,4 |
| i_h1 | 13,9 / 13,2 / 13,7, +0,7 | 14,4 / 9,6 / 12,8, **+4,8** | −0,3 |
| i_m15 | 14,4 / 13,4 / 13,7, +1,0 | 13,3 / 9,9 / 12,8, +3,4 | +1,0 |
| i_open | 14,3 / 13,3 / 13,7, +1,1 | 14,0 / 10,3 / 12,8, +3,7 | +2,1 |
| i_vwap | 13,4 / 12,4 / 13,7, +1,1 | 13,1 / 11,7 / 12,8, +1,4 | +1,7 |
| d_ma10 | 13,6 / 13,7 / 13,7, −0,1 | 10,3 / 15,1 / 12,8, **−4,8** | +1,4 |
| d_ma20 | 13,6 / 13,8 / 13,7, −0,2 | 8,9 / 16,3 / 12,8, **−7,3** | +5,6 |
| d_slope | 13,9 / 13,5, +0,4 | 7,9 / 17,3, **−9,4** | +0,6 |
| d_seq | 13,1 / 16,0, **−2,8** | 11,5 / 10,0, +1,5 | +12,0 |
| d_wkcur | 13,8 / 13,7, +0,2 | 14,4 / 9,1, +5,3 | −3,4 |

Esperança média (pts/op, 12 geometrias): sem filtro **−11,5** (desc) e −17,1 (conf); a favor das escalas intradiárias entre −3,8 e −13,3 (desc), −1,2 e −14,2 (conf); **contra** entre −13,1 e −29,0 (desc) e −31 a −47 (conf).

Leitura:
1. **Contra a tendência intradiária é pior que o acaso nos 3 períodos e em todas as escalas intradiárias** (ex. i_leg, geometria 150/100/750: contra 7,6% / 5,3% / 4,1% × sem filtro 11,2% / 9,1% / 11,4%; esperança −40 / −51 / −72 pts). O dono tem razão num sentido: a contratendência intradiária perde.
2. **A favor da tendência intradiária fica no acaso, ligeiramente acima** (i_leg: 11,9% / 10,0% / 13,6% × 11,2 / 9,1 / 11,4% sem filtro; +0,7 a +2,1 pp), **não acima do breakeven**. A diferença favor−contra vem principalmente do contra piorar, não do favor melhorar.
3. **As tendências diárias não são estáveis:** na descoberta, `d_wkprev` e `conc` pareciam a favor; em jul–ago **inverteram** (contra venceu por 5–9 pp) e em set voltaram a favor por +11 pp. Sinal sem consistência = acaso/regime.
4. `d_seq` teve a relação inversa na descoberta (contra melhor: 16,0% × 13,1%) e inverteu depois.

### Referência do dono: stop 100 / alvo 750, entrada X = 150 (cons), n e esperança em pts (IC 95% por bootstrap de dias)

| escala | modo | desc n / acerto / esp | conf n / acerto / esp | set n / acerto / esp |
|---|---|---|---|---|
| sem filtro | ambos | 1215 / 11,2% / −9,7 [−24;5] | 353 / 9,1% / −24,8 [−50;1] | 203 / 11,4% / −10,0 |
| i_leg | favor | 1156 / 11,9% / −3,7 [−19;12] | 344 / 10,0% / −17,6 [−42;8] | 199 / 13,6% / +9,1 |
| i_leg | contra | 438 / 7,6% / **−40,3 [−59;−19]** | 133 / 5,3% / **−50,9 [−82;−13]** | 73 / 4,1% / −71,9 |
| i_open | favor | 1148 / 11,4% / −8,0 | 326 / 8,7% / −28,4 [−54;0] | 189 / 11,7% / −7,3 |
| i_open | contra | 296 / 9,8% / −22,3 | 99 / 6,1% / −48,3 | 47 / 6,4% / −52,4 |
| i_h1 | favor | 786 / 11,6% / −7,1 | 226 / 10,7% / −12,5 | 134 / 10,5% / −17,5 |
| d_ma20 | favor | 608 / 11,6% / −6,7 | 161 / 6,8% / −48,6 | 99 / 17,3% / +40,1 |
| d_wkprev | favor | 637 / 12,4% / −0,3 | 174 / 6,9% / −43,2 | 115 / 16,7% / +34,5 |
| conc3 | favor | 581 / 12,1% / −1,0 | 147 / 6,1% / −54,7 | 94 / 16,1% / +29,7 |
| conc5 | favor | 417 / 12,1% / −1,6 | 105 / 8,6% / −33,7 | 63 / 17,7% / +42,7 |

Breakeven empírico 12,5% (fill 80–87%; ~9–10 ops/dia; não resolvidas 0,3–0,9%; maior sequência de perdas 30–53 ops; meses positivos 0–33% na descoberta). **Nenhuma célula de nenhuma grade tem limite inferior do IC > 0 em nenhum período** (favor 763/482/217 células com n≥100; esp>0 em 177/106/54; lo>0 em 0/0/0).

## 2. Teste contra o acaso (permutação dos rótulos de tendência, preços reais; 60 permutações)

Cada pregão recebe o rótulo de tendência de outro pregão sorteado (mesmo minuto). Se a tendência não informasse nada, favor−contra seria ≈ 0. Duas geometrias (150/100/750 e mm/150/750), cons. `p` = fração das permutações com dif ≥ observado (9 escalas: Bonferroni ~0,006 por escala).

| escala | período | favor / contra | dif pp | nulo (média ± dp) | p |
|---|---|---|---|---|---|
| i_leg | descoberta | 13,2 / 11,2 | +1,95 | −0,4 ± 1,3 | 0,03 |
| i_leg | confirmação | 11,9 / 7,6 | +4,35 | +0,2 ± 2,2 | 0,05 |
| i_leg | jan–ago | 12,9 / 10,4 | **+2,5** | −0,3 ± 1,0 | **0,02** |
| i_h1 | confirmação | 12,3 / 6,9 | +5,4 | +0,3 ± 3,1 | 0,08 |
| i_h1 | jan–ago | 12,7 / 11,4 | +1,4 | +0,3 ± 1,4 | 0,17 |
| d_wkprev | descoberta → confirmação | +3,1 → −3,7 | | | 0,05 → 0,90 |
| i_open, i_vwap, i_m15 | jan–ago | +0,1 a +0,25 | | | 0,42–0,48 |
| d_ma20, conc3, conc5 | jan–ago | −1,2 / −0,3 / +0,2 | | | 0,77 / 0,48 / 0,48 |

Só **`i_leg`** (a pernada de 750 confirmada) aparece em todos os períodos com o mesmo sinal, e o efeito é de ~+2,5 pp (favor 12,9% × contra 10,4% × acaso por rótulo 11,6%) com a esperança do favor ainda negativa (−6,4 pts contra −13,4 do rótulo aleatório). Ajustando por 9 escalas, p ≈ 0,18: **fraco, não confirmado como achado**.

Ressalva sobre o nulo embaralhado em blocos de 30 min (pedido no escopo, `null.py`, 24 sementes): embaralhar candles M1 injeta saltos entre barras e infla o ruído — a esperança do nulo fica em −30 a −70 pts, muito abaixo dos −10 dos dados reais, e o zigzag de 750 vira instável. Portanto o nulo em blocos **não é comparável em nível**; usei a permutação de rótulos como nulo principal e deixo o embaralhado só em `nulo_resultado.csv` / `nulo_vs_real.csv` (nele o real fica bem acima por construção).

## 3. Regras congeladas na descoberta e testadas na confirmação

Critério (gravado antes): a favor, cons, n ≥ 150, ordenado por esperança na descoberta (nenhuma célula tinha IC > 0, então as 8 melhores). Esperança em pts por operação.

| regra congelada | desc n / acerto × BE / esp [IC] | **conf** n / acerto × BE / esp [IC] | set |
|---|---|---|---|
| conc5, vela, X300, stop150, alvo1000 | 173 / 17,8 × 13,6 / +55,8 [−4;123] | 42 / 12,2 × 13,6 / **−13,4** [−113;103] | −17,0 |
| conc5, vela, X150, 150/1000 | 216 / 17,1 × 13,6 / +51,9 [−8;113] | 47 / 11,1 × 13,6 / −24,2 [−111;74] | +21,8 |
| conc3, vela, X150, 150/1000 | 286 / 15,3 × 13,6 / +27,8 [−21;82] | 65 / 8,1 × 13,6 / −50,1 [−117;33] | +29,3 |
| conc3, todos, X150, 200/1000 | 418 / 18,3 × 17,2 / +27,2 [−17;78] | 107 / 10,5 × 17,2 / −72,7 [−161;22] | +48,3 |
| conc5, vela, X150, 150/750 | 236 / 19,8 × 17,3 / +27,0 [−12;70] | 52 / 14,0 × 17,3 / −26,2 | −12,1 |
| conc5, vela, X300, 150/750 | 184 / 19,4 × 17,3 / +25,9 [−23;78] | 45 / 11,4 × 17,3 / −50,8 | −47,3 |
| conc5, todos, X150, 200/1000 | 298 / 18,1 × 17,2 / +25,2 [−31;87] | 78 / 13,2 × 17,2 / −38,3 | +49,7 |
| d_seq, todos, X150, 100/1000 | 199 / 11,6 × 9,7 / +24,8 [−37;100] | 83 / 12,0 × 9,7 / **+26,1** [−62;108] | +47,2 |

**7 de 8 invertem na confirmação (esperança negativa, acerto abaixo do breakeven); a única que segura (`d_seq`) tem IC que cruza zero nos dois períodos** e é a escala em que, no agregado da descoberta, *contra* era melhor — é o tipo de célula que sobrevive por sorte entre 727. Esperança jan–ago ≥ 0 sempre dentro do ruído.

## 4. Interação com as regras que já se repetiram (liga)

Média ponderada por n em 12 geometrias de referência (stop 100/150, alvo 750/1000, X 150/300/mm). Esperança favor (pts), a favor × contra, desc / conf / set:

| filtro | i_leg | i_h1 | conc5 | d_wkprev |
|---|---|---|---|---|
| nenhum | −8,3 / −5,0 / −4,6 | −6,8 / −4,5 / −28,6 | −3,5 / −44,3 / +12,3 | +4,8 / −52,1 / +36,5 |
| `cedo` (< 11h, DST) | −8,7 / −20,2 / +1,5 | −2,2 / −20,3 / −9,9 | −12,9 / −71,1 / +42,1 | +7,5 / −57,3 / +34,8 |
| `vela` ≥ 2× | −7,9 / **+4,0** / −23,2 | +2,8 / −6,4 / −19,6 | **+19,8** / −38,5 / −15,8 | +5,4 / −61,4 / +32,0 |

`cedo` **piora** na confirmação (a manhã de jul–ago foi pior que o dia: operação sem filtro −20 pts, só `cedo` −39). `vela` melhora o acerto a favor na descoberta (conc5: 14,3% contra 12,3% sem filtro), mas não se sustenta: a única linha positiva na descoberta (conc5+vela +19,8) vira −38,5 na confirmação. Nenhuma combinação liga × tendência tem IC > 0.

## 5. Tamanho de mão e ruína (R$250) da melhor célula congelada

Melhor da descoberta: **conc5, vela, X300, stop150, alvo1000** (perda líquida 157 pts = R$31,40 = 12,6% de R$250; ganho R$199,60; breakeven 13,6%; nulo 13,0%). Jan–ago: n = 215, acerto 16,7% (mas 12,2% na confirmação), esperança +42 pts só pela descoberta. `p` encolhido (n0 = 100) = 15,5% → edge encolhido +22 pts → o motor dá **1 contrato** (mínimo; Kelly 1/4 < 1). Mas partindo de R$250 o **risco de ruína (caixa < R$100) em 215 ops é 66%**, tempo mediano até quebrar ~5 ops (5 perdas seguidas), e a sequência esperada de perdas em 215 ops é ~29 (observada 16). Com a confirmação (−13 pts), o encolhido da amostra toda não passa em teste: **não é uma regra para operar**. A célula que sobreviveu (`d_seq` 150/100/1000, perda R$21,40): ruína 67% / ~8 ops, mesmo com +25 pts de esperança observada. A razão é a mesma de sempre: acerto ~12% e sequência de 30–50 perdas são incompatíveis com R$250.

## Limitações
- Barra M1: a ordem de toque de máxima/mínima dentro da barra é desconhecida; o simulador faz stop vencer o empate (conservador).
- `i_leg` usa zigzag de 750 sobre o caminho da vela M1 (convenção da REGRAS.md), não barras H1 propriamente ditas; M15/H1 entram como inclinação de EMA20.
- Recuo medido da máxima/mínima do dia (X) ou EMA60 M1; não testei recuo como % do último avanço nem outros prazos de ordem (TTL fixo em 10 barras).
- A "rearmar só com extremo novo" é uma escolha de desenho que reduz ops/dia de ~38 para ~9; sem ela os números são mais negativos.
- Poder: com acerto ~12% e n ≈ 1.000, o erro-padrão do acerto é ~1 pp e o do dif favor−contra ~2 pp; dif de 1–2 pp não se distingue do acaso nesta amostra.
- Nulo embaralhado em blocos: ver §2; o nulo principal é a permutação de rótulos.

## Número de testes
1.620 células (13 escalas × favor/contra × 36 geometrias + sem filtro; + filtros cedo/vela em 12 geometrias de referência) × 2 convenções × 3 períodos; 8 regras congeladas; 9 escalas × 61 permutações (nulo 2) e 25 sementes (nulo 1, 170 células cada). A pergunta central tem 13 escalas; nenhum resultado positivo sobreviveria a correção de múltiplos testes.
