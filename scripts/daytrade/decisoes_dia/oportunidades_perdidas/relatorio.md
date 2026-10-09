# Oportunidades perdidas do robo v2 (50 dias de `dias_usados.json`)

Codigo: `motor.py` (registra toda candidata + simula isolada), `coleta.py`, `analise.py`/`analise2.py`, `top10.py`, `motor2.py` + `varre.py` (mede mudancas), `avalia*.py`. Nada existente foi editado. v2 reproduz exatamente o total dos ciclos: R$4.678,77 em 100 ops (c0 +1.423,71; c1 +2.411,95; c2 +843,11).

## 1. Por que ele nao entrou (dinheiro na mesa por causa, dedupe regra+lado+45 min)

902 candidatas brutas -> 530 grupos -> 76 excluidos (o robo entrou com a mesma regra+lado na janela) -> **454 oportunidades**. Cada uma simulada isolada (mesmo motor, entrada limitada, stop da regra, 1-2 contratos).

| causa | n | ganhariam | perderiam | na mesa (ganhadoras) R$ | evitou (perdedoras) R$ | liquido R$ |
|---|---|---|---|---|---|---|
| veto (NAO_FAZER do mesmo lado) | 164 | 79 | 80 | +9.890 | -5.406 | **+4.484** |
| posicao ja aberta, mesmo lado (piramide) | 173 | 101 | 67 | +12.092 | -4.118 | **+7.975** |
| posicao ja aberta, lado oposto | 48 | 17 | 31 | +1.015 | -1.741 | -726 |
| FAZER nos dois lados (nao entra) | 48 | 16 | 31 | +1.491 | -2.065 | -573 |
| teto de 3 ops | 21 | 12 | 9 | +1.210 | -504 | +707 |
| **total** | 454 | 225 | 219 | +25.7k | -13.8k | +11.865 |

Leitura honesta:
- **Nao sao somaveis.** As 221 de "posicao aberta" so existiriam com 2+ posicoes simultaneas; as de veto se sobrepoem no tempo. O numero que vale e o medido no motor (secao 4).
- **O +R$4.386 de `vende_rompimento_stop_curto` era contagem repetida da mesma entrada em velas seguidas.** Dedupe: 25 oportunidades em 14 dias, **+R$398**. Os +6.057 (c1) e +2.270 (c2) de vetos viram **+2.836 e +727** (70 e 64 oportunidades); ciclos 0+1+2: +4.484.
- O que o robo deixou de ganhar esta quase todo em **dias bons**: bloqueadas em bons +11.158, c0 +4.464, **ruins -3.756** (197 oportunidades: 68 ganhariam, 126 perderiam). O veto nao esta errado em media; erra nos dias direcionais.
- Veto de compra custou mais que o de venda: compra +3.438 (61 opp, 61% ganham), venda +1.046 (103 opp, 41% ganham).
- Vetos que mais deixaram na mesa (dedupe): `compra rompimento com alvo menor` (2023_11_03) +1.345; `N3 comprar rompimento da manha` +1.144; `N1 comprar rompimento da 1a hora` +884; `compra_queda_1atr` +732; `vender_quebra_minima_cedo` +726.

## 2. O que separa ganhadoras de perdedoras (so estado observavel no instante)

AUC = P(ganhadora tem valor maior que perdedora); 0,5 = nada. "desloc" = (fechamento - abertura do dia) / ATR15, com sinal a favor do lado. Tercis = liquido R$ (e % de ganhadoras) do tercil baixo | medio | alto.

| variavel | veto: med gan / perd | AUC | tercis (baixo/medio/alto) |
|---|---|---|---|
| **deslocamento vs abertura (ATR, a favor)** | 2,28 / 1,59 | **0,64** | -347 (36%) / +1.013 (51%) / +3.818 (62%) |
| eficiencia do dia ate ali | 0,25 / 0,21 | 0,59 | +322 (47%) / +486 (43%) / +3.674 (58%) |
| regime da manha (ef ate 12h) | 0,25 / 0,22 | 0,58 | -5 / +621 / +3.868 (60%) |
| forca da perna (8 barras, ATR) | 1,25 / 0,87 | 0,58 | +7 / +1.572 / +2.903 |
| dist. VWAP (ATR, a favor) | 0,93 / 1,01 | 0,54 | sem ordem |
| vol recente/ATR15 | 1,09 / 1,16 | 0,48 | sem ordem |
| volume relativo | 1,38 / 1,75 | 0,49 | sem ordem |
| hora | 10,75 / 11,25 | 0,41 | manha melhor (+3.662, 56%) que 11-13h (-447, 41%) |

- Na posicao aberta (mesmo lado) a separacao e mais forte: AUC ef_dia 0,71, ef_manha 0,70; tercil alto de ef_manha +5.671 (85% ganham) contra +469 (45%).
- Nos "dois lados": o lado a favor do deslocamento ganha (AUC 0,75, tercil alto +443, 62%); o contra perde (19-20%).
- **Algo separa, mas fraco e instavel:** desloc AUC 0,68 em ciclos 0+1 e 0,59 no ciclo 2. Volatilidade, volume e VWAP nao separam. Tudo isso e correlato do tipo de dia (direcional), que so se confirma depois.

## 3. Teto realista por dia (hindsight, entrada limitada no fechamento da M15, stop <= R$120/600 pts, 1 contrato)

Para cada instante e lado: ordem limitada, saida no melhor extremo antes do stop de 600 pts; programacao dinamica de ate k ops sem sobreposicao.

| | robo v2 | teto 1 op | teto 3 ops | sem limite |
|---|---|---|---|---|
| 50 dias, R$ | 4.679 | 21.615 | 31.700 | 37.506 |
| captura (robo/teto 3) | | | **14,8%** | |
| bons / ruins / c0 | 3.149 / 106 / 1.424 | | 13.458 / 11.719 / 6.523 | |

(Teto e limite superior com visao do futuro, nao meta. O ponto util: nos dias ruins o teto e alto (11.719) e o robo captura 1%; nos bons captura 23%.)

Top 10 dias por dinheiro na mesa (teto3 - robo):

| dia | tipo | robo | teto3 | falta | por que |
|---|---|---|---|---|---|
| 2025-04-07 | ruim | -118 | 1.965 | 2.083 | dia de 4.800 pts; melhor era comprar 10:45 (+907); **nenhuma FAZER de compra**; robo vendeu e perdeu |
| 2022-05-24 | ruim | -283 | 794 | 1.077 | compra 12:00 ate 17:49 (+422); sem sinal de compra; 3 ops (1 compra, 2 vendas) todas stop |
| 2022-10-21 | bom | +55 | 1.019 | 964 | compra 09:45 ate 16:24 (+843); robo so entrou 14:00 e saiu no alvo curto +55 (entrada tardia + alvo fixo) |
| 2022-11-29 | c0 | -30 | 925 | 955 | compra 10:15-13:32 (+569); robo vendeu 10:45 (-71); comprou 12:45 (+104 no alvo) |
| 2023-12-13 | bom | +51 | 916 | 865 | compra 09:15-18:24 (+775); robo vendeu 10:00 (-60), comprou so 14:17 (+111 no alvo) |
| 2025-08-01 | c0 | +317 | 1.136 | 819 | compra 09:15 (+542); robo comprou certo mas saiu em +170 no alvo |
| 2023-10-17 | ruim | -131 | 656 | 787 | 3 ops, stops; a compra boa (+266) nao veio |
| 2024-12-12 | bom | +175 | 898 | 723 | venda 09:15-16:41 (+670); robo so vendeu 13:15 (+175); R$1.174 de oportunidades bloqueadas no dia |
| 2025-05-30 | ruim | +79 | 768 | 689 | venda 09:30-13:30 (+445); sem FAZER; entrou so 15:45; R$614 de bloqueadas |
| 2022-09-14 | ruim | +3 | 669 | 666 | compra 10:15 (+266); sem FAZER de compra; robo vendeu 12:30 e saiu no fim (+3) |

Padroes: (i) **sem sinal no lado certo** em 4 dos 10; (ii) **entrada tardia** (so entra depois do movimento) em 4; (iii) **alvo fixo curto** (1 ATR) deixa a perna correr em 4 (2022-10-21, 2023-12-13, 2025-08-01, 2022-11-29). Vetos pesam so em 2024-12-12 e 2025-05-30.

## 4. Mudancas propostas, medidas no robo v2 (`motor2.py`, 50 dias)

Protocolo: configuracao escolhida no melhor de ciclos 0+1 (30 dias), verificada no ciclo 2 (20 dias), mais leave-one-day-out (LODO). ~50 configuracoes testadas (multiplas comparacoes: o piso de ruido e alto). Todas com o robo v2 identico, so a mudanca indicada. Delta em R$ sobre o v2 (4.679).

**(a) Veto condicional (veto so age quando o estado indica perda).**

| mudanca | delta 50 | delta c0+1 | delta c2 | dias melhores / piores | pior dia | delta bom / ruim |
|---|---|---|---|---|---|---|
| veto desligado | +1.501 | +1.366 | +135 | 26 / 24 | -348 | +1.334 / -498 |
| **veto so vale se desloc < 0** (dia andando contra o lado) | **+1.977** | **+1.617** | +360 | 27 / 20 | -348 | +2.148 / -790 |
| veto so vale se desloc < 1 | +1.610 | +1.122 | +488 | 24 / 20 | -356 | +2.034 / -538 |
| veto so vale se ef_dia < 0,20 | +1.633 | +2.024 | **-391** | 18 / 17 | -356 | +1.484 / -489 |
| veto so vale na venda (compra liberada) | +1.864 | +1.468 | +396 | 17 / 13 | -283 | +2.052 / -697 |
| veto solto se desloc>=1 E ef_dia>=0,35 | +1.174 | +1.311 | -137 | | -283 | +1.404 / -177 |

Selecao em 0+1 escolhe "desloc<0" (+1.617) -> no c2 +360 (positivo). LODO (escolhe entre todas nos 49 dias): +570 (sai +1.977 -> +570: o ganho concentra-se em ~5 dias: 2023-04-11 +468, 2023-11-03 +385, 2025-06-06 +322, 2022-09-19 +322, 2022-10-21 +316; piores: 2025-01-22 -323, 2025-08-01 -286).

**(b) Mudancas estruturais.**

| mudanca | delta 50 | delta c0+1 | delta c2 | melhor / pior | pior dia | delta bom / ruim |
|---|---|---|---|---|---|---|
| teto dinamico 4/5 ops se saldo>0 (e ultimo ganhou) | +66 | +66 | 0 | 1 / 0 | -283 | +66 / 0 |
| cascata (tenta a proxima candidata) | 0 | 0 | 0 | 0 / 0 | -283 | 0 / 0 |
| dois lados: segue o lado a favor do deslocamento | +28 | 0 | +28 | 2 / 3 | -283 | +66 / -38 |
| piramide: 2a posicao mesmo lado se 1a no lucro (maxc=2) | +216 | +688 | **-472** | 13 / 9 | -283 | -162 / -135 |
| piramide so se lucro >= 0,5 ATR e desloc >= 1 | +476 | +254 | +222 | 4 / 3 | -283 | +332 / -148 |
| **alvo x1,5 se desloc >= 1 ATR** | **+598** | +293 | +305 | 18 / 10 | -283 | **+748 / +24** |
| alvo x2 se desloc >= 1,5 | +674 | +546 | +128 | 13 / 12 | -283 | +1.179 / -242 |

O teto de 3 ops e a cascata quase nao mudam nada (so 21 oportunidades; a cascata nunca encontrou segunda candidata). Piramide e a unica mudanca que captura o grande bolo de "posicao aberta", mas dobra a exposicao (R$240 de risco) e no c2 piora quando liberada sem filtro.

**Combinacoes (empilhadas; definidas depois de ver os 50 dias, entao otimistas):**

| combinacao | delta 50 | c0+1 | c2 | melhor/pior | pior dia | ops | DD cron. | delta bom / ruim |
|---|---|---|---|---|---|---|---|---|
| veto desloc<0 + teto5 + piramide a favor | +4.747 | +4.102 | +645 | 29 / 21 | -348 | 177 | 471 | +4.999 / -1.181 |
| + dois lados + piramide 0,5 ATR | +5.039 | +4.217 | +822 | 29 / 21 | -348 | 171 | 471 | +5.352 / -1.241 |
| veto desloc<0 + alvo x1,5 (desloc>=1) | +3.119 | +2.232 | +887 | 31 / 18 | -348 | 118 | | +3.312 / -496 |
| pilha com "dia direcional" (desloc>=1 e ef>=0,35) | +3.130 | +2.790 | +340 | | -283 | | | +3.440 / -236 |

**Aviso decisivo (reponderacao).** A amostra e estratificada: 20 bons + 20 ruins + 10 sorteados. Dias bons (ef>=0,25) sao ~5% do periodo IS (so ~16 sobravam alem dos usados), ruins (<0,15) ~80%. Todas as mudancas acima ganham nos bons e **perdem nos ruins** (v2 so faz +R$5/dia nos ruins). Reponderando 5% bom / 95% ruim: veto desloc<0 = **-R$32/dia**; veto desligado -R$20; pilha completa -R$44 a -R$49; so ficam ~neutras **alvo x1,5 com desloc>=1 (+R$3/dia; bom +748, ruim +24, c0 -174)** e pilha direcional estrita (-R$2,6/dia). Ou seja: **os ganhos de +R$2 a 5 mil dos 50 dias sao em grande parte efeito de ter 40 dos 50 dias escolhidos por serem direcionais; no calendario real nao se confirmam.** Nenhuma variavel instantanea (AUC <= 0,68) identifica dia direcional cedo o bastante.

## 5. Recomendacao para o robo do ciclo 3

1. Resposta ao dono: ele nao entrou porque (i) **veto** bloqueou, mas dedupe reduz o "R$4 mil" a ~R$0,4 mil (`vende_rompimento_stop_curto`) e o total de vetos a +R$4,5 mil, concentrado em dias bons; (ii) o grande bolo (+R$8 mil) era **sinal com posicao ja aberta**, que exigiria piramide; (iii) 4 dos 10 maiores dias nao tinham nenhuma regra FAZER no lado certo. Para ter entrado ele teria que: soltar vetos so quando o dia anda a favor, somar segunda posicao, e ter FAZER para continuidade de dia direcional (hoje o repertorio e de fade/reversao).
2. **Nao** adotar veto desligado/condicional nem piramide como regra geral: ganham so em dia direcional e no calendario real perdem. LODO tambem encolhe o ganho de +1.977 para +570.
3. **Candidata pre-registravel para o ciclo 3:** `alvo x1,5 quando desloc >= 1 ATR` (unica mudanca isolada positiva nos bons e nos ruins, em c0+1 (+293) e em c2 (+305); pior dia inalterado; custo: c0 -174 em 10 dias, n pequeno). Medir em 20 dias sorteados SEM estratificar (calendario real) para checar o efeito populacional.
4. Segunda linha a testar (hipotese, nao adotar): piramide so com `lucro >= 0,5 ATR`, `desloc >= 1` e `ef_dia >= 0,35` (+3.130 nos 50; -R$236 nos ruins).
5. Maior alavanca estrutural nao testada aqui: **novas regras de continuidade/entrada precoce** (compra/venda no 09:15-10:45 a favor do deslocamento) para os 4 dias "sem sinal" e as 4 "entradas tardias".
