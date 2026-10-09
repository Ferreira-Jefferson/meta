# Operador Jev (LLM) no WIN

Duas maneiras de ligar o Jev (TypeSafe) ao motor de execucao deterministico, escolhidas por `--motor`:

| `--motor` | endpoint | o que e |
|---|---|---|
| `decisoes` (**padrao**) | `POST https://openrouter.ai/api/alpha/decisions` | o Jev de verdade (modelo de decisoes, "System One"): estado + perguntas -> probabilidades. ~US$ 0,0003 por chamada, 0,8 s |
| `chat` | `/api/v1/chat/completions` (`typesafe/jev-router`) | o antigo. NAO e o Jev: e um roteador que repassa para outras LLMs (deepseek, sonnet, gemini...). ~1.000x mais caro, nao reprodutivel |

## Uso
```
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\operador_jev.py --periodo OOS --limiar 0.3 --paralelo-dias 6        # OOS inteiro (252 dias)
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\operador_jev.py --periodo IS --amostra 120 --seed 20261009 --limiar 0.3
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\operador_jev.py --datas 2026-03-10,2026-05-12 --saida sessoes_dec\teste
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\avaliar.py --pasta sessoes_dec\OOS --pasta sessoes_dec\IS --sorteios 300
.\.venv\Scripts\python.exe scripts\daytrade\operador_jev\gera_viewer.py --sessoes sessoes_dec\OOS --max-dias 60
.\.venv\Scripts\python.exe -m pytest scripts/daytrade/operador_jev
```
Opcoes do modo decisoes: `--limiar` (P minima da acao escolhida; padrao 0,5), `--modo-entrada argmax|lado`, `--modelo` (padrao a versao fixa
`typesafe/jev-1.13-20260917`), `--paralelo-dias`, `--paralelo-velas` (chamadas de mercado simultaneas por dia), `--paralelo-chamadas` (teto global),
`--amostra N --seed S`, `--refazer`, `--max-custo-usd`. Dias ja gravados sem falha de API sao pulados (retomada). Viewer: setas = vela a vela, espaco = play.

## O que se descobriu da API de decisoes (investigado com chamadas pequenas, 2026-10-09)
- **Corpo**: `{"model", "state", "questions": {id: {"type": "noul"|"choice"|"score", "instructions": str, "criteria": ...}}}`. Chave em `Authorization: Bearer`.
- **`noul` = probabilidade de "sim"** em [0,1] (pergunta falsa -> 0,06; "o estado nao traz a informacao" -> 0,2 a 0,5, perto do indefinido; nao ha campo "unknown").
  `criteria` do noul, se passado, tem de ser objeto com as chaves `true`/`false` (cada uma string, objeto ou array); nao e necessario.
- **`choice`**: `criteria` e objeto `{categoria: descricao}` (obrigatorio, minimo 1). Devolve `choice`, `probabilities` (somam 1) e `confidence`.
- **`score`**: `criteria` e **array** de rotulos ordenados = niveis 0..n-1. Devolve `score` = valor esperado do nivel (2 rotulos -> 0..1; 5 rotulos -> 0..4), `legend`, `probabilities` por nivel, `confidence`.
- **`state`**: aceita texto, objeto (record) ou array. Texto e mais barato: JSON estruturado custa ~1,2 token/char contra ~1 do texto compacto (25 KB de JSON = 21 mil tokens). Usamos **texto** (o mesmo pacote de mercado do modo chat).
- **Limites**: `questions` aguenta pelo menos 400 perguntas por chamada (testado; custo cresce ~linear: ~20 tokens de saida por pergunta). `state` rejeita com `{"detail":{"error_type":"max_tokens_exceeded"}}` perto de **32 mil tokens** de entrada (OK com 31 mil, falha com 47 mil). Nosso estado tem ~2,5 mil tokens + 54 perguntas = ~7,5 mil tokens de entrada e ~1,5 mil de saida.
- **Versao fixa**: `"model":"typesafe/jev-1.13-20260917"` funciona e a resposta confirma a mesma versao; `~typesafe/jev-latest` resolve hoje para ela. Nomes inexistentes (`typesafe/jev`, `jev-1.12`) -> 400 "Model ... does not exist". **Padrao do operador = versao fixa** (reprodutibilidade).
- **Determinismo**: quase, nao total. 5 chamadas identicas: mesmos tokens de entrada/saida e mesmas escolhas, mas as probabilidades variam em media 0,012 (maximo 0,03) por pergunta (ex.: P(fora) 0,44-0,49). Ou seja: ruido de ~+-0,03 em qualquer limiar; nao ha `seed`/`temperature` (ignorados).
- **Campos extras** (`system`, `context`, `instructions` global, `temperature`, `seed`, qualquer outro) sao **ignorados em silencio** (validacao so reclama de `model`, `state` e `questions`). Todo o contexto tem de ir em `state` e nas `instructions` de cada pergunta.
- **Latencia**: 0,6-0,9 s por chamada (mesmo com 400 perguntas). **Custo** real: US$ 0,000316 por chamada de mercado de 54 perguntas (7,5 mil tokens). Sem 429 com 16 requisicoes simultaneas em 16.600 chamadas.
- **Sensibilidade ao enunciado (importante)**: a frase "Ficar de fora e uma resposta valida" na pergunta `acao` moveu a P(fora) media de 0,43 para 0,66 e a escolha `fora` de 78% para 100% das velas (20 dias de jan/26, mesmas velas): com a frase o Jev nunca operou. O enunciado, nao so o mercado, decide quanto o Jev opera. O padrao atual nao tem a frase.

## Arquivos
- `operador_jev.py` CLI: roda dias (paralelo entre dias), grava `sessoes_dec/<periodo>/<data>.json`, `_custo.json`.
- `perguntas_jev.py` perguntas de `PERGUNTAS_DE_OPERACAO.md` no formato da API. Ids estaveis `b<bloco>_q<numero no arquivo>` (bloco 0 = "Antes de aceitar qualquer conclusao"), `d<n>_c/_v` (D1..D13 para uma COMPRA/uma VENDA), `s2`, `a1`, `stop`, `alvo`, `mao`, `acao`; gestao: `b11_q81..83`, `g_acao`. Todas abertas, sem gabarito de estrategia; "nao" e resposta valida. 54 perguntas de mercado + 4 de gestao.
- `jev_api.py` cliente (retry com backoff exponencial + jitter em 429/5xx/rede, teto de requisicoes simultaneas, custo acumulado) e `parse_resposta` (pura).
- `decisoes.py` conversao resposta -> ordem do motor (pura, sem rede), pivos, trailing, re-simulacao offline.
- `operador_decisoes.py` roda um dia: chamadas de mercado de todas as velas em paralelo (nao dependem da posicao), simulacao sequencial.
- `avaliar.py` painel padrao, por trimestre, nulos, re-limiar offline, diagnostico e calibracao.
- `mercado.py` dados e pacote textual (so velas fechadas, sem data real); `motor.py` execucao; `llm.py` cliente do modo chat; `gera_viewer.py` + `viewer_template.html`.
- `test_motor.py`, `test_decisoes.py` (parser com resposta gravada, perguntas bem formadas, conversao, pivo sem look-ahead, trailing so a favor).

## Como o modo decisoes decide
Por vela M15 fechada (09:15-17:30):
1. **Chamada de mercado** (sempre): estado so de mercado (sem posicao/ordens/resultado do dia, logo as respostas nao dependem da trajetoria) + as 54 perguntas.
2. **Chamada de gestao** (so com posicao aberta): estado + linha POSICAO + `b11_q81..83` e `g_acao` {manter, stop_pivo, zerar}.
3. **Sem posicao e sem ordem**: entra se `acao` = comprar/vender e **P(escolha) >= limiar**. Ordem LIMITADA no ultimo fechamento (arredondado para o lado passivo), validade 3 velas, enche se passar 10 pts alem (motor). Stop: `0.5atr|1atr|1.5atr` do ATR M15 ou `pivo` (ultimo fundo/topo confirmado a 0,3-4 ATR da entrada, 1 tick alem; senao 1,5 ATR). Alvo: `1/2/3 ATR` limitado, ou `sem_alvo` = deixar correr com stop movel na minima/maxima das ultimas 8 velas (so a favor). Mao: 1 ou 2. Com ordem pendente aguarda (nova decisao so depois de expirar/encher).
4. **Com posicao**: `zerar` sai a mercado; `stop_pivo` leva o stop ao ultimo pivo formado desde a entrada (so a favor, abaixo/acima do ultimo fechamento); trailing do "deixar correr" roda sempre (mesmo se a chamada falhar).
5. Falha de API (apos 8 tentativas) = ficar de fora; o dia e re-executado na proxima retomada.
Motor (inalterado): entrada/alvo sempre limitados, so stop e zerar a mercado, sem look-ahead (decisao no fechamento da vela k age a partir da k+1), custo 10 pts/contrato.

## Custo real (2026-10-09)
OOS inteiro (252 dias, 11.216 chamadas) US$ 3,17 em 13 min; IS (120 dias sorteados, seed 20261009, 5.420 chamadas) US$ 1,52 em 10 min; conferencia 40 dias US$ 0,48; testes e investigacao ~US$ 0,45. **Total ~US$ 5,6**, 0 falhas, 0 rate limit (16 requisicoes simultaneas).

## Log e viewer
`sessoes_dec/<periodo>/<data>.json`: por vela `jev.m` (todas as respostas compactas: noul = P(sim); choice = {c, p, k}; score = {s, p, k}), `jev.g` (gestao), `jev.info` (escolhas, P, stop/alvo/mao convertidos), modelo, custo, latencia, tokens; mais velas, ordens, trades, eventos e um `estado_exemplo`. Como as probabilidades ficam gravadas, o limiar pode ser mudado sem refazer chamadas (`avaliar.py`, re-limiar).
`viewer.html` (autocontido): no painel da vela mostra a decisao (acao/stop/alvo/mao com barras), a gestao e todas as perguntas com barras (verde = sim, vermelho = nao; categorias coloridas), confianca, modelo/custo/latencia, e o painel do periodo + re-limiar.

## Limitacoes
- **Re-limiar offline e aproximado**: as entradas sao exatas (a resposta de mercado da vela nao depende da posicao), mas a gestao so existe nas velas em que a posicao ORIGINAL estava aberta; numa trajetoria nova vale "manter" + trailing. A re-simulacao no proprio limiar da execucao reproduz o resultado exato (conferencia no `avaliar.py`).
- Conferencia empirica (40 dias de OOS, limiar 0,4): rodada ao vivo = 61 ops, R$ -939; re-simulacao das respostas da rodada principal nos mesmos dias = 75 ops, R$ -1.485. A diferenca e o ruido da API (+-0,03 perto do limiar) mais a aproximacao da gestao; re-simular as respostas da PROPRIA rodada reproduz exatamente (61 ops, R$ -939). Leia o re-limiar como ordem de grandeza, nao como previsao.
- Limiar acima de ~0,5 quase nao opera: com 3 categorias a P da escolha raramente passa de 0,45 (OOS: 17 ops a 0,5, nenhuma a 0,6+). Por isso as execucoes reais foram feitas a 0,3 (argmax com piso) e os limiares maiores vem do re-limiar.
- Ruido de +-0,03 nas probabilidades entre chamadas iguais; o resultado de um dia nao e reproduzivel ao centavo.
- Datas sao anonimizadas, mas precos reais podem denunciar a data a um modelo que decorou o mercado.
- Nulo aleatorio: usa a geometria (stop, alvo, mao, trailing) de cada ordem preenchida do Jev, mas nao reproduz as movimentacoes de stop por pivo da gestao.
- Perguntas de contexto exterior (dolar, indice americano, noticias) nao tem dado no estado e ficam perto de 0,2-0,5.
- Modo chat (legado): router escolhe o modelo por chamada; cada dia comeca so com o contexto de mercado; ordem nova com posicao aberta e rejeitada; nulo 2 com validade 2 velas.
