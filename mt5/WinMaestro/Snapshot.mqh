//+------------------------------------------------------------------+
//| WinMaestro/Snapshot.mqh                                          |
//| Passo 1 do ciclo (sec. 3): leitura de UM snapshot da corretora   |
//| (sec. 1.1). Nada e' lido da corretora depois, no mesmo ciclo.    |
//| Base = conexao, trava, liquida e vivas[]. Historico a parte: a   |
//| falha so' do historico nao e' INVALIDO (deixa os robos RESTRITOS)|
//| Tambem: relogio, grade do dia, janela do historico e o preco de  |
//| referencia validado (sec. 1.1, RV2 N-3).                         |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_SNAPSHOT_MQH
#define WINMAESTRO_SNAPSHOT_MQH

#include "Tipos.mqh"
#include "Log.mqh"
#include "Grade.mqh"

bool Trava_Confere(void);   // Partida.mqh

//+------------------------------------------------------------------+
//| Utilitarios                                                      |
//+------------------------------------------------------------------+
int      Mae_Sinal(const int x)              { return x > 0 ? 1 : (x < 0 ? -1 : 0); }
int      Mae_Abs(const int x)                { return x < 0 ? -x : x; }
datetime Mae_Dia(const datetime t)           { return t - (t % 86400); }
int      Mae_SegDia(const datetime t)        { return (int)(t % 86400); }
bool     Mae_DiaUtil(const datetime t)       { MqlDateTime d; TimeToStruct(t, d); return d.day_of_week != 0 && d.day_of_week != 6; }
int      Mae_Robo(const long magic)          { for(int r = 0; r < NDONOS; r++) if(mzMagic[r] == magic) return r; return -1; }
bool     Mae_EhRobo(const long magic)        { int r = Mae_Robo(magic); return r >= 0 && r < NROBOS; }
bool     Mae_TipoStop(const int t)           { return t == ORDER_TYPE_BUY_STOP || t == ORDER_TYPE_SELL_STOP || t == ORDER_TYPE_BUY_STOP_LIMIT || t == ORDER_TYPE_SELL_STOP_LIMIT; }
bool     Mae_TipoLimite(const int t)         { return t == ORDER_TYPE_BUY_LIMIT || t == ORDER_TYPE_SELL_LIMIT; }
bool     Mae_TipoMercado(const int t)        { return t == ORDER_TYPE_BUY || t == ORDER_TYPE_SELL; }
int      Mae_LadoTipo(const int t)
{
   return (t == ORDER_TYPE_BUY || t == ORDER_TYPE_BUY_LIMIT || t == ORDER_TYPE_BUY_STOP || t == ORDER_TYPE_BUY_STOP_LIMIT) ? 1 : -1;
}
string Mae_TipoNome(const int t)
{
   if(t < 0) return "-";
   string s = EnumToString((ENUM_ORDER_TYPE)t);
   StringReplace(s, "ORDER_TYPE_", "");
   StringToLower(s);
   return s;
}
string Mae_Papel(const int p)
{
   switch(p)
   {
      case P_E: return "E";
      case P_S: return "S";
      case P_A: return "A";
      case P_X: return "X";
      case P_K: return "K";
      case P_M: return "M";
   }
   return "?";
}
int Mae_PapelDe(const string s)
{
   if(s == "E") return P_E;
   if(s == "S") return P_S;
   if(s == "A") return P_A;
   if(s == "X") return P_X;
   if(s == "K") return P_K;
   if(s == "M") return P_M;
   return 0;
}
int Mae_RoboDe(const string s) { for(int r = 0; r < NDONOS; r++) if(mzNome[r] == s) return r; if(s == "MAE") return R_MAE; return -1; }
string Mae_Hms(const long msc) { return Log_HmsMsc(msc); }
// Preco arredondado ao tick do WIN (TICK_WIN; nenhuma divisao pelo tick lido, RV2 mudanca D).
double Mae_NoTick(const double p)    { return MathRound(p / TICK_WIN) * TICK_WIN; }
bool   Mae_Igual(const double a, const double b) { return MathAbs(a - b) <= TICK_WIN / 2.0; }

//+------------------------------------------------------------------+
//| Grade e horarios (spec 9; sec. 5)                                |
//+------------------------------------------------------------------+
// Le a grade da data de t: pre-abertura, inicio e F (minutos do dia). Data sem linha: F = 17:55 e AVISO (spec 9.1).
datetime mzGradeAvisoDia = 0;
void Mae_Grade(const datetime t, int &pre, int &neg, int &fim)
{
   int venc = 0;
   bool tem = Grade_Le(Mae_Dia(t), pre, neg, fim, venc);
   if(!tem && mzGradeAvisoDia != Mae_Dia(t))
   {
      mzGradeAvisoDia = Mae_Dia(t);
      Log("AVISO", "MAESTRO", "AMBIENTE", StringFormat("data %s sem linha na grade: F = 17:55 (corte 17:50)", TimeToString(Mae_Dia(t), TIME_DATE)));
   }
}
datetime Mae_FDe(const datetime t)      { int p, n, f; Mae_Grade(t, p, n, f); return Mae_Dia(t) + f * 60; }
datetime Mae_CDe(const datetime t)      { return Mae_FDe(t) - MARGEM_CORTE_MIN * 60; }
datetime Mae_C2De(const datetime t)     { return Mae_CDe(t) + PRAZO_CORTE_S; }
datetime Mae_InicioDe(const datetime t) { int p, n, f; Mae_Grade(t, p, n, f); return Mae_Dia(t) + n * 60; }
datetime Mae_PreDe(const datetime t)    { int p, n, f; Mae_Grade(t, p, n, f); return Mae_Dia(t) + p * 60; }
datetime Mae_FimSessaoDe(const datetime t) { return Mae_FDe(t) + CALL_MIN * 60; }

// Continuo: inicio <= t < F, dia util.
bool Mae_Continuo(const datetime t)      { return Mae_DiaUtil(t) && t >= Mae_InicioDe(t) && t < Mae_FDe(t); }
// Janela de ordens: pre-abertura <= t < fim da sessao (F + 15 min), dia util.
bool Mae_JanelaOrdens(const datetime t)  { return Mae_DiaUtil(t) && t >= Mae_PreDe(t) && t < Mae_FimSessaoDe(t); }
// Tick dos modulos: pre-abertura <= t < corte (sec. 7).
bool Mae_JanelaTick(const datetime t)    { return Mae_DiaUtil(t) && t >= Mae_PreDe(t) && t < Mae_CDe(t); }
// Fase do motor de corte da conta: a partir de C + PRAZO_CORTE (sec. 5.2).
bool Mae_FaseConta(const datetime t)     { return t >= Mae_C2De(t); }
// Prazos de restricao (sec. 2.3) so' contam no pregao (escolha: fora dele nada e' decidido).
bool Mae_JanelaPrazos(const datetime t)  { return Mae_DiaUtil(t) && t >= Mae_PreDe(t) && t < Mae_C2De(t); }
// Pregao anterior (dia util anterior); o inicio da janela dele.
datetime Mae_PregaoAnterior(const datetime dia)
{
   datetime d = Mae_Dia(dia) - 86400;
   while(!Mae_DiaUtil(d)) d -= 86400;
   return d;
}

//+------------------------------------------------------------------+
//| Preco de referencia (sec. 1.1)                                   |
//+------------------------------------------------------------------+
// Lado comprado (+1) = bid, vendido (-1) = ask, so' com livro valido; senao o ultimo last > 0 visto;
// senao `reserva` (preco da ficha ou da E). 0 = sem referencia (nada e' calculado com ela).
double Snap_Ref(const int lado, const double reserva)
{
   if(mzLivroOk) return lado > 0 ? mzBid : mzAsk;
   if(mzUltLast > 0.0) return mzUltLast;
   return reserva > 0.0 ? reserva : 0.0;
}
// Piso = max(TICK_WIN, SYMBOL_TRADE_STOPS_LEVEL em pontos do WIN) (sec. 0).
double Snap_Piso(void)
{
   double sl = (double)mzCorr.SimboloI(SYMBOL_TRADE_STOPS_LEVEL);
   double pt = mzCorr.SimboloD(SYMBOL_POINT);
   if(pt <= 0.0) pt = 1.0;
   return MathMax(TICK_WIN, sl * pt);
}

//+------------------------------------------------------------------+
//| Buscas no snapshot                                               |
//+------------------------------------------------------------------+
int Snap_VivaIdx(const ulong tk) { int n = ArraySize(mzViva); for(int i = 0; i < n; i++) if(mzViva[i].ticket == tk) return i; return -1; }
// Indices ordenados por ticket, refeitos a cada leitura do historico (B-5): busca binaria no lugar de laco por linha.
long mzIxDeal[][2];   // (DEAL_ORDER, indice em mzDeal)
long mzIxHist[][2];   // (ticket da ordem, indice em mzOH)
void Snap_Indexa(void)
{
   int nd = ArraySize(mzDeal);
   ArrayResize(mzIxDeal, nd);
   for(int i = 0; i < nd; i++) { mzIxDeal[i][0] = (long)mzDeal[i].ordem; mzIxDeal[i][1] = i; }
   if(nd > 1) ArraySort(mzIxDeal);
   int nh = ArraySize(mzOH);
   ArrayResize(mzIxHist, nh);
   for(int i = 0; i < nh; i++) { mzIxHist[i][0] = (long)mzOH[i].ticket; mzIxHist[i][1] = i; }
   if(nh > 1) ArraySort(mzIxHist);
}
int Snap_Busca(const long &ix[][2], const long chave)
{
   int lo = 0, hi = ArrayRange(ix, 0) - 1;
   while(lo <= hi)
   {
      int m = (lo + hi) / 2;
      if(ix[m][0] == chave) return (int)ix[m][1];
      if(ix[m][0] < chave) lo = m + 1; else hi = m - 1;
   }
   return -1;
}
int Snap_HistIdx(const ulong tk)    { if(tk == 0 || !mzHistOk) return -1; return Snap_Busca(mzIxHist, (long)tk); }
int Snap_DealDaOrdem(const ulong tk) { if(tk == 0 || !mzHistOk) return -1; return Snap_Busca(mzIxDeal, (long)tk); }
bool Snap_HistFinalExec(const int estado) { return estado == ORDER_STATE_FILLED || estado == ORDER_STATE_PARTIAL; }
bool Snap_HistFinalNao(const int estado)  { return estado == ORDER_STATE_CANCELED || estado == ORDER_STATE_REJECTED || estado == ORDER_STATE_EXPIRED; }

// Ausencia provada (sec. 2.1, decisoes 3 e C): historico lido e conexao ok nos ULTIMOS PROVA s, e mais de PROVA s
// desde `desde_msc` (= max(enviado, sumida)).
bool Snap_AusenciaProvada(const long desde_msc)
{
   if(!mzHistOk || mzHistOkDesde <= 0 || mzConexaoDesde <= 0) return false;
   if(mzMono - mzHistOkDesde < PROVA_MS) return false;
   if(mzMono - mzConexaoDesde < PROVA_MS) return false;
   return mzMono - desde_msc > PROVA_MS;
}

// Pares request_id -> ticket vistos no OnTradeTransaction(REQUEST) (sec. 1.1, req_tickets).
void Snap_RequestVisto(const uint req, const ulong ordem)
{
   if(req == 0 || ordem == 0) return;
   int n = ArraySize(mzReqId);
   for(int i = 0; i < n; i++) if(mzReqId[i] == req) { mzReqTk[i] = ordem; return; }
   if(n >= 200)   // guarda os 200 mais recentes
   {
      for(int i = 0; i < n - 1; i++) { mzReqId[i] = mzReqId[i + 1]; mzReqTk[i] = mzReqTk[i + 1]; }
      n--;
   }
   ArrayResize(mzReqId, n + 1); ArrayResize(mzReqTk, n + 1);
   mzReqId[n] = req; mzReqTk[n] = ordem;
}
ulong Snap_TicketDoRequest(const uint req)
{
   if(req == 0) return 0;
   int n = ArraySize(mzReqId);
   for(int i = 0; i < n; i++) if(mzReqId[i] == req) return mzReqTk[i];
   return 0;
}

//+------------------------------------------------------------------+
//| Janela do historico (sec. 1.1)                                   |
//+------------------------------------------------------------------+
// o mais antigo entre (inicio de hoje - 10 min), (primeiro envio de qualquer linha retida no mapa - 1 min) e o recuo de hoje.
// A retencao (Mapa_Retencao, no dia novo) so' guarda linhas de hoje e de episodios abertos; usar TODAS as retidas, e nao
// so' as de episodio aberto, impede a janela de encolher no meio do dia quando o episodio da noite fecha (a linha E de
// ontem continuaria no mapa sem o deal na janela, e o robo ficaria nao provado o dia inteiro).
datetime Snap_JanelaInicio(void)
{
   datetime ini = Mae_InicioDe(mzAgora) - 600;
   int n = ArraySize(mzL);
   for(int i = 0; i < n; i++)
   {
      datetime t = (datetime)(mzL[i].enviado_msc / 1000) - 60;
      if(t < ini) ini = t;
   }
   if(mzJanRecuo > 0 && mzJanRecuoDia == Mae_Dia(mzAgora) && mzJanRecuo < ini) ini = mzJanRecuo;
   return ini;
}

// Ordena os deals por instante e ticket (o calculo das fichas depende da ordem).
void Snap_OrdenaDeals(void)
{
   int n = ArraySize(mzDeal);
   for(int i = 1; i < n; i++)
   {
      SDealInfo d = mzDeal[i];
      int j = i - 1;
      while(j >= 0 && (mzDeal[j].time_msc > d.time_msc || (mzDeal[j].time_msc == d.time_msc && mzDeal[j].ticket > d.ticket)))
      {
         mzDeal[j + 1] = mzDeal[j];
         j--;
      }
      mzDeal[j + 1] = d;
   }
}

//+------------------------------------------------------------------+
//| Passo 1: leitura                                                 |
//+------------------------------------------------------------------+
// true = base ok. Falha de base = INVALIDO (sec. 1.1).
bool Snap_Le(void)
{
   mzAgoraMsc = mzCorr.AgoraMsc();
   mzMono = mzCorr.Mono();
   mzAgora = (datetime)(mzAgoraMsc / 1000);
   int venc = 0;
   mzGTem = Grade_Le(Mae_Dia(mzAgora), mzGPre, mzGNeg, mzGFim, venc);
   // conexao: TERMINAL_CONNECTED verdadeiro ha' CONEXAO s
   mzConectado = mzCorr.Conectado();
   if(!mzConectado) mzConexaoDesde = 0;
   else if(mzConexaoDesde == 0) mzConexaoDesde = mzMono;
   mzConexaoOk = mzConectado && mzMono - mzConexaoDesde >= CONEXAO_MS;
   mzTravaOk = Trava_Confere();
   double lv = 0.0, lp = 0.0;
   bool lok = mzCorr.LeLiquida(lv, lp);
   if(lok) mzLiq = (int)MathRound(lv);
   bool vok = mzCorr.LePendentes(mzViva);
   // tick: preco de referencia
   MqlTick t;
   mzLivroOk = false;
   if(mzCorr.UltimoTick(t))
   {
      mzBid = t.bid; mzAsk = t.ask;
      mzLivroOk = t.bid > 0.0 && t.ask >= t.bid && mzAgoraMsc - t.time_msc < IDADE_TICK_MS;
      if(t.last > 0.0) mzUltLast = t.last;
      // M-4: tick novo -> o relogio do servidor estimado (TimeTradeServer, do PC) deve bater com o instante do tick
      if(t.time_msc > 0 && t.time_msc != mzUltTickMsc)
      {
         if(mzUltTickMsc != 0) mzRelogioDesvio = MathAbs(mzAgoraMsc - t.time_msc) > 2000;
         mzUltTickMsc = t.time_msc;
      }
      Log_Cond("relogio", mzRelogioDesvio, "ALERTA", "MAESTRO", "AMBIENTE",
               StringFormat("relogio do servidor estimado difere do ultimo tick em %I64d ms: confira o relogio do PC", mzAgoraMsc - t.time_msc));
   }
   mzBaseOk = mzConexaoOk && mzTravaOk && lok && vok;
   bool hok = false;
   if(mzBaseOk)
   {
      mzJanIni = Snap_JanelaInicio();
      hok = mzCorr.LeHistorico(mzJanIni, mzAgora + 86400, mzDeal, mzOH);   // ate' agora + 1 dia (RV M-10)
      if(hok) { Snap_OrdenaDeals(); Snap_Indexa(); }
   }
   mzHistOk = hok;
   if(!hok) mzHistOkDesde = 0;
   else if(mzHistOkDesde == 0) mzHistOkDesde = mzMono;
   return mzBaseOk;
}

#endif
