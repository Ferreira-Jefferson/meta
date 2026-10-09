# WIN$N M1/M5 sem os leiloes (gerado 2026-10-06)

Gerado por `scripts/daytrade/gera_bases_win_sem_leiloes_2026_10_06.py` com `carrega_win_m1_sem_leiloes`
(`src/market_data_intraday/win_sem_leiloes.py`), a partir de `data/comparativo_win_2026/m1_WIN$N.parquet` (2025-10 a 2026-10)
e `m1_WIN$N_2022_2025.parquet` (2021-12 a 2025-09). So WIN$N (preco nao ajustado); WIN@/WIN@D nao foram gravados.

Arquivos: `m1_*` e `m5_*` em `.parquet` e `.csv` (TSV, layout MT5 `<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>`,
SPREAD=0) + `PROXY`, `FLAG_LEILAO`, `ULTIMA_CONTINUA`, `HL_APROX` (0/1). `dias_*.csv` (separador `;`): uma linha por pregao
(`call_preco`, `call_volume`, `leilao_preco`, `leilao_hora`, `leilao_volume`, `proxy`, `*_estimado`, `ultima_barra_continua`...).
M5 reamostrado DEPOIS do ajuste, ancorado em 09:00.

## O que mudou em relacao a base original
- Barras a partir do fim do pregao da grade (18:25, ou 17:55 antes de 2024-03-11 nos periodos de horario de verao dos EUA) foram descartadas (call).
- A ultima barra do continuo (`ULTIMA_CONTINUA=1`, 18:24 / 17:54) tem close = ultimo negocio continuo e volume sem o call.
- A barra do leilao de abertura (`FLAG_LEILAO=1`) tem volume sem o leilao; com fases (abr-out/2026) o open passa a ser o 1o negocio continuo.
- Zerar posicao: use `ULTIMA_CONTINUA`, nunca "ultima barra do dia".

## O que e aproximado
- Com ticks (`tem_fases=True`, 2026-04-06 em diante, tabela `data/win_fases_pregao_6m.csv`): valores medidos. Excecoes na tabela, coluna `fonte`=`ticks+M1`:
  2026-05-06 e 2026-08-10 (lacuna de ticks na fonte, volume/max/min completados pelo M1) e 2026-09-24 (leilao lido da 1a barra M1 09:02; volume do leilao estimado, 1o negocio continuo desconhecido).
- Antes de 2026-04-06 (e 2025-10 a 2026-04-03) nao ha ticks: `PROXY=1` na barra do call. Close do call = close da barra anterior; volume do call e do leilao = excesso sobre
  a mediana das 5 barras vizinhas (`*_volume_estimado=True`); o OPEN da barra do leilao NAO e corrigido; high/low so sao encolhidos quando o preco removido era a propria maxima/minima (`HL_APROX=1`, limite inferior do intervalo real).
- 2026-04-10: a maxima de 198580 do M1 do dia e o preco do call (18:24), nao divergencia de ticks; na base sem leilao ela deixa de existir.

## Pregoes depois de 2026-10-05 (desde 2026-10-09)
`m1_WIN$N.parquet` esta CONGELADO (ate 2026-10-05). Os pregoes seguintes entram em `m1_WIN$N_AAAA-MM.parquet`, um por mes, gerados por `scripts/daytrade/atualiza_bases_mt5.py` com o mesmo tratamento (fases por tick). Leia com `market_data_intraday.bases_versionadas.le_win("m1_WIN$N.parquet")`, que junta os pedacos.
