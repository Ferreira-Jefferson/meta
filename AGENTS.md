# AGENTS.md — Regras para IAs neste repositório

Este projeto é um **robô de trade B3** organizado em **arquitetura feature-first**. Toda IA (Claude, Copilot, Cursor, agentes autônomos) deve seguir estas regras ao editar código.

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

## O que NÃO fazer

- Não adicionar dependência sem justificativa (peso do projeto importa).
- Não usar TA-Lib (dependência C — atrito no Windows).
- Não trocar SQLite por outro DB nesta fase.
- Não introduzir framework SPA (React/Vue). HTMX resolve.
- Não misturar múltiplas estratégias em um arquivo — uma por arquivo em `strategy/`.
