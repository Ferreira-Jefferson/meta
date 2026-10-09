//+------------------------------------------------------------------+
//| Registro.mqh — grava as negociações desta estratégia num CSV     |
//| (pasta Common\Files), para comparar com o backtest em Python.    |
//+------------------------------------------------------------------+
#ifndef ESCADA_REGISTRO
#define ESCADA_REGISTRO

#define ARQ_DEALS "EscadaWinM15_negocios.csv"

//--- Uma linha por negócio (entrada e saída), com o comentário que diz o porquê.
void GravaNegocios(ulong magic)
{
   if(!HistorySelect(0, TimeCurrent() + SEG_DIA)) return;
   int f = FileOpen(ARQ_DEALS, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ';');
   if(f == INVALID_HANDLE) { PrintFormat("ERRO ao criar %s", ARQ_DEALS); return; }
   FileWrite(f, "hora", "tipo", "entrada_saida", "volume", "preco", "resultado", "comentario");
   for(int k = 0; k < HistoryDealsTotal(); k++)
   {
      ulong d = HistoryDealGetTicket(k);
      if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != magic) continue;
      long es = HistoryDealGetInteger(d, DEAL_ENTRY);
      FileWrite(f, TimeToString((datetime)HistoryDealGetInteger(d, DEAL_TIME), TIME_DATE | TIME_SECONDS),
                HistoryDealGetInteger(d, DEAL_TYPE) == DEAL_TYPE_BUY ? "compra" : "venda",
                es == DEAL_ENTRY_IN ? "entrada" : "saida",
                DoubleToString(HistoryDealGetDouble(d, DEAL_VOLUME), 0),
                DoubleToString(HistoryDealGetDouble(d, DEAL_PRICE), 0),
                DoubleToString(HistoryDealGetDouble(d, DEAL_PROFIT), 2),
                HistoryDealGetString(d, DEAL_COMMENT));
   }
   FileClose(f);
   PrintFormat("Negócios gravados em Common\\Files\\%s", ARQ_DEALS);
}

#endif
