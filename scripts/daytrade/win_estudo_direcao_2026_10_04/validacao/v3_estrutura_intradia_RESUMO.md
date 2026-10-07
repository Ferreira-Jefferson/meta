# V3 - estrutura intradia contra nulo que preserva sazonalidade (WIN, replicacao WDO)

Script: `v3_estrutura_intradia.py` (criterio escrito no topo antes de rodar). Saidas: `v3_estrutura_intradia.csv` (todas as celulas, por ano e pooled, real/nulo/sd/n/z), `v3_veredito.txt`.

## Metodo
- Caminho do dia = abertura + soma dos retornos M1; 1.233 pregoes (WIN), ATR14 ate D-1, banda morta 0,05 ATR com histerese, zigue-zague da rodada anterior (K=0,1 e 0,2).
- Nulo novo: por minuto-do-dia, retorno padronizado pelo desvio do dia, permutado entre dias (so entre dias que tem o minuto), reescalado pelo desvio do dia de destino. 20 replicas. Preserva perfil de volatilidade por horario; destroi persistencia de direcao.
- z = (real - nulo) / sqrt(se_real^2 + sd_nulo^2). Criterio: WIN pooled |z|>=3 e |dif|>=2pp no sentido da hipotese; sentido certo em >=4/5 anos (2022-2026); WDO mesmo sentido com |z|>=2.
- Aviso: 2025+ ja foi visto na escolha dos achados.

## Tabela (pooled 2021-10..2026-10)
| hipotese | real WIN | nulo novo | por ano (real vs nulo, 2022..2026) | WDO real vs nulo | passa? |
|---|---|---|---|---|---|
| H1 share novas max/min em 9-12h (K=0,2) | 60,7% | 60,8% (z -0,1) | 57,1/58,9/62,7/61,7/65,8 vs 61,5/61,7/60,9/60,0/60,1 | 61,2% vs 60,6% | NAO |
| H2 P(0 cruzamentos da abertura) | 26,2% | 22,9% (z 1,8) | 24,0/19,8/27,5/28,4/33,5 vs 23,6/21,4/23,6/24,1/21,9 (4/5 anos acima) | 21,2% vs 21,4% | NAO |
| H3 (t=10:30, >=0,3 ATR) P(nao cruzar ate o fim) | 78,0% (n=268) | 71,8% (z 1,9) | 77,8/72,5/78,0/79,3/81,4 vs 72,6/69,2/72,1/72,3/72,2 (5/5 acima) | 80,1% vs 73,4% (z 2,0) | NAO por z (<3), sentido consistente |
| H3 t=9:30 / 10:00 / 11:00 | 62,9 / 68,2 / 84,8% | 59,5 / 64,2 / 79,9% | sentido 3/3, 4/5, 4/5 | 61,2/69,6/83,3 vs 58,2/67,0/78,5 | NAO (z 0,7 / 0,9 / 1,7) |
| H4 (10:00, extremo, nao revisitou) P(fecha mesmo lado da abertura) | 74,7% (n=281) | 73,1% (z 0,3) | 3/5 anos | 79,7% vs 80,2% | NAO |
| H5 K=0,1 k=1 / 2 / 3: P(voltar ao outro lado) | 69,2 / 49,6 / 37,5% | 70,7 / 53,1 / 41,4% (z -1,6 / -2,3 / -2,2) | sentido certo 2/5, 3/5, 4/5 anos | 70,4/52,7/40,7 vs 71,7/54,5/42,8 | NAO |

## Vereditos
- **H1 NAO VALIDADO.** Com o nulo que preserva a volatilidade por horario, a concentracao 9-12h some (60,7% real vs 60,8% nulo). Era 100% sazonalidade de volatilidade (o nulo antigo dava 39-40%). WDO identico (61,2 vs 60,6).
- **H2 NAO VALIDADO (z 1,8).** WIN real 26,2% vs nulo 22,9%; o excesso existe em 4 dos 5 anos mas e pequeno e concentrado em 2025-26 (28,4 e 33,5%; 2022-2023 em linha ou abaixo do nulo). **WDO nao replica: 21,2% vs 21,4%, e 2026 abaixo do nulo (17,3%).** Persistencia de direcao intradia nao e robusta; o "23,8/30,6 vs 19,5" da rodada anterior era em parte o nulo antigo (que dava 19,5; o nulo novo da ~22,9).
- **H3 NAO VALIDADO, mas e a pista mais consistente.** Em todas as 16 celulas (4 horarios x 4 X) o real fica acima do nulo no pooled em WIN e em quase todas no WDO; sentido certo em todos os anos no headline 10:30 (5/5). Excesso de 4 a 6pp (ex.: 10:30, >=0,3 ATR: 78,0 vs 71,8%), z ~1,7-2,0, WDO 80,1 vs 73,4 (z 2,0). Nao atinge o limiar pre-fixado z>=3: com ~270 dias nao ha poder para separar. Inconclusivo na pratica, mas nunca negativo. O condicional bruto (78% de nao cruzar as 10:30) e mecanico: o nulo ja da 72%. P(fechar do mesmo lado): 86,9 vs 83,8% (WIN), 87,3 vs 84,3% (WDO), z ~1,2 e 1,0.
- **H4 NAO VALIDADO.** Fechar do mesmo lado da abertura: 74,7 vs 73,1% (z 0,3); WDO 79,7 vs 80,2%. Fechar alem do preco das 10:00: 55,5 vs 48,6% WIN (z 1,3), 52,3 vs 50,5% WDO. Nada.
- **H5 NAO VALIDADO.** Diferenca real-nulo de -1,5 a -4pp, z -1,6 a -2,3 pooled, sentido certo em 2/5, 3/5 e 4/5 anos (so k=3 passa o criterio b); WDO mesmo sinal, menor, z -1,1 a -1,5. Os "1-8pp abaixo do nulo antigo" encolheram para 1,5-4pp com nulo novo; abaixo do limiar. K=0,2 idem (z -0,5 a -2,2).

## Quantas vezes dispara e quanto sobra (descricao, nao estrategia)
H3 WIN (>=0,3 ATR): disparos 178 (9:30), 223 (10:00), 268 (10:30), 282 (11:00) em ~5 anos = ~35-55 dias/ano (2022-2026 cada ano 24-62). WDO: 160 / 227 / 236 / 233. Movimento restante medio ate o fechamento NA direcao do lado: WIN 10:30 +204 pts (+0,100 ATR; nulo ~0 pts / +0,003 ATR); 11:00 +182 pts (+0,085 ATR); 10:00 +74 pts (+0,038 ATR); 9:30 +150 pts. WDO +0,04 a +0,065 ATR.
H4 WIN (extremo sem revisitar abertura): 281 (10:00), 184 (10:30), 129 (11:00) = ~25-60 dias/ano. Restante medio: +66 pts (+0,043 ATR) as 10:00, +184 pts (+0,090 ATR) as 10:30, +170 pts as 11:00; nulo ~0 (-18 a 0 pts). WDO +0,088 / +0,065 / +0,145 ATR (z 1,3 / 1,0 / 2,1).
Observacao fora do criterio pre-fixado: o retorno medio restante (continuacao) e positivo em WIN e WDO, nulo ~0, em ~4-5 dos 5 anos para os headlines (ex. WIN 10:30: +0,069/+0,139/+0,082/+0,125/+0,109 ATR vs nulo ~0), mas com z 1-2 por celula e dispersao alta (caudas). Isto e uma pista de CONTINUACAO (drift pos-extremo), mais do que de probabilidade de lado. Nao foi um criterio escrito antes, entao so vale como hipotese nova.

## Caminhos
1. H1, H2, H5 descartar como estrutura: era sazonalidade de volatilidade / efeito do nulo antigo; WDO nao replica H2.
2. H3/H4 (continuacao quando o preco esta longe da abertura e o dia ainda nao cruzou ate 10:30-11:00): unica pista com sentido consistente em anos e em dois ativos, mas z<3 e o OOS 2025+ ja foi visto. Caminho: pre-registrar uma celula (10:30, >=0,3 ATR, retorno ate o fechamento em ATR) e testar em dado novo (outubro em diante), ou backtest com entrada limite + custo (fora desta tarefa) para ver se +0,09 ATR (~+180 pts WIN) em ~50 dias/ano sobrevive ao custo e a taxa de nao-preenchimento.
3. Ressalvas: n pequeno (100-300 eventos), eventos de H5 agrupados no mesmo dia (z binomial otimista), 4 horarios x 4 X x 2 desfechos = muitas celulas (sem correcao).
