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

## Congelamento do v4
(preencher antes do sorteio)
