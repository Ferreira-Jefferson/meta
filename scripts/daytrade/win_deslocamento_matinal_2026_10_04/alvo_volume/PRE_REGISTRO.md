# Pre-registro -- alvo que se aproxima e saida por volume (win_deslocamento_matinal, WIN@)

Escrito ANTES de rodar. Data 2026-10-06.

## Base (referencia)
`win_deslocamento_matinal` adotada: decisao 10:30, desloc >= 0,3 ATR14, EnterLimit ttl 15, stop do outro lado da
abertura com teto `risco_max_pct=0.10` do caixa, SEM alvo, sai no fim do pregao. Capital CONTINUO R$1.000, 1 contrato,
fila P2 (2 x V_barra, entrada e saida), `limit_fill_capped_by_volume`, `anchor_exits_at_fill`.
IS 2021-10..2024-12 (referencia esperada: 143 trades, +R$3.021,50). OOS 2025-01..2026-09.
**A OOS 2025-26 ja foi vista em rodadas anteriores desta estrategia: nao e' cega.** Veredito = consistencia IS + OOS + ano a ano.
Aquecimento de 40 pregoes (so' historico de volume/ATR; entradas bloqueadas antes da janela, como `roda_risco`).

## Regra 1 -- ALVO QUE SE APROXIMA
R = |preco de entrada - stop efetivo| (depois do teto de 10%). Alvo-limite real fatiada (exit_split_unit=1, sem prazo).
Inicia em `A` x R; a cada `N` velas M5 FECHADAS depois do fill, aproxima 0,22 R; piso 1,1 R (nunca menos que o stop).
Mecanismo: `AdjustTarget` do motor; o motor cancela a limite parada e rearma no nivel novo ENTRANDO NO FIM DA FILA
(fila cheia de novo) -- cada aproximacao paga a fila outra vez (realista, mantido).
Grade: A in {1,5; 2; 3} x N in {5; 10} = 6 celulas. Controle: alvo fixo (sem aproximar) em 1,5R/2R/3R (3 celulas) para isolar o efeito da aproximacao.
Contagem: so' velas M5 que COMECAM em/apos o fill (a vela do fill nao conta).

## Regra 2 -- SAIDA POR VOLUME (so' velas JA FECHADAS; so' velas que comecam em/apos o fill)
Disparo -> `Exit` do motor = SAIDA A MERCADO na ABERTURA da barra seguinte (como saida de protecao; motivo SIGNAL). Declarado: nao e' limite.
- V1 (media): vela M5, volume >= k x media das 20 velas M5 anteriores (historico continuo entre pregoes), k in {2; 3};
  versao "qualquer" e versao "contra" (corpo contra a posicao) = 4 celulas.
- V2 (WinCincoMedias v2.01, SAIDA_VOL): vrel = volume / MEDIANA do mesmo horario nos 20 pregoes anteriores (min 5); dispara se
  vrel >= quantil 90 expansivo das vrel anteriores (min 100 velas, a vela atual fora do quantil), corpo CONTRA;
  M30 e M5 = 2 celulas. Diferenca: o historico do quantil comeca no inicio do aquecimento da janela (nao no inicio do contrato).

## Combinacoes (SO' pela IS)
Escolher, em cada regra, as 2 melhores celulas na IS (alvo: 6 celulas da grade; volume: 6 celulas V1+V2), por:
(1) entre as que tem MaxDD R$ IS <= MaxDD da referencia, maior liquido IS; (2) se menos de 2 cumprirem, completa pelo maior
fator de recuperacao (liquido/MaxDD) IS. Combinar 2x2 = 4 celulas (alvo + saida por volume juntos). Roda IS e OOS.

## Metricas por celula e janela
trades, liquido, capital final, R$/op, acerto, ganho/perda medios, payoff, saidas por STOP/alvo/volume(SIGNAL)/fim do dia,
MaxDD R$ e %, fator de recuperacao, liquido por ano, "trades alterados vs referencia" (dias com PnL diferente e soma da diferenca R$).
