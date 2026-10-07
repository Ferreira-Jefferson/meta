# Raschke.mq5 — estratégias de Linda Raschke (Street Smarts, 1995)

Código: `scripts/raschke/nucleo.py` (referência, testado) ↔ `mt5/Raschke.mq5` (EA). Cada regra é uma função com o mesmo nome nos dois lados. Um setup por instância (input `Setup`).

## Fonte das regras
O site lindaraschke.net não publica regras. As regras vêm do **texto integral do livro** (caps. 3–10), cruzadas com mql5.com/en/articles/2785 (80-20), 2825 (Pinball), investingpaths.com (Holy Grail/3-10) e TradingView (3-10). Onde o livro é ambíguo, a escolha virou **parâmetro** da varredura.

| Setup | Regra implementada | Ambiguidade → escolha |
|---|---|---|
| Holy Grail | ADX14>30; recuo à EMA20 (primeiro toque); buy stop na máxima da barra que tocou; stop na mínima do recuo; alvo = swing high 20 | "ADX subindo": `toque` (ADX[i]>min) ou `inicial` (pico recente subindo). Direção = inclinação da EMA20 (o livro não usa +DI/-DI). "Trigger line" **não existe** no livro. |
| Turtle Soup | nova mínima de 20 barras, anterior com ≥4 barras de idade; buy stop em L+folga; stop 1 tick abaixo da mínima de hoje | folga em fração do ATR (livro: 5–10 ticks, de 1995); validade da ordem em barras |
| Turtle Soup Plus One | idem, idade ≥3, fechamento ≤ L, buy stop exato em L na barra seguinte | stop usa a mínima do dia 1 (a do dia 2 é futuro no momento da ordem) |
| 80-20 | pregão anterior abre nos 20% superiores e fecha nos 20% inferiores ⇒ compra no dia: perfura a mínima de ontem (5–15 ticks) e buy stop NA mínima de ontem | o texto do livro se contradiz entre parágrafo e regra numerada; usei a regra numerada. Só intraday. |
| Momentum Pinball | RSI(3) do ROC(1) <30 / >70 no fechamento diário; buy stop acima da máxima da 1ª hora do dia seguinte; stop na mínima da 1ª hora; carrega overnight se no lucro | Wilder vs SMA no RSI (usei Wilder). Em base diária (sem 1ª hora): variante `PinD`. |
| Anti | estocástico %K7 suav.4 (rápida), %D10 (lenta): lenta com inclinação, rápida recua e vira (hook) ⇒ buy stop 1 tick acima da máxima; stop no swing do recuo | o livro usa estocástico; o par SMA3−SMA10/SMA16 (`Anti310`) é interpretação de blogs |

**Premissa:** os gatilhos são ordens-STOP (rompimento) — isso é o próprio setup. O desenho "nunca a mercado" do CLAUDE.md não se aplica sem mudar a estratégia; a ordem stop só é enviada se o preço ainda não passou do nível.

## Convenções do simulador (conservadoras, com testes)
compra stop enche em max(open, nível)+1 tick; stop sai em min(open, stop)−1 tick; stop vence alvo na mesma barra e vale na barra da entrada; alvo (limite) só enche se o preço passar 1 tick além; saída a mercado paga 1 tick; custos: WIN/WDO R$0,50 por contrato, ações 0,035%/lado.

## Como comprovar no MT5
1. Compile `Raschke.mq5` (já compila: 0 erros).
2. Paridade de sinais: no Testador rode o EA em WINV26 (H1, 2026.06.01–2026.10.01, `LogSinais=true`, `Setup=ANTI`, `AntiRecuo=1`, `TickSize=5`) e compare as linhas `SINAL …` do Journal com
   `python -m scripts.raschke.paridade WINV26 H1 ANTI "modo=stoch;recuo=1" 2026.06.01 2026.10.01`.
   Diferenças pequenas na 1ª semana são esperadas (aquecimento dos indicadores).
3. Os símbolos `@D` não negociam no Testador (trade_mode 0); a série de 5 anos só existe como dado em Python.
