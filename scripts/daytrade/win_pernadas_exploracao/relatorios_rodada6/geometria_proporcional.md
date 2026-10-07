# Geometria proporcional assimétrica no recuo do WIN ("ganhar de balde, perder de colherinha")

Janelas: descoberta jan–jun/2026 (122 pregões), confirmação jul–ago/2026 (44), referência set/2026 (20). Só 2026 (dez/2025 apenas aqueceu a base de volatilidade). Caminho dentro da vela: alta mínima→máxima, baixa máxima→mínima.

## Veredito (honesto)
**Nenhuma geometria proporcional se confirmou.** Das 8 células congeladas, 4 ficaram positivas na confirmação (1, 2, 5, 8), mas **nenhuma com IC de 95% acima de zero**; 2 (células 3 e 4) foram significativamente negativas (−113 pts/op); em set/26 só a célula 1 ficou marginalmente positiva (+4 pts, IC −106 a +161) e as demais negativas. A checagem com ticks (mar–jun) derruba o resto: onde o M1 mostrava +30 a +160 pts/op, os ticks dão −7 a −67 pts/op (células 3 a 8); só as células 1 e 2 (E1) mantêm o sinal, com n=11–12 e IC que cruza zero. A razão alvo/stop é fácil de fabricar; o que decide é o acerto contra o breakeven, e ele fica no nível do acaso. O "ganhar 5–10× o risco" existe só no nominal: o payoff realizado fica em 2,4–6,4 e 55–95% das operações terminam em stop. Não há nada para dimensionar em dinheiro.

## Método
- **Eventos em tempo real**: zigzag de T ∈ {250, 500, 750} pts sobre o caminho da vela; perna em curso, topo provisório E (máximo corrente), início P, avanço A = E−P; espelhado na baixa. O evento só vale com o recuo ainda dentro da perna (r·A < T).
- **E1**: limite em E − r·A (r 38/50/62%); stop = s·(E−entrada), s ∈ {1/10, 1/7, 1/5, 1/3}; alvo = E + (m−1)·(E−entrada), m ∈ {1; 1,27; 1,62} (m=1 é o topo). 36 geometrias.
- **E2**: fundo provisório confirmado = repique ≥ k% (25/38/50) do recuo desde a mínima corrente; limite no reteste a j% (50/62/79) do repique; stop ∈ {mín−1 tick, mín−3 ticks, 0,5× e 1,0× da distância entrada→mín}; alvo como em E1 sobre o recuo até a mínima. 3 × 36 geometrias.
- **E3**: limite como E1; stop técnico = extremo das últimas N (5/10/15) velas M1 − 1 tick (conhecido ao armar); alvo = k·stop, k ∈ {5; 7,5; 10}. 27 geometrias.
- Só entram geometrias com alvo/stop nominal ≥ ~3 e stop entre 15 e 500 pts.
- **Execução**: limite com prazo de **10 minutos**; alvo limite; só o stop a mercado (+5 pts); custo 2 pts; fim do pregão 17:50 a mercado. Conservador = enche só 1 tick além do nível (o alvo também exige +1 tick); otimista = ao toque. Mesma vela: stop vence o alvo; na vela do preenchimento só vale o stop. Ordem cancelada se uma vela faz máxima acima de E. Um trade (ou ordem pendente) por vez por célula; um evento por topo (estrutura nova).
- **Filtros** (72 combinações): tendência (qualquer / a favor da perna de 750; para T=750 são idênticos); horário de armar (<11h / 11–13h / ≥13h / todos); volatilidade (nenhuma / v2x: alguma das últimas 10 velas ≥2× o range do mesmo minuto nos 20 pregões anteriores / onda: 30 velas ≥1,5× o esperado); ordem do recuo (todos / 1º / 2º+).
- **Contagem de testes**: 513 geometrias × 72 filtros = ~36,9 mil células (35,8 mil com algum trade; ~20,5 mil com n≥40 na descoberta). A melhor de tantas é positiva por acaso: nos 40 sorteios do nulo padrão (M1 embaralhado em blocos de 30 min) o máximo de t da grade foi em média 2,63 (p95 3,06; máx. 3,38); no real foi 3,24. Só 2 células reais tiveram t≥3, contra 0,2 esperadas no nulo: sinal tênue, que a confirmação não sustentou.
- **Congelamento** (`congelado_ANTES_da_confirmacao.json`, gravado antes de abrir jul–ago): n≥40, média>0, **platô** (≥60% dos vizinhos de grade positivos, ≥3 vizinhos com n≥20), máx. 2 por (T, família), ordenado por t. 8 células (2 duplicatas T=750 removidas). O platô foi frouxo: 3.607 de 5.478 elegíveis passaram, porque vizinhas compartilham a mesma amostra.
- **Estatística**: IC por bootstrap de dias (2.000); t por razão agrupada por dia; breakeven empírico = perda_média/(ganho_médio+perda_média); nulo analítico p0 = stop/(alvo+stop) e esperança nula analítica (≈ −6 pts: só custo e deslize). O nulo embaralhado dá −9 a −26 pts de esperança (injeta saltos entre barras), por isso os p-valores dele (0,024 = piso de 40 sorteios) são quase triviais; é referência, o juiz é o IC e o acerto contra o breakeven.
- Limitação: stop e alvo na mesma vela M1 contam como stop (sem ticks); o bloqueio sequencial usa a sequência não filtrada.

## 1. Células congeladas: descoberta → confirmação → set
ordens = ordens armadas; n = preenchidas; seq perdas = maior sequência de perdas; payoff nom/real = alvo/stop nominal e ganho médio/perda média realizados; stop% = fração de saídas em stop.


### CONSERVADOR

| # | celula | janela | ordens | n | fill% | acerto% | BE emp% | nulo p0% | pts/op | IC95 | t | nulo analit. | nulo emb. (p) | seq perdas | op/dia | payoff nom/real | stop% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | desc | 133 | 63 | 47 | 44,4 | 25,4 | 25,0 | 100,8 | [40; 163] | 3,24 | -5,7 | -10,2 (0,024) | 5 | 0,52 | 3,0/2,9 | 56 |
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | conf | 46 | 20 | 43 | 35,0 | 25,5 | 25,0 | 46,5 | [-30; 131] | 1,21 | -5,8 | -19,7 (0,049) | 4 | 0,45 | 3,0/2,9 | 65 |
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | set | 32 | 14 | 44 | 28,6 | 27,7 | 25,0 | 4,4 | [-106; 161] | 0,07 | -5,7 | - (-) | 4 | 0,67 | 3,0/2,6 | 71 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | desc | 156 | 68 | 44 | 44,1 | 25,5 | 25,0 | 99,5 | [38; 163] | 3,13 | -5,7 | -9,0 (0,024) | 6 | 0,56 | 3,0/2,9 | 56 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | conf | 53 | 24 | 45 | 33,3 | 25,4 | 25,0 | 40,1 | [-34; 131] | 1,01 | -5,8 | -22,2 (0,024) | 4 | 0,55 | 3,0/2,9 | 67 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | set | 37 | 16 | 43 | 25,0 | 27,7 | 25,0 | -12,9 | [-110; 123] | -0,23 | -5,7 | - (-) | 4 | 0,76 | 3,0/2,6 | 75 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | desc | 411 | 156 | 38 | 26,3 | 13,8 | 16,7 | 116,8 | [42; 200] | 2,93 | -6,2 | -12,3 (0,024) | 13 | 1,28 | 5,0/6,2 | 74 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | conf | 88 | 39 | 44 | 5,1 | 16,9 | 16,7 | -113,0 | [-177; -30] | -2,98 | -6,2 | 0,7 (0,951) | 22 | 0,89 | 5,0/4,9 | 95 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | set | 63 | 27 | 43 | 14,8 | 19,1 | 16,7 | -39,2 | [-132; 71] | -0,74 | -6,2 | - (-) | 11 | 1,29 | 5,0/4,2 | 85 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | desc | 294 | 113 | 38 | 28,3 | 14,0 | 16,7 | 129,0 | [45; 221] | 2,88 | -6,2 | -11,3 (0,024) | 11 | 0,93 | 5,0/6,2 | 72 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | conf | 64 | 26 | 41 | 3,8 | 13,6 | 16,7 | -115,3 | [-194; -14] | -2,39 | -6,2 | 1,1 (0,927) | 21 | 0,59 | 5,0/6,4 | 96 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | set | 50 | 21 | 42 | 19,0 | 22,2 | 16,7 | -30,1 | [-147; 109] | -0,45 | -6,2 | - (-) | 8 | 1,00 | 5,0/3,5 | 81 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | desc | 188 | 108 | 57 | 31,5 | 19,9 | 16,7 | 157,7 | [42; 287] | 2,58 | -6,2 | -16,5 (0,024) | 7 | 0,89 | 5,0/4,0 | 66 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | conf | 91 | 46 | 51 | 30,4 | 21,5 | 16,7 | 93,2 | [-96; 306] | 0,89 | -6,2 | -21,2 (0,098) | 8 | 1,05 | 5,0/3,7 | 63 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | set | 49 | 29 | 59 | 17,2 | 29,6 | 16,7 | -115,3 | [-255; 71] | -1,37 | -6,2 | - (-) | 9 | 1,38 | 5,0/2,4 | 79 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | desc | 240 | 178 | 74 | 21,3 | 14,2 | 13,7 | 41,2 | [8; 75] | 2,47 | -6,3 | -12,8 (0,024) | 14 | 1,46 | 7,1/6,0 | 79 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | conf | 63 | 44 | 70 | 15,9 | 13,7 | 12,5 | 11,8 | [-43; 75] | 0,40 | -6,4 | -12,3 (0,195) | 13 | 1,00 | 7,9/6,3 | 84 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | set | 42 | 31 | 74 | 6,5 | 17,7 | 13,4 | -52,2 | [-86; -2] | -2,39 | -6,3 | - (-) | 21 | 1,48 | 7,1/4,6 | 94 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | desc | 625 | 445 | 71 | 23,1 | 18,2 | 18,6 | 38,3 | [8; 68] | 2,42 | -6,1 | -14,7 (0,024) | 15 | 3,65 | 4,5/4,5 | 77 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | conf | 175 | 106 | 61 | 20,8 | 22,9 | 18,4 | -13,5 | [-51; 23] | -0,72 | -6,1 | -8,5 (0,537) | 14 | 2,41 | 4,5/3,4 | 79 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | set | 119 | 86 | 72 | 15,1 | 18,1 | 18,3 | -22,9 | [-76; 28] | -0,85 | -6,1 | - (-) | 15 | 4,10 | 4,5/4,5 | 85 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | desc | 117 | 72 | 62 | 27,8 | 14,6 | 11,8 | 241,9 | [35; 489] | 2,19 | -6,4 | -0,6 (0,024) | 10 | 0,59 | 7,5/5,9 | 69 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | conf | 55 | 33 | 60 | 36,4 | 21,7 | 11,8 | 175,0 | [-78; 474] | 1,21 | -6,4 | -26,0 (0,024) | 7 | 0,75 | 7,5/3,6 | 58 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | set | 32 | 23 | 72 | 8,7 | 16,8 | 11,8 | -136,6 | [-320; 117] | -1,11 | -6,4 | - (-) | 14 | 1,10 | 7,5/5,0 | 87 |

### OTIMISTA

| # | celula | janela | ordens | n | fill% | acerto% | BE emp% | nulo p0% | pts/op | IC95 | t | nulo analit. | nulo emb. (p) | seq perdas | op/dia | payoff nom/real | stop% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | desc | 133 | 63 | 47 | 44,4 | 25,4 | 25,0 | 100,8 | [40; 163] | 3,24 | -5,7 | - (-) | 5 | 0,52 | 3,0/2,9 | 56 |
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | conf | 46 | 20 | 43 | 35,0 | 25,5 | 25,0 | 46,5 | [-30; 131] | 1,21 | -5,8 | - (-) | 4 | 0,45 | 3,0/2,9 | 65 |
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | set | 32 | 14 | 44 | 28,6 | 27,7 | 25,0 | 4,4 | [-106; 161] | 0,07 | -5,7 | - (-) | 4 | 0,67 | 3,0/2,6 | 71 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | desc | 156 | 68 | 44 | 44,1 | 25,5 | 25,0 | 99,5 | [38; 163] | 3,13 | -5,7 | - (-) | 6 | 0,56 | 3,0/2,9 | 56 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | conf | 53 | 24 | 45 | 33,3 | 25,4 | 25,0 | 40,1 | [-34; 131] | 1,01 | -5,8 | - (-) | 4 | 0,55 | 3,0/2,9 | 67 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | set | 37 | 16 | 43 | 25,0 | 27,7 | 25,0 | -12,9 | [-110; 123] | -0,23 | -5,7 | - (-) | 4 | 0,76 | 3,0/2,6 | 75 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | desc | 410 | 159 | 39 | 27,7 | 14,4 | 16,7 | 120,9 | [48; 201] | 3,14 | -6,2 | - (-) | 10 | 1,30 | 5,0/6,0 | 72 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | conf | 88 | 39 | 44 | 5,1 | 16,9 | 16,7 | -113,0 | [-177; -30] | -2,98 | -6,2 | - (-) | 22 | 0,89 | 5,0/4,9 | 95 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | set | 62 | 29 | 47 | 17,2 | 22,2 | 16,7 | -42,5 | [-140; 69] | -0,78 | -6,2 | - (-) | 11 | 1,38 | 5,0/3,5 | 83 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | desc | 292 | 114 | 39 | 28,9 | 14,1 | 16,7 | 134,8 | [54; 224] | 3,06 | -6,2 | - (-) | 11 | 0,93 | 5,0/6,1 | 71 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | conf | 64 | 26 | 41 | 3,8 | 13,6 | 16,7 | -115,3 | [-194; -14] | -2,39 | -6,2 | - (-) | 21 | 0,59 | 5,0/6,4 | 96 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | set | 50 | 23 | 46 | 21,7 | 25,6 | 16,7 | -35,0 | [-157; 106] | -0,51 | -6,2 | - (-) | 8 | 1,10 | 5,0/2,9 | 78 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | desc | 184 | 111 | 60 | 30,6 | 19,8 | 16,7 | 147,5 | [34; 273] | 2,46 | -6,2 | - (-) | 7 | 0,91 | 5,0/4,0 | 67 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | conf | 87 | 49 | 56 | 30,6 | 19,9 | 16,7 | 119,8 | [-63; 322] | 1,18 | -6,2 | - (-) | 8 | 1,11 | 5,0/4,0 | 63 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | set | 47 | 28 | 60 | 14,3 | 27,1 | 16,7 | -130,6 | [-272; 56] | -1,53 | -6,2 | - (-) | 9 | 1,33 | 5,0/2,7 | 82 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | desc | 241 | 187 | 78 | 23,5 | 14,4 | 13,7 | 52,7 | [18; 86] | 3,16 | -6,3 | - (-) | 14 | 1,53 | 7,0/6,0 | 76 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | conf | 63 | 45 | 71 | 15,6 | 13,9 | 12,5 | 9,1 | [-43; 71] | 0,32 | -6,4 | - (-) | 13 | 1,02 | 7,9/6,2 | 84 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | set | 42 | 31 | 74 | 6,5 | 17,7 | 13,4 | -52,2 | [-86; -2] | -2,39 | -6,3 | - (-) | 21 | 1,48 | 7,1/4,6 | 94 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | desc | 628 | 453 | 72 | 23,4 | 18,3 | 18,5 | 39,6 | [10; 69] | 2,58 | -6,1 | - (-) | 16 | 3,71 | 4,5/4,5 | 76 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | conf | 173 | 107 | 62 | 21,5 | 22,5 | 18,4 | -6,5 | [-45; 32] | -0,34 | -6,1 | - (-) | 14 | 2,43 | 4,5/3,4 | 79 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | set | 118 | 87 | 74 | 16,1 | 18,1 | 18,3 | -15,7 | [-68; 35] | -0,59 | -6,1 | - (-) | 15 | 4,14 | 4,5/4,5 | 84 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | desc | 116 | 75 | 65 | 26,7 | 14,6 | 11,8 | 220,7 | [20; 460] | 2,05 | -6,4 | - (-) | 10 | 0,61 | 7,5/5,8 | 71 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | conf | 52 | 33 | 63 | 36,4 | 18,2 | 11,8 | 256,0 | [-18; 548] | 1,71 | -6,4 | - (-) | 5 | 0,75 | 7,5/4,5 | 58 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | set | 30 | 22 | 73 | 4,5 | 10,2 | 11,8 | -157,0 | [-334; 106] | -1,23 | -6,4 | - (-) | 14 | 1,05 | 7,5/8,8 | 91 |

Leitura: o acerto das células 1–2 na descoberta (44%) bate o breakeven (25%) com folga, mas na confirmação cai a 33–35% (IC da esperança cruza zero) e no set a 25–29% (≈ breakeven). As células E3 de T=500 (3 e 4) têm acerto 26–28% na descoberta e **4–5% na confirmação**, o oposto do que a descoberta indicava: ruído de seleção. A célula 8 tem a melhor esperança nominal (+175 pts) com n=33 e IC de −78 a +474. Nenhuma tem as ~150 operações fora da amostra que o estudo anterior já pedia.

## 2. Sensibilidade com ticks (mar–jun, só descoberta, 83 pregões com tick)
Ticks de `data/cache_win_ticks/WIN@D/`, alinhados ao M1 por deslocamento diário (ajuste por diferença), descartando ticks fora da faixa do minuto (2–3%), reduzidos a barras de 1 segundo com 4 pontos (abre, extremo que veio primeiro, outro extremo, fecha; a ordem sub-segundo se perde). Mesmo desenho de execução e filtros (volatilidade lida da vela M1 anterior); mesmos dias nas duas bases; "N velas" do E3 = N minutos.

Dias com tick (mar-jun, desc): 83

| # | celula | modo | base | n | acerto% | BE emp% | pts/op | IC95 | t | seq perdas |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | cons | M1 | 43 | 44,2 | 25,8 | 95,8 | [24; 170] | 2,68 | 5 |
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | cons | ticks | 11 | 45,5 | 26,2 | 84,4 | [-42; 252] | 1,32 | 2 |
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | otim | M1 | 43 | 44,2 | 25,8 | 95,8 | [24; 170] | 2,68 | 5 |
| 1 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/1o recuo | otim | ticks | 11 | 45,5 | 26,2 | 84,4 | [-42; 252] | 1,32 | 2 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | cons | M1 | 46 | 43,5 | 25,8 | 93,1 | [22; 167] | 2,61 | 6 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | cons | ticks | 12 | 50,0 | 26,2 | 103,8 | [-19; 265] | 1,64 | 2 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | otim | M1 | 46 | 43,5 | 25,8 | 93,1 | [22; 167] | 2,61 | 6 |
| 2 | T500 E1 r=62% s=1/3 alvo=1.0x / qualquer/<11h/v2x/todos | otim | ticks | 12 | 50,0 | 26,2 | 103,8 | [-19; 265] | 1,64 | 2 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | cons | M1 | 114 | 26,3 | 13,0 | 136,2 | [43; 242] | 2,69 | 13 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | cons | ticks | 40 | 7,5 | 15,6 | -67,1 | [-136; 13] | -1,82 | 13 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | otim | M1 | 116 | 27,6 | 13,4 | 142,0 | [52; 243] | 2,91 | 10 |
| 3 | T500 E3 r=38% N=5 alvo=5.0xstop / qualquer/todas/-/2o+ | otim | ticks | 41 | 7,3 | 16,4 | -75,4 | [-144; 3] | -2,05 | 13 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | cons | M1 | 87 | 27,6 | 13,0 | 140,8 | [45; 255] | 2,60 | 11 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | cons | ticks | 24 | 12,5 | 16,7 | -35,1 | [-153; 111] | -0,53 | 8 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | otim | M1 | 88 | 28,4 | 13,2 | 148,1 | [52; 257] | 2,80 | 11 |
| 4 | T500 E3 r=38% N=5 alvo=5.0xstop / a favor/todas/-/2o+ | otim | ticks | 24 | 12,5 | 16,7 | -35,1 | [-153; 111] | -0,53 | 8 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | cons | M1 | 66 | 31,8 | 20,3 | 159,8 | [-3; 346] | 1,86 | 7 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | cons | ticks | 28 | 14,3 | 15,0 | -12,2 | [-211; 235] | -0,11 | 10 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | otim | M1 | 68 | 30,9 | 20,1 | 149,8 | [-8; 332] | 1,78 | 7 |
| 5 | T250 E3 r=38% N=10 alvo=5.0xstop / a favor/todas/v2x/todos | otim | ticks | 32 | 21,9 | 15,7 | 98,0 | [-112; 346] | 0,86 | 7 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | cons | M1 | 121 | 21,5 | 14,2 | 41,7 | [3; 83] | 2,03 | 14 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | cons | ticks | 258 | 7,4 | 8,9 | -8,0 | [-27; 15] | -0,72 | 50 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | otim | M1 | 127 | 23,6 | 14,2 | 54,1 | [15; 95] | 2,58 | 14 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1.27x / qualquer/11-13h/-/2o+ | otim | ticks | 267 | 9,0 | 9,4 | -1,9 | [-23; 24] | -0,16 | 46 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | cons | M1 | 324 | 21,9 | 17,9 | 31,1 | [-5; 69] | 1,60 | 15 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | cons | ticks | 579 | 16,1 | 17,1 | -6,9 | [-30; 17] | -0,58 | 28 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | otim | M1 | 331 | 22,4 | 18,0 | 33,8 | [-1; 69] | 1,80 | 16 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1.62x / qualquer/todas/-/2o+ | otim | ticks | 608 | 18,8 | 17,6 | 7,7 | [-15; 31] | 0,66 | 28 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | cons | M1 | 43 | 25,6 | 14,3 | 208,1 | [-71; 573] | 1,31 | 10 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | cons | ticks | 9 | 0,0 | 100,0 | -240,9 | [-332; -151] | -5,52 | 9 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | otim | M1 | 45 | 24,4 | 14,4 | 186,4 | [-84; 540] | 1,22 | 10 |
| 8 | T250 E3 r=38% N=10 alvo=7.5xstop / a favor/todas/v2x/1o recuo | otim | ticks | 10 | 20,0 | 14,6 | 92,5 | [-297; 495] | 0,47 | 3 |

Stop curto (E1 s=1/10 e E3 N=5, todos os r/alvos, sem filtro, conservador), mesmos dias:

| familia | T | base | celulas | trades | acerto% | pts/op (media ponderada) |
|---|---|---|---|---|---|---|
| E1 | 250 | M1 | 9 | 10480 | 5,5 | -11,3 |
| E1 | 250 | ticks | 9 | 2948 | 5,1 | -12,7 |
| E1 | 500 | M1 | 9 | 4852 | 7,8 | -3,3 |
| E1 | 500 | ticks | 9 | 1011 | 4,0 | -19,2 |
| E1 | 750 | M1 | 9 | 1969 | 8,2 | -1,5 |
| E1 | 750 | ticks | 9 | 448 | 4,7 | -22,4 |
| E3 | 250 | M1 | 9 | 5995 | 14,5 | -7,7 |
| E3 | 250 | ticks | 9 | 2587 | 12,0 | -27,0 |
| E3 | 500 | M1 | 9 | 2558 | 15,3 | 18,7 |
| E3 | 500 | ticks | 9 | 681 | 12,3 | -27,9 |
| E3 | 750 | M1 | 9 | 916 | 18,0 | 45,1 |
| E3 | 750 | ticks | 9 | 271 | 8,9 | -136,4 |

Leitura: com ticks (a) o número de eventos muda muito (o caminho de 2 pontos por vela produz estrutura diferente); (b) o acerto das células E2/E3 cai à metade ou menos e a esperança passa de +30/+160 para −7/−67 pts/op (células 3 a 8; a 8 chega a 0 acerto em n=9); (c) só o E1 das células 1 e 2 preserva o sinal (+84 e +104 pts/op), com n=11–12 e IC que cruza zero. **O "stop curto" (E1 s=1/10 e E3 N=5) é pior com ticks em todas as 6 linhas**: E3 T=500 passa de +19 para −28 pts/op e T=750 de +45 para −136. O resultado positivo do stop técnico no M1 é artefato do caminho de 2 pontos, como o outro analista avisou. Onde M1 e ticks divergem, vale o ticks.

## 3. Tamanho de mão e ruína (R$250 de partida; motor `rodada4/decisao/motor.py`)
Calculado sobre as operações da confirmação. **Só teria sentido com esperança confirmada > 0 e IC acima de zero; nenhuma célula tem isso.** As colunas de capital mostram o que seria necessário *se* a esperança pontual da confirmação fosse real, e a checagem com ticks diz que não é. Contratos = Kelly ¼ com p encolhido para o nulo (n0=100) e teto de pior caso de 25% do caixa (dá 0–1 porque o p encolhido ≈ nulo). Ruína = caixa < R$100 em ~1 ano de operações; p95 da sequência de perdas por Monte Carlo.

| # | celula | esperanca conf (pts/op) | contratos a R$250 | p_est (encolhido) | ruina R$250 (1 ano) | p95 seq perdas | capital p/ ruina<=5% | R$/op (1 ctr) |
|---|---|---|---|---|---|---|---|---|
| 1 | T500 E1 r=62% s=1/3 alvo=1,0x / qualquer/<11h/v2x/1o recuo | 46,5 | 1 | 26,6% | 22% | 15 | 500 | 9,30 |
| 2 | T500 E1 r=62% s=1/3 alvo=1,0x / qualquer/<11h/v2x/todos | 40,1 | 1 | 26,6% | 28% | 16 | 500 | 8,02 |
| 3 | T500 E3 r=38% N=5 alvo=5,0xstop / qualquer/todas/-/2o+ | -113,0 | 0 | 13,4% | 100% | 94 | - | -22,61 |
| 4 | T500 E3 r=38% N=5 alvo=5,0xstop / a favor/todas/-/2o+ | -115,3 | 0 | 14,0% | 100% | 102 | - | -23,05 |
| 5 | T250 E3 r=38% N=10 alvo=5,0xstop / a favor/todas/v2x/todos | 93,2 | 0 | 21,0% | 54% | 19 | 1000 | 18,64 |
| 6 | T750 E2 k=25% j=62% stop=d10 alvo=1,27x / qualquer/11-13h/-/2o+ | 11,8 | 0 | 13,6% | 57% | 36 | 1000 | 2,35 |
| 7 | T750 E2 k=50% j=50% stop=d10 alvo=1,62x / qualquer/todas/-/2o+ | -13,5 | 0 | 19,6% | 98% | 33 | - | -2,69 |
| 8 | T250 E3 r=38% N=10 alvo=7,5xstop / a favor/todas/v2x/1o recuo | 175,0 | 0 | 17,9% | 41% | 15 | 1000 | 34,99 |

## 4. Regras (SE … ENTÃO …)

| ID | SE | ENTÃO | Papel | Descoberta | Confirmação | Set | Status |
|---|---|---|---|---|---|---|---|
| R52 | avanço de zigzag 500, 1º recuo, limite a 62% do avanço, stop = 1/3 da distância ao topo, alvo = topo (razão 3), antes de 11h com vela M1 ≥2× o minuto | acerto 44% × BE 25%, +101 pts/op | ACEITA / STOP / ALVO | n=63, IC +40 a +163 | n=20, +46 (IC −30 a +131), acerto 35% | n=14, +4 | **falhou** (positiva sem significância; ticks n=11; ~37 mil testes) |
| R53 | stop técnico (5 velas) + alvo 5×, T=500, 2º+ recuo | +117 pts/op | STOP / ALVO | n=156, IC +42 a +200 | **−113** (IC −177 a −30), acerto 5% | −39 | **falhou, inverteu** (ticks −67) |
| R54 | stop técnico (10 velas), alvo 5× ou 7,5×, T=250, a favor, v2x | +158 / +242 pts/op | STOP / ALVO | IC cruza 0 em ambas na confirmação | +93 / +175 (IC cruza 0) | −115 / −137 | **falhou** (ticks −12 / −241) |
| R55 | E2 (fundo confirmado, reteste, stop na mínima), T=750 | +38 a +41 pts/op | ACEITA | IC +8 a +75 | +12 / −14 | −52 / −23 | **falhou**; com ticks −7 a −8, acerto 7–16% |
| R56 | stop de 1/10 da distância ao topo (E1) ou stop técnico de 5 velas (E3), sem filtro | lucro | STOP | média −1,5 a −11 pts/op (E1); E3 +19/+45 só em T=500/750 | — | — | **negativa**: com ticks −13 a −22 (E1), −27 a −136 (E3) |
| R57 | razão alvo/stop realizada | 5–10× | ALVO | nominal 3–10, realizada 2,4–6,4 | — | — | **negativa**: o alvo-limite exige +1 tick e o stop paga +5 de deslize; 55–95% das saídas são stop |
| R58 | filtros de horário/volatilidade/ordem do recuo/tendência cruzados com a geometria | maior acerto | LIGA / REJEITA | só v2x e <11h aparecem entre as melhores | — | — | **sem efeito além de R20/R35** (volatilidade liga, não dá direção) |

## 5. Conclusão e o que fica
- **O princípio colherinha/balde não vira esperança positiva neste mercado, mesmo com alvo e stop proporcionais à estrutura.** O acerto observado fica perto do nulo analítico `stop/(alvo+stop)`; custo (2 pts + 5 de deslize + 1 tick do alvo) e ruído de 1 minuto comem a razão.
- Uma célula (E1, r=62%, s=1/3, alvo no topo, 1º recuo, <11h com vela v2x, T=500) tem acerto 44% × BE 25% na descoberta e sinal positivo nas três janelas M1, mas com n=63 → 20 → 14, IC que cruza zero fora da descoberta e n=11 nos ticks. É a única a **observar** em sombra, nunca a operar; precisaria de ≥150 operações fora da amostra.
- Resultados M1 (2 pontos por vela) são otimistas para stops curtos; a checagem com ticks deve ser obrigatória para qualquer célula de stop <150 pts.

## Arquivos
`rodada6/geometria_proporcional/`: `geomlib.py` (eventos/zigzag), `simfam.py` (simulação), `stage.py`, `runwin.py` (real + 40 sorteios por janela), `congelar.py` + `congelado_ANTES_da_confirmacao.json`, `avalia.py`, `ruina_cel.py`, `tickprep.py`, `ticks_sens.py`, `ticks_rep.py`; tabelas `tabelas_avalia.md`, `tabela_ticks.md`, `tabela_ruina.md`.
