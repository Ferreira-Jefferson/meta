//+------------------------------------------------------------------+
//| TempoDaBarra.mq5 — contagem regressiva para o fechamento da      |
//| barra: a do tempo gráfico do gráfico e uma de referência (M15).  |
//|                                                                  |
//| É indicador, não EA: fica no mesmo gráfico de qualquer EA, ou    |
//| sozinho. Não manda ordem nem lê a conta.                         |
//|                                                                  |
//| Relógio = hora do servidor (TimeTradeServer), atualizada a cada  |
//| segundo por timer, mesmo sem negócio. Barras até H4 fecham no    |
//| múltiplo do período contado da meia-noite do servidor (é assim   |
//| que o MT5 alinha M1..H4). D1 e acima fecham no fim do pregão:    |
//| sem contagem. A última barra do dia fecha no fim do pregão, que  |
//| pode vir antes do múltiplo do período.                           |
//+------------------------------------------------------------------+
#property copyright "TempoDaBarra"
#property version   "1.00"
#property description "Quanto falta para a barra fechar: a do gráfico e a de referência (M15)."
#property indicator_chart_window
#property indicator_plots 0

input ENUM_TIMEFRAMES  TempoReferencia = PERIOD_M15;          // 2ª contagem (Atual = desliga)
input ENUM_BASE_CORNER Canto           = CORNER_RIGHT_LOWER;  // Canto do gráfico
input int              TamanhoFonte    = 11;
input color            Cor             = clrSilver;
input color            CorAviso        = clrOrangeRed;
input int              SegundosAviso   = 30;                  // Últimos N segundos na cor de aviso

#define PREFIXO "TempoDaBarra_"

//--- Segundos até a barra do período fechar; -1 se o período não fecha pelo relógio (D1 e acima).
int SegundosFaltando(ENUM_TIMEFRAMES tf, datetime agora)
{
   int p = PeriodSeconds(tf);
   if(p <= 0 || p > 4 * 3600) return -1;
   return p - (int)(agora % p);
}

string Formata(int s)
{
   if(s >= 3600) return StringFormat("%d:%02d:%02d", s / 3600, (s % 3600) / 60, s % 60);
   return StringFormat("%02d:%02d", s / 60, s % 60);
}

string NomeTF(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_CURRENT) tf = (ENUM_TIMEFRAMES)_Period;
   return StringSubstr(EnumToString(tf), 7);                  // "PERIOD_M15" -> "M15"
}

ENUM_ANCHOR_POINT Ancora()
{
   switch(Canto)
   {
      case CORNER_LEFT_UPPER:  return ANCHOR_LEFT_UPPER;
      case CORNER_LEFT_LOWER:  return ANCHOR_LEFT_LOWER;
      case CORNER_RIGHT_UPPER: return ANCHOR_RIGHT_UPPER;
      default:                 return ANCHOR_RIGHT_LOWER;
   }
}

//--- Linha n do texto (0 = a mais perto do canto).
void Linha(int n, string texto, color cor)
{
   string nome = PREFIXO + IntegerToString(n);
   if(ObjectFind(0, nome) < 0)
   {
      ObjectCreate(0, nome, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, nome, OBJPROP_CORNER, Canto);
      ObjectSetInteger(0, nome, OBJPROP_ANCHOR, Ancora());
      ObjectSetInteger(0, nome, OBJPROP_XDISTANCE, 10);
      ObjectSetInteger(0, nome, OBJPROP_YDISTANCE, 10 + n * (TamanhoFonte + 9));
      ObjectSetInteger(0, nome, OBJPROP_FONTSIZE, TamanhoFonte);
      ObjectSetString(0, nome, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, nome, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, nome, OBJPROP_HIDDEN, true);
   }
   ObjectSetString(0, nome, OBJPROP_TEXT, texto);
   ObjectSetInteger(0, nome, OBJPROP_COLOR, cor);
}

void Mostra(int n, ENUM_TIMEFRAMES tf, datetime agora)
{
   int s = SegundosFaltando(tf, agora);
   if(s < 0) { Linha(n, NomeTF(tf) + " fecha no fim do pregão", Cor); return; }
   Linha(n, NomeTF(tf) + " fecha em " + Formata(s), s <= SegundosAviso ? CorAviso : Cor);
}

void Atualiza()
{
   datetime agora = TimeTradeServer();
   bool referencia = TempoReferencia != PERIOD_CURRENT && TempoReferencia != (ENUM_TIMEFRAMES)_Period;
   bool embaixo = Canto == CORNER_LEFT_LOWER || Canto == CORNER_RIGHT_LOWER;
   // o tempo do gráfico fica sempre na linha de cima
   Mostra(referencia && embaixo ? 1 : 0, (ENUM_TIMEFRAMES)_Period, agora);
   if(referencia) Mostra(embaixo ? 0 : 1, TempoReferencia, agora);
   else ObjectDelete(0, PREFIXO + "1");
   ChartRedraw(0);
}

int OnInit()
{
   ObjectsDeleteAll(0, PREFIXO);
   EventSetTimer(1);
   Atualiza();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0, PREFIXO);
   ChartRedraw(0);
}

void OnTimer() { Atualiza(); }

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   return rates_total;
}
