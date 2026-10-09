"""Monta RELATORIO.md a partir de tabelas.md (geradas por p5_relatorio_tabelas.py)."""
from pathlib import Path
ER = Path(__file__).resolve().parent
t = (ER / "tabelas.md").read_text(encoding="cp1252", errors="replace")
parts = t.split("### ")
T1 = parts[1].split("\n", 1)[1]
T2 = parts[2].split("\n", 1)[1]
T3 = parts[3].split("\n", 1)[1]
r = f"""# Estudo da rotação (robo_v4, 90 dias de `dias_usados.json`)

Estratos pela ef do dia inteiro: rotação < 0,15 (55 dias), intermediário 0,15-0,25 (14), direcional >= 0,25 (21). Aleatórios (ciclos 3+4) = 40 dias, dos quais 28 de rotação. Base: `cfg4.monta(robo_v4.IDS)` sem mudança = R$ 9.989,70 total, reponderado R$ 73,11/dia, pior dia -R$ 253,10, 25 dias negativos (24 de rotação, 1 intermediário). Todos os 169 trades do v4 usam 1 contrato.

## Resposta curta

| pergunta | resposta |
|---|---|
| Algum uso do estado causal melhora o v4? | **Não.** Nenhum dos usos com estado causal (E1/E2) tem Δ reponderado > 0: 0 positivos, 3 nulos (b1, d2/E2), o resto negativo (de -0,2 a -32). Só o oráculo (não causal) dá algo positivo: c4/OR +0,09 e d2/OR +1,14. |
| O estado causal é bom? | Fraco até 11h (AUC 0,52-0,72), razoável só a partir das 12h (0,81-0,86 para ef parcial). |
| A rotação perde de fato? | Só nos **aleatórios**: 28 dias de rotação, -R$ 25,6/dia, 17 negativos (-R$ 717). Nos 27 dias de rotação de escolha (c0-c2) o v4 dá **+R$ 69,3/dia**, mas as regras foram desenhadas em cima deles. |
| Teto se soubéssemos a rotação (a3/OR: não operar em rotação) | +R$ 717 nos 40 aleatórios, mas perde os +R$ 1.871 dos dias de rotação de escolha: Δ reponderado **-16,1**. Nem com clarividência vale parar. |

## Tabela 1. Resultado por fonte do trade, v4, 90 dias (ordenada pela perda em rotação)
"fora" = intermediário + direcional.
{T1}
Leitura:
- Perdem em rotação e ganham fora, com n >= 2: **"Recuo à média 8 em tendência de alta"** (6 trades, -R$ 94 em rotação / +R$ 152 fora) e **"F2 vende falha da máxima matinal"** (9 trades, -R$ 36 / +R$ 281). Com n = 1 há outras (F5, F2 gap de baixa, A3), sem valor estatístico.
- Ganham em rotação: **gap_fade_fechamento** (18 trades, +R$ 443, acerto 56%), **P2 rompe faixa 1h com volume** (3, +R$ 239), **venda pullback EMA20** (13, +R$ 95), recuo a favor da tendência (12, +R$ 79), C8 (+R$ 268, n=1).
- Esses ganhos vêm dos dias de escolha. Nos 28 aleatórios de rotação, `venda pullback EMA20 em baixa` faz 8 trades e -R$ 308, e `gap_fade_fechamento` 8 trades e +R$ 27.
- Em rotação, por saída: 33 alvos (+R$ 3.010, média +91), 42 stops (-R$ 3.042, média -72), 22 fim de pregão (+R$ 1.186). Nenhuma fonte passa de n = 18.

## Tabela 2. O estado causal separa o dia que terminará em rotação? (AUC, orientação declarada antes)
Rótulo = ef do dia inteiro < 0,15. IS937 = calendário IS completo (só mercado, sem rodar robô; base de rotação 80%); 90d = amostra estratificada (base 61%). Features só com dados até a hora cheia (M15 fechadas, M1 < t). Orientação: ef parcial, amplitude/ATRd, gap e deslocamento baixos = rotação; cruzamentos de VWAP, sobreposição e proximidade do meio da faixa altos = rotação.
{T2}
Precisão no limiar = mediana do calendário (IS937):

| estado | 10h | 11h | 12h | 13h |
|---|---|---|---|---|
| E1 (ef parcial <= mediana): P(rotação / marcado) | 83% | 89% | 93% | 97% |
| E1: P(rotação / não marcado) | 76% | 70% | 66% | 62% |
| E2 (voto >= 3 de 4): P(rotação / marcado) | 81% | 88% | 92% | 95% |
| E2: P(rotação / não marcado) | 78% | 74% | 72% | 69% |
| base | 80% | 80% | 80% | 80% |

Às 10h o estado praticamente não informa (83% contra 80%). A partir das 12h informa, mas a maior parte das entradas já aconteceu. Gap (AUC 0,52), sobreposição e cruzamentos de VWAP são fracos; ef parcial e deslocamento/ATR15 são as melhores e são quase a mesma coisa. Acerto bruto no limiar mediana (`p2.log`) não é bom indicador porque a base é 80%.

## Tabela 3. Usos medidos sobre o v4, 90 dias
Δ em relação ao v4 sem mudança. E1/E2 = estados causais; OR = oráculo (ef do dia inteiro, não causal, só como teto). "d 40 aleat" = soma do Δ R$ nos 40 dias de ciclos 3+4. LOO mín = menor Δ reponderado tirando cada dia. Usos: a1/a2 = vetar fontes no estado; a3 = vetar toda entrada; b1 = 1 contrato; b2 = alvo x0,5; c1 = parar após 1ª perda; c2 = parar após 2 ops; c3 = parar após 1ª perda sem estado; c4 = parar se P&L do dia <= -R$ 100; d1/d2 = repertório de fade da borda da faixa.
{T3}

Notas:
- **Declarados antes de ver qualquer efeito no robô** (cabeçalho de `p3_usos.py`, escrito antes de rodar): estados E1/E2/OR com limiares = medianas do calendário IS por hora (vêm de `p2_resultado.json`, sem usar resultado do robô); antes das 10h o estado é "não rotação"; usos b, c, d e seus parâmetros (0,85/0,15 da faixa, faixa >= 4 ATR15, stop 0,5 ATR15, alvo no meio da faixa, recompensa >= risco, -R$ 100).
- **NÃO declarados antes: as listas de fontes de a1 e a2** saem da Tabela 1, nos mesmos 90 dias (in-sample). A regra de seleção (n_rot >= 2 e R$rot < 0 e R$fora > 0 para a1; R$rot < 0 e R$fora >= 0 para a2) foi fixada antes de medir o efeito, mas a lista vem dos dados testados. Mesmo assim os Δ são negativos.
- b1 é nulo: o v4 só usa 1 contrato. Redução de mão não é alavanca nesta versão.
- c3 (parar após a 1ª perda, sem estado) piora tudo (Δrep -19,6, 37 dias negativos): o robô depende de reentrar depois de um stop.
- b2 (alvo x0,5) melhora os dias de rotação em E1/E2 (+4,2/+4,5 R$/dia) mas corta os dias bons: Δrep -6,0/-3,4. Confirma o que já se sabia (alvo curto).
- d1/d2 quase não disparam com E2 (0 a 1 trade a mais); com E1 disparam e perdem.

## O que isso diz sobre o problema

1. O prejuízo em rotação não aparece concentrado em uma fonte ou horário. Nos 28 aleatórios de rotação, o v4 perde -R$ 717 espalhado por 20 fontes (maior: pullback EMA20 em baixa, -R$ 308 em 8 trades), e por trade por hora de sinal: 10h -R$ 31, 11h -R$ 30, 12h -R$ 7, 13h -R$ 35 (n pequeno).
2. A diferença entre "rotação ganha" (+69/dia) e "rotação perde" (-26/dia) é viés de seleção: os 50 dias de escolha foram os usados para desenhar as regras. A estimativa honesta de rotação é a dos 28 dias aleatórios, e é ruidosa (17 de 28 negativos, 56 trades).
3. O estado só é legível tarde (12-13h, AUC 0,81-0,86), e mesmo com informação perfeita (oráculo) parar ou reduzir perde no reponderado. Gerir a rotação com um estado do dia no formato "desliga/reduz/para" não funciona neste robô.
4. Em rotação o robô é payoff assimétrico (alvo +91, stop -72, acerto 34% nos alvos). A "queda" na rotação é compatível com variância de acerto, sem efeito de regime mensurável com 28 dias.

## Propostas para o pré-registro do ciclo 5

| # | proposta | status | justificativa |
|---|---|---|---|
| 1 | Não adotar veto/redução/parada baseado em estado causal de rotação. | registrar como refutado | 0 de 31 passam; o oráculo também perde (a3/OR -16,1). |
| 2 | Ampliar a amostra de rotação aleatória antes de qualquer tese de rotação: sorteio de pelo menos 40 dias novos do IS (fora dos 90, nunca abr-out/2026), v4 reportado por estrato. | a pré-registrar | 28 dias de rotação e 17 negativos não dão IC útil; é o que mais falta. |
| 3 | Uma única variante do estado: só depois das 12:00, E1 (ef parcial <= mediana das 12h) + veto das duas fontes da lista a1 ("Recuo à média 8 em tendência de alta", "F2 vende falha da máxima matinal"), testada apenas em dados novos. | hipótese, uma variante | única janela em que o estado separa (AUC 0,81). Lista de 2 fontes com n pequeno: só vale em dado novo. Nesta rodada a1 foi testada desde as 10h e deu -6,9. |
| 4 | Não repetir: parar após 1ª perda (c1/c3), alvo x0,5 em rotação (b2), fade da borda da faixa com estado causal (d1/d2). | registrar como refutado | Δ reponderado de -3 a -20. |
| 5 | Redução de mão só existe se o ciclo 5 abrir 2 contratos por regra (tese separada). | nota | b1 nulo, o v4 só usa 1 contrato. |
| 6 | Antes de buscar causa da rotação: IC do R$/dia de rotação nos aleatórios por bootstrap por dia. | análise | n por fonte <= 18, 28 dias. |

## Arquivos
`common.py` (estimativas causais `feats`, estratos, métricas), `p1_tabela_fontes.py` (+ `p1.log`, `p1_fontes.json`, `v4_90.json`), `p2_auc_regime.py` (+ `p2.log`, `p2_resultado.json`, `p2_feats.json`), `p2b_precisao.py` (`p2b.log`), `p3_usos.py` (+ `p3.log`, `p3_res.json`, `p3_resumo.json`), `p4_extras.py` (`p4.log`), `p5_relatorio_tabelas.py`, `p6_monta_relatorio.py`, `tabelas.md`. Nenhum arquivo existente alterado; mt5/ não tocado; sem commit.
"""
(ER / "RELATORIO.md").write_text(r, encoding="utf-8")
