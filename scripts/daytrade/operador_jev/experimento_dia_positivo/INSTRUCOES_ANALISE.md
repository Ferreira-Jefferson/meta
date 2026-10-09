# Análise de dia: que perguntas fariam este dia terminar POSITIVO?

## Objetivo (do dono)

Olhe **só este dia** e descubra tudo o que um operador deveria ter olhado e considerado, a cada momento, para sair do dia com lucro. Não existe estratégia pré-definida. O único objetivo é: com estas perguntas respondidas ao longo do dia, o operador termina positivo. Se ficar de fora o dia inteiro, o resultado é zero, que não é lucro.

As perguntas serão respondidas pelo **Jev** (TypeSafe, modelo de decisão). Ele recebe o estado do mercado, em texto, e devolve uma probabilidade por resposta. Ele não vê gráfico e não explica nada.

## O que você tem

- **O pregão inteiro** (WIN M15, M1 se precisar) e os dias anteriores. Use `scripts/daytrade/operador_jev/mercado.py`: ele monta exatamente o pacote que o Jev recebe em cada vela. Leia o arquivo para ver como chamar. Use também `scripts/daytrade/topos_fundos/dados.py`.
- **O que o Jev atual fez nesse dia:** `scripts/daytrade/operador_jev/sessoes_dec/<PERIODO>/<data>.json`. Em `pontos` estão as respostas de cada vela; em `trades`, as operações. As 54 perguntas atuais estão em `perguntas_jev.py`.
- **O motor de execução:** `motor.py`. Regras: entrada só por ordem limitada (enche se o preço passar 10 pts além), stop a mercado, alvo limitado, custo de 10 pts por contrato, zera no fim do pregão.

## Como trabalhar, para cada dia

1. **Retrospectiva com o futuro à vista.** Descreva o dia:
   - o tipo de dia;
   - onde estavam as melhores entradas e saídas;
   - quanto dava para ganhar realisticamente com as regras do motor.

   Compare com o que o Jev fez e por que errou ou acertou.
2. **Momentos de decisão.** Liste os 2 a 5 momentos (vela M15) que decidiram o dia: entrar, não entrar, sair, segurar, inverter.
3. **Perguntas.** Para cada momento, escreva as perguntas que, respondidas **só com o que existia até aquela vela**, levariam à decisão certa. Regras:
   - **Nada de futuro.** A pergunta precisa ter resposta a partir do pacote de mercado daquele instante. Escreva qual informação do pacote a responde. Se faltar dado no pacote, diga qual campo precisaria ser acrescentado.
   - **Universal:** sem data, sem preço absoluto, sem "neste dia". Tem de fazer sentido em qualquer pregão.
   - **Aberta, com "não" válido:** a resposta certa pode ser não.
   - **No formato do Jev:**
     - `noul` (sim/não → P(sim));
     - `choice` com categorias descritas;
     - `score` com níveis ordenados.

     Escreva o `instructions` completo, em português, claro para quem só lê texto.
   - **Diga a resposta que levaria à decisão certa naquele momento** e qual decisão ela sustenta: entrar comprando, entrar vendendo, ficar fora, segurar, sair, apertar o stop.
4. **Teste de sanidade.** Antes de propor, pergunte-se: essa pergunta também ajudaria (ou ao menos não atrapalharia) nos outros dias que você analisou, inclusive nos dias bons do Jev? Pergunta que só serve a um dia é ajuste ao dia. Marque assim:
   - **"geral"** se você vê que ela valeria em vários dias;
   - **"específica"** se não.

## Lições do projeto que você deve respeitar

São medidas, não opinião:

- **O WIN M15 é de continuação, não de reversão.** RSI ≤ 30 continua caindo. O Jev atual compra a queda e vende a alta, e esse é o principal erro dele.
- **A escada v4.1, a estratégia que funciona, ganha deixando correr.** Os 10% melhores trades fazem 174% do lucro. Ela entra a favor do H1 e do lado da abertura.
- **Depois das 15h os sinais são piores.**
- **Pergunta sobre a vela isolada** (padrão de vela, figura, Fibonacci) não separou nada em nenhum teste.

## Entrega

Grave em `scripts/daytrade/operador_jev/experimento_dia_positivo/analises/<seu_nome>.md`:

- uma seção por dia, com retrospectiva, momentos e perguntas (no formato acima);
- ao final, uma tabela consolidada das suas perguntas com: id, tipo, instructions, categorias/níveis, resposta-alvo, decisão que sustenta, geral/específica e em quantos dos seus dias ela apareceu.

Não chame a API do Jev nesta fase. Não altere nenhum outro arquivo.
