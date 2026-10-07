# Decisões do EA (mt5/LarryWilliams.mq5)

Arquivo separado de DECISOES.md (do motor Python) para não colidir na escrita; DECISOES.md vence em caso de divergência.

## Mapa input do EA -> chave de params_recomendados.json (nomes de chave a confirmar com o gerador)
| Input EA | Significado | Chave sugerida |
|---|---|---|
| UsarVB/Oops/Smash/HiddenSmash/Outside/GSV/WR/UO/TDM/TDW/TresBarras | liga o setup | setup |
| PermiteCompra / PermiteVenda | lados | lado_compra / lado_venda |
| ModoSaida, SaidaDias, BailoutAposDias, RRAlvo | saída | modo_saida, saida_dias, bailout_apos_dias, rr_alvo |
| StopModo, StopFrac, AtrPeriodo | stop | stop_modo, stop_frac, atr_periodo |
| VB_Kc, VB_Kv | VB | kc, kv |
| Oops_GapMin, Oops_CompraApos17 | OOPS | gap_min, compra_apos_17 |
| Smash_N, Smash_ExcluirOutside, Smash_StopExtremo | SMASH | n, excluir_outside, stop_extremo |
| HS_Zona, HS_ExigeCloseOposto | HSMASH | zona, exige_close_oposto |
| EntradaNaAbertura, Outside_LadoVenda, Outside_EvitaQuinta | OUTSIDE/WR/UO/TDM/TDW | modo_entrada, lado_venda, evita_quinta |
| GSV_N, GSV_Kc, GSV_Kv | GSV | n, kc, kv |
| WR_Periodo, WR_Espera, WR_NivelCompra, WR_NivelVenda, WR_Janela | WR | periodo, espera, nivel_compra, nivel_venda, janela |
| UO_P1..P3, UO_NivelCompra, UO_NivelVenda, UO_Janela | UO | p1..p3, nivel_compra, nivel_venda, janela |
| TDM_DiasCompra/Venda, TDW_DiasCompra/Venda | TDM/TDW | dias_compra, dias_venda |
| TB_Timeframe, TB_StopFrac | TRES_BARRAS | timeframe, stop_frac |
| Tend_Geral, Tend_WR, Tend_3B, Tend_SMA_N | tendência | tendencia, tendencia_wr, tendencia_3b, sma_n |
| FiltroDiasCompra/Venda, FiltroMeses | filtros | filtro_dias_compra/venda, filtro_meses |

Seção dos defaults: bloco de `input` em LarryWilliams.mq5 (valores do livro/especificação); trocar ali.

## [INTERP] tomadas no EA
1. **Modo de saída único e global** (um enum para todos os setups diários). Recomendado por setup: VB/GSV/OUTSIDE/UO/WR = BAILOUT; OOPS = ABERTURA_SEGUINTE; SMASH/HSMASH = BAILOUT ou ALVO_RR; TDM = TEMPO_N (3); TDW = FECHAMENTO. Para testar combinações, rode um setup por vez.
2. **Prioridade** com vários setups: VB > OOPS > SMASH > HSMASH > OUTSIDE > GSV > WR > UO > TDM > TDW; o primeiro que gera sinal (após filtros) no dia vale.
3. **VB/GSV com os dois lados**: as duas ordens stop ficam pendentes (OCO manual: ao abrir posição, a outra é cancelada). Se os dois níveis fossem tocados no mesmo tick, vale o que o MT5 executar primeiro; o "mais próximo da abertura" do motor é só convenção de barra.
4. **Entrada LIMITE_NO_FECHAMENTO_S**: se a limite em C(S) já é executável (compra com C(S) >= ask), o EA executa a MERCADO (preço melhor que o pedido). Caso contrário, limite DAY.
5. **Ordem stop já atravessada** na hora de armar (ex.: buy stop abaixo do ask): não arma, apenas loga.
6. **OOPS**: stop = StopFrac·R1 a partir da entrada (não usa "mínima do dia", que é desconhecida). Máscaras de dia do livro (S&P sem qua/qui; Bonds venda só quarta) = usar FiltroDiasCompra/Venda, que valem para todos os setups.
7. **SMASH/HSMASH**: stop = range inteiro de S (extremo oposto) por padrão [SEC].
8. **GSV**: média sobre j = 1..N dias fechados; venda usa o espelho (Swing1 = H[j]−L[j+3], Swing2 = H[j+3]−L[j+1]); stop StopFrac·R1 (não US$1.750).
9. **WR**: sinal = %R[S-1] ≥ nível e %R[S] < nível (cruzamento em S) E existe toque de 100 (0 na venda) pelo menos WR_Espera pregões antes de S dentro de WR_Janela. Variante lateral (≤90/≈10) NÃO implementada. Saída por indicador: comprado sai com %R ≤ WR_NivelVenda; vendido com %R ≥ WR_NivelCompra.
10. **UO**: pivôs de 3 barras no UO (confirmados com 1 barra de atraso, shift ≥ 2); par = dois pivôs mais recentes; pico/fundo intermediário = max/min do UO entre eles; gatilho só vale se o rompimento ocorre exatamente em S (UO[1] rompe, UO[2] não). Saídas de indicador avaliadas na abertura sobre barras fechadas.
11. **TENDÊNCIA swing**: remove inside days (relativo ao último não-inside), pivôs de 3 barras confirmados 1 barra depois; tendência = lado do rompimento mais recente (por high/low da barra). Janela de 150 barras.
12. **TDM**: dia de pregão do mês contado pelas barras D1 do próprio símbolo; mercado/limite como OUTSIDE.
13. **TRES_BARRAS**: lado definido pela tendência swing D1 (se Tend_3B = NENHUM, compra se permitida, senão venda). A cada barra nova do TF: cancela e rearma a limite de entrada em SMA3(mínimas) (compra); após o fill, coloca limite de alvo em SMA3(máximas) e a reposiciona a cada barra. Stop nativo TB_StopFrac·R1 diário. Zera no fim do pregão. Nunca converte em mercado. Requer conta NETTING (a limite de alvo é ordem oposta; em HEDGING abriria posição nova).
14. **SAIDA_ALVO_RR** usa TP nativo (gatilho a mercado, ao contrário do desenho fechado) — só para reproduzir a regra do livro/Rogue Quant.
15. **BAILOUT**: testado na primeira abertura de dia posterior (dias ≥ 1 + BailoutAposDias): `open(D) > entrada` (compra). Se não lucrativa, mantém até o stop/próxima abertura.
16. **Pregão**: HoraAbertura/MinAbertura/HoraFim/MinFim em horário do servidor; ordens armadas DelayAbertura minutos após a abertura com ORDER_TIME_DAY + cancelamento manual no fim.
17. **CSV**: `data` = data da ENTRADA (AAAA-MM-DD), lado C/V, preços com ponto decimal, `;` como separador, sem aspas; pnl_pts = (saída−entrada)·lado, sem custos nem slippage. Motivos: stop, alvo, alvo_limite, bailout, fechamento, tempo, abertura_seguinte, indicador, reversao, fim_pregao.
18. Hidden Gaps: não implementado (sem fonte). Filtro intermercado do GSV: omitido.
