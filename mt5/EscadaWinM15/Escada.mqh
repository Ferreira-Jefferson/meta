//+------------------------------------------------------------------+
//| Escada.mqh — pivôs ZigZag (K x ATR) do pregão e o estágio da     |
//| escada em cada pivô confirmado. Espelha escada.py.               |
//|                                                                  |
//| Pivô confirmado sem olhar o futuro, recomeçando a cada pregão.   |
//| Estágio no fundo F_k (compra): 0 se F_k <= F_k-1; 1 se F_k >     |
//| F_k-1; +1 para cada par anterior em que o fundo E o topo do meio |
//| também subiram (teto 6). Venda = espelho, nos topos.             |
//+------------------------------------------------------------------+
#ifndef ESCADA_ESCADA
#define ESCADA_ESCADA

#include "Barras.mqh"

#define K_ZIGZAG     1.5
#define PIVO_TOPO    1
#define PIVO_FUNDO   2
#define SEM_ESTAGIO  -1

struct Pivo
{
   int    tipo;       // PIVO_TOPO ou PIVO_FUNDO
   int    i_pivo;     // barra (índice global) do topo/fundo
   double preco;
   int    i_conf;     // barra (índice global) em que ficou confirmado
};

//--- Lado da operação que um pivô sugere: fundo -> compra (+1), topo -> venda (-1).
int LadoDoPivo(const Pivo &p) { return p.tipo == PIVO_FUNDO ? 1 : -1; }

void AnotaPivo(Pivo &piv[], int tipo, int i_pivo, double preco, int i_conf)
{
   int n = ArraySize(piv); ArrayResize(piv, n + 1);
   piv[n].tipo = tipo; piv[n].i_pivo = i_pivo; piv[n].preco = preco; piv[n].i_conf = i_conf;
}

//--- ZigZag das barras ini..fim (um pregão). Um pivô confirma quando o preço volta K x ATR do extremo.
int ZigZag(int ini, int fim, Pivo &piv[])
{
   ArrayResize(piv, 0);
   int dir = 0, hi = ini, lo = ini;
   for(int t = ini; t <= fim; t++)
   {
      double atr = g_barras[t].atr;
      if(atr == SEM_VALOR) { hi = lo = t; continue; }
      if(g_barras[t].h >= g_barras[hi].h) hi = t;
      if(g_barras[t].l <= g_barras[lo].l) lo = t;
      double dist = atr * K_ZIGZAG;
      if(dir != -1 && hi < t && g_barras[hi].h - g_barras[t].l >= dist)
      {
         AnotaPivo(piv, PIVO_TOPO, hi, g_barras[hi].h, t); dir = -1; lo = t;
      }
      else if(dir != 1 && lo < t && g_barras[t].h - g_barras[lo].l >= dist)
      {
         AnotaPivo(piv, PIVO_FUNDO, lo, g_barras[lo].l, t); dir = 1; hi = t;
      }
   }
   return ArraySize(piv);
}

//--- "a" é melhor que "b" para o lado (mais alto na compra, mais baixo na venda)?
bool Melhor(double a, double b, int lado) { return lado == 1 ? a > b : a < b; }

//--- Estágio da escada no pivô i (SEM_ESTAGIO se ainda não há pivô anterior do mesmo tipo).
int Estagio(const Pivo &piv[], int i)
{
   int lado = LadoDoPivo(piv[i]);
   int mesmos[]; int n = 0;
   for(int j = i; j >= 0; j--)
      if(piv[j].tipo == piv[i].tipo) { ArrayResize(mesmos, n + 1); mesmos[n++] = j; }
   if(n < 2) return SEM_ESTAGIO;
   if(!Melhor(piv[mesmos[0]].preco, piv[mesmos[1]].preco, lado)) return 0;
   int s = 1;
   for(int q = 1; q < n - 1; q++)
   {
      int a = mesmos[q - 1], b = mesmos[q], c = mesmos[q + 1];
      if(a - 1 <= b || b - 1 <= c) break;
      if(Melhor(piv[b].preco, piv[c].preco, lado) && Melhor(piv[a - 1].preco, piv[b - 1].preco, lado))
      {
         s++;
         if(s >= 6) break;
      }
      else break;
   }
   return s;
}

//--- O pivô confirmado exatamente na barra i, se houver (índice em piv[], ou -1).
int PivoConfirmadoEm(const Pivo &piv[], int i)
{
   int n = ArraySize(piv);
   return (n > 0 && piv[n - 1].i_conf == i) ? n - 1 : -1;
}

#endif
