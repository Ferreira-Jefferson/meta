# Z9-T5 prioridade fixa

Regra: robô de prioridade maior que quer operar toma a posição de um menor (zera a mercado a `preco(t)`, t = entrada do causador, e assume a `preco_entrada`; no mesmo lado só transfere a gestão: mantém o preço de entrada, vale a saída do maior, 1 operação, atribuída ao novo dono). Menor é bloqueado por maior. Empate de instante: maior primeiro. Saída natural a `preco_saida`. R$ = pontos x 0,20 x lado, custo R$2/operação, cada ano começa em R$1.000. Aproximação: robô bloqueado/interrompido não muda as operações seguintes dele.

## Ordens (decididas só com 2022-2025, gravadas em ordens.json antes de simular qualquer ano; sim.py)
Métricas isoladas 2022-2025 (com custo): líquido / fator de lucro / acerto
- WinGapBarra1 6.359 / 1,164 / 50,0%
- WinCincoMedias 6.279 / 1,192 / 45,4%
- WinDeslocamentoMatinal 4.307 / 1,419 / 46,4%
- WinRetanguloEma34 1.724 / 1,192 / 47,3%
- Win_c1 797 / 1,313 / 10,9%

Ordens (maior -> menor):
- P1 líquido: GapBarra1 > CincoMedias > DeslocMatinal > RetanguloEma34 > Win_c1
- P2 fator de lucro: DeslocMatinal > Win_c1 > CincoMedias > RetanguloEma34 > GapBarra1
- P3 acerto (pedido antigo do dono): GapBarra1 > RetanguloEma34 > DeslocMatinal > CincoMedias > Win_c1

## Por ano: líquido c/ custo (ops, acerto %, maior queda R$). Nenhuma variante nem a soma quebra em nenhum ano.
| ano | soma isolada | P1 líquido | P2 fator lucro | P3 acerto |
|---|---|---|---|---|
| 2022* | 5.026 (473, 42,9, 2.315) | 4.907 (270, 48,5, 1.917) | 4.437 (348, 44,0, 1.997) | 4.497 (275, 47,3, 1.860) |
| 2023* | 4.512 (455, 45,1, 2.108) | 3.355 (255, 49,8, 1.394) | 2.098 (318, 45,9, 1.837) | 3.647 (262, 50,8, 1.253) |
| 2024* | 4.720 (477, 44,9, 1.883) | 5.110 (266, 51,9, 1.475) | 2.860 (329, 44,7, 1.333) | 5.477 (267, 52,4, 1.444) |
| 2025* | 5.208 (344, 43,3, 3.112) | 2.915 (196, 47,4, 3.182) | 2.130 (234, 42,7, 1.271) | 3.215 (193, 48,2, 3.057) |
| 2026 (fora da escolha) | 14.079 (361, 45,2, 3.335) | 5.167 (208, 43,3, 2.506) | 6.010 (244, 43,0, 1.851) | 4.802 (212, 42,5, 1.691) |

(*) in-sample: a ordem foi escolhida com estes anos. Soma 2022-2025: isolada 19.466; P1 16.287; P2 11.525; P3 16.836.
Posições zeradas por prioridade / transferências de gestão (5 anos): P1 10 / 41; P2 150 / 334; P3 13 / 102.

## Por robô (líquido atribuído ao dono final da operação; ops entre parênteses) 2022 / 2023 / 2024 / 2025 / 2026
P1 (isolado entre colchetes é o mesmo robô sozinho):
- GapBarra1 1.214 / 1.291 / 2.287 / 1.567 / 5.740 (igual ao isolado: nunca é bloqueado)
- CincoMedias 3.204 / 981 / 2.481 / 1.831 / 112 [isolado 2.695 / 1.232 / 1.493 / 859 / 3.339]
- DeslocMatinal 392 / 468 / 197 / -273 / -865 [isol. -255 / 1.404 / 1.347 / 1.811 / 2.465]
- RetanguloEma34 252 / 404 / 163 / -171 / -123 [isol. 1.148 / 140 / -23 / 459 / 1.210]
- Win_c1 -155 / 211 / -18 / -39 / 303 [isol. 224 / 445 / -384 / 512 / 1.325]
P2:
- DeslocMatinal 3.742 / 3.889 / 4.281 / 4.650 / 7.788
- Win_c1 1.039 / 1.085 / 420 / 524 / 815
- CincoMedias 4.223 / 1.806 / 1.340 / 350 / 546
- RetanguloEma34 793 / 40 / 88 / -166 / 497
- GapBarra1 -5.360 / -4.722 / -3.269 / -3.228 / -3.636 (entra por último e leva 44-77 zeragens por ano a mercado)
P3:
- GapBarra1 1.214 / 1.291 / 2.287 / 1.567 / 5.740
- RetanguloEma34 944 / 1.356 / 169 / 314 / 771
- DeslocMatinal 712 / 1.063 / 1.628 / 1.099 / -1.028
- CincoMedias 1.807 / -234 / 1.416 / 274 / -958
- Win_c1 -180 / 171 / -23 / -39 / 277
(ops por robô e ano em res.json / trades_<variante>.csv)

## Observações
1. Seleção: P3 (acerto) é a melhor em 2022-2025 (16.836) com P1 muito perto (16.287); isso é escolher entre 3 ordens olhando o in-sample. Fora da amostra (2026) a ordem se inverte: P2 6.010 > P1 5.167 > P3 4.802, tudo bem abaixo da soma isolada 14.079. Diferença entre ordens em 2026 é pequena frente à perda para a soma isolada: o ordenamento pouco importa, a convivência custa.
2. Nenhuma prioridade fixa bate a soma isolada em 2023-2026 e só P1/P3 ganham em 2024 (5.110 / 5.477 vs 4.720). Em troca, a queda máxima cai em quase todos os anos (ex. 2026: 1.691-2.506 vs 3.335) e o acerto sobe de ~44% para ~48-52% in-sample (cai para ~43% em 2026). 1 contrato só: a soma isolada empilha posições simultâneas que aqui não existem, então a comparação com ela não é de mesmo risco.
3. P2 mostra o custo de pôr o robô mais lucrativo em último: o GapBarra1 (maior líquido isolado) fica negativo todos os anos (-3,2 a -5,4 mil) porque é zerado a mercado por todos os outros (150 zeragens, 334 transferências), enquanto o DeslocMatinal domina. Em P1/P3 o GapBarra1 no topo roda idêntico ao isolado; o 2026 de 5.740 vem quase só dele.

## Limitações
- Aproximação do enunciado: operações seguintes do robô interrompido/bloqueado não mudam (na realidade um robô bloqueado mudaria o estado dele); sinais existem só no instante da entrada.
- A zeragem a mercado usa `preco(t)` sem deslize extra; antes de 2026-02-20 os ticks são sintéticos (4 por M1).
- Transferência de gestão aplica a saída do robô maior ao preço de entrada do menor, que pode já estar além do stop dele; aqui não há reavaliação de stop no instante da transferência (a saída do maior é usada como é, `preco_saida` dele, que pode ter sido calculada a partir de outra entrada).
- O dono rejeitou regras que olham o mês anterior: as ordens aqui são fixas, mas foram escolhidas com 2022-2025 que inclui anos usados por outras frentes; 2026 é a única amostra honesta e é de 1 ano.
- Líquido por robô é atribuído ao dono final, não a quem originou a posição.
