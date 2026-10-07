# Volume sintético no WIN: participação de avanço e recuo (2026)

Código e tabelas em `rodada4/volume_sintetico/` (`volume_sintetico.py` = medidas; `prep_ticks.py`; `validacao.py`; `eventos.py`; `run_nulo.py`; `analise.py`; `alcance*.py`; `descr.py`). Só dados de 2026. Descoberta jan–jun, confirmação jul–ago (regras congeladas em `regras_congeladas.json` antes de rodar a confirmação), setembro só referência.

## 1. Medidas construídas (todas fechadas no minuto, normalizadas pelo mesmo minuto dos 20 pregões anteriores, janela ±2 min)
| medida | fonte | existe |
|---|---|---|
| negócios/min relativos (TICKVOL rel; `nt` dos ticks) | M1 / ticks | ano todo / mar+ |
| contratos/min relativos (VOL rel) | M1 | ano todo |
| contratos por ponto andado (esforço × resultado) | M1 | ano todo |
| tamanho médio (VOL/TICKVOL rel) | M1 | ano todo |
| delta pela regra do tick (contratos) e delta acumulado | ticks | mar+ |
| delta ponderado pela vela: `vol·(2c−h−l)/(h−l)` (CLV) e `vol·sinal(c−o)·|c−o|/(h−l)` (corpo/range) | M1 | ano todo |
| razão RECUO/AVANÇO (negócios, contratos, tamanho, delta) do mesmo movimento | derivada | — |

Observação: TICKVOL do M1 não é o nº de negócios; é ~3,3× o nº de negócios dos ticks, mas correlaciona 0,988 por minuto. Serve como "contagem de ticks" em qualquer gráfico (a ideia do dono funciona como contagem). VOL do M1 = soma do volume dos ticks (corr 0,9995).

## 2. Validação contra o delta real (WINV26 com flags, 12/08–30/09: 35 pregões, 19.694 minutos)
| medida sintética | corr. 1 min | acerto de sinal 1 min | corr. 15 min | corr. acumulado do dia | mediana corr. acum./dia |
|---|---|---|---|---|---|
| regra do tick (ticks WIN@D) | **0,928** | 93,4% | 0,960 | 0,879 | 0,934 |
| regra do tick (ticks WINV26) | 0,926 | 92,5% | 0,956 | 0,870 | 0,949 |
| candle corpo/range (só M1) | 0,844 | 86,4% | 0,863 | 0,753 | 0,885 |
| candle CLV (só M1) | 0,652 | 72,3% | 0,698 | 0,481 | 0,736 |
| sinal do corpo × volume (só M1) | 0,742 | 86,4% | 0,773 | 0,689 | 0,804 |

- A regra do tick reproduz bem o delta por minuto (corr 0,93; fração delta/volume 0,96), melhor que o "78% por negócio" porque o erro se cancela dentro do minuto. Ela subestima a magnitude (beta 0,70 contra o real). O acumulado do dia deriva (0,88 no agregado).
- Pior na 1ª hora (corr 0,77 às 09–10; 0,97 depois).
- Sem ticks, o delta por corpo/range é o melhor substituto (0,84), muito melhor que o CLV (0,65).
- Estável entre agosto (0,94) e setembro (0,92).

## 3. Teste: depois de avanço A e recuo r, a participação no recuo × avanço muda o que vem?
Evento: zigzag de 150+ pts de avanço A, recuo de r = 38/50/62% de A, **decisão no fechamento da vela M1** que atinge o recuo (nada olhado adiante); os dois sentidos espelhados. Participação de cada vela alocada nos trechos do caminho em proporção ao comprimento. Base = mesmo nível de recuo e mesmo bloco de horário (<11h, 11–13h, ≥13h) da mesma janela; nulo = velas M1 embaralhadas em blocos de 30 min (300 simulações, as velas levam seu volume/delta junto), o mesmo código. Recuos com menos de 0,25 min de recuo ou de avanço são descartados.
Execução (esperança): limite na região do fechamento (enche só se negociar 1 tick = 5 pts abaixo em até 5 min), alvo por limite (1 tick além), stop a mercado +5 pts, custo 2 pts, saída de tempo em 60 min. Geometrias G1 = alvo 200/stop 200; G2 = 400/200.

Eventos: descoberta 5.813 (110 dias; delta por ticks: 4.287 em 83 dias, mar–jun); confirmação 1.769 (44 dias); set 957 (21 dias).
Base sem condição (descoberta): P(novo extremo) 47,8% / 38,0% / 25,7% nos níveis 38/50/62% (≈ 1−r, igual ao acaso da R32); MFE30 ≈ MAE30 ≈ 320 pts; esperança líquida da execução −13 a −20 pts/op nas duas geometrias (o custo e o stop em 98% dos preenchimentos pesam; sem borda).

Medidas testadas (12): N1 negócios/min no recuo; N2 razão negócios recuo/avanço; V2 razão contratos; E1 contratos por ponto no recuo; E2 razão esforço recuo/avanço; S1 tamanho médio no recuo; S2 razão; P1/P2 delta por corpo/range no recuo e diferença recuo−avanço; D1/D2/D3 delta por regra do tick no recuo, diferença, e acumulado do movimento. Cortes pelos tercis da descoberta (baixo ≤ 1/3, alto ≥ 2/3), 6 desfechos: P(novo extremo), P(chegar a 2A), MFE30, MAE30, esperança G1, esperança G2.

### Descoberta: 144 testes (12 medidas × 2 lados × 6 desfechos)
|z|≥2: 17 (acaso esperado ~6); |z|≥2,5: 9 (~1,8). Regra de congelamento escrita antes: |z|≥2,5 contra o nulo, IC bootstrap por dias excluindo zero, n≥200, mesmo sinal nas duas metades da descoberta. Passaram 2.

### Lista congelada (antes da confirmação)
1. **S1 alto → P(chegar a 2A) maior** (+3,1 pp; z 2,9; IC [0,0; +6,2]).
2. **D3 alto → P(chegar a 2A) maior** (+3,8 pp; z 3,0; IC [+0,1; +8,0]).

### Confirmação (jul–ago, 44 dias)
| regra | descoberta | confirmação | setembro |
|---|---|---|---|
| S1 alto → P(2A) | +3,1 pp (n 1.757, z 2,9) | **−1,9 pp (n 445, z −1,0)** | +3,0 pp (n 79) |
| D3 alto → P(2A) | +3,8 pp (n 1.372, z 3,0) | **+1,8 pp (n 584, z 1,0)** | −1,1 pp (n 326) |
**As duas falharam** (nenhuma com |z|≥2; S1 inverteu).
Varredura de todas as 144 células sem congelamento: 11 com |z|≥2 em jul–ago, 5 em setembro (acaso ~6 e ~6). Das 17 da descoberta, 14 mantiveram o sinal na confirmação, mas só 2 com |z|≥2 (não congeladas): **S1 baixo → MFE30 menor** (−30 pts → −42 pts; set −38) e **D3 alto → esperança G2 maior** (+18 → +30 pts/op, z 2,5; set −19). Nenhuma sobrevive ao crivo prévio; são pistas fracas, não regras.

### Alcance do próximo movimento (correlação de postos medida × MFE60/A, 100 nulos; 12 medidas × 3 janelas)
Sem controle do tamanho do avanço, parecia haver sinal estável nas 3 janelas: N2 (−0,14, z −4,7/−2,9/−2,3), V2 (−0,14), D3 (+0,10, z 6,1/3,5/2,3), S1. **Era o tamanho do avanço:** avanços grandes têm razão recuo/avanço mais alta e MFE/A menor. Estratificando por faixa de A (<250, 250–400, 400–750, ≥750) as correlações caem a |r| ≤ 0,07 e z inconsistentes (N2 0,8/−0,4/−1,7; V2 1,1/0,0/−1,7; D3 2,2/0,6/1,3). Em pontos absolutos a MFE60 mediana é ~igual entre tercis de N2 (440–510 pts na descoberta).

## 4. Contagem de testes
Descoberta: 144 (tercis) + 12 (alcance bruto) + 12 (alcance estratificado) = 168. Confirmação: 2 regras congeladas (+ varredura informativa de 144 + 12). Setembro: referência.

## 5. O que se conclui
- O volume sintético existe e é bom: delta pela regra do tick tem corr 0,93 por minuto com o real; TICKVOL é bom substituto da contagem de negócios; sem ticks, o delta corpo/range (0,84).
- Participação no recuo × avanço (negócios, contratos, esforço por ponto, tamanho do negócio, delta) **não muda** P(novo extremo), P(2A), a distribuição de MFE/MAE em 30 min nem a esperança do alvo/stop em jul–ago. Reforça R15, R18, R32: o recuo é lido só pela distância; a participação descreve (o volume seca no recuo) mas não prevê.
- Cuidado de método: razões recuo/avanço estão confundidas com o tamanho do avanço; sempre estratificar por A.
- Limitações: decisão no fechamento do M1 e alocação proporcional ao caminho (convenção); 83 dias de ticks na descoberta; delta por regra do tick subestima magnitude; setembro com amostra pequena.
