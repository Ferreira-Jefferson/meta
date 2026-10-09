# Análise rodada 2: os dias ruins da v3

Leia primeiro `INSTRUCOES_ANALISE.md`. O método é o mesmo; abaixo está o que muda.

## O que já se sabe (rodada v3, 50 dias sorteados)

- **As perguntas da v2/v3 têm viés de tendência.** Os 40 dias de onde elas vieram eram extremos do Jev v1, quase todos direcionais. Nos 50 dias sorteados não houve **nenhum** dia direcional:
  - 39 foram de rotação (eficiência direcional do dia abaixo de 0,15);
  - 11 foram intermediários;
  - a v3 perdeu −R$3.858 na rotação e ganhou +R$1.994 nos intermediários.
- **O padrão dos dias ruins:** 29 dos 30 são de rotação. Em 22 deles, a primeira entrada saiu com o Jev lendo o dia como "alta/baixa dirigida" logo cedo. Depois o dia virou rotação e veio uma série de entradas e saídas por `zerar` (175 saídas, −R$7.073).
- **Perguntas atuais (v3):** `v3/perguntas_v3.py`, com o texto em `perguntas_v3.md`. Sessões dos seus dias: `sessoes_v3/R50/M/<data>.json`. Diagnóstico de cada dia: `dias_ruins_v3.json`.

## Seu foco

Para cada dia, busque o **lucro máximo SEGURO** desse dia, e não o lucro máximo possível. "Seguro" quer dizer:

- replicável pelo motor: entrada limitada, stop sempre definido, alvo limitado;
- dentro do caixa real: R$2.000 iniciais, R$1.000 por contrato, no máximo 2 contratos;
- **sem exigir saber que o dia viraria rotação.**

Ficar de fora também é uma resposta válida. Se o melhor seguro for não operar, diga que pergunta, respondida às 9:30–10:30, mostraria isso.

Responda especialmente a estas perguntas:

1. **Rotação logo cedo.** O que, até a vela em que o Jev entrou, já indicava que o dia não era dirigido? Pense em amplitude da 1ª hora contra o ATR, sobreposição das velas, volume, posição contra a faixa de ontem, ausência de seguimento.
2. **Lucro numa rotação.** Num dia de rotação, existe forma segura de lucrar, por exemplo operar as bordas da faixa com alvo no meio ou na outra borda? Ou o certo é ficar fora? Lembre: o projeto mediu muitas reversões no WIN M15 sem vantagem estável. Proponha só o que for claramente defensável.
3. **Excesso de troca.** Que pergunta faria o Jev **não** sair e entrar de novo a cada vela?
4. **Não quebrar o que funciona.** Antes de propor uma pergunta, verifique se ela teria piorado os dias intermediários ou direcionais em que a v3 ganhou. Esses dias estão em `sessoes_v3/R50/M/` e você pode olhá-los para checar, mas não para criar perguntas.

## Entrega

Grave em `analises_r2/<seu_nome>.md`, no mesmo formato da rodada 1. Ao final, inclua a tabela consolidada com estas colunas:

- id
- tipo
- instructions
- categorias
- resposta-alvo
- decisão que sustenta
- geral ou específica
- em quantos dias apareceu
- se arrisca piorar os dias bons

Não chame a API. Não abra dias fora dos seus, dos anteriores a eles e dos 20 dias bons da v3.
