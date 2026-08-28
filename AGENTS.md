# AGENTS.md — Regras para IAs neste repositório

Este projeto é um **robô de trade B3** organizado em **arquitetura feature-first**. Toda IA (Claude, Copilot, Cursor, agentes autônomos) deve seguir estas regras ao editar código.

> **Antes de mexer em execução, dimensionamento ou método de medição, leia
> [`LICOES_DE_PRODUCAO.md`](LICOES_DE_PRODUCAO.md).** É o registro dos erros que
> já custaram dinheiro real (incluindo o incidente de 2026-08-28, que zerou a
> conta) e do invariante que sobrou de cada um. Foi escrito para sobreviver à
> troca de linguagem/plataforma — as regras de lá valem em qualquer corretora, e
> várias delas contradizem o que "parece razoável" à primeira vista.

## Camadas

Três níveis, e a direção das dependências é sempre para baixo:

| camada | quem é | pode importar |
|---|---|---|
| **orquestração** | `scheduler.py`, `live/`, `dashboard/` | qualquer feature + `core/` |
| **feature** | `market_data`, `strategy`, `backtest`, `journal` | só `core/` |
| **core** | `core/` | nada do projeto |

Orquestração é a única camada que compõe features — é literalmente o trabalho dela.
`dashboard` está aqui (não em feature) porque é fundamentalmente composição: mostra
runs (`journal`), dispara refresh (`market_data`, `scheduler`), lista robôs
(`strategy`) — nunca teve como ser uma feature isolada, e agora também compõe
`live/` para mostrar a operação real. Feature nunca importa outra feature nem a
orquestração. Se uma feature precisa de algo de outra, ou o dado sobe para
`core/` (dataclass) ou passa pelo diário.

## Regras de fronteira (invioláveis)

1. **Feature depende apenas de `core/`**. `market_data`, `strategy`, `backtest`, `journal` NÃO podem se importar entre si nem importar `scheduler`/`live`/`dashboard`. Se precisar de dado de outra feature, passe pelo `core/` (dataclass) ou pelo diário (SQLite). `dashboard` é orquestração (ver tabela acima) e pode importar qualquer feature.
2. **Estratégias vivem em `strategy/`**. A lógica de sinal deve ser **função pura** de OHLCV → decisão. Sem I/O, sem acesso a banco, sem imports de fora. Motivo: essa lógica será **portada para MQL5** — quanto mais isolada, mais fácil.
3. **O diário é o ativo mais valioso**. Sempre que uma nova feature aparecer no snapshot de entrada/saída, adicione coluna em `signal_snapshots` **e** em `live_signal_snapshots` (via migration), além do campo em `core.models.MarketSnapshot` e da tupla `journal.live_store._SNAPSHOT_COLUMNS`. As duas tabelas são espelhos em bancos diferentes (backtest × operação real) e só servem para comparar real com simulado se tiverem as MESMAS colunas — `tests/test_live_journal_rationale.py` falha se divergirem. Não descarte dado — descartar é perder capacidade de melhoria futura.
4. **Sem look-ahead**. Sinal identificado em `close[D]` → executado em `open[D+1]`. Qualquer código de backtest ou estratégia que use dado do futuro é bug crítico.
5. **Feature-first, não layer-first**. Ao adicionar funcionalidade, primeiro pergunte: "qual feature é dona disso?". Só crie coisa em `core/` se for genuinamente compartilhado.
6. **Nenhuma regra de decisão em `live/`**. O robô que opera dinheiro real é o MESMO objeto que o backtest roda — `strategy.on_bar()` e `WithdrawalPolicy.on_close()`. Se `live/` decidir qualquer coisa por conta própria (um filtro "só por segurança", um arredondamento de tamanho, um stop extra), o backtest deixa de descrever a operação e todo o histórico de validação vira ficção. `live/` cuida de relógio, dado, estado, ordem e persistência.
7. **Ao vivo, decisão atrasada não executa**. Intenção decidida no fecho de D vale no pregão D+1 e em nenhum outro: se a máquina ficou fora do ar, a intenção EXPIRA. Executar tarde é pior que não executar — cria trade que nenhum backtest reproduz. Ver `core/live_models.py`. **Isso não é o mesmo que ignorar o buraco**: o pregão que passou sem `on_bar` é REPORTADO à estratégia (`Strategy.on_missed_bars`), que decide se ainda deve algo — a família dip marca a rotação como devida e recalcula tudo com o dado do pregão de retorno. A decisão que sai daí é NOVA, não a velha executada tarde; sem esse caminho, uma máquina fora do ar no último pregão do mês cancelaria a rotação do mês inteiro. Interpretar o buraco é da estratégia, nunca de `live/` (regra 6).

## Convenções

- Python 3.11+, type hints obrigatórios em funções públicas.
- Indicadores em `core/indicators.py` são funções puras `(pd.Series, ...) -> pd.Series`. Sem estado, sem classes.
- Custos e slippage **sempre aplicados** no backtest. Nunca reportar métrica sem custo.
- Persistência do diário sempre via `journal/writer.py` — não escreva SQL de fora do módulo.
- Frontend: HTMX substitui trechos parciais, não faz full reload. Templates herdam de `base.html`.

## Estética do frontend

**Terminal Editorial** (dark mode default). Não invente outra direção sem alinhamento.

- Fontes: JetBrains Mono (dados/números), Instrument Serif (leitura/headlines).
- Cantos vivos (`border-radius: 0`). Bordas finas de 1px. Sem sombras.
- Paleta em `static/css/tokens.css` — nunca hardcode cor em template.
- Ao criar/editar template, **invoque a skill `frontend-design`** (`.claude/skills/frontend-design/SKILL.md`) para refinar.

## Testes

- Todo indicador novo em `core/indicators.py` → teste com valores conhecidos.
- Toda regra de saída/entrada em `strategy/` → teste com cenário sintético.
- Alteração no engine → teste anti-look-ahead deve permanecer verde.

### A suíte roda em PARALELO — e continua rodando

`pyproject.toml` fixa `-n auto --dist load` (pytest-xdist). Medido nesta
máquina: 92s serial → 35s em paralelo. Não é conforto: o ciclo de trabalho
aqui é "mede → decide → mede de novo", e uma suíte lenta é o gargalo do
projeto inteiro, não um detalhe de infra.

Duas condições que **todo teste novo** tem de respeitar, senão o paralelismo
quebra em falha intermitente (a pior espécie de falha):

1. **Nenhum caminho de arquivo fixo compartilhado.** `tmp_path` sempre. Dois
   workers rodam ao mesmo tempo e pegariam o mesmo arquivo.
2. **Nenhuma dependência de ordem entre testes.** `--dist load` distribui
   teste a teste entre workers; ordem de coleta não é ordem de execução.

Vale o mesmo espírito para **varredura de parâmetros**: `ProcessPoolExecutor`
com `submit`/`as_completed` (nunca `pool.map`, que só entrega na ordem de
submissão e prende resultado pronto atrás de unidade lenta), `redirect_stdout`
por unidade e `flush=True` em todo print — ver
`scripts/daytrade/sweep_gremah_tick.py`.

### Resultado sai assim que fica pronto

Regra: nenhuma rodada longa espera todas as unidades terminarem para falar.
Cada unidade que termina imprime **a linha dela** (formato da tabela padrão)
na hora, com `flush=True`; o resumo ordenado vem depois, no fim. Ver
`scripts/daytrade/sweep_copa.py`.

Motivo: uma varredura de 20 minutos que só fala no fim é uma varredura que
ninguém consegue interromper com informação — e interromper cedo, ao ver que
o espaço inteiro está negativo, é metade do valor de varrer. Quando o
resultado parcial não fizer sentido isolado (ex.: precisa de todas as
unidades para deduplicar), imprima ao menos o progresso e o melhor-até-agora.

## Saída de backtest: uma tabela só

Todo script de day trade imprime resultado por
`backtest/intraday/report.py` — `linha_de_resultado()` + `tabela()`. As 12
colunas da base (`variante`, `retorno`, `líquido R$`, `MaxDD %`, `MaxDD R$`,
`lucro/DD`, `win%`, `trades`, `R$/dia`, `trd/dia`, `capital final`,
`pregões`) são fixas e sempre nessa ordem; o que a rodada tem de específico
entra como coluna `extras`, **depois** da base, nunca no lugar dela.

Não inventar colunas próprias, não reformatar número por script: a mesma
grandeza tem de aparecer com o mesmo nome e o mesmo formato em toda tabela
do repo, senão comparar duas rodadas vira trabalho de leitura. O módulo
explica as duas decisões que fogem do óbvio (`lucro/DD` no lugar do Calmar
anualizado, e capital NOCIONAL apagando as colunas que dependem de saldo).

**Capital inicial nunca é um número digitado a mão.** Todo backtest/sweep de
ação usa `capital_minimo_brl(preco_de_referencia)` (via `config_for(...,
preco_atual=preco_ref)`) — o mínimo REAL pra operar aquele ativo naquele
preço, nunca um valor de teste arbitrário tipo "R$50.000 pra não zerar".
Motivo (2026-08-27, correção do dono): um capital genérico decide sozinho
quantos lotes cabem e se o portão de capital deixa a sessão operar —
mudar o capital pode mudar qual geometria "vence" a comparação, então usar
um número que não é o real produz uma resposta que não generaliza pra
produção. `enforce_capital_minimo` fica no default do perfil (ligado pra
ação) pelo mesmo motivo: desligar o portão mede geometria isolada do caixa,
que é outra pergunta, não a de "isto bate a produção de verdade". A tabela
de saída sempre mostra o capital inicial usado (é `capital final − líquido
R$`, ou informe a coluna direto) — nunca deixar implícito no código do
script.

## O que NÃO fazer

- Não adicionar dependência sem justificativa (peso do projeto importa).
- Não usar TA-Lib (dependência C — atrito no Windows).
- Não trocar SQLite por outro DB nesta fase.
- Não introduzir framework SPA (React/Vue). HTMX resolve.
- Não misturar múltiplas estratégias em um arquivo — uma por arquivo em `strategy/`.
