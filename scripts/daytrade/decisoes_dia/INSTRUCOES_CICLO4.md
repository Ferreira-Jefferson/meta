# Ciclo 4 → 5: análise dos dias negativos do robo_v4

Leia `INSTRUCOES_CICLO.md` inteiro (itens 5–7 valem: dinheiro na mesa, hipóteses ordenadas pelo retorno, gestão adaptativa) e `INSTRUCOES_CICLO3.md`. Leia `ciclo4/PREREGISTRO.md`, `robo_v4.py`, `ciclo4/cfg4.py` (motor e como plugar candidata) e `ciclo4_negativos.json`.

## O que mudou
1. **Robô base: `robo_v4.py`.** "Não quebrar" é medido nos **90 dias** de `dias_usados.json` (ciclos 0–4). Use o motor de `ciclo4/cfg4.py` (`cfg4.monta(robo_v4.IDS)` + a sua mudança) e confira que, sem mudança, reproduz o v4.
2. **Métrica:** R$/dia reponderado (direcional ef ≥ 0,25 = 3,8%; não-direcional = 96,2%), estrato não-direcional, e o efeito separado nos 40 dias aleatórios (ciclos 3+4) — os únicos ao calendário real. Reporte também leave-one-day-out (mínimo do Δ reponderado tirando cada dia).
3. **Já se sabe (não repita):** entrada cedo a favor da perna (E1/G6/B_F1) ganha em direcional e perde em rotação; nenhum A2 condicional separa perdedoras; soltar vetos de compra de queda custa caro; religar vetos após a 1ª op custa −14/dia; reversão à VWAP e alvo curto/trava em rotação pioram.
4. **Os 9 negativos do v4 são TODOS dias de rotação (ef < 0,15).** Nos 40 dias aleatórios os ruins somam perda em todas as versões. Pergunta central: o que, observável no momento da decisão, separa a operação que perde em rotação da que ganha — ou qual repertório ganha em rotação sem custar nos outros dias?
