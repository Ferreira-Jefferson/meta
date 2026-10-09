# Escada WIN M15 (v4.1)

Robô de topos e fundos no WIN. Pesquisa completa (rodadas 2–16) no commit `eac5052`.

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
- IS: 387 operações, +76.768, DD 5.545.
- OOS: 98 operações, +59.537, DD 3.623.
- Virgem: 21 operações, +2.443.

Um stop novo é só um par de funções `inicial(s, D)` e `mover(stop, t, p, D)` passado para `estrategia.rodar`.
