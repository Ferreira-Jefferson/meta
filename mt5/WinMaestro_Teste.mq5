//+------------------------------------------------------------------+
//| WinMaestro_Teste.mq5                                             |
//| Testes unitarios do nucleo v2.02 do WinMaestro sobre a corretora |
//| FALSA (spec O15, sec. 12; desenho v2.2 sec. 9 "R3 sec. 6").      |
//|  - um teste por linha da tabela (sec. 4.2), da intencao efetiva  |
//|    (sec. 4.1), do casamento (sec. 2.1) e do motor de corte (5);  |
//|  - um teste por cenario (a)-(n) da sec. 8;                       |
//|  - testes dos adaptadores dos 5 modulos.                         |
//| Cada teste roda o codigo do MAESTRO (o mesmo .mqh do EA real) e  |
//| confere o que ficou na corretora falsa e no mapa. A falsa so'    |
//| registra o que a "bolsa" fez; nao decide nada.                   |
//| Nao ha' caminho para a corretora real: com WINMAESTRO_TESTE a    |
//| classe CCorretoraReal nem e' compilada, os modulos nao tem       |
//| CTrade e o painel/botao ficam desligados.                        |
//| Roda tudo no OnInit, imprime PASSOU/FALHOU por caso e o placar,  |
//| e sai (ExpertRemove). Grava so' em MQL5/Files/WinMaestro_unit/ e |
//| em variaveis globais com o prefixo WinMaestroTeste (apagadas).   |
//| Anexe num grafico DIFERENTE do que roda o WinMaestro, de um      |
//| simbolo com cotacao (ex.: o WIN vigente).                        |
//+------------------------------------------------------------------+
#property copyright "WinMaestro"
#property version   "2.02"
#property description "Testes unitarios do WinMaestro v2.02 (corretora falsa)"
#property strict

#define WINMAESTRO_TESTE
#include "WinMaestro\Inputs.mqh"
#include "WinMaestro\CorretoraFalsa.mqh"
#include "WinMaestro\Partida.mqh"
#include "WinMaestro\WinGapBarra1.mqh"
#include "WinMaestro\WinCincoMedias.mqh"
#include "WinMaestro\WinDeslocamentoMatinal.mqh"
#include "WinMaestro\WinRetanguloEma34.mqh"
#include "WinMaestro\Win_c1.mqh"

input bool Teste_Verboso = false;   // imprime o log do maestro no Diario durante os testes

CCorretoraFalsa *F = NULL;
int    gPassou = 0;
int    gFalhou = 0;
string gFalhas = "";
string gLogPasta = "";
bool   gReal = false;               // ganchos -> modulos reais (testes dos adaptadores)
//--- modulo de teste (stub): escreve a intencao pedida pelo teste no Tick e registra os eventos
Intencao gStub[NROBOS];
bool     gStubPede[NROBOS];
int      gStubInit[NROBOS];
double   gStubStop[NROBOS];
int      gStubZerar[NROBOS];
int      gEvN[NROBOS];
int      gEvUlt[NROBOS];
long     gEvId[NROBOS];
double   gEvPreco[NROBOS];
string   gEvMot[NROBOS];
int      gTicks[NROBOS];

//+------------------------------------------------------------------+
//| Ganchos do nucleo (no EA real: os 5 modulos)                     |
//+------------------------------------------------------------------+
int Robo_Init(const int r, const VistaRobo &v)
{
   if(gReal)
      switch(r)
      {
         case R_GB: return WGB1::Init(v);
         case R_CM: return WCM::Init(v);
         case R_DM: return WDM::Init(v);
         case R_RE: return WRE::Init(v);
         case R_C1: return WC1::Init(v);
      }
   return gStubInit[r];
}
void Robo_Tick(const int r, const VistaRobo &v, Intencao &i)
{
   gTicks[r]++;
   if(gStubPede[r]) { i = gStub[r]; gStubPede[r] = false; }
}
void Robo_Evento(const int r, const SEvento &e, const VistaRobo &v, Intencao &i)
{
   gEvN[r]++; gEvUlt[r] = e.ev; gEvId[r] = e.id_entrada; gEvPreco[r] = e.preco; gEvMot[r] = e.motivo;
}
double Robo_StopRegra(const int r, const int lado)
{
   if(gReal)
      switch(r)
      {
         case R_GB: return WGB1::StopRegra(lado);
         case R_CM: return WCM::StopRegra(lado);
         case R_DM: return WDM::StopRegra(lado);
         case R_RE: return WRE::StopRegra(lado);
         case R_C1: return WC1::StopRegra(lado);
      }
   return gStubStop[r];
}
int Robo_MinutoZerar(const int r, const datetime dia)
{
   if(gReal)
      switch(r)
      {
         case R_GB: return WGB1::MinutoZerarRobo(dia);
         case R_CM: return WCM::MinutoZerarRobo(dia);
         case R_DM: return WDM::MinutoZerarRobo(dia);
         case R_RE: return WRE::MinutoZerarRobo(dia);
         case R_C1: return WC1::MinutoZerarRobo(dia);
      }
   return gStubZerar[r];
}
void Robo_Exporta(const int r)
{
   if(!mzInit[r]) Car_CopiaPrefixo(mzNome[r] + ".");
}

//+------------------------------------------------------------------+
//| Harness                                                          |
//+------------------------------------------------------------------+
void Ok(const string nome, const bool cond)
{
   if(cond) { gPassou++; Print("PASSOU  ", nome); }
   else     { gFalhou++; gFalhas += "\n   " + nome; Print("FALHOU  ", nome); }
}

void T_Stubs(void)
{
   gReal = false;
   int zr[NROBOS] = {18 * 60 + 20, 18 * 60 + 24, 18 * 60 + 20, 17 * 60, 17 * 60 + 50};
   for(int r = 0; r < NROBOS; r++)
   {
      Int_Nada(gStub[r], ""); gStubPede[r] = false; gStubInit[r] = INIT_SUCCEEDED; gStubStop[r] = 0.0; gStubZerar[r] = zr[r];
      gEvN[r] = 0; gEvUlt[r] = 0; gEvId[r] = 0; gEvPreco[r] = 0.0; gEvMot[r] = ""; gTicks[r] = 0;
   }
}

// corretora nova (sem o maestro ainda): o teste pode mexer nela antes de ligar
void T_Prepara(const datetime t)
{
   if(F != NULL) delete F;
   F = new CCorretoraFalsa();
   mzCorr = F;
   F.DefineAgora(t);
   FolderClean("WinMaestro_unit", 0);
   FolderCreate("WinMaestro_unit");
   FolderCreate("WinMaestro_unit\\logs");
   T_Stubs();
}

// "OnInit" do maestro sobre a corretora atual (P17: tudo reinicializado)
void T_Base(void)
{
   Mae_Reseta();
   mzSemTrava = true; mzTela = false; mzLogImprime = Teste_Verboso; mzLogAlert = false;
   mzTravaPrefixo = "WinMaestroTeste"; mzTravaSoMarca = true; mzTravaRelogio = 0;
   Log_Pasta(gLogPasta);
   mzMemPasta = "WinMaestro_unit\\";
   Mae_Partida();
}

// liga com memoria valida (vazia) e espera a base firmar (CONEXAO 10 s)
void T_Liga(void)
{
   T_Base();
   Mae_GravaMemoria(true);
   Mae_CarregaMemoria();
   Espera(11);
}
void T_Inicia(const datetime t) { T_Prepara(t); T_Liga(); }
// reinicio do EA sobre a mesma corretora, com a memoria gravada
void T_Reinicia(void) { Mae_Fim(REASON_PARAMETERS); T_Base(); }
void T_ApagaMemoria(void) { FileDelete("WinMaestro_unit\\estado.txt"); FileDelete("WinMaestro_unit\\estado.bak"); }

void Passa(const int ms) { F.AvancaMs(ms); Mae_Ciclo(); }
void Espera(const int seg) { for(int k = 0; k < seg * 4; k++) Passa(250); }
void Um(void) { F.AvancaMs(250); Mae_CicloUm(); }   // um ciclo so', sem as RODADAS

long   MG(const int r)                 { return mzMagic[r]; }
int    TLim(const int lado)            { return lado > 0 ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT; }
int    TStop(const int lado)           { return lado > 0 ? ORDER_TYPE_SELL_STOP : ORDER_TYPE_BUY_STOP; }   // a S que protege `lado`
ulong  TK(const int r, const int tipo) { return F.TicketPend(MG(r), tipo); }
int    NP(const int r, const int tipo) { return F.ContaPendTipo(MG(r), tipo); }
double PP(const ulong tk)              { return F.PrecoPend(tk); }
bool   Vivo(const ulong tk)            { return tk != 0 && F.PendIdx(tk) >= 0; }
int    EH(const ulong tk)              { return F.EstadoHist(tk); }
int    ND(void)                        { return ArraySize(F.m_deal); }
long   SetupPend(const ulong tk)       { int i = F.PendIdx(tk); return i < 0 ? -1 : F.m_pend[i].setup_msc; }
long   DoneHist(const ulong tk)        { int i = F.HistIdx(tk); return i < 0 ? -1 : F.m_hist[i].done_msc; }
long   DealMagic(const int k)          { return (k >= 0 && k < ND()) ? F.m_deal[k].magic : -1; }
int    DealTipo(const int k)           { return (k >= 0 && k < ND()) ? F.m_deal[k].tipo : -1; }
double DealVol(const int k)            { return (k >= 0 && k < ND()) ? F.m_deal[k].vol : -1.0; }
long   DealMsc(const int k)            { return (k >= 0 && k < ND()) ? F.m_deal[k].time_msc : -1; }
int    Linha(const int r, const int papel) { for(int i = ArraySize(mzL) - 1; i >= 0; i--) if(mzL[i].robo == r && mzL[i].papel == papel) return i; return -1; }
// ultima linha do robo com o papel E o motivo (K/M/S/A/E: a linha da tabela que pediu, ex. "X3", "L3"; X: I1/I2/I3/MOD)
int    LinhaMot(const int r, const int papel, const string mot) { for(int i = ArraySize(mzL) - 1; i >= 0; i--) if(mzL[i].robo == r && mzL[i].papel == papel && mzL[i].motivo == mot) return i; return -1; }
int    LDesf(const int i)              { return (i >= 0 && i < ArraySize(mzL)) ? mzL[i].desfecho : -1; }
ulong  LTk(const int i)                { return (i >= 0 && i < ArraySize(mzL)) ? mzL[i].ticket : 0; }
long   LId(const int i)                { return (i >= 0 && i < ArraySize(mzL)) ? mzL[i].id : -1; }
long   LIde(const int i)               { return (i >= 0 && i < ArraySize(mzL)) ? mzL[i].id_entrada : -1; }
string LProva(const int i)             { return (i >= 0 && i < ArraySize(mzL)) ? mzL[i].prova : ""; }
string LMot(const int i)               { return (i >= 0 && i < ArraySize(mzL)) ? mzL[i].motivo : ""; }
uint   LReq(const int i)               { return (i >= 0 && i < ArraySize(mzL)) ? mzL[i].request_id : 0; }
int    Desf(const int r, const int papel) { return LDesf(Linha(r, papel)); }
int    NLinhas(const int r, const int papel) { int c = 0; for(int i = 0; i < ArraySize(mzL); i++) if(mzL[i].robo == r && mzL[i].papel == papel) c++; return c; }
int    NRecusadas(const int r, const int papel) { int c = 0; for(int i = 0; i < ArraySize(mzL); i++) if(mzL[i].robo == r && mzL[i].papel == papel && mzL[i].desfecho == D_RECUSADA) c++; return c; }
// houve (viva ou no historico) ordem deste magic/tipo/preco?
bool   Existiu(const long magic, const int tipo, const double preco)
{
   for(int i = 0; i < ArraySize(F.m_pend); i++) if(F.m_pend[i].magic == magic && F.m_pend[i].tipo == tipo && MathAbs(F.m_pend[i].preco - preco) < 0.5) return true;
   for(int i = 0; i < ArraySize(F.m_hist); i++) if(F.m_hist[i].magic == magic && F.m_hist[i].tipo == tipo && MathAbs(F.m_hist[i].preco - preco) < 0.5) return true;
   return false;
}
bool   ExistiuTipo(const long magic, const int tipo)
{
   for(int i = 0; i < ArraySize(F.m_pend); i++) if(F.m_pend[i].magic == magic && F.m_pend[i].tipo == tipo) return true;
   for(int i = 0; i < ArraySize(F.m_hist); i++) if(F.m_hist[i].magic == magic && F.m_hist[i].tipo == tipo) return true;
   return false;
}

void Pede(const int r, const Intencao &x) { gStub[r] = x; gStubPede[r] = true; }
long Entrar(const int r, const int lado, const double limite, const double stop, const datetime expira = 0)
{
   Intencao x; long id = Ficha_NovoId(r);
   Int_Entrar(x, id, lado, limite, stop, expira, "teste");
   Pede(r, x);
   return id;
}
void Manter(const int r, const double stop, const double alvo) { Intencao x; Int_Manter(x, stop, alvo, "teste"); Pede(r, x); }
void Sair(const int r) { Intencao x; Int_Sair(x, "teste"); Pede(r, x); }
void Nada(const int r) { Intencao x; Int_Nada(x, "teste"); Pede(r, x); }

// Abre uma ficha LEGITIMA: ENTRAR -> S -> E limite; a E enche no preco dela. Devolve o ticket da S.
ulong Abre(const int r, const int lado, const double limite, const double stop)
{
   Entrar(r, lado, limite, stop);
   Passa(250);
   ulong e = TK(r, TLim(lado));
   if(e != 0) F.Dispara(e);
   Passa(250);
   return TK(r, TStop(lado));
}

// Entrega ao OnTradeTransaction DO MAESTRO as transacoes que a falsa acumulou (como o terminal faria). Cada uma roda o ciclo.
void Entrega(void)
{
   int n = ArraySize(F.m_tq_t);
   MqlTradeTransaction t[]; MqlTradeRequest q[]; MqlTradeResult r[];
   ArrayResize(t, n); ArrayResize(q, n); ArrayResize(r, n);
   for(int k = 0; k < n; k++) { t[k] = F.m_tq_t[k]; q[k] = F.m_tq_q[k]; r[k] = F.m_tq_r[k]; }
   F.LimpaTrans();
   for(int k = 0; k < n; k++) Mae_OnTradeTransaction(t[k], q[k], r[k]);
}
datetime ZMin(const datetime a, const datetime b) { return a < b ? a : b; }

void Trava_LimpaGV(void)
{
   if(mzTravaNome != "") GlobalVariableDel(mzTravaNome);
   if(mzHbNome != "") GlobalVariableDel(mzHbNome);
}

//+------------------------------------------------------------------+
//| Tabela (sec. 4.2): P1 P2 P3 X1 X2 X3 L1 L2 L3 L4 A1 A2 E1 Z      |
//+------------------------------------------------------------------+
void T_P1_E1(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   long id = Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   ulong s = TK(R_GB, ORDER_TYPE_SELL_STOP), e = TK(R_GB, ORDER_TYPE_BUY_LIMIT);
   int ls = Linha(R_GB, P_S), le = Linha(R_GB, P_E);
   Ok("P1/E1: ENTRAR -> a S sai ANTES da E (volume 1, nivel pedido); E1 so' com a S VIVA; id da entrada consumido",
      s != 0 && e != 0 && SetupPend(s) < SetupPend(e) && PP(s) == 118700.0 && PP(e) == 119900.0 &&
      LId(ls) < LId(le) && LIde(ls) == id && LIde(le) == id && LDesf(ls) == D_VIVA && LDesf(le) == D_VIVA && Est_Consumido(R_GB, id));
}

void T_P1_Recria(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);              // o dono (ou a corretora) cancela a S
   Passa(250);
   ulong s2 = TK(R_GB, ORDER_TYPE_SELL_STOP);
   Ok("P1: ficha +1 sem S -> S nova no nivel pedido (S FALTANDO)",
      s != 0 && s2 != 0 && s2 != s && PP(s2) == 118700.0 && mzEst[R_GB].f == 1 && mzEst[R_GB].sit == SIT_LEGITIMA);
}

void T_P1_SemHistorico(void)
{
   // isola a guarda okR: a S some com o historico lido (NAO_EXECUTADA), a S nova e' recusada (RECUSADA: nada pendente) e
   // so' entao o historico falha. Vencida a em_espera, so' o okR (sem lado inequivoco) segura o P1.
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL_STOP;
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Passa(250);
   bool recusada = NRecusadas(R_GB, P_S) == 1 && !mzEst[R_GB].pendS;
   F.m_recusa_magic = 0;
   F.m_hist_falha = true;
   int env = F.m_envios;
   Espera(8);
   bool parado = NP(R_GB, ORDER_TYPE_SELL_STOP) == 0 && F.m_envios == env && !mzEst[R_GB].confiavel && !mzEst[R_GB].inequivoco &&
                 !mzEst[R_GB].pendS && !mzEst[R_GB].pendX && !mzEst[R_GB].pendA;
   Ok("P1 (R): S faltando, nada pendente, em_espera vencida, historico ilegivel (sem lado inequivoco) -> nenhuma S nova", recusada && parado);
   F.m_hist_falha = false;
   Espera(1);
   Ok("P1 (R): historico de volta -> a S volta", NP(R_GB, ORDER_TYPE_SELL_STOP) == 1);
}

void T_P1_Inequivoco(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);     // posicao manual que o historico ainda nao mostra: Delta +1
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Passa(250);
   ulong s2 = TK(R_GB, ORDER_TYPE_SELL_STOP);
   Ok("P1 (R): RESTRITO com lado inequivoco (provado, sinal da liquida = sinal da ficha) -> a S e' criada assim mesmo",
      !mzEst[R_GB].confiavel && mzEst[R_GB].inequivoco && s2 != 0 && PP(s2) == 118700.0 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1);
}

void T_P1_Retenta(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.Roteiro(FM_RECUSA);
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   int env1 = F.m_envios;
   Espera(4);
   int env2 = F.m_envios;
   Espera(2);
   Ok("P1: S recusada -> em_espera ate' RETENTA (nada em 4 s), depois a S e a E saem",
      env1 == 1 && env2 == 1 && NRecusadas(R_GB, P_S) == 1 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1);
}

void T_P1_ForaDaJanela(void)
{
   // a janela do historico comeca em 08:50 (inicio 09:00 - 10 min): o deal das 08:50:11 esta' dentro dela (A-3)
   T_Inicia(D'2026.10.07 08:50:00');
   F.DealPorFora(MG(R_GB), 1, 1.0, 120000.0);              // ficha do GB por ordem a mercado fora do mapa: TROCADA
   Espera(2);
   bool nada = F.ContaPend() == 0 && F.m_envios == 0 && mzEst[R_GB].sit == SIT_TROCADA;
   F.DefineAgora(D'2026.10.07 08:55:00');
   Espera(1);
   ulong s = TK(R_GB, ORDER_TYPE_SELL_STOP);
   Ok("P1: antes da pre-abertura nada sai; na pre-abertura a S (emergencia ref - 1.200, gravada) e nenhuma ordem a mercado",
      nada && s != 0 && PP(s) == 118800.0 && mzEmerg[R_GB] == 118800.0 && mzNivS[R_GB] == 118800.0 && ND() == 1);
   F.DefineAgora(D'2026.10.07 09:00:00');
   Espera(1);
   Ok("I2/X3: no continuo a trocada e' corrigida a mercado com o magic do robo; L3 cancela a S depois",
      ND() == 2 && DealTipo(1) == DEAL_TYPE_SELL && DealMagic(1) == MG(R_GB) && EH(s) == ORDER_STATE_CANCELED && DoneHist(s) > DealMsc(1) && mzEst[R_GB].f == 0);
}

void T_P2(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   ulong x = F.PendPorFora(MG(R_GB), ORDER_TYPE_BUY_STOP, 121000);   // S do lado que AUMENTA |f|
   Passa(250);
   Ok("P2: S do lado que aumenta |f| -> cancelada; a S certa fica", EH(x) == ORDER_STATE_CANCELED && Vivo(s));
   ulong y = F.PendPorFora(MG(R_GB), ORDER_TYPE_SELL_STOP, 118000);  // cobertura 2 > |f| 1
   Passa(250);
   Ok("P2: cobertura > |f| -> cancela a menos protetora (118000), fica a de 118700", EH(y) == ORDER_STATE_CANCELED && Vivo(s) && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1);
}

void T_P3(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Manter(R_GB, 119000, 0);
   Passa(250);
   int lm = Linha(R_GB, P_M);
   Ok("P3: MANTER com stop novo -> MOVE_S (OrderModify, mesmo ticket); M EXECUTADA pelo preco novo",
      Vivo(s) && PP(s) == 119000.0 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && LDesf(lm) == D_EXECUTADA);
}

void T_Nivel_Emergencia(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Manter(R_GB, 120100, 0);                    // nivel pedido ja' atravessado (acima do bid)
   Passa(250);
   bool sViva = Vivo(s) && PP(s) == 118700.0;  // cadeia: intencao/memoria invalidas -> vale a S viva
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Passa(250);
   ulong e = TK(R_GB, ORDER_TYPE_SELL_STOP);
   bool emerg = e != 0 && PP(e) == 118800.0 && mzEmerg[R_GB] == 118800.0;
   F.Precos(119500, 119505);
   Espera(2);
   bool parada = PP(e) == 118800.0;            // a emergencia nao persegue o preco
   F.Precos(120400, 120405);
   Espera(1);
   Ok("sec. 4.3: cadeia intencao -> memoria -> S viva -> regra -> emergencia (uma vez, gravada); nao persegue o preco; sai dela so' quando o nivel pedido fica valido",
      sViva && emerg && parada && PP(e) == 120100.0);
}

void T_Nivel_Referencia(void)
{
   T_Prepara(D'2026.10.07 10:00:00');
   F.m_bid = 0.0; F.m_ask = 0.0; F.m_last = 0.0;      // livro invalido e nenhum last visto
   F.DealPorFora(MG(R_GB), 1, 1.0, 119500.0);
   T_Liga();
   bool porFicha = Existiu(MG(R_GB), ORDER_TYPE_SELL_STOP, 118300.0);
   T_Prepara(D'2026.10.07 10:00:00');
   F.m_bid = 0.0; F.m_ask = 0.0; F.m_last = 119000.0; // livro invalido, last valido
   F.DealPorFora(MG(R_GB), 1, 1.0, 119500.0);
   T_Liga();
   bool porLast = Existiu(MG(R_GB), ORDER_TYPE_SELL_STOP, 117800.0);
   Ok("sec. 1.1: referencia sem livro valido = ultimo last; sem last = preco da ficha (emergencia 117800 / 118300)", porFicha && porLast);
}

void T_A1_X1_X3_L3(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong a = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   Ok("A1: MANTER com alvo, LEGITIMA, continuo -> A limite oposta no alvo", a != 0 && PP(a) == 121000.0 && Vivo(s));
   Sair(R_RE);
   Passa(250);
   int nd = ND();
   Ok("X1 -> X3 -> L3: SAIR cancela o A (a S fica), manda a X com o magic do robo e so' depois cancela a S",
      EH(a) == ORDER_STATE_CANCELED && nd == 2 && DealMagic(1) == MG(R_RE) && DealTipo(1) == DEAL_TYPE_SELL && DealVol(1) == 1.0 &&
      DoneHist(a) < DealMsc(1) && EH(s) == ORDER_STATE_CANCELED && DoneHist(s) > DealMsc(1) && mzEst[R_RE].f == 0);
}

void T_X2(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_DM, 1, 119800, 118600);
   Passa(250);
   ulong e = TK(R_DM, ORDER_TYPE_BUY_LIMIT), s = TK(R_DM, ORDER_TYPE_SELL_STOP);
   Sair(R_DM);
   Passa(250);
   Ok("X2: SAIR com E viva e ficha 0 -> K da E; a S so' depois (L3); nenhuma ordem a mercado",
      e != 0 && EH(e) == ORDER_STATE_CANCELED && EH(s) == ORDER_STATE_CANCELED && DoneHist(e) < DoneHist(s) && ND() == 0 && gEvUlt[R_DM] == EV_ENTRADA_CANCELADA);
}

void T_X3_SCruzada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_por_preco = true; F.m_stop_falha = true;   // o mercado atravessa a S e ela NAO executa (stop que ficou para tras)
   F.Move(118600, 118605);
   Sair(R_GB);
   int env = F.m_envios;
   Espera(2);
   bool espera = F.m_envios == env && Vivo(s) && PP(s) == 118700.0 && ND() == 1;
   Espera(30);
   int lk = LinhaMot(R_GB, P_K, "X3");                   // no mesmo ciclo L3 manda outro K (o da S de emergencia): procura o da X3 (B2-8)
   Ok("X3/M-5: S em nivel ja' cruzado -> nada sai enquanto ela pode executar (sem 2a saida; P3 nao mexe); viva ha' 30 s sem executar -> K dela (X3), S valida e a X sai",
      espera && EH(s) == ORDER_STATE_CANCELED && lk >= 0 && LMot(lk) == "X3" && NLinhas(R_GB, P_X) == 1 && ND() == 2 &&
      DealTipo(1) == DEAL_TYPE_SELL && DealMagic(1) == MG(R_GB) && mzEst[R_GB].f == 0);
}

void T_X3_Recusada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.Roteiro(FM_RECUSA);
   Sair(R_GB);
   Passa(250);
   int env1 = F.m_envios;
   bool sFica = Vivo(s);
   Espera(4);
   int env2 = F.m_envios;
   Espera(2);
   Ok("X3: saida recusada -> a S continua; em_espera 5 s; depois a X sai e a S e' cancelada",
      sFica && env1 == env2 && NRecusadas(R_GB, P_X) == 1 && ND() == 2 && EH(s) == ORDER_STATE_CANCELED);
}

void T_L1(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   long id = Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   ulong e = TK(R_GB, ORDER_TYPE_BUY_LIMIT), s = TK(R_GB, ORDER_TYPE_SELL_STOP);
   Nada(R_GB);
   Passa(250);
   Ok("L1: intencao NADA com E viva -> K da E; ENTRADA_CANCELADA pela prova; a S so' depois (L3)",
      EH(e) == ORDER_STATE_CANCELED && EH(s) == ORDER_STATE_CANCELED && DoneHist(e) < DoneHist(s) && gEvUlt[R_GB] == EV_ENTRADA_CANCELADA && gEvId[R_GB] == id);
}

void T_L2(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong a = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   Manter(R_RE, 118700, 0);
   Passa(250);
   Ok("L2: MANTER sem alvo -> K do A; a S fica; nada a mercado", a != 0 && EH(a) == ORDER_STATE_CANCELED && Vivo(s) && ND() == 1);
}

void T_L3_OCO(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong a = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   F.Dispara(a);                               // o alvo enche
   Passa(250);
   Ok("L3: ficha 0 provada, nada pendente -> cancela a S (OCO)", EH(s) == ORDER_STATE_CANCELED && ND() == 2 && mzEst[R_RE].f == 0);
}

void T_L3_Restrito(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong a = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   ulong x = F.PendPorFora(MG(R_CM), ORDER_TYPE_SELL_STOP, 118000);   // S do CM sem ficha e sem prova
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);                  // Delta: todos RESTRITOS
   F.Dispara(a);
   Passa(250);
   Ok("L3 (R): RESTRITO com prova (a irma A do episodio LEGITIMA executou) -> cancela a S; sem prova (S do CM) -> nao cancela",
      !mzEst[R_RE].confiavel && EH(s) == ORDER_STATE_CANCELED && Vivo(x));
   F.MostraOcultos();
   Passa(250);
   Ok("L3: confiavel de novo -> a S do CM sem ficha e' cancelada", mzEst[R_CM].confiavel && EH(x) == ORDER_STATE_CANCELED);
   // a outra prova: a E do episodio CANCELED sem nenhum deal
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_CM, 1, 119800, 118600);
   Passa(250);
   ulong ec = TK(R_CM, ORDER_TYPE_BUY_LIMIT), sc = TK(R_CM, ORDER_TYPE_SELL_STOP);
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);                  // Delta: todos RESTRITOS
   F.CancelaPorFora(ec, ORDER_STATE_CANCELED);
   Passa(250);
   Ok("L3 (R): RESTRITO com prova (a E do episodio CANCELED e nenhum deal no episodio) -> cancela a S",
      ec != 0 && !mzEst[R_CM].confiavel && EH(sc) == ORDER_STATE_CANCELED);
}

void T_L4(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong x = F.PendPorFora(MG(R_CM), ORDER_TYPE_BUY_LIMIT, 119000);
   Passa(250);
   Ok("L4: limite com o magic do robo fora do mapa -> cancelada", EH(x) == ORDER_STATE_CANCELED);
}

void T_A2(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong a = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   Manter(R_RE, 118700, 120800);
   Passa(250);
   Ok("A2: alvo novo -> MOVE_A (mesmo ticket, preco novo)", a != 0 && Vivo(a) && PP(a) == 120800.0 && NP(R_RE, ORDER_TYPE_SELL_LIMIT) == 1);
}

void T_E1_Consumido(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   long id = Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   F.Dispara(TK(R_GB, ORDER_TYPE_BUY_LIMIT));
   Passa(250);
   F.Dispara(TK(R_GB, ORDER_TYPE_SELL_STOP));  // o stop executa: ficha 0
   Passa(250);
   int env = F.m_envios;
   Intencao x; Int_Entrar(x, id, 1, 119900, 118700, 0, "mesmo id");
   Pede(R_GB, x);
   Espera(2);
   bool consumido = F.m_envios == env && mzEst[R_GB].f == 0 && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 0;
   Entrar(R_GB, 1, 119900, 118700);            // controle: id novo, mesmo estado
   Espera(1);
   Ok("E1: ENTRAR com id_entrada ja' consumido -> nem S nem E; controle: um id novo entra", consumido && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1);
}

void T_E1_O2(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_CM, -1, 120100, 121300);
   Passa(250);
   bool cm = NP(R_CM, ORDER_TYPE_SELL_LIMIT) == 1;
   long id = Entrar(R_GB, 1, 120100, 118900);
   Passa(250);
   Passa(250);
   ulong sg = 0;
   for(int i = 0; i < ArraySize(F.m_hist); i++) if(F.m_hist[i].magic == MG(R_GB) && F.m_hist[i].tipo == ORDER_TYPE_SELL_STOP) sg = F.m_hist[i].ticket;
   Ok("E1/O2: E que cruzaria a limite oposta de outro robo -> ENTRADA_RECUSADA(autoneg), id consumido, nenhuma E; L3 cancela a S",
      cm && !ExistiuTipo(MG(R_GB), ORDER_TYPE_BUY_LIMIT) && gEvUlt[R_GB] == EV_ENTRADA_RECUSADA && gEvMot[R_GB] == "autoneg" &&
      Est_Consumido(R_GB, id) && sg != 0 && EH(sg) == ORDER_STATE_CANCELED);
}

void T_Z(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_GB, 1, 119900, 118700);
   int env = F.m_envios;
   Espera(5);
   bool z = F.m_envios == env;
   Manter(R_GB, 118700, 121000);               // controle: no mesmo estado, um alvo pedido sai (o nucleo envia)
   Passa(250);
   Ok("Z: estado estavel -> nenhuma ordem por 5 s; controle: um alvo pedido no mesmo estado sai (A1)",
      z && F.m_envios == env + 1 && NP(R_GB, ORDER_TYPE_SELL_LIMIT) == 1);
}

//+------------------------------------------------------------------+
//| Intencao efetiva (sec. 4.1) e prazos                             |
//+------------------------------------------------------------------+
void T_I1(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   gStubZerar[R_GB] = 20 * 60;                 // zeragem propria do robo depois do corte
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.DefineAgora(D'2026.10.07 18:19:59');
   Passa(250);
   bool antes = ND() == 1;
   F.DefineAgora(D'2026.10.07 18:20:00');
   Passa(250);
   int lx = Linha(R_GB, P_X);
   Ok("I1: em C (18:20) a ficha sai a mercado mesmo com o modulo pedindo MANTER; a origem e' I1 (o I3 nao e' quem age)",
      antes && ND() == 2 && DealTipo(1) == DEAL_TYPE_SELL && EH(s) == ORDER_STATE_CANCELED && LMot(lx) == "I1" && mzOrigemUlt[R_GB] == I_1);
}

void T_I2_Trocada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong a = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   F.Dispara(a); F.Dispara(s);                 // S e A executam (ficha -1 aberta pela S: TROCADA)
   Passa(250);
   bool sCompra = Existiu(MG(R_RE), ORDER_TYPE_BUY_STOP, 121205.0);
   Ok("I2: trocada -> S de compra na emergencia (ask + 1.200) e correcao a mercado com o magic do robo; a S sai depois",
      sCompra && ND() == 4 && DealTipo(3) == DEAL_TYPE_BUY && DealMagic(3) == MG(R_RE) && mzEst[R_RE].f == 0 && NP(R_RE, ORDER_TYPE_BUY_STOP) == 0);
}

void T_I2_Duplicada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_GB, 1, 119900, 118700);
   F.DealPorFora(MG(R_GB), 1, 1.0, 120005.0);   // segunda execucao: ficha +2
   Passa(250);
   Ok("I2: duplicada -> 2a S (volume 1) antes, correcao de 1 contrato, ficha +1 LEGITIMA com uma S so'",
      mzEst[R_GB].f == 1 && mzEst[R_GB].sit == SIT_LEGITIMA && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && ND() == 3 && DealVol(2) == 1.0 &&
      DealTipo(2) == DEAL_TYPE_SELL && !mzBloqBotao);
   Espera(5);
   F.DealPorFora(MG(R_GB), 1, 1.0, 120005.0);
   Espera(1);
   Ok("I2/decisao 1: a 2a correcao em 10 min executa (nunca trava) e liga o bloqueio com botao", mzEst[R_GB].f == 1 && ND() == 5 && mzBloqBotao);
}

void T_I3_Zeragem(void)
{
   T_Inicia(D'2026.10.07 16:59:00');
   Abre(R_RE, 1, 119900, 118700);
   F.DefineAgora(D'2026.10.07 16:59:59');
   Passa(250);
   bool antes = ND() == 1;
   F.DefineAgora(D'2026.10.07 17:00:00');
   Passa(250);
   Ok("I3: no horario de zeragem do robo (RE 17:00) a ficha sai", antes && ND() == 2 && mzEst[R_RE].f == 0);
}

void T_I3_SRecusada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL_STOP;   // so' as S do GB sao recusadas
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Espera(55);
   bool semX = ND() == 1 && NRecusadas(R_GB, P_S) >= 10;
   Espera(7);
   Ok("I3 (decisao m): S recusada com a ficha aberta por 60 s -> saida a mercado com o magic do robo; antes disso P1 retenta a cada 5 s",
      semX && ND() == 2 && DealMagic(1) == MG(R_GB) && DealTipo(1) == DEAL_TYPE_SELL && mzEst[R_GB].f == 0);
}

void T_I4(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_CM, -1, 120100, 121300);
   Passa(250);
   ulong e = TK(R_CM, ORDER_TYPE_SELL_LIMIT), s = TK(R_CM, ORDER_TYPE_BUY_STOP);
   Mae_Bloqueia("teste");
   Passa(250);
   bool cancelou = EH(e) == ORDER_STATE_CANCELED && EH(s) == ORDER_STATE_CANCELED && gEvUlt[R_CM] == EV_ENTRADA_CANCELADA;
   int env = F.m_envios;
   Entrar(R_CM, -1, 120100, 121300);
   Espera(2);
   bool barrada = F.m_envios == env && NP(R_CM, ORDER_TYPE_SELL_LIMIT) == 0;
   Mae_Desbloqueia();
   Entrar(R_CM, -1, 120100, 121300);
   Espera(1);
   Ok("I4/sec. 2.4: bloqueio -> E vivas canceladas (S depois) com ENTRADA_CANCELADA; entrada nova nao sai; desbloqueado, a mesma entrada sai",
      cancelou && barrada && NP(R_CM, ORDER_TYPE_SELL_LIMIT) == 1);
}

void T_I5(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_CM, -1, 120100, 121300);
   Passa(250);
   ulong e = TK(R_CM, ORDER_TYPE_SELL_LIMIT), s = TK(R_CM, ORDER_TYPE_BUY_STOP);
   int env = F.m_envios;
   gStubInit[R_CM] = INIT_FAILED;
   T_Reinicia();
   Espera(15);
   bool congelada = Vivo(e) && Vivo(s) && mzInitFalhou[R_CM] && F.m_envios == env && mzOrigemUlt[R_CM] == I_5;
   Entrar(R_GB, 1, 119900, 118700);            // controle: o GB (Init ok) entra no mesmo estado
   Espera(1);
   Ok("I5: modulo sem Init (Init falhou) -> CONGELADA: E viva e S mantidas, nada novo; controle: outro robo entra", congelada && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1);
}

void T_PrazoEntrar(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL_STOP;
   long id = Entrar(R_GB, 1, 119900, 118700);
   Espera(11);
   int env = F.m_envios;
   Espera(10);
   Ok("PRAZO_ENTRAR: ENTRAR que nao manda a E em 10 s -> ENTRADA_PERDIDA, id consumido, sem novas tentativas",
      gEvUlt[R_GB] == EV_ENTRADA_PERDIDA && gEvId[R_GB] == id && Est_Consumido(R_GB, id) && env >= 2 && env <= 3 && F.m_envios == env &&
      NRecusadas(R_GB, P_S) == env && !ExistiuTipo(MG(R_GB), ORDER_TYPE_BUY_LIMIT));
}

void T_PrazoSair(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL;      // as X do GB sao recusadas
   Sair(R_GB);
   Espera(62);
   int env = F.m_envios;
   Espera(10);
   Ok("PRAZO_SAIR: SAIR que nao executa em 60 s de ciclos confiaveis -> SAIDA_EXPIRADA; X3 para; a S protege",
      gEvUlt[R_GB] == EV_SAIDA_EXPIRADA && mzInt[R_GB].tipo == INT_MANTER && F.m_envios == env && Vivo(s) && NRecusadas(R_GB, P_X) >= 10 && mzEst[R_GB].f == 1);
}

//+------------------------------------------------------------------+
//| Casamento e desfechos (sec. 2.1)                                 |
//+------------------------------------------------------------------+
void T_C_RequestId(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.m_req_no_timeout = true;
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   F.Roteiro(FM_TIMEOUT_TK0_EXEC);
   F.LimpaTrans();
   Um();                                                   // P1: S com TIMEOUT e ticket 0 (a ordem ficou viva)
   int li = Linha(R_GB, P_S);
   bool tk0 = LTk(li) == 0 && LReq(li) != 0 && LDesf(li) == D_PENDENTE;
   ulong certo = TK(R_GB, ORDER_TYPE_SELL_STOP);
   ulong dup = F.PendPorFora(MG(R_GB), ORDER_TYPE_SELL_STOP, 118700);   // outra ordem identica aparece depois do envio
   Um();
   bool ambigua = LTk(li) == 0 && LDesf(li) == D_PENDENTE;
   Entrega();                                              // o terminal entrega a transacao REQUEST (request_id -> ticket) ao maestro
   Ok("sec. 2.1: ticket 0 com dois candidatos segue PENDENTE; a transacao REQUEST entregue ao OnTradeTransaction casa a linha com a ordem certa; P2 cancela a duplicada fora do mapa",
      tk0 && ambigua && certo != 0 && certo != dup && LTk(li) == certo && LDesf(li) == D_VIVA && EH(dup) == ORDER_STATE_CANCELED && Vivo(certo));
}

void T_C_HistFilled(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.Roteiro(FM_TIMEOUT_TK0_EXEC);
   Sair(R_GB);
   Passa(250);
   int lx = Linha(R_GB, P_X);
   Ok("sec. 2.1: X com ticket 0 casada pela ordem FILLED do historico (magic/tipo/volume/setup) -> EXECUTADA; S cancelada; nenhuma 2a X",
      LTk(lx) != 0 && LDesf(lx) == D_EXECUTADA && ND() == 2 && NLinhas(R_GB, P_X) == 1 && EH(s) == ORDER_STATE_CANCELED && mzEst[R_GB].f == 0);
}

void T_C_AusenciaTk0(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Espera(30);
   F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Sair(R_GB);
   Passa(250);
   int lx = Linha(R_GB, P_X);
   int env = F.m_envios;
   Espera(29);
   bool espera = LDesf(lx) == D_PENDENTE && F.m_envios == env && Vivo(s);
   Espera(8);
   Ok("sec. 2.1/decisao 3: X sem ticket ausente -> PENDENTE ate' 30 s (nada sai, a S fica); depois NAO_EXECUTADA, RETENTA e a X sai de novo",
      espera && LDesf(lx) == D_NAO_EXECUTADA && ND() == 2 && mzEst[R_GB].f == 0);
}

void T_C_AindaNaoListada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.Roteiro(FM_PEND_OCULTA);
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   int ls = Linha(R_GB, P_S);
   bool pend = LTk(ls) != 0 && LDesf(ls) == D_PENDENTE && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 0;
   F.MostraPend();
   Passa(250);
   Ok("sec. 2.1: ordem aceita que ainda nao esta' nas vivas fica PENDENTE (nao SUMIDA) e a E espera; listada -> VIVA e a E sai",
      pend && LDesf(ls) == D_VIVA && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1);
}

void T_C_Sumida(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Espera(30);
   F.CancelaPorFora(s, ORDER_STATE_CANCELED, true);       // some das vivas sem estado no historico
   Passa(250);
   int ls = Linha(R_GB, P_S);
   bool sumida = LDesf(ls) == D_SUMIDA && !mzEst[R_GB].provado;
   int env = F.m_envios;
   Espera(29);
   bool semS = F.m_envios == env;
   Espera(8);
   Ok("sec. 2.1/decisao C: VIVA que some sem estado final = SUMIDA (pendente, nada novo); 30 s depois NAO_EXECUTADA, RETENTA e a S volta",
      sumida && semS && LDesf(ls) == D_NAO_EXECUTADA && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1);
}

void T_C_DealVence(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Espera(30);
   F.Roteiro(FM_TUDO_OCULTO);                             // a X executa; historico e deal so' aparecem depois
   Sair(R_GB);
   Passa(250);
   int lx = Linha(R_GB, P_X);
   Espera(31);
   // com M-1 o Delta -1 (a X executou sem deal nem ordem visiveis) fica estavel junto com a prova da ausencia: a absorcao
   // virtual zera a ficha e nenhuma 2a X sai; a S fica (L3 nunca por absorcao virtual)
   bool nao = LDesf(lx) == D_NAO_EXECUTADA && NLinhas(R_GB, P_X) == 1 && Vivo(s) && mzEst[R_GB].f == 0 && mzEst[R_GB].abs_virtual;
   F.MostraOcultos();
   Passa(250);
   Ok("sec. 2.1: o deal sempre vence: NAO_EXECUTADA por ausencia que ganha deal -> EXECUTADA; nenhuma 2a X (absorcao virtual; a S fica ate' o deal)",
      nao && LDesf(lx) == D_EXECUTADA && ND() == 2 && NLinhas(R_GB, P_X) == 1 && mzEst[R_GB].f == 0 && EH(s) == ORDER_STATE_CANCELED);
}

void T_C_FilledSemDeal(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   Abre(R_CM, 1, 119800, 118600);
   F.Roteiro(FM_DONE_SEM_DEAL);
   Sair(R_GB);
   Passa(250);
   int lx = Linha(R_GB, P_X);
   Ok("sec. 2.1/2.2: FILLED sem deal = EXECUTADA; Delta_resto 0 pela linha: so' o robo dela fica RESTRITO, a S dele fica",
      LDesf(lx) == D_EXECUTADA && mzDeltaResto == 0 && mzEst[R_CM].confiavel && !mzEst[R_GB].confiavel && Vivo(sg));
   F.MostraOcultos();
   Passa(250);
   Ok("sec. 2.1: o deal chega -> ficha 0 e so' entao a S sai", mzEst[R_GB].f == 0 && mzEst[R_GB].confiavel && EH(sg) == ORDER_STATE_CANCELED);
}

void T_C_KExecutouAntes(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_DM, 1, 119800, 118600);
   Passa(250);
   ulong e = TK(R_DM, ORDER_TYPE_BUY_LIMIT), s = TK(R_DM, ORDER_TYPE_SELL_STOP);
   F.Roteiro(FM_TIMEOUT_TK0_NADA);                        // o K fica sem resposta
   Nada(R_DM);
   Passa(250);
   int lk = Linha(R_DM, P_K);
   bool kpend = LDesf(lk) == D_PENDENTE;
   F.Dispara(e);
   Passa(250);
   Ok("sec. 2.1 K: o alvo executou antes -> K NAO_EXECUTADA ('executou antes'), E EXECUTADA, ENTRADA_EXECUTADA ao modulo, a S protege",
      kpend && LDesf(lk) == D_NAO_EXECUTADA && StringFind(LProva(lk), "executou antes") >= 0 && Desf(R_DM, P_E) == D_EXECUTADA &&
      gEvUlt[R_DM] == EV_ENTRADA_EXECUTADA && Vivo(s) && mzEst[R_DM].f == 1);
}

void T_C_P4(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.Roteiro(FM_MODIFICA_TROCA);
   Manter(R_GB, 119000, 0);
   Passa(250);
   ulong s2 = TK(R_GB, ORDER_TYPE_SELL_STOP);
   int ls = Linha(R_GB, P_S), lm = Linha(R_GB, P_M);
   int env = F.m_envios;
   Espera(1);
   Ok("sec. 2.1 M/P4: OrderModify que troca o ticket -> a linha da S passa ao ticket novo; nenhuma S extra",
      s2 != 0 && s2 != s && PP(s2) == 119000.0 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && LTk(ls) == s2 && LDesf(ls) == D_VIVA &&
      LDesf(lm) == D_EXECUTADA && F.m_envios == env);
}

//+------------------------------------------------------------------+
//| Confianca (sec. 2.2)                                             |
//+------------------------------------------------------------------+
void T_DeltaVirtual(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong a = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   F.DealPorFora(0, -1, 1.0, 120000.0, false, true);      // zeragem manual que o historico ainda nao mostra
   Espera(2);
   bool restr = !mzEst[R_RE].confiavel && !mzDeltaEstavel && !mzBloqAuto;
   Espera(30);
   // absorcao virtual: ficha 0 virtual, bloqueio automatico (I4 -> NADA); L2 e L3 nunca agem por ela: A e S ficam
   bool virt = mzDeltaEstavel && mzBloqAuto && !mzBloqBotao && mzEst[R_RE].abs_virtual && mzEst[R_RE].confiavel && Vivo(s) && Vivo(a);
   F.MostraOcultos();
   Passa(250);
   Ok("sec. 2.2: Delta estavel 30 s -> deal externo virtual: absorve, bloqueio automatico (sem botao), S e A preservadas; o deal real absorve de verdade e cancela A e S",
      a != 0 && restr && virt && mzBloqBotao && EH(s) == ORDER_STATE_CANCELED && EH(a) == ORDER_STATE_CANCELED && mzEst[R_RE].f == 0);
}

void T_NaoClassificado(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.DealPorFora(0, -1, 1.0, 120000.0, false, true);
   F.m_deal_oculto[ArraySize(F.m_deal_oculto) - 1] = false;   // o deal aparece, a ordem ainda nao
   Espera(40);
   bool restr = mzNaoClassTotal == 1 && !mzEst[R_GB].confiavel && !mzEst[R_CM].confiavel && Vivo(s) && !mzBloqBotao && ArraySize(mzAbsVistas) == 0;
   F.MostraHist();
   Passa(250);
   Ok("sec. 1.2: deal sem ordem = nao classificado, sem prazo (todos RESTRITOS, S intactas); a ordem aparece -> externo, absorcao e bloqueio",
      restr && mzNaoClassTotal == 0 && mzBloqBotao && EH(s) == ORDER_STATE_CANCELED);
}

//+------------------------------------------------------------------+
//| Motor de corte (sec. 5)                                          |
//+------------------------------------------------------------------+
void T_K_Conta(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   Entrar(R_CM, -1, 120100, 121300);
   Passa(250);
   ulong ec = TK(R_CM, ORDER_TYPE_SELL_LIMIT), sc = TK(R_CM, ORDER_TYPE_BUY_STOP);
   F.DefineAgora(D'2026.10.07 18:22:00');
   Espera(1);
   int nd = ND();
   Ok("sec. 5.2: em C+2 cancela as limites, C_CONTA(|liquida|) com o magic MAESTRO, depois as S; encerramento sem absorcao nem bloqueio",
      EH(ec) == ORDER_STATE_CANCELED && nd == 2 && DealMagic(1) == MAGIC_MAESTRO && DealTipo(1) == DEAL_TYPE_SELL && DealVol(1) == 1.0 &&
      DoneHist(ec) < DealMsc(1) && DoneHist(sg) > DealMsc(1) && DoneHist(sc) > DealMsc(1) &&
      EH(sg) == ORDER_STATE_CANCELED && EH(sc) == ORDER_STATE_CANCELED && F.ContaPend() == 0 && F.m_liq == 0 && !mzBloqBotao &&
      ArraySize(mzAbsVistas) == 0 && mzEst[R_GB].f == 0 && !mzEpAberto[R_GB]);
}

void T_K_Recusa(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   F.m_recusa_magic = MAGIC_MAESTRO; F.m_recusa_tipo = ORDER_TYPE_SELL;
   F.DefineAgora(D'2026.10.07 18:22:00');
   Passa(250);
   int t1 = NLinhas(R_MAE, P_X);
   bool v1 = Vivo(sg);
   Espera(4);
   int t2 = NLinhas(R_MAE, P_X);
   bool v2 = Vivo(sg);
   Espera(2);
   int t3 = NLinhas(R_MAE, P_X);
   bool v3 = Vivo(sg);
   F.m_recusa_magic = 0;
   Espera(6);
   int nd = ND();
   Ok("sec. 5.2/RV2 N-6: C_CONTA recusado -> em_espera[MAESTRO] 5 s (sem rajada); a S fica viva a cada passo enquanto a liquida != 0 e sai depois do deal",
      t1 == 1 && t2 == 1 && t3 == 2 && v1 && v2 && v3 && F.m_liq == 0 && EH(sg) == ORDER_STATE_CANCELED && DoneHist(sg) > DealMsc(nd - 1));
}

void T_K_DepoisDeF(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   Entrar(R_CM, -1, 120100, 121300);
   Passa(250);
   ulong ec = TK(R_CM, ORDER_TYPE_SELL_LIMIT), sc = TK(R_CM, ORDER_TYPE_BUY_STOP);
   F.DefineAgora(D'2026.10.07 18:25:30');
   Espera(2);
   Ok("sec. 5.3: depois de F nenhuma ordem a mercado; E/A cancelados; S ficam com a liquida != 0",
      NLinhas(R_MAE, P_X) == 0 && ND() == 1 && EH(ec) == ORDER_STATE_CANCELED && Vivo(sg) && Vivo(sc));
}

void T_K_SemHistorico(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   F.m_hist_falha = true;
   F.DefineAgora(D'2026.10.07 18:22:00');
   Espera(1);
   Ok("sec. 5.2: o motor da conta age so' com a base (historico ilegivel): C_CONTA e depois a S", ND() == 2 && DealMagic(1) == MAGIC_MAESTRO && F.m_liq == 0 && EH(sg) == ORDER_STATE_CANCELED);
}

void T_K_MercadoRecente(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   Abre(R_GB, 1, 119900, 118700);
   F.DefineAgora(D'2026.10.07 18:21:50');
   F.Roteiro(FM_TIMEOUT_TK0_NADA);                       // I1: a X sai sem desfecho
   Passa(250);
   bool x = NLinhas(R_GB, P_X) == 1;
   F.DefineAgora(D'2026.10.07 18:22:00');
   Espera(19);
   bool espera = NLinhas(R_MAE, P_X) == 0;
   Espera(3);
   Ok("sec. 5.2: ordem a mercado PENDENTE com menos de 30 s segura o C_CONTA; depois dos 30 s ele sai", x && espera && NLinhas(R_MAE, P_X) == 1 && F.m_liq == 0);
}

//+------------------------------------------------------------------+
//| Trava (sec. 1.6)                                                 |
//+------------------------------------------------------------------+
void T_BaseTrava(void)
{
   Mae_Reseta();
   mzSemTrava = false; mzTela = false; mzLogImprime = Teste_Verboso; mzLogAlert = false;
   mzTravaPrefixo = "WinMaestroTeste"; mzTravaSoMarca = true;
   Log_Pasta(gLogPasta);
   mzMemPasta = "WinMaestro_unit\\";
}

void T_Trava_Parada(void)
{
   T_Prepara(D'2026.10.07 10:00:00');
   T_BaseTrava();
   mzTravaRelogio = 1000000;
   Trava_Nomes();
   GlobalVariableSet(mzTravaNome, 12345.0);
   GlobalVariableSet(mzHbNome, (double)mzTravaRelogio);
   Mae_Partida();
   bool inerte1 = !mzTravaMinha && !mzMemCarregada;
   mzTravaRelogio += 30;
   Mae_Ciclo();
   bool inerte2 = !mzTravaMinha && !mzMemCarregada && F.m_envios == 0 && !FileIsExist("WinMaestro_unit\\estado.txt");
   mzTravaRelogio += 31;
   Mae_Ciclo();
   Ok("sec. 1.6: trava de outro token com heartbeat recente -> inerte (nao grava memoria); heartbeat parado >= 60 s -> toma e carrega a memoria",
      inerte1 && inerte2 && mzTravaMinha && GlobalVariableGet(mzTravaNome) == mzToken && mzMemCarregada);
   Trava_LimpaGV();
}

void T_Trava_MesmoToken(void)
{
   T_Prepara(D'2026.10.07 10:00:00');
   T_BaseTrava();
   mzTravaRelogio = 1000000;
   Trava_Nomes();
   GlobalVariableSet(mzTravaNome, mzToken);              // o mesmo grafico (ChartID que sobrevive)
   GlobalVariableSet(mzHbNome, (double)mzTravaRelogio);
   Mae_Partida();
   Ok("sec. 1.6: trava com o meu token -> retoma na hora", mzTravaMinha && mzMemCarregada);
   Trava_LimpaGV();
}

void T_Trava_Avancando(void)
{
   T_Prepara(D'2026.10.07 10:00:00');
   T_BaseTrava();
   mzTravaRelogio = 1000000;
   Trava_Nomes();
   GlobalVariableSet(mzTravaNome, 777.0);
   GlobalVariableSet(mzHbNome, (double)mzTravaRelogio);
   Mae_Partida();
   bool aos30 = false;
   for(int k = 1; k <= 70; k++)
   {
      mzTravaRelogio += 1;
      GlobalVariableSet(mzHbNome, (double)mzTravaRelogio);   // a outra instancia segue viva
      Mae_Ciclo();
      if(k == 30) aos30 = !mzTravaRemoveu && !mzTravaMinha;
   }
   Ok("sec. 1.6/RV2 N-5: heartbeat alheio AVANCANDO por mais de 60 s = segunda instancia -> Alert e ExpertRemove (aqui so' marca); antes disso inerte",
      aos30 && mzTravaRemoveu && !mzTravaMinha && F.m_envios == 0);
   Trava_LimpaGV();
}

void T_Trava_Perdida(void)
{
   T_Prepara(D'2026.10.07 10:00:00');
   T_BaseTrava();
   mzTravaRelogio = 1000000;
   Trava_Nomes();
   GlobalVariableDel(mzTravaNome);
   Mae_Partida();
   Mae_GravaMemoria(true);
   Espera(11);
   bool minha = mzTravaMinha;
   GlobalVariableSet(mzTravaNome, 999.0);                // outra instancia toma a trava
   GlobalVariableSet(mzHbNome, (double)mzTravaRelogio);
   Entrar(R_GB, 1, 119900, 118700);
   Espera(2);
   bool invalido = !mzTravaMinha && F.m_envios == 0;
   mzTravaRelogio += 61;                                  // o heartbeat dela para
   Espera(2);
   Ok("sec. 1.6: trava tomada por outro -> INVALIDO (nada sai); heartbeat parado -> retomada atomica e memoria recarregada; a entrada sai depois",
      minha && invalido && mzTravaMinha && GlobalVariableGet(mzTravaNome) == mzToken && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1);
   Trava_LimpaGV();
}

//+------------------------------------------------------------------+
//| Memoria (sec. 1.2)                                               |
//+------------------------------------------------------------------+
void T_M_Reinicio(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   int env = F.m_envios;
   T_Reinicia();
   Espera(15);
   bool reinicio = mzEst[R_GB].sit == SIT_LEGITIMA && F.m_envios == env && Vivo(s) && mzNivS[R_GB] == 118700.0 && mzInit[R_GB] &&
                   mzInt[R_GB].tipo == INT_MANTER && mzInt[R_GB].stop == 118700.0;
   Manter(R_GB, 119000, 0);                    // controle: depois do reinicio o nucleo move a S pedida
   Passa(250);
   Ok("sec. 1.2: reinicio com memoria -> papel E pelo mapa (LEGITIMA), nivel da S e intencao inicial MANTER; nada enviado; controle: o MANTER novo move a S",
      reinicio && Vivo(s) && PP(s) == 119000.0);
}

void T_M_SemMemoriaSemLog(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_GB, 1, 119900, 118700);
   Mae_Fim(REASON_CLOSE);
   T_ApagaMemoria();
   T_Base();
   Espera(15);
   Ok("decisao 5: sem memoria e sem log a entrada fora do mapa vira X (papel pelo tipo) -> ficha TROCADA e zerada",
      mzMemPerdida && ND() == 2 && DealTipo(1) == DEAL_TYPE_SELL && DealMagic(1) == MG(R_GB) && mzEst[R_GB].f == 0);
}

void T_M_MapaDoLog(void)
{
   gLogPasta = "WinMaestro_unit\\";
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   int env = F.m_envios;
   Mae_Fim(REASON_CLOSE);
   T_ApagaMemoria();
   T_Base();
   Espera(15);
   gLogPasta = "";
   Log_Pasta("");
   int le = Linha(R_GB, P_E);
   bool refeito = mzMemPerdida && le >= 0 && LDesf(le) == D_EXECUTADA && mzEst[R_GB].sit == SIT_LEGITIMA && F.m_envios == env && Vivo(s);
   Manter(R_GB, 119000, 0);                    // controle: o mapa refeito permite mover a S (papel S pelo log)
   Passa(250);
   Ok("sec. 6: memoria perdida -> mapa refeito das linhas ORDEM do log do dia: a ficha segue LEGITIMA, nada enviado; controle: o MANTER novo move a S",
      refeito && Vivo(s) && PP(s) == 119000.0);
}

void T_M_NaoGrava(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   mzMemPasta = "";                                      // a gravacao passa a falhar
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Passa(250);
   bool sNova = NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && !mzMemGravando;
   Manter(R_GB, 118700, 121000);
   Espera(1);
   bool semA = NP(R_GB, ORDER_TYPE_SELL_LIMIT) == 0;
   // a barreira do passo 5 para a E: a memoria grava ate' a decisao (pode_entrar) e falha exatamente no registro da E
   mzMemPasta = "WinMaestro_unit\\";
   Mae_GravaMemoria(true);
   long id = Entrar(R_CM, -1, 120100, 121300);
   Um();                                                 // P1: a S do CM sai (memoria gravando)
   bool sCM = NP(R_CM, ORDER_TYPE_BUY_STOP) == 1 && mzMemGravando;
   mzMemPasta = "";
   Um();                                                 // E1 decide (memoria gravando); o registro falha -> a E nao sai e o id volta
   bool semE = NP(R_CM, ORDER_TYPE_SELL_LIMIT) == 0 && NLinhas(R_CM, P_E) == 0 && !Est_Consumido(R_CM, id) && !mzMemGravando;
   Espera(11);
   Ok("sec. 3 passo 5: memoria que nao grava -> a S sai com a linha do log; A nao sai; a E que falha no proprio registro nao sai, devolve o id e vira ENTRADA_PERDIDA",
      sNova && semA && sCM && semE && gEvUlt[R_CM] == EV_ENTRADA_PERDIDA && gEvId[R_CM] == id && NP(R_CM, ORDER_TYPE_SELL_LIMIT) == 0);
}

void T_M_OutraConta(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_GB, 1, 119900, 118700);
   Mae_Fim(REASON_PARAMETERS);
   F.m_login = 456;
   T_Base();
   Ok("spec 10.1: memoria de outra conta e' ignorada (memoria perdida)", mzMemPerdida && ArraySize(mzL) == 0);
}

//+------------------------------------------------------------------+
//| Ambiente (sec. 6)                                                |
//+------------------------------------------------------------------+
void T_Amb_Hedging(void)
{
   T_Prepara(D'2026.10.07 10:00:00');          // controle: a mesma entrada em conta NETTING sai
   T_Liga();
   Entrar(R_GB, 1, 119900, 118700);
   Espera(2);
   bool controle = NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1;
   T_Prepara(D'2026.10.07 10:00:00');
   F.m_hedging = true;
   T_Liga();
   Entrar(R_GB, 1, 119900, 118700);
   Espera(2);
   Ok("sec. 6: conta nao NETTING -> INVALIDO permanente (nenhuma ordem); controle: em NETTING a mesma entrada sai", controle && mzNaoNetting && F.m_envios == 0);
}

void T_Amb_Protegendo(void)
{
   T_Prepara(D'2026.10.07 10:00:00');
   F.m_tick_size = 0.0;
   F.DealPorFora(MG(R_GB), 1, 1.0, 120000.0);             // ficha trocada do GB
   T_Liga();
   Espera(1);
   Ok("sec. 6/mudanca D: tick lido 0 com ficha -> PROTEGENDO; a correcao sai assim mesmo (nenhuma divisao pelo tick lido); modulos sem Tick",
      mzProtegendo && ND() == 2 && DealMagic(1) == MG(R_GB) && mzEst[R_GB].f == 0 && gTicks[R_GB] == 0 && Existiu(MG(R_GB), ORDER_TYPE_SELL_STOP, 118800.0));
}

void T_Amb_Parado(void)
{
   T_Prepara(D'2026.10.07 10:00:00');
   F.m_tick_size = 0.0;
   T_Liga();
   Entrar(R_GB, 1, 119900, 118700);
   Espera(2);
   bool parado = mzParado && F.m_envios == 0;
   F.m_tick_size = 5.0;                        // o ambiente volta (rechecado a cada 30 s)
   Espera(31);
   Ok("sec. 6: tick lido 0 sem ficha nem ordem -> parado (nenhuma ordem); o ambiente volta -> a entrada pedida sai",
      parado && !mzParado && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1);
}

//+------------------------------------------------------------------+
//| Cenarios (a)-(n) da sec. 8                                       |
//+------------------------------------------------------------------+
void T_Cen_a(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong sc = Abre(R_CM, 1, 119800, 118600);
   ulong sr = Abre(R_RE, 1, 119900, 118700);
   Manter(R_RE, 118700, 121000);
   Passa(250);
   ulong ar = TK(R_RE, ORDER_TYPE_SELL_LIMIT);
   int ncm = NLinhas(R_CM, P_S) + NLinhas(R_CM, P_K) + NLinhas(R_CM, P_X) + NLinhas(R_CM, P_M);
   Mae_Fim(REASON_CLOSE);                                 // MT5 morto
   F.Dispara(sr); F.Dispara(ar);                          // com o EA fora: a S do RE executa e o A enche
   T_Base();
   Espera(12);
   Ok("(a) S e A do RE com o EA fora -> TROCADA: S de compra na emergencia, X compra 1 com o magic do RE, S cancelada; CM intacto",
      mzEst[R_RE].f == 0 && ND() == 5 && DealTipo(4) == DEAL_TYPE_BUY && DealMagic(4) == MG(R_RE) && Existiu(MG(R_RE), ORDER_TYPE_BUY_STOP, 121205.0) &&
      NP(R_RE, ORDER_TYPE_BUY_STOP) == 0 && Vivo(sc) && mzEst[R_CM].f == 1 &&
      NLinhas(R_CM, P_S) + NLinhas(R_CM, P_K) + NLinhas(R_CM, P_X) + NLinhas(R_CM, P_M) == ncm);
}

void T_Cen_b(const bool executou)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_C1, 1, 0.0, 118800);                          // C1: a S antes, depois a E a mercado
   Passa(250);
   ulong s = TK(R_C1, ORDER_TYPE_SELL_STOP);
   bool entrou = mzEst[R_C1].f == 1 && s != 0 && PP(s) == 118800.0;
   Espera(30);
   F.Roteiro(executou ? FM_TIMEOUT_TK0_EXEC : FM_TIMEOUT_TK0_NADA);
   Sair(R_C1);
   Um();                                                  // a X sai com TIMEOUT e ticket 0
   F.m_conectado = false;
   int env = F.m_envios;
   Espera(90);
   bool fora = F.m_envios == env && Vivo(s);
   F.m_conectado = true;
   Espera(12);
   if(executou)
   {
      Ok("(b) X do C1 com TIMEOUT/ticket 0 e 90 s sem internet, EXECUTOU: casada pela ordem FILLED -> ficha 0 e so' entao a S sai; nenhuma 2a X",
         entrou && fora && mzEst[R_C1].f == 0 && ND() == 2 && NLinhas(R_C1, P_X) == 1 && EH(s) == ORDER_STATE_CANCELED);
      return;
   }
   bool aindaPend = NLinhas(R_C1, P_X) == 1 && Desf(R_C1, P_X) == D_PENDENTE && Vivo(s);
   Espera(36);
   Ok("(b) idem, NAO CHEGOU: PENDENTE (RESTRITO) ate' 30 s de conexao e historico; NAO_EXECUTADA; X3 de novo; a S nunca sai antes",
      entrou && fora && aindaPend && NLinhas(R_C1, P_X) == 2 && mzEst[R_C1].f == 0 && ND() == 2 && EH(s) == ORDER_STATE_CANCELED);
}

void T_Cen_c(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   ulong sd = Abre(R_DM, 1, 119800, 118600);
   Entrar(R_CM, -1, 120100, 121300);
   Passa(250);
   ulong ec = TK(R_CM, ORDER_TYPE_SELL_LIMIT), sc = TK(R_CM, ORDER_TYPE_BUY_STOP);
   F.DealPorFora(0, -1, 2.0, 120000.0, false, true);
   F.m_deal_oculto[ArraySize(F.m_deal_oculto) - 1] = false;   // o deal aparece; a ordem ainda nao
   Espera(2);
   bool restr = mzNaoClassTotal == 1 && Vivo(sg) && Vivo(sd) && Vivo(ec) && Vivo(sc) && !mzBloqBotao;
   F.MostraHist();
   Espera(1);
   bool zerou = mzBloqBotao && mzEst[R_GB].f == 0 && mzEst[R_DM].f == 0 && EH(sg) == ORDER_STATE_CANCELED && EH(sd) == ORDER_STATE_CANCELED &&
                EH(ec) == ORDER_STATE_CANCELED && EH(sc) == ORDER_STATE_CANCELED && gEvUlt[R_CM] == EV_ENTRADA_CANCELADA;
   Mae_Desbloqueia();
   bool livre = !mzBloqBotao;
   T_Reinicia();
   Espera(12);
   Ok("(c) zeragem manual com GB e DM posicionados e E do CM viva: nao classificado (S intactas) -> absorve GB e DM, bloqueio, cancela E e S; botao libera; reinicio nao rebloqueia",
      restr && zerou && livre && !mzBloqBotao && ND() == 3);
}

void T_Cen_d(void)
{
   T_Inicia(D'2026.10.06 15:00:00');
   ulong s = Abre(R_DM, 1, 119800, 118600);
   Mae_Fim(REASON_CLOSE);                                 // EA fora no corte
   F.CancelaPorFora(s, ORDER_STATE_EXPIRED);              // a S DAY venceu com o pregao
   F.DefineAgora(D'2026.10.07 08:56:00');
   F.Precos(117000, 117005);                              // gap contra
   T_Base();
   Espera(11);
   ulong s2 = TK(R_DM, ORDER_TYPE_SELL_STOP);
   bool noite = mzEst[R_DM].noite && s2 != 0 && PP(s2) == 115800.0 && ND() == 1;
   F.DefineAgora(D'2026.10.07 09:00:00');
   Passa(250);
   Ok("(d) ficha da noite com gap contra: janela cobre o episodio de ontem; S de emergencia na pre-abertura (sem X fora do continuo); 09:00 X3 e L3",
      noite && ND() == 2 && DealTipo(1) == DEAL_TYPE_SELL && DealMagic(1) == MG(R_DM) && mzEst[R_DM].f == 0 && EH(s2) == ORDER_STATE_CANCELED);
   Espera(70);
   Ok("(d) depois que o episodio da noite fecha a janela nao encolhe: o DM segue provado e confiavel, sem bloqueio",
      mzEst[R_DM].confiavel && mzEst[R_DM].f == 0 && mzEst[R_DM].sit == SIT_ZERO && !mzBloqAuto && !mzBloqBotao);
}

void T_Revisao_Regressoes(void)
{
   // corte: C_CONTA executado com a posicao ainda nao atualizada nao gera um segundo C_CONTA
   T_Inicia(D'2026.10.07 18:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   F.CongelaLiq();
   F.DefineAgora(D'2026.10.07 18:22:00');
   Espera(5);
   bool um = NLinhas(R_MAE, P_X) == 1 && F.m_liq == 0;
   F.MostraLiq();
   Espera(1);
   Ok("sec. 5.2: C_CONTA executado e posicao atrasada -> nenhum segundo C_CONTA nos 30 s; a S sai com a liquida 0", um && NLinhas(R_MAE, P_X) == 1 && F.m_liq == 0 && EH(sg) == ORDER_STATE_CANCELED);

   // PRAZO_SAIR nao conta o tempo INVALIDO
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_GB, 1, 119900, 118700);
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL;
   Sair(R_GB);
   Espera(5);
   F.m_conectado = false;
   Espera(55);
   F.m_conectado = true;
   Espera(12);
   Ok("sec. 4.1: PRAZO_SAIR conta so' ciclos confiaveis: 55 s sem internet nao expiram a saida (que foi tentada)",
      gEvUlt[R_GB] != EV_SAIDA_EXPIRADA && mzInt[R_GB].tipo == INT_SAIR && NRecusadas(R_GB, P_X) >= 2);

   // rearme para o outro lado: a S velha sai, a nova entra no lado certo
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_CM, -1, 120100, 121300);
   Passa(250);
   ulong sv = TK(R_CM, ORDER_TYPE_BUY_STOP), ev = TK(R_CM, ORDER_TYPE_SELL_LIMIT);
   Entrar(R_CM, 1, 119800, 118600);
   Espera(1);
   ulong sn = TK(R_CM, ORDER_TYPE_SELL_STOP);
   Ok("L1/L3: rearme do CM para o outro lado -> E velha e S velha canceladas; S nova antes da E nova",
      EH(ev) == ORDER_STATE_CANCELED && EH(sv) == ORDER_STATE_CANCELED && sn != 0 && PP(sn) == 118600.0 && NP(R_CM, ORDER_TYPE_BUY_LIMIT) == 1 &&
      SetupPend(sn) < SetupPend(TK(R_CM, ORDER_TYPE_BUY_LIMIT)));

   // E1 com stop pedido invalido: recusa a entrada (nao entra com a S de emergencia)
   T_Inicia(D'2026.10.07 10:00:00');
   long id = Entrar(R_GB, 1, 119900, 119950);
   Espera(1);
   Ok("E1: stop pedido invalido -> ENTRADA_RECUSADA, nenhuma E; a S de emergencia sai depois (L3)",
      !ExistiuTipo(MG(R_GB), ORDER_TYPE_BUY_LIMIT) && gEvUlt[R_GB] == EV_ENTRADA_RECUSADA && gEvId[R_GB] == id && NP(R_GB, ORDER_TYPE_SELL_STOP) == 0);

   // emergencia gravada para um lado nao bloqueia a S quando a ficha inverte
   T_Inicia(D'2026.10.07 08:50:00');
   F.DealPorFora(MG(R_GB), 1, 1.0, 120000.0);
   F.DefineAgora(D'2026.10.07 08:55:00');
   Espera(1);
   ulong se = TK(R_GB, ORDER_TYPE_SELL_STOP);
   bool emerg1 = se != 0 && PP(se) == 118800.0 && mzEmergLado[R_GB] == 1;
   F.Dispara(se);
   F.DealPorFora(MG(R_GB), -1, 1.0, 120000.0);
   Espera(1);
   Ok("sec. 4.3: ficha que inverte no mesmo episodio -> emergencia nova do outro lado (BUY_STOP ask + 1.200)",
      emerg1 && mzEst[R_GB].f == -1 && Existiu(MG(R_GB), ORDER_TYPE_BUY_STOP, 121205.0) && mzEmergLado[R_GB] == -1);
}

void T_Cen_e(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   for(int k = 0; k < 8; k++) F.Roteiro(FM_NORMAL);
   F.Roteiro(FM_DONE_SEM_DEAL);                           // a 9a ordem (E a mercado do C1): deal atrasado, FILLED visivel
   Entrar(R_GB, 1, 120100, 118900);
   Entrar(R_CM, -1, 120100, 121300);
   Entrar(R_DM, 1, 119800, 118600);
   Entrar(R_RE, -1, 120200, 121400);
   Entrar(R_C1, 1, 0.0, 118800);
   Passa(250);
   bool sAntes = NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && NP(R_DM, ORDER_TYPE_SELL_STOP) == 1 && NP(R_RE, ORDER_TYPE_BUY_STOP) == 1 && NP(R_C1, ORDER_TYPE_SELL_STOP) == 1;
   bool es = NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1 && NP(R_DM, ORDER_TYPE_BUY_LIMIT) == 1 && NP(R_RE, ORDER_TYPE_SELL_LIMIT) == 1;
   bool o2 = !ExistiuTipo(MG(R_CM), ORDER_TYPE_SELL_LIMIT) && gEvUlt[R_CM] == EV_ENTRADA_RECUSADA && gEvMot[R_CM] == "autoneg";
   bool c1 = Desf(R_C1, P_E) == D_EXECUTADA && !mzEst[R_C1].confiavel && mzEst[R_GB].confiavel && mzDeltaResto == 0;
   F.MostraOcultos();
   Passa(250);
   Ok("(e) cinco entradas no mesmo segundo: S de cada um antes da E; O2 pelo mapa no mesmo ciclo (CM recusado); deal do C1 atrasado com FILLED: so' o C1 RESTRITO",
      sAntes && es && o2 && c1 && mzEst[R_C1].f == 1 && NP(R_CM, ORDER_TYPE_BUY_STOP) == 0);
}

void T_Cen_f(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   Abre(R_CM, 1, 119800, 118600);
   F.DefineAgora(D'2026.10.07 18:21:45');
   F.Roteiro(FM_TIMEOUT_TK0_NADA);                        // a X do GB (a primeira) fica sem desfecho
   Passa(250);
   bool cm = mzEst[R_CM].f == 0 && !mzEst[R_GB].confiavel && NLinhas(R_GB, P_X) == 1;
   F.DefineAgora(D'2026.10.07 18:22:00');
   Passa(250);
   bool espera = NLinhas(R_MAE, P_X) == 0 && Vivo(sg);
   Espera(17);
   Ok("(f) corte com uma X sem desfecho: os outros saem por X3; em C+2 o C_CONTA espera a X ter 30 s, zera a liquida e entao cancela as S",
      cm && espera && NLinhas(R_MAE, P_X) == 1 && F.m_liq == 0 && EH(sg) == ORDER_STATE_CANCELED);
}

void T_Cen_g(const bool encheu)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_DM, 1, 119800, 118600);
   Passa(250);
   ulong e = TK(R_DM, ORDER_TYPE_BUY_LIMIT), s = TK(R_DM, ORDER_TYPE_SELL_STOP);
   if(encheu) F.Roteiro(FM_EXECUTA_ANTES);                // o K do TTL perde a corrida: a E enche
   Nada(R_DM);
   Passa(250);
   if(encheu)
   {
      // o K que perdeu a corrida volta INVALID_ORDER: RECUSADA e em_espera[DM][K] por RETENTA (o M nao espera)
      bool exec = Desf(R_DM, P_E) == D_EXECUTADA && gEvUlt[R_DM] == EV_ENTRADA_EXECUTADA && Vivo(s) && mzEst[R_DM].f == 1 &&
                  Desf(R_DM, P_K) == D_RECUSADA && Dec_Espera(R_DM, P_K);
      Manter(R_DM, 118700, 0);                            // o DM reancora o stop no evento
      Passa(250);
      Ok("(g) E do DM enche com o K do TTL em voo: ENTRADA_EXECUTADA; o K RECUSADA espera RETENTA; MANTER(stop reancorado) -> P3 move a S", exec && PP(s) == 118700.0);
      return;
   }
   Ok("(g) idem, o K vence: ENTRADA_CANCELADA; L3 cancela a S", EH(e) == ORDER_STATE_CANCELED && gEvUlt[R_DM] == EV_ENTRADA_CANCELADA && EH(s) == ORDER_STATE_CANCELED);
}

void T_Cen_h(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   Abre(R_GB, 1, 119900, 118700);
   Abre(R_CM, 1, 119800, 118600);
   F.DefineAgora(D'2026.10.07 18:19:00');
   F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Sair(R_GB);
   Passa(250);
   Mae_Fim(REASON_CLOSE);                                 // o MT5 reinicia
   F.DefineAgora(D'2026.10.07 18:19:20');
   T_Base();
   Espera(11);
   bool gbRestrito = !mzEst[R_GB].confiavel && mzEst[R_CM].confiavel && mzEst[R_CM].f == 1;
   F.DefineAgora(D'2026.10.07 18:20:00');
   Espera(1);
   bool cmSaiu = mzEst[R_CM].f == 0;
   Espera(45);
   Ok("(h) MT5 reinicia 18:19 com uma X pendente: o robo da X RESTRITO, os outros saem em 18:20 (I1); a X prova NAO_EXECUTADA e sai antes de C+2",
      gbRestrito && cmSaiu && mzEst[R_GB].f == 0 && F.m_liq == 0 && F.ContaPend() == 0 && mzAgora < Mae_C2De(mzAgora) && NLinhas(R_MAE, P_X) == 0);
}

void T_Cen_i(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   ulong sc = Abre(R_CM, 1, 119800, 118600);
   Entrar(R_DM, 1, 119700, 118500);
   Passa(250);
   ulong ed = TK(R_DM, ORDER_TYPE_BUY_LIMIT);
   int env = F.m_envios;
   Mae_Fim(REASON_PARAMETERS);
   T_Base();
   mzAtivo[R_GB] = false; mzAtivo[R_CM] = false;          // o dono desliga dois robos posicionados
   Espera(12);
   bool intacto = Vivo(sg) && Vivo(sc) && Vivo(ed) && mzEst[R_GB].f == 1 && mzEst[R_CM].f == 1 && F.m_envios == env;
   Sair(R_GB);
   Passa(250);
   bool saiu = mzEst[R_GB].f == 0;
   int env2 = F.m_envios;
   Entrar(R_GB, 1, 119900, 118700);
   Espera(2);
   Ok("(i) robos desligados: nada cancelado na partida (E viva do DM inclusive); gerem ate' zerar; entrada nova nao sai",
      intacto && saiu && F.m_envios == env2 && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 0);
}

void T_Cen_j(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_GB, 1, 119900, 118700);
   Abre(R_CM, 1, 119800, 118600);
   Abre(R_DM, 1, 119700, 118500);
   Entrar(R_RE, 1, 119500, 118300);
   Passa(250);
   ulong er = TK(R_RE, ORDER_TYPE_BUY_LIMIT);
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);       // posicao manual que o historico nao mostra
   Espera(2);
   bool restr = !mzEst[R_GB].confiavel && !mzEst[R_CM].confiavel;
   Espera(30);
   bool virt = mzDeltaEstavel && mzEst[R_GB].confiavel && !mzBloqAuto && mzExterna == 1 && Vivo(er);
   F.m_hist_falha = true;
   Espera(62);
   bool bloq = mzBloqAuto && EH(er) == ORDER_STATE_CANCELED && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && NP(R_CM, ORDER_TYPE_SELL_STOP) == 1;
   Espera(540);
   bool botao = mzBloqBotao;
   F.DefineAgora(D'2026.10.07 18:22:00');
   Espera(2);
   int nd = ND();
   Ok("(j) cruzada aberta com 3 fichas: RESTRITOS 30 s, depois externo virtual (todos confiaveis); historico ilegivel: 60 s bloqueio (E canceladas), 10 min botao; corte pela conta (4 contratos)",
      restr && virt && bloq && botao && F.m_liq == 0 && DealMagic(nd - 1) == MAGIC_MAESTRO && DealVol(nd - 1) == 4.0);
}

void T_Cen_k(const bool filled)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   Abre(R_CM, 1, 119800, 118600);
   Int_Sair(mzInt[R_GB], "teste");                        // o robo JA' pede a saida quando a S executa (sem depender de um Tick)
   F.Dispara(sg, !filled, true);                          // a S executa; o deal (e, sem `filled`, a ordem) so' aparece 3 s depois
   int env = F.m_envios;
   Passa(250);
   // ficha velha +1, SAIR pedido, nada pendente que reduza (com `filled`): so' o `confiavel` segura a X3 e so' o lado
   // inequivoco (que exige provado) segura o P1
   bool restr = !mzEst[R_GB].confiavel && !mzEst[R_GB].inequivoco && mzEst[R_GB].f == 1 && mzInt[R_GB].tipo == INT_SAIR;
   if(filled) restr = restr && Desf(R_GB, P_S) == D_EXECUTADA && mzEst[R_CM].confiavel && !mzEst[R_GB].reduz_pend && !mzEst[R_GB].pendK;
   else       restr = restr && Desf(R_GB, P_S) == D_SUMIDA && !mzEst[R_CM].confiavel;
   Espera(3);
   bool nada = F.m_envios == env && NLinhas(R_GB, P_X) == 0;
   F.MostraOcultos();
   Passa(250);
   Ok(filled ? "(k) S executou, ordem FILLED sem deal, SAIR ja' pedido: Delta_resto 0 -> so' o robo da S RESTRITO; nenhuma X nem S; o deal chega -> ficha 0"
             : "(k) S executou com a posicao ja' em 0, deal 3 s depois, SAIR ja' pedido: SUMIDA, todos RESTRITOS, nada sai; o deal chega -> ficha 0",
      restr && nada && mzEst[R_GB].f == 0 && ND() == 3 && NLinhas(R_GB, P_X) == 0 && F.m_envios == env);
}

void T_Cen_l(void)
{
   T_Inicia(D'2026.10.07 18:19:00');
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL;     // a correcao (venda a mercado do GB) e' sempre recusada
   F.DealPorFora(MG(R_GB), 1, 1.0, 120000.0);
   Espera(60);
   int tent = NLinhas(R_GB, P_X);
   bool semRajada = tent >= 10 && tent <= 13 && mzRecusaN[R_GB][P_X] >= 5 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1;
   F.DefineAgora(D'2026.10.07 18:22:00');
   Espera(2);
   int nd = ND();
   Ok("(l) correcao recusada seguidas vezes: S na emergencia, X a cada 5 s (sem rajada, ALERTA na 5a); em C+2 o C_CONTA resolve e a S sai",
      semRajada && F.m_liq == 0 && DealMagic(nd - 1) == MAGIC_MAESTRO && NP(R_GB, ORDER_TYPE_SELL_STOP) == 0);
}

void T_Cen_m(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong sd = Abre(R_DM, 1, 119800, 118600);
   F.m_recusa_magic = MG(R_DM);                           // tudo do DM e' recusado
   F.CancelaPorFora(sd, ORDER_STATE_CANCELED);
   Espera(10);
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   bool gb = NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && mzEst[R_GB].confiavel;
   Espera(52);
   Ok("(m) corretora recusa um robo: os outros operam (RECUSADA nao e' pendente); S recusada com ficha 60 s -> I3 e X3 recusadas, retentadas",
      gb && NRecusadas(R_DM, P_S) >= 10 && NRecusadas(R_DM, P_X) >= 1 && mzEst[R_DM].f == 1 && mzOrigemUlt[R_DM] == I_3 && mzEst[R_GB].confiavel);
}

void T_Cen_n(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   ulong e = TK(R_GB, ORDER_TYPE_BUY_LIMIT), s = TK(R_GB, ORDER_TYPE_SELL_STOP);
   F.CongelaLiq();                                        // a posicao chega depois do deal (N-1)
   F.Dispara(e);
   Passa(250);
   bool restr = !mzEst[R_GB].confiavel && !mzEst[R_CM].confiavel && mzDeltaResto == -1 && Vivo(s) && !mzBloqBotao && !mzBloqAuto && ArraySize(mzAbsVistas) == 0;
   F.MostraLiq();
   Passa(250);
   Ok("(n) deal da E antes da posicao: todos RESTRITOS, nenhuma absorcao nem bloqueio, S intacta; a posicao chega -> LEGITIMA",
      restr && mzEst[R_GB].confiavel && mzEst[R_GB].sit == SIT_LEGITIMA && Vivo(s) && mzEst[R_GB].f == 1);
}


//+------------------------------------------------------------------+
//| v2.01: achados da revisao 1 (um teste por achado com efeito)     |
//+------------------------------------------------------------------+
void T_A1_ExtDescDia(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);      // posicao manual de antes da janela (o deal nunca aparece)
   Espera(32);
   bool estavel = mzDeltaEstavel && mzDeltaResto == 1 && mzEst[R_GB].confiavel;
   Mae_Desbloqueia();                                     // o dono reconhece: externa de origem desconhecida +1
   Passa(250);
   bool gravada = mzExtDesc == 1 && mzDeltaResto == 0 && mzEst[R_GB].confiavel;
   F.DealPorFora(0, -1, 1.0, 120000.0);                   // o dono zera na mao: o deal de fechamento esta' na janela
   Espera(35);
   bool fica = mzExtDesc == 1 && mzDeltaResto == 0 && F.m_liq == 0;   // ela explica esse deal: fica ate' o dia novo
   F.DefineAgora(D'2026.10.08 09:30:00');
   Espera(2);
   Ok("A-1: externa desconhecida gravada pelo botao explica a posicao antiga e o deal que a fecha; no dia novo deixa de valer: Delta 0 e robos confiaveis",
      estavel && gravada && fica && mzExtDesc == 0 && mzDeltaResto == 0 && mzEst[R_GB].confiavel && mzEst[R_CM].confiavel);
}

void T_A1_ExtDescZera(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);      // posicao manual cujo deal (e ordem) ainda nao aparecem
   Espera(32);
   Mae_Desbloqueia();                                     // o dono grava a diferenca como externa desconhecida (+1)
   Passa(250);
   bool gravada = mzExtDesc == 1 && mzDeltaResto == 0;
   F.MostraOcultos();                                     // o deal aparece na janela: a externa passou a sobrar
   F.DealPorFora(0, -1, 1.0, 120000.0);                   // e o dono zera
   Espera(5);
   bool espera = mzExtDesc == 1 && F.m_liq == 0 && mzSomaDeals == 0;   // 30 s de liquida e deals em 0 antes de largar
   Espera(30);
   Ok("A-1: liquida e deals da janela em 0 por 30 s -> a externa desconhecida deixa de valer no mesmo dia (Delta 0, confiaveis)",
      gravada && espera && mzExtDesc == 0 && mzDeltaResto == 0 && mzEst[R_GB].confiavel);
}

void T_A2_RecusaAssinc(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_rej_magic = MG(R_GB); F.m_rej_tipo = ORDER_TYPE_SELL_STOP; F.m_rej_ms = 0;   // a bolsa aceita a S (PLACED) e rejeita depois
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Passa(250);
   int n1 = NLinhas(R_GB, P_S);                           // a original e uma nova, REJECTED no historico
   Espera(4);
   int n2 = NLinhas(R_GB, P_S);
   Espera(23);
   int n3 = NLinhas(R_GB, P_S);
   Ok("A-2: recusa assincrona (aceita no envio, REJECTED no historico) -> a mesma RETENTA de 5 s e a mesma contagem (ALERTA na 5a): sem rajada",
      n1 == 2 && n2 == 2 && n3 >= 5 && n3 <= 7 && mzRecusaN[R_GB][P_S] >= 4 && Desf(R_GB, P_S) == D_NAO_EXECUTADA && ND() == 1);
}

void T_K_SVivas(void)
{
   T_Inicia(D'2026.10.07 18:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   ulong sc = Abre(R_CM, 1, 119800, 118600);
   F.DefineAgora(D'2026.10.07 18:22:00');
   F.Roteiro(FM_TIMEOUT_TK0_NADA);                        // o primeiro C_CONTA fica sem desfecho
   bool vivas = true;
   for(int k = 0; k < 28; k++) { Espera(1); if(!Vivo(sg) || !Vivo(sc) || F.m_liq == 0) vivas = false; }
   Espera(12);
   int nd = ND();
   Ok("sec. 5.2: as S ficam vivas a cada segundo enquanto a liquida != 0 (C_CONTA sem desfecho 30 s); zerada a conta, saem depois do deal do C_CONTA",
      vivas && F.m_liq == 0 && NLinhas(R_MAE, P_X) == 2 && DealMagic(nd - 1) == MAGIC_MAESTRO && DealVol(nd - 1) == 2.0 &&
      EH(sg) == ORDER_STATE_CANCELED && EH(sc) == ORDER_STATE_CANCELED && DoneHist(sg) > DealMsc(nd - 1) && DoneHist(sc) > DealMsc(nd - 1));
}

void T_KM_Assinc(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.m_assinc_ms = 2000;                                  // K e M respondem DONE e fazem efeito 2 s depois
   Entrar(R_DM, 1, 119800, 118600);
   Passa(250);
   ulong e = TK(R_DM, ORDER_TYPE_BUY_LIMIT), s = TK(R_DM, ORDER_TYPE_SELL_STOP);
   Nada(R_DM);
   Espera(1);
   bool umK = NLinhas(R_DM, P_K) == 1 && Vivo(e) && Vivo(s) && Desf(R_DM, P_K) == D_PENDENTE;
   Espera(2);
   bool kE = EH(e) == ORDER_STATE_CANCELED && NLinhas(R_DM, P_K) == 2 && Vivo(s);   // o K da E provou; o da S (L3) em voo
   Espera(3);
   bool kS = EH(s) == ORDER_STATE_CANCELED && NLinhas(R_DM, P_K) == 2;
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   Manter(R_GB, 119000, 0);
   Espera(1);
   bool umM = NLinhas(R_GB, P_M) == 1 && PP(sg) == 118700.0 && Desf(R_GB, P_M) == D_PENDENTE;
   Espera(2);
   Ok("sec. 2.1 K/M assincronos: um K (ou M) por ordem enquanto o efeito nao aparece; provado o K da E, L3 manda o da S; M EXECUTADA pelo preco novo",
      e != 0 && umK && kE && kS && umM && PP(sg) == 119000.0 && NLinhas(R_GB, P_M) == 1 && Desf(R_GB, P_M) == D_EXECUTADA);
}

void T_Trans(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   ulong e = TK(R_GB, ORDER_TYPE_BUY_LIMIT);
   F.LimpaTrans();
   F.Dispara(e);                                          // a E enche; nenhum Passa: so' as transacoes
   int t0 = gTicks[R_GB];
   MqlTradeTransaction tr; MqlTradeRequest rq; MqlTradeResult rs;
   ZeroMemory(tr); ZeroMemory(rq); ZeroMemory(rs);
   tr.type = TRADE_TRANSACTION_DEAL_ADD; tr.symbol = "OUTRO_SIMBOLO";
   Mae_OnTradeTransaction(tr, rq, rs);
   bool ignorada = gTicks[R_GB] == t0 && Desf(R_GB, P_E) == D_VIVA;
   Entrega();
   Ok("OnTradeTransaction: transacao do simbolo roda o ciclo (o fill da E vira ENTRADA_EXECUTADA sem OnTimer); de outro simbolo e' ignorada",
      e != 0 && ignorada && gTicks[R_GB] > t0 && gEvUlt[R_GB] == EV_ENTRADA_EXECUTADA && Desf(R_GB, P_E) == D_EXECUTADA);
}

void T_Preco_Corrida(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_por_preco = true;
   Sair(R_GB);
   Um();                                                  // a X executa (ficha 0); a S ainda viva (L3 no ciclo seguinte)
   bool x = ND() == 2 && Vivo(s);
   F.Move(118650, 118655);                                // o mercado atravessa a S antes do K dela: ela dispara (corrida aceita, sec. 4.4)
   bool disparou = EH(s) == ORDER_STATE_FILLED && ND() == 3 && F.m_liq == -1;
   Espera(2);
   int nd = ND();
   Ok("execucao por preco: S que dispara junto com a X (corrida aceita) -> TROCADA, S de compra antes, correcao a mercado com o magic do robo; ficha 0",
      x && disparou && mzEst[R_GB].f == 0 && nd == 4 && DealTipo(3) == DEAL_TYPE_BUY && DealMagic(3) == MG(R_GB) &&
      ExistiuTipo(MG(R_GB), ORDER_TYPE_BUY_STOP) && F.m_liq == 0 && NP(R_GB, ORDER_TYPE_BUY_STOP) == 0);
}

void T_M1_DeltaEstavel(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);      // posicao manual que o historico nao mostra: Delta +1 duradouro
   Espera(32);
   bool estavel = mzDeltaEstavel && mzEst[R_CM].confiavel;
   F.Roteiro(FM_PEND_OCULTA);                             // a S do GB fica PENDENTE (aceita, ainda nao listada): GB nao provado
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   bool gbPend = Desf(R_GB, P_S) == D_PENDENTE && !mzEst[R_GB].provado;
   Entrar(R_CM, -1, 120100, 121300);
   Espera(2);
   Ok("M-1: Delta estavel segue estavel enquanto o VALOR nao muda, mesmo com um robo nao provado: o CM entra",
      estavel && gbPend && mzDeltaEstavel && mzEst[R_CM].confiavel && NP(R_CM, ORDER_TYPE_SELL_LIMIT) == 1 && Desf(R_GB, P_S) == D_PENDENTE);
}

void T_M2_EntregaId(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Int_Entrar(mzInt[R_CM], 222, -1, 120100, 121300, 0, "rearme");
   double niv = mzNivS[R_CM];
   Est_Entrega(R_CM, EV_ENTRADA_EXECUTADA, 111, 119800.0, mzAgora, "");   // encheu a entrada ANTERIOR (compra)
   bool outra = mzInt[R_CM].tipo == INT_MANTER && mzInt[R_CM].stop == 0.0 && mzNivS[R_CM] == niv;
   Int_Entrar(mzInt[R_CM], 333, 1, 119800, 118600, 0, "pedida");
   Est_Entrega(R_CM, EV_ENTRADA_EXECUTADA, 333, 119800.0, mzAgora, "");
   Ok("M-2: ENTRADA_EXECUTADA de outra entrada (rearme) -> MANTER sem nivel (o stop da venda nao vira memoria); da pedida -> MANTER(stop dela)",
      outra && mzInt[R_CM].tipo == INT_MANTER && mzInt[R_CM].stop == 118600.0);
}

void T_M3_RearmeMesmoLado(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Entrar(R_CM, 1, 119800, 118600);
   Passa(250);
   ulong ec = TK(R_CM, ORDER_TYPE_BUY_LIMIT), sc = TK(R_CM, ORDER_TYPE_SELL_STOP);
   F.CancelaPorFora(ec, ORDER_STATE_EXPIRED);             // a E velha vence
   Entrar(R_CM, 1, 118500, 118000);                       // rearme do mesmo lado com a limite ABAIXO do nivel da S velha
   Espera(1);
   ulong e2 = TK(R_CM, ORDER_TYPE_BUY_LIMIT);
   Ok("M-3: rearme do mesmo lado, S velha invalida para a E nova (ficha 0) -> P3 move a S ao nivel pedido e a E sai",
      ec != 0 && Vivo(sc) && PP(sc) == 118000.0 && e2 != 0 && PP(e2) == 118500.0 && NP(R_CM, ORDER_TYPE_SELL_STOP) == 1);
}

void T_M4_Relogio(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Espera(30);
   F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Sair(R_GB);
   Passa(250);
   int lx = Linha(R_GB, P_X);
   F.m_desvio_ms = 60000;                                 // o relogio do PC salta 60 s para frente
   Espera(1);
   Ok("M-4: prazos no relogio monotonico: salto de 60 s do relogio do PC nao prova ausencia (X de ticket 0 segue PENDENTE, nenhuma 2a X); ALERTA de relogio",
      LDesf(lx) == D_PENDENTE && NLinhas(R_GB, P_X) == 1 && mzRelogioDesvio && Vivo(s));
}

void T_B1_CasaTardia(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   Espera(30);
   F.Roteiro(FM_NORMAL);                                  // a S normal
   F.Roteiro(FM_TK0_OCULTA);                              // a E: timeout com ticket 0 e a ordem so' aparece depois
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   int le = Linha(R_GB, P_E);
   bool tk0 = le >= 0 && LTk(le) == 0;
   Espera(32);
   bool nao = LDesf(le) == D_NAO_EXECUTADA;
   F.MostraPend();
   ulong e = TK(R_GB, ORDER_TYPE_BUY_LIMIT);
   F.Dispara(e);                                          // a E atrasada aparece e enche
   Passa(250);
   Ok("B-1: E de ticket 0 ja' NAO_EXECUTADA e' casada quando a ordem aparece; o deal vence: EXECUTADA e ficha LEGITIMA (nao TROCADA)",
      tk0 && nao && e != 0 && LTk(le) == e && LDesf(le) == D_EXECUTADA && mzEst[R_GB].sit == SIT_LEGITIMA);
}

void T_B2_Retcode0(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.m_rc = 0;
   F.Roteiro(FM_RETCODE);                                 // OrderSend falso com retcode 0 (pedido mal formado no cliente)
   Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   int env1 = F.m_envios;
   Espera(4);
   int env2 = F.m_envios;
   Espera(2);
   Ok("B-2: OrderSend falso com retcode 0 = recusa: RECUSADA (nao PENDENTE), em_espera 5 s; depois a S e a E saem",
      env1 == 1 && env2 == 1 && NRecusadas(R_GB, P_S) == 1 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 1 && NP(R_GB, ORDER_TYPE_BUY_LIMIT) == 1);
}

void T_B3_SValida(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s1 = Abre(R_GB, 1, 119900, 119500);
   ulong sx = F.PendPorFora(MG(R_GB), ORDER_TYPE_SELL_STOP, 120100);   // S do GB em nivel ja' atravessado que nao executou
   // a lista da corretora nao tem ordem garantida: a S invalida vem primeiro
   SOrdemViva tmp = F.m_pend[0]; F.m_pend[0] = F.m_pend[1]; F.m_pend[1] = tmp;
   bool to = F.m_pend_oculta[0]; F.m_pend_oculta[0] = F.m_pend_oculta[1]; F.m_pend_oculta[1] = to;
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);      // Delta +1: GB RESTRITO com lado inequivoco (P2 nao age, P3 sim)
   Int_Manter(mzInt[R_GB], 120100, 0, "nivel invalido");
   mzNivS[R_GB] = 120100;
   Passa(250);
   Ok("B-3: a S viva da cadeia e' a primeira VALIDA: a S boa (119500) nao vai para a emergencia (118800) por causa da S invalida antes dela",
      s1 != 0 && Vivo(sx) && Vivo(s1) && PP(s1) == 119500.0 && mzEmerg[R_GB] == 0.0 && !mzEst[R_GB].confiavel && mzEst[R_GB].inequivoco);
}

void T_B4_RecuoEstavel(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   mzMemPerdida = true;
   F.DealPorFora(0, 1, 1.0, 120000.0, false, true);      // Delta transitorio: o deal ainda nao esta' no historico
   Espera(3);
   bool semRecuo = mzRecuoN == 0;
   F.MostraOcultos();
   Espera(1);
   Ok("B-4: com memoria perdida, Delta que nao e' estavel nao recua a janela", semRecuo && mzRecuoN == 0 && mzDeltaResto == 0);
}

void T_B8_PrefereViva(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.Roteiro(FM_TIMEOUT_TK0_EXEC);                        // a S com timeout e ticket 0 (a ordem ficou viva)
   Entrar(R_GB, 1, 119900, 118700);
   Um();
   int ls = Linha(R_GB, P_S);
   ulong viva = TK(R_GB, ORDER_TYPE_SELL_STOP);
   F.m_tk++;
   F.AddHist(F.m_tk, MG(R_GB), ORDER_TYPE_SELL_STOP, 118700.0, 1.0, F.Msc(), ORDER_STATE_REJECTED, "", false);   // REJECTED de outro envio
   Um();
   Ok("B-8: casamento de ticket 0 prefere a ordem viva/executada a' REJECTED do mesmo magic/tipo/preco: casa, nao fica ambigua",
      viva != 0 && LTk(ls) == viva && LDesf(ls) == D_VIVA);
}

void T_B9_SFaltaInvalido(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL_STOP;
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Espera(40);
   F.m_conectado = false;
   Espera(30);
   F.m_conectado = true;
   Espera(12);
   bool semX = ND() == 1;
   Espera(60);
   Ok("B-9: a S faltando conta de novo depois do INVALIDO: nenhuma saida (I3) logo na volta; 60 s de base firme depois, I3",
      semX && ND() == 2 && DealMagic(1) == MG(R_GB) && DealTipo(1) == DEAL_TYPE_SELL);
}

void T_B19_DecisaoAtrasada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   mzPartidaMsc = 0;
   bool velha = Ficha_DecisaoPerdida(R_C1, mzAgora - 121, "teste");
   bool nova = Ficha_DecisaoPerdida(R_C1, mzAgora - 60, "teste");
   Ok("B-19: decisao com mais de 120 s de atraso (robo RESTRITO, sem Tick) = DECISAO PERDIDA; com menos, vale", velha && !nova);
}

//+------------------------------------------------------------------+
//| v2.02: achados da revisao 2 (um teste por mudanca de comportamento)|
//+------------------------------------------------------------------+
void T_B2_1_AusenciaConta(void)
{
   // corretora que descarta a X em silencio (timeout com ticket 0 e nada acontece): cada X vira NAO_EXECUTADA por ausencia
   T_Inicia(D'2026.10.07 10:00:00');
   Abre(R_GB, 1, 119900, 118700);
   Espera(1);
   for(int k = 0; k < 5; k++) F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Sair(R_GB);
   Passa(250);                                            // 1a X
   Espera(32);
   int n1 = mzRecusaN[R_GB][P_X];                         // a 1a ausencia conta
   Espera(150);                                           // 5 ausencias (~35 s cada); a 6a X executa
   Ok("B2-1: prova por ausencia conta na mesma sequencia de recusas: 1 apos a 1a; a 5a seguida dispara o ALERTA; RETENTA de 5 s mantida; a 6a X executa (uma saida so')",
      n1 == 1 && mzRecusaAlerta[R_GB][P_X] > 0 && NLinhas(R_GB, P_X) == 6 && ND() == 2 && mzEst[R_GB].f == 0);
}

void T_B2_2_SCruzRelogio(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   F.m_por_preco = true; F.m_stop_falha = true;           // stop atravessado que nao executa
   F.Move(118600, 118605);
   Sair(R_GB);
   Espera(2);                                             // a X3 espera a S cruzada
   Manter(R_GB, 118700, 0);                               // o modulo desiste da saida...
   F.Move(120000, 120005);                                // ...e o preco volta: a S deixa de estar cruzada
   Espera(40);
   bool semK = NLinhas(R_GB, P_K) == 0 && Vivo(s);
   F.Move(118600, 118605);                                // cruza de novo, 42 s depois do 1o cruzamento
   Sair(R_GB);
   Espera(2);
   bool espera = NLinhas(R_GB, P_K) == 0 && NLinhas(R_GB, P_X) == 0 && Vivo(s);   // o prazo conta deste cruzamento
   Espera(30);
   Ok("B2-2: SAIR com a S cruzada de novo respeita os 30 s contados do cruzamento atual (o relogio de um cruzamento anterior nao vale); depois K (X3) e a X",
      semK && espera && LinhaMot(R_GB, P_K, "X3") >= 0 && EH(s) == ORDER_STATE_CANCELED && NLinhas(R_GB, P_X) == 1 && mzEst[R_GB].f == 0);
}

void T_B2_3_EmergCruzada(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Manter(R_GB, 120100, 0);                               // nivel pedido atravessado: vale a S viva
   Passa(250);
   F.CancelaPorFora(s, ORDER_STATE_CANCELED);
   Passa(250);
   ulong e = TK(R_GB, ORDER_TYPE_SELL_STOP);              // S de emergencia (bid - 1.200), gravada
   bool emerg = e != 0 && PP(e) == 118800.0 && mzEmerg[R_GB] == 118800.0;
   F.m_por_preco = true; F.m_stop_falha = true;
   F.Move(118600, 118605);                                // a emergencia fica atravessada e nao executa
   F.m_recusa_magic = MG(R_GB); F.m_recusa_tipo = ORDER_TYPE_SELL;   // e a saida a mercado do GB e' recusada
   Sair(R_GB);
   Espera(32);                                            // 30 s: K da S cruzada (X3), S nova, X recusada
   ulong s2 = TK(R_GB, ORDER_TYPE_SELL_STOP);
   bool prot = EH(e) == ORDER_STATE_CANCELED && s2 != 0 && s2 != e && PP(s2) == 118590.0 && mzEmerg[R_GB] == 118800.0 &&
               NRecusadas(R_GB, P_X) >= 1 && mzEst[R_GB].f == 1;
   int rx = NRecusadas(R_GB, P_X);
   Espera(6);
   bool retenta = NRecusadas(R_GB, P_X) > rx && Vivo(s2) && PP(s2) == 118590.0;
   F.m_recusa_magic = 0;
   Espera(6);
   Ok("B2-3: emergencia atravessada e saida recusada -> S no primeiro nivel valido alem do preco (118590; a emergencia gravada nao muda); a X retenta a cada 5 s; aceita, a ficha zera e L3 cancela a S",
      emerg && prot && retenta && mzEst[R_GB].f == 0 && ND() == 2 && EH(s2) == ORDER_STATE_CANCELED);
}

void T_B2_4_AbsorveDono(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong sg = Abre(R_GB, 1, 119900, 118700);
   ulong sc = Abre(R_CM, 1, 119800, 118600);
   F.Roteiro(FM_TUDO_OCULTO);                             // a X do CM executa; historico e deal so' aparecem depois
   Sair(R_CM);
   Passa(250);
   Espera(36);
   // o Delta -1 e' explicado pela X do CM: so' a ficha do CM e' absorvida (o GB vem antes na ordem fixa e fica intacto);
   // sem a absorcao do CM, ele sairia de novo (2a X)
   bool virt = NLinhas(R_CM, P_X) == 1 && mzEst[R_CM].abs_virtual && mzEst[R_CM].f == 0 && mzEst[R_GB].f == 1 && !mzEst[R_GB].abs_virtual &&
               Vivo(sg) && Vivo(sc) && !mzBloqBotao;
   F.MostraOcultos();
   Passa(250);
   Ok("B2-4: absorcao virtual so' na ficha do robo cujo deal explica o Delta (CM, nao o GB da ordem fixa); nenhuma 2a X; o deal chega -> CM 0 e a S dele sai, GB intacto",
      virt && NLinhas(R_CM, P_X) == 1 && mzEst[R_CM].f == 0 && EH(sc) == ORDER_STATE_CANCELED && mzEst[R_GB].f == 1 && Vivo(sg) && ND() == 3);
}

void T_B2_5_ERecusadaAssinc(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   F.m_rej_magic = MG(R_GB); F.m_rej_tipo = ORDER_TYPE_BUY_LIMIT; F.m_rej_ms = 0;   // a E e' aceita (PLACED) e REJECTED depois
   long id = Entrar(R_GB, 1, 119900, 118700);
   Passa(250);
   int le = Linha(R_GB, P_E);
   Espera(6);
   Ok("B2-5: E aceita e REJECTED no historico -> ENTRADA_RECUSADA ao modulo (nao CANCELADA), uma vez; nenhuma E nova; L3 cancela a S",
      le >= 0 && LDesf(le) == D_NAO_EXECUTADA && gEvUlt[R_GB] == EV_ENTRADA_RECUSADA && gEvId[R_GB] == id && gEvN[R_GB] == 1 &&
      NLinhas(R_GB, P_E) == 1 && NP(R_GB, ORDER_TYPE_SELL_STOP) == 0);
}

void T_B2_6_PortaoRecasa(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   Espera(30);
   F.Roteiro(FM_TIMEOUT_TK0_NADA);
   Sair(R_GB);
   Passa(250);
   int lx = Linha(R_GB, P_X);                             // a X de ticket 0 que nunca chegou
   Espera(37);                                            // NAO_EXECUTADA por ausencia; a 2a X executa; L3 cancela a S
   bool base = LTk(lx) == 0 && LDesf(lx) == D_NAO_EXECUTADA && mzEst[R_GB].f == 0 && EH(s) == ORDER_STATE_CANCELED;
   long c0 = mzCasaChamadas;
   Espera(2);
   long c1 = mzCasaChamadas - c0;                         // toda ordem do GB esta' no mapa: o recasamento nao roda
   F.PendPorFora(MG(R_GB), ORDER_TYPE_SELL_LIMIT, 121000);   // controle: ordem do GB fora do mapa
   long c2 = mzCasaChamadas;
   Passa(250);
   Ok("B2-6: linha de ticket 0 NAO_EXECUTADA so' e' recasada com ordem do magic do dono fora do mapa (0 chamadas em 2 s sem ela); controle: com ela, roda",
      base && c1 == 0 && mzCasaChamadas > c2 && LTk(lx) == 0);
}

void T_M_Versao201(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   ulong s = Abre(R_GB, 1, 119900, 118700);
   int env = F.m_envios;
   Mae_Fim(REASON_PARAMETERS);
   Mae_Exporta(); Mem_Set("versao", "2.01"); Mem_Grava(true);    // a memoria como a 2.01 a gravou (mesmo formato)
   T_Base();
   Espera(15);
   bool le201 = !mzMemPerdida && mzEst[R_GB].sit == SIT_LEGITIMA && mzNivS[R_GB] == 118700.0 && F.m_envios == env && Vivo(s);
   Mae_Fim(REASON_PARAMETERS);
   Mae_Exporta(); Mem_Set("versao", "2.00"); Mem_Grava(true);    // controle: a da 2.00 (formato antigo) nao e' lida
   T_Base();
   Ok("v2.02: memoria gravada pela 2.01 (mesmo formato) e' lida na troca de versao (mapa, niveis); controle: a da 2.00 nao",
      le201 && mzMemPerdida);
}

//+------------------------------------------------------------------+
//| Adaptadores dos modulos (sec. 7)                                 |
//+------------------------------------------------------------------+
void T_Vista(const int r, const bool tem, const int lado, const double preco)
{
   ZeroMemory(mzVista[r]);
   mzVista[r].agora = mzAgora; mzVista[r].tem = tem; mzVista[r].lado = lado; mzVista[r].preco = preco; mzVista[r].hora = mzAgora; mzVista[r].id = 1;
}

void T_Mod_GB(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   WGB1::Reseta(); WGB1::Configura();
   WGB1::AlvoPts = 500;
   T_Vista(R_GB, true, 1, 120000);
   mzVista[R_GB].stop_pedido = 118800;
   Intencao i; Int_Manter(i, 118800, 0, "x");
   WGB1::GerirPosicao(mzVista[R_GB], i);
   Ok("GB: GerirPosicao -> MANTER(stop pedido, alvo = entrada + AlvoPts)", i.tipo == INT_MANTER && MathAbs(i.stop - 118800) < 1 && MathAbs(i.alvo - 120500) < 1);
   WGB1::Reseta(); WGB1::Configura();
   datetime agora = D'2026.10.07 09:40:00';
   WGB1::g_dkey = WGB1::DateKey(agora); WGB1::g_decidido = true; WGB1::g_exp = D'2026.10.07 09:35:00';
   T_Vista(R_GB, false, 0, 0);
   mzVista[R_GB].agora = agora;
   Intencao j; Int_Entrar(j, 5, 1, 119900, 118700, WGB1::g_exp, "x");
   WGB1::Tick(mzVista[R_GB], j);
   Ok("GB: depois de g_exp a ENTRAR vira NADA (o maestro cancela a E)", j.tipo == INT_NADA);
   T_Vista(R_GB, true, 1, 120000);
   Ok("GB: StopRegra(lado) = preco da ficha -/+ StopPts; 0 para o outro lado", MathAbs(WGB1::StopRegra(1) - 118800) < 1 && WGB1::StopRegra(-1) == 0.0);
}

void T_Mod_CM(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   WCM::Reseta(); WCM::Configura();
   Intencao i; Int_Manter(i, 100, 0, "x");
   WCM::Fecha(i, "teste");
   bool sair = i.tipo == INT_SAIR;
   WCM::Cancela(i, 0, "teste");
   Ok("CM: Fecha -> SAIR; Cancela -> NADA", sair && i.tipo == INT_NADA);
   WCM::g_stop_aperta = 118000; WCM::g_a_favor_ent = true; WCM::g_ultima_barra = D'2026.10.07 10:00:00';
   Mem_Limpa();
   WCM::Exporta();
   ArrayResize(mzCarK, ArraySize(mzMemK)); ArrayResize(mzCarV, ArraySize(mzMemV));
   for(int k = 0; k < ArraySize(mzMemK); k++) { mzCarK[k] = mzMemK[k]; mzCarV[k] = mzMemV[k]; }
   mzCarMesmoDia = true;
   WCM::Reseta();
   WCM::Importa();
   Ok("CM: Exporta/Importa do stop que aperta, a_favor e vela", WCM::g_stop_aperta == 118000.0 && WCM::g_a_favor_ent && WCM::g_ultima_barra == D'2026.10.07 10:00:00');
   T_Vista(R_CM, false, 0, 0);
   Ok("CM: StopRegra sem ficha = 0", WCM::StopRegra(1) == 0.0);
   // M-7: a posicao herda o "a favor do mes" da entrada que ENCHEU, nao da ultima pedida
   WCM::Reseta(); WCM::Configura();
   WCM::g_ped_id = 20; WCM::g_ped_favor = true; WCM::g_ped_id_ant = 10; WCM::g_ped_favor_ant = false;
   WCM::g_a_favor_ent = true; WCM::g_stop_aperta = 118000;
   SEvento e; e.ev = EV_ENTRADA_EXECUTADA; e.id_entrada = 10; e.preco = 119800; e.hora = mzAgora; e.motivo = "";
   Intencao k; Int_Manter(k, 0, 0, "x");
   WCM::Evento(e, mzVista[R_CM], k);
   bool ant = !WCM::g_a_favor_ent && WCM::g_stop_aperta == 0.0;
   WCM::g_stop_aperta = 118000; e.id_entrada = 99;
   WCM::Evento(e, mzVista[R_CM], k);
   bool alheio = !WCM::g_a_favor_ent && WCM::g_stop_aperta == 118000.0;
   WCM::g_mzh_dia_cache = 5;
   WCM::Reseta();
   Ok("CM (M-7/B-16): ENTRADA_EXECUTADA da entrada anterior ao rearme -> a_favor dela e o stop que aperta recomeca; id alheio nao mexe; o cache volta no Reseta",
      ant && alheio && WCM::g_mzh_dia_cache == -1 && WCM::g_ped_id == 0);
}

void T_Mod_Zeragem(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   WGB1::Configura(); WCM::Configura(); WDM::Configura(); WRE::Configura(); WC1::Configura();
   gReal = true;
   datetime d = D'2026.10.07 00:00:00';
   // DM (B-13): o horario dele vem da FimSessao do proprio modulo (sessao do simbolo; sem ela, os inputs) - MinutosZerar
   bool dia2525 = Dec_Zeragem(R_GB) == d + 1100 * 60 && Dec_Zeragem(R_CM) == d + 1100 * 60 &&
                  Dec_Zeragem(R_DM) == ZMin(d + WDM::MinutoZerarRobo(d) * 60, Mae_CDe(mzAgora)) &&
                  Dec_Zeragem(R_RE) == d + 1020 * 60 && Dec_Zeragem(R_C1) == d + 1070 * 60;
   mzAgora = D'2023.05.10 10:00:00';
   datetime d2 = D'2023.05.10 00:00:00';
   bool dia1755 = Dec_Zeragem(R_GB) == d2 + 1070 * 60 && Dec_Zeragem(R_CM) == d2 + 1070 * 60 &&
                  Dec_Zeragem(R_DM) == ZMin(d2 + WDM::MinutoZerarRobo(d2) * 60, Mae_CDe(mzAgora)) &&
                  Dec_Zeragem(R_RE) == d2 + 1020 * 60 && Dec_Zeragem(R_C1) == d2 + 1070 * 60;
   gReal = false;
   Ok("spec 9.2/D2: zeragem = min(horario do robo, corte): GB/CM/RE/C1 18:20/18:20/17:00/17:50 nos dias de 18:25 e 17:50/17:50/17:00/17:50 nos de 17:55; DM pela sessao dele",
      dia2525 && dia1755);
}

void T_Mod_DM(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   WDM::Reseta(); WDM::Configura();
   WDM::g_distStop = 500; WDM::g_id = 77; WDM::g_ordem = 1; WDM::g_stopAjustado = false;
   T_Vista(R_DM, true, -1, 10000000);
   SEvento e; e.ev = EV_ENTRADA_EXECUTADA; e.id_entrada = 77; e.preco = 10000000; e.hora = mzAgora; e.motivo = "";
   Intencao i; Int_Manter(i, 10000600, 0, "x");
   WDM::Evento(e, mzVista[R_DM], i);
   Ok("DM: ENTRADA_EXECUTADA -> AjustarStop: MANTER(stop reancorado = preco executado + distancia); g_ordem limpo no evento",
      i.tipo == INT_MANTER && MathAbs(i.stop - 10000500) < 1 && WDM::g_stopAjustado && WDM::g_ordem == 0);
   WDM::g_ordem = 1;
   e.ev = EV_ENTRADA_CANCELADA; e.id_entrada = 78;
   WDM::Evento(e, mzVista[R_DM], i);
   bool outro = WDM::g_ordem == 1;
   e.id_entrada = 77;
   WDM::Evento(e, mzVista[R_DM], i);
   Ok("DM: ENTRADA_CANCELADA so' limpa a entrada dele (id)", outro && WDM::g_ordem == 0);
   WDM::g_ordem = 1;
   Intencao j; Int_Entrar(j, 78, 1, 119800, 118600, 0, "x");
   WDM::CancelarEntrada(j, "prazo");
   bool alheia = j.tipo == INT_ENTRAR;
   Int_Entrar(j, 77, 1, 119800, 118600, 0, "x");
   WDM::CancelarEntrada(j, "prazo");
   Ok("DM: TTL -> NADA so' sobre a ENTRAR dele; g_ordem fica ate' o evento", alheia && j.tipo == INT_NADA && WDM::g_ordem == 1);
   // B-10: o nivel atravessado e' reavaliado a cada Tick (requer grafico com cotacao)
   WDM::Reseta(); WDM::Configura();
   WDM::g_stopAjustado = true; WDM::g_stopNivel = 100000000.0;   // comprado, nivel acima de qualquer cotacao: atravessado
   T_Vista(R_DM, true, 1, 120000);
   Intencao k; Int_Manter(k, 0, 0, "x");
   WDM::StopAtravessado(k);
   bool sai = k.tipo == INT_SAIR;
   WDM::g_stopNivel = 1.0;                                       // nivel abaixo de qualquer cotacao: nao atravessado
   Intencao m; Int_Manter(m, 0, 0, "x");
   WDM::StopAtravessado(m);
   Ok("DM (B-10): last alem de g_stopNivel em qualquer Tick -> SAIR (de novo, depois de uma SAIDA_EXPIRADA); aquem -> nada", sai && m.tipo == INT_MANTER);
   // B-13: a zeragem propria segue os inputs do DM (MinutosZerar)
   datetime d = D'2026.10.07 00:00:00';
   int esperado = (int)((WDM::FimSessao(d + 12 * 3600) - d) / 60) - WDM::MinutosZerar;
   int z1 = WDM::MinutoZerarRobo(d);
   WDM::MinutosZerar += 30;
   int z2 = WDM::MinutoZerarRobo(d);
   WDM::Configura();
   Ok("DM (B-13): zeragem propria = FimSessao do DM (sessao, ou HoraFimPregao:MinutoFimPregao) - MinutosZerar", z1 == esperado && z2 == z1 - 30);
}

void T_Mod_RE(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   WRE::Reseta(); WRE::Configura();
   WRE::g_id = 55; WRE::g_lado_entrada = WRE::RET_LONG; WRE::g_meio_original = 120000; WRE::g_stop_original = 119500; WRE::g_alvo_original = 120900;
   WRE::g_ordem_pendente = true;
   T_Vista(R_RE, true, 1, 120010);
   SEvento e; e.ev = EV_ENTRADA_EXECUTADA; e.id_entrada = 55; e.preco = 120010; e.hora = mzAgora; e.motivo = "";
   Intencao i; Int_Manter(i, 119500, 0, "x");
   WRE::Evento(e, mzVista[R_RE], i);
   Ok("RE: ENTRADA_EXECUTADA -> MANTER(stop e alvo reancorados pelo preco executado)",
      i.tipo == INT_MANTER && i.stop == 119510.0 && i.alvo == 120910.0 && WRE::g_ticket_alvo == 1 && !WRE::g_ordem_pendente && WRE::g_preco_entrada == 120010.0);
   WRE::Reseta(); WRE::Configura();
   WRE::g_id = 56; WRE::g_lado_entrada = WRE::RET_SHORT; WRE::g_meio_original = 121000; WRE::g_stop_original = 121500; WRE::g_alvo_original = 120100;
   // M-6: a entrada 55 foi rearmada TRES vezes (anel de 4): o fill tardio dela ainda acha os niveis dela.
   WRE::g_anel_id[0] = 55; WRE::g_anel_lado[0] = (int)WRE::RET_LONG; WRE::g_anel_meio[0] = 120000; WRE::g_anel_stop[0] = 119500; WRE::g_anel_alvo[0] = 120900;
   WRE::g_anel_id[1] = 57; WRE::g_anel_lado[1] = (int)WRE::RET_SHORT; WRE::g_anel_meio[1] = 121000; WRE::g_anel_stop[1] = 121400; WRE::g_anel_alvo[1] = 120200;
   WRE::g_anel_id[2] = 58; WRE::g_anel_lado[2] = (int)WRE::RET_SHORT; WRE::g_anel_meio[2] = 121000; WRE::g_anel_stop[2] = 121300; WRE::g_anel_alvo[2] = 120300;
   WRE::g_anel_pos = 3;
   T_Vista(R_RE, true, 1, 120000);
   e.id_entrada = 55; e.preco = 120000;
   Int_Nada(i, "x");
   WRE::Evento(e, mzVista[R_RE], i);
   Ok("RE (M-6): fill tardio de uma entrada 3 rearmes atras -> adota os niveis dela pelo anel",
      i.tipo == INT_MANTER && i.stop == 119500.0 && i.alvo == 120900.0 && WRE::g_lado_entrada == WRE::RET_LONG);
   e.id_entrada = 99; Int_Nada(i, "x");
   WRE::Evento(e, mzVista[R_RE], i);
   Ok("RE (M-6): fill de id fora do anel -> ignorado", i.tipo == INT_NADA);
   // M-6: o fill chega antes da posicao propria aparecer -> fica pendente e e' adotado no Tick.
   WRE::Reseta(); WRE::Configura();
   WRE::g_id = 70; WRE::g_lado_entrada = WRE::RET_LONG; WRE::g_meio_original = 120000; WRE::g_stop_original = 119500; WRE::g_alvo_original = 120900;
   T_Vista(R_RE, false, 0, 0);
   WRE::g_nb_ultima = iTime(_Symbol, WRE::TempoGrafico, 0);   // sem vela nova: o Tick so' faz a parte de fill/alvo
   e.id_entrada = 70; e.preco = 120020; Int_Nada(i, "x");
   WRE::Evento(e, mzVista[R_RE], i);
   bool pendente = i.tipo == INT_NADA && WRE::g_fill_id == 70;
   T_Vista(R_RE, true, 1, 120020);
   Int_Nada(i, "x");
   WRE::Tick(mzVista[R_RE], i);
   Ok("RE (M-6): fill sem posicao propria fica pendente e o Tick o adota quando a posicao aparece",
      pendente && WRE::g_fill_id == 0 && i.tipo == INT_MANTER && i.stop == 119520.0 && WRE::g_preco_entrada == 120020.0);
   // B-17: sem posicao, o alvo velho volta ao inicial.
   T_Vista(R_RE, false, 0, 0);
   WRE::g_ticket_alvo = 1; WRE::g_fill_id = 77; Int_Nada(i, "x");
   WRE::Tick(mzVista[R_RE], i);
   Ok("RE (B-17/M-6): sem posicao propria o estado do alvo volta ao inicial e o fill pendente e' descartado (nunca vai a uma posicao posterior)",
      WRE::g_ticket_alvo == 0 && WRE::g_largura_posicao == 0.0 && WRE::g_fill_id == 0 && i.tipo == INT_NADA);
   WRE::Reseta(); WRE::Configura();
   WRE::g_id = 60; WRE::g_ordem_pendente = true;
   Intencao j; Int_Entrar(j, 61, 1, 120000, 119500, 0, "x");
   WRE::CancelarEntradaPendente(j);
   bool alheia = j.tipo == INT_ENTRAR;
   WRE::g_ordem_pendente = true;
   Int_Entrar(j, 60, 1, 120000, 119500, 0, "x");
   WRE::CancelarEntradaPendente(j);
   bool propria = j.tipo == INT_NADA && !WRE::g_ordem_pendente;
   WRE::g_ticket_alvo = 1; WRE::g_tem_retangulo = true;
   Int_Entrar(j, 62, 1, 120000, 119500, 0, "x");
   WRE::ZerarPregao(j);
   Ok("RE: CancelarEntradaPendente so' sobre a ENTRAR dele; ZerarPregao -> NADA e o estado do robo volta ao inicial",
      alheia && propria && j.tipo == INT_NADA && WRE::g_ticket_alvo == 0 && !WRE::g_tem_retangulo);
}

void T_Mod_C1(void)
{
   T_Inicia(D'2026.10.07 10:00:00');
   WC1::Reseta(); WC1::Configura();
   mzPartidaMsc = 0;
   Intencao i; Int_Nada(i, "x");
   WC1::Entra(i, 1, -1000000.0, 100.0);
   Ok("C1: Entra -> ENTRAR a mercado (limite 0) com o stop da regra (requer grafico com cotacao)", i.tipo == INT_ENTRAR && i.limite == 0.0 && i.lado == 1 && i.stop < 0.0);
   mzPartidaMsc = (long)(TimeCurrent() + 365 * 86400) * 1000;
   Intencao j; Int_Nada(j, "x");
   WC1::Entra(j, 1, -1000000.0, 100.0);
   Ok("C1: decisao anterior a' partida = DECISAO PERDIDA (a intencao nao muda)", j.tipo == INT_NADA);
   T_Vista(R_C1, false, 0, 0);
   Ok("C1: StopRegra sem ficha = 0; zeragem propria 17:50", WC1::StopRegra(1) == 0.0 && WC1::MinutoZerarRobo(D'2026.10.07 00:00:00') == 17 * 60 + 50);
}

//+------------------------------------------------------------------+
int OnInit()
{
   Print("WinMaestro_Teste v2.02: inicio");
   T_P1_E1();
   T_P1_Recria();
   T_P1_SemHistorico();
   T_P1_Inequivoco();
   T_P1_Retenta();
   T_P1_ForaDaJanela();
   T_P2();
   T_P3();
   T_Nivel_Emergencia();
   T_Nivel_Referencia();
   T_A1_X1_X3_L3();
   T_X2();
   T_X3_SCruzada();
   T_X3_Recusada();
   T_L1();
   T_L2();
   T_L3_OCO();
   T_L3_Restrito();
   T_L4();
   T_A2();
   T_E1_Consumido();
   T_E1_O2();
   T_Z();
   T_I1();
   T_I2_Trocada();
   T_I2_Duplicada();
   T_I3_Zeragem();
   T_I3_SRecusada();
   T_I4();
   T_I5();
   T_PrazoEntrar();
   T_PrazoSair();
   T_C_RequestId();
   T_C_HistFilled();
   T_C_AusenciaTk0();
   T_C_AindaNaoListada();
   T_C_Sumida();
   T_C_DealVence();
   T_C_FilledSemDeal();
   T_C_KExecutouAntes();
   T_C_P4();
   T_DeltaVirtual();
   T_NaoClassificado();
   T_K_Conta();
   T_K_Recusa();
   T_K_DepoisDeF();
   T_K_SemHistorico();
   T_K_MercadoRecente();
   T_Trava_Parada();
   T_Trava_MesmoToken();
   T_Trava_Avancando();
   T_Trava_Perdida();
   T_M_Reinicio();
   T_M_SemMemoriaSemLog();
   T_M_MapaDoLog();
   T_M_NaoGrava();
   T_M_OutraConta();
   T_Amb_Hedging();
   T_Amb_Protegendo();
   T_Amb_Parado();
   T_Cen_a();
   T_Cen_b(true);
   T_Cen_b(false);
   T_Cen_c();
   T_Cen_d();
   T_Cen_e();
   T_Cen_f();
   T_Cen_g(true);
   T_Cen_g(false);
   T_Cen_h();
   T_Cen_i();
   T_Cen_j();
   T_Cen_k(false);
   T_Cen_k(true);
   T_Cen_l();
   T_Cen_m();
   T_Cen_n();
   T_Revisao_Regressoes();
   T_A1_ExtDescDia();
   T_A1_ExtDescZera();
   T_A2_RecusaAssinc();
   T_K_SVivas();
   T_KM_Assinc();
   T_Trans();
   T_Preco_Corrida();
   T_M1_DeltaEstavel();
   T_M2_EntregaId();
   T_M3_RearmeMesmoLado();
   T_M4_Relogio();
   T_B1_CasaTardia();
   T_B2_Retcode0();
   T_B3_SValida();
   T_B4_RecuoEstavel();
   T_B8_PrefereViva();
   T_B9_SFaltaInvalido();
   T_B19_DecisaoAtrasada();
   T_B2_1_AusenciaConta();
   T_B2_2_SCruzRelogio();
   T_B2_3_EmergCruzada();
   T_B2_4_AbsorveDono();
   T_B2_5_ERecusadaAssinc();
   T_B2_6_PortaoRecasa();
   T_M_Versao201();
   T_Mod_GB();
   T_Mod_CM();
   T_Mod_Zeragem();
   T_Mod_DM();
   T_Mod_RE();
   T_Mod_C1();
   PrintFormat("WinMaestro_Teste v2.02: %d PASSOU, %d FALHOU%s", gPassou, gFalhou, gFalhou > 0 ? "; falharam:" + gFalhas : "");
   if(F != NULL) { delete F; F = NULL; }
   mzCorr = NULL;
   Log_Fecha();
   FolderClean("WinMaestro_unit", 0);
   ExpertRemove();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { if(F != NULL) { delete F; F = NULL; } mzCorr = NULL; }
void OnTick() { }
//+------------------------------------------------------------------+
