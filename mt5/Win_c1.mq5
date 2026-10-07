//+------------------------------------------------------------------+
//| Win_c1.mq5  (v2.07: Win + break-even; H1, filtro H3, gap ATR)    |
//| Expert Advisor para o MINI INDICE (WIN). Calcula em H1 (fixo no  |
//| codigo, sem input), qualquer que seja o tempo do grafico.        |
//|                                                                  |
//| v2.06 (2026-10-06): o tempo grafico passou de M5 para H1 e o     |
//| filtro superior de M15 para H3 (proximo tempo do MT5 >= 3x a     |
//| base). Inputs, filtros e horas sem entrada iguais aos da v2.05;  |
//| o que era contado em velas continua em velas (agora H1) e o      |
//| break-even continua em MINUTOS (15 depois da abertura da H1 de   |
//| entrada, checado no 1o tick de cada M1). Por que: no replay da   |
//| comparacao de tempos graficos (Y1b, 2022-2026, custo de R$2/op)  |
//| o H1 deu +R$2.267 (4 de 5 anos positivos) contra perda no M5     |
//| fora de 2026; escolha do dono. A v2.05 (M5) esta em              |
//| Win_c1_v2_05.mq5.bak.                                            |
//|                                                                  |
//| Direcao: WMA (Linear Weighted, a ROXA) e SMMA (Smoothed, a VERDE)|
//| de periodo 34 sobre o fechamento. Compra so' com a vela INTEIRA  |
//| (pavio incluido) ACIMA da roxa E a verde ABAIXO da roxa; venda   |
//| so' com a vela inteira ABAIXO da roxa E a verde ACIMA da roxa.   |
//| Decide so' no FECHAMENTO da vela e entra a mercado na abertura da|
//| seguinte.                                                        |
//|                                                                  |
//| Filtros de entrada (todos sobre a vela do sinal):                |
//|  - Idade: a vela do sinal e' no maximo a IdadeMax-esima vela     |
//|    seguida a fechar do mesmo lado da roxa (comeco da onda).      |
//|  - Distancia: a ponta do pavio mais proxima da roxa esta a pelo  |
//|    menos DistMinPontos dela (preco nao colado na roxa).          |
//|  - Gap: |roxa - verde| / ATR < GapMaxATR (medias nao esticadas).  |
//|  - Indecisao: nas ultimas JanelaToques velas fechadas, no maximo  |
//|    ToquesMax tocaram a roxa (vela nao inteira do lado do sinal). |
//|    Muito toque recente = mercado sem direcao, mais stops.        |
//|  - Horario: nao abre operacao nas horas de HorasSemEntrada (hora do  |
//|    servidor). Nos dados, 11h e as entradas depois das 15h perdiam |
//|    nos dois periodos testados.                                    |
//|  - Espaco: o extremo da vela do lado do preco esta a pelo menos  |
//|    ExtRoxaMinATR x ATR da roxa, e o fechamento a pelo menos      |
//|    DistVerdeMinATR x ATR da verde (onda com espaco para andar).  |
//|                                                                  |
//|  - M15 alinhado (AlinharM15 = 1, ligado por padrao; 0 desliga): |
//|    (desde a v2.05/v2.06 o filtro superior e' o H3, nao o M15; o |
//|    nome do input ficou AlinharM15 para nao quebrar presets):     |
//|    da H1 seguinte ao sinal, a ULTIMA barra H3 JA FECHADA (nunca  |
//|    a H3 em formacao) tem fechamento do mesmo lado da roxa H3     |
//|    (LWMA34 do close H3) que o sinal (acima na compra, abaixo na  |
//|    venda) E a verde H3 (SMMA34) do lado oposto da roxa H3.       |
//|    Comparacoes estritas. Validado em 60 meses de WIN@D (IC cruza |
//|    zero); faz parte da estrategia, por isso vem ligado.          |
//|  - DebugFiltros (desligado por padrao): imprime no Diario, por   |
//|    sinal que passou os demais filtros, os valores do H3 e o      |
//|    veredito do filtro.                                           |
//|                                                                  |
//| Saida: nao ha alvo nem trailing. O stop fica na roxa deslocado   |
//| KFechamentoATR x ATR para o lado do preco, e e' recolocado a cada|
//| fechamento de vela H1 (acompanha a roxa, sobe e desce). Se uma   |
//| vela H1 fecha ENTRE a roxa e a verde, a posicao e' encerrada a   |
//| mercado.                                                         |
//|                                                                  |
//| Saida por esticada: o "afastamento" e' (fechamento - roxa) no    |
//| sentido da operacao, em ATR, medido a cada fechamento de vela H1.|
//| Depois que ele passa de EsticadaArmaATR, a posicao e' encerrada a|
//| mercado quando o afastamento recua EsticadaRecuoATR em relacao ao|
//| maior afastamento ja' visto na operacao (preco foi longe demais  |
//| da roxa e esta voltando).                                        |
//|                                                                  |
//| Saida por break-even a mercado (v2.05; BreakEvenMinutos > 0, vem  |
//| DESLIGADA: 0 = comportamento da v2.04, inalterado): a cada abertura|
//| de barra M1, a partir de BreakEvenMinutos minutos depois da      |
//| abertura da H1 de entrada, se o resultado flutuante (bid na compra,|
//| ask na venda, contra o preco de entrada) for <= BreakEvenColchaoPts|
//| pontos a favor, fecha a mercado (PositionClose, sem stop pendente).|
//| No vencimento, posicao contra ou colada no zero fecha; mais de     |
//| colchao pontos a favor segue, e fecha a mercado na 1a M1 em que a  |
//| vantagem volta a ser <= colchao. Convive com stop da roxa, canal e |
//| esticada (a checagem de BE vem depois deles, na mesma barra).      |
//| Por que existe: no simulador M1 em WIN@D (60 meses) a regra com    |
//| colchao de 7 pts melhora liquido e DD (WF 2022-26: +833, DD -983), |
//| mas o IC por dias cruza zero, o nulo de saida aleatoria nao e'     |
//| rejeitado (p~0,10-0,14), NAO replicou em WSP@D (-646) e no replay  |
//| de ticks reais WINV26 (12/08-01/10) ficou -441. Ligue so' para     |
//| teste (BreakEvenMinutos=15, BreakEvenColchaoPts=7).                |
//|                                                                  |
//| Uma posicao por vez. Entradas ate' MinutosSemEntrada antes do fim|
//| do pregao; zera tudo a mercado MinutosZerar antes do fim.        |
//|                                                                  |
//| Origem dos parametros: simulacao M1 em WINV26 (set/2026 refino,  |
//| ago/2026 validacao). Custos (5 pts/op + 2 pts de slippage no     |
//| stop) valem so' naquela simulacao; aqui quem cobra e' a corretora|
//| ou o Testador.                                                   |
//+------------------------------------------------------------------+
//+--------------------------------------------------------------------+
//| v2.07 (2026-10-06, frente Z8): REGRA NaoOperarGapATR -- nao abre   |
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
//| Neste robo (Z7, total 2022-2026 com custo): -R$145 (2024 +7, 2026  |
//| -152). Versao anterior em Win_c1_v2_06.mq5.bak.                    |
//+--------------------------------------------------------------------+
#property copyright "win"
#property version   "2.07"
#property description "Win_c1 v2.07: Win com break-even a mercado (15 min, colchao 7 pts); H1 com filtro H3 + NaoOperarGapATR"
#property strict

#include <Trade\Trade.mqh>

// Tempos graficos FIXOS no codigo (sem input, para o Testador nao trocar): o EA calcula tudo em H1, com o filtro
// superior em H3, qualquer que seja o tempo do grafico em que for colocado.
const ENUM_TIMEFRAMES TempoGrafico = PERIOD_H1;
const ENUM_TIMEFRAMES TempoFiltro  = PERIOD_H3;

input int    Periodo             = 34;     // Periodo da WMA (roxa) e da SMMA (verde)
input double KFechamentoATR      = 0.6;    // Stop na roxa deslocado K x ATR para o lado do preco
input int    PeriodoATR          = 14;     // Periodo do ATR (media simples do True Range, H1)
input int    IdadeMax            = 9;      // So' entra ate' a N-esima vela seguida do mesmo lado da roxa (0 = sem filtro)
input double DistMinPontos       = 15.0;   // Ponta do pavio a no minimo N pontos da roxa
input double GapMaxATR           = 3.0;    // So' entra se |roxa-verde| / ATR < N (0 = sem filtro)
input double ExtRoxaMinATR       = 1.4;    // Extremo da vela (maxima na compra, minima na venda) a no minimo N x ATR da roxa (0 = sem filtro)
input double DistVerdeMinATR     = 1.2;    // Fechamento a no minimo N x ATR da verde, no sentido da operacao (0 = sem filtro)
input double EsticadaArmaATR      = 2.5;    // Arma a saida por esticada quando o afastamento da roxa passa de N x ATR (0 = sem esta saida)
input double EsticadaRecuoATR    = 0.75;   // Armada, sai quando o afastamento recua N x ATR do maior afastamento da operacao
input int    AlinharM15          = 1;      // 1 = exige H3 alinhado, 0 = desliga (ultima H3 fechada: close do lado do sinal da roxa H3 e verde H3 do lado oposto)
input bool   DebugFiltros        = false;  // Imprime no Diario os valores do filtro H3 a cada sinal que passou os demais filtros
input int    JanelaToques        = 20;     // Janela, em velas H1 fechadas, para contar os toques na roxa (0 = sem filtro)
input int    ToquesMax           = 14;     // Maximo de velas da janela que tocaram a roxa para poder entrar
input string HorasSemEntrada     = "11,15,16,17"; // Horas cheias do servidor (0-23, separadas por virgula) em que NAO abre operacao; vazio = sem filtro
input int    HoraFimPregao       = 18;     // Hora do fim do pregao (horario do servidor do MT5)
input int    MinutoFimPregao     = 0;      // Minuto do fim do pregao
input int    MinutosSemEntrada   = 30;     // Para de abrir operacao tantos minutos antes do fim
input int    MinutosZerar        = 10;     // Fecha a posicao a mercado tantos minutos antes do fim
input double Lote                = 1.0;    // Contratos por operacao
input ulong  MagicNumber         = 80080002; // Codigo que identifica as ordens deste robo
input int    BreakEvenMinutos    = 15;     // Break-even a mercado: minutos apos a abertura da H1 de entrada (0 = desligado; 15 = a regra testada)
input double BreakEvenColchaoPts = 7.0;    // Break-even: fecha a mercado se o resultado flutuante for <= N pontos a favor (7 = custo 5 + slippage 2)
input double NaoOperarGapATR     = 1.0;  // Z8: nao abre posicao nova no dia em que |abertura - fechamento anterior| >= N x ATR14 D1 (0 = desliga)

CTrade trade;

int      g_h_smma = INVALID_HANDLE;
int      g_h_wma = INVALID_HANDLE;
int      g_h_smma15 = INVALID_HANDLE;  // SMMA34 (verde) do H3
int      g_h_wma15 = INVALID_HANDLE;   // LWMA34 (roxa) do H3
datetime g_ultima_barra = 0;
datetime g_ultima_m1 = 0;       // ultima barra M1 ja' checada pelo break-even
bool     g_hora_bloqueada[24];  // horas (do servidor) sem entrada nova

// estado da saida por esticada (da posicao aberta)
ulong    g_ticket_pos = 0;
bool     g_esticada_armada = false;
double   g_pico_afastamento = -1.0e9;

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
      PrintFormat("AVISO: grafico em %s, mas o EA calcula tudo em %s com filtro %s (fixo no codigo).",
                  EnumToString((ENUM_TIMEFRAMES)Period()), EnumToString(TempoGrafico), EnumToString(TempoFiltro));
   if(Periodo < 2 || PeriodoATR < 1 || KFechamentoATR < 0.0)
   {
      Print("ERRO: parametros invalidos (Periodo >= 2, PeriodoATR >= 1, KFechamentoATR >= 0).");
      return INIT_PARAMETERS_INCORRECT;
   }

   ArrayInitialize(g_hora_bloqueada, false);
   string horas[];
   // O Testador, em otimizacao, nao repassa parametros de texto aos agentes e entrega "(null)": nesse caso vale o padrao.
   string horas_txt = HorasSemEntrada;
   if(horas_txt == "(null)") horas_txt = "11,15,16,17";
   int n_horas = StringSplit(horas_txt, ',', horas);
   for(int i = 0; i < n_horas; i++)
   {
      StringTrimLeft(horas[i]); StringTrimRight(horas[i]);
      if(horas[i] == "") continue;
      int h = (int)StringToInteger(horas[i]);
      if(h < 0 || h > 23 || (h == 0 && horas[i] != "0"))
      {
         PrintFormat("ERRO: HorasSemEntrada invalida ('%s'): use horas de 0 a 23 separadas por virgula.", horas_txt);
         return INIT_PARAMETERS_INCORRECT;
      }
      g_hora_bloqueada[h] = true;
   }

   g_h_smma = iMA(_Symbol, TempoGrafico, Periodo, 0, MODE_SMMA, PRICE_CLOSE);
   g_h_wma = iMA(_Symbol, TempoGrafico, Periodo, 0, MODE_LWMA, PRICE_CLOSE);
   if(g_h_smma == INVALID_HANDLE || g_h_wma == INVALID_HANDLE)
      return INIT_FAILED;

   // handles do H3 so' sao criados quando precisam ser lidos (filtro ligado ou debug)
   if(AlinharM15 != 0 || DebugFiltros)
   {
      g_h_smma15 = iMA(_Symbol, TempoFiltro, Periodo, 0, MODE_SMMA, PRICE_CLOSE);
      g_h_wma15 = iMA(_Symbol, TempoFiltro, Periodo, 0, MODE_LWMA, PRICE_CLOSE);
      if(g_h_smma15 == INVALID_HANDLE || g_h_wma15 == INVALID_HANDLE)
         return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(g_h_smma);
   IndicatorRelease(g_h_wma);
   if(g_h_smma15 != INVALID_HANDLE) IndicatorRelease(g_h_smma15);
   if(g_h_wma15 != INVALID_HANDLE) IndicatorRelease(g_h_wma15);
}

//+------------------------------------------------------------------+
// So para o Testador: criterio "Custom max" = lucro / drawdown medido nos
// trades FECHADOS. O DD de equidade do Testador (~R$34k em todo passe) e'
// artefato de marcacao da posicao aberta e nao serve para ranquear.
double   g_eq_max = 0.0;
datetime g_eq_max_t = 0;
string   g_eq_max_info = "";

double OnTester()
{
   PrintFormat("OnTester: pico de equidade %.2f em %s | %s", g_eq_max, TimeToString(g_eq_max_t, TIME_DATE|TIME_SECONDS), g_eq_max_info);
   HistorySelect(0, TimeCurrent());
   double acum = 0.0, pico = 0.0, dd = 0.0;
   for(int k = 0; k < HistoryDealsTotal(); k++)
   {
      ulong tk = HistoryDealGetTicket(k);
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != (long)MagicNumber) continue;
      if(HistoryDealGetInteger(tk, DEAL_ENTRY) == DEAL_ENTRY_IN) continue;
      acum += HistoryDealGetDouble(tk, DEAL_PROFIT) + HistoryDealGetDouble(tk, DEAL_COMMISSION)
            + HistoryDealGetDouble(tk, DEAL_SWAP) + HistoryDealGetDouble(tk, DEAL_FEE);
      if(acum > pico) pico = acum;
      if(pico - acum > dd) dd = pico - acum;
   }
   PrintFormat("OnTester: liquido=%.2f ddFechados=%.2f ddEquidadeTester=%.2f", acum, dd,
               TesterStatistics(STAT_EQUITY_DD));
   return acum / MathMax(dd, 20.0);
}

//+------------------------------------------------------------------+
double Arredonda(double preco)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   return NormalizeDouble(MathRound(preco / tick) * tick, _Digits);
}

int MinutoDoDia(datetime t)
{
   MqlDateTime d;
   TimeToStruct(t, d);
   return d.hour * 60 + d.min;
}

bool SelecionaPosicao()
{
   if(!PositionSelect(_Symbol)) return false;
   return PositionGetInteger(POSITION_MAGIC) == (long)MagicNumber;
}

//+------------------------------------------------------------------+
// Roxa, verde e fechamento da ultima vela FECHADA (indice 1)
bool LeMedias(double &wma, double &smma, double &close1)
{
   double w[1], s[1], c[1];
   if(CopyBuffer(g_h_wma, 0, 1, 1, w) != 1) return false;
   if(CopyBuffer(g_h_smma, 0, 1, 1, s) != 1) return false;
   if(CopyClose(_Symbol, TempoGrafico, 1, 1, c) != 1) return false;
   wma = w[0]; smma = s[0]; close1 = c[0];
   return true;
}

// ATR: media simples do True Range das PeriodoATR ultimas velas fechadas
bool LeATR(double &atr, int shift = 1)
{
   int n = PeriodoATR + 1;  // +1: o True Range da vela mais antiga precisa do fechamento anterior
   double hi[], lo[], cl[];
   ArraySetAsSeries(hi, true); ArraySetAsSeries(lo, true); ArraySetAsSeries(cl, true);
   if(CopyHigh(_Symbol, TempoGrafico, shift, n, hi) != n) return false;
   if(CopyLow(_Symbol, TempoGrafico, shift, n, lo) != n) return false;
   if(CopyClose(_Symbol, TempoGrafico, shift, n, cl) != n) return false;
   double soma = 0.0;
   for(int i = 0; i < PeriodoATR; i++)
      soma += MathMax(hi[i] - lo[i], MathMax(MathAbs(hi[i] - cl[i + 1]), MathAbs(lo[i] - cl[i + 1])));
   atr = soma / PeriodoATR;
   return atr > 0.0;
}

// Afastamento do fechamento da vela fechada `shift` em relacao a roxa, no sentido da
// operacao, em ATR. Atualiza o pico e arma a saida por esticada.
bool AcumulaAfastamento(bool compra, int shift, double &afast)
{
   double w[1], c[1], atr;
   if(CopyBuffer(g_h_wma, 0, shift, 1, w) != 1) return false;
   if(CopyClose(_Symbol, TempoGrafico, shift, 1, c) != 1) return false;
   if(!LeATR(atr, shift)) return false;
   afast = (compra ? 1.0 : -1.0) * (c[0] - w[0]) / atr;
   if(afast >= EsticadaArmaATR) g_esticada_armada = true;
   g_pico_afastamento = MathMax(g_pico_afastamento, afast);
   return true;
}

// +1 compra, -1 venda, 0 nada -- usando a vela FECHADA no indice 1
int Sinal()
{
   double smma[1], wma[1], hi[1], lo[1];
   if(CopyBuffer(g_h_smma, 0, 1, 1, smma) != 1) return 0;
   if(CopyBuffer(g_h_wma, 0, 1, 1, wma) != 1) return 0;
   if(CopyHigh(_Symbol, TempoGrafico, 1, 1, hi) != 1) return 0;
   if(CopyLow(_Symbol, TempoGrafico, 1, 1, lo) != 1) return 0;
   // vela INTEIRA (pavio incluido) fora da roxa e verde do lado oposto da roxa
   if(lo[0] > wma[0] && smma[0] < wma[0]) return 1;
   if(hi[0] < wma[0] && smma[0] > wma[0]) return -1;
   return 0;
}

// Quantas velas fechadas seguidas (contando a do sinal) terminaram do lado do sinal da roxa
int IdadeDaOnda(int sinal)
{
   int n = IdadeMax + 1;  // basta saber se passa de IdadeMax
   double w[], c[];
   ArraySetAsSeries(w, true); ArraySetAsSeries(c, true);
   if(CopyBuffer(g_h_wma, 0, 1, n, w) != n) return n;
   if(CopyClose(_Symbol, TempoGrafico, 1, n, c) != n) return n;
   int idade = 0;
   for(int i = 0; i < n; i++)
   {
      int lado = c[i] > w[i] ? 1 : (c[i] < w[i] ? -1 : 0);
      if(lado != sinal) break;
      idade++;
   }
   return idade;
}

// Quantas das ultimas `janela` velas fechadas NAO ficaram inteiras do lado do sinal da roxa
int ToquesNaRoxa(int sinal, int janela)
{
   double w[], hi[], lo[];
   ArraySetAsSeries(w, true); ArraySetAsSeries(hi, true); ArraySetAsSeries(lo, true);
   if(CopyBuffer(g_h_wma, 0, 1, janela, w) != janela) return janela;
   if(CopyHigh(_Symbol, TempoGrafico, 1, janela, hi) != janela) return janela;
   if(CopyLow(_Symbol, TempoGrafico, 1, janela, lo) != janela) return janela;
   int toques = 0;
   for(int i = 0; i < janela; i++)
      if(sinal > 0 ? lo[i] <= w[i] : hi[i] >= w[i]) toques++;
   return toques;
}

// Filtros de entrada sobre a vela do sinal
bool FiltrosAprovam(int sinal, double wma, double smma, double close1, double atr)
{
   double hi[1], lo[1];
   if(CopyHigh(_Symbol, TempoGrafico, 1, 1, hi) != 1) return false;
   if(CopyLow(_Symbol, TempoGrafico, 1, 1, lo) != 1) return false;

   if(IdadeMax > 0 && IdadeDaOnda(sinal) > IdadeMax) return false;

   if(JanelaToques > 0 && ToquesNaRoxa(sinal, JanelaToques) > ToquesMax) return false;

   double dist = sinal > 0 ? lo[0] - wma : wma - hi[0];  // ponta do pavio mais proxima da roxa
   if(dist < DistMinPontos) return false;

   if(GapMaxATR > 0.0 && MathAbs(wma - smma) / atr >= GapMaxATR) return false;

   double ext = sinal > 0 ? hi[0] - wma : wma - lo[0];  // extremo da vela ate' a roxa
   if(ExtRoxaMinATR > 0.0 && ext / atr < ExtRoxaMinATR) return false;

   if(DistVerdeMinATR > 0.0 && sinal * (close1 - smma) / atr < DistVerdeMinATR) return false;
   return true;
}

//+------------------------------------------------------------------+
// Filtro superior (H3) alinhado, lido na abertura da H1 `t_entrada` (abertura da H1 seguinte ao sinal).
// A barra H3 usada e' a ultima JA FECHADA nesse instante: a de abertura <= t_entrada - 3h.
//   H1 abre 12:00 -> alvo 09:00 -> barra H3 09:00 (fechou 12:00)       [recem-fechada: usa]
//   H1 abre 13:00 -> alvo 10:00 -> barra H3 09:00 (fechou 12:00)       [H3 de 12:00 em formacao: nao usa]
//   H1 abre 10:00 -> alvo 07:00 -> sem barra nesse horario: a ultima anterior (pregao da vespera)
// iBarShift(exact=false) devolve a barra que CONTEM o instante alvo (ou a ultima antes dele); a checagem
// t15 + PeriodSeconds(TempoFiltro) <= t_entrada garante que ela ja' fechou (nunca usa barra em formacao).
bool LeM15(datetime t_entrada, double &wma15, double &smma15, double &close15)
{
   int sh = iBarShift(_Symbol, TempoFiltro, t_entrada - PeriodSeconds(TempoFiltro), false);
   if(sh < 0) return false;
   datetime t15 = iTime(_Symbol, TempoFiltro, sh);
   if(t15 == 0 || t15 + PeriodSeconds(TempoFiltro) > t_entrada) return false;
   double w[1], s[1], c[1];
   if(CopyBuffer(g_h_wma15, 0, sh, 1, w) != 1) return false;    // -1 = indicador ainda nao calculado
   if(CopyBuffer(g_h_smma15, 0, sh, 1, s) != 1) return false;
   if(CopyClose(_Symbol, TempoFiltro, sh, 1, c) != 1) return false;
   if(w[0] == EMPTY_VALUE || s[0] == EMPTY_VALUE) return false;
   wma15 = w[0]; smma15 = s[0]; close15 = c[0];
   return true;
}

// Filtro superior (H3). Roda so' na vela nova com sinal que ja' passou os demais filtros.
bool FiltrosNovosAprovam(int sinal, datetime t_entrada)
{
   if(AlinharM15 == 0 && !DebugFiltros) return true;

   double w15 = 0, s15 = 0, c15 = 0;
   bool m15_lido = LeM15(t_entrada, w15, s15, c15);
   bool m15_ok = m15_lido
              && (sinal > 0 ? (c15 > w15 && s15 < w15) : (c15 < w15 && s15 > w15));
   bool aprova = AlinharM15 == 0 || m15_ok;

   if(DebugFiltros)
      PrintFormat("FILTROS %s | %s | H3=%s | roxa15=%s | verde15=%s | close15=%s | %s",
                  TimeToString(t_entrada, TIME_DATE | TIME_MINUTES), sinal > 0 ? "COMPRA" : "VENDA",
                  m15_lido ? (m15_ok ? "sim" : "nao") : "sem_dado",
                  m15_lido ? StringFormat("%.1f", w15) : "-", m15_lido ? StringFormat("%.1f", s15) : "-",
                  m15_lido ? StringFormat("%.0f", c15) : "-",
                  aprova ? "APROVA" : "REJEITA");
   return aprova;
}

//+------------------------------------------------------------------+
// Cotacao valida: simbolos sem livro (ex.: WIN$ continuo no testador) vem com bid/ask = 0 e abririam posicao a preco 0.
bool CotacaoValida()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   return bid > 0.0 && ask > 0.0 && ask >= bid;
}

void Entra(int sinal, double wma, double atr)
{
   if(!CotacaoValida())
   {
      PrintFormat("Entrada ignorada: %s sem cotacao (bid/ask) valida -- use o contrato real (ex.: WINV26), nao a serie continua", _Symbol);
      return;
   }
   double preco = sinal > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double sl = Arredonda(wma + sinal * KFechamentoATR * atr);

   // Preco ja' dentro da faixa do stop (perto demais da roxa): o stop ficaria do lado errado do preco.
   if(sinal > 0 ? sl > preco - tick : sl < preco + tick)
   {
      PrintFormat("Entrada ignorada: stop %.0f nao fica abaixo/acima do preco %.0f", sl, preco);
      return;
   }

   bool ok = sinal > 0 ? trade.Buy(Lote,  _Symbol, 0.0, sl, 0.0, "win")
                       : trade.Sell(Lote, _Symbol, 0.0, sl, 0.0, "win");
   if(!ok)
      PrintFormat("ERRO entrada: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

// A cada fechamento de vela H1 com posicao aberta: encerra se a vela fechou entre
// a roxa e a verde; senao recoloca o stop na roxa +/- K x ATR. O estado e' recalculado
// do zero a cada vela, entao um reinicio do EA no meio da posicao nao perde nada.
void AtualizaPosicao()
{
   double wma, smma, close1, atr;
   if(!LeMedias(wma, smma, close1) || !LeATR(atr)) return;

   if(close1 > MathMin(wma, smma) && close1 < MathMax(wma, smma))
   {
      if(!trade.PositionClose(_Symbol))
         PrintFormat("ERRO fechar no canal: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return;
   }

   bool compra = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   if(!CotacaoValida()) return;  // sem cotacao nao ha' como decidir o stop: tenta na proxima vela

   if(EsticadaArmaATR > 0.0)
   {
      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      if(ticket != g_ticket_pos)
      {
         // posicao nova (ou EA reiniciado no meio dela): reconstroi o pico das velas desde a entrada
         g_ticket_pos = ticket;
         g_esticada_armada = false;
         g_pico_afastamento = -1.0e9;
         double ignora;
         int desde = iBarShift(_Symbol, TempoGrafico, (datetime)PositionGetInteger(POSITION_TIME));
         for(int sh = desde; sh >= 2; sh--)
            AcumulaAfastamento(compra, sh, ignora);
      }
      double afast;
      if(AcumulaAfastamento(compra, 1, afast) && g_esticada_armada && afast <= g_pico_afastamento - EsticadaRecuoATR)
      {
         if(!trade.PositionClose(_Symbol))
            PrintFormat("ERRO fechar por esticada: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
         return;
      }
   }

   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double novo = Arredonda(wma + (compra ? 1.0 : -1.0) * KFechamentoATR * atr);
   double preco = compra ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   // O preco ja' passou do novo stop: ele nao pode ser colocado, sai a mercado.
   if(compra ? novo > preco - tick : novo < preco + tick)
   {
      if(!trade.PositionClose(_Symbol))
         PrintFormat("ERRO fechar stop alcancado: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return;
   }

   double sl = PositionGetDouble(POSITION_SL);
   if(MathAbs(novo - sl) > tick / 2.0 && !trade.PositionModify(_Symbol, novo, 0.0))
      PrintFormat("ERRO mover stop: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
// Break-even a mercado (v2.05). Roda no PRIMEIRO tick de cada barra M1 (equivale a checar na abertura do minuto,
// como o simulador M1) e so' com posicao selecionada. Prazo = abertura da H1 de entrada + BreakEvenMinutos:
// a decisao usa so' o preco atual (bid na compra / ask na venda = preco de saida), sem olhar a frente. Sem estado
// alem da ultima M1 checada: reiniciar o EA no meio da posicao nao perde nada.
void VerificaBreakEven()
{
   if(BreakEvenMinutos <= 0) return;
   datetime m1 = iTime(_Symbol, PERIOD_M1, 0);
   if(m1 == g_ultima_m1) return;
   g_ultima_m1 = m1;
   if(!CotacaoValida()) return;

   datetime t_ent = iTime(_Symbol, TempoGrafico, iBarShift(_Symbol, TempoGrafico, (datetime)PositionGetInteger(POSITION_TIME)));
   if(m1 < t_ent + BreakEvenMinutos * 60) return;

   bool compra = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   double saida = compra ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double fl = (compra ? 1.0 : -1.0) * (saida - PositionGetDouble(POSITION_PRICE_OPEN));  // pontos a favor
   if(fl > BreakEvenColchaoPts) return;
   PrintFormat("Break-even: %s %.0f pts a favor <= %.1f (M1 %s) -> fecha a mercado", compra ? "compra" : "venda", fl,
               BreakEvenColchaoPts, TimeToString(m1, TIME_DATE | TIME_MINUTES));
   if(!trade.PositionClose(_Symbol))
      PrintFormat("ERRO fechar break-even: retcode=%u (%s) -- tenta de novo na proxima M1", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
void OnTick()
{
   GapDiaBloqueado();   // Z8: o 1o tick do pregao decide se o dia esta' bloqueado pelo gap (NaoOperarGapATR)
   if(MQLInfoInteger(MQL_TESTER))   // diagnostico do pico de equidade (so Testador)
   {
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      if(eq > g_eq_max)
      {
         g_eq_max = eq; g_eq_max_t = TimeCurrent();
         g_eq_max_info = StringFormat("saldo=%.2f lucroFlutuante=%.2f vol=%.0f abertura=%.1f atual=%.1f bid=%.1f ask=%.1f",
            AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_PROFIT),
            PositionSelect(_Symbol) ? PositionGetDouble(POSITION_VOLUME) : 0.0,
            PositionSelect(_Symbol) ? PositionGetDouble(POSITION_PRICE_OPEN) : 0.0,
            PositionSelect(_Symbol) ? PositionGetDouble(POSITION_PRICE_CURRENT) : 0.0,
            SymbolInfoDouble(_Symbol, SYMBOL_BID), SymbolInfoDouble(_Symbol, SYMBOL_ASK));
      }
   }
   int fim = HoraFimPregao * 60 + MinutoFimPregao;
   int agora = MinutoDoDia(TimeCurrent());

   bool tem_pos = SelecionaPosicao();

   if(tem_pos)
   {
      // posicao de OUTRO dia (EA ficou sem tick no fim do pregao) tambem zera
      bool de_outro_dia = (long)(TimeCurrent() / 86400) != (long)(PositionGetInteger(POSITION_TIME) / 86400);
      if(agora >= fim - MinutosZerar || de_outro_dia)
      {
         if(!trade.PositionClose(_Symbol))
            PrintFormat("ERRO zerar: retcode=%u (%s) -- tenta de novo no proximo tick", trade.ResultRetcode(), trade.ResultRetcodeDescription());
         return;
      }
   }

   datetime barra = iTime(_Symbol, TempoGrafico, 0);
   bool nova_barra = (barra != g_ultima_barra);
   g_ultima_barra = barra;

   if(tem_pos)
   {
      if(nova_barra) AtualizaPosicao();                       // stop/canal/esticada primeiro, como no simulador
      if(BreakEvenMinutos > 0 && SelecionaPosicao()) VerificaBreakEven();
      return;
   }
   if(!nova_barra) return;

   // Sinal da vela fechada de OUTRO dia (primeira barra do pregao) e' sinal velho: nao opera.
   if((long)(iTime(_Symbol, TempoGrafico, 1) / 86400) != (long)(barra / 86400)) return;

   int sinal = Sinal();
   if(sinal == 0) return;
   if(agora >= fim - MinutosSemEntrada) return;
   if(g_hora_bloqueada[MinutoDoDia(barra) / 60]) return;  // hora da vela que abriu: igual ao backtest
   if(PositionSelect(_Symbol)) return;  // posicao de outro robo/magic no simbolo: nao mexe

   double wma, smma, close1, atr;
   if(!LeMedias(wma, smma, close1) || !LeATR(atr)) return;
   if(!FiltrosAprovam(sinal, wma, smma, close1, atr)) return;
   if(!FiltrosNovosAprovam(sinal, barra)) return;

   if(GapDiaBloqueado()) { PrintFormat("Entrada %s nao enviada: dia bloqueado pelo gap (NaoOperarGapATR)", sinal > 0 ? "COMPRA" : "VENDA"); return; }
   Entra(sinal, wma, atr);
}
//+------------------------------------------------------------------+
