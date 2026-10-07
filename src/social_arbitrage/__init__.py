"""Arbitragem social -- tese discricionaria a partir de uma assimetria de
informacao real, ANTES do mercado precificar. Duas lentes (`thesis.Lente`):

  * **Chris Camilo** ("Laughing at Wall Street") -- observacao de consumo
    (prateleira vazia, video viral) antes do mercado notar.
  * **Larry Williams** (recorde de +11.376% em 1987, Robbins World Cup) --
    smart money via COT, calendario (TDW), padrao "Oops!" e %R como
    confirmacao -- ver a docstring de `thesis.Lente.POSICIONAMENTO` para os
    quatro juntos, e o dimensionamento por Kelly + teto de pior caso em
    `sizing.py`.

## Por que este modulo mora fora de `strategy/`

Regra 2 do `AGENTS.md` exige sinal PURO em `strategy/`: OHLCV in, decisao
out, sem I/O, porque aquele codigo sera portado para MQL5. Nenhuma das duas
lentes tem OHLCV puro como insumo -- Camilo usa observacao de campo, Williams
usa COT (dado externo) + confluencia de 4 fatores --, o dimensionamento e'
discricionario (Kelly fracionario, nao uma formula de risco fixa do motor) e
a saida por padrao NAO usa stop (nem Camilo nem Williams usam; ver
`CLAUDE.md`). Forcar isso dentro de `strategy/` quebraria a premissa que faz
o resto do repo portavel. Por isso e' feature-first PROPRIA
(`social_arbitrage/`), irma de `strategy/`/`journal/`/`backtest/`, e nao um
submodulo de estrategia.

## As duas fases do metodo (comuns as duas lentes)

1. **Desequilibrio de informacao** -- uma mudanca real de consumo acontece
   (prateleira vazia, video viral, fila de espera) e o mercado ainda nao
   sabe. E' aqui que a tese nasce (`thesis.Fase.DETECTADA`).
2. **Paridade de informacao** -- a imprensa financeira ou o proprio
   resultado trimestral da empresa confirma o que ja foi observado. A partir
   daqui a informacao e' publica e a tese perde a vantagem -- e' o CRITERIO
   DE SAIDA, nao um preco-alvo.

Entre as duas fases fica a etapa que realmente sustenta o metodo, e que
nenhum software substitui: verificar a tese durante dias/semanas (contatar
loja/distribuidor, medir se o volume pesa no resultado da empresa) antes de
arriscar capital nela. Ver `thesis.Fase.EM_VERIFICACAO`.

## Faseamento deste modulo (nao construir tudo de uma vez)

  1. **(pronto)** `brand_map.py` -- catalogo marca de consumo -> empresa
     listada na B3. Fundacao da lente CONSUMO: sem ele nao ha para onde a
     tese apontar.
  2. **(pronto)** `thesis.py` + `store.py` -- ficha da tese, evidencias
     acumuladas, maquina de estados ate APROVADA/REJEITADA, e registro
     manual de abertura/fechamento de posicao (o dono opera pelo canal que
     ja usa -- MT5/home broker -- e registra aqui; isto NAO manda ordem).
  3. **(pronto)** `sizing.py` -- dimensionamento por Kelly fracionario
     (meio-Kelly default) MAIS o teto independente de pior-caso de Larry
     Williams (150% da pior perda historica por unidade). As duas amarras
     sao INDEPENDENTES de proposito -- foi a segunda, nao a primeira, que
     segurou a conta dele no crash de 1987.
  4. **(pronto)** fontes de deteccao automatica para CONSUMO, NENHUMA exige
     credencial: `deteccao_reddit.py` (feed RSS/Atom publico de busca --
     `reddit.com/r/.../search.json` sem autenticacao devolve 403, mas
     `search.rss` devolve 200 com resultado real, confirmado ao vivo em
     2026-09-27; sem `score`/upvotes, que so' a API OAuth tem, e mais
     sensivel a rate limit -- 429 medido apos 2 chamadas seguidas sem
     pausa) e `deteccao_trends.py` (Google Trends via `pytrends`,
     nao-oficial). `scripts/social_arbitrage_monitorar.py` varre o catalogo
     e SUGERE um comando `detectar` pronto -- nunca cria tese sozinho
     (`tamanho_alvo_pct`/`criterio_saida` continuam decisao humana, sem
     default, por proposito). X/Twitter pesquisado e descartado por ora:
     tier gratuito acabou em fev/2026, e busca em historico completo exige
     Enterprise (US$42k/mes). TikTok pesquisado e fechado: API de pesquisa
     oficial so' libera para instituicao academica/ONG credenciada.
     Para POSICIONAMENTO, a serie de "posicao em aberto por tipo de
     investidor" que a B3 publica para futuros (o analogo do COT Report
     americano) e' produto COMERCIAL do UP2DATA (contato de vendas, preco
     nao publico) -- ainda NAO integrada, decisao de custo do dono.
  5. **(futuro, nao comecado)** disparo automatico de ordem apos aprovacao.
     Decisao adiada de proposito: dimensionamento concentrado (ate 40% do
     capital, ao estilo Camilo/Williams) e ausencia de stop colidem com o
     gate de risco que `live/` ja aplica aos robos sistematicos, e essa
     reconciliacao merece decisao propria do dono antes de automatizar o
     disparo de ordem -- nao e' so' um detalhe de integracao.

## O que este modulo explicitamente NAO e'

Nao e' um robo sistematico: nao ha `on_bar`, nao ha backtest, nao ha
`Strategy`/`IntradayStrategy`. E' um funil de registro e apoio a decisao
discricionaria -- a decisao final e' sempre do dono.
"""
