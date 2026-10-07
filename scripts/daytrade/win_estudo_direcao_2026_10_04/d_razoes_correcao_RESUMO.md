# D - Razoes impulso/correcao e estrutura fractal (WIN@D M1, 2021-10-01..2026-10-01)

Metodo: zigue-zague sobre fechamentos M1 por pregao (barras >=300; 6 dias curtos de 325-351 barras mantidos; sessao 09:00-17:54/18:24 conforme horario de verao). Limiar = k x ATR14 diario (media simples de TR) de D-1; primeiras 14 sessoes descartadas (1.234 dias: IS 796 / OOS 438). MACRO k=0,5, MICRO k=0,10 (principal); sensibilidade 0,35/0,07 e 0,75/0,15. Razao = correcao / impulso anterior, so pivos confirmados. Predicao: apos confirmar a correcao, o que vem primeiro - superar o extremo do impulso ("A") ou perder a origem ("B"); P = A/(A+B), pernada nao decidida no pregao fica fora. Tamanhos em % da abertura do dia (ajuste por diferenca: aproximado). Nulo: 5 embaralhamentos dos retornos M1 dentro de cada dia (mesmo ATR, mesmos limiares, mesmo zigue-zague); z = (real - media nulo)/sqrt(ep_bootstrap_por_dia^2 + dp_entre_sementes^2). Script: d_razoes_correcao.py. CSVs: d_razoes_correcao_{hist_razoes,fib_bandas,predicao,pernadas,dia,autossimilaridade,dia_previsao}.csv (3 configuracoes; ';' e virgula decimal).

## Descritivo (config 0,5/0,1)
- Pernadas macro: IS 416 / OOS 241 (so ~0,5 por dia; 0,35 ATR da ~1,5/dia). Tamanho mediano-media 0,89% (IS) / 1,18% (OOS) da abertura = 0,77 / 0,82 ATR. Real e nulo quase identicos.
- Dentro de cada pernada macro: 2,7 micro-impulsos e 2,7 micro-correcoes (IS); 2,4 (OOS) - o nulo tem MAIS (3,0 / 2,7): o real tem ligeiramente menos micro-oscilacoes (pernada mais "limpa").
- Maior devolucao interna / tamanho da pernada (a "subiu 100, devolveu 20"): media 0,275 IS / 0,242 OOS, mediana 0,246 / 0,214, dp 0,14. Nulo: 0,284 / 0,266. Real menor que o nulo em ~0,01-0,025 nas duas janelas (pernada macro um pouco mais limpa que o acaso), efeito pequeno.
- Razao micro-correcao/micro-impulso media dentro da pernada: 0,63 IS / 0,60 OOS (nulo 0,65 / 0,62).

## Tabela de achados
| achado | IS | OOS | nulo embaralhado | sobrevive? |
|---|---|---|---|---|
| Pico micro em 38,2% | share 2,6% (n=13.614) | 2,6% (n=6.753) | 2,8% / 3,0% | NAO (abaixo do nulo, z -0,8 / -1,6) |
| Pico micro em 50% | 3,5% | 3,4% | 3,5% / 3,3% | NAO (razao 1,00) |
| Pico micro em 61,8% | 3,8% | 4,1% | 3,6% / 3,4% | Fraco: razao 1,07 / 1,18, z 1,5 / 1,9, mesmo sinal nas 2 janelas, nenhuma passa de 2; nao confirmado nas outras 2 configs |
| Pico macro em 38,2/50/61,8 | n=110 / 74 (0,5) ou 641 / 350 (0,35) | idem | dentro de 1-2 dp | NAO (50% da 1,3-1,5x acima do nulo nas duas, z~1,1, nao significativo; 38,2 e 61,8 abaixo ou iguais ao nulo) |
| Histograma micro | massa ~0,3-0,6 pp/bin acima do nulo em 0,50-0,80 e abaixo em 0,25-0,45 | idem | - | Parcial: padrao consistente nas duas janelas, mas muito pequeno e difuso (sem pico em Fibonacci); compativel com reversao de curto prazo nos retornos M1 que o embaralhamento destroi |
| Correcao rasa prediz continuacao (P supera extremo) - micro | P cai de 99,0% (r<0,25) a 69,3% (r 0,79-1) | 98,8% a 66,7% | nulo 97,8% a 70,4% / 70,2% | NAO acima do nulo: a queda monotonica existe tambem no embaralhado (mecanica do zigue-zague); difs -1,0 a +1,2 pp, |z|<1,1 na IS; OOS bin 0,79-1: -3,5 pp, z -2,4 (so uma celula; IS foi -1,0 pp) |
| Correcao rasa prediz continuacao - macro | amostra 5-134 por bin, P=82-100% | 83-100% | iguais dentro de 1 dp | NAO (sem poder; n pequeno; 0,35: dif -3 a -4 pp na faixa 0,79-1, z~-0,5) |
| Eficiencia M1 de D-1 -> D (Spearman) | -0,126 (p perm 0,000, n=795) | -0,015 (p 0,77, n=438) | perm 0 +- 0,035 | NAO (IS significativa, OOS some; sinal negativo fraco) |
| Eficiencia zigue-zague de D-1 -> D | -0,059 (p 0,11) | +0,111 (p 0,03) | perm 0 | NAO (sinais invertem) |
| Eficiencia de D-1 prediz continuacao do sinal de D-1 | P(mesmo sinal) 46,4% / 51,7% / 49,4% por tercil; geral 49,2% | 49,3% / 52,7% / 45,2%; geral 49,1% | perm ~49% +- 2,5% | NAO |
| Razao fav/contra do dia (mediana) | 1,47 | 1,52 | 1,52 / 1,51 | = nulo; eficiencia M1 diaria media 5,1% igual ao nulo (o shuffle preserva soma e modulos) |
| Autossimilaridade macro vs micro (KS das razoes) | 0,20 (0,5/0,1) | 0,19 | 0,185 +- 0,005 / 0,18 +- 0,02 | As distribuicoes macro e micro sao parecidas (KS 0,12-0,30), mas tanto quanto no nulo: a semelhanca e propriedade do passeio aleatorio, nao de estrutura do WIN |

Sensibilidade: com as 3 configuracoes (24 celulas de Fibonacci, 27 de predicao x 2 janelas) NENHUMA celula tem |z|>2 nas duas janelas com mesmo sinal (maximos |z| IS 2,5 / OOS 1,9 para Fib; 1,4 / 2,4 para predicao), exatamente o esperado ao acaso.

## Conclusao honesta
1. Nao ha razoes de Fibonacci especiais: 38,2% e 50% nao aparecem acima do embaralhado; 61,8% no micro e a unica insinuacao (+7% a +18% relativo, z<2, nao replicada em outro limiar).
2. Correcao rasa nao prediz continuacao alem do que o zigue-zague ja produz num passeio aleatorio: a relacao "quanto mais rasa, mais provavel superar o extremo" e real mas igual ao nulo. Nao e informacao util.
3. A unica diferenca real vs nulo, repetida nas duas janelas, e pequena: pernadas macro com devolucao interna maxima ~0,01-0,025 menor (mais limpas), e retracoes micro levemente mais fundas (0,5-0,8) em vez de rasas. Sugere leve reversao microestrutural nos retornos M1, nao padrao tradeavel de razao.
4. Eficiencia do dia nao e autocorrelacionada de forma estavel e nao informa direcao do dia seguinte.
Limites: macro com k=0,5 ATR gera so ~0,5 pernada/dia (amostras de 5-30 por bin de predicao), por isso as conclusoes macro sao de baixo poder; eventos micro dentro do mesmo dia sao correlacionados (por isso o ep usa bootstrap por dia); o zigue-zague opera em fechamentos M1 (nao extremos H/L); nulo com 5 sementes (dp entre sementes subestima levemente a incerteza). O embaralhamento preserva o retorno do dia, por isso a previsao de direcao do dia usou permutacao, nao o shuffle.
