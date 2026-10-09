//+------------------------------------------------------------------+
//| Ordens.mqh — tudo o que fala com a corretora: entrada limitada,  |
//| validade dela, cancelamento, mover o stop e zerar. Espelha       |
//| operacao.py, com a diferença de que aqui a fila é a real.        |
//|                                                                  |
//|  - Entrada: ordem LIMITADA no close da barra de confirmação, já  |
//|    com o stop (campo sl, no servidor). Vale por 3 barras M15.    |
//|  - Uma posição por vez; sem alvo; zera no corte do pregão.       |
//+------------------------------------------------------------------+
#ifndef ESCADA_ORDENS
#define ESCADA_ORDENS

#include <Trade\Trade.mqh>
#include "Calendario.mqh"

#define VALIDADE_BARRAS 3

CTrade g_trade;

//--- Entrada pendente desta estratégia.
struct Entrada
{
   ulong  ticket;
   int    lado;
   int    vence_na_barra;   // cancela quando esta barra M15 fechar
};
Entrada g_entrada;

void ConfiguraOrdens(ulong magic)
{
   g_trade.SetExpertMagicNumber(magic);
   g_trade.SetDeviationInPoints(0);
   g_entrada.ticket = 0;
}

//=================== consultas ===================
bool TemPosicao(ulong magic)
{
   return PositionSelect(_Symbol) && (ulong)PositionGetInteger(POSITION_MAGIC) == magic;
}

//--- Há posição no símbolo que NÃO é desta estratégia (manual ou outro robô)? Então não opera.
bool PosicaoDeOutro(ulong magic)
{
   return PositionSelect(_Symbol) && (ulong)PositionGetInteger(POSITION_MAGIC) != magic;
}

bool TemEntradaPendente()
{
   return g_entrada.ticket != 0 && OrderSelect(g_entrada.ticket);
}

//=================== entrada ===================
//--- Preço do limite do lado de dentro do livro: se o mercado já passou dele, fica a 1 tick da melhor oferta.
//--- Igual ao LimiteNoLivro do robô ES do WinMaestro (2026-10-09): a entrada NUNCA sai a mercado.
double LimiteNoLivro(int lado, double limite)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(lado == 1 && ask > 0.0 && limite >= ask)  return ask - tick;
   if(lado == -1 && bid > 0.0 && limite <= bid) return bid + tick;
   return limite;
}

//--- Envia a entrada limitada (nunca a mercado), com o stop junto. `limite` volta com o preço realmente pedido.
bool EnviaEntrada(int lado, double &limite, double stop, double lotes, int barra_conf, string motivo)
{
   double pedido = LimiteNoLivro(lado, limite);
   if(pedido != limite) PrintFormat("Limite %.0f já passou: entrada posta a 1 tick da melhor oferta, %.0f", limite, pedido);
   limite = pedido;
   if((limite - stop) * lado <= 0) { PrintFormat("Entrada %s não enviada: stop %.0f do lado errado do limite %.0f", motivo, stop, limite); return false; }
   bool ok = lado == 1 ? g_trade.BuyLimit(lotes, limite, _Symbol, stop, 0, ORDER_TIME_DAY, 0, motivo)
                       : g_trade.SellLimit(lotes, limite, _Symbol, stop, 0, ORDER_TIME_DAY, 0, motivo);
   if(!ok)
   {
      PrintFormat("ERRO ao enviar entrada %s: %d %s", motivo, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return false;
   }
   g_entrada.ticket = g_trade.ResultOrder();
   g_entrada.lado = lado;
   g_entrada.vence_na_barra = barra_conf + VALIDADE_BARRAS;
   return true;
}

void CancelaEntrada(string motivo)
{
   if(!TemEntradaPendente()) { g_entrada.ticket = 0; return; }
   if(g_trade.OrderDelete(g_entrada.ticket)) PrintFormat("Entrada cancelada: %s", motivo);
   else PrintFormat("ERRO ao cancelar entrada (%s): %d", motivo, g_trade.ResultRetcode());
   g_entrada.ticket = 0;
}

//--- A entrada venceu (3 barras fechadas depois da confirmação)?
void VenceEntrada(int barra_fechada)
{
   if(TemEntradaPendente() && barra_fechada >= g_entrada.vence_na_barra) CancelaEntrada("validade de 3 barras");
}

//=================== posição ===================
double StopDaPosicao() { return PositionGetDouble(POSITION_SL); }
int    LadoDaPosicao() { return PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1; }

void Zera(string motivo, ulong magic)
{
   if(!TemPosicao(magic)) return;
   if(g_trade.PositionClose(_Symbol)) PrintFormat("Posição zerada: %s", motivo);
   else PrintFormat("ERRO ao zerar (%s): %d", motivo, g_trade.ResultRetcode());
}

//--- Move o stop da posição. Se o preço já passou do novo stop, zera (o stop teria sido executado).
void MoveStop(double novo, ulong magic)
{
   if(!TemPosicao(magic) || novo == StopDaPosicao()) return;
   int lado = LadoDaPosicao();
   double preco = lado == 1 ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if((preco - novo) * lado <= 0) { Zera("preço já além do novo stop", magic); return; }
   if(g_trade.PositionModify(_Symbol, novo, 0)) PrintFormat("Stop movido para %.0f (estrutura)", novo);
   else PrintFormat("ERRO ao mover stop para %.0f: %d", novo, g_trade.ResultRetcode());
}

//--- Corte do pregão: cancela a entrada pendente e zera a posição.
void FazCorte(ulong magic)
{
   CancelaEntrada("corte do pregão");
   Zera("corte do pregão (fim do contínuo - 5 min)", magic);
}

#endif
