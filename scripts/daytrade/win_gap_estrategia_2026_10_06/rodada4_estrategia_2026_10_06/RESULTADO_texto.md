# WIN gap — rodada 4: V2 r0 como estratégia (stop × alvo, classe, EA_SPEC)

Entrada fixa V2 r0 (1ª barra M5 contínua fecha contra o gap; limite no close dela; ttl 6 barras M5). IS 2026-04-06..2026-10-05, 120 pregões, simulador a tick da rodada 2, R$1.000, sizing de produção (2 contratos no modo B; 1 a 5 no modo A), fills `toque` e `atrav+1t`. Critério de escolha escrito antes da tabela: `CRITERIO.md`. A IS é a janela onde a pista nasceu: nenhum número desta rodada é fora da amostra.
Reprodução: `run4.py` → `analise4.py` → `holdout4.py` → `crosscheck4.py` → `tabela_escolha.py` → `gera_resultado.py`.

## 1. Mapa stop × alvo (110 células)

Linhas = stop em pontos; colunas = alvo (R = distância do stop; P50@1R = metade em 1R, resto até o fim; BE1R = stop vai para a entrada depois de +1R, sem alvo).

```
{{HEAT}}
```

- Líquido B (toque) varia de R$1.226 (S300|BE1R) a R$12.858 (S1200|3R); **110 de 110 células com líquido B > 0**, nos dois fills (`atrav+1t` idêntico: a ordem no close enche com ≥ 1 tick de folga).
- Por stop, a coluna "sem alvo" é a maior ou praticamente empatada com a maior em 8 dos 10 stops; os alvos fixos (500 a 2000 pts) rendem menos em todo stop (ex.: S700: sem alvo R$9.572; T2000 R$6.880; T500 R$2.698). Exceções: S1200 com 3R (R$12.858 contra R$10.928) e S1500 com BE1R (R$12.410 contra R$12.222), e S1000 com BE1R (R$11.088, empate com R$11.108).
- R$/trade da coluna "sem alvo": R$78 (S300), R$154 (S700), R$176 (S1200), R$197 (S1500).
- Sobe com o stop: a coluna "sem alvo" vai de R$4.808 (S300) a R$12.222 (S1500), com salto até S500 (R$9.478) e depois subida lenta (R$8.500 a R$12.222 de S600 a S1500).

## 2. Censura do modo A (conta contínua R$1.000)

```
{{CENSURA}}
```

6 de 110 células censuradas, todas com stop 1500 e alvo (500, 1000, 1500, 1R, 1,5R, P50@1R): 3 por ordens recusadas por capital (31 em T1500, 31 em 1R, 34 em P50@1R; caixa mínimo R$4, R$4 e −R$96) e 3 só por caixa mínimo abaixo da margem de R$100 (T500 R$58, T1000 R$76, 1,5R R$48). Nenhuma célula com stop ≤ 1200 é censurada; a coluna "sem alvo" nunca é.

## 3. Platô (vizinhos = stops a ±1 e ±2 posições, mesmo alvo)

```
{{PLATO}}
```

- **700 está num platô, não num pico.** Na coluna "sem alvo": 10 de 10 stops com líquido B > 0 e p do nulo de direção ≤ 0,05; os 4 vizinhos de 700 (500, 600, 800, 900) são positivos e acima do nulo; líquido de 700 = R$9.572 contra mediana dos vizinhos R$9.721 (razão 0,98). Nenhum dos 11 alvos tem 700 como pico (razão de 0,88 a 1,33; 1R é o mais alto, 1,33, ainda abaixo do limite de 1,5).
- Forma da curva "sem alvo" em R$: S300 4.808 · S400 7.142 · S500 9.478 · S600 8.500 · S700 9.572 · S800 9.964 · S900 10.174 · S1000 11.108 · S1200 10.928 · S1500 12.222. Cai abaixo de 500; de 500 a 1500 é uma faixa de R$8.500 a R$12.200 com inclinação positiva suave (não é um topo em 700).
- O líquido B cresce com o stop porque o stop largo chega perto de "segurar até o fim"; o risco por trade cresce junto: stop de 700 = R$140 por contrato (R$280 com 2 contratos), 1200 = R$240 (R$480), 1500 = R$300 (R$600). MaxDD B: S700 R$1.785, S1200 R$2.535; MaxDD A: S700 R$2.678 (16,9%), S1200 R$6.771 (29,6%); lucro/DD B 5,36 contra 4,31.

## 4. Seleção na grade (nulo de máximo) e metades

```
{{SELECAO}}
```

p ajustado pelo máximo de 110 células (mesmo sorteio de direção para todas as células, estatística t = excesso sobre o nulo da própria célula): 19 de 110 células com p ajustado < 0,05; melhor t em S500|sem alvo (p ajustado 0,021); S700|sem alvo 0,035; célula escolhida 0,035. Metades abr–jun (56 pregões) × jul–out (64): 103 de 110 células positivas nas duas; correlação de postos 0,68; o top 10 de abr–jun é dominado por S1000-S1200 e sem alvo/BE1R, o de jul–out por S1500 (stops largos cada vez melhor).

## 5. Escolha (CRITERIO.md)

```
{{ESCOLHA}}
```

**Célula escolhida: stop 1200 pts, sem alvo (segura até o fim do contínuo).** Pontuação (mediana do líquido B dos 3 vizinhos 900, 1000 e 1500; o stop 1200 só tem 3 dentro de ±2 posições) R$11.108; líquido B da célula R$10.928 (razão 0,98 sobre os vizinhos: não é pico); mínimo célula+vizinhos R$10.174; p da célula 0,002, ajustado 0,035; abr–jun R$5.382, jul–out R$5.546; modo A não censurado nos dois fills (caixa mínimo R$466), 100% dos vizinhos não censurados. O melhor platô é "sem alvo" (os 3 primeiros colocados da lista elegível: S1200|sem alvo, S1200|BE1R e S1000|sem alvo).

Duas observações sobre a escolha, fora do critério:
- A pontuação do critério (líquido) cresce com o stop; por lucro/DD, S700|sem alvo é melhor (B 5,36 contra 4,31; A 4,90 contra 2,23) e tem p ajustado igual (0,035). S700|sem alvo também é elegível (nona da lista) e é mudar um parâmetro da classe (`stop_pts=700`).
- Com 2 contratos a R$1.000, S1200 arrisca R$480 por stop (48% do capital inicial); o modo A escalona os contratos com o caixa (média 3,6; faixa 1–5).

```
{{TABELA}}
```

## 6. Holdout 2025-12-19..2026-02-19 — DESCRITIVO, JÁ GASTO (rodada 3)

Mesma grade, regra M1 conservadora, 38 pregões, 19 trades por célula. Não é validação e não entrou na escolha.

```
{{HOLD}}
```

- A forma não se repete: no holdout a coluna "sem alvo" é plana, R$2.733 a R$3.601 para os 10 stops (S300 R$3.181; S700 R$3.201; S1200 R$3.327; S1500 R$3.007), sem a subida com o stop da IS; as colunas "sem alvo", T1000, T1500, T2000, 1,5R, 2R, 3R, P50@1R e BE1R têm 10 de 10 stops positivos; as colunas T500 (9/10) e 1R (7/10) têm negativos (S500|T500 −R$239; S300, S400 e S500|1R −R$159, −R$199 e −R$239).
- O melhor alvo no holdout é BE1R (R$4.099 em S1200; R$2.915 em S700), a coluna "sem alvo" fica no meio (S1200 R$3.327).
- Com 19 trades por célula o holdout não tem poder para distinguir células vizinhas (rodada 3: efeito mínimo detectável R$337 por trade).

## 7. Classe, testes e cruzamento com o motor

- Classe: `src/strategy/daytrade/lab/win_gap_barra1.py::WinGapBarra1` (`name = "win_gap_barra1"`), defaults `stop_pts=1200`, sem alvo, `recuo_pts=0`, `ttl_barras=6`. Pura (OHLCV): o gap vem de barras (open da 1ª barra do dia = leilão; close da última barra do dia anterior = call). Não está em `registry.py` (teste `test_nao_esta_no_registry`).
- Testes `tests/test_win_gap_barra1.py`: 17 passando (sinal do gap, só opera com a barra 1 contra o gap, ordem a limite com prazo e alvo fatiado, sem look-ahead, dia sem call anterior / abertura atrasada, vencimento e filtro de rolagem, flatten às 18:10 (17:40 no regime antigo) e nunca na barra do call, fuso do feed, breakeven, call lido de `initialize`).
- **Suíte inteira** (`.\.venv\Scripts\python.exe -m pytest`, paralelo): **2.404 passaram, 1 pulado, 0 falhas** (64,6 s). O pulado é `test_live_broker_mt5.py` (pacote MetaTrader5 real instalado nesta máquina).

Cruzamento (`crosscheck4.py`, motor real, M5, R$1.000, `config_for`, `session_end_time=18:20`, celula S1200|sem alvo):

```
{{CROSS}}
```

- **(B)** classe no motor, barras sem leilão + gap externo (o do CSV) + flatten do motor: **63 trades, +R$17.446,50, idêntico trade a trade** (lado, contratos, entrada, saída, motivo, P&L) ao simulador em modo barra (a semântica do motor). A classe reproduz o simulador.
- **(A)** classe no motor, barras M5 BRUTAS (com leilão e call; gap calculado pela classe, igual ao gap do CSV de fases em 120/120 dias): 63 trades, +R$17.783,50, contra o simulador a tick 62 trades, +R$15.103,50 (modo A). Diferenças, explicadas:
  1. **Barra do fill:** o motor só avalia o stop da barra seguinte à do fill; o tick vê o stop dentro da barra do fill em 1 trade (2026-09-10: −R$272,50 no motor, −R$241,50 por contrato no tick).
  2. **Fonte da barra × tick:** em 2026-09-11 a máxima M5 (vinda de M1) toca o limite de venda (190.610) e o motor enche (+R$1.852,50, 5 contratos); nos ticks esse preço não é negociado depois das 09:05, sem fill. É a diferença de 5 pts entre as duas fontes (rodada 2, CHECAGEM_DADOS). Esse trade é ~R$1,85 mil dos R$2,68 mil de diferença.
  3. **Fim do dia:** a classe zera às 18:15 (abertura da barra das 18:15) para a saída não cair na barra do call; o simulador zera no último tick (18:24:59). Nos 62 trades comuns, soma da diferença por contrato −R$67.
  4. **Caixa:** os contratos seguem o caixa e o caixa diverge depois dos itens acima: 59 de 62 trades com a mesma quantidade.
  5. **Sinal:** o open da barra 1 em feed bruto é o preço do leilão; o simulador usa o 1º negócio contínuo. Muda o sinal em 1 dia de 120 (2026-05-20, que a classe opera e o simulador não).
- Descoberta de integração: o motor **não entrega a última barra do dia a `on_bar`** (o flatten roda antes e `on_bar` não roda depois dele), então o call de D−1 não chega pelo caminho normal; a classe lê o call do DataFrame em `initialize` (só datas anteriores a hoje) e cai no close da última barra vista quando não há tabela (ao vivo). Sem isso, no 1º cruzamento 4 dias saíram só no motor e 5 só no simulador (gaps pequenos).

## 8. EA

`EA_SPEC.md` (mesma pasta) e `EA_referencia_trades.csv` (trades esperados por pregão, 1 contrato, S1200 e S700, simulador a tick).
