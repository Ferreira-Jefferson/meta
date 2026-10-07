# Z9-T1 preempcao total

Regra: o sinal de outro robo encerra a posicao a mercado (`preco(t)`, t = entrada do novo) e ele assume a `preco_entrada` dele. T1b: mesmo lado so' transfere a gestao (preco de entrada original, saida do novo robo, 1 operacao). Mesmo robo: ignora. Empate: ordem de ROBOS. Custo R$2/operacao, R$1.000 por ano, 1 contrato.

Aproximacao: robo interrompido/bloqueado nao altera as operacoes seguintes dele; sinal so' existe no instante da entrada; sinal de robo que ja' tem a posicao e' ignorado (nao e' contado como assumido).

## Por ano (liquido c/ custo, ops, acerto %, maior queda R$, quebra)

| ano | soma isolada liq* | T1 liq | T1 ops | T1 acerto | T1 DD | T1 quebra | T1b liq | T1b ops | T1b acerto | T1b DD | T1b quebra |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 5026  | 4136 | 473 | 42.9 | 2005 | None | 5071 | 355 | 44.5 | 1935 | None |
| 2023 | 4512  | 1038 | 455 | 44.4 | 1761 | None | 1806 | 335 | 45.7 | 1655 | None |
| 2024 | 4720  | 979 | 477 | 43.2 | 2461 | None | 1961 | 351 | 43.9 | 1803 | None |
| 2025 | 5208  | 1297 | 344 | 42.7 | 1504 | None | 1982 | 245 | 42.4 | 1228 | None |
| 2026 | 14079  | 6548 | 361 | 44.9 | 1462 | None | 7073 | 254 | 44.1 | 1460 | None |

*soma isolada = soma das operacoes isoladas dos 5 robos (sem NETTING): 2022 +5.026, 2023 +4.512, 2024 +4.720, 2025 +5.208, 2026 +14.079.

## Por robo -- T1 (liquido c/ custo pelo dono ao fechar (em T1b a cadeia transferida fica toda com o ultimo dono, entao o liquido por robo nao e' atribuicao justa); anos somados 2022-2026)

| robo | sinais | assumiu | interrompido | ops (dono) | liquido R$ |
|---|---|---|---|---|---|
| WinGapBarra1 | 530 | 530 | 371 | 530 | 4042 |
| WinCincoMedias | 815 | 815 | 225 | 815 | 589 |
| WinDeslocamentoMatinal | 244 | 244 | 89 | 244 | 5633 |
| WinRetanguloEma34 | 343 | 343 | 39 | 343 | 2403 |
| Win_c1 | 178 | 178 | 29 | 178 | 1331 |

Por ano e robo (liquido): 2022: WinGapBa 1621, WinCinco 1403, WinDeslo 182, WinRetan 871, Win_c1 59; 2023: WinGapBa -365, WinCinco 48, WinDeslo 1098, WinRetan 17, Win_c1 240; 2024: WinGapBa -25, WinCinco 366, WinDeslo 1118, WinRetan -252, Win_c1 -228; 2025: WinGapBa 836, WinCinco -1207, WinDeslo 1119, WinRetan 575, Win_c1 -26; 2026: WinGapBa 1975, WinCinco -21, WinDeslo 2116, WinRetan 1192, Win_c1 1286

## Por robo -- T1b (liquido c/ custo pelo dono ao fechar (em T1b a cadeia transferida fica toda com o ultimo dono, entao o liquido por robo nao e' atribuicao justa); anos somados 2022-2026)

| robo | sinais | assumiu | interrompido | ops (dono) | liquido R$ |
|---|---|---|---|---|---|
| WinGapBarra1 | 530 | 530 | 371 | 285 | -20215 |
| WinCincoMedias | 815 | 815 | 225 | 612 | 15216 |
| WinDeslocamentoMatinal | 244 | 244 | 89 | 169 | 12976 |
| WinRetanguloEma34 | 343 | 343 | 39 | 325 | 4506 |
| Win_c1 | 178 | 178 | 29 | 149 | 5410 |

Por ano e robo (liquido): 2022: WinGapBa -5360, WinCinco 4882, WinDeslo 2677, WinRetan 1464, Win_c1 1408; 2023: WinGapBa -4722, WinCinco 3178, WinDeslo 1290, WinRetan 901, Win_c1 1159; 2024: WinGapBa -3269, WinCinco 1741, WinDeslo 3019, WinRetan 128, Win_c1 342; 2025: WinGapBa -3228, WinCinco 1481, WinDeslo 1967, WinRetan 839, Win_c1 923; 2026: WinGapBa -3636, WinCinco 3934, WinDeslo 4023, WinRetan 1174, Win_c1 1578
