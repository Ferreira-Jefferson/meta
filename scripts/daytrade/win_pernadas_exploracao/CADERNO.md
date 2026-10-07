# Caderno de regras candidatas — pernadas do WIN

> **Status atualizado em `REGRAS.md` (rodada 3, replicação em jan–ago/2026).** As pistas abaixo são o registro de setembro; várias de direção (P4, P11, P12, P7) não se repetiram em 2026.

Fase: **levantamento**. Nada aqui é regra fechada. Cada linha é uma pista com o número que a sustenta, o papel que ela poderia ter num robô e o que falta para virar regra.

**Janela de exploração:** setembro/2026 (21 pregões, WINV26). Pernada = zigzag de 750 pts sobre o caminho da vela (vela de alta: mínima→máxima; de baixa: máxima→mínima; confere com os ticks em 86-88%).

**Nulo padrão a partir da rodada 2:** embaralhar as velas M1 dentro de blocos de 30 min de cada pregão. Preserva a volatilidade de cada horário e destrói a ordem. Um nulo que embaralha o dia inteiro superestima padrões, porque confunde horário com estrutura.

**Validação:** ainda não feita. As famílias de horário, volatilidade, gap, estrutura do dia, reversão da manhã e virada não foram medidas no histórico de 5 anos. As de correção e continuação já foram (ver "Já medido").

## Papéis

| Papel | O que faz no robô |
|---|---|
| LIGA / DESLIGA | se o robô pode operar agora |
| ACEITA / REJEITA | se um sinal específico é aceito |
| DIREÇÃO | de que lado operar |
| STOP + / STOP − | afastar ou aproximar o stop |
| ALVO + / ALVO − | aumentar ou reduzir o alvo |
| TAMANHO + / − | mais ou menos contratos |
| SAÍDA | quando encerrar antes do alvo ou do stop |

## Mapa do dia (leitura conjunta das rodadas 1 e 2)

| Faixa | O que acontece | Papel candidato |
|---|---|---|
| 09:00–10:30 | Nascem as pernadas, grandes e rápidas (todas as >3.000 pts). Movimentos de 5–15 min revertem (VR5 0,70) — provável leilão de abertura. Recuo vira pernada um pouco MENOS que o acaso | LIGA para seguir pernada |
| 10:30 | Degrau de NY: faixa/minuto 1,28× contra 0,94 nos outros horários (nenhum dos 67 cortes de controle passa) | marco de troca de regime |
| 10:30–12:30 | A manhã é devolvida: desvio >500 pts do fechamento anterior reverte em 60 min em 73%; consenso (abertura+VWAP+fechamento anterior) às 10:30 vai contra em 12/14 dias | DIREÇÃO contra o consenso; ALVO no retorno |
| 13:00–18:00 | Poucas pernadas, lentas (12–15 pts/min) e sujas. Extremos do dia já formados. Recuo de 500 pts vira pernada de 750 em 77–88% (acaso: 66%) | DESLIGA seguir pernada; SAÍDA rápida em recuo de 500 |

## Pistas

| # | Papel | Pista | Número (set/26) | Status | O que falta |
|---|---|---|---|---|---|
| P1 | LIGA/DESLIGA | **Relógio.** Pernadas nascem de manhã | Chave "hora<11h": 21% do tempo ligado, 73% das pernadas capturadas (M5); P(250→750) 20% ligada × 5% desligada. AUC da hora sozinha 0,74 (M5) / 0,78 (M15); somar volatilidade e pernada anterior não acrescenta | **pista forte, sinal único** | validar a curva de troca fora de set/26 |
| P2 | (refinamento de P1) | Volatilidade curta subindo | Bruta: correlação −0,78 com a hora (é o relógio). Sem o relógio (`rh`): +1 a +5 pp, AUC ~0,5 | **rebaixada** — era o relógio | só como refinamento, se sobreviver |
| P3 | (refinamento de P1) | Pernada anterior grande | Com nulo por horário: tamanho n não prevê n+1 (corr. 0,00 × nulo −0,01). No zigzag de 100 pts sobra +5 a +10 pp após fixar hora (n pequeno) | **rebaixada** | — |
| P4 | DIREÇÃO | Gap contra o dia | gap fecha 85% (17/20); dia termina contra o gap 70%; gap × resto do dia rho −0,37 (p 0,10) | pista (casa com estudo anterior "sobra gap contra D-1") | n=20; validar |
| P5 | DIREÇÃO | 1ª pernada indica o fechamento | 71% (H1); retorno 9–10h acerta o dia 15/21 (p 0,08), some às 10:30 | pista fraca | conflita com P11 — medir juntos |
| P6 | DESLIGA / ALVO − | Extremos do dia saem cedo | extremo do dia nas 2 primeiras pernadas H1 em 20/21; máx/mín mediana ~10:28 | pista forte (falta nulo com horário) | refazer com nulo por blocos |
| P7 | ALVO − / SAÍDA | Pernada seguinte não passa do início da anterior | **corrigida**: 42% × 48% do nulo com horário (z −2,9); razão mediana 0,88 × 0,97; some no zigzag de 500 | pista fraca | — |
| P8 | ALVO − | Pernadas encolhem ao longo do dia | 1ª H1 mediana 2.160; 4ª em diante 1.000–1.500 | provável efeito de P1 | — |
| P9 | ALVO − / TAMANHO − | Tarde: mesma pernada, 4× mais lenta, 3× mais suja | 70 → 12–15 pts/min | pista | normalizar a definição de correção |
| P10 | SAÍDA | Clímax no topo final | volume 1,16× × 1,07× (AUC 0,60); delta vira logo após o pivô | coincidente, fraca | — |
| P11 | DIREÇÃO / REJEITA | **Manhã devolvida depois das 10:30** | resto do dia contra a manhã em 14/21; com consenso das 3 leituras às 10:30, 12/14 contra (mediana 1.093 pts); desvio >500 do fechamento anterior reverte em 60 min em 73% na janela 10:30–12:30 (46–57% fora dela) | **pista forte** (3 análises por caminhos diferentes) | validar; grade tem amostras sobrepostas |
| P12 | SAÍDA / DESLIGA | **Recuo da tarde é virada** | depois das 13h, recuo de 500 vira pernada de 750 em 77% (nulo 66%, p95 74%) / 84–88% (método por ticks) | pista | n tarde 35–61 |
| P13 | (base) | Virada em tempo real = ruína do jogador | P(virar 750 \| recuou X): 18% (150), 27–32% (250), 46–49% (375), 63–66% (500); igual ao nulo; tamanho da alta, nº da tentativa e direção não mudam | **forte, negativo útil** | — |
| P14 | ACEITA / REJEITA | Nada no momento do recuo separa virada de respiro | cruzamentos de média, VWAP, RSI, divergência, volume, fluxo, pavio: AUC 0,43–0,57; 14/156 p<0,05 (acaso ~8) | negativo útil | — |
| P15 | REJEITA contra-tendência | Agressão forte a favor da pernada = continuação | mesmo sinal em topo e fundo, AUC 0,39–0,52 | fraca | — |
| P16 | ACEITA virada / ALVO + | Pernada esticada longe do VWAP vira mais | 1,43 × 1,05 ATR M5; AUC 0,55–0,62, mesmo sinal nos dois lados; pool p 0,10 | fraca, coerente com P11 | — |
| P17 | DIREÇÃO (neutra) | **Alta e baixa são simétricas** | tamanho, velocidade, correções, volume e virada iguais nos dois lados | forte, negativo útil | → mesmos parâmetros para compra e venda |
| P18 | LIGA / TAMANHO | Volatilidade vem em aglomerados | faixa de bloco de 15 min × seguinte: 0,25 (nulo ±0,08) | pista | separar regime do dia de curto prazo |
| P19 | LIGA / STOP + | Minuto cheio concentra movimento | :00 = 1,57× a média da hora (todas as horas); :30 = 1,25× | pista (parte mecânica) | — |
| P20 | REJEITA na 1ª hora | Reversão de curto prazo das 9h às 10h | VR5 0,70 (nulo 0,84–1,11); nas outras horas ~1 | pista (pode ser leilão) | — |

## Descartado em setembro (não prioritário, sem poder após controle)

- Médias móveis (9/21/50/200: distância, inclinação, compressão, cruzamentos), MACD, RSI, VWAP como gatilho, sequência de cores, posição no range, distância à máx/mín do dia e do dia anterior.
- Volume da vela anterior ao início da pernada (Spearman 0,02–0,12).
- Saldo de agressão compra/venda antes do pivô; surtos de agressão de 1 e 5 min; minuto 80/20 praticamente não existe.
- Tamanho da pernada anterior para prever a próxima; número da tentativa do recuo; deriva do dia.
- Classificar o dia (tendência × lateral) pela manhã: eficiência da manhã × do dia rho 0,02.
- Números redondos, máx/mín do dia anterior como ímã, POC anterior.
- Dólar (WDO) como líder: anda contra em 76% das pernadas, mas no mesmo minuto; não acrescenta à volatilidade do próprio WIN.
- Saltos de 1 minuto (continuação ou devolução).

## Já medido no histórico de 5 anos (base usada — não serve mais para validar estas famílias)

- Forma interna da pernada ≈ passeio aleatório; embaralhar minutos reproduz contagem e correções.
- Entrar na correção depois da "correção típica" do M5/M15/H1 com vela virando: acerto = breakeven.
- Ordem-limite em recuo de 40–50% do avanço: bate o nulo no IS e no OOS, líquido não significativo (+11/+15 pts ± 16).
- ATR das velas dos 5 pregões anteriores normaliza a contagem de pernadas entre dias/meses.

## Ferramenta

`rodada2/chave/kit_pernadas.py`: carrega M1, reamostra, estado do zigzag minuto a minuto só com o passado, features no instante t, eventos "já andou X" e rótulo separado (olha o futuro). `test_kit.py` prova que nenhuma feature usa dado depois de t.

## Rodadas

- Rodada 1 (2026-10-04): anatomia multi-TF, tempo, volume, sequência, pontos cegos, indicadores, fluxo de agressão → `relatorios_rodada1/`.
- Rodada 2 (2026-10-04): direção — transições, virada, assimetria alta×baixa e regime do dia, chave liga/desliga, gerador de hipóteses → `relatorios_rodada2/`.
- Rodada 3 (2026-10-04): replicação jan–ago/26, recuo × tamanho, confluência multi-TF, desvios → `relatorios_rodada3/`.
- Rodada 4 (2026-10-04): teoria dos jogos e motor de decisão, primeira hora (negativa), vela fora do padrão (R35, R36), composição de velas (R37–R39) → `relatorios_rodada4/`. Ainda em andamento: excursão após o recuo e volume sintético.
- Rodada 5 (2026-10-04): tendência maior × assertividade e geometria colherinha/balde (stop ~100 × alvo ~750) → `relatorios_rodada5/` (em andamento).

**Princípios do dono, valem para toda regra daqui em diante (2026-10-04):** operar a favor da tendência (o recuo serve só como ponto de entrada) e alvo sempre maior que o stop. Uma regra com alvo ≤ stop pode, no máximo, servir de desempate ou de tamanho de mão.
