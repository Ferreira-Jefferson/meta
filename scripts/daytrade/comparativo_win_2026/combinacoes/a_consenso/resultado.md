# Frente A: consenso / maioria

Base: votos e eventos da F0, WIN 02/01-05/10/2026, R$1.000, 1 contrato. Votantes: Win, WinCincoMedias, WinDeslocamentoMatinal, WinRetanguloEma34, WdoRetangulo (Win_c1 fora). Voto lido na ultima M1 fechada; no primeiro minuto do pregao conta como neutro.
Celulas olhadas: parte 1 = 9 variantes x 6 escopos (5 estrategias + conjunto) = 54 (mais 54 numa tabela fixa, so referencia); parte 2 = 9 (stop x alvo). Total 63 celulas. Controle: 200 sorteios. Placebo de votante: 200 sorteios (parte 1) e 40 (parte 2).

## Parte 1: consenso como filtro (saida original)
Variantes: k>=1,2,3 (outras a favor); maioria (a favor > contra); outra familia sem ninguem contra; outra familia a favor liquido; ponderado pela forca >= 0,5/1,0/1,5.
Walk-forward: mes m escolhe a variante com maior liquido R$2/op das saidas em meses < m. Padrao de janeiro (declarado antes): maioria.

| escopo | ops (sem filtro) | liquido s/custo | R$2/op | sem filtro s/custo | sem filtro R$2 | pct vs sorteio | DD R$2 | quebra |
|---|---|---|---|---|---|---|---|---|
| Win | 106 (181) | 2.346 | 2.134 | 3.997 | 3.635 | 52 | 709 | nao |
| WinCincoMedias | 274 (308) | 8.630 | 8.082 | 8.859 | 8.243 | 77,5 | 989 | nao |
| WinDeslocamentoMatinal | 35 (65) | 2.973 | 2.903 | 2.219 | 2.089 | 97 | 682 | nao |
| WinRetanguloEma34 | 389 (733) | 357 | -421 | 2.307 | 841 | 8 | 1.288 | 28/05/2026 (R$2) |
| WdoRetangulo | 98 (134) | 2.938 | 2.742 | 2.837 | 2.569 | 76 | 1.178 | nao |
| **conjunto 5, variante comum** | 1.055 (1.421) | **19.974** | **17.864** | 20.219 | 17.377 | **94,5** | 1.813 | nao |
| conjunto 5, soma das escolhas individuais | 902 (1.421) | 17.244 | 15.440 | 20.219 | 17.377 | 89,5 | 1.365 | nao |

Melhor isolada: WinCincoMedias +8.859 (R$2: 8.243). Conjunto comum por mes (s/custo): jan 4.129, fev 1.919, mar 1.196, abr 3.038, mai 1.106, jun 267, jul 1.445, ago 2.220, set 4.168, out 486. Com R$2/op: 3.967, 1.699, 910, 2.780, 882, 45, 1.281, 1.962, 3.916, 422. Tabelas por estrategia: `resultado_mensal_filtro.csv`.
Escolhas do conjunto: maioria em jan-mar, depois k>=1 de abril em diante (o filtro mais frouxo). Variantes fixas sobre o conjunto (referencia, nao walk-forward): k1 +20.570, maioria +18.607, k2 +13.190, k3 +4.796.

Leitura: o consenso nao melhora o liquido total (19.974 contra 20.219 sem custo; +487 com R$2, porque tira operacoes). O percentil 94,5 contra o sorteio mostra que ele escolhe um pouco melhor que cortar ao acaso a mesma quantidade, abaixo de p95. A queda maxima fica igual ou pior. Filtros mais duros (k3, ponderado 1,5) cortam o lucro quase na proporcao do que cortam.

Placebo de votante (conjunto, variante comum; liquido real 19.974 / R$2: 17.864):

| votante trocado por lado sorteado | placebo media s/custo | p5..p95 | percentil do real |
|---|---|---|---|
| Win | 19.760 | 18.196..21.116 | 56 |
| WinCincoMedias | 19.311 | 17.404..20.807 | 73 |
| WinDeslocamentoMatinal | 19.913 | 18.783..20.957 | 50,5 |
| WinRetanguloEma34 | 15.953 | 13.063..18.602 | 99,5 |
| WdoRetangulo (placebo natural) | 18.742 | 17.175..20.003 | 94,5 |

So o voto do WinRetanguloEma34 carrega informacao (trocar por sorteio derruba 4 mil); os de tendencia nao (Win e Desloc: trocar por sorteio nao muda nada). Mas a informacao do RetEma34 e mais "ele tem posicao contraria" do que consenso: ele vota quase sempre (EMA34 mesmo sem retangulo).

## Parte 2: consenso como gatilho (estrategia nova)
Regra declarada: >=3 votos no mesmo lado, pelo menos 1 de tendencia e 1 de retangulo, na transicao; ordem-limite no ultimo fechamento, prazo 3 min, linhas 09:04-16:58; 1 posicao por vez; stop a mercado, alvo em limite, em multiplos do ATR M5 (grade stop {1,2,3} x alvo {1,2,3}); zera 17:50; janeiro stop 2 / alvo 2. 1.770 gatilhos, 426 operacoes executadas na versao walk-forward.

Grade (total jan-out, s/custo / R$2): (1,1) 1.598/-270; (1,2) 4.705/3.305; (1,3) 4.196/3.112; (2,1) -57/-1.483; (2,2) 5.125/4.133; (2,3) 4.953/4.181; (3,1) 301/-929; (3,2) 5.174/4.302; (3,3) 4.621/3.953. Alvo de 1 ATR perde; alvos 2-3 ATR ganham em todos os stops.
Walk-forward: escolhe (3,2) de abril em diante.

| | ops | s/custo | R$2/op | DD R$2 | quebra | acerto |
|---|---|---|---|---|---|---|
| ConsensoGatilho walk-forward | 426 | +4.015 | +3.163 | 2.295 | nao | 57,7% |

Por mes (s/custo): jan 1.025, fev 731, mar -259, abr 1.446, mai -1.091, jun 733, jul 909, ago 1.506, set -987, out 2. R$2: 929, 645, -331, 1.340, -1.187, 643, 823, 1.402, -1.093, -8. Queda maxima R$2.223-2.295 num capital de R$1.000 (caixa corrido nao quebra porque o lucro de jan-fev cobre).
Controle (mesmos horarios, lado sorteado, mesma celula do mes, 200 sorteios): mediana -178 (R$2: -1.009); a versao real fica no percentil 91,5. Abaixo de p95.
Placebo de votante (40 sorteios, um sorteio por episodio de voto): WinCincoMedias trocado -> media +552 (real no percentil 97,5, o unico voto que importa); WinRetanguloEma34 -> 2.928 (p87,5); Desloc -> 3.283 (p67,5); Win -> 4.201 (p52,5); WdoRetangulo -> 4.369 (p40). Win e WdoRetangulo trocados por acaso nao mudam nada: o gatilho vive do WinCincoMedias.
Ressalva: a grade de multiplos do ATR mostra que o resultado vem da geometria alvo 2-3 ATR e stop largo; com a lado sorteado a mediana e negativa, entao a direcao do consenso agrega algo, mas o ganho nao ultrapassa p95. Ordens mais frouxas do gatilho nao foram testadas.

## Comparacao
| item | s/custo | R$2 |
|---|---|---|
| melhor isolada (WinCincoMedias) | 8.859 | 8.243 |
| soma sem filtro (5 sem Win_c1) | 20.219 | 17.377 |
| A1 filtro walk-forward (conjunto) | 19.974 | 17.864 |
| A2 gatilho walk-forward | 4.015 | 3.163 |

Bases escolhidas olhando 2026: o walk-forward protege so a camada de combinacao.

Arquivos: consenso_filtro.py, consenso_gatilho.py, resultado_resumo.csv, resultado_mensal_filtro.csv, resultado_variantes_fixas.csv, resultado_placebo_filtro.csv, escolhas_walkforward_*.csv, resultado_gatilho_*.csv, resultado_placebo_gatilho.csv, trades/ (A1_filtro_conjunto_comum.csv, A1_filtro_conjunto_individual.csv, A2_gatilho_walkforward.csv), gatilho.log.
