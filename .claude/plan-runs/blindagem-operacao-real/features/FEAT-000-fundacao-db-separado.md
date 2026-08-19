# FEAT-000 — fundacao-db-separado

> Plano de ação escrito pelo feature-agent, revisado (e corrigido quando necessário) pelo plan-reviewer.
> Status: `rascunho` → `em revisão` → `aprovado` → `executado` → `concluído`

**Status:** **executado — 261 testes verdes, PRE-GATE verde, aguardando code-review (rodada 2 de correção, tentativa 1/2)** (decisão do usuário aplicada, opção A, ver 6c)

> **Resolução da escalação 6b (usuário, via orquestrador):** opção **A** — a guarda do
> `LiveRuntime` por "broker test-double" (metade do item 0.3) sai do escopo de FEAT-000 e
> passa a ser requisito explícito de FEAT-001 (que já reescreve `live_service.py`/`run_live.py`
> e é onde `PaperBroker` efetivamente sai de produção — 1.2/1.4). FEAT-000 mantém a outra
> metade do passo 5 (o rename `DB_PATH`→`LIVE_DB_PATH` em `runtime.py`, que P3 já provava e
> não dependia da decisão) e passos 1-4, 6-8, sem alteração. Ver seção 6c.

**Run:** `blindagem-operacao-real` | **Plano original:** `C:\Users\Jeffe\.claude\plans\crie-um-plano-p-ra-gentle-papert.md` (seção "Lote 0 — Fundação", subitens 0.2 e 0.3 — 0.1 é NO-OP já confirmado no EXEC-MAP)
**Tier:** T3 | **Wave:** 1 | **Isolamento:** worktree `../meta-FEAT-000`
**Branch:** `feat/blindagem-operacao-real-FEAT-000`

## 1. Problema / objetivo

Hoje `db/journal.sqlite` guarda, no mesmo arquivo, o diário de backtest (`runs`/`trades`/`equity_curve`) e a operação real (`live_*`), e um backtest longo rodando em `threading.Thread` dentro do processo que serve `/operacao` pode disputar lock de arquivo com a gravação de uma ordem real. Esta feature separa fisicamente as duas coisas (`db/live.sqlite` dedicado às tabelas `live_*`), migra o dado existente sem apagar o original, e fecha o buraco do simulador acelerado (`scripts/run_live_sim.py`) que hoje só não escreve no banco real porque alguém lembrou de passar `db_path=SIM_DB`, sem nenhuma guarda de código.

**Estado atual (regra 6):** nada disto existe hoje.
- `core/config.py:9` só tem `DB_PATH = ROOT/"db"/"journal.sqlite"` — não existe `LIVE_DB_PATH`.
- `journal/live_store.py:131-141` (`_connect`/`live_journal`) usa `DB_PATH` como default e não liga `WAL`/`busy_timeout`.
- `live/runtime.py:160` cai no mesmo `DB_PATH` (backtest) quando `db_path=None`, e não há nenhuma guarda contra um feed de teste/simulação apontando para o banco de produção.
- `scripts/run_live_sim.py:90-92` apaga `SIM_DB` sem checar se ela é, por acidente, o banco real.
- Não existe `scripts/migrate_live_db.py`.
Delta desta feature: os cinco pontos acima.

## 2. Arquivos

**Escreve** (cria/edita):
- `src/core/config.py` — adiciona `LIVE_DB_PATH = ROOT / "db" / "live.sqlite"`.
- `src/journal/live_store.py` — `_connect`/`live_journal` passam a usar `LIVE_DB_PATH` como default; liga `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout`; corrige a docstring que hoje afirma que backtest e operação real "compartilham o arquivo .sqlite" (deixa de ser verdade).
- `src/journal/schema.sql` — só comentário: documenta que as tabelas `live_*` definidas aqui agora vivem fisicamente em `db/live.sqlite` (`core.config.LIVE_DB_PATH`), extraídas por `_live_ddl`; nenhuma mudança de DDL.
- `src/live/runtime.py` — troca o import `DB_PATH` por `LIVE_DB_PATH as DB_PATH` (mantém o NOME do atributo — ver premissa 4 — mas o valor passa a ser o banco separado). **Nenhuma guarda por tipo de broker/feed nesta feature** — ver 6c: a guarda "recusa `db_path=LIVE_DB_PATH` com broker test-double" (item 0.3) foi movida para FEAT-001 por decisão do usuário.
- `scripts/run_live_sim.py` — importa `ROOT`, `DB_PATH` e `LIVE_DB_PATH`; torna `SIM_DB` **absoluto** (`ROOT / "db" / "live_sim.sqlite"` — hoje é `Path("db/live_sim.sqlite")`, relativo ao cwd, então `python scripts/run_live_sim.py` rodado de outro diretório cria e apaga um `db/` em lugar errado); extrai a guarda para uma função de módulo **importável e testável** `_ensure_disposable_sim_db(path)` que levanta `SystemExit` se `path.resolve()` for igual a `LIVE_DB_PATH.resolve()` **ou** a `DB_PATH.resolve()`, chamada no início de `main()` antes de qualquer leitura/escrita. **Não usar `assert`** (é removido sob `python -O`, e uma salvaguarda contra `.unlink()` do banco real não pode evaporar por flag de interpretador).
- `scripts/migrate_live_db.py` (**novo**) — `migrate(source=DB_PATH, dest=LIVE_DB_PATH) -> dict[str, int]`: copia as linhas das tabelas `live_*` de `source` para `dest`, nunca escreve em `source`, devolve `{tabela: linhas_inseridas}`. CLI fina por cima (`--source`/`--dest`, imprime o dict). Detalhes obrigatórios de implementação em 3.4.
- `tests/test_live_store.py` — 2 asserções novas: (a) `_connect` liga `journal_mode=WAL` e `busy_timeout`; (b) **o default de `_connect` e de `live_journal` é `LIVE_DB_PATH`** (ver 4 — é o coração da feature e o plano original não tinha prova nenhuma disso).
- `tests/test_live_runtime.py` — 1 teste novo: `LiveRuntime(db_path=None).db_path == LIVE_DB_PATH` e `live.runtime.DB_PATH is core.config.LIVE_DB_PATH` (P3). Testes de guarda por broker test-double **não** entram aqui — são escopo de FEAT-001 (ver 6c).
- `tests/test_migrate_live_db.py` (**novo**) — migração idempotente, não-destrutiva, com integridade referencial no destino; e a guarda de `scripts/run_live_sim.py` (mesmo arquivo por serem as duas salvaguardas de `scripts/` desta feature — evita criar um 4º arquivo de teste).

**Só lê:**
- `src/live/broker.py` — confirmar `PaperBroker`/`ManualBroker`/`mode` antes de decidir o critério da guarda.
- `src/live/feed.py` — confirmar que `ReplayFeed` é o único dublê de teste (docstring: "dirigido a mão, para teste e simulação determinística").
- `src/dashboard/live_service.py`, `scripts/run_live.py` — confirmar que nenhum dos dois constrói `ReplayFeed` em produção (só `ParquetCloseFeed`/`YFinanceFeed`), para a guarda não quebrar o caminho real.
- `tests/test_dashboard_app.py` — confirmar a convenção `monkeypatch.setattr(live_runtime, "DB_PATH", tmp)` que preciso preservar (arquivo de outra feature, não devo editá-lo).

**Consome de outras features:** nada — FEAT-000 é a primeira da cadeia.
**Produz para outras features:** `core.config.LIVE_DB_PATH`; `journal.live_store`/`live.runtime` apontando por padrão para o banco separado; `scripts/migrate_live_db.py`. FEAT-001 consome o caminho e o nome da função de migração.

## 2b. Premissas a montante (regra 17)

| # | Premissa | Como verificar | Origem |
|---|----------|----------------|--------|
| 1 | `LiveRuntime.__init__` lê `DB_PATH` como nome GLOBAL do módulo (lookup dinâmico a cada instância, não default de parâmetro fixado em tempo de definição) | `src/live/runtime.py:160`; docstring de `tests/test_dashboard_app.py:22-26` | código existente |
| 2 | `ReplayFeed` só é construído em `tests/` e em `scripts/run_live_sim.py` — nunca em `dashboard/live_service.py` nem em `scripts/run_live.py` (que só usam `ParquetCloseFeed`/`YFinanceFeed`) | `grep -rn "ReplayFeed" src/ scripts/ tests/` | código existente |
| 3 | `ensure_tables`/`_live_ddl` já filtram o DDL por `CREATE ... LIVE_`, então extrair só as tabelas `live_*` de `schema.sql` continua funcionando sem dividir o arquivo | `src/journal/live_store.py:88-117` | código existente |
| 4 | `tests/test_dashboard_app.py` faz `monkeypatch.setattr(live_runtime, "DB_PATH", tmp)` — o atributo precisa continuar se chamando `DB_PATH` em `live.runtime`, mesmo que o valor passe a vir de `LIVE_DB_PATH` | `tests/test_dashboard_app.py:46` | código existente, fora do escopo desta feature — não pode quebrar |
| 5 | **VERIFICADO pelo plan-reviewer:** `PaperBroker` **está** no caminho de produção em 2 pontos — `scripts/run_live.py:170` (com `--mode` default `"paper"`, linha 312) e `src/dashboard/live_service.py:51` (usado até para LER `/operacao`). Nenhum dos dois passa `db_path`, logo ambos herdam o novo default `LIVE_DB_PATH` | `grep -rn "PaperBroker" src/ scripts/` | é a premissa que gera a escalação 6b |
| 6 | **VERIFICADO:** os 4 chamadores de `live_journal()` **sem argumento** (`dashboard/app.py:370,433,699` e `live_service.py:30`) seguem o novo default automaticamente — nenhum deles passa `DB_PATH` explícito, então não sobra caminho lendo o banco antigo por acidente | `grep -rn "live_journal(" src/` | confirma que o passo 2 é wire-up suficiente |
| 7 | **VERIFICADO:** suíte verde antes da feature — `249 passed in 7.13s` (`.venv/Scripts/python.exe -m pytest -q` em `meta/`, 2026-08-18). Nenhuma falha pré-existente para confundir com regressão | execução direta | baseline da prova |

## 3. Passos

> **RED antes de GREEN (T3):** os testes dos passos 2, 4, 5 e 6 são escritos e rodados ANTES da
> implementação correspondente, e têm de falhar com o código atual (`LIVE_DB_PATH` não existe,
> `migrate()` não existe, guarda não existe). Colar a saída RED na seção 7.

| # | Ação | Arquivo(s) | Como sei que funcionou |
|---|------|-----------|------------------------|
| 1 | Adicionar `LIVE_DB_PATH = ROOT / "db" / "live.sqlite"` com comentário do porquê (disputa de lock entre backtest em `threading.Thread` e gravação de ordem real) | `src/core/config.py` | `python -c "from core.config import LIVE_DB_PATH; print(LIVE_DB_PATH.name)"` → `live.sqlite` |
| 2 | Trocar import/defaults de `_connect(db_path=...)` e `live_journal(db_path=...)` de `DB_PATH` para `LIVE_DB_PATH`; ligar `PRAGMA journal_mode=WAL` (ler o resultado — esse PRAGMA devolve linha) e `PRAGMA busy_timeout=5000` em `_connect`, **depois** de `sqlite3.connect` e **antes** de `ensure_tables`; corrigir a docstring do módulo (linhas 27-34) que hoje afirma que backtest e operação real "só compartilham o arquivo `.sqlite`" | `src/journal/live_store.py` | testes novos `test_connect_liga_wal_e_busy_timeout` e `test_default_do_diario_ao_vivo_e_live_db_path` passam |
| 3 | Comentário em `schema.sql` documentando a separação física (sem tocar DDL) | `src/journal/schema.sql` | `git diff` mostra só linhas iniciadas por `--`; `tests/test_live_store.py` inteiro continua verde (o filtro de `_live_ddl` remove linhas `--` antes do split — premissa 3) |
| 4 | Criar `scripts/migrate_live_db.py` conforme 3.4 (abaixo) | `scripts/migrate_live_db.py` (novo) | `tests/test_migrate_live_db.py` passa (copia, é idempotente, origem intacta byte a byte, `PRAGMA foreign_key_check` vazio no destino, origem sem tabelas `live_*` não quebra) |
| 5 | Em `runtime.py`: importar `LIVE_DB_PATH as DB_PATH` no lugar de `DB_PATH` (com comentário explicando por que o nome do módulo permanece `DB_PATH` — premissa 4). **Sem guarda de tipo de broker/feed** — movida para FEAT-001 (decisão do usuário, 6c) | `src/live/runtime.py` | teste `tests/test_live_runtime.py` passa: `LiveRuntime(db_path=None).db_path == LIVE_DB_PATH` e `live.runtime.DB_PATH is core.config.LIVE_DB_PATH` (P3) — suíte inteira segue verde |
| 6 | Em `run_live_sim.py`: tornar `SIM_DB` absoluto (`ROOT / "db" / "live_sim.sqlite"`); criar `_ensure_disposable_sim_db(path)` que levanta `SystemExit` se `path.resolve()` coincidir com `LIVE_DB_PATH.resolve()` ou `DB_PATH.resolve()`; chamá-la na 1ª linha de `main()`, antes do bloco `if SIM_DB.exists()`. Sem `assert` (some sob `python -O`) | `scripts/run_live_sim.py` | teste novo `test_run_live_sim_recusa_apagar_banco_real` passa: chamar `_ensure_disposable_sim_db(LIVE_DB_PATH)` e `(DB_PATH)` levanta `SystemExit`; chamar com `SIM_DB` não levanta |
| 7 | Rodar a **suíte inteira** (não só os 3 arquivos da feature): a troca de default e a guarda podem quebrar `tests/test_dashboard_app.py`, `tests/test_live_broker.py` e `tests/test_live_feed.py`, que nenhum comando restrito a 3 arquivos veria | — | `../meta/.venv/Scripts/python.exe -m pytest -q` → exit 0, **≥ 249 testes** (baseline medido pelo plan-reviewer em 2026-08-18: `249 passed in 7.13s`; a suíte inteira leva ~7s, não há economia real em rodar só 3 arquivos) |
| 8 | Registrar na seção 7 a **consequência operacional**: depois deste merge, `/operacao` e `scripts/run_live.py status` passam a ler `db/live.sqlite`, que nasce VAZIO. A conta real `principal` continua só em `db/journal.sqlite` até alguém rodar `python scripts/migrate_live_db.py` na máquina. Isso é ação humana (fora do teste automatizado), mas tem de aparecer no relatório de execução e no commit — senão o usuário abre o painel e vê "conta não existe" sem entender por quê | — | linha presente na seção 7 e na mensagem do commit |

> Ordem executável: 1 → 2 → 3 → 4 → 5 (consome `LIVE_DB_PATH` do passo 1) → 6 (consome `LIVE_DB_PATH` e `DB_PATH` do passo 1) → 7 → 8. Sem bloqueio — decisão 6c já aplicada.

### 3.4 `scripts/migrate_live_db.py` — requisitos que a implementação não pode ignorar

O plano original dizia só "`ATTACH` + `INSERT OR IGNORE`", o que **não roda** contra o banco real.
Obrigatório:

1. **Criar o schema no destino antes de copiar** — `journal.live_store.ensure_tables()` (ou `_connect(dest)`) sobre `dest`; sem isso o `INSERT` bate em "no such table".
2. **Copiar preservando as chaves originais** (`INSERT OR IGNORE INTO dest.<t> SELECT * FROM <t>`, sem listar colunas e sem deixar o AUTOINCREMENT do destino reatribuir `id`). É isso — e só isso — que torna a 2ª rodada um no-op e mantém as FKs válidas.
3. **Respeitar a ordem de FK** (o `_connect` do store liga `PRAGMA foreign_keys = ON`; fora de ordem, o `INSERT` do filho falha): `live_accounts` → `live_intents` → `live_orders` → `live_fills` → `live_positions`, `live_equity`, `live_withdrawals`, `live_deposits`, `live_events`.
4. **`ATTACH` não pode rodar dentro de transação aberta** — abrir a conexão sobre `dest`, `ATTACH` a `source` como somente-leitura (`file:...?mode=ro` com `uri=True`) e só então iniciar a transação. O modo `ro` é a garantia mecânica de "nunca escreve em `source`", não só disciplina.
5. **Origem sem tabelas `live_*`** (instalação nova) → devolve `{}` e sai com código 0, sem exceção. Descobrir as tabelas presentes via `sqlite_master` e intersectar com a lista ordenada do item 3, em vez de assumir que todas existem.
6. **Reversibilidade:** a migração nunca toca `source`; desfazer é apagar `db/live.sqlite`. Registrar isso na docstring do script.
7. Se a prova falhar (linha duplicada na 2ª rodada, `foreign_key_check` não-vazio), **não** relaxar a asserção: o defeito é da ordem/colunas do `INSERT`.

## 4. Prova de conclusão (uma só)

**Origem:** ⬜ comando/teste que já existe ☑ **comando que já existe (`pytest -q`, a suíte do projeto) carregado com asserções novas** — 2 em `tests/test_live_store.py` e 3 em `tests/test_live_runtime.py` (arquivos existentes) + 1 arquivo novo `tests/test_migrate_live_db.py`, inevitável porque `scripts/migrate_live_db.py` é script novo sem cobertura para reusar. ⬜ estado observável

```
cd meta-FEAT-000 && ../meta/.venv/Scripts/python.exe -m pytest -q
```

Baseline antes da feature (medido pelo plan-reviewer em `meta/`, 2026-08-18): **`249 passed in 7.13s`**.
Depois da feature: exit 0 e **≥ 255 testes**, sem `skip`, sem `xfail`.
A suíte inteira roda em ~7s — restringir o comando a 3 arquivos não economiza nada e cega
justamente as regressões que esta feature pode causar (`tests/test_dashboard_app.py`,
`tests/test_live_broker.py`, `tests/test_live_feed.py` são os que exercitam `live_journal()`
sem argumento, `PaperBroker` e `ReplayFeed`).

**As 5 asserções que a prova precisa conter** (sem elas o comando passa com a feature quebrada) — a guarda por broker test-double (P5 na revisão original) saiu do escopo desta feature, ver 6c:

| # | Asserção | Sem ela, o que passaria quebrado |
|---|----------|----------------------------------|
| P1 | `live_store._connect.__defaults__[0] == LIVE_DB_PATH` **e** `live_store.live_journal.__wrapped__.__defaults__[0] == LIVE_DB_PATH` | **o buraco mais grave do plano original:** dava para ligar WAL e criar `LIVE_DB_PATH` sem trocar default nenhum — o diário ao vivo continuaria gravando em `journal.sqlite` e a prova ficava verde. Nada no plano provava a separação, que é a feature inteira |
| P2 | conexão em `tmp_path`: `PRAGMA journal_mode` → `wal` e `PRAGMA busy_timeout` → `5000` | `_connect` sem WAL/busy_timeout — a disputa de lock que motivou o item 0.2 continua |
| P3 | `LiveRuntime(..., db_path=None).db_path == LIVE_DB_PATH` e `live.runtime.DB_PATH is core.config.LIVE_DB_PATH` | `runtime.py` continuar importando `DB_PATH` de backtest; toda a operação real seguiria no banco compartilhado |
| P4 | migração: 1ª rodada copia N linhas; 2ª rodada insere 0; `source` idêntica byte a byte (comparar `read_bytes()` antes/depois); `PRAGMA foreign_key_check` vazio no destino; origem sem tabelas `live_*` devolve `{}` sem exceção | migração que duplica histórico, que corrompe FK por ordem errada de cópia, ou que quebra em instalação nova |
| P5 | `_ensure_disposable_sim_db(LIVE_DB_PATH)` e `(DB_PATH)` levantam `SystemExit`; `_ensure_disposable_sim_db(SIM_DB)` não levanta | a guarda do `.unlink()` do simulador ficaria **sem prova nenhuma** (o plano original a "provava" por `py_compile` + leitura visual — inspeção manual, proibida) |

**Teste de falsificação (uma linha):** apago a troca de default em `live_store.py` e em `runtime.py`
(mantendo `LIVE_DB_PATH` criada e o WAL ligado) — a feature está funcionalmente ausente, e
P1/P3 falham. Com a prova original (só WAL + migração + guarda por feed), esse mesmo cenário
passava verde.

**RED antes de GREEN:** obrigatório (T3) — cada asserção acima é escrita e rodada contra o código
ATUAL antes de qualquer implementação, e a saída RED (com o nome dos testes que falharam) vai
colada na seção 7. Uma asserção que já passa em RED é uma asserção que não prova nada: reescrever.

## 5. Riscos e gatilhos de escalação

- **Divergência com o EXEC-MAP:** a coluna "Escreve" do EXEC-MAP para FEAT-000 não lista arquivos de teste, mas a própria "Prova de conclusão" declarada lá ("teste novo: migração idempotente + `LiveRuntime` recusa...") só é possível criando/editando `tests/test_live_store.py`, `tests/test_live_runtime.py` e `tests/test_migrate_live_db.py`. Tratado aqui como delta trivial e esperado (a prova já pedia isso), não como desvio de arquitetura — registrado explicitamente, não escalado.
- **Nome `DB_PATH` mantido em `live/runtime.py` apontando para `LIVE_DB_PATH`:** um pouco confuso para quem ler o código sem contexto (variável chamada `DB_PATH` que na verdade é o banco ao vivo). Mitigação: comentário explícito no import e na linha do `__init__` explicando que o nome é mantido só por compatibilidade com o monkeypatch de `tests/test_dashboard_app.py` (arquivo de outra feature, fora do meu escopo para editar).
- **Banco real de produção (`db/journal.sqlite` de verdade) não é migrado automaticamente por esta feature** — o script existe e é testado com bancos sintéticos em `tmp_path`; rodar `scripts/migrate_live_db.py` contra o banco real da máquina é ação humana, fora do escopo de teste automatizado desta feature.
- **Conta real fica invisível até a migração rodar (novo, plan-reviewer):** trocar o default é uma
  migração de dado, não só de caminho. No instante do merge, `db/live.sqlite` está vazio e a conta
  `principal` (que hoje vive em `db/journal.sqlite`) some do `/operacao` até um humano rodar
  `python scripts/migrate_live_db.py`. Nenhum teste pega isso (todos usam `tmp_path`). Mitigação
  obrigatória: passo 8 — a consequência vai escrita no relatório de execução e na mensagem do
  commit. Reversão é trivial (apagar `db/live.sqlite`), porque a origem nunca é escrita.
- **Guarda larga demais é tão ruim quanto guarda ausente:** um `ValueError` no `__init__` do
  `LiveRuntime` derruba `/operacao` inteiro (`live_service._build_runtime` constrói o runtime até
  para LER status). Por isso P5 tem duas metades e a prova é a suíte inteira, não 3 arquivos.
- **Resolvido — critério do dublê:** ver seção 6c. O plan-reviewer confirmou que a divergência
  era material, não semântica; o usuário escolheu a opção A (guarda por broker vai para
  FEAT-001). Sem risco residual nesta feature.

**Gaps do agente de hipóteses (2026-08-18) — conhecidos, não corrigidos nesta feature:**

- **A3/A4 (dois processos escrevendo em `journal.sqlite`/`live.sqlite` durante a janela de deploy):** mitigação é operacional — parar os processos antigos antes de rodar `migrate_live_db.py`, não código. Fora do escopo de FEAT-000.
- **C1-C7 (concorrência WAL entre múltiplos processos, OneDrive sincronizando o `.sqlite` por baixo, `ATTACH` sobre uma origem que já esteja em modo WAL):** riscos de infraestrutura/ambiente além do escopo de uma feature de fundação de banco. Ver nota operacional de deploy (fora deste plano).
- **E1 (validação geral de `db_path` explícito arbitrário passado a `LiveRuntime`):** pertence a FEAT-001, que já revisa identidade de conta/broker (a guarda por broker test-double, ver 6c).
- **C5 (tratamento de exceção em `execute_session`):** arquivo (`live/runtime.py` além do rename do passo 5) fora do escopo desta feature.

## 6. Correções do plan-reviewer

Revisão de 2026-08-18. **Natureza: SUBSTANTIVAS** (prova trocada, passos novos, 1 bloqueio).

| # | O que estava errado | Correção aplicada | Motivo |
|---|---------------------|-------------------|--------|
| 1 | **A prova não provava a feature.** Nenhuma asserção verificava que o default de `_connect`/`live_journal`/`LiveRuntime` passou a ser `LIVE_DB_PATH`. Dava para criar a constante, ligar WAL, escrever a migração e a guarda — e deixar o diário ao vivo gravando em `journal.sqlite` — com a prova **verde** | Seção 4 reescrita com 6 asserções nomeadas (P1..P6) e uma coluna dizendo o que passaria quebrado sem cada uma. P1 e P3 são novas e são o núcleo | A separação física É a feature (0.2). Prova que não pega a ausência da feature é prova inválida (regra C) |
| 2 | Prova restrita a 3 arquivos de teste — cega para as regressões que esta feature provoca (`live_journal()` sem argumento em `dashboard/app.py:370,433,699` e `live_service.py:30`; `PaperBroker`/`ReplayFeed` em `test_live_broker.py`/`test_live_feed.py`/`test_dashboard_app.py`) | Prova passa a ser `pytest -q` (suíte inteira), com baseline medido: **249 passed in 7.13s** | Ordem de preferência da regra 7: comando que já existe > teste novo. A suíte inteira leva 7s — o recorte não economizava nada e escondia risco |
| 3 | **Passo 6 provado por inspeção visual** ("`py_compile` limpo; leitura confirma que o assert roda antes do `.unlink()`") | Guarda extraída para `_ensure_disposable_sim_db(path)`, importável, levantando `SystemExit`; asserção P6 nos dois sentidos | Inspeção visual é prova inválida (regra C). Metade do item 0.3 ficava sem prova |
| 4 | Guarda por `assert` | Trocada por `raise SystemExit` | `assert` some sob `python -O`. Salvaguarda contra `.unlink()` do banco real não pode depender de flag de interpretador |
| 5 | Guarda comparava só contra `LIVE_DB_PATH`; e `SIM_DB = Path("db/live_sim.sqlite")` é **relativo ao cwd** | Guarda compara contra `LIVE_DB_PATH` **e** `DB_PATH`; `SIM_DB` passa a ser absoluto (`ROOT / "db" / "live_sim.sqlite"`) | Como está, a comparação é tautológica (nomes de arquivo diferentes, nunca coincidem) — código morto se passando por salvaguarda. E rodar o script de outro diretório cria/apaga um `db/` no lugar errado |
| 6 | **Migração descrita como "`ATTACH` + `INSERT OR IGNORE`" — não roda contra o banco real** | Nova seção 3.4 com 7 requisitos: criar schema no destino; `SELECT *` preservando `id`; ordem de FK (`live_accounts` → `live_intents` → `live_orders` → `live_fills` → resto); `ATTACH` fora de transação e com `mode=ro`; origem sem `live_*` devolve `{}`; reversibilidade; o que fazer se a prova falhar | `_connect` liga `PRAGMA foreign_keys = ON` (`live_store.py:134`) e todas as tabelas `live_*` têm FK para `live_accounts` — copiar fora de ordem **falha**, e sem `SELECT *` o AUTOINCREMENT do destino reatribui `id` e a 2ª rodada duplica |
| 7 | Prova da migração sem checagem de integridade | P4 exige `PRAGMA foreign_key_check` vazio no destino + `source.read_bytes()` idêntico | É a asserção que pega a ordem errada de cópia; "origem intacta" genérico não pega |
| 8 | Passo 5 comparava `self.db_path` com `core.config.LIVE_DB_PATH` importado direto | Compara com o nome de módulo `DB_PATH` | Senão `monkeypatch.setattr(live_runtime, "DB_PATH", tmp)` (`test_dashboard_app.py:46`) desloca o default mas não a guarda, e as duas coisas divergem em teste |
| 9 | Consequência operacional da troca de default não estava no plano | Passo 8 + risco novo na seção 5 | Depois do merge `/operacao` lê um `db/live.sqlite` vazio e a conta `principal` "some" até alguém rodar a migração. É migração de dado (checklist B), não detalhe |
| 10 | RED antes de GREEN citado só no fim, sem exigir evidência | Nota no topo da seção 3 + exigência de colar a saída RED na seção 7 + "asserção que já passa em RED não prova nada" | T3 exige RED e exige que ele seja verificável depois |
| 11 | **Critério da guarda trocado (broker → feed)** | **Não corrigido — ESCALADO.** Ver 6b | Fora do que o revisor pode decidir: exige ou reordenar features, ou emendar a prova formal do `EXEC-MAP` |

### 6b. ESCALAÇÃO — critério do "test double" na guarda do `LiveRuntime` (passo 5)

**O que o original pede (literal):** plano original, Lote 0, item 0.3 — *"`LiveRuntime` passa a
**recusar** `db_path` que aponte para `LIVE_DB_PATH` quando **o broker** for um test double"*.
O `EXEC-MAP.md` repete na coluna "Prova de conclusão" de FEAT-000: *"`LiveRuntime` recusa
`db_path=LIVE_DB_PATH` com **broker test-double**"*.

**O que o plano escreveu:** guarda por `isinstance(feed, ReplayFeed)` — critério de **feed**.

**Por que a diferença é material (não é sinônimo):**

| Caminho | Broker | Feed | `db_path` | Guarda por broker | Guarda por feed |
|---------|--------|------|-----------|-------------------|-----------------|
| `scripts/run_live_sim.py` sem `db_path=SIM_DB` | `PaperBroker` | `ReplayFeed` | `LIVE_DB_PATH` | recusa ✅ | recusa ✅ |
| `python scripts/run_live.py loop` **sem flags** (`--mode` default `"paper"`, `run_live.py:312`) | `PaperBroker` | `ParquetCloseFeed` | `LIVE_DB_PATH` | recusa ✅ | **aceita ❌** |
| `/operacao` (`live_service.py:51`, conta em modo `paper`) | `PaperBroker` | `ParquetCloseFeed` | `LIVE_DB_PATH` | **recusa — quebra a página ❌** | aceita ✅ |

Ou seja: o critério do original fecha o buraco real (fills simulados entrando no diário de
produção pelo comando default do supervisor) mas **derruba `/operacao`**; o critério do plano
mantém tudo de pé mas **deixa o buraco aberto**. Nenhum dos dois é "só uma implementação".

**Onde o plano original é insuficiente:** 0.3 pressupõe que `PaperBroker` já esteja fora do
caminho de produção — o que só acontece em **1.2** (fim do fallback silencioso) e **1.4**
("`PaperBroker` e `ReplayFeed` → `tests/doubles.py`"; o próprio texto admite: *"`ReplayFeed` já
está fora do caminho de produção; `PaperBroker` não"*). O `EXEC-MAP` agendou isso em FEAT-001,
**depois** de FEAT-000. A feature, como cortada, depende de artefato da feature seguinte.

**Opções (sem escolher — decisão do orquestrador/usuário):**

- **A — Serializar ao contrário.** Mover a guarda (item 0.3) para FEAT-001, que já escreve
  `live_service.py`, `run_live.py` e `broker.py`. FEAT-000 fica só com 0.2 (banco separado,
  WAL, migração) e a linha do `EXEC-MAP` perde a cláusula do broker. Custo: reescrever 2 linhas
  do `EXEC-MAP`; nenhuma feature perde escopo.
- **B — Ampliar o escopo de FEAT-000.** Incluir `src/dashboard/live_service.py` e
  `scripts/run_live.py` na coluna "Escreve" e implementar o critério do original (broker),
  ajustando os dois pontos que hoje caem em `PaperBroker`. Custo: colisão física declarada com
  FEAT-001 nos mesmos arquivos; retrabalho quase certo.
- **C — Emendar o critério para "feed", como o plano escreveu.** Custo: assumido e registrado
  que `run_live.py loop` sem flags segue podendo gravar fills simulados no `db/live.sqlite` real
  até FEAT-001; exige alterar a "Prova de conclusão" de FEAT-000 no `EXEC-MAP` (hoje ela diz
  "broker test-double") e adicionar o buraco à lista de pendências de FEAT-001.

**Bloqueava:** só o passo 5 (parte da guarda) e a asserção P5 original. Resolvido em 6c.

### 6c. Resolução da escalação (usuário, via orquestrador — 2026-08-18)

**Decisão: opção A.** FEAT-000 entrega só a separação física do banco — rename
`DB_PATH`→`LIVE_DB_PATH` em `runtime.py` (sem guarda), WAL/busy_timeout, migração idempotente,
guarda do simulador acelerado. A guarda "`LiveRuntime` recusa `db_path=LIVE_DB_PATH` quando o
broker for test-double" (a letra original do item 0.3) passa a ser requisito explícito de
FEAT-001 — que já reescreve `live_service.py`/`run_live.py`/`broker.py` e é onde `PaperBroker`
efetivamente sai do caminho de produção (1.2/1.4). `EXEC-MAP.md` atualizado: linha de FEAT-000
perdeu a cláusula do broker na prova; linha de FEAT-001 ganhou a guarda como escrita explícita.

Consequência para esta feature: passo 5 fica só com o rename (P3 já cobria isso, nunca esteve
bloqueado); P5/P6 originais viram P5 único (guarda do simulador). Nenhum outro passo muda.

## 7. Registro de execução

> Preenchido pelo feature-agent após executar.

**Passos executados:** 8/8 (passo 5 executado só com o rename, sem guarda — ver 6c, não é bloqueio)

**Commits:**
- `50a1f1d` feat(blindagem): FEAT-000 adiciona LIVE_DB_PATH separado do banco de backtest
- `b96adf5` feat(blindagem): FEAT-000 diário ao vivo usa LIVE_DB_PATH por padrão e liga WAL/busy_timeout
- `404c29b` feat(blindagem): FEAT-000 LiveRuntime passa a apontar para o banco separado
- `c862c99` feat(blindagem): FEAT-000 migração journal.sqlite->live.sqlite e guarda do simulador acelerado

**Evidência RED (obrigatória, T3) — saída do `pytest` com os testes novos ANTES da implementação:**
```
$ ../meta/.venv/Scripts/python.exe -m pytest -q tests/test_live_store.py tests/test_live_runtime.py tests/test_migrate_live_db.py
=================================== ERRORS ====================================
__________________ ERROR collecting tests/test_live_store.py __________________
ImportError while importing test module '...\tests\test_live_store.py'.
tests\test_live_store.py:7: in <module>
    from core.config import LIVE_DB_PATH
E   ImportError: cannot import name 'LIVE_DB_PATH' from 'core.config' (...\src\core\config.py)
_______________ ERROR collecting tests/test_migrate_live_db.py ________________
ImportError while importing test module '...\tests\test_migrate_live_db.py'.
tests\test_migrate_live_db.py:23: in <module>
    from core.config import DB_PATH, LIVE_DB_PATH
E   ImportError: cannot import name 'LIVE_DB_PATH' from 'core.config' (...\src\core\config.py)
=========================== short test summary info ===========================
ERROR tests/test_live_store.py
ERROR tests/test_migrate_live_db.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
2 errors in 1.08s

$ ../meta/.venv/Scripts/python.exe -m pytest -q tests/test_live_runtime.py::test_db_path_default_e_live_db_path
F                                                                        [100%]
_____________________ test_db_path_default_e_live_db_path _____________________
    def test_db_path_default_e_live_db_path():
        from core.config import LIVE_DB_PATH
E       ImportError: cannot import name 'LIVE_DB_PATH' from 'core.config' (...\src\core\config.py)
1 failed in 0.72s
```
(collection falhando nos dois arquivos que importam `LIVE_DB_PATH` no topo do
módulo já é a prova RED de todas as asserções P1/P2/P4/P5 neles; o 3º bloco
isola P3 em `test_live_runtime.py`, que não importa `LIVE_DB_PATH` no topo do
módulo e por isso falha em runtime, não em coleta.)

**Consequência operacional a comunicar (passo 8):**
```
Depois deste merge, /operacao e `scripts/run_live.py status` passam a ler
db/live.sqlite, que nasce VAZIO. A conta real "principal" continua só em
db/journal.sqlite até alguém rodar, na máquina de produção:
    python scripts/migrate_live_db.py
Isso é ação humana, fora do teste automatizado. Reversão é trivial (apagar
db/live.sqlite) porque a migração nunca escreve na origem.
```

**Relatório do PRE-GATE (regra 18) — input obrigatório do code-reviewer:**
```
1. prova      ✅ ../meta/.venv/Scripts/python.exe -m pytest -q → exit 0, 256 passed in 2.76s
              (baseline pré-feature 249 passed, medido nesta mesma worktree após
              restaurar data/raw/ — ver Desvios; +7 testes novos = 256)
2. lint       n/a: sem ruff/flake8 instalado no venv (registrado no EXEC-MAP)
3. typecheck  ✅ ../meta/.venv/Scripts/python.exe -m py_compile src/core/config.py
              src/journal/live_store.py src/live/runtime.py scripts/run_live_sim.py
              scripts/migrate_live_db.py tests/test_live_store.py
              tests/test_live_runtime.py tests/test_migrate_live_db.py → sem erro
4. escopo     ✅ git diff --name-only plan/blindagem-operacao-real...HEAD → 9 arquivos,
              todos previstos na seção 2 (6 de código/schema + 3 de teste)
5. higiene    ✅ grep no diff por TODO/FIXME/print/console.log/pdb/breakpoint → só
              `print(result)` legítimo na CLI de migrate_live_db.py; git status limpo
Rodadas até fechar: 1
```

**Evidência da prova de conclusão:**
```
$ cd meta-FEAT-000 && ../meta/.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 28%]
........................................................................ [ 56%]
........................................................................ [ 84%]
........................................                                 [100%]
256 passed, 1 warning in 2.76s
```
As 5 asserções P1..P5: `test_default_do_diario_ao_vivo_e_live_db_path` +
`test_connect_liga_wal_e_busy_timeout` (`tests/test_live_store.py`),
`test_db_path_default_e_live_db_path` (`tests/test_live_runtime.py`),
`test_migrate_copia_e_e_idempotente_e_preserva_origem` +
`test_migrate_origem_sem_tabelas_live_devolve_vazio` +
`test_migrate_origem_inexistente_devolve_vazio` +
`test_run_live_sim_recusa_apagar_banco_real` (`tests/test_migrate_live_db.py`) —
todas presentes e verdes na execução acima.

**Desvios (triviais, com plano atualizado):**
- **Worktree sem `data/raw/`** (gitignored, não copiado por `git worktree add`):
  a suíte completa falhava com 2 testes de `test_dashboard_app.py` por
  `FileNotFoundError` ao carregar parquet (`247 passed, 2 failed`), nada a ver
  com esta feature. Copiei `../meta/data/raw` para `meta-FEAT-000/data/raw`
  (arquivo gitignorado, sem impacto em commit/escopo) e a suíte voltou ao
  baseline documentado — `249 passed`. Registrado aqui porque não estava
  antecipado no EXEC-MAP ("nenhum worktree depende de banco do repo
  principal" cobria `db/*.sqlite`, mas não `data/raw/`).
- Teste `test_run_live_sim_recusa_apagar_banco_real` e os 3 testes de
  `migrate()` foram escritos no mesmo arquivo novo `tests/test_migrate_live_db.py`
  (o plano já previa isso explicitamente na seção 2, "evita criar um 4º
  arquivo de teste") — sem desvio real, só confirmando que segui o previsto.
- Nenhum outro desvio: os 9 arquivos tocados são exatamente os 9 previstos na
  seção 2 do plano (6 de produção + 3 de teste).

**Desvios relevantes para features seguintes:**
- FEAT-001 herda a obrigação da guarda "`LiveRuntime` recusa `db_path=LIVE_DB_PATH`
  quando o broker for test-double" (decisão 6c, já refletida no `EXEC-MAP.md`).
- FEAT-001 deve estar ciente de que `db/live.sqlite` nasce vazio após este
  merge — se algum teste seu assumir dado pré-existente na conta `principal`
  fora de `tmp_path`, ele vai falhar até a migração manual rodar na máquina
  (não deveria acontecer, já que a suíte inteira usa `tmp_path`, mas registrando
  por transparência).

**Arquivos realmente tocados:**
- `src/core/config.py`
- `src/journal/live_store.py`
- `src/journal/schema.sql`
- `src/live/runtime.py`
- `scripts/run_live_sim.py`
- `scripts/migrate_live_db.py` (novo)
- `tests/test_live_store.py`
- `tests/test_live_runtime.py`
- `tests/test_migrate_live_db.py` (novo)

## 7b. Correção pós-code-review (agente de hipóteses, 2026-08-18)

> O `code-reviewer` original aprovou a feature (ver DoD abaixo), mas um "agente de
> hipóteses" independente — parte do processo que esta run exige por lote — encontrou
> gaps reais não cobertos pelo code-review, vários no núcleo do que a run
> `blindagem-operacao-real` existe para evitar (dinheiro inventado/perdido em silêncio).
> Um fixer novo (agente novo, MODO: CORREÇÃO) corrigiu os itens abaixo na mesma
> worktree/branch de FEAT-000.

**Itens corrigidos:**

1. **Marcador de conclusão de migração** (fecha A1/A2/A4/B2) — `scripts/migrate_live_db.py`
   agora lê `PRAGMA user_version` do destino ANTES de copiar, dentro da mesma transação da
   cópia. Se `user_version == 0` e o destino já tem qualquer linha em `live_accounts` (escrita
   real por fora desta migração), a migração é RECUSADA (`MigrationRefused`) a menos que
   `--force`/`force=True` seja passado — flag que ignora só essa checagem específica. Se
   `user_version == 0` e destino vazio, copia normalmente e grava `PRAGMA user_version = 1` na
   mesma transação. Se `user_version >= 1` (já migrado antes), segue copiando normalmente sem
   exigir `--force` (idempotência preservada). Limite residual documentado no docstring do
   módulo (não corrigido, fora de escopo): `ensure_tables`/`_connect` do `live_store` já dão um
   `commit()` implícito ao criar o schema, antes da transação de cópia começar — na prática
   inofensivo, pois `CREATE TABLE IF NOT EXISTS` não grava dado nem toca `user_version`.
2. **Relatório de divergência de contagem** (fecha F1/A5/A6) — depois de copiar cada tabela,
   compara `COUNT(*)` da origem (somente-leitura) com `COUNT(*)` do destino pós-cópia. Se o
   destino ficou com menos linhas, imprime `AVISO: <tabela> tem N linhas na origem mas só M no
   destino — Q linha(s) não copiada(s), possivelmente por violação de CHECK/UNIQUE/NOT NULL`
   por tabela afetada e levanta `MigrationIncomplete` (dado já commitado — não é rollback, é
   relatório loud). Sem divergência, comportamento atual (retorno normal) é mantido.
3. **Distinção "arquivo de origem ausente" vs. "arquivo existe sem tabelas `live_*`"** (fecha
   A7) — `source` que não existe no disco agora levanta `FileNotFoundError` com o caminho na
   mensagem (antes devolvia `{}`/exit 0, indistinguível de "migração completa" — um typo em
   `--source` passava despercebido). `source` existente sem nenhuma tabela `live_*` continua
   devolvendo `{}` (caso legítimo de instalação nova) — já coberto por teste existente
   (`test_migrate_origem_sem_tabelas_live_devolve_vazio`), então nenhum teste novo foi
   necessário para essa metade (regra 6: checar o que já existe antes de inventar trabalho).
4. **Sidecars WAL** (fecha D3 + item não-bloqueante do code-reviewer sobre `.gitignore`) —
   `.gitignore` ganhou `db/*.sqlite-wal`/`db/*.sqlite-shm`; `scripts/run_live_sim.py` apaga os
   sidecars do `SIM_DB` junto com o `.unlink()` principal (não é erro se não existirem); a
   docstring de `migrate_live_db.py` explica que desfazer a migração apagando só
   `live.sqlite` pode deixar sidecars órfãos — rodar `PRAGMA wal_checkpoint(TRUNCATE)` antes,
   ou apagar os três arquivos juntos.
5. **Comentário honesto sobre `busy_timeout`** (item não-bloqueante do code-reviewer) —
   `src/journal/live_store.py`: o comentário não atribui mais a essa linha a proteção contra
   lock que o Python já dá por padrão (`sqlite3.connect` usa `timeout=5.0s`); reflete que é
   defesa explícita contra alguém no futuro passar `timeout=0` ao conectar.
6. **Teste com caminho de produção real** (fecha E3) — `tests/test_live_runtime.py`:
   `test_db_path_default_e_live_db_path` reescrito para `monkeypatch.setattr(live_runtime,
   "DB_PATH", tmp_path / "live_test.sqlite")` (convenção de `tests/test_dashboard_app.py:46`)
   antes de instanciar `LiveRuntime`, comparando contra o valor monkeypatchado. Mantida
   asserção separada, ANTES do monkeypatch, provando `live_runtime.DB_PATH is
   core.config.LIVE_DB_PATH` sem instanciar nada apontando pro caminho real.

**Fora de escopo desta correção (registrado, ver seção 5):** A3/A4, C1-C7, E1, C5.

**Testes novos/ajustados em `tests/test_migrate_live_db.py`:**
- `test_migrate_origem_inexistente_levanta_filenotfound` (substitui o teste que esperava `{}`)
- `test_migrate_recusa_destino_ja_povoado_sem_marcador` (novo)
- `test_migrate_force_ignora_recusa_e_copia` (novo)
- `test_migrate_destino_ja_migrado_nao_exige_force` (novo)
- `test_migrate_reporta_divergencia_e_levanta_incompleto` (novo)

**PRE-GATE (correção):**
```
1. prova      ✅ ../meta/.venv/Scripts/python.exe -m pytest -q → exit 0, 260 passed in 7.51s
              (baseline pré-correção 256 passed; +4 testes novos líquidos em
              tests/test_migrate_live_db.py = 260)
2. lint       n/a: sem ruff/flake8 instalado no venv (mesmo registrado no PRE-GATE original)
3. typecheck  ✅ ../meta/.venv/Scripts/python.exe -m py_compile scripts/migrate_live_db.py
              scripts/run_live_sim.py src/journal/live_store.py
              tests/test_migrate_live_db.py tests/test_live_runtime.py → sem erro
4. escopo     ✅ git diff --name-only HEAD (antes dos commits desta correção) → 6 arquivos,
              todos os citados no briefing de correção: .gitignore,
              scripts/migrate_live_db.py, scripts/run_live_sim.py,
              src/journal/live_store.py, tests/test_live_runtime.py,
              tests/test_migrate_live_db.py
5. higiene    ✅ grep no diff por TODO/FIXME/print/console.log/pdb/breakpoint → só
              os `print(...)` legítimos de CLI/AVISO já previstos pela correção
Rodadas até fechar: 1
```

**Evidência da prova (correção):**
```
$ cd meta-FEAT-000 && ../meta/.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 27%]
........................................................................ [ 55%]
........................................................................ [ 83%]
............................................                             [100%]
260 passed, 1 warning in 7.51s
```

**Smoke-test manual do CLI (`scripts/migrate_live_db.py`):**
- `--source <inexistente> --dest <novo>` → `[migrate] ERRO: origem não existe: ...` + exit 1
  (confirmado via shell fora do pytest, além dos testes automatizados).

**Commits desta correção (branch `feat/blindagem-operacao-real-FEAT-000`):**
- `758c248` feat(blindagem): FEAT-000 marcador de migração + relatório de divergência + distinção arquivo ausente
- `dadb9ec` feat(blindagem): FEAT-000 sidecars WAL do banco ao vivo (.gitignore + limpeza no simulador)
- `c11b56a` feat(blindagem): FEAT-000 comentário honesto sobre busy_timeout
- `cd0af6f` feat(blindagem): FEAT-000 teste de runtime usa monkeypatch em vez do caminho real de produção

**Desvios:** nenhum. Os 6 arquivos tocados são exatamente os 6 citados no briefing da
correção (`scripts/migrate_live_db.py`, `scripts/run_live_sim.py`, `.gitignore`,
`src/journal/live_store.py`, `tests/test_migrate_live_db.py`, `tests/test_live_runtime.py`).
Nenhum arquivo de outra feature ou fora da lista foi tocado.

## 7c. Correção pós-code-review (rodada 2 — REJEIÇÃO, tentativa 1/2, 2026-08-18)

> O `code-reviewer` rejeitou a correção da seção 7b com 2 issues bloqueantes e 2
> não-bloqueantes. Um fixer novo (agente novo, MODO: CORREÇÃO) corrigiu os 4 itens
> abaixo na mesma worktree/branch de FEAT-000.

**Itens corrigidos:**

1. **(bloqueante) Checagem de divergência não pegava perda silenciosa no `--force`** —
   a checagem antiga comparava `COUNT(*)` TOTAL origem vs. destino pós-cópia
   (`after < source_count`). Isso não detecta o caso reproduzido de fato pelo
   revisor: destino já com `live_accounts` id=1 (conta `principal` criada pelo robô
   real, dinheiro de verdade) e origem também com id=1 — `INSERT OR IGNORE` descarta
   a linha da ORIGEM preservando a do DESTINO, a contagem TOTAL bate (nada "some" em
   número), o aviso não disparava, e a conta real era perdida em silêncio. Trocado
   para checagem linha a linha, por tabela, depois do commit:
   `SELECT COUNT(*) FROM (SELECT * FROM src_ro.<tabela> EXCEPT SELECT * FROM <tabela>)`
   — linhas da origem sem equivalente EXATO (todas as colunas) no destino. Resultado
   != 0 cobre tanto descarte por CHECK/UNIQUE/NOT NULL quanto colisão de id com
   conteúdo divergente. `MigrationIncomplete.mismatches` mudou de
   `(tabela, count_origem, count_destino)` para `(tabela, linhas_sem_par_exato)` —
   ajustado em `scripts/migrate_live_db.py` e no teste existente
   `test_migrate_reporta_divergencia_e_levanta_incompleto`. Continua dando 0 na 2ª
   rodada idempotente (`test_migrate_copia_e_e_idempotente_e_preserva_origem`) e no
   teste de `--force` sem colisão (`test_migrate_force_ignora_recusa_e_copia`, id=99
   no destino) — ambos seguem verdes sem alteração de asserção.
2. **(bloqueante) Mensagem de recusa e help do `--force` diziam o oposto do
   comportamento real** — ambos afirmavam "use só se tiver certeza de que é seguro
   **sobrescrever**", falso: `INSERT OR IGNORE` nunca sobrescreve, PRESERVA a linha
   do destino e DESCARTA a da origem em colisão de `id`. Mensagem de `MigrationRefused`
   e help de `--force` (`scripts/migrate_live_db.py`) reescritos para dizer isso
   explicitamente — dado real pode ser PERDIDO, não sobrescrito.
3. **(não-bloqueante) Limpeza dos sidecars `-wal`/`-shm` aninhada em
   `if SIM_DB.exists()`** — se alguém apagasse só o arquivo principal a mão, os
   sidecars órfãos sobreviviam. `scripts/run_live_sim.py`: loop de limpeza tirado de
   dentro do `if`, mantendo só a condição `not args.keep`.
4. **(não-bloqueante) `source.exists()` é `True` para diretório** — `--source db/`
   por engano caía num erro cru do sqlite. `scripts/migrate_live_db.py`: checagem
   `source.is_file()` explícita, levanta `IsADirectoryError` com mensagem amigável
   (tratada em `main()` junto de `FileNotFoundError`).

**Teste novo em `tests/test_migrate_live_db.py`:**
- `test_migrate_force_detecta_colisao_de_id_com_conteudo_divergente` — reproduz o
  cenário realista do revisor (destino `live_accounts` id=1 cash=1000 criado pelo
  robô real; origem id=1 cash=47321,55 + `live_intents` pendurado nesse id) e
  confirma que `migrate(force=True)` detecta e reporta a divergência
  (`MigrationIncomplete`, `("live_accounts", 1)` em `.mismatches`) em vez de sair
  silenciosamente com exit 0; confirma também que o cash do destino (robô real)
  não foi sobrescrito e que o intent sem colisão de PK própria entrou normalmente.

**PRE-GATE (correção rodada 2):**
```
1. prova      ✅ ../meta/.venv/Scripts/python.exe -m pytest -q → exit 0, 261 passed in 4.50s
              (baseline pré-correção 260 passed; +1 teste novo em
              tests/test_migrate_live_db.py = 261)
2. lint       n/a: sem ruff/flake8 instalado no venv (mesmo registrado nas rodadas anteriores)
3. typecheck  ✅ ../meta/.venv/Scripts/python.exe -m py_compile scripts/migrate_live_db.py
              scripts/run_live_sim.py tests/test_migrate_live_db.py → sem erro
4. escopo     ✅ git diff --name-only HEAD~2..HEAD → 3 arquivos, exatamente os 3
              autorizados no briefing da correção: scripts/migrate_live_db.py,
              scripts/run_live_sim.py, tests/test_migrate_live_db.py
5. higiene    ✅ grep no diff por TODO/FIXME/print/console.log/pdb/breakpoint → só
              os `print(...)` de AVISO/CLI já existentes/previstos; git status limpo
Rodadas até fechar: 1
```

**Evidência da prova (correção rodada 2):**
```
$ cd meta-FEAT-000 && ../meta/.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 27%]
........................................................................ [ 55%]
........................................................................ [ 82%]
.............................................                            [100%]
261 passed, 1 warning in 4.50s
```

**Smoke-test manual do CLI (`scripts/migrate_live_db.py`):**
- `--source db --dest <novo>` (diretório em vez de arquivo) →
  `[migrate] ERRO: origem não é um arquivo: db` + exit 1 (confirmado via shell,
  além do comportamento coberto por `IsADirectoryError`).
- `--help` → texto do `--force` confirmado dizendo "NÃO sobrescreve... a linha do
  DESTINO é mantida e a linha da ORIGEM é descartada... dado real pode ser
  PERDIDO" (sem menção a "sobrescrever").
- Limpeza de sidecars órfãos testada isoladamente (sem o arquivo principal
  presente): `-wal`/`-shm` removidos mesmo com `SIM_DB.exists() is False`.

**Commits desta correção (branch `feat/blindagem-operacao-real-FEAT-000`):**
- `60aafcf` feat(blindagem): FEAT-000 divergencia da migracao detecta colisao de id com conteudo divergente
- `b5f2162` feat(blindagem): FEAT-000 limpeza dos sidecars WAL roda mesmo com o banco principal ja apagado

**Desvios:** nenhum. Os 3 arquivos tocados (`scripts/migrate_live_db.py`,
`scripts/run_live_sim.py`, `tests/test_migrate_live_db.py`) são exatamente os 3
autorizados no briefing desta correção. Nenhum arquivo de outra feature ou fora da
lista foi tocado.

## 8. Definition of Done

- [x] Escalação 6b respondida pelo usuário (opção A, ver 6c) — passo 5 ajustado (só rename, sem guarda)
- [x] Todos os 8 passos da seção 3 executados
- [x] Evidência RED colada na seção 7, mostrando os testes novos falhando ANTES da implementação
- [x] As 5 asserções P1..P5 da seção 4 existem, com os nomes usados na seção 7
- [x] Prova de conclusão (`pytest -q`, suíte inteira) executada com evidência colada na seção 7 — exit 0, 256 testes (≥ 255), 0 skip
- [x] **PRE-GATE verde nos 5 itens**, com relatório na seção 7
- [x] Nenhum arquivo fora da seção 2 tocado (ou desvio justificado)
- [x] Testes da feature verdes; nada skipado
- [x] Sem `TODO`/código comentado/log de debug
- [x] Commits atômicos na convenção do projeto (`feat(blindagem): FEAT-000 <descrição>`)
- [x] Correção pós-code-review (agente de hipóteses) aplicada — 6 itens da seção 7b, suíte
      verde em 260 testes, PRE-GATE da correção verde
- [x] Correção pós-code-review rodada 2 (REJEIÇÃO, tentativa 1/2) aplicada — 4 itens
      (2 bloqueantes + 2 não-bloqueantes) da seção 7c, suíte verde em 261 testes,
      PRE-GATE da correção verde
- [ ] `code-reviewer` aprovou (rodada de correção)
