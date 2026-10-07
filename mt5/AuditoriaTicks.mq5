//+------------------------------------------------------------------+
//| AuditoriaTicks.mq5 -- NAO opera. So' conta, tick a tick, o que o  |
//| Testador entrega, por dia: ticks, ticks com ultimo negocio = 0,   |
//| ticks com ultimo negocio a mais de 100 pts do meio compra/venda,  |
//| e quantos valores diferentes de ultimo negocio apareceram.        |
//| Grava em <pasta comum do MT5>\Files\auditoria_ticks_<Rotulo>.csv  |
//| Rodar no Testador com "Cada tick e' baseado em um tick real".     |
//+------------------------------------------------------------------+
#property version "1.00"
#property strict

input string Rotulo     = "tester";
input double LimitePts  = 100.0;

datetime g_dia = 0;
long     g_ticks = 0, g_zero = 0, g_longe = 0, g_unicos = 0;
double   g_ultimo_last = -1.0;
string   g_linhas[];

void FechaDia()
{
   if(g_dia == 0) return;
   int n = ArraySize(g_linhas);
   ArrayResize(g_linhas, n + 1);
   g_linhas[n] = StringFormat("%s;%I64d;%I64d;%I64d;%I64d", TimeToString(g_dia, TIME_DATE),
                              g_ticks, g_zero, g_longe, g_unicos);
   g_ticks = g_zero = g_longe = g_unicos = 0;
   g_ultimo_last = -1.0;
}

void OnTick()
{
   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t)) return;
   MqlDateTime dt; TimeToStruct(t.time, dt);
   int mm = dt.hour * 60 + dt.min;
   if(mm < 9 * 60 + 5 || mm >= 18 * 60 + 20) return;
   datetime dia = StringToTime(StringFormat("%04d.%02d.%02d", dt.year, dt.mon, dt.day));
   if(dia != g_dia) { FechaDia(); g_dia = dia; }
   g_ticks++;
   if(t.last == 0.0) g_zero++;
   else if(t.bid > 0 && t.ask > 0 && MathAbs(t.last - (t.bid + t.ask) / 2.0) > LimitePts) g_longe++;
   if(t.last != g_ultimo_last) { g_unicos++; g_ultimo_last = t.last; }
}

void OnDeinit(const int reason)
{
   FechaDia();
   string nome = "auditoria_ticks_" + Rotulo + ".csv";
   int h = FileOpen(nome, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(h == INVALID_HANDLE) { Print("nao consegui gravar ", nome); return; }
   FileWriteString(h, "dia;ticks;last_zero;last_longe;trocas_de_last\n");
   for(int i = 0; i < ArraySize(g_linhas); i++) FileWriteString(h, g_linhas[i] + "\n");
   FileClose(h);
   PrintFormat("auditoria gravada: %s (%d dias)", nome, ArraySize(g_linhas));
}
