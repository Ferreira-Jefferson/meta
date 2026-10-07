# X2 - ranking do DEV (2022-01-03 a 2024-06-28, com custo R$2/op) - REFUTADA NO DEV
SHA-256 seletor.py: 10ae2e58f8969f3cf28822961e3dc58cf600b84747de9196313f2675b725a046

| robo | ops | liq c/ custo | queda | fator rec. | acerto % |
|---|---|---|---|---|---|
| Win | 566 | -2.299 | 3.433 | -0,67 | 32,5 |
| Win_c1 | 593 | -1.514 | 2.805 | -0,54 | 30,2 |
| WinCincoMedias | 1191 | +764 | 2.849 | 0,27 | 39,0 |
| WinDeslocamentoMatinal | 114 | +1.428 | 917 | 1,56 | 43,9 |
| WinRetanguloEma34 | 525 | -4.642 | 4.657 | -1,00 | 36,6 |

Prioridade P1: Desloc > Cinco > Win_c1 > Win > RetEma34. P2: Desloc > Cinco > RetEma34 > Win > Win_c1. P3: alfabetica (Win, Cinco, Desloc, RetEma34, Win_c1).

| var | ops | liq s/ custo | liq c/ custo | acerto | payoff | FL | queda | FR | meses+ | quebra | ignoradas | empates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 1805 | +2.791 | -819 | 37,8 | 1,69 | 0,98 | 3.106 | -0,26 | 14/30 | SIM | 1184 | 367 |
| P2 | 1791 | +2.701 | -881 | 38,4 | 1,63 | 0,98 | 3.015 | -0,29 | 14/30 | SIM | 1198 | 366 |
| P3 | 1827 | +2.471 | -1.183 | 37,9 | 1,65 | 0,98 | 2.889 | -0,41 | 14/30 | SIM | 1162 | 388 |

Nenhuma variante tem liquido com custo > 0 e sem quebra. Variante: NENHUMA. VAL e 2026 NAO rodados (regra: parar).
