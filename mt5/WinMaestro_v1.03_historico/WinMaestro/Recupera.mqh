//+------------------------------------------------------------------+
//| WinMaestro/Recupera.mqh                                          |
//| Trava (sec. 10.3), sequencia de partida (sec. 10.2), painel (O7).        |
//| A sequencia anda pelo timer; nenhum Tick() e nenhuma entrada     |
//| antes do passo 11 (PRONTO).                                      |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_RECUPERA_MQH
#define WINMAESTRO_RECUPERA_MQH

#include "Fichas.mqh"

// gancho do EA: Init() de cada modulo com o estado restaurado (marca mzFalhou[r] quando falha)
void Robo_InitTodos(void);

string   mzTravaNome = "";
string   mzHbNome = "";
double   mzToken = 0.0;
int      mzPasso = 0;               // 0 = parado; 1..11 = passo em curso; 12 = pronto
datetime mzPassoDesde = 0;
datetime mzPassoLog = 0;
bool     mzPassoAlertou = false;
datetime mzAmbUlt = 0;

//+------------------------------------------------------------------+
//| Trava (D3)                                                       |
//+------------------------------------------------------------------+
bool Trava_Toma(void)
{
   if(mzCorr.Testador()) { mzIniciou = true; Log("INFO", "MAESTRO", "TRAVA", "Testador: trava pulada (P16)"); return true; }
   string conta = StringFormat("%I64d", mzCorr.ContaI(ACCOUNT_LOGIN));
   mzTravaNome = "WinMaestro.lock." + conta + "." + _Symbol;
   mzHbNome    = "WinMaestro.hb." + conta + "." + _Symbol;
   long cid = ChartID();
   uint tk = (uint)(cid ^ (cid >> 32));
   if(tk == 0) tk = 1;
   mzToken = (double)tk;
   if(!GlobalVariableCheck(mzTravaNome)) GlobalVariableSet(mzTravaNome, 0.0);
   bool ok = GlobalVariableSetOnCondition(mzTravaNome, mzToken, 0.0);
   if(!ok)
   {
      double v = GlobalVariableGet(mzTravaNome);
      if(v == mzToken) ok = true;                                // mesmo grafico (reinicio por input ou timeframe)
      else
      {
         double hb = GlobalVariableCheck(mzHbNome) ? GlobalVariableGet(mzHbNome) : 0.0;
         if((double)TimeLocal() - hb < 10.0)
         {
            string m = StringFormat("WinMaestro ja' roda em outro grafico deste terminal (%s, conta %s): esta instancia recusada", _Symbol, conta);
            Alert(m);
            Print(m);
            return false;
         }
         ok = GlobalVariableSetOnCondition(mzTravaNome, mzToken, v);
         if(ok) Log("AVISO", "MAESTRO", "TRAVA", "trava de outro grafico com heartbeat parado ha' 10 s ou mais: tomada");
      }
   }
   if(!ok) { Print("WinMaestro: trava nao tomada"); return false; }
   GlobalVariableSet(mzHbNome, (double)TimeLocal());
   mzIniciou = true;
   Log("INFO", "MAESTRO", "TRAVA", StringFormat("trava tomada (%s, token %u)", mzTravaNome, tk));
   return true;
}

void Trava_Heartbeat(void)
{
   if(!mzIniciou || mzCorr.Testador() || mzHbNome == "") return;
   GlobalVariableSet(mzHbNome, (double)TimeLocal());
}

// A trava ainda e' desta instancia? (M-3: outro grafico pode te^-la tomado com o heartbeat parado)
bool Trava_Confere(void)
{
   if(!mzIniciou || mzCorr.Testador() || mzTravaNome == "") return true;
   if(!GlobalVariableCheck(mzTravaNome))
   {
      // variavel apagada (janela F3, GlobalVariablesDeleteAll): ninguem detem a trava -> retoma (M-8)
      GlobalVariableSet(mzTravaNome, 0.0);
      bool ok = GlobalVariableSetOnCondition(mzTravaNome, mzToken, 0.0);
      GlobalVariableSet(mzHbNome, (double)TimeLocal());
      Log(ok ? "AVISO" : "ALERTA", "MAESTRO", "TRAVA", ok ? "variavel da trava apagada: retomada" : "variavel da trava apagada e tomada por outro grafico");
      return ok;
   }
   return GlobalVariableGet(mzTravaNome) == mzToken;
}

void Trava_Libera(void)
{
   if(!mzIniciou || mzCorr.Testador() || mzTravaNome == "") return;
   GlobalVariableSetOnCondition(mzTravaNome, 0.0, mzToken);
}

//+------------------------------------------------------------------+
//| Recuperacao sem memoria: transito pelas linhas ORDEM do log      |
//+------------------------------------------------------------------+
int Rec_Campos(const string linha, string &c[])
{
   ArrayResize(c, 0);
   string s = linha;
   int n = 0;
   while(true)
   {
      int p = StringFind(s, " | ");
      ArrayResize(c, n + 1);
      if(p < 0) { c[n++] = s; break; }
      c[n++] = StringSubstr(s, 0, p);
      s = StringSubstr(s, p + 3);
   }
   for(int i = 0; i < n; i++) { StringTrimLeft(c[i]); StringTrimRight(c[i]); }
   return n;
}

string Rec_Token(const string s, const string chave)
{
   int p = StringFind(s, chave);
   if(p < 0) return "";
   int ini = p + StringLen(chave);
   int fim = StringFind(s, " ", ini);
   if(fim < 0) fim = StringLen(s);
   return StringSubstr(s, ini, fim - ini);
}

void Rec_SeqMax(const string coment)
{
   int r, papel, seq;
   if(!Mae_LeComent(coment, r, papel, seq)) return;
   if(seq > mzSeq[r]) mzSeq[r] = seq;
}

// seq de hoje >= maior seq ja' usado no historico e nas pendentes: o comentario nunca se repete no dia (A-3).
void Rec_SeqHistorico(void)
{
   datetime hoje = Mae_Dia(Mae_Agora());
   if(mzSeqDia != hoje) { for(int r = 0; r < NROBOS; r++) mzSeq[r] = 0; mzSeqDia = hoje; }
   int nh = ArraySize(mzHo);
   for(int i = 0; i < nh; i++) if((datetime)(mzHo[i].setup_msc / 1000) >= hoje) Rec_SeqMax(mzHo[i].comentario);
   int np = ArraySize(mzPend);
   for(int i = 0; i < np; i++) Rec_SeqMax(mzPend[i].comentario);
}

// Memoria perdida: as linhas ORDEM do log do dia sem DESFECHO voltam ao transito; seq = maior do dia + 1.
void Recupera_LogOrdens(void)
{
   datetime agora = Mae_Agora();
   datetime hoje = Mae_Dia(agora);
   mzSeqDia = hoje;
   for(int r = 0; r < NROBOS; r++) mzSeq[r] = 0;
   string ls[];
   int nl = Log_LeDia(hoje, ls);
   string coms[];
   int nc = 0;
   string c[];
   for(int i = 0; i < nl; i++)
   {
      if(Rec_Campos(ls[i], c) < 5) continue;
      string ev = c[3], det = c[4];
      string dl = Rec_Token(det, "deal #");
      if((ev == "ENTROU" || ev == "SAIU" || ev == "EXTERNA") && dl != "")
      {
         int nl = ArraySize(mzLogTk);
         ArrayResize(mzLogTk, nl + 1);
         mzLogTk[nl] = (ulong)StringToInteger(dl);       // ja' logado hoje: nao reloga (resumo sem ALERTA falso)
      }
      string com = Rec_Token(det, "com=");
      if(com == "") continue;
      Rec_SeqMax(com);
      if(ev == "ORDEM" && StringFind(det, "envio ") == 0)
      {
         int r, papel, seq;
         if(!Mae_LeComent(com, r, papel, seq)) continue;
         int n = ArraySize(mzTr);
         bool ja = false;
         for(int k = 0; k < n; k++) if(mzTr[k].coment == com) ja = true;
         if(ja) continue;
         ArrayResize(mzTr, n + 1);
         mzTr[n].robo = r; mzTr[n].papel = papel; mzTr[n].seq = seq; mzTr[n].coment = com;
         mzTr[n].vol = StringToDouble(Rec_Token(det, "vol="));
         mzTr[n].lado = (int)StringToInteger(Rec_Token(det, "lado="));
         mzTr[n].preco = StringToDouble(Rec_Token(det, "preco="));
         string hhmmss = StringSubstr(c[0], 0, 8);
         mzTr[n].hora = StringToTime(TimeToString(hoje, TIME_DATE) + " " + hhmmss);
         string canc = Rec_Token(det, "cancela=#");
         mzTr[n].ticket = (papel == P_K && canc != "") ? (ulong)StringToInteger(canc) : 0;
         mzTr[n].req_id = 0; mzTr[n].retcode = 0; mzTr[n].alertou = false; mzTr[n].tipo = -1;
         ArrayResize(coms, nc + 1); coms[nc++] = com;
         continue;
      }
      // retorno: ticket da ordem; RECUSADA resolve
      for(int k = ArraySize(mzTr) - 1; k >= 0; k--)
      {
         if(mzTr[k].coment != com) continue;
         if(ev == "ORDEM" && StringFind(det, "RECUSADA") >= 0 && mzTr[k].papel != P_K) { Mae_TrRemove(k); continue; }
         if(ev == "ORDEM" && StringFind(det, "retorno ") == 0 && mzTr[k].papel != P_K)
         {
            string ord = Rec_Token(det, "ord=#");
            if(ord != "") mzTr[k].ticket = (ulong)StringToInteger(ord);
         }
         if(ev == "DESFECHO" && StringFind(det, "sem desfecho") < 0) Mae_TrRemove(k);
      }
   }
   Rec_SeqHistorico();
   int nt = ArraySize(mzTr);
   Log(nt > 0 ? "ALERTA" : "INFO", "MAESTRO", "MEMORIA", StringFormat("transito reconstruido do log do dia: %d ordem(ns) sem desfecho; seq GB %d CM %d DM %d RE %d C1 %d",
       nt, mzSeq[0], mzSeq[1], mzSeq[2], mzSeq[3], mzSeq[4]));
}

//+------------------------------------------------------------------+
//| Ambiente (passo 3)                                               |
//+------------------------------------------------------------------+
bool Recupera_Ambiente(string &falha)
{
   falha = "";
   long mm = mzCorr.ContaI(ACCOUNT_MARGIN_MODE);
   if(mm != ACCOUNT_MARGIN_MODE_RETAIL_NETTING && mm != ACCOUNT_MARGIN_MODE_EXCHANGE) { falha = "conta nao e' NETTING"; return false; }
   if(mzCorr.SimboloI(SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL) { falha = "simbolo nao negociavel"; return false; }
   if(!Mae_LeTick()) { falha = "tamanho ou valor do tick zerado"; return false; }
   long exe = mzCorr.SimboloI(SYMBOL_TRADE_EXEMODE);
   long fm = mzCorr.SimboloI(SYMBOL_FILLING_MODE);
   if(exe == SYMBOL_TRADE_EXECUTION_EXCHANGE) mzFillMercado = ORDER_FILLING_RETURN;          // P15
   else mzFillMercado = ((fm & SYMBOL_FILLING_IOC) != 0) ? ORDER_FILLING_IOC : ORDER_FILLING_FOK;
   return true;
}

bool Recupera_TemAlgoDeRobo(void)
{
   if(mzLiqOk && mzLiq != 0) return true;
   int n = ArraySize(mzPend);
   for(int i = 0; i < n; i++) if(Mae_Robo(mzPend[i].magic) >= 0) return true;
   return false;
}

void Recupera_Vai(const int passo, const string nome_fim)
{
   if(nome_fim != "") Log("INFO", "MAESTRO", "RECUPERA", "fim do passo " + nome_fim);
   mzPasso = passo;
   mzPassoDesde = Mae_Agora();
   mzPassoLog = 0;
   mzPassoAlertou = false;
}

void Recupera_Inicia(void)
{
   mzPasso = 1;
   mzPassoDesde = 0;
   mzPassoLog = 0;
   mzPassoAlertou = false;
   mzAmbUlt = 0;
}

// PRONTO: operacoes do dia por robo reconstruidas dos deals.
void Recupera_LogPronto(void)
{
   datetime hoje = Mae_Dia(Mae_Agora());
   for(int r = 0; r < NROBOS; r++)
   {
      int ops = 0, fora = 0;
      int n = ArraySize(mzDl);
      for(int i = 0; i < n; i++)
      {
         if(mzDl[i].robo != r || (datetime)(mzDl[i].t / 1000) < hoje) continue;
         if(mzDl[i].tipo != DEAL_TYPE_BUY && mzDl[i].tipo != DEAL_TYPE_SELL) continue;
         ops++;
         datetime td = (datetime)(mzDl[i].t / 1000);
         if(mzHeartbeatMem > 0 && td > mzHeartbeatMem && td < mzPartidaEm) fora++;
      }
      Log("INFO", mzNome[r], "PRONTO", StringFormat("%s; ficha %+d @%.0f; %d deal(s) hoje (%d com o EA fora); R$ %.2f; stop pedido %.0f; alvo %.0f%s",
          mzAtivo[r] ? "ligado" : "DESLIGADO", mzF[r], mzPm[r], ops, fora, mzRes[r], mzStopNivel[r], mzAlvoNivel[r], mzFalhou[r] ? "; Init FALHOU" : ""));
   }
   if(mzHeartbeatMem > 0 && mzPartidaEm - mzHeartbeatMem > 60)
      Log("AVISO", "MAESTRO", "RECUPERA", StringFormat("EA fora %s-%s", TimeToString(mzHeartbeatMem, TIME_DATE | TIME_SECONDS), TimeToString(mzPartidaEm, TIME_SECONDS)));
   long dif = (long)(TimeTradeServer() - TimeGMT());
   if(!mzCorr.Testador() && MathAbs(dif + 3 * 3600) > 120)
      Log("AVISO", "MAESTRO", "PRONTO", StringFormat("TimeTradeServer - TimeGMT = %+.1f h (esperado -3 h, P22)", (double)dif / 3600.0));
   Log("INFO", "MAESTRO", "PRONTO", StringFormat("maestro pronto: liquida %+d, externa %+d, bloqueio %s, corte de hoje %s",
       mzLiq, mzExt, mzBloq ? "SIM (" + mzBloqMotivo + ")" : "nao", TimeToString(Mae_CorteDe(Mae_Agora()), TIME_MINUTES)));
}

//+------------------------------------------------------------------+
//| Sequencia de partida (sec. 10.2)                                     |
//+------------------------------------------------------------------+
void Recupera_Passo(void)
{
   if(mzPasso <= 0 || mzPasso >= 12) return;
   datetime agora = Mae_Agora();
   if(mzPassoDesde == 0) mzPassoDesde = agora;
   switch(mzPasso)
   {
      case 1:   // trava
      {
         Log("INFO", "MAESTRO", "RECUPERA", "passo 1: trava");
         if(!Trava_Toma()) { mzPasso = 0; ExpertRemove(); return; }
         Recupera_Vai(2, "1 (trava)");
         Log("INFO", "MAESTRO", "RECUPERA", "passo 2: conexao");
         return;
      }
      case 2:   // conexao: leitura confiavel e tick valido; nenhuma ordem
      {
         Mae_Conexao();
         MqlTick t;
         bool tick_ok = mzCorr.UltimoTick(t) && (t.bid > 0.0 || t.last > 0.0);
         bool con_ok = mzCorr.Testador() || (mzConectado && agora - mzConectadoDesde >= 10);
         if(con_ok && tick_ok) { Recupera_Vai(3, "2 (conexao)"); Log("INFO", "MAESTRO", "RECUPERA", "passo 3: ambiente"); return; }
         if(agora - mzPassoLog >= 30) { mzPassoLog = agora; Log("AVISO", "MAESTRO", "RECUPERA", StringFormat("esperando conexao (%s) e tick valido (%s)", con_ok ? "ok" : "nao", tick_ok ? "ok" : "nao")); }
         if(!mzPassoAlertou && agora - mzPassoDesde >= 300) { mzPassoAlertou = true; Log("ALERTA", "MAESTRO", "RECUPERA", "5 min sem conexao confiavel ou tick valido"); }
         return;
      }
      case 3:   // ambiente
      {
         string falha;
         bool ok = Recupera_Ambiente(falha);
         if(mzCorr.RoboEmOutroSimbolo(mzMagic)) Log("AVISO", "MAESTRO", "AMBIENTE", "ha' ordem ou posicao com magic de robo em outro simbolo (O16)");
         mzVencimento = Grade_VencimentoDoSimbolo(_Symbol);
         if(ok)
         {
            Log("INFO", "MAESTRO", "AMBIENTE", StringFormat("NETTING ok; tick %.2f = R$ %.2f; preenchimento a mercado %s; vencimento do contrato %s",
                mzTickSize, mzTickValor, EnumToString(mzFillMercado), mzVencimento > 0 ? TimeToString(mzVencimento, TIME_DATE) : "(serie continua: nenhum)"));
            Recupera_Vai(4, "3 (ambiente)");
            Log("INFO", "MAESTRO", "RECUPERA", "passo 4: historico");
            return;
         }
         if(falha == "tamanho ou valor do tick zerado" && agora - mzPassoDesde < 60) return;   // repete por 60 s
         Leitura_Atualiza(false);
         if(Recupera_TemAlgoDeRobo())
         {
            mzProtegendo = true;
            mzSemOrdens = (falha == "conta nao e' NETTING");     // conta hedging: cada S/X abriria posicao nova (M-5)
            Log("ALERTA", "MAESTRO", "PROTEGENDO", "ambiente falhou (" + falha + ") com ficha ou ordem de robo: " + (falha == "conta nao e' NETTING" ? "NENHUMA ordem (so' alerta)" : "so' S, cancelamentos e saida do corte") + "; rechecando a cada 30 s");
            Recupera_Vai(4, "3 (ambiente, PROTEGENDO)");
            return;
         }
         Log("ALERTA", "MAESTRO", "AMBIENTE", "ambiente falhou (" + falha + ") sem ficha nem ordem de robo: EA parado");
         mzPasso = 0;
         ExpertRemove();
         return;
      }
      case 4:   // historico: janela ate' a cruzada fechar (prazo 60 s)
      {
         if(mzPassoLog == 0)
         {
            // a externa de origem desconhecida gravada pelo botao entra ja' na janela (M-2)
            mzPassoLog = agora;
            if(Mem_Carrega() < 2 && Mem_Get("servidor", "") == mzCorr.ContaS(ACCOUNT_SERVER) &&
               Mem_GetI("conta", -1) == mzCorr.ContaI(ACCOUNT_LOGIN) && Mem_Get("simbolo", "") == _Symbol)
               mzExtDesc = (int)Mem_GetI("ext_desc", 0);
            Mem_Limpa();
         }
         Leitura_Atualiza(true);
         if(mzLiqOk && mzCruzOk)
         {
            Log("INFO", "MAESTRO", "HISTORICO", StringFormat("janela desde %s; %d deals; liquida %+d", TimeToString(mzJanIni, TIME_DATE | TIME_MINUTES), ArraySize(mzDl), mzLiq));
            Recupera_Vai(5, "4 (historico)");
            Log("INFO", "MAESTRO", "RECUPERA", "passo 5: memoria");
            return;
         }
         if(agora - mzPassoDesde < 60) return;
         mzBloqCruz = true;
         mzBloqMotivo = StringFormat("verificacao cruzada nao fecha em 10 pregoes (diferenca %+d)", mzDifPendente);
         mzBloq = true;                                       // a memoria ainda nao foi lida: grava depois do passo 5
         Log("ALERTA", "MAESTRO", "HISTORICO", "historico nao fecha com a liquida em 60 s: bloqueio de entradas (botao)");
         Recupera_Vai(5, "4 (historico, sem fechar)");
         Log("INFO", "MAESTRO", "RECUPERA", "passo 5: memoria");
         return;
      }
      case 5:   // memoria
      {
         bool bloq_hist = mzBloq;
         string mot_hist = mzBloqMotivo;
         int st = Mae_Importa();
         if(st == 0) Log("INFO", "MAESTRO", "MEMORIA", "estado.txt valido");
         if(st == 1) Log("AVISO", "MAESTRO", "MEMORIA", "estado.txt invalido ou ausente: usado o .bak");
         if(st == 2) Log("ALERTA", "MAESTRO", "MEMORIA", "memoria perdida (estado.txt e .bak ruins ou ausentes)");
         if(st == 3) Log("AVISO", "MAESTRO", "MEMORIA", "memoria de outra conta, servidor ou simbolo: ignorada");
         if(st >= 2) Recupera_LogOrdens();
         else Rec_SeqHistorico();
         if(bloq_hist) { mzBloq = true; if(StringFind(mzBloqMotivo, mot_hist) < 0) mzBloqMotivo = (mzBloqMotivo == "" ? mot_hist : mzBloqMotivo + "; " + mot_hist); mzBloqCruz = true; }
         mzMemCarregada = true;
         if(mzBloq) Mae_BotaoMostra(true);
         Mae_GravaMemoria(true);
         Recupera_Vai(6, "5 (memoria)");
         Log("INFO", "MAESTRO", "RECUPERA", "passo 6: reconstrucao");
         return;
      }
      case 6:   // reconstrucao: fichas, desfechos, externas, absorcoes, bloqueios
      {
         Leitura_Atualiza(true);
         Mae_NovosEventos();
         Transito_Resolve();
         for(int r = 0; r < NROBOS; r++) Mae_EControle(r);
         for(int r = 0; r < NROBOS; r++)
         {
            SRoboEstado e; Mae_Estado(r, e);
            string est = "";
            if(e.f != 0 && Mae_Trocada(r, e)) est = " TROCADA";
            if(Mae_Duplicada(r, e)) est = " DUPLICADA";
            if(Mae_Noite(r)) est += " (atravessou a noite)";
            Log("INFO", mzNome[r], "RECUPERA", StringFormat("ficha %+d @%.0f%s; ordens vivas %d; transito %s", e.f, mzPm[r], est, e.nVivas, Mae_TemTransito(r) ? "SIM" : "nao"));
         }
         Log("INFO", "MAESTRO", "RECUPERA", StringFormat("liquida %+d = fichas %+d + externa %+d; cruzada %s", mzLiq, Mae_SomaFichas(), mzExt, mzCruzOk ? "fecha" : "NAO fecha"));
         Recupera_Vai(7, "6 (reconstrucao)");
         Log("INFO", "MAESTRO", "RECUPERA", "passo 7: orfas");
         return;
      }
      case 7:   // orfas antes de qualquer outra ordem
      {
         for(int r = 0; r < NROBOS; r++) Mae_Fase1(r, true);
         Recupera_Vai(8, "7 (orfas)");
         Log("INFO", "MAESTRO", "RECUPERA", "passo 8: protecao");
         return;
      }
      case 8:   // protecao: S para toda E viva e toda ficha; alvo do RE da memoria
      {
         for(int r = 0; r < NROBOS; r++) Mae_Fase2(r, true);
         Recupera_Vai(9, "8 (protecao)");
         Log("INFO", "MAESTRO", "RECUPERA", "passo 9: pendencias");
         return;
      }
      case 9:   // pendencias: trocada, duplicada, ficha da noite, corte perdido (executa no continuo; senao agenda)
      {
         for(int r = 0; r < NROBOS; r++) Mae_Fase1(r, false);
         Recupera_Vai(10, "9 (pendencias)");
         Log("INFO", "MAESTRO", "RECUPERA", "passo 10: modulos");
         return;
      }
      case 10:  // modulos
      {
         if(mzProtegendo)
         {
            if(agora - mzAmbUlt < 30) return;
            mzAmbUlt = agora;
            string falha;
            if(!Recupera_Ambiente(falha)) { Log_Cond("protegendo", true, "ALERTA", "MAESTRO", "PROTEGENDO", "ambiente segue falhando: " + falha); return; }
            Log_Cond("protegendo", false, "", "MAESTRO", "PROTEGENDO", "");
            mzProtegendo = false;
            mzSemOrdens = false;
            Log("INFO", "MAESTRO", "AMBIENTE", "ambiente ok: saindo do modo PROTEGENDO");
         }
         Robo_InitTodos();
         mzModulosIniciados = true;
         Mae_EntregaEventos();
         Recupera_Vai(11, "10 (modulos)");
         return;
      }
      case 11:  // PRONTO
      {
         mzPronto = true;
         mzProntoEm = mzCorr.Testador() ? 0 : agora;     // no Testador o EA nunca esteve fora: nenhuma DECISAO PERDIDA
         Mae_GravaMemoria(true);
         Recupera_LogPronto();
         mzPasso = 12;
         return;
      }
   }
}

// Sequencia inteira de uma vez (Testador: nada a esperar; PRONTO antes do 1o Tick dos modulos).
void Recupera_Completa(void)
{
   for(int k = 0; k < 40 && mzPasso > 0 && mzPasso < 12; k++)
   {
      int antes = mzPasso;
      Recupera_Passo();
      if(mzPasso == antes && mzPasso != 4) break;          // passo esperando (ex.: sem tick valido): proximo evento
   }
}

// Timer (250 ms): partida, trava, heartbeat, reconciliacao (1 s) e painel.
datetime mzUltSegundo = 0;
void Mae_OnTimer(void)
{
   if(mzCorr == NULL || mzPasso == 0) return;
   if(mzPasso < 12) { if(mzCorr.Testador()) Recupera_Completa(); else Recupera_Passo(); }
   if(mzPasso == 0) return;
   datetime agora = Mae_Agora();
   if(agora == mzUltSegundo) return;
   mzUltSegundo = agora;
   if(!mzTravaPerdida && !Trava_Confere())
   {
      mzTravaPerdida = true;                              // outro grafico tem a trava: so' a protecao (S) sai desta instancia
      Log("ALERTA", "MAESTRO", "TRAVA", "a trava passou a outro grafico: desta instancia so' sai protecao (S); remova uma das duas");
   }
   if(!mzTravaPerdida) Trava_Heartbeat();
   if(mzPasso >= 10) Mae_Reconcilia();
   Mae_Painel();
}

// OnTradeTransaction: log bruto, request_id -> ticket, reconciliacao a cada deal.
void Mae_OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(mzCorr == NULL || !mzIniciou) return;
   bool do_simbolo = (trans.symbol == _Symbol) || (trans.type == TRADE_TRANSACTION_REQUEST && request.symbol == _Symbol);
   if(!do_simbolo) return;
   Log_Trans(StringFormat("%s ordem #%I64u deal #%I64u estado %s preco %.0f vol %.0f magic %I64u req %u",
             EnumToString(trans.type), trans.order, trans.deal, EnumToString(trans.order_state), trans.price, trans.volume,
             request.magic, result.request_id));
   if(trans.type == TRADE_TRANSACTION_REQUEST) Mae_RequestVisto(result.request_id, result.order);
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD && mzPasso >= 10) Mae_Reconcilia();
}

//+------------------------------------------------------------------+
//| Painel (O7): so' leitura                                         |
//+------------------------------------------------------------------+
void Mae_Painel(void)
{
   if(mzCorr.Testador() && !MQLInfoInteger(MQL_VISUAL_MODE)) return;
   datetime agora = Mae_Agora();
   string s = StringFormat("WinMaestro v1.03 | %s | %s | passo %s\n", _Symbol, TimeToString(agora, TIME_DATE | TIME_SECONDS),
                           mzPasso >= 12 ? "PRONTO" : IntegerToString(mzPasso));
   s += StringFormat("liquida %+d | externa %+d | cruzada %s | corte %s | %s\n", mzLiq, mzExt, mzCruzOk ? "ok" : "NAO FECHA",
                     TimeToString(Mae_CorteDe(agora), TIME_MINUTES), mzBloq ? "BLOQUEIO: " + mzBloqMotivo : "entradas liberadas");
   if(mzProtegendo) s += "MODO PROTEGENDO (so' S, cancelamentos e corte)\n";
   for(int r = 0; r < NROBOS; r++)
   {
      SRoboEstado e; Mae_Estado(r, e);
      string est = "";
      if(!mzAtivo[r]) est += " [desligado]";
      if(mzFalhou[r]) est += " [Init falhou]";
      if(Mae_TemTransito(r)) est += " [PAUSADO: sem desfecho]";
      if(e.f != 0 && Mae_Trocada(r, e)) est += " [TROCADA]";
      if(Mae_Duplicada(r, e)) est += " [DUPLICADA]";
      if(Mae_Noite(r)) est += " [noite]";
      s += StringFormat("%s: ficha %+d @%.0f | S %s | A %s | E %s | R$ %.2f%s\n", mzNome[r], e.f, mzPm[r],
                        e.iS >= 0 ? DoubleToString(mzPend[e.iS].preco, 0) : "-",
                        e.iA >= 0 ? DoubleToString(mzPend[e.iA].preco, 0) : "-",
                        e.iE >= 0 ? DoubleToString(mzPend[e.iE].preco, 0) : "-", mzRes[r], est);
   }
   Comment(s);
}

#endif
