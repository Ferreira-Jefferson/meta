//+------------------------------------------------------------------+
//| WinMaestro/EscadaWinM15.mqh
//| Robo ES: escada de topos e fundos M15 v4.2 (sempre 1 contrato no Maestro).
//|
//| A logica de SINAL e de STOP e' a MESMA do EA avulso: os arquivos de mt5/EscadaWinM15/
//| (Calendario, Barras, Indicadores, Escada, Filtros, Stop) sao incluidos aqui dentro do
//| namespace WES, sem copia. So' a execucao muda (desenho v2.2 sec. 7):
//|  - sinal -> ENTRAR(limite no close da confirmacao, stop v4.2, validade de 3 barras M15);
//|  - posicao -> MANTER(stop que sobe a cada pivo a favor confirmado, sem alvo);
//|  - validade vencida, entrada cancelada/recusada/perdida -> NADA;
//|  - zeragem e corte: do maestro (fim do continuo - 5 min).
//| Diferenca do avulso: o limite e' posto do lado de dentro do livro se o mercado ja' passou
//| dele (nunca a mercado), como no GB.
//+------------------------------------------------------------------+
#ifndef WINMAESTRO_ESCADAWINM15_MQH
#define WINMAESTRO_ESCADAWINM15_MQH

namespace WES
{
#include "..\EscadaWinM15\Calendario.mqh"
#include "..\EscadaWinM15\Barras.mqh"
#include "..\EscadaWinM15\Indicadores.mqh"
#include "..\EscadaWinM15\Escada.mqh"
#include "..\EscadaWinM15\Filtros.mqh"
#include "..\EscadaWinM15\Stop.mqh"

#define ES_VALIDADE_BARRAS 3
#define ES_DIAS_AQUECIMENTO 120

double   g_stop      = 0.0;    // stop pedido para a posicao (ou para a entrada armada)
datetime g_expira    = 0;      // fim da validade da entrada armada
datetime g_ult_min   = 0;      // ultimo minuto em que as barras foram lidas

//--- Volta todo o estado (barras, indicadores, entrada) ao inicial (P17).
void Reseta()
{
   ArrayResize(g_barras, 0); g_nbarras = 0; g_tem_aberta = false; g_ult_m1 = 0;
   ArrayResize(g_mme38, 0); IniciaSerie(g_h1); IniciaSerie(g_h4);
   g_stop = 0.0; g_expira = 0; g_ult_min = 0;
}

void Configura() { }

//--- Preco do limite do lado de dentro do livro: se o mercado ja' passou dele, fica a 1 tick da melhor oferta.
double LimiteNoLivro(int lado, double limite)
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID), ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(lado == 1 && ask > 0.0 && limite >= ask)  return ask - TICK_WIN;
   if(lado == -1 && bid > 0.0 && limite <= bid) return bid + TICK_WIN;
   return limite;
}

//--- Com posicao: se a barra i confirmou um pivo a favor, o stop sobe (desce na venda) para ele.
void GerePosicao(int i, const Pivo &piv[], const VistaRobo &v, Intencao &ped)
{
   int p = PivoConfirmadoEm(piv, i);
   double atual = g_stop > 0.0 ? g_stop : v.stop_pedido;
   double novo = p >= 0 ? StopPelaEstrutura(atual, piv[p], v.lado) : atual;
   if(novo != g_stop || ped.tipo != INT_MANTER)
   {
      g_stop = novo;
      Int_Manter(ped, g_stop, 0.0, p >= 0 ? "escada stop na estrutura" : "escada posicao");
   }
}

//--- Sem posicao nem entrada armada: a barra i virou sinal da v4.2?
void ProcuraEntrada(int i, const Pivo &piv[], Intencao &ped)
{
   int p = PivoConfirmadoEm(piv, i);
   if(p < 0) return;
   int est = Estagio(piv, p);
   if(est == SEM_ESTAGIO || est < 1) return;
   datetime fecha = g_barras[i].t + SEG_BARRA;
   if(fecha >= HoraCorte(g_barras[i].dia)) return;
   int lado = LadoDoPivo(piv[p]);
   if(!PassaFiltros(i, lado)) return;
   double stop = StopInicial(i, lado, piv[p].preco);
   double limite = LimiteNoLivro(lado, g_barras[i].c);
   if((limite - stop) * lado <= 0) return;
   if(Ficha_DecisaoPerdida(R_ES, fecha, "sinal da escada")) return;
   g_stop = stop;
   g_expira = fecha + ES_VALIDADE_BARRAS * SEG_BARRA;
   PrintFormat("ES sinal %s est%d: confirmacao %s, limite %.0f, stop %.0f, validade %s", lado == 1 ? "COMPRA" : "VENDA", est,
               TimeToString(g_barras[i].t, TIME_DATE | TIME_MINUTES), limite, stop, TimeToString(g_expira, TIME_MINUTES));
   Int_Entrar(ped, Ficha_NovoId(R_ES), lado, limite, stop, g_expira, "escada sinal");
}

//--- Uma M15 fechou: indicadores sempre; decisao so' na mais recente.
void AoFecharBarra(int i, bool decide, const VistaRobo &v, Intencao &ped)
{
   AtualizaIndicadores(i);
   if(!decide) return;
   Pivo piv[];
   ZigZag(InicioDoDia(i), i, piv);
   if(v.tem) { GerePosicao(i, piv, v, ped); return; }
   if(ped.tipo == INT_ENTRAR) return;               // uma entrada por vez
   ProcuraEntrada(i, piv, ped);
}

void Tick(const VistaRobo &v, Intencao &ped)
{
   if(ped.tipo == INT_ENTRAR && g_expira > 0 && v.agora >= g_expira) { Int_Nada(ped, "escada validade da entrada"); g_expira = 0; }
   if(!v.tem && ped.tipo == INT_MANTER) Int_Nada(ped, "escada posicao encerrada");
   if(v.tem && ped.tipo != INT_MANTER) Int_Manter(ped, g_stop > 0.0 ? g_stop : v.stop_pedido, 0.0, "escada posicao");
   datetime minuto = v.agora - (v.agora % 60);
   if(minuto == g_ult_min) return;                   // barras so' mudam na virada do minuto
   g_ult_min = minuto;
   int novas[];
   int n = SincronizaBarras(v.agora, novas);
   for(int k = 0; k < n; k++) AoFecharBarra(novas[k], k == n - 1, v, ped);
}

void Evento(const SEvento &e, const VistaRobo &v, Intencao &ped)
{
   if(e.ev == EV_ENTRADA_EXECUTADA) { g_expira = 0; Int_Manter(ped, g_stop, 0.0, "escada entrada executada"); }
   else if(e.ev == EV_ENTRADA_CANCELADA || e.ev == EV_ENTRADA_RECUSADA || e.ev == EV_ENTRADA_PERDIDA)
   { g_expira = 0; if(!v.tem) Int_Nada(ped, "escada entrada encerrada"); }
}

//--- Stop pela regra do robo para a ficha atual (0 = sem regra).
double StopRegra(const int lado)
{
   if(!Ficha_Tem(R_ES) || Ficha_Lado(R_ES) != lado || g_stop <= 0.0) return 0.0;
   return g_stop;
}

int MinutoZerarRobo(const datetime dia) { return FimContinuoMin(dia) - MIN_CORTE_ANTES; }

void Exporta()
{
   Mem_SetD("ES.stop", g_stop);
   Mem_SetI("ES.expira", (long)g_expira);
}

void Importa()
{
   g_stop = Car_GetD("ES.stop", 0.0);
   g_expira = (datetime)Car_GetI("ES.expira", 0);
}

//--- Partida: le o historico M1 para as medias, o ATR e o H4 ja' valerem (nenhuma decisao no aquecimento).
int Init(const VistaRobo &v)
{
   Reseta();
   Importa();
   g_ult_m1 = v.agora - ES_DIAS_AQUECIMENTO * SEG_DIA;
   int novas[];
   int n = SincronizaBarras(v.agora, novas);
   for(int k = 0; k < n; k++) AtualizaIndicadores(novas[k]);
   g_ult_min = v.agora - (v.agora % 60);
   PrintFormat("ES pronto: %d barras M15 de aquecimento, H4 com %d blocos", g_nbarras, g_h4.n);
   return INIT_SUCCEEDED;
}

void Deinit(const int reason) { }

} // namespace WES

#endif
