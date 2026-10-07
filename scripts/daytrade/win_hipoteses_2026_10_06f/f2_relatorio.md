# f2 — Figuras gráficas / estrutura como filtro ou saída do WinCincoMedias v2.02 (WIN, só 2026)

Baseline reproduzido: +R$8.377,14 · 13/14 janelas · pior −117,00 · PF 1,77 · 248 trades · DD 781,50 · sem setembro 7.785,61.

## Método
- Pivôs fractais (k velas de cada lado), contados só a partir da vela de **confirmação** p+k; pivôs diários só a partir do pregão seguinte à confirmação. Dados insuficientes = filtro neutro (não corta). Features calculadas por contrato (segmento), como a estratégia.
- Cada variante roda com 10 sementes de filtro aleatório que corta a mesma fração de sinais alinhados (por lado e por segmento); percentil = % das sementes com líquido abaixo do filtro real. Saída por figura: controle aleatório com a mesma frequência de gatilhos por barra.
- Saída por topo/fundo duplo: cópia exata de `simula` (extraída por `inspect` e com um único gancho; sem o gancho reproduz o baseline exato).
- Candidata exigiria: líquido, janelas+ (≥13), pior (≥ −117), DD (≤ 781,50), sem setembro (> 7.785,61), meses melhores > piores, ≥150 trades, percentil ≥ 90 e platô.

## Variantes: 112 (104 isoladas + 8 combinações AND dos melhores) = 1.232 rodadas contando o controle aleatório
| família | n | acima do baseline em líquido | melhor líquido | % ≥ p90 do aleatório |
|---|---|---|---|---|
| estrutura HH/HL (M30 k2/3/5; diário k1/2/3; modos full, hl, hh, não-contra) | 24 | 3 | 8.908 (dia k3 hh) | 2 |
| rompimento (N 12/24/48, dia anterior, semana; só rompe / não rompe; m 1/3/6) | 30 | 0 | 7.500 | 4 |
| barreira (pivô M30 k3/k5, diário k2; espaço ≥ 0,5…3 ATR) | 15 | 2 | 8.467 | 2 |
| congestão (range N/ATR vs quantil; contração N vs N anteriores) | 27 | 0 | 8.216 | 1 (+0 contração) |
| saída topo/fundo duplo (k 2/3, tol 0,2…1,0 ATR) | 8 | 3 | 8.487 | 0 |
| combinações | 8 | 5 | 8.971 | 4 |

## Melhores linhas (líq · janelas · pior · PF · trades · DD · sem set · meses melh/pior · aleatório mediana/máx · percentil)
| variante | líq | jan | pior | PF | trades | DD | sem set | m+/m− | rand med/máx | pct |
|---|---|---|---|---|---|---|---|---|---|---|
| AND estrutura diária k3 hh + barreira diária 2,0 ATR | 8.970,61 | 13/14 | −352,50 | 2,11 | 201 | 781,50 | 8.209,61 | 6/3 | 7.632/8.806 | 100 |
| estrutura diária k3 "hh" | 8.908,14 | 12/14 | −314,00 | 1,97 | 224 | 781,50 | 8.316,61 | 2/1 | 8.228/8.973 | 90 |
| barreira diária k2 ≥ 0,5 ATR | 8.466,81 | 13/14 | −117,00 | 1,79 | 241 | 781,50 | 7.929,31 | 3/3 | 8.265/8.457 | 100 |
| barreira diária k2 ≥ 2,0 ATR | 8.416,11 | 14/14 | +11,00 | 1,88 | 218 | 781,50 | 7.655,11 | 5/4 | 7.449/9.125 | 90 |
| saída duplo k2 tol 0,6 | 8.487,44 | 13/14 | −117,00 | 1,78 | 249 | 727,50 | 7.895,91 | 4/2 | 8.148/9.263 | 80 |
| congestão: range6/ATR acima do quantil 0,3 | 8.215,54 | 13/14 | −117,00 | 1,89 | 206 | 744,34 | 7.498,51 | 5/6 | 7.116/8.769 | 90 |

## Leitura
- Nenhuma das 112 satisfaz todos os critérios. Os ganhos de líquido (até +R$590) vêm com perda de janela positiva e/ou pior mês (−314 a −418 contra −117), ou deixam o aleatório na mesma faixa (máx do aleatório 8.8k–9.3k em quase todas).
- Estrutura diária: melhor líquido, mas o pior mês piora de −117 para −314 (a estratégia v2.02 já faz o "a favor da tendência" pelo mês); os modos vizinhos (full, ncontra, hl) oscilam 7.8k–8.5k e o k vizinho (2 vs 3) não repete → sem platô.
- Barreira diária: 0,5 e 2,0 ATR melhoram, 1,0 e 1,5 pioram (7.534 e 7.913): ziguezague, não platô. O de 2,0 tem 14/14 e pior +11, mas perde em sem setembro (7.655 < 7.786) e fica no percentil 90 com semente aleatória chegando a 9.125.
- Rompimento e contração: sempre abaixo do baseline (cortam bons sinais; "não rompe" reduz DD mas cai o líquido a 6.9–7.5k). Congestão: filtros mais seletivos baixam o DD (≈403–450) mas custam >R$1.000.
- Saída por topo/fundo duplo: efeito quase nulo (±R$100), dentro do ruído do aleatório (percentil 40–80).
- Combinações são seleção sobre as mesmas 112 linhas do mesmo ano: o ganho (8.971, percentil 100) tem 6 meses melhores, 3 piores, mas pior −352 e janelas 13/14 → não domina o baseline; e é escolhido pós-fato.

## Conclusão
**Nenhuma supera a atual.** `f2_candidatas.py::CANDIDATAS` fica vazio. Candidatas fracas descartadas, caso o dono queira olhar: estrutura diária k3 hh e barreira diária 2,0 ATR (ambas perdem no pior mês/sem setembro e não têm platô).

Arquivos: f2_figuras.py, f2_figuras_stdout.log, f2_resumo.csv, f2_res.pkl.
