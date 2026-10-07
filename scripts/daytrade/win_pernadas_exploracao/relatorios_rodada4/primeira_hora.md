# Reversão da 1ª hora (R22) transformada em regra de entrada: WIN, 2026

## Método
- Dados: WIN@D M1, só 2026. Descoberta jan–jun (122 pregões), confirmação jul–ago, referência set. Código: `rodada4/primeira_hora/` (`core_ph.py`, `descoberta.py`, `congela.py`, `confirma.py`).
- Gatilho: ao fechar uma vela M1 dentro da janela, se |fechamento − fechamento K minutos antes| ≥ M, deixa-se uma limite CONTRA o movimento em fechamento ± d (vende acima após alta, compra abaixo após queda). Um pedido por vez.
- Grade: janela {09:00–09:30, 09:30–10:00, 10:00–10:30, NY a NY+30 (10:30 com horário de verão dos EUA, 11:30 sem, R28)} × M {150,250,350} × K {5,10,15} × d {0,50,100} × prazo {5,10 min} × alvo {100,150,200,300} × stop {150,250,400} = **2.592 configurações** (todas rodadas em descoberta, confirmação e set; alvo mínimo 100 pts, nunca 1 tick).
- Preenchimento conservador: a limite enche só se o preço negociar 1 tick (5 pts) além do nível, dentro do prazo. Otimista: enche ao tocar. Alvo, idem (5 pts além no conservador). Na vela do preenchimento só o stop conta (pessimista). Stop e alvo na mesma vela: stop primeiro. Stop paga 5 pts de deslize. Custo 2 pts por operação. Posição aberta há 30 min é zerada a mercado (paga 5 pts de deslize). Atraso realizado de preenchimento reportado em minutos (≈1,8–2,2 min).
- Esperança em pts por operação, líquida; IC 95% por bootstrap de dias (400 reamostras).
- Nulo: velas M1 de cada pregão embaralhadas dentro de blocos de 30 min (7 embaralhamentos, grade inteira, jan–jun).

## Descoberta (jan–jun), premissa conservadora
- Configurações com n ≥ 150: 2.475. Esperança média da grade: **−19,4 pts/op**. Só 6,5% têm esperança > 0 e **nenhuma tem IC inferior > 0**.
- Média por janela: 09:00 −25,6; **09:30 −6,0**; 10:00 −19,3; NY −25,0. d maior ajuda (d=0 −21,5; d=100 −16,9); alvo e stop quase indiferentes.
- Nulo: média da grade −18,9 a −23,3 (igual ao real, −19,4); fração com EV>0 de 3% a 12% (real 6,5%); **máximo por embaralhamento de 21,6 a 49,2 pts (real 28,4)**. O melhor resultado real está dentro do que o acaso produz entre 2.592 tentativas.
- Platô: o único canto com vizinhança positiva é 09:30, M250, K10, d=100, prazo 5, alvo 200, stop 150–250 (mapa abaixo). Fora desse canto, vizinhos negativos.

Mapa 09:30–10:00, M=250, K=10, prazo 5, esperança conservadora em pts (colunas = stop 150 / 250 / 400):

| d | alvo | descoberta | confirmação jul–ago |
|---|---|---|---|
| 0 | 100 | −20,3 / −4,9 / −6,0 | −16,7 / 4,4 / 3,3 |
| 0 | 150 | −19,3 / −8,3 / −8,3 | −3,2 / 8,9 / 2,9 |
| 0 | 200 | −13,2 / −2,1 / −4,7 | −2,7 / 10,9 / 10,2 |
| 0 | 300 | −17,1 / −5,9 / 12,1 | −9,7 / 7,5 / 19,5 |
| 50 | 100 | −6,4 / 2,6 / −6,4 | −8,5 / −0,4 / −1,7 |
| 50 | 150 | 0,7 / 10,6 / 2,4 | −0,9 / 2,2 / 17,4 |
| 50 | 200 | −4,4 / 7,8 / −2,8 | 1,8 / 9,5 / 9,8 |
| 50 | 300 | −14,8 / 9,9 / −10,2 | 5,5 / −1,5 / −26,4 |
| 100 | 100 | −1,1 / −5,0 / −7,6 | 8,0 / −0,3 / 22,2 |
| 100 | 150 | 15,1 / 4,6 / −6,0 | 24,1 / 8,6 / 37,0 |
| 100 | 200 | 19,7 / 17,8 / 4,0 | 14,6 / −17,1 / 37,5 |
| 100 | 300 | 17,7 / 13,7 / −4,8 | 13,6 / −2,0 / 33,7 |

## Lista congelada (escrita antes de rodar jul–ago)
Critério: n ≥ 150, vizinhança com média > 0 e ≥ 60% dos vizinhos positivos; mais as duas melhores por esperança bruta.
1. 09:30, M250, K10, d100, prazo 5, alvo 200, stop 150.
2. 09:30, M250, K10, d100, prazo 5, alvo 200, stop 250.
3. 09:30, M350, K10, d50, prazo 10, alvo 200, stop 400 (topo da grade).

## Confirmação (jul–ago) e set, premissa conservadora (otimista entre parênteses)

| Config | Descoberta | Confirmação jul–ago | Set (referência) |
|---|---|---|---|
| 1 | n223, fill 60%, acerto 49,8% × BE 44,2%, **+19,7** [−0,1; 43,6] (+21,3) | n60, 48,3% × 44,2%, **+14,6** [−23,9; 52,8] (+26,2) | n50, 42,0% × 44,2%, −7,9 [−49,8; 41,2] (+3,8) |
| 2 | n197, 60,4% × 56,5%, +17,8 [−12; 50] (+21,3) | n55, 52,7% × 56,5%, **−17,1** [−55; 40] (−1,6) | n42, −18,7 (+1,5) |
| 3 | n151, fill 84%, 70,9% × 66,0%, +28,4 [−14; 75] (+39,7) | n36, 66,7% × 67,3%, **−3,7** [−94; 77] | n35, −73,0 (−73,0) |

Grade inteira: esperança média −19,3 (desc) → −8,4 (jul–ago) → −24,7 (set); fração positiva 7,1% → 33,8% → 11,1%. Correlação entre esperança de descoberta e de confirmação entre configurações: 0,22. Os melhores de cada janela: 09:00 +11,6 → +10,2; 09:30 +28,4 → −3,7; 10:00 +15,3 → −19,9; NY +3,8 → −22,1. As janelas 09:00 e 09:30 ficam em média levemente positivas em jul–ago (+3,3 e +3,2) mas 10:00 e NY continuam negativas.

## Veredito
Não há vantagem demonstrada depois de custos. A reversão de 5–15 min existe em variância, mas a faixa capturada por uma limite com alvo ≥ 100 pts é menor que custo + perdas de stop: a grade média perde ~19 pts/op, igual ao nulo embaralhado. Dos 3 congelados, 1 sobrevive em sinal em jul–ago (com IC cruzando zero, n=60) e nenhum em set. Premissa de fila otimista melhora a esperança em 2–12 pts/op e dá a falsa impressão de edge em alguns casos (ex.: config 1 em set −7,9 → +3,8). Hora 09:30–10:00 com d=100 é o único canto candidato; precisa de mais pregões antes de qualquer uso.
