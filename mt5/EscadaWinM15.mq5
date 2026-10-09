//+------------------------------------------------------------------+
//| EscadaWinM15.mq5 — robô escada de topos e fundos no WIN, M15,    |
//| versão v4.1 (adotada em 2026-10-08).                             |
//|                                                                  |
//| Port de scripts/daytrade/topos_fundos/ (Python). Cada módulo em  |
//| EscadaWinM15/ tem o mesmo papel do arquivo .py de mesmo assunto: |
//|   Calendario  grade da B3 (fim do contínuo) e vencimentos        |
//|   Barras      M15 do contínuo montado do M1, TR e ATR(14)        |
//|   Indicadores médias, estocástico, tendência H1 e H4             |
//|   Escada      pivôs ZigZag 1,5 ATR e estágio da escada           |
//|   Filtros     os 5 filtros de entrada                            |
//|   Stop        stop inicial (MME38) e movimento pela estrutura    |
//|   Ordens      entrada limitada, cancelamento, stop, zeragem      |
//|   Registro    CSV das negociações                                |
//|                                                                  |
//| REGRA                                                            |
//|  1. Fundo confirmado acima do anterior (estágio >= 1) -> compra; |
//|     topo abaixo do anterior -> venda.                            |
//|  2. Filtros a favor: H1 (MME 9/21/34), lado da abertura do dia,  |
//|     MMS17 x MMS34, MMS72 do open inclinada, e sinal bom          |
//|     (Estocástico 14 < 70 a favor OU H4 neutro).                  |
//|  3. Ordem limitada no close da barra de confirmação, 2 contratos,|
//|     válida por 3 barras; stop junto, no servidor.                |
//|  4. Stop no pivô, apertado até 0,2 ATR além da MME38; sobe a cada|
//|     novo pivô a favor. Sem alvo. Zera 5 min antes do fim do      |
//|     contínuo. Uma posição por vez.                               |
//|                                                                  |
//| Rodar em WIN$N (Testador) ou no contrato vigente; qualquer tempo |
//| gráfico (o EA monta o M15 sozinho a partir do M1).               |
//+------------------------------------------------------------------+
#property copyright "EscadaWinM15"
#property version   "1.00"
#property strict

#include "EscadaWinM15/Calendario.mqh"
#include "EscadaWinM15/Barras.mqh"
#include "EscadaWinM15/Indicadores.mqh"
#include "EscadaWinM15/Escada.mqh"
#include "EscadaWinM15/Filtros.mqh"
#include "EscadaWinM15/Stop.mqh"
#include "EscadaWinM15/Ordens.mqh"
#include "EscadaWinM15/Registro.mqh"

input double Lotes       = 2;          // Contratos por operação
input ulong  MagicNumber = 41041015;   // Código que identifica as ordens deste robô

#define DIAS_AQUECIMENTO 120            // histórico lido na partida para as médias e o H4 já valerem

datetime g_ult_minuto = 0;

//=================== decisões a cada M15 fechada ===================
//--- Com posição aberta: se a barra confirmou um pivô a favor, o stop sobe para ele.
void GerenciaPosicao(int i, const Pivo &piv[])
{
   if(!TemPosicao(MagicNumber)) return;
   int p = PivoConfirmadoEm(piv, i);
   if(p < 0) return;
   double novo = StopPelaEstrutura(StopDaPosicao(), piv[p], LadoDaPosicao());
   MoveStop(novo, MagicNumber);
}

//--- Sem posição nem entrada pendente: a barra confirmou um pivô que vira sinal da v4.1?
void ProcuraEntrada(int i, const Pivo &piv[])
{
   if(TemPosicao(MagicNumber) || TemEntradaPendente() || PosicaoDeOutro(MagicNumber)) return;
   int p = PivoConfirmadoEm(piv, i);
   if(p < 0) return;
   int est = Estagio(piv, p);
   if(est == SEM_ESTAGIO || est < 1) return;
   if(g_barras[i].t + SEG_BARRA >= HoraCorte(g_barras[i].dia)) return;   // sem tempo de pregão para operar
   int lado = LadoDoPivo(piv[p]);
   if(!PassaFiltrosV41(i, lado)) return;
   double limite = g_barras[i].c, stop = StopInicialV41(i, lado, piv[p].preco);
   if((limite - stop) * lado <= 0) return;
   string motivo = StringFormat("escada %s est%d", lado == 1 ? "compra" : "venda", est);
   PrintFormat("SINAL %s: confirmação %s, limite %.0f, stop %.0f (pivô %.0f)", motivo,
               TimeToString(g_barras[i].t, TIME_DATE | TIME_MINUTES), limite, stop, piv[p].preco);
   EnviaEntrada(lado, limite, stop, Lotes, i, motivo);
}

//--- Uma M15 acabou de fechar: atualiza indicadores e, se for ao vivo, decide.
void AoFecharBarra(int i, bool ao_vivo)
{
   AtualizaIndicadores(i);
   if(!ao_vivo) return;
   Pivo piv[];
   ZigZag(InicioDoDia(i), i, piv);
   VenceEntrada(i);
   GerenciaPosicao(i, piv);
   ProcuraEntrada(i, piv);
}

//--- Lê os minutos novos e processa as M15 que fecharam. Só a mais recente decide (as outras são atraso de dados).
void Sincroniza(bool ao_vivo)
{
   int novas[];
   int n = SincronizaBarras(TimeCurrent(), novas);
   for(int k = 0; k < n; k++) AoFecharBarra(novas[k], ao_vivo && k == n - 1);
}

//=================== eventos do MetaTrader ===================
int OnInit()
{
   ConfiguraOrdens(MagicNumber);
   IniciaSerie(g_h1); IniciaSerie(g_h4);
   g_ult_m1 = TimeCurrent() - DIAS_AQUECIMENTO * SEG_DIA;
   Sincroniza(false);
   PrintFormat("EscadaWinM15 v4.1 pronto: %d barras M15 de aquecimento, H4 com %d blocos.", g_nbarras, g_h4.n);
   return INIT_SUCCEEDED;
}

void OnTick()
{
   datetime agora = TimeCurrent();
   if(agora >= HoraCorte(DiaDe(agora))) FazCorte(MagicNumber);   // fim do dia: nada fica aberto
   VigiaStopDaEntrada();
   datetime minuto = agora - (agora % 60);
   if(minuto == g_ult_minuto) return;          // barras só mudam na virada do minuto
   g_ult_minuto = minuto;
   Sincroniza(true);
}

void OnDeinit(const int reason)
{
   GravaNegocios(MagicNumber);
}
