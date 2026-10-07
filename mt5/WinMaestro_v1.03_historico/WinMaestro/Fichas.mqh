//+------------------------------------------------------------------+
//| WinMaestro/Fichas.mqh                                            |
//| Nucleo do maestro: fichas, verificacao D1, envio com o magic do  |
//| robo, papeis S/E/A/X/C, uma operacao por robo, reconciliacao,    |
//| absorcao, correcoes, bloqueio e botao.                            |
//|                                                                  |
//| Regra de ouro: a ficha sai dos DEALS (Ficha_Calcula, funcao pura |
//| do historico); a memoria guarda so' niveis, instantes e o        |
//| registro de transito. Nenhum modulo chama Position*/Order*/      |
//| History*/OrderSend: tudo passa por aqui e pela Corretora.        |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_FICHAS_MQH
#define WINMAESTRO_FICHAS_MQH

#include "Corretora.mqh"
#include "Log.mqh"
#include "Memoria.mqh"
#include "Grade.mqh"

#define NROBOS 5
#define R_GB 0
#define R_CM 1
#define R_DM 2
#define R_RE 3
#define R_C1 4

// retorno das funcoes de envio vistas pelos modulos (sec. 3.3)
#define FICHA_ENVIADA   0
#define FICHA_RECUSADA  1
#define FICHA_BLOQUEADA 2

// papeis (sec. 2)
#define P_E 1
#define P_S 2
#define P_A 3
#define P_X 4
#define P_C 5
#define P_K 6      // cancelamento

// desfechos (sec. 4.4, sec. 5.1)
#define D_SEM   0  // sem desfecho ("nao sei")
#define D_VIVA  1  // ordem nova listada nas pendentes
#define D_EXEC  2  // ordem nova executada (deal com DEAL_ORDER = ticket)
#define D_NAO   3  // ordem nova nao executada / cancelamento que nao aconteceu
#define D_CANC  4  // cancelamento confirmado no historico
#define D_ANTES 5  // cancelamento perdeu a corrida: a ordem executou

// eventos aos modulos (sec. 3.3)
#define EV_ENTRADA_CANCELADA 1
#define EV_EXECUTOU_ANTES    2

// constantes (sec. 1)
#define CM_RESERVA_PTS       4945.0
#define PRAZO_CONFIRMACAO    5
#define ALERTA_SEM_DESFECHO  30
#define PRAZO_SEM_DESFECHO   600
#define IDADE_PROVA          30
#define RETENTA              5
#define STOP_EMERGENCIA_PTS  1200.0
#define DM_CAPITAL           1000.0
#define MARGEM_CORTE         5

// ---- ganchos definidos pelo EA (ou pelos stubs do EA de teste) ----
void   Robo_Evento(const int r, const int ev);
int    Robo_MinutoZerar(const int r, const datetime dia);   // horario proprio de zeragem (min do dia), antes do corte
double Robo_StopRegra(const int r);                         // stop pela regra do robo para a ficha atual (0 = sem regra)
void   Robo_Exporta(void);                                  // escreve as variaveis dos modulos na memoria

//+------------------------------------------------------------------+
//| Estado                                                           |
//+------------------------------------------------------------------+
string mzNome[NROBOS]  = {"GB", "CM", "DM", "RE", "C1"};
long   mzMagic[NROBOS] = {80080601, 80080501, 80080101, 20261005, 80080002};
bool   mzAtivo[NROBOS];
bool   mzFalhou[NROBOS];          // Init do modulo falhou: sem Tick e sem entrada (o maestro segue protegendo)

struct STransito
{
   int      robo;
   int      papel;
   int      seq;
   string   coment;
   double   vol;
   int      lado;
   double   preco;
   datetime hora;
   ulong    ticket;       // ordem criada; no cancelamento, a ordem alvo
   uint     req_id;
   uint     retcode;
   bool     alertou;
   int      tipo;         // ENUM_ORDER_TYPE pedido (prova sem ticket nem comentario, M-6)
};

struct SDealC
{
   ulong  ticket;
   ulong  ordem;
   long   t;
   long   magic;
   int    tipo;
   int    vol;
   double preco;
   double custo;
   string ord_coment;     // comentario da ordem de origem (classificacao sem registro, A-3)
   bool   pendente;       // magic 0 sem ordem localizada, na carencia (M-5): sem efeito nas fichas          // DEAL_COMMISSION + DEAL_FEE (negativos = cobranca)
   double lucro;
   string coment;
   int    robo;
   int    papel;
   int    papel_mapa;     // papel conhecido pelo proprio envio (mapa de ordens do maestro); 0 = nao
   bool   verificado;     // ordem do deal ja' procurada (magic 0 resolvido ou papel conhecido)
   bool   ajuste;         // par fecha/reabre externo fora do continuo (ajuste noturno, P14): sem efeito nas fichas
   bool   ord_ok;
   int    ord_tipo;
   long   ord_setup;
   double ord_preco;
   int    f_antes;
   int    f_depois;
   int    liq_antes;
   int    liq_depois;
   bool   novo;
};

struct SCk  { int robo; long t; int f; };
struct SAbs { ulong deal; int robo; int vol; double preco; long t; };

// leitura
bool       mzLiqOk = false;
double     mzLiquidaD = 0.0;
int        mzLiq = 0;
bool       mzPendOk = false;
SOrdemViva mzPend[];
bool       mzConectado = false;
datetime   mzConectadoDesde = 0;
bool       mzReler = true;
bool       mzReleuOk = false;          // releitura completa feita depois da ultima (re)conexao
datetime   mzUltReleitura = 0;
datetime   mzCruzUltTent = 0;
bool       mzCruzOk = false;
datetime   mzCruzFalhaDesde = 0;
int        mzDifPendente = 0;
int        mzExtDesc = 0;              // externa de origem desconhecida (memoria)
int        mzExtIni = 0;               // externa no inicio da janela em uso
datetime   mzJanIni = 0;
SDealC     mzDl[];
SOrdemHist mzHo[];
long       mzUltDealMsc = 0;           // ultimo deal ja' logado (memoria)
ulong      mzUltDealTk = 0;
ulong      mzLogTk[];                  // deals logados nesta execucao (dois deals no mesmo ms)
double     mzTickSize = 0.0;
double     mzTickValor = 0.0;
int        mzDigitos = 0;
ENUM_ORDER_TYPE_FILLING mzFillMercado = ORDER_FILLING_RETURN;
datetime   mzVencimento = 0;

// fichas (saida de Ficha_Calcula)
int    mzF[NROBOS];
double mzPm[NROBOS];
long   mzHoraMsc[NROBOS];
ulong  mzFid[NROBOS];
bool   mzPorE[NROBOS];
double mzRes[NROBOS];
double mzResBruto[NROBOS];
int    mzContratos[NROBOS];
long   mzZeroMsc[NROBOS];        // instante do deal que levou a ficha a zero (OCO, 5.4)
bool   mzIndet[NROBOS];          // ficha com deal de ordem ainda nao identificada: nada e' decidido para o robo
datetime mzIndetDesde[NROBOS];   // desde quando a ficha esta' indeterminada (30 s depois vira trocada, M-4)
string mzSaidaPedida[NROBOS];    // saida por regra do robo barrada por estado aberto: o maestro envia quando fechar (A-2)
ulong  mzSaidaFid[NROBOS];       // ficha a que o pedido se refere (deal de abertura)
bool   mzMagic0Pend = false;     // deal sem magic e sem ordem localizada ainda na carencia de 10 s (M-5)
datetime mzRelerPedido = 0;      // ultima releitura completa pedida por estado aberto (B-7)
int    mzEvR[];                  // avisos aos modulos enfileirados ate' os modulos iniciarem (B-1)
int    mzEvE[];
int    mzExt = 0;
SCk    mzCk[];
SAbs   mzAbs[];
bool   mzHouveExternoHoje = false;
double mzLucroHoje = 0.0;
bool   mzDiaComecouZerado = true;

// intencao e controle por robo
double   mzStopNivel[NROBOS];
double   mzAlvoNivel[NROBOS];
ulong    mzETicket[NROBOS];
int      mzEDir[NROBOS];
datetime mzEVivaDesde[NROBOS];
datetime mzESumiuDesde[NROBOS];
bool     mzECancelPedido[NROBOS];
datetime mzSemSDesde[NROBOS];
// retentativas e recusas por papel (B-8): uma recusa de alvo nunca atrasa a zeragem, e o ALERTA conta um papel so'
#define RC_X 0   // saidas, correcoes, zeragens
#define RC_S 1   // protecao (S)
#define RC_A 2   // alvo
#define RC_K 3   // cancelamento da E
datetime mzRecProx[NROBOS][4];
int      mzRecN[NROBOS][4];
datetime mzRecAl[NROBOS][4];
datetime mzUltCorrecao[NROBOS];    // instante da ultima correcao EXECUTADA
bool     mzCorrTravada[NROBOS];
bool     mzEpisodio[NROBOS];        // ficha trocada/duplicada em curso (um episodio = um periodo continuo com a ficha errada)
datetime mzCorteAlertaR[NROBOS];
int      mzSeq[NROBOS];
datetime mzSeqDia = 0;

// transito
STransito mzTr[];

// mapa das ordens que o proprio maestro mandou ou viu vivas: ticket -> robo e papel (atribuicao do deal, A-1/M-1)
ulong mzOmTk[];
int   mzOmRobo[];
int   mzOmPapel[];

// bloqueio e botao
bool     mzBloq = false;
string   mzBloqMotivo = "";
bool     mzBloqCruz = false;
ulong    mzReconhecidos[];
ulong    mzAbsVistas[];
datetime mzBotaoClique = 0;
#define  MAE_BOTAO "WinMaestro_Desbloquear"

// partida
bool     mzIniciou = false;
bool     mzTravaPerdida = false;     // a trava passou a outro grafico: nenhum envio
bool     mzSemOrdens = false;        // conta nao NETTING: nenhum envio (so' ALERTA)
bool     mzMemFalhou = false;        // a ultima gravacao da memoria falhou: so' a protecao sai
bool     mzCorteConta = false;       // envio do corte com a cruzada aberta (zera a liquida REAL; D2)
datetime mzCorteContaAlerta = 0;
datetime mzCorteContaProx = 0;
bool     mzMemCarregada = false;     // nada e' gravado antes do passo 5 (senao apagaria a memoria antes de le^-la)
bool     mzPronto = false;
datetime mzProntoEm = 0;
datetime mzPartidaEm = 0;
datetime mzHeartbeatMem = 0;
bool     mzProtegendo = false;
bool     mzModulosIniciados = false;
datetime mzCorteDia = 0;
datetime mzResumoDia = 0;
datetime mzAvisoGradeDia = 0;
string   mzFichaMotivo = "";       // motivo do ultimo BLOQUEADA/RECUSADA (para o log do modulo)

// memoria carregada (para os modulos importarem no Init)
string mzCarK[];
string mzCarV[];
bool   mzCarMesmoDia = false;

//+------------------------------------------------------------------+
//| Utilitarios                                                      |
//+------------------------------------------------------------------+
int  Mae_Sinal(const int x)            { return x > 0 ? 1 : (x < 0 ? -1 : 0); }
int  Mae_Abs(const int x)              { return x < 0 ? -x : x; }
int  Mae_Min(const int a, const int b) { return a < b ? a : b; }
datetime Mae_Agora(void)               { return mzCorr.Agora(); }
datetime Mae_Dia(const datetime t)     { return t - (t % 86400); }
int  Mae_SegDia(const datetime t)      { return (int)(t % 86400); }
long Mae_AgoraMsc(void)
{
   long msc = (long)Mae_Agora() * 1000;
   MqlTick t;
   if(mzCorr.UltimoTick(t) && t.time_msc > msc && t.time_msc < msc + 1000) msc = t.time_msc;   // ms do ultimo tick (B-6)
   return msc;
}

// Aviso ao modulo; antes de os modulos iniciarem (passos 6-9 da partida) fica na fila e e' entregue depois do Init.
void Mae_Evento(const int r, const int ev)
{
   if(mzModulosIniciados) { Robo_Evento(r, ev); return; }
   int n = ArraySize(mzEvR);
   ArrayResize(mzEvR, n + 1); ArrayResize(mzEvE, n + 1);
   mzEvR[n] = r; mzEvE[n] = ev;
}

void Mae_EntregaEventos(void)
{
   int n = ArraySize(mzEvR);
   for(int i = 0; i < n; i++) Robo_Evento(mzEvR[i], mzEvE[i]);
   ArrayResize(mzEvR, 0); ArrayResize(mzEvE, 0);
}

// Estado aberto pede releitura completa, no maximo uma a cada 10 s (B-7).
void Mae_PedeReler(void)
{
   datetime a = Mae_Agora();
   if(a - mzRelerPedido >= 10) { mzReler = true; mzRelerPedido = a; }
}

int Mae_Robo(const long magic)
{
   for(int r = 0; r < NROBOS; r++) if(mzMagic[r] == magic) return r;
   return -1;
}

string Mae_Letra(const int papel)
{
   switch(papel)
   {
      case P_E: return "E";
      case P_S: return "S";
      case P_A: return "A";
      case P_X: return "X";
      case P_C: return "C";
      case P_K: return "K";
   }
   return "?";
}

bool Mae_TipoStop(const int t)
{
   return t == ORDER_TYPE_BUY_STOP || t == ORDER_TYPE_SELL_STOP || t == ORDER_TYPE_BUY_STOP_LIMIT || t == ORDER_TYPE_SELL_STOP_LIMIT;
}
bool Mae_TipoLimite(const int t) { return t == ORDER_TYPE_BUY_LIMIT || t == ORDER_TYPE_SELL_LIMIT; }
int  Mae_LadoTipo(const int t)
{
   return (t == ORDER_TYPE_BUY || t == ORDER_TYPE_BUY_LIMIT || t == ORDER_TYPE_BUY_STOP || t == ORDER_TYPE_BUY_STOP_LIMIT) ? 1 : -1;
}
string Mae_TipoNome(const int t)
{
   string s = EnumToString((ENUM_ORDER_TYPE)t);
   StringReplace(s, "ORDER_TYPE_", "");
   StringToLower(s);
   return s;
}

double Mae_NoTick(const double p)
{
   if(mzTickSize <= 0.0) return p;
   return NormalizeDouble(MathRound(p / mzTickSize) * mzTickSize, mzDigitos);
}

double Mae_ValorPonto(void)
{
   if(mzTickSize <= 0.0 || mzTickValor <= 0.0) return 0.0;
   return mzTickValor / mzTickSize;
}

// Piso para "nivel atravessado": max(1 tick, SYMBOL_TRADE_STOPS_LEVEL) (itens 1.25, 4.30).
double Ficha_PisoStop(void)
{
   double pt = mzCorr.SimboloD(SYMBOL_POINT);
   double sl = (double)mzCorr.SimboloI(SYMBOL_TRADE_STOPS_LEVEL) * pt;
   return MathMax(mzTickSize, sl);
}

// Le tamanho/valor do tick do simbolo; leitura zerada nunca e' usada (item 5.22).
bool Mae_LeTick(void)
{
   double ts = mzCorr.SimboloD(SYMBOL_TRADE_TICK_SIZE);
   double tv = mzCorr.SimboloD(SYMBOL_TRADE_TICK_VALUE);
   if(ts > 0.0) mzTickSize = ts;
   if(tv > 0.0) mzTickValor = tv;
   mzDigitos = (int)mzCorr.SimboloI(SYMBOL_DIGITS);
   return mzTickSize > 0.0 && mzTickValor > 0.0;
}

//+------------------------------------------------------------------+
//| Horarios (sec. 9)                                                    |
//+------------------------------------------------------------------+
bool Mae_DiaUtil(const datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   return d.day_of_week != 0 && d.day_of_week != 6;
}

// Horarios do dia em minutos: pre-abertura, inicio do continuo, F (fim do continuo) e corte (F - 5).
void Mae_Horarios(const datetime t, int &pre, int &neg, int &fim, int &corte)
{
   datetime dia = Mae_Dia(t);
   int venc = 0;
   bool tem = Grade_Le(dia, pre, neg, fim, venc);
   if(!tem && mzAvisoGradeDia != dia && mzCorr != NULL)
   {
      mzAvisoGradeDia = dia;
      Log("AVISO", "MAESTRO", "AMBIENTE", StringFormat("data %s sem linha na grade: F = 17:55 (corte 17:50)", TimeToString(dia, TIME_DATE)));
   }
   // o vencimento do contrato do grafico nao muda o corte: vale o fim do continuo da grade do dia (decisao do dono)
   corte = fim - MARGEM_CORTE;
}

datetime Mae_FDe(const datetime t)     { int p, n, f, c; Mae_Horarios(t, p, n, f, c); return Mae_Dia(t) + f * 60; }
datetime Mae_CorteDe(const datetime t) { int p, n, f, c; Mae_Horarios(t, p, n, f, c); return Mae_Dia(t) + c * 60; }
datetime Mae_InicioDe(const datetime t){ int p, n, f, c; Mae_Horarios(t, p, n, f, c); return Mae_Dia(t) + n * 60; }

bool Mae_Continuo(const datetime t)
{
   if(!Mae_DiaUtil(t)) return false;
   int p, n, f, c; Mae_Horarios(t, p, n, f, c);
   int s = Mae_SegDia(t);
   return s >= n * 60 && s < f * 60;
}

// Janela em que o maestro manda qualquer ordem (S, cancelamento): da pre-abertura ate' F.
bool Mae_JanelaOrdens(const datetime t)
{
   if(!Mae_DiaUtil(t)) return false;
   int p, n, f, c; Mae_Horarios(t, p, n, f, c);
   int s = Mae_SegDia(t);
   return s >= p * 60 && s < f * 60;
}

// Janela do call (M-3): cancelamentos e S ate' CALL_MIN minutos depois de F (leilao de fechamento incluido).
#define CALL_MIN 15
bool Mae_JanelaCall(const datetime t)
{
   if(!Mae_DiaUtil(t)) return false;
   int p, n, f, c; Mae_Horarios(t, p, n, f, c);
   int s = Mae_SegDia(t);
   return s >= p * 60 && s < (f + CALL_MIN) * 60;
}

// Tick() dos robos: de negociacao_inicio ao corte.
bool Mae_JanelaTick(const datetime t)
{
   if(!Mae_DiaUtil(t)) return false;
   int p, n, f, c; Mae_Horarios(t, p, n, f, c);
   int s = Mae_SegDia(t);
   return s >= n * 60 && s < c * 60;
}

// Zeragem do robo = min(horario do robo, corte) (sec. 9.2).
datetime Mae_Zr(const int r, const datetime t)
{
   datetime dia = Mae_Dia(t);
   int p, n, f, c; Mae_Horarios(t, p, n, f, c);
   int z = Robo_MinutoZerar(r, dia);
   if(z <= 0 || z > c) z = c;
   return dia + z * 60;
}

//+------------------------------------------------------------------+
//| Transito (sec. 4.1)                                                  |
//+------------------------------------------------------------------+
bool Mae_TemTransito(const int r)
{
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++) if(mzTr[i].robo == r) return true;
   return false;
}

int Mae_TrIdx(const int r, const int seq, const int papel)
{
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++) if(mzTr[i].robo == r && mzTr[i].seq == seq && mzTr[i].papel == papel) return i;
   return -1;
}

void Mae_TrRemove(const int i)
{
   int n = ArraySize(mzTr);
   if(i < 0 || i >= n) return;
   for(int k = i; k < n - 1; k++) mzTr[k] = mzTr[k + 1];
   ArrayResize(mzTr, n - 1);
}

// OnTradeTransaction(TRADE_TRANSACTION_REQUEST): liga request_id ao ticket (busca por request_id, sec. 4.3).
void Mae_RequestVisto(const uint req_id, const ulong ordem)
{
   if(req_id == 0 || ordem == 0) return;
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++)
      if(mzTr[i].req_id == req_id && mzTr[i].ticket == 0 && mzTr[i].papel != P_K) mzTr[i].ticket = ordem;
}

int Mae_ProxSeq(const int r)
{
   datetime hoje = Mae_Dia(Mae_Agora());
   if(mzSeqDia != hoje)
   {
      for(int k = 0; k < NROBOS; k++) mzSeq[k] = 0;
      mzSeqDia = hoje;
   }
   mzSeq[r]++;
   return mzSeq[r];
}

// Le "MAE|CM|E|0042" -> robo e seq. false se nao for comentario do maestro.
bool Mae_LeComent(const string c, int &r, int &papel, int &seq)
{
   string p[];
   if(StringSplit(c, '|', p) != 4 || p[0] != "MAE") return false;
   r = -1;
   for(int k = 0; k < NROBOS; k++) if(mzNome[k] == p[1]) r = k;
   if(r < 0) return false;
   papel = 0;
   for(int k = P_E; k <= P_K; k++) if(Mae_Letra(k) == p[2]) papel = k;
   seq = (int)StringToInteger(p[3]);
   return papel > 0;
}

//+------------------------------------------------------------------+
//| Leitura da corretora e calculo das fichas (sec. 3, sec. 6)               |
//+------------------------------------------------------------------+
int Mae_HoIdx(const ulong tk)
{
   int n = ArraySize(mzHo);
   for(int i = n - 1; i >= 0; i--) if(mzHo[i].ticket == tk) return i;
   return -1;
}

void Mae_HoUpsert(const SOrdemHist &o)
{
   int i = Mae_HoIdx(o.ticket);
   if(i < 0) { i = ArraySize(mzHo); ArrayResize(mzHo, i + 1); }
   mzHo[i] = o;
}

int Mae_DlIdx(const ulong tk)
{
   int n = ArraySize(mzDl);
   for(int i = n - 1; i >= 0; i--) if(mzDl[i].ticket == tk) return i;
   return -1;
}

bool Mae_DealDaOrdem(const ulong ordem, int &idx)
{
   idx = -1;
   if(ordem == 0) return false;
   int n = ArraySize(mzDl);
   for(int i = 0; i < n; i++) if(mzDl[i].ordem == ordem) { idx = i; return true; }
   return false;
}

int Mae_PendIdx(const ulong tk)
{
   int n = ArraySize(mzPend);
   for(int i = 0; i < n; i++) if(mzPend[i].ticket == tk) return i;
   return -1;
}

bool Mae_Logado(const ulong tk)
{
   int n = ArraySize(mzLogTk);
   for(int i = n - 1; i >= 0; i--) if(mzLogTk[i] == tk) return true;
   return false;
}

int Mae_OmIdx(const ulong tk)
{
   int n = ArraySize(mzOmTk);
   for(int i = n - 1; i >= 0; i--) if(mzOmTk[i] == tk) return i;
   return -1;
}

void Mae_OmAdd(const ulong tk, const int r, const int papel)
{
   if(tk == 0 || r < 0) return;
   int i = Mae_OmIdx(tk);
   if(i >= 0) { if(mzOmPapel[i] == 0) mzOmPapel[i] = papel; return; }
   int n = ArraySize(mzOmTk);
   if(n >= 500)                                                  // limite: descarta as mais antigas
   {
      for(int k = 0; k < n - 100; k++) { mzOmTk[k] = mzOmTk[k + 100]; mzOmRobo[k] = mzOmRobo[k + 100]; mzOmPapel[k] = mzOmPapel[k + 100]; }
      n -= 100;
   }
   ArrayResize(mzOmTk, n + 1); ArrayResize(mzOmRobo, n + 1); ArrayResize(mzOmPapel, n + 1);
   mzOmTk[n] = tk; mzOmRobo[n] = r; mzOmPapel[n] = papel;
}

// A ordem pode ser a deste envio? (nao e' de outro papel ja' registrado, nem de outro envio no transito)
bool Mae_OmLivre(const ulong tk, const int papel)
{
   int om = Mae_OmIdx(tk);
   if(om >= 0 && mzOmPapel[om] != 0 && mzOmPapel[om] != papel) return false;
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++) if(mzTr[i].ticket == tk) return false;
   return true;
}

// Insere deals novos no cache (ordenado por instante e ticket). marcar_novo = vai ao log.
void Mae_Mescla(SDealInfo &d[], SOrdemHist &o[], const bool marcar_novo)
{
   int no = ArraySize(o);
   for(int i = 0; i < no; i++) Mae_HoUpsert(o[i]);
   int nd = ArraySize(d);
   for(int i = 0; i < nd; i++)
   {
      if(Mae_DlIdx(d[i].ticket) >= 0) continue;
      int n = ArraySize(mzDl);
      if(n > 0 && d[i].time_msc < mzDl[n - 1].t) mzReler = true;   // deal com hora anterior a' ultima processada
      ArrayResize(mzDl, n + 1);
      SDealC c;
      c.ticket = d[i].ticket; c.ordem = d[i].ordem; c.t = d[i].time_msc; c.magic = d[i].magic;
      c.tipo = d[i].tipo; c.vol = (int)MathRound(d[i].vol); c.preco = d[i].preco;
      c.custo = d[i].comissao + d[i].taxa; c.lucro = d[i].lucro; c.coment = d[i].comentario;
      c.robo = Mae_Robo(d[i].magic); c.papel = 0; c.papel_mapa = 0; c.verificado = false; c.ajuste = false;
      c.ord_ok = false; c.ord_tipo = -1; c.ord_setup = 0; c.ord_preco = 0.0; c.ord_coment = ""; c.pendente = false;
      c.f_antes = 0; c.f_depois = 0; c.liq_antes = 0; c.liq_depois = 0;
      c.novo = marcar_novo && (d[i].time_msc > mzUltDealMsc || (d[i].time_msc == mzUltDealMsc && d[i].ticket != mzUltDealTk)) && !Mae_Logado(d[i].ticket);
      // insercao ordenada
      int k = n;
      while(k > 0 && (mzDl[k - 1].t > c.t || (mzDl[k - 1].t == c.t && mzDl[k - 1].ticket > c.ticket)))
      {
         mzDl[k] = mzDl[k - 1];
         k--;
      }
      mzDl[k] = c;
   }
   // Ordem de origem de cada deal: decide o robo quando o DEAL_MAGIC vem 0 (P2) e o papel (tipo e
   // instante de colocacao, P3). Fontes: mapa do maestro, historico de ordens, HistoryOrderSelect.
   int n = ArraySize(mzDl);
   for(int i = 0; i < n; i++)
   {
      if(mzDl[i].ord_ok) continue;
      if(mzDl[i].robo < 0 && (mzDl[i].magic != 0 || mzDl[i].verificado)) continue;   // externo com magic, ou ja' procurado
      int om = Mae_OmIdx(mzDl[i].ordem);
      if(om >= 0)
      {
         if(mzDl[i].robo < 0)
         {
            mzDl[i].robo = mzOmRobo[om];
            Log_Cond("p2", true, "AVISO", mzNome[mzOmRobo[om]], "ESTADO", StringFormat("deal #%I64u sem DEAL_MAGIC atribuido pela ordem #%I64u do robo (P2)", mzDl[i].ticket, mzDl[i].ordem));
         }
         if(mzDl[i].robo == mzOmRobo[om]) mzDl[i].papel_mapa = mzOmPapel[om];
      }
      int h = Mae_HoIdx(mzDl[i].ordem);
      if(h < 0)
      {
         SOrdemHist oh;
         if(mzCorr.LeOrdemHist(mzDl[i].ordem, oh)) { Mae_HoUpsert(oh); h = Mae_HoIdx(mzDl[i].ordem); }
      }
      if(h >= 0)
      {
         if(mzDl[i].robo < 0)
         {
            int ro = Mae_Robo(mzHo[h].magic);
            if(ro >= 0)
            {
               mzDl[i].robo = ro;
               Log_Cond("p2", true, "AVISO", mzNome[ro], "ESTADO", StringFormat("deal #%I64u sem DEAL_MAGIC atribuido pela ordem #%I64u do robo (P2)", mzDl[i].ticket, mzDl[i].ordem));
            }
         }
         if(mzDl[i].robo >= 0)
         {
            mzDl[i].ord_ok = true;
            mzDl[i].ord_tipo = mzHo[h].tipo;
            mzDl[i].ord_setup = mzHo[h].setup_msc;
            mzDl[i].ord_preco = mzHo[h].preco;
            mzDl[i].ord_coment = mzHo[h].comentario;
         }
         mzDl[i].verificado = true;
      }
      if(om >= 0) mzDl[i].verificado = true;
   }
}

int Mae_SomaDeals(SDealInfo &d[])
{
   int s = 0, n = ArraySize(d);
   for(int i = 0; i < n; i++)
   {
      if(d[i].tipo == DEAL_TYPE_BUY)  s += (int)MathRound(d[i].vol);
      if(d[i].tipo == DEAL_TYPE_SELL) s -= (int)MathRound(d[i].vol);
   }
   return s;
}

// Recua um pregao (pula sabado e domingo).
datetime Mae_PregaoAnterior(const datetime dia)
{
   datetime d = dia - 86400;
   while(!Mae_DiaUtil(d)) d -= 86400;
   return d;
}

// Releitura completa: janela desde o ultimo instante com liquida zero (sec. 3.2).
bool Mae_ReleituraCompleta(void)
{
   datetime agora = Mae_Agora();
   mzCruzUltTent = agora;
   datetime dia = Mae_Dia(agora);
   SDealInfo d[];
   SOrdemHist o[];
   for(int k = 0; k < 10; k++)
   {
      int p, n, f, c;
      Mae_Horarios(dia, p, n, f, c);
      datetime ini = dia + n * 60 - 600;
      if(!mzCorr.LeHistorico(ini, agora + 86400, d, o)) return false;
      int soma = Mae_SomaDeals(d);
      int ext = -99999;
      if(soma == mzLiq) ext = 0;
      else if(mzExtDesc != 0 && soma + mzExtDesc == mzLiq) ext = mzExtDesc;
      if(ext != -99999)
      {
         if(ext == 0 && mzExtDesc != 0)
         {
            Log("AVISO", "MAESTRO", "HISTORICO", StringFormat("externa de origem desconhecida %+d nao e' mais necessaria: zerada", mzExtDesc));
            mzExtDesc = 0;
         }
         ArrayResize(mzDl, 0);
         ArrayResize(mzHo, 0);
         mzJanIni = ini; mzExtIni = ext;
         Mae_Mescla(d, o, true);
         mzCruzOk = true; mzReler = false; mzReleuOk = true; mzUltReleitura = agora;
         return true;
      }
      if(k < 9) dia = Mae_PregaoAnterior(dia);
   }
   // nao fechou em 10 pregoes: fica com a janela mais longa e anota a diferenca (sec. 3.2)
   ArrayResize(mzDl, 0);
   ArrayResize(mzHo, 0);
   int p2, n2, f2, c2;
   Mae_Horarios(dia, p2, n2, f2, c2);
   mzJanIni = dia + n2 * 60 - 600; mzExtIni = 0;
   Mae_Mescla(d, o, true);
   mzDifPendente = mzLiq - Mae_SomaDeals(d);
   mzCruzOk = false; mzReler = false; mzReleuOk = true; mzUltReleitura = agora;
   return true;
}

bool Mae_LeituraIncremental(void)
{
   datetime agora = Mae_Agora();
   int n = ArraySize(mzDl);
   datetime de = (n > 0) ? (datetime)(mzDl[n - 1].t / 1000) - 60 : mzJanIni;
   if(de < mzJanIni) de = mzJanIni;
   SDealInfo d[];
   SOrdemHist o[];
   if(!mzCorr.LeHistorico(de, agora + 86400, d, o)) return false;
   Mae_Mescla(d, o, true);
   return true;
}

// Ficha do robo r no instante t (deals com hora <= t: uma ordem colocada no mesmo milissegundo de um
// deal ja' viu esse deal -- no Testador o preenchimento e a ordem seguinte saem no mesmo tick).
int Mae_FichaEm(const int r, const long t)
{
   int f = 0, n = ArraySize(mzCk);
   for(int i = 0; i < n; i++)
   {
      if(mzCk[i].t > t) break;
      if(mzCk[i].robo == r) f = mzCk[i].f;
   }
   return f;
}

void Mae_CkAdd(const int r, const long t)
{
   int n = ArraySize(mzCk);
   ArrayResize(mzCk, n + 1);
   mzCk[n].robo = r; mzCk[n].t = t; mzCk[n].f = mzF[r];
}

void Ficha_Aplica(const int r, const int v, const double preco, const long t, const ulong tk, const int papel, const bool hoje)
{
   int a = mzF[r];
   int b = a + v;
   if(a == 0 || Mae_Sinal(a) == Mae_Sinal(v))
      mzPm[r] = (a == 0) ? preco : (mzPm[r] * Mae_Abs(a) + preco * Mae_Abs(v)) / Mae_Abs(b);
   else
   {
      int fechar = Mae_Min(Mae_Abs(a), Mae_Abs(v));
      if(hoje) mzResBruto[r] += (preco - mzPm[r]) * fechar * Mae_Sinal(a) * Mae_ValorPonto();
      if(Mae_Abs(v) > Mae_Abs(a)) mzPm[r] = preco;
      else if(b == 0) mzPm[r] = 0.0;
   }
   mzF[r] = b;
   if(a == 0 && b != 0)                           { mzPorE[r] = (papel == P_E); mzHoraMsc[r] = t; mzFid[r] = tk; }
   else if(a != 0 && b != 0 && Mae_Sinal(a) != Mae_Sinal(b)) { mzPorE[r] = false; mzHoraMsc[r] = t; mzFid[r] = tk; }
   else if(b == 0)                                { mzPorE[r] = false; mzHoraMsc[r] = 0; mzFid[r] = 0; }
   if(a != 0 && b == 0) mzZeroMsc[r] = t;
}

int Mae_SomaFichas(void)
{
   int s = 0;
   for(int r = 0; r < NROBOS; r++) s += mzF[r];
   return s;
}

// Calcula fichas, externa e absorcoes a partir do cache de deals. Funcao pura do historico (sec. 3.1, sec. 7.1).
void Ficha_Calcula(void)
{
   for(int r = 0; r < NROBOS; r++)
   {
      mzF[r] = 0; mzPm[r] = 0.0; mzHoraMsc[r] = 0; mzFid[r] = 0; mzPorE[r] = false;
      mzRes[r] = 0.0; mzResBruto[r] = 0.0; mzContratos[r] = 0; mzZeroMsc[r] = 0; mzIndet[r] = false;
   }
   mzExt = mzExtIni;
   ArrayResize(mzCk, 0);
   ArrayResize(mzAbs, 0);
   mzHouveExternoHoje = false;
   mzLucroHoje = 0.0;
   mzMagic0Pend = false;
   long agora_msc = (long)Mae_Agora() * 1000;
   datetime hoje = Mae_Dia(Mae_Agora());
   mzDiaComecouZerado = true;
   bool zerado_ate_hoje = true;
   int n = ArraySize(mzDl);
   for(int i = 0; i < n; i++)
   {
      int s = 0;
      if(mzDl[i].tipo == DEAL_TYPE_BUY) s = 1;
      else if(mzDl[i].tipo == DEAL_TYPE_SELL) s = -1;
      else continue;                                      // balanco, credito, taxa: nao entram no volume
      int v = s * mzDl[i].vol;
      long t = mzDl[i].t;
      // deal sem magic cuja ordem ainda nao foi localizada: 10 s de carencia sem efeito nas fichas (M-5)
      mzDl[i].pendente = (mzDl[i].robo < 0 && mzDl[i].magic == 0 && !mzDl[i].verificado && agora_msc - t < 10000);
      if(mzDl[i].pendente)
      {
         mzMagic0Pend = true;
         mzDl[i].liq_antes = Mae_SomaFichas() + mzExt; mzDl[i].liq_depois = mzDl[i].liq_antes;
         continue;
      }
      // ajuste noturno lancado como fecha/reabre (P14): dois deals externos opostos, mesmo volume, no mesmo segundo, fora do continuo
      mzDl[i].ajuste = false;
      if(mzDl[i].robo < 0 && i + 1 < n && mzDl[i + 1].robo < 0 && mzDl[i + 1].vol == mzDl[i].vol &&
         ((mzDl[i].tipo == DEAL_TYPE_BUY && mzDl[i + 1].tipo == DEAL_TYPE_SELL) || (mzDl[i].tipo == DEAL_TYPE_SELL && mzDl[i + 1].tipo == DEAL_TYPE_BUY)) &&
         mzDl[i + 1].t - t <= 1000 && !Mae_Continuo((datetime)(t / 1000)))
      {
         mzDl[i].ajuste = true; mzDl[i + 1].ajuste = true;
         mzDl[i].liq_antes = Mae_SomaFichas() + mzExt; mzDl[i].liq_depois = mzDl[i].liq_antes;
         mzDl[i + 1].liq_antes = mzDl[i].liq_antes; mzDl[i + 1].liq_depois = mzDl[i].liq_antes;
         i++;
         continue;
      }
      bool de_hoje = (datetime)(t / 1000) >= hoje;
      if(de_hoje && zerado_ate_hoje) { zerado_ate_hoje = false; mzDiaComecouZerado = (Mae_SomaFichas() + mzExt == 0); }
      if(de_hoje) mzLucroHoje += mzDl[i].lucro;
      mzDl[i].liq_antes = Mae_SomaFichas() + mzExt;
      int r = mzDl[i].robo;
      if(r >= 0)
      {
         // papel: o registro do envio e' a verdade (A-3); sem registro, o comentario MAE; sem ele, tipo e ficha na colocacao
         int papel;
         int rc_, pc_, sc_;
         if(mzDl[i].papel_mapa > 0) papel = (mzDl[i].papel_mapa == P_S || mzDl[i].papel_mapa == P_E) ? mzDl[i].papel_mapa : P_X;
         else if(mzDl[i].ord_ok && Mae_TipoStop(mzDl[i].ord_tipo)) papel = P_S;
         else if(mzDl[i].ord_ok && Mae_LeComent(mzDl[i].ord_coment, rc_, pc_, sc_) && rc_ == r) papel = (pc_ == P_E || pc_ == P_S) ? pc_ : P_X;
         else if(mzDl[i].ord_ok) papel = (Mae_FichaEm(r, mzDl[i].ord_setup) == 0) ? P_E : P_X;
         else { papel = (mzF[r] == 0) ? P_E : P_X; mzIndet[r] = true; }   // ordem ainda nao identificada: ficha indeterminada
         mzDl[i].papel = papel;
         mzDl[i].f_antes = mzF[r];
         Ficha_Aplica(r, v, mzDl[i].preco, t, mzDl[i].ticket, papel, de_hoje);
         if(de_hoje) { mzRes[r] += mzDl[i].custo; mzContratos[r] += mzDl[i].vol; }
         Mae_CkAdd(r, t);
         mzDl[i].f_depois = mzF[r];
      }
      else
      {
         if(de_hoje) mzHouveExternoHoje = true;
         int rem = v;
         // 1. compensa a externa existente de sinal oposto
         if(mzExt != 0 && Mae_Sinal(mzExt) != Mae_Sinal(rem))
         {
            int k = Mae_Min(Mae_Abs(mzExt), Mae_Abs(rem));
            mzExt += Mae_Sinal(rem) * k;
            rem   -= Mae_Sinal(rem) * k;
         }
         if(rem != 0)
         {
            int liq = Mae_SomaFichas() + mzExt;
            if(liq == 0 || Mae_Sinal(liq) == Mae_Sinal(rem)) mzExt += rem;   // 2. aumenta |liquida|: externa
            else
            {
               // 3. reduz a liquida abaixo da soma das fichas: zeragem manual, absorcao na ordem fixa
               for(int ra = 0; ra < NROBOS && rem != 0; ra++)
               {
                  if(mzF[ra] == 0 || Mae_Sinal(mzF[ra]) == Mae_Sinal(rem)) continue;
                  int a = Mae_Min(Mae_Abs(mzF[ra]), Mae_Abs(rem));
                  Ficha_Aplica(ra, Mae_Sinal(rem) * a, mzDl[i].preco, t, mzDl[i].ticket, P_X, de_hoje);
                  int na = ArraySize(mzAbs);
                  ArrayResize(mzAbs, na + 1);
                  mzAbs[na].deal = mzDl[i].ticket; mzAbs[na].robo = ra; mzAbs[na].vol = a; mzAbs[na].preco = mzDl[i].preco; mzAbs[na].t = t;
                  Mae_CkAdd(ra, t);
                  rem -= Mae_Sinal(rem) * a;
               }
               if(rem != 0) mzExt += rem;
            }
         }
      }
      mzDl[i].liq_depois = Mae_SomaFichas() + mzExt;
   }
   if(zerado_ate_hoje) mzDiaComecouZerado = (Mae_SomaFichas() + mzExt == 0);
   for(int r = 0; r < NROBOS; r++)
   {
      mzRes[r] += mzResBruto[r];
      if(mzF[r] == 0) mzIndet[r] = false;                 // ficha zero nao tem direcao a duvidar
      if(!mzIndet[r]) mzIndetDesde[r] = 0;
      else if(mzIndetDesde[r] == 0) mzIndetDesde[r] = Mae_Agora();
   }
}

void Mae_Conexao(void)
{
   bool c = mzCorr.Conectado();
   datetime agora = Mae_Agora();
   if(c && !mzConectado)
   {
      mzConectadoDesde = agora;
      mzReler = true;
      mzReleuOk = false;
      if(mzIniciou) Log("AVISO", "MAESTRO", "ESTADO", "conexao (re)estabelecida: releitura completa do historico");
   }
   if(!c && mzConectado) Log("AVISO", "MAESTRO", "ESTADO", "terminal desconectado: nada e' enviado nem resolvido");
   mzConectado = c;
}

// Le liquida, pendentes e historico e recalcula as fichas. Chamado antes de qualquer decisao (sec. 3.1).
void Leitura_Atualiza(const bool completa)
{
   Mae_Conexao();
   double pr = 0.0;
   mzLiqOk = mzCorr.LeLiquida(mzLiquidaD, pr);
   if(mzLiqOk) mzLiq = (int)MathRound(mzLiquidaD);
   mzPendOk = mzCorr.LePendentes(mzPend);
   if(!mzLiqOk) return;                                  // leitura descartada (item 1.6)
   datetime agora = Mae_Agora();
   bool ok;
   if(completa || mzReler || agora - mzUltReleitura >= 600 || (!mzCruzOk && agora - mzCruzUltTent >= 10))
      ok = Mae_ReleituraCompleta();
   else
      ok = Mae_LeituraIncremental();
   if(!ok) { mzReler = true; mzReleuOk = false; return; }   // historico ilegivel: estado nao confiavel ate' uma releitura completa (A-4)
   Ficha_Calcula();
   mzCruzOk = (Mae_SomaFichas() + mzExt == mzLiq);
   if(mzPendOk)
   {
      int np = ArraySize(mzPend);
      for(int i = 0; i < np; i++)
      {
         int ro = Mae_Robo(mzPend[i].magic);
         if(ro >= 0) Mae_OmAdd(mzPend[i].ticket, ro, Mae_TipoStop(mzPend[i].tipo) ? P_S : 0);
      }
   }
   if(mzCruzOk) mzCruzFalhaDesde = 0;
   else if(mzCruzFalhaDesde == 0) mzCruzFalhaDesde = agora;
}

bool Mae_LeituraConfiavel(void)
{
   if(!mzLiqOk || !mzPendOk || !mzReleuOk) return false;
   if(mzCorr.Testador()) return true;
   return mzConectado && Mae_Agora() - mzConectadoDesde >= 10;
}

//+------------------------------------------------------------------+
//| Estado de cada robo: papeis das ordens vivas e invariantes (sec. 2)  |
//+------------------------------------------------------------------+
#define MAX_ORD 32
struct SRoboEstado
{
   int  f;
   int  iE;          // E valida (indice em mzPend; -1 = nenhuma)
   int  iS;          // S valida mais protetora
   int  iA;          // A valida
   int  dirE;        // direcao da E (viva, sem desfecho ou ainda nao confirmada)
   bool trans;       // transitorio da entrada (5.3)
   int  lp;          // lado protegido pela S (+1 compra, -1 venda, 0 nada)
   int  need;        // volume de S necessario (|ficha|, ou 1 para a E)
   int  volS;        // volume das S validas
   int  nSk;
   int  sKeep[MAX_ORD];
   int  nOrfas;
   int  orfas[MAX_ORD];
   int  nVivas;      // ordens vivas do robo
};

// Papel de uma ordem viva: stop = S; limite colocada com ficha 0 = E; senao A.
int Mae_PapelViva(const int r, const int i)
{
   if(Mae_TipoStop(mzPend[i].tipo)) return P_S;
   if(Mae_TipoLimite(mzPend[i].tipo)) return (Mae_FichaEm(r, mzPend[i].setup_msc) == 0) ? P_E : P_A;
   return 0;
}

// Direcao de uma E de mercado ainda sem desfecho no transito (C1).
int Mae_DirETransito(const int r)
{
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++) if(mzTr[i].robo == r && mzTr[i].papel == P_E) return mzTr[i].lado;
   return 0;
}

// Trocada: ficha aberta por deal que nao foi E (fora do transitorio). Duplicada: aberta por E, com |ficha| >= 2.
// Ficha indeterminada ha' 30 s: a ordem nao apareceu; passa a ser tratada como trocada (correcao e corte, M-4).
bool Mae_IndetVelha(const int r) { return mzIndet[r] && mzIndetDesde[r] > 0 && Mae_Agora() - mzIndetDesde[r] >= 30; }
bool Mae_Trocada(const int r, const SRoboEstado &e)   { return e.f != 0 && ((!mzPorE[r] && !e.trans) || Mae_IndetVelha(r)); }
bool Mae_Duplicada(const int r, const SRoboEstado &e) { return mzPorE[r] && Mae_Abs(e.f) >= 2 && !Mae_IndetVelha(r); }
bool Mae_Noite(const int r)
{
   return mzF[r] != 0 && mzHoraMsc[r] > 0 && (datetime)(mzHoraMsc[r] / 1000) < Mae_Dia(Mae_Agora());
}

void Mae_EstadoOrfa(SRoboEstado &e, const int i) { if(e.nOrfas < MAX_ORD) e.orfas[e.nOrfas++] = i; }

void Mae_Estado(const int r, SRoboEstado &e)
{
   e.f = mzF[r]; e.iE = -1; e.iS = -1; e.iA = -1; e.dirE = 0; e.trans = false; e.lp = 0; e.need = 0; e.volS = 0;
   e.nSk = 0; e.nOrfas = 0; e.nVivas = 0;
   int n = ArraySize(mzPend);
   int iEs[MAX_ORD], iSs[MAX_ORD], iAs[MAX_ORD];
   int nE = 0, nS = 0, nA = 0;
   for(int i = 0; i < n; i++)
   {
      if(mzPend[i].magic != mzMagic[r]) continue;
      e.nVivas++;
      int p = Mae_PapelViva(r, i);
      if(p == P_E && nE < MAX_ORD) iEs[nE++] = i;
      else if(p == P_S && nS < MAX_ORD) iSs[nS++] = i;
      else if(p == P_A && nA < MAX_ORD) iAs[nA++] = i;
      else Mae_EstadoOrfa(e, i);
   }
   // E: a conhecida (mzETicket) ou a mais antiga; as demais sao excedentes
   for(int k = 0; k < nE; k++) if(mzPend[iEs[k]].ticket == mzETicket[r]) e.iE = iEs[k];
   if(e.iE < 0) for(int k = 0; k < nE; k++) if(e.iE < 0 || mzPend[iEs[k]].setup_msc < mzPend[e.iE].setup_msc) e.iE = iEs[k];
   if(e.iE >= 0) e.dirE = Mae_LadoTipo(mzPend[e.iE].tipo);
   else if(mzETicket[r] != 0 && e.f == 0) e.dirE = mzEDir[r];    // E que sumiu da lista e ainda nao foi confirmada: segue tratada como viva
   if(e.dirE == 0) e.dirE = Mae_DirETransito(r);
   e.trans = (Mae_Abs(e.f) == 1 && !mzPorE[r] && e.dirE != 0 && e.f == -e.dirE);
   if(e.f != 0 && !e.trans) { e.lp = Mae_Sinal(e.f); e.need = Mae_Abs(e.f); }
   else if(e.f == 0 && e.dirE != 0) { e.lp = e.dirE; e.need = 1; }
   // E so' com ficha 0 (ou no transitorio)
   if(e.iE >= 0 && !(e.f == 0 || e.trans)) e.iE = -1;
   for(int k = 0; k < nE; k++) if(iEs[k] != e.iE) Mae_EstadoOrfa(e, iEs[k]);
   // S: do lado que protege, das mais protetoras para as menos, ate' o volume necessario
   for(int a = 1; a < nS; a++)
   {
      int x = iSs[a], b = a - 1;
      while(b >= 0)
      {
         bool antes = (e.lp > 0) ? mzPend[x].preco > mzPend[iSs[b]].preco : mzPend[x].preco < mzPend[iSs[b]].preco;
         if(!antes) break;
         iSs[b + 1] = iSs[b];
         b--;
      }
      iSs[b + 1] = x;
   }
   for(int k = 0; k < nS; k++)
   {
      int i = iSs[k];
      int protege = -Mae_LadoTipo(mzPend[i].tipo);     // SELL_STOP protege compra (+1)
      int v = (int)MathRound(mzPend[i].vol);
      if(e.lp != 0 && protege == e.lp && e.volS + v <= e.need && e.nSk < MAX_ORD)
      {
         e.sKeep[e.nSk++] = i;
         e.volS += v;
         if(e.iS < 0) e.iS = i;
      }
      else Mae_EstadoOrfa(e, i);
   }
   // A: so' com ficha valida (nao trocada, nao transitoria), do lado oposto; no maximo uma
   bool a_ok = (e.f != 0 && !e.trans && mzPorE[r]);
   for(int k = 0; k < nA; k++)
   {
      int i = iAs[k];
      bool ok = a_ok && Mae_LadoTipo(mzPend[i].tipo) == -Mae_Sinal(e.f);
      if(ok && e.iA < 0) e.iA = i;
      else if(ok && mzAlvoNivel[r] > 0.0 && MathAbs(mzPend[i].preco - mzAlvoNivel[r]) < MathAbs(mzPend[e.iA].preco - mzAlvoNivel[r]))
      {
         Mae_EstadoOrfa(e, e.iA);
         e.iA = i;
      }
      else Mae_EstadoOrfa(e, i);
   }
}

// A ficha que o modulo enxerga: +-1 aberta por uma E (trocada, duplicada e transitorio o modulo nunca ve).
bool Ficha_Tem(const int r)        { return Mae_Abs(mzF[r]) == 1 && mzPorE[r] && !mzIndet[r]; }
int  Ficha_Lado(const int r)       { return Ficha_Tem(r) ? Mae_Sinal(mzF[r]) : 0; }
double Ficha_Preco(const int r)    { return Ficha_Tem(r) ? mzPm[r] : 0.0; }
datetime Ficha_Hora(const int r)   { return Ficha_Tem(r) ? (datetime)(mzHoraMsc[r] / 1000) : 0; }
ulong Ficha_Id(const int r)        { return Ficha_Tem(r) ? mzFid[r] : 0; }
double Ficha_Stop(const int r)     { return mzStopNivel[r]; }
string Ficha_Motivo(void)          { return mzFichaMotivo; }

bool Ficha_TemAlvo(const int r)
{
   SRoboEstado e; Mae_Estado(r, e);
   return e.iA >= 0;
}

// E viva (ou sem desfecho) do robo: lado, preco e hora de colocacao. Substitui OrderSelect(g_ordem).
bool Ficha_Entrada(const int r, int &lado, double &preco, datetime &setup)
{
   SRoboEstado e; Mae_Estado(r, e);
   if(e.iE >= 0)
   {
      lado = Mae_LadoTipo(mzPend[e.iE].tipo); preco = mzPend[e.iE].preco; setup = (datetime)(mzPend[e.iE].setup_msc / 1000);
      return true;
   }
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++)
      if(mzTr[i].robo == r && mzTr[i].papel == P_E) { lado = mzTr[i].lado; preco = mzTr[i].preco; setup = mzTr[i].hora; return true; }
   if(mzETicket[r] != 0 && mzF[r] == 0) { lado = mzEDir[r]; preco = 0.0; setup = mzEVivaDesde[r]; return true; }
   return false;
}

//+------------------------------------------------------------------+
//| Bloqueio de entradas e botao (sec. 7.2)                              |
//+------------------------------------------------------------------+
void Mae_BotaoMostra(const bool mostra)
{
   if(mzCorr == NULL || mzCorr.Testador()) return;
   if(!mostra) { ObjectDelete(0, MAE_BOTAO); return; }
   if(ObjectFind(0, MAE_BOTAO) >= 0) return;
   ObjectCreate(0, MAE_BOTAO, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_XDISTANCE, 170);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_XSIZE, 160);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_YSIZE, 30);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_BGCOLOR, clrFireBrick);
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_COLOR, clrWhite);
   ObjectSetString(0, MAE_BOTAO, OBJPROP_TEXT, "Desbloquear");
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_STATE, false);
}

void Mae_GravaMemoria(const bool forcar);

void Mae_Bloqueia(const string causa)
{
   if(StringFind(mzBloqMotivo, causa) < 0) mzBloqMotivo = (mzBloqMotivo == "") ? causa : mzBloqMotivo + "; " + causa;
   if(!mzBloq)
   {
      mzBloq = true;
      Log("ALERTA", "MAESTRO", "BLOQUEIO", "entradas bloqueadas: " + causa + " -- olhe o extrato e use o botao Desbloquear (2 cliques em 3 s)");
   }
   else Log("AVISO", "MAESTRO", "BLOQUEIO", "nova causa: " + causa);
   Mae_BotaoMostra(true);
   Mae_GravaMemoria(true);
}

bool Mae_Reconhecido(const ulong tk)
{
   int n = ArraySize(mzReconhecidos);
   for(int i = 0; i < n; i++) if(mzReconhecidos[i] == tk) return true;
   return false;
}

void Mae_Desbloqueia(void)
{
   // grava as absorcoes vistas como reconhecidas
   int na = ArraySize(mzAbsVistas);
   for(int i = 0; i < na; i++)
      if(!Mae_Reconhecido(mzAbsVistas[i]))
      {
         int n = ArraySize(mzReconhecidos);
         ArrayResize(mzReconhecidos, n + 1);
         mzReconhecidos[n] = mzAbsVistas[i];
      }
   // ordens sem desfecho ha' 10 min saem do transito (a ficha continua vindo dos deals); as recentes ficam
   datetime agora_d = Mae_Agora();
   for(int i = ArraySize(mzTr) - 1; i >= 0; i--)
   {
      if(agora_d - mzTr[i].hora < PRAZO_SEM_DESFECHO) continue;
      Log("AVISO", mzNome[mzTr[i].robo], "DESBLOQUEIO", StringFormat("ordem sem desfecho retirada do transito pelo dono: %s ord #%I64u", mzTr[i].coment, mzTr[i].ticket));
      Mae_TrRemove(i);
   }
   if(mzBloqCruz && mzDifPendente != 0)
   {
      mzExtDesc = mzDifPendente;
      Log("AVISO", "MAESTRO", "DESBLOQUEIO", StringFormat("diferenca %+d gravada como externa de origem desconhecida", mzExtDesc));
      mzReler = true;
   }
   for(int r = 0; r < NROBOS; r++) mzCorrTravada[r] = false;
   Log("INFO", "MAESTRO", "DESBLOQUEIO", "dono liberou as entradas (causas: " + mzBloqMotivo + ")");
   mzBloq = false; mzBloqMotivo = ""; mzBloqCruz = false;
   Mae_BotaoMostra(false);
   Mae_GravaMemoria(true);
}

// OnChartEvent: dois cliques em ate' 3 s.
void Mae_BotaoClique(const string obj)
{
   if(obj != MAE_BOTAO) return;
   ObjectSetInteger(0, MAE_BOTAO, OBJPROP_STATE, false);
   if(!mzBloq) { Mae_BotaoMostra(false); return; }
   datetime agora = TimeLocal();
   if(mzBotaoClique > 0 && agora - mzBotaoClique <= 3)
   {
      mzBotaoClique = 0;
      ObjectSetString(0, MAE_BOTAO, OBJPROP_TEXT, "Desbloquear");
      Mae_Desbloqueia();
      return;
   }
   mzBotaoClique = agora;
   ObjectSetString(0, MAE_BOTAO, OBJPROP_TEXT, "Confirmar (clique de novo)");
}

//+------------------------------------------------------------------+
//| Verificacao antes de toda ordem (D1, sec. 4.3)                       |
//+------------------------------------------------------------------+
// Autonegociacao (O2): E ou A que cruza com limite propria viva do lado oposto, de outro robo.
bool Mae_Autoneg(const int r, const int lado, const double preco)
{
   int n = ArraySize(mzPend);
   for(int i = 0; i < n; i++)
   {
      int ro = Mae_Robo(mzPend[i].magic);
      if(ro < 0 || ro == r || !Mae_TipoLimite(mzPend[i].tipo)) continue;
      if(lado > 0 && mzPend[i].tipo == ORDER_TYPE_SELL_LIMIT && preco >= mzPend[i].preco) return true;
      if(lado < 0 && mzPend[i].tipo == ORDER_TYPE_BUY_LIMIT  && preco <= mzPend[i].preco) return true;
   }
   return false;
}

// Transito do robo fora o cancelamento (uma S antiga em cancelamento nao barra a entrada nova, B-9).
bool Mae_TemTransitoNaoK(const int r)
{
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++) if(mzTr[i].robo == r && mzTr[i].papel != P_K) return true;
   return false;
}

// Ordens vivas do robo que nao sao stop (E, A, limites avulsas).
int Mae_VivasNaoStop(const int r)
{
   int c = 0, n = ArraySize(mzPend);
   for(int i = 0; i < n; i++) if(mzPend[i].magic == mzMagic[r] && !Mae_TipoStop(mzPend[i].tipo)) c++;
   return c;
}

bool Mae_TemTransitoPapel(const int r, const int papel)
{
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++) if(mzTr[i].robo == r && mzTr[i].papel == papel) return true;
   return false;
}

// O estado fecha? motivo vazio = fecha. alvo = ordem a cancelar/modificar (papel K ou modificacao).
// A protecao nao tem portao: a S (criar) so' confere a lista de ordens e a coerencia (lado e volume);
// leitura, cruzada e ordem em transito de outro papel nao a barram (C-1, A-4).
bool Mae_EstadoFecha(const int r, const int papel, const int lado, const double preco, const double vol,
                     const ulong alvo, const bool s_da_entrada, const bool e_com_s_propria, string &motivo)
{
   Leitura_Atualiza(false);
   motivo = "";
   if(mzSemOrdens) { motivo = "conta nao NETTING"; return false; }
   if(mzTravaPerdida && papel != P_S) { motivo = "a trava passou a outro grafico"; return false; }   // a S passa (5)
   if(mzCorteConta)
   {
      // corte com a cruzada aberta: so' a liquida REAL lida sem erro e a lista de ordens contam (D2)
      if(!mzLiqOk || !mzPendOk) { motivo = "posicao real ou ordens nao lidas"; return false; }
      if(papel == P_K && Mae_PendIdx(alvo) < 0) { motivo = "ordem a cancelar nao esta' viva"; return false; }
      if(papel == P_C && (mzLiq == 0 || lado != -Mae_Sinal(mzLiq) || (int)MathRound(vol) != Mae_Abs(mzLiq))) { motivo = "C do corte diferente da liquida"; return false; }
      return true;
   }
   SRoboEstado e; Mae_Estado(r, e);
   if(papel == P_S)
   {
      if(!mzPendOk) { motivo = "lista de ordens nao lida"; return false; }
      if(Mae_TemTransitoPapel(r, P_S)) { motivo = "outra S do robo sem desfecho"; return false; }
      int lp = e.lp, need = e.need;
      if(s_da_entrada && e.f == 0 && e.dirE == 0) { lp = -lado; need = 1; }
      if(lp == 0 || -lado != lp) { motivo = "S sem ficha nem E do lado que protege"; return false; }
      if(e.volS + (int)MathRound(vol) > need) { motivo = "S ja' cobre a ficha"; return false; }
      // a S nunca e' barrada por autonegociacao (protecao sem portao), mas o cruzamento com limite propria fica no log (B-5, P12)
      if(Mae_Autoneg(r, lado, preco))
         Log_Cond(StringFormat("autoneg_s.%d", r), true, "AVISO", mzNome[r], "AUTONEG", StringFormat("S @%.0f pode casar com limite propria de outro robo ao disparar (P12): enviada assim mesmo", preco));
      return true;
   }
   if(!Mae_LeituraConfiavel()) { motivo = "leitura nao confiavel"; return false; }
   if(!mzCruzOk) { motivo = StringFormat("verificacao cruzada nao fecha (deals %+d, liquida %+d)", Mae_SomaFichas() + mzExt, mzLiq); return false; }
   if(papel == P_E ? Mae_TemTransitoNaoK(r) : Mae_TemTransito(r)) { motivo = "robo tem ordem sem desfecho"; return false; }
   if(mzMemFalhou && papel == P_E) { motivo = "memoria nao gravada"; return false; }     // so' entradas novas (A-4)
   if(mzIndet[r] && !Mae_IndetVelha(r)) { motivo = "deal do robo com ordem ainda nao identificada"; return false; }
   switch(papel)
   {
      case P_E:
         if(e.f != 0) { motivo = "E com ficha aberta"; return false; }
         if(e.iE >= 0 || e.dirE != 0 || e.iA >= 0) { motivo = "E com outra operacao viva"; return false; }
         if(Mae_VivasNaoStop(r) > 0) { motivo = "E com ordens vivas do robo"; return false; }
         break;
      case P_A:
         if(e.f == 0 || lado != -Mae_Sinal(e.f) || e.trans) { motivo = "A sem ficha do lado certo"; return false; }
         if(e.iA >= 0 && e.iA != Mae_PendIdx(alvo)) { motivo = "ja' existe A viva"; return false; }
         break;
      case P_X:
         if(e.f == 0 || lado != -Mae_Sinal(e.f) || (int)MathRound(vol) != Mae_Abs(e.f)) { motivo = "X com volume diferente da ficha"; return false; }
         break;
      case P_C:
         if(e.f == 0 || lado != -Mae_Sinal(e.f) || (int)MathRound(vol) > Mae_Abs(e.f)) { motivo = "C sem ficha a corrigir"; return false; }
         break;
      case P_K:
         if(Mae_PendIdx(alvo) < 0) { motivo = "ordem a cancelar nao esta' viva"; return false; }
         break;
   }
   if((papel == P_E || papel == P_A) && Mae_Autoneg(r, lado, preco))
   {
      motivo = "autonegociacao";
      Log("AVISO", mzNome[r], "AUTONEG", StringFormat("%s %s @%.0f cruzaria com limite propria viva de outro robo: nao enviada", Mae_Letra(papel), lado > 0 ? "compra" : "venda", preco));
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Envio e desfecho (sec. 4.1, sec. 4.4)                                    |
//+------------------------------------------------------------------+
// Retcodes que provam recusa (o servidor respondeu "nao"). Qualquer outro sem prova = "nao sei" (itens 1.6, 1.24).
bool Mae_RecusaDefinitiva(const uint rc)
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

string Mae_DesfechoNome(const int d)
{
   switch(d)
   {
      case D_SEM:   return "sem desfecho";
      case D_VIVA:  return "viva";
      case D_EXEC:  return "executada";
      case D_NAO:   return "nao executada";
      case D_CANC:  return "cancelamento confirmado";
      case D_ANTES: return "executou antes do cancelamento";
   }
   return "?";
}

// Procura a prova do desfecho de uma ordem do transito (sec. 4.4, sec. 5.1).
int Mae_Prova(const int i, string &prova)
{
   prova = "";
   datetime agora = Mae_Agora();
   bool confiavel = Mae_LeituraConfiavel();
   int idade = (int)(agora - mzTr[i].hora);
   if(mzTr[i].papel == P_K)
   {
      ulong alvo = mzTr[i].ticket;
      int dl;
      if(Mae_PendIdx(alvo) >= 0)
      {
         if(Mae_RecusaDefinitiva(mzTr[i].retcode)) { prova = "cancelamento recusado; ordem segue listada"; return D_NAO; }
         if(confiavel && idade > IDADE_PROVA)      { prova = "ordem segue listada nas pendentes"; return D_NAO; }
         return D_SEM;
      }
      if(Mae_DealDaOrdem(alvo, dl)) { prova = StringFormat("deal #%I64u da ordem", mzDl[dl].ticket); return D_ANTES; }
      int h = Mae_HoIdx(alvo);
      if(h < 0)
      {
         SOrdemHist oh;
         if(mzCorr.LeOrdemHist(alvo, oh)) { Mae_HoUpsert(oh); h = Mae_HoIdx(alvo); }
      }
      if(h >= 0)
      {
         int st = mzHo[h].estado;
         if(st == ORDER_STATE_CANCELED || st == ORDER_STATE_EXPIRED || st == ORDER_STATE_REJECTED) { prova = "historico " + EnumToString((ENUM_ORDER_STATE)st); return D_CANC; }
         if(st == ORDER_STATE_FILLED || st == ORDER_STATE_PARTIAL) { prova = "historico " + EnumToString((ENUM_ORDER_STATE)st); return D_ANTES; }
      }
      return D_SEM;
   }
   // ordem nova: acha o ticket (retorno, request_id ou comentario)
   if(mzTr[i].ticket == 0)
   {
      // so' ordem do mesmo robo, colocada a partir de 2 s antes do envio (nunca a de ontem com o mesmo comentario)
      long desde = ((long)mzTr[i].hora - 2) * 1000;
      long mg = mzMagic[mzTr[i].robo];
      int n = ArraySize(mzPend);
      for(int k = 0; k < n && mzTr[i].ticket == 0; k++)
         if(mzPend[k].magic == mg && mzPend[k].setup_msc >= desde && mzPend[k].comentario == mzTr[i].coment) mzTr[i].ticket = mzPend[k].ticket;
      int nh = ArraySize(mzHo);
      for(int k = 0; k < nh && mzTr[i].ticket == 0; k++)
         if(mzHo[k].magic == mg && mzHo[k].setup_msc >= desde && mzHo[k].comentario == mzTr[i].coment) mzTr[i].ticket = mzHo[k].ticket;
      // comentario perdido (P3): ordem do robo com o mesmo tipo, volume e preco (limite/stop), colocada desde o envio - 2 s
      bool mercado = (mzTr[i].tipo == ORDER_TYPE_BUY || mzTr[i].tipo == ORDER_TYPE_SELL);
      for(int k = 0; k < n && mzTr[i].ticket == 0 && mzTr[i].tipo >= 0; k++)
         if(mzPend[k].magic == mg && mzPend[k].setup_msc >= desde && mzPend[k].tipo == mzTr[i].tipo && MathAbs(mzPend[k].vol - mzTr[i].vol) < 0.5 &&
            (mercado || MathAbs(mzPend[k].preco - mzTr[i].preco) < mzTickSize / 2.0) && Mae_OmLivre(mzPend[k].ticket, mzTr[i].papel)) mzTr[i].ticket = mzPend[k].ticket;
      for(int k = 0; k < nh && mzTr[i].ticket == 0 && mzTr[i].tipo >= 0; k++)
         if(mzHo[k].magic == mg && mzHo[k].setup_msc >= desde && mzHo[k].tipo == mzTr[i].tipo && MathAbs(mzHo[k].vol - mzTr[i].vol) < 0.5 &&
            (mercado || MathAbs(mzHo[k].preco - mzTr[i].preco) < mzTickSize / 2.0) && Mae_OmLivre(mzHo[k].ticket, mzTr[i].papel)) mzTr[i].ticket = mzHo[k].ticket;
      if(mzTr[i].ticket != 0) Mae_OmAdd(mzTr[i].ticket, mzTr[i].robo, mzTr[i].papel);
   }
   ulong tk = mzTr[i].ticket;
   int dl;
   if(tk != 0 && Mae_DealDaOrdem(tk, dl)) { prova = StringFormat("deal #%I64u @%.0f", mzDl[dl].ticket, mzDl[dl].preco); return D_EXEC; }
   if(tk != 0 && Mae_PendIdx(tk) >= 0) { prova = "listada nas pendentes"; return D_VIVA; }
   if(tk != 0)
   {
      int h = Mae_HoIdx(tk);
      if(h < 0)
      {
         SOrdemHist oh;
         if(mzCorr.LeOrdemHist(tk, oh)) { Mae_HoUpsert(oh); h = Mae_HoIdx(tk); }
      }
      if(h >= 0)
      {
         int st = mzHo[h].estado;
         if(st == ORDER_STATE_CANCELED || st == ORDER_STATE_REJECTED || st == ORDER_STATE_EXPIRED) { prova = "historico " + EnumToString((ENUM_ORDER_STATE)st); return D_NAO; }
      }
   }
   if(confiavel && mzCruzOk && idade > IDADE_PROVA)
   {
      prova = StringFormat("%d s sem aparecer nas pendentes, no historico ou em deal, cruzada fechando", idade);
      return D_NAO;
   }
   return D_SEM;
}

void Mae_LogDesfecho(const int i, const int d, const string prova)
{
   Log(d == D_SEM ? "AVISO" : "INFO", mzNome[mzTr[i].robo], "DESFECHO",
       StringFormat("com=%s %s ord=#%I64u apos %d s; prova: %s", mzTr[i].coment, Mae_DesfechoNome(d), mzTr[i].ticket,
                    (int)(Mae_Agora() - mzTr[i].hora), prova == "" ? "-" : prova));
}

// Exporta o estado do maestro para a memoria e grava (sec. 10.1).
void Mae_Exporta(void);

void Mae_GravaMemoria(const bool forcar)
{
   if(!mzIniciou || !mzMemCarregada || mzMemPasta == "") return;
   Mae_Exporta();
   bool ok = Mem_Grava(forcar);
   mzMemFalhou = !ok;
   Log_Cond("memoria", !ok, "ALERTA", "MAESTRO", "MEMORIA", "falha ao gravar estado.txt: so' a protecao (S) sai ate' gravar");
}

// Envia uma ordem do robo r: verificacao D1, registro de transito, OrderSend sincrono e UMA leitura do desfecho.
// Sem prova, a ordem fica no transito e o desfecho e' procurado nos ciclos seguintes (OnTradeTransaction e timer).
int Mae_Envia(const int r, const int papel, MqlTradeRequest &req, const string motivo, const bool s_da_entrada,
              const bool e_com_s_propria, int &desfecho, ulong &ticket)
{
   desfecho = D_SEM; ticket = 0;
   bool janela = (papel == P_K || papel == P_S) ? Mae_JanelaCall(Mae_Agora()) : Mae_JanelaOrdens(Mae_Agora());   // K e S tambem no call (M-3)
   if(!janela) { mzFichaMotivo = "fora da janela de ordens"; return FICHA_BLOQUEADA; }
   int lado = 0;
   if(papel != P_K) lado = Mae_LadoTipo((int)req.type);
   double preco = req.price;
   if(papel == P_E && req.action == TRADE_ACTION_DEAL) preco = (lado > 0) ? mzCorr.SimboloD(SYMBOL_ASK) : mzCorr.SimboloD(SYMBOL_BID);
   string porque;
   if(!Mae_EstadoFecha(r, papel, lado, preco, req.volume, req.order, s_da_entrada, e_com_s_propria, porque))
   {
      mzFichaMotivo = "estado aberto: " + porque;
      Log_Cond(StringFormat("estado.%d.%s", r, porque), true, "AVISO", mzNome[r], "ESTADO",
               StringFormat("BLOQUEADA %s (%s): %s", Mae_Letra(papel), motivo, porque));
      Mae_PedeReler();                                     // tenta explicar: releitura completa (no maximo a cada 10 s)
      return FICHA_BLOQUEADA;
   }
   Log_CondEncerraPrefixo(StringFormat("estado.%d.", r));
   // registro de transito ANTES do envio
   int seq = Mae_ProxSeq(r);
   string coment = StringFormat("MAE|%s|%s|%04d", mzNome[r], Mae_Letra(papel), seq);
   if(papel != P_K) req.comment = coment;
   req.magic = (ulong)mzMagic[r];
   req.symbol = _Symbol;
   int n = ArraySize(mzTr);
   ArrayResize(mzTr, n + 1);
   mzTr[n].robo = r; mzTr[n].papel = papel; mzTr[n].seq = seq; mzTr[n].coment = coment; mzTr[n].vol = req.volume;
   mzTr[n].lado = lado; mzTr[n].preco = preco; mzTr[n].hora = Mae_Agora(); mzTr[n].ticket = (papel == P_K) ? req.order : 0;
   mzTr[n].req_id = 0; mzTr[n].retcode = 0; mzTr[n].alertou = false; mzTr[n].tipo = (papel == P_K) ? -1 : (int)req.type;
   Mae_GravaMemoria(false);
   if(mzMemFalhou && papel == P_E)
   {
      Mae_TrRemove(Mae_TrIdx(r, seq, papel));
      mzFichaMotivo = "memoria nao gravada";
      return FICHA_BLOQUEADA;
   }
   int liq_antes = mzLiq;
   if(papel == P_K)
      Log("INFO", mzNome[r], "ORDEM", StringFormat("envio papel=K cancela=#%I64u com=%s motivo=%s", req.order, coment, motivo));
   else
      Log("INFO", mzNome[r], "ORDEM", StringFormat("envio papel=%s tipo=%s lado=%+d vol=%.0f preco=%.0f com=%s motivo=%s",
          Mae_Letra(papel), Mae_TipoNome((int)req.type), lado, req.volume, preco, coment, motivo));
   MqlTradeResult res;
   ZeroMemory(res);
   bool ok = mzCorr.Envia(req, res);
   int idx = Mae_TrIdx(r, seq, papel);
   if(Mae_RecusaDefinitiva(res.retcode))
   {
      Log("AVISO", mzNome[r], "ORDEM", StringFormat("retorno com=%s RECUSADA rc %u/%d req %u (%s)", coment, res.retcode, res.retcode_external, res.request_id, res.comment));
      if(papel == P_K && idx >= 0) { mzTr[idx].retcode = res.retcode; }
      else
      {
         if(idx >= 0) Mae_TrRemove(idx);
         mzFichaMotivo = StringFormat("recusada rc %u", res.retcode);
         desfecho = D_NAO;
         Mae_GravaMemoria(false);
         return FICHA_RECUSADA;
      }
   }
   if(idx >= 0)
   {
      if(papel != P_K) { mzTr[idx].ticket = res.order; Mae_OmAdd(res.order, r, papel); }
      mzTr[idx].req_id = res.request_id;
      mzTr[idx].retcode = res.retcode;
   }
   // uma leitura do desfecho, sem esperar
   string prova = "";
   int d = D_SEM;
   Leitura_Atualiza(false);
   idx = Mae_TrIdx(r, seq, papel);
   if(idx >= 0) d = Mae_Prova(idx, prova);
   if(idx >= 0) ticket = mzTr[idx].ticket;
   double exec = 0.0;
   int dl;
   if(d == D_EXEC && Mae_DealDaOrdem(ticket, dl)) exec = mzDl[dl].preco;
   Log("INFO", mzNome[r], "ORDEM", StringFormat("retorno com=%s ord=#%I64u deal=#%I64u req %u rc %u/%d envio=%s pedido %.0f exec %.0f; liquida %+d -> %+d",
       coment, ticket, res.deal, res.request_id, res.retcode, res.retcode_external, ok ? "ok" : "falso", preco, exec, liq_antes, mzLiq));
   if(idx >= 0)
   {
      Mae_LogDesfecho(idx, d, prova);
      if(d != D_SEM) Mae_TrRemove(idx);
   }
   if(d == D_EXEC && papel == P_C) mzUltCorrecao[r] = Mae_Agora();
   desfecho = d;
   Mae_GravaMemoria(false);
   if(d == D_NAO && papel != P_K) { mzFichaMotivo = "nao executada: " + prova; return FICHA_RECUSADA; }
   return FICHA_ENVIADA;
}

// Cancela uma ordem viva do robo (5.1). Devolve o desfecho (D_CANC, D_ANTES, D_NAO, D_SEM) ou -1 se bloqueado.
int Mae_Cancela(const int r, const ulong tk, const string motivo)
{
   if(!Mae_JanelaCall(Mae_Agora())) { mzFichaMotivo = "fora da janela de ordens"; return -1; }
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_REMOVE;
   req.order = tk;
   int d; ulong t;
   int ret = Mae_Envia(r, P_K, req, motivo, false, false, d, t);
   if(ret == FICHA_BLOQUEADA) return -1;
   Log(d == D_CANC ? "INFO" : "AVISO", mzNome[r], d == D_ANTES ? "EXECUTOU_ANTES" : "CANCELA",
       StringFormat("#%I64u (%s): %s", tk, motivo, Mae_DesfechoNome(d)));
   return d;
}

// Cancela todas as S vivas do robo (tickets lidos antes: a lista muda a cada cancelamento).
void Mae_CancelaStops(const int r, const string motivo)
{
   ulong tks[];
   int n = ArraySize(mzPend), m = 0;
   for(int i = 0; i < n; i++)
      if(mzPend[i].magic == mzMagic[r] && Mae_TipoStop(mzPend[i].tipo)) { ArrayResize(tks, m + 1); tks[m++] = mzPend[i].ticket; }
   for(int k = 0; k < m; k++)
      if(Mae_PendIdx(tks[k]) >= 0) Mae_Cancela(r, tks[k], motivo);
}

// Modifica o preco de uma S ou A viva (OrderModify; nunca cancelar e recriar).
int Mae_Modifica(const int r, const int papel, const ulong tk, const double preco, const string motivo)
{
   if(!(papel == P_S ? Mae_JanelaCall(Mae_Agora()) : Mae_JanelaOrdens(Mae_Agora()))) { mzFichaMotivo = "fora da janela de ordens"; return FICHA_BLOQUEADA; }
   string porque;
   int i = Mae_PendIdx(tk);
   int lado = (i >= 0) ? Mae_LadoTipo(mzPend[i].tipo) : 0;
   // mover a S e' protecao: so' a trava, a conta e a lista de ordens a barram; o A passa pelos itens 1-3 do D1
   Leitura_Atualiza(false);
   porque = "";
   if(mzTravaPerdida && papel != P_S) porque = "a trava passou a outro grafico";
   else if(mzSemOrdens) porque = "conta nao NETTING";
   else if(!mzPendOk || Mae_PendIdx(tk) < 0) porque = "ordem nao esta' viva";
   else if(papel == P_A && !Mae_LeituraConfiavel()) porque = "leitura nao confiavel";
   else if(papel == P_A && !mzCruzOk) porque = "verificacao cruzada nao fecha";
   else if(papel == P_A && Mae_TemTransito(r)) porque = "robo tem ordem sem desfecho";
   else if(papel == P_A && Mae_Autoneg(r, lado, preco)) porque = "autonegociacao";
   if(porque != "")
   {
      mzFichaMotivo = "estado aberto: " + porque;
      Log_Cond(StringFormat("estado.%d.%s", r, porque), true, "AVISO", mzNome[r], "ESTADO", StringFormat("BLOQUEADA mover %s (%s): %s", Mae_Letra(papel), motivo, porque));
      return FICHA_BLOQUEADA;
   }
   MqlTradeRequest req;
   MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action = TRADE_ACTION_MODIFY;
   req.order = tk;
   req.symbol = _Symbol;
   req.price = Mae_NoTick(preco);
   req.sl = 0.0; req.tp = 0.0;
   req.type_time = ORDER_TIME_DAY;
   req.expiration = 0;
   double antes = mzPend[Mae_PendIdx(tk)].preco;
   bool ok = mzCorr.Envia(req, res);
   bool aceito = (res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_PLACED || res.retcode == TRADE_RETCODE_NO_CHANGES);
   Log(aceito ? "INFO" : "AVISO", mzNome[r], "ORDEM", StringFormat("modifica %s ord=#%I64u de %.0f para %.0f rc %u/%d envio=%s (%s)",
       Mae_Letra(papel), tk, antes, req.price, res.retcode, res.retcode_external, ok ? "ok" : "falso", motivo));
   Leitura_Atualiza(false);
   if(!aceito) { mzFichaMotivo = StringFormat("modificacao recusada rc %u", res.retcode); return FICHA_RECUSADA; }
   Log("INFO", mzNome[r], papel == P_S ? "STOP" : "ALVO", StringFormat("movido %.0f -> %.0f (%s)", antes, req.price, motivo));
   return FICHA_ENVIADA;
}

// Envia uma S (stop pendente, DAY) do lado que protege lp, com o volume dado.
int Mae_EnviaS(const int r, const int lp, const double nivel, const int vol, const string motivo, const bool da_entrada, int &desfecho)
{
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_PENDING;
   req.type = (lp > 0) ? ORDER_TYPE_SELL_STOP : ORDER_TYPE_BUY_STOP;
   req.volume = (double)(vol > 0 ? vol : 1);
   req.price = Mae_NoTick(nivel);
   req.type_filling = ORDER_FILLING_RETURN;
   req.type_time = ORDER_TIME_DAY;
   req.deviation = 0;
   ulong tk;
   int ret = Mae_Envia(r, P_S, req, motivo, da_entrada, false, desfecho, tk);
   if(ret == FICHA_ENVIADA && (desfecho == D_VIVA || desfecho == D_EXEC))
      Log("INFO", mzNome[r], "STOP", StringFormat("criado %s %.0f @%.0f ord #%I64u (%s)", lp > 0 ? "sell_stop" : "buy_stop", req.volume, req.price, tk, motivo));
   return ret;
}

void Mae_Recusa(const int r, const string oque, const int cat)
{
   datetime agora = Mae_Agora();
   mzRecProx[r][cat] = agora + RETENTA;
   if(StringFind(mzFichaMotivo, StringFormat("rc %u", TRADE_RETCODE_MARKET_CLOSED)) >= 0)
   {
      // mercado fechado (feriado da B3 ou fora do pregao): a corretora decide; AVISO por objeto, sem escalar (M-4)
      Log_Cond(StringFormat("fechado.%d", r), true, "AVISO", mzNome[r], "ORDEM", "mercado fechado (feriado?): " + oque + " retentada a cada 5 s");
      return;
   }
   Log_Cond(StringFormat("fechado.%d", r), false, "", mzNome[r], "ORDEM", "");
   mzRecN[r][cat]++;
   if(mzRecN[r][cat] == 5 || (mzRecN[r][cat] > 5 && agora - mzRecAl[r][cat] >= 300))
   {
      mzRecAl[r][cat] = agora;
      Log("ALERTA", mzNome[r], "ORDEM", StringFormat("%d recusas seguidas: %s (%s)", mzRecN[r][cat], oque, mzFichaMotivo));
   }
}

//+------------------------------------------------------------------+
//| Saida a mercado (sec. 5.2)                                           |
//+------------------------------------------------------------------+
// papel X (saida) ou C (correcao). vol = contratos (0 = |ficha|). cancela_a: o A sai antes (5.2 passo 1).
// cancela_s: depois da saida executada, as S do robo sao canceladas (5.2 passo 4).
int Mae_Saida(const int r, const int papel, const string motivo, const int vol, const bool cancela_a, const bool cancela_s)
{
   datetime agora = Mae_Agora();
   if(!Mae_Continuo(agora)) { mzFichaMotivo = "fora do continuo"; return FICHA_BLOQUEADA; }
   Leitura_Atualiza(false);
   SRoboEstado e; Mae_Estado(r, e);
   if(e.f == 0) { mzFichaMotivo = "sem ficha"; return FICHA_BLOQUEADA; }
   // 1. cancela a A (a S fica); sem confirmacao, a saida espera
   if(cancela_a && e.iA >= 0)
   {
      int d = Mae_Cancela(r, mzPend[e.iA].ticket, "saida: cancela o alvo antes");
      if(d == D_ANTES) { Leitura_Atualiza(false); mzFichaMotivo = "alvo executou antes"; return FICHA_BLOQUEADA; }
      if(d != D_CANC) { mzFichaMotivo = "alvo sem cancelamento confirmado"; return FICHA_BLOQUEADA; }
      Mae_Estado(r, e);
      if(e.f == 0) { mzFichaMotivo = "sem ficha"; return FICHA_BLOQUEADA; }
   }
   // 3. mercado, lado oposto
   int lado = -Mae_Sinal(e.f);
   int v = (vol > 0) ? vol : Mae_Abs(e.f);
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_DEAL;
   req.type = (lado > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.volume = (double)v;
   req.price = (lado > 0) ? mzCorr.SimboloD(SYMBOL_ASK) : mzCorr.SimboloD(SYMBOL_BID);
   req.type_filling = mzFillMercado;
   req.deviation = 0;
   Log("INFO", mzNome[r], papel == P_C ? "CORRECAO" : "SAIDA", StringFormat("%s %d a mercado (%s); ficha %+d", lado > 0 ? "compra" : "venda", v, motivo, e.f));
   int d; ulong tk;
   int ret = Mae_Envia(r, papel, req, motivo, false, false, d, tk);
   if(ret != FICHA_ENVIADA) return ret;
   if(d == D_EXEC)
   {
      mzRecN[r][RC_X] = 0;
      if(cancela_s)
      {
         Leitura_Atualiza(false);
         Mae_Estado(r, e);
         if(e.f == 0 && e.dirE == 0) Mae_CancelaStops(r, "saida executada: cancela a S");
      }
   }
   return FICHA_ENVIADA;   // executada; ou sem desfecho (a S fica; o desfecho vem nos ciclos seguintes)
}

//+------------------------------------------------------------------+
//| API dos modulos (sec. 3.3)                                           |
//+------------------------------------------------------------------+
// Checagens comuns a toda entrada. momento = instante da decisao do robo (decisao anterior a' partida = perdida).
bool Mae_PodeEntrar(const int r, const datetime momento, const string motivo)
{
   datetime agora = Mae_Agora();
   if(!mzPronto || mzProtegendo) { mzFichaMotivo = "maestro nao esta' pronto"; return false; }
   if(!mzAtivo[r] || mzFalhou[r]) { mzFichaMotivo = "robo desligado"; return false; }
   if(mzBloq) { mzFichaMotivo = "bloqueio de entradas"; Log("AVISO", mzNome[r], "BLOQUEIO", "entrada nao enviada (" + motivo + "): bloqueio de entradas"); return false; }
   if(!Mae_JanelaTick(agora) || agora >= Mae_Zr(r, agora)) { mzFichaMotivo = "fora do horario de entrada"; return false; }
   if(momento > 0 && momento < mzProntoEm)
   {
      mzFichaMotivo = "decisao perdida";
      Log("AVISO", mzNome[r], "DECISAO PERDIDA", StringFormat("decisao de %s anterior a' partida (%s): %s", TimeToString(momento, TIME_DATE | TIME_SECONDS), TimeToString(mzProntoEm, TIME_SECONDS), motivo));
      return false;
   }
   Leitura_Atualiza(false);
   string porque = "";
   if(mzTravaPerdida) porque = "a trava passou a outro grafico";
   else if(mzSemOrdens) porque = "conta nao NETTING";
   else if(!Mae_LeituraConfiavel()) porque = "leitura nao confiavel";
   else if(!mzCruzOk) porque = "verificacao cruzada nao fecha";
   else if(mzMemFalhou) porque = "memoria nao gravada";
   else if(mzIndet[r]) porque = "deal do robo com ordem ainda nao identificada";
   if(porque != "")
   {
      mzFichaMotivo = "estado aberto: " + porque;
      Log_Cond(StringFormat("estado.%d.%s", r, porque), true, "AVISO", mzNome[r], "ESTADO", StringFormat("BLOQUEADA entrada (%s): %s", motivo, porque));
      Mae_PedeReler();
      return false;
   }
   SRoboEstado e; Mae_Estado(r, e);
   if(e.f != 0 || Mae_VivasNaoStop(r) > 0 || Mae_TemTransitoNaoK(r) || mzETicket[r] != 0)
   {
      mzFichaMotivo = "segunda entrada";
      Log("AVISO", mzNome[r], "SEGUNDA_ENTRADA", StringFormat("BLOQUEADA segunda entrada (%s): ficha %+d, %d ordens vivas", motivo, e.f, e.nVivas));
      return false;
   }
   return true;
}

// Entrada com a S ANTES (5.3, C-1): so' com a S viva a E sai. E recusada ou provada nao executada -> cancela a S.
int Mae_Entra(const int r, const int lado, const double stop, MqlTradeRequest &req, const string motivo, const bool fallback_day = false)
{
   double pe = (req.action == TRADE_ACTION_DEAL) ? ((lado > 0) ? mzCorr.SimboloD(SYMBOL_ASK) : mzCorr.SimboloD(SYMBOL_BID)) : req.price;
   if(Mae_Autoneg(r, lado, pe))
   {
      mzFichaMotivo = "estado aberto: autonegociacao";
      Log("AVISO", mzNome[r], "AUTONEG", StringFormat("E %s @%.0f cruzaria com limite propria viva de outro robo: nao enviada", lado > 0 ? "compra" : "venda", pe));
      return FICHA_BLOQUEADA;
   }
   mzStopNivel[r] = Mae_NoTick(stop);
   mzAlvoNivel[r] = 0.0;
   int ds;
   uint t0 = GetTickCount();
   int rs = Mae_EnviaS(r, lado, mzStopNivel[r], 1, "S antes da E", true, ds);
   if(rs != FICHA_ENVIADA || ds != D_VIVA)
   {
      if(rs == FICHA_ENVIADA && ds == D_SEM) mzFichaMotivo = "S sem desfecho: E nao enviada";
      else if(rs == FICHA_ENVIADA) mzFichaMotivo = "S nao ficou viva: E nao enviada";
      SRoboEstado e0; Mae_Estado(r, e0);
      if(e0.f == 0 && e0.iS < 0 && !Mae_TemTransito(r)) mzStopNivel[r] = 0.0;
      return (rs == FICHA_ENVIADA) ? FICHA_BLOQUEADA : rs;
   }
   Log("INFO", mzNome[r], "STOP", StringFormat("S viva antes da E: %u ms", GetTickCount() - t0));
   int d; ulong tk;
   int ret = Mae_Envia(r, P_E, req, motivo, false, true, d, tk);
   if(ret == FICHA_RECUSADA && fallback_day && req.type_time == ORDER_TIME_SPECIFIED)
   {
      // validade com horario recusada: mesma S, E com validade do dia (o robo cancela no prazo dele) (M-7)
      Log("AVISO", mzNome[r], "ORDEM", "E com validade SPECIFIED recusada: tentando validade do dia, com a mesma S");
      req.type_time = ORDER_TIME_DAY; req.expiration = 0; req.comment = "";
      ret = Mae_Envia(r, P_E, req, motivo + " (DAY)", false, true, d, tk);
   }
   if(ret != FICHA_ENVIADA || d == D_NAO)
   {
      // E recusada, barrada ou provada nao executada -> cancela a S (se ainda nao houver ficha)
      SRoboEstado e; Mae_Estado(r, e);
      if(e.f == 0 && e.dirE == 0) Mae_CancelaStops(r, "E nao saiu: cancela a S");
      Mae_Estado(r, e);
      if(e.f == 0 && e.iS < 0 && !Mae_TemTransito(r)) mzStopNivel[r] = 0.0;
      return (ret == FICHA_ENVIADA) ? FICHA_RECUSADA : ret;
   }
   if(d == D_VIVA) { mzETicket[r] = tk; mzEDir[r] = lado; mzEVivaDesde[r] = Mae_Agora(); mzECancelPedido[r] = false; mzESumiuDesde[r] = 0; }
   return FICHA_ENVIADA;   // viva, executada, ou sem desfecho (a S protege; o desfecho vem nos ciclos seguintes)
}

int Ficha_EntraLimite(const int r, const int lado, const double preco, const double stop, const ENUM_ORDER_TYPE_TIME validade,
                      const datetime expira, const datetime momento, const string motivo)
{
   mzFichaMotivo = "";
   if(!Mae_PodeEntrar(r, momento, motivo)) return FICHA_BLOQUEADA;
   if(stop <= 0.0 || preco <= 0.0) { mzFichaMotivo = "preco ou stop invalido"; Log("ERRO", mzNome[r], "SINAL", "entrada sem preco/stop valido"); return FICHA_BLOQUEADA; }
   Log("INFO", mzNome[r], "SINAL", StringFormat("%s limite @%.0f stop %.0f (%s)", lado > 0 ? "compra" : "venda", preco, stop, motivo));
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_PENDING;
   req.type = (lado > 0) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
   req.volume = 1.0;
   req.price = Mae_NoTick(preco);
   req.type_filling = ORDER_FILLING_RETURN;
   req.type_time = validade;
   req.expiration = (validade == ORDER_TIME_SPECIFIED) ? expira : 0;
   req.deviation = 0;
   return Mae_Entra(r, lado, stop, req, motivo, validade == ORDER_TIME_SPECIFIED);
}

// Entrada a mercado (C1).
int Ficha_EntraMercado(const int r, const int lado, const double stop, const datetime momento, const string motivo)
{
   mzFichaMotivo = "";
   if(!Mae_PodeEntrar(r, momento, motivo)) return FICHA_BLOQUEADA;
   if(stop <= 0.0) { mzFichaMotivo = "stop invalido"; Log("ERRO", mzNome[r], "SINAL", "entrada a mercado sem stop valido"); return FICHA_BLOQUEADA; }
   Log("INFO", mzNome[r], "SINAL", StringFormat("%s a mercado, stop %.0f (%s)", lado > 0 ? "compra" : "venda", stop, motivo));
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_DEAL;
   req.type = (lado > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.volume = 1.0;
   req.price = (lado > 0) ? mzCorr.SimboloD(SYMBOL_ASK) : mzCorr.SimboloD(SYMBOL_BID);
   req.type_filling = mzFillMercado;
   req.deviation = 0;
   return Mae_Entra(r, lado, stop, req, motivo);
}

int Ficha_Fecha(const int r, const string motivo)
{
   mzFichaMotivo = "";
   Leitura_Atualiza(false);
   if(!Ficha_Tem(r)) { mzFichaMotivo = "sem ficha"; return FICHA_BLOQUEADA; }
   if(mzSaidaPedida[r] != "" && mzSaidaFid[r] == mzFid[r]) { mzFichaMotivo = "saida ja' pedida (o maestro envia)"; return FICHA_ENVIADA; }
   int ret = Mae_Saida(r, P_X, motivo, 0, true, true);
   if(ret == FICHA_BLOQUEADA && Ficha_Tem(r) && Mae_Continuo(Mae_Agora()))
   {
      // estado aberto momentaneo: o pedido nao se perde; o maestro envia assim que o estado fechar (A-2)
      mzSaidaPedida[r] = motivo; mzSaidaFid[r] = mzFid[r];
      Log("INFO", mzNome[r], "SAIDA", StringFormat("saida por regra (%s) adiada: %s; o maestro envia assim que o estado fechar", motivo, mzFichaMotivo));
      Mae_GravaMemoria(false);
      return FICHA_ENVIADA;
   }
   return ret;
}

int Ficha_DefineStop(const int r, const double nivel, const string motivo)
{
   mzFichaMotivo = "";
   if(nivel <= 0.0) { mzFichaMotivo = "nivel 0"; Log("ERRO", mzNome[r], "STOP", "nivel 0 pedido pelo modulo ignorado (" + motivo + ")"); return FICHA_BLOQUEADA; }
   double n = Mae_NoTick(nivel);
   mzStopNivel[r] = n;
   Mae_GravaMemoria(false);
   Leitura_Atualiza(false);
   SRoboEstado e; Mae_Estado(r, e);
   if(e.iS >= 0)
   {
      if(MathAbs(mzPend[e.iS].preco - n) < mzTickSize / 2.0) return FICHA_ENVIADA;
      int rm = Mae_Modifica(r, P_S, mzPend[e.iS].ticket, n, motivo);
      if(rm == FICHA_RECUSADA) Mae_Recusa(r, "mover S", RC_S);
      return rm;
   }
   if(e.lp == 0 || e.trans) { mzFichaMotivo = "sem ficha nem entrada"; return FICHA_BLOQUEADA; }
   int d;
   int ret = Mae_EnviaS(r, e.lp, n, e.need - e.volS, motivo, false, d);
   if(ret == FICHA_ENVIADA && d == D_NAO) return FICHA_RECUSADA;
   return ret;
}

int Ficha_DefineAlvo(const int r, const double nivel, const string motivo)
{
   mzFichaMotivo = "";
   if(nivel <= 0.0) { mzFichaMotivo = "nivel 0"; Log("ERRO", mzNome[r], "ALVO", "nivel 0 pedido pelo modulo ignorado (" + motivo + ")"); return FICHA_BLOQUEADA; }
   Leitura_Atualiza(false);
   if(!Ficha_Tem(r)) { mzFichaMotivo = "A sem ficha"; return FICHA_BLOQUEADA; }
   double n = Mae_NoTick(nivel);
   mzAlvoNivel[r] = n;
   if(!Mae_Continuo(Mae_Agora()) || Mae_Noite(r)) { mzFichaMotivo = "A so' no continuo"; return FICHA_BLOQUEADA; }
   Mae_GravaMemoria(false);
   SRoboEstado e; Mae_Estado(r, e);
   if(e.iA >= 0)
   {
      if(MathAbs(mzPend[e.iA].preco - n) < mzTickSize / 2.0) return FICHA_ENVIADA;
      int rm = Mae_Modifica(r, P_A, mzPend[e.iA].ticket, n, motivo);
      if(rm == FICHA_RECUSADA) Mae_Recusa(r, "mover A", RC_A);
      return rm;
   }
   int lado = -Mae_Sinal(e.f);
   MqlTradeRequest req;
   ZeroMemory(req);
   req.action = TRADE_ACTION_PENDING;
   req.type = (lado > 0) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
   req.volume = 1.0;
   req.price = n;
   req.type_filling = ORDER_FILLING_RETURN;
   req.type_time = ORDER_TIME_DAY;
   req.deviation = 0;
   int d; ulong tk;
   int ret = Mae_Envia(r, P_A, req, motivo, false, false, d, tk);
   if(ret == FICHA_ENVIADA && (d == D_VIVA || d == D_EXEC)) Log("INFO", mzNome[r], "ALVO", StringFormat("criado @%.0f ord #%I64u (%s)", n, tk, motivo));
   return ret;
}

// Cancela a E (papel P_E) ou o A (P_A) do robo a pedido do modulo. ENVIADA so' com o cancelamento CONFIRMADO;
// sem confirmacao o maestro refaz o cancelamento da E a cada RETENTA ate' o historico mostrar o desfecho (A-2, item 1.8).
int Ficha_Cancela(const int r, const int papel, const string motivo)
{
   mzFichaMotivo = "";
   Leitura_Atualiza(false);
   SRoboEstado e; Mae_Estado(r, e);
   int i = (papel == P_E) ? e.iE : (papel == P_A ? e.iA : -1);
   if(i < 0) { mzFichaMotivo = "nada a cancelar"; return FICHA_BLOQUEADA; }
   ulong tk = mzPend[i].ticket;
   if(papel == P_E)
   {
      if(Mae_TemTransitoPapel(r, P_K) || (mzECancelPedido[r] && Mae_Agora() < mzRecProx[r][RC_K]))
      {
         mzFichaMotivo = "cancelamento da E em curso";
         mzECancelPedido[r] = true;
         return FICHA_BLOQUEADA;
      }
      mzECancelPedido[r] = true;
   }
   int d = Mae_Cancela(r, tk, motivo);
   if(d == D_ANTES)
   {
      Leitura_Atualiza(false);
      Mae_Evento(r, EV_EXECUTOU_ANTES);
      mzFichaMotivo = "executou antes do cancelamento";
      return FICHA_BLOQUEADA;
   }
   if(d != D_CANC)
   {
      if(papel == P_E) Mae_Recusa(r, "cancelar a E", RC_K);
      mzFichaMotivo = "cancelamento sem confirmacao (o maestro refaz)";
      return FICHA_BLOQUEADA;
   }
   if(papel == P_E)
   {
      // so' entao cancela a S dela, se a E nao encheu nesse meio-tempo (5.1)
      mzETicket[r] = 0;
      mzECancelPedido[r] = false;
      Leitura_Atualiza(false);
      Mae_Estado(r, e);
      if(e.f == 0 && e.dirE == 0) Mae_CancelaStops(r, "E cancelada e confirmada: cancela a S");
   }
   if(papel == P_A) mzAlvoNivel[r] = 0.0;
   return FICHA_ENVIADA;
}

//+------------------------------------------------------------------+
//| Reconciliacao (sec. 6)                                               |
//+------------------------------------------------------------------+
// Loga os deals novos (ENTROU/SAIU/EXTERNA/AJUSTE) e as absorcoes novas (bloqueio, sec. 7.1).
void Mae_NovosEventos(void)
{
   int n = ArraySize(mzDl);
   for(int i = 0; i < n; i++)
   {
      if(!mzDl[i].novo || mzDl[i].pendente) continue;      // deal sem magic na carencia: loga quando resolver
      mzDl[i].novo = false;
      if(Mae_Logado(mzDl[i].ticket)) continue;
      int nl = ArraySize(mzLogTk);
      if(nl >= 2000) { ArrayRemove(mzLogTk, 0, 1000); nl = ArraySize(mzLogTk); }
      ArrayResize(mzLogTk, nl + 1); mzLogTk[nl] = mzDl[i].ticket;
      if(mzDl[i].t > mzUltDealMsc || (mzDl[i].t == mzUltDealMsc && mzDl[i].ticket > mzUltDealTk)) { mzUltDealMsc = mzDl[i].t; mzUltDealTk = mzDl[i].ticket; }
      datetime td = (datetime)(mzDl[i].t / 1000);
      bool fora = !mzPronto && mzHeartbeatMem > 0 && td > mzHeartbeatMem && td < mzPartidaEm;
      string quando = StringFormat("%s%s", Log_HmsMsc(mzDl[i].t), fora ? " (EA fora)" : "");
      if(mzDl[i].ajuste)
      {
         Log("ALERTA", "MAESTRO", "AJUSTE", StringFormat("deal externo #%I64u %s %d @%.0f em %s fora do continuo, par fecha/reabre: tratado como ajuste, sem efeito nas fichas (P14)",
             mzDl[i].ticket, mzDl[i].tipo == DEAL_TYPE_BUY ? "compra" : "venda", mzDl[i].vol, mzDl[i].preco, quando));
         continue;
      }
      if(mzDl[i].tipo != DEAL_TYPE_BUY && mzDl[i].tipo != DEAL_TYPE_SELL)
      {
         Log("INFO", "MAESTRO", "AJUSTE", StringFormat("deal #%I64u tipo %d valor %.2f em %s (nao entra no volume)", mzDl[i].ticket, mzDl[i].tipo, mzDl[i].lucro, quando));
         continue;
      }
      int r = mzDl[i].robo;
      if(r >= 0)
      {
         bool entrou = Mae_Abs(mzDl[i].f_depois) > Mae_Abs(mzDl[i].f_antes);
         string lado = mzDl[i].tipo == DEAL_TYPE_BUY ? "compra" : "venda";
         Log(fora ? "AVISO" : "INFO", mzNome[r], entrou ? "ENTROU" : "SAIU",
             StringFormat("%s %d papel %s; pedido %.0f exec %.0f deal #%I64u ord #%I64u em %s; ficha %+d -> %+d; liquida %+d -> %+d",
                          lado, mzDl[i].vol, Mae_Letra(mzDl[i].papel), mzDl[i].ord_preco, mzDl[i].preco, mzDl[i].ticket, mzDl[i].ordem, quando,
                          mzDl[i].f_antes, mzDl[i].f_depois, mzDl[i].liq_antes, mzDl[i].liq_depois));
         if(fora) Log("ALERTA", "MAESTRO", "RECUPERA", StringFormat("%s: %s %d @%.0f em %s com o EA fora", mzNome[r], lado, mzDl[i].vol, mzDl[i].preco, quando));
      }
      else
         Log(Mae_Continuo(td) ? "AVISO" : "ALERTA", "MAESTRO", "EXTERNA", StringFormat("deal externo magic %I64d %s %d @%.0f deal #%I64u em %s; liquida %+d -> %+d; externa %+d",
             mzDl[i].magic, mzDl[i].tipo == DEAL_TYPE_BUY ? "compra" : "venda", mzDl[i].vol, mzDl[i].preco, mzDl[i].ticket, quando,
             mzDl[i].liq_antes, mzDl[i].liq_depois, mzExt));
   }
   // absorcoes novas: uma linha ABSORVIDA por ficha absorvida; um bloqueio por deal externo nao reconhecido
   int na = ArraySize(mzAbs);
   int nv0 = ArraySize(mzAbsVistas);
   for(int i = 0; i < na; i++)
   {
      bool vista = false;
      for(int k = 0; k < nv0; k++) if(mzAbsVistas[k] == mzAbs[i].deal) vista = true;
      if(vista) continue;
      if(Mae_Reconhecido(mzAbs[i].deal))                    // ja' reconhecida pelo dono: nao reloga nem rebloqueia (B-3)
      {
         bool ja0 = false;
         int nv1 = ArraySize(mzAbsVistas);
         for(int k = 0; k < nv1; k++) if(mzAbsVistas[k] == mzAbs[i].deal) ja0 = true;
         if(!ja0) { ArrayResize(mzAbsVistas, nv1 + 1); mzAbsVistas[nv1] = mzAbs[i].deal; }
         continue;
      }
      Log("ALERTA", mzNome[mzAbs[i].robo], "ABSORVIDA", StringFormat("zeragem manual: %d contrato(s) absorvido(s) a %.0f pelo deal externo #%I64u (%s)",
          mzAbs[i].vol, mzAbs[i].preco, mzAbs[i].deal, Log_HmsMsc(mzAbs[i].t)));
      int nv = ArraySize(mzAbsVistas);
      bool ja = false;
      for(int k = nv0; k < nv; k++) if(mzAbsVistas[k] == mzAbs[i].deal) ja = true;
      if(ja) continue;
      ArrayResize(mzAbsVistas, nv + 1);
      mzAbsVistas[nv] = mzAbs[i].deal;
      if(!Mae_Reconhecido(mzAbs[i].deal)) Mae_Bloqueia(StringFormat("zeragem manual (deal #%I64u)", mzAbs[i].deal));
   }
}

// Resolve o transito: desfechos por prova, ALERTA aos 30 s, bloqueio aos 10 min (sec. 4.4).
void Transito_Resolve(void)
{
   datetime agora = Mae_Agora();
   for(int i = ArraySize(mzTr) - 1; i >= 0; i--)
   {
      if(i >= ArraySize(mzTr)) continue;
      string prova;
      int d = Mae_Prova(i, prova);
      int r = mzTr[i].robo;
      if(d != D_SEM)
      {
         Mae_LogDesfecho(i, d, prova);
         if(mzTr[i].papel == P_E && d == D_VIVA)
         {
            mzETicket[r] = mzTr[i].ticket; mzEDir[r] = mzTr[i].lado; mzEVivaDesde[r] = agora; mzECancelPedido[r] = false; mzESumiuDesde[r] = 0;
         }
         if(mzTr[i].papel == P_E && d == D_NAO)
         {
            Log("INFO", mzNome[r], "CANCELA", "E sem desfecho provada nao executada: modulo avisado (nao rearma); a S vira orfa");
            Mae_Evento(r, EV_ENTRADA_CANCELADA);
         }
         int om = Mae_OmIdx(mzTr[i].ticket);
         bool era_e = mzTr[i].papel == P_K && (mzTr[i].ticket == mzETicket[r] || (om >= 0 && mzOmPapel[om] == P_E));
         if(era_e && d == D_ANTES) Mae_Evento(r, EV_EXECUTOU_ANTES);      // so' a E do robo (M-1)
         if(era_e && d == D_CANC)
         {
            if(!mzECancelPedido[r]) Mae_Evento(r, EV_ENTRADA_CANCELADA);
            mzETicket[r] = 0;
            mzECancelPedido[r] = false;
         }
         if(mzTr[i].papel == P_C && d == D_EXEC) mzUltCorrecao[r] = agora;
         Log_Cond(StringFormat("semdesfecho.%s", mzTr[i].coment), false, "", mzNome[r], "DESFECHO", "");
         Mae_TrRemove(i);
         continue;
      }
      int idade = (int)(agora - mzTr[i].hora);
      if(idade >= ALERTA_SEM_DESFECHO)
         Log_Cond(StringFormat("semdesfecho.%s", mzTr[i].coment), true, "ALERTA", mzNome[r], "DESFECHO",
                  StringFormat("%s ord #%I64u sem desfecho ha' %d s: envios do robo esperam a prova; a S segue (e e' recriada se faltar)", mzTr[i].coment, mzTr[i].ticket, idade));
      if(idade >= PRAZO_SEM_DESFECHO && !mzTr[i].alertou)
      {
         mzTr[i].alertou = true;
         Mae_Bloqueia(StringFormat("ordem sem desfecho ha' 10 min (%s)", mzTr[i].coment));
      }
   }
}

// Acompanha a E viva de cada robo; E que some sem deal avisa o modulo (ENTRADA_CANCELADA).
void Mae_EControle(const int r)
{
   SRoboEstado e; Mae_Estado(r, e);
   datetime agora = Mae_Agora();
   if(e.iE >= 0)
   {
      if(mzPend[e.iE].ticket != mzETicket[r])
      {
         mzETicket[r] = mzPend[e.iE].ticket; mzEDir[r] = Mae_LadoTipo(mzPend[e.iE].tipo);
         mzEVivaDesde[r] = agora; mzECancelPedido[r] = false;
      }
      mzESumiuDesde[r] = 0;
      return;
   }
   if(mzETicket[r] == 0) return;
   ulong tk = mzETicket[r];
   if(Mae_PendIdx(tk) >= 0) return;                         // segue viva (como A? nao: papel muda so' com ficha)
   int dl;
   if(Mae_DealDaOrdem(tk, dl)) { mzETicket[r] = 0; mzESumiuDesde[r] = 0; return; }   // encheu
   int h = Mae_HoIdx(tk);
   if(h < 0) { SOrdemHist oh; if(mzCorr.LeOrdemHist(tk, oh)) { Mae_HoUpsert(oh); h = Mae_HoIdx(tk); } }
   bool sumiu = false;
   string como = "";
   if(h >= 0)
   {
      int st = mzHo[h].estado;
      if(st == ORDER_STATE_CANCELED || st == ORDER_STATE_EXPIRED || st == ORDER_STATE_REJECTED) { sumiu = true; como = EnumToString((ENUM_ORDER_STATE)st); }
      if(st == ORDER_STATE_FILLED || st == ORDER_STATE_PARTIAL) return;   // deal ainda nao chegou: segue tratada como viva
   }
   if(!sumiu)
   {
      if(mzESumiuDesde[r] == 0) mzESumiuDesde[r] = agora;
      if(Mae_LeituraConfiavel() && mzCruzOk && agora - mzESumiuDesde[r] > IDADE_PROVA) { sumiu = true; como = "ausente das pendentes e do historico ha' 30 s"; }
   }
   if(!sumiu) return;
   if(!mzECancelPedido[r])
   {
      Log("AVISO", mzNome[r], "CANCELA", StringFormat("E #%I64u sumiu sem deal (%s): modulo avisado (nao rearma)", tk, como));
      Mae_Evento(r, EV_ENTRADA_CANCELADA);
   }
   mzETicket[r] = 0; mzEDir[r] = 0; mzESumiuDesde[r] = 0; mzECancelPedido[r] = false;
}

// Nivel para (re)criar a S de uma ficha: memoria -> regra do robo -> emergencia (5.3, 10.2 passo 8).
double Mae_NivelStopFicha(const int r, const SRoboEstado &e, string &fonte)
{
   bool trocada = Mae_Trocada(r, e);                                // trocada: a regra do robo nao define -> emergencia
   if(!trocada && mzStopNivel[r] > 0.0) { fonte = "memoria"; return mzStopNivel[r]; }
   if(!trocada && Ficha_Tem(r))
   {
      double n = Robo_StopRegra(r);
      if(n > 0.0) { fonte = "regra do robo"; return Mae_NoTick(n); }
   }
   fonte = "emergencia";
   return Mae_NoTick(mzPm[r] - Mae_Sinal(e.f) * STOP_EMERGENCIA_PTS);
}

// O nivel de stop ja' foi atravessado pelo preco? (lado protegido lp)
bool Mae_NivelAtravessado(const int lp, const double nivel)
{
   double piso = Ficha_PisoStop();
   if(lp > 0)
   {
      double bid = mzCorr.SimboloD(SYMBOL_BID);
      return bid > 0.0 && bid <= nivel + piso;
   }
   double ask = mzCorr.SimboloD(SYMBOL_ASK);
   return ask > 0.0 && ask >= nivel - piso;
}

// Fase 1: orfas, cancelamentos de E, saidas e correcoes (sec. 2, sec. 5, sec. 7.2, sec. 8, sec. 9.3).
void Mae_Fase1(const int r, const bool so_orfas)
{
   if(Mae_TemTransito(r) || (mzIndet[r] && !Mae_IndetVelha(r)) || !mzPendOk || mzSemOrdens || mzTravaPerdida) return;
   datetime agora = Mae_Agora();
   if(!Mae_JanelaCall(agora)) return;                     // orfas e E canceladas ate' o call (M-3); saidas so' no continuo
   SRoboEstado e; Mae_Estado(r, e);
   // orfas (mais de 5 s de vida, sem ordem do robo sem desfecho)
   for(int k = 0; k < e.nOrfas; k++)
   {
      int i = e.orfas[k];
      if(i >= ArraySize(mzPend)) continue;
      // mais de 5 s de vida; ou irma de uma ficha que um deal zerou depois de ela nascer (OCO imediato, 5.4)
      bool oco = (e.f == 0 && mzZeroMsc[r] > 0 && mzPend[i].setup_msc < mzZeroMsc[r]);
      if(Mae_AgoraMsc() - mzPend[i].setup_msc < 5000 && !oco) continue;
      ulong tk_o = mzPend[i].ticket;
      // reconfere com a lista relida: a orfa tem de continuar orfa (lista parcial nao decide, M-2)
      Leitura_Atualiza(false);
      if(!mzPendOk || Mae_TemTransito(r)) return;
      Mae_Estado(r, e);
      bool segue = false;
      for(int q = 0; q < e.nOrfas; q++) if(mzPend[e.orfas[q]].ticket == tk_o) { segue = true; i = e.orfas[q]; }
      if(!segue) { k = -1; continue; }
      Log("AVISO", mzNome[r], "ORFA", StringFormat("%s @%.0f ord #%I64u fora dos invariantes (ficha %+d)%s: cancelando", Mae_TipoNome(mzPend[i].tipo), mzPend[i].preco, mzPend[i].ticket, e.f, oco ? " [OCO]" : ""));
      int d = Mae_Cancela(r, tk_o, "orfa");
      if(d != D_CANC) return;
      Leitura_Atualiza(false);
      Mae_Estado(r, e);
      k = -1;                                            // recomeca: os indices mudaram
   }
   if(so_orfas) return;
   // cancelamento da E: bloqueio, zeragem/corte, pedido do modulo sem confirmacao, sem S em 10 s
   if(e.iE >= 0)
   {
      string m = "";
      if(mzBloq) m = "bloqueio de entradas";
      else if(agora >= Mae_Zr(r, agora)) m = "zeragem/corte";
      else if(mzECancelPedido[r] && agora >= mzRecProx[r][RC_K]) m = "pedido do robo (retentativa)";
      else if(e.volS == 0 && e.f == 0 && mzEVivaDesde[r] > 0 && agora - mzEVivaDesde[r] >= 10) m = "sem S em 10 s";
      if(m != "")
      {
         ulong tk = mzPend[e.iE].ticket;
         int d = Mae_Cancela(r, tk, "E: " + m);
         if(d == D_CANC)
         {
            mzETicket[r] = 0;
            Log("INFO", mzNome[r], m == "zeragem/corte" ? "CORTE" : "CANCELA", "E cancelada (" + m + ")" + (mzECancelPedido[r] ? "" : ": modulo avisado (nao rearma)"));
            if(!mzECancelPedido[r]) Mae_Evento(r, EV_ENTRADA_CANCELADA);
            mzECancelPedido[r] = false;
         }
         else if(d == D_ANTES) Mae_Evento(r, EV_EXECUTOU_ANTES);
         else Mae_Recusa(r, "cancelar a E (" + m + ")", RC_K);
         return;
      }
   }
   // saida por regra adiada (A-2): enviada assim que o estado fechar; some se a ficha zerar ou mudar
   if(mzSaidaPedida[r] != "" && (e.f == 0 || mzFid[r] != mzSaidaFid[r])) { mzSaidaPedida[r] = ""; mzSaidaFid[r] = 0; }
   if(mzSaidaPedida[r] != "" && Ficha_Tem(r) && Mae_Continuo(agora) && agora >= mzRecProx[r][RC_X])
   {
      int rs = Mae_Saida(r, P_X, "pedido do robo: " + mzSaidaPedida[r], 0, true, true);
      if(rs == FICHA_ENVIADA) { mzSaidaPedida[r] = ""; mzSaidaFid[r] = 0; }
      else if(rs == FICHA_RECUSADA) { Log("AVISO", mzNome[r], "SAIDA", "saida adiada recusada: volta a' regra do robo"); mzSaidaPedida[r] = ""; mzSaidaFid[r] = 0; }
      return;
   }
   // saidas do maestro e correcoes
   if(e.f == 0 || e.trans) { mzEpisodio[r] = false; return; }
   bool trocada = Mae_Trocada(r, e), dup = Mae_Duplicada(r, e);
   if(!trocada && !dup) mzEpisodio[r] = false;
   if(trocada || dup)
   {
      // um episodio = periodo continuo com a ficha errada; a 2a correcao em 10 min (episodio novo) trava
      if(!mzEpisodio[r])
      {
         mzEpisodio[r] = true;
         Log("ALERTA", mzNome[r], dup ? "DUPLICADA" : "TROCADA", StringFormat("ficha %+d (deal #%I64u): S cobre |ficha|; correcao com o magic do robo", e.f, mzFid[r]));
         if(mzUltCorrecao[r] > 0 && agora - mzUltCorrecao[r] < 600 && !mzCorrTravada[r])
         {
            mzCorrTravada[r] = true;
            Log("ALERTA", mzNome[r], dup ? "DUPLICADA" : "TROCADA", "segunda correcao em menos de 10 min: SEM correcao; a ficha segue protegida pela S");
            Mae_Bloqueia(StringFormat("correcao repetida (%s)", mzNome[r]));
         }
      }
      if(mzCorrTravada[r] || mzProtegendo) return;
      if(!Mae_Continuo(agora) || agora < mzRecProx[r][RC_X]) return;
      int vol = dup ? Mae_Abs(e.f) - 1 : Mae_Abs(e.f);
      int ret = Mae_Saida(r, P_C, dup ? "correcao de duplicada" : "correcao de ficha trocada", vol, trocada, trocada);
      if(ret == FICHA_RECUSADA) Mae_Recusa(r, "correcao", RC_X);
      return;
   }
   if(!Mae_Continuo(agora) || agora < mzRecProx[r][RC_X]) return;
   string motivo = "";
   bool corte = agora >= Mae_CorteDe(agora);
   if(Mae_Noite(r)) motivo = "ficha que atravessou a noite";
   else if(agora >= Mae_Zr(r, agora)) motivo = corte ? "corte" : "zeragem do robo";
   if(motivo == "") return;
   if(mzProtegendo && !corte) return;                    // PROTEGENDO: so' a saida do corte
   Log("INFO", mzNome[r], Mae_Noite(r) ? "NOITE" : (motivo == "corte" ? "CORTE" : "ZERAGEM"), StringFormat("zerando ficha %+d (%s)", e.f, motivo));
   int ret = Mae_Saida(r, P_X, motivo, 0, true, true);
   if(ret == FICHA_RECUSADA) Mae_Recusa(r, "saida (" + motivo + ")", RC_X);
   else if(ret == FICHA_ENVIADA) mzRecN[r][RC_X] = 0;
}

// Fase 2: S para toda E viva e toda ficha (inclusive trocada e duplicada, com volume |ficha|), a qualquer hora em
// que a corretora aceite ordens; mover S e A para o nivel pedido (sec. 5.3, sec. 8, sec. 9.3, sec. 10.2 passo 8).
// A protecao nao espera ordem de outro papel em transito (C-1).
void Mae_Fase2(const int r, const bool partida)
{
   if(!mzPendOk || mzSemOrdens) return;                   // ficha indeterminada e trava perdida nao param a protecao (5)
   datetime agora = Mae_Agora();
   if(!Mae_JanelaCall(agora)) return;
   if(mzTickSize <= 0.0) return;
   if(!mzCruzOk && agora >= Mae_CorteDe(agora)) return;    // corte com a cruzada aberta: quem age e' Mae_CorteConta
   SRoboEstado e; Mae_Estado(r, e);
   if(e.trans) return;
   if(e.lp != 0 && e.volS < e.need && !Mae_TemTransitoPapel(r, P_S))
   {
      if(mzSemSDesde[r] == 0) mzSemSDesde[r] = agora;
      if(agora < mzRecProx[r][RC_S] && !partida) return;
      double nivel;
      string fonte;
      if(e.f == 0)
      {
         if(e.iE < 0) return;                                   // E ainda nao confirmada: a S dela ja' foi antes
         nivel = mzStopNivel[r];
         fonte = "nivel da entrada";
         if(nivel <= 0.0)
         {
            if(Mae_TemTransito(r)) return;
            Log("ALERTA", mzNome[r], "STOP", "E viva sem nivel de stop conhecido: cancelando a E (sem S possivel)");
            int d = Mae_Cancela(r, mzPend[e.iE].ticket, "E sem S possivel");
            if(d == D_CANC) { mzETicket[r] = 0; Mae_Evento(r, EV_ENTRADA_CANCELADA); }
            return;
         }
      }
      else
      {
         if(!partida && agora - mzSemSDesde[r] < 2) return;
         // saida do robo sem desfecho e cruzada aberta: a liquida ja' mudou e o deal nao chegou -> a ficha provavelmente
         // ja' zerou; S nova so' com a cruzada fechando (sem saida em voo, a S e' recriada) (T28)
         if(!mzCruzOk && (Mae_TemTransitoPapel(r, P_X) || Mae_TemTransitoPapel(r, P_C))) return;
         nivel = Mae_NivelStopFicha(r, e, fonte);
      }
      if(e.f != 0 && Mae_NivelAtravessado(e.lp, nivel))
      {
         if(Mae_Continuo(agora) && agora >= mzRecProx[r][RC_X] && !Mae_TemTransito(r) && !mzProtegendo && !mzTravaPerdida && !mzIndet[r] && !Mae_Trocada(r, e) && !Mae_Duplicada(r, e))
         {
            Log("AVISO", mzNome[r], "STOP", StringFormat("ficha %+d sem S e nivel %.0f (%s) ja' atravessado: saida a mercado", e.f, nivel, fonte));
            int ret = Mae_Saida(r, P_X, "nivel atravessado", 0, true, true);
            if(ret == FICHA_RECUSADA) Mae_Recusa(r, "saida (nivel atravessado)", RC_X);
         }
         else Log_Cond(StringFormat("atravessado.%d", r), true, "ALERTA", mzNome[r], Mae_Noite(r) ? "NOITE" : "STOP",
                       StringFormat("ficha %+d: nivel %.0f (%s) ja' atravessado pelo preco: nenhuma S", e.f, nivel, fonte));
         return;
      }
      if(fonte == "emergencia") Log("ALERTA", mzNome[r], "STOP", StringFormat("ficha %+d sem nivel de stop do robo: S de emergencia a %.0f pts do preco da ficha", e.f, STOP_EMERGENCIA_PTS));
      int d;
      string m = (e.f == 0) ? "S da entrada" : (Mae_Noite(r) ? "NOITE: S DAY nova" : (e.volS > 0 ? "S complementar" : "S recriada"));
      int ret = Mae_EnviaS(r, e.lp, nivel, 1, m + " (" + fonte + ")", false, d);   // uma S de 1 por contrato que falta (B-3)
      if(ret == FICHA_ENVIADA && (d == D_VIVA || d == D_EXEC))
      {
         mzRecN[r][RC_S] = 0; mzSemSDesde[r] = 0;
         if(Mae_Noite(r)) Log("INFO", mzNome[r], "NOITE", StringFormat("S DAY nova @%.0f (%s)", nivel, fonte));
         if(e.f != 0 && mzStopNivel[r] <= 0.0 && !Mae_Trocada(r, e)) mzStopNivel[r] = Mae_NoTick(nivel);
      }
      else if(ret != FICHA_BLOQUEADA) Mae_Recusa(r, "S", RC_S);
      return;
   }
   if(e.volS >= e.need) mzSemSDesde[r] = 0;
   // move as S validas para o nivel pedido pelo robo
   if(mzStopNivel[r] > 0.0 && !Mae_Trocada(r, e) && agora >= mzRecProx[r][RC_S])
      for(int k = 0; k < e.nSk; k++)
      {
         int i = e.sKeep[k];
         if(MathAbs(mzPend[i].preco - mzStopNivel[r]) < mzTickSize / 2.0) continue;
         if(Mae_NivelAtravessado(e.lp, mzStopNivel[r]))
         {
            Log_Cond(StringFormat("pedidoatravessado.%d", r), true, "AVISO", mzNome[r], "STOP",
                     StringFormat("nivel pedido %.0f ja' atravessado: S mantida em %.0f", mzStopNivel[r], mzPend[i].preco));
            break;
         }
         int ret = Mae_Modifica(r, P_S, mzPend[i].ticket, mzStopNivel[r], "S ao nivel pedido (retentativa)");
         if(ret == FICHA_RECUSADA) Mae_Recusa(r, "mover S", RC_S);
         return;
      }
   // alvo: recriado sempre que o robo pediu um e ele nao esta' vivo; movido ao nivel pedido (so' no continuo, nunca na ficha da noite)
   if(e.f != 0 && Ficha_Tem(r) && mzAlvoNivel[r] > 0.0 && Mae_Continuo(agora) && !Mae_Noite(r) && !Mae_TemTransito(r) &&
      !mzProtegendo && !mzTravaPerdida && agora >= mzRecProx[r][RC_A])
   {
      if(e.iA < 0)
      {
         int lado = -Mae_Sinal(e.f);
         MqlTradeRequest req;
         ZeroMemory(req);
         req.action = TRADE_ACTION_PENDING;
         req.type = (lado > 0) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
         req.volume = 1.0; req.price = mzAlvoNivel[r];
         req.type_filling = ORDER_FILLING_RETURN; req.type_time = ORDER_TIME_DAY; req.deviation = 0;
         int d; ulong tk;
         int ret = Mae_Envia(r, P_A, req, partida ? "alvo recriado da memoria" : "alvo recriado", false, false, d, tk);
         if(ret == FICHA_ENVIADA && d == D_VIVA) Log("INFO", mzNome[r], "ALVO", StringFormat("recriado @%.0f ord #%I64u", mzAlvoNivel[r], tk));
         else Mae_Recusa(r, "alvo", RC_A);
      }
      else if(MathAbs(mzPend[e.iA].preco - mzAlvoNivel[r]) >= mzTickSize / 2.0)
      {
         int ret = Mae_Modifica(r, P_A, mzPend[e.iA].ticket, mzAlvoNivel[r], "A ao nivel pedido (retentativa)");
         if(ret == FICHA_RECUSADA) Mae_Recusa(r, "mover A", RC_A);
      }
   }
}

// Fim de operacao: sem ficha, sem E, sem transito -> niveis pedidos zerados.
void Mae_Limpeza(const int r)
{
   SRoboEstado e; Mae_Estado(r, e);
   if(e.f == 0 && e.dirE == 0 && e.iE < 0 && !Mae_TemTransito(r) && mzETicket[r] == 0)
   {
      if(e.iS < 0) mzStopNivel[r] = 0.0;
      mzAlvoNivel[r] = 0.0;
   }
}

// Corte: ALERTA para ficha aberta de robo cuja zeragem ja' devia ter acontecido; robo sem desfecho: ALERTA por minuto.
void Mae_Corte(void)
{
   datetime agora = Mae_Agora();
   if(!Mae_DiaUtil(agora)) return;
   datetime corte = Mae_CorteDe(agora), fim = Mae_FDe(agora), hoje = Mae_Dia(agora);
   if(agora < corte || agora >= fim + 3600) return;
   if(mzCorteDia != hoje)
   {
      mzCorteDia = hoje;
      Log("INFO", "MAESTRO", "CORTE", StringFormat("corte %s (F %s)", TimeToString(corte, TIME_MINUTES), TimeToString(fim, TIME_MINUTES)));
      for(int r = 0; r < NROBOS; r++)
         if(mzF[r] != 0 && Mae_Zr(r, agora) < corte)
            Log("ALERTA", mzNome[r], "CORTE", StringFormat("ficha %+d aberta no corte: a zeragem do robo falhou; zerando pelo corte", mzF[r]));
   }
   if(agora < fim)
      for(int r = 0; r < NROBOS; r++)
         if(Mae_TemTransito(r) && agora - mzCorteAlertaR[r] >= 60)
         {
            mzCorteAlertaR[r] = agora;
            Log("ALERTA", mzNome[r], "CORTE", "ordem sem desfecho depois do corte: a saida espera a prova; a S protege ate' F");
         }
}

// Resumo do dia (O19), depois do corte, uma vez.
void Mae_Resumo(void)
{
   datetime agora = Mae_Agora();
   if(!Mae_DiaUtil(agora)) return;
   datetime hoje = Mae_Dia(agora);
   if(mzResumoDia == hoje || agora < Mae_CorteDe(agora)) return;
   bool aberto = false;
   for(int r = 0; r < NROBOS; r++) if(mzF[r] != 0) aberto = true;
   if(aberto && agora < Mae_FDe(agora)) return;
   mzResumoDia = hoje;
   double total = 0.0, bruto = 0.0;
   int deals = 0, linhas = 0;
   for(int r = 0; r < NROBOS; r++)
   {
      total += mzRes[r]; bruto += mzResBruto[r];
      Log("INFO", mzNome[r], "RESUMO", StringFormat("R$ %.2f (bruto %.2f), %d contrato(s) negociado(s), ficha %+d", mzRes[r], mzResBruto[r], mzContratos[r], mzF[r]));
   }
   int n = ArraySize(mzDl);
   for(int i = 0; i < n; i++)
      if(mzDl[i].robo >= 0 && (datetime)(mzDl[i].t / 1000) >= hoje && (mzDl[i].tipo == DEAL_TYPE_BUY || mzDl[i].tipo == DEAL_TYPE_SELL)) deals++;
   int na = ArraySize(mzAbs);
   for(int i = 0; i < na; i++) if((datetime)(mzAbs[i].t / 1000) >= hoje) deals++;
   string ls[];
   int nl = Log_LeDia(hoje, ls);
   for(int i = 0; i < nl; i++)
      if(StringFind(ls[i], "| ENTROU |") > 0 || StringFind(ls[i], "| SAIU |") > 0 || StringFind(ls[i], "| ABSORVIDA |") > 0) linhas++;
   Log("INFO", "MAESTRO", "RESUMO", StringFormat("total R$ %.2f (bruto %.2f); deals de robo + absorcoes %d; linhas ENTROU/SAIU/ABSORVIDA no log %d", total, bruto, deals, linhas));
   if(deals != linhas) Log("ALERTA", "MAESTRO", "RESUMO", StringFormat("contagem diverge: %d deals x %d linhas no log (item 1.21)", deals, linhas));
   if(!mzHouveExternoHoje && mzDiaComecouZerado && mzLiq == 0)
   {
      if(MathAbs(bruto - mzLucroHoje) > 0.01)
         Log("ALERTA", "MAESTRO", "RESUMO", StringFormat("total pelas fichas %.2f diferente da soma de DEAL_PROFIT %.2f", bruto, mzLucroHoje));
   }
   else Log("INFO", "MAESTRO", "RESUMO", "comparacao fichas x DEAL_PROFIT nao aplicavel (dia com deal externo, posicao no inicio ou liquida aberta)");
}

// Corte com a verificacao cruzada aberta (D2: "todos zerados ate' o corte"). Decide so' pela posicao REAL e pelas
// ordens REAIS vivas, nunca pelas fichas (A-1):
//  0. espera TODA ordem de robo em transito ter desfecho, e a cruzada aberta ha' 10 s (lag de deal nao e' historico incompleto);
//  1. cancela as limites vivas dos robos (E, A): cancelar nunca aumenta a exposicao;
//  2. liquida real != 0: uma C a mercado de -liquida (papel C registrado: nunca vira E), magic do 1o robo com S viva do
//     lado que protege a liquida (senao GB);
//  3. liquida real 0: cancela as S dos robos.
// Sem ordem em voo, sem limite viva e com volume = -liquida, a exposicao so' diminui. Posicao ilegivel: nada sai, ALERTA
// por minuto. Em F com algo aberto: as S DAY ficam e ALERTA por minuto.
void Mae_CorteContaAlerta(const string msg)
{
   datetime agora = Mae_Agora();
   if(agora - mzCorteContaAlerta < 60) return;
   mzCorteContaAlerta = agora;
   Log("ALERTA", "MAESTRO", "CORTE_CONTA", msg);
}

void Mae_CorteConta(void)
{
   datetime agora = Mae_Agora();
   if(!Mae_DiaUtil(agora) || mzCruzOk) return;
   datetime corte = Mae_CorteDe(agora), fim = Mae_FDe(agora);
   if(agora < corte || agora >= fim + CALL_MIN * 60) return;
   if(mzTravaPerdida || mzSemOrdens) return;
   bool conexao = mzCorr.Testador() || (mzConectado && agora - mzConectadoDesde >= 10);
   if(!mzLiqOk || !mzPendOk || !conexao) { Mae_CorteContaAlerta("corte com a verificacao cruzada aberta e a posicao real ilegivel: nada enviado; as S ficam"); return; }
   if(mzCruzFalhaDesde == 0 || agora - mzCruzFalhaDesde < 10) return;
   if(ArraySize(mzTr) > 0)
   {
      if(agora >= fim) Mae_CorteContaAlerta("F com ordem de robo sem desfecho e a cruzada aberta: S DAY mantidas");
      return;                                              // a saida espera a prova (9.3 item 5)
   }
   if(agora < mzCorteContaProx) return;
   // 1. limites vivas dos robos
   ulong tks[];
   int rs[];
   int n = ArraySize(mzPend), m = 0;
   for(int i = 0; i < n; i++)
   {
      int ro = Mae_Robo(mzPend[i].magic);
      if(ro < 0 || Mae_TipoStop(mzPend[i].tipo)) continue;
      ArrayResize(tks, m + 1); ArrayResize(rs, m + 1);
      tks[m] = mzPend[i].ticket; rs[m] = ro; m++;
   }
   if(m > 0)
   {
      Log("ALERTA", "MAESTRO", "CORTE_CONTA", StringFormat("corte com a cruzada aberta: cancelando %d limite(s) viva(s) dos robos antes de zerar", m));
      mzCorteConta = true;
      for(int k = 0; k < m; k++)
         if(Mae_PendIdx(tks[k]) >= 0 && Mae_Cancela(rs[k], tks[k], "corte: limite cancelada antes da zeragem da conta") != D_CANC) { mzCorteContaProx = agora + RETENTA; break; }
      mzCorteConta = false;
      return;
   }
   // 2. liquida real != 0
   if(mzLiq != 0)
   {
      if(agora >= fim) { Mae_CorteContaAlerta(StringFormat("F com a liquida real %+d e a cruzada aberta: S DAY mantidas", mzLiq)); return; }
      int r = -1;
      for(int k = 0; k < NROBOS && r < 0; k++)
         for(int i = 0; i < n && r < 0; i++)
            if(mzPend[i].magic == mzMagic[k] && Mae_TipoStop(mzPend[i].tipo) && -Mae_LadoTipo(mzPend[i].tipo) == Mae_Sinal(mzLiq)) r = k;
      if(r < 0) r = R_GB;
      int lado = -Mae_Sinal(mzLiq);
      MqlTradeRequest req;
      ZeroMemory(req);
      req.action = TRADE_ACTION_DEAL;
      req.type = (lado > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      req.volume = (double)Mae_Abs(mzLiq);
      req.price = (lado > 0) ? mzCorr.SimboloD(SYMBOL_ASK) : mzCorr.SimboloD(SYMBOL_BID);
      req.type_filling = mzFillMercado;
      req.deviation = 0;
      Log("ALERTA", mzNome[r], "CORTE_CONTA", StringFormat("corte com a verificacao cruzada aberta (deals %+d x liquida real %+d): %s %d a mercado para zerar a liquida real",
          Mae_SomaFichas() + mzExt, mzLiq, lado > 0 ? "compra" : "venda", Mae_Abs(mzLiq)));
      int d; ulong tk;
      mzCorteConta = true;
      int ret = Mae_Envia(r, P_C, req, "corte: zera a liquida real", false, false, d, tk);
      mzCorteConta = false;
      if(ret != FICHA_ENVIADA) mzCorteContaProx = agora + RETENTA;
      return;
   }
   // 3. liquida real 0: cancela as S dos robos
   m = 0;
   for(int i = 0; i < n; i++)
   {
      int ro = Mae_Robo(mzPend[i].magic);
      if(ro < 0) continue;
      ArrayResize(tks, m + 1); ArrayResize(rs, m + 1);
      tks[m] = mzPend[i].ticket; rs[m] = ro; m++;
   }
   if(m == 0) return;
   Log("ALERTA", "MAESTRO", "CORTE_CONTA", StringFormat("liquida real 0 com a cruzada aberta: cancelando %d S dos robos", m));
   mzCorteConta = true;
   for(int k = 0; k < m; k++)
   {
      if(Mae_PendIdx(tks[k]) < 0) continue;
      if(Mae_Cancela(rs[k], tks[k], "corte: liquida real zerada") != D_CANC) { mzCorteContaProx = agora + RETENTA; break; }
   }
   mzCorteConta = false;
}

// Uma reconciliacao completa (a cada 1 s e a cada deal).
void Mae_Reconcilia(void)
{
   Leitura_Atualiza(false);
   if(!mzLiqOk) { Log_Cond("leitura", true, "AVISO", "MAESTRO", "ESTADO", "leitura da liquida descartada (erro de consulta)"); Mae_CorteConta(); return; }
   Log_Cond("leitura", false, "", "MAESTRO", "ESTADO", "");
   Mae_NovosEventos();
   Transito_Resolve();
   datetime agora = Mae_Agora();
   // cruzada que nao fecha com leitura confiavel: ALERTA apos 30 s; bloqueio apos 60 s (mesmo prazo da partida)
   bool cruz_ruim = !mzCruzOk && Mae_LeituraConfiavel() && mzCruzFalhaDesde > 0;
   if(cruz_ruim && agora - mzCruzFalhaDesde >= 30)
      Log_Cond("cruzada", true, "ALERTA", "MAESTRO", "ESTADO",
               StringFormat("verificacao cruzada nao fecha: deals %+d x liquida %+d; nenhum envio", Mae_SomaFichas() + mzExt, mzLiq));
   if(!cruz_ruim) Log_Cond("cruzada", false, "", "MAESTRO", "ESTADO", "");
   if(cruz_ruim && agora - mzCruzFalhaDesde >= 60 && !mzBloqCruz)
   {
      mzBloqCruz = true;
      Mae_Bloqueia(StringFormat("verificacao cruzada nao fecha ha' 60 s: deals %+d x liquida %+d (diferenca na janela de 10 pregoes %+d)",
                   Mae_SomaFichas() + mzExt, mzLiq, mzDifPendente));
   }
   for(int r = 0; r < NROBOS; r++)
      Log_Cond(StringFormat("indet.%d", r), mzIndet[r], "ALERTA", mzNome[r], "ESTADO", "deal do robo com ordem ainda nao identificada: nada e' decidido para o robo ate' a ordem aparecer no historico");
   if(mzPendOk)
   {
      for(int r = 0; r < NROBOS; r++) Mae_EControle(r);
      for(int r = 0; r < NROBOS; r++) Mae_Fase1(r, false);
      for(int r = 0; r < NROBOS; r++) Mae_Fase2(r, false);
   }
   for(int r = 0; r < NROBOS; r++) Mae_Limpeza(r);
   Mae_CorteConta();
   Mae_Corte();
   Mae_Resumo();
   Mae_GravaMemoria(false);
}

// O robo pode receber Tick()? O calculo do sinal roda sempre (leilao e fora do pregao, como no avulso);
// so' o ENVIO e' condicionado pelo maestro (horario, D1, bloqueio, uma operacao por vez) (A-5).
bool Mae_PodeTick(const int r)
{
   return mzPronto && !mzProtegendo && !mzFalhou[r];
}

//+------------------------------------------------------------------+
//| Memoria (sec. 10.1)                                                  |
//+------------------------------------------------------------------+
void Mae_Exporta(void)
{
   Mem_Limpa();
   datetime agora = Mae_Agora();
   Mem_Set("servidor", mzCorr.ContaS(ACCOUNT_SERVER));
   Mem_SetI("conta", mzCorr.ContaI(ACCOUNT_LOGIN));
   Mem_Set("simbolo", _Symbol);
   Mem_SetI("pregao", (long)Mae_Dia(agora));
   Mem_SetI("ult_deal_msc", mzUltDealMsc);
   Mem_SetU("ult_deal_tk", mzUltDealTk);
   Mem_SetI("heartbeat", mzCorr.Testador() ? 0 : (long)agora);
   Mem_SetI("seq_dia", (long)mzSeqDia);
   Mem_SetB("bloqueio", mzBloq);
   Mem_Set("bloqueio_motivo", mzBloqMotivo);
   Mem_SetB("bloqueio_cruzada", mzBloqCruz);
   Mem_SetI("ext_desc", mzExtDesc);
   Mem_SetI("dif_pendente", mzDifPendente);
   string rec = "";
   int nrc = ArraySize(mzReconhecidos);
   for(int i = 0; i < nrc; i++) rec += (i > 0 ? "," : "") + StringFormat("%I64u", mzReconhecidos[i]);
   Mem_Set("reconhecidos", rec);
   int nt = ArraySize(mzTr);
   Mem_SetI("tr.n", nt);
   for(int i = 0; i < nt; i++)
      Mem_Set(StringFormat("tr.%d", i), StringFormat("%d|%d|%d|%s|%.2f|%d|%.2f|%I64d|%I64u|%u|%u|%d",
              mzTr[i].robo, mzTr[i].papel, mzTr[i].seq, mzTr[i].coment, mzTr[i].vol, mzTr[i].lado, mzTr[i].preco,
              (long)mzTr[i].hora, mzTr[i].ticket, mzTr[i].req_id, mzTr[i].retcode, mzTr[i].tipo));
   for(int r = 0; r < NROBOS; r++)
   {
      string p = mzNome[r] + ".mae.";
      Mem_SetI(p + "seq", mzSeq[r]);
      Mem_SetD(p + "stop", mzStopNivel[r]);
      Mem_SetD(p + "alvo", mzAlvoNivel[r]);
      Mem_SetU(p + "eticket", mzETicket[r]);
      Mem_SetI(p + "edir", mzEDir[r]);
      Mem_SetI(p + "eviva", (long)mzEVivaDesde[r]);
      Mem_SetB(p + "ecancpedido", mzECancelPedido[r]);
      Mem_SetI(p + "ultcorr", (long)mzUltCorrecao[r]);
      Mem_SetB(p + "corrtravada", mzCorrTravada[r]);
      Mem_Set(p + "saidapedida", mzSaidaPedida[r]);
      Mem_SetU(p + "saidafid", mzSaidaFid[r]);
   }
   Robo_Exporta();
}

// Leitura de chaves da memoria carregada (modulos, no Init).
int Car_Idx(const string k)
{
   int n = ArraySize(mzCarK);
   for(int i = 0; i < n; i++) if(mzCarK[i] == k) return i;
   return -1;
}
bool   Car_Tem(const string k)                    { return mzCarMesmoDia && Car_Idx(k) >= 0; }
long   Car_GetI(const string k, const long def)   { int i = Car_Idx(k); return (!mzCarMesmoDia || i < 0) ? def : StringToInteger(mzCarV[i]); }
double Car_GetD(const string k, const double def) { int i = Car_Idx(k); return (!mzCarMesmoDia || i < 0) ? def : StringToDouble(mzCarV[i]); }
bool   Car_GetB(const string k, const bool def)   { int i = Car_Idx(k); return (!mzCarMesmoDia || i < 0) ? def : (mzCarV[i] == "1"); }

// Copia as chaves de modulo da memoria carregada para a memoria em montagem (enquanto os modulos nao iniciaram).
void Car_CopiaModulos(void)
{
   if(!mzCarMesmoDia) return;
   int n = ArraySize(mzCarK);
   for(int i = 0; i < n; i++)
   {
      string k = mzCarK[i];
      if(StringFind(k, ".mae.") >= 0) continue;
      for(int r = 0; r < NROBOS; r++) if(StringFind(k, mzNome[r] + ".") == 0) { Mem_Set(k, mzCarV[i]); break; }
   }
}

// Le a memoria (passo 5). Devolve 0 ok, 1 .bak, 2 perdida, 3 ignorada (outra conta/servidor/simbolo).
int Mae_Importa(void)
{
   int st = Mem_Carrega();
   ArrayResize(mzCarK, 0); ArrayResize(mzCarV, 0);
   mzCarMesmoDia = false;
   if(st == 2) return 2;
   if(Mem_Get("servidor", "") != mzCorr.ContaS(ACCOUNT_SERVER) || Mem_GetI("conta", -1) != mzCorr.ContaI(ACCOUNT_LOGIN) || Mem_Get("simbolo", "") != _Symbol)
   {
      Mem_Limpa();
      return 3;
   }
   datetime hoje = Mae_Dia(Mae_Agora());
   bool mesmo = ((datetime)Mem_GetI("pregao", 0) == hoje);
   mzHeartbeatMem = (datetime)Mem_GetI("heartbeat", 0);
   mzUltDealMsc = Mem_GetI("ult_deal_msc", 0);
   mzUltDealTk = Mem_GetU("ult_deal_tk", 0);
   // sempre mantidos: transito nao resolvido, bloqueios, reconhecidos, externa desconhecida
   mzBloq = Mem_GetB("bloqueio", false);
   mzBloqMotivo = Mem_Get("bloqueio_motivo", "");
   mzBloqCruz = Mem_GetB("bloqueio_cruzada", false);
   mzExtDesc = (int)Mem_GetI("ext_desc", 0);
   mzDifPendente = (int)Mem_GetI("dif_pendente", 0);
   string rec[];
   int nr = StringSplit(Mem_Get("reconhecidos", ""), ',', rec);
   ArrayResize(mzReconhecidos, 0);
   for(int i = 0; i < nr; i++)
   {
      if(rec[i] == "") continue;
      int n = ArraySize(mzReconhecidos);
      ArrayResize(mzReconhecidos, n + 1);
      mzReconhecidos[n] = (ulong)StringToInteger(rec[i]);
   }
   int nt = (int)Mem_GetI("tr.n", 0);
   ArrayResize(mzTr, 0);
   for(int i = 0; i < nt; i++)
   {
      string c[];
      if(StringSplit(Mem_Get(StringFormat("tr.%d", i), ""), '|', c) != 15) continue;   // coment tem 3 '|' internos
      int n = ArraySize(mzTr);
      ArrayResize(mzTr, n + 1);
      mzTr[n].robo = (int)StringToInteger(c[0]); mzTr[n].papel = (int)StringToInteger(c[1]); mzTr[n].seq = (int)StringToInteger(c[2]);
      mzTr[n].coment = c[3] + "|" + c[4] + "|" + c[5] + "|" + c[6];
      mzTr[n].vol = StringToDouble(c[7]); mzTr[n].lado = (int)StringToInteger(c[8]); mzTr[n].preco = StringToDouble(c[9]);
      mzTr[n].hora = (datetime)StringToInteger(c[10]); mzTr[n].ticket = (ulong)StringToInteger(c[11]);
      mzTr[n].req_id = (uint)StringToInteger(c[12]); mzTr[n].retcode = (uint)StringToInteger(c[13]); mzTr[n].alertou = false;
      mzTr[n].tipo = (int)StringToInteger(c[14]);
   }
   mzSeqDia = mesmo ? (datetime)Mem_GetI("seq_dia", 0) : 0;
   for(int r = 0; r < NROBOS; r++)
   {
      string p = mzNome[r] + ".mae.";
      bool guarda = mesmo || mzF[r] != 0;                    // outro pregao: so' o estado das fichas abertas
      mzSeq[r] = mesmo ? (int)Mem_GetI(p + "seq", 0) : 0;
      mzStopNivel[r] = guarda ? Mem_GetD(p + "stop", 0.0) : 0.0;
      mzAlvoNivel[r] = guarda ? Mem_GetD(p + "alvo", 0.0) : 0.0;
      mzETicket[r] = mesmo ? Mem_GetU(p + "eticket", 0) : 0;
      mzEDir[r] = mesmo ? (int)Mem_GetI(p + "edir", 0) : 0;
      mzEVivaDesde[r] = mesmo ? (datetime)Mem_GetI(p + "eviva", 0) : 0;
      mzECancelPedido[r] = mesmo ? Mem_GetB(p + "ecancpedido", false) : false;
      mzUltCorrecao[r] = (datetime)Mem_GetI(p + "ultcorr", 0);
      mzCorrTravada[r] = Mem_GetB(p + "corrtravada", false);
      mzSaidaPedida[r] = mesmo ? Mem_Get(p + "saidapedida", "") : "";
      mzSaidaFid[r] = mesmo ? Mem_GetU(p + "saidafid", 0) : 0;
   }
   int n = ArraySize(mzMemK);
   ArrayResize(mzCarK, n); ArrayResize(mzCarV, n);
   for(int i = 0; i < n; i++) { mzCarK[i] = mzMemK[i]; mzCarV[i] = mzMemV[i]; }
   mzCarMesmoDia = mesmo;
   return st;
}

//+------------------------------------------------------------------+
//| Reinicializacao explicita de todo o estado (OnInit, P17)         |
//+------------------------------------------------------------------+
void Fichas_Reseta(void)
{
   for(int r = 0; r < NROBOS; r++)
   {
      mzAtivo[r] = true; mzFalhou[r] = false;
      mzF[r] = 0; mzPm[r] = 0.0; mzHoraMsc[r] = 0; mzFid[r] = 0; mzPorE[r] = false; mzRes[r] = 0.0; mzResBruto[r] = 0.0; mzContratos[r] = 0;
      mzZeroMsc[r] = 0; mzIndet[r] = false; mzEpisodio[r] = false;
      mzStopNivel[r] = 0.0; mzAlvoNivel[r] = 0.0; mzETicket[r] = 0; mzEDir[r] = 0; mzEVivaDesde[r] = 0; mzESumiuDesde[r] = 0;
      mzECancelPedido[r] = false; mzSemSDesde[r] = 0;
      for(int c = 0; c < 4; c++) { mzRecProx[r][c] = 0; mzRecN[r][c] = 0; mzRecAl[r][c] = 0; }
      mzIndetDesde[r] = 0; mzSaidaPedida[r] = ""; mzSaidaFid[r] = 0;
      mzUltCorrecao[r] = 0; mzCorrTravada[r] = false; mzCorteAlertaR[r] = 0; mzSeq[r] = 0;
   }
   mzLiqOk = false; mzLiquidaD = 0.0; mzLiq = 0; mzPendOk = false; ArrayResize(mzPend, 0);
   mzConectado = false; mzConectadoDesde = 0; mzReler = true; mzReleuOk = false; mzUltReleitura = 0; mzCruzUltTent = 0;
   mzCruzOk = false; mzCruzFalhaDesde = 0; mzDifPendente = 0; mzExtDesc = 0; mzExtIni = 0; mzJanIni = 0;
   ArrayResize(mzDl, 0); ArrayResize(mzHo, 0); mzUltDealMsc = 0; mzUltDealTk = 0; ArrayResize(mzLogTk, 0);
   mzTickSize = 0.0; mzTickValor = 0.0; mzDigitos = 0; mzFillMercado = ORDER_FILLING_RETURN; mzVencimento = 0;
   mzExt = 0; ArrayResize(mzCk, 0); ArrayResize(mzAbs, 0); mzHouveExternoHoje = false; mzLucroHoje = 0.0; mzDiaComecouZerado = true;
   mzSeqDia = 0; ArrayResize(mzTr, 0);
   ArrayResize(mzOmTk, 0); ArrayResize(mzOmRobo, 0); ArrayResize(mzOmPapel, 0);
   mzTravaPerdida = false; mzSemOrdens = false; mzMemFalhou = false;
   mzCorteConta = false; mzCorteContaAlerta = 0; mzCorteContaProx = 0;
   mzMagic0Pend = false; mzRelerPedido = 0; ArrayResize(mzEvR, 0); ArrayResize(mzEvE, 0);
   mzBloq = false; mzBloqMotivo = ""; mzBloqCruz = false; ArrayResize(mzReconhecidos, 0); ArrayResize(mzAbsVistas, 0); mzBotaoClique = 0;
   mzIniciou = false; mzMemCarregada = false; mzPronto = false; mzProntoEm = 0; mzPartidaEm = 0; mzHeartbeatMem = 0; mzProtegendo = false; mzModulosIniciados = false;
   mzCorteDia = 0; mzResumoDia = 0; mzAvisoGradeDia = 0; mzFichaMotivo = "";
   ArrayResize(mzCarK, 0); ArrayResize(mzCarV, 0); mzCarMesmoDia = false;
   Mem_Limpa(); mzMemUltimoTexto = "";
   Log_CondLimpa();
}

#endif
