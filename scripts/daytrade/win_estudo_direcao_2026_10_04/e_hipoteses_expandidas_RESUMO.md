# WIN: hipóteses expandidas sobre memória de curto prazo

Base: WIN@D M1 (ajuste por diferença), 1.219 pregões válidos (>=500 barras, ATR de 14 dias disponível). IS = 786 pregões (até 2024-12-31), OOS = 433. Tudo normalizado pelo ATR14 do range diário (só passado, deslocado 1 dia). Nulos: independência de sinais (P = px·py + (1-px)(1-py)), espelho de nível, ou correlação zero. Sem scipy: p-valores por aproximação normal. Resultado completo em `e_hipoteses_expandidas.csv`.

## As 15 hipóteses geradas
1. 1ª hora (09:00-10:00) prevê o sinal do resto do dia. (testada)
2. 1ª hora concordando/discordando de D-1 muda a continuação. (testada)
3. NR7/NR4 em D-1 gera expansão de range em D. (testada)
4. Persistência de range: range(D-1)/ATR prevê range(D)/ATR. (testada)
5. |gap|/ATR prevê o range do dia. (testada)
6. Últimos 30 min de D-1 prevêem o gap, a 1ª hora e o dia de D. (testada)
7. Máxima, mínima, fechamento, ponto médio e VWAP de D-1 como ímãs/reação vs nível espelhado. (testada)
8. Horário da máxima/mínima do dia (1ª hora) vs direção do dia. (testada, mas descritiva: usa informação do fim do dia)
9. WDO de D-1 prevê WIN de D (defasado); WDO do mesmo dia como referência. (testada)
10. Pós-dia extremo (>1 e >1,5 ATR): continua ou reverte, em 1 e em 5 dias. (testada)
11. Volume relativo de D-1 prevê o range de D e modula a persistência direcional. (testada)
12. Dia em que a 1ª hora fez o extremo e nunca mais o revisitou (tendência "limpa"): frequência e persistência nos dias seguintes. (não testada)
13. Razão corpo/range de D-1 (dia de convicção vs indecisão) prevê o range de D. (não testada)
14. Fechamento de D-1 no terço superior/inferior do range prevê o gap fechado ou não. (não testada)
15. Cruzamento WIN×WDO: divergência de D-1 (os dois subindo juntos, anômalo) prevê reversão em D. (não testada)

## Resultados (IS | OOS | nulo | sobrevive)
Sobrevive = p<0,05 nas duas janelas, mesmo sentido.

| hipótese | tipo | IS | OOS | nulo | sobrevive? |
|---|---|---|---|---|---|
| H1 sinal da 1ª hora → sinal do resto | direção | 53,8% (n=781, IC 50,3-57,2) | 51,4% (n=430, IC 46,7-56,1) | 50,0% | não (IS marginal, OOS nada) |
| H1b 1ª hora → resto, Spearman | direção | 0,036 | 0,017 | 0 | não |
| H1c 1ª hora concorda com D-1 → continua | direção | 54,8% (n=374) | 51,9% (n=208) | 50,0% | não |
| H1c 1ª hora discorda de D-1 → continua | direção | 52,8% (n=407) | 50,9% (n=222) | 50,0% | não |
| H2 NR7 → range D/ATR | volatilidade | 1,068 vs 0,995 (p=0,043; n=115) | 1,014 vs 1,026 (n=58) | não-NR7 | não |
| H2b NR4 → range D/ATR | volatilidade | 1,046 vs 0,993 | 1,042 vs 1,018 | não-NR4 | não |
| H3 range(D-1)/ATR → range(D)/ATR | volatilidade | -0,020 | -0,031 | 0 | não |
| H3b \|gap\|/ATR → range D/ATR | volatilidade | 0,038 | -0,012 | 0 | não |
| H4a últimos 30 min D-1 → sinal do gap | direção | 40,8% concordam (n=774, p<0,0001) | 45,1% (n=419, p=0,052) | 50% | quase: sentido contrário ao movimento (reversão para o gap), OOS marginal |
| H4b últimos 30 min D-1 → 1ª hora D | direção | 48,8% | 51,1% | 50% | não |
| H4c últimos 30 min D-1 → dia D | direção | 50,8% | 53,2% | 50% | não |
| H5 máxima D-1: P(tocar) vs espelho | níveis | 45,0% vs 47,7% | 43,1% vs 45,3% | espelho | não |
| H5 mínima D-1 | níveis | 46,6% vs 41,6% (p=0,059) | 45,2% vs 43,0% | espelho | não |
| H5 fechamento D-1 | níveis | 70,9% vs 69,3% | 71,7% vs 65,1% (p=0,115) | espelho | não |
| H5 ponto médio D-1 | níveis | 58,7% vs 54,1% | 59,9% vs 57,6% | espelho | não |
| H5 VWAP D-1 | níveis | 59,9% vs 56,1% | 60,5% vs 59,5% | espelho | não |
| H5r rejeição 30 min após toque (5 níveis) | níveis | todas dif. com IC cruzando 0 | idem | espelho | não (0/5) |
| H6 mínima do dia na 1ª hora → dia de alta | forma (olha o futuro) | 95,3% (n=211, IC 91,5-97,4) | 91,4% (n=151) | 51,9% / 51,0% | sim, mas não é previsão: só se sabe ao fim do dia |
| H6 máxima do dia na 1ª hora → dia de baixa | forma (olha o futuro) | 92,7% (n=220) | 90,1% (n=142) | 47,7% / 48,7% | sim, mesma ressalva |
| H7a WDO(D-1) → WIN(D) | direção | 49,6% | 49,9% | 50% | não |
| H7b WDO(D) vs WIN(D), mesmo dia (referência) | direção | 33,1% concordam (n=780) | 33,9% (n=425) | 50% | sim (correlação negativa conhecida, estável nas duas janelas) |
| H8 pós-dia >1 ATR → D mesmo sinal | direção | 58,1% (n=105, IC 48,5-67,1) | 47,3% (n=55) | 49,2% / 48,5% | não |
| H8 pós-dia >1,5 ATR | direção | 50,0% (n=24) | 31,6% (n=19) | ~49% | não (n minúsculo) |
| H8b pós-dia >1 ATR → 5 dias | direção | 57,5% (n=106) | 54,5% (n=55) | 53,4% / 49,9% | não |
| H9a volume rel. D-1 → range D/ATR | volatilidade | rho 0,155 (IC 0,086-0,223) | rho 0,123 (IC 0,029-0,215) | 0 | **sim** |
| H9b vol D-1 alto → D segue D-1 | direção | 49,6% (n=258) | 49,0% (n=147) | 49,2% / 48,5% | não |
| H9b vol D-1 baixo → D segue D-1 | direção | 46,2% (n=273) | 49,2% (n=132) | idem | não |

Comparações múltiplas: 62 p-valores em 31 linhas-hipótese (cada uma nas duas janelas). Por acaso se esperam ~3,1 com p<0,05; saíram 11, mas 6 são H6 (informação do futuro) e H7b (referência), dois dos quais não são testes preditivos. Descontando isso, restam 3 achados preditivos reais: H9a (duas janelas) e H4a (IS forte, OOS marginal). Nenhum deles prevê a direção do dia.

## Conclusão honesta
- Direção: o passado imediato (D-1, últimos 30 min de D-1, WDO de D-1, dia extremo, 1ª hora) não prevê a direção do WIN em D. Todas as taxas ficam entre 46% e 55%, com IC cobrindo 50% na OOS. O único sinal de direção com cara de real é H4a: o gap de D tende a ir CONTRA os últimos 30 min de D-1 (59% IS, 55% OOS discordam). É reversão do fluxo de fim de pregão, não continuação. OOS ainda marginal (p=0,052); fica como candidata, não como achado.
- Volatilidade/forma: o que o passado prevê é a escala. O volume relativo de D-1 (contra a média de 20 dias) prevê o range de D além do que o ATR já capta (rho ≈ 0,12-0,16, estável nas duas janelas). NR7/NR4 aparecem fracos (+7% no IS, nada no OOS). A persistência de range puro deu zero porque o ATR14 do denominador já absorve a persistência. Portanto "range de ontem" já está embutido no ATR; o que sobra de informação é volume.
- Níveis de D-1 (máx, mín, fechamento, meio, VWAP) não são ímãs nem suportes/resistências melhores que o nível espelhado à mesma distância. Os níveis dentro do range (fechamento, meio, VWAP) são tocados em 60-70% dos dias, mas o espelho também, então é efeito de distância, não de memória.
- H6 é uma descrição, não um sinal: dia com mínima na 1ª hora quase sempre fecha em alta (91-95%), mas isso só é conhecido depois. A versão tradável seria "às 10:00 o preço está na mínima do dia até agora", que não foi medida.
- WDO×WIN: só existe correlação negativa no mesmo dia (concordam em 33%); defasada é zero.
- Limitações: ajuste por diferença (percentuais aproximados, normalizei por ATR); ATR do range em vez de ATR de True Range; 62 testes; sem scipy (p por aproximação normal); H5 limita níveis a 0,05-3 ATR da abertura.

## Sugestões para a próxima rodada
1. H4a refinada: reversão dos últimos 30 min de D-1 no gap. Testar com janelas de 15/45/60 min, condicionando ao tamanho do gap (>0,3 ATR) e a fechar o gap em D. É a única pista direcional.
2. Versão tradável de H6: às 10:00, preço no extremo do dia até agora (mínima/máxima móvel) e a probabilidade de ele permanecer sem ser revisitado até o fim. Mede a "tendência limpa" sem olhar o futuro (hipótese 12).
3. Volume relativo de D-1 como filtro de tamanho/escala (alvo e stop em múltiplos do ATR ajustados por volume), pois prevê range, não direção.
4. Razão corpo/range e localização do fechamento de D-1 (hipóteses 13 e 14) contra range e gap de D.
5. Janela semanal/mensal da tese do dono mediada por volatilidade (previsão de escala), já que o nível diário não deu direção.

Arquivos: `C:\Users\Jeffe\Documents\study\meta\scripts\daytrade\win_estudo_direcao_2026_10_04\e_hipoteses_expandidas.py`, `e_hipoteses_expandidas.csv` (separador `;`, vírgula decimal), este RESUMO.
