# Larry Williams — especificação única (contrato EA MQL5 ⇄ motor Python)

Fonte primária: *Long-Term Secrets to Short-Term Trading* (1999) — PDF
https://atoast2trading.wordpress.com/wp-content/uploads/2012/02/larry-williams-long-term-secrets-to-short-term-trading.pdf
(texto extraído em `C:\Users\Jeffe\.claude\projects\c--Users-Jeffe-Documents-study-meta\d3c8fbd6-322b-4eb1-ac09-fb3c84fe427c\tool-results\webfetch-1791124813540-wya78u.pdf.txt`);
Ultimate Oscillator: https://williamspercentr.com/newsletters/ULTI.pdf ; %R: https://williamspercentr.com/the-original-percent-r

Legenda: **[LIVRO]** regra do próprio Larry · **[SEC]** fonte secundária · **[INTERP]** interpretação (confiança menor, marcada no código e no relatório).
Os valores em US$ do livro viram **fração do range de ontem (R1)** ou **ATR** — conversão = [INTERP].

## Notação
D = dia atual; D-1 = ontem; O,H,L,C = abertura, máxima, mínima, fechamento. R1 = H(D-1) − L(D-1).
"S" = dia do setup (= D-1 quando a entrada é no dia D). Tudo que usa O(D) só é avaliado após a abertura de D;
nada usa H/L/C de D para decidir entrada de D (sem look-ahead). Ordens do dia expiram no fim do pregão (day order, como Larry).

## Setups (cada um selecionável por input no EA; lado compra e lado venda ligáveis separadamente)

### VB — Volatility Breakout [LIVRO cap.4]
- Compra: buy stop em `O(D) + Kc·R1`. Venda: sell stop em `O(D) − Kv·R1`. Kc, Kv independentes (livro: T-Bond 1,0/1,0; S&P 0,4/2,0; padrão MQL5 0,5).
- Primeiro nível tocado vale; se ambos tocados no mesmo candle de resolução, vale o mais próximo de O(D) (documentar).
- Stop inicial: `StopFrac·R1` (livro: 50% de R1 ou US$ fixo) a partir da entrada. [INTERP: US$→fração]
- Saída (modo): BAILOUT (primeira abertura lucrativa depois da entrada; "mesmo que 1 tick"; opção `BailoutAposDias` = esperar N dias, livro usa 0–2) | FECHAMENTO do dia | TEMPO N dias | REVERSAO (sinal oposto).

### OOPS — Oops! [LIVRO cap.7]
- Compra: `O(D) < L(D-1)` (gap abaixo da MÍNIMA de ontem, não do fechamento); entrada buy stop em `L(D-1)` (preço voltando ao range). Venda: `O(D) > H(D-1)`; sell stop em `H(D-1)`.
- `GapMin` opcional (em fração de R1 / ticks) [SEC Unger usa 15 pts no DAX].
- Stop: `StopFrac·R1` ou mínima/máxima do dia. Saída: abertura do dia seguinte ("1½ dia") | BAILOUT | `N` dias.
- Filtros do livro (opcionais, máscara de dias): S&P compra todos exceto qua/qui; Bonds venda só na quarta; Oops de compra após 17º pregão do mês.

### SMASH — Smash Day (naked close) [LIVRO cap.5; stop = SEC]
- Setup em S: compra se `C(S) < min(L(S-1 … S-n))` (n=1 base; livro admite 3–8; Rogue Quant: 8 melhor). Venda espelhada (`C(S) > max(H(S-1…S-n))`).
- Entrada em D: buy stop em `H(S)` (venda: sell stop em `L(S)`), válido só em D.
- Stop: extremo oposto de S (`L(S)` / `H(S)`) [SEC — livro silencioso]. Alternativa `StopFrac·R1`. Saída: BAILOUT | tempo N | RR.
- Filtro opcional de tendência. Outside bar NÃO é excluída (livro não exclui; MQL5 exclui → parâmetro `ExcluirOutsideNoSmash`).

### HSMASH — Hidden Smash Day [LIVRO]
- Compra: `C(S) > C(S-1)` (fecha de alta) E `C(S)` nos 25% inferiores do range de S (param `Zona`=0,25); "melhores": também `C(S) < O(S)` (param `ExigeCloseAbaixoOpen`). Entrada buy stop em `H(S)` em D.
- Venda: `C(S) < C(S-1)`, C(S) nos 25% superiores, (melhores: `C(S) > O(S)`); sell stop em `L(S)`.
- Stop/saída como SMASH. "Hidden Gaps": **não existe fonte** — NÃO implementar; registrar no relatório.

### OUTSIDE — Outside Day com fechamento fora [LIVRO cap.5]
- Em S: `H(S)>H(S-1)` E `L(S)<L(S-1)` E `C(S)<L(S-1)` → SINAL ALTISTA. Filtro: `O(D) < C(S)`. Entrada: compra na abertura de D.
  Como é entrada na abertura (a mercado no livro), no EA/motor há dois modos: `A_MERCADO_NA_ABERTURA` (fiel ao livro, cobra slippage) e `LIMITE_NO_FECHAMENTO_S` (limite em C(S)). Reportar os dois.
- Lado venda (outside com `C(S)>H(S-1)`, `O(D)>C(S)`): livro silencioso → parâmetro `LadoVenda` (default desligado), [INTERP]. Evitar quinta (livro). Stop `StopFrac·R1`/US$; saída BAILOUT.

### GSV — Greatest Swing Value [LIVRO cap.8 — confiança baixa nos detalhes]
- Para cada dia completo j: `Swing1 = H(j-3) − L(j)` , `Swing2 = H(j-1) − L(j-3)`, `GSV_j = max(Swing1,Swing2)` (lado compra); espelhar para venda. Média dos últimos `n` dias (n=1…4; livro: 4 melhor que 10).
- Compra: buy stop em `O(D) + 0,8·média`; venda: `O(D) − 1,2·média` (S&P 1982-98). Só comprar após dia de baixa e vender após dia de alta [INTERP: C(D-1)<O(D-1)].
- Stop `StopFrac` (livro US$1.750), saída BAILOUT. Filtro opcional de tendência intermercado (usar BOVA11/WIN×dólar não é replicável → omitir, registrar).

### WR — Williams %R [LIVRO 1973 via williamspercentr.com; níveis = original]
- `%R = 100·(HH(n) − C)/(HH(n) − LL(n))` (escala 0–100 de Larry; 100 = sobrevendido), n=10 (14 como variação [SEC]).
- Compra (tendência de alta): %R tocou 100, passaram `Espera=5` pregões, e %R volta a `< 95` (param 85–95) → compra na abertura de D (a mercado no livro → mesmos dois modos de OUTSIDE). Venda (tendência de baixa): %R tocou 0, esperou 5, voltou a `> 5…15`.
- Lateral: compra ≤ 90, venda ≈ 10 (opcional). Filtro de tendência obrigatório no livro ("não funciona comprando em mercado de baixa"): ver TENDENCIA.
- Stop `StopFrac·R1`/ATR; saída: BAILOUT | tempo | %R oposto.

### UO — Ultimate Oscillator [LIVRO: artigo S&C abr/1985]
- BP = `C − min(L, C(-1))`; TR = `max(H,C(-1)) − min(L,C(-1))`; A_p = ΣBP/ΣTR em p ∈ {7,14,28}; `UO = 100·(4·A7+2·A14+A28)/7`.
- Compra: divergência altista (mínima de preço mais baixa, mínima do UO mais alta) com a primeira mínima do UO **< 30**; gatilho: UO rompe acima do pico que antecedeu a segunda mínima → compra na abertura seguinte.
- Venda: divergência baixista com UO antes **> 50** (artigo original; param 70 = variante moderna); gatilho: UO rompe abaixo do fundo anterior ao topo.
- Saídas (livro): comprado sai se UO > 70, ou se UO < 45 depois de ter passado de 50; vendido sai se UO ≤ 30, ou UO > 65 depois de ter passado de 50→. + stop de preço `StopFrac·R1`/ATR [INTERP].
- Pivôs do preço/UO: 3 barras (mínima com mínimas maiores dos dois lados), confirmados só com 1 barra de atraso (sem look-ahead).

### TDM — Trade Day of Month [LIVRO cap.6/10]
- Dia de PREGÃO do mês (1…22) contado do primeiro. Compra na abertura do TDM escolhido (param lista; livro: 1º pregão do mês no S&P → 85% acerto, evitar jan/fev/out; Oops de compra após o 17º).
- Saída: stop `StopFrac·R1`/US$, ou fechamento do 3º dia após entrada, ou BAILOUT. Filtro de máscara de meses.

### TDW — Trade Day of Week [LIVRO cap.4/6]
- (a) Como FILTRO em qualquer setup: máscara de dias de compra e de venda. (b) Setup próprio: compra na abertura dos dias da máscara, saída no fechamento (variação abertura→fechamento é a medida de Larry); S&P: segunda 57%.

### TRES_BARRAS — Three-Bar High/Low [LIVRO cap.9; INTRADIÁRIO M5/M15 — única regra explicitamente intradiária dele]
- SMA(3) das máximas e das mínimas. Compra: ordem LIMITE no SMA3(mínimas) só se tendência por swing = alta; alvo: ordem limite no SMA3(máximas). Venda espelhada só em tendência de baixa. Stop de proteção `StopFrac` (a mercado). Zera no fim do pregão. Só WIN/WDO (M1 → M5/M15).
- Esta é a única que naturalmente cumpre o desenho "fechado" do repo (entrada e alvo em limite).

## TENDENCIA (filtro compartilhado) [LIVRO cap.1/9]
- Short-term low: mínima com mínimas MAIORES nos dois lados (3 barras); short-term high espelhado. Inside days ignorados. Confirmação só depois que a barra seguinte se completa (sem look-ahead).
- Tendência de ALTA: o preço rompeu para cima o último short-term high mais recentemente do que rompeu para baixo o último short-term low (baixa: inverso). Alternativas de comparação: `NENHUM` | `SWING` | `SMA(n)` (C > SMA n).

## Execução, custos e honestidade
- **Desvio declarado do CLAUDE.md:** o desenho "fechado" do repo proíbe entrada a mercado; entradas por rompimento (VB, SMASH, HSMASH, OOPS) são buy/sell STOP — viram mercado ao disparar. A pedido do dono o EA reproduz Larry fielmente; o motor cobra `SlippageTicks` por entrada disparada e reporta a sensibilidade (0/1/2 ticks). Só TRES_BARRAS é 100% limite. Isto vai no relatório final como limitação, não é escondido.
- Resolução intradiária: WIN/WDO usam M1 para ordenar eventos dentro do dia; ações/ETFs só têm barra diária → convenções: se entrada e stop caem no mesmo candle, assume-se o PIOR (stop executado); ambos níveis de entrada tocados → o mais próximo da abertura primeiro. Declarar em cada resultado.
- Capital inicial = mínimo real do instrumento (CLAUDE.md): ação `preço·100·2`; WIN R$250 / WDO R$375 (sizing com reserva). Futuro segurado overnight exige margem de carregamento ≠ day-trade → registrar no relatório.
- Custos: usar `backtest/intraday/costs.py` (B3_EQUITY_EXCHANGE_FEE_PCT_PER_LEG, corretagem, deslize) — não digitar à mão.
- Tabela de saída: 12 colunas fixas de `backtest/intraday/report.py` (variante, retorno, líquido R$, MaxDD %, MaxDD R$, lucro/DD, win%, trades, R$/dia, trd/dia, capital final, pregões) + `extras` depois; BR decimais; sempre ao lado do nulo `breakeven empírico` (CLAUDE.md "What NOT to do").
