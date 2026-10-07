# Desvios: situações que destoam da base do mesmo horário (WIN, 2026)

Dados: só 2026. Descoberta jan-jun (121 pregões, 10.115 eventos de 5 em 5 min, 09:30-16:30). Confirmação jul-ago (43 pregões, 3.570 eventos). Set/26 não usado.

## Método
- Evento = fechamento de cada minuto :04/:09... Descritores usam só dado até aquele fechamento.
- Descritores (15): bloco horário (5), distância à abertura, ao fechamento anterior (5 faixas, pts), gap (3), distância ao VWAP em ATR (5; ATR = 3x amplitude M1 média de 60 min), volatilidade relativa ao horário (3; mediana por horário só da descoberta), posição no range (3), distância da máx e da mín do dia (3+3), direção/progresso/recuo do zigzag 750 (3+3+3), nº de pernadas (4), dia da semana (5), movimento de 30 min (5).
- Resultados (7): sobe antes de descer 250/500/750 pts; nova máx / nova mín do dia por >=250 pts (só avaliada se o preço está a <=500 pts da máx/mín; senão era tautologia); fecha o dia acima do preço atual; fecha acima 60 min depois.
- Base = média do mesmo resultado no mesmo bloco de 30 min (no mesmo período). Diferença = célula - base do horário de seus próprios eventos.
- IC por bootstrap de DIAS (1.000 reamostragens, IC 99,5% na descoberta; 2.000 e IC 95% na confirmação). Filtros: n>=200 eventos, >=30 dias, |diferença|>=10 pp.

## Células testadas
- 1.734 células (15 descritores simples + todos os pares), 7.894 testes (célula x resultado) com n>=200.
- Passaram (IC 99,5% inteiro de um lado, |dif|>=10pp, >=30 dias): **12 testes** (9 células após remover sobreposição >50%). Pelo acaso, esperaríamos ~40 testes a 0,5%: o conjunto todo é compatível com ruído. Nenhum resultado "sobe antes de descer Y" passou.
- Uma primeira versão com "nova máx/mín" sem controle de distância deu centenas de "achados" (perto da máxima, nova máxima é quase certa; longe do VWAP idem) - descartada como tautologia.
- Lista congelada: as 9 do tier 1 + 11 do tier 2 (maior margem de IC, |dif|>=10pp, sem exigir IC fora de zero) = 20. `congelada.csv`.

## Confirmação jul-ago (`confirmacao.csv`)
Confirma = mesmo sinal, IC 95% sem o zero, |dif|>=5pp.

| Célula | Resultado | Desc. % | Base desc. | Conf. % | Base conf. | n conf (dias) | Dif. conf. [IC95] | Confirma |
|---|---|---|---|---|---|---|---|---|
| vol rel<0,8 & zigzag 750-1250 | nova mín | 20,8 | 55,1 | 42,2 | 58,7 | 180 (14) | -16 [-40;+14] | não |
| VWAP<-1,5ATR & vol rel>1,25 | nova mín | 67,3 | 42,9 | n=8 | - | - | - | inconclusivo |
| VWAP<-1,5ATR & mom30<=-300 | nova mín | 67,3 | 50,6 | 68,0 | 60,1 | 219 (27) | +8 [-11;+20] | não (mesmo sinal) |
| gap<-300 & 250-750 da máx | fecha acima | 73,1 | 48,8 | 24,3 | 43,6 | 148 (8) | -19 | não (inverteu) |
| vol rel>1,25 & zigzag alta | nova máx | 76,9 | 57,0 | n=19 | - | - | - | inconclusivo |
| vol rel<0,8 | nova mín | 34,5 | 52,6 | 60,1 | 55,7 | 636 (29) | +4 | não (inverteu) |
| vol rel>1,25 & 3+ pernadas | nova máx | 76,6 | 54,1 | n=20 | - | - | - | inconclusivo |
| zigzag prog>2000 & mom30<=-300 | nova mín | 71,7 | 54,5 | 77,8 | 62,5 | 126 (17) | +15 [-10;+28] | não (mesmo sinal) |
| gap>300 & zigzag alta | fecha acima | 34,0 | 48,5 | 57,8 | 47,7 | 742 (19) | +10 | não (inverteu) |
| VWAP>+1,5ATR & vol rel>1,25 | nova máx | 74,4 | 50,7 | n=15 | - | - | - | inconclusivo |
| vol rel<0,8 & zigzag baixa | nova mín | 33,7 | 51,9 | 60,3 | 55,1 | 590 (29) | +5 | não (inverteu) |
| **VWAP>+1,5ATR & mom30>=+300** | **nova máx** | 69,3 | 57,4 | 82,0 | 67,4 | 178 (19) | **+14,6 [+3;+24]** | **sim** |
| vol rel>1,25 & mom30<=-300 | nova mín | 65,7 | 48,0 | n=10 | - | - | - | inconclusivo |
| vol rel<0,8 & mom30 neutro | nova mín | 23,7 | 46,7 | 54,5 | 54,2 | 264 (26) | 0 | não |
| 09:30-10:30 & zigzag 1250-2000 | nova máx | 92,9 | 82,7 | 57,4 | 62,2 | 61 (14) | -5 | não |
| dFechAnt -750:-300 & mom30>=300 | sobe 500 antes | 37,6 | 49,3 | 54,9 | 49,2 | 51 (14) | +6 | não (inverteu) |
| VWAP<-1,5ATR & zigzag alta | fecha acima | 24,6 | 47,7 | 70,9 | 50,4 | 158 (16) | +20 | não (inverteu) |
| zigzag alta & 2 pernadas | sobe 750 antes | 35,7 | 51,1 | 43,7 | 45,8 | 142 (16) | -2 | não |
| pos>0,8 & zigzag baixa | sobe 250 antes | 63,3 | 48,3 | 55,3 | 48,7 | 38 (10) | +6 | não |
| gap<-300 & zigzag 750-1250 | fecha acima | 67,1 | 48,7 | 25,1 | 46,7 | 267 (10) | -22 [-33;-1] | não (inverteu) |

(Células de n pequeno na confirmação por causa da volatilidade relativa: o 'volRel' usa mediana da descoberta e jul-ago teve poucos eventos nas faixas extremas.)
