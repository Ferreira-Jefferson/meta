# Teoria dos jogos e probabilidade aplicadas ao robô de WIN

Guia aplicado. Constantes do WIN usadas em todos os exemplos: **R$0,20 por ponto por contrato**, tick de 5 pts (= R$1,00), margem/capital mínimo prático ~R$250 por contrato. Os números de exemplo (custo, nº de trades, probabilidades) são ilustrativos; os fatos do WIN em 2026 vêm do contexto da pesquisa (direção não prevista fora de um mês; horário, ondas de volatilidade, razão de variância 0,81 na 1ª hora).

Convenção: **1R** = perda no stop. Alvo = b·R. p = chance de bater o alvo antes do stop. q = 1−p.

---

## 0. A conta que organiza tudo

Se a direção é ~aleatória (passeio sem tendência), a ruína do jogador dá, sem custo:

    p = stop / (stop + alvo)          (só a distância importa)

Esse é exatamente o **breakeven**: p_BE = perda/(ganho+perda). A esperança por operação é então **zero menos o custo**:

    E[op] = p·G − q·L − c        com  p = L/(G+L)  ⇒  E[op] = −c

Exemplo: alvo 750 pts (R$150), stop 250 pts (R$50): p = 250/1000 = **25%**. Custo c = 10 pts (R$2, ilustrativo: ~1 tick de slippage/spread + corretagem). E = −R$2 por contrato por operação, para qualquer geometria alvo/stop.

**Consequência central:** a geometria sozinha não cria vantagem; ela só escolhe entre muitos acertos pequenos e poucos acertos grandes (mesma esperança, variância muito diferente). Vantagem real só pode vir de:

1. **p condicional > p nulo** em estados específicos (horário, volatilidade, reversão da 1ª hora). Uma vantagem é um desvio `p_cond − p_BE`, de poucos pontos percentuais.
2. **Custo menor** (menos trades, ordem-limite em vez de mercado, stop como única exceção).
3. **Tamanho variável**: a esperança total é Σ(tamanho_i · E_i); se E_i varia e o tamanho acompanha, o total cresce mesmo com a média simples de E_i quase nula. É o único ganho estrutural "grátis", e só funciona se o estado for identificável antes (sem look-ahead).

---

## 1. Teoria dos jogos no mercado

### 1.1 Informado × desinformado, seleção adversa
- **Kyle (1985)**, "Continuous Auctions and Insider Trading", Econometrica 53(6) — https://www.jstor.org/stable/1913210 — um informado esconde a ordem em meio ao ruído; o formador de mercado ajusta o preço pelo fluxo líquido (λ de Kyle = impacto por unidade).
- **Glosten & Milgrom (1985)**, "Bid, ask and transaction prices in a specialist market with heterogeneously informed traders", J. Financial Economics 14(1) — https://ideas.repec.org/a/eee/jfinec/v14y1985i1p71-100.html — o spread existe mesmo com lucro esperado zero do formador, porque ele perde para o informado e recupera do desinformado.

### 1.2 O que isso significa para quem só entra com limite
Uma limite é uma **opção grátis que você dá ao mercado**. Condicional ao preenchimento, a chance de o preço ir contra você sobe: a limite de compra é preenchida quando alguém vende nela, e vende mais agressivamente quem sabe de algo, ou o preço está atravessando o nível rumo a valores piores.

Modelo mínimo (Glosten-Milgrom em miniatura). Seja π a fração de agressores informados; o preço justo condicional ao fill fica deslocado ≈ π·Δ contra você (Δ = movimento informado). Exemplo ilustrativo: π=10%, Δ=100 pts ⇒ −10 pts de seleção adversa por fill, mais que o ganho de capturar 1 tick (5 pts). **Capturar spread só dá lucro se π·Δ < meio-spread + rebate.** O projeto já viu isso: o bruto maker do WDO (R$0,45) ficou abaixo do custo (R$0,50), e o motor antigo, sem fila, errava o sinal do resultado (ver `LICOES_DE_PRODUCAO.md`). A lógica vale no WIN.

Leituras práticas:
- **Fill imediato é mau sinal; fill lento é melhor** (alguém negociou ali e você estava no fim da fila = fluxo desinformado). Registrar `tempo_até_fill` e o resultado pós-fill, e testar E[op | fill rápido] < E[op | fill lento], é um teste barato da seleção adversa. Também é variável de **tamanho**: mão menor quando o fill foi imediato.
- **Fila**: a calibração de fila (`fidelidade.py`) mede o quanto você é "o último da fila", o estado de seleção adversa máxima. Backtest sem fila é jogo contra um adversário que não existe.
- **Stop a mercado = você vira o taker**: paga o spread ao informado. É correto como seguro, mas o custo precisa estar em c.

### 1.3 Estratégias mistas e imprevisibilidade
Em jogos de soma zero contra um adversário que explora padrões (matching pennies, von Neumann), a estratégia ótima é **aleatorizar** para ser inexplorável. Aplicações, com cautela:
- **Níveis redondos / stops agrupados** (múltiplos de 50/100 pts) são pontos focais de Schelling: muita liquidez e caça de stop. Deslocar limite e stop em poucos ticks de forma pseudo-aleatória evita ser o stop óbvio. Verifique no backtest que o jitter não derruba a taxa de fill além do custo.
- **Horário exato**: o minuto :00 é agitado porque todos agem nele. Aleatorizar ±1-2 min dentro do estado é de graça; aleatorizar fora do estado desperdiça a vantagem.
- Regra: se p_cond não muda com o jitter, ele é grátis e só reduz a chance de ser explorado; se muda, é custo e deve ser rejeitado.

### 1.4 Jogo repetido
Com 1-2 contratos você não move preço e não tem reputação: o jogo que se repete é **contra você mesmo** (disciplina, tamanho, parar). Isso favorece **regras pré-comprometidas** (Kelly fracionário, teto de perda diária) em vez de decisão no calor do pregão. Contra o HFT de livro, a vantagem de quem é pequeno é poder **não operar** nos estados em que o outro lado é o informado.

Para formador de mercado ótimo com inventário: Avellaneda & Stoikov (2008) — https://www.math.nyu.edu/~avellane/HighFrequencyTrading.pdf — o preço de reserva se desloca contra o inventário; base para dimensionar menor quando já se está posicionado.

---

## 2. Valor esperado e dimensionamento

### 2.1 Kelly
Kelly (1956), "A New Interpretation of Information Rate", Bell System Technical Journal — https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf. Thorp (2007), "The Kelly Criterion in Blackjack, Sports Betting and the Stock Market" — https://www.eecs.harvard.edu/cs286r/courses/fall12/papers/Thorpe_KellyCriterion2007.pdf.

Aposta binária (ganha b·R com p, perde 1R com q):

    f* = (b·p − q) / b       fração do capital arriscada por trade

Exemplo (alvo 750/stop 250, b=3). Para p=0,30: f* = (0,9 − 0,7)/3 = **6,7%** do capital em risco. Capital R$2.000: R$133 de risco; 1 contrato arrisca 250 pts × R$0,20 = **R$50**, então 2,7 contratos. Com p=0,25: f* = 0. Com p=0,20: f* < 0 (não opere).

O crescimento geométrico g(f) é uma parábola de pico em f*; passa a zero em ≈ 2f* e fica **negativo acima**. Metade do Kelly dá ≈75% do crescimento com ≈50% da variância. Por isso **Kelly fracionário (¼ a ½)** é regra (MacLean, Thorp & Ziemba, "Good and bad properties of the Kelly criterion").

### 2.2 Kelly com p estimado em 21 dias
Suponha 21 pregões × 3 trades = n=63 operações, acerto observado p̂ = 0,30 contra o nulo 0,25.

    EP(p̂) = sqrt(0,30·0,70/63) = 0,058   ⇒ IC95% ≈ [0,19; 0,41]

O IC inclui p=0,19 (Kelly negativo) e 0,41 (Kelly 21%). z = (0,30−0,25)/0,058 = 0,87: nem se distingue do nulo. Usar f* = 6,7% é apostar no ruído do estimador.

**Encolhimento bayesiano** (Baker & McHale 2013, "Optimal Betting Under Parameter Uncertainty: Improving the Kelly Criterion" — https://www.researchgate.net/publication/262425087_Optimal_Betting_Under_Parameter_Uncertainty_Improving_the_Kelly_Criterion): a estimativa ruidosa é encolhida para um prior e a aposta junto. Com prior normal centrado no nulo (0,25) e desvio 0,02 (pequenas vantagens é o que se espera de mercado quase eficiente):

    peso   = σ²_prior / (σ²_prior + EP²) = 0,0004 / (0,0004 + 0,00333) = 0,107
    p_post = 0,25 + 0,107·0,05 = 0,2554
    f*     = (3·0,2554 − 0,7446)/3 = 0,0072  → 0,7% do capital

**De 6,7% para 0,7%: o Kelly honesto é ~1/9 do ingênuo.** Em R$2.000 são R$14 de risco, menos de 1 contrato (R$50). Conclusão: **com ~21 dias de evidência e stop de 250 pts, o tamanho correto é 1 contrato ou nenhum**. Só se escala quando n cresce (EP cai com √n) e a vantagem persiste fora da amostra.

### 2.3 Discretização do lote e capital pequeno
Com ~R$250 por contrato o tamanho não é contínuo; "mão pequena quando a chance é pior" só existe a partir de 2-3 contratos. Antes disso a decisão é binária. Duas saídas:
- **Dimensionar pelo stop**: stop em ATR menor ⇒ menos R$ por contrato (stop_pts × 0,20) ⇒ mais contratos cabem no mesmo R.
- **Pular o trade** quando a chance está pior (tamanho 0, de graça em custo).

### 2.4 Por confiança e por volatilidade
- Confiança: `contratos = floor( k · f*(p_post) · capital / (stop_pts·0,20) )`, k ∈ [0,25; 0,5], p_post do encolhimento acima. Degraus 0/1/2 de p_post, não de p̂ cru.
- Volatilidade: manter o risco em R$ por trade constante em R. Se a vol dobra e o stop em pts dobra, o nº de contratos cai à metade (vol-targeting). Antes das 11h, no :00 e na abertura de NY o stop é maior ⇒ mão menor, mas é onde nasce movimento; depois das 13h quase nada acontece e o custo fixo c vira o resultado (E = −c por trade).

---

## 3. Sobrevivência

### 3.1 Ergodicidade (Ole Peters)
Peters (2019), "The ergodicity problem in economics", Nature Physics 15:1216 — https://www.nature.com/articles/s41567-019-0732-0. Há crítica (Toda 2024, "Ergodicity Economics is Pseudoscience", https://www.researchgate.net/publication/378283303); o ponto prático (média no tempo ≠ média do conjunto em processos multiplicativos) é matemática aceita e é o que importa aqui.

Exemplo canônico: a cada rodada capital ×1,5 ou ×0,6 com 50%. Esperança do conjunto +5%/rodada. Crescimento no tempo: √(1,5·0,6) = 0,949 ⇒ **−5,1% por rodada**. A média de 1.000 traders sobe; a trajetória típica de cada um morre.

No WIN: arriscar 30% do capital por trade com p=0,30, b=3 (esperança positiva em R) dá g = 0,30·ln(1,9) + 0,70·ln(0,7) = 0,193 − 0,250 = **−5,7% por trade**. Esperança positiva, crescimento negativo. Maximizar valor esperado empurra f para cima; maximizar o crescimento no tempo escolhe f*.

### 3.2 Risco de ruína e drawdown
Aproximação de difusão: P(atingir drawdown D alguma vez) ≈ exp(−2·μ·D/σ²), com μ e σ² por trade em R.

Exemplo: +3R com 0,30 / −1R com 0,70 ⇒ μ = 0,2R, σ² = 3,4 − 0,04 = 3,36.
- P(DD ≥ 20R) = exp(−2·0,2·20/3,36) = **9%**.
- Se a esperança verdadeira for só 0,05R: exp(−2·0,05·20/3,4) = **55%**.
Com 1R = 1% do capital, 20R = 20% de drawdown. O mesmo robô é seguro ou provável de sofrer 20% conforme uma vantagem que não se mede bem em 21 dias. Daí 1R pequeno (0,5-1% do capital) e mão menor em vez de parar.

Ruína do jogador (Feller, vol. I, cap. XIV) é a base da fórmula p = L/(G+L) da seção 0.

### 3.3 Acerto alto com payoff ruim quebra
Alvo 50 pts / stop 250 pts: p_BE = 250/300 = **83,3%**. Um robô com 85% de acerto parece ótimo: E = 0,85·R$10 − 0,15·R$50 = +R$1,00 bruto, e −R$1,00 após custo de R$2. A cauda (−R$50) é 5× o ganho (R$10): 3 stops seguidos (0,15³ = 0,34% por trio, comum em 21 dias × 3 trades) apagam 15 vitórias. É a assimetria negativa ("catar moedas na frente do rolo compressor"). O inverso, "ganhar de balde, perder de colherinha", é p baixo (25-35%) e b alto (3+); o preço é que 6-10 stops seguidos sejam rotina (0,70⁸ = 5,8%), aceitável porque cada um custa 1R.

---

## 4. Combinar sinais fracos

### 4.1 Log-odds (Bayes ingênuo)
Cada sinal i dá uma razão de verossimilhança LR_i. Com independência condicional:

    log-odds_post = log-odds_prior + Σ ln(LR_i)

Um sinal que "acerta 55%" tem LR = 0,55/0,45 = 1,222 (ln = 0,20). Três independentes: odds = 1,222³ = 1,826 ⇒ p = **64,6%**.

### 4.2 Correlação
Sinais do mesmo preço (RSI, estocástico, MM) são quase o mesmo sinal. n_eff = n/(1+(n−1)ρ). Com ρ = 0,5 e n = 3: n_eff = 1,5 ⇒ odds = 1,222^1,5 = 1,351 ⇒ p = **57,5%**. Tratar três correlacionados como independentes superestima a vantagem em ~7 pp, mais que a vantagem inteira.

Regra de projeto: sinais de **fontes diferentes** (relógio, volatilidade, reversão de curto prazo na 1ª hora, estado do livro), não três osciladores do mesmo preço. Teste a correlação entre sinais **no OOS** antes de somar log-odds.

### 4.3 Atualização bayesiana ao longo do pregão
Prior por faixa de horário (Beta(a,b) calibrado no histórico). A cada evento (movimento de 5-15 min na 1ª hora, abertura de NY, :00) atualiza-se o log-odds. Uso da razão de variância 0,81 na 1ª hora (Lo & MacKinlay 1988, https://academic.oup.com/rfs/article/1/1/41/1583037): VR(2) = 1 + ρ₁ ⇒ ρ₁ ≈ −0,19; um movimento de 100 pts em 5 min sugere devolução esperada ≈ 19 pts. Contra custo de 10 pts sobram ~9 pts (R$1,80) por contrato **em teoria**, antes de seleção adversa e fila, e estimado em uma janela (sujeito ao encolhimento da 2.2). Fora da 1ª hora ρ₁ volta a ≈ 0 e o sinal desliga: o prior é condicionado ao relógio.

---

## 5. Constância

Métricas (por mês e por semana, não só no total):
- **Fração de meses positivos** e sua incerteza (com 6-12 meses, ±20 pp: indicativo, não prova).
- **Desvio dos retornos mensais** e razão média/desvio.
- **Sortino**: média / desvio só das perdas (não pune ganhos grandes, coerente com "balde/colherinha").
- **Ulcer Index** (Martin & McCann 1989): UI = √(média dos DD%²), mede profundidade e duração do drawdown; **Martin ratio = retorno / UI**.
- **Lucro / MaxDD** (padrão do projeto) e **tempo no fundo** (dias abaixo do pico).
- **Sharpe deflacionado** (Bailey & López de Prado, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) quando se escolheu o melhor de N testados.

Exemplo, lucro semelhante em 6 meses:

| mês | A | B |
|---|---|---|
| 1 | +400 | +1.200 |
| 2 | +350 | −600 |
| 3 | +300 | +900 |
| 4 | +250 | −300 |
| 5 | +300 | +1.000 |
| 6 | +400 | −400 |
| **total R$** | **+2.000** | **+1.800** |
| meses positivos | 6/6 | 3/6 |
| desvio mensal | R$61 | R$815 |

A ganha mais e é muito mais constante: escolha A. Com n=6 a diferença de constância ainda é fraca, e **a comparação deve ser feita no mesmo risco por trade (mesmo R)**, para a constância não ser só diferença de tamanho de mão.

Desempate sugerido: (1) menor Ulcer / pior drawdown, (2) maior fração de meses positivos **no OOS**, (3) vantagem que sobrevive ao encolhimento, (4) menos parâmetros.

---

## 6. Mapa: conceito → decisão do robô

| Decisão | Conceito | Regra |
|---|---|---|
| Entra ou não | Log-odds, seleção adversa | Só em estado com p_post > p_BE + margem; reduzir/vetar após fill imediato se for pior |
| Tamanho | Kelly encolhido, vol-targeting | 1R = 0,5-1% do capital; ¼-½ Kelly de p_post; degraus 0/1/2 contratos |
| Stop | Ruína do jogador, vol | Distância em ATR; stop é o único taker, incluir seu custo em c |
| Alvo | p = L/(G+L), custo | Alvo que dê p_BE realista (25-35%), não que maximize acerto |
| Horário | Estado condicional | Operar antes das 11h e na abertura de NY; após 13h tamanho 0 |
| Parar no dia | Autocorrelação de perdas | Teto de perda diária como higiene de risco, não como fonte de edge (parada por contagem já foi refutada em outro robô do projeto) |
| Quando escalar | EP ~ 1/√n | Só quando o IC95% de E[op] exclui zero fora da amostra |

---

## 7. As 3 armadilhas

1. **Custo e seleção adversa comem a pequena vantagem.** 1-2 pp de acerto valem R$1-3 por trade no WIN; um tick de custo ou fila mal calibrada inverte o sinal (o projeto viu: motor sem fila previu +R$3,82 e a realidade foi −R$3,00). Meça com fila e custo reais e olhe nº de trades e pregões sem trade antes do líquido.
2. **Comparações múltiplas e sobreajuste.** Testando 100 horários × 20 filtros, ~5 "vencem" por acaso. Pequena vantagem exige n grande, OOS congelado, correção pelo número de testes (Sharpe deflacionado) e checagem da vizinhança da célula vencedora. Em 2026 nenhuma regra de direção sobreviveu fora de um mês: o prior correto é "é acaso".
3. **Kelly sobre p̂ ruidoso e tamanho dependente do resultado recente.** Kelly cru em 21 dias dá ~9× o tamanho justo; subir a mão depois de ganhos ou dobrar depois de perdas leva ao mesmo precipício (acima de 2f* o crescimento do tempo é negativo). Use encolhimento, ¼-½ Kelly e tamanho que só sobe com n e IC.

---

## Fontes
- Kyle (1985) — https://www.jstor.org/stable/1913210
- Glosten & Milgrom (1985) — https://ideas.repec.org/a/eee/jfinec/v14y1985i1p71-100.html
- Peters (2019) — https://www.nature.com/articles/s41567-019-0732-0
- Baker & McHale (2013) — https://www.researchgate.net/publication/262425087_Optimal_Betting_Under_Parameter_Uncertainty_Improving_the_Kelly_Criterion
- Kelly (1956) — https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf
- Thorp (2007) — https://www.eecs.harvard.edu/cs286r/courses/fall12/papers/Thorpe_KellyCriterion2007.pdf
- Avellaneda & Stoikov (2008) — https://www.math.nyu.edu/~avellane/HighFrequencyTrading.pdf
- Lo & MacKinlay (1988) — https://academic.oup.com/rfs/article/1/1/41/1583037
- Bailey & López de Prado, Deflated Sharpe — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Toda (2024), crítica à economia da ergodicidade — https://www.researchgate.net/publication/378283303

Nota: Kyle, Glosten-Milgrom, Peters, Toda e Baker-McHale foram localizados por busca. Kelly, Thorp, Avellaneda-Stoikov, Lo-MacKinlay, Bailey-López de Prado, MacLean-Thorp-Ziemba, Martin-McCann e Feller são clássicos citados de memória; confira os links antes de citar formalmente.
