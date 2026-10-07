//+------------------------------------------------------------------+
//| WinMaestro/Envia.mqh                                             |
//| Passos 5 e 6 do ciclo (sec. 3): a linha nova entra no mapa       |
//| (PENDENTE) e a linha ORDEM no log, com FileFlush, ANTES do       |
//| OrderSend; depois o envio sincrono, com o heartbeat gravado      |
//| imediatamente antes e depois (sec. 1.6). Recusa definitiva =     |
//| RECUSADA + em_espera[dono][papel] ate' RETENTA; ALERTA na 5a     |
//| recusa seguida e a cada 5 min. Qualquer outro retorno e' "nao    |
//| sei": a linha fica PENDENTE e o desfecho sai do passo 2.         |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_ENVIA_MQH
#define WINMAESTRO_ENVIA_MQH

#include "Estado.mqh"

void Trava_Hb(void);   // Partida.mqh

struct SAcao
{
   int      tipo;        // AC_*
   string   linha;       // P1, X3, ... (identificador da tabela da sec. 4.2 / passo da sec. 5)
   ulong    ticket;      // CANCELA, MOVE_*
   int      tipo_alvo;   // MOVE_*: tipo da ordem movida
   double   preco;
   int      lado;        // lado da ORDEM: +1 compra, -1 venda
   int      vol;
   long     id_entrada;
   datetime expira;
   string   motivo;
};

void Acao_Zera(SAcao &a) { a.tipo = AC_NENHUMA; a.linha = ""; a.ticket = 0; a.tipo_alvo = -1; a.preco = 0.0; a.lado = 0; a.vol = 0; a.id_entrada = 0; a.expira = 0; a.motivo = ""; }

// Retcodes em que o servidor respondeu "nao" (prova de recusa). Qualquer outro sem prova = "nao sei" (itens 1.6, 1.24).
bool Env_RecusaDefinitiva(const uint rc)
{
   switch(rc)
   {
      case TRADE_RETCODE_REQUOTE: case TRADE_RETCODE_REJECT: case TRADE_RETCODE_CANCEL: case TRADE_RETCODE_INVALID:
      case TRADE_RETCODE_INVALID_VOLUME: case TRADE_RETCODE_INVALID_PRICE: case TRADE_RETCODE_INVALID_STOPS:
      case TRADE_RETCODE_TRADE_DISABLED: case TRADE_RETCODE_MARKET_CLOSED: case TRADE_RETCODE_NO_MONEY:
      case TRADE_RETCODE_PRICE_CHANGED: case TRADE_RETCODE_PRICE_OFF: case TRADE_RETCODE_INVALID_EXPIRATION:
      case TRADE_RETCODE_ORDER_CHANGED: case TRADE_RETCODE_SERVER_DISABLES_AT: case TRADE_RETCODE_CLIENT_DISABLES_AT:
      case TRADE_RETCODE_FROZEN: case TRADE_RETCODE_INVALID_FILL: case TRADE_RETCODE_ONLY_REAL: case TRADE_RETCODE_LIMIT_ORDERS:
      case TRADE_RETCODE_LIMIT_VOLUME: case TRADE_RETCODE_INVALID_ORDER: case TRADE_RETCODE_POSITION_CLOSED:
      case TRADE_RETCODE_INVALID_CLOSE_VOLUME: case TRADE_RETCODE_CLOSE_ORDER_EXIST: case TRADE_RETCODE_LIMIT_POSITIONS:
      case TRADE_RETCODE_REJECT_CANCEL: case TRADE_RETCODE_LONG_ONLY: case TRADE_RETCODE_SHORT_ONLY:
      case TRADE_RETCODE_CLOSE_ONLY: case TRADE_RETCODE_FIFO_CLOSE: case TRADE_RETCODE_HEDGE_PROHIBITED:
      case TRADE_RETCODE_TOO_MANY_REQUESTS: case TRADE_RETCODE_LOCKED:
         return true;
   }
   return false;
}

int Env_ProxSeq(const int dono)
{
   datetime hoje = Mae_Dia(mzAgora);
   if(mzSeqDia != hoje) { for(int k = 0; k <= NROBOS; k++) mzSeq[k] = 0; mzSeqDia = hoje; }
   mzSeq[dono]++;
   return mzSeq[dono];
}

int Env_Papel(const int tipo_acao)
{
   switch(tipo_acao)
   {
      case AC_ENVIA_S: return P_S;
      case AC_ENVIA_E: return P_E;
      case AC_ENVIA_A: return P_A;
      case AC_ENVIA_X: case AC_C_CONTA: return P_X;
      case AC_MOVE_S: case AC_MOVE_A: return P_M;
      case AC_CANCELA: return P_K;
   }
   return 0;
}

// Linha ORDEM do log, em formato que a partida sem memoria rele (Partida.mqh: Mae_MapaDoLog).
string Env_LinhaLog(const int i)
{
   return StringFormat("envio lin=%I64d r=%s p=%s ep=%d ide=%I64d seq=%d tipo=%d preco=%.1f vol=%.0f alvo=%I64u msc=%I64d exp=%I64d mot=%s com=%s",
                       mzL[i].id, mzL[i].robo == R_MAE ? "MAE" : mzNome[mzL[i].robo], Mae_Papel(mzL[i].papel), mzL[i].episodio, mzL[i].id_entrada,
                       mzL[i].seq, mzL[i].tipo, mzL[i].preco, mzL[i].vol, mzL[i].alvo_ticket, mzL[i].enviado_msc, (long)mzL[i].expira,
                       mzL[i].motivo, mzL[i].coment);
}

// Executa a acao do dono (robo ou R_MAE). true = um OrderSend foi feito.
bool Env_Executa(const int dono, SAcao &a)
{
   int papel = Env_Papel(a.tipo);
   if(papel == 0) return false;
   //--- monta o pedido
   MqlTradeRequest req;
   ZeroMemory(req);
   req.symbol = _Symbol;
   req.magic = (ulong)mzMagic[dono];
   req.deviation = 0;
   int tipo = -1;
   double preco_linha = 0.0;
   double vol = 1.0;
   switch(a.tipo)
   {
      case AC_ENVIA_S:
         req.action = TRADE_ACTION_PENDING;
         tipo = a.lado > 0 ? ORDER_TYPE_BUY_STOP : ORDER_TYPE_SELL_STOP;
         req.price = a.preco; req.type_time = ORDER_TIME_DAY; req.type_filling = ORDER_FILLING_RETURN;
         preco_linha = a.preco;
         break;
      case AC_ENVIA_A:
         req.action = TRADE_ACTION_PENDING;
         tipo = a.lado > 0 ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
         req.price = a.preco; req.type_time = ORDER_TIME_DAY; req.type_filling = ORDER_FILLING_RETURN;
         preco_linha = a.preco;
         break;
      case AC_ENVIA_E:
         if(a.preco > 0.0)
         {
            req.action = TRADE_ACTION_PENDING;
            tipo = a.lado > 0 ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
            req.price = a.preco; req.type_filling = ORDER_FILLING_RETURN;
            if(a.expira > 0 && mzSpecifiedOk) { req.type_time = ORDER_TIME_SPECIFIED; req.expiration = a.expira; }
            else req.type_time = ORDER_TIME_DAY;
            preco_linha = a.preco;
         }
         else
         {
            req.action = TRADE_ACTION_DEAL;
            tipo = a.lado > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
            req.price = a.lado > 0 ? mzAsk : mzBid; req.type_filling = mzFillMercado;
         }
         break;
      case AC_ENVIA_X:
      case AC_C_CONTA:
         req.action = TRADE_ACTION_DEAL;
         tipo = a.lado > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
         req.price = a.lado > 0 ? mzAsk : mzBid; req.type_filling = mzFillMercado;
         vol = (double)a.vol;
         break;
      case AC_MOVE_S:
      case AC_MOVE_A:
         req.action = TRADE_ACTION_MODIFY;
         req.order = a.ticket; req.price = a.preco; req.type_time = ORDER_TIME_DAY;
         tipo = a.tipo_alvo;
         preco_linha = a.preco;
         break;
      case AC_CANCELA:
         req.action = TRADE_ACTION_REMOVE;
         req.order = a.ticket;
         break;
   }
   if(req.action != TRADE_ACTION_MODIFY && req.action != TRADE_ACTION_REMOVE) { req.type = (ENUM_ORDER_TYPE)tipo; req.volume = vol; }
   //--- episodio: aberto pela S de uma entrada ou de protecao (sec. 1.2)
   if(dono < NROBOS && papel == P_S && !mzEpAberto[dono])
   {
      mzEp[dono]++;
      mzEpAberto[dono] = true;
      Log("INFO", mzNome[dono], "EPISODIO", StringFormat("episodio %d aberto (%s)", mzEp[dono], a.linha));
   }
   //--- passo 5: registro ANTES do envio
   int seq = Env_ProxSeq(dono);
   int i = ArraySize(mzL);
   ArrayResize(mzL, i + 1);
   mzL[i].id = mzProxLinha++;
   mzL[i].robo = dono;
   mzL[i].papel = papel;
   mzL[i].episodio = (dono < NROBOS && mzEpAberto[dono]) ? mzEp[dono] : 0;
   mzL[i].id_entrada = a.id_entrada;
   mzL[i].seq = seq;
   mzL[i].coment = StringFormat("MAE|%s|%s|%04d", dono == R_MAE ? "MAE" : mzNome[dono], Mae_Papel(papel), seq);
   mzL[i].tipo = tipo;
   mzL[i].preco = preco_linha;
   mzL[i].vol = vol;
   mzL[i].alvo_ticket = (papel == P_K || papel == P_M) ? a.ticket : 0;
   mzL[i].enviado_msc = mzAgoraMsc;
   mzL[i].enviado_mono = mzMono;
   mzL[i].ticket = 0;
   mzL[i].request_id = 0;
   mzL[i].retcode = 0;
   mzL[i].desfecho = D_PENDENTE;
   mzL[i].sumida_msc = 0;
   mzL[i].sumida_mono = 0;
   mzL[i].prova = "";
   mzL[i].expira = (papel == P_E) ? a.expira : 0;
   mzL[i].motivo = (papel == P_X) ? a.motivo : a.linha;   // X: I1/I2/I3/MOD/C_CONTA (I2 = correcao); outros: a linha da tabela
   mzL[i].ev = 0;
   mzL[i].estado_hist = -1;
   if(papel != P_K && papel != P_M) req.comment = mzL[i].coment;
   Mae_GravaMemoria(true);
   Log_Cond("memoria.envio", !mzMemGravando, "ALERTA", "MAESTRO", "MEMORIA", "memoria nao grava: E e A nao saem; S, K, M e X saem com a linha do log");
   if(!mzMemGravando && (papel == P_E || papel == P_A))
   {
      ArrayResize(mzL, i);
      mzProxLinha--;
      mzSeq[dono]--;
      return false;
   }
   Log("INFO", mzNome[dono], "ORDEM", Env_LinhaLog(i) + StringFormat(" linha=%s %s", a.linha, a.motivo));
   //--- passo 6: envio sincrono, heartbeat em volta
   MqlTradeResult res;
   ZeroMemory(res);
   int liq_antes = mzLiq;
   Trava_Hb();
   bool ok = mzCorr.Envia(req, res);
   Trava_Hb();
   if(papel != P_K && papel != P_M) mzL[i].ticket = res.order;
   mzL[i].request_id = res.request_id;
   mzL[i].retcode = res.retcode;
   // OrderSend falso com retcode 0 (pedido mal formado no cliente) tambem e' recusa: nada chegou ao servidor (B-2)
   bool recusa = Env_RecusaDefinitiva(res.retcode) || (!ok && res.retcode == 0);
   if(recusa)
   {
      mzL[i].desfecho = D_RECUSADA;
      mzL[i].prova = StringFormat("rc %u", res.retcode);
      Rec_Registra(dono, papel, StringFormat("%s rc %u", Mae_Papel(papel), res.retcode), true);
   }
   Log(recusa ? "AVISO" : "INFO", mzNome[dono], "ORDEM", StringFormat("retorno lin=%I64d tk=%I64u deal=%I64u req=%u rc=%u/%d envio=%s %s pedido %.0f exec %.0f; liquida %+d",
       mzL[i].id, res.order, res.deal, res.request_id, res.retcode, res.retcode_external, ok ? "ok" : "falso",
       recusa ? "RECUSADA" : "sem desfecho ainda", req.price, res.price, liq_antes));
   Mae_GravaMemoria(true);
   return true;
}

#endif
