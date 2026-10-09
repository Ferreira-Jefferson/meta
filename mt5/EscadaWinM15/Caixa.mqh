//+------------------------------------------------------------------+
//| Caixa.mqh — caixa do robô: o valor informado pelo dono somado ao |
//| resultado de todas as negociações deste magic no histórico.      |
//|                                                                  |
//| Existe porque o saldo da conta no MT5 nem sempre bate com o da   |
//| corretora. Só informa (gráfico e log): não trava nem muda lotes. |
//+------------------------------------------------------------------+
#ifndef ESCADA_CAIXA
#define ESCADA_CAIXA

#define CAIXA_POR_CONTRATO 1000.0   // margem + pior sequência de perdas medida (≈ R$950 por contrato)

//--- Resultado de tudo o que este robô já negociou (lucro, corretagem, taxas e swap que a corretora informar).
double ResultadoDoRobo(ulong magic)
{
   if(!HistorySelect(0, TimeCurrent() + SEG_DIA)) return 0.0;
   double r = 0.0;
   for(int k = 0; k < HistoryDealsTotal(); k++)
   {
      ulong d = HistoryDealGetTicket(k);
      if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != magic) continue;
      r += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_COMMISSION)
         + HistoryDealGetDouble(d, DEAL_FEE) + HistoryDealGetDouble(d, DEAL_SWAP);
   }
   return r;
}

//--- Mostra no gráfico o caixa atual; avisa no log (uma vez por mudança) se ficou abaixo do sugerido para os lotes.
void MostraCaixa(double inicial, double lotes, ulong magic)
{
   static double ultimo = -1e18;
   double resultado = ResultadoDoRobo(magic);
   double caixa = inicial + resultado;
   double sugerido = CAIXA_POR_CONTRATO * lotes;
   Comment(StringFormat("EscadaWinM15 v4.2\nCaixa informado: R$ %.2f\nResultado do robô: R$ %+.2f\nCaixa atual: R$ %.2f\nSugerido p/ %.0f contrato(s): R$ %.0f%s",
                        inicial, resultado, caixa, lotes, sugerido, caixa < sugerido ? "  << ABAIXO" : ""));
   if(caixa == ultimo) return;
   ultimo = caixa;
   PrintFormat("CAIXA: informado R$ %.2f, resultado do robô R$ %+.2f, atual R$ %.2f%s", inicial, resultado, caixa,
               caixa < sugerido ? StringFormat(" (abaixo dos R$ %.0f sugeridos para %.0f contrato(s))", sugerido, lotes) : "");
}

#endif
