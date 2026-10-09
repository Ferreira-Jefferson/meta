# Perguntas e regras v4

Código: `v4/regras_v4.py` (regras puras), `v4/decisoes_v4.py` (v3 + regras), `v4/perguntas_v4.py` (perguntas e blocos de estado), `v4/rodar_v4.py`, `v4/analisa_v4.py`. Tudo abaixo foi fixado ANTES de sortear e rodar os 50 dias novos (a origem são os achados dos 30 dias ruins da v3, `analises_r2/`).

## O que muda em relação à v3

| # | mudança | como está implementada | origem |
|---|---|---|---|
| 1 | Gestão = "a tese foi invalidada?" | `v4_g_acao` (manter / stop_pivo / zerar) sem cláusula de eficiência. Bloco de estado TESE DA POSIÇÃO com o último swing contra a posição (fractal de 2 velas, só de hoje). **Guarda determinística**: `zerar` e `stop_pivo` só valem se algum fechamento M15 passou além do swing que valia na entrada ou além do swing de agora; senão vira `manter`. Registra também `v4_motivo_de_sair` (sem_fato_novo / tese_invalidada / fim_do_pregao), só para análise | r2g3_04, r2_estrutura_quebrada, r2_g_perda_sem_invalidacao, R2G5-03 |
| 2 | Portão de direção comprovada | **Trava oficial determinística**: sem posição, só entra se a eficiência direcional do dia na vela de decisão (`|fech-abertura| / soma das amplitudes M15`, igual ao DERIVADOS) for **>= 0,20** e a entrada for a favor do lado do dia (`fech - abertura`). O Jev também responde `v4_direcao_comprovada` (noul) na etapa 2; as duas são registradas, a trava determinística é a que vale. Limiar fixado em 0,20 antes de rodar; 0,15 e 0,25 só como sensibilidade descritiva | R2G5-01 |
| 3 | Risco vs caixa | Bloco de estado com a perda do stop (R$ e % do caixa) de cada opção de stop, por lado. Regra determinística: perda (distância do stop x R$0,20 x contratos, sem somar o custo de 10 pts) > 6% do caixa => 1 contrato; com 1 contrato ainda > 6% => não entra. Caixa = R$ 2.000 no início do dia + resultado do dia (os dias sorteados são esparsos, o caixa não atravessa dias) | r2g1_risco_stop, R2G5-04 |
| 4 | Reentrada | Bloco de estado com nº de operações do dia, saldo, velas desde a última saída e o motivo dela. Regra: máximo 3 operações por dia; se a última operação perdeu, só reentra com >= 2 velas M15 desde a saída (e o portão do item 2 vale para toda entrada) | R2G5-05, r2g3_05 |
| 5 | O resto igual à v3 | 8 perguntas de mercado + `acao/stop/alvo/mao` (textos idênticos), duas etapas, limiar 0,3, `typesafe/jev-1.13-20260917`, estado de 16 velas M15, entrada limitada (3 velas), alvo limitado, stop a mercado, `zerar` **limitado** (variante L da v3: 2 velas no último fechamento) | v3 |

Etapa 1 (8 perguntas de mercado): reusada dos logs da v3 nos mesmos dias (o estado de entrada é idêntico, então a chamada é a mesma; 0 chamadas ao vivo foram necessárias). Etapa 2 (acao/stop/alvo/mao + `v4_direcao_comprovada`) e gestão são chamadas novas, sequenciais, porque o pacote agora depende do estado da simulação.

## O que ficou FORA (decisão registrada)

| id | motivo |
|---|---|
| `r2_lado_da_abertura` | efeito misto nos 20 dias bons da r2_g2 (+R$0 no total, muda 11 dos 20 dias em sentidos mistos); o portão do item 2 já inclui "a favor do lado do dia" (fech - abertura) |
| `r2_reconquista_abertura` | hipótese desenhada em 2 dias em V (n=7 eventos em 26 dias); não é regra |
| R2G5-02 `gap_anomalo` | verificação de dado, não de estratégia; feita à mão (ver RODADAS.md) |
| R2G5-06 `perna_ja_andou` | redundante com `v2_perna_esgotada` (já na v3) |
| P2 `extrema_devolvida`, P5, P6, r2g3_01/02/03 | específicas ou não medidas nos dias bons; fora do escopo pré-registrado da v4 |

## Ressalvas de desenho (declaradas antes de rodar)

- O portão é literal: sem número mínimo de velas (R2G5-01 original pedia >= 6). Na 1ª vela do dia a eficiência é alta por construção.
- Dar ao Jev o bloco com as regras muda o que ele propõe (ele pode obedecer à regra por conta própria). Por isso a ablação offline também usa as respostas de entrada da v3 (sem bloco), ver RODADAS.md.
