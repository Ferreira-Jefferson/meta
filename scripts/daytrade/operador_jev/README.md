# Operador Jev (LLM) no WIN

A LLM (`typesafe/jev-router` no OpenRouter) olha o WIN vela M15 a vela, responde as perguntas de `PERGUNTAS_DE_OPERACAO.md`
(vai inteiro no prompt de sistema, identico entre chamadas) e decide sozinha; um motor Python deterministico executa.

## Arquivos
- `operador_jev.py` CLI: roda dias (em paralelo entre dias, sequencial dentro do dia), imprime tabela e nulos, grava `sessoes/<data>.json` e `sessoes/_resumo.json`.
- `mercado.py` dados (M15+M1 de todos os periodos) e o pacote de mercado textual (sem data real, so velas fechadas).
- `motor.py` execucao: limite so enche passando 10 pts, stop a mercado (gap sai na abertura), alvo limitado, stop vence empate, custo 10 pts/contrato, zera 5 min antes do fim.
- `llm.py` cliente OpenRouter (json_schema -> json_object -> texto; retry com backoff; 2 tentativas de JSON; falha = ficar fora). Chave so de `.env`, nunca impressa.
- `gera_viewer.py` + `viewer_template.html` geram `viewer.html` (autocontido, abre com duplo clique).
- `test_motor.py` testes do motor com operador falso (inclui teste de look-ahead do pacote).

## Uso
```
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\operador_jev.py --inicio 2026-03-10 --dias 2 --periodo OOS [--modelo typesafe/jev-router] [--paralelo-dias 3] [--max-custo-usd 5]
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\operador_jev.py --datas 2026-09-02,2026-08-27
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\gera_viewer.py
.\.venv\Scripts\python.exe -m pytest scripts/daytrade/operador_jev/test_motor.py
```
Viewer: setas esquerda/direita avancam/voltam uma vela, espaco = play/pause.

## Decisoes de desenho / limitacoes
- O router escolhe o modelo por chamada (visto: deepseek, gemini, claude-sonnet, gpt, kimi). Isso torna o operador NAO reprodutivel e mistura "operadores" diferentes no mesmo dia; para comparar, fixe `--modelo` (ex.: `anthropic/claude-sonnet-5.5`). O modelo de cada decisao fica no log e no viewer.
- Cada dia comeca so com o contexto de mercado (sem memoria de outros dias); o "acumulado" mostrado ao operador e o do proprio dia.
- Ordem nova com posicao aberta e rejeitada; nova ordem com outra pendente a substitui. Compra limite acima do ultimo fechamento (ou venda abaixo) e rejeitada (seria ordem a mercado).
- No M1 do preenchimento so o stop conta (alvo nao). Datas sao anonimizadas, mas precos reais podem denunciar a data a um modelo que decorou o mercado.
- Nulo 2 (aleatorio): limite no ultimo fechamento, validade 2 velas, mesmas distancias de stop/alvo e contratos de cada trade do Jev, mesmo motor. Com poucos dias/trades nao diz nada.
- `--max-custo-usd` aborta (ficar fora no resto do dia) ao passar do teto.
