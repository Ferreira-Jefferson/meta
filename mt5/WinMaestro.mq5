//+------------------------------------------------------------------+
//| WinMaestro.mq5                                                   |
//| EA unico para o MINI INDICE (WIN), conta NETTING: roda os 5 robos|
//| (GB, CM, DM, RE, C1) ao mesmo tempo, cada um com a sua FICHA     |
//| (posicao virtual = soma dos deals com o magic dele) e mandando as|
//| ordens dele com o magic dele.                                    |
//|                                                                  |
//| v2.02 (2026-10-07): todos os achados da revisao de codigo 2      |
//| (mt5/WinMaestro_v2_revisao_codigo_2.md); ver as notas.           |
//| v2.01 (2026-10-07): todos os achados da revisao de codigo 1      |
//| (mt5/WinMaestro_v2_revisao_codigo_1.md); ver as notas.           |
//| v2.00 (2026-10-07). Nucleo novo: desenho mt5/WinMaestro_         |
//| ARQUITETURA_v2.md (v2.2) sobre a especificacao 1.0.              |
//|  - Os modulos declaram a INTENCAO; a cada ciclo o nucleo le UM   |
//|    snapshot, casa as ordens enviadas com a corretora (mapa       |
//|    ticket -> papel persistido), deriva fichas e confianca, e faz |
//|    no maximo UMA acao por robo, pela tabela de prioridade fixa:  |
//|    protecao > saida > limpeza > alvo > entrada.                  |
//|  - A partir de C + 2 min (C = fim do continuo - 5 min) so' o     |
//|    motor da conta age, com a base (sem historico).               |
//|  - Uma instancia so', num grafico so'. Qualquer tempo serve.     |
//|  Robos (logica de sinal dos EAs avulsos):                        |
//|   GB WinGapBarra1 M5 80080601 | CM WinCincoMedias H2 80080501    |
//|   DM WinDeslocamentoMatinal M1 80080101 | RE WinRetanguloEma34   |
//|   M15 20261005 | C1 Win_c1 H1 80080002                           |
//+------------------------------------------------------------------+
#property copyright "WinMaestro"
#property version   "2.02"
#property description "WinMaestro v2.02: os 5 robos do WIN ao mesmo tempo, cada um com a sua ficha e o seu magic (conta NETTING)"
#property strict

#include "WinMaestro\Inputs.mqh"
#include "WinMaestro\Partida.mqh"
#include "WinMaestro\WinGapBarra1.mqh"
#include "WinMaestro\WinCincoMedias.mqh"
#include "WinMaestro\WinDeslocamentoMatinal.mqh"
#include "WinMaestro\WinRetanguloEma34.mqh"
#include "WinMaestro\Win_c1.mqh"

//+------------------------------------------------------------------+
//| Ganchos do nucleo -> modulos (desenho sec. 7)                    |
//+------------------------------------------------------------------+
int Robo_Init(const int r, const VistaRobo &v)
{
   switch(r)
   {
      case R_GB: return WGB1::Init(v);
      case R_CM: return WCM::Init(v);
      case R_DM: return WDM::Init(v);
      case R_RE: return WRE::Init(v);
      case R_C1: return WC1::Init(v);
   }
   return INIT_FAILED;
}

void Robo_Tick(const int r, const VistaRobo &v, Intencao &i)
{
   switch(r)
   {
      case R_GB: WGB1::Tick(v, i); break;
      case R_CM: WCM::Tick(v, i);  break;
      case R_DM: WDM::Tick(v, i);  break;
      case R_RE: WRE::Tick(v, i);  break;
      case R_C1: WC1::Tick(v, i);  break;
   }
}

void Robo_Evento(const int r, const SEvento &e, const VistaRobo &v, Intencao &i)
{
   switch(r)
   {
      case R_GB: WGB1::Evento(e, v, i); break;
      case R_CM: WCM::Evento(e, v, i);  break;
      case R_DM: WDM::Evento(e, v, i);  break;
      case R_RE: WRE::Evento(e, v, i);  break;
      case R_C1: WC1::Evento(e, v, i);  break;
   }
}

double Robo_StopRegra(const int r, const int lado)
{
   switch(r)
   {
      case R_GB: return WGB1::StopRegra(lado);
      case R_CM: return WCM::StopRegra(lado);
      case R_DM: return WDM::StopRegra(lado);
      case R_RE: return WRE::StopRegra(lado);
      case R_C1: return WC1::StopRegra(lado);
   }
   return 0.0;
}

int Robo_MinutoZerar(const int r, const datetime dia)
{
   switch(r)
   {
      case R_GB: return WGB1::MinutoZerarRobo(dia);
      case R_CM: return WCM::MinutoZerarRobo(dia);
      case R_DM: return WDM::MinutoZerarRobo(dia);
      case R_RE: return WRE::MinutoZerarRobo(dia);
      case R_C1: return WC1::MinutoZerarRobo(dia);
   }
   return 0;
}

// Modulo iniciado: Exporta(); ainda sem Init: preserva as chaves dele como foram carregadas.
void Robo_Exporta(const int r)
{
   if(!mzInit[r]) { Car_CopiaPrefixo(mzNome[r] + "."); return; }
   switch(r)
   {
      case R_GB: WGB1::Exporta(); break;
      case R_CM: WCM::Exporta();  break;
      case R_DM: WDM::Exporta();  break;
      case R_RE: WRE::Exporta();  break;
      case R_C1: WC1::Exporta();  break;
   }
}

void Robo_Deinit(const int r, const int reason)
{
   if(!mzInit[r]) return;
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
   for(int k = 0; k < StringLen(ruins); k++) StringReplace(t, StringSubstr(ruins, k, 1), "_");
   return t;
}

//+------------------------------------------------------------------+
int OnInit()
{
   // P17: tudo reinicializado explicitamente (variaveis globais podem sobreviver a PARAMETERS/CHARTCHANGE)
   Mae_Reseta();
   WGB1::Reseta(); WCM::Reseta(); WDM::Reseta(); WRE::Reseta(); WC1::Reseta();
   WGB1::Configura(); WCM::Configura(); WDM::Configura(); WRE::Configura(); WC1::Configura();

   if(mzCorr != NULL) delete mzCorr;
   mzCorr = new CCorretoraReal();

   mzAtivo[R_GB] = Ativo_GB; mzAtivo[R_CM] = Ativo_CM; mzAtivo[R_DM] = Ativo_DM; mzAtivo[R_RE] = Ativo_RE; mzAtivo[R_C1] = Ativo_C1;
   mzSemTrava = mzCorr.Testador();          // P16: no Testador a trava e' pulada
   mzTela = true;
   mzLogImprime = true; mzLogAlert = true;

   string pasta;
   if(mzCorr.Testador())
   {
      pasta = "WinMaestro_teste\\";
      FolderClean("WinMaestro_teste", 0);                 // apagada no inicio de cada teste (spec 10.1)
   }
   else
      pasta = "WinMaestro\\" + Mae_PastaLimpa(mzCorr.ContaS(ACCOUNT_SERVER)) + "_" +
              StringFormat("%I64d", mzCorr.ContaI(ACCOUNT_LOGIN)) + "_" + Mae_PastaLimpa(_Symbol) + "\\";
   FolderCreate(StringSubstr(pasta, 0, StringLen(pasta) - 1));
   FolderCreate(pasta + "logs");
   Log_Pasta(pasta);
   mzMemPasta = pasta;

   Log("INFO", "MAESTRO", "INICIO", StringFormat("WinMaestro v%s em %s; ligados: GB %s CM %s DM %s RE %s C1 %s; pasta %s", WM_VERSAO,
       _Symbol, Ativo_GB ? "sim" : "nao", Ativo_CM ? "sim" : "nao", Ativo_DM ? "sim" : "nao", Ativo_RE ? "sim" : "nao", Ativo_C1 ? "sim" : "nao", pasta));
   Mae_Partida();
   EventSetMillisecondTimer(250);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(mzCorr != NULL) Mae_Fim(reason);
   for(int r = 0; r < NROBOS; r++) Robo_Deinit(r, reason);
   Log_Fecha();
   if(mzCorr != NULL) { delete mzCorr; mzCorr = NULL; }
}

void OnTimer()  { Mae_Ciclo(); }
void OnTick()   { Mae_Ciclo(); }

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   Mae_OnTradeTransaction(trans, request, result);
}

void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_CLICK && mzCorr != NULL) Mae_BotaoClique(sparam);
}
//+------------------------------------------------------------------+
