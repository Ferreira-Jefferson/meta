# Pré-registro do ciclo 4 (escrito ANTES de montar ou selecionar qualquer coisa)

Data: 2026-10-09. Base: `robo_v3.py` (congelado no ciclo 3). Dias de escolha: os **70** de `dias_usados.json` (ciclos 0–3). Nada em `ciclo4/` altera arquivo existente.

## Origem das candidatas
Análises dos 12 dias negativos do v3 (`analises/c3_*.md`, `regras/c3_*.py`, `regras/c3_grupo_*.py`, `ciclo3/c3_av2d*.py`, `ciclo3/ag2_*.py`). Toda candidata foi desenhada olhando os mesmos 70 dias: a seleção abaixo é hipótese, a validação é só a do item 5.

Ficam FORA por decisão prévia (os próprios agentes marcaram como ajustadas ao dia ou reprovadas): qualquer A2 condicional, OPV/OPF (vetos/FAZER após 1ª op), reversão à VWAP (H3/H3b), compra de reversão prioritária (H1–H3 de 08_18), alvo curto/trava em rotação, entrada cedo E1/E1s/G6/B_F1, NG (gap de baixa 07_11), AF1 (09_05), combinações "escolhidas depois de ver".

## Candidatas (cada uma isolada sobre o v3, depois seleção para frente)
| id | o que é | origem | grupo exclusivo |
|---|---|---|---|
| D1 | F1 prioritária: retomada da abertura a favor do gap | c3_2024_04_26 A_F1 prio | — |
| D2 | G4: flip após stop da gap_fade | c3_grupo_2024_04_26 G4 | — |
| D3 | conflito de lados → entra o lado do deslocamento | c3_grupo_2024_04_26 E1 (= CFd de 06_20) | conflito |
| D4 | conflito de lados → só se VWAP e maioria concordam | c3_grupo_2024_09_05 G3d | conflito |
| D5 | H4: A2 não vale com ef<0,12 e faixa 2h ≤ 2 ATR15 | c3_grupo_2022_08_18 H4 | — |
| D6 | B-N5: não vender mínima nova com volume ≥ 2,5× mediana | c3_2022_09_21 N5 | — |
| D7 | S2: não repetir o lado após 2 stops nele | c3_grupo_2022_12_12 S2 | — |
| D8 | N2: não comprar com gap de alta já todo devolvido | c3_2022_12_12 N2 | — |
| D9 | N1: não comprar após 1ª vela de queda forte | c3_2022_12_12 N1 | — |
| D10 | G7a: a favor de vela de expansão, sem alvo, trailing 2 ATR15 após 1 ATR15 a favor | c3_grupo_2022_12_12 G7a | — |
| D11 | BN3: após vitória matinal em dia de rotação não opera mais | c3_grupo_2024_09_05 BN3 | — |
| D12 | AN1: descarta FAZER com alvo < 0,5×stop | c3_2024_09_05 AN1 | — |
| D13 | N1: não vender no terço inferior da faixa em rotação (ef<0,10) | c3_2022_04_13 N1 | — |
| D14 | N1: não comprar recuo em rotação comprimida (ef<0,08, amplitude<0,35 ATRd) | c3_2022_05_17 N1 | — |
| D15 | F1: fade cedo do gap com rejeição (09:45–10:15) | c3_2022_05_17 F1 | — |
| D16 | G1: alvo ×2 se a favor da perna (desloc ≥0,3 ATRd e ef ≥0,3) | c3_grupo_2025_06_20 G1 0,3/0,3/2,0 | — |

Cada candidata é portada para `ciclo4/cfg4.py` reaproveitando a função do agente. **Conferência obrigatória:** isolada sobre o v3, ela tem de reproduzir o Δ reponderado relatado pelo agente (tolerância ±0,10 R$/dia). Se não reproduzir, registrar a divergência e usar o número do port.

## Métrica e estratos (iguais ao ciclo 3, Emenda 1)
Reponderado = 3,8% × média direcional (ef ≥ 0,25) + 96,2% × média não-direcional, nos 70 dias.

## Seleção para frente a partir do v3
A cada passo, cada candidata restante (respeitando grupos exclusivos) é testada sobre a base atual. Passa se TODAS:
- (a) Δ reponderado > 0;
- (b) Δ R$/dia do estrato não-direcional ≥ 0;
- (c) Δ R$ > 0 nos 50 dias c0–c2 **e** Δ R$ ≥ 0 nos 20 dias c3;
- (d) pior dia da configuração ≥ pior dia da base − R$50;
- (e) **novo:** leave-one-day-out — o mínimo do Δ reponderado tirando cada um dos 70 dias é > 0 (o ganho não pode depender de um dia só).

Entra a que passa com maior Δ reponderado. Pára quando nenhuma passa. Resultado = `robo_v4.py`, congelado com sha256 registrado abaixo ANTES do sorteio.

## Validação (dados novos, sem ajuste depois)
Sorteio aleatório simples de 20 dias do IS (2022-01-01 a 2025-09-30, ≥300 barras M1), fora dos 70 de `dias_usados.json`, nunca abr–out/2026: `numpy.random.default_rng(20261017).choice(candidatos_ordenados, 20, replace=False)`. Registrar como `ciclo4` em `dias_usados.json`.
Rodar v1, v2, v3, v4: total, R$/dia, acerto, fator de lucro, pior dia, dias +/−, por estrato. Pareado v4−v3: bootstrap por dia (10.000, IC 95%) e sign-flip (10.000). Nulo: 200 réplicas com entradas sorteadas (mesma contagem e geometria do v4). Caixa R$2.000 (1–2 contratos, pára < R$1.000).
Também: v3 e v4 acumulados nos 40 dias aleatórios (ciclos 3+4) — a única amostra ao calendário real.
Dias negativos do v4 → `ciclo4_negativos.json`. Nenhuma regra muda depois de ver os 20 dias.

## Congelamento do v4 (antes do sorteio)

**Montagem.** `ciclo4/cfg4.py` (motor + D1..D16, funções dos agentes importadas) sobre o v3. O motor foi estendido só em: conflito de lados (`empate` = None | desloc | vwap_maioria; D3/D4) e cadeia `post` que pára se uma etapa cancela a entrada (no v3 `post` é vazio). **Identidade:** sem candidata, o motor novo reproduz o v3 nos 70 dias (0 dias diferentes, trades idênticos; total R$6.716,72, reponderado R$61,70; e = cache do ciclo 3 nos 50 dias, dif máx 0,0). Candidatas tardias (embrulham toda a lista de FAZER): D11, D12; as demais na ordem D1<D2<D9<D13<D16 (a mesma da avaliação e do `robo_v4`).

**Conferência (cada candidata isolada sobre o v3, 70 dias; `p_confere.log`).** Todas reproduzem o Δ reponderado relatado (dif ≤ 0,005; tolerância ±0,10).

| id | Δrep relatado | Δrep port | Δ nd/dia | Δ dir/dia | Δ c0-2 (50d) R$ | Δ c3 (20d) R$ | pior/melhor | pior dia | LOO mín |
|---|---|---|---|---|---|---|---|---|---|
| D1 | +4,98 | +4,98 | +4,94 | +6,14 | +144,8 | +224,9 | 0/3 | -253,1 | +0,67 |
| D2 | +2,32 | +2,32 | +2,00 | +10,30 | +228,0 | +78,2 | 1/3 | -253,1 | +0,83 |
| D3 | +1,37 | +1,37 | +1,46 | -0,75 | -66,0 | +123,9 | 2/2 | -253,1 | -1,03 |
| D4 | +1,40 | +1,40 | +1,46 | 0,00 | -51,1 | +123,9 | 1/1 | -253,1 | -1,00 |
| D5 | +3,68 | +3,68 | +3,83 | 0,00 | +191,3 | 0,0 | 0/2 | -253,1 | +1,44 |
| D6 | +1,97 | +1,97 | +2,07 | -0,69 | -13,9 | +103,7 | 1/1 | -253,1 | -0,03 |
| D7 | +2,75 | +2,75 | +2,86 | 0,00 | +39,1 | +104,1 | 0/3 | -213,0 | +0,94 |
| D8 | +5,03 | +5,03 | +5,23 | 0,00 | 0,0 | +261,6 | 0/2 | -253,1 | +1,77 |
| D9 | +3,33 | +3,33 | +3,43 | +0,80 | +16,0 | +171,6 | 0/2 | -253,1 | +0,03 |
| D10 | +3,95 | +3,95 | +2,63 | +37,16 | +700,5 | +174,1 | 2/5 | -253,1 | +0,59 |
| D11 | +2,58 | +2,58 | +2,88 | -5,00 | -36,6 | +80,6 | 4/2 | -253,1 | +0,32 |
| D12 | +1,78 | +1,78 | +2,39 | -13,43 | -176,6 | +27,3 | 2/3 | -253,1 | +0,02 |
| D13 | +6,93 | +6,93 | +7,41 | -5,00 | +130,1 | +140,3 | 3/6 | -253,1 | +4,76 |
| D14 | +4,85 | +4,85 | +5,04 | 0,00 | 0,0 | +252,1 | 0/1 | -253,1 | 0,00 |
| D15 | +5,29 | +5,29 | +5,50 | 0,00 | 0,0 | +275,2 | 0/2 | -253,1 | +1,40 |
| D16 | +7,35 | +7,35 | +5,00 | +66,03 | +1.320,6 | +250,2 | 3/16 | -253,1 | +3,78 |

**Seleção para frente (critérios (a)-(e) exatos; `p_selecao.py`, `p_selecao.log`, `p_selecao.json`; 70 dias, Δ reponderado).**
- Passo 1 (base v3, rep 61,70): passam D1, D2, D5, D7, D9, D10, D13, D16 (D3/D4 falham (c) e (e); D6 falha (c) e (e); D8, D11, D12, D14, D15 falham (c) c0-2 ≤ 0 ou c3; D14 também (e)). Entra **D16** (+7,35).
- Passo 2 (rep 69,05): passam D1, D2, D5, D7, D9, D13; D10 cai em (e) (LOO −0,64); D6 vira −3,53. Entra **D13** (+6,93).
- Passo 3 (rep 75,98): passam D1, D2, D7, D9; D5 vira 0,00. Entra **D1** (+4,98).
- Passo 4 (rep 80,96): passam D2, D9 (D7 e D8 perdem (c) em c0-2). Entra **D9** (+3,33).
- Passo 5 (rep 84,29): passa D2 (+1,54, LOO mín +0,25). Entra **D2**.
- Passo 6 (rep 85,83): nenhuma passa (melhor Δ: D10 +2,72 mas LOO −0,64). Pára.
Resultado: **v4 = v3 + D16, D13, D1, D9, D2** (nessa ordem de entrada). Fora: D3, D4, D5, D6, D7, D8, D10, D11, D12, D14, D15.

**v3 × v4 nos 70 dias (as MESMAS em que tudo foi escolhido: é ajuste, não validação).**

| | total R$ | reponderado R$/dia | dir R$/dia | não-dir R$/dia | pior dia | ops | acerto | dias − | caixa final / mín (R$2.000) |
|---|---|---|---|---|---|---|---|---|---|
| v3 | 6.716,72 | 61,70 | 194,89 | 56,38 | −253,09 (2024-02-01) | 146 | 64,4% | 21 | 15.433,50 / 2.368,22 |
| v4 | 9.312,13 | 85,83 | 269,36 | 78,50 | −253,09 (2024-02-01) | 134 | 67,9% | 16 | 20.624,24 / 2.311,92 |

Δ v4−v3: +R$2.595,41 (c0-2 50 dias +1.741,43; c3 20 dias +853,98); Δ reponderado +24,13 (LOO mín +20,15, tirando 2024-04-26); 5 dias piores (−99,9 em 2022-03-07; −57,0; −32,0; −23,0; −7,3) e 28 melhores; nenhuma parada de caixa; risco máximo do dia 10,2% do caixa.

**Hashes (sha256).**
- `robo_v4.py`: `b503396addfbbcb689657fb16a57ccb7bfdad7c61b38ad243720b682098467f6`
- `ciclo4/cfg4.py`: `42c133785289f82ef690eb8c16726aa29a7754e722a47cf1209e16faa0d0fa50`

Nada mais é ajustado depois do sorteio dos 20 dias novos.

## Resultado da validação (rodado depois do congelamento; sha256 conferidos pelo script)
`ciclo4/p_validacao.py` → `p_validacao.log`, `p_validacao_resultados.json`, `../ciclo4_negativos.json`. 20 dias sorteados (seed 20261017, 867 candidatos): 1 bom, 4 intermediários, 15 ruins.

| | total | R$/dia | ops | acerto | FP | pior dia | dias +/− |
|---|---|---|---|---|---|---|---|
| v1 | +42,81 | 2,14 | 31 | 41,9% | 1,04 | −184 | 6/13 |
| v2 | +288,42 | 14,42 | 37 | 45,9% | 1,22 | −184 | 9/11 |
| v3 | +525,32 | 26,27 | 38 | 47,4% | 1,41 | −190 | 8/11 |
| **v4** | **+677,54** | **33,88** | 35 | 51,4% | 1,57 | −190 | 9/9 |

- Por estrato (v4): bom (1) +73 · intermediário (4) +888 · ruim (15) −284. O v3 no bom fez +296: o D16 (alvo ×2) cortou −222 no único dia direcional (2024-11-01).
- Pareado v4−v3: +152 (+7,61/dia), IC95 [−30; +52], sign-flip p=0,59, 4 melhores / 2 piores. v4−v1: p=0,17.
- Nulo (200 réplicas, geometria do v4): média −87, p95 665; v4 +678 → **p=0,05**.
- Caixa R$2.000: v3 termina 2.479 (mín 1.549), v4 2.537 (mín 1.549); nenhum parou.
- v3 em 40 dias aleatórios fora da sua amostra (ciclos 3+4): +R$836,81 (R$20,92/dia), 16 dias +, 23 −.
- Dias negativos do v4: 9 (todos ruins): 2022-02-09 −190, 2024-01-09 −134, 2023-06-02 −117, 2025-04-02 −91, 2022-03-22 −71, 2023-11-17 −55, 2024-07-10 −25, 2025-01-16 −24, 2025-07-17 −17.
- Leitura: v4 ≥ v3 nos dados novos, mas a diferença não se separa do acaso. Dentro da amostra o ganho era +24/dia reponderado; fora, +7,6/dia — de novo cerca de 1/3. O robô segue perdendo nos dias de rotação.
