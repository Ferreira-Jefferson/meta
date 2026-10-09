//+------------------------------------------------------------------+
//| Barras.mqh — barras M15 do pregão contínuo, montadas a partir do |
//| M1, e o ATR(14) de cada uma.                                     |
//|                                                                  |
//| Igual a dados.py: minutos do leilão de fechamento (call) e       |
//| depois ficam de fora; barras de 15 min alinhadas ao relógio;     |
//| ATR conhecido ANTES da barra, contínuo dentro do contrato, e o   |
//| 1º TR de cada pregão = máxima - mínima.                          |
//+------------------------------------------------------------------+
#ifndef ESCADA_BARRAS
#define ESCADA_BARRAS

#include "Calendario.mqh"

#define SEG_BARRA     900      // 15 minutos
#define ATR_N         14
#define ATR_MIN       5
#define INVALIDO      -1.0

struct Barra
{
   datetime t;          // início da barra
   double   o, h, l, c;
   datetime dia;
   int      contrato;
   double   tr;
   double   atr;        // INVALIDO enquanto houver menos de 5 TRs no contrato
};

Barra    g_barras[];
int      g_nbarras   = 0;

Barra    g_aberta;                // barra em formação
bool     g_tem_aberta = false;
datetime g_ult_m1     = 0;        // último minuto M1 já consumido

//--- Último índice (barra fechada mais recente).
int UltimaBarra() { return g_nbarras - 1; }

//--- Índice da 1ª barra do pregão da barra i.
int InicioDoDia(int i)
{
   int k = i;
   while(k > 0 && g_barras[k - 1].dia == g_barras[i].dia) k--;
   return k;
}

//--- TR da barra: usa o fechamento anterior só se for do mesmo pregão.
double CalculaTR(const Barra &b, int i_ant)
{
   double tr = b.h - b.l;
   if(i_ant >= 0 && g_barras[i_ant].dia == b.dia)
   {
      double pc = g_barras[i_ant].c;
      tr = MathMax(tr, MathMax(MathAbs(b.h - pc), MathAbs(b.l - pc)));
   }
   return tr;
}

//--- ATR da barra i: média dos até 14 TRs ANTERIORES no mesmo contrato (mínimo 5).
double CalculaATR(int i)
{
   double soma = 0; int n = 0;
   for(int k = i - 1; k >= 0 && n < ATR_N; k--)
   {
      if(g_barras[k].contrato != g_barras[i].contrato) break;
      soma += g_barras[k].tr; n++;
   }
   return n >= ATR_MIN ? soma / n : INVALIDO;
}

//--- Acrescenta a barra fechada ao histórico e calcula TR e ATR.
int GuardaBarra(Barra &b)
{
   b.dia      = DiaDe(b.t);
   b.contrato = ContratoDe(b.dia);
   b.tr       = CalculaTR(b, g_nbarras - 1);
   ArrayResize(g_barras, g_nbarras + 1, 20000);
   g_barras[g_nbarras] = b;
   g_barras[g_nbarras].atr = CalculaATR(g_nbarras);
   return g_nbarras++;
}

//--- Junta um minuto M1 do contínuo na barra em formação. Devolve true se fechou a barra anterior.
bool JuntaMinuto(const MqlRates &m, Barra &fechada)
{
   datetime inicio = m.time - (m.time % SEG_BARRA);
   bool fechou = false;
   if(g_tem_aberta && g_aberta.t != inicio) { fechada = g_aberta; fechou = true; g_tem_aberta = false; }
   if(!g_tem_aberta)
   {
      g_aberta.t = inicio; g_aberta.o = m.open; g_aberta.h = m.high; g_aberta.l = m.low; g_aberta.c = m.close;
      g_tem_aberta = true;
   }
   else
   {
      g_aberta.h = MathMax(g_aberta.h, m.high);
      g_aberta.l = MathMin(g_aberta.l, m.low);
      g_aberta.c = m.close;
   }
   return fechou;
}

//--- A barra em formação já terminou pelo relógio (15 min passados ou fim do contínuo)?
bool AbertaVenceu(datetime agora)
{
   if(!g_tem_aberta) return false;
   return agora >= g_aberta.t + SEG_BARRA || agora >= FimContinuo(g_aberta.t);
}

//--- Lê os minutos M1 completos desde a última leitura e devolve, em ordem, os índices das barras M15 que fecharam.
int SincronizaBarras(datetime agora, int &novas[])
{
   ArrayResize(novas, 0);
   MqlRates m1[];
   int n = CopyRates(_Symbol, PERIOD_M1, g_ult_m1 + 60, agora, m1);
   for(int k = 0; k < n; k++)
   {
      if(m1[k].time + 60 > agora) break;          // minuto ainda em formação
      g_ult_m1 = m1[k].time;
      if(!NoContinuo(m1[k].time)) continue;        // leilão de fechamento e fora do horário
      Barra fechada;
      if(JuntaMinuto(m1[k], fechada))
      {
         int s = ArraySize(novas); ArrayResize(novas, s + 1);
         novas[s] = GuardaBarra(fechada);
      }
   }
   if(AbertaVenceu(agora))
   {
      Barra fechada = g_aberta; g_tem_aberta = false;
      int s = ArraySize(novas); ArrayResize(novas, s + 1);
      novas[s] = GuardaBarra(fechada);
   }
   return ArraySize(novas);
}

#endif
