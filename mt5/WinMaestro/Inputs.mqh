//+------------------------------------------------------------------+
//| WinMaestro/Inputs.mqh                                            |
//| Inputs do WinMaestro (grupo Maestro no topo, depois um grupo por |
//| robo). Incluido pelo EA e pelo EA de teste (que testa os modulos)|
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_INPUTS_MQH
#define WINMAESTRO_INPUTS_MQH

input group "Maestro"
input bool Ativo_GB = true;   // WinGapBarra1 ligado (desligado: nao abre nada novo; gere o que tiver ate' zerar)
input bool Ativo_CM = true;   // WinCincoMedias ligado
input bool Ativo_DM = true;   // WinDeslocamentoMatinal ligado
input bool Ativo_RE = true;   // WinRetanguloEma34 ligado
input bool Ativo_C1 = true;   // Win_c1 ligado
input double Risco_Capital = 1000;     // Capital da parada diaria, em R$ (fixo; nao e' o saldo da corretora)
input double Risco_PerdaDiaPct = 10.0; // Parada diaria: resultado liquido realizado do dia dos robos <= -isto % do capital -> sem entrada nova ate' o pregao seguinte (0 = desligada)

input group "WinGapBarra1"
input double GB_StopPts = 1200; // Stop em pontos (ordem stop no servidor, nasce com a entrada)
input double GB_AlvoPts = 0; // Alvo em pontos (0 = sem alvo). Se ativado e' ordem LIMITE oposta, nunca o tp nativo
input double GB_AlvoR = 0; // Alvo em multiplos do stop (0 = sem alvo); vale se AlvoPts = 0
input double GB_BeR = 0; // Breakeven: apos excursao de BeR x stop, stop vai para a entrada +/- 5 pts (0 = desligado)
input int GB_RecuoPts = 0; // Recuo do limite em relacao ao fechamento da barra 1 (pts)
input int GB_TtlBarras = 6; // Validade da ordem de entrada, em barras M5 (6 = ate' 09:35)
input int GB_GapMinPts = 5; // |gap| minimo em pontos (1 tick)
input int GB_AberturaHora = 9; // Hora da abertura do continuo (servidor)
input int GB_AberturaMin = 0; // Minuto da abertura
input int GB_FlattenHora = 18; // Zera a partir desta hora (servidor)...
input int GB_FlattenMinuto = 20; // ...e minuto (limitado ao corte: fim do continuo - 5 min)
input bool GB_EvitarVencimento = true; // Nao opera a 1a sessao em/depois do vencimento do WIN

input group "WinCincoMedias"
input int CM_Ema1 = 2; // EMA mais rapida (versao M5 era 9)
input int CM_Ema2 = 4; // EMA 2 (M5: 21)
input int CM_Ema3 = 6; // EMA 3 (M5: 34)
input int CM_Ema4 = 17; // EMA 4 (M5: 100)
input int CM_Ema5 = 33; // EMA mais lenta (M5: 200)
input int CM_EmaSaida = 4; // (M5: 21) Operacao a favor do mes sai no fechamento do outro lado desta EMA
input int CM_DiasMesAnterior = 5; // Pregoes iniciais do mes que seguem a direcao do mes anterior (0 = desliga)
input int CM_ValidadeVelas = 5; // Validade da limite de entrada, em velas H2 (5 = 10 h; a ordem e' do dia e morre no fim do pregao)
input int CM_HoraUltimaEntrada = 18; // Hora da ultima vela que pode gerar entrada (servidor)
input int CM_MinutoUltimaEntrada = 20; // Minuto: velas que abrem a partir daqui nao geram entrada e encerram a posicao
input int CM_HoraZerar = 18; // Zera a posicao a mercado a partir deste horario (servidor), limitado ao corte (D2)
input int CM_MinutoZerar = 24; // Minuto do zeramento (limitado ao corte: 18:20 / 17:50)
input datetime CM_InicioContrato = 0; // 1o dia do contrato como principal (0 = automatico: dia seguinte ao vencimento, 4a-feira mais proxima do dia 15 dos meses pares)
input bool CM_SaidaVolume = true; // Sai quando uma vela fechada tem volume no topo do historico e corpo contra a posicao
input double CM_SaidaVolumeQuantil = 0.90; // Quantil do volume relativo (0.90 = 10% maiores desde o inicio do contrato)
input int CM_VolumePregoes = 20; // Volume relativo = volume / mediana do mesmo horario nos N pregoes anteriores
input int CM_StopApertaVelas = 2; // Stop que aperta: depois de N velas fechadas desde a entrada, se esta' no negativo, poe stop (0 = desliga)
input double CM_StopApertaATR = 1.0; // Distancia desse stop: entrada -/+ K x ATR(14) da vela do sinal
input bool CM_SaidaSupertrendH1 = true; // Sai quando o Supertrend em H4 (velas H4 fechadas) esta' contra a posicao (nome antigo mantido para os .set salvos)
input int CM_SupertrendPeriodo = 10; // Periodo do ATR do Supertrend H4
input double CM_SupertrendMult = 3.0; // Multiplicador do ATR do Supertrend H4
input double CM_NaoOperarGapATR = 1.0; // Z8: nao abre posicao nova no dia em que |abertura - fechamento anterior| >= N x ATR14 D1 (0 = desliga)

input group "WinDeslocamentoMatinal"
input int DM_MinutosDecisao = 90; // Minutos de pregao ate' a decisao (90 = 10:30 com abertura 09:00)
input int DM_JanelaDecisaoMin = 5; // Se a decisao atrasar mais que isso (feed parado), o dia passa em branco
input double DM_DeslocMinATR = 0.3; // Afastamento minimo da abertura, em ATR diario
input double DM_BandaATR = 0.05; // Banda morta da abertura (cruzou = fechou alem dela), em ATR
input int DM_PeriodoATR = 14; // ATR diario: media simples do True Range das N ultimas velas D1
input int DM_EntradaTTLMin = 15; // Cancela a limite de entrada se nao encher em N minutos
input int DM_MinutosZerar = 5; // Zera a mercado N minutos antes do fim do continuo (limitado ao corte)
input int DM_HoraFimPregao = 18; // Fim do pregao (servidor) se a sessao do simbolo nao puder ser lida
input int DM_MinutoFimPregao = 25; // Minuto do fim do pregao (idem)
input int DM_FiltroMM = 0; // 0 = sem media; 1 = preco do lado da EMA100 M5; 2 = preco do lado da EMA10 e da EMA100 M5
input double DM_RiscoMaxPct = 10.0; // Teto do stop em % de R$1.000 fixos (DM_CAPITAL, B9; 0 = stop na linha da abertura)
input double DM_NaoOperarGapATR = 1.0; // Z8: nao abre posicao nova no dia em que |abertura - fechamento anterior| >= N x ATR14 D1 (0 = desliga)

input group "WinRetanguloEma34"
input int RE_JanelaBarras = 20; // Velas M15 na janela de deteccao do retangulo (>=6); pode incluir velas do pregao anterior
input double RE_ToleranciaBorda = 0.20; // Tolerancia de toque nas bordas, fracao da largura (default da G21/G29)
input double RE_AlvoFracaoLargura = 0.90; // Alvo = meio +/- esta fracao da largura (G29: 2x o stop)
input double RE_StopFracaoLargura = 0.45; // Stop  = meio -/+ esta fracao da largura (vencedor do IS da G21/G29)
input int RE_TtlBarrasEntrada = 10; // Cancela a limite de entrada se nao preencher dentro deste numero de velas M15
input double RE_LarguraMinimaPontos = 328.0; // Piso EMPIRICO extra de largura, em pontos (herdado da G21/G29 sem retune)
input int RE_PeriodoEma = 34; // Periodo da EMA que filtra a entrada (G29: so' passa do lado certo dela)
input int RE_AlvoAproximaBarras = 5; // PADRAO G37: a cada N velas fechadas depois da entrada, o alvo chega mais perto (0 = alvo parado, comportamento antigo)
input double RE_AlvoAproximaPasso = 0.10; // Quanto o alvo se aproxima a cada passo, em fracao da largura do retangulo
input double RE_AlvoPisoFracao = 0.50; // O alvo nunca chega mais perto que isto (fracao da largura) -- tem de ficar ACIMA do stop (perda>=ganho proibido)
input double RE_TickSizeWin = 5.0; // Tick minimo do WIN -- NAO mude (o MT5 relata errado sozinho pra WIN@/WDO@)
input int RE_HoraZerar = 17; // Hora que o robo fecha tudo e para de operar pelo resto do dia (junto com o minuto abaixo)
input int RE_MinutoZerar = 0; // PADRAO 2026-10-06: zera 17:00 (era 17:50). Novas entradas param TtlBarrasEntrada velas antes
input int RE_HoraInicio = 9; // Hora a partir da qual o robo comeca a contar velas (junto com o minuto abaixo)
input int RE_MinutoInicio = 1; // Minuto (junto com a hora acima) -- pula o leilao de abertura (08:55-09:01, cotacoes indicativas nao negociaveis, medido ate' 17mil pts de oscilacao numa unica vela)
input double RE_RangeMaximoBarraPontos = 2000.0; // Referencia M1: vela com faixa (maxima-minima) maior que isto x raiz(minutos da vela) e' tick ruim e sai do historico (M15: ~7.746 pts; 0 = desligado)
input double RE_FiltroAmplitudeATR = 0.5; // v1.06 (f3): so' arma se a amplitude do pregao ate' a decisao >= isto x ATR14 D1 (0 = desligado)
input double RE_NaoOperarGapATR = 1.0; // Z8: nao abre posicao nova no dia em que |abertura - fechamento anterior| >= N x ATR14 D1 (0 = desliga)

input group "Win_c1"
input int C1_Periodo = 34; // Periodo da WMA (roxa) e da SMMA (verde)
input double C1_KFechamentoATR = 0.6; // Stop na roxa deslocado K x ATR para o lado do preco
input int C1_PeriodoATR = 14; // Periodo do ATR (media simples do True Range, H1)
input int C1_IdadeMax = 9; // So' entra ate' a N-esima vela seguida do mesmo lado da roxa (0 = sem filtro)
input double C1_DistMinPontos = 15.0; // Ponta do pavio a no minimo N pontos da roxa
input double C1_GapMaxATR = 3.0; // So' entra se |roxa-verde| / ATR < N (0 = sem filtro)
input double C1_ExtRoxaMinATR = 1.4; // Extremo da vela (maxima na compra, minima na venda) a no minimo N x ATR da roxa (0 = sem filtro)
input double C1_DistVerdeMinATR = 1.2; // Fechamento a no minimo N x ATR da verde, no sentido da operacao (0 = sem filtro)
input double C1_EsticadaArmaATR = 2.5; // Arma a saida por esticada quando o afastamento da roxa passa de N x ATR (0 = sem esta saida)
input double C1_EsticadaRecuoATR = 0.75; // Armada, sai quando o afastamento recua N x ATR do maior afastamento da operacao
input int C1_AlinharM15 = 1; // 1 = exige H3 alinhado, 0 = desliga (ultima H3 fechada: close do lado do sinal da roxa H3 e verde H3 do lado oposto)
input bool C1_DebugFiltros = false; // Imprime no Diario os valores do filtro H3 a cada sinal que passou os demais filtros
input int C1_JanelaToques = 20; // Janela, em velas H1 fechadas, para contar os toques na roxa (0 = sem filtro)
input int C1_ToquesMax = 14; // Maximo de velas da janela que tocaram a roxa para poder entrar
input string C1_HorasSemEntrada = "11,15,16,17"; // Horas cheias do servidor (0-23, separadas por virgula) em que NAO abre operacao; vazio = sem filtro
input int C1_HoraFimPregao = 18; // Hora do fim do pregao (horario do servidor do MT5)
input int C1_MinutoFimPregao = 0; // Minuto do fim do pregao
input int C1_MinutosSemEntrada = 30; // Para de abrir operacao tantos minutos antes do fim
input int C1_MinutosZerar = 10; // Fecha a posicao a mercado tantos minutos antes do fim
input int C1_BreakEvenMinutos = 15; // Break-even a mercado: minutos apos a abertura da H1 de entrada (0 = desligado; 15 = a regra testada)
input double C1_BreakEvenColchaoPts = 7.0; // Break-even: fecha a mercado se o resultado flutuante for <= N pontos a favor (7 = custo 5 + slippage 2)
input double C1_NaoOperarGapATR = 1.0; // Z8: nao abre posicao nova no dia em que |abertura - fechamento anterior| >= N x ATR14 D1 (0 = desliga)

input group "EscadaWinM15"
input bool Ativo_ES = true;   // EscadaWinM15 (escada de topos e fundos M15, robo ES) ligado (desligado: nao abre nada novo)

#endif
