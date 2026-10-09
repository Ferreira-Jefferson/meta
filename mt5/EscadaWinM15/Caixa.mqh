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
   // Só o que está em uso: linha zerada ou que não se aplica agora não aparece (pedido do dono, 2026-10-09).
   string s = "EscadaWinM15 v4.1\nCaixa informado: R$ " + DoubleToString(inicial, 2) + "\n";
   if(resultado != 0.0) s += StringFormat("Resultado do robô: R$ %+.2f\nCaixa atual: R$ %.2f\n", resultado, caixa);
   if(caixa < sugerido) s += StringFormat("ATENÇÃO: caixa abaixo do sugerido (R$ %.0f)\n", sugerido);
   // Posição aberta: o flutuante só vira caixa ao fechar; a margem fica bloqueada enquanto a posição existe.
   if(PositionSelect(_Symbol) && (ulong)PositionGetInteger(POSITION_MAGIC) == magic)
   {
      double aberto = PositionGetDouble(POSITION_PROFIT), margem = AccountInfoDouble(ACCOUNT_MARGIN);
      bool compra = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      double entrada = PositionGetDouble(POSITION_PRICE_OPEN), sl = PositionGetDouble(POSITION_SL);
      // stop em pontos a partir da entrada, do ponto de vista da operação: -635 = perde 635 se bater; +200 = garante 200
      string stop_pts = sl > 0 ? StringFormat("%+.0f pts", (sl - entrada) * (compra ? 1 : -1)) : "sem stop";
      s += StringFormat("Posição: %s %.0f @ %.0f | stop %s\nResultado aberto: R$ %+.2f\n", compra ? "compra" : "venda",
                        PositionGetDouble(POSITION_VOLUME), entrada, stop_pts, aberto);
      if(margem > 0.0) s += StringFormat("Margem em uso: R$ %.2f\n", margem);
      s += StringFormat("Caixa livre: R$ %.2f\n", caixa + aberto - margem);
   }
   Comment(s);
   if(caixa == ultimo) return;
   ultimo = caixa;
   PrintFormat("CAIXA: informado R$ %.2f, resultado do robô R$ %+.2f, atual R$ %.2f%s", inicial, resultado, caixa,
               caixa < sugerido ? StringFormat(" (abaixo dos R$ %.0f sugeridos para %.0f contrato(s))", sugerido, lotes) : "");
}

#endif
