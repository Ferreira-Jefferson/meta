# Lista de regras candidatas — WIN

Cada regra é um **SE … ENTÃO …** com um papel no robô. A coluna "base" é o que acontece sem a condição (ou o acaso), para comparar. Uma regra só interessa se destoa da base.

**Definições congeladas em 2026-10-04** (não mudar ao replicar):
- Pernada = zigzag de 750 pts sobre o caminho da vela (vela de alta: mínima→máxima; de baixa: máxima→mínima).
- "Recuo de X" = o preço voltou X pts a partir do extremo corrente da pernada.
- Horário de Brasília. VWAP do dia desde 09:00. "Fechamento anterior" = último preço do pregão anterior.
- **Nulo padrão:** velas M1 embaralhadas dentro de blocos de 30 min de cada pregão. Preserva o horário e destrói a ordem.

**Janelas:**
- set/26: exploração.
- jan–ago/26: replicação das regras de setembro com definição congelada.
- Regras novas: descoberta em jan–jun/26, confirmação em jul–ago/26.
- **2025 e antes: reservados, nunca abertos.** Exceção autorizada pelo dono em 2026-10-06: jul e ago/2025 abertos (teste G34) e agora gastos.

**Status:**
- `replicou` — mesmo sentido e força parecida em jan–ago/26.
- `parcial` — mesmo sentido mais fraco, ou só em parte dos meses.
- `falhou` — sumiu ou inverteu (não usar).
- `negativa` — a regra é "isto NÃO funciona", e isso se sustentou (útil para não usar).

## Resumo em uma linha

Em 2026, o WIN tem estrutura de **quando** e **quanto** se mexe (relógio, ondas de volatilidade, minuto cheio, 1ª hora). Em **para onde** ele vai, nenhuma regra de preço, indicador, nível, recuo ou fluxo se sustentou fora de setembro. Setembro foi um mês atípico de reversão da manhã.

## PADRÃO ATUAL (2026-10-06, 2ª): G37 + zera 17:00 (G41)

Mesma estratégia do G37 abaixo, encerrando o dia às 17:00 (antes 17:50). Total jan-set/26 +R$3.167,50. Classe `WinBuscaLucroG41RetanguloZeraCedo`, EA `WinRetanguloEma34` v1.04.

## PADRÃO ANTERIOR (2026-10-06): candidata nº1 = G21 + EMA34 + alvo que se aproxima (G37)

Substitui o padrão de 2026-10-05 abaixo. Mesma entrada; alvo começa em 0,90×largura e vem 0,10×largura mais perto a cada 5 velas fechadas depois da entrada, até 0,50×largura (stop fixo 0,45). Total jan-set/26: +R$3.325,50 (antes +R$2.912,50); setembro −R$324 (antes −R$629). Classe `WinBuscaLucroG37RetanguloEma34AlvoAproxima`, EA `WinRetanguloEma34` v1.03. Ver ORQUESTRACAO.md "PADRÃO ATUAL (2026-10-06)".

## PADRÃO ANTERIOR (2026-10-05): candidata nº1 = G21 + filtro EMA34

A partir de agora, "o retângulo" significa sempre `WinBuscaLucroG29RetanguloEma34`
(período 34), não mais `WinBuscaLucroG21Retangulo1000` puro — a EMA34 melhorou o
resultado nos três períodos testados (descoberta, conferência e o mês ruim de
setembro) sem exceção. Ainda NÃO é validada para operar ao vivo (setembro negativo,
80,8% de chance de ruína). Ver `ea_busca_lucro/ORQUESTRACAO.md`, seção "PADRÃO ATUAL".

## Ficha de decisão (consolidada após a rodada 7, 2026-10-04)

O que sobra de 65 regras, por uso na decisão. O resto do arquivo é o registro detalhado.

| Uso | Fator | Número que sustenta | Regras |
|---|---|---|---|
| **ENTRAR** | nenhum fator confirmado | entradas a favor ficam logo abaixo do breakeven (K5: 13,8% × 14,9%); a combinação de todos os fatores não cria fatia positiva fora da amostra | R62 |
| **NÃO OPERAR** | contra a pernada de 750 em curso | 5–8% de acerto em 100/750; −40 a −51 pts/op | R43 |
| **NÃO OPERAR** | tarde (≥ 13h; ajustar pelo horário de verão dos EUA) | quase não nasce pernada (3,4%); AUC 0,36–0,48 nas 3 janelas | R03, R28, R62 |
| **NÃO OPERAR** | preço preso numa caixa estreita (≤ 150 pts por 20 min) / volatilidade curta baixa | acerto 7,6–9% × base 13,8% | R36, R62 |
| **LIGAR / TAMANHO** (sem direção) | antes das 11h; onda de volatilidade; vela M1 ≥ 2× o mesmo minuto | pernadas: 13,2% × 4,7%; 62% delas em 21% do tempo; 13,5% × 9,3% em 30 min | R01, R02, R20, R35 |
| **STOP +** | minuto :00 e :30; 1ª hora | amplitude 1,37× / 1,18×; stop de 100 varrido no 1º minuto em 49–59% das entradas da manhã | R21, R48 |
| **OBSERVAR EM SOMBRA** (n pequeno, IC cruza 0) | limite a 62% de avanço de 500, stop 1/3, alvo no topo, 1º recuo, < 11h + vela ≥ 2× | +101 / +46 / +4 pts/op nas 3 janelas | R61 |
| **OBSERVAR EM SOMBRA** | M15×H1, M15 rompe só a EMA9 | +56 / +45 nas janelas novas | R65 |
| **REDUNDANTES** | VWAP ≈ posição no dia ≈ distância à máxima (ρ 0,87–0,89); hora ≈ vol30/300 ≈ caixa (0,74–0,86); EMAs entre si | — | — |
| **DESCARTAR** | contagem de velas, fluxo/volume sintético, gap, esticado, profundidade/sequência/forma do recuo, barreiras, médias, indicadores no recuo | = acaso | R05–R08, R10, R13–R19, R25–R27, R31–R34, R37–R42, R44–R47, R50–R60, R63, R64 |

**Leitura:** no WIN de 2026, do minuto à hora, preço, velas, volume e médias têm estrutura de QUANDO e QUANTO, não de PARA ONDE. Direção, se existir, deve vir de informação externa ao gráfico do WIN.

## Busca de EA (2026-10-05) — 25 gerações, 3 fases, encerrada

Depois da ficha acima, o dono pediu a construção de um robô lucrativo via orquestrador recursivo de subagentes (não mais só pesquisa de padrões). Resultado completo em `ea_busca_lucro/ORQUESTRACAO.md` (4.647 linhas) e na memória `ea_win_orquestracao_2026_10_04`. Resumo:
- **Fase 1 (preço/volume do WIN/WDO, capital R$250):** 16 famílias testadas, todas mortas — raridade, censura de capital, ou geometria que não sobrevive a ticks reais.
- **Fase 2 (capital R$1.000 + alvo/stop 2×–5×):** capital resolve ruína de forma limpa, mas revela que o lucro fora da amostra vem concentrado em poucos pregões, pior que na descoberta — confirmado 4× em 3 famílias sem relação entre si (LICOES_DE_PRODUCAO.md 6.52–6.53).
- **Fase 3 (fonte externa: fôlego de 24 ações do Ibovespa, WDO contínuo):** achado novo — **transmissão de volatilidade entre WDO/cesta e WIN é real; transmissão de direção não é** (3× em contextos independentes). Fôlego da cesta prediz confirmação de pernada (+7,2pp), mas fraco demais para pagar o desenho de execução.
- **Veredito:** nenhuma estratégia validada. Próximo degrau é decisão de escopo do dono (categoria de volatilidade/opções, nova fonte de dado, ou encerrar).
- **Checagem de volatilidade/opções (2026-10-05):** bloqueada por falta de dado real (opções do IBOV no MT5 local existem mas são ilíquidas, ~3,6 negócios/dia; sem IV/book/notícias). Relatório em `ea_busca_lucro/viabilidade_volatilidade.md`.
- **G26, pós-fechamento (2026-10-05):** dono observou no replay visual (`.claude/artifacts/g21_retangulo/`) que perdas da G21 pareciam contra a tendência mais ampla. Testado com disciplina IS/OOS-1: a observação era real na descoberta (filtro de tendência melhora win% e concentração), mas não se confirmou na conferência — um candidato não mudou quase nada (filtrou só 2 de 98 trades) e o outro, o melhor do IS, inverteu para negativo no OOS-1. Mesmo padrão de toda a busca. Detalhe em `ea_busca_lucro/ORQUESTRACAO.md`.
- **G27, pós-fechamento (2026-10-05):** dono pediu algo mais estrutural (tendência de M15/H1, não drift cru). i_m15/i_h1 (EMA) pioraram até na descoberta. Só `i_leg` (pernada de 750 em curso) melhorou no IS (win 37,9%→40,4%, concentração 41%→36%) — mas no OOS-1 a concentração piorou para 302%/438% (pior que sem filtro). Terceira tentativa seguida de resolver a concentração da G21 por tendência, terceira que não se confirma.
- **G28, pós-fechamento (2026-10-05):** dono propôs o inverso — usar a FALTA de acordo entre tendências (M15×H1×pernada) como sinal de QUANDO entrar (filtro de regime, não de direção), já que confirmar a tendência não ajudou. Refutada já na descoberta: operar só quando as escalas discordam é pior que operar sempre, nas duas definições testadas (liquido ~R$0 e R$1.750 contra R$2.790 sem filtro). Não foi promovida ao OOS-1. Leitura provável: a G21 já embute uma lógica de continuação local (entra no lado que o preço já vinha), e consenso de tendência parece ajudar essa continuação, não atrapalhar — o oposto da hipótese.
- **G29, pós-fechamento (2026-10-05):** dono pediu EMA 34 clássica (venda só com fechamento abaixo, compra só acima). Platô real no IS (períodos 21/34/55, todos POSITIVO); no OOS-1 melhorou TODAS as métricas (líquido R$650→R$737, acerto 39,8%→41,6%, concentração top3 97%→88%). **Reprovada no OOS-2 (set/26, gate final):** líquido −R$629,50, acerto 31,2% (abaixo do BE 37,7%), sequência de 14 perdas, p_ruína 80,8%. Combinado jan-set ainda positivo (R$2.912,50, POSITIVO) mas um mês com 80% de ruína não é validável só porque a média do ano compensa. G21+EMA34 não é estratégia validada.

## Regras de setembro, replicadas em jan–ago/26

| ID | SE | ENTÃO | Papel | set/26 | jan–ago/26 | Base | Status |
|---|---|---|---|---|---|---|---|
| R01 | hora < 11:00 | maior chance de nascer pernada de 750 (recuo de 250 → 750) | LIGA | 20% × 5% | **13,2% × 4,7%** (jan quase sem efeito) | igual ao nulo com horário | **replicou** (é o relógio) |
| R02 | hora < 11:00 | o robô ligado ali pega a maior parte das pernadas | LIGA | 73% em 21% do tempo | **62% em 21%** (jan–mar 39–53%; abr–ago 64–84%) | 21% | **replicou** |
| R03 | hora ≥ 13:00 | quase não nasce pernada nova | DESLIGA seguir | 3% | **3,4%** (× 10,3% antes) | — | **replicou** |
| R04 | hora ≥ 13:00 e recuo de 500 | o recuo vira pernada de 750 | SAÍDA | 77–88% | 64,6% | nulo 66,8%, manhã 67,2% | **falhou** |
| R05 | às 10:30 o preço está do mesmo lado da abertura, do VWAP e do fechamento anterior | o resto do dia vai contra | DIREÇÃO | 12/14 | **50,0%** (meses 20–79%) | 50% | **falhou** |
| R06 | 10:30–12:30, preço > 500 pts do fechamento anterior | volta em parte em 60 min | DIREÇÃO | 73% | 49,9% | 49,2% | **falhou** |
| R07 | idem, da abertura | idem | DIREÇÃO | 66% | 47,5% | 49,0% | **falhou** |
| R08 | idem, do VWAP | idem | DIREÇÃO | 61% | 48,4% | 47,5% | **falhou** |
| R09 | houve gap | o gap fecha no dia | ALVO | 85% | 73% | mesma distância no sentido oposto: 70,6% | **parcial** (é só a volatilidade) |
| R10 | houve gap | o dia termina contra o gap | DIREÇÃO | 70% | 53,4% (IC 46–61%) | 50% | **falhou** |
| R11 | qualquer dia | ≥1 extremo do dia nas 2 primeiras pernadas H1 | ALVO − à tarde | 95% | 92% | nulo com horário 91% | **replicou, = acaso** |
| R12 | qualquer dia | máx e mín saem cedo | ALVO − à tarde | ~10:28 | 10:44 / 11:04 | nulo 10:52 / 11:12 | **parcial** |
| R13 | uma pernada terminou | a seguinte passa do início da anterior | ALVO − | 42% | 49,1% | 49,1% | **falhou** |
| R14 | recuo de X do extremo | chance de virar pernada de 750 | (base) | 21/31/47/64% | **20/32/48/65%** (X = 150/250/375/500) | igual ao nulo | **negativa** (só a distância importa) |
| R15 | médias, VWAP, RSI, divergência, volume, fluxo, vela, no recuo | mudam a chance da R14 | ACEITA/REJEITA | não | AUC 0,47–0,52 | 0,50 | **negativa** |
| R16 | tamanho da pernada anterior | prevê o tamanho da próxima | ALVO | não | corr. 0,02 | 0,00 | **negativa** |
| R17 | pernada de alta × de baixa | são diferentes | parâmetros | iguais | iguais (razões 0,97–1,04) | 1,00 | **negativa** → mesmos parâmetros nos 2 lados |
| R18 | agressão forte a favor da pernada | a pernada continua | REJEITA contra | AUC 0,41–0,45 | 0,49–0,53, sem direção estável | 0,50 | **falhou** |
| R19 | pernada > 1,5 ATR M5 do VWAP | vira mais | ACEITA virada | 32,4% × 29,2% | 32,4% × 31,5% | — | **falhou** |
| R20 | bloco de 15 min agitado para o horário | o seguinte também | LIGA / TAMANHO | 0,25 | **0,19–0,67** por mês (0,36 total) | ±0,07 | **replicou** (mais forte no inverno dos EUA) |
| R21 | minuto :00 (e :30) | amplitude acima da média da hora | STOP + | 1,57× / 1,25× | **1,37× / 1,18×** | 1,00 | **replicou** |
| R22 | 09:00–10:00 | movimentos de 5–15 min são devolvidos | REJEITA rompimento curto / DIREÇÃO contra | VR5 0,70 | **VR5 0,81**, abaixo do acaso em 7/8 meses | 1,00 | **replicou** (único efeito com direção que se sustentou) |
| R23 | tarde | pernadas mais lentas e mais sujas | ALVO − / prazo + | 4,5× / 1,8× | 2,6× / 1,4× | nulo com horário 2,4× / 1,5× | **parcial, ≈ relógio** |
| R24 | abertura de NY | salto de amplitude | marco de regime | 1,28× às 10:30 | 1,16× às 10:30 (mar–ago); **às 11:30 em jan–fev** | 0,94 | **replicou** — depende do horário de verão dos EUA |
| R25 | volume da vela anterior ao início | prevê o tamanho da pernada | — | não | 0,00 / 0,04 | ±0,03 | **negativa** |
| R26 | dólar (WDO) | antecipa o WIN | — | não | anda contra 83,5% (nulo 83,1%), não lidera | — | **negativa** |
| R27 | dentro da pernada, recuo passou da "correção típica" e a vela virou | a pernada retoma | ACEITA | — | acerto = mínimo necessário (5 anos) | — | **negativa** |

## Regras novas da rodada 3 (descoberta jan–jun/26 → confirmação jul–ago/26)

| ID | SE | ENTÃO | Papel | Descoberta | Confirmação | Status |
|---|---|---|---|---|---|---|
| R28 | data entre o 2º domingo de março e o 1º domingo de novembro (horário de verão dos EUA) | o salto de NY é às 10:30; fora disso, às 11:30 | ajuste do relógio de todas as regras de horário | jan–fev: 11:30 (1,26× e 1,55×); mar–ago: 10:30 | — | **observado** (aplicar a R01–R03, R24) |
| R29 | preço > 1,5 ATR acima do VWAP, subiu ≥ 300 pts nos últimos 30 min e está a ≤ 500 pts da máxima do dia | faz nova máxima do dia por ≥ 250 pts | ALVO + / ACEITA seguir esticado | 69% × 57% (n=638) | **82% × 67%** (n=178, 19 dias, IC +3 a +24 pp) | **confirmou, fraca** (espelho na queda: mesmo sinal, sem confirmar) |
| R30 | queda de ≥ 300 pts chega a ≤ 100 pts do POC do dia | o repique de 250 antes de cair mais 250 é MENOS provável | REJEITA comprar a queda | 43,1% × 49,3% | 39,8% × 47,7% (z −1,5 / −2,1) | **no limite** |
| R31 | queda do M5 chega a uma barreira do M15/H1 (pivô, média, Fibonacci, VWAP, bandas, dia anterior, OR, nível tocado) | repique ou platô | ACEITA entrada | 34 tipos × 136 configurações: nada acima do acaso | — | **negativa** |
| R32 | depois de um avanço A, recuo de r% | faz novo extremo | ALVO / SAÍDA | = 1 − r (ex.: 50% → 53%), igual ao nulo; 50% não é barreira nem ímã | idem | **negativa** |
| R33 | avanço A ≥ 375 pts e recuo ≥ 38% | chegar a 2A é um pouco menos provável | ALVO − | 19,1% × 22,0% | 18,0% × 22,4% (z −2,5) | **parcial** (inverteu em set/26) |
| R34 | dentro da pernada | há ~5% menos correções que no acaso | — | — | 3,25 × 3,43 por pernada | fraca |

## Regras novas da rodada 4 (descoberta jan–jun/26 → confirmação jul–ago/26)

| ID | SE | ENTÃO | Papel | Descoberta | Confirmação | Status |
|---|---|---|---|---|---|---|
| R35 | vela M1 com faixa ≥ 2× (ou ≥ 3×) a do mesmo minuto nos 20 pregões anteriores | mais chance de pernada de 750 nos 30 min seguintes, **sem direção** | LIGA / TAMANHO + / ALVO + | lift ~1,3–2,5× | **13,5% × 9,3%** (jul–ago) | **confirmou** (o volume não acrescenta nada além do tamanho) |
| R36 | caixa de ≤ 150 pts por 20 min | a chance de pernada cai para perto de zero | DESLIGA | forte | inconclusiva | **pista** |
| R37 | saldo das últimas 10 velas M1 no quintil superior (inferior) | +250 antes de −250 (o inverso) | DIREÇÃO fraca, só na escala de 250 pts | D +0,04 | **55,5% × 43,3%** (D +0,12; set +0,17). Bootstrap jan–ago IC +0,02 a +0,10; 7/9 meses (mai e jun inverteram) | **parcial** — microtendência de ~10 min. Não diz nada sobre a pernada de 750. Com alvo = stop, fere o princípio colherinha/balde: só serve como desempate de direção |
| R38 | contagem de velas de alta e de baixa, por cor, corpo ou volume (M1/M5/M15, 10–120 min) | direção dos 30/60 min seguintes ou da pernada de 750 | DIREÇÃO | 696 células | D ≈ 0. A correlação descoberta × confirmação é −0,03 | **negativa** |
| R39 | divergência de contagem entre tempos (M1 de alta × M15 de baixa), ou pico num tempo que não aparece no outro | direção | DIREÇÃO | nada passou \|z\|>3 | — | **negativa** (contagens entre tempos têm correlação de 0,56–0,96: tempo maior traz pouca informação nova) |

| R40 | tamanho médio do negócio no recuo no tercil alto | chegar a 2A é mais provável | ALVO + | +3,1 pp (n=1.757, z 2,9) | −1,9 pp (n=445) | **falhou** (inverteu) |
| R41 | delta acumulado do movimento (avanço + recuo, regra do tick) no tercil alto, a favor do avanço | chegar a 2A é mais provável | ALVO + | +3,8 pp (n=1.372, z 3,0) | +1,8 pp (z 1,0); set −1,1 | **falhou** |
| R42 | participação no recuo × avanço (12 medidas de volume sintético: negócios, contratos por ponto, tamanho do negócio, delta) | muda P(novo extremo), P(2A), MFE ou MAE | ACEITA / ALVO | 17 de 144 com \|z\|≥2 (acaso ~6) | perto do acaso | **negativa**: o recuo se lê só pela distância (reforça R15, R18, R32). A aparente previsão do alcance pela razão recuo/avanço era efeito do tamanho do avanço; estratificando por A, \|r\| ≤ 0,07 |

| R51 | depois de avanço A e recuo r | o preço anda X a favor / Y contra | ALVO / STOP | alcance não depende de A nem de r: depende do horário e da volatilidade. Em 60 min o MFE mediano é ~430–590 pts e o MAE ~335–450, iguais ao nulo (o MAE é ~10% menor quando A < 750). Recuo raso favorece continuar e fundo favorece virar, mas só +1 a +8 pts | 7 células passaram na descoberta, 0 confirmaram; todas negativas em set | **negativa** — o alcance é ~constante em pontos (com A pequeno anda 2,4A; com A grande, 0,5A) |

**Volume sintético (ferramenta, `rodada4/volume_sintetico/volume_sintetico.py`).** A regra do tick reproduz o delta real do WINV26 com correlação 0,93 por minuto (0,77 na 1ª hora) e acerta o sinal em 93% dos minutos; subestima a magnitude (beta 0,70). Sem ticks, o delta por corpo/range da vela dá correlação 0,84. O TICKVOL do M1 correlaciona 0,988 com o número de negócios e serve como contagem em qualquer gráfico.

Primeira hora (rodada 4, 2.592 configurações): sem vantagem depois do custo. **Negativa.** As geometrias de lá (alvo < stop) também ferem o princípio colherinha/balde.

## Rodada 5 — tendência maior × geometria colherinha/balde

Entrada por limite a 150/300 pts do extremo do dia (ou na EMA60 M1), stop 75–200, alvo 600–1.000, convenção conservadora de preenchimento. Referência abaixo: stop 100 / alvo 750 / X 150. Nulo 11,8%, breakeven empírico 12,5%.

| ID | SE | ENTÃO | Papel | Descoberta | Confirmação | set/26 | Status |
|---|---|---|---|---|---|---|---|
| R43 | entrada CONTRA a pernada de 750 em curso (ou contra qualquer escala intradiária) | acerto abaixo do acaso | **REJEITA** contra-tendência | 7,6%, −40 pts/op | 5,3%, −51 pts/op (IC todo < 0) | 4,1% | **replicou** — princípio do dono confirmado no lado negativo |
| R44 | entrada A FAVOR da pernada de 750 | acerto maior | ACEITA | 11,9%, −3,7 pts/op | 10,0%, −17,6 | 13,6% | **parcial**: só acima do rótulo aleatório (12,9% × 11,6%, p 0,02; p ≈ 0,18 corrigido). **Não paga o breakeven** em nenhuma das 1.620 células |
| R45 | tendência diária (MA20, inclinação, semana anterior, concordância de 3 ou 5 escalas) | muda o acerto a favor | ACEITA | +, pequeno | **inverteu** (−3 a −9 pp) | +11 a +12 pp | **falhou** (instável entre períodos) |
| R46 | concordância de 5 escalas + vela M1 ≥ 2×, limite 300 abaixo da máxima, stop 150 / alvo 1.000 | lucro | ACEITA | 17,8% × BE 13,6%, +56 pts | 12,2%, −13 pts (n=42) | — | **falhou** |
| R47 | filtro "cedo" (< 11h) somado à tendência | melhora | LIGA | — | piora (−39 × −20 pts/op) | — | **falhou** |

| R48 | stop fixo de 100 (ou 50–250) com alvo ≥ 3× o stop, qualquer gatilho, direção ou gestão | lucro | geometria | 0 de 2.976 células com t ≥ 3; média −14 pts/op (nulo −12) | 13 de 15 congeladas inverteram; 100/750 com h<11 + v2x deu −54 pts/op (IC todo < 0) | — | **negativa**: o ruído de 1 min varre o stop de 100 em ≤ 1 barra em 49–59% das entradas da manhã (28–38% à tarde); ~89% das operações terminam em stop |
| R49 | stop técnico (extremo das últimas 5–15 velas) + alvo 7,5× o stop, em dia de vela ≥ 2× e onda de volatilidade | lucro | STOP / ALVO | +46 a +69 pts/op | +17 a +96 (IC enorme, n = 21–38) | positiva | **pista única viva**, sem conclusão: precisa de ≥ 150 operações fora da amostra |
| R50 | mover o stop para a entrada, parcial no meio, stop por volatilidade | melhora | SAÍDA | não muda o sinal (−13/−14 × −14) | — | — | **negativa** (stop por volatilidade é pior) |

Ruína a R$250 em qualquer célula de ~12% de acerto: 66–67% em ~215 operações, sequência esperada de ~29–50 perdas seguidas.

## Rodada 6 — forma do recuo e geometria proporcional

| ID | SE | ENTÃO | Papel | Descoberta | Confirmação / set | Status |
|---|---|---|---|---|---|---|
| R52 | o preço sai do fundo F do recuo | repica até onde | ALVO / SAÍDA | mediana 0,60–0,64 do recuo; 71% repicam ≥ 50%; 50% e 62% não são ímãs | idem | **= acaso** (igual ao embaralhado) |
| R53 | depois do repique | reteste com fundo mais baixo / mais alto / duplo | STOP | 54–62% / 21–41% / 6–14%; quando fura, ~30% do recuo (75/105/155 pts em T 250/500/750) | idem | **= acaso** |
| R54 | fundo mais alto + repique ≥ 50% | supera o topo de origem | ACEITA | 74–81% × ruína do jogador 72–79% (+4 pp, z ≤ 1,7 contra o embaralhado) | inverte em set (−5 pp, z −2,5) | **falhou** — é só a distância ao topo |
| R55 | limite no fundo F (posta com o repique confirmado), stop F − k, alvo no topo de origem (3–5× o stop) | lucro | geometria | 0 de 36 células com IC > 0; 500/125 k=100: 19,7% × BE 22,5%, −12 pts/op | 0/36 | **negativa** |

| R56 | sequência de recuos (supera de primeira? nº de tentativas, 2º < 1º, correlação r1×r2, recuos encolhendo, ordem do recuo) | muda o desfecho | ACEITA / ALVO | supera de primeira 45,6% × nulo 45,2%; tentativas 1/2/3/4+ = 59/13/5/2% = nulo; P(r2<r1) 50,1% × 49,7%; corr. +0,02; 9 escalas | 5 negativas confirmaram | **negativa** (= passeio aleatório em todas as escalas) |
| R57 | 1º fundo em 23–38% do avanço (recuo raso); entrada a m acima do fundo, stop no fundo, alvo 5× o risco | P(5R) acima do acaso | ACEITA | z +2,6 | T750: 19,7% × nulo 15,2% (z +2,4, n=380); T500: 18,3% × 15,3% (z +2,4) | **parcial** — sinal confirmou, mas fica a 1–3 pp do breakeven de 16,7%; com custo +0,1 a +0,3R, IC cruza zero |
| R58 | repique (bounce) entre 11h e 13h, mesma geometria | P(5R) e P(10R) acima do acaso | LIGA | z +2,5 | P(5R) T750 22,0% × 17,3% (z +2,6); T500 z +1,8; P(10R) z +2,5 / +3,2 | **parcial** — curiosamente o oposto do relógio de pernadas (R01): para razão alta o meio-dia (menos ruído) ajuda |
| R59 | fundo do recuo ≥ fundo do recuo anterior | P(5R) maior | ACEITA | — | z +2,0 (T750), +1,5 (T500) | **fraca** |

| R60 | geometria proporcional (513 geometrias × 72 filtros: limite a r% do avanço, reteste do fundo, stop técnico de N velas; alvo 3–10× o stop) | lucro | geometria | 8 congeladas em platô, +38 a +242 pts/op | 4 de 8 positivas, nenhuma com IC > 0; set: 7 de 8 negativas. **Com ticks (mar–jun) 6 de 8 viram negativas** | **negativa** |
| R61 | limite a 62% do avanço (T 500), stop 1/3 da distância ao topo, alvo no topo (3×), 1º recuo, antes das 11h, com vela M1 ≥ 2× | lucro | ACEITA (observar) | +101 (IC +40 a +163), 44% × BE 25%, n=63 | +46 (IC −30 a +131), n=20; set +4, n=14; ticks +84, n=12 | **única positiva nas 3 janelas**, n pequeno — só observar em sombra |

| R62 | combinação de TODOS os fatores (logística L2, CV por mês; 900 geometrias de rótulo, ~110 limiares, 4 conjuntos de EMAs) | uma fatia (top 10–20%) acima do breakeven | ACEITA | top 20% +63 pts/op em CV | jul–ago −25 (IC −128 a +98); set −92; AUC 0,63 só pelo relógio (sem ele 0,56; set 0,46); 75% dos nulos de rótulo embaralhado igualam ou superam o real | **negativa** — fatores somados não fazem entrada |

| R63 | M5 rompe as EMAs contra a tendência enquanto o M15 (ou M30/H1) segue alinhado e só toca a EMA9/21 — encaixe multi-TF (2.880 células: pares de TF × períodos × toque × stop × alvo) | entrada a favor acerta mais | ACEITA | literal do dono −17 pts/op (16% × BE 18,5%), aleatório no mesmo horário 20,5%; 10 congeladas de platô, +34 a +60 | as 9 de platô juntas −21 (jul–ago, n=400) e −42 (set, n=263); 0 de 9 replicaram | **negativa**. Volta à tendência do M15 antes de perder a EMA50: 32% × 44% de falha (pior que o acaso) |
| R64 | períodos das EMAs (rápida 5–15, média 15–40, lenta 34–120; EMA × SMA) | mudam o resultado | (parâmetro) | insensível: 9/21/50 ≈ 5/17/34 ≈ 13/24/120; 77 de 81 células rápida×média ≤ 0. Pioram: média colada à lenta, SMA, exigir romper as 3 médias | — | **negativa** — o número exato não importa porque o encaixe não funciona |
| R65 | M15×H1, M15 rompe só a EMA9, H1 com alinhamento frouxo | lucro | ACEITA (observar) | positiva | +56 (jul–ago) e +45 (set), IC [−64; +228] e [−112; +205], z 1,5 e 0,7 | **em aberto** — precisa de ≥ 150 operações novas; ruína 55% a R$250 |

Taxa-base de "entradas que deveriam ter sido feitas" (a favor, stop técnico com piso de 100 pts, conferido com ticks): K3 23,4% × BE 24,5%; K5 13,8% × 14,9%; K10 5,0% × 5,8%. Contra a pernada: 0,7–1,5 pp pior.

**R49 (stop técnico + alvo 7,5×) caiu:** com ticks, o stop técnico de 5–10 velas passa de positivo no M1 para −7 a −136 pts/op. O positivo era artefato do caminho de 2 pontos por vela.

Geometria de referência da sequência (entrada no fundo + m, stop no fundo, sem custo): P(3R/5R/10R) = 22,5 / 14,1 / 6,3% × nulo 22,0 / 13,8 / 6,3% × fórmula 25,0 / 16,7 / 9,1%. Alvos de 5–10× o risco acontecem na frequência do acaso.

**Nota de método (rodada 6).** O caminho de 2 pontos por vela M1 (mínima→máxima ou máxima→mínima) gera ~5× mais eventos de recuo em escala pequena do que os ticks e piora os resultados. Com ticks (mar–jun, n=763) o acerto fica igual à ruína do jogador e a esperança em ~0 pts/op (IC −11 a +11), sem vantagem — mas também menos negativo que no M1. Estudos de stop curto/escala pequena (rodada 5 "balde", R48) podem estar pessimistas pelo mesmo motivo; o veredito "sem vantagem" não muda.

## Falharam na confirmação (não reusar)

- Volatilidade relativa baixa → menos novas mínimas (inverteu em 4 variantes).
- Gap < −300 com preço perto da máxima → fecha acima (73% → 24%).
- Gap > 300 com zigzag de alta → fecha abaixo (inverteu).
- Preço abaixo do VWAP −1,5 ATR com zigzag de alta → fecha abaixo (inverteu).
- 1ª hora com zigzag de 1.250–2.000 → nova máxima (93% → 57%).
- Todo "sobe Y antes de descer Y" (Y = 250/500/750).
- Recuo pequeno (A < 375, recuo ≥ 38%) → continua; 2º recuo ou mais ≥ 50% → não retoma.
- Barreiras: VWAP, ±0,5% do fechamento anterior, nível tocado 3 vezes.

## Nota de dados

`data/cache_win_ticks/WIN@D` não tem o lado do agressor (flags constantes, bid/ask zerados). Só o WINV26 tem, e ele só é líquido a partir de ~12/08/2026. Para fluxo antes disso, usar a regra do tick (78% de concordância por negócio; correlação 0,97 do delta por minuto).
