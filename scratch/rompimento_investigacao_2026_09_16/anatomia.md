# Anatomia do pós-rompimento — WIN@, IS (129 pregões, < 2026-06-13)

Território: o que acontece DEPOIS do rompimento de retângulo (não a definição
do rompimento, não o que prediz, não a executabilidade). Fonte:
`scripts/daytrade/rompimento_anatomia_pos_retorno_2026_09_16.py` (log ao
lado). Base: mesmo detector de produção (`detecta_retangulo`, W=20,
tolerância 0,20, largura mínima 328) e mesma regra de morte do robô
(`MARGEM_MORTE=0,25`, `BARRAS_MORTE=3`) usadas em
`rompimento_retangulo_fenomeno_2026_09_16.py`. 417 rompimentos.

## Bug de método encontrado e corrigido nesta rodada (registrar para não repetir)

Primeira versão: os contadores de "reconfirma o rompimento" (mesma regra de
morte aplicada de novo) começavam a contar A PARTIR DA PRÓPRIA BARRA DE
DETECÇÃO. Como a barra de detecção JÁ é, por definição, uma barra que fechou
além da margem, a inércia normal de 1-3 barras seguintes reconfirmava a
MESMA regra quase sempre — antes de o preço ter qualquer chance de retestar.
Resultado da 1a passada: 76,5% "nunca retesta" (deveria ser MENOR que os
30,7% já medidos no script-irmão, não maior — o script-irmão usa horizonte
de só 60 barras, e um horizonte maior só pode aumentar a taxa de reteste,
nunca diminuir). Fix: os contadores de reconfirmação só começam a contar
DEPOIS do primeiro toque na borda (`tocou_idx`). Depois do fix, (b)+(c) =
82,0% >= 69,3% do script-irmão, na direção certa. Ver docstring de
`classifica()` no script.

Segundo bug (menor): a semente do nulo por pregão usava `hash(dia_iso)`, que
o Python RANDOMIZA por processo (`PYTHONHASHSEED`) — o nulo mudava a cada
execução. Trocado por `dia.toordinal()` (estável); reprodutibilidade
confirmada rodando duas vezes e comparando byte a byte.

## Q: A árvore de desfechos — frequência, tempo, magnitude

| ramo | n | % de todos | barras até o desfecho (mediana) | profundidade máx (mediana, pts) | R$/contrato (mediana) |
|---|---|---|---|---|---|
| (a) nunca retesta a borda | 75 | 18,0% | 304 (pregão restante) | 0 | 0,00 |
| (b1) retesta, NÃO entra, RETOMA | 57 | 13,7% | 11 | 23 | 4,52 |
| (b2) retesta, NÃO entra, indefinido | 1 | 0,2% | 5 (até tocar) | 21 | 4,26 |
| (c1) ENTRA, sai de novo MESMO lado | 187 | 44,8% | 31 (méd 56,5, dp 66,5, p25 15, p75 68,5) | 211 (méd 251,7, dp 197,1) | 42,20 |
| (c2) ENTRA, atravessa até a OPOSTA | 84 | 20,1% | 51 (méd 77,4, dp 74,5, p25 33, p75 93) | 811 (méd 838,4, dp 195,2) | 162,11 |
| (c3) ENTRA, passa o meio, indefinido | 10 | 2,4% | 39 (até entrar) | 502 | 100,46 |
| (c4) ENTRA, fica raso | 3 | 0,7% | 25 (até entrar) | 140 | 27,94 |

Conferência cruzada: (b)+(c) = 342/417 = 82,0%, e tem de ser **≥** 69,3% (o
reteste do script-irmão, medido em horizonte de 60 barras — aqui o horizonte
é o pregão inteiro). Bate na direção certa.

**Conjectura:** a magnitude de (c2) (mediana 811 pts, R$162/contrato bruto)
domina em ordem de grandeza qualquer coisa que (a) ou (b) oferecem (que são
~0 por definição — não há posição a favor desses ramos). Se existe uma
estratégia aqui, ela vive em capturar (c2) ou em explorar que (c1) é 2,2×
mais frequente que (c2) mas devolve só ~211 pts de profundidade útil antes
de reverter — ou seja, entrar no retângulo tem de assumir que na maioria das
vezes (65,8% dos que entram) o preço vai só até ~0,4 da largura antes de sair
de novo pelo mesmo lado.

## Q: Volta? Retoma ou entra? — a pergunta textual do dono

De 342 rompimentos que retestam a borda (82,0% de 417):
- **NÃO entra** (retoma o rompimento ou fica indefinido no toque): 58 (17,0%)
- **ENTRA** no retângulo (fecha do lado de dentro): 284 (83,0%)

Entre os que NÃO entram, 57 de 58 (98,3%) CONFIRMAM a retomada (voltam a
fechar além da borda por 3 barras) — o "indefinido sem entrar" é
praticamente inexistente (1 caso).

**Resposta direta, textual:** dado que o preço retesta a borda, ele entra no
retângulo MUITO mais do que retoma o rompimento (83,0% contra 17,0%). E
quando ele NÃO entra, ele quase sempre (98,3%) confirma a retomada — não
fica "grudado" na borda por muito tempo (mediana 11 barras).

**Comparação com o nulo (calculada à mão a partir das duas tabelas do log,
já que o nulo sempre "retesta" por construção — ver limitação abaixo):**
NULO: de 417 retestes, 104 não-entram (24,9%) e 313 entram (75,1%). REAL
entra mais (83,0% vs 75,1%, **+7,9 pp**) — um toque num nível que É a borda
de um rompimento validado tem MAIS chance de virar entrada de verdade do que
um toque genérico num nível qualquer. É a única diferença clara entre real e
nulo nesta árvore.

## Q: Até onde vai o retorno ao retângulo, dado que entrou?

Dos 284 que entram: 65,8% saem de novo pelo MESMO lado (c1, profundidade
mediana 211 pts = 0,4 da largura), 29,6% atravessam até a borda OPOSTA (c2,
profundidade mediana 811 pts = 1,7× a largura, passando 270 pts da borda
oposta), e só 4,6% ficam indefinidos (c3+c4) — a maioria dos que entram
RESOLVE dentro do pregão, para um lado ou para o outro.

**Conjectura:** não existe "ficar no meio" como desfecho comum — a
distribuição é bimodal: ou o preço sai de novo raso (mediana 0,4 da largura)
ou atravessa TUDO (mediana 1,7×). Isso é coerente com o achado já registrado
do `win_retangulo` de que "o alvo tinha de ser MAIOR, não menor" — o preço,
quando decide ir, vai além da borda oposta, não para o meio.

## Q: O desfecho depende de quanto já andou na detecção?

Corte na mediana do afastamento (263 pontos):

| | CURTO (< 263) n=208 | ESTICADO (≥ 263) n=209 |
|---|---|---|
| (a) nunca retesta | 13,9% | 22,0% |
| (b1)+(b2) retoma/indefinido | 15,9% | 12,0% |
| (c1) sai mesmo lado | 44,7% | 45,0% |
| (c2) atravessa oposta | 22,1% | 18,2% |

**Conjectura REFUTADA (era a hipótese do próprio pedido):** "quanto mais
esticado, mais provável voltar" — os dados mostram o OPOSTO. Rompimentos
ESTICADOS retestam MENOS (78,0% contra 86,1%) e atravessam menos até a
oposta (18,2% contra 22,1%). Interpretação: o afastamento na detecção não é
"exaustão" — é força do movimento. Quanto mais o preço já andou quando o
rompimento é confirmado, mais ele tende a continuar andando (momentum), não
a reverter. Isto é consistente com o Q2 do script-irmão (razão MFE/MAE de
0,92, abaixo do nulo 1,09) já mostrar que o rompimento cru não tem
continuação líquida — mas dentro da amostra que TEM afastamento maior, a
tendência remanescente pesa mais que a reversão.

## Q: Segundo rompimento — depois de entrar, rompe de novo?

- Reconfirma MESMO lado (c1): 187 de 417 (44,8%)
- Rompe o lado OPOSTO (c2, segundo rompimento de verdade): 84 de 417 (20,1%)
- Dado que há um 2º rompimento, fração que foi para o lado OPOSTO: 31,0%
- NULO: razão oposto = 31,5% (praticamente igual)

**Conjectura:** não há viés estrutural de lado no segundo rompimento — a
razão real (31,0%) é estatisticamente indistinguível do nulo (31,5%) e do
"nulo teórico" de 50% ambos os dois ficam abaixo dele, o que sugere que,
DADO que o preço vai romper de novo depois de entrar, ele prefere reconfirmar
o MESMO lado (c1) quase 2,2× mais que virar para o oposto (c2) — em real E
em nulo igualmente. Isso não é uma vantagem do rompimento validado sobre o
acaso: é uma propriedade genérica de "depois de qualquer nível tocado, o
lado de onde você veio é mais provável de vencer de novo" — provavelmente
viés de tendência de curto prazo comum a ambas as amostras.

## Limitação de método, declarada

O NULO usa como "borda" o próprio preço de fechamento do instante sorteado
(gap zero), enquanto o evento real só é classificado depois de já ter
percorrido uma distância (mediana 263 pontos) além da borda real. Isso torna
o nulo **trivialmente "retestado"** quase sempre no primeiro bar seguinte
(100% de reteste no nulo contra 82,0% no real) — não é comparável para a
pergunta "qual a chance de retestar", só para "dado que retestou, o que
acontece depois" (que é a comparação que o relatório usa). Uma comparação
mais justa da TAXA de reteste exigiria um nulo que também parta de um ponto
já afastado ~263 pontos de algum nível de referência — não construído aqui
por prazo.

## Perguntas abertas (não respondidas nesta rodada)

1. **O que acontece DEPOIS do segundo rompimento (c1)?** Ele reteste de novo
   e entra de novo (rompimento "duplo-falso")? Não medido — dado o volume de
   c1 (187 casos), esta é provavelmente a próxima pergunta mais barata.
2. **Existe assimetria alta/baixa?** Não separei os 417 eventos por
   `lado` na árvore — o script-irmão mostra 45,8%/54,2% na direção do
   rompimento original, mas não sei se a árvore de desfechos difere entre
   alta e baixa.
3. **A magnitude de (c2) muda com a largura do retângulo?** Não testado; é o
   próximo corte natural depois do afastamento.
4. **Quanto do "atravessa até a oposta" (c2) seria capturável por uma ordem
   real?** Este script mede o TETO teórico (profundidade máxima), que exige
   sair exatamente no pico — não uma execução real. Território de
   executabilidade, fora do meu escopo.
