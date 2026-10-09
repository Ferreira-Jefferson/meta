# Ciclo 3 → 4: análise dos dias negativos do robo_v3

Leia `INSTRUCOES_CICLO.md` inteiro. Tudo dele continua valendo, inclusive os itens 5–7: dinheiro na mesa, hipóteses ordenadas pelo retorno e gestão adaptativa. Leia também `ciclo3/PREREGISTRO.md`, `robo_v3.py` e `ciclo3_negativos.json`. Abaixo, o que muda.

## O que mudou

1. **O robô base é o `robo_v3.py`.** O "não quebrar" é medido nos **70 dias** de `dias_usados.json` (ciclos 0 a 3).
2. **A métrica que decide é o R$/dia REPONDERADO ao calendário real**, e não a soma dos dias. O método está em `ciclo3/`. Em resumo:
   - direcional (eficiência do dia ≥ 0,25) = 3,8% dos dias;
   - não-direcional = 96,2%.

   Uma proposta só serve se melhorar o reponderado **e** não piorar o estrato não-direcional. Mostre também o efeito separado nos 20 dias do ciclo 3, os únicos sorteados ao calendário real.
3. **O que já se sabe** (não repita):
   - "Sem alvo" e o stop pela volatilidade ganham nos dias direcionais e perdem no calendário real.
   - Vetos novos quase sempre pioram o conjunto.
   - Nos dias de rotação, que são 79% dos dias, todas as versões perdem.
4. **Foco deste ciclo:** em 9 dos 12 dias negativos, nenhuma FAZER sinalizou no lado da maior perna do dia, que tem de +685 a +3.670 pts e costuma acontecer entre 09:15 e 09:45. Isso pede repertório novo de **continuação e de entrada cedo**, a favor da perna, sem precisar saber de antemão que o dia vai ser direcional.

   Teste também o caso de "FAZER nos dois lados = não entra": em 2022-12-12, essa regra perdeu +R$734.
5. **O A2 de venda liberou perdas** em 5 dias do ciclo 3, mas no total ainda é positivo. Proponha uma versão condicional dele que use só estado observável no momento da decisão.
