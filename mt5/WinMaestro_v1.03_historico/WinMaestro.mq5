//+------------------------------------------------------------------+
//| WinMaestro.mq5                                                   |
//| EA unico para o MINI INDICE (WIN), conta NETTING: roda os 5 robos|
//| (GB, CM, DM, RE, C1) ao mesmo tempo, cada um com a sua FICHA     |
//| (posicao virtual = soma dos deals com o magic dele) e mandando as|
//| ordens dele com o magic dele. Especificacao: mt5/WinMaestro_     |
//| ESPECIFICACAO.md v1.0 (2026-10-07). Aposenta o WinSeletor.       |
//|                                                                  |
//| v1.03 (2026-10-07).                                              |
//|  Robos (logica de sinal dos EAs avulsos; so' a execucao mudou):  |
//|   GB WinGapBarra1           M5   magic 80080601                  |
//|   CM WinCincoMedias         H2   magic 80080501                  |
//|   DM WinDeslocamentoMatinal M1   magic 80080101                  |
//|   RE WinRetanguloEma34      M15  magic 20261005                  |
//|   C1 Win_c1                 H1   magic 80080002                  |
//|  - Toda entrada nasce com o stop na corretora (ordem stop S com o|
//|    magic do robo). Uma operacao por vez por robo.                |
//|  - Antes de toda ordem: liquida, ordens vivas e historico tem de |
//|    fechar (D1). Corte global = fim do continuo - 5 min (D2).     |
//|  - Uma instancia so', num grafico so' (D3). Qualquer tempo serve.|
//+------------------------------------------------------------------+
#property copyright "WinMaestro"
#property version   "1.03"
#property description "WinMaestro v1.03: os 5 robos do WIN ao mesmo tempo, cada um com a sua ficha e o seu magic (conta NETTING)"
#property strict

#include "WinMaestro\Inputs.mqh"
#include "WinMaestro\Corretora.mqh"
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


//+------------------------------------------------------------------+
//| Ganchos do nucleo (Fichas.mqh / Recupera.mqh)                    |
//+------------------------------------------------------------------+
void Robo_Evento(const int r, const int ev)
{
   switch(r)
   {
      case R_GB: WGB1::Evento(ev); break;
      case R_CM: WCM::Evento(ev);  break;
      case R_DM: WDM::Evento(ev);  break;
      case R_RE: WRE::Evento(ev);  break;
      case R_C1: WC1::Evento(ev);  break;
   }
}

// Horario proprio de zeragem do robo (min do dia); o maestro limita ao corte (sec. 9.2).
int Robo_MinutoZerar(const int r, const datetime dia)
{
   switch(r)
   {
      case R_GB: return GB_FlattenHora * 60 + GB_FlattenMinuto;
      case R_CM: return CM_HoraZerar * 60 + CM_MinutoZerar;
      case R_DM: return (int)((Mae_FDe(dia) - dia) / 60) - DM_MinutosZerar;     // "sessao - 5 min" pela grade
      case R_RE: return RE_HoraZerar * 60 + RE_MinutoZerar;
      case R_C1: return C1_HoraFimPregao * 60 + C1_MinutoFimPregao - C1_MinutosZerar;
   }
   return 0;
}

double Robo_StopRegra(const int r)
{
   switch(r)
   {
      case R_GB: return WGB1::StopRegra();
      case R_CM: return WCM::StopRegra();
      case R_DM: return WDM::StopRegra();
      case R_RE: return WRE::StopRegra();
      case R_C1: return WC1::StopRegra();
   }
   return 0.0;
}

void Robo_Exporta(void)
{
   if(!mzModulosIniciados) { Car_CopiaModulos(); return; }   // modulos ainda nao iniciaram: preserva o que foi lido
   WGB1::Exporta();
   WCM::Exporta();
   WDM::Exporta();
   WRE::Exporta();
   WC1::Exporta();
}

int Robo_Init(const int r)
{
   switch(r)
   {
      case R_GB: return WGB1::Init();
      case R_CM: return WCM::Init();
      case R_DM: return WDM::Init();
      case R_RE: return WRE::Init();
      case R_C1: return WC1::Init();
   }
   return INIT_FAILED;
}

void Robo_InitTodos(void)
{
   for(int r = 0; r < NROBOS; r++)
   {
      int ini = Robo_Init(r);
      mzFalhou[r] = (ini != INIT_SUCCEEDED);
      if(mzFalhou[r]) Log("ALERTA", mzNome[r], "PRONTO", StringFormat("Init do modulo falhou (codigo %d, veja os inputs): sem Tick e sem entrada; o maestro segue protegendo", ini));
      else Log("INFO", mzNome[r], "PRONTO", "modulo iniciado");
   }
}

void Robo_Tick(const int r)
{
   switch(r)
   {
      case R_GB: WGB1::Tick(); break;
      case R_CM: WCM::Tick();  break;
      case R_DM: WDM::Tick();  break;
      case R_RE: WRE::Tick();  break;
      case R_C1: WC1::Tick();  break;
   }
}

void Robo_Deinit(const int r, const int reason)
{
   switch(r)
   {
      case R_GB: WGB1::Deinit(reason); break;
      case R_CM: WCM::Deinit(reason);  break;
      case R_DM: WDM::Deinit(reason);  break;
      case R_RE: WRE::Deinit(reason);  break;
      case R_C1: WC1::Deinit(reason);  break;
   }
}

string Mae_PastaLimpa(const string s)
{
   string t = s;
   string ruins = "\\/:*?\"<>| ";
   for(int i = 0; i < StringLen(ruins); i++) StringReplace(t, StringSubstr(ruins, i, 1), "_");
   return t;
}

//+------------------------------------------------------------------+
int OnInit()
{
   // P17: tudo reinicializado explicitamente (variaveis globais podem sobreviver a PARAMETERS/CHARTCHANGE)
   Fichas_Reseta();
   mzTravaNome = ""; mzHbNome = ""; mzToken = 0.0; mzPasso = 0; mzPassoDesde = 0; mzPassoLog = 0; mzPassoAlertou = false; mzAmbUlt = 0;
   mzUltSegundo = 0;
   WGB1::Reseta(); WCM::Reseta(); WDM::Reseta(); WRE::Reseta(); WC1::Reseta();
   WGB1::Configura(); WCM::Configura(); WDM::Configura(); WRE::Configura(); WC1::Configura();

   if(mzCorr != NULL) delete mzCorr;
   mzCorr = new CCorretoraReal();

   mzAtivo[R_GB] = Ativo_GB; mzAtivo[R_CM] = Ativo_CM; mzAtivo[R_DM] = Ativo_DM; mzAtivo[R_RE] = Ativo_RE; mzAtivo[R_C1] = Ativo_C1;
   // magics fixos da especificacao (sec. 1), nao sao input: trocar o magic com o robo posicionado orfanaria a ficha (M-8)

   string pasta;
   if(mzCorr.Testador())
   {
      pasta = "WinMaestro_teste\\";
      FolderClean("WinMaestro_teste", 0);                 // apagada no inicio de cada teste (sec. 10.1)
   }
   else
      pasta = "WinMaestro\\" + Mae_PastaLimpa(mzCorr.ContaS(ACCOUNT_SERVER)) + "_" +
              StringFormat("%I64d", mzCorr.ContaI(ACCOUNT_LOGIN)) + "_" + Mae_PastaLimpa(_Symbol) + "\\";
   FolderCreate(StringSubstr(pasta, 0, StringLen(pasta) - 1));
   FolderCreate(pasta + "logs");
   Log_Pasta(pasta);
   mzMemPasta = pasta;

   mzPartidaEm = Mae_Agora();
   Log("INFO", "MAESTRO", "INICIO", StringFormat("WinMaestro v1.03 em %s; ligados: GB %s CM %s DM %s RE %s C1 %s; pasta %s",
       _Symbol, Ativo_GB ? "sim" : "nao", Ativo_CM ? "sim" : "nao", Ativo_DM ? "sim" : "nao", Ativo_RE ? "sim" : "nao", Ativo_C1 ? "sim" : "nao", pasta));
   Recupera_Inicia();
   EventSetMillisecondTimer(250);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(mzCorr != NULL) Log("INFO", "MAESTRO", "FIM", StringFormat("reason %d", reason));
   if(mzIniciou && mzCorr != NULL)
   {
      Mae_GravaMemoria(true);
      if(reason != REASON_PARAMETERS && reason != REASON_CHARTCHANGE && reason != REASON_TEMPLATE) Trava_Libera();
      for(int r = 0; r < NROBOS; r++) Robo_Deinit(r, reason);
      Mae_BotaoMostra(false);
      Comment("");
   }
   Log_Fecha();
   if(mzCorr != NULL) { delete mzCorr; mzCorr = NULL; }
}

void OnTimer()
{
   Mae_OnTimer();
}

void OnTick()
{
   if(mzCorr == NULL) return;
   if(mzPasso > 0 && mzPasso < 12 && mzCorr.Testador()) Recupera_Completa();   // Testador: PRONTO antes da 1a barra
   if(mzPasso < 12) return;
   for(int r = 0; r < NROBOS; r++)
      if(Mae_PodeTick(r)) Robo_Tick(r);
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   Mae_OnTradeTransaction(trans, request, result);
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_CLICK && mzCorr != NULL) Mae_BotaoClique(sparam);
}
//+------------------------------------------------------------------+
