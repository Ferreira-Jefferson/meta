# WIN - pernadas em relacao a linha de abertura (parte C)

Script: `c_pernadas_linha_abertura.py` (+ `c_distribuicoes.py`). Tabela completa: `c_resumo_tabela.csv` (por k); por dia `c_dias_k0X.csv`, episodios `c_episodios_k0X.csv`, condicional `c_cond5_k0X.csv`, distribuicoes `c_distribuicoes.csv`.

## Metodo
- Caminho do dia: p0 = OPEN da 1a barra, depois CLOSE de cada M1. 1.233 pregoes (primeiros 14 sem ATR descartados; nenhum com <200 barras). Sessao 09:00-17:54 ou 18:24 (horario de verao), ~555 barras/dia.
- Zigue-zague com reversao minima = K x ATR14 diario ate D-1 (SMA do TR, sem look-ahead), K = 0,1 / 0,2 / 0,3. Perna em curso no fim do dia conta como perna.
- Linha = abertura do dia. Banda morta = 0,05 x ATR(D-1), com histerese (so troca de lado ao passar a banda oposta). Cruzamento = troca de lado. Episodio = trecho continuo de um lado; perna pertence ao episodio onde termina.
- "Nova maxima/minima do dia" = perna de alta cujo fim supera a maxima corrida do dia ate o inicio da perna (idem minima).
- Nulo: 8 embaralhamentos por dia dos retornos M1 (preserva soma e volatilidade do dia, destroi ordem e sazonalidade intradiaria). Os numeros "nulo" sao a media das 8 replicas. Nao rodei bootstrap em blocos.
- IS 2021-10..2024-12 (~800 dias), OOS 2025-01..2026-10 (~430 dias).

## Distribuicoes principais (% dos dias; real vs nulo)
Cruzamentos da abertura por dia (igual para os 3 K):
| cruz. | IS real | IS nulo | OOS real | OOS nulo |
|---|---|---|---|---|
| 0 | 23,8 | 19,6 | 30,6 | 19,4 |
| 1 | 16,5 | 17,8 | 19,6 | 18,3 |
| 2 | 15,5 | 16,2 | 14,2 | 14,9 |
| 3 | 11,9 | 13,0 | 10,5 | 13,5 |
| 4 | 9,1 | 10,3 | 9,8 | 10,6 |
| 5 | 6,9 | 7,7 | 5,7 | 8,8 |
| >=6 | 16,4 | 15,4 | 9,6 | 14,6 |
Media 2,78 (IS) / 2,19 (OOS); mediana 2 / 1.

Pernadas por dia (K=0,2 ATR): mediana 6 (p25 4,5 / p75 8 no IS; 4 / 7,75 no OOS); ~3,3 de alta + ~3,3 de baixa (IS), 3,1+3,1 (OOS); nulo 3,37+3,37 / 3,27+3,27. K=0,1: mediana 19 (IS) / 16,5 (OOS), nulo 19 / 17,75. K=0,3: mediana 3 (p25 2, p75 4), 1,66 alta + 1,63 baixa.
Distribuicao K=0,2 (%): 1:0,9 | 2:2,6 | 3:10,3 | 4:11,2 | 5:14,6 | 6:14,2 | 7:13,7 | 8:9,2 | 9:8,8 | 10:5,7 | 11:3,9 | 12:1,5 | 13:1,5 | >=14:1,9 (IS real). Nulo quase identico (mais caudas leves em 3 e 12).

Novas maximas do dia (pernadas) K=0,2: 1,52/dia (IS), 1,44 (OOS); minimas 1,57 / 1,42; nulo 1,58-1,60. Hora das novas maximas (K=0,2, % das ocorrencias): 9-10h 16 (IS) / 24 (OOS) vs nulo 11 / 10; 10-12h 44 / 38 vs 29 / 28; 12-15h 18 / 22 vs 28 / 28; 15-18h 17 / 10 vs 27 / 25.

Episodios (K=0,2): ~1,9 por lado por dia (IS; 1,6 OOS); duracao mediana 53-54 min (IS), 60-69 (OOS) vs nulo 56-67; excursao maxima mediana ~0,19 ATR (IS), 0,21 (OOS), igual ao nulo; pernadas a favor ~1,2 e contra ~0,55 por episodio (nulo igual).

## Tabela achado | IS | OOS | nulo | sobrevive?
| achado | IS real | OOS real | nulo IS / OOS | sobrevive? |
|---|---|---|---|---|
| Pernadas totais/dia (K=0,2, mediana) | 6 | 6 | 6 / 6 | NAO (identico ao nulo; zigue-zague de passeio aleatorio) |
| Pernadas alta = baixa | 3,30 / 3,26 | 3,11 / 3,10 | 3,37 / 3,27 | NAO (simetria trivial) |
| Cruzamentos da abertura/dia (media) | 2,78 | 2,19 | 2,81-2,93 / 2,79-2,85 | PARCIAL: real menor em ambos, mas IS so -0,1 a -0,15; OOS -0,65 |
| P(0 cruzamentos: dia todo de um lado) | 23,8% | 30,6% | 19,6% / 19,4% | SIM (direcao igual nas 2 janelas, +4 e +11pp), efeito modesto no IS |
| Novas maximas concentradas 9-12h | 60% | 62% | 40% / 38% | SIM (forte e igual em IS/OOS), mas parte e sazonalidade de volatilidade (o embaralhamento a destroi) e o nulo e "recordes de passeio" |
| Novas max/min depois de 15h | 17% | 10% | 27% / 25% | SIM (mesma ressalva) |
| Spearman(n_pernadas, range/ATR) K=0,2 | 0,08 | 0,18 | 0,09 / 0,11 | NAO |
| Spearman(n_pernadas, abs(dir)/ATR) | -0,12 | +0,04 | -0,06 / +0,01 | NAO (sinal inverte) |
| Spearman(n_alta - n_baixa, direcao do dia) K=0,2 | 0,48 | 0,42 | 0,39 / 0,39 | PARCIAL (acima do nulo ~+0,04-0,09, mas e quase tautologico) |
| P(dia de tendencia = fecha nos 20% do extremo) | 52% | 42% | 51% / 50% | NAO (IS = nulo; OOS abaixo, inconsistente) |
| P(tendencia | poucas pernadas) vs (muitas) K=0,2 | 56% vs 47% | 42% vs 43% | 53% vs 47% / 50% vs 47% | NAO |
| D-1 n_pernadas -> D range/ATR (Spearman, K=0,2) | 0,18 | 0,23 | 0,14 / 0,16 | FRACO: excesso +0,04 a +0,07; boa parte e agrupamento de volatilidade que o ATR normalizado nao remove |
| D-1 n_pernadas -> D n_pernadas | 0,24 | 0,25 | 0,23 / 0,22 | NAO (= nulo) |
| D-1 cruzamentos -> qualquer coisa de D | ~0,0-0,08 | ~0,0-0,08 | igual | NAO |
| D-1 (n_alta - n_baixa) -> direcao de D | 0,04 | -0,00 | 0,01 / 0,02 | NAO |
| Cond: acima da abertura, k pernadas de alta, P(nova max do dia depois) K=0,2 | k1 52% k2 40% k3 32% | 50% 39% 30% | 55% 45% 35% / 53% 43% 33% | PARCIAL: cai com k tanto no real quanto no nulo (mecanico); real 2-5pp abaixo do nulo nas duas janelas (mais "esgotamento") |
| Cond: P(voltar abaixo da abertura) K=0,2 | k1 58% k2 32% k3 21% | 51% 29% 24% | 59% 35% 23% / 60% 35% 25% | NAO/FRACO (cai com k igual ao nulo; real 1-6pp menor, n pequeno em k>=3) |
| Cond K=0,1 (n grande), P(voltar abaixo) | k1 71% k2 52% k3 39% k>=4 21% | 65% 46% 35% 17% | 72 53 42 23 / 72 55 43 24 | FRACO: real 1-8pp abaixo do nulo nas duas janelas, direcao consistente, magnitude pequena |

## Conclusao honesta
1. A contagem de pernadas (por dia, por episodio, alta vs baixa) e indistinguivel de um zigue-zague de passeio aleatorio com a mesma volatilidade: medianas iguais, distribuicoes quase sobrepostas. A pergunta "quantas pernadas tem uma subida?" tem resposta (~1,2 a favor e ~0,55 contra por episodio acima da abertura em K=0,2, ~2,9 e ~2,0 em K=0,1) mas o nulo da a mesma resposta - nao e estrutura do mercado.
2. O que difere do nulo, de forma consistente nas duas janelas: (a) o preco passa mais dias inteiros de um lado da abertura (P(0 cruzamentos) 24%/31% vs 19-20%) e cruza menos vezes na media; (b) novas maximas/minimas do dia se concentram em 9-12h (~60% vs ~40%). (b) em parte reflete sazonalidade intradiaria de volatilidade, que o embaralhamento diario destroi - e um nulo generoso; um nulo que preserve o perfil por minuto reduziria o excesso (nao testado).
3. Probabilidades condicionais "acima da abertura com k pernadas de alta": queda de P(volta abaixo) com k e queda de P(nova maxima) com k sao majoritariamente mecanicas (aparecem igual no nulo). O excesso real e de 1-8pp, consistente em sinal, nao em magnitude, e nao verifiquei utilidade operacional (nem custo).
4. Nada disso preve o dia seguinte alem do agrupamento de volatilidade (n_pernadas D-1 -> range D, rho~0,2, so ~0,05 acima do nulo); direcao de D nao e prevista por pernadas/cruzamentos de D-1. Numero de pernadas nao distingue dia de tendencia de dia lateral.
5. Limites: nulo apenas por embaralhamento (sem blocos, 8 replicas); K e banda escolhidos por convencao (0,05 ATR de banda); OOS mostra regime diferente (menos cruzamentos, menos dias de fechamento extremo) - o IS nao reproduz tudo no OOS; contagens por k>=3 com K=0,3 tem n minusculo (5-33 eventos).
