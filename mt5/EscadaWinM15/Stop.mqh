//+------------------------------------------------------------------+
//| Stop.mqh — stop da v4.1. Espelha stop.py.                        |
//|  - inicial: no pivô; se a MME38 do M15 está entre o pivô e a     |
//|    entrada (a mais de 0,25 ATR da entrada), sobe para 0,2 ATR    |
//|    além dela.                                                    |
//|  - movimento: a cada novo fundo (compra) / topo (venda)          |
//|    confirmado, o stop vai para ele, se for a favor.              |
//+------------------------------------------------------------------+
#ifndef ESCADA_STOP
#define ESCADA_STOP

#include "Escada.mqh"
#include "Indicadores.mqh"

#define COLCHAO_ATR    0.2
#define FOLGA_MIN_ATR  0.25

//--- O stop mais a favor da posição (mais alto na compra, mais baixo na venda).
double StopMaisAFavor(double a, double b, int lado) { return lado == 1 ? MathMax(a, b) : MathMin(a, b); }

//--- Arredonda o stop ao tick, para o lado de MAIS espaço (abaixo na compra, acima na venda).
double StopNoTick(double preco, int lado)
{
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   return (lado == 1 ? MathFloor(preco / tick) : MathCeil(preco / tick)) * tick;
}

//--- Stop inicial da v4.1 para a entrada no close da barra de confirmação i.
double StopInicialV41(int i, int lado, double preco_pivo)
{
   double atr = g_barras[i].atr, entrada = g_barras[i].c, mme = g_mme38[i];
   double stop = preco_pivo;
   if((entrada - mme) * lado > FOLGA_MIN_ATR * atr)
      stop = StopMaisAFavor(preco_pivo, mme - lado * COLCHAO_ATR * atr, lado);
   return StopNoTick(stop, lado);
}

//--- Novo stop pela estrutura: se o pivô confirmado na barra é do lado da posição, o stop vai para ele.
double StopPelaEstrutura(double stop_atual, const Pivo &pivo, int lado)
{
   if(LadoDoPivo(pivo) != lado) return stop_atual;
   return StopMaisAFavor(stop_atual, pivo.preco, lado);
}

#endif
