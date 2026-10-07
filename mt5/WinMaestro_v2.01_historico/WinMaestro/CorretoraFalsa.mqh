//+------------------------------------------------------------------+
//| WinMaestro/CorretoraFalsa.mqh                                    |
//| Corretora FALSA, com respostas roteirizadas (spec O15, sec. 12). |
//| So' entra no EA de teste WinMaestro_Teste.mq5; nunca no .ex5 de  |
//| producao. Simula conta NETTING de 1 simbolo: pendentes, deals,   |
//| ordens do historico, posicao, relogio em ms, e os modos de falha |
//| que o desenho v2.2 precisa provar:                               |
//|  - DONE sem deal (ordem FILLED no historico, deal atrasado);     |
//|  - execucao com historico E deal atrasados (so' a posicao muda); |
//|  - posicao atrasada em relacao ao deal (N-1);                    |
//|  - timeout com ticket 0 (executou ou nao), com/sem request_id;   |
//|  - ordem aceita que ainda nao aparece nas pendentes;             |
//|  - recusa, retcode roteirizado, cancelamento que perde a corrida;|
//|  - OrderModify que troca o ticket (P4);                          |
//|  - leitura de historico / pendentes / posicao que falha;         |
//|  - conexao perdida;                                              |
//|  (v2.01, A-3)                                                    |
//|  - execucao por PRECO (m_por_preco): Move() dispara as pendentes |
//|    atravessadas; no envio, stop do lado errado e' recusado e     |
//|    limite que cruza enche; m_stop_falha simula stop atravessado  |
//|    que nao executa;                                              |
//|  - recusa ASSINCRONA: aceita no envio (PLACED) e REJECTED no     |
//|    historico depois (modo de 1 envio ou persistente por magic);  |
//|  - K e M ASSINCRONOS (m_assinc_ms): respondem DONE e so' fazem   |
//|    efeito depois do atraso;                                      |
//|  - fila de transacoes (REQUEST, DEAL_ADD, HISTORY_ADD) que o     |
//|    teste entrega ao OnTradeTransaction do maestro.               |
//| A falsa NAO decide nada do maestro: so' guarda o que a "bolsa"   |
//| fez. Toda conclusao do teste sai do codigo do maestro.           |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_CORRETORAFALSA_MQH
#define WINMAESTRO_CORRETORAFALSA_MQH

#include "Corretora.mqh"

#define FM_NORMAL           0
#define FM_RECUSA           1   // servidor responde REJECT; nada acontece
#define FM_DONE_SEM_DEAL    2   // mercado: DONE; ordem FILLED no historico; o deal so' aparece depois de MostraOcultos()
#define FM_TIMEOUT_TK0_EXEC 3   // timeout com ticket 0; a ordem EXECUTOU (mercado) ou ficou viva (pendente)
#define FM_TIMEOUT_TK0_NADA 4   // timeout com ticket 0; nada aconteceu
#define FM_EXECUTA_ANTES    5   // cancelamento: a ordem enche antes (o cancelamento perde a corrida)
#define FM_RETCODE          6   // responde m_rc; nada acontece
#define FM_TUDO_OCULTO      7   // mercado: executa; historico e deal so' aparecem depois de MostraOcultos() (a posicao muda na hora)
#define FM_MODIFICA_TROCA   8   // OrderModify: a ordem ganha ticket novo (P4)
#define FM_PEND_OCULTA      9   // pendente aceita (PLACED) mas so' aparece na lista depois de MostraPend()
#define FM_ACEITA_RECUSA   10   // aceita (PLACED) e o historico mostra REJECTED depois de m_rej_ms (recusa assincrona, A-2)
#define FM_TK0_OCULTA      11   // pendente: timeout com ticket 0 e a ordem so' aparece nas vivas depois de MostraPend()

#define AQ_REJEITA   1          // fila assincrona: pendente -> REJECTED
#define AQ_MOSTRA    2          // fila assincrona: ordem a mercado REJECTED (oculta) aparece no historico
#define AQ_REMOVE    3          // fila assincrona: K
#define AQ_MODIFICA  4          // fila assincrona: M

class CCorretoraFalsa : public CCorretora
{
public:
   long       m_msc;          // relogio do servidor em ms
   bool       m_conectado;
   bool       m_testador;
   bool       m_liq_falha;
   bool       m_hist_falha;
   bool       m_pend_falha;
   int        m_liq;          // posicao real
   bool       m_liq_congela;  // LeLiquida devolve m_liq_vista (posicao atrasada, N-1)
   int        m_liq_vista;
   double     m_bid, m_ask, m_last;
   long       m_tick_msc;     // instante do ultimo tick (0 = o relogio)
   SOrdemViva m_pend[];
   bool       m_pend_oculta[];
   SDealInfo  m_deal[];
   bool       m_deal_oculto[];
   SOrdemHist m_hist[];
   bool       m_hist_oculto[];
   ulong      m_tk, m_dtk;
   uint       m_req;
   uint       m_rc;
   bool       m_req_no_timeout;  // TIMEOUT devolve request_id? (o MT5 real nao garante: padrao false)
   int        m_modos[];
   int        m_envios;
   bool       m_hedging;
   long       m_trade_mode;
   long       m_exp_mode;
   long       m_stops_level;
   double     m_tick_size;
   long       m_recusa_magic;    // != 0: recusa (REJECT) os pedidos deste magic...
   int        m_recusa_tipo;     // ...deste tipo de ordem (-1 = todos os pedidos do magic, inclusive cancelar e modificar)
   long       m_login;
   long       m_desvio_ms;       // relogio do PC adiantado/atrasado em relacao ao monotonico (M-4)
   // execucao por preco, recusa assincrona, K/M assincronos (A-3)
   bool       m_por_preco;       // Move() executa as pendentes atravessadas; o envio valida o preco (padrao false: testes da v2.00)
   bool       m_stop_falha;      // com m_por_preco: stop atravessado nao executa
   long       m_assinc_ms;       // > 0: K e M respondem DONE e fazem efeito so' depois deste atraso
   long       m_rej_magic;       // != 0: os PENDING/DEAL deste magic...
   int        m_rej_tipo;        // ...deste tipo (-1 = todos) sao aceitos e REJECTED depois de m_rej_ms
   long       m_rej_ms;
   int        m_aq_op[];
   ulong      m_aq_tk[];
   double     m_aq_preco[];
   long       m_aq_quando[];
   // transacoes que o terminal entregaria ao OnTradeTransaction (o teste as entrega com Entrega())
   MqlTradeTransaction m_tq_t[];
   MqlTradeRequest     m_tq_q[];
   MqlTradeResult      m_tq_r[];
   bool       m_tq_emite;        // o envio atual emite REQUEST (o pedido chegou ao servidor)
   ulong      m_tq_ord;          // ordem real do envio atual (inclusive a do timeout com ticket 0)

   CCorretoraFalsa(void)
   {
      m_msc = (long)D'2026.10.07 10:00:00' * 1000; m_conectado = true; m_testador = false;
      m_liq_falha = false; m_hist_falha = false; m_pend_falha = false; m_liq = 0; m_liq_congela = false; m_liq_vista = 0;
      m_bid = 120000.0; m_ask = 120005.0; m_last = 120000.0; m_tick_msc = 0;
      m_tk = 1000; m_dtk = 5000; m_req = 0; m_rc = 0; m_req_no_timeout = false; m_envios = 0;
      m_hedging = false; m_trade_mode = SYMBOL_TRADE_MODE_FULL; m_exp_mode = SYMBOL_EXPIRATION_DAY; m_stops_level = 0; m_tick_size = 5.0;
      m_recusa_magic = 0; m_recusa_tipo = -1; m_login = 123; m_desvio_ms = 0;
      m_por_preco = false; m_stop_falha = false; m_assinc_ms = 0; m_rej_magic = 0; m_rej_tipo = -1; m_rej_ms = 0;
      m_tq_emite = false; m_tq_ord = 0;
   }

   // ---- transacoes ----
   void Trans(const ENUM_TRADE_TRANSACTION_TYPE tipo, const ulong ordem, const ulong deal, const int estado, const MqlTradeRequest &q, const MqlTradeResult &r)
   {
      int n = ArraySize(m_tq_t);
      ArrayResize(m_tq_t, n + 1); ArrayResize(m_tq_q, n + 1); ArrayResize(m_tq_r, n + 1);
      ZeroMemory(m_tq_t[n]);
      m_tq_t[n].type = tipo; m_tq_t[n].order = ordem; m_tq_t[n].deal = deal; m_tq_t[n].symbol = _Symbol;
      m_tq_t[n].order_state = (ENUM_ORDER_STATE)estado;
      m_tq_q[n] = q; m_tq_r[n] = r;
   }
   void TransSimples(const ENUM_TRADE_TRANSACTION_TYPE tipo, const ulong ordem, const ulong deal, const int estado)
   {
      MqlTradeRequest q; MqlTradeResult r; ZeroMemory(q); ZeroMemory(r);
      Trans(tipo, ordem, deal, estado, q, r);
   }
   void LimpaTrans(void) { ArrayResize(m_tq_t, 0); ArrayResize(m_tq_q, 0); ArrayResize(m_tq_r, 0); }

   // ---- fila assincrona ----
   void Fila(const int op, const ulong tk, const double preco, const long atraso)
   {
      int n = ArraySize(m_aq_op);
      ArrayResize(m_aq_op, n + 1); ArrayResize(m_aq_tk, n + 1); ArrayResize(m_aq_preco, n + 1); ArrayResize(m_aq_quando, n + 1);
      m_aq_op[n] = op; m_aq_tk[n] = tk; m_aq_preco[n] = preco; m_aq_quando[n] = m_msc + atraso;
   }
   // Aplica o que venceu (chamado em toda leitura: o efeito assincrono aparece "entre" duas leituras do maestro).
   void Processa(void)
   {
      int n = ArraySize(m_aq_op), w = 0;
      for(int k = 0; k < n; k++)
      {
         if(m_aq_quando[k] > m_msc)
         {
            m_aq_op[w] = m_aq_op[k]; m_aq_tk[w] = m_aq_tk[k]; m_aq_preco[w] = m_aq_preco[k]; m_aq_quando[w] = m_aq_quando[k]; w++;
            continue;
         }
         ulong tk = m_aq_tk[k];
         int i = PendIdx(tk);
         if(m_aq_op[k] == AQ_REJEITA && i >= 0)   CancelaPorFora(tk, ORDER_STATE_REJECTED);
         if(m_aq_op[k] == AQ_REMOVE && i >= 0)    CancelaPorFora(tk, ORDER_STATE_CANCELED);
         if(m_aq_op[k] == AQ_MODIFICA && i >= 0)  m_pend[i].preco = m_aq_preco[k];
         if(m_aq_op[k] == AQ_MOSTRA)
         {
            int h = HistIdx(tk);
            if(h >= 0) { m_hist_oculto[h] = false; TransSimples(TRADE_TRANSACTION_HISTORY_ADD, tk, 0, ORDER_STATE_REJECTED); }
         }
      }
      ArrayResize(m_aq_op, w); ArrayResize(m_aq_tk, w); ArrayResize(m_aq_preco, w); ArrayResize(m_aq_quando, w);
   }

   // ---- execucao por preco ----
   // A ordem esta' atravessada pelo preco atual? (stop de venda: bid <= preco; de compra: ask >= preco;
   // limite de compra: ask <= preco; de venda: bid >= preco)
   bool Atravessada(const int tipo, const double preco)
   {
      switch(tipo)
      {
         case ORDER_TYPE_SELL_STOP:  return m_bid <= preco;
         case ORDER_TYPE_BUY_STOP:   return m_ask >= preco;
         case ORDER_TYPE_BUY_LIMIT:  return m_ask <= preco;
         case ORDER_TYPE_SELL_LIMIT: return m_bid >= preco;
      }
      return false;
   }
   void ExecutaPorPreco(void)
   {
      if(!m_por_preco) return;
      bool achou = true;
      while(achou)
      {
         achou = false;
         int n = ArraySize(m_pend);
         for(int i = 0; i < n; i++)
         {
            bool stop = m_pend[i].tipo == ORDER_TYPE_SELL_STOP || m_pend[i].tipo == ORDER_TYPE_BUY_STOP;
            if(m_pend_oculta[i] || (stop && m_stop_falha) || !Atravessada(m_pend[i].tipo, m_pend[i].preco)) continue;
            Dispara(m_pend[i].ticket);
            achou = true;
            break;
         }
      }
   }
   // O mercado anda: com m_por_preco, executa o que ele atravessou.
   void Move(const double bid, const double ask) { Precos(bid, ask); ExecutaPorPreco(); }

   // ---- comandos do teste ----
   void DefineAgora(const datetime t) { m_msc = (long)t * 1000; }
   void AvancaMs(const long ms)       { m_msc += ms; }
   void Avanca(const int seg)         { m_msc += (long)seg * 1000; }
   void Roteiro(const int modo)       { int n = ArraySize(m_modos); ArrayResize(m_modos, n + 1); m_modos[n] = modo; }
   long Msc(void)                     { m_msc++; return m_msc; }
   int  Lado(const int tipo)          { return (tipo == ORDER_TYPE_BUY || tipo == ORDER_TYPE_BUY_LIMIT || tipo == ORDER_TYPE_BUY_STOP || tipo == ORDER_TYPE_BUY_STOP_LIMIT) ? 1 : -1; }
   void Precos(const double bid, const double ask) { m_bid = bid; m_ask = ask; m_last = bid; }

   int PendIdx(const ulong tk)
   {
      int n = ArraySize(m_pend);
      for(int i = 0; i < n; i++) if(m_pend[i].ticket == tk) return i;
      return -1;
   }
   int HistIdx(const ulong tk)
   {
      int n = ArraySize(m_hist);
      for(int i = 0; i < n; i++) if(m_hist[i].ticket == tk) return i;
      return -1;
   }
   void RemovePend(const int i)
   {
      int n = ArraySize(m_pend);
      for(int k = i; k < n - 1; k++) { m_pend[k] = m_pend[k + 1]; m_pend_oculta[k] = m_pend_oculta[k + 1]; }
      ArrayResize(m_pend, n - 1); ArrayResize(m_pend_oculta, n - 1);
   }
   ulong AddPend(const long magic, const int tipo, const double preco, const double vol, const string com, const bool oculta)
   {
      m_tk++;
      int n = ArraySize(m_pend);
      ArrayResize(m_pend, n + 1); ArrayResize(m_pend_oculta, n + 1);
      m_pend[n].ticket = m_tk; m_pend[n].magic = magic; m_pend[n].tipo = tipo; m_pend[n].preco = preco;
      m_pend[n].vol = vol; m_pend[n].setup_msc = Msc(); m_pend[n].comentario = com;
      m_pend_oculta[n] = oculta;
      return m_tk;
   }
   void AddHist(const ulong tk, const long magic, const int tipo, const double preco, const double vol, const long setup, const int estado,
                const string com, const bool oculto)
   {
      int n = ArraySize(m_hist);
      ArrayResize(m_hist, n + 1); ArrayResize(m_hist_oculto, n + 1);
      m_hist[n].ticket = tk; m_hist[n].magic = magic; m_hist[n].tipo = tipo; m_hist[n].preco = preco; m_hist[n].vol = vol;
      m_hist[n].setup_msc = setup; m_hist[n].done_msc = Msc(); m_hist[n].estado = estado; m_hist[n].comentario = com;
      m_hist_oculto[n] = oculto;
      if(!oculto) TransSimples(TRADE_TRANSACTION_HISTORY_ADD, tk, 0, estado);
   }
   ulong AddDeal(const ulong ordem, const long magic, const int lado, const double vol, const double preco, const bool oculto)
   {
      int n = ArraySize(m_deal);
      ArrayResize(m_deal, n + 1); ArrayResize(m_deal_oculto, n + 1);
      m_dtk++;
      m_deal[n].ticket = m_dtk; m_deal[n].ordem = ordem; m_deal[n].time_msc = Msc(); m_deal[n].magic = magic;
      m_deal[n].tipo = (lado > 0) ? DEAL_TYPE_BUY : DEAL_TYPE_SELL; m_deal[n].vol = vol; m_deal[n].preco = preco;
      m_deal[n].comissao = 0.0; m_deal[n].taxa = 0.0; m_deal[n].lucro = 0.0; m_deal[n].razao = 0; m_deal[n].comentario = "";
      m_deal_oculto[n] = oculto;
      m_liq += lado * (int)MathRound(vol);
      if(!oculto) TransSimples(TRADE_TRANSACTION_DEAL_ADD, ordem, m_dtk, ORDER_STATE_FILLED);
      return m_dtk;
   }

   // Uma pendente executa no preco dela (stop disparado, limite cheia).
   // oculto_hist/oculto_deal: historico e deal so' aparecem depois de MostraOcultos().
   bool Dispara(const ulong tk, const bool oculto_hist = false, const bool oculto_deal = false, const bool sem_magic = false)
   {
      int i = PendIdx(tk);
      if(i < 0) return false;
      SOrdemViva o = m_pend[i];
      RemovePend(i);
      AddHist(o.ticket, o.magic, o.tipo, o.preco, o.vol, o.setup_msc, ORDER_STATE_FILLED, o.comentario, oculto_hist);
      AddDeal(o.ticket, sem_magic ? 0 : o.magic, Lado(o.tipo), o.vol, o.preco, oculto_deal);
      return true;
   }
   // Cancelamento feito por fora (dono, corretora, validade). oculto: some das pendentes sem estado no historico ainda.
   bool CancelaPorFora(const ulong tk, const int estado, const bool oculto = false)
   {
      int i = PendIdx(tk);
      if(i < 0) return false;
      SOrdemViva o = m_pend[i];
      RemovePend(i);
      AddHist(o.ticket, o.magic, o.tipo, o.preco, o.vol, o.setup_msc, estado, o.comentario, oculto);
      return true;
   }
   // Deal manual/externo (ordem a mercado com o magic dado; 0 = manual). sem_ordem: a ordem nao aparece no historico.
   ulong DealPorFora(const long magic, const int lado, const double vol, const double preco, const bool sem_ordem = false, const bool oculto = false)
   {
      m_tk++;
      if(!sem_ordem) AddHist(m_tk, magic, lado > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, preco, vol, Msc(), ORDER_STATE_FILLED, "", oculto);
      return AddDeal(m_tk, magic, lado, vol, preco, oculto);
   }
   // Ordem pendente posta "a mao" com um magic (fora do mapa do maestro).
   ulong PendPorFora(const long magic, const int tipo, const double preco) { return AddPend(magic, tipo, preco, 1.0, "", false); }

   void MostraOcultos(void)
   {
      for(int i = 0; i < ArraySize(m_deal_oculto); i++) m_deal_oculto[i] = false;
      for(int i = 0; i < ArraySize(m_hist_oculto); i++) m_hist_oculto[i] = false;
   }
   void MostraHist(void)  { for(int i = 0; i < ArraySize(m_hist_oculto); i++) m_hist_oculto[i] = false; }
   void MostraPend(void)  { for(int i = 0; i < ArraySize(m_pend_oculta); i++) m_pend_oculta[i] = false; }
   void CongelaLiq(void)  { m_liq_congela = true; m_liq_vista = m_liq; }
   void MostraLiq(void)   { m_liq_congela = false; m_liq_vista = m_liq; }

   int ContaPend(void) { return ArraySize(m_pend); }
   int ContaPendTipo(const long magic, const int tipo)
   {
      int c = 0, n = ArraySize(m_pend);
      for(int i = 0; i < n; i++) if(m_pend[i].magic == magic && m_pend[i].tipo == tipo) c++;
      return c;
   }
   ulong TicketPend(const long magic, const int tipo)
   {
      int n = ArraySize(m_pend);
      for(int i = 0; i < n; i++) if(m_pend[i].magic == magic && m_pend[i].tipo == tipo) return m_pend[i].ticket;
      return 0;
   }
   double PrecoPend(const ulong tk) { int i = PendIdx(tk); return i < 0 ? 0.0 : m_pend[i].preco; }
   int EstadoHist(const ulong tk)   { int i = HistIdx(tk); return i < 0 ? -1 : m_hist[i].estado; }
   // Quantas ordens o maestro mandou (todas as acoes: TRADE_ACTION_*), desde o ultimo zero.
   void ZeraEnvios(void) { m_envios = 0; }

   // ---- interface CCorretora ----
   virtual datetime Agora(void)                { return (datetime)((m_msc + m_desvio_ms) / 1000); }
   virtual long     AgoraMsc(void)             { return m_msc + m_desvio_ms; }
   virtual long     Mono(void)                 { return m_msc; }
   virtual bool     Conectado(void)            { return m_conectado; }
   virtual bool     Testador(void)             { return m_testador; }
   virtual bool     LeLiquida(double &vol_assinado, double &preco)
   {
      Processa();
      if(m_liq_falha) return false;
      vol_assinado = (double)(m_liq_congela ? m_liq_vista : m_liq); preco = 0.0;
      return true;
   }
   virtual bool LePendentes(SOrdemViva &o[])
   {
      ArrayResize(o, 0);
      Processa();
      if(m_pend_falha) return false;
      int n = ArraySize(m_pend);
      for(int i = 0; i < n; i++)
      {
         if(m_pend_oculta[i]) continue;
         int k = ArraySize(o); ArrayResize(o, k + 1); o[k] = m_pend[i];
      }
      return true;
   }
   virtual bool LeHistorico(const datetime de, const datetime ate, SDealInfo &d[], SOrdemHist &o[])
   {
      ArrayResize(d, 0); ArrayResize(o, 0);
      Processa();
      if(m_hist_falha) return false;
      int n = ArraySize(m_deal);
      for(int i = 0; i < n; i++)
      {
         datetime t = (datetime)(m_deal[i].time_msc / 1000);
         if(m_deal_oculto[i] || t < de || t > ate) continue;
         int k = ArraySize(d); ArrayResize(d, k + 1); d[k] = m_deal[i];
      }
      int nh = ArraySize(m_hist);
      for(int i = 0; i < nh; i++)
      {
         datetime t = (datetime)(m_hist[i].setup_msc / 1000);
         if(m_hist_oculto[i] || t < de || t > ate) continue;
         int k = ArraySize(o); ArrayResize(o, k + 1); o[k] = m_hist[i];
      }
      return true;
   }
   // Envio + a transacao REQUEST que o terminal entregaria (com o ticket real, inclusive no timeout de ticket 0).
   virtual bool Envia(MqlTradeRequest &req, MqlTradeResult &res)
   {
      m_tq_emite = false; m_tq_ord = 0;
      bool ok = EnviaX(req, res);
      if(m_tq_emite)
      {
         MqlTradeResult r = res;
         r.order = m_tq_ord;
         Trans(TRADE_TRANSACTION_REQUEST, m_tq_ord, 0, 0, req, r);
      }
      return ok;
   }
   bool EnviaX(MqlTradeRequest &req, MqlTradeResult &res)
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
      if(!m_conectado) { res.retcode = TRADE_RETCODE_CONNECTION; res.request_id = 0; return false; }
      if(modo != FM_TIMEOUT_TK0_NADA) { m_tq_emite = true; m_tq_ord = req.order; }
      if(modo == FM_RECUSA)  { res.retcode = TRADE_RETCODE_REJECT; return false; }
      if(m_recusa_magic != 0 && (long)req.magic == m_recusa_magic &&
         (m_recusa_tipo < 0 || ((req.action == TRADE_ACTION_PENDING || req.action == TRADE_ACTION_DEAL) && (int)req.type == m_recusa_tipo)))
         { res.retcode = TRADE_RETCODE_REJECT; return false; }
      if(modo == FM_RETCODE) { res.retcode = m_rc; return false; }
      bool rej = modo == FM_ACEITA_RECUSA ||
                 (m_rej_magic != 0 && (long)req.magic == m_rej_magic && (m_rej_tipo < 0 || (int)req.type == m_rej_tipo));
      if(req.action == TRADE_ACTION_PENDING)
      {
         if(modo == FM_TIMEOUT_TK0_NADA) { res.retcode = TRADE_RETCODE_TIMEOUT; if(!m_req_no_timeout) res.request_id = 0; return false; }
         // por preco: stop do lado errado do mercado e' recusado na hora, como na bolsa
         if(m_por_preco && ((req.type == ORDER_TYPE_SELL_STOP && req.price >= m_bid) || (req.type == ORDER_TYPE_BUY_STOP && req.price <= m_ask)))
            { res.retcode = TRADE_RETCODE_INVALID_PRICE; return false; }
         ulong tk = AddPend((long)req.magic, (int)req.type, req.price, req.volume, req.comment, modo == FM_PEND_OCULTA || modo == FM_TK0_OCULTA);
         m_tq_ord = tk;
         if(modo == FM_TIMEOUT_TK0_EXEC || modo == FM_TK0_OCULTA) { res.retcode = TRADE_RETCODE_TIMEOUT; if(!m_req_no_timeout) res.request_id = 0; return false; }
         res.order = tk; res.retcode = TRADE_RETCODE_PLACED;
         if(rej) { Fila(AQ_REJEITA, tk, 0.0, m_rej_ms); return true; }
         // por preco: limite que cruza o mercado enche na hora (no preco dela)
         if(m_por_preco && (req.type == ORDER_TYPE_BUY_LIMIT || req.type == ORDER_TYPE_SELL_LIMIT) && Atravessada((int)req.type, req.price)) Dispara(tk);
         return true;
      }
      if(req.action == TRADE_ACTION_DEAL)
      {
         if(modo == FM_TIMEOUT_TK0_NADA) { res.retcode = TRADE_RETCODE_TIMEOUT; if(!m_req_no_timeout) res.request_id = 0; return false; }
         m_tk++;
         m_tq_ord = m_tk;
         int lado = Lado((int)req.type);
         if(rej)
         {
            // a ordem a mercado e' aceita (PLACED) e o historico so' mostra REJECTED depois de m_rej_ms; nenhum deal
            AddHist(m_tk, (long)req.magic, (int)req.type, lado > 0 ? m_ask : m_bid, req.volume, Msc(), ORDER_STATE_REJECTED, req.comment, true);
            Fila(AQ_MOSTRA, m_tk, 0.0, m_rej_ms);
            res.order = m_tk; res.retcode = TRADE_RETCODE_PLACED;
            return true;
         }
         double preco = lado > 0 ? m_ask : m_bid;
         long setup = Msc();
         bool oc_hist = (modo == FM_TUDO_OCULTO);
         bool oc_deal = (modo == FM_DONE_SEM_DEAL || modo == FM_TUDO_OCULTO);
         AddHist(m_tk, (long)req.magic, (int)req.type, preco, req.volume, setup, ORDER_STATE_FILLED, req.comment, oc_hist);
         ulong d = AddDeal(m_tk, (long)req.magic, lado, req.volume, preco, oc_deal);
         if(modo == FM_TIMEOUT_TK0_EXEC) { res.retcode = TRADE_RETCODE_TIMEOUT; if(!m_req_no_timeout) res.request_id = 0; return false; }
         res.order = m_tk; res.retcode = TRADE_RETCODE_DONE;
         res.deal = oc_deal ? 0 : d;
         res.price = oc_deal ? 0.0 : preco;
         return true;
      }
      if(req.action == TRADE_ACTION_REMOVE)
      {
         int i = PendIdx(req.order);
         if(i < 0) { res.retcode = TRADE_RETCODE_INVALID_ORDER; return false; }
         if(modo == FM_TIMEOUT_TK0_NADA) { res.retcode = TRADE_RETCODE_TIMEOUT; return false; }
         if(modo == FM_EXECUTA_ANTES) { Dispara(req.order); res.retcode = TRADE_RETCODE_INVALID_ORDER; return false; }
         if(m_assinc_ms > 0) { Fila(AQ_REMOVE, req.order, 0.0, m_assinc_ms); res.order = req.order; res.retcode = TRADE_RETCODE_DONE; return true; }
         CancelaPorFora(req.order, ORDER_STATE_CANCELED);
         res.order = req.order; res.retcode = TRADE_RETCODE_DONE;
         return true;
      }
      if(req.action == TRADE_ACTION_MODIFY)
      {
         int i = PendIdx(req.order);
         if(i < 0) { res.retcode = TRADE_RETCODE_INVALID_ORDER; return false; }
         if(modo == FM_TIMEOUT_TK0_NADA) { res.retcode = TRADE_RETCODE_TIMEOUT; return false; }
         // stop do lado errado do mercado e' recusado, como na bolsa
         if((m_pend[i].tipo == ORDER_TYPE_SELL_STOP && req.price >= m_bid) || (m_pend[i].tipo == ORDER_TYPE_BUY_STOP && req.price <= m_ask))
            { res.retcode = TRADE_RETCODE_INVALID_PRICE; return false; }
         if(modo == FM_MODIFICA_TROCA)
         {
            SOrdemViva o = m_pend[i];
            RemovePend(i);
            AddHist(o.ticket, o.magic, o.tipo, o.preco, o.vol, o.setup_msc, ORDER_STATE_CANCELED, o.comentario, false);
            AddPend(o.magic, o.tipo, req.price, o.vol, o.comentario, false);
            res.order = req.order; res.retcode = TRADE_RETCODE_DONE;
            return true;
         }
         if(m_assinc_ms > 0) { Fila(AQ_MODIFICA, req.order, req.price, m_assinc_ms); res.order = req.order; res.retcode = TRADE_RETCODE_DONE; return true; }
         m_pend[i].preco = req.price;
         res.order = req.order; res.retcode = TRADE_RETCODE_DONE;
         ExecutaPorPreco();
         return true;
      }
      res.retcode = TRADE_RETCODE_INVALID;
      return false;
   }
   virtual double SimboloD(const ENUM_SYMBOL_INFO_DOUBLE p)
   {
      switch(p)
      {
         case SYMBOL_TRADE_TICK_SIZE:  return m_tick_size;
         case SYMBOL_TRADE_TICK_VALUE: return 1.0;
         case SYMBOL_POINT:            return 1.0;
         case SYMBOL_BID:              return m_bid;
         case SYMBOL_ASK:              return m_ask;
         case SYMBOL_LAST:             return m_last;
      }
      return 0.0;
   }
   virtual long SimboloI(const ENUM_SYMBOL_INFO_INTEGER p)
   {
      switch(p)
      {
         case SYMBOL_DIGITS:            return 0;
         case SYMBOL_TRADE_STOPS_LEVEL: return m_stops_level;
         case SYMBOL_TRADE_MODE:        return m_trade_mode;
         case SYMBOL_TRADE_EXEMODE:     return SYMBOL_TRADE_EXECUTION_EXCHANGE;
         case SYMBOL_FILLING_MODE:      return 0;
         case SYMBOL_EXPIRATION_MODE:   return m_exp_mode;
      }
      return 0;
   }
   virtual bool UltimoTick(MqlTick &t)
   {
      ZeroMemory(t);
      long ms = (m_tick_msc > 0) ? m_tick_msc : m_msc;
      t.bid = m_bid; t.ask = m_ask; t.last = m_last; t.time_msc = ms; t.time = (datetime)(ms / 1000);
      return true;
   }
   virtual long ContaI(const ENUM_ACCOUNT_INFO_INTEGER p)
   {
      if(p == ACCOUNT_LOGIN) return m_login;
      if(p == ACCOUNT_MARGIN_MODE) return m_hedging ? ACCOUNT_MARGIN_MODE_RETAIL_HEDGING : ACCOUNT_MARGIN_MODE_RETAIL_NETTING;
      return 0;
   }
   virtual string ContaS(const ENUM_ACCOUNT_INFO_STRING p)  { return "FALSA"; }
   virtual bool   RoboEmOutroSimbolo(const long &magics[])   { return false; }
};

#endif
