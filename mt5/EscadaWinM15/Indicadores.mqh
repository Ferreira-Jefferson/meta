//+------------------------------------------------------------------+
//| Indicadores.mqh — médias móveis, estocástico e tendência dos     |
//| tempos gráficos maiores (H1 e H4), sempre com barras fechadas.   |
//|                                                                  |
//| Espelha indicadores.py e filtros.py:                             |
//|  - MME com semente no 1º valor (pandas ewm adjust=False)         |
//|  - tendência = +1 se close > MME34 e MME9 > MME21; -1 espelho    |
//|  - H1 = fechamento da última M15 de cada hora do relógio         |
//|  - H4 = blocos 09-13, 13-17 e 17-fim do pregão                   |
//+------------------------------------------------------------------+
#ifndef ESCADA_INDICADORES
#define ESCADA_INDICADORES

#include "Barras.mqh"

#define MME_APERTO 38

//=================== médias sobre as barras M15 ===================
double g_mme38[];

double ProximaMME(double anterior, double valor, int n, bool primeira)
{
   if(primeira) return valor;
   double a = 2.0 / (n + 1);
   return a * valor + (1 - a) * anterior;
}

//--- Média simples do close (ou do open) das n barras até i. SEM_VALOR se não há barras suficientes.
double MMS(int i, int n, bool do_open = false)
{
   if(i < n - 1) return SEM_VALOR;
   double s = 0;
   for(int k = i - n + 1; k <= i; k++) s += do_open ? g_barras[k].o : g_barras[k].c;
   return s / n;
}

//--- %K "cru" do estocástico n na barra i.
double EstocasticoCru(int i, int n)
{
   if(i < n - 1) return SEM_VALOR;
   double hh = g_barras[i].h, ll = g_barras[i].l;
   for(int k = i - n + 1; k < i; k++) { hh = MathMax(hh, g_barras[k].h); ll = MathMin(ll, g_barras[k].l); }
   if(hh == ll) return SEM_VALOR;
   return 100.0 * (g_barras[i].c - ll) / (hh - ll);
}

//--- Estocástico lento: %K de n períodos suavizado por média de `suav`.
double Estocastico(int i, int n = 14, int suav = 3)
{
   double s = 0;
   for(int k = i - suav + 1; k <= i; k++)
   {
      if(k < 0) return SEM_VALOR;
      double x = EstocasticoCru(k, n);
      if(x == SEM_VALOR) return SEM_VALOR;
      s += x;
   }
   return s / suav;
}

//=================== tempos gráficos maiores ===================
//--- Uma série de barras maiores (H1 ou H4): fechamentos e as três MMEs da tendência.
struct SerieMaior
{
   datetime chave_aberta;   // bloco em formação
   double   close_aberto;
   int      n;              // blocos fechados
   double   mme9, mme21, mme34, ultimo_close;
};

SerieMaior g_h1, g_h4;

void IniciaSerie(SerieMaior &s) { s.chave_aberta = 0; s.n = 0; }

//--- Fecha o bloco em formação: atualiza as MMEs com o fechamento dele.
void FechaBloco(SerieMaior &s)
{
   bool primeira = s.n == 0;
   s.mme9  = ProximaMME(s.mme9,  s.close_aberto, 9,  primeira);
   s.mme21 = ProximaMME(s.mme21, s.close_aberto, 21, primeira);
   s.mme34 = ProximaMME(s.mme34, s.close_aberto, 34, primeira);
   s.ultimo_close = s.close_aberto;
   s.n++;
   s.chave_aberta = 0;
}

//--- Põe a M15 fechada no bloco `chave`; se a chave mudou, o bloco anterior fecha antes.
void AlimentaSerie(SerieMaior &s, datetime chave, double close)
{
   if(s.chave_aberta != 0 && s.chave_aberta != chave) FechaBloco(s);
   s.chave_aberta = chave;
   s.close_aberto = close;
}

//--- Tendência do último bloco FECHADO: +1, -1 ou 0 (0 também se ainda não há bloco).
int Tendencia(const SerieMaior &s)
{
   if(s.n == 0) return 0;
   if(s.ultimo_close > s.mme34 && s.mme9 > s.mme21) return 1;
   if(s.ultimo_close < s.mme34 && s.mme9 < s.mme21) return -1;
   return 0;
}

//--- Bloco H4 de uma barra: 09-13, 13-17 ou 17-fim do pregão.
datetime ChaveH4(datetime t)
{
   int h = MinutoDoDia(t) / 60;
   return DiaDe(t) + (h < 13 ? 9 : (h < 17 ? 13 : 17)) * 3600;
}

//--- A barra i é a última do seu bloco H4 (termina às 13:00 ou às 17:00)?
bool FechaBlocoH4(int i)
{
   int fim = MinutoDoDia(g_barras[i].t + SEG_BARRA);
   return fim == 13 * 60 || fim == 17 * 60;
}

//=================== atualização a cada M15 fechada ===================
//--- Atualiza tudo o que depende da barra i. Ordem importa: o H1 da hora da barra i continua aberto
//--- (só fecha quando chega uma barra de outra hora); o bloco H4 fecha junto com a sua última barra.
void AtualizaIndicadores(int i)
{
   ArrayResize(g_mme38, i + 1, 20000);
   g_mme38[i] = ProximaMME(i > 0 ? g_mme38[i - 1] : 0, g_barras[i].c, MME_APERTO, i == 0);

   AlimentaSerie(g_h1, g_barras[i].t - (g_barras[i].t % 3600), g_barras[i].c);
   AlimentaSerie(g_h4, ChaveH4(g_barras[i].t), g_barras[i].c);
   if(FechaBlocoH4(i)) FechaBloco(g_h4);
}

#endif
