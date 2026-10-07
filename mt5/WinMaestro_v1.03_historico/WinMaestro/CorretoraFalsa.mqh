//+------------------------------------------------------------------+
//| WinMaestro/CorretoraFalsa.mqh                                    |
//| Corretora FALSA, com respostas roteirizadas (O15, sec. 12). So'  |
//| entra no EA de teste WinMaestro_Teste.mq5; nunca no .ex5 de      |
//| producao. Simula conta NETTING de 1 simbolo: pendentes, deals,   |
//| ordens do historico, relogio em ms e os modos de falha:          |
//| DONE sem deal (historico atrasado), timeout com ticket 0         |
//| (executou ou nao), recusa, mercado fechado, cancelamento que     |
//| perde a corrida ou fica sem resposta, deal sem magic, deal de    |
//| ordem desconhecida, leitura de historico/pendentes que falha,    |
//| conexao perdida.                                                 |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_CORRETORAFALSA_MQH
#define WINMAESTRO_CORRETORAFALSA_MQH

#include "Corretora.mqh"

#define FM_NORMAL           0
#define FM_RECUSA           1   // servidor responde REJECT; nada acontece
#define FM_DONE_SEM_DEAL    2   // mercado: DONE sem deal no retorno; o deal so' aparece no historico depois de MostraOcultos()
#define FM_TIMEOUT_TK0_EXEC 3   // timeout com ticket 0; a ordem EXECUTOU (ou ficou viva, se pendente)
#define FM_TIMEOUT_TK0_NADA 4   // timeout com ticket 0; nada aconteceu (tambem no cancelamento)
#define FM_EXECUTA_ANTES    5   // cancelamento: a ordem enche antes (o cancelamento perde a corrida)
#define FM_RETCODE          6   // responde m_rc (ex.: MARKET_CLOSED, TOO_MANY_REQUESTS); nada acontece

class CCorretoraFalsa : public CCorretora
{
public:
   long       m_msc;          // relogio do servidor em ms
   bool       m_mesmo_ms;     // eventos sem avancar o relogio (dois deals no mesmo ms)
   bool       m_conectado;
   bool       m_testador;
   bool       m_liq_falha;
   bool       m_hist_falha;
   bool       m_pend_falha;
   int        m_liq;
   double     m_bid, m_ask;
   SOrdemViva m_pend[];
   SDealInfo  m_deal[];
   bool       m_oculto[];     // deal fora do historico ate' MostraOcultos()
   SOrdemHist m_hist[];
   ulong      m_tk, m_dtk;
   uint       m_req;
   uint       m_rc;
   int        m_modos[];
   int        m_envios;
   long       m_tick_msc;     // instante do ultimo tick (0 = o relogio)
   bool       m_sem_coment;   // a corretora nao preserva o comentario (P3)
   bool       m_hedging;      // conta nao NETTING
   int        m_hist_n;       // leituras de historico
   int        m_liq_pico;     // maior |liquida| desde ZeraPico()

   CCorretoraFalsa(void)
   {
      m_msc = (long)D'2026.10.07 10:00:00' * 1000; m_mesmo_ms = false; m_conectado = true; m_testador = true;
      m_liq_falha = false; m_hist_falha = false; m_pend_falha = false; m_liq = 0;
      m_bid = 120000.0; m_ask = 120005.0; m_tk = 1000; m_dtk = 5000; m_req = 0; m_rc = 0; m_envios = 0;
      m_tick_msc = 0; m_sem_coment = false; m_hedging = false; m_hist_n = 0; m_liq_pico = 0;
   }

   // ---- comandos do teste ----
   void DefineAgora(const datetime t) { m_msc = (long)t * 1000; }
   void ZeraPico(void)                { m_liq_pico = (m_liq < 0 ? -m_liq : m_liq); }
   void Avanca(const int seg)         { m_msc += (long)seg * 1000; }
   void Roteiro(const int modo)       { int n = ArraySize(m_modos); ArrayResize(m_modos, n + 1); m_modos[n] = modo; }
   long Msc(void)                     { if(!m_mesmo_ms) m_msc++; return m_msc; }
   int  Lado(const int tipo)          { return (tipo == ORDER_TYPE_BUY || tipo == ORDER_TYPE_BUY_LIMIT || tipo == ORDER_TYPE_BUY_STOP || tipo == ORDER_TYPE_BUY_STOP_LIMIT) ? 1 : -1; }

   int PendIdx(const ulong tk)
   {
      int n = ArraySize(m_pend);
      for(int i = 0; i < n; i++) if(m_pend[i].ticket == tk) return i;
      return -1;
   }

   void RemovePend(const int i)
   {
      int n = ArraySize(m_pend);
      for(int k = i; k < n - 1; k++) m_pend[k] = m_pend[k + 1];
      ArrayResize(m_pend, n - 1);
   }

   ulong AddPend(const long magic, const int tipo, const double preco, const double vol, const string com)
   {
      m_tk++;
      int n = ArraySize(m_pend);
      ArrayResize(m_pend, n + 1);
      m_pend[n].ticket = m_tk; m_pend[n].magic = magic; m_pend[n].tipo = tipo; m_pend[n].preco = preco;
      m_pend[n].vol = vol; m_pend[n].setup_msc = Msc(); m_pend[n].comentario = m_sem_coment ? "" : com;
      return m_tk;
   }

   void AddHist(const ulong tk, const long magic, const int tipo, const double preco, const double vol, const long setup, const int estado, const string com)
   {
      int n = ArraySize(m_hist);
      ArrayResize(m_hist, n + 1);
      m_hist[n].ticket = tk; m_hist[n].magic = magic; m_hist[n].tipo = tipo; m_hist[n].preco = preco; m_hist[n].vol = vol;
      m_hist[n].setup_msc = setup; m_hist[n].done_msc = Msc(); m_hist[n].estado = estado; m_hist[n].comentario = com;
   }

   ulong AddDeal(const ulong ordem, const long magic, const int lado, const double vol, const double preco, const string com, const bool oculto)
   {
      int n = ArraySize(m_deal);
      ArrayResize(m_deal, n + 1); ArrayResize(m_oculto, n + 1);
      m_dtk++;
      m_deal[n].ticket = m_dtk; m_deal[n].ordem = ordem; m_deal[n].time_msc = Msc(); m_deal[n].magic = magic;
      m_deal[n].tipo = (lado > 0) ? DEAL_TYPE_BUY : DEAL_TYPE_SELL; m_deal[n].vol = vol; m_deal[n].preco = preco;
      m_deal[n].comissao = 0.0; m_deal[n].taxa = 0.0; m_deal[n].lucro = 0.0; m_deal[n].razao = 0; m_deal[n].comentario = com;
      m_oculto[n] = oculto;
      m_liq += lado * (int)MathRound(vol);
      int a = (m_liq < 0 ? -m_liq : m_liq);
      if(a > m_liq_pico) m_liq_pico = a;
      return m_dtk;
   }

   // Uma pendente executa no preco dela (stop disparado, limite cheia). sem_magic: o deal vem com DEAL_MAGIC 0 (P2).
   bool Dispara(const ulong tk, const bool sem_magic = false)
   {
      int i = PendIdx(tk);
      if(i < 0) return false;
      SOrdemViva o = m_pend[i];
      RemovePend(i);
      AddHist(o.ticket, o.magic, o.tipo, o.preco, o.vol, o.setup_msc, ORDER_STATE_FILLED, o.comentario);
      AddDeal(o.ticket, sem_magic ? 0 : o.magic, Lado(o.tipo), o.vol, o.preco, o.comentario, false);
      return true;
   }

   // Cancelamento feito por fora (dono, corretora, validade).
   bool CancelaPorFora(const ulong tk, const int estado)
   {
      int i = PendIdx(tk);
      if(i < 0) return false;
      SOrdemViva o = m_pend[i];
      RemovePend(i);
      AddHist(o.ticket, o.magic, o.tipo, o.preco, o.vol, o.setup_msc, estado, o.comentario);
      return true;
   }

   // Deal manual/externo (ordem a mercado com o magic dado; 0 = manual).
   ulong DealPorFora(const long magic, const int lado, const double vol, const double preco, const string com = "")
   {
      m_tk++;
      AddHist(m_tk, magic, lado > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, preco, vol, Msc(), ORDER_STATE_FILLED, com);
      return AddDeal(m_tk, magic, lado, vol, preco, com, false);
   }

   // Deal com magic de robo cuja ordem nao aparece no historico (ordem desconhecida, M-1).
   ulong DealSemOrdem(const long magic, const int lado, const double vol, const double preco)
   {
      m_tk++;
      return AddDeal(m_tk, magic, lado, vol, preco, "", false);
   }

   void MostraOcultos(void) { int n = ArraySize(m_oculto); for(int i = 0; i < n; i++) m_oculto[i] = false; }

   int ContaPend(void) { return ArraySize(m_pend); }
   int ContaPendTipo(const long magic, const int tipo)
   {
      int c = 0, n = ArraySize(m_pend);
      for(int i = 0; i < n; i++) if(m_pend[i].magic == magic && m_pend[i].tipo == tipo) c++;
      return c;
   }
   double VolPendTipo(const long magic, const int tipo)
   {
      double v = 0.0;
      int n = ArraySize(m_pend);
      for(int i = 0; i < n; i++) if(m_pend[i].magic == magic && m_pend[i].tipo == tipo) v += m_pend[i].vol;
      return v;
   }
   ulong TicketPend(const long magic, const int tipo)
   {
      int n = ArraySize(m_pend);
      for(int i = 0; i < n; i++) if(m_pend[i].magic == magic && m_pend[i].tipo == tipo) return m_pend[i].ticket;
      return 0;
   }
   int HistIdx(const ulong tk)
   {
      int n = ArraySize(m_hist);
      for(int i = 0; i < n; i++) if(m_hist[i].ticket == tk) return i;
      return -1;
   }

   // ---- interface CCorretora ----
   virtual datetime Agora(void)                { return (datetime)(m_msc / 1000); }
   virtual bool     Conectado(void)            { return m_conectado; }
   virtual bool     Testador(void)             { return m_testador; }
   virtual bool     LeLiquida(double &vol_assinado, double &preco)
   {
      if(m_liq_falha) return false;
      vol_assinado = (double)m_liq; preco = 0.0;
      return true;
   }
   virtual bool LePendentes(SOrdemViva &o[])
   {
      int n = ArraySize(m_pend);
      if(m_pend_falha) { ArrayResize(o, n > 0 ? n - 1 : 0); for(int i = 0; i < n - 1; i++) o[i] = m_pend[i + 1]; return false; }   // lista parcial + erro
      ArrayResize(o, n);
      for(int i = 0; i < n; i++) o[i] = m_pend[i];
      return true;
   }
   virtual bool LeHistorico(const datetime de, const datetime ate, SDealInfo &d[], SOrdemHist &o[])
   {
      ArrayResize(d, 0); ArrayResize(o, 0);
      m_hist_n++;
      if(m_hist_falha) return false;
      int n = ArraySize(m_deal);
      for(int i = 0; i < n; i++)
      {
         datetime t = (datetime)(m_deal[i].time_msc / 1000);
         if(m_oculto[i] || t < de || t > ate) continue;
         int k = ArraySize(d); ArrayResize(d, k + 1); d[k] = m_deal[i];
      }
      int nh = ArraySize(m_hist);
      for(int i = 0; i < nh; i++)
      {
         datetime t = (datetime)(m_hist[i].setup_msc / 1000);
         if(t < de || t > ate) continue;
         int k = ArraySize(o); ArrayResize(o, k + 1); o[k] = m_hist[i];
      }
      return true;
   }
   virtual bool LeOrdemHist(const ulong ticket, SOrdemHist &o)
   {
      if(m_hist_falha) return false;
      int i = HistIdx(ticket);
      if(i < 0) return false;
      o = m_hist[i];
      return true;
   }
   virtual bool Envia(MqlTradeRequest &req, MqlTradeResult &res)
   {
      ZeroMemory(res);
      m_envios++;
      m_req++;
      res.request_id = m_req;
      int modo = FM_NORMAL;
      int nm = ArraySize(m_modos);
      if(nm > 0)
      {
         modo = m_modos[0];
         for(int k = 0; k < nm - 1; k++) m_modos[k] = m_modos[k + 1];
         ArrayResize(m_modos, nm - 1);
      }
      if(modo == FM_RECUSA)  { res.retcode = TRADE_RETCODE_REJECT; return false; }
      if(modo == FM_RETCODE) { res.retcode = m_rc; return false; }
      if(req.action == TRADE_ACTION_PENDING)
      {
         if(modo == FM_TIMEOUT_TK0_NADA) { res.retcode = TRADE_RETCODE_TIMEOUT; return false; }
         ulong tk = AddPend((long)req.magic, (int)req.type, req.price, req.volume, req.comment);
         if(modo == FM_TIMEOUT_TK0_EXEC) { res.retcode = TRADE_RETCODE_TIMEOUT; return false; }
         res.order = tk; res.retcode = TRADE_RETCODE_PLACED;
         return true;
      }
      if(req.action == TRADE_ACTION_DEAL)
      {
         if(modo == FM_TIMEOUT_TK0_NADA) { res.retcode = TRADE_RETCODE_TIMEOUT; return false; }
         m_tk++;
         int lado = Lado((int)req.type);
         double preco = lado > 0 ? m_ask : m_bid;
         long setup = Msc();
         AddHist(m_tk, (long)req.magic, (int)req.type, preco, req.volume, setup, ORDER_STATE_FILLED, req.comment);
         ulong d = AddDeal(m_tk, (long)req.magic, lado, req.volume, preco, req.comment, modo == FM_DONE_SEM_DEAL);
         if(modo == FM_TIMEOUT_TK0_EXEC) { res.retcode = TRADE_RETCODE_TIMEOUT; return false; }
         res.order = m_tk; res.retcode = TRADE_RETCODE_DONE;
         res.deal = (modo == FM_DONE_SEM_DEAL) ? 0 : d;
         res.price = (modo == FM_DONE_SEM_DEAL) ? 0.0 : preco;
         return true;
      }
      if(req.action == TRADE_ACTION_REMOVE)
      {
         int i = PendIdx(req.order);
         if(i < 0) { res.retcode = TRADE_RETCODE_INVALID_ORDER; return false; }
         if(modo == FM_TIMEOUT_TK0_NADA) { res.retcode = TRADE_RETCODE_TIMEOUT; return false; }
         if(modo == FM_EXECUTA_ANTES) { Dispara(req.order); res.retcode = TRADE_RETCODE_INVALID_ORDER; return false; }
         CancelaPorFora(req.order, ORDER_STATE_CANCELED);
         res.order = req.order; res.retcode = TRADE_RETCODE_DONE;
         return true;
      }
      if(req.action == TRADE_ACTION_MODIFY)
      {
         int i = PendIdx(req.order);
         if(i < 0) { res.retcode = TRADE_RETCODE_INVALID_ORDER; return false; }
         // stop do lado errado do mercado e' recusado, como na bolsa
         if((m_pend[i].tipo == ORDER_TYPE_SELL_STOP && req.price >= m_bid) || (m_pend[i].tipo == ORDER_TYPE_BUY_STOP && req.price <= m_ask))
            { res.retcode = TRADE_RETCODE_INVALID_PRICE; return false; }
         m_pend[i].preco = req.price;
         res.order = req.order; res.retcode = TRADE_RETCODE_DONE;
         return true;
      }
      res.retcode = TRADE_RETCODE_INVALID;
      return false;
   }
   virtual double SimboloD(const ENUM_SYMBOL_INFO_DOUBLE p)
   {
      switch(p)
      {
         case SYMBOL_TRADE_TICK_SIZE:  return 5.0;
         case SYMBOL_TRADE_TICK_VALUE: return 1.0;
         case SYMBOL_POINT:            return 1.0;
         case SYMBOL_BID:              return m_bid;
         case SYMBOL_ASK:              return m_ask;
      }
      return 0.0;
   }
   virtual long SimboloI(const ENUM_SYMBOL_INFO_INTEGER p)
   {
      switch(p)
      {
         case SYMBOL_DIGITS:            return 0;
         case SYMBOL_TRADE_STOPS_LEVEL: return 0;
         case SYMBOL_TRADE_MODE:        return SYMBOL_TRADE_MODE_FULL;
         case SYMBOL_TRADE_EXEMODE:     return SYMBOL_TRADE_EXECUTION_EXCHANGE;
         case SYMBOL_FILLING_MODE:      return 0;
      }
      return 0;
   }
   virtual bool UltimoTick(MqlTick &t)
   {
      ZeroMemory(t);
      long ms = (m_tick_msc > 0) ? m_tick_msc : m_msc;
      t.bid = m_bid; t.ask = m_ask; t.time_msc = ms; t.time = (datetime)(ms / 1000);
      return true;
   }
   virtual long ContaI(const ENUM_ACCOUNT_INFO_INTEGER p)
   {
      if(p == ACCOUNT_LOGIN) return 123;
      if(p == ACCOUNT_MARGIN_MODE) return m_hedging ? ACCOUNT_MARGIN_MODE_RETAIL_HEDGING : ACCOUNT_MARGIN_MODE_RETAIL_NETTING;
      return 0;
   }
   virtual string ContaS(const ENUM_ACCOUNT_INFO_STRING p)  { return "FALSA"; }
   virtual bool   RoboEmOutroSimbolo(const long &magics[])   { return false; }
};

#endif
