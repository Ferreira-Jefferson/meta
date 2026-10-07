# Lente 4 - auditoria de dado e vieses mecanicos

Script: `auditoria.py` (saida completa em `auditoria_stdout.txt`, tabela A em `A_reversao_mecanica.csv`). Lista de dias a tratar: `dias_flag.csv`.

## 1. Rolagem do WIN$N

Prova: nos minutos em comum, `WIN$N == WINV26` exato (100% dos minutos) de 2026-08-12 em diante; antes, `WIN$N - WINV26` e um degrau constante por trecho.

| dia | evento | degrau medido | gap bruto do CSV | gap real (bruto - degrau) |
|---|---|---|---|---|
| 2026-04-15 | J26 -> M26 | ~+4.2k (estimado pelo residuo contra o IBOV; M26/J26 expirados, nao existem no MT5) | +4415 | ~+200 (+-1k) |
| 2026-06-17 | M26 -> Q26 | +3495 (V26-$N: -7302 -> -3807) | +3350 | ~-145 |
| 2026-08-12 | Q26 -> V26 | +3465 (-3465 -> 0) | +3960 | ~+495 |

- A troca ocorre na abertura do dia de vencimento (diferenca constante o dia inteiro, 06-17 e 08-12). Logo o pregao de D e intra-contrato; so gap/pre-preco de D e Delta contra o dia anterior (preco) sao contaminados. Volume nao mostra anomalia (dV% -6,7 / +18,8 / -9,0).
- **2026-10-05 (+17.775 pts) NAO e rolagem.** WIN$N, WIN@ e WINV26 sao identicos; WINZ26 tambem salta (+8,2%); o IBOV fecha +7,9% (192.115 -> 207.277) e WIN fecha-a-fecha confere (+14.790 vs +14.797 do IBOV). 1o turno da eleicao foi 04/10. Gap real de mercado, leilao so cruza 09:04:16. E o ponto de maior alavancagem do conjunto: sd do gap 1889 pts com ele, 1043 sem; media 351 vs 116 sem rolagens+10-05.
- 2026-04-08 (+4875): real (fecha-a-fecha WIN +3620 vs IBOV +3942). Demais gaps > 1400 pts (04-13, 04-30, 05-06, 05-15, 05-25, 09-03, 09-08, 09-14) batem com o IBOV; sao de mercado.
- Proxima rolagem (14/10) fica fora da janela.

## 2. Dias estranhos

- **2026-07-31: aconteceu de verdade.** 1o negocio 12:34 em WIN$N, WIN@, WIN@D, WINV26, WINZ26 (via MT5); IBOV/PETR4/VALE3 so abrem 12:45 (normal: 10:00). Abertura atrasada de mercado, nao falta de dado.
- **2026-09-24: falta de dado, nao evento.** M1 (parquet, WIN@, WINV26, MT5) tem barras de 09:02 a 18:24, com 143.495 contratos no 1o minuto (leilao). O tick-feed do MT5 (WIN$N e WINV26) so comeca 09:14:00.161; ate 09:13 faltam ~12 minutos de ticks (~1,0M contratos). Acoes abriram 10:02 normal. Efeitos no CSV: pre = vazio, abertura 185.965 (M1: 186.575, -610 pts), volume -5,2%.
- Conciliacao CSV x M1 em todos os 127 dias: volume do CSV e -0,45% do M1 (sd 0,1, constante: M1 inclui o minuto 18:24:59/leilao), abertura +-20 pts, max/min iguais em 118+ dias. Outliers: 09-24 (-5,2%), 08-10 (-3,2%, ticks faltando 10:00-10:06), 05-06 (-2,4%, ticks faltando 09:16-09:22). Maxima/minima divergentes: 04-10 (-415), 04-09 (-55), 07-09 (-70), 08-12 (-30), 07-24 e 07-29 (+65).
- Feriados reais ausentes (04-21, 05-01, 06-04, 09-07): coerente com o calendario B3. Nao ha meia-sessao na janela (nao ha 24/12, 31/12, quarta de cinzas). Todos os 127 call a 18:31.
- 2026-09-28: `pregao_hora_inicio` 09:03:40 contra leilao 09:02:40 (1 min; definicao).

## 3. Vieses mecanicos (n=127; nulo = embaralhar o NIVEL entre dias 2000x e recalcular delta%)

**(a) Delta% contra o dia anterior.** Sob niveis independentes a autocorrelacao lag-1 do delta% ja sai ~ -0,47 (Spearman, IC 95% do nulo [-0,60;-0,33]), e delta%_D vs nivel_(D-1) sai ~ -0,68 a -0,70.

| serie | rho1 do nivel | rho1 do delta% real | rho1 do delta% sob nulo | rho(delta%_D, nivel_D-1) real | idem nulo |
|---|---|---|---|---|---|
| pre_volume | +0,57 | -0,40 | -0,47 | -0,47 | -0,68 |
| pre_negocios | +0,37 | -0,43 | -0,48 | -0,55 | -0,70 |
| pregao_volume | +0,38 | -0,30 | -0,47 | -0,52 | -0,68 |
| pregao_negocios | +0,79 | -0,26 | -0,48 | -0,26 | -0,68 |
| pregao_vn | +0,82 | -0,33 | -0,49 | -0,32 | -0,69 |
| pos_volume | +0,40 | -0,56 | -0,46 | -0,48 | -0,67 |
| pos_negocios | +0,53 | -0,55 | -0,48 | -0,47 | -0,70 |
| pos_vn | +0,49 | -0,52 | -0,48 | -0,52 | -0,69 |

Consequencia: qualquer "delta%_D explica/prediz delta%_(D+1)" ou "delta%_D vs nivel de ontem" mostra rho negativo de ~ -0,3 a -0,5 por construcao. Os reais estao dentro do IC do nulo (exceto pos_*, ligeiramente mais negativos: -0,55 vs -0,48, sem folga estatistica). Nao existe "reversao" a descobrir nesses pares. Alternativa sem o vies: usar nivel (ou log-nivel) de D contra nivel de D-1, ou delta% contra media movel de 5 dias anteriores.

Variante para precos: `Delta pos_D = call_D - fechamento_D` e `gap_(D+1) = pre_(D+1) - call_D` compartilham call_D com sinal oposto. Spearman real = -0,08 (Pearson -0,29, puxado pelo 10-05). Acoplamento mecanico esperado = -sd(dpos)/sd(gap) = -0,06 (todos) a -0,11 (sem 10-05). Pequeno.

**(b) Volume x amplitude por construcao.** Spearman volume x (max-min) = 0,585; negocios x amplitude 0,158; volume x negocios 0,654; volume x amplitude controlando negocios 0,645; volume x |fech-abert| 0,328; dV%_D x amplitude_D 0,43. Qualquer variavel que carregue volume do proprio D (inclusive dV% e volume do call de D) correlaciona ~+0,4 a +0,6 com amplitude de D sem informacao causal. Teste limpo (sem termo comum): amplitude_D vs volume_(D-1) = +0,06; amplitude_D vs amplitude_(D-1) = +0,02 (n=126). Ou seja, o volume de ontem nao diz nada da amplitude de hoje nesta janela; o que correlaciona e simultaneo.

**(c) Razao de razoes (dVN% = delta% de volume por negocio).** dV% x dN% = +0,87 e dV% x dVN% = +0,71 (mecanico: VN = V/N). Pos-fase e pre-fase: cauda pesada: dV% pre curtose 22, |z| max 7,2 (07-09); dV% pos curtose 23, max +247% (05-11), dN% pre max +331%; dVN% pos max +292%. Pearson vs Spearman divergem: dVN% pos x dV% pos 0,46 vs 0,24. Para pre_volume, 07-31 e 09-24 tem volume 0 e viram NaN/inf (Pearson devolve NaN). Use Spearman e/ou log-razao; fases pre e pos sao as mais sensiveis (pouco volume, poucos negocios: 35-130).

**(d) Calendario.** Volume medio por dia da semana (mi): seg 16,3 / ter 17,5 / qua 17,8 / qui 17,4 / sex 16,4 (Kruskal por permutacao p=0,037); amplitude: 2661 / 2842 / 3471 / 3229 / 3049 pts (p=0,057). Delta% de volume medio por dia: +2,4 / +8,8 / +3,0 / -1,6 / -6,4%: um dia-da-semana alimenta correlacao falsa em qualquer delta% contra variavel que dependa do dia (ex.: sexta com volume baixo seguida de segunda). |gap| mediano seg-ter 555-635 pts vs qui-sex 368-392 (gap de segunda cobre fim de semana). Dias pos-feriado: gaps +120/-490/+370/+2880, volume normal (17,5-18,7 vs media 17,1). Vencimentos (04-15, 06-17, 08-12): volume nao se descola (16,0/19,6 [06-17]/15,0), efeito e no gap (roll), nao no volume.
Efeito de limpar: Spearman gap x variacao do pregao = -0,23 com todos os 127; -0,18 sem rolagens+10-05+07-31+09-24 (n=121) (Pearson -0,20 -> -0,14).

## 4. Poder estatistico (Spearman, Fisher com var (1+rho^2/2)/(n-3); MC conferido)

| cenario | n | menor |rho| com 80% de poder |
|---|---|---|
| alfa=0,05 (1 teste) | 126 | **0,25** |
| alfa=0,01 | 126 | 0,31 |
| alfa=0,05/20 | 126 | 0,34 |
| alfa=0,05/100 (limiar do 1o rank do BH com 100 testes: p<=5e-4) | 126 | **0,38** |
| alfa=0,05 | 63 (cada metade) | **0,36** |
| alfa=5e-4 | 63 | 0,54 |

- Para ser "significativo" (p<0,05) basta |rho|>=0,175 (n=126), mas so com 56% de poder em rho=0,20 e 37% em 0,15. Com BH/100 testes o rho minimo para p<=5e-4 e 0,30 em n=126; poder em rho=0,30: 39%; em rho=0,35: 64%.
- P(>=1 falso positivo em 100 testes nulos a 0,05) = 99,4%; esperados 5.
- Em cada metade (n~63) so |rho|>=0,25 passa a 0,05 e |rho|>=0,36 tem 80% de poder; "estavel nas duas metades" para rho verdadeiro ~0,25 acontece em menos de metade das vezes (poder 47% por metade). Falha de replicacao entre metades NAO refuta efeito de ~0,2-0,3; replicacao entre metades de rho pequeno e tao provavel quanto cara-ou-coroa.
- Dependencia: niveis tem autocorrelacao (volume pregao rho1=+0,38, negocios +0,79, |gap| -0,20, amplitude +0,02); em series persistentes (negocios, vn) o n efetivo e menor que 126 e a permutacao simples entre dias e anticonservadora; use permutacao por blocos ou compare via diferencas.

## Resumo para as outras lentes
1. Excluir/tratar os dias do `dias_flag.csv` (3 rolagens para tudo que use gap/pre-preco; 07-31 e 09-24 fora; 10-05 sempre com e sem).
2. Nunca interpretar rho negativo entre delta%_D e delta%_(D+1) ou nivel_(D-1): ~ -0,47/-0,68 por construcao.
3. Volume e amplitude do mesmo dia: +0,4 a +0,6 sem informacao.
4. Teto de afirmacao: so |rho| >= ~0,30 (n=126) sobrevive a BH com ~100 testes; abaixo disso e hipotese.
