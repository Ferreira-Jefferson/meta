//+------------------------------------------------------------------+
//| WinMaestro/Risco.mqh                                             |
//| v2.03 (2026-10-08): parada diaria, decidida pelo dono.           |
//|  Quando o resultado liquido realizado do dia dos robos chega a   |
//|  -Risco_PerdaDiaPct % do capital (Risco_Capital, input fixo; nao |
//|  e' o saldo), nenhuma entrada nova ate' o pregao seguinte: as E  |
//|  vivas nao executadas sao canceladas; as posicoes seguem (S,     |
//|  saida, zeragem, corte).                                         |
//| Ligar: o resultado sai dos deals do dia no snapshot (sobrevive a |
//| reinicio e funciona no Testador), por robo, calculado junto com  |
//| as fichas (Estado.mqh: Est_Fichas, contas puras em               |
//| RiscoRegra.mqh). Ligada, fica travada em RAM ate' o dia virar    |
//| (mzBloqDiaDia): uma re-derivacao do historico no meio do pregao  |
//| (botao, recuo da janela, externa que cai, historico incompleto)  |
//| nao a desfaz. Nada e' gravado na memoria.                        |
//| Onde entra no fluxo: Risco_Dia() no passo 3 (Mae_CicloUm, depois |
//| de Est_Prazos) liga mzBloqDia, que entra em Mae_Bloqueio(): I4   |
//| (intencao NADA com ficha 0 -> L1 cancela a E viva) e pode_entrar |
//| (nenhuma E nova). Nao exige o botao.                             |
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_RISCO_MQH
#define WINMAESTRO_RISCO_MQH

#include "Envia.mqh"
#include "RiscoRegra.mqh"

//--- RAM (resultado refeito a cada ciclo com o historico lido; a parada fica travada no dia em que ligou)
double   mzResDia = 0.0;          // resultado liquido realizado do dia dos robos (R$)
double   mzResDiaR[NROBOS];       // o mesmo por robo
bool     mzBloqDiaLog = false;    // ultimo estado da parada ja' logado
datetime mzBloqDiaDia = 0;        // dia (Mae_Dia) em que a parada ligou; 0 = nao ligou

double Risco_LimiteDia(void)      { return Risco_Capital * Risco_PerdaDiaPct / 100.0; }
double Risco_Pct(const double rs) { return Risco_Capital > 0.0 ? 100.0 * rs / Risco_Capital : 0.0; }

// "GB +0.00 CM -12.40 ..." (painel e log)
string Risco_PorRobo(void)
{
   string s = "";
   for(int r = 0; r < NROBOS; r++) s += StringFormat("%s%s %+.2f", r > 0 ? " " : "", mzNome[r], mzResDiaR[r]);
   return s;
}

// Passo 3: resultado liquido realizado do dia dos robos = o que Est_Fichas realizou HOJE por robo, cada um como se tivesse
// conta propria (preco medio da ficha; saida pelo proprio deal, pela absorcao de zeragem manual ao preco do deal externo, ou
// pelo C_CONTA ao preco dele), mais comissao + taxa + swap dos deals do robo. Nunca o DEAL_PROFIT: em NETTING ele e' o da
// posicao liquida que o deal reduziu (de outro robo ou do dono). Posicao aberta (flutuante) nao entra. A parada liga pelo
// PIOR acumulado do dia (um evento por deal) e, ligada, fica travada em RAM ate' o pregao seguinte (dia novo em mzAgora),
// mesmo que um gain depois traga o resultado de volta ou que o historico re-derivado deixe de mostrar a perda. Depois de
// reinicio ou no Testador ela volta a ligar pelo historico do dia. Sem historico lido o resultado fica o ultimo calculo e a
// trava vale (sem historico nenhum robo e' confiavel e nenhuma entrada sai de qualquer forma). Risco_PerdaDiaPct = 0 (o EA
// reinicia, Mae_Reseta) desfaz: saida de emergencia do dono.
void Risco_Dia(void)
{
   bool ligada = Risco_PerdaDiaPct > 0.0 && Risco_Capital > 0.0;
   datetime hoje = Mae_Dia(mzAgora);
   bool bloq = ligada && mzBloqDiaDia == hoje;                 // travada hoje
   double run = mzResDia, pior = 0.0;
   if(mzHistOk)
   {
      Risco_Acumula(eResEv, run, pior);                        // eResEv: um evento por deal de hoje, na ordem do historico (Est_Fichas)
      mzResDia = run;
      for(int r = 0; r < NROBOS; r++) mzResDiaR[r] = eResR[r];
      if(ligada && Risco_ParadaDe(pior, Risco_Capital, Risco_PerdaDiaPct)) bloq = true;
   }
   if(bloq) mzBloqDiaDia = hoje;
   if(bloq && !mzBloqDiaLog)
      Log("ALERTA", "MAESTRO", "RISCO", StringFormat("parada diaria LIGADA: resultado do dia chegou a R$%.2f (%.2f%%; agora R$%.2f = %s), limite -%.2f%% de R$%.0f = -R$%.2f: "
          "entradas vivas canceladas e nenhuma nova ate' o pregao seguinte; posicoes seguem", pior, Risco_Pct(pior), run, Risco_PorRobo(),
          Risco_PerdaDiaPct, Risco_Capital, Risco_LimiteDia()));
   else if(!bloq && mzBloqDiaLog)
      Log("INFO", "MAESTRO", "RISCO", StringFormat("parada diaria DESLIGADA (%s): resultado do dia R$%.2f",
          !ligada ? "desligada nos inputs" : "pregao novo " + TimeToString(hoje, TIME_DATE), mzResDia));
   if(!bloq) mzBloqDiaDia = 0;
   mzBloqDiaLog = bloq;
   mzBloqDia = bloq;
}

#endif
