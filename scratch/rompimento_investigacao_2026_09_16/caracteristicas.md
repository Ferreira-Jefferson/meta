# Características do rompimento e o que predizem — WIN@ M1, IS (129 pregões, 2025-12-01 a 2026-06-12)

Território deste documento: **as CARACTERÍSTICAS do rompimento e o que elas predizem** — não
o fenômeno em si (existe/continua/retesta — isso é `rompimento_retangulo_fenomeno_2026_09_16.py`,
outro agente, cujo `excursao`/`quem_chega_primeiro`/`HORIZONTE` foram IMPORTADOS aqui, não
redefinidos), nem definições (`definicoes.md`) nem executabilidade (`executabilidade.md`).

Script fonte: `scripts/daytrade/rompimento_caracteristicas_2026_09_16.py` (+ `.log`, 417
rompimentos, 129 pregões, todos com ≥400 barras). Retângulo: `detecta_retangulo` de produção
(W=20, tolerância 0,20, largura mínima 328). Rompimento: a regra de morte do robô
(fechamento além da borda + 25% da largura por 3 barras) — a mesma do território do fenômeno.

Rótulo (desfecho, importado): `outcome_continuo = MFE - MAE` a partir do PREÇO DE DETECÇÃO
(nunca da borda — vantagem de largada já documentada e evitada), horizonte 60 barras;
`favor_60` = 1 se +60 pts é tocado antes de -60 (mesma função `quem_chega_primeiro`).

---

## 1. Quantos rompimentos por pregão, características, tamanhos, volumes (pedido literal do dono)

- **417 rompimentos em 129 pregões** — média 3,23/pregão, mediana 3,0, desvio 2,28, min 0, max 11.
- **7 de 129 pregões (5,4%) não tiveram nenhum rompimento.**
- Direção: ALTA 191 (45,8%) / BAIXA 226 (54,2%) — bate com o território do fenômeno (417/191/226).
- Largura do retângulo rompido: média 472,1 pts, **mediana 435,1**, desvio 135,7 pts (n=417).
- Vida do retângulo até romper: média 28,8, **mediana 18** barras, desvio 34,2 (cauda longa).
- Já andou da borda até a detecção: média 291,1, **mediana 262,9** pts, desvio 161,3.
- Amplitude das 3 barras do rompimento: média 370,6, **mediana 319,0** pts, desvio 200,7.
- Toques totais (topo+piso): média/mediana 14,0, desvio 2,2.
- Cruzamentos do meio: média 5,4, mediana 5,0, desvio 1,7.
- Volume do rompimento / volume médio do retângulo: média 1,274, **mediana 1,198**, desvio 0,447.
- Volume acumulado do dia / típico no mesmo instante: média/mediana ~1,047, desvio 0,128 —
  ou seja, no INSTANTE do rompimento o dia não está com volume anormal (dispersão pequena).
- Hora do rompimento (BRT): média 13,0h, mediana 12,3h, desvio 2,2h.

**Conjectura 1.1.** O rompimento típico não é um evento "raro e dramático": acontece ~3x por
pregão, no meio do dia (mediana 12h18 BRT), depois de um retângulo com só 18 barras de vida —
quase metade da largura mínima usada para VALIDAR o retângulo (W=20). Ele é um evento
FREQUENTE e ORDINÁRIO da série, não uma cauda.

**Pergunta aberta 1.1.** Por que a hora do rompimento (mediana 12h18) não coincide com o pico
de FORMAÇÃO do retângulo (10h BRT, medido em `definicoes.md`)? Consistente com vida mediana de
18 barras: um retângulo que nasce por volta de 10h leva ~18-30 min para romper, chegando perto
do meio-dia. Não é contradição, é a mesma cadeia — mas não foi verificado diretamente (exigiria
juntar timestamp de nascimento com o de rompimento por evento, fora do escopo desta rodada).

## 2. Qual característica prediz o desfecho?

**Nenhuma das 25 características testadas isoladamente teve `|rho| acima do limiar
assintótico de 5%`** (limiar ≈0,096 para n=417). O maior `|rho|` observado foi 0,094
(contenção da banda) — abaixo do próprio limiar. Sob H0 pura, esperar-se-iam ~1,2 falsos
positivos entre 25 testes; **obtivemos 0**. Tabela completa (todas as 25, incluindo as que
falharam) está no `.log`, seção (B).

Lista testada: largura (pts e relativa ao dia), duração do retângulo, hora da sessão, toques,
visitas, trocas, cruzamentos, contenção, deriva, contração, afastamento até detecção (pts e
relativo), amplitude das 3 barras do rompimento (pts e relativa), volume do rompimento vs
retângulo, volume acumulado do dia vs típico, distância ao topo/fundo do dia, posição no range
do dia, tendência do pregão, gap de abertura, dia da semana, direção, ordem do rompimento no
pregão.

**Conjectura 2.1 (a mesma taxa-base do `wdo_orb`).** Confirma-se aqui o padrão já registrado em
`wdo_orb_perfil_operacao_sem_preditor_2026_09_14`: **nenhuma característica observável NO
INSTANTE do sinal prediz o desfecho**, e a taxa-base deste tipo de investigação no projeto
continua próxima de zero — agora em duas famílias independentes (rompimento ORB e rompimento de
retângulo). Isso é evidência ACUMULADA, não coincidência de uma família só.

**Pergunta aberta 2.1.** Toda tabela por quartil em (B) tem quartis "bagunçados" (não
monotônicos) — nenhuma característica sequer se aproxima de separar por EXTREMO (1º e 4º
quartil na mesma direção, meio no meio). Não há "sinal fraco mas real" escondido em cauda —
o ruído está espalhado por toda a distribuição.

## 3. VOLUME — rodada própria (pedido explícito do dono)

Conjectura clássica testada: **"rompimento com volume CONTINUA, sem volume FALHA."**

| medida | rho | veredito |
|---|---:|---|
| volume do rompimento (3 barras) / volume médio do retângulo | +0,058 | NÃO sobrevive |
| volume acumulado do dia / típico no mesmo instante (calibrado por dia, correção de nível — não é "metade do volume da barra", é o dia inteiro até ali) | -0,010 | NÃO sobrevive |

**Tabela por quartil do volume do rompimento** (a que mais se aproxima da conjectura clássica):
Q1(baixo) outcome médio **-161,5** (n=105) · Q2 **+184,3** (n=104) · Q3 **+58,6** (n=104) ·
Q4(alto) **+42,7** (n=104). Se a conjectura clássica valesse, esperaríamos monotonicidade
crescente Q1→Q4; em vez disso o **pico é no Q2**, não no Q4 — o quartil de volume MAIS ALTO
tem outcome pior que Q2 e Q3. Não é "sinal fraco", é ausência de padrão monotônico.

**Conjectura 3.1 — a clássica está REFUTADA nesta amostra.** Rompimento com volume alto não
continua mais que rompimento com volume moderado; e rompimento com volume baixo (Q1) tem o
PIOR outcome médio, não o melhor caso a favor da hipótese contrária. O volume, medido das duas
formas causais mais óbvias, não separa continuação de falha no instante do rompimento.

**Limitação declarada.** Isso testa APENAS o volume NO INSTANTE do rompimento contra o
desfecho seguinte — não testa (fora do escopo) se volume confirma o RETÂNGULO como válido
antes de romper (`copawin_retangulo_volume_2026_09_15` já tratou dessa pergunta, território
diferente, mesmo veredito de "feature majoritariamente morta").

## 4. Quantos rompimentos por pregão muda o quê? O 1º é diferente do 3º?

| ordem no pregão | n | outcome médio | desvio | favor60% |
|---|---:|---:|---:|---:|
| 1º | 122 | -1,5 | 1.067,8 | 34,4% |
| 2º | 98 | +153,1 | 794,5 | 40,8% |
| 3º ou mais | 197 | -10,5 | 801,9 | 37,6% |

**Conjectura 4.1.** Ao contrário do `copa_win` (onde a 1ª operação do dia é custo estrutural
mensurável), aqui **o 1º rompimento não é visivelmente pior** que o 3º+ (-1,5 vs -10,5, ambos
perto de zero, dispersão enorme dos dois — 1.068 e 802). O 2º parece melhor (+153,1) mas com
n=98 e desvio 794,5 isso é ~1 SE de 80 pts de distância de zero — não é conclusivo, e a
característica `ordem_no_dia` teve `rho=0,013` na tabela geral (item 2), ou seja, tratada como
variável contínua ela não prediz nada. **Não transferir o achado do `copa_win` para este
fenômeno.**

**Pergunta aberta 4.1.** Com n=98 no grupo "2º", uma leitura mais firme exigiria mais pregões
com ≥2 rompimentos (86 dos 129 pregões têm isso, então a amostra já está perto do teto
disponível no IS) — não é "rodar mais", é esperar mais dados reais ou aceitar a incerteza.

## 5. O tamanho importa (como importa no `win_retangulo`)?

No `win_retangulo`, a LARGURA do retângulo prediz retorno/risco na direção POSITIVA
(ρ +0,34 IS / +0,31 OOS) contra o desfecho de uma ESTRATÉGIA (entrada no meio, alvo além da
borda). Aqui, contra o desfecho do ROMPIMENTO (MFE-MAE a partir da detecção), **largura teve
rho = -0,000** — nulo absoluto — e `largura_rel_dia` teve rho = -0,006, igualmente nulo.

**Conjectura 5.1 — o achado de largura NÃO transfere.** A largura prediz a QUALIDADE da
entrada de FADE (operar dentro do retângulo, na direção do centro) mas não prediz a
continuação do ROMPIMENTO (operar fora, na direção da fuga). São mecanismos opostos por
desenho — um retângulo largo dá mais espaço de alvo dentro dele (explica o ρ do fade), mas
isso não fala nada sobre o que acontece depois que o preço já saiu dele. Faz sentido
mecanicamente e não deveria ter sido óbvio antes de medir.

## 6. Combinações (top-5 |rho| isolado, 10 pares declarados)

Top-5 usado: contenção da banda, toques totais, volume rompimento/retângulo, duração do
retângulo, deriva. **10 combinações testadas** (todas em `.log`, seção E) — a alpha=5%,
esperar-se-iam ~0,5 combinação positiva por acaso, somada aos ~1,2 já esperados no teste
isolado (item 2): ~1,7 falsos positivos esperados no total das 35 comparações desta rodada.

**Achado mais notável (não confirmado): contenção ALTA (=1,0) × volume do rompimento ALTO**
→ outcome médio **+212,4** (n=97), contra as outras 3 combinações do mesmo par
(+25,2 / -90,7 / -10,3). É o quadrante mais extremo de toda a seção de combos.

**Por que isto NÃO é declarado achado, e sim pergunta em aberto:** (a) o desvio-padrão do
outcome contínuo é ~900 pts em toda a amostra — para n=97, erro-padrão da média ≈ 91 pts,
então +212 é ~2,3 erros-padrão de zero, dentro do que se espera encontrar ao vasculhar 40
quadrantes (4 por par × 10 pares) escolhendo o mais extremo DEPOIS de ver o resultado — exatamente
o vício que este projeto já registrou ("escolher parâmetro que melhor encaixa no dia que já se
viu não é calibração"); (b) nenhuma das duas variáveis isoladas (contenção rho=0,094,
volume_ratio rho=0,058) passou no teste unitário.

**Pergunta aberta 6.1.** Se esta combinação sobreviver a uma amostra NOVA (mais pregões reais,
nunca esta mesma janela), ela merece revisita. Até lá é hipótese gerada pelos dados, não
achado — não deve entrar em nenhuma tabela de decisão do robô.

---

## Resumo para quem for desenhar a estratégia depois

1. O rompimento é um evento **frequente e ordinário** (~3/pregão), não uma cauda rara.
2. **Nenhuma das 25 características isoladas prediz o desfecho** — mesma taxa-base de
   `wdo_orb_perfil_operacao_sem_preditor_2026_09_14`, agora replicada numa segunda família.
3. **A conjectura clássica de volume está refutada** nas duas formas causais testadas.
4. **A largura NÃO transfere** do achado do `win_retangulo` — mecanismo oposto (fade vs fuga).
5. **Ordem do rompimento no dia não separa** (ao contrário do `copa_win`).
6. Uma combinação (contenção×volume) chamou atenção mas não passa no crivo de múltiplas
   comparações — registrada como pergunta aberta, não como filtro a adotar.
7. **Conclusão de método para quem for desenhar geometria em cima disto:** se nenhuma
   característica separa o rompimento que continua do que falha, qualquer estratégia de
   ROMPIMENTO nesta base terá de se sustentar na ASSIMETRIA alvo/stop e no breakeven —
   não em filtro de entrada. Isso é pergunta para o território de EXECUTABILIDADE/ECONOMIA,
   não deste documento.
