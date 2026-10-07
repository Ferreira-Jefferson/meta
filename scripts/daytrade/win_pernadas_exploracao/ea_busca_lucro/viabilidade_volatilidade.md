# Viabilidade — estratégia de volatilidade (não-direcional) no WIN

Levantamento feito em 2026-10-05. Não é estratégia nem backtest — só reconhecimento.

## 1. Dado de opções: existe, mas é metadado vazio de liquidez

Nada em `data/` (nenhuma subpasta/arquivo com nome de opção, IV, strike, grego).
Nada em `src/`/`scripts/` que trate opção como produto — todo `symbols_get`/
`symbol_info` do repo serve só para achar o CONTRATO FUTURO corrente (raiz+letra+ano),
nunca uma opção. `requirements.txt` não tem cliente de opções; `.env` só guarda
`OPENROUTER_API_KEY` (LLM), nenhuma chave de dado de mercado.

Havia um terminal MT5 acessível neste ambiente e eu o consultei (só leitura,
nenhuma ordem): **opções de IBOV existem no catálogo do terminal** —
`symbols_get("IBOV*")` devolve 1938 séries sob `path="BOVESPA\OPCOES\..."`,
com `option_strike` e `expiration_time` reais (ex. `IBOVJ180B2`, strike
180.000, vencimento 2026-10-06). Isso é dado de produto real, não lixo.

Mas na prática está vazio: `copy_rates_range` (candle D1/M1 pronto) devolve
**0 barras** para toda série testada — o terminal nunca construiu OHLC para
elas. `symbol_info_tick` mostra `bid=ask=0` (sem cotação corrente) na
maioria, e `last=0/volume=0` em quase todas. Uma série que EU AMOSTREI por
acaso teve negócio (`IBOVJ180B2`, last=61,00, 1 negócio) — e
`copy_ticks_range` (90 dias) devolveu **328 ticks**, ou seja ~3,6
negócios/dia nessa série. Isso é demais esparso para qualquer coisa que
precise de profundidade de book ou de uma superfície de IV contínua, e não
sei se essa série foi sorte ou é representativa — não amostrei o universo
inteiro de 1938 séries por economia de tempo.

Busca externa: a B3 publica o **VXBR** (S&P/B3 Ibovespa VIX), índice oficial
de vol implícita — grátis, mas é UM número agregado por dia, não superfície
por strike/vencimento. `brapi.dev` vende um dataset de opções desde 2009
(strikes, séries, OHLCV, bid/ask EOD) — não confirmei se o tier grátis cobre
isso. `OBM.com.br` calcula IV/gregos por série, grátis, mas é página web
(sem API, sem granularidade intraday, sem histórico para baixar em massa).

## 2. Volatilidade sem opções, só com o WIN linear

- **(a) Straddle sintético / gamma scalping.** Precisa rebalancear quase
  contínuo, e CADA rebalanceio paga o desenho de execução fechado deste
  projeto (nunca a mercado, sempre limite+fila — ver CLAUDE.md): no mínimo
  2 ticks (R$0,40) + deslize, por PERNA, dezenas de vezes por dia. A série
  de opções que amostrei (3,6 negócios/dia) sugere que o WIN real também não
  teria contraparte líquida o bastante para rebalancear rápido sem mover o
  próprio preço. Não é de graça — é provavelmente inviável aqui, mas não
  tenho o número exato (não medi).
- **(b) Vol como filtro/sizing de uma aposta direcional.** Isto NÃO é
  categoria nova — é o mesmo dial que `copy_win` já usa (`stop_vol x
  volatilidade`). A Fase 1/2 encerrou com 0 edge direcional explorável; usar
  previsão de vol para aumentar o TAMANHO de uma aposta sem direção não cria
  edge, só aumenta a variância de uma aposta que já é zero. Ganho
  incremental real: zero, a não ser como gestão de risco (contratos menores
  quando vol baixa), não como fonte de lucro.
- **(c) Breakout por expansão de vol (tipo ORB).** Já foi testado
  (G7/G8/G13, `wdo_orb_*`) — é direcional disfarçado: aposta que depois de
  compressão vem expansão, mas ainda escolhe um lado. Não é volatilidade
  pura, é o mesmo jogo direcional com um filtro de regime.

## 3. Infraestrutura: motor é linear, de ponta a ponta

`core/instruments.py` declara só `point_value_brl`/`price_tick_size`/
`margin_per_contract_brl` — nenhum campo de prêmio, strike, exercício.
`backtest/intraday/engine.py`/`machine.py` e `strategy/daytrade/base.py`
assumem posição = contratos lineares, custo = ticks de deslize/fila. Não há
BS/binomial, não há proxy de vol histórica como insumo de preço (dá pra
implementar em numpy puro, sem scipy — confirmei que nem `scipy` nem
`sklearn` estão no venv), não há bid-ask mais largo nem liquidação por
exercício/vencimento. Isso não é "mais um parâmetro" — é um **5º motor do
zero** (ao lado dos 4 que já existem), com precificação, fila própria
(a amostra de 328 ticks/90d sugere fila PIOR que a do WIN) e liquidação no
vencimento. Esforço honesto: semanas de trabalho sério, não um ajuste.

## Veredito

**Não dá sem o dono fornecer/assinar algo.** O que falta especificamente:
um feed de dado de opções B3 com profundidade e histórico de verdade —
volume por série, bid/ask, e IV calculada com método (Kaplan-Meier do
preenchimento, no espírito do que este projeto já exige para o WDO) — via
assinatura de vendor (ex. pacote pago da brapi, ou entitlement de dado de
opções na própria corretora/MT5) ou um parceiro de dados B3. O que o
terminal MT5 já expõe de graça (metadado de strike/vencimento, ticks
esparsos) é real mas não suficiente: 3,6 negócios/dia numa série não dá pra
nem ESTIMAR vol implícita com confiança, quanto mais operar.

Enquanto isso não existir, qualquer rota sem opções (a/b/c acima) **é
resseguimento do que já foi testado**, não uma categoria nova — (b) é a
Fase 1/2 com um dial a mais sobre um edge que já deu 0, e (c) já tem nome e
já foi medido (ORB). Não vale a pena nem como "geração extra": a busca de
25 gerações já cobriu o espaço direcional; adicionar um multiplicador de
tamanho por vol prevista não muda o resultado de uma aposta sem direção.
