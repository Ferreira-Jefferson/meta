# Pré-registro do ciclo 3 (escrito ANTES de rodar qualquer dia novo)

Data: 2026-10-09. Base: `robo_v2.py` (v2 = +R$4.678,77 nos 50 dias de `dias_usados.json`). Nada em `ciclo3/` altera arquivo existente.

## Objetivo
Aumentar o ganho de forma que se replique na operação real. Toda seleção usa o R$/dia REPONDERADO ao calendário real, não a soma dos 50 dias (que é estratificada: 20 bons, 20 ruins, 10 sorteados).

## 1. Estratos e frações reais
- Eficiência do dia inteiro = |fecho − abertura| / soma das faixas M15 (`robo.eficiencia`).
- Estratos: **bom** ef ≥ 0,25; **intermediário** 0,15 ≤ ef < 0,25; **ruim** ef < 0,15. (Limiar 0,25 = o do ciclo 2; frações com 0,30 reportadas à parte.)
- Fração real de cada estrato = proporção dos pregões do IS (2022-01-01 a 2025-09-30, ≥ 300 barras M1) em cada faixa.
- R$/dia reponderado = Σ_estrato fração × média de R$/dia do estrato nos 50 dias. Reportar sempre também por estrato.

## 2. Candidatas (cada uma isolada sobre o v2, depois combinadas)
C1 alvo ×1,5 se deslocamento a favor ≥ 1 ATR15 (oportunidades_perdidas) · C2 sem alvo, stop 1,5 ATR15 (≤600 pts) global; C2b2 idem com stop 2; C2c só em continuação; C2d continuação+rompimento (natureza pela função de gestao_adaptativa/coleta.py) ·
C3 stop por vol4 (≥1,0 → 2 ATR; <1,0 → 1 ATR; sem alvo) · C4 c2_2023_09_04 P2 · C5 c2_2024_11_04 P1 (vetos de compra) e C5m espelho para venda (os 3 vetos de venda de rompimento/mínima nova da manhã deixam de valer em dia direcional de baixa, mesma função `_desloc`, definido sem olhar resultado) ·
C6 c2_2025_04_07 N4+N1+F1 · C7 c2_2024_04_22 N5 · C8 c2_2022_05_24 A1+A2+F2 · C9 c2_2025_06_06 N5+N4+P5 · C10a veto original da v1 no lugar do A2; C10b A2v (raso E sem volume) ·
Extras marcados como "entra" nos relatórios: C11 c2_2023_10_17 N1; C12 c2_2023_10_17 F2; C13 c2_2024_11_04 P2; C14 c2_2024_11_04 V1; C15 c2_2025_04_07 F2A (prioritária, chandelier).
Grupos exclusivos (a mesma peça é trocada): {C2, C2b2, C2c, C2d, C3}; {C4, C5}; {C10a, C10b}.
Ordem de aplicação fixa (pelo número); a gestão (C2/C3) vale antes de C1.

## 3. Medição nos 50 dias (por candidata isolada sobre o v2)
R$/dia reponderado; média por estrato; Δ vs v2 em c0+1 (30 dias) e em c2 (20 dias); dias piores/melhores; pior dia; leave-one-day-out (Δ reponderado sem cada dia; mínimo reportado).

## 4. Seleção para frente (forward selection) a partir do v2
A cada passo, sobre a base atual, cada candidata restante é testada. Passa se TODAS:
(a) Δ reponderado > 0; (b) Δ R$/dia do estrato ruim ≥ 0; (c) Δ R$ > 0 em c0+1 E Δ R$ > 0 em c2; (d) pior dia da configuração ≥ pior dia da base − R$50.
Entra a que passa com maior Δ reponderado. Para quando nenhuma passa. Resultado = `robo_v3.py` (congelado, com sha256 registrado abaixo antes do sorteio).
Também medir o v3 com o caixa real: R$2.000, R$1.000 por contrato, contratos = min(2, ⌊caixa/1000⌋) fixados no início do dia, pregões em ordem cronológica, pára se caixa < R$1.000; P&L do dia escala linear com contratos (mesmas ordens); registrar o risco máximo do dia como % do caixa (stop de 600 pts × 2 contratos = 12% do caixa: limite da regra).

## 5. Validação (dados novos, sem nenhum ajuste depois)
Sorteio ALEATÓRIO SIMPLES de 20 dias do IS (2022-01-01 a 2025-09-30, ≥300 barras, fora dos 50 de `dias_usados.json`, nunca abr–out/2026), `numpy.random.default_rng(20261016).choice(candidatos_ordenados, 20, replace=False)`. Registrar em `dias_usados.json` como ciclo3 (feito pelo script de validação, que só acrescenta a chave).
Rodar v1, v2, v3 nesses 20: total, R$/dia, acerto, fator de lucro, pior dia, dias +/−. Pareado v3−v2 e v3−v1: bootstrap por dia (10.000, IC 95%) e teste de sign-flip por dia (10.000). Nulo: 200 réplicas com entradas sorteadas (mesmos dias, mesma contagem de entradas e mesma geometria de stop/alvo/gestão do v3 por trade, horário e lado aleatórios, mesmo motor de execução).
Dias negativos do v3 nos 20 → `ciclo3_negativos.json` (diagnóstico de 1 linha + maior movimento do dia não capturado e por quê).
Nenhuma regra do v3 pode ser mudada depois de ver os 20 dias: o resultado é reportado como saiu.

## Emenda 1 (antes de avaliar qualquer candidata; depois de contar os estratos)
Frações reais medidas (937 pregões IS): bom (ef ≥ 0,25) 3,8% · intermediário 16,8% · ruim 79,4% (com limiar 0,30 o bom é 1,3%). Dos 50 dias usados só **3** são intermediários (c0), então um peso de 16,8% sobre a média de n=3 seria ruído. Decisão: a **métrica primária de seleção** passa a ter 2 estratos: **direcional** (ef ≥ 0,25; 3,8%; n=20) e **não-direcional** (ef < 0,25; 96,2%; n=30, intermediários + ruins juntos). Os 3 estratos continuam reportados como informação. O critério (b) "estrato ruim" é aplicado ao estrato não-direcional (n=30), e reportado também para o ruim puro (n=27).

## Congelamento do v3 (antes do sorteio)
Seleção para frente rodada nos 50 dias (`p3_selecao.py`, `p3_selecao.log`): entraram, em ordem, **C8, C7, C6, C4** (C5 perdeu para C4 no mesmo grupo; C1, a gestão sem alvo, C9, C10, C11–C15 não passaram nos critérios). `robo_v3.py` congelado com IDS = [C8, C7, C6, C4]. Nada mais é ajustado depois do sorteio.
