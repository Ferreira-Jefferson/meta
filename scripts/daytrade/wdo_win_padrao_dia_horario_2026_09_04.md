# Padrão dia da semana / horário — WDO F1 maker e CopaWin (2026-09-04)

Achado do script `wdo_win_padrao_dia_horario_2026_09_04.py` — leia a docstring
dele antes de reusar qualquer número aqui. Resumo do que importa:

- **Puramente descritivo**, sobre trades já fechados. Dia da semana e hora de
  ENTRADA são conhecidos no instante da entrada — sem look-ahead.
- **NÃO é um filtro de entrada novo.** "Dia/semana prediz direção" já foi
  testado e refutado 2x nesta família (ver `LICOES_DE_PRODUCAO.md` /
  `wdof1_tendencia_confirmacao_2026_08_28.py`).
- Capital usado é COM FOLGA de propósito (R$5.000 WDO / R$3.000 WIN — níveis
  já medidos como estáveis, sem trava de caixa). O capital real do dono
  censuraria a maior parte do histórico pelo piso, o que responderia
  "sobrevive?" em vez de "quando o edge se concentra?".
- Nenhuma tabela aqui é regra de execução. Virar regra exige experimento
  próprio com protocolo IS/OOS.

Reproduzir: `python -u scripts/daytrade/wdo_win_padrao_dia_horario_2026_09_04.py`

## Testado depois: NÃO é recomendado parar de operar nos piores dias/horários

Pergunta seguinte do dono (2026-09-04): "e se parássemos de operar nos dias e
horários menos favoráveis, qual o impacto no lucro e na acertividade?".
Testado de verdade (não só descrito) em três rodadas — regra escolhida com o
trecho IS (`< 2026-06-13`) e medida no OOS nunca visto pela regra
(`wdo_win_filtro_dia_horario_impacto_2026_09_04.py`), e depois com a regra
manual do próprio dono usando os dias/horas do relatório acima
(`wdo_win_filtro_manual_fullhist_2026_09_04.py`). Mecanismo: um wrapper
(`FiltroDiaHora`) bloqueia só `Enter`/`EnterLimit` do robô de produção nas
janelas excluídas — saídas e posições já abertas seguem geridas normalmente.

**Conclusão: em toda variante testada (7 no total, 2 robôs), parar de operar
nos piores dias/horários NÃO trouxe vantagem de acertividade que justifique —
o ganho de win% nunca passou de ~1 ponto percentual, e o líquido caiu em
TODAS elas, de forma bem maior que esse ganho. Não recomendado.**

### Tabela comparativa — impacto no OOS (>= 2026-06-13, nunca visto pela regra IS)

**WDO F1 maker** — baseline: R$4.227,39 líquido, 93,5% win, 1.997 trades

| variante | regra excluída | líquido R$ | Δ líquido | win% | Δ win% | trades |
|---|---|---:|---:|---:|---:|---:|
| sem_pior_dia (IS) | quarta | 2.475,08 | -1.752,31 | 93,4% | -0,1pp | 1.399 |
| sem_horas_ruins (IS) | 9h,10h,12h,13h,14h | 3.186,58 | -1.040,81 | 94,4% | +0,9pp | 1.316 |
| sem_ambos (IS) | quarta + as 5 horas | 2.054,34 | -2.173,05 | 94,3% | +0,8pp | 1.025 |
| manual (relatório) | sexta + 9h | 3.496,87 | -730,52 | 94,5% | +1,0pp | 1.478 |

**CopaWin** — baseline: R$8.103,70 líquido, 56,7% win, 97 trades

| variante | regra excluída | líquido R$ | Δ líquido | win% | Δ win% | trades |
|---|---|---:|---:|---:|---:|---:|
| sem_pior_dia (IS) | quarta | 6.144,10 | -1.959,60 | 57,5% | +0,8pp | 80 |
| sem_horas_ruins (IS) | 12h,15h,17h | 3.558,00 | -4.545,70 | 54,0% | -2,7pp | 100 |
| sem_ambos (IS) | quarta + as 3 horas | 3.850,40 | -4.253,30 | 54,2% | -2,5pp | 83 |
| manual (relatório) | terça + 12h,15h,17h | 4.216,10 | -3.887,60 | 57,0% | +0,3pp | 79 |

### Por quê

Os dois robôs (principalmente o WDO F1, um market-maker de grid) ganham
dinheiro por VOLUME de trades pequenos, não por acertar mais um trade
isolado — bloquear uma janela de tempo tira trades que, na média, ainda
somavam mais lucro do que custavam, mesmo sendo "os piores". O win% sobe um
pouco porque os trades mais fracos saem da conta, mas a fração que sobe é
pequena demais para compensar o volume perdido. Além disso, qual dia/hora é
"o pior" MUDA dependendo da janela olhada (sexta no histórico inteiro vira
quarta só no IS, para os dois robôs) — sinal de que não existe um vilão
estável, e sim ruído específico do recorte escolhido.

Scripts: `wdo_win_filtro_dia_horario_impacto_2026_09_04.py` (regra IS→OOS
honesta) e `wdo_win_filtro_manual_fullhist_2026_09_04.py` (regra manual,
com ressalva de vazamento parcial documentada na própria docstring).
Memória: `wdo_win_filtro_dia_horario_refutado_2026_09_04`.

## WDO F1 maker (WDO@)

177 pregões completos, 7.046 trades, líquido R$2.671,80, win 90,3%, capital
inicial R$5.000 (final R$7.671,80).

### Por dia da semana

| dia | pregões | trades | win% | líquido R$ | R$/pregão | mediana/pregão | pior pregão | melhor pregão |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| segunda | 36 | 1.416 | 89,8% | 150,37 | 4,18 | 17,34 | -453,48 | 378,00 |
| terça | 36 | 1.281 | 90,6% | 722,31 | 20,06 | 17,05 | -287,69 | 361,32 |
| quarta | 35 | 1.475 | 90,8% | 840,15 | 24,00 | 39,58 | -434,18 | 448,09 |
| **quinta** | 35 | 1.557 | 90,4% | 957,76 | **27,36** | 66,46 | -401,76 | 511,50 |
| sexta | 35 | 1.317 | 89,6% | 1,21 | **0,03** | 13,18 | -579,67 | 429,67 |

**Melhor dia: quinta (R$27,36/pregão). Pior dia: sexta (R$0,03/pregão, quase nulo).**

### Por hora local (todos os dias juntos)

| hora | trades | pregões c/trade | win% | líquido R$ | R$/trade | R$/pregão |
|---|---:|---:|---:|---:|---:|---:|
| 9h | 1.975 | 175 | 87,4% | -956,89 | -0,48 | -5,41 |
| 10h | 1.334 | 121 | 89,9% | 616,53 | 0,46 | 3,48 |
| 11h | 945 | 100 | 91,4% | 724,20 | 0,77 | 4,09 |
| 12h | 708 | 87 | 90,5% | 258,19 | 0,36 | 1,46 |
| 13h | 546 | 79 | 91,2% | -255,17 | -0,47 | -1,44 |
| 14h | 516 | 75 | 92,4% | 113,40 | 0,22 | 0,64 |
| **15h** | 410 | 60 | 94,1% | 944,65 | 2,30 | **5,34** |
| 16h | 344 | 54 | 94,5% | 734,11 | 2,13 | 4,15 |
| 17h | 175 | 37 | 90,9% | 266,32 | 1,52 | 1,50 |
| 18h | 93 | 33 | 90,3% | 226,46 | 2,44 | 1,28 |

**Melhor horário: 15h (R$5,34/pregão). Pior horário: 9h — abertura — (-R$5,41/pregão).**
15h–18h é consistentemente positivo; 9h é negativa em quase todo dia (só sexta 9h escapa).

### Cruzamento dia × hora (R$/trade; `*` = amostra pequena, n<30)

| dia \ hora | 9h | 10h | 11h | 12h | 13h | 14h | 15h | 16h | 17h | 18h |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| segunda | -1,78 | **3,01** | 0,65 | 0,67 | **-2,23** | 0,37 | -1,57 | -1,47 | -0,53* | 3,18* |
| terça | -0,82 | -1,55 | -0,59 | 2,01 | 3,58 | 2,12 | **4,17** | 4,03 | 2,14* | 4,88* |
| quarta | -0,86 | 0,82 | 0,80 | -0,91 | 0,71 | 1,90 | **4,36** | 3,88 | **-5,84** | 1,76* |
| quinta | 0,10 | 0,16 | 2,32 | 0,49 | -2,25 | **-2,27** | 2,70 | 2,42 | **8,43** | 5,29* |
| sexta | 0,77 | -0,57 | 0,26 | -0,31 | -0,72 | -0,72 | -0,14 | **-1,63** | 0,26* | 0,91 |

Melhor/pior por dia (célula com maior amostra, ver script para n exato):
segunda 10h / segunda 13h · terça 15h / terça 10h · quarta 15h / quarta 17h ·
quinta 17h / quinta 14h · sexta 18h / sexta 16h.

## CopaWin (WIN@)

184 pregões completos, só 321 trades (baixa frequência, ~1,7/pregão), líquido
R$19.340,20, win 52,6%, capital inicial R$3.000 (final R$22.340,20 — retorno
grande vem do sizing dinâmico por risco sobre um capital pequeno, não é
"quase 650% de edge limpo").

### Por dia da semana

| dia | pregões | trades | win% | líquido R$ | R$/pregão | mediana/pregão | pior pregão | melhor pregão |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| segunda | 39 | 61 | 54,1% | 5.877,50 | 150,71 | 107,50 | -1.196,30 | 1.421,00 |
| terça | 37 | 63 | 49,2% | 663,40 | **17,93** | 12,30 | -623,50 | 963,00 |
| quarta | 36 | 61 | 54,1% | 966,00 | 26,83 | -0,60 | -733,50 | 1.252,50 |
| quinta | 36 | 68 | 51,5% | 4.145,90 | 115,16 | 20,05 | -909,10 | 1.609,00 |
| **sexta** | 36 | 68 | 54,4% | 7.687,40 | **213,54** | 183,85 | -546,40 | 1.386,00 |

**Melhor dia: sexta (R$213,54/pregão). Pior dia: terça (R$17,93/pregão).**

### Por hora local (todos os dias juntos)

| hora | trades | pregões c/trade | win% | líquido R$ | R$/trade | R$/pregão |
|---|---:|---:|---:|---:|---:|---:|
| 9h | 125 | 125 | 49,6% | 4.723,70 | 37,79 | 25,67 |
| **10h** | 105 | 88 | 53,3% | 10.481,90 | **99,83** | **56,97** |
| 11h | 22 | 21 | 68,2% | 1.475,70 | 67,08 | 8,02 |
| 12h | 16 | 16 | 56,2% | 1.857,30 | 116,08 | 10,09 |
| 13h | 5 | 5 | 60,0% | -72,00 | -14,40 | -0,39 |
| **14h** | 8 | 8 | 62,5% | -487,20 | **-60,90** | -2,65 |
| 15h | 14 | 13 | 50,0% | -232,60 | -16,61 | -1,26 |
| 16h | 10 | 10 | 60,0% | 965,20 | 96,52 | 5,25 |
| 17h | 10 | 6 | 10,0% | -75,30 | -7,53 | -0,41 |
| 18h | 6 | 6 | 83,3% | 703,50 | 117,25 | 3,82 |

**Melhor horário: 10h (R$99,83/trade). Pior horário: 14h (-R$60,90/trade).**
A partir das 11h a amostra cai muito (≤22 trades no total do histórico) — 9h e
10h concentram a maior parte do volume e são as únicas leituras robustas.

### Cruzamento dia × hora

Quase toda célula tem **menos de 30 trades** (a maioria tem 1-5) — o robô
entra pouco por pregão, então o cruzamento fino é ruído, não padrão. Números
completos (com contagem por célula) ficam só no output do script; não valem
reprodução em tabela resumida porque nenhuma célula individual sustenta
leitura.

## Como reler isto depois

- Índice de memória do projeto: `wdo_win_padrao_dia_horario_2026_09_04`
  (auto-memory, fora do repo).
- Script fonte, com o método completo documentado na docstring:
  `scripts/daytrade/wdo_win_padrao_dia_horario_2026_09_04.py`.
