# Combinações de estratégias WIN 2026 — TODO vivo (recuperação após desligar o PC)

**Pedido do dono (2026-10-06):** criar estratégias que usam as 6 do comparativo para decidir.
1. **Consenso:** só entra quando todas ou a maioria das estratégias concordam que a entrada é boa.
2. **Nota / probabilidade:** cada estratégia dá uma nota para a entrada. A nota combinada estima a probabilidade de acerto e decide se entra, o tamanho do alvo e o do stop.
3. **Outras possibilidades:** um agente de ideias propõe; as escolhidas viram frentes novas.

**Base:** `scripts/daytrade/comparativo_win_2026/` (dados.py, port_*.py, resultados/*.csv), WIN$N 02/01–05/10/2026, regras de execução do Testador (docstring de dados.py), R$1.000 iniciais, 1 contrato. As 6 estratégias: Win, Win_c1, WinCincoMedias, WinDeslocamentoMatinal, WinRetanguloEma34, WdoRetangulo.

## ESTADO GERAL (2026-10-06): TODAS AS FRENTES CONCLUÍDAS — nenhuma passou do p95
C portfólio K: não ajuda (NETTING custa ~R$3–4 mil/ano). A consenso: filtro p94,5 (+487 c/ custo), gatilho novo p91,5 (+3.163). B nota: AUC 0,48–0,50, refutada. D regime 10:30, E saída na virada, F veto: refutadas. N/RDT: refutada no VAL (p82); bloco VAL (jul/24–set/25) GASTO 1 de 3; HOLDOUT 2026 intocado pela RDT.
Fase 2 concluída: seção "Combinações testadas" na página do comparativo.

## DECISÃO DO DONO (2026-10-06): C1 = Win_c1 + filtro pela nota (B, tabela de frequência walk-forward) APROVADO
VAL: −1.688 → +86 (Δ +1.774), 331 → 67 ops, maior queda 2.253 → 288, sem quebra. Não atingiu o critério estatístico (p 0,102; Holm 0,917; sorteio p50 +1.339); aprovado pelo dono por filtrar entradas ruins. Próximo: acompanhar em simulação de out/2026 em diante. Regra congelada: v_validacao/v1/CONGELADAS.md (C1) + v1_regras.py.

## PROTOCOLO (todo agente segue)
- **Edição do TODO: só com edição pontual da SUA seção (ferramenta Edit com o trecho exato). PROIBIDO sed/regex/reescrita do arquivo inteiro** — em 2026-10-06 um sed apagou as linhas "Fase:" de todas as seções. Cópia de segurança: TODO.md.bak.
- Ao COMEÇAR: marque sua frente como `[~] em andamento` e escreva a fase atual.
- A CADA ETAPA concluída: atualize a sua seção — fase, o que já fez, o que falta, arquivos que criou ou está mexendo, e o último resultado. Edite SÓ a sua seção.
- Ao TERMINAR: `[x] concluída`, resultado final em 2–4 linhas e o caminho dos arquivos.
- Se ao começar você encontrar a sua seção já em andamento (PC desligou), retome do "falta", sem refazer o que está marcado como feito.
- Arquivos de cada frente ficam na subpasta dela, dentro de `combinacoes/`.
- Método obrigatório em todo teste:
  - sem olhar o futuro: o voto em t usa só barras fechadas até t;
  - parâmetros escolhidos só no passado (walk-forward por mês: treina nos meses anteriores e aplica no mês seguinte);
  - comparar com a melhor estratégia isolada e com um filtro aleatório que descarta a mesma fração de entradas (percentil do resultado contra 200 sorteios);
  - tabela por mês jan–out + total, sem custo e com R$2/op;
  - capital R$1.000, quebra marcada.

## Fases
- Fase 0 — Fundação (camada de votos + simulador de saída genérico). As frentes A, B e as de ideias dependem dela.
- Fase 1 — Frentes A (consenso) e B (nota/probabilidade), em paralelo, mais as frentes que saírem das ideias.
- Fase 2 — Consolidação no HTML do comparativo.

---

## F0 — Fundação: votos e simulador de saída
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: votos (+teste sem-futuro), simulador de saída (+validação), eventos, descritiva
Falta: —
Arquivos (em combinacoes/f0_fundacao/): votos.py -> votos.parquet (106.615 M1 x 26 col: <E>.voto/.forca/.posicao/.sinal, .ret nos retângulos; definições e linhas do .mq5 no docstring); test_votos_sem_futuro.py (passa); saida.py (simula_saida, simula_saida_lote; `python saida.py valida`); eventos.py -> eventos.parquet (1.608 entradas x 51 col: votos das 6 na última M1 fechada, favor/contra/neutro, contexto, MFE/MAE até a saída e até 17:50); descritiva.py -> descritiva.md
Último resultado: teste sem-futuro 0 diferenças em 6 cortes. Simulador reproduz 65/65 saídas do WinDeslocamentoMatinal (stop do EA, zera 18:20) e 134/134 do WdoRetangulo (stop+alvo limite). Própria estratégia vota o lado da entrada em 100% (Win, Win_c1, Cinco, Desloc), 97,8% WdoRet, 80,5% RetEma34 (limite no meio enche depois de o preço cruzar o meio). Win e Win_c1 votam igual (gêmeas). Votos de Win/Cinco/Desloc concordam 94–100% quando ativos ao mesmo tempo; correlação diária baixa entre o grupo de tendência e os retângulos (−0,08 a 0,10).

## IDEIAS — agente que propõe outras possibilidades
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: leitura (ports, notas.json, CSVs, memórias WIN); descritiva dos CSVs; 10 propostas escritas e ranqueadas.
Falta: —
Arquivos: combinacoes/ideias/propostas.md
Resultado: Win e Win_c1 são um voto só (correlação diária 0,97). Na prática há 2 famílias: tendência (Win, Cinco, Desloc; mesmo lado em 79–92% dos dias) e retângulo (RetEma34, WdoRet; ~50% contra a tendência, correlação ~0). WdoRet serve de voto placebo. Todas as bases foram escolhidas em 2026, então o walk-forward protege só a camada de combinação. Testar primeiro: 1, 2, 3 e 4.
Ideias propostas (ranqueadas):
1. Portfólio com teto de K contratos simultâneos e prioridade (só CSVs) — rápido
2. Estado das 10:30 do Deslocamento (sinal a favor / contra / sem sinal) como regime diário das outras — rápido
3. Saída pela virada da outra família, em teste pareado com as mesmas entradas — médio
4. Veto cruzado: bloquear entrada quando outra família tem posição real contrária — rápido (pós-F0)
5. Ordem de chegada: 1ª entrada × 2ª que confirma (no lucro/prejuízo) — rápido (pós-F0; casar com B)
6. Stop/alvo escalados pela volatilidade esperada do horário, sem mexer no lado — médio (casar com B)
7. Revezamento por faixa horária: cada bloco só para a melhor no passado — médio, sobreajuste alto
8. Peso por desempenho recente / desligar após queda (análogo já refutado) — rápido, chance baixa
9. Clusters de estados de votos por família (análogo ao "mapa de vantagem" refutado) — médio, chance baixa
10. Meta-rotulagem logística das entradas (quase igual à B; multi-fator já refutado) — pesado, chance baixa

## A — Consenso / maioria
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: filtro de consenso (9 variantes, walk-forward, controle 200, placebo de votante), gatilho novo (grade 9, walk-forward, controle, placebo), resultado.md, trades/.
Falta: —
Arquivos: combinacoes/a_consenso/ (consenso_filtro.py, consenso_gatilho.py, resultado.md, resultado_*.csv, trades/)
Resultado: 63 células olhadas. Filtro, conjunto de 5: walk-forward +19.974 (R$2: +17.864) contra 20.219 (17.377) sem filtro e 8.859 da melhor isolada; percentil 94,5 contra o sorteio; DD igual ou pior. Placebo: so o voto do WinRetanguloEma34 carrega informação (p99,5). Gatilho novo: +4.015 (R$2: +3.163), 426 ops, DD 2,2 mil, p91,5 contra lado sorteado; só o voto do WinCincoMedias importa (p97,5). Nada passa de p95 de forma robusta.

## B — Nota / probabilidade de acerto → entra ou não, tamanho de alvo e stop
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: filtro walk-forward (3 modelos, sorteio 200, placebo 200, ideia 5 como feature), resize de alvo/stop pela nota (RetEma34 re-simulado; overlay de stop nas de tendência), ideia 6 (vol do horário), resultado.md/csv, trades/
Falta: —
Arquivos: combinacoes/b_nota/ (resultado.md, resultado.csv, trades/, comum.py, run_filtro.py, run_saida.py, relatorio.py, extrai_retema34.py)
Resultado: AUC fora da amostra 0,502 (tabela) / 0,479 (logística) / 0,471 (nota): sem poder preditivo; calibração sem ordem nos quintis. Walk-forward só filtrou com a tabela (abr, jul, ago): carteira R$2 13.890 contra 17.377, percentil 16 no sorteio, 4 no placebo; logística e nota nunca acharam limiar no passado (= sem filtro). Resize: RetEma34 pela nota +227 sobre a re-simulação (percentil 95 de 3 modelos, ~115 células olhadas; re-simulação reproduz só 69% dos trades originais); overlay de stop e ideia 6 sem ganho. Jan–mar sem filtro. Nenhuma versão quebrou.

<!-- Frentes novas (C, D, ...) vindas das IDEIAS são acrescentadas abaixo pelo orquestrador. -->

## C — Portfólio com teto de K contratos simultâneos + prioridade (ideia 1)
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: simulador (portfolio.py), 48 células x 2 custos, controle de 200 sorteios, escolha walk-forward, resultado.md/csv, 3 CSVs em trades/.
Falta: —
Arquivos: combinacoes/c_portfolio/ (portfolio.py, resultado.md, resultado.csv, resultado_mensal.csv, trades/)
Resultado: nenhuma célula quebrou. K=1 perde para a melhor isolada (+7,6 a 9,9 mil; percentil 0-7 contra o sorteio). K=3 independente 5 sem Win_c1: +20.649 (R$2: +17.833), DD 1.562, percentil 93 no líquido. Com NETTING (186-236 entradas bloqueadas) cai para +16,9 mil e o percentil vai a ~55 (indistinguível do acaso). Walk-forward do teto escolhe K3 quase sempre. Bases escolhidas em 2026; prioridade só atua em empate de minuto (diferença mínima). "Pior saldo intradia" aproximado coincide com o menor saldo.

## D — Estado das 10:30 do Deslocamento como regime diário (ideia 2)
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: pré-registro (4 células d1–d4, sem parâmetros, sem walk-forward), rodada com controles (200 sorteios de dias, placebo de lado, permutação de dias), resultado.md/csv, trades d1 e d4.
Falta: —
Arquivos: combinacoes/d_regime_1030/ (lib_comb.py, d_regime.py, resultado.md, resultado.csv, trades/d1.csv, d4.csv). Regime = voto do Deslocamento na barra da decisão (1ª M1 + 89 min; 66 dias com sinal, 124 sem); Deslocamento isento.
Resultado: nenhuma célula melhora a soma sem filtro (5 sem Win_c1: +20.219 / R$2 +17.377): d1 −145 (13 entradas removidas), d2 −2.007, d3 −887 (R$2: −369; DD 1.524 contra 1.603), d4 −1.032. Nenhuma quebrou. Percentis contra sorteio de dias: d1 59, d2 99,5, d3 64, d4 84,5 (altos só porque o sorteio remove entradas boas ao acaso; mesmo assim o delta é negativo). Veredito: refutada, encerra. Nenhuma passa de p95 com delta positivo.

## E — Saída pela virada da outra família, teste pareado (ideia 3)
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: simulação das 6 variantes (V1/V2/V3 x a/b), pareado com IC por dia, controles (sorteio de instante e placebo, 200), tabelas, resultado.md, trades/
Falta: —
Arquivos: combinacoes/e_saida_virada/ (virada.py, relatorio.py, resultado.md, resultado_mensal/pareado/controles.csv, trades/V*.csv)
Resultado: nenhuma variante melhora a soma das 5 (sem custo original +20.219; V1a 16.840, V1b 16.276, V2a 12.910, V2b 11.632, V3a 16.241, V3b 17.039; delta pareado −2,2 a −6,0 R$/op, IC inclui 0 em V1/V3 e fica abaixo de 0 em V2). V1a perde menos que sair cedo ao acaso (pct 100 no sorteio de instante) mas continua pior que a original; V2/V3 não se distinguem do acaso ou ficam abaixo. Nenhuma quebra com R$1.000. 36 células pareadas olhadas. Veredito: refutada.
Pré-registro (escrito antes de rodar; 6 variantes, nada além delas; 5 estratégias Win, Cinco, Desloc, RetEma34, WdoRet; Win_c1 fora):
- Famílias: tendência {Win, Cinco, Desloc}; retângulo {RetEma34, WdoRet}. "Contra" = voto == -lado da posição, numa M1 fechada t (bar contendo a entrada em diante), saída a mercado no `last` do 1º tick da M1 t+1; vale só se esse tick for anterior à saída original (senão a original vale). Saída a mercado declarada aceitável: é condicional tipo stop. Stop/alvo originais intocados.
- V1 = outra família INTEIRA contra (todos os membros votando contra); V2 = QUALQUER membro da outra família contra; V3 = qualquer outro membro da PRÓPRIA família (sem a própria) contra. Cada uma sem (a) e com (b) exigir posição no lucro no close da M1 t (lado*(close-entrada)>0): V1a,V1b,V2a,V2b,V3a,V3b.
- Pareado: R$ novo − R$ original por operação; IC 95% bootstrap por dia (2000 reamostras) da média sobre todas as ops e sobre as afetadas.
- Controle 1: instante sorteado (200): permuta dos atrasos (nº de M1 desde a entrada) das saídas disparadas entre as mesmas operações; mesma exigência de lucro nas versões (b). Percentil do ΔR$ total real.
- Controle 2: placebo (200): voto da outra família trocado por lado sorteado, persistente em cada trecho de voto contínuo (mesma atividade e cadência); percentil.
- Limitação declarada: as entradas seguintes da mesma estratégia no dia não são recalculadas (mesmas operações originais).
- Tabela: mês jan–out + total, sem custo e R$2/op, por estratégia e soma (5 sem Win_c1), caixa R$1.000 corrido por saída, quebra marcada.

## F — Veto cruzado por posição real contrária da outra família (ideia 4)
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: 3 células (f1, f2, f3) com 200 sorteios e placebo de lado da posição; posições conferem com `.posicao` da F0 (0 divergências); resultado.md/csv, trades f1/f2 e vetadas.
Falta: —
Arquivos: combinacoes/f_veto/ (f_veto.py, resultado.md, resultado.csv, trades/)
Resultado: o veto remove entradas que, somadas, ganham: f1 (193 vetadas) −3.209, f2 (290, NETTING) −4.044, f3 (123, contrária no lucro) −1.483 contra a soma sem filtro; R$2: −2.823 / −3.464 / −1.237. Percentil contra o sorteio 28–34 (pior ou igual ao acaso). Perde nas duas metades do ano. Nenhuma quebrou. Veredito: refutada, encerra.

<!-- Ideias 5 (ordem de chegada) e 6 (stop/alvo pela volatilidade do horário) foram incorporadas à frente B. Ideias 7–10 ficam fora por ora (sobreajuste alto ou análogo já refutado). -->

---

## N — Estratégia NOVA (1 ou 2), nascida dos conceitos das 6 — pedido do dono, 2026-10-06
O dono quer 1 ou 2 estratégias novas, livres (podem mudar totalmente o desenho), usando conceitos das 6. Os testes devem ser seguros, replicáveis e próximos da realidade, SEM gastar a base inteira na busca.

### Protocolo de dados (fixo — ninguém altera sem o orquestrador)
| Bloco | Período | Dado | Uso | Quantas vezes |
|---|---|---|---|---|
| DEV | 2022-01-03 → 2024-06-28 | WIN$N M1 cru (MT5), ticks gerados das M1 (4/M1, como dados.py) | exploração e ajuste livres | à vontade |
| VAL | 2024-07-01 → 2025-09-30 | idem | conferência das candidatas congeladas | UMA vez por candidata, no máx. 3 candidatas |
| HOLDOUT | 2026-01-02 → 2026-10-05 | WIN$N com ticks reais desde 20/02 (dados.py) | veredito final da candidata vencedora | UMA vez, só a congelada |
| FORWARD | out/2026 em diante | ao vivo/sombra | validação limpa de verdade | — |

Regras:
- Nada de olhar dados de 2026 (nem descritiva) na fase de desenho; os números já conhecidos do comparativo (tabela mensal) podem ser citados como motivação.
- Ressalva: 2026 está parcialmente contaminado, porque as 6 estratégias base foram escolhidas olhando 2026. O conceito vem delas.
- Os blocos 2022–2024 e 2025 já foram usados pela linha WinCincoMedias. Para uma estratégia NOVA isso é aceitável, mas não reutilize parâmetros afinados lá.
- Ao congelar uma candidata, grave regra, parâmetros e hash do arquivo em `n_nova/PREREGISTRO.md` ANTES de rodar VAL.
- Execução: mesmas regras do Testador (dados.py); entrada por ordem-limite ou a mercado conforme a estratégia, mas declarado; custo R$2/op sempre reportado junto.
- Critério de sucesso, definido antes:
  - VAL: lucro com custo > 0, ≥ 60% dos meses positivos, PF ≥ 1,2, sem quebrar com R$1.000, e acima do p95 de um controle aleatório de mesma frequência e mesmo horário;
  - HOLDOUT: com custo > 0 e sem quebra.

### N1 — Desenho e pré-registro
Status: [x] concluída
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito:
- DEV/VAL baixado: WIN$N M1 cru, 2021-12-01..2025-09-30, 530.220 barras, 958 dias, 0 fora da grade de 5.
- n_nova/dados_dev.py: DEV 622 pregões; VAL 315, conferido só que existe.
- Exploratória só no DEV: explora_1..6b.
- PREREGISTRO.md.
Falta: — (N2: rodar a grade de 12 células no DEV, aplicar a regra de escolha, congelar com hash, VAL única)
Arquivos: combinacoes/n_nova/ (baixa_dev.py, dados_dev.py, explora_lib.py, explora_1_regime.py … explora_6b_grade.py + *_stdout.log + *.parquet, PREREGISTRO.md); data/comparativo_win_2026/m1_WIN$N_2022_2025.parquet
Resultado: 1 candidata pré-registrada, RDT. A 2ª vaga fica vazia de propósito: 4 direções morreram no DEV.
- Retângulo em dia neutro: −24 pts/op.
- Gatilho roxa M5 a favor do regime: +7,7 bruto, −2,3 líquido.
- Reversão da 1ª hora: negativa já no bruto.
- Recuo fundo com impulso M30 de 5 EMAs: só 2023 é positivo.
Ponto fraco declarado: a RDT opera pouco, 1,3–2 operações/mês. A melhor célula do DEV teve 13/30 meses positivos (13/23 entre os meses com operação), então reprova a regra de ≥60% de meses lida ao pé da letra. O orquestrador decide a leitura ANTES do VAL.
Candidatas pré-registradas:
- **RDT — Recuo no Dia de Tendência.**
  - Regime (Deslocamento): às 10:30, |fech 10:29 − abertura| ≥ k·ATRd(14 D1) e nenhuma M1 fechada do outro lado da abertura ± 0,05 ATRd.
  - Entrada (família limite/retângulo): ordem-limite a favor em abertura + f·(fech 10:29 − abertura), válida até `ate`.
  - Stop a mercado na linha abertura ∓ 0,05 ATRd. Sem alvo, zera às 17:50 (família tendência). 1 operação/dia, 1 contrato.
  - Grade só no DEV: f {0,25; 0,5; 0,75} × ate {12:00; 14:00} × k {0,3; 0,4} = 12 células.
  - Regra de escolha: maior lucro/DD com vizinhos positivos e caixa mínimo ≥ R$500.
  - Controle: 200 sorteios de dia e lado, com a mesma contagem por mês, o mesmo horário e a mesma geometria em ATR.
  - Números do DEV, R$2/op: f 0,5 até 12:00 dá +R$2.169, 40 operações, PF 2,30, DD R$412, caixa mínimo R$1.210, +R$1.194 sem as 2 melhores; os três anos são positivos.
  - As 9 células f<1 da olhada prévia são todas positivas. O Deslocamento puro no mesmo bloco dá +R$2.509, mas o caixa vai a −R$787 (quebra).

### N2 — Desenvolvimento em DEV + VAL única
Status: [x] concluída — RDT REFUTADA no VAL
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: DEV 12 células; escolha f0,5/até 12:00/k0,4; congelada com SHA-256 ed31fee6...1fd36; VAL rodada UMA vez (n2_val_resultado.json existe: NÃO rodar de novo).
Falta: —
Arquivos: n_nova/n2_rdt.py, n2_resultado.md (relatório completo), n2_dev_grade.csv, n2_dev_ops.csv, n2_val_ops.csv, n2_val_resultado.json, logs n2_*_stdout.log
Resultado: VAL 12 ops, +R$215 com custo, PF 1,55, caixa mín R$734, 3/5 trimestres positivos (4/15 meses), passa 4 critérios e FALHA o controle aleatório (percentil 82; p95 = R$574). Sem as 2 melhores: −R$241. Veredito: REFUTADA, não vai ao holdout.

### N3 — HOLDOUT 2026 (uma vez)
Status: [ ] aguardando N2

---

## R — Ranking pelo critério do dono (2026-10-06, depois das frentes)
Correção do dono: uma estratégia NOVA é candidata se, com custo, rende mais que a PIOR das 6 originais no mesmo período (WinRetanguloEma34, +R$841 com R$2/op em 2026). Depois tabelar fator de recuperação, PF, acerto, DD etc. de todas e conferir qual se sobressai. Filtros sobre os mesmos robôs continuam comparados com a versão sem filtro do mesmo robô.
### R1 — RDT no HOLDOUT 2026 (uma vez, célula congelada)
Status: [x] concluída (2026-10-06) — holdout RODOU UMA VEZ, não rodar de novo
Justificativa da exceção: a regra de liberação mudou (dono, 2026-10-06): nova estratégia é candidata se, com custo, render mais que a pior das 6 originais no mesmo período (WinRetanguloEma34, +R$841). Isso só se mede em 2026, então o holdout foi aberto UMA vez para a RDT, mesmo refutada no VAL (percentil 82).
Adaptação (n2_rdt.py intocado, SHA conferido): r1_holdout.py troca o módulo `dados_dev` por um shim sobre `dados.py` (m1/ticks/dias de 2026; ticks reais desde 20/02) e amplia `explora_lib.vencimentos` para 2021–2026 (ATR D1 ajustado precisa dos vencimentos de dez/25–2026). Prova: o mesmo adaptador no VAL reproduz n2_val_ops.csv IDÊNTICO (12 ops, +R$215).
Resultado 2026 (célula f0,5/até 12:00/k0,4): 39 sinais, 14 ops; sem custo +R$283, com custo +R$255; PF 1,19; DD R$643; caixa mín R$714; sem quebra; 5/10 meses positivos; sem as 2 melhores −R$485. Controle 200 sorteios: p50 −95, p95 R$1.626, RDT no percentil 67,5. NÃO supera a pior das 6 (+R$841) -> não é candidata.
Arquivos: n_nova/r1_holdout.py, r1_RDT_2026.csv, r1_stdout.log
### R2 — Tabela de ranking (script `ranking.py` → `ranking.csv` + seção no HTML)
Status: [x] concluída — 18 candidatas (nova: líquido c/ custo > R$841; variante: também > o próprio original). RDT 2026 = +255, não passa. Seção "Candidatas" publicada na página do comparativo (ordenável).
Próximo passo sugerido: validar as candidatas fora de 2026 (bloco VAL jul/24–set/25, 2 vagas restantes de 3) — aguarda decisão do dono.

---

## V — Validação das candidatas fora de 2026 (pedido do dono: "teste o que merece ser validado")
Pré-registro: `v_validacao/PREREGISTRO_V.md`. Bloco VAL 2024-07 → 2025-09, rodada ÚNICA com Holm sobre 13 candidatas.
### V0 — Robôs e votos no período 2024-01 → 2025-09 (ports com dados trocados + votos + eventos)
Status: [x] concluída (2026-10-06)
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: shim + prova 2026 (5/5 byte-iguais) + 5 ports no periodo + votos_val + eventos_val + teste sem-futuro OK (3 cortes, 0 diferencas) + resumo.md
Falta: -
Arquivos: combinacoes/v_validacao/v0/: dados_val.py, roda_port.py, compara_prova.py, gera_votos_eventos.py, resumo.py, resultados/<robo>.csv, votos_val.parquet (247.353 M1 x 26), eventos_val.parquet (1.932 x 51), resumo.md, prova_2026/, logs/
Último resultado: VAL jul/24-set/25 (ops/líq sem custo): Win 320/-2.105, Win_c1 331/-1.026, Cinco 543/+16, Desloc 69/+3.810, RetEma34 163/-476. Periodo todo: 427/-1.788, 442/-700, 788/-52, 98/+3.324, 177/-758. WdoRetangulo neutro (voto/posicao 0). Sem avaliar candidatas.
### V1 — Refazer as candidatas em 2026 sem WdoRetangulo → congelar → VAL uma vez
Status: [x] concluída (2026-10-06) — VAL RODOU UMA VEZ, não rodar de novo (só v1_relatorio.py reconstrói o relatório)
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: reprodução COM Wdo 13/13 em 100%; 2026 sem Wdo: seguem 10 (C1,C4,C5,C7,C8,C9,C10,C11,C12,C13), caem C2 (Δ -258), C3 (-883), C6 (-90); CONGELADAS.md com SHA-256 antes do VAL; VAL 2024-07→2025-09 rodado uma vez (2.000 sorteios, Holm sobre 10); resultado.md/csv
Falta: -
Arquivos: combinacoes/v_validacao/v1/ (v1_regras.py, v1_2026.py, v1_niveis_val.py, v1_val.py, v1_relatorio.py, CONGELADAS.md, resultado.md, resultado.csv, reproducao_2026.csv, filtro_2026.csv, trades_val/, controles_val/, trades_2026_sem_wdo/, trades_2026_com_wdo/, val.log)
Último resultado / VEREDITO: 0 APROVADAS, 0 PROMISSORAS, 10 REFUTADAS no VAL. Melhor: C1 (Win_c1 filtro tabela) Δ +R$1.774 (de -1.688 para +86), FR 0,30 contra -0,75, mas p bruto 0,102 (Holm 0,92): fica fora até da PROMISSORA por 0,002. C4 corta o Deslocamento de 69 para 20 ops, Δ -1.415 (p 0,05 só diz que perde menos que cortar ao acaso). Saídas E: Δ entre -5 e +214, p bruto ≥0,52. C12 Δ -306. C13 -4.146 (p 0,81; quebra 30/10/2024). Nenhuma passa; o resultado de 2026 não se sustenta fora do ano.

---

## W — [SUBSTITUÍDA pela X, decisão do dono 2026-10-06: o filtro mensal não serve para EA] Win_c1 com o filtro pela nota NATIVO no EA (pedido do dono, 2026-10-06)
Regra aprovada: C1 (`v_validacao/v1/v1_regras.py::_core_c1` + `b_nota/comum.py`). O EA não tem os resultados dos outros robôs para treinar a tabela, então ela será traduzida para a forma fixa equivalente ("entra só se ≥ K dos outros votantes a favor"), conferida contra a versão walk-forward em 2026 e no VAL.
Status: [!] PARADA na etapa 1 — forma fixa diverge da aprovada; EA NÃO implementado (aguarda decisão do dono)
Fase: parada na etapa 1 (substituída pela X) [linha restaurada pelo orquestrador]
Feito: w_win_c1/forma_fixa.py (2026 e VAL; reusa v1_regras._core_c1/_carrega_b/_previsoes_b + comum.escolhe_limiar) -> forma_fixa_mes_{2026,val}.csv, forma_fixa_k_{2026,val}.csv, logs. A walk-forward reproduz o congelado (2026 sem Wdo: 173 ops / +3.680 com R$2 — o "146 ops" citado no pedido é a versão COM Wdo; VAL: 67 / +86).
Conjunto de fav (outros votantes a favor: Cinco, Desloc, RetEma34) mantido por mês:
- 2026: jan–mar todos (sem filtro: jan sem passado, fev–mar antes de MES_MIN_FILTRO=4); abr {0,2,3} (corta só fav=1, não é fav≥K); mai–out TODOS (frac 0: o passado nunca achou limiar que melhore). Regra mais recente aplicada em 2026 (out) = SEM FILTRO.
- VAL: jul–set/24 fav≥2; out–nov/24 fav≥3; dez/24–mar/25 {0,3}; abr/25 {0,2,3}; mai–set/25 {0,3}. Regra mais recente (set/25) = {0,3} ≈ fav≥3 (fav=0 quase não ocorre no Win_c1).
- A tabela não é monótona: P(fav=0) > P(fav=1) ≈ P(fav=2) < P(fav=3) em quase todo mês; por isso o conjunto vira {0,3} e não "≥K".
Forma fixa x aprovada (ops / líquido sem custo / com R$2):
| versão | 2026 | VAL |
|---|---|---|
| original sem filtro | 187 / +3.799 / +3.425 | 331 / −1.026 / −1.688 |
| walk-forward C1 (aprovada) | 173 / +4.026 / +3.680 | 67 / +220 / +86 |
| fav≥1 fixo | 184 / +3.835 / +3.467 | 325 / −1.158 / −1.808 |
| fav≥2 fixo | 93 / +3.161 / +2.975 | 168 / −745 / −1.081 |
| fav≥3 fixo | 11 / +850 / +828 | 20 / +128 / +88 |
| {0,3} fixo (último conjunto do VAL) | 14 / +814 / +786 | 26 / +260 / +208 |
Divergência: nenhum K reproduz as duas janelas. A regra mais recente de 2026 é "sem filtro" (K=0 = v2.05, nada a implementar); a do VAL é K=3, que em 2026 corta 162 de 173 operações (+3.680 -> +828). A aprovada se comporta como "sem filtro" em 2026 e como "≥3" no VAL porque a tabela é re-treinada em cada janela com passados diferentes.
Falta (só se o dono decidir): escolher entre (a) K=3 fixo (regra do VAL, opera ~1/mês em 2026), (b) não filtrar (regra atual de 2026), (c) outra forma; aí seguir etapas 2–5 (backup v2_05, v2.06 com FiltroVotos/VotosMinimos no fim, compilar 0/0, copiar ao terminal, espelho.py).
Arquivos: combinacoes/w_win_c1/ (forma_fixa.py, forma_fixa_mes_2026.csv, forma_fixa_mes_val.csv, forma_fixa_k_2026.csv, forma_fixa_k_val.csv, forma_fixa_2026.log, forma_fixa_val.log). mt5/Win_c1.mq5 intocado (v2.05).
Último resultado: forma fixa diverge; parado antes do EA.


---

## X — Robôs novos com REGRAS FIXAS (pedido do dono, 2026-10-06)
O dono rejeitou o ajuste mensal ("olhar o mês anterior é arriscado; não faz sentido olhar resultado de outros robôs"). Tudo aqui é regra FIXA, que um EA executa sozinho.
**Dados:** parâmetros escolhidos UMA vez no DEV (2022-01-03 → 2024-06-28) e congelados. Depois, conferência SEM mudar nada em VAL (2024-07 → 2025-09; bloco já usado por outras regras, mas nunca por estas) e em 2026 (com ticks reais).
**Votantes/robôs:** Win, Win_c1, WinCincoMedias, WinDeslocamentoMatinal, WinRetanguloEma34 (o WdoRetangulo está excluído). Na unanimidade, Win e Win_c1 contam como UM voto (votam igual).
**Critério do dono:** com custo, render mais que o pior robô original NO MESMO período, e tabela de indicadores (acerto, payoff, fator de lucro, maior queda, fator de recuperação, meses+, quebra). O percentil contra o sorteio também é reportado, como informação.

### X0 — Robôs e votos em 2022-01 → 2023-12 (completa a base DEV; a V0 já tem 2024-01 → 2025-09)
Status: [x] concluída (2026-10-06)
Fase: concluída [linha restaurada pelo orquestrador; o texto original se perdeu num sed de outro agente]
Feito: prova do shim 5/5 byte-igual (2026 jan-out); 5 robos 2022-01-03..2023-12-28; votos_dev (271.005x26), eventos_dev (2.483); teste sem-futuro OK (3 cortes, 0 dif); emenda com V0 sem buraco/duplicata; verificacao continua 2022-2025: 4 de 5 robos identicos, Desloc difere (saldo/teto 10%); resumo.md
Falta: -
Arquivos: combinacoes/x_fixas/x0/: dados_val.py, roda_port.py, gera_votos_eventos.py, juntar.py, resumo.py, resultados/, resultados_2022_2025/, votos_dev/eventos_dev.parquet, votos_2022_2025/eventos_2022_2025.parquet, continuo/ (+votos_cont/eventos_cont), resumo.md, logs/
Último resultado: 2022-23 ops/liq sem custo: Win 459/-1.484, Win_c1 482/-654, Cinco 946/+3.214, Desloc 85/+1.809 (0 overnight), RetEma34 511/-3.310 (rodado sem parar; quebraria em 2022-06). [corrigido 2026-10-06: Cinco e Desloc pós-X0b (zeragem no fim real do pregão); a versão original do X0 dava Cinco 946/+769 e Desloc 85/+1.634 com 30 overnight, porque nos dias de 17:54 a posição dormia até o leilão do dia seguinte. Win, Win_c1 e RetEma34 não mudam.] Ressalva: Desloc 2024-25 na emenda (V0, saldo reinicia em R$1.000) = 98/+3.324; rodada continua = 98/+3.405 (23 ops mudam, so o teto por saldo).
### X0b — zeragem no fim real do pregão
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: Desloc (zera fim_dia-5min, fim_dia limitado a 18:25) e Cinco (ZERAR=min(18:24, fim_dia-1)) rodados continuo 2022-01-03..2025-09-30, R$1.000, sem editar ports (patch em memoria); dias com pregao >=18:25 (631 de 958): 0 diferencas; Win/Win_c1/RetEma34 copiados de x0/continuo; votos_2022_2025 e eventos_2022_2025 refeitos; overnight/de outro dia depois = 0
Falta: -
Arquivos: combinacoes/x_fixas/x0b/: roda_x0b.py, ve.py, analise.py, resultados_2022_2025/, votos_2022_2025.parquet, eventos_2022_2025.parquet, resumo.md, logs/
Último resultado: Cinco 1734 ops, liq sem custo 717 -> 3.162 (com R$2: -2.751 -> -306); Desloc 183 ops, 5.039 -> 5.214 (com R$2: 4.673 -> 4.848). Dias afetados: Desloc 45, Cinco 123 (todos em dias com pregao < 18:25; 327 dias assim).
### X1 — UNANIMIDADE: robô novo que entra quando os 4 votos concordam
Pré-registro, fixado antes de rodar:
- **Sinal:** na abertura da M1 t+1, se os 4 votos (Win, Cinco, Desloc, RetEma34) na M1 t forem todos +1 (ou todos −1) e na M1 t−1 não eram (transição), envia uma ORDEM-LIMITE no fechamento de t, com prazo de 3 min. Não opera de 09:00 a 09:05 nem depois de 17:30. Zera às 17:50. 1 contrato, uma posição por vez.
- **Saídas (grade de 4 células, escolhida no DEV pela regra abaixo):**
  - U1: sai a mercado na M1 seguinte em que a unanimidade quebrar, com stop de proteção a 2×ATR14 M5;
  - U2: stop 1,5×ATR / alvo 3×ATR;
  - U3: stop 2×ATR / alvo 2×ATR;
  - U4: stop 1×ATR / alvo 2×ATR.
  
  Alvo por ordem-limite, stop a mercado.
- **Escolha no DEV:** maior lucro/DD entre as células com líquido com custo > 0 e sem quebra. Se nenhuma servir, a regra é REFUTADA no DEV e não segue.
Status: [x] concluída (2026-10-06) — REFUTADA no DEV
Fase: fim
Feito: DEV U1-U4 rodado (script x1.py). Líquido com custo: U1 -2.457 (702 ops), U2 -698 (227), U3 -232 (248; sem custo +264), U4 -1.629 (331). Nenhuma > 0 -> pela regra pré-registrada, REFUTADA; nada congelado; VAL e 2026 não rodados.
Falta: -
Arquivos: combinacoes/x_fixas/x1/ (x1.py, dev_tabela.md, resultado.md, trades/dev_U*.csv)

### X2 — SELETOR: robô novo que usa os outros como indicadores (1 contrato)
Pré-registro, fixado antes de rodar:
- **Sinal:** a entrada de um dos 5 robôs, tirada das operações dele. Se o seletor está fora, entra com o robô que sinalizou. Se mais de um sinaliza no mesmo minuto, escolhe pela prioridade fixa. Enquanto está posicionado, ignora os outros. Entrada, alvo, stop e saída são os do robô escolhido, exatamente como na operação dele.
- **Prioridade (3 variantes, todas reportadas):**
  - P1: fator de recuperação no DEV, desempate pelo acerto no DEV;
  - P2: acerto no DEV;
  - P3: ordem de chegada (sem prioridade).
- **Ranking calculado UMA vez no DEV e congelado.** A escolha da variante é feita no DEV (maior lucro/DD com custo, sem quebra).
- **Nota:** coincidência no mesmo minuto é rara. Na maior parte do tempo vale "quem chega primeiro". A diferença entre as variantes fica no desempate.
Status: [x] concluída (2026-10-06) - REFUTADA NO DEV
Fase: fim
Feito: DEV P1-P3 rodado; nenhuma variante com liquido c/ custo > 0 sem quebra (P1 -819, P2 -881, P3 -1.183, todas quebram; FR -0,26/-0,29/-0,41). VAL e 2026 nao rodados (regra: parar).
Falta: -
Arquivos: combinacoes/x_fixas/x2/ (seletor.py, CONGELADA.md, resultado.md, ranking_dev.csv, dev_variantes.csv)
Último resultado: ranking DEV c/ custo: Desloc +1.428 (FR 1,56), Cinco +764 (0,27), Win_c1 -1.514, Win -2.299, RetEma34 -4.642. Seletor perde das 2 melhores isoladas (so Desloc e Cinco positivos).

---

## Y — Os mesmos robôs em OUTROS TEMPOS GRÁFICOS (pedido do dono, 2026-10-06)
Pergunta: os robôs se comportam de maneira diferente em outros tempos gráficos? É uma LEITURA comparativa e nada é adotado aqui. Um tempo gráfico só vira candidato se for positivo com custo em TODOS os anos de 2022 a 2025 e também em 2026, e mesmo assim vai para o forward de outubro antes de qualquer EA.

**Regras fixas para todos:**
- Parâmetros iguais aos do EA (mesmos números); só o tempo gráfico muda.
- Filtros de tempo gráfico superior escalam junto: "superior" = o próximo da lista do MT5 que seja ≥ 3× a base. Documente cada caso.
- Prazos em barras continuam em barras, como o EA faria se o tempo gráfico fosse trocado.
- Prazos em minutos continuam em minutos.
- Horários (zeragem, decisão das 10:30) não mudam.
- Na versão no tempo gráfico NATIVO, o port parametrizado deve reproduzir o original byte a byte (2026 e um ano da base 2022–25). Sem isso, nada vale.

**Dados:**
- 2022-01 → 2025-09: shim da `x_fixas/x0b`, que já corrige o fim real do pregão, com ticks sintéticos 4/M1.
- 2026: `dados.py`, com ticks reais desde 20/02.

**Saída:** tabela por robô × tempo gráfico × ano (2022, 2023, 2024, 2025 até set, 2026 até 05/10), com custo de R$2/op. Colunas: operações, líquido, acerto, fator de lucro, maior queda e "anos +". Arquivos em `combinacoes/y_tempos/<robo>/`.

### Y1 — Win e Win_c1 (nativo M5, filtro M15). Grade: M1, M2, M3, M5, M10, M15, M30
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: port_win_tf.py; PROVA M5 4/4 BYTE-IGUAL (2026 e 2022-25, Win e Win_c1; prova.py); grade 28 rodadas; relatorio.py.
Falta: -
Resultado: NENHUM candidato (nenhum tf positivo com custo nos 5 anos). Melhor: M30 3/5 anos + (Win_c1 +736 total, Win −65); M1 perde 34 mil. Só 2026 é positivo em M2–M5/M15. Filtro superior: M2→M6 (regra ≥3×), não M10.
Arquivos: combinacoes/y_tempos/win/ (port_win_tf.py, roda_y1.py, prova.py, grade.py, relatorio.py, resultado.md, resultado.csv, trades/, logs/)
Nota: regra "próximo MT5 ≥3× a base" dá M2→M6 (não M10); usei M6. Tabela SUP em port_win_tf.py.
Feito:
Falta:
Arquivos:
Último resultado:

### Y2 — WinCincoMedias (nativo M30; Supertrend H1). Grade: M5, M10, M15, M20, M30, H1, H2
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: port_cinco_tf.py, roda_y2.py, prova 2/2 byte-igual (cmp); grade 7 TFs x 2 periodos; agrega.py -> resultado.md/.csv
Falta: -
Arquivos: combinacoes/y_tempos/cinco/ (port_cinco_tf.py, roda_y2.py, agrega.py, resultado.md/.csv, prova/, trades/, logs/)
Resultado (c/ custo R$2, 2022/23/24/25/26): M5 -1346/-4367/-5337/-1923/+2407 (1 ano+); M10 3 anos+; M15 3; M20 4 (2024 -3001); M30 nativo 3 (2022 -939, 2024 -1942); H1 4 (2022 -1406); H2 5 de 5: +1446/+1232/+1291/+657/+3196 (ops 198/169/193/130/131, FP 1,09-1,28). Candidato: H2 (Supertrend H4).
Feito:
Falta:
Arquivos:
Último resultado:

### Y3 — WinDeslocamentoMatinal (nativo M1; decisão às 10:30). Grade: M1, M2, M3, M5, M10, M15, M30
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: prova byte a byte M1 (2026 e 2022-25 X0b) OK; grade 7 tempos x 5 anos; tabela.
Falta: -
Arquivos: combinacoes/y_tempos/desloc/ (port_desloc_tf.py, run_y3.py, tabela.py, resultado.md/.csv, trades/, prova/, grade.log)
Último resultado: com R$2/op, total 2022-26: M1 +6.937 (248 ops, 5/5 anos+), M2 +6.288 (5/5), M3 +5.355 (4/5; 2022 -214), M5 +4.517 (4/5; 2022 -257), M10 -697, M15 -744, M30 -817 (quebram em 2023 e ficam sem operar; M10+ também perdem dias por janela de 5 min com 1a barra 09:02-09:04). Candidatos (5 anos+): M1 (nativo) e M2. Nenhum tempo supera o M1 em total; M3/M5 ganham do M1 só em 2025.

### Y4 — WinRetanguloEma34 (nativo M1; input TimeframeBase). Grade: M1, M2, M3, M5, M10, M15
Status: [x] concluída (2026-10-06) — NENHUM candidato
Fase: fim
Feito: port_ret_tf.py (cópia parametrizada, escolhas documentadas no docstring); PROVA M1 byte a byte OK em 2026 (733 ops, +2.307 sem custo) e 2022-25 (688 ops, -4.068); grade M1,M2,M3,M5,M10,M15 nos 2 períodos; resultado.md/.csv; trades/.
Falta: —
Arquivos: combinacoes/y_tempos/retangulo/ (port_ret_tf.py, run_tf.py, grade.sh, relatorio.py, resultado.md, resultado.csv, trades/, prova/)
Último resultado: líquido c/ custo total 2022-2026: M1 -4.603 (1/5 anos +), M2 -7.542 (1/5), M3 +461 (2/5; 2025 +552, 2026 +1.648; 2022-24 negativos), M5 -1.318 (2/5), M10 e M15 = 0 operações por construção (detector exige 60 velas no dia; M10 tem 48, M15 32). Candidato (positivo nos 5 anos): nenhum.

### Y1b — Win e Win_c1 em tempos MAIORES (pedido do dono, 2026-10-06). Grade: H1, H2, H3, H4
Mesmas regras da seção Y e o mesmo `y_tempos/win/port_win_tf.py`, cuja prova já foi feita na Y1. O filtro superior segue a mesma regra, o próximo tempo do MT5 ≥ 3× a base: H1→H3, H2→H6, H3→H12, H4→H12. Nesses tempos o pregão tem poucas velas, então é preciso conferir que o robô opera de fato e reportar as operações por ano.
Status: [x] concluída (2026-10-06) — NENHUM candidato
Fase: fim
Feito: wrapper roda_y1b.py (SUP H1->H3, H2->H6, H3->H12, H4->H12; port_win_tf.py intocado), grade 16 rodadas, relatorio_b.py, resultado_maiores.md/.csv. Sanidade: todos operam (H1 18-45/ano, H2 20-46, H3 8-17, H4 8-16). Entradas só em horas de abertura de vela: H1 10/12/13/14h, H2 10/12/14h, H3 e H4 só 12h (as demais caem em 11/15/16/17 sem entrada ou depois do fim).
Falta: -
Arquivos: y_tempos/win/ (roda_y1b.py, grade_b.py, relatorio_b.py, resultado_maiores.md/.csv, trades/*_M60|120|180|240_*.csv)
Último resultado: líquido c/ custo total 2022-26: Win H1 +1570 (3/5 anos), H2 -2474 (1/5), H3 +1649 (3/5), H4 +18 (2/5); Win_c1 H1 +2267 (4/5; 2024 -391), H2 -638 (1/5), H3 +18 (3/5), H4 -231 (2/5). Candidato (5/5 anos): nenhum; o mais perto é Win_c1 H1.

---

## Z — Tempos gráficos escolhidos pelo dono viram PADRÃO nos EAs e no código de teste (2026-10-06)
Escolha do dono:
- WinDeslocamentoMatinal M1, que já é o nativo; o EA calcula em M1 internamente, então não muda;
- WinCincoMedias H2, com Supertrend H4;
- Win_c1 H1, com filtro H3;
- Win H1, com filtro H3.

O tempo fica FIXO no código, sem input, como o dono pediu antes para o CincoMedias. Versão anterior guardada em .bak. A compilação deve sair com 0 erros e 0 avisos e o EA é copiado para MQL5\Experts. O port Python passa a ter o novo tempo como padrão, e o EA tem de bater com o port, com o número esperado no Testador.

### Z1 — Win e Win_c1 → H1 (filtro H3)
Status: [x] concluída (2026-10-06)
Fase: fim
Resultado: EAs Win v2.05 / Win_c1 v2.06 em H1 (filtro H3) fixos no código, 0 erros/0 avisos, em MQL5\Experts. Port padrão H1 = Y1b byte a byte. Esperado no Testador WINV26 13/08–30/09 sem custo (port H1 sobre M1+ticks do WINV26): Win 2 ops +R$10 (31/08 10:00 C zera; 08/09 13:00 C zera); Win_c1 3 ops +R$5 (31/08 10:00 C BE 11:16; 31/08 12:00 C zera; 08/09 13:00 C BE 13:15). Com WIN$N aparece mais 1 venda 14/08 14:00 (Win stop −197; c1 BE −1): é aquecimento — o WIN$N tem salto de ~3.500 pts na rolagem 12/08 e o Testador aquece no histórico do WINV26.
Arquivos: mt5/Win.mq5, Win_c1.mq5 (+ .ex5, _compile.log, Win_v2_04.mq5.bak, Win_c1_v2_05.mq5.bak); port_win_padrao.py; resultados/Win.csv, Win_c1.csv (H1); resultados_M5_historico/; combinacoes/z_padrao/ (z1_testador_esperado.py, m1_WINV26.parquet, z1_*_WINV26.csv, z1_*_WIN$N.csv)
Fase anterior: 6 — número esperado no Testador (WINV26 13/08–30/09)
Feito: leitura; backup mt5/Win_v2_04.mq5.bak e Win_c1_v2_05.mq5.bak; EAs editados (Win v2.05, Win_c1 v2.06: const TempoGrafico=H1/TempoFiltro=H3, PeriodSeconds no filtro, aviso no Diário se gráfico ≠ H1); compilados 0 erros/0 avisos (mt5/Win_compile.log, Win_c1_compile.log), .mq5/.ex5 copiados p/ MQL5\Experts (hash igual); port_win_padrao.py criado e rodado: resultados/Win.csv (22 ops, +1.404 s/ custo) e Win_c1.csv (32, +1.541) BYTE-IGUAIS a y_tempos/win/trades/*_M60_2026.csv; M5 antigos em resultados_M5_historico/; número esperado no Testador (acima)
Falta: -

### Z2 — WinCincoMedias → H2 (Supertrend H4) + zeragem antes do fim real do pregão
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: backup mt5/WinCincoMedias_v2_03.mq5.bak; EA v2.04 (TempoGrafico H2, TempoSupertrend H4, Supertrend ate = t1 - PeriodSeconds(TempoGrafico), MinutoZerarHoje = min(18:24, fim da sessão − 1) via SymbolInfoSessionTrade, fallback 18:24; inputs com os mesmos nomes); compilado 0 erros/0 avisos, .mq5/.ex5 em MQL5\Experts (hash igual). port_cinco_medias_padrao.py (importa y_tempos/cinco/port_cinco_tf com tf=120 + zeragem X0b); CSV M30 movido p/ resultados_M30_historico/; novo resultados/WinCincoMedias.csv = cinco_M120_2026.csv da Y2 (DataFrame.equals True; só o rótulo "Supertrend H4 contra").
Falta: -
Arquivos: mt5/WinCincoMedias.mq5/.ex5/_compile.log, mt5/WinCincoMedias_v2_03.mq5.bak, comparativo_win_2026/port_cinco_medias_padrao.py, resultados/WinCincoMedias.csv, resultados/WinCincoMedias_esperado_testador_WINV26.csv (e _WINN.csv), resultados_M30_historico/WinCincoMedias.csv
Último resultado: 2026 H2 sem custo 131 ops, +R$3.458 (todo pregão de 2026 vai até 18:25 → zeragem 18:24, igual à Y2). Esperado no Testador (WINV26 13/08–30/09, ticks reais, R$1.000, sem custo): 23 ops, +R$500 (com M1 WIN$N: 24 ops, +R$851; a diferença é só 1 trade, 21/08 10:00, +R$351, sensível ao aquecimento das EMAs no WINV26).

### Y4b — WinRetanguloEma34 adaptado para tempos maiores (pedido do dono, 2026-10-06). Grade: M1, M2, M3, M5, M10, M15, M20, M30, H1, H2, H3, H4
Do M10 em diante o EA não opera porque três regras foram feitas para o M1. Ajustes PRÉ-REGISTRADOS, iguais em todos os tempos (versão "RetTF"):
- **A. Janela entre dias.** O detector usa as últimas 20 velas FECHADAS, mesmo que venham do pregão anterior. Cai a exigência de 3×janela = 60 velas no dia. O retângulo continua morrendo pelas regras do EA.
- **B. Corte de entrada antes da zeragem.** Passa a ser min((TTL+1) × vela, 60 min) antes das 17:00. No M1 dá 11 min, como hoje. No H1 ficaria em 11 h sem o teto.
- **C. Descarte de vela ruim.** O limite passa a ser 2.000 × √(minutos da vela): 2.000 no M1, ~6.300 no M10, ~15.500 no H1, ~31.000 no H4. A amplitude normal cresce com a raiz do tempo.
- **Inalterados:** largura mínima de 328 pts, tolerância, frações de alvo e stop, aproximação do alvo a cada 5 velas, EMA34, TTL de 10 velas e zeragem às 17:00.

Reportar as duas versões, a ORIGINAL (já medida na Y4, do M1 ao M5) e a RetTF, em todos os tempos, para separar o efeito dos ajustes do efeito do tempo. Candidato: positivo com custo nos 5 anos, mais o saldo mínimo recomeçando com R$1.000 a cada ano.
Status: [x] concluída (2026-10-06) — NENHUM candidato
Fase: fim
Feito: port_ret_tf_v2.py (flag ajustes); PROVA ajustes=False byte-igual (cmp) no M1 2026, M1 2022-25, M3 2026 e M3 2022-25; grade RetTF 12 tempos x 2 períodos; resultado.md/.csv; sanidade H1-H4.
Falta: —
Arquivos: combinacoes/y_tempos/retangulo/y4b/ (port_ret_tf_v2.py, run_y4b.py, grade.sh, relatorio_y4b.py, sanidade_h.py, resultado.md, resultado.csv, trades/rettf_*, prova/)
Último resultado: RetTF líquido c/ custo total 2022-26: M1 -5.564 (1/5 anos +), M2 -9.679 (1/5), M3 -2.761 (2/5), M5 -3.024 (1/5), M10 -1.706 (2/5), M15 +1.388 (3/5; 2024 -1.061), M20 -2.441, M30 -3.440, H1 -31 (3/5), H2 -294 (3/5), H3 -393 (0/5), H4 -131 (2/5). Os ajustes não melhoraram o M1-M5 (pioram vs ORIGINAL). Candidato 5/5: nenhum. H3/H4 quase sem operar (7 ops em 5 anos, 0 em 2026): ~3 velas válidas/dia (08h/09h caem no filtro do leilão), 6-7 retângulos formados em 2026 mas nenhuma entrada passa nos filtros. Extras: reset diário só de retângulo/pendente (histórico de velas mantido, pré-carregado); zeragem 17:00 só em vela nova (H2/H3 às 18:00; H4 sai por fim_dados); vela de ontem processada de manhã pode armar entrada (H3).

### Z3 — WinRetanguloEma34 → M15 AJUSTADO (versão RetTF da Y4b) como padrão (dono, 2026-10-06)
O EA passa a operar em M15, tempo fixo no código, com os ajustes A, B e C da Y4b e as adaptações extras que a Y4b documentou: reset diário do retângulo e da ordem pendente, histórico entre dias, filtro de leilão mantido, e a última vela do dia anterior processada de manhã. A versão anterior, v1.04, fica em .bak. Port padrão novo; a referência é `y_tempos/retangulo/y4b/port_ret_tf_v2.py` (M15, ajustes=True).
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: backup mt5/WinRetanguloEma34_v1_04.mq5.bak; EA v1.05 (const TempoGrafico=M15 sem input; histórico de velas entre dias, pré-carregado com 600 velas M15 na 1ª vela e limitado a 3×janela; ResetSessao zera só retângulo/pendente; corte de entrada min((TTL+1)×vela, 60) = 16:00; descarte = RangeMaximoBarraPontos(2000, ref. M1)×√min = 7.746 no M15; leilão <09:01 mantido); compilado 0 erros/0 avisos; .mq5/.ex5 em MQL5\Experts (hash igual). port_retangulo_ema34_padrao.py (tf=15, ajustes=True); CSV M1 movido p/ resultados_M1_historico/; novo resultados/WinRetanguloEma34.csv BYTE-IGUAL (cmp) a y4b/trades/rettf_M15_2026.csv (83 ops, +1.636 s/ custo, +1.470 c/ custo).
Falta: -
Arquivos: mt5/WinRetanguloEma34.mq5/.ex5/_compile.log, mt5/WinRetanguloEma34_v1_04.mq5.bak; comparativo_win_2026/port_retangulo_ema34_padrao.py; resultados/WinRetanguloEma34.csv (M15); resultados_M1_historico/WinRetanguloEma34.csv; combinacoes/z_padrao/z3_testador_esperado.py; esperado_testador/WinRetanguloEma34_esperado_testador_WINV26.csv (e _WINN.csv)
Último resultado: esperado no Testador (WINV26 13/08–30/09, ticks reais, R$1.000, sem custo; port M15 sobre M1+ticks do WINV26): 8 ops, +R$200 (01/09 09:31 C alvo +124; 01/09 10:20 C stop −62; 11/09 09:59 V stop −122; 11/09 10:28 V alvo +245; 15/09 10:13 C stop −95; 15/09 10:31 V stop −95; 15/09 10:48 C alvo +169; 28/09 15:58 V zera 17:00 +36). Com ticks do WIN$N: 10 ops, +R$251 (mais 18/08 09:30 V stop −51 e 10:01 C alvo +102) — o WIN$N tem 1 tick por dia às 18:30 que vira uma vela M15 a mais no histórico entre dias; os ticks do WINV26 acabam 18:27.

### Z4 — Por que o WinRetanguloEma34 M15 ajustado quebra em 2024, e um filtro que resolva SEM ser só de 2024 (dono, 2026-10-06)
Protocolo fixo:
- **Etapa 1, diagnóstico:** de onde vem a perda de 2024 (−1.061, saldo mín. −230). Cortes por mês, hora, lado, largura do retângulo em pts e em ATR, ATR diário, tendência do dia, distância da EMA34, motivo de saída e duração. Cada corte é comparado com 2022, 2023, 2025 e 2026. É descritivo; não decide nada.
- **Etapa 2, filtros:** no MÁXIMO 4, cada um com mecanismo de mercado explicável, poucos parâmetros e valores escolhidos olhando só 2024. São escritos aqui ANTES de medir os outros anos.
- **Etapa 3, conferência nos anos que não criaram o filtro** (2022, 2023, 2025 e 2026). APROVADO só se tudo abaixo valer:
  - 2024 não quebra (saldo recomeçando com R$1.000);
  - melhora com custo em ≥ 3 dos 4 outros anos;
  - nenhum ano quebra;
  - o total dos 4 outros anos fica acima do p95 de um filtro aleatório que corta a mesma fração de operações em cada ano (1.000 sorteios).
- Com 4 filtros, um passar por acaso é possível; o percentil é reportado junto.
Status: [x] concluída (2026-10-06) — os 4 filtros REFUTADOS
Fase: fim
Feito: leitura do protocolo; wrapper port_z4.py (monkeypatch do port Y4b, filtro aplicado ao ARMAR a entrada + contexto da entrada) — sem filtro dá operações IGUAIS a rettf_M15_*.csv; roda_z4.py; comum.py. Vela pós-pregão (pedido do orquestrador): WIN$N 2026 tem 1 tick às 18:30 em 157/157 dias de tick real → 156 velas M15 pós-18:25 entram no histórico em 2026; 2022–25 = 0 (M1 termina 18:24). Em 2026, 60 de 83 ops vêm de retângulo com essa vela na janela (48) ou na amplitude (60). Base sem o tick 18:30 (`roda_z4.py ... sempos`): 2022–2025 idênticos (2024 segue −1.061, quebra −230); 2026 +1.470 (83 ops) → +1.954 (84 ops), saldo mín 217 nos dois; 60 ops comuns. A quebra de 2024 NÃO muda; conferência de 2026 nas duas versões da base.
Etapa 1 FEITA (diagnostico.md, diag_tabelas.md, diagnostico.py, trades/base_enriquecido.csv). Etapa 2 FEITA (filtros.py). Etapa 3 FEITA (conferencia.py/.md/.csv, port re-rodado com o filtro ao armar; sorteio sobre linhas do CSV da base, mesma fração por ano, 1.000). Etapa 4 FEITA (resultado.md).
Falta: —
Arquivos: combinacoes/z4_ret2024/ (port_z4.py, roda_z4.py, comum.py, diagnostico.py/.md, diag_tabelas.md, filtros.py, conferencia.py/.md/.csv/.log, resultado.md, trades/)
**Resultado final:** os 4 evitam a quebra de 2024 (saldo mín 622–927), mas TODOS melhoram só 2022 e 2023 e pioram 2025 e 2026 (2/4). Líquido c/ custo 2022/2023/2024/2025/2026 (base +70/−98/−1.061/+1.007/+1.470): f1 +235/−359/−159/+1.204/+790 (pct 23,6); f2 +1.111/+1.356/+272/−13/−1.032 QUEBRA 2026 (pct 52,2); f3 +1.024/+140/−23/+507/+1.196 (total 4 anos +2.867 vs base +2.449, pct 94,6, p95 +2.897); f4 +1.028/+277/−148/+328/+692 (pct 72,8). Sem o tick 18:30 em 2026: mesmos vereditos (f3 pct 88,5). Leitura: a perda de 2024 é um regime (manhã/dia parado perde em 2022–24 e paga em 2025–26), não um defeito filtrável.
Diagnóstico (etapa 1): perda de 2024 = decisões de MANHÃ (antes das 12h: 73 ops −1.231; ≥12h: 62 ops +170; 9:30–9:59 sozinho 23 ops −969, 10% acerto), sobretudo manhã com o dia ainda parado (amplitude < 0,5 ATR D1: −1.147), via stop rápido (34 dos 40 stops em ≤20 min são de manhã); ano de menor volatilidade (faixa diária 1.599 vs 1.835–2.194); quebra em ago, perda formada em jul (24 ops −552). ATENÇÃO: o diagnóstico (obrigatório comparar com outros anos) já mostrou que manhã×tarde INVERTE em 2025/2026; amplitude do dia é monotônica nos dois grupos.
Filtros pré-registrados (etapa 2): `z4_ret2024/filtros.py` SHA-256 c339089992cbf87bb7af0302360b0ab5349a02d2cac4c7fb4b86f9857aa3e081. Aplicados ao ARMAR a entrada (wrapper port_z4.py); valores só de 2024.
- f1: não arma com decisão (fim da vela M15) antes das 10:00 — janela quase toda do pregão anterior; 2024 9:30–9:59 = 23 ops −969.
- f2: não arma com decisão antes das 12:00 — manhã inteira; 2024 <12h 73 ops −1.231, ≥12h +170.
- f3: só arma se amplitude do pregão até a decisão ≥ 0,5 × ATR14 D1 (pregões anteriores) — dia comprimido, expansão atropela o stop curto; corte no meio dos quintis de 2024.
- f4: bloqueia só (decisão < 12:00 E amplitude < 0,5 ATR D1) — célula de 2024 = −1.147, resto do ano +86.

### Z5 — Varredura do limite do f3 (dono, 2026-10-06): "testar outros ranges de ATR para ver se a melhora é constante e se tem algum melhor"
Filtro f3: só arma a entrada se a amplitude do pregão até a decisão ≥ k × ATR14 D1. Grade fixa: k ∈ {0 (sem filtro), 0,2, 0,3, 0,4, 0,5, 0,6, 0,7, 0,8, 1,0}.
Duas bases: (i) oficial da Y4b; (ii) SEM as velas pós-pregão (tick das 18:30 do WIN$N em 2026), que é o que o EA real vê.
**Leitura pré-definida:**
- A melhora é "constante" se a curva total × k for um platô suave, ou seja, se os vizinhos do melhor k ficam perto dele. Se for pico isolado, não é.
- Para cada k: anos que melhoram contra k = 0, quebra, total dos 5 anos e percentil contra o sorteio de mesma fração (1.000 sorteios).
- Escolher o melhor k olhando os 5 anos é ajuste dentro da amostra. Por isso o k sugerido é o CENTRO do platô, e não o pico.
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: roda_z5.py (reusa port_z4); prova: k=0 = base e k=0,5 = f3 da Z4, operações idênticas nas 2 bases; grade 9 k x 2 bases; resultado.md/.csv
Falta: —
Arquivos: combinacoes/z5_f3_varredura/ (roda_z5.py, grade_z5.py, analisa_z5.py, resultado.md, resultado.csv, trades/)
Último resultado: total 5 anos (oficial) k0 +1.388, 0,2 +1.964, 0,3 +1.547, 0,4 +2.164, 0,5 +2.844 (p97,7; 4 anos p94,2), 0,6 +2.185, 0,7 +1.076, 0,8 +220, 1,0 +697. Morro largo 0,4–0,6, não pico isolado; centro 0,5 (= pico). Melhora NÃO constante: 3/5 anos (2022–24 melhoram, 2025 e 2026 pioram; 0,5: +954/+238/+1.038/−500/−274). Sem quebra para k>0. Sem pós-pregão: mesmo desenho (0,5 +2.818, p95,3).

### Z6 — Aplicar f3 (k = 0,5) no EA WinRetanguloEma34 → v1.06 (dono, 2026-10-06, depois da Z5)
Filtro: só arma a entrada se a amplitude do pregão até a decisão for ≥ 0,5 × ATR14 D1. Input `FiltroAmplitudeATR = 0.5`, e 0 desliga. A referência é `z5_f3_varredura/roda_z5.py` com k = 0,5 na base SEM velas pós-pregão.
O port padrão passa a ignorar as velas depois do fim do pregão, como no contrato real: 2026 esperado = +1.170 com custo.
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: backup mt5/WinRetanguloEma34_v1_05.mq5.bak; EA v1.06 (input FiltroAmplitudeATR=0.5 no fim, 0 desliga; definição = port_z4: decisão = fim da vela M15; amplitude = máx−mín das M1 do dia (desde 00:00; no WIN não há M1 antes das 09:00) com abertura ≤ decisão−1 min; ATR14 D1 = média SIMPLES do TR dos 14 pregões anteriores, D1 montado das M1; bloqueio filtrado logo antes de ArmarEntrada, sem mudar estado, com Print da amplitude e do ATR). Pós-pregão: vela que abre ≥ fim da sessão (SymbolInfoSessionTrade; fallback 18:25 se ausente ou fora de [zeragem, 18:30]) é ignorada e no lugar dela processa a última vela da sessão ainda não processada (= base sem pós da Z4, onde a 18:15 entra de manhã); também fora do pré-carregamento; no WINV26 é no-op. Compilado 0 erros/0 avisos; .mq5/.ex5 em MQL5\Experts (hash igual). port_retangulo_ema34_padrao.py = port_ret_tf_v2 + port_z4.instala(f3 0,5, sem_pos) sem editar os dois.
Falta: —
Arquivos: mt5/WinRetanguloEma34.mq5/.ex5/_compile.log, mt5/WinRetanguloEma34_v1_05.mq5.bak; comparativo_win_2026/port_retangulo_ema34_padrao.py; resultados/WinRetanguloEma34.csv (v1.06); resultados_M15_v105_historico/WinRetanguloEma34.csv; combinacoes/z_padrao/z6_testador_esperado.py; esperado_testador/WinRetanguloEma34_v106_esperado_testador_WINV26.csv (e _WINN.csv)
Último resultado: 2026 = 48 ops, +1.266 s/ custo, +1.170 c/ custo, 246 armações bloqueadas; as 48 operações IGUAIS (10 colunas) a z5_f3_varredura/trades/k0.5_2026_sempos.csv. Esperado no Testador (WINV26 13/08–30/09, ticks reais, R$1.000, sem custo): 5 ops, +R$221 (01/09 09:31 C alvo +124; 01/09 10:20 C stop −62; 11/09 09:59 V stop −122; 11/09 10:28 V alvo +245; 28/09 15:58 V zera 17:00 +36); 22 armações bloqueadas. Contra a v1.05 (8 ops +200) saem as 3 de 15/09 (−95/−95/+169). Com ticks do WIN$N dá o MESMO (5 ops +221): a proteção pós-pregão elimina a diferença WIN$N×WINV26 da Z3.

### Z7 — Regra GENÉRICA para dias extremos, motivada por 01–05/10/2026 (eleição: gap de +9,2% em 05/10) — dono, 2026-10-06
Os 3 pregões de outubro somaram −1.601, a pior janela de 3 pregões de 2026. NÃO se ajusta nada a outubro. Testa-se uma regra genérica nos 5 anos. 2022 também teve eleição (02/10 e 30/10), o que serve de teste natural.
**Regras pré-registradas** (bloqueiam o DIA inteiro, para os 5 robôs; ATR14 D1 = média simples dos 14 pregões anteriores):
- G1: gap de abertura |abertura − fechamento anterior| ≥ k × ATR, com k ∈ {1,0; 1,5; 2,0};
- G2: dia seguinte a um pregão com amplitude ≥ m × ATR, com m ∈ {2,0; 2,5}.

O gap da troca de contrato do WIN$N NÃO conta, porque não é movimento de mercado. Nesses dias o gap é medido contra o fechamento do MESMO contrato, ou o dia é excluído do G1; documente qual opção foi usada.

**Robôs nos padrões atuais:** WinCincoMedias H2, WinDeslocamentoMatinal M1, Win_c1 H1, Win H1 e WinRetanguloEma34 v1.06. Período 2022-01 → 2026-10-05, custo de R$2/op. Os robôs são de day trade, então bloquear um dia = remover as entradas daquele dia.

**Critério:** uma regra passa se, na SOMA dos 5 robôs, melhorar com custo em ≥ 4 dos 5 anos (2026 incluído; outubro é só um dos meses) e ficar acima do p95 de um sorteio que bloqueia o mesmo número de dias por ano (1.000 sorteios). Reportar também por robô, e a lista dos dias bloqueados com o que aconteceu (gap, amplitude, data).
Status: [x] concluída (2026-10-06)
Fase: fim
Feito: diárias, G1 (3 k) e G2 (2 m), 1.000 sorteios, por robô; 0 operações atravessam a noite; rolagem tratada (WIN$N salta NO DIA DO VENCIMENTO, não no seguinte; esse dia foi excluído do G1)
Falta: —
Arquivos: combinacoes/z7_dias_extremos/ (z7.py, resultado.md, resultado.csv, dias_bloqueados.csv, base_por_ano_robo.csv)
Último resultado: VEREDITO — G1 k=1,0 APROVADA (10 dias; 4/5 anos melhores, 2023 sem bloqueio; +1.749 sobre base 21.414; p99,8); G1 k=1,5 REFUTADA (3/5 anos, +1.318, p99,8); G1 k=2,0 REFUTADA (1/5, +542, p95,5); G2 m=2,0 REFUTADA (2/5, −506, p46,6); G2 m=2,5 REFUTADA (1/5, −806, p15,3). Ressalvas: 2026 do k=1,0 depende de 05/10 (+542; sem ele 2026 = −247 e vira 3/5); ganho vem quase todo do CincoMedias; 5 regras testadas sem correção de multiplicidade.

### Z8 — Aplicar a regra G1 (k=1,0) nos 5 EAs (dono, 2026-10-06: "Sim, coloque")
Regra: não abre posição no dia em que |abertura − fechamento anterior| ≥ `NaoOperarGapATR` × ATR14 D1 (média simples do TR dos 14 pregões anteriores). O input vai no FIM da lista, com padrão 1,0; 0 desliga. A definição é EXATAMENTE a de `z7_dias_extremos/z7.py`, inclusive a exclusão do dia do vencimento quando o símbolo é contínuo.
EAs:
- Win v2.05 → v2.06
- Win_c1 v2.06 → v2.07
- WinCincoMedias v2.04 → v2.05
- WinDeslocamentoMatinal v1.30 → v1.31
- WinRetanguloEma34 v1.06 → v1.07

Cada um com .bak, compilação 0/0, cópia para Experts, port padrão Python com a regra, `resultados/` 2026 regenerado e número esperado no Testador.
Status: [x] concluída (2026-10-06)
Fase: fim
**Resultado final:** 5 EAs com a regra (Win v2.06, Win_c1 v2.07, Cinco v2.05, Desloc v1.31, Ret v1.07), bloco idêntico, 0 erros/0 avisos, em MQL5\Experts (hash igual). 2026 c/ custo, soma dos 5 = +9.547 contra +9.587 da Z7 (diferença −40 só no Deslocamento, pelo teto de risco do saldo); dias bloqueados 03/03, 08/04, 05/10. Testador WINV26 13/08–30/09: nenhum dia bloqueado (maior gap 0,76 ATR em 08/09) → mesmo esperado de antes (Win 2 ops +10; Win_c1 3 ops +5; Cinco 23 ops +500/+501; Ret 5 ops +221; Desloc 11 ops +55). Para VER o bloqueio: WINV26 01/10–05/10 (05/10: gap +17.775 pts = 5,11 ATR, ATR 3.477,5), sem custo: Win 1 op −676; Win_c1 1 op −209; Cinco 4 ops −174 (sem a regra 5 ops −315); Desloc 1 op −100 (sem: 2 ops −190); Ret 2 ops +115 (sem: 3 ops +77).
Arquivos finais: mt5/{Win,Win_c1,WinCincoMedias,WinDeslocamentoMatinal,WinRetanguloEma34}.mq5/.ex5/_compile.log + .bak; comparativo_win_2026/filtro_gap.py, port_deslocamento_padrao.py (novo), port_win_padrao.py, port_cinco_medias_padrao.py, port_retangulo_ema34_padrao.py; resultados/ (5 CSVs), resultados_pre_gap_historico/; esperado_testador/*_z8_*_WINV26.csv; combinacoes/z8_gap/ (bloco_gap.mqh.txt, aplica_z8_eas.py, baixa_winv26_outubro.py, z8_testador_esperado.py, m1_WINV26_ate_0510.parquet, ticks_WINV26/, logs/)
Ports FEITOS: port_win_padrao.rodar(gap=True), port_cinco_medias_padrao (rodada final), port_retangulo_ema34_padrao.roda(gap=True) tiram as entradas dos dias bloqueados (CSV novo = antigo menos esses dias, conferido; Ret saldo mín 403 > 0 → estado igual); port_deslocamento_padrao.py (NOVO, wrapper: atr_d1=0 nos dias bloqueados, port não editado). CSVs antigos em resultados_pre_gap_historico/; resultados/ regenerado (só os 5). 2026 c/ custo: Win +1.208 (−152, 08/04), Win_c1 +1.325 (−152), Cinco +3.339 (+143, 05/10), Desloc +2.465 (+376; Z7 +416, −40 pelo teto do saldo em 12 stops), Ret +1.210 (+40) → SOMA +9.547 (Z7 +9.587; diferença só no Desloc).
Feito: leitura; comparativo_win_2026/filtro_gap.py (cópia da lógica do z7.py; reproduz os 10 dias da Z7); backups mt5/Win_v2_05, Win_c1_v2_06, WinCincoMedias_v2_04, WinDeslocamentoMatinal_v1_30, WinRetanguloEma34_v1_06 (.mq5.bak). WINV26 13/08–30/09: maior gap 0,76 ATR (08/09) → nenhum dia bloqueado. **5 EAs PRONTOS** (Win v2.06, Win_c1 v2.07, Cinco v2.05, Desloc v1.31, Ret v1.07): bloco idêntico (z8_gap/bloco_gap.mqh.txt, aplicado por z8_gap/aplica_z8_eas.py), input NaoOperarGapATR=1.0 no fim, compilados 0/0, .mq5/.ex5 em MQL5\Experts com hash igual.
Falta: —
Arquivos: ver "Arquivos finais" acima
Último resultado: ver "Resultado final" acima. Obs.: Cinco 13/08–30/09 dá +501 com ticks do WINV26 (z8) contra +500 do arquivo da Z2 (ticks do WIN$N): 5 saídas a ±5 pts, nada a ver com a regra.

### Z9 — Convivência em conta NETTING (dono, 2026-10-06: "crie variações... dispare um subagente para cada teste")
Base comum: z9_netting/base.py (operações isoladas 2022-2026 com regra do gap; `preco(ts)` a mercado; `resumo`). Isolado (5 contas) = 2022 +5.026 · 2023 +4.512 · 2024 +4.720 · 2025 +5.208 · 2026 +14.079. Cada teste é um subagente e edita SÓ a própria linha abaixo (com Edit; sed proibido).
- Z9-T0 bloqueio (o que os EAs fazem hoje; quem entra primeiro fica) — Fase: concluída. c/ custo 2022 +4.740 · 2023 +3.908 · 2024 +5.173 · 2025 +3.123 · 2026 +5.131 (isolado +14.079). z9_netting/t0_bloqueio/
- Z9-T1 preempção total (sinal novo zera a posição a mercado e assume) — Fase: concluída. Líquido c/ custo T1 / T1b / soma isolada: 2022 +4.136 / +5.071 / +5.026; 2023 +1.038 / +1.806 / +4.512; 2024 +979 / +1.961 / +4.720; 2025 +1.297 / +1.982 / +5.208; 2026 +6.548 / +7.073 / +14.079. Sem quebra. Preempção perde ~metade+ da soma isolada em todos os anos; T1b (só transfere gestão no mesmo lado) é melhor que T1 em todos. Caminho: z9_netting/t1_preempcao/ (sim.py, trades_T1.csv, trades_T1b.csv, resultado.md)
- Z9-T2 mesmo lado mantém; lado oposto zera e inverte — Fase: concluída. Líquido c/ custo T2 / T2b / T2c (isolada): 2022 +6.255/+6.204/+4.867 (+5.026); 2023 +3.757/+3.673/+1.873 (+4.512); 2024 +2.860/+2.930/+1.717 (+4.720); 2025 +1.757/+1.836/+2.085 (+5.208); 2026 +8.389/+8.286/+7.229 (+14.079). Sem quebra em nenhum. Inversões T2: 63/45/44/26/32. Caminho: z9_netting/t2_mesmo_lado/ (sim.py, resultado.md, trades_T2*.csv)
- Z9-T3 só opera com concordância (≥2 robôs do mesmo lado, nenhum contra) — Fase: concluída. Melhor 2022-25 (entrada a mercado): T3cd (sai pelo último + conflito zera) +7.026 (2022 +550, 2023 +2.907, 2024 +2.335, 2025 +1.234; 2026 +5.412) vs T3a +5.588 vs soma isolada +19.466 (2026 +14.079); nenhuma variante 2-robôs chega perto da soma isolada; T3e (3 robôs) só ~22 ops/ano, +3.517. Concordância existe em ~75-95 dias/ano (~35-45% dos dias com op). Entrada limite do 2º é pior (T3a 2022 quebra). Ver z9_netting/t3_consenso/resultado.md
- Z9-T4 lado oposto só zera e fica fora (conflito = sem posição) — Fase: concluída. Líquido c/ custo 2022/23/24/25/26: T4 +4.913/+3.936/+3.895/+2.338/+6.526; T4b +6.143/+3.531/+4.577/+2.420/+6.717; T4c(=T0) +4.740/+3.908/+5.173/+3.123/+5.131; isolada +5.026/+4.512/+4.720/+5.208/+14.079; sem quebra. Conflito: 164 em 2022-25, posição aberta perde 57% no natural, zerar não melhora (−508 R$ agregado). Caminho: z9_netting/t4_conflito_fora/resultado.md
- Z9-T5 prioridade fixa por robô (ordem pré-registrada pelo líquido 2022-2025) — Fase: concluída. 2026: P1 líquido +5.167, P2 fator lucro +6.010, P3 acerto +4.802 vs soma isolada +14.079; 2022-25 (in-sample) P1 16.287, P2 11.525, P3 16.836 vs 19.466; ninguém quebra; DD menor. Caminho: z9_netting/t5_prioridade/resultado.md
- Z9-T6 EA maestro: posição líquida = soma dos sinais (netting com vários contratos) — Fase: concluída. T6 líquido 2022-26: +5.028/+4.514/+4.726/+5.212/+14.087 (≈ isolada +2..+8, custo ~R$940 vs R$946 de 2×ops → economia ~0 pois ops iguais; ver resultado.md), máx 4 contratos (margem R$400), saldo mín a mercado 985/989/866/910/700, sem quebra. cap2: 4.903/4.610/4.422/3.541/13.103; cap1: 5.462/3.755/3.270/2.619/6.769. Caminho: z9_netting/t6_maestro/resultado.md
