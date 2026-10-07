# Placar forward -- regras congeladas (escrito antes do primeiro resultado, 2026-10-05)

Estrategia: `win_deslocamento_matinal` em WIN@D, M1, 1 contrato, motor do repo, fila P2, capital reposto por pregao (nominal).
Parametros: `desloc_min_atr=0.3`, sem stop ATR, sem alvo ATR (mesmos de `mm/run_mm_multi.BASE`). **Nada muda de parametro.**

| variante | regra |
|---|---|
| BASE | sem media |
| E100 | preco do lado da EMA100 M5 |
| P_10_100 | preco do lado da EMA10 e da EMA100 M5 |

## Janela forward
- Comeca em **2026-10-01** (primeiro pregao nunca usado; a OOS terminou em 2026-09-30).
- Vai ate o ultimo pregao COMPLETO. Recalculado do zero a cada execucao (idempotente).
- Dados: M1 do `WIN@D` do MT5 (conferido contra o CSV de pesquisa nos dias sobrepostos).

## Criterio de decisao (pre-registrado)
1. Placar mensal e' **so informativo**.
2. Decisao formal quando a BASE somar **>= 40 operacoes forward** (~10 meses).
3. Uma variante substitui a BASE **somente se** liquido >= BASE **e** MaxDD <= BASE.
4. Entre E100 e P_10_100 (ambas cumprindo 3), vence o **maior fator de recuperacao** (liquido / MaxDD).
5. Se nenhuma cumprir, **fica a BASE**.

## Adendo 2026-10-06 — variante BASE_R10_cap1000

Acrescentada por decisão do dono depois do estudo `risco/`: a regra que passou a valer no EA (v1.30, `RiscoMaxPct=10`). Teto de stop = 10% do caixa atual, stop apertado até o teto (mínimo 2 ticks), capital CONTÍNUO a partir de R$1.000, fila P2. Regras congeladas como as demais. Linha informativa: mede daqui para frente a regra adotada; não entra no critério de desempate E100 × P_10_100.

## Adendo 2026-10-06 (2) — variante R10_volM30_cap1000

Igual à BASE_R10_cap1000 + saída por clímax de volume CONTRA a posição (regra do WinCincoMedias v2.01: vela M30 FECHADA com volume relativo à mediana do mesmo horário nos 20 pregões anteriores ≥ quantil 90 do histórico, mínimo 100 velas; corpo contra a posição; sai a mercado na abertura seguinte). Candidata do estudo `alvo_volume/` (IS +R$325 / OOS +R$843 sobre a referência; OOS não cega). Histórico do quantil = todo o M1 baixado (desde 15/08/2026). Linha informativa, comparada com BASE_R10_cap1000; adoção só com dado forward.
