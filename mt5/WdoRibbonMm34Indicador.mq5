//+------------------------------------------------------------------+
//| WdoRibbonMm34Indicador.mq5                                          |
//| Desenha as 4 MMs (SMA/EMA/SMMA/LWMA) usadas por WdoRibbonMm34.mq5,  |
//| calculadas SO' COM O FECHAMENTO DO PROPRIO PREGAO (reiniciadas toda |
//| abertura -- mesma regra do EA). Nao desenha nada antes da vela      |
//| `Periodo` do pregao -- e' o ponto em que o EA passa a ter ribbon    |
//| valido pra avaliar. So' visualizacao, nao manda ordem.               |
//|                                                                      |
//| 2026-09-29: a 1a tentativa desse calculo so'-do-dia usava time[]/    |
//| close[] recebidos como parametro do OnCalculate e nao aparecia (ou   |
//| aparecia errado) -- MQL5 tem ambiguidade documentada/confusa sobre   |
//| a ordem (serie ou nao) desses arrays por padrao, e forcar com        |
//| ArraySetAsSeries dos dois lados nao resolveu. A CORRECAO: ignora os  |
//| arrays recebidos por parametro e busca o proprio tempo/fechamento    |
//| via CopyTime/CopyClose em arrays LOCAIS recem-declaradas -- essas    |
//| nunca foram marcadas como serie, entao SEMPRE vem indice 0 = mais    |
//| antiga, sem depender de suposicao nenhuma sobre o default do MT5.    |
//+------------------------------------------------------------------+
#property copyright "wdo_ribbon_mm34"
#property version   "1.71"
#property strict
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

// Cores = as do template com_MM.tpl (MAs padrao do MT5, periodo 34): amarela=SMA, azul=EMA, verde=SMMA (lenta), roxa=LWMA (rapida).
#property indicator_label1  "SMA"
#property indicator_type1   DRAW_LINE
#property indicator_color1  C'255,215,0'
#property indicator_width1  2

#property indicator_label2  "EMA"
#property indicator_type2   DRAW_LINE
#property indicator_color2  C'0,0,255'
#property indicator_width2  2

#property indicator_label3  "SMMA"
#property indicator_type3   DRAW_LINE
#property indicator_color3  C'60,179,113'
#property indicator_width3  2

#property indicator_label4  "LWMA"
#property indicator_type4   DRAW_LINE
#property indicator_color4  C'218,138,214'
#property indicator_width4  2

input int Periodo = 34; // mesmo Periodo do EA WdoRibbonMm34

double BufSma[], BufEma[], BufSmma[], BufLwma[];
int    g_dia_idx[];  // quantas velas do pregao ja' fecharam ate' esta (1-based)

int OnInit()
{
   SetIndexBuffer(0, BufSma,  INDICATOR_DATA);
   SetIndexBuffer(1, BufEma,  INDICATOR_DATA);
   SetIndexBuffer(2, BufSmma, INDICATOR_DATA);
   SetIndexBuffer(3, BufLwma, INDICATOR_DATA);
   ArraySetAsSeries(BufSma,  false);
   ArraySetAsSeries(BufEma,  false);
   ArraySetAsSeries(BufSmma, false);
   ArraySetAsSeries(BufLwma, false);
   for(int p = 0; p < 4; p++)
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   int start = (prev_calculated > 1) ? prev_calculated - 1 : 0;
   ArrayResize(g_dia_idx, rates_total);

   // busca so' o trecho NOVO (+ Periodo barras de contexto pra tras, o
   // maximo que a janela da SMA/LWMA pode precisar) em arrays LOCAIS
   // (nunca marcadas como serie, garante indice 0 = mais antiga do
   // trecho). Pedir rates_total inteiro a cada chamada (como na 1a
   // tentativa) reprocessava o historico todo em TODA barra nova --
   // e' o que deixava o Tester lento num backtest de meses.
   int desde = (start > Periodo) ? start - Periodo : 0;
   int qtd = rates_total - desde;
   datetime tempos[];
   double   fechamentos[];
   if(CopyTime(_Symbol, _Period, 0, qtd, tempos) != qtd) return(prev_calculated);
   if(CopyClose(_Symbol, _Period, 0, qtd, fechamentos) != qtd) return(prev_calculated);
   // tempos[k]/fechamentos[k] corresponde ao indice do grafico (desde + k)

   for(int i = start; i < rates_total; i++)
   {
      int k = i - desde;
      if(i == 0)
      {
         g_dia_idx[i] = 1;
      }
      else
      {
         MqlDateTime a, b;
         TimeToStruct(tempos[k],     a);
         TimeToStruct(tempos[k - 1], b);
         bool novo_dia = (a.year != b.year || a.mon != b.mon || a.day != b.day);
         g_dia_idx[i] = novo_dia ? 1 : g_dia_idx[i - 1] + 1;
      }

      if(g_dia_idx[i] < Periodo)
      {
         BufSma[i] = EMPTY_VALUE; BufEma[i] = EMPTY_VALUE;
         BufSmma[i] = EMPTY_VALUE; BufLwma[i] = EMPTY_VALUE;
         continue;
      }

      double soma = 0.0, soma_pond = 0.0, soma_pesos = 0.0;
      for(int w = 1; w <= Periodo; w++)
      {
         double c = fechamentos[k - Periodo + w];
         soma       += c;
         soma_pond  += c * w;
         soma_pesos += w;
      }
      BufSma[i]  = soma / Periodo;
      BufLwma[i] = soma_pond / soma_pesos;

      if(g_dia_idx[i] == Periodo)
      {
         BufEma[i]  = BufSma[i];
         BufSmma[i] = BufSma[i];
      }
      else
      {
         double kk = 2.0 / (Periodo + 1);
         BufEma[i]  = fechamentos[k] * kk + BufEma[i - 1] * (1.0 - kk);
         BufSmma[i] = (BufSmma[i - 1] * (Periodo - 1) + fechamentos[k]) / Periodo;
      }
   }
   return(rates_total);
}
//+------------------------------------------------------------------+
