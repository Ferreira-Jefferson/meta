//+------------------------------------------------------------------+
//| WinF2.mq5                                                           |
//| Expert Advisor para o MINI INDICE (WIN). Estrategia "F2": rompimento |
//| por afastamento no grafico de 15 minutos.                            |
//|                                                                      |
//| Sinal (vela M15 FECHADA): fechamento ACIMA de LWMA(34) + 3 x ATR(14) |
//| = COMPRA; fechamento ABAIXO de LWMA(34) - 3 x ATR(14) = VENDA. So'   |
//| vale o sinal NOVO: a vela anterior nao podia estar no mesmo estado.  |
//| Entra a mercado na abertura da vela seguinte. Stop e alvo FIXOS (sem |
//| trailing, sem alvo dinamico): padrao 300 / 900 pontos (1:3).         |
//|                                                                      |
//| O ATR e' o de Wilder (media exponencial recursiva), calculado aqui,  |
//| porque e' o do simulador onde a regra foi medida; o iATR do MT5 e'   |
//| media simples e daria outro valor.                                   |
//|                                                                      |
//| Uma posicao por vez. Sinal que chega com posicao aberta e' perdido,  |
//| nao fica esperando. Sem entrada nos ultimos                          |
//| MinutosSemEntrada do pregao; zera tudo a mercado MinutosZerar antes  |
//| do fim. Sinal de uma vela de dia anterior nunca entra.               |
//|                                                                      |
//| Medida em WIN@D de 2021-10 a 2026-09. NAO e' garantia. No periodo    |
//| 2025-04..2026-09, com 1 contrato e custos de 5 pts + 2 de slippage:  |
//| 300/600 rendeu ~R$ +6 por operacao (liquido ~R$ +1.800, drawdown     |
//| ~R$ 1.360); 200/600 rendeu ~R$ -0,30 (liquido ~R$ -93). Em 1.040     |
//| sinais (60 meses) o 300 supera o 200 em ~R$ 4 por operacao, IC95     |
//| [+0,8; +7,2]. O IC da propria F2 inclui zero, e setembro/2026 deu    |
//| perda nas duas geometrias. Custos reais e deslize pioram isso; aqui  |
//| quem cobra e' a corretora.                                           |
//| Alvo 900 (1:3), 60 meses: ~R$ +9,1 por operacao contra +7,2 do 600  |
//| (IC95 da diferenca [-1,5; +4,8], cruza zero); acerto cai p/ ~36%.    |
//| SaidaPorM5 (desligada): zera quando uma vela M5 fecha contra a LWMA  |
//| M5; simulador: +9 R$/op sobre o 300/900 fixo, IC95 [+6,2; +12,5],    |
//| positiva nos 3 periodos, mas some com 5 min de atraso.               |
//+------------------------------------------------------------------+
#property copyright "win_f2"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input int    PeriodoMedia        = 34;     // Periodo da LWMA (media ponderada linear) do fechamento
input int    PeriodoATR          = 14;     // Periodo do ATR de Wilder
input double MultiplicadorATR    = 3.0;    // Quantos ATR o fechamento precisa estar afastado da LWMA
input double StopPontos          = 300.0;  // Stop fixo, em pontos
input double AlvoPontos          = 900.0;  // Alvo fixo, em pontos
input int    HoraInicioPregao    = 9;      // Nao abre operacao antes desta hora (horario do servidor do MT5)
input int    HoraFimPregao       = 18;     // Hora do fim do pregao (horario do servidor do MT5)
input int    MinutoFimPregao     = 0;      // Minuto do fim do pregao
input int    MinutosSemEntrada   = 30;     // Para de abrir operacao tantos minutos antes do fim
input int    MinutosZerar        = 10;     // Fecha a posicao a mercado tantos minutos antes do fim
input bool   SaidaPorM5          = false;  // Sai a mercado quando uma vela M5 FECHA do lado contrario da LWMA M5 (mede +9 R$/op no simulador; exige execucao imediata)
input int    PeriodoMediaSaida   = 34;     // Periodo da LWMA do M5 usada nessa saida
input double Lote                = 1.0;    // Contratos por operacao
input ulong  MagicNumber         = 80080002; // Codigo que identifica as ordens deste robo (diferente do robo Win)
#define TF         PERIOD_M15
#define BARRAS_ATR 700   // historico para o ATR de Wilder convergir (o peso do inicio cai a (13/14)^700 ~ 0)

CTrade   trade;
int      g_h_wma = INVALID_HANDLE;
int      g_h_wma_m5 = INVALID_HANDLE;
datetime g_ultima_barra = 0;
datetime g_ultima_barra_m5 = 0;
int      g_falhas_protecao = 0; // ticks seguidos em que nao foi possivel colocar stop/alvo na posicao

//+------------------------------------------------------------------+
int OnInit()
{
   if(Period() != PERIOD_M15)
      Print("AVISO: a estrategia usa velas de 15 minutos; o grafico pode ser qualquer um, mas o normal e' M15.");

   g_h_wma = iMA(_Symbol, TF, PeriodoMedia, 0, MODE_LWMA, PRICE_CLOSE);
   if(g_h_wma == INVALID_HANDLE)
      return INIT_FAILED;

   if(SaidaPorM5)
   {
      g_h_wma_m5 = iMA(_Symbol, PERIOD_M5, PeriodoMediaSaida, 0, MODE_LWMA, PRICE_CLOSE);
      if(g_h_wma_m5 == INVALID_HANDLE)
         return INIT_FAILED;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(g_h_wma);
   if(g_h_wma_m5 != INVALID_HANDLE) IndicatorRelease(g_h_wma_m5);
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
// Estado de uma vela fechada: +1 acima da banda de cima, -1 abaixo da de baixo, 0 dentro.
int Estado(double fechamento, double lwma, double atr)
{
   if(fechamento > lwma + MultiplicadorATR * atr) return 1;
   if(fechamento < lwma - MultiplicadorATR * atr) return -1;
   return 0;
}

// Ultimas BARRAS_ATR velas M15: ATR de Wilder (semente = 1o true range, como o simulador) e os
// fechamentos das duas ultimas velas FECHADAS (indices 1 e 2). Devolve false se faltar dado.
bool LeVelas(double &atr1, double &atr2, double &c1, double &c2, datetime &t1, datetime &t0)
{
   MqlRates r[];
   ArraySetAsSeries(r, false);   // r[0] = mais antiga, r[n-1] = vela em formacao
   int n = CopyRates(_Symbol, TF, 0, BARRAS_ATR, r);
   if(n < PeriodoATR + 5) return false;

   double a = 0.0, alfa = 1.0 / PeriodoATR;
   for(int i = 1; i < n - 1; i++)       // ate a vela fechada mais recente (n-2)
   {
      double tr = MathMax(r[i].high - r[i].low,
                  MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
      a = (i == 1) ? tr : a + alfa * (tr - a);
      if(i == n - 3) atr2 = a;          // vela de indice 2
   }
   atr1 = a;
   c1 = r[n - 2].close;
   c2 = r[n - 3].close;
   t1 = r[n - 2].time;
   t0 = r[n - 1].time;
   return true;
}

// +1 compra, -1 venda, 0 nada: sinal NOVO da vela fechada, e so' se ela e' do mesmo dia e contigua a vela atual
int Sinal()
{
   double atr1 = 0, atr2 = 0, c1, c2;
   datetime t1, t0;
   if(!LeVelas(atr1, atr2, c1, c2, t1, t0)) return 0;
   if(atr1 <= 0 || atr2 <= 0) return 0;

   // sinal de vela do dia anterior (ou com buraco) nao entra: no simulador, o sinal da ultima vela do dia nunca vira entrada
   MqlDateTime d1, d0;
   TimeToStruct(t1, d1);
   TimeToStruct(t0, d0);
   if(d1.day_of_year != d0.day_of_year || d1.year != d0.year) return 0;
   if(t0 - t1 != PeriodSeconds(TF)) return 0;

   double w[2];
   if(CopyBuffer(g_h_wma, 0, 1, 2, w) != 2) return 0;   // w[0] = vela indice 2, w[1] = vela indice 1

   int s1 = Estado(c1, w[1], atr1);
   int s2 = Estado(c2, w[0], atr2);
   if(s1 != 0 && s1 != s2) return s1;
   return 0;
}

//+------------------------------------------------------------------+
// Poe stop e alvo a StopPontos/AlvoPontos do preco REAL de abertura da posicao selecionada.
// Devolve true se a posicao ja tem exatamente isso ou se a corretora aceitou a alteracao.
bool ProtegePosicao()
{
   bool compra = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   double fill = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl_ok = Arredonda(compra ? fill - StopPontos : fill + StopPontos);
   double tp_ok = Arredonda(compra ? fill + AlvoPontos : fill - AlvoPontos);
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(MathAbs(PositionGetDouble(POSITION_SL) - sl_ok) < tick / 2.0 &&
      MathAbs(PositionGetDouble(POSITION_TP) - tp_ok) < tick / 2.0)
      return true;
   if(trade.PositionModify(_Symbol, sl_ok, tp_ok)) return true;
   PrintFormat("ERRO proteger posicao: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   return false;
}

// A ordem vai SEM stop e SEM alvo: o Ask/Bid lido no sinal pode estar defasado quando a ordem executa (latencia,
// abertura agitada) e o stop sairia do lado errado ou colado no preco. Logo apos o preenchimento, stop e alvo
// partem do preco real; se a corretora nao aceitar, a posicao e' fechada em vez de ficar sem protecao.
void Entra(int sinal)
{
   bool ok = sinal > 0 ? trade.Buy(Lote,  _Symbol, 0.0, 0.0, 0.0, "win_f2")
                       : trade.Sell(Lote, _Symbol, 0.0, 0.0, 0.0, "win_f2");
   if(!ok)
   {
      PrintFormat("ERRO entrada: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return;
   }
   if(!SelecionaPosicao()) return;
   for(int tentativa = 0; tentativa < 3; tentativa++)
   {
      if(ProtegePosicao()) return;
      if(!SelecionaPosicao()) return;   // ja foi encerrada por outro motivo
   }
   Print("ERRO: nao consegui colocar stop/alvo apos 3 tentativas -- fechando a posicao");
   if(!trade.PositionClose(_Symbol))
      PrintFormat("ERRO zerar: retcode=%u (%s) -- o OnTick tenta de novo", trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

// Saida opcional: na 1a cotacao de cada vela M5 nova, se a vela M5 que acabou de fechar (e que abriu depois da entrada)
// fechou do lado contrario da LWMA do M5 (compra: abaixo; venda: acima), zera a posicao a mercado.
void VerificaSaidaM5()
{
   datetime barra5 = iTime(_Symbol, PERIOD_M5, 0);
   if(barra5 == g_ultima_barra_m5) return;
   g_ultima_barra_m5 = barra5;

   if(!SelecionaPosicao()) return;
   datetime t_pos = (datetime)PositionGetInteger(POSITION_TIME);
   if(iTime(_Symbol, PERIOD_M5, 1) < t_pos - t_pos % PeriodSeconds(PERIOD_M5)) return;   // vela fechada ainda e' anterior a entrada

   double w[1];
   if(CopyBuffer(g_h_wma_m5, 0, 1, 1, w) != 1) return;
   double c = iClose(_Symbol, PERIOD_M5, 1);
   bool compra = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
   if((compra && c < w[0]) || (!compra && c > w[0]))
   {
      PrintFormat("Saida M5: fechamento %.0f contra a LWMA %.0f -- zerando", c, w[0]);
      if(!trade.PositionClose(_Symbol))
         PrintFormat("ERRO zerar: retcode=%u (%s)", trade.ResultRetcode(), trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
void OnTick()
{
   int fim = HoraFimPregao * 60 + MinutoFimPregao;
   int agora = MinutoDoDia(TimeCurrent());

   if(SelecionaPosicao())
   {
      // posicao de OUTRO dia (EA ficou sem tick no fim do pregao) tambem zera
      bool de_outro_dia = (long)(TimeCurrent() / 86400) != (long)(PositionGetInteger(POSITION_TIME) / 86400);
      if(agora >= fim - MinutosZerar || de_outro_dia)
      {
         if(!trade.PositionClose(_Symbol))
            PrintFormat("ERRO zerar: retcode=%u (%s) -- tenta de novo no proximo tick", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      }
      else if(ProtegePosicao())   // garante stop/alvo a StopPontos/AlvoPontos do preco real (reinicio do EA, falha na entrada)
         g_falhas_protecao = 0;
      else if(++g_falhas_protecao >= 3)   // nao consegue proteger (ex.: preco ja' passou do nivel): sai a mercado
      {
         Print("ERRO: posicao sem protecao apos 3 ticks -- fechando a mercado");
         if(trade.PositionClose(_Symbol)) g_falhas_protecao = 0;
      }
   }

   if(SaidaPorM5) VerificaSaidaM5();

   datetime barra = iTime(_Symbol, TF, 0);
   if(barra == g_ultima_barra) return;
   g_ultima_barra = barra;

   int sinal = Sinal();
   if(sinal == 0) return;

   int abre = MinutoDoDia(barra);   // minuto em que a vela seguinte ao sinal abre
   if(abre < HoraInicioPregao * 60) return;
   if(abre >= fim - MinutosSemEntrada || agora >= fim - MinutosSemEntrada) return;
   if(PositionSelect(_Symbol)) return;  // ja tem posicao (deste ou de outro robo): sinal perdido
   Entra(sinal);
}
//+------------------------------------------------------------------+
