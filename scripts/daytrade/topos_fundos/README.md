# Escada WIN M15 (v4.1)

Robô de topos e fundos no WIN. Pesquisa completa (rodadas 2–16) no commit `eac5052`; estudos posteriores (saída, calendário, Supertrend) no histórico do git, nada adotado.

| arquivo | o que é |
|---|---|
| `dados.py` | períodos IS / OOS / virgem, M1 auditado → M15, contrato, ATR |
| `indicadores.py` | médias móveis (MMS, MME, inclinação), estocástico, tendência MME 9/21/34 |
| `escada.py` | pivôs ZigZag, estágio, pregões (arrays por dia) e sinais |
| `filtros.py` | filtros de entrada: H1, abertura, MMS17×34, MMS72, sinal bom |
| `stop.py` | stop inicial (pivô + aperto MME38) e movimento (estrutura) |
| `operacao.py` | entrada limitada, gestão da posição, resultado e resumo |
| `estrategia.py` | monta a v4.1 e roda os três períodos |
| `auditoria_dados.py` | confere as bases M1 contra o calendário e a grade da B3 |

Rodar: `.venv\Scripts\python.exe scripts/daytrade/topos_fundos/estrategia.py`

Esperado (pts, 2 contratos, custo incluído):
- IS: 416 operações, +61.989, DD 5.856.
- OOS: 109 operações, +52.605, DD 4.553.
- Virgem: 23 operações, +1.582.

Em 2026-10-09 a comparação com o EA no Testador do MT5 mostrou um viés otimista no modelo: a barra que tocava o stop antes da entrada encher era contada como "ordem cancelada". Como o stop fica além do limite, o preço passa pelo limite antes, então na prática a entrada enche e sai no stop. Corrigido em `operacao.entrada_limitada`, o total caiu 24% no IS e 15% no OOS. Com a correção, o Python e o Testador (OOS, M1 OHLC) casam em 128 de 131 operações.

A v4.2 (sem o filtro MMS17×34) foi adotada e revertida em 2026-10-09: lucro praticamente igual, mas queda maior no IS (+19%) e no OOS (+16%), e 2024 negativo (−12 contra +648 da v4.1, 1 contrato, R$). Só 5 dos 30 dias do funil que escolheu o filtro eram de 2024; 80% da vantagem da v4.1 naquele ano veio de fora deles.

Um stop novo é só um par de funções `inicial(s, D)` e `mover(stop, t, p, D)` passado para `estrategia.rodar`.
