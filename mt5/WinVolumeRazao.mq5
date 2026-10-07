//+------------------------------------------------------------------+
//| WinVolumeRazao.mq5                                                  |
//| Volume relativo para o WIN: o volume intradiario tem formato de "U" |
//| (alto na abertura e no fechamento, baixo no meio), entao comparar   |
//| com as velas vizinhas engana. Aqui cada vela e' comparada com o     |
//| volume da MESMA HORA e do MESMO DIA DA SEMANA nos ultimos `Dias`    |
//| pregoes (segunda com as segundas anteriores, terca com as tercas).  |
//| Semana sem pregao naquele dia (feriado) ou sem volume e' pulada.    |
//|                                                                      |
//| Valor plotado = volume da vela / MEDIANA (ponderada pela recencia)  |
//| dos volumes daquele                                                  |
//| horario nos pregoes anteriores. Linha de equilibrio (Nivel, padrao 1,0):         |
//| acima = mais volume que o normal para o horario;                    |
//| abaixo = menos. Com Dias = 2 a mediana e' a media de     |
//| as duas ultimas segundas, tercas, etc.                              |
//| Volta semana a semana ate achar `Dias` pregoes validos. Se o        |
//| historico acabar antes, a vela fica VAZIA (nao calcula com menos) e |
//| um aviso pequeno aparece na janela do indicador.                    |
//| historico). Funciona em qualquer tempo grafico; a vela ainda em formacao        |
//| aparece baixa no comeco porque o volume dela ainda esta' juntando.  |
//+------------------------------------------------------------------+
#property copyright "win_volume_razao"
#property version   "1.00"
#property strict

#property indicator_separate_window
#property indicator_buffers 2
#property indicator_plots   1
#property indicator_label1  "Volume / mediana do horario"
#property indicator_type1   DRAW_COLOR_HISTOGRAM
#property indicator_color1  clrLime, C'70,100,140', C'150,140,70', clrRed   // cores reais vem das entradas (OnInit)
#property indicator_width1  2
#property indicator_minimum 0.0

enum ETipoVolume { VOL_REAL, VOL_TICK };

input int         Dias         = 20;          // Quantos pregoes anteriores do MESMO dia da semana entram no calculo (20 = as 20 ultimas segundas, se hoje e' segunda)
input double      MeiaVida     = 4.0;         // Em quantas semanas o peso de um pregao cai pela metade (4 = o de 4 semanas atras pesa metade do de ontem-da-semana). 0 = todos com o mesmo peso
input ETipoVolume TipoVolume   = VOL_REAL; // REAL = contratos negociados; TICK = numero de negocios
input double      Nivel        = 1.0;         // Linha de equilibrio (1,0 = volume igual ao normal do horario); tambem muda a cor verde/vermelho
input color       CorNivel     = clrSilver;   // Cor da linha de equilibrio
input int         EspessuraNivel = 2;         // Espessura da linha de equilibrio (1 a 5)
input ENUM_LINE_STYLE EstiloNivel = STYLE_SOLID; // Estilo da linha de equilibrio
input double      NivelBaixo   = 0.0;         // Linha de volume BAIXO (0 = automatico pelo tempo grafico: M1 0,55; M5 e demais 0,65). Ex.: 0,7 = 70% do normal
input color       CorNivelBaixo = clrTomato;  // Cor da linha de volume baixo
input double      NivelAlto    = 0.0;         // Linha de volume ALTO / sobre-volume (0 = automatico pelo tempo grafico: M1 1,75; M5 e demais 1,45). Ex.: 1,5 = 150% do normal
input color       CorNivelAlto = clrLimeGreen; // Cor da linha de volume alto
input ENUM_LINE_STYLE EstiloLimites = STYLE_DASH; // Estilo das linhas de volume baixo e alto
input color       CorSobre     = clrLime;         // Barra com SOBRE-volume (razao >= NivelAlto)
input color       CorAcima     = C'70,100,140';   // Barra acima do equilibrio mas abaixo do sobre-volume
input color       CorAbaixo    = C'150,140,70';     // Barra abaixo do equilibrio mas acima do volume baixo
input color       CorSub       = clrRed;          // Barra com volume BAIXO (razao < NivelBaixo)

double g_razao[];
double g_baixo = 0.65, g_alto = 1.45;   // niveis em uso (automaticos ou os digitados)
datetime g_primeira_ok = 0;     // primeira vela com pregoes suficientes
int      g_achados_ultima = 0;  // quantos pregoes a ultima vela achou
const string MSG = "WinVolRazaoMsg";
double g_cor[];

//+------------------------------------------------------------------+
void Aviso(string texto)
{
   int win = ChartWindowFind();
   if(texto == "") { ObjectDelete(0, MSG); return; }
   if(ObjectFind(0, MSG) < 0)
   {
      ObjectCreate(0, MSG, OBJ_LABEL, win < 0 ? 0 : win, 0, 0);
      ObjectSetInteger(0, MSG, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, MSG, OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, MSG, OBJPROP_YDISTANCE, 22);
      ObjectSetInteger(0, MSG, OBJPROP_FONTSIZE, 9);
      ObjectSetInteger(0, MSG, OBJPROP_COLOR, clrOrange);
      ObjectSetInteger(0, MSG, OBJPROP_SELECTABLE, false);
   }
   ObjectSetString(0, MSG, OBJPROP_TEXT, texto);
}

void OnDeinit(const int reason) { ObjectDelete(0, MSG); }

int OnInit()
{
   SetIndexBuffer(0, g_razao, INDICATOR_DATA);
   SetIndexBuffer(1, g_cor,   INDICATOR_COLOR_INDEX);
   PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, EMPTY_VALUE);
   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 0, CorSobre);
   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 1, CorAcima);
   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 2, CorAbaixo);
   PlotIndexSetInteger(0, PLOT_LINE_COLOR, 3, CorSub);
   // padroes = percentis 15 e 85 da razao em 5 anos de WIN (Dias=20, meia-vida 4): M1 e' mais "esticado" que M5
   g_baixo = NivelBaixo > 0 ? NivelBaixo : (_Period == PERIOD_M1 ? 0.55 : 0.65);
   g_alto  = NivelAlto  > 0 ? NivelAlto  : (_Period == PERIOD_M1 ? 1.75 : 1.45);
   IndicatorSetInteger(INDICATOR_DIGITS, 2);
   IndicatorSetInteger(INDICATOR_LEVELS, 3);
   double valores[3]  = {Nivel, g_baixo, g_alto};
   color  cores[3]    = {CorNivel, CorNivelBaixo, CorNivelAlto};
   ENUM_LINE_STYLE estilos[3] = {EstiloNivel, EstiloLimites, EstiloLimites};
   for(int k = 0; k < 3; k++)
   {
      IndicatorSetDouble(INDICATOR_LEVELVALUE, k, valores[k]);
      IndicatorSetInteger(INDICATOR_LEVELCOLOR, k, cores[k]);
      IndicatorSetInteger(INDICATOR_LEVELSTYLE, k, estilos[k]);
      IndicatorSetInteger(INDICATOR_LEVELWIDTH, k, MathMax(1, MathMin(5, EspessuraNivel)));
   }
   IndicatorSetString(INDICATOR_SHORTNAME, StringFormat("Volume / mediana do dia da semana e horario (%d sem, meia-vida %g) [%.2f | %.2f]", Dias, MeiaVida, g_baixo, g_alto));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
// v[0] = pregao mais recente. Sem meia-vida: mediana comum. Com meia-vida: MEDIANA PONDERADA, o peso do
// pregao k (k=0 o mais recente) e' 0,5^(k/MeiaVida) -- a mediana continua ignorando dia fora da curva,
// mas acompanha melhor o nivel recente do volume.
double Mediana(double &v[], int n)
{
   ArrayResize(v, n);
   if(MeiaVida <= 0.0)
   {
      ArraySort(v);
      return (n % 2 == 1) ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2.0;
   }
   double w[];
   ArrayResize(w, n);
   for(int k = 0; k < n; k++) w[k] = MathPow(0.5, k / MeiaVida);
   for(int a = 1; a < n; a++)                       // ordena por valor (insercao), levando o peso junto
   {
      double xv = v[a], xw = w[a];
      int b = a - 1;
      while(b >= 0 && v[b] > xv) { v[b + 1] = v[b]; w[b + 1] = w[b]; b--; }
      v[b + 1] = xv; w[b + 1] = xw;
   }
   double total = 0.0, acum = 0.0;
   for(int k = 0; k < n; k++) total += w[k];
   for(int k = 0; k < n; k++) { acum += w[k]; if(acum >= 0.5 * total) return v[k]; }
   return v[n - 1];
}

int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[], const double &high[],
                const double &low[], const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   if(Dias < 1) return 0;
   int ini = prev_calculated > 0 ? prev_calculated - 1 : 0;
   if(prev_calculated == 0) g_primeira_ok = 0;

   for(int i = ini; i < rates_total; i++)
   {
      double vol = (double)(TipoVolume == VOL_REAL ? volume[i] : tick_volume[i]);
      double ant[];
      ArrayResize(ant, 0);

      for(int d = 1; ArraySize(ant) < Dias; d++)
      {
         datetime alvo = time[i] - (datetime)(d * 7 * 86400);   // mesmo dia da semana, d semanas atras
         if(alvo < time[0]) break;                                // acabou o historico do grafico
         int shift = iBarShift(_Symbol, _Period, alvo, true);      // exato: mesma hora
         if(shift < 0) continue;                                  // sem vela nesse horario (feriado, ou historico faltando)
         int idx = rates_total - 1 - shift;
         double v = (double)(TipoVolume == VOL_REAL ? volume[idx] : tick_volume[idx]);
         if(v <= 0) continue;                                     // dia sem negocio naquele horario nao conta
         int n = ArraySize(ant);
         ArrayResize(ant, n + 1);
         ant[n] = v;
      }

      g_achados_ultima = ArraySize(ant);
      if(ArraySize(ant) < Dias) { g_razao[i] = EMPTY_VALUE; g_cor[i] = 0; continue; }
      if(g_primeira_ok == 0) g_primeira_ok = time[i];

      double med = Mediana(ant, ArraySize(ant));
      g_razao[i] = med > 0 ? vol / med : EMPTY_VALUE;
      g_cor[i]   = g_razao[i] >= g_alto ? 0 : (g_razao[i] >= Nivel ? 1 : (g_razao[i] >= g_baixo ? 2 : 3));
   }
   if(g_achados_ultima < Dias)
      Aviso(StringFormat("Dados insuficientes: achei %d de %d pregoes do mesmo dia da semana (carregue mais historico ou reduza 'Dias')", g_achados_ultima, Dias));
   else if(g_primeira_ok != 0 && g_primeira_ok > time[0])
      Aviso(StringFormat("Velas antes de %s sem dados suficientes (precisam de %d pregoes anteriores)", TimeToString(g_primeira_ok, TIME_DATE), Dias));
   else
      Aviso("");
   return rates_total;
}
//+------------------------------------------------------------------+
