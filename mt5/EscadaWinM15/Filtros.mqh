//+------------------------------------------------------------------+
//| Filtros.mqh — os filtros de entrada da v4.1, lidos na barra de   |
//| confirmação (M15 fechada). Espelha filtros.py.                   |
//| Cada função responde: "o filtro deixa operar este lado?"         |
//+------------------------------------------------------------------+
#ifndef ESCADA_FILTROS
#define ESCADA_FILTROS

#include "Indicadores.mqh"

#define ESTOC_MAX       70.0
#define AQUECIMENTO_H4  30     // o estado do H4 só vale depois de 31 blocos fechados

//--- H1 fechado com tendência MME 9/21/34 a favor.
bool H1AFavor(int lado) { return Tendencia(g_h1) == lado; }

//--- Close da confirmação do lado a favor da abertura do pregão.
bool LadoDaAbertura(int i, int lado)
{
   double abertura = g_barras[InicioDoDia(i)].o;
   return (g_barras[i].c - abertura) * lado > 0;
}

//--- MMS17 acima da MMS34 (close) na compra; abaixo na venda.
bool Mms17AcimaMms34(int i, int lado)
{
   double m17 = MMS(i, 17), m34 = MMS(i, 34);
   if(m17 == INVALIDO || m34 == INVALIDO) return false;
   return (m17 - m34) * lado > 0;
}

//--- MMS72 do open subindo (contra 3 barras atrás) na compra; caindo na venda.
bool Mms72OpenInclinada(int i, int lado)
{
   double agora = MMS(i, 72, true), antes = MMS(i - 3, 72, true);
   if(agora == INVALIDO || antes == INVALIDO) return false;
   return (agora - antes) * lado > 0;
}

//--- Sinal bom: estocástico 14 (suav. 3) abaixo de 70 a favor, OU H4 neutro.
bool SinalBom(int i, int lado)
{
   double k = Estocastico(i);
   bool nao_esticado = k != INVALIDO && (lado == 1 ? k : 100 - k) < ESTOC_MAX;
   bool h4_neutro = g_h4.n > AQUECIMENTO_H4 && Tendencia(g_h4) == 0;
   return nao_esticado || h4_neutro;
}

//--- Todos os filtros da v4.1.
bool PassaFiltrosV41(int i, int lado)
{
   return H1AFavor(lado) && LadoDaAbertura(i, lado) && Mms17AcimaMms34(i, lado)
       && Mms72OpenInclinada(i, lado) && SinalBom(i, lado);
}

#endif
