# WinVolumeRazao — volume relativo do WIN

Indicador MT5 (`mt5/WinVolumeRazao.mq5`). Mostra, vela a vela, **quanto o volume está acima ou abaixo do normal para aquele dia da semana e horário**.

## 1. O que é

O volume intradiário do WIN tem formato de "U": alto na abertura e no fechamento, baixo no almoço. Por isso o volume bruto de uma vela não diz nada sozinho — 150 mil contratos às 17:00 podem ser normais, e os mesmos 150 mil às 12:30 podem ser enormes. Comparar com as velas vizinhas também engana, porque os vizinhos estão no mesmo trecho do "U".

O indicador tira essa sazonalidade. Cada vela é comparada com **a mesma hora do mesmo dia da semana** nas semanas anteriores:

```
razão = volume da vela ÷ mediana ponderada do volume da mesma hora, nas últimas N ocorrências do mesmo dia da semana
```

- Quarta-feira, 11:50 é comparada com as 11:50 das últimas quartas. Segunda com segundas, e assim por diante.
- **N = `Dias`** (padrão 20 → 20 semanas ≈ 5 meses).
- **Mediana ponderada pela recência:** o pregão de k semanas atrás pesa `0,5^(k / MeiaVida)`. Com `MeiaVida = 4` (padrão), o de 4 semanas atrás vale metade do da semana passada. A mediana continua ignorando dia fora da curva (rolagem, notícia), mas acompanha melhor o nível recente do volume. `MeiaVida = 0` volta à mediana comum.
- Semana sem pregão naquele dia (feriado) ou sem volume naquele horário é pulada; ele continua voltando até achar N válidas.
- Se o histórico do gráfico não tem N semanas, a vela fica **vazia** e aparece um aviso laranja pequeno no canto da janela.
- `1,00` = volume igual ao normal para aquele dia/horário. `1,30` = 30% acima. `0,60` = 40% abaixo.

Funciona em qualquer tempo gráfico (compara velas do mesmo tempo gráfico em que está). Use uma série contínua com os 5 anos de histórico (`WIN$D` ou `WIN@D` — são idênticas em volume e preço, medido em 138.610 barras M5), nunca um contrato individual como `WINV26`, que tem poucos meses.

## 2. Como aparece no gráfico

Janela separada, abaixo do preço, com um histograma e **três linhas horizontais**:

| Elemento | Padrão | Significado |
|---|---|---|
| Linha prata (sólida) | 1,00 | Equilíbrio: volume normal para o dia/horário |
| Linha vermelha (tracejada) | 0,65 em M5 · 0,55 em M1 | Abaixo dela: volume baixo |
| Linha verde (tracejada) | 1,45 em M5 · 1,75 em M1 | Acima dela: sobre-volume |

Cada barra tem a cor da faixa em que cai:

| Faixa da razão | Cor padrão | Leitura |
|---|---|---|
| ≥ linha verde | **verde** | sobre-volume |
| de 1,00 até a verde | azul-acinzentado | acima do normal |
| da vermelha até 1,00 | amarelo-mostarda | abaixo do normal |
| < linha vermelha | **vermelho** | volume baixo |

As duas cores do meio são opacas de propósito, para o verde e o vermelho se destacarem. Todas as cores, espessura e estilo das linhas e os três níveis são parâmetros. Deixar `NivelBaixo` e `NivelAlto` em **0** usa os valores automáticos por tempo gráfico acima; digitar outro número usa o seu.

O nome do indicador mostra os valores em uso: `Volume / mediana do dia da semana e horario (20 sem, meia-vida 4) [0.65 | 1.45]`. A vela ainda em formação aparece baixa no começo, porque o volume dela ainda está se acumulando.

## 3. O que ele responde — e o que não responde

**Responde:** o mercado está mais ou menos agitado do que o normal para este momento?

**Não responde:** direção; se o movimento está no começo ou no fim; por que o volume subiu (notícia, rolagem, leilão).

### Tabela de leitura (preço × volume)

Combine a cor da barra com o que o preço fez na mesma vela. É interpretação, **não foi testada** como regra de entrada:

| Preço na vela | Volume | Leitura possível |
|---|---|---|
| Vela grande, rompendo | verde | convicção, mais gente entrando |
| Vela pequena, sem sair do lugar | verde | disputa: uma ponta absorvendo a outra |
| Vela grande | vermelho | movimento sem participação, mais fácil de reverter |
| Vela pequena | vermelho | mercado sem interesse, lateral |

## 4. O que se mediu (WIN, 2026)

Bateria feita com 4 estudos independentes. **Ajuste** (escolha de parâmetros) em jun/jul/ago de 2026; **teste** (só confirma) em abr/mai/set de 2026; **validação final** em meses reservados que nenhum estudo tocou (jan–mar/2026 e set–dez/2025). Intervalos por bootstrap de dias; comparações com nulo embaralhado.

> **Nota de versão:** os estudos 4.1 a 4.3 foram feitos com a razão de 2 semanas (a versão inicial); os de volatilidade e filtro também foram repetidos com 4, 10 e 20 semanas (conclusões iguais). As tabelas de faixa **não foram refeitas** com o estimador final da seção 4.4. A correlação com a volatilidade foi medida de novo com ele.

### 4.1 O que ele rastreia: volatilidade, sim; direção, não

Range da próxima vela, relativo ao normal do horário (1,00 = normal), por faixa da razão:

| Razão | Ajuste | Teste |
|---|---|---|
| < 0,7 | 0,96 | 0,91 |
| 0,7 a 1,0 | 1,05 | 0,99 |
| 1,0 a 1,5 | 1,11 | 1,08 |
| ≥ 1,5 | 1,28 | 1,28 |

- Crescimento monotônico e estável do ajuste ao teste: **~30% mais range** da faixa mais baixa para a mais alta.
- Correlação (Spearman) com o range da próxima vela: **0,36 no teste e 0,33 em 32 meses de 2022–2025** com o estimador escolhido. Muito acima do nulo (≈ 0).
- **Direção:** em todas as faixas, tamanhos de corpo e horizontes (1, 3 e 6 velas), os intervalos cruzam o zero e os sinais trocam entre ajuste e teste. Indistinguível de ruído.

### 4.2 Não serve de filtro para a estratégia WIN

Na estratégia WIN (vela inteira fora da WMA 34 + SMMA 34 do lado oposto), o resultado por faixa de razão na vela do sinal **inverte de sinal entre ajuste e teste** (a faixa de volume baixo foi a melhor no ajuste, +R$ 2,3/op, e a pior no teste, −R$ 5,6/op). Foram varridas 748 combinações de `Dias` e níveis, cada uma comparada com filtros aleatórios do mesmo tamanho: nenhuma se sustentou. O ganho aparente de drawdown vem de operar menos, e um filtro aleatório do mesmo tamanho dá o mesmo.

### 4.3 Não detecta "fim de movimento" nem clímax

Hipótese testada: entrada no fim do movimento é armadilha, e sobre-volume depois de movimento esticado é clímax/exaustão. Com três medidas de "esticado" (distância à roxa, velas seguidas do mesmo lado, retorno das últimas 12 velas):

- Operações esticadas **não** foram piores que as do começo, no ajuste nem no teste.
- Sobre-volume em movimento esticado: probabilidade de reversão entre 48,7% e 51,9% — moeda.

### 4.4 Qual estimador da "normalidade" (o que a razão compara)

Comparados com o mesmo protocolo (escolha no ajuste; confirmação no teste; checagem em 32 meses de 2022 a ago/2025 que nenhum estudo anterior tocou). Quanto menor `sd log` e `desvio mensal da mediana`, mais honesta é a razão; `Spearman` mede o quanto ela antecipa a volatilidade.

| Estimador (VAULT, 32 meses) | sd log | % abaixo / acima das linhas | desvio mensal da mediana | Spearman |
|---|---|---|---|---|
| mediana, 10 semanas | 0,402 | 13,8 / 20,3 | 0,081 | 0,340 |
| média, 10 semanas | 0,399 | 17,3 / 16,1 | 0,078 | 0,331 |
| média aparada, 10 semanas | 0,398 | 15,2 / 18,0 | 0,079 | 0,338 |
| geométrica ponderada, 20 sem., meia-vida 4 | 0,389 | 13,1 / 19,5 | 0,069 | 0,329 |
| **mediana ponderada, 20 sem., meia-vida 4** | 0,397 | 13,4 / 20,1 | 0,068 | 0,334 |
| mediana 10 sem. + ajuste de nível | 0,398 | 12,8 / 21,1 | 0,033 | 0,302 |

- **Nenhum estimador domina.** As diferenças de dispersão são pequenas (0,389 a 0,402). O que se separa é a *deriva de nível*.
- **Média comum:** viés para baixo (a razão fica ~5% abaixo de 1 em M5), porque o volume é assimétrico à direita, e é puxada por dia atípico. Rejeitada, como você previu.
- **Ponderar pela recência** acompanha melhor o nível do volume (desvio mensal da mediana de 0,081 → 0,068; mesma melhora no ajuste e no teste) sem sacrificar quase nada da previsão de volatilidade (0,340 → 0,334).
- **Escolhido: mediana ponderada (20 semanas, meia-vida 4).** Mantém a robustez a dia fora da curva que a mediana dá e reduz a deriva. A geométrica ponderada tem dispersão 0,008 menor, mas é menos robusta a um dia extremo; a diferença é pequena e não foi testada com intervalo.
- **Ajuste de nível foi testado e rejeitado.** Multiplicar a base pelo nível das últimas 5 sessões elimina quase toda a deriva (0,033), mas **derruba a previsão de volatilidade** (0,334 → 0,302; no teste 0,36 → 0,26). Volatilidade é agrupada: pregões recentes agitados antecipam range maior hoje. Tirar esse nível joga fora a informação que o indicador existe para dar.

### 4.5 Parâmetros escolhidos

| Parâmetro | Padrão | Por quê |
|---|---|---|
| `Dias` | **20** | Janela maior com pesos que decaem: as semanas antigas contam pouco, mas ajudam a mediana a ignorar dia atípico. Custa ~5 meses de histórico no início do gráfico. |
| `MeiaVida` | **4** semanas | Melhor equilíbrio entre acompanhar o nível recente e não ficar ruidoso (testado 4 e 8; 4 foi melhor na calibração do ajuste e do teste). |
| Dia da semana | mantido | Desenho pedido. Medido: na qualidade da linha de base é indistinguível de usar só a hora; na previsão de volatilidade ganha da hora. |
| Níveis M5 | **0,65 / 1,45** | Percentis 15 e 85 da razão em **5 anos** (0,675 e 1,467, arredondados a 0,05). Fração de barras fora das linhas por ano, 2022–2026: 11,8–13,9% embaixo e 13,1–18,0% em cima. |
| Níveis M1 | **0,55 / 1,75** | Mesmos percentis em 5 anos (0,564 e 1,767); a M1 tem cauda mais larga. Por ano: 12,1–14,9% embaixo e 12,6–17,9% em cima. |

> Uma primeira calibração, só com jun–ago/2026, deu 0,65 / 1,35 (M5) e 0,55 / 1,65 (M1) e falhou fora desse período (até 23% das barras acima da linha verde em 2025). Calibrar na série inteira resolve; o custo é que o histórico todo entrou na calibração, então não há mais meses "virgens" para validar estes dois números. Eles são uma escala descritiva, não um parâmetro de estratégia.

## 5. Limitações (leia antes de confiar)

- **A cauda de cima varia de ano para ano.** O centro da razão é estável (mediana 0,99 a 1,01 em todos os anos), mas a fração acima da linha verde vai de 13% (2022) a 18% (2025) com os níveis atuais. É variação de dispersão, não tendência: o volume por barra caiu de 2021 a 2025 e voltou a subir em 2026. Em um mês isolado a fração oscila ±5 pontos em torno disso. Não trate uma sequência de barras verdes como evento raro sem olhar o contexto.
- **Volatilidade ≠ operabilidade.** +30% de range é efeito estatístico modesto.
- **Amostra:** 6 meses de ajuste/teste + 7 meses reservados. Efeitos pequenos podem não aparecer.
- **Virada de contrato:** a razão fica ~14% abaixo do normal nesses dias (medido em 9 dias); a mediana protege mais que a média.
- **Série contínua:** o volume da série soma mais de um contrato (≈9× o de `WINV26` nos dias medidos). A razão cancela a escala, mas a composição pode mudar perto do vencimento.
- Os valores acima são de **M5 e M1**. Outros tempos gráficos usam os níveis do M5 e não foram calibrados.

## 6. Como reproduzir

| O quê | Script |
|---|---|
| Réplica em Python do indicador | `scripts/daytrade/win_volume_razao_py.py` |
| Volume × resultado da estratégia | `scripts/daytrade/win_volume_hA_2026_10_01.py` |
| Volume × volatilidade/direção | `scripts/daytrade/win_volume_hB_2026_10_01.py` |
| Fim de movimento e clímax | `scripts/daytrade/win_volume_hC_2026_10_01.py` |
| Qualidade da linha de base e níveis | `scripts/daytrade/win_volume_hD_2026_10_01.py` |
| Comparação de estimadores (mediana, aparada, geométrica, ponderada, ajuste de nível) e o estimador do indicador (`base_grupo(d, 20, "mediana", 4)`) | `scripts/daytrade/win_volume_estimador_2026_10_01.py` |
| Padrões finais e validação nos meses reservados | `scripts/daytrade/win_volume_padroes_2026_10_01.py` |

Dados: `data/wdo-mt5/WIN@D_M5_*.csv` e `WIN@D_M1_*.csv` (baixados por `scripts/daytrade/baixa_m1_mt5_csv.py`).
