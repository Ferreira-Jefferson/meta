# Composição de velas (cor, corpo, volume) em M1/M5/M15 e a direção da próxima pernada — WIN 2026

Scripts, tabelas e CSVs em `rodada4/composicao_velas/` (`core.py`, `sims.py`, `analise.py`, `congela.py`, `conf.py`, `pos.py`; `descoberta.csv`, `regras_congeladas.csv`, `confirmacao.csv`). Só 2026 (WIN@D M1 contínuo). Descoberta jan–jun (125 pregões), confirmação jul–ago, set só referência.

## Veredito

Contagem de velas de compra × venda, sozinha, **não prevê a direção** da pernada de 750+ nem o movimento de 30/60 min: nenhuma das variantes de cor/corpo/volume em u30/u60 passou |z|>3 na descoberta. O único resíduo é de curtíssimo prazo e escala 250 pts: o saldo líquido das últimas 10 velas M1 (saldo de corpos, deslocamento líquido, posição do fechamento) tende a continuar por +250 antes de −250. Confirmou em jul–ago e em set, mas é **instável por mês** (zero ou invertido em abr–jun) e não aparece em 30/60 min na descoberta. Status: **parcial / fraco**.

## Método

- Amostras: fim de cada M15, 09:30–16:45 (cerca de 30 por pregão; 5.610 linhas em 2026). Só informação até o fechamento da vela-sinal. Lateral = |deslocamento 60 min| / range 60 min < 0,25 (28% das amostras).
- Features sobre as últimas k velas: fração de alta menos baixa (`frac`), saldo de corpo / soma |corpo| (`corpo`), o mesmo ponderado por volume (`vol`), posição média do fechamento na vela menos 0,5 (`cpos`), saldo de corpos / soma de ranges (`sal`), deslocamento líquido / soma de ranges (`net`, eficiência assinada). Janelas: M1 k=10/20/30/60; M5 k=6/12/24 (30/60/120 min); M15 k=4/8 (60/120 min): 54 features. Cruzadas M1−M15 e M5−M15 na mesma janela (divergência): 4. Picos (vela com volume ou range que explode num tempo e não aparece no outro; sinal = cor da vela): 4. Total 62.
- Resultados: u30, u60 (fechamento 30/60 min depois > fechamento do sinal), h250 e h750 (+250/+750 antes de −250/−750 usando máxima/mínima das velas seguintes; vela que toca os dois lados é descartada). Estatística: D = P(alta | quintil superior da feature) − P(alta | quintil inferior), cortes por feature × condição × faixa horária (<11h, 11–14h, >14h) congelados da descoberta real. D>0 = maioria segue; D<0 = contra.
- Condições: todas, lateral, não lateral.
- Nulo: 150 simulações com velas M1 embaralhadas em blocos de 30 min (forma, retorno e volume; reencadeadas), com features e resultados recalculados. **Esse nulo tem média negativa** (D ≈ −0,03 a −0,04 em h250/u30), porque o bloco conserva o saldo (mais alta antes, menos alta depois, dentro do bloco). Logo o z contra o nulo (`z`) é inflado em cerca de +1; reporto também `z0` = D / desvio do nulo (centrado em 0). Nulo binomial não foi usado.

## Nº de testes

- Descoberta: 696 células válidas (62 features × 3 condições × 4 resultados, menos células com n<30 por lado). |z|>2: 123 (ao acaso: ~32; o viés do nulo explica boa parte); |z|>3: 19. Média de D por resultado: h250 +0,010; h750 +0,007; u30 −0,010; u60 +0,012. Por condição: todas +0,003, lateral +0,018, não lateral −0,007.
- Congeladas (|z|>3 na descoberta): 19 regras, escritas em `regras_congeladas.csv` antes de abrir a confirmação. Confirmação: 19 (jul–ago) + 19 (set).
- Pós-hoc, sem valor de confirmação: ~36 leituras (u30/u60/h750, meses, faixa horária, bootstrap) nas 3 regras que sobraram.
- Total aproximado: 770.

## Descoberta — 10 maiores |z| (jan–jun)

| feature | cond | res | n topo/base | P topo % | P base % | D | nulo D | z | z0 |
|---|---|---|---|---|---|---|---|---|---|
| net_1m_10 | lateral | h250 | 184/184 | 55,6 | 37,4 | +0,182 | −0,042 | 4,7 | 3,8 |
| sal_1m_10 | lateral | h250 | 184/184 | 55,6 | 39,1 | +0,165 | −0,042 | 4,4 | 3,5 |
| corpo_1m_10 | lateral | h250 | 185/184 | 55,1 | 38,8 | +0,163 | −0,044 | 4,4 | 3,4 |
| cpos_1m_10 | todas | h250 | 731/731 | 52,2 | 48,2 | +0,040 | −0,045 | 3,8 | 1,7 |
| sal_1m_10 | todas | h250 | 731/731 | 51,4 | 46,9 | +0,045 | −0,028 | 3,7 | 2,3 |
| corpo_5m_12 | todas | h250 | 682/682 | 52,4 | 47,7 | +0,047 | −0,031 | 3,5 | 2,1 |
| net_1m_10 | todas | h250 | 731/731 | 51,3 | 47,3 | +0,040 | −0,028 | 3,4 | 2,0 |
| frac_1m_10 | lateral | h250 | 312/295 | 52,4 | 44,1 | +0,083 | −0,043 | 3,4 | 2,2 |
| cpos_5m_6 | todas | h250 | 731/731 | 50,6 | 47,4 | +0,033 | −0,036 | 3,2 | 1,5 |
| net_1m_10 | lateral | h750 | 184/184 | 57,9 | 42,0 | +0,159 | −0,009 | 3,1 | 2,9 |

Lista congelada completa (19) em `regras_congeladas.csv`: todas de continuação (D>0); 16 em h250, 2 em h750, 1 em u60; M1 k=10 domina.

## Confirmação, lado a lado (regras e cortes congelados)

| regra (feature, condição, resultado) | desc. D | conf. D (jul–ago) | conf. P topo/base % | conf. n | z0 conf | set D |
|---|---|---|---|---|---|---|
| net_1m_10, todas, h250 | +0,040 | **+0,122** | 55,5/43,3 | 245/261 | 3,3 | +0,168 |
| sal_1m_10, todas, h250 | +0,045 | **+0,138** | 56,3/42,5 | 253/264 | 3,8 | +0,130 |
| cpos_1m_10, todas, h250 | +0,040 | **+0,119** | 52,5/40,6 | 229/237 | 3,0 | +0,065 |
| corpo_1m_20, não lateral, h250 | +0,039 | +0,156 | 55,2/39,6 | 199/168 | 3,4 | +0,015 |
| corpo_5m_12, todas, h250 | +0,047 | +0,137 | 55,4/41,7 | 257/260 | 3,8 | +0,018 |
| sal_5m_24, não lateral, h250 | +0,048 | +0,160 | 59,4/43,4 | 162/171 | 4,0 | +0,068 |
| net_1m_30, todas, h250 | +0,025 | +0,046 | 50,0/45,4 | 285/270 | 1,4 | −0,004 |
| cpos/sal/net M5 k=6, todas, h250 | +0,03 | +0,04 | cerca de 49/46 | cerca de 280 | 0,8–1,2 | cerca de 0 |
| frac_1m_10, lateral, h250 | +0,083 | **−0,014** | 45,9/47,3 | 103/111 | −0,2 | +0,073 |
| corpo/sal/net/vol M1 k=10, lateral, h250 | +0,12 a +0,18 | +0,07 a +0,08 | 51/44 | 45–58/66–74 | 0,8–1,0 | n insuf. |
| cpos_5m_6, lateral, u60 e h250 | +0,151 / +0,127 | **−0,103 / −0,068** | | 69/80 | <0 | — |

Resumo: sinal igual em 14 de 19; D>0 com z0>1,65 em 6 de 19; correlação de D entre descoberta e confirmação nas 664 células: −0,03. As regras "lateral" (maior D na descoberta, n≈184 por lado) encolheram para +0,07 e as de lateral M5 inverteram. O h750 ficou sem n suficiente na confirmação (<30 por lado). As colunas de z contra o nulo estão em `confirmacao.csv`.

## As 3 regras que sobraram (pós-hoc)

`net`, `sal` e `cpos` em M1 k=10, todas as condições, resultado h250. Exemplo `net_1m_10`:

| resultado | D jan–jun | D jul–ago | D set |
|---|---|---|---|
| h250 | +0,040 | +0,122 | +0,168 |
| u30 | −0,041 | +0,034 | +0,117 |
| u60 | +0,013 | +0,085 | +0,053 |
| h750 | +0,012 | +0,177 | +0,085 |

- Por mês (D em h250, net_1m_10): jan +0,20; fev +0,11; mar +0,05; abr +0,01; **mai −0,02; jun −0,08**; jul +0,12; ago +0,11; set +0,17. Sete de nove positivos; abr–jun sem efeito ou invertido.
- Por faixa horária: +0,10 (09:30–11h), +0,05 (11–14h), +0,08 (>14h). Não é só relógio.
- jan–ago, IC95 por bootstrap de pregões do D em h250: [+0,02; +0,10] (net), [+0,02; +0,11] (sal), [+0,02; +0,10] (cpos).
- Retorno a favor em 60 min (comprar topo, vender base), pts por mês: jan +80, fev +60, mar +70, abr −74, mai −17, jun −62, jul +39, ago +79, set +39.
- Uso prático: comprar o topo e vender a base do quintil com saída em ±250 dá acerto cerca de 53% em jan–ago (cerca de 56% em jul–ago), ou seja, cerca de +15 pts por trade antes de custo (cerca de R$3 por contrato). Pequeno e dependente de regime.
- O mesmo saldo em 30–60 min (k=30/60) ou em M5/M15 perde força: é microtendência de uns 10 minutos.

## Cruzamento de tempos (M1 × M5 × M15)

- Correlação entre contagens de cor: `frac` M1(30)×M5(6) 0,63; M1(60)×M15(4) 0,56; M5(12)×M15(4) 0,67. Corpos ponderados M1(30)×M5(6) 0,96 (praticamente a mesma coisa). Os tempos maiores trazem pouca informação nova.
- Divergência M1(60) × M15(4), jan–ago (base: P(alta 60 min) 48,7%; P(+250 antes de −250) 49,1%): M1 alta e M15 baixa, n=164, 44,0% e 51,9%; M1 baixa e M15 alta, n=132, 50,9% e 49,6%; ambos alta, n=827, 50,4% e 50,7%; ambos baixa, n=885, 43,7% e 46,8%. Nenhuma das 4 features cruzadas passou |z|>3.
- Picos (volume ou range que aparece num tempo e não no outro): nenhuma das 4 variantes passou |z|>3.

## Falharam

As outras 677 células da descoberta e as regras de lateral na confirmação. Em especial: contagem de cor em M1/M5/M15 (10 a 120 min) em u30/u60; ponderação por volume; fração de alta em lateralização (D lateral +0,083 → −0,014); posição do fechamento e saldo em M5 lateral (invertido); divergências entre tempos; picos.

## Limites

- Amostras a cada 15 min se sobrepõem nos resultados h250/h750; a dependência só é reproduzida na medida em que o embaralhado a reproduz.
- O nulo em blocos de 30 min tem D médio negativo; o z contra ele superestima. A leitura segura é D contra 0 com o desvio do nulo (z0) e o IC por pregões.
- h250/h750 medem o preço, não "a próxima pernada de 750 em zigzag"; o zigzag completo não foi recalculado por amostra. Máxima/mínima por vela, sem ordenar dentro da vela (empate descartado).
- Janelas M15 k=4/8 só existem a partir de 10:30/11:30.
