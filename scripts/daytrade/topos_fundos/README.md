# Escada WIN M15 (v4.2)

Robô de topos e fundos no WIN. Pesquisa completa (rodadas 2–16) no commit `eac5052`; estudos posteriores (saída, calendário, Supertrend) no histórico do git, nada adotado.

| arquivo | o que é |
|---|---|
| `dados.py` | períodos IS / OOS / virgem, M1 auditado → M15, contrato, ATR |
| `indicadores.py` | médias móveis (MMS, MME, inclinação), estocástico, tendência MME 9/21/34 |
| `escada.py` | pivôs ZigZag, estágio, pregões (arrays por dia) e sinais |
| `filtros.py` | filtros de entrada: H1, abertura, MMS72, sinal bom |
| `stop.py` | stop inicial (pivô + aperto MME38) e movimento (estrutura) |
| `operacao.py` | entrada limitada, gestão da posição, resultado e resumo |
| `estrategia.py` | monta a v4.2 e roda os três períodos |
| `auditoria_dados.py` | confere as bases M1 contra o calendário e a grade da B3 |

Rodar: `.venv\Scripts\python.exe scripts/daytrade/topos_fundos/estrategia.py`

Esperado (pts, 2 contratos, custo incluído):
- IS: 485 operações, +63.664, DD 6.976.
- OOS: 131 operações, +53.408, DD 5.273.
- Virgem: 25 operações, +1.957.

Em 2026-10-09 a comparação com o EA no Testador do MT5 mostrou um viés otimista no modelo: a barra que tocava o stop antes da entrada encher era contada como "ordem cancelada". Como o stop fica além do limite, o preço passa pelo limite antes, então na prática a entrada enche e sai no stop. Corrigido em `operacao.entrada_limitada`, o total caiu 24% no IS e 15% no OOS. Com a correção, o Python e o Testador (OOS, M1 OHLC) casam em 128 de 131 operações.

v4.2 = v4.1 sem o filtro MMS17×34 (2026-10-09). Esse filtro foi escolhido por um funil de 30 dias e, sem esses dias, perdia para a versão sem ele.

Um stop novo é só um par de funções `inicial(s, D)` e `mover(stop, t, p, D)` passado para `estrategia.rodar`.
