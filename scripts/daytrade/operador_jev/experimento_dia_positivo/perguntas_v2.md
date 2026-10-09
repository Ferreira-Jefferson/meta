# Perguntas v2 - experimento "perguntas para o dia positivo"

Consolidação das propostas dos 4 agentes (`analises/grupo_a..d.md`, 20 dias de TREINO). Fundidas as redundantes; descartadas as 'específicas' de 1-2 dias (reconquista da abertura, fundo/topo defendido, volatilidade contraindo, stop além do pivô, profundidade do recuo).

**Aviso sobre os limiares:** todos os números (0,25 ATRd; 60% da amplitude; eficiência 0,15/0,30; volume 1,5x e 1,2x; 50% de devolução; 12 e 8 velas) foram escolhidos pelos agentes olhando os dias de treino. Foram mantidos como estão (ajustar agora seria olhar a validação) e são hipóteses, não parâmetros calibrados. Duas adaptações: P6 `perna_esgotada` usa a perna 'abertura até o extremo do dia' (o pivô de 8 velas não está no pacote) e P8 `seguimento` olha rompimentos das últimas 5 velas (sem contar a última) para haver velas seguintes.

As perguntas leem as linhas **DERIVADOS** do pacote (`montar_estado(derivados=True)`).

## Perguntas de mercado (17, independem da posição)

| id | tipo | categorias / níveis | resposta-alvo -> decisão | origem | geral/específica |
|---|---|---|---|---|---|
| `v2_dia_tipo` | choice | `alta_dirigida`; `baixa_dirigida`; `rotacao`; `indefinido` | alta_dirigida -> só comprar ou ficar fora; baixa_dirigida -> só vender ou fora; rotacao -> sem sinal a favor, não perseguir; indefinido -> fora | gb_01 + gc1 + P02 + P04 (4 grupos; 5/5 dias no grupo_b) | geral (falha no dia de faixa 06-25: 2 falsos positivos) |
| `v2_eficiencia` | score | 0 = abaixo de 0,15 (anda e devolve); 1 = de 0,15 a 0,30; 2 = acima de 0,30 (anda numa direção e não devolve) | 2 -> só a favor, sem alvo fixo, nunca fade; 0 -> rotação: ficar fora ou alvo curto; 1 -> seguir as demais | gc1 (grupo_c; 5/5 dias) | geral (separa o dia direcional; falha no início do dia em V) |
| `v2_preco_vs_ref` | choice | `acima_de_ambos`; `entre`; `abaixo_de_ambos` | acima_de_ambos -> só comprar; abaixo_de_ambos -> só vender; entre -> exige confirmação das outras perguntas | P02 (grupo_d; 5/5) + P3/P5 do grupo_a | geral |
| `v2_rompe_ontem` | choice | `acima_com_volume`; `abaixo_com_volume`; `sem_volume`; `voltou_para_dentro`; `nenhum` | acima_com_volume -> lado comprador; abaixo_com_volume -> lado vendedor; voltou_para_dentro -> fora; demais -> sem sinal | P1 (grupo_a; 4/5) + P03 (grupo_d; 3/5) | geral |
| `v2_rompe_dia` | choice | `rompeu_alta_com_volume`; `rompeu_baixa_com_volume`; `rompeu_sem_volume`; `nenhum` | rompeu_*_com_volume -> não operar contra o rompimento (não vender nova máxima, não comprar nova mínima); nenhum -> sem informação | gb_02 + gc3 + P06 (3 grupos) | geral (tira também alguns acertos de contra-tendência) |
| `v2_seguimento` | choice | `seguiu`; `falhou`; `sem_rompimento` | seguiu -> a favor do rompimento; falhou -> contra o rompimento falho (ou fora); sem_rompimento -> sem sinal | P8 (grupo_a; 5/5) + P09 (grupo_d; 3/5) | geral |
| `v2_faixa_rompida` | noul | P(sim) | sim -> o movimento começou, o lado é o do fechamento; entrar a favor sem perseguir | P2 (grupo_a; 3/5) | geral |
| `v2_lateral_morta` | noul | P(sim) | sim -> ficar fora / não abrir; sair se estiver posicionado; não -> sem efeito | P7 (grupo_a; 5/5) + P07 (grupo_d; 4/5) | geral |
| `v2_estrutura` | choice | `alta`; `baixa`; `lateral`; `indefinido` | alta -> comprar/segurar compra, não vender; baixa -> vender/segurar venda, não comprar; lateral -> fora | P01 (grupo_d; 5/5) | geral (correlacionada com v2_dia_tipo) |
| `v2_swing_rompido` | choice | `acima_do_topo`; `abaixo_do_fundo`; `nenhum` | acima_do_topo -> permite comprar com stop abaixo do último fundo; abaixo_do_fundo -> permite vender; nenhum -> fora | gc5 (grupo_c; 4/5) | geral (hipótese; depende da definição de swing) |
| `v2_h1` | choice | `alta`; `baixa`; `misto` | alta/baixa -> operar só na direção do H1; misto -> sem sinal | P5 (grupo_a; 4/5) | geral |
| `v2_pullback` | choice | `retomada_alta`; `retomada_baixa`; `nenhuma` | retomada_alta -> entrar comprando (limite no fechamento, stop no pivô, sem alvo); retomada_baixa -> entrar vendendo; nenhuma -> esperar | gb_03 + gc6 (2 grupos; ~3/5) | geral (é a entrada da escada v4.1 em forma de pergunta) |
| `v2_gap` | choice | `sem_gap`; `ampliando`; `preenchendo`; `preenchido` | ampliando -> continuação, não buscar reversão (só no sentido do gap); preenchendo -> na direção do preenchimento; preenchido -> não entrar mais nessa direção | P05 (grupo_d; 3/5) + gb_05 (grupo_b; 3/5) | geral (evidência fraca para 'preenchido') |
| `v2_extremo_novo` | choice | `renovou_maxima`; `renovou_minima`; `nenhum` | renovou -> tendência ativa, seguir a favor (veto a operar contra); nenhum -> sinal tardio, ficar fora de entrada nova a favor | P13 (grupo_d; 3/5) + gc8 (grupo_c; 5/5) | geral só em dia direcional |
| `v2_devolveu_50` | noul | P(sim) | sim -> sair ou apertar o stop de posição na direção da manhã; não abrir novas posições nessa direção; não -> manter | gb_04 (grupo_b) | geral (inerte nos dias que seguem; decisiva nos que viram) |
| `v2_perna_esgotada` | noul | P(sim) | sim -> perna parou depois de longa extensão: sair da posição a favor / apertar o stop; não abrir nova entrada na mesma direção | P6 (grupo_a; 3/5) [adaptada: perna = abertura até o extremo do dia, em vez do último pivô de 8 velas] | geral |
| `v2_tendencia_limpa` | noul | P(sim) | sim -> segurar a favor sem alvo fixo, só com stop de trailing; não -> sem efeito | P9 (grupo_a; 2/5 sim, 'não' nos demais) | geral (resposta 'não' nos dias sem tendência) |

### Instructions completos

**`v2_dia_tipo`** (choice): Classifique o dia até agora. 'alta_dirigida': o deslocamento desde a abertura é de pelo menos +0,25 ATR diário E o valor absoluto do deslocamento é pelo menos 60% da amplitude do dia (máxima menos mínima desde a abertura). 'baixa_dirigida': o mesmo para baixo (deslocamento de pelo menos -0,25 ATR diário e pelo menos 60% da amplitude). 'rotacao': o dia já tem 8 ou mais velas M15 e não cumpre nenhuma das duas condições (o preço anda nos dois sentidos e devolve). 'indefinido': menos de 8 velas M15 fechadas hoje.
  - `alta_dirigida`: deslocamento para cima nas duas condições; `baixa_dirigida`: deslocamento para baixo nas duas condições; `rotacao`: 8+ velas e nenhuma das duas condições (anda e devolve); `indefinido`: menos de 8 velas hoje

**`v2_eficiencia`** (score): Qual a eficiência direcional do dia? Use a linha 'Eficiência direcional' dos DERIVADOS: valor absoluto de (último fechamento menos abertura) dividido pela soma das amplitudes (máxima menos mínima) de todas as velas M15 de hoje. Com menos de 8 velas hoje, responda nível 0. Nível 0 = abaixo de 0,15 (o preço anda e devolve); nível 1 = de 0,15 a 0,30; nível 2 = acima de 0,30 (anda numa direção e não devolve).
  - níveis: 0 = abaixo de 0,15 (anda e devolve); 1 = de 0,15 a 0,30; 2 = acima de 0,30 (anda numa direção e não devolve)

**`v2_preco_vs_ref`** (choice): Compare o último fechamento M15 com a abertura de hoje e com o fechamento de ontem (linha 'Gap' / 'Abertura do dia'). Onde está o preço?
  - `acima_de_ambos`: acima da abertura de hoje E acima do fechamento de ontem; `entre`: entre os dois (um acima e outro abaixo); `abaixo_de_ambos`: abaixo da abertura de hoje E abaixo do fechamento de ontem

**`v2_rompe_ontem`** (choice): A última vela M15 fechada fechou além da máxima ou da mínima de ontem (linha 'Ontem' dos DERIVADOS)? Se sim, o volume dela é pelo menos 1,5 vez a média das 20 velas anteriores (linha de volume dos DERIVADOS)? 'voltou_para_dentro': hoje o preço já passou a máxima ou a mínima de ontem, mas o último fechamento está de volta dentro da faixa de ontem. 'Nenhum rompimento' é uma resposta válida e comum.
  - `acima_com_volume`: fechou acima da máxima de ontem com volume >= 1,5x a média das 20 anteriores; `abaixo_com_volume`: fechou abaixo da mínima de ontem com volume >= 1,5x a média; `sem_volume`: fechou fora da faixa de ontem, mas com volume abaixo de 1,5x; `voltou_para_dentro`: passou a máxima/mínima de ontem hoje, mas fechou de volta dentro; `nenhum`: dentro da faixa de ontem e sem ter passado dela hoje

**`v2_rompe_dia`** (choice): A última vela M15 fechada fechou além da máxima (ou da mínima) de todas as velas de hoje até a vela anterior (linha 'ultima vela fechou alem da max/min do dia' dos DERIVADOS)? Se sim, o volume dela é pelo menos 1,2 vez a média das 10 velas anteriores?
  - `rompeu_alta_com_volume`: fechou acima da máxima do dia até a vela anterior, volume >= 1,2x a média das 10 anteriores; `rompeu_baixa_com_volume`: fechou abaixo da mínima do dia até a vela anterior, volume >= 1,2x a média das 10 anteriores; `rompeu_sem_volume`: rompeu a máxima ou a mínima do dia, mas com volume abaixo de 1,2x; `nenhum`: fechou dentro da faixa do dia

**`v2_seguimento`** (choice): Nas últimas 5 velas M15 fechadas (sem contar a última), alguma vela fechou além da máxima/mínima de ontem, da máxima/mínima do dia até então ou da faixa das 12 velas anteriores? Se sim, o fechamento da última vela ficou ALÉM do fechamento da vela do rompimento (seguiu) ou voltou para dentro/atrás dele (falhou)? Se não houve rompimento recente, 'sem_rompimento'.
  - `seguiu`: rompimento recente e o fechamento atual segue além dele; `falhou`: rompimento recente e o preço voltou para dentro/atrás dele; `sem_rompimento`: nenhum rompimento nas últimas 5 velas

**`v2_faixa_rompida`** (noul): Hoje há pelo menos 13 velas M15 fechadas? Se sim: a faixa das 12 velas anteriores à última (linha 'Faixa das 12 velas' dos DERIVADOS) é menor que 1 ATR diário, a última vela fechou fora dessa faixa e a amplitude dela é pelo menos 1,5 vez o ATR M15? Se faltarem velas ou a vela não saiu da faixa, responda não.

**`v2_lateral_morta`** (noul): Nas últimas 8 velas M15 fechadas, a faixa total (linha 'Últimas 8 velas' dos DERIVADOS) é menor que 0,5 ATR diário E o volume médio dessas 8 velas é menor que 70% do volume médio das velas de hoje? Se sim, o mercado está parado. Se não, responda não.

**`v2_estrutura`** (choice): Compare os dois últimos fundos e os dois últimos topos relevantes de hoje (pontos de virada com pelo menos 2 velas de cada lado; as linhas de swing dos DERIVADOS ajudam). Use pelo menos as 8 últimas velas fechadas. Qual é a estrutura de preço de hoje?
  - `alta`: topos E fundos mais altos que os anteriores; `baixa`: topos E fundos mais baixos que os anteriores; `lateral`: sem sequência clara ou preço preso numa faixa; `indefinido`: poucas velas para decidir

**`v2_swing_rompido`** (choice): Compare o último fechamento com o último topo de swing e o último fundo de swing de hoje (linha dos DERIVADOS). Ele fechou acima do último topo, abaixo do último fundo, ou nenhum dos dois?
  - `acima_do_topo`: último fechamento acima do último topo de swing de hoje; `abaixo_do_fundo`: último fechamento abaixo do último fundo de swing de hoje; `nenhum`: dentro da faixa entre o último fundo e o último topo (ou sem swing formado)

**`v2_h1`** (choice): Olhe os H1 completos de hoje (últimas 3 horas fechadas): os fechamentos H1 vêm subindo, descendo ou sem direção? E a última vela M15 fechou do mesmo lado do fechamento H1 de 3 horas atrás? Só diga 'alta' ou 'baixa' se os dois concordam.
  - `alta`: H1 subindo e M15 acima do fechamento H1 de 3 h atrás; `baixa`: H1 descendo e M15 abaixo do fechamento H1 de 3 h atrás; `misto`: não concordam, ou menos de 3 H1 completos hoje

**`v2_pullback`** (choice): Em dia com direção (deslocamento desde a abertura de pelo menos 0,25 ATR diário em módulo e eficiência direcional de pelo menos 0,15), o preço recuou contra o dia por 1 a 3 velas M15 (entre 30% e 60% da última perna a favor), a última vela fechou de volta no sentido do dia (fechamento acima da própria abertura numa alta; abaixo numa baixa) e o preço não perdeu o último fundo (alta) ou topo (baixa) de swing de hoje nem a abertura do dia?
  - `retomada_alta`: dia de alta, recuo de 1-3 velas e a última vela retomou para cima sem perder o último fundo nem a abertura; `retomada_baixa`: dia de baixa, recuo de 1-3 velas e a última vela retomou para baixo sem perder o último topo nem a abertura; `nenhuma`: não há pullback retomado (ou o dia não tem direção)

**`v2_gap`** (choice): Se hoje houve gap relevante (abertura diferente do fechamento de ontem em pelo menos 0,15 ATR diário), qual a situação dele agora (linha 'Gap' dos DERIVADOS)? Fração preenchida: 0% = preço na abertura, 100% = voltou ao fechamento de ontem, negativa = o preço se afastou do fechamento de ontem.
  - `sem_gap`: gap menor que 0,15 ATR diário (ou inexistente); `ampliando`: preço se afastou do fechamento de ontem (fração negativa); `preenchendo`: preenchido entre 0% e 75%; `preenchido`: preenchido em 75% ou mais

**`v2_extremo_novo`** (choice): O extremo do dia (máxima ou mínima) foi renovado nas últimas 6 velas M15 fechadas (linhas 'Máxima do dia ... há N velas' dos DERIVADOS: N menor que 6 = renovou)?
  - `renovou_maxima`: máxima do dia renovada nas últimas 6 velas; `renovou_minima`: mínima do dia renovada nas últimas 6 velas; `nenhum`: nenhum extremo novo nas últimas 6 velas

**`v2_devolveu_50`** (noul): O preço devolveu mais de 50% do deslocamento máximo que o dia fez a partir da abertura (linha 'Deslocamento máximo do dia' dos DERIVADOS)?

**`v2_perna_esgotada`** (noul): A perna do dia (deslocamento da abertura até o extremo do dia no sentido do deslocamento máximo) andou mais de 1 ATR diário (amplitude do dia nos DERIVADOS) E nas últimas 3 velas fechadas o extremo não foi renovado (velas desde o extremo >= 3)? Se uma das duas coisas não é verdade, responda não.

**`v2_tendencia_limpa`** (noul): O fechamento está a mais de 1 ATR diário da abertura, o H1 está na mesma direção e nenhuma das últimas 6 velas M15 fechou contra essa direção por mais de 0,5 ATR M15 (diferença entre abertura e fechamento da vela)? Se sim, o dia é de tendência limpa.

**`v2_estrutura_preservada`** (noul): Para a posição aberta (linha POSICAO), desde a entrada: o último fundo M15 (compra) ou topo M15 (venda) formado depois da entrada continua sem ser perdido por nenhum fechamento E o preço fez novo extremo a favor nas últimas 8 velas M15 ou está a menos de 1 ATR M15 dele?

**`v2_g_acao`** (choice): O que fazer com a posição aberta agora? 'manter': o preço está do lado certo da abertura do dia, o último fundo (compra) ou topo (venda) de swing formado depois da entrada não foi perdido por nenhum fechamento e a eficiência direcional do dia é de pelo menos 0,15. 'stop_pivo': perdeu UMA dessas três coisas (ou devolveu mais de 50% do deslocamento máximo do dia), mas a posição ainda tem lucro aberto: mover o stop para o último pivô a favor. 'zerar': perdeu DUAS ou mais, ou a eficiência do dia caiu abaixo de 0,15.
  - `manter`: manter posição e stop como estão; `stop_pivo`: mover o stop para o último pivô a favor (compra: sobe; venda: desce); `zerar`: zerar a posição

## Gestão (só com posição)

| id | tipo | resposta-alvo -> decisão | origem |
|---|---|---|---|
| `v2_estrutura_preservada` | noul | sim -> manter (sem alvo, deixar correr); não -> apertar o stop ao pivô ou zerar | gb_06 + P11 + gc7 (3 grupos) |
| `v2_g_acao` | choice | manter / apertar stop (stop_pivo) / zerar conforme os três critérios | gc7 (grupo_c; 4/5) + gb_04 |

## Perguntas finais (iguais às do v1)

`acao` {comprar, vender, fora}, `stop` {0.5atr, 1atr, 1.5atr, pivo}, `alvo` {sem_alvo, 1atr, 2atr, 3atr}, `mao` {1, 2}. Limiar 0,3 (P da escolha), versão `jev-1.13-20260917`. Na versão A a pergunta `acao` acrescenta: "O estado traz, depois do mercado, as RESPOSTAS DA ETAPA 1: probabilidades do Jev para perguntas sobre este mesmo estado (tipo de dia, estrutura, rompimentos, H1...). Leve essas respostas em conta."

## Regra do veto (versão B), derivada das respostas-alvo

A ação do Jev (comprar/vender, com P >= limiar 0,3, como no v1) só é aceita se nenhuma pergunta de DIREÇÃO votar contra ela. Voto = categoria com P >= 0.5:

| pergunta | vota COMPRA (+1) | vota VENDA (-1) |
|---|---|---|
| `v2_dia_tipo` | `alta_dirigida` | `baixa_dirigida` |
| `v2_estrutura` | `alta` | `baixa` |
| `v2_h1` | `alta` | `baixa` |
| `v2_preco_vs_ref` | `acima_de_ambos` | `abaixo_de_ambos` |
| `v2_rompe_ontem` | `acima_com_volume` | `abaixo_com_volume` |
| `v2_rompe_dia` | `rompeu_alta_com_volume` | `rompeu_baixa_com_volume` |
| `v2_swing_rompido` | `acima_do_topo` | `abaixo_do_fundo` |

- comprar é vetado se QUALQUER pergunta acima votar venda; vender é vetado se qualquer votar compra (sinais mistos -> os dois vetados -> fica de fora).
- `v2_lateral_morta` com P(sim) >= 0.5 veta as duas ações (mercado parado: ficar fora).
- `v2_dia_tipo = rotacao` NÃO veta: os agentes divergem (grupo_b: sem direção -> fora; grupo_c: em rotação o fade é permitido).
- Gestão: se P(`v2_estrutura_preservada`) < 0.5, o motor aperta o stop ao último pivô a favor (só a favor); senão mantém. O stop móvel de 'deixar correr' (posição sem alvo) segue rodando como no v1. A chamada de gestão do B traz só essa pergunta; o `g_acao` não é usado.
