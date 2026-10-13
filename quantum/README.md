# Quantum — análise quantitativa da B3, sozinha e sem olhar o futuro

MVP inspirado no vídeo [*O que é análise quantitativa*](https://youtube.com/watch?v=WCVbHArkPAU)
(Mauricio Gamil). O método do vídeo, implementado como regras fechadas:

1. **Dados de todas as empresas da bolsa**: preços, balanços e indicadores com histórico.
2. **Uma hipótese vira regra objetiva.** Ranqueia o mercado inteiro por indicador e pega as N melhores.
3. **Backtest**: pesos iguais, filtro de liquidez (R$ 500 mil/dia) e rebalanceamento a cada 3, 6 ou 12 meses.
4. **4Ds**: rentabilidade (vs Ibovespa e CDI), risco (volatilidade, beta, queda), ciclos (altas e quedas
   do Ibovespa) e técnicos (taxa de acerto, payoff).

Este sistema acrescenta o que o vídeo não faz, para o resultado não sair enviesado:

| proteção | como |
|---|---|
| **sem olhar o futuro** | balanço só conta depois de `DT_RECEB` (data de entrega à CVM); decide no fechamento, executa no pregão seguinte |
| **IS / OOS / VIRGEM** | períodos fixados em `config.py` antes de qualquer resultado; a escolha usa só o IS; o OOS só confirma; o VIRGEM fica trancado e a revelação é registrada |
| **contra o acaso** | cada resultado comparado com 200 carteiras sorteadas do mesmo universo |
| **múltiplos testes** | Benjamini-Hochberg (q=0,10) sobre todas as estratégias da rodada |
| **custos** | 0,10% por lado sobre o giro |
| **desdobramentos** | valor de mercado com preço sem ajuste × ações da época, corrigidas por desdobramentos |

## Uso

```powershell
.\.venv\Scripts\python.exe -m quantum atualizar               # baixa tudo + roda os estudos (~30-40 min na 1ª vez)
.\.venv\Scripts\python.exe -m quantum servir                  # painel em http://127.0.0.1:8100
.\.venv\Scripts\python.exe -m quantum fonte yahoo             # baixa novos arquivos de UMA fonte
.\.venv\Scripts\python.exe -m quantum estudar --estrategias dy3a,formula_magica
.\.venv\Scripts\python.exe -m pytest quantum/tests
```

Com o servidor no ar, a atualização completa roda sozinha uma vez por dia útil, depois das 20h
(`QUANTUM_HORA_ATUALIZACAO`; desligue com `QUANTUM_AUTO=0`). Para atualizar sem o servidor aberto,
agende no Windows:

```powershell
schtasks /Create /TN "Quantum atualizar" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 20:30 `
  /TR "\"$PWD\.venv\Scripts\python.exe\" -m quantum atualizar" 
```

## Telas

| tela | o que mostra |
|---|---|
| **Painel** | estado da base, botão "atualizar tudo", execuções, veredito da última rodada |
| **Empresas** | todas as listadas com 12 indicadores, busca, setor, liquidez e ordenação |
| **Empresa** | indicadores de hoje, posição em cada estratégia, gráficos (retorno vs Ibov, receita/EBIT/lucro, múltiplos, proventos) e documentos do RI com filtro |
| **Estratégias** | as 10 receitas e a carteira que cada uma mandaria comprar hoje |
| **Estudos** | protocolo IS→OOS, veredito por estratégia, detalhe com grade, curvas, nulo e 4Ds; revelação do VIRGEM |
| **Backtest** | qualquer estratégia, N, frequência, período, liquidez e custo, com os 4Ds e as carteiras de cada rebalanceamento |
| **Fatores** | quintis de qualquer indicador: o fator ordena retorno ou não? |
| **Documentos** | lista curta, dados extraídos dos PDFs do RI (proventos, releases, fatos relevantes), uso e teto do Haiku |
| **Fontes** | cada fonte com status, botão "baixar novos arquivos" e a lista de todos os arquivos obtidos, com filtro |

## Fontes (todas gratuitas, exceto a última)

| fonte | o que vem | por quê |
|---|---|---|
| CVM · dados abertos | cadastro, FCA (tickers, site de RI), DFP/ITR (balanços com data de entrega), IPE (documentos do RI) | fonte ORIGINAL dos balanços; tem a data de entrega, que é o que permite backtest honesto |
| Yahoo (yfinance) | preço, proventos, desdobramentos, Ibovespa | gratuito e cobre as ativas |
| Banco Central (SGS 12) | CDI diário | benchmark de renda fixa |
| balancos.com.br | DFs publicadas | **paga, por consulta**; cobre principalmente S.A. FECHADAS. Para listadas, a CVM já é a fonte original. Fica desligada até existir `BALANCOS_TOKEN/LOGIN/SENHA` no ambiente |

## Dados dos documentos do RI: primeiro grátis, Haiku só de reserva

`documentos.py` lê os PDFs que as empresas protocolam na CVM (os mesmos do site de RI), **só para a lista curta**:
as empresas vigiadas (botão na página da empresa) e o topo de hoje de cada estratégia, começando pelas que o estudo
confirmou. São 30 empresas no máximo (`LISTA_CURTA_MAX`).

1. **Grátis, sem LLM:** o `pypdf` extrai o texto e regras (regex + palavras-chave) leem:
   - **proventos:** tipo (JCP/dividendo), R$/ação, data-com, data ex, pagamento
   - **releases:** receita, EBITDA, lucro, dívida líquida, unidade
   - **fatos relevantes:** tópicos (recompra, aquisição/venda, emissão, guidance, rating...) + resumo

   No primeiro teste real, 15 de 25 documentos saíram completos só por regras.
2. **Haiku (`claude-haiku-4-5`), só quando as regras não acham o mínimo.** Ele nasce **desligado**; liga com
   `QUANTUM_HAIKU=1` + credencial Anthropic no ambiente. Recebe só as páginas mais relevantes (~6 mil tokens no
   máximo, nunca o PDF inteiro) e responde em JSON validado por esquema. Tetos diários rígidos:
   `QUANTUM_HAIKU_DOCS_DIA` (40) e `QUANTUM_HAIKU_USD_DIA` (US$ 0,50). Cada chamada grava tokens e custo, e um
   documento já processado nunca é reenviado.

**Por que não raspar o site de RI de cada empresa:** são ~400 sites com layouts que mudam sem aviso.
Os mesmos documentos chegam à CVM padronizados e com data (IPE). O link de RI de cada empresa
aparece na página dela para leitura humana.

## Limitações conhecidas (leia antes de confiar num número)

- **Viés de sobrevivência.** O Yahoo quase não guarda tickers deslistados, e empresas que saíram da bolsa somem
  do passado. Isso infla o resultado de estratégias que compram empresas em dificuldade (P/VP baixo,
  dividendos altos). A CVM tem os balanços delas; o que falta é o preço.
- **Composição do capital só existe na CVM a partir de 2020.** Antes disso, as ações são estimadas por
  lucro ÷ LPA do mesmo documento. Funciona para empresas com lucro; quem teve prejuízo usa o último número conhecido.
- **Valor de mercado = ações totais × preço do ticker mais líquido.** Em empresas com ON e PN de preços muito
  diferentes, o número fica aproximado (é a mesma convenção do Fundamentus).
- **Escala da composição do capital.** Algumas empresas declaram as ações em milhares (Bradesco, Santander,
  Petrobras no 1T21). O sistema corrige com três checagens: lucro ÷ LPA, mediana da própria empresa e valor
  patrimonial por ação acima de R$ 2.000. Microcaps com dado ruim na própria CVM (ex.: GFSA3) ainda escapam; o filtro
  de liquidez costuma tirá-las do universo.
- **Units** (TAEE11, KLBN11, SANB11...): o preço por ação é o preço da unit dividido pela composição declarada no FCA.
- **Bancos e seguradoras** têm outro modelo de balanço: EV/EBIT, ROIC e margens ficam em branco para eles.
- **"Valor + Momento"**: o vídeo cita o método sem dizer os dois indicadores. Aqui ele é lucro/preço + momento
  12−1, a combinação clássica da literatura.

## Módulos

```
quantum/
├── config.py        períodos IS/OOS/VIRGEM, premissas, caminhos
├── armazem.py       SQLite: esquema, upsert, log, estudos, revelações
├── fontes/          arquivo.py (download + manifesto), cvm.py, yahoo.py, bcb.py
├── pipeline.py      uma etapa por fonte + atualização completa + tarefas em segundo plano
├── base.py          carrega o banco e monta o painel point-in-time de qualquer data
├── estrategias.py   catálogo declarativo (fatores, direção, filtros)
├── backtest.py      motor de ranking, pesos iguais, execução D+1, custo sobre giro
├── metricas.py      os 4Ds
├── estudos.py       protocolo IS→OOS, nulo por sorteio, Benjamini-Hochberg, estudo de fator
├── web/             FastAPI + Jinja2 + HTMX + Plotly
└── tests/
```

Para criar uma estratégia nova, acrescente uma entrada em `estrategias.ESTRATEGIAS`. Ela aparece sozinha
em todas as telas e na próxima rodada de estudos. Antes de rodar, escreva a regra e não mexa nela
depois de ver o OOS.
