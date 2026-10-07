# Resumo -- alvo que se aproxima e saida por volume (WIN@, R$1.000 continuo, teto 10%, fila P2)
OOS 2025-26 ja vista antes: nao e' cega. Tabelas completas: `resultado.csv` (analisa.py). Pre-registro: PRE_REGISTRO.md.
Referencia reproduzida: IS 143 trades +R$3.021,50 (MaxDD R$1.181); OOS 113 trades +R$5.267,50 (MaxDD R$1.268).

- ALVO QUE SE APROXIMA: NAO replica. IS: 5 de 6 celulas quebram o caixa (-R$900 a -R$950, 48-101 trades, censuradas); a unica que
  nao quebra (A3 N5) faz +R$868 contra +R$3.022. OOS: todas abaixo da referencia (+R$3.846 a +R$4.952 contra +R$5.268). O controle de alvo fixo
  mostra que o alvo em si ja destroi (1,5R: -R$176 IS; 2R: -R$910 IS); a aproximacao nao salva e cada reposicionamento volta ao fim da fila.
  Motivo: a estrategia ganha no dia de tendencia que corre ate' o fechamento; qualquer alvo corta justamente esse ganho (payoff 1,53 -> 1,2-1,3).
- SAIDA POR VOLUME: so' a versao com corpo CONTRA tem sinal (qualquer vela: -R$1.700 a -R$1.800 OOS e quebra o caixa na IS).
  V2 (WinCincoMedias, M30) e' a unica positiva nas duas janelas e em 4/4 anos IS (2021 +82 vs +448 pior; 2022 +342 vs -234): IS +R$3.347 (+R$325),
  OOS +R$6.111 (+R$843), MaxDD IS 1.004 (menor que ref). V1 k2 contra: IS +R$3.279, OOS +R$5.478 mas MaxDD OOS 1.414 (maior). Ganho pequeno
  e dentro do ruido (n=143/113): MANTER como candidata, nao adotar.
- JUNTAS: piores que a saida por volume sozinha (o alvo contamina). IS 3 de 4 quebram o caixa.
