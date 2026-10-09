# Perguntas v3 - versão enxuta da v2

Código: `v3/perguntas_v3.py` (textos idênticos aos da v2; só se cortou). Execução: `v3/rodar_v3.py`. Medições: `v3/ablacao_api_rodada1.log`, `v3/ablacao_api_rodada2.json`, `v3/estado_api.json`.

**Método.** Só dados de TREINO e os logs da v2 (nada da validação nem dos 50 dias da rodada v3 entrou na escolha). A associação das 17 perguntas com o resultado do trade é nula (|rho| <= 0,09 em 180 entradas), então o resultado não serve para ranquear pergunta; o critério é **quanto cada pergunta muda a decisão da etapa 2**. Medido de duas formas: (a) offline, nos 40 dias dos logs da v2-A (1.360 velas; regressão ridge leave-day-out de P(comprar)-P(vender) e de P(fora) sobre as respostas); (b) **real**, chamando a etapa 2 de novo em 340 velas de treino (1 de cada 2 de 20 dias) com um subconjunto das respostas e comparando a classe da decisão (comprar/vender/fora, limiar 0,3) com a decisão logada. Ruído da API: repetir a mesma chamada concorda em 96,5%.

## Perguntas v3 (8 de mercado + 1 de gestão + 4 finais)

| # | id | tipo | por que fica |
|---|---|---|---|
| 1 | `v2_dia_tipo` | choice | a que mais move a decisão: sem ela a concordância cai a 80,6% (e P(lado) erra 0,12) |
| 2 | `v2_lateral_morta` | noul | segunda maior: sem ela 82,6%, e o Jev passa a entrar mais (62,6% das velas contra 50,6%); é o freio de "ficar fora" |
| 3 | `v2_perna_esgotada` | noul | sem ela 88,8%; única cuja correlação com o lado é negativa (-0,24) |
| 4 | `v2_tendencia_limpa` | noul | sem ela 92,4% e entra mais (55,3%); absorve `v2_eficiencia` (corr 0,73) |
| 5 | `v2_preco_vs_ref` | choice | sem ela 91,8%; absorve `v2_rompe_ontem` (corr 0,82), `v2_pullback` e `v2_extremo_novo` |
| 6 | `v2_rompe_dia` | choice | sem ela 91,8% |
| 7 | `v2_swing_rompido` | choice | sem ela 92,6%; absorve `v2_estrutura` e `v2_h1` (corr 0,74 e 0,64) |
| 8 | `v2_seguimento` | choice | sem ela 93,2%; ligada a "ficar fora" (corr -0,62) |
| G | `v2_g_acao` | choice | única de gestão usada (manter / stop_pivo / zerar) |
| F | `acao`, `stop`, `alvo`, `mao` | choice | iguais à v1/v2 (a `acao` manda ler as respostas da etapa 1) |

**Teste do conjunto (real, 340 velas de treino, concordância com a decisão das 17 respostas; ruído 96,5%):**

| conjunto | n | concorda | entra (ref 50,6%) |
|---|---|---|---|
| nenhuma resposta | 0 | 66,8% | 48,5% |
| R6 (1-6 acima) | 6 | 86,8% | 54,1% |
| R7 (sem swing_rompido) | 7 | 89,1% | 50,0% |
| **R8 = v3** | **8** | **91,8%** | **52,1%** |
| R9 (+ faixa_rompida) | 9 | 90,9% | 47,4% |
| R10 (+ estrutura) | 10 | 90,6% | 47,4% |
| S10 (primeiro palpite offline) | 10 | 90,0% | 55,3% |

Régua escrita antes de rodar o R8: menor conjunto com concordância >= 90% e taxa de entrada a menos de 5 pontos da referência. R7 fica fora por 0,9 ponto. Ressalva: R8 foi escolhido nas mesmas 340 velas em que foi medido (é ajuste, não validação; a validação é a rodada de 50 dias novos).

## O que saiu e por quê (9 de mercado + 1 de gestão)

| id | motivo |
|---|---|
| `v2_eficiencia` | redundante com `tendencia_limpa` (0,73) e `devolveu_50` (-0,71); sem ela 93,5% |
| `v2_rompe_ontem` | redundante com `preco_vs_ref` (0,82); sem ela 95,3% (= ruído) |
| `v2_faixa_rompida` | R8 sem ela é igual ou melhor que R9 com ela; ganho offline 0,001 |
| `v2_estrutura` | redundante com `h1` (0,80) e `swing_rompido` (0,74); sem ela 95,3% (= ruído); R10 não melhora |
| `v2_h1` | redundante com `estrutura` (0,80); sem ela 94,1% |
| `v2_pullback` | corr 0,91 com `dia_tipo`; sem ela 94,7% |
| `v2_gap` | sem efeito: 94,4% e ganho offline 0,000 |
| `v2_extremo_novo` | redundante com `pullback` (0,80) e `dia_tipo` (0,75); sem ela 93,8% |
| `v2_devolveu_50` | sem ela 95,0% (= ruído) |
| `v2_estrutura_preservada` (gestão) | o modo A nunca a usou na decisão (só `v2_g_acao`) |

Cortadas em conjunto, as 9 mudam a decisão em 8,2% das velas (91,8% de concordância contra 96,5% do ruído), acima do ruído mas abaixo de qualquer das três maiores sozinha.

## State (pacote de mercado)

Medido em 340 velas de treino; referência = o mesmo pacote completo da v2 chamado de novo (ruído = 95,0% de concordância). As perguntas são as da v3 em todas as linhas.

| estado | tokens/vela (2 chamadas) | US$/vela | concorda | entra (ref 51,2%) |
|---|---|---|---|---|
| completo (40 velas M15, 10 dias de DIARIO, H1 de 3 dias) | 11.146 | 0,00047 | 95,0% (repetição) | 51,5% |
| 16 velas M15 | 9.063 | 0,00038 | 93,2% | 49,7% |
| 12 velas M15 | 8.725 | 0,00037 | 94,7% | 49,1% |
| 16 velas + DIARIO 5 dias + H1 de ontem e hoje | 7.749 | 0,00033 | 93,5% | 49,1% |
| **16 velas, sem DIARIO, H1 só de hoje (v3)** | **6.363** | **0,00027** | **95,3%** | **50,0%** |
| 12 velas, sem DIARIO, H1 só de hoje | 6.025 | 0,00025 | 92,6% | 48,5% |

Escolhido: 16 velas M15, seção DIARIO removida (os DERIVADOS já trazem ATR diário, ontem, gap), H1 só de hoje. Os DERIVADOS não mudam (são calculados do histórico completo).

## Fusão das duas etapas (1 chamada com perguntas + acao/stop/alvo/mao)

Testada em 340 velas de treino: concordância com a decisão de duas etapas **55,6%**, entra em 65,6% das velas (ref 51,2%), P(lado) erra 0,24. Pior que qualquer corte de pergunta. **Duas etapas mantidas**: o Jev precisa ver as respostas.

## Custo por chamada, antes x depois (medido nos logs)

| | v2-A (17 perguntas, estado completo) | v3 | variação |
|---|---|---|---|
| tokens de entrada por vela sem posição (2 chamadas) | 13.357 | 6.353 | -52% |
| US$ por vela sem posição | 0,000561 | 0,000267 | -52% |
| tokens de entrada por vela com posição (3 chamadas) | 19.014 | 9.033 | -52% |
| US$ por vela com posição | 0,000799 | 0,000379 | -53% |
| **US$ por dia** | **0,0229** (A: US$ 0,459 / 20 dias) | **0,0101** (US$ 0,5035 / 50 dias) | **-56%** |
