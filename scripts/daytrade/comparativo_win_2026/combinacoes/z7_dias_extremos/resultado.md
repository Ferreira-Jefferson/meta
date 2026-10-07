# Z7 - regra generica para dias extremos (G1 gap, G2 dia seguinte a pregao largo)

Veredito pelo criterio pre-registrado (>= 4 de 5 anos melhores na SOMA com custo R$2/op E acima do p95 do sorteio de mesmo numero de dias por ano, 1.000 sorteios, semente 20261006):

| regra | dias bloq. (22/23/24/25/26) | anos melhores | delta soma | percentil | veredito |
|---|---|---|---|---|---|
| G1 k=1,0 | 3/0/2/2/3 (10) | 4 (2023 sem bloqueio) | +1.749 | 99,8 | APROVADA |
| G1 k=1,5 | 1/0/2/0/1 (4) | 3 | +1.318 | 99,8 | REFUTADA (anos) |
| G1 k=2,0 | 0/0/1/0/1 (2) | 1 | +542 | 95,5 | REFUTADA (anos) |
| G2 m=2,0 | 4/4/6/10/4 (28) | 2 | -506 | 46,6 | REFUTADA |
| G2 m=2,5 | 0/1/0/3/2 (6) | 1 | -806 | 15,3 | REFUTADA |

Soma dos 5 robos, liquido com custo (R$), base e delta por ano:

| ano | base | G1 k1,0 | G1 k1,5 | G1 k2,0 | G2 m2,0 | G2 m2,5 |
|---|---|---|---|---|---|---|
| 2022 | 2.790 | +883 | +308 | 0 | -421 | 0 |
| 2023 | 3.999 | 0 | 0 | 0 | +70 | +156 |
| 2024 | 1.140 | +468 | +468 | 0 | -96 | 0 |
| 2025 | 4.193 | +103 | 0 | 0 | -287 | 0 |
| 2026 | 9.292 | +295 | +542 | +542 | +228 | -962 |
| total | 21.414 | +1.749 | +1.318 | +542 | -506 | -806 |

Ressalvas (honestas):
- G1 k=1,0 e UM veredito aprovado entre 5 regras testadas; sem correcao de multiplicidade. Sao so 10 dias em 4,8 anos.
- Em 2026, +295 depende de 05/10 (+542): sem esse dia, 2026 fica -247 e a regra passaria a 3 de 5 anos. A regra nao foi escolhida por outubro (pre-registrada), mas o criterio passa por pouco.
- O ganho e concentrado: 2022-10-31 (+575, pos-eleicao 2o turno), 2026-10-05 (+542), 2024-03-08 (+468), 2022-02-24 (+308, Ucrania). Contra: 2026-04-08 (-304), 2025-05-12 (+151).
- Por robo (G1 k1,0, total, anos melhores): Cinco +1.796 (4), Deslocamento -125 (1), Win_c1 -145 (1), Win +107 (1), Ret34 +116 (2). O ganho vem quase todo do CincoMedias (2022: +1.249).
- G2 (dia seguinte a pregao largo) nao ajuda: os dias pos-largos sao normais para os robos.
- Eleicoes: 02/10/2022 e domingo (sem pregao); 03/10/2022 gap 1,36 ATR (so k=1,0; 0 operacoes); 31/10/2022 gap 1,44 ATR (so k=1,0; removeu -575); 05/10/2026 gap +17.775 pts = 5,11 ATR (todas as k; removeu -542, 3 ops).

## Metodo
- Diarias das M1 do WIN$N (2022-2025 + dados.m1 2025-10 em diante, sem duplicatas), velas ate 18:25. ATR14 = media simples do TR dos 14 pregoes anteriores (sem o corrente).
- Rolagem: constatado empiricamente que o WIN$N salta NO DIA DO VENCIMENTO (gap 1,2-1,6 ATR so nessas datas, ex.: 15/10/2025, 17/12/2025), nao no dia seguinte como `ini_contrato` supoe. Opcao usada: EXCLUIR do G1 o 1o pregao >= vencimento (28 dias) e usar apenas (maxima-minima) como TR desse dia no ATR. A 1a versao (dia seguinte) bloqueava 27 dias, 17 deles falsos de rolagem.
- G2 usa a amplitude do pregao anterior / ATR14 vigente naquele pregao (sem olhar o futuro).
- Todas as 1.713 operacoes entram e saem no mesmo dia (0 excecoes), logo bloquear dia = remover entradas do dia.
- Operacoes ate 05/10/2026. Sorteio: por ano, n dias iguais aos da regra, entre os pregoes do ano.

Arquivos: z7.py, resultado.csv (por regra, por ano e por robo), dias_bloqueados.csv (data, gap, amplitude em ATR, ops, liquido removido, nota), base_por_ano_robo.csv, saida.log.
