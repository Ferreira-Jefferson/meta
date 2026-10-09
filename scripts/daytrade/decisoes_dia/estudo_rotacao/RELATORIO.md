# Estudo da rotação (robo_v4, 90 dias de `dias_usados.json`)

Estratos pela ef do dia inteiro: rotação < 0,15 (55 dias), intermediário 0,15-0,25 (14), direcional >= 0,25 (21). Aleatórios (ciclos 3+4) = 40 dias, dos quais 28 de rotação. Base: `cfg4.monta(robo_v4.IDS)` sem mudança = R$ 9.989,70 total, reponderado R$ 73,11/dia, pior dia -R$ 253,10, 25 dias negativos (24 de rotação, 1 intermediário). Todos os 169 trades do v4 usam 1 contrato.

## Resposta curta

| pergunta | resposta |
|---|---|
| Algum uso do estado causal melhora o v4? | **Não.** Nenhum dos usos com estado causal (E1/E2) tem Δ reponderado > 0: 0 positivos, 3 nulos (b1, d2/E2), o resto negativo (de -0,2 a -32). Só o oráculo (não causal) dá algo positivo: c4/OR +0,09 e d2/OR +1,14. |
| O estado causal é bom? | Fraco até 11h (AUC 0,52-0,72), razoável só a partir das 12h (0,81-0,86 para ef parcial). |
| A rotação perde de fato? | Só nos **aleatórios**: 28 dias de rotação, -R$ 25,6/dia, 17 negativos (-R$ 717). Nos 27 dias de rotação de escolha (c0-c2) o v4 dá **+R$ 69,3/dia**, mas as regras foram desenhadas em cima deles. |
| Teto se soubéssemos a rotação (a3/OR: não operar em rotação) | +R$ 717 nos 40 aleatórios, mas perde os +R$ 1.871 dos dias de rotação de escolha: Δ reponderado **-16,1**. Nem com clarividência vale parar. |

## Tabela 1. Resultado por fonte do trade, v4, 90 dias (ordenada pela perda em rotação)
"fora" = intermediário + direcional.
| fonte | rot n | rot R$ | rot acerto | int n | int R$ | dir n | dir R$ | fora(int+dir) R$ |
|---|---|---|---|---|---|---|---|---|
| 2025_08_01:F2 gap de baixa preenche (compra) | 1 | -102 | 0% | 0 | +0 | 0 | +0 | +0 |
| 2023_03_20:Recuo à EMA21 em baixa (venda) | 1 | -95 | 0% | 0 | +0 | 0 | +0 | +0 |
| 2023_11_03:Recuo à média 8 em tendência de alta | 6 | -94 | 33% | 0 | +0 | 1 | +152 | +152 |
| 2023_08_21:gap_preenchido | 1 | -92 | 0% | 1 | +178 | 1 | +178 | +356 |
| 2025_06_04:F5 compra suporte na rotacao da manha | 1 | -86 | 0% | 0 | +0 | 1 | +47 | +47 |
| 2022_11_29:falha_de_queda_1a_hora | 1 | -56 | 0% | 0 | +0 | 0 | +0 | +0 |
| c1:A3 reteste_minima_de_ontem | 1 | -53 | 0% | 0 | +0 | 0 | +0 | +0 |
| 2024_05_16:F2 vende falha da maxima matinal | 9 | -35 | 56% | 3 | +281 | 0 | +0 | +281 |
| 2024_01_19:gap de alta perde abertura (fecha o gap) | 2 | -18 | 50% | 0 | +0 | 1 | -60 | -60 |
| 2023_11_03:Rompimento da faixa da 1ª hora a favor do gap | 2 | -18 | 50% | 0 | +0 | 0 | +0 | +0 |
| 2022_11_16:venda nova minima sob abertura/VWAP | 0 | +0 | - | 1 | +131 | 2 | +97 | +228 |
| 2023_11_03:Nova máxima da tarde | 0 | +0 | - | 0 | +0 | 1 | +225 | +225 |
| 2025_06_04:F3 recuo na media em tendencia de baixa | 0 | +0 | - | 1 | +8 | 0 | +0 | +8 |
| 2025_08_01:F1 falha da minima de ontem (compra) | 0 | +0 | - | 1 | -36 | 3 | +211 | +175 |
| c1:A4 barra_de_expansao | 0 | +0 | - | 1 | +130 | 5 | +1.298 | +1.428 |
| 2023_03_20:Falha da alta inicial (venda) | 2 | +10 | 50% | 0 | +0 | 0 | +0 | +0 |
| 2025_06_04:F1 rompe minima da 1a hora (venda) | 10 | +12 | 60% | 10 | +1.152 | 4 | +1.087 | +2.240 |
| c3g:G4 flip | 1 | +26 | 100% | 1 | +217 | 1 | +470 | +687 |
| 2024_06_18:faixa_tarde | 1 | +32 | 100% | 0 | +0 | 0 | +0 | +0 |
| 2024_06_18:recuo_tendencia | 1 | +45 | 100% | 0 | +0 | 0 | +0 | +0 |
| 2022_11_29:recuo_a_favor_tendencia | 12 | +79 | 42% | 2 | +20 | 8 | +1.037 | +1.057 |
| 2023_08_21:minima_de_ontem | 1 | +79 | 100% | 0 | +0 | 0 | +0 | +0 |
| 2023_11_03:Impulso das 2 primeiras velas acima da máxima de ontem | 4 | +95 | 50% | 1 | +65 | 2 | +325 | +389 |
| 2022_11_16:venda pullback EMA20 em baixa | 13 | +95 | 54% | 2 | +576 | 0 | +0 | +576 |
| c3a:F1 retoma a abertura a favor do gap | 2 | +114 | 50% | 0 | +0 | 2 | +144 | +144 |
| 2023_08_21:falha_de_alta | 1 | +118 | 100% | 0 | +0 | 0 | +0 | +0 |
| 2023_03_20:Rompe mínima da 1ª hora (venda) | 2 | +149 | 50% | 2 | +350 | 1 | +118 | +468 |
| c2:P2 rompe faixa 1h com volume, alvo 1R | 3 | +239 | 100% | 0 | +0 | 0 | +0 | +0 |
| c2:C8 expansao_compressao | 1 | +268 | 100% | 0 | +0 | 0 | +0 | +0 |
| 2024_06_18:gap_fade_fechamento | 18 | +443 | 56% | 5 | +303 | 8 | +132 | +435 |


Leitura:
- Perdem em rotação e ganham fora, com n >= 2: **"Recuo à média 8 em tendência de alta"** (6 trades, -R$ 94 em rotação / +R$ 152 fora) e **"F2 vende falha da máxima matinal"** (9 trades, -R$ 36 / +R$ 281). Com n = 1 há outras (F5, F2 gap de baixa, A3), sem valor estatístico.
- Ganham em rotação: **gap_fade_fechamento** (18 trades, +R$ 443, acerto 56%), **P2 rompe faixa 1h com volume** (3, +R$ 239), **venda pullback EMA20** (13, +R$ 95), recuo a favor da tendência (12, +R$ 79), C8 (+R$ 268, n=1).
- Esses ganhos vêm dos dias de escolha. Nos 28 aleatórios de rotação, `venda pullback EMA20 em baixa` faz 8 trades e -R$ 308, e `gap_fade_fechamento` 8 trades e +R$ 27.
- Em rotação, por saída: 33 alvos (+R$ 3.010, média +91), 42 stops (-R$ 3.042, média -72), 22 fim de pregão (+R$ 1.186). Nenhuma fonte passa de n = 18.

## Tabela 2. O estado causal separa o dia que terminará em rotação? (AUC, orientação declarada antes)
Rótulo = ef do dia inteiro < 0,15. IS937 = calendário IS completo (só mercado, sem rodar robô; base de rotação 80%); 90d = amostra estratificada (base 61%). Features só com dados até a hora cheia (M15 fechadas, M1 < t). Orientação: ef parcial, amplitude/ATRd, gap e deslocamento baixos = rotação; cruzamentos de VWAP, sobreposição e proximidade do meio da faixa altos = rotação.
| populacao | feature | 10h | 11h | 12h | 13h |
|---|---|---|---|---|---|
| IS937 | ef_parc | 0,59 | 0,72 | 0,81 | 0,86 |
| IS937 | amp_atrd | 0,53 | 0,65 | 0,73 | 0,77 |
| IS937 | cruz_vwap | 0,54 | 0,61 | 0,66 | 0,70 |
| IS937 | sobrep | 0,52 | 0,60 | 0,62 | 0,63 |
| IS937 | meio_faixa | 0,54 | 0,63 | 0,73 | 0,73 |
| IS937 | gap_atrd | 0,52 | 0,52 | 0,52 | 0,52 |
| IS937 | desloc_atr15 | 0,57 | 0,71 | 0,81 | 0,86 |
| IS937 | voto>=3de4 | 0,55 | 0,66 | 0,73 | 0,78 |
| 90d | ef_parc | 0,67 | 0,81 | 0,82 | 0,86 |
| 90d | amp_atrd | 0,58 | 0,76 | 0,80 | 0,82 |
| 90d | cruz_vwap | 0,59 | 0,67 | 0,74 | 0,75 |
| 90d | sobrep | 0,53 | 0,64 | 0,63 | 0,68 |
| 90d | meio_faixa | 0,59 | 0,70 | 0,70 | 0,65 |
| 90d | gap_atrd | 0,58 | 0,58 | 0,58 | 0,58 |
| 90d | desloc_atr15 | 0,63 | 0,81 | 0,82 | 0,86 |
| 90d | voto>=3de4 | 0,58 | 0,75 | 0,75 | 0,77 |


Precisão no limiar = mediana do calendário (IS937):

| estado | 10h | 11h | 12h | 13h |
|---|---|---|---|---|
| E1 (ef parcial <= mediana): P(rotação / marcado) | 83% | 89% | 93% | 97% |
| E1: P(rotação / não marcado) | 76% | 70% | 66% | 62% |
| E2 (voto >= 3 de 4): P(rotação / marcado) | 81% | 88% | 92% | 95% |
| E2: P(rotação / não marcado) | 78% | 74% | 72% | 69% |
| base | 80% | 80% | 80% | 80% |

Às 10h o estado praticamente não informa (83% contra 80%). A partir das 12h informa, mas a maior parte das entradas já aconteceu. Gap (AUC 0,52), sobreposição e cruzamentos de VWAP são fracos; ef parcial e deslocamento/ATR15 são as melhores e são quase a mesma coisa. Acerto bruto no limiar mediana (`p2.log`) não é bom indicador porque a base é 80%.

## Tabela 3. Usos medidos sobre o v4, 90 dias
Δ em relação ao v4 sem mudança. E1/E2 = estados causais; OR = oráculo (ef do dia inteiro, não causal, só como teto). "d 40 aleat" = soma do Δ R$ nos 40 dias de ciclos 3+4. LOO mín = menor Δ reponderado tirando cada dia. Usos: a1/a2 = vetar fontes no estado; a3 = vetar toda entrada; b1 = 1 contrato; b2 = alvo x0,5; c1 = parar após 1ª perda; c2 = parar após 2 ops; c3 = parar após 1ª perda sem estado; c4 = parar se P&L do dia <= -R$ 100; d1/d2 = repertório de fade da borda da faixa.
| uso | estado | total R$ | rep R$/dia | d rep | d nd/dia | d rot/dia | d 40 aleat R$ | pior/melhor dia | LOO min | trades |
|---|---|---|---|---|---|---|---|---|---|---|
| base | - | 9990 | 73.1 | +0,00 | +0,00 | +0,00 | +0 | 0/0 | +0,00 | 169 |
| a1 | E1 | 9492 | 66.2 | -6,93 | -7,21 | -8,46 | -278 | 7/3 | -7,48 | 159 |
| a1 | E2 | 9461 | 65.7 | -7,36 | -7,66 | -7,60 | -284 | 7/2 | -7,92 | 160 |
| a1 | OR | 9673 | 68.7 | -4,41 | -4,58 | -5,75 | -23 | 8/5 | -7,16 | 157 |
| a2 | E1 | 9672 | 69.2 | -3,86 | -3,92 | -4,34 | -104 | 9/6 | -5,30 | 155 |
| a2 | E2 | 9543 | 67.4 | -5,66 | -5,80 | -5,26 | -208 | 9/4 | -6,95 | 157 |
| a2 | OR | 9918 | 72.1 | -1,00 | -1,04 | -1,30 | +169 | 12/8 | -3,70 | 153 |
| a3 | E1 | 7200 | 40.9 | -32,24 | -32,48 | -14,68 | -663 | 26/12 | -35,36 | 127 |
| a3 | E2 | 7797 | 47.1 | -26,03 | -26,36 | -13,57 | -242 | 20/10 | -29,06 | 138 |
| a3 | OR | 8836 | 57.0 | -16,08 | -16,73 | -20,98 | +717 | 28/24 | -19,90 | 72 |
| b1 | E1 | 9990 | 73.1 | +0,00 | +0,00 | +0,00 | +0 | 0/0 | +0,00 | 169 |
| b1 | E2 | 9990 | 73.1 | +0,00 | +0,00 | +0,00 | +0 | 0/0 | +0,00 | 169 |
| b1 | OR | 9990 | 73.1 | +0,00 | +0,00 | +0,00 | +0 | 0/0 | +0,00 | 169 |
| b2 | E1 | 9399 | 67.1 | -5,97 | -5,85 | +4,15 | -166 | 20/8 | -8,94 | 174 |
| b2 | E2 | 9688 | 69.7 | -3,37 | -3,37 | +4,47 | -40 | 16/8 | -6,31 | 173 |
| b2 | OR | 9567 | 67.2 | -5,90 | -6,13 | -7,69 | +123 | 27/12 | -8,88 | 177 |
| c1 | E1 | 9198 | 64.9 | -8,21 | -8,09 | -6,20 | -52 | 9/4 | -10,98 | 156 |
| c1 | E2 | 9508 | 66.4 | -6,72 | -6,99 | -4,82 | -135 | 5/2 | -9,48 | 162 |
| c1 | OR | 9496 | 66.2 | -6,88 | -7,16 | -8,98 | +184 | 12/9 | -9,64 | 142 |
| c2 | E1 | 9581 | 67.4 | -5,69 | -5,92 | -7,43 | +13 | 3/2 | -7,12 | 164 |
| c2 | E2 | 9734 | 69.5 | -3,56 | -3,70 | -4,64 | +13 | 2/1 | -4,96 | 166 |
| c2 | OR | 9599 | 67.7 | -5,45 | -5,67 | -7,11 | +22 | 6/6 | -7,23 | 157 |
| c4 | E1 | 9817 | 70.7 | -2,41 | -2,51 | -3,14 | +95 | 1/1 | -3,79 | 167 |
| c4 | E2 | 9817 | 70.7 | -2,41 | -2,51 | -3,14 | +95 | 1/1 | -3,79 | 167 |
| c4 | OR | 9996 | 73.2 | +0,09 | +0,09 | +0,11 | +274 | 1/3 | -1,41 | 165 |
| d1 | E1 | 9767 | 70.0 | -3,11 | -3,23 | +0,18 | -233 | 2/1 | -3,50 | 166 |
| d1 | E2 | 9975 | 72.9 | -0,21 | -0,22 | -0,27 | +0 | 1/0 | -0,21 | 168 |
| d1 | OR | 9867 | 71.4 | -1,71 | -1,77 | -2,22 | -117 | 6/4 | -2,59 | 160 |
| d2 | E1 | 9757 | 69.9 | -3,25 | -3,37 | +0,00 | -233 | 1/0 | -3,29 | 168 |
| d2 | E2 | 9990 | 73.1 | +0,00 | +0,00 | +0,00 | +0 | 0/0 | +0,00 | 169 |
| d2 | OR | 10072 | 74.3 | +1,14 | +1,19 | +1,49 | +28 | 1/3 | +0,26 | 165 |
| c3 | - | 7513 | 53.5 | -19,60 | -18,04 | -8,98 | -730 | 21/9 | -22,52 | 129 |


Notas:
- **Declarados antes de ver qualquer efeito no robô** (cabeçalho de `p3_usos.py`, escrito antes de rodar): estados E1/E2/OR com limiares = medianas do calendário IS por hora (vêm de `p2_resultado.json`, sem usar resultado do robô); antes das 10h o estado é "não rotação"; usos b, c, d e seus parâmetros (0,85/0,15 da faixa, faixa >= 4 ATR15, stop 0,5 ATR15, alvo no meio da faixa, recompensa >= risco, -R$ 100).
- **NÃO declarados antes: as listas de fontes de a1 e a2** saem da Tabela 1, nos mesmos 90 dias (in-sample). A regra de seleção (n_rot >= 2 e R$rot < 0 e R$fora > 0 para a1; R$rot < 0 e R$fora >= 0 para a2) foi fixada antes de medir o efeito, mas a lista vem dos dados testados. Mesmo assim os Δ são negativos.
- b1 é nulo: o v4 só usa 1 contrato. Redução de mão não é alavanca nesta versão.
- c3 (parar após a 1ª perda, sem estado) piora tudo (Δrep -19,6, 37 dias negativos): o robô depende de reentrar depois de um stop.
- b2 (alvo x0,5) melhora os dias de rotação em E1/E2 (+4,2/+4,5 R$/dia) mas corta os dias bons: Δrep -6,0/-3,4. Confirma o que já se sabia (alvo curto).
- d1/d2 quase não disparam com E2 (0 a 1 trade a mais); com E1 disparam e perdem.

## O que isso diz sobre o problema

1. O prejuízo em rotação não aparece concentrado em uma fonte ou horário. Nos 28 aleatórios de rotação, o v4 perde -R$ 717 espalhado por 20 fontes (maior: pullback EMA20 em baixa, -R$ 308 em 8 trades), e por trade por hora de sinal: 10h -R$ 31, 11h -R$ 30, 12h -R$ 7, 13h -R$ 35 (n pequeno).
2. A diferença entre "rotação ganha" (+69/dia) e "rotação perde" (-26/dia) é viés de seleção: os 50 dias de escolha foram os usados para desenhar as regras. A estimativa honesta de rotação é a dos 28 dias aleatórios, e é ruidosa (17 de 28 negativos, 56 trades).
3. O estado só é legível tarde (12-13h, AUC 0,81-0,86), e mesmo com informação perfeita (oráculo) parar ou reduzir perde no reponderado. Gerir a rotação com um estado do dia no formato "desliga/reduz/para" não funciona neste robô.
4. Em rotação o robô é payoff assimétrico (alvo +91, stop -72, acerto 34% nos alvos). A "queda" na rotação é compatível com variância de acerto, sem efeito de regime mensurável com 28 dias.

## Propostas para o pré-registro do ciclo 5

| # | proposta | status | justificativa |
|---|---|---|---|
| 1 | Não adotar veto/redução/parada baseado em estado causal de rotação. | registrar como refutado | 0 de 31 passam; o oráculo também perde (a3/OR -16,1). |
| 2 | Ampliar a amostra de rotação aleatória antes de qualquer tese de rotação: sorteio de pelo menos 40 dias novos do IS (fora dos 90, nunca abr-out/2026), v4 reportado por estrato. | a pré-registrar | 28 dias de rotação e 17 negativos não dão IC útil; é o que mais falta. |
| 3 | Uma única variante do estado: só depois das 12:00, E1 (ef parcial <= mediana das 12h) + veto das duas fontes da lista a1 ("Recuo à média 8 em tendência de alta", "F2 vende falha da máxima matinal"), testada apenas em dados novos. | hipótese, uma variante | única janela em que o estado separa (AUC 0,81). Lista de 2 fontes com n pequeno: só vale em dado novo. Nesta rodada a1 foi testada desde as 10h e deu -6,9. |
| 4 | Não repetir: parar após 1ª perda (c1/c3), alvo x0,5 em rotação (b2), fade da borda da faixa com estado causal (d1/d2). | registrar como refutado | Δ reponderado de -3 a -20. |
| 5 | Redução de mão só existe se o ciclo 5 abrir 2 contratos por regra (tese separada). | nota | b1 nulo, o v4 só usa 1 contrato. |
| 6 | Antes de buscar causa da rotação: IC do R$/dia de rotação nos aleatórios por bootstrap por dia. | análise | n por fonte <= 18, 28 dias. |

## Arquivos
`common.py` (estimativas causais `feats`, estratos, métricas), `p1_tabela_fontes.py` (+ `p1.log`, `p1_fontes.json`, `v4_90.json`), `p2_auc_regime.py` (+ `p2.log`, `p2_resultado.json`, `p2_feats.json`), `p2b_precisao.py` (`p2b.log`), `p3_usos.py` (+ `p3.log`, `p3_res.json`, `p3_resumo.json`), `p4_extras.py` (`p4.log`), `p5_relatorio_tabelas.py`, `p6_monta_relatorio.py`, `tabelas.md`. Nenhum arquivo existente alterado; mt5/ não tocado; sem commit.
