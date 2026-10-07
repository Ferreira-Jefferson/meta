# V1 — candidatas CONGELADAS (escrito em 2026-10-06 ANTES de rodar o VAL)

## Etapa 1 (2026) — reprodução com o WdoRetangulo e filtro do pré-registro
Reprodução COM o WdoRetangulo contra o CSV da frente (linhas idênticas por entrada/saída/lado/rs ÷ linhas do CSV): **13/13 candidatas reproduzem 100%** (C1 146/146, C2 292/292, C3 35/35, C4 56/56, C5-C7 181/181, C8-C9 308/308, C10-C11 65/65, C12 733/733, C13 426/426; mesmo número de operações).
O `WdoRetangulo.csv` foi apagado de `resultados/` (exclusão do dono); para o E (que lê as posições de todos os votantes) ele foi reconstruído das próprias operações em `f0_fundacao/eventos.parquet` (`v1/_base_com_wdo/`), só para a prova de reprodução.

Filtro (líquido com R$2/op, janela 2026; variante: Δ > 0 contra o próprio original; nova: > R$841):

| id | robô | regra | líq. sem Wdo | líq. original | Δ | critério | segue |
|---|---|---|---|---|---|---|---|
| C1 | Win_c1 | B filtro tabela | 3680.0 | 3425.0 | 255.0 | delta > 0 | True |
| C2 | WinCincoMedias | A1 filtro consenso, comum | 7985.0 | 8243.0 | -258.0 | delta > 0 | False |
| C3 | WinDeslocamentoMatinal | A1 filtro consenso, individual | 1206.0 | 2089.0 | -883.0 | delta > 0 | False |
| C4 | WinDeslocamentoMatinal | A1 filtro consenso, comum | 3209.0 | 2089.0 | 1120.0 | delta > 0 | True |
| C5 | Win | E V2b | 3673.0 | 3635.0 | 38.0 | delta > 0 | True |
| C6 | Win | E V1a | 3545.0 | 3635.0 | -90.0 | delta > 0 | False |
| C7 | Win | E V1b | 3673.0 | 3635.0 | 38.0 | delta > 0 | True |
| C8 | WinCincoMedias | E V3b | 8430.0 | 8243.0 | 187.0 | delta > 0 | True |
| C9 | WinCincoMedias | E V3a | 8308.0 | 8243.0 | 65.0 | delta > 0 | True |
| C10 | WinDeslocamentoMatinal | E V3a | 2177.0 | 2089.0 | 88.0 | delta > 0 | True |
| C11 | WinDeslocamentoMatinal | E V3b | 2133.0 | 2089.0 | 44.0 | delta > 0 | True |
| C12 | WinRetanguloEma34 | B resize pela nota | 1627.0 | 841.0 | 786.0 | delta > 0 | True |
| C13 | ConsensoGatilho | A2 gatilho de consenso WF | 5148.0 | - | - | liq > 841 | True |

**Seguem para o VAL (10):** C1, C4, C5, C7, C8, C9, C10, C11, C12, C13. **Caem em 2026 sem o WdoRetangulo (3):** C2 (Δ −258), C3 (Δ −883), C6 (Δ −90).
Observação declarada: sem o WdoRetangulo a "outra família" dos robôs de tendência é só o WinRetanguloEma34, então **C5 (V2b) e C7 (V1b) viram a MESMA regra** (mesmas 181 operações, mesmo Δ). Os dois entram no VAL e no Holm como candidatas separadas, como o pré-registro lista; o resultado dos dois é idêntico por construção. C8–C11 (V3, outro membro da própria família) não dependem do WdoRetangulo e ficam iguais ao original das frentes.

## Regras congeladas (as 13 funções estão em `v1_regras.py`; cada uma é a regra da frente, sem mexer em parâmetro nem grade)
| id | robô | regra da frente |
|---|---|---|
| C1 | Win_c1 | B, filtro "entra ou não" pela tabela de frequência (fav 0–3), limiar walk-forward, MES_MIN_FILTRO=4 |
| C2 | WinCincoMedias | A1, filtro de consenso, variante comum ao conjunto (9 variantes, melhor do passado, padrão `maj`) |
| C3 | WinDeslocamentoMatinal | A1, escolha individual |
| C4 | WinDeslocamentoMatinal | A1, variante comum |
| C5 | Win | E V2b (qualquer um da outra família contra, só no lucro) |
| C6 | Win | E V1a |
| C7 | Win | E V1b |
| C8 | WinCincoMedias | E V3b |
| C9 | WinCincoMedias | E V3a |
| C10 | WinDeslocamentoMatinal | E V3a |
| C11 | WinDeslocamentoMatinal | E V3b |
| C12 | WinRetanguloEma34 | B resize pela nota (modelo `nota`, grade 3x3 de alvo/stop, mediana do passado) |
| C13 | ConsensoGatilho | A2 gatilho (≥3 votos, ≥1 de cada família; stop e alvo em múltiplos de ATR M5 {1,2,3} x {1,2,3}, célula do passado) |

Votantes sem o WdoRetangulo: Win, WinCincoMedias, WinDeslocamentoMatinal (T) e WinRetanguloEma34 (R). C13 passa a exigir 3 dos 4 (≥1 T, e o WinRetanguloEma34 obrigatório).

## Execução no VAL (2024-07-01 → 2025-09-30), fixada antes
- Walk-forward: mesmo laço das frentes, com o mês sendo a chave sequencial ano*12+mês; o passado é expansivo e inclui 2024-01..06. Janela aplicada: 2024-07..2025-09 (15 meses). C12: modelo `nota` treinado nos meses anteriores; com <20 eventos de RetEma34 no passado fora da amostra ele fica na célula (1,1), como na frente.
- Operações: as do robô com **entrada** na janela. Meses/trimestres das tabelas pela data de **saída**. Trimestres: 2024T3, 2024T4, 2025T1, 2025T2, 2025T3 (5).
- Δ = Σ(rs − R$2) da candidata − Σ(rs − R$2) do original do mesmo robô na janela, **sem truncar na quebra** (os robôs operam sem parar por saldo). Para as saídas (E) o número de operações não muda, então Δ com custo = Δ sem custo.
- Capital R$1.000 corrido por ordem de saída, a partir de 2024-07-01. Quebra = saldo ≤ 0 em algum ponto (data marcada, a curva segue). Maior queda = máx(pico − saldo), com pico inicial R$1.000. Fator de recuperação = líquido com custo ÷ maior queda. Fator de lucro = Σganhos ÷ Σperdas (líquido de custo). Payoff = ganho médio ÷ perda média (líquido de custo). Acerto = % de operações com líquido > 0.
- **Teste, unilateral, 2.000 sorteios, semente 20261006**, p = (1 + nº de sorteios com Δ_sorteio ≥ Δ_real) ÷ 2001:
  - filtros (C1, C4): sorteio mantém ao acaso, entre as entradas do original na janela, o MESMO número de operações que a candidata manteve (mesma fração cortada);
  - saídas (C5, C7–C11): `virada.sorteio_instante` — permuta, entre as operações disparadas, o instante da saída (mesmo nº de saídas antecipadas, mesma distribuição de tempo desde a entrada; nas (b) só vale se estiver no lucro);
  - resize (C12): a regra da frente — o escore da nota é trocado por uniforme sorteado e a mesma escolha walk-forward é refeita (célula escolhida no passado com o escore sorteado); Δ contra o original;
  - nova (C13): sorteio de lado nos MESMOS gatilhos (mesmo horário), com a mesma célula de stop/alvo do mês da candidata; compara o líquido com custo da candidata com o do sorteio.
- Holm sobre o conjunto que chegou ao VAL (10 candidatas), α = 0,05. (O pré-registro dizia 13; a lista que segue é a regra dada pelo pedido. O Holm com m = 13 também é reportado, sem mudar a classificação principal.)
- Classificação, exatamente pelo pré-registro. Variante: APROVADA = Δ>0 e p Holm<0,05; PROMISSORA = Δ>0, fator de recuperação maior que o do original e p bruto<0,10, sem passar no Holm; REFUTADA = o resto. Nova (C13): APROVADA se líquido com custo > o do pior original no VAL (menor líquido com custo entre os 5 robôs), sem quebra, fator de lucro ≥ 1,2, ≥3 de 5 trimestres positivos, p bruto ≤ 0,05 (percentil ≥95) **e** p Holm<0,05; senão REFUTADA. (Leitura estrita; a leitura só com p bruto ≤0,05 também é reportada.)

## SHA-256 (conferidos no momento do congelamento)
| arquivo | sha256 |
|---|---|
| `v1_regras.py (as 13 regras)` | `4c976de1b31861c2c9b610d594c5b487dc5e689e6a6d77a121ad20fe97837d5b` |
| `v1_val.py (execucao do VAL)` | `a9b2d45a2ff73bd3e7cfe768b78973edd29a996b69696845315cebdbb218ef40` |
| `v1_2026.py (etapa 2026)` | `bc74472018860de0dca9973c3119c50f82668206f31ba97ae71dce44f6257f0a` |
| `v1_niveis_val.py` | `2ce21c4249c8494dbe74d6df660bb2b8c8ed9803658d62ee77b954bf374afd68` |
| `a_consenso/consenso_filtro.py` | `8445030fb60c4e039b4c02c66ea98393c4c40307213b308f40cd6bb77968feaf` |
| `a_consenso/consenso_gatilho.py` | `d9425f9b6311c80ec479ef4abfe27d48fbf24dbd0832d7ea244843cff091fb29` |
| `b_nota/comum.py` | `fd3c3d102d348bc66592c1f51685233ec40c995423a38c0a11e60a618293768f` |
| `e_saida_virada/virada.py` | `243b9ef01eda7ae0b7efb8c3d68cf9da5b46459bda6d57d7a4b38173da37682d` |
| `f0_fundacao/saida.py` | `ad4e53691dfc1e1b7512943a67b9624111554b45e39f14415acc93be5bfc4a25` |
| `port_win.py (importado por consenso_gatilho)` | `1ee9f24ef68b3eb28287855bc5352d29c1b21bce035819b526c9c7f22a367432` |
| `port_retangulo_ema34.py (niveis do C12)` | `9ad9e21730f6b9f898c4b6c3c6697d7fab19fd0f6ad0128998184da3e724ca08` |
| `dados.py` | `94beee8af3fe27aa40bfd86dcba6595542119bd3479ae55b5f8833d270984e16` |
| `v0/dados_val.py` | `d67ade7079bb06f9dabb3554c844c5bb858c4ec3384fd974145d2a60452aeaf3` |
| `v0/votos_val.parquet` | `31548111afd840cf2a06541cbc2638b09b16f9991ab925b306812e6018013c50` |
| `v0/eventos_val.parquet` | `aae823dcef975a8bd1b35bdf3065f2f99d5adb7762d8b441e5eaa8c9d310fca8` |
| `v1/retema34_niveis_val.csv` | `1a467e2a49444707b0dde437f6d1505e3980b9e309664fc91a0ccbd178fe5866` |
| `v1/filtro_2026.csv` | `63f47b86a1d09f7f58566d5c9a3fc61d21c0db8e80b39e7ba1c437017ec3661e` |
| `v0/resultados/Win.csv` | `85d1cf5a198f51f9d55ff90bf4bb5f4157acd6e4c9c92b9e43b631dd7f9b70ac` |
| `v0/resultados/Win_c1.csv` | `2c8a73736c288b1c24e867c19ae76449e6a81b3ffd2b8e99c9f249d710abe088` |
| `v0/resultados/WinCincoMedias.csv` | `faf8d94ce316b1d827a6b1d975fcbe22f05c5e97181b68ace123a43cc8972aee` |
| `v0/resultados/WinDeslocamentoMatinal.csv` | `032e3d1f6017d5be6d9bb38821622302363ca9e66182aa49685e42e8e77f6d5d` |
| `v0/resultados/WinRetanguloEma34.csv` | `cf750ae49b3f4fa5c58909160429d82e1e9adf8440d620e876bb4e439ad2780d` |
