# Rodada 6 - WinGapBarra1, jan-abr/2026, alvo a mercado (escrito ANTES de rodar/ranquear)

## Janela e convencao
- Unica janela: 2026-01-02..2026-04-30 (nenhuma outra data e' rodada). Conta continua, 1 contrato, R$1.000 inicial; "quebrou" = saldo <= 0 apos uma operacao fechada, e a conta para ali.
- Replay da pagina (comparativo_win_2026/port_win_gap_barra1.py): ticks sinteticos (4 por M1) ate 2026-02-19, reais de 2026-02-20 em diante.
- Entrada: limite no close da barra das 09:00, valida ate 09:35, convencao do port (enche ao tocar, a partir do tick seguinte). Nenhum custo extra de entrada.
- Saidas, TODAS a mercado, preco = last do tick que toca o nivel (pior em gaps, convencao do port): stop (entrada -/+ stop), alvo (entrada +/- k x stop; escolha explicita do dono, revoga aqui a regra "nunca alvo a mercado"), zeragem 18:20.
- Custo: R$5 por contrato por saida a mercado (taxas + deslize). Como toda operacao termina em exatamente uma saida a mercado, = R$5 por operacao, no lugar dos R$2 do port. Substitui, nao soma.
- Grade: stops 400..1500 (passo 100, 12 valores) x alvo {2x, 3x, 4x do stop, sem alvo (regra atual, referencia)} = 48 celulas. Sem alvo = so stop e 18:20.
- Se stop e alvo cabem no mesmo tick sequencial, vale o que ocorre primeiro por indice de tick (stop e alvo nao ocorrem no mesmo tick).

## Metricas por celula
trades, liquido, win%, payoff, profit factor, MaxDD R$ e % (pico inicial R$1.000), fator de recuperacao (liquido/MaxDD R$), pior trade, perda media, max perdas consecutivas, saidas por tipo (stop/alvo/18:20), liquido por mes (jan..abr), saldo minimo, quebrou?

## Ranking multicriterio (media de postos ponderada, 1 = melhor, empate = posto medio)
Postos entre as 48 celulas (a coluna "sem alvo" entra no mesmo ranking e e' sinalizada). Oito metricas, soma dos pesos = 8:
1. Fator de recuperacao total = liquido / MaxDD R$ (peso 1; com 2 abaixo forma o peso 2 do FR)
2. Segunda metrica de FR: mediana dos liquidos mensais (4 meses) / MaxDD R$ (peso 1)
3. Profit factor (1)
4. Win% (1)
5. Meses positivos de 4 (1, maior melhor)  [substitui "janelas positivas"]
6. Liquido do pior mes (1, maior melhor)
7. Maximo de perdas consecutivas (1, menor melhor)
8. MaxDD % (1, menor melhor)  [unica janela, entao e' o pior DD%]
score = soma(peso x posto)/8.

Suavizacao de plato: score final = media do score da celula e das vizinhas imediatas de stop (+-100 pts) dentro do MESMO multiplo de alvo (pontas usam a unica vizinha). Menor score final = melhor.
Eliminatorio: celula que quebra a conta nao pode ser escolhida (aparece no ranking marcada, fora do top 10).
Desempate: menor stop.

## Nulos (estatistica = liquido R$ da celula; tambem FR)
- Direcao aleatoria, celula top: >= 10.000 sorteios; em cada dia de sinal o lado e' sorteado 50/50 (mesmos dias de sinal, mesma geometria, mesmo custo); p = P(liquido nulo >= observado).
- Max-estatistica sobre as 48 celulas: cada sorteio de direcao (um lado por dia, comum a todas as celulas) calcula o liquido das 48 celulas; guarda o maximo; p corrigido pela selecao = P(max nulo >= liquido observado da celula top). Idem para FR.
- Aproximacao: o nulo nao aplica a regra de quebra de conta (liquido e DD sobre a sequencia completa).

## Ressalvas (fazem parte do resultado)
- NAO e' fora da amostra: jan-mar/2026 ja foram vistos no replay da pagina (jan -139, fev +765, mar -419 com stop 1200, custo R$2) e abril esta na janela de descoberta.
- n ~ 35-40 operacoes por celula; o poder e' declarado no relatorio.
