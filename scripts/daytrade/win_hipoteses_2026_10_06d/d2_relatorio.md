# D2 — Família ALVO sobre WinCincoMedias v2.01 (WIN M30, só 2026)

Baseline reproduzido exato pela cópia desligada: +7.805,20, 13/14, pior −117,00, PF 1,68, 248 trades, DD 781,50, sem set. 7.370,70.
Alvo = ordem-limite, enche só se negociar 1 tick além; preço = nível (ou abertura se abre além); sem deslize; saídas atuais mantidas e com prioridade; nível do fechamento t vale de t+1; na barra da entrada o alvo só vale na seguinte. ATR(14) M30 da barra do sinal. 26 variantes + baseline.

## Tabela (liq = R$; "mel" = meses/janelas que melhoram vs baseline, de 14)

| variante | líquido | jan+ | pior | PF | acerto | payoff | trades | DD | sem set | saídas alvo | mel |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 7805,20 | 13/14 | −117,00 | 1,68 | 40,3 | 2,49 | 248 | 781,5 | 7370,70 | 0 | – |
| fixo k=1 | 6433,20 | 12/14 | −363,50 | 1,39 | 49,2 | 1,44 | 374 | 904,5 | 6167,70 | 139 | 6 |
| fixo k=2 | 8010,00 | 12/14 | −117,00 | 1,61 | 45,0 | 1,96 | 298 | 781,5 | 7887,00 | 54 | 7 |
| fixo k=3 | 7833,40 | 12/14 | −117,00 | 1,61 | 43,1 | 2,12 | 274 | 797,0 | 7695,90 | 27 | 3 |
| fixo k=4 | 7791,40 | 13/14 | −117,00 | 1,65 | 41,6 | 2,32 | 262 | 781,5 | 7495,40 | 14 | 3 |
| fixo k=6 | 7583,40 | 12/14 | −117,00 | 1,65 | 40,6 | 2,42 | 254 | 781,5 | 7256,40 | 6 | 1 |
| fixo k=8 | 7914,60 | 13/14 | −117,00 | 1,68 | 40,5 | 2,47 | 252 | 781,5 | 7427,60 | 4 | 3 |
| trail k=2 j=0,5 | 8164,60 | 13/14 | −117,00 | 1,62 | 44,6 | 2,02 | 294 | 781,5 | 7982,60 | 50 | 6 |
| trail k=2 j=1 | 8379,30 | 12/14 | −117,00 | 1,67 | 44,8 | 2,06 | 281 | 781,5 | 8111,30 | 36 | 6 |
| trail k=2 j=2 | 8109,80 | 12/14 | −117,00 | 1,66 | 43,8 | 2,13 | 274 | 781,5 | 7993,30 | 28 | 6 |
| trail k=4 j=0,5 | 7767,30 | 13/14 | −117,00 | 1,65 | 41,4 | 2,34 | 261 | 781,5 | 7471,30 | 13 | 3 |
| trail k=4 j=1 | 7936,50 | 13/14 | −117,00 | 1,67 | 41,3 | 2,37 | 259 | 781,5 | 7640,50 | 11 | 5 |
| trail k=4 j=2 | 7855,90 | 13/14 | −117,00 | 1,67 | 40,7 | 2,43 | 253 | 781,5 | 7559,90 | 5 | 1 |
| trail k=8 j=0,5 | 7917,60 | 13/14 | −117,00 | 1,68 | 40,5 | 2,47 | 252 | 781,5 | 7430,60 | 4 | 3 |
| trail k=8 j=1 | 7974,20 | 13/14 | −117,00 | 1,68 | 40,0 | 2,53 | 250 | 781,5 | 7428,20 | 2 | 2 |
| trail k=8 j=2 | 7987,70 | 13/14 | −117,00 | 1,70 | 40,2 | 2,53 | 249 | 781,5 | 7553,20 | 1 | 1 |
| contra N=2 kk=0 | 7651,70 | 12/14 | −117,00 | 1,67 | 40,0 | 2,50 | 255 | 781,5 | 7217,20 | 10 | 3 |
| contra N=2 kk=0,25 | 7762,70 | 12/14 | −117,00 | 1,67 | 41,2 | 2,39 | 255 | 781,5 | 7328,20 | 7 | 2 |
| contra N=3 kk=0 | 7778,00 | 13/14 | −117,00 | 1,68 | 40,8 | 2,44 | 250 | 781,5 | 7343,50 | 2 | 0 |
| contra N=3 kk=0,25 | 7844,00 | 13/14 | −117,00 | 1,69 | 40,8 | 2,45 | 250 | 781,5 | 7409,50 | 2 | 2 |
| contra N=4 kk=0 / 0,25 | 7805,20 | 13/14 | −117,00 | 1,68 | 40,3 | 2,49 | 248 | 781,5 | 7370,70 | 0 | 0 (inerte) |
| estr dia anterior | 7229,00 | 10/14 | −117,00 | 1,57 | 45,9 | 1,85 | 292 | 773,0 | 6976,00 | 55 | 3 |
| estr 10 barras | 7895,30 | 12/14 | −320,00 | 1,56 | 59,7 | 1,05 | 417 | 708,0 | 6950,30 | 213 | 7 |
| estr 20 barras | 7686,10 | 11/14 | −174,00 | 1,54 | 57,3 | 1,15 | 403 | 711,4 | 6729,60 | 188 | 6 |
| estr 40 barras | 8496,60 | 11/14 | −171,00 | 1,63 | 56,4 | 1,25 | 388 | 851,0 | 7434,60 | 172 | 6 |

(contra N=4 é eixo morto: nunca dispara, idêntico ao baseline. Mês a mês completo no `_stdout.log`.)

## O que se aprende

1. **Alvo fixo não tem sinal consistente, ao contrário do M5 em que tudo piorou.** O líquido oscila sem tendência em k (k=1 −1.372; k=2 +205; k=3 +28; k=4 −14; k=6 −222; k=8 +109). Só k=1 (corta quase tudo) é claramente ruim: payoff cai a 1,44 e o pior mês vai a −363. O custo de cortar a cauda aparece como queda de payoff (2,49 → 1,96 em k=2) e de PF (1,68 → 1,61), compensada por mais trades (298): o alvo fecha cedo e o robô reentra. Ou seja, o ganho em k=2 não vem de "melhor saída" por trade, vem de girar mais.
2. **Os ganhos são concentrados em poucos meses.** Em trail k=2/j=1: jul +420, ago +770 (primeira janela, 37→808), fev-mar pequenos; perde janeiro (−370) e a segunda janela de ago (−300). Só 6/14 janelas melhoram e uma janela positiva a menos (12/14). Com o regime de jul/ago diferente do de janeiro, isso é mais cara de dependência de regime do que de efeito estrutural.
3. **Trail (alvo que se afasta) com k=2 é a única região com algum platô:** j=0,5/1/2 dão +360/+574/+305 sobre o baseline, sem set. +612/+741/+623, DD igual, pior igual. Mas k=4 e k=8 voltam a ~baseline (+−130), pois o alvo quase nunca dispara (1 a 13 saídas): a EMA4 sai antes. Na prática o trail só "faz algo" quando k é pequeno, e aí vira o alvo fixo k=2 com mais folga. O trail captura mais que a EMA4 em poucos casos, não de forma sistemática.
4. **Alvo que se aproxima ao zero (contra):** inútil ou pior (−154 a +39). Dispara 0 a 10 vezes; a EMA4/quebra do alinhamento já tira o trade perdedor antes, e o "voltar à entrada" encontra a saída normal primeiro. Não há resgate de zero a zero para capturar.
5. **Estrutura (máx/mín N barras):** aumenta acerto (57-60%) e destrói payoff (1,05-1,25); piora pior mês (−170 a −320) e janelas positivas (11-12/14). 40 barras dá +691 mas com DD maior (851), só 11/14 e sem set. abaixo do baseline (7.434 vs 7.371 = +64): o ganho todo é setembro. Não é candidata. Máx/mín do dia anterior é pior que o baseline em tudo.
6. **Lição geral:** nesta estratégia a EMA4 já é um stop/alvo adaptativo; um alvo de preço só ajuda onde corta ganhos muito grandes que depois devolveriam (alguns meses de jul/ago) e atrapalha onde a tendência corre (janeiro, +3.056 → 2.400-2.800). O efeito líquido é próximo de zero com variância alta entre meses.

## Candidatas congeladas (3, evidência FRACA)

Nenhuma é robusta: todas melhoram o líquido e o sem-setembro, mantêm DD e pior, mas perdem PF (1,61-1,67 vs 1,68) e, duas delas, uma janela positiva; 6-7 de 14 meses melhoram. Congeladas só por terem platô em j (trail) e vizinhança k=2/k=3 positiva. Quem validar em 2025 deve esperar efeito pequeno e tratar "nenhuma supera a atual" como resultado provável.

| nome | parâmetros |
|---|---|
| alvo_trail_k2_j1 | alvo 2×ATR(14) M30 do sinal, sobe para extremo+1×ATR a cada novo extremo |
| alvo_trail_k2_j05 | idem j=0,5 |
| alvo_fixo_k2 | alvo fixo 2×ATR |

Módulo: `d2_candidatas.py` (`CANDIDATAS = {nome: f(ano, dados)}`; confere com a rodada 2026).
