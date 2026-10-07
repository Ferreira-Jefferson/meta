# PRE-REGISTRO MM (escrito antes de rodar) - win_deslocamento_matinal + media movel

Base: config CONGELADA (X0,3, stop linha, sem alvo, EnterLimit ultimo preco ttl 15), WIN@, capital reposto por pregao (nominal),
fila P2 (76.000/76.000) como decisao; P0 como referencia. IS 2021-10..2024-12. Baseline IS P2 = 143 trades, +4.144,50, +28,98/op.

## Grade (11 celulas + baseline), MM so' com barras fechadas ate' 10:30 (M5 completas; diaria ate' D-1)
| id | tipo | regra |
|---|---|---|
| A_e10, A_e20, A_e50 | alinhamento | nao opera se preco 10:30 do lado errado da EMA10/20/50 M5 (EMA corre entre pregoes) |
| A_s10d, A_s20d | alinhamento | idem vs SMA10/20 dos fechamentos diarios ate' D-1 |
| S30, S15 | inclinacao | EMA20 M5 subindo (compra) / caindo (venda) vs 30 / 15 min antes |
| E15, E25 | esticado | nao opera se abs(preco - EMA20 M5) > k ATR, k=0,15 / 0,25 |
| P30, P60 | recuo | limite em EMA20 M5 (compra: min(ultimo, EMA); venda: max) em vez do ultimo preco, ttl 30 / 60 barras M1; stop igual |
Vizinhas: A_e10-A_e20-A_e50; A_s10d-A_s20d; S30-S15; E15-E25; P30-P60.

## Criterio de escolha (SO' na IS, P2) - todos obrigatorios
(a) R$/op > baseline (+28,98); (b) liquido IS >= 90% da baseline (>= +3.730,05);
(c) 2022, 2023 e 2024 positivos; (d) pelo menos uma vizinha tambem com R$/op > baseline.
Maximo 2 escolhidas (maior R$/op entre as que passam). Reporto IC95% (bootstrap por pregao) e win% vs breakeven empirico.
OOS (2025-01..2026-09) roda UMA vez para as escolhidas + baseline; nada e' retocado depois.
Desenho de execucao inalterado (EnterLimit+ttl, stop a mercado, anchor_exits_at_fill, sem alvo, achatamento). Max 3 workers.
