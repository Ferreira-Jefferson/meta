# PRE-REGISTRO — win_deslocamento_matinal (escrito em 2026-10-04 ANTES de qualquer backtest)

Nada abaixo foi escolhido olhando resultado de backtest. Antes deste arquivo só foram olhados
(a) os resumos do estudo de 2026-10-04 e (b) estatísticas de DADO que não dependem da estratégia:
mediana de volume M1 do WIN e do WDO na janela 10:30–12:30 na IS, e amplitude mediana de barra.

## 1. A regra, em linguagem simples
Todo pregão: anote a abertura. Aos 90 minutos de pregão (10:30 BRT) meça quanto o preço já se afastou
da abertura, em unidades do ATR14 diário (ATR até D-1). Se o preço está a pelo menos X·ATR da
abertura E ainda não passou para o outro lado dela (além de uma banda de 0,05 ATR) em nenhum
fechamento M1 da manhã, o dia é "de fluxo direcional": entre A FAVOR do lado em que o preço está,
com ordem-limite parada no último preço, e saia no fim do pregão (achatamento do motor) ou por um alvo
em ordem-limite. A abertura é a linha de invalidação: o stop vive no lado de lá dela (ou mais perto).
No máximo uma operação por pregão. Não persegue: se a limite não encher em 15 min, o dia passa em branco.

## 2. Mecanismo de cada componente (e o achado que o sustenta)
| componente | por que existe | achado |
|---|---|---|
| deslocamento ≥ X·ATR às 10:30 | dia que se afasta cedo da abertura é dia de fluxo direcional (persistência intradiária); X em ATR para valer igual em dia calmo/agitado e em WIN/WDO | V3/H3: 78,0% não cruza mais a abertura contra 72% no nulo que preserva volatilidade por horário; +0,10 ATR (~200 pts) a favor até o fecho contra ~0 no nulo; 5/5 anos acima do nulo; WDO mesmo sentido (z 2,0) |
| "limpo" (nunca fechou do outro lado da abertura além de 0,05 ATR) | é a definição usada no achado; dia que já cruzou a linha é outro estado | V3, mesma função `estados` (banda 0,05 ATR, histerese) |
| entrar a favor do lado | o drift pós-evento é na direção do lado | V3/H3d (restante em ATR positivo; nulo ~0) |
| stop na linha de abertura (± banda 0,05 ATR), com teto `stop_atr` | a abertura é a linha de invalidação do achado (78% não voltam a cruzar). O teto existe por CAPITAL: o caixa real do WIN é R$250 (margem 100 × 2 × 1,25) e a linha fica a ≥0,35 ATR ≈ R$140 da entrada: um stop cheio deixa R$110, dois seguidos zeram o robô (piso de sobrevivência R$100) | CLAUDE.md "capital mínimo"; item 6.15 de LICOES |
| alvo opcional em ATR (limite real fatiada, sem prazo) | ablação: o drift médio é pequeno (+0,10 ATR) e de cauda longa; saber se realizar parte ajuda ou corta a cauda que paga | V3/H3d (caudas) |
| saída no fim do pregão | o achado mede o "restante até o fechamento" | V3 |
| uma operação por dia, ttl 15 min | o achado é um evento por dia às 10:30; ordem sem prazo preenche horas depois (269,7 min medidos num robô irmão) | CLAUDE.md "ordem de entrada precisa de prazo" |

Fica FORA (refutado ou inconclusivo): direção de D-1/semana/mês, gap como sinal, dia da semana, níveis de D-1,
Fibonacci, contagem de pernadas, 1ª hora, extremos 9-12h, WDO de D-1, corpo/range, eficiência, reversão M1,
NR7, sexta pós-semana-de-baixa. Volume relativo de D-1 só como ABLAÇÃO (seção 6).

## 3. Execução (desenho FECHADO)
EnterLimit no último fechamento (offset 0 ticks), ttl_bars=15 (M1: 1 barra = 1 minuto; reporto o atraso REALIZADO em minutos),
alvo (quando existe) como limite fatiada `exit_split_unit=1`, `exit_ttl_bars=EXIT_TTL_BARS_SEM_PRAZO`, `anchor_exits_at_fill=True`,
stop a mercado (única exceção), achatamento de fim de pregão do motor (confiro que dispara: nenhum trade termina depois do corte).
1 contrato. Montagem por `config_for` / `profile_for("WIN@")`, `target_fills_as_maker=True`.
Capital inicial WIN = margem 100 × MARGIN_BUFFER_FUTUROS 2,0 × RESERVA_CAIXA_SEGURANCA 1,25 = R$250. WDO = 150 × 2,5 = R$375.

## 4. Premissas de FILA (WIN NÃO é calibrado — `fidelidade.py` só tem WDO@; não empresto número)
A base é M1 e o motor desconta o volume INTEIRO da barra que toca o nível da fila (o volume real no nível é ~1/18 dele no WIN:
amplitude mediana de barra 90 pts = 18 ticks). Por isso a premissa é declarada em múltiplos de V̄ = mediana de volume M1 (campo VOL, contratos)
entre 10:30 e 12:30 BRT na IS: **V̄(WIN) = 38.152 → arredondado 38.000**, **V̄(WDO) = 6.681 → 6.700**. Mesma fila na entrada e na saída:
- **P0**: fila 0/0 (otimista; é o motor antigo — serve só de teto).
- **P1**: Q = 1·V̄ = 38.000 (≈ 2,1 mil contratos de fila REAL no nível; ≈ um minuto médio inteiro de negociação).
- **P2**: Q = 2·V̄ = 76.000 (≈ 4,2 mil contratos no nível). É a MAIS PESSIMISTA e é a que decide.

Referência de sanidade: no WDO a fila medida é 329/494 contratos, ≈ 0,3–0,45 do volume no nível (V̄/6 ticks ≈ 1,1 mil); se o WIN se parecer, P1 e P2 são conservadoras.
No WDO replico com P0, a calibrada do `fidelidade.py` (329/494), P1=6.700, P2=13.400.
"Atravessar 1 tick para encher" NÃO é suportado pelo motor sem modificá-lo; não improviso (limitação declarada).
Regra de aceitação: **só é aceita se for positiva (líquido > 0 e R$/op > 0) em P2**.

## 5. Parâmetros livres (3) e grade (12 células) — só IS
Fixos (vindos do estudo, não tunáveis): decisão aos 90 min, ATR14 diário (média de 14 true ranges até D-1), banda 0,05 ATR, ttl 15, offset 0.
Livres:
1. `X` (deslocamento mínimo, ATR) ∈ {0,3 ; 0,5}   (0,3 = headline do estudo; 0,5 = vizinho já medido lá)
2. `stop_atr` (teto do stop em ATR) ∈ {0,15 ; 0,25 ; linha}   (linha = abertura ∓ 0,05 ATR, sem teto)
   — 0,15·ATR ≈ R$60 sobrevive a 2 stops seguidos no caixa de R$250; 0,25 ≈ R$100 a 1; linha ≈ R$140+ a 1 (e nem sempre).
3. `alvo_atr` ∈ {nenhum ; 0,30}   (nenhum = só achatamento)

**Canônica**: X=0,3, stop=linha, alvo=nenhum (a regra "pura" do estudo). Espero que ela seja CENSURADA pelo caixa; a grade existe para o desenho de capital.

## 6. Ablação (só na célula escolhida e na grade inteira como checagem)
`escala_volume`: multiplica `stop_atr` e `alvo_atr` por clip(relvol20^0,33 ; 0,8 ; 1,25), relvol20 = volume(D-1)/média do volume das 20 sessões até D-1
(0,33 = coeficiente de log(range/ATR) em log(relvol20), V2). Só adoto se, na IS sob P2: líquido ≥ +20% E melhora em ≥ 2 de 3 anos E melhora em ≥ 60% das 12 células. Senão fica de fora.

## 7. Critério de escolha na IS (2021-10-01..2024-12-31)
Uma célula é ELEGÍVEL se, simultaneamente:
(a) líquido > 0 em P0 e em P2; (b) ≥ 60 trades em P2; (c) NÃO censurada em P2: sem "ZERADO", pregões com sinal perdidos por falta de caixa ≤ 5% dos pregões com sinal, caixa mínimo ≥ R$100 (margem crua);
(d) PLATÔ: ≥ 2/3 dos vizinhos (células que diferem em UM parâmetro por UM passo) também têm líquido > 0 em P2.
Escolha: a canônica se for elegível; senão a elegível com mais vizinhos positivos em P2, desempate por menor MaxDD R$ em P2 (não por maior lucro).
Se nenhuma for elegível, o veredito é NÃO ACEITA e a OOS roda assim mesmo UMA vez na célula de melhor platô só para registrar (declarado como tal).
Reporto: win% vs breakeven EMPÍRICO perda_média/(ganho_médio+perda_média), n, média R$/op, IC95% por bootstrap de pregões (5.000), estabilidade 2022/2023/2024.
Pregões com sinal e n de sinais por ano são conferidos contra o estudo (35–55/ano) como teste de que a implementação reproduz o achado.

## 8. Protocolo
1. IS: 12 células × (P0,P1,P2) = 36 runs, ≤3 workers, resultado impresso célula a célula.
2. Escolher conforme a seção 7; ablação de volume; escrever CONGELADO.md (config, resultado IS, FAIXA ESPERADA para a OOS) ANTES de abrir a OOS.
3. OOS (2025-01-01..2026-09-30) UMA vez na célula congelada, P0/P1/P2; WDO (mesma regra em ATR, IS e OOS) UMA vez. Sem retoque.

A OOS já foi vista DESCRITIVAMENTE no estudo (a pista veio em parte dela): é SEMI-CEGA. Nenhum parâmetro é escolhido olhando a OOS.

## 9. ADENDO (escrito depois de UM teste de fumaça de infraestrutura, ainda ANTES da grade e SEM olhar a OOS)
O teste de fumaça (IS, célula X=0,3 / stop 0,25 ATR / sem alvo, P0, capital real R$250, 58 s por run) mostrou o que a seção 5 já antecipava:
150 sinais, só 12 operações, caixa final R$84 (< margem crua R$100): em poucos stops o caixa de R$250 zera o robô. Visto isso (e só isso; −R$166 em 12 trades censurados),
registro ANTES da grade a correção de método para separar EDGE de CENSURA — mesma separação que o `wdo_orb` fez em 2026-09-14 ("capital REPOSTO por pregão"):
- **Corrida NOMINAL** (capital R$1.000.000, `enforce_capital_cap=False`, 1 contrato, mesma fila): como há no máximo 1 operação por pregão e nada depende do caixa,
  a sequência de trades é a que o robô faria com capital reposto todo pregão. Responde "o edge existe depois de custo e fila?". NÃO é capital real; é diagnóstico.
- **Caminhada REAL de caixa** (R$250, regra do motor: abre o 1º contrato se caixa realizado ≥ R$100 = margem crua; senão o sinal é perdido), aplicada aos trades da corrida
  nominal e CONFERIDA contra o motor com capital real em células escolhidas. Responde "é censurado pelo capital?" (sinais perdidos, caixa mínimo, ruína). Reporto também a probabilidade de
  travar embaralhando os trades 10.000 vezes e o capital que a IS inteira teria exigido para nunca cair abaixo de R$100.
- Elegibilidade (seção 7) passa a ter dois níveis, ambos reportados: **elegível de EDGE** = (a)+(b)+(d) na corrida nominal; **elegível COMPLETA** = edge + (c) na caminhada real de R$250.
  Para escolher a célula que vai à OOS (UMA vez) usa-se: a canônica se elegível de edge e de platô; senão a elegível de edge com mais vizinhos positivos em P2, desempate pelo MENOR stop médio em R$
  (menor exigência de capital), depois menor MaxDD R$. O veredito "aceita" exige elegibilidade COMPLETA; sem ela o veredito é "edge detectado mas censurado pelo capital real" ou "sem edge", conforme o caso.
- Atraso realizado da entrada em minutos = (rótulo da barra de fill) − (10:30). O achatamento: confiro razão de saída FORCED_FLATTEN e o horário (nas sessões em horário de verão dos EUA o pregão do WIN fecha 17:55 e a última barra é 17:54 BRT).
