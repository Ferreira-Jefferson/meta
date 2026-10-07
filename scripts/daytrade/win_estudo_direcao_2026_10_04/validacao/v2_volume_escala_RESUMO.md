# V2: o passado prevê ESCALA (volatilidade)? Validação

Base: WIN@D e WDO@D, M1, 1.219 pregões válidos cada, 2021-10 a 2026-10. Alvo: log(range D / ATR14). Regressão OLS, IC95 por bootstrap (1.000 reorganizações por dia; por semana quando o alvo é diário dentro de semana). Critério de "validado" escrito no topo de `v2_volume_escala.py` antes de rodar. Controles: log(range D-1/ATR), |gap D|/ATR, |ret D-1|/ATR, dia da semana (o ATR14 já está no denominador). Os anos de 2025+ já tinham sido vistos, então a validação vem de ano a ano, WDO e controles.

## Tabela: checagem, resultado, passa?

| checagem | resultado | passa? |
|---|---|---|
| H_VOL (a) WIN, volume relativo 20d, com todos os controles | coef 0,333 (IC 0,177 a 0,480); ganho de R² 0,0133 (sem controles 0,0248) | sim |
| controlando só range D-1 / só gap / só ret D-1 | 0,460 / 0,364 / 0,421, todos com IC > 0 | sim |
| (b) WIN ano a ano 2022..2026 | coef +0,30 / +0,48 / +0,22 / +0,31 / +0,38: sinal positivo em 5/5, IC exclui 0 só em 2022 e 2023 (2/5; exigia 3/5) | não |
| (c) WDO, todos os controles | coef 0,166 (IC 0,023 a 0,303); ΔR² só 0,0041. Sem controles 0,360 | sim (fraco) |
| WDO ano a ano | -0,20 / +0,03 / +0,36 / +0,49 / +0,13; IC exclui 0 em 2/5 (2024, 2025); 2022 negativo | instável |
| (d) razão tercil alto/baixo (range D/ATR médio) | WIN 1,129 (0,963 → 1,087); WDO 1,157 (0,937 → 1,084). Medianas WIN 0,885 → 0,980 | sim (>=1,10) |
| razão por ano, WIN | 1,14 / 1,09 / 1,16 / 1,10 / 1,14 | estável |
| razão por ano, WDO | 0,99 / 1,07 / 1,29 / 1,31 / 1,21 | cresce com o tempo, 2022 sem efeito |
| H_NORM: média 60d | WIN coef 0,103 (IC -0,047 a 0,252); WDO -0,005 | não |
| H_NORM: z-score 60d | WIN 0,019 (IC -0,001 a 0,039); WDO 0,005 | não |
| tendência do volume | log do volume cai 1,4%/ano (WIN) e 13%/ano (WDO); correlação do relvol20 com o tempo 0,03 / -0,05: a normalização de 20d remove a tendência | ok |
| H_UTIL: previsor de tamanho, WIN | relvol 1,129 (rho 0,144); |gap|/ATR 0,987 (rho 0,023); range D-1/ATR 0,992 (rho -0,026) | relvol é o único |
| H_UTIL: previsor de tamanho, WDO | relvol 1,157 (rho 0,177); range D-1/ATR 1,120 (rho 0,172); |gap|/ATR 1,049 (rho 0,059) | relvol e range D-1 quase empatados |
| H_SEMANA: log range W-1 → range W (controle log ATR e nº de dias) | WIN 0,010 (IC -0,136 a 0,143); WDO 0,046 (IC -0,108 a 0,188); anos WIN positivos só em 2026 | não |
| H_SEMANA: volatilidade realizada W-1 | WIN -0,013; WDO 0,042 (ICs cruzam 0) | não |
| H_SEMANA: dias de W, range W-1/ATR | WIN -0,001 (IC -0,091 a 0,086); WDO 0,076 (IC 0,001 a 0,158, passa na borda; 1/5 anos) | não |
| H_MES: log range M-1 → range M (n=59 meses) | WIN 0,067 (IC -0,247 a 0,386); WDO 0,121 (IC -0,149 a 0,437); metades da amostra com sinais opostos | não |
| H_MES: médias de range diário / desvio do retorno diário de M-1 | WIN 1,854 e 0,824, IC > 0; WDO -0,112 e -0,319 (sinais opostos, não replica) | só WIN, não replica |
| H_NR: NR7 bruto (sem controles) | WIN +0,051 (IC -0,007 a 0,106); WDO -0,043 (IC -0,104 a 0,019) | não |
| H_NR: NR7 com controles, amostra toda | WIN +0,106 (IC 0,040 a 0,169), ΔR² 0,0073; WDO +0,091 (IC 0,025 a 0,154), ΔR² 0,0055 | sim |
| H_NR: NR7 ano a ano | WIN positivo em 5/5 (IC exclui 0 em 2022, 2023); WDO positivo em 5/5 (nenhum IC exclui 0) | sim (pelo critério: sinal) |
| H_NR: NR4 com controles | WIN +0,101 (IC 0,048 a 0,159), 3/5 anos com IC > 0; WDO +0,069 (IC 0,012 a 0,129), 1/5 | sim |

## Vereditos pelo critério escrito antes

- **Volume relativo de D-1 prevê escala: INCONCLUSIVO.** Passa em (a) controles, (c) WDO e (d) utilidade, mas falha em (b): sinal positivo nos 5 anos, mas IC por ano exclui zero só em 2 (n≈250 por ano tem pouco poder, e o efeito é pequeno). Falhou exatamente uma condição. Não é reflexo do range de D-1 nem do gap: o coeficiente cai de 0,386 para 0,333 com os controles (ΔR² 1,3 ponto percentual), então tem informação própria, pequena. No WDO o ganho incremental é só 0,4 pp e o efeito some em 2022-2023.
- **Normalização (H_NORM): NÃO VALIDADO.** O efeito existe com a média de 20 dias e some com média de 60 dias e z-score de 60 dias, nos dois ativos. Não é artefato de tendência de volume (a normalização de 20d zera a tendência), mas é sensível à escolha da janela: o que está sendo previsto é "volume de ontem acima do recente", não nível relativo de longo prazo.
- **Utilidade para dimensionar stop/alvo (H_UTIL): relvol é o melhor, mas o efeito é modesto.** Range de D/ATR médio no tercil alto contra o baixo: ×1,13 (WIN) e ×1,16 (WDO). O tamanho do gap e o range de D-1 no WIN não separam nada (razão 0,99); no WDO o range de D-1 chega perto (1,12). Em termos práticos o stop/alvo ajustado por tercil de volume mexeria cerca de 13-16% entre os extremos, e a mediana mostra 0,885 contra 0,980 no WIN.
- **Semana (H_SEMANA): NÃO VALIDADO.** Range ou volatilidade da semana anterior não prevê o range da semana nem dos dias dela além do ATR14, no WIN e no WDO (a exceção marginal, WDO dias de W, IC inferior 0,001 e 1/5 anos).
- **Mês (H_MES): NÃO VALIDADO.** n=59, baixo poder. O range de M-1 não passa em nenhum ativo. As medidas alternativas (média do range diário, desvio do retorno) passam só no WIN e com sinal oposto no WDO, o que as torna achados de uma amostra pequena e comparações múltiplas, não replicados.
- **NR7/NR4 (H_NR): VALIDADO pelo critério formal, com ressalva forte.** Com controles o coeficiente é positivo nos dois ativos (+10% no log do range) e positivo em 5/5 anos. Mas sem controles o efeito não existe (WIN +0,051 com IC cruzando 0; WDO negativo, -0,043; a média bruta do range/ATR em WDO é 0,980 para NR7 contra 1,018 para os demais). Ou seja, o efeito só aparece condicionado ao range de D-1 (quando se fixa o range de D-1/ATR, ser o mais estreito dos últimos 7 dias soma um pouco). É efeito de forma funcional em cima de um controle colinear, pequeno (ΔR² 0,5-0,7 pp), com IC por ano excluindo 0 em 2/5 (WIN) e 0/5 (WDO). Tratar como INCONCLUSIVO na prática; não usar como regra de operação sem teste dedicado. A conclusão da rodada anterior ("só IS, 1,068 vs 0,995") não foi contradita no bruto, mas o controle adicionou um sinal condicional que lá não existia.

## Resumo de uma frase
O único efeito de escala que se sustenta é o volume relativo de ontem (média de 20 dias) com razão ~1,13-1,16 entre tercis, estável no sinal, mas fraco por ano e sensível à janela de normalização. Semana e mês não acrescentam nada ao ATR14. Nenhuma dessas checagens toca na direção.

## Limitações
- Janela OOS (2025+) já tinha sido vista; os anos separados têm n≈250 e IC largo.
- Tercis com corte na amostra toda (leve informação futura nos cortes); só para descrever utilidade.
- Mês: n=59. Muitos testes (cerca de 60 linhas) sem correção; esperam-se ~3 passes por acaso.
- ATR do range (não True Range); ajuste por diferença; bootstrap sem pressupor normalidade, mas ignorando heterocedasticidade entre regimes.
- Volume = tick volume (TICKVOL) do M1, não contratos.

## Arquivos
Pasta `C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_estudo_direcao_2026_10_04\validacao\`: `v2_volume_escala.py`, `v2_regressoes.csv`, `v2_tercis.csv`, `v2_tendencia_volume.csv` (separador `;`, vírgula decimal), este RESUMO.
