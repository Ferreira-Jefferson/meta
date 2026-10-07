//+------------------------------------------------------------------+
//| WinSeletor/Comum.mqh                                             |
//| Utilitario comum aos 5 modulos do WinSeletor.mq5.                |
//+------------------------------------------------------------------+
#ifndef WINSELETOR_COMUM_MQH
#define WINSELETOR_COMUM_MQH

// Ha posicao aberta ou ordem pendente com este magic no simbolo do grafico?
// Cada robo e' identificado pelo magic proprio (o original de cada EA).
bool WinTemPosOuOrdens(const ulong magic)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != magic) continue;
      return true;
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != magic) continue;
      return true;
   }
   return false;
}

#endif
