# WIN: persistencia dia -> dia (a_persistencia_diaria)

Script: `a_persistencia_diaria.py`. Tabelas completas (todas as linhas, IC, nulo, p): `a_persistencia_diaria_tabelas.md` e CSVs `a_*.csv`. Base diaria: `a_diario.csv`.

## Dados e tratamento
- WIN@D M1, ajuste por diferenca: diferencas em PONTOS sao exatas, entao a direcao (sinal) e os pontos sao exatos; percentuais sao aproximados (preco ajustado ~170 mil de mediana). Normalizacao por ATR(14) diario (conhecido antes de D).
- Pregao: abertura = OPEN da 1a barra (09:00 na grande maioria), fechamento = CLOSE da ultima barra (18:24 no horario normal, 17:54 no outro regime de horario de verao dos EUA). Mediana 565 barras/dia.
- Excluidos: 5 dias que abrem 13:00 (quartas de cinzas, 325 barras: 2022-03-02, 2023-02-22, 2024-02-14, 2025-03-05, 2026-02-18), 2026-07-31 (351 barras, abre fora do normal) e 2026-10-01 (incompleto, para 17:17). 14 dias com gap == 0 saem das taxas de gap.
- IS 2021-10..2024-12: 791 dias. OOS 2025-01..2026-09: 434 dias.
- Nulo = taxa incondicional na mesma janela. p = binomial (aprox. normal) contra o nulo, sem correcao; sao ~170 linhas de teste, entao ~8 "significativas a 5%" aparecem so por acaso.

## Resposta direta a pergunta do dono
| pergunta | IS | OOS | nulo (taxa-base) |
|---|---|---|---|
| Fechou em ALTA (cc) -> abre em alta | 42,0% (n=386) IC [37,1;46,9] | 44,7% (n=215) [38,2;51,3] | 49,9% / 52,0% |
| Fechou em ALTA -> abre em BAIXA | 58,0% | 55,3% | 50,1% / 48,0% |
| Fechou em BAIXA -> abre em ALTA | 57,8% | 59,7% | 49,9% / 52,0% |
| Dias com "D-1 alta E gap baixa" (fracao de TODOS os dias) | 28,3% | 27,4% | (se independente: ~25%) |
Ou seja: "fechou em alta e abriu em baixa" acontece em mais da metade das vezes (55-58%) e e NORMAL; na verdade e mais comum que abrir em alta. O gap tende a reverter a direcao de D-1. Tamanho: gap medio apos D-1 alta = -73 pts (IS) / -38 pts (OOS); apos D-1 baixa = +51 / +92 pts, contra |gap| tipico de 430-490 pts (~0,25%) e ATR ~1.900-2.200 pts. Efeito real, mas pequeno (~0,03-0,05% do preco, ~+-8pp na frequencia).

## Tabela de achados
| achado | IS | OOS | nulo | sobrevive? |
|---|---|---|---|---|
| Gap tende a ser CONTRA a direcao de D-1 (cc) | -7,9pp (p=0,002) | -7,3pp (p=0,03) | 50% | SIM nas duas, mesmo sinal, efeito pequeno |
| Idem, direcao do candle (C>O) de D-1 | -9,1pp (p=0,0002) | -4,7pp (p=0,16) | 50% | Parcial: sinal igual, OOS nao significativo |
| Fechou perto da maxima (>80% do range) -> gap alta | 33,5% (n=212) | 42,5% (n=87) | 49,9/52,0 | Sim em sinal; OOS p=0,08 |
| Fechou perto da minima (<20%) -> gap alta | 62,0% | 68,2% | 49,9/52,0 | SIM (p=0,001 / 0,003) |
| Retorno de D-1 em quintis (Q5 forte) -> gap alta | 39,2% | 42,2% | 49,9/52,0 | Sim em sinal (p=0,008 / 0,07); gradiente monotono Q1 62,7% -> Q5 39,2% |
| D-1 alta -> D fecha em alta (cc) | 47,0% | 49,1% | 49,3/50,8 | NAO (p 0,37/0,61), dif. -2pp |
| D-1 baixa -> D fecha em alta (cc) | 51,3% | 52,8% | idem | NAO (+2pp, p>0,4) |
| Candle de D-1 -> candle de D | -0,7 a +0,6pp | -1,3 a +1,1pp | 52,0/51,3 | NAO (zero) |
| Autocorrelacao lag 1..5 (cc/ATR) | -0,04 -0,04 +0,01 +0,06 -0,04 | -0,06 +0,04 -0,02 +0,10 +0,01 | +-0,07 (IS) / +-0,09 (OOS) | NAO; nenhum lag passa nas duas janelas (lag 4 positivo nas duas mas dentro/na borda do ruido; 5 lags = 1 em 5 sai por acaso) |
| Magnitude de D-1 (quintis) -> direcao/retorno de D | todos |dif|<7pp, p>0,08 | idem, sinais trocam Q1/Q3 | - | NAO (sem padrao consistente; retorno medio por quintil tem IC de +-200 a +-470 pts) |
| Sequencias 2/3/4 dias -> continua | 46-51% | 41-59% (n=19-107) | embaralhado 47-50% | NAO (p_perm 0,12-0,92; todos dentro do p2,5-p97,5 do nulo) |
| Gap alta/baixa -> dia fecha a favor do gap | 49,2% / 45,5% | 48,2% / 46,1% | 52,0/48,0 (51,3/48,7) | NAO (dif. ~+-3pp, p>0,2) |
| Gap fecha no dia (preco volta ao C-1) | 73,4% / 73,5% | 75,7% / 76,6% | = base | base alta e igual nos dois sentidos; fechar gap e comum, nao e previsao |
| Gap fecha: gap pequeno (Q1) | 94% | 93-95% | 73,5/76,1 | SIM (mecanico: gap pequeno = perto do C-1) |
| Gap fecha: gap grande (Q5) | 49% / 40% | 45% / 58% | idem | SIM (mecanico: gap grande = mais longe); nao e sinal de direcao |
| Rompe maxima de D-1 dado D-1 alta | 63,8% | 58,2% | 49,1/47,2 | SIM (+11 a +15pp), mas em grande parte reflexo do gap (gap contra D-1 e o inverso: abre abaixo e rompe a minima? ver nota) |
| Rompe minima de D-1 dado D-1 alta | 38,8% | 35,5% | 51,2/48,4 | SIM (-12 a -13pp) |
| Rompe maxima dado D-1 baixa | 34,5% | 35,7% | 49,1/47,2 | SIM (-12 a -15pp) |
| Rompe minima dado D-1 baixa | 63,5% | 61,5% | 51,2/48,4 | SIM (+12 a +13pp) |
| Rompe as duas (inside/outside) | 9-13% | 8-11% | 11,1 / 9,9 | NAO |
| Rompe maxima primeiro -> fecha acima dela | 54,7% (n=349) | 55,6% (n=178) | ~52 (C>O geral) | NAO distinguivel de moeda/base (IC cruza 50 e o nulo) |
| Rompe minima primeiro -> fecha abaixo | 51,5% | 50,0% | ~48 | NAO |

Nota sobre rompimento: "D-1 alta -> rompe a maxima de D-1 em 58-64%" e uma tendencia de continuidade INTRADIA do nivel (o candle de D-1 alta tem maxima mais alta que o fechamento; preco passa por ela), enquanto o fechamento de D nao segue (47-49% de alta). Rompe o nivel mas nao fecha alem dele de forma confiavel: o nivel e tocado, nao sustentado. (Nulo da 6b "mesmos dias": 66-74% e o C>O condicionado a ter rompido a maxima, nao e comparavel direto; o nulo util e o geral ~52%.)

## Conclusao
O dia anterior NAO preve a direcao do dia seguinte em candle nem em fechamento: P(D fecha em alta | D-1 alta) = 47,0% (IS) e 49,1% (OOS) contra 49-51% de base; a diferenca (+-2pp, ~+-30 pts em media contra ATR de ~2.000 pts) esta bem dentro do ruido, a autocorrelacao diaria e ~0 em lags 1-5 e sequencias de 2-4 dias nao diferem do embaralhamento. Isso vale para magnitude (quintis) e para posicao do fechamento no range. O unico efeito que sobrevive nas duas janelas e na ABERTURA: o gap tende a ser contra D-1 (apos alta, abre em baixa em 55-58% das vezes; apos fechar perto da minima, abre em alta 62-68%; gradiente monotono por quintil de retorno), de ~7-8pp e ~+-40-90 pts de gap medio (~0,03-0,05% do preco, ~1/10 do |gap| tipico). Esse efeito nao se transmite ao resto do dia: dado o gap, o dia fecha a favor dele em ~46-54% (nulo 48-52%). Portanto o caso "fechou em alta e abriu em baixa" que o dono viu e normal e ate mais frequente que o oposto, mas nao informa a tendencia do dia. Cautelas: ~170 testes sem correcao (cerca de 8 falsos positivos esperados a 5%); o efeito de gap contra D-1 pode ter componente de microestrutura (fechamento em 18:24/17:54 na ultima barra e abertura em 09:00, nao investigado aqui) e o ajuste por diferenca nao afeta sinais. Para a semana anterior (nao medido nesta parte), nada aqui sugere persistencia: se o dia a dia nao persiste, agregados de 5 dias tendem ao mesmo.
