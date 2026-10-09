# Ciclo — análise de um dia em que o ROBÔ fechou negativo

Leia antes `CICLO.md`, `INSTRUCOES.md` (as regras das regras continuam valendo), `base.py`, `robo.py` e o log do robô no seu dia.

## Seu dia

O robô, que junta todas as regras FAZER e NAO_FAZER de `regras/`, fechou este pregão no negativo. Responda:

1. **O que nas regras levou ao prejuízo?**
   - Qual FAZER entrou e por quê.
   - Qual veto deveria ter agido e não agiu, ou agiu errado e bloqueou o que ganharia.
   - Se a saída (stop, alvo, gestão) foi o problema.

   Mostre a vela, o sinal e o número.
2. **5 maneiras de ter deixado ESTE dia positivo**, em código, no mesmo formato de `INSTRUCOES.md`. Podem ser de dois tipos:
   - **regra nova** de FAZER;
   - **ajuste numa regra existente:** uma condição a mais, outro stop ou alvo, uma janela de horário.

   Cada uma deve dar R$ > 0 no dia, conferido com o simulador.
3. **5 coisas a NÃO fazer neste dia**, em código, como NAO_FAZER. Cada uma descreve uma condição de mercado que vira veto, e dá R$ < 0 no dia.
4. **Não quebrar o que funcionava.** Para cada regra nova ou ajuste, rode o robô com a mudança em TODOS os dias de `dias_usados.json` e mostre:
   - o total antes e depois em cada dia;
   - quantos dias pioraram.

   Mudança que melhora o seu dia e piora o conjunto **não serve**. Marque-a como "ajustada ao dia" e não a proponha para o robô.

## Sempre (dono, 2026-10-09)
5. **Dinheiro na mesa:** qual era o MAIOR movimento aproveitável do dia (pts e R$ com as regras de execução) e POR QUE o robô não pegou — veto (qual), teto de ops, conflito de lados, regra ausente, saída cedo. Quando uma entrada bloqueada ganharia muito, pergunte sempre "por que não entrou e o que teria de fazer?".
6. **Hipóteses diferentes, ordenadas pelo retorno:** busque a de MAIOR retorno possível (segura e replicável), sem descartar as menores.
7. **Gestão adaptativa:** stop, alvo (ter ou não), trailing e quando mover devem poder variar com o estado observado (regime do dia, volatilidade, força da perna, hora), em vez de parâmetros fixos. Proponha mapeamentos estado→decisão e meça contra a versão fixa.

## Entrega

- **`regras/c<N>_<AAAA_MM_DD>.py`**: as novas FAZER e NAO_FAZER, e os ajustes propostos como novas versões das funções. **Não edite** os arquivos `r_*.py` existentes.
- **`analises/c<N>_<AAAA_MM_DD>.md`**, com:
  - a causa do prejuízo;
  - a tabela das 10 propostas, com: nome, fazer/não fazer, natureza, R$ no dia, efeito no conjunto de dias usados (melhora / piora / neutro), geral ou ajustada;
  - a sua recomendação do que entra no robô.

Não rode dias fora de `dias_usados.json`.
