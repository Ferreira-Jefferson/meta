# Larry Williams — relatório do motor de pesquisa (Python)

_Contrato: `ESPECIFICACAO.md` · decisões do motor: `DECISOES.md` · parâmetros finais: `params_recomendados.json` · trades de referência para o Testador do MT5: `ref_trades/` · universo de ações: `universo_acoes.csv`._

## Resposta curta (números primeiro)

**Nenhum setup se mostrou robusto.** São 42 pares (setup × classe de ativo) — 11 setups em ações, WIN, WDO e ETFs de bitcoin (TRES_BARRAS só em WIN/WDO). Placar do OOS, lido uma vez, na célula escolhida só no IS, a 1 tick de slippage:

| veredito | pares | quais |
|---|---|---|
| POSITIVA (IC95% do win% acima do breakeven, vale a 2 ticks) | **0** | — |
| POSITIVA FRACA (R$/op > 0 e win% > breakeven, mas o IC95% cruza o breakeven) | 6 | VB/WIN, SMASH/WIN, TDW/WIN, VB/WDO, OOPS/WDO, GSV/WDO |
| NÃO FUNCIONA (reprovada no IS, ou aprovada no IS e negativa no OOS) | 18 | ações: VB, OOPS, SMASH, OUTSIDE, GSV, UO, TDM, TDW · WIN: OOPS, GSV, TDM, TRES_BARRAS · WDO: SMASH, TDM, TDW, TRES_BARRAS · BTC: SMASH, TDW |
| SEM TRADES SUFICIENTES (< 60 trades no IS ou < 40 no OOS) | 8 | HSMASH, OUTSIDE, WR, UO em WIN e WDO |
| AMOSTRA INSUFICIENTE (só ~1 ano de M1 dos ETFs de bitcoin) | 8 | todos os setups no bitcoin que sobraram |
| INCONCLUSIVO (OOS com < 300 trades em ações) | 2 | HSMASH/ações (276), WR/ações (286) |

As 6 "positivas fracas" (OOS, 1 tick; entre colchetes o IC95% do win%):

| par | N OOS | win% [IC95%] | breakeven empírico | R$/op a 0 / 1 / 2 ticks |
|---|---|---|---|---|
| VB / WIN (k=0,3/0,3, stop 1,0×R1, REVERSAO, filtro SMA50) | 59 | 25,4% [16,1; 37,8] | 24,2% | 22,17 / 20,17 / 18,17 |
| SMASH / WIN (n=1, stop 1,0×R1, TEMPO 3d) | 47 | 46,8% [33,3; 60,8] | 43,9% | 25,48 / 23,48 / 21,48 |
| TDW / WIN (quinta, só compra, tendência swing, sem stop) | 57 | 50,9% [38,3; 63,4] | 50,4% | 4,99 / 2,99 / 0,99 |
| VB / WDO (k=0,3/0,3, só venda, BAILOUT 1d, sem stop) | 74 | 87,8% [78,5; 93,5] | 79,3% | 128,76 / 118,76 / 108,76 |
| OOPS / WDO (gap_min 0, BAILOUT, sem stop) | 47 | 85,1% [72,3; 92,6] | 82,7% | 50,78 / 40,78 / 30,78 |
| GSV / WDO (n=1, k=0,5/0,5, stop 1,0×R1, TEMPO 3d) | 58 | 44,8% [32,7; 57,5] | 37,1% | 105,41 / 95,41 / 85,41 |

**Como ler esses 6:** com 42 testes e N de OOS entre 47 e 74, meio punhado de resultados positivos é o que a sorte sozinha produz (um OOS aleatório sem edge é positivo ~50% das vezes). Em todos o IC95% do win% inclui o breakeven. Nenhum é recomendação; são candidatos a observar com mais dado. Em WIN/WDO os 6 saem de **um único ativo cada**, sem diversificação para checar robustez.

**Ações (40 ativos, OOS 2021→hoje, 276 a 5.841 trades por setup):** nenhuma célula escolhida no IS se sustentou. Exemplos: VB −0,216%/op (win 45,6% vs breakeven 48,0%, N 1.359); TDW −0,157%/op (46,8% vs 50,8%, N 5.841); GSV −0,385%/op (75,5% vs 82,4%); OOPS −0,325%/op (75,3% vs 79,4%); TDM −0,224%/op (47,8% vs 50,4%). O único OOS positivo nas ações foi o UO (+0,724%/op, 80,8% vs 72,2%, N 308) numa célula **reprovada no IS** (vizinhas 1/11): isolado, não é confiável.

**TRES_BARRAS** (o único setup 100% limite): WIN 2.095 trades no OOS, win 77,8% [76,0; 79,5] vs breakeven 78,8%, −R$2,29/op; WDO 2.090 trades, 73,5% vs 75,9%, −R$7,02/op. Sem modelo de fila calibrado (premissa de toque estrito), então o resultado real tende a ser **pior**.

**Capital mínimo real (R$250 WIN, R$375 WDO, ação = 2 lotes):** em quase toda célula o portão de caixa barra trades ou zera a conta — a leitura COM portão está marcada `CENSURADA(cx)` e `pulou*` nas tabelas. A seleção usa a leitura de edge (capital nocional); a pergunta "o dono sobrevive com 1 lote?" tem resposta quase sempre **não** para estas regras.

**A escolha irrestrita no IS favorece `sem stop`** (o IS premia o trade que nunca é cortado) — em 22 dos 42 pares a célula escolhida é sem stop. Por isso há uma segunda tabela por classe com a melhor célula **COM stop de proteção**; o placar dela é parecido (18 NÃO FUNCIONA, 5 positivas fracas, 0 positivas).

**Eixos mortos (item 6.25):** `OUTSIDE.modo` é morto por construção (limite em C(S) com filtro O<C(S) é executável na abertura = mercado); `HSMASH.close_contra` é morto no WIN (7–8 trades no total). Os demais eixos mexem no resultado (tabela ao final).

## O que falhou / limitações (para o dono)

- **Limite duro dos ETFs de bitcoin**: o repositório guarda ~100 mil barras M1 por veículo (≈ 1 ano). IS ≈ 150 pregões, OOS ≈ 100: dezenas de trades por setup. Conclusão possível: nenhuma. BTC-USD cru não foi usado, como pedido.
- **WR não gera sinal com o toque literal em 100 em série contínua** (0 sinais no WDO e 3 no WIN em 5 anos). Introduzi o parâmetro `toque` {100, 95} [INTERP]; a grade do WR foi rodada duas vezes (a 1ª sem `toque`, descartada).
- **Fila das ordens limite não é calibrada** (TRES_BARRAS e modos LIMITE): premissa de toque estrito (preço atravessa o nível). Pelas regras do repositório isso é "hipótese, não previsão".
- **Venda a descoberto em ação sem custo de aluguel**; futuro segurado overnight sem margem de carregamento (os WIN/WDO aqui seguram posições por dias em BAILOUT/TEMPO/REVERSAO).
- **Slippage aplicado depois da simulação dos níveis**, por ponta (entrada disparada, saídas a mercado): 0/1/2 ticks comparam o mesmo caminho de trades; é uma aproximação (o stop real executa com o slippage já no caminho).
- **Divergências motor × EA** (DECISOES.md vence): bailout `≥ entrada + 1 tick` vs `> entrada`; tendência por fechamento vs por high/low; WR (toque + espera + gatilho vs cruzamento em S); UO (pivôs no preço vs pivôs próprios; rompimento em qualquer barra da validade vs exatamente em S); TRES_BARRAS (alvo congelado no fill vs reposicionado a cada barra). O CSV de referência só bate com o log do EA nos setups em que essas regras coincidem (VB, OOPS, SMASH, HSMASH, OUTSIDE, GSV, TDM, TDW sem tendência).
- **2 testes da suíte inteira falham fora do meu código**: `tests/test_run_live_cli.py::test_cmd_loop_valueerror_de_conta_broker_divergente_e_fatal` e `::test_cmd_loop_outros_erros_continuam_com_retry` (falham também isolados; o terminal MT5 está aberto nesta máquina — "terminal já aberto com AutoTrading desligado"). Os 42 testes de `tests/test_larry_williams.py` passam; suíte completa: 2357 passed, 2 failed, 1 skipped.

_Contrato: `ESPECIFICACAO.md`. Decisões: `DECISOES.md`. Parâmetros finais: `params_recomendados.json`._

## Como ler (números primeiro)

- **Edge** = capital nocional, todos os trades entram (a pergunta é "a regra tem vantagem?"). As colunas marcadas com `*` (`cap.final*`, `pulou*`) são a leitura **COM portão de caixa no capital mínimo real** (ação: preço×lote×2; WIN R$250; WDO R$375): mede se o dono sobreviveria operando 1 lote/contrato. **CENSURADA(cx)** = o portão barrou trades, o caixa zerou ou houve < 20 trades.

- **Sempre** win% ao lado do **breakeven empírico** `perda_média/(ganho_média+perda_média)` e do N. `R$/op > 0` e `win% > BE` são a mesma afirmação.

- **Slippage por entrada disparada**: escolha e tabela a **1 tick**; sensibilidade 0/1/2 ticks ao lado.

- Escolha da célula **só no IS**, por **mediana entre ativos** (ações/ETF) ou entre **semestres do IS** (WIN/WDO), com mínimo de trades, `share>0 ≥ 50%` e **vizinhança** (≥ 50% das vizinhas a um eixo de distância positivas). O OOS foi aberto **uma vez** por (setup, classe), na célula escolhida.

- **Aviso de múltiplos testes**: cada célula escolhida saiu de uma grade de centenas a milhares de células; o OOS é a única leitura honesta. Trades de ativos diferentes no mesmo dia são correlacionados — o IC do win% agregado entre ações é otimista.

## Ativos que entraram e que saíram

**Ações/ETF B3 (data/raw, 157 arquivos): 40 entraram, 117 saíram.** Corte: mediana do giro financeiro diário (close×volume) ≥ R$ 20 mi tanto no histórico inteiro quanto nos últimos 250 pregões; ≥ 750 barras no IS (2010–2020) e ≥ 500 no OOS (2021–hoje); ≤ 5% de dias sem volume; nenhum salto diário > 50% (suspeita de desdobramento não ajustado). BOVA11 incluído a pedido (lote 1).

Entraram: ABEV3, BBAS3, BBDC3, BBDC4, BBSE3, BOVA11, BPAC11, BRAP4, BRKM5, CMIG4, CPFE3, CSAN3, CSNA3, CYRE3, ECOR3, EGIE3, EQTL3, FLRY3, GGBR4, GOAU4, HYPE3, IRBR3, ITSA4, ITUB4, KLBN11, LREN3, MRVE3, MULT3, PETR3, PETR4, PSSA3, RADL3, RENT3, SANB11, SBSP3, TIMS3, TOTS3, USIM5, VALE3, WEGE3.

Saíram (motivo principal; lista completa com todos os motivos em `universo_acoes.csv`):

- **giro < corte** (92): AALR3, ABCB4, AFLT3, ALPA3, ALPA4, ALUP11, BAZA3, BDLL4, BEES3, BEES4, BGIP4, BLAU3, BMEB3, BMEB4, BMGB4, BOBR4, BRAP3, BRKM3, BRSR6, CGAS3, CGAS5, CGRA4, CLSC4, CMIG3, COCE5, CPLE3, CSMG3, DASA3, EALT4, ELPL4, EMAE4, ENEV3, ENGI4, ETER3, EUCA4, EVEN3, EZTC3, FESA3, FESA4, FRAS3, GEPA4, GFSA3, GGBR3, GOAU3, GOLD11, GRND3, IMAB11, INEP4, ITSA3, ITUB3, JHSF3, KEPL3, KLBN3, KLBN4, LEVE3, LIGT3, LOGN3, LPSB3, MATD3, MDIA3, MNDL3, MSPA4, MTSA4, MWET4, MYPK3, OIBR3, OIBR4, PINE4, PNVL3, POMO3, POMO4, POSI3, RAPT3, RAPT4, ROMI3, RSID3, RSUL4, SANB4, SAPR4, SHUL4, SMTO3, TASA4, TCSA3, TELB4, TGMA3, TRIS3, TUPY3, UNIP6, USIM3, USIM6, VIVT3, WHRL4
- **barras insuficientes (IS/OOS)** (6): CMIN3, CXSE3, FIBR3, HAPV3, RDOR3, SAPR11
- **dias sem volume** (5): ENGI11, PCAR3, SUZB3, TAEE11, UGPA3

**WIN e WDO**: `WIN@D`/`WDO@D` M1 (ajuste por diferença), 2021-10 → 2026-10; pregão regular 09:00–17:54 (corte único porque o CSV tem barras até 18:24–18:29 em parte dos pregões; ver DECISOES.md); pregões com < 300 barras descartados. IS 2021-10→2024-06, OOS 2024-07→hoje.

**Bitcoin (somente veículos listados na B3, M1 → diário em horário de Brasília, critério de `cripto_comum.py`: ≥ 96 barras M1/pregão e giro mediano > R$ 1 mi/dia)**:

- BITH11: ENTROU — 251 pregões (2025-08-27→2026-08-27), mediana 400 barras/pregão, giro mediano R$ 11.8 mi.
- BTCI11: ENTROU — 232 pregões (2025-09-23→2026-08-27), mediana 413 barras/pregão, giro mediano R$ 2.2 mi.
- QBTC11: ENTROU — 314 pregões (2025-05-28→2026-08-27), mediana 315 barras/pregão, giro mediano R$ 5.2 mi.

_Limite duro_: o repositório guarda só ~100.000 barras M1 por ETF (≈ 1 ano). IS = primeiros 60% dos pregões, OOS = 40% finais: **amostra de poucas dezenas de trades por setup — qualquer veredito de bitcoin é INCONCLUSIVO.** BTC-USD cru não foi usado.


## Ações B3 (diário)

Linha IS = a escolhida; linha OOS = leitura única. `liquido`/`MaxDD`/`trades` = mediana entre ativos; pregões = 2674 (IS) / 1403 (OOS). Slippage 1 tick.

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes    BE emp%    N total cap.final*     pulou*
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
VB ACAO IS                            —       734,40        —      807,05     0,91  54,5%     62       0,27     0,0              —    2674       45,3       2499      3.077          0
VB ACAO OOS                           —      -464,40        —    1.372,77    -0,34  45,6%     34      -0,33     0,0              —    1403       48,0       1359      4.553          0
OOPS ACAO IS                          —       128,58        —      196,62     0,65  82,3%     22       0,05     0,0              —    2674       76,8        869      2.588          1  CENSURADA(cx)
OOPS ACAO OOS                         —       -33,88        —      213,05    -0,16  75,3%     10      -0,02     0,0              —    1403       79,4        381      4.722          0  CENSURADA(cx)
SMASH ACAO IS                         —       -36,32        —      208,34    -0,17  31,2%     13      -0,01     0,0              —    2674       33,1        532      2.242          1  CENSURADA(cx)
SMASH ACAO OOS                        —      -123,72        —      264,39    -0,47  24,8%      8      -0,09     0,0              —    1403       35,5        331      4.657          0  CENSURADA(cx)
HSMASH ACAO IS                        —      -152,96        —      205,57    -0,74  39,2%     14      -0,06     0,0              —    2674       59,6        558      2.155          0  CENSURADA(cx)
HSMASH ACAO OOS                       —       -99,55        —      150,75    -0,66  36,6%      7      -0,07     0,0              —    1403       59,2        276      4.661          0  CENSURADA(cx)
OUTSIDE ACAO IS                       —       170,94        —      103,68     1,65  84,6%     18       0,06     0,0              —    2674       78,6        720      2.422          1  CENSURADA(cx)
OUTSIDE ACAO OOS                      —        51,16        —       43,93     1,16  79,8%      8       0,04     0,0              —    1403       84,6        322      4.819          0  CENSURADA(cx)
GSV ACAO IS                           —       137,19        —      184,39     0,74  80,4%     26       0,05     0,0              —    2674       74,0       1033      2.446          1  CENSURADA(cx)
GSV ACAO OOS                          —       -92,37        —      290,80    -0,32  75,5%     13      -0,07     0,0              —    1403       82,4        523      4.617          0  CENSURADA(cx)
WR ACAO IS                            —        93,30        —      104,20     0,90  82,5%     13       0,03     0,0              —    2674       79,3        509      2.390          0  CENSURADA(cx)
WR ACAO OOS                           —         6,44        —      105,77     0,06  80,1%      7       0,00     0,0              —    1403       84,4        286      4.795          0  CENSURADA(cx)
UO ACAO IS                            —       -27,18        —      218,60    -0,12  76,3%     14      -0,01     0,0              —    2674       79,1        578      2.431          1  CENSURADA(cx)
UO ACAO OOS                           —        78,40        —        4,52    17,35  80,8%      8       0,06     0,0              —    1403       72,2        308      4.795          0  CENSURADA(cx)
TDM ACAO IS                           —       263,25        —      210,86     1,25  56,6%     30       0,10     0,0              —    2674       43,2       1194      2.629          0
TDM ACAO OOS                          —       -66,16        —      287,91    -0,23  47,8%     14      -0,05     0,0              —    1403       50,4        554      4.610          0  CENSURADA(cx)
TDW ACAO IS                           —      -337,34        —      698,55    -0,48  45,9%    223      -0,13     0,1              —    2674       51,0       8927      1.895         36  CENSURADA(cx)
TDW ACAO OOS                          —      -350,02        —      639,13    -0,55  46,8%    146      -0,25     0,1              —    1403       50,8       5841      4.257          0
```

| setup | célula escolhida no IS (params; saída; stop; lados; filtros) | status IS | IS: score mediana | vizinhas + | OOS 0/1/2 ticks (exp% mediana) | OOS win% [IC95%] vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|---|
| VB | k=(1,0; 1,0), sem stop, saida=REVERSAO, lados=C, tend=SWING, filtro dia: sem_sex | APROVADA_NO_IS (261/3240 células passam) | 1,411 | 13/18 | -0,171% / -0,216% / -0,271% | 45,6% [43,0; 48,3] vs 48,0% | 1359 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| OOPS | gap_min=0,25, sem stop, saida=BAILOUT(0d), lados=C, tend=SWING, filtro dia: sem_sex | APROVADA_NO_IS (86/1944 células passam) | 0,571 | 11/16 | -0,219% / -0,325% / -0,431% | 75,3% [70,8; 79,4] vs 79,4% | 381 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| SMASH | n=5, excl_out=False, stop=1,0xR1, saida=RR(2,0R), lados=CV, tend=SWING, filtro dia: sem_ter | REPROVADA_NO_IS (0/4133 células passam) | -0,053 | 0/15 | -0,984% / -1,082% / -1,152% | 24,8% [20,4; 29,7] vs 35,5% | 331 | NAO FUNCIONA: reprovada nos criterios do IS |
| HSMASH | zona=0,25, close_contra=True, stop=extremo de S, saida=BAILOUT(0d), lados=C, filtro dia: sem_sex | REPROVADA_NO_IS (0/610 células passam) | -0,498 | 0/10 | -0,669% / -0,738% / -0,808% | 36,6% [31,1; 42,4] vs 59,2% | 276 | INCONCLUSIVO: OOS com 276 trades (< 300) -> CENSURADA |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, sem stop, saida=BAILOUT(0d), lados=CV, tend=SWING, filtro dia: sem_qui | APROVADA_NO_IS (234/432 células passam) | 0,832 | 10/12 | 0,508% / 0,300% / 0,174% | 79,8% [75,1; 83,8] vs 84,6% | 322 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| GSV | n=4, k=(0,8; 1,2), sem stop, saida=BAILOUT(0d), lados=C, tend=SWING, filtro dia: sem_qua | APROVADA_NO_IS (232/3714 células passam) | 0,556 | 13/16 | -0,268% / -0,385% / -0,420% | 75,5% [71,7; 79,0] vs 82,4% | 523 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| WR | n=14, espera=5, gatilho=85,0, toque=95,0, modo=A_MERCADO_NA_ABERTURA, sem stop, saida=BAILOUT(0d), lados=C, tend=SWING, filtro dia: sem_qui | APROVADA_NO_IS (5/4535 células passam) | 0,861 | 5/10 | 0,312% / 0,269% / 0,165% | 80,1% [75,1; 84,3] vs 84,4% | 286 | INCONCLUSIVO: OOS com 286 trades (< 300) -> CENSURADA |
| UO | compra_max=35,0, venda_min=70,0, validade=10, modo=A_MERCADO_NA_ABERTURA, sem stop, saida=BAILOUT(0d), lados=CV, filtro dia: sem_ter | REPROVADA_NO_IS (0/625 células passam) | 0,092 | 1/11 | 0,765% / 0,724% / 0,574% | 80,8% [76,1; 84,8] vs 72,2% | 308 | NAO FUNCIONA: reprovada nos criterios do IS (OOS isolado positivo, mas a celula nao passou no IS: nao confiavel, so' investigar) |
| TDM | dias=(1), meses=(1; 2; 10), sem stop, saida=TEMPO(3d), lados=C, tend=SMA50, filtro dia: sem_seg | APROVADA_NO_IS (394/2268 células passam) | 0,748 | 15/18 | -0,099% / -0,224% / -0,353% | 47,8% [43,7; 52,0] vs 50,4% | 554 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| TDW | dia=0, sem stop, saida=FECHAMENTO, lados=V, tend=SMA50 | REPROVADA_NO_IS (0/135 células passam) | -0,154 | 0/10 | -0,034% / -0,157% / -0,255% | 46,8% [45,5; 48,1] vs 50,8% | 5841 | NAO FUNCIONA: reprovada nos criterios do IS |

**Ações B3 (diário) — melhor célula COM stop de proteção** (a escolha irrestrita acima tende a `sem stop`, risco aberto; aqui o stop é obrigatório. Mesmo critério de escolha no IS, OOS lido uma vez):

| setup | célula (com stop) | status IS | vizinhas + | OOS exp 1 tick | OOS win% vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|
| VB | k=(0,3; 0,3), stop=1,0xR1, saida=REVERSAO, lados=C, tend=SMA50, filtro dia: sem_qua | REPROVADA_NO_IS | 6/18 | -0,414% | 21,1% vs 24,5% | 2888 | NAO FUNCIONA: reprovada nos criterios do IS |
| OOPS | gap_min=0,0, stop=1,0xR1, saida=BAILOUT(0d), lados=C, tend=SMA50, filtro dia: sem_ter | REPROVADA_NO_IS | 1/16 | -0,371% | 53,2% vs 62,4% | 1328 | NAO FUNCIONA: reprovada nos criterios do IS |
| SMASH | n=5, excl_out=False, stop=1,0xR1, saida=RR(2,0R), lados=CV, tend=SWING, filtro dia: sem_ter | REPROVADA_NO_IS | 0/15 | -1,082% | 24,8% vs 35,5% | 331 | NAO FUNCIONA: reprovada nos criterios do IS |
| HSMASH | zona=0,25, close_contra=True, stop=extremo de S, saida=BAILOUT(0d), lados=C, filtro dia: sem_sex | REPROVADA_NO_IS | 0/10 | -0,738% | 36,6% vs 59,2% | 276 | INCONCLUSIVO: OOS com 276 trades (< 300) -> CENSURADA |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, stop=1,0xR1, saida=BAILOUT(0d), lados=CV, tend=SMA50, filtro dia: sem_ter | APROVADA_NO_IS | 10/12 | -0,283% | 63,7% vs 69,9% | 292 | INCONCLUSIVO: OOS com 292 trades (< 300) -> CENSURADA |
| GSV | n=2, k=(0,5; 0,5), stop=1,0xR1, saida=TEMPO(3d), lados=C, tend=SMA50, filtro dia: sem_seg | REPROVADA_NO_IS | 1/17 | -1,158% | 21,1% vs 43,3% | 1694 | NAO FUNCIONA: reprovada nos criterios do IS |
| WR | n=10, espera=5, gatilho=95,0, toque=100,0, modo=A_MERCADO_NA_ABERTURA, stop=1,0xR1, saida=OSC, lados=CV, tend=SMA50, filtro dia: sem_qua | REPROVADA_NO_IS | 1/7 | -0,222% | 33,9% vs 35,5% | 115 | INCONCLUSIVO: OOS com 115 trades (< 300) -> CENSURADA |
| UO | compra_max=30,0, venda_min=50,0, validade=10, modo=A_MERCADO_NA_ABERTURA, stop=1,0xR1, saida=BAILOUT(0d), lados=CV, tend=SMA50 | REPROVADA_NO_IS | 0/8 | -0,190% | 62,5% vs 65,1% | 275 | INCONCLUSIVO: OOS com 275 trades (< 300) -> CENSURADA |
| TDM | dias=(1), meses=(1; 2; 10), stop=1,0xR1, saida=TEMPO(3d), lados=C, tend=SMA50, filtro dia: sem_seg | APROVADA_NO_IS | 14/18 | -0,282% | 39,5% vs 43,5% | 554 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| TDW | dia=4, stop=1,0xR1, saida=FECHAMENTO, lados=V, tend=SMA50 | REPROVADA_NO_IS | 0/10 | -0,113% | 47,5% vs 51,5% | 5662 | NAO FUNCIONA: reprovada nos criterios do IS |


## WIN (mini-índice, M1)

Linha IS = a escolhida; linha OOS = leitura única. `liquido`/`MaxDD`/`trades` = do ativo; pregões = 680 (IS) / 563 (OOS). Slippage 1 tick.

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes    BE emp%    N total cap.final*     pulou*
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
VB WIN IS                             —     3.101,40        —    4.177,50     0,74  28,1%     64       4,56     0,1              —     680       24,7         64         85         56  CENSURADA(cx)
VB WIN OOS                            —     1.190,30        —    6.687,00     0,18  25,4%     59       2,11     0,1              —     563       24,2         59        -36         58  CENSURADA(cx)
OOPS WIN IS                           —     1.848,00        —    7.240,00     0,26  87,1%     70       2,72     0,1              —     680       85,4         70       -154         67  CENSURADA(cx)
OOPS WIN OOS                          —    -4.984,50        —    8.157,00    -0,61  83,7%     49      -8,85     0,1              —     563       89,1         49     -1.150         46  CENSURADA(cx)
SMASH WIN IS                          —     4.655,00        —    2.012,00     2,31  45,0%     60       6,85     0,1              —     680       36,4         60       -118         59  CENSURADA(cx)
SMASH WIN OOS                         —     1.103,50        —    3.253,50     0,34  46,8%     47       1,96     0,1              —     563       43,9         47          2         41  CENSURADA(cx)
HSMASH WIN IS                         —      -430,00        —      834,50    -0,52  62,5%      8      -0,63     0,0              —     680       77,5          8       -152          3  CENSURADA(cx)
HSMASH WIN OOS                        —       498,50        —      420,50     1,19  71,4%      7       0,89     0,0              —     563       54,7          7         49          5  CENSURADA(cx)
OUTSIDE WIN IS                        —       764,00        —      962,50     0,79  64,7%     17       1,12     0,0              —     680       56,0         17      1.014          0  CENSURADA(cx)
OUTSIDE WIN OOS                       —     2.141,50        —      491,50     4,36  72,7%     11       3,80     0,0              —     563       33,2         11      2.392          0  CENSURADA(cx)
GSV WIN IS                            —     5.707,50        —    2.046,50     2,79  95,9%     74       8,39     0,1              —     680       91,5         74      5.958          0
GSV WIN OOS                           —    -9.313,00        —   13.851,50    -0,67  85,0%     60     -16,54     0,1              —     563       91,9         60     -3.520         14  CENSURADA(cx)
WR WIN IS                             —       326,50        —    1.794,50     0,18  48,9%     45       0,48     0,1              —     680       47,1         45         84         44  CENSURADA(cx)
WR WIN OOS                            —     1.925,50        —    1.437,00     1,34  54,5%     33       3,42     0,1              —     563       44,2         33         68         25  CENSURADA(cx)
UO WIN IS                             —     3.706,00        —      735,50     5,04  33,3%     12       5,45     0,0              —     680       12,1         12         94         11  CENSURADA(cx)
UO WIN OOS                            —    -2.469,00        —    3.396,00    -0,73   5,6%     18      -4,39     0,0              —     563       15,2         18         39         17  CENSURADA(cx)
TDM WIN IS                            —        97,00        —    2.054,00     0,05  51,4%     72       0,14     0,1              —     680       51,0         72         76         69  CENSURADA(cx)
TDM WIN OOS                           —     3.240,50        —    1.483,50     2,18  55,6%     63       5,76     0,1              —     563       44,4         63      3.490          0
TDW WIN IS                            —     1.113,50        —    2.301,50     0,48  56,7%     67       1,64     0,1              —     680       52,3         67      1.364          0
TDW WIN OOS                           —       170,50        —    2.888,00     0,06  50,9%     57       0,30     0,1              —     563       50,4         57         88         53  CENSURADA(cx)
TRES_BARRAS WIN IS                    —      -295,00        —    6.993,50    -0,04  80,7%   2626      -0,43     3,9              —     680       80,7       2626        -62      2.390  CENSURADA(cx)
TRES_BARRAS WIN OOS                   —    -4.798,50        —    8.958,00    -0,54  77,8%   2095      -8,52     3,7              —     563       78,8       2095         92      2.090  CENSURADA(cx)
```

| setup | célula escolhida no IS (params; saída; stop; lados; filtros) | status IS | IS: score mediana | vizinhas + | OOS 0/1/2 ticks (R$/op) | OOS win% [IC95%] vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|---|
| VB | k=(0,3; 0,3), stop=1,0xR1, saida=REVERSAO, lados=CV, tend=SMA50, filtro dia: sem_qua | APROVADA_NO_IS (1071/2173 células passam) | 146,855 | 17/18 | 22,17 / 20,17 / 18,17 | 25,4% [16,1; 37,8] vs 24,2% | 59 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| OOPS | gap_min=0,0, sem stop, saida=BAILOUT(0d), lados=CV, filtro dia: sem_sex | APROVADA_NO_IS (128/148 células passam) | 112,627 | 15/16 | -99,72 / -101,72 / -103,72 | 83,7% [71,0; 91,5] vs 89,1% | 49 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| SMASH | n=1, excl_out=False, stop=1,0xR1, saida=TEMPO(3d), lados=CV, filtro dia: sem_ter | APROVADA_NO_IS (47/107 células passam) | 103,273 | 15/18 | 25,48 / 23,48 / 21,48 | 46,8% [33,3; 60,8] vs 43,9% | 47 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| HSMASH | zona=0,25, close_contra=False, stop=extremo de S, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | nan | 0/0 | 73,21 / 71,21 / 69,21 | 71,4% [35,9; 91,8] vs 54,7% | 7 | SEM TRADES SUFICIENTES (inconclusivo) |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | -7,562 | 4/8 | 196,68 / 194,68 / 192,68 | 72,7% [43,4; 90,3] vs 33,2% | 11 | SEM TRADES SUFICIENTES (inconclusivo) |
| GSV | n=1, k=(0,5; 0,5), sem stop, saida=BAILOUT(0d), lados=CV, filtro dia: sem_qua | APROVADA_NO_IS (118/207 células passam) | 105,396 | 13/16 | -153,22 / -155,22 / -157,22 | 85,0% [73,9; 91,9] vs 91,9% | 60 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| WR | n=10, espera=5, gatilho=95,0, toque=95,0, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | 1,792 | 11/16 | 60,35 / 58,35 / 56,35 | 54,5% [38,0; 70,2] vs 44,2% | 33 | SEM TRADES SUFICIENTES (inconclusivo) |
| UO | compra_max=35,0, venda_min=50,0, validade=10, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=OSC, lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | nan | 0/0 | -135,17 / -137,17 / -139,17 | 5,6% [1,0; 25,8] vs 15,2% | 18 | SEM TRADES SUFICIENTES (inconclusivo) |
| TDM | dias=(1; 2; 3), meses=(1; 2; 10), sem stop, saida=FECHAMENTO, lados=C | REPROVADA_NO_IS (0/38 células passam) | -4,167 | 9/18 | 53,44 / 51,44 / 49,44 | 55,6% [43,3; 67,2] vs 44,4% | 63 | NAO FUNCIONA: reprovada nos criterios do IS (OOS isolado positivo, mas a celula nao passou no IS: nao confiavel, so' investigar) |
| TDW | dia=3, sem stop, saida=FECHAMENTO, lados=C, tend=SWING | APROVADA_NO_IS (60/120 células passam) | 69,031 | 7/10 | 4,99 / 2,99 / 0,99 | 50,9% [38,3; 63,4] vs 50,4% | 57 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| TRES_BARRAS | tf=5, stop=2,0xR1, tend=SMA50 | APROVADA_NO_IS (3/12 células passam) | 0,884 | 2/4 | -1,94 / -2,29 / -2,64 | 77,8% [76,0; 79,5] vs 78,8% | 2095 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |

**WIN (mini-índice, M1) — melhor célula COM stop de proteção** (a escolha irrestrita acima tende a `sem stop`, risco aberto; aqui o stop é obrigatório. Mesmo critério de escolha no IS, OOS lido uma vez):

| setup | célula (com stop) | status IS | vizinhas + | OOS exp 1 tick | OOS win% vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|
| VB | k=(0,3; 0,3), stop=1,0xR1, saida=REVERSAO, lados=CV, tend=SMA50, filtro dia: sem_qua | APROVADA_NO_IS | 17/18 | R$ 20,17 | 25,4% vs 24,2% | 59 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| OOPS | gap_min=0,1, stop=0,5xR1, saida=ABERTURA_SEGUINTE, lados=CV, filtro dia: sem_qua | APROVADA_NO_IS | 16/16 | R$ 4,47 | 43,6% vs 42,4% | 39 | INCONCLUSIVO: OOS com 39 trades (< 40) -> CENSURADA |
| SMASH | n=1, excl_out=False, stop=1,0xR1, saida=TEMPO(3d), lados=CV, filtro dia: sem_ter | APROVADA_NO_IS | 15/18 | R$ 23,48 | 46,8% vs 43,9% | 47 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| HSMASH | zona=0,25, close_contra=False, stop=extremo de S, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 0/0 | R$ 71,21 | 71,4% vs 54,7% | 7 | SEM TRADES SUFICIENTES (inconclusivo) |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 4/8 | R$ 194,68 | 72,7% vs 33,2% | 11 | SEM TRADES SUFICIENTES (inconclusivo) |
| GSV | n=2, k=(0,5; 0,5), stop=1,0xR1, saida=TEMPO(3d), lados=CV | APROVADA_NO_IS | 14/16 | R$ -56,83 | 37,6% vs 44,5% | 85 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| WR | n=10, espera=5, gatilho=95,0, toque=95,0, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 11/16 | R$ 58,35 | 54,5% vs 44,2% | 33 | SEM TRADES SUFICIENTES (inconclusivo) |
| UO | compra_max=35,0, venda_min=50,0, validade=10, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=OSC, lados=CV | SEM_DADOS_SUFICIENTES | 0/0 | R$ -137,17 | 5,6% vs 15,2% | 18 | SEM TRADES SUFICIENTES (inconclusivo) |
| TDM | dias=(1; 2; 3), meses=(), stop=1,0xR1, saida=BAILOUT(0d), lados=C, filtro dia: sem_ter | REPROVADA_NO_IS | 6/18 | R$ 9,48 | 66,7% vs 65,2% | 51 | NAO FUNCIONA: reprovada nos criterios do IS (OOS isolado positivo, mas a celula nao passou no IS: nao confiavel, so' investigar) |
| TDW | dia=1, stop=1,0xR1, saida=FECHAMENTO, lados=V, tend=SWING | APROVADA_NO_IS | 7/10 | R$ -60,50 | 31,4% vs 45,2% | 51 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| TRES_BARRAS | tf=5, stop=2,0xR1, tend=SMA50 | APROVADA_NO_IS | 2/4 | R$ -2,29 | 77,8% vs 78,8% | 2095 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |


## WDO (mini-dólar, M1)

Linha IS = a escolhida; linha OOS = leitura única. `liquido`/`MaxDD`/`trades` = do ativo; pregões = 682 (IS) / 560 (OOS). Slippage 1 tick.

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes    BE emp%    N total cap.final*     pulou*
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
VB WDO IS                             —    15.325,00        —    3.283,00     4,67  93,0%     86      22,47     0,1              —     682       84,2         86     15.700          0
VB WDO OOS                            —     8.788,00        —    4.026,50     2,18  87,8%     74      15,69     0,1              —     560       79,3         74     -2.290         66  CENSURADA(cx)
OOPS WDO IS                           —    13.739,50        —    4.725,50     2,91  93,4%     61      20,15     0,1              —     682       81,0         61     -3.084         53  CENSURADA(cx)
OOPS WDO OOS                          —     1.916,50        —    6.250,00     0,31  85,1%     47       3,42     0,1              —     560       82,7         47     -2.053         31  CENSURADA(cx)
SMASH WDO IS                          —     6.192,50        —    3.636,00     1,70  41,7%     60       9,08     0,1              —     682       31,8         60         54         59  CENSURADA(cx)
SMASH WDO OOS                         —    -4.335,50        —    4.953,00    -0,88  23,9%     46      -7,74     0,1              —     560       34,9         46        120         45  CENSURADA(cx)
HSMASH WDO IS                         —      -218,00        —      605,50    -0,36  50,0%      6      -0,32     0,0              —     682       55,9          6       -230          5  CENSURADA(cx)
HSMASH WDO OOS                        —      -272,50        —      560,50    -0,49  60,0%      5      -0,49     0,0              —     560       66,8          5       -186          4  CENSURADA(cx)
OUTSIDE WDO IS                        —     1.661,50        —      681,00     2,44  58,3%     12       2,44     0,0              —     682       44,4         12       -216         11  CENSURADA(cx)
OUTSIDE WDO OOS                       —     1.598,00        —    1.507,00     1,06  64,3%     14       2,85     0,0              —     560       50,4         14        -36         12  CENSURADA(cx)
GSV WDO IS                            —    14.920,00        —    1.779,00     8,39  64,6%     65      21,88     0,1              —     682       44,5         65     15.295          0
GSV WDO OOS                           —     5.533,50        —    4.246,00     1,30  44,8%     58       9,88     0,1              —     560       37,1         58      5.908          0
WR WDO IS                             —    -1.054,00        —    2.665,50    -0,40  39,4%     33      -1,55     0,0              —     682       43,5         33       -188         32  CENSURADA(cx)
WR WDO OOS                            —    -1.849,00        —    3.313,00    -0,56  39,5%     38      -3,30     0,1              —     560       47,0         38        -78         27  CENSURADA(cx)
UO WDO IS                             —       -80,00        —    1.745,00    -0,05  44,0%     25      -0,12     0,0              —     682       44,5         25       -132         16  CENSURADA(cx)
UO WDO OOS                            —     1.422,00        —      440,50     3,23  72,7%     11       2,54     0,0              —     560       48,3         11      1.797          0  CENSURADA(cx)
TDM WDO IS                            —    10.314,50        —    7.063,00     1,46  91,8%     61      15,12     0,1              —     682       84,8         61     10.690          0
TDM WDO OOS                           —   -13.606,00        —   16.405,00    -0,83  71,4%     42     -24,30     0,1              —     560       86,6         42       -542         37  CENSURADA(cx)
TDW WDO IS                            —     4.224,00        —    2.068,50     2,04  54,2%     72       6,19     0,1              —     682       44,2         72       -200         71  CENSURADA(cx)
TDW WDO OOS                           —    -5.385,00        —    5.385,00    -1,00  42,5%     80      -9,62     0,1              —     560       55,4         80        130         79  CENSURADA(cx)
TRES_BARRAS WDO IS                    —   -12.506,50        —   16.488,00    -0,76  75,7%   2553     -18,34     3,7              —     682       77,1       2553          8      2.500  CENSURADA(cx)
TRES_BARRAS WDO OOS                   —   -14.670,00        —   15.877,50    -0,92  73,5%   2090     -26,20     3,7              —     560       75,9       2090        128      2.075  CENSURADA(cx)
```

| setup | célula escolhida no IS (params; saída; stop; lados; filtros) | status IS | IS: score mediana | vizinhas + | OOS 0/1/2 ticks (R$/op) | OOS win% [IC95%] vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|---|
| VB | k=(0,3; 0,3), sem stop, saida=BAILOUT(1d), lados=V, tend=SWING, filtro dia: sem_qui | APROVADA_NO_IS (310/2140 células passam) | 219,250 | 14/17 | 128,76 / 118,76 / 108,76 | 87,8% [78,5; 93,5] vs 79,3% | 74 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| OOPS | gap_min=0,0, sem stop, saida=BAILOUT(0d), lados=CV, filtro dia: sem_qui | APROVADA_NO_IS (13/64 células passam) | 185,583 | 13/16 | 50,78 / 40,78 / 30,78 | 85,1% [72,3; 92,6] vs 82,7% | 47 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| SMASH | n=1, excl_out=True, stop=0,5xR1, saida=RR(2,0R), lados=CV, filtro dia: sem_qua | APROVADA_NO_IS (67/73 células passam) | 167,052 | 16/18 | -85,45 / -94,25 / -103,05 | 23,9% [13,9; 37,9] vs 34,9% | 46 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| HSMASH | zona=0,25, close_contra=False, stop=extremo de S, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | nan | 0/0 | -44,50 / -54,50 / -64,50 | 60,0% [23,1; 88,2] vs 66,8% | 5 | SEM TRADES SUFICIENTES (inconclusivo) |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | nan | 0/0 | 124,14 / 114,14 / 104,14 | 64,3% [38,8; 83,7] vs 50,4% | 14 | SEM TRADES SUFICIENTES (inconclusivo) |
| GSV | n=1, k=(0,5; 0,5), stop=1,0xR1, saida=TEMPO(3d), lados=CV, filtro dia: sem_sex | APROVADA_NO_IS (92/155 células passam) | 188,562 | 14/16 | 105,41 / 95,41 / 85,41 | 44,8% [32,7; 57,5] vs 37,1% | 58 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| WR | n=10, espera=5, gatilho=95,0, toque=95,0, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | -137,000 | 2/13 | -38,66 / -48,66 / -58,66 | 39,5% [25,6; 55,3] vs 47,0% | 38 | SEM TRADES SUFICIENTES (inconclusivo) |
| UO | compra_max=35,0, venda_min=50,0, validade=10, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | 23,250 | 9/12 | 139,27 / 129,27 / 119,27 | 72,7% [43,4; 90,3] vs 48,3% | 11 | SEM TRADES SUFICIENTES (inconclusivo) |
| TDM | dias=(1; 2; 3), meses=(), sem stop, saida=BAILOUT(0d), lados=C, filtro dia: sem_sex | APROVADA_NO_IS (35/44 células passam) | 229,667 | 17/18 | -313,95 / -323,95 / -333,95 | 71,4% [56,4; 82,8] vs 86,6% | 42 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| TDW | dia=2, sem stop, saida=FECHAMENTO, lados=V, tend=SMA50 | APROVADA_NO_IS (33/120 células passam) | 84,115 | 6/10 | -57,31 / -67,31 / -77,31 | 42,5% [32,3; 53,4] vs 55,4% | 80 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| TRES_BARRAS | tf=5, stop=1,0xR1, tend=SWING | REPROVADA_NO_IS (0/12 células passam) | -5,561 | 0/4 | -4,32 / -7,02 / -9,72 | 73,5% [71,6; 75,4] vs 75,9% | 2090 | NAO FUNCIONA: reprovada nos criterios do IS |

**WDO (mini-dólar, M1) — melhor célula COM stop de proteção** (a escolha irrestrita acima tende a `sem stop`, risco aberto; aqui o stop é obrigatório. Mesmo critério de escolha no IS, OOS lido uma vez):

| setup | célula (com stop) | status IS | vizinhas + | OOS exp 1 tick | OOS win% vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|
| VB | k=(0,3; 0,3), stop=1,0xR1, saida=REVERSAO, lados=V, filtro dia: sem_ter | APROVADA_NO_IS | 9/17 | R$ 188,58 | 32,7% vs 24,9% | 52 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| OOPS | gap_min=0,0, stop=1,0xR1, saida=TEMPO(3d), lados=CV, filtro dia: sem_seg | APROVADA_NO_IS | 9/16 | R$ 55,63 | 50,9% vs 45,5% | 53 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| SMASH | n=1, excl_out=True, stop=0,5xR1, saida=RR(2,0R), lados=CV, filtro dia: sem_qua | APROVADA_NO_IS | 16/18 | R$ -94,25 | 23,9% vs 34,9% | 46 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| HSMASH | zona=0,25, close_contra=False, stop=extremo de S, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 0/0 | R$ -54,50 | 60,0% vs 66,8% | 5 | SEM TRADES SUFICIENTES (inconclusivo) |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 0/0 | R$ 114,14 | 64,3% vs 50,4% | 14 | SEM TRADES SUFICIENTES (inconclusivo) |
| GSV | n=1, k=(0,5; 0,5), stop=1,0xR1, saida=TEMPO(3d), lados=CV, filtro dia: sem_sex | APROVADA_NO_IS | 14/16 | R$ 95,41 | 44,8% vs 37,1% | 58 | POSITIVA FRACA no OOS (win% > breakeven mas o IC95% cruza o breakeven) |
| WR | n=10, espera=5, gatilho=95,0, toque=95,0, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 2/13 | R$ -48,66 | 39,5% vs 47,0% | 38 | SEM TRADES SUFICIENTES (inconclusivo) |
| UO | compra_max=35,0, venda_min=50,0, validade=10, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 9/12 | R$ 129,27 | 72,7% vs 48,3% | 11 | SEM TRADES SUFICIENTES (inconclusivo) |
| TDM | dias=(1; 2; 3), meses=(), stop=1,0xR1, saida=BAILOUT(0d), lados=C, filtro dia: sem_sex | APROVADA_NO_IS | 11/18 | R$ -90,23 | 55,4% vs 65,5% | 56 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| TDW | dia=2, stop=1,0xR1, saida=FECHAMENTO, lados=V, tend=SMA50 | APROVADA_NO_IS | 6/10 | R$ -50,31 | 41,2% vs 51,5% | 80 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| TRES_BARRAS | tf=5, stop=1,0xR1, tend=SWING | REPROVADA_NO_IS | 0/4 | R$ -7,02 | 73,5% vs 75,9% | 2090 | NAO FUNCIONA: reprovada nos criterios do IS |


## ETFs de bitcoin na B3 (diário)

Linha IS = a escolhida; linha OOS = leitura única. `liquido`/`MaxDD`/`trades` = mediana entre ativos; pregões = 150 (IS) / 101 (OOS). Slippage 1 tick.

```
variante                        retorno   liquido R$  MaxDD %    MaxDD R$ lucro/DD   win% trades     R$/dia trd/dia  capital final pregoes    BE emp%    N total cap.final*     pulou*
--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
VB ETF_BTC IS                         —        17,98        —        0,69    26,00  63,2%      6       0,12     0,0              —     150       17,8         19         91          0  CENSURADA(cx)
VB ETF_BTC OOS                        —        -0,20        —        2,89    -0,07  45,5%      4      -0,00     0,0              —     101       47,2         11         42          0  CENSURADA(cx)
OOPS ETF_BTC IS                       —         4,73        —        0,97     4,89  53,3%      5       0,03     0,0              —     150       31,9         15         78          0  CENSURADA(cx)
OOPS ETF_BTC OOS                      —        -2,40        —        2,40    -1,00  18,2%      4      -0,02     0,0              —     101       91,4         11         39          0  CENSURADA(cx)
SMASH ETF_BTC IS                      —         5,61        —        0,65     8,69  56,2%      8       0,04     0,1              —     150       29,9         16         79          0  CENSURADA(cx)
SMASH ETF_BTC OOS                     —        -0,84        —        1,46    -0,58  50,0%      9      -0,01     0,1              —     101       59,8         18         40          0  CENSURADA(cx)
HSMASH ETF_BTC IS                     —         0,05        —        2,63     0,02  26,7%      5       0,00     0,0              —     150       30,7         15         73          0  CENSURADA(cx)
HSMASH ETF_BTC OOS                    —         0,00        —        1,24     0,00  28,6%      4       0,00     0,0              —     101       34,4          7         40          0  CENSURADA(cx)
OUTSIDE ETF_BTC IS                    —        -1,93        —        2,09    -0,92  33,3%      3      -0,01     0,0              —     150       63,8          6         71          0  CENSURADA(cx)
OUTSIDE ETF_BTC OOS                   —         0,00        —        0,31     0,00  25,0%      2       0,00     0,0              —     101       37,6          4         41          0  CENSURADA(cx)
GSV ETF_BTC IS                        —         5,12        —        0,04   144,99  80,0%      7       0,03     0,0              —     150       26,7         20         78          0  CENSURADA(cx)
GSV ETF_BTC OOS                       —        -0,08        —        0,10    -0,85  57,1%      5      -0,00     0,0              —     101       84,1         14         42          0  CENSURADA(cx)
WR ETF_BTC IS                         —         6,50        —        0,16    41,01  81,2%      5       0,04     0,0              —     150       22,6         16         79          0  CENSURADA(cx)
WR ETF_BTC OOS                        —         1,11        —        0,00        —  90,0%      3       0,01     0,0              —     101       10,8         10         42          0  CENSURADA(cx)
UO ETF_BTC IS                         —        -0,96        —        0,96    -1,00  12,5%      3      -0,01     0,0              —     150       24,7          8         72          0  CENSURADA(cx)
UO ETF_BTC OOS                        —         3,31        —        0,54     6,11  33,3%      4       0,03     0,0              —     101       14,4         12         44          0  CENSURADA(cx)
TDM ETF_BTC IS                        —         3,58        —        0,00        —  75,0%      5       0,02     0,0              —     150        9,4         16         77          0  CENSURADA(cx)
TDM ETF_BTC OOS                       —        -0,02        —        0,02    -1,00  71,4%      2      -0,00     0,0              —     101       82,8          7         39          0  CENSURADA(cx)
TDW ETF_BTC IS                        —         7,34        —        0,21    34,74  69,0%     10       0,05     0,1              —     150       21,8         29         80          0  CENSURADA(cx)
TDW ETF_BTC OOS                       —        -0,35        —        0,59    -0,59  40,0%     10      -0,00     0,1              —     101       46,0         30         41          0  CENSURADA(cx)
```

| setup | célula escolhida no IS (params; saída; stop; lados; filtros) | status IS | IS: score mediana | vizinhas + | OOS 0/1/2 ticks (exp% mediana) | OOS win% [IC95%] vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|---|
| VB | k=(1,0; 1,0), sem stop, saida=REVERSAO, lados=V, filtro dia: sem_seg | APROVADA_NO_IS (380/2846 células passam) | 7,564 | 13/17 | -0,326% / -0,550% / -0,776% | 45,5% [21,3; 72,0] vs 47,2% | 11 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 11 trades |
| OOPS | gap_min=0,0, sem stop, saida=TEMPO(3d), lados=V, tend=SWING, filtro dia: sem_seg | APROVADA_NO_IS (111/1046 células passam) | 1,273 | 9/14 | -1,806% / -1,831% / -1,856% | 18,2% [5,1; 47,7] vs 91,4% | 11 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 11 trades |
| SMASH | n=1, excl_out=True, stop=1,0xR1, saida=TEMPO(3d), lados=V, tend=SMA50, filtro dia: sem_qui | APROVADA_NO_IS (531/1880 células passam) | 1,692 | 14/15 | -0,311% / -0,374% / -0,437% | 50,0% [29,0; 71,0] vs 59,8% | 18 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| HSMASH | zona=0,25, close_contra=False, stop=extremo de S, saida=RR(2,0R), lados=CV | REPROVADA_NO_IS (0/18 células passam) | -0,267 | 3/14 | -0,152% / -0,208% / -0,264% | 28,6% [8,2; 64,1] vs 34,4% | 7 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 7 trades |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | nan | 0/0 | -0,466% / -0,529% / -0,592% | 25,0% [4,6; 69,9] vs 37,6% | 4 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 4 trades |
| GSV | n=2, k=(0,5; 0,5), sem stop, saida=BAILOUT(0d), lados=V, filtro dia: sem_seg | APROVADA_NO_IS (46/724 células passam) | 2,021 | 10/14 | 0,067% / -0,157% / -0,381% | 57,1% [32,6; 78,6] vs 84,1% | 14 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 14 trades |
| WR | n=10, espera=5, gatilho=85,0, toque=95,0, modo=LIMITE_NO_FECHAMENTO_S, sem stop, saida=OSC, lados=CV, filtro dia: sem_qui | APROVADA_NO_IS (75/451 células passam) | 3,883 | 11/13 | 1,816% / 1,739% / 1,662% | 90,0% [59,6; 98,2] vs 10,8% | 10 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 10 trades |
| UO | compra_max=35,0, venda_min=50,0, validade=10, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=OSC, lados=CV | SEM_DADOS_SUFICIENTES (0/0 células passam) | nan | 0/0 | 1,088% / 1,063% / 1,038% | 33,3% [13,8; 60,9] vs 14,4% | 12 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 12 trades |
| TDM | dias=(1; 2; 3), meses=(), sem stop, saida=BAILOUT(0d), lados=C, tend=SWING, filtro dia: sem_ter | APROVADA_NO_IS (179/512 células passam) | 1,576 | 9/12 | 0,010% / -0,210% / -0,430% | 71,4% [35,9; 91,8] vs 82,8% | 7 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 7 trades |
| TDW | dia=3, sem stop, saida=FECHAMENTO, lados=V, tend=SWING | APROVADA_NO_IS (11/135 células passam) | 1,865 | 5/10 | -0,069% / -0,165% / -0,262% | 40,0% [24,6; 57,7] vs 46,0% | 30 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |

**ETFs de bitcoin na B3 (diário) — melhor célula COM stop de proteção** (a escolha irrestrita acima tende a `sem stop`, risco aberto; aqui o stop é obrigatório. Mesmo critério de escolha no IS, OOS lido uma vez):

| setup | célula (com stop) | status IS | vizinhas + | OOS exp 1 tick | OOS win% vs BE | N OOS | veredito |
|---|---|---|---|---|---|---|---|
| VB | k=(0,3; 0,3), stop=1,0xR1, saida=REVERSAO, lados=V, tend=SMA50, filtro dia: sem_qua | APROVADA_NO_IS | 12/17 | -0,119% | 21,1% vs 19,0% | 19 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| OOPS | gap_min=0,0, stop=1,0xR1, saida=TEMPO(3d), lados=V, tend=SMA50, filtro dia: sem_ter | APROVADA_NO_IS | 12/15 | -0,672% | 41,7% vs 47,7% | 12 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 12 trades |
| SMASH | n=1, excl_out=True, stop=1,0xR1, saida=TEMPO(3d), lados=V, tend=SMA50, filtro dia: sem_qui | APROVADA_NO_IS | 14/15 | -0,374% | 50,0% vs 59,8% | 18 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |
| HSMASH | zona=0,25, close_contra=False, stop=extremo de S, saida=RR(2,0R), lados=CV | REPROVADA_NO_IS | 3/14 | -0,208% | 28,6% vs 34,4% | 7 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 7 trades |
| OUTSIDE | modo=A_MERCADO_NA_ABERTURA, venda=True, stop=0,5xR1, saida=BAILOUT(0d), lados=CV | SEM_DADOS_SUFICIENTES | 0/0 | -0,529% | 25,0% vs 37,6% | 4 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 4 trades |
| GSV | n=1, k=(0,5; 0,5), stop=0,5xR1, saida=TEMPO(3d), lados=CV, tend=SMA50, filtro dia: sem_ter | REPROVADA_NO_IS | 0/14 | -0,680% | 8,3% vs 37,9% | 24 | NAO FUNCIONA: reprovada nos criterios do IS |
| WR | n=10, espera=5, gatilho=95,0, toque=95,0, modo=A_MERCADO_NA_ABERTURA, stop=1,0xR1, saida=OSC, lados=V | APROVADA_NO_IS | 10/14 | -2,444% | 25,0% vs 61,0% | 8 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 8 trades |
| UO | compra_max=35,0, venda_min=50,0, validade=10, modo=A_MERCADO_NA_ABERTURA, stop=0,5xR1, saida=OSC, lados=CV | SEM_DADOS_SUFICIENTES | 0/0 | 1,063% | 33,3% vs 14,4% | 12 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 12 trades |
| TDM | dias=(15), meses=(), stop=1,0xR1, saida=TEMPO(3d), lados=C, filtro dia: sem_qui | APROVADA_NO_IS | 11/17 | -0,630% | 23,1% vs 49,3% | 13 | AMOSTRA INSUFICIENTE (so' ~1 ano de M1 dos ETFs de bitcoin); OOS com 13 trades |
| TDW | dia=3, stop=0,5xR1, saida=FECHAMENTO, lados=V, tend=SWING | APROVADA_NO_IS | 5/10 | -0,216% | 40,0% vs 45,0% | 30 | NAO FUNCIONA: aprovada no IS, NAO se sustenta no OOS |


## Eixos da grade que não mexem no resultado (item 6.25)

Fração dos grupos (demais eixos fixos) em que mudar o eixo altera trades/líquido do IS. **0,00 = eixo morto**; `—` = eixo com 1 valor.

| setup | classe | eixo: fração |
|---|---|---|
| VB | ACAO | k=1.00; stop=1.00; saida=0.69; lados=1.00; tend=1.00; tdw=1.00 |
| VB | WIN | k=1.00; stop=0.99; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| VB | WDO | k=1.00; stop=0.99; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| VB | ETF_BTC | k=1.00; stop=1.00; saida=0.77; lados=1.00; tend=1.00; tdw=1.00 |
| OOPS | ACAO | gap_min=1.00; stop=1.00; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| OOPS | WIN | gap_min=1.00; stop=0.99; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| OOPS | WDO | gap_min=1.00; stop=0.94; saida=0.99; lados=1.00; tend=1.00; tdw=1.00 |
| OOPS | ETF_BTC | gap_min=1.00; stop=0.99; saida=0.94; lados=1.00; tend=1.00; tdw=1.00 |
| SMASH | ACAO | n=1.00; excl_out=1.00; stop=1.00; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| SMASH | WIN | n=1.00; excl_out=0.48; stop=0.91; saida=0.96; lados=0.99; tend=1.00; tdw=0.97 |
| SMASH | WDO | n=1.00; excl_out=0.48; stop=0.82; saida=0.92; lados=0.99; tend=1.00; tdw=0.94 |
| SMASH | ETF_BTC | n=1.00; excl_out=0.17; stop=0.91; saida=0.89; lados=0.99; tend=1.00; tdw=0.94 |
| HSMASH | ACAO | zona=1.00; close_contra=1.00; stop=1.00; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| HSMASH | WIN | zona=0.96; close_contra=0.00; stop=0.71; saida=0.82; lados=1.00; tend=0.67; tdw=0.83 |
| HSMASH | WDO | zona=0.66; close_contra=0.33; stop=0.33; saida=0.49; lados=0.64; tend=0.93; tdw=0.56 |
| HSMASH | ETF_BTC | zona=0.95; close_contra=0.73; stop=0.83; saida=0.62; lados=0.97; tend=0.97; tdw=0.94 |
| OUTSIDE | ACAO | modo=0.00; venda=1.00; stop=1.00; saida=1.00; lados=—; tend=1.00; tdw=1.00 |
| OUTSIDE | WIN | modo=0.00; venda=1.00; stop=0.67; saida=1.00; lados=—; tend=1.00; tdw=1.00 |
| OUTSIDE | WDO | modo=0.00; venda=1.00; stop=0.75; saida=0.96; lados=—; tend=1.00; tdw=1.00 |
| OUTSIDE | ETF_BTC | modo=0.00; venda=0.83; stop=0.88; saida=0.87; lados=—; tend=1.00; tdw=1.00 |
| GSV | ACAO | n=1.00; k=1.00; stop=1.00; saida=0.99; lados=1.00; tend=1.00; tdw=1.00 |
| GSV | WIN | n=0.99; k=1.00; stop=0.85; saida=0.93; lados=1.00; tend=0.99; tdw=0.95 |
| GSV | WDO | n=1.00; k=1.00; stop=0.95; saida=0.97; lados=1.00; tend=0.99; tdw=1.00 |
| GSV | ETF_BTC | n=0.94; k=1.00; stop=0.85; saida=0.60; lados=0.97; tend=0.99; tdw=0.89 |
| WR | ACAO | n=1.00; espera=—; gatilho=1.00; toque=1.00; modo=1.00; stop=1.00; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| WR | WIN | n=0.61; espera=—; gatilho=0.53; toque=1.00; modo=0.69; stop=0.74; saida=0.85; lados=0.97; tend=0.98; tdw=0.90 |
| WR | WDO | n=0.45; espera=—; gatilho=0.23; toque=1.00; modo=0.49; stop=0.49; saida=0.48; lados=0.50; tend=0.50; tdw=0.50 |
| WR | ETF_BTC | n=0.37; espera=—; gatilho=0.44; toque=0.93; modo=0.97; stop=0.86; saida=0.85; lados=0.97; tend=1.00; tdw=0.94 |
| UO | ACAO | compra_max=0.67; venda_min=0.67; validade=—; modo=1.00; stop=1.00; saida=1.00; lados=1.00; tend=1.00; tdw=1.00 |
| UO | WIN | compra_max=0.22; venda_min=0.63; validade=—; modo=0.26; stop=0.44; saida=0.41; lados=0.64; tend=0.83; tdw=0.50 |
| UO | WDO | compra_max=0.41; venda_min=0.67; validade=—; modo=0.55; stop=0.58; saida=0.59; lados=0.74; tend=0.97; tdw=0.64 |
| UO | ETF_BTC | compra_max=0.19; venda_min=0.67; validade=—; modo=0.37; stop=0.38; saida=0.44; lados=0.68; tend=0.67; tdw=0.54 |
| TDM | ACAO | dias=1.00; meses=1.00; stop=1.00; saida=1.00; lados=—; tend=1.00; tdw=1.00 |
| TDM | WIN | dias=1.00; meses=1.00; stop=1.00; saida=1.00; lados=—; tend=1.00; tdw=1.00 |
| TDM | WDO | dias=1.00; meses=0.97; stop=1.00; saida=1.00; lados=—; tend=1.00; tdw=1.00 |
| TDM | ETF_BTC | dias=1.00; meses=1.00; stop=0.98; saida=0.92; lados=—; tend=1.00; tdw=1.00 |
| TDW | ACAO | dia=1.00; stop=1.00; saida=—; lados=1.00; tend=1.00; tdw=— |
| TDW | WIN | dia=1.00; stop=1.00; saida=—; lados=1.00; tend=1.00; tdw=— |
| TDW | WDO | dia=1.00; stop=1.00; saida=—; lados=1.00; tend=1.00; tdw=— |
| TDW | ETF_BTC | dia=1.00; stop=1.00; saida=—; lados=1.00; tend=1.00; tdw=— |
| TRES_BARRAS | WIN | tf=1.00; stop=1.00; tend=1.00 |
| TRES_BARRAS | WDO | tf=1.00; stop=1.00; tend=1.00 |
