# Escolha congelada

Congelado em: 2026-10-06 20:23:32 (hora local), ANTES de rodar qualquer data do holdout.

**Stop escolhido: 1500 pontos** (melhor score final suavizado entre os stops que nao quebram a conta: 3,250; ranking completo em out/ranking.csv).
Aviso declarado: 1500 e' a ponta da grade; a suavizacao usou so' um vizinho.

Convencao do holdout: replay da pagina, 1 contrato, R$1.000 inicial, R$2/operacao, sem alvo, flatten 18:20, ticks gerados de M1,
janela 2025-10-01..2025-12-18, vencimento/rolagem pela regra do EA. Somente o stop 1500.

Referencia de selecao do stop 1500: liquido somado das 5 janelas R$15.715 em 530 operacoes = R$29,65 por operacao.

"Sustenta" (pre-declarado) = TODOS:
1. liquido > 0;
2. R$/operacao >= 50% da media de selecao (>= R$14,82);
3. nao quebra (saldo nunca <= 0).

## Resultado do holdout (rodado uma vez)
n=23, liquido R$1.370, win 65,2%, PF 2,16, MaxDD R$617 (20,7%), saldo minimo R$999, sem quebra. R$/op 59,57 (2,0x a selecao). Nulo de direcao aleatoria: p=0,055 (200.000 sorteios). Sustenta pelos tres criterios. A janela 2025-10-01..2025-12-18 esta GASTA.
