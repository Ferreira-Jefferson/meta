//+------------------------------------------------------------------+
//| WinCincoMedias.mq5                                               |
//| Expert Advisor para o MINI INDICE (WIN), sempre em H2             |
//| (Supertrend em H4), fixos no codigo.                              |
//|                                                                  |
//| v2.04 (2026-10-06): TEMPO GRAFICO H2 (era M30) e SUPERTREND H4    |
//| (era H1), escolha do dono. Foi assim que a estrategia foi medida  |
//| na rodada Y2 (port Python, 1 contrato, R$2 por operacao):         |
//| positiva em TODOS os anos, sem quebra -- 2022 +R$1.446, 2023      |
//| +R$1.232, 2024 +R$1.291, 2025 (ate' set) +R$657, 2026 +R$3.196.   |
//| No M30 eram 3 de 5 anos positivos. Mesmos numeros de todos os     |
//| inputs; so' o tempo grafico mudou. v2.03 em                       |
//| WinCincoMedias_v2_03.mq5.bak. Referencia Python do H2:            |
//| scripts/daytrade/comparativo_win_2026/port_cinco_medias_padrao.py |
//|                                                                  |
//| ZERAGEM ANTES DO FIM REAL DO PREGAO (v2.04): zera em              |
//| min(HoraZerar:MinutoZerar, fim da sessao - 1 min). Em 2022-23 o   |
//| pregao as vezes acabava 17:55; zerando so' as 18:24 a posicao     |
//| dormia ate' o dia seguinte (o H2 foi medido ja' com esta correcao).|
//| O fim da sessao vem de SymbolInfoSessionTrade; se nao der para    |
//| ler, vale HoraZerar:MinutoZerar (18:24). Obs.: no Testador a      |
//| sessao lida e' a configuracao ATUAL do simbolo, nao a da epoca.   |
//|                                                                  |
//| O QUE O H2 MUDA NA PRATICA                                       |
//|  - Velas H2 alinhadas a meia-noite do servidor: 08h (pregao das   |
//|    09h as 10h), 10h, 12h, 14h, 16h e 18h. A primeira decisao e'   |
//|    as 10:00.                                                      |
//|  - Validade da limite = ValidadeVelas (5) velas H2 = ate' 10 h,   |
//|    mas a ordem e' ORDER_TIME_DAY: na pratica vale ate' o fim do    |
//|    dia.                                                           |
//|  - Ultima entrada 18:20 e' comparada com a ABERTURA da vela que   |
//|    fechou. A vela das 18h nunca fecha dentro do pregao, entao a   |
//|    das 16h (fecha 18:00) ainda gera entrada as 18:00, que e'      |
//|    zerada as 18:24 -- igual ao port. A saida "horario" nunca      |
//|    acontece no H2: quem encerra o dia e' a zeragem.               |
//|  - Stop que aperta = 2 velas H2; volume relativo = mesma vela H2  |
//|    (mesmo horario) dos 20 pregoes anteriores; ATR(14) de velas H2.|
//|  - Supertrend H4: so' velas H4 ja' fechadas quando a vela H2 fecha|
//|    (abertura <= abertura da vela H2 - 2 h).                      |
//|                                                                  |
//| HISTORICO                                                        |
//| v2.00 (2026-10-06): M30 FIXO NO CODIGO (independe do periodo do   |
//| Testador/grafico), EMAs 2/4/6/17/33 e saida na EMA4 -- o mesmo    |
//| horizonte de tempo da v1 (M5, 9/21/34/100/200, saida 21).         |
//| Simulacao Python com custos: 2026 +R$7.350 (12/14 meses, pior     |
//| -R$117); 2025 -R$84 (PF 0,99) contra -R$1.366 da v1. 2025 foi     |
//| usado na escolha: so' conta demo daqui para frente valida.        |
//| v1.01 guardada em WinCincoMedias_v1_01.mq5.bak.                   |
//| v2.01: + saida por CLIMAX DE VOLUME CONTRA (vela M30 fechada com  |
//| volume relativo no topo 10% do contrato e corpo contra a posicao).|
//| Python: 2026 +R$7.805 (13/14), 2025 +R$203 (PF 1,02) contra      |
//| +R$7.350 / -R$84 sem ela; a mesma regra com range deu -R$245 em  |
//| 2025. Ganho pequeno, IC cruza zero.                               |
//| v2.02: + STOP QUE APERTA: depois de 2 velas M30 fechadas desde a  |
//| entrada, se esta' no negativo, stop a mercado em entrada -/+ 1 ATR.|
//| Python: 2026 +R$8.377 (PF 1,77), 2025 +R$284 (PF 1,03). Com 4 a  |
//| 10 velas o stop nunca chega a ser posto (trade ja' saiu antes).   |
//| v2.01 guardada em WinCincoMedias_v2_01.mq5.bak.                   |
//| v2.03: + saida quando o SUPERTREND(10,3) em H1 (so' velas H1      |
//| fechadas, desde o inicio do contrato) esta' CONTRA a posicao.     |
//| Python: 2026 +R$8.860, 2025 +R$567, 2022-24 +R$2.445 (v2.02:      |
//| +8.377 / +284 / +1.405). Melhora 2022, 2025 e 2026; 2023 e 2024  |
//| ficam um pouco piores. v2.02 em WinCincoMedias_v2_02.mq5.bak.     |
//| Estrategia NOVA e separada do EA Win.mq5 (roxa/verde).            |
//| Referencia Python: scripts/daytrade/win_cinco_medias.py          |
//|                                                                  |
//| SINAL (vela H2 fechada)                                          |
//|  5 EMAs do fechamento (padrao 2, 4, 6, 17, 33).                  |
//|  COMPRA: Ema1 > Ema2 > Ema3 > Ema4 > Ema5 e as 5 subindo         |
//|          (valor da vela fechada > valor da vela anterior).       |
//|  VENDA : espelho.                                                |
//|                                                                  |
//| FILTRO DE LADO PELO MES                                          |
//|  Nos DiasMesAnterior primeiros pregoes do mes vale a direcao do  |
//|  mes ANTERIOR (fechamento - abertura do mes anterior). Depois,   |
//|  vale o fechamento da vela do sinal contra a ABERTURA do mes:    |
//|  acima = so' compra, abaixo = so' vende, igual = os dois.        |
//|                                                                  |
//| ENTRADA                                                          |
//|  Ordem LIMITE no fechamento da vela do sinal (nunca a mercado),  |
//|  valida ValidadeVelas velas; cancelada se o alinhamento sumir ou |
//|  o dia virar. Se o preco ja' estiver melhor que o limite, a      |
//|  limite vai no preco atual (enche na hora, nunca pior que o      |
//|  fechamento do sinal). Uma posicao por vez.                      |
//|                                                                  |
//| SAIDA (a mercado, na abertura da vela seguinte)                  |
//|  Operacao A FAVOR do mes: sai quando uma vela FECHA do outro lado |
//|  da EMA de saida (EmaSaida, padrao 4).                           |
//|  Operacao sem direcao do mes definida: sai quando o alinhamento  |
//|  das 5 EMAs quebra.                                              |
//|  Sem entrada a partir de HoraUltimaEntrada; posicao aberta e'    |
//|  encerrada depois da vela dessa hora e zerada em HoraZerar (ou   |
//|  1 min antes do fim da sessao, se for antes).                    |
//|                                                                  |
//| Resultado de referencia da v2.00 em M30 (historico; o H2 esta' no |
//| topo) (simulacao Python, WIN 2026, 14 janelas                    |
//| mensais, 1 contrato): +R$7.490,10, 11/14 positivas, pior janela  |
//| -R$272,30, PF 1,54. Escolhido sobre os mesmos meses: NAO validado|
//| fora de 2026.                                                    |
//|                                                                  |
//| ROLAGEM: o mes so' e' medido a partir do dia em que o contrato   |
//| virou o principal (dia seguinte ao vencimento do anterior). Se o |
//| mes comecou no contrato antigo, a "abertura do mes" e' a do 1o   |
//| pregao do contrato atual, e o mes anterior nao conta (os dois    |
//| lados nos primeiros pregoes). v1.00 usava a abertura do mes do   |
//| proprio contrato, inclusive dos dias em que ele era pouco        |
//| negociado: em ago/2026 isso marcou "mes de baixa" durante uma    |
//| alta de 6% e o robo so' vendeu (-R$545 no Testador).             |
//| Diferenca restante da simulacao: as EMAs usam todo o historico do|
//| contrato (la' recomecam na rolagem). Rode no contrato vigente    |
//| (WINV26...), nao na serie continua.                              |
//+------------------------------------------------------------------+
//+--------------------------------------------------------------------+
//| v2.05 (2026-10-06, frente Z8): REGRA NaoOperarGapATR -- nao abre   |
//| posicao nova no dia em que |abertura - fechamento do pregao        |
//| anterior| >= NaoOperarGapATR (1,0) x ATR14 D1 (media simples do    |
//| True Range dos 14 pregoes anteriores). Input novo no FIM da lista; |
//| 0 desliga. As saidas seguem normais. Definicao completa (velas     |
//| ate' 18:25, dia de vencimento numa serie continua) no bloco "REGRA |
//| NaoOperarGapATR", identico nos 5 EAs do WIN. Decide no 1o tick do  |
//| pregao e escreve no Diario "Dia bloqueado: gap X pts = Y ATR".     |
//|                                                                    |
//| Por que (Z7, regra G1 k=1,0 pre-registrada, 5 robos somados,       |
//| 2022-01 a 2026-10-05, custo R$2/op): bloqueia so' 10 dias em ~5    |
//| anos -- eleicoes de 2022 (03/10 e 31/10), Ucrania (24/02/2022),    |
//| crash global de 05/08/2024, tarifas (04/04/2025), 05/10/2026 (gap  |
//| de +9,2% depois do 1o turno) e mais 4 --; +R$1.749 na soma (base   |
//| +R$21.414), melhora 4 de 5 anos (2023 nao teve dia bloqueado),     |
//| p99,8 contra bloquear o mesmo numero de dias ao acaso.             |
//|                                                                    |
//| FRAGILIDADE: o ganho vem quase todo do WinCincoMedias (+1.796), e  |
//| o de 2026 depende de 05/10 (+542; sem ele 2026 = -247 e a regra    |
//| cai para 3 de 5 anos). 5 regras testadas na Z7, sem correcao de    |
//| multiplicidade.                                                    |
//|                                                                    |
//| Neste robo (Z7, total 2022-2026 com custo): +R$1.796 (2022 +1.249, |
//| 2024 +202, 2025 +202, 2026 +143). Versao anterior em               |
//| WinCincoMedias_v2_04.mq5.bak.                                      |
//+--------------------------------------------------------------------+
#property copyright "WinCincoMedias"
#property version   "2.05"
#property strict

#include <Trade\Trade.mqh>

// Tempos graficos FIXOS da estrategia. Nao sao input de proposito: o EA calcula medias,
// sinal e horarios sempre em H2 (e o Supertrend em H4), seja qual for o periodo escolhido
// no Testador ou no grafico.
const ENUM_TIMEFRAMES TempoGrafico    = PERIOD_H2;
const ENUM_TIMEFRAMES TempoSupertrend = PERIOD_H4;   // proximo tempo do MT5 >= 2x o TempoGrafico

input int    Ema1               = 2;      // EMA mais rapida (versao M5 era 9)
input int    Ema2               = 4;      // EMA 2 (M5: 21)
input int    Ema3               = 6;      // EMA 3 (M5: 34)
input int    Ema4               = 17;     // EMA 4 (M5: 100)
input int    Ema5               = 33;     // EMA mais lenta (M5: 200)
input int    EmaSaida           = 4;      // (M5: 21) Operacao a favor do mes sai no fechamento do outro lado desta EMA
input int    DiasMesAnterior    = 5;      // Pregoes iniciais do mes que seguem a direcao do mes anterior (0 = desliga)
input int    ValidadeVelas      = 5;      // Validade da limite de entrada, em velas H2 (5 = 10 h; a ordem e' do dia e morre no fim do pregao)
input int    HoraUltimaEntrada  = 18;     // Hora da ultima vela que pode gerar entrada (servidor)
input int    MinutoUltimaEntrada= 20;     // Minuto: velas que abrem a partir daqui nao geram entrada e encerram a posicao
input int    HoraZerar          = 18;     // Zera a posicao a mercado a partir deste horario (servidor), ou 1 min antes do fim da sessao se for antes
input int    MinutoZerar        = 24;     // Minuto do zeramento (tambem e' o padrao se a sessao do simbolo nao puder ser lida)
input double Lote               = 1.0;    // Contratos por operacao
input ulong  MagicNumber        = 80080501; // Codigo que identifica as ordens deste robo
input datetime InicioContrato   = 0;      // 1o dia do contrato como principal (0 = automatico: dia seguinte ao vencimento, 4a-feira mais proxima do dia 15 dos meses pares)
input bool   SaidaVolume        = true;   // Sai quando uma vela fechada tem volume no topo do historico e corpo contra a posicao
input double SaidaVolumeQuantil = 0.90;   // Quantil do volume relativo (0.90 = 10% maiores desde o inicio do contrato)
input int    VolumePregoes      = 20;     // Volume relativo = volume / mediana do mesmo horario nos N pregoes anteriores
input int    StopApertaVelas    = 2;      // Stop que aperta: depois de N velas fechadas desde a entrada, se esta' no negativo, poe stop (0 = desliga)
input double StopApertaATR      = 1.0;    // Distancia desse stop: entrada -/+ K x ATR(14) da vela do sinal
input bool   SaidaSupertrendH1  = true;   // Sai quando o Supertrend em H4 (velas H4 fechadas) esta' contra a posicao (nome antigo mantido para os .set salvos)
input int    SupertrendPeriodo  = 10;     // Periodo do ATR do Supertrend H4
input double SupertrendMult     = 3.0;    // Multiplicador do ATR do Supertrend H4
input double NaoOperarGapATR     = 1.0;  // Z8: nao abre posicao nova no dia em que |abertura - fechamento anterior| >= N x ATR14 D1 (0 = desliga)

CTrade   trade;
int      g_h[5];
int      g_h_saida = INVALID_HANDLE;
datetime g_ultima_barra = 0;
bool     g_a_favor = false;      // a posicao aberta e' a favor do mes? (recuperado do comentario)

const string COM_FAVOR  = "wcm F";
const string COM_NEUTRO = "wcm N";

//+------------------------------------------------------------------+
//| REGRA NaoOperarGapATR (Z8, 2026-10-06) -- BLOCO IDENTICO nos 5   |
//| EAs do WIN (Win, Win_c1, WinCincoMedias, WinDeslocamentoMatinal, |
//| WinRetanguloEma34). Copiado de proposito, sem include: mudar aqui|
//| = mudar nos 5. Referencia Python: comparativo_win_2026/          |
//| filtro_gap.py (mesma definicao de combinacoes/z7_dias_extremos/  |
//| z7.py).                                                          |
//|  - Dia BLOQUEADO: |abertura do pregao - fechamento do pregao     |
//|    anterior| >= NaoOperarGapATR x ATR14 D1. Nao abre posicao nova|
//|    no dia; saidas seguem normais.                                |
//|  - Diarias montadas das velas M1 com abertura <= 18:25 (abertura |
//|    = 1a M1 do dia, maxima, minima, ultimo fechamento).           |
//|  - ATR14 D1 = media SIMPLES do True Range dos 14 pregoes         |
//|    ANTERIORES (nada do dia corrente).                            |
//|  - Simbolo CONTINUO (nome com '$' ou '@': WIN$N, WIN@, WIN$): no |
//|    dia do vencimento (4a-feira mais proxima do dia 15 dos meses  |
//|    pares; sem pregao nele, o 1o pregao ate' 3 dias depois) a     |
//|    serie troca de contrato: o gap NAO bloqueia e o True Range    |
//|    desse dia vale so' a amplitude (ignora o salto). Num contrato |
//|    especifico (WINV26...) nao ha salto: sem exclusao, TR completo|
//|  - Decide no 1o tick do pregao (com a 1a vela M1 do dia ja'      |
//|    formada) e guarda o resultado ate' o dia virar.               |
//+------------------------------------------------------------------+
long g_gap_dia_avaliado = -1;    // dia (TimeCurrent / 86400) ja' avaliado
bool g_gap_bloqueado    = false; // resultado do dia avaliado

// Vencimento do WIN de um mes par: quarta-feira mais proxima do dia 15.
datetime GapVencimentoWIN(int ano, int mes)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = 15;
   datetime t15 = StructToTime(d);
   TimeToStruct(t15, d);
   int dif = 3 - d.day_of_week;           // 3 = quarta
   if(dif > 3) dif -= 7;
   if(dif < -3) dif += 7;
   return t15 + dif * 86400;
}

// Serie continua (troca de contrato no vencimento): nome com '$' ou '@'.
bool GapSimboloContinuo()
{
   return StringFind(_Symbol, "$") >= 0 || StringFind(_Symbol, "@") >= 0;
}

// `dia` (00:00) e' o 1o pregao em/apos um vencimento, ate' 3 dias depois; `dia_ant` = pregao anterior.
bool GapDiaDeRolagem(datetime dia, datetime dia_ant)
{
   MqlDateTime d; TimeToStruct(dia, d);
   int ano = d.year, mes = d.mon;
   for(int k = 0; k < 2; k++)             // vencimento deste mes e do mes anterior
   {
      if(mes % 2 == 0)
      {
         datetime v = GapVencimentoWIN(ano, mes);
         if(v > dia_ant && v <= dia && dia - v < 4 * 86400) return true;
      }
      mes--; if(mes == 0) { mes = 12; ano--; }
   }
   return false;
}

// true = hoje NAO abre posicao nova. Avalia uma vez por dia; chame em todo tick (o 1o tick do pregao decide).
bool GapDiaBloqueado()
{
   if(NaoOperarGapATR <= 0.0) return false;
   datetime agora = TimeCurrent();
   long dia_n = (long)(agora / 86400);
   if(dia_n == g_gap_dia_avaliado) return g_gap_bloqueado;
   datetime dia0 = (datetime)(dia_n * 86400);
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_M1, dia0 - 45 * 86400, agora, r);
   if(n < 1 || r[n - 1].time < dia0) return false;   // ainda sem vela M1 de hoje: decide no proximo tick
   datetime dd[];
   double   dO[], dH[], dL[], dC[];
   int nd = 0;
   for(int i = 0; i < n; i++)
   {
      MqlDateTime t; TimeToStruct(r[i].time, t);
      if(t.hour * 60 + t.min > 18 * 60 + 25) continue;          // so' velas M1 com abertura <= 18:25
      datetime d = (datetime)((long)(r[i].time / 86400) * 86400);
      if(nd == 0 || d != dd[nd - 1])
      {
         nd++;
         ArrayResize(dd, nd); ArrayResize(dO, nd); ArrayResize(dH, nd); ArrayResize(dL, nd); ArrayResize(dC, nd);
         dd[nd - 1] = d; dO[nd - 1] = r[i].open; dH[nd - 1] = r[i].high; dL[nd - 1] = r[i].low;
      }
      if(r[i].high > dH[nd - 1]) dH[nd - 1] = r[i].high;
      if(r[i].low  < dL[nd - 1]) dL[nd - 1] = r[i].low;
      dC[nd - 1] = r[i].close;
   }
   g_gap_dia_avaliado = dia_n;
   g_gap_bloqueado = false;
   if(nd < 16 || dd[nd - 1] != dia0)
   {
      PrintFormat("NaoOperarGapATR: %s sem historico para o ATR14 D1 (%d pregoes M1 lidos, preciso de 15 + hoje) -- dia liberado",
                  TimeToString(dia0, TIME_DATE), nd);
      return false;
   }
   bool continuo = GapSimboloContinuo();
   double soma = 0.0;
   for(int k = nd - 15; k <= nd - 2; k++)                        // 14 pregoes anteriores a hoje
   {
      double amp = dH[k] - dL[k];
      double tr = MathMax(amp, MathMax(MathAbs(dH[k] - dC[k - 1]), MathAbs(dL[k] - dC[k - 1])));
      if(continuo && GapDiaDeRolagem(dd[k], dd[k - 1])) tr = amp;  // salto da troca de contrato nao e' volatilidade
      soma += tr;
   }
   double atr = soma / 14.0;
   double gap = dO[nd - 1] - dC[nd - 2];
   if(atr <= 0.0) return false;
   if(MathAbs(gap) < NaoOperarGapATR * atr) return false;
   if(continuo && GapDiaDeRolagem(dd[nd - 1], dd[nd - 2]))
   {
      PrintFormat("NaoOperarGapATR: %s gap %.0f pts = %.2f ATR, mas e' dia de vencimento numa serie continua (%s): troca de contrato, dia liberado",
                  TimeToString(dia0, TIME_DATE), gap, MathAbs(gap) / atr, _Symbol);
      return false;
   }
   g_gap_bloqueado = true;
   PrintFormat("Dia bloqueado: gap %.0f pts = %.2f ATR (abertura %.0f, fechamento anterior %.0f, ATR14 D1 %.1f, limite %.2f ATR) -- sem entrada nova hoje",
               gap, MathAbs(gap) / atr, dO[nd - 1], dC[nd - 2], atr, NaoOperarGapATR);
   return true;
}
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
int OnInit()
{
   if(Period() != TempoGrafico)
      PrintFormat("AVISO: grafico em %s, mas o EA calcula tudo em %s, com Supertrend em %s (fixo no codigo).",
                  EnumToString((ENUM_TIMEFRAMES)Period()), EnumToString(TempoGrafico), EnumToString(TempoSupertrend));
   int per[5] = {Ema1, Ema2, Ema3, Ema4, Ema5};
   for(int i = 0; i < 5; i++)
   {
      if(per[i] < 1) { Print("ERRO: periodos das EMAs devem ser >= 1."); return INIT_PARAMETERS_INCORRECT; }
      g_h[i] = iMA(_Symbol, TempoGrafico, per[i], 0, MODE_EMA, PRICE_CLOSE);
      if(g_h[i] == INVALID_HANDLE) return INIT_FAILED;
   }
   if(EmaSaida < 1 || ValidadeVelas < 1 || DiasMesAnterior < 0)
   {
      Print("ERRO: EmaSaida >= 1, ValidadeVelas >= 1, DiasMesAnterior >= 0.");
      return INIT_PARAMETERS_INCORRECT;
   }
   g_h_saida = iMA(_Symbol, TempoGrafico, EmaSaida, 0, MODE_EMA, PRICE_CLOSE);
   if(g_h_saida == INVALID_HANDLE) return INIT_FAILED;
   long rv[1];
   g_usa_real = CopyRealVolume(_Symbol, TempoGrafico, 1, 1, rv) == 1 && rv[0] > 0;
   if(!g_usa_real) Print("AVISO: simbolo sem volume real; a saida por volume usa o tick volume.");
   trade.SetExpertMagicNumber(MagicNumber);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   for(int i = 0; i < 5; i++) IndicatorRelease(g_h[i]);
   IndicatorRelease(g_h_saida);
}

//+------------------------------------------------------------------+
double Arredonda(double preco)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   return NormalizeDouble(MathRound(preco / tick) * tick, _Digits);
}

int MinutoDoDia(datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   return d.hour * 60 + d.min;
}

long Dia(datetime t) { return (long)(t / 86400); }

bool SelecionaPosicao()
{
   if(!PositionSelect(_Symbol)) return false;
   return PositionGetInteger(POSITION_MAGIC) == (long)MagicNumber;
}

// Ticket da ordem-limite pendente deste robo (0 = nenhuma)
ulong OrdemPendente()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if(OrderGetInteger(ORDER_MAGIC) != (long)MagicNumber) continue;
      return tk;
   }
   return 0;
}

//+------------------------------------------------------------------+
// +1 compra, -1 venda, 0 nada -- 5 EMAs na vela fechada `shift` contra a anterior
int Alinhamento(int shift)
{
   double v[5], ant[5];
   for(int i = 0; i < 5; i++)
   {
      double b[];                     // dinamico: ArraySetAsSeries nao vale para array estatico
      ArraySetAsSeries(b, true);      // b[0] = vela `shift`, b[1] = a anterior
      if(CopyBuffer(g_h[i], 0, shift, 2, b) != 2) return 0;
      if(b[0] == EMPTY_VALUE || b[1] == EMPTY_VALUE) return 0;
      v[i] = b[0]; ant[i] = b[1];
   }
   bool up = true, dn = true;
   for(int i = 0; i < 4; i++)
   {
      if(!(v[i] > v[i + 1])) up = false;
      if(!(v[i] < v[i + 1])) dn = false;
   }
   for(int i = 0; i < 5; i++)
   {
      if(!(v[i] > ant[i])) up = false;
      if(!(v[i] < ant[i])) dn = false;
   }
   return up ? 1 : (dn ? -1 : 0);
}

int Sinal(double x) { return x > 0.0 ? 1 : (x < 0.0 ? -1 : 0); }

datetime InicioDoDia(datetime t) { return (datetime)(Dia(t) * 86400); }

datetime InicioDoMes(int ano, int mes)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = 1;
   return StructToTime(d);
}

// Vencimento do WIN de um mes par: quarta-feira mais proxima do dia 15.
datetime VencimentoWIN(int ano, int mes)
{
   MqlDateTime d; ZeroMemory(d);
   d.year = ano; d.mon = mes; d.day = 15;
   datetime t15 = StructToTime(d);
   TimeToStruct(t15, d);
   int dif = 3 - d.day_of_week;           // 3 = quarta
   if(dif > 3) dif -= 7;
   if(dif < -3) dif += 7;
   return t15 + dif * 86400;
}

// 1o dia em que o contrato atual e' o principal: dia seguinte ao ultimo vencimento
// ANTERIOR ao dia de `t`. InicioContrato (input) substitui o calculo se preenchido.
datetime InicioDoContratoAtual(datetime t)
{
   if(InicioContrato > 0) return InicioDoDia(InicioContrato);
   MqlDateTime d; TimeToStruct(t, d);
   int ano = d.year, mes = d.mon;
   for(int k = 0; k < 4; k++)
   {
      if(mes % 2 == 0)
      {
         datetime v = VencimentoWIN(ano, mes);
         if(Dia(v) < Dia(t)) return InicioDoDia(v) + 86400;
      }
      mes--; if(mes == 0) { mes = 12; ano--; }
   }
   return 0;
}

// Abertura da 1a vela do TempoGrafico em ou depois de `a`, e antes de `ate`
bool AberturaDesde(datetime a, datetime ate, double &abertura)
{
   int sh = iBarShift(_Symbol, TempoGrafico, a, false);
   if(sh < 0) return false;
   if(iTime(_Symbol, TempoGrafico, sh) < a) sh--;
   if(sh < 0) return false;
   datetime tb = iTime(_Symbol, TempoGrafico, sh);
   if(tb < a || tb >= ate) return false;
   abertura = iOpen(_Symbol, TempoGrafico, sh);
   return abertura > 0.0;
}

// Direcao do mes vista no fechamento da vela `shift`: +1 so' compra, -1 so' venda, 0 os dois.
// O mes so' e' medido a partir do dia em que o contrato virou o principal: antes disso
// o contrato e' pouco negociado e a abertura dele nao representa o mercado.
int RegimeMes(int shift)
{
   datetime t = iTime(_Symbol, TempoGrafico, shift);
   MqlDateTime d; TimeToStruct(t, d);
   datetime ini_mes = InicioDoMes(d.year, d.mon);
   datetime ini_contrato = InicioDoContratoAtual(t);
   datetime ancora = MathMax(ini_mes, ini_contrato);

   if(DiasMesAnterior > 0)
   {
      // numero do pregao desde a ancora (1 = primeiro)
      int sh_d_ini = iBarShift(_Symbol, PERIOD_D1, ancora, false);
      int sh_d_hoje = iBarShift(_Symbol, PERIOD_D1, t, false);
      if(sh_d_ini >= 0 && sh_d_hoje >= 0)
      {
         if(iTime(_Symbol, PERIOD_D1, sh_d_ini) < ancora) sh_d_ini--;
         int n_pregao = sh_d_ini - sh_d_hoje + 1;
         if(n_pregao <= DiasMesAnterior)
         {
            // mes anterior so' conta se ja' era deste contrato
            if(ini_contrato >= ini_mes) return 0;
            int am = d.mon - 1, aa = d.year;
            if(am == 0) { am = 12; aa--; }
            datetime anc_ant = MathMax(InicioDoMes(aa, am), ini_contrato);
            double ab;
            if(!AberturaDesde(anc_ant, ini_mes, ab)) return 0;
            int sh_fim = iBarShift(_Symbol, TempoGrafico, ini_mes - 1, false);   // ultima vela do mes anterior
            if(sh_fim < 0) return 0;
            double fe = iClose(_Symbol, TempoGrafico, sh_fim);
            if(fe <= 0.0) return 0;
            return Sinal(fe - ab);
         }
      }
   }
   double abertura, c[1];
   if(!AberturaDesde(ancora, t + 1, abertura)) return 0;
   if(CopyClose(_Symbol, TempoGrafico, shift, 1, c) != 1) return 0;
   return Sinal(c[0] - abertura);
}

// A posicao aberta foi a favor do mes? Vem do comentario da ordem de entrada
// (sobrevive a reinicio do EA). Se a corretora nao repassar o comentario para a
// posicao, procura na ordem que a abriu.
bool AFavorDoMes()
{
   string com = PositionGetString(POSITION_COMMENT);
   if(com == COM_FAVOR) return true;
   if(com == COM_NEUTRO) return false;
   long id = PositionGetInteger(POSITION_IDENTIFIER);
   if(HistorySelectByPosition(id))
      for(int i = HistoryOrdersTotal() - 1; i >= 0; i--)
      {
         ulong tk = HistoryOrderGetTicket(i);
         string oc = HistoryOrderGetString(tk, ORDER_COMMENT);
         if(oc == COM_FAVOR) return true;
         if(oc == COM_NEUTRO) return false;
      }
   PositionSelect(_Symbol);   // HistorySelect nao desfaz a selecao, mas garante
   return false;
}

//+------------------------------------------------------------------+
bool Fecha(string motivo)
{
   if(trade.PositionClose(_Symbol)) return true;
   PrintFormat("ERRO fechar (%s): retcode=%u (%s)", motivo, trade.ResultRetcode(), trade.ResultRetcodeDescription());
   return false;
}

void Cancela(ulong tk, string motivo)
{
   if(!trade.OrderDelete(tk))
      PrintFormat("ERRO cancelar ordem (%s): retcode=%u (%s)", motivo, trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
// SAIDA POR CLIMAX DE VOLUME (v2.01). So' velas FECHADAS: a vela em formacao nunca entra.
// Volume relativo da vela `shift` = volume / mediana do volume no MESMO horario dos
// VolumePregoes pregoes anteriores (minimo 5), contando so' pregoes do contrato atual
// (antes da rolagem o contrato e' pouco negociado e o volume nao representa o mercado).
// Limite = quantil SaidaVolumeQuantil dos volumes relativos das velas ANTERIORES desde o
// inicio do contrato, com pelo menos 100 velas. Igual a scripts/daytrade/win_cinco_medias.py.
double   g_hist_vrel[];
datetime g_hist_inicio = 0;     // inicio do contrato do historico
datetime g_hist_ultima = 0;     // ultima vela incluida
bool     g_usa_real = true;     // volume real (contratos); sem ele, tick volume

double VolumeDe(int shift)
{
   long v[1];
   if(g_usa_real) { if(CopyRealVolume(_Symbol, TempoGrafico, shift, 1, v) != 1) return -1; }
   else           { if(CopyTickVolume(_Symbol, TempoGrafico, shift, 1, v) != 1) return -1; }
   return (double)v[0];
}

double VolRel(int shift, datetime ini_contrato)
{
   datetime t = iTime(_Symbol, TempoGrafico, shift);
   if(t == 0) return -1;
   long hora = (long)t % 86400;
   double vol = VolumeDe(shift);
   if(vol < 0) return -1;
   int n = 800;
   datetime tt[]; long vv[];
   ArraySetAsSeries(tt, true); ArraySetAsSeries(vv, true);
   int got = CopyTime(_Symbol, TempoGrafico, shift + 1, n, tt);
   int gv = g_usa_real ? CopyRealVolume(_Symbol, TempoGrafico, shift + 1, n, vv)
                       : CopyTickVolume(_Symbol, TempoGrafico, shift + 1, n, vv);
   got = MathMin(got, gv);
   double amostra[];
   int k = 0;
   for(int i = 0; i < got && k < VolumePregoes; i++)
   {
      if(tt[i] < ini_contrato) break;
      if((long)tt[i] % 86400 != hora) continue;
      ArrayResize(amostra, k + 1); amostra[k++] = (double)vv[i];
   }
   if(k < 5) return -1;
   ArraySort(amostra);
   double med = (k % 2 == 1) ? amostra[k / 2] : (amostra[k / 2 - 1] + amostra[k / 2]) / 2.0;
   if(med <= 0.0) return -1;
   return vol / med;
}

double Quantil(const double &x[], double q)
{
   int n = ArraySize(x);
   double s[]; ArrayCopy(s, x); ArraySort(s);
   double pos = q * (n - 1);
   int lo = (int)MathFloor(pos);
   int hi = MathMin(lo + 1, n - 1);
   return s[lo] + (pos - lo) * (s[hi] - s[lo]);
}

// Atualiza o historico ate' a vela 2 e devolve o limite valido para a vela 1 (-1 = sem limite ainda)
double LimiteVolume()
{
   datetime t1 = iTime(_Symbol, TempoGrafico, 1);
   datetime ini = InicioDoContratoAtual(t1);
   datetime t2 = iTime(_Symbol, TempoGrafico, 2);
   if(ini != g_hist_inicio || g_hist_ultima > t2)
   {
      ArrayResize(g_hist_vrel, 0); g_hist_inicio = ini; g_hist_ultima = 0;
   }
   // acrescenta as velas fechadas ainda nao incluidas, da mais antiga para a mais nova, ate' a vela 2
   datetime desde = g_hist_ultima > 0 ? g_hist_ultima : ini - 1;
   int sh_ini = iBarShift(_Symbol, TempoGrafico, desde, false);
   if(sh_ini < 0) return -1;
   for(int sh = sh_ini; sh >= 2; sh--)
   {
      datetime ts = iTime(_Symbol, TempoGrafico, sh);
      if(ts <= desde || ts < ini) continue;
      double vr = VolRel(sh, ini);
      if(vr >= 0)
      {
         int n = ArraySize(g_hist_vrel);
         ArrayResize(g_hist_vrel, n + 1); g_hist_vrel[n] = vr;
      }
      g_hist_ultima = ts;
   }
   if(ArraySize(g_hist_vrel) < 100) return -1;
   return Quantil(g_hist_vrel, SaidaVolumeQuantil);
}

// Vela 1 (acabou de fechar) e' climax de volume CONTRA a posicao `lado`?
bool ClimaxContra(int lado)
{
   double lim = LimiteVolume();
   if(lim < 0) return false;
   double vr = VolRel(1, g_hist_inicio);
   if(vr < 0 || vr < lim) return false;
   double o = iOpen(_Symbol, TempoGrafico, 1), c = iClose(_Symbol, TempoGrafico, 1);
   return lado > 0 ? c < o : c > o;
}

//+------------------------------------------------------------------+
// STOP QUE APERTA (v2.02). Recalculado do zero a cada vela fechada (sobrevive a reinicio):
// se alguma vela fechada a partir da StopApertaVelas-esima desde a entrada (contando a da
// entrada) terminou no NEGATIVO, o stop da posicao vai para entrada -/+ StopApertaATR x ATR(14)
// da vela do sinal (a anterior a da entrada). Stop na corretora = a mercado. Nunca afrouxa.
// ATR = media de Wilder do True Range (igual ao Python), sobre 300 velas.
double AtrWilder(int shift)
{
   int n = 300;
   double hi[], lo[], cl[];
   ArraySetAsSeries(hi, false); ArraySetAsSeries(lo, false); ArraySetAsSeries(cl, false);
   int a = CopyHigh(_Symbol, TempoGrafico, shift, n, hi);
   int b = CopyLow(_Symbol, TempoGrafico, shift, n, lo);
   int c = CopyClose(_Symbol, TempoGrafico, shift, n, cl);
   int m = MathMin(a, MathMin(b, c));
   if(m < 15) return -1;
   double atr = hi[0] - lo[0];
   for(int i = 1; i < m; i++)
   {
      double tr = MathMax(hi[i] - lo[i], MathMax(MathAbs(hi[i] - cl[i - 1]), MathAbs(lo[i] - cl[i - 1])));
      atr += (tr - atr) / 14.0;
   }
   return atr;
}

// Nivel do stop que aperta para a posicao selecionada (0 = ainda nao ha')
double NivelStopAperta(int lado)
{
   if(StopApertaVelas <= 0) return 0.0;
   datetime t_pos = (datetime)PositionGetInteger(POSITION_TIME);
   double entrada = PositionGetDouble(POSITION_PRICE_OPEN);
   int sh_e = iBarShift(_Symbol, TempoGrafico, t_pos, false);     // vela da entrada
   if(sh_e < 1) return 0.0;                                       // entrada na vela em formacao
   bool armou = false;
   for(int sh = sh_e - StopApertaVelas + 1; sh >= 1; sh--)        // velas fechadas com nb >= N
   {
      double c = iClose(_Symbol, TempoGrafico, sh);
      if(lado * (c - entrada) < 0) { armou = true; break; }
   }
   if(!armou) return 0.0;
   double atr = AtrWilder(sh_e + 1);
   if(atr <= 0) return 0.0;
   return Arredonda(entrada - lado * StopApertaATR * atr);
}

void AjustaStopAperta(int lado)
{
   double nivel = NivelStopAperta(lado);
   if(nivel <= 0.0) return;
   double sl = PositionGetDouble(POSITION_SL);
   if(sl > 0.0 && lado * (sl - nivel) >= 0.0) return;              // ja' esta' igual ou mais apertado
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double preco = lado > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(lado > 0 ? preco <= nivel + tick : preco >= nivel - tick)    // preco ja' passou do stop: sai agora
   {
      Fecha("stop que aperta (preco ja' alem do nivel)");
      return;
   }
   if(!trade.PositionModify(_Symbol, nivel, PositionGetDouble(POSITION_TP)))
      PrintFormat("ERRO colocar stop que aperta @ %.0f: retcode=%u (%s)", nivel, trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
// SAIDA PELO SUPERTREND (v2.03 em H1; v2.04 em H4 = TempoSupertrend). Supertrend(SupertrendPeriodo,
// SupertrendMult) calculado do zero sobre as velas H4 desde o inicio do contrato atual, so' as que
// JA' FECHARAM quando a vela H2 `1` fechou: abertura <= abertura da vela H2 - 2 h (vale porque o
// TempoSupertrend e' 2x o TempoGrafico; igual a `ate = ts[j] - base` de port_cinco_tf.py).
// ATR de Wilder comecando no 1o True Range (h-l), valido a partir da SupertrendPeriodo-esima vela.
// Devolve +1/-1, 0 = ainda sem direcao.
int DirecaoSupertrend()
{
   datetime t1 = iTime(_Symbol, TempoGrafico, 1);
   if(t1 == 0) return 0;
   datetime ini = InicioDoContratoAtual(t1);
   datetime ate = t1 - PeriodSeconds(TempoGrafico); // abertura da ultima vela H4 ja' fechada
   if(ate < ini) return 0;
   MqlRates r[];
   ArraySetAsSeries(r, false);                      // r[0] = mais antiga
   int n = CopyRates(_Symbol, TempoSupertrend, ini, ate, r);
   if(n < SupertrendPeriodo) return 0;
   double atr = 0.0, fu = 0.0, fl = 0.0;
   int cur = 0;
   bool tem = false;
   for(int i = 0; i < n; i++)
   {
      double tr = i == 0 ? r[i].high - r[i].low
                         : MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      atr = i == 0 ? tr : atr + (tr - atr) / SupertrendPeriodo;
      if(i < SupertrendPeriodo - 1) continue;      // ATR ainda sem barras suficientes
      double hl2 = (r[i].high + r[i].low) / 2.0;
      double bu = hl2 + SupertrendMult * atr, bl = hl2 - SupertrendMult * atr;
      if(!tem)
      {
         fu = bu; fl = bl; cur = r[i].close >= hl2 ? 1 : -1; tem = true;
         continue;
      }
      double pc = r[i - 1].close;
      double nfu = (bu < fu || pc > fu) ? bu : fu;
      double nfl = (bl > fl || pc < fl) ? bl : fl;
      fu = nfu; fl = nfl;
      if(cur == 1 && r[i].close < fl) cur = -1;
      else if(cur == -1 && r[i].close > fu) cur = 1;
   }
   return cur;
}

bool CotacaoValida()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   return bid > 0.0 && ask > 0.0 && ask >= bid;
}

void Entra(int lado, bool a_favor)
{
   if(!CotacaoValida())
   {
      PrintFormat("Entrada ignorada: %s sem cotacao valida -- use o contrato real (ex.: WINV26), nao a serie continua", _Symbol);
      return;
   }
   double c[1];
   if(CopyClose(_Symbol, TempoGrafico, 1, 1, c) != 1) return;
   double limite = Arredonda(c[0]);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK), bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   // Preco ja' melhor que o limite: a limite vai no preco atual (enche na hora, nunca pior que o fechamento do sinal).
   double preco = lado > 0 ? MathMin(limite, Arredonda(ask)) : MathMax(limite, Arredonda(bid));
   string com = a_favor ? COM_FAVOR : COM_NEUTRO;
   bool ok = lado > 0 ? trade.BuyLimit(Lote, preco, _Symbol, 0.0, 0.0, ORDER_TIME_DAY, 0, com)
                      : trade.SellLimit(Lote, preco, _Symbol, 0.0, 0.0, ORDER_TIME_DAY, 0, com);
   if(!ok)
      PrintFormat("ERRO entrada limite %s @ %.0f: retcode=%u (%s)", lado > 0 ? "COMPRA" : "VENDA", preco,
                  trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

// Minuto do dia em que zera (v2.04): min(HoraZerar:MinutoZerar, fim da sessao de hoje - 1 min).
// O fim da sessao vem de SymbolInfoSessionTrade (como em WinDeslocamentoMatinal.mq5); sem ele,
// vale HoraZerar:MinutoZerar. Igual a ZERAR = min(18:24, fim_dia - 1) do port (x0b).
int MinutoZerarHoje(datetime agora)
{
   static long dia_cache = -1;
   static int  val_cache = 0;
   if(Dia(agora) == dia_cache) return val_cache;
   int padrao = HoraZerar * 60 + MinutoZerar;
   MqlDateTime t; TimeToStruct(agora, t);
   datetime de, ate;
   long fim = 0;
   for(uint s = 0; s < 10; s++)
   {
      if(!SymbolInfoSessionTrade(_Symbol, (ENUM_DAY_OF_WEEK)t.day_of_week, s, de, ate)) break;
      if((long)ate > fim) fim = (long)ate;
   }
   int z = padrao;
   if(fim > 0 && fim < 86400) z = MathMin(padrao, (int)(fim / 60) - 1);
   if(dia_cache < 0 || z != padrao)
      PrintFormat("Zeragem de hoje: %02d:%02d (fim da sessao lido: %s)", z / 60, z % 60,
                  (fim > 0 && fim < 86400) ? StringFormat("%02d:%02d", (int)(fim / 3600), (int)(fim % 3600) / 60) : "nao lido");
   dia_cache = Dia(agora);
   val_cache = z;
   return z;
}

//+------------------------------------------------------------------+
void OnTick()
{
   GapDiaBloqueado();   // Z8: o 1o tick do pregao decide se o dia esta' bloqueado pelo gap (NaoOperarGapATR)
   int agora = MinutoDoDia(TimeCurrent());
   int zerar = MinutoZerarHoje(TimeCurrent());
   int ultima = HoraUltimaEntrada * 60 + MinutoUltimaEntrada;

   bool tem_pos = SelecionaPosicao();
   if(tem_pos)
   {
      bool de_outro_dia = Dia(TimeCurrent()) != Dia((datetime)PositionGetInteger(POSITION_TIME));
      if(agora >= zerar || de_outro_dia) { Fecha("fim do pregao"); return; }
   }

   datetime barra = iTime(_Symbol, TempoGrafico, 0);
   if(barra == g_ultima_barra) return;
   g_ultima_barra = barra;

   datetime t1 = iTime(_Symbol, TempoGrafico, 1);
   bool mesmo_dia = Dia(t1) == Dia(barra);
   int  est1 = Alinhamento(1);
   if(SaidaVolume) LimiteVolume();   // historico do volume relativo acompanha todas as velas

   // 1) posicao aberta: decide a saida pela vela que acabou de fechar
   if(tem_pos)
   {
      int lado = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      g_a_favor = AFavorDoMes();
      bool sai = false;
      string motivo = "";
      if(MinutoDoDia(t1) >= ultima) { sai = true; motivo = "horario"; }
      else if(g_a_favor)
      {
         double e[1], c[1];
         if(CopyBuffer(g_h_saida, 0, 1, 1, e) == 1 && CopyClose(_Symbol, TempoGrafico, 1, 1, c) == 1)
            if(lado * (c[0] - e[0]) <= 0.0) { sai = true; motivo = StringFormat("fechou do outro lado da EMA%d", EmaSaida); }
      }
      else if(est1 != lado) { sai = true; motivo = "alinhamento quebrou"; }
      if(!sai && SaidaVolume && ClimaxContra(lado)) { sai = true; motivo = "climax de volume contra"; }
      if(!sai && SaidaSupertrendH1 && DirecaoSupertrend() == -lado) { sai = true; motivo = "Supertrend H4 contra"; }
      if(sai) Fecha(motivo);
      else if(StopApertaVelas > 0) AjustaStopAperta(lado);
      return;   // vela da saida nao gera entrada nova (igual a simulacao)
   }

   // 2) ordem-limite pendente: validade e alinhamento
   ulong tk = OrdemPendente();
   if(tk != 0)
   {
      int lado_ord = OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_LIMIT ? 1 : -1;
      datetime colocada = (datetime)OrderGetInteger(ORDER_TIME_SETUP);
      int velas = iBarShift(_Symbol, TempoGrafico, colocada, false);   // velas fechadas desde que entrou no livro
      if(!mesmo_dia || Dia(colocada) != Dia(barra)) { Cancela(tk, "dia novo"); }
      else if(velas >= ValidadeVelas)               { Cancela(tk, "validade"); }
      else if(est1 != lado_ord)                     { Cancela(tk, "alinhamento sumiu"); }
      else return;                                  // continua valendo
   }

   // 3) sinal novo
   if(!mesmo_dia || est1 == 0) return;
   if(MinutoDoDia(t1) >= ultima || agora >= zerar) return;
   if(PositionSelect(_Symbol)) return;              // posicao de outro robo no simbolo: nao mexe
   int reg = RegimeMes(1);
   if(reg != 0 && reg != est1) return;              // lado contra o mes
   if(GapDiaBloqueado()) { PrintFormat("Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)", est1 > 0 ? "COMPRA" : "VENDA"); return; }
   Entra(est1, reg == est1);
}
//+------------------------------------------------------------------+
