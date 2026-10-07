//+------------------------------------------------------------------+
//| WinMaestro/Corretora.mqh                                         |
//| Porta UNICA para a corretora (especificacao sec. 1, O15).            |
//| So' este arquivo chama OrderSend, PositionSelect, Order*,        |
//| History*, AccountInfo*, SymbolInfo* em nome do maestro.          |
//| CCorretora e' a interface; CCorretoraReal fala com o MT5;        |
//| v2.00: AgoraMsc() novo; LeOrdemHist() saiu (HistoryOrderSelect  |
//| troca a selecao global de historico: so' LeHistorico le).        |
//| a falsa (CorretoraFalsa.mqh) so' entra no EA de teste.           |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_CORRETORA_MQH
#define WINMAESTRO_CORRETORA_MQH

struct SOrdemViva
{
   ulong  ticket;
   long   magic;
   int    tipo;          // ENUM_ORDER_TYPE
   double preco;
   double vol;
   long   setup_msc;
   string comentario;
};

struct SOrdemHist
{
   ulong  ticket;
   long   magic;
   int    tipo;          // ENUM_ORDER_TYPE
   double preco;
   double vol;
   long   setup_msc;
   long   done_msc;
   int    estado;        // ENUM_ORDER_STATE
   string comentario;
};

struct SDealInfo
{
   ulong  ticket;
   ulong  ordem;
   long   time_msc;
   long   magic;
   int    tipo;          // ENUM_DEAL_TYPE
   double vol;
   double preco;
   double comissao;
   double taxa;
   double lucro;
   long   razao;
   string comentario;
};

//+------------------------------------------------------------------+
class CCorretora
{
public:
   virtual          ~CCorretora(void) {}
   virtual datetime Agora(void) = 0;                                   // relogio do servidor (TimeTradeServer)
   virtual long     AgoraMsc(void) = 0;
   virtual long     Mono(void) = 0;                                    // relogio MONOTONICO em ms (GetTickCount64) para medir prazos                                // idem em ms (v2.2 sec. 1.1: ms por GetTickCount64 desde o ultimo segundo)
   virtual bool     Conectado(void) = 0;
   virtual bool     Testador(void) = 0;
   virtual bool     LeLiquida(double &vol_assinado, double &preco) = 0; // false = leitura descartada (erro)
   virtual bool     LePendentes(SOrdemViva &o[]) = 0;                  // ordens vivas do simbolo; false = erro
   virtual bool     LeHistorico(const datetime de, const datetime ate, SDealInfo &d[], SOrdemHist &o[]) = 0;
   virtual bool     Envia(MqlTradeRequest &req, MqlTradeResult &res) = 0;
   virtual double   SimboloD(const ENUM_SYMBOL_INFO_DOUBLE p) = 0;
   virtual long     SimboloI(const ENUM_SYMBOL_INFO_INTEGER p) = 0;
   virtual bool     UltimoTick(MqlTick &t) = 0;
   virtual long     ContaI(const ENUM_ACCOUNT_INFO_INTEGER p) = 0;
   virtual string   ContaS(const ENUM_ACCOUNT_INFO_STRING p) = 0;
   virtual bool     RoboEmOutroSimbolo(const long &magics[]) = 0;      // O16
};

CCorretora *mzCorr = NULL;

// No EA de teste (WINMAESTRO_TESTE) a classe real nao e' compilada: nao ha' caminho para OrderSend (B-9).
#ifndef WINMAESTRO_TESTE

//+------------------------------------------------------------------+
class CCorretoraReal : public CCorretora
{
public:
   datetime m_seg;
   ulong    m_tc;
   CCorretoraReal(void) { m_seg = 0; m_tc = 0; }
   virtual datetime Agora(void)                { return TimeTradeServer(); }
   virtual long     AgoraMsc(void)
   {
      datetime s = TimeTradeServer();
      ulong tc = GetTickCount64();
      if(s != m_seg) { m_seg = s; m_tc = tc; }
      ulong d = tc - m_tc;
      if(d > 999) d = 999;
      return (long)s * 1000 + (long)d;
   }
   virtual bool     Testador(void)             { return MQLInfoInteger(MQL_TESTER) != 0; }
   virtual long     Mono(void)                 { return MQLInfoInteger(MQL_TESTER) != 0 ? (long)TimeCurrent() * 1000 : (long)GetTickCount64(); }
   virtual bool     Conectado(void)
   {
      if(MQLInfoInteger(MQL_TESTER) != 0) return true;
      return TerminalInfoInteger(TERMINAL_CONNECTED) != 0;
   }

   virtual bool LeLiquida(double &vol_assinado, double &preco)
   {
      ResetLastError();
      if(PositionSelect(_Symbol))
      {
         double v = PositionGetDouble(POSITION_VOLUME);
         vol_assinado = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? v : -v;
         preco = PositionGetDouble(POSITION_PRICE_OPEN);
         return true;
      }
      int e = GetLastError();
      if(e == ERR_TRADE_POSITION_NOT_FOUND) { vol_assinado = 0.0; preco = 0.0; return true; }   // "sem posicao" (B-11)
      // outro codigo: confere a lista de posicoes; so' a lista lida inteira e sem o simbolo vale "zerado" (B-6)
      int total = PositionsTotal();
      for(int i = 0; i < total; i++)
      {
         string sym = PositionGetSymbol(i);
         if(sym == "" || sym == _Symbol) return false;   // erro na lista, ou posicao do simbolo que nao selecionou: "nao sei"
      }
      vol_assinado = 0.0; preco = 0.0;
      return true;
   }

   virtual bool LePendentes(SOrdemViva &o[])
   {
      ArrayResize(o, 0);
      int total = OrdersTotal();
      for(int i = 0; i < total; i++)
      {
         ulong tk = OrderGetTicket(i);
         if(tk == 0) return false;                        // lista mudou no meio: leitura descartada
         if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
         int n = ArraySize(o);
         ArrayResize(o, n + 1);
         o[n].ticket     = tk;
         o[n].magic      = OrderGetInteger(ORDER_MAGIC);
         o[n].tipo       = (int)OrderGetInteger(ORDER_TYPE);
         o[n].preco      = OrderGetDouble(ORDER_PRICE_OPEN);
         o[n].vol        = OrderGetDouble(ORDER_VOLUME_CURRENT);
         o[n].setup_msc  = OrderGetInteger(ORDER_TIME_SETUP_MSC);
         o[n].comentario = OrderGetString(ORDER_COMMENT);
      }
      return true;
   }

   virtual bool LeHistorico(const datetime de, const datetime ate, SDealInfo &d[], SOrdemHist &o[])
   {
      ArrayResize(d, 0);
      ArrayResize(o, 0);
      if(!HistorySelect(de, ate)) return false;
      int nd = HistoryDealsTotal();
      for(int i = 0; i < nd; i++)
      {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0) return false;
         if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol) continue;
         int n = ArraySize(d);
         ArrayResize(d, n + 1);
         d[n].ticket     = tk;
         d[n].ordem      = (ulong)HistoryDealGetInteger(tk, DEAL_ORDER);
         d[n].time_msc   = HistoryDealGetInteger(tk, DEAL_TIME_MSC);
         d[n].magic      = HistoryDealGetInteger(tk, DEAL_MAGIC);
         d[n].tipo       = (int)HistoryDealGetInteger(tk, DEAL_TYPE);
         d[n].vol        = HistoryDealGetDouble(tk, DEAL_VOLUME);
         d[n].preco      = HistoryDealGetDouble(tk, DEAL_PRICE);
         d[n].comissao   = HistoryDealGetDouble(tk, DEAL_COMMISSION);
         d[n].taxa       = HistoryDealGetDouble(tk, DEAL_FEE);
         d[n].lucro      = HistoryDealGetDouble(tk, DEAL_PROFIT);
         d[n].razao      = HistoryDealGetInteger(tk, DEAL_REASON);
         d[n].comentario = HistoryDealGetString(tk, DEAL_COMMENT);
      }
      int no = HistoryOrdersTotal();
      for(int i = 0; i < no; i++)
      {
         ulong tk = HistoryOrderGetTicket(i);
         if(tk == 0) return false;
         if(HistoryOrderGetString(tk, ORDER_SYMBOL) != _Symbol) continue;
         int n = ArraySize(o);
         ArrayResize(o, n + 1);
         o[n].ticket     = tk;
         o[n].magic      = HistoryOrderGetInteger(tk, ORDER_MAGIC);
         o[n].tipo       = (int)HistoryOrderGetInteger(tk, ORDER_TYPE);
         o[n].preco      = HistoryOrderGetDouble(tk, ORDER_PRICE_OPEN);
         o[n].vol        = HistoryOrderGetDouble(tk, ORDER_VOLUME_INITIAL);
         o[n].setup_msc  = HistoryOrderGetInteger(tk, ORDER_TIME_SETUP_MSC);
         o[n].done_msc   = HistoryOrderGetInteger(tk, ORDER_TIME_DONE_MSC);
         o[n].estado     = (int)HistoryOrderGetInteger(tk, ORDER_STATE);
         o[n].comentario = HistoryOrderGetString(tk, ORDER_COMMENT);
      }
      return true;
   }

   virtual bool Envia(MqlTradeRequest &req, MqlTradeResult &res)
   {
      ResetLastError();
      return OrderSend(req, res);
   }

   virtual double SimboloD(const ENUM_SYMBOL_INFO_DOUBLE p)   { return SymbolInfoDouble(_Symbol, p); }
   virtual long   SimboloI(const ENUM_SYMBOL_INFO_INTEGER p)  { return SymbolInfoInteger(_Symbol, p); }
   virtual bool   UltimoTick(MqlTick &t)                      { return SymbolInfoTick(_Symbol, t); }
   virtual long   ContaI(const ENUM_ACCOUNT_INFO_INTEGER p)   { return AccountInfoInteger(p); }
   virtual string ContaS(const ENUM_ACCOUNT_INFO_STRING p)    { return AccountInfoString(p); }

   virtual bool RoboEmOutroSimbolo(const long &magics[])
   {
      int nm = ArraySize(magics);
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         string s = PositionGetSymbol(i);
         if(s == "" || s == _Symbol) continue;
         long mg = PositionGetInteger(POSITION_MAGIC);
         for(int k = 0; k < nm; k++) if(mg == magics[k]) return true;
      }
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong tk = OrderGetTicket(i);
         if(tk == 0) continue;
         if(OrderGetString(ORDER_SYMBOL) == _Symbol) continue;
         long mg = OrderGetInteger(ORDER_MAGIC);
         for(int k = 0; k < nm; k++) if(mg == magics[k]) return true;
      }
      return false;
   }
};

#endif   // WINMAESTRO_TESTE

#endif
