# Gestão adaptativa (50 dias de dias_usados.json, entradas do robo_v2 fixas)

Código: coleta.py (entradas + estado + grade de 120 gestões), analise.py, robustez.py, motor_completo.py. Saídas: analise_saida.txt, robustez_saida.txt, motor_completo_saida.txt.
Método: 100 entradas enchidas (23 / 31 / 46 por ciclo), 1 contrato. Cada entrada é simulada ISOLADA (mesmo preço e instante de fill; muda só a saída). Stop = min(k·ATR15, 600 pts = R$120). Trailing: be1 = empate após +1 ATR; t2/t4/t8 = mín/máx das últimas N M15 fechadas.

## Teto e fixas (R$, soma das 100 entradas)
| | R$ |
|---|---|
| gestão atual do robo_v2 | 4.679 (ciclos: 1.424 / 2.412 / 843) |
| melhor fixa (in-sample): stop 2 ATR, sem alvo, sem trailing | 10.690 (isolado) |
| TETO retrospectivo (melhor das 120 por trade) | 16.864 (ciclos: 3.224 / 7.506 / 6.134) |
Motor completo (sequência de entradas, 1 posição, máx 3 ops): atual 4.679 (100 ops); stop 2/sem alvo 7.490 (64 ops); stop 1,5/sem alvo 7.143; stop 1/sem alvo 7.220; stop 1,5/alvo 3 = 5.002; alvo 2 = 3.684. O isolado superestima a fixa (posição aberta mais tempo bloqueia entradas seguintes); valor honesto ~7,5 mil.
Marginais (média sobre a grade): alvo sem = 7.507, alvo 3 = 4.328, alvo 2 = 3.312, alvo 0,75 = 1.256. Trailing: nenhum 4.501, t8 4.327, be1 4.006, t4 2.694, t2 1.830. O stop quase não importa (3.338 a 3.573).

## Atual × fixa × adaptativa (R$; adaptativa = 1 gestão por regime escolhida pelo R$ máximo no treino; regime com <5 trades usa a fixa)
| regime (parâmetros) | ciclos 0+1 -> 2: adapt | fixa | atual | LODO adapt | LODO fixa | LOCO soma adapt / fixa | LODO adapt-fixa, IC95 dias |
|---|---|---|---|---|---|---|---|
| ef>=0,20 dir x rot (6) | 1.962 | 2.383 | 843 | 8.060 | 8.112 | 9.171 / 9.714 | -53 [-1.742; 1.231] |
| vol4>=1,0 alta x baixa (6) | 2.759 | 2.383 | 843 | 9.884 | 8.112 | 10.055 / 9.714 | +1.771 [330; 3.581] |
| a favor x contra do dia (6) | 2.383 | 2.383 | 843 | 10.888 | 8.112 | 9.179 / 9.714 | +2.776 [697; 5.647] |
| natureza continuação x resto (6) | 2.801 | 2.383 | 843 | 10.515 | 8.112 | 10.172 / 9.714 | +2.403 [879; 4.170] |
| ef × vol, 4 regimes (12) | 2.190 | 2.383 | 843 | 8.612 | 8.112 | 8.064 / 9.714 | +500 [-1.772; 2.638] |
(a fixa tem 3 parâmetros; LOCO = deixa 1 ciclo fora e escolhe nos outros 2; atual na soma dos 3 ciclos = 4.679.)
Fixa LODO − atual = +3.434 (IC95 [54; 7.088]; 20 dias melhores, 22 piores). Fixa escolhida só em 0+1 (stop 2/sem alvo/t8) rende 2.383 no ciclo 2 contra 843 do atual.

## Mapas (50 dias)
- vol4: alta -> stop 2/sem alvo/nenhum; baixa -> stop 1/sem alvo/nenhum.
- a favor -> stop 1,5/sem alvo; contra (19 trades) -> stop 0,75/sem alvo/t2.
- continuação -> stop 1/sem; resto -> stop 2/sem/t8.
Em TODOS os regimes o alvo escolhido é "sem alvo". O que muda entre regimes é só o stop (1 a 2 ATR) e o trailing, diferenças de poucas centenas de R$.
Correlação estado × melhor stop por trade: |r| <= 0,26 (vol4 0,26; perna -0,21; hora -0,18); nenhuma variável de estado passa de 0,25 de correlação com R$ da fixa.

## Veredito
1. O ganho real é uma gestão FIXA: tirar o alvo e deixar correr (stop 1–2 ATR, sem trailing). Motor completo: +R$2.800 sobre o atual (4.679 -> 7.490) nos 50 dias, mas a escolha usa os mesmos 50 dias (in-sample); fora da amostra (escolha em 0+1, ciclo 2) +R$1.540 isolado.
2. A adaptação por estado NÃO é demonstrada. No LODO 3 regimes "vencem" a fixa, mas: pelo corte por ciclo (0+1 -> 2) o ganho é +376/+418 em dois regimes e 0 ou negativo nos demais; no leave-one-cycle-out somado só vol4 (+341) e natureza (+458) ficam acima, e 'a favor' perde no ciclo 0 (640 contra 1.395). Cinco definições de regime foram testadas (escolha de regime = liberdade extra), com 100 trades e 19-60 por regime. Não satisfaz "bate as duas fora da amostra" de forma estável.
3. O teto (16,9 mil) é 3,6× o atual e 1,6× a fixa, mas é retrospectivo: o estado observável explica quase nada dele.
4. gestor_adaptativo.py NÃO foi criado (nenhum mapeamento sobreviveu). Recomendação ao ciclo 3: testar a fixa "sem alvo, stop 1,5–2 ATR (teto 600 pts)" como mudança das FAZER, com os 20 dias novos como validação genuína; adaptar só se vol4 (alta -> stop mais largo) repetir no ciclo 3.
Limites: motor isolado ignora bloqueio de posição; trailing avaliado só nos fechamentos M15; stop capado em 600 pts (2 ATR ≈ cap, pois ATR15 médio ≈ 325); n=100; 49 dias com trade.
