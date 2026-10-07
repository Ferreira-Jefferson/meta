//+------------------------------------------------------------------+
//| WinMaestro_Teste.mq5                                             |
//| Testes unitarios do WinMaestro com a corretora FALSA (O15, s12). |
//| Roda tudo no OnInit, imprime PASSOU/FALHOU por caso e o placar,  |
//| e sai (ExpertRemove). Nao ha' caminho para a corretora real: a   |
//| classe CCorretoraReal nem e' compilada aqui (WINMAESTRO_TESTE).  |
//| Grava arquivos so' em MQL5/Files/WinMaestro_unit*/.              |
//| Anexe num grafico DIFERENTE do que roda o WinMaestro.            |
//+------------------------------------------------------------------+
#property copyright "WinMaestro"
#property version   "1.03"
#property description "Testes unitarios do WinMaestro v1.03 (corretora falsa)"
#property strict

#define WINMAESTRO_TESTE
#include "WinMaestro\Inputs.mqh"
#include "WinMaestro\Corretora.mqh"
#include "WinMaestro\CorretoraFalsa.mqh"
#include "WinMaestro\Log.mqh"
#include "WinMaestro\Memoria.mqh"
#include "WinMaestro\Grade.mqh"
#include "WinMaestro\Fichas.mqh"
#include "WinMaestro\Recupera.mqh"
#include "WinMaestro\WinGapBarra1.mqh"
#include "WinMaestro\WinCincoMedias.mqh"
#include "WinMaestro\WinDeslocamentoMatinal.mqh"
#include "WinMaestro\WinRetanguloEma34.mqh"
#include "WinMaestro\Win_c1.mqh"

CCorretoraFalsa *F = NULL;
int gEvento = 0;
int gEventoRobo = -1;
int gPassou = 0;
int gFalhou = 0;

//+------------------------------------------------------------------+
//| Stubs dos ganchos do nucleo (no EA real: os 5 modulos)           |
//+------------------------------------------------------------------+
void Robo_Evento(const int r, const int ev) { gEvento = ev; gEventoRobo = r; }
int Robo_MinutoZerar(const int r, const datetime dia)
{
   switch(r)
   {
      case R_GB: return 18 * 60 + 20;
      case R_CM: return 18 * 60 + 24;
      case R_DM: return 18 * 60 + 20;
      case R_RE: return 17 * 60;
      case R_C1: return 17 * 60 + 50;
   }
   return 0;
}
double Robo_StopRegra(const int r) { return 0.0; }
void   Robo_Exporta(void) { }
void   Robo_InitTodos(void) { }

//+------------------------------------------------------------------+
void Ok(const string nome, const bool cond)
{
   if(cond) { gPassou++; Print("PASSOU  ", nome); }
   else     { gFalhou++; Print("FALHOU  ", nome); }
}

void T_Base(void)
{
   mzCorr = F;
   mzLogImprime = false;
   mzLogAlert = false;
   Log_Pasta("");
   mzMemPasta = "";
   mzIniciou = true;
   mzMemCarregada = true;
   mzModulosIniciados = true;
   Mae_LeTick();
   mzPronto = true;
   mzProntoEm = F.Agora() - 3600;
   Leitura_Atualiza(true);
   gEvento = 0; gEventoRobo = -1;
}

void T_Reset(void)
{
   if(F != NULL) { delete F; F = NULL; }
   mzCorr = NULL;
   Fichas_Reseta();
   F = new CCorretoraFalsa();
   T_Base();
}

// "Reinicio" do EA sem memoria: todo o estado do maestro volta ao inicial; a corretora continua.
void T_Reinicia(void)
{
   Fichas_Reseta();
   T_Base();
}

long MG(const int r) { return mzMagic[r]; }

// Entrada limite do robo e preenchimento da E; devolve o ticket da S.
ulong EntraEnche(const int r, const int lado, const double preco, const double stop)
{
   Ficha_EntraLimite(r, lado, preco, stop, ORDER_TIME_DAY, 0, 0, "teste");
   ulong s = F.TicketPend(MG(r), lado > 0 ? ORDER_TYPE_SELL_STOP : ORDER_TYPE_BUY_STOP);
   F.Dispara(F.TicketPend(MG(r), lado > 0 ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT));
   Mae_Reconcilia();
   return s;
}

int TrIdxPapel(const int r, const int papel)
{
   int n = ArraySize(mzTr);
   for(int i = 0; i < n; i++) if(mzTr[i].robo == r && mzTr[i].papel == papel) return i;
   return -1;
}

bool TemCondPrefixo(const string p)
{
   int n = ArraySize(mzCondChave);
   for(int i = 0; i < n; i++) if(StringFind(mzCondChave[i], p) == 0) return true;
   return false;
}

//+------------------------------------------------------------------+
//| Casos originais (adaptados ao envio sem espera e a' S antes da E)|
//+------------------------------------------------------------------+
void T01_02(void)
{
   T_Reset();
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t01");
   ulong e = F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT), s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   Ok("T01 entrada limite: S viva antes da E, as duas no servidor (5.3, C-1)",
      r == FICHA_ENVIADA && e != 0 && s != 0 && s < e && F.ContaPend() == 2 && F.m_pend[F.PendIdx(s)].preco == 118700.0 &&
      F.m_pend[F.PendIdx(s)].setup_msc < F.m_pend[F.PendIdx(e)].setup_msc && mzStopNivel[R_GB] == 118700.0 && !Mae_TemTransito(R_GB));
   r = Ficha_Cancela(R_GB, P_E, "t02");
   int he = F.HistIdx(e), hs = F.HistIdx(s);
   Ok("T02 E cancelada e confirmada no historico; so' depois a S (5.1)",
      r == FICHA_ENVIADA && F.ContaPend() == 0 && he >= 0 && hs >= 0 && F.m_hist[he].estado == ORDER_STATE_CANCELED &&
      F.m_hist[hs].estado == ORDER_STATE_CANCELED && F.m_hist[he].done_msc < F.m_hist[hs].done_msc && gEvento == 0);
}

void T03(void)
{
   T_Reset();
   int r = Ficha_EntraMercado(R_C1, 1, 119000, 0, "t03");
   ulong s = F.TicketPend(MG(R_C1), ORDER_TYPE_SELL_STOP);
   long setup_e = 0;
   int nh = ArraySize(F.m_hist);
   for(int i = 0; i < nh; i++) if(F.m_hist[i].magic == MG(R_C1) && F.m_hist[i].tipo == ORDER_TYPE_BUY) setup_e = F.m_hist[i].setup_msc;
   Ok("T03 C1: S viva antes da E a mercado (5.3)",
      r == FICHA_ENVIADA && mzF[R_C1] == 1 && Ficha_Tem(R_C1) && s != 0 && setup_e > 0 && F.m_pend[F.PendIdx(s)].setup_msc < setup_e);
}

void T04(void)
{
   T_Reset();
   F.Roteiro(FM_RECUSA);
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t04");
   Ok("T04 S recusada: a E nao sai (nenhuma entrada sem a S viva)",
      r == FICHA_RECUSADA && F.ContaPend() == 0 && F.m_envios == 1 && !Mae_TemTransito(R_GB) && mzStopNivel[R_GB] == 0.0);
}

void T05(void)
{
   T_Reset();
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t05a");
   int r2 = Ficha_EntraLimite(R_GB, 1, 119800, 118600, ORDER_TIME_DAY, 0, 0, "t05b");
   Ok("T05 segunda entrada do mesmo robo: BLOQUEADA (SEGUNDA_ENTRADA)",
      r2 == FICHA_BLOQUEADA && Ficha_Motivo() == "segunda entrada" && F.ContaPend() == 2);
}

void T06(void)
{
   T_Reset();
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t06");
   F.Roteiro(FM_DONE_SEM_DEAL);
   int n0 = F.m_envios;
   int r = Ficha_Fecha(R_C1, "t06");
   bool espera = r == FICHA_ENVIADA && Mae_TemTransito(R_C1) && F.ContaPendTipo(MG(R_C1), ORDER_TYPE_SELL_STOP) == 1;
   F.MostraOcultos();
   Mae_Reconcilia();
   Ok("T06 DONE sem deal: sem esperar dentro da chamada; o deal vem depois; so' entao a S e' cancelada",
      espera && mzF[R_C1] == 0 && F.ContaPend() == 0 && !Mae_TemTransito(R_C1) && F.m_envios == n0 + 2);
}

void T07(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);
   int r = Ficha_EntraMercado(R_C1, 1, 119000, 0, "t07");
   bool espera = Mae_TemTransito(R_C1) && F.ContaPendTipo(MG(R_C1), ORDER_TYPE_SELL_STOP) == 1;
   F.Avanca(31);
   Mae_Reconcilia();
   Ok("T07 timeout com ticket 0 (nao executou): a S fica; provada nao executada aos 30 s; S cancelada",
      r == FICHA_ENVIADA && espera && !Mae_TemTransito(R_C1) && F.ContaPend() == 0 && mzF[R_C1] == 0 && gEvento == EV_ENTRADA_CANCELADA);

   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_EXEC);
   r = Ficha_EntraMercado(R_C1, 1, 119000, 0, "t07b");
   Ok("T07b timeout com ticket 0 (executou): ordem achada pelo comentario, ficha +1 com a S",
      r == FICHA_ENVIADA && mzF[R_C1] == 1 && Ficha_Tem(R_C1) && !Mae_TemTransito(R_C1) && F.ContaPendTipo(MG(R_C1), ORDER_TYPE_SELL_STOP) == 1);
}

void T08(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_RECUSA);
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t08");
   Ok("T08 E recusada: RECUSADA ao modulo, S cancelada, nada no transito, nenhum nivel pendurado",
      r == FICHA_RECUSADA && F.ContaPend() == 0 && !Mae_TemTransito(R_GB) && mzStopNivel[R_GB] == 0.0);
}

void T09(void)
{
   T_Reset();
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t09");
   ulong e = F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT), s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   F.Dispara(s);
   int n0 = F.m_envios;
   Mae_Reconcilia();
   SRoboEstado st; Mae_Estado(R_GB, st);
   bool trans = mzF[R_GB] == -1 && st.trans && !Ficha_Tem(R_GB) && F.m_envios == n0 && F.PendIdx(e) >= 0;
   F.Dispara(e);
   Mae_Reconcilia();
   Ok("T09 S executa antes da E: transitorio (sem correcao); a E enche e a ficha volta a 0",
      trans && mzF[R_GB] == 0 && F.ContaPend() == 0 && F.m_envios == n0);

   T_Reset();
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t09b");
   e = F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT); s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   F.Dispara(s);
   Mae_Reconcilia();
   F.CancelaPorFora(e, ORDER_STATE_CANCELED);
   Mae_Reconcilia();
   Ok("T09b ficha invertida e a E some sem deal: trocada, corrigida com o magic do robo",
      mzF[R_GB] == 0 && F.ContaPend() == 0 && gEvento == EV_ENTRADA_CANCELADA);
}

void T10(void)
{
   T_Reset();
   ulong s = EntraEnche(R_RE, 1, 119900, 119000);
   int ra = Ficha_DefineAlvo(R_RE, 121000, "t10");
   ulong a = F.TicketPend(MG(R_RE), ORDER_TYPE_SELL_LIMIT);
   F.Dispara(s);
   F.Dispara(a);
   Mae_Reconcilia();
   Ok("T10 S e A do RE executam (EA fora): ficha trocada corrigida com C de compra 1",
      ra == FICHA_ENVIADA && a != 0 && mzF[R_RE] == 0 && F.ContaPend() == 0);
}

void T11(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DealPorFora(MG(R_GB), 1, 1, 120005);
   Mae_Reconcilia();
   Ok("T11 entrada executada duas vezes: correcao de 1, S mantida",
      mzF[R_GB] == 1 && Ficha_Tem(R_GB) && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1);
}

void T12(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   EntraEnche(R_DM, 1, 119900, 118800);
   Ficha_EntraLimite(R_CM, -1, 120100, 125045, ORDER_TIME_DAY, 0, 0, "t12cm");
   ulong ext = F.DealPorFora(0, -1, 2, 120000);
   Mae_Reconcilia();
   bool b1 = mzBloq && mzF[R_GB] == 0 && mzF[R_DM] == 0 && mzExt == 0 && gEvento == EV_ENTRADA_CANCELADA && gEventoRobo == R_CM;
   F.Avanca(6);
   Mae_Reconcilia();
   bool b2 = F.ContaPend() == 0;
   int r = Ficha_EntraLimite(R_RE, 1, 119900, 119000, ORDER_TIME_DAY, 0, 0, "t12re");
   Mae_Desbloqueia();
   bool b3 = !mzBloq && Mae_Reconhecido(ext);
   ArrayResize(mzAbsVistas, 0);                 // reinicio: absorcoes esquecidas, reconhecidos mantidos
   Mae_Reconcilia();
   Ok("T12 zeragem manual: absorcao GB e DM, E cancelada, S canceladas, bloqueio; botao libera; reinicio nao rebloqueia",
      b1 && b2 && r == FICHA_BLOQUEADA && b3 && !mzBloq);
}

void T13(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DealPorFora(0, 1, 1, 120005);
   Mae_Reconcilia();
   bool a = mzExt == 1 && mzF[R_GB] == 1 && !mzBloq;
   F.DealPorFora(0, -1, 1, 120000);
   Mae_Reconcilia();
   Ok("T13 posicao manual aberta e fechada: externa volta a 0, fichas intactas, sem bloqueio",
      a && mzExt == 0 && mzF[R_GB] == 1 && !mzBloq);
}

void T14(void)
{
   T_Reset();
   F.m_liq = 1;                                   // liquida sem deal que a explique
   Leitura_Atualiza(true);
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t14");
   Ok("T14 verificacao cruzada nao fecha: entrada nao sai (nem a S dela)",
      !mzCruzOk && r == FICHA_BLOQUEADA && StringFind(Ficha_Motivo(), "cruzada") >= 0 && F.m_envios == 0);
}

void T15(void)
{
   T_Reset();
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t15");
   F.Roteiro(FM_RECUSA);
   int r = Ficha_Fecha(R_C1, "t15");
   Ok("T15 saida recusada: a S continua", r == FICHA_RECUSADA && mzF[R_C1] == 1 && F.ContaPendTipo(MG(R_C1), ORDER_TYPE_SELL_STOP) == 1);
}

void T16(void)
{
   T_Reset();
   ulong s = EntraEnche(R_RE, 1, 119900, 119000);
   Ficha_DefineAlvo(R_RE, 121000, "t16");
   F.Dispara(s);
   Mae_Reconcilia();
   Ok("T16 OCO: o stop executa e o alvo e' cancelado na hora", mzF[R_RE] == 0 && F.ContaPend() == 0);
}

void T17(void)
{
   T_Reset();
   FolderCreate("WinMaestro_unit");
   mzMemPasta = "WinMaestro_unit\\";
   FileDelete("WinMaestro_unit\\estado.txt"); FileDelete("WinMaestro_unit\\estado.bak"); FileDelete("WinMaestro_unit\\estado.tmp");
   Mem_Limpa(); Mem_Set("a", "x"); Mem_SetI("b", 42);
   bool w1 = Mem_Grava(true);
   Mem_Limpa();
   int c1 = Mem_Carrega();
   long b1 = Mem_GetI("b", 0);
   Mem_Limpa(); Mem_Set("a", "x"); Mem_SetI("b", 43);
   Mem_Grava(true);
   int h = FileOpen("WinMaestro_unit\\estado.txt", FILE_WRITE | FILE_TXT | FILE_UNICODE);
   if(h != INVALID_HANDLE) { FileWriteString(h, "b=99\nfim=1\n"); FileClose(h); }
   int c2 = Mem_Carrega();
   long b2 = Mem_GetI("b", 0);
   FileDelete("WinMaestro_unit\\estado.txt"); FileDelete("WinMaestro_unit\\estado.bak");
   int c3 = Mem_Carrega();
   mzMemPasta = "";
   Ok("T17 memoria: grava e le com checksum; .txt corrompido -> .bak; os dois ausentes -> memoria perdida",
      w1 && c1 == 0 && b1 == 42 && c2 == 1 && b2 == 42 && c3 == 2);
}

void T18(void)
{
   T_Reset();
   mzVencimento = 0;
   bool g1 = Mae_CorteDe(D'2026.10.07 10:00') == D'2026.10.07 18:20' && Mae_FDe(D'2026.10.07 10:00') == D'2026.10.07 18:25';
   bool g2 = Mae_CorteDe(D'2023.06.01 10:00') == D'2023.06.01 17:50';
   mzVencimento = Grade_VencimentoDoSimbolo("WINV26");
   bool g3 = mzVencimento == D'2026.10.14' && Mae_CorteDe(D'2026.10.14 10:00') == D'2026.10.14 18:20';   // o vencimento nao muda o corte
   mzVencimento = 0;
   bool g4 = Mae_CorteDe(D'2026.11.03 10:00') == D'2026.11.03 17:50' && Grade_VencimentoDoSimbolo("WIN$N") == 0;
   bool g5 = Mae_Zr(R_CM, D'2026.10.07 10:00') == D'2026.10.07 18:20' && Mae_Zr(R_RE, D'2026.10.07 10:00') == D'2026.10.07 17:00' &&
             Mae_Zr(R_CM, D'2023.06.01 10:00') == D'2023.06.01 17:50';
   Ok("T18 grade e corte (D2): 18:20; 17:50 nos dias de 17:55; vencimento do contrato nao muda o corte; 17:50 sem linha; CM limitado ao corte",
      g1 && g2 && g3 && g4 && g5);
}

void T19(void)
{
   T_Reset();
   int r1 = Ficha_EntraLimite(R_CM, -1, 120100, 125045, ORDER_TIME_DAY, 0, 0, "t19cm");
   int n0 = F.m_envios;
   int r2 = Ficha_EntraLimite(R_GB, 1, 120100, 118900, ORDER_TIME_DAY, 0, 0, "t19gb");
   Ok("T19 autonegociacao (O2): E que cruza com limite propria de outro robo nao sai (nem a S dela)",
      r1 == FICHA_ENVIADA && r2 == FICHA_BLOQUEADA && StringFind(Ficha_Motivo(), "autonegociacao") >= 0 && F.m_envios == n0);
}

void T20(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DefineAgora(D'2026.10.07 18:20:01');
   Mae_Reconcilia();
   Ok("T20 corte: ficha aberta zerada pelo timer em F - 5 min e S cancelada depois", mzF[R_GB] == 0 && F.ContaPend() == 0);
}

void T21(void)
{
   T_Reset();
   F.DefineAgora(D'2026.10.06 15:00:00');
   Leitura_Atualiza(true);
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t21");
   ulong s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   F.Dispara(F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT));
   F.CancelaPorFora(s, ORDER_STATE_EXPIRED);       // EA fora no corte: a S DAY venceu com o pregao
   F.DefineAgora(D'2026.10.07 08:56:00');
   T_Reinicia();                                    // volta sem memoria
   bool n1 = mzF[R_GB] == 1 && Mae_Noite(R_GB) && mzCruzOk && F.ContaPend() == 0;
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();  // S DAY nova na pre-abertura, pela reconciliacao
   ulong s2 = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   bool n2 = s2 != 0 && F.m_pend[F.PendIdx(s2)].preco == 119900.0 - STOP_EMERGENCIA_PTS;
   F.DefineAgora(D'2026.10.07 09:00:01');
   Mae_Reconcilia();
   Ok("T21 ficha que atravessou a noite: S DAY nova na pre-abertura (emergencia sem memoria); zerada no primeiro continuo",
      n1 && n2 && mzF[R_GB] == 0 && F.ContaPend() == 0);
}

void T22(void)
{
   T_Reset();
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t22");
   F.Roteiro(FM_DONE_SEM_DEAL);
   F.DefineAgora(D'2026.10.07 17:49:50');
   int r = Ficha_Fecha(R_C1, "t22");
   bool p1 = r == FICHA_ENVIADA && Mae_TemTransito(R_C1);
   int n0 = F.m_envios;
   F.DefineAgora(D'2026.10.07 18:20:10');
   Mae_Reconcilia();
   bool p2 = F.m_envios == n0 && Mae_TemTransito(R_C1) && F.ContaPendTipo(MG(R_C1), ORDER_TYPE_SELL_STOP) == 1;
   F.MostraOcultos();
   Mae_Reconcilia();
   Ok("T22 ordem sem desfecho no corte: nada reenviado, S protegendo; com o deal visivel, S cancelada",
      p1 && p2 && !Mae_TemTransito(R_C1) && mzF[R_C1] == 0 && F.ContaPend() == 0);
}

void T23(void)
{
   T_Reset();
   mzProntoEm = F.Agora();
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, F.Agora() - 60, "t23");
   Ok("T23 decisao anterior a' partida: DECISAO PERDIDA, nada enviado",
      r == FICHA_BLOQUEADA && Ficha_Motivo() == "decisao perdida" && F.m_envios == 0);
}

void T24(void)
{
   T_Reset();
   Ficha_EntraLimite(R_DM, 1, 119900, 118800, ORDER_TIME_DAY, 0, 0, "t24");
   F.Roteiro(FM_EXECUTA_ANTES);
   int r = Ficha_Cancela(R_DM, P_E, "t24");
   Ok("T24 cancelamento perde a corrida: EXECUTOU_ANTES ao modulo, ficha +1 com a S",
      r == FICHA_BLOQUEADA && gEvento == EV_EXECUTOU_ANTES && mzF[R_DM] == 1 && F.ContaPendTipo(MG(R_DM), ORDER_TYPE_SELL_STOP) == 1);
}

void T25(void)
{
   T_Reset();
   FolderClean("WinMaestro_unit_log", 0);
   FolderCreate("WinMaestro_unit_log");
   FolderCreate("WinMaestro_unit_log\\logs");
   Log_Pasta("WinMaestro_unit_log\\");
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t25");
   string com = ArraySize(mzTr) == 1 ? mzTr[0].coment : "";
   ArrayResize(mzTr, 0);
   for(int k = 0; k < NROBOS; k++) mzSeq[k] = 0;
   Recupera_LogOrdens();
   bool ok = ArraySize(mzTr) == 1 && com != "" && mzTr[0].coment == com && mzTr[0].papel == P_E && mzSeq[R_C1] == 2;
   Log_Pasta("");
   Ok("T25 memoria perdida: transito refeito das linhas ORDEM do log do dia; seq continua", ok);
}

void T26(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   int r = Ficha_DefineStop(R_GB, 119905, "t26");
   ulong s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   int r0 = Ficha_DefineStop(R_GB, 0.0, "t26 nivel zero");
   int rx = Ficha_DefineStop(R_GB, 120100, "t26 lado errado");   // acima do bid: a bolsa recusa
   Ok("T26 mover a S: OrderModify do mesmo ticket; nivel 0 ignorado; nivel do lado errado recusado e a S antiga fica",
      r == FICHA_ENVIADA && s != 0 && F.ContaPend() == 1 && r0 == FICHA_BLOQUEADA && rx == FICHA_RECUSADA &&
      F.m_pend[F.PendIdx(s)].preco == 119905.0 && mzRecProx[R_GB][RC_S] > F.Agora());
}

//+------------------------------------------------------------------+
//| Achados da revisao de codigo 1                                   |
//+------------------------------------------------------------------+
void T27_C1(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);
   int r = Ficha_EntraLimite(R_CM, -1, 120100, 125045, ORDER_TIME_DAY, 0, 0, "t27");
   bool a = r == FICHA_ENVIADA && Mae_TemTransito(R_CM) && F.ContaPendTipo(MG(R_CM), ORDER_TYPE_BUY_STOP) == 1;
   F.Avanca(6);
   Mae_Reconcilia();
   Ok("T27 C-1 S antes da E: E sem desfecho e a S ja' no servidor; a S nao vira orfa enquanto a E nao tem desfecho",
      a && F.ContaPendTipo(MG(R_CM), ORDER_TYPE_BUY_STOP) == 1);
}

void T28_C1(void)
{
   T_Reset();
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t28");
   ulong s = F.TicketPend(MG(R_C1), ORDER_TYPE_SELL_STOP);
   F.Roteiro(FM_DONE_SEM_DEAL);
   Ficha_Fecha(R_C1, "t28");                      // X executou; o deal ainda nao chegou (cruzada aberta)
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);       // a corretora tira a S
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   bool sem_s = Mae_TemTransito(R_C1) && F.ContaPendTipo(MG(R_C1), ORDER_TYPE_SELL_STOP) == 0;   // nao cria S para posicao que ja' saiu
   F.MostraOcultos();
   Mae_Reconcilia();
   bool zerou = mzF[R_C1] == 0 && F.ContaPend() == 0;

   T_Reset();
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t28b");
   s = F.TicketPend(MG(R_C1), ORDER_TYPE_SELL_STOP);
   F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Ficha_Fecha(R_C1, "t28b");                     // X nao saiu; a cruzada fecha
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   Ok("T28 C-1 X em transito: com a cruzada aberta (X executou) nenhuma S nova; com a cruzada fechando (X nao saiu) a S e' recriada",
      sem_s && zerou && Mae_TemTransito(R_C1) && F.ContaPendTipo(MG(R_C1), ORDER_TYPE_SELL_STOP) == 1);
}

void T29_C2(void)
{
   T_Reset();
   ulong s = EntraEnche(R_RE, 1, 119900, 119000);
   Ficha_DefineAlvo(R_RE, 121000, "t29");
   ulong a = F.TicketPend(MG(R_RE), ORDER_TYPE_SELL_LIMIT);
   F.Dispara(s); F.Dispara(a);                      // ficha -1 trocada
   F.Roteiro(FM_RECUSA);                            // a correcao e' recusada
   Mae_Reconcilia();
   F.Avanca(3);
   Mae_Reconcilia();
   bool com_s = mzF[R_RE] == -1 && F.ContaPendTipo(MG(R_RE), ORDER_TYPE_BUY_STOP) == 1 &&
                F.m_pend[F.PendIdx(F.TicketPend(MG(R_RE), ORDER_TYPE_BUY_STOP))].preco == 121000.0 + STOP_EMERGENCIA_PTS;
   F.Avanca(3);
   Mae_Reconcilia();                                // correcao refeita: ficha 0, S cancelada
   Ok("T29 C-2 ficha trocada no continuo com a correcao recusada: recebe S (emergencia); depois e' corrigida",
      com_s && mzF[R_RE] == 0 && F.ContaPend() == 0);
}

void T30_C2(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DealPorFora(MG(R_GB), 1, 2, 120005);           // ficha +3
   Mae_Reconcilia();
   Ok("T30 C-2 |ficha| = 3: correcao de 2 numa ordem so', sem trava nem bloqueio, S de 1 mantida",
      mzF[R_GB] == 1 && Ficha_Tem(R_GB) && F.VolPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1.0 && !mzBloq && !mzCorrTravada[R_GB]);
}

void T31_A1(void)
{
   T_Reset();
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t31");
   ulong e = F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT), s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   F.Dispara(e, true);                              // deal sem DEAL_MAGIC
   F.Avanca(6);
   Mae_Reconcilia();
   bool a = mzF[R_GB] == 1 && Ficha_Tem(R_GB) && mzExt == 0 && F.PendIdx(s) >= 0 && !mzBloq;
   F.Dispara(s, true);
   Mae_Reconcilia();
   Ok("T31 A-1 deal sem magic atribuido pela ordem: ficha do GB (nao externa), S intacta; o stop sem magic zera sem bloqueio",
      a && mzF[R_GB] == 0 && mzExt == 0 && !mzBloq);
}

void T32_A2(void)
{
   T_Reset();
   Ficha_EntraLimite(R_DM, 1, 119900, 118800, ORDER_TIME_DAY, 0, 0, "t32");
   ulong e = F.TicketPend(MG(R_DM), ORDER_TYPE_BUY_LIMIT);
   F.Roteiro(FM_TIMEOUT_TK0_NADA);                  // o primeiro cancelamento fica sem resposta e nao acontece
   int r = Ficha_Cancela(R_DM, P_E, "t32");
   bool a = r == FICHA_BLOQUEADA && F.PendIdx(e) >= 0 && mzECancelPedido[R_DM];
   int l; double p; datetime st;
   bool viva = Ficha_Entrada(R_DM, l, p, st);
   F.Avanca(31);
   Mae_Reconcilia();                                // prova: nao cancelou; o maestro refaz o cancelamento
   bool b = F.PendIdx(e) < 0 && F.m_hist[F.HistIdx(e)].estado == ORDER_STATE_CANCELED;
   F.Avanca(6);
   Mae_Reconcilia();
   Ok("T32 A-2 cancelamento de E sem desfecho: BLOQUEADA ao modulo (E segue visivel), refeito pelo maestro ate' o historico confirmar",
      a && viva && b && F.ContaPend() == 0);
}

void T33_A3(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t33");
   int i = TrIdxPapel(R_C1, P_E);
   SOrdemHist oh;
   oh.ticket = 777; oh.magic = MG(R_C1); oh.tipo = ORDER_TYPE_BUY; oh.preco = 119500; oh.vol = 1;
   oh.setup_msc = (long)(F.Agora() - 86400) * 1000; oh.done_msc = oh.setup_msc + 1; oh.estado = ORDER_STATE_FILLED;
   oh.comentario = (i >= 0) ? mzTr[i].coment : "";
   Mae_HoUpsert(oh);                                // ordem de ONTEM com o mesmo comentario
   Transito_Resolve();
   i = TrIdxPapel(R_C1, P_E);
   Ok("T33 A-3 comentario de ontem nao prova a ordem de hoje", i >= 0 && mzTr[i].ticket == 0);
}

void T34_A4(void)
{
   T_Reset();
   ulong s = EntraEnche(R_GB, 1, 119900, 118700);
   F.m_hist_falha = true;
   Leitura_Atualiza(false);
   bool nc = !Mae_LeituraConfiavel();
   int n0 = F.m_envios;
   int r = Ficha_Fecha(R_GB, "t34");
   bool barrou = r == FICHA_BLOQUEADA && F.m_envios == n0;
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();  // a protecao passa mesmo com o estado nao confiavel
   bool protege = F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1;
   F.m_hist_falha = false;
   Leitura_Atualiza(false);
   Ok("T34 A-4 leitura do historico que falha: estado nao confiavel, saida barrada, S passa; volta confiavel na releitura",
      nc && barrou && protege && Mae_LeituraConfiavel());
}

void T36_A6(void)
{
   T_Reset();
   EntraEnche(R_RE, 1, 119900, 119000);
   F.Roteiro(FM_RECUSA);
   int r = Ficha_DefineAlvo(R_RE, 121000, "t36");
   F.Avanca(6);
   Mae_Reconcilia();
   Ok("T36 A-6 alvo recusado no preenchimento e' recriado pelo maestro",
      r == FICHA_RECUSADA && F.ContaPendTipo(MG(R_RE), ORDER_TYPE_SELL_LIMIT) == 1 && F.m_pend[F.PendIdx(F.TicketPend(MG(R_RE), ORDER_TYPE_SELL_LIMIT))].preco == 121000.0);
}

void T37_M1(void)
{
   T_Reset();
   F.DealSemOrdem(MG(R_GB), 1, 1, 120005);          // ordem que nao aparece no historico nem no mapa
   Mae_Reconcilia();
   bool indet = mzIndet[R_GB] && !Ficha_Tem(R_GB);
   F.Avanca(3);
   Mae_Reconcilia();
   ulong s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   bool protegida = s != 0 && F.m_pend[F.PendIdx(s)].preco == 120005.0 - STOP_EMERGENCIA_PTS;
   F.Avanca(31);
   Mae_Reconcilia();                                // 30 s sem a ordem: tratada como trocada, corrigida
   Ok("T37 M-1/M-4 ficha indeterminada: o modulo nao a ve, mas ela recebe S; sem a ordem em 30 s e' corrigida",
      indet && protegida && mzF[R_GB] == 0 && F.ContaPend() == 0);
}

void T38_M2(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.m_pend_falha = true;                           // lista parcial (a S some da leitura) + erro
   int n0 = F.m_envios;
   F.Avanca(10);
   Mae_Reconcilia();
   F.m_pend_falha = false;
   Ok("T38 M-2 lista parcial de pendentes: nenhuma orfa cancelada nem S duplicada",
      F.m_envios == n0 && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1);
}

void T39_M3(void)
{
   T_Reset();
   ulong s = EntraEnche(R_GB, 1, 119900, 118700);
   mzTravaPerdida = true;
   int r = Ficha_EntraLimite(R_DM, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t39");
   int rf = Ficha_Fecha(R_GB, "t39");
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   int n0 = F.m_envios;
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   mzTravaPerdida = false;
   Ok("T39 M-3 trava em outro grafico: entrada e saida nao saem desta instancia; a S sai",
      r == FICHA_BLOQUEADA && rf != FICHA_ENVIADA && mzF[R_GB] == 1 && F.m_envios == n0 + 1 && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1);
}

void T40_M4(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DefineAgora(D'2026.10.07 18:20:01');
   F.m_rc = TRADE_RETCODE_MARKET_CLOSED;
   F.Roteiro(FM_RETCODE);
   Mae_Reconcilia();
   Ok("T40 M-4 mercado fechado (feriado): recusa retentada sem escalar a ALERTA",
      mzF[R_GB] == 1 && mzRecN[R_GB][RC_X] == 0 && mzRecProx[R_GB][RC_X] > F.Agora());
}

void T41_M5(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DealPorFora(MG(R_GB), 1, 1, 120005);           // duplicada
   mzProtegendo = true;
   Mae_Reconcilia();
   F.Avanca(3);
   Mae_Reconcilia();
   bool a = mzF[R_GB] == 2 && F.VolPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 2.0;
   mzSemOrdens = true;
   F.CancelaPorFora(F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP), ORDER_STATE_CANCELED);
   int n0 = F.m_envios;
   F.Avanca(3);
   Mae_Reconcilia();
   Ok("T41 M-5 PROTEGENDO: sem correcao, so' S (cobrindo |ficha|); conta nao NETTING: nenhuma ordem",
      a && F.m_envios == n0);
}

void T42_M6(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t42");
   mzBloq = true;
   Mae_Desbloqueia();
   Ok("T42 M-6 botao: ordem recente sem desfecho continua no transito", !mzBloq && Mae_TemTransito(R_C1));
}

void T43_M7(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DefineAgora(D'2026.10.07 19:00:00');
   F.DealPorFora(0, -1, 1, 120000);
   F.DealPorFora(0, 1, 1, 120010);
   Mae_Reconcilia();
   Ok("T43 M-7 ajuste noturno fecha/reabre fora do continuo: sem absorcao nem bloqueio; ficha da noite intacta",
      mzF[R_GB] == 1 && mzExt == 0 && !mzBloq);
}

void T44_M9(void)
{
   T_Reset();
   mzMemPasta = "WinMaestro_unit<|>\\";
   Mae_GravaMemoria(true);
   bool falhou = mzMemFalhou;
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t44");
   mzMemPasta = ""; mzMemFalhou = false;
   Ok("T44 M-9 falha ao gravar a memoria: ALERTA e nenhuma entrada", falhou && r == FICHA_BLOQUEADA && F.m_envios == 0);
}

void T45_M10(void)
{
   T_Reset();
   ulong s = EntraEnche(R_GB, 1, 119900, 118700);
   F.m_liq += 1;                                    // cruzada abre
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   Ok("T45 M-10 cruzada aberta nao barra a protecao: S recriada", !mzCruzOk && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1);
}

void T46_B1(void)
{
   T_Reset();
   F.DefineAgora(D'2026.10.06 15:00:00');
   Leitura_Atualiza(true);
   EntraEnche(R_RE, 1, 119900, 119000);
   mzAlvoNivel[R_RE] = 121000;
   F.DefineAgora(D'2026.10.07 08:56:00');
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   Ok("T46 B-1 ficha da noite: nenhum alvo recriado fora do continuo", F.ContaPendTipo(MG(R_RE), ORDER_TYPE_SELL_LIMIT) == 0);
}

void T47_B2(void)
{
   T_Reset();
   EntraEnche(R_RE, 1, 119900, 119000);
   Ficha_DefineAlvo(R_RE, 121000, "t47");
   F.DealPorFora(MG(R_RE), 1, 1, 120005);           // duplicada
   Mae_Reconcilia();
   Ok("T47 B-2 correcao de duplicada nao cancela o alvo", mzF[R_RE] == 1 && F.ContaPendTipo(MG(R_RE), ORDER_TYPE_SELL_LIMIT) == 1);
}

void T48_B3(void)
{
   T_Reset();
   FolderClean("WinMaestro_unit_b3", 0);
   FolderCreate("WinMaestro_unit_b3");
   FolderCreate("WinMaestro_unit_b3\\logs");
   Log_Pasta("WinMaestro_unit_b3\\");
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t48");
   F.m_mesmo_ms = true;
   F.Dispara(F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT));
   Mae_Reconcilia();                                // o 1o deal e' logado
   F.DealPorFora(MG(R_GB), 1, 1, 120005);           // segundo deal no MESMO ms, visto numa leitura depois
   F.m_mesmo_ms = false;
   Mae_Reconcilia();
   string ls[];
   int nl = Log_LeDia(Mae_Dia(F.Agora()), ls), entrou = 0;
   for(int i = 0; i < nl; i++) if(StringFind(ls[i], "| ENTROU |") > 0) entrou++;
   Log_Pasta("");
   Ok("T48 B-3 dois deals no mesmo ms: os dois logados (marca por ticket)", entrou == 2);
}

void T49_B4(void)
{
   T_Reset();
   F.m_liq = 1;
   Leitura_Atualiza(true);
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t49a");
   bool aberta = TemCondPrefixo("estado.0.");
   F.m_liq = 0;
   Leitura_Atualiza(true);
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t49b");
   Ok("T49 B-4 condicao de estado aberto encerrada quando o envio seguinte passa", aberta && !TemCondPrefixo("estado.0."));
}

void T50_B5(void)
{
   T_Reset();
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t50");
   ulong s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);       // a S da E some
   F.Roteiro(FM_RECUSA);                            // a 1a recriacao e' recusada
   Mae_Reconcilia();
   F.Avanca(6);
   Mae_Reconcilia();                                // a S e' retentada antes do prazo de cancelar a E (10 s)
   Ok("T50 B-5 S da E recusada e' retentada antes de a E ser cancelada",
      F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1 && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_BUY_LIMIT) == 1);
}

void T51_B6(void)
{
   T_Reset();
   F.m_msc = (long)D'2026.10.07 10:00:00' * 1000 + 100;
   F.m_tick_msc = (long)D'2026.10.07 10:00:00' * 1000 + 437;
   long a = Mae_AgoraMsc();
   F.m_tick_msc = (long)D'2026.10.07 09:59:58' * 1000 + 437;   // tick de outro segundo: nao serve
   long b = Mae_AgoraMsc();
   F.m_tick_msc = 0;
   Ok("T51 B-6 instante em ms vem do ultimo tick do mesmo segundo", a == (long)D'2026.10.07 10:00:00' * 1000 + 437 && b == (long)D'2026.10.07 10:00:00' * 1000);
}

void T52_B7(void)
{
   T_Reset();
   for(int k = 0; k < 20; k++) F.AddPend(MG(R_GB), ORDER_TYPE_SELL_STOP, 110000 + k * 5, 1, "");
   F.Avanca(6);
   Mae_Reconcilia();
   Ok("T52 B-7 mais de 16 ordens orfas do robo: todas canceladas", F.ContaPend() == 0);
}

void T53_B8(void)
{
   T_Reset();
   FolderCreate("WinMaestro_unit");
   mzMemPasta = "WinMaestro_unit\\";
   string v = "a" + ShortToString(0x00E7) + ShortToString(0x00E3) + "o";
   Mem_Limpa(); Mem_Set("x", v);
   Mem_Grava(true);
   Mem_Limpa();
   int c = Mem_Carrega();
   mzMemPasta = "";
   Ok("T53 B-8 memoria com acento grava e le (checksum sobre o mesmo texto)", c == 0 && Mem_Get("x", "") == v);
}

void T54_B10(void)
{
   T_Reset();
   F.m_rc = TRADE_RETCODE_TOO_MANY_REQUESTS;
   F.Roteiro(FM_RETCODE);
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t54");
   Ok("T54 B-10 TOO_MANY_REQUESTS e' recusa provada (sem pausa de 30 s)", r == FICHA_RECUSADA && !Mae_TemTransito(R_GB));
}

void T55_C2ep(void)
{
   T_Reset();
   for(int vez = 0; vez < 2; vez++)
   {
      Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t55");
      ulong e = F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT), s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
      F.CancelaPorFora(e, ORDER_STATE_CANCELED);
      F.Dispara(s);                                 // ficha -1 aberta pela S, sem E: trocada
      F.m_bid = 118700; F.m_ask = 118705;           // o preco esta' no stop que executou
      Mae_Reconcilia();
      F.Avanca(3);
      Mae_Reconcilia();
   }
   Ok("T55 C-2 segundo episodio em 10 min: sem correcao, bloqueio, e a ficha continua protegida pela S",
      mzF[R_GB] == -1 && mzCorrTravada[R_GB] && mzBloq && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_BUY_STOP) == 1);
}

//+------------------------------------------------------------------+
//| Lacunas de cobertura                                             |
//+------------------------------------------------------------------+
void T56_Partida(void)
{
   T_Reset();
   ulong s = EntraEnche(R_GB, 1, 119900, 118700);
   mzStopNivel[R_GB] = 118500;                      // nivel pedido pelo robo, so' na memoria
   FolderClean("WinMaestro_unit_part", 0);
   FolderCreate("WinMaestro_unit_part");
   mzMemPasta = "WinMaestro_unit_part\\";
   Mae_GravaMemoria(true);
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);       // a S sumiu com o EA fora
   // partida completa
   Fichas_Reseta();
   mzCorr = F;
   mzMemPasta = "WinMaestro_unit_part\\";
   mzPartidaEm = F.Agora();
   Recupera_Inicia();
   for(int k = 0; k < 60 && mzPasso > 0 && mzPasso < 12; k++) { Recupera_Passo(); F.Avanca(1); }
   ulong s2 = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   bool ok = mzPasso == 12 && mzPronto && mzF[R_GB] == 1 && s2 != 0 && F.m_pend[F.PendIdx(s2)].preco == 118500.0;
   mzMemPasta = "";
   Ok("T56 sequencia de partida: passos 1-11 ate' PRONTO; S recriada no nivel da memoria", ok);
}

void T57_Memoria(void)
{
   T_Reset();
   FolderClean("WinMaestro_unit_mem", 0);
   FolderCreate("WinMaestro_unit_mem");
   mzMemPasta = "WinMaestro_unit_mem\\";
   mzStopNivel[R_CM] = 125000; mzAlvoNivel[R_RE] = 121000; mzBloq = true; mzBloqMotivo = "teste";
   ArrayResize(mzReconhecidos, 1); mzReconhecidos[0] = 42; mzExtDesc = 3; mzSeq[R_GB] = 7; mzSeqDia = Mae_Dia(F.Agora());
   mzUltCorrecao[R_DM] = F.Agora() - 100;
   ArrayResize(mzTr, 1);
   mzTr[0].robo = R_C1; mzTr[0].papel = P_X; mzTr[0].seq = 3; mzTr[0].coment = "MAE|C1|X|0003"; mzTr[0].vol = 1; mzTr[0].lado = -1;
   mzTr[0].preco = 120000; mzTr[0].hora = F.Agora(); mzTr[0].ticket = 991; mzTr[0].req_id = 12; mzTr[0].retcode = 10012; mzTr[0].alertou = false; mzTr[0].tipo = ORDER_TYPE_SELL;
   Mae_GravaMemoria(true);
   Fichas_Reseta();
   mzCorr = F;
   mzMemPasta = "WinMaestro_unit_mem\\";
   int st = Mae_Importa();
   bool ok = st == 0 && mzStopNivel[R_CM] == 125000 && mzAlvoNivel[R_RE] == 121000 && mzBloq && mzBloqMotivo == "teste" &&
             ArraySize(mzReconhecidos) == 1 && mzReconhecidos[0] == 42 && mzExtDesc == 3 && mzSeq[R_GB] == 7 &&
             mzUltCorrecao[R_DM] == F.Agora() - 100 && ArraySize(mzTr) == 1 && mzTr[0].coment == "MAE|C1|X|0003" &&
             mzTr[0].ticket == 991 && mzTr[0].papel == P_X && mzTr[0].robo == R_C1 && mzTr[0].retcode == 10012;
   mzMemPasta = "";
   Ok("T57 memoria ida e volta: transito, bloqueio, reconhecidos, externa desconhecida, seq, niveis e correcao", ok);
}

void T58_OnTrade(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t58");
   int i = TrIdxPapel(R_C1, P_E);
   uint req = (i >= 0) ? mzTr[i].req_id : 0;
   MqlTradeTransaction tr; MqlTradeRequest rq; MqlTradeResult rs;
   ZeroMemory(tr); ZeroMemory(rq); ZeroMemory(rs);
   tr.type = TRADE_TRANSACTION_REQUEST; rq.symbol = _Symbol; rs.request_id = req; rs.order = 4242;
   Mae_OnTradeTransaction(tr, rq, rs);              // TRADE_TRANSACTION_REQUEST: request_id -> ticket
   i = TrIdxPapel(R_C1, P_E);
   bool liga = req != 0 && i >= 0 && mzTr[i].ticket == 4242;
   // DEAL_ADD reconcilia na hora: o stop do RE executa e o alvo cai pelo OCO sem esperar o timer
   T_Reset();
   ulong s = EntraEnche(R_RE, 1, 119900, 119000);
   Ficha_DefineAlvo(R_RE, 121000, "t58");
   mzPasso = 12;
   F.Dispara(s);
   ZeroMemory(tr); tr.type = TRADE_TRANSACTION_DEAL_ADD; tr.symbol = _Symbol;
   Mae_OnTradeTransaction(tr, rq, rs);
   mzPasso = 0;
   Ok("T58 OnTradeTransaction do maestro: request_id liga o ticket; DEAL_ADD reconcilia (OCO na hora)", liga && F.ContaPend() == 0 && mzF[R_RE] == 0);
}

void T59_Conexao(void)
{
   T_Reset();
   F.m_testador = false;
   F.m_conectado = false;
   Leitura_Atualiza(false);
   F.m_conectado = true;
   Leitura_Atualiza(false);
   bool nao = !Mae_LeituraConfiavel();
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t59");
   F.Avanca(11);
   Leitura_Atualiza(false);
   bool sim = Mae_LeituraConfiavel();
   F.m_testador = true;
   Ok("T59 perda de conexao: leitura nao confiavel ate' 10 s conectado e releitura completa; nada sai antes",
      nao && r == FICHA_BLOQUEADA && F.m_envios == 0 && sim);
}

void T60_Colisao(void)
{
   T_Reset();
   F.AddHist(9001, MG(R_GB), ORDER_TYPE_BUY_LIMIT, 119000, 1, (long)F.Agora() * 1000 - 5000, ORDER_STATE_CANCELED, "MAE|GB|E|0007");
   Leitura_Atualiza(true);
   Rec_SeqHistorico();
   Ok("T60 colisao de comentario: seq do dia continua depois do maior seq do historico", Mae_ProxSeq(R_GB) == 8);
}

void T61_CorteConta(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   EntraEnche(R_CM, -1, 120100, 125045);
   F.m_liq += 1;                                    // liquida real +1 sem deal que explique: cruzada aberta
   F.DefineAgora(D'2026.10.07 18:20:05');
   F.m_liq_falha = true;                            // 1o: posicao real ilegivel -> nada sai
   int n0 = F.m_envios;
   Mae_Reconcilia();
   bool nada = F.m_envios == n0 && F.ContaPend() == 2;
   F.m_liq_falha = false;
   Mae_Reconcilia();                                // cruzada aberta ha' menos de 10 s: espera
   F.Avanca(11);
   Mae_Reconcilia();                                // ordem C de venda 1 com o magic do GB
   bool zerou = F.m_liq == 0;
   bool c_gb = false;
   int nh = ArraySize(F.m_hist);
   for(int i = 0; i < nh; i++)
      if(F.m_hist[i].tipo == ORDER_TYPE_SELL && F.m_hist[i].magic == MG(R_GB) && StringFind(F.m_hist[i].comentario, "MAE|GB|C|") == 0 && F.m_hist[i].vol == 1.0) c_gb = true;
   bool s_ficou = F.ContaPend() == 2;               // as S so' saem depois da ordem executada
   F.Avanca(1);
   Mae_Reconcilia();                                // liquida real 0: cancela todas as pendentes dos robos
   F.Avanca(2);
   Mae_Reconcilia();
   Ok("T61 corte com a cruzada aberta: posicao ilegivel -> nada; depois C de -liquida com o magic do robo do mesmo lado; so' entao as S canceladas; liquida real 0",
      !mzCruzOk && nada && zerou && c_gb && s_ficou && F.ContaPend() == 0 && F.m_liq == 0);
}

//+------------------------------------------------------------------+
//| Achados da revisao de codigo 2                                   |
//+------------------------------------------------------------------+
void T62_A1(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   Ficha_EntraLimite(R_CM, -1, 120100, 125045, ORDER_TIME_DAY, 0, 0, "t62");   // E do CM viva (limite)
   F.m_liq += 1;                                    // liquida real +2 com deals +1: cruzada aberta
   F.ZeraPico();
   F.DefineAgora(D'2026.10.07 18:20:00');
   Mae_Reconcilia();                                // cruzada aberta ha' menos de 10 s: espera
   bool espera = F.ContaPendTipo(MG(R_CM), ORDER_TYPE_SELL_LIMIT) == 1 && F.m_liq == 2;
   F.Avanca(11); Mae_Reconcilia();                  // 1. cancela a limite do CM
   bool limite = F.ContaPendTipo(MG(R_CM), ORDER_TYPE_SELL_LIMIT) == 0 && F.m_liq == 2;
   F.Avanca(1); Mae_Reconcilia();                   // 2. C de venda 2 com o magic do GB (dono da S de venda)
   bool c_gb = false;
   int nh = ArraySize(F.m_hist);
   for(int i = 0; i < nh; i++) if(F.m_hist[i].magic == MG(R_GB) && StringFind(F.m_hist[i].comentario, "MAE|GB|C|") == 0 && F.m_hist[i].vol == 2.0) c_gb = true;
   F.Avanca(1); Mae_Reconcilia();                   // 3. liquida 0: S canceladas
   Ok("T62 A-1 corte com a cruzada aberta decide pela posicao e ordens reais: espera 10 s, cancela limites, zera com o dono da S, cancela as S; nunca passa da liquida inicial",
      espera && limite && c_gb && F.m_liq == 0 && F.ContaPend() == 0 && F.m_liq_pico <= 2);
}

void T63_A2(void)
{
   T_Reset();
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t63");
   F.m_liq += 1;                                    // cruzada aberta por um instante (deal atrasado de outro robo)
   int n0 = F.m_envios;
   int r = Ficha_Fecha(R_C1, "canal");
   bool adiada = r == FICHA_ENVIADA && mzSaidaPedida[R_C1] == "canal" && F.m_envios == n0 && mzF[R_C1] == 1;
   F.m_liq -= 1;                                    // o estado fecha
   Mae_Reconcilia();
   Ok("T63 A-2 saida por regra barrada por estado aberto nao se perde: o maestro envia quando o estado fecha",
      adiada && mzF[R_C1] == 0 && F.ContaPend() == 0 && mzSaidaPedida[R_C1] == "");
}

void T64_A3(void)
{
   T_Reset();
   ulong s = EntraEnche(R_C1, 1, 119000, 118000);
   F.Dispara(s);                                    // a S zera a ficha
   F.DealPorFora(MG(R_C1), -1, 1, 117995, "MAE|C1|X|0009");   // X colocada depois do zero (corrida 1.23), sem registro nesta execucao
   Mae_Reconcilia();
   bool troc1 = mzF[R_C1] == 0 && F.ContaPend() == 0;   // trocada pelo comentario X, corrigida
   // com o registro do envio (mapa), o papel X vale mesmo sem comentario
   T_Reset();
   s = EntraEnche(R_C1, 1, 119000, 118000);
   F.Dispara(s);
   ulong d = F.DealPorFora(MG(R_C1), -1, 1, 117995, "");
   Mae_OmAdd(F.m_tk, R_C1, P_X);
   SRoboEstado e; Leitura_Atualiza(true); Mae_Estado(R_C1, e);
   bool troc2 = mzF[R_C1] == -1 && !Ficha_Tem(R_C1) && Mae_Trocada(R_C1, e);
   Mae_Reconcilia();
   Ok("T64 A-3 X que executa depois do zero: ficha trocada (nunca entrada), corrigida pela secao 8",
      troc1 && troc2 && mzF[R_C1] == 0 && d > 0);
}

void T65_A4(void)
{
   T_Reset();
   ulong s = EntraEnche(R_RE, 1, 119900, 119000);
   Ficha_DefineAlvo(R_RE, 121000, "t65");
   mzMemPasta = "WinMaestro_unit<|>\\";             // gravacao falha
   ulong a = F.TicketPend(MG(R_RE), ORDER_TYPE_SELL_LIMIT);
   F.Dispara(a);                                    // alvo enche
   Mae_Reconcilia();                                // OCO: a S cai mesmo com a memoria falhando
   bool oco = mzMemFalhou && F.ContaPend() == 0;
   ulong s2 = EntraEnche(R_GB, 1, 119900, 118700);  // entrada nova: barrada
   bool entrada = s2 == 0 && mzF[R_GB] == 0;
   mzMemPasta = ""; mzMemFalhou = false;
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   mzMemPasta = "WinMaestro_unit<|>\\";
   F.DefineAgora(D'2026.10.07 18:20:01');
   Mae_Reconcilia();                                // corte sai com a memoria falhando
   bool corte = mzF[R_GB] == 0 && F.ContaPend() == 0;
   mzMemPasta = ""; mzMemFalhou = false;
   Ok("T65 A-4 memoria que nao grava: OCO e corte saem; so' entradas novas param", oco && entrada && corte && s > 0);
}

void T66_M1(void)
{
   T_Reset();
   EntraEnche(R_RE, 1, 119900, 119000);
   Ficha_DefineAlvo(R_RE, 121000, "t66");
   F.Dispara(F.TicketPend(MG(R_RE), ORDER_TYPE_SELL_LIMIT));   // alvo enche
   F.Roteiro(FM_EXECUTA_ANTES);                     // o cancelamento da S perde a corrida
   Mae_Reconcilia();
   Ok("T66 M-1 cancelamento de S que perde a corrida nao avisa EXECUTOU_ANTES ao modulo", gEvento != EV_EXECUTOU_ANTES);
}

void T67_M2(void)
{
   T_Reset();
   FolderClean("WinMaestro_unit_m2", 0);
   FolderCreate("WinMaestro_unit_m2");
   mzMemPasta = "WinMaestro_unit_m2\\";
   mzExtDesc = 1;
   Mae_GravaMemoria(true);                          // memoria com a externa de origem desconhecida gravada pelo botao
   F.m_liq = 1;                                     // posicao sem deal na janela
   Fichas_Reseta();
   mzCorr = F;
   mzMemPasta = "WinMaestro_unit_m2\\";
   mzPartidaEm = F.Agora();
   Recupera_Inicia();
   Recupera_Completa();
   bool ok = mzPasso == 12 && mzCruzOk && !mzBloq && mzExtDesc == 1;
   mzMemPasta = "";
   Ok("T67 M-2 partida com externa desconhecida gravada: cruzada fecha no passo 4, sem rebloqueio", ok);
}

void T68_M3(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DefineAgora(D'2026.10.07 18:24:58');
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);   // a X executa; o cancelamento da S fica sem resposta
   Ficha_Fecha(R_GB, "t68");
   bool viva = F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1;
   F.DefineAgora(D'2026.10.07 18:26:00');           // depois de F, no call
   Mae_Reconcilia();
   F.Avanca(31);
   Mae_Reconcilia();
   Ok("T68 M-3 S orfa depois de F e' cancelada no call", viva && mzF[R_GB] == 0 && F.ContaPend() == 0);
}

void T69_M5(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DealSemOrdem(0, -1, 1, 120000);                // deal sem magic, ordem ainda nao localizada
   Mae_Reconcilia();
   bool carencia = !mzBloq && mzF[R_GB] == 1 && mzMagic0Pend;
   F.Avanca(11);
   Mae_Reconcilia();                                // 10 s sem a ordem: externo (zeragem manual)
   Ok("T69 M-5 deal sem magic: 10 s de carencia sem efeito; depois, externo", carencia && mzF[R_GB] == 0 && mzBloq);
}

void T70_M6(void)
{
   T_Reset();
   F.m_sem_coment = true;                           // a corretora perde o comentario (P3)
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_EXEC);   // a E entra no livro, mas volta timeout com ticket 0
   Ficha_EntraLimite(R_DM, 1, 119900, 118800, ORDER_TIME_DAY, 0, 0, "t70");
   Mae_Reconcilia();
   F.Avanca(31);
   Mae_Reconcilia();
   ulong e = F.TicketPend(MG(R_DM), ORDER_TYPE_BUY_LIMIT);
   Ok("T70 M-6 E viva sem ticket nem comentario e' achada por tipo, preco e volume: nada de 'nao executada'",
      e != 0 && !Mae_TemTransito(R_DM) && mzETicket[R_DM] == e && gEvento != EV_ENTRADA_CANCELADA);
}

void T71_M7(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_RECUSA);      // S aceita; E SPECIFIED recusada; E DAY aceita
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_SPECIFIED, F.Agora() + 1800, 0, "t71");
   int ns = 0, nh = ArraySize(F.m_hist);
   for(int i = 0; i < nh; i++) if(F.m_hist[i].tipo == ORDER_TYPE_SELL_STOP) ns++;
   Ok("T71 M-7 GB: validade com horario recusada -> E do dia com a MESMA S",
      r == FICHA_ENVIADA && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1 && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_BUY_LIMIT) == 1 && ns == 0 && F.m_envios == 3);
}

void T72_M8(void)
{
   T_Reset();
   F.m_testador = false;
   bool tomou = Trava_Toma();
   GlobalVariableDel(mzTravaNome);                  // dono apaga as variaveis globais
   bool retomou = Trava_Confere() && GlobalVariableGet(mzTravaNome) == mzToken;
   GlobalVariableSet(mzTravaNome, mzToken + 1.0);   // outro grafico com a trava
   bool perdida = !Trava_Confere();
   GlobalVariableDel(mzTravaNome); GlobalVariableDel(mzHbNome);
   F.m_testador = true;
   Ok("T72 M-8 variavel da trava apagada: retomada; so' outro token e' trava perdida", tomou && retomou && perdida);
}

void T73_B1(void)
{
   T_Reset();
   Ficha_EntraLimite(R_DM, 1, 119900, 118800, ORDER_TIME_DAY, 0, 0, "t73");
   mzModulosIniciados = false;                      // partida: modulos ainda nao iniciados
   F.CancelaPorFora(F.TicketPend(MG(R_DM), ORDER_TYPE_BUY_LIMIT), ORDER_STATE_CANCELED);
   Mae_Reconcilia();
   bool fila = gEvento == 0 && ArraySize(mzEvR) == 1;
   mzModulosIniciados = true;
   Mae_EntregaEventos();
   Ok("T73 B-1 aviso aos modulos antes do Init fica na fila e e' entregue depois", fila && gEvento == EV_ENTRADA_CANCELADA && gEventoRobo == R_DM);
}

void T74_B2(void)
{
   T_Reset();
   EntraEnche(R_RE, 1, 119900, 119000);
   Ficha_DefineAlvo(R_RE, 121000, "t74");
   F.CancelaPorFora(F.TicketPend(MG(R_RE), ORDER_TYPE_SELL_LIMIT), ORDER_STATE_CANCELED);
   mzProtegendo = true;
   Mae_Reconcilia(); F.Avanca(6); Mae_Reconcilia();
   bool sem = F.ContaPendTipo(MG(R_RE), ORDER_TYPE_SELL_LIMIT) == 0;
   mzProtegendo = false;
   Mae_Reconcilia();
   Ok("T74 B-2 PROTEGENDO nao recria alvo; fora dele, recria", sem && F.ContaPendTipo(MG(R_RE), ORDER_TYPE_SELL_LIMIT) == 1);
}

void T75_B3(void)
{
   T_Reset();
   EntraEnche(R_GB, 1, 119900, 118700);
   F.DealPorFora(MG(R_GB), 1, 1, 120005);           // duplicada
   mzProtegendo = true;                             // sem correcao: so' protecao
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   bool duas = F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 2 && F.VolPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 2.0;
   mzProtegendo = false;
   Mae_Reconcilia();                                // correcao de 1: sobra uma S de 1, sem buraco
   Ok("T75 B-3 S complementar de 1 por contrato excedente; depois da correcao fica uma S de 1",
      duas && mzF[R_GB] == 1 && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) >= 1);
}

void T76_B4(void)
{
   T_Reset();
   FolderClean("WinMaestro_unit_b4", 0);
   FolderCreate("WinMaestro_unit_b4");
   FolderCreate("WinMaestro_unit_b4\\logs");
   Log_Pasta("WinMaestro_unit_b4\\");
   EntraEnche(R_GB, 1, 119900, 118700);             // ENTROU logado
   Fichas_Reseta();                                 // reinicio com a memoria perdida
   mzCorr = F; mzIniciou = true; mzMemCarregada = true; mzModulosIniciados = true; mzPronto = true;
   Log_Pasta("WinMaestro_unit_b4\\");
   Mae_LeTick();
   Leitura_Atualiza(true);
   Recupera_LogOrdens();
   ArrayResize(mzDl, 0); Leitura_Atualiza(true);
   Mae_NovosEventos();
   string ls[];
   int nl = Log_LeDia(Mae_Dia(F.Agora()), ls), entrou = 0;
   for(int i = 0; i < nl; i++) if(StringFind(ls[i], "| ENTROU |") > 0) entrou++;
   Log_Pasta("");
   Ok("T76 B-4 memoria perdida: deal ja' logado no dia nao e' relogado", entrou == 1);
}

void T77_B5(void)
{
   T_Reset();
   Ficha_EntraLimite(R_DM, 1, 119000, 118000, ORDER_TIME_DAY, 0, 0, "t77dm");   // compra limite do DM a 119000
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t77gb");   // S do GB a 118700 (abaixo da limite do DM)
   Ok("T77 B-5 S que pode casar com limite propria: enviada (protecao) e registrada no log", r == FICHA_ENVIADA && TemCondPrefixo("autoneg_s.0") && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1);
}

void T78_B7(void)
{
   T_Reset();
   F.m_liq = 1;                                     // cruzada aberta
   Leitura_Atualiza(true);
   int h0 = F.m_hist_n;
   for(int k = 0; k < 20; k++) Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t78");
   Ok("T78 B-7 estado aberto repetido nao relê 10 pregoes a cada chamada", F.m_hist_n - h0 < 60);
}

void T79_B8(void)
{
   T_Reset();
   EntraEnche(R_RE, 1, 119900, 119000);
   mzRecProx[R_RE][RC_A] = F.Agora() + 60;          // alvo recusado ha' pouco
   F.DefineAgora(D'2026.10.07 17:00:01');
   Mae_Reconcilia();                                // a zeragem do RE nao espera o prazo do alvo
   bool zerou = mzF[R_RE] == 0;
   T_Reset();
   Ficha_EntraLimite(R_DM, 1, 119900, 118800, ORDER_TIME_DAY, 0, 0, "t79");
   Ficha_Cancela(R_DM, P_E, "t79");
   Ok("T79 B-8 retentativas por papel; pedido de cancelamento confirmado e' desligado", zerou && !mzECancelPedido[R_DM]);
}

void T80_B9(void)
{
   T_Reset();
   Ficha_EntraLimite(R_CM, 1, 119900, 114955, ORDER_TIME_DAY, 0, 0, "t80a");
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_TIMEOUT_TK0_NADA);   // E cancelada; o cancelamento da S fica sem desfecho
   Ficha_Cancela(R_CM, P_E, "t80");
   int r = Ficha_EntraLimite(R_CM, 1, 119800, 114855, ORDER_TIME_DAY, 0, 0, "t80b");   // rearma na mesma vela
   Ok("T80 B-9 cancelar a E e rearmar na mesma vela com o cancelamento da S antiga em curso", r == FICHA_ENVIADA && F.ContaPendTipo(MG(R_CM), ORDER_TYPE_BUY_LIMIT) == 1);
}

void T81_DM(void)
{
   T_Reset();
   WDM::Reseta(); WDM::Configura();
   Ficha_EntraLimite(R_DM, 1, 119900, 118800, ORDER_TIME_DAY, 0, 0, "t81");
   WDM::g_ordem = 1;
   F.Roteiro(FM_TIMEOUT_TK0_NADA);                  // o cancelamento fica sem resposta
   WDM::CancelarEntrada("prazo");
   bool lembra = WDM::g_ordem == 1 && WDM::OrdemPendenteViva();
   F.Avanca(31); Mae_Reconcilia();                  // o maestro refaz o cancelamento
   bool some = !WDM::OrdemPendenteViva() && WDM::g_ordem == 0;
   Ok("T81 A-2 modulo DM nao esquece a E com o cancelamento sem confirmacao; esquece quando ela some", lembra && some);
}

void T82_RE(void)
{
   T_Reset();
   WRE::Reseta(); WRE::Configura();
   Ficha_EntraLimite(R_RE, 1, 119900, 119000, ORDER_TIME_DAY, 0, 0, "t82");
   WRE::g_ordem_pendente = true; WRE::g_ticket_entrada = 1; WRE::g_lado_entrada = WRE::RET_LONG;
   WRE::g_meio_original = 119900; WRE::g_stop_original = 119000; WRE::g_alvo_original = 121000;
   F.Roteiro(FM_TIMEOUT_TK0_NADA);
   WRE::CancelarEntradaPendente();
   bool lembra = WRE::g_ordem_pendente;
   WRE::g_ordem_pendente = false;
   WRE::Evento(EV_EXECUTOU_ANTES);
   Ok("T82 A-2/A-6 modulo RE nao esquece a E sem confirmacao; EXECUTOU_ANTES restaura a entrada para adotar o fill", lembra && WRE::g_ordem_pendente);
}

void T83_Partida(void)
{
   // PROTEGENDO: conta nao NETTING com ordem de robo -> nenhuma ordem sai
   T_Reset();
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t83");
   F.m_hedging = true;
   Fichas_Reseta(); mzCorr = F; mzLogAlert = false; mzLogImprime = false;
   mzPartidaEm = F.Agora();
   Recupera_Inicia();
   int n0 = F.m_envios;
   for(int k = 0; k < 20 && mzPasso > 0 && mzPasso < 10; k++) { Recupera_Passo(); F.Avanca(1); }
   F.CancelaPorFora(F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP), ORDER_STATE_CANCELED);
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   bool prot = mzProtegendo && mzSemOrdens && F.m_envios == n0;
   F.m_hedging = false;
   // passo 4 esgotando 60 s: bloqueio e segue ate' PRONTO
   T_Reset();
   F.m_liq = 2;
   Fichas_Reseta(); mzCorr = F;
   mzPartidaEm = F.Agora();
   Recupera_Inicia();
   for(int k = 0; k < 120 && mzPasso > 0 && mzPasso < 12; k++) { Recupera_Passo(); F.Avanca(1); }
   Ok("T83 partida: PROTEGENDO em conta nao NETTING nao manda nada; passo 4 esgota 60 s, bloqueia e chega ao PRONTO",
      prot && mzPasso == 12 && mzBloq);
}

void T84_Noite(void)
{
   T_Reset();
   F.DefineAgora(D'2026.10.06 15:00:00');
   Leitura_Atualiza(true);
   Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t84");
   ulong s = F.TicketPend(MG(R_GB), ORDER_TYPE_SELL_STOP);
   F.Dispara(F.TicketPend(MG(R_GB), ORDER_TYPE_BUY_LIMIT));
   F.CancelaPorFora(s, ORDER_STATE_EXPIRED);
   F.DefineAgora(D'2026.10.07 08:56:00');
   T_Reinicia();
   F.m_bid = 118000; F.m_ask = 118005;              // gap contra: o nivel de emergencia ja' foi atravessado
   Mae_Reconcilia(); F.Avanca(3); Mae_Reconcilia();
   bool sem_s = F.ContaPend() == 0;
   F.DefineAgora(D'2026.10.07 09:00:01');
   F.m_rc = TRADE_RETCODE_MARKET_CLOSED;
   F.Roteiro(FM_RETCODE);                           // leilao prorrogado: a saida e' recusada
   Mae_Reconcilia();
   bool retenta = mzF[R_GB] == 1 && mzRecProx[R_GB][RC_X] > F.Agora() && mzRecN[R_GB][RC_X] == 0;
   F.Avanca(6);
   Mae_Reconcilia();
   Ok("T84 ficha da noite: nivel atravessado na pre-abertura -> nenhuma S; saida recusada no leilao retentada; zerada depois",
      sem_s && retenta && mzF[R_GB] == 0);
}

void T85_Simultaneas(void)
{
   T_Reset();
   F.Roteiro(FM_NORMAL); F.Roteiro(FM_DONE_SEM_DEAL);   // a E a mercado do C1 executa; o deal chega depois
   Ficha_EntraMercado(R_C1, 1, 119000, 0, "t85c1");
   int r = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t85gb");   // mesmo segundo, cruzada aberta
   bool barrada = r == FICHA_BLOQUEADA && F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 0;
   F.MostraOcultos();
   Mae_Reconcilia();
   int r2 = Ficha_EntraLimite(R_GB, 1, 119900, 118700, ORDER_TIME_DAY, 0, 0, "t85gb2");
   Ok("T85 entradas no mesmo segundo com cruzada transitoria: a segunda espera (sem S nem E soltas) e entra depois",
      barrada && r2 == FICHA_ENVIADA && mzF[R_C1] == 1);
}

void T86_OnTimer(void)
{
   T_Reset();
   ulong s = EntraEnche(R_GB, 1, 119900, 118700);
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   mzPasso = 12;
   Mae_OnTimer(); F.Avanca(3); Mae_OnTimer();       // timer do maestro reconcilia e recria a S
   mzPasso = 0;
   Ok("T86 OnTimer do maestro: reconciliacao por segundo recria a S", F.ContaPendTipo(MG(R_GB), ORDER_TYPE_SELL_STOP) == 1);
}

//+------------------------------------------------------------------+
int OnInit()
{
   Print("WinMaestro_Teste: inicio");
   T01_02(); T03(); T04(); T05(); T06(); T07(); T08(); T09(); T10(); T11(); T12(); T13();
   T14(); T15(); T16(); T17(); T18(); T19(); T20(); T21(); T22(); T23(); T24(); T25(); T26();
   T27_C1(); T28_C1(); T29_C2(); T30_C2(); T31_A1(); T32_A2(); T33_A3(); T34_A4(); T36_A6();
   T37_M1(); T38_M2(); T39_M3(); T40_M4(); T41_M5(); T42_M6(); T43_M7(); T44_M9(); T45_M10();
   T46_B1(); T47_B2(); T48_B3(); T49_B4(); T50_B5(); T51_B6(); T52_B7(); T53_B8(); T54_B10(); T55_C2ep();
   T56_Partida(); T57_Memoria(); T58_OnTrade(); T59_Conexao(); T60_Colisao(); T61_CorteConta();
   T62_A1(); T63_A2(); T64_A3(); T65_A4(); T66_M1(); T67_M2(); T68_M3(); T69_M5(); T70_M6(); T71_M7(); T72_M8();
   T73_B1(); T74_B2(); T75_B3(); T76_B4(); T77_B5(); T78_B7(); T79_B8(); T80_B9(); T81_DM(); T82_RE(); T83_Partida();
   T84_Noite(); T85_Simultaneas(); T86_OnTimer();
   PrintFormat("WinMaestro_Teste: %d PASSOU, %d FALHOU", gPassou, gFalhou);
   if(F != NULL) { delete F; F = NULL; }
   mzCorr = NULL;
   Log_Fecha();
   ExpertRemove();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { }
void OnTick() { }
//+------------------------------------------------------------------+
