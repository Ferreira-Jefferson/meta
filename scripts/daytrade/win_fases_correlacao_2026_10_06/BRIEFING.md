# Briefing comum — correlação entre pré-pregão, pregão e pós-pregão do WIN

Pergunta do dono: o comportamento do pré-pregão, do pregão e do pós-pregão se influencia? O que importa no fim é
saber se algo **impacta o PREGÃO**, porque é só no pregão que ele pode operar.

## Dados (não use mais dado do que isto — a janela foi dada pelo dono)

- `data/win_fases_pregao_6m.csv` (separador `;`): 127 pregões de 2026-04-06 a 2026-10-05, uma linha por dia.
  Colunas `pre_*` = leilão de abertura (preço único, volume, nº de negócios, hora do cruzamento ~09:00–09:04);
  `pregao_*` = negociação contínua do leilão até 18:25 (abertura, máx, mín, fechamento, volume, negócios);
  `pos_*` = call de fechamento (leilão a partir de 18:25, cruza ~18:31, preço único).
  Gerado por `scripts/daytrade/win_fases_pregao_6m_2026_10_06.py` a partir dos ticks do WIN$N no MT5.
- Caminho intradiário do pregão: `data/comparativo_win_2026/m1_WIN$N.parquet` (M1, preço cru do contrato
  principal, colunas open/high/low/close/tick_volume/real_volume, índice em horário de Brasília).
  **Regra do dono: WIN só em M5** — reamostre para M5 (09:00, 09:05, …) antes de qualquer análise de caminho.
  Nunca use WIN@ nem WIN@D (preço ajustado).
- Grade oficial da B3: `data/b3_grade_horaria_win.csv` (nesta janela inteira: pré 08:55, pregão 09:00–18:25,
  call 18:25).
- Python: `.venv\Scripts\python.exe` (raiz `C:\Users\Jeffe\Documents\study\meta`). Bash disponível também.

## Definições já usadas na tela do dono (mantenha)

- Variação de preço do pré = leilão de abertura − call de fechamento do DIA ANTERIOR (gap da noite).
- Variação do pregão = fechamento − abertura do pregão.
- Variação do pós = call de fechamento − fechamento do pregão do mesmo dia.
- Δ volume / Δ negócios / Δ volume-por-negócio = % contra a mesma fase do pregão anterior.
- 1 ponto do WIN = R$0,20 por contrato.

## Regras de tempo (não negociáveis)

- Só conta como possível sinal para operar o pregão de D o que é **conhecido no momento da decisão**:
  tudo de D−1 (pregão, call), o leilão de abertura de D, e — para decisões dentro do pregão — só barras M5
  **já fechadas**. O call de D acontece DEPOIS do pregão de D: ele pode explicar o pregão de D (contemporâneo,
  sem uso operacional) ou prever o pregão de D+1, nunca o contrário. Rotule cada achado como
  **preditivo (operável)** ou **contemporâneo (descritivo)**.
- Volume de vela em formação nunca entra (regra do dono).

## Dias problemáticos — trate explicitamente

- 2026-07-31: o pregão só tem negócios a partir de 12:34 (manhã ausente na fonte ou abertura atrasada).
- 2026-09-24: sem leilão de abertura na fonte; primeiro negócio 09:14.
- 2026-10-05: gap de +17.775 pts contra o call de 02/10 — suspeita de troca de contrato no WIN$N (não verificado).
- Possíveis rolagens do WIN$N perto dos vencimentos (WIN vence na quarta mais próxima do dia 15 dos meses pares:
  15/04, 17/06, 12/08, 14/10/2026). Um "gap" que é troca de contrato não é gap de mercado.
  Rode os números com e sem esses dias e mostre os dois.

## Método (n = 127 é pequeno — seja honesto)

- Para toda relação, reporte n, tamanho de efeito (Spearman ρ e/ou diferença de médias em pontos), e um
  **nulo por permutação** (embaralhar a variável-alvo entre dias, ≥ 5.000 vezes) — não só p-valor paramétrico.
- Você vai testar muitas relações: reporte quantas testou e aplique correção para múltiplos testes
  (Benjamini-Hochberg). Diga quantas sobrevivem.
- Estabilidade: repita nas duas metades da janela (abr–jun × jul–out) e diga se o sinal se mantém.
- Para todo achado que pareça operável, traduza em pontos/R$ por contrato e lembre que custo e deslize existem
  (não precisa simular estratégia; basta o tamanho do efeito contra a variação típica).
- Não dê veredito do tipo "isso é bom/vale a pena". Entregue números, observações e hipóteses. O dono decide.
- Não use dados fora da janela para "validar" — isso queima a base.

## Entrega

Crie sua subpasta em `scripts/daytrade/win_fases_correlacao_2026_10_06/<sua_lente>/` com o script (reprodutível)
e um `RESULTADO.md` com as tabelas. Na resposta final devolva: (1) tabela-resumo dos achados com n, efeito,
p de permutação, q de BH, estável nas duas metades (sim/não), rótulo preditivo/contemporâneo; (2) até 5 hipóteses
novas que os dados sugerem e que valeria olhar; (3) problemas de dado encontrados.
